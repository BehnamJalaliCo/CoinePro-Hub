"""Runs workshop sessions on the chosen runtime (api process only).

Every runtime call happens outside a database transaction; what it returns
goes through domain.ingest in a short transaction of its own. After a
session ends: its transcript is stored (rule 7) and the next session waiting
for the same area of the repository starts (rule 6). A runtime that fails
fails the session (error code runtime_error), never the request that asked.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from uuid import UUID

from hq_api.domain import oversight
from hq_api.errors import ApiError
from hq_api.workshop import domain as D
from hq_api.workshop.runtime import FakeRuntime, ManagedRuntime, Runtime, configured

log = logging.getLogger("hq_api.workshop")
SYNC_EVERY_S = 5.0
# KV paths relative to the `kv` mount (read_kv adds the mount): the owner
# writes them as kv/hq-api/workshop/... (docs/ops/WORKSHOP.md).
GITHUB_PATH = "hq-api/workshop/github/{workspace}"  # token (the owner puts it there)
MANAGED_PATH = "hq-api/workshop/managed"  # api_key, agent_id, environment_id


def runtime(hub: Any) -> Runtime:
    """The runtime in use, or 503 runtime_not_configured until the owner chooses."""
    rt: Runtime | None = getattr(hub, "workshop", None)
    if rt is None:
        raise ApiError(503, "runtime_not_configured")
    return rt


async def build(hub: Any) -> Runtime | None:
    """At start: the runtime of WORKSHOP_RUNTIME, when everything it needs is
    there. `self_hosted` is a design only (docs/ops/WORKSHOP.md): None."""
    name = configured(hub.settings)
    if name != "managed" or hub.bao is None:
        return None
    try:
        cfg = await hub.bao.read_kv(MANAGED_PATH)
    except Exception:  # noqa: BLE001 - not set up yet: the workshop stays off
        log.warning("workshop: managed runtime chosen but not configured")
        return None
    if not (cfg.get("api_key") and cfg.get("agent_id") and cfg.get("environment_id")):
        log.warning("workshop: managed runtime chosen but not configured")
        return None
    key = str(cfg["api_key"])

    async def github_token(workspace: str) -> str | None:
        try:
            data = await hub.bao.read_kv(GITHUB_PATH.format(workspace=workspace))
        except Exception:  # noqa: BLE001 - reported as a failed session start
            return None
        token = data.get("token")
        return str(token) if token else None

    return ManagedRuntime(
        api_key=lambda: key,
        agent_id=str(cfg["agent_id"]),
        environment_id=str(cfg["environment_id"]),
        github_token=github_token,
    )


def meta_runtime(hub: Any) -> str | None:
    """What GET /meta reports: the runtime actually usable (never the test fake)."""
    rt = getattr(hub, "workshop", None)
    name = getattr(rt, "name", None)
    return name if name in ("managed", "self_hosted") else None


async def _tx(hub: Any) -> Any:
    return hub.db.tx(await hub.companies.ids())


async def _fail(hub: Any, session_id: UUID, summary: str) -> dict[str, Any]:
    async with await _tx(hub) as tx:
        s = await D.finish(
            tx, await D.load(tx, session_id, lock=True), "failed", "runtime_error", summary
        )
    await after_finish(hub, s)
    return s


async def settle(hub: Any, out: dict[str, Any]) -> dict[str, Any]:
    s: dict[str, Any] = out["session"]
    if out["interrupt"]:
        await interrupt(hub, [s])
    if out["finished"]:
        await after_finish(hub, s)
    return s


async def start(hub: Any, session_id: UUID) -> dict[str, Any]:
    rt = runtime(hub)
    async with await _tx(hub) as tx:
        s = await D.load(tx, session_id)
        # The overseer's hold (prompt 08 §2): it does not start until the owner decides.
        overseer_hold = await oversight.held(tx, "session", s["ref"])
    if s["state"] != "starting" or s["held"] or s["runtime"] != rt.name or overseer_hold:
        return s
    try:
        external_id, items = await rt.start(D.spec(s))
    except Exception as exc:  # noqa: BLE001 - the session fails, the caller does not
        log.warning(
            "workshop: start failed", extra={"session": s["ref"], "error_type": type(exc).__name__}
        )
        return await _fail(hub, session_id, "اجرای سشن شروع نشد")
    async with await _tx(hub) as tx:
        await tx.exec(
            "UPDATE workshop.sessions SET external_id = :x WHERE id = :id",
            x=external_id[:200],
            id=session_id,
        )
        out = await D.ingest(tx, session_id, items)
    return await settle(hub, out)


async def steer(hub: Any, session_id: UUID, text: str) -> dict[str, Any]:
    rt = runtime(hub)
    async with await _tx(hub) as tx:
        s = await D.load(tx, session_id)
        await oversight.require_not_held(tx, "session", s["ref"])
    if s["runtime"] != rt.name:
        return s
    try:
        items = await rt.send(D.spec(s), text)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "workshop: send failed", extra={"session": s["ref"], "error_type": type(exc).__name__}
        )
        return await _fail(hub, session_id, "پیام به سشن نرسید")
    async with await _tx(hub) as tx:
        out = await D.ingest(tx, session_id, items)
    return await settle(hub, out)


async def answer(
    hub: Any, session_id: UUID, approval: dict[str, Any], allow: bool
) -> dict[str, Any]:
    rt = runtime(hub)
    async with await _tx(hub) as tx:
        s = await D.load(tx, session_id)
    if s["runtime"] != rt.name:
        return s
    try:
        items = await rt.answer(D.spec(s), approval["external_id"], approval["action"], allow)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "workshop: answer failed", extra={"session": s["ref"], "error_type": type(exc).__name__}
        )
        return await _fail(hub, session_id, "پاسخ به سشن نرسید")
    async with await _tx(hub) as tx:
        out = await D.ingest(tx, session_id, items)
    return await settle(hub, out)


async def interrupt(hub: Any, sessions: list[dict[str, Any]]) -> None:
    """Best effort: a session stopped or paused stops on its runtime too."""
    rt: Runtime | None = getattr(hub, "workshop", None)
    if rt is None:
        return
    for s in sessions:
        if not s.get("external_id") or s.get("runtime") != rt.name:
            continue
        try:
            await rt.stop(D.spec(s))
        except Exception as exc:  # noqa: BLE001 - the record is already stopped
            log.warning(
                "workshop: interrupt failed",
                extra={"session": s["ref"], "error_type": type(exc).__name__},
            )


async def after_finish(hub: Any, s: dict[str, Any]) -> None:
    """The transcript into storage, then whoever waits for the area starts."""
    rt: Runtime | None = getattr(hub, "workshop", None)
    if rt is not None and s["runtime"] == rt.name:
        try:
            data = await rt.transcript(D.spec(s))
        except Exception as exc:  # noqa: BLE001 - the events stay; retried by sync
            log.warning(
                "workshop: transcript failed",
                extra={"session": s["ref"], "error_type": type(exc).__name__},
            )
            data = b""
        if data:
            async with await _tx(hub) as tx:
                await D.store_transcript(
                    tx, hub.storage, await D.load(tx, s["id"], lock=True), data
                )
    async with await _tx(hub) as tx:
        released = await D.next_in_line(tx, s["workspace_id"])
    if rt is not None:
        for r in released:
            await start(hub, r["id"])


async def stopped(hub: Any, sessions: list[dict[str, Any]]) -> None:
    """Sessions just stopped by the hub (stop, revoke): on the runtime too."""
    await interrupt(hub, sessions)
    for s in sessions:
        await after_finish(hub, s)


async def paused(hub: Any) -> None:
    """After a kill switch or a deploy freeze: the paused sessions are
    interrupted on their runtime (the records were paused in the same
    transaction as the lock)."""
    if getattr(hub, "workshop", None) is None:
        return
    async with await _tx(hub) as tx:
        rows = await tx.all(
            D.SESSION_SQL + " WHERE s.held = 'company_locked' AND s.state <> ALL(:final)",
            final=list(D.FINAL),
        )
    await interrupt(hub, rows)


async def sync(hub: Any) -> int:
    """Poll the runtime for the sessions it runs on its own (managed)."""
    rt: Runtime | None = getattr(hub, "workshop", None)
    if rt is None or isinstance(rt, FakeRuntime):
        return 0
    async with await _tx(hub) as tx:
        rows = await tx.all(
            D.SESSION_SQL
            + """ WHERE s.state = ANY(:active) AND s.external_id IS NOT NULL AND s.held IS NULL
                  AND s.runtime = :rt
                  ORDER BY s.created_at""",
            active=list(D.ACTIVE),
            rt=rt.name,
        )
    n = 0
    for s in rows:
        try:
            items, cursor = await rt.poll(D.spec(s))
        except Exception as exc:  # noqa: BLE001 - next round
            log.warning(
                "workshop: poll failed",
                extra={"session": s["ref"], "error_type": type(exc).__name__},
            )
            continue
        async with await _tx(hub) as tx:
            if cursor and cursor != s["external_cursor"]:
                await tx.exec(
                    "UPDATE workshop.sessions SET external_cursor = :c WHERE id = :id",
                    c=cursor[:200],
                    id=s["id"],
                )
            out = await D.ingest(tx, s["id"], items)
        await settle(hub, out)
        n += len(items)
    return n


async def loop(hub: Any) -> None:
    """The api's background poller (only does anything for `managed`)."""
    while True:
        await asyncio.sleep(SYNC_EVERY_S)
        with contextlib.suppress(Exception):
            await sync(hub)
