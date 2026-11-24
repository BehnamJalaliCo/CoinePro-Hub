"""⟨1.39⟩ Prompt 39 §11 (P1, the publications half; contract §60): every publication is one
permanent row of media.publications, made where every publication passes and following IG-Hub's
answers; the backfill (also after a fresh start); the 24-hour sweep keeps a row's files; the desk
tidied; the Persian search; «منتظر شما»; owner only and RLS."""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from PIL import Image

from hq_api import fresh_start as FS
from hq_api.db import Tx
from hq_api.domain import flows as FL
from hq_api.domain import players as PL
from hq_api.domain import publications as PB
from hq_api.domain import publish_keep as PK
from hq_api.domain import session_publish as SPB
from hq_api.domain import work as W
from hq_api.hub import Hub

from .conftest import agent_headers
from .test_p17_runners import take
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT
from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
from .test_w17_session_publish import an_output, tap
from .test_w19_publish_time import answer, asked, connected
from .test_w24_publish_retention import a_file

pytestmark = pytest.mark.usefixtures("hiring_open")


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def _row(su: Any, where: str, *args: Any) -> Any:
    return await su.fetchrow(f"SELECT * FROM media.publications WHERE {where}", *args)


async def _topic(su: Any, co: str, order: str, title: str) -> None:
    await su.execute(
        """INSERT INTO growth.topics (company_id, kind, title_fa, norm, source, by_code, order_ref)
           SELECT id, 'topic', $2, $2, 'claim', 'test', $3 FROM core.companies WHERE code = $1""",
        co,
        title,
        order,
    )


# ------------------------------------------------------------------- units --
def test_the_three_spellings_fold_to_one_key_and_the_snippet_is_short() -> None:
    keys = {PB.fold(x) for x in ("بلاکچین", "بلاک چین", "بلاک‌چین", "بلاكچين")}
    assert keys == {"بلاکچین"}
    assert PB.fold("ریلز ۱۲") == PB.fold("ریلز 12")
    text = "x" * 200 + " درس امروز: بلاک‌چین با یک مثال ساده " + "y" * 200
    got = PB.snippet(text, "بلاک چین")
    assert got is not None and "بلاک‌چین" in got and len(got) <= 80


def test_the_title_is_the_topic_then_the_session_then_the_caption_never_a_file() -> None:
    assert PB.title_of("زی‌کش", "جلسه", "کپشن", "reel", "a") == "زی‌کش"
    assert PB.title_of(None, "موضوع جلسه", "کپشن", "reel", "a") == "موضوع جلسه"
    long = "خط اول کپشن " * 20
    assert PB.title_of(None, None, f"\n{long}\nخط دوم", "reel", "a") == " ".join(long.split())[:80]
    assert PB.title_of(None, None, None, "story", "zaribsad") == "استوری در @zaribsad"


