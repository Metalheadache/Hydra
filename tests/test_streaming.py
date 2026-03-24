"""
Tests for streaming LLM tokens and the hydra.stream() pipeline.
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


# ── Agent token streaming tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_emits_agent_token_events():
    """Verify AGENT_TOKEN events are emitted for each streamed chunk."""
    from hydra.agent import Agent
    from hydra.config import HydraConfig
    from hydra.models import AgentSpec, AgentStatus, SubTask, Priority
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
    token_events: List[HydraEvent] = []

    def _collect_token(event: HydraEvent) -> None:
        if event.type == EventType.AGENT_TOKEN:
            token_events.append(event)

    event_bus.on(_collect_token)

    tool_registry = ToolRegistry()

    agent = Agent(
        agent_spec=spec,
        sub_task=sub_task,
        tool_registry=tool_registry,
        state_manager=state_manager,
        config=config,
        event_bus=event_bus,
    )

    # Mock litellm.acompletion to return a streaming response
    chunks = [
        _make_stream_chunk("Hello"),
        _make_stream_chunk(", "),
        _make_stream_chunk("world"),
        _make_stream_chunk("!"),
        _make_finish_chunk(usage_total=8),
    ]

    mock_stream = _async_chunks(*chunks)

    with patch("litellm.acompletion", AsyncMock(return_value=mock_stream)):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    assert len(token_events) == 4  # 4 content chunks
    tokens_text = "".join(e.data["token"] for e in token_events)
    assert tokens_text == "Hello, world!"


@pytest.mark.asyncio
async def test_agent_emits_tool_call_and_result_events():
    """AGENT_TOOL_CALL and AGENT_TOOL_RESULT events are emitted around tool calls."""
    from hydra.agent import Agent
    from hydra.config import HydraConfig
    from hydra.models import AgentSpec, AgentStatus, SubTask, Priority, ToolResult
    from hydra.tool_registry import ToolRegistry
    from hydra.tools.base import BaseTool

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")

    spec = AgentSpec(
        agent_id="tool_agent",
        sub_task_id="st_tool",
        role="Tool Agent",
        goal="Use a tool",
        backstory="Test",
        tools_needed=["mock_tool"],
    )
    sub_task = SubTask(
        id="st_tool",
        description="Use the mock tool",
        expected_output="Result",
        priority=Priority.NORMAL,
    )

    state_manager = MagicMock()
    state_manager.get_upstream_context = AsyncMock(return_value="")
    state_manager.write_output = AsyncMock()
    state_manager.write_shared = AsyncMock()

    # Create a mock tool
    class MockTool(BaseTool):
        name = "mock_tool"
        description = "A mock tool"
        parameters = {"type": "object", "properties": {}, "required": []}

        async def execute(self, **kwargs) -> ToolResult:
            return ToolResult(success=True, data="mock result")

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool())

    event_bus = EventBus()
    call_events: List[HydraEvent] = []
    result_events: List[HydraEvent] = []

    event_bus.on(lambda e: call_events.append(e) if e.type == EventType.AGENT_TOOL_CALL else None)
    event_bus.on(lambda e: result_events.append(e) if e.type == EventType.AGENT_TOOL_RESULT else None)

    agent = Agent(
        agent_spec=spec,
        sub_task=sub_task,
        tool_registry=tool_registry,
        state_manager=state_manager,
        config=config,
        event_bus=event_bus,
    )

    # First call returns a tool call, second call returns final text
    tool_call_delta = MagicMock()
    tool_call_delta.index = 0
    tool_call_delta.id = "tc_1"
    tool_call_delta.function = MagicMock()
    tool_call_delta.function.name = "mock_tool"
    tool_call_delta.function.arguments = "{}"

    tool_call_chunk = _make_stream_chunk(content=None)
    tool_call_chunk.choices[0].delta.tool_calls = [tool_call_delta]

    final_chunk = _make_stream_chunk(content="Done!")
    finish_chunk = _make_finish_chunk()

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _async_chunks(tool_call_chunk, finish_chunk)
        else:
            return _async_chunks(final_chunk, finish_chunk)

    with patch("litellm.acompletion", side_effect=mock_acompletion):
        output = await agent.execute()

    assert len(call_events) == 1
    assert call_events[0].data["tool"] == "mock_tool"
    assert len(result_events) == 1
    assert result_events[0].data["tool"] == "mock_tool"
    assert result_events[0].data["success"] is True


# ── hydra.stream() integration tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_hydra_stream_yields_pipeline_events():
    """hydra.stream() yields PIPELINE_START and PIPELINE_COMPLETE events."""
    from hydra import Hydra
    from hydra.config import HydraConfig
    from hydra.models import TaskPlan, SubTask, AgentSpec, Priority

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")
    hydra = Hydra(config=config)

    # Build a minimal mock plan
    plan = TaskPlan(
        original_task="Test task",
        sub_tasks=[
            SubTask(
                id="st_1",
                description="Do something",
                expected_output="output",
                priority=Priority.NORMAL,
            )
        ],
        agent_specs=[
            AgentSpec(
                agent_id="agent_1",
                sub_task_id="st_1",
                role="Worker",
                goal="Do something",
                backstory="Test agent",
                tools_needed=[],
            )
        ],
        execution_groups=[["st_1"]],
    )

    mock_agent_output_chunk = _make_stream_chunk("The answer is 42.")
    mock_finish_chunk = _make_finish_chunk(usage_total=20)

    quality_response = MagicMock()
    quality_response.choices = [MagicMock()]
    quality_response.choices[0].message.content = '{"score": 8.5, "feedback": "Good output"}'

    synthesis_chunks = [
        _make_stream_chunk("Final "),
        _make_stream_chunk("synthesis "),
        _make_stream_chunk("result."),
        _make_finish_chunk(),
    ]

    call_counter = [0]

    async def mock_acompletion(**kwargs):
        call_counter[0] += 1
        stream = kwargs.get("stream", False)
        if stream:
            # Could be agent or synthesis call — synthesis has "synthesis expert" in system prompt
            msgs_str = str(kwargs.get("messages", ""))
            if "synthesis expert" in msgs_str.lower() or "Synthesize all" in msgs_str:
                return _async_chunks(*synthesis_chunks)
            else:
                return _async_chunks(mock_agent_output_chunk, mock_finish_chunk)
        else:
            # Quality scoring (non-streaming)
            return quality_response

    # Bypass Brain by patching Brain.plan directly to return our mock plan
    with patch("hydra.brain.Brain.plan", AsyncMock(return_value=plan)), \
         patch("litellm.acompletion", side_effect=mock_acompletion):

        collected_events: List[HydraEvent] = []
        async for event in hydra.stream("Test task"):
            collected_events.append(event)

    event_types = [e.type for e in collected_events]

    assert EventType.PIPELINE_START in event_types
    assert EventType.PIPELINE_COMPLETE in event_types
    # PIPELINE_COMPLETE is last or second-to-last
    pipeline_complete_idx = event_types.index(EventType.PIPELINE_COMPLETE)
    assert pipeline_complete_idx == len(event_types) - 1


@pytest.mark.asyncio
async def test_hydra_run_backward_compat():
    """run() still works and returns a dict (backward compatibility)."""
    from hydra import Hydra
    from hydra.config import HydraConfig
    from hydra.models import TaskPlan, SubTask, AgentSpec, Priority

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")
    hydra = Hydra(config=config)

    plan = TaskPlan(
        original_task="Simple test",
        sub_tasks=[
            SubTask(
                id="st_1",
                description="Simple sub-task",
                expected_output="output",
                priority=Priority.NORMAL,
            )
        ],
        agent_specs=[
            AgentSpec(
                agent_id="agent_1",
                sub_task_id="st_1",
                role="Worker",
                goal="Do something",
                backstory="Test agent",
                tools_needed=[],
            )
        ],
        execution_groups=[["st_1"]],
    )

    agent_chunks = [_make_stream_chunk("Result text."), _make_finish_chunk()]
    synthesis_chunks = [_make_stream_chunk("Synthesized result."), _make_finish_chunk()]

    quality_response = MagicMock()
    quality_response.choices = [MagicMock()]
    quality_response.choices[0].message.content = '{"score": 9.0, "feedback": "Excellent"}'

    async def mock_acompletion(**kwargs):
        stream = kwargs.get("stream", False)
        if stream:
            msgs = str(kwargs.get("messages", ""))
            if "synthesis expert" in msgs.lower() or "Synthesize all" in msgs:
                return _async_chunks(*synthesis_chunks)
            return _async_chunks(*agent_chunks)
        else:
            return quality_response

    with patch("hydra.brain.Brain.plan", AsyncMock(return_value=plan)), \
         patch("litellm.acompletion", side_effect=mock_acompletion):

        result = await hydra.run("Simple test")

    # run() must return a dict with the expected keys
    assert isinstance(result, dict)
    assert "output" in result
    assert "warnings" in result
    assert "execution_summary" in result
    assert "files_generated" in result
    assert "per_agent_quality" in result


@pytest.mark.asyncio
async def test_hydra_stream_yields_synthesis_tokens():
    """SYNTHESIS_TOKEN events appear in the stream."""
    from hydra import Hydra
    from hydra.config import HydraConfig
    from hydra.models import TaskPlan, SubTask, AgentSpec, Priority

    config = HydraConfig(api_key="test-key", default_model="openai/gpt-4o-mini")
    hydra = Hydra(config=config)

    plan = TaskPlan(
        original_task="Token test",
        sub_tasks=[
            SubTask(
                id="st_1",
                description="Sub task",
                expected_output="output",
                priority=Priority.NORMAL,
            )
        ],
        agent_specs=[
            AgentSpec(
                agent_id="agent_1",
                sub_task_id="st_1",
                role="Worker",
                goal="Do something",
                backstory="Test",
                tools_needed=[],
            )
        ],
        execution_groups=[["st_1"]],
    )

    agent_chunks = [_make_stream_chunk("Agent output."), _make_finish_chunk()]
    synthesis_chunks = [
        _make_stream_chunk("Synth "),
        _make_stream_chunk("token "),
        _make_stream_chunk("test."),
        _make_finish_chunk(),
    ]

    quality_response = MagicMock()
    quality_response.choices = [MagicMock()]
    quality_response.choices[0].message.content = '{"score": 8.0, "feedback": "Good"}'

    async def mock_acompletion(**kwargs):
        stream = kwargs.get("stream", False)
        if stream:
            msgs = str(kwargs.get("messages", ""))
            if "synthesis expert" in msgs.lower() or "Synthesize all" in msgs:
                return _async_chunks(*synthesis_chunks)
            return _async_chunks(*agent_chunks)
        return quality_response

    with patch("hydra.brain.Brain.plan", AsyncMock(return_value=plan)), \
         patch("litellm.acompletion", side_effect=mock_acompletion):

        synthesis_token_events = []
        async for event in hydra.stream("Token test"):
            if event.type == EventType.SYNTHESIS_TOKEN:
                synthesis_token_events.append(event)

    assert len(synthesis_token_events) == 3
    assembled = "".join(e.data["token"] for e in synthesis_token_events)
    assert assembled == "Synth token test."
