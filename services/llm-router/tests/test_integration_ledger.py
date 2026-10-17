"""Integration: ledger, RLS, budgets, quota guard, fallback, events (real Postgres + NATS)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import pytest

from llm_router.backends.base import ERROR, QUOTA, BackendResult
from llm_router.schemas import RunRequest
from llm_router.service import RouterError

from .conftest import Captured, FakeBackend, company_id, ok_result


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


async def wait_for(cap: Captured, subject_suffix: str, n: int = 1) -> list[dict[str, Any]]:
    for _ in range(50):
        found = [m for s, m in cap.messages if s.endswith(subject_suffix)]
        if len(found) >= n:
            return found
        await asyncio.sleep(0.05)
    return [m for s, m in cap.messages if s.endswith(subject_suffix)]


# --------------------------------------------------------------------- RLS --
async def test_rls_cross_company(su: asyncpg.Connection) -> None:
    ty, fx, hq = [await company_id(su, c) for c in ("TY", "FX", "HQ")]
    for cid, actor in ((ty, "TY-TECH-01"), (fx, "FX-TECH-01")):
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority,
                   caller, status) VALUES (gen_random_uuid(), now(), $1, $2, 'general', 2, 't', 'ok')""",
            cid,
            actor,
        )
        await su.execute(
            """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
               VALUES ($1, 'company', $2, 'day', 10)""",
            cid,
            actor[:2],
        )
    async with su.transaction():
        await su.execute("SET LOCAL ROLE hq_llm_reader")
        await su.execute("SELECT set_config('app.company_ids', $1, true)", "{" + ty + "}")
        assert [r["actor_ref"] for r in await su.fetch("SELECT actor_ref FROM llm.calls")] == [
            "TY-TECH-01"
        ]
        assert await su.fetchval("SELECT count(*) FROM llm.calls WHERE company_id = $1", fx) == 0
        assert [r["scope_ref"] for r in await su.fetch("SELECT scope_ref FROM llm.budgets")] == [
            "TY"
        ]
        assert [r["company"] for r in await su.fetch("SELECT company FROM llm.v_usage_daily")] == [
            "TY"
        ]
        assert [
            r["company"] for r in await su.fetch("SELECT company FROM llm.v_top_actors_30d")
        ] == ["TY"]
    async with su.transaction():  # no permitted companies -> nothing
        await su.execute("SET LOCAL ROLE hq_llm_reader")
        assert await su.fetchval("SELECT count(*) FROM llm.calls") == 0
    with pytest.raises(asyncpg.InsufficientPrivilegeError):  # partitions are not a way around RLS
        async with su.transaction():
            await su.execute("SET LOCAL ROLE hq_llm_reader")
            await su.fetch("SELECT * FROM llm.calls_default")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):  # readers cannot write
        async with su.transaction():
            await su.execute("SET LOCAL ROLE hq_llm_reader")
            await su.execute("SELECT set_config('app.company_ids', $1, true)", "{" + ty + "}")
            await su.execute("UPDATE llm.calls SET status = 'error'")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):  # writer: only its own companies
        async with su.transaction():
            await su.execute("SET LOCAL ROLE hq_llm_writer")
            await su.execute("SELECT set_config('app.company_ids', $1, true)", "{" + ty + "}")
            await su.execute(
                """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority,
                       caller, status) VALUES (gen_random_uuid(), now(), $1, 'x', 'general', 2, 't', 'ok')""",
                fx,
            )
    async with su.transaction():  # writer cannot touch other companies' rows, nor delete
        await su.execute("SET LOCAL ROLE hq_llm_writer")
        await su.execute("SELECT set_config('app.company_ids', $1, true)", "{" + ty + "}")
        assert (
            await su.execute("UPDATE llm.calls SET status = 'error' WHERE company_id = $1", fx)
            == "UPDATE 0"
        )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with su.transaction():
            await su.execute("SET LOCAL ROLE hq_llm_writer")
            await su.execute("DELETE FROM llm.calls")
    async with su.transaction():  # FORCE RLS: even the owner sees no ledger rows
        await su.execute("SET LOCAL ROLE hq")
        assert await su.fetchval("SELECT count(*) FROM llm.calls") == 0
    assert hq  # holding exists


