"""Prompt 25 (contract §34): the owner's order answered live. The owner, 2026-11-06: «به محض فرمان
باید اون مسئول … با من حرف بزنه و مرحله به مرحله با من پیش بره یا یه فرمان کلی بدم خودش بره همه
کارهارو بکنه». Order W-000153 («مرحله به مرحله با فرمان من») sat «در انتظار فرمان مرحله اول»
with nowhere for the owner to answer: no tool let its holder ask, no route let the owner reply.

- The pace is read from the owner's words: a step order, or a general one carried to the end.
- A step order opens its live talk with its holder at once (the holder's persona, work mode).
- The holder asks (`order.ask`): the owner's turn, `waiting`, a notification at once, the talk.
- No «no progress» nudge while the owner's turn is open.
- The owner answers (page or talk card): a step, the turn cleared, the holder's work runs again
  with the dialogue in its brief.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import orders as O
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, say, talk  # noqa: F401 - the fixture

STEP_TEXT = "برای {co} کارگروه محتوای اینستاگرام راه بینداز، مرحله به مرحله با فرمان من {w}"


def test_the_pace_is_read_from_the_owners_words() -> None:
    assert O.pace_of("برای پروچارت کارگروه محتوا بساز، مرحله‌به‌مرحله با فرمان من") == "step"
    assert O.pace_of("قدم به قدم جلو برو") == "step"
    assert O.pace_of("برای تریدیار سه پست آموزشی بساز") == "auto"
    assert "order.ask" in O.pace_brief("F-0001", "step")
    assert "END" in O.pace_brief("F-0001", "auto") and "F-0001" in O.pace_brief("F-0001", "auto")


def test_an_open_turn_keeps_the_first_and_the_newest_ask() -> None:
    """Audit: the 11th ask in one open turn was dropped (asks[:10]), so its asker was never woken."""

    def a(code: str, q: str) -> dict[str, Any]:
        return {"question_fa": q, "by": {"kind": "agent", "code": code}}

    asks = [a(f"X-{i}", f"q{i}") for i in range(11)]
    kept = OT.keep_asks(asks)
    assert len(kept) == OT.MAX_ASKS
    assert kept[0]["by"]["code"] == "X-0" and kept[-1]["by"]["code"] == "X-10"
    assert "X-10" in OT._asker_codes({**kept[0], "asks": kept})
    # an asker's repeated ask goes first, so every distinct asker still stays
    asks = [a("X-0", "q0"), a("X-1", "q1"), a("X-1", "q1b")]
    asks += [a(f"X-{i}", f"q{i}") for i in range(2, 10)]
    kept = OT.keep_asks(asks)
    assert len(kept) == OT.MAX_ASKS
    assert {k["by"]["code"] for k in kept} == {f"X-{i}" for i in range(10)}
    assert [k["question_fa"] for k in kept if k["by"]["code"] == "X-1"] == ["q1b"]


async def test_the_owners_chosen_pace_wins_over_the_words(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """⟨2026-11-09⟩ the owner (F-0013: «از اول تا آخر» read as `auto`, the holder went to the end
    before his «با من» landed): the app asks «با من یا خودکار؟» when the session is made and the
    answer is the pace, whatever the words say; without it the words still decide."""
    co = (await new_company())["code"]
    text = f"برای {co} کارگروه تولید محتوا را با همکاری خودم از اول تا آخر راه بینداز {words()}"
    assert O.pace_of(text) == "auto"
    out = await post_order(client, owner, text, pace="step")
    assert out["pace"] == "step", out
    brief = await su.fetchval(
        "SELECT brief FROM work.work WHERE ref = $1", out["routes"][0]["work_ref"]
    )
    assert "STEP BY STEP" in brief and "to the END" not in brief
    assert await su.fetchval("SELECT pace FROM owner.orders WHERE ref = $1", out["ref"]) == "step"
    out = await post_order(client, owner, STEP_TEXT.format(co=co, w=words()), pace="auto")
    assert out["pace"] == "auto", out
    brief = await su.fetchval(
        "SELECT brief FROM work.work WHERE ref = $1", out["routes"][0]["work_ref"]
    )
    assert "to the END on your own" in brief
    r = await client.post(
        "/api/v1/orders", headers={**owner, **idem()}, json={"text": text, "pace": "fast"}
    )
    assert r.status_code == 422


async def _turns(su: Any, conv: str) -> list[Any]:
    return list(
        await su.fetch(
            """SELECT t.by_kind, t.show_md, t.text FROM talk.turns t
               JOIN talk.conversations c ON c.id = t.conversation_id
               WHERE c.ref = $1 ORDER BY t.n""",
            conv,
        )
    )


async def test_a_step_order_talks_asks_and_goes_on_with_the_owners_word(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, STEP_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    assert out["pace"] == "step" and out["talk_ref"], out
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", work_ref)
    assert "STEP BY STEP" in brief and ref in brief
    # the live talk with the holder, open at once and the same on every call
    conv = await su.fetchrow(
        "SELECT persona, mode, order_ref FROM talk.conversations WHERE ref = $1", out["talk_ref"]
    )
    role = await su.fetchval("SELECT role FROM core.employees WHERE code = $1", holder)
    assert (conv["persona"], conv["mode"], conv["order_ref"]) == (f"{role}@{co}", "work", ref)
    assert len(await _turns(su, out["talk_ref"])) == 1  # the holder's hello
    r = await client.post(f"/api/v1/orders/{ref}/talk", headers=owner)
    assert r.status_code == 200 and r.json() == {"conversation_ref": out["talk_ref"]}
    # someone not on the order may not ask; the holder asks
    stranger = await agent_headers(f"{co}-HR-MGR")
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask", headers=stranger, json={"question_fa": "ادامه بدهم؟"}
    )
    assert r.status_code == 403
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask",
        headers=await agent_headers(holder),
        json={"question_fa": "اول صفحه‌ی آموزش را بسازم یا صفحه‌ی سیگنال؟"},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["state"] == "waiting" and rep["pace"] == "step"
    assert rep["turn"]["question_fa"].startswith("اول صفحه‌ی آموزش")
    assert rep["turn"]["by"]["code"] == holder and rep["conversation_ref"] == out["talk_ref"]
    assert rep["steps"][-1]["what_fa"].startswith("سؤال از تو")
    n = await su.fetchrow(
        """SELECT owner_visible, level, link_kind, link_ref FROM notify.notifications
           WHERE source_code = 'orders' AND link_ref = $1 ORDER BY created_at DESC LIMIT 1""",
        out["talk_ref"],
    )
    assert n is not None and n["owner_visible"] and n["level"] == "decision"
    turns = await _turns(su, out["talk_ref"])
    assert len(turns) == 2 and "صفحه‌ی سیگنال" in turns[-1]["show_md"]
    # an old order whose holder waits on the owner is not nudged for «no progress»
    await su.execute(
        "UPDATE owner.orders SET created_at = now() - interval '9 hours' WHERE ref = $1", ref
    )
    await su.execute(
        """UPDATE owner.order_reports SET last_step_at = now() - interval '9 hours',
               acked_at = now() - interval '9 hours' WHERE ref = $1""",
        ref,
    )
    s = SimpleNamespace(
        order_ack_minutes=100_000, order_progress_hours=2, order_owner_hours=6, order_talk_limit=999
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await OR.timers(tx, s, ref) == []
    # the holder's run that asked has ended; the owner answers on the order's page: a step, the
    # turn cleared, and the holder's work runs again at once
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM work.work w WHERE w.id = r.work_id AND w.ref = $1 AND r.state = 'queued'""",
        work_ref,
    )
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers=owner, json={"text": "از صفحه‌ی آموزش شروع کن"}
    )
    assert r.status_code == 422  # Idempotency-Key
    r = await client.post(
        f"/api/v1/orders/{ref}/reply",
        headers={**owner, **idem()},
        json={"text": "از صفحه‌ی آموزش شروع کن"},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["turn"] is None and rep["state"] != "waiting"
    assert (rep["steps"][-1]["who_fa"], rep["steps"][-1]["what_fa"]) == (
        "مدیر کل",
        "از صفحه‌ی آموزش شروع کن",
    )
    assert await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE w.ref = $1 AND r.reason = $2""",
        work_ref,
        f"owner_reply:{ref}",
    )
    turns = await _turns(su, out["talk_ref"])
    assert turns[-1]["by_kind"] == "owner" and "صفحه‌ی آموزش" in turns[-1]["text"]
    # the holder's next run reads the dialogue
    async with hub.db.tx(await hub.companies.ids()) as tx:
        wid = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=work_ref)
        d = await OT.dialogue(tx, wid)
    assert d is not None and d["order"] == ref and d["pace"] == "step"
    assert d["owner_turn"] is None and d["steps"][-1] == "مدیر کل: از صفحه‌ی آموزش شروع کن"


async def test_an_order_card_in_the_orders_talk_goes_onto_that_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, f"برای {co} گزارش فروش هفته را آماده کن {words()}")
    ref = out["ref"]
    # ⟨1.17⟩ §35.1 every order is a session: its talk is open at once, whatever the pace
    assert out["pace"] == "auto" and out["talk_ref"]
    [route] = out["routes"]
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", route["work_ref"])
    assert "to the END on your own" in brief
    r = await client.post(f"/api/v1/orders/{ref}/talk", headers=owner)
    assert r.status_code == 200, r.text
    conv = r.json()["conversation_ref"]
    assert conv == out["talk_ref"]
    orders_before = await su.fetchval("SELECT count(*) FROM owner.orders")
    card = {"kind": "order", "title_fa": "ادامه", "body_fa": "",
            "payload": {"text": "فروش دو هفته را با هم مقایسه کن"}}  # fmt: skip
    talk["router"].answers = [answer("الان روی همین فرمان انجامش میدهم.", cards=[card])]
    said = await say(client, owner, conv, "فروش دو هفته را هم مقایسه کن")
    assert (
        "## The order you hold" in talk["router"].text_sent() and ref in talk["router"].text_sent()
    )
    (c,) = said["answer"]["cards"]
    r = await client.post(f"/api/v1/talk/cards/{c['id']}/run", json={}, headers={**owner, **idem()})
    assert r.status_code == 200, r.text
    assert r.json()["made"] == [ref]
    assert await su.fetchval("SELECT count(*) FROM owner.orders") == orders_before  # no new order
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    assert rep["steps"][-1] == {**rep["steps"][-1], "who_fa": "مدیر کل",
                                "what_fa": "فروش دو هفته را با هم مقایسه کن"}  # fmt: skip
    assert rep["conversation_ref"] == conv


async def test_an_ended_order_takes_no_reply(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, f"برای {co} گزارش هزینه را آماده کن {words()}")
    await su.execute(
        """UPDATE owner.order_reports SET ended_at = now(), closed_at = now(), state = 'cancelled'
           WHERE ref = $1""",
        out["ref"],
    )
    r = await client.post(
        f"/api/v1/orders/{out['ref']}/reply", headers={**owner, **idem()}, json={"text": "ادامه"}
    )
    assert r.status_code == 409
    r = await client.post(
        "/api/v1/orders/F-99999999/reply", headers={**owner, **idem()}, json={"text": "ادامه"}
    )
    assert r.status_code == 404


async def test_a_long_reply_is_taken_whole(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    """⟨2026-11-09⟩ the owner's replies in F-0013 and F-0014 were over 2000 letters and got 422
    («String should have at most 2000 characters»): a reply is as long as a talk turn, and its
    step keeps all of it."""
    co = (await new_company())["code"]
    out = await post_order(client, owner, f"برای {co} گزارش فروش هفته را آماده کن {words()}")
    long = "این کارگروه را یک اسکیل کن که در شرکت‌های دیگر هم به کار بیاید. " * 60 + "پایان"
    assert 3000 < len(long) <= OT.OWNER_WORD_MAX
    r = await client.post(
        f"/api/v1/orders/{out['ref']}/reply", headers={**owner, **idem()}, json={"text": long}
    )
    assert r.status_code == 200, r.text
    step = r.json()["steps"][-1]
    assert step["who_fa"] == "مدیر کل" and step["what_fa"].endswith("پایان")
    r = await client.post(
        f"/api/v1/orders/{out['ref']}/reply",
        headers={**owner, **idem()},
        json={"text": "ب" * (OT.OWNER_WORD_MAX + 1)},
    )
    assert r.status_code == 422 and "text" in r.json()["fields"]


@pytest.mark.parametrize("text", ["", "   "])
async def test_an_empty_reply_is_refused(
    client: httpx.AsyncClient, owner: dict[str, str], text: str
) -> None:
    r = await client.post(
        "/api/v1/orders/F-0001/reply", headers={**owner, **idem()}, json={"text": text}
    )
    assert r.status_code in (404, 422)
