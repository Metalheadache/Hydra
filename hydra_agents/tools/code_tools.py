"""
Code execution tools with security controls.
"""

from __future__ import annotations

import asyncio
import platform
import re
import shlex
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_PYTHON_TIMEOUT = 30
_SHELL_TIMEOUT = 15

# Cached once at import time so every tool call doesn't re-scan PATH.
_UNSHARE_PATH: str | None = shutil.which("unshare")

# Warn at most once per process about non-Linux platforms (not on every call).
_non_linux_warned: bool = False


def _network_sandbox_prefix(sandbox_network: bool) -> list[str] | None:
    """Build the unshare prefix for network-namespace sandboxing.

    Args:
        sandbox_network: True when the caller wants network isolation.

    Returns:
        - ``[]``   — sandboxing disabled; proceed normally.
        - non-empty list — prepend this to the subprocess argv.
        - ``None`` — sandboxing was requested but is unavailable;
                     the caller **must** fail-closed (return an error).

    Implementation notes:
        ``unshare --user --net --`` creates a new *user* namespace (so no
        CAP_SYS_ADMIN is needed) and a network namespace inside it.  The child
        process has no network interfaces beyond loopback and cannot make
        outbound calls.  Requires Linux ≥ 3.8 with unprivileged user namespaces
        enabled (``kernel.unprivileged_userns_clone=1`` on Debian/Ubuntu; on
        most other distros this is the default).
    """
    global _non_linux_warned

    if not sandbox_network:
        return []

    if platform.system() != "Linux":
        if not _non_linux_warned:
            logger.warning(
                "network_sandbox_unavailable",
                reason="HYDRA_SANDBOX_NETWORK requires Linux; not supported on this platform",
            )
            _non_linux_warned = True
        return None  # fail-closed

    if _UNSHARE_PATH is None:
        logger.error(
            "network_sandbox_unavailable",
            reason="`unshare` not found in PATH; install util-linux or use the Docker image",
        )
        return None  # fail-closed

    return [_UNSHARE_PATH, "--user", "--net", "--"]


# Only these shell commands are allowed
_ALLOWED_SHELL_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "wc", "grep", "find", "jq",
    "echo", "pwd", "date", "sort", "uniq", "cut", "awk", "sed",
    "tr", "xargs", "du", "stat",
})

# Shell metacharacters that could enable injection attacks
# These are rejected anywhere in the command, not just the first token
_SHELL_METACHARACTERS = re.compile(r'[|;&`$><()\n\r]')


# Dangerous env vars to strip from subprocess environment
_DANGEROUS_ENV_VARS = frozenset({
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_CLIENT_SECRET",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "HYDRA_API_KEY",
})


class RunPythonTool(BaseTool):
    """Execute Python code in an isolated temp directory and return stdout.

    Network access is blocked when sandbox_network=True (Linux only, via
    ``unshare --user --net``).  For full container-level isolation, run Hydra
    in Docker and set HYDRA_SANDBOX_NETWORK=true.
    """

    name = "run_python"
    description = (
        "Execute Python code in a sandboxed subprocess. "
        "Returns stdout, stderr, and a list of any files created in the temp directory. "
        "SECURITY: code runs in a fresh temp directory with no persistent state. "
        "Network access is blocked when HYDRA_SANDBOX_NETWORK=true (Linux only); "
        "otherwise network calls are permitted — run in Docker for full isolation."
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
    requires_confirmation = True  # Arbitrary code execution requires user approval

    def __init__(self, sandbox_network: bool = False, output_dir: str = "./hydra_output") -> None:
        self._sandbox_network = sandbox_network
        self._output_dir = output_dir

    async def execute(self, code: str, timeout: int = _PYTHON_TIMEOUT) -> ToolResult:
        tmp_dir = tempfile.mkdtemp(prefix="hydra_python_")
        try:
            script_path = Path(tmp_dir) / "script.py"
            script_path.write_text(code, encoding="utf-8")

            # Build subprocess environment: minimal set, stripping dangerous credentials
            safe_env = {
                "PATH": "/usr/bin:/bin",
                "HOME": tmp_dir,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            # Also strip from any inherited env (though we build from scratch here,
            # this makes the intent explicit and guards against future changes)
            for var in _DANGEROUS_ENV_VARS:
                safe_env.pop(var, None)

            # Optionally wrap in a network namespace to block outbound calls
            sandbox = _network_sandbox_prefix(self._sandbox_network)
            if sandbox is None:
                return ToolResult(
                    success=False,
                    error=(
                        "Network sandboxing is enabled (HYDRA_SANDBOX_NETWORK=true) but "
                        "cannot be enforced on this host — `unshare` is missing or this "
                        "platform is not Linux. Refusing to run without the requested sandbox."
                    ),
                )
            cmd = [*sandbox, sys.executable, str(script_path)]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmp_dir,
                env=safe_env,
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
            # Security: skip symlinks to prevent exfiltration of sensitive files
            created_files = [
                p.name
                for p in Path(tmp_dir).iterdir()
                if p.name != "script.py" and p.is_file() and not p.is_symlink()
            ]

            exit_code = proc.returncode
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # H4: Copy created files to output_directory before temp dir is cleaned up
            # Prefix filenames with a short unique ID to prevent overwrites across runs
            # (os imported at module level)
            import uuid as _uuid
            run_prefix = _uuid.uuid4().hex[:8]
            output_dir = Path(self._output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            created_files_paths: list[str] = []
            for fname in created_files:
                src = Path(tmp_dir) / fname
                if src.exists():
                    dest = output_dir / f"{run_prefix}_{fname}"
                    shutil.copy2(str(src), str(dest))
                    created_files_paths.append(str(dest))

            logger.info(
                "python_executed",
                exit_code=exit_code,
                stdout_len=len(stdout_text),
                files_created=created_files_paths,
            )

            return ToolResult(
                success=(exit_code == 0),
                data={
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "exit_code": exit_code,
                    "files_created": created_files_paths,
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

    def __init__(self, sandbox_network: bool = False, output_dir: str = "./hydra_output") -> None:
        self._sandbox_network = sandbox_network
        self._output_dir = output_dir

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

        # Security: block absolute paths and parent traversal in arguments
        # Prevents reading arbitrary host files (e.g., "cat /etc/passwd")
        for arg in tokens[1:]:
            if arg.startswith("/") or ".." in arg:
                logger.warning("shell_path_blocked", command=command, arg=arg)
                return ToolResult(
                    success=False,
                    error=(
                        f"Absolute paths and '..' traversal are not allowed in shell arguments. "
                        f"Blocked argument: '{arg}'"
                    ),
                )

        try:
            # Use a safe CWD (output dir) rather than inheriting the process CWD
            safe_cwd = self._output_dir
            # Build subprocess environment: strip dangerous credentials
            safe_env = {k: v for k, v in os.environ.items() if k not in _DANGEROUS_ENV_VARS}
            # Optionally wrap in a network namespace to block outbound calls
            sandbox = _network_sandbox_prefix(self._sandbox_network)
            if sandbox is None:
                return ToolResult(
                    success=False,
                    error=(
                        "Network sandboxing is enabled (HYDRA_SANDBOX_NETWORK=true) but "
                        "cannot be enforced on this host — `unshare` is missing or this "
                        "platform is not Linux. Refusing to run without the requested sandbox."
                    ),
                )
            # Use create_subprocess_exec (not shell=True) to avoid shell interpretation
            proc = await asyncio.create_subprocess_exec(
                *sandbox, *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=safe_cwd,
                env=safe_env,
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
