"""Workflows of prompt 12 part B (deterministic; the activities are in
mgmt_activities.py and each asks the launch gate first)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=3)


async def _act(name: str, limit: timedelta) -> dict[str, Any]:
    out: dict[str, Any] = await workflow.execute_activity(
        name, start_to_close_timeout=limit, retry_policy=TRIES
    )
    return out


@workflow.defn(name="WasteDaily")
class WasteDaily:
    """07:45 (owner zone): yesterday's waste report (prompt 12 §8)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("waste_daily", timedelta(minutes=20))


@workflow.defn(name="CartableReminders")
class CartableReminders:
    """Every 15 minutes: the owner's waiting cards (prompt 12 §11)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("cartable_reminders", timedelta(minutes=5))


@workflow.defn(name="DeployRecheck")
class DeployRecheck:
    """Every 15 minutes: pending deploy cards still bound to the PR head (§7)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("deploy_recheck", timedelta(minutes=10))


@workflow.defn(name="HrRounds")
class HrRounds:
    """Daily 10:00 (owner zone): the monthly HR round on the 1st of a Jalali month (§6)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("hr_rounds", timedelta(minutes=20))


@workflow.defn(name="CeoLetters")
class CeoLetters:
    """Hourly: the CEOs' weekly letters at the owner's day and hour (§4.3)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("ceo_letters", timedelta(minutes=10))


P12B_WORKFLOWS = [WasteDaily, CartableReminders, DeployRecheck, HrRounds, CeoLetters]
