"""The forward proxy (HTTP and CONNECT) of the egress service, with the same
guard as every other request: the browser's only way out, and the gateway's
for MCP servers over HTTP.

Two listeners, each accepting only its own network's clients:
- browser (port 3128): every connection carries the Basic credential of one
  browse session (created per web.browse call, in memory, never logged);
  its entries go back with that call's result.
- gateway (port 3129): every connection names its tool call in headers
  (`X-HQ-Call`, `X-HQ-Tool`, `X-HQ-Class`); its entries are collected by
  `POST /v1/proxy/drain {call_id}` after the call.
A tunnel's TLS is not opened: its host, port, size and time are logged. The
hub's own names are refused for tunnels altogether (their paths cannot be
seen inside TLS, and /internal must stay unreachable).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import ipaddress
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from hq_egress.guard import Blocked, Guard
from hq_egress.net import Entry

HEAD_MAX = 16 * 1024
IDLE_S = 60.0
LIFETIME_S = 180.0
DROP_HEADERS = frozenset(
    {
        "proxy-authorization",
        "proxy-connection",
        "connection",
        "keep-alive",
        "x-hq-call",
        "x-hq-tool",
        "x-hq-class",
    }
)


@dataclass
class Bucket:
    """What one tool call's connections did, and what is left of its caps."""

    tool: str
    cls: str
    bytes_left: int
    expires: float
    entries: list[Entry] = field(default_factory=list)


class Buckets:
    def __init__(self, ttl_s: float = 600) -> None:
        self._items: dict[str, tuple[str, Bucket]] = {}
        self.ttl_s = ttl_s

    def open(self, tool: str, cls: str, bytes_left: int, key: str | None = None) -> tuple[str, str]:
        """(key, secret) of a new bucket (a browse session's proxy login)."""
        self._sweep()
        key = key or "s" + secrets.token_hex(12)
        secret = secrets.token_urlsafe(24)
        self._items[key] = (secret, Bucket(tool, cls, bytes_left, time.monotonic() + self.ttl_s))
        return key, secret

    def get(self, key: str, secret: str | None = None) -> Bucket | None:
        self._sweep()
        item = self._items.get(key)
        if item is None:
            return None
        if secret is not None and not hmac.compare_digest(item[0], secret):
            return None
        return item[1]

    def drain(self, key: str) -> list[Entry]:
        item = self._items.pop(key, None)
        return item[1].entries if item else []

    def _sweep(self) -> None:
        now = time.monotonic()
        for k in [k for k, (_, b) in self._items.items() if b.expires < now]:
            self._items.pop(k, None)


