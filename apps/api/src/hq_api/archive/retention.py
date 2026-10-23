"""Retention, disposal and legal holds (prompt 14 §5, contract §23.5, §23.12).

A record's retention comes from its class's rule: the trigger date (filed,
a date field, its case's close, its supersession) plus the rule's `keep`;
`permanent` never ends. The daily sweep is rule-only (no model, no outside
call) and runs while the holding is locked, except what would wake an agent:
  - `then: review` records get ONE work item for the archivist per sweep, and
    only while the holding is unlocked (else they wait, listed in
    GET /archive/retention/due);
  - `then: dispose_card` records go (weekly, batched) on ONE `archive_disposal`
    card for the owner, never a record under a hold.
Nothing is destroyed without that card's seal. At the seal (the deciding
transaction) every listed record still disposable and not held since is
disposed: its files' rows are marked destroyed (an encrypted file's wrapped
key goes with them), a tombstone keeps ref, class, title, dates and every
file's hash, and the stored objects are queued and removed once that
transaction has committed. A record held in between is skipped and named in
the card's resolution.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from dateutil.relativedelta import relativedelta

from hq_api import audit, events
from hq_api.archive import vocab as V
from hq_api.archive.common import LIVE, OWNER, SERVICE, J, actor_of, dumps, holding, invalid
from hq_api.db import Tx
from hq_api.domain import gate
from hq_api.errors import ApiError
from hq_api.principal import Principal

CARD_EVERY = timedelta(days=7)
CARD_MAX = 200
REVIEW_MAX = 50
ARCHIVIST = "archivist"


# ================================================================ compute ==
def due_of(trigger_at: date | None, keep: Any) -> date | None:
    if trigger_at is None or keep == "permanent" or not isinstance(keep, dict):
        return None
    return trigger_at + relativedelta(years=int(keep.get("years") or 0), months=int(keep.get("months") or 0))


async def _case_closed_at(tx: Tx, r: dict[str, Any], fields: list[dict[str, Any]]) -> date | None:
    refs = [
        x["to_ref"]
        for x in await tx.all(
            "SELECT to_ref FROM archive.links WHERE record_id = :r AND to_kind = 'case' AND removed_at IS NULL",
            r=r["id"],
        )
    ]
    meta = J(r["metadata"], {})
    for f in fields:
        v = meta.get(f["key"])
        if f["type"] == "ref" and isinstance(v, dict) and v.get("kind") == "case":
            refs.append(v["ref"])
    if not refs:
        return None
    at = await tx.scalar(
        "SELECT max(closed_at) FROM legal.cases WHERE ref = ANY(:r) AND status = 'closed'", r=list(set(refs))
    )
    return at.date() if at is not None else None


async def compute(
    tx: Tx, r: dict[str, Any], cls: dict[str, Any] | None, fields: list[dict[str, Any]]
) -> None:
    """The record's rule, trigger date, due date and whether it may be disposed."""
    rr = None
    if cls is not None and cls.get("retention"):
        rr = await tx.first(
            "SELECT * FROM archive.retention_rules WHERE ref = :r AND status = 'active'", r=cls["retention"]
        )
    if rr is None or r["state"] in ("draft", "disposed"):
        await tx.exec(
            """UPDATE archive.records SET retention_rule_id = NULL, trigger_at = NULL, due_at = NULL,
                   disposable = false WHERE id = :id AND (retention_rule_id IS NOT NULL OR due_at IS NOT NULL)""",
            id=r["id"],
        )
        return
    trig = rr["trigger"]
    trigger_at: date | None = None
    if trig == "filed":
        trigger_at = (r["filed_at"] or datetime.now(UTC)).date()
    elif trig.startswith("field:"):
        key = trig.split(":", 1)[1]
        f = next((x for x in fields if x["key"] == key), None)
        trigger_at = V.field_dates(f, J(r["metadata"], {}).get(key))
    elif trig == "case_closed":
        trigger_at = await _case_closed_at(tx, r, fields)
    elif trig == "superseded":
        trigger_at = r["trigger_at"] if r["state"] == "superseded" and r["trigger_at"] else (
            datetime.now(UTC).date() if r["state"] == "superseded" else None
        )
    keep = J(rr["keep"])
    due = due_of(trigger_at, keep)
    disposable = rr["then_do"] == "dispose_card" and keep != "permanent"
    await tx.exec(
        """UPDATE archive.records SET retention_rule_id = :rr, trigger_at = :t, due_at = :d, disposable = :x
           WHERE id = :id""",
        id=r["id"], rr=rr["id"], t=trigger_at, d=due, x=disposable,
    )  # fmt: skip


