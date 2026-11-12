"""Audit 2026-11-08 (docs/AUDIT_2026-11-08.md) — the findings fixed in W11, each proved the other way
round from the audit's own scenario tests:

B1  the owner's word in a working session is the order's word by code (a step, the holder woken,
    the brief carries the last owner turns verbatim);
B3  the talk-loop stop counts only runs that produced nothing, never the hub's own wakes, resets on
    progress, and is at least 3x the plan; a NULL wake always writes a step (M11);
B5  the day's caps count effective tokens (a cache read at a tenth), as the run's cap does;
B4  while links are not enforced a manager asks another company's CEO, any role asks the holding's
    AIOPS or LEGAL, and a company present in the session counts as linked;
M4  a hire refused for a missing or full envelope is a `budget` blocker with the fix envelope.set;
M5  a routine's work is never below its seat's floor; the seeds and the playbook default too;
M7  a budget stop adds +X by code within the envelope, the CEO asked only when it does not fit;
M10 a tool's refusal names a fix only where one exists;
m1  the voice-off notice once per conversation.
(M1 is proved in test_p21_routing_orders: a manager's hire inside the envelope is approved by code.)
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx

from hq_api.agents import runner
from hq_api.domain import groups as GR
from hq_api.domain import links as LK
from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import playbooks as PB
from hq_api.domain import work as W
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_routing_orders import all_tx, auto_hiring, envelope, make_order, report  # noqa: F401
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, open_cv, say, talk  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued

SLOGAN = "بازار را بخوان، نه شایعه را"
NINE_STEPS = (
    "کارگروه روزانه‌ی ریلز:\n"
    "۱- موضوع روزانه با ChatGPT، بدون تکرار تا ۳۶۵ روز\n"
    "۲- متن گویندگی ۱ تا ۱.۵ دقیقه با شعار ثابت «" + SLOGAN + "»\n"
    "۳- صدا با Google AI Studio، گوینده‌ی ثابت Kore\n"
    "۴- کنترل غلط فارسی صدا"
)


async def runs_of_order(su: Any, ref: str, states: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await su.fetch(
            """SELECT r.reason, r.state FROM agents.runs r
               WHERE r.state = ANY($2::text[])
                 AND r.work_id IN (SELECT w.id FROM work.work w
                                    WHERE w.ref = ANY((SELECT work_refs FROM owner.order_reports
                                                        WHERE ref = $1)::text[]))
               ORDER BY r.queued_at""",
            ref,
            list(states),
        )
    ]


async def done_run(
    su: Any, work_id: Any, reason: str, actions: list[dict[str, Any]] | None = None
) -> Any:
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               priority, started_at, finished_at)
           SELECT company_id, assignee_id, id, 'work', $2, 'done', 'P2', now(), now()
           FROM work.work WHERE id = $1 RETURNING id""",
        work_id,
        reason,
    )
    if actions:
        await su.execute(
            """INSERT INTO agents.steps (run_id, company_id, n, summary_fa, actions)
               SELECT $1, company_id, 1, 'قدم', $2::jsonb FROM agents.runs WHERE id = $1""",
            rid,
            json.dumps(actions),
        )
    return rid


