"""Prompt 5.1 §2.4: the subscription quota never stays `limited` for good.

A usage-limit error whose reset time cannot be read (every billing_error)
holds until the breaker's retry time, or five hours; the hold is persisted, so
a router restart keeps its expiry. Windows the CLI reports separately are kept
apart; a malformed window is refused before it is stored; a half-open breaker
still checks the quota.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest

from llm_router.backends.base import QUOTA, BackendResult
from llm_router.quota import LIMITED, WARNING, QuotaController, Throttled
from llm_router.quota import OK as Q_OK
from llm_router.schemas import RunRequest
from llm_router.service import RouterError

from .conftest import ROUTER_DIR, _env, needs_db, ok_result
from .conftest import FakeBackend as Scripted

T0 = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, at: datetime = T0) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def req(priority: int = 3) -> RunRequest:
    return RunRequest(
        company_code="TY",
        actor_ref="TY-CEO",
        task_class="general",
        priority=priority,
        prompt="hello",
    )


def sdk(status: str, window: Any, reset: datetime | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"status": status, "window": window}
    if reset is not None:
        event["resets_at"] = reset.timestamp()
    return event


async def subscription_id(su: asyncpg.Connection) -> str:
    return str(await su.fetchval("SELECT id FROM llm.connections WHERE key = 'claude-max'"))


# ----------------------------------------------------------------- units --
async def test_a_guard_without_a_reset_time_expires_after_five_hours() -> None:
    clock = Clock()
    q = QuotaController(None, None, now=clock)
    await q.on_quota_guard("c", "claude-max", None)
    s = q.state("c")
    assert (s.status, s.source) == (LIMITED, "quota_guard")
    assert s.resets_at == T0 + timedelta(hours=5) and s.estimated
    with pytest.raises(Throttled) as exc:
        q.check("c", "claude_subscription", 3)
    assert exc.value.retry_after == 300  # the reset is only an estimate: look again soon
    clock.at = T0 + timedelta(hours=5, seconds=1)
    assert q.state("c").status == Q_OK
    q.check("c", "claude_subscription", 4)
    assert [c.status for c in await q.scan({"c": "claude-max"}, set())] == [Q_OK]


async def test_a_guard_without_a_reset_time_takes_the_breakers_retry_time() -> None:
    clock = Clock()
    q = QuotaController(None, None, now=clock)
    retry = T0 + timedelta(minutes=10)
    await q.on_quota_guard("c", "claude-max", None, fallback=retry)
    assert q.state("c").resets_at == retry
    # A fallback in the past is no expiry: five hours instead.
    await q.on_quota_guard("d", "claude-max", None, fallback=T0 - timedelta(seconds=1))
    assert q.state("d").resets_at == T0 + timedelta(hours=5)
    # A reported reset time wins over every fallback.
    reset = T0 + timedelta(hours=2)
    await q.on_quota_guard("e", "claude-max", reset, fallback=retry)
    assert q.state("e").resets_at == reset and not q.state("e").estimated
    clock.at = retry + timedelta(seconds=1)
    assert q.state("c").status == Q_OK and q.state("e").status == LIMITED


async def test_an_sdk_state_without_a_reset_time_expires_too() -> None:
    clock = Clock()
    q = QuotaController(None, None, now=clock)
    await q.observe("c", "claude-max", {"status": "rejected"})
    assert q.state("c").resets_at == T0 + timedelta(hours=5)
    clock.at = T0 + timedelta(hours=6)
    assert q.state("c").status == Q_OK


async def test_windows_the_cli_reports_apart_are_kept_apart() -> None:
    clock = Clock()
    q = QuotaController(None, None, now=clock)
    five = await q.observe("c", "claude-max", sdk("rejected", "five_hour", T0 + timedelta(hours=1)))
    assert five is not None and five.status == LIMITED
    # Another window being fine does not lift the five-hour limit.
    assert await q.observe("c", "claude-max", sdk("allowed", "seven_day")) is None
    assert (q.state("c").status, q.state("c").window) == (LIMITED, "five_hour")
    await q.observe("c", "claude-max", sdk("allowed_warning", "seven_day", T0 + timedelta(hours=3)))
    assert q.state("c").window == "five_hour"  # the worst window decides
    clock.at = T0 + timedelta(hours=2)
    s = q.state("c")
    assert (s.status, s.window, s.resets_at) == (WARNING, "seven_day", T0 + timedelta(hours=3))
    clock.at = T0 + timedelta(hours=4)
    assert q.state("c").status == Q_OK
    # The same window reporting again replaces its own state.
    await q.observe("c", "claude-max", sdk("rejected", "five_hour", T0 + timedelta(hours=9)))
    await q.observe("c", "claude-max", sdk("allowed", "five_hour"))
    assert q.state("c").status == Q_OK


async def test_a_malformed_window_is_refused_before_it_is_stored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    q = QuotaController(None, None, now=Clock())
    with caplog.at_level(logging.WARNING, logger="llm_router.quota"):
        await q.observe("c", "claude-max", sdk("rejected", "Five Hours!"))
        await q.observe("c", "claude-max", sdk("rejected", 5))
    assert [r.getMessage() for r in caplog.records].count("quota window refused") == 2
    s = q.state("c")
    assert s.status == LIMITED and s.window is None  # the status still counts


# ----------------------------------------------------------- integration --
@needs_db
async def test_a_guard_without_a_reset_survives_a_restart_and_still_expires(
    su: asyncpg.Connection, db: Any, bus: Any
) -> None:
    cid = await subscription_id(su)
    clock = Clock(datetime.now(UTC))
    first = QuotaController(db, bus, now=clock)
    await first.on_quota_guard(cid, "claude-max", None)
    row = await su.fetchrow(
        "SELECT status, resets_at FROM llm.quota_status WHERE connection_id = $1::uuid", cid
    )
    assert row["status"] == LIMITED and row["resets_at"] == clock.at + timedelta(hours=5)
    restarted = QuotaController(db, bus, now=clock)
    assert await restarted.load() == 1
    s = restarted.state(cid)
    assert (s.status, s.resets_at, s.estimated) == (LIMITED, clock.at + timedelta(hours=5), True)
    assert await restarted.scan({cid: "claude-max"}, set()) == []
    clock.at += timedelta(hours=5, seconds=1)
    assert restarted.state(cid).status == Q_OK
    assert [c.status for c in await restarted.scan({cid: "claude-max"}, set())] == [Q_OK]
    row = await su.fetchrow(
        "SELECT status, source, resets_at FROM llm.quota_status WHERE connection_id = $1::uuid",
        cid,
    )
    assert tuple(row) == (Q_OK, "reset", None)


def _alembic(target: str) -> None:
    code = (
        "import sys; from alembic import command; from alembic.config import Config; "
        "getattr(command, sys.argv[1])(Config('alembic.ini'), sys.argv[2])"
    )
    verb = "downgrade" if target != "head" else "upgrade"
    subprocess.run(
        [sys.executable, "-c", code, verb, target],
        cwd=ROUTER_DIR,
        check=True,
        env=_env("hq", "HQ_DB_PASSWORD"),
        capture_output=True,
    )


@needs_db
async def test_a_row_saved_without_a_reset_before_the_fix_gets_five_hours(
    su: asyncpg.Connection, db: Any, bus: Any
) -> None:
    cid = await subscription_id(su)
    _alembic("0008")
    try:
        await su.execute(
            """INSERT INTO llm.quota_status (connection_id, status, source, observed_at, changed_at)
               VALUES ($1::uuid, 'limited', 'quota_guard', now() - interval '6 hours',
                       now() - interval '6 hours')""",
            cid,
        )
    finally:
        _alembic("head")
    row = await su.fetchrow(
        """SELECT resets_at - observed_at AS hold, resets_estimated
           FROM llm.quota_status WHERE connection_id = $1::uuid""",
        cid,
    )
    assert tuple(row) == (timedelta(hours=5), True)
    q = QuotaController(db, bus)
    assert await q.load() == 1
    assert q.state(cid).status == Q_OK  # five hours after it was seen
    assert [c.status for c in await q.scan({cid: "claude-max"}, set())] == [Q_OK]
    with pytest.raises(asyncpg.CheckViolationError):  # and none can be saved again
        await su.execute(
            "UPDATE llm.quota_status SET status = 'limited', resets_at = NULL "
            "WHERE connection_id = $1::uuid",
            cid,
        )


@needs_db
async def test_windows_survive_a_restart(su: asyncpg.Connection, db: Any, bus: Any) -> None:
    cid = await subscription_id(su)
    clock = Clock(datetime.now(UTC).replace(microsecond=0))
    q = QuotaController(db, bus, now=clock)
    await q.observe(cid, "claude-max", sdk("rejected", "five_hour", clock.at + timedelta(hours=1)))
    await q.observe(
        cid, "claude-max", sdk("allowed_warning", "seven_day", clock.at + timedelta(hours=3))
    )
    restarted = QuotaController(db, bus, now=clock)
    await restarted.load()
    assert (restarted.state(cid).status, restarted.state(cid).window) == (LIMITED, "five_hour")
    clock.at += timedelta(hours=2)
    assert (restarted.state(cid).status, restarted.state(cid).window) == (WARNING, "seven_day")


@needs_db
async def test_a_malformed_window_never_loses_the_row(
    su: asyncpg.Connection, db: Any, bus: Any
) -> None:
    cid = await subscription_id(su)
    q = QuotaController(db, bus)
    await q.observe(cid, "claude-max", sdk("rejected", "Five Hours!"))
    row = await su.fetchrow(
        "SELECT status, window_kind FROM llm.quota_status WHERE connection_id = $1::uuid", cid
    )
    assert row is not None and tuple(row) == (LIMITED, None)


@needs_db
async def test_a_billing_error_holds_until_the_breakers_retry_time(
    make_service: Any, su: asyncpg.Connection
) -> None:
    svc = make_service(
        subscription=Scripted(BackendResult(QUOTA, error_class="billing_error"), ok_result())
    )
    await svc.run(req(2), "hq-ops", 10_000)
    cid = await subscription_id(su)
    snap = svc.breakers[cid].snapshot
    s = svc.quota.state(cid)
    assert s.status == LIMITED and s.resets_at is not None
    assert s.resets_at == datetime.fromtimestamp(snap.retry_at, UTC)
    row = await su.fetchrow(
        "SELECT resets_at FROM llm.quota_status WHERE connection_id = $1::uuid", cid
    )
    assert row["resets_at"] == s.resets_at


@needs_db
async def test_a_half_open_breaker_still_checks_the_quota(
    make_service: Any, su: asyncpg.Connection
) -> None:
    svc = make_service(subscription=Scripted(ok_result(), ok_result()))
    await svc.run(req(2), "hq-ops", 10_000)
    cid = await subscription_id(su)
    await svc.quota.observe(
        cid, "claude-max", sdk("rejected", "seven_day", datetime.now(UTC) + timedelta(hours=2))
    )
    # The breaker opened for quota earlier and its retry time has passed: the next
    # request is its probe, and a P3 probe still waits while the quota is limited.
    now = time.time()
    svc.breakers[cid].restore_quota(now - 400, now - 100)
    with pytest.raises(RouterError) as exc:
        await svc.run(req(3), "hq-ops", 10_000)
    assert exc.value.code == "quota_throttled"
    assert (await svc.run(req(2), "hq-ops", 10_000)).status == "ok"  # P2 probes and closes it
