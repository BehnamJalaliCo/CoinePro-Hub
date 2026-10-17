"""Control (contract §9, OPERATING_MODEL §1.12): kill switches and deploy
freezes. The holding switch (the holding company's row) stops every company:
the router refuses everything but P0, agent writes get 423 and the worker
pauses agent workflows. The owner is never locked out."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal


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
    """Returns whether the state changed. Emits control.changed on the company
    (and, for the holding, on every company's subject so each stream sees it)."""
    cur = await tx.first(
        "SELECT state FROM control.kill_switches WHERE company_id = :co FOR UPDATE",
        co=company["id"],
    )
    if cur is None:
        await tx.exec(
            "INSERT INTO control.kill_switches (company_id) VALUES (:co)", co=company["id"]
        )
        cur = {"state": "released"}
    if cur["state"] == state_:
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
    return True


async def set_deploy_freeze(
    tx: Tx, who: Principal, company: dict[str, Any], until: datetime, reason: str
) -> dict[str, Any]:
    """`until` in the future sets/extends a freeze; in the past lifts them."""
    lifted = await tx.exec(
        """UPDATE control.deploy_freezes SET lifted_at = now()
           WHERE company_id = :co AND lifted_at IS NULL""",
        co=company["id"],
    )
    active = await tx.scalar("SELECT :u > now()", u=until)
    if active:
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
        {"deploy_freeze_until": until.isoformat() if active else None, "by": who.code},
    )
    return {"active": bool(active), "replaced": lifted}
