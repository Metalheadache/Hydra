"""
Tests for ExecutionEngine — parallel execution, retries, failures.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from hydra.config import HydraConfig
from hydra.execution_engine import ExecutionEngine
from hydra.models import AgentOutput, AgentSpec, AgentStatus, SubTask, TaskPlan
from hydra.state_manager import StateManager


def make_config(**kwargs) -> HydraConfig:
    defaults = {
        "api_key": "test-key",
        "max_concurrent_agents": 5,
        "per_agent_timeout_seconds": 10,
        "retry_backoff_base": 0.01,  # Fast retries in tests
        "total_token_budget": 1_000_000,
    }
    defaults.update(kwargs)
    return HydraConfig(**defaults)


def make_plan(groups: list[list[str]], sub_tasks: list[SubTask], agent_specs: list[AgentSpec]) -> TaskPlan:
    return TaskPlan(
        original_task="Test task",
        sub_tasks=sub_tasks,
        agent_specs=agent_specs,
        execution_groups=groups,
    )


def make_sub_task(tid: str, deps: list[str] | None = None, max_retries: int = 2) -> SubTask:
    return SubTask(
        id=tid,
        description="Test sub-task",
        expected_output="Test output",
        dependencies=deps or [],
        max_retries=max_retries,
    )


def make_mock_agent(sub_task_id: str, status: AgentStatus = AgentStatus.COMPLETED, output: str = "done", delay: float = 0.0, state_manager: StateManager | None = None) -> MagicMock:
    """Create a mock Agent that returns a predetermined output.

    Mirrors real Agent.execute() behaviour by writing to state_manager when provided.
    """
    agent = MagicMock()
    spec = MagicMock()
    spec.agent_id = f"agent_{sub_task_id}"
    spec.sub_task_id = sub_task_id
    agent.agent_spec = spec

    sub_task = make_sub_task(sub_task_id)
    agent.sub_task = sub_task

    async def execute(extra_context: str = ""):
        if delay:
            await asyncio.sleep(delay)
        result = AgentOutput(
            agent_id=spec.agent_id,
            sub_task_id=sub_task_id,
            status=status,
            output=output,
            tokens_used=100,
        )
        # Real Agent.execute() always writes to state — mock should too
        if state_manager is not None:
            await state_manager.write_output(sub_task_id, result)
        return result

    agent.execute = execute
    return agent


@pytest.mark.asyncio
async def test_sequential_groups_execute_in_order():
    """Groups must execute sequentially — group 2 should not start before group 1 finishes."""
    config = make_config()
    sm = StateManager()

    execution_order: list[str] = []

    async def make_ordered_execute(tid: str, delay: float = 0.0):
        async def execute(extra_context: str = ""):
            await asyncio.sleep(delay)
            execution_order.append(tid)
            return AgentOutput(
                agent_id=f"agent_{tid}",
                sub_task_id=tid,
                status=AgentStatus.COMPLETED,
                output="done",
                tokens_used=10,
            )
        return execute

    agent_a = MagicMock()
    agent_a.agent_spec = MagicMock(agent_id="agent_a", sub_task_id="st_a")
    agent_a.sub_task = make_sub_task("st_a")
    agent_a.execute = await make_ordered_execute("st_a", delay=0.05)

    agent_b = MagicMock()
    agent_b.agent_spec = MagicMock(agent_id="agent_b", sub_task_id="st_b")
    agent_b.sub_task = make_sub_task("st_b")
    agent_b.execute = await make_ordered_execute("st_b")

    agents = {"st_a": agent_a, "st_b": agent_b}
    plan = make_plan(
        groups=[["st_a"], ["st_b"]],
        sub_tasks=[make_sub_task("st_a"), make_sub_task("st_b")],
        agent_specs=[],
    )

    engine = ExecutionEngine(config, agents, sm, plan)
    await engine.execute()

    # st_a must complete before st_b starts
    assert execution_order == ["st_a", "st_b"]


@pytest.mark.asyncio
async def test_parallel_group_runs_concurrently():
    """Agents in the same group should run concurrently, not sequentially."""
    config = make_config()
    sm = StateManager()

    agents = {
        "st_a": make_mock_agent("st_a", delay=0.1),
        "st_b": make_mock_agent("st_b", delay=0.1),
        "st_c": make_mock_agent("st_c", delay=0.1),
    }
    plan = make_plan(
        groups=[["st_a", "st_b", "st_c"]],
        sub_tasks=[make_sub_task(tid) for tid in ["st_a", "st_b", "st_c"]],
        agent_specs=[],
    )

    engine = ExecutionEngine(config, agents, sm, plan)
    start = time.monotonic()
    await engine.execute()
    elapsed = time.monotonic() - start

    # If parallel: ~0.1s. If sequential: ~0.3s. Allow generous margin.
    assert elapsed < 0.25, f"Expected parallel execution (~0.1s) but took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_failed_agent_is_written_to_state():
    """A failed agent's output should be recorded in the StateManager."""
    config = make_config(retry_backoff_base=0.001)
    sm = StateManager()

    agent = make_mock_agent("st_fail", status=AgentStatus.FAILED, output=None, state_manager=sm)
    # Override execute to always fail (and write to state, like real Agent does)
    async def always_fail(extra_context: str = ""):
        result = AgentOutput(
            agent_id="agent_st_fail",
            sub_task_id="st_fail",
            status=AgentStatus.FAILED,
            error="Simulated failure",
        )
        await sm.write_output("st_fail", result)
        return result
    agent.execute = always_fail

    plan = make_plan(
        groups=[["st_fail"]],
        sub_tasks=[make_sub_task("st_fail", max_retries=1)],
        agent_specs=[],
    )
    agents = {"st_fail": agent}

    engine = ExecutionEngine(config, agents, sm, plan)
    await engine.execute()  # Should not raise

    result = await sm.get_output("st_fail")
    assert result is not None
    assert result.status == AgentStatus.FAILED


