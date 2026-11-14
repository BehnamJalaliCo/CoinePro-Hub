"""⟨2026-11-14⟩ The owner's switch on the work the hub starts by itself (owner.settings.self_work).

The owner: «من میترسم چیزی رو ست بکنم که با یه ست کردن کل لیمیت هفتگی من میپره، استفاده های
الکی و بیمورد در هاب هلدینگ آپ». Two days of the ledger: about $20 a day of agent runs nobody
asked for (the groups' daily plans, the catalogue watch's memos, the advisor, alerts, scheduled
meetings, hiring, stars, substitutes, works one agent opened for another). Off: an agent run starts
only for what the owner asked for; everything else is refused at its claim (`owner_only`, no model
call) and its open work cancelled with the reason in Persian. Nothing is deleted; on again, the
schedules go on as before.

What the owner asked for:
- `talk` and `message`: his conversation with an employee, his word in an employee's thread;
- `direct`: a turn of one of his sessions (the holder's own, on the workshop);
- `meeting`: a meeting he called (`meetings.meetings.created_by_kind = 'owner'`);
- `work` and the rest: a work whose chain leads to his order: its root made by him (an order's
  root, a flow's day), or, a root another employee opened, the work that asked for it
  (`requested_by_work_id`), followed up to a few hops.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.principal import Principal

REFUSED = "owner_only"
CLOSE_REASON = "work the hub started by itself is off (owner's switch): only his own orders run"
HOPS = 6


async def on(tx: Tx) -> bool:
    got = await tx.scalar("SELECT self_work FROM owner.settings WHERE id = 1")
    return got is None or bool(got)


async def owner_rooted(tx: Tx, work_id: UUID | str) -> bool:
    """Whether a work's chain leads to the owner (his order's root, or what asked for it)."""
    seen: set[str] = set()
    current: str | None = str(work_id)
    for _ in range(HOPS):
        if current is None or current in seen:
            return False
        seen.add(current)
        row = await tx.first(
            """SELECT r.created_by_kind AS root_by,
                      COALESCE(r.requested_by_work_id, w.requested_by_work_id) AS asked_by
               FROM work.work w JOIN work.work r ON r.id = w.root_id
               WHERE w.id = CAST(:w AS uuid)""",
            w=current,
        )
        if row is None:
            return False
        if row["root_by"] == "owner":
            return True
        current = str(row["asked_by"]) if row["asked_by"] is not None else None
    return False


async def asked_by_owner(tx: Tx, run: dict[str, Any]) -> bool:
    trigger = str(run.get("trigger") or "")
    if trigger in ("talk", "message"):
        return True
    if trigger == "meeting":
        ref = str(run.get("reason") or "").split(":")
        if len(ref) < 2:
            return False
        by = await tx.scalar(
            "SELECT created_by_kind FROM meetings.meetings WHERE ref = :r", r=ref[1]
        )
        return bool(by == "owner")
    if run.get("work_id") is None:
        return trigger == "direct"
    return await owner_rooted(tx, run["work_id"])


async def refuse(tx: Tx, run: dict[str, Any]) -> bool:
    """True when the switch is off and this run was not asked for by the owner."""
    if await on(tx):
        return False
    return not await asked_by_owner(tx, run)


async def close_work(tx: Tx, work_id: UUID | str | None) -> None:
    """The refused run's work, still open, is cancelled (its record stays)."""
    if work_id is None:
        return
    from hq_api.domain import work as W

    w = await tx.first(
        "SELECT * FROM work.work WHERE id = CAST(:w AS uuid) FOR UPDATE", w=str(work_id)
    )
    if w is None or w["status"] not in W.OPEN:
        return
    await tx.exec(
        """UPDATE work.work SET status = 'cancelled', close_reason = :why, closed_at = now()
           WHERE id = :id""",
        id=w["id"],
        why=CLOSE_REASON,
    )
    await W.event(tx, dict(w), "cancelled", SERVICE, {"why": REFUSED})


SERVICE = Principal(kind="service", code="self_work", role="service")


async def set_on(tx: Tx, who: Principal, value: bool, why: str = "") -> bool:
    """The owner's switch (his word in chat or his tap): True when it changed."""
    before = await on(tx)
    if before == value:
        return False
    await tx.exec("UPDATE owner.settings SET self_work = :v WHERE id = 1", v=value)
    holding = await tx.one("SELECT id FROM core.companies WHERE kind = 'holding'")
    await audit.record(
        tx, who, company_id=holding["id"], action="hub.self_work", action_class="A2",
        target_kind="owner_settings", target_ref="self_work",
        summary=f"{'on' if before else 'off'} -> {'on' if value else 'off'}"
        + (f": {why}" if why else ""),
    )  # fmt: skip
    return True
