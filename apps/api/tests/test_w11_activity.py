"""W11 (contract §41, 2026-11-08): the session shows its work live and never stalls. The owner, on
his Pro-Chart reels session (F-0011): a 9-step brief, a «test reel» order, two hires approved — then
nothing ran, the session still read «در جریان», no plan task came from his steps.

A. `GET /orders/{ref}/activity`: who works now, the last lines in plain Persian (never a ref, a tool
   key or a code), idle/waiting/stuck; `session.activity` streamed on a run's step;
B. the owner's numbered list (Persian or Latin digits, items over several lines) is the plan, once;
C. the holder is woken when someone joins by a hire, when a hire decision is applied, when a child
   work is delivered; the sweep wakes an idle holder once and marks a still-idle session `stuck`
   with ONE notification naming the cause; `moving` only with a live run;
D. `POST /orders/{ref}/nudge`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import session_activity as SA
from hq_api.domain import sessions as SE
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_routing_orders import all_tx, deliver, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued, run_card

NINE_STEPS = """کارگروه ریلز روزانه را این‌طور راه بینداز:
۱- موضوع روز را با ChatGPT پیدا کند
۲- متن گویندگی را بنویسد
۳- صدا را از Google AI Studio بگیرد
و کیفیتش را چک کند
4. کارگردانی ثانیه‌به‌ثانیه
5) رفرنس حرکت از Pinterest
6: ویدیو را با Opus بسازد و کپشن سئو بنویسد
۷ - کاور را از روی پک برند بسازد
۸. به اینستاگرام تحویل دهد
۹- بعد از انتشار تحلیل کند"""


def plain(*texts: Any) -> None:
    for t in texts:
        if isinstance(t, str) and t:
            assert HZ.check(t) == [], (t, HZ.check(t))


async def fake_run(
    su: Any,
    company: dict[str, Any],
    code: str,
    work_id: Any,
    *,
    state: str = "done",
    error: str | None = None,
    reason: str = "test",
    minutes_ago: int = 5,
    steps: list[tuple[str, list[dict[str, Any]]]] = (),  # type: ignore[assignment]
) -> Any:
    emp = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", code)
    final = state in ("done", "failed", "refused")
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state, error_code,
               queued_at, started_at, finished_at, steps)
           VALUES ($1, $2, $3, 'work', $4, $5, $6, now() - make_interval(mins => $7),
                   CASE WHEN $5 <> 'queued' THEN now() - make_interval(mins => $7) END,
                   CASE WHEN $8 THEN now() - make_interval(mins => $7) + interval '2 minutes' END, $9)
           RETURNING id""",
        company["id"], emp, work_id, reason, state, error, minutes_ago, final, len(steps),
    )  # fmt: skip
    for n, (summary, actions) in enumerate(steps, 1):
        await su.execute(
            """INSERT INTO agents.steps (run_id, company_id, n, at, summary_fa, actions)
               VALUES ($1, $2, $3, now() - make_interval(mins => $4) + make_interval(secs => $3 * 10),
                       $5, $6::jsonb)""",
            rid, company["id"], n, minutes_ago, summary, json.dumps(actions, ensure_ascii=False),
        )  # fmt: skip
    return rid


async def runs_with_reason(su: Any, work_ref: str, prefix: str) -> list[Any]:
    return [
        dict(r)
        for r in await su.fetch(
            """SELECT r.id, r.state, r.reason FROM agents.runs r JOIN work.work w ON w.id = r.work_id
               WHERE w.ref = $1 AND r.reason LIKE $2 ORDER BY r.queued_at""",
            work_ref,
            prefix + "%",
        )
    ]


async def stream(su: Any, ref: str, type_: str) -> list[dict[str, Any]]:
    rows = await su.fetch(
        """SELECT payload FROM core.outbox WHERE subject LIKE $1 AND payload->>'ref' = $2
           AND created_at >= (SELECT max(created_at) FROM owner.orders WHERE ref = $2) ORDER BY id""",
        f"%.{type_}",
        ref,
    )
    return [json.loads(r["payload"]) for r in rows]


