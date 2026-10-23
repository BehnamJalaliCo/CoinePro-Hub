"""Internal API behind the Tool Gateway's tools (prompt 05 §3, agents/tools.md).

Every endpoint here is for an agent of a RUNNING run (agent token + run
registry) and passes OPA (`hq.internal`) and the action gate (`hq.actions`).
Reads run in a READ ONLY transaction: an agent reads its own company; a
holding-scope role (charter scope "holding": oversight, AI operations, the
advisor) may read every company, never write in another. Answers are compact
and carry references, not bodies of other threads; the gateway redacts them
again before the model sees them.

Also here: the run's own gate (reserve a tool call: caps per step and per run
in agents.runs), the audit row of every tool call, the employee's memory and
the live push of a reply being written (advisor, contract §16.3).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from hq_api import audit, idempotency
from hq_api.context import Ctx, internal_ctx
from hq_api.db import Tx
from hq_api.domain import backups, hiring, oversight
from hq_api.domain import files as F
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.routes.backups import BackupStatus
from hq_api.routes.internal import allow, escrow_of
from hq_api.routes.treasury import TOTALS, period_start
from hq_api.schemas import CODE, FileRef, Model
from hq_common.redact import scrub_async

router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 429)
SNIPPET = 240
LIVE_TYPES = ("reply.started", "reply.delta", "reply.done", "reply.failed")
LIVE_MAX_BYTES = 2 * 1024 * 1024
TOOL_CLASSES = ("A0", "A1", "A2")


def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


@asynccontextmanager
async def read_tx(ctx: Ctx) -> AsyncIterator[Tx]:
    """A READ ONLY transaction over the companies the agent may read."""
    scope = await ctx.hub.companies.ids() if ctx.who.scope == "holding" else await ctx.scope()
    async with ctx.hub.db.tx(scope) as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        yield tx


# A tool-call cap (per step or per run) answers 429 with this Retry-After: the
# next step may call again; a run at its own cap ends before then.
CAP_RETRY_AFTER_S = 30


async def _company(ctx: Ctx, op: str, code: str | None, **target: Any) -> Any:
    """The company a read targets (given, for holding scope, or the agent's
    own), looked up only AFTER the policy allowed the read: a missing and a
    forbidden code answer the same 403 (prompt 5.1 §3)."""
    assert ctx.who.company is not None
    wanted = code or ctx.who.company
    await allow(ctx, op, {"company": wanted, **target})
    return await ctx.hub.companies.by_code(wanted)


# ------------------------------------------------------------------ work.get --
class ChainItem(BaseModel):
    ref: str
    depth: int
    title: str
    assignee: str | None
    status: str


class DeliverableBrief(BaseModel):
    ref: str
    title: str
    summary: str
    producer: str
    created_at: datetime


class BudgetLeft(BaseModel):
    tokens: int | None
    usd: Decimal | None
    tokens_used: int
    usd_used: Decimal
    tokens_left: int | None
    usd_left: Decimal | None


class AgentWorkDetail(BaseModel):
    id: UUID
    ref: str
    company: str
    department: str | None
    kind: str
    title: str
    brief: str
    priority: str
    status: str
    assignee: str | None
    created_by: str
    depth: int
    due_at: datetime | None
    budget: BudgetLeft
    escrow_classes: list[str]
    evidence: list[dict[str, Any]]
    progress_note: str | None
    chain: list[ChainItem]
    children: list[ChainItem]
    deliverables: list[DeliverableBrief]


@router.get("/work/ref/{ref}", response_model=AgentWorkDetail, responses=E)
async def tool_work_get(ref: str, ctx: Ctx = Depends(internal_ctx)) -> AgentWorkDetail:
    """work.get: one work item with its delegation chain, brief, budget left,
    evidence and deliverables (summaries)."""
    _agent(ctx)
    async with read_tx(ctx) as tx:
        # Under the agent's scope: work of a company it may not read is not found.
        w = await W.load_ref(tx, ref)
        await allow(ctx, "work.read", {"company": w["company"]})
        chain = await tx.all(
            """WITH RECURSIVE up AS (
                   SELECT id, parent_id, ref, depth, title, status, assignee_id FROM work.work WHERE id = :id
                   UNION ALL
                   SELECT p.id, p.parent_id, p.ref, p.depth, p.title, p.status, p.assignee_id
                   FROM work.work p JOIN up ON up.parent_id = p.id)
               SELECT up.ref, up.depth, up.title, up.status, e.code AS assignee
               FROM up LEFT JOIN core.employees e ON e.id = up.assignee_id ORDER BY up.depth""",
            id=w["id"],
        )
        children = await tx.all(
            """SELECT w.ref, w.depth, w.title, w.status, e.code AS assignee, w.budget_tokens
               FROM work.work w LEFT JOIN core.employees e ON e.id = w.assignee_id
               WHERE w.parent_id = :id ORDER BY w.created_at LIMIT 50""",
            id=w["id"],
        )
        dls = await tx.all(
            """SELECT d.ref, d.title, left(d.summary, 500) AS summary, e.code AS producer, d.created_at
               FROM cartable.deliverables d JOIN core.employees e ON e.id = d.producer_id
               WHERE d.work_id = :id ORDER BY d.created_at LIMIT 20""",
            id=w["id"],
        )
        escrow = await escrow_of(tx, w)
    given = sum(int(c["budget_tokens"] or 0) for c in children)
    tokens_left = (
        max(int(w["budget_tokens"]) - int(w["tokens_used"]) - given, 0)
        if w["budget_tokens"] is not None
        else None
    )
    usd_left = (
        max(Decimal(w["budget_usd"]) - Decimal(w["usd_used"]), Decimal(0))
        if w["budget_usd"] is not None
        else None
    )
    return AgentWorkDetail(
        id=w["id"],
        ref=w["ref"],
        company=w["company"],
        department=w["department"],
        kind=w["kind"],
        title=w["title"],
        brief=w["brief"],
        priority=w["priority"],
        status=w["status"],
        assignee=w["a_code"],
        created_by=f"{w['created_by_kind']}:{w['created_by_code']}",
        depth=w["depth"],
        due_at=w["due_at"],
        budget=BudgetLeft(
            tokens=w["budget_tokens"],
            usd=w["budget_usd"],
            tokens_used=w["tokens_used"],
            usd_used=w["usd_used"],
            tokens_left=tokens_left,
            usd_left=usd_left,
        ),
        escrow_classes=escrow,
        evidence=list(w["evidence"] or []),
        progress_note=w["progress_note"],
        chain=[ChainItem(**c) for c in chain],
        children=[ChainItem(**{k: c[k] for k in ChainItem.model_fields}) for c in children],
        deliverables=[DeliverableBrief(**d) for d in dls],
    )


# ------------------------------------------------------------- company.state --
class CompanyState(BaseModel):
    company: str
    kind: str
    name_en: str | None
    kill_switch: str
    deploy_freeze_until: datetime | None
    departments: list[dict[str, Any]]
    employees: dict[str, int]
    work_open: dict[str, int]
    decisions_pending: int
    budgets: list[dict[str, Any]]
    # ⟨1.4.2⟩ hiring starts with the owner (§18.11): while closed, record a team gap
    # in an output instead of proposing a hire
    hiring: Literal["closed", "open"] = "closed"


class HoldingState(BaseModel):
    companies: list[CompanyState]
    hiring: Literal["closed", "open"] = "closed"


async def _company_state(tx: Tx, co: Any) -> CompanyState:
    depts = await tx.all(
        """SELECT d.code, d.name_en, m.code AS manager, m.activity AS manager_activity
           FROM core.departments d
           LEFT JOIN core.employees m ON m.department_id = d.id AND m.kind IN ('manager', 'inspector')
                AND m.status <> 'dismissed'
           WHERE d.company_id = :co AND d.status = 'active' ORDER BY d.sort, d.code""",
        co=co.id,
    )
    emps = await tx.all(
        """SELECT kind, count(*) AS n FROM core.employees
           WHERE company_id = :co AND status = 'active' GROUP BY kind""",
        co=co.id,
    )
    work = await tx.all(
        """SELECT status, count(*) AS n FROM work.work
           WHERE company_id = :co AND status IN ('queued', 'in_progress', 'waiting', 'delivered')
             AND kind <> 'recurring' GROUP BY status""",
        co=co.id,
    )
    pending = await tx.scalar(
        "SELECT count(*) FROM cartable.decisions WHERE company_id = :co AND status = 'pending'",
        co=co.id,
    )
    ks = await tx.scalar("SELECT state FROM control.kill_switches WHERE company_id = :co", co=co.id)
    freeze = await tx.scalar(
        """SELECT max(until) FROM control.deploy_freezes
           WHERE company_id = :co AND lifted_at IS NULL AND until > now()""",
        co=co.id,
    )
    budgets = await _budget_use(tx, co.id, "month")
    return CompanyState(
        company=co.code,
        kind=co.kind,
        name_en=co.name_en,
        kill_switch=ks or "released",
        deploy_freeze_until=freeze,
        departments=depts,
        employees={r["kind"]: int(r["n"]) for r in emps},
        work_open={r["status"]: int(r["n"]) for r in work},
        decisions_pending=int(pending or 0),
        budgets=budgets,
        hiring=await hiring.state(tx),
    )


async def _budget_use(tx: Tx, company_id: Any, period: str) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT b.scope_type, b.scope_ref, b.period, b.token_limit, b.usd_limit,
                  COALESCE(u.tokens, 0) AS tokens_used, COALESCE(u.usd, 0) AS usd_used
           FROM llm.budgets b
           LEFT JOIN llm.usage u ON u.scope_type = b.scope_type AND u.scope_ref = b.scope_ref
                AND u.period = b.period AND u.period_start = :ps
           WHERE b.enabled AND b.company_id = :co AND b.period = :p""",
        co=company_id,
        p=period,
        ps=period_start(period).date(),
    )
    out = []
    for b in rows:
        pcts = []
        if b["token_limit"]:
            pcts.append(100.0 * b["tokens_used"] / b["token_limit"])
        if b["usd_limit"]:
            pcts.append(100.0 * float(b["usd_used"]) / float(b["usd_limit"]))
        out.append(
            {
                "scope": f"{b['scope_type']}:{b['scope_ref']}",
                "period": b["period"],
                "used_pct": round(max(pcts), 1) if pcts else None,
            }
        )
    return out


