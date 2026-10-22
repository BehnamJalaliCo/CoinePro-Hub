"""Control (contract §9, OPERATING_MODEL §1.12): kill switches and deploy
freezes. The holding switch (the holding company's row) stops every company:
the router refuses everything but P0, agent writes get 423, the worker
pauses agent workflows and the Code Workshop pauses the company's sessions
(contract §17.3 rule 5). The owner is never locked out."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.workshop import domain as workshop


class KillSwitch(BaseModel):
    scope: str
    company: str
    state: str
    reason: str | None
    changed_by: str | None
    changed_at: datetime


class Freeze(BaseModel):
    company: str
    until: datetime
    reason: str
    created_by: str


class ControlState(BaseModel):
    holding: KillSwitch
    companies: list[KillSwitch]
    deploy_freezes: list[Freeze]


def scope_of(row: dict[str, Any]) -> str:
    return "holding" if row["kind"] == "holding" else f"company:{row['code']}"


async def state(tx: Tx) -> ControlState:
    rows = await tx.all(
        """SELECT c.code, c.kind, COALESCE(k.state, 'released') AS state, k.reason, k.changed_by_code,
                  COALESCE(k.changed_at, c.created_at) AS changed_at
           FROM core.companies c LEFT JOIN control.kill_switches k ON k.company_id = c.id
           ORDER BY c.kind = 'holding' DESC, c.code"""
    )
    switches = [
        KillSwitch(
            scope=scope_of(r),
            company=r["code"],
            state=r["state"],
            reason=r["reason"],
            changed_by=r["changed_by_code"],
            changed_at=r["changed_at"],
        )
        for r in rows
    ]
    freezes = await tx.all(
        """SELECT c.code AS company, f.until, f.reason, f.created_by_code AS created_by
           FROM control.deploy_freezes f JOIN core.companies c ON c.id = f.company_id
           WHERE f.lifted_at IS NULL AND f.until > now() ORDER BY f.until"""
    )
    holding = next(s for s in switches if s.scope == "holding")
    return ControlState(
        holding=holding,
        companies=[s for s in switches if s.scope != "holding"],
        deploy_freezes=[Freeze(**f) for f in freezes],
    )


async def resolve_scope(tx: Tx, scope: str) -> dict[str, Any]:
    if scope == "holding":
        row = await tx.first("SELECT id, code, kind FROM core.companies WHERE kind = 'holding'")
    elif scope.startswith("company:"):
        row = await tx.first(
            "SELECT id, code, kind FROM core.companies WHERE code = :c AND kind = 'company'",
            c=scope[8:],
        )
    else:
        row = None
    if row is None:
        raise ApiError(422, "validation_failed", fields={"scope": "holding or company:<CODE>"})
    return row


async def set_kill_switch(
    tx: Tx, who: Principal, company: dict[str, Any], state_: str, reason: str
) -> bool:
    """Returns whether the state (or its owner) changed. Emits control.changed on
    the company (and, for the holding, on every company's subject so each stream
    sees it). The owner engaging a switch an agent engaged takes it over: from
    then on only the owner (with step-up) releases it. The Chief Overseer's
    engage takes it over the same way, unless the owner or the overseer holds
    it already (contract §18.15): a CEO that engaged first cannot release the
    overseer's switch."""
    cur = await tx.first(
        """SELECT k.state, k.changed_by_kind,
                  EXISTS (SELECT 1 FROM core.employees e
                          WHERE k.changed_by_kind = 'agent' AND e.code = k.changed_by_code
                            AND e.kind = 'overseer') AS by_overseer
           FROM control.kill_switches k WHERE k.company_id = :co FOR UPDATE OF k""",
        co=company["id"],
    )
    if cur is None:
        await tx.exec(
            "INSERT INTO control.kill_switches (company_id) VALUES (:co)", co=company["id"]
        )
        cur = {"state": "released", "changed_by_kind": None, "by_overseer": False}
    overseer = who.is_agent and who.role == "overseer"
    takeover = state_ == "engaged" and (
        (who.is_owner and cur["changed_by_kind"] != "owner")
        or (overseer and cur["changed_by_kind"] != "owner" and not cur["by_overseer"])
    )
    if cur["state"] == state_ and not takeover:
        return False
    await tx.exec(
        """UPDATE control.kill_switches SET state = :s, reason = :r, changed_by_kind = :k,
               changed_by_code = :c, changed_at = now()
           WHERE company_id = :co""",
        co=company["id"],
        s=state_,
        r=reason,
        k=who.kind,
        c=who.code,
    )
    data = {"kill_switch": state_, "scope": scope_of(company), "by": who.code}
    if company["kind"] == "holding":
        for c in await tx.all("SELECT code FROM core.companies ORDER BY code"):
            await events.emit(tx, c["code"], "control.changed", scope_of(company), data)
    else:
        await events.emit(tx, company["code"], "control.changed", scope_of(company), data)
    if state_ == "engaged":
        await workshop.pause_locked(tx)
    return True


