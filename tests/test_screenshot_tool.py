"""
Tests for ScreenshotTool.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra_agents.tools.screenshot_tools import ScreenshotTool


# ── SSRF / URL validation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ssrf_localhost_blocked():
    """Requests to localhost must be blocked before any browser launch."""
    tool = ScreenshotTool()
    with patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True):
        result = await tool.execute(url="http://localhost/admin")
    assert not result.success
    assert "ssrf" in (result.error or "").lower() or "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_ssrf_private_ip_blocked():
    """Requests to private IP ranges must be blocked."""
    tool = ScreenshotTool()
    with patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True):
        result = await tool.execute(url="http://192.168.1.1/")
    assert not result.success
    assert "ssrf" in (result.error or "").lower() or "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_ssrf_loopback_ip_blocked():
    """Direct loopback IP must be blocked."""
    tool = ScreenshotTool()
    with patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True):
        result = await tool.execute(url="http://127.0.0.1:8080/secret")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_file_url_outside_output_dir_blocked(tmp_path):
    """file:// URLs pointing outside output_directory must be rejected."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    tool = ScreenshotTool(output_dir=str(output_dir))
    with patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True):
        result = await tool.execute(url="file:///etc/passwd")
    assert not result.success
    assert "output_directory" in (result.error or "") or "file://" in (result.error or "")


@pytest.mark.asyncio
async def test_file_url_inside_output_dir_passes_validation(tmp_path):
    """file:// URLs inside output_directory pass the path check (browser call is mocked)."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    local_file = output_dir / "page.html"
    local_file.write_text("<html><body>hi</body></html>", encoding="utf-8")

    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(
            url=f"file://{local_file}",
            output_filename="local_shot.png",
        )

    assert result.success
    assert result.data["filepath"].endswith("local_shot.png")


# ── Basic invocation (mocked browser) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_basic_screenshot_mocked(tmp_path):
    """Successful screenshot returns filepath, message, and files list."""
    output_dir = tmp_path / "screenshots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(url="https://example.com", output_filename="test_shot.png")

    assert result.success
    assert result.data["filepath"].endswith("test_shot.png")
    assert "files" in result.data
    assert len(result.data["files"]) == 1
    assert result.data["url"] == "https://example.com"
    mock_page.goto.assert_called_once()
    mock_page.screenshot.assert_called_once()


@pytest.mark.asyncio
async def test_default_filename_generated(tmp_path):
    """When output_filename is omitted, a timestamp-based name is generated."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(url="https://example.com")

    assert result.success
    assert result.data["filepath"].endswith(".png")
    assert "screenshot_" in Path(result.data["filepath"]).name


@pytest.mark.asyncio
async def test_selector_not_found_returns_error(tmp_path):
    """When selector matches nothing, execute returns an error ToolResult."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(
            url="https://example.com",
            selector="#nonexistent",
            output_filename="selector_shot.png",
        )

    assert not result.success
    assert "#nonexistent" in (result.error or "") or "selector" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_playwright_not_installed_returns_error():
    """When playwright is not available, execute returns a helpful error."""
    tool = ScreenshotTool()
    with patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", False):
        result = await tool.execute(url="https://example.com")
    assert not result.success
    assert "playwright" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_blocked(tmp_path):
    """Filenames with path traversal components must be rejected."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(
            url="https://example.com",
            output_filename="../evil.png",
        )

    assert not result.success
    assert "traversal" in (result.error or "").lower() or result.error is not None


# ── SSRF redirect interceptor ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ssrf_redirect_interceptor_blocks_private_ip(tmp_path):
    """Route interceptor must abort any request to a private IP (guards SSRF via redirect)."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    captured_handler = None

    async def _capture_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    mock_page.route = AsyncMock(side_effect=_capture_route)
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(url="https://example.com", output_filename="shot.png")

    assert result.success
    assert captured_handler is not None, "page.route() was never called"

    # Simulate the browser following a redirect to an AWS metadata endpoint (link-local)
    mock_route = AsyncMock()
    mock_request = MagicMock()
    mock_request.url = "http://169.254.169.254/latest/meta-data/"
    await captured_handler(mock_route, mock_request)
    mock_route.abort.assert_called_once_with("blockedbyclient")

    # Simulate a request to a 10.x private address
    mock_route2 = AsyncMock()
    mock_request2 = MagicMock()
    mock_request2.url = "http://10.0.0.1/internal"
    await captured_handler(mock_route2, mock_request2)
    mock_route2.abort.assert_called_once_with("blockedbyclient")


# ── timeout path ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_returns_error(tmp_path):
    """asyncio.wait_for timeout must produce a ToolResult error, not an exception."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    async def mock_wait_for(coro, timeout):
        coro.close()   # prevent "coroutine was never awaited" warning
        raise asyncio.TimeoutError

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools.asyncio.wait_for", mock_wait_for),
    ):
        result = await tool.execute(url="https://example.com")

    assert not result.success
    assert "timed out" in (result.error or "").lower()


# ── file:// percent-encoding ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_url_percent_encoded_path(tmp_path):
    """Percent-encoded file:// paths must be decoded before path validation."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    # Create a file whose name contains a space (encoded as %20 in URL)
    html_file = output_dir / "my file.html"
    html_file.write_text("<html><body>hello</body></html>", encoding="utf-8")

    tool = ScreenshotTool(output_dir=str(output_dir))
    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    encoded_url = f"file://{output_dir}/my%20file.html"

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result = await tool.execute(url=encoded_url, output_filename="encoded_shot.png")

    assert result.success, f"Expected success but got: {result.error}"


# ── uuid filename ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_filename_uses_uuid(tmp_path):
    """Auto-generated filenames must use a UUID fragment, not a timestamp."""
    output_dir = tmp_path / "shots"
    output_dir.mkdir()
    tool = ScreenshotTool(output_dir=str(output_dir))

    mock_page = _make_mock_page()
    mock_pw = _make_mock_pw(mock_page)

    with (
        patch("hydra_agents.tools.screenshot_tools._PLAYWRIGHT_AVAILABLE", True),
        patch("hydra_agents.tools.screenshot_tools._async_playwright", return_value=_AsyncCM(mock_pw)),
    ):
        result1 = await tool.execute(url="https://example.com")
        result2 = await tool.execute(url="https://example.com")

    assert result1.success and result2.success
    # Two calls must produce different filenames
    assert result1.data["filepath"] != result2.data["filepath"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_page() -> AsyncMock:
    page = AsyncMock()
    page.goto = AsyncMock()
    page.screenshot = AsyncMock()
    page.query_selector = AsyncMock(return_value=AsyncMock())
    page.set_default_timeout = MagicMock()
    return page


def _make_mock_pw(mock_page: AsyncMock) -> AsyncMock:
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    return mock_pw


class _AsyncCM:
    """Minimal async context manager wrapping a mock playwright instance."""

    def __init__(self, pw) -> None:
        self._pw = pw

    async def __aenter__(self):
        return self._pw

    async def __aexit__(self, *args):
        return False
