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

import ast
import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from hq_api.domain import substitutes as S
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
    is bound to ends first; the started run takes the token, so `narrate` speaks inside it)."""
    await su.execute(
        """UPDATE agents.runs o SET state = 'done', finished_at = now()
           FROM agents.runs r
           WHERE r.id = $1 AND o.employee_id = r.employee_id AND o.state = 'running'
             AND o.id <> r.id AND o.work_id IS NULL""",
        run_id,
    )
    await su.execute(
        """UPDATE agents.runs SET state = 'running', started_at = now() - make_interval(mins => $2),
               token_expires_at = now() + interval '1 hour'
           WHERE id = $1""",
        run_id,
        minutes_ago,
    )


async def finish_run(su: Any, run_id: Any, company_id: Any, actions: list[dict[str, Any]]) -> None:
    """A running run wrote one step with these actions and ended `done`."""
    await su.execute(
        """INSERT INTO agents.steps (run_id, company_id, n, at, summary_fa, actions)
           VALUES ($1, $2, 1, now() - interval '20 seconds', 'گزارش', $3::jsonb)""",
        run_id, company_id, json.dumps(actions),
    )  # fmt: skip
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now(), steps = 1 WHERE id = $1",
        run_id,
    )


async def pass_time(su: Any, s: dict[str, Any], minutes: int) -> None:
    """`minutes` pass for this session: every time it keeps moves back by as much (its report's
    clock and steps, its works' runs and their steps, its outside calls, its notifications, its
    plan). Immutable times are moved past their triggers, as the clock does it."""
    ids = [
        r["id"]
        for r in await su.fetch(
            """WITH RECURSIVE t(id) AS (
                   SELECT id FROM work.work WHERE ref = $1
                   UNION SELECT c.id FROM work.work c JOIN t
                       ON c.parent_id = t.id OR c.requested_by_work_id = t.id)
               SELECT id FROM t""",
            s["root_ref"],
        )
    ]
    m = timedelta(minutes=minutes)
    steps = json.loads(
        await su.fetchval("SELECT steps FROM owner.order_reports WHERE ref = $1", s["ref"]) or "[]"
    )
    for st in steps:
        st["at"] = (datetime.fromisoformat(str(st["at"])) - m).isoformat()
    back = "make_interval(mins => $2)"
    async with su.transaction():
        await su.execute("SET LOCAL session_replication_role = replica")
        await su.execute(
            f"""UPDATE agents.runs SET queued_at = queued_at - {back},
                   created_at = created_at - {back}, started_at = started_at - {back},
                   finished_at = finished_at - {back}, dispatched_at = dispatched_at - {back}
               WHERE work_id = ANY($1::uuid[])""",
            ids, minutes,
        )  # fmt: skip
        await su.execute(
            f"""UPDATE agents.steps SET at = at - {back}
               WHERE run_id IN (SELECT id FROM agents.runs WHERE work_id = ANY($1::uuid[]))""",
            ids, minutes,
        )  # fmt: skip
        await su.execute(
            f"""UPDATE substitutes.calls SET created_at = created_at - {back},
                   claimed_at = claimed_at - {back}, finished_at = finished_at - {back}
               WHERE purpose_kind = 'caller_work' AND purpose_ref = ANY($1::text[])""",
            [str(i) for i in ids], minutes,
        )  # fmt: skip
        await su.execute(
            f"""UPDATE notify.notifications SET created_at = created_at - {back}
               WHERE link_ref = ANY($1::text[])""",
            [x for x in (s["ref"], s.get("talk_ref")) if x], minutes,
        )  # fmt: skip
        await su.execute(
            f"""UPDATE owner.session_tasks SET updated_at = updated_at - {back},
                   created_at = created_at - {back}
               WHERE ref = $1""",
            s["ref"], minutes,
        )  # fmt: skip
        await su.execute(
            f"""UPDATE owner.order_reports SET last_step_at = last_step_at - {back},
                   acked_at = acked_at - {back}, created_at = created_at - {back},
                   steps = $3::jsonb
               WHERE ref = $1""",
            s["ref"], minutes, json.dumps(steps, ensure_ascii=False),
        )  # fmt: skip


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
    wk: dict[str, Any],
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
    assert w["cap_s"] >= 900 and w["step"] == 0 and w["company_fa"]  # a busy lane: later
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "moving", rep["session"]
    assert "ChatGPT" in rep["session"]["reason_fa"]
    assert await sweep(wk["hub"], ref) == []  # live: nobody is woken
    # past its deadline builder A's reaper ends it `failed` `not_claimed` (simulated here)
    await su.execute(
        """UPDATE substitutes.calls SET state = 'failed', state_reason = 'not_claimed',
               finished_at = now(), input_md = NULL WHERE id = $1""",
        call,
    )
    await idle_for(su, ref, 11)
    act = await activity(client, owner, ref)
    assert act["working"] == [] and act["mood"] in ("idle", "stuck"), act
    assert await sweep(wk["hub"], ref) == ["idle_wake"]
    [woke] = await runs_with_reason(su, s["root_ref"], "session_idle:")
    assert woke["state"] == "queued"
    # the woken run's brief: an explicit turn, first; the dead call named; task 3 to do now
    await start_run(su, woke["id"])
    async with await all_tx(hub) as tx:
        d = await OT.dialogue(tx, wid)
        direct = await DR.server_for(tx) is not None
    assert d is not None and next(iter(d)) == "wake", list(d)[:3]
    assert d["wake"].startswith("WOKEN BY THE HUB (1 of at most 2)"), d["wake"]
    # «با من» and task 3 not started: never «start it», but show and ask
    assert "STEP BY STEP" in d["wake"] and "Do NOT start task 3" in d["wake"], d["wake"]
    assert "order.ask" in d["wake"] and "«گام شماره‌ی 3 ریلز»" in d["wake"]
    assert "ChatGPT «پیش‌نویس متن» (not_claimed)" in d["wake"]
    assert "Do not only narrate" in d["wake"]
    assert d["ended_without_answer"][0]["why"] == "not_claimed"
    assert d["ended_without_answer"][0]["who"] == "ChatGPT" and "waiting_on" not in d
    # direct by rule always; whether the workshop can hold a direct turn now, apart
    assert d["direct"] is True and "direct_rule" in d and d["direct_turn"] is direct
    # the owner's talk about the order never reads the hub's wake
    async with await all_tx(hub) as tx:
        talk = await OT.talk_brief(tx, ref)
    assert talk is not None and "wake" not in talk and talk["ended_without_answer"]
    assert "`queued`" in d["async_rule"] and "has NOT finished" in d["async_rule"]
    # the woken run only narrates (inside the run) and ends: stuck at once, one notification
    await narrate(client, s, "پیش‌نویس هنوز در صف است")
    await finish_run(su, woke["id"], co["id"], [{"tool": "order.progress", "outcome": "ok"}])
    assert await sweep(wk["hub"], ref) == ["stuck"]
    assert await sweep(wk["hub"], ref) == []  # once
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
    assert await sweep(wk["hub"], ref) == []
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


async def test_the_incident_through_the_real_reaper_the_reply_wakes_first_then_two_wakes_then_stuck(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """The same stall with builder A's real reaper: the call ends through `_applied`, the session
    hears it in one line and the holder gets a reply work, whose run comes before any idle wake."""
    s = await an_order(client, owner, su, new_company)
    ref, wid, co = s["ref"], s["wid"], s["company"]
    said = "پیش‌نویس متن ریلز از ChatGPT خواسته شد و در صف است"
    await fake_run(su, co, s["holder"], wid, minutes_ago=3, steps=[
        (said, [{"tool": "substitute.call", "outcome": "ok", "hint": "ChatGPT"},
                {"tool": "order.progress", "outcome": "ok"}]),
    ])  # fmt: skip
    await narrate(client, s, said)
    call = await queued_call(su, s)
    # well past any deadline (whatever it counts from): the reaper ends it and delivers its end
    async with await all_tx(hub) as tx:
        assert await S.expire_stale(tx, hub, datetime.now(UTC) + timedelta(hours=6)) >= 1
    row = await su.fetchrow(
        "SELECT state, delivered_at, reply_work_id FROM substitutes.calls WHERE id = $1", call
    )
    assert row["state"] in ("failed", "skipped") and row["delivered_at"] is not None, dict(row)
    assert row["reply_work_id"] is not None
    assert s["talk_ref"], "every order opens its talk on routing"
    line = await su.fetchval(
        """SELECT t.say_fa FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE c.ref = $1 ORDER BY t.n DESC LIMIT 1""",
        s["talk_ref"],
    )
    assert "ChatGPT جواب نداد" in line, line
    reply = await su.fetchrow(
        "SELECT id, ref, requested_by_work_id FROM work.work WHERE id = $1", row["reply_work_id"]
    )
    assert reply["requested_by_work_id"] == wid  # in the order's tree
    [first] = await su.fetch(
        "SELECT id FROM agents.runs WHERE work_id = $1 AND state = 'queued'", reply["id"]
    )
    # the reply's queued run keeps the session live, past the idle threshold too
    await pass_time(su, s, 11)
    act = await activity(client, owner, ref)
    assert act["mood"] != "idle" and act["working"], act
    assert await sweep(wk["hub"], ref) == []
    # it ends having only narrated; the session sits idle: idle wake 1
    await end_run(su, first["id"], co["id"], [{"tool": "order.progress", "outcome": "ok"}])
    await narrate(client, s, "پیش‌نویس را خودم مینویسم")
    await pass_time(su, s, 11)
    assert await sweep(wk["hub"], ref) == ["idle_wake"]
    [w1] = await runs_with_reason(su, s["root_ref"], "session_idle:")
    await start_run(su, w1["id"])
    async with await all_tx(hub) as tx:
        root_brief = await OT.dialogue(tx, wid)
        reply_brief = await OT.dialogue(tx, reply["id"])
    # the wake instruction is the woken work's own, never another run's of the same order
    assert root_brief is not None and next(iter(root_brief)) == "wake"
    assert reply_brief is not None and "wake" not in reply_brief
    acted = [{"tool": "web.read", "outcome": "ok"}, {"tool": "order.progress", "outcome": "ok"}]
    await finish_run(su, w1["id"], co["id"], acted)
    await narrate(client, s, "منبع را خواندم")
    await pass_time(su, s, 11)
    assert await sweep(wk["hub"], ref) == ["idle_wake"]  # wake 2 of 2
    wakes = await runs_with_reason(su, s["root_ref"], "session_idle:")
    assert len(wakes) == 2
    await start_run(su, wakes[-1]["id"])
    await narrate(client, s, "باز هم منبع را خواندم")
    await finish_run(su, wakes[-1]["id"], co["id"], acted)
    assert await sweep(wk["hub"], ref) == ["stuck"]
    p = await pulse_of(hub, ref)
    assert p.stuck_fa is not None and p.stuck_fa.startswith("مسئول 2 بار"), p.stuck_fa

    async def notes() -> int:
        return int(
            await su.fetchval(
                """SELECT count(*) FROM notify.notifications
                   WHERE link_kind = 'order' AND link_ref = $1 AND source_code = 'sessions'""",
                ref,
            )
        )

    assert await notes() == 1
    await pass_time(su, s, 30)
    assert await sweep(wk["hub"], ref) == []  # no third wake, no second notification
    assert len(await runs_with_reason(su, s["root_ref"], "session_idle:")) == 2
    assert await notes() == 1


async def test_two_idle_wakes_that_led_nowhere_make_it_stuck_with_the_plan_named(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
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
    assert await sweep(wk["hub"], ref) == ["idle_wake"]  # wake 2 of 2
    wakes = await runs_with_reason(su, s["root_ref"], "session_idle:")
    assert len(wakes) == 2
    await start_run(su, wakes[-1]["id"])
    async with await all_tx(hub) as tx:
        d = await OT.dialogue(tx, s["wid"])
    assert d is not None and d["wake"].startswith("WOKEN BY THE HUB (2 of at most 2)")
    assert "Continue task 1 now" in d["wake"]  # «خودکار»: the next task, at once
    await end_run(su, wakes[-1]["id"], co["id"], [{"tool": "web.read", "outcome": "ok"}])
    # the cap: stuck at once, no third wake; the sentence says what was last done and what is left
    assert await sweep(wk["hub"], ref) == ["stuck"]
    p = await pulse_of(hub, ref)
    assert p.spent and p.wakes == 2
    assert p.stuck_fa is not None and p.stuck_fa.startswith("مسئول 2 بار دوباره سر کار آمد")
    assert "سه موضوع پیدا کردم" in p.stuck_fa and "کار 1 («گام شماره‌ی 1 ریلز»)" in p.stuck_fa
    await idle_for(su, ref, 40)
    assert await sweep(wk["hub"], ref) == []
    assert len(await runs_with_reason(su, s["root_ref"], "session_idle:")) == 2
    # real work after the last wake (a child's delivery, a reply) is judged afresh, by the idle
    # thresholds: no second «گیر کرد» at 0 minutes idle
    await narrate(client, s, "کار دو هم جلو رفت")
    p = await pulse_of(hub, ref)
    assert not p.spent and p.stuck_fa is None, p
    assert await sweep(wk["hub"], ref) == []
    assert (
        await su.fetchval(
            """SELECT count(*) FROM notify.notifications
               WHERE link_kind = 'order' AND link_ref = $1 AND source_code = 'sessions'""",
            ref,
        )
        == 1
    )
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
    wk: dict[str, Any],
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
    assert await sweep(wk["hub"], ref) == ["plan_done"]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "delivered"
    rep = await report(client, owner, ref)
    assert rep["session"]["badge"] == "ready" and rep["steps"][-1]["what_fa"] == SA.PLAN_DONE_FA
    no_shoma(rep["session"]["reason_fa"], rep["brief"]["need_fa"])
    # a ready session waits for the owner: never «آرام»
    act = await activity(client, owner, ref)
    assert act["mood"] == "waiting" and act["waiting_fa"] == SA.READY_WAITING_FA, act
    assert await sweep(wk["hub"], ref) == []


async def test_a_root_closed_while_the_plan_is_open_is_opened_again_and_its_holder_woken(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
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
    assert await sweep(wk["hub"], ref) == ["reopened", "idle_wake"]
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
    wk: dict[str, Any],
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
    assert await sweep(wk["hub"], ref) == []

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
    stalled_row = await su.fetchrow(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               queued_at, started_at)
           SELECT $1, e.id, $3, 'work', 'stalled', 'running', now() - interval '41 minutes',
                  now() - interval '40 minutes'
           FROM core.employees e
           WHERE e.company_id = $1 AND e.code <> $2 AND e.status = 'active'
             AND NOT EXISTS (SELECT 1 FROM agents.runs x WHERE x.employee_id = e.id
                               AND x.state = 'running')
           ORDER BY e.code LIMIT 1 RETURNING id, employee_id""",
        a["company"]["id"], a["holder"], a["wid"],
    )  # fmt: skip
    assert stalled_row is not None
    stalled = stalled_row["id"]
    await su.execute(
        "UPDATE core.employees SET activity = 'working' WHERE id = $1", stalled_row["employee_id"]
    )
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
    # through the runner's own end: the employee rests again and the stream hears the end
    assert await su.fetchval(
        "SELECT activity FROM core.employees WHERE id = $1", stalled_row["employee_id"]
    ) in ("error", "sleeping")
    assert (
        await su.fetchval(
            """SELECT count(*) FROM core.outbox WHERE subject LIKE '%.run.finished'
           AND payload->>'ref' = $1""",
            str(stalled),
        )
        == 1
    )
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
    assert NS.when_fa(now + timedelta(days=3), zone, now) == "۳ روز دیگر، از ساعت 23:30"
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
    # a raised card waits for the owner: not a failure, the step's own words stay
    card = [{"tool": "propose", "outcome": "pending", "code": "a3_requires_decision"}]
    assert SA.step_text("پیشنهاد انتشار را برای مُهر فرستادم", card) == (
        "پیشنهاد انتشار را برای مُهر فرستادم"
    )
    assert "(نشد)" not in SA.tools_text(card)
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
    await fake_run(su, co, s["holder"], wid, reason=f"requeue:session_idle:{ref}", minutes_ago=12,
                   steps=[("در صف است", [{"tool": "order.progress", "outcome": "ok"}])])  # fmt: skip
    await idle_for(su, ref, 11)  # its own step moved the clock, inside the run
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


