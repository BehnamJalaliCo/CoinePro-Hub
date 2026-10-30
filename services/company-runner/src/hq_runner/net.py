"""How the runner reaches the hub (contract §26.1a).

With a hub IP (`--hub-ip 10.10.1.4`) the runner connects to that address over
the holding's private network while TLS keeps the hub's hostname: the SNI, the
Host header and certificate verification all use the hostname; only the TCP
connection goes to the given IP. Verification is never turned off.

If the private address does not answer, the runner falls back to ordinary DNS
and says so: `via` is "public". Without a hub IP, `via` is "private" when the
hostname itself resolves to a private address (an /etc/hosts line), otherwise
"public". The private route is tried again every few minutes.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import socket
import ssl
import time
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpcore
import httpx

log = logging.getLogger("hq_runner.net")

PROBE_TIMEOUT_S = 3.0
RETRY_PRIVATE_EVERY_S = 300.0
RTT_EVERY_S = 30.0


class PinnedAsyncBackend(httpcore.AsyncNetworkBackend):
    """Opens TCP connections for `host` to `ip`; everything else (TLS with the
    original server_hostname) is left to httpcore."""

    def __init__(self, host: str, ip: str, inner: httpcore.AsyncNetworkBackend | None = None):
        self.host = host.lower()
        self.ip = ip
        self.inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        target = self.ip if host.lower() == self.host else host
        return await self.inner.connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:  # pragma: no cover - never used
        return await self.inner.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


class PinnedSyncBackend(httpcore.NetworkBackend):
    """The same for the synchronous client (the Claude hook helper)."""

    def __init__(self, host: str, ip: str, inner: httpcore.NetworkBackend | None = None):
        self.host = host.lower()
        self.ip = ip
        self.inner = inner or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        target = self.ip if host.lower() == self.host else host
        return self.inner.connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:  # pragma: no cover - never used
        return self.inner.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    def sleep(self, seconds: float) -> None:  # pragma: no cover - never used
        self.inner.sleep(seconds)


def ssl_context(ca_file: str | None = None) -> ssl.SSLContext:
    """Full verification; `ca_file` adds a CA (tests, or a hub with its own CA)."""
    ctx = httpx.create_ssl_context()
    if ca_file:
        ctx.load_verify_locations(cafile=ca_file)
    return ctx


def hub_parts(hub: str) -> tuple[str, str, int]:
    """(scheme, host, port) of the hub URL. Plain http is accepted only for a
    loopback host (tests)."""
    parts = urlsplit(hub)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError(f"hub must be an https URL, got {hub!r}")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("hub must use https")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme, parts.hostname, port


def async_transport(
    hub: str, hub_ip: str | None, ca_file: str | None = None
) -> httpx.AsyncHTTPTransport:
    ctx = ssl_context(ca_file)
    transport = httpx.AsyncHTTPTransport(verify=ctx, retries=0)
    if hub_ip:
        _, host, _ = hub_parts(hub)
        # httpx has no public hook for name resolution; the pool is rebuilt with
        # the same settings and a backend that pins the hub's hostname to its IP.
        transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=ctx,
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=30.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=PinnedAsyncBackend(host, hub_ip),
        )
    return transport


def sync_transport(hub: str, hub_ip: str | None, ca_file: str | None = None) -> httpx.HTTPTransport:
    ctx = ssl_context(ca_file)
    transport = httpx.HTTPTransport(verify=ctx, retries=0)
    if hub_ip:
        _, host, _ = hub_parts(hub)
        transport._pool = httpcore.ConnectionPool(
            ssl_context=ctx,
            max_connections=4,
            keepalive_expiry=10.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=PinnedSyncBackend(host, hub_ip),
        )
    return transport


ProbeFn = Callable[[str, int, float], Awaitable[float]]


async def tcp_probe(host: str, port: int, limit_s: float = PROBE_TIMEOUT_S) -> float:
    """Milliseconds to open a TCP connection; raises OSError/TimeoutError."""
    start = time.monotonic()
    _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), limit_s)
    ms = (time.monotonic() - start) * 1000
    writer.close()
    with contextlib.suppress(OSError, TimeoutError):
        await asyncio.wait_for(writer.wait_closed(), 1.0)
    return ms


PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
)


def is_private_address(addr: str) -> bool:
    """A private-network address (RFC 1918, CGNAT, IPv6 ULA)."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip.version == n.version and ip in n for n in PRIVATE_NETWORKS)


