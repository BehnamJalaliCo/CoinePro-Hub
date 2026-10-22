"""Settings from the environment (no secret here: the Hetzner token and the
owner's public keys are read from OpenBao at the moment of work)."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field

Net = ipaddress.IPv4Network | ipaddress.IPv6Network


def _nets(name: str, default: str) -> tuple[Net, ...]:
    raw = os.environ.get(name, default)
    return tuple(ipaddress.ip_network(x.strip()) for x in raw.split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: int(os.environ.get("PROVISIONER_PORT", "8110")))
    # Who may call this service's API (compose's fixed subnet of hq-prov: the api).
    api_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("PROVISIONER_API_CLIENTS", "172.30.10.0/24")
    )
    hub_url: str = field(
        default_factory=lambda: os.environ.get("HQ_API_INTERNAL_URL", "http://api:8000")
    )
    openbao_addr: str = field(
        default_factory=lambda: os.environ.get("OPENBAO_ADDR", "http://openbao:8200")
    )
    approle_file: str = field(
        default_factory=lambda: os.environ.get(
            "OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json"
        )
    )
    hetzner_url: str = field(
        default_factory=lambda: os.environ.get("HETZNER_API_URL", "https://api.hetzner.cloud/v1")
    )
    templates_dir: str = field(
        default_factory=lambda: os.environ.get("PROVISIONER_TEMPLATES", "/app/templates")
    )
    # Where a new server reports its cloud-init results (the hub's public
    # HTTPS; the one-time token goes in the Authorization header, never the URL).
    callback_url: str = field(
        default_factory=lambda: os.environ.get(
            "PROVISIONER_CALLBACK_URL", "https://hq.coinepro.com/api/v1/provisioning/callback"
        )
    )
    callback_ttl_s: int = field(
        default_factory=lambda: int(os.environ.get("PROVISIONER_CALLBACK_TTL_S", "3600"))
    )
    poll_s: float = field(default_factory=lambda: float(os.environ.get("PROVISIONER_POLL_S", "15")))
    # How long a step may wait (server running, the callback).
    boot_wait_s: float = field(
        default_factory=lambda: float(os.environ.get("PROVISIONER_BOOT_WAIT_S", "600"))
    )
    callback_wait_s: float = field(
        default_factory=lambda: float(os.environ.get("PROVISIONER_CALLBACK_WAIT_S", "3600"))
    )
    hetzner_poll_s: float = field(
        default_factory=lambda: float(os.environ.get("PROVISIONER_HETZNER_POLL_S", "2"))
    )
    # The company networks the provisioner makes (never an existing network).
    network_range: str = field(
        default_factory=lambda: os.environ.get("PROVISIONER_NETWORK_RANGE", "10.20.0.0/16")
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
