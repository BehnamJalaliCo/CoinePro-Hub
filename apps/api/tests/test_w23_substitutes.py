"""The stall of 2026-11-10 (the owner's Pro-Chart reels session went silent for 12 hours after its
holder wrote «پیش‌نویس متن ... از ChatGPT خواسته شد و در صف است»): a substitute call never
stalls silently again.

- every call has a deadline: a queued one nobody took ends `not_claimed`, a running one its
  runner lost ends `timeout` (S.expire_stale, every minute and at every CLI claim, also while the
  holding is locked); `pending_for` and the reaper read the same deadline;
- every end reaches its caller (a reply work that says plainly why and to carry on with its own
  model now) and its session (one line), including a skip by the web pass and egress `off`;
- one web job that breaks never stops the others, and different players run at once;
- nothing is queued that could never run (a CLI seat while the runner is off; a web question
  longer than egress takes);
- an agent's creative wakes its work when it ends, and when the owner decides it;
- ChatGPT has the content_draft seat (migration 0062).
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from hq_api.domain import advisor as A
from hq_api.domain import humanize as HZ
from hq_api.domain import substitutes as S
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.security import agent_tokens

from .conftest import AGENT_KEY, agent_headers, substitutes_headers
from .p10_fakes import holding_switch
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import FakeEgress, bench, claim, per_day, png
from .test_p21_routing_orders import all_tx
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, refuse_queued

MIGRATION = Path(__file__).parents[1] / "migrations" / "versions" / "0062_gpt_content_draft.py"


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0062", MIGRATION)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _session(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, co: str
) -> dict[str, Any]:
    """An order with its live session; its holder runs on the root work (a token bound to it)."""
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    [route] = out["routes"]
    holder, root = route["to"], route["work_ref"]
    await refuse_queued(su, root)
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               started_at, token_expires_at)
           SELECT e.company_id, e.id, w.id, 'work', 'test', 'running', now(), now() + interval '1 hour'
           FROM core.employees e, work.work w WHERE e.code = $1 AND w.ref = $2 RETURNING id""",
        holder,
        root,
    )
    return {
        "ref": out["ref"],
        "conv": out["talk_ref"],
        "holder": holder,
        "root": root,
        "root_id": await su.fetchval("SELECT id FROM work.work WHERE ref = $1", root),
        "company_id": await su.fetchval("SELECT company_id FROM work.work WHERE ref = $1", root),
        "run": rid,
        "headers": {"Authorization": f"Bearer {agent_tokens.mint(AGENT_KEY, holder, str(rid))}"},
    }


async def _end_run(su: Any, s: dict[str, Any]) -> None:
    await su.execute(
        "UPDATE agents.runs SET state = 'done', finished_at = now() WHERE id = $1", s["run"]
    )


async def _last_line(su: Any, conv: str) -> str:
    line: str = await su.fetchval(
        """SELECT t.show_md FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE c.ref = $1 ORDER BY t.n DESC LIMIT 1""",
        conv,
    )
    return line


async def _reply(su: Any, call_id: Any) -> Any:
    return await su.fetchrow(
        """SELECT w.ref, w.title, w.brief, w.budget_tokens, w.requested_by_work_id, e.code
           FROM substitutes.calls c JOIN work.work w ON w.id = c.reply_work_id
           JOIN core.employees e ON e.id = w.assignee_id WHERE c.id = $1::uuid""",
        str(call_id),
    )


async def _settle(su: Any) -> None:
    """The jobs a test left queued or running (made by hand) are over: no later test's lane holds
    them, and no reaper delivers them."""
    await su.execute(
        """UPDATE substitutes.calls SET state = 'skipped', state_reason = 'test', finished_at = now(),
               delivered_at = COALESCE(delivered_at, now())
           WHERE state IN ('queued', 'running')"""
    )


async def _call(su: Any, call_id: Any) -> Any:
    return await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1::uuid", str(call_id))


# ===================================================================== the words ==
def test_the_deadlines_and_the_words_are_data() -> None:
    t0 = datetime(2026, 11, 10, 18, 58, tzinfo=UTC)
    text = {"state": "queued", "seat": "content_draft", "task": "text", "created_at": t0,
            "claimed_at": None, "timeout_s": 300}  # fmt: skip
    assert S.deadline_at(text) == t0 + timedelta(minutes=15) == t0 + S.QUEUE_DEADLINE
    image = {**text, "seat": "creative", "task": "image"}
    assert S.deadline_at(image) == t0 + timedelta(minutes=30)
    running = {
        **text,
        "state": "running",
        "claimed_at": t0 + timedelta(minutes=2),
        "timeout_s": 600,
    }
    assert S.deadline_at(running) == t0 + timedelta(minutes=2, seconds=600 + 120)
    # asked again: the clock runs from then; behind a busy lane, from when the lane was free
    again = {**text, "queued_at": t0 + timedelta(minutes=14)}
    assert S.deadline_at(again) == t0 + timedelta(minutes=29)
    assert S.deadline_at(text, t0 + timedelta(minutes=9)) == t0 + timedelta(minutes=24)
    assert S.deadline_at(text, t0 - timedelta(minutes=9)) == t0 + timedelta(minutes=15)
    # the reasons in the owner's words, by their machine word
    assert S.reason_fa("not_claimed") == "نوبتش نرسید"
    assert S.reason_fa("timeout: egress") == "جوابش طول کشید"
    assert S.reason_fa("browser_unavailable") == "مرورگرش در دسترس نبود"
    assert S.reason_fa("expired") == S.reason_fa("signed_out") == "از حسابش بیرون افتاده بود"
    assert S.reason_fa("per_day") == S.reason_fa("limited") == "سهم امروزش تمام شده بود"
    assert S.reason_fa("worker_error") == "خطای داخلی"
    assert S.reason_fa("too_long") == "متن بلندتر از حد بود"
    assert S.reason_fa("holding_locked") == "کارها قفل بود"
    assert S.reason_fa("recipe_failed: paste_prompt") and S.reason_fa(None) == S.REASON_FA_DEFAULT
    assert S.seat_fa("content_draft") == "پیش‌نویس متن" and S.seat_fa("creative", "image") == "تصویر"
    assert S.seat_fa("creative", "video") == "ویدیو" and S.seat_fa("long_read") == "خواندن متن بلند"
    for phrase in [*S.REASON_FA.values(), *S.SEAT_FA.values(), S.REASON_FA_DEFAULT]:
        assert HZ.check(phrase) == [] and "شما" not in phrase, phrase
    # a too-long question is the caller's to shorten, never «channel not configured»
    err = S.refusal("too_long")
    assert err.status == 422 and err.fields == {
        "input_md": "at most 20000 characters for this player"
    }