# ===================================================================== B1 ==
async def test_the_owners_word_in_a_working_session_is_the_orders_word_by_code(
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
    root_ref = route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root_ref)
    await refuse_queued(su, root_ref)
    assert await runs_of_order(su, ref, ("queued", "running")) == []
    assert OT.is_question("چرا کار جلو نمیرود") and OT.is_question("ادامه بدهیم؟")
    assert not OT.is_question(NINE_STEPS) and not OT.is_question("از صفحه‌ی آموزش شروع کن")
    # a working session (the order's talk opens in work mode): the owner's plan reaches the holder
    talk["router"].answers = [answer("یادداشت گرفتم؛ شروع میکنم.", "**یادداشت‌ها**")]
    said = await say(client, owner, conv, NINE_STEPS)
    assert said["answer"]["cards"] == []  # no card to tap
    live = await runs_of_order(su, ref, ("queued", "running"))
    assert [r["reason"] for r in live] == [f"owner_reply:{ref}"]  # the holder is woken by code
    rep = await report(client, owner, ref)
    assert any(s["who_fa"] == "مدیر کل" and SLOGAN in s["what_fa"] for s in rep["steps"]), rep[
        "steps"
    ]
    assert len(rep["tasks"]) == 4  # §41.2 the numbered list, once
    async with await all_tx(hub) as tx:
        brief = await OT.dialogue(tx, wid)
    assert brief is not None
    text = json.dumps(brief, ensure_ascii=False)
    assert SLOGAN in text and "Kore" in text  # the prose a task title cannot hold, verbatim
    assert brief["owner_said"] and NINE_STEPS.strip() in brief["owner_said"][-1]
    assert len(brief["plan"]) == 4 and brief["plan_next"] == 1
    # a question is answered by the talk alone: no step, nobody woken
    await refuse_queued(su, root_ref)
    talk["router"].answers = [answer("هنوز نه؛ تا ظهر.")]
    await say(client, owner, conv, "موضوع امروز را پیدا کردی؟")
    assert await runs_of_order(su, ref, ("queued", "running")) == []
    rep = await report(client, owner, ref)
    assert all("موضوع امروز را پیدا کردی" not in s["what_fa"] for s in rep["steps"])
    assert len(brief["owner_said"]) <= OT.OWNER_SAID
    # consult mode: the owner's word feeds the plan only
    await say(client, owner, conv, "حالت مشورت")
    talk["router"].answers = [answer("مشورت.")]
    await say(client, owner, conv, "1- اول این 2- بعد آن")
    assert await runs_of_order(su, ref, ("queued", "running")) == []
    rep = await report(client, owner, ref)
    assert len(rep["tasks"]) == 6


# ===================================================================== B3 + M11 ==
async def test_the_talk_loop_counts_only_runs_that_produced_nothing_and_a_null_wake_says_why(
    hub: Hub,
    wk: dict[str, Any],
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    made = await make_order(hub, company, WORK_TEXT.format(co=company["code"], w=words()))
    ref, w = made["ref"], made["work"]
    await refuse_queued(su, w["ref"])
    assert hub.settings.order_talk_limit == 12
    progress = [{"tool": "order.progress", "class": "A1", "outcome": "ok"}]
    # 13 runs that each reported a step: work, never «talk without output»
    for i in range(13):
        await done_run(su, w["id"], f"progress:{i}", progress)
    # 13 wakes of the hub's own: never counted either
    wakes = ("session_idle", "owner_reply", "child_delivered", "child_cancelled", "joined", "nudge")
    for why in wakes:
        for _ in range(3):
            await done_run(su, w["id"], f"{why}:{ref}")
    async with await all_tx(wk["hub"]) as tx:
        assert "talk_loop" not in await OR.timers(tx, hub.settings, ref)
        assert (
            await OR.idle_runs(
                tx, await OR.ensure(tx, ref), [{"id": w["id"]}], made["work"]["created_at"]
            )
            == 0
        )
    # the limit grows with the plan: 3 per task, never below the setting
    h = await agent_headers(f"{company['code']}-CEO")
    r = await client.post(f"/internal/v1/orders/{ref}/ack", headers=h,
                          json={"plan_fa": "برنامه", "steps": [f"کار {i}" for i in range(6)]})  # fmt: skip
    assert r.status_code == 200, r.text
    async with await all_tx(wk["hub"]) as tx:
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        assert await OR.talk_limit(tx, rep, 12) == 18
        assert await OR.talk_limit(tx, rep, 40) == 40
    # empty runs count — from the last step of the story (the ack moved it): 18 of them stop it
    await su.execute(
        "UPDATE owner.order_reports SET last_step_at = now() - interval '1 hour' WHERE ref = $1",
        ref,
    )
    for i in range(19):
        await done_run(su, w["id"], f"empty:{i}")
    async with await all_tx(wk["hub"]) as tx:
        fired = await OR.timers(tx, hub.settings, ref)
        assert "talk_loop" in fired
        # M11: a wake that returns NULL writes a step saying why, never a silent nothing
        out = await OT.wake_or_say(tx, ref, "test:wake")
    assert out["run_id"] is None and out["why_fa"]
    rep_out = await report(client, owner, ref)
    assert rep_out["steps"][-1]["what_fa"].startswith("مسئول بیدار نشد:"), rep_out["steps"][-1]
    assert rep_out["session"]["badge"] == "stuck"
    # progress resets the count: the owner's reply restarts the order and the holder is woken
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "ادامه"}
    )
    assert r.status_code == 200, r.text
    async with await all_tx(wk["hub"]) as tx:
        assert "talk_loop" not in await OR.timers(tx, hub.settings, ref)
    assert [x["reason"] for x in await runs_of_order(su, ref, ("queued",))] == [
        f"owner_reply:{ref}"
    ]


