"""Hiring: the owner opens it, the CEOs hire (contract §18.11, v1.4.2-1.4.3;
prompt 5.1 §1.3 and its review).

The state is one row of core.hiring for the holding (migration 0010); no
row reads "closed". While closed, an agent's hire proposal is refused before
any card exists (403 hiring_closed, here and in OPA hq.internal). The state
is read FOR SHARE in the proposing transaction, so a close committing
meanwhile waits for it and then withdraws the card it made. The owner opens
hiring in one of two modes:

  proposals  hiring opens to agents and the owner decides every card; each
             CEO (and each holding head with a hiring duty,
             seed/bootstrap/hiring_proposals.yaml) gets one work item
             "propose your first month's team" (a second start adds none)
  delegated  each CEO decides inside the company's monthly envelope: not
             served before prompt 8 (409 not_ready, nothing changes)

The owner hires directly in any state (POST /org/hires). Closing (always
safe, no step-up) withdraws every pending hire card through
cartable.withdraw_pending_hires, the same function the migration used.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import bootstrap, events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor
from hq_api.worker.jalali import to_jalali

NOTE = "مالک: استخدام با شروع خود مالک"
PROPOSALS_KEY = "hiring_proposals"

Mode = Literal["proposals", "delegated"]  # proposals first: the one served (examples)


class Envelope(BaseModel):
    """One operating company's monthly token envelope (contract §18.11)."""

    company: str
    tokens_month: int | None  # the company's monthly budget (llm.budgets), if set
    committed_month: int  # monthly estimates of its active employees' hire cards
    used_month: int  # tokens used this Jalali month
    hires_month: int  # hire cards approved this Jalali month


class Hiring(BaseModel):
    state: Literal["closed", "open"]
    mode: Mode | None
    changed_at: datetime | None
    changed_by: Actor | None
    withdrawn: list[str]
    envelopes: list[Envelope] = Field(default_factory=list)


async def state(tx: Tx) -> str:
    """ "open" or "closed" for any caller (a definer function: an agent's own
    company-scoped transaction cannot see the holding's row)."""
    value: str | None = await tx.scalar("SELECT core.hiring_state()")
    return value or "closed"


async def require_open(tx: Tx, who: Principal, kind: str) -> None:
    """An agent's hire proposal while hiring is closed: 403 hiring_closed. The
    holding's row is read FOR SHARE: a concurrent close (an UPDATE of it)
    waits for this transaction and then withdraws the card it made."""
    if kind != "hire" or not who.is_agent:
        return
    if await tx.scalar("SELECT core.hiring_state_for_share()") != "open":
        raise ApiError(403, "hiring_closed")


def require_mode(mode: str) -> None:
    """`delegated` (each CEO hires inside its envelope) arrives with prompt 8;
    until then it changes nothing (checked before any step-up is consumed)."""
    if mode == "delegated":
        raise ApiError(409, "not_ready", "delegated hiring arrives with prompt 8")


def jalali_month_start(today: date) -> date:
    """The Gregorian date of the first day of today's Jalali month."""
    _, _, day = to_jalali(today)
    return today - timedelta(days=day - 1)


async def envelopes(tx: Tx) -> list[Envelope]:
    """Every active operating company's envelope (contract §18.11)."""
    start = jalali_month_start(datetime.now(UTC).date())
    rows = await tx.all(
        """SELECT c.code,
                  (SELECT b.token_limit FROM llm.budgets b
                    WHERE b.company_id = c.id AND b.scope_type = 'company' AND b.scope_ref = c.code
                      AND b.period = 'month' AND b.enabled) AS tokens_month,
                  (SELECT COALESCE(sum(COALESCE((d.payload->'quota_estimate_month'->>'tokens')::bigint,
                                                d.quota_tokens, 0)), 0)
                     FROM core.employees e JOIN cartable.decisions d ON d.id = e.hired_by_decision_id
                    WHERE e.company_id = c.id AND e.status = 'active') AS committed_month,
                  (SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                                       + COALESCE(k.cache_read_tokens, 0)
                                       + COALESCE(k.cache_write_tokens, 0)), 0)
                     FROM llm.calls k WHERE k.company_id = c.id AND k.started_at >= :start) AS used_month,
                  (SELECT count(*) FROM cartable.decisions d
                    WHERE d.company_id = c.id AND d.kind = 'hire' AND d.status = 'approved'
                      AND d.decided_at >= :start) AS hires_month
           FROM core.companies c WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code""",
        start=datetime.combine(start, time.min, tzinfo=UTC),
    )
    return [
        Envelope(
            company=r["code"],
            tokens_month=int(r["tokens_month"]) if r["tokens_month"] is not None else None,
            committed_month=int(r["committed_month"]),
            used_month=int(r["used_month"]),
            hires_month=int(r["hires_month"]),
        )
        for r in rows
    ]


async def load(tx: Tx, holding_id: UUID) -> Hiring:
    row = await tx.first(
        """SELECT state, mode, changed_at, changed_by_kind, changed_by_code, withdrawn
           FROM core.hiring WHERE company_id = :co""",
        co=holding_id,
    )
    env = await envelopes(tx)
    if row is None:
        return Hiring(
            state="closed", mode=None, changed_at=None, changed_by=None, withdrawn=[], envelopes=env
        )
    return Hiring(
        state=row["state"],
        mode=row["mode"],
        changed_at=row["changed_at"],
        changed_by=actor(row["changed_by_kind"], row["changed_by_code"]),
        withdrawn=list(row["withdrawn"] or []),
        envelopes=env,
    )


async def _set(tx: Tx, holding_id: UUID, who: Principal, state_: str, mode: str | None) -> None:
    await tx.exec(
        """INSERT INTO core.hiring (company_id) VALUES (:co) ON CONFLICT (company_id) DO NOTHING""",
        co=holding_id,
    )
    await tx.exec(
        """UPDATE core.hiring SET state = :st, mode = :mode, changed_at = now(),
               changed_by_kind = :k, changed_by_code = :c
           WHERE company_id = :co""",
        co=holding_id,
        st=state_,
        mode=mode,
        k="owner" if who.is_owner else "service",
        c=who.code,
    )


async def withdraw_pending(tx: Tx) -> list[str]:
    refs = await tx.scalar("SELECT cartable.withdraw_pending_hires(:note)", note=NOTE)
    return list(refs or [])


async def start(
    tx: Tx,
    who: Principal,
    *,
    holding_id: UUID,
    holding_code: str,
    mode: Mode,
    charters: Any,
) -> dict[str, Any]:
    """Open hiring in mode `proposals` (the only one served before prompt 8)."""
    require_mode(mode)
    await _set(tx, holding_id, who, "open", mode)
    out = await bootstrap.apply(tx, bootstrap.load(PROPOSALS_KEY), who=who, charters=charters)
    work: list[dict[str, str]] = out["created"]
    await events.emit(
        tx, holding_code, "hiring.changed", None, {"state": "open", "mode": mode, "work": work}
    )
    return {"work": work}


async def close(tx: Tx, who: Principal, *, holding_id: UUID, holding_code: str) -> list[str]:
    """Close hiring; pending hire cards are withdrawn (never deleted)."""
    await _set(tx, holding_id, who, "closed", None)
    refs = await withdraw_pending(tx)
    await events.emit(
        tx,
        holding_code,
        "hiring.changed",
        None,
        {"state": "closed", "mode": None, "withdrawn": refs},
    )
    return refs
