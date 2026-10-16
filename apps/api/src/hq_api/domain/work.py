"""Work and delegation (contract §4, OPERATING_MODEL §1.4, §1.9).

Delegation is a database record: a child work row with depth = parent + 1
(the database caps it at 2 and checks budgets). Nobody "calls" an agent;
the runtime picks work up from these rows and the stream.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import org, recurrence
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import (
    Actor,
    Budget,
    EmployeeRef,
    Escrow,
    Evidence,
    Model,
    Schedule,
    actor,
    employee_ref,
)

OPEN = ("queued", "in_progress", "waiting")
CLOSED = ("done", "cancelled", "failed")

WORK_SQL = f"""
    SELECT w.*, c.code AS company, d.code AS department, {org.ref_cols("a", "a_")},
           es.allowed_action_classes AS es_classes, es.token_cap_per_run AS es_token_cap,
           es.usd_cap_per_month AS es_usd_cap, es.expires_at AS es_expires_at, es.status AS es_status,
           es.approved_by_kind AS es_by_kind, es.approved_by_code AS es_by_code,
           (SELECT ref FROM cartable.decisions WHERE id = es.decision_id) AS es_decision,
           sc.rrule AS sc_rrule, sc.timezone AS sc_timezone, sc.next_at AS sc_next_at,
           sc.status AS sc_status,
           ARRAY(SELECT dl.id FROM cartable.deliverables dl WHERE dl.work_id = w.id ORDER BY dl.created_at)
               AS deliverable_ids
    FROM work.work w
    JOIN core.companies c ON c.id = w.company_id
    LEFT JOIN core.departments d ON d.id = w.department_id
    LEFT JOIN core.employees a ON a.id = w.assignee_id
    LEFT JOIN work.escrows es ON es.work_id = w.id
    LEFT JOIN work.schedules sc ON sc.work_id = w.id
