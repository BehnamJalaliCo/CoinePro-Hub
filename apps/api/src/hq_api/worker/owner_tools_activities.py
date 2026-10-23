"""Temporal activities of prompt 12 §2, §3, §13 (contract §21.2, §21.3, §21.10).

corpus_nightly    03:30 Tehran: the corpus of «از هاب بپرس», incremental (the
                  hub's repository from disk, each workspace's with the hub's
                  existing git access); no model
ask_sweep         every 5 min: an ask whose librarian run ended without
                  ask.answer is `failed`
weekly_review     every 15 min: skip what was not done by its next week, build
                  this week's agenda 30 minutes before its time (code), ask the
                  advisor for the one-page brief (advisor_review)
dceo_sweep        every 5 min: a missing baseline prediction; model predictions
                  of medium- and high-risk cards inside the day's cap
dceo_principles   Saturday 11:00 (owner zone): at most 5 proposed principles

Every one of them asks the launch gate first and does nothing while the
holding is locked: no git call, no row, no work, no model.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import ask, corpus, dceo, gate, reviews
from hq_api.hub import Hub


class OwnerToolsActivities:
    def __init__(self, hub: Hub, tx: Any, router: Any = None) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company
        self.router = router

    def all(self) -> list[Any]:
        return [
            self.corpus_nightly,
            self.ask_sweep,
            self.weekly_review,
            self.dceo_sweep,
            self.dceo_principles,
        ]

    @activity.defn(name="corpus_nightly")
    async def corpus_nightly(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.automation_lock(tx)) is not None:
                return gate.skipped(lock)
        return await corpus.build(self.hub, self._tx)

    @activity.defn(name="ask_sweep")
    async def ask_sweep(self) -> dict[str, Any]:
        return await ask.sweep(self.hub, self._tx)

    @activity.defn(name="weekly_review")
    async def weekly_review(self) -> dict[str, Any]:
        async with self._tx() as tx:
            return await reviews.tick(tx, self.hub)

    @activity.defn(name="dceo_sweep")
    async def dceo_sweep(self) -> dict[str, Any]:
        return await dceo.sweep(self.hub, self.router, self._tx)

    @activity.defn(name="dceo_principles")
    async def dceo_principles(self) -> dict[str, Any]:
        return await dceo.propose_principles(self.hub, self.router, self._tx)