# ====================================================================== the words ==
def test_a_step_is_said_in_plain_persian_or_by_its_tools() -> None:
    # the step's own summary when it is plain
    assert (
        SA.step_text("سایت را خواندم و سه موضوع پیدا کردم", [])
        == "سایت را خواندم و سه موضوع پیدا کردم"
    )
    # a summary with a ref, a tool key or English falls back to the tools, in words
    acts = [
        {"tool": "web.read", "class": "A0", "outcome": "ok", "hint": "pro-chart"},
        {"tool": "substitute.call", "class": "A0", "outcome": "ok", "hint": "ChatGPT"},
        {"tool": "activity.set", "class": "A0", "outcome": "ok"},
    ]
    text = SA.step_text("Called web.read on W-000153 then substitute.call", acts)
    assert text == "سایت pro-chart را خواند؛ از ChatGPT پرسید", text
    plain(text)
    assert SA.step_text("", [{"tool": "speech.make", "outcome": "ok"}]) == "صدا ساخت"
    assert SA.step_text(None, [{"tool": "deliver", "outcome": "ok"}]) == "خروجی تحویل داد"
    assert SA.step_text("", [{"tool": "order.ask", "outcome": "ok"}]) == "از شما پرسید"
    assert SA.step_text("", [{"tool": "hire.decide", "outcome": "error", "code": "x"}]) == (
        "درباره‌ی استخدام تصمیم گرفت (نشد)"
    )
    # an employee code as a hint is resolved to a title, never shown as a code
    text = SA.step_text("", [{"tool": "work.delegate", "outcome": "ok", "hint": "PC-MEDIA-01"}],
                        {"PC-MEDIA-01": "سناریست پروچارت"})  # fmt: skip
    assert text == "کار را به سناریست پروچارت سپرد"
    assert SA.step_text(
        "", [{"tool": "work.delegate", "outcome": "ok", "hint": "PC-MEDIA-01"}]
    ) == ("کار را به یکی از همکاران سپرد")
    assert SA.step_text("", [{"tool": "something.odd", "outcome": "ok"}]) == "کار کرد"
    assert SA.step_text("", []) == "کار کرد"
    # the hints the runner keeps: a site's name, a player's name; never a path or a text
    assert SA.hint_of("web.read", {"url": "https://www.pro-chart.com/blog/x?y=1"}) == "pro-chart"
    assert SA.hint_of("substitute.call", {"player": "gpt", "input_md": "secret text"}) == "ChatGPT"
    assert SA.hint_of("substitute.call", {"seat": "creative"}) is None
    assert SA.hint_of("linked.read", {"company": "IG"}) == "IG"
    assert SA.hint_of("files.read", {"file_id": "abc"}) is None
    # how a run ended
    assert SA.end_text("done", None) == SA.DONE_FA
    assert SA.end_text("done", "work_closed") is None
    assert "سقف" in (SA.end_text("done", "limit_reached", True) or "")
    assert (SA.end_text("refused", "daily_cap") or "").startswith("کار متوقف شد: سقف توکن امروز")
    assert SA.end_text("failed", "weird_code") == "کار متوقف شد: جواب آماده نشد."


