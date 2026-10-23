"""Prompt 12 §8, §10 (contract §21.7): the daily waste report by code and the
ROI of agents, departments and companies."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import roi as ROI
from hq_api.domain import stars as S
from hq_api.domain import waste as WASTE
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.mgmt_activities import MgmtActivities

from .p10_support import holding_switch

TEHRAN = ZoneInfo("Asia/Tehran")


def _day() -> date:
    return date(2045, 1, 1) + timedelta(days=secrets.randbelow(18_000))  # within the API's days


async def _run(su: Any, emp: str, state: str, at: datetime, work: Any = None) -> str:
    return str(
        await su.fetchval(
            """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state, queued_at,
                   started_at, finished_at)
               SELECT company_id, id, $3, 'work', 'test', $2, $4::timestamptz, $4::timestamptz,
                      $4::timestamptz + interval '1 minute'
               FROM core.employees WHERE code = $1 RETURNING id""",
            emp,
            state,
            work,
            at,
        )
    )


async def _call(
    su: Any,
    company_id: Any,
    at: datetime,
    *,
    actor: str = "x",
    tokens: int = 100,
    status: str = "ok",
    run: str | None = None,
    model: str = "claude-sonnet-5-5",
    task: str = "p12b_gen",
    request: str | None = None,
    prefix: str | None = None,
    input_tokens: int | None = None,
    cache_read: int = 0,
    usd: str = "0.01",
) -> None:
    meta = {
        k: v
        for k, v in (("run_id", run), ("request_sha256", request), ("prefix_sha256", prefix))
        if v
    }
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, task_class, priority, caller,
               status, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, meta)
           VALUES (gen_random_uuid(), $2, $2, $1, $3, $4, 2, 'hq-agents', $5, $6, $7, $8, $9, 0, $10, $11)""",
        company_id,
        at,
        actor,
        task,
        status,
        model,
        input_tokens if input_tokens is not None else tokens // 2,
        tokens - (input_tokens if input_tokens is not None else tokens // 2) - cache_read,
        cache_read,
        float(usd),
        json.dumps(meta),
    )


