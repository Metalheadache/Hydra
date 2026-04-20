"""
Tests for RegexTool.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hydra_agents.tools.regex_tools import RegexTool


# ── search ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_basic():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="search", text="abc 123 def 456")
    assert result.success
    assert result.data["count"] == 2
    assert result.data["matches"][0]["match"] == "123"
    assert result.data["matches"][1]["match"] == "456"


@pytest.mark.asyncio
async def test_search_line_and_column():
    tool = RegexTool()
    text = "hello world\nfoo bar\nbaz qux"
    result = await tool.execute(pattern=r"bar", action="search", text=text)
    assert result.success
    assert result.data["count"] == 1
    m = result.data["matches"][0]
    assert m["line"] == 2
    assert m["match"] == "bar"
    assert m["context_before"] == "hello world"
    assert m["context_after"] == "baz qux"


@pytest.mark.asyncio
async def test_search_no_matches():
    tool = RegexTool()
    result = await tool.execute(pattern=r"xyz999", action="search", text="hello world")
    assert result.success
    assert result.data["count"] == 0
    assert result.data["matches"] == []


@pytest.mark.asyncio
async def test_search_flag_ignorecase():
    tool = RegexTool()
    result = await tool.execute(
        pattern=r"HELLO", action="search", text="hello world", flags=["ignorecase"]
    )
    assert result.success
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_search_max_matches_truncation():
    tool = RegexTool()
    text = " ".join(str(i) for i in range(200))
    result = await tool.execute(pattern=r"\d+", action="search", text=text, max_matches=10)
    assert result.success
    assert result.data["count"] == 10
    assert result.data["truncated"] is True


# ── extract ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_numbered_groups():
    tool = RegexTool()
    result = await tool.execute(
        pattern=r"(\w+)@(\w+)", action="extract", text="user@host admin@server"
    )
    assert result.success
    assert result.data["count"] == 2
    first = result.data["matches"][0]
    assert first["groups"]["1"] == "user"
    assert first["groups"]["2"] == "host"


@pytest.mark.asyncio
async def test_extract_named_groups():
    tool = RegexTool()
    result = await tool.execute(
        pattern=r"(?P<user>\w+)@(?P<domain>\w+)",
        action="extract",
        text="alice@example",
    )
    assert result.success
    groups = result.data["matches"][0]["groups"]
    assert groups["user"] == "alice"
    assert groups["domain"] == "example"


@pytest.mark.asyncio
async def test_extract_no_groups_returns_full_match():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="extract", text="abc 42")
    assert result.success
    assert result.data["matches"][0]["groups"]["0"] == "42"


# ── replace ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replace_inline():
    tool = RegexTool()
    result = await tool.execute(
        pattern=r"\d+", action="replace", text="abc 123 def 456", replacement="NUM"
    )
    assert result.success
    assert result.data["result"] == "abc NUM def NUM"


@pytest.mark.asyncio
async def test_replace_file(tmp_path):
    content = "foo 1\nbar 2\nbaz 3\n"
    target = tmp_path / "data.txt"
    target.write_text(content, encoding="utf-8")

    tool = RegexTool(output_dir=str(tmp_path))
    result = await tool.execute(
        pattern=r"\d",
        action="replace",
        file_path=str(target),
        replacement="X",
    )
    assert result.success
    assert "diff_summary" in result.data
    assert "filepath" in result.data
    assert target.read_text(encoding="utf-8") == "foo X\nbar X\nbaz X\n"


@pytest.mark.asyncio
async def test_replace_requires_replacement():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="replace", text="hello 123")
    assert not result.success
    assert "replacement" in (result.error or "").lower()


# ── split ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_split_basic():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\s+", action="split", text="one two  three")
    assert result.success
    assert result.data["parts"] == ["one", "two", "three"]


@pytest.mark.asyncio
async def test_split_truncation():
    tool = RegexTool()
    text = ",".join("x" for _ in range(300))
    result = await tool.execute(pattern=r",", action="split", text=text, max_matches=5)
    assert result.success
    assert result.data["count"] == 5
    assert result.data["truncated"] is True


# ── ReDoS timeout ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redos_timeout_returns_error():
    """_run_with_timeout propagates TimeoutError as a ToolResult failure."""
    tool = RegexTool()

    async def mock_timeout(*args, **kwargs):
        raise concurrent.futures.TimeoutError("Regex execution timed out after 5.0s (possible ReDoS pattern)")

    with patch("hydra_agents.tools.regex_tools._run_with_timeout", mock_timeout):
        result = await tool.execute(pattern=r"\d+", action="search", text="hello 123")

    assert not result.success
    assert result.error is not None
    assert "timeout" in result.error.lower() or "redos" in result.error.lower()


# ── file mode ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_mode_no_matches(tmp_path):
    content = "hello world\n"
    target = tmp_path / "test.txt"
    target.write_text(content, encoding="utf-8")

    tool = RegexTool(output_dir=str(tmp_path))
    result = await tool.execute(pattern=r"xyz999", action="search", file_path=str(target))
    assert result.success
    assert result.data["count"] == 0


@pytest.mark.asyncio
async def test_binary_file_rejected(tmp_path):
    target = tmp_path / "binary.bin"
    target.write_bytes(b"\x00\x01\x02\x03hello")

    tool = RegexTool(output_dir=str(tmp_path))
    result = await tool.execute(pattern=r".", action="search", file_path=str(target))
    assert not result.success
    assert "binary" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_file_path_outside_output_dir_blocked(tmp_path):
    other_dir = tmp_path / "secret"
    other_dir.mkdir()
    secret_file = other_dir / "secret.txt"
    secret_file.write_text("top secret", encoding="utf-8")

    safe_dir = tmp_path / "output"
    safe_dir.mkdir()

    tool = RegexTool(output_dir=str(safe_dir))
    result = await tool.execute(pattern=r".", action="search", file_path=str(secret_file))
    assert not result.success


# ── invalid pattern ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_pattern_reports_re_error():
    tool = RegexTool()
    result = await tool.execute(pattern=r"[invalid", action="search", text="hello")
    assert not result.success
    assert "Invalid regex pattern" in (result.error or "")


# ── mutual exclusivity ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_and_file_path_mutually_exclusive(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("hi", encoding="utf-8")

    tool = RegexTool(output_dir=str(tmp_path))
    result = await tool.execute(
        pattern=r"\w+",
        action="search",
        text="hello",
        file_path=str(target),
    )
    assert not result.success
    assert "both" in (result.error or "").lower() or "mutually" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_no_input_returns_error():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="search")
    assert not result.success


# ── empty string input ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_empty_string():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="search", text="")
    assert result.success
    assert result.data["count"] == 0
    assert result.data["matches"] == []


@pytest.mark.asyncio
async def test_extract_empty_string():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="extract", text="")
    assert result.success
    assert result.data["count"] == 0


@pytest.mark.asyncio
async def test_replace_empty_string():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="replace", text="", replacement="X")
    assert result.success
    assert result.data["result"] == ""


@pytest.mark.asyncio
async def test_split_empty_string():
    tool = RegexTool()
    result = await tool.execute(pattern=r"\s+", action="split", text="")
    assert result.success
    assert result.data["parts"] == [""]


# ── optional groups filter None ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_optional_group_none_filtered():
    """Non-participating optional groups must be omitted, not returned as None."""
    tool = RegexTool()
    # (a)|(b) — for each match exactly one branch fires; the other group is None
    result = await tool.execute(pattern=r"(a)|(b)", action="extract", text="a b")
    assert result.success
    assert result.data["count"] == 2
    first = result.data["matches"][0]
    assert first["groups"].get("1") == "a"
    assert "2" not in first["groups"]   # None filtered out
    second = result.data["matches"][1]
    assert second["groups"].get("2") == "b"
    assert "1" not in second["groups"]  # None filtered out


# ── max_matches=0 boundary ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_max_matches_zero():
    """max_matches=0 must return an empty match list marked as truncated."""
    tool = RegexTool()
    result = await tool.execute(pattern=r"\d+", action="search", text="abc 123", max_matches=0)
    assert result.success
    assert result.data["count"] == 0
    assert result.data["truncated"] is True


# ── atomic file write ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replace_file_atomic_no_tmp_left(tmp_path):
    """After a successful replace, no .tmp file should remain."""
    content = "hello 1\nworld 2\n"
    target = tmp_path / "data.txt"
    target.write_text(content, encoding="utf-8")

    tool = RegexTool(output_dir=str(tmp_path))
    result = await tool.execute(
        pattern=r"\d", action="replace", file_path=str(target), replacement="N"
    )
    assert result.success
    assert target.read_text(encoding="utf-8") == "hello N\nworld N\n"
    tmp_file = tmp_path / "data.txt.tmp"
    assert not tmp_file.exists()   # .tmp cleaned up after atomic replace
