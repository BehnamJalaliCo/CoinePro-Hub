"""Prompt 11 §4 and §5 (contract §20.4, §20.5): the three cards and the live
scorecard (PR-090), OKRs per company; and the launch gate: no KPI collection
and no governance job while the holding is locked. No model is ever called."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.domain import gov_kpis as K
from hq_api.domain import gov_okr as OKR
from hq_api.domain import oversight_checks as OC
from hq_api.hub import Hub
from hq_api.worker import schedules

from .conftest import agent_headers, idem
from .p10_support import holding_switch, llm_calls
from .p11b_helpers import acts, card_of, ceo, manual_kpi, quarter, record


async def _checks(su: Any, co: dict[str, Any], oks: list[bool]) -> None:
    await su.execute("SELECT ops.ensure_check_partitions(1)")
    site = await su.fetchval(
        "INSERT INTO ops.sites (company_id, url) VALUES ($1, $2) RETURNING id",
        co["id"],
        f"https://{co['code'].lower()}.example.com/",
    )
    now = datetime.now(UTC)
    for i, ok in enumerate(oks):
        await su.execute(
            """INSERT INTO ops.checks (site_id, company_id, at, ok, status, latency_ms, tls_days_left)
               VALUES ($1, $2, $3, $4, 200, $5, 40)""",
            site,
            co["id"],
            now - timedelta(minutes=5 * (i + 1)),
            ok,
            100 + i,
        )


async def _run_check(hub: Hub, ref: str) -> OC.Checked:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
        companies = {r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")}
        ctx = OC.CheckCtx(tx, holding["id"], holding["code"], companies, datetime.now(UTC), {})
        return await OC.CHECKS[ref](ctx)


# ------------------------------------------------------------------- §4 --
async def test_a_health_kpi_is_measured_by_code_with_no_model(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    await _checks(su, co, [True, True, True, False])
    before = await llm_calls(su)
    async with holding_switch(su, "released"):
        out = await acts(hub).kpi_collect()
    assert out["measured"] >= 1
    k = await card_of(client, owner, co["code"], "health.uptime_24h")
    assert k["state"] == "ok" and k["value"] == 75.0 and k["card"] == "stability"
    assert k["source_ref"]["kind"] == "query" and k["source_ref"]["ref"].startswith("health.uptime_24h:")
    assert k["at"] and k["trend"][-1] == 75.0 and len(k["trend"]) == 30
    assert await llm_calls(su) == before  # by code: no model, no agent run


async def test_a_stale_value_is_stale_and_pr_090_raises_a_finding(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    key = await manual_kpi(client, owner, co, freshness_hours=24)
    r = await record(client, co, key, 1200, at=datetime.now(UTC) - timedelta(hours=30))
    assert r.status_code == 200, r.text
    k = await card_of(client, owner, co["code"], key)
    assert (k["state"], k["value"]) == ("stale", 1200.0)
    checked = await _run_check(hub, "PR-090")
    mine = [p for p in checked.problems if p.company == co["code"]]
    assert [p.key for p in mine] == [f"kpi:{key}"]
    async with holding_switch(su, "released"):
        await acts(hub).kpi_collect()
    events = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1 AND payload->>'ref' = $2",
        f"hq.core.{co['code']}.kpi.stale",
        key,
    )
    assert events == 1
    # A fresh value clears it.
    assert (await record(client, co, key, 1300)).status_code == 200
    assert (await card_of(client, owner, co["code"], key))["state"] == "ok"


async def test_a_manual_kpi_without_a_source_is_422_and_a_query_kpi_is_codes(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    key = await manual_kpi(client, owner, co)
    body = {"company": co["code"], "key": key, "value": 5, "at": datetime.now(UTC).isoformat()}
    r = await client.post(
        "/internal/v1/governance/kpis/record", headers={**await ceo(co), **idem()}, json=body
    )
    assert r.status_code == 422 and "source" in r.json()["fields"]
    r = await client.post(
        "/internal/v1/governance/kpis/record",
        headers={**await ceo(co), **idem()},
        json={**body, "source": {"kind": "metric", "ref": ""}},
    )
    assert r.status_code == 422
    r = await client.post(
        "/internal/v1/governance/kpis/record",
        headers={**await ceo(co), **idem()},
        json={**body, "key": "health.uptime_24h", "source": {"kind": "metric", "ref": "x"}},
    )
    assert r.status_code == 422 and r.json()["fields"]["key"].startswith("a query KPI")
    # Another company's CEO records nothing here; an employee neither.
    other = await new_company()
    r = await client.post(
        "/internal/v1/governance/kpis/record",
        headers={**await ceo(other), **idem()},
        json={**body, "source": {"kind": "metric", "ref": "x"}},
    )
    assert r.status_code == 403


async def test_a_query_outside_the_registry_is_422(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    r = await client.get(f"/api/v1/kpis/{co['code']}", headers=owner)
    version = r.json()["version"]
    keys = {k["key"] for k in r.json()["kpis"]}
    assert {"health.uptime_24h", "treasury.cost_month_usd", "users.active"} <= keys
    bad = {"kpis": [{"key": "sql.drop_everything", "source": {"kind": "query", "query": "sql.drop_everything"},
                     "card": "growth", "name_fa": "x"}]}  # fmt: skip
    r = await client.put(
        f"/api/v1/kpis/{co['code']}", headers={**owner, "If-Match": str(version)}, json=bad
    )
    assert r.status_code == 422 and "not a query of the registry" in r.json()["fields"]["kpis.0.source"]
    # A target change needs the current version (If-Match) and is versioned.
    ok = {"kpis": [{"key": "health.uptime_24h", "target": 99.9}]}
    r = await client.put(f"/api/v1/kpis/{co['code']}", headers=owner, json=ok)
    assert r.status_code == 428
    r = await client.put(
        f"/api/v1/kpis/{co['code']}", headers={**owner, "If-Match": str(version)}, json=ok
    )
    assert r.status_code == 200 and r.json()["version"] == version + 1
    up = next(k for k in r.json()["kpis"] if k["key"] == "health.uptime_24h")
    assert (up["target"], up["version"]) == (99.9, 2)
    r = await client.put(
        f"/api/v1/kpis/{co['code']}", headers={**owner, "If-Match": str(version)}, json=ok
    )
    assert r.status_code == 409


async def test_the_holding_card_aggregates_one_more_company(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    a, b, c = await new_company(), await new_company(), await new_company()
    key = await manual_kpi(client, owner, a, aggregate="sum")
    await manual_kpi(client, owner, b, key)
    for co, v in ((a, 3), (b, 4)):
        assert (await record(client, co, key, v)).status_code == 200
    holding = await card_of(client, owner, "HQ", key)
    assert (holding["value"], holding["state"], holding["source_ref"]["ref"]) == (7.0, "ok", "sum:2")
    await manual_kpi(client, owner, c, key)
    # A company with the KPI but no value yet is left out, never counted as zero.
    assert (await card_of(client, owner, "HQ", key))["value"] == 7.0
    assert (await record(client, c, key, 5)).status_code == 200
    holding = await card_of(client, owner, "HQ", key)
    assert (holding["value"], holding["source_ref"]["ref"]) == (12.0, "sum:3")
    # The holding's own KPIs are on its card too.
    r = await client.get("/api/v1/cards", headers=owner)
    own = {k["key"] for card in r.json() for k in card["kpis"]}
    assert {"hub.services_up_pct", "treasury.agents_cost_month_usd"} <= own


async def test_revenue_without_a_source_is_no_source_never_zero(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    async with holding_switch(su, "released"):
        await acts(hub).kpi_collect()
    k = await card_of(client, owner, co["code"], "revenue.commission_7d_usdt")
    assert (k["state"], k["value"], k["at"], k["source_ref"]) == ("no_source", None, None, None)
    assert all(v is None for v in k["trend"])


async def test_the_scorecard_is_paged_and_searchable(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    r = await client.get("/api/v1/scorecards", headers=owner, params={"q": co["code"]})
    assert r.status_code == 200
    rows = r.json()["items"]
    assert [x["company"] for x in rows] == [co["code"]]
    keys = {k["key"] for k in rows[0]["kpis"]}
    assert {"health.uptime_24h", "revenue.commission_7d_usdt", "users.active", "funnel.conversion_7d",
            "treasury.cost_month_usd"} == keys  # fmt: skip
    assert all({"value", "at", "source_ref", "target", "trend", "state", "card", "direction"} <= set(k)
               for k in rows[0]["kpis"])  # fmt: skip
    page = await client.get("/api/v1/scorecards", headers=owner, params={"limit": 1})
    assert len(page.json()["items"]) == 1 and page.json()["next_cursor"]
    nxt = await client.get(
        "/api/v1/scorecards", headers=owner, params={"limit": 1, "cursor": page.json()["next_cursor"]}
    )
    assert nxt.json()["items"][0]["company"] > page.json()["items"][0]["company"]


async def test_kpi_attainment_is_the_share_of_scorecard_kpis_at_target(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    k1 = await manual_kpi(client, owner, co, target=100, scorecard=True)
    k2 = await manual_kpi(client, owner, co, target=10, scorecard=True)
    await record(client, co, k1, 120)
    await record(client, co, k2, 5)
    async with hub.db.tx([co["id"]]) as tx:
        assert await K.attainment(tx, co["id"]) == 50.0  # one of the two with a value and a target


# ------------------------------------------------------------------- §5 --
async def _draft(client: httpx.AsyncClient, co: dict[str, Any], kpi: str, **kr: Any) -> httpx.Response:
    body = {
        "company": co["code"],
        "quarter": quarter(),
        "objectives": [
            {"title_fa": "رشد کاربران فعال", "why_md": "دلیل", "key_results": [
                {"title_fa": "کاربر فعال", "kpi": kpi, "start": 100, "target": 300, "weight": 2},
                {"title_fa": "رضایت", "metric_fa": "نظرسنجی", "start": 0, "target": 10, **kr},
            ]},
        ],
    }  # fmt: skip
    return await client.post(
        "/internal/v1/governance/okr/draft", headers={**await ceo(co), **idem()}, json=body
    )


async def test_an_okr_is_active_only_with_the_owners_seal(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    key = await manual_kpi(client, owner, co)
    r = await _draft(client, co, key)
    assert r.status_code == 200, r.text
    ref, (ob,) = r.json()["decision"], r.json()["objectives"]
    d = await client.get(f"/api/v1/decisions/{ref}", headers=owner)
    assert (d.json()["kind"], d.json()["payload"]["objective"]) == ("okr", ob)
    assert (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()["status"] == "proposed"
    # A second draft for the quarter waits for the first card.
    assert (await _draft(client, co, key)).status_code == 409
    r = await client.post(
        f"/api/v1/decisions/{ref}/return", headers={**owner, **idem()}, json={"note": "هدف بالاتر"}
    )
    assert r.status_code == 200
    assert (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()["status"] == "draft"
    r = await _draft(client, co, key)
    ref, (ob,) = r.json()["decision"], r.json()["objectives"]
    o = (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()
    kr_metric = next(k for k in o["key_results"] if k["metric_fa"])
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**owner, **idem()},
        json={"amendments": {"key_result_changes": [{"ref": kr_metric["ref"], "target": 20}]}},
    )
    assert r.status_code == 200, r.text
    o = (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()
    assert o["status"] == "active" and o["decision"] == ref
    assert next(k for k in o["key_results"] if k["metric_fa"])["target"] == 20
    events = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1 AND payload->'data'->>'status' = 'active'",
        f"hq.core.{co['code']}.okr.updated",
    )
    assert events == 1
    # An okr card never comes from `propose`.
    r = await client.post(
        "/internal/v1/decisions",
        headers={**await ceo(co), **idem()},
        json={"kind": "okr", "title": "x", "payload": {"objective": ob, "quarter": quarter()}},
    )
    assert r.status_code == 403


async def test_a_kpi_key_result_takes_the_kpis_value_and_work_serves_it(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    key = await manual_kpi(client, owner, co)
    await record(client, co, key, 250)
    r = await _draft(client, co, key)
    ref, (ob,) = r.json()["decision"], r.json()["objectives"]
    await client.post(f"/api/v1/decisions/{ref}/approve", headers={**owner, **idem()}, json={})
    o = (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()
    kr = next(k for k in o["key_results"] if k["kpi"] == key)
    assert (kr["current"], kr["progress"]) == (250.0, 0.75)
    # Work serves a key result (POST /work and work.delegate) and the planner shows it.
    w = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co["code"], "title": "کمپین", "key_result": kr["ref"],
              "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )  # fmt: skip
    assert w.status_code == 201 and w.json()["key_result"] == kr["ref"]
    child = await client.post(
        f"/internal/v1/work/{w.json()['id']}/delegate",
        headers=await agent_headers(f"{co['code']}-CEO"),
        json={"to": f"{co['code']}-GROWTH-MGR", "title": "بخش رشد"},
    )
    assert child.status_code == 201 and child.json()["key_result"] == kr["ref"]
    p = await client.get("/api/v1/planner", headers=owner, params={"scope": f"company:{co['code']}"})
    items = [i for d in p.json()["days"] for i in d["items"] if i["ref"] == w.json()["ref"]]
    assert items and items[0]["key_result"] == kr["ref"]
    other = await new_company()
    bad = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": other["code"], "title": "x", "key_result": kr["ref"]},
    )
    assert bad.status_code == 422


async def test_the_fx_ceo_drafts_no_okr_for_ty(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    ty, fx = await new_company(), await new_company()
    key = await manual_kpi(client, owner, ty)
    body = {"company": ty["code"], "quarter": quarter(), "objectives": [
        {"title_fa": "x", "key_results": [{"title_fa": "y", "kpi": key, "start": 0, "target": 1}]}]}  # fmt: skip
    r = await client.post(
        "/internal/v1/governance/okr/draft", headers={**await ceo(fx), **idem()}, json=body
    )
    assert r.status_code == 403


async def test_a_late_checkin_is_a_finding_and_the_score_follows_the_krs(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    key = await manual_kpi(client, owner, co, target=1, scorecard=True)
    await record(client, co, key, 200)
    r = await _draft(client, co, key)
    ref, (ob,) = r.json()["decision"], r.json()["objectives"]
    await client.post(f"/api/v1/decisions/{ref}/approve", headers={**owner, **idem()}, json={})
    o = (await client.get(f"/api/v1/okr/{ob}", headers=owner)).json()
    metric = next(k for k in o["key_results"] if k["metric_fa"])
    # A check-in of the metric with its evidence moves it.
    r = await client.post(
        "/internal/v1/governance/okr/checkin",
        headers={**await ceo(co), **idem()},
        json={"key_result": metric["ref"], "confidence": 0.6, "note_md": "پیش میرویم", "current": 5,
              "evidence": [{"kind": "link", "ref": "W-000001", "note": "survey"}]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    # Score: KPI KR (weight 2) at 0.5, metric (weight 1) at 0.5 -> 50, not the scorecard's 100.
    async with hub.db.tx([co["id"]]) as tx:
        assert await K.attainment(tx, co["id"]) == 50.0
        assert round(await OKR.active_progress(tx, co["id"]) or 0, 4) == 0.5
    await su.execute(
        """UPDATE governance.key_results SET last_checkin_at = now() - interval '15 days'
           WHERE ref = $1""",
        metric["ref"],
    )
    checked = await _run_check(hub, "PR-116")
    keys = {p.key for p in checked.problems if p.company == co["code"]}
    assert f"okr:{metric['ref']}" in keys
    kpi_kr = next(k for k in o["key_results"] if k["kpi"])
    assert f"okr:{kpi_kr['ref']}" not in keys  # activated today: not late yet


# --------------------------------------------------------------- the gate --
async def test_no_collection_and_no_governance_job_while_the_holding_is_locked(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:  # fmt: skip
    co = await new_company()
    await _checks(su, co, [True])
    before = await su.fetchval("SELECT count(*) FROM governance.kpi_values")
    works = await su.fetchval("SELECT count(*) FROM work.work")
    async with holding_switch(su, "engaged"):
        assert await acts(hub).kpi_collect() == {"skipped": True, "reason": "holding_locked"}
        assert await acts(hub).governance_daily() == {"skipped": True, "reason": "holding_locked"}
    assert await su.fetchval("SELECT count(*) FROM governance.kpi_values") == before
    assert await su.fetchval("SELECT count(*) FROM work.work") == works
    assert (await card_of(client, owner, co["code"], "health.uptime_24h"))["state"] == "no_source"


def test_the_governance_schedules() -> None:
    from datetime import time

    fixed = {d.id: d for d in schedules.fixed(time(8, 0), "Asia/Tehran")}
    kpi = fixed[schedules.KPI_COLLECT]
    assert kpi.workflow == "KpiCollect" and kpi.spec.intervals[0].every == timedelta(minutes=15)
    daily = fixed[schedules.GOVERNANCE_DAILY]
    assert daily.workflow == "GovernanceDaily" and daily.spec.time_zone_name == "Asia/Tehran"
    assert not kpi.paused and not daily.paused  # they gate themselves
