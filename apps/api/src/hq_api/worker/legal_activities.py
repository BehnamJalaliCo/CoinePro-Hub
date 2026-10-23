"""Temporal activities of prompt 13, the legal and voice half.

legal_mail_poll  every 5 minutes: the holding mailbox's new messages through
                 egress; only replies to a case's sent message are kept
                 (masked, on the case's timeline, the counsel woken)
voice_bakeoff    daily 03:40 (owner zone): queue the bake-off samples still
                 missing for every voice the hub can run (the TTS one-shot
                 speaks them when it runs; it is opt-in and off today)

Both ask the launch gate first (hq_api.domain.gate) and do nothing at all
while the holding is locked: no mailbox call, no job, no model (neither
calls a model ever). The sealed email's one send is not here: it is the
decision's effect (decision_apply_effect -> legal.deliver), which waits
while a lock is set.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import gate, legal, voices
from hq_api.hub import Hub


class LegalVoiceActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.legal_mail_poll, self.voice_bakeoff]

    @activity.defn(name="legal_mail_poll")
    async def legal_mail_poll(self) -> dict[str, Any]:
        return await legal.poll(self.hub, self._tx)

    @activity.defn(name="voice_bakeoff")
    async def voice_bakeoff(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if (lock := await gate.holding_lock(tx)) is not None:
                return gate.skipped(lock)
            return await voices.queue_bakeoff(tx)
