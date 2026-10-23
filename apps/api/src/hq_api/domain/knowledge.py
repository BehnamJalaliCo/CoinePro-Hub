"""The four-layer knowledge base (prompt 11 §3, contract §20.3).

One store, four layers, nothing copied:
  holding     knowledge.entries (company = the holding): read by everyone
  company     knowledge.entries of that company, plus the support articles of
              prompt 10 as kind `support` through the view
              knowledge.support_entries (edited and sealed only at /support/kb)
  department  knowledge.entries with a department: that department, the
              company's CEO and the holding
  employee    the employee's memory (core.employee_memory, §16.6), shown to
              the owner read-only

Every entry has at least one source and an expiry no later than its kind
allows (fact 90 days, faq 180, playbook and policy 365, principle 730; the
database checks it too). The cycle: an agent proposes (`in_review`) -> the
overseer or AI safety reviews (code checks first: injection, secrets, a
conflict with a rule red line) -> a company or department entry is approved
by that company's CEO (`knowledge.approve`), a holding entry by the owner's
card (`knowledge_entry`). What the owner writes is approved by that act.

Fourteen days before expiry a review work item goes to the layer's keeper;
at expiry the entry is `expired`: agents no longer find it and a deliverable
or a meeting claim that cites it is refused (422 knowledge_expired).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import CODE, Actor, Model, actor
from hq_common import injection
from hq_common.redact import scrub

LAYERS = ("holding", "company", "department")
KINDS = ("principle", "policy", "fact", "faq", "playbook")
MAX_DAYS = {"fact": 90, "faq": 180, "playbook": 365, "policy": 365, "principle": 730}
REVIEW_DAYS = 14
DEPT = r"^[A-Z][A-Z0-9]{1,11}$"
K_REF = re.compile(r"^K-[0-9]{4,}(?:@[0-9]+)?$")
KB_REF = re.compile(r"^KB-[0-9]{4,6}(?:@[0-9]+)?$")
REVIEWERS = ("overseer", "ai_safety")  # the charters that review (contract §20.3)
SYSTEM = Principal(kind="service", code="knowledge", role="service")


class KnowledgeSource(Model):
    kind: str = Field(pattern=r"^[a-z][a-z_]{1,20}$")
    ref: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class KnowledgeEntryIn(Model):
    """Create and update body (contract §20.12)."""

    layer: Literal["holding", "company", "department"]
    company: str = Field(pattern=CODE)
    department: str | None = Field(default=None, pattern=DEPT)
    kind: Literal["principle", "policy", "fact", "faq", "playbook"]
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=20000)
    sources: list[KnowledgeSource] = Field(min_length=1, max_length=20)
    valid_until: date


class KnowledgeChecks(Model):
    injection: bool
    secrets: bool
    conflicts: bool
    policy: bool


class KnowledgeReview(BaseModel):
    by: Actor
    at: datetime
    verdict: str
    checks: dict[str, bool]
    notes_md: str


class KnowledgeEntry(BaseModel):
    id: UUID
    ref: str
    layer: str
    company: str
    department: str | None
    kind: str
    title_fa: str
    body_md: str
    sources: list[dict[str, Any]]
    # ⟨1.5⟩ the employee layer (memory, §16.6) has no expiry: null there only
    valid_until: date | None
    status: str
    review: KnowledgeReview | None
    approved_by: Actor | None
    version: int
    created_by: Actor
    created_at: datetime
    updated_at: datetime


def today() -> date:
    return datetime.now(UTC).date()


def check_expiry(kind: str, valid_until: date, *, on: date | None = None) -> None:
    on = on or today()
    if valid_until < on:
        raise ApiError(422, "validation_failed", fields={"valid_until": "already in the past"})
    limit = on + timedelta(days=MAX_DAYS[kind])
    if valid_until > limit:
        raise ApiError(
            422,
            "validation_failed",
            fields={
                "valid_until": f"at most {MAX_DAYS[kind]} days for a {kind} (until {limit.isoformat()})"
            },
        )


# ------------------------------------------------------------------ render --
ENTRY_SQL = """
    SELECT e.*, c.code AS company FROM knowledge.entries e JOIN core.companies c ON c.id = e.company_id
