"""Temporal worker and NATS bridge (prompt 04 §6) on the real Temporal dev
server, Postgres and NATS. The worker runs in-process on its own task queue
and connects as hq_worker, like production."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from nats.js.api import RetentionPolicy, StorageType, StreamConfig
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from hq_api import audit, workflows_client
from hq_api.companies import Companies
from hq_api.db import Database
from hq_api.domain import decisions as D
from hq_api.domain import org, recurrence, recurring
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.worker import jalali, report, schedules
from hq_api.worker.activities import Activities, _plain
from hq_api.worker.bridge import Bridge, call_data, pick
from hq_api.worker.workflows import WORKFLOWS

from .conftest import make_secrets, settings

OWNER = Principal(kind="owner", code="owner", role="owner")
WAIT = 60


# ------------------------------------------------------------------ fixtures --
@pytest.fixture(scope="session")
async def wk(hub: Hub) -> AsyncIterator[dict[str, Any]]:
    s = settings(
        db_user="hq_worker",
        db_password=os.environ["HQ_WORKER_DB_PASSWORD"],
        task_queue=f"hq-core-test-{uuid.uuid4().hex[:8]}",
    )
    db = Database.create(s, pool_size=4)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    whub = Hub(
        settings=s,
        db=db,
        companies=Companies(db, ttl_s=0),
        secrets=make_secrets(),
        policy=hub.policy,
        storage=hub.storage,
        bus=hub.bus,
        temporal=client,
    )
    acts = Activities(whub, client, lock_poll_s=1, escalation_gap_s=0)
    async with Worker(client, task_queue=s.task_queue, workflows=WORKFLOWS, activities=acts.all()):
        yield {"hub": whub, "client": client, "acts": acts, "tq": s.task_queue}
    await db.close()


async def _all(h: Hub) -> list[Any]:
    return await h.companies.ids()


def agent(co: dict[str, Any], dept: str = "GROWTH") -> Principal:
    return Principal(
        kind="agent",
        code=f"{co['code']}-{dept}-MGR",
        role="manager",
        company=co["code"],
        company_id=co["id"],
        department=dept,
    )


async def propose_hire(hub: Hub, co: dict[str, Any], *, expires_at: datetime | None = None) -> str:
    body = D.DecisionIn(
        kind="hire",
        title="Hire a growth analyst",
        what="w",
        why="y",
        expires_at=expires_at,
        payload={
            "company": co["code"],
            "department": "GROWTH",
            "title_fa": "کارشناس رشد",
            "title_en": "Growth analyst",
            "reason": "load",
            "duties": ["campaigns"],
            "model": "claude-sonnet-5-5",
            "effort": "high",
            "permissions": [],
        },
    )
    async with hub.db.tx(await _all(hub)) as tx:
        d = await D.propose(
            tx,
            agent(co),
            company_id=co["id"],
            company_code=co["code"],
            body=body,
            thread_code=f"{co['code']}-GROWTH-MGR",
        )
    ref: str = d["ref"]
    return ref


async def approve(hub: Hub, ref: str) -> None:
    async with hub.db.tx(await _all(hub)) as tx:
        await D.decide(tx, OWNER, await D.load(tx, ref, lock=True), "approved", note="ok")


async def result_of(client: Client, workflow_id: str) -> Any:
    return await asyncio.wait_for(client.get_workflow_handle(workflow_id).result(), WAIT)


async def set_switch(hub: Hub, company_id: Any, state: str) -> None:
    async with hub.db.tx(await _all(hub)) as tx:
        await tx.exec(
            "UPDATE control.kill_switches SET state = :s, reason = 'test' WHERE company_id = :co",
            s=state,
            co=company_id,
        )


async def wait_for(check: Callable[[], Any], seconds: float = 30) -> Any:
    end = asyncio.get_running_loop().time() + seconds
    while True:
        value = await check()
        if value:
            return value
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.3)


# -------------------------------------------------------------- pure units --
@pytest.mark.parametrize(
    ("day", "expected"),
    [
        ("2026-10-17", "1405/07/25"),
        ("2024-03-20", "1403/01/01"),
        ("2025-03-20", "1403/12/30"),
        ("2025-03-21", "1404/01/01"),
        ("2026-09-22", "1405/06/31"),
        ("2026-09-23", "1405/07/01"),
        ("2000-01-01", "1378/10/11"),
    ],
)
def test_jalali(day: str, expected: str) -> None:
    d = datetime.fromisoformat(day).date()
    assert jalali.jalali_str(d) == expected
    assert jalali.jalali_long(datetime(2026, 10, 17).date()) == "25 مهر 1405"


def test_calendar_mapping_matches_the_rule() -> None:
    weekly = schedules.calendar_for(
        recurrence.parse("FREQ=WEEKLY;BYDAY=MO,FR;BYHOUR=9;BYMINUTE=30")
    )
    assert [r.start for r in weekly.day_of_week] == [1, 5]  # Temporal: 0 = Sunday
    assert [r.start for r in weekly.hour] == [9] and [r.start for r in weekly.minute] == [30]
    hourly = schedules.calendar_for(recurrence.parse("FREQ=HOURLY;INTERVAL=6;BYMINUTE=15"))
    assert (hourly.hour[0].start, hourly.hour[0].end, hourly.hour[0].step) == (0, 23, 6)
    daily = schedules.calendar_for(recurrence.parse("FREQ=DAILY;BYHOUR=8,20"))
    assert [r.start for r in daily.hour] == [8, 20] and [r.start for r in daily.minute] == [0]
    monthly = schedules.calendar_for(recurrence.parse("FREQ=MONTHLY;BYMONTHDAY=1,15;BYHOUR=7"))
    assert [r.start for r in monthly.day_of_month] == [1, 15]
    exp = datetime(2027, 1, 1, tzinfo=UTC)
    until = recurrence.parse("FREQ=DAILY;UNTIL=20261201T000000Z")
    assert schedules.recurring_spec(until, "Asia/Tehran", exp).end_at == until.until
    assert schedules.recurring_spec(recurrence.parse("FREQ=DAILY"), "UTC", exp).end_at == exp
    fixed = {d.id: d for d in schedules.fixed(time(8, 0), "Asia/Tehran")}
    assert set(fixed) == set(schedules.FIXED)
    assert fixed[schedules.MORNING].spec.time_zone_name == "Asia/Tehran"
    assert (
        fixed[schedules.MORNING].signature()
        != schedules.fixed(time(9, 0), "Asia/Tehran")[2].signature()
    )


def test_bridge_allow_lists_metadata() -> None:
    data = call_data(
        {
            "call_id": "c1",
            "company": "TY",
            "text": "secret",
            "prompt": "p",
            "model": "m",
            "usage": {"input_tokens": 3, "raw": "x"},
            "actor_ref": "x" * 500,
        }
    )
    assert data == {"call_id": "c1", "company": "TY", "model": "m", "usage": {"input_tokens": 3}}
    assert pick({"level": 90, "note": "body"}, frozenset({"level"})) == {"level": 90}
    assert _plain(
        {"a": uuid.UUID(int=1), "b": [timedelta(seconds=2)], "c": datetime(2026, 1, 1)}
    ) == {"a": str(uuid.UUID(int=1)), "b": [2.0], "c": "2026-01-01 00:00:00"}


# ----------------------------------------------------------------- decisions --
async def test_hire_effect_via_decision_lifecycle(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co)
    await workflows_client.decision_created(wk["hub"], ref)  # the API's call after proposing
    await approve(hub, ref)
    await workflows_client.decision_decided(wk["hub"], ref)
    out = await result_of(wk["client"], f"decision-{ref}")
    assert out["result"] == "applied" and out["employee"] == f"{co['code']}-GROWTH-01"
    async with hub.db.tx(await _all(hub)) as tx:
        emp = await tx.one(
            "SELECT reports_to, hired_by_decision_id, status FROM core.employees WHERE code = :c",
            c=out["employee"],
        )
        assert emp["status"] == "active" and emp["hired_by_decision_id"] is not None
        a = await tx.one(
            "SELECT model, effort FROM llm.assignments WHERE scope_type = 'role' AND scope_ref = :r",
            r=f"{co['code']}:{out['employee']}",
        )
        assert (a["model"], a["effort"]) == ("claude-sonnet-5-5", "high")
        assert (await D.load(tx, ref))["effect_status"] == "applied"
        assert (
            await tx.scalar("SELECT count(*) FROM msg.threads WHERE code = :c", c=out["employee"])
            == 1
        )
        assert (
            await tx.scalar(
                "SELECT count(*) FROM audit.entries WHERE action = 'decision.effect' AND target_ref = :r",
                r=ref,
            )
            == 1
        )
    # A second signal is harmless (idempotent effect).
    await workflows_client.decision_decided(wk["hub"], ref)
    again = await result_of(wk["client"], f"decision-{ref}")
    assert again["result"] in ("applied", "approved")


async def test_rejected_decision_ends_without_effect(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co)
    async with hub.db.tx(await _all(hub)) as tx:
        await D.decide(tx, OWNER, await D.load(tx, ref, lock=True), "rejected", note="no")
    await workflows_client.decision_decided(wk["hub"], ref)
    out = await result_of(wk["client"], f"decision-{ref}")
    assert out == {"ref": ref, "result": "rejected", "effect": "none"}


async def test_pending_decision_expires(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co, expires_at=datetime.now(UTC) + timedelta(seconds=3))
    await workflows_client.decision_created(wk["hub"], ref)
    out = await result_of(wk["client"], f"decision-{ref}")
    assert out == {"ref": ref, "result": "expired"}
    async with hub.db.tx(await _all(hub)) as tx:
        assert (await D.load(tx, ref))["status"] == "expired"
        body = await tx.scalar(
            """SELECT m.body FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
               WHERE t.code = :c ORDER BY m.seq DESC LIMIT 1""",
            c=f"{co['code']}-GROWTH-MGR",
        )
        assert ref in body
    # Expiring twice is a no-op.
    assert (await wk["acts"].decision_expire(ref))["expired"] is False


async def test_effect_waits_while_the_holding_is_locked(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    holding = await hub.companies.holding()
    ref = await propose_hire(hub, co)
    await approve(hub, ref)
    try:
        await set_switch(hub, holding.id, "engaged")
        assert (await wk["acts"].holding_locked())["locked"] is True
        await workflows_client.decision_decided(wk["hub"], ref)
        await asyncio.sleep(3)
        async with hub.db.tx(await _all(hub)) as tx:
            assert (await D.load(tx, ref))["effect_status"] == "pending"
    finally:
        await set_switch(hub, holding.id, "released")
    out = await result_of(wk["client"], f"decision-{ref}")
    assert out["result"] == "applied"


async def test_rejected_effect_is_marked_failed_with_an_urgent_notification(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any], owner_db: Database
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co)
    await approve(hub, ref)
    # The department disappears from the payload's point of view: archive is not
    # enough, so rename the code the payload points to (as hq, test setup only).
    async with owner_db.raw() as tx:  # superuser, triggers off: test setup only
        await tx.exec("SET LOCAL session_replication_role = replica")
        await tx.exec(
            "UPDATE core.departments SET code = 'GONE' WHERE company_id = :co AND code = 'GROWTH'",
            co=co["id"],
        )
    await workflows_client.decision_decided(wk["hub"], ref)
    out = await result_of(wk["client"], f"decision-{ref}")
    assert out["result"] == "effect_failed"
    async with hub.db.tx(await _all(hub)) as tx:
        d = await D.load(tx, ref)
        assert d["effect_status"] == "failed" and "not_found" in d["effect_error"]
        assert (
            await tx.scalar(
                "SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_ref = :r",
                r=ref,
            )
            == 1
        )


async def test_reconcile_decisions_starts_missing_workflows(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co)  # no workflow started on purpose
    out = await wk["acts"].reconcile_decisions()
    assert out["pending"] >= 1
    desc = await wk["client"].get_workflow_handle(f"decision-{ref}").describe()
    assert desc.status is not None
    async with hub.db.tx(await _all(hub)) as tx:
        await D.decide(tx, OWNER, await D.load(tx, ref, lock=True), "rejected", note="cleanup")
    await workflows_client.decision_decided(wk["hub"], ref)
    assert (await result_of(wk["client"], f"decision-{ref}"))["result"] == "rejected"


# ----------------------------------------------------------------- recurring --
async def make_recurring(hub: Hub, co: dict[str, Any]) -> dict[str, Any]:
    async with hub.db.tx(await _all(hub)) as tx:
        w = await W.create(
            tx,
            OWNER,
            company_id=co["id"],
            company_code=co["code"],
            title="Weekly growth digest",
            brief="b",
            kind="recurring",
            priority="P3",
            escrow=W.EscrowIn(
                allowed_action_classes=["A0", "A1"],
                token_cap_per_run=20000,
                usd_cap_per_month=5,
                expires_at=datetime.now(UTC) + timedelta(days=90),
            ),
            schedule=W.ScheduleIn(
                rrule="FREQ=WEEKLY;BYDAY=MO,FR;BYHOUR=9;BYMINUTE=30", timezone="Asia/Tehran"
            ),
        )
        first = await recurring.activate(tx, w, OWNER)
    assert first is not None
    return {**w, "first_run": first}


async def describe(client: Client, sid: str) -> Any:
    return await client.get_schedule_handle(sid).describe()


async def test_recurring_schedule_and_runs(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    w = await make_recurring(hub, co)
    sid = f"recurring-{w['ref']}"
    client = wk["client"]
    try:
        out = await wk["acts"].reconcile_schedules()
        assert out["recurring"][sid] in ("created", "updated", "unchanged")
        assert out["fixed"][schedules.MAINTENANCE] in (
            "created",
            "updated",
            "unchanged",
            "unpaused",
            "paused",
        )
        desc = await describe(client, sid)
        spec = desc.schedule.spec
        assert spec.time_zone_name == "Asia/Tehran"
        cal = spec.calendars[0]
        assert [r.start for r in cal.hour] == [9] and [r.start for r in cal.minute] == [30]
        assert sorted(r.start for r in cal.day_of_week) == [1, 5]
        assert desc.schedule.state.paused is False
        assert (await wk["acts"].reconcile_schedules())["recurring"][sid] == "unchanged"

        # The first run exists (activation); the schedule's action is idempotent.
        rule = recurrence.parse("FREQ=WEEKLY;BYDAY=MO,FR;BYHOUR=9;BYMINUTE=30")
        nxt = recurrence.next_at(
            rule, "Asia/Tehran", w["first_run"]["occurrence_at"] + timedelta(minutes=1)
        )
        assert nxt is not None
        args = [str(w["id"]), nxt.isoformat()]
        r1 = await client.execute_workflow(
            "RecurringRun", args=args, id=f"rr-{uuid.uuid4()}", task_queue=wk["tq"]
        )
        r2 = await client.execute_workflow(
            "RecurringRun", args=args, id=f"rr-{uuid.uuid4()}", task_queue=wk["tq"]
        )
        assert r1["created"] is True and r2["created"] is False
        async with hub.db.tx(await _all(hub)) as tx:
            runs = await tx.all(
                "SELECT ref, budget_tokens, depth FROM work.work WHERE recurrence_of = :w",
                w=w["id"],
            )
        assert len(runs) == 2 and all(r["budget_tokens"] == 20000 for r in runs)

        # Locked company: the run is skipped and the schedule is paused.
        await set_switch(hub, co["id"], "engaged")
        later = recurrence.next_at(rule, "Asia/Tehran", nxt + timedelta(minutes=1))
        assert later is not None
        skipped = await client.execute_workflow(
            "RecurringRun",
            args=[str(w["id"]), later.isoformat()],
            id=f"rr-{uuid.uuid4()}",
            task_queue=wk["tq"],
        )
        assert skipped["created"] is False and "locked" in skipped["reason"]
        assert (await wk["acts"].reconcile_schedules())["recurring"][sid] == "paused"
        assert (await describe(client, sid)).schedule.state.paused is True
        await set_switch(hub, co["id"], "released")
        assert (await wk["acts"].reconcile_schedules())["recurring"][sid] == "unpaused"
        async with hub.db.tx(await _all(hub)) as tx:
            assert (
                await tx.scalar(
                    "SELECT count(*) FROM work.work_events WHERE work_id = :w AND kind = 'run_skipped'",
                    w=w["id"],
                )
                == 1
            )
    finally:
        await set_switch(hub, co["id"], "released")
        async with hub.db.tx(await _all(hub)) as tx:
            await tx.exec("UPDATE work.work SET status = 'cancelled' WHERE id = :w", w=w["id"])
            await tx.exec(
                "UPDATE work.schedules SET status = 'ended' WHERE work_id = :w", w=w["id"]
            )
        out = await wk["acts"].reconcile_schedules()
    assert sid in out["deleted"]
    with pytest.raises(RPCError) as info:
        await describe(client, sid)
    assert info.value.status == RPCStatusCode.NOT_FOUND
    unknown = await wk["acts"].recurring_run(str(uuid.uuid4()), datetime.now(UTC).isoformat())
    assert unknown["created"] is False


async def test_expired_escrows_end(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any], owner_db: Database
) -> None:
    co = await new_company()
    w = await make_recurring(hub, co)
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        await tx.exec(
            "UPDATE work.escrows SET expires_at = now() - interval '1 minute' WHERE work_id = :w",
            w=w["id"],
        )
    assert (await wk["acts"].end_expired_escrows())["ended"] >= 1
    async with hub.db.tx(await _all(hub)) as tx:
        s = await tx.one(
            "SELECT s.status, e.status AS es FROM work.schedules s JOIN work.escrows e ON e.work_id = s.work_id WHERE s.work_id = :w",
            w=w["id"],
        )
    assert (s["status"], s["es"]) == ("ended", "expired")


# ---------------------------------------------------------------- escalation --
async def test_overdue_work_escalates_one_level_at_a_time(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with hub.db.tx(await _all(hub)) as tx:
        emp = await org.hire(
            tx,
            company_id=co["id"],
            company_code=co["code"],
            department_code="GROWTH",
            title_fa="کارشناس",
            title_en="Analyst",
            duties=[],
            permissions=[],
            decision_id=None,
        )
        w = await W.create(
            tx,
            OWNER,
            company_id=co["id"],
            company_code=co["code"],
            title="Late task",
            brief="",
            kind="one_off",
            priority="P2",
            assignee_code=emp["code"],
            due_at=datetime.now(UTC) - timedelta(hours=2),
        )
    for level in (1, 2, 3):
        out = await wk["acts"].escalate_overdue()
        assert f"{w['ref']}:{level}" in out["escalated"]
    assert f"{w['ref']}:4" not in (await wk["acts"].escalate_overdue())["escalated"]
    async with hub.db.tx(await _all(hub)) as tx:
        assert (
            await tx.scalar("SELECT escalation_level FROM work.work WHERE id = :w", w=w["id"]) == 3
        )
        for thread in (f"{co['code']}-GROWTH-MGR", f"{co['code']}-CEO"):
            assert (
                await tx.scalar(
                    """SELECT count(*) FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
                   WHERE t.code = :c AND m.links ->> 'work' = :r""",
                    c=thread,
                    r=w["ref"],
                )
                == 1
            )
        n = await tx.one(
            "SELECT level, link_kind FROM notify.notifications WHERE link_ref = :r", r=w["ref"]
        )
        assert (n["level"], n["link_kind"]) == ("decision", "work")
        assert (
            await tx.scalar(
                "SELECT count(*) FROM work.work_events WHERE work_id = :w AND kind = 'escalated'",
                w=w["id"],
            )
            == 3
        )


# ------------------------------------------------- digest, reports, verify --
async def test_digest_workflow_runs(wk: dict[str, Any]) -> None:
    out = await wk["client"].execute_workflow(
        "NotificationDigest", id=f"nd-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert "khalvat" in out and "batches" in out


async def test_morning_report_once_a_day(hub: Hub, wk: dict[str, Any]) -> None:
    client = wk["client"]
    first = await client.execute_workflow(
        "MorningReport", id=f"mr-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    second = await client.execute_workflow(
        "MorningReport", id=f"mr-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert second == {"created": False, "reason": "already sent today"}
    async with hub.db.tx(await _all(hub)) as tx:
        tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1")
        today = datetime.now(ZoneInfo(tz)).date()
        row = await tx.one(
            """SELECT w.status, d.ref, d.title, d.body, p.code AS producer FROM work.work w
               JOIN cartable.deliverables d ON d.work_id = w.id JOIN core.employees p ON p.id = d.producer_id
               WHERE w.title = :t""",
            t=report.work_title(today),
        )
        assert row["status"] == "done" and row["producer"].endswith("-SYS")
        assert row["title"] == report.title(today) and "گزارش صبحگاهی" in row["title"]
        assert "## شرکت‌ها" in row["body"] and "(HQ)" in row["body"]
        n = await tx.one("SELECT level FROM notify.notifications WHERE link_ref = :r", r=row["ref"])
        assert n["level"] == "report"
    if first.get("created"):
        assert first["deliverable"] == row["ref"]


async def test_report_render_lists_alerts_and_switches() -> None:
    from datetime import date
    from decimal import Decimal

    data = {
        "today": date(2026, 10, 17),
        "risks": {"high": 2, "low": 1},
        "deliverables": {"new_24h": 4, "unrated": 3},
        "unread": 5,
        "companies": [
            {
                "code": "TY",
                "name_fa": "تریدیار",
                "kind": "company",
                "kill_switch": "engaged",
                "decisions_pending": 3,
                "work_open": 7,
                "work_overdue": 1,
                "deliverables_new": 2,
                "tokens_yesterday": 1200,
                "usd_yesterday": Decimal("0.5"),
                "calls_yesterday": 9,
            }
        ],
        "budgets": [
            {
                "company": "TY",
                "scope_type": "company",
                "scope_ref": "TY",
                "period": "month",
                "alert_level": 90,
            }
        ],
    }
    summary, body = report.render(data)
    assert summary.startswith("3 تصمیم")
    assert "ریسک بالا: 2" in body and "به 90٪ رسیده" in body and "کلید توقف فعال:** TY" in body
    assert report.title(date(2026, 10, 17)) == "گزارش صبحگاهی 1405/07/25 / 2026-10-17"


async def test_audit_verify_alerts_when_broken(
    hub: Hub, wk: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ok = await wk["acts"].audit_verify()
    assert ok["ok"] is True and ok["checked"] >= 0

    async def broken(_tx: Any) -> dict[str, Any]:
        return {"ok": False, "checked": 10, "first_bad_seq": 7}

    monkeypatch.setattr(audit, "verify", broken)
    out = await wk["acts"].audit_verify()
    assert out == {"ok": False, "checked": 10, "first_bad_seq": 7}
    async with hub.db.tx(await _all(hub)) as tx:
        assert (
            await tx.scalar(
                "SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_kind = 'audit' AND link_ref = '7'"
            )
            >= 1
        )


async def test_score_job_and_maintenance(hub: Hub, wk: dict[str, Any], owner_db: Database) -> None:
    out = await wk["client"].execute_workflow(
        "ScoreJob", id=f"sj-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert out["employees"] >= 0
    key = uuid.uuid4()
    async with owner_db.raw() as tx:
        await tx.exec(
            """INSERT INTO core.idempotency_keys (principal, key, method, path, body_sha256, created_at)
               VALUES ('test:old', :k, 'POST', '/x', 'h', now() - interval '2 days')""",
            k=key,
        )
    res = await wk["client"].execute_workflow(
        "Maintenance", id=f"mt-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert set(res) == {
        "escalate_overdue",
        "end_expired_escrows",
        "reconcile_decisions",
        "reconcile_schedules",
        "purge",
    }
    assert res["purge"]["idempotency_keys"] >= 1
    async with owner_db.raw() as tx:
        assert (
            await tx.scalar("SELECT count(*) FROM core.idempotency_keys WHERE key = :k", k=key) == 0
        )
    rec = await wk["client"].execute_workflow(
        "Reconcile", id=f"rc-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert schedules.MORNING in rec["fixed"]


# ------------------------------------------------------------------- bridge --
ROUTER_STREAMS = (
    StreamConfig(
        name="HQ_LLM",
        subjects=["hq.llm.>"],
        retention=RetentionPolicy.LIMITS,
        storage=StorageType.FILE,
        max_age=7 * 24 * 3600,
    ),
    StreamConfig(
        name="HQ_ALERTS",
        subjects=["hq.alerts.>"],
        retention=RetentionPolicy.LIMITS,
        storage=StorageType.FILE,
        max_age=30 * 24 * 3600,
    ),
)


async def test_bridge_forwards_metadata_only(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    assert hub.bus is not None
    js = hub.bus.js
    for cfg in ROUTER_STREAMS:
        try:
            await js.add_stream(cfg)
        except Exception:
            await js.update_stream(cfg)
    co = await new_company()
    bridge = Bridge(wk["hub"], idle_s=0.1)
    assert await bridge.subscribe() == 2
    call_id = str(uuid.uuid4())
    base = {
        "call_id": call_id,
        "company": co["code"],
        "actor_ref": f"{co['code']}-CEO",
        "model": "claude-haiku-5-5",
        "text": "SECRET-PROMPT-TEXT",
        "prompt": "SECRET-PROMPT-TEXT",
    }
    await js.publish(f"hq.llm.{co['code']}.call.started", json.dumps(base).encode())
    await js.publish(
        f"hq.llm.{co['code']}.call.finished",
        json.dumps(
            {
                **base,
                "status": "ok",
                "usage": {"input_tokens": 2, "output_tokens": 4, "secret": "x"},
                "equiv_cost_usd": "0.000068",
            }
        ).encode(),
    )
    await js.publish(
        f"hq.alerts.budget.{co['code']}",
        json.dumps(
            {
                "type": "budget",
                "level": 100,
                "percent": 101.5,
                "company": co["code"],
                "scope_type": "company",
                "scope_ref": co["code"],
                "period": "month",
                "note": "SECRET-PROMPT-TEXT",
            }
        ).encode(),
    )
    await js.publish(
        "hq.alerts.llm.anomaly",
        json.dumps(
            {
                "type": "llm_anomaly",
                "actor_ref": f"{co['code']}-CEO",
                "company": co["code"],
                "calls_this_hour": 999,
                "threshold": 100,
                "hour": "2026-10-17T10:00:00+00:00",
            }
        ).encode(),
    )
    await js.publish(
        "hq.alerts.llm.cost_ratio",
        json.dumps(
            {
                "type": "llm.cost_ratio",
                "connection": "claude-max",
                "model": f"m-{co['code']}",
                "ratio": "5.33",
                "since": "x",
                "window_minutes": 60,
                "at": "y",
            }
        ).encode(),
    )
    await js.publish(f"hq.llm.{co['code']}.call.started", b"not json")

    async def drained() -> bool:
        await bridge.drain_once()
        try:
            await js.get_last_msg("HQ_CORE", f"hq.core.{co['code']}.budget.alert")
        except Exception:
            return False
        return True

    await wait_for(drained)
    await bridge.drain_once()
    fin = json.loads(
        (await js.get_last_msg("HQ_CORE", f"hq.core.{co['code']}.llm.call_finished")).data
    )
    started = json.loads(
        (await js.get_last_msg("HQ_CORE", f"hq.core.{co['code']}.llm.call_started")).data
    )
    budget = json.loads(
        (await js.get_last_msg("HQ_CORE", f"hq.core.{co['code']}.budget.alert")).data
    )
    assert fin["type"] == "llm.call.finished" and fin["ref"] == call_id
    assert fin["data"]["usage"] == {"input_tokens": 2, "output_tokens": 4}
    assert started["type"] == "llm.call.started" and started["company"] == co["code"]
    assert budget["type"] == "budget.alert" and budget["data"]["level"] == 100
    for env in (fin, started, budget):
        assert "SECRET" not in json.dumps(env)
    async with hub.db.tx(await _all(hub)) as tx:
        rows = await tx.all(
            "SELECT level, link_ref FROM notify.notifications WHERE company_id = :co AND link_kind = 'treasury'",
            co=co["id"],
        )
        ratio = await tx.scalar(
            "SELECT level FROM notify.notifications WHERE link_ref = :r",
            r=f"cost_ratio:claude-max:m-{co['code']}",
        )
    levels = {r["link_ref"]: r["level"] for r in rows}
    assert levels[f"budget:company:{co['code']}:month"] == "urgent"
    assert levels[f"actor:{co['code']}-CEO"] == "urgent"
    assert ratio == "report"


# ------------------------------------------------------- remaining branches --
async def test_decision_already_expired_and_unscheduled_run(
    hub: Hub, wk: dict[str, Any], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    ref = await propose_hire(hub, co, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    await workflows_client.decision_created(wk["hub"], ref)
    assert (await result_of(wk["client"], f"decision-{ref}"))["result"] == "expired"
    w = await make_recurring(hub, co)
    # Without an occurrence (a manual trigger) the run is created for "now".
    out = await wk["client"].execute_workflow(
        "RecurringRun", args=[str(w["id"])], id=f"rr-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert out["created"] is True
    async with hub.db.tx(await _all(hub)) as tx:
        await tx.exec("UPDATE work.work SET status = 'cancelled' WHERE id = :w", w=w["id"])
        await tx.exec("UPDATE work.schedules SET status = 'ended' WHERE work_id = :w", w=w["id"])


class FakeMsg:
    def __init__(self, subject: str, data: bytes, seq: int = 1) -> None:
        self.subject = subject
        self.data = data
        self.metadata = type("M", (), {"sequence": type("S", (), {"stream": seq})()})()
        self.acked = self.naked = False

    async def ack(self) -> None:
        self.acked = True

    async def nak(self, delay: float | None = None) -> None:
        self.naked = True


class FakeSub:
    def __init__(self, msgs: list[FakeMsg]) -> None:
        self.msgs = msgs

    async def fetch(self, batch: int, timeout: float) -> list[FakeMsg]:  # noqa: ASYNC109 - nats signature
        if not self.msgs:
            raise TimeoutError
        out, self.msgs = self.msgs, []
        return out


async def test_bridge_ignores_unknown_input_and_retries_failures(
    wk: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = Bridge(wk["hub"])
    ignored = [
        FakeMsg("hq.llm.TY.other.thing", b"{}"),
        FakeMsg("hq.llm.TY.call.started", b"[1, 2]"),
        FakeMsg("hq.alerts.something.else", b"{}"),
        FakeMsg("hq.other.stream", b"{}"),
    ]
    for m in ignored:
        await bridge.handle("HQ_ALERTS" if "alerts" in m.subject else "HQ_LLM", m)
    await bridge.handle("HQ_OTHER", FakeMsg("hq.x.y", b"{}"))

    async def boom(stream: str, msg: Any) -> None:
        raise RuntimeError("down")

    bad = FakeMsg("hq.llm.TY.call.started", b"{}")
    bridge._subs = {"HQ_LLM": FakeSub([bad]), "HQ_ALERTS": FakeSub([])}
    monkeypatch.setattr(bridge, "handle", boom)
    assert await bridge.drain_once() == 0
    assert bad.naked and not bad.acked

    # No bus: nothing to bind; the loop keeps going until cancelled.
    lonely = Bridge(
        Hub(
            settings=wk["hub"].settings,
            db=wk["hub"].db,
            companies=wk["hub"].companies,
            secrets=wk["hub"].secrets,
            policy=wk["hub"].policy,
            storage=wk["hub"].storage,
        ),
        idle_s=0.01,
    )
    assert await lonely.subscribe() == 0
    task = asyncio.create_task(lonely.run())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_worker_main_starts_and_stops(
    wk: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from hq_api.worker import __main__ as entry

    env = {
        "DB_HOST": wk["hub"].settings.db_host,
        "DB_USER": "hq_worker",
        "DB_PASSWORD": os.environ["HQ_WORKER_DB_PASSWORD"],
        "NATS_URL": wk["hub"].settings.nats_url,
        "NATS_PASSWORD": os.environ.get("NATS_PASSWORD", ""),
        "TEMPORAL_ADDRESS": wk["hub"].settings.temporal_address,
        "HQ_TASK_QUEUE": f"hq-core-main-{uuid.uuid4().hex[:6]}",
        "OPENBAO_APPROLE_FILE": str(tmp_path / "missing.json"),
        "OPA_URL": wk["hub"].settings.opa_url,
        "HQ_FILES_ROOT": str(tmp_path),
        "LOG_LEVEL": "warning",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(entry, "SECRETS_REFRESH_S", 0.05)
    from hq_common import heartbeat

    health_file = tmp_path / "health.json"
    monkeypatch.setattr(heartbeat, "DEFAULT_PATH", health_file)
    original_run = heartbeat.run

    async def fast_run(check: Any, *, path: Any = health_file, interval: float = 0.1) -> None:
        await original_run(check, path=health_file, interval=0.1)

    monkeypatch.setattr(heartbeat, "run", fast_run)
    stop = asyncio.Event()
    task = asyncio.create_task(entry.main(stop))

    async def healthy() -> bool:
        if task.done():
            task.result()  # surface a crash
        return health_file.exists()

    await wait_for(healthy, 30)
    assert json.loads(health_file.read_text())["temporal"] is True
    await asyncio.sleep(0.2)  # let the secrets refresh run once (OpenBao unreachable: kept)
    stop.set()
    await asyncio.wait_for(task, 30)
    assert (await entry.load_secrets(None)).web_push_ready is False
