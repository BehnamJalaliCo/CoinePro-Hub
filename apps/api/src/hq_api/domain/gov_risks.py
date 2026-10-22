"""The risk register (prompt 11 §8, contract §20.8, M5).

Risk        RK-0001, per company; score = likelihood x impact (1..25)
keeper      the Inspector General (QC): only the keeper closes a risk (and
            the owner); its owner (the answerable) updates it
review_at   at most 14 days ahead for a score of 15+, 30 for 8+, else 90
overdue     first a work item for the owner (once per review date), then
            PR-112's finding; a 15+ risk needs a mitigation or the owner's
            acceptance (a `risk_acceptance` card, 🔏, at most 90 days)
drafts      a `critical` finding and a post-mortem draft a risk (draft:
            true) once (dedupe key); draft_risk() is the one entry point
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

Category = Literal["product", "security", "data", "money", "people", "vendor", "ops", "reputation"]
Status = Literal["open", "mitigating", "accepted", "closed"]
ACCEPT_MAX = timedelta(days=90)
KEEPER_ROLE = "inspector"
SYSTEM = Principal(kind="service", code="risk-register", role="service")


def max_review(score: int) -> timedelta:
    if score >= 15:
        return timedelta(days=14)
    if score >= 8:
        return timedelta(days=30)
    return timedelta(days=90)


class Links(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str | None = Field(default=None, pattern=r"^FI-[0-9]{4,}$")
    incident: str | None = Field(default=None, pattern=r"^I-[0-9]{4,}$")
    decision: str | None = Field(default=None, pattern=r"^D-[0-9]{4,}$")
    work: str | None = Field(default=None, pattern=r"^W-[0-9]{4,}$")


class RiskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(default="", max_length=20000)
    category: Category
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    links: Links | None = None
    owner: str | None = Field(
        default=None, pattern=r"^([A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?|owner)$"
    )
    mitigation_md: str | None = Field(default=None, max_length=20000)
    review_at: datetime | None = None


class RiskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: str | None = Field(default=None, min_length=1, max_length=300)
    body_md: str | None = Field(default=None, max_length=20000)
    category: Category | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation_md: str | None = Field(default=None, max_length=20000)
    status: Literal["open", "mitigating", "closed"] | None = None
    review_at: datetime | None = None
    owner: str | None = Field(
        default=None, pattern=r"^([A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?|owner)$"
    )
    note: str = Field(default="", max_length=2000)


class UpdateIn(BaseModel):
    """risk.update (A2): its owner or the keeper."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=r"^RK-[0-9]{4,}$")
    version: int = Field(ge=1)
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation_md: str | None = Field(default=None, max_length=20000)
    status: Literal["open", "mitigating", "closed"] | None = None
    note: str = Field(min_length=1, max_length=2000)


class HistoryItem(BaseModel):
    at: datetime
    by: Actor
    change: dict[str, Any]
    note: str


class Accepted(BaseModel):
    decision: str
    until: datetime


class Risk(BaseModel):
    id: UUID
    ref: str
    company: str
    title_fa: str
    body_md: str
    category: str
    likelihood: int
    impact: int
    score: int
    owner: Actor
    mitigation_md: str | None
    status: str
    review_at: datetime
    accepted: Accepted | None
    links: dict[str, Any]
    draft: bool
    origin: str
    history: list[HistoryItem]
    version: int


class RiskMatrix(BaseModel):
    company: str | None
    counts: list[list[int]]


SQL = """
    SELECT r.*, c.code AS company, d.ref AS accepted_ref FROM governance.risks r
    JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN cartable.decisions d ON d.id = r.accepted_decision_id
"""


