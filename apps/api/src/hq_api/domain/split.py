"""Agents in parallel (contract §33.7 ⟨1.15⟩): a work split into independent parts.

The parent's assignee proposes the split (`work.split {parts: [{title_fa, role, brief}]}`, A1). Code:
- refuses more than PARALLEL_MAX parts (data: seed/work/grok.yaml), fewer than two, and parts that
  depend on each other (a part naming another part or its output);
- makes each part an ordinary child work (the depth limit of 2 stays, the database enforces it),
  with its own run (the work's arrival wakes its assignee) and an equal share of what is left of the
  parent's budget (a share is kept for the merge); the router's concurrency still applies, so the
  parts queue rather than overload;
- does not wake the parent's assignee for each part's output (migration 0050): when every part has
  ended (delivered, done, failed or cancelled) it queues ONE merge run of the parent's assignee,
  whose context carries every part side by side (a failed part as failed, never hidden).

`role` of a part names who receives it: an employee code, a department code (its manager) or a
charter role of the parent's company; the policy (grok.rego) checks it like a delegation.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import EMPLOYEE_CODE, Model

SEED = Path(__file__).resolve().parents[3] / "seed" / "work" / "grok.yaml"
SERVICE = Principal(kind="service", code="split", role="service")
OPEN_SPLIT = ("running", "merging")
ENDED_PART = ("delivered", "done", "failed", "cancelled")
FAILED_PART = ("failed", "cancelled")
MERGE_REASON = "split_merge:"
ROLE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
DEPT = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
MIN_TITLE_MATCH = 8  # a part's title found in another part's brief: they depend on each other
SUMMARY_CHARS = 3000  # each part's output as the merge run reads it
# A part that names another part ("part 2", «بخش دوم», "the first part's output", ...).
_NUM = r"(?:[0-9۰-۹]+|اول|دوم|سوم|چهارم|پنجم|یکم|one|two|three|four|five|first|second|third)"
PART_REF = re.compile(
    rf"(?:\b(?:part|section|step)\s*#?\s*{_NUM}\b)|(?:(?:بخش|قسمت|مرحله)(?:\s*شماره)?\s*{_NUM})",
    re.IGNORECASE,
)
OTHER_PARTS = re.compile(
    r"(?:other|previous|next|another)\s+parts?|(?:بخش|قسمت)(?:‌|\s)?(?:های)?\s*(?:دیگر|قبلی|بعدی)",
    re.IGNORECASE,
)


@cache
def settings() -> dict[str, Any]:
    doc = yaml.safe_load(SEED.read_text(encoding="utf-8")) or {}
    par = dict(doc.get("parallel") or {})
    ws = dict(doc.get("workspace") or {})
    return {
        "max": max(2, min(10, int(par.get("max", 3)))),
        "min": max(2, int(par.get("min", 2))),
        "merge_share": min(0.9, max(0.0, float(par.get("merge_share", 0.25)))),
        "workspace": {
            "runner_min": str(ws.get("runner_min", "0.3.0")),
            "keep_days": int(ws.get("keep_days", 30)),
            "turn_timeout_s": max(60, min(3600, int(ws.get("turn_timeout_s", 3600)))),
        },
    }


def parallel_max() -> int:
    return int(settings()["max"])


# ------------------------------------------------------------------ shapes --
class SplitPartIn(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    role: str = Field(min_length=2, max_length=64)
    brief: str = Field(min_length=1, max_length=20000)


class WorkSplitIn(Model):
    """`work.split`: 2..PARALLEL_MAX independent parts (the maximum is data, checked by code)."""

    parts: list[SplitPartIn] = Field(min_length=1, max_length=10)


class SplitPart(BaseModel):
    n: int
    ref: str
    title_fa: str
    role: str
    assignee: str | None = None
    who_fa: str | None = None
    status: str
    state: Literal["working", "delivered", "failed"]
    progress_pct: int | None = None
    output_ref: str | None = None
    output_title_fa: str | None = None
    failed_fa: str | None = None
    tokens_used: int = 0
    budget_tokens: int | None = None


class WorkSplit(BaseModel):
    """The parts of a work side by side, and the one merge."""

    work_ref: str
    state: Literal["running", "merging", "done", "failed", "cancelled"]
    proposed_by: str
    parts: list[SplitPart]
    merge_queued_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------- the checks --
def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").replace("ي", "ی").replace("ك", "ک")
    t = t.replace("‌", " ").lower()
    return " ".join(re.sub(r"[^\w\s]", " ", t).split())


def dependency(parts: list[SplitPartIn]) -> tuple[int, str] | None:
    """(the part's number, why) of the first part that depends on another; None when independent."""
    titles = [_norm(p.title_fa) for p in parts]
    for i, p in enumerate(parts, 1):
        text = f"{p.title_fa}\n{p.brief}"
        if PART_REF.search(text) or OTHER_PARTS.search(text):
            return i, "names another part"
        brief = _norm(p.brief)
        for j, t in enumerate(titles, 1):
            if j != i and len(t) >= MIN_TITLE_MATCH and t in brief:
                return i, f"uses part {j}"
    if len(set(titles)) != len(titles):
        return next(i for i, t in enumerate(titles, 1) if titles.count(t) > 1), "repeats a part"
    return None


def check_parts(parts: list[SplitPartIn]) -> None:
    conf = settings()
    if not conf["min"] <= len(parts) <= conf["max"]:
        raise ApiError(
            422,
            "validation_failed",
            f"a split has {conf['min']}..{conf['max']} parts",
            fields={"parts": f"{conf['min']}..{conf['max']} parts"},
            message_fa=f"یک کار به {conf['min']} تا {conf['max']} بخش مستقل تقسیم میشود.",
        )
    dep = dependency(parts)
    if dep is not None:
        n, why = dep
        raise ApiError(
            422,
            "validation_failed",
            "parts_dependent: parallel parts must not use each other's output",
            fields={f"parts.{n - 1}": why},
            message_fa=f"بخش {n} به بخش دیگری وابسته است؛ بخش‌های موازی باید مستقل باشند.",
        )


async def resolve(
    tx: Tx, parent: dict[str, Any], role: str, avoid: list[str] | None = None
) -> dict[str, Any]:
    """Who receives a part: an employee code, a department code (its manager) or a charter role
    of the parent's company (a holder not given another part of this split first, then the parent's
    department, then the least busy)."""
    co = parent["company_id"]
    base = """SELECT e.id, e.code, e.kind, e.role, e.status, e.title_fa, d.code AS department
              FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
              WHERE e.company_id = :co AND e.status = 'active' AND e.kind <> 'system'"""
    row: dict[str, Any] | None = None
    if re.fullmatch(EMPLOYEE_CODE, role):
        row = await tx.first(base + " AND e.code = :r", co=co, r=role)
    elif DEPT.fullmatch(role):
        row = await tx.first(
            base + " AND d.code = :r AND e.kind IN ('manager', 'inspector') ORDER BY e.created_at",
            co=co,
            r=role,
        )
    elif ROLE_KEY.fullmatch(role):
        row = await tx.first(
            base  # noqa: S608 - module constants; values are bound
            + """ AND e.role = :r
                ORDER BY (e.code = ANY(CAST(:avoid AS text[]))),
                         (e.department_id IS NOT DISTINCT FROM :dept) DESC,
                         (SELECT count(*) FROM work.work o WHERE o.assignee_id = e.id
                            AND o.status IN ('queued', 'in_progress', 'waiting')),
                         e.created_at
                LIMIT 1""",
            co=co,
            r=role,
            dept=parent.get("department_id"),
            avoid=list(avoid or []),
        )
    if row is None:
        raise ApiError(
            422,
            "validation_failed",
            fields={"role": f"no active employee for {role} in {parent['company']}"},
            message_fa=f"کسی با نقش «{role}» در این شرکت نیست.",
        )
    return row


def shares(parent: dict[str, Any], given_tokens: int, n: int) -> int | None:
    """Each part's token budget: an equal share of what the parent has left (after its earlier
    children), with merge_share kept for the merge run; None when the parent has no budget."""
    if parent.get("budget_tokens") is None:
        return None
    left = int(parent["budget_tokens"]) - int(parent["tokens_used"] or 0) - given_tokens
    keep = 1.0 - float(settings()["merge_share"])
    each = int(max(0, left) * keep) // n
    if each <= 0:
        raise ApiError(
            409,
            "budget_exceeded",
            "nothing left of the work's budget for parallel parts",
            message_fa="از بودجه‌ی این کار چیزی برای بخش‌های موازی نمانده است.",
        )
    return each


# -------------------------------------------------------------- the split --
async def split(
    tx: Tx, who: Principal, parent: dict[str, Any], parts: list[SplitPartIn],
    assignees: list[dict[str, Any]],
) -> dict[str, Any]:  # fmt: skip
    """The split row and one child work per part (the caller checked the parts and the policy)."""
    if parent["status"] in W.CLOSED:
        raise ApiError(409, "validation_failed", "the work is closed")
    if await tx.scalar(
        "SELECT 1 FROM work.splits WHERE work_id = :w AND state = ANY(:open)",
        w=parent["id"],
        open=list(OPEN_SPLIT),
    ):
        raise ApiError(409, "validation_failed", "the work already has open parallel parts")
    if await tx.scalar("SELECT 1 FROM work.split_parts WHERE work_id = :w", w=parent["id"]):
        raise ApiError(409, "validation_failed", "a parallel part is not split again")
    given = int(
        await tx.scalar(
            "SELECT COALESCE(sum(budget_tokens), 0) FROM work.work WHERE parent_id = :p",
            p=parent["id"],
        )
        or 0
    )
    each = shares(parent, given, len(parts))
    sp = await tx.one(
        """INSERT INTO work.splits (company_id, work_id, parts, proposed_by)
           VALUES (:co, :w, :n, :by) RETURNING *""",
        co=parent["company_id"],
        w=parent["id"],
        n=len(parts),
        by=who.code,
    )
    made: list[dict[str, Any]] = []
    for n, (part, to) in enumerate(zip(parts, assignees, strict=True), 1):
        child = await W.create(
            tx,
            who,
            company_id=parent["company_id"],
            company_code=parent["company"],
            title=part.title_fa,
            brief=part.brief,
            kind="one_off",
            priority=parent["priority"],
            assignee_code=to["code"],
            due_at=parent["due_at"],
            budget=W.BudgetIn(tokens=each) if each is not None else None,
            parent=parent,
            key_result=parent.get("key_result_ref"),
        )
        await tx.exec(
            """INSERT INTO work.split_parts (split_id, company_id, work_id, n, role)
               VALUES (:s, :co, :w, :n, :r)""",
            s=sp["id"],
            co=parent["company_id"],
            w=child["id"],
            n=n,
            r=part.role,
        )
        made.append({"n": n, "ref": child["ref"], "title_fa": part.title_fa, "to": to["code"]})
    if parent["status"] in ("queued", "in_progress"):
        await tx.exec("UPDATE work.work SET status = 'waiting' WHERE id = :id", id=parent["id"])
    await W.event(tx, parent, "split", who, {"parts": made})
    await events.emit(
        tx,
        parent["company"],
        "work.split",
        parent["ref"],
        {"state": "running", "parts": made, "by": who.code},
    )
    return dict(sp)


# --------------------------------------------------------- the short meeting --
PARTS_SQL = """
    SELECT sp.n, sp.role, w.id, w.ref, w.title, w.status, w.progress_pct, w.close_reason,
           w.tokens_used, w.budget_tokens, e.code AS a_code, e.title_fa AS a_title_fa,
           (SELECT d.ref FROM cartable.deliverables d WHERE d.work_id = w.id
             ORDER BY d.created_at DESC, d.ref DESC LIMIT 1) AS out_ref,
           (SELECT d.title FROM cartable.deliverables d WHERE d.work_id = w.id
             ORDER BY d.created_at DESC, d.ref DESC LIMIT 1) AS out_title,
           (SELECT left(COALESCE(NULLIF(d.summary, ''), d.body), :chars) FROM cartable.deliverables d
             WHERE d.work_id = w.id ORDER BY d.created_at DESC, d.ref DESC LIMIT 1) AS out_text
    FROM work.split_parts sp JOIN work.work w ON w.id = sp.work_id
    LEFT JOIN core.employees e ON e.id = w.assignee_id
    WHERE sp.split_id = :s ORDER BY sp.n
"""


async def parts_of(tx: Tx, split_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(PARTS_SQL, s=split_id, chars=SUMMARY_CHARS)


def part_state(p: dict[str, Any]) -> Literal["working", "delivered", "failed"]:
    if p["status"] in FAILED_PART:
        return "failed"
    if p["status"] in ("delivered", "done") and not W.is_partial_title(p["out_title"]):
        return "delivered"
    return "working"


def ended(parts: list[dict[str, Any]]) -> bool:
    return bool(parts) and all(p["status"] in ENDED_PART for p in parts)


async def advance(tx: Tx, sp: dict[str, Any], *, worker: bool = True) -> str:
    """Move one split along; returns its state. Every part ended: ONE merge run of the parent's
    assignee (`split_merge:<ref>`), queued by the worker only (runs are the worker's to queue,
    migration 0011: the api leaves it to the next sweep); the merge delivered or the parent
    closed: the split ends."""
    if sp["state"] not in OPEN_SPLIT:
        return str(sp["state"])
    parent = await W.load(tx, sp["work_id"])
    parts = await parts_of(tx, sp["id"])
    new: str | None = None
    if parent["status"] in W.CLOSED:
        new = {"cancelled": "cancelled", "failed": "failed"}.get(parent["status"], "done")
    elif sp["state"] == "running" and ended(parts):
        if not worker:
            return "running"
        reason = f"{MERGE_REASON}{parent['ref']}"
        if parent["assignee_id"] is not None:
            await tx.exec(
                "SELECT agents.queue_run(:e, 'work', :w, NULL, :r, :p)",
                e=parent["assignee_id"],
                w=parent["id"],
                r=reason,
                p=parent["priority"],
            )
        if parent["status"] == "waiting":
            await tx.exec(
                "UPDATE work.work SET status = 'in_progress' WHERE id = :id", id=parent["id"]
            )
        await tx.exec(
            """UPDATE work.splits SET state = 'merging', merge_reason = :r, merge_queued_at = now(),
                   updated_at = now() WHERE id = :id""",
            r=reason,
            id=sp["id"],
        )
        failed = [p["ref"] for p in parts if part_state(p) == "failed"]
        await W.event(tx, parent, "split_merge", SERVICE, {"failed": failed})
        await events.emit(
            tx,
            parent["company"],
            "work.split",
            parent["ref"],
            {
                "state": "merging",
                "parts": [{"n": p["n"], "ref": p["ref"], "state": part_state(p)} for p in parts],
                "failed": failed,
            },
        )
        return "merging"
    elif sp["state"] == "merging" and await tx.scalar(
        """SELECT 1 FROM cartable.deliverables d WHERE d.work_id = :w AND d.created_at > :at
             AND NOT (d.title LIKE :partial)""",
        w=parent["id"],
        at=sp["merge_queued_at"],
        partial=W.PARTIAL_PREFIX + "%",
    ):
        new = "done"
    if new is None:
        return str(sp["state"])
    await tx.exec(
        "UPDATE work.splits SET state = :st, ended_at = now(), updated_at = now() WHERE id = :id",
        st=new,
        id=sp["id"],
    )
    await events.emit(tx, parent["company"], "work.split", parent["ref"], {"state": new})
    return new


async def after_part(tx: Tx, work_id: UUID) -> None:
    """A part changed (delivered, failed, closed) in the api: the split is brought up to date; the
    merge run itself is queued by the worker's sweep (every few minutes)."""
    sp = await tx.first(
        """SELECT s.* FROM work.splits s JOIN work.split_parts p ON p.split_id = s.id
           WHERE p.work_id = :w AND s.state = ANY(:open) FOR UPDATE OF s""",
        w=work_id,
        open=list(OPEN_SPLIT),
    )
    if sp is not None:
        await advance(tx, dict(sp), worker=False)


async def after_parent(tx: Tx, work_id: UUID) -> None:
    sp = await tx.first(
        "SELECT * FROM work.splits WHERE work_id = :w AND state = ANY(:open) FOR UPDATE",
        w=work_id,
        open=list(OPEN_SPLIT),
    )
    if sp is not None:
        await advance(tx, dict(sp), worker=False)


async def sweep(tx: Tx) -> int:
    """Every open split once (the worker's tick); returns how many moved."""
    n = 0
    for sp in await tx.all(
        """SELECT * FROM work.splits WHERE state = ANY(:open) ORDER BY created_at LIMIT 200
           FOR UPDATE SKIP LOCKED""",
        open=list(OPEN_SPLIT),
    ):
        if await advance(tx, dict(sp)) != sp["state"]:
            n += 1
    return n


# ------------------------------------------------------------------ reading --
def _part(p: dict[str, Any], company_fa: str | None) -> SplitPart:
    state = part_state(p)
    return SplitPart(
        n=int(p["n"]),
        ref=p["ref"],
        title_fa=HZ.humanize(p["title"]) or p["title"],
        role=p["role"],
        assignee=p["a_code"],
        who_fa=(f"{p['a_title_fa']} {company_fa}".strip() if p["a_title_fa"] else None),
        status=p["status"],
        state=state,
        progress_pct=p["progress_pct"],
        output_ref=p["out_ref"],
        output_title_fa=HZ.humanize(p["out_title"]) if p["out_title"] else None,
        failed_fa=(HZ.humanize(p["close_reason"]) or "به نتیجه نرسید")
        if state == "failed"
        else None,
        tokens_used=int(p["tokens_used"] or 0),
        budget_tokens=p["budget_tokens"],
    )


async def view(tx: Tx, work_id: UUID) -> WorkSplit | None:
    """The work's latest split, its parts side by side."""
    sp = await tx.first(
        """SELECT s.*, w.ref AS work_ref, c.name_fa AS company_fa FROM work.splits s
           JOIN work.work w ON w.id = s.work_id JOIN core.companies c ON c.id = s.company_id
           WHERE s.work_id = :w ORDER BY s.created_at DESC LIMIT 1""",
        w=work_id,
    )
    if sp is None:
        return None
    return WorkSplit(
        work_ref=sp["work_ref"],
        state=sp["state"],
        proposed_by=sp["proposed_by"],
        parts=[_part(p, sp["company_fa"]) for p in await parts_of(tx, sp["id"])],
        merge_queued_at=sp["merge_queued_at"],
        created_at=sp["created_at"],
    )


async def views(tx: Tx, work_ids: list[UUID]) -> list[WorkSplit]:
    rows = await tx.all(
        "SELECT work_id, min(created_at) AS at FROM work.splits "
        "WHERE work_id = ANY(:ids) GROUP BY work_id ORDER BY at",
        ids=work_ids,
    )
    out = []
    for r in rows:
        v = await view(tx, r["work_id"])
        if v is not None:
            out.append(v)
    return out


async def merge_brief(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    """What the merge run (and any later run of the parent) reads: the parts side by side, each
    with its output or why it failed, and what to do."""
    sp = await tx.first(
        "SELECT * FROM work.splits WHERE work_id = :w ORDER BY created_at DESC LIMIT 1", w=work_id
    )
    if sp is None:
        return None
    parts = await parts_of(tx, sp["id"])
    return {
        "state": sp["state"],
        "instruction": (
            "Every part has ended: write ONE merged deliverable for this work with `deliver`, "
            "from the parts' outputs below; say plainly which part failed and what is missing."
            if sp["state"] == "merging"
            else "The parts are still running; do not merge yet."
            if sp["state"] == "running"
            else "The split is over."
        ),
        "parts": [
            {
                "n": p["n"],
                "ref": p["ref"],
                "title": p["title"],
                "assignee": p["a_code"],
                "state": part_state(p),
                "output": {"ref": p["out_ref"], "title": p["out_title"], "text": p["out_text"]}
                if p["out_ref"]
                else None,
                "failed": p["close_reason"] if part_state(p) == "failed" else None,
            }
            for p in parts
        ],
    }
