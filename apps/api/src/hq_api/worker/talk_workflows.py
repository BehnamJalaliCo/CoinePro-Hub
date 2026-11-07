"""⟨1.14⟩ Prompt 23 (contract §32.2, §32.8): one persona turn of the owner's
talk (the activities are in talk_activities.py).

TalkTurn(turn_id)   id talk-turn-<id>: the turn, once (a retry would speak
                    twice); a failure gives the plain line instead of a
                    silent turn; then, when due, the conversation's summary
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

TURN_LIMIT = timedelta(minutes=10)  # the steps, the reads and every sentence spoken
ONCE = RetryPolicy(maximum_attempts=1)


@workflow.defn(name="TalkTurn")
class TalkTurn:
    @workflow.run
    async def run(self, turn_id: str) -> dict[str, Any]:
        try:
            out: dict[str, Any] = await workflow.execute_activity(
                "talk_turn", turn_id, start_to_close_timeout=TURN_LIMIT, retry_policy=ONCE
            )
        except ActivityError:
            out = await workflow.execute_activity(
                "talk_plain",
                turn_id,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        if out.get("summary_due") and out.get("ref"):
            with contextlib.suppress(ActivityError):  # the next turn tries again
                await workflow.execute_activity(
                    "talk_summary",
                    out["ref"],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=ONCE,
                )
        if out.get("memory_due") and out.get("order_ref"):
            # ⟨1.22⟩ §40.1 the session's memory folded every 20 turns; never blocks the turn
            with contextlib.suppress(ActivityError):
                await workflow.execute_activity(
                    "session_memory",
                    out["order_ref"],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=ONCE,
                )
        return {"state": out.get("state")}


TALK_WORKFLOWS = [TalkTurn]
