"""
Memory tools for inter-agent shared context.
These tools require a StateManager reference at instantiation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra.state_manager import StateManager

logger = structlog.get_logger(__name__)


class MemoryStoreTool(BaseTool):
    """Store a value in the shared context for other agents to read."""

    name = "memory_store"
    description = (
        "Store a key-value pair in the shared memory context. "
        "Other agents can retrieve this value using memory_retrieve with the same key."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Unique key to store the value under.",
            },
            "value": {
                "description": "Value to store (any JSON-serialisable type).",
            },
        },
        "required": ["key", "value"],
    }

    def __init__(self, state_manager: "StateManager | None" = None) -> None:
        self._state_manager = state_manager

    async def execute(self, key: str, value) -> ToolResult:
        if self._state_manager is None:
            return ToolResult(success=False, error="MemoryStoreTool: StateManager not injected.")
        try:
            await self._state_manager.write_shared(key, value)
            return ToolResult(success=True, data={"key": key, "stored": True})
        except Exception as exc:
            logger.error("memory_store_failed", key=key, error=str(exc))
            return ToolResult(success=False, error=f"Failed to store memory key '{key}': {exc}")


class MemoryRetrieveTool(BaseTool):
    """Retrieve a value from the shared context by key."""

    name = "memory_retrieve"
    description = (
        "Retrieve a previously stored value from shared memory by key. "
        "Returns None if the key does not exist."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key to look up in shared memory.",
            },
        },
        "required": ["key"],
    }

    def __init__(self, state_manager: "StateManager | None" = None) -> None:
        self._state_manager = state_manager

    async def execute(self, key: str) -> ToolResult:
        if self._state_manager is None:
            return ToolResult(success=False, error="MemoryRetrieveTool: StateManager not injected.")
        try:
            value = await self._state_manager.read_shared(key)
            return ToolResult(success=True, data={"key": key, "value": value, "found": value is not None})
        except Exception as exc:
            logger.error("memory_retrieve_failed", key=key, error=str(exc))
            return ToolResult(success=False, error=f"Failed to retrieve memory key '{key}': {exc}")
