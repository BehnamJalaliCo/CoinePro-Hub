"""Due-date reminders (prompt 14 §6, contract §23.6, §23.12).

The daily job reads every active reminder rule: for each live record of the
rule's class whose field holds a date still ahead (or today), the nearest
lead time that has come (`at - lead_days <= today`) becomes ONE reminder,
once per (record, field, date, lead). Rule-only: no model, no outside call.
  - to the owner, channel `cartable`: a `decision`-level notification (the
    cartable reminder of §21.8, held in Khalvat, in the digest);
  - to the owner, channel `digest`: a `report` line of the digest;
  - to a role or a company's CEO: a work item, which waits (state `pending`,
    nothing woken) while the holding or that company is locked.
Marking the underlying action done (POST /archive/reminders/{id}/done) closes
it; a reminder whose date the record no longer holds is closed by the job.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.archive import vocab as V
from hq_api.archive.common import OWNER, SERVICE, J, dumps
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.errors import ApiError


async def _deliver(tx: Tx, rem: dict[str, Any], r: dict[str, Any], title: str) -> str:
    """-> the reminder's state: sent (delivered) or pending (waits for the lock)."""
    from hq_api.domain import notify
    from hq_api.domain import work as W

    to = J(rem["to_whom"])
    days = (rem["at"] - datetime.now(UTC).date()).days
    text = f"{r['ref']} · {title}: {rem['field']} در {rem['at'].isoformat()} ({days} روز دیگر)"
    if to == "owner" or to is None:
        row = await notify.raise_notification(
            tx,
            company_id=r["company_id"],
            company_code=r["scope"],
            level="decision" if rem["channel"] == "cartable" else "report",
            title_fa=f"یادآور بایگانی: {text}"[:200],
            body_fa=text[:500],
            link_kind="archive_record",
            link_ref=r["ref"],
            source_kind="service",
            source_code="archive",
        )
        await tx.exec(
            "UPDATE archive.reminders SET state = 'sent', sent_at = now(), notification_id = :n WHERE id = :id",
            id=rem["id"],
            n=row["id"],
        )
        return "sent"
    if await gate.automation_lock(tx, r["company_id"]) is not None:
        return "pending"
    if isinstance(to, dict) and to.get("company_ceo"):
        who = await tx.first(
            """SELECT e.code, e.company_id, c.code AS company FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id
               WHERE e.company_id = :co AND e.kind = 'ceo' AND e.status = 'active' LIMIT 1""",
            co=r["company_id"],
        )
    else:
        role = (to or {}).get("role") if isinstance(to, dict) else None
        who = await tx.first(
            """SELECT e.code, e.company_id, c.code AS company FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id
               WHERE e.role = :role AND e.status = 'active' AND (e.company_id = :co OR c.kind = 'holding')
               ORDER BY (e.company_id = :co) DESC LIMIT 1""",
            role=role,
            co=r["company_id"],
        )
    if who is None:
        return "pending"
    w = await W.create(
        tx,
        SERVICE,
        company_id=who["company_id"],
        company_code=who["company"],
        title=f"یادآور: {text}"[:300],
        brief=f"Archive reminder for {r['ref']}: its field `{rem['field']}` is {rem['at']}. Read it with archive.read "
        "if you hold that tool, and do what the date asks.",
        kind="one_off",
        priority="P3",
        assignee_code=who["code"],
    )
    await tx.exec(
        "UPDATE archive.reminders SET state = 'sent', sent_at = now(), work_ref = :w WHERE id = :id",
        id=rem["id"],
        w=w["ref"],
    )
    return "sent"


