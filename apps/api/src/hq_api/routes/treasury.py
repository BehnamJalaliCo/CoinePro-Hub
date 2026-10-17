"""Token Treasury, read side of llm.* (contract §10) and the owner's
controls over connections, assignments and budgets (🔏).

Cost source: `equiv_cost_usd` and `cost_usd` come from our price table in
llm.connections (the router writes them); the SDK's own figure stays in
meta.sdk_cost_usd. Keys are write-only: stored in OpenBao, never returned.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from hq_api import pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import org, pricing
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["treasury"])
E = responses(401, 403, 404, 409, 422)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SCOPES = ("holding", "company", "department", "role", "task_class")
THRESHOLDS = (100, 90, 70)


# ------------------------------------------------------------------ models --
class Totals(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    thinking_tokens: int
    cost_usd: Decimal
    equiv_cost_usd: Decimal


class BudgetUse(BaseModel):
    company: str
    scope_type: str
    scope_ref: str
    period: str
    token_limit: int | None
    usd_limit: Decimal | None
    tokens_used: int
    usd_used: Decimal
    pct: float | None
    level: int


class Consumer(BaseModel):
    actor: str
    company: str
    calls: int
    tokens: int
    usd: Decimal


class Summary(BaseModel):
    period: str
    period_start: datetime
    company: str | None
    totals: Totals
    budgets: list[BudgetUse]
    top_consumers: list[Consumer]


class BreakdownRow(BaseModel):
    key: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    equiv_cost_usd: Decimal


class Call(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime | None
    company: str
    department: str | None
    actor: str
    work_ref: str | None
    task_class: str
    priority: int
    caller: str
    connection: str | None
    model: str | None
    effort: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    thinking_tokens: int | None
    cost_usd: Decimal | None
    equiv_cost_usd: Decimal | None
    latency_ms: int | None
    status: str
    error_class: str | None


class WhatIf(BaseModel):
    model: str
    calls: int
    priced_calls: int
    actual_usd: Decimal
    what_if_usd: Decimal | None
    difference_usd: Decimal | None
    source_url: str | None
    as_of: str | None


class Connection(BaseModel):
    id: UUID
    key: str
    kind: str
    provider: str
    display_name: str
    status: str
    status_reason: str | None
    quota_reset_at: datetime | None
    has_secret_ref: bool
    models: list[str]
    default_model: str | None
    pricing: dict[str, Any]
    limits: dict[str, Any]
    fallback_priority: int | None
    updated_at: datetime


class Price(Model):
    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    cache_read: Decimal | None = Field(default=None, ge=0)
    cache_write: Decimal | None = Field(default=None, ge=0)
    cache_write_1h: Decimal | None = Field(default=None, ge=0)
    long_prompt: dict[str, Any] | None = None
    source_url: str = Field(pattern=r"^https://", max_length=500)
    as_of: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ConnectionPatch(Model):
    status: Literal["enabled", "disabled"] | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    pricing: dict[str, Price] | None = None


class SecretIn(Model):
    secret: str = Field(min_length=8, max_length=8192, repr=False)


class SecretOut(BaseModel):
    connection: str
    stored: bool


class AssignmentIn(Model):
    scope_type: Literal["holding", "company", "department", "role", "task_class"]
    scope_ref: str = Field(min_length=1, max_length=100)
    connection: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=100)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    note: str | None = Field(default=None, max_length=500)


class Assignment(BaseModel):
    scope_type: str
    scope_ref: str
    connection: str | None
    model: str | None
    effort: str | None
    note: str | None


class Resolved(BaseModel):
    company: str
    department: str | None
    connection: str | None
    model: str | None
    effort: str | None


class Assignments(BaseModel):
    assignments: list[Assignment]
    resolved: list[Resolved]


class AssignmentsPut(Model):
    assignments: list[AssignmentIn] = Field(min_length=1, max_length=200)


class BudgetIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    scope_type: Literal["holding", "company", "department", "role", "task_class"]
    scope_ref: str = Field(min_length=1, max_length=100)
    period: Literal["day", "month"]
    token_limit: int | None = Field(default=None, gt=0)
    usd_limit: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)
    enabled: bool = True

    @field_validator("usd_limit")
    @classmethod
    def _one_limit(cls, v: Decimal | None, info: Any) -> Decimal | None:
        if v is None and info.data.get("token_limit") is None:
            raise ValueError("token_limit or usd_limit is required")
        return v


class BudgetsPut(Model):
    budgets: list[BudgetIn] = Field(min_length=1, max_length=200)


# ----------------------------------------------------------------- helpers --
def period_start(period: str, now: datetime | None = None) -> datetime:
    n = (now or datetime.now(UTC)).astimezone(UTC)
    day = n.replace(hour=0, minute=0, second=0, microsecond=0)
    return day if period == "day" else day.replace(day=1)


TOTALS = """count(*) AS calls,
    COALESCE(sum(c.input_tokens), 0) AS input_tokens, COALESCE(sum(c.output_tokens), 0) AS output_tokens,
    COALESCE(sum(c.cache_read_tokens), 0) AS cache_read_tokens,
    COALESCE(sum(c.cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(sum(c.cost_usd), 0) AS cost_usd, COALESCE(sum(c.equiv_cost_usd), 0) AS equiv_cost_usd"""


def level_of(pct: float | None) -> int:
    if pct is None:
        return 0
    return next((t for t in THRESHOLDS if pct >= t), 0)


# ---------------------------------------------------------------- read side --
@router.get("/treasury/summary", response_model=Summary, responses=E)
async def treasury_summary(
    period: Literal["day", "month"] = "month",
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> Summary:
    """Totals (tokens by kind, `cost_usd`, `equiv_cost_usd`), budget use with
    the 70/90/100 thresholds, and the top 5 consumers."""
    start = period_start(period)
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        t = await tx.one(
            f"""SELECT {TOTALS}, COALESCE(sum(c.thinking_tokens), 0) AS thinking_tokens FROM llm.calls c
                WHERE c.started_at >= :s AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)""",  # noqa: S608 - composed from module constants; values are bound
            s=start,
            co=co.id if co else None,
        )
        budgets = await tx.all(
            """SELECT b.*, c.code AS company,
                      COALESCE(u.tokens, 0) AS tokens_used, COALESCE(u.usd, 0) AS usd_used
               FROM llm.budgets b JOIN core.companies c ON c.id = b.company_id
               LEFT JOIN llm.usage u ON u.scope_type = b.scope_type AND u.scope_ref = b.scope_ref
                    AND u.period = b.period AND u.period_start = :ps
               WHERE b.enabled AND b.period = :period AND (CAST(:co AS uuid) IS NULL OR b.company_id = :co)
               ORDER BY c.code, b.scope_type, b.scope_ref""",
            ps=start.date(),
            period=period,
            co=co.id if co else None,
        )
        top = await tx.all(
            """SELECT c.actor_ref AS actor, co.code AS company, count(*) AS calls,
                      COALESCE(sum(COALESCE(c.input_tokens, 0) + COALESCE(c.output_tokens, 0)
                          + COALESCE(c.cache_read_tokens, 0) + COALESCE(c.cache_write_tokens, 0)), 0) AS tokens,
                      COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd
               FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
               WHERE c.started_at >= :s AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
               GROUP BY c.actor_ref, co.code ORDER BY usd DESC, tokens DESC LIMIT 5""",
            s=start,
            co=co.id if co else None,
        )
    uses = []
    for b in budgets:
        pcts = []
        if b["token_limit"]:
            pcts.append(100.0 * b["tokens_used"] / b["token_limit"])
        if b["usd_limit"]:
            pcts.append(100.0 * float(b["usd_used"]) / float(b["usd_limit"]))
        pct = round(max(pcts), 1) if pcts else None
        uses.append(
            BudgetUse(
                company=b["company"],
                scope_type=b["scope_type"],
                scope_ref=b["scope_ref"],
                period=b["period"],
                token_limit=b["token_limit"],
                usd_limit=b["usd_limit"],
                tokens_used=b["tokens_used"],
                usd_used=b["usd_used"],
                pct=pct,
                level=level_of(pct),
            )
        )
    return Summary(
        period=period,
        period_start=start,
        company=company,
        totals=Totals(**t),
        budgets=uses,
        top_consumers=[Consumer(**r) for r in top],
    )


BREAKDOWN_KEYS = {
    "company": "co.code",
    "department": "c.department",
    "actor": "c.actor_ref",
    "model": "c.model",
    "connection": "cn.key",
    "task_class": "c.task_class",
    "priority": "'P' || c.priority",
}


@router.get("/treasury/breakdown", response_model=list[BreakdownRow], responses=E)
async def treasury_breakdown(
    by: Literal[
        "company", "department", "actor", "model", "connection", "task_class", "priority"
    ] = "company",
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> list[BreakdownRow]:
    """Grouped totals; the default window is the current month."""
    start = from_ or period_start("month")
    end = to or datetime.now(UTC) + timedelta(seconds=1)
    co = await ctx.hub.companies.by_code(company) if company else None
    key = BREAKDOWN_KEYS[by]
    async with ctx.tx() as tx:
        rows = await tx.all(
            f"""SELECT {key} AS key, {TOTALS}
                FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
                LEFT JOIN llm.connections cn ON cn.id = c.connection_id
                WHERE c.started_at >= :s AND c.started_at < :e
                  AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
                GROUP BY 1
                ORDER BY COALESCE(sum(c.equiv_cost_usd), 0) + COALESCE(sum(c.cost_usd), 0) DESC,
                         count(*) DESC
                LIMIT 500""",  # noqa: S608
            s=start,
            e=end,
            co=co.id if co else None,
        )
    return [BreakdownRow(**r) for r in rows]


@router.get("/treasury/calls", response_model=Page[Call], responses=E)
async def treasury_calls(
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    actor: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, pattern=r"^[a-z_]{2,30}$"),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Call]:
    """Ledger rows, metadata only: never prompt or response text."""
    after_t, after_id = pagination.time_id(cursor)
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT c.id, c.started_at, c.finished_at, co.code AS company, c.department, c.actor_ref AS actor,
                      c.work_ref, c.task_class, c.priority, c.caller, cn.key AS connection, c.model, c.effort,
                      c.input_tokens, c.output_tokens, c.cache_read_tokens, c.cache_write_tokens,
                      c.thinking_tokens, c.cost_usd, c.equiv_cost_usd, c.latency_ms, c.status, c.error_class
               FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
               LEFT JOIN llm.connections cn ON cn.id = c.connection_id
               WHERE (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
                 AND (CAST(:actor AS text) IS NULL OR c.actor_ref = :actor)
                 AND (CAST(:status AS text) IS NULL OR c.status = :status)
                 AND (CAST(:after_t AS timestamptz) IS NULL
                      OR (c.started_at, c.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
               ORDER BY c.started_at DESC, c.id DESC LIMIT :lim""",
            co=co.id if co else None,
            actor=actor,
            status=status,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("started_at", "id"))
    return Page(items=[Call(**r) for r in items], next_cursor=nxt)