# ================================================== the deadline and the delivery ==
async def test_a_queued_call_past_its_deadline_fails_and_its_caller_and_session_hear_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    s = await _session(client, owner, su, co)
    try:
        async with bench(su, hub, web=("gpt",)):
            await per_day(su, "gpt", "content_draft", 5)
            # ChatGPT writes the draft (its content_draft seat): queued, with its deadline
            r = await client.post(
                "/internal/v1/substitutes/call", headers=s["headers"],
                json={"seat": "content_draft", "player": "gpt", "input_md": "یک متن ریلز درباره‌ی نمودار بنویس."},
            )  # fmt: skip
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["state"] == "queued" and "not done" in body["note"]
            row = await _call(su, body["call"])
            assert (row["player"], row["seat"], row["via"]) == ("gpt", "content_draft", "web")
            deadline = S.deadline_at(dict(row))
            assert body["deadline_at"] == deadline.isoformat()
            assert deadline == row["created_at"] + S.QUEUE_DEADLINE
            since = await su.fetchval("SELECT clock_timestamp()")
            async with await all_tx(hub) as tx:
                # pending until its deadline, never after: the reaper's own rule
                before = await S.pending_for(tx, [s["root_id"]], deadline - timedelta(seconds=1))
                assert [p["id"] for p in before] == [row["id"]]
                p = before[0]
                assert (p["player"], p["player_fa"], p["seat"], p["seat_fa"], p["state"]) == (
                    "gpt", "ChatGPT", "content_draft", "پیش‌نویس متن", "queued",
                )  # fmt: skip
                assert p["deadline_at"] == deadline and p["claimed_at"] is None
                assert set(p) == {"id", "player", "player_fa", "seat", "seat_fa", "state",
                                  "created_at", "claimed_at", "deadline_at", "ending"}  # fmt: skip
                assert p["ending"] is False
                await S.expire_stale(tx, hub, deadline - timedelta(seconds=1))
            assert (await _call(su, row["id"]))["state"] == "queued"
            async with await all_tx(hub) as tx:
                # past its deadline and not yet reaped: still pending, `ending` (never neither)
                at = await S.pending_for(tx, [s["root_id"]], deadline)
                assert [(x["id"], x["ending"]) for x in at] == [(row["id"], True)]
                assert await S.expire_stale(tx, hub, deadline) >= 1
                assert await S.pending_for(tx, [s["root_id"]], deadline) == []
            ended = await _call(su, row["id"])
            assert (ended["state"], ended["state_reason"]) == ("failed", "not_claimed")
            assert ended["input_md"] is None and ended["finished_at"] is not None
            assert ended["delivered_at"] is not None
            # the caller: a reply work of its own order that says why and to carry on now
            reply = await _reply(su, row["id"])
            assert reply is not None and reply["code"] == s["holder"]
            assert reply["requested_by_work_id"] == s["root_id"]
            assert (
                "nobody picked it up" in reply["brief"] and "Do not wait for it" in reply["brief"]
            )
            assert "own model" in reply["brief"] and s["root"] in reply["brief"]
            assert reply["budget_tokens"] == S.REPLY_TOKENS == 60_000
            assert reply["title"] == "ChatGPT جواب نداد (پیش‌نویس متن)"
            # the session: one plain line, addressed to nobody as «شما»
            line = await _last_line(su, s["conv"])
            assert "ChatGPT جواب نداد (نوبتش نرسید)" in line, line
            assert "با مدل خودش ادامه میدهد" in line and "شما" not in line
            assert HZ.check(line) == [], (line, HZ.check(line))
            async with await all_tx(hub) as tx:
                gone = await S.ended_since(tx, [s["root_id"]], since)
            assert [g["id"] for g in gone] == [row["id"]]
            assert gone[0] == {
                "id": row["id"], "player_fa": "ChatGPT", "seat_fa": "پیش‌نویس متن", "state": "failed",
                "state_reason": "not_claimed", "reason_fa": "نوبتش نرسید",
                "finished_at": ended["finished_at"],
            }  # fmt: skip
            async with await all_tx(hub) as tx:
                assert (
                    await S.ended_since(tx, [s["root_id"]], datetime.now(UTC) + timedelta(hours=1))
                    == []
                )
                assert (
                    await S.pending_for(tx, []) == [] and await S.ended_since(tx, [], since) == []
                )
            await refuse_queued(su, reply["ref"])
    finally:
        await _end_run(su, s)


async def test_a_caller_no_longer_active_is_logged_and_the_session_still_hears_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    s = await _session(client, owner, su, co)
    try:
        async with bench(su, hub, web=("gpt",)):
            cid = await su.fetchval(
                """INSERT INTO substitutes.calls (company_id, player, seat, via, task, state, caller_kind,
                       caller_code, purpose_kind, purpose_ref, input_md, timeout_s, day, month_key)
                   VALUES ($1, 'gpt', 'content_draft', 'web', 'text', 'queued', 'agent', 'ZZ-GONE',
                           'caller_work', $2, 'x', 300, current_date, '1405-08') RETURNING id""",
                s["company_id"],
                str(s["root_id"]),
            )
            async with await all_tx(hub) as tx:
                await S.expire_stale(tx, hub, datetime.now(UTC) + timedelta(minutes=16))
            row = await _call(su, cid)
            assert (row["state"], row["state_reason"]) == ("failed", "not_claimed")
            assert row["delivered_at"] is not None and row["reply_work_id"] is None
            line = await _last_line(su, s["conv"])
            assert "ChatGPT جواب نداد (نوبتش نرسید)" in line and "دیگر فعال نیست" in line, line
    finally:
        await _end_run(su, s)


