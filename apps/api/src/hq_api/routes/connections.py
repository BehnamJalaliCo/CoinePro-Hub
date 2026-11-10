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
import logging
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

log = logging.getLogger("hq_api.routes.connections")
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
        raise ApiError(409, "channel_not_configured", "the worker is not reachable from here")
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


class ConnectionSetIn(Model):
    """⟨2026-11-08⟩ H2 `connection.set`: a connection's non-secret settings, by an agent."""

    company: str | None = Field(default=None, pattern=CODE)
    kind: str = Field(pattern=KIND)
    accounts: list[str] | None = Field(default=None, max_length=20)
    via: str | None = Field(default=None, max_length=20)
    server: dict[str, Any] | None = None
    read_command: str | None = Field(default=None, max_length=500)
    publish_command: str | None = Field(default=None, max_length=500)  # ⟨2026-11-10⟩ §44.5
    channels: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    site_url: str | None = Field(default=None, max_length=300)
    channel_id: str | None = Field(default=None, max_length=64)
    handle: str | None = Field(default=None, max_length=64)
    property_id: str | None = Field(default=None, max_length=32)


SET_ROLES = ("ceo", "media_director")  # with the technical charters (TECH), see connections.rego


@internal_router.post("/connections/set", response_model=CN.Connection, responses=E)
async def agent_connection_set(
    body: ConnectionSetIn, ctx: Ctx = Depends(internal_ctx)
) -> CN.Connection:
    """⟨2026-11-08⟩ H2 connection.set (A2): a company's CEO, media director or technical role
    registers a connection's non-secret settings — Instagram's account names and that they are
    read through IG-Hub (`via: ig_hub`, `server`), a read-only `read_command` (the same check the
    daily read applies), Telegram channels, a site's address, a YouTube channel id. Another
    company's connection by its technical role under the linked rule (H1). Never a secret (the
    owner's `make growth-secret`): refused with the field named. Audited; the state recomputed;
    a step in the order's session when the run belongs to one."""
    from hq_api.domain import links as LK
    from hq_api.domain import order_report as OR
    from hq_api.domain import sessions as SE
    from hq_api.routes.servers import _reachable, _technical

    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    code = body.company or str(who.company)
    company = await ctx.hub.companies.find(code)
    lib = ctx.hub.charters
    technical = _technical(lib, who.charter)
    linked = False
    if company is not None and company.id != who.company_id and technical:
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
            linked = await _reachable(ctx, tx, who, company.id)
    await allow(
        ctx,
        "connection.set",
        {"company": code, "charter": who.charter, "technical": technical, "linked": linked},
    )
    if company is None:
        raise ApiError(404, "not_found", f"company {code}", message_fa=f"شرکتی با کد {code} نیست.")
    fields = body.model_dump(exclude_none=True, exclude={"company", "kind"})
    async with ctx.hub.db.tx(list({who.company_id, company.id})) as tx:
        cur = await tx.first(
            "SELECT config FROM growth.connections WHERE company_id = :co AND kind = :k FOR UPDATE",
            co=company.id,
            k=body.kind,
        )
        raw = cur["config"] if cur is not None else {}
        current = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        config = CN.agent_config(body.kind, current, fields)
        await CN.set_config(tx, company, body.kind, config, None)
        keys = ", ".join(sorted(fields))
        for co_id in {who.company_id, company.id}:
            await ctx.audit(
                tx,
                company_id=co_id,
                action="connection.set",
                action_class="A2",
                target_kind="connection",
                target_ref=f"{code}:{body.kind}",
                summary=f"{who.code} set {keys}" + (" (linked)" if linked else ""),
            )
        await ctx.emit(tx, code, "connection.updated", None, {"kind": body.kind, "config": True})
        out = await CN.one_for(tx, company, body.kind)
    del LK
    # the order's session hears it (the run's work, when it belongs to an order)
    if who.run_id is not None:
        try:
            async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
                work_id = await tx.scalar(
                    "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid)", r=who.run_id
                )
                ref = await OR.order_of_work(tx, work_id) if work_id is not None else None
                if ref is not None:
                    emp = await tx.first(
                        """SELECT e.title_fa, c.name_fa FROM core.employees e
                           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
                        c=who.code,
                    )
                    who_fa = OR.who_fa(emp["title_fa"], emp["name_fa"]) if emp else "کارمند"
                    # (the handles stay in the connection itself: a dotted name reads as a tool
                    # key to the owner's plain-language filter)
                    accounts = out.config.get("accounts") or []
                    line = f"اتصال {CN.LABEL_FA[body.kind]} {company.name_fa} ثبت شد"
                    if accounts:
                        line += f": {len(accounts)} حساب"
                    await SE.step(tx, ref, who_fa, line, remember_line=line)
        except Exception:  # noqa: BLE001 - the session's line never fails the setting
            log.warning("connection.set: the session's step failed", extra={"company": code})
    return out


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
