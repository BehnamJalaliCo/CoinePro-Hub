"""Temporal activities of prompt 10 (contract §19). The later sections add
theirs here (revenue pulls, lifecycle sends, the feedback batch...), each
behind hq_api.domain.gate: while the holding (or the company) is locked an
activity that would call a model or an outside service returns
gate.skipped(lock) and does nothing else.

support_retention  daily 04:15 (owner zone): every text a customer wrote that
                   is older than SUPPORT_RETENTION_DAYS is removed; rows,
                   times, states and tags stay (prompt 10 §1.4). Rule-only (no
                   model, no outside call): it runs while the hub is locked.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import support
from hq_api.hub import Hub


class SupportActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.support_retention]

    @activity.defn(name="support_retention")
    async def support_retention(self) -> dict[str, Any]:
        days = self.hub.settings.support_retention_days
        async with self._tx() as tx:
            purged = await support.purge_texts(tx, days)
        return {"days": days, **purged}
