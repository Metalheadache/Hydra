"""
Tests for the Hydra event system (EventBus, HydraEvent, EventType).
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest
import pytest_asyncio

from hydra_agents.events import EventBus, EventType, HydraEvent


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def bus() -> EventBus:
    return EventBus()


# ── Basic emit / receive ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eventbus_basic_emit_sync_listener(bus: EventBus):
    """Sync listeners are called on emit."""
    received: List[HydraEvent] = []
    bus.on(received.append)

    event = HydraEvent(type=EventType.PIPELINE_START, data={"x": 1})
    await bus.emit(event)

    assert len(received) == 1
    assert received[0].type == EventType.PIPELINE_START
    assert received[0].data == {"x": 1}


@pytest.mark.asyncio
async def test_eventbus_multiple_sync_listeners(bus: EventBus):
    """Multiple sync listeners all receive the event."""
    a: List[HydraEvent] = []
    b: List[HydraEvent] = []
    bus.on(a.append)
    bus.on(b.append)

    await bus.emit(HydraEvent(type=EventType.AGENT_START))

    assert len(a) == 1
    assert len(b) == 1


@pytest.mark.asyncio
async def test_eventbus_async_listener(bus: EventBus):
    """Async listeners are called and awaited."""
    received: List[HydraEvent] = []

    async def async_cb(event: HydraEvent) -> None:
        received.append(event)

    bus.on_async(async_cb)

    await bus.emit(HydraEvent(type=EventType.AGENT_COMPLETE, agent_id="agent1"))

    # Async listeners are scheduled as tasks — give the event loop a moment
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].agent_id == "agent1"


@pytest.mark.asyncio
async def test_eventbus_stream_yields_events_in_order(bus: EventBus):
    """stream() yields events in emission order."""
    types = [
        EventType.PIPELINE_START,
        EventType.BRAIN_START,
        EventType.BRAIN_COMPLETE,
        EventType.PIPELINE_COMPLETE,
    ]

    async def _emit_all():
        for t in types:
            await bus.emit(HydraEvent(type=t))
        await bus.close()

    asyncio.create_task(_emit_all())

    collected = []
    async for event in bus.stream():
        collected.append(event.type)

    assert collected == types


@pytest.mark.asyncio
async def test_eventbus_stream_stops_on_sentinel(bus: EventBus):
    """stream() stops cleanly when close() is called."""
    bus._has_stream_consumer = True  # simulate stream() being active
    await bus.emit(HydraEvent(type=EventType.AGENT_START))
    await bus.close()

    collected = []
    async for event in bus.stream():
        collected.append(event)

    assert len(collected) == 1


# ── Event filtering (manual) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_event_filtering_by_type(bus: EventBus):
    """Demonstrate manual type filtering pattern."""
    agent_events: List[HydraEvent] = []

    def _only_agent_start(event: HydraEvent) -> None:
        if event.type == EventType.AGENT_START:
            agent_events.append(event)

    bus.on(_only_agent_start)

    await bus.emit(HydraEvent(type=EventType.PIPELINE_START))
    await bus.emit(HydraEvent(type=EventType.AGENT_START, agent_id="a1"))
    await bus.emit(HydraEvent(type=EventType.AGENT_COMPLETE, agent_id="a1"))
    await bus.emit(HydraEvent(type=EventType.AGENT_START, agent_id="a2"))

    assert len(agent_events) == 2
    assert all(e.type == EventType.AGENT_START for e in agent_events)


# ── HydraEvent fields ─────────────────────────────────────────────────────────

def test_hydra_event_defaults():
    """HydraEvent has sensible defaults."""
    event = HydraEvent(type=EventType.AGENT_TOKEN)
    assert event.timestamp > 0
    assert event.agent_id is None
    assert event.sub_task_id is None
    assert event.tokens is None
    assert event.metadata == {}


def test_hydra_event_fields():
    """HydraEvent stores all fields."""
    event = HydraEvent(
        type=EventType.AGENT_TOOL_CALL,
        agent_id="agent_1",
        sub_task_id="st_1",
        group_index=0,
        tokens=42,
        data={"tool": "web_search"},
        metadata={"extra": "info"},
    )
    assert event.type == EventType.AGENT_TOOL_CALL
    assert event.agent_id == "agent_1"
    assert event.sub_task_id == "st_1"
    assert event.group_index == 0
    assert event.tokens == 42
    assert event.data["tool"] == "web_search"
    assert event.metadata["extra"] == "info"


# ── Callback registration via Hydra.on_* ──────────────────────────────────────

@pytest.mark.asyncio
async def test_hydra_on_agent_start_callback():
    """Hydra.on_agent_start registers a filtered callback."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from hydra_agents import Hydra

    hydra = Hydra.__new__(Hydra)
    hydra._event_callbacks = []

    agent_start_events: List[HydraEvent] = []
    hydra.on_agent_start(agent_start_events.append)

    # Build a bus and wire it
    bus = EventBus()
    hydra._wire_callbacks(bus)

    # Emit filtered and unfiltered events
    await bus.emit(HydraEvent(type=EventType.PIPELINE_START))
    await bus.emit(HydraEvent(type=EventType.AGENT_START, agent_id="a1"))
    await bus.emit(HydraEvent(type=EventType.AGENT_COMPLETE, agent_id="a1"))
    await bus.emit(HydraEvent(type=EventType.AGENT_START, agent_id="a2"))

    assert len(agent_start_events) == 2
    assert all(e.type == EventType.AGENT_START for e in agent_start_events)