def test_the_owners_numbered_list_is_read_in_any_digits_and_over_lines() -> None:
    items = OT.numbered_items(NINE_STEPS)
    assert len(items) == 9, items
    assert items[0] == "موضوع روز را با ChatGPT پیدا کند"
    assert items[2] == "صدا را از Google AI Studio بگیرد و کیفیتش را چک کند"  # two lines, one item
    assert items[3] == "کارگردانی ثانیه‌به‌ثانیه" and items[5].startswith("ویدیو را با Opus")
    assert items[8] == "بعد از انتشار تحلیل کند"
    # one numbered line alone is not a list; a sentence with a number in it is not an item
    assert OT.numbered_items("1. فقط یک کار") == []
    assert OT.numbered_items("ساعت 8. بعد از آن 9 نفر میآیند") == []
    assert OT.numbered_items("") == []
    # a list in one line, its numbers running from 1
    assert OT.numbered_items("کارها: 1- موضوع 2- متن 3- صدا") == ["موضوع", "متن", "صدا"]
    assert OT.numbered_items("۱) اول ۲) دوم") == ["اول", "دوم"]
    assert OT.numbered_items("3- سوم 4- چهارم") == []  # not from 1: a sentence, not a list


# ======================================================== A. the activity, live ==
async def test_the_activity_shows_who_works_and_the_last_lines_in_plain_persian(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    # the run the work's creation queued: somebody is in the queue → `moving`, a worker listed
    r = await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)
    assert r.status_code == 200, r.text
    act = r.json()
    assert len(act["working"]) == 1 and act["working"][0]["doing_fa"] == "در صف اجرا"
    assert act["working"][0]["step"] == 0 and act["idle_since"] is None
    plain(act["working"][0]["who_fa"], act["working"][0]["work_title_fa"])
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "moving"
    # a run that worked: its steps, in the owner's words (the summary plain, or the tools)
    await refuse_queued(su, work_ref)
    await fake_run(
        su, company, holder, wid, minutes_ago=8,
        steps=[
            ("سایت را خواندم و سه موضوع پیدا کردم", [{"tool": "web.read", "outcome": "ok", "hint": "pro-chart"}]),
            ("Asked substitute.call about W-000153 topics", [{"tool": "substitute.call", "outcome": "ok", "hint": "ChatGPT"}]),
            ("", [{"tool": "order.progress", "outcome": "ok"}, {"tool": "deliver", "outcome": "ok", "ref": "O-000001"}]),
        ],
    )  # fmt: skip
    await fake_run(su, company, holder, wid, state="refused", error="daily_cap", minutes_ago=3)
    r = await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)
    act = r.json()
    texts = [ln["text_fa"] for ln in act["last"]]
    assert texts[0].startswith("شروع کرد:"), texts
    assert "سایت را خواندم و سه موضوع پیدا کردم" in texts
    assert "از ChatGPT پرسید" in texts
    assert "یک قدم را گزارش داد؛ خروجی تحویل داد" in texts
    assert SA.DONE_FA in texts
    assert any(t.startswith("کار متوقف شد: سقف توکن امروز") for t in texts), texts
    for ln in act["last"]:
        plain(ln["text_fa"], ln["who_fa"])
        assert "W-" not in ln["text_fa"] and "substitute" not in ln["text_fa"]
    assert act["working"] == [] and act["idle_since"] is not None and act["waiting_fa"] is None
    assert act["stuck_fa"] is None  # idle, not yet for two thresholds
    # the owner's open turn: `waiting_fa`
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask", headers=await agent_headers(holder),
        json={"question_fa": "کدام موضوع را اول بسازم؟"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    act = (await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)).json()
    assert act["waiting_fa"] and "کدام موضوع" in act["waiting_fa"]
    # the stream: a run's step of a work of the order is a `session.activity` line, with the count
    # of runs working now; a run of no order emits nothing; a failure never fails the run
    run_id = await su.fetchval(
        "SELECT id FROM agents.runs WHERE work_id = $1 ORDER BY queued_at LIMIT 1", wid
    )
    async with await all_tx(hub) as tx:
        run = dict(await tx.one("SELECT * FROM agents.runs WHERE id = :id", id=run_id))
        emp = dict(await tx.one(
            "SELECT e.code, e.title_fa, e.company_id FROM core.employees e WHERE e.code = :c", c=holder
        ))  # fmt: skip
        await SA.on_run(tx, run, emp, "step", n=1, summary="موضوع پیدا شد",
                        actions=[{"tool": "web.read", "outcome": "ok", "hint": "pro-chart"}])  # fmt: skip
        await SA.on_run(tx, run, emp, "finished", state="failed", code="daily_cap")
        await SA.on_run(tx, {**run, "work_id": None}, emp, "step", n=1, summary="x", actions=[])
        bad = {**run, "work_id": "not-a-uuid"}
        await SA.on_run(tx, bad, emp, "step", n=1, summary="x", actions=[])  # swallowed, logged
    evs = await stream(su, ref, "session.activity")
    assert len(evs) == 2, evs
    assert evs[0]["data"]["order"] == ref and evs[0]["data"]["line"]["text_fa"] == "موضوع پیدا شد"
    assert isinstance(evs[0]["data"]["working"], int) and evs[0]["data"]["line"]["who_fa"]
    assert evs[1]["data"]["line"]["text_fa"].startswith("کار متوقف شد")
    assert ref not in evs[0]["data"]["line"]["text_fa"]


