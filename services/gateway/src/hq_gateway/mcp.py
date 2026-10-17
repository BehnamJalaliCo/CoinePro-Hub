"""The MCP bridge (prompt 07 §3, contract §18.7): `mcp.call` reaches a server
the owner registered and enabled, with the official MCP Python SDK.

transport `http`       streamable HTTP, ONLY through the egress service's
                       forward proxy (EGRESS_PROXY_URL; its SSRF guard checks
                       the resolved address); without the proxy such a server
                       is `channel_not_configured`, never a direct connection.
transport `container`  a compose service on the internal network hq-mcp
                       (http://mcp-<name>:<port>/...), e.g. a stdio server
                       behind a reviewed stdio->HTTP bridge; no docker socket.

The server's secret (if any) comes from the api for this one call and only
ever goes into the request header; it is in no result, log line or error.
What the server answers is untrusted data: labelled (`source: "mcp"`) and
redacted by the gateway like every result.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

CONTAINER_HOST = re.compile(r"^mcp-[a-z0-9-]{1,40}$")
MAX_TEXT_BLOCKS = 20


@dataclass(frozen=True)
class ServerSpec:
    """One enabled server, as the api resolved it for one call."""

    key: str
    transport: str
    url: str
    listing_sha256: str | None
    auth_header: str | None = None
    secret: str | None = field(default=None, repr=False)  # never printed

    def headers(self) -> dict[str, str]:
        if not (self.auth_header and self.secret):
            return {}
        value = self.secret
        if self.auth_header.lower() == "authorization" and " " not in value:
            value = f"Bearer {value}"
        return {self.auth_header: value}


@dataclass(frozen=True)
class Listing:
    names: list[str]
    sha256: str


class NotConfigured(Exception):
    """The server cannot be reached from here (no egress proxy, a bad URL)."""


class Session(Protocol):
    async def list_tools(self) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


Opener = Callable[[ServerSpec], contextlib.AbstractAsyncContextManager[Session]]


def listing_of(tools: list[Any]) -> Listing:
    """The server's tools as the owner's seal pins them: names, descriptions and
    input schemas (a changed description or schema is a changed tool)."""
    rows: list[dict[str, Any]] = [
        {
            "name": str(getattr(t, "name", "")),
            "description": str(getattr(t, "description", None) or ""),
            "input_schema": getattr(t, "input_schema", None) or {},
        }
        for t in tools
    ]
    rows.sort(key=lambda r: str(r["name"]))
    canon = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return Listing(
        names=[str(r["name"]) for r in rows], sha256=hashlib.sha256(canon.encode()).hexdigest()
    )


def render(server: str, tool: str, result: Any) -> dict[str, Any]:
    """A CallToolResult as data for the model: text blocks only (an image or a
    resource is named, not passed on), labelled as untrusted."""
    texts: list[str] = []
    other: list[str] = []
    for block in list(getattr(result, "content", None) or [])[:MAX_TEXT_BLOCKS]:
        kind = str(getattr(block, "type", "") or "")
        if kind == "text":
            texts.append(str(getattr(block, "text", "")))
        else:
            other.append(kind or "unknown")
    out: dict[str, Any] = {
        "source": "mcp",
        "untrusted": True,
        "server": server,
        "tool": tool,
        "is_error": bool(getattr(result, "is_error", False)),
        "text": texts,
    }
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        out["structured"] = structured
    if other:
        out["omitted"] = other  # e.g. ["image"]: not passed to the model
    return out


class SdkOpener:
    """Opens a session with the MCP Python SDK over streamable HTTP."""

    def __init__(self, proxy_url: str | None, timeout_s: float) -> None:
        self.proxy_url = proxy_url or None
        self.timeout_s = timeout_s

    def target(self, spec: ServerSpec) -> tuple[str, str | None]:
        """(url, proxy) for a server, or NotConfigured."""
        parts = urlsplit(spec.url)
        if spec.transport == "http":
            if parts.scheme != "https" or not parts.hostname:
                raise NotConfigured("an http server needs an https URL")
            if not self.proxy_url:
                raise NotConfigured("no egress proxy (EGRESS_PROXY_URL)")
            return spec.url, self.proxy_url
        if spec.transport == "container":
            host = parts.hostname or ""
            if parts.scheme != "http" or not CONTAINER_HOST.fullmatch(host) or not parts.port:
                raise NotConfigured("a container server is http://mcp-<name>:<port>/...")
            return spec.url, None
        raise NotConfigured("unknown transport")

    @contextlib.asynccontextmanager
    async def __call__(self, spec: ServerSpec) -> AsyncIterator[Session]:
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        url, proxy = self.target(spec)
        timeout = httpx2.Timeout(self.timeout_s, read=self.timeout_s)
        async with (
            httpx2.AsyncClient(headers=spec.headers(), timeout=timeout, proxy=proxy) as http,
            Client(
                streamable_http_client(url, http_client=http),
                read_timeout_seconds=self.timeout_s,
            ) as client,
        ):
            yield client