@router.get("/treasury/what-if", response_model=WhatIf, responses=E)
async def treasury_what_if(
    model: str = Query(min_length=3, max_length=100),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> WhatIf:
    """ "What would these calls have cost on model X", from our price table
    (the first connection that prices X), token counts unchanged."""
    start = from_ or period_start("month")
    end = to or datetime.now(UTC) + timedelta(seconds=1)
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        price_row = await tx.first(
            """SELECT pricing FROM llm.connections WHERE pricing ? :m
               ORDER BY kind = 'claude_subscription' DESC, key LIMIT 1""",
            m=model,
        )
        rows = await tx.all(
            """SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                      COALESCE((meta ->> 'cache_write_1h_tokens')::int, 0) AS w1h,
                      COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0) AS actual
               FROM llm.calls c
               WHERE c.started_at >= :s AND c.started_at < :e AND c.input_tokens IS NOT NULL
                 AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
               LIMIT 200000""",
            s=start,
            e=end,
            co=co.id if co else None,
        )
    actual = sum((Decimal(r["actual"]) for r in rows), Decimal(0))
    if price_row is None:
        return WhatIf(
            model=model,
            calls=len(rows),
            priced_calls=0,
            actual_usd=actual,
            what_if_usd=None,
            difference_usd=None,
            source_url=None,
            as_of=None,
        )
    table = price_row["pricing"]
    total = Decimal(0)
    priced = 0
    for r in rows:
        c = pricing.cost_usd(
            table,
            model,
            input_tokens=r["input_tokens"] or 0,
            output_tokens=r["output_tokens"] or 0,
            cache_read_tokens=r["cache_read_tokens"] or 0,
            cache_write_tokens=r["cache_write_tokens"] or 0,
            cache_write_1h_tokens=r["w1h"],
        )
        if c is not None:
            total += c
            priced += 1
    entry = table.get(model) or {}
    return WhatIf(
        model=model,
        calls=len(rows),
        priced_calls=priced,
        actual_usd=actual,
        what_if_usd=total,
        difference_usd=total - actual,
        source_url=entry.get("source_url"),
        as_of=entry.get("as_of"),
    )


# ------------------------------------------------------------- connections --
CONN_SQL = """SELECT id, key, kind, provider, display_name, status, status_reason, quota_reset_at,
                     secret_ref IS NOT NULL AS has_secret_ref, models, default_model, pricing, limits,
                     fallback_priority, updated_at FROM llm.connections"""


@router.get("/connections", response_model=list[Connection], responses=E)
async def list_connections(ctx: Ctx = Depends(owner_ctx)) -> list[Connection]:
    """The registry without secrets (keys are never readable)."""
    async with ctx.tx() as tx:
        rows = await tx.all(CONN_SQL + " ORDER BY kind = 'claude_subscription' DESC, key")
    return [Connection(**r) for r in rows]


@router.patch("/connections/{id}", response_model=Connection, responses=E)
async def update_connection(
    id: UUID, body: ConnectionPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Connection:
    """🔏 step-up `connection.update` (target = the id). Status, name and the
    price table (every price with `source_url` and `as_of`)."""
    fields = body.model_dump(exclude_unset=True, mode="json")
    async with ctx.tx() as tx:
        cur = await tx.one(CONN_SQL + " WHERE id = :id FOR UPDATE", id=id)
        await stepup.consume(tx, request, ctx.who, "connection.update", str(id))
        if "pricing" in fields:
            merged = {
                **cur["pricing"],
                **{
                    k: {kk: vv for kk, vv in v.items() if vv is not None}
                    for k, v in fields["pricing"].items()
                },
            }
            await tx.exec(
                "UPDATE llm.connections SET pricing = CAST(:p AS jsonb), updated_at = now() WHERE id = :id",
                id=id,
                p=json.dumps(merged),
            )
        if "status" in fields:
            await tx.exec(
                """UPDATE llm.connections SET status = :s, status_reason = 'set by the owner',
                       status_changed_at = now(), updated_at = now() WHERE id = :id""",
                id=id,
                s=fields["status"],
            )
        if "display_name" in fields:
            await tx.exec(
                "UPDATE llm.connections SET display_name = :n, updated_at = now() WHERE id = :id",
                id=id,
                n=fields["display_name"],
            )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.update",
            action_class="A2",
            target_kind="connection",
            target_ref=cur["key"],
            summary="fields: " + ",".join(sorted(fields)),
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="connection.update",
            target_kind="connection",
            target_ref=cur["key"],
            data={"fields": sorted(fields), "status": fields.get("status")},
        )
        return Connection(**await tx.one(CONN_SQL + " WHERE id = :id", id=id))


@router.post("/connections/{id}/secret", response_model=SecretOut, responses={**E, 503: E[422]})
async def set_connection_secret(
    id: UUID, body: SecretIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> SecretOut:
    """🔏 step-up `connection.secret` (target = the id). Write-only: the key goes
    to OpenBao at the connection's secret_ref; it is never returned, logged or
    audited (the audit records only that it changed)."""
    bao = ctx.hub.bao
    async with ctx.tx() as tx:
        cur = await tx.one("SELECT key, secret_ref FROM llm.connections WHERE id = :id", id=id)
        await stepup.consume(tx, request, ctx.who, "connection.secret", str(id))
        if not cur["secret_ref"] or not str(cur["secret_ref"]).startswith("kv/llm-connections/"):
            raise ApiError(422, "validation_failed", "this connection takes no key")
        if bao is None:
            raise ApiError(503, "channel_not_configured", "the secret store is not available")
        await bao.write_kv(str(cur["secret_ref"]).removeprefix("kv/"), {"api_key": body.secret})
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.secret",
            action_class="A2",
            target_kind="connection",
            target_ref=cur["key"],
            summary="key replaced",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="connection.secret",
            target_kind="connection",
            target_ref=cur["key"],
        )
    return SecretOut(connection=cur["key"], stored=True)


# ------------------------------------------------------ assignments, budgets --
async def _assignments(ctx: Ctx, tx: Any) -> Assignments:
    rows = await tx.all(
        """SELECT a.scope_type, a.scope_ref, cn.key AS connection, a.model, a.effort, a.note
           FROM llm.assignments a LEFT JOIN llm.connections cn ON cn.id = a.connection_id
           ORDER BY array_position(ARRAY['holding','company','department','role','task_class'], a.scope_type),
                    a.scope_ref"""
    )
    holding = await ctx.hub.companies.holding()
    resolver = org.Assignments(rows, holding.code)
    depts = await tx.all(
        """SELECT c.code AS company, d.code AS department FROM core.companies c
           LEFT JOIN core.departments d ON d.company_id = c.id ORDER BY c.code, d.sort"""
    )
    resolved = []
    seen: set[str] = set()
    for r in depts:
        if r["company"] not in seen:
            seen.add(r["company"])
            m = resolver.resolve(r["company"], None, "-", "-")
            resolved.append(
                Resolved(
                    company=r["company"],
                    department=None,
                    connection=m.connection if m else None,
                    model=m.model if m else None,
                    effort=m.effort if m else None,
                )
            )
        if r["department"]:
            m = resolver.resolve(r["company"], r["department"], "-", "-")
            resolved.append(
                Resolved(
                    company=r["company"],
                    department=r["department"],
                    connection=m.connection if m else None,
                    model=m.model if m else None,
                    effort=m.effort if m else None,
                )
            )
    return Assignments(assignments=[Assignment(**r) for r in rows], resolved=resolved)


@router.get("/assignments", response_model=Assignments, responses=E)
async def get_assignments(ctx: Ctx = Depends(owner_ctx)) -> Assignments:
    """holding -> company -> department -> role -> task class, plus the resolved
    choice for every company and department."""
    async with ctx.tx() as tx:
        return await _assignments(ctx, tx)


@router.put("/assignments", response_model=Assignments, responses=E)
async def put_assignments(
    body: AssignmentsPut, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Assignments:
    """🔏 step-up `assignments.update` (target `*`). Upserts the listed levels."""
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "assignments.update", "*")
        for a in body.assignments:
            if a.connection is None and a.model is None and a.effort is None:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={"assignments": "set connection, model or effort"},
                )
            conn_id = None
            if a.connection:
                conn_id = await tx.scalar(
                    "SELECT id FROM llm.connections WHERE key = :k", k=a.connection
                )
                if conn_id is None:
                    raise ApiError(
                        422, "validation_failed", fields={"connection": f"unknown {a.connection}"}
                    )
            await tx.exec(
                """INSERT INTO llm.assignments (scope_type, scope_ref, connection_id, model, effort, note)
                   VALUES (:st, :sr, :cn, :m, :e, :note)
                   ON CONFLICT (scope_type, scope_ref) DO UPDATE
                       SET connection_id = EXCLUDED.connection_id, model = EXCLUDED.model,
                           effort = EXCLUDED.effort, note = EXCLUDED.note, updated_at = now()""",
                st=a.scope_type,
                sr=a.scope_ref,
                cn=conn_id,
                m=a.model,
                e=a.effort,
                note=a.note,
            )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="assignments.update",
            action_class="A2",
            target_kind="assignments",
            target_ref="*",
            summary=f"{len(body.assignments)} level(s)",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="assignments.update",
            target_kind="assignments",
            target_ref="*",
            data={"levels": [f"{a.scope_type}:{a.scope_ref}" for a in body.assignments]},
        )
        return await _assignments(ctx, tx)


