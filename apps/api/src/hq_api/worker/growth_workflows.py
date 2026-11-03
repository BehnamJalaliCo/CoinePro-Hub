"""Workflows of the working groups, the connections and the owner's home
(prompt 21 part 3, contract §29.11-§29.13; the activities are in
growth_activities.py and are rule-based: no model)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name="GroupsTick")
class GroupsTick:
    """Every 10 minutes: the group files, their members, the routines due."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "groups_tick", start_to_close_timeout=timedelta(minutes=8), retry_policy=TRIES
        )
        return out


@workflow.defn(name="ConnectionsRead")
class ConnectionsRead:
    """Hourly: each connection's daily read (once a day), IG-Hub's jobs collected."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "connections_read", start_to_close_timeout=timedelta(minutes=25), retry_policy=TRIES
        )
        return out


@workflow.defn(name="ConnectionTest")
class ConnectionTest:
    """The owner's «آزمودن»: one connection read now."""

    @workflow.run
    async def run(self, company_id: str, kind: str) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "connection_test",
            args=[company_id, kind],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return out


@workflow.defn(name="HomeMorning")
class HomeMorning:
    """08:00 the owner's time: suggestions, progress and the morning's lines."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "home_morning", start_to_close_timeout=timedelta(minutes=10), retry_policy=TRIES
        )
        return out


GROWTH_WORKFLOWS = [GroupsTick, ConnectionsRead, ConnectionTest, HomeMorning]
