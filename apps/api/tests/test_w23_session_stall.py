"""W23 (2026-11-11): an open, unfinished session never goes silent.

The incident (production, 2026-11-10 18:58 UTC): the owner's «با من» order session (Pro-Chart's
daily reels, a plan of 18 tasks, at task 3) went silent for twelve hours. The holder wrote
«پیش‌نویس متن … از ChatGPT خواسته شد و در صف است» and nothing happened after it; the app read
«آرام» and offered nothing to press.

A. a pending outside call is someone working (a Worker of kind `call`, mood `working`); past
   its deadline it is not live, the holder is woken with an explicit turn that names it, and a
   woken run that only narrates makes the session `stuck` at once (one sentence, one
   notification); the wakes are capped; «ادامه بده» resets the count;
B. the root of an order whose plan still has open tasks is not delivered by `deliver`, is opened
   again when another path delivered it, and is delivered once every task is done; a `ready`
   session reads `waiting` («منتظر تأیید تو»), never «آرام»;
C. a voice job (speech.make) is pending work and wakes its caller when it ends;
D. the order tick survives a broken order, runs newest first and reaps a stalled work run;
E. the owner is «تو» in the session («سؤال از تو»), and quota codes are said in plain words.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api import audit
from hq_api.domain import direct as DR
from hq_api.domain import no_silence as NS
from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import session_activity as SA
from hq_api.domain import sessions as SE
from hq_api.domain import speech_make as SM
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.lines.base import StepFailed
from hq_api.worker import schedules

from .conftest import agent_headers
from .test_p21_routing_orders import all_tx, deliver, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued
from .test_w11_activity import fake_run, runs_with_reason


# ------------------------------------------------------------------ helpers --
async def an_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    *,
    tasks: int = 18,
    done: int = 2,
    pace: str = "step",
) -> dict[str, Any]:
    """An order with a plan of `tasks` tasks, the first `done` of them ticked, its first run
    gone (refused) so a wake can queue one."""
    company = await new_company()
    out = await post_order(client, owner, WORK_TEXT.format(co=company["code"], w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    holder, root_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root_ref)
    h = await agent_headers(holder)
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack", headers=h,
        json={"plan_fa": "برنامه‌ی ریلز روزانه",
              "steps": [f"گام شماره‌ی {i} ریلز" for i in range(1, tasks + 1)]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    if done:
        r = await client.post(
            f"/internal/v1/orders/{ref}/progress", headers=h,
            json={"step_fa": "گام‌های اول انجام شد", "done": list(range(1, done + 1))},
        )  # fmt: skip
        assert r.status_code == 200, r.text
    await refuse_queued(su, root_ref)
    await su.execute("UPDATE owner.orders SET pace = $2 WHERE ref = $1", ref, pace)
    return {
        "company": company, "ref": ref, "holder": holder, "root_ref": root_ref, "wid": wid,
        "h": h, "talk_ref": out.get("talk_ref"),
    }  # fmt: skip


async def narrate(client: httpx.AsyncClient, s: dict[str, Any], text: str) -> None:
    """The holder's `order.progress` (a step of the story: it moves the clock)."""
    r = await client.post(
        f"/internal/v1/orders/{s['ref']}/progress",
        headers=await agent_headers(s["holder"]),
        json={"step_fa": text},
    )
    assert r.status_code == 200, r.text


async def queued_call(su: Any, s: dict[str, Any], *, seat: str = "content_draft") -> Any:
    """A ChatGPT web call the holder's run made for the order's root (as substitute.call stores
    it), still in the player's queue."""
    return await su.fetchval(
        """INSERT INTO substitutes.calls (company_id, player, seat, via, task, state, caller_kind,
               caller_code, purpose_kind, purpose_ref, input_md, timeout_s, day, month_key)
           VALUES ($1, 'gpt', $2, 'web', 'text', 'queued', 'agent', $3, 'caller_work', $4, 'x', 300,
                   current_date, '1405-08') RETURNING id""",
        s["company"]["id"], seat, s["holder"], str(s["wid"]),
    )  # fmt: skip