# ============================================= B. the owner's steps are the plan ==
async def test_the_owners_numbered_steps_become_the_plan_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    # the holder's own plan first (two of the owner's steps, word for word)
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack", headers=await agent_headers(holder),
        json={"plan_fa": "برنامه", "steps": ["موضوع روز را با ChatGPT پیدا کند", "متن گویندگی را بنویسد"]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    talk["router"].answers = [answer("فهمیدم، شروع میکنم.")]
    await say(client, owner, conv, NINE_STEPS)
    rep = await report(client, owner, ref)
    titles = [t["title_fa"] for t in rep["tasks"]]
    assert len(titles) == 9, titles  # the two the holder wrote were not added twice
    assert titles[:2] == ["موضوع روز را با ChatGPT پیدا کند", "متن گویندگی را بنویسد"]
    assert titles[2] == "صدا را از Google AI Studio بگیرد و کیفیتش را چک کند"
    assert titles[-1] == "بعد از انتشار تحلیل کند"
    assert [t["by"] for t in rep["tasks"]] == ["agent"] * 2 + ["owner"] * 7
    assert all(t["state"] == "todo" for t in rep["tasks"])
    assert any(s["what_fa"] == "برنامه: 7 کار از حرف مدیر کل" for s in rep["steps"]), rep["steps"]
    assert "برنامه: 7 کار" in (rep["memory_md"] or "")
    for t in titles:
        plain(t)
    # the same list again (the page's reply, or an `order` card): nothing added twice
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": NINE_STEPS[:1990]}
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["tasks"]) == 9
    # a word without a list adds nothing
    r = await client.post(
        f"/api/v1/orders/{ref}/reply",
        headers={**owner, **idem()},
        json={"text": "خوب است، ادامه بده"},
    )
    assert len(r.json()["tasks"]) == 9
    # the holder's brief: the plan with n, title, state, the next task and the instruction
    async with await all_tx(hub) as tx:
        wid = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=work_ref)
        d = await OT.dialogue(tx, wid)
    assert d is not None and len(d["plan"]) == 9
    assert d["plan"][0] == {"n": 1, "title": "موضوع روز را با ChatGPT پیدا کند", "state": "todo"}
    assert d["plan_next"] == 1 and "order.progress" in d["plan_instruction"]
    assert "order.ask" in d["plan_instruction"] and "Never stop silently" in d["plan_instruction"]
    assert "## The order you hold" in talk["router"].text_sent()


