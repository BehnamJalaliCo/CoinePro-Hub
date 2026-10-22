"""The personal assistant's errands (prompt 08 §5, contract §18.3).

Thread `P` is the conversation: every owner message there opens an errand
(E-…) unless it continues an open one (`links.errand`); the message carries
`links.errand` and wakes the assistant. The assistant records its steps
(`errand.step`), finishes with the result (`errand.finish`; the result is
posted in P), and puts dated reminders in the owner's planner
(`planner.add`). An external commitment (pay, buy, book, sign up, send, a
security change) is a decision of kind `errand_action` (A3): the errand waits
for the owner, and even an approved one is never carried out by an agent
(the gateway refuses commitments); the assistant prepares the last step and
the owner takes it. Usage comes from the token ledger (the errand's runs).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import FileRef, Model

THREAD = "P"
OPEN = ("queued", "working", "waiting_owner")
STEP_KINDS = ("search", "read", "browse", "request", "draft", "note", "proposal")
MAX_STEPS = 200
ERRAND_REF = r"^E-[0-9]{4,}$"
SQL = """
    SELECT e.*, d.ref AS decision_ref FROM owner.errands e
    LEFT JOIN cartable.decisions d ON d.id = e.decision_id
"""


class ErrandIn(Model):
    brief_md: str = Field(min_length=1, max_length=20000)
    source: Literal["voice", "text"] = "text"
    file_ids: list[UUID] = Field(default_factory=list, max_length=10)
    due_at: datetime | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)


class StepIn(Model):
    kind: Literal["search", "read", "browse", "request", "draft", "note", "proposal"]
    summary_fa: str = Field(min_length=1, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)


class FinishIn(Model):
    result_md: str = Field(min_length=1, max_length=50000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=20)


class PlannerIn(Model):
    title_fa: str = Field(min_length=1, max_length=200)
    at: datetime
    note: str | None = Field(default=None, max_length=2000)
    errand: str | None = Field(default=None, pattern=ERRAND_REF)


class Step(BaseModel):
    at: datetime
    kind: str
    summary_fa: str
    data: dict[str, Any]


class Usage(BaseModel):
    usd: Decimal
    input_tokens: int
    output_tokens: int


class Errand(BaseModel):
    id: UUID
    ref: str
    title_fa: str
    brief_md: str
    source: str
    file_ids: list[UUID]
    due_at: datetime | None
    status: Literal["queued", "working", "waiting_owner", "done", "failed", "cancelled"]
    steps: list[Step]
    result_md: str | None
    attachments: list[FileRef]
    decision_ref: str | None
    message_ref: str | None
    usage: Usage
    created_at: datetime
    updated_at: datetime


def title_of(brief: str) -> str:
    line = next((ln.strip() for ln in brief.splitlines() if ln.strip()), brief.strip())
    return (line[:117] + "…") if len(line) > 120 else line


async def usage(tx: Tx, run_ids: list[UUID]) -> Usage:
    """From the ledger, never from the agent: every call of the errand's runs."""
    if not run_ids:
        return Usage(usd=Decimal(0), input_tokens=0, output_tokens=0)
    row = await tx.one(
        """SELECT COALESCE(sum(equiv_cost_usd), 0) AS usd,
                  COALESCE(sum(input_tokens + cache_read_tokens + cache_write_tokens), 0) AS i,
                  COALESCE(sum(output_tokens), 0) AS o
           FROM llm.calls WHERE meta->>'run_id' = ANY(:runs)""",
        runs=[str(r) for r in run_ids],
    )
    return Usage(usd=Decimal(row["usd"]), input_tokens=int(row["i"]), output_tokens=int(row["o"]))


