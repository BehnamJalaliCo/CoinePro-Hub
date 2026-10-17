"""Internal API for the agent runtime and services (contract §12).

Never routed by Caddy. Every call is checked against OPA (`hq.internal`):
an agent acts only in its own company, department and role. While its
company (or the holding) is locked, an agent's writes get 423
company_locked. Agents act under RLS scoped to their own company; the one
cross-company path (CEO -> CEO work request) widens the scope for that
single insert after the policy allowed it.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, internal_ctx
from hq_api.db import Tx
from hq_api.domain import control, hiring, notify, org
from hq_api.domain import decisions as D
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.principal import Principal
from hq_api.routes.messages import (
    MESSAGE_SQL,
    Citation,
    Links,
    Message,
    post_message,
    render_messages,
    validate_citations,
)
from hq_api.schemas import EMPLOYEE_CODE, Evidence, FileRef, Model
from hq_api.workshop import service as workshop_service

router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
Priority = Literal["P0", "P1", "P2", "P3", "P4"]
MIME = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")


# ------------------------------------------------------------------ models --
class Progress(Model):
    note: str = Field(min_length=1, max_length=2000)
    pct: int | None = Field(default=None, ge=0, le=100)


class Delegate(Model):
    to: str = Field(pattern=EMPLOYEE_CODE)
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(default="", max_length=50000)
    priority: Priority | None = None
    due_at: datetime | None = None
    budget: W.BudgetIn | None = None


class UsageIn(Model):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    equiv_cost_usd: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=6)
    cost_usd: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=6)


class ProducedWith(Model):
    connection: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=100)
    effort: str | None = Field(default=None, max_length=10)
    label_fa: str | None = Field(default=None, max_length=100)


class Deliver(Model):
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=5000)
    body: str | None = Field(default=None, max_length=500000)
    attachments: list[UUID] = Field(default_factory=list, max_length=20)
    produced_with: ProducedWith = Field(default_factory=ProducedWith)
    usage: UsageIn = Field(default_factory=UsageIn)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)


class Fail(Model):
    reason: str = Field(min_length=1, max_length=2000)
    decline: bool = False


class DeliverOut(BaseModel):
    work: W.Work
    deliverable: str
    closed_children: list[str]


class WorkRequest(Model):
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    to: str | None = Field(default=None, pattern=EMPLOYEE_CODE)
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(default="", max_length=50000)
    kind: Literal["one_off", "recurring", "event", "project"] = "one_off"
    priority: Priority = "P3"
    due_at: datetime | None = None
    budget: W.BudgetIn | None = None
    escrow: W.EscrowIn | None = None
    schedule: W.ScheduleIn | None = None
    requested_by_work_id: UUID | None = None


class WorkCreated(BaseModel):
    work: W.Work
    decision: str | None


class AgentDecide(Model):
    note: str | None = Field(default=None, max_length=5000)
    reason_code: Literal["cost", "risk", "timing", "quality", "other"] | None = None


class AgentMessage(Model):
    body: str = Field(min_length=1, max_length=100000)
    links: Links | None = None
    attachments: list[UUID] = Field(default_factory=list, max_length=20)
    # Validated server-side: a ref that does not exist or that the author may
    # not read is dropped and counted in meta.citations_dropped (contract §16.3).
    citations: list[Citation] = Field(default_factory=list, max_length=50)


class Activity(Model):
    employee: str = Field(pattern=EMPLOYEE_CODE)
    activity: Literal["sleeping", "working", "waiting", "error"]
    note: str | None = Field(default=None, max_length=500)


class NotificationIn(Model):
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    level: Literal["urgent", "decision", "report", "info", "learning"]
    title_fa: str = Field(min_length=1, max_length=300)
    body_fa: str = Field(default="", max_length=4000)
    link_kind: str | None = Field(default=None, pattern=r"^[a-z_]{2,30}$")
    link_ref: str | None = Field(default=None, max_length=100)
    choices: list[dict[str, str]] | None = Field(default=None, max_length=6)
    # Agents raise 🔴 only for an incident category (policy data); else it becomes 🟡.
    category: Literal["service_down", "security", "data_loss", "budget_hard_stop"] | None = None


class NotificationOut(BaseModel):
    id: UUID
    level: str
    state: str


class KillSwitchIn(Model):
    scope: str = Field(pattern=r"^(holding|company:[A-Z][A-Z0-9]{1,9})$")
    state: Literal["engaged", "released"]
    reason: str = Field(min_length=1, max_length=1000)


class FreezeIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    until: datetime
    reason: str = Field(min_length=1, max_length=1000)


class ContextOut(BaseModel):
    employee: org.Employee
    company: dict[str, Any]
    owner: dict[str, Any]
    open_work: list[W.Work]


# ----------------------------------------------------------------- helpers --
# The action class of every internal write (OPERATING_MODEL §1.12). Reads are A0.
# A3 never happens here (it goes through a decision) and A4 never at all.
OP_CLASS: dict[str, str] = {
    "context.read": "A0",
    "activity.set": "A0",
    "work.accept": "A1",
    "work.progress": "A1",
    "work.deliver": "A1",
    "work.fail": "A1",
    "decision.propose": "A1",
    "decision.approve": "A2",
    "message.post": "A1",
    "notification.raise": "A1",
    "file.upload": "A1",
    "work.delegate": "A2",
    "work.create": "A2",
    "kill_switch.set": "A2",
    "deploy_freeze.set": "A2",
    # prompt 05: the Tool Gateway's reads, memory, the run itself, live replies
    "work.read": "A0",
    "company.read": "A0",
    "health.read": "A0",
    "hub.read": "A0",
    "treasury.read": "A0",
    "knowledge.read": "A0",
    "audit.read": "A0",
    "memory.read": "A0",
    "memory.write": "A1",
    "run.reserve": "A0",
    "run.record": "A0",
    "thread.live": "A1",
    "file.read": "A0",
    # prompt 07: backups.status (the overseer, the platform SRE)
    "backup.read": "A0",
    # prompt 06: the Code Workshop (the grant's driver)
    "workshop.read": "A0",
    "workshop.session": "A1",
    "workshop.message": "A1",
}


async def lock_state(hub: Any, who: Principal) -> str | None:
    """'holding' | 'company' | 'deploy_freeze' | None for the agent's company
    right now (control.lock_state: kill switch or deploy freeze)."""
    if who.company_id is None:
        return "company"  # an agent without a company is treated as locked (safe side)
    async with hub.db.raw() as tx:
        state: str | None = await tx.scalar("SELECT control.lock_state(:co)", co=who.company_id)
    return state


async def action_gate(
    hub: Any,
    who: Principal,
    name: str,
    cls: str,
    *,
    escrow_classes: list[str],
    incident: bool = False,
) -> None:
    """hq.actions: A0-A3 by role and escrow, A4 always denied for non-owners.
    The real lock state goes in; a refusal for that reason alone is the
    contract's 423 company_locked, not a 403."""
    lock = await lock_state(hub, who) if who.is_agent else None
    verdict = await hub.policy.query(
        "actions",
        {
            "principal": who.opa(),
            "action": {"class": cls, "name": name, "company": who.company},
            "context": {
                "escrow_classes": escrow_classes,
                "company_locked": lock is not None,
                "incident": incident,
            },
        },
    )
    if verdict.allow:
        return
    if "policy_unavailable" in verdict.reasons:
        raise ApiError(503, "policy_unavailable", "policy service unavailable (fail-closed)")
    if verdict.reasons == ("company_locked",):
        raise ApiError(423, "company_locked", f"locked: {lock}")
    raise ApiError(403, "policy_denied", ", ".join(verdict.reasons) or "denied")


