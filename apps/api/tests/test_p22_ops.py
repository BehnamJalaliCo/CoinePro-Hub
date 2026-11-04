"""Prompt 22 part 3 (contract §31.6, §31.7): ad budgets that stop by themselves,
an automation from one sentence.

- the compiler with a faked router: a good sentence, a sentence asking for a
  forbidden action (refused by code), malformed model JSON (a plain error), the
  preview built by code, one router call of the task class `automation_compile`;
- seal required (🔏 automation.seal); schedules, metrics and events run by code,
  once per occurrence, every run in the Audit; a failing automation turns itself
  off and tells the owner; a lines action is refused plainly when the lines
  engine is missing;
- the ads: both platforms read through a fake egress; a tripped rule PAUSES the
  campaign (a status change only, never a budget), writes the Audit and a work
  item for the growth lead, once per day; loosening a rule and resuming a
  campaign are 🔏.
Nothing leaves the test (a fake egress, a fake OpenBao, a fake webhook)."""

from __future__ import annotations

import json
import sys
import types
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest

from hq_api import events, workflows_client
from hq_api.domain import ads as AD
from hq_api.domain import automations as AU
from hq_api.domain import connections as CN
from hq_api.domain import humanize as H
from hq_api.domain.gov_common import owner_tz
from hq_api.hub import Hub
from hq_api.lines import signing

from .conftest import idem, step_up
from .p10_fakes import holding_switch
from .test_p21_connections import FakeBao, put_config

SECRET_JSON = json.dumps(
    {
        "clientId": "cid-" + "1" * 20,
        "clientSecret": "csec-" + "2" * 20,
        "refreshToken": "1//refresh-" + "3" * 30,
        "developerToken": "dev-" + "4" * 20,
    }
)
META_TOKEN = "EAAB" + "M" * 60
N8N_SECRET = "n8n-hmac-" + "5" * 30
COMPANIES = {"ZZ"}  # a code no real company has


# ---------------------------------------------------------------- fakes --
class AdsEgress:
    """Google Ads' and Meta's APIs behind egress, answered by URL. Records every
    call so a test can see exactly what was sent."""

    def __init__(self, today: date) -> None:
        self.today = today
        self.calls: list[dict[str, Any]] = []
        self.fail_mutate = False
        self.google_spend = 120.0  # the campaign's spend today (micros / 1e6)

    def entry(self, host: str) -> dict[str, Any]:
        return {"tool": "http.request", "kind": "request", "class": "A0", "method": "POST",
                "host": host, "status": 200, "bytes_in": 10, "bytes_out": 0, "ms": 5}  # fmt: skip

    async def request(self, method: str, url: str, *, company: str, **kw: Any) -> CN.Answer:
        self.calls.append({"method": method, "url": url, "company": company, **kw})
        u = urlsplit(url)
        host, path = u.hostname or "", u.path
        acct = kw.get("account") or {}
        ent = [self.entry(host)]

        def ok(body: Any, status: int = 200) -> CN.Answer:
            return CN.Answer("ok", status, json.dumps(body), None, ent)

        if host == "oauth2.googleapis.com":
            form = parse_qs(str(kw.get("body")))
            assert form["grant_type"] == ["refresh_token"] and form["refresh_token"]
            return ok({"access_token": "ya29." + "A" * 40, "expires_in": 3600})
        if host == "googleads.googleapis.com":
            assert acct["secret"].startswith("ya29.") and kw["headers"]["developer-token"]
            if path.endswith("campaigns:mutate"):
                if self.fail_mutate:
                    return ok({"error": "no"}, 500)
                return ok({"results": [{"resourceName": "x"}]})
            query = kw["json_body"]["query"]
            if "segments.date" in query:
                rows = [
                    {
                        "campaign": {"id": "111", "name": "جذب کاربر", "status": "ENABLED"},
                        "metrics": {"costMicros": str(int(self.google_spend * 1_000_000)),
                                    "clicks": "40", "conversions": 4.0, "conversionsValue": 60.0},
                        "segments": {"date": self.today.isoformat()},
                    },
                    {
                        "campaign": {"id": "111", "name": "جذب کاربر", "status": "ENABLED"},
                        "metrics": {"costMicros": "20000000", "clicks": "10", "conversions": 1.0,
                                    "conversionsValue": 50.0},
                        "segments": {"date": (self.today - timedelta(days=1)).isoformat()},
                    },
                ]  # fmt: skip
                return ok([{"results": rows[:1]}, {"results": rows[1:]}])
            return ok([{"results": [
                {"campaign": {"id": "111", "name": "جذب کاربر", "status": "ENABLED"}},
                {"campaign": {"id": "222", "name": "قدیمی", "status": "PAUSED"}},
            ]}])  # fmt: skip
        if host == "graph.facebook.com":
            assert acct["secret"] == META_TOKEN
            if method == "POST":
                return ok({"success": not self.fail_mutate}, 200 if not self.fail_mutate else 500)
            if path.endswith("/insights"):
                row = {"campaign_id": "333", "campaign_name": "متا", "spend": "30.5", "clicks": "12",
                       "date_start": self.today.isoformat(),
                       "actions": [{"action_type": "purchase", "value": "2"},
                                   {"action_type": "link_click", "value": "9"}],
                       "action_values": [{"action_type": "purchase", "value": "90"}]}  # fmt: skip
                return ok({"data": [row]})
            return ok({"data": [{"id": "333", "name": "متا", "effective_status": "ACTIVE"}]})
        return CN.Answer("error", None, "", "fetch_failed", ent)

    def mutations(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["method"] == "POST" and "oauth2" not in c["url"]
                and "searchStream" not in c["url"]]  # fmt: skip


@pytest.fixture
def egress(hub: Hub) -> Any:
    yield
    CN.OVERRIDE = None
    hub.bao = None
    AU.N8N_POST = None


async def today_of(hub: Hub) -> date:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return CN.owner_today(await owner_tz(tx))


