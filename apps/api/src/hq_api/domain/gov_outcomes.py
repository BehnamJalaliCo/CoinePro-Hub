"""Decision outcome reviews at 30, 60 and 90 days (prompt 11 §6, contract
§20.6, M3).

expected   Decision.expected {metric_fa, kpi?, baseline, target, by_days}:
           optional for every kind; for a `proposal` made after this prompt
           went live (governance.rollout) a missing one is a warning on the
           card (`expected_missing`) for 7 days, then 422 validation_failed.
           Cards made before are never touched.
reviews    the seal of a decision with `expected` makes one review for day 30,
           60 and 90, up to by_days (governance.outcome_reviews, OR-0001)
verdict    on the due day, with a KPI, by code: `met` at the target, `partly`
           at half the distance or more, else `missed` (status verified).
           Without a KPI (or without a value) it is `unmeasurable`: the
           proposer writes outcome.note with its evidence and the overseer
           decides in PR-006 (protocol.result's `outcomes`).
accuracy   a proposer's prediction accuracy = (met + partly / 2) / decided
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gov_common as G
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

GRACE = timedelta(days=7)
ROLLOUT_KEY = "p11.governance"
DAYS = (30, 60, 90)
NOTE_WITHIN = timedelta(
    days=7
)  # an unmeasurable review without a note after this is PR-006's finding


class DecisionExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_fa: str = Field(min_length=1, max_length=300)
    kpi: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.]{1,60}$")
    baseline: float = Field(allow_inf_nan=False)
    target: float = Field(allow_inf_nan=False)
    by_days: Literal[30, 60, 90]


class OutcomeMeasured(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float = Field(allow_inf_nan=False)
    at: datetime
    source_ref: G.EvidenceSource


class OutcomeNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=r"^OR-[0-9]{4,}$")
    note_md: str = Field(min_length=1, max_length=5000)
    measured: OutcomeMeasured | None = None
    evidence: list[G.EvidenceSource] = Field(default_factory=list, max_length=20)


class OverseerVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=r"^OR-[0-9]{4,}$")
    verdict: Literal["met", "partly", "missed", "unmeasurable"]
    note_md: str = Field(min_length=1, max_length=5000)


class OutcomeReview(BaseModel):
    id: UUID
    ref: str
    decision: str
    company: str
    day: int
    due_at: datetime
    expected: dict[str, Any]
    measured: dict[str, Any] | None
    verdict: str
    proposer: Actor
    proposer_note_md: str | None
    overseer_note_md: str | None
    status: str
    version: int


class Accuracy(BaseModel):
    proposer: Actor
    company: str
    met: int
    partly: int
    missed: int
    unmeasurable: int
    accuracy: float | None


SQL = """
    SELECT r.*, c.code AS company FROM governance.outcome_reviews r
    JOIN core.companies c ON c.id = r.company_id
