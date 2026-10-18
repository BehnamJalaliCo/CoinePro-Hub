"""Settings from the environment (non-secret; egress holds no secret of its own)."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field

Net = ipaddress.IPv4Network | ipaddress.IPv6Network


def _nets(name: str, default: str) -> tuple[Net, ...]:
    raw = os.environ.get(name, default)
    return tuple(ipaddress.ip_network(x.strip()) for x in raw.split(",") if x.strip())


def _hosts(name: str, default: str) -> frozenset[str]:
    raw = os.environ.get(name, default)
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


@dataclass(frozen=True)
class Settings:
    api_port: int = field(default_factory=lambda: int(os.environ.get("EGRESS_PORT", "8090")))
    browser_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_BROWSER_PROXY_PORT", "3128"))
    )
    gateway_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_GATEWAY_PROXY_PORT", "3129"))
    )
    # Who may call what (compose's fixed subnets: hq-egress-api, hq-browser).
    api_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_API_CLIENTS", "172.30.8.0/24")
    )
    gateway_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_GATEWAY_PROXY_CLIENTS", "172.30.8.0/24")
    )
    browser_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_BROWSER_PROXY_CLIENTS", "172.30.9.0/24")
    )
    searxng_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_SEARXNG_URL", "http://searxng:8080")
    )
    browser_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_BROWSER_URL", "http://browser:8095")
    )
    # The proxy as the browser reaches it (on its own network).
    browser_proxy_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_BROWSER_PROXY_URL", "http://egress:3128")
    )
    hub_hosts: frozenset[str] = field(
        default_factory=lambda: _hosts("EGRESS_HUB_HOSTS", "hq.coinepro.com")
    )
    fetch_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_FETCH_TIMEOUT_S", "15"))
    )
    # One call's caps (a run's and a company's are the api's).
    max_call_bytes: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_MAX_CALL_BYTES", str(20 * 1024 * 1024)))
    )
    browse_call_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_BROWSE_CALL_S", "20"))
    )
    # One call's whole time (every hop, a slow server, the parsing): below the
    # gateway's 25 s for a tool, so the call's entries always come back to it.
    call_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_CALL_DEADLINE_S", "20"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
