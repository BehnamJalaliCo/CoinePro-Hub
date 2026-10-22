"""Employee score (OPERATING_MODEL §1.16, contract §3.3):

    0.40·owner_rating + 0.25·success_with_evidence
  + 0.20·cost_per_accepted_output + 0.15·on_time

each normalised to 0..10 over the last 90 days:
  owner_rating        latest owner rating per deliverable (1..10 -> 0..10)
  success_with_evidence  done / (done + failed + cancelled) of the employee's work
  cost_per_accepted_output  10 x min(1, department median / own cost per
                      accepted output); accepted = latest rating >= 6
  on_time             share of finished work with a due date closed on time
A component without data is left out and the weights are renormalised;
no data at all -> no score. Computed by a job (nightly, and after each
rating for that department), stored, never edited by hand.

The owner's welcome of a new hire (its `hire` story, contract §18.12 and
§18.15) is a small fixed positive part on top: +0.2 in the month of the
welcome (`owner_welcome` in the components), the score capped at 10. A
welcome alone makes no score: it only adds to one that has data.
"""

from __future__ import annotations

import json
from decimal import Decimal
from statistics import median
from typing import Any
from uuid import UUID

from hq_api.db import Tx

WEIGHTS = {
    "owner_rating": 0.40,
    "success_with_evidence": 0.25,
    "cost_per_accepted_output": 0.20,
    "on_time": 0.15,
}
ACCEPTED_FROM = 6
WELCOME_BONUS = 0.2


def with_welcome(score: float | None, welcomed: bool) -> float | None:
    """The owner's welcome this month: +0.2 on a score that exists (max 10)."""
    if score is None or not welcomed:
        return score
    return round(min(10.0, score + WELCOME_BONUS), 2)


def combine(components: dict[str, float | None]) -> float | None:
    present = {k: v for k, v in components.items() if v is not None and k in WEIGHTS}
    if not present:
        return None
    total_w = sum(WEIGHTS[k] for k in present)
    return round(sum(WEIGHTS[k] * v for k, v in present.items()) / total_w, 2)


def cost_component(own: float | None, dept_median: float | None) -> float | None:
    if own is None or dept_median is None:
        return None
    if own <= 0:
        return 10.0
    return round(10 * min(1.0, dept_median / own), 2)


async def recompute_department(tx: Tx, department_id: UUID) -> list[dict[str, Any]]:
    rows = await tx.all(
        """WITH emp AS (
               SELECT e.id, e.code FROM core.employees e
               WHERE e.department_id = :d AND e.kind = 'employee' AND e.status <> 'dismissed'),
           latest AS (
               SELECT DISTINCT ON (r.deliverable_id) r.deliverable_id, r.score, dl.producer_id
               FROM cartable.ratings r JOIN cartable.deliverables dl ON dl.id = r.deliverable_id
               WHERE dl.producer_id IN (SELECT id FROM emp) AND dl.created_at > now() - interval '90 days'
               ORDER BY r.deliverable_id, r.version_no DESC),
           closed AS (
               SELECT w.assignee_id,
                      count(*) FILTER (WHERE w.status = 'done') AS done,
                      count(*) FILTER (WHERE w.status IN ('done', 'failed', 'cancelled')) AS finished,
                      count(*) FILTER (WHERE w.status = 'done' AND w.due_at IS NOT NULL) AS with_due,
                      count(*) FILTER (WHERE w.status = 'done' AND w.due_at IS NOT NULL
                                       AND w.closed_at <= w.due_at) AS on_time
               FROM work.work w
               WHERE w.assignee_id IN (SELECT id FROM emp) AND w.updated_at > now() - interval '90 days'
               GROUP BY w.assignee_id),
           cost AS (
               SELECT c.actor_ref, sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)) AS usd
               FROM llm.calls c
               WHERE c.actor_ref IN (SELECT code FROM emp) AND c.started_at > now() - interval '90 days'
               GROUP BY c.actor_ref)
           SELECT e.id, e.code,
                  (SELECT avg(score) FROM latest l WHERE l.producer_id = e.id) AS rating_avg,
                  (SELECT count(*) FROM latest l WHERE l.producer_id = e.id AND l.score >= :acc) AS accepted,
                  cl.done, cl.finished, cl.with_due, cl.on_time, co.usd,
                  EXISTS (SELECT 1 FROM owner.stories s
                           WHERE s.kind = 'hire' AND s.links ->> 'employee' = e.code
                             AND s.welcomed_at >= date_trunc('month', now())) AS welcomed
           FROM emp e LEFT JOIN closed cl ON cl.assignee_id = e.id LEFT JOIN cost co ON co.actor_ref = e.code""",
        d=department_id,
        acc=ACCEPTED_FROM,
    )
    per_output: dict[UUID, float] = {}
    for r in rows:
        if r["usd"] is not None and r["accepted"]:
            per_output[r["id"]] = float(Decimal(r["usd"]) / r["accepted"])
    dept_median = median(per_output.values()) if per_output else None

    results = []
    for r in rows:
        comps: dict[str, float | None] = {
            "owner_rating": round((float(r["rating_avg"]) - 1) * 10 / 9, 2)
            if r["rating_avg"] is not None
            else None,
            "success_with_evidence": round(10 * r["done"] / r["finished"], 2)
            if r["finished"]
            else None,
            "cost_per_accepted_output": cost_component(per_output.get(r["id"]), dept_median),
            "on_time": round(10 * r["on_time"] / r["with_due"], 2) if r["with_due"] else None,
        }
        score = combine(comps)
        if r["welcomed"]:
            comps["owner_welcome"] = WELCOME_BONUS  # recorded; added once a score exists
        results.append(
            {
                "id": r["id"],
                "code": r["code"],
                "score": with_welcome(score, bool(r["welcomed"])),
                "owner_avg": round(float(r["rating_avg"]), 2)
                if r["rating_avg"] is not None
                else None,
                "components": comps,
            }
        )
    ranked = sorted(
        (x for x in results if x["score"] is not None), key=lambda x: (-x["score"], x["code"])
    )
    rank = {x["id"]: i + 1 for i, x in enumerate(ranked)}
    for x in results:
        x["rank"] = rank.get(x["id"])
        await tx.exec(
            """UPDATE core.employees SET score = :s, score_owner_avg = :oa, score_components = CAST(:c AS jsonb),
                   rank_in_department = :rank, score_updated_at = now()
               WHERE id = :id""",
            id=x["id"],
            s=x["score"],
            oa=x["owner_avg"],
            c=json.dumps(x["components"]),
            rank=x["rank"],
        )
        if x["score"] is not None:
            await tx.exec(
                """INSERT INTO core.employee_scores (employee_id, company_id, month, value, components)
                   SELECT :id, company_id, date_trunc('month', now())::date, :s, CAST(:c AS jsonb)
                   FROM core.employees WHERE id = :id
                   ON CONFLICT (employee_id, month) DO UPDATE
                       SET value = EXCLUDED.value, components = EXCLUDED.components, computed_at = now()""",
                id=x["id"],
                s=x["score"],
                c=json.dumps(x["components"]),
            )
    return results


async def recompute_all(tx: Tx) -> int:
    depts = await tx.all(
        "SELECT DISTINCT department_id FROM core.employees WHERE kind = 'employee' AND department_id IS NOT NULL"
    )
    n = 0
    for d in depts:
        n += len(await recompute_department(tx, d["department_id"]))
    return n
