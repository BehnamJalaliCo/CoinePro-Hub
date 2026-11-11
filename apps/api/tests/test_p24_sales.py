"""Prompt 24 (contract §33.1, §33.4-§33.6): usage in the advisor's words, the small CRM of each
company, affiliate follow-up and the decisions' money impact.

The model is a fake router (`workflows_client.route_order`, or the `ask` the worker passes), every
request kept: each call must carry its own task class, and no figure may come from it (a text with a
made-up figure is replaced by code's own).
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from hq_api import workflows_client
from hq_api.domain import affiliate_gaps as AG
from hq_api.domain import home as HM
from hq_api.domain import impact as IM
from hq_api.domain import leads as L
from hq_api.domain import usage as U
from hq_api.hub import Hub

from .conftest import agent_headers, idem

API = "/api/v1"
LINES = [
    "دیروز بیشتر مصرف برای کار شرکت‌ها بود و روال آرامی داشت.",
    "بخش مشاور سهم کوچکی داشت و چیز غیرعادی دیده نشد.",
    "هزینه‌ی صدا و تبلیغات هم پایین ماند.",
]
SAVING = "برای صرفه‌جویی، کارهای تکراری را در یک نوبت انجام دهید."
DRAFT = "سلام، از توجه شما به خدمات ما سپاسگزاریم. اگر پرسشی دارید خوشحال میشویم کمک کنیم."


class Router:
    """The router, faked: every request kept; `handlers` answer by the request's purpose."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def of(self, task_class: str) -> list[dict[str, Any]]:
        return [r for r in self.seen if r["task_class"] == task_class]

    async def ask(self, req: dict[str, Any]) -> Any:
        self.seen.append(req)
        fn = self.handlers.get(req["meta"]["purpose"])
        got = fn(req) if fn else None
        return {"routes": [got]} if got is not None else None

    async def __call__(self, hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> Any:
        return await self.ask(req)


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> Router:
    r = Router()
    r.handlers["usage_report"] = lambda req: {"lines_fa": LINES, "saving_fa": SAVING}
    r.handlers["sales_followup"] = lambda req: {"draft_fa": DRAFT}
    monkeypatch.setattr(workflows_client, "route_order", r)
    return r


# ============================================================ task classes ==
def router_seed() -> dict[str, Any]:
    up = Path(__file__).resolve().parents
    f = up[len(up) - 1] / "services/llm-router/seed/task_classes.yaml"
    if len(up) > 3:
        f = up[3] / "services/llm-router/seed/task_classes.yaml"
    if not f.exists():
        return {}
    return {r["key"]: r for r in yaml.safe_load(f.read_text("utf-8"))["task_classes"]}


async def test_the_router_task_classes_are_seeded_by_the_migration(su: Any) -> None:
    rows = {
        r["key"]: r
        for r in await su.fetch(
            "SELECT key, transferable, description FROM llm.task_classes WHERE key = ANY($1::text[])",
            ["usage_report", "sales_followup", "decision_impact"],
        )
    }
    assert set(rows) == {"usage_report", "sales_followup", "decision_impact"}
    assert not any(r["transferable"] for r in rows.values())
    seed = router_seed()
    if seed:  # the router's seed holds the same rows (where the checkout is there)
        for key, r in rows.items():
            assert seed[key]["description"] == r["description"]
    assert U.TASK_CLASS == "usage_report" and L.TASK_CLASS == "sales_followup"
    assert IM.TASK_CLASS == "decision_impact"


# ============================================================ usage report ==
async def test_the_usage_report_numbers_by_code_words_by_one_call(
    client: httpx.AsyncClient, owner: dict[str, str], router: Router, su: Any
) -> None:
    # (an owner's report of the last minute is returned as it is: none from an earlier test)
    await su.execute("DELETE FROM sales.usage_reports WHERE made_by = 'owner'")
    r = await client.post(f"{API}/usage/reports", json={"period": "day"}, headers=owner)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["ref"].startswith("UR-") and rep["period"] == "day" and rep["words"] == "model"
    assert rep["text"] == {"lines_fa": LINES, "saving_fa": SAVING}
    pack = rep["pack"]
    assert set(pack) >= {"period", "from", "to", "by_domain", "by_company", "top_runs", "voice_usd",
                         "lines", "ads_spend_usd", "vs_prev", "anomalies"}  # fmt: skip
    calls = router.of("usage_report")
    assert len(calls) == 1
    req = calls[0]
    assert req["effort"] == "low" and req["max_output_tokens"] <= 4000 and req["json_schema"]
    assert json.loads(req["prompt"])["pack"]["period"] == "day"
    # asked again within a minute: the same report, no second call
    again = await client.post(f"{API}/usage/reports", json={"period": "day"}, headers=owner)
    assert again.json()["ref"] == rep["ref"] and len(router.of("usage_report")) == 1
    r = await client.get(
        f"{API}/usage/reports", params={"period": "day", "limit": 1}, headers=owner
    )
    assert r.status_code == 200 and r.json()["items"][0]["ref"] == rep["ref"]
    assert (
        await client.get(f"{API}/usage/reports", params={"limit": 201}, headers=owner)
    ).status_code == 422
    ev = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.usage.report' AND payload->>'ref' = $1",
        rep["ref"],
    )
    assert ev >= 1  # (a round trip of the migrations in this database starts the refs again)


