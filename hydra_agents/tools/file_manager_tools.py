"""
File management tool for Hydra agents.

Single tool with an action enum to keep the Brain's tool-selection space
manageable.  Destructive actions (delete, move) use requires_confirmation
via separate tool classes to leverage Hydra's existing confirmation
infrastructure.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools._security import ensure_dir, safe_read_path, safe_write_path
from hydra_agents.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra_agents.state_manager import StateManager

logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = "./hydra_output"


class FileManagerTool(BaseTool):
    """Non-destructive file operations: list, tree, info, find, zip, unzip, copy, mkdir."""

    name = "file_manager"
    description = (
        "Manage files and directories. Actions: list, tree, info, find, "
        "copy, zip, unzip, mkdir. For move/delete operations, use "
        "file_move and file_delete tools instead (they require confirmation). "
        "All operations are sandboxed to the configured output directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "tree", "info", "find", "copy", "zip", "unzip", "mkdir"],
                "description": "File operation to perform.",
            },
            "path": {
                "type": "string",
                "description": "Primary path (file or directory).",
            },
            "destination": {
                "type": "string",
                "description": "Destination path (for copy, unzip).",
                "default": "",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern for 'find' action, e.g. '**/*.pdf'.",
                "default": "",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths for 'zip' action.",
                "default": [],
            },
        },
        "required": ["action", "path"],
    }

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        state_manager: "StateManager | None" = None,
    ) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve path within output_dir. Rejects paths that escape it."""
        root = Path(self._output_dir).resolve()
        resolved = (root / path_str).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Path escapes output directory: {path_str!r}")
        return resolved

    async def execute(
        self,
        action: str,
        path: str,
        destination: str = "",
        pattern: str = "",
        files: list | None = None,
    ) -> ToolResult:
        try:
            p = self._resolve_path(path)

            if action == "list":
                if not p.is_dir():
                    return ToolResult(success=False, error=f"Not a directory: {path}")
                entries = []
                for item in sorted(p.iterdir()):
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size_bytes": stat.st_size if item.is_file() else None,
                        "modified": stat.st_mtime,
                    })
                return ToolResult(success=True, data={"entries": entries, "count": len(entries)})

            elif action == "tree":
                if not p.is_dir():
                    return ToolResult(success=False, error=f"Not a directory: {path}")
                tree_lines = []
                count = 0
                for item in sorted(p.rglob("*")):
                    if count >= 200:
                        tree_lines.append("... (truncated at 200 entries)")
                        break
                    try:
                        rel = item.relative_to(p)
                    except ValueError:
                        continue
                    if len(rel.parts) > 3:
                        continue
                    indent = "  " * (len(rel.parts) - 1)
                    suffix = "/" if item.is_dir() else f" ({item.stat().st_size:,} bytes)"
                    tree_lines.append(f"{indent}{item.name}{suffix}")
                    count += 1
                return ToolResult(success=True, data={"tree": "\n".join(tree_lines)})

            elif action == "info":
                if not p.exists():
                    return ToolResult(success=False, error=f"Not found: {path}")
                stat = p.stat()
                return ToolResult(
                    success=True,
                    data={
                        "name": p.name,
                        "type": "dir" if p.is_dir() else "file",
                        "size_bytes": stat.st_size,
                        "extension": p.suffix,
                        "modified": stat.st_mtime,
                        "created": stat.st_ctime,
                        "absolute_path": str(p),
                    },
                )

            elif action == "find":
                if not pattern:
                    return ToolResult(success=False, error="'pattern' required for find action")
                if not p.is_dir():
                    return ToolResult(success=False, error=f"Not a directory: {path}")
                matches = [str(m) for m in sorted(p.glob(pattern))[:100]]
                return ToolResult(success=True, data={"matches": matches, "count": len(matches)})

            elif action == "copy":
                if not destination:
                    return ToolResult(success=False, error="'destination' required for copy action")
                if not p.exists():
                    return ToolResult(success=False, error=f"Source not found: {path}")
                dst = self._resolve_path(destination)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if p.is_dir():
                    shutil.copytree(str(p), str(dst))
                else:
                    shutil.copy2(str(p), str(dst))
                logger.info("file_copy", src=str(p), dst=str(dst))
                return ToolResult(success=True, data={"copied": str(p), "to": str(dst)})

            elif action == "zip":
                file_list = files or []
                # Default zip output name
                zip_dest = destination or (str(p) + ".zip" if p.is_dir() or p.is_file() else "archive.zip")
                output_path = ensure_dir(Path(self._output_dir))
                zip_path = safe_write_path(output_path, Path(zip_dest).name)
                if zip_path is None:
                    return ToolResult(success=False, error="Path traversal blocked on zip output")

                with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                    if file_list:
                        for f in file_list:
                            fp = self._resolve_path(f)
                            if fp.is_file():
                                zf.write(str(fp), f)
                    elif p.is_dir():
                        for item in p.rglob("*"):
                            if item.is_file():
                                zf.write(str(item), str(item.relative_to(p)))
                    elif p.is_file():
                        zf.write(str(p), p.name)
                    else:
                        return ToolResult(success=False, error=f"Nothing to zip: {path}")

                if self._state_manager is not None:
                    await self._state_manager.register_file(zip_path.name, str(zip_path))

                logger.info("file_zip", output=str(zip_path))
                return ToolResult(
                    success=True,
                    data={"zip_path": str(zip_path), "size_bytes": zip_path.stat().st_size},
                )

            elif action == "unzip":
                if not p.is_file():
                    return ToolResult(success=False, error=f"Not a file: {path}")
                dst = self._resolve_path(destination or str(p.stem))
                dst.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(str(p), "r") as zf:
                    # Security: check for zip-slip
                    for member in zf.namelist():
                        member_path = (dst / member).resolve()
                        if not member_path.is_relative_to(dst.resolve()):
                            return ToolResult(success=False, error=f"Zip-slip blocked: {member}")
                    zf.extractall(str(dst))
                    names = zf.namelist()
                logger.info("file_unzip", output=str(dst), files=len(names))
                return ToolResult(
                    success=True,
                    data={"extracted_to": str(dst), "file_count": len(names), "files": names[:50]},
                )

            elif action == "mkdir":
                p.mkdir(parents=True, exist_ok=True)
                logger.info("mkdir", path=str(p))
                return ToolResult(success=True, data={"created": str(p)})

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as exc:
            logger.error("file_manager_failed", action=action, path=path, error=str(exc))
            return ToolResult(success=False, error=f"File manager '{action}' failed: {exc}")


