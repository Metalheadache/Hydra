"""
Shared security helpers for Hydra tools.

Consolidates path-safety and URL-safety logic that was previously duplicated
across file_tools.py and research_tools.py.  New tools should import from
here instead of re-implementing guards.

Existing tools (file_tools, research_tools) can migrate to these at their
own pace — the module-level functions they already use are intentionally
kept API-compatible.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# ── Default output directory ──────────────────────────────────────────────────

_DEFAULT_OUTPUT_DIR = os.environ.get("HYDRA_OUTPUT_DIRECTORY", "./hydra_output")


# ── Path safety ───────────────────────────────────────────────────────────────
# Mirrors the logic from file_tools._ensure_output_dir / _safe_filepath,
# but adds support for *reading* files outside the output directory (within
# an explicit allowed-roots list).

def ensure_dir(directory: str | Path) -> Path:
    """Create directory if it doesn't exist and return the Path.

    Drop-in replacement for file_tools._ensure_output_dir.
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_write_path(output_dir: str | Path, filename: str) -> Path | None:
    """Resolve *filename* under *output_dir* and verify no path traversal.

    Returns None if the resolved path escapes the output directory.
    Drop-in replacement for file_tools._safe_filepath.
    """
    resolved_root = Path(output_dir).resolve()
    filepath = (Path(output_dir) / filename).resolve()
    if not filepath.is_relative_to(resolved_root):
        logger.warning("path_traversal_blocked", filename=filename, output_dir=str(output_dir))
        return None
    return filepath


def safe_read_path(
    file_path: str,
    *,
    allowed_roots: list[str | Path] | None = None,
    must_exist: bool = True,
) -> Path:
    """Validate a file path for *reading*.

    Unlike safe_write_path (which constrains to the output dir), read paths
    may come from anywhere the user uploaded or the pipeline generated.
    We still enforce:
    - The path resolves to a real location (no dangling symlink tricks)
    - If *allowed_roots* is given, the resolved path must be under one of them
    - If *must_exist*, the file must actually exist

    Raises:
        ValueError  on any validation failure (callers catch and return ToolResult)
    """
    resolved = Path(file_path).resolve()

    if must_exist and not resolved.exists():
        raise ValueError(f"File not found: {file_path}")

    if allowed_roots:
        roots = [Path(r).resolve() for r in allowed_roots]
        if not any(resolved.is_relative_to(root) for root in roots):
            raise ValueError(
                f"Path {file_path!r} is outside allowed directories: "
                f"{[str(r) for r in roots]}"
            )

    return resolved


# ── URL / SSRF safety ─────────────────────────────────────────────────────────
# Extracted from research_tools.py so that screenshot_tools, ocr_tools, or
# any future tool that fetches URLs can reuse the same guards.

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback"}


def is_ssrf_target_sync(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback address.

    Sync version — suitable for non-async contexts or pre-checks.
    Mirrors research_tools._is_ssrf_target.
    """
    import socket

    import httpx

    try:
        parsed = httpx.URL(url)
        host = parsed.host
    except Exception:
        return False

    if host.lower() in _BLOCKED_HOSTNAMES:
        return True

    bare_host = host.strip("[]")
    try:
        addr = ipaddress.ip_address(bare_host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass

    try:
        resolved = socket.getaddrinfo(bare_host, None)
        for _family, _, _, _, sockaddr in resolved:
            try:
                addr = ipaddress.ip_address(sockaddr[0])
                if any(addr in net for net in _BLOCKED_NETWORKS):
                    return True
            except ValueError:
                pass
    except Exception:
        pass

    return False


async def is_ssrf_target(url: str) -> bool:
    """Async version — uses loop.getaddrinfo() for non-blocking DNS.

    Mirrors research_tools._is_ssrf_target_async.
    """
    import asyncio

    import httpx

    try:
        parsed = httpx.URL(url)
        host = parsed.host
    except Exception:
        return False

    if host.lower() in _BLOCKED_HOSTNAMES:
        return True

    bare_host = host.strip("[]")
    try:
        addr = ipaddress.ip_address(bare_host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        resolved = await loop.getaddrinfo(bare_host, None)
        for _family, _, _, _, sockaddr in resolved:
            try:
                addr = ipaddress.ip_address(sockaddr[0])
                if any(addr in net for net in _BLOCKED_NETWORKS):
                    return True
            except ValueError:
                pass
    except Exception:
        pass

    return False