# the words the owner reads in the session, as code writes them: «تو», never «شما» or a plural
PLURAL = re.compile(
    r"شما(?!ره)|خودتان|(?:کنید|بکنید|نکنید|بزنید|بدهید|ندهید|ببینید|بچسبانید|بگذارید|بنویسید|بگویید|"
    r"بپرسید|بفرستید|ببرید|بروید|بخوانید|بیندازید|بیاورید|بسازید|بگیرید|بمانید|باشید|بخواهید|"
    r"کرده‌اید|میخواهید|میتوانید|دارید|هستید|گفتید|دادید|زدید|کردید|بدانید|شوید)"
    r"(?=[\s.،؛»:\"'!؟)]|$)"
)


def plural_in(module: Any) -> list[str]:
    """Every string the module's code writes (its docstrings aside: they quote the owner)."""
    tree = ast.parse(Path(str(module.__file__)).read_text(encoding="utf-8"))
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            found += [f"{node.lineno}: {m.group(0)}" for m in PLURAL.finditer(node.value)]
    return found


def test_what_the_owner_reads_of_his_sessions_says_tu() -> None:
    from hq_api.domain import hands as HANDS

    for module in (SA, OR, OT, SE, NS, SM, W, DR, HANDS):
        assert plural_in(module) == [], module.__name__
    assert PLURAL.findall("فرمان تازه بدهید.") and PLURAL.findall("سؤال از شما")
    assert not PLURAL.findall("شماره‌ی کار") and not PLURAL.findall("فرمان تازه بده.")