class Proxy:
    def __init__(
        self,
        guard: Guard,
        buckets: Buckets,
        *,
        mode: str,
        clients: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
        gateway_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        assert mode in ("browser", "gateway")
        self.guard = guard
        self.buckets = buckets
        self.mode = mode
        self.clients = clients
        self.gateway_bytes = gateway_bytes

    async def serve(self, host: str, port: int) -> asyncio.Server:
        return await asyncio.start_server(self.handle, host, port, limit=HEAD_MAX)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await asyncio.wait_for(self._handle(reader, writer), timeout=LIFETIME_S)
        except (TimeoutError, ConnectionError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    def _client_ok(self, writer: asyncio.StreamWriter) -> bool:
        peer = writer.get_extra_info("peername")
        try:
            ip = ipaddress.ip_address(peer[0])
        except (TypeError, ValueError, IndexError):
            return False
        return any(ip in net for net in self.clients)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not self._client_ok(writer):
            return
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            await _answer(writer, 400, "Bad Request")
            return
        headers: list[tuple[str, str]] = []
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                headers.append((k.strip(), v.strip()))
        low = {k.lower(): v for k, v in headers}
        bucket = self._bucket(low)
        if bucket is None:
            extra = {"Proxy-Authenticate": 'Basic realm="egress"'} if self.mode == "browser" else {}
            await _answer(writer, 407, "Proxy Authentication Required", extra)
            return
        method = method.upper()
        if method == "CONNECT":
            await self._tunnel(target, bucket, reader, writer)
        elif target.lower().startswith("http://"):
            await self._forward(method, target, version, headers, bucket, reader, writer)
        else:
            await _answer(writer, 400, "Bad Request")

    def _bucket(self, low: dict[str, str]) -> Bucket | None:
        if self.mode == "browser":
            auth = low.get("proxy-authorization", "")
            if not auth.lower().startswith("basic "):
                return None
            try:
                user, _, secret = base64.b64decode(auth[6:]).decode().partition(":")
            except (ValueError, UnicodeDecodeError):
                return None
            return self.buckets.get(user, secret)
        call = low.get("x-hq-call", "")
        if not (8 <= len(call) <= 64) or not call.replace("-", "").isalnum():
            return None
        found = self.buckets.get(call)
        if found is None:
            tool = low.get("x-hq-tool", "mcp.call")[:40]
            cls = low.get("x-hq-class", "A0")[:2]
            self.buckets.open(
                tool, cls if cls in ("A0", "A1", "A2") else "A2", self.gateway_bytes, call
            )
            found = self.buckets.get(call)
        return found

    async def _connect(
        self, host: str, port: int, entry: Entry, bucket: Bucket, writer: asyncio.StreamWriter
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter] | None:
        try:
            if self.guard.is_hub(host):
                raise Blocked("hub_internal")
            self.guard.check_name(host)
            if port not in self.guard.ports_for(host):
                raise Blocked("port_not_allowed")
            addrs = await self.guard.addresses(host, port)
        except Blocked as b:
            entry.blocked_reason = b.reason
            bucket.entries.append(entry)
            await _answer(writer, 403, "Forbidden", {"X-Egress-Blocked": b.reason})
            return None
        for addr in addrs:
            try:
                return await asyncio.wait_for(asyncio.open_connection(addr, port), timeout=10)
            except (OSError, TimeoutError):
                continue
        entry.status = 502
        bucket.entries.append(entry)
        await _answer(writer, 502, "Bad Gateway")
        return None

    async def _tunnel(
        self,
        target: str,
        bucket: Bucket,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        host, _, port_s = target.rpartition(":")
        host = host.strip("[]").lower().rstrip(".")
        entry = Entry(bucket.tool, "CONNECT", host[:255], kind="connect", cls=bucket.cls)
        if not port_s.isdigit() or not host:
            await _answer(writer, 400, "Bad Request")
            return
        start = time.monotonic()
        up = await self._connect(host, int(port_s), entry, bucket, writer)
        if up is None:
            return
        entry.status = 200
        bucket.entries.append(entry)
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await _pipe_both(reader, writer, up, entry, bucket)
        entry.ms = int((time.monotonic() - start) * 1000)

    async def _forward(
        self,
        method: str,
        url: str,
        version: str,
        headers: list[tuple[str, str]],
        bucket: Bucket,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            t = self.guard.target(url)
        except Blocked as b:
            entry = Entry(
                bucket.tool, method, "?", kind="request", cls=bucket.cls, blocked_reason=b.reason
            )
            bucket.entries.append(entry)
            await _answer(writer, 403, "Forbidden", {"X-Egress-Blocked": b.reason})
            return
        entry = Entry(bucket.tool, method, t.host[:255], kind="request", cls=bucket.cls)
        start = time.monotonic()
        up = await self._connect(t.host, t.port, entry, bucket, writer)
        if up is None:
            return
        bucket.entries.append(entry)
        path = url.split("/", 3)[3] if url.count("/") >= 3 else ""
        out = [f"{method} /{path} {version}"]
        out += [f"{k}: {v}" for k, v in headers if k.lower() not in DROP_HEADERS]
        out.append("Connection: close")
        up[1].write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
        await up[1].drain()
        await _pipe_both(reader, writer, up, entry, bucket, parse_status=True)
        entry.ms = int((time.monotonic() - start) * 1000)


async def _pipe_both(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    up: tuple[asyncio.StreamReader, asyncio.StreamWriter],
    entry: Entry,
    bucket: Bucket,
    *,
    parse_status: bool = False,
) -> None:
    up_r, up_w = up

    async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter, inbound: bool) -> None:
        first = parse_status and inbound
        try:
            while True:
                chunk = await asyncio.wait_for(src.read(65536), timeout=IDLE_S)
                if not chunk:
                    break
                if first:
                    first = False
                    with contextlib.suppress(ValueError, IndexError):
                        entry.status = int(chunk.split(b" ", 2)[1])
                if inbound:
                    entry.bytes_in += len(chunk)
                else:
                    entry.bytes_out += len(chunk)
                bucket.bytes_left -= len(chunk)
                if bucket.bytes_left < 0:
                    entry.blocked_reason = "egress_limit"
                    break
                dst.write(chunk)
                await dst.drain()
        except (TimeoutError, ConnectionError, OSError):
            pass
        finally:
            with contextlib.suppress(Exception):
                dst.close()

    tasks = [
        asyncio.create_task(pump(reader, up_w, False)),
        asyncio.create_task(pump(up_r, writer, True)),
    ]
    try:
        _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError, TimeoutError, ConnectionError):
                await asyncio.wait_for(t, timeout=IDLE_S)
    finally:
        for t in tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            up_w.close()


async def _answer(
    writer: asyncio.StreamWriter, code: int, reason: str, extra: dict[str, str] | None = None
) -> None:
    lines = [f"HTTP/1.1 {code} {reason}", "Content-Length: 0", "Connection: close"]
    lines += [f"{k}: {v}" for k, v in (extra or {}).items()]
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    with contextlib.suppress(ConnectionError):
        await writer.drain()


def entries_json(entries: list[Entry]) -> list[dict[str, Any]]:
    return [e.as_json() for e in entries]
