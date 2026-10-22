"""The revenue radar (prompt 10 §2, contract §19.1).

Owner (/api/v1):
    GET  /revenue/summary            ?period=day|week|month&company
    GET  /revenue/days               ?company&account&from&to (unpaged, at most 400 rows)
    GET  /revenue/accounts
    POST /revenue/accounts           🔏 revenue.account (the body's SHA-256), Idempotency-Key;
                                     adds or changes one by company + exchange; the key is
                                     never in the API (`make account-secret`)
    POST /revenue/accounts/{id}/pull ?from&to (at most REVENUE_PULL_MAX_DAYS) · Idempotency-Key
Agents (/internal/v1):
    POST /revenue/read               revenue.read (A0; OPA op revenue.read)
The worker's connector (/internal/v1, the worker's service token only):
    POST /egress/connectors/{adapter}/pull   one call's account (its secret for that call)
                                             and its egress-log reservation, for the gateway
    POST /egress/connectors/{adapter}/log    that call's egress entries
Every pull the worker carries out asks hq_api.domain.gate first and is
`skipped` while the holding (or the company) is locked.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from hq_api import idempotency
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import affiliate as A
from hq_api.domain import egress as G
from hq_api.domain import gate
from hq_api.domain import revenue as V
from hq_api.errors import ApiError, responses
from hq_api.routes.agent_tools import _company, read_tx
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model
from hq_api.security import stepup

log = logging.getLogger("hq_api.routes.revenue")
router = APIRouter(tags=["revenue"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428, 429)
EXCHANGE = r"^[a-z][a-z0-9_-]{1,30}$"
ACCOUNT_KEY = r"^[a-z0-9][a-z0-9_.-]{1,40}$"
ADAPTER = r"^[a-z][a-z0-9-]{1,40}$"


class RevenueAccount(Model):
    id: str
    company: str
    exchange: str
    adapter: str
    service_account: str
    title_fa: str
    status: Literal["not_configured", "ok", "error"]
    last_pull_at: datetime | None = None
    last_error: str | None = None
    version: int


class CoinRow(Model):
    coin: str
    amount: Decimal
    usdt: Decimal | None = None
    price_source: str | None = None


class DaySource(Model):
    adapter: str | None = None
    endpoints: list[str] = Field(default_factory=list)


class RevenueDay(Model):
    company: str
    account: str
    day: date
    commission_usdt: Decimal
    by_coin: list[CoinRow]
    fees_usdt: Decimal | None = None
    volume_usdt: Decimal | None = None
    new_invitees: int
    active_traders: int | None = None
    deposits_usdt: Decimal | None = None
    complete: bool
    pulled_at: datetime
    source: DaySource


class CompanyRevenue(Model):
    company: str
    usdt: Decimal
    token_cost_usd: Decimal
    net_usd: Decimal
    share: float | None = None


class AccountRevenue(Model):
    account: str
    company: str
    usdt: Decimal


class TrendPoint(Model):
    day: date
    usdt: Decimal


class SummaryAlert(Model):
    kind: Literal["drop", "pull_failed", "incomplete"]
    company: str
    account: str | None = None
    note_fa: str


class RevenueSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    period: Literal["day", "week", "month"]
    from_: date = Field(alias="from")
    to: date
    total_usdt: Decimal
    prev_total_usdt: Decimal | None = None
    by_company: list[CompanyRevenue]
    by_account: list[AccountRevenue]
    trend: list[TrendPoint]
    alerts: list[SummaryAlert]


class RevenueAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=CODE)
    exchange: str = Field(pattern=EXCHANGE)
    adapter: Literal["lbank-affiliate-v2"] = "lbank-affiliate-v2"
    service_account: str = Field(pattern=ACCOUNT_KEY)
    title_fa: str = Field(min_length=1, max_length=200)


class RevenuePull(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    id: str
    account: str
    kind: Literal["scheduled", "retry", "manual", "backfill"]
    from_: date = Field(alias="from")
    to: date
    state: Literal["queued", "running", "ok", "incomplete", "failed", "skipped"]
    skipped_reason: str | None = None
    days_complete: int
    days_incomplete: int
    error_code: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


# ------------------------------------------------------------------ owner --
async def _company_id(ctx: Ctx, code: str | None) -> UUID | None:
    if code is None:
        return None
    try:
        return (await ctx.hub.companies.by_code(code)).id
    except ApiError as exc:
        raise ApiError(404, "not_found", "no such company") from exc


@router.get("/revenue/summary", response_model=RevenueSummary, responses=E)
async def revenue_summary(
    period: Literal["day", "week", "month"] = "day",
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Commission per company and account against the Token Treasury's cost
    of the same days (`net_usd = usdt - token_cost_usd`; USDT taken as USD)."""
    co = await _company_id(ctx, company)
    async with ctx.tx() as tx:
        return RevenueSummary.model_validate(await V.summary(tx, period, co))


