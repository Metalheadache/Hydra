"""
History database — SQLite-backed storage for task run history.

HistoryDB is lazily initialized: tables are created on first use.
Uses aiosqlite for async I/O to avoid blocking the event loop.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import aiosqlite

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_runs (
    task_id TEXT PRIMARY KEY,
    task_text TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    duration_ms INTEGER,
    total_tokens INTEGER,
    total_cost REAL,
    files_count INTEGER DEFAULT 0,
    agent_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class HistoryDB:
    """Async SQLite-backed task run history store."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._initialized = False

    async def init(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        if self._initialized:
            return
        # Ensure parent directory exists
        db_path = Path(self.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        first_create = not db_path.exists()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(_CREATE_TABLE_SQL)
            # Enable WAL mode for better concurrent read performance
            await db.execute("PRAGMA journal_mode=WAL")
            await db.commit()
        # Restrict DB file permissions on first creation (owner read/write only)
        if first_create and db_path.exists():
            os.chmod(self.db_path, 0o600)
        self._initialized = True

    async def _ensure_init(self) -> None:
        if not self._initialized:
            await self.init()

    async def save_run(
        self,
        task_id: str,
        task_text: str,
        status: str,
        result: dict | None,
        duration_ms: int | None,
        total_tokens: int | None,
        total_cost: float | None = None,
        files_count: int = 0,
        agent_count: int = 0,
    ) -> None:
        """Insert or replace a task run record."""
        await self._ensure_init()
        result_json = json.dumps(result, default=str) if result is not None else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO task_runs
                    (task_id, task_text, status, result_json, duration_ms,
                     total_tokens, total_cost, files_count, agent_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_text,
                    status,
                    result_json,
                    duration_ms,
                    total_tokens,
                    total_cost,
                    files_count,
                    agent_count,
                ),
            )
            await db.commit()

    async def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Return summary rows ordered by created_at DESC."""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    task_id,
                    substr(task_text, 1, 100) AS task_text,
                    status,
                    duration_ms,
                    total_tokens,
                    total_cost,
                    files_count,
                    agent_count,
                    created_at
                FROM task_runs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_run(self, task_id: str) -> dict | None:
        """Return the full record for a task run, or None if not found."""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_runs WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            data = dict(row)
            # Decode result_json inline
            if data.get("result_json"):
                try:
                    data["result"] = json.loads(data["result_json"])
                except json.JSONDecodeError:
                    data["result"] = None
            else:
                data["result"] = None
            return data

    async def delete_run(self, task_id: str) -> bool:
        """Delete a run. Returns True if a row was deleted."""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM task_runs WHERE task_id = ?",
                (task_id,),
            )
            await db.commit()
            return cursor.rowcount > 0
