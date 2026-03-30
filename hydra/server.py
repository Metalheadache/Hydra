"""
Hydra FastAPI Server — REST + WebSocket API for the Hydra framework.

Start with:
    python -m hydra.server          (default host=0.0.0.0, port=8000)
    python -m hydra.server --port 9000

Or programmatically:
    from hydra.server import start_server
    start_server(host="0.0.0.0", port=8000)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from hydra.audit import AuditLogger
from hydra.config import HydraConfig
from hydra.events import EventBus, EventType, HydraEvent
from hydra.file_processor import FileProcessor
from hydra.history import HistoryDB
from hydra import Hydra

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum task text length accepted by the API (32 KB)
MAX_TASK_LENGTH = 32768

# Suggested LLM model list shown in the UI
_SUGGESTED_MODELS = [
    {"id": "anthropic/claude-sonnet-4-6", "provider": "Anthropic"},
    {"id": "gpt-4o", "provider": "OpenAI"},
    {"id": "deepseek/deepseek-chat", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-reasoner", "provider": "DeepSeek"},
    {"id": "ollama/llama3", "provider": "Ollama"},
    {"id": "gemini/gemini-2.5-flash", "provider": "Google"},
]

# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Hydra",
    description="Dynamic Multi-Agent Orchestration Framework API",
    version="0.1.0",
)

# CORS middleware — reads _config.cors_origins per request so changes take effect
# without a restart. A custom middleware is used instead of add_middleware() to
# allow dynamic origin resolution.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """CORS middleware that reads origins from _config on every request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        origin = request.headers.get("origin")
        cors_origins_str = _config.cors_origins if "_config" in globals() else "*"
        allowed_origins = [o.strip() for o in cors_origins_str.split(",")]
        allow_all = "*" in allowed_origins
        allow_origin = "*" if allow_all else (origin if origin in allowed_origins else "")

        if request.method == "OPTIONS":
            # Preflight
            response = Response(status_code=204)
        else:
            response = await call_next(request)

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = allow_origin
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        if not allow_all and origin in allowed_origins:
            response.headers["Vary"] = "Origin"
        return response


app.add_middleware(DynamicCORSMiddleware)

# task_id validation pattern (used by history endpoints)
TASK_ID_PATTERN = re.compile(r"^task_[a-f0-9]{8,}$")

# ── Shared state ──────────────────────────────────────────────────────────────

# In-memory config; loaded once at startup, mutated via POST /api/config
_config = HydraConfig()

# Lock to protect read-modify-write updates to _config
_config_lock = asyncio.Lock()

# Track active pipeline tasks so we can cancel them on shutdown
_active_tasks: set[asyncio.Task] = set()

# Output directory is taken from config; history DB lives there too
_DB_PATH = str(Path(_config.output_directory) / "history.db")
_history_db = HistoryDB(_DB_PATH)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _redact_config(cfg: HydraConfig) -> dict:
    """Return config as dict with api_key redacted."""
    data = cfg.model_dump()
    data["api_key"] = "***" if cfg.api_key else ""
    return data


def _extract_result_meta(result: dict) -> tuple[int | None, float | None, int, int]:
    """
    Extract (total_tokens, total_cost, files_count, agent_count) from a result dict.
    All values are best-effort; fall back to 0 / None on missing data.
    """
    summary = result.get("execution_summary", {}) or {}
    total_tokens = summary.get("total_tokens")
    total_cost = summary.get("total_cost")
    files_count = len(result.get("files_generated", []))
    per_agent = result.get("per_agent_quality", {}) or {}
    agent_count = len(per_agent)
    return total_tokens, total_cost, files_count, agent_count


# ── Auth dependency ───────────────────────────────────────────────────────────

async def verify_token(request: Request) -> None:
    """
    FastAPI dependency for optional token-based authentication.
    If HydraConfig.server_token is empty, auth is disabled.
    Otherwise, the client must supply the token via X-API-Key header
    or ?token= query parameter.
    """
    if not _config.server_token:
        return  # auth not configured — open access
    token = request.headers.get("X-API-Key") or request.query_params.get("token")
    if token != _config.server_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup() -> None:
    await _history_db.init()


