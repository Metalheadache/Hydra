"""
Tests for PostBrain — quality gate, synthesis.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_agents.config import HydraConfig
from hydra_agents.models import AgentOutput, AgentSpec, AgentStatus, Priority, SubTask, TaskPlan
from hydra_agents.post_brain import PostBrain
from hydra_agents.state_manager import StateManager


def make_config() -> HydraConfig:
    return HydraConfig(api_key="test-key", min_quality_score=5.0)


def make_plan(sub_tasks: list[SubTask], agent_specs: list[AgentSpec] | None = None) -> TaskPlan:
    return TaskPlan(
        original_task="Test task for post-brain",
        sub_tasks=sub_tasks,
        agent_specs=agent_specs or [],
        execution_groups=[[st.id for st in sub_tasks]],
    )


def make_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_quality_gate_passes_all_completed():
    """Quality gate should pass when all tasks complete successfully."""
    config = make_config()
    sm = StateManager()

    st = SubTask(id="st_1", description="Task 1", expected_output="Result 1")
    plan = make_plan([st])

    await sm.write_output(
        "st_1",
        AgentOutput(agent_id="a1", sub_task_id="st_1", status=AgentStatus.COMPLETED, output="Great result"),
    )

    pb = PostBrain(config, sm, plan)
    mock_resp = make_llm_response("Synthesized final output.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await pb.synthesize()

    assert result["output"] == "Synthesized final output."
    # No critical failures → no warnings
    assert not any("CRITICAL" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_quality_gate_warns_on_failed_critical():
    """Quality gate must warn when a CRITICAL sub-task fails."""
    config = make_config()
    sm = StateManager()

    st = SubTask(
        id="st_critical",
        description="Critical task",
        expected_output="Must succeed",
        priority=Priority.CRITICAL,
    )
    plan = make_plan([st])

    await sm.write_output(
        "st_critical",
        AgentOutput(
            agent_id="a1",
            sub_task_id="st_critical",
            status=AgentStatus.FAILED,
            error="Something went wrong",
        ),
    )

    pb = PostBrain(config, sm, plan)
    mock_resp = make_llm_response("Best effort synthesis.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await pb.synthesize()

    # Should have a warning about the critical failure
    assert any("CRITICAL" in w or "critical" in w.lower() for w in result["warnings"])


@pytest.mark.asyncio
async def test_quality_gate_warns_schema_violation():
    """Quality gate must warn when output doesn't match declared schema."""
    config = make_config()
    sm = StateManager()

    schema = {
        "type": "object",
        "properties": {"score": {"type": "number"}},
        "required": ["score"],
    }
    st = SubTask(
        id="st_schema",
        description="Schema task",
        expected_output="A JSON with score",
        output_schema=schema,
    )
    plan = make_plan([st])

    # Output is a string, not matching the schema
    await sm.write_output(
        "st_schema",
        AgentOutput(
            agent_id="a1",
            sub_task_id="st_schema",
            status=AgentStatus.COMPLETED,
            output="this is not matching the schema",
        ),
    )

    pb = PostBrain(config, sm, plan)
    mock_resp = make_llm_response("Synthesized.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await pb.synthesize()

    assert any("schema" in w.lower() or "validation" in w.lower() for w in result["warnings"])


@pytest.mark.asyncio
async def test_synthesis_includes_all_outputs():
    """The LLM synthesis call should receive all agent outputs."""
    config = make_config()
    sm = StateManager()

    st1 = SubTask(id="st_1", description="Task 1", expected_output="R1")
    st2 = SubTask(id="st_2", description="Task 2", expected_output="R2")
    spec1 = AgentSpec(
        sub_task_id="st_1", role="Agent One", goal="g", backstory="b", tools_needed=[]
    )
    spec2 = AgentSpec(
        sub_task_id="st_2", role="Agent Two", goal="g", backstory="b", tools_needed=[]
    )
    plan = make_plan([st1, st2], [spec1, spec2])

    await sm.write_output("st_1", AgentOutput(agent_id="a1", sub_task_id="st_1", status=AgentStatus.COMPLETED, output="Output from agent one"))
    await sm.write_output("st_2", AgentOutput(agent_id="a2", sub_task_id="st_2", status=AgentStatus.COMPLETED, output="Output from agent two"))

    captured_content = []

    async def mock_completion(**kwargs):
        for msg in kwargs.get("messages", []):
            captured_content.append(msg.get("content", ""))
        return make_llm_response("Final synthesis.")

    pb = PostBrain(config, sm, plan)
    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=mock_completion):
        result = await pb.synthesize()

    full_content = " ".join(captured_content)
    assert "Output from agent one" in full_content
    assert "Output from agent two" in full_content


@pytest.mark.asyncio
async def test_synthesis_llm_failure_returns_fallback():
    """If the synthesis LLM call fails, return a fallback with the raw outputs."""
    config = make_config()
    sm = StateManager()

    st = SubTask(id="st_1", description="Task 1", expected_output="R1")
    plan = make_plan([st])
    await sm.write_output("st_1", AgentOutput(agent_id="a1", sub_task_id="st_1", status=AgentStatus.COMPLETED, output="raw output"))

    pb = PostBrain(config, sm, plan)

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("LLM down")):
        result = await pb.synthesize()

    # Should not raise; should return fallback
    assert "output" in result
    assert result["output"] != ""


@pytest.mark.asyncio
async def test_execution_summary_in_result():
    """Result dict must include execution summary and files metadata."""
    config = make_config()
    sm = StateManager()

    st = SubTask(id="st_1", description="Task", expected_output="R")
    plan = make_plan([st])
    await sm.write_output("st_1", AgentOutput(agent_id="a1", sub_task_id="st_1", status=AgentStatus.COMPLETED, output="ok", tokens_used=250, execution_time_ms=1200))

    pb = PostBrain(config, sm, plan)
    mock_resp = make_llm_response("Done.")

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        result = await pb.synthesize()

    assert "execution_summary" in result
    assert result["execution_summary"]["total_tokens_used"] == 250
    assert "files_generated" in result
    assert "per_agent_quality" in result