def route_answer(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[dict[str, Any]]:
    """The router, faked: every request it gets is kept; `answer` is what comes back."""
    seen: list[dict[str, Any]] = []

    async def fake(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> Any:
        seen.append(req)
        return answer(req) if callable(answer) else answer

    monkeypatch.setattr(workflows_client, "route_order", fake)
    return seen


def routes(rule: Any, refused: list[str] | None = None) -> dict[str, Any]:
    return {"routes": [{"rule": rule, "refused_fa": refused or []}], "status": "ok"}


DAILY_REPORT = {
    "trigger": {"kind": "schedule", "rrule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"},
    "conditions": [],
    "actions": [{"kind": "notify.owner", "args": {"title_fa": "گزارش صبح", "body_fa": "سلام"}}],
}


def hourly(*actions: dict[str, Any], company_args: bool = False) -> dict[str, Any]:
    return {"trigger": {"kind": "schedule", "rrule": "FREQ=HOURLY;BYMINUTE=0"},
            "conditions": [], "actions": list(actions)}  # fmt: skip


def work(title: str = "کار آزمایشی") -> dict[str, Any]:
    return {"kind": "work.create", "args": {"title_fa": title, "brief_fa": "شرح کوتاه"}}


# ------------------------------------------------------------ the compiler --
def test_the_rule_is_checked_by_code_only_the_allow_list_survives() -> None:
    known = {"AA", "BB"}
    ok, why = AU.validate_rule(DAILY_REPORT, None, known)
    assert why == [] and ok is not None and ok["trigger"]["rrule"].startswith("FREQ=DAILY")
    for bad_action in ("ad.raise_budget", "email.send", "server.exec", "work.delete", ""):
        rule = {**DAILY_REPORT, "actions": [{"kind": bad_action, "args": {}}]}
        got, why = AU.validate_rule(rule, None, known)
        assert got is None and why and "مجاز" in why[0]
    # an unknown event, a made-up argument, a metric with no company, a bad schedule
    event = {"kind": "event", "type": "billing.charge"}
    assert AU.validate_rule({**DAILY_REPORT, "trigger": event}, None, known)[0] is None
    assert AU.validate_rule({**DAILY_REPORT, "trigger": {"kind": "event", "type": "automation.run"}},
                            None, known)[0] is None  # never an automation waiting for automations  # fmt: skip
    extra = {"kind": "notify.owner", "args": {"title_fa": "x", "amount_usd": 5}}
    assert AU.validate_rule({**DAILY_REPORT, "actions": [extra]}, None, known)[0] is None
    metric = {"kind": "metric", "connection": "ga4", "key": "sessions", "op": "<", "value": 100}
    assert AU.validate_rule({**DAILY_REPORT, "trigger": metric}, None, known)[0] is None
    assert AU.validate_rule({**DAILY_REPORT, "trigger": metric}, "AA", known)[0] is not None
    bad_cron = {"kind": "schedule", "rrule": "FREQ=SECONDLY"}
    assert AU.validate_rule({**DAILY_REPORT, "trigger": bad_cron}, None, known)[0] is None
    # a company action needs a company; another company's code is refused in a company rule
    work_rule = {**DAILY_REPORT, "actions": [work()]}
    got, why = AU.validate_rule(work_rule, None, known)
    assert got is None and "شرکت" in why[0]
    other = {"kind": "work.create", "args": {"title_fa": "x", "company": "BB"}}
    assert AU.validate_rule({**DAILY_REPORT, "actions": [other]}, "AA", known)[0] is None
    assert AU.validate_rule({**DAILY_REPORT, "actions": [other]}, None, known)[0] is not None
    too_many = {**DAILY_REPORT, "actions": [DAILY_REPORT["actions"][0]] * (AU.MAX_ACTIONS + 1)}
    assert AU.validate_rule(too_many, None, known)[0] is None
    assert (
        AU.validate_rule({"trigger": DAILY_REPORT["trigger"], "actions": [], "x": 1}, None, known)[
            0
        ]
        is None
    )


def test_the_preview_is_written_by_code_from_the_checked_rule() -> None:
    rule, _ = AU.validate_rule(
        {
            "trigger": {"kind": "schedule", "rrule": "FREQ=WEEKLY;BYDAY=SA;BYHOUR=8"},
            "conditions": [{"connection": "ga4", "key": "sessions", "op": "<", "value": 100,
                            "window_days": 3, "agg": "sum"}],
            "actions": [
                {"kind": "work.create", "args": {"title_fa": "بازبینی سایت", "company": "AA"}},
                {"kind": "ad.pause", "args": {"platform": "meta_ads", "campaign": "333",
                                              "company": "AA"}},
                {"kind": "n8n.run", "args": {"workflow": "report-weekly"}},
            ],
        },
        "AA",
        {"AA"},
    )  # fmt: skip
    assert rule is not None
    text = AU.preview_fa(rule, "AA")
    assert "شنبه ساعت 08:00" in text and "بازبینی سایت" in text and "متوقف میشود" in text
    assert "جمع" in text and "sessions" in text and "جریان خودکار" in text
    assert "بودجه‌ای را بالا نمیبرد" in text and "مُهر" in text
    assert H.check(text) == [] and H.is_persian_answer(text, threshold=0.5)
    # the model's own words never reach it: a hostile title is only quoted, as data
    assert (
        AU.preview_fa(AU.validate_rule(DAILY_REPORT, None, set())[0] or {}, None).count("\n") >= 3
    )


async def test_a_good_sentence_is_one_router_call_and_a_checked_rule(
    client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = route_answer(monkeypatch, routes(DAILY_REPORT))
    r = await client.post("/api/v1/automations/compile", headers=owner,
                          json={"sentence_fa": "هر روز ساعت ۹ صبح یک گزارش برایم بفرست"})  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["refused_fa"] == [] and out["rule"]["trigger"]["kind"] == "schedule"
    assert "هر روز ساعت 09:00" in out["preview_fa"]
    assert len(seen) == 1  # ONE call
    q = seen[0]
    assert q["task_class"] == "automation_compile" and q["max_output_tokens"] <= 1000
    assert q["effort"] == "low" and q["json_schema"]["additionalProperties"] is False
    assert "sonnet" in q["model"]  # a mid model
    props = q["json_schema"]["properties"]["routes"]["items"]["properties"]["rule"]["properties"]
    assert set(props["actions"]["items"]["properties"]["kind"]["enum"]) == set(AU.ACTION_KINDS)
    # nothing was saved by compiling
    # a secret in the sentence is masked before the model sees it
    token = "sk-" + "a1" * 20
    seen.clear()
    await client.post("/api/v1/automations/compile", headers=owner,
                      json={"sentence_fa": f"هر روز به این توکن {token} گزارش بده"})  # fmt: skip
    assert token not in seen[0]["prompt"]


async def test_a_forbidden_action_is_refused_whatever_the_model_says(
    client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = {**DAILY_REPORT, "actions": [{"kind": "ad.raise_budget", "args": {"campaign": "1"}}]}
    route_answer(monkeypatch, routes(bad))
    r = await client.post("/api/v1/automations/compile", headers=owner,
                          json={"sentence_fa": "هر روز بودجه‌ی تبلیغ را دو برابر کن"})  # fmt: skip
    out = r.json()
    assert r.status_code == 200 and out["rule"] is None and out["preview_fa"] is None
    assert out["refused_fa"] and "مجاز" in out["refused_fa"][0]
    # the model refused itself: its plain Persian reason is kept, an English one is not
    route_answer(monkeypatch, routes(None, ["این کار پول خرج میکند و مجاز نیست.", "no way"]))
    out = (await client.post("/api/v1/automations/compile", headers=owner,
                             json={"sentence_fa": "برای من تبلیغ بخر"})).json()  # fmt: skip
    assert out["rule"] is None and out["refused_fa"] == ["این کار پول خرج میکند و مجاز نیست."]
    # a good action next to a bad one: the whole rule is refused (nothing half-runs)
    mixed = {
        **DAILY_REPORT,
        "actions": [*DAILY_REPORT["actions"], {"kind": "shell.run", "args": {}}],
    }
    route_answer(monkeypatch, routes(mixed))
    out = (await client.post("/api/v1/automations/compile", headers=owner,
                             json={"sentence_fa": "گزارش بده و سرور را ریست کن"})).json()  # fmt: skip
    assert out["rule"] is None and out["refused_fa"]


async def test_malformed_model_json_is_a_plain_error(
    client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for answer in (None, {"routes": None, "status": "error"}, {"routes": "oops"},
                   {"routes": [["not", "a", "dict"]]}, {"routes": [{"rule": 5, "refused_fa": "x"}]}):  # fmt: skip
        route_answer(monkeypatch, answer)
        r = await client.post("/api/v1/automations/compile", headers=owner,
                              json={"sentence_fa": "هر روز یک گزارش بفرست"})  # fmt: skip
        assert r.status_code == 502, (answer, r.text)
        assert H.is_persian_answer(r.json()["message_fa"]) and "Traceback" not in r.text
    # a rule that is not an object is refused with a reason, not an error
    route_answer(monkeypatch, routes([1, 2]))
    r = await client.post("/api/v1/automations/compile", headers=owner,
                          json={"sentence_fa": "هر روز یک گزارش بفرست"})  # fmt: skip
    assert r.status_code == 200 and r.json()["rule"] is None and r.json()["refused_fa"]


# ---------------------------------------------------- propose, seal, state --
@pytest.fixture
async def made(su: Any) -> AsyncIterator[list[str]]:
    refs: list[str] = []
    yield refs
    for ref in refs:  # the test database outlives a run: nothing stays on
        await su.execute("UPDATE growth.automations SET state = 'off' WHERE ref = $1", ref)


async def propose(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    made: list[str],
    rule: dict[str, Any],
    company: str | None = None,
    sentence: str = "جمله‌ی آزمایشی",
) -> dict[str, Any]:
    body: dict[str, Any] = {"rule": rule, "sentence_fa": sentence}
    if company:
        body["company"] = company
    r = await client.post("/api/v1/automations", headers={**owner, **idem()}, json=body)
    assert r.status_code == 201, r.text
    made.append(r.json()["ref"])
    return dict(r.json())


async def seal(
    client: httpx.AsyncClient, hub: Hub, sess: dict[str, Any], ref: str
) -> httpx.Response:
    su_h = await step_up(hub, sess["session_id"], "automation.seal", ref)
    return await client.post(f"/api/v1/automations/{ref}/seal", headers={**sess["headers"], **su_h})


async def test_a_proposed_automation_runs_nothing_until_the_owner_seals(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    a = await propose(client, h, made, hourly(work()), co["code"], "هر ساعت یک کار بساز")
    ref = a["ref"]
    assert ref.startswith("AT-") and a["state"] == "proposed" and a["company"] == co["code"]
    assert a["runs"] == 0 and "هر ساعت" in a["preview_fa"] and a["sealed_at"] is None
    # a made-up rule is refused like the model's; so is a missing idempotency key
    bad = await client.post("/api/v1/automations", headers={**h, **idem()},
                            json={"rule": {**DAILY_REPORT, "actions": [{"kind": "x", "args": {}}]},
                                  "sentence_fa": "چیزی"})  # fmt: skip
    assert bad.status_code == 422
    noidem = await client.post("/api/v1/automations", headers=h, json={"rule": DAILY_REPORT,
                                                                       "sentence_fa": "چیزی"})  # fmt: skip
    assert noidem.status_code in (400, 422)
    # a proposal cannot be switched on, and the tick ignores it
    assert (await client.post(f"/api/v1/automations/{ref}/state", headers=h,
                              json={"state": "on"})).status_code == 409  # fmt: skip
    async with holding_switch(su, "released"):
        await AU.tick(hub, now=datetime.now(UTC) + timedelta(hours=2))
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.automation_runs ar JOIN growth.automations "
            "a ON a.id = ar.automation_id WHERE a.ref = $1",
            ref,
        )
        == 0
    )
    # the seal needs the step-up, and only the owner
    plain = await client.post(f"/api/v1/automations/{ref}/seal", headers=h)
    assert plain.status_code == 403
    wrong = await step_up(hub, owner_session["session_id"], "automation.seal", "AT-9999")
    assert (await client.post(f"/api/v1/automations/{ref}/seal",
                              headers={**h, **wrong})).status_code == 403  # fmt: skip
    r = await seal(client, hub, owner_session, ref)
    assert r.status_code == 200 and r.json()["state"] == "on" and r.json()["sealed_at"]
    assert (await seal(client, hub, owner_session, ref)).status_code == 409  # only once
    # the sentence and the rule never change (a trigger in the database)
    with pytest.raises(Exception, match="immutable"):
        await su.execute("UPDATE growth.automations SET rule = '{}'::jsonb WHERE ref = $1", ref)
    off = await client.post(f"/api/v1/automations/{ref}/state", headers=h, json={"state": "off"})
    assert off.status_code == 200 and off.json()["state"] == "off"
    on = await client.post(f"/api/v1/automations/{ref}/state", headers=h, json={"state": "on"})
    assert on.json()["state"] == "on"
    listed = (
        await client.get("/api/v1/automations", headers=h, params={"company": co["code"]})
    ).json()
    assert [x["ref"] for x in listed] == [ref]
    detail = (await client.get(f"/api/v1/automations/{ref}", headers=h)).json()
    assert detail["ref"] == ref and detail["run_log"] == []
    audit = await su.fetch("SELECT action, step_up FROM audit.entries WHERE target_ref = $1", ref)
    assert {x["action"] for x in audit} >= {"automation.propose", "automation.seal"}
    assert any(x["step_up"] for x in audit if x["action"] == "automation.seal")


# ----------------------------------------------------------------- running --
async def run_work_count(su: Any, company_id: UUID) -> int:
    return int(
        await su.fetchval("SELECT count(*) FROM work.work WHERE company_id = $1", company_id)
    )


async def test_a_schedule_runs_once_per_occurrence_and_every_run_is_in_the_audit(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    a = await propose(client, h, made, hourly(work("کار ساعتی")), co["code"])
    ref = a["ref"]
    now = datetime.now(UTC) + timedelta(hours=2)  # an hour mark has passed since the seal
    async with holding_switch(su, "released"):
        assert (await AU.tick(hub, now=now))["fired"] == 0  # not sealed yet
        assert (await seal(client, hub, owner_session, ref)).status_code == 200
        before = await run_work_count(su, co["id"])
        first = await AU.tick(hub, now=now)
        again = await AU.tick(hub, now=now)  # the same occurrence: never twice
    assert first["fired"] >= 1 and again["fired"] == 0
    assert await run_work_count(su, co["id"]) == before + 1
    detail = (await client.get(f"/api/v1/automations/{ref}", headers=h)).json()
    assert detail["runs"] == 1 and len(detail["run_log"]) == 1 and detail["last_run_at"]
    run = detail["run_log"][0]
    assert run["outcome"] == "ok" and run["key"].startswith("schedule:")
    assert run["steps"][0]["kind"] == "work.create" and H.is_persian_answer(
        run["steps"][0]["note_fa"]
    )
    audit = await su.fetch("SELECT action, actor_code FROM audit.entries WHERE target_ref = $1 "
                           "AND action = 'automation.run'", ref)  # fmt: skip
    assert len(audit) == 1 and audit[0]["actor_code"] == "automations"
    ev = await su.fetchval("SELECT count(*) FROM core.outbox WHERE payload ->> 'type' = 'automation.run' "
                           "AND payload ->> 'ref' = $1", ref)  # fmt: skip
    assert ev == 1
    # a locked holding runs nothing
    other = await propose(client, h, made, hourly(work("ساعتی دوم")), co["code"])
    await seal(client, hub, owner_session, other["ref"])
    n = await run_work_count(su, co["id"])
    async with holding_switch(su, "engaged"):
        out = await AU.tick(hub, now=now + timedelta(hours=3))
    assert out.get("skipped") and await run_work_count(su, co["id"]) == n


async def test_a_metric_trigger_fires_once_a_day_and_its_conditions_gate_it(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    today = await today_of(hub)
    metric = {"kind": "metric", "connection": "search_console", "key": "clicks", "op": "<",
              "value": 100, "window_days": 2, "agg": "sum"}  # fmt: skip
    cond = {"connection": "ga4", "key": "sessions", "op": ">", "value": 10, "window_days": 1,
            "agg": "last"}  # fmt: skip
    rule = {"trigger": metric, "conditions": [cond],
            "actions": [{"kind": "notify.owner", "args": {"title_fa": "کلیک‌ها کم شد"}}]}  # fmt: skip
    a = await propose(client, h, made, rule, co["code"])
    ref = a["ref"]
    assert "کمتر از 100" in a["preview_fa"] and "ga4" not in a["preview_fa"]
    await seal(client, hub, owner_session, ref)

    async def fig(kind: str, key: str, day: date, value: float) -> None:
        await su.execute(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES ($1, $2, $3, $4, '', $5, 'test')
               ON CONFLICT (company_id, kind, day, key, subject) DO UPDATE SET value = $5""",
            co["id"], kind, day, key, value)  # fmt: skip

    async with holding_switch(su, "released"):
        assert (await AU.tick(hub))["fired"] == 0  # no figures yet
        await fig("search_console", "clicks", today, 30)
        await fig("search_console", "clicks", today - timedelta(days=1), 40)
        skipped = await AU.tick(hub)  # 70 < 100, but the condition (sessions) has no figure
        assert skipped["skipped"] == 1 and skipped["fired"] == 0
        await fig("ga4", "sessions", today, 50)
        # the skipped day was recorded once; a new day of data runs it
        await fig("search_console", "clicks", today + timedelta(days=1), 20)
        await fig("ga4", "sessions", today + timedelta(days=1), 50)
        fired = await AU.tick(hub, now=datetime.now(UTC) + timedelta(days=1))
        assert fired["fired"] == 1
        assert (await AU.tick(hub, now=datetime.now(UTC) + timedelta(days=1)))["fired"] == 0
        await fig("search_console", "clicks", today + timedelta(days=2), 500)
        calm = await AU.tick(hub, now=datetime.now(UTC) + timedelta(days=2))  # 520 is not < 100
        assert calm["fired"] == 0
    detail = (await client.get(f"/api/v1/automations/{ref}", headers=h)).json()
    assert detail["runs"] == 1 and {r["outcome"] for r in detail["run_log"]} == {"ok", "skipped"}
    note = await su.fetchval("SELECT count(*) FROM notify.notifications WHERE link_ref = $1", ref)
    assert note == 1


async def test_an_event_after_the_seal_runs_it_once_and_earlier_events_never(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    rule = {"trigger": {"kind": "event", "type": "support.message"}, "conditions": [],
            "actions": [work("پیام پشتیبانی")]}  # fmt: skip

    async def emit(code: str) -> None:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await events.emit(tx, code, "support.message", "C-1", {"channel": "chat"})

    await emit(co["code"])  # before the seal: never
    a = await propose(client, h, made, rule, co["code"])
    await seal(client, hub, owner_session, a["ref"])
    other = await new_company()
    async with holding_switch(su, "released"):
        await emit(other["code"])  # another company's event does not count
        await emit(co["code"])
        before = await run_work_count(su, co["id"])
        first = await AU.tick(hub)
        second = await AU.tick(hub)
    assert first["fired"] == 1 and second["fired"] == 0
    assert await run_work_count(su, co["id"]) == before + 1
    run = (await client.get(f"/api/v1/automations/{a['ref']}", headers=h)).json()["run_log"][0]
    assert run["trigger"]["kind"] == "event" and run["trigger"]["type"] == "support.message"
    assert run["key"].startswith("event:")


async def test_a_failing_automation_turns_itself_off_and_tells_the_owner(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any], egress: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    rule = {"trigger": {"kind": "event", "type": "revenue.alert"}, "conditions": [],
            "actions": [{"kind": "n8n.run", "args": {"workflow": "report-weekly"}}]}  # fmt: skip
    a = await propose(client, h, made, rule, co["code"])
    assert a["n8n_workflow"] == "report-weekly"
    await seal(client, hub, owner_session, a["ref"])
    async with holding_switch(su, "released"):
        for _ in range(AU.FAILURES_OFF + 1):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await events.emit(tx, co["code"], "revenue.alert", "A-1", {})
        out = await AU.tick(hub)  # n8n is not set up on this hub: every run fails plainly
    assert out["failed"] == AU.FAILURES_OFF  # the 4th event finds it already off
    detail = (await client.get(f"/api/v1/automations/{a['ref']}", headers=h)).json()
    assert detail["state"] == "off" and detail["off_reason"] == "failures"
    assert detail["failures_in_row"] == AU.FAILURES_OFF and detail["runs"] == AU.FAILURES_OFF
    assert detail["last_error_fa"] and H.is_persian_answer(detail["last_error_fa"])
    note = await su.fetchrow("SELECT title_fa, level FROM notify.notifications WHERE link_ref = $1",
                             a["ref"])  # fmt: skip
    assert note and "خاموش" in note["title_fa"]
    # switched on again by the owner, the count starts over
    on = await client.post(f"/api/v1/automations/{a['ref']}/state", headers=h, json={"state": "on"})
    assert on.json()["state"] == "on" and on.json()["failures_in_row"] == 0


async def test_n8n_run_posts_a_signed_webhook_and_a_missing_lines_engine_is_refused_plainly(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any], egress: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    posts: list[tuple[str, bytes, dict[str, str]]] = []

    async def post(url: str, body: bytes, headers: dict[str, str]) -> int:
        posts.append((url, body, headers))
        return 200

    AU.N8N_POST = post
    monkeypatch.setenv("HQ_N8N_URL", "http://n8n.test:5678")
    hub.bao = FakeBao({"hq/n8n": N8N_SECRET})
    rule = hourly({"kind": "n8n.run", "args": {"workflow": "report-weekly"}},
                  {"kind": "line.run", "args": {"line": "LN-0001"}})  # fmt: skip
    a = await propose(client, h, made, rule, co["code"])
    await seal(client, hub, owner_session, a["ref"])
    import hq_api.lines as lines_pkg

    monkeypatch.delattr(lines_pkg, "engine", raising=False)  # the lines engine is missing here
    monkeypatch.setitem(sys.modules, "hq_api.lines.engine", None)
    async with holding_switch(su, "released"):
        out = await AU.tick(hub, now=datetime.now(UTC) + timedelta(hours=2))
    assert out["failed"] == 1
    assert len(posts) == 1
    url, body, headers = posts[0]
    assert url == "http://n8n.test:5678/webhook/report-weekly"
    assert signing.verify(
        N8N_SECRET, body, headers[signing.HEADER]
    )  # signed with the shared secret
    assert N8N_SECRET.encode() not in body
    assert json.loads(body)["automation"] == a["ref"]
    run = (await client.get(f"/api/v1/automations/{a['ref']}", headers=h)).json()["run_log"][0]
    assert run["outcome"] == "failed"
    assert [s["ok"] for s in run["steps"]] == [
        True,
        False,
    ]  # the first step ran, the second stopped it
    assert "موتور خط" in run["steps"][1]["note_fa"]


async def test_lines_actions_call_the_engine_when_it_is_there(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, made: list[str],
    new_company: Callable[..., Any], monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    calls: list[tuple[str, str]] = []

    line = {"id": "line-id", "company_id": co["id"], "state": "on", "ref": "LN-0001"}

    async def load(tx: Any, ref: str) -> dict[str, Any]:
        assert ref == "LN-0001"
        return dict(line)

    async def set_state(tx: Any, row: dict[str, Any], state: str) -> dict[str, Any]:
        calls.append(("state", state))
        return {**row, "state": state}

    async def start_run(tx: Any, row: dict[str, Any], *, trigger: str, who: Any) -> dict[str, Any]:
        calls.append(("run", trigger))
        return {"ref": "RN-0001", "state": "queued"}

    async def kick(hub_: Any, ref: str) -> None:
        calls.append(("kick", ref))

    engine = types.SimpleNamespace(start_run=start_run, kick=kick)
    store = types.SimpleNamespace(load=load, set_state=set_state)
    monkeypatch.setitem(sys.modules, "hq_api.lines.engine", engine)
    monkeypatch.setitem(sys.modules, "hq_api.lines.store", store)
    import hq_api.lines as lines_pkg

    monkeypatch.setattr(lines_pkg, "engine", engine, raising=False)
    monkeypatch.setattr(lines_pkg, "store", store, raising=False)
    rule = hourly({"kind": "line.pause", "args": {"line": "LN-0001"}},
                  {"kind": "line.run", "args": {"line": "LN-0001"}})  # fmt: skip
    a = await propose(client, h, made, rule, co["code"])
    await seal(client, hub, owner_session, a["ref"])
    async with holding_switch(su, "released"):
        out = await AU.tick(hub, now=datetime.now(UTC) + timedelta(hours=2))
    assert out["fired"] == 1
    assert calls == [("state", "paused"), ("run", "owner"), ("kick", "RN-0001")]


# --------------------------------------------------------------- the ads --
def test_a_rule_trips_on_the_daily_cap_or_on_a_low_roas_after_the_minimum() -> None:
    today = date(2026, 11, 4)

    def days(*rows: tuple[int, float, float]) -> list[dict[str, Any]]:
        return [{"day": today - timedelta(days=d), "spend": s, "revenue": r} for d, s, r in rows]

    cap = {"daily_cap": 100, "min_roas": None, "window_days": 7, "min_spend_before_judging": 0}
    t = AD.judge(cap, days((0, 120, 0), (1, 20, 0)), today)
    assert t is not None and t.reason == "daily_cap" and "100" in t.detail_fa
    assert AD.judge(cap, days((0, 100, 0)), today) is None  # equal is not over
    roas = {"daily_cap": None, "min_roas": 2, "window_days": 3, "min_spend_before_judging": 50}
    low = AD.judge(roas, days((0, 30, 20), (1, 30, 20), (5, 900, 0)), today)
    assert (
        low is not None and low.reason == "min_roas" and "0.67" in low.detail_fa
    )  # 5 days ago is out
    assert AD.judge(roas, days((0, 20, 0), (1, 20, 0)), today) is None  # 40 < 50: not judged yet
    assert AD.judge(roas, days((0, 30, 90), (1, 30, 90)), today) is None  # 3.0 >= 2
    assert AD.judge(cap, days((4, 500, 0)), today) is None  # stale figures are not judged
    assert AD.judge(cap, [], today) is None
    assert AD.roas_of(60, 120) == 0.5 and AD.roas_of(5, 0) is None


def test_loosening_a_rule_is_what_needs_the_seal() -> None:
    old = {"daily_cap": 100, "min_roas": 2, "window_days": 7, "min_spend_before_judging": 50,
           "action": "pause", "state": "on", "scope": "account"}  # fmt: skip
    assert not AD.loosens(old, {**old, "daily_cap": 80, "min_roas": 3})  # tighter
    assert not AD.loosens(old, {**old, "window_days": 3, "scope": "111"} | {"scope": "account"})
    for change in ({"daily_cap": 150}, {"daily_cap": None}, {"min_roas": 1}, {"min_roas": None},
                   {"min_spend_before_judging": 500}, {"action": "notify"}, {"state": "off"},
                   {"scope": "111"}):  # fmt: skip
        assert AD.loosens(old, {**old, **change}), change


async def test_both_platforms_are_read_and_a_pause_changes_nothing_but_the_status(
    hub: Hub,
) -> None:
    today = date(2026, 11, 4)
    eg = AdsEgress(today)
    ctx = CN.ReadCtx(hub=hub, tx_factory=None, company_id=UUID(int=1), company="ZZ", kind="google_ads",
                     config={"customer_id": "123-456-7890", "login_customer_id": "5550001111"},
                     secret=SECRET_JSON, today=today, http=eg)  # fmt: skip
    rows, camps = await AD.read_google_ads(ctx)
    assert {(r.campaign_id, r.day): (r.spend, r.clicks) for r in rows} == {
        ("111", today): (120.0, 40), ("111", today - timedelta(days=1)): (20.0, 10)}  # fmt: skip
    assert {c.campaign_id: c.status for c in camps} == {"111": "active", "222": "paused"}
    search = next(c for c in eg.calls if c["url"].endswith("googleAds:searchStream"))
    assert "/customers/1234567890/" in search["url"] and search["headers"]["login-customer-id"]
    await AD.set_status(ctx, "111", paused=True)
    await AD.set_status(ctx, "111", paused=False)
    sent = [c["json_body"]["operations"] for c in eg.mutations()]
    assert [o[0]["update"]["status"] for o in sent] == ["PAUSED", "ENABLED"]
    for ops in sent:  # a status and nothing else: no budget, no bid, no target
        assert ops[0]["updateMask"] == "status" and set(ops[0]["update"]) == {
            "resourceName",
            "status",
        }
    mctx = CN.ReadCtx(hub=hub, tx_factory=None, company_id=UUID(int=1), company="ZZ", kind="meta_ads",
                      config={"account_id": "act_555"}, secret=META_TOKEN, today=today, http=eg)  # fmt: skip
    rows, camps = await AD.read_meta_ads(mctx)
    assert len(rows) == 1 and rows[0].spend == 30.5 and rows[0].conversions == 2.0
    assert rows[0].revenue == 90.0 and camps[0].status == "active"  # link_click is not a conversion
    eg.calls.clear()
    await AD.set_status(mctx, "333", paused=True)
    post = eg.mutations()[0]
    assert post["url"].endswith("/333") and parse_qs(post["body"]) == {"status": ["PAUSED"]}
    assert "budget" not in json.dumps(eg.calls).lower()
    with pytest.raises(CN.ReadError):
        await AD.set_status(mctx, "33; DROP", paused=True)
    for bad in ("not json", json.dumps({"clientId": "x"})):
        bad_ctx = CN.ReadCtx(hub=hub, tx_factory=None, company_id=UUID(int=1), company="ZZ",
                             kind="google_ads", config={"customer_id": "1234567890"}, secret=bad,
                             today=today, http=eg)  # fmt: skip
        with pytest.raises(CN.ReadError) as exc:
            await AD.read_google_ads(bad_ctx)
        assert H.is_persian_answer(exc.value.reason_fa)


async def seed_campaign(
    su: Any, co: dict[str, Any], today: date, spend: float, platform: str = "google_ads",
    campaign: str = "111", status: str = "active",
) -> None:  # fmt: skip
    await su.execute(
        """INSERT INTO growth.ad_campaigns (company_id, platform, campaign_id, name, status)
           VALUES ($1, $2, $3, 'جذب کاربر', $4)
           ON CONFLICT (company_id, platform, campaign_id) DO UPDATE SET status = $4, resumed_at = NULL""",
        co["id"], platform, campaign, status)  # fmt: skip
    await su.execute(
        """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend, revenue)
           VALUES ($1, $2, $3, $4, $5, 0)
           ON CONFLICT (company_id, platform, campaign_id, day) DO UPDATE SET spend = $5""",
        co["id"], platform, campaign, today, spend)  # fmt: skip


async def add_rule(su: Any, co: dict[str, Any], **kw: Any) -> UUID:
    cols = {"platform": "google_ads", "scope": "account", "daily_cap": 100, "min_roas": None,
            "window_days": 7, "min_spend_before_judging": 0, "action": "pause", **kw}  # fmt: skip
    return UUID(str(await su.fetchval(
        """INSERT INTO growth.ad_rules (company_id, platform, scope, daily_cap, min_roas, window_days,
               min_spend_before_judging, action) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
        co["id"], cols["platform"], cols["scope"], cols["daily_cap"], cols["min_roas"],
        cols["window_days"], cols["min_spend_before_judging"], cols["action"])))  # fmt: skip


@pytest.fixture
async def clean_rules(su: Any) -> AsyncIterator[list[UUID]]:
    ids: list[UUID] = []
    yield ids
    for i in ids:
        await su.execute("DELETE FROM growth.ad_rules WHERE id = $1", i)


async def test_the_daily_read_stores_each_campaigns_day_and_the_accounts_totals(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any
) -> None:
    co = await new_company()
    today = await today_of(hub)
    CN.OVERRIDE = AdsEgress(today)
    hub.bao = FakeBao({f"hq/growth/{co['code']}/google_ads": SECRET_JSON,
                       f"hq/growth/{co['code']}/meta_ads": META_TOKEN})  # fmt: skip
    await put_config(su, co["id"], "google_ads", {"customer_id": "1234567890"})
    await put_config(su, co["id"], "meta_ads", {"account_id": "555"})
    async with holding_switch(su, "released"):
        g = await CN.read_one(hub, co["id"], "google_ads")
        m = await CN.read_one(hub, co["id"], "meta_ads")
    assert g["state"] == "connected" and m["state"] == "connected", (g, m)
    day = {r["day"]: r for r in await su.fetch(
        "SELECT * FROM growth.ad_daily WHERE company_id = $1 AND platform = 'google_ads' "
        "ORDER BY day", co["id"])}  # fmt: skip
    now_row = day[today]
    assert float(now_row["spend"]) == 120 and now_row["clicks"] == 40
    assert float(now_row["revenue"]) == 60 and float(now_row["roas"]) == 0.5
    camps = {r["campaign_id"]: r for r in await su.fetch(
        "SELECT * FROM growth.ad_campaigns WHERE company_id = $1 AND platform = 'google_ads'", co["id"])}  # fmt: skip
    assert camps["111"]["status"] == "active" and camps["222"]["status"] == "paused"
    assert camps["222"]["paused_by"] == "platform"
    figs = {(r["kind"], r["key"]): float(r["value"]) for r in await su.fetch(
        "SELECT kind, key, value FROM growth.metrics_daily WHERE company_id = $1 AND day = $2",
        co["id"], today) if r["kind"] in ("google_ads", "meta_ads")}  # fmt: skip
    assert figs[("google_ads", "ad_spend")] == 120 and figs[("google_ads", "ad_roas")] == 0.5
    assert figs[("meta_ads", "ad_spend")] == 30.5 and figs[("meta_ads", "ad_conversions")] == 2
    # the secret is in OpenBao only
    dump = json.dumps([dict(r) for r in await su.fetch(
        "SELECT * FROM growth.connections WHERE company_id = $1", co["id"])], default=str)  # fmt: skip
    assert META_TOKEN not in dump and "refresh" not in dump
    # the hub's own revenue, where the owner attributed it (a campaign listed in the config)
    await put_config(su, co["id"], "google_ads",
                     {"customer_id": "1234567890", "hub_revenue_campaigns": ["111"], "usdt_rate": 2})  # fmt: skip
    acct = await su.fetchval(
        """INSERT INTO revenue.accounts (company_id, exchange, adapter, service_account, title_fa,
               created_by_kind, created_by_code)
           VALUES ($1, 'lbank', 'lbank-v2', 'lbank-test', 'حساب', 'owner', 'owner') RETURNING id""",
        co["id"])  # fmt: skip
    await su.execute("INSERT INTO revenue.days (company_id, account_id, day, commission_usdt) "
                     "VALUES ($1, $2, $3, 45)", co["id"], acct, today)  # fmt: skip
    async with holding_switch(su, "released"):
        await CN.read_one(hub, co["id"], "google_ads")
    assert float(await su.fetchval(
        "SELECT revenue FROM growth.ad_daily WHERE company_id = $1 AND campaign_id = '111' AND day = $2",
        co["id"], today)) == 90  # fmt: skip


async def test_a_tripped_rule_pauses_the_campaign_tells_the_lead_and_never_raises_a_budget(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any, clean_rules: list[UUID]
) -> None:
    co = await new_company()
    today = await today_of(hub)
    eg = AdsEgress(today)
    CN.OVERRIDE = eg
    hub.bao = FakeBao({f"hq/growth/{co['code']}/google_ads": SECRET_JSON})
    await put_config(su, co["id"], "google_ads", {"customer_id": "1234567890"})
    await seed_campaign(su, co, today, spend=120)
    await seed_campaign(su, co, today, spend=50, campaign="222")  # under the cap
    clean_rules.append(await add_rule(su, co))
    works = await run_work_count(su, co["id"])
    async with holding_switch(su, "released"):
        out = await AD.evaluate_due(hub)
        again = await AD.evaluate_due(hub)
    assert out["tripped"] == 1 and out["paused"] == 1 and again["tripped"] == 0
    sent = eg.mutations()
    assert len(sent) == 1  # once, whatever the number of ticks
    op = sent[0]["json_body"]["operations"][0]
    assert op["update"]["status"] == "PAUSED" and op["update"]["resourceName"].endswith(
        "/campaigns/111"
    )
    assert "budget" not in json.dumps(eg.calls).lower()
    assert sent[0]["account"]["secret"].startswith("ya29.")
    camp = await su.fetchrow("SELECT * FROM growth.ad_campaigns WHERE company_id = $1 AND "
                             "campaign_id = '111'", co["id"])  # fmt: skip
    assert camp["status"] == "paused" and camp["paused_by"] == "rule" and camp["paused_rule_id"]
    assert H.is_persian_answer(camp["paused_reason_fa"])
    assert (await su.fetchval("SELECT status FROM growth.ad_campaigns WHERE company_id = $1 "
                              "AND campaign_id = '222'", co["id"])) == "active"  # fmt: skip
    trip = await su.fetchrow("SELECT * FROM growth.ad_trips WHERE company_id = $1", co["id"])
    assert trip["outcome"] == "paused" and trip["reason"] == "daily_cap" and trip["work_id"]
    assert await run_work_count(su, co["id"]) == works + 1  # the growth lead's work item
    audit = await su.fetch("SELECT action, actor_code FROM audit.entries WHERE company_id = $1 "
                           "AND action = 'ads.trip'", co["id"])  # fmt: skip
    assert len(audit) == 1 and audit[0]["actor_code"] == "ads"
    ev = await su.fetchval("SELECT count(*) FROM core.outbox WHERE payload ->> 'type' = 'ad.paused' "
                           "AND payload ->> 'company' = $1", co["code"])  # fmt: skip
    assert ev == 1
    # the owner's weekly summary names it
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lines = await AD.weekly_lines(tx, co["id"], datetime.now(UTC) - timedelta(days=7),
                                      datetime.now(UTC) + timedelta(days=1))  # fmt: skip
    assert lines and "متوقف شد" in lines[0] and H.check(lines[0]) == []


async def test_notify_only_rules_do_not_touch_the_platform_and_a_failed_pause_is_tried_again(
    hub: Hub, su: Any, new_company: Callable[..., Any], egress: Any, clean_rules: list[UUID]
) -> None:
    co = await new_company()
    today = await today_of(hub)
    eg = AdsEgress(today)
    CN.OVERRIDE = eg
    hub.bao = FakeBao({f"hq/growth/{co['code']}/google_ads": SECRET_JSON,
                       f"hq/growth/{co['code']}/meta_ads": META_TOKEN})  # fmt: skip
    await put_config(su, co["id"], "google_ads", {"customer_id": "1234567890"})
    await put_config(su, co["id"], "meta_ads", {"account_id": "555"})
    await seed_campaign(su, co, today, spend=120)
    clean_rules.append(await add_rule(su, co, action="notify"))
    async with holding_switch(su, "released"):
        out = await AD.evaluate_due(hub)
    assert out["notified"] == 1 and eg.calls == []  # not even a read
    assert (await su.fetchval("SELECT status FROM growth.ad_campaigns WHERE company_id = $1",
                              co["id"])) == "active"  # fmt: skip
    # a pause that the platform refuses is recorded as failed and retried after half an hour
    await seed_campaign(su, co, today, spend=300, platform="meta_ads", campaign="333")
    clean_rules.append(await add_rule(su, co, platform="meta_ads", daily_cap=100))
    eg.fail_mutate = True
    async with holding_switch(su, "released"):
        failed = await AD.evaluate_due(hub)
        soon = await AD.evaluate_due(hub)
        eg.fail_mutate = False
        later = await AD.evaluate_due(hub, now=datetime.now(UTC) + timedelta(minutes=31))
    assert failed["failed"] == 1 and soon["tripped"] == 0
    assert later["paused"] == 1
    trip = await su.fetchrow("SELECT outcome, detail_fa FROM growth.ad_trips WHERE platform = 'meta_ads' "
                             "AND company_id = $1", co["id"])  # fmt: skip
    assert trip["outcome"] == "paused"
    assert (await su.fetchval("SELECT status FROM growth.ad_campaigns WHERE company_id = $1 AND "
                              "platform = 'meta_ads'", co["id"])) == "paused"  # fmt: skip
    # a locked company is not judged at all
    await seed_campaign(su, co, today, spend=999, campaign="444")
    calls = len(eg.calls)
    async with holding_switch(su, "engaged"):
        out = await AD.evaluate_due(hub)
    assert out.get("skipped") and len(eg.calls) == calls


async def test_ad_rules_and_resuming_are_the_owners_with_a_seal_where_it_loosens(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any,
    new_company: Callable[..., Any], egress: Any, clean_rules: list[UUID],
) -> None:  # fmt: skip
    h, sid = owner_session["headers"], owner_session["session_id"]
    co = await new_company()
    c = co["code"]
    body = {"platform": "google_ads", "daily_cap": 100, "min_roas": 1.5, "window_days": 7,
            "min_spend_before_judging": 40}  # fmt: skip
    noidem = await client.post(f"/api/v1/companies/{c}/ad-rules", headers=h, json=body)
    assert noidem.status_code in (400, 422)
    r = await client.post(f"/api/v1/companies/{c}/ad-rules", headers={**h, **idem()}, json=body)
    assert r.status_code == 201, r.text  # a new rule only adds a guard: no step-up
    rule = r.json()
    clean_rules.append(UUID(rule["id"]))
    assert (
        rule["action"] == "pause"
        and rule["state"] == "on"
        and H.is_persian_answer(rule["summary_fa"])
    )
    assert (
        await client.post(
            f"/api/v1/companies/{c}/ad-rules",
            headers={**h, **idem()},
            json={"platform": "meta_ads"},
        )
    ).status_code == 422  # nothing to judge
    path = f"/api/v1/companies/{c}/ad-rules/{rule['id']}"
    tighter = await client.put(path, headers=h, json={"daily_cap": 80})
    assert tighter.status_code == 200 and tighter.json()["daily_cap"] == 80
    looser = await client.put(path, headers=h, json={"daily_cap": 500})
    assert looser.status_code == 403  # raising a cap is 🔏 ads.cap
    su_h = await step_up(hub, sid, "ads.cap", rule["id"])
    ok = await client.put(path, headers={**h, **su_h}, json={"daily_cap": 500})
    assert ok.status_code == 200 and ok.json()["daily_cap"] == 500
    off = await client.put(path, headers=h, json={"state": "off"})
    assert off.status_code == 403
    assert (await client.delete(path, headers=h)).status_code == 403
    su_h = await step_up(hub, sid, "ads.cap", rule["id"])
    assert (await client.delete(path, headers={**h, **su_h})).status_code == 204
    assert (await client.get(f"/api/v1/companies/{c}/ad-rules", headers=h)).json() == []
    audit = await su.fetch("SELECT action, step_up FROM audit.entries WHERE company_id = $1 "
                           "AND action LIKE 'ads.%'", co["id"])  # fmt: skip
    assert sum(1 for a in audit if a["step_up"]) == 2
    # resume: the campaign on again at the platform, 🔏 ads.resume (target <platform>:<id>)
    today = await today_of(hub)
    eg = AdsEgress(today)
    CN.OVERRIDE = eg
    hub.bao = FakeBao({f"hq/growth/{c}/google_ads": SECRET_JSON})
    await put_config(su, co["id"], "google_ads", {"customer_id": "1234567890"})
    cid = str(int(co["id"].int % 10**9) + 900_000_000)  # a campaign id of this test's own
    await seed_campaign(su, co, today, spend=1, campaign=cid, status="paused")
    url = f"/api/v1/ads/campaigns/google_ads/{cid}/resume"
    assert (await client.post(url, headers=h)).status_code == 403
    wrong = await step_up(hub, sid, "ads.resume", f"meta_ads:{cid}")
    assert (await client.post(url, headers={**h, **wrong})).status_code == 403
    eg.fail_mutate = True
    su_h = await step_up(hub, sid, "ads.resume", f"google_ads:{cid}")
    refused = await client.post(url, headers={**h, **su_h})
    assert refused.status_code == 502 and H.is_persian_answer(refused.json()["message_fa"])
    assert (await su.fetchval("SELECT status FROM growth.ad_campaigns WHERE company_id = $1 AND "
                              "campaign_id = $2", co["id"], cid)) == "paused"  # fmt: skip
    eg.fail_mutate = False
    again = await client.post(url, headers={**h, **su_h})  # the same step-up: it was not spent
    assert again.status_code == 200, again.text
    assert again.json() == {
        "platform": "google_ads",
        "campaign_id": cid,
        "company": c,
        "status": "active",
    }
    op = eg.mutations()[-1]["json_body"]["operations"][0]["update"]
    assert op["status"] == "ENABLED" and op["resourceName"].endswith(f"/campaigns/{cid}")
    row = await su.fetchrow("SELECT status, resumed_at, paused_by FROM growth.ad_campaigns "
                            "WHERE company_id = $1 AND campaign_id = $2", co["id"], cid)  # fmt: skip
    assert row["status"] == "active" and row["resumed_at"] and row["paused_by"] is None
    # the overview: accounts, campaigns with 30 days, trips
    view = (await client.get(f"/api/v1/companies/{c}/ads", headers=h)).json()
    assert [a["platform"] for a in view["accounts"]] == ["google_ads", "meta_ads"]
    assert view["accounts"][1]["state"] == "not_connected" and view["accounts"][1]["missing_fa"]
    camp = next(x for x in view["campaigns"] if x["campaign_id"] == cid)
    assert camp["status"] == "active" and camp["totals"]["spend"] == 1 and len(camp["days"]) == 1
    # nobody but the owner
    assert (await client.get(f"/api/v1/companies/{c}/ads")).status_code == 401


async def test_the_two_platforms_are_connection_kinds_with_their_guides(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    assert {"google_ads", "meta_ads"} <= set(CN.KINDS)
    co = await new_company()
    listed = (await client.get(f"/api/v1/companies/{co['code']}/connections", headers=owner)).json()
    ads = {x["kind"]: x for x in listed if x["kind"] in ("google_ads", "meta_ads")}
    assert set(ads) == {"google_ads", "meta_ads"}
    assert all(x["secret_needed"] is True and x["reader"] is True for x in ads.values())
    assert (
        "رمز اتصال" in ads["google_ads"]["missing_fa"]
        and ads["meta_ads"]["state"] == "not_connected"
    )
    for kind in ("google_ads", "meta_ads"):
        g = (await client.get(f"/api/v1/connections/guides/{kind}", headers=owner)).json()
        assert H.is_persian_answer(g["body_md"], threshold=0.5) and H.check(g["body_md"]) == []
        assert "گام" in g["body_md"] and "بودجه را بالا نمیبرد" in g["body_md"]
        assert "developer_token" not in json.dumps(ads[kind])


async def test_the_new_events_are_on_the_growth_topic() -> None:
    topic = events.TOPICS["growth"]
    assert all(
        any(t.startswith(p) for p in topic) for t in ("ad.paused", "ad.resumed", "automation.run")
    )
    assert not any("advisor.proactive".startswith(p) for p in topic if p in ("ad.", "automation."))


def _load_0042() -> Any:
    import importlib.util
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    spec = importlib.util.spec_from_file_location("m0042", versions / "0042_ads_automations.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_migration_0042_downgrades_cleanly_and_keeps_other_kinds(su: Any) -> None:
    """The downgrade script runs (inside a transaction that is rolled back): the
    tables and the sequence go, the two kinds leave the three checks, every
    other kind a parallel migration added stays."""
    mod = _load_0042()
    assert mod.revision == "0042"
    tx = su.transaction()
    await tx.start()
    try:
        # one check printed the other way ('{a,b}'::text[]), as a parallel migration may leave it
        await su.execute(
            """ALTER TABLE growth.connections DROP CONSTRAINT connections_kind_check;
               ALTER TABLE growth.connections ADD CONSTRAINT connections_kind_check CHECK (
                   kind = ANY ('{bing,ga4,instagram,pagespeed,play_console,search_console,telegram,trends,x,youtube,google_ads,meta_ads,newsletter}'::text[]));"""
        )
        got = await su.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'connections_kind_check' AND conrelid = 'growth.connections'::regclass"
        )
        assert "'{" in got
        await su.execute(mod.DOWNGRADE)
        got = await su.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'connections_kind_check' AND conrelid = 'growth.connections'::regclass"
        )
        assert "newsletter" in got and "google_ads" not in got
        assert await su.fetchval("SELECT to_regclass('growth.ad_rules')") is None
        assert await su.fetchval("SELECT to_regclass('growth.automations')") is None
        defs = await su.fetch(
            """SELECT pg_get_constraintdef(c.oid) AS d FROM pg_constraint c
               WHERE c.contype = 'c' AND c.conrelid IN ('growth.connections'::regclass,
                     'growth.metrics_daily'::regclass, 'owner.progress'::regclass)
                 AND pg_get_constraintdef(c.oid) LIKE '%(kind = ANY%'"""
        )
        assert len(defs) == 3
        for r in defs:
            assert "google_ads" not in r["d"] and "meta_ads" not in r["d"]
            assert "search_console" in r["d"] and "telegram" in r["d"]
    finally:
        await tx.rollback()
    assert await su.fetchval("SELECT to_regclass('growth.ad_rules')") is not None