@router.get("/company/state", response_model=CompanyState | HoldingState, responses=E)
async def tool_company_state(
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(internal_ctx),
) -> CompanyState | HoldingState:
    """company.state: departments, active employees, open work by status, pending
    decisions, kill switch, deploy freeze, budget use. A holding-scope role
    without `company` gets every company."""
    _agent(ctx)
    if company is None and ctx.who.scope == "holding":
        await allow(ctx, "company.read", {"company": ctx.who.company})
        async with read_tx(ctx) as tx:
            return HoldingState(
                companies=[await _company_state(tx, c) for c in await ctx.hub.companies.all()],
                hiring=await hiring.state(tx),
            )
    co = await _company(ctx, "company.read", company)
    async with read_tx(ctx) as tx:
        return await _company_state(tx, co)


# -------------------------------------------------------------- health.sites --
class SiteHealth(BaseModel):
    company: str
    url: str
    kind: str
    enabled: bool
    consecutive_failures: int
    last: dict[str, Any] | None
    uptime_24h: float | None


class IncidentBrief(BaseModel):
    ref: str
    company: str
    url: str
    opened_at: datetime
    severity: str
    checks_failed: int
    last_status: int | None
    last_error: str | None
    work_ref: str | None


class SitesHealth(BaseModel):
    sites: list[SiteHealth]
    open_incidents: list[IncidentBrief]
    since: datetime


