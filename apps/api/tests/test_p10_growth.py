"""Prompt 10 §3 and §8 (contract §19.2, §19.7): the funnel and its leaks,
referral.check and referral rescue, the feedback inbox, the weekly support
figures; and that none of them acts while the holding is locked. No exchange,
no model and no customer channel is reached: a fake connector, a counting
router and a fake Telegram behind §7's sender."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from hq_api.domain import desk, lifecycle
from hq_api.domain import feedback as FB
from hq_api.domain import funnel as F
from hq_api.domain import rescue as R
from hq_api.domain import support as S
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.revenue_activities import RevenueActivities

from .conftest import agent_headers
from .p10_fakes import (
    SIGNER_SECRET,
    FakeConnector,
    FakeRouter,
    affiliate_account,
    holding_switch,
    settled,
)
from .p10_support import fake_telegram, inbound, make_live, seal_basics
from .test_egress import FakeBao


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


async def _employee(
    su: Any, co: dict[str, Any], suffix: str, role: str, dept: str = "SALES"
) -> str:
    code = f"{co['code']}-{dept}-{suffix}"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role, reports_to)
           SELECT c.id, d.id, $1, 'employee', $3, $3, $3,
                  (SELECT id FROM core.employees WHERE code = $4)
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = $5
           WHERE c.code = $2""",
        code, co["code"], role, f"{co['code']}-{dept}-MGR", dept,
    )  # fmt: skip
    return code


async def _inbound(hub: Hub, co: dict[str, Any], user: str, body: str) -> dict[str, Any]:
    async with hub.db.tx([co["id"]]) as tx:
        return await S.store_inbound(
            tx, hub, company_id=co["id"], channel_kind="telegram_bot", external_user_id=user, body=body,
        )  # fmt: skip