async def _work(su: Any, company_id: Any, status: str = "in_progress") -> Any:
    return await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code, status)
           VALUES ($1, 'one_off', 'w', 'owner', 'owner', $2) RETURNING id""",
        company_id,
        status,
    )


async def test_each_waste_category_is_counted_with_fixed_data(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    cid, emp = co["id"], f"{co['code']}-TECH-MGR"
    day = _day()
    t0 = datetime.combine(day, time(9, 0), tzinfo=TEHRAN).astimezone(UTC)
    await su.execute(
        """INSERT INTO llm.assignments (scope_type, scope_ref, model)
           VALUES ('task_class', 'p12b_tc', 'claude-haiku-5-5'), ('task_class', 'p12b_gen', 'claude-sonnet-5-5')
           ON CONFLICT (scope_type, scope_ref) DO NOTHING"""
    )
    r1 = await _run(su, emp, "failed", t0)
    await _call(su, cid, t0, actor=emp, run=r1, tokens=1000)
    w2 = await _work(su, cid, "cancelled")
    r2 = await _run(su, emp, "done", t0, w2)
    await su.execute(
        """INSERT INTO work.work_events (work_id, company_id, at, kind, actor_kind, actor_code)
           VALUES ($1, $2, $3, 'progress', 'agent', $4)""",
        w2, cid, t0 + timedelta(seconds=30), emp,
    )  # fmt: skip
    await _call(su, cid, t0, actor=emp, run=r2, tokens=200)
    r3 = await _run(su, emp, "done", t0 + timedelta(hours=1), await _work(su, cid))
    await _call(su, cid, t0 + timedelta(hours=1), actor=emp, run=r3, tokens=300)
    w4 = await _work(su, cid)
    for i in range(3):
        r = await _run(su, emp, "done", t0 + timedelta(hours=2, minutes=i), w4)
        await _call(su, cid, t0 + timedelta(hours=2, minutes=i), actor=emp, run=r, tokens=10)
    await _call(su, cid, t0 + timedelta(hours=3), status="error", tokens=50)
    await _call(su, cid, t0 + timedelta(hours=4), request="a" * 64, tokens=40)
    await _call(su, cid, t0 + timedelta(hours=4, minutes=5), request="a" * 64, tokens=40)
    await _call(su, cid, t0 + timedelta(hours=5), prefix="b" * 64, tokens=21000, input_tokens=20000)
    await _call(
        su,
        cid,
        t0 + timedelta(hours=5, minutes=30),
        prefix="b" * 64,
        tokens=21000,
        input_tokens=20000,
    )
    await _call(
        su, cid, t0 + timedelta(hours=6), model="claude-opus-5-5", task="p12b_tc", tokens=70
    )
    await _call(su, cid, t0 + timedelta(hours=7), tokens=5000)  # fine: no category
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await WASTE.store(tx, day)
    mine = next(r for r in rows if r["company_id"] == cid and r["scope"] == "company")
    raw = mine["items"]
    items = {i["category"]: i for i in (json.loads(raw) if isinstance(raw, str) else raw)}
    assert {k: (v["count"], v["tokens"]) for k, v in items.items()} == {
        "failed_runs": (1, 1000),
        "cancelled_work": (1, 200),
        "no_progress_runs": (4, 330),
        "retry_loops": (3, 30),
        "router_errors": (1, 50),
        "duplicate_calls": (1, 40),
        "cache_miss": (1, 21000),
        "over_model": (1, 70),
    }
    assert items["failed_runs"]["top"] == [{"employee": emp, "run_id": r1, "tokens": 1000}]
    total = 1000 + 200 + 300 + 30 + 50 + 80 + 42000 + 70 + 5000
    waste = 1000 + 200 + 300 + 30 + 50 + 40 + 21000 + 70
    assert int(mine["total_tokens"]) == total and int(mine["waste_tokens"]) == waste
    assert float(mine["share"]) == pytest.approx(waste / total, rel=1e-5)
    # Only figures: no prompt or reply text anywhere in the row.
    cols = {r["column_name"] for r in await su.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'llm' AND table_name = 'waste_daily'"
    )}  # fmt: skip
    assert not cols & {"prompt", "response", "text", "body", "system"}
    for i in items.values():
        assert set(i) == {"category", "tokens", "usd", "count", "top"}
        assert all(set(t) <= {"employee", "run_id", "work_ref", "tokens"} for t in i["top"])
    # Efficiency stars read the same figure (one day, one waste share).
    async with hub.db.tx(await hub.companies.ids()) as tx:
        shares = await WASTE.shares_between(tx, day, day + timedelta(days=1))
    assert shares[cid] == pytest.approx(float(mine["share"]), rel=1e-5)
    r = await client.get(f"/api/v1/treasury/waste?day={day}&company={co['code']}", headers=owner)
    assert (
        r.status_code == 200
        and r.json()["waste_tokens"] == waste
        and r.json()["company"] == co["code"]
    )
    rng = await client.get(
        f"/api/v1/treasury/waste?from={day - timedelta(days=1)}&to={day}&company={co['code']}",
        headers=owner,
    )
    assert rng.status_code == 200 and [d["waste_tokens"] for d in rng.json()] == [0, waste]
    holding = await client.get(f"/api/v1/treasury/waste?day={day}", headers=owner)
    assert holding.json()["company"] is None and holding.json()["waste_tokens"] >= waste
    # RLS (llm.waste_daily is a tenant table): another company sees none of it.
    other = await new_company()
    async with hub.db.tx([other["id"]]) as tx:
        assert (
            await tx.scalar("SELECT count(*) FROM llm.waste_daily WHERE company_id = :c", c=cid)
            == 0
        )
    async with hub.db.tx([cid]) as tx:
        assert (
            await tx.scalar("SELECT count(*) FROM llm.waste_daily WHERE company_id = :c", c=cid)
            == 1
        )


async def test_the_waste_job_does_nothing_while_the_holding_is_locked(hub: Hub, su: Any) -> None:
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    day = _day()
    async with holding_switch(su, "engaged"):
        assert await acts.waste_daily(day.isoformat()) == {
            "skipped": True,
            "reason": "holding_locked",
        }
    assert not await su.fetchval("SELECT count(*) FROM llm.waste_daily WHERE day = $1", day)
    async with holding_switch(su, "released"):
        out = await acts.waste_daily(day.isoformat())
    assert out["rows"] >= 1 and out["alerts"] == 0


def test_the_waste_morning_line() -> None:
    assert "مصرفی ثبت نشد" in WASTE.morning_line({"total_tokens": 0})
    line = WASTE.morning_line(
        {"total_tokens": 100, "waste_tokens": 20, "waste_usd": "0.5", "share": 0.2,
         "items": [{"category": "failed_runs", "tokens": 20}]}
    )  # fmt: skip
    assert "20 توکن" in line and "20.0%" in line and "failed_runs" in line


async def test_roi_by_code_revenue_for_companies_only(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co, bare = await new_company(), await new_company()
    anchor = date(2031, 6, 15) + timedelta(days=secrets.randbelow(20) * 31)
    start, _ = S.month_window(anchor)
    key = S.jalali_key(start)
    at = datetime.combine(start + timedelta(days=2), time(12), tzinfo=TEHRAN).astimezone(UTC)
    ceo = f"{co['code']}-CEO"
    for c in (co, bare):
        await _call(su, c["id"], at, actor=f"{c['code']}-CEO", usd="1.00")
        await _call(su, c["id"], at, actor=f"{c['code']}-CEO", usd="1.00")
    emp = await su.fetchrow("SELECT id FROM core.employees WHERE code = $1", ceo)
    w = await _work(su, co["id"])
    for score in (8, 4):
        dl = await su.fetchval(
            """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, created_at)
               VALUES ($1, $2, $3, 'o', $4) RETURNING id""",
            co["id"], w, emp["id"], at,
        )  # fmt: skip
        await su.execute(
            """INSERT INTO cartable.ratings (company_id, deliverable_id, version_no, score, rated_by_code)
               VALUES ($1, $2, 1, $3, 'owner')""",
            co["id"], dl, score,
        )  # fmt: skip
    acct = await su.fetchval(
        """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
               created_by_kind, created_by_code)
           VALUES ($1, 'lbank', 'lbank-affiliate-v2', $2, 'افیلیت', 'owner', 'owner') RETURNING id""",
        co["id"],
        f"lbank-{co['code'].lower()}",
    )
    await su.execute(
        """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
           VALUES ($1, $2, $3, 10, true)""",
        co["id"],
        acct,
        start + timedelta(days=3),
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await ROI.rows(tx, "company", "month", key, co["code"])
        none = await ROI.rows(tx, "company", "month", key, bare["code"])
        people = await ROI.rows(tx, "employee", "month", key, co["code"])
        depts = await ROI.rows(tx, "department", "month", key, co["code"])
    (row,) = rows
    assert (row["cost_usd"], row["accepted"], row["avg_rating"], row["value_points"]) == (
        2,
        1,
        6.0,
        0.8,
    )
    assert row["cost_per_accepted_usd"] == 2 and row["revenue_usd"] == 10 and row["roi"] == 5.0
    assert row["net_usd"] == 8 and row["period_key"] == key
    assert none[0]["revenue_usd"] is None and none[0]["roi"] is None  # no revenue: null, never 0
    me = next(p for p in people if p["key"] == ceo)
    assert me["cost_usd"] == 2 and me["accepted"] == 1
    assert all(p["roi"] is None and p["revenue_usd"] is None for p in people + depts)
    r = await client.get(
        f"/api/v1/treasury/roi?by=employee&period=month&key={key}&company={co['code']}",
        headers=owner,
    )
    assert r.status_code == 200 and all(x["roi"] is None for x in r.json())
    wk = await client.get(
        f"/api/v1/treasury/roi?by=company&period=week&company={co['code']}", headers=owner
    )
    assert wk.status_code == 200 and wk.json()[0]["period"] == "week"
    bad = await client.get("/api/v1/treasury/roi?period=week&key=2031-06-10", headers=owner)
    assert bad.status_code == 422  # a week starts on a Saturday
