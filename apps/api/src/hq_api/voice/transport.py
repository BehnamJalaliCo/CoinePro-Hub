"""How a provider call reaches the one process that may make it.

Only the worker is on the egress network (hq-egress-api) and holds the OpenBao read of the voice
key; the api process, where a talk turn runs, is on neither. So the api asks the worker for each
provider call through Temporal (the pattern of the owner's «آزمودن» in routes/connections.py:
`ConnectionTest`) and gets back numbers and a file id, never audio and never a key. Tests set
OVERRIDE to a fake transport (a local one that runs the worker's code against a fake egress).

Ops (args are plain JSON; none holds a secret):
  models_get {provider, model}                       free metadata call for one model
  speak      {provider, model, text, voice, rate, name}   one sentence: Ogg/Opus stored as a file
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Protocol

log = logging.getLogger("hq_api.voice.transport")

WORKFLOW = "VoiceCall"
EXECUTION_S = 75  # a sentence of speech is seconds; this bounds a stuck worker


class TransportDown(Exception):
    """The worker could not be reached or the call could not run."""


class Transport(Protocol):
    async def call(self, hub: Any, op: str, args: dict[str, Any]) -> dict[str, Any]: ...


OVERRIDE: Transport | None = None
# True inside the worker's own activities: the call is made right there, not through Temporal.
LOCAL: contextvars.ContextVar[bool] = contextvars.ContextVar("voice_local", default=False)


async def call(hub: Any, op: str, args: dict[str, Any]) -> dict[str, Any]:
    """{outcome: ok|blocked|error, code, data} of one provider call, run on the worker."""
    if OVERRIDE is not None:
        return await OVERRIDE.call(hub, op, args)
    if LOCAL.get():
        from hq_api.voice import remote

        return await remote.run(hub, op, args)
    client = getattr(hub, "temporal", None)
    if client is None:
        raise TransportDown("no worker connection")
    try:
        out = await client.execute_workflow(
            WORKFLOW,
            args=[op, json.dumps(args, ensure_ascii=False)],
            id=f"voice-{op}-{uuid.uuid4().hex[:12]}",
            task_queue=hub.settings.task_queue,
            execution_timeout=timedelta(seconds=EXECUTION_S),
        )
    except Exception as exc:
        log.warning("voice call could not run", extra={"op": op, "error": type(exc).__name__})
        raise TransportDown(type(exc).__name__) from exc
    if not isinstance(out, dict):
        raise TransportDown("bad answer")
    return out
