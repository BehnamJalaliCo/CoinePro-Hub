"""Temporal activities of prompt 10 §2, §3 and §8 (the revenue and growth half).

revenue_plan(kind)   07:00 Tehran `scheduled` / 11:00 and 18:00 `retry`: the
                     pulls to carry out (domain/revenue.plan_pulls); while the
                     holding is locked each account gets one `skipped` row at
                     07:00 and nothing else happens
revenue_pull(id)     one pull, a settled day at a time, through the gateway's
                     connector (domain/affiliate.GatewayConnector); asks the
                     gate again before every day
rescue_follow_ups    hourly: due rescue cases, under a sealed rescue rule, by
                     the §7 sender only (domain/rescue.py)
feedback_batch       nightly: pending feedback signals, one light-model call
                     per company through llm-router (domain/feedback.py)
support_weekly       Saturday: the week's support figures to the support lead

Every one of them asks hq_api.domain.gate first: while the holding (or the
company) is locked there is no model call, no outside call and no new run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity

from hq_api.domain import affiliate as A
from hq_api.domain import feedback as FB
from hq_api.domain import gate
from hq_api.domain import rescue as R
from hq_api.domain import revenue as V
from hq_api.hub import Hub

STALE_RUNNING = timedelta(hours=4)  # a pull whose activity died


class RevenueActivities:
    def __init__(
        self,
        hub: Hub,
        tx: Any,
        *,
        router: Any = None,
        connector: A.Connector | None = None,
    ) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company
        self.router = router
        s = hub.settings
        self.connector: A.Connector = connector or A.GatewayConnector(
            s.gateway_url,
            lambda: self.hub.secrets.gateway_token,
            lambda: self.hub.secrets.worker_api_token,
        )

    def all(self) -> list[Any]:
        return [
            self.revenue_plan,
            self.revenue_pull,
            self.rescue_follow_ups,
            self.feedback_batch,
            self.support_weekly,
        ]

    @activity.defn(name="revenue_plan")
    async def revenue_plan(self, kind: str) -> dict[str, Any]:
        if kind not in ("scheduled", "retry"):
            raise ValueError(f"unknown pull kind {kind}")
        async with self._tx() as tx:
            await tx.exec(
                """UPDATE revenue.pulls SET state = 'failed', error_code = 'interrupted', finished_at = now()
                   WHERE state = 'running' AND started_at < :t""",
                t=datetime.now(UTC) - STALE_RUNNING,
            )
            lock = await gate.holding_lock(tx)
            rows = await V.plan_pulls(
                tx, kind, backfill_days=self.hub.settings.revenue_backfill_days
            )
        queued = [str(r["id"]) for r in rows if r["state"] == "queued"]
        skipped = [str(r["id"]) for r in rows if r["state"] == "skipped"]
        out: dict[str, Any] = {"kind": kind, "queued": queued, "skipped_pulls": skipped}
        if lock is not None:
            out.update(gate.skipped(lock))
        return out

    @activity.defn(name="revenue_pull")
    async def revenue_pull(self, pull_id: str) -> dict[str, Any]:
        return await V.run_pull(self.hub, self._tx, self.connector, pull_id)

    @activity.defn(name="rescue_follow_ups")
    async def rescue_follow_ups(self) -> dict[str, Any]:
        return await R.follow_ups(self.hub, self._tx)

    @activity.defn(name="feedback_batch")
    async def feedback_batch(self) -> dict[str, Any]:
        return await FB.batch(self.hub, self._tx, self.router)

    @activity.defn(name="support_weekly")
    async def support_weekly(self) -> dict[str, Any]:
        return await FB.weekly(self.hub, self._tx)
