"""
Tests for StateManager — concurrent writes, context injection, truncation.
"""

import asyncio

import pytest

from hydra.models import AgentOutput, AgentStatus
from hydra.state_manager import StateManager, _TRUNCATE_CHAR_LIMIT


@pytest.mark.asyncio
async def test_write_and_read_output():
    sm = StateManager()
    output = AgentOutput(
        agent_id="agent_1",
        sub_task_id="st_1",
        status=AgentStatus.COMPLETED,
        output="Hello world",
        tokens_used=100,
    )
    await sm.write_output("st_1", output)
    retrieved = await sm.get_output("st_1")
    assert retrieved is not None
    assert retrieved.output == "Hello world"
    assert retrieved.tokens_used == 100


@pytest.mark.asyncio
async def test_concurrent_writes():
    """Concurrent writes from multiple coroutines should not corrupt state."""
    sm = StateManager()

    async def write_output(n: int):
        output = AgentOutput(
            agent_id=f"agent_{n}",
            sub_task_id=f"st_{n}",
            status=AgentStatus.COMPLETED,
            output=f"Result {n}",
        )
        await sm.write_output(f"st_{n}", output)

    await asyncio.gather(*[write_output(i) for i in range(20)])
    all_outputs = await sm.get_all_outputs()
    assert len(all_outputs) == 20
    for i in range(20):
        assert f"st_{i}" in all_outputs
        assert all_outputs[f"st_{i}"].output == f"Result {i}"


@pytest.mark.asyncio
async def test_upstream_context_basic():
    sm = StateManager()
    sm.register_role("st_1", "Research Agent")
    output = AgentOutput(
        agent_id="agent_1",
        sub_task_id="st_1",
        status=AgentStatus.COMPLETED,
        output="This is the research result.",
    )
    await sm.write_output("st_1", output)

    context = await sm.get_upstream_context("st_2", ["st_1"])
    assert "Research Agent" in context
    assert "This is the research result." in context


@pytest.mark.asyncio
async def test_upstream_context_missing_dep():
    """If a dependency output doesn't exist yet, skip it gracefully."""
    sm = StateManager()
    context = await sm.get_upstream_context("st_2", ["st_nonexistent"])
    assert context == ""


@pytest.mark.asyncio
async def test_upstream_context_truncation():
    """Long outputs should be truncated."""
    sm = StateManager()
    sm.register_role("st_1", "Big Agent")
    long_output = "x" * (_TRUNCATE_CHAR_LIMIT + 500)
    output = AgentOutput(
        agent_id="agent_1",
        sub_task_id="st_1",
        status=AgentStatus.COMPLETED,
        output=long_output,
    )
    await sm.write_output("st_1", output)
    context = await sm.get_upstream_context("st_2", ["st_1"])
    assert "truncated" in context.lower()
    # Should not include the full content
    assert len(context) < len(long_output)


@pytest.mark.asyncio
async def test_upstream_context_failed_dep():
    """Failed upstream outputs should not be included in context."""
    sm = StateManager()
    sm.register_role("st_1", "Failed Agent")
    output = AgentOutput(
        agent_id="agent_1",
        sub_task_id="st_1",
        status=AgentStatus.FAILED,
        error="API error",
    )
    await sm.write_output("st_1", output)
    context = await sm.get_upstream_context("st_2", ["st_1"])
    assert context == ""


@pytest.mark.asyncio
async def test_shared_context():
    sm = StateManager()
    await sm.write_shared("my_key", {"value": 42})
    retrieved = await sm.read_shared("my_key")
    assert retrieved == {"value": 42}

    missing = await sm.read_shared("nonexistent")
    assert missing is None


@pytest.mark.asyncio
async def test_no_dependencies_returns_empty():
    sm = StateManager()
    context = await sm.get_upstream_context("st_1", [])
    assert context == ""


@pytest.mark.asyncio
async def test_execution_summary():
    sm = StateManager()
    for i in range(3):
        await sm.write_output(
            f"st_{i}",
            AgentOutput(
                agent_id=f"agent_{i}",
                sub_task_id=f"st_{i}",
                status=AgentStatus.COMPLETED,
                tokens_used=100,
                execution_time_ms=500,
            ),
        )
    await sm.write_output(
        "st_fail",
        AgentOutput(
            agent_id="agent_fail",
            sub_task_id="st_fail",
            status=AgentStatus.FAILED,
            error="oops",
        ),
    )

    summary = await sm.get_execution_summary()
    assert summary["total_agents"] == 4
    assert summary["completed"] == 3
    assert summary["failed"] == 1
    assert summary["total_tokens_used"] == 300
