"""Hiring starts with the owner (contract §18.11, prompt 5.1 §1.3).

The state is one row of core.hiring for the holding (migration 0010); no
row reads "closed". While closed, an agent's hire proposal is refused before
any card exists (403 hiring_closed, here and in OPA hq.internal). The owner
opens it in one of two modes:

  proposals  hiring opens to agents and each CEO (and each holding head with a
             hiring duty, seed/bootstrap/hiring_proposals.yaml) gets one work
             item "propose your first month's team" (a second start adds none)
  self       hiring stays closed to agents; the owner hires directly
             (POST /org/hires)

Closing (always safe, no step-up) withdraws every pending hire card through
cartable.withdraw_pending_hires, the same function the migration used.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api import bootstrap, events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

NOTE = "مالک: استخدام با شروع خود مالک"
PROPOSALS_KEY = "hiring_proposals"


class Hiring(BaseModel):
    state: Literal["closed", "open"]
    mode: Literal["self", "proposals"] | None
    changed_at: datetime | None
    changed_by: Actor | None
    withdrawn: list[str]


async def state(tx: Tx) -> str:
    """ "open" or "closed" for any caller (a definer function: an agent's own
    company-scoped transaction cannot see the holding's row)."""
    value: str | None = await tx.scalar("SELECT core.hiring_state()")
    return value or "closed"


async def require_open(tx: Tx, who: Principal, kind: str) -> None:
    """An agent's hire proposal while hiring is closed: 403 hiring_closed."""
    if kind == "hire" and who.is_agent and await state(tx) != "open":
        raise ApiError(403, "hiring_closed")


async def load(tx: Tx, holding_id: UUID) -> Hiring:
    row = await tx.first(
        """SELECT state, mode, changed_at, changed_by_kind, changed_by_code, withdrawn
           FROM core.hiring WHERE company_id = :co""",
        co=holding_id,
    )
    if row is None:
        return Hiring(state="closed", mode=None, changed_at=None, changed_by=None, withdrawn=[])
    return Hiring(
        state=row["state"],
        mode=row["mode"],
        changed_at=row["changed_at"],
        changed_by=actor(row["changed_by_kind"], row["changed_by_code"]),
        withdrawn=list(row["withdrawn"] or []),
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
    mode: Literal["self", "proposals"],
    charters: Any,
) -> dict[str, Any]:
    """Open hiring (proposals) or keep it closed to agents (self)."""
    await _set(tx, holding_id, who, "open" if mode == "proposals" else "closed", mode)
    work: list[dict[str, str]] = []
    if mode == "proposals":
        out = await bootstrap.apply(tx, bootstrap.load(PROPOSALS_KEY), who=who, charters=charters)
        work = out["created"]
    await events.emit(
        tx,
        holding_code,
        "hiring.changed",
        None,
        {"state": "open" if mode == "proposals" else "closed", "mode": mode, "work": work},
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
