"""
Research tools: web search and web fetch.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
import structlog

from hydra.models import ToolResult
from hydra.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra.config import HydraConfig

import ipaddress
import re as _re

logger = structlog.get_logger(__name__)

_MAX_FETCH_CHARS = 5000
_DEFAULT_SEARCH_RESULTS = 5

# SSRF-prevention: private/loopback CIDR blocks
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),        # "this" network
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
]
_BLOCKED_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback"}


class WebSearchTool(BaseTool):
    """Search the web and return top results (title, URL, snippet)."""

    name = "web_search"
    description = (
        "Search the web for information. Returns top N results with title, URL, and snippet. "
        "Supports Brave, Tavily, and SerpAPI backends (configured via HYDRA_SEARCH_BACKEND)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string.",
            },
            "num_results": {
                "type": "integer",
                "description": f"Number of results to return (default {_DEFAULT_SEARCH_RESULTS}).",
                "default": _DEFAULT_SEARCH_RESULTS,
            },
        },
        "required": ["query"],
    }
    timeout_seconds = 15

    def __init__(self, config: "HydraConfig | None" = None) -> None:
        self._config = config

    async def execute(self, query: str, num_results: int = _DEFAULT_SEARCH_RESULTS) -> ToolResult:
        # Prefer config values when available; fall back to environment variables.
        if self._config is not None:
            backend = self._config.search_backend.lower()
            api_key = self._config.search_api_key
        else:
            backend = os.environ.get("HYDRA_SEARCH_BACKEND", "brave").lower()
            api_key = os.environ.get("HYDRA_SEARCH_API_KEY", "")

        try:
            if backend == "brave":
                return await self._search_brave(query, num_results, api_key)
            elif backend == "tavily":
                return await self._search_tavily(query, num_results, api_key)
            elif backend == "serpapi":
                return await self._search_serpapi(query, num_results, api_key)
            else:
                return ToolResult(success=False, error=f"Unknown search backend: {backend!r}")
        except Exception as exc:
            logger.error("web_search_failed", query=query, backend=backend, error=str(exc))
            return ToolResult(success=False, error=f"Web search failed: {exc}")

    async def _search_brave(self, query: str, num_results: int, api_key: str) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, error="HYDRA_SEARCH_API_KEY not set for Brave Search.")
        headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
        params = {"q": query, "count": num_results}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:num_results]:
            results.append({"title": item.get("title"), "url": item.get("url"), "snippet": item.get("description")})
        return ToolResult(success=True, data={"results": results, "query": query})

    async def _search_tavily(self, query: str, num_results: int, api_key: str) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, error="HYDRA_SEARCH_API_KEY not set for Tavily.")
        payload = {"api_key": api_key, "query": query, "max_results": num_results}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
        results = [
            {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
            for r in data.get("results", [])[:num_results]
        ]
        return ToolResult(success=True, data={"results": results, "query": query})

    async def _search_serpapi(self, query: str, num_results: int, api_key: str) -> ToolResult:
        if not api_key:
            return ToolResult(success=False, error="HYDRA_SEARCH_API_KEY not set for SerpAPI.")
        params = {"q": query, "api_key": api_key, "num": num_results, "engine": "google"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        results = [
            {"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet")}
            for r in data.get("organic_results", [])[:num_results]
        ]
        return ToolResult(success=True, data={"results": results, "query": query})


class WebFetchTool(BaseTool):
    """Fetch a URL and return clean text content (HTML stripped)."""

    name = "web_fetch"
    description = (
        "Fetch a URL and return its readable text content. "
        "HTML tags, scripts, and styles are stripped. "
        f"Returns up to {_MAX_FETCH_CHARS} characters."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch (must start with http:// or https://).",
            },
            "max_chars": {
                "type": "integer",
                "description": f"Maximum characters to return (default {_MAX_FETCH_CHARS}).",
                "default": _MAX_FETCH_CHARS,
            },
        },
        "required": ["url"],
    }
    timeout_seconds = 20

    async def execute(self, url: str, max_chars: int = _MAX_FETCH_CHARS) -> ToolResult:
        # SSRF prevention
        if _is_ssrf_target(url):
            return ToolResult(
                success=False,
                error=f"SSRF blocked: requests to private/loopback addresses are not allowed ({url})",
            )

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; HydraBot/1.0; +https://github.com/hydra-framework)"
                )
            }
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                raw_content = resp.text

            if "html" in content_type:
                text = self._parse_html(raw_content)
            else:
                text = raw_content

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"

            logger.info("web_fetch_success", url=url, chars=len(text))
            return ToolResult(success=True, data={"url": url, "content": text, "content_type": content_type})

        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"Request to {url!r} timed out after {self.timeout_seconds}s")
        except httpx.HTTPStatusError as exc:
            return ToolResult(success=False, error=f"HTTP {exc.response.status_code} fetching {url!r}: {exc}")
        except Exception as exc:
            logger.error("web_fetch_failed", url=url, error=str(exc))
            return ToolResult(success=False, error=f"Failed to fetch {url!r}: {exc}")

    @staticmethod
    def _parse_html(html: str) -> str:
        """Strip HTML tags and return clean text."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Collapse excessive blank lines
            lines = [line for line in text.splitlines() if line.strip()]
            return "\n".join(lines)
        except ImportError:
            # Fallback: very basic tag stripping
            import re
            return re.sub(r"<[^>]+>", " ", html)