@router.get("/revenue/days", response_model=list[RevenueDay], responses=E)
async def revenue_days(
    request: Request,
    company: str | None = Query(default=None, pattern=CODE),
    account: UUID | None = None,
    to: date | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """RevenueDay rows, newest first (at most 400): `from` and `to` are the
    exchange's settlement days (lbank: UTC+8)."""
    end = to or A.last_settled_day()
    start = V.parse_day(request.query_params.get("from"), "from") or end - timedelta(days=29)
    if start > end or (end - start).days >= 400:
        raise ApiError(422, "validation_failed", fields={"from": "at most 400 days, from <= to"})
    co = await _company_id(ctx, company)
    async with ctx.tx() as tx:
        rows = await V.days_list(tx, company_id=co, account_id=account, start=start, end=end)
    return [RevenueDay.model_validate(r) for r in rows]


@router.get("/revenue/accounts", response_model=list[RevenueAccount], responses=E)
async def list_revenue_accounts(ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Every affiliate account: its service account (never the key), the
    last pull and its error."""
    async with ctx.tx() as tx:
        return [RevenueAccount.model_validate(V.account_out(r)) for r in await V.accounts(tx)]


@router.post("/revenue/accounts", response_model=RevenueAccount, status_code=201, responses=E)
async def put_revenue_account(
    body: RevenueAccountIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 (`revenue.account`, target = SHA-256 of the exact body): which
    service account (a signer, `make account-secret` holds its key) pulls a
    company's commission from an exchange. Requires `Idempotency-Key`."""
    co = await _company_id(ctx, body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        step_up_id = await stepup.consume(
            tx, request, ctx.who, "revenue.account", await stepup.body_target(request)
        )
        await V.check_service_account(tx, body.adapter, body.service_account, body.company)
        row = await tx.one(
            """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
                   body_sha256, created_by_kind, created_by_code)
               VALUES (:co, :ex, :ad, :sa, :t, :h, 'owner', 'owner')
               ON CONFLICT (company_id, exchange) DO UPDATE SET adapter = EXCLUDED.adapter,
                   service_account = EXCLUDED.service_account, title_fa = EXCLUDED.title_fa,
                   body_sha256 = EXCLUDED.body_sha256, updated_at = now()
               RETURNING id""",
            co=co,
            ex=body.exchange,
            ad=body.adapter,
            sa=body.service_account,
            t=body.title_fa,
            h=await stepup.body_target(request),
        )
        acct = await V.account(tx, row["id"])
        await ctx.audit(
            tx,
            company_id=acct["company_id"],
            action="revenue.account",
            action_class="A2",
            target_kind="revenue_account",
            target_ref=str(acct["id"]),
            summary=f"{body.exchange} via {body.service_account} ({body.adapter})",
            step_up=step_up_id is not None,
        )
        out = RevenueAccount.model_validate(V.account_out(acct))
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post(
    "/revenue/accounts/{id}/pull", response_model=RevenuePull, status_code=202, responses=E
)
async def pull_now(
    id: UUID,
    request: Request,
    to: date | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """The owner's pull of `from`..`to` (at most REVENUE_PULL_MAX_DAYS settled
    days; default: the last settled day), through the same connector and rate
    limit as the schedule. Requires `Idempotency-Key`. While the holding is
    locked it is recorded `skipped` and nothing leaves the hub."""
    last = A.last_settled_day()
    end = to or last
    start = V.parse_day(request.query_params.get("from"), "from") or end
    limit = ctx.hub.settings.revenue_pull_max_days
    if start > end or end > last or (end - start).days >= limit:
        raise ApiError(
            422,
            "validation_failed",
            fields={"from": f"from <= to <= {last.isoformat()}, at most {limit} days"},
        )
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        acct = await V.account(tx, id)
        lock = await gate.automation_lock(tx, acct["company_id"])
        p = await V.create_pull(
            tx,
            acct,
            kind="manual",
            from_day=start,
            to_day=end,
            by_kind="owner",
            by_code="owner",
            state="skipped" if lock else "queued",
            skipped_reason=gate.REASONS.get(lock, lock) if lock else None,
        )
        await ctx.audit(
            tx,
            company_id=acct["company_id"],
            action="revenue.pull",
            action_class="A1",
            target_kind="revenue_account",
            target_ref=str(acct["id"]),
            summary=f"manual {start}..{end}" + (f" skipped: {lock}" if lock else ""),
        )
        out = RevenuePull.model_validate(V.pull_out(p))
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json", by_alias=True))
    if not lock:
        await _start_pull(ctx.hub, out.id)
    return out


async def _start_pull(hub: Any, pull_id: str) -> None:
    """Best effort: a queued manual pull the workflow never got is carried
    out by the next scheduled run (the database is the source of truth)."""
    client = getattr(hub, "temporal", None)
    if client is None:
        return
    try:
        from temporalio.common import WorkflowIDConflictPolicy

        await client.start_workflow(
            "RevenuePull",
            pull_id,
            id=f"revenue-pull-{pull_id}",
            task_queue=hub.settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - picked up by the next scheduled run
        log.warning("could not start a revenue pull", extra={"pull": pull_id})


# ----------------------------------------------------------------- agents --
class RevenueReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    company: str | None = Field(default=None, pattern=CODE)
    from_: date = Field(alias="from")
    to: date
    by: Literal["day", "company", "account"] = "day"


@internal_router.post("/revenue/read", responses=E)
async def revenue_read(body: RevenueReadIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """revenue.read (A0): commission and referrals by day, company and
    account, incomplete days marked, the treasury's cost beside it. A
    company's readers see their own company; the holding's advisor and
    overseer any company."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    if body.from_ > body.to or (body.to - body.from_).days >= 400:
        raise ApiError(422, "validation_failed", fields={"from": "at most 400 days, from <= to"})
    co = await _company(ctx, "revenue.read", body.company, charter=ctx.who.charter)
    async with read_tx(ctx) as tx:
        rows = await V.days_list(
            tx, company_id=co.id, account_id=None, start=body.from_, end=body.to
        )
        costs = await V.token_costs(tx, body.from_, body.to, co.id)
        alerts = await tx.all(
            """SELECT kind, day, note_fa FROM revenue.alerts WHERE company_id = :co
                 AND (day BETWEEN :s AND :e OR day IS NULL) ORDER BY created_at DESC LIMIT 20""",
            co=co.id,
            s=body.from_,
            e=body.to,
        )
    usdt = sum((Decimal(r["commission_usdt"]) for r in rows), Decimal(0))
    cost = costs.get(co.code, Decimal(0))
    out: dict[str, Any] = {
        "company": co.code,
        "from": body.from_.isoformat(),
        "to": body.to.isoformat(),
        "total_usdt": str(usdt),
        "token_cost_usd": str(cost),
        "net_usd": str(usdt - cost),
        "new_invitees": sum(int(r["new_invitees"]) for r in rows),
        "incomplete_days": sorted({r["day"] for r in rows if not r["complete"]}),
        "alerts": [
            {
                "kind": a["kind"],
                "day": a["day"].isoformat() if a["day"] else None,
                "note_fa": a["note_fa"],
            }
            for a in alerts
        ],
        "source": "revenue.days (affiliate pulls), llm.calls (Token Treasury)",
    }
    if body.by == "day":
        days: dict[str, dict[str, Any]] = {}
        for r in rows:
            d = days.setdefault(r["day"], {"day": r["day"], "usdt": Decimal(0), "new_invitees": 0,
                                           "complete": True})  # fmt: skip
            d["usdt"] += Decimal(r["commission_usdt"])
            d["new_invitees"] += int(r["new_invitees"])
            d["complete"] = d["complete"] and bool(r["complete"])
        out["days"] = [{**d, "usdt": str(d["usdt"])} for _, d in sorted(days.items())][-120:]
    elif body.by == "account":
        accts: dict[str, Decimal] = {}
        for r in rows:
            accts[r["account"]] = accts.get(r["account"], Decimal(0)) + Decimal(
                r["commission_usdt"]
            )
        out["accounts"] = [{"account": a, "usdt": str(v)} for a, v in sorted(accts.items())]
    return out


# ------------------------------------------------- the worker's connector --
class ConnectorPullIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=CODE)
    exchange: str = Field(pattern=EXCHANGE)
    endpoint: str = Field(pattern=r"^[a-z][a-z/._-]{1,60}$")
    tool: Literal["revenue.pull"] = "revenue.pull"


class ConnectorEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    tool: Literal["revenue.pull", "referral.check"] = "revenue.pull"
    kind: Literal["request"] = "request"
    cls: Literal["A0"] = Field(default="A0", alias="class")
    method: str = Field(min_length=1, max_length=10, pattern=r"^[A-Z0-9_-]{1,10}$")
    host: str = Field(min_length=1, max_length=255)
    status: int | None = Field(default=None, ge=100, le=999)
    bytes_in: int = Field(default=0, ge=0, le=2**62)
    bytes_out: int = Field(default=0, ge=0, le=2**62)
    ms: int = Field(default=0, ge=0, le=2**31 - 1)
    blocked_reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    requests: int = Field(default=1, ge=1, le=1_000_000)


class ConnectorLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=CODE)
    reservation: UUID | None = None
    entries: list[ConnectorEntry] = Field(default_factory=list, max_length=200)


WORKER = "worker"


async def _worker(ctx: Ctx, adapter: str, company: str) -> tuple[A.AdapterSpec, Any]:
    """The worker's service token only (OPA egress.connector), a known adapter."""
    if ctx.who.kind != "service":
        raise ApiError(403, "policy_denied", "the worker's connector only")
    await allow(ctx, "egress.connector", {"company": company, "adapter": adapter})
    spec = A.ADAPTERS.get(adapter)
    if spec is None:
        raise ApiError(404, "not_found", "unknown adapter")
    try:
        co = await ctx.hub.companies.by_code(company)
    except ApiError as exc:
        raise ApiError(404, "not_found", "no such company") from exc
    return spec, co


async def signer_account(
    ctx: Ctx, tx: Any, spec: A.AdapterSpec, company_id: UUID, company: str, exchange: str
) -> dict[str, Any]:
    """The company's revenue account on that exchange -> its service account
    (a signer of the adapter's kind) with its secret, for one call."""
    acct = await tx.first(
        "SELECT * FROM revenue.accounts WHERE company_id = :co AND exchange = :ex AND adapter = :ad",
        co=company_id,
        ex=exchange,
        ad=spec.name,
    )
    if acct is None:
        raise ApiError(409, "account_not_configured", "no revenue account for this exchange")
    row = await tx.first(
        "SELECT key, site, companies, policy FROM tools.accounts WHERE key = :k",
        k=acct["service_account"],
    )
    inject = ((row or {}).get("policy") or {}).get("inject") or {}
    if row is None or inject.get("kind") != "signer" or inject.get("signer") != spec.signer:
        raise ApiError(403, "policy_denied", "the service account is not this adapter's signer")
    if row["companies"] is not None and company not in row["companies"]:
        raise ApiError(403, "policy_denied", "account_not_for_this_company")
    secret = await G.read_secret(ctx.hub.bao, row["key"])
    if not secret:
        raise ApiError(409, "account_not_configured")
    ports = [int(p) for p in (row["policy"] or {}).get("ports") or [] if str(p).isdigit()][:5]
    return {
        "key": row["key"],
        "site": row["site"],
        "secret": secret,
        "inject": {"kind": "signer", "signer": spec.signer},
        "ports": ports,
        "allow": [],
    }


@internal_router.post("/egress/connectors/{adapter}/pull", responses=E)
async def connector_pull(
    adapter: str, body: ConnectorPullIn, ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    """For the gateway, on the worker's behalf: the account (with its secret,
    for this one call) of the company's exchange, and the call's row in the
    egress log, written now. The worker's connector is the ONLY user of a
    signer account (contract §19.1); a keyless endpoint gets no account."""
    spec, co = await _worker(ctx, adapter, body.company)
    if body.endpoint not in spec.endpoints:
        raise ApiError(404, "not_found", "unknown endpoint")
    async with ctx.hub.db.tx([co.id]) as tx:
        lock = await gate.automation_lock(tx, co.id)
        if lock is not None:
            raise ApiError(423, "company_locked", f"locked: {lock}")
        acct = None
        if body.endpoint not in A.PUBLIC_ENDPOINTS:
            acct = await signer_account(ctx, tx, spec, co.id, co.code, body.exchange)
        host = acct["site"] if acct else "public"
        reservation = await G.reserve_row(
            tx,
            company_id=co.id,
            actor=WORKER,
            run_id=None,
            entry={
                "tool": body.tool,
                "kind": "request",
                "class": "A0",
                "method": "POST",
                "host": host,
            },
        )
    return {
        "account": acct,
        "reservation": reservation,
        "max_bytes": min(ctx.hub.settings.egress_call_bytes, 2 * 1024 * 1024),
    }


@internal_router.post("/egress/connectors/{adapter}/log", status_code=204, responses=E)
async def connector_log(
    adapter: str, body: ConnectorLogIn, ctx: Ctx = Depends(internal_ctx)
) -> None:
    """The entries of one connector call (no secret: method, host, status,
    sizes, time); they settle its reservation."""
    _, co = await _worker(ctx, adapter, body.company)
    async with ctx.hub.db.tx([co.id]) as tx:
        call_id = None
        if body.reservation is not None and await G.own_reservation(
            tx, body.reservation, actor=WORKER, run_id=None
        ):
            call_id = body.reservation
        await G.record(
            tx,
            company_id=co.id,
            actor=WORKER,
            run_id=None,
            entries=[e.model_dump(by_alias=True) for e in body.entries],
            call_id=call_id,
        )