# --------------------------------------------------------- a reel's chain --
async def test_a_reel_is_one_row_from_its_tap_to_its_link_and_held_then_published(
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
    await _topic(su, co, order, "زی‌کش؛ حریم خصوصی در بلاک‌چین")
    rn = await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=5)
    body = {"output": output, "file_id": reel, "cover_file_id": cover,
            "caption": "زی‌کش ارزی است که …\nخط دوم", "scheduled_at": later.isoformat(),
            "comment": {"keywords": ["زی‌کش", "zcash"], "reply": "لینک ثبت‌نام",
                        "link": "https://pro-chart.com/x"}}  # fmt: skip
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    # made with the job, in its transaction: scheduled for its hour at once
    # (an output's ref may repeat in a test database that outlives its runs: the job names it)
    row = await _row(su, "chain[1] = $1", UUID(r.json()["job"]))
    assert row is not None and row["state"] == "scheduled" and row["kind"] == "reel"
    assert row["title_fa"] == "زی‌کش؛ حریم خصوصی در بلاک‌چین" and row["topic_fa"] == row["title_fa"]
    assert row["caption"].startswith("زی‌کش ارزی") and row["account"] == "pro.chart"
    comment = _j(row["comment"])
    # the words as IG-Hub was sent them (with their written forms, §46)
    assert comment["keywords"][0] == "زی‌کش" and "zcash" in comment["keywords"]
    assert comment["reply"] == "لینک ثبت‌نام"
    assert len(comment["public_replies"]) == 10  # what IG-Hub was sent (§46)
    roles = {f["role"] for f in _j(row["files"])}
    assert roles == {"video", "cover"} and row["thumb_file_id"] is not None
    assert all(f["size"] for f in _j(row["files"]))
    src = _j(row["source"])
    assert src["order"] == order and src["session"] == order and src["output"] == output
    assert src["job_id"] == str(row["chain"][0]) and src["automation"] is None
    ref = row["ref"]
    assert ref.startswith("P-") and len(ref) >= 8
    # publication.updated on the new topic `publish`
    ev = await su.fetchrow(
        """SELECT payload FROM core.outbox WHERE subject = $1 AND payload -> 'data' ->> 'ref' = $2
           ORDER BY created_at DESC LIMIT 1""",
        f"hq.core.{co}.publication.updated",
        ref,
    )
    data = _j(ev["payload"])["data"]
    assert data["ref"] == ref and data["state"] == "scheduled" and data["kind"] == "reel"

    # IG-Hub holds it for its time; then its page is closed (held), then it goes out
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:71", "url": None})
    row = await _row(su, "ref = $1", ref)
    assert row["state"] == "scheduled" and row["external_id"] == "pub:71"
    t0 = later + timedelta(minutes=2)
    assert await asked(hub, su, output, t0) == 1
    check = await take(client, rn)
    row = await _row(su, "ref = $1", ref)
    assert len(row["chain"]) == 2 and str(row["chain"][1]) == check["id"]
    await answer(client, rn, check["id"], {"external_id": "pub:71", "url": None, "held": True})
    row = await _row(su, "ref = $1", ref)
    assert row["state"] == "held" and row["state_note_fa"] == PB.HELD_FA
    assert await asked(hub, su, output, t0 + timedelta(minutes=11)) == 2
    check = await take(client, rn)
    url = "https://www.instagram.com/reel/Z71/"
    await answer(client, rn, check["id"], {"external_id": "Z71", "url": url})
    row = await _row(su, "ref = $1", ref)
    assert row["state"] == "published" and row["url"] == url and row["published_at"] is not None
    assert len(row["chain"]) == 3 and row["external_id"] == "Z71"
    n = await su.fetchval("SELECT count(*) FROM media.publications WHERE company_id = $1", pc["id"])
    assert n == 1

    # the routes (owner only): the item, the list with its search, today, the tree
    item = (await client.get(f"/api/v1/publications/{ref}", headers=owner)).json()
    assert item["state"] == "published" and item["comment"]["link"] == "https://pro-chart.com/x"
    assert item["source"]["session"] == order and item["set"] is None
    found = (await client.get("/api/v1/publications", headers=owner,
                              params={"company": co, "q": "زیکش"})).json()  # fmt: skip
    assert [c["ref"] for c in found["items"]] == [ref] and found["items"][0]["match"] == "title"
    tree = (await client.get("/api/v1/publications/tree", headers=owner,
                             params={"to": (date.today() + timedelta(days=2)).isoformat()})).json()  # fmt: skip
    mine = next(c for c in tree["companies"] if c["code"] == co)
    assert mine["total"] == 1 and mine["accounts"][0]["by_kind"] == {"reel": 1}
    # owner only: an agent and nobody are refused
    for path in ("/api/v1/publications/today", f"/api/v1/publications/{ref}",
                 "/api/v1/publications/waiting", "/api/v1/publications"):  # fmt: skip
        assert (await client.get(path)).status_code == 401
        r = await client.get(path, headers=await agent_headers(f"{co}-CEO"))
        assert r.status_code in (401, 403), (path, r.status_code)
    assert (
        await client.get("/api/v1/publications", headers=owner, params={"company": "ZZZZ9"})
    ).status_code == 404
    assert (
        await client.get("/api/v1/publications", headers=owner, params={"account": "nobody.at.all"})
    ).status_code == 404
    # RLS: another company's scope sees none of it
    other = (await new_company())["id"]
    async with hub.db.tx([other]) as tx:
        assert await tx.scalar("SELECT count(*) FROM media.publications WHERE ref = :r", r=ref) == 0
    async with hub.db.tx([pc["id"]]) as tx:
        assert await tx.scalar("SELECT count(*) FROM media.publications WHERE ref = :r", r=ref) == 1

    # ⟨2026-11-20⟩ the owner's views show only yesterday and today (Tehran) and what still has to
    # go out: three days back, the published row leaves every view; the row itself stays
    old = datetime.now(UTC) - timedelta(days=3)
    await su.execute(
        "UPDATE media.publications SET scheduled_at = $2, published_at = $2 WHERE ref = $1",
        ref,
        old,
    )
    assert (await client.get(f"/api/v1/publications/{ref}", headers=owner)).status_code == 404
    page = (await client.get("/api/v1/publications", headers=owner, params={"company": co})).json()
    assert page["items"] == []
    far = {"from": (old.date() - timedelta(days=1)).isoformat(),
           "to": (date.today() + timedelta(days=1)).isoformat()}  # fmt: skip
    tree = (await client.get("/api/v1/publications/tree", headers=owner, params=far)).json()
    assert all(c["code"] != co for c in tree["companies"])
    cal = (await client.get("/api/v1/publications/calendar", headers=owner,
                            params={**far, "company": co})).json()  # fmt: skip
    assert sum(d["published"] for d in cal["days"]) == 0
    # still to go out, however old its time: shown
    await su.execute("UPDATE media.publications SET state = 'held' WHERE ref = $1", ref)
    assert (await client.get(f"/api/v1/publications/{ref}", headers=owner)).status_code == 200
    page = (await client.get("/api/v1/publications", headers=owner, params={"company": co})).json()
    assert [c["ref"] for c in page["items"]] == [ref]
    # yesterday's: shown
    async with hub.db.tx([pc["id"]]) as tx:
        since = await PB.shown_from(tx)
    assert timedelta(hours=24) <= datetime.now(UTC) - since < timedelta(hours=48)
    await su.execute(
        "UPDATE media.publications SET state = 'published', published_at = $2 WHERE ref = $1",
        ref,
        since,
    )
    assert (await client.get(f"/api/v1/publications/{ref}", headers=owner)).status_code == 200
    assert await su.fetchval("SELECT count(*) FROM media.publications WHERE ref = $1", ref) == 1


