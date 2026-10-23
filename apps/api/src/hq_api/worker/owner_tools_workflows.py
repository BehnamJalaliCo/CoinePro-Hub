"""Workflows of prompt 12 §2, §3, §13 (deterministic; the activities are in
owner_tools_activities.py and each asks the launch gate first)."""

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


@workflow.defn(name="CorpusNightly")
class CorpusNightly:
    """03:30 Tehran: the corpus of «از هاب بپرس» (prompt 12 §2.1)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("corpus_nightly", timedelta(minutes=60))


@workflow.defn(name="AskSweep")
class AskSweep:
    """Every 5 minutes: an ask whose run ended without an answer fails (§2.2)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("ask_sweep", timedelta(minutes=2))


@workflow.defn(name="WeeklyReviewTick")
class WeeklyReviewTick:
    """Every 15 minutes: the weekly review's agenda and brief (§3)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("weekly_review", timedelta(minutes=5))


@workflow.defn(name="DceoSweep")
class DceoSweep:
    """Every 5 minutes: the digital CEO's predictions (§13)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("dceo_sweep", timedelta(minutes=10))


@workflow.defn(name="DceoPrinciples")
class DceoPrinciples:
    """Saturday 11:00 (owner zone): the digital CEO's proposed principles (§13.5)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await _act("dceo_principles", timedelta(minutes=10))


OWNER_TOOLS_WORKFLOWS = [CorpusNightly, AskSweep, WeeklyReviewTick, DceoSweep, DceoPrinciples]
