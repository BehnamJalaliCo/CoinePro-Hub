"""Checked claims and the agent health board (prompt 12 §12, contract §21.9).

`claim.verdict` (A2: the fact checker, the overseer, QC) records one checked
claim of a deliverable: confirmed, refuted (only with evidence) or
unverifiable. The claim text is masked and at most 300 characters.

The health board is code over the runs, the cards, the ratings and the
claims of one period (7 or 30 days), one row per employee:
    truth        refuted share >= 20% with at least 5 claims checked
    reliability  failed share >= 25%
    loops        two or more retry loops (>= 3 runs on one work item in a
                 day without progress) in the period
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common.redact import scrub

TRUTH_SHARE = 0.20
TRUTH_MIN = 5
RELIABILITY_SHARE = 0.25
LOOPS_MIN = 2
LOOP_RUNS = 3
PERIODS = {"7d": 7, "30d": 30}
CHECKERS = ("fact_checker", "overseer", "inspector")  # charter roles (QC = the inspector)

CLAIM_SQL = """
    SELECT q.*, c.code AS company FROM quality.claims q JOIN core.companies c ON c.id = q.company_id
"""


def health_flags(
    runs: int, failed: int, loops: int, checked: int, refuted: int
) -> tuple[list[str], float | None, float]:
    """(flags, refuted_share, failed_share) of one employee (pure)."""
    failed_share = failed / runs if runs else 0.0
    refuted_share = refuted / checked if checked else None
    flags: list[str] = []
    if refuted_share is not None and checked >= TRUTH_MIN and refuted_share >= TRUTH_SHARE:
        flags.append("truth")
    if runs and failed_share >= RELIABILITY_SHARE:
        flags.append("reliability")
    if loops >= LOOPS_MIN:
        flags.append("loops")
    return flags, refuted_share, failed_share


async def record(
    tx: Tx,
    who: Principal,
    *,
    deliverable_ref: str,
    claim_md: str,
    verdict: str,
    evidence: list[dict[str, Any]],
    protocol: str | None,
) -> dict[str, Any]:
    if verdict == "refuted" and not evidence:
        raise ApiError(
            422, "validation_failed", fields={"evidence": "a refuted claim needs evidence"}
        )
    dl = await tx.first(
        """SELECT dl.id, dl.ref, dl.company_id, dl.producer_id, c.code AS company, e.code AS employee
           FROM cartable.deliverables dl JOIN core.companies c ON c.id = dl.company_id
           LEFT JOIN core.employees e ON e.id = dl.producer_id
           WHERE dl.ref = :r""",
        r=deliverable_ref,
    )
    if dl is None:
        raise ApiError(404, "not_found", f"deliverable {deliverable_ref}")
    text = scrub(" ".join(claim_md.split()))[:300]
    row = await tx.one(
        """INSERT INTO quality.claims (company_id, deliverable_id, deliverable_ref, employee_id, employee_code,
               claim_md, verdict, checked_by_kind, checked_by_code, protocol, evidence)
           VALUES (:co, :dl, :ref, :emp, :code, :claim, :v, :bk, :bc, :p, CAST(:ev AS jsonb))
           RETURNING *""",
        co=dl["company_id"],
        dl=dl["id"],
        ref=dl["ref"],
        emp=dl["producer_id"],
        code=dl["employee"],
        claim=text,
        v=verdict,
        bk=who.kind,
        bc=who.code,
        p=protocol,
        ev=json.dumps(
            [{k: scrub(str(v))[:1000] for k, v in e.items()} for e in evidence], ensure_ascii=False
        ),
    )
    await events.emit(
        tx,
        dl["company"],
        "claim.verdict",
        row["ref"],
        {"deliverable": dl["ref"], "employee": dl["employee"], "verdict": verdict},
    )
    row["company"] = dl["company"]
    return row


def render(r: dict[str, Any]) -> dict[str, Any]:
    """Claim (contract §21.9)."""
    return {
        "id": r["id"],
        "ref": r["ref"],
        "company": r["company"],
        "deliverable": r["deliverable_ref"],
        "employee": r["employee_code"],
        "claim_md": r["claim_md"],
        "verdict": r["verdict"],
        "checked_by": {"kind": r["checked_by_kind"], "code": r["checked_by_code"]},
        "protocol": r["protocol"],
        "evidence": [
            {"kind": e.get("kind", ""), "ref": e.get("ref", ""), "note": e.get("note", "")}
            for e in r["evidence"] or []
        ],
        "at": r["at"],
    }


async def health(
    tx: Tx, period: str, company: str | None, now: datetime | None = None
) -> list[dict[str, Any]]:
    """AgentHealth rows of the period, one per employee (code order)."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=PERIODS[period])
    rows = await tx.all(
        """SELECT e.id, e.code, c.code AS company,
               (SELECT count(*) FROM agents.runs r WHERE r.employee_id = e.id AND r.queued_at >= :s
                  AND r.state IN ('done', 'failed', 'refused')) AS runs,
               (SELECT count(*) FROM agents.runs r WHERE r.employee_id = e.id AND r.queued_at >= :s
                  AND r.state = 'failed') AS failed,
               (SELECT count(*) FROM agents.runs r WHERE r.employee_id = e.id AND r.queued_at >= :s
                  AND r.state = 'refused') AS refused,
               (SELECT COALESCE(sum(r.cost_usd + r.equiv_cost_usd), 0) FROM agents.runs r
                 WHERE r.employee_id = e.id AND r.queued_at >= :s) AS cost_usd,
               (SELECT count(*) FROM (
                    SELECT r.work_id, date_trunc('day', r.queued_at) AS d, count(*) AS n
                    FROM agents.runs r
                    WHERE r.employee_id = e.id AND r.queued_at >= :s AND r.work_id IS NOT NULL
                    GROUP BY 1, 2) x
                 WHERE x.n >= :loop AND NOT EXISTS (
                    SELECT 1 FROM cartable.deliverables dl WHERE dl.work_id = x.work_id
                       AND dl.producer_id = e.id AND date_trunc('day', dl.created_at) = x.d)
               ) AS loops,
               (SELECT count(*) FROM cartable.decisions d WHERE d.proposer_kind = 'agent'
                  AND d.proposer_code = e.code AND d.status = 'returned' AND d.decided_at >= :s)
                 + (SELECT count(*) FROM cartable.deliverables dl
                     JOIN LATERAL (SELECT x.score FROM cartable.ratings x WHERE x.deliverable_id = dl.id
                                   ORDER BY x.version_no DESC LIMIT 1) rt ON true
                    WHERE dl.producer_id = e.id AND dl.created_at >= :s AND rt.score <= 4) AS owner_returns,
               (SELECT count(*) FROM quality.claims q WHERE q.employee_id = e.id AND q.at >= :s) AS checked,
               (SELECT count(*) FROM quality.claims q WHERE q.employee_id = e.id AND q.at >= :s
                  AND q.verdict = 'refuted') AS refuted
           FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE e.kind <> 'system' AND e.status <> 'dismissed'
             AND (CAST(:co AS text) IS NULL OR c.code = :co)
           ORDER BY e.code""",
        s=since,
        co=company,
        loop=LOOP_RUNS,
    )
    out = []
    for r in rows:
        flags, refuted_share, failed_share = health_flags(
            int(r["runs"]), int(r["failed"]), int(r["loops"]), int(r["checked"]), int(r["refuted"])
        )
        runs = int(r["runs"])
        out.append(
            {
                "employee": r["code"],
                "company": r["company"],
                "period": period,
                "runs": runs,
                "failed_share": round(failed_share, 4),
                "refused_share": round(int(r["refused"]) / runs, 4) if runs else 0.0,
                "retry_loops": int(r["loops"]),
                "owner_returns": int(r["owner_returns"]),
                "claims_checked": int(r["checked"]),
                "refuted": int(r["refuted"]),
                "refuted_share": round(refuted_share, 4) if refuted_share is not None else None,
                "cost_usd": Decimal(r["cost_usd"]).quantize(Decimal("0.000001")),
                "flags": flags,
            }
        )
    return out
