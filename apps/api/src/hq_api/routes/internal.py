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
from hq_api.domain import control, notify, org
from hq_api.domain import decisions as D
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.routes.messages import MESSAGE_SQL, Links, Message, post_message, render_messages
from hq_api.schemas import EMPLOYEE_CODE, Evidence, FileRef, Model

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
async def allow(ctx: Ctx, op: str, target: dict[str, Any]) -> None:
    await ctx.hub.policy.require(
        "internal", {"principal": ctx.who.opa(), "op": op, "target": target}
    )


async def work_for(ctx: Ctx, tx: Tx, id: UUID, op: str) -> dict[str, Any]:
    w = await W.load(tx, id, lock=True)
    await allow(ctx, op, {"assignee": w["a_code"], "company": w["company"]})
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
        if "label_fa" not in pw and pw.get("model"):
            pw["label_fa"] = f"انجام‌شده با {pw['model']}"
        u = body.usage
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
    company = await ctx.hub.companies.by_code(company_code)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        cross = company.id != ctx.who.company_id
        if cross:
            await tx.rescope([ctx.who.company_id, company.id])
        to_role, to_dept = "ceo", body.department
        if body.to:
            t = await tx.one(
                """SELECT e.kind, d.code AS department, e.company_id FROM core.employees e
                   LEFT JOIN core.departments d ON d.id = e.department_id WHERE e.code = :c""",
                c=body.to,
            )
            to_role, to_dept = t["kind"], t["department"]
        elif body.department:
            to_role = "manager"
        await allow(
            ctx,
            "work.create",
            {"company": company.code, "to_role": to_role, "to_department": to_dept},
        )
        assert ctx.who.company_id is not None
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        if body.requested_by_work_id is not None and not await tx.scalar(
            "SELECT 1 FROM work.work WHERE id = :id AND company_id = :co",
            id=body.requested_by_work_id,
            co=ctx.who.company_id,
        ):
            raise ApiError(
                422, "validation_failed", fields={"requested_by_work_id": "unknown work of yours"}
            )
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
            budget=body.budget,
            escrow=body.escrow,
            schedule=body.schedule,
            requested_by_work_id=body.requested_by_work_id,
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
    await allow(ctx, "decision.propose", {"company": ctx.who.company, "kind": body.kind})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
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
        m = await post_message(ctx, tx, code, body.body, links, body.attachments)
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
        return org.render(row, await org.Assignments.load(tx, holding.code), [None] * 12)


@router.post("/notifications", response_model=NotificationOut, status_code=201, responses=E)
async def raise_notification(
    body: NotificationIn, ctx: Ctx = Depends(internal_ctx)
) -> NotificationOut:
    """Services and agents raise a notification; level rules, Khalvat and the
    CEO attention quota apply."""
    code = body.company or ctx.who.company or (await ctx.hub.companies.holding()).code
    company = await ctx.hub.companies.by_code(code)
    await allow(ctx, "notification.raise", {"company": company.code})
    async with ctx.tx() as tx:
        n = await notify.raise_notification(
            tx,
            company_id=company.id,
            company_code=company.code,
            level=body.level,
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
            summary=body.level,
        )
    return NotificationOut(id=n["id"], level=n["level"], state=n["state"])


# ----------------------------------------------------------------- control --
@router.post("/control/kill-switch", response_model=control.ControlState, responses=E)
async def agent_kill_switch(
    body: KillSwitchIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """A CEO engages or releases the switch of its own company only.
    Requires `Idempotency-Key`."""
    await allow(ctx, "kill_switch.set", {"scope": body.scope})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        company = await control.resolve_scope(tx, body.scope)
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
    return result


@router.post("/control/deploy-freeze", response_model=control.ControlState, responses=E)
async def agent_deploy_freeze(
    body: FreezeIn, ctx: Ctx = Depends(internal_ctx)
) -> control.ControlState:
    """Services (deploy pipeline) or a CEO for its own company (§1.5 #5)."""
    await allow(ctx, "deploy_freeze.set", {"company": body.company})
    async with ctx.tx() as tx:
        company = await control.resolve_scope(tx, f"company:{body.company}")
        r = await control.set_deploy_freeze(tx, ctx.who, company, body.until, body.reason)
        await ctx.audit(
            tx,
            company_id=company["id"],
            action="deploy_freeze.set",
            action_class="A2",
            target_kind="company",
            target_ref=body.company,
            summary="active" if r["active"] else "lifted",
        )
        return await control.state(tx)


# ------------------------------------------------------------ context, files --
@router.get("/context/{employee}", response_model=ContextOut, responses=E)
async def run_context(employee: str, ctx: Ctx = Depends(internal_ctx)) -> ContextOut:
    """What the runtime needs for one step: the employee, its open work with
    budget left and escrow, its company's lock state and the owner's presence."""
    await allow(ctx, "context.read", {"employee": employee})
    async with ctx.tx() as tx:
        row = await org.load_employee(tx, employee)
        holding = await ctx.hub.companies.holding()
        emp = org.render(row, await org.Assignments.load(tx, holding.code), [None] * 12)
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
    data = await request.body()
    if len(data) > ctx.hub.settings.max_file_bytes:
        raise ApiError(413, "validation_failed", "file too large")
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


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
