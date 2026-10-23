"""The decision kinds of prompt 11 §5-§9 (contract §20.11, §20.12) and the
hooks domain/decisions.py calls for them.

okr               {objective: "OB-…", objectives: [OB-…], quarter} — made by
                  okr.draft; the owner may amend it (objective_changes,
                  key_result_changes); the seal makes the OKR active
risk_acceptance   {risk: "RK-…", until, score?} 🔏 — at most 90 days
authority_change  {changes: [{key, from, to: {actor?, limit?}}]} 🔏 — the api
                  writes `from` (the row now); the seal applies `to` if the
                  row is still `from` (else 409 decision_not_pending)
every kind        `expected` (gov_outcomes) and, for `deploy`, the calendar
                  (gov_calendar: window, calendar_conflicts)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from hq_api.db import Tx
from hq_api.domain import gov_authority as AU
from hq_api.domain import gov_calendar as CAL
from hq_api.domain import gov_common as G
from hq_api.domain import gov_okr as OKR
from hq_api.domain import gov_outcomes as OUT
from hq_api.domain import gov_risks as RK
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model

KINDS = ("okr", "risk_acceptance", "authority_change")
ACTION_CLASS = {"okr": "A1", "risk_acceptance": "A2", "authority_change": "A2"}
STEP_UP_KINDS = ("risk_acceptance", "authority_change")
SEALED_AS_IS = ("risk_acceptance", "authority_change")
OWNER = Principal(kind="owner", code="owner", role="owner")


class ObjectiveChange(Model):
    ref: str = Field(pattern=r"^OB-[0-9]{4,}$")
    title_fa: str | None = Field(default=None, min_length=1, max_length=300)


class KeyResultChange(Model):
    ref: str = Field(pattern=r"^KR-[0-9]{4,}$")
    title_fa: str | None = Field(default=None, min_length=1, max_length=300)
    target: float | None = Field(default=None, allow_inf_nan=False)
    weight: float | None = Field(default=None, gt=0, le=100)


class OkrPayload(Model):
    objective: str | dict[str, Any]
    objectives: list[str] = Field(default_factory=list, max_length=5)
    quarter: str = Field(pattern=G.QUARTER)
    # the owner's amendments (contract §20.5: an okr card may be amended)
    objective_changes: list[ObjectiveChange] | None = Field(default=None, max_length=5)
    key_result_changes: list[KeyResultChange] | None = Field(default=None, max_length=25)


class RiskAcceptancePayload(Model):
    risk: str = Field(pattern=r"^RK-[0-9]{4,}$")
    until: datetime
    score: int | None = Field(default=None, ge=1, le=25)


class AuthorityLimitTo(Model):
    actor: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    limit: dict[str, Any] | None = None


class AuthorityChangeItem(Model):
    # `from` (the row when the card was made) is written by the api: kept as
    # an extra key, rebuilt by check_proposal() from the row itself.
    model_config = ConfigDict(extra="allow")

    key: str = Field(pattern=r"^[a-z][a-z0-9_.]{1,60}$")
    to: AuthorityLimitTo


class AuthorityChangePayload(Model):
    changes: list[AuthorityChangeItem] = Field(min_length=1, max_length=20)


PAYLOADS: dict[str, type[Model]] = {
    "okr": OkrPayload,
    "risk_acceptance": RiskAcceptancePayload,
    "authority_change": AuthorityChangePayload,
}


# --------------------------------------------------------------- proposal --
async def check_proposal(
    tx: Tx, who: Principal, kind: str, payload: dict[str, Any], company_id: UUID
) -> dict[str, Any]:
    """The payload as the card keeps it (422 when it cannot be sealed)."""
    if kind == "risk_acceptance":
        await RK.check_acceptance(tx, company_id, payload)
        score = await tx.scalar(
            "SELECT score FROM governance.risks WHERE ref = :r AND company_id = :co",
            r=payload["risk"],
            co=company_id,
        )
        return {**payload, "score": int(score)}
    if kind == "authority_change":
        current = {r["key"]: r for r in await AU.rows(tx)}
        changes = []
        for c in payload["changes"]:
            r = current.get(c["key"])
            to = c.get("to") or {}
            AU.validate_change(
                r,
                AU.AuthorityRuleChange(
                    key=c["key"], actor=to.get("actor"), limit=to.get("limit"), version=1
                ),
            )
            assert r is not None
            changes.append(
                {"key": c["key"], "from": {"actor": r["actor"], "limit": r["lim"]}, "to": to}
            )
        return {"changes": changes}
    if (
        kind == "okr"
        and who.kind != "service"
        and not await tx.scalar(
            "SELECT 1 FROM governance.objectives WHERE ref = :r AND company_id = :co AND status = 'proposed'",
            r=payload.get("objective"),
            co=company_id,
        )
    ):
        raise ApiError(
            422, "validation_failed", fields={"kind": "an okr card comes from okr.draft"}
        )
    return payload


async def deploy_payload(
    tx: Tx, company_id: UUID, title: str, payload: dict[str, Any], risk: str, who: Principal
) -> tuple[dict[str, Any], str | None, Any]:
    """A deploy's window on the calendar and its conflicts in the payload
    (whatever the proposer wrote there) and the risk note's line."""
    win = payload.get("window")
    if win:
        a = datetime.fromisoformat(str(win["from"]).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(win["to"]).replace("Z", "+00:00"))
        if b <= a or (b - a).days > 7:
            raise ApiError(
                422, "validation_failed", fields={"payload.window": "from < to, at most 7 days"}
            )
    event, conflicts = await CAL.deploy_proposed(
        tx, company_id, title, payload, risk, ("agent" if who.is_agent else who.kind, who.code)
    )
    out = {**payload, "calendar_conflicts": [c.model_dump() for c in conflicts] if event else None}
    note = "; ".join(f"تداخل تقویم ({c.severity}): {c.note_fa}" for c in conflicts) or None
    return out, note, (event, conflicts)


