"""
File generation tools for Hydra agents.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra.state_manager import StateManager

logger = structlog.get_logger(__name__)

# Default output directory — agents may override via config
_DEFAULT_OUTPUT_DIR = "./hydra_output"


def _ensure_output_dir(output_dir: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filepath(output_path: Path, filename: str) -> Path | None:
    """
    Resolve the filepath and verify it remains under output_path.
    Returns None if path traversal is detected.

    Uses Path.is_relative_to() (Python 3.9+) to prevent prefix-based bypass
    attacks where a sibling directory (e.g. /tmp/hydra_output_evil) would
    incorrectly pass a startswith() check against /tmp/hydra_output.
    """
    resolved_output = output_path.resolve()
    filepath = (output_path / filename).resolve()
    if not filepath.is_relative_to(resolved_output):
        return None
    return filepath


class WriteMarkdownTool(BaseTool):
    """Write content to a Markdown (.md) file."""

    name = "write_markdown"
    description = "Write content to a Markdown (.md) file. Returns the filepath of the created file."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the file (e.g. 'report.md'). Extension is added if missing.",
            },
            "content": {
                "type": "string",
                "description": "Full Markdown content to write.",
            },
            "output_dir": {
                "type": "string",
                "description": f"Directory to write the file. Defaults to '{_DEFAULT_OUTPUT_DIR}'.",
            },
        },
        "required": ["filename", "content"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR, state_manager: "StateManager | None" = None) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(self, filename: str, content: str, output_dir: str | None = None) -> ToolResult:
        try:
            effective_dir = output_dir if output_dir is not None else self._output_dir
            output_path = _ensure_output_dir(effective_dir)
            if not filename.endswith(".md"):
                filename = filename + ".md"
            filepath = _safe_filepath(output_path, filename)
            if filepath is None:
                return ToolResult(success=False, error="Path traversal blocked")
            filepath.write_text(content, encoding="utf-8")
            if self._state_manager is not None:
                await self._state_manager.register_file(filename, str(filepath))
            logger.info("markdown_written", filepath=str(filepath), bytes=len(content))
            return ToolResult(success=True, data={"filepath": str(filepath), "bytes_written": len(content)})
        except Exception as exc:
            logger.error("write_markdown_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to write markdown file: {exc}")


class WriteJsonTool(BaseTool):
    """Write structured data to a JSON file with pretty-printing."""

    name = "write_json"
    description = "Write structured data to a .json file with pretty-printing. Returns the filepath."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the file (e.g. 'data.json').",
            },
            "data": {
                "description": "JSON-serialisable data to write.",
            },
            "output_dir": {
                "type": "string",
                "description": f"Directory to write the file. Defaults to '{_DEFAULT_OUTPUT_DIR}'.",
            },
        },
        "required": ["filename", "data"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR, state_manager: "StateManager | None" = None) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(self, filename: str, data, output_dir: str | None = None) -> ToolResult:
        try:
            effective_dir = output_dir if output_dir is not None else self._output_dir
            output_path = _ensure_output_dir(effective_dir)
            if not filename.endswith(".json"):
                filename = filename + ".json"
            filepath = _safe_filepath(output_path, filename)
            if filepath is None:
                return ToolResult(success=False, error="Path traversal blocked")
            text = json.dumps(data, indent=2, ensure_ascii=False)
            filepath.write_text(text, encoding="utf-8")
            if self._state_manager is not None:
                await self._state_manager.register_file(filename, str(filepath))
            logger.info("json_written", filepath=str(filepath))
            return ToolResult(success=True, data={"filepath": str(filepath), "bytes_written": len(text)})
        except Exception as exc:
            logger.error("write_json_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to write JSON file: {exc}")


class WriteCsvTool(BaseTool):
    """Write rows to a CSV file."""

    name = "write_csv"
    description = "Write tabular data (rows) to a .csv file. Returns the filepath."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the file (e.g. 'results.csv').",
            },
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column header names.",
            },
            "rows": {
                "type": "array",
                "items": {"type": "array"},
                "description": "List of rows, each row is a list of values.",
            },
            "output_dir": {
                "type": "string",
                "description": f"Directory to write the file. Defaults to '{_DEFAULT_OUTPUT_DIR}'.",
            },
        },
        "required": ["filename", "headers", "rows"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR, state_manager: "StateManager | None" = None) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(
        self,
        filename: str,
        headers: list[str],
        rows: list[list],
        output_dir: str | None = None,
    ) -> ToolResult:
        try:
            effective_dir = output_dir if output_dir is not None else self._output_dir
            output_path = _ensure_output_dir(effective_dir)
            if not filename.endswith(".csv"):
                filename = filename + ".csv"
            filepath = _safe_filepath(output_path, filename)
            if filepath is None:
                return ToolResult(success=False, error="Path traversal blocked")
            with filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            if self._state_manager is not None:
                await self._state_manager.register_file(filename, str(filepath))
            logger.info("csv_written", filepath=str(filepath), rows=len(rows))
            return ToolResult(success=True, data={"filepath": str(filepath), "rows_written": len(rows)})
        except Exception as exc:
            logger.error("write_csv_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to write CSV file: {exc}")


class WriteCodeTool(BaseTool):
    """Write source code to a file with a specified extension."""

    name = "write_code"
    description = (
        "Write source code to a file. Specify the language extension (py, js, ts, sh, etc.). "
        "Returns the filepath."
    )
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the file including extension (e.g. 'analysis.py').",
            },
            "code": {
                "type": "string",
                "description": "Source code content to write.",
            },
            "output_dir": {
                "type": "string",
                "description": f"Directory to write the file. Defaults to '{_DEFAULT_OUTPUT_DIR}'.",
            },
        },
        "required": ["filename", "code"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR, state_manager: "StateManager | None" = None) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(self, filename: str, code: str, output_dir: str | None = None) -> ToolResult:
        try:
            effective_dir = output_dir if output_dir is not None else self._output_dir
            output_path = _ensure_output_dir(effective_dir)
            filepath = _safe_filepath(output_path, filename)
            if filepath is None:
                return ToolResult(success=False, error="Path traversal blocked")
            filepath.write_text(code, encoding="utf-8")
            if self._state_manager is not None:
                await self._state_manager.register_file(filename, str(filepath))
            logger.info("code_written", filepath=str(filepath), bytes=len(code))
            return ToolResult(success=True, data={"filepath": str(filepath), "bytes_written": len(code)})
        except Exception as exc:
            logger.error("write_code_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to write code file: {exc}")
