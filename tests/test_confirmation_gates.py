"""
Tests for Feature 1: Human-in-the-Loop Confirmation Gates.
"""

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.agent import Agent
from hydra.config import HydraConfig
from hydra.events import EventBus, EventType, HydraEvent
from hydra.models import AgentSpec, AgentStatus, SubTask, ToolResult
from hydra.tool_registry import ToolRegistry
from hydra.tools.base import BaseTool


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_config() -> HydraConfig:
    return HydraConfig(api_key="test-key", per_agent_timeout_seconds=5)


def make_sub_task(task_id: str = "st_1") -> SubTask:
    return SubTask(
        id=task_id,
        description="Do something",
        expected_output="A result",
    )


def make_spec(sub_task_id: str = "st_1", tools: list[str] | None = None) -> AgentSpec:
    return AgentSpec(
        sub_task_id=sub_task_id,
        role="Test Agent",
        goal="Complete task",
        backstory="Expert tester",
        tools_needed=tools or [],
    )


def make_llm_response(content: str, tool_calls=None):
    """Non-streaming response for tests WITHOUT event_bus."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = 100
    usage.prompt_tokens = 60
    usage.completion_tokens = 40
    resp.usage = usage
    return resp


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


def _make_finish_chunk():
    usage = MagicMock()
    usage.total_tokens = 100
    usage.prompt_tokens = 60
    usage.completion_tokens = 40
    return _make_stream_chunk(content=None, usage=usage)


async def _async_chunks(*chunks) -> AsyncIterator:
    for chunk in chunks:
        yield chunk


def make_streaming_response(content: str, tool_calls_data: list | None = None):
    """Streaming response for tests WITH event_bus.
    Returns an async iterable that yields streaming chunks.
    """
    if tool_calls_data:
        # First chunk: tool call
        tc_chunk = _make_stream_chunk()
        # Return async iterable with tool call delta + finish
        async def _tool_stream():
            # Emit empty content chunk first
            yield _make_stream_chunk(content=None)
            # Emit tool call deltas
            for i, tc in enumerate(tool_calls_data):
                tc_delta = MagicMock()
                tc_delta.index = i
                tc_delta.id = tc["id"]
                tc_delta.function = MagicMock()
                tc_delta.function.name = tc["function"]["name"]
                tc_delta.function.arguments = tc["function"]["arguments"]
                delta = MagicMock()
                delta.content = None
                delta.tool_calls = [tc_delta]
                choice = MagicMock()
                choice.delta = delta
                chunk = MagicMock()
                chunk.choices = [choice]
                chunk.usage = None
                yield chunk
            yield _make_finish_chunk()
        return _tool_stream()
    else:
        # Simple content response
        return _async_chunks(
            _make_stream_chunk(content=content),
            _make_finish_chunk(),
        )


class NormalTool(BaseTool):
    name = "normal_tool"
    description = "A normal tool that runs without confirmation"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    requires_confirmation = False

    async def execute(self, text: str = "") -> ToolResult:
        return ToolResult(success=True, data={"result": f"done: {text}"})


class ConfirmationTool(BaseTool):
    name = "confirmation_tool"
    description = "A tool that requires user confirmation before executing"
    parameters = {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}
    requires_confirmation = True

    async def execute(self, cmd: str = "") -> ToolResult:
        return ToolResult(success=True, data={"executed": cmd})


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_event_types_exist():
    """CONFIRMATION_REQUIRED and CONFIRMATION_RESPONSE must be in EventType enum."""
    assert EventType.CONFIRMATION_REQUIRED == "confirmation_required"
    assert EventType.CONFIRMATION_RESPONSE == "confirmation_response"


@pytest.mark.asyncio
async def test_tool_without_confirmation_runs_normally():
    """Tool with requires_confirmation=False should run without any gate."""
    config = make_config()
    spec = make_spec(tools=["normal_tool"])
    sub_task = make_sub_task()
    from hydra.state_manager import StateManager
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(NormalTool())

    agent = Agent(spec, sub_task, registry, sm, config)

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "normal_tool"
    tool_call.function.arguments = json.dumps({"text": "hello"})

    first_response = make_llm_response("", tool_calls=[tool_call])
    second_response = make_llm_response("Normal tool ran fine.")
    second_response.choices[0].message.tool_calls = None

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[first_response, second_response]):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    assert "Normal tool ran fine" in str(output.output)


@pytest.mark.asyncio
async def test_confirmation_tool_approved_executes():
    """When confirmation is approved, the tool should execute and return its result."""
    config = make_config()
    spec = make_spec(tools=["confirmation_tool"])
    sub_task = make_sub_task()
    from hydra.state_manager import StateManager
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(ConfirmationTool())

    event_bus = EventBus()
    agent = Agent(spec, sub_task, registry, sm, config, event_bus=event_bus)

    # Approve automatically when CONFIRMATION_REQUIRED is emitted
    async def auto_approve(event: HydraEvent):
        if event.type == EventType.CONFIRMATION_REQUIRED:
            cid = event.data["confirmation_id"]
            await event_bus.respond_to_confirmation(cid, approved=True)

    event_bus.on_async(auto_approve)

    call_count = 0

    async def mock_llm(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_streaming_response("", tool_calls_data=[{
                "id": "call_confirm",
                "function": {"name": "confirmation_tool", "arguments": json.dumps({"cmd": "deploy"})},
            }])
        else:
            return make_streaming_response("Tool ran successfully after approval.")

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=mock_llm):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_confirmation_tool_rejected_returns_error():
    """When confirmation is rejected, the tool should NOT execute and return an error ToolResult."""
    config = make_config()
    spec = make_spec(tools=["confirmation_tool"])
    sub_task = make_sub_task()
    from hydra.state_manager import StateManager
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(ConfirmationTool())

    event_bus = EventBus()
    agent = Agent(spec, sub_task, registry, sm, config, event_bus=event_bus)

    # Capture tool result messages fed back to LLM
    captured_tool_results: list[dict] = []

    async def auto_reject(event: HydraEvent):
        if event.type == EventType.CONFIRMATION_REQUIRED:
            cid = event.data["confirmation_id"]
            await event_bus.respond_to_confirmation(cid, approved=False)

    event_bus.on_async(auto_reject)

    call_count = 0

    async def mock_llm(**kwargs):
        nonlocal call_count
        call_count += 1
        msgs = kwargs.get("messages", [])
        for m in msgs:
            if m.get("role") == "tool":
                captured_tool_results.append(m)
        if call_count == 1:
            return make_streaming_response("", tool_calls_data=[{
                "id": "call_reject",
                "function": {"name": "confirmation_tool", "arguments": json.dumps({"cmd": "drop_table"})},
            }])
        else:
            return make_streaming_response("The tool was rejected, so I cannot complete the action.")

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=mock_llm):
        output = await agent.execute()

    # Agent completes (LLM gracefully responds after rejection)
    assert output.status == AgentStatus.COMPLETED

    # Check that the tool result fed back to LLM indicates rejection
    assert any("rejected" in json.loads(m["content"]).get("error", "") for m in captured_tool_results)


@pytest.mark.asyncio
async def test_confirmation_timeout_treated_as_rejected():
    """When confirmation never comes, the timeout should treat it as rejected."""
    # Use a very short timeout — HydraConfig.per_agent_timeout_seconds must be int
    config = HydraConfig(api_key="test-key", per_agent_timeout_seconds=1)
    spec = make_spec(tools=["confirmation_tool"])
    sub_task = make_sub_task()
    from hydra.state_manager import StateManager
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(ConfirmationTool())

    event_bus = EventBus()
    agent = Agent(spec, sub_task, registry, sm, config, event_bus=event_bus)

    # Respond with a brief delay but AFTER the wait_for timeout by patching respond directly
    # Use a flag to ensure no response is ever sent
    captured: list[dict] = []
    call_count = 0

    async def mock_llm(**kwargs):
        nonlocal call_count
        call_count += 1
        msgs = kwargs.get("messages", [])
        for m in msgs:
            if m.get("role") == "tool":
                captured.append(m)
        if call_count == 1:
            return make_streaming_response("", tool_calls_data=[{
                "id": "call_timeout",
                "function": {"name": "confirmation_tool", "arguments": json.dumps({"cmd": "something"})},
            }])
        else:
            return make_streaming_response("Timed out, moving on.")

    # Patch asyncio.wait_for to immediately raise TimeoutError for confirmation calls
    original_wait_for = asyncio.wait_for
    timeout_calls = []

    async def fast_timeout_wait_for(coro, timeout=None, **kwargs):
        if timeout is not None and timeout <= 1:
            # Close the coroutine to avoid "never awaited" warning
            coro.close()
            raise asyncio.TimeoutError()
        return await original_wait_for(coro, timeout=timeout, **kwargs)

    with patch("hydra.agent.asyncio.wait_for", side_effect=fast_timeout_wait_for):
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=mock_llm):
            output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    # The tool result for the timed-out confirmation must be an error
    assert any("rejected" in json.loads(m["content"]).get("error", "") for m in captured)


@pytest.mark.asyncio
async def test_confirmation_tool_no_event_bus_runs_without_gate():
    """Without an event_bus, requires_confirmation tools should execute normally (backward compat)."""
    config = make_config()
    spec = make_spec(tools=["confirmation_tool"])
    sub_task = make_sub_task()
    from hydra.state_manager import StateManager
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(ConfirmationTool())

    # No event_bus — backward compatible path
    agent = Agent(spec, sub_task, registry, sm, config, event_bus=None)

    tool_call = MagicMock()
    tool_call.id = "call_no_bus"
    tool_call.function.name = "confirmation_tool"
    tool_call.function.arguments = json.dumps({"cmd": "test"})

    first_response = make_llm_response("", tool_calls=[tool_call])
    second_response = make_llm_response("Tool executed without event bus.")
    second_response.choices[0].message.tool_calls = None

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[first_response, second_response]):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_eventbus_request_confirmation_and_respond():
    """Unit test EventBus.request_confirmation + respond_to_confirmation roundtrip."""
    bus = EventBus()

    async def approve_immediately(event: HydraEvent):
        if event.type == EventType.CONFIRMATION_REQUIRED:
            cid = event.data["confirmation_id"]
            await bus.respond_to_confirmation(cid, approved=True)

    bus.on_async(approve_immediately)

    result = await bus.request_confirmation("cid-1", "some_tool", {"key": "val"})
    assert result is True


@pytest.mark.asyncio
async def test_eventbus_respond_to_confirmation_rejected():
    """EventBus.respond_to_confirmation with approved=False should return False."""
    bus = EventBus()

    async def reject_immediately(event: HydraEvent):
        if event.type == EventType.CONFIRMATION_REQUIRED:
            cid = event.data["confirmation_id"]
            await bus.respond_to_confirmation(cid, approved=False)

    bus.on_async(reject_immediately)

    result = await bus.request_confirmation("cid-2", "dangerous_tool", {})
    assert result is False


@pytest.mark.asyncio
async def test_confirmation_required_event_emitted():
    """CONFIRMATION_REQUIRED event must be emitted with correct fields."""
    bus = EventBus()
    received: list[HydraEvent] = []

    async def capture(event: HydraEvent):
        received.append(event)
        if event.type == EventType.CONFIRMATION_REQUIRED:
            await bus.respond_to_confirmation(event.data["confirmation_id"], approved=True)

    bus.on_async(capture)

    await bus.request_confirmation("cid-3", "my_tool", {"arg1": "val1"})

    conf_events = [e for e in received if e.type == EventType.CONFIRMATION_REQUIRED]
    assert len(conf_events) == 1
    assert conf_events[0].data["tool_name"] == "my_tool"
    assert conf_events[0].data["args"] == {"arg1": "val1"}
    assert conf_events[0].data["confirmation_id"] == "cid-3"


@pytest.mark.asyncio
async def test_rejected_confirmation_logged_to_audit():
    """When a confirmation is rejected, audit_logger.log_tool_execution should be called with success=False."""
    from hydra.state_manager import StateManager

    class ConfirmationTool(BaseTool):
        name = "confirm_tool"
        description = "Requires confirmation"
        parameters = {"type": "object", "properties": {}, "required": []}
        requires_confirmation = True

        async def execute(self) -> ToolResult:
            return ToolResult(success=True, data={"done": True})

    config = make_config()
    spec = make_spec(tools=["confirm_tool"])
    sub_task = make_sub_task()
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(ConfirmationTool())

    # Mock audit_logger
    audit_logger = MagicMock()

    bus = EventBus()

    # Auto-reject the confirmation
    async def reject_immediately(event: HydraEvent):
        if event.type == EventType.CONFIRMATION_REQUIRED:
            cid = event.data["confirmation_id"]
            await bus.respond_to_confirmation(cid, approved=False)

    bus.on_async(reject_immediately)

    first_response = make_streaming_response("", tool_calls_data=[{
        "id": "call_1",
        "function": {"name": "confirm_tool", "arguments": "{}"},
    }])
    second_response = make_streaming_response("Tool was rejected.")

    agent = Agent(spec, sub_task, registry, sm, config, event_bus=bus, audit_logger=audit_logger)

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[first_response, second_response]):
        await agent.execute()

    # audit_logger.log_tool_execution must have been called with result_success=False
    calls = audit_logger.log_tool_execution.call_args_list
    assert len(calls) >= 1
    rejection_calls = [c for c in calls if c.kwargs.get("result_success") is False or (c.args and c.args[2] is False)]
    assert len(rejection_calls) >= 1, "Expected at least one log_tool_execution call with success=False"