async def superseded(tx: Tx, ref: str) -> None:
    """Another record supersedes `ref` (a link of kind supersedes)."""
    r = await tx.first(
        "SELECT * FROM archive.records WHERE ref = :r AND state IN ('filed', 'sealed') FOR UPDATE", r=ref
    )
    if r is None:
        return
    await tx.exec(
        """UPDATE archive.records SET state = 'superseded', sealed_at = NULL, trigger_at = CURRENT_DATE
           WHERE id = :id""",
        id=r["id"],
    )
    from hq_api.archive import records as R
    from hq_api.archive import schema as SC

    r = await R.load(tx, ref)
    if r["class_key"]:
        cls = await SC.class_at(tx, r["class_key"], r["class_version"])
        await compute(tx, r, cls, list(cls["fields"]))


# ================================================================== holds ==
HOLD_SQL = "SELECT h.* FROM archive.holds h"


async def place(tx: Tx, who: Principal, body: dict[str, Any]) -> dict[str, Any]:
    """A legal hold: the counsel's (with its own case) or the owner's."""
    errors: dict[str, str] = {}
    scope = body.get("scope") or {}
    title = body.get("title_fa")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300:
        errors["title_fa"] = "text of 1-300 characters"
    reason = body.get("reason_md")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 20000:
        errors["reason_md"] = "text of 1-20000 characters"
    case = body.get("case")
    if case is not None:
        row = await tx.first("SELECT id, counsel_id FROM legal.cases WHERE ref = :r", r=case)
        if row is None:
            errors["case"] = "an existing case LC-…"
        elif who.is_agent and row["counsel_id"] != who.employee_id:
            errors["case"] = "one of your own cases"
    elif who.is_agent:
        errors["case"] = "the counsel places a hold with its case"
    recs = list(scope.get("records") or [])
    for i, ref in enumerate(recs):
        if not isinstance(ref, str) or not await tx.scalar("SELECT 1 FROM archive.records WHERE ref = :r", r=ref):
            errors[f"scope.records.{i}"] = "a record you can see"
    folder_ids: list[UUID] = []
    for i, ref in enumerate(scope.get("folders") or []):
        fid = await tx.scalar("SELECT id FROM archive.folders WHERE ref = :r", r=ref) if isinstance(ref, str) else None
        if fid is None:
            errors[f"scope.folders.{i}"] = "an existing folder"
        else:
            folder_ids.append(fid)
    classes = list(scope.get("classes") or [])
    for i, k in enumerate(classes):
        if not isinstance(k, str) or not await tx.scalar("SELECT 1 FROM archive.classes WHERE key = :k", k=k):
            errors[f"scope.classes.{i}"] = "an existing class"
    parties = list(scope.get("parties") or [])
    for i, p in enumerate(parties):
        if not isinstance(p, str) or not await tx.scalar("SELECT 1 FROM archive.parties WHERE ref = :r", r=p):
            errors[f"scope.parties.{i}"] = "an existing party"
    dates: dict[str, date | None] = {}
    for k in ("from", "to"):
        v = scope.get(k)
        try:
            dates[k] = date.fromisoformat(v) if v else None
        except (TypeError, ValueError):
            errors[f"scope.{k}"] = "a date YYYY-MM-DD"
            dates[k] = None
    if not (recs or folder_ids or classes or parties):
        errors["scope"] = "at least one of records, folders, classes or parties"
    if errors:
        raise invalid(errors)
    h = await holding(tx)
    kind, code = actor_of(who)
    row = await tx.one(
        """INSERT INTO archive.holds (company_id, title_fa, case_ref, reason_md, scope, record_refs, folder_ids,
               classes, party_refs, from_date, to_date, placed_by_kind, placed_by_code)
           VALUES (:co, :t, :c, :rs, CAST(:sc AS jsonb), :rr, :fi, :cl, :pr, :fd, :td, :bk, :bc) RETURNING *""",
        co=h["id"], t=title.strip(), c=case, rs=reason.strip(),
        sc=dumps({k: v for k, v in scope.items() if v not in (None, [], "")}), rr=recs, fi=folder_ids,
        cl=classes, pr=parties, fd=dates["from"], td=dates["to"], bk="owner" if who.is_owner else "agent", bc=code,
    )  # fmt: skip
    covered = await covered_records(tx, row["ref"])
    await audit.record(
        tx, who, company_id=h["id"], action="archive.hold", action_class="A2", target_kind="archive_hold",
        target_ref=row["ref"], summary=f"{case or 'owner'}: {len(covered)} record(s)",
    )  # fmt: skip
    await events.emit(tx, h["code"], "hold.changed", row["ref"], {"state": "active", "records": len(covered)})
    from hq_api.archive import automations as AU
    from hq_api.archive import records as R

    for ref in covered[:500]:
        await AU.fire(tx, "hold_set", await R.load(tx, ref))
    return row