SITES_SQL = """
    SELECT s.id, c.code AS company, s.url, s.kind, s.enabled, s.consecutive_failures,
           (SELECT jsonb_build_object('at', k.at, 'ok', k.ok, 'status', k.status,
                   'latency_ms', k.latency_ms, 'tls_days_left', k.tls_days_left, 'error_code', k.error_code)
              FROM ops.checks k WHERE k.site_id = s.id ORDER BY k.at DESC LIMIT 1) AS last,
           (SELECT round(100.0 * count(*) FILTER (WHERE k.ok) / nullif(count(*), 0), 1)
              FROM ops.checks k WHERE k.site_id = s.id AND k.at >= :since) AS uptime
    FROM ops.sites s JOIN core.companies c ON c.id = s.company_id
"""


@router.get("/health/sites", response_model=SitesHealth, responses=E)
async def tool_health_sites(
    company: str | None = Query(default=None, pattern=CODE),
    since: datetime | None = None,
    ctx: Ctx = Depends(internal_ctx),
) -> SitesHealth:
    """health.sites: the latest rule-based check of each site (status, latency,
    TLS days left, consecutive failures), 24 h uptime, and open incidents."""
    _agent(ctx)
    every = company is None and ctx.who.scope == "holding"
    if every:
        await allow(ctx, "health.read", {"company": ctx.who.company})
    co = None if every else await _company(ctx, "health.read", company)
    start = since or datetime.now(UTC) - timedelta(hours=24)
    async with read_tx(ctx) as tx:
        sites = await tx.all(
            SITES_SQL
            + " WHERE (CAST(:co AS uuid) IS NULL OR s.company_id = :co) ORDER BY c.code, s.url",
            co=co.id if co else None,
            since=start,
        )
        incidents = await tx.all(
            """SELECT i.ref, c.code AS company, s.url, i.opened_at, i.severity, i.checks_failed,
                      i.last_status, i.last_error, w.ref AS work_ref
               FROM ops.incidents i JOIN ops.sites s ON s.id = i.site_id
               JOIN core.companies c ON c.id = i.company_id LEFT JOIN work.work w ON w.id = i.work_id
               WHERE i.closed_at IS NULL AND (CAST(:co AS uuid) IS NULL OR i.company_id = :co)
               ORDER BY i.opened_at""",
            co=co.id if co else None,
        )
    return SitesHealth(
        sites=[
            SiteHealth(
                company=s["company"],
                url=s["url"],
                kind=s["kind"],
                enabled=s["enabled"],
                consecutive_failures=s["consecutive_failures"],
                last=s["last"],
                uptime_24h=float(s["uptime"]) if s["uptime"] is not None else None,
            )
            for s in sites
        ],
        open_incidents=[IncidentBrief(**i) for i in incidents],
        since=start,
    )


