"""Prompt 10 §2 (contract §19.1): the revenue radar. A pull of a settled day
through the connector (a fake that answers as egress's lbank-affiliate-v2
reductions do: no exchange is called), the signer account's secret, alerts,
the treasury's cost, company isolation, the launch gate, and PR-103's
reconcile check."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx

from hq_api.domain import affiliate as A
from hq_api.domain import oversight_checks as OC
from hq_api.domain import revenue as V
from hq_api.hub import Hub
from hq_api.worker import schedules
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.revenue_activities import RevenueActivities

from .conftest import agent_headers, body_bytes, idem, step_up, worker_headers
from .p10_fakes import SIGNER_SECRET, FakeConnector, affiliate_account, holding_switch, settled
from .test_egress import FakeBao


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


async def _pull(
    hub: Hub, acct: dict[str, Any], conn: Any, day: Any, kind: str = "manual"
) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        a = await V.account(tx, acct["id"])
        p = await V.create_pull(tx, a, kind=kind, from_day=day, to_day=day)
    return await V.run_pull(hub, txf(hub), conn, p["id"])


async def test_a_complete_day_by_coin_with_subjects_only(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    conn = FakeConnector()
    day = settled(1)
    async with holding_switch(su, "released"):
        out = await _pull(hub, acct, conn, day)
    assert out["state"] == "ok" and out["days_complete"] == 1, out
    d = await su.fetchrow(
        "SELECT * FROM revenue.days WHERE account_id = $1 AND day = $2", acct["id"], day
    )
    assert d["complete"] and d["gaps"] == "[]"
    assert Decimal(d["commission_usdt"]) == Decimal("32")  # 12 USDT + 0.01 ETH x 2000
    by_coin = {c["coin"]: c for c in json.loads(d["by_coin"])}
    assert by_coin["usdt"] == {
        "coin": "usdt",
        "amount": "12",
        "usdt": "12.00000000",
        "price_source": "par",
    }
    assert by_coin["eth"]["usdt"] == "20.00000000"
    assert by_coin["eth"]["price_source"] == f"lbank:kline:eth_usdt:{day.isoformat()}"
    assert (d["new_invitees"], d["min_balance_invitees"], d["active_traders"]) == (150, 75, 7)
    assert Decimal(d["deposits_usdt"]) == 300 and Decimal(d["fees_usdt"]) == Decimal("80.25")
    # The team list came in two pages of 100 with LBank's T+1 UTC+8 day.
    team = [c for c in conn.calls if c["endpoint"] == "invite/user/team/list"]
    assert [c["params"]["start"] for c in team] == [0, 100]
    assert team[0]["params"]["startTime"] == A.day_span(day)[0] and team[0]["local"] == {
        "min_balance": "100"
    }
    assert [
        c["params"]["tradeType"]
        for c in conn.calls
        if c["endpoint"] == "commission/stats/symbol/list"
    ] == [10]
    # Privacy: subjects only; no UID anywhere in the radar.
    inv = await su.fetch(
        "SELECT subject, meets_minimum FROM revenue.invitees WHERE account_id = $1", acct["id"]
    )
    assert len(inv) == 150 and all(len(r["subject"]) == 64 for r in inv)
    assert sum(1 for r in inv if r["meets_minimum"]) == 75
    blob = json.dumps([dict(r) for r in await su.fetch(
        "SELECT source::text, gaps::text, by_coin::text FROM revenue.days WHERE account_id = $1", acct["id"])])  # fmt: skip
    assert "90000001" not in blob
    stages = {r["stage"]: r["count"] for r in await su.fetch(
        "SELECT stage, count FROM growth.funnel_days WHERE company_id = $1 AND day = $2", co["id"], day)}  # fmt: skip
    assert stages == {"referral_verified": 150, "min_balance": 75}
    # The owner's views of it.
    pages = json.loads(d["source"])["pages"]
    assert all(len(p["sha256"]) == 64 for p in pages)


async def test_a_missing_page_is_an_incomplete_day_and_a_retry_fills_it(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    conn = FakeConnector()
    conn.missing_page = 1
    day = settled(0)
    async with holding_switch(su, "released"):
        out = await _pull(hub, acct, conn, day, kind="scheduled")
        assert out["state"] == "incomplete"
        d = await su.fetchrow("SELECT complete, gaps FROM revenue.days WHERE account_id = $1 AND day = $2",
                              acct["id"], day)  # fmt: skip
        assert not d["complete"]
        assert json.loads(d["gaps"]) == [
            {"endpoint": "invite/user/team/list", "page": 1, "error": "upstream_error"}
        ]
        # 11:00 / 18:00: the retry plans exactly the days still incomplete.
        async with hub.db.tx(await hub.companies.ids()) as tx:
            planned = [p for p in await V.plan_pulls(tx, "retry", backfill_days=90)
                       if p["account_id"] == acct["id"]]  # fmt: skip
        assert len(planned) == 1 and planned[0]["kind"] == "retry"
        assert planned[0]["to_day"] == day and planned[0]["state"] == "queued"
        conn.missing_page = None
        out = await V.run_pull(hub, txf(hub), conn, planned[0]["id"])
    assert out["state"] == "ok"
    d = await su.fetchrow("SELECT complete, attempts, new_invitees FROM revenue.days WHERE account_id = $1 AND day = $2",
                          acct["id"], day)  # fmt: skip
    assert (d["complete"], d["attempts"], d["new_invitees"]) == (True, 2, 150)
    # A complete day is never overwritten by a later incomplete pull.
    conn.missing_page = 0
    async with holding_switch(su, "released"):
        await _pull(hub, acct, conn, day)
    d = await su.fetchrow("SELECT complete, new_invitees, attempts FROM revenue.days WHERE account_id = $1 AND day = $2",
                          acct["id"], day)  # fmt: skip
    assert (d["complete"], d["new_invitees"], d["attempts"]) == (True, 150, 3)


async def test_the_signer_secret_reaches_the_worker_connector_only(
    client: httpx.AsyncClient,
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
    owner_session: dict[str, Any],
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    hub.bao = FakeBao({acct["key"]: SIGNER_SECRET})
    body = {"company": co["code"], "exchange": "lbank", "endpoint": "invite/user/team/list"}
    path = "/internal/v1/egress/connectors/lbank-affiliate-v2/pull"
    try:
        async with holding_switch(su, "released"):
            r = await client.post(path, headers=worker_headers(), json=body)
            assert r.status_code == 200, r.text
            grant = r.json()
            assert grant["account"]["secret"] == SIGNER_SECRET
            assert grant["account"]["inject"] == {"kind": "signer", "signer": "lbank-v2"}
            # The keyless price endpoint gets no account at all.
            r = await client.post(
                path, headers=worker_headers(), json={**body, "endpoint": "kline"}
            )
            assert r.status_code == 200 and r.json()["account"] is None
            # An agent, even the company's CEO, never gets a connector's account.
            ceo = await agent_headers(f"{co['code']}-CEO")
            r = await client.post(path, headers=ceo, json=body)
            assert r.status_code == 403 and SIGNER_SECRET not in r.text
            r = await client.post(path, headers=owner_session["headers"], json=body)
            assert r.status_code in (401, 403)
            r = await client.post(
                path.replace("lbank-affiliate-v2", "lbank-trading"),
                headers=worker_headers(),
                json=body,
            )
            assert r.status_code == 404
            # Its entries settle the reservation; no secret in the egress log.
            r = await client.post(
                path.replace("/pull", "/log"), headers=worker_headers(),
                json={"company": co["code"], "reservation": grant["reservation"],
                      "entries": [{"tool": "revenue.pull", "method": "POST", "host": "affiliate.lbank.test",
                                   "status": 200, "bytes_in": 900, "bytes_out": 300, "ms": 40, "class": "A0"}]},
            )  # fmt: skip
            assert r.status_code == 204, r.text
            rows = await su.fetch("SELECT * FROM egress.log WHERE company_id = $1", co["id"])
            assert {r["actor"] for r in rows} == {"worker"} and {r["tool"] for r in rows} == {
                "revenue.pull"
            }
            text = json.dumps([dict(r) for r in rows], default=str)
            for part in (SIGNER_SECRET, *SIGNER_SECRET.split(":")):
                assert part not in text
            # http.request (or web.browse) of an agent with the affiliate account: policy_denied.
            mgr = await agent_headers(f"{co['code']}-TECH-MGR")
            for tool, cls in (("http.request", "A0"), ("web.browse", "A2"), ("web.read", "A0")):
                r = await client.post(
                    "/internal/v1/egress/reserve", headers=mgr,
                    json={"tool": tool, "class": cls, "method": "GET", "account": acct["key"],
                          "url": "https://affiliate.lbank.test/affiliate-api/v2/trade/user/team"},
                )  # fmt: skip
                assert r.status_code == 403 and r.json()["code"] == "policy_denied", (tool, r.text)
                assert SIGNER_SECRET not in r.text
            refused = await su.fetchval(
                "SELECT count(*) FROM egress.log WHERE company_id = $1 AND blocked_reason = 'policy_denied'",
                co["id"],
            )
            assert refused == 3
    finally:
        hub.bao = None


async def test_the_owner_registers_an_account_sealed_and_pulls_by_hand(
    client: httpx.AsyncClient,
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
    owner_session: dict[str, Any],
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    # A §18.13 service account whose policy is the lbank-v2 signer.
    acct_body = {"key": f"aff-{co['code'].lower()}", "site": "affiliate.lbank.test", "title_fa": "افیلیت",
                 "companies": [co["code"]], "policy": {"inject": {"kind": "signer", "signer": "lbank-v2"}}}  # fmt: skip
    content = body_bytes(acct_body)
    seal = await step_up(hub, sid, "account.put", hashlib.sha256(content).hexdigest())
    r = await client.post("/api/v1/tools/accounts", content=content,
                          headers={**h, **seal, **idem(), "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 201, r.text
    bad = {**acct_body, "key": "aff-bad", "policy": {"inject": {"kind": "signer"}}}
    content = body_bytes(bad)
    seal = await step_up(hub, sid, "account.put", hashlib.sha256(content).hexdigest())
    r = await client.post("/api/v1/tools/accounts", content=content,
                          headers={**h, **seal, **idem(), "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 422
    body = {
        "company": co["code"],
        "exchange": "lbank",
        "service_account": acct_body["key"],
        "title_fa": "LBank",
    }
    content = body_bytes(body)
    r = await client.post("/api/v1/revenue/accounts", content=content,
                          headers={**h, **idem(), "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 403  # no step-up: no account
    seal = await step_up(hub, sid, "revenue.account", hashlib.sha256(content).hexdigest())
    r = await client.post("/api/v1/revenue/accounts", content=content,
                          headers={**h, **seal, **idem(), "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 201, r.text
    acct = r.json()
    assert (acct["status"], acct["adapter"], acct["company"]) == (
        "not_configured",
        "lbank-affiliate-v2",
        co["code"],
    )
    assert "secret" not in r.text
    # A plain bearer account is not a connector's account.
    plain = {**body, "exchange": "bybit", "service_account": "nope-account"}
    content = body_bytes(plain)
    seal = await step_up(hub, sid, "revenue.account", hashlib.sha256(content).hexdigest())
    r = await client.post("/api/v1/revenue/accounts", content=content,
                          headers={**h, **seal, **idem(), "Content-Type": "application/json"})  # fmt: skip
    assert r.status_code == 422
    listed = (await client.get("/api/v1/revenue/accounts", headers=h)).json()
    assert any(a["id"] == acct["id"] for a in listed)
    # The manual pull: Idempotency-Key, at most 31 days, never an unsettled day.
    url = f"/api/v1/revenue/accounts/{acct['id']}/pull"
    last = A.last_settled_day()
    assert (await client.post(url, headers=h)).status_code == 422
    r = await client.post(url, headers={**h, **idem()},
                          params={"from": (last - timedelta(days=40)).isoformat(), "to": last.isoformat()})  # fmt: skip
    assert r.status_code == 422
    r = await client.post(
        url, headers={**h, **idem()}, params={"to": (last + timedelta(days=1)).isoformat()}
    )
    assert r.status_code == 422
    key = idem()
    async with holding_switch(su, "released"):
        r = await client.post(
            url, headers={**h, **key}, params={"from": (last - timedelta(days=2)).isoformat()}
        )
        assert r.status_code == 202, r.text
        again = await client.post(
            url, headers={**h, **key}, params={"from": (last - timedelta(days=2)).isoformat()}
        )
    assert again.json()["id"] == r.json()["id"]  # one pull, not two
    assert (
        r.json()["state"] == "queued"
        and r.json()["kind"] == "manual"
        and r.json()["from"] < r.json()["to"]
    )
    # While the holding is locked the pull is recorded skipped; nothing runs.
    async with holding_switch(su, "engaged"):
        r = await client.post(url, headers={**h, **idem()})
    assert (r.json()["state"], r.json()["skipped_reason"]) == ("skipped", "holding_locked")


async def test_a_fifty_percent_drop_raises_exactly_one_alert(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    day = settled(0)
    for k in range(1, 5):  # the same weekday, the four weeks before: 100 USDT each
        await su.execute(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete, source)
               VALUES ($1, $2, $3, 100, true, '{"adapter": "lbank-affiliate-v2"}')""",
            co["id"], acct["id"], day - timedelta(days=7 * k),
        )  # fmt: skip
    conn = FakeConnector(usdt="50", eth=None)
    async with holding_switch(su, "released"):
        await _pull(hub, acct, conn, day)
        await _pull(hub, acct, conn, day)  # the same incident again: no second alert
    alerts = await su.fetch("SELECT kind, incident_key, notification_id FROM revenue.alerts WHERE company_id = $1",
                            co["id"])  # fmt: skip
    drops = [a for a in alerts if a["kind"] == "drop"]
    assert len(drops) == 1 and drops[0]["incident_key"] == f"drop:{acct['id']}:{day.isoformat()}"
    n = await su.fetchrow(
        "SELECT level, title_fa FROM notify.notifications WHERE id = $1",
        drops[0]["notification_id"],
    )
    assert n["level"] == "report" and co["code"] in n["title_fa"]
    ceo_line = await su.fetchval(
        """SELECT count(*) FROM msg.messages m JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.code = $1 AND m.body LIKE 'هشدار رادار درآمد%'""",
        f"{co['code']}-CEO",
    )
    assert ceo_line == 1
    # 60% is the line: 70 USDT raises nothing.
    other = await new_company()
    acct2 = await affiliate_account(su, other)
    for k in range(1, 5):
        await su.execute(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
               VALUES ($1, $2, $3, 100, true)""",
            other["id"], acct2["id"], day - timedelta(days=7 * k),
        )  # fmt: skip
    async with holding_switch(su, "released"):
        await _pull(hub, acct2, FakeConnector(usdt="70", eth=None), day)
    assert await su.fetchval("SELECT count(*) FROM revenue.alerts WHERE company_id = $1 AND kind = 'drop'",
                             other["id"]) == 0  # fmt: skip


async def test_two_failed_pulls_alert_once_and_task_the_platform_sre(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    holding = await su.fetchrow("SELECT id, code FROM core.companies WHERE kind = 'holding'")
    sre = await su.fetchval(
        "SELECT code FROM core.employees WHERE company_id = $1 AND role = 'hub_platform_sre' AND status = 'active'",
        holding["id"],
    )
    conn = FakeConnector()
    conn.fail_all = True
    async with holding_switch(su, "released"):
        first = await _pull(hub, acct, conn, settled(0))
        assert first["state"] == "failed"
        assert await su.fetchval("SELECT count(*) FROM revenue.alerts WHERE company_id = $1 AND kind = 'pull_failed'",
                                 co["id"]) == 0  # fmt: skip
        await _pull(hub, acct, conn, settled(0))
        await _pull(hub, acct, conn, settled(0))
    row = await su.fetchrow(
        "SELECT status, failures_in_row, last_error FROM revenue.accounts WHERE id = $1", acct["id"]
    )
    assert (row["status"], row["failures_in_row"], row["last_error"]) == (
        "error",
        3,
        "upstream_error",
    )
    alerts = await su.fetch("SELECT work_id FROM revenue.alerts WHERE company_id = $1 AND kind = 'pull_failed'",
                            co["id"])  # fmt: skip
    assert len(alerts) == 1
    if sre:  # the platform SRE, when the holding has one, gets one task
        assert alerts[0]["work_id"] is not None


async def test_token_cost_comes_from_the_treasury_ledger(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    day = settled(0)
    await su.execute(
        """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
           VALUES ($1, $2, $3, 40, true)""",
        co["id"], acct["id"], day,
    )  # fmt: skip
    start = datetime.combine(day, time(0, 0), A.UTC8)
    for at, cost, equiv in ((start + timedelta(hours=2), "1.25", "0.5"), (start + timedelta(hours=23), None, "2"),
                            (start - timedelta(minutes=1), "9", "9")):  # fmt: skip
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller, status,
                   input_tokens, output_tokens, cost_usd, equiv_cost_usd)
               VALUES (gen_random_uuid(), $1, $2, 'test', 'general', 3, 'tests', 'ok', 10, 1, $3::numeric, $4::numeric)""",
            at, co["id"], cost, equiv,
        )  # fmt: skip
    ledger = await su.fetchval(
        """SELECT sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)) FROM llm.calls
           WHERE company_id = $1 AND started_at >= $2 AND started_at < $3""",
        co["id"], start, start + timedelta(days=1),
    )  # fmt: skip
    r = await client.get(
        "/api/v1/revenue/summary", headers=owner, params={"period": "day", "company": co["code"]}
    )
    assert r.status_code == 200, r.text
    s = r.json()
    mine = next(c for c in s["by_company"] if c["company"] == co["code"])
    assert Decimal(mine["token_cost_usd"]) == ledger == Decimal("3.75")
    assert Decimal(mine["usdt"]) == 40 and Decimal(mine["net_usd"]) == Decimal(40) - ledger
    assert (
        mine["share"] == 1.0
        and Decimal(s["total_usdt"]) == 40
        and s["from"] == s["to"] == day.isoformat()
    )
    assert [t["day"] for t in s["trend"]] == [day.isoformat()] and Decimal(
        s["trend"][0]["usdt"]
    ) == 40
    days = (
        await client.get("/api/v1/revenue/days", headers=owner, params={"company": co["code"]})
    ).json()
    assert days[0]["day"] == day.isoformat() and days[0]["complete"] is True
    assert set(days[0]["source"]) == {"adapter", "endpoints"}
    week = (
        await client.get("/api/v1/revenue/summary", headers=owner, params={"period": "week"})
    ).json()
    assert len(week["trend"]) == 7


