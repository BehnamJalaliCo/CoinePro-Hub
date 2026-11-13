"""⟨2026-11-09⟩ «با من» holds the whole session while it waits for the owner.

The owner: «یه جلسه باز کردم … دکمه با من رو زدم و شروع کرده برای خودش کار رو جلو بردن». The
holder asked him after its step, but the part it had handed to a colleague (the company's CTO)
went on running. In a step-by-step order, while the owner has not answered, nothing of the order
runs: not its holder, not a colleague; the runs come back the moment he answers, says «ادامه بده»
or makes the order «خودکار». A general order («خودکار») is never held.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import order_report as OR
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture


async def queued_of(su: Any, work_id: Any) -> Any:
    return await su.fetchrow(
        """SELECT id, reason FROM agents.runs WHERE work_id = $1 AND state = 'queued'
           ORDER BY queued_at DESC LIMIT 1""",
        work_id,
    )


async def ask(client: httpx.AsyncClient, ref: str, holder: str, q: str) -> None:
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask",
        headers=await agent_headers(holder),
        json={"question_fa": q},
    )
    assert r.status_code == 200, r.text


async def test_a_step_session_holds_everything_until_the_owner_answers(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    text = f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    out = await post_order(client, owner, text, pace="step")
    ref = out["ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    assert holder == f"{co}-CEO", route
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)

    # the holder hands a part of its step to a colleague (the screenshot: the CTO reading numbers)
    r = await client.post(
        f"/internal/v1/work/{root}/delegate",
        headers=await agent_headers(holder),
        json={"to": f"{co}-TECH-MGR", "title": "خواندن عددهای روزانه"},
    )
    assert r.status_code == 201, r.text
    child = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", r.json()["ref"])
    part = await queued_of(su, child)
    assert part is not None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, child) is None  # nothing asked yet

    # the holder asks the owner: the whole session now waits for him
    await ask(client, ref, holder, "گام ۲ تمام شد؛ گام ۳ را شروع کنم؟")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        waiting = await OR.owner_turn(tx, child)
    assert waiting is not None and waiting["askers"] == {holder} and waiting["since"] is not None
    claim = await agents.runner.claim(str(part["id"]))
    assert (claim.state, claim.code) == ("final", "owner_turn")
    # the requeue sweep does not bring it back while he has not answered
    from hq_api.worker.activities import Activities

    acts = Activities(
        agents.whub, None, router=agents.router, gateway=agents.gateway, live=agents.live
    )
    await acts.requeue_runs()
    assert await queued_of(su, child) is None
    # a wake his own word started is never held (here: his «ادامه بده» reason)
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = $1 AND state = 'queued'""",
        root,
    )
    rid = await su.fetchval(
        "SELECT work.wake_assignee($1, $2)", root, f"child_delivered:{work_ref}:O-000001"
    )
    assert (await agents.runner.claim(str(rid))).code == "owner_turn"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert not await OR.held_for_owner(
            tx, {"trigger": "work", "work_id": root, "reason": f"nudge:{ref}"}
        )
        assert not await OR.held_for_owner(  # the owner's talk with the holder is never held
            tx, {"trigger": "talk", "work_id": root, "reason": "talk"}
        )

    # the owner answers: the holder runs with his word, and the colleague's part goes on
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "بله، ادامه بده"}
    )
    assert r.status_code == 200, r.text
    resumed = await queued_of(su, child)
    assert resumed is not None and resumed["reason"] == f"{OR.OWNER_TURN_REASON}{ref}"
    assert (await queued_of(su, root))["reason"] == f"owner_reply:{ref}"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, child) is None
    assert (await agents.runner.claim(str(resumed["id"]))).state == "running"

    # «ادامه بده» while a question is open answers it: the turn is cleared
    await ask(client, ref, holder, "گام ۴ را شروع کنم؟")
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT turn FROM owner.order_reports WHERE ref = $1", ref) is None

    # a general order («خودکار») is never held, an open question or not
    await ask(client, ref, holder, "گام ۵ را شروع کنم؟")
    r = await client.post(
        f"/api/v1/orders/{ref}/pace", headers={**owner, **idem()}, json={"pace": "auto"}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.owner_turn(tx, root) is None


async def test_the_nudge_wakes_whoever_asked_and_a_word_before_the_question_does_not_answer_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """⟨2026-11-10⟩ audit: «ادامه بده» cleared a colleague's question and woke only the holder
    (the colleague slept for ever); and a run his word had queued BEFORE a question was asked ran
    through that question. Also: a closed session takes no step, and its asker's run is a
    finished one."""
    co = (await new_company())["code"]
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="step"
    )
    ref = out["ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    r = await client.post(
        f"/internal/v1/work/{root}/delegate",
        headers=await agent_headers(holder),
        json={"to": f"{co}-TECH-MGR", "title": "خواندن عددهای روزانه"},
    )
    assert r.status_code == 201, r.text
    child = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", r.json()["ref"])
    colleague = f"{co}-TECH-MGR"
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', error_code = 'test', finished_at = now()
           WHERE work_id = ANY($1::uuid[]) AND state = 'queued'""",
        [root, child],
    )

    # a word of the owner's queued a run of the holder; THEN the colleague asks him something
    early = await su.fetchval("SELECT work.wake_assignee($1, $2)", root, f"nudge:{ref}")
    await asyncio.sleep(0.2)  # the question comes after his word
    await ask(client, ref, colleague, "عددها را از کدام حساب بخوانم؟")
    claim = await agents.runner.claim(str(early))
    assert (claim.state, claim.code) == ("final", "owner_turn")  # his earlier word is no answer

    # «ادامه بده» answers the question: the one who asked runs again, not only the holder
    r = await client.post(f"/api/v1/orders/{ref}/nudge", headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT turn FROM owner.order_reports WHERE ref = $1", ref) is None
    woke = await queued_of(su, child)
    assert woke is not None and woke["reason"] == f"nudge:{ref}", woke
    assert (await queued_of(su, root)) is not None
    # (the colleague's test token is a run of its own, so the claim reads `busy`: not held)
    assert (await agents.runner.claim(str(woke["id"]))).code != "owner_turn"

    # the owner closes the session: nothing more is written on it by a run that was still going
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask",
        headers=await agent_headers(holder),
        json={"question_fa": "ادامه بدهم؟"},
    )
    assert r.status_code == 409 and r.json()["code"] == "work_closed", r.text
    r = await client.post(
        f"/internal/v1/orders/{ref}/progress",
        headers=await agent_headers(holder),
        json={"step_fa": "یک قدم دیگر"},
    )
    assert r.status_code == 409 and r.json()["code"] == "work_closed", r.text


async def test_the_owners_numbered_steps_are_the_plan_in_his_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """⟨2026-11-10⟩ the owner's recording of 2026-11-09: he gave nine numbered steps (script,
    voice, voice check, direction, …); the holder already had five of its own, so his were
    appended after them and its «ساخت اولین ریلز» (4) ran before his script and voice (7, 8).
    His numbered steps are the plan: the holder's open ones step aside, and the numbers are the
    places in the plan."""
    from hq_api.domain import order_turns as OT

    co = (await new_company())["code"]
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="step"
    )
    ref = out["ref"]
    [route] = out["routes"]
    holder = route["to"]
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack",
        headers=await agent_headers(holder),
        json={
            "plan_fa": "برنامه‌ی من",
            "steps": [
                "بررسی وضع کارگروه",
                "ساختار روزانه و سری",
                "تکمیل تیم",
                "ساخت اولین ریلز و بازبینی",
                "انتشار و تحلیل",
            ],
        },
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/internal/v1/orders/{ref}/progress",
        headers=await agent_headers(holder),
        json={"step_fa": "وضع کارگروه بررسی شد", "done": [1]},
    )
    assert r.status_code == 200, r.text

    steps = (
        "به هرچه میگویم دقت کن.\n"
        "۱ - نویسنده یا سناریست باید استخدام بشه\n"
        "۲ - متن گفتار ۱ تا ۱:۳۰ دقیقه برای ساخت صدا آماده بشه\n"
        "۳ - بعد از صدا، QC زبان فارسی بررسی بکنه\n"
        "۴ - کارگردانی و تدوین لحظه‌ای روی متن صدا\n"
        "۵ - موشن‌گرافی ساخته بشه"
    )
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": steps}
    )
    assert r.status_code == 200, r.text
    rows = await su.fetch(
        """SELECT t.n, t.title_fa, t.state, t.by FROM owner.session_tasks t
           JOIN owner.order_reports r ON r.order_id = t.order_id WHERE r.ref = $1 ORDER BY t.n""",
        ref,
    )
    live = [(x["n"], x["by"], x["state"]) for x in rows if x["state"] != "dropped"]
    # what was done stays first; then HIS steps, in HIS order, numbered on from there
    assert live == [(1, "agent", "done"), *[(n, "owner", "todo") for n in range(2, 7)]], rows
    assert "سناریست" in rows[1]["title_fa"] and "متن گفتار" in rows[2]["title_fa"]
    assert "QC" in rows[3]["title_fa"] and "موشن" in rows[5]["title_fa"]
    # the holder's own open steps (its «ساخت اولین ریلز» among them) stepped aside
    aside = [x["title_fa"] for x in rows if x["state"] == "dropped"]
    assert len(aside) == 4 and any("ریلز" in t for t in aside), rows
    said = await su.fetchval("SELECT steps::text FROM owner.order_reports WHERE ref = $1", ref)
    assert "برنامه‌ی قبلی مسئول کنار رفت" in said

    # the holder's brief names the next task and the rule, by code
    async with hub.db.tx(await hub.companies.ids()) as tx:
        brief = await OT.talk_brief(tx, ref)
        work_id = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=route["work_ref"])
        nxt = await OT.step_next(tx, work_id)
    assert brief is not None and brief["plan_next"] == 2
    assert "next open task is 2" in brief["step_rule"] and "سناریست" in brief["step_rule"]
    assert "start NO task" in brief["step_rule"] and "workshop.stop" in brief["step_rule"]
    assert nxt is not None and nxt["n"] == 2

    # the same list again adds nothing and drops nothing
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": steps}
    )
    assert r.status_code == 200, r.text
    again = await su.fetchval(
        """SELECT count(*) FROM owner.session_tasks t JOIN owner.order_reports r
             ON r.order_id = t.order_id WHERE r.ref = $1 AND t.state <> 'dropped'""",
        ref,
    )
    assert again == 6

    # closing drops what is open; reopening brings the plan back (not the steps set aside before)
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/orders/{ref}/reopen", headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    back = await su.fetch(
        """SELECT t.n, t.state FROM owner.session_tasks t JOIN owner.order_reports r
             ON r.order_id = t.order_id WHERE r.ref = $1 AND t.state <> 'dropped' ORDER BY t.n""",
        ref,
    )
    assert [(x["n"], x["state"]) for x in back] == [
        (1, "done"),
        *[(n, "todo") for n in range(2, 7)],
    ]


def _step(summary: str, *, done: bool) -> dict[str, Any]:
    return {"summary_fa": summary, "actions": [], "done": done}


async def test_a_run_his_answer_woke_is_not_cut_by_the_next_question(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: Any,
) -> None:
    """⟨2026-11-13⟩ F-0018 P3: in a «با من» session the holder asked the owner after nearly every
    turn. Each answer woke the colleague's held part (`owner_turn_over:`), its run made one to six
    model steps, and the holder's next question cut it (`owner_turn`) mid-way: W-000381 was woken
    and cut 12 times in 27 minutes, each time from its first step. Now a question holds a run
    only before its first model step; one that has started goes on to its end, and the question
    holds the work's next run."""
    co = (await new_company())["code"]
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده", pace="step"
    )
    ref = out["ref"]
    [route] = out["routes"]
    holder, colleague = route["to"], f"{co}-TECH-MGR"
    root = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    r = await client.post(
        f"/internal/v1/work/{root}/delegate",
        headers=await agent_headers(holder),
        json={"to": colleague, "title": "خواندن عددهای روزانه"},
    )
    assert r.status_code == 201, r.text
    child = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", r.json()["ref"])
    part = await queued_of(su, child)

    # the holder asks; the part is held at its claim; his answer wakes it
    await ask(client, ref, holder, "گام ۲ تمام شد؛ گام ۳ را شروع کنم؟")
    assert (await agents.runner.claim(str(part["id"]))).code == "owner_turn"
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "بله"}
    )
    assert r.status_code == 200, r.text
    woken = await queued_of(su, child)
    assert woken["reason"] == f"{OR.OWNER_TURN_REASON}{ref}"
    assert (await agents.runner.claim(str(woken["id"]))).state == "running"

    # the holder asks again after the part's first model step (its next direct turn)
    real_step = agents.runner._model_step
    asked: list[int] = []

    async def step_then_ask(rc: Any, system: str, n: int, **kw: Any) -> Any:
        call = await real_step(rc, system, n, **kw)
        if not asked:
            asked.append(n)
            await ask(client, ref, holder, "گام ۳ هم تمام شد؛ گام ۴؟")
        return call

    monkeypatch.setattr(agents.runner, "_model_step", step_then_ask)
    agents.fake.enqueue(
        colleague,
        _step("قدم یک", done=False),
        _step("قدم دو", done=False),
        _step("تمام", done=True),
    )
    out = await agents.runner.execute(str(woken["id"]))
    assert asked == [1]
    assert out == {"state": "done", "code": None}, out  # before: refused, owner_turn, after 1 step
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", woken["id"]) == 3

    # the question holds the work's NEXT run, at its claim
    nxt = await su.fetchval("SELECT work.wake_assignee($1, $2)", child, "child_delivered:x")
    assert (await agents.runner.claim(str(nxt))).code == "owner_turn"

    # a question between the claim and the first model step: refused, no model call made
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "بله"}
    )
    assert r.status_code == 200, r.text
    again = await queued_of(su, child)
    assert again["reason"] == f"{OR.OWNER_TURN_REASON}{ref}"
    assert (await agents.runner.claim(str(again["id"]))).state == "running"
    await ask(client, ref, holder, "گام ۵؟")
    calls = sum(1 for c in agents.fake.calls if c.actor_ref == colleague)
    out = await agents.runner.execute(str(again["id"]))
    assert out == {"state": "refused", "code": "owner_turn"}, out
    assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", again["id"]) == 0
    assert sum(1 for c in agents.fake.calls if c.actor_ref == colleague) == calls