# ── HttpRequestTool ───────────────────────────────────────────────────────────

def _is_ssrf_target(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback address (SSRF prevention)."""
    import socket
    try:
        parsed = httpx.URL(url)
        host = parsed.host
    except Exception:
        return False

    if host.lower() in _BLOCKED_HOSTNAMES:
        return True

    # Strip IPv6 brackets
    bare_host = host.strip("[]")

    try:
        addr = ipaddress.ip_address(bare_host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass  # not a literal IP, try DNS resolution

    try:
        resolved_ips = socket.getaddrinfo(bare_host, None)
        for family, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if any(addr in net for net in _BLOCKED_NETWORKS):
                    return True
            except ValueError:
                pass
    except Exception:
        pass  # DNS failure — let the request proceed and fail naturally

    return False


class HttpRequestTool(BaseTool):
    """Make HTTP requests (GET, POST, PUT, DELETE) with SSRF prevention."""

    name = "http_request"
    description = (
        "Make an HTTP request (GET/POST/PUT/DELETE) to an external URL. "
        "Requests to localhost, 127.x, 10.x, 172.16.x–172.31.x, and 192.168.x are blocked "
        "for SSRF prevention. "
        "Returns status_code, selected headers, and truncated body text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "description": "HTTP method.",
            },
            "url": {
                "type": "string",
                "description": "Full URL to request (must start with http:// or https://).",
            },
            "headers": {
                "type": "object",
                "description": "Optional request headers as a dict.",
            },
            "body": {
                "description": "Optional request body. Dicts are sent as JSON; strings as raw text.",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default 30).",
                "default": 30,
            },
        },
        "required": ["method", "url"],
    }
    timeout_seconds = 30

    async def execute(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body=None,
        timeout: int = 30,
    ) -> ToolResult:
        # Validate URL scheme
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, error="URL must start with http:// or https://")

        # SSRF prevention
        if _is_ssrf_target(url):
            return ToolResult(
                success=False,
                error=f"SSRF blocked: requests to private/loopback addresses are not allowed ({url})",
            )

        method = method.upper()
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            return ToolResult(success=False, error=f"Unsupported HTTP method: {method!r}")

        # Enforce timeout upper bound to prevent resource exhaustion
        timeout = min(int(timeout), 60)

        try:
            request_kwargs: dict = {
                "method": method,
                "url": url,
                "timeout": timeout,
                "follow_redirects": False,
            }
            if headers:
                request_kwargs["headers"] = headers
            if body is not None:
                if isinstance(body, dict):
                    request_kwargs["json"] = body
                else:
                    request_kwargs["content"] = str(body)

            async with httpx.AsyncClient() as client:
                resp = await client.request(**request_kwargs)

            # Select safe response headers to expose
            safe_header_keys = {"content-type", "content-length", "x-request-id", "date", "server"}
            exposed_headers = {k: v for k, v in resp.headers.items() if k.lower() in safe_header_keys}

            body_text = resp.text
            truncated = len(body_text) > _MAX_FETCH_CHARS
            if truncated:
                body_text = body_text[:_MAX_FETCH_CHARS] + f"\n... [truncated at {_MAX_FETCH_CHARS} chars]"

            logger.info("http_request_done", method=method, url=url, status=resp.status_code)
            return ToolResult(
                success=True,
                data={
                    "status_code": resp.status_code,
                    "headers": exposed_headers,
                    "body": body_text,
                    "truncated": truncated,
                    "url": str(resp.url),
                },
            )

        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"Request to {url!r} timed out after {timeout}s")
        except httpx.HTTPStatusError as exc:
            return ToolResult(success=False, error=f"HTTP {exc.response.status_code}: {exc}")
        except Exception as exc:
            logger.error("http_request_failed", method=method, url=url, error=str(exc))
            return ToolResult(success=False, error=f"HTTP request failed: {exc}")