# ---------------------------------------------------------------- health.hub --
class HubHealth(BaseModel):
    at: datetime | None
    data: dict[str, Any]


@router.get("/health/hub", response_model=HubHealth, responses=E)
async def tool_health_hub(ctx: Ctx = Depends(internal_ctx)) -> HubHealth:
    """health.hub: the hub's own latest snapshot (services, restarts, disk,
    memory, certificate days left, backup age, restore-test result)."""
    _agent(ctx)
    await allow(ctx, "hub.read", {})
    holding = await ctx.hub.companies.holding()
    async with read_tx(ctx) as tx:
        row = await tx.first(
            "SELECT at, data FROM ops.hub_health WHERE company_id = :co", co=holding.id
        )
    return HubHealth(at=row["at"] if row else None, data=dict(row["data"]) if row else {})


# ------------------------------------------------------------ backups.status --
@router.get("/backups/status", response_model=BackupStatus, responses=E)
async def tool_backups_status(ctx: Ctx = Depends(internal_ctx)) -> BackupStatus:
    """backups.status: the backup status of §18.9 (holding-scope roles: the
    overseer, the platform SRE); metadata only, never a restore."""
    _agent(ctx)
    await allow(ctx, "backup.read", {})
    holding = await ctx.hub.companies.holding()
    async with read_tx(ctx) as tx:
        return BackupStatus(**await backups.status(tx, holding.id))


# ------------------------------------------------------------ treasury.usage --
class Usage(BaseModel):
    scope: str
    period: str
    period_start: datetime
    totals: dict[str, Any]
    by_model: list[dict[str, Any]]
    top_actors: list[dict[str, Any]]
    budgets: list[dict[str, Any]]


@router.get("/treasury/usage", response_model=Usage, responses=E)
async def tool_treasury_usage(
    scope: str = Query(default="company", pattern=r"^(company|holding|[A-Z][A-Z0-9]{1,9})$"),
    period: Literal["day", "month"] = "month",
    ctx: Ctx = Depends(internal_ctx),
) -> Usage:
    """treasury.usage: tokens and equivalent cost of a company (own; another one
    or `holding` for holding-scope roles) by model and top actors, budget use %."""
    _agent(ctx)
    assert ctx.who.company is not None
    target = ctx.who.company if scope == "company" else scope
    every = target == "holding"
    if every and ctx.who.scope != "holding":
        raise ApiError(403, "policy_denied", "treasury.read_not_permitted")
    if every:
        await allow(ctx, "treasury.read", {"company": ctx.who.company})
    co = None if every else await _company(ctx, "treasury.read", target)
    start = period_start(period)
    async with read_tx(ctx) as tx:
        totals = await tx.one(
            f"SELECT {TOTALS} FROM llm.calls c WHERE c.started_at >= :s "  # noqa: S608 - module constant
            "AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)",
            s=start,
            co=co.id if co else None,
        )
        by_model = await tx.all(
            f"SELECT c.model, {TOTALS} FROM llm.calls c WHERE c.started_at >= :s "  # noqa: S608 - module constant
            "AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co) GROUP BY c.model ORDER BY calls DESC",
            s=start,
            co=co.id if co else None,
        )
        top = await tx.all(
            """SELECT c.actor_ref AS actor, count(*) AS calls,
                      COALESCE(sum(COALESCE(c.input_tokens, 0) + COALESCE(c.output_tokens, 0)
                          + COALESCE(c.cache_read_tokens, 0) + COALESCE(c.cache_write_tokens, 0)), 0) AS tokens,
                      COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd
               FROM llm.calls c WHERE c.started_at >= :s AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
               GROUP BY c.actor_ref ORDER BY tokens DESC LIMIT 10""",
            s=start,
            co=co.id if co else None,
        )
        budgets = await _budget_use(tx, co.id, period) if co else []
    return Usage(
        scope=co.code if co else "holding",
        period=period,
        period_start=start,
        totals=_plain(totals),
        by_model=[_plain(r) for r in by_model],
        top_actors=[_plain(r) for r in top],
        budgets=budgets,
    )


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


