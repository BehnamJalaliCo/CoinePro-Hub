"""Prompt 05 §8 (Quota Controller) and §2 (fake model, ledger metadata, the
employee's own assignment)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from pydantic import ValidationError

from llm_router.assignment import Assignment, resolve, scope_chain
from llm_router.backends.base import OK, QUOTA, BackendCall, BackendResult, ChatMessage
from llm_router.backends.fake import DEFAULT_STEP, FakeBackend, tokens
from llm_router.quota import LIMITED, WARNING, QuotaController, Thresholds, Throttled
from llm_router.quota import OK as Q_OK
from llm_router.schemas import RunRequest
from llm_router.service import RouterError

from .conftest import Captured, needs_db, ok_result
from .conftest import FakeBackend as Scripted


def req(priority: int = 3, **kw: Any) -> RunRequest:
    return RunRequest(
        company_code="TY",
        actor_ref=kw.pop("actor_ref", "TY-CEO"),
        task_class="general",
        priority=priority,
        prompt="hello",
        **kw,
    )


def warned(status: str = "allowed_warning", in_s: int = 3600, util: float = 0.85) -> BackendResult:
    r = ok_result()
    r.rate_limit = {
        "status": status,
        "window": "five_hour",
        "utilization": util,
        "resets_at": (datetime.now(UTC) + timedelta(seconds=in_s)).timestamp(),
    }
    return r


# ----------------------------------------------------------------- units --
def test_employee_assignment_is_more_specific_than_its_role() -> None:
    chain = scope_chain(
        holding="HQ",
        company="TY",
        department="TECH",
        role="sre",
        task_class="general",
        employee="TY-TECH-01",
    )
    assert chain[-4:-2] == [("role", "TY-TECH-01"), ("role", "TY:TY-TECH-01")]
    table = {
        ("holding", "HQ"): Assignment("conn", "claude-sonnet-5-5", "medium"),
        ("role", "sre"): Assignment(None, "claude-haiku-5-5", "high"),
        ("role", "TY:TY-TECH-01"): Assignment(None, "claude-sonnet-5-5", "low"),
    }
    r = resolve(table, chain)
    assert (r.model, r.effort) == ("claude-sonnet-5-5", "low")
    assert r.trail[-1] == "role:TY:TY-TECH-01"


def test_meta_is_allow_listed() -> None:
    ok = req(meta={"charter": "cto@1", "run_id": "0193-x", "step": 2, "trigger": "work"})
    assert ok.meta == {"charter": "cto@1", "run_id": "0193-x", "step": 2, "trigger": "work"}
    with pytest.raises(ValidationError):
        req(meta={"prompt": "never content"})
    with pytest.raises(ValidationError):
        req(meta={"charter": "x" * 65})
    with pytest.raises(ValidationError):
        req(employee="not a code")


async def test_fake_backend_answers_by_actor_then_default() -> None:
    fake = FakeBackend()
    step = {
        "summary_fa": "قدم",
        "actions": [{"tool": "work.get", "args": {"ref": "W-1"}}],
        "done": False,
    }
    fake.enqueue("TY-CEO", step, "متن")
    call = BackendCall(
        "c1",
        None,
        "claude-sonnet-5-5",
        "medium",
        "sys",
        (ChatMessage("user", "hi"),),  # type: ignore[arg-type]
        {"type": "object"},
        30,
        actor_ref="TY-CEO",
    )
    first = await fake.run(call)
    assert first.status == OK and first.structured == step
    assert first.usage is not None and first.usage.input_tokens == tokens("syshi")
    second = await fake.run(call)
    assert second.text == "متن" and second.structured is None
    assert (await fake.run(call)).structured == DEFAULT_STEP  # queue empty: the default step
    plain = BackendCall("c2", None, "m", None, None, (ChatMessage("user", "x"),), None, 30)  # type: ignore[arg-type]
    assert (await fake.run(plain)).text == "OK"
    fake.enqueue("TY-CEO", "a" * 40)
    parts = [p async for p in fake.stream(call)]
    assert "".join(p.text for p in parts[:-1]) == "a" * 40  # type: ignore[union-attr]
    assert isinstance(parts[-1], BackendResult)
    scripted = FakeBackend(
        script=lambda c: {"summary_fa": c.actor_ref, "actions": [], "done": True}
    )
    assert (await scripted.run(call)).structured["summary_fa"] == "TY-CEO"
    assert len(fake.calls) == 5  # run x4 + stream


async def test_controller_without_a_database() -> None:
    q = QuotaController(None, None)
    q.check("c", "claude_subscription", 4)  # ok: nothing known yet
    await q.observe(
        "c", "claude-max", {"status": "rejected", "window": "seven_day", "utilization": 2}
    )
    assert q.state("c").status == LIMITED and q.state("c").utilization is None
    with pytest.raises(Throttled) as exc:
        q.check("c", "claude_subscription", 3)
    assert exc.value.retry_after == 300  # no reset time known: try again in 5 minutes
    q.check("c", "claude_subscription", 2)
    q.check("c", "api", 4)  # an API connection is never throttled by the subscription
    assert await q.observe("c", "k", None) is None
    assert await q.observe("c", "k", {"status": "strange"}) is None
    assert await q.load() == 0
    assert await q.scan({"c": "k"}, set()) == []  # no thresholds, no reset passed


# ----------------------------------------------------------- integration --
@needs_db
async def test_warning_pauses_p4_once_per_change(
    make_service: Any, su: asyncpg.Connection, captured: Captured
) -> None:
    svc = make_service(subscription=Scripted(warned(), ok_result(), ok_result()))
    r = await svc.run(
        req(3, meta={"charter": "ceo@1", "run_id": "r1", "step": 1}), "hq-ops", 10_000
    )
    assert r.status == "ok"
    row = await su.fetchrow("SELECT meta FROM llm.calls WHERE id = $1::uuid", r.call_id)
    import json

    meta = json.loads(row["meta"])
    assert meta["charter"] == "ceo@1" and meta["step"] == 1
    assert meta["rate_limit"] == {
        "status": "allowed_warning",
        "window": "five_hour",
        "utilization": 0.85,
    }
    st = await su.fetchrow("SELECT status, source, window_kind, utilization FROM llm.quota_status")
    assert (st["status"], st["source"], st["window_kind"]) == (
        WARNING,
        "sdk_rate_limit_event",
        "five_hour",
    )
    with pytest.raises(RouterError) as exc:
        await svc.run(req(4), "hq-ops", 10_000)
    assert (exc.value.status_code, exc.value.code) == (429, "quota_throttled")
    assert exc.value.retry_after and 30 <= exc.value.retry_after <= 3600
    assert (await svc.run(req(3), "hq-ops", 10_000)).status == "ok"  # P3 still runs
    refused = await su.fetchrow(
        "SELECT status, error_class FROM llm.calls WHERE priority = 4 ORDER BY started_at DESC LIMIT 1"
    )
    assert tuple(refused) == ("rate_limited", "quota_warning")
    await asyncio.sleep(0.3)
    alerts = [m for s, m in captured.messages if s == "hq.alerts.quota"]
    assert (
        len(alerts) == 1
        and alerts[0]["status"] == WARNING
        and alerts[0]["paused_priorities"] == ["P4"]
    )
    assert "hello" not in captured.raw()  # metadata only


@needs_db
async def test_limited_lets_only_p0_to_p2_through(
    make_service: Any, su: asyncpg.Connection
) -> None:
    svc = make_service(subscription=Scripted(warned("rejected"), ok_result()))
    await svc.run(req(2), "hq-ops", 10_000)
    assert svc.quota.state(next(iter(svc.quota.states))).status == LIMITED
    for p in (3, 4):
        with pytest.raises(RouterError) as exc:
            await svc.run(req(p), "hq-ops", 10_000)
        assert exc.value.code == "quota_throttled"
        assert exc.value.status_code == (429 if p == 4 else 503)
    assert (await svc.run(req(1), "hq-ops", 10_000)).status == "ok"


@needs_db
async def test_quota_guard_holds_until_its_reset(make_service: Any, su: asyncpg.Connection) -> None:
    reset = datetime.now(UTC) + timedelta(hours=1)
    svc = make_service(
        subscription=Scripted(
            BackendResult(QUOTA, error_class="usage_limit", quota_resets_at=reset.timestamp())
        )
    )
    await svc.run(req(2), "hq-ops", 10_000)
    cid = next(iter(svc.quota.states))
    s = svc.quota.state(cid)
    assert (s.status, s.source) == (LIMITED, "quota_guard")
    # A later SDK event saying "allowed" does not lower a guard's limit before its reset.
    assert await svc.quota.observe(cid, "claude-max", {"status": "allowed"}) is None
    assert svc.quota.state(cid).status == LIMITED


@needs_db
async def test_a_passed_reset_brings_it_back_and_survives_restarts(
    make_service: Any, su: asyncpg.Connection, db: Any, bus: Any, captured: Captured
) -> None:
    svc = make_service(subscription=Scripted(warned(in_s=1)))
    await svc.run(req(3), "hq-ops", 10_000)
    cid = next(iter(svc.quota.states))
    later = QuotaController(db, bus, now=lambda: datetime.now(UTC) + timedelta(seconds=5))
    assert await later.load() == 1  # the persisted state is read back
    assert later.state(cid).status == Q_OK  # its reset has passed
    changed = await later.scan({cid: "claude-max"}, set())
    assert [c.status for c in changed] == [Q_OK]
    assert await later.scan({cid: "claude-max"}, set()) == []  # told once
    st = await su.fetchrow(
        "SELECT status, source FROM llm.quota_status WHERE connection_id = $1::uuid", cid
    )
    assert tuple(st) == (Q_OK, "reset")


@needs_db
async def test_ledger_windows_when_configured(
    make_service: Any, su: asyncpg.Connection, db: Any, bus: Any
) -> None:
    svc = make_service(subscription=Scripted(ok_result(), ok_result()))
    await svc.run(req(3), "hq-ops", 10_000)
    await svc.run(req(3), "hq-ops", 10_000)  # 2 x 120 tokens on the subscription
    snap = await svc.registry.get()
    sub = next(c for c in snap.connections.values() if c.kind == "claude_subscription")
    companies = set(snap.companies_by_id)
    q = QuotaController(db, bus, thresholds=Thresholds(warn_5h=200, limit_7d=10_000))
    assert [s.status for s in await q.scan({sub.id: sub.key}, companies)] == [WARNING]
    assert q.state(sub.id).source == "ledger_window"
    q2 = QuotaController(db, bus, thresholds=Thresholds(limit_5h=100))
    assert [s.status for s in await q2.scan({sub.id: sub.key}, companies)] == [LIMITED]
    q3 = QuotaController(db, bus, thresholds=Thresholds(warn_5h=10**9))
    assert [s.status for s in await q3.scan({sub.id: sub.key}, companies)] == [Q_OK]
    # A fresh SDK figure decides over the ledger.
    await q3.observe(sub.id, sub.key, {"status": "allowed_warning"})
    assert await q3.scan({sub.id: sub.key}, companies) == []
    assert await svc.quota_scan() == 0