# ------------------------------------------------------------------- seal --
async def apply(tx: Tx, d: dict[str, Any], amendments: dict[str, Any] | None) -> dict[str, Any]:
    """Applied in the deciding transaction (before the card is marked
    approved, so a refusal changes nothing)."""
    if d["kind"] in SEALED_AS_IS and amendments:
        raise ApiError(
            422, "validation_failed", fields={"amendments": "this card is sealed as it is"}
        )
    p = d["payload"] or {}
    if d["kind"] == "okr":
        changes = {
            "objectives": (amendments or {}).get("objective_changes") or [],
            "key_results": (amendments or {}).get("key_result_changes") or [],
        }
        return await OKR.on_decided(tx, d, "approved", changes)
    if d["kind"] == "risk_acceptance":
        return await RK.accept(tx, d, p)
    if d["kind"] == "authority_change":
        current = {r["key"]: r for r in await AU.rows(tx)}
        items = []
        for c in p.get("changes") or []:
            r = current.get(c["key"])
            if r is None or {"actor": r["actor"], "limit": r["lim"]} != c.get("from"):
                raise ApiError(
                    409, "decision_not_pending", f"{c['key']} changed since the card was made"
                )
            to = c.get("to") or {}
            items.append(
                AU.AuthorityRuleChange(
                    key=c["key"], actor=to.get("actor"), limit=to.get("limit"), version=r["version"]
                )
            )
        done = await AU.apply(tx, OWNER, items, decision_ref=d["ref"])
        return {"authority": [x["key"] for x in done]}
    return {}


async def after_decided(tx: Tx, d: dict[str, Any], verdict: str) -> dict[str, Any]:
    """After the card's verdict is written: the outcome reviews of a sealed
    card with `expected`, an okr card that was not sealed, a deploy's window."""
    out: dict[str, Any] = {}
    if verdict == "approved":
        fresh = await tx.one("SELECT * FROM cartable.decisions WHERE id = :id", id=d["id"])
        out["outcome_reviews"] = await OUT.on_sealed(tx, {**d, **dict(fresh)})
    if d["kind"] == "okr" and verdict != "approved":
        out["okr"] = await OKR.on_decided(tx, d, verdict, None)
    if d["kind"] == "deploy":
        await CAL.deploy_decided(tx, d, verdict)
    return out


async def stale_okr_cards(tx: Tx) -> int:
    """Objectives whose okr card expired or was withdrawn go back to draft."""
    return await tx.exec(
        """UPDATE governance.objectives o SET status = 'draft'
           FROM cartable.decisions d
           WHERE d.id = o.decision_id AND o.status = 'proposed' AND d.status IN ('expired', 'withdrawn')"""
    )
