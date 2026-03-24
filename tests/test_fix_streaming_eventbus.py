"""
Tests for the 6 streaming/EventBus fixes:
1. Agent with event_bus uses streaming; without event_bus uses non-streaming
2. EventBus queue overflow (10001+ events, no crash)
3. EventBus drain() completes pending tasks
4. stream() timeout emits PIPELINE_ERROR
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.events import EventBus, EventType, HydraEvent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stream_chunk(content: str | None = None, tool_calls=None, usage=None):
    """Build a mock litellm streaming chunk."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls

    choice = MagicMock()
    choice.delta = delta

    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _make_finish_chunk(usage_total: int = 10):
    """Final chunk with usage info."""
    usage = MagicMock()
    usage.total_tokens = usage_total
    usage.prompt_tokens = 5
    usage.completion_tokens = 5
    return _make_stream_chunk(content=None, usage=usage)


async def _async_chunks(*chunks) -> AsyncIterator:
    """Yield chunks asynchronously."""
    for chunk in chunks:
        yield chunk


# ── Fix 1: Agent uses streaming vs non-streaming based on event_bus ──────────

@pytest.mark.asyncio
async def test_agent_with_event_bus_uses_streaming():
    """Agent with event_bus must call litellm.acompletion with stream=True."""
    from hydra.agent import Agent
    from hydra.config import HydraConfig
    from hydra.models import AgentSpec, SubTask, Priority
    from hydra.tool_registry import ToolRegistry

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")
    spec = AgentSpec(
        agent_id="test_agent",
        sub_task_id="st_1",
        role="Test Agent",
        goal="Test goal",
        backstory="Test",
        tools_needed=[],
    )
    sub_task = SubTask(
        id="st_1",
        description="Test task",
        expected_output="Some output",
        priority=Priority.NORMAL,
    )
    state_manager = MagicMock()
    state_manager.get_upstream_context = AsyncMock(return_value="")
    state_manager.write_output = AsyncMock()
    state_manager.write_shared = AsyncMock()

    event_bus = EventBus()
    agent = Agent(
        agent_spec=spec,
        sub_task=sub_task,
        tool_registry=ToolRegistry(),
        state_manager=state_manager,
        config=config,
        event_bus=event_bus,
    )

    captured_kwargs: dict = {}

    async def mock_acompletion(**kwargs):
        captured_kwargs.update(kwargs)
        return _async_chunks(
            _make_stream_chunk("Hello world!"),
            _make_finish_chunk(),
        )

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        await agent.execute()

    assert captured_kwargs.get("stream") is True, (
        "Agent with event_bus must use stream=True"
    )


@pytest.mark.asyncio
async def test_agent_without_event_bus_does_not_stream():
    """Agent without event_bus must call litellm.acompletion with stream=False (or omitted)."""
    from hydra.agent import Agent
    from hydra.config import HydraConfig
    from hydra.models import AgentSpec, SubTask, Priority
    from hydra.tool_registry import ToolRegistry

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")
    spec = AgentSpec(
        agent_id="test_agent_no_bus",
        sub_task_id="st_2",
        role="Test Agent No Bus",
        goal="Test goal",
        backstory="Test",
        tools_needed=[],
    )
    sub_task = SubTask(
        id="st_2",
        description="Test task",
        expected_output="Some output",
        priority=Priority.NORMAL,
    )
    state_manager = MagicMock()
    state_manager.get_upstream_context = AsyncMock(return_value="")
    state_manager.write_output = AsyncMock()
    state_manager.write_shared = AsyncMock()

    # No event_bus
    agent = Agent(
        agent_spec=spec,
        sub_task=sub_task,
        tool_registry=ToolRegistry(),
        state_manager=state_manager,
        config=config,
        event_bus=None,
    )

    captured_kwargs: dict = {}

    def mock_acompletion_sync(**kwargs):
        captured_kwargs.update(kwargs)
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Hello world!"
        response.choices[0].message.tool_calls = None
        response.usage = MagicMock()
        response.usage.total_tokens = 10
        return response

    # Non-streaming: return a plain response (not async iterator)
    with patch("litellm.acompletion", AsyncMock(side_effect=mock_acompletion_sync)):
        await agent.execute()

    # stream should NOT be True in the call kwargs
    assert captured_kwargs.get("stream") is not True, (
        "Agent without event_bus must NOT use stream=True"
    )