"""
SUPPORT_SQL = """
    SELECT s.*, c.code AS company FROM knowledge.support_entries s JOIN core.companies c ON c.id = s.company_id
"""


def render(r: dict[str, Any]) -> KnowledgeEntry:
    created = actor(r.get("created_by_kind"), r.get("created_by_code"))
    assert created is not None
    rv = r.get("review")
    review = None
    if isinstance(rv, dict) and rv.get("verdict"):
        by = actor(rv.get("by_kind"), rv.get("by_code"))
        review = KnowledgeReview(
            by=by or Actor(kind="system", code="knowledge"),
            at=datetime.fromisoformat(str(rv["at"])),
            verdict=str(rv["verdict"]),
            checks={k: bool(v) for k, v in (rv.get("checks") or {}).items()},
            notes_md=str(rv.get("notes_md") or ""),
        )
    return KnowledgeEntry(
        id=r["id"],
        ref=r["ref"],
        layer=r["layer"],
        company=r["company"],
        department=r.get("department"),
        kind=r["kind"],
        title_fa=r["title_fa"],
        body_md=r["body_md"],
        sources=list(r.get("sources") or []),
        valid_until=r.get("valid_until"),
        status=r["status"],
        review=review,
        approved_by=actor(r.get("approved_by_kind"), r.get("approved_by_code"))
        if r.get("approved_by_kind")
        else (
            actor("owner", "owner")
            if r["kind"] == "support" and r["status"] == "approved"
            else None
        ),
        version=r["version"],
        created_by=created,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def render_memory(r: dict[str, Any]) -> KnowledgeEntry:
    """A memory note in the employee layer (read-only, never copied)."""
    return KnowledgeEntry(
        id=UUID(int=int(r["id"])),
        ref=f"MEM-{int(r['id']):06d}",
        layer="employee",
        company=r["company"],
        department=r.get("department"),
        kind="fact",
        title_fa=f"حافظه‌ی {r['employee']}",
        body_md=r["note"],
        sources=[
            {
                "kind": "run" if r.get("run_id") else "employee",
                "ref": str(r.get("run_id") or r["employee"]),
                "note": "",
            }
        ],
        valid_until=None,
        status="approved",
        review=None,
        approved_by=None,
        version=1,
        created_by=Actor(kind="agent", code=r["employee"]),
        created_at=r["created_at"],
        updated_at=r["created_at"],
    )


async def load(
    tx: Tx, ref: str, version: int | None = None, *, lock: bool = False
) -> dict[str, Any]:
    """The entry's given version, else its approved one, else its latest."""
    if version is not None:
        sql = ENTRY_SQL + " WHERE e.ref = :r AND e.version = :v"
        return await tx.one(sql + (" FOR UPDATE OF e" if lock else ""), r=ref, v=version)
    row = await tx.first(
        ENTRY_SQL
        + " WHERE e.ref = :r ORDER BY e.status = 'approved' DESC, e.version DESC LIMIT 1"
        + (" FOR UPDATE OF e" if lock else ""),
        r=ref,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no knowledge entry {ref}")
    return row


async def load_support(tx: Tx, ref: str) -> dict[str, Any]:
    row = await tx.first(
        SUPPORT_SQL
        + " WHERE s.ref = :r ORDER BY s.status = 'approved' DESC, s.version DESC LIMIT 1",
        r=ref,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no support article {ref}")
    return row


# ------------------------------------------------------------------ checks --
def code_checks(title: str, body: str, red_lines: list[dict[str, Any]]) -> dict[str, bool]:
    """What code decides before any reviewer (True = passed): no instruction-
    like passage, no secret or personal data, no `rule` red line broken."""
    from hq_api.domain import charter as CH

    text = f"{title}\n{body}"
    return {
        "injection": not injection.injection_flags(text),
        "secrets": scrub(text) == text,
        "conflicts": not CH.matches(text, red_lines),
        "policy": True,
    }


async def _company(tx: Tx, code: str) -> dict[str, Any]:
    row = await tx.first("SELECT id, code, kind FROM core.companies WHERE code = :c", c=code)
    if row is None:
        raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
    return row


async def validate(tx: Tx, body: KnowledgeEntryIn) -> dict[str, Any]:
    co = await _company(tx, body.company)
    if (body.layer == "holding") != (co["kind"] == "holding"):
        raise ApiError(
            422,
            "validation_failed",
            fields={"layer": "the holding layer is the holding company's, and only its"},
        )
    if body.layer == "department":
        if not body.department or not await tx.scalar(
            "SELECT 1 FROM core.departments WHERE company_id = :co AND code = :d",
            co=co["id"],
            d=body.department,
        ):
            raise ApiError(
                422, "validation_failed", fields={"department": "a department of this company"}
            )
    elif body.department:
        raise ApiError(
            422, "validation_failed", fields={"department": "only for the department layer"}
        )
    check_expiry(body.kind, body.valid_until)
    return co


async def _keeper(tx: Tx, row: dict[str, Any]) -> str | None:
    """Who keeps a layer: the department's manager, the company's CEO, or for
    the holding the head of AI operations."""
    if row["layer"] == "department":
        code = await tx.scalar(
            """SELECT e.code FROM core.employees e JOIN core.departments d ON d.id = e.department_id
               WHERE e.company_id = :co AND d.code = :d AND e.kind IN ('manager', 'inspector') AND e.status = 'active'
               ORDER BY e.created_at LIMIT 1""",
            co=row["company_id"],
            d=row["department"],
        )
        if code:
            return str(code)
    if row["layer"] == "holding":
        code = await tx.scalar(
            """SELECT code FROM core.employees
               WHERE company_id = :co AND role = 'aiops_head' AND status = 'active' LIMIT 1""",
            co=row["company_id"],
        )
        return str(code) if code else None
    code = await tx.scalar(
        "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active' LIMIT 1",
        co=row["company_id"],
    )
    return str(code) if code else None


async def _reviewer(tx: Tx) -> dict[str, Any] | None:
    """AI safety first (the holding's OVS department), else the overseer."""
    return await tx.first(
        """SELECT e.code, c.id AS company_id, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.status = 'active' AND e.role = ANY(:roles)
           ORDER BY e.role = 'ai_safety' DESC, e.created_at LIMIT 1""",
        roles=list(REVIEWERS),
    )


async def _emit(tx: Tx, row: dict[str, Any], change: str) -> None:
    await events.emit(
        tx,
        row["company"],
        "knowledge.updated",
        f"{row['ref']}@{row['version']}",
        {"layer": row["layer"], "kind": row["kind"], "status": row["status"], "change": change},
    )


# ----------------------------------------------------------------- writing --
async def create(
    tx: Tx,
    who: Principal,
    body: KnowledgeEntryIn,
    *,
    ref: str | None = None,
) -> dict[str, Any]:
    """An entry or a new version of `ref`. The owner's is approved by that act
    (the approved version before it retires); an agent's goes to review."""
    co = await validate(tx, body)
    version = 1
    if ref is not None:
        prev = await load(tx, ref)
        if prev["company_id"] != co["id"] or prev["layer"] != body.layer:
            raise ApiError(
                422,
                "validation_failed",
                fields={"ref": "a new version keeps its company and layer"},
            )
        version = int(
            await tx.scalar("SELECT max(version) + 1 FROM knowledge.entries WHERE ref = :r", r=ref)
        )
    status = "approved" if who.is_owner else "in_review"
    row = await tx.one(
        """INSERT INTO knowledge.entries (company_id, ref, version, layer, department, kind, title_fa, body_md,
               sources, valid_until, status, approved_by_kind, approved_by_code, approved_at,
               created_by_kind, created_by_code)
           VALUES (:co, COALESCE(:ref, 'K-' || lpad(nextval('knowledge.entry_ref_seq')::text, 4, '0')), :v,
                   :layer, :dept, :kind, :title, :body, CAST(:src AS jsonb), :vu, :st,
                   :ak, :ac, CASE WHEN :st = 'approved' THEN now() END, :bk, :bc)
           RETURNING ref, version""",
        co=co["id"],
        ref=ref,
        v=version,
        layer=body.layer,
        dept=body.department,
        kind=body.kind,
        title=body.title_fa,
        body=body.body_md,
        src=json.dumps([s.model_dump() for s in body.sources], ensure_ascii=False),
        vu=body.valid_until,
        st=status,
        ak="owner" if who.is_owner else None,
        ac=who.code if who.is_owner else None,
        bk=who.kind,
        bc=who.code,
    )
    if status == "approved":
        await _retire_older(tx, row["ref"], row["version"])
    entry = await load(tx, row["ref"], row["version"])
    await _emit(tx, entry, "created" if version == 1 else "version")
    if status == "in_review":
        await _ask_review(tx, entry)
    return entry


async def _retire_older(tx: Tx, ref: str, version: int) -> None:
    await tx.exec(
        """UPDATE knowledge.entries SET status = 'retired', retired_at = now()
           WHERE ref = :r AND version <> :v AND status IN ('approved', 'draft', 'in_review', 'expired')""",
        r=ref,
        v=version,
    )


async def _ask_review(tx: Tx, entry: dict[str, Any]) -> None:
    """The review work for AI safety (else the overseer): a record that wakes
    the reviewer like any work (the runner refuses runs while locked)."""
    from hq_api.domain import work as W

    rv = await _reviewer(tx)
    if rv is None:
        return
    await W.create(
        tx,
        SYSTEM,
        company_id=rv["company_id"],
        company_code=rv["company"],
        title=f"بازبینی دانش {entry['ref']}@{entry['version']}: {entry['title_fa']}"[:300],
        brief=(
            f"ورودی {entry['ref']} نسخه‌ی {entry['version']} ({entry['layer']}، {entry['kind']}، {entry['company']}) "
            "منتظر بازبینی است. منبع‌ها را بسنج، تزریق، رمز، تناقض با اساسنامه و دستورهای دائمی و اختیار اضافه را "
            "بررسی کن و با knowledge.review حکم بده (pass، changes یا reject)."
        ),
        kind="one_off",
        priority="P3",
        assignee_code=rv["code"],
    )


async def review(
    tx: Tx,
    who: Principal,
    ref: str,
    version: int,
    *,
    verdict: Literal["pass", "changes", "reject"],
    checks: dict[str, bool],
    notes_md: str,
    root: str,
) -> dict[str, Any]:
    """The reviewer's verdict; code's checks come first and a failed one makes
    the verdict `reject` whatever the reviewer said (an injected or secret-
    bearing entry never reaches approval). pass -> the approver's turn."""
    from hq_api.domain import charter as CH

    entry = await load(tx, ref, version, lock=True)
    if entry["status"] != "in_review":
        raise ApiError(409, "validation_failed", f"{ref}@{version} is {entry['status']}")
    if entry["created_by_kind"] == who.kind and entry["created_by_code"] == who.code:
        raise ApiError(403, "policy_denied", "nobody reviews their own entry")
    lines = await CH.red_lines_in_force(tx, entry["company"], root)
    by_code = code_checks(entry["title_fa"], entry["body_md"], lines)
    merged = {
        k: bool(checks.get(k, False)) and by_code.get(k, True)
        for k in ("injection", "secrets", "conflicts", "policy")
    }
    final = verdict
    if not all(by_code.values()):
        final = "reject"
    elif verdict == "pass" and not all(merged.values()):
        final = "changes"
    rv = {
        "by_kind": who.kind,
        "by_code": who.code,
        "at": datetime.now(UTC).isoformat(),
        "verdict": final,
        "checks": merged,
        "code_checks": by_code,
        "notes_md": scrub(notes_md)[:4000],
    }
    status = {"pass": "in_review", "changes": "draft", "reject": "retired"}[final]
    await tx.exec(
        """UPDATE knowledge.entries SET review = CAST(:rv AS jsonb), status = :st,
               retired_at = CASE WHEN :st = 'retired' THEN now() ELSE retired_at END
           WHERE id = :id""",
        rv=json.dumps(rv, ensure_ascii=False),
        st=status,
        id=entry["id"],
    )
    entry = await load(tx, ref, version)
    await _emit(tx, entry, f"review:{final}")
    if final == "pass":
        await _after_pass(tx, entry)
    return entry


async def _after_pass(tx: Tx, entry: dict[str, Any]) -> None:
    """A passed holding entry is a card for the owner (`knowledge_entry`); a
    company or department entry is its CEO's to approve (a work item)."""
    from hq_api.domain import decisions as D
    from hq_api.domain import work as W

    if entry["layer"] == "holding":
        proposer = Principal(
            kind="agent" if entry["created_by_kind"] == "agent" else "service",
            code=entry["created_by_code"],
            role="agent",
        )
        d = await D.propose(
            tx,
            proposer,
            company_id=entry["company_id"],
            company_code=entry["company"],
            body=D.DecisionIn(
                kind="knowledge_entry",
                title=f"دانش هلدینگ {entry['ref']}: {entry['title_fa']}"[:300],
                what=entry["body_md"][:20000],
                why=f"بازبینی {entry['ref']}@{entry['version']} قبول شد; منبع‌ها: "
                + ", ".join(f"{s.get('kind')}:{s.get('ref')}" for s in entry["sources"])[:2000],
                risk="low",
                reversible=True,
                payload={"entry": f"{entry['ref']}@{entry['version']}"},
            ),
            thread_code=None,
        )
        await tx.exec(
            "UPDATE knowledge.entries SET decision_ref = :d WHERE id = :id",
            d=d["ref"],
            id=entry["id"],
        )
        return
    ceo = await tx.scalar(
        "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active' LIMIT 1",
        co=entry["company_id"],
    )
    if ceo:
        await W.create(
            tx,
            SYSTEM,
            company_id=entry["company_id"],
            company_code=entry["company"],
            title=f"تأیید دانش {entry['ref']}@{entry['version']}: {entry['title_fa']}"[:300],
            brief=(
                f"بازبینی {entry['ref']} نسخه‌ی {entry['version']} قبول شد. اگر درست و به‌کار است با "
                "knowledge.approve تأییدش کن؛ وگرنه نسخه‌ی تازه با knowledge.propose بده."
            ),
            kind="one_off",
            priority="P3",
            assignee_code=str(ceo),
        )


async def approve(tx: Tx, who: Principal, ref: str, version: int) -> dict[str, Any]:
    """A CEO approves a company or department entry of its own company after a
    passing review (RLS and OPA keep it to its company)."""
    entry = await load(tx, ref, version, lock=True)
    if entry["layer"] == "holding":
        raise ApiError(403, "policy_denied", "a holding entry is the owner's card")
    review_ = entry.get("review") or {}
    if entry["status"] != "in_review" or review_.get("verdict") != "pass":
        raise ApiError(409, "validation_failed", f"{ref}@{version} has no passing review")
    if entry["created_by_kind"] == who.kind and entry["created_by_code"] == who.code:
        raise ApiError(403, "policy_denied", "the proposer never approves its own entry")
    return await _approved(tx, entry, who)


async def _approved(tx: Tx, entry: dict[str, Any], who: Principal) -> dict[str, Any]:
    await tx.exec(
        """UPDATE knowledge.entries SET status = 'approved', approved_at = now(), approved_by_kind = :k,
               approved_by_code = :c
           WHERE id = :id""",
        k="owner" if who.is_owner else "agent",
        c=who.code,
        id=entry["id"],
    )
    await _retire_older(tx, entry["ref"], entry["version"])
    row = await load(tx, entry["ref"], entry["version"])
    await _emit(tx, row, "approved")
    return row


async def apply_card(tx: Tx, who: Principal, d: dict[str, Any]) -> None:
    """The owner sealed a `knowledge_entry` card: that exact version (still in
    review with a passing verdict) is approved; else the card is superseded."""
    ref, _, v = str(d["payload"].get("entry", "")).partition("@")
    try:
        entry = await load(tx, ref, int(v), lock=True)
    except (ApiError, ValueError) as exc:
        raise ApiError(409, "decision_not_pending", f"{d['ref']}: the entry is gone") from exc
    if entry["status"] != "in_review" or (entry.get("review") or {}).get("verdict") != "pass":
        raise ApiError(409, "decision_not_pending", f"{d['ref']}: {ref}@{v} is {entry['status']}")
    await _approved(tx, entry, who)


async def retire(tx: Tx, who: Principal, ref: str) -> dict[str, Any]:
    entry = await load(tx, ref, lock=True)
    if entry["status"] == "retired":
        raise ApiError(409, "validation_failed", f"{ref} is retired")
    await tx.exec(
        "UPDATE knowledge.entries SET status = 'retired', retired_at = now() WHERE ref = :r AND status <> 'retired'",
        r=ref,
    )
    row = await load(tx, ref, entry["version"])
    await _emit(tx, row, "retired")
    return row


# -------------------------------------------------------------- the daily job --
async def daily(tx: Tx, *, now: datetime | None = None, wake: bool = True) -> dict[str, Any]:
    """Expiry (rule-only, runs while the hub is locked) and, when `wake`, the
    review work 14 days before expiry (a work item wakes its keeper, so it
    waits while the holding is locked)."""
    from hq_api.domain import work as W

    day = (now or datetime.now(UTC)).date()
    expired = await tx.all(
        """UPDATE knowledge.entries SET status = 'expired', expired_at = now()
           WHERE status = 'approved' AND valid_until <= :d RETURNING id""",
        d=day,
    )
    for e in expired:
        row = await tx.one(ENTRY_SQL + " WHERE e.id = :id", id=e["id"])
        await _emit(tx, row, "expired")
    asked = 0
    if wake:
        due = await tx.all(
            ENTRY_SQL
            + """ WHERE e.status = 'approved' AND e.review_work_ref IS NULL
                    AND e.valid_until <= CAST(:d AS date) + CAST(:n AS int) ORDER BY e.valid_until LIMIT 200""",
            d=day,
            n=REVIEW_DAYS,
        )
        for row in due:
            keeper = await _keeper(tx, row)
            if keeper is None:
                continue
            w = await W.create(
                tx,
                SYSTEM,
                company_id=row["company_id"],
                company_code=row["company"],
                title=f"بازبینی دانش {row['ref']} پیش از انقضا ({row['valid_until'].isoformat()})"[
                    :300
                ],
                brief=(
                    f"ورودی {row['ref']} ({row['kind']}، لایه‌ی {row['layer']}) تا {row['valid_until'].isoformat()} "
                    "اعتبار دارد. منبع‌هایش را دوباره بسنج و نسخه‌ی تازه با تاریخ انقضای تازه بده "
                    "(knowledge.propose با همان ref)، یا بگذار منقضی شود."
                ),
                kind="one_off",
                priority="P3",
                assignee_code=keeper,
                due_at=datetime.combine(row["valid_until"], datetime.min.time(), UTC),
            )
            await tx.exec(
                "UPDATE knowledge.entries SET review_work_ref = :w WHERE id = :id",
                w=w["ref"],
                id=row["id"],
            )
            await events.emit(
                tx,
                row["company"],
                "knowledge.expiring",
                f"{row['ref']}@{row['version']}",
                {"valid_until": row["valid_until"].isoformat(), "work": w["ref"], "keeper": keeper},
            )
            asked += 1
    return {"expired": len(expired), "review_work": asked, "skipped_review": not wake}


# --------------------------------------------------------- citing knowledge --
async def require_citable(tx: Tx, refs: list[str]) -> None:
    """An entry (K-…) or a support article (KB-…) cited as evidence or a claim's
    source: one that has expired (and no approved version) is refused."""
    for raw in refs:
        ref = raw.split("@", 1)[0]
        if K_REF.match(raw):
            st = await tx.first(
                "SELECT bool_or(status = 'approved') AS ok, bool_or(status = 'expired') AS expired"
                " FROM knowledge.entries WHERE ref = :r",
                r=ref,
            )
        elif KB_REF.match(raw):
            st = await tx.first(
                "SELECT bool_or(status = 'approved' AND valid_until > CAST(now() AS date)) AS ok,"
                " bool_or(status = 'expired' OR valid_until <= CAST(now() AS date)) AS expired"
                " FROM knowledge.support_entries WHERE ref = :r",
                r=ref,
            )
        else:
            continue
        if st and st["expired"] and not st["ok"]:
            raise ApiError(422, "knowledge_expired", f"{ref} has expired", fields={"source": ref})


# ------------------------------------------------------------------ search --
async def search(
    tx: Tx,
    who: Principal,
    q: str,
    *,
    layer: str | None,
    kind: str | None,
    company_id: UUID | None,
    limit: int,
) -> list[dict[str, Any]]:
    """knowledge.search kind `knowledge`: approved, unexpired entries the agent
    may read (RLS: its company and the holding; department entries of its own
    department unless it is the CEO or a holding-scope role) and the company's
    approved support articles. The employee layer is memory.read's."""
    if layer == "employee":
        return []
    pat = "%" + str(await tx.scalar("SELECT core.like_escape(core.fa_normalize(:q))", q=q)) + "%"
    every_dept = who.scope == "holding" or who.role == "ceo"
    rows: list[dict[str, Any]] = []
    if kind != "support":
        rows += await tx.all(
            """SELECT 'knowledge' AS hit, e.ref, e.version, e.layer, e.kind, e.department, e.title_fa,
                      left(e.body_md, 400) AS body, e.valid_until, e.sources, c.code AS company, e.updated_at AS at
               FROM knowledge.entries e JOIN core.companies c ON c.id = e.company_id
               WHERE e.status = 'approved' AND e.valid_until > CAST(now() AS date) AND e.search LIKE :pat
                 AND (CAST(:layer AS text) IS NULL OR e.layer = :layer)
                 AND (CAST(:kind AS text) IS NULL OR e.kind = :kind)
                 AND (CAST(:co AS uuid) IS NULL OR e.company_id = :co OR e.layer = 'holding')
                 AND (e.layer <> 'department' OR :every OR e.department IS NOT DISTINCT FROM :dept)
               ORDER BY e.updated_at DESC LIMIT :lim""",
            pat=pat,
            layer=layer,
            kind=kind,
            co=company_id,
            every=every_dept,
            dept=who.department,
            lim=limit,
        )
    if (kind in (None, "support")) and layer in (None, "company"):
        rows += await tx.all(
            """SELECT 'support' AS hit, s.ref, s.version, s.layer, s.kind, NULL AS department, s.title_fa,
                      left(s.body_md, 400) AS body, s.valid_until, s.sources, c.code AS company, s.updated_at AS at
               FROM knowledge.support_entries s JOIN core.companies c ON c.id = s.company_id
               WHERE s.status = 'approved' AND s.valid_until > CAST(now() AS date) AND s.search LIKE :pat
                 AND (CAST(:co AS uuid) IS NULL OR s.company_id = :co)
               ORDER BY s.updated_at DESC LIMIT :lim""",
            pat=pat,
            co=company_id,
            lim=limit,
        )
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows[:limit]
