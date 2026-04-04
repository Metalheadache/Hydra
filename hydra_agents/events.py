"""
Hydra Event System — EventBus, HydraEvent, and EventType definitions.

Components emit events; listeners and stream() consumers receive them.
EventBus is optional everywhere — all components guard emits with
`if self.event_bus:`.
"""

from __future__ import annotations

import asyncio
import logging
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

    # Human-in-the-loop confirmation
    CONFIRMATION_REQUIRED = "confirmation_required"   # tool needs approval
    CONFIRMATION_RESPONSE = "confirmation_response"   # user approved/rejected

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
    metadata: dict = Field(default_factory=dict)


logger = logging.getLogger(__name__)


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

        # Telemetry counters
        self._events_emitted: int = 0
        self._events_dropped: int = 0
        self._events_delivered: int = 0

        # Confirmation gate state
        self._pending_confirmations: dict[str, asyncio.Event] = {}
        self._confirmation_responses: dict[str, bool] = {}

    @property
    def stats(self) -> dict[str, int]:
        """Telemetry snapshot: emitted, delivered, dropped counts."""
        return {
            "emitted": self._events_emitted,
            "delivered": self._events_delivered,
            "dropped": self._events_dropped,
        }

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
        self._events_emitted += 1
        if self._has_stream_consumer:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                self._events_dropped += 1
                logger.warning(
                    "eventbus_queue_full",
                    event_type=str(event.type),
                    dropped_total=self._events_dropped,
                    emitted_total=self._events_emitted,
                )

    async def drain(self) -> None:
        """Await all pending async listener tasks."""
        if self._pending_tasks:
            await asyncio.gather(*list(self._pending_tasks), return_exceptions=True)

    async def close(self) -> None:
        """Signal stream() consumers to stop by pushing a sentinel."""
        await self.drain()
        # If queue is full, drop exactly one event to make room for sentinel
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._events_dropped += 1
                logger.debug("eventbus_close_drop", reason="making room for sentinel")
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(None)  # sentinel — non-blocking
        except asyncio.QueueFull:
            pass  # consumer already gone, sentinel not needed
        if self._events_dropped > 0:
            logger.info(
                "eventbus_closed",
                emitted=self._events_emitted,
                delivered=self._events_delivered,
                dropped=self._events_dropped,
            )
        self._has_stream_consumer = False

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(self) -> AsyncGenerator[HydraEvent, None]:
        """
        Async generator that yields events as they arrive.

        Stops when a None sentinel is received (via close()) or when the
        consumer breaks out (e.g. on PIPELINE_COMPLETE / PIPELINE_ERROR).
        Sets _has_stream_consumer=True so emit() starts enqueuing events.
        """
        self._has_stream_consumer = True
        try:
            while True:
                event = await self._queue.get()
                if event is None:
                    break
                self._events_delivered += 1
                yield event
        finally:
            self._has_stream_consumer = False


    # ── Confirmation gates ────────────────────────────────────────────────────

    async def request_confirmation(
        self,
        confirmation_id: str,
        tool_name: str,
        args: dict,
    ) -> bool:
        """
        Emit a CONFIRMATION_REQUIRED event and wait for an external response.

        Returns True if approved, False if rejected.
        The caller is responsible for applying a timeout (e.g. asyncio.wait_for).
        """
        event = asyncio.Event()
        self._pending_confirmations[confirmation_id] = event
        self._confirmation_responses[confirmation_id] = False  # default: rejected

        try:
            await self.emit(HydraEvent(
                type=EventType.CONFIRMATION_REQUIRED,
                data={
                    "confirmation_id": confirmation_id,
                    "tool_name": tool_name,
                    "args": args,
                },
            ))

            await event.wait()
            return self._confirmation_responses.pop(confirmation_id, False)
        finally:
            self._pending_confirmations.pop(confirmation_id, None)
            self._confirmation_responses.pop(confirmation_id, None)

    async def respond_to_confirmation(self, confirmation_id: str, approved: bool) -> None:
        """
        Called by the frontend/API to approve or reject a pending confirmation.

        If the confirmation_id is not found (already timed out), this is a no-op.
        """
        if confirmation_id not in self._pending_confirmations:
            return
        self._confirmation_responses[confirmation_id] = approved
        event = self._pending_confirmations.get(confirmation_id)
        if event is not None:
            event.set()

        await self.emit(HydraEvent(
            type=EventType.CONFIRMATION_RESPONSE,
            data={
                "confirmation_id": confirmation_id,
                "approved": approved,
            },
        ))


async def _safe_async_call(
    callback: Callable[[HydraEvent], Awaitable[None]],
    event: HydraEvent,
) -> None:
    """Execute an async callback, swallowing exceptions."""
    try:
        await callback(event)
    except Exception:
        pass