async def test_an_orphaned_running_web_call_is_reaped_and_its_players_queue_moves_again(
    hub: Hub, su: Any
) -> None:
    async with bench(su, hub, web=("deepseek",)):
        await su.execute("UPDATE substitutes.seats SET per_day = 1000 WHERE player = 'deepseek'")
        try:
            holding = await hub.companies.holding()
            async with hub.db.tx(await hub.companies.ids()) as tx:
                lost = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال یک",
                                         company_id=holding.id)  # fmt: skip
                nxt = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال دو",
                                        company_id=holding.id)  # fmt: skip
            # the worker was recreated mid-job: `running`, never answered
            await su.execute(
                """UPDATE substitutes.calls SET state = 'running', claimed_at = now() - interval '20 minutes'
                   WHERE id = $1""",
                lost["id"],
            )
            fake = FakeEgress(
                {"ok": True, "text_md": "نرخ تورم ۳ درصد بود.", "recipe_version": "1"}
            )
            out = await S.web_jobs(hub, fake)
            assert out["expired"] >= 1 and out["ran"] == 1, out
            assert [c["prompt"] for c in fake.calls] == ["سوال دو"]
            a, b = await _call(su, lost["id"]), await _call(su, nxt["id"])
            assert (a["state"], a["state_reason"]) == ("failed", "timeout")
            assert b["state"] == "done"
            # an answer that comes after the reaper ended its call changes nothing
            late = None
            async with hub.db.tx(await hub.companies.ids()) as tx:
                late = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال سه",
                                         company_id=holding.id)  # fmt: skip

            class Reaped(FakeEgress):
                async def web(self, **kw: Any) -> dict[str, Any]:
                    self.calls.append(kw)
                    await su.execute(
                        """UPDATE substitutes.calls SET state = 'failed', state_reason = 'timeout',
                               finished_at = now() WHERE id = $1""",
                        late["id"],
                    )
                    return {"ok": True, "text_md": "دیر رسید"}

            await su.execute("UPDATE substitutes.players SET web_last_job_at = NULL")
            await S.web_jobs(hub, Reaped())
            c = await _call(su, late["id"])
            assert (c["state"], c["result"]) == ("failed", None)
            # a lines step that stops waiting ends its call (no orphan, no daily cap eaten)
            async with hub.db.tx(await hub.companies.ids()) as tx:
                gone = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال چهار",
                                         company_id=holding.id, purpose=("lines", "LR-000001"))  # fmt: skip
                assert await S.abandon(tx, hub, gone["id"]) is True
                assert await S.abandon(tx, hub, gone["id"]) is False  # once
            g = await _call(su, gone["id"])
            assert (g["state"], g["state_reason"]) == ("failed", "abandoned")
        finally:
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 60 WHERE player = 'deepseek' AND seat = 'quick_search'"
            )
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 5 WHERE player = 'deepseek' AND seat = 'third_opinion'"
            )


async def test_the_cli_reaper_delivers_and_a_cli_seat_is_never_queued_while_the_runner_is_off(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    pa = await agent_headers("HQ-PA")
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        r = await client.post("/internal/v1/substitutes/call", headers=pa,
                              json={"seat": "assistant_errand", "input_md": "این را خلاصه کن: هفته‌ی خوب."})  # fmt: skip
        assert r.status_code == 200 and r.json()["state"] == "queued", r.text
        call = r.json()["call"]
        job = (await claim(client))["job"]
        assert job["id"] == call
        # the dispatcher lost it: the next claim ends it, and the assistant hears it
        await su.execute(
            "UPDATE substitutes.calls SET claimed_at = now() - interval '30 minutes' WHERE id = $1::uuid",
            call,
        )
        await claim(client)
        row = await _call(su, call)
        assert (row["state"], row["state_reason"]) == ("failed", "timeout")
        reply = await _reply(su, call)
        assert reply is not None and reply["code"] == "HQ-PA"
        assert "longer than its time limit" in reply["brief"] and "own model" in reply["brief"]
        await refuse_queued(su, reply["ref"])
        # the substitutes runner is off: a CLI seat is skipped at once, never queued for ever
        S.RUNNER_OVERRIDE = False  # (the bench puts it back)
        r = await client.post("/internal/v1/substitutes/call", headers=pa,
                              json={"seat": "assistant_errand", "input_md": "یکی دیگر را خلاصه کن."})  # fmt: skip
        assert r.status_code == 503 and r.json()["code"] == "channel_not_configured", r.text
        holding = await hub.companies.holding()
        async with hub.db.tx(await hub.companies.ids()) as tx:
            off = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand", input_md="خلاصه",
                                    company_id=holding.id)  # fmt: skip
        assert (off["state"], off["state_reason"], off["input_md"]) == ("skipped", "off", None)


