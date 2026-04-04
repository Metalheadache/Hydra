"""
Hydra Audit Logger — structured JSON line logging for pipeline events.

AuditLogger is fully optional. Components accept it as
``audit_logger: AuditLogger | None = None`` and guard every call with
``if self.audit_logger:``.  When not configured, there is zero overhead.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """
    Structured audit logging for Hydra pipelines.

    Appends one JSON object per line (JSON Lines format) to
    ``<output_dir>/audit.log``.  The file is created on first write.

    Each entry is flat: { "timestamp": ..., "event_type": ..., <fields...> }

    Thread / coroutine safety: Python's built-in ``open`` + ``write`` is
    effectively atomic for small writes on POSIX; for production use at
    high concurrency consider wrapping writes in an asyncio.Lock.
    """

    def __init__(self, output_dir: str) -> None:
        self.log_path = Path(output_dir) / "audit.log"
        # Ensure the directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Lock to prevent interleaved writes under concurrent async contexts
        self._write_lock = threading.Lock()

    # ── Core writer ───────────────────────────────────────────────────────────

    def log(self, event_type: str, data: dict[str, Any]) -> None:
        """Append a flat JSON-Lines entry to the audit log (sync, thread-safe)."""
        entry = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type,
            **data,
        }
        with self._write_lock:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")

    async def log_async(self, event_type: str, data: dict[str, Any]) -> None:
        """Async wrapper for log() — safe to call from async contexts.

        Uses asyncio.to_thread() so the blocking file write doesn't block
        the event loop.
        """
        import asyncio
        await asyncio.to_thread(self.log, event_type, data)

    # ── Convenience helpers ───────────────────────────────────────────────────

    def log_llm_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: int,
        agent_id: str | None = None,
    ) -> None:
        """Log a single LLM completion call."""
        self.log(
            "llm_call",
            {
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "total_tokens": tokens_in + tokens_out,
                "duration_ms": duration_ms,
                "agent_id": agent_id,
            },
        )

    def log_tool_execution(
        self,
        tool_name: str,
        args: dict,
        result_success: bool,
        duration_ms: int,
        agent_id: str | None = None,
    ) -> None:
        """Log a single tool execution."""
        self.log(
            "tool_execution",
            {
                "tool_name": tool_name,
                "arg_keys": list(args.keys()),
                "success": result_success,
                "duration_ms": duration_ms,
                "agent_id": agent_id,
            },
        )

    def log_state_mutation(
        self,
        operation: str,
        key: str,
        agent_id: str | None = None,
    ) -> None:
        """Log a state-manager write operation."""
        self.log(
            "state_mutation",
            {
                "operation": operation,
                "key": key,
                "agent_id": agent_id,
            },
        )

    def log_quality_score(
        self,
        agent_id: str,
        sub_task_id: str,
        score: float,
        feedback: str | None = None,
    ) -> None:
        """Log a quality score assigned to an agent output."""
        self.log(
            "quality_score",
            {
                "agent_id": agent_id,
                "sub_task_id": sub_task_id,
                "score": score,
                "feedback": feedback,
            },
        )
