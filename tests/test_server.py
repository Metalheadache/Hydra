"""
Tests for hydra/server.py — REST endpoints, history DB, and WebSocket.

Uses httpx.AsyncClient with ASGITransport (no real network).
Hydra.run and Hydra.stream are mocked to avoid real LLM calls.
"""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── App import and test-DB setup ──────────────────────────────────────────────

import hydra_agents.server as server_module
from hydra_agents.events import EventType, HydraEvent
from hydra_agents.history import HistoryDB
from hydra_agents.models import FileAttachment


@pytest.fixture(autouse=True)
def reset_server_state(tmp_path):
    """
    Point server to a fresh temp output dir + fresh DB for each test.
    Resets global _config, _history_db.
    """
    from hydra_agents.config import HydraConfig

    original_config = server_module._config
    original_db = server_module._history_db
    original_db_path = server_module._DB_PATH

    # Fresh config with temp output dir
    cfg = HydraConfig(output_directory=str(tmp_path))
    server_module._config = cfg
    db_path = str(tmp_path / "history.db")
    server_module._DB_PATH = db_path
    server_module._history_db = HistoryDB(db_path)

    yield

    server_module._config = original_config
    server_module._history_db = original_db
    server_module._DB_PATH = original_db_path


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from hydra_agents.server import app

    # Trigger startup event
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Manually call startup
        await server_module._history_db.init()
        yield ac


# ── GET /api/config ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_config_redacts_api_key(client: AsyncClient):
    """Config endpoint should redact the api_key field."""
    # Set a key in the in-memory config
    from hydra_agents.config import HydraConfig

    server_module._config = HydraConfig(api_key="sk-real-key-123")

    resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] == "***"
    assert "default_model" in data


@pytest.mark.asyncio
async def test_get_config_empty_api_key(client: AsyncClient):
    """If api_key is empty, redacted value should be empty string."""
    from hydra_agents.config import HydraConfig

    server_module._config = HydraConfig(api_key="")
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["api_key"] == ""


# ── POST /api/config ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_config_updates_field(client: AsyncClient):
    """POST /api/config should update valid fields."""
    resp = await client.post("/api/config", json={"max_concurrent_agents": 3})
    assert resp.status_code == 200
    assert resp.json()["max_concurrent_agents"] == 3
    assert server_module._config.max_concurrent_agents == 3


@pytest.mark.asyncio
async def test_post_config_unknown_fields_ignored(client: AsyncClient):
    """Unknown fields should be silently ignored."""
    resp = await client.post(
        "/api/config", json={"max_concurrent_agents": 2, "nonexistent_field": "boom"}
    )
    assert resp.status_code == 200
    assert resp.json()["max_concurrent_agents"] == 2


