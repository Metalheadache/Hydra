"""
Screenshot tool: capture web pages as PNG images using Playwright.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import uuid
from pathlib import Path

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools._security import ensure_dir, is_ssrf_target, safe_write_path
from hydra_agents.tools.base import BaseTool

logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = "./hydra_output"
_BROWSER_TIMEOUT_MS = 30_000
_TOTAL_TIMEOUT_S = 30.0

try:
    from playwright.async_api import async_playwright as _async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _async_playwright = None  # type: ignore[assignment]
    _PLAYWRIGHT_AVAILABLE = False


class ScreenshotTool(BaseTool):
    """Capture a screenshot of a URL and save it as a PNG image."""

    name = "take_screenshot"
    description = (
        "Navigate to a URL and capture a screenshot as a PNG image. "
        "Supports full-page capture, viewport sizing, and CSS selector targeting. "
        "SSRF-protected: private/loopback addresses are blocked for both the initial URL "
        "and any redirects or sub-resources the page loads. "
        "file:// URLs must point inside the configured output directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to screenshot (http://, https://, or file:// inside output_directory).",
            },
            "output_filename": {
                "type": "string",
                "description": "Output PNG filename. Defaults to screenshot_{uuid}.png.",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture the full scrollable page (default false).",
                "default": False,
            },
            "width": {
                "type": "integer",
                "description": "Viewport width in pixels (default 1280).",
                "default": 1280,
            },
            "height": {
                "type": "integer",
                "description": "Viewport height in pixels (default 720).",
                "default": 720,
            },
            "wait_seconds": {
                "type": "number",
                "description": "Seconds to wait after page load before capturing (default 2.0).",
                "default": 2.0,
            },
            "selector": {
                "type": "string",
                "description": "Optional CSS selector — screenshot only the matching element.",
            },
        },
        "required": ["url"],
    }
    timeout_seconds = 35

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir

    async def execute(
        self,
        url: str,
        output_filename: str | None = None,
        full_page: bool = False,
        width: int = 1280,
        height: int = 720,
        wait_seconds: float = 2.0,
        selector: str | None = None,
    ) -> ToolResult:
        if not _PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                error=(
                    "playwright is not installed. "
                    "Run: pip install -r requirements-screenshot.txt && playwright install chromium"
                ),
            )

        # Validate file:// paths stay within output_directory.
        # Percent-decode the path so "file:///tmp/my%20file.html" resolves correctly.
        if url.startswith("file://"):
            local_path = urllib.parse.unquote(url[len("file://"):])
            resolved_root = Path(self._output_dir).resolve()
            resolved_file = Path(local_path).resolve()
            if not resolved_file.is_relative_to(resolved_root):
                return ToolResult(
                    success=False,
                    error=f"file:// URL must point inside output_directory ({self._output_dir})",
                )
        else:
            if await is_ssrf_target(url):
                return ToolResult(
                    success=False,
                    error=f"SSRF blocked: requests to private/loopback addresses are not allowed ({url})",
                )

        if output_filename is None:
            output_filename = f"screenshot_{uuid.uuid4().hex[:12]}.png"
        if not output_filename.endswith(".png"):
            output_filename = output_filename + ".png"

        output_path = ensure_dir(self._output_dir)
        filepath = safe_write_path(output_path, output_filename)
        if filepath is None:
            return ToolResult(success=False, error="Path traversal blocked")

        # _capture is a nested coroutine so asyncio.wait_for can cancel it cleanly.
        # Returns an error string on failure, None on success.
        async def _capture() -> str | None:
            async with _async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": width, "height": height},
                    )
                    page = await context.new_page()
                    page.set_default_timeout(_BROWSER_TIMEOUT_MS)

                    # Guard against SSRF via open redirect: intercept every request
                    # the page makes (navigation, sub-resources, redirects) and abort
                    # any that resolve to a private/loopback address.
                    async def _block_ssrf(route, request):
                        if await is_ssrf_target(request.url):
                            await route.abort("blockedbyclient")
                        else:
                            await route.continue_()

                    await page.route("**/*", _block_ssrf)
                    await page.goto(url, wait_until="networkidle")
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                    if selector:
                        element = await page.query_selector(selector)
                        if element is None:
                            return f"CSS selector {selector!r} matched no elements on {url}"
                        await element.screenshot(path=str(filepath))
                    else:
                        await page.screenshot(path=str(filepath), full_page=full_page)
                finally:
                    # asyncio.shield ensures browser.close() completes even when
                    # this coroutine is cancelled by asyncio.wait_for on timeout,
                    # preventing orphaned Chromium processes.
                    try:
                        await asyncio.shield(browser.close())
                    except Exception:
                        pass
            return None

        try:
            error = await asyncio.wait_for(_capture(), timeout=_TOTAL_TIMEOUT_S)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Screenshot timed out after {int(_TOTAL_TIMEOUT_S)}s")
        except Exception as exc:
            logger.error("screenshot_failed", url=url, error=str(exc))
            return ToolResult(success=False, error=f"Screenshot failed: {exc}")

        if error is not None:
            return ToolResult(success=False, error=error)

        logger.info("screenshot_saved", filepath=str(filepath), url=url)
        return ToolResult(
            success=True,
            data={
                "message": f"Screenshot saved to {filepath}",
                "filepath": str(filepath),
                "files": [str(filepath)],
                "url": url,
            },
        )