# ---------------------------------------------------------- knowledge.search --
KINDS = ("resolutions", "deliverables", "decisions", "work", "messages")


class Hit(BaseModel):
    kind: str
    ref: str
    company: str
    title: str
    snippet: str
    at: datetime


@router.get("/knowledge/search", response_model=list[Hit], responses=E)
async def tool_knowledge_search(
    q: str = Query(min_length=2, max_length=200),
    kinds: list[str] | None = Query(default=None),
    company: str | None = Query(default=None, pattern=CODE),
    limit: int = Query(default=20, ge=1, le=50),
    ctx: Ctx = Depends(internal_ctx),
) -> list[Hit]:
    """knowledge.search: resolutions, deliverables, decisions and work the role
    may read (message bodies: the advisor only). Refs and short snippets."""
    _agent(ctx)
    wanted = [
        k for k in (kinds or ["resolutions", "deliverables", "decisions", "work"]) if k in KINDS
    ]
    if not wanted:
        raise ApiError(422, "validation_failed", fields={"kinds": f"some of {', '.join(KINDS)}"})
    every = company is None and ctx.who.scope == "holding"
    if every:
        await allow(ctx, "knowledge.read", {"company": ctx.who.company, "kinds": wanted})
    co = None if every else await _company(ctx, "knowledge.read", company, kinds=wanted)
    queries = {
        "resolutions": """SELECT 'resolution' AS kind, r.ref, c.code AS company, r.title,
                              left(r.body, 400) AS body, r.sealed_at AS at
                          FROM cartable.resolutions r JOIN core.companies c ON c.id = r.company_id
                          WHERE core.fa_normalize(r.title || ' ' || r.body) LIKE :pat""",
        "deliverables": """SELECT 'deliverable' AS kind, d.ref, c.code AS company, d.title,
                               left(d.summary, 400) AS body, d.created_at AS at
                           FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
                           WHERE core.fa_normalize(d.title || ' ' || d.summary) LIKE :pat""",
        "decisions": """SELECT 'decision' AS kind, d.ref, c.code AS company, d.title,
                            left(d.what, 400) AS body, d.created_at AS at
                        FROM cartable.decisions d JOIN core.companies c ON c.id = d.company_id
                        WHERE core.fa_normalize(d.title || ' ' || d.what || ' ' || d.why) LIKE :pat""",
        "work": """SELECT 'work' AS kind, w.ref, c.code AS company, w.title, left(w.brief, 400) AS body,
                       w.created_at AS at
                   FROM work.work w JOIN core.companies c ON c.id = w.company_id
                   WHERE core.fa_normalize(w.title || ' ' || w.brief) LIKE :pat""",
        "messages": """SELECT 'message' AS kind, m.ref, c.code AS company, t.title_fa AS title,
                           left(m.body, 400) AS body, m.created_at AS at
                       FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
                       JOIN core.companies c ON c.id = m.company_id
                       WHERE core.fa_normalize(m.body) LIKE :pat""",
    }
    hits: list[dict[str, Any]] = []
    async with read_tx(ctx) as tx:
        pat = "%" + await tx.scalar("SELECT core.like_escape(core.fa_normalize(:q))", q=q) + "%"
        for k in wanted:
            hits += await tx.all(
                queries[k]
                + " AND (CAST(:co AS uuid) IS NULL OR c.id = :co) ORDER BY at DESC LIMIT :lim",
                pat=pat,
                co=co.id if co else None,
                lim=limit,
            )
    hits.sort(key=lambda h: h["at"], reverse=True)
    return [
        Hit(
            kind=h["kind"],
            ref=h["ref"],
            company=h["company"],
            title=h["title"],
            snippet=(h["body"] or "")[:SNIPPET],
            at=h["at"],
        )
        for h in hits[:limit]
    ]


# -------------------------------------------------------------- audit.recent --
class AuditBrief(BaseModel):
    seq: int
    at: datetime
    actor: str
    company: str
    action: str
    action_class: str
    target: str
    summary: str


