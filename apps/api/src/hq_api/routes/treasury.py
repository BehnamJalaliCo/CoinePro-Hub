"""Token Treasury, read side of llm.* (contract §10) and the owner's
controls over connections, assignments and budgets (🔏).

Cost source: `equiv_cost_usd` and `cost_usd` come from our price table in
llm.connections (the router writes them); the SDK's own figure stays in
meta.sdk_cost_usd. Keys are write-only: stored in OpenBao, never returned.
"""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import org, pricing
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
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
    version: int
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


DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WINDOW_DOC = (
    "A date (YYYY-MM-DD: that day in the owner's time zone; `to` counts its own day) "
    "or an ISO date-time (without a zone: the owner's time zone)."
)


def bound(raw: str | None, tz: ZoneInfo, *, end: bool) -> datetime | None:
    """One side of a window (6.1 §1.3): a bare date is the owner's day, and as
    `to` it includes that day; a time without a zone is the owner's time."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if DATE_ONLY.match(text):
        try:
            d = date.fromisoformat(text)
        except ValueError:
            d = None
        if d is not None:
            return datetime.combine(d + timedelta(days=1) if end else d, time.min, tzinfo=tz)
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(
            422, "validation_failed", fields={"to" if end else "from": "a date or an ISO date-time"}
        ) from None
    return t if t.tzinfo else t.replace(tzinfo=tz)


async def window(
    ctx: Ctx, from_raw: str | None, to_raw: str | None
) -> tuple[datetime, datetime, str]:
    """[start, end) and the owner's time zone; the default start is the first
    of the owner's month, the default end now."""
    async with ctx.tx() as tx:
        tzname = (
            await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
        )
    tz = ZoneInfo(tzname)
    start = bound(from_raw, tz, end=False)
    if start is None:
        start = datetime.now(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = bound(to_raw, tz, end=True) or datetime.now(UTC) + timedelta(seconds=1)
    if end <= start:
        raise ApiError(422, "validation_failed", fields={"to": "after from"})
    return start, end, tzname


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


MAX_DAYS = 400
# One row per day of [from, to] in the owner's zone, zeros included (a LEFT JOIN
# from the calendar, counting call ids, never rows of the calendar itself).
DAY_SQL = """
    WITH days AS (
        SELECT d::date AS day FROM generate_series(
            (CAST(:s AS timestamptz) AT TIME ZONE :tz)::date,
            ((CAST(:e AS timestamptz) - interval '1 microsecond') AT TIME ZONE :tz)::date,
            interval '1 day') AS d)
    SELECT to_char(days.day, 'YYYY-MM-DD') AS key, count(c.id) AS calls,
           COALESCE(sum(c.input_tokens), 0) AS input_tokens,
           COALESCE(sum(c.output_tokens), 0) AS output_tokens,
           COALESCE(sum(c.cache_read_tokens), 0) AS cache_read_tokens,
           COALESCE(sum(c.cache_write_tokens), 0) AS cache_write_tokens,
           COALESCE(sum(c.cost_usd), 0) AS cost_usd, COALESCE(sum(c.equiv_cost_usd), 0) AS equiv_cost_usd
    FROM days LEFT JOIN llm.calls c
      ON (c.started_at AT TIME ZONE :tz)::date = days.day
     AND c.started_at >= :s AND c.started_at < :e
     AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
    GROUP BY days.day ORDER BY days.day"""


@router.get("/treasury/breakdown", response_model=list[BreakdownRow], responses=E)
async def treasury_breakdown(
    by: Literal[
        "company", "department", "actor", "model", "connection", "task_class", "priority", "day"
    ] = "company",
    from_: str | None = Query(default=None, alias="from", max_length=40, description=WINDOW_DOC),
    to: str | None = Query(default=None, max_length=40, description=WINDOW_DOC),
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> list[BreakdownRow]:
    """Grouped totals; the default window is the current month. ⟨1.3⟩ `by=day`:
    one row per calendar day in the owner's time zone (key = ISO date),
    ascending, days without calls included with zeros, inside [from, to]."""
    start, end, tz = await window(ctx, from_, to)
    co = await ctx.hub.companies.by_code(company) if company else None
    if by == "day":
        if end - start > timedelta(days=MAX_DAYS):
            raise ApiError(422, "validation_failed", fields={"from": f"at most {MAX_DAYS} days"})
        async with ctx.tx() as tx:
            rows = await tx.all(DAY_SQL, s=start, e=end, tz=tz, co=co.id if co else None)
        return [BreakdownRow(**r) for r in rows]
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
    from_: str | None = Query(default=None, alias="from", max_length=40, description=WINDOW_DOC),
    to: str | None = Query(default=None, max_length=40, description=WINDOW_DOC),
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> WhatIf:
    """ "What would these calls have cost on model X", from our price table
    (the first connection that prices X), token counts unchanged."""
    start, end, _tz = await window(ctx, from_, to)
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
                     fallback_priority, version, updated_at FROM llm.connections"""


@router.get("/connections", response_model=list[Connection], responses=E)
async def list_connections(ctx: Ctx = Depends(owner_ctx)) -> list[Connection]:
    """The registry without secrets (keys are never readable)."""
    async with ctx.tx() as tx:
        rows = await tx.all(CONN_SQL + " ORDER BY kind = 'claude_subscription' DESC, key")
    return [Connection(**r) for r in rows]


class ModelPrice(Model):
    input_per_mtok: Decimal = Field(ge=0)
    output_per_mtok: Decimal = Field(ge=0)


class ConnectionLimits(Model):
    rpm: int | None = Field(default=None, ge=1, le=100000)
    tpm: int | None = Field(default=None, ge=1, le=100_000_000)
    daily_usd: Decimal | None = Field(default=None, ge=0)


class ConnectionIn(Model):
    """⟨1.5⟩ a new connection (contract §21.7, §21.14)."""

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    provider: Literal["anthropic", "openai", "google", "deepseek", "mistral", "openai_compatible"]
    kind: Literal["subscription", "api_key"]
    display_name: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    models: list[str] = Field(min_length=1, max_length=50)
    default_model: str | None = Field(default=None, max_length=100)
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)
    limits: ConnectionLimits = Field(default_factory=ConnectionLimits)
    fallback_priority: int | None = Field(default=None, ge=1, le=100)

    @field_validator("models")
    @classmethod
    def _models(cls, v: list[str]) -> list[str]:
        out = []
        for m in v:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}", m):
                raise ValueError(f"{m[:40]!r} is not a model id")
            out.append(m)
        if len(set(out)) != len(out):
            raise ValueError("each model once")
        return out

    @model_validator(mode="after")
    def _shape(self) -> ConnectionIn:
        if self.default_model is not None and self.default_model not in self.models:
            raise ValueError("default_model must be one of models")
        if any(m not in self.models for m in self.pricing):
            raise ValueError("pricing names a model not in models")
        if self.base_url is not None:
            if self.provider != "openai_compatible":
                raise ValueError("base_url is for an openai_compatible provider only")
            reason = public_https(self.base_url)
            if reason:
                raise ValueError(f"base_url: {reason}")
        elif self.provider == "openai_compatible":
            raise ValueError("an openai_compatible provider needs base_url")
        return self


def public_https(url: str) -> str | None:
    """Why a base URL may not be one (the egress guard's rule: https, a
    public host name or address, port 443 or its own), or None. The router
    resolves the name again before it calls (llm_router.verify)."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "not a valid URL"
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host:
        return "https only"
    if parts.username or parts.password:
        return "no credentials in the URL (the key goes to OpenBao)"
    if port is not None and not 1 <= port <= 65535:
        return "not a valid port"
    if host == "localhost" or host.endswith((".internal", ".local", ".localhost")):
        return "not a public host"
    if host in INTERNAL_HOSTS or any(host.endswith("." + h) for h in INTERNAL_HOSTS):
        return "not a host of the hub"
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None if "." in host else "a public host name"
    if not ip.is_global or ip.is_multicast:
        return "a private, loopback, link-local or reserved address"
    return None


INTERNAL_HOSTS = ("hq.coinepro.com",)


@router.post(
    "/connections",
    response_model=Connection,
    status_code=201,
    responses=responses(401, 403, 409, 422, 428),
)
async def create_connection(
    body: ConnectionIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.5⟩ 🔏 step-up `connection.create` (target = the SHA-256 of the exact
    body); `Idempotency-Key` required. -> `pending_secret`: its key goes
    through the write-only POST /connections/{id}/secret or the owner's
    `make connection-secret KEY=<key>`; the router then verifies it at no
    token cost (`verifying` -> `ready` or `error`). Used only through
    PUT /assignments. A duplicate key is 409 version_conflict. A new
    subscription runs through its own CLI and is not made here (409
    not_ready): the substitute accounts are seeded."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        sid = await stepup.consume(
            tx, request, ctx.who, "connection.create", await stepup.body_target(request)
        )
        if body.kind == "subscription":
            raise ApiError(
                409,
                "not_ready",
                "a subscription runs through its own CLI; the substitute subscriptions are seeded",
            )
        if await tx.scalar("SELECT 1 FROM llm.connections WHERE key = :k", k=body.key):
            raise ApiError(409, "version_conflict", f"the connection {body.key} exists already")
        pricing = {
            m: {
                "input_per_mtok": str(p.input_per_mtok),
                "output_per_mtok": str(p.output_per_mtok),
                # the router's price table (USD per 1M tokens), from the owner's figures
                "input": str(p.input_per_mtok),
                "output": str(p.output_per_mtok),
                "source_url": "https://owner.local/entered-by-the-owner",
                "as_of": datetime.now(UTC).date().isoformat(),
            }
            for m, p in body.pricing.items()
        }
        limits = body.limits.model_dump(mode="json", exclude_none=True)
        row = await tx.one(
            """INSERT INTO llm.connections (key, kind, provider, display_name, status, status_reason,
                   secret_ref, api_base, models, default_model, pricing, limits, fallback_priority)
               VALUES (:k, 'api', :p, :n, 'pending_secret', 'waiting for its key', :ref, :base,
                       CAST(:models AS jsonb), :dm, CAST(:pricing AS jsonb), CAST(:limits AS jsonb), :fp)
               RETURNING id""",
            k=body.key,
            p=body.provider,
            n=body.display_name,
            ref=f"kv/llm-connections/{body.key}",
            base=body.base_url,
            models=json.dumps(body.models),
            dm=body.default_model or body.models[0],
            pricing=json.dumps(pricing),
            limits=json.dumps(limits),
            fp=body.fallback_priority,
        )
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.create",
            action_class="A2",
            target_kind="connection",
            target_ref=body.key,
            summary=f"{body.provider} ({len(body.models)} models), waiting for its key",
            step_up=sid is not None,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="connection.create",
            target_kind="connection",
            target_ref=body.key,
            data={"provider": body.provider, "models": body.models},
        )
        out = Connection(**await tx.one(CONN_SQL + " WHERE id = :id", id=row["id"]))
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.patch(
    "/connections/{id}",
    response_model=Connection,
    responses=responses(401, 403, 404, 409, 422, 428),
)
async def update_connection(
    id: UUID, body: ConnectionPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Connection:
    """🔏 step-up `connection.update` (target = the id). Status, name and the
    price table (every price with `source_url` and `as_of`). Requires
    `If-Match: <version>` like every PATCH."""
    expected = if_match(request)
    fields = body.model_dump(exclude_unset=True, mode="json")
    async with ctx.tx() as tx:
        cur = await tx.one(CONN_SQL + " WHERE id = :id FOR UPDATE", id=id)
        check_version(cur["version"], expected)
        await stepup.consume(tx, request, ctx.who, "connection.update", str(id))
        # ⟨1.5⟩ a new connection is switched on by its verification, never by
        # hand; a substitute player's account is never the router's (§21.13).
        if fields.get("status") == "enabled" and (
            cur["status"] in ("pending_secret", "verifying", "error")
            or cur["kind"] == "subscription"
        ):
            raise ApiError(
                409, "not_ready", f"{cur['key']} is {cur['status']}: it cannot be enabled"
            )
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
        cur = await tx.one(
            "SELECT key, secret_ref, status FROM llm.connections WHERE id = :id FOR UPDATE", id=id
        )
        await stepup.consume(tx, request, ctx.who, "connection.secret", str(id))
        if not cur["secret_ref"] or not str(cur["secret_ref"]).startswith("kv/llm-connections/"):
            raise ApiError(422, "validation_failed", "this connection takes no key")
        new = cur["status"] in ("pending_secret", "verifying", "error")
        # ⟨1.5⟩ the owner's decision (§0.8 #8): "terminal only" keeps a new
        # connection's key off this route (`make connection-secret KEY=...`).
        if new and ctx.hub.settings.connection_secret_route == "terminal":  # noqa: S105
            raise ApiError(
                409,
                "validation_failed",
                f"a new connection's key goes in by terminal: make connection-secret KEY={cur['key']}",
            )
        if bao is None:
            raise ApiError(503, "channel_not_configured", "the secret store is not available")
        await bao.write_kv(str(cur["secret_ref"]).removeprefix("kv/"), {"api_key": body.secret})
        if new:  # the router verifies it at no token cost (llm_router.verify)
            await tx.exec(
                """UPDATE llm.connections SET status = 'verifying', status_reason = 'verifying its key',
                       status_changed_at = now(), updated_at = now() WHERE id = :id""",
                id=id,
            )
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
    """🔏 step-up `assignments.update`, bound to the request body: the target is the
    SHA-256 (hex) of the exact body bytes. Upserts the listed levels."""
    async with ctx.tx() as tx:
        await stepup.consume(
            tx, request, ctx.who, "assignments.update", await stepup.body_target(request)
        )
        for a in body.assignments:
            if a.connection is None and a.model is None and a.effort is None:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={"assignments": "set connection, model or effort"},
                )
            conn_id = None
            if a.connection:
                conn = await tx.first(
                    "SELECT id, kind FROM llm.connections WHERE key = :k", k=a.connection
                )
                if conn is None:
                    raise ApiError(
                        422, "validation_failed", fields={"connection": f"unknown {a.connection}"}
                    )
                # ⟨1.5⟩ a substitute player's subscription is called by seat only
                # (contract §21.13): no Claude run is ever assigned to it.
                if conn["kind"] == "subscription":
                    raise ApiError(
                        422,
                        "validation_failed",
                        fields={
                            "connection": f"{a.connection} is a substitute player's (seats only)"
                        },
                    )
                conn_id = conn["id"]
            # Only through the scope-checked function (the api role cannot write the table).
            await tx.exec(
                "SELECT llm.put_assignment(:st, :sr, :cn, :m, :e, :note)",
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
    """🔏 step-up `budgets.update`, bound to the request body: the target is the
    SHA-256 (hex) of the exact body bytes. Upserts per scope and period."""
    async with ctx.tx() as tx:
        await stepup.consume(
            tx, request, ctx.who, "budgets.update", await stepup.body_target(request)
        )
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
