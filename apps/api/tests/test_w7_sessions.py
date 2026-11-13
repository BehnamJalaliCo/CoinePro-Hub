"""Prompt 25, W7 (contract §35.1-§35.4, §35.7): every order a session. The owner, 2026-11-06:
«هر فرمان من باید یک سشن خودش رو داشته باشه تا بتونیم به نتیجه برسونیم و کار رو که اوکی کردیم و همه
چی تموم شد سشن بایگانی بشه یا پاک بشه».

- every routed order has a holder and its talk at once (a question single: the advisor's work);
- the badge by code (your_turn, ready, stuck, moving, closed), streamed as `session.updated`;
- the plan: the holder's steps (`order.ack`) ticked by `order.progress`, the owner's own lines;
- the order never ends by itself: delivered root works make it `ready`; only `close` ends it;
  `reopen` undoes it; `hide` takes it off the lists;
- participants: people (any persona key) and a player answering through its seat; «نظر همه»;
- the session's cards (delegate, budget, group, line, a hire with its company) run the order's
  own routes and become steps of the order;
- a second ask joins the open turn and the reply wakes both askers; an open turn reminds the owner
  once; a reply after a talk-loop stop restarts the order; a reply that wakes nothing says why;
- a council's «اجرا کن» inside a session continues the same order.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from hq_api.domain import humanize as HZ
from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import players as PL
from hq_api.domain import sessions as SE
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p12a_substitutes import bench, claim, done, per_day
from .test_p21_routing_orders import (  # noqa: F401
    all_tx,
    auto_hiring,
    deliver,
    envelope,
    make_order,
    report,
)
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture

WORK_TEXT = "برای {co} گزارش فروش هفته را آماده کن {w}"


def plain(*texts: Any) -> None:
    for t in texts:
        if isinstance(t, str) and t:
            assert HZ.check(t) == [], (t, HZ.check(t))


async def refuse_queued(su: Any, *work_refs: str) -> None:
    """The runs the works' creation queued are gone (so a wake can queue one)."""
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM work.work w WHERE w.id = r.work_id AND w.ref = ANY($1::text[]) AND r.state = 'queued'""",
        list(work_refs),
    )


async def woken(su: Any, ref: str) -> list[str]:
    """The works woken by the owner's replies on this order (the test database outlives a run
    and a round trip restarts the ref sequence: only this order's own rows)."""
    return [
        r["ref"]
        for r in await su.fetch(
            """SELECT w.ref FROM agents.runs r JOIN work.work w ON w.id = r.work_id
               WHERE r.reason = $1
                 AND r.queued_at >= (SELECT max(created_at) FROM owner.orders WHERE ref = $2)
               ORDER BY r.queued_at""",
            f"owner_reply:{ref}",
            ref,
        )
    ]


async def badges(su: Any, ref: str) -> list[str]:
    rows = await su.fetch(
        """SELECT payload FROM core.outbox WHERE subject LIKE '%.session.updated'
           AND payload->>'ref' = $1
           AND created_at >= (SELECT max(created_at) FROM owner.orders WHERE ref = $1)
           ORDER BY id""",
        ref,
    )
    return [json.loads(r["payload"])["data"]["badge"] for r in rows]


async def cards(
    client: httpx.AsyncClient, owner: dict[str, str], state: str = "open"
) -> dict[str, Any]:
    r = await client.get(f"/api/v1/sessions?state={state}&limit=200", headers=owner)
    assert r.status_code == 200, r.text
    return {c["ref"]: c for c in r.json()["items"]}


async def run_card(
    client: httpx.AsyncClient, owner: dict[str, str], card: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/talk/cards/{card['id']}/run", json={}, headers={**owner, **idem()}
    )