"""  # noqa: S608 - composed from module constants; values are bound


class Work(BaseModel):
    id: UUID
    ref: str
    company: str
    department: str | None
    kind: str
    title: str
    brief: str
    priority: str
    status: str
    created_by: Actor
    assignee: EmployeeRef | None
    parent_id: UUID | None
    root_id: UUID
    depth: int
    requested_by_work_id: UUID | None
    due_at: datetime | None
    overdue: bool
    escalation_level: int
    budget: Budget
    escrow: Escrow | None
    schedule: Schedule | None
    deliverable_ids: list[UUID]
    evidence: list[dict[str, Any]]
    progress_note: str | None
    progress_pct: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class EscrowIn(Model):
    allowed_action_classes: list[str] = Field(default_factory=lambda: ["A0", "A1"], max_length=3)
    token_cap_per_run: int = Field(gt=0, le=10_000_000)
    usd_cap_per_month: Decimal = Field(ge=0, le=1_000_000, max_digits=14, decimal_places=6)
    expires_at: datetime


class ScheduleIn(Model):
    rrule: str = Field(min_length=5, max_length=500)
    timezone: str = Field(default="Asia/Tehran", max_length=64)


class BudgetIn(Model):
    tokens: int | None = Field(default=None, ge=0, le=10_000_000_000)
    usd: Decimal | None = Field(default=None, ge=0, le=1_000_000, max_digits=14, decimal_places=6)


def render(r: dict[str, Any]) -> Work:
    now = datetime.now(UTC)
    escrow = None
    if r.get("es_status"):
        escrow = Escrow(
            allowed_action_classes=list(r["es_classes"]),
            token_cap_per_run=r["es_token_cap"],
            usd_cap_per_month=r["es_usd_cap"],
            expires_at=r["es_expires_at"],
            status=r["es_status"],
            approved_by=actor(r["es_by_kind"], r["es_by_code"]),
            decision=r["es_decision"],
        )
    schedule = None
    if r.get("sc_rrule"):
        schedule = Schedule(
            rrule=r["sc_rrule"],
            timezone=r["sc_timezone"],
            next_at=r["sc_next_at"],
            status=r["sc_status"],
        )
    creator = actor(r["created_by_kind"], r["created_by_code"])
    assert creator is not None
    return Work(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        department=r["department"],
        kind=r["kind"],
        title=r["title"],
        brief=r["brief"],
        priority=r["priority"],
        status=r["status"],
        created_by=creator,
        assignee=employee_ref(r, "a_"),
        parent_id=r["parent_id"],
        root_id=r["root_id"],
        depth=r["depth"],
        requested_by_work_id=r["requested_by_work_id"],
        due_at=r["due_at"],
        overdue=bool(r["due_at"] and r["due_at"] < now and r["status"] in OPEN),
        escalation_level=r["escalation_level"],
        budget=Budget(
            tokens=r["budget_tokens"],
            usd=r["budget_usd"],
            tokens_used=r["tokens_used"],
            usd_used=r["usd_used"],
        ),
        escrow=escrow,
        schedule=schedule,
        deliverable_ids=list(r["deliverable_ids"] or []),
        evidence=list(r["evidence"] or []),
        progress_note=r["progress_note"],
        progress_pct=r["progress_pct"],
        version=r["version"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def load(tx: Tx, work_id: UUID | str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec(
            "SELECT 1 FROM work.work WHERE id = CAST(:id AS uuid) FOR UPDATE", id=str(work_id)
        )
    return await tx.one(WORK_SQL + " WHERE w.id = CAST(:id AS uuid)", id=str(work_id))


async def load_ref(tx: Tx, ref: str) -> dict[str, Any]:
    return await tx.one(WORK_SQL + " WHERE w.ref = :ref", ref=ref)


async def event(
    tx: Tx, w: dict[str, Any], kind: str, who: Principal, data: dict[str, Any] | None = None
) -> None:
    await tx.exec(
        """INSERT INTO work.work_events (work_id, company_id, kind, actor_kind, actor_code, data)
           VALUES (:w, :co, :kind, :ak, :ac, CAST(:data AS jsonb))""",
        w=w["id"],
        co=w["company_id"],
        kind=kind,
        ak=who.kind,
        ac=who.code,
        data=json.dumps(data or {}, default=str, ensure_ascii=False),
    )


async def employee(tx: Tx, code: str) -> dict[str, Any]:
    row = await tx.first(
        """SELECT e.id, e.code, e.kind, e.status, e.company_id, e.department_id, d.code AS department
           FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
           WHERE e.code = :c""",
        c=code,
    )
    if row is None:
        raise ApiError(422, "validation_failed", fields={"assignee": f"unknown employee {code}"})
    if row["status"] != "active":
        raise ApiError(422, "validation_failed", fields={"assignee": f"{code} is {row['status']}"})
    return row


async def create(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    company_code: str,
    title: str,
    brief: str,
    kind: str,
    priority: str,
    department_code: str | None = None,
    assignee_code: str | None = None,
    due_at: datetime | None = None,
    budget: BudgetIn | None = None,
    escrow: EscrowIn | None = None,
    schedule: ScheduleIn | None = None,
    parent: dict[str, Any] | None = None,
    requested_by_work_id: UUID | None = None,
) -> dict[str, Any]:
    """A root work item (or a child when `parent` is given). Without an
    assignee it goes to the department's manager, else to the CEO."""
    dept_id = None
    if department_code:
        dept_id = await tx.scalar(
            "SELECT id FROM core.departments WHERE company_id = :co AND code = :d",
            co=company_id,
            d=department_code,
        )
        if dept_id is None:
            raise ApiError(
                422, "validation_failed", fields={"department": "unknown in this company"}
            )
    target: dict[str, Any] | None
    if assignee_code:
        target = await employee(tx, assignee_code)
        if target["company_id"] != company_id:
            raise ApiError(
                422, "validation_failed", fields={"assignee": "belongs to another company"}
            )
    elif dept_id is not None:
        target = await tx.first(
            """SELECT e.id, e.code, e.kind, e.status, e.company_id, e.department_id FROM core.employees e
               WHERE e.department_id = :d AND e.kind IN ('manager', 'inspector') AND e.status = 'active'""",
            d=dept_id,
        )
    else:
        target = await tx.first(
            """SELECT id, code, kind, status, company_id, department_id FROM core.employees
               WHERE company_id = :co AND kind = 'ceo' AND status = 'active'""",
            co=company_id,
        )
    if target is None:
        raise ApiError(422, "validation_failed", fields={"assignee": "nobody to receive this work"})
    if dept_id is None:
        dept_id = target["department_id"]
    if kind == "recurring" and (escrow is None or schedule is None):
        raise ApiError(
            422, "validation_failed", fields={"escrow": "recurring work needs escrow and schedule"}
        )
    rule = recurrence.parse(schedule.rrule) if schedule else None
    if schedule:
        recurrence.zone(schedule.timezone)
    if escrow:
        if not set(escrow.allowed_action_classes) <= {"A0", "A1", "A2"}:
            raise ApiError(
                422, "validation_failed", fields={"escrow.allowed_action_classes": "only A0..A2"}
            )
        if escrow.expires_at <= datetime.now(UTC):
            raise ApiError(
                422, "validation_failed", fields={"escrow.expires_at": "must be in the future"}
            )

    row = await tx.one(
        """INSERT INTO work.work (company_id, department_id, kind, title, brief, priority,
               created_by_kind, created_by_code, assignee_id, parent_id, depth, requested_by_work_id,
               due_at, budget_tokens, budget_usd)
           VALUES (:co, :dept, :kind, :title, :brief, :prio, :ck, :cc, :assignee, :parent, :depth,
                   :req, :due, :bt, :bu)
           RETURNING id, ref""",
        co=company_id,
        dept=dept_id,
        kind=kind,
        title=title,
        brief=brief,
        prio=priority,
        ck=who.kind,
        cc=who.code,
        assignee=target["id"],
        parent=parent["id"] if parent else None,
        depth=org.DEPTH_OF_KIND.get(target["kind"], 2) if parent is None else 0,
        req=requested_by_work_id,
        due=due_at,
        bt=budget.tokens if budget else None,
        bu=budget.usd if budget else None,
    )
    active = who.is_owner  # owner-created recurring work is active immediately
    if escrow:
        await tx.exec(
            """INSERT INTO work.escrows (company_id, work_id, allowed_action_classes, token_cap_per_run,
                   usd_cap_per_month, expires_at, status, approved_by_kind, approved_by_code)
               VALUES (:co, :w, :cls, :cap, :usd, :exp, :st, :bk, :bc)""",
            co=company_id,
            w=row["id"],
            cls=escrow.allowed_action_classes,
            cap=escrow.token_cap_per_run,
            usd=escrow.usd_cap_per_month,
            exp=escrow.expires_at,
            st="active" if active else "pending",
            bk=who.kind if active else None,
            bc=who.code if active else None,
        )
    if schedule and rule:
        await tx.exec(
            """INSERT INTO work.schedules (company_id, work_id, rrule, timezone, next_at, status)
               VALUES (:co, :w, :rrule, :tz, :next, :st)""",
            co=company_id,
            w=row["id"],
            rrule=rule.rrule(),
            tz=schedule.timezone,
            next=recurrence.next_at(rule, schedule.timezone),
            st="active" if active else "pending",
        )
    w = await load(tx, row["id"])
    await event(tx, w, "created", who, {"assignee": target["code"]})
    await events.emit(
        tx,
        company_code,
        "work.created",
        w["ref"],
        {"assignee": target["code"], "kind": kind, "priority": priority, "depth": w["depth"]},
    )
    return w