async def test_partitions_route_rows_by_month(su: asyncpg.Connection) -> None:
    month = datetime.now(UTC).strftime("calls_%Y_%m")
    assert await su.fetchval("SELECT to_regclass('llm.' || $1) IS NOT NULL", month)
    ty = await company_id(su, "TY")
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller, status)
           VALUES (gen_random_uuid(), now(), $1, 'a', 'general', 1, 't', 'ok')""",
        ty,
    )
    assert await su.fetchval(f"SELECT count(*) FROM llm.{month}") == 1
    assert await su.fetchval("SELECT count(*) FROM llm.calls_default") == 0


# ------------------------------------------------------------- happy path --
async def test_run_records_ledger_usage_and_events(
    su: asyncpg.Connection, make_service: Any, captured: Captured
) -> None:
    backend = FakeBackend(
        ok_result(
            input_tokens=1200, output_tokens=30, cache_read_tokens=500, cache_write_tokens=100
        )
    )
    svc = make_service(subscription=backend)
    resp = await svc.run(req(work_ref="W-1", role="lead-dev", effort="low"), "tests", 10_000)
    assert resp.status == "ok" and resp.text == "OK" and resp.connection == "claude-max"
    assert resp.model == "claude-sonnet-5-5" and resp.effort == "low"
    # From our price table (Sonnet 5.5: 1200x2 + 30x10 + 500x0.10 + 100x2.50 per 1M),
    # never the SDK's own figure, which stays in meta for comparison.
    assert resp.equiv_cost_usd == "0.003000" and resp.cost_usd is None
    call = backend.calls[0]
    assert call.effort == "low" and call.messages[0].content == "Say OK"

    row = await su.fetchrow("SELECT * FROM llm.calls WHERE id = $1", resp.call_id)
    assert row["status"] == "ok" and row["finished_at"] is not None
    assert (
        row["input_tokens"],
        row["output_tokens"],
        row["cache_read_tokens"],
        row["cache_write_tokens"],
    ) == (1200, 30, 500, 100)
    assert row["thinking_tokens"] is None
    assert row["equiv_cost_usd"] == Decimal("0.003000") and row["cost_usd"] is None
    meta = json.loads(row["meta"]) if isinstance(row["meta"], str) else row["meta"]
    assert meta["sdk_cost_usd"] == "0.000400"
    assert row["department"] == "TECH" and row["work_ref"] == "W-1" and row["caller"] == "tests"
    assert row["meta"]  # assignment trail, stop reason
    assert str(row["id"])[14] == "7"  # uuid v7

    usage = {
        (r["scope_type"], r["scope_ref"], r["period"]): r["tokens"]
        for r in await su.fetch("SELECT * FROM llm.usage")
    }
    for scope in (
        ("holding", "HQ"),
        ("company", "TY"),
        ("department", "TY-TECH"),
        ("role", "lead-dev"),
        ("role", "TY:lead-dev"),
        ("task_class", "general"),
    ):
        assert usage[(*scope, "day")] == 1830
        assert usage[(*scope, "month")] == 1830

    started = await wait_for(captured, ".call.started")
    finished = await wait_for(captured, ".call.finished")
    assert "hq.llm.TY.call.started" in captured.subjects()
    assert started[0]["call_id"] == finished[0]["call_id"] == resp.call_id
    assert finished[0]["usage"]["input_tokens"] == 1200


async def test_unknown_inputs_are_rejected(make_service: Any) -> None:
    svc = make_service()
    for kwargs, code in (
        (dict(company_code="ZZ"), "unknown_company"),
        (dict(task_class="nope"), "unknown_task_class"),
        (dict(model="gpt-9"), "assignment"),
        (dict(timeout_s=10_000), "timeout_too_long"),
    ):
        with pytest.raises(RouterError) as exc:
            await svc.run(req(**kwargs), "tests", 10_000)
        assert exc.value.code == code
    with pytest.raises(RouterError) as exc:
        await svc.run(req(prompt="x" * 50), "tests", 10)
    assert exc.value.status_code == 413


async def test_the_output_cap_reaches_the_backend_clamped(
    su: asyncpg.Connection, make_service: Any
) -> None:
    """prompt 5.1 §2.6: an agent step's hard cap, at most LLM_MAX_OUTPUT_TOKENS."""
    backend = FakeBackend()
    svc = make_service(subscription=backend)
    for cap in (1200, 900_000, None):
        await svc.run(req(max_output_tokens=cap), "t", 10_000)
    assert [c.max_output_tokens for c in backend.calls] == [1200, svc.s.max_output_tokens, None]