async def test_fx_never_sees_the_revenue_of_ty(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    ty, fx = await new_company(), await new_company()
    acct = await affiliate_account(su, ty)
    day = settled(0)
    await su.execute(
        """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
           VALUES ($1, $2, $3, 55, true)""",
        ty["id"], acct["id"], day,
    )  # fmt: skip
    async with hub.db.tx([fx["id"]]) as tx:
        for table in ("revenue.days", "revenue.accounts", "revenue.invitees", "revenue.alerts"):
            assert (
                await tx.scalar(f"SELECT count(*) FROM {table} WHERE company_id = :c", c=ty["id"])
                == 0
            )
    body = {"from": (day - timedelta(days=6)).isoformat(), "to": day.isoformat()}
    r = await client.post("/internal/v1/revenue/read", headers=await agent_headers(f"{fx['code']}-CEO"),
                          json={**body, "company": ty["code"]})  # fmt: skip
    assert r.status_code == 403 and "55" not in r.text
    r = await client.post(
        "/internal/v1/revenue/read", headers=await agent_headers(f"{ty['code']}-CEO"), json=body
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["total_usdt"]) == 55 and r.json()["company"] == ty["code"]
    # The GROWTH manager is no reader of the radar.
    r = await client.post("/internal/v1/revenue/read", headers=await agent_headers(f"{ty['code']}-GROWTH-MGR"),
                          json=body)  # fmt: skip
    assert r.status_code == 403
    # FIN reads it; the holding's advisor reads any company.
    r = await client.post("/internal/v1/revenue/read", headers=await agent_headers(f"{ty['code']}-FIN-MGR"),
                          json={**body, "by": "account"})  # fmt: skip
    assert r.status_code == 200 and r.json()["accounts"][0]["account"] == str(acct["id"])


async def test_nothing_is_pulled_while_the_holding_is_locked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    conn = FakeConnector()
    acts = RevenueActivities(hub, txf(hub), connector=conn)
    async with holding_switch(su, "engaged"):
        planned = await acts.revenue_plan("scheduled")
        assert (
            planned["skipped_pulls"]
            and not planned["queued"]
            and planned["reason"] == "holding_locked"
        )
        rows = await su.fetch(
            "SELECT state, skipped_reason, kind FROM revenue.pulls WHERE account_id = $1",
            acct["id"],
        )
        assert [(r["state"], r["skipped_reason"]) for r in rows] == [("skipped", "holding_locked")]
        retry = await acts.revenue_plan("retry")
        assert not retry["queued"]
        # A pull queued before the lock does nothing either.
        async with hub.db.tx(await hub.companies.ids()) as tx:
            a = await V.account(tx, acct["id"])
            p = await V.create_pull(tx, a, kind="manual", from_day=settled(1), to_day=settled(0))
        out = await acts.revenue_pull(str(p["id"]))
        assert out == {"skipped": True, "reason": "holding_locked", "pull": str(p["id"])}
    assert conn.calls == []  # no connector call, no outside call
    assert (
        await su.fetchval("SELECT count(*) FROM revenue.days WHERE account_id = $1", acct["id"])
        == 0
    )
    assert await su.fetchval("SELECT state FROM revenue.pulls WHERE id = $1", p["id"]) == "skipped"
    # Released: the first scheduled run is the 90-day backfill.
    async with holding_switch(su, "released"):
        planned = await acts.revenue_plan("scheduled")
    mine = await su.fetch(
        "SELECT kind, from_day, to_day FROM revenue.pulls WHERE account_id = $1 AND state = 'queued'",
        acct["id"],
    )
    assert [(r["kind"], (r["to_day"] - r["from_day"]).days) for r in mine] == [("backfill", 89)]


async def test_pr_103_reconciles_the_radar_with_its_pages(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    async with holding_switch(su, "released"):
        await _pull(hub, acct, FakeConnector(), settled(0))

    async def check() -> list[Any]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
            companies = {
                r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")
            }
            ctx = OC.CheckCtx(tx, holding["id"], holding["code"], companies, datetime.now(UTC), {})
            checked = await OC.CHECKS["PR-103"](ctx)
        assert co["code"] in checked.companies
        return [p for p in checked.problems if p.company == co["code"]]

    assert await check() == []
    await su.execute(
        "UPDATE revenue.days SET commission_usdt = commission_usdt + 1, new_invitees = 149 WHERE account_id = $1",
        acct["id"],
    )
    problems = await check()
    assert len(problems) == 1 and problems[0].key.startswith(f"revenue:{acct['id']}:")
    assert "commission_usdt" in problems[0].body_md and "new_invitees" in problems[0].body_md
    # PR-103 is seeded paused (its file), its checker waits for the owner's keys.
    status = await su.fetchval(
        "SELECT status FROM oversight.current_protocols WHERE ref = 'PR-103'"
    )
    assert status in (None, "paused")


def test_the_pull_and_growth_schedules() -> None:
    fixed = {d.id: d for d in schedules.fixed(time(8, 0), "Asia/Tehran")}
    pull = fixed[schedules.REVENUE_PULL]
    assert (pull.workflow, pull.args, pull.paused) == ("RevenuePulls", ("scheduled",), False)
    cal = pull.spec.calendars[0]
    assert (cal.hour[0].start, cal.minute[0].start, pull.spec.time_zone_name) == (
        7,
        0,
        "Asia/Tehran",
    )
    retry = fixed[schedules.REVENUE_RETRY]
    assert retry.args == ("retry",) and [h.start for h in retry.spec.calendars[0].hour] == [11, 18]
    assert fixed[schedules.RESCUE].workflow == "RescueFollowUps"
    assert fixed[schedules.FEEDBACK_BATCH].workflow == "FeedbackBatch"
    weekly = fixed[schedules.SUPPORT_WEEKLY]
    assert weekly.spec.calendars[0].day_of_week[0].start == 6  # Saturday


def test_the_settlement_day_is_t_plus_one_at_utc_plus_8() -> None:
    # 2026-10-22 03:30 UTC (07:00 Tehran) is 11:30 at UTC+8: the day before is settled.
    now = datetime(2026, 10, 22, 3, 30, tzinfo=UTC)
    assert A.last_settled_day(now).isoformat() == "2026-10-21"
    start, end = A.day_span(A.last_settled_day(now))
    assert start == int(datetime(2026, 10, 21, tzinfo=A.UTC8).timestamp() * 1000)
    assert end - start == 86_400_000 - 1
    assert dataclasses.is_dataclass(A.DayPull)