@router.get("/budgets", response_model=list[BudgetUse], responses=E)
async def get_budgets(ctx: Ctx = Depends(owner_ctx)) -> list[BudgetUse]:
    """Every budget with its current-period use."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT b.*, c.code AS company, COALESCE(u.tokens, 0) AS tokens_used, COALESCE(u.usd, 0) AS usd_used
               FROM llm.budgets b JOIN core.companies c ON c.id = b.company_id
               LEFT JOIN llm.usage u ON u.scope_type = b.scope_type AND u.scope_ref = b.scope_ref
                    AND u.period = b.period
                    AND u.period_start = CASE b.period WHEN 'day' THEN CAST(now() AT TIME ZONE 'UTC' AS date)
                                         ELSE CAST(date_trunc('month', now() AT TIME ZONE 'UTC') AS date) END
               ORDER BY c.code, b.scope_type, b.scope_ref, b.period"""
        )
    out = []
    for b in rows:
        pcts = []
        if b["token_limit"]:
            pcts.append(100.0 * b["tokens_used"] / b["token_limit"])
        if b["usd_limit"]:
            pcts.append(100.0 * float(b["usd_used"]) / float(b["usd_limit"]))
        pct = round(max(pcts), 1) if pcts else None
        out.append(
            BudgetUse(
                company=b["company"],
                scope_type=b["scope_type"],
                scope_ref=b["scope_ref"],
                period=b["period"],
                token_limit=b["token_limit"],
                usd_limit=b["usd_limit"],
                tokens_used=b["tokens_used"],
                usd_used=b["usd_used"],
                pct=pct,
                level=level_of(pct),
            )
        )
    return out