# ====================================================== §35.1 the session is the order ==
async def test_every_order_has_a_holder_and_a_session_at_once(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    assert out["pace"] == "auto" and out["talk_ref"]
    conv = await su.fetchrow(
        """SELECT persona, holder, holder_code, order_ref, closed_at FROM talk.conversations
           WHERE ref = $1""",
        out["talk_ref"],
    )
    assert conv["order_ref"] == ref and conv["closed_at"] is None
    assert conv["holder"] == conv["persona"] and conv["holder_code"] == route["to"]
    rep = await report(client, owner, ref)
    assert rep["conversation_ref"] == out["talk_ref"]
    assert rep["session"] == {**rep["session"], "state": "open", "badge": "moving", "hidden": False}
    assert rep["brief"]["done_fa"] and rep["brief"]["now_fa"] and rep["brief"]["need_fa"]
    assert rep["participants"][0] == {
        **rep["participants"][0], "kind": "holder", "key": conv["persona"], "company": co,
    }  # fmt: skip
    plain(rep["session"]["reason_fa"], *rep["brief"].values())
    assert "CEO" not in out["summary_fa"] and route["to"] not in out["summary_fa"]
    # a question with no company and no route: the advisor holds it (a root work of its own)
    q = await post_order(client, owner, f"یک کاری برای بهتر شدن اوضاع انجام بده {words()}")
    assert q["routes"][0]["kind"] == "question" and q["routes"][0]["work_ref"] and q["talk_ref"]
    adv = await su.fetchrow(
        "SELECT persona, holder_code FROM talk.conversations WHERE ref = $1", q["talk_ref"]
    )
    assert adv["persona"] == "advisor" and adv["holder_code"] == q["routes"][0]["to"]
    w = await su.fetchrow(
        """SELECT e.code, w.status FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.ref = $1""",
        q["routes"][0]["work_ref"],
    )
    assert w["code"] == q["routes"][0]["to"] and w["status"] == "queued"
    # both are on the list, moving
    listed = await cards(client, owner)
    assert listed[ref]["badge"] == "moving" and listed[ref]["holder"]["code"] == route["to"]
    assert listed[ref]["tasks"] == {"done": 0, "total": 0} and listed[ref]["pace"] == "auto"
    assert listed[q["ref"]]["holder"]["code"] == q["routes"][0]["to"]
    plain(listed[ref]["title_fa"], listed[ref]["reason_fa"], *listed[ref]["brief"].values())


async def test_the_sessions_list_pages_on_with_its_cursor(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    for _ in range(3):
        await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    seen: list[str] = []
    url = "/api/v1/sessions?state=all&limit=1"
    for i in range(3):
        r = await client.get(url, headers=owner)
        assert r.status_code == 200, r.text
        page = r.json()
        seen += [c["ref"] for c in page["items"]]
        if i < 2:
            assert page["next_cursor"], page
            url = f"/api/v1/sessions?state=all&limit=1&cursor={page['next_cursor']}"
    assert len(seen) == len(set(seen)) == 3
    # a cursor whose time is no time is the caller's mistake, never a 500
    url = "/api/v1/sessions?state=all&limit=1&cursor=WyJ4IiwieSIsInoiXQ"  # ["x","y","z"]
    bad = await client.get(url, headers=owner)
    assert bad.status_code == 422 and "cursor" in bad.json()["fields"], bad.text


async def test_a_company_without_a_manager_is_held_by_the_secretary_with_a_hire_card(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await su.execute(
        """UPDATE core.employees SET status = 'dismissed', dismissed_at = now()
           WHERE company_id = $1""",
        company["id"],
    )
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    [route] = out["routes"]
    assert route.get("work_ref") is None and route["note_fa"] and out["talk_ref"]
    conv = await su.fetchrow(
        "SELECT id, persona, holder FROM talk.conversations WHERE ref = $1", out["talk_ref"]
    )
    assert conv["persona"] == "secretary" and conv["holder"] == "secretary"
    card = await su.fetchrow(
        "SELECT kind, payload FROM talk.cards WHERE conversation_id = $1", conv["id"]
    )
    assert card["kind"] == "hire" and json.loads(card["payload"])["company"] == co
    rep = await report(client, owner, out["ref"])
    assert rep["participants"][0]["key"] == "secretary" and rep["session"]["state"] == "open"


# ======================================================= §35.2-§35.3 badges, plan, close ==
async def test_the_session_waits_for_the_owner_and_ends_only_by_the_owners_hand(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    # no department named: the company's CEO holds it (and may delegate to a manager below)
    out = await post_order(client, owner, f"برای {co} برنامه‌ی سه ماه آینده را آماده کن {words()}")
    ref, talk_ref = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    assert holder == f"{co}-CEO"
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    h = await agent_headers(holder)
    # the holder's plan with its steps: the session's tasks
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack",
        headers=h,
        json={"plan_fa": "سه قدم", "steps": ["جمع کردن عددها", "نوشتن گزارش", "فرستادن"]},
    )
    assert r.status_code == 200, r.text
    tasks = r.json()["tasks"]
    assert [t["title_fa"] for t in tasks] == ["جمع کردن عددها", "نوشتن گزارش", "فرستادن"]
    assert all(t["by"] == "agent" and t["state"] == "todo" and t["who_fa"] for t in tasks)
    r = await client.post(
        f"/internal/v1/orders/{ref}/progress",
        headers=h,
        json={"step_fa": "عددها جمع شد", "done": [1]},
    )
    assert r.status_code == 200 and r.json()["tasks"][0]["state"] == "done"
    # the owner's own line, moved up and in hand
    r = await client.post(
        f"/api/v1/orders/{ref}/tasks", headers=owner, json={"title_fa": "نمودار هم بگذار"}
    )
    assert r.status_code == 201, r.text
    mine = r.json()
    assert mine["n"] == 4 and mine["by"] == "owner"
    r = await client.patch(
        f"/api/v1/orders/{ref}/tasks/{mine['id']}", headers=owner, json={"n": 2, "state": "doing"}
    )
    assert r.status_code == 200 and r.json()["n"] == 2 and r.json()["state"] == "doing"
    rep = await report(client, owner, ref)
    assert [t["n"] for t in rep["tasks"]] == [1, 2, 3, 4]
    assert rep["tasks"][1]["title_fa"] == "نمودار هم بگذار"
    assert rep["brief"]["now_fa"].startswith("در حال انجام")
    listed = await cards(client, owner)
    assert listed[ref]["tasks"] == {"done": 1, "total": 4}
    # the holder asks: your turn (streamed), the brief asks for the owner's answer
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask", headers=h, json={"question_fa": "نمودار هفتگی یا ماهانه؟"}
    )
    rep = r.json()
    assert rep["session"]["badge"] == "your_turn" and "میپرسد" in rep["session"]["reason_fa"]
    assert rep["brief"]["need_fa"] == "جواب تو" and rep["turn"]["asks"][0]["by"]["code"] == holder
    assert await badges(su, ref) == ["your_turn"]
    assert (await cards(client, owner))[ref]["badge"] == "your_turn"
    # no «where is your plan» nudge while the turn is open; the owner is reminded once
    await su.execute(
        "UPDATE owner.orders SET created_at = now() - interval '9 hours' WHERE ref = $1", ref
    )
    await su.execute(
        """UPDATE owner.order_reports SET ack = NULL, acked_at = NULL,
               turn = turn || jsonb_build_object('at', to_jsonb(now() - interval '7 hours'))
           WHERE ref = $1""",
        ref,
    )
    s = SimpleNamespace(
        order_ack_minutes=10, order_progress_hours=2, order_owner_hours=6, order_talk_limit=999
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.timers(tx, s, ref) == ["turn"]
        assert await OR.timers(tx, s, ref) == []  # once
    n = await su.fetchrow(
        """SELECT title_fa, link_ref FROM notify.notifications
           WHERE source_code = 'orders' AND title_fa LIKE 'هنوز منتظر جواب توست%' AND link_ref = $1""",
        talk_ref,
    )
    assert n is not None
    plain(n["title_fa"])
    # a second ask by someone else working on the order joins the turn
    child = await client.post(
        f"/internal/v1/work/{wid}/delegate",
        headers=h,
        json={"to": f"{co}-SALES-MGR", "title": "عددها"},
    )
    assert child.status_code == 201, child.text
    sales = await agent_headers(f"{co}-SALES-MGR")
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask", headers=sales, json={"question_fa": "عددهای کدام ماه؟"}
    )
    assert r.status_code == 200, r.text
    turn = r.json()["turn"]
    assert (
        len(turn["asks"]) == 2
        and "هفتگی" in turn["question_fa"]
        and "کدام ماه" in turn["question_fa"]
    )
    assert turn["asks"][1]["by"]["code"] == f"{co}-SALES-MGR"
    # the owner's word wakes both askers
    await refuse_queued(su, work_ref, child.json()["ref"])
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "ماهانه؛ مهر"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["turn"] is None and r.json()["session"]["badge"] == "moving"
    assert set(await woken(su, ref)) == {work_ref, child.json()["ref"]}
    # the works end: ready, told once, nothing ends by itself
    await su.execute(
        "UPDATE work.work SET status = 'cancelled', closed_at = now() WHERE id = $1",
        uuid.UUID(child.json()["id"]),
    )
    # ⟨2026-11-11⟩ the root of an order whose plan still has open tasks is not delivered: the
    # holder ticks the rest of its plan first
    r = await client.post(
        f"/internal/v1/orders/{ref}/progress", headers=h,
        json={"step_fa": "گزارش و نمودار آماده شد", "done": [2, 3, 4]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    await client.post(
        f"/internal/v1/work/{wid}/progress", headers=h, json={"note": "تمام", "pct": 100}
    )
    assert (await deliver(client, holder, wid, "گزارش فروش هفته")).status_code == 200
    rep = await report(client, owner, ref)
    assert rep["state"] == "delivered" and rep["summary"] is not None
    assert rep["session"]["state"] == "open" and rep["session"]["badge"] == "ready"
    assert rep["brief"]["need_fa"] == "تأیید و بستن"
    assert await su.fetchval("SELECT ended_at FROM owner.order_reports WHERE ref = $1", ref) is None
    assert (await badges(su, ref))[-1] == "ready"
    ready = await su.fetch(
        """SELECT title_fa FROM notify.notifications WHERE link_kind = 'order' AND link_ref = $1
           AND title_fa LIKE 'فرمان تو آماده%'
           AND created_at >= (SELECT max(created_at) FROM owner.orders WHERE ref = $1)""",
        ref,
    )
    assert len(ready) == 1
    plain(ready[0]["title_fa"])
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.timers(tx, s, ref) == []  # a ready session nudges nobody
    assert (await cards(client, owner))[ref]["badge"] == "ready"
    # ⟨1.19⟩ §37.4 a word after delivery is a revision: the holder's root goes back to work and
    # the holder is woken (no more `409 no open work`); delivered again, ready again
    await refuse_queued(su, work_ref)
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "ادامه"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["session"]["badge"] == "moving"
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "in_progress"
    assert (await woken(su, ref))[-1] == work_ref
    assert (await deliver(client, holder, wid, "گزارش فروش هفته")).status_code == 200
    assert (await report(client, owner, ref))["session"]["badge"] == "ready"
    # the owner's OK: the only end
    r = await client.post(f"/api/v1/orders/{ref}/close", headers=owner, json={"verdict": "ok"})
    assert r.status_code == 422  # Idempotency-Key
    key = idem()
    r = await client.post(
        f"/api/v1/orders/{ref}/close",
        headers={**owner, **key},
        json={"verdict": "ok", "note": "خوب بود"},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["state"] == "delivered" and rep["session"]["state"] == "closed"
    assert rep["session"]["badge"] == "closed" and rep["session"]["closed_at"]
    assert rep["steps"][-1]["who_fa"] == "مدیر کل" and rep["steps"][-1]["what_fa"].startswith(
        "تأیید و بستن"
    )
    again = await client.post(
        f"/api/v1/orders/{ref}/close",
        headers={**owner, **key},
        json={"verdict": "ok", "note": "خوب بود"},
    )
    assert again.status_code == 200 and again.headers.get("Idempotent-Replay") == "true"
    row = await su.fetchrow(
        "SELECT ended_at, closed_at FROM owner.order_reports WHERE ref = $1", ref
    )
    assert row["ended_at"] is not None and row["closed_at"] is not None
    assert await su.fetchval("SELECT closed_at FROM talk.conversations WHERE ref = $1", talk_ref)
    assert ref not in await cards(client, owner) and ref in await cards(client, owner, "closed")
    ended = await su.fetch(
        """SELECT title_fa FROM notify.notifications WHERE link_kind = 'order' AND link_ref = $1
           AND title_fa LIKE 'فرمان تو تحویل شد%'
           AND created_at >= (SELECT max(created_at) FROM owner.orders WHERE ref = $1)""",
        ref,
    )
    assert len(ended) == 1
    # a closed session takes no word, no card, no second close
    r = await client.post(
        f"/api/v1/talk/conversations/{talk_ref}/turns",
        json={"text": "یک چیز دیگر", "source": "typed"},
        headers={**owner, **idem()},
    )
    assert r.status_code == 409 and r.json()["message_fa"]
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "ادامه"}
    )
    assert r.status_code == 409
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 409
    # reopened: open again, the talk alive, still ready (the work was delivered)
    r = await client.post(f"/api/v1/orders/{ref}/reopen", headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["session"]["state"] == "open" and r.json()["session"]["badge"] == "ready"
    row = await su.fetchrow(
        "SELECT ended_at, closed_at FROM owner.order_reports WHERE ref = $1", ref
    )
    assert row["ended_at"] is None and row["closed_at"] is None
    assert (
        await su.fetchval("SELECT closed_at FROM talk.conversations WHERE ref = $1", talk_ref)
        is None
    )
    assert ref in await cards(client, owner)
    # hidden: off every list but `all`; nothing deleted
    r = await client.post(f"/api/v1/orders/{ref}/hide", headers=owner)
    assert r.status_code == 200 and r.json()["session"]["hidden"] is True
    assert ref not in await cards(client, owner) and ref not in await cards(client, owner, "closed")
    assert (await cards(client, owner, "all"))[ref]["hidden"] is True
    r = await client.post(f"/api/v1/orders/{ref}/unhide", headers=owner)
    assert r.status_code == 200 and r.json()["session"]["hidden"] is False
    assert ref in await cards(client, owner)
    # a cancel without a final output: cancelled, its open works closed, the plan dropped
    other = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    r = await client.post(
        f"/api/v1/orders/{other['ref']}/close", headers={**owner, **idem()}, json={"verdict": "ok"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "cancelled"
    assert (
        await su.fetchval(
            "SELECT status FROM work.work WHERE ref = $1", other["routes"][0]["work_ref"]
        )
        == "cancelled"
    )
    for text in [s["what_fa"] for s in rep["steps"]] + list(rep["summary"].values()):
        plain(text)


# ============================================================ §35.4 participants ==
async def test_people_and_a_player_join_the_session_and_everyone_speaks(
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
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    holder_key = await su.fetchval("SELECT holder FROM talk.conversations WHERE ref = $1", conv)
    url = f"/api/v1/orders/{ref}/participants"
    r = await client.post(url, headers=owner, json={"kind": "person", "key": "advisor"})
    assert r.status_code == 200, r.text
    r = await client.post(url, headers=owner, json={"kind": "person", "key": f"ceo@{other}"})
    assert r.status_code == 200, r.text
    keys = {p["key"]: p for p in r.json()["participants"]}
    assert keys[holder_key]["kind"] == "holder" and keys["advisor"]["kind"] == "person"
    assert keys[f"ceo@{other}"]["company"] == other
    assert (
        await client.post(url, headers=owner, json={"kind": "person", "key": holder_key})
    ).status_code == 409
    assert (
        await client.post(url, headers=owner, json={"kind": "person", "key": "ceo@ZZZZ"})
    ).status_code == 404
    # a player signed out is refused in plain words
    r = await client.post(url, headers=owner, json={"kind": "player", "key": "gpt"})
    assert r.status_code == 409 and "ChatGPT" in r.json()["message_fa"]
    async with bench(su, hub, cli=("gpt",)):
        for seat in PL.TEXT_SEATS:
            await per_day(su, "gpt", seat, 5)
        r = await client.post(url, headers=owner, json={"kind": "player", "key": "gpt"})
        assert r.status_code == 200, r.text
        player = next(p for p in r.json()["participants"] if p["kind"] == "player")
        assert player == {
            "key": "player:gpt",
            "kind": "player",
            "title_fa": "ChatGPT",
            "company": None,
        }
        detail = (await client.get(f"/api/v1/talk/conversations/{conv}", headers=owner)).json()
        assert "player:gpt" in detail["present"]
        assert any(t["show_md"] == "ChatGPT آمد." for t in detail["turns_page"]["items"])
        # the owner asks the player: its seat is called with the masked talk, the turn waits
        said = await say(client, owner, conv, "نظرت درباره‌ی این گزارش چیست؟", to="player:gpt")
        assert said["turn"]["by"] == "player:gpt" and said["answer"]["state"] == "streaming"
        assert talk["router"].bodies == []  # no hub model for a player
        job = (await claim(client))["job"]
        assert job is not None and "نظرت درباره" in job["input_md"]
        assert "The order you hold" in job["input_md"] and holder_key not in job["input_md"]
        r = await done(
            client, job["id"], ok=True, text_md="به نظر من گزارش خوب است و نمودار کم دارد."
        )
        assert r.status_code == 200 and r.json()["state"] == "done", r.text
        t = await su.fetchrow(
            "SELECT state, show_md, persona FROM talk.turns WHERE id = $1::uuid", said["turn"]["id"]
        )
        assert t["state"] == "done" and t["persona"] == "player:gpt"
        assert t["show_md"].startswith("**ChatGPT**") and "نمودار کم دارد" in t["show_md"]
        # «نظر همه»: each present participant once (the player too), then the holder sums up
        talk["router"].answers = [
            answer("نظر مشاور.", "نظر مشاور"),
            answer("نظر مدیرعامل دیگر.", "نظر مدیرعامل دیگر"),
            answer("جمع‌بندی من.", "جمع‌بندی"),
        ]
        said = await say(client, owner, conv, "نظر همه را بگو")
        turns = said["turns"]
        assert [t["by"] for t in turns] == ["advisor", f"ceo@{other}", "player:gpt", holder_key]
        job = (await claim(client))["job"]
        assert job is not None
        await done(client, job["id"], ok=True, text_md="نظر من: خوب است.")
        assert (
            await su.fetchval(
                "SELECT directive FROM talk.turns WHERE id = $1::uuid", turns[-1]["id"]
            )
            == "sum_up"
        )
        assert "Sum up" in talk["router"].bodies[-1]["system"]
        states = await su.fetch(
            "SELECT state FROM talk.turns WHERE id = ANY($1::uuid[])", [t["id"] for t in turns]
        )
        assert all(s["state"] == "done" for s in states)
    # the holder stays; the advisor leaves
    r = await client.delete(f"{url}/{holder_key}", headers=owner)
    assert r.status_code == 409
    r = await client.delete(f"{url}/advisor", headers=owner)
    assert r.status_code == 200 and "advisor" not in {p["key"] for p in r.json()["participants"]}
    rep = await report(client, owner, ref)
    assert any(s["what_fa"].endswith("از جلسه رفت") for s in rep["steps"])


# ================================================================= §35.4 the cards ==
async def test_the_sessions_cards_run_the_orders_routes_and_become_its_steps(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    auto_hiring: None,  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await envelope(su, company, 50_000_000)
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    work_ref = route["work_ref"]
    before = await su.fetchval("SELECT budget_tokens FROM work.work WHERE ref = $1", work_ref)
    offered = [
        {"kind": "delegate", "title_fa": "بسپار به فنی", "body_fa": "",
         "payload": {"to": "TECH", "text": "عددهای فروش را از سامانه بیرون بکش"}},
        {"kind": "budget", "title_fa": "بودجه بیشتر", "body_fa": "", "payload": {"tokens": 5000}},
        {"kind": "group", "title_fa": "کارگروه محتوا", "body_fa": "",
         "payload": {"company": co, "group": "content"}},
    ]  # fmt: skip
    talk["router"].answers = [answer("کارت‌ها آماده است.", cards=offered)]
    said = await say(client, owner, conv, "عددها را بسپار، بودجه بده، به کارگروه محتوا ببر")
    got = {c["kind"]: c for c in said["answer"]["cards"]}
    assert set(got) == {"delegate", "budget", "group"}
    assert all(
        not c["unsolicited"]
        for c in await su.fetch(
            "SELECT unsolicited FROM talk.cards WHERE turn_id = $1::uuid", said["turn"]["id"]
        )
    )
    assert "ON THIS ORDER" in talk["router"].bodies[0]["system"]
    # delegate: a child of the order's root for the sales manager, a task of the plan
    r = await run_card(client, owner, got["delegate"])
    assert r.status_code == 200, r.text
    [child_ref] = r.json()["made"]
    child = await su.fetchrow(
        """SELECT e.code, p.ref AS parent FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           JOIN work.work p ON p.id = w.parent_id WHERE w.ref = $1""",
        child_ref,
    )
    assert child["code"] == f"{co}-TECH-MGR" and child["parent"] == work_ref
    rep = await report(client, owner, ref)
    assert [t["work_ref"] for t in rep["tasks"]] == [child_ref]
    assert rep["steps"][-1]["what_fa"].startswith("سپردن کار انجام شد")
    # ⟨2026-11-07⟩ W9 D: the hand-over the card made is no step of its own (the card's line says it)
    assert not any(
        s["who_fa"] == "سامانه" and s["what_fa"].endswith("سپرده شد") for s in rep["steps"]
    )
    # budget: the root work's own
    r = await run_card(client, owner, got["budget"])
    assert r.status_code == 200 and r.json()["made"] == [work_ref], r.text
    after = await su.fetchval("SELECT budget_tokens FROM work.work WHERE ref = $1", work_ref)
    assert after == (before + 5000 if before else None)
    # group: the company joins the working group
    r = await run_card(client, owner, got["group"])
    assert r.status_code == 200 and r.json()["made"] == ["content"], r.text
    assert (
        await su.fetchval(
            """SELECT m.state FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           WHERE g.key = 'content' AND m.company_id = $1""",
            company["id"],
        )
        == "on"
    )
    # a line from a template and a hire for a company named explicitly (by the advisor, no manager)
    r = await client.post(
        f"/api/v1/orders/{ref}/participants",
        headers=owner,
        json={"kind": "person", "key": "advisor"},
    )
    assert r.status_code == 200
    offered = [
        {"kind": "line", "title_fa": "ریلز هفتگی", "body_fa": "",
         "payload": {"company": co, "template": "instagram_reel", "title_fa": "ریلز هفتگی"}},
        {"kind": "hire", "title_fa": "استخدام مسئول انتشار", "body_fa": "",
         "payload": {"company": co, "role": "publisher"}},
    ]  # fmt: skip
    talk["router"].answers = [answer("دو کارت.", cards=offered)]
    said = await say(
        client, owner, conv, "خط تولید ریلز راه بینداز و یک مسئول انتشار استخدام کن", to="advisor"
    )
    assert said["turn"]["by"] == "advisor"
    got = {c["kind"]: c for c in said["answer"]["cards"]}
    r = await run_card(client, owner, got["line"])
    assert r.status_code == 200, r.text
    [line_ref] = r.json()["made"]
    line = await su.fetchrow(
        "SELECT template, state, mode FROM lines.lines WHERE ref = $1 AND company_id = $2",
        line_ref,
        company["id"],
    )
    assert line is not None and line["template"] == "instagram_reel" and line["mode"] == "draft"
    r = await run_card(client, owner, got["hire"])
    assert r.status_code == 200, r.text
    [code] = r.json()["made"]
    assert await su.fetchrow(
        "SELECT 1 FROM core.employees WHERE code = $1 AND company_id = $2 AND role = 'publisher' AND status = 'active'",
        code,
        company["id"],
    )
    # ⟨2026-11-07⟩ §39 hired from inside the session: the new employee joins this same session
    present = await su.fetchval("SELECT present FROM talk.conversations WHERE ref = $1", conv)
    assert f"publisher@{co}" in present
    # a hire decided later (a manager's hire card) joins the session too, by its decision
    card_id = await su.fetchval(
        "SELECT id FROM talk.cards WHERE kind = 'hire' AND $1 = ANY(made)", code
    )
    await su.execute("UPDATE talk.cards SET made = ARRAY['D-999999'] WHERE id = $1", card_id)
    async with await all_tx(hub) as tx:
        joined = await SE.join_hired(tx, f"{co}-SCRIPT", "scriptwriter", co, "نویسنده",
                                     decision_ref="D-999999")  # fmt: skip
    assert joined == [conv]
    present = await su.fetchval("SELECT present FROM talk.conversations WHERE ref = $1", conv)
    assert f"scriptwriter@{co}" in present
    rep = await report(client, owner, ref)
    labels = [
        s["what_fa"].split(" انجام شد")[0] for s in rep["steps"] if "انجام شد" in s["what_fa"]
    ]
    assert labels == ["سپردن کار", "بودجه", "کارگروه", "خط تولید", "استخدام"]
    for s in rep["steps"]:
        plain(s["what_fa"], s["who_fa"])
    # a closed session runs no card
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200
    talk_before = await su.fetchval(
        "SELECT count(*) FROM lines.lines WHERE company_id = $1", company["id"]
    )
    r = await run_card(client, owner, got["line"])  # a done card answers what it made, no new line
    assert r.status_code == 200 and r.json()["made"] == [line_ref]
    assert (
        await su.fetchval("SELECT count(*) FROM lines.lines WHERE company_id = $1", company["id"])
        == talk_before
    )


# ========================================================= replies: W6 a, h, the lock ==
async def test_a_reply_restarts_a_stopped_order_and_says_why_when_nothing_wakes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    work_ref = out["routes"][0]["work_ref"]
    await su.execute("UPDATE owner.order_reports SET talk_stopped_at = now() WHERE ref = $1", ref)
    await refuse_queued(su, work_ref)
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "ادامه بده"}
    )
    assert r.status_code == 200, r.text
    steps = [s["what_fa"] for s in r.json()["steps"]]
    assert steps[-2:] == ["ادامه بده", OT.RESTARTED_FA]
    assert (
        await su.fetchval("SELECT talk_stopped_at FROM owner.order_reports WHERE ref = $1", ref)
        is None
    )
    assert await woken(su, ref) == [work_ref]
    assert not [b for b in r.json()["blockers"] if b["kind"] == "talk_loop"]
    # the company locked: the reply wakes nothing and the step says why, in plain words
    r = await client.post(
        "/api/v1/control/kill-switch",
        headers={**owner, **idem()},
        json={"scope": f"company:{co}", "state": "engaged", "reason": "آزمون"},
    )
    assert r.status_code == 200, r.text
    await refuse_queued(su, work_ref)
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "باز هم ادامه"}
    )
    assert r.status_code == 200, r.text
    last = r.json()["steps"][-1]
    assert last["who_fa"] == "سامانه" and last["what_fa"].startswith("جواب رسید ولی")
    plain(last["what_fa"])
    assert await woken(su, ref) == [work_ref]  # no second run
    assert r.json()["session"]["badge"] == "your_turn"  # locked: the owner's fix


# ======================================================= §35.1 «اجرا کن» inside a session ==
async def test_a_councils_plan_inside_a_session_continues_the_same_order(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    o = await make_order(hub, company, "تحلیل بازار آموزش آنلاین")
    ref, w = o["ref"], o["work"]
    await su.execute(
        """INSERT INTO work.councils (company_id, work_id, state, plan_md)
           VALUES ($1, $2, 'done', $3)""",
        company["id"],
        w["id"],
        "هدف: هر روز یک ریلز.\n| چه کسی | چه کاری | تا کی |\n|---|---|---|\n| مدیر رسانه | سه ریلز | پنجشنبه |",
    )
    orders_before = await su.fetchval("SELECT count(*) FROM owner.orders")
    await refuse_queued(su, w["ref"])
    r = await client.post(f"/api/v1/work/{w['id']}/council/run", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    assert r.json()["ref"] == ref and r.json()["routes"][0]["work_ref"] == w["ref"]
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before  # no new F-ref
    assert (
        await su.fetchval("SELECT order_ref FROM work.councils WHERE work_id = $1", w["id"]) == ref
    )
    assert await woken(su, ref) == [w["ref"]]
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["who_fa"] == "مدیر کل" and rep["steps"][-1]["what_fa"].startswith(
        "اجرا کن"
    )


async def test_a_councils_plan_on_an_order_with_nothing_open_makes_a_new_order(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """The order is not ended but has no open or delivered work: the same-order
    path gives way, and its claim of the key goes back with it (no 409
    idempotency_conflict from the new order's own claim)."""
    company = await new_company()
    o = await make_order(hub, company, "تحلیل بازار آموزش آنلاین")
    ref, w = o["ref"], o["work"]
    await su.execute(
        """INSERT INTO work.councils (company_id, work_id, state, plan_md)
           VALUES ($1, $2, 'done', $3)""",
        company["id"],
        w["id"],
        "هدف: هر روز یک ریلز.\n| چه کسی | چه کاری | تا کی |\n|---|---|---|\n| مدیر رسانه | سه ریلز | پنجشنبه |",
    )
    await su.execute(
        "UPDATE work.work SET status = 'cancelled', closed_at = now() WHERE id = $1", w["id"]
    )
    r = await client.post(f"/api/v1/work/{w['id']}/council/run", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    assert r.json()["ref"].startswith("F-") and r.json()["ref"] != ref
    assert (
        await su.fetchval("SELECT order_ref FROM work.councils WHERE work_id = $1", w["id"])
        == r.json()["ref"]
    )


async def test_the_owner_switches_the_pace_at_any_time(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    from hq_api.domain import orders as O
    from hq_api.domain import sessions as SE

    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, work_ref = out["ref"], out["routes"][0]["work_ref"]
    assert out["pace"] == "auto"
    assert "to the END on your own" in await su.fetchval(
        "SELECT brief FROM work.work WHERE ref = $1", work_ref
    )
    await refuse_queued(su, work_ref)
    r = await client.post(f"/api/v1/orders/{ref}/pace", headers=owner, json={"pace": "step"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["pace"] == "step" and rep["steps"][-1]["who_fa"] == "مدیر کل"
    assert rep["steps"][-1]["what_fa"] == SE.PACE_FA["step"]
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", work_ref)
    assert O.pace_brief(ref, "step") in brief and "to the END on your own" not in brief
    assert (
        await su.fetchval(
            """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE w.ref = $1 AND r.reason = $2""",
            work_ref,
            f"pace:step:{ref}",
        )
        == 1
    )
    turns = await su.fetch(
        """SELECT t.by_kind, t.text FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE c.ref = $1 ORDER BY t.n""",
        out["talk_ref"],
    )
    assert turns[-1]["by_kind"] == "owner" and turns[-1]["text"] == SE.PACE_FA["step"]
    assert (await client.get("/api/v1/orders?limit=5", headers=owner)).status_code == 200
    # the same pace again changes nothing; a bad value is refused; a closed session takes none
    steps_before = len(rep["steps"])
    r = await client.post(f"/api/v1/orders/{ref}/pace", headers=owner, json={"pace": "step"})
    assert r.status_code == 200 and len(r.json()["steps"]) == steps_before
    assert (
        await client.post(f"/api/v1/orders/{ref}/pace", headers=owner, json={"pace": "fast"})
    ).status_code == 422
    r = await client.post(f"/api/v1/orders/{ref}/pace", headers=owner, json={"pace": "auto"})
    assert r.status_code == 200 and r.json()["pace"] == "auto"
    assert r.json()["steps"][-1]["what_fa"] == SE.PACE_FA["auto"]
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "cancel"}
    )
    assert r.status_code == 200
    r = await client.post(f"/api/v1/orders/{ref}/pace", headers=owner, json={"pace": "step"})
    assert r.status_code == 409 and r.json()["message_fa"]


async def test_the_player_persona_is_data_and_the_hire_card_names_its_company() -> None:
    from hq_api.talk import personas as P
    from hq_api.talk.context import BOUND_HELP, CARD_HELP, persona_section

    assert P.parse("player:gpt") == ("player", "gpt", None)
    assert P.parse("ceo@TY") == ("manager", "ceo", "TY")
    with pytest.raises(Exception, match="not_found"):
        P.parse("player:claude")
    p = P.Persona(
        key="ceo@TY", kind="manager", role="ceo", title_fa="مدیرعامل", company="TY",
        company_id=uuid.uuid4(), is_manager=True, employee=None, voice=P.default_voice("ceo@TY", "manager"),
        effort="medium", tools=(), cards=("order", "hire"), consult_only=False, face=None,
    )  # fmt: skip
    bound = persona_section(p, "work", ("order", "hire", "delegate"), False, "F-0001")
    assert (
        BOUND_HELP["order"] in bound
        and BOUND_HELP["hire"] in bound
        and CARD_HELP["delegate"] in bound
    )
    free = persona_section(p, "work", ("order", "hire"), False, None)
    assert CARD_HELP["order"] in free and "ON THIS ORDER" not in free
    guest = persona_section(p, "work", ("ask",), False, "F-0001", holder=False, sum_up=True)
    assert "another persona holds it" in guest and "Sum up" in guest


async def test_an_order_of_two_companies_has_one_plan_its_leads(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-13⟩ F-0018 went to Pro-Chart and IG; both sent a plan (14 + 15 tasks, «کار ۱۳ از
    ۲۹») and did each step twice. The first root's holder holds the plan; another root's holder
    gets 409 with a plain line and does its part when asked."""
    co = (await new_company())["code"]
    other = await new_company()
    out = await post_order(client, owner, f"برای {co} برنامه‌ی ریلز را آماده کن {words()}")
    ref = out["ref"]
    [route] = out["routes"]
    lead = route["to"]
    second = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code,
               assignee_id, status)
           SELECT $1, 'one_off', 'همکاری', 'service', 'orders', e.id, 'in_progress'
           FROM core.employees e WHERE e.code = $2 RETURNING ref""",
        other["id"], f"{other['code']}-CEO",
    )  # fmt: skip
    await su.execute(
        """UPDATE owner.orders SET routes = routes || jsonb_build_array(jsonb_build_object(
               'to', $2::text, 'kind', 'work', 'company', $3::text, 'work_ref', $4::text))
           WHERE ref = $1""",
        ref, f"{other['code']}-CEO", other["code"], second,
    )  # fmt: skip
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack",
        headers=await agent_headers(f"{other['code']}-CEO"),
        json={"plan_fa": "برنامه‌ی من", "steps": ["نوت", "بانک موضوع"]},
    )
    assert r.status_code == 409 and "برنامه‌ی جدا" in r.json()["message_fa"], r.text
    r = await client.post(
        f"/internal/v1/orders/{ref}/ack",
        headers=await agent_headers(lead),
        json={"plan_fa": "برنامه", "steps": ["نوت", "بانک موضوع"]},
    )
    assert r.status_code == 200 and len(r.json()["tasks"]) == 2, r.text
