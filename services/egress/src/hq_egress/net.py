"""Outgoing HTTP with the guard in the connection itself.

`GuardedBackend` is httpcore's network backend: every TCP connection (the
first request and each redirect hop) resolves its name through the guard and
connects to the address the guard checked, while TLS still verifies the
certificate for the name (SNI). `Fetcher.fetch` follows redirects by hand,
checking each Location as a new URL, and stops reading at the byte cap.
"""

from __future__ import annotations

import ssl
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import certifi
import httpcore
import httpx

from hq_egress.guard import Blocked, Guard

MAX_REDIRECTS = 5
# Request headers an agent may not set (the connection is ours).
HOP_HEADERS = frozenset(
    {
        "host",
        "connection",
        "keep-alive",
        "proxy-authorization",
        "proxy-connection",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "content-length",
        "expect",
    }
)
USER_AGENT = "Mozilla/5.0 (compatible; CoinePro-HQ-agent/1.0; +https://hq.coinepro.com)"


@dataclass
class Entry:
    """One request that left (or was stopped), as the egress log keeps it
    (contract §18.7 EgressEntry, without the context the api adds)."""

    tool: str
    method: str
    host: str
    kind: str = "request"  # request | connect | search | browse
    status: int | None = None
    bytes_in: int = 0
    bytes_out: int = 0
    ms: int = 0
    blocked_reason: str | None = None
    cls: str = "A0"

    def as_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["class"] = d.pop("cls")
        return d


@dataclass
class Fetched:
    status: int
    final_url: str
    headers: dict[str, str]
    body: bytes
    truncated: bool
    entries: list[Entry] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


class GuardedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, guard: Guard) -> None:
        self.guard = guard
        self.inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        last: Exception | None = None
        for addr in await self.guard.addresses(host, port):
            try:
                return await self.inner.connect_tcp(
                    addr, port, timeout=timeout, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise httpcore.ConnectError(str(last or "no address"))

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


def guarded_client(guard: Guard, timeout: float) -> httpx.AsyncClient:
    """An httpx client whose every connection goes through the guard; no proxy
    from the environment, no redirects of its own (Fetcher follows them)."""
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=ssl.create_default_context(cafile=certifi.where()),
        max_connections=20,
        max_keepalive_connections=5,
        keepalive_expiry=5.0,
        network_backend=GuardedBackend(guard),
    )
    return httpx.AsyncClient(
        transport=transport, timeout=timeout, follow_redirects=False, trust_env=False
    )


class Fetcher:
    def __init__(self, guard: Guard, timeout: float = 15.0) -> None:
        self.guard = guard
        self.http = guarded_client(guard, timeout)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        tool: str,
        cls: str,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        max_bytes: int,
        extra_ports: tuple[int, ...] = (),
        inject: Any = None,
    ) -> Fetched:
        """One request and its redirects; each hop is an Entry. `inject(host,
        headers)` adds a service account's credential for its own host only."""
        entries: list[Entry] = []
        current, verb, body = url, method.upper(), content
        for _hop in range(MAX_REDIRECTS + 1):
            try:
                target = self.guard.target(current, extra_ports=extra_ports)
            except Blocked as b:
                entries.append(Entry(tool, verb, _host(current), blocked_reason=b.reason, cls=cls))
                raise _with(b, entries) from None
            sent = {k: v for k, v in (headers or {}).items() if k.lower() not in HOP_HEADERS}
            sent.setdefault("User-Agent", USER_AGENT)
            if inject is not None:
                sent = inject(target.host, sent)
            entry = Entry(tool, verb, target.host, cls=cls, bytes_out=len(body or b""))
            entries.append(entry)
            start = time.monotonic()
            try:
                req = self.http.build_request(verb, current, headers=sent, content=body)
                resp = await self.http.send(req, stream=True)
            except Blocked as b:
                entry.blocked_reason = b.reason
                raise _with(b, entries) from None
            except httpx.HTTPError as exc:
                entry.ms = int((time.monotonic() - start) * 1000)
                raise FetchError(type(exc).__name__, entries) from None
            try:
                entry.status = resp.status_code
                if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    if resp.status_code == 303 or (
                        resp.status_code in (301, 302) and verb not in ("GET", "HEAD")
                    ):
                        verb, body = "GET", None
                    continue
                data, truncated = await _read(resp, max_bytes)
                entry.bytes_in = len(data)
                return Fetched(
                    resp.status_code,
                    current,
                    {k.lower(): v for k, v in resp.headers.items()},
                    data,
                    truncated,
                    entries,
                )
            finally:
                entry.ms = int((time.monotonic() - start) * 1000)
                await resp.aclose()
        entries.append(
            Entry(tool, verb, _host(current), blocked_reason="too_many_redirects", cls=cls)
        )
        raise _with(Blocked("too_many_redirects"), entries)


class FetchError(Exception):
    def __init__(self, reason: str, entries: list[Entry]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.entries = entries


def _with(b: Blocked, entries: list[Entry]) -> Blocked:
    b.entries = list(entries)
    return b


async def _read(resp: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        if size + len(chunk) > max_bytes:
            chunks.append(chunk[: max_bytes - size])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:255]
    except ValueError:
        return "?"