# ======================================================== the web pass's ends ==
async def test_a_skipped_or_browserless_web_call_reaches_its_caller(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    pa = await agent_headers("HQ-PA")
    async with bench(su, hub, web=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)

        async def ask(text: str) -> str:
            r = await client.post("/internal/v1/substitutes/call", headers=pa,
                                  json={"seat": "assistant_errand", "input_md": text})  # fmt: skip
            assert r.status_code == 200 and r.json()["state"] == "queued", r.text
            return str(r.json()["call"])

        first, second = await ask("خلاصه‌ی اول"), await ask("خلاصه‌ی دوم")
        # the profile went out after they were queued: both end now, each told to its caller
        await su.execute(
            "UPDATE substitutes.players SET web_state = 'expired' WHERE player = 'gpt'"
        )
        await S.web_jobs(hub, FakeEgress())
        for cid in (first, second):
            row = await _call(su, cid)
            assert (row["state"], row["state_reason"]) == ("skipped", "expired")
            reply = await _reply(su, cid)
            assert reply is not None and "signed out" in reply["brief"], reply
            await refuse_queued(su, reply["ref"])
        await su.execute(
            "UPDATE substitutes.players SET web_state = 'signed_in', web_last_job_at = NULL WHERE player = 'gpt'"
        )
        # a web question longer than egress takes: refused at once, the caller shortens it
        r = await client.post("/internal/v1/substitutes/call", headers=pa,
                              json={"seat": "assistant_errand", "input_md": "سلام " * 4_001})  # fmt: skip
        assert r.status_code == 422 and r.json()["fields"] == {
            "input_md": "at most 20000 characters for this player"
        }, r.text
        assert r.json()["message_fa"]
        holding = await hub.companies.holding()
        async with hub.db.tx(await hub.companies.ids()) as tx:
            long = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand",
                                     input_md="x" * (S.WEB_PROMPT_LIMIT + 1), company_id=holding.id)  # fmt: skip
        assert (long["state"], long["state_reason"], long["input_md"]) == (
            "skipped",
            "too_long",
            None,
        )
        # egress answers `off` (the profile browser is not running): a failure, delivered, and
        # every other waiting call of that player ends with it
        third, fourth = await ask("خلاصه‌ی سوم"), await ask("خلاصه‌ی چهارم")
        await S.web_jobs(hub, FakeEgress({"ok": False, "error": "off", "detail": "not running"}))
        for cid in (third, fourth):
            row = await _call(su, cid)
            assert (row["state"], row["state_reason"]) == ("failed", "browser_unavailable")
            reply = await _reply(su, cid)
            assert reply is not None and "browser on the hub was not available" in reply["brief"]
            await refuse_queued(su, reply["ref"])
        p = await su.fetchrow(
            """SELECT web_last_failure, web_error_until - now() AS hold FROM substitutes.players
               WHERE player = 'gpt'"""
        )
        assert p["web_last_failure"] == "off: not running"
        assert timedelta(minutes=9) < p["hold"] <= S.BROWSER_HOLD
        # for its ten minutes the next call is refused at once: nothing queued, no reply work
        calls = await su.fetchval("SELECT count(*) FROM substitutes.calls WHERE player = 'gpt'")
        works = await su.fetchval("SELECT count(*) FROM work.work")
        r = await client.post("/internal/v1/substitutes/call", headers=pa,
                              json={"seat": "assistant_errand", "input_md": "خلاصه‌ی پنجم"})  # fmt: skip
        assert r.status_code == 503 and "browser_unavailable" in r.text, r.text
        await S.web_jobs(hub, FakeEgress())
        assert (
            await su.fetchval("SELECT count(*) FROM substitutes.calls WHERE player = 'gpt'")
            == calls
        )
        assert await su.fetchval("SELECT count(*) FROM work.work") == works
        async with hub.db.tx(await hub.companies.ids()) as tx:
            held = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand", input_md="x",
                                     company_id=holding.id)  # fmt: skip
        assert (held["state"], held["state_reason"]) == ("skipped", "browser_unavailable")
        # the owner signs the profile in again (or the hold ends): calls are taken again
        r = await client.post("/internal/v1/substitutes/signed-in", headers=substitutes_headers(),
                              json={"player": "gpt", "via": "web"})  # fmt: skip
        assert r.status_code == 200, r.text
        fits = await ask("x" * S.WEB_PROMPT_LIMIT)
        assert (await _call(su, fits))["state"] == "queued"


async def test_one_browser_job_at_a_time_and_a_broken_one_never_stops_the_next(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    """browser-web holds one browser: a pass runs ONE web job for every player, the oldest call
    whose player is not resting; a job that breaks in the worker ends `worker_error` (its caller
    hears it) and the next pass goes on."""
    pa = await agent_headers("HQ-PA")
    async with bench(su, hub, web=("gpt", "deepseek")):
        await per_day(su, "gpt", "assistant_errand", 5)
        await su.execute("UPDATE substitutes.seats SET per_day = 1000 WHERE player = 'deepseek'")
        try:
            r = await client.post("/internal/v1/substitutes/call", headers=pa,
                                  json={"seat": "assistant_errand", "input_md": "خلاصه کن"})  # fmt: skip
            gpt_call = r.json()["call"]
            holding = await hub.companies.holding()
            async with hub.db.tx(await hub.companies.ids()) as tx:
                ds = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال عمومی",
                                       company_id=holding.id)  # fmt: skip

            class Broken(FakeEgress):
                async def web(self, **kw: Any) -> dict[str, Any]:
                    self.calls.append(kw)
                    if kw["account"] == "chatgpt-web":
                        raise RuntimeError("the worker broke on this job")
                    return {"ok": True, "text_md": "پاسخ عمومی", "recipe_version": "1"}

            fake = Broken()
            out = await S.web_jobs(hub, fake)  # the oldest: ChatGPT's, alone
            assert [c["account"] for c in fake.calls] == ["chatgpt-web"] and out["ran"] == 0, out
            g, d = await _call(su, gpt_call), await _call(su, ds["id"])
            assert (g["state"], g["state_reason"]) == ("failed", "worker_error")
            assert d["state"] == "queued" and d["claimed_at"] is None  # its turn is the next pass
            reply = await _reply(su, gpt_call)
            assert reply is not None and "internal error" in reply["brief"]
            await refuse_queued(su, reply["ref"])
            out = await S.web_jobs(hub, fake)
            assert [c["account"] for c in fake.calls][-1] == "deepseek-web" and out["ran"] == 1
            d = await _call(su, ds["id"])
            assert d["state"] == "done"
            # a resting player's older call waits; a younger call of another player goes first
            async with hub.db.tx(await hub.companies.ids()) as tx:
                rest = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="باز",
                                         company_id=holding.id)  # fmt: skip
                gpt2 = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand",
                                         input_md="خلاصه", company_id=holding.id, player="gpt")  # fmt: skip
            await su.execute(
                "UPDATE substitutes.players SET web_last_job_at = now() WHERE player = 'deepseek'"
            )
            await su.execute(
                "UPDATE substitutes.players SET web_last_job_at = NULL WHERE player = 'gpt'"
            )
            await S.web_jobs(hub, FakeEgress({"ok": True, "text_md": "خلاصه شد"}))
            assert (await _call(su, gpt2["id"]))["state"] == "done"
            assert (await _call(su, rest["id"]))["state"] == "queued"
        finally:
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 60 WHERE player = 'deepseek' AND seat = 'quick_search'"
            )
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 5 WHERE player = 'deepseek' AND seat = 'third_opinion'"
            )