@router.get("/audit/recent", response_model=list[AuditBrief], responses=E)
async def tool_audit_recent(
    company: str | None = Query(default=None, pattern=CODE),
    action: str | None = Query(default=None, pattern=r"^[a-z_]+(\.[a-z_]+)?$"),
    since: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    ctx: Ctx = Depends(internal_ctx),
) -> list[AuditBrief]:
    """audit.recent: audit rows (metadata only) for oversight roles and the advisor."""
    _agent(ctx)
    await allow(ctx, "audit.read", {"company": company})
    co = await ctx.hub.companies.by_code(company) if company else None
    async with read_tx(ctx) as tx:
        rows = await tx.all(
            """SELECT a.seq, a.at, a.actor_kind || ':' || a.actor_code AS actor, c.code AS company, a.action,
                      a.action_class, a.target_kind || ':' || a.target_ref AS target, a.summary
               FROM audit.entries a JOIN core.companies c ON c.id = a.company_id
               WHERE (CAST(:co AS uuid) IS NULL OR a.company_id = :co)
                 AND (CAST(:action AS text) IS NULL OR a.action = :action OR a.action LIKE :prefix)
                 AND (CAST(:since AS timestamptz) IS NULL OR a.at >= :since)
               ORDER BY a.seq DESC LIMIT :lim""",
            co=co.id if co else None,
            action=action,
            prefix=f"{action}.%" if action and "." not in action else "",
            since=since,
            lim=limit,
        )
    return [AuditBrief(**r) for r in rows]


# -------------------------------------------------------------------- memory --
class MemoryNote(BaseModel):
    id: int
    note: str
    tags: list[str]
    source: str | None
    at: datetime


class MemoryIn(Model):
    note: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=10)


MEMORY_LIMIT_CHARS = 12_000


@router.get("/memory", response_model=list[MemoryNote], responses=E)
async def tool_memory_read(
    limit: int = Query(default=20, ge=1, le=100), ctx: Ctx = Depends(internal_ctx)
) -> list[MemoryNote]:
    """memory.read: the employee's own notes, latest first, capped in size."""
    _agent(ctx)
    await allow(ctx, "memory.read", {"employee": ctx.who.code})
    async with read_tx(ctx) as tx:
        rows = await tx.all(
            """SELECT m.id, m.note, m.tags, s.code AS source, m.created_at AS at
               FROM core.employee_memory m LEFT JOIN core.employees s ON s.id = m.source_employee_id
               WHERE m.employee_id = :e ORDER BY m.id DESC LIMIT :lim""",
            e=ctx.who.employee_id,
            lim=limit,
        )
    out: list[MemoryNote] = []
    size = 0
    for r in rows:
        size += len(r["note"])
        if size > MEMORY_LIMIT_CHARS and out:
            break
        out.append(MemoryNote(**{**r, "tags": list(r["tags"] or [])}))
    return out


