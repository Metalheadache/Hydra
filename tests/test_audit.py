"""
Tests for AuditLogger — file creation, JSON Lines format, and helper methods.
Merged from test_audit.py and test_audit_logging.py.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_agents.audit import AuditLogger
from hydra_agents.config import HydraConfig
from hydra_agents.models import AgentSpec, AgentStatus, SubTask
from hydra_agents.state_manager import StateManager
from hydra_agents.tool_registry import ToolRegistry


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    """Return a fresh temporary directory for each test."""
    return str(tmp_path)


@pytest.fixture
def logger(tmp_dir):
    """Return an AuditLogger pointing at the tmp directory."""
    return AuditLogger(tmp_dir)


# ── AuditLogger unit tests (fixture-based) ───────────────────────────────────

def test_log_file_created_on_first_write(tmp_dir):
    """audit.log should not exist before the first log() call."""
    al = AuditLogger(tmp_dir)
    log_path = Path(tmp_dir) / "audit.log"
    assert not log_path.exists(), "File should not exist before first write"

    al.log("test_event", {"key": "value"})

    assert log_path.exists(), "File should be created after first write"


def test_entries_are_valid_json_lines(logger, tmp_dir):
    """Every line in audit.log should be valid JSON with required top-level fields."""
    logger.log("event_a", {"x": 1})
    logger.log("event_b", {"y": "hello"})
    logger.log("event_c", {"z": [1, 2, 3]})

    log_path = Path(tmp_dir) / "audit.log"
    lines = log_path.read_text().splitlines()
    assert len(lines) == 3

    for line in lines:
        entry = json.loads(line)  # raises if invalid JSON
        assert "timestamp" in entry
        assert "event_type" in entry


def test_log_llm_call_captures_model_and_tokens(logger, tmp_dir):
    """log_llm_call should persist model, tokens_in, and tokens_out at top level."""
    logger.log_llm_call(
        model="gpt-4o",
        tokens_in=150,
        tokens_out=300,
        duration_ms=420,
        agent_id="agent-1",
    )

    log_path = Path(tmp_dir) / "audit.log"
    entry = json.loads(log_path.read_text().strip())

    assert entry["event_type"] == "llm_call"
    assert entry["model"] == "gpt-4o"
    assert entry["tokens_in"] == 150
    assert entry["tokens_out"] == 300
    assert entry["duration_ms"] == 420
    assert entry["agent_id"] == "agent-1"


def test_log_tool_execution_captures_name_and_success(logger, tmp_dir):
    """log_tool_execution should persist tool_name and success flag at top level."""
    logger.log_tool_execution(
        tool_name="web_search",
        args={"query": "hydra"},
        result_success=True,
        duration_ms=88,
        agent_id="agent-2",
    )

    log_path = Path(tmp_dir) / "audit.log"
    entry = json.loads(log_path.read_text().strip())

    assert entry["event_type"] == "tool_execution"
    assert entry["tool_name"] == "web_search"
    assert entry["success"] is True
    assert entry["agent_id"] == "agent-2"


def test_log_state_mutation_captures_operation_and_key(logger, tmp_dir):
    """log_state_mutation should persist operation and key at top level."""
    logger.log_state_mutation(
        operation="write_output",
        key="st_42",
        agent_id="agent-3",
    )

    log_path = Path(tmp_dir) / "audit.log"
    entry = json.loads(log_path.read_text().strip())

    assert entry["event_type"] == "state_mutation"
    assert entry["operation"] == "write_output"
    assert entry["key"] == "st_42"


def test_log_quality_score(logger, tmp_dir):
    """log_quality_score should persist agent_id, sub_task_id, and score."""
    logger.log_quality_score(
        agent_id="agent-4",
        sub_task_id="st_99",
        score=8.5,
        feedback="Great output",
    )

    log_path = Path(tmp_dir) / "audit.log"
    entry = json.loads(log_path.read_text().strip())

    assert entry["event_type"] == "quality_score"
    assert entry["agent_id"] == "agent-4"
    assert entry["sub_task_id"] == "st_99"
    assert entry["score"] == 8.5
    assert entry["feedback"] == "Great output"


def test_no_crash_when_audit_logger_is_none():
    """Components that accept audit_logger=None should not crash."""
    from hydra_agents.state_manager import StateManager

    # StateManager with no audit_logger must still work normally
    sm = StateManager(audit_logger=None)
    import asyncio

    async def _run():
        await sm.write_shared("key", "value")
        result = await sm.read_shared("key")
        assert result == "value"

    asyncio.run(_run())


def test_multiple_log_entries_appended(logger, tmp_dir):
    """Each log() call should append a new line (not overwrite)."""
    for i in range(5):
        logger.log("tick", {"i": i})

    log_path = Path(tmp_dir) / "audit.log"
    lines = log_path.read_text().splitlines()
    assert len(lines) == 5

    for i, line in enumerate(lines):
        entry = json.loads(line)
        assert entry["i"] == i


def test_log_creates_parent_directories():
    """AuditLogger should create nested directories if they don't exist."""
    with tempfile.TemporaryDirectory() as base:
        nested_dir = str(Path(base) / "deep" / "nested" / "dir")
        al = AuditLogger(nested_dir)
        al.log("mkdir_test", {"ok": True})
        assert (Path(nested_dir) / "audit.log").exists()