async def allow(
    ctx: Ctx,
    op: str,
    target: dict[str, Any],
    *,
    escrow_classes: list[str] | None = None,
    incident: bool = False,
) -> None:
    """hq.internal (who may do what, where), then hq.actions for agents."""
    await ctx.hub.policy.require(
        "internal", {"principal": ctx.who.opa(), "op": op, "target": target}
    )
    if ctx.who.is_agent:
        await action_gate(
            ctx.hub,
            ctx.who,
            op,
            OP_CLASS[op],
            escrow_classes=escrow_classes or [],
            incident=incident,
        )


async def escrow_of(tx: Tx, w: dict[str, Any]) -> list[str]:
    """Allowed classes of the work's escrow (or of its recurring template's)."""
    classes = await tx.scalar(
        """SELECT allowed_action_classes FROM work.escrows
           WHERE status = 'active'
             AND work_id IN (CAST(:w AS uuid), COALESCE(CAST(:t AS uuid), CAST(:w AS uuid))) LIMIT 1""",
        w=str(w["id"]),
        t=str(w["recurrence_of"]) if w.get("recurrence_of") else None,
    )
    return list(classes or [])


async def work_for(ctx: Ctx, tx: Tx, id: UUID, op: str) -> dict[str, Any]:
    w = await W.load(tx, id, lock=True)
    await allow(
        ctx,
        op,
        {"assignee": w["a_code"], "company": w["company"]},
        escrow_classes=await escrow_of(tx, w),
    )
    await ctx.ensure_unlocked(tx, w["company_id"])
    return w


async def _audit_work(
    ctx: Ctx, tx: Tx, w: dict[str, Any], action: str, summary: str = "", cls: str = "A1"
) -> None:
    await ctx.audit(
        tx,
        company_id=w["company_id"],
        action=action,
        action_class=cls,
        target_kind="work",
        target_ref=w["ref"],
        summary=summary,
    )


# -------------------------------------------------------------------- work --
@router.post("/work/{id}/accept", response_model=W.Work, responses=E)
async def accept_work(id: UUID, ctx: Ctx = Depends(internal_ctx)) -> W.Work:
    """The assignee takes the work (queued or waiting -> in_progress)."""
    async with ctx.tx() as tx:
        w = await work_for(ctx, tx, id, "work.accept")
        if w["status"] not in ("queued", "waiting"):
            raise ApiError(409, "validation_failed", f"work is {w['status']}")
        await W.set_status(tx, w, "in_progress", accepted_at=datetime.now().astimezone())
        await W.event(tx, w, "accepted", ctx.who)
        await _audit_work(ctx, tx, w, "work.accept")
        await ctx.emit(tx, w["company"], "work.updated", w["ref"], {"status": "in_progress"})
        return W.render(await W.load(tx, id))


