"""W24 (2026-11-13): the session's team, one person at a time (contract §57).

The owner: «میخوام … مستقیم بزنم روی کارمند باهاش توی یه فضای کوچیک حرف بزنم و ببندم و اون ادامه بده
کارشو ولی نمیخوام خیلی تو ابعاد گسترده باز باشه که انقدر بین اینا حرف بزنم گیج بشم». And of the line
that came every few minutes: «دقیقا خروجیه چی تحویل شد؟».

A. the team: the holder first, the media seats only for a content session (filled or empty), the
   people present; the narrator of the order's company;
B. an empty seat hired at once by his own word (a hard check refuses with its code, nothing made);
C. a word to one person: a side work (and its plan task) or the person's open work, one main
   step per burst; the person's `order.progress` / `order.ask` from it are side lines (no main
   step, no owner's turn); reading the newest page marks the seat read;
D. a direct turn's output is named by its files, and a file re-issued under a version mark is a
   revision of the earlier output (`revision_of`), which the session's outputs carry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import order_report as OR
from hq_api.domain import order_turns as OT
from hq_api.domain import players as PL
from hq_api.domain import session_team as ST
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p21_routing_orders import envelope, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT


# ------------------------------------------------------------------ helpers --
async def team(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/orders/{ref}/team", headers=owner)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def say(
    client: httpx.AsyncClient, owner: dict[str, str], ref: str, code: str, text: str
) -> httpx.Response:
    return await client.post(
        f"/api/v1/orders/{ref}/team/{code}/say", headers={**owner, **idem()}, json={"text": text}
    )


async def side_lines(su: Any, ref: str, code: str) -> list[Any]:
    return list(
        await su.fetch(
            """SELECT l.* FROM owner.session_side_lines l JOIN owner.orders o ON o.id = l.order_id
               WHERE o.ref = $1 AND l.seat_code = $2 ORDER BY l.id""",
            ref,
            code,
        )
    )


def steps_with(rep: dict[str, Any], text: str) -> list[dict[str, Any]]:
    return [s for s in rep["steps"] if text in s["what_fa"]]


def side_steps(rep: dict[str, Any], who: str = "سناریست") -> list[dict[str, Any]]:
    """The main thread's steps of the owner's side talk with `who` («مدیر کل: با …: …»)."""
    return [
        s for s in rep["steps"]
        if s["who_fa"] == ST.OWNER_FA and s["what_fa"].startswith(f"با {who}")
    ]  # fmt: skip


# ===================================================================== A. the team ==
async def test_the_team_is_the_holder_the_media_seats_of_a_content_session_and_who_is_here(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    # a session that is not about content: the holder alone
    plain = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=plain, w=words()))
    t = await team(client, owner, out["ref"])
    assert [s["role_fa"] for s in t["seats"]] == [ST.HOLDER_FA] and t["narrator"] is None
    holder = t["seats"][0]
    assert holder["holder"] is True and holder["key"] == out["routes"][0]["to"]
    assert holder["employee"]["company"] == plain and holder["last"] is None
    assert holder["unread"] == 0 and holder["state"] in ("working", "idle")

    # the company has a narrator: a content session, its three media seats empty, then who came
    co = (await new_company())["code"]
    r = await client.put(f"/api/v1/companies/{co}/narrator", headers=owner, json={"voice": "kore"})
    assert r.status_code == 200, r.text
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    r = await client.post(
        f"/api/v1/orders/{ref}/participants",
        headers=owner,
        json={"kind": "person", "key": "advisor"},
    )
    assert r.status_code == 200, r.text
    t = await team(client, owner, ref)
    seats = t["seats"]
    assert [s["role_fa"] for s in seats[:4]] == [ST.HOLDER_FA, "نویسنده", "کارگردان", "موشن‌گرافی"]
    for s, role in zip(seats[1:4], ST.SEAT_ROLES, strict=True):
        assert s == {**s, "key": f"role:{role}", "role": role, "state": "empty", "employee": None}
    advisor = seats[4]
    assert advisor["role"] == "advisor" and advisor["state"] in ("idle", "working")
    assert advisor["role_fa"] == advisor["employee"]["title_fa"] and not advisor["holder"]
    assert t["narrator"]["voice"] == "Kore" and t["narrator"]["voice_fa"] == "Kore (محکم)"
    assert t["narrator"]["company"] == co
    # a player is never a seat; an unknown order is 404
    assert (await client.get("/api/v1/orders/F-99999999/team", headers=owner)).status_code == 404


# ===================================================================== B. the hire ==
async def test_an_empty_seat_is_hired_at_once_and_a_refusal_makes_nothing(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    await client.put(f"/api/v1/companies/{co}/narrator", headers=owner, json={"voice": "Puck"})
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    url = f"/api/v1/orders/{ref}/team/hire"
    # no Idempotency-Key: refused before anything
    r = await client.post(url, headers=owner, json={"role": "scriptwriter"})
    assert r.status_code in (400, 422, 428), r.text
    # a role that is not a media seat
    r = await client.post(url, headers={**owner, **idem()}, json={"role": "cto"})
    assert r.status_code == 422, r.text

    # a month envelope too small for one: its own code and plain words, nothing made
    await envelope(su, company, tokens=1)
    cards = await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE company_id = $1 AND kind = 'hire'",
        company["id"],
    )
    r = await client.post(url, headers={**owner, **idem()}, json={"role": "video_director"})
    assert r.status_code == 409 and r.json()["code"] == "envelope_exceeded", r.text
    assert r.json()["message_fa"]
    assert await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE company_id = $1 AND kind = 'hire'",
        company["id"],
    ) == cards  # fmt: skip
    assert not await su.fetchval(
        "SELECT 1 FROM core.employees WHERE company_id = $1 AND role = 'video_director'",
        company["id"],
    )

    # room in the envelope: hired by code, no card for anyone, and in the session at once
    await envelope(su, company, tokens=500_000_000)
    key = idem()
    r = await client.post(url, headers={**owner, **key}, json={"role": "scriptwriter"})
    assert r.status_code == 200, r.text
    seat = next(s for s in r.json()["seats"] if s["role"] == "scriptwriter")
    assert seat["state"] in ("idle", "working") and seat["employee"]["company"] == co
    code = seat["key"]
    emp = await su.fetchrow(
        """SELECT e.status, d.status AS card, d.decided_by_kind
           FROM core.employees e JOIN cartable.decisions d ON d.id = e.hired_by_decision_id
           WHERE e.code = $1""",
        code,
    )
    assert (emp["status"], emp["card"], emp["decided_by_kind"]) == ("active", "approved", "service")
    rep = await report(client, owner, ref)
    assert rep["cards"] == []
    assert steps_with(rep, "استخدام شد و به همین جلسه آمد")
    assert any(p["key"] == f"scriptwriter@{co}" for p in rep["participants"])
    # the same key again: the same answer, nobody hired twice
    r2 = await client.post(url, headers={**owner, **key}, json={"role": "scriptwriter"})
    assert r2.status_code == 200 and r2.json() == r.json()
    assert await su.fetchval(
        "SELECT count(*) FROM core.employees WHERE company_id = $1 AND role = 'scriptwriter'",
        company["id"],
    ) == 1  # fmt: skip
    # the seat is filled now
    r = await client.post(url, headers={**owner, **idem()}, json={"role": "scriptwriter"})
    assert r.status_code == 409 and r.json()["message_fa"] == ST.SEAT_FULL_FA
    # another session of the company: its scriptwriter comes in, nobody new is hired
    again = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    r = await client.post(
        f"/api/v1/orders/{again['ref']}/team/hire",
        headers={**owner, **idem()},
        json={"role": "scriptwriter"},
    )
    assert r.status_code == 200, r.text
    assert next(s for s in r.json()["seats"] if s["role"] == "scriptwriter")["key"] == code
    assert await su.fetchval(
        "SELECT count(*) FROM core.employees WHERE company_id = $1 AND role = 'scriptwriter'",
        company["id"],
    ) == 1  # fmt: skip


# ================================================================ C. a side talk ==
async def test_a_word_to_one_person_is_a_side_talk_and_their_answers_stay_in_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    other = (await new_company())["code"]
    await envelope(su, company, tokens=500_000_000)
    await client.put(f"/api/v1/companies/{co}/narrator", headers=owner, json={"voice": "Kore"})
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, holder = out["ref"], out["routes"][0]["to"]
    root = await su.fetchrow(
        "SELECT id, status FROM work.work WHERE ref = $1", out["routes"][0]["work_ref"]
    )
    r = await client.post(
        f"/api/v1/orders/{ref}/team/hire",
        headers={**owner, **idem()},
        json={"role": "scriptwriter"},
    )
    assert r.status_code == 200, r.text
    sw = next(s for s in r.json()["seats"] if s["role"] == "scriptwriter")
    code = sw["key"]

    # the holder's word is the main composer's; a code not in the team is not found
    r = await say(client, owner, ref, holder, "سلام")
    assert r.status_code == 409 and r.json()["message_fa"] == ST.HOLDER_SAY_FA
    r = await say(client, owner, ref, f"ceo@{other}", "سلام")
    assert r.status_code == 404
    r = await say(client, owner, ref, f"{other}-CEO", "سلام")
    assert r.status_code == 404 and r.json()["message_fa"] == ST.NOT_SEAT_FA
    r = await client.post(
        f"/api/v1/orders/{ref}/team/{code}/say", headers=owner, json={"text": "x"}
    )
    assert r.status_code in (400, 422, 428), r.text  # no Idempotency-Key

    # the first word: a side work under the root for the scriptwriter, a plan task, one main step
    first = "متن ریلز امروز را کوتاه‌تر کن و قلاب اولش را تندتر بنویس"
    r = await say(client, owner, ref, code, first)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["line"]["who"] == "owner" and got["line"]["text"] == first
    assert got["line"]["who_fa"] == ST.OWNER_FA and got["line"]["work_ref"] == got["work_ref"]
    side = await su.fetchrow(
        """SELECT w.id, w.title, w.brief, w.parent_id, w.status, e.code AS assignee
           FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1""",
        got["work_ref"],
    )
    assert side["assignee"] == code and side["parent_id"] == root["id"] and side["title"] == first
    assert f"در جلسه‌ی {ref}" in side["brief"] and "order.ask" in side["brief"]
    assert got["woken"] is True  # its first run is queued
    # the holder's own work goes on as it was (a side talk never makes it wait)
    assert (
        await su.fetchval("SELECT status FROM work.work WHERE id = $1", root["id"])
        == root["status"]
    )
    task = await su.fetchrow(
        """SELECT t.by, t.who_code, t.title_fa FROM owner.session_tasks t
           JOIN owner.orders o ON o.id = t.order_id WHERE o.ref = $1 AND t.work_ref = $2""",
        ref,
        got["work_ref"],
    )
    assert (task["by"], task["who_code"]) == ("owner", code)
    rep = await report(client, owner, ref)
    main = side_steps(rep)
    assert len(main) == 1, rep["steps"]
    assert "قلاب اولش را تندتر" in main[0]["what_fa"]

    # a second word within ten minutes joins the same side work: no second main step
    r = await say(client, owner, ref, code, "و یک جمله‌ی پایانی هم اضافه کن")
    assert r.status_code == 200 and r.json()["work_ref"] == got["work_ref"]
    lines = await side_lines(su, ref, code)
    assert [x["made_work"] for x in lines] == [True, False]
    assert await su.fetchval(
        "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'side_word'", side["id"]
    ) == 1  # fmt: skip
    rep = await report(client, owner, ref)
    assert len(side_steps(rep)) == 1
    # the run of the side work reads the side talk
    async with hub.db.tx(await hub.companies.ids()) as tx:
        brief = await OT.dialogue(tx, side["id"])
        root_brief = await OT.dialogue(tx, root["id"])
    assert brief is not None and brief["side_talk"]["with"] == ST.OWNER_FA
    assert brief["side_talk"]["lines"][0] == f"{ST.OWNER_FA}: {first}"
    assert f"session {ref}" in brief["side_talk"]["rule"]
    assert root_brief is not None and "side_talk" not in root_brief

    # the person answers from the side work: side lines, no main step, no owner's turn
    h = await agent_headers(code)
    r = await client.post(f"/internal/v1/orders/{ref}/progress", headers=h,
                          json={"step_fa": "قلاب را تندتر کردم؛ نسخه‌ی تازه آماده است"})  # fmt: skip
    assert r.status_code == 200, r.text
    r = await client.post(f"/internal/v1/orders/{ref}/ask", headers=h,
                          json={"question_fa": "جمله‌ی پایانی با شعار باشد یا بدون؟"})  # fmt: skip
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["turn"] is None
    assert not steps_with(rep, "قلاب را تندتر کردم") and not steps_with(rep, "جمله‌ی پایانی با")
    answered = [s for s in rep["steps"] if s["what_fa"] == ST.SEAT_STEP_FA]
    assert len(answered) == 1 and "سناریست" in answered[0]["who_fa"]
    assert not await su.fetchval(
        """SELECT count(*) FROM notify.notifications WHERE link_ref = ANY($1::text[])
             AND title_fa LIKE 'نوبت توست%'""",
        [ref, out.get("talk_ref") or ref],
    )
    lines = await side_lines(su, ref, code)
    assert [x["who"] for x in lines] == ["owner", "owner", "seat", "seat"]
    assert lines[2]["work_id"] == side["id"]
    # the holder's own step is still the main thread's
    r = await client.post(f"/internal/v1/orders/{ref}/progress",
                          headers=await agent_headers(holder), json={"step_fa": "گام اصلی جلسه"})  # fmt: skip
    assert r.status_code == 200 and steps_with(r.json(), "گام اصلی جلسه")
    # the stream says which side moved
    events = await su.fetch(
        """SELECT payload FROM core.outbox WHERE subject LIKE '%.session.team'
             AND payload->>'ref' = $1""",
        ref,
    )
    assert len(events) == 4

    # unread: the person's two lines; reading the newest page marks the seat read
    t = await team(client, owner, ref)
    seat = next(s for s in t["seats"] if s["key"] == code)
    assert seat["unread"] == 2 and seat["last"]["who"] == "seat"
    assert seat["last"]["text"].startswith("جمله‌ی پایانی")
    page = await client.get(f"/api/v1/orders/{ref}/team/{code}/lines", headers=owner,
                            params={"limit": 3})  # fmt: skip
    assert page.status_code == 200, page.text
    body = page.json()
    assert [x["who"] for x in body["items"]] == ["owner", "seat", "seat"]  # newest last
    assert body["next_cursor"]
    older = await client.get(f"/api/v1/orders/{ref}/team/{code}/lines", headers=owner,
                             params={"before": body["next_cursor"]})  # fmt: skip
    assert [x["text"] for x in older.json()["items"]] == [first]
    assert older.json()["next_cursor"] is None
    seat = next(s for s in (await team(client, owner, ref))["seats"] if s["key"] == code)
    assert seat["unread"] == 0
    r = await client.get(f"/api/v1/orders/{ref}/team/{other}-CEO/lines", headers=owner)
    assert r.status_code == 404

    # a word after the burst is one more main step
    await su.execute(
        """UPDATE owner.session_side_lines SET created_at = created_at - interval '11 minutes'
           WHERE order_id = (SELECT id FROM owner.orders WHERE ref = $1)""",
        ref,
    )
    r = await say(client, owner, ref, code, "ممنون؛ همین خوب است")
    assert r.status_code == 200, r.text
    rep = await report(client, owner, ref)
    assert len(side_steps(rep)) == 2

    # a person of another company present in the session: a work requested by the root
    r = await client.post(f"/api/v1/orders/{ref}/participants", headers=owner,
                          json={"kind": "person", "key": f"ceo@{other}"})  # fmt: skip
    assert r.status_code == 200, r.text
    r = await say(client, owner, ref, f"{other}-CEO", "نظرت درباره‌ی این ریلز چیست؟")
    assert r.status_code == 200, r.text
    asked = await su.fetchrow(
        "SELECT parent_id, requested_by_work_id FROM work.work WHERE ref = $1", r.json()["work_ref"]
    )
    assert asked["parent_id"] is None and asked["requested_by_work_id"] == root["id"]

    # a closed session takes no word
    r = await client.post(f"/api/v1/orders/{ref}/close", headers={**owner, **idem()},
                          json={"verdict": "cancel"})  # fmt: skip
    assert r.status_code == 200, r.text
    r = await say(client, owner, ref, code, "یک چیز دیگر")
    assert r.status_code == 409


def test_a_side_word_is_the_owners_own_word_for_a_held_run() -> None:
    waiting = {"askers": set(), "since": None}
    assert OR.answers_owner({"reason": f"{ST.SIDE_REASON}F-0001", "queued_at": None}, waiting)
    assert OR.answers_owner({"reason": f"retry:{ST.SIDE_REASON}F-0001", "queued_at": None}, waiting)
    assert not OR.answers_owner({"reason": "work:W-000001", "queued_at": None}, waiting)
    assert "side_word:%" in OR.WAKE_REASONS


# ============================================================ D. named outputs ==
def test_a_direct_turns_output_is_named_by_its_files_and_a_revision_says_so() -> None:
    def f(name: str, mime: str = "application/pdf") -> dict[str, Any]:
        return {"name": name, "mime": mime}

    assert WS.output_name([f("نکته‌های ریلز.pdf")], []) == ("نکته‌های ریلز", None)
    # the main file names it (a video before its cover and caption), the rest are counted
    title, rev = WS.output_name(
        [
            f("caption.txt", "text/plain"),
            f("cover.jpg", "image/jpeg"),
            f("reel-atr.mp4", "video/mp4"),
        ],
        [],
    )
    assert (title, rev) == ("reel-atr و ۲ فایل دیگر", None)
    # differs only by a version mark from a file of an earlier output: a revision of the newest
    earlier = [
        {"ref": "DL-000009", "name": "notes-v5.pdf"},
        {"ref": "DL-000004", "name": "notes.pdf"},
    ]
    for name in ("notes-v6.pdf", "notes_v7.pdf", "notes (3).pdf", "notes.pdf", "Notes نسخه ۲.pdf"):
        assert WS.output_name([f(name)], earlier) == ("نسخه‌ی تازه‌ی " + WS.version_base(name),
                                                      "DL-000009"), name  # fmt: skip
    assert WS.version_base("گزارش-نسخه‌ی-۲.pdf") == "گزارش"
    assert WS.version_base("nav3.png") == "nav3"  # a name's own digits are no version mark
    assert WS.output_name([f("notes-summary.pdf")], earlier) == ("notes-summary", None)
    # nothing in the title is the old «خروجی جلسه: …»
    assert not WS.output_name([f("a.pdf")], [])[0].startswith("خروجی جلسه")


async def test_the_sessions_outputs_carry_the_revision_they_replace(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, root_ref = out["ref"], out["routes"][0]["work_ref"]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load_ref(tx, root_ref)
        first = await PL.deliver(tx, w, title="یادداشت‌های ریلز", body="یادداشت",
                                 produced_with={"direct": True}, close=False)  # fmt: skip
        again = await PL.deliver(tx, w, title="نسخه‌ی تازه‌ی یادداشت‌های ریلز", body="یادداشت بهتر",
                                 produced_with={"direct": True, "revision_of": first["ref"]},
                                 close=False)  # fmt: skip
    rep = await report(client, owner, ref)
    outs = {o["ref"]: o for o in rep["outputs"]}
    assert outs[again["ref"]]["revision_of"] == first["ref"]
    assert outs[first["ref"]]["revision_of"] is None
