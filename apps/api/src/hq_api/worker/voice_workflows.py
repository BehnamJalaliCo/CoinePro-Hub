"""Workflows of the voice layer (prompt 23, contract §32.5; the activities are in
voice_activities.py)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

ONCE = RetryPolicy(maximum_attempts=1)


@workflow.defn(name="VoiceCall")
class VoiceCall:
    """One provider call for the api (a sentence, or a metadata call); no retry: a sentence that
    fails moves on to the next engine of the chain at once."""

    @workflow.run
    async def run(self, op: str, args_json: str) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "voice_call",
            args=[op, args_json],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=ONCE,
        )
        return out


@workflow.defn(name="VoiceCheck")
class VoiceCheck:
    """The light's check: after a key (provider, with a spoken word), or every 6 hours (`*`)."""

    @workflow.run
    async def run(self, provider: str, speech: bool) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "voice_check",
            args=[provider, speech],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=ONCE,
        )
        return out


VOICE_WORKFLOWS = [VoiceCall, VoiceCheck]