async def activity(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/orders/{ref}/activity", headers=owner)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def idle_for(su: Any, ref: str, minutes: int) -> None:
    await su.execute(
        """UPDATE owner.order_reports SET last_step_at = now() - make_interval(mins => $2)
           WHERE ref = $1""",
        ref,
        minutes,
    )


async def backdate(su: Any, ref: str, hours: int) -> None:
    """The session began `hours` ago (its report's receipt time is immutable: past the trigger)."""
    async with su.transaction():
        await su.execute("SET LOCAL session_replication_role = replica")
        await su.execute(
            """UPDATE owner.order_reports SET created_at = created_at - make_interval(hours => $2)
               WHERE ref = $1""",
            ref,
            hours,
        )


async def start_run(su: Any, run_id: Any, *, minutes_ago: int = 0) -> None:
    """A queued run starts (its employee runs one run at a time: the run a test's agent token
    is bound to ends first; `narrate` mints a new one)."""
    await su.execute(
        """UPDATE agents.runs o SET state = 'done', finished_at = now()
           FROM agents.runs r
           WHERE r.id = $1 AND o.employee_id = r.employee_id AND o.state = 'running'
             AND o.id <> r.id AND o.work_id IS NULL""",
        run_id,
    )
    await su.execute(
        """UPDATE agents.runs SET state = 'running', started_at = now() - make_interval(mins => $2)
           WHERE id = $1""",
        run_id,
        minutes_ago,
    )


async def end_run(su: Any, run_id: Any, company_id: Any, actions: list[dict[str, Any]]) -> None:
    """A queued run ran one step with these actions and ended `done`."""
    await start_run(su, run_id, minutes_ago=1)
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, at, summary_fa, actions)
           VALUES ($1, $2, 1, now() - interval '30 seconds', 'گزارش', $3::jsonb)""",
        run_id, company_id, json.dumps(actions),
    )  # fmt: skip
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now(), steps = 1 WHERE id = $1",
        run_id,
    )


async def pulse_of(hub: Hub, ref: str) -> SA.Pulse:
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        order = await OR.load_order(tx, ref)
        assert rep is not None and order is not None
        return await SA.read_pulse(tx, rep, await OR.tree(tx, OR.root_refs(order)), minutes=10)


async def sweep(hub: Hub, ref: str) -> list[str]:
    async with await all_tx(hub) as tx:
        return await SA.sweep(tx, ref, minutes=10)


def no_shoma(*texts: Any) -> None:
    for t in texts:
        if isinstance(t, str):
            assert "شما" not in t, t


# ========================================================== A. the incident ==
async def test_the_incident_a_queued_chatgpt_draft_never_leaves_the_session_silent(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company)
    ref, wid, co = s["ref"], s["wid"], s["company"]
    # the holder's run: it asked ChatGPT for the draft, narrated «… در صف است» and ended
    said = "پیش‌نویس متن ریلز از ChatGPT خواسته شد و در صف است"
    await fake_run(su, co, s["holder"], wid, minutes_ago=3, steps=[
        (said, [{"tool": "substitute.call", "outcome": "ok", "hint": "ChatGPT"},
                {"tool": "order.progress", "outcome": "ok"}]),
    ])  # fmt: skip
    await narrate(client, s, said)
    call = await queued_call(su, s)
    # someone works on it: ChatGPT, in its queue, with its deadline; never «آرام»
    act = await activity(client, owner, ref)
    assert act["mood"] == "working" and act["stuck_fa"] is None, act
    [w] = [x for x in act["working"] if x["kind"] == "call"]
    assert w["who_fa"] == "ChatGPT" and w["doing_fa"] == "در صف ChatGPT: پیش‌نویس متن", w
    assert w["cap_s"] == 900 and w["step"] == 0 and w["company_fa"]
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "moving", rep["session"]
    assert "ChatGPT" in rep["session"]["reason_fa"]
    assert await sweep(hub, ref) == []  # live: nobody is woken
    # past its deadline builder A's reaper ends it `failed` `not_claimed` (simulated here)
    await su.execute(
        """UPDATE substitutes.calls SET state = 'failed', state_reason = 'not_claimed',
               finished_at = now(), input_md = NULL WHERE id = $1""",
        call,
    )
    await idle_for(su, ref, 11)
    act = await activity(client, owner, ref)
    assert act["working"] == [] and act["mood"] in ("idle", "stuck"), act
    assert await sweep(hub, ref) == ["idle_wake"]
    [woke] = await runs_with_reason(su, s["root_ref"], "session_idle:")
    assert woke["state"] == "queued"
    # the woken run's brief: an explicit turn, first; the dead call named; task 3 to do now
    await start_run(su, woke["id"])
    async with await all_tx(hub) as tx:
        d = await OT.dialogue(tx, wid)
        direct = await DR.server_for(tx) is not None
    assert d is not None and next(iter(d)) == "wake", list(d)[:3]
    assert d["wake"].startswith("WOKEN BY THE HUB (1 of at most 2)"), d["wake"]
    assert "Continue task 3 now" in d["wake"] and "order.ask" in d["wake"]
    assert "ChatGPT «پیش‌نویس متن» (not_claimed)" in d["wake"]
    assert "3 «گام شماره‌ی 3 ریلز»" in d["wake"] and "Do not only narrate" in d["wake"]
    assert d["ended_without_answer"][0]["why"] == "not_claimed"
    assert d["ended_without_answer"][0]["who"] == "ChatGPT" and "waiting_on" not in d
    # the brief says the session is direct only when the workshop can hold a direct turn now
    assert d["direct"] is direct and ("direct_rule" in d) is direct
    assert "`queued`" in d["async_rule"] and "has NOT finished" in d["async_rule"]
    # the woken run only narrates: stuck at once, one sentence, one notification
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE id = $1", woke["id"]
    )
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, at, summary_fa, actions)
           VALUES ($1, $2, 1, now(), 'پیش‌نویس هنوز در صف است',
                   '[{"tool": "order.progress", "outcome": "ok"}]'::jsonb)""",
        woke["id"], co["id"],
    )  # fmt: skip
    await narrate(client, s, "پیش‌نویس هنوز در صف است")
    assert await sweep(hub, ref) == ["stuck"]
    assert await sweep(hub, ref) == []  # once
    act = await activity(client, owner, ref)
    assert act["mood"] == "stuck" and act["working"] == [], act
    assert "ChatGPT" in act["stuck_fa"] and "نوبتش نرسید" in act["stuck_fa"], act["stuck_fa"]
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "stuck" and rep["steps"][-1]["what_fa"].startswith("گیر کرد")
    notes = await su.fetch(
        """SELECT title_fa, body_fa FROM notify.notifications
           WHERE link_kind = 'order' AND link_ref = $1 AND source_code = 'sessions'""",
        ref,
    )
    assert len(notes) == 1 and "ادامه بده" in notes[0]["body_fa"], notes
    no_shoma(notes[0]["title_fa"], act["stuck_fa"])
    # no further wake: they are spent until the owner speaks
    await idle_for(su, ref, 30)
    assert await sweep(hub, ref) == []
    assert len(await runs_with_reason(su, s["root_ref"], "session_idle:")) == 1
    # «ادامه بده» resets the count: the holder now, and later the idle wake again
    r = await client.post(
        f"/api/v1/orders/{ref}/nudge", headers={**owner, "Idempotency-Key": str(uuid.uuid4())}
    )
    assert r.status_code == 200, r.text
    assert len(await runs_with_reason(su, s["root_ref"], "nudge:")) == 1
    p = await pulse_of(hub, ref)
    assert p.wakes == 0 and not p.spent and p.live
    await refuse_queued(su, s["root_ref"])
    await idle_for(su, ref, 11)
    p = await pulse_of(hub, ref)  # idle again: no wake spent since his word, not stuck
    assert not p.live and p.wakes == 0 and not p.spent and p.stuck_fa is None


