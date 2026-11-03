"""⟨1.11⟩ Prompt 21 part 3 (contract §29.12): what can be measured and managed.

GET  /companies/{code}/connections               every kind (the ten), its state,
                                                 non-secret config, secret set|missing
                                                 and the last week's figures
PUT  /companies/{code}/connections/{kind}        {config, label_fa?}: 🔏 connection.config
                                                 (target = SHA-256 of the body) when it
                                                 widens what is read
PUT  /companies/{code}/connections/{kind}/secret {secret}: write-only, 🔏
                                                 connection.secret (target <CODE>:<kind>);
                                                 into OpenBao kv/hq/growth/<CODE>/<kind>
POST /companies/{code}/connections/{kind}/test   one read now (on the worker, through
                                                 egress), the connection after it
GET  /connections/guides/{kind}                  the one-page Persian guide
/internal/v1/connections                         connection.read (A0): a company's
                                                 connections and their figures
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import Field

from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import connections as CN
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup

router = APIRouter(tags=["connections"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
KIND = "^(" + "|".join(CN.KINDS) + ")$"
TEST_WORKFLOW = "ConnectionTest"
MAX_CONFIG = 20_000


class ConfigIn(Model):
    config: dict[str, Any]
    label_fa: str | None = Field(default=None, min_length=1, max_length=200)


class SecretIn(Model):
    secret: str = Field(min_length=8, max_length=20_000, repr=False)


class SecretOut(Model):
    company: str
    kind: str
    secret: str  # always "set": the value is never returned


@router.get("/companies/{code}/connections", response_model=list[CN.Connection], responses=E)
async def list_company_connections(code: str, ctx: Ctx = Depends(owner_ctx)) -> list[CN.Connection]:
    """Every kind in the contract's order of work; a kind the company has
    not started reads `not_connected` with what it needs."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await CN.list_for(tx, company)


@router.put("/companies/{code}/connections/{kind}", response_model=CN.Connection, responses=E)
async def put_connection(
    code: str,
    body: ConfigIn,
    request: Request,
    kind: str = Path(pattern=KIND),
    ctx: Ctx = Depends(owner_ctx),
) -> CN.Connection:
    """The connection's non-secret config (handles, site, property, the
    IG-Hub command). 🔏 `connection.config` (target = SHA-256 of the exact
    body) when it widens what is read; a narrower config needs none. A
    secret is never put here (`secret`, `token`, `key`, `password`: refused)."""
    company = await ctx.hub.companies.by_code(code)
    raw = json.dumps(body.config, ensure_ascii=False)
    if len(raw) > MAX_CONFIG:
        raise ApiError(422, "validation_failed", fields={"config": "too large"})
    lowered = raw.lower()
    if any(w in lowered for w in ('"secret"', '"token"', '"password"', '"api_key"', "private_key")):
        raise ApiError(
            422, "validation_failed", fields={"config": "a secret goes through /secret only"}
        )
    async with ctx.tx() as tx:
        cur = await tx.first(
            "SELECT config FROM growth.connections WHERE company_id = :co AND kind = :k FOR UPDATE",
            co=company.id,
            k=kind,
        )
        wider = CN.widens((cur or {}).get("config") or {}, body.config)
        if wider:
            await stepup.consume(
                tx, request, ctx.who, "connection.config", await stepup.body_target(request)
            )
        await CN.set_config(tx, company, kind, body.config, body.label_fa)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="connection.config",
            action_class="A2",
            target_kind="connection",
            target_ref=f"{code}:{kind}",
            summary="config widened" if wider else "config narrowed",
            step_up=wider,
        )
        await ctx.interaction(
            tx,
            company_id=company.id,
            kind="setting",
            action="connection.config",
            target_kind="connection",
            target_ref=f"{code}:{kind}",
            data={"keys": sorted(body.config)[:20], "wider": wider},
        )
        await ctx.emit(tx, code, "connection.updated", None, {"kind": kind, "config": True})
        return await CN.one_for(tx, company, kind)