@pytest.mark.asyncio
async def test_successful_agent_output_stored():
    """A completed agent's output should be stored in state."""
    config = make_config()
    sm = StateManager()

    agents = {"st_ok": make_mock_agent("st_ok", output="success!", state_manager=sm)}
    plan = make_plan(
        groups=[["st_ok"]],
        sub_tasks=[make_sub_task("st_ok")],
        agent_specs=[],
    )

    engine = ExecutionEngine(config, agents, sm, plan)
    await engine.execute()

    result = await sm.get_output("st_ok")
    assert result is not None
    assert result.status == AgentStatus.COMPLETED
    assert result.output == "success!"


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """With max_concurrent_agents=2 and 4 agents, concurrency should be limited."""
    config = make_config(max_concurrent_agents=2)
    sm = StateManager()

    active_count = 0
    max_observed = 0

    async def controlled_execute(tid: str):
        async def execute(extra_context: str = ""):
            nonlocal active_count, max_observed
            active_count += 1
            max_observed = max(max_observed, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1
            return AgentOutput(
                agent_id=f"agent_{tid}",
                sub_task_id=tid,
                status=AgentStatus.COMPLETED,
                output="ok",
                tokens_used=10,
            )
        return execute

    agents = {}
    for tid in ["st_1", "st_2", "st_3", "st_4"]:
        a = MagicMock()
        a.agent_spec = MagicMock(agent_id=f"agent_{tid}", sub_task_id=tid)
        a.sub_task = make_sub_task(tid)
        a.execute = await controlled_execute(tid)
        agents[tid] = a

    plan = make_plan(
        groups=[["st_1", "st_2", "st_3", "st_4"]],
        sub_tasks=[make_sub_task(tid) for tid in ["st_1", "st_2", "st_3", "st_4"]],
        agent_specs=[],
    )

    engine = ExecutionEngine(config, agents, sm, plan)
    await engine.execute()

    # Should never exceed 2 concurrent agents
    assert max_observed <= 2, f"Semaphore not working: max concurrent was {max_observed}"
