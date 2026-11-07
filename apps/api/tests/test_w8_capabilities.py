"""The owner, 2026-11-06: a media director said «ابزارهای من به ChatGPT، Gemini یا DeepSeek اتصالی
ندارند» and «نمیدونه n8n کجاست». Every run and every talk now reads what the holding gives (live),
every working role may ask the outside players (the policy names the seats, a cover included), and a
CEO or a manager proposes an automation in one sentence that the owner seals."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.agents import runner
from hq_api.domain import capabilities as CAP
from hq_api.domain import order_report as OR
from hq_api.domain import players as PL
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.security import agent_tokens
from hq_api.talk import cards as TC
from hq_api.talk import personas as P

from .conftest import AGENT_KEY, agent_headers, idem
from .test_p12a_substitutes import bench, claim, done, per_day
from .test_p21_routing_orders import all_tx, report
from .test_p21_secretary import no_model, post_order, preview, words  # noqa: F401 - the fixture
from .test_p22_ops import DAILY_REPORT, route_answer, routes
from .test_p23_talk import answer, open_cv, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued, run_card


async def test_the_capability_brief_names_every_helper_and_how(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    line = await su.fetchval(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa, caps,
               steps)
           VALUES ($1, 'instagram_reel', 1, 'instagram', 'ریلز هفتگی', '{}', '[]') RETURNING ref""",
        co["id"],
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(tx, co["id"], n8n_up=False)
    players = {p["player"]: p for p in b["outside_players"]}
    assert {"gpt", "gemini", "deepseek"} <= set(players)
    assert players["gpt"]["name"] == "ChatGPT" and "creative" in players["gpt"]["seats"]
    assert {"outside_model", "cover_image_video", "automation", "hire", "delegate", "owner"} <= set(
        b["how"]
    )
    assert "substitute.call" in b["how"]["cover_image_video"]
    assert "creatives screen" in b["how"]["cover_image_video"]
    assert "a3_action" in b["how"]["cover_image_video"]  # a one-off publish is the owner's
    assert "automation.propose" in b["how"]["automation"]
    assert "an employee asks its manager" in b["how"]["automation"]
    assert "kind: proposal" in b["how"]["automation"]  # a brand-new n8n workflow
    assert "line.run" in b["how"]["production_line"]
    assert b["automations"]["n8n"] == "not set up"
    assert set(b["your_company"]) >= {
        "connections",
        "links",
        "working_groups",
        "production_lines",
        "production_lines_on",
    }
    assert b["your_company"]["production_lines"] == [
        {
            "ref": line,
            "title_fa": "ریلز هفتگی",
            "platform": "instagram",
            "state": "draft",
            "mode": "draft",
        }
    ]
    assert b["your_company"]["production_lines_on"] == 0