@app.on_event("shutdown")
async def _shutdown() -> None:
    logger.info("Server shutting down")
    for task in list(_active_tasks):
        if not task.done():
            task.cancel()
    if _active_tasks:
        await asyncio.gather(*_active_tasks, return_exceptions=True)
    _active_tasks.clear()


# ── Static / frontend ─────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # Mount static assets (JS, CSS, images) at /assets
    _assets = _FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
    # Mount fonts
    _fonts = _FRONTEND_DIST / "fonts"
    if _fonts.exists():
        app.mount("/fonts", StaticFiles(directory=str(_fonts)), name="fonts")


@app.get("/", include_in_schema=False)
async def serve_frontend() -> Any:
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse(
        "<h1>Hydra</h1><p>Frontend not built. Run <code>npm run build</code> inside <code>frontend/</code>.</p>",
        status_code=200,
    )


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config", dependencies=[Depends(verify_token)])
async def get_config() -> dict:
    """Return current config with api_key redacted."""
    return _redact_config(_config)


@app.post("/api/config", dependencies=[Depends(verify_token)])
async def update_config(body: dict) -> dict:
    """
    Partially update the in-memory config.
    Only recognised HydraConfig fields are accepted; unknown keys are ignored.
    """
    global _config, _history_db, _DB_PATH

    allowed = set(HydraConfig.model_fields.keys())
    # api_key is allowed to be set, but we never allow setting it to the redacted value
    updates = {k: v for k, v in body.items() if k in allowed}

    if not updates:
        raise HTTPException(status_code=400, detail="No valid config fields provided.")

    new_config: HydraConfig
    async with _config_lock:
        # Merge: build new config from current + overrides
        current = _config.model_dump()
        # If caller sends the redacted placeholder, keep existing key
        if updates.get("api_key") in ("***", None) and "api_key" in updates:
            updates.pop("api_key")
        current.update(updates)

        try:
            new_config = HydraConfig(**current)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    # Atomic reference swap outside lock (Python reference assignment is atomic)
    _config = new_config

    # Re-point history DB if output_directory changed
    new_db_path = str(Path(_config.output_directory) / "history.db")
    if new_db_path != _DB_PATH:
        _DB_PATH = new_db_path
        _history_db = HistoryDB(_DB_PATH)
        await _history_db.init()

    return _redact_config(_config)


# ── Tools ─────────────────────────────────────────────────────────────────────

