"""OKRs of every company (prompt 11 §5, contract §20.5, M1).

okr.draft    the CEO writes the next quarter's objectives and key results (a
             Jalali quarter: 1405-Q3 = Mehr to Azar), in the current quarter's
             last month or for a quarter still without one; the result is one
             decision card of kind `okr` for the owner (amendments allowed:
             {key_results: [{ref, target?, weight?, title_fa?}],
             objectives: [{ref, title_fa?}]})
seal         only the owner's seal makes the objectives `active` (and closes
             the quarter's earlier active ones); a card rejected, returned or
             expired leaves them `draft`. Nothing becomes active by itself.
key result   linked to a KPI (`current` is the KPI's value) or a metric checked
             in by hand (okr.checkin with evidence); progress =
             (current - start) / (target - start), clamped to 0..1
check-in     at least every 14 days (PR-116)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gov_common as G
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

CHECKIN_EVERY = timedelta(days=14)
KPI_KEY = r"^[a-z][a-z0-9_.]{1,60}$"


# ------------------------------------------------------------------ input --
class KeyResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: str = Field(min_length=1, max_length=300)
    kpi: str | None = Field(default=None, pattern=KPI_KEY)
    metric_fa: str | None = Field(default=None, min_length=1, max_length=300)
    start: float = Field(allow_inf_nan=False)
    target: float = Field(allow_inf_nan=False)
    weight: float = Field(default=1, gt=0, le=100)


class ObjectiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fa: str = Field(min_length=1, max_length=300)
    why_md: str = Field(default="", max_length=5000)
    key_results: list[KeyResultIn] = Field(min_length=1, max_length=5)


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    quarter: str = Field(pattern=G.QUARTER)
    objectives: list[ObjectiveIn] = Field(min_length=1, max_length=5)


class CheckinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_result: str = Field(pattern=r"^KR-[0-9]{4,}$")
    confidence: float = Field(ge=0, le=1)
    note_md: str = Field(min_length=1, max_length=5000)
    evidence: list[G.Source] = Field(default_factory=list, max_length=20)
    current: float | None = Field(default=None, allow_inf_nan=False)


# ----------------------------------------------------------------- output --
class Checkin(BaseModel):
    at: datetime
    by: Actor
    confidence: float
    note_md: str
    evidence: list[dict[str, Any]]


class KeyResult(BaseModel):
    id: UUID
    ref: str
    objective: str
    title_fa: str
    kpi: str | None
    metric_fa: str | None
    start: float
    target: float
    current: float | None
    progress: float
    confidence: float | None
    weight: float
    last_checkin_at: datetime | None
    checkin_due_at: datetime | None
    checkins: list[Checkin]


class Objective(BaseModel):
    id: UUID
    ref: str
    company: str
    quarter: str
    title_fa: str
    why_md: str
    owner: Actor
    status: str
    decision: str | None
    progress: float
    key_results: list[KeyResult]
    version: int


def progress(start: float, target: float, current: float | None) -> float:
    if current is None:
        return 0.0
    if target == start:
        return 1.0 if current == target else 0.0
    return max(0.0, min(1.0, (current - start) / (target - start)))


async def kr_current(tx: Tx, kr: dict[str, Any]) -> float | None:
    """A KPI-linked key result takes the KPI's value; a metric its check-in."""
    if kr["kpi_key"]:
        v = await tx.scalar(
            "SELECT last_value FROM governance.kpis WHERE company_id = :co AND key = :k",
            co=kr["company_id"],
            k=kr["kpi_key"],
        )
        return G.num(v)
    return G.num(kr["current"])


OBJECTIVE_SQL = """
    SELECT o.*, c.code AS company, d.ref AS decision_ref FROM governance.objectives o
    JOIN core.companies c ON c.id = o.company_id
    LEFT JOIN cartable.decisions d ON d.id = o.decision_id
"""