async def test_two_idle_wakes_that_led_nowhere_make_it_stuck_with_the_plan_named(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=3, done=0, pace="auto")
    ref, co = s["ref"], s["company"]
    await backdate(su, ref, 2)
    await narrate(client, s, "سه موضوع پیدا کردم و دارم متن را آماده میکنم")
    # wake 1 (25 minutes ago) read a site and wrote nothing
    await fake_run(su, co, s["holder"], s["wid"], reason=f"session_idle:{ref}", minutes_ago=25,
                   steps=[("سایت را خواندم", [{"tool": "web.read", "outcome": "ok"}])])  # fmt: skip
    await idle_for(su, ref, 11)
    p = await pulse_of(hub, ref)
    assert p.wakes == 1 and not p.spent and p.stuck_fa is None
    assert await sweep(hub, ref) == ["idle_wake"]  # wake 2 of 2
    wakes = await runs_with_reason(su, s["root_ref"], "session_idle:")
    assert len(wakes) == 2
    await end_run(su, wakes[-1]["id"], co["id"], [{"tool": "web.read", "outcome": "ok"}])
    # the cap: stuck at once, no third wake; the sentence says what was last done and what is left
    assert await sweep(hub, ref) == ["stuck"]
    p = await pulse_of(hub, ref)
    assert p.spent and p.wakes == 2
    assert p.stuck_fa is not None and p.stuck_fa.startswith("مسئول 2 بار دوباره سر کار آمد")
    assert "سه موضوع پیدا کردم" in p.stuck_fa and "کار 1 («گام شماره‌ی 1 ریلز»)" in p.stuck_fa
    await idle_for(su, ref, 40)
    assert await sweep(hub, ref) == []
    assert len(await runs_with_reason(su, s["root_ref"], "session_idle:")) == 2
    # the talk-loop count sees an idle wake that only reported (its own step moved the clock)
    narrated = await fake_run(
        su, co, s["holder"], s["wid"], reason=f"session_idle:{ref}", minutes_ago=2,
        steps=[("در صف است", [{"tool": "order.progress", "outcome": "ok"}])],
    )  # fmt: skip
    await narrate(client, s, "در صف است")
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        order = await OR.load_order(tx, ref)
        assert rep is not None and order is not None
        works = await OR.tree(tx, OR.root_refs(order))
        n = await OR.idle_runs(tx, rep, works, order["created_at"])
    assert n >= 1, n
    del narrated