@router.post("/memory", response_model=MemoryNote, status_code=201, responses=E)
async def tool_memory_write(
    body: MemoryIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """memory.write: append one note to the employee's own memory (append-only).
    Honours `Idempotency-Key` (a retried call writes the note once)."""
    _agent(ctx)
    await allow(ctx, "memory.write", {"employee": ctx.who.code})
    tags = sorted({t.strip()[:40] for t in body.tags if t.strip()})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        row = await tx.one(
            """INSERT INTO core.employee_memory (company_id, employee_id, run_id, note, tags)
               VALUES (:co, :e, CAST(:run AS uuid), :note, :tags)
               RETURNING id, note, tags, created_at AS at""",
            co=ctx.who.company_id,
            e=ctx.who.employee_id,
            run=ctx.who.run_id,
            note=body.note,
            tags=tags,
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,  # type: ignore[arg-type]
            action="memory.write",
            action_class="A1",
            target_kind="employee",
            target_ref=ctx.who.code,
            summary=f"note {row['id']}",
        )
        note = MemoryNote(
            id=row["id"], note=row["note"], tags=list(row["tags"]), source=None, at=row["at"]
        )
        if idem:
            await idem.store(tx, 201, note.model_dump(mode="json"))
    return note


# ------------------------------------------------------- the run's own gate --
class ReserveIn(Model):
    tool: str = Field(pattern=r"^[a-z][a-z_]*(\.[a-z_]+)?$", max_length=40)
    step: int = Field(ge=1, le=50)


class Gate(BaseModel):
    run_id: UUID
    employee: str
    company: str
    kind: str
    department: str | None
    role: str | None
    charter_version: int | None
    scope: str
    status: str
    lock: str | None
    own_thread: str | None
    work_ref: str | None
    escrow_classes: list[str]
    model: str | None
    effort: str | None
    tool_calls: int
    tool_calls_cap: int
    step: int
    step_tool_calls: int
    step_tool_calls_cap: int
    # ⟨1.4⟩ the overseer's open holds on this run (its employee, its work, or
    # `tool:<name>` for one tool): the gateway refuses every action but reads.
    held: list[str] = Field(default_factory=list)


@router.post("/runs/self/reserve", response_model=Gate, responses=E)
async def run_reserve(body: ReserveIn, ctx: Ctx = Depends(internal_ctx)) -> Gate:
    """The gateway reserves one tool call of the token's run before it acts: the
    caps per step and per run hold in the database, steps never go back. 429
    rate_limited when a cap is reached."""
    _agent(ctx)
    await allow(ctx, "run.reserve", {"employee": ctx.who.code})
    async with ctx.tx() as tx:
        row = await tx.first(
            """UPDATE agents.runs
                  SET tool_calls = tool_calls + 1,
                      step_tool_calls = CASE WHEN current_step = :step THEN step_tool_calls + 1 ELSE 1 END,
                      current_step = :step
                WHERE id = CAST(:run AS uuid) AND employee_id = :e AND state = 'running'
                  AND :step >= current_step AND tool_calls < tool_calls_cap
                  AND (current_step <> :step OR step_tool_calls < step_tool_calls_cap)
                RETURNING id, work_id, model, effort, charter_version, tool_calls, tool_calls_cap,
                          current_step, step_tool_calls, step_tool_calls_cap""",
            run=ctx.who.run_id,
            e=ctx.who.employee_id,
            step=body.step,
        )
        if row is None:
            raise ApiError(
                429,
                "rate_limited",
                "tool-call cap of this run or step reached",
                headers={"Retry-After": str(CAP_RETRY_AFTER_S)},
            )
        w = await W.load(tx, row["work_id"]) if row["work_id"] else None
        escrow = await escrow_of(tx, w) if w else []
        lock = await tx.scalar("SELECT control.lock_state(:co)", co=ctx.who.company_id)
        thread = await tx.scalar(
            """SELECT code FROM msg.threads WHERE employee_id = :e
                 AND kind IN ('advisor', 'overseer', 'assistant', 'legal', 'ceo', 'manager', 'employee')
               ORDER BY kind IN ('advisor', 'overseer', 'assistant', 'legal') DESC LIMIT 1""",
            e=ctx.who.employee_id,
        )
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as all_tx:
        held = await oversight.holds_for_run(all_tx, ctx.who.code, w["ref"] if w else None)
    assert ctx.who.company is not None
    return Gate(
        run_id=row["id"],
        employee=ctx.who.code,
        company=ctx.who.company,
        kind=ctx.who.role,
        department=ctx.who.department,
        role=ctx.who.charter,
        charter_version=row["charter_version"],
        scope=ctx.who.scope,
        status=ctx.who.status or "active",
        lock=lock,
        own_thread=thread,
        work_ref=w["ref"] if w else None,
        escrow_classes=escrow,
        model=row["model"],
        effort=row["effort"],
        tool_calls=row["tool_calls"],
        tool_calls_cap=row["tool_calls_cap"],
        step=row["current_step"],
        step_tool_calls=row["step_tool_calls"],
        step_tool_calls_cap=row["step_tool_calls_cap"],
        held=held,
    )


class ToolCallIn(Model):
    tool: str = Field(pattern=r"^[a-z][a-z_]*(\.[a-z_]+)?$", max_length=40)
    cls: Literal["A0", "A1", "A2", "A3", "A4"] | None = Field(default=None, alias="class")
    outcome: Literal["ok", "denied", "error"]
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,60}$")
    ref: str | None = Field(default=None, max_length=80)
    step: int = Field(ge=1, le=50)