async def active_freezes(tx: Tx, company_id: Any) -> list[dict[str, Any]]:
    """Active freezes with who set them (the setter's company for agents)."""
    return await tx.all(
        """SELECT f.id, f.until, f.created_by_kind, f.created_by_code,
                  (SELECT c.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id
                    WHERE f.created_by_kind = 'agent' AND e.code = f.created_by_code) AS created_by_company
           FROM control.deploy_freezes f
           WHERE f.company_id = :co AND f.lifted_at IS NULL AND f.until > now()
           ORDER BY f.created_at""",
        co=company_id,
    )


async def add_deploy_freeze(
    tx: Tx, who: Principal, company: dict[str, Any], until: datetime, reason: str
) -> None:
    """A new freeze; existing freezes of others stay (lifting follows authority)."""
    await tx.exec(
        """INSERT INTO control.deploy_freezes (company_id, until, reason, created_by_kind, created_by_code)
           VALUES (:co, :u, :r, :k, :c)""",
        co=company["id"],
        u=until,
        r=reason,
        k=who.kind,
        c=who.code,
    )
    await events.emit(
        tx,
        company["code"],
        "control.changed",
        f"company:{company['code']}",
        {"deploy_freeze_until": until.isoformat(), "by": who.code},
    )
    await workshop.pause_locked(tx)


async def lift_deploy_freezes(
    tx: Tx, who: Principal, company: dict[str, Any], ids: list[Any]
) -> int:
    """Lift exactly the freezes the caller has authority over (decided by the caller)."""
    if not ids:
        return 0
    n = await tx.exec(
        "UPDATE control.deploy_freezes SET lifted_at = now() WHERE id = ANY(:ids) AND lifted_at IS NULL",
        ids=ids,
    )
    left = await tx.scalar(
        """SELECT max(until) FROM control.deploy_freezes
           WHERE company_id = :co AND lifted_at IS NULL AND until > now()""",
        co=company["id"],
    )
    await events.emit(
        tx,
        company["code"],
        "control.changed",
        f"company:{company['code']}",
        {"deploy_freeze_until": left.isoformat() if left else None, "by": who.code},
    )
    return n


async def current_switch(tx: Tx, company_id: Any, *, lock: bool = False) -> dict[str, Any]:
    """The switch as it stands, with who set it (and that agent's company).
    `lock` holds the row until commit, so the authority the policy judged is
    still the one in force when the change is written."""
    row = await tx.first(
        """SELECT k.state, k.changed_by_kind, k.changed_by_code,
                  (SELECT c.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id
                    WHERE k.changed_by_kind = 'agent' AND e.code = k.changed_by_code) AS changed_by_company
           FROM control.kill_switches k WHERE k.company_id = :co"""  # noqa: S608 - constant clause below
        + (" FOR UPDATE OF k" if lock else ""),
        co=company_id,
    )
    return row or {
        "state": "released",
        "changed_by_kind": None,
        "changed_by_code": None,
        "changed_by_company": None,
    }
