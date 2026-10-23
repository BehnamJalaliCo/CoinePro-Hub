"""Temporal activities of prompt 11 §1-§3 (contract §20.1-§20.3).

meetings_tick    every minute (hq-meetings): plan the scheduled meetings,
                 prepare the agendas at T-24h, start, advance the live ones,
                 open and close war rooms, schedule postmortems, post the
                 standups. Each step in its own transaction; while the holding
                 is locked every step returns gate.skipped(lock) and does
                 nothing at all (no plan, no start, no turn run, no war room).
knowledge_daily  daily 06:30 (owner zone, hq-knowledge-daily): entries past
                 their `valid_until` become `expired` (rule-only: it runs while
                 the hub is locked); the review work 14 days before an expiry
                 wakes its keeper, so it waits while the holding is locked.
No model is called here; a turn's model call is its agent run's (refused by
the runner while locked).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from hq_api.domain import gate
from hq_api.domain import knowledge as K
from hq_api.domain import meeting_flow as MF
from hq_api.hub import Hub

log = logging.getLogger("hq_api.worker.meetings")


class MeetingActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.meetings_tick, self.knowledge_daily]

    @activity.defn(name="meetings_tick")
    async def meetings_tick(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        out: dict[str, Any] = {}
        for step in MF.STEPS:
            try:
                async with self._tx() as tx:
                    out[step] = await MF.tick_step(tx, step, now, self.hub.settings)
            except Exception:
                log.exception("meetings step failed", extra={"step": step})
                out[step] = {"error": True}
            if isinstance(out[step], dict) and out[step].get("skipped"):
                # Locked: the remaining steps would only say so again.
                return {"skipped": True, "reason": out[step]["reason"]}
        return out

    @activity.defn(name="knowledge_daily")
    async def knowledge_daily(self) -> dict[str, Any]:
        async with self._tx() as tx:
            lock = await gate.holding_lock(tx)
            out = await K.daily(tx, wake=lock is None)
        if lock is not None:
            out["review_reason"] = gate.REASONS.get(lock, lock)
        return out