# ------------------------------------------------------------- a set --
def a_slide(i: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (54, 96), (17 * i % 256, 255 - 13 * i % 256, 40 + i)).save(buf, format="PNG")
    return buf.getvalue()


async def slides_output(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], owner_session: dict[str, Any],
    su: Any, co: str, n: int,
) -> dict[str, Any]:  # fmt: skip
    """A session of `co` whose workshop turn delivered `n` picture stories (story_1 … story_n)."""
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    )
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    r = await run_ask(client, holder, {"work": work_ref, "brief": "استوری‌های امروز"})
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    files = []
    for i in range(1, n + 1):
        r = await send_file(client, rn, job["id"], f"story_{i}.png", "image/png", a_slide(i))
        assert r.status_code == 201, r.text
        files.append(r.json()["id"])
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": "cs-set-1", "result_fa": "ساخته شد.", "files": files}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    rep = (await client.get(f"/api/v1/orders/{out['ref']}/report", headers=owner)).json()
    return {"order": out["ref"], "output": rep["outputs"][-1]["ref"], "files": files,
            "work_ref": work_ref, "work_id": wid}  # fmt: skip


def test_late_stories_go_in_the_widest_gaps_of_the_same_day() -> None:
    """⟨2026-11-24⟩ the owner: «استوری های جا مانده هم انجام بده». A story whose hour went by goes
    out later the same day, in the middle of the widest gap; none when the day has no room."""
    t = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
    m = timedelta(minutes=1)
    slots = [t + 60 * m, t + 120 * m]
    got = FL.fill_late(slots, 3, t, t + 180 * m)
    assert got == [t + 30 * m, t + 90 * m, t + 150 * m]
    # the widest gap first, then the next widest
    assert FL.fill_late([t + 20 * m], 1, t, t + 120 * m) == [t + 70 * m]
    # never closer than LATE_GAP: a crowded evening takes fewer, a day that is over takes none
    assert FL.fill_late([], 9, t, t + 60 * m) == [t + 15 * m, t + 30 * m, t + 45 * m]
    assert FL.fill_late(slots, 2, t + 200 * m, t + 180 * m) == []
    assert FL.fill_late(slots, 0, t, t + 180 * m) == []


