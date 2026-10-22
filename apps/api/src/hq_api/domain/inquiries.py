"""Formal inquiries (prompt 08 §3, contract §18.2): the overseer and the
advisor ask anyone, a CEO asks inside its own company; the asked one answers.

An inquiry is a row of the asked one's company plus a work item for it at P1
(above normal work), so the runtime wakes it with the question in its brief;
the answer is posted in the asker's thread (A-…, N-…, or a CEO's own thread)
with `links.inquiry`, and the work item closes with the inquiry as its
evidence. An inquiry past its due time is `late`: the owner is told once and
it counts against the asked company's compliance (protocol PR-051). An
inquiry from rank 2 (the overseer, the advisor) must be answered: its work
item cannot be declined or failed away.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import notify, org
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Evidence, Model

ASKER_KINDS = ("overseer", "advisor", "ceo")  # contract §18.2; OPA decides who asks whom
MAX_DUE_HOURS = 24 * 14
WORK_PRIORITY = "P1"  # above normal work (P3): the asked one answers first
# Threads where an agent's answer may land: the asker's own thread with the owner.
ASKER_THREADS = ("advisor", "overseer", "assistant", "ceo", "manager", "employee")

SQL = """
    SELECT q.*, c.code AS company,
           (SELECT w.ref FROM work.work w WHERE w.id = q.work_id) AS work_ref
    FROM oversight.inquiries q JOIN core.companies c ON c.id = q.company_id
"""


class InquiryIn(Model):
    to: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$")
    question_md: str = Field(min_length=1, max_length=20000)
    due_in_hours: int = Field(ge=1, le=MAX_DUE_HOURS)


class AnswerIn(Model):
    answer_md: str = Field(min_length=1, max_length=50000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)


class Inquiry(BaseModel):
    id: UUID
    ref: str
    from_: Actor = Field(alias="from")
    to: Actor
    company: str
    question_md: str
    due_at: datetime
    status: Literal["open", "answered", "late", "withdrawn"]
    answer_md: str | None
    evidence: list[dict[str, Any]]
    answered_at: datetime | None
    thread_ref: str
    answer_message_ref: str | None
    work_ref: str | None
    created_at: datetime

    model_config = {"populate_by_name": True}


def render(r: dict[str, Any]) -> Inquiry:
    return Inquiry(
        id=r["id"],
        ref=r["ref"],
        **{"from": Actor(kind=r["from_kind"], code=r["from_code"])},
        to=Actor(kind="agent", code=r["to_code"]),
        company=r["company"],
        question_md=r["question_md"],
        due_at=r["due_at"],
        status=r["status"],
        answer_md=r["answer_md"],
        evidence=list(r["evidence"] or []),
        answered_at=r["answered_at"],
        thread_ref=r["thread_code"],
        answer_message_ref=r["answer_message_ref"],
        work_ref=r["work_ref"],
        created_at=r["created_at"],
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(SQL + " WHERE q.ref = :r" + (" FOR UPDATE OF q" if lock else ""), r=ref)
    if row is None:
        raise ApiError(404, "not_found")
    return row


async def asker_thread(tx: Tx, who: Principal) -> str:
    """The asker's own thread with the owner, where the answer will appear."""
    code: str | None = await tx.scalar(
        """SELECT code FROM msg.threads WHERE employee_id = :e AND kind = ANY(:kinds)
           ORDER BY kind IN ('advisor', 'overseer', 'assistant') DESC, created_at LIMIT 1""",
        e=who.employee_id,
        kinds=list(ASKER_THREADS),
    )
    if code is None:
        raise ApiError(
            422, "validation_failed", fields={"to": "the asker has no thread for the answer"}
        )
    return code


async def ask(
    tx: Tx, who: Principal, target: dict[str, Any], body: InquiryIn, thread_code: str
) -> dict[str, Any]:
    """The inquiry and its P1 work item for the asked one (tx scoped to both
    companies). `target` is the asked employee's row."""
    if target["status"] != "active":
        raise ApiError(422, "validation_failed", fields={"to": "not an active employee"})
    if target["code"] == who.code:
        raise ApiError(422, "validation_failed", fields={"to": "not yourself"})
    due = datetime.now(UTC) + timedelta(hours=body.due_in_hours)
    q = await tx.one(
        """INSERT INTO oversight.inquiries (company_id, from_kind, from_code, from_company_id, from_rank,
               to_employee_id, to_code, question_md, due_at, thread_code, run_id)
           VALUES (:co, :fk, :fc, :fco, :rank, :to, :tc, :q, :due, :th, CAST(:run AS uuid))
           RETURNING id, ref""",
        co=target["company_id"],
        fk=who.kind,
        fc=who.code,
        fco=who.company_id,
        rank=org.rank(who.role, who.charter) if who.is_agent else 1,
        to=target["id"],
        tc=target["code"],
        q=body.question_md,
        due=due,
        th=thread_code,
        run=who.run_id,
    )
    company_code: str = await tx.scalar(
        "SELECT code FROM core.companies WHERE id = :id", id=target["company_id"]
    )
    must = (org.rank(who.role, who.charter) or 9) <= 2
    w = await W.create(
        tx,
        who,
        company_id=target["company_id"],
        company_code=company_code,
        title=f"پاسخ پرسش رسمی {q['ref']} از {who.code}"[:300],
        brief=(
            f"Formal inquiry {q['ref']} from {who.code}"
            f"{' (rank 2: it must be answered)' if must else ''}, due {due.isoformat(timespec='minutes')}.\n"
            f'Answer it with the tool `inquiry.answer` {{ref: "{q["ref"]}", answer_md, evidence}}: '
            "the answer goes to the asker's thread; cite your evidence.\n\n"
            f"Question:\n{body.question_md}"
        )[:50000],
        kind="one_off",
        priority=WORK_PRIORITY,
        assignee_code=target["code"],
    )
    await W.event(tx, w, "inquiry", who, {"inquiry": q["ref"]})
    await tx.exec(
        "UPDATE oversight.inquiries SET work_id = :w, updated_at = now() WHERE id = :id",
        w=w["id"],
        id=q["id"],
    )
    return await load(tx, q["ref"])


