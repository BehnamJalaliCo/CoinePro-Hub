"""A new connection's secret, verified at no token cost (prompt 12 §9,
contract §21.7).

POST /connections makes a connection `pending_secret`. Its secret arrives
either through the api's write-only POST /connections/{id}/secret (which moves
it to `verifying`) or through the owner's own `make connection-secret` in their
terminal (straight to OpenBao at the connection's secret_ref). Every
LLM_CONNECTION_VERIFY_INTERVAL_S this job:
  - moves a `pending_secret` connection whose secret is now in OpenBao to
    `verifying` (the terminal route);
  - verifies each `verifying` one with a call that spends no token: the
    provider's model list (GET .../models) -> `ready` (with verified_at), or
    `error` with a short status_reason. Never the secret, never the response
    body, in a reason, a log or an event.
Nothing is called while the holding's kill switch is engaged (the hub is not
launched yet): the connections wait in `verifying`. An `openai_compatible`
base URL is resolved first and refused on a private, loopback, link-local,
metadata or otherwise non-public address (the egress guard's rule).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("llm_router.verify")

# Where each supported provider lists its models (the call costs no token).
MODELS_URL = {
    "anthropic": "https://api.anthropic.com/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "deepseek": "https://api.deepseek.com/models",
    "mistral": "https://api.mistral.ai/v1/models",
}
TIMEOUT_S = 15.0

ReadSecret = Callable[[str], Awaitable[dict[str, Any]]]
Resolve = Callable[[str, int], Awaitable[list[str]]]


def not_public(address: str) -> str | None:
    """Why an address is not a public one (the egress guard's classes), or None."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "not an address"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if str(ip) in ("169.254.169.254", "100.100.100.200", "fd00:ec2::254"):
        return "metadata"
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"
    if ip.is_private:
        return "private"
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified or not ip.is_global:
        return "reserved"
    return None


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(i[4][0]) for i in infos})


def models_url(provider: str, api_base: str | None) -> str:
    if provider == "openai_compatible":
        if not api_base:
            raise ValueError("an openai_compatible connection needs its base URL")
        return api_base.rstrip("/") + "/models"
    url = MODELS_URL.get(provider)
    if url is None:
        raise ValueError(f"unsupported provider {provider!r}")
    return url


def auth_headers(provider: str, key: str) -> dict[str, str]:
    if provider == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    if provider in ("google", "gemini"):
        return {"x-goog-api-key": key}
    return {"Authorization": f"Bearer {key}"}


async def check(
    provider: str,
    api_base: str | None,
    key: str,
    *,
    client: httpx.AsyncClient,
    resolve: Resolve = _resolve,
) -> tuple[str, str]:
    """(status, reason): `ready` when the provider lists models with this key."""
    try:
        url = models_url(provider, api_base)
    except ValueError as exc:
        return "error", str(exc)[:200]
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return "error", "the base URL must be https"
    try:
        addresses = await resolve(parts.hostname, parts.port or 443)
    except OSError:
        return "error", "the provider's host does not resolve"
    bad = next((why for a in addresses if (why := not_public(a))), None)
    if bad or not addresses:
        return "error", f"the provider's host is not public ({bad or 'no address'})"
    try:
        r = await client.get(url, headers=auth_headers(provider, key), timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        return "error", f"the provider did not answer ({type(exc).__name__})"
    if r.status_code in (401, 403):
        return "error", f"the provider refused the key ({r.status_code})"
    if r.status_code != 200:
        return "error", f"the model list answered {r.status_code}"
    try:
        body = r.json()
    except ValueError:
        return "error", "the model list is not JSON"
    listed: Any = body
    if isinstance(body, dict):
        listed = body.get("data") or body.get("models") or []
    count = len(listed) if isinstance(listed, list) else 0
    return "ready", f"verified: {count} models listed"


async def scan(
    db: Any,
    read_secret: ReadSecret,
    lock_state: Callable[[str], Awaitable[str | None]],
    *,
    client: httpx.AsyncClient | None = None,
    resolve: Resolve = _resolve,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """One pass (see the module docstring). Returns counts, never a secret."""
    async with db.pool.acquire() as conn:
        holding = await conn.fetchval(
            "SELECT id::text FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
        )
        rows = await conn.fetch(
            """SELECT id::text, key, provider, status, secret_ref, api_base
               FROM llm.connections WHERE status IN ('pending_secret', 'verifying') AND kind = 'api'
               ORDER BY created_at"""
        )
    if not rows:
        return {"checked": 0}
    if holding is not None and await lock_state(holding) is not None:
        return {"checked": 0, "skipped": "holding_locked"}
    out = {"checked": 0, "ready": 0, "error": 0, "waiting": 0}
    own = client is None
    http = client or httpx.AsyncClient(follow_redirects=False)
    try:
        for r in rows:
            secret: dict[str, Any] | None = None
            if r["secret_ref"]:
                try:
                    secret = await read_secret(str(r["secret_ref"]).removeprefix("kv/"))
                except Exception:  # noqa: BLE001 - not there yet (or OpenBao away)
                    secret = None
            key = (secret or {}).get("api_key")
            if not key:
                out["waiting"] += 1  # pending_secret stays; verifying lost its secret: wait
                continue
            status, reason = await check(
                str(r["provider"]), r["api_base"], str(key), client=http, resolve=resolve
            )
            out["checked"] += 1
            out[status] += 1
            async with db.pool.acquire() as conn:
                await conn.execute(
                    """UPDATE llm.connections SET status = $2, status_reason = $3,
                           status_changed_at = $4,
                           verified_at = CASE WHEN $2 = 'ready' THEN $4 ELSE verified_at END,
                           updated_at = now()
                       WHERE id = $1::uuid AND status IN ('pending_secret', 'verifying')""",
                    r["id"],
                    status,
                    reason[:300],
                    now(),
                )
            log.info("connection verified", extra={"connection": r["key"], "status": status})
    finally:
        if own:
            await http.aclose()
    return out
