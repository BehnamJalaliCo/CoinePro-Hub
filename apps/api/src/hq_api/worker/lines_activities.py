"""Temporal activities of the production lines (prompt 22, contract §30.3;
the engine is hq_api.lines.engine, the learning loop hq_api.lines.learning).

line_advance    one step of a run (the step's own timeout inside; a heartbeat
                every 20 s, so a worker that stops is noticed in two minutes)
lines_tick      every 5 minutes (hq-lines-tick): the schedules due, open runs
                no workflow moves, the 24h / 7d reads; only with HQ_LINES=on
                and nothing while the holding is locked
line_step_test  the owner's «آزمودن» of one step (nothing kept)
"""

from __future__ import annotations

import asyncio
from typing import Any

from temporalio import activity

from hq_api.hub import Hub
from hq_api.lines import engine

HEARTBEAT_S = 20


class LinesActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx

    def all(self) -> list[Any]:
        return [self.line_advance, self.lines_tick, self.line_step_test]

    @activity.defn(name="line_advance")
    async def line_advance(self, ref: str) -> dict[str, Any]:
        task = asyncio.ensure_future(engine.advance(self.hub, ref))
        while True:
            done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_S)
            if done:
                return task.result()
            activity.heartbeat()

    @activity.defn(name="lines_tick")
    async def lines_tick(self) -> dict[str, Any]:
        if not self.hub.settings.lines:  # HQ_LINES=off: no schedule runs yet (prompt 22)
            return {"skipped": "lines_off"}
        return await engine.tick(self.hub)

    @activity.defn(name="line_step_test")
    async def line_step_test(
        self, line_ref: str, key: str, given: dict[str, Any] | None
    ) -> dict[str, Any]:
        return await engine.test_step(self.hub, line_ref, key, given)