async def resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return [str(info[4][0]) for info in infos]


@dataclass
class RouteState:
    via: str  # "private" | "public"
    pinned_ip: str | None  # the IP the hostname is pinned to, or None for plain DNS
    rtt_ms: float | None


class Route:
    """Chooses and remembers the way to the hub; builds the matching client."""

    def __init__(
        self,
        hub: str,
        hub_ip: str | None,
        *,
        ca_file: str | None = None,
        probe: ProbeFn = tcp_probe,
        resolver: Callable[[str, int], Awaitable[list[str]]] = resolve,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hub = hub.rstrip("/")
        self.hub_ip = hub_ip
        self.ca_file = ca_file
        self.probe = probe
        self.resolver = resolver
        self._fixed_transport = transport
        self.clock = clock
        _, self.host, self.port = hub_parts(self.hub)
        self.state = RouteState(via="public", pinned_ip=None, rtt_ms=None)
        self._client: httpx.AsyncClient | None = None
        self._selected_at = -1e18
        self._rtt_at = -1e18

    @property
    def via(self) -> str:
        return self.state.via

    @property
    def rtt_ms(self) -> float | None:
        return self.state.rtt_ms

    async def select(self) -> RouteState:
        """Tries the private IP first (when given), else plain DNS."""
        self._selected_at = self.clock()
        new: RouteState
        if self.hub_ip:
            try:
                ms = await self.probe(self.hub_ip, self.port, PROBE_TIMEOUT_S)
                new = RouteState("private", self.hub_ip, round(ms, 1))
            except (OSError, TimeoutError) as exc:
                log.warning(
                    "hub private address %s:%s did not answer (%s); using the public address",
                    self.hub_ip,
                    self.port,
                    type(exc).__name__,
                )
                new = await self._public()
        else:
            new = await self._public()
        self._rtt_at = self.clock()
        await self._swap(new)
        return self.state

    async def _public(self) -> RouteState:
        addrs = await self.resolver(self.host, self.port)
        via = "private" if addrs and is_private_address(addrs[0]) else "public"
        rtt: float | None = None
        try:
            rtt = round(await self.probe(self.host, self.port, PROBE_TIMEOUT_S), 1)
        except (OSError, TimeoutError):
            rtt = None
        return RouteState(via, None, rtt)

    async def _swap(self, new: RouteState) -> None:
        changed = self._client is None or new.pinned_ip != self.state.pinned_ip
        self.state = new
        if changed:
            old, self._client = self._client, None
            if old is not None:
                await old.aclose()

    async def refresh(self) -> None:
        """Called before each poll: measures the round trip now and then and
        moves back to the private route when it answers again."""
        now = self.clock()
        if (
            self.hub_ip
            and self.state.pinned_ip is None
            and now - self._selected_at >= RETRY_PRIVATE_EVERY_S
        ):
            await self.select()
            return
        if now - self._rtt_at >= RTT_EVERY_S:
            self._rtt_at = now
            target = self.state.pinned_ip or self.host
            try:
                self.state.rtt_ms = round(await self.probe(target, self.port, PROBE_TIMEOUT_S), 1)
            except (OSError, TimeoutError):
                self.state.rtt_ms = None

    async def connect_failed(self) -> None:
        """A request could not connect: leave the private route for the public one."""
        if self.state.pinned_ip is not None:
            log.warning(
                "connection over the private address failed; switching to the public address"
            )
            self._selected_at = self.clock()
            await self._swap(await self._public())

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            transport = self._fixed_transport or async_transport(
                self.hub, self.state.pinned_ip, self.ca_file
            )
            self._client = httpx.AsyncClient(
                base_url=self.hub, transport=transport, timeout=httpx.Timeout(30.0, connect=10.0)
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def source_address_towards(ip: str | None) -> str | None:
    """The local address the kernel would use to reach `ip` (no packet is sent)."""
    if not ip:
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((ip, 9))
            addr = str(s.getsockname()[0])
    except OSError:
        return None
    return addr if is_private_address(addr) else None