async def test_while_the_holding_is_locked_an_agents_queued_call_is_skipped_and_told(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
    pa = await agent_headers("HQ-PA")
    async with bench(su, hub, web=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        r = await client.post("/internal/v1/substitutes/call", headers=pa,
                              json={"seat": "assistant_errand", "input_md": "خلاصه کن"})  # fmt: skip
        call = r.json()["call"]
        fake = FakeEgress()
        async with holding_switch(su, "engaged"):
            out = await S.web_jobs(hub, fake)
        assert out["skipped"] is True and out["reason"] == "holding_locked" and fake.calls == []
        row = await _call(su, call)
        assert (row["state"], row["state_reason"]) == ("skipped", "holding_locked")
        reply = await _reply(su, call)
        assert reply is not None and "locked" in reply["brief"]
        await refuse_queued(su, reply["ref"])


# ================================================================ the creative ==
async def test_an_agents_creative_wakes_its_work_when_it_ends_and_when_the_owner_decides(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    s = await _session(client, owner, su, company["code"])
    who = Principal(kind="agent", code=s["holder"], role="ceo", company=company["code"],
                    company_id=s["company_id"])  # fmt: skip

    async def creative(brief: str) -> dict[str, Any]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            row = await S.create_creative(
                tx, hub, who, company_id=s["company_id"], kind="image", brief_md=brief,
                prompt_md=S.template_prompt(brief, "instagram_post", "image", None),
                placement="instagram_post", overlay=None, duration_s=None, player="gpt",
                work_id=s["root_id"],
            )  # fmt: skip
        assert row["state"] == "queued"
        return row

    async def woken() -> list[str]:
        return [
            r["reason"]
            for r in await su.fetch(
                """SELECT reason FROM agents.runs WHERE work_id = $1 AND reason LIKE 'creative_done:%'
                   ORDER BY queued_at""",
                s["root_id"],
            )
        ]

    try:
        async with bench(su, hub, web=("gpt",)):
            await per_day(su, "gpt", "creative", 5)
            made = await creative("کاور ریلز")
            await S.web_jobs(hub, FakeEgress({"ok": True, "file": {"name": "c.png", "mime": "image/png",
                                                                   "b64": png(1080, 1350)}}))  # fmt: skip
            got = await su.fetchrow(
                "SELECT state FROM substitutes.creatives WHERE ref = $1", made["ref"]
            )
            assert got["state"] == "review"
            assert await woken() == [f"creative_done:{made['ref']}"]
            await refuse_queued(su, s["root"])
            # the owner accepts it: the holder goes on (publishing is its own decision, as always)
            r = await client.post(f"/api/v1/creatives/{made['ref']}/accept", headers=owner, json={})
            assert r.status_code == 200, r.text
            assert len(await woken()) == 2
            await refuse_queued(su, s["root"])
            # not made (the hub's browser was not available): it wakes too
            await su.execute(
                "UPDATE substitutes.players SET web_last_job_at = NULL WHERE player = 'gpt'"
            )
            lost = await creative("کاور دوم")
            await S.web_jobs(
                hub, FakeEgress({"ok": False, "error": "off", "detail": "not running"})
            )
            got = await su.fetchrow(
                "SELECT state, review_md FROM substitutes.creatives WHERE ref = $1", lost["ref"]
            )
            assert got["state"] == "failed" and "browser" in got["review_md"]
            assert (await woken())[-1] == f"creative_done:{lost['ref']}"
            await refuse_queued(su, s["root"])
    finally:
        await _end_run(su, s)


# ========================================================== ChatGPT's seat ==
async def test_chatgpt_has_the_content_draft_seat_after_seed_or_migration(su: Any) -> None:
    gpt = {x["seat"]: x for x in S.DEFAULT_SEATS["gpt"]}
    assert gpt["content_draft"] == {"seat": "content_draft", "via": "web", "model": "gpt-5.5",
                                    "enabled": True, "per_day": 30}  # fmt: skip
    assert any(x["seat"] == "content_draft" for x in S.DEFAULT_SEATS["gemini"])  # Gemini keeps it
    row = await su.fetchrow(
        "SELECT via, model, per_day FROM substitutes.seats WHERE player = 'gpt' AND seat = 'content_draft'"
    )
    assert row is not None and (row["via"], row["per_day"]) == ("web", 30)
    m = _migration()
    assert (m.revision, m.down_revision) == ("0062", "0061")
    # the api records a runner's Claude rate-limit windows (0062's grant)
    for priv in ("SELECT", "INSERT", "UPDATE"):
        assert await su.fetchval(
            "SELECT has_table_privilege('hq_api', 'llm.quota_status', $1)", priv
        ), priv
    # the session sweep (on the worker) reopens a delivered root (0062's grant)
    for role in ("hq_api", "hq_worker"):
        assert await su.fetchval(
            "SELECT has_function_privilege($1, 'work.reopen(uuid)', 'EXECUTE')", role
        ), role
    tr = su.transaction()
    await tr.start()
    try:
        # idempotent where the seat is there already: nothing changes, no audit row
        audits = await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE target_ref = 'gpt:content_draft'"
        )
        await su.execute(m.SEAT)
        assert await su.fetchval(
            "SELECT count(*) FROM substitutes.seats WHERE player = 'gpt' AND seat = 'content_draft'"
        ) == 1  # fmt: skip
        assert await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE target_ref = 'gpt:content_draft'"
        ) == audits  # fmt: skip
        # a hub without it (seats are never deleted: moved aside for the block) gets it, once
        await su.execute(
            "UPDATE substitutes.seats SET seat = 'third_opinion' WHERE player = 'gpt' AND seat = 'content_draft'"
        )
        await su.execute(m.SEAT)
        added = await su.fetchrow(
            """SELECT via, model, enabled, per_day FROM substitutes.seats
               WHERE player = 'gpt' AND seat = 'content_draft'"""
        )
        assert tuple(added) == ("web", "gpt-5.5", True, 30)
        assert await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE target_ref = 'gpt:content_draft'"
        ) == audits + 1  # fmt: skip
    finally:
        await tr.rollback()


async def test_the_workers_egress_client_answers_every_failure_never_raises() -> None:
    from hq_api.worker.management_activities import EgressWeb

    def client(handler: Callable[[httpx.Request], httpx.Response]) -> EgressWeb:
        return EgressWeb("http://egress:8090", transport=httpx.MockTransport(handler))

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    ask = {"account": "chatgpt-web", "task": "text", "prompt": "x", "timeout_s": 10}
    timed_out = await client(slow).web(**ask)  # no answer in time: the browser is not available
    assert timed_out["error"] == "off" and "in time" in timed_out["detail"]
    assert (await client(down).web(**ask))["error"] == "off"  # not reachable: the browser is not
    crashed = client(lambda r: httpx.Response(502, text="bad gateway"))
    assert (await crashed.web(**ask))["error"] == "off"
    refused = client(lambda r: httpx.Response(422, json={"detail": [{"loc": ["prompt"]}]}))
    got = await refused.web(**ask)
    assert got["ok"] is False and got["error"] == "failed" and "422" in got["detail"]
    fine = client(lambda r: httpx.Response(200, json={"ok": True, "text_md": "پاسخ"}))
    assert await fine.web(**ask) == {"ok": True, "text_md": "پاسخ"}


