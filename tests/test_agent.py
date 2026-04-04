"""
Tests for Agent — tool-use loop, context injection, timeout.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_agents.agent import Agent
from hydra_agents.config import HydraConfig
from hydra_agents.models import AgentSpec, AgentStatus, SubTask
from hydra_agents.state_manager import StateManager
from hydra_agents.tool_registry import ToolRegistry


def make_config() -> HydraConfig:
    return HydraConfig(api_key="test-key", per_agent_timeout_seconds=10)


def make_sub_task(task_id: str = "st_1", deps: list[str] | None = None) -> SubTask:
    return SubTask(
        id=task_id,
        description="Do something useful",
        expected_output="A useful result",
        dependencies=deps or [],
    )


def make_spec(sub_task_id: str = "st_1") -> AgentSpec:
    return AgentSpec(
        sub_task_id=sub_task_id,
        role="Test Analyst",
        goal="Complete the test task",
        backstory="Expert in testing",
        tools_needed=[],
    )


def make_llm_response(content: str, tool_calls=None):
    """Build a mock litellm response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = 500
    usage.prompt_tokens = 300
    usage.completion_tokens = 200
    resp.usage = usage
    return resp


@pytest.mark.asyncio
async def test_agent_basic_execution():
    """Agent returns text output when LLM produces no tool calls."""
    config = make_config()
    spec = make_spec()
    sub_task = make_sub_task()
    sm = StateManager()
    registry = ToolRegistry()

    agent = Agent(spec, sub_task, registry, sm, config)

    response = make_llm_response("Here is my analysis: All looks good.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=response):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    assert "All looks good" in str(output.output)
    assert output.tokens_used > 0


@pytest.mark.asyncio
async def test_agent_writes_to_state_manager():
    """Agent should write its output to the StateManager."""
    config = make_config()
    spec = make_spec("st_99")
    sub_task = make_sub_task("st_99")
    sm = StateManager()
    registry = ToolRegistry()

    agent = Agent(spec, sub_task, registry, sm, config)
    response = make_llm_response("Done.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=response):
        await agent.execute()

    stored = await sm.get_output("st_99")
    assert stored is not None
    assert stored.status == AgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_agent_tool_use_loop():
    """
    When the LLM requests a tool call, the agent should:
    1. Execute the tool.
    2. Feed the result back.
    3. Continue until the LLM produces a final text response.
    """
    from hydra_agents.models import ToolResult
    from hydra_agents.tools.base import BaseTool

    class EchoTool(BaseTool):
        name = "echo"
        description = "Echo the input"
        parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

        async def execute(self, text: str) -> ToolResult:
            return ToolResult(success=True, data={"echo": text})

    config = make_config()
    spec = make_spec()
    spec.tools_needed = ["echo"]
    sub_task = make_sub_task()
    sm = StateManager()
    registry = ToolRegistry()
    registry.register(EchoTool())

    agent = Agent(spec, sub_task, registry, sm, config)

    # First response: tool call
    tool_call = MagicMock()
    tool_call.id = "call_123"
    tool_call.function.name = "echo"
    tool_call.function.arguments = json.dumps({"text": "hello"})

    first_response = make_llm_response("", tool_calls=[tool_call])
    # Second response: final text
    second_response = make_llm_response("Echo confirmed: hello")
    second_response.choices[0].message.tool_calls = None

    with patch(
        "litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=[first_response, second_response],
    ):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    assert "Echo confirmed" in str(output.output)


@pytest.mark.asyncio
async def test_agent_with_upstream_context():
    """Agent should receive upstream context in its prompt."""
    config = make_config()
    spec = make_spec("st_2")
    sub_task = make_sub_task("st_2", deps=["st_1"])
    sm = StateManager()
    registry = ToolRegistry()

    sm.register_role("st_1", "Upstream Agent")
    from hydra_agents.models import AgentOutput, AgentStatus
    await sm.write_output(
        "st_1",
        AgentOutput(
            agent_id="a1",
            sub_task_id="st_1",
            status=AgentStatus.COMPLETED,
            output="Upstream result: data found.",
        ),
    )

    agent = Agent(spec, sub_task, registry, sm, config)

    captured_messages = []

    async def mock_completion(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return make_llm_response("Analysis complete based on upstream data.")

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion):
        output = await agent.execute()

    assert output.status == AgentStatus.COMPLETED
    # Check that upstream context was injected
    all_content = " ".join(str(m.get("content", "")) for m in captured_messages)
    assert "Upstream Agent" in all_content or "upstream" in all_content.lower()


@pytest.mark.asyncio
async def test_agent_handles_unknown_tool():
    """If LLM requests an unknown tool, the agent should return an error result and continue."""
    config = make_config()
    spec = make_spec()
    sub_task = make_sub_task()
    sm = StateManager()
    registry = ToolRegistry()  # No tools registered

    agent = Agent(spec, sub_task, registry, sm, config)

    # First response: requests unknown tool
    tool_call = MagicMock()
    tool_call.id = "call_xyz"
    tool_call.function.name = "nonexistent_tool"
    tool_call.function.arguments = "{}"

    first_response = make_llm_response("", tool_calls=[tool_call])
    second_response = make_llm_response("I couldn't use the tool, but here's my best answer.")
    second_response.choices[0].message.tool_calls = None

    with patch(
        "litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=[first_response, second_response],
    ):
        output = await agent.execute()

    # Agent should still complete (with the fallback answer)
    assert output.status == AgentStatus.COMPLETED
