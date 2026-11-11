"""The light's checks (contract §32.5): the background job behind a new key, and the recheck.

A check is two steps per engine of the provider: (1) the free metadata call (`models.get`) proves
the key is valid and the model exists for it; (2) one word of speech («سلام») proves the project
can really make speech (billing, quota, access), and its cost goes on the meter. The scheduled
recheck (every 6 h, `hq-voice-check`) and the recheck after a failure use step 1 only: free.

It runs on the worker as a Temporal workflow (`VoiceCheck`); when the api has no worker connection
(tests, a Temporal outage) it runs as a task of the api process, whose provider calls then fail
with a plain reason instead of leaving the light yellow. Each engine's result is stored and sent
on the stream as `voice.engine`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from hq_api.voice import catalog, store
from hq_api.voice.base import EngineFailed
from hq_api.voice.engines import engine_for

log = logging.getLogger("hq_api.voice.jobs")

WORKFLOW = "VoiceCheck"
EXECUTION_S = 180
ALL = "*"  # every provider whose key is set (the scheduled recheck)
_tasks: set[asyncio.Task[Any]] = set()


async def _settle(hub: Any, engine: str, state: str, reason: str | None) -> None:
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await store.set_state(tx, engine, state, reason):
            await store.emit_engine(tx, holding.code, engine, state, reason)


async def check_engine(hub: Any, engine: str, *, speech: bool) -> tuple[str, str | None]:
    """One engine's light now: the metadata call, then (for the owner's own check) a spoken
    word. The light and the stream are updated; returns (state, reason_fa)."""
    from hq_api.voice.speaker import speak_one

    cat = catalog.load()
    adapter = engine_for(engine)
    try:
        state, reason = await adapter.check(hub)
        if state == "ok" and speech:
            await speak_one(
                hub,
                engine,
                cat.check_text_fa,
                cat.voices_of(engine)[0]["name"],
                1.0,
                kind="check",
                persona="",
                conversation_ref=None,
                turn_id=None,
                seq=None,
                name=f"check-{engine}",
            )
    except EngineFailed as exc:
        state, reason = exc.state, exc.reason_fa
    await _settle(hub, engine, state, reason)
    return state, reason


async def run_check(hub: Any, provider: str, *, speech: bool) -> dict[str, str]:
    """Check every engine of `provider` (or of every provider whose key is set); {engine: state}."""
    cat = catalog.load()
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        st = await store.states(tx, holding.id)
    engines = [
        e.key
        for e in cat.engines.values()
        if e.provider != "local"
        and (provider == ALL or e.provider == provider)
        and st.get(e.key, {}).get("secret_set")
    ]
    out: dict[str, str] = {}
    for key in engines:
        state, _ = await check_engine(hub, key, speech=speech)
        out[key] = state
    return out


async def start_check(hub: Any, provider: str, *, speech: bool) -> None:
    """Begin a check without waiting for it: a workflow on the worker, else a local task."""
    client = getattr(hub, "temporal", None)
    if client is not None:
        try:
            await client.start_workflow(
                WORKFLOW,
                args=[provider, speech],
                id=f"voice-check-{provider}-{uuid.uuid4().hex[:10]}",
                task_queue=hub.settings.task_queue,
                execution_timeout=timedelta(seconds=EXECUTION_S),
            )
            return
        except Exception as exc:  # noqa: BLE001 - the local task below still runs the check
            log.warning("voice check could not start", extra={"error": type(exc).__name__})
    task = asyncio.create_task(_local(hub, provider, speech))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _local(hub: Any, provider: str, speech: bool) -> None:
    try:
        await asyncio.wait_for(run_check(hub, provider, speech=speech), EXECUTION_S)
    except Exception as exc:  # noqa: BLE001 - the light must not stay yellow
        log.warning("voice check failed", extra={"error": type(exc).__name__})
        await _stuck(hub, provider)


async def _stuck(hub: Any, provider: str) -> None:
    for e in catalog.load().engines_of(provider):
        with contextlib.suppress(Exception):
            await _settle(hub, e.key, "failing", "بررسی کلید به نتیجه نرسید؛ دوباره بسنج.")


async def drain() -> None:
    """Wait for the local check tasks (tests)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
