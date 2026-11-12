"""Prompt 24 (contract §33.8-§33.9): the company journey, personas and the message test.

The model is a fake router (`workflows_client.route_order`), every request kept. The tables of the
other parts of prompt 24 (payments, leads) are stand-ins made here only when the hub has none, so a
stage that reads them can be shown reached; with none at all the stages stay unreached without an
error. The persona_test step runs through the real engine with a fake text step before it.
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import journey as J
from hq_api.domain import kits as K
from hq_api.hub import Hub
from hq_api.lines import adapters, engine
from hq_api.lines import templates as T
from hq_api.lines.base import REGISTRY, StepOutput

from .conftest import agent_headers
from .p10_fakes import holding_switch
from .test_p22_engine import Fake, get_run, make_line, seal, start, steps_of

API = "/api/v1"
FIXTURES = Path(__file__).parent / "lines_fixture_p24"
NEXT_LINE = "اولین مشتری‌ها را از میان بازدیدکننده‌ها پیدا کنید و با آن‌ها حرف بزنید."


# ----------------------------------------------------------------- fakes --
class Router:
    """The router, faked: every request is kept; `handlers` answer by the request's purpose."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def of(self, purpose: str) -> list[dict[str, Any]]:
        return [r for r in self.seen if r["meta"]["purpose"] == purpose]

    async def __call__(self, hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> Any:
        self.seen.append(req)
        fn = self.handlers.get(req["meta"]["purpose"])
        if fn is None:
            return {"routes": None, "status": "error"}
        got = fn(req)
        if got is None:
            return None
        return {"routes": got, "status": "ok", "input_tokens": 200, "output_tokens": 50}


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> Router:
    r = Router()
    r.handlers["journey_next"] = lambda req: {"next_fa": NEXT_LINE}
    monkeypatch.setattr(workflows_client, "route_order", r)
    return r


@pytest.fixture(autouse=True)
def fixture_templates() -> Any:
    T.use_dirs(FIXTURES)
    T._load.cache_clear()
    yield
    T.use_dirs()
    T._load.cache_clear()


async def table_exists(su: Any, name: str) -> bool:
    return bool(await su.fetchval("SELECT to_regclass($1) IS NOT NULL", name))


@pytest.fixture
async def payments(su: Any) -> AsyncIterator[bool]:
    """A stand-in `money.payments` when the hub has none (True), else the real one (False)."""
    if await table_exists(su, "money.payments"):
        yield False
        return
    await su.execute(
        """CREATE SCHEMA IF NOT EXISTS money;
           CREATE TABLE money.payments (company_id uuid NOT NULL, customer text, status text NOT NULL,
               amount_usdt numeric, paid_at timestamptz NOT NULL);
           GRANT USAGE ON SCHEMA money TO hq_api, hq_worker;
           GRANT SELECT ON money.payments TO hq_api, hq_worker;"""
    )
    try:
        yield True
    finally:
        await su.execute("DROP TABLE money.payments; DROP SCHEMA money")


@pytest.fixture
async def leads(su: Any) -> AsyncIterator[bool]:
    """A stand-in `growth.leads` when the hub has no leads table (True), else False."""
    if await table_exists(su, "sales.leads") or await table_exists(su, "growth.leads"):
        yield False
        return
    await su.execute(
        """CREATE TABLE growth.leads (company_id uuid NOT NULL, ref text NOT NULL,
               created_at timestamptz NOT NULL DEFAULT now());
           GRANT SELECT ON growth.leads TO hq_api, hq_worker;"""
    )
    try:
        yield True
    finally:
        await su.execute("DROP TABLE growth.leads")


def by_key(journey: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["key"]: s for s in journey["stages"]}


async def get_journey(client: httpx.AsyncClient, h: dict[str, str], code: str) -> dict[str, Any]:
    r = await client.get(f"{API}/companies/{code}/journey", headers=h)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def J_at(text: str) -> datetime:  # a parsed timestamp of the journey JSON
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


async def stage_events(su: Any, code: str) -> list[str]:
    rows = await su.fetch(
        "SELECT payload->>'ref' AS ref FROM core.outbox WHERE subject = $1 ORDER BY id",
        f"hq.core.{code}.journey.stage",
    )
    return [r["ref"] for r in rows]


# ----------------------------------------------------------------- units --
def test_the_default_stages_are_the_contracts_and_data() -> None:
    assert [s["key"] for s in J.DEFAULT_STAGES] == [
        "founded", "server_ready", "first_content", "first_visitor", "first_lead",
        "first_payment", "ten_paying", "break_even",
    ]  # fmt: skip
    assert {s["rule"]["kind"] for s in J.DEFAULT_STAGES} <= set(J.RULE_KINDS)
    assert J.current_of(list(J.DEFAULT_STAGES), {}) == "founded"
    assert J.current_of(list(J.DEFAULT_STAGES), {"founded": 1, "first_lead": 1}) == "first_lead"
    target = J.next_target(list(J.DEFAULT_STAGES), {"founded": 1})
    assert target is not None and target["key"] == "server_ready"
    assert J.next_target(list(J.DEFAULT_STAGES), {s["key"]: 1 for s in J.DEFAULT_STAGES}) is None
    assert J.fallback_line(None) and "«سرور آماده»" in J.fallback_line(J.DEFAULT_STAGES[1])


def test_a_kits_stages_are_checked_and_both_seed_kits_have_them() -> None:
    got = J.normalize_stages(
        ["founded", {"key": "ten_paying", "rule": {"kind": "paying", "min": 3}}]
    )
    assert got[1]["title_fa"] == "ده مشتری پرداخت‌کننده" and got[1]["rule"]["min"] == 3
    own = J.normalize_stages(
        [{"key": "first_demo", "title_fa": "اولین دمو", "rule": {"kind": "leads"}}]
    )
    assert own[0]["key"] == "first_demo"
    for bad in (
        [], "founded", ["founded", "founded"], ["Bad Key"], [{"key": "x"}],
        [{"key": "first_demo", "title_fa": "ا", "rule": {"kind": "magic"}}],
        [{"key": "founded", "rule": {"kind": "company", "min": 2}}],
        [{"key": "founded", "extra": 1}], [3],
        [{"key": "ten_paying", "rule": {"kind": "paying", "min": 0}}],
        [{"key": "first_demo", "title_fa": "", "rule": {"kind": "leads"}}],
        [{"key": "first_demo", "title_fa": "ا", "rule": {"kind": "leads", "other": 1}}],
        ["founded"] * 21,
    ):  # fmt: skip
        with pytest.raises(ValueError):
            J.normalize_stages(bad)
    for key in ("content_brand", "saas_product"):
        assert J.normalize_stages(K.kit(key)["journey"])
    broken = {**K.kit("saas_product"), "journey": ["nope!"]}
    with pytest.raises(ValueError, match=r"journey|stage"):
        K.validate("saas_product", broken)


def test_the_persona_test_step_settings_are_checked() -> None:
    def tpl(**settings: Any) -> dict[str, Any]:
        return {
            "key": "pt", "title_fa": "ا", "platform": "telegram_post", "version": 1,
            "steps": [
                {"key": "draft", "kind": "gpt_text", "title_fa": "ا"},
                {"key": "check", "kind": "persona_test", "title_fa": "ا", "inputs": ["draft"],
                 "settings": settings},
            ],
        }  # fmt: skip

    assert (
        T.validate(tpl(min_score=80, aggregate="min", text_from="draft")).steps[1].kind
        == "persona_test"
    )
    assert T.validate(tpl()).steps[1].settings == {}  # defaults: 60 and the mean
    for bad in ({"min_score": 101}, {"min_score": -1}, {"min_score": "70"}, {"min_score": True},
                {"aggregate": "max"}, {"text_from": "later"}):  # fmt: skip
        with pytest.raises(ValueError):
            T.validate(tpl(**bad))


# --------------------------------------------------------------- journey --
async def test_a_new_company_is_founded_and_one_line_is_written_once(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router,
    su: Any, payments: bool, leads: bool,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    j = await get_journey(client, h, co["code"])
    s = by_key(j)
    assert [x["key"] for x in j["stages"]] == [x["key"] for x in J.DEFAULT_STAGES]
    assert s["founded"]["reached_at"] and s["founded"]["evidence"] == {
        "kind": "company",
        "ref": co["code"],
    }
    assert all(s[k]["reached_at"] is None and s[k]["evidence"] is None for k in list(s)[1:])
    assert j["current"] == "founded" and j["days_in_stage"] == 0 and j["next_fa"] == NEXT_LINE
    # one mid-model call, its own task class, a strict schema, the company's own code
    assert len(router.of("journey_next")) == 1
    q = router.of("journey_next")[0]
    assert q["task_class"] == "journey_next" and q["company_code"] == co["code"]
    assert "sonnet" in q["model"] and q["json_schema"]["additionalProperties"] is False
    assert q["max_output_tokens"] <= 500 and "سرور آماده" in q["prompt"]
    # nothing changed: nothing is asked again, and no stream event (the first look is the baseline)
    again = await get_journey(client, h, co["code"])
    assert again == j and len(router.of("journey_next")) == 1
    assert await stage_events(su, co["code"]) == []


async def test_a_missing_upstream_table_leaves_its_stages_unreached_without_error(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router,
    su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    have = [
        t for t in ("money.payments", "sales.leads", "growth.leads") if await table_exists(su, t)
    ]
    if have:
        pytest.skip(f"the hub already has {have}; the stand-in tests below cover them")
    j = by_key(await get_journey(client, h, co["code"]))
    for k in ("first_lead", "first_payment", "ten_paying", "break_even"):
        assert j[k]["reached_at"] is None
    # a table that is there but not as expected is the same: unreached, no error
    await su.execute(
        """CREATE SCHEMA IF NOT EXISTS money; CREATE TABLE money.payments (company_id uuid);
           GRANT USAGE ON SCHEMA money TO hq_api, hq_worker; GRANT SELECT ON money.payments TO hq_api, hq_worker;"""
    )
    try:
        await su.execute("INSERT INTO money.payments VALUES ($1)", co["id"])
        j = by_key(await get_journey(client, h, co["code"]))
        assert all(
            j[k]["reached_at"] is None for k in ("first_payment", "ten_paying", "break_even")
        )
    finally:
        await su.execute("DROP TABLE money.payments; DROP SCHEMA money")


async def test_stages_are_reached_from_existing_rows(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    base = by_key(await get_journey(client, h, co["code"]))  # the baseline look
    assert base["first_visitor"]["reached_at"] is None and len(router.of("journey_next")) == 1
    # analytics: the first day with visitors
    day = date.today() - timedelta(days=3)
    await su.execute(
        """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
           VALUES ($1, 'ga4', $2, 'sessions', '', 12, 'ga4')""",
        co["id"], day,
    )  # fmt: skip
    j = await get_journey(client, h, co["code"])
    visitor = by_key(j)["first_visitor"]
    assert visitor["evidence"] == {"kind": "metric", "ref": "sessions"}
    assert datetime.fromisoformat(visitor["reached_at"]).date() == day
    assert j["current"] == "first_visitor" and j["days_in_stage"] >= 3
    assert len(router.of("journey_next")) == 2  # a stage changed: one more call
    assert await stage_events(su, co["code"]) == ["first_visitor"]
    # a real (not dry) publish of a line, and a paired server
    h_line = await make_line(client, h, co["code"], template="persona_line")
    await su.execute(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, dry, published)
           SELECT $1, id, 1, 'owner', 'done', $3, $2::jsonb FROM lines.lines WHERE ref = $4""",
        co["id"], json.dumps([{"platform": "telegram_post", "kind": "post", "at": "2026-11-01T08:00:00+00:00"}]),
        True, h_line["ref"],
    )  # fmt: skip
    assert (
        by_key(await get_journey(client, h, co["code"]))["first_content"]["reached_at"] is None
    )  # dry
    await su.execute(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, dry, published)
           SELECT $1, id, 1, 'owner', 'done', false, $2::jsonb FROM lines.lines WHERE ref = $3""",
        co["id"], json.dumps([{"platform": "telegram_post", "kind": "post", "at": "2026-11-01T08:00:00+00:00"}]),
        h_line["ref"],
    )  # fmt: skip
    server = await su.fetchval(
        "INSERT INTO infra.servers (company_id, origin, name, state) VALUES ($1, 'attached', $2, 'online') RETURNING id",
        co["id"], f"j-{secrets.token_hex(3)}",
    )  # fmt: skip
    pairing = await su.fetchval(
        """INSERT INTO infra.runner_pairings (company_id, device_sha256, user_code, payload, expires_at, state, server_id)
           VALUES ($1, $2, 'ABCD-2345', '{}', now(), 'claimed', $3) RETURNING id""",
        co["id"], secrets.token_hex(32), server,
    )  # fmt: skip
    await su.execute(
        "INSERT INTO infra.runners (company_id, server_id, pairing_id, token_sha256) VALUES ($1, $2, $3, $4)",
        co["id"], server, pairing, secrets.token_hex(32),
    )  # fmt: skip
    j = await get_journey(client, h, co["code"])
    s = by_key(j)
    assert s["server_ready"]["evidence"]["kind"] == "server"
    assert s["first_content"]["evidence"]["kind"] == "line_run"
    assert s["first_content"]["reached_at"].startswith("2026-11-01T08:00")
    assert j["current"] == "first_visitor"  # the latest of the plan that is reached
    assert sorted(await stage_events(su, co["code"])) == [
        "first_content",
        "first_visitor",
        "server_ready",
    ]
    assert len(router.of("journey_next")) == 3  # one call for both stages that changed together
    # a reached stage stays reached, whatever happens to its rows
    await su.execute("DELETE FROM growth.metrics_daily WHERE company_id = $1", co["id"])
    assert (
        by_key(await get_journey(client, h, co["code"]))["first_visitor"]["reached_at"]
        == visitor["reached_at"]
    )
    # the timeline of all companies holds them, newest first
    r = await client.get(f"{API}/journeys", headers=h)
    assert r.status_code == 200, r.text
    board = r.json()
    reached = {
        st["key"]: st["reached_at"]
        for x in board["journeys"]
        if x["company"] == co["code"]
        for st in x["stages"]
        if st["reached_at"]
    }
    assert set(reached) == {"founded", "server_ready", "first_content", "first_visitor"}
    ats = [e["at"] for e in board["timeline"]]
    assert ats == sorted(ats, reverse=True)
    # the timeline keeps the newest 200 of every company (the test database holds many)
    mine = {e["stage"] for e in board["timeline"] if e["company"] == co["code"]}
    full = len(ats) < 200
    assert mine == {k for k, at in reached.items() if full or J_at(at) >= J_at(ats[-1])}
    assert co["code"] in {x["company"] for x in board["journeys"]}
    assert isinstance(await J.tick(hub), int)


async def test_payments_leads_and_break_even_read_the_other_parts_tables(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router,
    su: Any, payments: bool, leads: bool,
) -> None:  # fmt: skip
    if not (payments and leads):
        pytest.skip("the hub has the real payments or leads table; its own tests cover the stages")
    h = owner_session["headers"]
    co = await new_company()
    await get_journey(client, h, co["code"])
    now = datetime.now(UTC)
    # costs this month (ads) above what the first payments bring: not break-even yet
    await su.execute(
        """INSERT INTO growth.ad_daily (company_id, platform, campaign_id, day, spend)
           VALUES ($1, 'google_ads', '1', $2, 500)""",
        co["id"], now.date(),
    )  # fmt: skip
    await su.execute(
        "INSERT INTO growth.leads (company_id, ref) VALUES ($1, 'LD-000001')", co["id"]
    )
    j = by_key(await get_journey(client, h, co["code"]))
    assert j["first_lead"]["evidence"] == {"kind": "lead", "ref": "LD-000001"}
    assert j["first_payment"]["reached_at"] is None
    # an approved payment without money (ledger_only) is not a payment yet
    await su.execute(
        "INSERT INTO money.payments VALUES ($1, 'c0', 'ledger_only', 50, $2)", co["id"], now
    )
    assert by_key(await get_journey(client, h, co["code"]))["first_payment"]["reached_at"] is None
    await su.execute(
        "INSERT INTO money.payments VALUES ($1, 'c1', 'matched', 100, $2)",
        co["id"],
        now - timedelta(minutes=5),
    )
    j = by_key(await get_journey(client, h, co["code"]))
    assert (
        j["first_payment"]["evidence"]["kind"] == "payment"
        and j["ten_paying"]["reached_at"] is None
    )
    assert j["break_even"]["reached_at"] is None  # 100 < 500
    for i in range(2, 10):  # nine paying customers: not ten
        await su.execute(
            "INSERT INTO money.payments VALUES ($1, $2, 'matched', 30, $3)", co["id"], f"c{i}", now
        )
    j = by_key(await get_journey(client, h, co["code"]))
    assert j["ten_paying"]["reached_at"] is None and j["break_even"]["reached_at"] is None
    await su.execute(
        "INSERT INTO money.payments VALUES ($1, 'c10', 'chain_only', 200, $2)", co["id"], now
    )
    j = by_key(await get_journey(client, h, co["code"]))
    assert j["ten_paying"]["evidence"] == {"kind": "customers", "ref": "10"}
    assert j["break_even"]["evidence"] == {
        "kind": "month",
        "ref": now.strftime("%Y-%m"),
    }  # 100 + 8*30 + 200 >= 500


async def test_the_one_line_falls_back_to_code_when_the_model_is_down_or_wrong(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router,
    su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    router.handlers["journey_next"] = lambda req: None  # the router did not answer
    co = await new_company()
    j = await get_journey(client, h, co["code"])
    assert j["next_fa"] == "گام بعدی: «سرور آماده»."
    router.handlers["journey_next"] = lambda req: {
        "next_fa": "Buy more ads now and double the budget"
    }
    co2 = await new_company()
    assert (await get_journey(client, h, co2["code"]))["next_fa"] == "گام بعدی: «سرور آماده»."
    assert await stage_events(su, co2["code"]) == []


async def test_a_company_made_from_a_kit_keeps_the_kits_stages(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await J.adopt_kit(tx, co["id"], "saas_product", K.kit("saas_product"))
        assert not await J.adopt_kit(tx, co["id"], "x", {"title_fa": "no journey here"})
    j = await get_journey(client, h, co["code"])
    assert [s["key"] for s in j["stages"]] == [
        s["key"]
        for s in K.kit("saas_product")["journey"]
        and J.normalize_stages(K.kit("saas_product")["journey"])
    ]
    assert len(j["stages"]) == 8


async def test_the_journey_is_the_owners(
    client: httpx.AsyncClient, new_company: Any, router: Router,
) -> None:  # fmt: skip
    co = await new_company()
    ceo = await agent_headers(f"{co['code']}-CEO")
    for method, url in (
        ("GET", f"/companies/{co['code']}/journey"), ("GET", "/journeys"),
        ("GET", f"/companies/{co['code']}/personas"),
        ("POST", f"/companies/{co['code']}/personas/test"),
    ):  # fmt: skip
        r = await client.request(
            method, API + url, headers=ceo, json={"text": "x"} if method == "POST" else None
        )
        assert r.status_code in (401, 403), (url, r.status_code)
    assert (await client.get(f"{API}/companies/{co['code']}/journey")).status_code == 401


async def test_the_holding_and_unknown_companies_have_no_journey(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], router: Router,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    holding = await hub.companies.holding()
    assert (
        await client.get(f"{API}/companies/{holding.code}/journey", headers=h)
    ).status_code == 404
    assert (await client.get(f"{API}/companies/NOPE/journey", headers=h)).status_code == 404


# -------------------------------------------------------------- personas --
PERSONA = {
    "name_fa": "معامله‌گر تازه‌کار",
    "summary_fa": "تازه وارد بازار شده و از ضرر می‌ترسد.",
    "pains_fa": ["ضرر در معامله‌ی اول", "نبود آموزش ساده"],
    "objections_fa": ["اعتماد ندارم"],
    "channel_fa": "تلگرام",
}


async def add_persona(
    client: httpx.AsyncClient, h: dict[str, str], code: str, **over: Any
) -> dict[str, Any]:
    r = await client.post(f"{API}/companies/{code}/personas", json={**PERSONA, **over}, headers=h)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def test_personas_are_the_owners_data(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    p = await add_persona(client, h, co["code"])
    assert p["company"] == co["code"] and p["version"] == 1 and p["source"] == "owner"
    assert p["pains_fa"] == PERSONA["pains_fa"]
    kept = await add_persona(
        client, h, co["code"], name_fa="سرمایه‌گذار آرام", source="kb_suggested"
    )
    assert kept["source"] == "kb_suggested"
    r = await client.get(f"{API}/companies/{co['code']}/personas", headers=h)
    assert [x["id"] for x in r.json()] == [p["id"], kept["id"]]
    # an edit counts a version; a kept suggestion edited becomes the owner's own
    r = await client.patch(
        f"{API}/personas/{kept['id']}", json={"summary_fa": "خلاصه‌ی تازه"}, headers=h
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["version"] == 2
        and r.json()["source"] == "owner"
        and r.json()["summary_fa"] == "خلاصه‌ی تازه"
    )
    assert r.json()["name_fa"] == "سرمایه‌گذار آرام" and r.json()["pains_fa"] == PERSONA["pains_fa"]
    r = await client.patch(f"{API}/personas/{p['id']}", json={"pains_fa": ["یک درد"]}, headers=h)
    assert (
        r.json()["pains_fa"] == ["یک درد"] and r.json()["objections_fa"] == PERSONA["objections_fa"]
    )
    assert (await client.patch(f"{API}/personas/{p['id']}", json={}, headers=h)).status_code == 422
    # a secret in a persona is masked before it is stored
    token = "sk-" + "a1" * 20
    leaky = await add_persona(client, h, co["code"], summary_fa=f"کلید {token} دارد", name_fa="نشت")
    assert token not in leaky["summary_fa"]
    # archive: out of the list, the row stays
    assert (await client.delete(f"{API}/personas/{leaky['id']}", headers=h)).status_code == 204
    assert (await client.delete(f"{API}/personas/{leaky['id']}", headers=h)).status_code == 404
    assert (
        await client.patch(f"{API}/personas/{leaky['id']}", json={"name_fa": "x"}, headers=h)
    ).status_code == 404
    assert len((await client.get(f"{API}/companies/{co['code']}/personas", headers=h)).json()) == 2
    assert (
        await su.fetchval("SELECT count(*) FROM growth.personas WHERE company_id = $1", co["id"])
        == 3
    )
    # at most eight a company
    for i in range(6):
        await add_persona(client, h, co["code"], name_fa=f"پرسونا {i}")
    r = await client.post(f"{API}/companies/{co['code']}/personas", json=PERSONA, headers=h)
    assert r.status_code == 409 and "حداکثر" in r.json()["message_fa"]
    bad = await client.post(
        f"{API}/companies/{co['code']}/personas", json={**PERSONA, "source": "agent"}, headers=h
    )
    assert bad.status_code == 422
    assert (await client.get(f"{API}/companies/NOPE/personas", headers=h)).status_code == 404


async def put_knowledge(su: Any, company_id: Any, title: str, body: str) -> None:
    await su.execute(
        """INSERT INTO knowledge.entries (company_id, layer, kind, title_fa, body_md, sources, valid_until,
               status, approved_by_kind, approved_by_code, approved_at, created_by_kind, created_by_code)
           VALUES ($1, 'company', 'faq', $2, $3, '[{"kind": "owner"}]'::jsonb, current_date + 30,
                   'approved', 'owner', 'owner', now(), 'owner', 'owner')""",
        company_id, title, body,
    )  # fmt: skip


def suggestions(req: dict[str, Any]) -> dict[str, Any]:
    def one(n: int) -> dict[str, Any]:
        return {"name_fa": f"مخاطب {n}", "summary_fa": "خلاصه", "pains_fa": ["درد"], "objections_fa": ["ایراد"],
                "channel_fa": "تلگرام"}  # fmt: skip

    return {"personas": [one(i) for i in range(5)] + [{"name_fa": "", "summary_fa": "x"}]}


async def test_suggestions_come_from_the_knowledge_and_are_saved_only_when_kept(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router, su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    url = f"{API}/companies/{co['code']}/personas/suggest"
    r = await client.post(url, headers=h)  # no knowledge yet
    assert r.status_code == 422 and "دانش" in r.json()["message_fa"] and not router.seen
    await put_knowledge(
        su, co["id"], "مشتری ما کیست", "کاربران تازه‌کار بازار که آموزش ساده می‌خواهند."
    )
    router.handlers["persona_suggest"] = suggestions
    r = await client.post(url, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (
        len(out["personas"]) == 4 and "تا نگه نداشته‌ای" in out["basis_fa"]
    )  # clipped; the empty one is dropped
    q = router.of("persona_suggest")
    assert len(q) == 1 and q[0]["task_class"] == "persona_test" and "sonnet" in q[0]["model"]
    assert (
        "مشتری ما کیست" in q[0]["prompt"]
        and q[0]["json_schema"]["properties"]["routes"]["properties"]["personas"]["maxItems"] == 4
    )
    assert (
        await su.fetchval("SELECT count(*) FROM growth.personas WHERE company_id = $1", co["id"])
        == 0
    )
    kept = await add_persona(
        client, h, co["code"], **{**out["personas"][0], "source": "kb_suggested"}
    )
    assert kept["source"] == "kb_suggested"
    # the model down or nonsense: 422 with a plain reason, nothing saved (never a 5xx)
    router.handlers["persona_suggest"] = lambda req: None
    r = await client.post(url, headers=h)
    assert r.status_code == 422 and r.json()["message_fa"]
    router.handlers["persona_suggest"] = lambda req: {"personas": [{"name_fa": ""}]}
    assert (await client.post(url, headers=h)).status_code == 422


def verdicts(*scores: int) -> Callable[[dict[str, Any]], Any]:
    def answer(req: dict[str, Any]) -> dict[str, Any]:
        asked = json.loads(req["prompt"])["personas"]
        return {"results": [
            {"persona": a["persona"], "score": s, "would_act": s >= 60,
             "objection_fa": None if s >= 70 else f"ایراد {a['name']}", "fix_fa": None if s >= 70 else "کوتاه‌تر بنویس"}
            for a, s in zip(asked, scores, strict=True)
        ]}  # fmt: skip

    return answer


async def test_a_message_is_tested_in_one_call_and_checked_by_code(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, router: Router, su: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    url = f"{API}/companies/{co['code']}/personas/test"
    r = await client.post(url, json={"text": "سلام"}, headers=h)  # no persona yet
    assert r.status_code == 422 and "پرسونا" in r.json()["message_fa"] and not router.seen
    p1 = await add_persona(client, h, co["code"])
    p2 = await add_persona(client, h, co["code"], name_fa="سرمایه‌گذار آرام")
    router.handlers["persona_test"] = verdicts(85, 40)
    token = "sk-" + "b2" * 20
    r = await client.post(url, json={"text": f"با ما معامله کن؛ کلید {token}"}, headers=h)
    assert r.status_code == 200, r.text
    t = r.json()
    assert [x["persona"] for x in t["results"]] == [p1["id"], p2["id"]]  # the personas' own order
    assert (
        [x["score"] for x in t["results"]] == [85, 40] and t["average"] == 62 and t["lowest"] == 40
    )
    assert t["results"][0]["objection_fa"] is None and t["results"][1]["objection_fa"].startswith(
        "ایراد"
    )
    assert t["results"][1]["name_fa"] == "سرمایه‌گذار آرام" and t["results"][0]["would_act"] is True
    assert token not in t["text"]
    q = router.of("persona_test")
    assert len(q) == 1  # ONE call for all the personas
    assert (
        q[0]["task_class"] == "persona_test"
        and "sonnet" in q[0]["model"]
        and token not in q[0]["prompt"]
    )
    assert len(json.loads(q[0]["prompt"])["personas"]) == 2
    item = q[0]["json_schema"]["properties"]["routes"]["properties"]["results"]
    assert (
        item["minItems"] == item["maxItems"] == 2 and item["items"]["additionalProperties"] is False
    )
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.persona_tests WHERE company_id = $1", co["id"]
        )
        == 1
    )
    # an answer that fails the check is a 422 and is never stored
    good = verdicts(80, 80)

    def broken(mutate: Callable[[list[dict[str, Any]]], None]) -> Callable[[dict[str, Any]], Any]:
        def answer(req: dict[str, Any]) -> Any:
            out = good(req)
            mutate(out["results"])
            return out

        return answer

    def duplicate(rs: list[dict[str, Any]]) -> None:
        rs[1]["persona"] = rs[0]["persona"]

    def stranger(rs: list[dict[str, Any]]) -> None:
        rs[1]["persona"] = "p9"

    def too_high(rs: list[dict[str, Any]]) -> None:
        rs[0]["score"] = 150

    def not_a_number(rs: list[dict[str, Any]]) -> None:
        rs[0]["score"] = "high"

    def no_verdict(rs: list[dict[str, Any]]) -> None:
        rs[0]["would_act"] = "yes"

    def missing(rs: list[dict[str, Any]]) -> None:
        del rs[1]

    for mutate in (duplicate, stranger, too_high, not_a_number, no_verdict, missing):
        router.handlers["persona_test"] = broken(mutate)
        r = await client.post(url, json={"text": "پیام"}, headers=h)
        assert r.status_code == 422, mutate.__name__
    router.handlers["persona_test"] = lambda req: ["not", "an", "object"]
    assert (await client.post(url, json={"text": "پیام"}, headers=h)).status_code == 422
    router.handlers["persona_test"] = lambda req: None
    r = await client.post(url, json={"text": "پیام"}, headers=h)
    assert r.status_code == 422 and r.json()["message_fa"]
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.persona_tests WHERE company_id = $1", co["id"]
        )
        == 1
    )
    assert (await client.post(url, json={"text": ""}, headers=h)).status_code == 422
    assert (await client.post(url, json={"text": "  "}, headers=h)).status_code == 422


# ----------------------------------------------------- the line step gate --
@pytest.fixture
def line_fakes() -> Any:
    adapters.load()
    saved = dict(REGISTRY)
    seen: dict[str, list[Any]] = {"deliver": []}

    async def draft(ctx: Any) -> StepOutput:
        return StepOutput(text="این یک پیام آزمایشی برای مخاطب است.", via="chatgpt-web")

    async def deliver(ctx: Any) -> StepOutput:
        seen["deliver"].append(ctx)
        return StepOutput(text="delivered", via="telegram")

    REGISTRY["gpt_text"] = Fake("gpt_text", draft)
    REGISTRY["deliver"] = Fake("deliver", deliver)
    yield seen
    REGISTRY.clear()
    REGISTRY.update(saved)


async def persona_line(
    client: httpx.AsyncClient, h: dict[str, str], co: dict[str, Any]
) -> dict[str, Any]:
    await add_persona(client, h, co["code"])
    await add_persona(client, h, co["code"], name_fa="سرمایه‌گذار آرام")
    return await make_line(client, h, co["code"], template="persona_line")


async def test_below_min_score_the_run_waits_for_the_owner_with_the_objections(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await persona_line(client, h, co)
    router.handlers["persona_test"] = verdicts(40, 50)  # mean 45 < 70
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
        run = await get_run(client, h, run["ref"])
        s = steps_of(run)
        assert run["state"] == "waiting" and run["decision"]
        assert s["check"]["state"] == "waiting" and s["check"]["gate"] == "owner"
        assert s["send"]["state"] == "pending" and not line_fakes["deliver"]
        out = s["check"]["output"]
        assert (
            out["data"]["score"] == 45
            and out["data"]["min_score"] == 70
            and out["data"]["passed"] is False
        )
        assert len(out["data"]["results"]) == 2 and out["text"]
        card = (await client.get(f"{API}/decisions/{run['decision']}", headers=h)).json()
        assert card["kind"] == "line_publish" and card["payload"]["step"] == "check"
        assert "45" in card["why"] and "ایراد" in card["why"] and "کوتاه‌تر بنویس" in card["why"]
        assert len(router.of("persona_test")) == 1
        # the owner seals with the objections in front of him: the run goes on, no second model call
        await seal(client, hub, owner_session, run)
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
    run = await get_run(client, h, run["ref"])
    s = steps_of(run)
    assert s["check"]["state"] == "done" and s["check"]["sealed_by"] == "owner"
    assert s["check"]["output"]["data"] == {"passed": True, "passed_by": "owner", "sealed": True}
    assert s["send"]["state"] == "done" and len(line_fakes["deliver"]) == 1
    assert len(router.of("persona_test")) == 1
    assert run["cost"]["tokens"] == 250  # the test's tokens are in the run, once
    assert (
        await su.fetchval(
            "SELECT count(*) FROM growth.persona_tests WHERE run_ref = $1", run["ref"]
        )
        == 1
    )


async def test_the_owner_can_refuse_a_message_that_scored_low(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await persona_line(client, h, co)
    router.handlers["persona_test"] = verdicts(10, 20)
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
        run = await seal(
            client, hub, owner_session, await get_run(client, h, run["ref"]), approve=False
        )
    assert run["state"] == "cancelled" and not line_fakes["deliver"]
    assert steps_of(run)["check"]["state"] == "failed"


async def test_at_or_above_min_score_and_in_a_dry_run_the_run_does_not_wait(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await persona_line(client, h, co)
    async with holding_switch(su, "released"):
        router.handlers["persona_test"] = verdicts(70, 90)  # mean 80, lowest 70: at the line
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
        done = steps_of(await get_run(client, h, run["ref"]))
        assert done["check"]["output"]["data"]["passed"] is True and done["check"]["gate"] is None
        assert done["check"]["output"]["text"] == "این یک پیام آزمایشی برای مخاطب است."
        # a dry run tests and shows the result but never waits
        router.handlers["persona_test"] = verdicts(5, 5)
        dry = await start(client, h, line["ref"], dry=True)
        assert (await engine.drive(hub, dry["ref"]))["state"] == "done"
        dry_run = await get_run(client, h, dry["ref"])
        assert dry_run["decision"] is None
        assert steps_of(dry_run)["check"]["output"]["data"]["passed"] is False
    assert len(line_fakes["deliver"]) == 2


async def test_the_step_fails_plainly_when_the_model_or_the_personas_are_missing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"], template="persona_line")  # no persona yet
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "failed"
        run = await get_run(client, h, run["ref"])
        assert "پرسونا" in steps_of(run)["check"]["error_fa"] and not line_fakes["deliver"]
        await add_persona(client, h, co["code"])
        router.handlers["persona_test"] = lambda req: (
            None
        )  # the model is down: nothing passes untested
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "failed"
    run = await get_run(client, h, run["ref"])
    assert steps_of(run)["check"]["error_fa"] and not line_fakes["deliver"]


async def test_a_model_that_did_not_answer_is_tried_again_a_bad_answer_is_not(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    """A passing outage of the model or the router is retried while attempts remain; an answer
    that fails the check fails the step at once."""
    h = owner_session["headers"]
    co = await new_company()
    line = await persona_line(client, h, co)
    body = (await client.get(f"{API}/lines/{line['ref']}", headers=h)).json()
    steps = [{**s, "max_attempts": 2} if s["key"] == "check" else s for s in body["steps"]]
    r = await client.put(
        f"{API}/lines/{line['ref']}",
        json={"steps": steps},
        headers={**h, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 200, r.text
    router.handlers["persona_test"] = lambda req: None  # the model is down
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "failed"
    assert len(router.of("persona_test")) == 2 and not line_fakes["deliver"]
    router.handlers["persona_test"] = lambda req: {"results": []}  # an answer that fails the check
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "failed"
    assert len(router.of("persona_test")) == 3 and not line_fakes["deliver"]


async def test_the_lowest_score_can_be_the_measure(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    router: Router, su: Any, line_fakes: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await persona_line(client, h, co)
    body = (await client.get(f"{API}/lines/{line['ref']}", headers=h)).json()
    steps = [
        {**s, "settings": {**s["settings"], "aggregate": "min"}} if s["key"] == "check" else s
        for s in body["steps"]
    ]
    r = await client.put(
        f"{API}/lines/{line['ref']}",
        json={"steps": steps},
        headers={**h, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 200, r.text
    router.handlers["persona_test"] = verdicts(100, 60)  # mean 80 passes, the lowest (60) does not
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
    data = steps_of(await get_run(client, h, run["ref"]))["check"]["output"]["data"]
    assert data["score"] == 60 and data["aggregate"] == "min" and data["hold"] == "owner"