def test_the_fake_model_stops_at_the_output_cap() -> None:
    from llm_router.backends.base import BackendCall
    from llm_router.backends.fake import FakeBackend as Fake

    fake = Fake()
    fake.enqueue("TY-CEO", "x" * 400)
    conn: Any = None
    out = fake._result(
        BackendCall("c", conn, "m", None, None, (), None, 10, "TY-CEO", max_output_tokens=10)
    )
    assert out.stop_reason == "max_tokens" and out.usage is not None
    assert out.usage.output_tokens <= 10


async def test_advisor_role_inherits_opus_xhigh(su: asyncpg.Connection, make_service: Any) -> None:
    backend = FakeBackend()
    svc = make_service(subscription=backend)
    await svc.run(
        req(company_code="HQ", actor_ref="advisor", department=None, role="advisor"), "t", 10_000
    )
    assert (backend.calls[0].model, backend.calls[0].effort) == ("claude-opus-5-5", "xhigh")


# ----------------------------------------------------------------- budgets --
async def test_budget_alerts_at_70_and_90_then_p4_stops_at_100(
    su: asyncpg.Connection, make_service: Any, captured: Captured
) -> None:
    ty = await company_id(su, "TY")
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', 'TY', 'day', 1000)""",
        ty,
    )
    svc = make_service(
        subscription=FakeBackend(
            ok_result(input_tokens=700, output_tokens=0),
            ok_result(input_tokens=200, output_tokens=0),
            ok_result(input_tokens=100, output_tokens=0),
            ok_result(input_tokens=1, output_tokens=0),
        )
    )
    await svc.run(req(priority=4), "t", 10_000)  # 700 used after this call
    await svc.run(req(priority=4), "t", 10_000)  # pre-check sees 70% -> alert, then 900
    await svc.run(req(priority=3), "t", 10_000)  # pre-check sees 90% -> alert, then 1000
    with pytest.raises(RouterError) as exc:
        await svc.run(req(priority=4), "t", 10_000)  # 100%: background work stops
    assert exc.value.code == "budget_exhausted" and exc.value.status_code == 429
    assert exc.value.retry_after and exc.value.retry_after > 0
    rejected = await su.fetchrow(
        "SELECT status, error_class FROM llm.calls WHERE id = $1", exc.value.call_id
    )
    assert tuple(rejected) == ("rejected_budget", "budget_exhausted")
    ok = await svc.run(req(priority=1), "t", 10_000)  # P0-P3 still run
    assert ok.status == "ok"
    alerts = await wait_for(captured, "budget.TY", 3)
    assert [a["level"] for a in alerts] == [70, 90, 100]
    assert (await su.fetchrow("SELECT alert_level FROM llm.budgets"))["alert_level"] == 100


