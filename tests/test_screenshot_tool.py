"""
Tests for ScreenshotTool.
"""

from __future__ import annotations

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