# ======================================================= the lane, the retries ==
async def test_a_call_waiting_behind_a_busy_lane_is_not_reaped_and_a_free_lanes_is(
    hub: Hub, su: Any
) -> None:
    """The cover first, then the script (the owner's reels order): the script waits behind the
    cover in the web lane (one pass serves every player and waits for all its jobs), and its
    clock runs from when the lane is free again, not from when it was asked."""
    async with bench(su, hub, web=("gpt", "deepseek")):
        await per_day(su, "gpt", "creative", 5)
        await su.execute("UPDATE substitutes.seats SET per_day = 1000 WHERE player = 'deepseek'")
        try:
            holding = await hub.companies.holding()
            async with hub.db.tx(await hub.companies.ids()) as tx:
                cover = await S.seat_call(tx, hub, A.SERVICE, seat="creative", input_md="کاور",
                                          company_id=holding.id, player="gpt", task="image")  # fmt: skip
            assert cover["state"] == "queued" and cover["timeout_s"] == 900
            await su.execute(
                "UPDATE substitutes.calls SET state = 'running', claimed_at = now() WHERE id = $1",
                cover["id"],
            )
            async with hub.db.tx(await hub.companies.ids()) as tx:
                script = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search",
                                           input_md="متن", company_id=holding.id)  # fmt: skip
            cover = await _call(su, cover["id"])
            busy_until = cover["claimed_at"] + timedelta(seconds=900 + S.RUN_GRACE_S)
            async with hub.db.tx(await hub.companies.ids()) as tx:
                deadline = await S.deadline_of(tx, script["id"])
                assert deadline == busy_until + S.QUEUE_DEADLINE
                assert deadline == S.deadline_at(script, busy_until)
                # 16 minutes on: its own 15 are gone, but the lane was busy all along
                await S.expire_stale(tx, hub, script["created_at"] + timedelta(minutes=16))
            assert (await _call(su, script["id"]))["state"] == "queued"
            # the lane was free before it was asked: the clock runs from when it was asked
            await su.execute(
                """UPDATE substitutes.calls SET state = 'done', finished_at = $2 WHERE id = $1""",
                cover["id"],
                script["created_at"] - timedelta(seconds=1),
            )
            async with hub.db.tx(await hub.companies.ids()) as tx:
                assert await S.deadline_of(tx, script["id"]) == (
                    script["created_at"] + S.QUEUE_DEADLINE
                )
                await S.expire_stale(tx, hub, script["created_at"] + timedelta(minutes=16))
            row = await _call(su, script["id"])
            assert (row["state"], row["state_reason"]) == ("failed", "not_claimed")
            # ChatGPT's own queue: the cover asked first and taken only after the script was asked
            # still holds it (it was ahead); a job asked after it holds nothing
            async with hub.db.tx(await hub.companies.ids()) as tx:
                cover = await S.seat_call(tx, hub, A.SERVICE, seat="creative", input_md="کاور ۲",
                                          company_id=holding.id, player="gpt", task="image")  # fmt: skip
                script = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand",
                                           input_md="متن ۲", company_id=holding.id, player="gpt")  # fmt: skip
            assert script["state"] == "queued"
            await su.execute(
                """UPDATE substitutes.calls SET state = 'running', claimed_at = clock_timestamp()
                   WHERE id = $1""",
                cover["id"],
            )
            cover = await _call(su, cover["id"])
            async with hub.db.tx(await hub.companies.ids()) as tx:
                later = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="بعدی",
                                          company_id=holding.id)  # fmt: skip
                assert await S.deadline_of(tx, script["id"]) == (
                    cover["claimed_at"] + timedelta(seconds=900 + S.RUN_GRACE_S) + S.QUEUE_DEADLINE
                )
                assert await S.deadline_of(tx, later["id"]) == (
                    cover["claimed_at"] + timedelta(seconds=900 + S.RUN_GRACE_S) + S.QUEUE_DEADLINE
                )
            await su.execute(
                """UPDATE substitutes.calls SET state = 'running', claimed_at = clock_timestamp()
                   WHERE id = $1""",
                later["id"],
            )
            async with hub.db.tx(await hub.companies.ids()) as tx:
                # DeepSeek's short job, asked after the script and taken while it waited: it ends
                # before the cover, so the script's deadline stays the cover's
                assert await S.deadline_of(tx, script["id"]) == (
                    cover["claimed_at"] + timedelta(seconds=900 + S.RUN_GRACE_S) + S.QUEUE_DEADLINE
                )
        finally:
            await _settle(su)
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 60 WHERE player = 'deepseek' AND seat = 'quick_search'"
            )
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 5 WHERE player = 'deepseek' AND seat = 'third_opinion'"
            )


async def test_a_call_asked_again_waits_from_then(hub: Hub, su: Any) -> None:
    async with bench(su, hub, web=("deepseek",)):
        await su.execute("UPDATE substitutes.seats SET per_day = 1000 WHERE player = 'deepseek'")
        try:
            holding = await hub.companies.holding()
            async with hub.db.tx(await hub.companies.ids()) as tx:
                call = await S.seat_call(tx, hub, A.SERVICE, seat="quick_search", input_md="سوال",
                                         company_id=holding.id)  # fmt: skip
            assert call["queued_at"] is None
            # a broken page: asked once more with the page reloaded, its queue clock from now
            await S.web_jobs(hub, FakeEgress({"ok": False, "error": "recipe_failed", "step": "x"}))
            row = await _call(su, call["id"])
            assert (row["state"], row["attempt"]) == ("queued", 2)
            assert row["queued_at"] is not None and row["queued_at"] >= row["created_at"]
            # (as if the first attempt took ten minutes)
            await su.execute(
                "UPDATE substitutes.calls SET queued_at = created_at + interval '10 minutes' WHERE id = $1",
                call["id"],
            )
            async with hub.db.tx(await hub.companies.ids()) as tx:
                assert await S.deadline_of(tx, call["id"]) == (
                    row["created_at"] + timedelta(minutes=10) + S.QUEUE_DEADLINE
                )
                await S.expire_stale(tx, hub, row["created_at"] + timedelta(minutes=16))
            assert (await _call(su, call["id"]))["state"] == "queued"
        finally:
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 60 WHERE player = 'deepseek' AND seat = 'quick_search'"
            )
            await su.execute(
                "UPDATE substitutes.seats SET per_day = 5 WHERE player = 'deepseek' AND seat = 'third_opinion'"
            )