@pytest.mark.asyncio
async def test_hydra_on_agent_complete_callback():
    """Hydra.on_agent_complete registers a filtered callback."""
    from hydra_agents import Hydra

    hydra = Hydra.__new__(Hydra)
    hydra._event_callbacks = []

    complete_events: List[HydraEvent] = []
    hydra.on_agent_complete(complete_events.append)

    bus = EventBus()
    hydra._wire_callbacks(bus)

    await bus.emit(HydraEvent(type=EventType.AGENT_START))
    await bus.emit(HydraEvent(type=EventType.AGENT_COMPLETE, agent_id="x"))

    assert len(complete_events) == 1
    assert complete_events[0].agent_id == "x"


@pytest.mark.asyncio
async def test_hydra_on_tool_call_callback():
    """Hydra.on_tool_call registers a filtered callback for AGENT_TOOL_CALL."""
    from hydra_agents import Hydra

    hydra = Hydra.__new__(Hydra)
    hydra._event_callbacks = []

    tool_events: List[HydraEvent] = []
    hydra.on_tool_call(tool_events.append)

    bus = EventBus()
    hydra._wire_callbacks(bus)

    await bus.emit(HydraEvent(type=EventType.AGENT_START))
    await bus.emit(HydraEvent(type=EventType.AGENT_TOOL_CALL, data={"tool": "web_search"}))
    await bus.emit(HydraEvent(type=EventType.AGENT_TOOL_RESULT, data={"tool": "web_search", "success": True}))

    assert len(tool_events) == 1
    assert tool_events[0].data["tool"] == "web_search"


@pytest.mark.asyncio
async def test_hydra_on_event_catch_all():
    """Hydra.on_event is a catch-all callback."""
    from hydra_agents import Hydra

    hydra = Hydra.__new__(Hydra)
    hydra._event_callbacks = []

    all_events: List[HydraEvent] = []
    hydra.on_event(all_events.append)

    bus = EventBus()
    hydra._wire_callbacks(bus)

    for event_type in [
        EventType.PIPELINE_START,
        EventType.AGENT_START,
        EventType.AGENT_COMPLETE,
        EventType.SYNTHESIS_START,
        EventType.PIPELINE_COMPLETE,
    ]:
        await bus.emit(HydraEvent(type=event_type))

    assert len(all_events) == 5


# ── Error resilience ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eventbus_listener_exception_does_not_propagate(bus: EventBus):
    """A crashing listener must not crash the pipeline."""
    crash_count = 0

    def bad_listener(event: HydraEvent) -> None:
        nonlocal crash_count
        crash_count += 1
        raise RuntimeError("intentional crash")

    good_received: List[HydraEvent] = []
    bus.on(bad_listener)
    bus.on(good_received.append)

    # This should NOT raise
    await bus.emit(HydraEvent(type=EventType.AGENT_START))

    assert crash_count == 1
    assert len(good_received) == 1  # Good listener still received it


# ── Confirmation gate tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_confirmation_timeout_cleans_up_state():
    """When request_confirmation times out, both dicts should be empty (no memory leak)."""
    bus = EventBus()

    # No responder — it will time out
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            bus.request_confirmation(
                confirmation_id="test-id-1",
                tool_name="dangerous_tool",
                args={"key": "value"},
            ),
            timeout=0.01,
        )

    # Both dicts must be empty after timeout
    assert "test-id-1" not in bus._pending_confirmations, "Memory leak: _pending_confirmations not cleaned up"
    assert "test-id-1" not in bus._confirmation_responses, "Memory leak: _confirmation_responses not cleaned up"


@pytest.mark.asyncio
async def test_respond_to_confirmation_unknown_id_is_noop():
    """respond_to_confirmation with an unknown ID should be a no-op (no state written)."""
    bus = EventBus()
    unknown_id = "non-existent-confirmation-id"

    # Should not raise and should not write to _confirmation_responses
    await bus.respond_to_confirmation(unknown_id, approved=True)

    assert unknown_id not in bus._confirmation_responses
    assert unknown_id not in bus._pending_confirmations


@pytest.mark.asyncio
async def test_request_confirmation_approval_flow():
    """Normal approval flow should return True and clean up state."""
    bus = EventBus()
    conf_id = "approve-test"

    async def _auto_approve():
        await asyncio.sleep(0.01)
        await bus.respond_to_confirmation(conf_id, approved=True)

    asyncio.create_task(_auto_approve())

    result = await asyncio.wait_for(
        bus.request_confirmation(
            confirmation_id=conf_id,
            tool_name="some_tool",
            args={},
        ),
        timeout=1.0,
    )

    assert result is True
    # State should be cleaned up after successful confirmation
    assert conf_id not in bus._pending_confirmations
    assert conf_id not in bus._confirmation_responses
