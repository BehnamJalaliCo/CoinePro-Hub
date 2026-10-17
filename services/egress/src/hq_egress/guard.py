"""The egress guard (prompt 07 §2.3, contract §18.7): where an agent's request
may go. The guard resolves a name itself and checks every address it would
connect to; the connection is then made to that checked address (net.py), so
a name cannot resolve to one address for the check and another for the
connect (DNS rebinding). Redirects are checked again, hop by hop.

Blocked: loopback, link-local (and so the cloud metadata address
169.254.169.254), RFC 1918 (the hub's private network 10.10.1.0/24 and its
production neighbours among them), CGNAT, IPv6 private/ULA/link-local, IPv4
embedded in IPv6 (mapped, 6to4, Teredo, NAT64) when the embedded address is
not public, every other non-global range; single-label and internal names
(Docker's service names); the hub's own /internal; ports other than 80 and
443 unless a service account's policy lists the port for its own host.
"""

from __future__ import annotations

import asyncio
import ipaddress
import posixpath
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

IP = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

DEFAULT_PORTS = frozenset({80, 443})
SCHEMES = frozenset({"http", "https"})
INTERNAL_SUFFIXES = (
    ".internal",
    ".local",
    ".localhost",
    ".localdomain",
    ".lan",
    ".home",
    ".home.arpa",
    ".corp",
    ".intranet",
    ".docker",
)
METADATA = ipaddress.ip_address("169.254.169.254")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
NAT64 = ipaddress.ip_network("64:ff9b::/96")


class Blocked(Exception):
    """The request may not leave: `reason` is a stable code for the log."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail
        self.entries: list[Any] = []  # the log entries up to the refusal (net.py)


def classify(ip: IP) -> str | None:
    """None for a public address; else why it is blocked."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or (ip.sixtofour if ip.sixtofour else None)
        if embedded is None and ip.teredo:
            embedded = ip.teredo[1]
        if embedded is None and ip in NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            inner = classify(embedded)
            return f"embedded_{inner}" if inner else None
    if ip == METADATA:
        return "metadata"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT:
        return "cgnat"
    if ip.is_private:
        return "private_address"
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved or not ip.is_global:
        return "reserved_address"
    return None


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    out: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in out:
            out.append(addr)
    return out


@dataclass
class Target:
    scheme: str
    host: str
    port: int
    path: str


@dataclass
class Guard:
    """`hub_hosts`: the hub's own names (its /internal is never reachable; the
    browser may not open them at all). `allow`: test-only exceptions (never set
    from the environment)."""

    hub_hosts: frozenset[str] = frozenset()
    resolver: Resolver = system_resolver
    allow: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()
    extra_ports: dict[str, frozenset[int]] = field(default_factory=dict)

    def ports_for(self, host: str, extra: Iterable[int] = ()) -> frozenset[int]:
        return DEFAULT_PORTS | self.extra_ports.get(host, frozenset()) | frozenset(extra)

    def target(self, url: str, *, extra_ports: Iterable[int] = ()) -> Target:
        """Scheme, name, port and path rules of one URL (no DNS yet)."""
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise Blocked("bad_url") from exc
        scheme = (parts.scheme or "").lower()
        if scheme not in SCHEMES:
            raise Blocked("scheme_not_allowed", scheme)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host or parts.username is not None or parts.password is not None:
            raise Blocked("bad_url")
        port = port or (443 if scheme == "https" else 80)
        t = Target(scheme, host, port, parts.path or "/")
        self.check_name(t.host)
        if port not in self.ports_for(host, extra_ports):
            raise Blocked("port_not_allowed", str(port))
        if self.is_hub(host) and _internal_path(t.path):
            raise Blocked("hub_internal")
        return t

    def is_hub(self, host: str) -> bool:
        return host in self.hub_hosts

    def check_name(self, host: str) -> None:
        literal = _literal(host)
        if literal is not None:
            reason = classify(literal)
            if reason and not self._allowed(literal):
                raise Blocked(reason)
            return
        if "." not in host:
            raise Blocked("internal_name", host)
        if host.endswith(INTERNAL_SUFFIXES) or host in ("localhost",):
            raise Blocked("internal_name", host)

    async def addresses(self, host: str, port: int) -> list[str]:
        """The checked addresses of `host` (all must be public: one private
        answer blocks the name, so a mixed answer cannot be raced)."""
        self.check_name(host)
        literal = _literal(host)
        if literal is not None:
            return [str(literal)]
        try:
            found = await asyncio.wait_for(self.resolver(host, port), timeout=5)
        except (OSError, TimeoutError) as exc:
            raise Blocked("dns_failed", host) from exc
        if not found:
            raise Blocked("dns_failed", host)
        for addr in found:
            ip = ipaddress.ip_address(addr.split("%")[0])
            reason = classify(ip)
            if reason and not self._allowed(ip):
                raise Blocked(reason, host)
        return found

    def _allowed(self, ip: IP) -> bool:
        return any(ip in net for net in self.allow)


def _literal(host: str) -> IP | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _internal_path(path: str) -> bool:
    """/internal however it is spelled (percent-encoded, doubled slashes,
    dot segments, backslashes): what the hub's own proxy would route there."""
    p = path
    for _ in range(3):
        p = unquote(p)
    p = posixpath.normpath("/" + p.replace("\\", "/")).lower()
    return p == "/internal" or p.startswith("/internal/")