async def test_a_made_up_figure_is_never_kept(hub: Hub, router: Router) -> None:
    router.handlers["usage_report"] = lambda req: {
        "lines_fa": [*LINES[:2], "مصرف دیروز ۹۸۷۶۵۴ توکن بود."],
        "saving_fa": SAVING,
    }
    row = await U.make(hub, "week", made_by="owner")
    rep = U.render(row)
    assert rep.words == "code" and rep.text is not None
    assert U.numbers_ok(" ".join([*rep.text.lines_fa, rep.text.saving_fa]), rep.pack)
    # a model that does not answer: the words are code's as well
    router.handlers.pop("usage_report")
    rep = U.render(await U.make(hub, "day", made_by="owner"))
    assert rep.words == "code" and 3 <= len(rep.text.lines_fa if rep.text else []) <= 8


async def test_the_scheduled_reports_are_codes_and_go_to_the_technical_team(
    hub: Hub, router: Router, su: Any, new_company: Callable[..., Any]
) -> None:
    """The owner's rule of 2026-11-06: a scheduled report makes no model call, the weekly
    one goes to the head of AI operations, and the owner's morning gets only a company
    over its money budget, in one plain line in dollars."""
    # a schedule makes one report per period (a second tick finds it)
    now = datetime.now(UTC)
    await su.execute("DELETE FROM sales.usage_reports WHERE made_by = 'schedule'")
    day = await U.make(hub, "day", made_by="schedule", ask=router.ask, now=now)
    again = await U.make(hub, "day", made_by="schedule", ask=router.ask, now=now)
    assert again["ref"] == day["ref"] and day["words"] == "code"
    assert router.of("usage_report") == []
    co = await new_company()
    name = await su.fetchval("SELECT COALESCE(name_fa, code) FROM core.companies WHERE id = $1",
                             co["id"])  # fmt: skip
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, usd_limit)
           VALUES ($1, 'company', $2, 'month', 10)
           ON CONFLICT (scope_type, scope_ref, period) DO UPDATE SET usd_limit = 10, enabled = true""",
        co["id"], co["code"],
    )  # fmt: skip
    await su.execute(
        """INSERT INTO llm.usage (company_id, scope_type, scope_ref, period, period_start, usd)
           VALUES ($1, 'company', $2, 'month', date_trunc('month', now() AT TIME ZONE 'UTC')::date, 12.5)
           ON CONFLICT (scope_type, scope_ref, period, period_start) DO UPDATE SET usd = 12.5""",
        co["id"], co["code"],
    )  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            from hq_api.domain.gov_common import owner_tz

            tz = await owner_tz(tx)
            today = HM.owner_today(tz, now)
            money = await U.morning_lines(tx, tz, today)
            lines = await HM.morning_lines(tx, tz, today)
        assert len(money) == 1 and name in money[0] and "12 از 10 دلار" in money[0]
        assert any("12 از 10 دلار" in x for x in lines) and len(lines) <= 5
        assert not any("توکن" in x for x in lines)
    finally:
        await su.execute(
            "DELETE FROM llm.usage WHERE scope_type = 'company' AND scope_ref = $1", co["code"]
        )
        await su.execute(
            "DELETE FROM llm.budgets WHERE scope_type = 'company' AND scope_ref = $1", co["code"]
        )
    week = await U.make(hub, "week", made_by="schedule", ask=router.ask, now=now)
    sent = week["delivered"]
    assert sent.get("notice") and not sent.get("thread") and week["words"] == "code"
    n = await su.fetchrow(
        "SELECT body_fa, domain, owner_visible, routed_to FROM notify.notifications WHERE id = $1",
        uuid.UUID(sent["notice"]),
    )
    assert (n["domain"], n["owner_visible"]) == ("infra", False)
    assert n["routed_to"] == (sent["to"] or None) and "جزئیات" in n["body_fa"]
    assert router.of("usage_report") == []
    say, show = U.spoken(week)
    assert say and show


async def test_usage_reports_are_the_owner_s(client: httpx.AsyncClient, new_company: Any) -> None:
    co = await new_company()
    ceo = await agent_headers(f"{co['code']}-CEO")
    assert (await client.get(f"{API}/usage/reports", headers=ceo)).status_code in (401, 403)


# =================================================================== leads ==
async def test_leads_by_hand_change_and_pipeline(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    router: Router,
) -> None:
    co = await new_company()
    url = f"{API}/companies/{co['code']}/leads"
    r = await client.post(url, json={"contact": "+989121234567", "name_fa": "علی"}, headers=owner)
    assert r.status_code == 422  # a phone number is never a pseudonym
    r = await client.post(
        url,
        json={"name_fa": "علی", "source": "site", "value_usdt": "40", "contact": "site:ali-0001"},
        headers={**owner, **idem()},
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    assert (
        lead["ref"].startswith("LD-")
        and lead["stage"] == "new"
        and lead["events"][0]["kind"] == "created"
    )
    # the same pseudonym is the same lead
    r = await client.post(url, json={"contact": "site:ali-0001"}, headers=owner)
    assert r.json()["ref"] == lead["ref"]
    r2 = await client.post(url, json={"name_fa": "سارا"}, headers=owner)
    sara = r2.json()
    assert sara["contact"].startswith("m-")
    ref = lead["ref"]
    r = await client.patch(f"{API}/leads/{ref}", json={"stage": "contacted"}, headers=owner)
    assert r.status_code == 428
    r = await client.patch(f"{API}/leads/{ref}", json={"stage": "nope"},
                           headers={**owner, "If-Match": str(lead["version"])})  # fmt: skip
    assert r.status_code == 422 and r.json()["message_fa"]
    r = await client.patch(
        f"{API}/leads/{ref}",
        json={"stage": "contacted", "next_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
              "next_fa": "تماس دوباره", "note_fa": "علاقه دارد",
              "assignee": {"kind": "agent", "code": f"{co['code']}-SALES-MGR"}},
        headers={**owner, "If-Match": str(lead["version"])},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["stage"] == "contacted" and moved["assignee"]["code"] == f"{co['code']}-SALES-MGR"
    assert {"stage", "note"} <= {e["kind"] for e in moved["events"]}
    r = await client.patch(f"{API}/leads/{ref}", json={"value_usdt": "50"},
                           headers={**owner, "If-Match": str(lead["version"])})  # fmt: skip
    assert r.status_code == 409  # an old version
    r = await client.patch(
        f"{API}/leads/{sara['ref']}", json={"stage": "lost", "lost_reason_fa": "گران بود"},
        headers={**owner, "If-Match": str(sara["version"])},
    )  # fmt: skip
    assert r.json()["lost_reason_fa"] == "گران بود"
    r = await client.get(f"{API}/leads/{ref}", headers=owner)
    assert r.status_code == 200 and r.json()["next_fa"] == "تماس دوباره"
    assert (await client.get(f"{API}/leads/LD-x", headers=owner)).status_code == 404
    r = await client.get(url, params={"limit": 1}, headers=owner)
    assert len(r.json()["items"]) == 1 and r.json()["next_cursor"]
    r = await client.get(url, params={"limit": 1, "cursor": r.json()["next_cursor"]}, headers=owner)
    assert len(r.json()["items"]) == 1
    assert (await client.get(url, params={"limit": 201}, headers=owner)).status_code == 422
    r = await client.get(url, params={"stage": "lost"}, headers=owner)
    assert [x["ref"] for x in r.json()["items"]] == [sara["ref"]]
    r = await client.get(f"{API}/companies/{co['code']}/pipeline", headers=owner)
    p = r.json()
    assert p["total"] == 2 and p["lost_count"] == 1 and p["won_count"] == 0 and p["win_rate"] == 0.0
    st = {s["stage"]: s for s in p["stages"]}
    assert [s["stage"] for s in p["stages"]] == [
        "new",
        "contacted",
        "qualified",
        "trial",
        "paid",
        "lost",
    ]
    assert st["contacted"]["count"] == 1 and Decimal(st["contacted"]["value_usdt"]) == 40
    assert st["new"]["median_days"] is not None
    # the draft: one call of its own task class, guarded, never sent
    r = await client.post(f"{API}/leads/{ref}/draft", headers=owner)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["draft_fa"] == DRAFT and d["sent"] is False and d["guard_ok"] is True
    call = router.of("sales_followup")[-1]
    assert call["meta"]["lead"] == ref and "site:ali-0001" not in call["prompt"]
    router.handlers.pop("sales_followup")
    r = await client.post(f"{API}/leads/{ref}/draft", headers=owner)
    assert r.status_code == 422 and r.json()["message_fa"]


async def test_leads_are_made_by_code_and_paid_by_a_payment(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        a = await L.from_inbound(tx, co["id"], channel="telegram", subject="tg:user-0042",
                                 display_name="مریم")  # fmt: skip
        b = await L.from_inbound(tx, co["id"], channel="support", subject="sp:user-0043",
                                 display_name=None)  # fmt: skip
        none = await L.from_inbound(tx, co["id"], channel="mystery", subject="x:user-0044",
                                    display_name=None, mystery=True)  # fmt: skip
        again = await L.from_inbound(tx, co["id"], channel="telegram", subject="tg:user-0042",
                                     display_name="مریم")  # fmt: skip
    assert a is not None and b is not None and none is None and again is not None
    assert (a["source"], b["source"]) == ("telegram", "support") and again["id"] == a["id"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        paid = await L.from_payment(tx, co["id"], "tg:user-0042", Decimal("19.9"))
    assert (
        paid["stage"] == "paid"
        and paid["paid_at"] is not None
        and paid["value_usdt"] == Decimal("19.9")
    )
    kinds = [r["kind"] for r in await su.fetch(
        "SELECT kind FROM sales.lead_events WHERE lead_id = $1 ORDER BY id", a["id"])]  # fmt: skip
    assert kinds == ["created", "paid"]


async def test_a_reminder_at_next_at_once(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lead, _ = await L.create(
            tx, L.SERVICE, {"id": co["id"], "code": co["code"]}, source="manual",
            contact=f"m-{secrets.token_hex(6)}", name_fa="رضا",
            next_at=datetime.now(UTC) - timedelta(minutes=1), next_fa="پیگیری پیشنهاد",
        )  # fmt: skip
    out = await L.tick(hub)
    assert out["reminders"] >= 1
    w = await su.fetchrow(
        """SELECT w.title, w.brief, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.company_id = $1 AND w.brief LIKE '%' || $2 || '%'""",
        co["id"], lead["ref"],
    )  # fmt: skip
    assert (
        w is not None and w["code"] == f"{co['code']}-SALES-MGR" and "پیگیری پیشنهاد" in w["brief"]
    )
    again = await L.tick(hub)
    assert (
        await su.fetchval(
            "SELECT count(*) FROM sales.lead_events WHERE lead_id = $1 AND kind = 'reminder'",
            lead["id"],
        )
        == 1
    )
    assert again["locked"] == 0


# ========================================================= affiliate gaps ==
async def test_affiliate_due_against_received(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any],
    su: Any, router: Router,
) -> None:  # fmt: skip
    router.handlers["affiliate_gap"] = lambda req: {
        "draft_fa": "سلام، لطفاً تسویه‌ی کمیسیون این ماه را بررسی کنید."
    }
    co = await new_company()
    acc = await su.fetchval(
        """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
               created_by_kind, created_by_code)
           VALUES ($1, 'lbank', 'lbank-affiliate-v2', $2, 'حساب آزمایشی', 'owner', 'owner') RETURNING id""",
        co["id"], f"sa-{secrets.token_hex(4)}",
    )  # fmt: skip
    for d in range(1, 31):  # September: 10 USDT a day, every day complete
        await su.execute(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
               VALUES ($1, $2, $3, 10, true)""",
            co["id"], acc, date(2026, 9, d),
        )  # fmt: skip
    for d in range(1, 11):  # October: a day not pulled completely: never judged
        await su.execute(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
               VALUES ($1, $2, $3, 10, $4)""",
            co["id"], acc, date(2026, 10, d), d != 5,
        )  # fmt: skip
    now = datetime(2026, 11, 5, 10, tzinfo=UTC)
    out = await AG.scan(hub, router.ask, now=now)
    assert out["opened"] >= 1
    gap = await su.fetchrow(
        "SELECT * FROM sales.affiliate_gaps WHERE account_id = $1 AND month = '2026-09-01'", acc
    )
    assert gap["state"] == "open" and gap["due_usdt"] == 300 and gap["gap_pct"] == 100
    assert gap["work_ref"] and "تسویه" in gap["draft_fa"]
    w = await su.fetchrow(
        """SELECT e.code, w.brief FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.ref = $1""",
        gap["work_ref"],
    )
    assert w["code"] == f"{co['code']}-FIN-MGR" and "300.00" in w["brief"]
    assert router.of("sales_followup")  # the draft had its own task class
    assert (
        await su.fetchval(
            "SELECT count(*) FROM sales.affiliate_gaps WHERE account_id = $1 AND month = '2026-10-01'",
            acc,
        )
        == 0
    )
    # a second scan opens nothing new
    await AG.scan(hub, router.ask, now=now)
    assert (
        await su.fetchval("SELECT count(*) FROM sales.affiliate_gaps WHERE account_id = $1", acc)
        == 1
    )
    r = await client.get(
        f"{API}/revenue/affiliate-gaps", params={"company": co["code"]}, headers=owner
    )
    assert r.status_code == 200
    states = {g["month"]: g["state"] for g in r.json()}
    assert states["2026-09-01"] == "open" and states["2026-10-01"] == "waiting"
    # what arrived closes it once within 5%; the key is required, and a retry books nothing twice
    receipt = {"account_id": str(acc), "month": "2026-09", "received_usdt": "290"}
    r = await client.post(f"{API}/revenue/affiliate-receipts", json=receipt, headers=owner)
    assert r.status_code == 422, r.text
    key = idem()
    r = await client.post(
        f"{API}/revenue/affiliate-receipts", json=receipt, headers={**owner, **key}
    )
    assert r.status_code == 201, r.text
    again = await client.post(
        f"{API}/revenue/affiliate-receipts", json=receipt, headers={**owner, **key}
    )
    assert again.status_code == 201 and again.headers.get("Idempotent-Replay") == "true"
    assert again.json() == r.json()
    assert (
        await su.fetchval(
            "SELECT count(*) FROM sales.affiliate_receipts WHERE account_id = $1 AND month = '2026-09-01'",
            acc,
        )
        == 1
    )
    assert (
        await su.fetchval(
            "SELECT state FROM sales.affiliate_gaps WHERE account_id = $1 AND month = '2026-09-01'",
            acc,
        )
        == "closed"
    )
    r = await client.get(f"{API}/revenue/affiliate-gaps", params={"company": co["code"], "state": "closed"},
                         headers=owner)  # fmt: skip
    assert [g["month"] for g in r.json()] == ["2026-09-01"]


# ======================================================== decision impact ==
async def propose(client: httpx.AsyncClient, code: str, payload: dict[str, Any]) -> str:
    ceo = await agent_headers(f"{code}-CEO")
    r = await client.post(
        "/internal/v1/decisions",
        headers={**ceo, **idem()},
        json={"kind": "proposal", "title": "پیشنهاد کمپین تازه", "payload": payload},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["ref"])


async def test_impact_measured_by_code_estimated_once_and_sorted(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any],
    su: Any, router: Router,
) -> None:  # fmt: skip
    co = await new_company()
    router.handlers["decision_impact"] = lambda req: {
        "revenue_usdt": 1200, "cost_usd": 300, "horizon_days": 30,
        "basis_fa": "بر پایه‌ی هزینه‌ای که خود کارت نوشته است.",
    }  # fmt: skip
    # an ads cap the card names: measured from the campaign's own 14 days
    await su.execute(
        """INSERT INTO growth.ad_rules (company_id, platform, scope, state, daily_cap)
           VALUES ($1, 'google_ads', 'c-77', 'on', 10)""",
        co["id"],
    )
    for i in range(3):
        await su.execute(
            """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend, revenue)
               VALUES ($1, 'google_ads', 'c-77', current_date - $2::int, 10, 25)""",
            co["id"], i + 1,
        )  # fmt: skip
    measured = await propose(client, co["code"], {
        "okr": "O1", "impact_input": {"kind": "ads.cap", "platform": "google_ads", "campaign": "c-77",
                                      "new_daily_cap": "20"},
    })  # fmt: skip
    guessed = await propose(client, co["code"], {"okr": "O1", "cost": "حدود ۳۰۰ دلار"})
    decided = await propose(client, co["code"], {"okr": "O2"})
    r = await client.post(f"{API}/decisions/{decided}/reject", headers={**owner, **idem()},
                          json={"reason_code": "cost"})  # fmt: skip
    assert r.status_code == 200, r.text
    ids = [
        r["id"] for r in await su.fetch(
            "SELECT id FROM cartable.decisions WHERE ref = ANY($1::text[])", [measured, guessed, decided])
    ]  # fmt: skip
    out = await IM.sweep(hub, router.ask, only=ids)
    assert out["estimated"] == 1
    calls = router.of("decision_impact")
    assert len(calls) == 1 and calls[0]["meta"]["decision"] == guessed
    got = {
        r["ref"]: r["impact"]
        for r in await su.fetch(
            "SELECT ref, impact FROM cartable.decisions WHERE ref = ANY($1::text[])",
            [measured, guessed, decided],
        )
    }
    est = json.loads(got[guessed])
    assert est["kind"] == "estimate" and est["basis_fa"].startswith("تخمین")
    assert est["revenue_usdt"] == 1200 and est["cost_usd"] == 300
    assert got[decided] is None  # never for a card the owner has decided
    m = json.loads(got[measured])
    assert m["kind"] == "measured" and m["cost_usd"] == 300 and m["revenue_usdt"] == 750
    # one call per card: a second sweep asks nothing
    await IM.sweep(hub, router.ask, only=ids)
    assert len(router.of("decision_impact")) == 1
    r = await client.get(f"{API}/decisions/{guessed}", headers=owner)
    assert r.json()["impact"]["kind"] == "estimate"
    # sorted by impact: the largest first, cards without one last
    r = await client.get(
        f"{API}/decisions", params={"sort": "impact", "company": co["code"]}, headers=owner
    )
    assert r.status_code == 200, r.text
    assert [d["ref"] for d in r.json()["items"]] == [guessed, measured]
    r1 = await client.get(f"{API}/decisions", params={"sort": "impact", "company": co["code"], "limit": 1},
                          headers=owner)  # fmt: skip
    nxt = r1.json()["next_cursor"]
    assert nxt
    r2 = await client.get(f"{API}/decisions", params={"sort": "impact", "company": co["code"], "limit": 1,
                                                      "cursor": nxt}, headers=owner)  # fmt: skip
    assert r2.status_code == 200 and r2.json()["items"][0]["ref"] != r1.json()["items"][0]["ref"]
    bad = await client.get(
        f"{API}/decisions", params={"sort": "impact", "cursor": "xx"}, headers=owner
    )
    assert bad.status_code == 422


async def test_a_budget_change_is_measured_from_the_limit_in_force(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    ref = f"impact-{uuid.uuid4().hex[:8]}"
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, usd_limit)
           VALUES ($1, 'task_class', $2, 'month', 50)""",
        co["id"], ref,
    )  # fmt: skip
    d = {"kind": "budget_change", "company_id": co["id"], "payload": {
        "scope": {"scope_type": "task_class", "scope_ref": ref}, "period": "month", "usd_limit": "80"}}  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        m = await IM.measure(tx, d)
        none = await IM.measure(tx, {**d, "payload": {**d["payload"], "scope": {"scope_type": "task_class",
                                                                              "scope_ref": "nope"}}})  # fmt: skip
    assert (
        m is not None
        and m["kind"] == "measured"
        and m["cost_usd"] == 30.0
        and m["horizon_days"] == 30
    )
    assert none is None
    # a hire: the card's own monthly cost; a model nobody prices is not measured (no guess)
    hire = {"kind": "hire", "company_id": co["id"],
            "payload": {"model": "m-x", "quota_estimate_month": {"usd": "12.5"}}}  # fmt: skip
    unpriced = {"kind": "hire", "company_id": co["id"], "payload": {
        "model": "nope-model-x", "role": "content_writer", "quota_estimate_month": {"tokens": 100000}}}  # fmt: skip
    line = {"kind": "proposal", "company_id": co["id"], "payload": {"impact_input": {
        "kind": "line.caps", "line": "LN-999999", "new_runs_per_day": 4}}}  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        h = await IM.measure(tx, hire)
        assert await IM.measure(tx, unpriced) is None
        assert await IM.measure(tx, line) is None  # no such line: nothing to measure from
    assert h is not None and h["cost_usd"] == 12.5 and h["kind"] == "measured"
    assert IM.score(m) == 30.0 and IM.score(None) == 0.0


def test_an_estimate_is_checked_by_code() -> None:
    ok = {"revenue_usdt": 10, "cost_usd": None, "horizon_days": 7, "basis_fa": "بر پایه‌ی متن کارت."}
    assert IM.checked_estimate(ok)["basis_fa"].startswith("تخمین")  # type: ignore[index]
    for bad in (
        {**ok, "revenue_usdt": -1},
        {**ok, "revenue_usdt": float("inf")},
        {**ok, "revenue_usdt": None},
        {**ok, "horizon_days": 0},
        {**ok, "basis_fa": "based on the card text only"},
        {**ok, "extra": 1},
    ):
        assert IM.checked_estimate(bad) is None, bad
