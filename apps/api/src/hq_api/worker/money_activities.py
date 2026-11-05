"""Temporal activities of money and sales (prompt 24, contract §33.1-§33.6).

money_read          every 2 h (hq-money-read): each payment source one step; rule-based
money_reconcile     daily 06:40 Tehran (hq-money-reconcile): the reconcile and its alerts
money_weekly        Saturday 09:05 Tehran (hq-money-weekly): the owner's one weekly line
money_read_source   the owner's read of one chain source (POST /payment-sources/{id}/read)
usage_report        daily 07:55 and Saturday 09:00 Tehran: the pack by code, ONE router call
                    (task class `usage_report`) for the words
sales_tick          every 15 min (hq-sales-tick): the leads' reminders (rule-based) and the
                    pending cards' impact (measured by code; one `decision_impact` call per
                    proposal or A3 card that has no measurable input)
affiliate_gaps      daily 07:20 Tehran (hq-affiliate-gaps): due against received; a follow-up
                    opened gets one `sales_followup` draft (never sent)

Every model call goes through llm-router (the worker's own client) with its own task class.
Nothing runs while the holding is locked; nothing moves money.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from temporalio import activity

from hq_api.domain import affiliate_gaps as AG
from hq_api.domain import gate
from hq_api.domain import impact as IM
from hq_api.domain import leads as L
from hq_api.domain import money_jobs as MJ
from hq_api.domain import usage as U
from hq_api.hub import Hub


class MoneyActivities:
    def __init__(self, hub: Hub, router: Any) -> None:
        self.hub = hub
        self.router = router

    def all(self) -> list[Any]:
        return [
            self.money_read,
            self.money_reconcile,
            self.money_weekly,
            self.money_read_source,
            self.usage_report,
            self.sales_tick,
            self.affiliate_gaps,
        ]

    async def ask(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """One router call (its task class in the request), answered as the api's
        OrderRouting answers: {"routes": ...}."""
        if not self.hub.secrets.llm_router_token:
            return None
        call = await self.router.run(req, int(req.get("timeout_s", 60)))
        if not call.ok:
            return None
        out = call.structured
        if out is None and call.text:
            try:
                out = json.loads(call.text)
            except ValueError:
                out = None
        return {"routes": out.get("routes")} if isinstance(out, dict) else None

    async def _locked(self) -> bool:
        async with self.hub.db.tx(await self.hub.companies.ids()) as tx:
            return await gate.holding_lock(tx) is not None

    @activity.defn(name="money_read")
    async def money_read(self) -> dict[str, Any]:
        return await MJ.read_due(self.hub)

    @activity.defn(name="money_reconcile")
    async def money_reconcile(self) -> dict[str, Any]:
        return await MJ.reconcile_all(self.hub)

    @activity.defn(name="money_weekly")
    async def money_weekly(self) -> dict[str, Any]:
        return await MJ.weekly(self.hub)

    @activity.defn(name="money_read_source")
    async def money_read_source(self, source_id: str) -> dict[str, Any]:
        return await MJ.read_one(self.hub, UUID(source_id))

    @activity.defn(name="usage_report")
    async def usage_report(self, period: str) -> dict[str, Any]:
        if period not in U.PERIODS:
            return {"skipped": "period"}
        if await self._locked():
            return {"skipped": "locked"}
        row = await U.make(self.hub, period, made_by="schedule", ask=self.ask)
        return {"ref": row["ref"], "words": row["words"]}

    @activity.defn(name="sales_tick")
    async def sales_tick(self) -> dict[str, Any]:
        if await self._locked():
            return {"skipped": "locked"}
        reminders = await L.tick(self.hub)
        impacts = await IM.sweep(self.hub, self.ask)
        return {**reminders, **impacts}

    @activity.defn(name="affiliate_gaps")
    async def affiliate_gaps(self) -> dict[str, Any]:
        return await AG.scan(self.hub, self.ask)
