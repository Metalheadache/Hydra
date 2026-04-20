"""
Regex tool: search, extract, replace, and split text using regular expressions.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import difflib
import re
from pathlib import Path

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools._security import safe_read_path
from hydra_agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = "./hydra_output"
_MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_INLINE_BYTES = 1 * 1024 * 1024  # 1 MB
_REDOS_TIMEOUT = 5.0                  # seconds
_MAX_DIFF_CHARS = 8_000               # cap diff output to avoid overwhelming the LLM

_FLAG_MAP = {
    "ignorecase": re.IGNORECASE,
    "multiline": re.MULTILINE,
    "dotall": re.DOTALL,
}

# Module-level executor so leaked ReDoS threads are bounded.
# Python threads cannot be force-killed; on timeout the thread continues running
# until it completes or the process exits.  max_workers=2 caps the leak to at
# most two concurrent stuck threads.
_REGEX_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="hydra_regex",
)


def _build_flags(flags: list[str] | None) -> int:
    result = 0
    for f in (flags or []):
        flag = _FLAG_MAP.get(f.lower())
        if flag is not None:
            result |= flag
    return result


def _silence_future_exception(fut: asyncio.Future) -> None:
    """Drain any exception from an abandoned future to suppress Python's warning.

    When _run_with_timeout times out, the shielded inner future continues
    running but nothing awaits it.  Without this callback Python logs
    "Future exception was never retrieved" when the thread eventually raises.
    """
    if not fut.cancelled():
        fut.exception()


async def _run_with_timeout(fn, *args, timeout: float = _REDOS_TIMEOUT):
    """Execute fn(*args) in the regex thread pool; raise concurrent.futures.TimeoutError on timeout.

    Uses asyncio.shield so the underlying thread is not cancelled — it runs to
    completion or is abandoned when the process exits.  max_workers=2 caps the
    number of leaked threads.  A done callback suppresses log noise from
    abandoned threads that raise exceptions.
    """
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_REGEX_EXECUTOR, fn, *args)
    fut.add_done_callback(_silence_future_exception)
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except asyncio.TimeoutError:
        raise concurrent.futures.TimeoutError(
            f"Regex execution timed out after {timeout}s (possible ReDoS pattern)"
        )


class RegexTool(BaseTool):
    """Search, extract, replace, or split text using regular expressions."""

    name = "regex"
    description = (
        "Apply a regular expression to inline text or a file. "
        "Actions: search (find matches with line/column and context), "
        "extract (return captured groups; non-participating optional groups are omitted), "
        "replace (substitute pattern; writes file back when file_path is given), "
        "split (split text on pattern). "
        "ReDoS-protected with a 5-second execution timeout. "
        "File paths must be inside the configured output directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern.",
            },
            "action": {
                "type": "string",
                "enum": ["search", "extract", "replace", "split"],
                "description": "Operation to perform on the text.",
            },
            "text": {
                "type": "string",
                "description": "Inline text to process. Mutually exclusive with file_path.",
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Path to a text file inside output_directory to process. "
                    "Mutually exclusive with text."
                ),
            },
            "replacement": {
                "type": "string",
                "description": "Replacement string (required for the replace action).",
            },
            "flags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["ignorecase", "multiline", "dotall"],
                },
                "description": "Optional list of regex flags.",
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum number of matches/parts to return (default 100).",
                "default": 100,
            },
        },
        "required": ["pattern", "action"],
    }

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir

    async def execute(
        self,
        pattern: str,
        action: str,
        text: str | None = None,
        file_path: str | None = None,
        replacement: str | None = None,
        flags: list[str] | None = None,
        max_matches: int = 100,
    ) -> ToolResult:
        # Validate pattern early — gives a clear error before touching any input.
        re_flags = _build_flags(flags)
        try:
            compiled = re.compile(pattern, re_flags)
        except re.error as exc:
            return ToolResult(success=False, error=f"Invalid regex pattern: {exc}")

        if action not in {"search", "extract", "replace", "split"}:
            return ToolResult(
                success=False,
                error=f"Unknown action {action!r}. Choose from: search, extract, replace, split",
            )

        if action == "replace" and replacement is None:
            return ToolResult(success=False, error="replacement is required for the replace action")

        if text is not None and file_path is not None:
            return ToolResult(success=False, error="Provide either text or file_path, not both")

        # Resolve input
        source_file: Path | None = None
        if file_path is not None:
            try:
                resolved = safe_read_path(
                    file_path,
                    allowed_roots=[self._output_dir],
                    must_exist=True,
                )
            except ValueError as exc:
                return ToolResult(success=False, error=str(exc))

            size = resolved.stat().st_size
            if size > _MAX_FILE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"File too large: {size} bytes (max {_MAX_FILE_BYTES // (1024 * 1024)} MB)",
                )
            try:
                raw_bytes = resolved.read_bytes()
                if b"\x00" in raw_bytes:
                    return ToolResult(success=False, error="Binary files are not supported")
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return ToolResult(
                    success=False,
                    error="File is not valid UTF-8 text (binary files not supported)",
                )
            source_file = resolved

        elif text is not None:
            if len(text.encode("utf-8")) > _MAX_INLINE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"Inline text too large (max {_MAX_INLINE_BYTES // 1024} KB)",
                )
            content = text

        else:
            return ToolResult(success=False, error="Provide either text or file_path")

        try:
            if action == "search":
                return await self._search(compiled, content, max_matches)
            elif action == "extract":
                return await self._extract(compiled, content, max_matches)
            elif action == "replace":
                return await self._replace(compiled, content, replacement, source_file)
            else:  # split
                return await self._split(compiled, content, max_matches)

        except concurrent.futures.TimeoutError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("regex_failed", action=action, pattern=pattern, error=str(exc))
            return ToolResult(success=False, error=f"Regex operation failed: {exc}")

    # ── Action implementations ─────────────────────────────────────────────────

    async def _search(
        self, compiled: re.Pattern, content: str, max_matches: int
    ) -> ToolResult:
        lines = content.splitlines()

        def _find():
            matches = []
            for m in compiled.finditer(content):
                if len(matches) >= max_matches:
                    break
                before = content[: m.start()]
                line_num = before.count("\n") + 1
                col = m.start() - (before.rfind("\n") + 1)
                idx = line_num - 1
                matches.append(
                    {
                        "line": line_num,
                        "column": col,
                        "match": m.group(0),
                        "context_before": lines[idx - 1] if idx > 0 else None,
                        "context_line": lines[idx] if idx < len(lines) else "",
                        "context_after": lines[idx + 1] if idx + 1 < len(lines) else None,
                    }
                )
            return matches

        matches = await _run_with_timeout(_find)
        return ToolResult(
            success=True,
            data={
                "matches": matches,
                "count": len(matches),
                "truncated": len(matches) >= max_matches,
            },
        )

    async def _extract(
        self, compiled: re.Pattern, content: str, max_matches: int
    ) -> ToolResult:
        def _find():
            results = []
            for m in compiled.finditer(content):
                if len(results) >= max_matches:
                    break
                if compiled.groups:
                    # Filter out None: non-participating optional groups (e.g. (a)|(b))
                    # are omitted rather than returned as null to keep output clean.
                    groups: dict = {
                        str(i + 1): g
                        for i, g in enumerate(m.groups())
                        if g is not None
                    }
                    if compiled.groupindex:
                        groups.update(
                            {
                                name: m.group(name)
                                for name in compiled.groupindex
                                if m.group(name) is not None
                            }
                        )
                else:
                    groups = {"0": m.group(0)}
                results.append({"match": m.group(0), "groups": groups})
            return results

        results = await _run_with_timeout(_find)
        return ToolResult(
            success=True,
            data={
                "matches": results,
                "count": len(results),
                "truncated": len(results) >= max_matches,
            },
        )

    async def _replace(
        self,
        compiled: re.Pattern,
        content: str,
        replacement: str,
        source_file: Path | None,
    ) -> ToolResult:
        def _do_replace():
            return compiled.sub(replacement, content)

        new_content = await _run_with_timeout(_do_replace)

        if source_file is not None:
            original_lines = content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = list(
                difflib.unified_diff(
                    original_lines,
                    new_lines,
                    fromfile=str(source_file),
                    tofile=str(source_file),
                    n=2,
                )
            )
            diff_text = "".join(diff)
            if len(diff_text) > _MAX_DIFF_CHARS:
                diff_text = diff_text[:_MAX_DIFF_CHARS] + "\n... [diff truncated]"
            added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
            removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))

            # Atomic write: write to .tmp then replace so a crash mid-write does
            # not leave the original file partially overwritten.
            tmp = source_file.with_name(source_file.name + ".tmp")
            try:
                tmp.write_text(new_content, encoding="utf-8")
                tmp.replace(source_file)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise

            logger.info("regex_replace_file", filepath=str(source_file), added=added, removed=removed)
            return ToolResult(
                success=True,
                data={
                    "filepath": str(source_file),
                    "diff_summary": f"+{added} lines, -{removed} lines",
                    "diff": diff_text,
                    "bytes_written": len(new_content.encode("utf-8")),
                },
            )

        return ToolResult(success=True, data={"result": new_content})

    async def _split(
        self, compiled: re.Pattern, content: str, max_matches: int
    ) -> ToolResult:
        def _do_split():
            return compiled.split(content)

        parts = await _run_with_timeout(_do_split)
        truncated = len(parts) > max_matches
        if truncated:
            parts = parts[:max_matches]
        return ToolResult(
            success=True,
            data={"parts": parts, "count": len(parts), "truncated": truncated},
        )