async def test_a_late_days_stories_all_go_out_the_same_day(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-24⟩ the day's stories were made at 14:00 (Tehran) instead of before 09:15: the five
    whose hours went by go out in the afternoon's gaps, the seven others at their own hours; sent
    again, nothing goes twice."""
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    names = tuple(f"story_{i}.png" for i in range(1, 13))
    made = await slides_output(client, hub, owner, owner_session, su, co, 12)
    await connected(client, hub, owner_session, ig, co)
    fk = f"s{uuid.uuid4().hex[:8]}"
    hours = tuple(f"{h:02d}:15" for h in range(9, 21))
    flow = FL.Flow(key=fk, company=co, account="pro.chart", title_fa="استوری روزانه‌ی آزمایشی",
                   kit="/kit", start=date(2026, 11, 14), hours=("09:00",), stories=hours)  # fmt: skip
    monkeypatch.setattr(FL, "FLOWS", {fk: flow})

    async def rule(tx: Tx, hub_: Any, d: Any) -> dict[str, Any]:
        return {"keywords": ["قله"], "reply": "لینک VIP"}

    monkeypatch.setattr(SPB, "comment_of", rule)
    tz = ZoneInfo(FL.TEHRAN)
    day = datetime.now(tz).date() + timedelta(days=1)
    at_two = datetime.combine(day, datetime.min.time().replace(hour=14), tz).astimezone(UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz_: Any = None) -> Any:  # type: ignore[override]
            return at_two if tz_ is not None else at_two.replace(tzinfo=None)

    monkeypatch.setattr(FL, "datetime", Clock)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        d = dict(await tx.one(SPB.OUTPUT_SQL + " WHERE d.ref = :r", r=made["output"]))
        files = {str(f["name"]): dict(f) for f in await SPB._files(tx, d)}
        pkg = {"d": d, "stories": [(files[n], d) for n in names], "comment_d": d, "topic_d": None}
        route = await SPB._route(tx, pc["id"])
        w = {"id": made["work_id"], "ref": made["work_ref"], "company_id": pc["id"], "company": co}
        meta = {"key": fk, "day": day.isoformat()}
        assert await FL._publish_stories(tx, hub, w, meta, pkg, route, "pro.chart") == "scheduled"
    set_key = f"pro.chart:{day.isoformat()}:{made['output']}"
    rows = await su.fetch(
        "SELECT set_n, scheduled_at FROM media.publications WHERE set_key = $1 ORDER BY set_n",
        set_key,
    )
    assert [r["set_n"] for r in rows] == list(range(1, 13))
    at = {r["set_n"]: r["scheduled_at"].astimezone(tz) for r in rows}
    end = datetime.combine(day, FL.LATE_DAY_END, tz)
    for n in range(1, 6):  # its hour went by: later today, after 14:00, before the day's end
        assert at_two < at[n] <= end and at[n].strftime("%M") != "15", (n, at[n])
    for n in range(6, 13):  # its own hour
        assert at[n].strftime("%H:%M") == hours[n - 1]
    assert len(set(at.values())) == 12
    # sent again: nothing goes twice
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await FL._publish_stories(tx, hub, w, meta, pkg, route, "pro.chart") == "scheduled"
    assert (
        await su.fetchval("SELECT count(*) FROM media.publications WHERE set_key = $1", set_key)
        == 12
    )


async def test_twelve_story_slides_are_one_set_scheduled_then_published(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    names = tuple(f"story_{i}.png" for i in range(1, 13))
    made = await slides_output(client, hub, owner, owner_session, su, co, 12)
    rn = await connected(client, hub, owner_session, ig, co)
    fk = f"s{uuid.uuid4().hex[:8]}"
    hours = tuple(f"{h:02d}:15" for h in range(9, 21))
    flow = FL.Flow(key=fk, company=co, account="pro.chart", title_fa="استوری روزانه‌ی آزمایشی",
                   kit="/kit", start=date(2026, 11, 14), hours=("09:00",), stories=hours)  # fmt: skip
    monkeypatch.setattr(FL, "FLOWS", {fk: flow})

    async def rule(tx: Tx, hub_: Any, d: Any) -> dict[str, Any]:
        return {"keywords": ["قله"], "reply": "لینک VIP"}

    monkeypatch.setattr(SPB, "comment_of", rule)
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        d = dict(await tx.one(SPB.OUTPUT_SQL + " WHERE d.ref = :r", r=made["output"]))
        files = {str(f["name"]): dict(f) for f in await SPB._files(tx, d)}
        pkg = {"d": d, "stories": [(files[n], d) for n in names], "comment_d": d, "topic_d": None}
        route = await SPB._route(tx, pc["id"])
        w = {"id": made["work_id"], "ref": made["work_ref"], "company_id": pc["id"], "company": co}
        meta = {"key": fk, "day": day.isoformat()}
        assert await FL._publish_stories(tx, hub, w, meta, pkg, route, "pro.chart") == "scheduled"
    set_key = f"pro.chart:{day.isoformat()}:{made['output']}"
    rows = await su.fetch(
        "SELECT * FROM media.publications WHERE set_key = $1 AND company_id = $2 ORDER BY set_n",
        set_key,
        pc["id"],
    )
    assert [r["set_n"] for r in rows] == list(range(1, 13))
    assert {r["state"] for r in rows} == {"scheduled"} and {r["kind"] for r in rows} == {"story"}
    assert all(
        _j(r["files"])[0]["role"] == "slide" and _j(r["files"])[0]["n"] == r["set_n"] for r in rows
    )
    assert {r["story_word"] for r in rows} == {"قله"}
    assert {_j(r["source"])["automation"] for r in rows} == {f"N8:{fk}"}
    assert {_j(r["source"])["day"] for r in rows} == {day.isoformat()}
    # one card for the set
    page = (await client.get("/api/v1/publications", headers=owner,
                             params={"company": co, "group": "set"})).json()  # fmt: skip
    assert len(page["items"]) == 1
    card = page["items"][0]
    assert (
        card["set"] == {"n": 12, "done": 0, "next_at": card["set"]["next_at"]}
        and card["set_key"] == set_key
    )
    assert card["automation"] == f"N8:{fk}" and card["automation_fa"] == "استوری روزانه‌ی آزمایشی"
    item = (await client.get(f"/api/v1/publications/{rows[4]['ref']}", headers=owner)).json()
    assert [x["n"] for x in item["set"]] == list(range(1, 13))
    # each goes out with its link
    for i in range(12):
        job = await take(client, rn)
        await answer(
            client, rn, job["id"], {"external_id": f"S{i}", "url": f"https://instagram.test/s/{i}"}
        )
    rows = await su.fetch(
        "SELECT state, url FROM media.publications WHERE set_key = $1 AND company_id = $2",
        set_key,
        pc["id"],
    )
    assert {r["state"] for r in rows} == {"published"} and all(r["url"] for r in rows)
    page = (await client.get("/api/v1/publications", headers=owner,
                             params={"company": co, "group": "set"})).json()  # fmt: skip
    assert page["items"][0]["set"]["done"] == 12
    today = (day - timedelta(days=1)).isoformat()
    cal = (await client.get("/api/v1/publications/calendar", headers=owner,
                            params={"company": co, "from": today, "to": day.isoformat()})).json()  # fmt: skip
    assert sum(d["published"] for d in cal["days"]) == 12
    assert "pro.chart" in {a for d in cal["days"] for a in d["accounts"]}


# ---------------------------------------------------- the 24-hour sweep --
async def test_the_sweep_never_takes_a_file_a_publication_row_refers_to(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co, cid = company["code"], company["id"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    root_ref = out["routes"][0]["work_ref"]
    slide = await a_file(su, hub, cid, "story_3.png", "image/png", b"slide " * 20)
    frame = await a_file(su, hub, cid, "reel-thumb.jpg", "image/jpeg", b"\xff\xd8\xff frame")
    notes = await a_file(su, hub, cid, "notes.md", "text/markdown", b"notes " * 20)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load_ref(tx, root_ref)
        d = await PL.deliver(tx, w, title="اسلایدها", body="اسلاید", close=False,
                             produced_with={"direct": True},
                             attachments=[str(slide), str(frame), str(notes)])  # fmt: skip
    files = [{"role": "slide", "file_id": str(slide), "n": 3}]
    await su.execute(
        """INSERT INTO media.publications (company_id, account, kind, state, title_fa, files,
               thumb_file_id, chain)
           VALUES ($1, 'pro.chart', 'story', 'published', 'یک اسلاید', $2::jsonb, $3,
                   ARRAY[$4::uuid])""",
        cid, json.dumps(files), frame, uuid.uuid4(),
    )  # fmt: skip
    await su.execute(
        """INSERT INTO files.publish_keep (output, company_id, job_id, published_at, kept)
           VALUES ($1, $2, $3, now() - interval '4 days', ARRAY[]::uuid[])""",
        d["ref"], cid, uuid.uuid4(),
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await PK.published_files(tx, [str(slide), str(frame), str(notes)]) == {
            str(slide),
            str(frame),
        }
    ids = await hub.companies.ids()
    got = await PK.sweep(hub, lambda: hub.db.tx(ids), now=datetime.now(UTC) + timedelta(hours=1))
    assert got["outputs"] >= 1
    # the slide and the frame a row refers to stay; the rest of the output went
    assert await su.fetchval("SELECT 1 FROM files.files WHERE id = $1", slide) == 1
    assert await su.fetchval("SELECT 1 FROM files.files WHERE id = $1", frame) == 1
    assert await su.fetchval("SELECT count(*) FROM files.files WHERE id = $1", notes) == 0


# ------------------------------------------------------------------ desk --
async def test_the_desk_shows_only_complete_packages_titled_by_their_topic(
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
    await connected(client, hub, owner_session, ig, co)
    full = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    lone = await an_output(client, hub, owner, owner_session, su, co, ("cover.png",))
    await _topic(su, co, full["order"], "هاوینگ بعدی کی است؟")

    async def ready() -> list[dict[str, Any]]:
        r = await client.get("/api/v1/publish-desk", headers=owner, params={"company": co})
        assert r.status_code == 200, r.text
        desk = r.json()
        assert "held" in desk
        return list(desk["ready"])

    cards = await ready()
    assert [c["output"] for c in cards] == [full["output"]]  # a cover alone has no card
    assert cards[0]["title_fa"] == "هاوینگ بعدی کی است؟" and cards[0]["group_fa"]
    # a pilot without an account is no card
    await su.execute(
        """UPDATE work.work SET run_meta = coalesce(run_meta, '{}'::jsonb)
               || '{"flow": {"key": "dotcoin_pilot", "account": ""}}'::jsonb WHERE id = $1""",
        full["work_id"],
    )
    assert await ready() == []
    await su.execute(
        "UPDATE work.work SET run_meta = run_meta - 'flow' WHERE id = $1", full["work_id"]
    )
    assert len(await ready()) == 1
    # a version superseded by a newer one of its chain is no card
    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load_ref(tx, lone["work_ref"])
        await PL.deliver(tx, w, title="نسخه‌ی تازه", body="نسخه‌ی تازه", close=False,
                         produced_with={"direct": True, "revision_of": full["output"]},
                         attachments=[])  # fmt: skip
    assert await ready() == []


# ---------------------------------------------------------------- search --
async def test_the_three_spellings_find_the_same_publications_of_every_page(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    tag = uuid.uuid4().hex[:6]
    refs = []
    for i, (account, text) in enumerate((("zaribsad", "درس امروز: بلاک‌چین"),
                                         ("theprochart", "بلاکچین چیست"),
                                         ("dotcoin.me", "بلاك چين و امنیت"))):  # fmt: skip
        co = await new_company()
        caption = f"{text} {tag}"
        refs.append(
            await su.fetchval(
                """INSERT INTO media.publications (company_id, account, kind, state, title_fa,
                       caption, chain, search_fa)
                   VALUES ($1, $2, 'reel', 'published', $3, $4, ARRAY[$5::uuid], $6) RETURNING ref""",
                co["id"], account, f"عنوان {i}", caption, uuid.uuid4(),
                PB.search_of(f"عنوان {i}", None, caption, [], None),
            )
        )  # fmt: skip
    seen = []
    for q in ("بلاکچین", "بلاک چین", "بلاک\u200cچین"):
        r = await client.get("/api/v1/publications", headers=owner, params={"q": q, "limit": 100})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        mine = [c for c in items if c["ref"] in refs]
        assert {c["ref"] for c in mine} == set(refs), q
        assert all(c["match"] == "caption" and c["snippet_fa"] for c in mine)
        seen.append(sorted(c["ref"] for c in items))
    assert seen[0] == seen[1] == seen[2]
    # a word of one only finds that one
    r = await client.get("/api/v1/publications", headers=owner, params={"q": f"چیست {tag}"})
    assert [c["ref"] for c in r.json()["items"]] == [refs[1]]


# ----------------------------------------------------- «منتظر شما» (cap) --
async def test_a_flows_day_past_its_cap_never_waits_for_the_owner(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨1.39⟩ the owner, 2026-11-17: cost never holds a flow, so «منتظر شما» has no `budget_cap`."""
    pc = await new_company()
    made = await an_output(client, hub, owner, owner_session, su, pc["code"], ("cover.png",))
    meta = {"key": "zaribsad_daily", "day": date.today().isoformat(), "account": "zaribsad",
            "capped": "100.00", "publish_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat()}  # fmt: skip
    await su.execute(
        """UPDATE work.work SET run_meta = coalesce(run_meta, '{}'::jsonb)
               || jsonb_build_object('flow', $2::jsonb) WHERE id = $1""",
        made["work_id"], json.dumps(meta),
    )  # fmt: skip
    got = (await client.get("/api/v1/publications/waiting", headers=owner)).json()
    assert all(x["kind"] == "publish_ask" for x in got["items"])
    assert f"cap:{made['work_ref']}" not in {x["id"] for x in got["items"]}
    r = await client.post(
        f"/api/v1/publications/waiting/cap:{made['work_ref']}/raise_cap", headers=owner, json={}
    )
    assert r.status_code == 422, r.text


# -------------------------------------------- the backfill, after a wipe --
class _Rollback(Exception):
    pass


async def test_the_backfill_makes_one_row_per_chain_again_after_a_fresh_start(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    owner_db: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    await _topic(su, co, order, "سه سطح طلا")
    rn = await connected(client, hub, owner_session, ig, co)
    body = {"output": output, "file_id": reel, "cover_file_id": cover, "caption": "کپشن طلا",
            "comment": {"keywords": ["طلا"], "reply": "این هم لینک"}}  # fmt: skip
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    tapped = UUID(r.json()["job"])
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "B1", "url": "https://instagram.test/B1"})
    first = await _row(su, "chain[1] = $1", tapped)
    args = _j(
        await su.fetchval("SELECT args FROM infra.server_jobs WHERE id = $1", first["chain"][0])
    )

    def same(row: Any) -> None:
        assert row["caption"] == args["caption"] == "کپشن طلا"
        assert _j(row["comment"])["keywords"] == args["meta"]["comment"]["keywords"]
        assert _j(row["comment"])["reply"] == args["meta"]["comment"]["reply"]
        assert row["state"] == "published" and row["url"] == "https://instagram.test/B1"
        assert row["title_fa"] == "سه سطح طلا" and row["chain"] == first["chain"]
        assert _j(row["source"])["output"] == output and _j(row["source"])["order"] == order

    # idempotent: a second run makes nothing
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await PB.backfill(tx)  # (the test database may hold jobs other tests wrote by hand)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        again = await PB.backfill(tx)
    assert again["made"] == 0 and again["chains"] >= 1
    # the prompt-16 fresh start (rolled back) keeps the row and every file it refers to
    head = await su.fetchrow("SELECT last_seq, last_hash FROM audit.chain_head")
    with pytest.raises(_Rollback):
        async with owner_db.raw() as tx:
            await tx.exec("SELECT 1")  # the transaction begins here: everything below rolls back
            raw = (await tx.conn.get_raw_connection()).driver_connection
            await raw.execute(FS.body("ab12cd34", head["last_seq"], head["last_hash"]))
            n = await raw.fetchval(
                "SELECT count(*) FROM cartable.deliverables WHERE ref = $1", output
            )
            assert n == 0
            kept = await raw.fetchrow(
                "SELECT * FROM media.publications WHERE ref = $1", first["ref"]
            )
            same(kept)
            for fid in kept["file_ids"]:
                assert await raw.fetchval("SELECT 1 FROM files.files WHERE id = $1", fid) == 1
            raise _Rollback
    # the clean start of 2026-11-17 (rolled back): the work, the outputs and the sessions are gone,
    # the jobs, the files and the topics stay; the backfill makes the same row from them, once
    with pytest.raises(_Rollback):
        async with owner_db.raw() as tx:
            await tx.exec("SELECT 1")  # the transaction begins here: everything below rolls back
            raw = (await tx.conn.get_raw_connection()).driver_connection
            await raw.execute("SET LOCAL session_replication_role = replica")
            await raw.execute("DELETE FROM cartable.deliverables WHERE ref = $1", output)
            await raw.execute("DELETE FROM work.work WHERE ref = $1", made["work_ref"])
            await raw.execute("DELETE FROM owner.orders WHERE ref = $1", order)
            await raw.execute("DELETE FROM media.publications WHERE ref = $1", first["ref"])
            got = await PB.backfill(Tx(tx.conn))
            assert got["made"] >= 1
            row = await raw.fetchrow(
                "SELECT * FROM media.publications WHERE chain[1] = $1", first["chain"][0]
            )
            same(row)
            assert row["thumb_file_id"] == first["thumb_file_id"]
            assert (await PB.backfill(Tx(tx.conn)))["made"] == 0
            raise _Rollback
