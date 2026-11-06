"""Temporal activities of prompt 12 part B (contract §21.4-§21.8).

waste_daily        07:45 owner zone: yesterday's waste (code); on Saturday a
                   `report` notification for the technical handler of each
                   company whose week was above a 15% share
cartable_reminders every 15 min: the owner's waiting cards, each threshold once
deploy_recheck     every 15 min: a pending deploy card whose PR branch moved
                   is set aside (git ls-remote with the hub's existing access)
hr_rounds          daily 10:00 owner zone: on the 1st of a Jalali month the
                   monthly HR round of every active operating company and the
                   holding; rounds whose cards are all decided are closed
ceo_letters        hourly: at the owner's day and hour (default Saturday
                   09:00) one letter work item per company's CEO

Every one of them asks the launch gate first (hq_api.domain.gate) and does
nothing while the holding is locked: no work, no notification, no git call,
no model. A rule-only figure in an existing report (the morning report's
waste and reminder lines) is not one of them.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from temporalio import activity

from hq_api.domain import briefings, deploy_diff, gate, hr, notes, notify
from hq_api.domain import decisions as D
from hq_api.domain import waste as WASTE
from hq_api.hub import Hub
from hq_api.worker.jalali import to_jalali

log = logging.getLogger("hq_api.worker.mgmt")


class MgmtActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [
            self.waste_daily,
            self.cartable_reminders,
            self.deploy_recheck,
            self.hr_rounds,
            self.ceo_letters,
        ]

    async def _zone(self, tx: Any) -> ZoneInfo:
        tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
        return ZoneInfo(str(tz))

    async def _push(self, rows: list[dict[str, Any]]) -> None:
        ids = [r["id"] for r in rows if r.get("push_now")]
        if ids:
            await notify.deliver_pending(self.hub, ids)

    # ------------------------------------------------------------- waste --
    @activity.defn(name="waste_daily")
    async def waste_daily(self, day: str | None = None) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            zone = await self._zone(tx)
            d = date.fromisoformat(day) if day else datetime.now(zone).date() - timedelta(days=1)
            rows = await WASTE.store(tx, d)
            pushed = []
            # The alert once a week (2026-11-06: no daily system notice), on the day
            # that ends the owner's week (Friday's figures, read on Saturday):
            # each company's share of the week, for its technical handler.
            if d.weekday() == 4:
                start = d - timedelta(days=6)
                shares = await WASTE.shares_between(tx, start, d + timedelta(days=1))
                for co, share in shares.items():
                    if share is None or share <= WASTE.ALERT_SHARE:
                        continue
                    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=co)
                    pushed.append(
                        await notify.raise_notification(
                            tx,
                            company_id=co,
                            company_code=str(code),
                            level="report",
                            title_fa=f"هدررفت هفته‌ی {code}: {round(share * 100, 1)}%",
                            body_fa=f"از {start.isoformat()} تا {d.isoformat()}",
                            link_kind="treasury",
                            link_ref=f"waste:{d.isoformat()}",
                            source_kind="system",
                            source_code="waste",
                            domain="infra",
                        )
                    )
        await self._push(pushed)
        return {"day": d.isoformat(), "rows": len(rows), "alerts": len(pushed)}

    # --------------------------------------------------------- reminders --
    @activity.defn(name="cartable_reminders")
    async def cartable_reminders(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            raised = await notes.remind(tx)
        await self._push(raised)
        return {"reminded": [f"{r['decision']}:{r['kind']}" for r in raised]}

    # ------------------------------------------------------------ deploy --
    @activity.defn(name="deploy_recheck")
    async def deploy_recheck(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            cards = await tx.all(
                D.DECISION_SQL
                + " WHERE d.kind = 'deploy' AND d.status = 'pending' AND d.payload ? 'head_sha'"
                " ORDER BY d.created_at"
            )
        aside: list[str] = []
        for d in cards:
            now_sha = await deploy_diff.head_now(self.hub, d["payload"], d["company_id"])
            if not deploy_diff.moved(d["payload"], now_sha):
                continue
            async with self._tx() as tx:
                if await deploy_diff.set_aside(tx, d, str(now_sha)):
                    aside.append(d["ref"])
        if aside:
            from hq_api import workflows_client

            for ref in aside:  # its DecisionLifecycle sees it is no longer pending and ends
                try:
                    await workflows_client.decision_decided(self.hub, ref)
                except Exception:  # noqa: BLE001 - reconcile_decisions catches up
                    log.warning("could not signal %s", ref)
        return {"checked": len(cards), "set_aside": aside}

    # ---------------------------------------------------------------- HR --
    @activity.defn(name="hr_rounds")
    async def hr_rounds(self, day: str | None = None) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            zone = await self._zone(tx)
            today = date.fromisoformat(day) if day else datetime.now(zone).date()
            closed = await hr.close_rounds(tx)
            if to_jalali(today)[2] != hr.FIRST_DAY:
                return {"opened": [], "closed": closed}
            opened = []
            companies = await tx.all(
                """SELECT id, code, kind FROM core.companies
                   WHERE status = 'active' AND kind IN ('company', 'holding') ORDER BY kind DESC, code"""
            )
            for c in companies:
                if c["kind"] == "company" and await gate.automation_lock(tx, c["id"]) is not None:
                    continue
                r = await hr.open_round(tx, dict(c), today, zone)
                if r:
                    opened.append(r)
        return {"opened": opened, "closed": closed, "day": today.isoformat()}

    # ----------------------------------------------------------- letters --
    @activity.defn(name="ceo_letters")
    async def ceo_letters(self, at: str | None = None) -> dict[str, Any]:
        async with self._tx() as tx:
            now = datetime.fromisoformat(at) if at else datetime.now(UTC)
            return await briefings.letters(tx, now)

    # The morning report has no voice for the owner any more (the owner's rule of
    # 2026-11-06): it is the head of AI operations' report; briefings.morning stays
    # for a spoken text of the owner's own.
