"""Department ranks (prompt 12 §5, contract §21.5). Code only, no model;
computed with the stars roll-up of a closed week or Jalali month.

    score = 35% people     employees' scores x 10, weighted by active days
          + 30% delivery   work done with evidence on time / work due
          + 20% efficiency the employees' efficiency (§18.4, the roll-up's)
          + 15% owner      the owner's ratings of the department's
                           deliverables x 10

Every part is 0..100. A part without data is left out and the weights of the
rest are renormalised (the owner's 15% is spread over the others when the
owner rated nothing). A department without an active employee in the period
is not ranked. `rank_company` ranks inside the company; `rank_holding` ranks
the departments with the same code across companies, null when only one has
a score.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx

WEIGHTS = {"people": 0.35, "delivery": 0.30, "efficiency": 0.20, "owner": 0.15}
TREND = 4  # earlier periods shown in a trend


def department_score(parts: dict[str, float | None]) -> float | None:
    """The weighted score of the parts that have data (weights renormalised)."""
    present = {k: v for k, v in parts.items() if v is not None and k in WEIGHTS}
    if not present:
        return None
    total = sum(WEIGHTS[k] for k in present)
    return round(sum(WEIGHTS[k] * float(v) for k, v in present.items()) / total, 1)


def active_days(
    hired_at: datetime, dismissed_at: datetime | None, start: datetime, end: datetime
) -> float:
    """Days of [start, end) the employee was on the payroll."""
    a = max(hired_at, start)
    b = min(dismissed_at or end, end)
    return max(0.0, (b - a).total_seconds() / 86400)


def people_part(rows: list[tuple[float | None, float]]) -> float | None:
    """(score 0..10 or None, active days) per employee -> 0..100."""
    scored = [(s, d) for s, d in rows if s is not None and d > 0]
    days = sum(d for _, d in scored)
    if not days:
        return None
    return round(sum(float(s) * 10 * d for s, d in scored) / days, 1)


def rank(values: list[tuple[Any, float]]) -> dict[Any, int]:
    """Competition ranking, highest first (ties share a rank)."""
    ordered = sorted(values, key=lambda x: -x[1])
    out: dict[Any, int] = {}
    for i, (key, v) in enumerate(ordered):
        out[key] = 1 + sum(1 for _, w in ordered[:i] if w > v)
    return out


async def figures(
    tx: Tx,
    start: datetime,
    end: datetime,
    efficiency_of: dict[UUID, float | None],
    only: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Per department of an active operating company (`only`: of these
    companies): its parts for [start, end)."""
    depts = await tx.all(
        """SELECT d.id, d.code, d.company_id, c.code AS company
           FROM core.departments d JOIN core.companies c ON c.id = d.company_id
           WHERE c.kind = 'company' AND c.status = 'active' AND d.status <> 'archived'
             AND (CAST(:only AS uuid[]) IS NULL OR c.id = ANY(CAST(:only AS uuid[])))
           ORDER BY c.code, d.code""",
        only=only,
    )
    out = []
    for d in depts:
        emps = await tx.all(
            """SELECT id, score, hired_at, dismissed_at FROM core.employees
               WHERE department_id = :d AND kind <> 'system'
                 AND hired_at < :e AND (dismissed_at IS NULL OR dismissed_at > :s)""",
            d=d["id"],
            s=start,
            e=end,
        )
        staffed = [
            (
                float(e["score"]) if e["score"] is not None else None,
                active_days(e["hired_at"], e["dismissed_at"], start, end),
            )
            for e in emps
        ]
        if not any(days > 0 for _, days in staffed):
            continue  # no active employee in the period: not ranked
        due = await tx.one(
            """SELECT count(*) AS due,
                      count(*) FILTER (
                          WHERE w.status IN ('done', 'delivered')
                            AND COALESCE(w.delivered_at, w.closed_at) <= w.due_at
                            AND EXISTS (SELECT 1 FROM cartable.deliverables dl
                                         WHERE dl.work_id = w.id AND jsonb_array_length(dl.evidence) > 0)
                      ) AS on_time
               FROM work.work w
               WHERE w.department_id = :d AND w.due_at >= :s AND w.due_at < :e
                 AND w.status <> 'cancelled'""",
            d=d["id"],
            s=start,
            e=end,
        )
        rating = await tx.scalar(
            """SELECT avg(x.score) FROM cartable.deliverables dl
               JOIN core.employees e ON e.id = dl.producer_id
               JOIN LATERAL (SELECT r.score FROM cartable.ratings r WHERE r.deliverable_id = dl.id
                             ORDER BY r.version_no DESC LIMIT 1) x ON true
               WHERE e.department_id = :d AND dl.created_at >= :s AND dl.created_at < :e""",
            d=d["id"],
            s=start,
            e=end,
        )
        effs = [v for e in emps if (v := efficiency_of.get(e["id"])) is not None]
        parts = {
            "people": people_part(staffed),
            "delivery": round(100 * int(due["on_time"]) / int(due["due"]), 1)
            if int(due["due"])
            else None,
            "efficiency": round(sum(effs) / len(effs), 1) if effs else None,
            "owner": round(float(rating) * 10, 1) if rating is not None else None,
        }
        out.append(
            {
                "department_id": d["id"],
                "department": d["code"],
                "company_id": d["company_id"],
                "company": d["company"],
                "parts": parts,
                "employees": sum(1 for _, days in staffed if days > 0),
                "score": department_score(parts),
            }
        )
    return out