async def run(hub: Any, txf: Any, today: date | None = None) -> dict[str, Any]:
    """The daily reminder job (rule-only)."""
    from hq_api.archive import automations as AU
    from hq_api.archive import clearance as CL
    from hq_api.archive import records as R
    from hq_api.archive import schema as SC

    today = today or datetime.now(UTC).date()
    out = {"created": 0, "sent": 0, "pending": 0, "closed": 0}
    async with txf() as tx:
        await CL.full(tx)
        for rule in await tx.all(
            "SELECT * FROM archive.reminder_rules WHERE status = 'active' ORDER BY ref"
        ):
            leads = sorted(int(x) for x in rule["lead_days"])
            horizon = today + timedelta(days=max(leads))
            for x in await tx.all(
                """SELECT r.ref FROM archive.records r
                   WHERE r.class_key = :c AND r.state IN ('filed', 'sealed') AND r.metadata ? :f
                   ORDER BY r.ref LIMIT 5000""",
                c=rule["class_key"],
                f=rule["field"],
            ):
                r = await R.load(tx, x["ref"])
                fields = await R.class_fields(tx, r)
                f = next((y for y in fields if y["key"] == rule["field"]), None)
                at = V.field_dates(f, J(r["metadata"], {}).get(rule["field"]))
                if at is None or at < today or at > horizon:
                    continue
                lead = next((d for d in leads if at - timedelta(days=d) <= today), None)
                if lead is None:
                    continue
                rem = await tx.first(
                    """INSERT INTO archive.reminders (company_id, record_id, rule_id, field, at, lead_days, due_at,
                           channel, to_whom)
                       VALUES (:co, :r, :rule, :f, :at, :ld, :due, :ch, CAST(:to AS jsonb))
                       ON CONFLICT (record_id, field, at, lead_days) DO NOTHING RETURNING *""",
                    co=r["company_id"],
                    r=r["id"],
                    rule=rule["id"],
                    f=rule["field"],
                    at=at,
                    ld=lead,
                    due=at - timedelta(days=lead),
                    ch=rule["channel"],
                    to=dumps(J(rule["to_whom"])),
                )
                if rem is None:
                    continue
                out["created"] += 1
                state = await _deliver(tx, rem, r, r["title_fa"])
                out[state] += 1
                await events.emit(
                    tx,
                    r["scope"],
                    "reminder.due",
                    r["ref"],
                    {"field": rule["field"], "lead_days": lead, "state": state},
                )
                await AU.fire(tx, "reminder_due", r)
        # Pending ones (locked before) are delivered once they can be.
        for rem in await tx.all(
            "SELECT * FROM archive.reminders WHERE state = 'pending' AND due_at <= :d ORDER BY due_at LIMIT 500",
            d=today,
        ):
            r = await tx.first(R.RECORD_SQL + " WHERE r.id = :id", id=rem["record_id"])
            if r is None or r["state"] not in ("filed", "sealed"):
                continue
            if await _deliver(tx, rem, r, r["title_fa"]) == "sent":
                out["sent"] += 1
        # A date the record no longer holds closes its reminders.
        for rem in await tx.all(
            """SELECT m.id, m.field, m.at, r.metadata, r.class_key, r.class_version, r.state
               FROM archive.reminders m JOIN archive.records r ON r.id = m.record_id
               WHERE m.state <> 'done' LIMIT 2000"""
        ):
            meta = J(rem["metadata"], {})
            gone = rem["state"] not in ("filed", "sealed")
            if not gone and rem["class_key"]:
                cls = await SC.class_at(tx, rem["class_key"], rem["class_version"])
                f = next((y for y in cls["fields"] if y["key"] == rem["field"]), None)
                gone = V.field_dates(f, meta.get(rem["field"])) != rem["at"]
            if gone:
                await tx.exec(
                    "UPDATE archive.reminders SET state = 'done', done_at = now(), done_by = 'archive' WHERE id = :id",
                    id=rem["id"],
                )
                out["closed"] += 1
    return out


async def due_list(
    tx: Tx, today: date | None = None, *, scope: str | None = None
) -> list[dict[str, Any]]:
    """DueReminder rows (§23.12) the reader may see (RLS through the record)."""
    today = today or datetime.now(UTC).date()
    rows = await tx.all(
        """SELECT m.*, r.ref AS record, r.title_fa, co.code AS scope, r.class_key, x.ref AS rule
           FROM archive.reminders m JOIN archive.records r ON r.id = m.record_id
           JOIN core.companies co ON co.id = r.company_id
           LEFT JOIN archive.reminder_rules x ON x.id = m.rule_id
           WHERE m.state <> 'done' AND (CAST(:s AS text) IS NULL OR co.code = :s)
           ORDER BY m.at, m.lead_days DESC LIMIT 500""",
        s=scope,
    )
    return [
        {
            "id": x["id"],
            "record": x["record"],
            "title_fa": x["title_fa"],
            "scope": x["scope"],
            "class": x["class_key"],
            "field": x["field"],
            "at": x["at"],
            "lead_days": x["lead_days"],
            "days_left": (x["at"] - today).days,
            "state": x["state"],
            "rule": x["rule"],
            "to": J(x["to_whom"]),
            "channel": x["channel"],
        }
        for x in rows
    ]


async def done(tx: Tx, who: Any, rem_id: UUID) -> dict[str, Any]:
    row = await tx.first(
        """SELECT m.*, r.ref, r.company_id AS rco FROM archive.reminders m
           JOIN archive.records r ON r.id = m.record_id WHERE m.id = :id FOR UPDATE OF m""",
        id=rem_id,
    )
    if row is None:
        raise ApiError(404, "not_found", "no such reminder")
    if row["state"] != "done":
        await tx.exec(
            "UPDATE archive.reminders SET state = 'done', done_at = now(), done_by = :b WHERE id = :id",
            id=rem_id,
            b=(who or OWNER).code[:64],
        )
        await audit.record(
            tx,
            who or OWNER,
            company_id=row["rco"],
            action="archive.reminder_done",
            action_class="A1",
            target_kind="archive_record",
            target_ref=row["ref"],
            summary=f"{row['field']} {row['at']}",
        )
    return {"id": rem_id, "state": "done"}
