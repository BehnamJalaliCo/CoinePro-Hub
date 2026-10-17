"""Recurring work (§1.4 "دائمی"): approved once with an escrow (پاکت اختیار),
then every occurrence becomes a run work item with the escrow's per-run
budget, without asking again, until the escrow expires.

Runs are root work items linked by recurrence_of + occurrence_at (unique),
so creating the same occurrence twice is a no-op whoever tries first: the
activation (first run), or the Temporal Schedule's action.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import recurrence
from hq_api.principal import Principal

RUN_WINDOW = timedelta(hours=24)


async def activate(
    tx: Tx, template: dict[str, Any], approved_by: Principal, decision_id: Any = None
) -> dict[str, Any] | None:
    """Escrow and schedule become active; the first run is created now."""
    await tx.exec(
        """UPDATE work.escrows SET status = 'active', approved_by_kind = :k, approved_by_code = :c,
               decision_id = COALESCE(:d, decision_id)
           WHERE work_id = :w AND status = 'pending'""",
        w=template["id"],
        k="owner" if approved_by.is_owner else "agent",
        c=approved_by.code,
        d=decision_id,
    )
    await tx.exec(
        "UPDATE work.schedules SET status = 'active' WHERE work_id = :w AND status = 'pending'",
        w=template["id"],
    )
    if await tx.scalar("SELECT control.lock_state(:co)", co=template["company_id"]) in (
        "holding",
        "company",
    ):
        return None  # locked: the schedule brings the first run once released
    return await create_next_run(tx, template["id"], approved_by)


async def create_next_run(
    tx: Tx, template_id: Any, who: Principal, *, after: datetime | None = None
) -> dict[str, Any] | None:
    sched = await tx.first(
        """SELECT s.rrule, s.timezone, s.status, e.status AS escrow_status, e.expires_at,
                  e.token_cap_per_run
           FROM work.schedules s JOIN work.escrows e ON e.work_id = s.work_id
           WHERE s.work_id = :w""",
        w=template_id,
    )
    if sched is None or sched["status"] != "active" or sched["escrow_status"] != "active":
        return None
    rule = recurrence.parse(sched["rrule"])
    at = recurrence.next_at(rule, sched["timezone"], after)
    if at is None or at > sched["expires_at"]:
        await end(tx, template_id)
        return None
    return await create_run(tx, template_id, at, who)


async def create_run(
    tx: Tx, template_id: Any, occurrence_at: datetime, who: Principal
) -> dict[str, Any] | None:
    t = await tx.one(
        """SELECT w.*, c.code AS company, e.token_cap_per_run, e.expires_at, e.status AS escrow_status
           FROM work.work w JOIN core.companies c ON c.id = w.company_id
           JOIN work.escrows e ON e.work_id = w.id WHERE w.id = :w""",
        w=template_id,
    )
    if (
        t["escrow_status"] != "active"
        or occurrence_at > t["expires_at"]
        or t["status"] in ("cancelled", "failed")
    ):
        return None
    row = await tx.first(
        """INSERT INTO work.work (company_id, department_id, kind, title, brief, priority,
               created_by_kind, created_by_code, assignee_id, depth, recurrence_of, occurrence_at,
               due_at, budget_tokens)
           VALUES (:co, :d, 'one_off', :title, :brief, :prio, 'service', 'system', :a, :depth, :tpl,
                   :at, :due, :cap)
           ON CONFLICT (recurrence_of, occurrence_at) DO NOTHING
           RETURNING id, ref, occurrence_at""",
        co=t["company_id"],
        d=t["department_id"],
        title=t["title"],
        brief=t["brief"],
        prio=t["priority"],
        a=t["assignee_id"],
        depth=t["depth"],
        tpl=t["id"],
        at=occurrence_at,
        due=occurrence_at + RUN_WINDOW,
        cap=t["token_cap_per_run"],
    )
    if row is None:
        return None
    await tx.exec(
        "UPDATE work.schedules SET last_run_at = now(), next_at = :n WHERE work_id = :w",
        w=template_id,
        n=occurrence_at,
    )
    await tx.exec(
        """INSERT INTO work.work_events (work_id, company_id, kind, actor_kind, actor_code, data)
           VALUES (:w, :co, 'run_created', :ak, :ac, CAST(:data AS jsonb))""",
        w=template_id,
        co=t["company_id"],
        ak=who.kind,
        ac=who.code,
        data='{"run": "' + row["ref"] + '"}',
    )
    await events.emit(
        tx,
        t["company"],
        "work.created",
        row["ref"],
        {"recurrence_of": t["ref"], "occurrence_at": occurrence_at.isoformat()},
    )
    return row


async def end(tx: Tx, template_id: Any) -> None:
    await tx.exec(
        "UPDATE work.schedules SET status = 'ended', next_at = NULL WHERE work_id = :w AND status <> 'ended'",
        w=template_id,
    )
    await tx.exec(
        """UPDATE work.escrows SET status = 'expired'
           WHERE work_id = :w AND status = 'active' AND expires_at <= now()""",
        w=template_id,
    )


def utcnow() -> datetime:
    return datetime.now(UTC)