async def answer(tx: Tx, who: Principal, q: dict[str, Any], body: AnswerIn) -> dict[str, Any]:
    """The asked one's answer: posted in the asker's thread (tx scoped to the
    thread's company too), the inquiry answered, its work item done."""
    if q["to_code"] != who.code:
        raise ApiError(403, "policy_denied", "only the asked one answers")
    if q["status"] not in ("open", "late"):
        raise ApiError(409, "validation_failed", f"{q['ref']} is {q['status']}")
    evidence = [e.model_dump(exclude_none=True) for e in body.evidence]
    t = await tx.one("SELECT id, company_id FROM msg.threads WHERE code = :c", c=q["thread_code"])
    text = f"پاسخ پرسش رسمی {q['ref']} ({who.code}):\n\n{body.answer_md}"
    if evidence:
        text += "\n\nشاهدها: " + "، ".join(
            f"{e['kind']}:{e['ref']}" + (f" ({e['note']})" if e.get("note") else "")
            for e in evidence
        )
    m = await tx.one(
        """SELECT ref FROM msg.post(:t, 'agent', :a, :body, CAST(:links AS jsonb), NULL, 'text')""",
        t=t["id"],
        a=who.code,
        body=text[:100000],
        links=json.dumps({"inquiry": q["ref"]}),
    )
    await tx.exec(
        """UPDATE oversight.inquiries SET status = 'answered', answer_md = :a, evidence = CAST(:ev AS jsonb),
               answered_at = now(), answer_message_ref = :m, updated_at = now()
           WHERE id = :id""",
        a=body.answer_md,
        ev=json.dumps(evidence, ensure_ascii=False),
        m=m["ref"],
        id=q["id"],
    )
    if q["work_id"] is not None:
        w = await W.load(tx, q["work_id"], lock=True)
        if w["status"] not in W.CLOSED:
            await tx.exec(
                """UPDATE work.work SET status = 'done', closed_at = now(),
                       evidence = evidence || CAST(:ev AS jsonb) WHERE id = :id""",
                ev=json.dumps([{"kind": "link", "ref": q["ref"], "note": "inquiry answered"}]),
                id=w["id"],
            )
            await W.event(tx, w, "completed", who, {"inquiry": q["ref"]})
    thread_company: str = await tx.scalar(
        "SELECT code FROM core.companies WHERE id = :id", id=t["company_id"]
    )
    await events.emit(
        tx,
        thread_company,
        "message.created",
        m["ref"],
        {"thread": q["thread_code"], "author": who.code, "links": {"inquiry": q["ref"]}},
    )
    await events.emit(
        tx,
        q["company"],
        "inquiry.answered",
        q["ref"],
        {
            "from": q["from_code"],
            "to": who.code,
            "message": m["ref"],
            "late": q["status"] == "late",
        },
    )
    return await load(tx, q["ref"])


async def must_be_answered(tx: Tx, work_id: UUID) -> str | None:
    """The ref of an open inquiry from rank 2 behind this work item, if any."""
    ref: str | None = await tx.scalar(
        """SELECT ref FROM oversight.inquiries WHERE work_id = :w AND status IN ('open', 'late')
             AND from_rank <= 2 LIMIT 1""",
        w=work_id,
    )
    return ref


async def mark_late(tx: Tx) -> list[dict[str, Any]]:
    """Open inquiries past their due time: `late` (once), the owner told
    (🟡 decision level, in the asked company), `inquiry.late` on the stream.
    Returns the notifications to push."""
    rows = await tx.all(
        """UPDATE oversight.inquiries q SET status = 'late', late_at = now(), updated_at = now()
           FROM core.companies c
           WHERE c.id = q.company_id AND q.status = 'open' AND q.due_at < now()
           RETURNING q.ref, q.company_id, c.code AS company, q.from_code, q.to_code, q.due_at"""
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            await notify.raise_notification(
                tx,
                company_id=r["company_id"],
                company_code=r["company"],
                level="decision",
                title_fa=f"پرسش رسمی {r['ref']} بی‌پاسخ ماند ({r['to_code']})",
                body_fa=f"پرسنده: {r['from_code']} · مهلت گذشت",
                link_kind="inquiry",
                link_ref=r["ref"],
            )
        )
        await events.emit(
            tx, r["company"], "inquiry.late", r["ref"], {"from": r["from_code"], "to": r["to_code"]}
        )
    return out