# ── AuditLogger unit tests (self-contained, from test_audit_logging.py) ──────

def test_audit_log_file_created():
    """AuditLogger should create the log file on first write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        al.log("test_event", {"key": "value"})
        assert al.log_path.exists()


def test_audit_entries_are_valid_json_lines():
    """Each line in the log file must be valid JSON with required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        al.log("event_a", {"x": 1})
        al.log("event_b", {"y": "hello"})

        lines = al.log_path.read_text().splitlines()
        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "event_type" in entry


def test_audit_log_llm_call_captures_model_and_tokens():
    """log_llm_call should store model name and token counts (flat format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        al.log_llm_call(
            model="anthropic/claude-sonnet-4-6",
            tokens_in=500,
            tokens_out=200,
            duration_ms=1234,
            agent_id="agent_abc",
        )

        lines = al.log_path.read_text().splitlines()
        entry = json.loads(lines[0])
        assert entry["event_type"] == "llm_call"
        assert entry["model"] == "anthropic/claude-sonnet-4-6"
        assert entry["tokens_in"] == 500
        assert entry["tokens_out"] == 200
        assert entry["total_tokens"] == 700
        assert entry["duration_ms"] == 1234
        assert entry["agent_id"] == "agent_abc"


def test_audit_log_tool_execution_captures_name_and_success():
    """log_tool_execution should store tool name and success flag (flat format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        al.log_tool_execution(
            tool_name="web_search",
            args={"query": "hello"},
            result_success=True,
            duration_ms=50,
            agent_id="agent_xyz",
        )

        lines = al.log_path.read_text().splitlines()
        entry = json.loads(lines[0])
        assert entry["event_type"] == "tool_execution"
        assert entry["tool_name"] == "web_search"
        assert entry["success"] is True
        assert entry["agent_id"] == "agent_xyz"
        assert "query" in entry["arg_keys"]


def test_audit_log_state_mutation():
    """log_state_mutation should store operation and key (flat format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        al.log_state_mutation(operation="write_output", key="st_001", agent_id="agent_1")

        lines = al.log_path.read_text().splitlines()
        entry = json.loads(lines[0])
        assert entry["event_type"] == "state_mutation"
        assert entry["operation"] == "write_output"
        assert entry["key"] == "st_001"
        assert entry["agent_id"] == "agent_1"


def test_audit_multiple_entries_appended():
    """Each log() call appends a new line — old entries are preserved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        for i in range(5):
            al.log("iteration", {"i": i})

        lines = al.log_path.read_text().splitlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            entry = json.loads(line)
            assert entry["i"] == i


def test_audit_output_dir_created_automatically():
    """AuditLogger should create nested output directories if they don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_dir = os.path.join(tmpdir, "deep", "nested", "dir")
        al = AuditLogger(nested_dir)
        al.log("test", {})
        assert Path(nested_dir).exists()
        assert al.log_path.exists()


# ── Integration: StateManager with AuditLogger ────────────────────────────────

@pytest.mark.asyncio
async def test_state_manager_audit_write_output():
    """StateManager with audit_logger should log write_output operations (flat format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        sm = StateManager(audit_logger=al)

        from hydra_agents.models import AgentOutput
        output = AgentOutput(
            agent_id="a1",
            sub_task_id="st_1",
            status=AgentStatus.COMPLETED,
            output="result",
        )
        await sm.write_output("st_1", output)

        lines = al.log_path.read_text().splitlines()
        mutations = [json.loads(l) for l in lines if json.loads(l)["event_type"] == "state_mutation"]
        assert any(m["operation"] == "write_output" and m["key"] == "st_1" for m in mutations)


@pytest.mark.asyncio
async def test_state_manager_audit_write_shared():
    """StateManager with audit_logger should log write_shared operations (flat format)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        sm = StateManager(audit_logger=al)

        await sm.write_shared("my_key", {"data": 42})

        lines = al.log_path.read_text().splitlines()
        entries = [json.loads(l) for l in lines]
        mutations = [e for e in entries if e["event_type"] == "state_mutation"]
        assert any(m["operation"] == "write_shared" and m["key"] == "my_key" for m in mutations)


@pytest.mark.asyncio
async def test_state_manager_no_audit_logger_works_normally():
    """StateManager without audit_logger should work exactly as before."""
    sm = StateManager()  # No audit_logger — backward compatible
    from hydra_agents.models import AgentOutput
    output = AgentOutput(
        agent_id="a1",
        sub_task_id="st_1",
        status=AgentStatus.COMPLETED,
        output="result",
    )
    await sm.write_output("st_1", output)
    stored = await sm.get_output("st_1")
    assert stored is not None
    assert stored.status == AgentStatus.COMPLETED


# ── Integration: Agent with AuditLogger ───────────────────────────────────────

def make_llm_response(content: str, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.total_tokens = 300
    usage.prompt_tokens = 200
    usage.completion_tokens = 100
    resp.usage = usage
    return resp


@pytest.mark.asyncio
async def test_agent_logs_llm_call_to_audit():
    """Agent should log each LLM call to the audit logger."""
    from hydra_agents.agent import Agent

    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        config = HydraConfig(api_key="test-key", per_agent_timeout_seconds=10)
        spec = AgentSpec(
            sub_task_id="st_1",
            role="Tester",
            goal="Test",
            backstory="Expert",
            tools_needed=[],
        )
        sub_task = SubTask(id="st_1", description="Task", expected_output="Result")
        sm = StateManager()
        registry = ToolRegistry()

        agent = Agent(spec, sub_task, registry, sm, config, audit_logger=al)
        response = make_llm_response("Done.")

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=response):
            await agent.execute()

        lines = al.log_path.read_text().splitlines()
        llm_entries = [json.loads(l) for l in lines if json.loads(l)["event_type"] == "llm_call"]
        assert len(llm_entries) >= 1
        assert llm_entries[0]["model"] is not None


@pytest.mark.asyncio
async def test_agent_logs_tool_execution_to_audit():
    """Agent should log each tool execution to the audit logger."""
    from hydra_agents.agent import Agent
    from hydra_agents.models import ToolResult
    from hydra_agents.tools.base import BaseTool

    class SimpleTool(BaseTool):
        name = "simple_tool"
        description = "Simple test tool"
        parameters = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}

        async def execute(self, x: str = "") -> ToolResult:
            return ToolResult(success=True, data={"x": x})

    with tempfile.TemporaryDirectory() as tmpdir:
        al = AuditLogger(tmpdir)
        config = HydraConfig(api_key="test-key", per_agent_timeout_seconds=10)
        spec = AgentSpec(
            sub_task_id="st_1",
            role="Tester",
            goal="Test",
            backstory="Expert",
            tools_needed=["simple_tool"],
        )
        sub_task = SubTask(id="st_1", description="Task", expected_output="Result")
        sm = StateManager()
        registry = ToolRegistry()
        registry.register(SimpleTool())

        agent = Agent(spec, sub_task, registry, sm, config, audit_logger=al)

        import json as _json
        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.function.name = "simple_tool"
        tool_call.function.arguments = _json.dumps({"x": "test"})

        first_response = make_llm_response("", tool_calls=[tool_call])
        second_response = make_llm_response("Done.")
        second_response.choices[0].message.tool_calls = None

        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[first_response, second_response]):
            await agent.execute()

        lines = al.log_path.read_text().splitlines()
        tool_entries = [json.loads(l) for l in lines if json.loads(l)["event_type"] == "tool_execution"]
        assert len(tool_entries) >= 1
        assert tool_entries[0]["tool_name"] == "simple_tool"
        assert tool_entries[0]["success"] is True