"""


def render(r: dict[str, Any]) -> OutcomeReview:
    who = actor(r["proposer_kind"], r["proposer_code"])
    assert who is not None
    return OutcomeReview(
        id=r["id"],
        ref=r["ref"],
        decision=r["decision_ref"],
        company=r["company"],
        day=r["day"],
        due_at=r["due_at"],
        expected=r["expected"],
        measured=r["measured"],
        verdict=r["verdict"],
        proposer=who,
        proposer_note_md=r["proposer_note_md"],
        overseer_note_md=r["overseer_note_md"],
        status=r["status"],
        version=r["version"],
    )


# --------------------------------------------------------------- proposal --
async def check_expected(
    tx: Tx,
    kind: str,
    company_id: UUID,
    expected: dict[str, Any] | None,
    now: datetime | None = None,
) -> list[str]:
    """The card's warnings; 422 for a bad `expected` or for a proposal
    without one once the 7 days after the rollout are over."""
    if expected is not None:
        e = DecisionExpected.model_validate(expected)
        if e.kpi is not None and not await tx.scalar(
            "SELECT 1 FROM governance.kpis WHERE company_id = :co AND key = :k",
            co=company_id,
            k=e.kpi,
        ):
            raise ApiError(
                422, "validation_failed", fields={"expected.kpi": "not a KPI of this company"}
            )
        return []
    if kind != "proposal":
        return []
    since = await tx.scalar("SELECT at FROM governance.rollout WHERE key = :k", k=ROLLOUT_KEY)
    if since is None or (now or datetime.now(UTC)) - since < GRACE:
        return ["expected_missing"]
    raise ApiError(
        422,
        "validation_failed",
        fields={
            "expected": "a proposal states {metric_fa, kpi?, baseline, target, by_days} (contract §20.6)"
        },
    )


async def on_sealed(tx: Tx, d: dict[str, Any]) -> list[str]:
    """The reviews of a sealed decision with `expected` (day 30, 60, 90 up to by_days)."""
    exp = d.get("expected")
    if not exp:
        return []
    refs = []
    for day in (x for x in DAYS if x <= int(exp["by_days"])):
        row = await tx.first(
            """INSERT INTO governance.outcome_reviews (company_id, decision_id, decision_ref, day, due_at, expected,
                   proposer_kind, proposer_code)
               VALUES (:co, :d, :ref, :day, now() + make_interval(days => :day), CAST(:e AS jsonb), :pk, :pc)
               ON CONFLICT (decision_id, day) DO NOTHING RETURNING ref""",
            co=d["company_id"],
            d=d["id"],
            ref=d["ref"],
            day=day,
            e=json.dumps(exp, ensure_ascii=False),
            pk=d["proposer_kind"],
            pc=d["proposer_code"],
        )
        if row:
            refs.append(row["ref"])
    return refs


# ---------------------------------------------------------------- verdict --
def verdict_of(baseline: float, target: float, value: float) -> str:
    if target >= baseline:
        if value >= target:
            return "met"
        return (
            "partly"
            if target > baseline and value >= baseline + (target - baseline) / 2
            else "missed"
        )
    if value <= target:
        return "met"
    return "partly" if value <= baseline - (baseline - target) / 2 else "missed"


async def _kpi_value(tx: Tx, company_id: UUID, key: str, upto: datetime) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT v.value, v.at, v.source_ref FROM governance.kpi_values v
           JOIN governance.kpis k ON k.id = v.kpi_id
           WHERE k.company_id = :co AND k.key = :key AND v.at <= :t ORDER BY v.at DESC LIMIT 1""",
        co=company_id,
        key=key,
        t=upto,
    )


