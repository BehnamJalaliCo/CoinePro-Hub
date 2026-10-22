"""Outgoing HTTP with the guard in the connection itself.

`GuardedBackend` is httpcore's network backend: every TCP connection (the
first request and each redirect hop) resolves its name through the guard and
connects to the address the guard checked, while TLS still verifies the
certificate for the name (SNI). `Fetcher.fetch` follows redirects by hand,
checking each Location as a new URL (a GET or HEAD only: another method's
redirect comes back unfollowed), and stops reading at the byte cap. A
service account's credential goes on a hop to its own site over https only,
and its extra ports open for that site only (7.1); `check` judges every hop
(a GET that commits: rules.get_commitment).
"""

from __future__ import annotations

import asyncio
import contextvars
import re
import ssl
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import certifi
import httpcore
import httpx

from hq_egress.accounts import Account
from hq_egress.guard import Blocked, Guard

# (method, url) -> why this request is an external commitment, or None.
Check = Callable[[str, str], str | None]

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
READ_METHODS = ("GET", "HEAD")
_NOT_METHOD = re.compile(r"[^A-Z0-9_-]")
_REASON = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_INT_MAX = 2**31 - 1
# The entries of the call being served (app.py's catch-all answers with them).
CALL_ENTRIES: contextvars.ContextVar[list[Entry] | None] = contextvars.ContextVar(
    "egress_call_entries", default=None
)


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
        """As the egress log takes it: a hostile server's method, status or
        reason is cut to the log's shape, so one bad row never drops a batch."""
        d = asdict(self)
        d["class"] = d.pop("cls")
        d["method"] = _NOT_METHOD.sub("", str(self.method).upper())[:10] or "OTHER"
        d["host"] = (str(self.host or "") or "?")[:255]
        s = self.status
        d["status"] = s if type(s) is int and 100 <= s <= 999 else None
        if self.blocked_reason is not None:
            r = re.sub(r"[^a-z0-9_]", "_", str(self.blocked_reason).lower())[:41]
            d["blocked_reason"] = r if _REASON.match(r) else "other"
        for k in ("bytes_in", "bytes_out", "ms"):
            d[k] = max(0, int(d[k] or 0))
        d["ms"] = min(d["ms"], _INT_MAX)
        return d


def track(entry: Entry) -> Entry:
    """`entry` belongs to the call being served (returned even if it fails)."""
    call = CALL_ENTRIES.get()
    if call is not None and not any(e is entry for e in call):
        call.append(entry)
    return entry


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


def guarded_client(
    guard: Guard, timeout: float, ssl_context: ssl.SSLContext | None = None
) -> httpx.AsyncClient:
    """An httpx client whose every connection goes through the guard; no proxy
    from the environment, no redirects of its own (Fetcher follows them).
    `ssl_context`: the public CAs (certifi) unless a test gives its own."""
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=ssl_context or ssl.create_default_context(cafile=certifi.where()),
        max_connections=20,
        max_keepalive_connections=5,
        keepalive_expiry=5.0,
        network_backend=GuardedBackend(guard),
    )
    return httpx.AsyncClient(
        transport=transport, timeout=timeout, follow_redirects=False, trust_env=False
    )


class Fetcher:
    def __init__(
        self, guard: Guard, timeout: float = 15.0, ssl_context: ssl.SSLContext | None = None
    ) -> None:
        self.guard = guard
        self.http = guarded_client(guard, timeout, ssl_context)

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
        account: Account | None = None,
        check: Check | None = None,
    ) -> Fetched:
        """One request and its redirects; each hop is an Entry. A service
        `account`'s credential and ports apply to its own site only, its
        credential over https only; `check` refuses a hop that commits."""
        call = CALL_ENTRIES.get()
        entries: list[Entry] = call if call is not None else []
        current, verb, body = url, method.upper(), content
        ports = account.ports_for if account is not None else None
        for _hop in range(MAX_REDIRECTS + 1):
            try:
                target = self.guard.target(current, extra_ports=ports)
                why = check(verb, current) if check is not None else None
                if why:
                    raise Blocked("needs_owner", why)
            except Blocked as b:
                entries.append(Entry(tool, verb, _host(current), blocked_reason=b.reason, cls=cls))
                raise _with(b, entries) from None
            sent = {k: v for k, v in (headers or {}).items() if k.lower() not in HOP_HEADERS}
            sent.setdefault("User-Agent", USER_AGENT)
            if account is not None:
                sent = account.headers_for(target.host, sent, target.scheme)
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
            except asyncio.CancelledError:  # the call's deadline: the time spent still counts
                entry.ms = int((time.monotonic() - start) * 1000)
                entry.blocked_reason = entry.blocked_reason or "call_timeout"
                raise
            try:
                entry.status = resp.status_code
                if (
                    resp.status_code in (301, 302, 303, 307, 308)
                    and resp.headers.get("location")
                    and verb in READ_METHODS
                ):
                    # Only a read is followed: a POST's 307/308 would send the
                    # body and the account's credential again, unchecked.
                    current, body = urljoin(current, resp.headers["location"]), None
                    continue
                data, truncated = await _read(resp, max_bytes, entry)
                entry.bytes_in = len(data)
                return Fetched(
                    resp.status_code,
                    current,
                    {k.lower(): v for k, v in resp.headers.items()},
                    data,
                    truncated,
                    entries,
                )
            except asyncio.CancelledError:  # cut while reading (a dripping server)
                entry.blocked_reason = entry.blocked_reason or "call_timeout"
                raise
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


async def _read(
    resp: httpx.Response, max_bytes: int, entry: Entry | None = None
) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        if size + len(chunk) > max_bytes:
            chunks.append(chunk[: max_bytes - size])
            if entry is not None:
                entry.bytes_in = max_bytes
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
        if entry is not None:  # a dripping server cut at the deadline: what came counts
            entry.bytes_in = size
    return b"".join(chunks), False


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:255]
    except ValueError:
        return "?"