# ----------------------------------------------------- quota and fallback --
async def test_quota_guard_fallback_and_recovery(su: asyncpg.Connection, make_service: Any) -> None:
    reset = time.time() + 1.5
    sub = FakeBackend(
        BackendResult(QUOTA, error_class="usage_limit", quota_resets_at=reset), ok_result()
    )
    api = FakeBackend(ok_result(text="from api", model="claude-haiku-5-5"))
    svc = make_service(subscription=sub, api=api)

    first = await svc.run(req(), "t", 10_000)
    assert first.status == "quota_exhausted"
    conn = await su.fetchrow(
        "SELECT status, quota_reset_at FROM llm.connections WHERE key = 'claude-max'"
    )
    assert (
        conn["status"] == "quota_exhausted" and abs(conn["quota_reset_at"].timestamp() - reset) < 1
    )

    with pytest.raises(RouterError) as p4:
        await svc.run(req(priority=4), "t", 10_000)
    assert (p4.value.status_code, p4.value.code) == (
        429,
        "quota_exhausted",
    ) and p4.value.retry_after
    with pytest.raises(RouterError) as p2:  # not transferable -> clear error, no alternative
        await svc.run(req(priority=2), "t", 10_000)
    assert (p2.value.status_code, p2.value.code) == (503, "quota_exhausted")
    with pytest.raises(RouterError):  # transferable, but every alternative is off
        await svc.run(req(task_class="summarize"), "t", 10_000)
    statuses = [
        r["status"] for r in await su.fetch("SELECT status FROM llm.calls ORDER BY started_at")
    ]
    assert statuses == ["quota_exhausted"] * 4

    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = 'anthropic-api'")
    moved = await svc.run(req(task_class="summarize", model="claude-haiku-5-5"), "t", 10_000)
    assert moved.connection == "anthropic-api" and moved.text == "from api"
    assert moved.cost_usd is not None and moved.equiv_cost_usd is None
    meta = await su.fetchval("SELECT meta FROM llm.calls WHERE id = $1", moved.call_id)
    assert "fallback_from" in meta
    with pytest.raises(RouterError):  # P4 never moves to an alternative
        await svc.run(req(task_class="summarize", priority=4), "t", 10_000)

    await asyncio.sleep(max(0.0, reset - time.time()) + 0.1)
    back = await svc.run(req(), "t", 10_000)  # the single half-open probe succeeds
    assert back.status == "ok" and back.connection == "claude-max"
    assert (
        await su.fetchval("SELECT status FROM llm.connections WHERE key = 'claude-max'")
        == "enabled"
    )


async def test_quota_state_survives_restart(su: asyncpg.Connection, make_service: Any) -> None:
    await su.execute(
        """UPDATE llm.connections SET status = 'quota_exhausted', status_changed_at = now(),
               quota_reset_at = now() + interval '1 hour' WHERE key = 'claude-max'"""
    )
    svc = make_service()  # a fresh router restores the open quota breaker from the database
    with pytest.raises(RouterError) as exc:
        await svc.run(req(), "t", 10_000)
    assert exc.value.code == "quota_exhausted" and 3500 < (exc.value.retry_after or 0) <= 3601
    view = {c["key"]: c for c in await svc.connections_view()}
    assert view["claude-max"]["breaker"] == "open"


async def test_repeated_errors_open_the_breaker(su: asyncpg.Connection, make_service: Any) -> None:
    sub = FakeBackend(*[BackendResult(ERROR, error_class="server_error")] * 5)
    svc = make_service(subscription=sub)
    for _ in range(5):
        assert (await svc.run(req(), "t", 10_000)).status == "error"
    with pytest.raises(RouterError) as exc:
        await svc.run(req(), "t", 10_000)
    assert exc.value.code == "circuit_open"


async def test_disabled_connection_and_ledger_down(
    su: asyncpg.Connection, make_service: Any
) -> None:
    await su.execute("UPDATE llm.connections SET status = 'disabled' WHERE key = 'claude-max'")
    with pytest.raises(RouterError) as exc:
        await make_service().run(req(), "t", 10_000)
    assert exc.value.code == "connection_disabled"