# ================================================== B. the plan keeps it open ==
async def test_a_root_delivered_with_open_plan_tasks_stays_open_until_the_plan_is_done(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    ref, wid = s["ref"], s["wid"]
    r = await deliver(client, s["holder"], wid, "پیش‌نویس ریلز اول")
    assert r.status_code == 200, r.text
    assert r.json()["work"]["status"] == "in_progress"  # the plan has two open tasks
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] != "ready" and rep["state"] != "delivered", rep["session"]
    assert any(o["title_fa"] == "پیش‌نویس ریلز اول" for o in rep["outputs"])  # listed as output
    # (a deliver a work-scoped view makes alone, without the order in sight, is as before)
    async with hub.db.tx([s["company"]["id"]]) as tx:
        assert await W.plan_open(tx, s["root_ref"]) is False
    async with await all_tx(hub) as tx:
        assert await W.plan_open(tx, s["root_ref"]) is True
    # every task done and nothing runs: the sweep delivers the root, the session is ready
    r = await client.post(f"/internal/v1/orders/{ref}/progress", headers=s["h"],
                          json={"step_fa": "هر دو کار انجام شد", "done": [1, 2]})  # fmt: skip
    assert r.status_code == 200, r.text
    assert await sweep(hub, ref) == ["plan_done"]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "delivered"
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "ready" and rep["steps"][-1]["what_fa"] == SA.PLAN_DONE_FA
    no_shoma(rep["session"]["reason_fa"], rep["brief"]["need_fa"])
    # a ready session waits for the owner: never «آرام»
    act = await activity(client, owner, ref)
    assert act["mood"] == "waiting" and act["waiting_fa"] == SA.READY_WAITING_FA, act
    assert await sweep(hub, ref) == []


