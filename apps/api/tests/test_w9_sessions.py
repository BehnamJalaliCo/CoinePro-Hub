"""W9 (2026-11-07): the owner's order sessions get work done in one place. The owner, in the
session of his Pro-Chart content order, pressed «اجرا» three times on the media director's
automation card and got «نقش کارمند درست نیست.»; «go find why» then made two NEW orders to the
advisor, a 5-step plan, «دریافت شد؛ به مشاور کل سپرده شد» and a pile of «سامانه: خروجی رسید».
The owner: everything goes elsewhere, this is bureaucracy, a session must reach everything.

A. a role as a model writes it never refuses an automation: normalised against the company's real
   roles; every other refusal names the field and what is allowed;
B. no card inside a session makes a new order: `ask` brings the person in and is a child work of
   the same order, `minutes` are child works of the same order, the rest leave one line;
C. the holder reads its own failed cards and fixes them itself;
D. the session's story without the receipts and the duplicated output lines; the brief short;
E. a run carries only what it needs: no capability brief for a watcher, no holding map for a
   consult-only persona's talk.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.agents import runner
from hq_api.domain import automations as AU
from hq_api.domain import capabilities as CAP
from hq_api.domain import hiring
from hq_api.domain import humanize as HZ
from hq_api.domain import order_turns as OT
from hq_api.domain import sessions as SE
from hq_api.hub import Hub
from hq_api.talk import context as C
from hq_api.talk import personas as P
from hq_api.talk import store

from .test_p21_routing_orders import all_tx, auto_hiring, deliver, envelope, report  # noqa: F401
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p22_ops import route_answer, routes
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, run_card

# the owner's sentence, 2026-11-07 (the media director's card: the daily topic at eight)
SENTENCE = (
    "هر روز ساعت ۰۸:۰۰ یک کار «یافتن موضوع روزانه» برای سناریست بساز: سایت pro-chart.com را "
    "بخواند، تکراری نبودن را با ChatGPT چک کند و در بایگانی ثبت کند"
)
REEL_TEXT = "برای {co} یک ریلز آموزشی بساز {w}"


def daily_work(role: Any, **more: Any) -> dict[str, Any]:
    """The rule a model writes for SENTENCE, with the role as it wrote it."""
    args: dict[str, Any] = {"title_fa": "یافتن موضوع روزانه", "brief_fa": "سایت را بخوان", **more}
    if role is not None:
        args["role"] = role
    return {
        "trigger": {"kind": "schedule", "rrule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0"},
        "conditions": [],
        "actions": [{"kind": "work.create", "args": args}],
    }


async def hire(hub: Hub, company: dict[str, Any], role: str) -> str:
    async with await all_tx(hub) as tx:
        out = await hiring.auto_fill(tx, company["id"], role, charters=hub.charters, reason="آزمون")
    return str(out["employee"])


# ============================================================ A. the role, at the root ==
async def test_a_role_as_a_model_writes_it_never_refuses_the_rule(
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    auto_hiring: None,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    writer = await hire(hub, company, "scriptwriter")
    async with await all_tx(hub) as tx:
        roles = await AU.company_roles(tx, hub, co, department="MEDIA")
    assert roles.held["scriptwriter"] == "سناریست" and roles.employees[writer] == "scriptwriter"
    assert roles.managers["MEDIA"] == "media_director" and roles.ceo == "ceo"
    assert (
        roles.titles["سناریست"] == "scriptwriter" and roles.titles["scriptwriter"] == "scriptwriter"
    )
    assert roles.departments["scriptwriter"] == "MEDIA"
    # every form a model writes, to the role the company really has
    for word in ("scriptwriter", "Scriptwriter", f"scriptwriter@{co}", writer, writer.lower(),
                 "سناریست", " SCRIPTWRITER ", "script-writer", f"سناریست@{co}"):  # fmt: skip
        assert AU.normalize_role(word, roles) == ("scriptwriter", None), word
    # a department team's charter is the company's even before a hire (the work's own default
    # then gives it to the department's manager); a charter of a department the company has not
    # (the holding's oversight): the proposer's department manager, and a note
    assert AU.normalize_role("تهیه‌کننده‌ی صدا", roles) == ("voice_producer", None)
    role, note = AU.normalize_role("مسئول ایمنی هوش مصنوعی", roles)
    assert role == "media_director" and note and "مسئول ایمنی هوش مصنوعی" in note
    assert "مدیر رسانه و طراحی" in note
    # an unknown word: the proposer's department manager; without one, the CEO; never a refusal
    role, note = AU.normalize_role("موضوع‌یاب", roles)
    assert role == "media_director" and note and "موضوع‌یاب" in note
    assert AU.normalize_role("content writer", roles)[0] == "media_director"
    bare = roles.model_copy(update={"department": None})
    role, note = AU.normalize_role("موضوع‌یاب", bare)
    assert role == "ceo" and note and "مدیرعامل" in note
    # ⟨2026-11-07⟩ the everyday word for the scriptwriter (prompt 26.2's gap) is the scriptwriter
    assert AU.normalize_role("نویسنده", roles) == ("scriptwriter", None)
    assert AU.normalize_role("ceo", roles) == ("ceo", None)
    assert AU.normalize_role(None, roles) == (None, None)
    assert AU.normalize_role("  ", roles) == (None, None)
    # with no company known: a key is kept, anything else dropped with a note (no refusal)
    assert AU.normalize_role("scriptwriter", None) == ("scriptwriter", None)
    role, note = AU.normalize_role("نویسنده", None)
    assert role is None and note
    # the compiler: the owner's sentence, each bad role form; ONE call carrying the real roles
    expected = {
        "نویسنده": "scriptwriter",
        "موضوع‌یاب": "media_director",
        f"scriptwriter@{co}": "scriptwriter",
        writer: "scriptwriter",
        "Scriptwriter": "scriptwriter",
        "content writer": "media_director",
        "سناریست": "scriptwriter",
    }
    for word, want in expected.items():
        seen = route_answer(monkeypatch, routes(daily_work(word)))
        out = await AU.compile_sentence(hub, SENTENCE, co, department="MEDIA")
        assert out.rule is not None and out.refused_fa == [], (word, out.refused_fa)
        assert out.rule["actions"][0]["args"]["role"] == want, word
        assert len(seen) == 1
        prompt = json.loads(seen[0]["prompt"])
        assert prompt["roles"]["scriptwriter"] == "سناریست" and "media_director" in prompt["roles"]
        assert "roles" in seen[0]["system"] and "leave role out" in seen[0]["system"]
        assert out.preview_fa is not None and "08:00" in out.preview_fa
        assert "«سناریست»" in out.preview_fa or "«مدیر رسانه و طراحی»" in out.preview_fa
        if want != "scriptwriter":  # the preview says who takes it instead
            assert word in out.preview_fa and "داده میشود" in out.preview_fa
        assert HZ.check(out.preview_fa) == [], out.preview_fa
    # anything else wrong: the refusal names the field and what is allowed, in one line
    route_answer(monkeypatch, routes(daily_work("scriptwriter", priority="high")))
    out = await AU.compile_sentence(hub, SENTENCE, co)
    assert out.rule is None and len(out.refused_fa) == 1
    assert "priority" in out.refused_fa[0] and "P0" in out.refused_fa[0]
    assert "\n" not in out.refused_fa[0]
    for args, field in (
        ({"kind": "line.run", "args": {"line": "x"}}, "line"),
        ({"kind": "n8n.run", "args": {"workflow": "Bad Name!"}}, "workflow"),
        ({"kind": "ad.pause", "args": {"platform": "tiktok", "campaign": "1"}}, "platform"),
        ({"kind": "ad.pause", "args": {"platform": "meta_ads", "campaign": "abc"}}, "campaign"),
        ({"kind": "notify.lead", "args": {"title_fa": "x", "company": "ZZZZ"}}, "company"),
    ):
        got, why = AU.validate_rule({**daily_work(None), "actions": [args]}, None, {co})
        assert got is None and len(why) == 1 and field in why[0], (field, why)
    # a stored rule is rendered with the role's title, never its key
    rule, _ = AU.validate_rule(daily_work("scriptwriter"), co, {co}, roles)
    assert rule is not None
    text = AU.preview_fa(rule, co, AU.role_titles(hub.charters))
    assert "«سناریست»" in text and "scriptwriter" not in text


async def test_the_owners_automation_card_runs_in_the_session_with_any_role_word(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    holder = await su.fetchval("SELECT holder FROM talk.conversations WHERE ref = $1", conv)
    assert holder == f"media_director@{co}"
    card = {"kind": "automation", "title_fa": "یافتن موضوع روزانه ساعت ۰۸:۰۰", "body_fa": "",
            "payload": {"sentence_fa": SENTENCE}}  # fmt: skip
    talk["router"].answers = [answer("کارت آماده است.", cards=[card])]
    said = await say(client, owner, conv, "هر روز صبح موضوع پیدا کنید")
    (c,) = said["answer"]["cards"]
    orders_before = await su.fetchval("SELECT count(*) FROM owner.orders")
    # the model wrote a word no charter has: the proposer's department manager takes the work
    seen = route_answer(monkeypatch, routes(daily_work("موضوع‌یاب")))
    r = await run_card(client, owner, c)
    assert r.status_code == 200, r.text
    [aref] = r.json()["made"]
    row = await su.fetchrow(
        """SELECT a.rule, c.code FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
           WHERE a.ref = $1""",
        aref,
    )
    assert row["code"] == co
    assert json.loads(row["rule"])["actions"][0]["args"]["role"] == "media_director"
    assert json.loads(seen[0]["prompt"])["company"] == co
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before
    rep = await report(client, owner, ref)
    assert any("خودکارسازی" in s["what_fa"] and "موضوع‌یاب" in s["what_fa"] for s in rep["steps"])
    # the same card with another field wrong: the plain reason names the field, on the card too
    talk["router"].answers = [answer("کارت آماده است.", cards=[card])]
    said = await say(client, owner, conv, "دوباره")
    (c2,) = said["answer"]["cards"]
    route_answer(monkeypatch, routes(daily_work("نویسنده", priority="high")))
    r = await run_card(client, owner, c2)
    assert r.status_code == 422, r.text
    why = r.json()["message_fa"]
    assert "priority" in why and "P0" in why
    assert (
        await su.fetchval("SELECT reason_fa FROM talk.cards WHERE id = $1::uuid", c2["id"]) == why
    )
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"] == f"خودکارسازی انجام نشد: {why}"


# ================================================= B. nothing leaves the session ==
async def test_no_card_inside_a_session_makes_a_new_order(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    other = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    root_ref = route["work_ref"]
    holder_key = await su.fetchval("SELECT holder FROM talk.conversations WHERE ref = $1", conv)
    orders_before = await su.fetchval("SELECT count(*) FROM owner.orders")
    offered = [
        {"kind": "ask", "title_fa": "از فنی بپرس", "body_fa": "",
         "payload": {"text": "عددهای سرور را بده", "to": "TECH"}},
        {"kind": "ask", "title_fa": "از مدیرعامل شرکت دیگر", "body_fa": "",
         "payload": {"text": "نظر شما درباره‌ی این گزارش؟", "company": other}},
        {"kind": "ask", "title_fa": "برو ببین چرا", "body_fa": "",
         "payload": {"text": "برو ببین چرا این کارت اجرا نشد"}},
    ]  # fmt: skip
    talk["router"].answers = [answer("سه پرسش.", cards=offered)]
    said = await say(client, owner, conv, "از فنی بپرس، از آن شرکت بپرس، و برو ببین چرا")
    assert "IN THIS session" in talk["router"].bodies[0]["system"]
    by_title = {c["title_fa"]: c for c in said["answer"]["cards"]}
    assert len(by_title) == 3 and all(c["kind"] == "ask" for c in by_title.values())
    made: list[str] = []
    for c in offered:  # in the offered order (the page's own is by id)
        r = await run_card(client, owner, by_title[c["title_fa"]])
        assert r.status_code == 200, r.text
        made += r.json()["made"]
    # not one new order; three works of THIS order, each for the person asked
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before
    rows = {
        r["ref"]: dict(r)
        for r in await su.fetch(
            """SELECT w.ref, e.code, c.code AS company, p.ref AS parent, q.ref AS requested_by
               FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
               JOIN core.companies c ON c.id = w.company_id
               LEFT JOIN work.work p ON p.id = w.parent_id
               LEFT JOIN work.work q ON q.id = w.requested_by_work_id
               WHERE w.ref = ANY($1::text[])""",
            made,
        )
    }
    tech, ceo, adv = (rows[m] for m in made)
    assert tech["code"] == f"{co}-TECH-MGR" and tech["parent"] == root_ref
    assert ceo["code"] == f"{other}-CEO" and ceo["requested_by"] == root_ref
    assert ceo["company"] == other and ceo["parent"] is None
    assert adv["requested_by"] == root_ref and adv["company"] not in (co, other)
    # each asked person joined this session, and the lines are here, not in another order
    detail = (await client.get(f"/api/v1/talk/conversations/{conv}", headers=owner)).json()
    assert {f"cto@{co}", f"ceo@{other}", "advisor"} <= set(detail["present"])
    turns = detail["turns_page"]["items"]
    lines = [t for t in turns if t["show_md"] and "جوابش همین‌جا" in t["show_md"]]
    assert len(lines) == 3 and all(t["by"] == holder_key for t in lines)
    rep = await report(client, owner, ref)
    assert sorted(t["work_ref"] for t in rep["tasks"]) == sorted(made)
    assert all(t["who_fa"] for t in rep["tasks"])
    assert rep["steps"][-1]["what_fa"].startswith("پرسش به مشاور کل سپرده شد")
    assert {p["key"] for p in rep["participants"]} >= {f"cto@{co}", f"ceo@{other}", "advisor"}
    for s in rep["steps"]:
        assert HZ.check(s["what_fa"]) == [], s
    # the answer comes back into THIS session as the asked person's own turn
    tech_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", made[0])
    r = await deliver(client, f"{co}-TECH-MGR", tech_id, "عددهای سرور")
    assert r.status_code in (200, 201), r.text
    await report(client, owner, ref)
    detail = (await client.get(f"/api/v1/talk/conversations/{conv}", headers=owner)).json()
    answered = [
        t for t in detail["turns_page"]["items"] if (t["say_fa"] or "").startswith("جواب آمد")
    ]
    assert len(answered) == 1 and answered[0]["by"] == f"cto@{co}"
    assert "عددهای سرور" in answered[0]["show_md"]
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before
    # the minutes: works of this order (a department: its manager; another company: its CEO),
    # the rest on the plan; never an order
    minutes = {"summary_fa": "دو کار.", "decisions_fa": [],
               "tasks": [{"title_fa": "بودجه را بررسی کن", "company": co, "department": "FIN",
                          "due": "2026-12-01"},
                         {"title_fa": "گزارش آن شرکت", "company": other, "department": None,
                          "due": None},
                         {"title_fa": "یک کار بی‌مسئول", "company": None, "department": None,
                          "due": None}]}  # fmt: skip
    talk["router"].answers = [answer("صورت‌جلسه آماده است.", "صورت‌جلسه", minutes=minutes)]
    said = await say(client, owner, conv, "صورت‌جلسه کن")
    m = next(c for c in said["answer"]["cards"] if c["kind"] == "minutes")
    r = await run_card(client, owner, m)
    assert r.status_code == 200, r.text
    got = r.json()["made"]
    assert len(got) == 3
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before
    fin = await su.fetchrow(
        """SELECT e.code, p.ref AS parent FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           JOIN work.work p ON p.id = w.parent_id WHERE w.ref = $1""",
        got[0],
    )
    assert fin["code"] == f"{co}-FIN-MGR" and fin["parent"] == root_ref
    oth = await su.fetchrow(
        """SELECT e.code, q.ref AS requested_by FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           JOIN work.work q ON q.id = w.requested_by_work_id WHERE w.ref = $1""",
        got[1],
    )
    assert oth["code"] == f"{other}-CEO" and oth["requested_by"] == root_ref
    rep = await report(client, owner, ref)
    plan = {t["title_fa"]: t for t in rep["tasks"]}
    assert plan["یک کار بی‌مسئول"]["work_ref"] is None and plan["یک کار بی‌مسئول"]["by"] == "owner"
    assert plan["بودجه را بررسی کن (تا 2026-12-01)"]["work_ref"] == got[0]
    assert rep["steps"][-1]["what_fa"] == "صورت‌جلسه: 3 کار به همین فرمان اضافه شد."
    # outside a session an ask still goes through the dispatcher as an order
    r = await client.post(
        "/api/v1/talk/conversations", headers=owner, json={"persona": "secretary"}
    )
    free = r.json()["ref"]
    ask = {**offered[0], "payload": {"text": f"برای {co} عددهای سرور را گزارش بده", "company": co}}
    talk["router"].answers = [answer("پرسش.", cards=[ask])]
    said = await say(client, owner, free, f"به {co} بگو عددهای سرور را گزارش بده")
    (c,) = said["answer"]["cards"]
    r = await run_card(client, owner, c)
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before + 1


# ===================================================== C. the holder fixes its own failures ==
async def test_the_holder_reads_its_failed_cards_and_is_told_to_fix_them(
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
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    conv = out["talk_ref"]
    [route] = out["routes"]
    card = {"kind": "automation", "title_fa": "یافتن موضوع روزانه", "body_fa": "",
            "payload": {"sentence_fa": SENTENCE}}  # fmt: skip
    talk["router"].answers = [answer("کارت آماده است.", cards=[card])]
    said = await say(client, owner, conv, "هر روز صبح موضوع پیدا کنید")
    (c,) = said["answer"]["cards"]
    route_answer(monkeypatch, routes(daily_work("نویسنده", priority="high")))
    r = await run_card(client, owner, c)
    assert r.status_code == 422
    why = r.json()["message_fa"]
    # the holder's next turn sees the failed card: kind, title, the exact reason, the payload
    talk["router"].answers = [answer("کارت را درست میکنم.", cards=[card])]
    await say(client, owner, conv, "برو ببین چرا")
    body = talk["router"].bodies[-1]
    head = body["messages"][0]["content"]
    assert "## Cards that failed in this session" in head
    failed = json.loads(
        head.split("## Cards that failed in this session")[1].split("\n", 1)[1].split("\n\n")[0]
    )
    assert failed[0]["kind"] == "automation" and failed[0]["reason_fa"] == why
    assert (
        failed[0]["title_fa"] == "یافتن موضوع روزانه"
        and SENTENCE[:40] in failed[0]["payload"]["sentence_fa"]
    )
    assert "fix the card and offer it again" in body["system"]
    assert "never say it is someone else's job" in body["system"]
    # and the holder's run brief carries the same (the order's dialogue of its root work)
    work_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    async with await all_tx(hub) as tx:
        brief = await OT.dialogue(tx, work_id)
    assert brief is not None and brief["failed_cards"][0]["reason_fa"] == why
    # the charters say it too
    common = hub.charters.common
    assert "In the owner's session" in common and "failed_cards" in common
    assert hub.charters.common_version >= 8
    assert "failed_cards" in hub.charters.roles["manager"].body
    assert "failed_cards" in hub.charters.roles["ceo"].body
    # fixed and offered again: it runs (the role as the company has it), the failure is gone
    talk["router"].answers = [answer("کارت را درست کردم.", cards=[card])]
    said = await say(client, owner, conv, "درست کن و دوباره بده")
    (c2,) = said["answer"]["cards"]
    route_answer(monkeypatch, routes(daily_work("نویسنده")))
    r = await run_card(client, owner, c2)
    assert r.status_code == 200, r.text
    async with await all_tx(hub) as tx:
        brief = await OT.dialogue(tx, work_id)
    assert brief is not None and len(brief["failed_cards"]) == 1  # the old failure stays named


# ================================================== D. less noise for the owner ==
def test_the_brief_lines_are_short() -> None:
    assert SE.short("کوتاه") == "کوتاه"
    long = "این یک جمله‌ی بسیار بلند است که باید کوتاه شود " * 5
    cut = SE.short(long)
    assert len(cut) <= SE.BRIEF_CHARS and cut.endswith("…") and " " in cut
    assert SE.short("x" * 200) == "x" * 89 + "…"
    assert SE.short("  a   b  ") == "a b"


async def test_the_story_has_no_receipt_and_no_duplicated_output_lines(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    card = {"kind": "delegate", "title_fa": "بسپار به فنی", "body_fa": "",
            "payload": {"to": "TECH", "text": "عددهای فروش را از سامانه بیرون بکش " * 6}}  # fmt: skip
    talk["router"].answers = [answer("کارت.", cards=[card])]
    said = await say(client, owner, conv, "عددها را به فنی بسپار")
    (c,) = said["answer"]["cards"]
    r = await run_card(client, owner, c)
    assert r.status_code == 200, r.text
    [child_ref] = r.json()["made"]
    child_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", child_ref)
    r = await deliver(client, f"{co}-TECH-MGR", child_id, "عددهای فروش")
    assert r.status_code in (200, 201), r.text
    root_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    await su.execute("UPDATE work.work SET status = 'in_progress' WHERE id = $1", root_id)
    r = await deliver(client, route["to"], root_id, "گزارش فروش هفته")
    assert r.status_code in (200, 201), r.text
    rep = await report(client, owner, ref)
    assert [o["title_fa"] for o in rep["outputs"]] == ["عددهای فروش", "گزارش فروش هفته"]
    texts = [s["what_fa"] for s in rep["steps"]]
    assert not any("خروجی رسید" in t for t in texts), texts
    assert not any(
        s["who_fa"] == "سامانه" and s["what_fa"].endswith("سپرده شد") for s in rep["steps"]
    )
    assert texts[0].startswith("دریافت شد")  # the order's own receipt stays the first line
    assert any(t.startswith("سپردن کار انجام شد") for t in texts)
    for key in ("done_fa", "now_fa", "need_fa"):
        line = rep["brief"][key]
        assert 0 < len(line) <= SE.BRIEF_CHARS and "\n" not in line, (key, line)
        assert HZ.check(line) == [], line
    assert rep["brief"]["done_fa"].startswith("2 خروجی تحویل شد")
    assert rep["session"]["badge"] == "ready"
    # the story's clock moved with the outputs although they wrote no line
    last = await su.fetchval("SELECT last_step_at FROM owner.order_reports WHERE ref = $1", ref)
    assert last is not None
    cards = (await client.get("/api/v1/sessions?state=open&limit=200", headers=owner)).json()
    mine = next(x for x in cards["items"] if x["ref"] == ref)
    assert all(len(mine["brief"][k]) <= SE.BRIEF_CHARS for k in ("done_fa", "now_fa", "need_fa"))


# ===================================================== E. what a run carries ==
def test_a_watcher_or_a_system_run_takes_the_lean_brief() -> None:
    assert runner.caps_scope("work", "employee") == "full"
    assert runner.caps_scope("message", "advisor") == "full"
    assert runner.caps_scope("talk", "manager") == "full"
    assert runner.caps_scope("alert", "employee") == "lean"
    assert runner.caps_scope("schedule", "ceo") == "lean"
    assert runner.caps_scope("work", "system") == "lean"
    assert set(CAP.LEAN_HOW) <= set(CAP.HOW)


async def test_the_budgets_per_run(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    capsys: Any,
) -> None:
    company = await new_company()
    lib = hub.charters
    sre = lib.get("sre")
    assert sre is not None
    convs = {}
    for key in ("overseer", "secretary"):
        r = await client.post("/api/v1/talk/conversations", headers=owner, json={"persona": key})
        assert r.status_code == 201, r.text
        convs[key] = r.json()["ref"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        full = await CAP.brief(tx, company["id"], n8n_up=False, role="sre", tools=sre.tools,
                               scope=sre.scope)  # fmt: skip
        lean = await CAP.brief(tx, company["id"], n8n_up=False, role="sre", tools=sre.tools,
                               scope=sre.scope, lean=True)  # fmt: skip
        no_map = await CAP.brief(tx, None, n8n_up=False, role="overseer", holding_map=False)
        heads = {}
        for key, ref in convs.items():
            p = await P.resolve(tx, hub, key, store_voice=False)
            conv = await store.conversation(tx, ref)
            msgs = await C.messages(tx, hub, p, conv, "سلام", 10**6, {})
            heads[key] = msgs[0]["content"]
    assert set(lean) <= {"how", "technical"} and set(lean["how"]) == set(CAP.LEAN_HOW)
    # (H1, 2026-11-08: a technical role reaches the other companies' servers; none of its own here)
    assert not [s for s in lean["technical"]["servers"] if s.startswith(f"{company['code']} ·")]
    assert "ask" in lean["technical"]
    assert "the_holding" in full and "the_holding" not in no_map and "technical" in no_map
    assert '"the_holding":' not in heads["overseer"] and '"the_holding":' in heads["secretary"]
    assert "What the holding can do" in heads["overseer"]  # the rest of the brief stays
    size = {k: len(json.dumps(v, ensure_ascii=False)) for k, v in
            {"full": full, "lean": lean, "no_map": no_map}.items()}  # fmt: skip
    assert size["lean"] < 1500 < size["full"]
    with capsys.disabled():
        print("\ncapability brief chars:", size)
        print("talk head chars (consult-only overseer / secretary):",
              {k: len(v) for k, v in heads.items()})  # fmt: skip
        print("run context budgets (chars): work", runner.CONTEXT_CHARS + runner.CAPS_CHARS,
              "watcher", runner.CONTEXT_CHARS + size["lean"],
              "meeting", runner.CONTEXT_CHARS)  # fmt: skip


def test_the_everyday_and_the_companys_own_words_find_the_role() -> None:
    """⟨2026-11-07⟩ prompt 26.2's gap: «نویسنده» is the company's title of its scriptwriter, whose
    charter title is «سناریست»; it went to the CEO. It finds the scriptwriter now."""
    roles = AU.Roles(held={"scriptwriter": "نویسنده", "media_director": "مدیر رسانه و طراحی",
                           "ceo": "مدیرعامل"}, ceo="ceo")  # fmt: skip
    assert AU.normalize_role("نویسنده", roles) == ("scriptwriter", None)
    assert AU.normalize_role("سناریست", roles) == ("scriptwriter", None)
    other = AU.Roles(held={"scriptwriter": "سناریست", "ceo": "مدیرعامل"}, ceo="ceo")
    assert AU.normalize_role("نویسنده", other) == ("scriptwriter", None)
