"""
Thread-safe shared state manager for inter-agent communication.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from hydra.models import AgentOutput, AgentStatus, FileAttachment

logger = structlog.get_logger(__name__)

# Approximate tokens → characters ratio (conservative)
_CHARS_PER_TOKEN = 4
_TRUNCATE_TOKEN_LIMIT = 500
_TRUNCATE_CHAR_LIMIT = _TRUNCATE_TOKEN_LIMIT * _CHARS_PER_TOKEN
_CONTEXT_WINDOW_WARN_RATIO = 0.5
_MODEL_CONTEXT_WINDOW = 100_000  # default estimate


class StateManager:
    """
    In-memory state store for Hydra agents.

    Provides:
    - Per-agent output storage
    - Upstream context injection for dependent agents
    - Shared key-value store (for memory tools)
    - File registration
    - Execution summary statistics
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._agent_outputs: dict[str, AgentOutput] = {}
        self._shared_context: dict[str, Any] = {}
        self._files: dict[str, str] = {}          # filename → filepath
        self._uploaded_files: list[FileAttachment] = []   # uploaded file attachments
        self._start_time = time.monotonic()
        self._sub_task_to_role: dict[str, str] = {}  # sub_task_id → agent role

    # ── Agent output storage ──────────────────────────────────────────────────

    async def write_output(self, sub_task_id: str, output: AgentOutput) -> None:
        """Store an agent's result."""
        async with self._lock:
            self._agent_outputs[sub_task_id] = output
            logger.debug(
                "agent_output_written",
                sub_task_id=sub_task_id,
                status=output.status,
                tokens=output.tokens_used,
            )

    def write_output_sync(self, sub_task_id: str, output: AgentOutput) -> None:
        """Synchronous variant for use outside async contexts."""
        self._agent_outputs[sub_task_id] = output

    async def get_output(self, sub_task_id: str) -> AgentOutput | None:
        """Retrieve an agent's result by sub-task ID."""
        async with self._lock:
            return self._agent_outputs.get(sub_task_id)

    def get_output_sync(self, sub_task_id: str) -> AgentOutput | None:
        """Synchronous variant."""
        return self._agent_outputs.get(sub_task_id)

    # ── Role registry ─────────────────────────────────────────────────────────

    def register_role(self, sub_task_id: str, role: str) -> None:
        """Associate a human-readable role with a sub-task ID for richer context strings."""
        self._sub_task_to_role[sub_task_id] = role

    # ── Context injection ─────────────────────────────────────────────────────

    async def get_upstream_context(
        self,
        sub_task_id: str,
        dependency_ids: list[str],
    ) -> str:
        """
        Build a formatted string of upstream results to inject into a dependent agent.

        - Short outputs (≤ 500 tokens) are included in full.
        - Long outputs are truncated with a note to use memory_retrieve.
        - Warns if total injected context exceeds 50 % of the estimated context window.
        """
        if not dependency_ids:
            return ""

        sections: list[str] = []
        total_chars = 0

        async with self._lock:
            for dep_id in dependency_ids:
                dep_output = self._agent_outputs.get(dep_id)
                if dep_output is None:
                    logger.warning("upstream_output_missing", dep_id=dep_id, requesting=sub_task_id)
                    continue
                if dep_output.status != AgentStatus.COMPLETED:
                    logger.warning(
                        "upstream_not_completed",
                        dep_id=dep_id,
                        status=dep_output.status,
                        requesting=sub_task_id,
                    )
                    continue

                role = self._sub_task_to_role.get(dep_id, dep_id)
                raw = str(dep_output.output or "")

                if len(raw) > _TRUNCATE_CHAR_LIMIT:
                    body = raw[:_TRUNCATE_CHAR_LIMIT] + (
                        f"\n... [truncated — full output available via memory_retrieve key='{dep_id}']"
                    )
                    logger.debug("upstream_context_truncated", dep_id=dep_id)
                else:
                    body = raw

                section = f"### Result from: {role}\n{body}"
                sections.append(section)
                total_chars += len(section)

        if not sections:
            return ""

        context = "\n\n".join(sections)
        approx_tokens = total_chars // _CHARS_PER_TOKEN
        if approx_tokens > _MODEL_CONTEXT_WINDOW * _CONTEXT_WINDOW_WARN_RATIO:
            logger.warning(
                "high_context_injection",
                approx_tokens=approx_tokens,
                context_window=_MODEL_CONTEXT_WINDOW,
            )

        return context

    # ── Shared key-value store ────────────────────────────────────────────────

    async def write_shared(self, key: str, value: Any) -> None:
        """Store a value in the shared context (used by memory_store tool)."""
        async with self._lock:
            self._shared_context[key] = value
            logger.debug("shared_context_written", key=key)

    async def read_shared(self, key: str) -> Any:
        """Read a value from shared context (used by memory_retrieve tool)."""
        async with self._lock:
            return self._shared_context.get(key)

    # ── File registry ─────────────────────────────────────────────────────────

    async def register_file(self, filename: str, filepath: str) -> None:
        """Track a file generated by an agent."""
        async with self._lock:
            self._files[filename] = filepath
            logger.info("file_registered", filename=filename, filepath=filepath)

    async def get_all_files(self) -> dict[str, str]:
        """Return all registered files."""
        async with self._lock:
            return dict(self._files)

    # ── Uploaded file attachments ─────────────────────────────────────────────

    async def store_files(self, files: list[FileAttachment]) -> None:
        """Store uploaded file metadata for agent access."""
        async with self._lock:
            self._uploaded_files.extend(files)
            logger.debug("uploaded_files_stored", count=len(files))

    async def get_files(self) -> list[FileAttachment]:
        """Get all uploaded files."""
        async with self._lock:
            return list(self._uploaded_files)

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_all_outputs(self) -> dict[str, AgentOutput]:
        """Return a snapshot of all agent outputs."""
        async with self._lock:
            return dict(self._agent_outputs)

    async def get_execution_summary(self) -> dict:
        """Return aggregated execution statistics."""
        async with self._lock:
            outputs = list(self._agent_outputs.values())

        total_tokens = sum(o.tokens_used for o in outputs)
        total_time_ms = sum(o.execution_time_ms for o in outputs)
        completed = sum(1 for o in outputs if o.status == AgentStatus.COMPLETED)
        failed = sum(1 for o in outputs if o.status == AgentStatus.FAILED)
        wall_clock_ms = int((time.monotonic() - self._start_time) * 1000)

        return {
            "total_agents": len(outputs),
            "completed": completed,
            "failed": failed,
            "total_tokens_used": total_tokens,
            "total_agent_time_ms": total_time_ms,
            "wall_clock_time_ms": wall_clock_ms,
            "files_generated": len(self._files),
        }