@app.get("/api/tools", dependencies=[Depends(verify_token)])
async def list_tools() -> list[dict]:
    """Return all registered tools with name, description, and parameter schema."""
    hydra = Hydra(config=_config)
    registry = hydra.tool_registry
    tools = []
    for name in registry.list_names():
        tool = registry.get(name)
        if tool is None:
            continue
        schema = tool.get_schema()
        # schema is in OpenAI function-calling format:
        # {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        fn = schema.get("function", schema)
        tools.append(
            {
                "name": fn.get("name", name),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
        )
    return tools


# ── Models ────────────────────────────────────────────────────────────────────

@app.get("/api/models", dependencies=[Depends(verify_token)])
async def list_models() -> list[dict]:
    """Return suggested model list."""
    return _SUGGESTED_MODELS


# ── Upload ────────────────────────────────────────────────────────────────────

@app.post("/api/upload", dependencies=[Depends(verify_token)])
async def upload_files(files: list[UploadFile]) -> list[dict]:
    """
    Accept one or more multipart file uploads.
    Returns list of FileAttachment objects as dicts.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    cfg = _config  # snapshot for consistent reads during this request
    processor = FileProcessor(cfg.output_directory)
    results = []
    max_bytes = cfg.max_upload_file_size_mb * 1024 * 1024
    for upload in files:
        # Read in chunks to detect oversized files early without loading everything
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(8192)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File '{upload.filename}' exceeds {cfg.max_upload_file_size_mb}MB limit",
                )
            chunks.append(chunk)
        content = b"".join(chunks)
        filename = upload.filename or "unnamed"
        try:
            attachment = await processor.process_upload(filename, content)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        results.append(attachment.model_dump())
    return results


# ── Task (REST, non-streaming) ────────────────────────────────────────────────

@app.post("/api/task", dependencies=[Depends(verify_token)])
async def run_task(body: dict) -> dict:
    """
    Run a task synchronously (non-streaming, for programmatic/webhook use).
    Body: {"task": str, "files": list[str] | null}
    """
    task = body.get("task")
    if not task or not isinstance(task, str):
        raise HTTPException(status_code=400, detail="'task' field is required and must be a string.")

    if len(task) > MAX_TASK_LENGTH:
        raise HTTPException(status_code=400, detail=f"Task text exceeds {MAX_TASK_LENGTH} character limit")

    files: list[str] | None = body.get("files")

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    started = time.time()

    hydra = Hydra(config=_config)
    status = "completed"
    result: dict = {}
    try:
        result = await hydra.run(task, files=files)
    except Exception as exc:
        status = "failed"
        result = {"error": str(exc)}

    duration_ms = int((time.time() - started) * 1000)
    total_tokens, total_cost, files_count, agent_count = _extract_result_meta(result)

    await _history_db.save_run(
        task_id=task_id,
        task_text=task,
        status=status,
        result=result,
        duration_ms=duration_ms,
        total_tokens=total_tokens,
        total_cost=total_cost,
        files_count=files_count,
        agent_count=agent_count,
    )

    if status == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "Pipeline failed"))

    result["task_id"] = task_id
    return result


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/api/files/{filename:path}", dependencies=[Depends(verify_token)])
async def download_file(filename: str) -> Any:
    """
    Download a generated file from the output directory.
    Path traversal is blocked — only files within output_directory are served.
    """
    output_dir = Path(_config.output_directory).resolve()
    filepath = (output_dir / filename).resolve()
    if not filepath.is_relative_to(output_dir):
        raise HTTPException(status_code=403, detail="Access denied")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(filepath), filename=filepath.name)


@app.get("/api/history", dependencies=[Depends(verify_token)])
async def list_history(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """Return list of past task runs (summary view)."""
    return await _history_db.list_runs(limit=limit, offset=offset)


@app.get("/api/history/{task_id}", dependencies=[Depends(verify_token)])
async def get_history_run(task_id: str) -> dict:
    """Return the full record for a specific task run."""
    if not TASK_ID_PATTERN.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    row = await _history_db.get_run(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task run '{task_id}' not found.")
    return row


@app.delete("/api/history/{task_id}", dependencies=[Depends(verify_token)])
async def delete_history_run(task_id: str) -> dict:
    """Delete a task run record."""
    if not TASK_ID_PATTERN.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task_id format")
    deleted = await _history_db.delete_run(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task run '{task_id}' not found.")
    return {"deleted": task_id}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/task")
async def ws_task(websocket: WebSocket) -> None:
    """
    WebSocket streaming endpoint.

    Client sends:
        {"type": "start_task", "task": "...", "files": [...], "config_overrides": {...}}
    Server streams HydraEvent objects as JSON.

    During execution, client may also send:
        {"type": "confirmation_response", "confirmation_id": "...", "approved": true}
        {"type": "cancel"}

    Optional auth: pass ?token=<server_token> as query param when HYDRA_SERVER_TOKEN is set.
    """
    await websocket.accept()

    cfg = _config  # snapshot for consistent reads during this connection

    # Auth via first message (not query param — query params are logged by proxies)
    if cfg.server_token:
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            auth_msg = json.loads(raw_auth)
        except (asyncio.TimeoutError, Exception):
            await websocket.close(code=4001)
            return
        if auth_msg.get("type") != "auth" or auth_msg.get("token") != cfg.server_token:
            await websocket.close(code=4001)
            return

    pipeline_task: asyncio.Task | None = None
    event_bus: EventBus | None = None
    task_id: str | None = None
    task_text: str = ""
    started: float = 0.0

    async def _send_event(event: HydraEvent) -> None:
        try:
            await websocket.send_text(event.model_dump_json())
        except Exception:
            pass  # Client may have disconnected

    async def _run_and_stream(
        task: str,
        files: list[str] | None,
        cfg: HydraConfig,
        bus: EventBus,
        audit: AuditLogger,
    ) -> dict:
        """Run pipeline, stream events, return final result."""
        # Register audit log listener
        async def _audit_listener(event: HydraEvent) -> None:
            try:
                await audit.log_async(str(event.type), event.model_dump())
            except Exception:
                pass

        bus.on_async(_audit_listener)

        hydra = Hydra(config=cfg)
        result: dict = {}
        try:
            async for event in hydra.stream(task, files=files, event_bus=bus):
                await _send_event(event)
                if event.type == EventType.PIPELINE_COMPLETE:
                    result = event.data if isinstance(event.data, dict) else {}
                elif event.type == EventType.PIPELINE_ERROR:
                    result = {"error": (event.data or {}).get("error", "Pipeline error")}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_event = HydraEvent(
                type=EventType.PIPELINE_ERROR,
                data={"error": str(exc)},
            )
            await _send_event(error_event)
            result = {"error": str(exc)}
        return result

    try:
        # Wait for first message to start the task (30s timeout — client should send immediately)
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        msg = json.loads(raw)

        if msg.get("type") != "start_task":
            await websocket.send_text(
                json.dumps({"error": "Expected 'start_task' message type."})
            )
            await websocket.close(code=1008)
            return

        task_text = msg.get("task", "")
        if not task_text:
            await websocket.send_text(json.dumps({"error": "'task' is required."}))
            await websocket.close(code=1008)
            return

        if len(task_text) > MAX_TASK_LENGTH:
            await websocket.send_text(
                json.dumps({"error": f"Task text exceeds {MAX_TASK_LENGTH} character limit"})
            )
            await websocket.close(code=1008)
            return

        files: list[str] | None = msg.get("files")
        config_overrides: dict = msg.get("config_overrides") or {}

        # Build per-task config
        cfg_data = _config.model_dump()
        if config_overrides:
            allowed = set(HydraConfig.model_fields.keys())
            valid_overrides = {k: v for k, v in config_overrides.items() if k in allowed}
            cfg_data.update(valid_overrides)
        try:
            task_cfg = HydraConfig(**cfg_data)
        except Exception:
            task_cfg = _config

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        started = time.time()
        audit = AuditLogger(task_cfg.output_directory)
        event_bus = EventBus()
        # Mark stream consumer BEFORE any events can be emitted so the first
        # PIPELINE_START event is queued rather than dropped.
        event_bus._has_stream_consumer = True

        # Run pipeline in background task so we can handle incoming messages concurrently
        pipeline_task = asyncio.create_task(
            _run_and_stream(task_text, files, task_cfg, event_bus, audit)
        )
        _active_tasks.add(pipeline_task)
        pipeline_task.add_done_callback(_active_tasks.discard)

        # Listen for incoming client messages while pipeline runs
        async def _listen_for_client() -> None:
            try:
                while True:
                    raw_in = await websocket.receive_text()
                    try:
                        incoming = json.loads(raw_in)
                    except json.JSONDecodeError:
                        continue

                    msg_type = incoming.get("type")
                    if msg_type == "cancel":
                        if pipeline_task and not pipeline_task.done():
                            pipeline_task.cancel()
                        break
                    elif msg_type == "confirmation_response" and event_bus:
                        conf_id = incoming.get("confirmation_id", "")
                        approved = bool(incoming.get("approved", False))
                        await event_bus.respond_to_confirmation(conf_id, approved)
            except (WebSocketDisconnect, asyncio.CancelledError):
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()

        listener_task = asyncio.create_task(_listen_for_client())

        result: dict = {}
        status = "completed"
        try:
            result = await pipeline_task
            if "error" in result:
                status = "failed"
        except asyncio.CancelledError:
            status = "cancelled"
            result = {}
        except Exception as exc:
            status = "failed"
            result = {"error": str(exc)}
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

        # Save to history
        duration_ms = int((time.time() - started) * 1000)
        total_tokens, total_cost, files_count, agent_count = _extract_result_meta(result)
        if task_id:
            await _history_db.save_run(
                task_id=task_id,
                task_text=task_text,
                status=status,
                result=result if status != "cancelled" else None,
                duration_ms=duration_ms,
                total_tokens=total_tokens,
                total_cost=total_cost,
                files_count=files_count,
                agent_count=agent_count,
            )

    except WebSocketDisconnect:
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
    except Exception as exc:
        logger.exception("ws_task_error: %s", exc)
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the Hydra HTTP server."""
    uvicorn.run("hydra.server:app", host=host, port=port, reload=False)