async def measure_due(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """Every review that came due: a KPI's verdict by code, else
    `unmeasurable` (waiting for the proposer's note). outcome.due once."""
    now = now or datetime.now(UTC)
    rows = await tx.all(
        SQL
        + " WHERE r.status = 'due' AND r.verdict = 'pending' AND r.due_at <= :now ORDER BY r.due_at",
        now=now,
    )
    decided, waiting = [], []
    for r in rows:
        exp = r["expected"]
        v = await _kpi_value(tx, r["company_id"], exp["kpi"], now) if exp.get("kpi") else None
        if v is not None:
            verdict = verdict_of(float(exp["baseline"]), float(exp["target"]), float(v["value"]))
            measured = {
                "value": float(v["value"]),
                "at": v["at"].isoformat(),
                "source_ref": v["source_ref"],
            }
            await tx.exec(
                """UPDATE governance.outcome_reviews SET measured = CAST(:m AS jsonb), verdict = :v,
                       status = 'verified', decided_by_kind = 'rule', decided_by_code = 'PR-006', decided_at = now(),
                       due_emitted_at = coalesce(due_emitted_at, now()) WHERE id = :id""",
                m=json.dumps(measured, ensure_ascii=False),
                v=verdict,
                id=r["id"],
            )
            decided.append(r["ref"])
        else:
            await tx.exec(
                """UPDATE governance.outcome_reviews SET verdict = 'unmeasurable',
                       due_emitted_at = coalesce(due_emitted_at, now()) WHERE id = :id""",
                id=r["id"],
            )
            waiting.append(r["ref"])
        if r["due_emitted_at"] is None:
            await events.emit(
                tx, r["company"], "outcome.due", r["ref"],
                {"decision": r["decision_ref"], "day": r["day"], "proposer": r["proposer_code"],
                 "verdict": verdict if v is not None else "unmeasurable"},
            )  # fmt: skip
    return {"decided": decided, "waiting_for_note": waiting}


async def note(tx: Tx, who: Principal, body: OutcomeNoteIn) -> dict[str, Any]:
    """The proposer's note on a review that is due (outcome.note)."""
    r = await tx.first(SQL + " WHERE r.ref = :ref FOR UPDATE OF r", ref=body.ref)
    if r is None:
        raise ApiError(404, "not_found", f"no outcome review {body.ref}")
    if not who.is_owner and r["proposer_code"] != who.code:
        raise ApiError(403, "policy_denied", "only the proposer notes its outcome")
    if r["status"] == "verified":
        raise ApiError(409, "validation_failed", f"{body.ref} is verified ({r['verdict']})")
    if r["due_at"] > datetime.now(UTC):
        raise ApiError(409, "validation_failed", f"{body.ref} is due at {r['due_at'].isoformat()}")
    measured = body.measured.model_dump(mode="json") if body.measured else r["measured"]
    await tx.exec(
        """UPDATE governance.outcome_reviews SET proposer_note_md = :n, proposer_evidence = CAST(:ev AS jsonb),
               measured = CAST(:m AS jsonb), status = 'answered',
               verdict = CASE WHEN verdict = 'pending' THEN 'unmeasurable' ELSE verdict END
           WHERE id = :id""",
        n=body.note_md,
        ev=json.dumps([e.model_dump() for e in body.evidence], ensure_ascii=False),
        m=json.dumps(measured, ensure_ascii=False) if measured else None,
        id=r["id"],
    )
    return {"ref": body.ref, "status": "answered"}


async def overseer_verdicts(tx: Tx, who: Principal, items: list[OverseerVerdict]) -> list[str]:
    """PR-006: the overseer's verdict on answered reviews (protocol.result)."""
    done = []
    for v in items:
        r = await tx.first(SQL + " WHERE r.ref = :ref FOR UPDATE OF r", ref=v.ref)
        if r is None or r["status"] != "answered":
            raise ApiError(
                409, "validation_failed", fields={f"outcomes.{v.ref}": "only an answered review"}
            )
        await tx.exec(
            """UPDATE governance.outcome_reviews SET verdict = :v, overseer_note_md = :n, status = 'verified',
                   decided_by_kind = :bk, decided_by_code = :bc, decided_at = now() WHERE id = :id""",
            v=v.verdict,
            n=v.note_md,
            bk="agent" if who.is_agent else "owner",
            bc=who.code,
            id=r["id"],
        )
        done.append(v.ref)
    return done


# ------------------------------------------------------------------- read --
async def listing(
    tx: Tx,
    *,
    company_id: UUID | None,
    verdict: str | None,
    due: bool | None,
    decision: str | None,
    limit: int,
    after: tuple[datetime, UUID] | None,
) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await tx.all(
            SQL
            + """ WHERE (CAST(:co AS uuid) IS NULL OR r.company_id = :co)
                    AND (CAST(:v AS text) IS NULL OR r.verdict = :v)
                    AND (CAST(:d AS text) IS NULL OR r.decision_ref = :d)
                    AND (CAST(:due AS boolean) IS NULL
                         OR (CAST(:due AS boolean) AND r.status <> 'verified' AND r.due_at <= now())
                         OR (NOT CAST(:due AS boolean) AND (r.status = 'verified' OR r.due_at > now())))
                    AND (CAST(:at AS timestamptz) IS NULL
                         OR (r.due_at, r.id) > (CAST(:at AS timestamptz), CAST(:id AS uuid)))
                  ORDER BY r.due_at, r.id LIMIT :lim""",
            co=company_id,
            v=verdict,
            d=decision,
            due=due,
            at=after[0] if after else None,
            id=after[1] if after else None,
            lim=limit + 1,
        )
    ]


async def accuracy(tx: Tx, company_id: UUID | None = None) -> list[Accuracy]:
    """Prediction accuracy of every proposer (OPERATING_MODEL §1.16)."""
    rows = await tx.all(
        """SELECT r.proposer_kind, r.proposer_code, c.code AS company,
                  count(*) FILTER (WHERE r.verdict = 'met') AS met,
                  count(*) FILTER (WHERE r.verdict = 'partly') AS partly,
                  count(*) FILTER (WHERE r.verdict = 'missed') AS missed,
                  count(*) FILTER (WHERE r.verdict = 'unmeasurable') AS unmeasurable
           FROM governance.outcome_reviews r JOIN core.companies c ON c.id = r.company_id
           WHERE r.status = 'verified' AND (CAST(:co AS uuid) IS NULL OR r.company_id = :co)
           GROUP BY r.proposer_kind, r.proposer_code, c.code ORDER BY c.code, r.proposer_code""",
        co=company_id,
    )
    out = []
    for r in rows:
        decided = int(r["met"]) + int(r["partly"]) + int(r["missed"])
        who = actor(r["proposer_kind"], r["proposer_code"])
        assert who is not None
        out.append(
            Accuracy(
                proposer=who,
                company=r["company"],
                met=int(r["met"]),
                partly=int(r["partly"]),
                missed=int(r["missed"]),
                unmeasurable=int(r["unmeasurable"]),
                accuracy=round((int(r["met"]) + int(r["partly"]) / 2) / decided, 4)
                if decided
                else None,
            )
        )
    return out
