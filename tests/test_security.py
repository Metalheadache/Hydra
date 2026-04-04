"""
Security tests for shell injection and path traversal vulnerabilities.
"""

import os
import tempfile
from pathlib import Path

import pytest

from hydra_agents.tools.code_tools import RunShellTool
from hydra_agents.tools.file_tools import WriteMarkdownTool, WriteJsonTool, WriteCsvTool, WriteCodeTool


# ── Shell Injection Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shell_injection_semicolon_blocked():
    """Semicolon injection (cmd; malicious) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo hello; rm -rf /tmp/test")
    assert not result.success
    assert "metacharacter" in (result.error or "").lower() or "not allowed" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_shell_injection_pipe_blocked():
    """Pipe injection (cmd | malicious) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo hello | cat /etc/passwd")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_ampersand_blocked():
    """Background execution (&) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo hello & evil_command")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_backtick_blocked():
    """Backtick substitution must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo `whoami`")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_dollar_subshell_blocked():
    """Dollar subshell substitution $(cmd) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo $(whoami)")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_redirect_output_blocked():
    """Output redirection (>) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo hello > /tmp/evil.txt")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_redirect_input_blocked():
    """Input redirection (<) must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("cat < /etc/passwd")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_and_and_blocked():
    """Double-ampersand (&&) injection must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("echo ok && evil_cmd")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_injection_double_pipe_blocked():
    """Double-pipe (||) injection must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("false || evil_cmd")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_non_whitelisted_command_blocked():
    """Non-whitelisted commands must always be blocked."""
    tool = RunShellTool()
    result = await tool.execute("rm -rf /")
    assert not result.success
    assert "not in the allowed list" in (result.error or "")


@pytest.mark.asyncio
async def test_shell_whitelisted_command_allowed():
    """Whitelisted commands with safe arguments should succeed."""
    tool = RunShellTool()
    result = await tool.execute("echo hello world")
    assert result.success
    assert "hello world" in (result.data or {}).get("stdout", "")


@pytest.mark.asyncio
async def test_shell_ls_command_allowed():
    """ls with a safe path should work."""
    tool = RunShellTool()
    result = await tool.execute("ls /tmp")
    # May or may not succeed depending on permissions, but should not be blocked by security
    assert result.error is None or "not in the allowed list" not in result.error
    assert result.error is None or "metacharacter" not in result.error.lower()


@pytest.mark.asyncio
async def test_shell_empty_command_blocked():
    """Empty command should return an error."""
    tool = RunShellTool()
    result = await tool.execute("")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_shell_parentheses_blocked():
    """Parentheses for subshell must be blocked."""
    tool = RunShellTool()
    result = await tool.execute("(echo bad)")
    assert not result.success


# ── Path Traversal Tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path_traversal_write_markdown_blocked():
    """../evil.md path traversal must be blocked in WriteMarkdownTool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteMarkdownTool(output_dir=tmpdir)
        result = await tool.execute(filename="../evil.md", content="pwned", output_dir=tmpdir)
        assert not result.success
        assert "traversal" in (result.error or "").lower()
        # File should NOT have been created outside tmpdir
        assert not Path(tmpdir).parent.joinpath("evil.md").exists()


@pytest.mark.asyncio
async def test_path_traversal_write_json_blocked():
    """../evil.json path traversal must be blocked in WriteJsonTool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteJsonTool(output_dir=tmpdir)
        result = await tool.execute(filename="../evil.json", data={"pwned": True}, output_dir=tmpdir)
        assert not result.success
        assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_write_csv_blocked():
    """../evil.csv path traversal must be blocked in WriteCsvTool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteCsvTool(output_dir=tmpdir)
        result = await tool.execute(
            filename="../evil.csv",
            headers=["a", "b"],
            rows=[["1", "2"]],
            output_dir=tmpdir,
        )
        assert not result.success
        assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_write_code_blocked():
    """../evil.py path traversal must be blocked in WriteCodeTool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteCodeTool(output_dir=tmpdir)
        result = await tool.execute(filename="../evil.py", code="import os", output_dir=tmpdir)
        assert not result.success
        assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_absolute_path_blocked():
    """Absolute path in filename must be blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteMarkdownTool(output_dir=tmpdir)
        result = await tool.execute(filename="/etc/evil.md", content="pwned", output_dir=tmpdir)
        # Should be blocked — /etc/evil.md is not under tmpdir
        assert not result.success
        assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_safe_filename_allowed():
    """Normal filenames should work fine."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteMarkdownTool(output_dir=tmpdir)
        result = await tool.execute(filename="safe_report.md", content="# Hello", output_dir=tmpdir)
        assert result.success
        written = Path(tmpdir) / "safe_report.md"
        assert written.exists()
        assert written.read_text() == "# Hello"


@pytest.mark.asyncio
async def test_path_traversal_nested_safe_path():
    """Nested filenames within output dir should work."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a subdirectory
        subdir = Path(tmpdir) / "subdir"
        subdir.mkdir()
        tool = WriteJsonTool(output_dir=str(subdir))
        result = await tool.execute(filename="data.json", data={"ok": True})
        assert result.success


