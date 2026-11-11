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

import asyncio
import importlib.util
from collections.abc import Callable
from dataclasses import replace
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

from .conftest import AGENT_KEY, agent_headers
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
                                  "created_at", "claimed_at", "deadline_at"}  # fmt: skip
                await S.expire_stale(tx, hub, deadline - timedelta(seconds=1))
            assert (await _call(su, row["id"]))["state"] == "queued"
            async with await all_tx(hub) as tx:
                assert await S.pending_for(tx, [s["root_id"]], deadline) == []
                assert await S.expire_stale(tx, hub, deadline) >= 1
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
        hub.settings = replace(hub.settings, substitutes_runner=False)
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
        # egress answers `off` (the profile browser is not running): a failure, delivered
        await su.execute(
            "UPDATE substitutes.players SET web_state = 'signed_in', web_last_job_at = NULL WHERE player = 'gpt'"
        )
        third = await ask("خلاصه‌ی سوم")
        await S.web_jobs(hub, FakeEgress({"ok": False, "error": "off", "detail": "not running"}))
        row = await _call(su, third)
        assert (row["state"], row["state_reason"]) == ("failed", "browser_unavailable")
        reply = await _reply(su, third)
        assert reply is not None and "browser on the hub was not available" in reply["brief"]
        await refuse_queued(su, reply["ref"])
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
            fits = await S.seat_call(tx, hub, A.SERVICE, seat="assistant_errand",
                                     input_md="x" * S.WEB_PROMPT_LIMIT, company_id=holding.id)  # fmt: skip
        assert (long["state"], long["state_reason"], long["input_md"]) == (
            "skipped",
            "too_long",
            None,
        )
        assert fits["state"] == "queued"


async def test_one_broken_web_job_never_stops_the_other_players_which_run_at_once(
    client: httpx.AsyncClient, hub: Hub, su: Any
) -> None:
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

            class Both(FakeEgress):
                """Each job waits for the other: only jobs that run at once both get through."""

                def __init__(self) -> None:
                    super().__init__()
                    self.together = asyncio.Event()

                async def web(self, **kw: Any) -> dict[str, Any]:
                    self.calls.append(kw)
                    if len(self.calls) == 2:
                        self.together.set()
                    await asyncio.wait_for(self.together.wait(), 5)
                    if kw["account"] == "chatgpt-web":
                        raise RuntimeError("the worker broke on this job")
                    return {"ok": True, "text_md": "پاسخ عمومی", "recipe_version": "1"}

            fake = Both()
            out = await S.web_jobs(hub, fake)
            assert len(fake.calls) == 2 and out["ran"] == 1, out
            g, d = await _call(su, gpt_call), await _call(su, ds["id"])
            assert (g["state"], g["state_reason"]) == ("failed", "worker_error")
            assert d["state"] == "done"
            reply = await _reply(su, gpt_call)
            assert reply is not None and "internal error" in reply["brief"]
            await refuse_queued(su, reply["ref"])
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
    tr = su.transaction()
    await tr.start()
    try:
        # idempotent where the seat is there already: nothing changes, no audit row
        audits = await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE target_ref = 'gpt:content_draft'"
        )
        await su.execute(m.UPGRADE)
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
        await su.execute(m.UPGRADE)
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