# ── Destructive operations — separate tools with requires_confirmation ────────


class FileMoveTool(BaseTool):
    """Move/rename a file or directory. Requires confirmation."""

    name = "file_move"
    description = (
        "Move or rename a file or directory. This is a destructive operation "
        "and requires confirmation."
    )
    requires_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path."},
            "destination": {"type": "string", "description": "Destination path."},
        },
        "required": ["source", "destination"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir

    async def execute(self, source: str, destination: str) -> ToolResult:
        try:
            root = Path(self._output_dir).resolve()
            src = (root / source).resolve()
            dst = (root / destination).resolve()

            if not src.is_relative_to(root):
                return ToolResult(success=False, error=f"Source path escapes output directory: {source}")
            if not dst.is_relative_to(root):
                return ToolResult(success=False, error=f"Destination path escapes output directory: {destination}")

            if not src.exists():
                return ToolResult(success=False, error=f"Source not found: {source}")

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

            logger.info("file_moved", src=str(src), dst=str(dst))
            return ToolResult(success=True, data={"moved": str(src), "to": str(dst)})

        except Exception as exc:
            logger.error("file_move_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to move: {exc}")


class FileDeleteTool(BaseTool):
    """Delete a file or directory. Requires confirmation."""

    name = "file_delete"
    description = (
        "Delete a file or directory (recursively for directories). "
        "This is a destructive operation and requires confirmation."
    )
    requires_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to delete."},
        },
        "required": ["path"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir

    async def execute(self, path: str) -> ToolResult:
        try:
            root = Path(self._output_dir).resolve()
            p = (root / path).resolve()

            if not p.is_relative_to(root):
                return ToolResult(success=False, error=f"Path escapes output directory: {path}")

            if not p.exists():
                return ToolResult(success=False, error=f"Not found: {path}")

            if p.is_dir():
                shutil.rmtree(str(p))
            else:
                p.unlink()

            logger.info("file_deleted", path=str(p))
            return ToolResult(success=True, data={"deleted": str(p)})

        except Exception as exc:
            logger.error("file_delete_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to delete: {exc}")
