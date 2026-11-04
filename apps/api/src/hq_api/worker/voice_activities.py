"""Temporal activities of the voice layer (prompt 23, contract §32.5): the only code that makes a
provider call. The worker is the one process on the egress network that may read the voice key.

voice_call   one provider call for the api (a metadata call, or one sentence of speech): the key is
             read from OpenBao for this call, sent to egress, and dropped; what returns is a stored
             file's id and the provider's own token counts (hq_api.voice.remote)
voice_check  the light's check (hq_api.voice.jobs): after a new key (with a spoken word), every
             6 h by the schedule `hq-voice-check` (metadata only, free), after a failure
"""

from __future__ import annotations

import json
from typing import Any

from temporalio import activity

from hq_api.domain import gate
from hq_api.hub import Hub
from hq_api.voice import jobs, remote, transport


class VoiceActivities:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub

    def all(self) -> list[Any]:
        return [self.voice_call, self.voice_check]

    @activity.defn(name="voice_call")
    async def voice_call(self, op: str, args_json: str) -> dict[str, Any]:
        return await remote.run(self.hub, op, json.loads(args_json))

    @activity.defn(name="voice_check")
    async def voice_check(self, provider: str, speech: bool) -> dict[str, Any]:
        if provider == jobs.ALL:  # the schedule: nothing while the holding is locked
            async with self.hub.db.tx(await self.hub.companies.ids()) as tx:
                if await gate.holding_lock(tx) is not None:
                    return {"skipped": "locked"}
        token = transport.LOCAL.set(True)  # this is the worker: call the provider right here
        try:
            return {"engines": await jobs.run_check(self.hub, provider, speech=speech)}
        finally:
            transport.LOCAL.reset(token)