# ------------------------------------------------- queue, stream, extras --
async def test_p4_rejected_when_busy(su: asyncpg.Connection, make_service: Any) -> None:
    svc = make_service(subscription=FakeBackend(delay=0.3), capacity=2, p4_max_waiting=0)
    busy = asyncio.create_task(svc.run(req(priority=4), "t", 10_000))
    await asyncio.sleep(0.05)
    with pytest.raises(RouterError) as exc:
        await svc.run(req(priority=4), "t", 10_000)
    assert (exc.value.status_code, exc.value.retry_after) == (429, 7)
    assert (await svc.run(req(priority=0), "t", 10_000)).status == "ok"  # reserved slot
    await busy


async def test_stream_and_transcript(su: asyncpg.Connection, make_service: Any) -> None:
    svc = make_service(subscription=FakeBackend(ok_result(text="hello there friend")))
    gen = await svc.stream(req(store_transcript=True, system="be brief"), "t", 10_000)
    chunks = [c async for c in gen]
    assert chunks[0].startswith("event: start")
    assert sum(c.startswith("event: delta") for c in chunks) == 3
    assert chunks[-1].startswith("event: end") and '"status": "ok"' in chunks[-1]
    row = await su.fetchrow("SELECT status, input_tokens FROM llm.calls")
    assert tuple(row) == ("ok", 100)
    t = await su.fetchrow(
        "SELECT request, response, expires_at > now() AS live FROM llm.transcripts"
    )
    assert t["response"] == "hello there friend" and t["live"] and "be brief" in t["request"]
    await su.execute("UPDATE llm.transcripts SET expires_at = now() - interval '1 second'")
    done = await svc.maintenance()
    assert done["transcripts_purged"] == 1


async def test_close_stale_running_rows(su: asyncpg.Connection, make_service: Any) -> None:
    ty = await company_id(su, "TY")
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller, status)
           VALUES (gen_random_uuid(), now() - interval '2 hours', $1, 'a', 'general', 1, 't', 'running')""",
        ty,
    )
    assert await make_service().close_stale() == 1
    assert await su.fetchval("SELECT error_class FROM llm.calls") == "interrupted"


async def test_anomaly_alert(su: asyncpg.Connection, make_service: Any, captured: Captured) -> None:
    ty = await company_id(su, "TY")
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller, status)
           SELECT gen_random_uuid(), date_trunc('hour', now()), $1, 'TY-OPS-09', 'general', 4, 't', 'ok'
           FROM generate_series(1, 40)""",
        ty,
    )
    svc = make_service()
    alerts = await svc.anomaly_scan()
    assert [a["actor_ref"] for a in alerts] == ["TY-OPS-09"]
    assert await svc.anomaly_scan() == []  # once per actor and hour
    assert (await wait_for(captured, "llm.anomaly"))[0]["calls_this_hour"] == 40


async def test_sdk_cost_drift_alerts_once_after_an_hour(
    su: asyncpg.Connection, make_service: Any, captured: Captured
) -> None:
    t = [datetime(2026, 10, 16, 8, 0, tzinfo=UTC)]
    drifting = ok_result(model="claude-haiku-5-5", input_tokens=2, output_tokens=4)
    drifting.sdk_cost_usd = Decimal("0.002144")  # ~1000x our Haiku price (0.000002)
    backend = FakeBackend(*[drifting] * 3)
    svc = make_service(subscription=backend, now=lambda: t[0])
    for minutes in (0, 30, 31):
        t[0] += timedelta(minutes=minutes)
        resp = await svc.run(req(model="claude-haiku-5-5"), "tests", 10_000)
        assert resp.equiv_cost_usd == "0.000002"  # ours, not the SDK's
    alerts = await wait_for(captured, "llm.cost_ratio")
    assert len(alerts) == 1
    alert = alerts[0]
    assert (alert["connection"], alert["model"], alert["window_minutes"]) == (
        "claude-max",
        "claude-haiku-5-5",
        60,
    )
    assert set(alert) == {"type", "connection", "model", "ratio", "since", "window_minutes", "at"}
    assert Decimal(alert["ratio"]) > 2
