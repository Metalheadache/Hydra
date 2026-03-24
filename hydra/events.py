"""
Hydra Event System — EventBus, HydraEvent, and EventType definitions.

Components emit events; listeners and stream() consumers receive them.
EventBus is optional everywhere — all components guard emits with
`if self.event_bus:`.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # Brain
    BRAIN_START = "brain_start"
    BRAIN_COMPLETE = "brain_complete"

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_TOOL_RESULT = "agent_tool_result"
    AGENT_TOKEN = "agent_token"           # streaming token
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    AGENT_RETRY = "agent_retry"

    # Execution groups
    GROUP_START = "group_start"           # parallel group starting
    GROUP_COMPLETE = "group_complete"

    # PostBrain
    QUALITY_START = "quality_start"
    QUALITY_SCORE = "quality_score"       # per-agent score
    QUALITY_RETRY = "quality_retry"
    SYNTHESIS_START = "synthesis_start"
    SYNTHESIS_TOKEN = "synthesis_token"   # streaming synthesis
    SYNTHESIS_COMPLETE = "synthesis_complete"

    # File processing
    FILE_PROCESSED = "file_processed"   # after each file is processed

    # Pipeline
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"


class HydraEvent(BaseModel):
    type: EventType
    timestamp: float = Field(default_factory=time.time)
    data: Any = None
    agent_id: str | None = None
    sub_task_id: str | None = None
    group_index: int | None = None
    tokens: int | None = None
    metadata: dict = {}


class EventBus:
    """
    Central event dispatcher. Components emit events; listeners receive them.

    - Sync listeners are called inline (must be fast — they block the emitting coroutine
      only for their own duration; slow listeners should use on_async instead).
    - Async listeners are scheduled as background tasks (truly non-blocking).
    - All emitted events are also pushed to an internal asyncio.Queue consumed
      by stream(). Queue is bounded (maxsize=10000) to prevent unbounded growth.
    - When no stream() consumer exists (_has_stream_consumer=False), events are
      not enqueued (run() + callbacks path optimization).
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[HydraEvent], None]] = []
        self._async_listeners: list[Callable[[HydraEvent], Awaitable[None]]] = []
        self._queue: asyncio.Queue[HydraEvent | None] = asyncio.Queue(maxsize=10000)
        self._has_stream_consumer: bool = False
        self._pending_tasks: set[asyncio.Task] = set()

    # ── Registration ──────────────────────────────────────────────────────────

    def on(self, callback: Callable[[HydraEvent], None]) -> None:
        """Register a sync callback for all events."""
        self._listeners.append(callback)

    def on_async(self, callback: Callable[[HydraEvent], Awaitable[None]]) -> None:
        """Register an async callback for all events."""
        self._async_listeners.append(callback)

    # ── Emission ──────────────────────────────────────────────────────────────

    async def emit(self, event: HydraEvent) -> None:
        """
        Emit an event to all listeners and push to the stream queue.

        Sync listeners are called directly (fire-and-forget, errors are swallowed).
        Async listeners are scheduled as background tasks.
        """
        # Sync listeners — called inline, must be fast
        for cb in self._listeners:
            try:
                cb(event)
            except Exception:
                pass  # Never let a listener crash the pipeline

        # Async listeners — fire-and-forget tasks (tracked for drain())
        for cb in self._async_listeners:
            task = asyncio.create_task(_safe_async_call(cb, event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)

        # Push to queue for stream() — only when a consumer exists
        if self._has_stream_consumer:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                import logging
                logging.getLogger(__name__).warning(
                    "EventBus queue full (maxsize=10000); discarding event type=%s", event.type
                )

    async def drain(self) -> None:
        """Await all pending async listener tasks."""
        if self._pending_tasks:
            await asyncio.gather(*list(self._pending_tasks), return_exceptions=True)

    async def close(self) -> None:
        """Signal stream() consumers to stop by pushing a sentinel."""
        await self.drain()
        await self._queue.put(None)  # sentinel

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(self) -> AsyncGenerator[HydraEvent, None]:
        """
        Async generator that yields events as they arrive.

        Stops when a None sentinel is received (via close()) or when the
        consumer breaks out (e.g. on PIPELINE_COMPLETE / PIPELINE_ERROR).
        Sets _has_stream_consumer=True so emit() starts enqueuing events.
        """
        self._has_stream_consumer = True
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event


async def _safe_async_call(
    callback: Callable[[HydraEvent], Awaitable[None]],
    event: HydraEvent,
) -> None:
    """Execute an async callback, swallowing exceptions."""
    try:
        await callback(event)
    except Exception:
        pass
