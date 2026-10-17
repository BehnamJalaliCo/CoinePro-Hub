"""Agents at work, the owner's side (contract §16): role charters, runs and
their steps (the "agent screen"), rule-based site checks and incidents, the
subscription quota, and the live stream of a reply being written.

Steps carry summaries and tool metadata only - never a prompt, raw model
output or a tool payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hq_api import pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import sites as site_seed
from hq_api.errors import ApiError, responses
from hq_api.routes.agent_tools import SITES_SQL
from hq_api.schemas import CODE, Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["agents"])
E = responses(401, 403, 404, 409, 422)
HEARTBEAT_S = 15.0


# ------------------------------------------------------------------- roles --
class RoleLimits(BaseModel):
    steps_per_run: int
    tokens_per_step: int
    tokens_per_run: int


class Role(BaseModel):
    role: str
    title_fa: str
    title_en: str
    kind: str
    scope: str
    department: str | None
    model: str
    effort: str
    priority: str
    tools: list[str]
    limits: RoleLimits
    version: int


@router.get("/roles", response_model=list[Role], responses=E)
async def list_roles(ctx: Ctx = Depends(owner_ctx)) -> list[Role]:
    """The role charters (agents/roles/*.md), read-only: what each role is, its
    default model and effort, its tools and limits, and the charter version."""
    lib = ctx.hub.charters
    if lib is None:
        return []
    return [
        Role(
            role=c.role,
            title_fa=c.title_fa,
            title_en=c.title_en,
            kind=c.kind,
            scope=c.scope,
            department=c.department,
            model=c.model,
            effort=c.effort,
            priority=c.priority,
            tools=list(c.tools),
            limits=RoleLimits(**c.limits.__dict__),
            version=c.version,
        )
        for c in sorted(lib.roles.values(), key=lambda c: c.role)
    ]


# -------------------------------------------------------------------- runs --
class RunTokens(BaseModel):
    input: int
    output: int
    cache_read: int
    cache_write: int


class StepAction(BaseModel):
    tool: str
    cls: str | None = Field(default=None, serialization_alias="class")
    outcome: str
    ref: str | None = None


class Step(BaseModel):
    run_id: UUID
    n: int
    at: datetime
    summary_fa: str
    actions: list[StepAction]


class Run(BaseModel):
    id: UUID
    employee: str
    company: str
    work_ref: str | None
    thread: str | None
    trigger: str
    reason: str
    state: str
    priority: str
    model: str | None
    effort: str | None
    started_at: datetime | None
    finished_at: datetime | None
    queued_at: datetime
    steps: int
    tool_calls: int
    tokens: RunTokens
    equiv_cost_usd: Decimal
    cost_usd: Decimal
    charter_version: int | None
    charter: str | None
    partial: bool
    error_code: str | None


class RunDetail(Run):
    # `steps` is the count (contract §16.2); the steps themselves are here.
    steps_detail: list[Step]


RUN_SQL = """
    SELECT r.*, e.code AS employee, c.code AS company, w.ref AS work_ref, t.code AS thread
    FROM agents.runs r
    JOIN core.employees e ON e.id = r.employee_id
    JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN work.work w ON w.id = r.work_id
    LEFT JOIN msg.threads t ON t.id = r.thread_id
"""


def render_run(r: dict[str, Any]) -> Run:
    return Run(
        id=r["id"],
        employee=r["employee"],
        company=r["company"],
        work_ref=r["work_ref"],
        thread=r["thread"],
        trigger=r["trigger"],
        reason=r["reason"],
        state=r["state"],
        priority=r["priority"],
        model=r["model"],
        effort=r["effort"],
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        queued_at=r["queued_at"],
        steps=r["steps"],
        tool_calls=r["tool_calls"],
        tokens=RunTokens(
            input=r["input_tokens"],
            output=r["output_tokens"],
            cache_read=r["cache_read_tokens"],
            cache_write=r["cache_write_tokens"],
        ),
        equiv_cost_usd=r["equiv_cost_usd"],
        cost_usd=r["cost_usd"],
        charter_version=r["charter_version"],
        charter=r["charter_role"],
        partial=r["partial"],
        error_code=r["error_code"],
    )


def render_step(s: dict[str, Any]) -> Step:
    return Step(
        run_id=s["run_id"],
        n=s["n"],
        at=s["at"],
        summary_fa=s["summary_fa"],
        actions=[
            StepAction(
                tool=str(a.get("tool", "")),
                cls=a.get("class"),
                outcome=str(a.get("outcome", "")),
                ref=a.get("ref"),
            )
            for a in s["actions"] or []
            if isinstance(a, dict)
        ],
    )


@router.get("/runs", response_model=Page[Run], responses=E)
async def list_runs(
    company: list[str] | None = Query(default=None),
    employee: str | None = Query(default=None, max_length=40),
    state: Literal["queued", "running", "done", "failed", "refused"] | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Run]:
    """Agent runs, newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            RUN_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:emp AS text) IS NULL OR e.code = :emp)
                    AND (CAST(:state AS text) IS NULL OR r.state = :state)
                    AND (CAST(:from_ AS timestamptz) IS NULL OR r.queued_at >= :from_)
                    AND (CAST(:to_ AS timestamptz) IS NULL OR r.queued_at < :to_)
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (r.queued_at, r.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY r.queued_at DESC, r.id DESC LIMIT :lim""",
            companies=company,
            emp=employee,
            state=state,
            from_=from_,
            to_=to,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("queued_at", "id"))
    return Page(items=[render_run(r) for r in items], next_cursor=nxt)


@router.get("/runs/{id}", response_model=RunDetail, responses=E)
async def get_run(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> RunDetail:
    """One run with its steps: summaries and tool metadata only."""
    async with ctx.tx() as tx:
        r = await tx.one(RUN_SQL + " WHERE r.id = :id", id=id)
        steps = await tx.all("SELECT * FROM agents.steps WHERE run_id = :id ORDER BY n", id=id)
    return RunDetail(**render_run(r).model_dump(), steps_detail=[render_step(s) for s in steps])


@router.get("/work/{id}/runs", response_model=list[RunDetail], responses=E)
async def work_runs(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> list[RunDetail]:
    """The runs of one work item, oldest first, with their steps."""
    async with ctx.tx() as tx:
        await tx.one("SELECT 1 FROM work.work WHERE id = :id", id=id)
        rows = await tx.all(RUN_SQL + " WHERE r.work_id = :id ORDER BY r.queued_at", id=id)
        steps = await tx.all(
            "SELECT * FROM agents.steps WHERE run_id = ANY(:ids) ORDER BY run_id, n",
            ids=[r["id"] for r in rows],
        )
    by_run: dict[UUID, list[Step]] = {}
    for s in steps:
        by_run.setdefault(s["run_id"], []).append(render_step(s))
    return [
        RunDetail(**render_run(r).model_dump(), steps_detail=by_run.get(r["id"], [])) for r in rows
    ]


# --------------------------------------------------------------- site checks --
class Site(BaseModel):
    id: UUID
    company: str
    url: str
    kind: str
    method: str
    expect: dict[str, Any]
    interval_s: int
    enabled: bool
    canary: bool
    consecutive_failures: int
    last: dict[str, Any] | None
    uptime_24h: float | None
    version: int


class SiteIn(Model):
    url: str = Field(pattern=r"^https?://[^\s/$.?#][^\s]*$", max_length=500)
    kind: Literal["web", "api", "bot"] = "web"
    method: Literal["GET", "HEAD"] = "GET"
    expect: dict[str, Any] = Field(default_factory=lambda: dict(site_seed.DEFAULT_EXPECT))
    interval_s: int = Field(default=300, ge=60, le=86400)
    enabled: bool = True


class SitesPut(Model):
    company: str = Field(pattern=CODE)
    sites: list[SiteIn] = Field(max_length=50)


class Incident(BaseModel):
    id: UUID
    ref: str
    company: str
    url: str
    opened_at: datetime
    closed_at: datetime | None
    severity: str
    checks_failed: int
    last_status: int | None
    last_error: str | None
    work_ref: str | None


def _expect_ok(expect: dict[str, Any]) -> dict[str, Any]:
    status = expect.get("status", 200)
    contains = expect.get("contains")
    if not isinstance(status, int) or not 100 <= status <= 599:
        raise ApiError(422, "validation_failed", fields={"expect.status": "an HTTP status"})
    if contains is not None and (not isinstance(contains, str) or not 1 <= len(contains) <= 200):
        raise ApiError(422, "validation_failed", fields={"expect.contains": "1..200 characters"})
    return {"status": status, **({"contains": contains} if contains else {})}


async def _sites(tx: Any, company_id: UUID | None) -> list[Site]:
    rows = await tx.all(
        SITES_SQL.replace(
            "SELECT s.id,", "SELECT s.id, s.method, s.expect, s.interval_s, s.canary, s.version,"
        )
        + " WHERE (CAST(:co AS uuid) IS NULL OR s.company_id = :co) ORDER BY c.code, s.url",
        co=company_id,
        since=datetime.now(UTC) - timedelta(hours=24),
    )
    return [
        Site(
            id=r["id"],
            company=r["company"],
            url=r["url"],
            kind=r["kind"],
            method=r["method"],
            expect=dict(r["expect"]),
            interval_s=r["interval_s"],
            enabled=r["enabled"],
            canary=r["canary"],
            consecutive_failures=r["consecutive_failures"],
            last=r["last"],
            uptime_24h=float(r["uptime"]) if r["uptime"] is not None else None,
            version=r["version"],
        )
        for r in rows
    ]


@router.get("/ops/sites", response_model=list[Site], responses=E)
async def list_sites(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[Site]:
    """Sites under rule-based checks with their latest check and 24 h uptime."""
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        return await _sites(tx, co.id if co else None)


@router.put("/ops/sites", response_model=list[Site], responses=E)
async def put_sites(request: Request, body: SitesPut, ctx: Ctx = Depends(owner_ctx)) -> list[Site]:
    """🔏 (`sites.update`, target = SHA-256 of the body) replace one company's
    list: new URLs are added, listed ones updated, missing ones switched off
    (never deleted: their checks and incidents stay). Canaries are not touched."""
    co = await ctx.hub.companies.by_code(body.company)
    urls = [s.url for s in body.sites]
    if len(set(urls)) != len(urls):
        raise ApiError(422, "validation_failed", fields={"sites": "a URL appears twice"})
    target = hashlib.sha256(await request.body()).hexdigest()
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "sites.update", target)
        for s in body.sites:
            expect = json.dumps(_expect_ok(s.expect))
            changed = await tx.exec(
                """UPDATE ops.sites SET kind = :kind, method = :method, expect = CAST(:expect AS jsonb),
                       interval_s = :iv, enabled = :en
                   WHERE company_id = :co AND url = :url AND NOT canary""",
                co=co.id,
                url=s.url,
                kind=s.kind,
                method=s.method,
                expect=expect,
                iv=s.interval_s,
                en=s.enabled,
            )
            if not changed:
                await tx.exec(
                    """INSERT INTO ops.sites (company_id, url, kind, method, expect, interval_s, enabled)
                       VALUES (:co, :url, :kind, :method, CAST(:expect AS jsonb), :iv, :en)
                       ON CONFLICT (company_id, url) DO NOTHING""",
                    co=co.id,
                    url=s.url,
                    kind=s.kind,
                    method=s.method,
                    expect=expect,
                    iv=s.interval_s,
                    en=s.enabled,
                )
        off = await tx.exec(
            """UPDATE ops.sites SET enabled = false
               WHERE company_id = :co AND NOT canary AND enabled AND NOT (url = ANY(:urls))""",
            co=co.id,
            urls=urls,
        )
        await ctx.audit(
            tx,
            company_id=co.id,
            action="sites.update",
            action_class="A2",
            target_kind="company",
            target_ref=co.code,
            summary=f"{len(urls)} listed, {off} switched off",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="setting",
            action="sites.update",
            target_kind="company",
            target_ref=co.code,
            data={"urls": urls},
        )
        return await _sites(tx, co.id)


@router.get("/ops/incidents", response_model=list[Incident], responses=E)
async def list_incidents(
    company: str | None = Query(default=None, pattern=CODE),
    open: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: Ctx = Depends(owner_ctx),
) -> list[Incident]:
    """Incidents opened by the rule-based checks, newest first."""
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT i.*, c.code AS company, s.url, w.ref AS work_ref
               FROM ops.incidents i JOIN core.companies c ON c.id = i.company_id
               JOIN ops.sites s ON s.id = i.site_id LEFT JOIN work.work w ON w.id = i.work_id
               WHERE (CAST(:co AS uuid) IS NULL OR i.company_id = :co)
                 AND (CAST(:open AS boolean) IS NULL OR (i.closed_at IS NULL) = :open)
               ORDER BY i.opened_at DESC LIMIT :lim""",
            co=co.id if co else None,
            open=open,
            lim=limit,
        )
    return [Incident(**{k: r[k] for k in Incident.model_fields}) for r in rows]


# ------------------------------------------------------------------- quota --
class Subscription(BaseModel):
    connection: str | None
    status: Literal["ok", "warning", "limited"]
    window: str | None
    utilization: Decimal | None
    resets_at: datetime | None
    source: str | None
    changed_at: datetime | None


class Throttle(BaseModel):
    paused_priorities: list[str]


class Quota(BaseModel):
    subscription: Subscription
    throttle: Throttle


PAUSED = {"ok": [], "warning": ["P4"], "limited": ["P3", "P4"]}


@router.get("/treasury/quota", response_model=Quota, responses=E)
async def treasury_quota(ctx: Ctx = Depends(owner_ctx)) -> Quota:
    """The subscription's quota as the Quota Controller sees it (code, no model):
    at `warning` P4 waits, at `limited` only P0-P2 run."""
    async with ctx.tx() as tx:
        row = await tx.first(
            """SELECT cn.key, q.status, q.window_kind, q.utilization, q.resets_at, q.source, q.changed_at
               FROM llm.connections cn LEFT JOIN llm.quota_status q ON q.connection_id = cn.id
               WHERE cn.kind = 'claude_subscription' AND cn.status <> 'disabled'
               ORDER BY CASE q.status WHEN 'limited' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, cn.key
               LIMIT 1"""
        )
        now = await tx.scalar("SELECT now()")
    status = (row or {}).get("status") or "ok"
    if row and status != "ok" and row["resets_at"] is not None and row["resets_at"] <= now:
        status = "ok"  # its reset has passed (the controller catches up within a minute)
    return Quota(
        subscription=Subscription(
            connection=row["key"] if row else None,
            status=status,
            window=row["window_kind"] if row and status != "ok" else None,
            utilization=row["utilization"] if row else None,
            resets_at=row["resets_at"] if row and status != "ok" else None,
            source=row["source"] if row else None,
            changed_at=row["changed_at"] if row else None,
        ),
        throttle=Throttle(paused_priorities=PAUSED[status]),
    )


# -------------------------------------------------------------------- live --
@router.get("/threads/{code}/live", responses=E)
async def thread_live(code: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Owner only, SSE: `reply.started {run_id}`, `reply.delta {text}` (the reply
    being written, in Persian chunks), `reply.done {message_ref}`,
    `reply.failed {code}`. The stored message is the final text; deltas are
    never stored. A comment line every 15 s keeps the connection open."""
    async with ctx.tx() as tx:
        await tx.one("SELECT 1 FROM msg.threads WHERE code = :c", c=code)
    live = ctx.hub.live
    if live is None:
        raise ApiError(503, "internal_error", "live replies are off")
    q = live.subscribe(code)

    async def events() -> AsyncIterator[str]:
        try:
            yield ": live\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    type_, data = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"event: {type_}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            live.unsubscribe(code, q)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