async def render(tx: Tx, r: dict[str, Any], *, history: bool = True) -> Risk:
    items: list[HistoryItem] = []
    if history:
        for h in await tx.all(
            "SELECT * FROM governance.risk_history WHERE risk_id = :id ORDER BY at", id=r["id"]
        ):
            by = actor(h["by_kind"] if h["by_kind"] != "rule" else "system", h["by_code"])
            assert by is not None
            items.append(HistoryItem(at=h["at"], by=by, change=h["change"], note=h["note"]))
    owner = actor(r["owner_kind"], r["owner_code"])
    assert owner is not None
    return Risk(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        title_fa=r["title_fa"],
        body_md=r["body_md"],
        category=r["category"],
        likelihood=r["likelihood"],
        impact=r["impact"],
        score=r["score"],
        owner=owner,
        mitigation_md=r["mitigation_md"],
        status=r["status"],
        review_at=r["review_at"],
        accepted=Accepted(decision=r["accepted_ref"], until=r["accepted_until"])
        if r["status"] == "accepted" and r["accepted_ref"]
        else None,
        links=r["links"] or {},
        draft=r["draft"],
        origin=r["origin"],
        history=items,
        version=r["version"],
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(SQL + " WHERE r.ref = :ref" + (" FOR UPDATE OF r" if lock else ""), ref=ref)


def clamp_review(score: int, wanted: datetime | None, now: datetime) -> datetime:
    latest = now + max_review(score)
    if wanted is None:
        return latest
    if wanted.tzinfo is None:
        wanted = wanted.replace(tzinfo=UTC)
    return min(max(wanted, now), latest)


async def _owner_of(tx: Tx, company_id: UUID, given: str | None, who: Principal) -> tuple[str, str]:
    """(kind, code): the given employee of the company (or the owner); else the
    raiser when it is of that company; else the company's CEO."""
    if given == "owner":
        return "owner", "owner"
    code = given or (who.code if who.is_agent and who.company_id == company_id else None)
    if code is None:
        code = await tx.scalar(
            "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active'",
            co=company_id,
        )
        if code is None:
            return "owner", "owner"
    if not await tx.scalar(
        "SELECT 1 FROM core.employees WHERE code = :c AND company_id = :co AND status = 'active'",
        c=code,
        co=company_id,
    ):
        raise ApiError(
            422, "validation_failed", fields={"owner": "an active employee of this company"}
        )
    return "agent", code


async def _history(
    tx: Tx, r: dict[str, Any], by: tuple[str, str], change: dict[str, Any], note: str = ""
) -> None:
    await tx.exec(
        """INSERT INTO governance.risk_history (company_id, risk_id, by_kind, by_code, change, note)
           VALUES (:co, :r, :bk, :bc, CAST(:c AS jsonb), :n)""",
        co=r["company_id"],
        r=r["id"],
        bk=by[0],
        bc=by[1],
        c=json.dumps(change, ensure_ascii=False, default=str),
        n=note[:2000],
    )


def _by(who: Principal) -> tuple[str, str]:
    return (
        "agent" if who.is_agent else who.kind if who.kind in ("owner", "service") else "service",
        who.code,
    )


async def create(
    tx: Tx,
    who: Principal,
    company_id: UUID,
    company_code: str,
    body: RiskIn,
    *,
    origin: str,
    draft: bool = False,
    dedupe_key: str | None = None,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    score = body.likelihood * body.impact
    ok, oc = await _owner_of(tx, company_id, body.owner, who)
    row = await tx.first(
        """INSERT INTO governance.risks (company_id, title_fa, body_md, category, likelihood, impact, owner_kind,
               owner_code, mitigation_md, status, review_at, links, origin, draft, dedupe_key, created_by_kind,
               created_by_code)
           VALUES (:co, :t, :b, :cat, :l, :i, :ok, :oc, :m, :st, :rev, CAST(:links AS jsonb), :origin, :draft,
                   :dk, :bk, :bc)
           ON CONFLICT (company_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
           RETURNING ref""",
        co=company_id,
        t=body.title_fa,
        b=body.body_md,
        cat=body.category,
        l=body.likelihood,
        i=body.impact,
        ok=ok,
        oc=oc,
        m=body.mitigation_md,
        st="mitigating" if body.mitigation_md else "open",
        rev=clamp_review(score, body.review_at, now),
        links=json.dumps(body.links.model_dump(exclude_none=True) if body.links else {}),
        origin=origin,
        draft=draft,
        dk=dedupe_key,
        bk=_by(who)[0] if origin != "finding" else "rule",
        bc=who.code,
    )
    if row is None:
        return None  # the draft exists already
    r = await load(tx, row["ref"])
    await _history(tx, r, _by(who), {"created": True, "score": score, "origin": origin})
    await events.emit(tx, company_code, "risk.updated", r["ref"], {"score": score, "status": r["status"],
                                                                   "created": True})  # fmt: skip
    return r


async def update(
    tx: Tx,
    who: Principal,
    r: dict[str, Any],
    changes: dict[str, Any],
    *,
    expected_version: int | None,
    note: str,
) -> dict[str, Any]:
    """A change by the owner, the risk's owner or the keeper. Closing is the
    keeper's (and the owner's); `accepted` comes only from a sealed card."""
    if expected_version is not None and r["version"] != expected_version:
        raise ApiError(409, "version_conflict", f"current version is {r['version']}")
    if r["status"] == "closed" and changes.get("status") != "open":
        raise ApiError(409, "validation_failed", f"{r['ref']} is closed")
    status = changes.get("status")
    if status == "closed" and not who.is_owner and not (who.is_agent and who.role == KEEPER_ROLE):
        raise ApiError(403, "policy_denied", "only the keeper (QC) closes a risk")
    if status == "mitigating" and not (changes.get("mitigation_md") or r["mitigation_md"]):
        raise ApiError(
            422, "validation_failed", fields={"mitigation_md": "mitigating needs a mitigation"}
        )
    now = datetime.now(UTC)
    lk = changes.get("likelihood") or r["likelihood"]
    im = changes.get("impact") or r["impact"]
    fields = ("title_fa", "body_md", "category", "likelihood", "impact", "mitigation_md", "status")
    sets: dict[str, Any] = {k: v for k, v in changes.items() if k in fields and v is not None}
    if changes.get("owner"):
        sets["owner_kind"], sets["owner_code"] = await _owner_of(
            tx, r["company_id"], changes["owner"], who
        )
    review = clamp_review(lk * im, changes.get("review_at") or r["review_at"], now)
    if review != r["review_at"]:
        sets["review_at"] = review
    if status == "closed":
        sets["closed_at"], sets["closed_by_code"] = now, who.code
    elif status == "open" and r["status"] == "closed":
        sets["closed_at"], sets["closed_by_code"] = None, None
    if not sets:
        return r
    if who.is_agent or who.is_owner:
        sets["draft"] = False  # a person looked at it
    assign = ", ".join(f"{k} = :{k}" for k in sets)
    await tx.exec(f"UPDATE governance.risks SET {assign} WHERE id = :id", id=r["id"], **sets)  # noqa: S608 - fixed names
    await _history(tx, r, _by(who), {k: v for k, v in sets.items() if k != "draft"}, note)
    fresh = await load(tx, r["ref"])
    await events.emit(tx, fresh["company"], "risk.updated", r["ref"], {"score": fresh["score"],
                                                                       "status": fresh["status"]})  # fmt: skip
    return fresh


async def accept(tx: Tx, d: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """The owner sealed a `risk_acceptance` card (🔏): accepted until ≤ 90 days."""
    r = await tx.first(SQL + " WHERE r.ref = :ref AND r.company_id = :co FOR UPDATE OF r",
                       ref=payload["risk"], co=d["company_id"])  # fmt: skip
    if r is None or r["status"] == "closed":
        raise ApiError(409, "decision_not_pending", f"{payload['risk']} is not open")
    until = datetime.fromisoformat(str(payload["until"]).replace("Z", "+00:00"))
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if until > datetime.now(UTC) + ACCEPT_MAX:
        raise ApiError(422, "validation_failed", fields={"payload.until": "at most 90 days"})
    await tx.exec(
        """UPDATE governance.risks SET status = 'accepted', accepted_decision_id = :d, accepted_until = :u,
               draft = false WHERE id = :id""",
        d=d["id"],
        u=until,
        id=r["id"],
    )
    await _history(
        tx,
        r,
        ("owner", "owner"),
        {"status": "accepted", "until": until.isoformat(), "decision": d["ref"]},
    )
    await events.emit(
        tx,
        r["company"],
        "risk.updated",
        r["ref"],
        {"status": "accepted", "until": until.isoformat()},
    )
    return {"risk": r["ref"], "until": until.isoformat()}


async def check_acceptance(tx: Tx, company_id: UUID, payload: dict[str, Any]) -> None:
    """A `risk_acceptance` card names an open risk of its company, ≤ 90 days."""
    r = await tx.first(
        "SELECT status FROM governance.risks WHERE ref = :ref AND company_id = :co",
        ref=payload.get("risk"),
        co=company_id,
    )
    if r is None or r["status"] == "closed":
        raise ApiError(
            422, "validation_failed", fields={"payload.risk": "an open risk of this company"}
        )
    until = datetime.fromisoformat(str(payload["until"]).replace("Z", "+00:00"))
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if until > datetime.now(UTC) + ACCEPT_MAX or until <= datetime.now(UTC):
        raise ApiError(
            422, "validation_failed", fields={"payload.until": "within the next 90 days"}
        )


async def matrix(tx: Tx, company_id: UUID | None) -> list[list[int]]:
    counts = [[0] * 5 for _ in range(5)]
    for r in await tx.all(
        """SELECT likelihood, impact, count(*) AS n FROM governance.risks
           WHERE status <> 'closed' AND (CAST(:co AS uuid) IS NULL OR company_id = :co)
           GROUP BY likelihood, impact""",
        co=company_id,
    ):
        counts[r["likelihood"] - 1][r["impact"] - 1] = int(r["n"])
    return counts


# ------------------------------------------------------------- the rules --
async def draft_risk(
    tx: Tx,
    company_id: UUID,
    company_code: str,
    *,
    title_fa: str,
    body_md: str,
    category: str,
    likelihood: int,
    impact: int,
    links: dict[str, str],
    origin: Literal["finding", "postmortem"],
    dedupe_key: str,
) -> str | None:
    """A draft for the keeper (a critical finding, a post-mortem): once per key."""
    r = await create(
        tx,
        SYSTEM,
        company_id,
        company_code,
        RiskIn(
            company=company_code,
            title_fa=title_fa[:300],
            body_md=body_md[:20000],
            category=category,
            likelihood=likelihood,
            impact=impact,
            links=Links(**links),
        ),
        origin=origin,
        draft=True,
        dedupe_key=dedupe_key,
    )
    return r["ref"] if r else None


async def sweep(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """The register's daily rules (code, no model): an expired acceptance
    reopens; an overdue review is a work item for the risk's owner (once per
    review date); a critical finding of the last week drafts a risk."""
    now = now or datetime.now(UTC)
    reopened, tasked, drafted = [], [], []
    for r in await tx.all(
        SQL + " WHERE r.status = 'accepted' AND r.accepted_until < :now", now=now
    ):
        await tx.exec(
            "UPDATE governance.risks SET status = 'open', review_at = :n WHERE id = :id",
            n=now,
            id=r["id"],
        )
        await _history(
            tx, r, ("rule", "risk-register"), {"status": "open", "why": "acceptance expired"}
        )
        reopened.append(r["ref"])
    for r in await tx.all(
        SQL  # noqa: S608 - a module constant
        + """ WHERE r.status IN ('open', 'mitigating') AND r.review_at < :now AND r.owner_kind = 'agent'
                  AND (r.review_work_id IS NULL OR NOT EXISTS (
                       SELECT 1 FROM work.work w WHERE w.id = r.review_work_id AND w.created_at >= r.review_at))""",
        now=now,
    ):
        w = await W.create(
            tx,
            SYSTEM,
            company_id=r["company_id"],
            company_code=r["company"],
            title=f"بازبینی ریسک {r['ref']}: {r['title_fa']}"[:300],
            brief=(
                f"موعد بازبینی ریسک {r['ref']} (امتیاز {r['score']}) گذشته است. با risk.update احتمال، اثر، "
                "راه کاهش یا وضعیت را به‌روز کن و یادداشت بگذار؛ ریسک ۱۵ یا بیشتر یا راه کاهش میگیرد "
                "یا با کارت risk_acceptance پذیرش مالک را میخواهد. بستن فقط با بازرس است."
            ),
            kind="one_off",
            priority="P2",
            assignee_code=r["owner_code"],
        )
        await tx.exec(
            "UPDATE governance.risks SET review_work_id = :w WHERE id = :id", w=w["id"], id=r["id"]
        )
        tasked.append(r["ref"])
    for f in await tx.all(
        """SELECT f.ref, f.title_fa, f.company_id, c.code AS company FROM oversight.findings f
           JOIN core.companies c ON c.id = f.company_id
           WHERE f.severity = 'critical' AND f.created_at > :since""",
        since=now - timedelta(days=7),
    ):
        ref = await draft_risk(
            tx, f["company_id"], f["company"],
            title_fa=f"ریسک از یافته‌ی {f['ref']}: {f['title_fa']}", body_md=f"پیش‌نویس از یافته‌ی بحرانی {f['ref']}.",
            category="ops", likelihood=3, impact=5, links={"finding": f["ref"]}, origin="finding",
            dedupe_key=f"finding:{f['ref']}",
        )  # fmt: skip
        if ref:
            drafted.append(ref)
            await audit.record(tx, audit.SYSTEM, company_id=f["company_id"], action="risk.draft",
                               action_class="A1", target_kind="risk", target_ref=ref,
                               summary=f"from critical finding {f['ref']}")  # fmt: skip
    return {"reopened": reopened, "review_work": tasked, "drafted": drafted}


async def overdue(tx: Tx, now: datetime) -> list[dict[str, Any]]:
    """PR-112's problems: a review whose owner's work is a day old and not done;
    a risk of 15+ with neither a mitigation nor an unexpired acceptance."""
    return [
        dict(r)
        for r in await tx.all(
            SQL  # noqa: S608 - a module constant
            + """ WHERE r.status <> 'closed' AND (
                     (r.review_at < :now AND (r.owner_kind <> 'agent' OR EXISTS (
                         SELECT 1 FROM work.work w WHERE w.id = r.review_work_id
                          AND w.created_at < :day AND w.status NOT IN ('done', 'cancelled'))))
                  OR (r.score >= 15 AND r.status <> 'accepted' AND coalesce(r.mitigation_md, '') = ''
                      AND r.review_at < :now)
                  OR (r.status = 'accepted' AND r.accepted_until < :now))
                  ORDER BY r.ref""",
            now=now,
            day=now - timedelta(days=1),
        )
    ]