async def covered_records(tx: Tx, hold_ref: str) -> list[str]:
    rows = await tx.all(
        """SELECT r.ref FROM archive.records r WHERE :h = ANY (archive.held_by(r.id)) ORDER BY r.ref LIMIT 5000""",
        h=hold_ref,
    )
    return [x["ref"] for x in rows]


async def render_hold(tx: Tx, h: dict[str, Any]) -> dict[str, Any]:
    refs = await covered_records(tx, h["ref"])
    return {
        "ref": h["ref"],
        "title_fa": h["title_fa"],
        "case": h["case_ref"],
        "reason_md": h["reason_md"],
        "scope": J(h["scope"], {}),
        "state": h["state"],
        "placed_by": {"kind": h["placed_by_kind"], "code": h["placed_by_code"]},
        "placed_at": h["placed_at"],
        "released_at": h["released_at"],
        "records": len(refs),
        "record_refs": refs,
        "version": h["version"],
    }


async def release(tx: Tx, h: dict[str, Any], step_up_id: UUID) -> dict[str, Any]:
    if h["state"] != "active":
        raise ApiError(409, "validation_failed", f"{h['ref']} is already released")
    row = await tx.one(
        """UPDATE archive.holds SET state = 'released', released_at = now(), release_step_up_id = :s
           WHERE id = :id RETURNING *""",
        id=h["id"], s=step_up_id,
    )  # fmt: skip
    hq = await holding(tx)
    await audit.record(
        tx, OWNER, company_id=hq["id"], action="archive.hold_release", action_class="A2",
        target_kind="archive_hold", target_ref=h["ref"], summary=h["case_ref"] or "", step_up=True,
    )  # fmt: skip
    await events.emit(tx, hq["code"], "hold.changed", h["ref"], {"state": "released"})
    return row


# ================================================================== sweep ==
async def due(tx: Tx, today: date | None = None, *, limit: int = 500) -> list[dict[str, Any]]:
    """Records whose retention ended (RetentionDue, §23.12), within the
    reader's clearance."""
    today = today or datetime.now(UTC).date()
    rows = await tx.all(
        """SELECT r.ref, r.title_fa, co.code AS scope, r.class_key, x.ref AS rule, r.trigger_at, r.due_at,
                  x.then_do, archive.held_by(r.id) AS holds, r.disposal_ref, r.review_work_ref, r.disposal_kept
           FROM archive.records r JOIN core.companies co ON co.id = r.company_id
           JOIN archive.retention_rules x ON x.id = r.retention_rule_id
           WHERE r.state IN ('filed', 'sealed', 'superseded') AND r.due_at IS NOT NULL AND r.due_at <= :d
           ORDER BY r.due_at, r.ref LIMIT :lim""",
        d=today, lim=limit,
    )  # fmt: skip
    return [
        {"ref": x["ref"], "title_fa": x["title_fa"], "scope": x["scope"], "class": x["class_key"],
         "rule": x["rule"], "trigger_at": x["trigger_at"], "due_at": x["due_at"], "then": x["then_do"],
         "holds": list(x["holds"] or []), "decision_ref": x["disposal_ref"], "review_work": x["review_work_ref"],
         "kept": x["disposal_kept"]}
        for x in rows
    ]  # fmt: skip


