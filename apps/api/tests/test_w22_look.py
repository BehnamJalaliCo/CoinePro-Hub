"""⟨1.33⟩ What the 1.0.1 look reads (contract §55): the live work line and the session's mood,
the publish desk, the Claude accounts with today's meter, and one row for one publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import asyncpg
import httpx

from hq_api.domain import limits as LM
from hq_api.domain import publish_desk as PD
from hq_api.domain import session_activity as SA
from hq_api.hub import Hub

from .test_p17_runners import take
from .test_p21_routing_orders import auto_hiring, envelope  # noqa: F401 - the fixture
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w13_second_account import MAIN, SECOND, _quota
from .test_w14_workshop import run_ask, workshop
from .test_w17_session_publish import an_output, tap
from .test_w19_publish_time import answer, asked, connected


# ======================================================= §55.1 the live line ==
def test_a_turns_event_is_said_in_the_owners_words_or_not_at_all() -> None:
    line = SA.turn_line
    said = {"role": "assistant", "text": "صحنه‌ی سوم را رندر میکنم.\nبعد صدا را میگذارم."}
    assert line("message", said) == "صحنه‌ی سوم را رندر میکنم."
    # English narration, a tool's result and an unknown tool say nothing he can read
    assert line("message", {"role": "assistant", "text": "Rendering scene 3 now."}) is None
    assert line("progress", {"tool_use_id": "t1", "text": "ok"}) is None
    assert line("progress", {"tool": "SomethingNew"}) is None
    # a file is its name only, never its path; a command is never shown
    wrote = line("file_change", {"path": "/home/studio/hq-workspace/W-000210/out/reel.mp4"})
    assert wrote == "فایل «reel.mp4» را مینویسد"
    assert line("command", {"cmd": "ffmpeg -i a.mp4 b.mp4"}) == "دستور اجرا میکند"
    assert line("progress", {"tool": "WebSearch"}) == "در وب میگردد"
    # a hub tool of a direct turn reads as that tool's own verb
    verb = line("progress", {"tool": "mcp__hq__speech_make"})
    assert verb == SA.TOOLS_FA["speech.make"][1]


def test_the_mood_is_one_word_by_code() -> None:
    now = datetime.now(UTC)

    def w(kind: str, step: int = 0, last: str | None = None) -> SA.Worker:
        return SA.Worker(who_fa="x", company_fa="y", work_title_fa="z", started_at=now,
                         step=step, doing_fa="d", kind=kind, last_fa=last)  # type: ignore[arg-type]  # fmt: skip

    assert SA.mood_of([w("run")], None, None) == "thinking"
    assert SA.mood_of([w("run", step=2)], "q", None) == "working"
    assert SA.mood_of([w("workshop")], None, None) == "thinking"
    assert SA.mood_of([w("direct", last="فایل را مینویسد")], None, None) == "working"
    assert SA.mood_of([], "مسئول میپرسد", "گیر") == "waiting"
    assert SA.mood_of([], None, "گیر") == "stuck"
    assert SA.mood_of([], None, None) == "idle"


async def test_a_workshop_turn_shows_its_cap_and_its_last_line(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(client, owner, f"برای {co} {words()} یک موشن‌گرافی بساز")
    [route] = out["routes"]
    r = await run_ask(client, route["to"], {"work": route["work_ref"], "brief": "ATR را بساز"})
    assert r.status_code == 201, r.text
    job = await take(client, rn)

    async def turn() -> tuple[dict[str, Any], dict[str, Any]]:
        got = await client.get(f"/api/v1/orders/{out['ref']}/activity", headers=owner)
        assert got.status_code == 200, got.text
        act = got.json()
        return act, next(w for w in act["working"] if w["kind"] == "workshop")

    act, w = await turn()
    assert w["cap_s"] == job["timeout_s"] == 3600 and w["last_fa"] is None
    assert act["mood"] in ("thinking", "working") and act["mood_fa"]

    def ev(seq: int, type_: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"seq": seq, "type": "session_event",
                "data": {"type": type_, "at": "2026-11-10T10:00:00Z", "summary_fa": "", "data": data}}  # fmt: skip

    events = [
        ev(1, "message", {"role": "assistant", "text": "صحنه‌ی سوم را رندر میکنم."}),
        ev(2, "progress", {"tool_use_id": "t", "is_error": False, "text": "done"}),
    ]
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events", json={"events": events}, headers=rn["h"]
    )
    assert r.status_code == 200, r.text
    act, w = await turn()
    assert w["last_fa"] == "صحنه‌ی سوم را رندر میکنم." and w["last_at"] is not None
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events",
        json={"events": [ev(3, "file_change", {"path": "out/reel.mp4", "tool": "Write"})]},
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text
    act, w = await turn()
    assert w["last_fa"] == "فایل «reel.mp4» را مینویسد"
    assert all(x["kind"] in ("run", "workshop", "direct", "server") for x in act["working"])


# ============================================ §55.2 and §55.4 the publish desk ==
def test_a_package_is_the_video_with_its_cover_or_the_pictures() -> None:
    def f(name: str, mime: str) -> dict[str, Any]:
        return {"id": name, "name": name, "mime": mime, "size": 1}

    reel = PD.package([f("a.png", "image/png"), f("cover.jpg", "image/jpeg"), f("r.mp4", "video/mp4")])  # fmt: skip
    assert reel is not None and reel["kind"] == "reel" and reel["file"]["name"] == "r.mp4"
    assert reel["cover"]["name"] == "cover.jpg"
    post = PD.package([f("one.png", "image/png"), f("caption.txt", "text/plain")])
    assert post is not None and post["kind"] == "post" and post["cover"] is None
    many = PD.package([f(f"{i}.png", "image/png") for i in range(12)])
    assert many is not None and many["kind"] == "carousel" and many["n"] == 10
    assert PD.package([f("report.pdf", "application/pdf")]) is None


async def test_the_desk_follows_an_output_from_ready_to_published(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]

    async def desk() -> dict[str, list[dict[str, Any]]]:
        r = await client.get("/api/v1/publish-desk", params={"company": co}, headers=owner)
        assert r.status_code == 200, r.text
        return r.json()

    # 1. ready, before the company's path is set: a card with no action
    d = await desk()
    [card] = d["ready"]
    assert d["queue"] == [] and d["done"] == []
    assert card["output"] == output and card["order"] == order and card["company"] == co
    assert card["kind"] == "reel" and card["file"]["id"] == reel and card["cover"]["id"] == cover
    assert card["state"] == "ready" and card["publish"] is None and card["route_ready"] is False

    # 2. the path is set; he sets it for a time: it waits in the queue, one row for it
    rn = await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=5)
    r = await tap(client, owner, order, {"output": output, "file_id": reel, "caption": "سه سطح",
                                         "cover_file_id": cover, "scheduled_at": later.isoformat()})  # fmt: skip
    assert r.status_code == 202, r.text
    first = r.json()
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:7", "url": None})
    d = await desk()
    [card] = d["queue"]
    assert d["ready"] == [] and d["done"] == []
    assert card["state"] == "scheduled" and card["route_ready"] is True
    assert card["account"] == "pro.chart" and card["publish"]["job"] == first["job"]
    assert datetime.fromisoformat(card["at"]) == later.replace(microsecond=later.microsecond)

    # 3. after its time the hub asks IG-Hub with one more job: still ONE row, the newest job's,
    #    that says when it was first sent (§55.4)
    assert await asked(hub, su, output, later + timedelta(minutes=5)) == 1
    q = await take(client, rn)
    assert q["args"]["meta"]["check"] == "pub:7"
    await answer(
        client, rn, q["id"], {"external_id": "1801", "url": "https://www.instagram.com/reel/Cz9/"}
    )
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    [p] = rep["publishes"]
    assert p["state"] == "published" and p["job"] == q["id"] and p["at"] == first["at"]
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert [x["job"] for x in panel["publishes"]] == [q["id"]]
    d = await desk()
    [card] = d["done"]
    assert d["ready"] == [] and d["queue"] == []
    assert card["state"] == "published" and card["publish"]["url"].endswith("/Cz9/")

    # 4. another company's desk does not show it, and an unknown company is 404
    other = await client.get("/api/v1/publish-desk", params={"company": ig["code"]}, headers=owner)
    assert other.status_code == 200 and other.json()["done"] == []
    assert (await client.get("/api/v1/publish-desk", params={"company": "ZZZZ"}, headers=owner)
            ).status_code == 404  # fmt: skip
    assert (await client.get("/api/v1/publish-desk")).status_code == 401


async def test_an_output_he_took_back_is_ready_again(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("one.png",))
    order, output, (one,) = made["order"], made["output"], made["files"]
    await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=3)
    r = await tap(client, owner, order, {"output": output, "file_id": one, "kind": "post",
                                         "caption": "سطح طلا", "scheduled_at": later.isoformat()})  # fmt: skip
    assert r.status_code == 202, r.text
    r = await client.post(f"/api/v1/publishes/{r.json()['job']}/cancel", headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "cancelled", r.text
    r = await client.get("/api/v1/publish-desk", params={"company": co}, headers=owner)
    d = r.json()
    assert [c["state"] for c in d["done"]] == ["cancelled"] and d["queue"] == []
    [again] = d["ready"]
    assert again["kind"] == "post" and again["publish"] is None and again["state"] == "ready"


# ================================================== §55.3 the limit at a glance ==
async def test_each_claude_account_is_a_ring_and_one_of_them_works(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: asyncpg.Connection
) -> None:
    keys = ["claude-max", "claude-max-2"]
    before = await su.fetch("SELECT key, status FROM llm.connections WHERE key = ANY($1)", keys)
    saved = await su.fetch(
        """SELECT q.* FROM llm.quota_status q JOIN llm.connections c ON c.id = q.connection_id
           WHERE c.key = ANY($1)""",
        keys,
    )
    await su.execute("UPDATE llm.connections SET status = 'enabled' WHERE key = ANY($1)", keys)
    await su.execute(
        """DELETE FROM llm.quota_status
           WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))""",
        keys,
    )
    both = SimpleNamespace(
        secrets=SimpleNamespace(runner_claude_token_main=MAIN, runner_claude_token=SECOND)
    )

    async def read(h: Any = both) -> tuple[list[LM.ClaudeAccount], bool]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await LM.accounts(tx, h, await tx.scalar("SELECT now()"))

    try:
        rows, waiting = await read()
        assert [(a.key, a.state, a.name_fa) for a in rows] == [
            ("claude-max", "working", "اکانت اصلی"), ("claude-max-2", "ready", "اکانت دوم"),
        ]  # fmt: skip
        assert not waiting and rows[0].utilization is None and rows[0].resets_at is None
        # the main one is full: the second one works, and the main one says when it resets
        await _quota(su, "claude-max", "warning", "0.99", "2 days")
        await _quota(su, "claude-max-2", "warning", "0.40", "1 day")
        rows, waiting = await read()
        assert [a.state for a in rows] == ["full", "working"] and not waiting
        assert rows[0].utilization == Decimal("0.99") and rows[0].resets_at is not None
        assert rows[0].window_fa == "پنجره‌ی هفتگی" and rows[1].utilization == Decimal("0.40")
        # both full: everything waits
        await _quota(su, "claude-max-2", "limited", "1", "1 day")
        rows, waiting = await read()
        assert [a.state for a in rows] == ["full", "full"] and waiting
        # the main one's window reset: it works again and its ring is empty
        await _quota(su, "claude-max", "warning", "0.99", "-1 minute")
        rows, waiting = await read()
        assert rows[0].state == "working" and rows[0].utilization == Decimal("0")
        assert rows[0].resets_at is None and not waiting
        # switched off on the hub: off, and never the one that works
        await su.execute("UPDATE llm.connections SET status = 'disabled' WHERE key = 'claude-max'")
        rows, waiting = await read()
        assert [a.state for a in rows] == ["off", "full"] and waiting
        # nothing of an account ever leaves but its name and its window
        r = await client.get("/api/v1/treasury/limits", headers=owner)
        assert r.status_code == 200, r.text
        assert MAIN not in r.text and SECOND not in r.text
        body = r.json()
        assert set(body) == {"accounts", "waiting", "today"}
        assert body["today"]["cap"] == hub.settings.agent_daily_token_cap
        assert (await client.get("/api/v1/treasury/limits")).status_code == 401
    finally:
        await su.execute(
            """DELETE FROM llm.quota_status
               WHERE connection_id IN (SELECT id FROM llm.connections WHERE key = ANY($1))""",
            keys,
        )
        for r0 in saved:
            cols = list(r0.keys())
            await su.execute(
                f"INSERT INTO llm.quota_status ({', '.join(cols)}) VALUES "
                f"({', '.join(f'${i + 1}' for i in range(len(cols)))})",
                *[r0[c] for c in cols],
            )
        for r0 in before:
            await su.execute(
                "UPDATE llm.connections SET status = $2 WHERE key = $1", r0["key"], r0["status"]
            )


async def test_todays_meter_has_three_marks(hub: Hub, su: asyncpg.Connection) -> None:
    async def meter(cap: int) -> LM.TodayMeter:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await LM.today(tx, cap, datetime.now(UTC))

    spent = (await meter(1)).spent
    open_ = await meter(0)
    assert open_.cap == 0 and open_.state == "calm" and open_.note_fa == LM.NOTE_FA["open"]
    assert open_.resets_at > datetime.now(UTC)
    base = max(spent, 1)
    assert (await meter(base * 10)).state == "calm"
    if spent > 0:
        assert (await meter(int(spent / 0.75))).state == "warm"
        assert (await meter(int(spent / 0.95))).state == "near"
        full = await meter(spent)
        assert full.state == "full" and full.share >= 1