async def test_the_holding_map_keeps_to_its_room_however_many_companies(
    hub: Hub, su: Any, new_company: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner rule 9: the number of companies is data; the map never grows a talk turn past its
    room (2026-11-07: with every test company in it, the talk turns ran out of tokens)."""
    co = await new_company()
    for _ in range(3):
        await new_company()
    active = await su.fetchval("SELECT count(*) FROM core.companies WHERE status = 'active'")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(tx, co["id"], n8n_up=False)
    full = [c for c in b["the_holding"] if "departments" in c]
    assert full[0]["kind"] == "holding" and full[1]["code"] == co["code"]  # the reader's first
    assert sum(len(json.dumps(c, ensure_ascii=False)) for c in full) <= CAP.MAP_CHARS
    more = (b.get("the_holding_more") or {}).get("companies", 0)
    assert len(b["the_holding"]) + more == active
    keys = list(b)
    assert keys.index("your_company") < keys.index("the_holding") == len(keys) - 1
    assert len(json.dumps(b, ensure_ascii=False, default=str)) <= runner.CAPS_CHARS
    # a small room: the rest by code and name, then only how many more
    monkeypatch.setattr(CAP, "MAP_CHARS", 1)
    monkeypatch.setattr(CAP, "MAP_NAMES_CHARS", 120)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(tx, co["id"], n8n_up=False)
    assert all(set(c) == {"code", "name_fa"} for c in b["the_holding"])
    assert sum(len(json.dumps(c, ensure_ascii=False)) for c in b["the_holding"]) <= 120
    assert b["the_holding_more"]["companies"] == active - len(b["the_holding"]) > 0
    assert "linked.read" in b["the_holding_more"]["read"]
    assert "the_holding_more" in b["how"]["other_companies"]


async def test_a_manager_proposes_an_automation_and_the_owner_is_told(
    client: httpx.AsyncClient,
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = (await new_company())["code"]
    route_answer(monkeypatch, routes(DAILY_REPORT))
    r = await client.post(
        "/internal/v1/automations/propose",
        headers={**await agent_headers(f"{co}-CEO"), **idem()},
        json={"sentence_fa": "هر روز ساعت ۹ گزارش صبح را برایم بفرست"},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["state"] == "proposed" and a["company"] == co
    n = await su.fetchrow(
        """SELECT owner_visible, level FROM notify.notifications
           WHERE link_kind = 'automation' AND link_ref = $1""",
        a["ref"],
    )
    assert n is not None and n["owner_visible"] and n["level"] == "decision"
    # nothing runs before the owner's seal
    assert (
        await su.fetchval("SELECT state FROM growth.automations WHERE ref = $1", a["ref"])
        == "proposed"
    )


# ================================================== talk: a player comes as a participant ==
async def test_talk_never_reads_substitute_call(hub: Hub) -> None:
    """A0 and in every charter, but in talk it would answer `queued` and land as a work item."""
    lib = hub.charters
    assert "substitute.call" in lib.get("ceo").tools
    reads = P.read_tools(lib, "ceo", None)
    assert "substitute.call" not in reads and "company.state" in reads


async def test_a_player_comes_only_into_a_session() -> None:
    with pytest.raises(ApiError) as e:
        await TC._invite_player(None, {"ref": "CV-1", "order_ref": None}, {"player": "gpt"})  # type: ignore[arg-type]
    assert e.value.status == 422 and e.value.message_fa == TC.NO_SESSION_FA
    with pytest.raises(ApiError) as e:
        await TC._invite_player(None, {"ref": "CV-1", "order_ref": "F-1"}, {"player": "claude"})  # type: ignore[arg-type]
    assert e.value.status == 422 and "ChatGPT" in str(e.value.message_fa)


async def test_a_session_brings_a_player_in_by_a_card_and_a_manager_automates_its_company(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    offered = [
        {"kind": "invite", "title_fa": "ChatGPT بیاید", "body_fa": "", "payload": {"player": "gpt"}},
        {"kind": "automation", "title_fa": "گزارش هر روز", "body_fa": "",
         "payload": {"sentence_fa": "هر روز ساعت ۹ گزارش صبح را برایم بفرست"}},
    ]  # fmt: skip
    talk["router"].answers = [answer("دو کارت آماده است.", cards=offered)]
    said = await say(client, owner, conv, "ChatGPT را بیاور و گزارش روزانه را خودکار کن")
    got = {c["kind"]: c for c in said["answer"]["cards"]}
    assert set(got) == {"invite", "automation"}
    system = talk["router"].bodies[0]["system"]
    assert '"player": "gpt"' in system and "no connection" in system
    assert "substitute.call" not in system.split("# Your read tools")[1].split("# You, here")[0]
    # signed out: refused in plain words; the card may run again
    r = await run_card(client, owner, got["invite"])
    assert r.status_code == 409 and "ChatGPT" in r.json()["message_fa"], r.text
    async with bench(su, hub, cli=("gpt",)):
        for seat in PL.TEXT_SEATS:
            await per_day(su, "gpt", seat, 5)
        r = await run_card(client, owner, got["invite"])
        assert r.status_code == 200 and r.json()["made"] == ["player:gpt"], r.text
    present = await su.fetchval("SELECT present FROM talk.conversations WHERE ref = $1", conv)
    assert "player:gpt" in present
    rep = await report(client, owner, ref)
    assert any(s["what_fa"] == "ChatGPT به جلسه آمد" for s in rep["steps"])
    # a manager's automation card is its own company's when the payload names none
    route_answer(monkeypatch, routes(DAILY_REPORT))
    r = await run_card(client, owner, got["automation"])
    assert r.status_code == 200, r.text
    [aref] = r.json()["made"]
    assert (
        await su.fetchval(
            """SELECT c.code FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
               WHERE a.ref = $1""",
            aref,
        )
        == co
    )


async def test_a_late_answer_belongs_to_the_callers_order_and_its_session_hears_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    holder, root = route["to"], route["work_ref"]
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               started_at, token_expires_at)
           SELECT e.company_id, e.id, w.id, 'work', 'test', 'running', now(), now() + interval '1 hour'
           FROM core.employees e, work.work w WHERE e.code = $1 AND w.ref = $2 RETURNING id""",
        holder,
        root,
    )
    caller = {"Authorization": f"Bearer {agent_tokens.mint(AGENT_KEY, holder, str(rid))}"}
    call = None
    try:
        async with bench(su, hub, cli=("gpt",)):
            await per_day(su, "gpt", "assistant_errand", 5)
            r = await client.post(
                "/internal/v1/substitutes/call", headers=caller,
                json={"seat": "assistant_errand", "input_md": "یک خلاصه‌ی کوتاه از گزارش فروش بنویس."},
            )  # fmt: skip
            assert r.status_code == 200 and r.json()["state"] == "queued", r.text
            call = r.json()["call"]
            job = (await claim(client))["job"]
            assert job is not None and job["id"] == call
            ok = await done(client, call, ok=True, text_md="خلاصه: فروش این هفته بهتر شد.")
            assert ok.status_code == 200 and ok.json()["state"] == "done", ok.text
        reply = await su.fetchrow(
            """SELECT w.id, w.ref, w.brief, r.ref AS asked_by FROM substitutes.calls c
               JOIN work.work w ON w.id = c.reply_work_id
               JOIN work.work r ON r.id = w.requested_by_work_id WHERE c.id = $1::uuid""",
            call,
        )
        assert reply is not None and reply["asked_by"] == root and root in reply["brief"]
        async with await all_tx(hub) as tx:
            assert await OR.order_of_work(tx, reply["id"]) == ref
        line = await su.fetchval(
            """SELECT t.show_md FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
               WHERE c.ref = $1 ORDER BY t.n DESC LIMIT 1""",
            conv,
        )
        assert "رسید" in line and "ChatGPT" in line and "فروش این هفته بهتر شد" in line, line
        await refuse_queued(su, reply["ref"])
    finally:
        await su.execute(
            "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE id = $1", rid
        )


