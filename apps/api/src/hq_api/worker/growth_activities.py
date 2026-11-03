"""Temporal activities of the working groups, the connections and the
owner's home (prompt 21 part 3, contract §29.11-§29.13). Rule-based: no
model is called here (the model runs only in the employees' own runs).

groups_tick       every 10 minutes (hq-groups-tick): the group files, the
                  members (a new eligible company joins), empty seats asked
                  of automatic hiring, the routines due -> one work item each;
                  nothing while the holding is locked
connections_read  hourly (hq-connections-read): each connection's daily read
                  through egress, IG-Hub's runner jobs; the hub's own figures;
                  nothing while the holding is locked
connection_test   the owner's «آزمودن» (one read now; the launch gate is
                  checked by the read itself)
home_morning      08:00 the owner's time (hq-home-morning): suggestions,
                  progress, the morning's 5 lines (no outside call)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from temporalio import activity

from hq_api.domain import connections as CN
from hq_api.domain import groups as GR
from hq_api.domain import home as HM
from hq_api.hub import Hub


class GrowthActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx

    def all(self) -> list[Any]:
        return [self.groups_tick, self.connections_read, self.connection_test, self.home_morning]

    @activity.defn(name="groups_tick")
    async def groups_tick(self) -> dict[str, Any]:
        if not self.hub.settings.groups:  # HQ_GROUPS=off: nothing runs yet (prompt 21's step 2)
            return {"skipped": "groups_off"}
        return await GR.tick(self.hub)

    @activity.defn(name="connections_read")
    async def connections_read(self) -> dict[str, Any]:
        return await CN.read_due(self.hub)

    @activity.defn(name="connection_test")
    async def connection_test(self, company_id: str, kind: str) -> dict[str, Any]:
        after = await CN.read_one(self.hub, UUID(company_id), kind)
        return {"state": after.get("state"), "error": bool(after.get("last_error_fa"))}

    @activity.defn(name="home_morning")
    async def home_morning(self) -> dict[str, Any]:
        return await HM.morning_tick(self.hub)