async def render(tx: Tx, o: dict[str, Any], *, with_checkins: bool = True) -> Objective:
    krs = await tx.all(
        "SELECT * FROM governance.key_results WHERE objective_id = :o ORDER BY ref", o=o["id"]
    )
    items: list[KeyResult] = []
    total = weighted = 0.0
    for kr in krs:
        cur = await kr_current(tx, kr)
        p = progress(float(kr["start"]), float(kr["target"]), cur)
        w = float(kr["weight"])
        total += w
        weighted += w * p
        checkins: list[Checkin] = []
        if with_checkins:
            for c in await tx.all(
                """SELECT * FROM governance.okr_checkins WHERE key_result_id = :k ORDER BY at DESC LIMIT 20""",
                k=kr["id"],
            ):
                by = actor(c["by_kind"], c["by_code"])
                assert by is not None
                checkins.append(
                    Checkin(at=c["at"], by=by, confidence=float(c["confidence"]), note_md=c["note_md"],
                            evidence=list(c["evidence"] or []))
                )  # fmt: skip
        since = kr["last_checkin_at"] or o["activated_at"]
        items.append(
            KeyResult(
                id=kr["id"],
                ref=kr["ref"],
                objective=o["ref"],
                title_fa=kr["title_fa"],
                kpi=kr["kpi_key"],
                metric_fa=kr["metric_fa"],
                start=float(kr["start"]),
                target=float(kr["target"]),
                current=cur,
                progress=round(p, 4),
                confidence=G.num(kr["confidence"]),
                weight=w,
                last_checkin_at=kr["last_checkin_at"],
                checkin_due_at=since + CHECKIN_EVERY if since and o["status"] == "active" else None,
                checkins=checkins,
            )
        )
    owner = actor(o["owner_kind"], o["owner_code"])
    assert owner is not None
    return Objective(
        id=o["id"],
        ref=o["ref"],
        company=o["company"],
        quarter=o["quarter"],
        title_fa=o["title_fa"],
        why_md=o["why_md"],
        owner=owner,
        status=o["status"],
        decision=o["decision_ref"],
        progress=round(weighted / total, 4) if total else 0.0,
        key_results=items,
        version=o["version"],
    )


async def active_progress(tx: Tx, company_id: UUID, now: datetime | None = None) -> float | None:
    """The weighted progress of the current quarter's active key results, or
    None when the company has no active OKR this quarter."""
    tz = await G.owner_tz(tx)
    quarter = G.quarter_of(G.today(tz, now))
    krs = await tx.all(
        """SELECT k.* FROM governance.key_results k JOIN governance.objectives o ON o.id = k.objective_id
           WHERE o.company_id = :co AND o.quarter = :q AND o.status = 'active'""",
        co=company_id,
        q=quarter,
    )
    if not krs:
        return None
    total = sum(float(k["weight"]) for k in krs)
    acc = 0.0
    for k in krs:
        acc += float(k["weight"]) * progress(
            float(k["start"]), float(k["target"]), await kr_current(tx, k)
        )
    return acc / total if total else None