async def test_a_root_closed_while_the_plan_is_open_is_opened_again_and_its_holder_woken(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=3, done=1, pace="auto")
    ref, wid = s["ref"], s["wid"]
    r = await deliver(client, s["holder"], wid, "خروجی میانی")
    assert r.status_code == 200 and r.json()["work"]["status"] == "in_progress"

    async def force_delivered() -> None:  # another path delivered it (a council, an old hub)
        async with await all_tx(hub) as tx:
            w = await W.load(tx, wid)
            assert (
                await W.set_status(
                    tx, w, "delivered", plan_open=False, delivered_at=datetime.now(UTC)
                )
                == "delivered"
            )

    await force_delivered()
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] != "ready", rep["session"]  # the plan is not done
    act = await activity(client, owner, ref)
    assert act["waiting_fa"] != SA.READY_WAITING_FA
    assert await sweep(hub, ref) == ["reopened", "idle_wake"]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "in_progress"
    rep = await report(client, owner, ref)
    assert any(x["what_fa"] == SA.REOPENED_FA.format(n=2) for x in rep["steps"]), rep["steps"]
    assert len(await runs_with_reason(su, s["root_ref"], "session_idle:")) == 1
    # «ادامه بده» on a root closed that way opens it too, and wakes its holder
    await refuse_queued(su, s["root_ref"])
    await force_delivered()
    r = await client.post(
        f"/api/v1/orders/{ref}/nudge", headers={**owner, "Idempotency-Key": str(uuid.uuid4())}
    )
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "in_progress"
    assert len(await runs_with_reason(su, s["root_ref"], "nudge:")) == 1


def test_the_badge_and_the_mood_of_an_unfinished_plan_and_an_outside_call() -> None:
    now = datetime.now(UTC)
    rep = {"closed_at": None, "ended_at": None, "turn": None, "talk_stopped_at": None,
           "steps": [{"who_fa": "مدیرعامل", "what_fa": "خروجی"}], "last_step_at": now,
           "acked_at": None, "created_at": now - timedelta(minutes=5)}  # fmt: skip
    roots = [{"is_root": True, "status": "delivered"}]
    calm = SA.Pulse(live=False, clock=now, idle=timedelta(0), woken=None, stuck_fa=None)
    assert SE.badge_of(rep, "delivered", roots, [], decision_pending=False, pulse=calm) == (
        "ready",
        "کار تحویل شد؛ منتظر تأیید و بستن توست",
    )
    left = SA.Pulse(live=False, clock=now, idle=timedelta(0), woken=None, stuck_fa=None,
                    open_tasks=[{"n": 3, "title_fa": "صدا", "state": "todo"}])  # fmt: skip
    assert (
        SE.badge_of(rep, "delivered", roots, [], decision_pending=False, pulse=left)[0] == "moving"
    )
    call = SA.Worker(who_fa="ChatGPT", company_fa="پروچارت", work_title_fa="ریلز",
                     started_at=now, step=0, doing_fa="در صف ChatGPT: پیش‌نویس متن",
                     kind="call", cap_s=900)  # fmt: skip
    assert SA.mood_of([call], None, None) == "working"
    assert SA.mood_of([], SA.READY_WAITING_FA, None) == "waiting"