async def _recompute_pending(tx: Tx) -> int:
    """case_closed triggers that arrived since (a case closed)."""
    from hq_api.archive import records as R
    from hq_api.archive import schema as SC

    n = 0
    for x in await tx.all(
        """SELECT r.ref FROM archive.records r JOIN archive.retention_rules x ON x.id = r.retention_rule_id
           WHERE r.state IN ('filed', 'sealed', 'superseded') AND r.trigger_at IS NULL
             AND x.trigger = 'case_closed' LIMIT 500"""
    ):
        r = await R.load(tx, x["ref"])
        cls = await SC.class_at(tx, r["class_key"], r["class_version"])
        await compute(tx, r, cls, list(cls["fields"]))
        n += 1
    return n


async def archivist(tx: Tx) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT e.id, e.code, e.company_id, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.role = :r AND e.status = 'active' ORDER BY e.created_at LIMIT 1""",
        r=ARCHIVIST,
    )


async def archivist_work(tx: Tx, title: str, brief: str, *, priority: str = "P3") -> str | None:
    """One work item for the archivist (HQ-ARC); None when the hub has none.
    The caller decides the gate: code calls this only while unlocked, or for
    the owner's own act."""
    from hq_api.domain import work as W

    a = await archivist(tx)
    if a is None:
        return None
    w = await W.create(
        tx, SERVICE, company_id=a["company_id"], company_code=a["company"], title=title[:300],
        brief=brief[:50000], kind="one_off", priority=priority, assignee_code=a["code"],
    )  # fmt: skip
    await tx.exec(
        """UPDATE work.work SET run_meta = COALESCE(run_meta, CAST('{}' AS jsonb)) || CAST(:m AS jsonb)
           WHERE id = :id""",
        m=json.dumps({"task_class": "archive"}),
        id=w["id"],
    )
    return str(w["ref"])


async def sweep(hub: Any, txf: Any, today: date | None = None) -> dict[str, Any]:
    """The daily retention job (rule-only). Returns what it did."""
    from hq_api.archive import automations as AU
    from hq_api.archive import clearance as CL
    from hq_api.archive import records as R

    today = today or datetime.now(UTC).date()
    out: dict[str, Any] = {"recomputed": 0, "due": 0, "review_items": 0, "card": None, "deferred": 0}
    async with txf() as tx:
        await CL.full(tx)
        out["recomputed"] = await _recompute_pending(tx)
        lock = await gate.holding_lock(tx)
        rows = await due(tx, today, limit=2000)
        out["due"] = len(rows)
        for x in rows:  # retention_due, once per record
            n = await tx.exec(
                "UPDATE archive.records SET due_seen_at = now() WHERE ref = :r AND due_seen_at IS NULL", r=x["ref"]
            )
            if n:
                await AU.fire(tx, "retention_due", await R.load(tx, x["ref"]))
        review = [x for x in rows if x["then"] == "review" and not x["review_work"]][:REVIEW_MAX]
        if review and lock is not None:
            out["deferred"] = len(review)  # waking the archivist waits for the launch
        elif review:
            lines = "\n".join(f"- {x['ref']} ({x['class']}, {x['scope']}): {x['title_fa']}" for x in review)
            ref = await archivist_work(
                tx,
                f"بازبینی نگهداری {len(review)} سند بایگانی",
                "The retention of these records ended (rule `review`). For each, read it (archive.read) and "
                "say in your deliverable whether it should be kept (and why) or proposed for disposal; "
                "you never dispose of anything yourself.\n\n" + lines,
            )
            if ref:
                await tx.exec(
                    "UPDATE archive.records SET review_work_ref = :w WHERE ref = ANY(:r)",
                    w=ref, r=[x["ref"] for x in review],
                )  # fmt: skip
                out["review_items"] = 1
        disposable = [
            x for x in rows
            if x["then"] == "dispose_card" and not x["decision_ref"] and not x["kept"] and not x["holds"]
        ]  # fmt: skip
        if disposable:
            out["card"] = await disposal_card(tx, disposable[:CARD_MAX])
    if out["card"]:
        from hq_api import workflows_client

        await workflows_client.decision_created(hub, out["card"])
    return out


