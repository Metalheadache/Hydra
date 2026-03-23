"""
Code execution tools with security controls.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_PYTHON_TIMEOUT = 30
_SHELL_TIMEOUT = 15

# Only these shell commands are allowed
_ALLOWED_SHELL_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "wc", "grep", "find", "jq",
    "echo", "pwd", "date", "sort", "uniq", "cut", "awk", "sed",
    "tr", "xargs", "du", "stat",
})

# Shell metacharacters that could enable injection attacks
# These are rejected anywhere in the command, not just the first token
_SHELL_METACHARACTERS = re.compile(r'[|;&`$><()\n\r]')


class RunPythonTool(BaseTool):
    """Execute Python code in an isolated temp directory and return stdout.

    WARNING: Network access is NOT blocked. Code can make network calls.
    For production use, run in Docker with --network none.
    """

    name = "run_python"
    description = (
        "Execute Python code in a sandboxed subprocess. "
        "Returns stdout, stderr, and a list of any files created in the temp directory. "
        "SECURITY: code runs in a fresh temp directory with no persistent state. "
        "WARNING: Network access is NOT blocked. Code can make network calls. "
        "For production use, run in Docker with --network none."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Execution timeout in seconds (default {_PYTHON_TIMEOUT}).",
                "default": _PYTHON_TIMEOUT,
            },
        },
        "required": ["code"],
    }
    timeout_seconds = _PYTHON_TIMEOUT + 5

    async def execute(self, code: str, timeout: int = _PYTHON_TIMEOUT) -> ToolResult:
        # NOTE: Network access is not restricted at the OS level. The code subprocess
        # can freely make network calls. For true isolation, run in a container
        # with --network none or use seccomp/namespaces.
        tmp_dir = tempfile.mkdtemp(prefix="hydra_python_")
        try:
            script_path = Path(tmp_dir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmp_dir,
                # Restrict environment to minimal set
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": tmp_dir,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    success=False,
                    error=f"Python execution timed out after {timeout}s",
                )

            # Collect any files created (excluding the script itself)
            files_created = [
                str(p.relative_to(tmp_dir))
                for p in Path(tmp_dir).iterdir()
                if p.name != "script.py" and p.is_file()
            ]

            exit_code = proc.returncode
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            logger.info(
                "python_executed",
                exit_code=exit_code,
                stdout_len=len(stdout_text),
                files_created=files_created,
            )

            return ToolResult(
                success=(exit_code == 0),
                data={
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "exit_code": exit_code,
                    "files_created": files_created,
                },
                error=None if exit_code == 0 else f"Python exited with code {exit_code}:\n{stderr_text}",
            )

        except Exception as exc:
            logger.error("run_python_failed", error=str(exc))
            return ToolResult(success=False, error=f"Failed to execute Python code: {exc}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class RunShellTool(BaseTool):
    """Execute whitelisted shell commands and return output."""

    name = "run_shell"
    description = (
        "Execute shell commands. Only a safe whitelist of commands is allowed: "
        f"{', '.join(sorted(_ALLOWED_SHELL_COMMANDS))}. "
        "Shell metacharacters (|, ;, &, $, >, <, `, (, )) are rejected to prevent injection. "
        "Returns stdout and stderr."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command string to execute (must start with a whitelisted command).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Execution timeout in seconds (default {_SHELL_TIMEOUT}).",
                "default": _SHELL_TIMEOUT,
            },
        },
        "required": ["command"],
    }
    timeout_seconds = _SHELL_TIMEOUT + 5

    async def execute(self, command: str, timeout: int = _SHELL_TIMEOUT) -> ToolResult:
        stripped = command.strip()
        if not stripped:
            return ToolResult(success=False, error="Empty command.")

        # Security: reject any shell metacharacters anywhere in the command
        # This prevents injection via arguments (e.g., "ls; rm -rf /")
        if _SHELL_METACHARACTERS.search(stripped):
            logger.warning("shell_metacharacter_blocked", command=command)
            return ToolResult(
                success=False,
                error=(
                    "Command contains shell metacharacters (|, ;, &, $, >, <, `, (, )) "
                    "which are not allowed for security reasons."
                ),
            )

        # Parse command into tokens using shlex to avoid shell interpretation
        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            return ToolResult(success=False, error=f"Invalid command syntax: {exc}")

        if not tokens:
            return ToolResult(success=False, error="Empty command after parsing.")

        # Security: check the first token is whitelisted
        first_token = tokens[0]
        if first_token not in _ALLOWED_SHELL_COMMANDS:
            logger.warning("shell_command_blocked", command=command, first_token=first_token)
            return ToolResult(
                success=False,
                error=(
                    f"Command '{first_token}' is not in the allowed list. "
                    f"Allowed commands: {', '.join(sorted(_ALLOWED_SHELL_COMMANDS))}"
                ),
            )

        try:
            # Use create_subprocess_exec (not shell=True) to avoid shell interpretation
            proc = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(success=False, error=f"Shell command timed out after {timeout}s: {command!r}")

            exit_code = proc.returncode
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            logger.info("shell_executed", command=command, exit_code=exit_code)
            return ToolResult(
                success=(exit_code == 0),
                data={"stdout": stdout_text, "stderr": stderr_text, "exit_code": exit_code},
                error=None if exit_code == 0 else f"Shell exited with code {exit_code}:\n{stderr_text}",
            )
        except Exception as exc:
            logger.error("run_shell_failed", command=command, error=str(exc))
            return ToolResult(success=False, error=f"Failed to execute shell command: {exc}")