async def test_an_end_whose_delivery_failed_is_delivered_once_more_never_twice(
    hub: Hub, su: Any, monkeypatch: Any
) -> None:
    async with bench(su, hub, web=("gpt",)):
        holding = await hub.companies.holding()

        async def ended_undelivered() -> Any:
            return await su.fetchval(
                """INSERT INTO substitutes.calls (company_id, player, seat, via, task, state, state_reason,
                       caller_kind, caller_code, timeout_s, day, month_key, finished_at)
                   VALUES ($1, 'gpt', 'assistant_errand', 'web', 'text', 'failed', 'timeout', 'agent',
                           'HQ-PA', 300, current_date, '1405-08', now() - interval '5 minutes')
                   RETURNING id""",
                holding.id,
            )

        first = await ended_undelivered()
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await S.expire_stale(tx, hub) >= 1
        row = await _call(su, first)
        assert row["delivered_at"] is not None and row["reply_work_id"] is not None
        reply = await _reply(su, first)
        assert reply["code"] == "HQ-PA" and "longer than its time limit" in reply["brief"]
        # a delivery that fails again is given up (logged), never tried a third time
        second = await ended_undelivered()
        tries: list[Any] = []

        async def broken(tx: Any, hub: Any, call: dict[str, Any]) -> None:
            tries.append(call["id"])
            raise RuntimeError("the delivery broke")

        monkeypatch.setattr(S, "deliver_to_agent", broken)
        for _ in range(2):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await S.expire_stale(tx, hub)
        row = await _call(su, second)
        assert tries.count(second) == 1  # once more, never twice
        assert row["delivered_at"] is not None and row["reply_work_id"] is None


# ============================================================ the ready seat ==
async def test_a_work_takes_the_seat_its_player_can_answer_now(hub: Hub, su: Any) -> None:
    from hq_api.domain import players as PL

    # GPT signed in on its CLI only: its web content_draft (first of TEXT_SEATS) is passed over
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "content_draft", 5)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            found = await PL.text_seat(tx, "gpt")
            assert found is not None
            assert (found[1]["seat"], found[1]["via"]) == ("assistant_errand", "cli")
            assert await PL.availability(tx, "gpt") is None
    # its web chat signed in: content_draft, the strong model
    async with bench(su, hub, web=("gpt",)), hub.db.tx(await hub.companies.ids()) as tx:
        found = await PL.text_seat(tx, "gpt")
        assert found is not None and found[1]["seat"] == "content_draft"
    # nobody signed in: the first seat it has on, whose reason the caller reads
    async with bench(su, hub), hub.db.tx(await hub.companies.ids()) as tx:
        found = await PL.text_seat(tx, "gpt")
        assert found is not None and found[1]["seat"] == "content_draft"
        assert await PL.availability(tx, "gpt") == "signed_out"
    # an unnamed draft goes to the player that can write it now (ChatGPT signed out, Gemini in)
    async with bench(su, hub, web=("gemini",)), hub.db.tx(await hub.companies.ids()) as tx:
        found = await S.holder(tx, "content_draft", None)
        assert found is not None and found[0]["player"] == "gemini"
    async with bench(su, hub, web=("gpt", "gemini")), hub.db.tx(await hub.companies.ids()) as tx:
        found = await S.holder(tx, "content_draft", None)
        assert found is not None and found[0]["player"] == "gpt"