# ====================================================== C. never a silent stall ==
async def test_the_holder_is_woken_on_a_join_a_hire_decision_and_a_childs_delivery(
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
    root_ref = route["work_ref"]
    await refuse_queued(su, root_ref)
    # someone hired from the session's card (the filled-at-once path) → the holder woken
    conv_id = await su.fetchval("SELECT id FROM talk.conversations WHERE ref = $1", conv)
    async with await all_tx(hub) as tx:
        joined = await SE.join_hired(tx, f"{co}-SCRIPT", "scriptwriter", co, "نویسنده",
                                     conversation_id=conv_id)  # fmt: skip
    assert joined == [conv]
    woken = await runs_with_reason(su, root_ref, "joined:")
    assert len(woken) == 1 and woken[0]["state"] == "queued"
    assert woken[0]["reason"] == f"joined:{co}-SCRIPT"
    await refuse_queued(su, root_ref)
    # a hire card decided later (decisions.apply_effect → join_hired by the card's decision)
    card = {"kind": "hire", "title_fa": "استخدام مسئول انتشار", "body_fa": "",
            "payload": {"company": co, "role": "publisher", "department": "MEDIA"}}  # fmt: skip
    talk["router"].answers = [answer("کارت استخدام.", cards=[card])]
    said = await say(client, owner, conv, "یک مسئول انتشار استخدام کن")
    (c,) = said["answer"]["cards"]
    r = await run_card(client, owner, c)
    assert r.status_code == 200, r.text
    assert await runs_with_reason(su, root_ref, "joined:")  # the hire at once woke the holder too
    await refuse_queued(su, root_ref)
    await su.execute("UPDATE talk.cards SET made = ARRAY['D-999998'] WHERE id = $1", c["id"])
    async with await all_tx(hub) as tx:
        await SE.join_hired(tx, f"{co}-VOICE", "voice_producer", co, "تهیه‌کننده‌ی صدا",
                            decision_ref="D-999998")  # fmt: skip
    assert [w["reason"] for w in await runs_with_reason(su, root_ref, "joined:")][
        -1
    ] == f"joined:{co}-VOICE"
    await refuse_queued(su, root_ref)
    # a child work of the order delivered by someone else → the holder woken
    ask = {"kind": "ask", "title_fa": "از فنی بپرس", "body_fa": "",
           "payload": {"text": "عددهای سرور را بده", "to": "TECH"}}  # fmt: skip
    talk["router"].answers = [answer("میپرسم.", cards=[ask])]
    said = await say(client, owner, conv, "از فنی بپرس")
    (a,) = said["answer"]["cards"]
    r = await run_card(client, owner, a)
    assert r.status_code == 200, r.text
    [child_ref] = r.json()["made"]
    child_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", child_ref)
    await refuse_queued(su, root_ref)
    r = await deliver(client, f"{co}-TECH-MGR", child_id, "عددهای سرور")
    assert r.status_code in (200, 201), r.text
    woken = await runs_with_reason(su, root_ref, "child_delivered:")
    # (a child of the root: the database's own trigger wakes the parent first, the hook finds the
    # run queued; a requested work in another company has only the hook)
    assert len(woken) == 1 and woken[0]["reason"].startswith(f"child_delivered:{child_ref}")
    # a failed child wakes the holder too
    ask2 = {**ask, "payload": {"text": "یک سؤال دیگر", "to": "FIN"}}
    talk["router"].answers = [answer("میپرسم.", cards=[ask2])]
    said = await say(client, owner, conv, "از مالی بپرس")
    (a2,) = said["answer"]["cards"]
    [child2] = (await run_card(client, owner, a2)).json()["made"]
    child2_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", child2)
    await refuse_queued(su, root_ref)
    r = await client.post(
        f"/internal/v1/work/{child2_id}/fail", headers=await agent_headers(f"{co}-FIN-MGR"),
        json={"reason": "نشد"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert [w["reason"] for w in await runs_with_reason(su, root_ref, "child_failed:")] == [
        f"child_failed:{child2}"
    ]
    # the holder delivering its own root wakes nobody
    rep = await report(client, owner, ref)
    plain(*[s["what_fa"] for s in rep["steps"]])


async def test_the_sweep_wakes_an_idle_holder_once_then_marks_it_stuck_with_the_cause(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    holder, root_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root_ref)
    # a live (queued) run: nothing is idle, nothing fires
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == []
    await refuse_queued(su, root_ref)
    # idle a minute: nothing yet, and the badge says since when
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "moving"
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == []
    # idle past the threshold: the holder is woken once, with the plan's next task in the step
    h = await agent_headers(holder)
    r = await client.post(f"/internal/v1/orders/{ref}/ack", headers=h,
                          json={"plan_fa": "دو قدم", "steps": ["اول", "دوم"]})  # fmt: skip
    assert r.status_code == 200
    r = await client.post(f"/internal/v1/orders/{ref}/progress", headers=h,
                          json={"step_fa": "اول شد", "done": [1]})  # fmt: skip
    await su.execute(
        """UPDATE owner.order_reports SET last_step_at = now() - interval '11 minutes',
               acked_at = now() - interval '11 minutes' WHERE ref = $1""",
        ref,
    )
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == ["idle_wake"]
        assert await SA.sweep(tx, ref, minutes=10) == []  # live now (the woken run is queued)
    woken = await runs_with_reason(su, root_ref, "session_idle:")
    assert len(woken) == 1 and woken[0]["state"] == "queued"
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"] == "مسئول دوباره سر کار آمد: ادامه از کار 2", rep["steps"][
        -1
    ]
    assert rep["session"]["badge"] == "moving" and rep["session"]["reason_fa"].startswith(
        "در حال کار"
    )
    # the woken run was refused (the runtime down) and nothing moved for another threshold
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'runtime_not_configured', finished_at = now(),
               started_at = now() WHERE id = $1""",
        woken[0]["id"],
    )
    await su.execute(
        "UPDATE owner.order_reports SET last_step_at = now() - interval '14 minutes' WHERE ref = $1",
        ref,
    )
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == []  # woken already this period; not yet stuck
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "moving" and "کسی کار نمیکند" in rep["session"]["reason_fa"]
    await su.execute(
        "UPDATE owner.order_reports SET last_step_at = now() - interval '21 minutes' WHERE ref = $1",
        ref,
    )
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == ["stuck"]
        assert await SA.sweep(tx, ref, minutes=10) == []  # once
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "stuck", rep["session"]
    assert rep["session"]["reason_fa"].startswith("موتور اجرای ایجنت‌ها روی هاب آماده نیست")
    assert rep["steps"][-1]["what_fa"].startswith("گیر کرد: موتور اجرای ایجنت‌ها")
    notes = await su.fetch(
        """SELECT title_fa, body_fa, level, owner_visible FROM notify.notifications
           WHERE link_kind = 'order' AND link_ref = $1 AND source_code = 'sessions'""",
        ref,
    )
    assert len(notes) == 1 and notes[0]["level"] == "decision" and notes[0]["owner_visible"]
    assert "موتور اجرای ایجنت‌ها" in notes[0]["body_fa"] and "ادامه بده" in notes[0]["body_fa"]
    plain(notes[0]["title_fa"], notes[0]["body_fa"], rep["session"]["reason_fa"])
    act = (await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)).json()
    assert act["stuck_fa"] == rep["session"]["reason_fa"] and act["working"] == []
    # the badges streamed: moving … stuck
    # the cause when nothing explains it: the plain default
    async with await all_tx(hub) as tx:
        rep_row = await OR.ensure(tx, ref)
        assert rep_row is not None
        # (no run, no blocker, no failed call, no empty seat: nothing explains it)
        why = await SA.stuck_cause(tx, {**rep_row, "blockers": "[]"}, [], SA.clock_of(rep_row))
    assert why == SA.UNKNOWN_WHY_FA
    # the owner's open turn: never woken, never stuck
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask", headers=h, json={"question_fa": "ادامه؟"}
    )
    assert r.status_code == 200
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == []
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "your_turn"
    # D. «ادامه بده»: the holder woken now, the turn kept (the owner answers through reply)
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "بله"}
    )
    assert r.status_code == 200
    await refuse_queued(su, root_ref)
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers=owner)
    assert r.status_code == 422  # Idempotency-Key
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    act = r.json()
    assert len(act["working"]) == 1 and act["working"][0]["doing_fa"] == "در صف اجرا"
    nudged = await runs_with_reason(su, root_ref, "nudge:")
    assert len(nudged) == 1 and nudged[0]["state"] == "queued"
    rep = await report(client, owner, ref)
    assert rep["steps"][-1] == {
        **rep["steps"][-1],
        "who_fa": "مدیر کل",
        "what_fa": "مدیر کل گفت ادامه بده",
    }
    assert rep["session"]["badge"] == "moving"
    turns = await su.fetch(
        """SELECT t.by_kind, t.text FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE c.ref = $1 ORDER BY t.n DESC LIMIT 1""",
        out["talk_ref"],
    )
    assert turns[0]["by_kind"] == "owner" and turns[0]["text"] == "ادامه بده"
    # the tick runs the sweep for every open order (a failure in one never stops it)
    other = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    await refuse_queued(su, other["routes"][0]["work_ref"])
    await su.execute(
        "UPDATE owner.order_reports SET last_step_at = now() - interval '11 minutes' WHERE ref = $1",
        other["ref"],
    )
    tick = await OR.tick(hub)
    assert tick["orders"] >= 2 and tick["fired"].get(other["ref"]) == ["idle_wake"], tick
    assert ref not in tick["fired"]  # this one was woken this period already
    # a closed session: nothing
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200
    async with await all_tx(hub) as tx:
        assert await SA.sweep(tx, ref, minutes=10) == []
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers={**owner, **idem()})
    assert r.status_code == 409
    del wid


def test_the_badge_moves_only_with_a_live_run() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    rep = {"closed_at": None, "ended_at": None, "turn": None, "talk_stopped_at": None,
           "steps": [{"who_fa": "مدیرعامل", "what_fa": "برنامه"}], "last_step_at": now - timedelta(minutes=3),
           "acked_at": None, "created_at": now - timedelta(minutes=5)}  # fmt: skip
    roots = [{"is_root": True, "status": "in_progress"}]
    live = SA.Pulse(live=True, clock=rep["last_step_at"], idle=timedelta(0), woken=None, stuck_fa=None,
                    doing_fa="سایت را خواند")  # fmt: skip
    assert SE.badge_of(rep, "in_progress", roots, [], decision_pending=False, pulse=live) == (
        "moving",
        "در حال کار: سایت را خواند",
    )
    idle = SA.Pulse(
        live=False, clock=rep["last_step_at"], idle=timedelta(minutes=3), woken=None, stuck_fa=None
    )
    badge, why = SE.badge_of(rep, "in_progress", roots, [], decision_pending=False, pulse=idle)
    assert badge == "moving" and why == "از 3 دقیقه پیش کسی کار نمیکند؛ مسئول بیدار میشود"
    stuck = SA.Pulse(live=False, clock=rep["last_step_at"], idle=timedelta(minutes=25), woken=None,
                     stuck_fa="بودجه‌ی این کار تمام شده است. بودجه‌ی کار را در گزارش فرمان بیشتر کنید.")  # fmt: skip
    assert (
        SE.badge_of(rep, "in_progress", roots, [], decision_pending=False, pulse=stuck)[0]
        == "stuck"
    )
    # the owner's turn and a closed session come first, live or not
    assert SE.badge_of({**rep, "turn": {"who_fa": "x", "question_fa": "q"}}, "waiting", roots, [],
                       decision_pending=False, pulse=live)[0] == "your_turn"  # fmt: skip
    assert SE.badge_of({**rep, "closed_at": now}, "cancelled", roots, [], decision_pending=False,
                       pulse=live)[0] == "closed"  # fmt: skip
    # without a pulse (older callers) the badge is as before
    assert SE.badge_of(rep, "in_progress", roots, [], decision_pending=False) == (
        "moving",
        "مدیرعامل: برنامه",
    )
