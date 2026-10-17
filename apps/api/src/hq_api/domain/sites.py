"""Rule-based site checks (contract §16.4): the site list as data.

The list is seeded from seed/sites.yaml and edited by the owner afterwards
(PUT /api/v1/ops/sites). Nothing here knows a company or a URL.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from hq_api.db import Tx

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "sites.yaml"
DEFAULT_EXPECT = {"status": 200}
# Names that only exist inside a private network (the hub's own services have
# single-label names: postgres, api, opa, ...).
INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa", ".intranet")
RESOLVE_TIMEOUT_S = 3.0

Resolve = Callable[[str], Awaitable[list[str]]]


async def resolve(host: str) -> list[str]:
    """The addresses a host name resolves to (empty when it does not resolve)."""
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), RESOLVE_TIMEOUT_S
        )
    except (OSError, TimeoutError):
        return []
    return sorted({str(i[4][0]) for i in infos})


def _not_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return True
    # RFC 1918 (the hub's 10.10.1.0/24 and the neighbours too), loopback,
    # link-local, CGNAT, multicast, reserved, unspecified: anything not global.
    return not ip.is_global


async def internal_reason(url: str, resolver: Resolve = resolve) -> str | None:
    """Why a monitored URL may not be checked (prompt 5.1 §3): a private or
    internal address, as written or as resolved. None when it is public (or
    does not resolve at all: that is a DNS failure the checker reports)."""
    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    if not host:
        return "no host"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith(INTERNAL_SUFFIXES):
            return "an internal name"
        if any(_not_public(a) for a in await resolver(host)):
            return "resolves to a private or internal address"
        return None
    return "a private or internal address" if _not_public(host) else None


@lru_cache(maxsize=1)
def seeded() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("sites") or [])


async def seed(tx: Tx) -> int:
    """Adds missing (company, url) rows; canary rows follow the file's `enabled`."""
    added = 0
    for s in seeded():
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=s["company"])
        if co is None:
            continue  # a company this hub does not have (yet)
        row = await tx.first(
            """INSERT INTO ops.sites (company_id, url, kind, method, expect, interval_s, enabled, canary)
               VALUES (:co, :url, :kind, :method, CAST(:expect AS jsonb), :interval, :enabled, :canary)
               ON CONFLICT (company_id, url) DO NOTHING RETURNING id""",
            co=co,
            url=s["url"],
            kind=s.get("kind", "web"),
            method=s.get("method", "GET"),
            expect=json.dumps(s.get("expect") or DEFAULT_EXPECT),
            interval=int(s.get("interval_s", 300)),
            enabled=bool(s.get("enabled", True)),
            canary=bool(s.get("canary", False)),
        )
        added += row is not None
        if row is None and s.get("canary"):
            await tx.exec(
                """UPDATE ops.sites SET enabled = :enabled
                   WHERE company_id = :co AND url = :url AND canary AND enabled IS DISTINCT FROM :enabled""",
                co=co,
                url=s["url"],
                enabled=bool(s.get("enabled", True)),
            )
    return added
