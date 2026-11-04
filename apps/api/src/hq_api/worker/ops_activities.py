"""Temporal activity of the ads and automations tick (prompt 22 part 3, contract
§31.6, §31.7). Rule-based: no model is called here (the model runs only once, in
the owner's own compile request).

ops_tick  every 5 minutes (hq-ops-tick): the ad rules over the campaigns the
          daily read stored, then the automations (schedules, metrics, events);
          nothing while the holding or a company is locked
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import ads as AD
from hq_api.domain import automations as AU
from hq_api.hub import Hub


class OpsActivities:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub

    def all(self) -> list[Any]:
        return [self.ops_tick]

    @activity.defn(name="ops_tick")
    async def ops_tick(self) -> dict[str, Any]:
        return {"ads": await AD.evaluate_due(self.hub), "automations": await AU.tick(self.hub)}
