"""FastAPI dependencies: who is calling, CSRF, rate limits.

/api/v1 is the owner's API (cookie on the web, Bearer on Android).
/internal/v1 is for agents (signed per-run token) and services (token whose
SHA-256 is in OpenBao). /internal is never routed by Caddy.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import Depends, Request

from hq_api.errors import ApiError
from hq_api.hub import Hub, get_hub
from hq_api.principal import OWNER_CODE, Principal
from hq_api.security import agent_tokens, sessions
from hq_common.tokens import bearer, digest

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
REPLAYS = agent_tokens.ReplayGuard()


def client_ip(request: Request) -> str:
    # Caddy is the only hop in front of the api (X-Forwarded-For set by it).
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(request: Request) -> str:
    return hashlib.sha256(client_ip(request).encode()).hexdigest()[:32]


def check_csrf(hub: Hub, request: Request) -> None:
    """Web mutations need X-HQ-Client: web and our exact Origin (contract §2)."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin", "").rstrip("/").encode("utf-8", "surrogateescape")
    expected = hub.settings.public_origin.encode()
    if (
        request.headers.get("x-hq-client") != "web"
        or not expected
        or not hmac.compare_digest(origin, expected)
    ):
        raise ApiError(403, "csrf_rejected")


async def owner(request: Request, hub: Hub = Depends(get_hub)) -> Principal:
    token = bearer(request.headers.get("authorization"))
    via_cookie = False
    if token is None:
        token = request.cookies.get(sessions.COOKIE)
        via_cookie = token is not None
    if not token:
        raise ApiError(401, "unauthenticated")
    if via_cookie:
        check_csrf(hub, request)
    async with hub.db.raw() as tx:
        row = await sessions.lookup(tx, hub.settings, token)
    if row is None:
        raise ApiError(401, "unauthenticated")
    who = Principal(
        kind="owner",
        code=OWNER_CODE,
        role="owner",
        session_id=row["id"],
        via_cookie=via_cookie,
    )
    hub.limiter.check(f"owner:{row['id']}", hub.settings.rate_per_principal)
    request.state.principal = who
    return who


async def internal(request: Request, hub: Hub = Depends(get_hub)) -> Principal:
    # /internal is never routed by the edge: a proxied request does not belong here.
    if "x-forwarded-for" in request.headers:
        raise ApiError(403, "forbidden", "/internal is not reachable through a proxy")
    token = bearer(request.headers.get("authorization"))
    if not token:
        raise ApiError(401, "unauthenticated")
    if token.startswith(agent_tokens.PREFIX + "."):
        try:
            claims = agent_tokens.verify(hub.secrets.agent_token_key, token)
        except agent_tokens.InvalidToken as exc:
            raise ApiError(401, "unauthenticated") from exc
        # The same token with the same request id twice is a replay.
        rid = request.headers.get("x-request-id")
        if rid and not REPLAYS.first_use(f"{claims.jti}:{rid}", claims.exp):
            raise ApiError(401, "unauthenticated", "replayed request")
        who = await agent_principal(hub, claims.employee, run=claims.run)
    else:
        name = next(
            (
                n
                for n, d in hub.secrets.service_tokens.items()
                if hmac.compare_digest(digest(token), d)
            ),
            None,
        )
        if name is None:
            raise ApiError(401, "unauthenticated")
        who = Principal(kind="service", code=name, role="service")
    hub.limiter.check(f"{who.kind}:{who.code}", hub.settings.rate_per_principal)
    request.state.principal = who
    return who


async def agent_principal(hub: Hub, code: str, *, run: str | None = None) -> Principal:
    """The employee behind an agent token. The token's run must be in the run
    registry (agents.runs), belong to that employee and be running: a token
    outlives neither its run nor its hour."""
    try:
        run_id = str(uuid.UUID(run)) if run is not None else None
    except ValueError:
        run_id = None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        row: dict[str, Any] | None = await tx.first(
            """SELECT e.id, e.code, e.kind, e.status, e.role, e.company_id, c.code AS company,
                      e.department_id, d.code AS department,
                      (SELECT r.state = 'running' AND r.token_expires_at > now()
                         FROM agents.runs r
                        WHERE r.id = CAST(:run AS uuid) AND r.employee_id = e.id) AS run_ok
               FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id
               LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE e.code = :code""",
            code=code,
            run=run_id,
        )
    if row is None or row["status"] == "dismissed" or row["run_ok"] is not True:
        raise ApiError(401, "unauthenticated")
    return Principal(
        kind="agent",
        code=row["code"],
        role=row["kind"],
        company=row["company"],
        company_id=row["company_id"],
        department=row["department"],
        department_id=row["department_id"],
        employee_id=row["id"],
        status=row["status"],
        run_id=run_id,
        charter=row["role"],
    )


def auth_rate_limit(request: Request, hub: Hub = Depends(get_hub)) -> None:
    hub.limiter.check(f"auth-ip:{ip_hash(request)}", hub.settings.auth_rate_per_ip)