@pytest.mark.asyncio
async def test_path_traversal_sibling_directory_blocked():
    """
    Sibling-directory attack must be blocked.

    output_dir = /tmp/hydra_output
    filename resolves to /tmp/hydra_output_evil/file.md

    A naive str.startswith() check would pass ("/tmp/hydra_output_evil".startswith("/tmp/hydra_output") == True).
    is_relative_to() correctly rejects this.
    """
    import tempfile, os
    # Use a fixed prefix pair to exercise the bypass
    base = Path(tempfile.mkdtemp(prefix="hydra_output"))
    try:
        # Create the sibling directory
        evil_dir = Path(str(base) + "_evil")
        evil_dir.mkdir(exist_ok=True)
        try:
            tool = WriteMarkdownTool(output_dir=str(base))
            # Craft a filename that, when resolved, lands in the sibling dir
            # relative path: ../../<basename>_evil/file.md  (two levels: base → parent → evil)
            parent = base.parent
            evil_relative = os.path.relpath(evil_dir / "file.md", base)
            result = await tool.execute(filename=evil_relative, content="pwned", output_dir=str(base))
            assert not result.success, "Sibling-directory attack should have been blocked"
            assert "traversal" in (result.error or "").lower()
            # Make sure the evil file was NOT created
            assert not (evil_dir / "file.md").exists()
        finally:
            # Clean up sibling dir
            import shutil
            shutil.rmtree(evil_dir, ignore_errors=True)
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


# ── Path Traversal: WriteXlsxTool and WritePptxTool ───────────────────────────

@pytest.mark.asyncio
async def test_path_traversal_write_xlsx_blocked():
    """../../evil.xlsx path traversal must be blocked in WriteXlsxTool."""
    from hydra_agents.tools.document_tools import WriteXlsxTool

    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteXlsxTool(output_dir=tmpdir)
        result = await tool.execute(
            filename="../../evil.xlsx",
            sheets=[{"name": "S", "headers": ["a"], "rows": [["1"]]}],
        )
        assert not result.success
        assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_write_pptx_blocked():
    """../../evil.pptx path traversal must be blocked in WritePptxTool."""
    from hydra_agents.tools.document_tools import WritePptxTool

    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WritePptxTool(output_dir=tmpdir)
        result = await tool.execute(
            filename="../../evil.pptx",
            slides=[{"title": "Pwned"}],
        )
        assert not result.success
        assert "traversal" in (result.error or "").lower()


# ── PdfReaderTool allowed_dirs ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pdf_reader_allowed_dirs_blocks():
    """PdfReaderTool must block access to paths outside allowed_dirs."""
    from hydra_agents.tools.document_tools import PdfReaderTool

    tool = PdfReaderTool(allowed_dirs=["/tmp/safe_hydra_test"])
    result = await tool.execute(filepath="/etc/passwd")
    assert not result.success
    assert "access denied" in (result.error or "").lower() or "not under" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_pdf_reader_allowed_dirs_allows():
    """PdfReaderTool must allow access to paths inside allowed_dirs."""
    import fitz  # pymupdf — skip if not available

    try:
        import fitz
    except ImportError:
        pytest.skip("pymupdf not available")

    from hydra_agents.tools.document_tools import PdfReaderTool

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Allowed dir test")
        doc.save(str(pdf_path))
        doc.close()

        tool = PdfReaderTool(allowed_dirs=[tmpdir])
        result = await tool.execute(filepath=str(pdf_path))
        assert result.success, f"Expected success, got: {result.error}"
        assert "Allowed dir test" in result.data["text"]


# ── WebFetchTool: follow_redirects=False ─────────────────────────────────────

@pytest.mark.asyncio
async def test_web_fetch_no_redirect_follow():
    """WebFetchTool must NOT follow redirects (follow_redirects=False)."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from hydra_agents.tools.research_tools import WebFetchTool

    tool = WebFetchTool()
    captured_kwargs = {}

    # Capture the kwargs passed when AsyncClient is instantiated
    original_async_client = __import__("httpx").AsyncClient

    class CapturingClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self._mock = MagicMock()

        async def __aenter__(self):
            resp = MagicMock()
            resp.headers = {"content-type": "text/plain"}
            resp.text = "hello"
            resp.raise_for_status = MagicMock()
            self._mock.get = AsyncMock(return_value=resp)
            return self._mock

        async def __aexit__(self, *args):
            return False

    with patch("hydra_agents.tools.research_tools.httpx.AsyncClient", CapturingClient):
        await tool.execute(url="https://example.com")

    assert captured_kwargs.get("follow_redirects") is False, (
        "WebFetchTool must set follow_redirects=False"
    )


# ── DataTransformTool: negative limit ────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_transform_negative_limit_error():
    """DataTransformTool limit with count=-1 must return an error."""
    from hydra_agents.tools.data_tools import DataTransformTool

    tool = DataTransformTool()
    data = [{"x": 1}, {"x": 2}, {"x": 3}]
    result = await tool.execute(
        data=data,
        operations=[{"type": "limit", "params": {"count": -1}}],
    )
    assert not result.success
    assert result.error is not None
    assert "non-negative" in (result.error or "").lower() or "negative" in (result.error or "").lower()