# ── Fix 2: EventBus queue overflow ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_eventbus_queue_overflow_no_crash():
    """Putting 10001+ events into the queue must not crash (bounded at 10000)."""
    bus = EventBus()
    # Don't call stream() — just emit many events
    for i in range(10001):
        await bus.emit(HydraEvent(type=EventType.AGENT_TOKEN, data={"i": i}))

    # Queue should be at maxsize (10000), not crash
    assert bus._queue.qsize() <= 10000


@pytest.mark.asyncio
async def test_eventbus_queue_bounded():
    """EventBus queue has maxsize=10000."""
    bus = EventBus()
    assert bus._queue.maxsize == 10000


# ── Fix 3: EventBus drain() completes pending tasks ──────────────────────────

@pytest.mark.asyncio
async def test_eventbus_drain_completes_pending_tasks():
    """drain() awaits all pending async listener tasks."""
    bus = EventBus()

    results: list[str] = []

    async def slow_listener(event: HydraEvent) -> None:
        await asyncio.sleep(0.01)
        results.append(event.type)

    bus.on_async(slow_listener)

    # Emit 3 events — each schedules a background task
    for _ in range(3):
        await bus.emit(HydraEvent(type=EventType.AGENT_START))

    # Before drain, tasks may not be complete
    # After drain, all tasks must be done
    await bus.drain()

    assert len(results) == 3, (
        f"drain() should await all pending tasks, but only {len(results)}/3 completed"
    )


@pytest.mark.asyncio
async def test_eventbus_close_drains_before_sentinel():
    """close() should drain pending tasks before sending sentinel."""
    bus = EventBus()

    results: list[str] = []

    async def async_listener(event: HydraEvent) -> None:
        await asyncio.sleep(0.01)
        results.append(event.type)

    bus.on_async(async_listener)
    await bus.emit(HydraEvent(type=EventType.AGENT_START))
    await bus.emit(HydraEvent(type=EventType.AGENT_COMPLETE))
    await bus.close()

    # After close(), pending async tasks should be done
    assert len(results) == 2


# ── Fix 4: stream() timeout emits PIPELINE_ERROR ─────────────────────────────

@pytest.mark.asyncio
async def test_stream_timeout_emits_pipeline_error():
    """stream() must emit PIPELINE_ERROR event when pipeline times out."""
    from hydra import Hydra
    from hydra.config import HydraConfig

    # 1 second timeout
    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini", total_task_timeout_seconds=1)
    hydra = Hydra(config=config)

    async def _slow_pipeline(task: str, state_ref=None, event_bus=None, **kwargs):
        await asyncio.sleep(60)  # Much longer than timeout
        return {"output": "never", "warnings": [], "execution_summary": {}, "files_generated": [], "per_agent_quality": {}, "agents_needing_retry": []}

    collected_events: List[HydraEvent] = []

    with patch.object(hydra, "_run_pipeline", side_effect=_slow_pipeline):
        async for event in hydra.stream("Test task"):
            collected_events.append(event)

    event_types = [e.type for e in collected_events]
    assert EventType.PIPELINE_ERROR in event_types, (
        "stream() must yield PIPELINE_ERROR when pipeline times out"
    )
    error_event = next(e for e in collected_events if e.type == EventType.PIPELINE_ERROR)
    assert "timed out" in str(error_event.data.get("error", "")).lower(), (
        "PIPELINE_ERROR data must mention timeout"
    )


@pytest.mark.asyncio
async def test_stream_timeout_cancels_pipeline_task():
    """stream() must cancel the pipeline task on timeout."""
    from hydra import Hydra
    from hydra.config import HydraConfig

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini", total_task_timeout_seconds=1)
    hydra = Hydra(config=config)

    pipeline_cancelled = asyncio.Event()

    async def _slow_pipeline(task: str, state_ref=None, event_bus=None, **kwargs):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pipeline_cancelled.set()
            raise

    with patch.object(hydra, "_run_pipeline", side_effect=_slow_pipeline):
        async for _ in hydra.stream("Test task"):
            pass

    # Give a moment for cancellation to propagate
    await asyncio.sleep(0.1)
    assert pipeline_cancelled.is_set(), "Pipeline task must be cancelled on timeout"
