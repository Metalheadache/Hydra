"""
Tests for Feature 2: Audit Logging.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.audit import AuditLogger
from hydra.config import HydraConfig
from hydra.models import AgentSpec, AgentStatus, SubTask
from hydra.state_manager import StateManager
from hydra.tool_registry import ToolRegistry


# ── AuditLogger unit tests ─────────────────────────────────────────────────────

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

        from hydra.models import AgentOutput
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
    from hydra.models import AgentOutput
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
    from hydra.agent import Agent

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
    from hydra.agent import Agent
    from hydra.models import ToolResult
    from hydra.tools.base import BaseTool

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
