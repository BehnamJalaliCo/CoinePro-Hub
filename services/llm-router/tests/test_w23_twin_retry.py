"""⟨2026-11-11⟩ W23: a call the main subscription refused is made once more on the owner's other
subscription (audit C1b), a stream only before its first delta; a quota refusal says when to come
back; and a runner's limit the api wrote into llm.quota_status is the router's too (audit C1a)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from llm_router.backends.base import QUOTA, BackendCall, BackendResult, Delta
from llm_router.schemas import RunRequest

from .conftest import FakeBackend, ok_result


def req(**kw: Any) -> RunRequest:
    base: dict[str, Any] = {
        "company_code": "TY",
        "actor_ref": "TY-TECH-01",
        "department": "TECH",
        "task_class": "general",
        "priority": 2,
        "prompt": "Say OK",
        "timeout_s": 30,
    }
    base.update(kw)
    return RunRequest(**base)


def refused(in_s: float = 600) -> BackendResult:
    return BackendResult(QUOTA, error_class="usage_limit", quota_resets_at=time.time() + in_s)


class Quiet(FakeBackend):
    """Streams nothing before a refusal (the CLI refuses before it writes a word)."""

    async def stream(self, call: BackendCall) -> AsyncIterator[Delta | BackendResult]:
        self.calls.append(call)
        result = self._next()
        if result.text:
            for word in result.text.split(" "):
                yield Delta(word + " ")
        yield result


async def _second(su: asyncpg.Connection, status: str) -> None:
    await su.execute("UPDATE llm.connections SET status = $1 WHERE key = 'claude-max-2'", status)


async def _restore(su: asyncpg.Connection) -> None:
    await _second(su, "disabled")
    await su.execute(
        "UPDATE llm.connections SET status = 'enabled', quota_reset_at = NULL WHERE key = 'claude-max'"
    )


async def _calls(su: asyncpg.Connection) -> list[dict[str, Any]]:
    rows = await su.fetch(
        """SELECT c.id::text, c.status, c.error_class, n.key, c.meta FROM llm.calls c
           JOIN llm.connections n ON n.id = c.connection_id ORDER BY c.started_at"""
    )
    return [{**dict(r), "meta": json.loads(r["meta"])} for r in rows]


async def test_a_refused_call_is_made_once_more_on_the_other_subscription(
    su: asyncpg.Connection, make_service: Any
) -> None:
    sub = FakeBackend(refused(), ok_result(text="from the second account"), refused(), refused())
    svc = make_service(subscription=sub)
    await _second(su, "enabled")
    try:
        r = await svc.run(req(), "t", 10_000)
        assert (r.status, r.connection, r.text) == ("ok", "claude-max-2", "from the second account")
        first, again = await _calls(su)
        assert (first["status"], first["key"]) == ("quota_exhausted", "claude-max")
        assert (again["status"], again["key"]) == ("ok", "claude-max-2")
        assert again["meta"]["retry_of"] == first["id"]
        # the second account refuses too: once only, the refusal comes back with when to retry
        r2 = await svc.run(req(), "t", 10_000)
        assert (r2.status, r2.connection) == ("quota_exhausted", "claude-max-2")
        assert r2.retry_after is not None and 0 < r2.retry_after <= 600
        assert len(await _calls(su)) == 3
    finally:
        await _restore(su)


async def test_without_a_usable_twin_the_refusal_stands_with_its_wait(
    su: asyncpg.Connection, make_service: Any
) -> None:
    svc = make_service(subscription=FakeBackend(refused(1200), ok_result()))
    r = await svc.run(req(), "t", 10_000)  # claude-max-2 is switched off
    assert (r.status, r.error_class) == ("quota_exhausted", "usage_limit")
    assert r.retry_after is not None and 1100 < r.retry_after <= 1200
    assert [c["status"] for c in await _calls(su)] == ["quota_exhausted"]
    await _restore(su)


async def test_a_retry_that_would_not_land_on_the_twin_is_never_sent(
    su: asyncpg.Connection, make_service: Any
) -> None:
    """The twin said it could take the call, but admission put the retry elsewhere (here an api
    key, the twin's breaker having opened meanwhile): the retry is only ever for the twin, so it is
    not sent, its row ends, and the refusal stands."""
    api = FakeBackend(ok_result(text="from api"))
    svc = make_service(subscription=FakeBackend(refused()), api=api)
    await _second(su, "enabled")
    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = 'anthropic-api'")
    try:
        twin = (await svc.registry.get()).connection_by_key("claude-max-2")
        assert twin is not None
        svc._twin_subscription = lambda *_a, **_k: twin  # type: ignore[method-assign]
        svc.breaker_for(twin).on_quota(None, time.time() + 600)
        r = await svc.run(req(task_class="summarize"), "t", 10_000)
        assert (r.status, r.connection) == ("quota_exhausted", "claude-max")
        first, dropped = await _calls(su)
        assert (first["status"], first["key"]) == ("quota_exhausted", "claude-max")
        assert (dropped["status"], dropped["error_class"], dropped["key"]) == (
            "error", "retry_not_on_twin", "anthropic-api",
        )  # fmt: skip
        assert dropped["meta"]["retry_of"] == first["id"]
        assert api.calls == []  # never sent
        assert svc.scheduler.active == 0  # its slot given back
    finally:
        await su.execute(
            "UPDATE llm.connections SET status = 'disabled' WHERE key = 'anthropic-api'"
        )
        await _restore(su)


async def test_the_retry_waits_only_seconds_for_a_slot(
    su: asyncpg.Connection, make_service: Any
) -> None:
    """The caller's deadline is timeout_s + 30 s: the retry never waits timeout_s for a slot
    before its own timeout_s run; with no slot within seconds the refusal stands."""
    from llm_router.scheduler import QueueTimeout

    svc = make_service(subscription=FakeBackend(refused(), ok_result(text="two")))
    await _second(su, "enabled")
    waits: list[float] = []
    real = svc.scheduler.acquire

    async def acquire(priority: int, timeout: float) -> None:  # noqa: ASYNC109 - its API
        waits.append(timeout)
        if len(waits) == 2:
            raise QueueTimeout()
        await real(priority, timeout)

    svc.scheduler.acquire = acquire
    try:
        r = await svc.run(req(), "t", 10_000)
        assert waits == [30, svc.RETRY_SLOT_WAIT_S] and svc.RETRY_SLOT_WAIT_S <= 5
        assert (r.status, r.connection) == ("quota_exhausted", "claude-max")
        assert [c["key"] for c in await _calls(su)] == ["claude-max"]
        assert svc.scheduler.active == 0
    finally:
        await _restore(su)


async def test_a_stream_moves_only_before_its_first_delta(
    su: asyncpg.Connection, make_service: Any
) -> None:
    sub = Quiet(refused(), ok_result(text="hello from two"))
    svc = make_service(subscription=sub)
    await _second(su, "enabled")
    try:
        events = [e async for e in await svc.stream(req(), "t", 10_000)]
        kinds = [e.split("\n", 1)[0] for e in events]
        assert kinds.count("event: start") == 2 and kinds[-1] == "event: end"
        end = json.loads(events[-1].split("data: ", 1)[1])
        assert (end["status"], end["connection"]) == ("ok", "claude-max-2")
        text = "".join(
            json.loads(e.split("data: ", 1)[1])["text"]
            for e in events
            if e.startswith("event: delta")
        )
        assert text.strip() == "hello from two"
        assert [c["key"] for c in await _calls(su)] == ["claude-max", "claude-max-2"]
    finally:
        await _restore(su)
    # a stream that already wrote something is never made again (the caller has the words)
    await su.execute("TRUNCATE llm.calls, llm.quota_status")
    late = BackendResult(QUOTA, text="partial", error_class="usage_limit")
    svc2 = make_service(subscription=Quiet(late, ok_result()))
    await _second(su, "enabled")
    try:
        events = [e async for e in await svc2.stream(req(), "t", 10_000)]
        end = json.loads(events[-1].split("data: ", 1)[1])
        assert (end["status"], end["connection"]) == ("quota_exhausted", "claude-max")
        assert len(await _calls(su)) == 1
    finally:
        await _restore(su)


def _window(status: str, util: str | None, resets: datetime, seen: datetime) -> dict[str, Any]:
    """A window as the api writes it (the router's own QuotaState.as_json)."""
    return {
        "status": status,
        "window": "five_hour",
        "utilization": util,
        "resets_at": resets.isoformat(),
        "source": "sdk_rate_limit_event",
        "observed_at": seen.isoformat(),
        "estimated": False,
    }


async def test_a_runners_limit_written_by_the_api_moves_the_hubs_calls(
    su: asyncpg.Connection, make_service: Any
) -> None:
    """The workshop's Claude Code job saw the main account rejected; the api wrote that window. The
    router takes it in (scan) and sends its own calls to the other account; a later save of the
    router's own window keeps the api's."""
    main = str(await su.fetchval("SELECT id FROM llm.connections WHERE key = 'claude-max'"))
    now = datetime.now(UTC)
    sub = FakeBackend(ok_result(text="on two"), ok_result(text="on two again"))
    svc = make_service(subscription=sub)
    await svc.quota.load()
    await _second(su, "enabled")
    try:
        windows = {"sdk:five_hour": _window("limited", None, now + timedelta(hours=2), now)}
        await su.execute(
            """INSERT INTO llm.quota_status (connection_id, status, window_kind, resets_at, source,
                   observed_at, windows)
               VALUES ($1::uuid, 'limited', 'five_hour', $2, 'sdk_rate_limit_event', $3, $4::jsonb)""",
            main,
            now + timedelta(hours=2),
            now,
            json.dumps(windows),
        )
        assert not svc.quota.near_full(main)  # not read yet
        await svc.quota_scan()
        assert svc.quota.near_full(main)
        r = await svc.run(req(priority=3), "t", 10_000)
        assert (r.status, r.connection) == ("ok", "claude-max-2")
        # the router saves the main account's state again (another window of its own): the api's
        # window is still there, under the row's lock
        later = now + timedelta(seconds=5)
        await su.execute(
            """UPDATE llm.quota_status SET windows = windows || $2::jsonb
               WHERE connection_id = $1::uuid""",
            main,
            json.dumps(
                {"sdk:seven_day": _window("warning", "0.5000", now + timedelta(days=3), later)}
            ),
        )
        await svc.quota.observe(
            main, "claude-max", {"status": "allowed", "window": "seven_day_opus"}
        )
        saved = json.loads(
            await su.fetchval(
                "SELECT windows FROM llm.quota_status WHERE connection_id = $1::uuid", main
            )
        )
        assert {"sdk:five_hour", "sdk:seven_day", "sdk:seven_day_opus"} <= set(saved)
        assert saved["sdk:five_hour"]["status"] == "limited"
        assert (
            await su.fetchval(
                "SELECT status FROM llm.quota_status WHERE connection_id = $1::uuid", main
            )
            == "limited"
        )
    finally:
        await _restore(su)