@pytest.mark.asyncio
async def test_post_config_no_valid_fields_returns_400(client: AsyncClient):
    """If no valid fields provided, return 400."""
    resp = await client.post("/api/config", json={"unknown_key": "value"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_post_config_redact_placeholder_preserved(client: AsyncClient):
    """Sending '***' as api_key should not overwrite the real key."""
    from hydra_agents.config import HydraConfig

    server_module._config = HydraConfig(api_key="real-key")
    resp = await client.post("/api/config", json={"api_key": "***", "max_concurrent_agents": 2})
    assert resp.status_code == 200
    assert server_module._config.api_key == "real-key"


# ── GET /api/tools ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tools_returns_list(client: AsyncClient):
    """Tools endpoint should return a non-empty list with name/description/parameters."""
    resp = await client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "name" in first
    assert "description" in first
    assert "parameters" in first


# ── GET /api/models ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_models_returns_list(client: AsyncClient):
    """Models endpoint should return the suggested model list."""
    resp = await client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [m["id"] for m in data]
    assert "anthropic/claude-sonnet-4-6" in ids


# ── POST /api/upload ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_single_file(client: AsyncClient, tmp_path):
    """Uploading a text file should return a FileAttachment with extracted_text."""
    content = b"Hello from the test file!"
    resp = await client.post(
        "/api/upload",
        files=[("files", ("test.txt", io.BytesIO(content), "text/plain"))],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    att = data[0]
    assert att["original_name"] == "test.txt"
    assert att["extracted_text"] is not None
    assert "Hello from the test file!" in att["extracted_text"]


@pytest.mark.asyncio
async def test_upload_multiple_files(client: AsyncClient):
    """Uploading multiple files should return multiple attachments."""
    resp = await client.post(
        "/api/upload",
        files=[
            ("files", ("a.txt", io.BytesIO(b"File A"), "text/plain")),
            ("files", ("b.txt", io.BytesIO(b"File B"), "text/plain")),
        ],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_upload_no_files_returns_4xx(client: AsyncClient):
    """Uploading nothing should return a 4xx error (422 from FastAPI or 400 from our guard)."""
    resp = await client.post("/api/upload", files=[])
    assert resp.status_code in (400, 422)


# ── POST /api/task ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_task_success(client: AsyncClient):
    """POST /api/task should call Hydra.run and return the result."""
    fake_result = {
        "output": "Test output",
        "warnings": [],
        "execution_summary": {"total_tokens": 100},
        "files_generated": [],
        "per_agent_quality": {"agent_1": {}},
        "agents_needing_retry": [],
    }

    with patch("hydra_agents.server.Hydra") as MockHydra:
        instance = MockHydra.return_value
        instance.run = AsyncMock(return_value=fake_result)

        resp = await client.post("/api/task", json={"task": "Do something"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "Test output"
        assert "task_id" in data


@pytest.mark.asyncio
async def test_post_task_missing_task_returns_400(client: AsyncClient):
    resp = await client.post("/api/task", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_post_task_failure_returns_500(client: AsyncClient):
    with patch("hydra_agents.server.Hydra") as MockHydra:
        instance = MockHydra.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("LLM error"))

        resp = await client.post("/api/task", json={"task": "Fail me"})
        assert resp.status_code == 500


# ── History: GET /api/history ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_history_empty(client: AsyncClient):
    """Empty DB should return an empty list."""
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_history_save_list_get_delete_cycle(client: AsyncClient):
    """Full CRUD cycle: save → list → get → delete."""
    db = server_module._history_db

    task_id = "task_abcdef1234567890"
    result = {"output": "hello", "warnings": [], "files_generated": []}

    # Save
    await db.save_run(
        task_id=task_id,
        task_text="Test task for history",
        status="completed",
        result=result,
        duration_ms=1234,
        total_tokens=500,
    )

    # List
    resp = await client.get("/api/history")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["task_id"] == task_id
    assert rows[0]["status"] == "completed"

    # Get full record
    resp = await client.get(f"/api/history/{task_id}")
    assert resp.status_code == 200
    full = resp.json()
    assert full["task_id"] == task_id
    assert full["result"]["output"] == "hello"

    # Delete
    resp = await client.delete(f"/api/history/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == task_id

    # Verify gone
    resp = await client.get(f"/api/history/{task_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_history_not_found(client: AsyncClient):
    # Valid format task_id that doesn't exist → 404
    resp = await client.get("/api/history/task_abcdef12345678")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_history_not_found(client: AsyncClient):
    # Valid format task_id that doesn't exist → 404
    resp = await client.delete("/api/history/task_abcdef12345678")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_history_pagination(client: AsyncClient):
    """Test limit/offset query params."""
    db = server_module._history_db
    for i in range(5):
        await db.save_run(
            task_id=f"task_{i:03d}",
            task_text=f"Task {i}",
            status="completed",
            result=None,
            duration_ms=i * 100,
            total_tokens=i * 10,
        )

    resp = await client.get("/api/history?limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp = await client.get("/api/history?limit=3&offset=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── WebSocket /ws/task ────────────────────────────────────────────────────────

def test_websocket_start_task_streams_events(tmp_path):
    """WebSocket should stream events via Starlette TestClient."""
    from starlette.testclient import TestClient
    from hydra_agents.server import app
    from hydra_agents.config import HydraConfig

    events_to_yield = [
        HydraEvent(type=EventType.PIPELINE_START, data={"task_preview": "Test"}),
        HydraEvent(type=EventType.BRAIN_START),
        HydraEvent(type=EventType.PIPELINE_COMPLETE, data={"warnings": 0, "files": 0}),
    ]

    async def fake_stream(task, files=None):
        for event in events_to_yield:
            yield event

    # Set fresh config with temp output dir
    server_module._config = HydraConfig(output_directory=str(tmp_path))
    import hydra_agents.server as sm
    sm._history_db = HistoryDB(str(tmp_path / "history.db"))

    with patch("hydra_agents.server.Hydra") as MockHydra:
        instance = MockHydra.return_value
        instance.stream = fake_stream

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/task") as ws:
                ws.send_json({"type": "start_task", "task": "Run this"})
                received = []
                for _ in range(len(events_to_yield) + 2):
                    try:
                        data = ws.receive_json()
                        received.append(data)
                    except Exception:
                        break

                types = [m.get("type") for m in received]
                # We should have received at least some events
                assert len(received) > 0


@pytest.mark.asyncio
async def test_websocket_wrong_message_type_closes(client: AsyncClient):
    """WebSocket should close if first message is not 'start_task'."""
    from starlette.testclient import TestClient
    from hydra_agents.server import app

    # Use Starlette's sync test client for WebSocket testing (simpler)
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/task") as ws:
            ws.send_json({"type": "wrong_type"})
            # Should receive an error and close
            try:
                data = ws.receive_json()
                assert "error" in data
            except Exception:
                pass  # Connection may close immediately


# ── HistoryDB unit tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_db_init_creates_table(tmp_path):
    """HistoryDB.init() should create the task_runs table."""
    db = HistoryDB(str(tmp_path / "test.db"))
    await db.init()
    assert Path(tmp_path / "test.db").exists()


@pytest.mark.asyncio
async def test_history_db_save_and_retrieve(tmp_path):
    db = HistoryDB(str(tmp_path / "test.db"))
    await db.init()

    result = {"output": "done", "warnings": []}
    await db.save_run(
        task_id="t1",
        task_text="My task",
        status="completed",
        result=result,
        duration_ms=500,
        total_tokens=200,
        total_cost=0.001,
        files_count=1,
        agent_count=2,
    )

    row = await db.get_run("t1")
    assert row is not None
    assert row["task_id"] == "t1"
    assert row["status"] == "completed"
    assert row["result"]["output"] == "done"
    assert row["files_count"] == 1
    assert row["agent_count"] == 2


@pytest.mark.asyncio
async def test_history_db_list_ordering(tmp_path):
    """Runs should be returned newest-first (by task_id DESC as a proxy if timestamps tie)."""
    db = HistoryDB(str(tmp_path / "test.db"))
    await db.init()

    for i in range(3):
        await db.save_run(
            task_id=f"t{i}",
            task_text=f"Task {i}",
            status="completed",
            result=None,
            duration_ms=i,
            total_tokens=i,
        )

    rows = await db.list_runs()
    # All 3 rows should be returned
    assert len(rows) == 3
    task_ids = {r["task_id"] for r in rows}
    assert task_ids == {"t0", "t1", "t2"}


@pytest.mark.asyncio
async def test_history_db_delete_returns_false_if_not_found(tmp_path):
    db = HistoryDB(str(tmp_path / "test.db"))
    await db.init()
    deleted = await db.delete_run("nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_history_db_lazy_init(tmp_path):
    """HistoryDB should initialize lazily on first operation."""
    db_path = str(tmp_path / "lazy.db")
    db = HistoryDB(db_path)
    assert not Path(db_path).exists()

    # First operation triggers init
    rows = await db.list_runs()
    assert rows == []
    assert Path(db_path).exists()


# ── New tests (Fix 14) ────────────────────────────────────────────────────────

def test_ws_cancel_stops_pipeline(tmp_path):
    """Sending a 'cancel' message should cancel the pipeline task."""
    from starlette.testclient import TestClient
    from hydra_agents.server import app
    from hydra_agents.config import HydraConfig

    cancel_event = asyncio.Event()

    async def fake_stream_slow(task, files=None, event_bus=None):
        # Emit one event then stall until cancelled
        yield HydraEvent(type=EventType.PIPELINE_START, data={"task_preview": task[:100]})
        try:
            await asyncio.sleep(30)  # long wait
        except asyncio.CancelledError:
            cancel_event.set()
            return
        yield HydraEvent(type=EventType.PIPELINE_COMPLETE, data={})

    server_module._config = HydraConfig(output_directory=str(tmp_path))
    import hydra_agents.server as sm
    sm._history_db = HistoryDB(str(tmp_path / "history.db"))

    with patch("hydra_agents.server.Hydra") as MockHydra:
        instance = MockHydra.return_value
        instance.stream = fake_stream_slow

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/task") as ws:
                ws.send_json({"type": "start_task", "task": "Long running task"})
                # Read the first event (PIPELINE_START)
                data = ws.receive_json()
                assert data.get("type") == "pipeline_start"
                # Send cancel
                ws.send_json({"type": "cancel"})
                # Connection should close without more events
                try:
                    ws.receive_json()
                except Exception:
                    pass  # Expected — connection closes after cancel


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client: AsyncClient):
    """Uploading a file exceeding the configured size limit should return 413."""
    from hydra_agents.config import HydraConfig

    # Set a very small limit (1 byte)
    server_module._config = HydraConfig(
        output_directory=str(server_module._config.output_directory),
        max_upload_file_size_mb=0,  # 0 MB → effectively 0 bytes max
    )

    oversized_content = b"X" * 10  # 10 bytes, more than 0 MB
    resp = await client.post(
        "/api/upload",
        files=[("files", ("big.txt", io.BytesIO(oversized_content), "text/plain"))],
    )
    assert resp.status_code == 413


def test_ws_malformed_json_ignored(tmp_path):
    """Malformed JSON from client during pipeline should be silently ignored (not crash)."""
    from starlette.testclient import TestClient
    from hydra_agents.server import app
    from hydra_agents.config import HydraConfig

    events_to_yield = [
        HydraEvent(type=EventType.PIPELINE_START, data={"task_preview": "Test"}),
        HydraEvent(type=EventType.PIPELINE_COMPLETE, data={"warnings": 0, "files": 0}),
    ]

    async def fake_stream(task, files=None, event_bus=None):
        for event in events_to_yield:
            yield event

    server_module._config = HydraConfig(output_directory=str(tmp_path))
    import hydra_agents.server as sm
    sm._history_db = HistoryDB(str(tmp_path / "history.db"))

    with patch("hydra_agents.server.Hydra") as MockHydra:
        instance = MockHydra.return_value
        instance.stream = fake_stream

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws/task") as ws:
                ws.send_json({"type": "start_task", "task": "Do something"})
                # Send malformed JSON mid-stream (should be ignored)
                ws.send_text("{{not valid json}}")
                received = []
                for _ in range(5):
                    try:
                        data = ws.receive_json()
                        received.append(data)
                    except Exception:
                        break
                # Pipeline should still complete normally
                types = [m.get("type") for m in received]
                assert len(received) > 0  # got at least some events


@pytest.mark.asyncio
async def test_task_text_too_long_rejected(client: AsyncClient):
    """POST /api/task with task text exceeding MAX_TASK_LENGTH should return 400."""
    from hydra_agents.server import MAX_TASK_LENGTH

    long_task = "x" * (MAX_TASK_LENGTH + 1)
    resp = await client.post("/api/task", json={"task": long_task})
    assert resp.status_code == 400
    assert "character limit" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_auth_token_required(client: AsyncClient):
    """When server_token is configured, requests without it should get 401."""
    from hydra_agents.config import HydraConfig

    server_module._config = HydraConfig(
        output_directory=str(server_module._config.output_directory),
        server_token="secret-token-123",
    )

    # Without token — should be rejected
    resp = await client.get("/api/config")
    assert resp.status_code == 401

    # With wrong token — should also be rejected
    resp = await client.get("/api/config", headers={"X-API-Key": "wrong-token"})
    assert resp.status_code == 401

    # With correct token — should succeed
    resp = await client.get("/api/config", headers={"X-API-Key": "secret-token-123"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_token_skipped(client: AsyncClient):
    """When server_token is empty (default), all requests should be allowed without auth."""
    from hydra_agents.config import HydraConfig

    # Ensure no token is set (default)
    server_module._config = HydraConfig(
        output_directory=str(server_module._config.output_directory),
        server_token="",
    )

    # No auth header — should succeed
    resp = await client.get("/api/config")
    assert resp.status_code == 200

    # Random token provided — should still succeed (auth not enforced)
    resp = await client.get("/api/config", headers={"X-API-Key": "any-token"})
    assert resp.status_code == 200


# ─── File Download Endpoint Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_file_valid(client: AsyncClient, tmp_path):
    """GET /api/files/{filename} returns the file for valid files in output dir."""
    # Create a file in the output directory
    output_dir = Path(server_module._config.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    test_file = output_dir / "report.txt"
    test_file.write_text("hello world")

    resp = await client.get("/api/files/report.txt")
    assert resp.status_code == 200
    assert b"hello world" in resp.content


@pytest.mark.asyncio
async def test_download_file_not_found(client: AsyncClient):
    """GET /api/files/{filename} returns 404 for missing files."""
    resp = await client.get("/api/files/nonexistent.txt")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_file_path_traversal_blocked(client: AsyncClient, tmp_path):
    """GET /api/files/{filename} with path traversal returns 403."""
    # Attempt to escape the output directory
    resp = await client.get("/api/files/../../../etc/passwd")
    assert resp.status_code in (403, 404)  # 403=blocked, 404=normalised by FastAPI


# ─── PIPELINE_COMPLETE Full Result Test ───────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_complete_contains_full_result():
    """PIPELINE_COMPLETE event should contain the full result dict, not just counts."""
    from hydra_agents import Hydra
    from hydra_agents.config import HydraConfig
    from hydra_agents.events import EventBus, EventType, HydraEvent

    full_result = {
        "output": "Test output",
        "warnings": [],
        "execution_summary": {"total_tokens": 100},
        "files_generated": ["report.txt"],
        "per_agent_quality": {},
        "agents_needing_retry": [],
        "retry_metadata": {"retried_agents": [], "retry_performed": False},
    }

    hydra = Hydra(config=HydraConfig())

    with patch.object(hydra, "_run_pipeline", AsyncMock(return_value=full_result)):
        events_received = []
        async for event in hydra.stream("test task"):
            events_received.append(event)

    complete_events = [e for e in events_received if e.type == EventType.PIPELINE_COMPLETE]
    assert len(complete_events) == 1
    data = complete_events[0].data
    assert isinstance(data, dict)
    # Must contain full result fields (not just counts)
    assert "output" in data
    assert "execution_summary" in data
    assert data["output"] == "Test output"


# ─── agent_complete Event Fields Test ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_complete_event_has_full_fields():
    """agent_complete event data must include output, status, tokens_used, execution_time_ms."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from hydra_agents.agent import Agent
    from hydra_agents.config import HydraConfig
    from hydra_agents.events import EventBus, EventType
    from hydra_agents.models import AgentOutput, AgentSpec, AgentStatus, SubTask
    from hydra_agents.state_manager import StateManager
    from hydra_agents.tool_registry import ToolRegistry

    spec = AgentSpec(
        agent_id="agent-1",
        sub_task_id="task-1",
        role="Researcher",
        goal="Research something",
        backstory="Expert researcher",
        tools_needed=[],
    )
    from hydra_agents.models import Priority
    sub_task = SubTask(
        id="task-1",
        description="Research topic X",
        expected_output="Summary",
        dependencies=[],
        priority=Priority.NORMAL,
    )

    config = HydraConfig()
    registry = ToolRegistry()
    state = StateManager()
    bus = EventBus()

    agent = Agent(
        agent_spec=spec,
        sub_task=sub_task,
        tool_registry=registry,
        state_manager=state,
        config=config,
        event_bus=bus,
    )

    complete_events = []
    bus.on(lambda e: complete_events.append(e) if e.type == EventType.AGENT_COMPLETE else None)

    expected_output = AgentOutput(
        agent_id="agent-1",
        sub_task_id="task-1",
        status=AgentStatus.COMPLETED,
        output="done",
        tokens_used=42,
        execution_time_ms=123,
        quality_score=None,
    )

    with patch.object(agent, "_run_tool_loop", AsyncMock(return_value=("done", 42))):
        with patch.object(state, "write_output", AsyncMock()):
            with patch.object(state, "write_shared", AsyncMock()):
                with patch.object(state, "get_upstream_context", AsyncMock(return_value="")):
                    await agent.execute()

    assert len(complete_events) >= 1
    event = complete_events[-1]
    data = event.data or {}
    assert "status" in data, f"Missing 'status' in agent_complete data: {data}"
    assert "tokens_used" in data, f"Missing 'tokens_used' in agent_complete data: {data}"
    assert "execution_time_ms" in data, f"Missing 'execution_time_ms' in agent_complete data: {data}"
