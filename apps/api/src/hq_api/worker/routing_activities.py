"""⟨1.11⟩ Prompt 21 part 1, the worker's side (rule-based, no model), run by
the Maintenance workflow every 5 minutes:

    order_tick      every open order's report (contract §29.2): its blockers,
                    its state, the 10-minute / 2-hour / 6-hour timers and the
                    talk-without-output stop
    tech_summary    the weekly technical summary (§29.1): Saturday 09:00 in
                    the owner's zone, once a week
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import order_report, tech_summary
from hq_api.hub import Hub


class RoutingActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.order_tick, self.tech_summary]

    @activity.defn(name="order_tick")
    async def order_tick(self) -> dict[str, Any]:
        return await order_report.tick(self.hub)

    @activity.defn(name="tech_summary")
    async def tech_summary(self) -> dict[str, Any]:
        async with self._tx() as tx:
            out = await tech_summary.run(tx)
        if out.get("notification") is not None:
            out["notification"] = str(out["notification"])
        return out