async def test_one_pass_makes_at_most_its_cap_of_reply_works_and_owes_the_rest(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """The first pass after a deploy: every call stuck since the deadlock ends at once, but only
    REPLIES_PER_PASS reply works are made; a caller whose work closed gets none; the rest are owed
    to the next pass, never lost."""
    co = (await new_company())["code"]
    s = await _session(client, owner, su, co)
    other = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    closed_ref = other["routes"][0]["work_ref"]
    await refuse_queued(su, closed_ref)
    await su.execute("UPDATE work.work SET status = 'cancelled' WHERE ref = $1", closed_ref)
    closed_id = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", closed_ref)
    holding = await hub.companies.holding()

    async def stuck(company: Any, caller: str, work: Any, hours: float) -> Any:
        return await su.fetchval(
            """INSERT INTO substitutes.calls (company_id, player, seat, via, task, state, caller_kind,
                   caller_code, purpose_kind, purpose_ref, input_md, timeout_s, day, month_key,
                   created_at)
               VALUES ($1, 'gpt', 'assistant_errand', 'web', 'text', 'queued', 'agent', $2,
                       CASE WHEN $3::text IS NULL THEN NULL ELSE 'caller_work' END, $3, 'x', 300,
                       current_date, '1405-08', now() - make_interval(secs => $4))
               RETURNING id""",
            company,
            caller,
            str(work) if work is not None else None,
            hours * 3600,
        )

    try:
        async with bench(su, hub, web=("gpt",)):
            incident = await stuck(s["company_id"], s["holder"], s["root_id"], 20)
            gone = await stuck(s["company_id"], s["holder"], closed_id, 19)
            rest = [await stuck(holding.id, "HQ-PA", None, 18 - i / 10) for i in range(28)]
            ids = [str(x) for x in (incident, gone, *rest)]
            async with await all_tx(hub) as tx:
                await S.expire_stale(tx, hub)
            rows = {
                str(r["id"]): r
                for r in await su.fetch(
                    "SELECT * FROM substitutes.calls WHERE id = ANY($1::uuid[])", ids
                )
            }
            # every one ended at once
            assert all(
                (r["state"], r["state_reason"]) == ("failed", "not_claimed") for r in rows.values()
            )
            made = [i for i in ids if rows[i]["reply_work_id"] is not None]
            assert len(made) == S.REPLIES_PER_PASS == 25
            # the stalled session's own call: its holder's reply and the session's line
            reply = await _reply(su, incident)
            assert reply is not None and reply["code"] == s["holder"]
            assert "ChatGPT جواب نداد (نوبتش نرسید)" in await _last_line(su, s["conv"])
            # its work closed: nobody waits, no reply work (marked delivered)
            g = rows[str(gone)]
            assert g["delivered_at"] is not None and g["reply_work_id"] is None
            # the rest are owed, then delivered on the next pass
            owed = [i for i in ids if rows[i]["delivered_at"] is None]
            assert len(owed) == 4 and all(rows[i]["delivery_owed"] for i in owed)
            async with await all_tx(hub) as tx:
                await S.expire_stale(tx, hub)
            after = await su.fetch(
                "SELECT reply_work_id FROM substitutes.calls WHERE id = ANY($1::uuid[])", owed
            )
            assert all(r["reply_work_id"] is not None for r in after)
            await refuse_queued(su, reply["ref"])
    finally:
        await _end_run(su, s)


async def test_a_paced_call_and_a_call_behind_a_retry_keep_their_clock(hub: Hub, su: Any) -> None:
    """Two waits that are a turn, not "nobody took it": the 60-second pace of the call's own
    player (the next pass skips it, and starts another player's long job), and a retried job
    ahead of it (the passes take each queue by when a call was made)."""
    end = timedelta(seconds=900 + S.RUN_GRACE_S)
    async with bench(su, hub, web=("gpt", "gemini")):
        await per_day(su, "gpt", "creative", 5)
        await per_day(su, "gemini", "creative", 5)
        holding = await hub.companies.holding()

        async def ask(player: str, seat: str, task: str = "text") -> dict[str, Any]:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                row = await S.seat_call(tx, hub, A.SERVICE, seat=seat, input_md="x", player=player,
                                        company_id=holding.id, task=task)  # fmt: skip
            assert row["state"] == "queued", row
            return row

        async def run(call: dict[str, Any], at: str) -> dict[str, Any]:
            await su.execute(
                f"""UPDATE substitutes.calls SET state = 'running', claimed_at = {at}
                    WHERE id = $1""",
                call["id"],
            )
            return dict(await _call(su, call["id"]))

        async def deadline(call: dict[str, Any]) -> Any:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                return await S.deadline_of(tx, call["id"])

        # 1. ChatGPT's script joins inside ChatGPT's pace; the pass that skips it starts Gemini's
        # long image: the script waits for that pass. A job taken later than two minutes after it
        # joined does not hold it.
        script = await ask("gpt", "assistant_errand")
        image = await run(await ask("gemini", "creative", "image"), "clock_timestamp()")
        late = await ask("gemini", "creative", "image")
        await run(late, f"'{(script['created_at'] + timedelta(minutes=3)).isoformat()}'")
        assert await deadline(script) == image["claimed_at"] + end + S.QUEUE_DEADLINE
        await su.execute(
            "UPDATE substitutes.calls SET state = 'done', finished_at = now() WHERE id = ANY($1)",
            [image["id"], late["id"]],
        )
        # 2. A ChatGPT cover made before the script, asked again (its page reloaded) and taken
        # five minutes after the script: still ahead of it in ChatGPT's queue
        cover = await ask("gpt", "creative", "image")
        script = await ask("gpt", "assistant_errand")
        await su.execute(
            "UPDATE substitutes.calls SET queued_at = $2, attempt = 2 WHERE id = $1",
            cover["id"],
            script["created_at"] + timedelta(minutes=4),
        )
        cover = await run(cover, f"'{(script['created_at'] + timedelta(minutes=5)).isoformat()}'")
        assert await deadline(script) == cover["claimed_at"] + end + S.QUEUE_DEADLINE
        await su.execute(
            "UPDATE substitutes.calls SET state = 'done', finished_at = now() WHERE id = ANY($1)",
            [cover["id"], script["id"]],
        )
        # 3. a ChatGPT job ahead, taken 90 s after the script joined, done in 30 s; the next pass
        # rests ChatGPT (its pace) and takes Gemini's long image 70 s after that job: the script
        # waits for the image (its pace window counts from the last job ahead of it)
        ahead = await ask("gpt", "assistant_errand")
        script = await ask("gpt", "assistant_errand")
        t = script["created_at"]
        await su.execute(
            """UPDATE substitutes.calls SET state = 'done', claimed_at = $2, finished_at = $3
               WHERE id = $1""",
            ahead["id"],
            t + timedelta(seconds=90),
            t + timedelta(seconds=120),
        )
        image = await run(
            await ask("gemini", "creative", "image"),
            f"'{(t + timedelta(seconds=160)).isoformat()}'",
        )
        assert await deadline(script) == image["claimed_at"] + end + S.QUEUE_DEADLINE
        await _settle(su)


async def test_an_end_nobody_waits_for_any_more_makes_no_reply_work(hub: Hub, su: Any) -> None:
    """A deploy finds calls stuck for days (the CLI queue while its runner was off, the web lane
    deadlock): they end, marked delivered and logged, without a reply work; so does a call whose
    caller's work is gone. A fresh call with no work (a message's run) still gets its reply."""
    async with bench(su, hub, web=("gpt",)):
        holding = await hub.companies.holding()

        async def stuck(hours: float, purpose: str | None, ref: str | None) -> Any:
            return await su.fetchval(
                """INSERT INTO substitutes.calls (company_id, player, seat, via, task, state,
                       caller_kind, caller_code, purpose_kind, purpose_ref, input_md, timeout_s, day,
                       month_key, created_at)
                   VALUES ($1, 'gpt', 'assistant_errand', 'web', 'text', 'queued', 'agent', 'HQ-PA',
                           $2, $3, 'x', 300, current_date, '1405-08',
                           now() - make_interval(secs => $4))
                   RETURNING id""",
                holding.id,
                purpose,
                ref,
                hours * 3600,
            )

        old = await stuck(30, None, None)
        gone = await stuck(1, S.CALLER_WORK, str(uuid.uuid4()))
        fresh = await stuck(1, None, None)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await S.expire_stale(tx, hub)
        for cid in (old, gone):
            row = await _call(su, cid)
            assert (row["state"], row["state_reason"]) == ("failed", "not_claimed")
            assert row["delivered_at"] is not None and row["reply_work_id"] is None
        row = await _call(su, fresh)
        assert row["reply_work_id"] is not None