# ============================================ F. an idle wake handed to a direct turn ==
async def test_an_idle_wake_handed_to_a_direct_turn_is_judged_by_that_turn(
    client: httpx.AsyncClient,
    hub: Hub,
    wk: dict[str, Any],
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    async def handed(s: dict[str, Any], minutes_ago: int) -> Any:
        """The classic run of a wake, ended at once by the hand-over, and the direct turn's own
        run (trigger `direct`) that did the work, in the four minutes after."""
        ref, co = s["ref"], s["company"]
        emp = await su.fetchval("SELECT id FROM core.employees WHERE code = $1", s["holder"])
        await su.execute(  # the classic run, ended with the runner's note (DR.HANDED)
            """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                   note, queued_at, started_at, finished_at)
               VALUES ($1, $2, $3, 'work', $4, 'done', 'direct turn J-1',
                       now() - make_interval(mins => $5), now() - make_interval(mins => $5),
                       now() - make_interval(mins => $5))""",
            co["id"], emp, s["wid"], f"session_idle:{ref}", minutes_ago,
        )  # fmt: skip
        return await su.fetchval(
            """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                   queued_at, started_at, finished_at)
               VALUES ($1, $2, $3, 'direct', $4, 'done', now() - make_interval(mins => $5),
                       now() - make_interval(mins => $5), now() - make_interval(mins => $5 - 4))
               RETURNING id""",
            co["id"], emp, s["wid"], f"direct:{ref}", minutes_ago - 1,
        )  # fmt: skip

    # the turn ticked task 1 inside its window: it worked, the session is not spent
    s = await an_order(client, owner, su, new_company, tasks=3, done=0, pace="auto")
    await backdate(su, s["ref"], 2)
    await handed(s, 8)
    await su.execute(
        """UPDATE owner.session_tasks SET state = 'done', updated_at = now() - interval '5 minutes'
           WHERE ref = $1 AND n = 1""",
        s["ref"],
    )
    await idle_for(su, s["ref"], 9)  # the clock stood before the wake
    p = await pulse_of(hub, s["ref"])
    assert p.wakes == 1 and not p.spent and p.stuck_fa is None, p
    assert await sweep(wk["hub"], s["ref"]) == []
    # a turn that made nothing, ticked nothing: the wake only narrated, stuck at once
    t = await an_order(client, owner, su, new_company, tasks=3, done=0, pace="auto")
    await backdate(su, t["ref"], 2)
    await idle_for(su, t["ref"], 9)  # the clock stood before the wake
    await handed(t, 8)
    p = await pulse_of(hub, t["ref"])
    assert p.wakes == 1 and p.spent and p.stuck_fa is not None, p
    assert await sweep(wk["hub"], t["ref"]) == ["stuck"]


def test_a_direct_turn_reads_the_wake_first_and_the_outside_work() -> None:
    w = {"title": "ریلز روزانه", "ref": "W-000123"}
    emp = {"title_fa": "مدیرعامل", "code": "PC-CEO", "company_name_fa": "پروچارت", "company": "PC"}
    brief = {
        "order": "F-0011", "text": "ریلز روزانه", "wake": "WOKEN BY THE HUB (1 of at most 2): …",
        "async_rule": OT.ASYNC_RULE, "direct_rule": OT.DIRECT_RULE, "plan": [{"n": 3}],
        "waiting_on": [{"who": "ChatGPT", "makes": "در صف ChatGPT: پیش‌نویس متن"}],
        "ended_without_answer": [{"who": "Gemini", "why": "not_claimed"}],
    }  # fmt: skip
    for first in (True, False):
        text = DR.compose(w, emp, brief, charter=None, tools=[], first=first, inputs=[],
                          reason=f"requeue:session_idle:{brief['order']}")  # fmt: skip
        assert text.index("WOKEN BY THE HUB") < text.index("## وضع جلسه"), text[:400]
        assert "waiting_on" in text and "ended_without_answer" in text and "not_claimed" in text
        assert OT.ASYNC_RULE in text and DR.why_fa("session_idle:F-1") in text
    assert DR.why_fa("session_idle:F-1").startswith("ستاد تو را بیدار کرد")
    assert DR.why_fa("requeue:owner_reply:F-1") == DR.why_fa("owner_reply:F-1")
    assert DR.why_fa("speech_done:x") != DR.why_fa("speech_failed:x") != DR.why_fa("x")
    assert DR.why_fa("creative_done:CR-1") != DR.why_fa("x")
    assert OR.base_reason("requeue:workspace_failed:W-1").startswith(DR.CLASSIC_REASONS)
    for text in (DR.why_fa("session_idle:F-1"), DR.why_fa("speech_done:x"),
                 DR.why_fa("creative_done:CR-1")):  # fmt: skip
        assert not PLURAL.findall(text), text


def test_what_wakes_an_agent_and_what_it_polls_is_said_truly(hub: Hub) -> None:
    from hq_api.agents import protocol as P

    rule = OT.ASYNC_RULE
    for tool in ("substitute.call", "speech.make", "workshop.run"):
        assert tool in rule
    # a `{job}` tool is polled, nothing wakes the agent for it
    assert "hub.ops" in rule and "call it again with `{job}`" in rule and "nothing wakes" in rule
    lib = hub.charters
    system = P.system_prompt(lib, lib.get("ceo"), {}, max_actions=4)
    assert "is called again with `{job}`" in system and "nothing wakes you for it" in system
    text = (Path(str(lib.root)) / "tools.md").read_text(encoding="utf-8")
    assert "`speech_done:`" in text and "`queued` is not an answer" in text
    # a destructive command or an A3 card waiting for the owner's seal is no failure
    for code in ("awaiting_seal", "a3_requires_decision"):
        acts = [{"tool": "server.exec", "outcome": "denied", "code": code}]
        assert SA.step_text("دستور برای مُهر مدیر کل فرستاده شد", acts) == (
            "دستور برای مُهر مدیر کل فرستاده شد"
        )
        assert "(نشد)" not in SA.tools_text(acts)
    assert "(نشد)" in SA.tools_text([{"tool": "server.exec", "outcome": "denied", "code": "x"}])


def test_the_stuck_sentence_names_the_end_of_the_last_step_and_the_owner_is_tu(hub: Hub) -> None:
    from hq_api.talk import context as TC

    said = (
        "گام ۲ در جریان است. موضوع اول («آموزش حد ضرر») ثبت شد. گوینده‌ی شرکت هم ثبت شد. "
        "پیش‌نویس متن ریلز از ChatGPT خواسته شد و در صف است."
    )
    last = SA.last_words(said)
    assert last.endswith("از ChatGPT خواسته شد و در صف است") and "گام ۲ در جریان است" not in last
    assert last.startswith("… ") and len(last) <= SA.LAST_WORDS + 2
    assert SA.last_words("کوتاه شد.") == "کوتاه شد"
    rep = {"steps": [{"who_fa": "مدیرعامل پروچارت", "what_fa": said, "at": "2026-11-10T18:58:00"}]}
    line = SA.STUCK_PLAN_FA.format(
        last=SA.last_words(SA._last_step_fa(rep) or ""), n=3, title="متن"
    )
    assert "آخرین کار: … " in line and ".؛" not in line and "…؛" not in line, line
    # the agents are told to write to the owner with «تو»; the brand's «شما» is for others
    assert "«تو»" in hub.charters.common and "«تو»" in TC.TALK_RULES
    assert "مدیر کل (مالک) «تو»" in (
        Path(str(hub.charters.root)) / "charter" / "HOLDING.md"
    ).read_text(encoding="utf-8")


async def test_a_call_past_its_deadline_shows_as_ending_until_the_reaper_ends_it(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    late: list[dict[str, Any]] = []

    async def pending_for(tx: Any, ids: list[Any], at: Any = None) -> list[dict[str, Any]]:
        return list(late)

    monkeypatch.setattr(S, "pending_for", pending_for)
    work = {"id": uuid.uuid4(), "ref": "W-000999", "status": "in_progress", "title": "ریلز",
            "company_fa": "پروچارت"}  # fmt: skip
    row = {"id": uuid.uuid4(), "player": "gpt", "player_fa": "ChatGPT", "seat": "content_draft",
           "seat_fa": "پیش‌نویس متن", "state": "queued", "created_at": now - timedelta(minutes=17),
           "claimed_at": None, "deadline_at": now - timedelta(minutes=1), "ending": True}  # fmt: skip
    late.append(row)
    async with await all_tx(hub) as tx:
        [c] = await SA.pending_outside(tx, [work], now)
        assert c["doing_fa"] == "ChatGPT جواب نداد؛ تمام میشود…" and c["who_fa"] == "ChatGPT"
        assert await SA.ended_outside(tx, [work], now - timedelta(hours=1), now) == []
        # the reaper did not end it within its grace: not live any more, and named as the cause
        late[0] = {**row, "deadline_at": now - SA.ENDING_GRACE - timedelta(minutes=1)}
        assert await SA.pending_outside(tx, [work], now) == []
        [gone] = await SA.ended_outside(tx, [work], now - timedelta(hours=1), now)
    assert gone["who_fa"] == "ChatGPT" and gone["why_fa"] == "نوبتش نرسید"