async def delegate(
    tx: Tx,
    who: Principal,
    parent: dict[str, Any],
    *,
    to_code: str,
    title: str,
    brief: str,
    priority: str | None,
    due_at: datetime | None,
    budget: BudgetIn | None,
) -> dict[str, Any]:
    if parent["status"] in CLOSED:
        raise ApiError(409, "validation_failed", "the work is closed")
    child = await create(
        tx,
        who,
        company_id=parent["company_id"],
        company_code=parent["company"],
        title=title,
        brief=brief,
        kind="one_off",
        priority=priority or parent["priority"],
        assignee_code=to_code,
        due_at=due_at or parent["due_at"],
        budget=budget,
        parent=parent,
    )
    if parent["status"] in ("queued", "in_progress"):
        await tx.exec("UPDATE work.work SET status = 'waiting' WHERE id = :id", id=parent["id"])
    await event(tx, parent, "delegated", who, {"child": child["ref"], "to": to_code})
    await events.emit(
        tx,
        parent["company"],
        "work.delegated",
        parent["ref"],
        {"child": child["ref"], "to": to_code},
    )
    return child


async def set_status(tx: Tx, w: dict[str, Any], status: str, **cols: Any) -> None:
    sets = ", ".join(["status = :status", *[f"{k} = :{k}" for k in cols]])
    await tx.exec(f"UPDATE work.work SET {sets} WHERE id = :id", id=w["id"], status=status, **cols)  # noqa: S608


async def close_delivered_children(tx: Tx, w: dict[str, Any], who: Principal) -> list[str]:
    """When a parent is delivered, its delivered children are done (their
    output was consumed); evidence exists, so the database allows it."""
    rows = await tx.all(
        """UPDATE work.work SET status = 'done', closed_at = now()
           WHERE parent_id = :id AND status = 'delivered' RETURNING id, ref""",
        id=w["id"],
    )
    for r in rows:
        await events.emit(tx, w["company"], "work.completed", r["ref"], {"by": who.code})
    return [r["ref"] for r in rows]


async def add_usage(tx: Tx, w: dict[str, Any], tokens: int, usd: Decimal) -> None:
    if tokens or usd:
        await tx.exec(
            "UPDATE work.work SET tokens_used = tokens_used + :t, usd_used = usd_used + :u WHERE id = :id",
            id=w["id"],
            t=tokens,
            u=usd,
        )


def evidence_json(items: list[Evidence]) -> str:
    return json.dumps([e.model_dump(exclude_none=True) for e in items], ensure_ascii=False)