@router.put(
    "/companies/{code}/connections/{kind}/secret",
    response_model=SecretOut,
    responses={**E, 503: E[422]},
)
async def put_connection_secret(
    code: str,
    body: SecretIn,
    request: Request,
    kind: str = Path(pattern=KIND),
    ctx: Ctx = Depends(owner_ctx),
) -> SecretOut:
    """🔏 `connection.secret` (target `<CODE>:<kind>`). Write-only: the value
    goes to OpenBao (kv/hq/growth/<CODE>/<kind>) and is never returned,
    logged or audited (the audit says only that it was set)."""
    company = await ctx.hub.companies.by_code(code)
    if CN.SECRET.get(kind) is False:
        raise ApiError(422, "validation_failed", fields={"kind": "this connection takes no secret"})
    bao = ctx.hub.bao
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "connection.secret", f"{code}:{kind}")
        if bao is None:
            raise ApiError(503, "channel_not_configured", "the secret store is not available")
        await CN.write_secret(bao, code, kind, body.secret)
        await tx.exec(
            """INSERT INTO growth.connections (company_id, kind, label_fa, secret_set, secret_set_at)
               VALUES (:co, :k, :l, true, now())
               ON CONFLICT (company_id, kind) DO UPDATE SET secret_set = true,
                   secret_set_at = now(), last_error_fa = NULL, updated_at = now()""",
            co=company.id,
            k=kind,
            l=CN.LABEL_FA[kind],
        )
        row = await tx.one(
            "SELECT * FROM growth.connections WHERE company_id = :co AND kind = :k",
            co=company.id,
            k=kind,
        )
        await tx.exec(
            "UPDATE growth.connections SET state = :st WHERE id = :id",
            id=row["id"],
            st=CN.state_of(kind, row),
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="connection.secret",
            action_class="A2",
            target_kind="connection",
            target_ref=f"{code}:{kind}",
            summary="secret set",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=company.id,
            kind="setting",
            action="connection.secret",
            target_kind="connection",
            target_ref=f"{code}:{kind}",
        )
        await ctx.emit(tx, code, "connection.updated", None, {"kind": kind, "secret": "set"})
    return SecretOut(company=code, kind=kind, secret="set")  # noqa: S106 - a state, not a value


async def run_test(hub: Any, company_id: Any, kind: str) -> None:
    """One read on the worker (only it reaches egress), awaited."""
    client = getattr(hub, "temporal", None)
    if client is None:
        raise ApiError(503, "channel_not_configured", "the worker is not reachable from here")
    try:
        await client.execute_workflow(
            TEST_WORKFLOW,
            args=[str(company_id), kind],
            id=f"connection-test-{kind}-{uuid.uuid4().hex[:12]}",
            task_queue=hub.settings.task_queue,
            execution_timeout=timedelta(seconds=150),
        )
    except Exception as exc:
        raise ApiError(503, "channel_not_configured", "the read could not run now") from exc


@router.post(
    "/companies/{code}/connections/{kind}/test",
    response_model=CN.Connection,
    responses={**E, 503: E[422]},
)
async def read_connection_now(
    code: str, kind: str = Path(pattern=KIND), ctx: Ctx = Depends(owner_ctx)
) -> CN.Connection:
    """One read now: the figures stored, the state and the Persian error (if
    any) as the daily read would leave them. Instagram queues its IG-Hub job
    and answers at once (the figures come when the job is done)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        if not await tx.scalar(
            "SELECT 1 FROM growth.connections WHERE company_id = :co AND kind = :k",
            co=company.id,
            k=kind,
        ):
            raise ApiError(404, "not_found", "this connection is not started yet")
    await run_test(ctx.hub, company.id, kind)
    async with ctx.tx() as tx:
        await ctx.audit(
            tx,
            company_id=company.id,
            action="connection.test",
            action_class="A0",
            target_kind="connection",
            target_ref=f"{code}:{kind}",
        )
        return await CN.one_for(tx, company, kind)


@router.get("/connections/guides/{kind}", response_model=CN.Guide, responses=E)
async def get_guide(kind: str = Path(pattern=KIND), ctx: Ctx = Depends(owner_ctx)) -> CN.Guide:
    """The one-page Persian guide for the owner: which account, which
    permission, what to paste (seed/connection_guides/<kind>.md)."""
    del ctx
    return CN.guide(kind)


@internal_router.get("/connections", response_model=list[CN.Connection], responses=E)
async def agent_connections(
    company: str | None = Query(default=None, pattern=CODE),
    kind: str | None = Query(default=None, pattern=KIND),
    days: int = Query(default=7, ge=1, le=60),
    ctx: Ctx = Depends(internal_ctx),
) -> list[CN.Connection]:
    """connection.read: a company's connections and their daily figures (no
    secret, ever: only `set` or `missing`). An agent reads its own company; a
    holding reader (the advisor, the overseer) any."""
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    code = company or str(who.company)
    await allow(ctx, "connection.read", {"company": code, "charter": who.charter})
    co = await ctx.hub.companies.by_code(code)
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        found = await CN.list_for(tx, co, days=days)
    return [c for c in found if kind is None or c.kind == kind]