# ----------------------------------------------------------------- funnel --
async def test_a_funnel_with_two_sources_estimates_nothing_else(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        from hq_api.domain import revenue as V

        a = await V.account(tx, acct["id"])
        p = await V.create_pull(tx, a, kind="manual", from_day=settled(0), to_day=settled(0))
    async with holding_switch(su, "released"):
        await V.run_pull(hub, txf(hub), FakeConnector(), p["id"])
    r = await client.get("/api/v1/growth/funnel", headers=owner, params={"company": co["code"]})
    assert r.status_code == 200, r.text
    f = r.json()
    stages = {s["key"]: s for s in f["stages"]}
    assert stages["referral_verified"] == {"key": "referral_verified", "label_fa": F.LABELS["referral_verified"],
                                           "count": 150, "connected": True, "source": "affiliate"}  # fmt: skip
    assert (stages["min_balance"]["count"], stages["min_balance"]["connected"]) == (75, True)
    for key in ("visit", "signup", "vip_active"):
        assert (stages[key]["connected"], stages[key]["count"], stages[key]["source"]) == (
            False,
            None,
            None,
        )
    rates = {(c["from"], c["to"]): c["rate"] for c in f["conversions"]}
    assert rates[("referral_verified", "min_balance")] == 0.5
    assert [k for k, v in rates.items() if v is not None] == [("referral_verified", "min_balance")]
    # Without the sealed minimum, min_balance has no source either.
    other = await new_company()
    await affiliate_account(su, other, min_balance=None)
    async with hub.db.tx([other["id"]]) as tx:
        await tx.exec(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, complete)
               SELECT company_id, id, :d, 1, true FROM revenue.accounts WHERE company_id = :co""",
            d=settled(0), co=other["id"],
        )  # fmt: skip
        g = await F.funnel(tx, other["id"], other["code"], "month")
    assert {s["key"]: s["connected"] for s in g["stages"]} == {
        "visit": False, "signup": False, "referral_verified": True, "min_balance": False, "vip_active": False,
    }  # fmt: skip
    # A product source registered for signup connects that stage (CR-009/010).
    await su.execute(
        """INSERT INTO intake.sources (company_id, kind, kinds) VALUES ($1, 'product', ARRAY['signup'])""",
        other["id"],
    )
    async with hub.db.tx([other["id"]]) as tx:
        g = await F.funnel(tx, other["id"], other["code"], "week")
    assert {s["key"]: (s["connected"], s["count"]) for s in g["stages"]}["signup"] == (True, 0)


async def test_a_conversion_falling_more_than_30_percent_is_one_leak_for_sales(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    end = settled(0)
    await su.execute(
        "INSERT INTO revenue.days (company_id, account_id, day, complete) VALUES ($1, $2, $3, true)",
        co["id"], acct["id"], end,
    )  # fmt: skip
    for k in range(35):
        day = end - timedelta(days=k)
        minimum = 20 if k < 7 else 50  # the last week: 20%, the four before: 50%
        for stage, n in (("referral_verified", 100), ("min_balance", minimum)):
            await su.execute(
                """INSERT INTO growth.funnel_days (company_id, day, stage, count, source)
                   VALUES ($1, $2, $3, $4, 'affiliate')""",
                co["id"], day, stage, n,
            )  # fmt: skip
    async with hub.db.tx([co["id"]]) as tx:
        found = await F.detect_leaks(tx, co["id"], co["code"], end)
        again = await F.detect_leaks(tx, co["id"], co["code"], end)
    assert [(x["stage"], round(x["rate"], 2), round(x["median_rate"], 2)) for x in found] == [
        ("min_balance", 0.2, 0.5)
    ]
    assert again == []  # one leak per stage and week
    leak = await su.fetchrow(
        "SELECT note_fa, work_id FROM growth.leaks WHERE company_id = $1", co["id"]
    )
    assert leak["work_id"] is not None and "20%" in leak["note_fa"]
    assignee = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1",
        leak["work_id"],
    )
    assert assignee == f"{co['code']}-SALES-MGR"


# ------------------------------------------------------- referral rescue --
async def test_referral_check_opens_a_rescue_case_and_a_later_check_rescues_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    acct = await affiliate_account(su, co)
    agent = await agent_headers(await _employee(su, co, "01", "support_agent"))
    rescuer = await agent_headers(await _employee(su, co, "02", "referral_rescue"))
    out = await _inbound(hub, co, "7001", "سلام، من قبلاً ثبت‌نام کردم ولی VIP ندارم")
    await su.execute(
        """UPDATE support.customers SET uids = '[{"exchange": "lbank", "uid": "12345"}]'::jsonb WHERE id = $1""",
        out["customer_id"],
    )
    hub.bao = FakeBao({acct["key"]: SIGNER_SECRET})
    body = {"company": co["code"], "exchange": "lbank", "uid": "12345"}
    entry = {"tool": "referral.check", "method": "POST", "host": "affiliate.lbank.test", "status": 200,
             "bytes_in": 100, "bytes_out": 200, "ms": 30, "class": "A0"}  # fmt: skip
    try:
        async with holding_switch(su, "released"):
            r = await client.post("/internal/v1/growth/referral-check", headers=agent, json=body)
            assert r.status_code == 200, r.text
            g = r.json()["grant"]
            assert (g["endpoint"], g["params"], g["local"]) == ("invite/user/info", {"uid": "12345"},
                                                                {"min_balance": "100"})  # fmt: skip
            assert g["account"]["secret"] == SIGNER_SECRET  # for the gateway's one call to egress
            # The connector said: not our invitee -> a rescue case, in the conversation.
            r = await client.post("/internal/v1/growth/referral-check/result", headers=agent,
                                  json={**body, "reservation": g["reservation"], "ok": True, "invitee": False,
                                        "meets_minimum": None, "entries": [entry]})  # fmt: skip
            assert r.status_code == 200, r.text
            ans = r.json()
            assert set(ans) == {"invitee", "meets_minimum", "rescue", "checked_at"}
            assert (ans["invitee"], ans["meets_minimum"], ans["rescue"]["state"]) == (
                False,
                None,
                "open",
            )
            ref = ans["rescue"]["ref"]
            case = await su.fetchrow("SELECT * FROM growth.rescue_cases WHERE ref = $1", ref)
            assert (case["source"], case["conversation_id"]) == (
                "support",
                out["conversation"]["id"],
            )
            assert (
                case["subject"] == R.subject_of(hub, co["id"], "lbank", "12345")
                and "12345" not in case["subject"]
            )
            # Within 10 minutes the answer is the cached one: no connector call.
            r = await client.post("/internal/v1/growth/referral-check", headers=agent, json=body)
            assert r.json()["done"] and r.json()["cached"] and r.json()["invitee"] is False
            # The rescue specialist re-checks later (no cache): now ours -> rescued.
            saved = hub.settings
            hub.settings = dataclasses.replace(saved, referral_check_cache_s=0)
            try:
                r = await client.post(
                    "/internal/v1/growth/referral-check", headers=rescuer, json=body
                )
                g = r.json()["grant"]
                r = await client.post("/internal/v1/growth/referral-check/result", headers=rescuer,
                                      json={**body, "reservation": g["reservation"], "ok": True, "invitee": True,
                                            "meets_minimum": True, "entries": [entry]})  # fmt: skip
            finally:
                hub.settings = saved
            assert (
                r.json()["rescue"] == {"ref": ref, "state": "rescued"}
                and r.json()["meets_minimum"] is True
            )
            # A grant settles only its own run's reservation.
            r = await client.post("/internal/v1/growth/referral-check/result", headers=agent,
                                  json={**body, "reservation": g["reservation"], "ok": True, "invitee": True})  # fmt: skip
            assert r.status_code == 403
    finally:
        hub.bao = None
    view = (await client.get(f"/api/v1/growth/rescue/{ref}", headers=owner)).json()
    assert view["state"] == "rescued" and view["conversation"] == out["conversation"]["ref"]
    assert [s["kind"] for s in view["steps"]] == ["check", "check", "check"]
    listed = (
        await client.get("/api/v1/growth/rescue", headers=owner, params={"company": co["code"]})
    ).json()
    assert [c["ref"] for c in listed["items"]] == [ref]
    checks = await su.fetch("SELECT ok, invitee, cached, by_code FROM growth.referral_checks WHERE company_id = $1",
                            co["id"])  # fmt: skip
    assert sorted((c["invitee"], c["cached"]) for c in checks) == [
        (False, False),
        (False, True),
        (True, False),
    ]
    logged = await su.fetchval("SELECT count(*) FROM egress.log WHERE company_id = $1 AND tool = 'referral.check'",
                               co["id"])  # fmt: skip
    assert logged >= 2
    # The rescue rate: rescued / (rescued + lost).
    async with hub.db.tx([co["id"]]) as tx:
        lost, _ = await R.open_case(tx, company_id=co["id"], company=co["code"], source="product",
                                    exchange="lbank", subject="ab" * 32)  # fmt: skip
        await R.close_case(tx, lost, co["code"], "lost", "30_days", "۳۰ روز بی‌نتیجه.")
        rate = await R.rate(
            tx, co["id"], date.today() - timedelta(days=7), date.today() + timedelta(days=1)
        )
    assert (rate["rescued"], rate["lost"], rate["rate"]) == (1, 1, 0.5)


async def test_i_registered_already_a_uid_check_in_a_conversation_opens_its_rescue_case(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    """§4.5: the support agent, woken on a conversation, checks the UID the
    customer gave; the UID stays on that customer (support.customers, the
    one place a raw UID lives) and "not ours" opens the conversation's
    rescue case. The agent's brief says how."""
    co = await new_company()
    acct = await affiliate_account(su, co)
    code = await _employee(su, co, "01", "support_agent")
    body = {"company": co["code"], "exchange": "lbank", "uid": "4455667"}
    hub.bao = FakeBao({acct["key"]: SIGNER_SECRET})
    try:
        async with holding_switch(su, "released"):
            m = await _inbound(hub, co, "7301", "من قبلاً ثبت‌نام کردم ولی VIP ندارم")
            async with hub.db.tx([co["id"]]) as tx:
                out = await desk.process(tx, hub, m["message"]["id"])
            assert out.result == "drafting" and out.work
            # The agent's run on that work item (the runner starts it; the test does).
            await su.execute(
                """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                       started_at, token_expires_at)
                   SELECT e.company_id, e.id, w.id, 'work', 'test', 'running', now(), now() + interval '1 hour'
                   FROM core.employees e, work.work w WHERE e.code = $2 AND w.ref = $1""",
                out.work, code,
            )  # fmt: skip
            agent = await agent_headers(code)
            r = await client.post("/internal/v1/growth/referral-check", headers=agent, json=body)
            assert r.status_code == 200, r.text
            g = r.json()["grant"]
            r = await client.post("/internal/v1/growth/referral-check/result", headers=agent,
                                  json={**body, "reservation": g["reservation"], "ok": True, "invitee": False,
                                        "meets_minimum": None, "entries": []})  # fmt: skip
    finally:
        hub.bao = None
    assert r.status_code == 200, r.text
    rescue = r.json()["rescue"]
    assert rescue["state"] == "open"
    case = await su.fetchrow(
        "SELECT conversation_id, subject FROM growth.rescue_cases WHERE ref = $1", rescue["ref"]
    )
    assert case["conversation_id"] == m["conversation"]["id"] and "4455667" not in case["subject"]
    uids = await su.fetchval("SELECT uids FROM support.customers WHERE id = $1", m["customer_id"])
    assert json.loads(uids) == [{"exchange": "lbank", "uid": "4455667"}]
    assert await su.fetchval(
        "SELECT rescue_case_id FROM support.conversations WHERE id = $1", m["conversation"]["id"]
    ) is not None  # fmt: skip
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", out.work)
    assert "referral.check" in brief and "vip.min_balance" in brief


async def test_a_customer_message_reaches_the_feedback_inbox_by_rule(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    """§8.1 meets §4.3: each customer message is a feedback signal, tagged by
    the company's keywords with no model; nothing while the holding is locked."""
    co = await new_company()
    await su.execute(
        """INSERT INTO feedback.keywords (company_id, pattern, kind, area, created_by_kind, created_by_code)
           VALUES ($1, 'برداشت', 'bug', 'withdrawal', 'owner', 'owner')""",
        co["id"],
    )
    locked = await _inbound(hub, co, "8802", "برداشت من گیر کرده است")
    async with holding_switch(su, "engaged"), hub.db.tx([co["id"]]) as tx:
        assert (await desk.process(tx, hub, locked["message"]["id"])).result == "skipped"
    assert await su.fetchval(
        "SELECT count(*) FROM feedback.signals WHERE company_id = $1", co["id"]
    ) == 0  # fmt: skip
    async with holding_switch(su, "released"), hub.db.tx([co["id"]]) as tx:
        await desk.process(tx, hub, locked["message"]["id"])
    sig = await su.fetchrow(
        "SELECT tagged_by, kind, area, source_ref, item_id, quote FROM feedback.signals WHERE message_id = $1",
        locked["message"]["id"],
    )
    assert (sig["tagged_by"], sig["kind"], sig["area"]) == ("rule", "bug", "withdrawal")
    assert sig["source_ref"] == locked["conversation"]["ref"] and sig["item_id"] is not None


async def test_referral_check_has_a_cap_a_gate_and_only_its_roles(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co, fx = await new_company(), await new_company()
    acct = await affiliate_account(su, co)
    agent = await agent_headers(await _employee(su, co, "01", "support_agent"))
    body = {"company": co["code"], "exchange": "lbank", "uid": "555"}
    hub.bao = FakeBao({acct["key"]: SIGNER_SECRET})
    try:
        async with holding_switch(su, "released"):
            # Another company's agent, and a role without the tool, are refused.
            fx_agent = await agent_headers(await _employee(su, fx, "01", "support_agent"))
            assert (await client.post("/internal/v1/growth/referral-check", headers=fx_agent,
                                      json=body)).status_code == 403  # fmt: skip
            ceo = await agent_headers(f"{co['code']}-CEO")
            assert (
                await client.post("/internal/v1/growth/referral-check", headers=ceo, json=body)
            ).status_code == 403
            for i in range(30):
                await su.execute(
                    """INSERT INTO growth.referral_checks (company_id, exchange, subject, ok, invitee, by_kind, by_code)
                       VALUES ($1, 'lbank', $2, true, false, 'agent', 'x')""",
                    co["id"], f"{i:064x}",
                )  # fmt: skip
            r = await client.post("/internal/v1/growth/referral-check", headers=agent, json=body)
            assert r.status_code == 429 and r.headers["retry-after"] == "600"
        async with holding_switch(su, "engaged"):
            r = await client.post("/internal/v1/growth/referral-check", headers=agent, json=body)
            assert r.status_code == 423  # no outside call while the holding is locked
    finally:
        hub.bao = None


async def test_rescue_update_notes_and_closes_but_never_sends(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    rescuer = await agent_headers(await _employee(su, co, "02", "referral_rescue"))
    agent = await agent_headers(await _employee(su, co, "01", "support_agent"))
    async with hub.db.tx([co["id"]]) as tx:
        case, _ = await R.open_case(tx, company_id=co["id"], company=co["code"], source="product",
                                    exchange="lbank", subject="cd" * 32)  # fmt: skip
    url = f"/internal/v1/growth/rescue/{case['ref']}/update"
    async with holding_switch(su, "released"):
        r = await client.post(
            url, headers=rescuer, json={"state": "open", "note_fa": "پیام دوم را بهتر بنویسیم"}
        )
        assert r.status_code == 200 and r.json()["state"] == "open"
        r = await client.post(
            url, headers=rescuer, json={"state": "rescued", "note_fa": "به نظرم برگشت"}
        )
        assert r.status_code == 422  # rescued only on a check that says "ours"
        assert (
            await client.post(url, headers=agent, json={"state": "lost", "note_fa": "x"})
        ).status_code == 403
        r = await client.post(
            url, headers=rescuer, json={"state": "lost", "note_fa": "دیگر جواب نمیدهد"}
        )
        assert r.json()["state"] == "lost"
        assert (
            await client.post(url, headers=rescuer, json={"state": "open", "note_fa": "x"})
        ).status_code == 409
    steps = await su.fetch(
        "SELECT kind, by_kind FROM growth.rescue_steps WHERE case_id = $1 ORDER BY at", case["id"]
    )
    assert [s["kind"] for s in steps] == ["check", "note", "note"]
    assert (
        await su.fetchval("SELECT count(*) FROM growth.sends WHERE company_id = $1", co["id"]) == 0
    )


async def _sealed_rescue_rule(hub: Hub, company_id: Any) -> dict[str, Any]:
    """The company's own sealed rescue template and rule (the owner's path,
    §7.2), on telegram_bot; quiet hours off so the test runs at any hour."""
    async with hub.db.tx([company_id]) as tx:
        t = await lifecycle.propose_template(
            tx, company_id=company_id, purpose="rescue", variables=[], by_kind="owner",
            by_code="owner", body_fa="سلام؛ برای فعال شدن VIP راهنمای ثبت‌نام دوباره را ببینید.",
        )  # fmt: skip
        t = await lifecycle.seal_template(tx, t["ref"], t["version"], step_up_id=None)
        r = await lifecycle.create_rule(
            tx, company_id=company_id, kind="rescue", template_ref=t["ref"],
            template_version=t["version"], channel="telegram_bot", trigger={"after_hours": 24},
            limits={"max_follow_ups": 2, "quiet_hours": ["00:00", "00:00"], "daily_cap": 50,
                    "per_customer_days": 30},
            by_kind="owner", by_code="owner",
        )  # fmt: skip
        return await lifecycle.seal_rule(tx, r["ref"], r["version"], step_up_id=None)


async def test_follow_ups_go_by_the_sealed_rule_through_the_lifecycle_sender(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    """Rescue follow-ups (§3.4) go only through §7's growth.send_template
    (sealed rule and template, opt-out, a live channel, the guard with the
    safety line) and out through desk.send; nothing while locked."""
    co, bare = await new_company(), await new_company()
    await seal_basics(hub, co["id"])
    await make_live(su, co["id"])
    rule = await _sealed_rescue_rule(hub, co["id"])
    talk = await inbound(hub, co["id"], "سلام، VIP ندارم", user="7101")
    quits = await inbound(hub, co["id"], "سلام", user="7102")
    async with hub.db.tx([co["id"], bare["id"]]) as tx:
        case, _ = await R.open_case(tx, company_id=co["id"], company=co["code"], source="support",
                                    exchange="lbank", subject="e1" * 32,
                                    conversation_id=talk["conversation"]["id"])  # fmt: skip
        quit_, _ = await R.open_case(tx, company_id=co["id"], company=co["code"], source="support",
                                     exchange="lbank", subject="e2" * 32,
                                     conversation_id=quits["conversation"]["id"])  # fmt: skip
        far, _ = await R.open_case(tx, company_id=co["id"], company=co["code"], source="product",
                                   exchange="lbank", subject="e4" * 32)  # fmt: skip
        waiting, _ = await R.open_case(tx, company_id=bare["id"], company=bare["code"], source="product",
                                       exchange="lbank", subject="e3" * 32)  # fmt: skip
    async with fake_telegram() as tg:
        async with holding_switch(su, "engaged"):
            assert (await R.follow_ups(hub, txf(hub)))["reason"] == "holding_locked"
        assert tg.calls == []  # nothing while locked
        assert (
            await su.fetchval("SELECT count(*) FROM growth.sends WHERE company_id = $1", co["id"])
            == 0
        )
        async with holding_switch(su, "released"):
            stop = await inbound(hub, co["id"], "لغو", user="7102", message_id="stop-7102")
            async with hub.db.tx([co["id"]]) as tx:
                assert (await desk.process(tx, hub, stop["message"]["id"])).result == "opted_out"
            out = await R.follow_ups(hub, txf(hub))
            mine = next(c for c in out["companies"] if c["company"] == co["code"])
            assert (mine["sent"], mine["opted_out"], mine["no_channel"]) == (1, 1, 1)
            assert [s["status"] for s in mine["sends"]] == ["sent"]
            row = await su.fetchrow("SELECT state, follow_ups, next_follow_up_at FROM growth.rescue_cases WHERE id = $1",
                                    case["id"])  # fmt: skip
            assert (row["state"], row["follow_ups"]) == ("contacted", 1)
            assert row["next_follow_up_at"] > datetime.now(UTC) + timedelta(hours=23)
            send = await su.fetchrow("SELECT * FROM growth.sends WHERE dedupe_key = $1",
                                     f"rescue:{case['ref']}:1")  # fmt: skip
            assert (send["status"], send["rescue_case_id"], send["follow_up"]) == (
                "sent",
                case["id"],
                1,
            )
            assert send["template"].startswith(rule["template_ref"])
            assert len(tg.calls) == 1 and "VIP" in tg.calls[0]["text"]
            assert desk.SAFETY_DEFAULT.split("؛")[0] in tg.calls[0]["text"]  # the safety line
            # A product's case with no conversation reaches no channel: tried again in a day.
            nc = await su.fetchrow("SELECT status, reason FROM growth.sends WHERE dedupe_key = $1",
                                   f"rescue:{far['ref']}:1")  # fmt: skip
            assert (nc["status"], nc["reason"]) == ("no_channel", "no_conversation")
            assert await su.fetchval("SELECT next_follow_up_at FROM growth.rescue_cases WHERE id = $1",
                                     far["id"]) > datetime.now(UTC) + timedelta(hours=23)  # fmt: skip
            for _ in range(2):
                await su.execute(
                    "UPDATE growth.rescue_cases SET next_follow_up_at = now() - interval '1 minute' WHERE id = $1",
                    case["id"],
                )
                await R.follow_ups(hub, txf(hub))
    states = {r["id"]: (r["state"], r["close_reason"]) for r in await su.fetch(
        "SELECT id, state, close_reason FROM growth.rescue_cases WHERE id = ANY($1::uuid[])",
        [case["id"], quit_["id"], waiting["id"], far["id"]])}  # fmt: skip
    assert states[case["id"]] == ("lost", "max_follow_ups")
    assert states[quit_["id"]] == ("opted_out", "opted_out")
    assert states[far["id"]] == ("open", None)
    assert states[waiting["id"]] == ("open", None)  # no sealed rescue rule: nothing is ever sent
    assert len(tg.calls) == 2  # follow-ups 1 and 2 of the one reachable case
    kinds = [r["kind"] for r in await su.fetch(
        "SELECT kind FROM growth.rescue_steps WHERE case_id = $1 ORDER BY at", case["id"])]  # fmt: skip
    assert kinds == ["check", "message", "follow_up", "note"]
    assert (
        await su.fetchval("SELECT count(*) FROM growth.sends WHERE company_id = $1", bare["id"])
        == 0
    )


async def test_a_products_referral_failed_event_opens_a_case_once(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    src = await su.fetchval(
        "INSERT INTO intake.sources (company_id, kind, kinds) VALUES ($1, 'product', ARRAY['referral_failed']) RETURNING id",
        co["id"],
    )
    subject = R.subject_of(hub, co["id"], "lbank", "99887766")
    await su.execute(
        """INSERT INTO intake.events (company_id, source_id, kind, event_id, subject, data)
           VALUES ($1, $2, 'referral_failed', 'ev-1', $3, '{"exchange": "lbank"}')""",
        co["id"], src, subject,
    )  # fmt: skip
    async with holding_switch(su, "released"):
        await R.follow_ups(hub, txf(hub))
        await R.follow_ups(hub, txf(hub))
    cases = await su.fetch(
        "SELECT source, subject FROM growth.rescue_cases WHERE company_id = $1", co["id"]
    )
    assert [(c["source"], c["subject"]) for c in cases] == [("product", subject)]
    assert await su.fetchval("SELECT state FROM intake.events WHERE event_id = 'ev-1'") == "applied"


# --------------------------------------------------------------- feedback --
async def test_five_messages_of_one_meaning_are_one_item_and_one_product_task(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    await su.execute(
        """INSERT INTO feedback.keywords (company_id, pattern, kind, area, created_by_kind, created_by_code)
           VALUES ($1, 'واريز', 'bug', 'deposit', 'owner', 'owner')""",  # an Arabic yeh: normalised
        co["id"],
    )
    router = FakeRouter()
    async with holding_switch(su, "released"):
        for i in range(5):
            text = f"واریز من بعد از {i + 1} ساعت نرسید @ali_test{i} UID 8812345{i}"
            m = await _inbound(hub, co, f"80{i}", text)
            async with hub.db.tx([co["id"]]) as tx:
                got = await FB.ingest(tx, hub, company_id=co["id"], company=co["code"],
                                      source_ref=m["conversation"]["ref"], text=text,
                                      message_id=m["message"]["id"])  # fmt: skip
            assert got["tagged_by"] == "rule"
        await FB.batch(hub, txf(hub), router)
    items = await su.fetch("SELECT * FROM feedback.items WHERE company_id = $1", co["id"])
    assert len(items) == 1
    item = items[0]
    assert (item["kind"], item["area"], item["count"]) == ("bug", "deposit", 5)
    quotes = json.loads(item["quotes"])
    assert len(quotes) == 3
    for q in quotes:
        assert "@ali_test" not in q and "8812345" not in q
    assert item["threshold_work_id"] is not None
    task = await su.fetchrow(
        """SELECT w.brief, e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1""",
        item["threshold_work_id"],
    )
    assert task["code"] == f"{co['code']}-PRODUCT-MGR" and item["ref"] in task["brief"]
    assert [b for b in router.bodies if b["company_code"] == co["code"]] == []  # keywords: no model
    listed = (
        await client.get("/api/v1/feedback", headers=owner, params={"company": co["code"]})
    ).json()
    assert [i["ref"] for i in listed["items"]] == [item["ref"]] and listed["items"][0]["count"] == 5
    r = await client.patch(f"/api/v1/feedback/{item['ref']}", headers={**owner, "If-Match": "999"},
                           json={"state": "triaged"})  # fmt: skip
    assert r.status_code == 409
    r = await client.patch(f"/api/v1/feedback/{item['ref']}", headers={**owner, "If-Match": str(item["version"])},
                           json={"state": "in_backlog", "work_ref": "TY-123"})  # fmt: skip
    assert r.status_code == 200 and r.json()["state"] == "in_backlog"


async def test_the_nightly_batch_tags_the_rest_with_a_light_model_unless_locked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    m = await _inbound(hub, co, "901", "کاش اپ حالت شب داشت، @night_owl")
    async with hub.db.tx([co["id"]]) as tx:
        got = await FB.ingest(tx, hub, company_id=co["id"], company=co["code"], source_ref=m["conversation"]["ref"],
                              text="کاش اپ حالت شب داشت، @night_owl", message_id=m["message"]["id"])  # fmt: skip
    assert got["tagged_by"] == "pending"
    router = FakeRouter(
        json.dumps([{"i": 0, "kind": "feature", "area": "app_theme", "title_fa": "حالت شب در اپ"}])
    )
    async with holding_switch(su, "engaged"):
        assert (await FB.batch(hub, txf(hub), router))["reason"] == "holding_locked"
    assert router.bodies == []  # no model call while the holding is locked
    async with holding_switch(su, "released"):
        acts = RevenueActivities(hub, txf(hub), router=router, connector=FakeConnector())
        out = await acts.feedback_batch()
    mine = next(c for c in out["companies"] if c["company"] == co["code"])
    assert mine["tagged"] == 1
    body = next(b for b in router.bodies if b["company_code"] == co["code"])
    assert (body["priority"], body["model"], body["task_class"]) == (
        4,
        "claude-haiku-5-5",
        "classify",
    )
    assert "@night_owl" not in body["prompt"]
    sig = await su.fetchrow("SELECT tagged_by, kind, area, item_id FROM feedback.signals WHERE id = $1",
                            got["signal"]["id"])  # fmt: skip
    assert (sig["tagged_by"], sig["kind"], sig["area"]) == ("model", "feature", "app_theme")
    # A malformed answer leaves a signal pending.
    m2 = await _inbound(hub, co, "902", "پیام نامفهوم")
    async with hub.db.tx([co["id"]]) as tx:
        g2 = await FB.ingest(tx, hub, company_id=co["id"], company=co["code"], source_ref=m2["conversation"]["ref"],
                             text="پیام نامفهوم", message_id=m2["message"]["id"])  # fmt: skip
    async with holding_switch(su, "released"):
        await FB.batch(hub, txf(hub), FakeRouter("sure! here you go"))
    assert (
        await su.fetchval(
            "SELECT tagged_by FROM feedback.signals WHERE id = $1", g2["signal"]["id"]
        )
        == "pending"
    )


async def test_feedback_tag_by_the_support_lead_and_the_product_manager(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    lead = await agent_headers(await _employee(su, co, "03", "support_lead"))
    product = await agent_headers(f"{co['code']}-PRODUCT-MGR")
    m = await _inbound(hub, co, "950", "برداشت تتر خیلی کند است @slow_user")
    body = {"source_ref": m["conversation"]["ref"], "kind": "complaint", "area": "withdrawal",
            "title_fa": "کندی برداشت تتر"}  # fmt: skip
    async with holding_switch(su, "released"):
        r = await client.post("/internal/v1/feedback/tag", headers=lead, json=body)
        assert r.status_code == 200, r.text
        assert r.json()["created"] and r.json()["count"] == 1
        m2 = await _inbound(hub, co, "951", "برداشت تتر کند است")
        r = await client.post("/internal/v1/feedback/tag", headers=product,
                              json={**body, "source_ref": m2["conversation"]["ref"], "title_fa": "برداشت تتر کند"})  # fmt: skip
        assert r.status_code == 200 and not r.json()["created"] and r.json()["count"] == 2  # merged
        sales = await agent_headers(f"{co['code']}-SALES-MGR")
        assert (
            await client.post("/internal/v1/feedback/tag", headers=sales, json=body)
        ).status_code == 403
        r = await client.post(
            "/internal/v1/feedback/tag", headers=lead, json={**body, "source_ref": "SC-999999"}
        )
        assert r.status_code == 404
    item = await su.fetchrow(
        "SELECT quotes, sources FROM feedback.items WHERE company_id = $1", co["id"]
    )
    assert "@slow_user" not in item["quotes"] and len(item["sources"]) == 2


async def test_the_weekly_support_figures_go_to_the_lead_or_the_morning_report(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    led, alone = await new_company(), await new_company()
    lead = await _employee(su, led, "03", "support_lead")
    for co in (led, alone):
        await _inbound(hub, co, "1", "سؤال درباره‌ی VIP")
    today = datetime.now(UTC).date() + timedelta(days=1)
    async with holding_switch(su, "engaged"):
        assert (await FB.weekly(hub, txf(hub), today))["reason"] == "holding_locked"
    async with holding_switch(su, "released"):
        out = await FB.weekly(hub, txf(hub), today)
    assert len(out["tasks"]) >= 1
    owner_of = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1",
        out["tasks"][-1],
    )
    assert owner_of in (lead,) or owner_of.endswith("-SALES-03")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lines = await FB.morning_lines(tx, today)
        week = await FB.support_week(tx, alone["id"], today - timedelta(days=7), today)
    assert any(alone["code"] in ln for ln in lines) and not any(
        f"**{led['code']}**" in ln for ln in lines
    )
    assert week["rescue"]["rate"] is None and week["unanswered"] == 0