async def disposal_card(tx: Tx, rows: list[dict[str, Any]]) -> str | None:
    """At most one pending archive_disposal card, at most one a week."""
    from hq_api.domain import decisions as D

    recent = await tx.scalar(
        """SELECT 1 FROM cartable.decisions WHERE kind = 'archive_disposal'
             AND (status = 'pending' OR created_at > now() - CAST(:gap AS interval)) LIMIT 1""",
        gap=f"{int(CARD_EVERY.total_seconds())} seconds",
    )
    if recent:
        return None
    h = await holding(tx)
    payload = {
        "records": [
            {"ref": x["ref"], "class": x["class"], "title_fa": x["title_fa"], "retention_rule": x["rule"],
             "trigger_at": x["trigger_at"].isoformat() if x["trigger_at"] else None}
            for x in rows
        ]
    }  # fmt: skip
    what = "\n".join(
        f"- {x['ref']} · {x['class']} · {x['scope']} · {x['title_fa']} (پایان نگهداری {x['due_at']})" for x in rows
    )
    d = await D.propose(
        tx,
        SERVICE,
        company_id=h["id"],
        company_code=h["code"],
        body=D.DecisionIn(
            kind="archive_disposal",
            title=f"امحای {len(rows)} سند بایگانی (پایان دوره‌ی نگهداری)",
            what=("با مُهر این کارت، فایل‌های این سندها نابود میشوند و فقط سنگ‌نوشته (ارجاع، رده، عنوان، "
                  "تاریخ‌ها و hash فایل‌ها) میماند. سند توقیف‌شده هرگز امحا نمیشود.\n\n" + what)[:20000],
            why="قاعده‌های نگهداری بایگانی (dispose_card)",
            risk="high",
            reversible=False,
            payload=payload,
        ),  # fmt: skip
        thread_code=None,
        company_kind="holding",
    )
    await tx.exec("UPDATE archive.records SET disposal_ref = :d WHERE ref = ANY(:r)",
                  d=d["ref"], r=[x["ref"] for x in rows])  # fmt: skip
    return str(d["ref"])


