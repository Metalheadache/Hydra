"""
Tests for the 8 security and correctness fixes:
1. SSRF via redirect (HttpRequestTool follow_redirects=False)
2. WebFetchTool SSRF (direct localhost blocked)
3. DataTransformTool group_by without agg_field → error
4. DataTransformTool empty data → graceful result
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hydra_agents.tools.research_tools import HttpRequestTool, WebFetchTool
from hydra_agents.tools.data_tools import DataTransformTool


# ── SSRF: HttpRequestTool redirect prevention ─────────────────────────────────

@pytest.mark.asyncio
async def test_http_request_follow_redirects_false():
    """HttpRequestTool must NOT follow redirects (follow_redirects=False)."""
    tool = HttpRequestTool()

    captured_kwargs = {}

    async def mock_request(**kwargs):
        captured_kwargs.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = "ok"
        resp.url = "https://example.com"
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = mock_request

    with patch("hydra_agents.tools.research_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(method="GET", url="https://example.com")

    assert captured_kwargs.get("follow_redirects") is False, (
        "HttpRequestTool must set follow_redirects=False to prevent SSRF via redirect"
    )


@pytest.mark.asyncio
async def test_http_request_ssrf_redirect_to_localhost_blocked():
    """
    Simulate a redirect to 127.0.0.1 — the pre-redirect SSRF check on the
    initial URL passes (it's external), but follow_redirects=False means
    the redirect is never followed, so the attack is neutralised.
    """
    tool = HttpRequestTool()

    # The initial URL is external and passes SSRF check.
    # With follow_redirects=False, a redirect response is returned directly
    # (status 301/302) without following — so no request hits 127.0.0.1.
    async def mock_request(**kwargs):
        resp = MagicMock()
        resp.status_code = 301
        resp.headers = {"location": "http://127.0.0.1/secret"}
        resp.text = ""
        resp.url = "https://example.com"
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = mock_request

    with patch("hydra_agents.tools.research_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute(method="GET", url="https://example.com")

    # The request should succeed (redirect returned as-is, not followed)
    # The key is that we do NOT end up hitting 127.0.0.1
    assert result.success
    assert result.data["status_code"] == 301  # redirect returned, not followed


@pytest.mark.asyncio
async def test_http_request_timeout_upper_bound():
    """HttpRequestTool must cap timeout at 60 seconds."""
    tool = HttpRequestTool()

    captured_kwargs = {}

    async def mock_request(**kwargs):
        captured_kwargs.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = "ok"
        resp.url = "https://example.com"
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = mock_request

    with patch("hydra_agents.tools.research_tools.httpx.AsyncClient", return_value=mock_client):
        # Request timeout of 9999 should be capped at 60
        result = await tool.execute(method="GET", url="https://example.com", timeout=9999)

    assert captured_kwargs.get("timeout") <= 60, (
        "Timeout must be capped at 60 seconds to prevent resource exhaustion"
    )


# ── SSRF: WebFetchTool localhost URL blocked ───────────────────────────────────

@pytest.mark.asyncio
async def test_web_fetch_localhost_blocked():
    """WebFetchTool must block direct requests to localhost."""
    tool = WebFetchTool()
    result = await tool.execute(url="http://localhost/secret")
    assert not result.success
    assert "SSRF" in (result.error or "") or "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_web_fetch_127_0_0_1_blocked():
    """WebFetchTool must block requests to 127.0.0.1."""
    tool = WebFetchTool()
    result = await tool.execute(url="http://127.0.0.1/secret")
    assert not result.success
    assert "SSRF" in (result.error or "") or "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_web_fetch_169_254_blocked():
    """WebFetchTool must block requests to AWS metadata (169.254.169.254)."""
    tool = WebFetchTool()
    result = await tool.execute(url="http://169.254.169.254/latest/meta-data/")
    assert not result.success
    assert "SSRF" in (result.error or "") or "blocked" in (result.error or "").lower()


# ── DataTransformTool: group_by without agg_field → error ─────────────────────

@pytest.mark.asyncio
async def test_group_by_non_count_without_agg_field_returns_error():
    """group_by with agg_func != 'count' and no agg_field must return an error."""
    tool = DataTransformTool()
    data = [
        {"category": "A", "value": 10},
        {"category": "B", "value": 20},
        {"category": "A", "value": 30},
    ]
    operations = [
        {
            "type": "group_by",
            "params": {
                "field": "category",
                "agg_func": "sum",
                # agg_field intentionally omitted
            },
        }
    ]
    result = await tool.execute(data=data, operations=operations)
    assert not result.success
    assert result.error is not None
    assert "agg_field" in result.error.lower() or "required" in result.error.lower()


@pytest.mark.asyncio
async def test_group_by_count_without_agg_field_ok():
    """group_by with agg_func='count' must work without agg_field."""
    tool = DataTransformTool()
    data = [
        {"category": "A"},
        {"category": "B"},
        {"category": "A"},
    ]
    operations = [
        {
            "type": "group_by",
            "params": {
                "field": "category",
                "agg_func": "count",
            },
        }
    ]
    result = await tool.execute(data=data, operations=operations)
    assert result.success
    groups = {row["category"]: row["count"] for row in result.data["result"]}
    assert groups["A"] == 2
    assert groups["B"] == 1


@pytest.mark.asyncio
async def test_group_by_sum_with_agg_field_ok():
    """group_by with agg_func='sum' and agg_field must work correctly."""
    tool = DataTransformTool()
    data = [
        {"category": "A", "value": 10},
        {"category": "B", "value": 20},
        {"category": "A", "value": 30},
    ]
    operations = [
        {
            "type": "group_by",
            "params": {
                "field": "category",
                "agg_func": "sum",
                "agg_field": "value",
            },
        }
    ]
    result = await tool.execute(data=data, operations=operations)
    assert result.success
    groups = {row["category"]: row["sum_value"] for row in result.data["result"]}
    assert groups["A"] == 40.0
    assert groups["B"] == 20.0


# ── DataTransformTool: empty data → graceful result ────────────────────────────

@pytest.mark.asyncio
async def test_data_transform_empty_data_graceful():
    """DataTransformTool must handle empty input data gracefully."""
    tool = DataTransformTool()
    result = await tool.execute(data=[], operations=[])
    assert result.success
    assert result.data["result"] == []
    assert result.data["count"] == 0


@pytest.mark.asyncio
async def test_data_transform_empty_data_with_filter():
    """Filter on empty data must return empty result, not error."""
    tool = DataTransformTool()
    result = await tool.execute(
        data=[],
        operations=[
            {"type": "filter", "params": {"field": "x", "operator": "==", "value": 1}}
        ],
    )
    assert result.success
    assert result.data["result"] == []


@pytest.mark.asyncio
async def test_data_transform_empty_data_with_group_by():
    """group_by on empty data must return empty result, not error."""
    tool = DataTransformTool()
    result = await tool.execute(
        data=[],
        operations=[
            {"type": "group_by", "params": {"field": "cat", "agg_func": "count"}}
        ],
    )
    assert result.success
    assert result.data["result"] == []