@router.post("/work/{id}/progress", response_model=W.Work, responses=E)
async def progress_work(id: UUID, body: Progress, ctx: Ctx = Depends(internal_ctx)) -> W.Work:
    """A progress note (and optional percentage) on the assignee's work."""
    async with ctx.tx() as tx:
        w = await work_for(ctx, tx, id, "work.progress")
        if w["status"] in W.CLOSED:
            raise ApiError(409, "validation_failed", f"work is {w['status']}")
        status = "in_progress" if w["status"] == "queued" else w["status"]
        await W.set_status(tx, w, status, progress_note=body.note, progress_pct=body.pct)
        await W.event(tx, w, "progress", ctx.who, {"pct": body.pct})
        await _audit_work(
            ctx, tx, w, "work.progress", f"{body.pct}%" if body.pct is not None else ""
        )
        await ctx.emit(tx, w["company"], "work.updated", w["ref"], {"progress_pct": body.pct})
        return W.render(await W.load(tx, id))


@router.post("/work/{id}/delegate", response_model=W.Work, status_code=201, responses=E)
async def delegate_work(
    id: UUID, body: Delegate, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """CEO -> manager, manager -> employee of the same department. Depth and
    budget are enforced by the database (409 delegation_depth_exceeded /
    budget_exceeded). Returns the child work."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        w = await W.load(tx, id, lock=True)
        to = await tx.first(
            """SELECT e.kind, c.code AS company, d.code AS department FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE e.code = :c""",
            c=body.to,
        )
        await allow(
            ctx,
            "work.delegate",
            {
                "assignee": w["a_code"],
                "company": w["company"],
                "to_role": to["kind"] if to else None,
                "to_department": to["department"] if to else None,
            },
            escrow_classes=await escrow_of(tx, w),
        )
        await ctx.ensure_unlocked(tx, w["company_id"])
        child = await W.delegate(
            tx,
            ctx.who,
            w,
            to_code=body.to,
            title=body.title,
            brief=body.brief,
            priority=body.priority,
            due_at=body.due_at,
            budget=body.budget,
        )
        await _audit_work(
            ctx, tx, child, "work.delegate", f"from {w['ref']} to {body.to}", cls="A2"
        )
        result = W.render(child)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


async def _run_ledger(tx: Tx, actor: str, run_id: str) -> tuple[UsageIn, dict[str, Any]]:
    """Usage (every token kind and both costs) and the connection, provider,
    model and effort of a run, from llm.calls (the router's ledger)."""
    row = await tx.one(
        """SELECT COALESCE(sum(c.input_tokens), 0) AS i, COALESCE(sum(c.output_tokens), 0) AS o,
                  COALESCE(sum(c.cache_read_tokens), 0) AS cr, COALESCE(sum(c.cache_write_tokens), 0) AS cw,
                  COALESCE(sum(c.equiv_cost_usd), 0) AS eq, COALESCE(sum(c.cost_usd), 0) AS usd,
                  (array_agg(cn.key ORDER BY c.started_at DESC))[1] AS connection,
                  (array_agg(c.provider ORDER BY c.started_at DESC))[1] AS provider,
                  (array_agg(c.model ORDER BY c.started_at DESC) FILTER (WHERE c.model IS NOT NULL))[1] AS model,
                  (array_agg(c.effort ORDER BY c.started_at DESC) FILTER (WHERE c.effort IS NOT NULL))[1] AS effort
           FROM llm.calls c LEFT JOIN llm.connections cn ON cn.id = c.connection_id
           WHERE c.actor_ref = :actor AND c.meta->>'run_id' = :run
             AND c.started_at >= (SELECT COALESCE(r.started_at, r.queued_at) - interval '1 minute'
                                  FROM agents.runs r WHERE r.id = CAST(:run AS uuid))""",
        actor=actor,
        run=run_id,
    )
    usage = UsageIn(
        input_tokens=int(row["i"]),
        output_tokens=int(row["o"]),
        cache_read_tokens=int(row["cr"]),
        cache_write_tokens=int(row["cw"]),
        equiv_cost_usd=Decimal(row["eq"]),
        cost_usd=Decimal(row["usd"]),
    )
    produced = {
        k: row[k] for k in ("connection", "provider", "model", "effort") if row[k] is not None
    }
    return usage, produced


# The urgent cap is per company per (rolling) hour: try again after a while.
URGENT_RETRY_AFTER_S = 600


async def _request_budget(
    ctx: Ctx, tx: Tx, body: WorkRequest
) -> tuple[UUID | None, W.BudgetIn | None]:
    """An agent's request opens root work that would wake another agent:
    without a budget and a bound, two managers (or CEOs) could wake each other
    for ever (prompt 5.1 §2.6). The request is tied to the work it came from
    (the run's own work by default); its token budget is what that work has
    left, at most AGENT_REQUEST_BUDGET_TOKENS (and never more than asked);
    a chain of requests is at most AGENT_REQUEST_CHAIN_MAX hops long."""
    s = ctx.hub.settings
    origin = body.requested_by_work_id
    if origin is None and ctx.who.run_id is not None:
        origin = await tx.scalar(
            """SELECT r.work_id FROM agents.runs r JOIN work.work w ON w.id = r.work_id
               WHERE r.id = CAST(:run AS uuid) AND w.company_id = :co""",
            run=ctx.who.run_id,
            co=ctx.who.company_id,
        )
    cap = s.agent_request_budget_tokens
    if origin is not None:
        # Every company's view: a chain may have crossed companies (CEO to CEO).
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as all_tx:
            hops = await all_tx.scalar(
                """WITH RECURSIVE chain(id, hops) AS (
                       SELECT w.root_id, 0 FROM work.work w WHERE w.id = :id
                       UNION ALL
                       SELECT p.root_id, c.hops + 1 FROM chain c
                       JOIN work.work r ON r.id = c.id
                       JOIN work.work p ON p.id = r.requested_by_work_id
                       WHERE c.hops < 20)
                   SELECT max(hops) FROM chain""",
                id=origin,
            )
            left = await all_tx.first(
                """SELECT budget_tokens - tokens_used
                          - (SELECT COALESCE(sum(c.budget_tokens), 0) FROM work.work c WHERE c.parent_id = w.id)
                          AS left
                   FROM work.work w WHERE w.id = :id AND budget_tokens IS NOT NULL""",
                id=origin,
            )
        if int(hops or 0) + 1 > s.agent_request_chain_max:
            raise ApiError(
                409,
                "delegation_depth_exceeded",
                f"a chain of requests is at most {s.agent_request_chain_max} long",
            )
        if left is not None:
            cap = max(0, min(cap, int(left["left"])))
    if body.kind == "recurring":  # bounded by its escrow, approved by a decision
        return origin, body.budget
    if cap <= 0:  # nothing left to hand on: no work with a zero budget
        raise ApiError(409, "budget_exceeded", "the requesting work has no token budget left")
    asked = body.budget.tokens if body.budget and body.budget.tokens is not None else None
    tokens = min(asked, cap) if asked is not None else cap
    usd = body.budget.usd if body.budget else None
    return origin, W.BudgetIn(tokens=tokens, usd=usd)


@router.post("/work/{id}/deliver", response_model=DeliverOut, responses=E)
async def deliver_work(
    id: UUID, body: Deliver, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """Creates the Deliverable (cartable of outputs) and marks the work
    delivered; its delivered children become done. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        w = await work_for(ctx, tx, id, "work.deliver")
        if w["status"] in W.CLOSED or w["status"] == "delivered":
            raise ApiError(409, "validation_failed", f"work is {w['status']}")
        if body.attachments:
            n = await tx.scalar(
                "SELECT count(*) FROM files.files WHERE id = ANY(:ids) AND company_id = :co",
                ids=body.attachments,
                co=w["company_id"],
            )
            if n != len(set(body.attachments)):
                raise ApiError(422, "validation_failed", fields={"attachments": "unknown files"})
        pw = body.produced_with.model_dump(exclude_none=True)
        u = body.usage
        if ctx.who.run_id is not None:
            # A registered run: what the deliverable cost and what produced it come
            # from the run's own ledger rows, never from the agent (prompt 5.1 §2.7).
            u, pw = await _run_ledger(tx, ctx.who.code, ctx.who.run_id)
        if "label_fa" not in pw and pw.get("model"):
            pw["label_fa"] = f"انجام‌شده با {pw['model']}"
        dl = await tx.one(
            """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
                   attachments, produced_with, usage, evidence)
               VALUES (:co, :w, :p, :title, :summary, :body, CAST(:att AS uuid[]), CAST(:pw AS jsonb),
                       CAST(:usage AS jsonb), CAST(:ev AS jsonb))
               RETURNING id, ref""",
            co=w["company_id"],
            w=w["id"],
            p=ctx.who.employee_id,
            title=body.title,
            summary=body.summary,
            body=body.body,
            att=[str(a) for a in body.attachments],
            pw=_json(pw),
            usage=u.model_dump_json(),
            ev=W.evidence_json(body.evidence),
        )
        if ctx.who.run_id is None:
            # A registered run's usage is booked on the work by the runtime, step
            # by step (agents.runs); a deliverable's `usage` is what it shows.
            await W.add_usage(
                tx,
                w,
                u.input_tokens + u.output_tokens + u.cache_read_tokens + u.cache_write_tokens,
                u.equiv_cost_usd + u.cost_usd,
            )
        await W.set_status(tx, w, "delivered", delivered_at=datetime.now().astimezone())
        closed = await W.close_delivered_children(tx, w, ctx.who)
        await W.event(
            tx, w, "delivered", ctx.who, {"deliverable": dl["ref"], "closed_children": closed}
        )
        await _audit_work(ctx, tx, w, "work.deliver", f"deliverable {dl['ref']}")
        await ctx.emit(
            tx,
            w["company"],
            "deliverable.created",
            dl["ref"],
            {"work": w["ref"], "producer": ctx.who.code},
        )
        await ctx.emit(tx, w["company"], "work.updated", w["ref"], {"status": "delivered"})
        if w["parent_id"] is None:
            await notify.raise_notification(
                tx,
                company_id=w["company_id"],
                company_code=w["company"],
                level="info",
                title_fa=f"خروجی تازه {dl['ref']}: {body.title[:120]}",
                link_kind="deliverable",
                link_ref=dl["ref"],
                source_kind="agent",
                source_code=ctx.who.code,
            )
        result = DeliverOut(
            work=W.render(await W.load(tx, id)), deliverable=dl["ref"], closed_children=closed
        )
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@router.post("/work/{id}/fail", response_model=W.Work, responses=E)
async def fail_work(id: UUID, body: Fail, ctx: Ctx = Depends(internal_ctx)) -> W.Work:
    """`decline: true` turns down a cross-department request (status cancelled)."""
    async with ctx.tx() as tx:
        w = await work_for(ctx, tx, id, "work.fail")
        if w["status"] in W.CLOSED:
            raise ApiError(409, "validation_failed", f"work is {w['status']}")
        status = "cancelled" if body.decline else "failed"
        await W.set_status(
            tx, w, status, close_reason=body.reason, closed_at=datetime.now().astimezone()
        )
        await W.event(
            tx, w, "declined" if body.decline else "failed", ctx.who, {"reason": body.reason[:200]}
        )
        await _audit_work(ctx, tx, w, "work.decline" if body.decline else "work.fail")
        await ctx.emit(tx, w["company"], "work.updated", w["ref"], {"status": status})
        return W.render(await W.load(tx, id))


@router.post("/work", response_model=WorkCreated, status_code=201, responses=E)
async def request_work(
    body: WorkRequest, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """An agent opens work: a manager requests another department's manager
    (cross-department), a CEO hands work to its managers or asks another
    company's CEO (the only cross-company path). Recurring work proposed by an
    agent waits for a `recurring_approval` decision. Requires `Idempotency-Key`."""
    if ctx.who.kind != "agent":
        raise ApiError(403, "policy_denied", "agents only")
    company_code = body.company or ctx.who.company
    assert company_code is not None
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        cross = company_code != ctx.who.company
        # The policy decides BEFORE anything outside the agent's company is
        # looked up, so a refusal never tells whether a code exists elsewhere.
        if cross:
            if body.to or body.department:  # CEO to CEO only: addressed to the company
                raise ApiError(403, "policy_denied", "work.create_not_permitted")
            to_role: str | None = "ceo"
            to_dept: str | None = None
        else:
            to_role, to_dept = "ceo", body.department
            if body.to:
                t = await tx.first(  # under the agent's own scope: other companies are invisible
                    """SELECT e.kind, d.code AS department FROM core.employees e
                       LEFT JOIN core.departments d ON d.id = e.department_id WHERE e.code = :c""",
                    c=body.to,
                )
                to_role, to_dept = (t["kind"], t["department"]) if t else (None, None)
            elif body.department:
                to_role = "manager"
        await allow(
            ctx,
            "work.create",
            {
                "company": company_code,
                "kind": body.kind,
                "to_role": to_role,
                "to_department": to_dept,
            },
        )
        # Looked up only now: a missing and a forbidden company both answer 403.
        company = await ctx.hub.companies.find(company_code)
        if company is None:
            raise ApiError(403, "policy_denied", "work.create_not_permitted")
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        if cross:
            await tx.rescope([ctx.who.company_id, company.id])
            await ctx.ensure_unlocked(tx, company.id)  # the destination is locked too
        if body.requested_by_work_id is not None and not await tx.scalar(
            "SELECT 1 FROM work.work WHERE id = :id AND company_id = :co",
            id=body.requested_by_work_id,
            co=ctx.who.company_id,
        ):
            raise ApiError(
                422, "validation_failed", fields={"requested_by_work_id": "unknown work of yours"}
            )
        requested_by, budget = await _request_budget(ctx, tx, body)
        w = await W.create(
            tx,
            ctx.who,
            company_id=company.id,
            company_code=company.code,
            title=body.title,
            brief=body.brief,
            kind=body.kind,
            priority=body.priority,
            department_code=body.department,
            assignee_code=body.to,
            due_at=body.due_at,
            budget=budget,
            escrow=body.escrow,
            schedule=body.schedule,
            requested_by_work_id=requested_by,
        )
        decision_ref = None
        if body.kind == "recurring":
            assert body.escrow is not None
            assert body.schedule is not None
            d = await D.propose(
                tx,
                ctx.who,
                company_id=company.id,
                company_code=company.code,
                body=D.DecisionIn(
                    kind="recurring_approval",
                    title=f"Recurring work {w['ref']}: {body.title}"[:300],
                    what=body.brief[:20000],
                    why="Recurring work needs approval once, with an escrow (§1.4).",
                    work_id=w["id"],
                    risk="low",
                    reversible=True,
                    payload={
                        "work_id": str(w["id"]),
                        "escrow": body.escrow.model_dump(mode="json"),
                        "schedule": body.schedule.model_dump(mode="json"),
                    },
                ),
                thread_code=ctx.who.code,
            )
            decision_ref = d["ref"]
        await ctx.audit(
            tx,
            company_id=company.id,
            action="work.create",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"{body.kind} for {w['a_code']}" + (" (cross-company)" if cross else ""),
        )
        result = WorkCreated(work=W.render(w), decision=decision_ref)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    if decision_ref:
        await workflows_client.decision_created(ctx.hub, decision_ref)
    return result


# --------------------------------------------------------------- decisions --
@router.post("/decisions", response_model=D.Decision, status_code=201, responses=E)
async def propose_decision(
    body: D.DecisionIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """An agent proposes a decision for its own company (hire, recurring
    approval, deploy, A3 action, proposal, evaluation, ...). It lands in the
    owner's decision cartable with a 🟡 notification. Requires `Idempotency-Key`."""
    if ctx.who.kind != "agent":
        raise ApiError(403, "policy_denied", "agents only")
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    async with ctx.tx() as tx:
        # The key first: a retried request gets the answer it already got.
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        # Hiring starts with the owner (§18.11): a hire while closed is refused
        # before anything else; OPA gets the state too (a second, fail-closed
        # layer), and D.propose reads it again FOR SHARE (a close waits).
        hiring_state = await hiring.state(tx)
        if body.kind == "hire" and hiring_state != "open":
            raise ApiError(403, "hiring_closed")
        payload = D.validate_payload(body.kind, body.payload)  # 422 before the policy
        scope = payload.get("scope") if body.kind == "budget_change" else None
        await allow(
            ctx,
            "decision.propose",
            {"company": ctx.who.company, "kind": body.kind, "scope": scope, "hiring": hiring_state},
        )
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        d = await D.propose(
            tx,
            ctx.who,
            company_id=ctx.who.company_id,
            company_code=ctx.who.company,
            body=body,
            thread_code=ctx.who.code
            if await tx.scalar("SELECT 1 FROM msg.threads WHERE code = :c", c=ctx.who.code)
            else None,
            charters=ctx.hub.charters,
            company_kind=(await ctx.hub.companies.by_id(ctx.who.company_id)).kind,
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,
            action="decision.propose",
            action_class="A1",
            target_kind="decision",
            target_ref=d["ref"],
            summary=f"{body.kind}, risk {body.risk}",
        )
        result = D.render(d)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    await workflows_client.decision_created(ctx.hub, result.ref)
    return result


async def _agent_decide(
    ctx: Ctx,
    request: Request,
    ref: str,
    verdict: Literal["approved", "rejected"],
    body: AgentDecide,
) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        d = await D.load(tx, ref, lock=True)
        quota_ok = await D.within_quota(tx, d)
        await allow(
            ctx,
            "decision.approve",
            {k: v for k, v in D.opa_input(ctx.who, d, quota_ok).items() if k != "principal"},
        )
        await ctx.ensure_unlocked(tx, d["company_id"])
        out = await D.decide(tx, ctx.who, d, verdict, note=body.note, reason_code=body.reason_code)
        await ctx.audit(
            tx,
            company_id=d["company_id"],
            action=f"decision.{'approve' if verdict == 'approved' else 'reject'}",
            action_class=d["action_class"],
            target_kind="decision",
            target_ref=ref,
            summary=f"{d['kind']} -> {verdict} by {ctx.who.code}",
        )
        result = D.render(out)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workflows_client.decision_decided(ctx.hub, ref)
    return result


@router.post("/decisions/{ref}/approve", response_model=D.Decision, responses=E)
async def agent_approve_decision(
    ref: str, body: AgentDecide, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """A CEO approves within its authority (OPA hq.decisions): recurring work of
    its own company inside the company's monthly budget. Requires `Idempotency-Key`."""
    return await _agent_decide(ctx, request, ref, "approved", body)


@router.post("/decisions/{ref}/reject", response_model=D.Decision, responses=E)
async def agent_reject_decision(
    ref: str, body: AgentDecide, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """Same authority as approve. Requires `Idempotency-Key`."""
    return await _agent_decide(ctx, request, ref, "rejected", body)


# ---------------------------------------------------------------- messages --
@router.post("/threads/{code}/messages", response_model=Message, status_code=201, responses=E)
async def agent_message(
    code: str, body: AgentMessage, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """An agent replies in a thread it belongs to. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        t = await tx.one(
            """SELECT t.code, t.kind, c.code AS company, d.code AS department, t.company_id
               FROM msg.threads t JOIN core.companies c ON c.id = t.company_id
               LEFT JOIN core.departments d ON d.id = t.department_id WHERE t.code = :c""",
            c=code,
        )
        await allow(
            ctx,
            "message.post",
            {
                "thread_code": t["code"],
                "thread_kind": t["kind"],
                "thread_company": t["company"],
                "thread_department": t["department"],
            },
        )
        await ctx.ensure_unlocked(tx, t["company_id"])
        links = body.links.model_dump(exclude_none=True) if body.links else {}
        kept: list[Citation] = []
        dropped = 0
        if body.citations:
            from hq_api.routes.agent_tools import read_tx  # the author's read scope

            async with read_tx(ctx) as rtx:
                kept, dropped = await validate_citations(rtx, body.citations)
        m = await post_message(
            ctx,
            tx,
            code,
            body.body,
            links,
            body.attachments,
            citations=kept,
            meta={"citations_dropped": dropped} if body.citations else None,
        )
        result = (
            await render_messages(tx, [await tx.one(MESSAGE_SQL + " WHERE m.id = :id", id=m["id"])])
        )[0]
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# -------------------------------------------------- activity, notifications --
@router.post("/activity", response_model=org.Employee, responses=E)
async def set_activity(body: Activity, ctx: Ctx = Depends(internal_ctx)) -> org.Employee:
    """Live activity of an employee -> `activity.changed` on the stream."""
    await allow(ctx, "activity.set", {"employee": body.employee})
    async with ctx.tx() as tx:
        emp = await tx.one(
            """SELECT e.id, e.company_id, c.code AS company
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
            c=body.employee,
        )
        await tx.exec(
            "UPDATE core.employees SET activity = :a, activity_note = :n, activity_at = now() WHERE id = :id",
            id=emp["id"],
            a=body.activity,
            n=body.note,
        )
        await ctx.audit(
            tx,
            company_id=emp["company_id"],
            action="activity.set",
            action_class="A0",
            target_kind="employee",
            target_ref=body.employee,
            summary=body.activity,
        )
        # Only the state goes on the stream; the note is read from the employee.
        await ctx.emit(
            tx, emp["company"], "activity.changed", body.employee, {"activity": body.activity}
        )
        row = await org.load_employee(tx, body.employee)
        holding = await ctx.hub.companies.holding()
        return org.render(
            row, await org.Assignments.load(tx, holding.code), [None] * 12, ctx.hub.charters
        )


@router.post("/notifications", response_model=NotificationOut, status_code=201, responses=E)
async def raise_notification(
    body: NotificationIn, ctx: Ctx = Depends(internal_ctx)
) -> NotificationOut:
    """Services and agents raise a notification; level rules, Khalvat and the CEO
    attention quota apply. An agent's 🔴 needs an incident `category` and is
    capped per company per hour; otherwise it is raised as 🟡. While its company
    is locked an agent raises only 🔴 incidents."""
    code = body.company or ctx.who.company or (await ctx.hub.companies.holding()).code
    company = await ctx.hub.companies.find(code)
    if company is None:  # an agent learns nothing of another company's code: 403 either way
        raise ApiError(
            403 if ctx.who.is_agent else 404, "policy_denied" if ctx.who.is_agent else "not_found"
        )
    if ctx.who.is_agent and company.code != ctx.who.company:
        raise ApiError(403, "policy_denied", "notification.raise_not_permitted")
    async with ctx.tx() as tx:
        level = body.level
        if not ctx.who.is_agent:
            await allow(
                ctx,
                "notification.raise",
                {
                    "company": company.code,
                    "level": level,
                    "category": body.category,
                    "company_locked": False,
                },
            )
        else:
            locked = await tx.scalar("SELECT control.lock_state(:co)", co=company.id) is not None
            if level == "urgent" and body.category is not None:
                # Count and raise under one lock per company: two agents racing for
                # the last 🔴 of the hour cannot both get it.
                await tx.exec(
                    "SELECT pg_advisory_xact_lock(:k)", k=advisory_key("urgent", company.id)
                )
                n = await notify.counts(tx, datetime.now().astimezone(), ctx.who.code, company.id)
                if n["company_urgent_hour"] >= notify.AGENT_URGENT_PER_HOUR:
                    if locked:
                        raise ApiError(
                            429,
                            "rate_limited",
                            "too many urgent notifications this hour",
                            headers={"Retry-After": str(URGENT_RETRY_AFTER_S)},
                        )
                    level = "decision"
            target = {
                "company": company.code,
                "level": level,
                "category": body.category,
                "company_locked": locked,
            }
            verdict = await ctx.hub.policy.query(
                "internal",
                {"principal": ctx.who.opa(), "op": "notification.raise", "target": target},
            )
            if (
                not verdict.allow
                and level == "urgent"
                and "urgent_needs_incident" in verdict.reasons
                and not locked
            ):
                level = "decision"  # not an incident: the owner sees it, without the alarm
                target["level"] = level
            await allow(
                ctx,
                "notification.raise",
                target,
                incident=level == "urgent" and body.category is not None,
            )
        n = await notify.raise_notification(
            tx,
            company_id=company.id,
            company_code=company.code,
            level=level,
            title_fa=body.title_fa,
            body_fa=body.body_fa,
            link_kind=body.link_kind,
            link_ref=body.link_ref,
            source_kind=ctx.who.kind,
            source_code=ctx.who.code,
            choices=body.choices,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="notification.raise",
            action_class="A1",
            target_kind="notification",
            target_ref=str(n["id"]),
            summary=level if level == body.level else f"{body.level} -> {level}",
        )
    return NotificationOut(id=n["id"], level=n["level"], state=n["state"])


# ----------------------------------------------------------------- control --
@router.post("/control/kill-switch", response_model=control.ControlState, responses=E)
async def agent_kill_switch(
    body: KillSwitchIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """A CEO engages its own company's switch, and releases only a switch that
    an agent of its own company engaged (an owner's switch: owner + step-up).
    Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        company = await control.resolve_scope(tx, body.scope)
        current = await control.current_switch(tx, company["id"], lock=True)
        await allow(
            ctx, "kill_switch.set", {"scope": body.scope, "state": body.state, "current": current}
        )
        changed = await control.set_kill_switch(tx, ctx.who, company, body.state, body.reason)
        await ctx.audit(
            tx,
            company_id=company["id"],
            action=f"kill_switch.{'engage' if body.state == 'engaged' else 'release'}",
            action_class="A2",
            target_kind="kill_switch",
            target_ref=body.scope,
            summary=("changed" if changed else "unchanged") + f" by {ctx.who.code}",
        )
        result = await control.state(tx)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workshop_service.paused(ctx.hub)
    return result


@router.post("/control/deploy-freeze", response_model=control.ControlState, responses=E)
async def agent_deploy_freeze(
    body: FreezeIn, ctx: Ctx = Depends(internal_ctx)
) -> control.ControlState:
    """Services (the deploy pipeline) or a CEO for its own company (§1.5 #5). A past
    `until` lifts only the freezes the caller may lift: the pipeline's by the
    pipeline, a CEO's own by that CEO; the owner's only by the owner."""
    async with ctx.tx() as tx:
        company = await control.resolve_scope(tx, f"company:{body.company}")
        lift = not await tx.scalar("SELECT :u > now()", u=body.until)
        if not lift:
            await allow(
                ctx, "deploy_freeze.set", {"company": body.company, "lift": False, "freeze": None}
            )
            await control.add_deploy_freeze(tx, ctx.who, company, body.until, body.reason)
            summary = "active"
        elif not (active := await control.active_freezes(tx, company["id"])):
            # Nothing is frozen: lifting again is a no-op for whoever may set a freeze.
            await allow(
                ctx, "deploy_freeze.set", {"company": body.company, "lift": False, "freeze": None}
            )
            summary = "nothing to lift"
        else:
            mine = []
            for f in active:
                freeze = {
                    k: f[k] for k in ("created_by_kind", "created_by_code", "created_by_company")
                }
                verdict = await ctx.hub.policy.query(
                    "internal",
                    {
                        "principal": ctx.who.opa(),
                        "op": "deploy_freeze.set",
                        "target": {"company": body.company, "lift": True, "freeze": freeze},
                    },
                )
                if "policy_unavailable" in verdict.reasons:
                    raise ApiError(
                        503, "policy_unavailable", "policy service unavailable (fail-closed)"
                    )
                if verdict.allow:
                    mine.append(f["id"])
            if not mine:
                raise ApiError(403, "policy_denied", "lifted_only_by_setter_authority")
            if ctx.who.is_agent:
                await action_gate(ctx.hub, ctx.who, "deploy_freeze.set", "A2", escrow_classes=[])
            await control.lift_deploy_freezes(tx, ctx.who, company, mine)
            summary = f"lifted {len(mine)}"
        await ctx.audit(
            tx,
            company_id=company["id"],
            action="deploy_freeze.set",
            action_class="A2",
            target_kind="company",
            target_ref=body.company,
            summary=summary,
        )
        result = await control.state(tx)
    await workshop_service.paused(ctx.hub)  # the paused sessions stop on their runtime too
    return result


# ------------------------------------------------------------ context, files --
@router.get("/context/{employee}", response_model=ContextOut, responses=E)
async def run_context(employee: str, ctx: Ctx = Depends(internal_ctx)) -> ContextOut:
    """What the runtime needs for one step: the employee, its open work with
    budget left and escrow, its company's lock state and the owner's presence."""
    await allow(ctx, "context.read", {"employee": employee})
    async with ctx.tx() as tx:
        row = await org.load_employee(tx, employee)
        holding = await ctx.hub.companies.holding()
        emp = org.render(
            row, await org.Assignments.load(tx, holding.code), [None] * 12, ctx.hub.charters
        )
        lock = await tx.scalar("SELECT control.lock_state(:co)", co=row["company_id"])
        presence = await tx.one("SELECT khalvat, since, until FROM owner.presence WHERE id = 1")
        work = await tx.all(
            W.WORK_SQL
            + " WHERE w.assignee_id = :e AND w.status IN ('queued', 'in_progress', 'waiting') "
            "ORDER BY w.priority, w.due_at NULLS LAST, w.created_at LIMIT 50",
            e=row["id"],
        )
    return ContextOut(
        employee=emp,
        company={"code": row["company"], "locked": lock},
        owner={
            "khalvat": presence["khalvat"],
            "since": presence["since"],
            "until": presence["until"],
        },
        open_work=[W.render(w) for w in work],
    )


@router.post(
    "/files",
    response_model=FileRef,
    status_code=201,
    responses=E,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_file(
    request: Request,
    name: str = Query(min_length=1, max_length=255),
    ctx: Ctx = Depends(internal_ctx),
) -> FileRef:
    """Raw body upload (`Content-Type` = the file's media type) for the agent's
    own company; returns a FileRef to attach to a deliverable or message."""
    if ctx.who.kind != "agent":
        raise ApiError(403, "policy_denied", "agents only")
    assert ctx.who.company is not None
    assert ctx.who.company_id is not None
    await allow(ctx, "file.upload", {"company": ctx.who.company})
    mime = (
        (request.headers.get("content-type") or "application/octet-stream")
        .split(";")[0]
        .strip()
        .lower()
    )
    if not MIME.match(mime):
        raise ApiError(422, "validation_failed", fields={"Content-Type": "invalid media type"})
    async with ctx.tx() as tx:  # a locked company writes nothing, not even bytes
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
    limit = ctx.hub.settings.max_file_bytes
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():  # the limit holds while reading, not after
        size += len(chunk)
        if size > limit:
            raise ApiError(413, "validation_failed", "file too large")
        chunks.append(chunk)
    data = b"".join(chunks)
    key, sha = await ctx.hub.storage.put(data)
    async with ctx.tx() as tx:
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        row = await tx.one(
            """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
                   created_by_kind, created_by_code)
               VALUES (:co, :name, :mime, :size, :sha, :key, 'agent', :by)
               RETURNING id, name, mime, size, sha256""",
            co=ctx.who.company_id,
            name=name,
            mime=mime,
            size=len(data),
            sha=sha,
            key=key,
            by=ctx.who.code,
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,
            action="file.upload",
            action_class="A1",
            target_kind="file",
            target_ref=str(row["id"]),
            summary=f"{mime}, {len(data)} bytes",
        )
    return FileRef(**row)


def advisory_key(purpose: str, company_id: UUID) -> int:
    """A stable 64-bit advisory-lock key for (purpose, company)."""
    import hashlib

    digest = hashlib.sha256(f"{purpose}:{company_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