@router.post("/runs/self/tool-calls", status_code=204, response_class=Response, responses=E)
async def run_record_tool_call(body: ToolCallIn, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """One audit row per tool call (tool, class, outcome, ref) - never its input
    or output. Written by the gateway after the call."""
    _agent(ctx)
    await allow(ctx, "run.record", {"employee": ctx.who.code})
    async with ctx.tx() as tx:
        await audit.record(
            tx,
            ctx.who,
            company_id=ctx.who.company_id,  # type: ignore[arg-type]
            action="tool.call",
            action_class=body.cls or "A0",
            target_kind="tool",
            target_ref=body.tool,
            summary=" ".join(
                x for x in (body.outcome, body.code or "", body.ref or "", f"step {body.step}") if x
            )[:500],
            request_id=ctx.request_id,
        )
    return Response(status_code=204)


# ------------------------------------------------------------- live replies --
@router.post("/threads/{code}/live", status_code=204, response_class=Response, responses=E)
async def push_live(code: str, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The reply being written, pushed by the runtime as NDJSON lines
    {type: reply.started|reply.delta|reply.done|reply.failed, ...} and fanned
    out to the owner's GET /api/v1/threads/{code}/live. Never stored, never on
    NATS, never logged; the final text is the stored message."""
    _agent(ctx)
    async with read_tx(ctx) as tx:
        t = await tx.one(
            """SELECT t.code, t.kind, c.code AS company, d.code AS department FROM msg.threads t
               JOIN core.companies c ON c.id = t.company_id LEFT JOIN core.departments d ON d.id = t.department_id
               WHERE t.code = :c""",
            c=code,
        )
    await allow(
        ctx,
        "thread.live",
        {
            "thread_code": t["code"],
            "thread_kind": t["kind"],
            "thread_company": t["company"],
            "thread_department": t["department"],
        },
    )
    live = ctx.hub.live
    if live is None:
        raise ApiError(503, "live_unavailable", "live replies are off")
    size, buf = 0, b""
    async for chunk in request.stream():
        size += len(chunk)
        if size > LIVE_MAX_BYTES:
            raise ApiError(413, "validation_failed", "live stream too large")
        buf += chunk
        *lines, buf = buf.split(b"\n")
        for line in lines:
            _publish_line(live, code, ctx.who.run_id, line)
    if buf.strip():
        _publish_line(live, code, ctx.who.run_id, buf)
    return Response(status_code=204)


def _publish_line(live: Any, thread: str, run_id: str | None, line: bytes) -> None:
    if not line.strip():
        return
    try:
        ev = json.loads(line)
    except ValueError:
        return
    if not isinstance(ev, dict) or ev.get("type") not in LIVE_TYPES:
        return
    data: dict[str, Any] = {"run_id": run_id}
    if ev["type"] == "reply.delta":
        text = ev.get("text")
        if not isinstance(text, str) or not text:
            return
        data["text"] = text[:4000]
    elif ev["type"] == "reply.done":
        data["message_ref"] = str(ev.get("message_ref") or "")[:40]
    elif ev["type"] == "reply.failed":
        data["code"] = str(ev.get("code") or "internal_error")[:60]
    live.publish(thread, ev["type"], data)


# -------------------------------------------------------------- files.read --
class Frame(BaseModel):
    """A key frame of a video (contract §17.8): its file and where it is (s)."""

    id: UUID
    at_s: float | None = None


class AgentFileRef(FileRef):
    """files.read: an owner file attached in the agent's own company (§17.1),
    plus the key frames of a video; the model sees images as vision input.
    `frames`: [{id, at_s}] in time order; `agent`: the image copy a model sees
    (long edge <= 1568, no EXIF); `text`: a PDF's text (prompt 07 §3), masked."""

    frames: list[Frame] = Field(default_factory=list)
    agent: UUID | None = None
    text: str | None = None


@router.get("/files/{id}/meta", response_model=AgentFileRef, responses=E)
async def tool_file_meta(id: UUID, ctx: Ctx = Depends(internal_ctx)) -> AgentFileRef:
    """files.read: own company only (never another's, whatever the charter's
    scope); the policy is decided before the lookup, so a missing and a
    forbidden file answer the same 403."""
    _agent(ctx)
    await allow(ctx, "file.read", {"company": ctx.who.company})
    async with ctx.tx() as tx:  # the agent's own company (RLS)
        # An owner upload not attached anywhere yet is nobody's to read (06.1 §3).
        row = await tx.first(
            F.FILE_SQL
            + f" WHERE f.id = :id AND f.variant = 'original' AND NOT {F.UNATTACHED_UPLOAD}",
            id=id,
        )
        if row is None:
            raise ApiError(403, "policy_denied", "file.read_not_permitted")
        frames = await tx.all(
            """SELECT id, frame_at_s FROM files.files WHERE parent_id = :id AND variant = 'frame'
               ORDER BY frame_at_s NULLS LAST, created_at""",
            id=id,
        )
        agent = await tx.scalar(
            "SELECT id FROM files.files WHERE parent_id = :id AND variant = 'agent' LIMIT 1", id=id
        )
        text = await tx.scalar("SELECT text FROM files.processing WHERE file_id = :id", id=id)
    ref = F.render(row)
    return AgentFileRef(
        **ref.model_dump(),
        frames=[
            Frame(id=r["id"], at_s=float(r["frame_at_s"]) if r["frame_at_s"] is not None else None)
            for r in frames
        ],
        agent=agent,
        text=await scrub_async(text) if text else None,
    )
