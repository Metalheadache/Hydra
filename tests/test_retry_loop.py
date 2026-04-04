"""
Tests for the quality retry loop in Hydra._run_pipeline.

These tests verify that:
1. agents_needing_retry triggers a re-execution and re-synthesis
2. the retry is capped at 1 cycle (no infinite loops)
3. retry_metadata is correctly set in both retry and no-retry paths
4. when no agents need retry, retry_metadata reflects that
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_agents import Hydra
from hydra_agents.config import HydraConfig
from hydra_agents.models import AgentOutput, AgentSpec, AgentStatus, SubTask, TaskPlan
from hydra_agents.state_manager import StateManager


def make_config(**kwargs) -> HydraConfig:
    defaults = {
        "api_key": "test-key",
        "min_quality_score": 5.0,
        "retry_backoff_base": 0.0,
        "total_task_timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return HydraConfig(**defaults)


def make_plan(sub_task_ids: list[str]) -> TaskPlan:
    sub_tasks = [
        SubTask(
            id=tid,
            description=f"Task {tid}",
            expected_output=f"Output {tid}",
            retry_allowed=True,
            max_retries=1,
        )
        for tid in sub_task_ids
    ]
    agent_specs = [
        AgentSpec(sub_task_id=tid, role=f"Role {tid}", goal="g", backstory="b", tools_needed=[])
        for tid in sub_task_ids
    ]
    return TaskPlan(
        original_task="Test retry task",
        sub_tasks=sub_tasks,
        agent_specs=agent_specs,
        execution_groups=[sub_task_ids],
    )


def _synth_result(agents_needing_retry: list[str], output: str = "Synthesis") -> dict:
    return {
        "output": output,
        "warnings": [],
        "execution_summary": {},
        "files_generated": [],
        "per_agent_quality": {},
        "agents_needing_retry": agents_needing_retry,
    }


@pytest.mark.asyncio
async def test_no_retry_when_quality_ok():
    """When all agents pass quality, retry_metadata should show no retry was performed."""
    config = make_config()
    hydra = Hydra(config=config)
    plan = make_plan(["st_1"])

    with (
        patch("hydra_agents.brain.Brain.plan", new_callable=AsyncMock, return_value=plan),
        patch("hydra_agents.agent_factory.AgentFactory.create_agents", return_value={}),
        patch("hydra_agents.execution_engine.ExecutionEngine.execute", new_callable=AsyncMock),
        patch(
            "hydra_agents.post_brain.PostBrain.synthesize",
            new_callable=AsyncMock,
            return_value=_synth_result(agents_needing_retry=[]),
        ),
    ):
        result = await hydra._run_pipeline("Test task")

    assert result["retry_metadata"]["retry_performed"] is False
    assert result["retry_metadata"]["retried_agents"] == []


@pytest.mark.asyncio
async def test_retry_triggered_when_quality_low():
    """
    When an agent scores below min_quality_score, the retry loop should:
    1. Re-execute the flagged agent via ExecutionEngine._execute_with_retry
    2. Re-synthesize (PostBrain.synthesize called a second time)
    3. Set retry_metadata.retry_performed = True
    4. List the retried agent in retry_metadata.retried_agents
    """
    config = make_config(min_quality_score=7.0)
    hydra = Hydra(config=config)
    plan = make_plan(["st_low"])

    synthesize_call_count = {"n": 0}

    async def mock_synthesize():
        synthesize_call_count["n"] += 1
        if synthesize_call_count["n"] == 1:
            return _synth_result(agents_needing_retry=["st_low"], output="Initial synthesis")
        return _synth_result(agents_needing_retry=[], output="Improved synthesis")

    mock_execute_with_retry = AsyncMock()

    with (
        patch("hydra_agents.brain.Brain.plan", new_callable=AsyncMock, return_value=plan),
        patch("hydra_agents.agent_factory.AgentFactory.create_agents", return_value={}),
        patch("hydra_agents.execution_engine.ExecutionEngine.execute", new_callable=AsyncMock),
        patch("hydra_agents.execution_engine.ExecutionEngine._execute_with_retry", mock_execute_with_retry),
        patch("hydra_agents.post_brain.PostBrain.synthesize", side_effect=mock_synthesize),
    ):
        result = await hydra._run_pipeline("Test retry task")

    # Retry metadata
    assert result["retry_metadata"]["retry_performed"] is True
    assert "st_low" in result["retry_metadata"]["retried_agents"]

    # synthesize should have been called exactly twice
    assert synthesize_call_count["n"] == 2, (
        f"Expected 2 synthesize calls, got {synthesize_call_count['n']}"
    )

    # _execute_with_retry should have been called once with the flagged sub_task_id
    mock_execute_with_retry.assert_called_once_with("st_low")


@pytest.mark.asyncio
async def test_retry_is_single_cycle_only():
    """
    Even if the second synthesize still returns agents_needing_retry,
    we must NOT perform a third execution cycle. Retry is capped at 1.
    """
    config = make_config(min_quality_score=7.0)
    hydra = Hydra(config=config)
    plan = make_plan(["st_bad"])

    synthesize_call_count = {"n": 0}

    async def always_needs_retry():
        synthesize_call_count["n"] += 1
        return _synth_result(
            agents_needing_retry=["st_bad"],
            output=f"Synthesis {synthesize_call_count['n']}",
        )

    mock_execute_with_retry = AsyncMock()

    with (
        patch("hydra_agents.brain.Brain.plan", new_callable=AsyncMock, return_value=plan),
        patch("hydra_agents.agent_factory.AgentFactory.create_agents", return_value={}),
        patch("hydra_agents.execution_engine.ExecutionEngine.execute", new_callable=AsyncMock),
        patch("hydra_agents.execution_engine.ExecutionEngine._execute_with_retry", mock_execute_with_retry),
        patch("hydra_agents.post_brain.PostBrain.synthesize", side_effect=always_needs_retry),
    ):
        result = await hydra._run_pipeline("Test single cycle")

    # Synthesize should have been called exactly 2 times (initial + post-retry),
    # NOT 3 or more even though the second result still flagged agents for retry.
    assert synthesize_call_count["n"] == 2, (
        f"Expected 2 synthesize calls, got {synthesize_call_count['n']}"
    )

    # _execute_with_retry should have been called exactly once
    assert mock_execute_with_retry.call_count == 1, (
        f"Expected 1 retry execution, got {mock_execute_with_retry.call_count}"
    )


@pytest.mark.asyncio
async def test_retry_metadata_always_present():
    """
    retry_metadata must always be present in the result dict, even when no retry occurs.
    """
    config = make_config()
    hydra = Hydra(config=config)
    plan = make_plan(["st_1"])

    with (
        patch("hydra_agents.brain.Brain.plan", new_callable=AsyncMock, return_value=plan),
        patch("hydra_agents.agent_factory.AgentFactory.create_agents", return_value={}),
        patch("hydra_agents.execution_engine.ExecutionEngine.execute", new_callable=AsyncMock),
        patch(
            "hydra_agents.post_brain.PostBrain.synthesize",
            new_callable=AsyncMock,
            return_value=_synth_result(agents_needing_retry=[]),
        ),
    ):
        result = await hydra._run_pipeline("Test metadata presence")

    assert "retry_metadata" in result
    assert "retry_performed" in result["retry_metadata"]
    assert "retried_agents" in result["retry_metadata"]


@pytest.mark.asyncio
async def test_retry_with_multiple_agents():
    """Multiple agents flagged for retry should each be re-executed."""
    config = make_config(min_quality_score=7.0)
    hydra = Hydra(config=config)
    plan = make_plan(["st_a", "st_b", "st_c"])

    synthesize_call_count = {"n": 0}

    async def mock_synthesize():
        synthesize_call_count["n"] += 1
        if synthesize_call_count["n"] == 1:
            return _synth_result(agents_needing_retry=["st_a", "st_c"], output="Initial")
        return _synth_result(agents_needing_retry=[], output="Final")

    mock_execute_with_retry = AsyncMock()

    with (
        patch("hydra_agents.brain.Brain.plan", new_callable=AsyncMock, return_value=plan),
        patch("hydra_agents.agent_factory.AgentFactory.create_agents", return_value={}),
        patch("hydra_agents.execution_engine.ExecutionEngine.execute", new_callable=AsyncMock),
        patch("hydra_agents.execution_engine.ExecutionEngine._execute_with_retry", mock_execute_with_retry),
        patch("hydra_agents.post_brain.PostBrain.synthesize", side_effect=mock_synthesize),
    ):
        result = await hydra._run_pipeline("Multi-agent retry")

    assert result["retry_metadata"]["retry_performed"] is True
    retried = result["retry_metadata"]["retried_agents"]
    assert "st_a" in retried
    assert "st_c" in retried
    assert "st_b" not in retried

    # Both flagged agents should have been retried (in parallel via gather)
    called_with = {c.args[0] for c in mock_execute_with_retry.call_args_list}
    assert called_with == {"st_a", "st_c"}
    assert mock_execute_with_retry.call_count == 2
