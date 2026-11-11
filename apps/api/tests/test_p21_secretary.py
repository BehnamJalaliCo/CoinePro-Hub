"""Prompt 21 part 2 (contract §29.4, §29.8): the holding's secretary.

The clip order of prompt 20 (docs/ops/reports/PROMPT_20.md §1.1) previews to
the media department of the company that makes it (never AI operations),
with its collaborator, reels, single mode and the table's budget; an edited
preview is followed exactly and remembered; several companies make one root
and a requested child each; the council only on «شورا» or an outside
question; an inside question goes to the company's own Claude on its server
as a capped job. No model is reached (route_order is refused)."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import dispatch as D
from hq_api.domain import humanize
from hq_api.domain import orders as O
from hq_api.domain import players as PL
from hq_api.hub import Hub

from .conftest import idem
from .test_p17_runners import pair, poll, take

CLIP = (
    "یه مدلی رو می‌خوام پیاده‌سازی بکنیم که یه ویدیوسازی رو راه اندازی بکنیم توی شرکت آی جی که "
    "ویدیوها بر حسب این ساخته میشن که برای کانال سیگنال تریدیار شرکت تریدیار که میخوام همه "
    "مواردش اتوماسیون شده و ایجنتیک اجرا بشه ، داخل سرور IG ساخته بشه ویدیو هم باید صدا گذاری "
    "بشه و توسط opus 5.5 ادیت و موشنگرافی میشه کارگردانی باید بشه و هیچ سناریویی هر روز تکراری "
    "نباشه بهترین خروجی رو باید داشته باشیم و مخاطب رو تا آخرین لحظه ویدیو میخ کوب کنیم و توسط "
    "ig-hub دایرکت هوشمند براش ست میشه و پست میشه چون داخل اون شرکت همه api های مجاز "
    "اینستاگرام هست"
)


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    async def refuse(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> None:
        calls.append(req)

    monkeypatch.setattr(workflows_client, "route_order", refuse)
    return calls


async def ig(su: Any, new_company: Callable[..., Any]) -> str:
    """IG-Hub as a company (the owner's data on the hub; the test database
    outlives a run, so it is made once)."""
    if not await su.fetchval("SELECT 1 FROM core.companies WHERE code = 'IG'"):
        await new_company(code="IG")
    return "IG"


async def preview(client: httpx.AsyncClient, owner: dict[str, str], text: str) -> dict[str, Any]:
    r = await client.post("/api/v1/orders/preview", headers=owner, json={"text": text})
    assert r.status_code == 200, r.text
    route = dict(r.json())
    assert humanize.check(route["preview_fa"]) == [], route["preview_fa"]
    assert humanize.check(route["why_fa"]) == [], route["why_fa"]
    return route


async def post_order(
    client: httpx.AsyncClient, owner: dict[str, str], text: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": text, "source": "voice", **extra},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def work_of(su: Any, ref: str) -> Any:
    return await su.fetchrow(
        """SELECT w.*, e.code AS assignee, d.code AS dept, c.code AS company FROM work.work w
           JOIN core.employees e ON e.id = w.assignee_id JOIN core.companies c ON c.id = w.company_id
           LEFT JOIN core.departments d ON d.id = w.department_id WHERE w.ref = $1""",
        ref,
    )


def words() -> str:
    """Words no earlier run used: an order the memory has not seen."""
    return " ".join(f"واژه{secrets.token_hex(3)}" for _ in range(4))


# ------------------------------------------------------------ the rules --
def test_output_kinds_counts_and_budgets_are_data() -> None:
    norm = O.normalise
    assert D.output_of(norm("۳ ریلز برای تریدیار بساز"))[:2] == ("reel", 3)
    assert D.output_of(norm("سه تا پست آموزشی"))[:2] == ("post", 3)
    assert D.output_of(norm("یک استوری"))[:2] == ("story", 1)
    assert D.output_of(norm("گزارش فروش"))[:2] == ("report", None)
    assert D.output_of(norm("کاری بکن"))[:2] == ("other", None)
    # a year or a figure over the cap is no count (Route.count would refuse it: 500)
    assert D.output_of(norm("سال ۱۴۰۵ برنامه بازاریابی بنویس"))[:2] == ("plan", None)
    assert D.output_of(norm("برای ۱۲۰ پست کپشن بنویس"))[:2] == ("post", None)
    assert D.output_of(norm("۱۰۰ پست بنویس"))[:2] == ("post", 100)
    assert D.budget_of("reel", None) == 400_000 and D.budget_of("reel", 3) == 600_000
    assert D.budget_of("reel", 50) == 1_200_000  # never above the kind's max
    assert D.question_scope(norm("رقیب ما در بازار چه کرد")) == "outside"
    assert D.question_scope(norm("فروش و بازار")) == "inside"  # real figures win
    assert D.similarity("a b c d", "a b c e") == 0.6


async def test_the_clip_order_goes_to_the_media_director_with_its_collaborator(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],
    new_company: Callable[..., Any],
) -> None:
    await ig(su, new_company)
    r = await preview(client, owner, CLIP)
    assert r["companies"][0] == "IG" and r["department"] == "MEDIA"
    assert "TY" in r["collaborators"] and r["kind"] == "work"
    assert (r["output_kind"], r["mode"], r["player"]) == ("reel", "single", "auto")
    assert r["budget_tokens"] == D.budget_of("reel", r["count"])
    assert r["confidence"] >= 0.8 and "ریلز" in r["preview_fa"] and r["preview_fa"].startswith("→")
    assert no_model == []  # the rules alone
    out = await post_order(client, owner, CLIP)
    assert out["routed_by"] == "rules" and out["route"]["department"] == "MEDIA"
    root, *children = out["routes"]
    assert (root["company"], root["to"]) == ("IG", "IG-MEDIA-MGR")  # never IG-AIOPS-MGR
    w = await work_of(su, root["work_ref"])
    assert w["dept"] == "MEDIA" and w["mode"] == "single" and w["player"] == "auto"
    assert w["budget_tokens"] is None  # ⟨2026-11-08⟩ an owner's order has no token cap
    assert w["parent_id"] is None and w["created_by_kind"] == "owner"
    # one requested child work per collaborator, in its own company
    ty = next(c for c in children if c["company"] == "TY")
    child = await work_of(su, ty["work_ref"])
    assert child["company"] == "TY" and child["requested_by_work_id"] == w["id"]
    assert child["parent_id"] is None and child["mode"] == "single"
    stored = await su.fetchval("SELECT route FROM owner.orders WHERE ref = $1", out["ref"])
    assert json.loads(stored)["companies"][0] == "IG"
    # no council on a production order (finding 4 of prompt 20)
    assert await su.fetchval("SELECT count(*) FROM work.councils WHERE work_id = $1", w["id"]) == 0


async def test_an_edited_preview_is_followed_exactly_and_remembered(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    text = f"برای {co} دو پست آموزشی بساز {words()}"
    r = await preview(client, owner, text)
    assert (r["companies"], r["department"], r["output_kind"], r["count"]) == (
        [co],
        "MEDIA",
        "post",
        2,
    )
    edited = {**r, "department": "GROWTH", "mode": "single", "budget_tokens": 90_000}
    out = await post_order(client, owner, text, route=edited)
    [route] = out["routes"]
    assert route["to"] == f"{co}-GROWTH-MGR"
    w = await work_of(su, route["work_ref"])
    assert w["dept"] == "GROWTH" and w["budget_tokens"] is None  # the estimate is no cap
    mem = await su.fetchrow(
        "SELECT kind, data, order_ref FROM owner.dispatch_memory WHERE order_ref = $1", out["ref"]
    )
    data = json.loads(mem["data"])
    assert mem["kind"] == "correction" and data["from"] == {"department": "MEDIA"}
    assert data["to"] == {"department": "GROWTH"}
    # the secretary reads its memory first: the same order now goes the owner's way
    again = await preview(client, owner, text)
    assert again["department"] == "GROWTH" and again["confidence"] >= 0.95
    assert "اصلاح قبلی" in again["why_fa"]
    # a route sent back unchanged is no correction
    before = await su.fetchval("SELECT count(*) FROM owner.dispatch_memory")
    await post_order(client, owner, text, route=again)
    assert await su.fetchval("SELECT count(*) FROM owner.dispatch_memory") == before
    # a route naming what does not exist is refused
    bad = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": text, "route": {**r, "department": "NOPE"}},
    )
    assert bad.status_code == 422


async def test_the_memory_takes_the_homes_no_reasons(su: Any, hub: Hub) -> None:
    text = f"کمپین تبلیغ تلویزیونی {words()}"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await D.remember(tx, "no", text, {"suggestion": "S-1", "reason_fa": "گران است"})
        hits = await D.recall(tx, "no", text)
    data = (
        hits[0]["data"]
        if hits and isinstance(hits[0]["data"], dict)
        else json.loads(hits[0]["data"])
    )
    assert data["reason_fa"] == "گران است"


async def test_the_council_only_on_the_owners_word_or_an_outside_question(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    assert (await preview(client, owner, f"برای {co} یک پست بساز {words()}"))["mode"] == "single"
    said = await preview(client, owner, f"برای {co} یک پست بساز با شورا {words()}")
    assert said["mode"] == "council"
    outside = f"برای {co} {words()} چه ایده‌ای برای تبلیغات در بازار تازه داری؟"
    r = await preview(client, owner, outside)
    assert (r["kind"], r["mode"], r["output_kind"]) == ("question", "council", "plan")
    out = await post_order(client, owner, outside)
    [route] = out["routes"]
    assert route["to"] == f"{co}-CEO" and route["kind"] == "work"
    k = await su.fetchrow(
        """SELECT k.round, k.roles, k.fact_pack_ref FROM work.councils k JOIN work.work w ON w.id = k.work_id
           WHERE w.ref = $1""",
        route["work_ref"],
    )
    assert k["round"] == 1 and json.loads(k["roles"])["claude"] == "captain"
    assert k["fact_pack_ref"].startswith("FP-")
    # an outside-looking question with nobody named still goes to the advisor
    plain = await preview(client, owner, f"نظرت درباره‌ی این هفته چیست؟ {words()}")
    assert plain["kind"] == "question" and plain["mode"] == "single"


async def test_an_inside_question_goes_to_the_companys_own_claude_as_a_capped_job(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = await new_company()
    question = f"چرا فروش {co['code']} این هفته کم شد؟"
    # no server online: the advisor answers, as before
    assert (await preview(client, owner, question))["kind"] == "question"
    rn = await pair(client, hub, owner_session, co, name=f"web-{secrets.token_hex(2)}")
    await poll(client, rn)  # the runner is online
    r = await preview(client, owner, question)
    assert (r["kind"], r["mode"], r["output_kind"]) == ("server", "single", "answer")
    out = await post_order(client, owner, question)
    [route] = out["routes"]
    assert route["to"] == f"{co['code']}-TECH-MGR" and route["note_fa"]
    job = await take(client, rn)
    assert job["kind"] == "claude" and job["actor"]["code"] == "secretary"
    args = job["args"]
    assert args["token_cap"] >= D.SERVER_MIN_TOKENS and args["max_turns"] == D.SERVER_TURNS
    assert "Read" in args["allowed_tools"] and "فروش" in args["brief"]
    # the CTO's own run makes no model call while the server answers
    w = await work_of(su, route["work_ref"])
    run = {"work_id": w["id"]}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await PL.player_turn(tx, hub, run) == "server_answer"
    answer = "فروش این هفته ۱۲٪ کم شد چون پرداخت درگاه دو روز قطع بود."
    res = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        headers=rn["h"],
        json={"exit_code": 0, "data": {"result_fa": answer}},
    )
    assert res.status_code == 200, res.text
    dl = await su.fetchrow(
        "SELECT body, produced_with FROM cartable.deliverables WHERE work_id = $1", w["id"]
    )
    assert dl["body"] == answer
    pw = json.loads(dl["produced_with"])
    assert pw["via"] == "server" and pw["server_job"] == job["id"]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) == "delivered"


async def test_a_question_without_a_company_and_no_route_goes_to_the_advisor(
    client: httpx.AsyncClient, owner: dict[str, str], no_model: list[Any]
) -> None:
    out = await post_order(client, owner, f"یک کاری برای بهتر شدن اوضاع انجام بده {words()}")
    assert out["routed_by"] == "advisor" and out["routes"][0]["kind"] == "question"
    assert len(no_model) == 1  # the model was asked once (and said nothing)
    assert out["route"]["kind"] == "question" and humanize.check(out["route"]["preview_fa"]) == []


def test_a_name_inside_a_longer_name_is_not_another_company() -> None:
    d = {
        "companies": {
            "HQ": {"name_fa": "هلدینگ", "name_en": "Holding", "holding": True},
            "IG": {"name_fa": "آی جی هاب", "name_en": "IG-Hub", "holding": False},
        }
    }
    assert D.companies_in_order(O.normalise("در آی جی هاب یک ریلز بساز"), d) == ["IG"]