def ranked(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adds rank_company and rank_holding to the rows that have a score."""
    scored = [r for r in rows if r["score"] is not None]
    for co in {r["company"] for r in scored}:
        mine = [r for r in scored if r["company"] == co]
        ranks = rank([(r["department_id"], float(r["score"])) for r in mine])
        for r in mine:
            r["rank_company"] = ranks[r["department_id"]]
    for code in {r["department"] for r in scored}:
        same = [r for r in scored if r["department"] == code]
        ranks = rank([(r["department_id"], float(r["score"])) for r in same])
        for r in same:
            r["rank_holding"] = ranks[r["department_id"]] if len(same) > 1 else None
    return scored


async def compute(
    tx: Tx,
    period: str,
    key: str,
    start: datetime,
    end: datetime,
    efficiency_of: dict[UUID, float | None],
    only: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """The ranks of a closed period, written once (append-only, idempotent)."""
    if await tx.scalar(
        "SELECT 1 FROM people.department_ranks WHERE period = :p AND key = :k LIMIT 1",
        p=period,
        k=key,
    ):
        return []
    rows = ranked(await figures(tx, start, end, efficiency_of, only))
    for r in rows:
        previous = await tx.all(
            """SELECT score FROM people.department_ranks
               WHERE period = :p AND department_id = :d ORDER BY key DESC LIMIT :n""",
            p=period,
            d=r["department_id"],
            n=TREND,
        )
        r["trend"] = [float(x["score"]) for x in reversed(previous)] + [float(r["score"])]
        await tx.exec(
            """INSERT INTO people.department_ranks (company_id, period, key, department_id, department,
                   score, parts, employees, rank_company, rank_holding, trend, computed_at)
               VALUES (:co, :p, :k, :d, :code, :score, CAST(:parts AS jsonb), :n, :rc, :rh,
                       CAST(:trend AS jsonb), :at)""",
            co=r["company_id"],
            p=period,
            k=key,
            d=r["department_id"],
            code=r["department"],
            score=r["score"],
            parts=json.dumps(r["parts"]),
            n=r["employees"],
            rc=r["rank_company"],
            rh=r["rank_holding"],
            trend=json.dumps(r["trend"]),
            at=datetime.now(UTC),
        )
    if rows:
        holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
        await events.emit(
            tx,
            holding["code"],
            "rankings.updated",
            f"{period}:{key}",
            {"period": period, "key": key},
        )
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=holding["id"],
            action="rankings.compute",
            action_class="A1",
            target_kind="rankings",
            target_ref=f"{period}:{key}",
            summary=f"{len(rows)} department(s) ranked by code",
        )
    return rows


def render(r: dict[str, Any]) -> dict[str, Any]:
    """DepartmentRank (contract §21.5)."""
    return {
        "period": r["period"],
        "key": r["key"],
        "company": r["company"],
        "department": r["department"],
        "score": float(r["score"]),
        "parts": {k: (float(v) if v is not None else None) for k, v in (r["parts"] or {}).items()},
        "employees": int(r["employees"]),
        "rank_company": int(r["rank_company"]),
        "rank_holding": int(r["rank_holding"]) if r["rank_holding"] is not None else None,
        "trend": [float(x) for x in r["trend"] or []],
        "computed_at": r["computed_at"],
    }