async def render(tx: Tx, r: dict[str, Any]) -> Errand:
    refs = await F.refs(tx, list(r["attachments"] or []))
    return Errand(
        id=r["id"],
        ref=r["ref"],
        title_fa=r["title_fa"],
        brief_md=r["brief_md"],
        source=r["source"],
        file_ids=list(r["file_ids"] or []),
        due_at=r["due_at"],
        status=r["status"],
        steps=[Step.model_validate(s) for s in r["steps"] or []],
        result_md=r["result_md"],
        attachments=[refs[a] for a in r["attachments"] or [] if a in refs],
        decision_ref=r["decision_ref"],
        message_ref=r["message_ref"],
        usage=await usage(tx, list(r["run_ids"] or [])),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(SQL + " WHERE e.ref = :r" + (" FOR UPDATE OF e" if lock else ""), r=ref)
    if row is None:
        raise ApiError(404, "not_found")
    return row


async def open_errand(
    tx: Tx,
    holding_id: UUID,
    *,
    brief: str,
    source: str,
    file_ids: list[UUID],
    due_at: datetime | None,
    title: str | None,
) -> dict[str, Any]:
    row = await tx.one(
        """INSERT INTO owner.errands (company_id, title_fa, brief_md, source, file_ids, due_at)
           VALUES (:co, :t, :b, :s, CAST(:f AS uuid[]), :due) RETURNING ref""",
        co=holding_id,
        t=(title or title_of(brief))[:200],
        b=brief,
        s=source,
        f=[str(f) for f in file_ids],
        due=due_at,
    )
    return await load(tx, row["ref"])


async def for_message(
    tx: Tx, holding_id: UUID, links: dict[str, Any], body: str, attachments: list[UUID], voice: bool
) -> str:
    """The errand an owner message in P belongs to: the open one it names
    (`links.errand`) or a new one with the message as its brief."""
    ref = links.get("errand")
    if ref:
        e = await load(tx, str(ref), lock=True)
        if e["status"] not in OPEN:
            raise ApiError(
                422, "validation_failed", fields={"links.errand": f"{ref} is {e['status']}"}
            )
        return str(ref)
    brief = body.strip() or "پیوست‌های این پیام"
    e = await open_errand(
        tx,
        holding_id,
        brief=brief[:20000],
        source="voice" if voice else "text",
        file_ids=attachments[:10],
        due_at=None,
        title=None,
    )
    return str(e["ref"])


async def opened_by(tx: Tx, ref: str, message_ref: str) -> None:
    await tx.exec(
        """UPDATE owner.errands SET message_ref = COALESCE(message_ref, :m), updated_at = now()
           WHERE ref = :r""",
        m=message_ref,
        r=ref,
    )


async def _working(tx: Tx, who: Principal, ref: str) -> dict[str, Any]:
    e = await load(tx, ref, lock=True)
    if e["status"] not in OPEN:
        raise ApiError(409, "validation_failed", f"{ref} is {e['status']}")
    if who.run_id:
        await tx.exec(
            """UPDATE owner.errands SET run_ids = array_append(run_ids, CAST(:run AS uuid))
               WHERE id = :id AND NOT (CAST(:run AS uuid) = ANY(run_ids))""",
            run=who.run_id,
            id=e["id"],
        )
    return e


async def step(tx: Tx, who: Principal, ref: str, body: StepIn) -> dict[str, Any]:
    e = await _working(tx, who, ref)
    if len(e["steps"] or []) >= MAX_STEPS:
        raise ApiError(422, "validation_failed", fields={"steps": f"at most {MAX_STEPS}"})
    item = {
        "at": datetime.now(UTC).isoformat(),
        "kind": body.kind,
        "summary_fa": body.summary_fa,
        "data": body.data,
    }
    await tx.exec(
        """UPDATE owner.errands SET steps = steps || CAST(:s AS jsonb),
               status = CASE WHEN status = 'queued' THEN 'working' ELSE status END, updated_at = now()
           WHERE id = :id""",
        s=json.dumps([item], ensure_ascii=False, default=str),
        id=e["id"],
    )
    await _updated(tx, e["ref"], "step")
    return await load(tx, ref)


async def finish(tx: Tx, who: Principal, ref: str, body: FinishIn) -> tuple[dict[str, Any], str]:
    """The result: errand done, its files attached, the result posted in P."""
    e = await _working(tx, who, ref)
    if e["status"] == "waiting_owner":
        raise ApiError(
            409, "validation_failed", f"{ref} waits for the owner's decision {e['decision_ref']}"
        )
    files = list(dict.fromkeys(body.file_ids))
    if files:
        found = await tx.all(
            "SELECT id FROM files.files WHERE id = ANY(:ids) AND variant = 'original' AND company_id = :co",
            ids=files,
            co=e["company_id"],
        )
        if len(found) != len(files):
            raise ApiError(
                422, "validation_failed", fields={"file_ids": "unknown file of the holding"}
            )
    await tx.exec(
        """UPDATE owner.errands SET status = 'done', result_md = :r, attachments = CAST(:f AS uuid[]),
               finished_at = now(), updated_at = now()
           WHERE id = :id""",
        r=body.result_md,
        f=[str(f) for f in files],
        id=e["id"],
    )
    t = await tx.one("SELECT id FROM msg.threads WHERE code = :c", c=THREAD)
    m = await tx.one(
        """SELECT ref FROM msg.post(:t, 'agent', :a, :body, CAST(:links AS jsonb),
                                    CAST(:f AS uuid[]), 'text')""",
        t=t["id"],
        a=who.code,
        body=f"نتیجه‌ی {ref}:\n\n{body.result_md}"[:100000],
        links=json.dumps({"errand": ref}),
        f=[str(f) for f in files],
    )
    holding: str = await tx.scalar(
        "SELECT code FROM core.companies WHERE id = :id", id=e["company_id"]
    )
    await events.emit(
        tx,
        holding,
        "message.created",
        m["ref"],
        {"thread": THREAD, "author": who.code, "links": {"errand": ref}},
    )
    await _updated(tx, ref, "done")
    return await load(tx, ref), str(m["ref"])


async def cancel(tx: Tx, ref: str) -> dict[str, Any]:
    e = await load(tx, ref, lock=True)
    if e["status"] not in OPEN:
        raise ApiError(409, "validation_failed", f"{ref} is {e['status']}")
    await tx.exec(
        "UPDATE owner.errands SET status = 'cancelled', finished_at = now(), updated_at = now() WHERE id = :id",
        id=e["id"],
    )
    await _updated(tx, ref, "cancelled")
    out = dict(await load(tx, ref))
    out["withdrawn"] = await withdraw_action(tx, e)
    return out


WITHDRAW_NOTE = "مالک: کار پیشکار لغو شد"


async def withdraw_action(tx: Tx, e: dict[str, Any]) -> str | None:
    """A cancelled errand withdraws its pending `errand_action` card (nothing
    is left for the owner to seal); the card's ref, or None."""
    if not e.get("decision_id"):
        return None
    d = await tx.first(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(),
               decided_by_kind = 'service', decided_by_code = 'system', note = :n
           WHERE id = :id AND status = 'pending' AND kind = 'errand_action'
           RETURNING ref, company_id, thread_code""",
        id=e["decision_id"],
        n=WITHDRAW_NOTE,
    )
    if d is None:
        return None
    company = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=d["company_id"])
    await events.emit(
        tx,
        company,
        "decision.decided",
        d["ref"],
        {"status": "withdrawn", "kind": "errand_action"},
    )
    return str(d["ref"])


async def on_proposed(tx: Tx, ref: str, decision_id: UUID) -> None:
    """An `errand_action` decision: the errand waits for the owner."""
    e = await load(tx, ref, lock=True)
    if e["status"] not in OPEN:
        raise ApiError(
            422, "validation_failed", fields={"payload.errand": f"{ref} is {e['status']}"}
        )
    await tx.exec(
        """UPDATE owner.errands SET status = 'waiting_owner', decision_id = :d, updated_at = now()
           WHERE id = :id""",
        d=decision_id,
        id=e["id"],
    )
    await _updated(tx, ref, "waiting_owner")


async def on_decided(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """The owner decided the errand's commitment: the errand goes on (the
    assistant hears it through the decision's follow-up and thread message);
    an agent still never makes the commitment itself."""
    ref = (d.get("payload") or {}).get("errand")
    if not ref:
        return
    e = await tx.first(SQL + " WHERE e.ref = :r FOR UPDATE OF e", r=str(ref))
    if e is None or e["status"] != "waiting_owner" or e["decision_id"] != d["id"]:
        return
    item = {
        "at": datetime.now(UTC).isoformat(),
        "kind": "note",
        "summary_fa": f"تصمیم مالک درباره‌ی {d['ref']}: {verdict}",
        "data": {"decision": d["ref"], "verdict": verdict},
    }
    await tx.exec(
        """UPDATE owner.errands SET status = 'working', steps = steps || CAST(:s AS jsonb), updated_at = now()
           WHERE id = :id""",
        s=json.dumps([item], ensure_ascii=False),
        id=e["id"],
    )
    await _updated(tx, str(ref), verdict)


async def add_planner_item(
    tx: Tx, who: Principal, holding_id: UUID, body: PlannerIn
) -> dict[str, Any]:
    errand_id = None
    if body.errand:
        errand_id = (await load(tx, body.errand))["id"]
    row = await tx.one(
        """INSERT INTO owner.planner_items (company_id, title_fa, at, note, errand_id, created_by_kind,
               created_by_code)
           VALUES (:co, :t, :at, :n, :e, :k, :c) RETURNING id, ref, title_fa, at, note""",
        co=holding_id,
        t=body.title_fa,
        at=body.at,
        n=body.note,
        e=errand_id,
        k=who.kind,
        c=who.code,
    )
    if body.errand:
        await _updated(tx, body.errand, "planner")
    return row


async def _updated(tx: Tx, ref: str, change: str) -> None:
    e = await tx.one(
        """SELECT e.status, c.code AS company FROM owner.errands e
           JOIN core.companies c ON c.id = e.company_id WHERE e.ref = :r""",
        r=ref,
    )
    await events.emit(
        tx, e["company"], "errand.updated", ref, {"status": e["status"], "change": change}
    )