# ------------------------------------------------------------------ draft --
async def draft(
    tx: Tx, who: Principal, company_id: UUID, code: str, body: DraftIn, *, charters: Any = None
) -> dict[str, Any]:
    """Objectives and key results (`proposed`) and their one `okr` card."""
    from hq_api.domain import decisions as D

    tz = await G.owner_tz(tx)
    current = G.quarter_of(G.today(tz))
    if body.quarter not in (current, G.next_quarter(current)):
        raise ApiError(
            422, "validation_failed",
            fields={"quarter": f"the current ({current}) or the next quarter ({G.next_quarter(current)})"},
        )  # fmt: skip
    if await tx.scalar(
        """SELECT 1 FROM governance.objectives o JOIN cartable.decisions d ON d.id = o.decision_id
           WHERE o.company_id = :co AND o.quarter = :q AND o.status = 'proposed' AND d.status = 'pending'""",
        co=company_id,
        q=body.quarter,
    ):
        raise ApiError(
            409, "validation_failed", f"an OKR card for {body.quarter} is already waiting"
        )
    kpis = {
        r["key"]
        for r in await tx.all(
            "SELECT key FROM governance.kpis WHERE company_id = :co", co=company_id
        )
    }
    for i, o in enumerate(body.objectives):
        for j, kr in enumerate(o.key_results):
            where = f"objectives.{i}.key_results.{j}"
            if (kr.kpi is None) == (kr.metric_fa is None):
                raise ApiError(
                    422, "validation_failed", fields={where: "a kpi or a metric_fa, one of them"}
                )
            if kr.kpi is not None and kr.kpi not in kpis:
                raise ApiError(
                    422, "validation_failed", fields={f"{where}.kpi": "not a KPI of this company"}
                )
    refs: list[str] = []
    ids: list[UUID] = []
    for o in body.objectives:
        row = await tx.one(
            """INSERT INTO governance.objectives (company_id, quarter, title_fa, why_md, owner_kind, owner_code,
                   status, created_by_kind, created_by_code)
               VALUES (:co, :q, :t, :w, :ok, :oc, 'proposed', :bk, :bc) RETURNING id, ref""",
            co=company_id,
            q=body.quarter,
            t=o.title_fa,
            w=o.why_md,
            ok="agent" if who.is_agent else "owner",
            oc=who.code,
            bk="agent" if who.is_agent else who.kind,
            bc=who.code,
        )
        refs.append(row["ref"])
        ids.append(row["id"])
        for kr in o.key_results:
            await tx.exec(
                """INSERT INTO governance.key_results (company_id, objective_id, title_fa, kpi_key, metric_fa,
                       start, target, weight)
                   VALUES (:co, :o, :t, :k, :m, :s, :tg, :w)""",
                co=company_id,
                o=row["id"],
                t=kr.title_fa,
                k=kr.kpi,
                m=kr.metric_fa,
                s=kr.start,
                tg=kr.target,
                w=kr.weight,
            )
    lines = [f"- {r}: {o.title_fa}" for r, o in zip(refs, body.objectives, strict=True)]
    d = await D.propose(
        tx,
        who,
        company_id=company_id,
        company_code=code,
        body=D.DecisionIn(
            kind="okr",
            title=f"OKR {body.quarter}: {body.objectives[0].title_fa}"[:300],
            what="\n".join(lines)[:20000],
            why=(body.objectives[0].why_md or "")[:20000],
            risk="low",
            reversible=True,
            payload={"objective": refs[0], "objectives": refs, "quarter": body.quarter},
        ),
        thread_code=who.code if who.is_agent else None,
        charters=charters,
    )
    await tx.exec(
        "UPDATE governance.objectives SET decision_id = :d WHERE id = ANY(:ids)", d=d["id"], ids=ids
    )
    await events.emit(tx, code, "okr.updated", refs[0], {"status": "proposed", "quarter": body.quarter,
                                                         "decision": d["ref"]})  # fmt: skip
    return {"decision": d, "objectives": refs}


# ---------------------------------------------------------------- the seal --
async def on_decided(
    tx: Tx, d: dict[str, Any], verdict: str, amendments: dict[str, Any] | None
) -> dict[str, Any]:
    """approved: the owner's amendments, then `active` (the quarter's earlier
    active objectives close); otherwise the objectives go back to `draft`."""
    p = d["payload"] or {}
    refs = list(p.get("objectives") or [p.get("objective")])
    rows = await tx.all(
        "SELECT * FROM governance.objectives WHERE ref = ANY(:r) AND company_id = :co FOR UPDATE",
        r=refs,
        co=d["company_id"],
    )
    if verdict != "approved":
        await tx.exec(
            "UPDATE governance.objectives SET status = 'draft' WHERE id = ANY(:ids) AND status = 'proposed'",
            ids=[r["id"] for r in rows],
        )
        return {"objectives": refs, "status": "draft"}
    if not rows or any(r["status"] != "proposed" for r in rows):
        raise ApiError(409, "decision_not_pending", "these objectives are not waiting for a seal")
    for a in (amendments or {}).get("objectives") or []:
        await tx.exec(
            "UPDATE governance.objectives SET title_fa = :t WHERE ref = :r AND id = ANY(:ids)",
            t=str(a.get("title_fa"))[:300],
            r=a.get("ref"),
            ids=[r["id"] for r in rows],
        )
    for a in (amendments or {}).get("key_results") or []:
        kr = await tx.first(
            "SELECT * FROM governance.key_results WHERE ref = :r AND objective_id = ANY(:ids)",
            r=a.get("ref"),
            ids=[r["id"] for r in rows],
        )
        if kr is None:
            raise ApiError(
                422, "validation_failed", fields={"amendments.key_results": f"{a.get('ref')}?"}
            )
        await tx.exec(
            """UPDATE governance.key_results SET target = coalesce(:tg, target), weight = coalesce(:w, weight),
                   title_fa = coalesce(:t, title_fa) WHERE id = :id""",
            tg=G.number(a.get("target")) if a.get("target") is not None else None,
            w=G.number(a.get("weight")) if a.get("weight") is not None else None,
            t=a.get("title_fa"),
            id=kr["id"],
        )
    quarter = rows[0]["quarter"]
    await tx.exec(
        """UPDATE governance.objectives SET status = 'closed', closed_at = now()
           WHERE company_id = :co AND quarter = :q AND status = 'active' AND NOT (id = ANY(:ids))""",
        co=d["company_id"],
        q=quarter,
        ids=[r["id"] for r in rows],
    )
    await tx.exec(
        "UPDATE governance.objectives SET status = 'active', activated_at = now() WHERE id = ANY(:ids)",
        ids=[r["id"] for r in rows],
    )
    await events.emit(tx, d["company"], "okr.updated", refs[0], {"status": "active", "quarter": quarter,
                                                                  "decision": d["ref"]})  # fmt: skip
    return {"objectives": refs, "status": "active"}


