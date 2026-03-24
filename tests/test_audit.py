"""
Tests for AuditLogger — file creation, JSON Lines format, and helper methods.
"""

import json
import tempfile
from pathlib import Path

import pytest

from hydra.audit import AuditLogger


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    """Return a fresh temporary directory for each test."""
    return str(tmp_path)


@pytest.fixture
def logger(tmp_dir):
    """Return an AuditLogger pointing at the tmp directory."""
    return AuditLogger(tmp_dir)


# ── Tests ─────────────────────────────────────────────────────────────────────

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
    from hydra.state_manager import StateManager

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