@router.put("/budgets", response_model=list[BudgetUse], responses=E)
async def put_budgets(
    body: BudgetsPut, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> list[BudgetUse]:
    """🔏 step-up `budgets.update` (target `*`). Upserts per scope and period."""
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "budgets.update", "*")
        for b in body.budgets:
            co = await ctx.hub.companies.by_code(b.company)
            await tx.exec(
                """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit, usd_limit, enabled)
                   VALUES (:co, :st, :sr, :p, :tl, :ul, :en)
                   ON CONFLICT (scope_type, scope_ref, period) DO UPDATE
                       SET token_limit = EXCLUDED.token_limit, usd_limit = EXCLUDED.usd_limit,
                           enabled = EXCLUDED.enabled, updated_at = now()""",
                co=co.id,
                st=b.scope_type,
                sr=b.scope_ref,
                p=b.period,
                tl=b.token_limit,
                ul=b.usd_limit,
                en=b.enabled,
            )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="budgets.update",
            action_class="A2",
            target_kind="budgets",
            target_ref="*",
            summary=f"{len(body.budgets)} budget(s)",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="budgets.update",
            target_kind="budgets",
            target_ref="*",
            data={"budgets": [f"{b.scope_type}:{b.scope_ref}/{b.period}" for b in body.budgets]},
        )
    return await get_budgets(ctx)