# ===================================================================== B5 ==
async def test_the_day_caps_count_effective_tokens_like_the_run_cap(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    r = runner.Runner(hub, router=None, gateway=None)  # type: ignore[arg-type]
    async with await all_tx(hub) as tx:
        before = await r._spent_today(tx)
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
               status, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, meta)
           VALUES ($1, now(), $2, 'audit', 'general', 3, 'audit', 'ok', 1000, 500, 40000, 0,
                   '{"run_id": "audit"}'::jsonb)""",
        uuid.uuid4(),
        company["id"],
    )
    async with await all_tx(hub) as tx:
        after = await r._spent_today(tx)
    assert after - before == W.effective_tokens(1000, 500, 40000, 0) == 5_500
    # the company's cap counts the same way
    await su.execute(
        "UPDATE core.companies SET daily_token_cap = 5_600 WHERE id = $1", company["id"]
    )
    async with await all_tx(hub) as tx:
        assert await r._company_cap_reached(tx, company["id"]) is False
    await su.execute(
        "UPDATE core.companies SET daily_token_cap = 5_400 WHERE id = $1", company["id"]
    )
    async with await all_tx(hub) as tx:
        assert await r._company_cap_reached(tx, company["id"]) is True
    await su.execute(
        "UPDATE core.companies SET daily_token_cap = NULL WHERE id = $1", company["id"]
    )


# ===================================================================== B4 ==
async def test_a_manager_asks_another_company_and_the_hub_while_links_are_open(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    third = (await new_company())["code"]
    body = {"company": other, "title": "انتشار ریل روی حساب ما", "brief": "ریل آماده است",
            "kind": "one_off", "priority": "P2"}  # fmt: skip
    headers = await agent_headers(f"{co}-MEDIA-MGR")
    # links not enforced (the default): the other company's CEO takes it
    r = await client.post("/internal/v1/work", json=body, headers={**headers, **idem()})
    assert r.status_code == 201, r.text
    assert r.json()["work"]["assignee"]["code"] == f"{other}-CEO"
    # any role asks the holding's AIOPS (its manager): the hub's technical hand
    holding = await hub.companies.holding()
    r = await client.post(
        "/internal/v1/work",
        json={**body, "company": holding.code, "department": "AIOPS", "title": "n8n را روشن کن"},
        headers={**(await agent_headers(f"{co}-MEDIA-01")), **idem()}
        if await su.fetchval("SELECT 1 FROM core.employees WHERE code = $1", f"{co}-MEDIA-01")
        else {**headers, **idem()},
    )
    assert r.status_code == 201, r.text
    assert r.json()["work"]["company"] == holding.code
    # a named person in another company: still never
    r = await client.post(
        "/internal/v1/work", json={**body, "to": f"{other}-TECH-MGR"}, headers={**headers, **idem()}
    )
    assert r.status_code == 403
    # links enforced: only along an `on` link — or a company present in the session of the order
    await su.execute("UPDATE owner.settings SET links_enforced = true WHERE id = 1")
    try:
        r = await client.post("/internal/v1/work", json=body, headers={**headers, **idem()})
        assert r.status_code == 403, r.text
        async with await all_tx(hub) as tx:
            await LK.create(
                tx, holding.id, LK.LinkIn(**{"from": co, "to": other, "kind": "publishes"})
            )
        r = await client.post("/internal/v1/work", json=body, headers={**headers, **idem()})
        assert r.status_code == 201, r.text
        # the third company is not linked, but its CEO sits in the session of the order
        out = await post_order(client, owner, f"برای {co} یک ریلز آموزشی بساز {words()}")
        ref, conv = out["ref"], out["talk_ref"]
        root_ref = next(x["work_ref"] for x in out["routes"] if x["company"] == co)
        root_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root_ref)
        r = await client.post("/internal/v1/work", headers={**headers, **idem()},
                              json={**body, "company": third, "requested_by_work_id": str(root_id)})  # fmt: skip
        assert r.status_code == 403, r.text
        r = await client.post(f"/api/v1/orders/{ref}/participants", headers=owner,
                              json={"kind": "person", "key": f"ceo@{third}"})  # fmt: skip
        assert r.status_code == 200, r.text
        r = await client.post("/internal/v1/work", headers={**headers, **idem()},
                              json={**body, "company": third, "requested_by_work_id": str(root_id)})  # fmt: skip
        assert r.status_code == 201, r.text
        assert r.json()["work"]["assignee"]["code"] == f"{third}-CEO"
        del conv
    finally:
        await su.execute("UPDATE owner.settings SET links_enforced = false WHERE id = 1")


# ===================================================================== M4 + M10 ==
async def test_an_envelope_refusal_is_a_blocker_with_a_fix_and_a_tool_refusal_names_a_real_fix(
    hub: Hub,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    made = await make_order(hub, company, WORK_TEXT.format(co=co, w=words()))
    ref, w = made["ref"], made["work"]
    await refuse_queued(su, w["ref"])

    async def refused(tool: str, code: str) -> None:
        await done_run(su, w["id"], f"audit:{code}",
                       [{"tool": tool, "class": "A1", "outcome": "refused", "code": code}])  # fmt: skip

    await refused("propose", "envelope_required")
    rep = await report(client, owner, ref)
    [b] = [x for x in rep["blockers"] if x["kind"] == "budget"]
    assert b["title_fa"] == "پاکت ماه شرکت تعیین نشده"
    assert b["fix"] == {"action": "envelope.set", "label_fa": "پاکت ماه را تعیین کن", "target": co}
    assert rep["session"]["badge"] == "your_turn"
    r = await client.post(f"/api/v1/orders/{ref}/fix", headers=owner,
                          json={"action": "envelope.set", "target": co})  # fmt: skip
    assert r.status_code == 200, r.text  # the app's own page; nothing refused
    # a full envelope (another order of the company): the same fix
    made2 = await make_order(hub, company, WORK_TEXT.format(co=co, w=words()))
    await refuse_queued(su, made2["work"]["ref"])
    await done_run(su, made2["work"]["id"], "audit:envelope_exceeded",
                   [{"tool": "propose", "class": "A1", "outcome": "refused", "code": "envelope_exceeded"}])  # fmt: skip
    rep2 = await report(client, owner, made2["ref"])
    [full] = [x for x in rep2["blockers"] if x["kind"] == "budget"]
    assert full["title_fa"] == "پاکت ماه شرکت پر است"
    assert full["fix"] == {
        "action": "envelope.set",
        "label_fa": "پاکت ماه را تعیین کن",
        "target": co,
    }
    # M10: a tool's missing account, in words; a fix only where a page exists. ⟨2026-11-08⟩ the
    # owner's decisions: voice off and no video tool — their refusals are never a blocker
    await refused("speech.make", "channel_not_configured")
    await refused("media.render", "channel_not_configured")
    await refused("substitute.call", "channel_not_configured")
    await refused("telegram", "channel_not_configured")
    await refused("some.tool", "channel_not_configured")
    rep = await report(client, owner, ref)
    conn = {x["title_fa"]: x for x in rep["blockers"] if x["kind"] == "connection_missing"}
    assert not [t for t in conn if "صدا" in t or "ویدیو" in t], list(conn)
    assert conn["بازیکن بیرونی وارد حسابش نیست"]["fix"] is None
    generic = [x for x in rep["blockers"] if x["title_fa"] == "یک اتصال وصل نیست"]
    assert {(x["fix"] or {}).get("target") for x in generic} == {"telegram", None}
    assert all((x["fix"] or {}).get("action") in (None, "connection.guide") for x in generic)
    for x in rep["blockers"]:
        assert "speech.make" not in x["title_fa"] and "some.tool" not in json.dumps(
            x, ensure_ascii=False
        )


# ===================================================================== M5 ==
async def test_routines_never_sit_below_their_seats_floor(hub: Hub) -> None:
    lib = hub.charters
    assert lib is not None
    async with await all_tx(hub) as tx:
        floor = {
            role: await W.budget_floor(tx, lib, role)
            for role in ("media_director", "publisher", "content_analyst", "scriptwriter")
        }
    [(_key, content)] = [(k, d) for k, d in GR.load_files() if k == "content"]
    routines = {r["key"]: r for r in content["routines"]}
    below = {k: (r["max_tokens"], floor[r["seat"]]) for k, r in routines.items()
             if r["seat"] in floor and r["max_tokens"] < floor[r["seat"]]}  # fmt: skip
    assert below == {}, below
    assert routines["evening_line"]["max_tokens"] >= floor["media_director"]
    assert routines["publishing"]["max_tokens"] >= floor["publisher"]
    assert max(floor.values()) <= PB.DEFAULT_TOKENS
    import inspect

    src = inspect.getsource(GR.run_routine)
    assert "raise_to_floor" in src


# ===================================================================== M7 ==
async def test_a_budget_stop_adds_by_code_within_the_envelope(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    co = company["code"]
    rn = runner.Runner(hub, None, None, None)  # type: ignore[arg-type]
    rc = SimpleNamespace(
        charter=SimpleNamespace(
            limits=SimpleNamespace(tokens_per_run=160_000, tokens_per_step=40_000)
        ),
        emp={"code": f"{co}-TECH-MGR"},
    )
    async with await all_tx(hub) as tx:
        plain = await W.create(
            tx, OR.SERVICE, company_id=company["id"], company_code=co, title="کار معمولی",
            brief="x", kind="one_off", priority="P3", assignee_code=f"{co}-TECH-MGR",
            budget=W.BudgetIn(tokens=50_000),
        )  # fmt: skip
    # no envelope: the CEO is asked, as before
    await rn._budget_stop(rc, plain["ref"])  # type: ignore[arg-type]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", plain["id"]) == "waiting"
    assert (
        await su.fetchval(
            "SELECT count(*) FROM work.work WHERE title LIKE 'بودجه کم است%' AND company_id = $1",
            company["id"],
        )
        == 1
    )
    # an envelope with room: +X by code, audited, the work goes on; no second ask
    await envelope(su, company, 50_000_000)
    async with await all_tx(hub) as tx:
        second = await W.create(
            tx, OR.SERVICE, company_id=company["id"], company_code=co, title="کار دوم",
            brief="x", kind="one_off", priority="P3", assignee_code=f"{co}-TECH-MGR",
            budget=W.BudgetIn(tokens=50_000),
        )  # fmt: skip
    await rn._budget_stop(rc, second["ref"])  # type: ignore[arg-type]
    row = await su.fetchrow(
        "SELECT status, budget_tokens FROM work.work WHERE id = $1", second["id"]
    )
    assert row["status"] == "in_progress" and row["budget_tokens"] == 50_000 + 160_000
    assert (
        await su.fetchval(
            "SELECT count(*) FROM work.work WHERE title LIKE 'بودجه کم است%' AND company_id = $1",
            company["id"],
        )
        == 1
    )
    assert (
        await su.fetchval(
            """SELECT count(*) FROM audit.entries WHERE action = 'work.budget' AND target_ref = $1
           AND summary LIKE '%by code within the month envelope%'""",
            second["ref"],
        )
        == 1
    )


# ===================================================================== m1 ==
async def test_a_voice_layer_down_never_writes_a_notice(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    talk: dict[str, Any],  # noqa: F811
) -> None:
    """m1 as the owner decided it on 2026-11-08: no voice notice, ever (not once, not at all);
    the answer is text alone (the voice is on here, the layer down)."""
    cv = await open_cv(client, owner)
    talk["voice"].unavailable = True
    talk["router"].answers = [answer("سلام.")]
    out = await say(client, owner, cv["ref"], "سلام")
    assert out["answer"]["state"] == "done" and "صدا" not in out["answer"]["show_md"]
    talk["router"].answers = [answer("باز هم سلام.")]
    out = await say(client, owner, cv["ref"], "دوباره")
    assert out["answer"]["state"] == "done" and "صدا" not in out["answer"]["show_md"]
    talk["voice"].unavailable = False
