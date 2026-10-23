"""Workflows of prompt 13, the legal and voice half (deterministic; the
activities are in legal_activities.py and each asks the launch gate first)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=2)


@workflow.defn(name="LegalMailPoll")
class LegalMailPoll:
    """Every 5 minutes: replies to the legal cases' emails (prompt 13 §3.2)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "legal_mail_poll", start_to_close_timeout=timedelta(minutes=4), retry_policy=TRIES
        )
        return out


@workflow.defn(name="VoiceBakeoff")
class VoiceBakeoff:
    """Daily: the bake-off samples still missing (prompt 13 §4.2)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "voice_bakeoff", start_to_close_timeout=timedelta(minutes=2), retry_policy=TRIES
        )
        return out


P13B_WORKFLOWS = [LegalMailPoll, VoiceBakeoff]