# ======================================================== C. a voice job ==
async def test_a_voice_job_is_pending_work_and_wakes_its_caller_when_it_ends(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    ref, co = s["ref"], s["company"]
    job = str(uuid.uuid4())
    # the holder's run asked for the narration (its first answer: `running` with the job) and ended
    await fake_run(su, co, s["holder"], s["wid"], minutes_ago=3, steps=[
        ("صدای گوینده را خواستم", [{"tool": "speech.make", "outcome": "ok", "ref": job}]),
    ])  # fmt: skip
    async with hub.db.tx([co["id"]]) as tx:  # the job's start, as routes/speech records it
        await audit.record(tx, SM.SERVICE, company_id=co["id"], action="speech.make",
                           action_class="A1", target_kind="speech", target_ref=job,
                           summary="AI Studio Kore, 40 chars")  # fmt: skip
    act = await activity(client, owner, ref)
    [v] = [x for x in act["working"] if x["kind"] == "call"]
    assert v["who_fa"] == SA.VOICE_WHO_FA and v["doing_fa"] == "صدا را آماده میکند", v
    assert v["cap_s"] == int(SA.VOICE_DEADLINE.total_seconds()) and act["mood"] == "working"
    assert await sweep(hub, ref) == []

    # it ends without a voice (the recipe's own time cap: AI Studio's sign-in is not touched, so
    # no other test reads it signed out): recorded with the job, and the caller woken
    async def too_slow(*_a: Any, **_k: Any) -> Any:
        raise StepFailed("طول کشید", code="timeout")

    monkeypatch.setattr(SM.tts, "speak", too_slow)
    got = await SM.make(hub, {"job": job, "company_id": str(co["id"]), "company": co["code"],
                              "by": s["holder"], "text": "سلام", "voice": "Kore", "style": ""})  # fmt: skip
    assert got["state"] == "failed" and got["code"] == "timeout"
    made = await su.fetchval(
        """SELECT summary FROM audit.entries WHERE company_id = $1 AND action = 'speech.made'
           ORDER BY at DESC LIMIT 1""",
        co["id"],
    )
    assert job in made and made.startswith(s["holder"])
    woken = await runs_with_reason(su, s["root_ref"], "speech_failed:")
    assert [w["reason"] for w in woken] == [f"speech_failed:{job}"]
    assert (
        SA.start_text(f"speech_failed:{job}", "")
        == "ساخت صدا به نتیجه نرسید؛ با بقیه‌ی کار ادامه میدهد"
    )
    async with await all_tx(hub) as tx:
        order = await OR.load_order(tx, ref)
        assert order is not None
        works = await OR.tree(tx, OR.root_refs(order))
        assert await SA.pending_outside(tx, works) == []
        [ended] = await SA.ended_outside(tx, works, datetime.now(UTC) - timedelta(minutes=5))
    assert ended["who_fa"] == SA.VOICE_WHO_FA and ended["why_fa"] == "جوابش طول کشید"
    # a voice whose run still works is not woken: the run asks again itself
    assert (
        await SM.wake_caller(hub, {"job": str(uuid.uuid4()), "by": s["holder"]}, done=True) is None
    )


# =============================================================== D. the tick ==
async def test_the_order_tick_survives_a_broken_order_runs_newest_first_and_reaps_a_stalled_run(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    b = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    await idle_for(su, a["ref"], 11)
    await idle_for(su, b["ref"], 11)
    # a work run whose worker is gone: running 40 minutes without a step (a colleague of a's
    # holder: the holder's own test token holds a running run)
    stalled = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               queued_at, started_at)
           SELECT $1, e.id, $3, 'work', 'stalled', 'running', now() - interval '41 minutes',
                  now() - interval '40 minutes'
           FROM core.employees e
           WHERE e.company_id = $1 AND e.code <> $2 AND e.status = 'active'
             AND NOT EXISTS (SELECT 1 FROM agents.runs x WHERE x.employee_id = e.id
                               AND x.state = 'running')
           ORDER BY e.code LIMIT 1 RETURNING id""",
        a["company"]["id"], a["holder"], a["wid"],
    )  # fmt: skip
    assert stalled is not None
    seen: list[str] = []
    real = OR.timers

    async def timers(tx: Any, settings: Any, ref: str) -> list[str]:
        seen.append(ref)
        if ref == a["ref"]:
            raise RuntimeError("a broken order")
        return await real(tx, settings, ref)

    monkeypatch.setattr(OR, "timers", timers)
    tick = await OR.tick(wk["hub"])
    assert a["ref"] in tick["failed"] and b["ref"] not in tick["failed"], tick["failed"]
    # the broken order's timers failed; its sweep and the other order still ran
    assert tick["fired"].get(a["ref"]) == ["idle_wake"], tick["fired"].get(a["ref"])
    assert tick["fired"].get(b["ref"]) == ["idle_wake"], tick["fired"].get(b["ref"])
    assert seen.index(b["ref"]) < seen.index(a["ref"])  # newest first
    assert tick["reaped"] >= 1
    row = await su.fetchrow("SELECT state, error_code FROM agents.runs WHERE id = $1", stalled)
    assert (row["state"], row["error_code"]) == ("failed", "runtime_error")
    # the tick is its own schedule, every 2 minutes, not the maintenance chain's 13th step
    fixed = {d.id: d for d in schedules.fixed(datetime.now(UTC).time(), "Asia/Tehran")}
    assert fixed[schedules.ORDER_TICK].workflow == "OrderTick"
    out = await wk["client"].execute_workflow(
        "OrderTick", id=f"ot-{uuid.uuid4()}", task_queue=wk["tq"]
    )
    assert "orders" in out and "error" not in out, out


# ======================================================== E. the owner's words ==
async def test_the_owner_is_tu_in_the_session(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    r = await client.post(f"/internal/v1/orders/{s['ref']}/ask", headers=s["h"],
                          json={"question_fa": "کدام موضوع اول؟"})  # fmt: skip
    assert r.status_code == 200, r.text
    rep = await report(client, owner, s["ref"])
    assert rep["steps"][-1]["what_fa"] == "سؤال از تو: کدام موضوع اول؟"
    assert rep["brief"]["need_fa"] == "جواب تو"
    if rep.get("conversation_ref"):
        show = await su.fetchval(
            """SELECT t.show_md FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
               WHERE c.ref = $1 ORDER BY t.n DESC LIMIT 1""",
            rep["conversation_ref"],
        )
        assert show.startswith("**سؤال از تو** · "), show
    title = await su.fetchval(
        """SELECT title_fa FROM notify.notifications WHERE link_ref = ANY($1::text[])
           AND source_code = 'orders' ORDER BY created_at DESC LIMIT 1""",
        [s["ref"], rep.get("conversation_ref") or s["ref"]],
    )
    assert title.startswith("نوبت توست"), title
    for text in (SA.start_text("owner_reply:F-1", ""), SA.start_text("nudge:F-1", ""),
                 SA.start_text("owner_turn_over:F-1", ""), SA.DIRECT_DOING_FA,
                 SA.UNKNOWN_WHY_FA, SA.STUCK_TITLE_FA, SA.TOOLS_FA["order.ask"][0],
                 SA.END_WHY_FA["owner_turn"], *[a + b for a, b in NS.RUN_WHY_FA.values()]):  # fmt: skip
        no_shoma(text)


def test_quota_codes_are_said_in_plain_words_with_the_reset_time() -> None:
    zone = ZoneInfo("Asia/Tehran")
    now = datetime(2026, 11, 11, 20, 0, tzinfo=UTC)  # 23:30 in Tehran
    at = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)  # 03:30 the next day there
    assert NS.when_fa(at, zone, now) == "از فردا ساعت 03:30"
    assert NS.when_fa(now + timedelta(minutes=20), zone, now) == "از ساعت 23:50"
    assert NS.when_fa(now - timedelta(minutes=1), zone, now) is None
    assert NS.when_fa(now + timedelta(days=3), zone, now) == "از 3 روز دیگر، ساعت 23:30"
    assert NS.parse_at("120", now) == now + timedelta(seconds=120)
    assert NS.parse_at("2026-11-12T00:00:00Z") == at and NS.parse_at(None) is None
    assert NS.quota_why_fa("usage_limit", "از ساعت 03:30") == (
        "اکانت‌های Claude پر است؛ از ساعت 03:30 دوباره کار میکند."
    )
    for code in (
        "quota_exhausted",
        "usage_limit",
        "billing_error",
        "circuit_open",
        "quota_throttled",
    ):
        assert NS.quota_why_fa(code) and "{" not in (NS.quota_why_fa(code) or "")
        line = SA.end_text("failed", code, reset_fa="از ساعت 03:30")
        assert line is not None and line.startswith("کار متوقف شد: ") and "03:30" in line, line
        assert SA.end_text("failed", code) != SA.end_text("failed", "weird_code")
    assert NS.quota_why_fa("daily_cap") is None


async def test_a_run_a_quota_stopped_says_in_the_session_when_it_works_again(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    s = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    co = s["company"]
    emp = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", s["holder"])
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               error_code, queued_at, started_at, finished_at, steps)
           VALUES ($1, $2, $3, 'work', 'quota', 'failed', 'usage_limit', now() - interval '3 minutes',
                   now() - interval '3 minutes', now() - interval '1 minute', 1) RETURNING id""",
        co["id"], emp, s["wid"],
    )  # fmt: skip
    at = datetime.now(UTC) + timedelta(hours=2)
    # the runner keeps the reset the router gave on the run's last step (usage.retry_at)
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, at, summary_fa, actions, usage)
           VALUES ($1, $2, 1, now() - interval '2 minutes', 'شروع', '[]'::jsonb, $3::jsonb)""",
        rid, co["id"], json.dumps({"code": "usage_limit", "retry_at": at.isoformat()}),
    )  # fmt: skip
    act = await activity(client, owner, s["ref"])
    [end] = [ln for ln in act["last"] if ln["id"] == f"{rid}:end"]
    async with await all_tx(hub) as tx:
        zone = await SA.owner_zone(tx)
    when = NS.when_fa(at, zone, datetime.now(UTC))
    assert end["text_fa"] == f"کار متوقف شد: اکانت‌های Claude پر است؛ {when} دوباره کار میکند.", end
    no_shoma(end["text_fa"])
    # a step whose action did not happen shows the tools' real outcome, not the model's claim
    assert SA.step_text("پیش‌نویس آماده شد", [{"tool": "substitute.call", "outcome": "denied",
                                               "hint": "ChatGPT"}]) == "از ChatGPT پرسید (نشد)"  # fmt: skip


async def test_a_requeued_run_reads_as_the_wake_or_the_word_it_retries(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """The worker re-queues a failed run with `retry:` / `requeue:` in front of its reason
    (stacked when it fails again): it is still the owner's word or the idle wake it retries."""
    assert OR.base_reason("requeue:retry:requeue:owner_reply:F-0011") == "owner_reply:F-0011"
    assert OR.base_reason("session_idle:F-0011") == "session_idle:F-0011"
    assert OR.base_reason(None) == ""
    assert SA.start_text("requeue:owner_reply:F-0011", "") == SA.start_text("owner_reply:F-1", "")
    assert SA.start_text("retry:requeue:session_idle:F-0011", "کار") == "دوباره سر کار آمد"
    now = datetime.now(UTC)
    waiting = {"since": now - timedelta(minutes=5)}
    assert OR.answers_owner({"reason": "requeue:owner_reply:F-1", "queued_at": now}, waiting)
    assert not OR.answers_owner({"reason": "requeue:work:W-1", "queued_at": now}, waiting)
    s = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    ref, co, wid = s["ref"], s["company"], s["wid"]
    await backdate(su, ref, 2)
    # the owner's word, its run failed and was re-queued: the word is the first run's time
    said = await fake_run(su, co, s["holder"], wid, reason=f"owner_reply:{ref}", minutes_ago=40)
    await fake_run(su, co, s["holder"], wid, reason=f"requeue:owner_reply:{ref}", minutes_ago=35)
    said_at = await su.fetchval("SELECT queued_at FROM agents.runs WHERE id = $1", said)
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        assert await SA.owner_since(tx, rep, [wid]) == said_at
    # an idle wake failed on the quota; its re-queue only narrated: one wake, spent, stuck
    await fake_run(su, co, s["holder"], wid, reason=f"session_idle:{ref}", state="failed",
                   error="usage_limit", minutes_ago=30)  # fmt: skip
    await fake_run(su, co, s["holder"], wid, reason=f"requeue:session_idle:{ref}", minutes_ago=20,
                   steps=[("در صف است", [{"tool": "order.progress", "outcome": "ok"}])])  # fmt: skip
    await idle_for(su, ref, 15)
    p = await pulse_of(hub, ref)
    assert p.wakes == 1 and p.spent, p
    assert p.stuck_fa is not None and p.stuck_fa.startswith("مسئول 1 بار"), p.stuck_fa
    async with await all_tx(hub) as tx:
        rep = await OR.ensure(tx, ref)
        order = await OR.load_order(tx, ref)
        assert rep is not None and order is not None
        works = await OR.tree(tx, OR.root_refs(order))
        assert await OR.idle_runs(tx, rep, works, order["created_at"]) >= 1
    # a wake that failed (a quota, a model error) is the worker's to bring back: not spent
    t = await an_order(client, owner, su, new_company, tasks=2, done=0, pace="auto")
    await backdate(su, t["ref"], 2)
    await fake_run(su, t["company"], t["holder"], t["wid"], reason=f"session_idle:{t['ref']}",
                   state="failed", error="usage_limit", minutes_ago=20)  # fmt: skip
    await idle_for(su, t["ref"], 15)
    p = await pulse_of(hub, t["ref"])
    assert p.wakes == 1 and not p.spent and p.stuck_fa is None, p