# --------------------------------------------------------------- check-in --
async def checkin(tx: Tx, who: Principal, company_id: UUID, body: CheckinIn) -> dict[str, Any]:
    kr = await tx.first(
        """SELECT k.*, o.status AS objective_status, o.ref AS objective_ref FROM governance.key_results k
           JOIN governance.objectives o ON o.id = k.objective_id
           WHERE k.ref = :r AND k.company_id = :co""",
        r=body.key_result,
        co=company_id,
    )
    if kr is None:
        raise ApiError(404, "not_found", f"no key result {body.key_result}")
    if kr["objective_status"] != "active":
        raise ApiError(
            409, "validation_failed", f"{kr['objective_ref']} is {kr['objective_status']}"
        )
    if body.current is not None and kr["kpi_key"]:
        raise ApiError(
            422, "validation_failed", fields={"current": "a KPI key result takes the KPI's value"}
        )
    if body.current is not None and not body.evidence:
        raise ApiError(
            422, "validation_failed", fields={"evidence": "a new value needs its source"}
        )
    ev = [e.model_dump() for e in body.evidence]
    await tx.exec(
        """INSERT INTO governance.okr_checkins (company_id, key_result_id, by_kind, by_code, confidence, note_md,
               evidence, current)
           VALUES (:co, :k, :bk, :bc, :c, :n, CAST(:ev AS jsonb), :cur)""",
        co=company_id,
        k=kr["id"],
        bk="agent" if who.is_agent else "owner",
        bc=who.code,
        c=body.confidence,
        n=body.note_md,
        ev=json.dumps(ev, ensure_ascii=False),
        cur=body.current,
    )
    await tx.exec(
        """UPDATE governance.key_results SET last_checkin_at = now(), confidence = :c,
               current = coalesce(:cur, current) WHERE id = :k""",
        c=body.confidence,
        cur=body.current,
        k=kr["id"],
    )
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :co", co=company_id)
    await events.emit(
        tx, code, "okr.updated", kr["objective_ref"], {"key_result": kr["ref"], "checkin": True}
    )
    return {"key_result": kr["ref"], "confidence": body.confidence,
            "next_due_at": (datetime.now(UTC) + CHECKIN_EVERY).isoformat()}  # fmt: skip


async def checkins_due(tx: Tx, now: datetime) -> list[dict[str, Any]]:
    """Active key results whose last check-in (or activation) is 14+ days old."""
    rows = await tx.all(
        """SELECT k.ref, k.company_id, c.code AS company, o.ref AS objective, o.owner_code,
                  coalesce(k.last_checkin_at, o.activated_at) AS since
           FROM governance.key_results k JOIN governance.objectives o ON o.id = k.objective_id
           JOIN core.companies c ON c.id = k.company_id
           WHERE o.status = 'active' AND coalesce(k.last_checkin_at, o.activated_at) < :t
           ORDER BY k.ref""",
        t=now - CHECKIN_EVERY,
    )
    return [dict(r) for r in rows]