# ================================================================ dispose ==
async def apply_disposal(tx: Tx, d: dict[str, Any]) -> dict[str, Any]:
    """The owner sealed an archive_disposal card (in its transaction)."""
    from hq_api.archive import clearance as CL

    await CL.full(tx)
    today = datetime.now(UTC).date()
    disposed: list[str] = []
    skipped: list[dict[str, str]] = []
    for item in (d["payload"] or {}).get("records") or []:
        ref = item.get("ref")
        r = await tx.first(
            """SELECT r.*, co.code AS scope FROM archive.records r JOIN core.companies co ON co.id = r.company_id
               WHERE r.ref = :r FOR UPDATE OF r""",
            r=ref,
        )
        if r is None or r["state"] == "disposed":
            skipped.append({"ref": str(ref), "why": "gone"})
            continue
        holds = list(await tx.scalar("SELECT archive.held_by(:r)", r=r["id"]) or [])
        if holds:
            skipped.append({"ref": r["ref"], "why": "held: " + ", ".join(holds)})
            continue
        if not r["disposable"] or r["due_at"] is None or r["due_at"] > today:
            skipped.append({"ref": r["ref"], "why": "no longer due"})
            continue
        files = await tx.all(
            "SELECT id, name, sha256, storage_key FROM archive.record_files WHERE record_id = :r ORDER BY version_n, name",
            r=r["id"],
        )
        for f in files:
            if f["storage_key"]:
                await tx.exec(
                    """INSERT INTO archive.destroy_queue (company_id, storage_key, why, ref)
                       VALUES (:co, :k, 'disposal', :ref)""",
                    co=r["company_id"], k=f["storage_key"], ref=r["ref"],
                )  # fmt: skip
        await tx.exec(
            """UPDATE archive.record_files SET destroyed_at = now(), storage_key = NULL, wrapped_dek = NULL,
                   text = NULL, ocr_wanted = false WHERE record_id = :r AND destroyed_at IS NULL""",
            r=r["id"],
        )
        await tx.exec(
            """INSERT INTO archive.tombstones (company_id, record_id, ref, class_key, title_fa, level_rank, dates,
                   hashes, decision_ref)
               VALUES (:co, :r, :ref, :c, :t, :lr, CAST(:dt AS jsonb), CAST(:h AS jsonb), :d)""",
            co=r["company_id"], r=r["id"], ref=r["ref"], c=r["class_key"], t=r["title_fa"], lr=r["level_rank"],
            dt=dumps({"created_at": r["created_at"], "filed_at": r["filed_at"], "sealed_at": r["sealed_at"],
                      "trigger_at": r["trigger_at"], "due_at": r["due_at"], "disposed_at": datetime.now(UTC)}),
            h=dumps([{"name": f["name"], "sha256": f["sha256"]} for f in files]), d=d["ref"],
        )  # fmt: skip
        await tx.exec(
            """UPDATE archive.records SET state = 'disposed', disposed_at = now(), sealed_at = NULL,
                   metadata = '{}', parties = '[]', party_refs = '{}', watch_dates = '{}', suggestion = NULL,
                   meta_tsv = NULL, sens_tsv = NULL, text_tsv = NULL, disposal_ref = :d
               WHERE id = :id""",
            id=r["id"], d=d["ref"],
        )  # fmt: skip
        await tx.exec(
            "UPDATE archive.reminders SET state = 'done', done_at = now(), done_by = 'disposal' WHERE record_id = :r AND state <> 'done'",
            r=r["id"],
        )
        await tx.exec(
            "UPDATE archive.intake SET text = NULL, updated_at = now() WHERE file_id = ANY(:f)",
            f=[x["id"] for x in await tx.all("SELECT file_id AS id FROM archive.record_files WHERE record_id = :r", r=r["id"])],
        )  # fmt: skip
        await audit.record(
            tx, OWNER, company_id=r["company_id"], action="archive.dispose", action_class="A2",
            target_kind="archive_record", target_ref=r["ref"], summary=f"{d['ref']}: {len(files)} file(s)",
            step_up=True,
        )  # fmt: skip
        await events.emit(tx, r["scope"], "record.updated", r["ref"], {"state": "disposed", "change": "disposed"})
        disposed.append(r["ref"])
    # Records left on the card but not disposed may come on a later card.
    await tx.exec(
        "UPDATE archive.records SET disposal_ref = NULL WHERE disposal_ref = :d AND state <> 'disposed'",
        d=d["ref"],
    )
    return {"disposed": disposed, "skipped": skipped}


async def card_declined(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """Rejected: the owner keeps them (not proposed again under this rule);
    returned, expired or withdrawn: they may come on a later card."""
    await tx.exec(
        """UPDATE archive.records SET disposal_ref = NULL,
               disposal_kept = disposal_kept OR CAST(:kept AS boolean)
           WHERE disposal_ref = :d""",
        d=d["ref"], kept=verdict == "rejected",
    )  # fmt: skip


async def destroy_queued(hub: Any, txf: Any, limit: int = 500) -> int:
    """Removes the stored objects of what a committed transaction destroyed."""
    async with txf() as tx:
        rows = await tx.all(
            "SELECT id, storage_key FROM archive.destroy_queue WHERE done_at IS NULL ORDER BY id LIMIT :l",
            l=limit,
        )
    n = 0
    for x in rows:
        await hub.storage.destroy(x["storage_key"])
        async with txf() as tx:
            await tx.exec("UPDATE archive.destroy_queue SET done_at = now() WHERE id = :id", id=x["id"])
        n += 1
    return n
