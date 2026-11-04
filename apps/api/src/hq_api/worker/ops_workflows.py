"""Workflow of the ads and automations tick (prompt 22 part 3, contract §31.6,
§31.7; the activity is in ops_activities.py and is rule-based: no model)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name="OpsTick")
class OpsTick:
    """Every 5 minutes: the ad rules, then the automations that are due."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "ops_tick", start_to_close_timeout=timedelta(minutes=4), retry_policy=TRIES
        )
        return out


OPS_WORKFLOWS = [OpsTick]
