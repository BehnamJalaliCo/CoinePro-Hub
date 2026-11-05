"""Workflows of money and sales (prompt 24, contract §33.1-§33.6; the activities are in
money_activities.py). The payments' reads and reconcile are rule-based; the usage report, the
affiliate drafts and the decisions' estimates are one router call each, in their own task class."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)
ONCE = RetryPolicy(maximum_attempts=1)


async def _one(name: str, minutes: int, *args: Any, retry: RetryPolicy = TRIES) -> dict[str, Any]:
    out: dict[str, Any] = await workflow.execute_activity(
        name,
        args=list(args),
        start_to_close_timeout=timedelta(minutes=minutes),
        retry_policy=retry,
    )
    return out


@workflow.defn(name="MoneyRead")
class MoneyRead:
    """Every 2 hours: each payment source one step (the chain scanned, the ledger's job)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _one("money_read", 50)


@workflow.defn(name="MoneyReconcile")
class MoneyReconcile:
    """Daily: every company with a source reconciled, its new problems alerted."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _one("money_reconcile", 30)


@workflow.defn(name="MoneyWeekly")
class MoneyWeekly:
    """Saturday: the owner's one weekly line of the payments."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _one("money_weekly", 5)


@workflow.defn(name="MoneyReadSource")
class MoneyReadSource:
    """The owner's read of one chain source, awaited by the api (no retry: the owner asks again)."""

    @workflow.run
    async def run(self, source_id: str) -> dict[str, Any]:
        return await _one("money_read_source", 8, source_id, retry=ONCE)


@workflow.defn(name="UsageReport")
class UsageReport:
    """The usage report of a period: daily 07:55 Tehran (its 3 lines reach the morning summary),
    weekly Saturday 09:00 (the advisor's thread)."""

    @workflow.run
    async def run(self, period: str) -> dict[str, Any]:
        return await _one("usage_report", 4, period)


@workflow.defn(name="SalesTick")
class SalesTick:
    """Every 15 minutes: the leads' reminders due; the pending cards' money impact."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _one("sales_tick", 12)


@workflow.defn(name="AffiliateGaps")
class AffiliateGaps:
    """Daily, after the revenue pull: commission due against received, the follow-ups."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _one("affiliate_gaps", 20)


MONEY_WORKFLOWS = [
    MoneyRead,
    MoneyReconcile,
    MoneyWeekly,
    MoneyReadSource,
    UsageReport,
    SalesTick,
    AffiliateGaps,
]