async def test_the_secretarys_group_card_works_outside_a_session_or_refuses_plainly(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    for group, status in (("content", 200), ("no_such_group", 422)):
        cv = await open_cv(client, owner)
        card = {"kind": "group", "title_fa": "کارگروه", "body_fa": "",
                "payload": {"company": co, "group": group}}  # fmt: skip
        talk["router"].answers = [answer("کارتش را گذاشتم.", cards=[card])]
        out = await say(client, owner, cv["ref"], f"{co} را در کارگروه {group} راه بنداز")
        (c,) = out["answer"]["cards"]
        r = await run_card(client, owner, c)
        assert r.status_code == status, r.text
        if status == 422:
            assert r.json()["message_fa"] == "این کارگروه را نمیشناسم."
    assert (
        await su.fetchval(
            """SELECT m.state FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
               WHERE g.key = 'content' AND m.company_id = $1""",
            company["id"],
        )
        == "on"
    )


# ======================================================= orders: an automation is the CEO's ==
async def test_an_automation_order_goes_to_the_ceo_never_by_a_stray_word(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    # «ریلز» and «اینستاگرام» would make it the media director's: an automation is the CEO's
    r = await preview(client, owner, f"برای {co} اتوماسیون انتشار ریلز اینستاگرام بساز {words()}")
    assert r["companies"] == [co] and r["department"] is None, r
    assert r["output_kind"] == "other" and r["kind"] == "work"
    r = await preview(client, owner, f"برای {co} با n8n خودکارسازی پست تلگرام را راه بینداز")
    assert r["companies"] == [co] and r["department"] is None, r
    # the holding has no CEO: AI operations
    r = await preview(client, owner, f"برای هلدینگ یک خودکارسازی گزارش روزانه بساز {words()}")
    assert r["companies"][0] == "HQ" and r["department"] == "AIOPS", r
    # a manager named outright still receives it
    r = await preview(client, owner, f"مدیر رسانه {co} یک اتوماسیون برای استوری بسازد {words()}")
    assert r["department"] == "MEDIA", r
    # a production that runs automated («اتوماسیون شده») stays its output's
    r = await preview(client, owner, f"برای {co} سه ریلز بساز که اتوماسیون شده منتشر بشه {words()}")
    assert (r["department"], r["output_kind"], r["count"]) == ("MEDIA", "reel", 3), r
    assert no_model == []  # the rules alone


async def test_the_brief_maps_the_whole_holding_and_ig_hubs_accounts(
    hub: Hub, su: Any, new_company: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner, 2026-11-06: a media director did not know what company IG is or which Instagram
    accounts IG-Hub holds. Every run's brief now names every active company and its channels."""
    import json

    a, b = await new_company(), await new_company()
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set)
           VALUES ($1, 'instagram', 'اینستاگرام', $2::jsonb, false)""",
        b["id"],
        json.dumps({"via": "ig_hub", "accounts": ["@pro.chart"],
                    "server": {"company": "IG", "name": "IG-Hub"}}),
    )  # fmt: skip
    # every company in full: a room for all of them (the room itself is the next test's)
    monkeypatch.setattr(CAP, "MAP_CHARS", 10**8)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        brief = await CAP.brief(tx, a["id"], n8n_up=True)
    by_code = {c["code"]: c for c in brief["the_holding"]}
    assert {a["code"], b["code"]} <= set(by_code)
    ig = next(c for c in by_code[b["code"]]["channels"] if c["kind"] == "instagram")
    assert ig["accounts"] == ["pro.chart"] and ig["via"] == {"server": "IG-Hub", "company": "IG"}
    assert brief["voice"]["aistudio"] in {"signed_in", "signed_out", "unknown"}
    assert "linked.read" in brief["how"]["other_companies"]
    assert "speech.make" in brief["how"]["voice"]


def test_the_brief_is_never_cut_by_a_long_context() -> None:
    """Appended last, the brief was the first thing trimmed from a long run context."""
    import inspect

    from hq_api.agents import runner

    src = inspect.getsource(runner)
    assert "caps_block" in src and 'text + "\\n\\n" + caps_block' in src
    assert runner.CAPS_CHARS >= 8_000
