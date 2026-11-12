"""⟨1.31⟩ What the owner's reels order still lacked (contract §47 to §53).

The owner, 2026-11-10: «هیچ روزی تکراری نباشد: ۳۶۵ روز، ۳۶۵ مطلب», «گوینده یک بار برای همیشه تنظیم
شود», «در ساعت‌های پربازدید طبق زمان‌بندی منتشر کند», «کارمند ۲۴ ساعته» from one sentence, a
scheduled post taken back from the app, a picture that goes out as a JPEG, and the workshop on
its highest effort.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from PIL import Image

from hq_api.domain import best_hour as BH
from hq_api.domain import groups as GR
from hq_api.domain import routines as RT
from hq_api.domain import session_publish as SPB
from hq_api.domain import topics as TP
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .p10_fakes import holding_switch
from .test_p13a_media import hire as media_hire
from .test_p17_runners import take
from .test_p21_groups import TEHRAN, at
from .test_p21_routing_orders import auto_hiring, envelope  # noqa: F401 - the fixture
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p22_ops import DAILY_REPORT, route_answer, routes
from .test_p22_ops import work as work_action
from .test_p23_talk import talk  # noqa: F401 - the fixture
from .test_w8_speech import FakeWeb, clean, web  # noqa: F401 - the fixtures
from .test_w8_speech import make as speech
from .test_w14_workshop import refuse_queued, run_ask, workshop
from .test_w17_session_publish import an_output, tap
from .test_w18_standing_publish import a_day, a_group, args_of, caption_of, jobs_of
from .test_w19_publish_time import COMMAND, answer, asked, connected


async def claim(client: httpx.AsyncClient, who: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        "/internal/v1/topics/claim", headers=await agent_headers(who), json=body
    )


# ============================================================ §47 the ledger ==
def test_two_titles_that_say_the_same_are_one_topic() -> None:
    w = TP.words
    # the order of the words, Arabic and Persian letters, the half-space, marks and digits
    assert TP.norm_of(w("آموزش اندیکاتور RSI")) == TP.norm_of(w("اندیکاتور  rsi"))
    assert TP.norm_of(w("مقايسه‌ی پروچارت")) == TP.norm_of(w("مقایسه ی پروچارت"))
    assert w("۳ سطح طلا") == w("3 سطح طلا") and w("اندیکاتورها") == w("اندیکاتور")
    # «آموزش X» and «معرفی X» are one reel; another indicator is another topic
    brand = frozenset({"پروچارت", "پرو", "چارت", "prochart", "pc"})
    assert TP.same(w("آموزش اندیکاتور RSI"), w("معرفی اندیکاتور RSI در پروچارت چیست", brand))
    assert not TP.same(w("آموزش اندیکاتور RSI"), w("معرفی اندیکاتور RSI در پروچارت چیست"))
    assert w("پرو چارت", brand) == ["پرو", "چارت"]  # nothing but the name: it is kept
    assert TP.same(w("پرو چارت در برابر تریدینگ ویو"), w("پروچارت در برابر تریدینگ‌ویو"))
    assert not TP.same(w("اندیکاتور RSI"), w("اندیکاتور MACD"))
    assert not TP.same(w("مقایسه پروچارت با TradingView"), w("مقایسه پروچارت با CoinMarketCap"))
    assert not TP.same(w("واگرایی در اندیکاتور RSI"), w("اندیکاتور RSI"))  # a part of it is new
    assert not TP.same([], w("طلا"))
    # a title of nothing but filler still has its words
    assert w("آموزش و معرفی") == ["اموزش", "و", "معرفی"]
    # a reference is its address: a pin by its number, whatever the country or the query
    pin = TP.norm_url("https://ir.pinterest.com/pin/motion-graphic-12345678901/?utm=x")
    assert (
        pin
        == TP.norm_url("https://www.pinterest.com/pin/12345678901")
        == ("pinterest:pin:12345678901")
    )
    assert TP.norm_url("https://www.Example.com/a/b/?q=1#x") == "example.com/a/b"
    assert TP.norm_url("not a link") is None and TP.norm_url("ftp://x.test/a") is None


async def test_a_topic_is_named_before_it_is_made_and_never_twice(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    talk: None,  # noqa: F811
    auto_hiring: None,  # noqa: F811
    no_model: list[Any],  # noqa: F811
) -> None:
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch, None)
    co, key, writer = g["co"], g["key"], g["writer"]
    base = f"/api/v1/groups/{key}/members/{co}/topics"

    # day one: the routine's work is told how the ledger works (it is empty so far)
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    async with holding_switch(su, "released"):
        ticked = await GR.tick(hub, now=at(day, 8, 0), only={g["company"]["id"]})
    assert ticked["queued"] >= 1, ticked
    run = await su.fetchrow(
        """SELECT x.id, w.ref, w.brief FROM growth.routine_runs x
           JOIN growth.groups gr ON gr.id = x.group_id JOIN work.work w ON w.id = x.work_id
           WHERE gr.key = $1 ORDER BY x.occurrence_at DESC LIMIT 1""",
        key,
    )
    assert "topic.claim" in run["brief"] and "Already said" not in run["brief"]

    r = await claim(client, writer, {"work": run["ref"], "title_fa": "آموزش اندیکاتور RSI"})
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["new"] is True and first["group"] == key
    assert first["entry"]["kind"] == "topic" and first["entry"]["source"] == "claim"
    assert first["entry"]["by"] == writer and first["entry"]["work_ref"] == run["ref"]
    # the same one again by the same run is the same line
    r = await claim(client, writer, {"work": run["ref"], "title_fa": "اندیکاتور RSI آموزش"})
    assert r.status_code == 201 and r.json()["new"] is False, r.text
    assert r.json()["entry"]["id"] == first["entry"]["id"]
    # it changes its mind: a run names one topic, the second replaces the first
    r = await claim(client, writer, {"work": run["ref"], "title_fa": "اندیکاتور ATR در پروچارت"})
    assert r.status_code == 201 and r.json()["new"] is True, r.text
    assert r.json()["entry"]["id"] == first["entry"]["id"]
    # the sample it uses, by its address
    pin = "https://www.pinterest.com/pin/990011223344/"
    r = await claim(
        client, writer, {"work": run["ref"], "kind": "reference", "url": pin,
                         "title_fa": "حرکت نرم نمودار"},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["entry"]["url"] == pin, r.text
    r = await claim(
        client, writer, {"work": run["ref"], "kind": "reference", "title_fa": "بی نشانی"}
    )
    assert r.status_code == 422 and "url" in r.json()["fields"], r.text
    # somebody else's work is not one's own to name
    other = await new_company()
    r = await claim(client, f"{other['code']}-CEO", {"work": run["ref"], "title_fa": "طلا"})
    assert r.status_code == 403, r.text

    # the owner sees the ledger in the working group's page, adds a line and frees one
    r = await client.get(base, headers=owner)
    assert r.status_code == 200, r.text
    led = r.json()
    assert (led["topics"], led["references"]) == (1, 1)
    assert [e["title_fa"] for e in led["items"] if e["kind"] == "topic"] == [
        "اندیکاتور ATR در پروچارت"
    ]
    r = await client.post(base, headers=owner, json={"title_fa": "مقایسه با TradingView"})
    assert r.status_code == 201 and r.json()["source"] == "owner", r.text
    mine = r.json()["id"]
    r = await client.post(base, headers=owner, json={"title_fa": "مقایسه‌ی پروچارت با tradingview"})
    assert r.status_code == 201, r.text  # one word more of three: another topic
    r = await client.post(base, headers=owner, json={"title_fa": "TradingView مقایسه با"})
    assert r.status_code == 409 and r.json()["code"] == "topic_taken", r.text
    r = await client.get(base, headers=owner, params={"q": "tradingview", "kind": "topic"})
    assert len(r.json()["items"]) == 2 and r.json()["topics"] == 3

    # day two: what was said is in the brief, and saying it again is refused by code
    day2 = day + timedelta(days=1)
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day2, 8, 0), only={g["company"]["id"]})
    run2 = await su.fetchrow(
        """SELECT x.id, w.ref, w.brief FROM growth.routine_runs x
           JOIN growth.groups gr ON gr.id = x.group_id JOIN work.work w ON w.id = x.work_id
           WHERE gr.key = $1 ORDER BY x.occurrence_at DESC LIMIT 1""",
        key,
    )
    assert run2["id"] != run["id"]
    assert "Already said, newest first:" in run2["brief"]
    assert "اندیکاتور ATR در پروچارت" in run2["brief"] and "990011223344" in run2["brief"]
    r = await claim(
        client, writer, {"work": run2["ref"], "title_fa": "معرفی اندیکاتور ATR پروچارت"}
    )
    assert r.status_code == 409, r.text
    refused = r.json()
    assert (
        refused["code"] == "topic_taken"
        and "اندیکاتور ATR در پروچارت" in refused["fields"]["title_fa"]
    )
    assert "مقایسه با TradingView" in refused["fields"]["recent"]
    assert "اندیکاتور ATR در پروچارت" in refused["message_fa"]
    r = await claim(client, writer, {"work": run2["ref"], "kind": "reference",
                                     "url": "https://ir.pinterest.com/pin/990011223344"})  # fmt: skip
    assert r.status_code == 409, r.text
    r = await claim(client, writer, {"work": run2["ref"], "title_fa": "اندیکاتور MACD در پروچارت"})
    assert r.status_code == 201, r.text
    # the owner frees a line: it may be said once more; nothing is deleted
    r = await client.delete(f"{base}/{mine}", headers=owner)
    assert r.status_code == 200, r.text
    assert (await client.delete(f"{base}/{mine}", headers=owner)).status_code == 404
    assert await su.fetchval("SELECT state FROM growth.topics WHERE id = $1::uuid", mine) == "freed"
    r = await client.post(base, headers=owner, json={"title_fa": "مقایسه با TradingView"})
    assert r.status_code == 201, r.text
    audits = await su.fetch(
        "SELECT action FROM audit.entries WHERE company_id = $1 AND action LIKE 'topic.%'",
        g["company"]["id"],
    )
    assert {x["action"] for x in audits} == {"topic.claim", "topic.add", "topic.free"}


async def test_a_package_that_says_a_topic_again_is_not_sent_by_itself(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    talk: None,  # noqa: F811
    auto_hiring: None,  # noqa: F811
    no_model: list[Any],  # noqa: F811
) -> None:
    seal = {"publish": {"mode": "auto", "account": "@pro.chart"}}
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch, seal)
    key, co = g["key"], g["co"]
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    # day one names nothing: the hub reads the topic from the package it sends
    one = await a_day(client, hub, su, g, day, ("reel.mp4", "caption.txt"))
    [job] = await jobs_of(su, one["run"])
    assert args_of(job)["caption"] == caption_of(day)
    row = await su.fetchrow(
        "SELECT title_fa, source, output, by_code FROM growth.topics WHERE run_id = $1", one["run"]
    )
    assert (row["title_fa"], row["source"], row["output"]) == (
        caption_of(day).splitlines()[0], "package", one["output"],
    )  # fmt: skip
    # day two says the very same thing: held, told to him once, with one tap to send it anyway
    day2 = day + timedelta(days=1)
    again = {"caption.txt": caption_of(day)}
    two = await a_day(client, hub, su, g, day2, ("reel.mp4", "caption.txt"), texts=again)
    assert await jobs_of(su, two["run"]) == []
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", two["run"])
    assert note.startswith("موضوع این نوبت پیش‌تر گفته شده") and "خودکار منتشر نشد" in note
    n = await su.fetch(
        "SELECT link_ref FROM notify.notifications WHERE source_code = 'publish' AND company_id = $1",
        g["company"]["id"],
    )
    assert [x["link_ref"] for x in n] == [two["output"]]
    assert await SPB.after_delivered(hub, two["work_id"]) == "held"  # said once, never again
    assert len(await su.fetch(
        "SELECT 1 FROM notify.notifications WHERE source_code = 'publish' AND company_id = $1",
        g["company"]["id"])) == 1  # fmt: skip
    # his own tap sends it all the same: his choice
    r = await client.post(
        f"/api/v1/deliverables/{two['output']}/publish",
        headers={**owner, **idem()},
        json={"file_id": two["files"]["reel.mp4"], "caption": caption_of(day)},
    )
    assert r.status_code == 202 and r.json()["state"] == "publishing", r.text
    # day three has `topic.txt`: that names it, whatever the caption opens with
    day3 = day2 + timedelta(days=1)
    named = {"caption.txt": "این هفته چه خبر؟\n#پروچارت", "topic.txt": "ابزار هشدار قیمت"}
    three = await a_day(
        client, hub, su, g, day3, ("reel.mp4", "caption.txt", "topic.txt"), texts=named
    )
    assert len(await jobs_of(su, three["run"])) == 1
    assert await su.fetchval(
        "SELECT title_fa FROM growth.topics WHERE run_id = $1", three["run"]
    ) == "ابزار هشدار قیمت"  # fmt: skip
    r = await client.get(f"/api/v1/groups/{key}/members/{co}/topics", headers=owner)
    assert r.json()["topics"] == 2 and r.json()["items"][0]["output"] == three["output"]


# ========================================================== §48 the narrator ==
async def test_a_companys_narrator_is_set_once_and_speech_make_takes_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    web: FakeWeb,  # noqa: F811
    clean: None,  # noqa: F811
) -> None:
    co = await new_company()
    code = co["code"]
    producer = await media_hire(su, co, "voice_producer")
    r = await client.get(f"/api/v1/companies/{code}/narrator", headers=owner)
    assert r.status_code == 200, r.text
    none = r.json()
    assert none["set"] is False and none["voice"] == "Kore" and none["aistudio"] == "signed_in"
    assert {"Kore", "Charon", "Puck"} <= {v["name"] for v in none["voices"]}
    # without one, the model's own choice is used
    r = await speech(client, producer, {"text_fa": "سلام", "voice": "Puck", "style": "تند"})
    assert r.status_code == 202 and r.json()["narrator"] is False, r.text
    assert (web.sent[-1]["voice"], web.sent[-1]["style"]) == ("Puck", "تند")

    bad = await client.put(
        f"/api/v1/companies/{code}/narrator", headers=owner, json={"voice": "Nobody"}
    )
    assert bad.status_code == 422 and "voice" in bad.json()["fields"], bad.text
    r = await client.put(
        f"/api/v1/companies/{code}/narrator",
        headers=owner,
        json={"voice": "charon", "style_fa": "آرام و مطمئن، مثل گوینده‌ی خبر"},
    )
    assert r.status_code == 200, r.text
    fixed = r.json()
    assert fixed["set"] is True and fixed["voice"] == "Charon" and fixed["by"] == "owner"
    # from now on: this voice in this style, whatever the model asks for
    r = await speech(client, producer, {"text_fa": "با پروچارت همیشه با نمودار", "voice": "Puck"})
    assert r.status_code == 202, r.text
    got = r.json()
    assert (got["voice"], got["style"], got["narrator"]) == (
        "Charon", "آرام و مطمئن، مثل گوینده‌ی خبر", True,
    )  # fmt: skip
    assert (web.sent[-1]["voice"], web.sent[-1]["style"]) == (
        "Charon", "آرام و مطمئن، مثل گوینده‌ی خبر",
    )  # fmt: skip
    r = await speech(client, producer, {"text_fa": "بی سبک و بی نام"})
    assert r.status_code == 202 and web.sent[-1]["voice"] == "Charon", r.text
    # another company keeps its own
    other = await new_company()
    theirs = await media_hire(su, other, "voice_producer")
    r = await speech(client, theirs, {"text_fa": "سلام"})
    assert r.status_code == 202 and r.json()["narrator"] is False, r.text
    row = await su.fetchrow(
        "SELECT action_class, actor_kind FROM audit.entries "
        "WHERE action = 'narrator.set' AND company_id = $1",
        co["id"],
    )
    assert (row["action_class"], row["actor_kind"]) == ("A2", "owner")
    # the brief of whoever works for the company names it
    from hq_api.domain import capabilities as CAP

    async with hub.db.tx(await hub.companies.ids()) as tx:
        brief = await CAP.brief(tx, co["id"], n8n_up=False)
    assert brief["narration"]["narrator"]["voice"] == "Charon"


async def test_the_holder_of_his_session_sets_the_narrator_when_he_asks(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
) -> None:
    co = await new_company()
    code = co["code"]
    out = await post_order(client, owner, f"برای {code} {words()} گوینده‌ی ریلزها را Leda بگذار")
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    r = await client.post(
        "/internal/v1/narrator",
        headers=await agent_headers(holder),
        json={"work": work_ref, "voice": "Leda", "style_fa": "جوان و پرانرژی"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["voice"] == "Leda" and r.json()["company"] == code
    got = (await client.get(f"/api/v1/companies/{code}/narrator", headers=owner)).json()
    assert got["set"] is True and got["by"] == holder and got["style_fa"] == "جوان و پرانرژی"
    # a work of no order of the owner's: not this way
    wid = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code,
               assignee_id)
           SELECT $1, 'one_off', 'کار بی فرمان', 'service', 'test', e.id
           FROM core.employees e WHERE e.code = $2 RETURNING ref""",
        co["id"],
        f"{code}-CEO",
    )
    r = await client.post(
        "/internal/v1/narrator",
        headers=await agent_headers(f"{code}-CEO"),
        json={"work": wid, "voice": "Puck"},
    )
    assert r.status_code == 403, r.text


# ========================================================= §49 the best hour ==
def test_the_best_hour_needs_a_month_and_is_not_one_lucky_post() -> None:
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    def post(days_ago: float, hour_utc: int, e: int) -> tuple[datetime, int]:
        t = (now - timedelta(days=days_ago)).replace(hour=hour_utc, minute=5)
        return t, e

    # too few, or too short a time: no hour yet
    few = [post(d, 15, 100) for d in range(3, 9)]
    assert BH.choose(few, "Asia/Tehran", now) == (None, 6, 6)
    short = [post(3 + d * 0.5, 15, 100) for d in range(20)]
    hour, n, days = BH.choose(short, "Asia/Tehran", now)
    assert hour is None and n == 20 and days < BH.MIN_DAYS
    # a month of posts at two hours: the evening ones do better (18:30 UTC+3:30 = 15:00 UTC)
    posts = [post(3 + d * 2, 15, 120 + d) for d in range(14)]
    posts += [post(4 + d * 2, 6, 40) for d in range(14)]
    hour, n, days = BH.choose(posts, "Asia/Tehran", now)
    assert (hour, n) == (18, 28) and days >= BH.MIN_DAYS
    # one lucky post at another hour does not make that hour (an hour needs two posts)
    lucky = [*posts, post(10, 21, 5000)]
    assert BH.choose(lucky, "Asia/Tehran", now)[0] == 18
    # two there pull it only as far as they deserve, toward the account's own mean
    assert BH.choose([*lucky, post(12, 21, 60)], "Asia/Tehran", now)[0] in (0, 18)
    # a post of the last two days is still counting, and one older than the window is history
    fresh = [*posts, post(0.5, 9, 9000), post(1, 9, 9000), post(200, 9, 9000), post(201, 9, 9000)]
    assert BH.choose(fresh, "Asia/Tehran", now)[0] == 18
    # the hour's next occurrence: today while it is ahead (a standing package is not kept)
    assert BH.next_at(18, "Asia/Tehran", now, tomorrow=False) == datetime(
        2026, 11, 10, 14, 30, tzinfo=UTC
    )
    assert BH.next_at(9, "Asia/Tehran", now, tomorrow=False) is None
    assert BH.next_at(9, "Asia/Tehran", now) == datetime(2026, 11, 11, 5, 30, tzinfo=UTC)
    # the command is the company's own publish command, and IG-Hub's answer is read strictly
    assert BH.command("python3 /srv/ig-hub/deploy/hq_publish.py", "@pro.chart") == (
        "python3 /srv/ig-hub/deploy/hq_publish.py posts pro.chart 100"
    )
    text = (
        'noise\n{"items": [{"id": "17", "media_type": "VIDEO", "permalink": "https://i/p/1", '
        '"posted_at": "2026-11-01T15:00:00+00:00", "like_count": 40, "comments_count": 2, '
        '"caption": "x"}, {"id": "", "posted_at": "x"}, {"id": "18", "posted_at": '
        '"2026-11-02T15:00:00"}], "hours": []}'
    )
    assert BH.parse(text) == [
        {"post_id": "17", "posted_at": datetime(2026, 11, 1, 15, 0, tzinfo=UTC),
         "media_type": "VIDEO", "permalink": "https://i/p/1", "likes": 40, "comments": 2}
    ]  # fmt: skip
    assert BH.parse("فایلی برای انتشار نرسید") is None and BH.parse('{"accounts": []}') is None


async def test_the_hub_reads_the_posts_from_ig_hub_and_publishes_at_the_best_hour(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    monkeypatch: pytest.MonkeyPatch,
    talk: None,  # noqa: F811
    auto_hiring: None,  # noqa: F811
    no_model: list[Any],  # noqa: F811
) -> None:
    seal = {"publish": {"mode": "auto", "account": "@pro.chart", "at": "07:15", "best": True}}
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch, seal)
    key, co, cid, rn = g["key"], g["co"], g["company"]["id"], g["ig_rn"]
    member = (await client.get(f"/api/v1/groups/{key}/members", headers=owner)).json()[0]
    assert member["publish"]["best"] is True and member["publish"]["at"] == "07:15"

    # nothing read yet: said as it is, no hour
    r = await client.get(f"/api/v1/companies/{co}/best-hour", headers=owner)
    assert r.status_code == 200, r.text
    none = r.json()
    assert none["enough"] is False and none["hour"] is None and none["account"] == "pro.chart"
    assert none["basis"] == "likes_comments" and "خوانده نشده" in none["note_fa"]

    # the daily read: one read-only job on IG-Hub's server, the company's own command
    now = datetime.now(UTC)
    got = await BH.read_due(hub, now)
    assert got["asked"] >= 1, got
    job = await take(client, rn)
    assert job["kind"] == "exec" and job["args"]["cmd"] == f"{g_command(g)} posts pro.chart 100"
    assert (await BH.read_due(hub, now))["waiting"] >= 1  # on its way: not asked twice
    # a month of posts: the ones at one hour of his day draw the most
    local = now.astimezone(TEHRAN)
    best_hour = (local.hour + 3) % 24
    other_hour = (local.hour + 9) % 24

    def posted(days_ago: int, hour: int) -> str:
        t = (local - timedelta(days=days_ago)).replace(hour=hour, minute=10, second=0)
        return t.astimezone(UTC).isoformat()

    items = [
        {"id": f"b{d}", "media_type": "VIDEO", "permalink": f"https://www.instagram.com/reel/b{d}/",
         "posted_at": posted(3 + d * 2, best_hour), "like_count": 300 + d, "comments_count": 20}
        for d in range(15)
    ] + [
        {"id": f"o{d}", "media_type": "IMAGE", "permalink": None,
         "posted_at": posted(4 + d * 2, other_hour), "like_count": 30, "comments_count": 1}
        for d in range(15)
    ]  # fmt: skip
    import json as _json

    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events",
        json={"events": [{"seq": 1, "type": "stdout",
                          "data": {"text": _json.dumps({"items": items, "hours": []})}}]},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    await answer(client, rn, job["id"], None)
    assert (await BH.read_due(hub, now))["read"] >= 1
    assert await su.fetchval(
        "SELECT count(*) FROM growth.ig_posts WHERE company_id = $1 AND account = 'pro.chart'", cid
    ) == 30  # fmt: skip
    assert (await BH.read_due(hub, now))["asked"] == 0  # read today: tomorrow again

    r = await client.get(f"/api/v1/companies/{co}/best-hour", headers=owner)
    best = r.json()
    assert best["enough"] is True and best["hour"] == f"{best_hour:02d}:00", best
    assert best["posts"] == 30 and best["days"] >= BH.MIN_DAYS and best["at"] is not None
    assert "لایک و کامنت" in best["note_fa"] and "reach" in best["note_fa"]
    bad = await client.get(
        f"/api/v1/companies/{co}/best-hour", headers=owner, params={"account": "someone"}
    )
    assert bad.status_code == 422, bad.text

    # the standing word with «بهترین ساعت»: today's package is set for that hour while it is
    # ahead (never his fixed 07:15 once there is a month of data)
    day = datetime.now(TEHRAN).date()
    made = await a_day(client, hub, su, g, day, ("reel.mp4", "caption.txt"))
    assert "at the hour this account's posts do best" in made["brief"]
    [pub] = await jobs_of(su, made["run"])
    want = BH.next_at(best_hour, "Asia/Tehran", datetime.now(UTC), tomorrow=False)
    sched = args_of(pub)["meta"].get("scheduled_at")
    if want is None:  # the test runs late in his day: the hour has passed, it goes out now
        assert sched is None
    else:
        assert sched is not None and datetime.fromisoformat(sched) == want
    # the output's page offers the hour for his own tap too
    panel = (
        await client.get(f"/api/v1/deliverables/{made['output']}/publish", headers=owner)
    ).json()
    assert panel["best"]["hour"] == f"{best_hour:02d}:00" and panel["best"]["enough"] is True


def g_command(g: dict[str, Any]) -> str:
    from .test_w18_standing_publish import COMMAND as GROUP_COMMAND

    return GROUP_COMMAND


# ================================================ §50 a routine from a sentence ==
def test_a_routine_is_a_schedule_that_makes_work_or_tells_someone() -> None:
    assert RT.is_routine(DAILY_REPORT)
    assert RT.is_routine({**DAILY_REPORT, "actions": [work_action()]})
    event = {**DAILY_REPORT, "trigger": {"kind": "event", "type": "work.completed"}}
    assert not RT.is_routine(event) and not RT.is_routine(None)
    line = {"kind": "line.run", "args": {"line": "LN-0001"}}
    assert not RT.is_routine({**DAILY_REPORT, "actions": [work_action(), line]})
    assert not RT.is_routine({**DAILY_REPORT, "actions": []})
    yes = ("یک کارمند سئوی ۲۴ ساعته برای پروچارت", "هر روز ساعت ۹ رتبه‌ها را ببین",
           "هفتگی یک خلاصه بده", "هر ۶ ساعت سایت را ببین", "this report daily",
           "مرتباً فروش را گزارش بده", "به‌طور مرتب سایت را ببین", "گزارش روزانه‌ای بده",
           "کار 24/7")  # fmt: skip
    no = ("یک ریلز درباره‌ی طلا بساز", "وضع شرکت را بررسی کن", "",
          # audit 2026-11-11: «مرتب» inside an unrelated word is not a word of repetition
          "یک گزارش مرتبط با فروش هفته بده", "برای بار دوم مرتبه‌ی سایت را ببین",
          "فایل‌ها را مرتب کن", "در شهر تهران روز جمعه جلسه بگذار")  # fmt: skip
    assert all(RT.asks_for_a_routine([s]) for s in yes)
    assert not any(RT.asks_for_a_routine([s]) for s in no)
    nxt = RT.next_run(
        "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "Asia/Tehran", datetime(2026, 11, 10, 12, tzinfo=UTC)
    )
    assert nxt == datetime(2026, 11, 11, 5, 30, tzinfo=UTC)
    assert RT.next_run("nonsense", "Asia/Tehran") is None


async def test_the_owner_says_one_sentence_and_the_routine_runs(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    out = await post_order(client, owner, f"برای {co} {words()} وضع سئوی سایت را بررسی کن")
    order = out["ref"]
    rule = {**DAILY_REPORT, "actions": [work_action("رصد روزانه‌ی سئو")]}
    route_answer(monkeypatch, routes(rule))
    cards = await su.fetchval("SELECT count(*) FROM cartable.decisions WHERE status = 'pending'")
    r = await client.post(
        "/api/v1/routines",
        headers={**owner, **idem()},  # his bearer alone: no step-up assertion
        json={"sentence_fa": "هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده", "order": order},
    )
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["state"] == "on" and made["company"] == co and made["order"] == order
    assert made["when_fa"] == "هر روز ساعت 09:00" and "رصد روزانه‌ی سئو" in made["preview_fa"]
    assert made["next_at"] is not None and made["runs"] == 0
    row = await su.fetchrow(
        "SELECT state, sealed_at, sealed_step_up_id, source FROM growth.automations WHERE ref = $1",
        made["ref"],
    )
    assert row["state"] == "on" and row["sealed_at"] is not None
    assert row["sealed_step_up_id"] is None  # no fingerprint of his was asked for
    assert cards == await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE status = 'pending'"
    )
    # the session says so and lists it; the list of routines has it
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    assert [x["ref"] for x in rep["routines"]] == [made["ref"]]
    assert any(
        s["who_fa"] == "مدیر کل" and s["what_fa"].startswith("روال دائمی ساخته شد: هر روز ساعت")
        for s in rep["steps"]
    )
    listed = (await client.get("/api/v1/routines", headers=owner, params={"company": co})).json()
    assert [x["ref"] for x in listed] == [made["ref"]]
    auto = (await client.get(f"/api/v1/automations/{made['ref']}", headers=owner)).json()
    assert auto["routine"] is True and auto["order"] == order
    # one tap switches it off (and on again)
    r = await client.post(
        f"/api/v1/automations/{made['ref']}/state", headers=owner, json={"state": "off"}
    )
    assert r.status_code == 200 and r.json()["state"] == "off", r.text
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    assert rep["routines"][0]["state"] == "off" and rep["routines"][0]["next_at"] is None

    # more than a routine is still an automation he seals: nothing is made here
    n = await su.fetchval("SELECT count(*) FROM growth.automations")
    event = {**rule, "trigger": {"kind": "event", "type": "work.completed"}}
    route_answer(monkeypatch, routes(event))
    r = await client.post(
        "/api/v1/routines", headers={**owner, **idem()},
        json={"sentence_fa": "هر وقت کاری تمام شد یک کار تازه بساز", "company": co},
    )  # fmt: skip
    assert r.status_code == 422 and "روال" in r.json()["message_fa"], r.text
    route_answer(monkeypatch, routes(None, ["زمان این کار روشن نیست."]))
    r = await client.post(
        "/api/v1/routines", headers={**owner, **idem()},
        json={"sentence_fa": "یک کاری بکن", "company": co},
    )  # fmt: skip
    assert r.status_code == 422 and r.json()["message_fa"] == "زمان این کار روشن نیست.", r.text
    assert n == await su.fetchval("SELECT count(*) FROM growth.automations")
    r = await client.post(
        "/api/v1/routines", headers={**owner, **idem()},
        json={"sentence_fa": "هر روز گزارش بده", "order": "F-999999"},
    )  # fmt: skip
    assert r.status_code == 404, r.text


async def test_the_holder_makes_the_routine_when_his_words_ask_for_one(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rule = {**DAILY_REPORT, "actions": [work_action("گزارش صبح")]}

    async def propose(order: dict[str, Any], sentence: str) -> httpx.Response:
        [route] = order["routes"]
        holder = route["to"]
        # the holder's run is for the order's own work (a run's work never changes)
        await su.execute(
            """UPDATE agents.runs r SET state = 'refused', finished_at = now()
               FROM core.employees e WHERE e.id = r.employee_id AND e.code = $1
                 AND r.state IN ('queued', 'running')""",
            holder,
        )
        await su.execute(
            """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
                   started_at, token_expires_at)
               SELECT e.company_id, e.id, w.id, 'work', 'test', 'running', now(),
                      now() + interval '1 hour'
               FROM core.employees e, work.work w WHERE e.code = $1 AND w.ref = $2""",
            holder,
            route["work_ref"],
        )
        headers = await agent_headers(holder)
        route_answer(monkeypatch, routes(rule))
        return await client.post(
            "/internal/v1/automations/propose",
            headers={**headers, **idem()},
            json={"sentence_fa": sentence},
        )

    # he asked for nothing standing: a proposal, as before, and the owner is told
    plain = await post_order(client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن")
    r = await propose(plain, "هر روز ساعت ۹ گزارش صبح بده")
    assert r.status_code == 201 and r.json()["state"] == "proposed", r.text
    assert r.json()["routine"] is False
    # he says it in the session («هر روز»): it is on in that request
    r = await client.post(
        f"/api/v1/orders/{plain['ref']}/reply",
        headers={**owner, **idem()},
        json={"text": "یک کارمند ۲۴ ساعته میخواهم که هر روز صبح گزارش بدهد"},
    )
    assert r.status_code == 200, r.text
    r = await propose(plain, "هر روز ساعت ۹ گزارش صبح را برای مدیر کل بفرست")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["state"] == "on" and a["routine"] is True and a["order"] == plain["ref"]
    row = await su.fetchrow(
        "SELECT sealed_step_up_id, sealed_at FROM growth.automations WHERE ref = $1", a["ref"]
    )
    assert row["sealed_at"] is not None and row["sealed_step_up_id"] is None
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_kind = 'automation' AND link_ref = $1",
        a["ref"],
    ) == 0  # nothing waits for him: no card, no notice to seal  # fmt: skip
    rep = (await client.get(f"/api/v1/orders/{plain['ref']}/report", headers=owner)).json()
    assert [x["ref"] for x in rep["routines"]] == [a["ref"]]
    assert any(
        s["what_fa"].startswith("روال دائمی به خواست مدیر کل ساخته شد") for s in rep["steps"]
    )
    audit = await su.fetchrow(
        "SELECT actor_kind, action_class FROM audit.entries "
        "WHERE action = 'automation.routine' AND target_ref = $1",
        a["ref"],
    )
    assert (audit["actor_kind"], audit["action_class"]) == ("agent", "A1")


# ================================== §51 a scheduled post taken back from the app ==
async def test_a_scheduled_post_is_cancelled_from_the_app(
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
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "two.mp4"))
    order, output, (reel, two) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=5)
    body = {"output": output, "file_id": reel, "caption": "سه سطح طلا",
            "scheduled_at": later.isoformat()}  # fmt: skip

    async def cancel(job: str) -> httpx.Response:
        return await client.post(f"/api/v1/publishes/{job}/cancel", headers=owner)

    # 1. cancelled before the runner took it: gone at once, nothing reaches IG-Hub
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    first = r.json()["job"]
    r = await cancel(first)
    assert r.status_code == 200 and r.json()["state"] == "cancelled", r.text
    assert (await client.get("/api/v1/runners/jobs/next", params={"wait": 0}, headers=rn["h"])
            ).status_code == 204  # fmt: skip
    assert (await cancel(first)).status_code == 409  # cancelled already
    assert (await cancel("00000000-0000-4000-8000-000000000009")).status_code == 404

    # 2. a new tap is a new publication; IG-Hub holds it for its time
    r = await tap(client, owner, order, body)
    assert r.status_code == 202 and r.json()["job"] != first, r.text
    pub = r.json()["job"]
    job = await take(client, rn)
    r = await cancel(pub)  # the file is on its way: not yet
    assert r.status_code == 409 and r.json()["code"] == "not_cancellable", r.text
    await answer(client, rn, job["id"], {"external_id": "pub:41", "url": None})
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    assert rep["publishes"][0]["state"] == "scheduled"

    # 3. he takes it back: one job with meta `cancel` and no file, on IG-Hub's server
    r = await cancel(pub)
    assert r.status_code == 200, r.text
    going = r.json()
    assert going["state"] == "scheduled" and going["note_fa"] == "در حال لغو"
    assert (await cancel(pub)).json()["job"] == going["job"]  # the cancel is on its way already
    c = await take(client, rn)
    assert c["id"] == going["job"] and c["args"]["files"] == [] and c["args"]["caption"] == ""
    assert c["args"]["meta"]["cancel"] == "pub:41" and "check" not in c["args"]["meta"]
    assert c["args"]["command"] == COMMAND
    # IG-Hub refuses (an older command there): the publication stands, said plainly, followed on
    await answer(client, rn, c["id"], None, exit_code=1, why="فایلی برای انتشار نرسید")
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    p = rep["publishes"][0]
    assert p["state"] == "scheduled" and p["note_fa"].startswith("لغو انجام نشد")
    said = [s["what_fa"] for s in rep["steps"]]
    assert any(x.startswith("لغو ریلز در @pro.chart انجام نشد") for x in said), said
    assert await asked(hub, su, output, later + timedelta(minutes=5)) == 1  # still followed
    q = await take(client, rn)
    assert q["args"]["meta"]["check"] == "pub:41" and "cancel" not in q["args"]["meta"]
    await answer(client, rn, q["id"], {"external_id": "pub:41", "url": None})

    # 4. again, and IG-Hub cancels it: the session says so, nothing follows it any more
    r = await cancel(pub)
    assert r.status_code == 200, r.text
    c = await take(client, rn)
    await answer(client, rn, c["id"], {"external_id": "cancelled:pub:41", "url": None})
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    p = rep["publishes"][0]
    assert p["state"] == "cancelled" and p["url"] is None and p["published_at"] is None
    said = [s["what_fa"] for s in rep["steps"]]
    assert "لغو شد: ریلز در @pro.chart منتشر نمیشود" in said
    assert sum(1 for x in said if x.startswith("لغو انتشار: ریلز در @pro.chart")) == 2
    n = await asked(hub, su, output, later + timedelta(hours=1))
    assert await asked(hub, su, output, later + timedelta(hours=2)) == n == 1
    assert (await cancel(pub)).status_code == 409
    audits = await su.fetch(
        "SELECT action_class, actor_kind FROM audit.entries WHERE action = 'publish.cancel' "
        "AND company_id = $1",
        pc["id"],
    )
    assert len(audits) == 3 and {(a["action_class"], a["actor_kind"]) for a in audits} == {
        ("A2", "owner")
    }

    # 5. a cancel that comes too late: it went out first, and that is what the session says
    r = await tap(client, owner, order, {**body, "file_id": two})
    late = r.json()["job"]
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:42", "url": None})
    assert (await cancel(late)).status_code == 200
    c = await take(client, rn)
    await answer(
        client, rn, c["id"], {"external_id": "1790", "url": "https://www.instagram.com/reel/Cy1/"}
    )
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    p = next(x for x in rep["publishes"] if x["file_id"] == two)
    assert p["state"] == "published" and p["url"] == "https://www.instagram.com/reel/Cy1/"
    assert (await cancel(late)).status_code == 409


# ==================================================== §52 a picture as a JPEG ==
def test_a_picture_becomes_a_jpeg_on_white() -> None:
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (255, 0, 0, 0)).save(buf, format="PNG")  # see-through
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(buf.getvalue())
        f.flush()
        data, w, h = SPB._to_jpeg(f.name)
    assert data[:3] == b"\xff\xd8\xff" and (w, h) == (40, 20)
    px = Image.open(io.BytesIO(data)).convert("RGB").getpixel((5, 5))
    assert all(c > 240 for c in px)  # white where it was see-through, not black
    big = io.BytesIO()
    Image.new("RGB", (6000, 3000), (10, 20, 30)).save(big, format="WEBP")
    with tempfile.NamedTemporaryFile(suffix=".webp") as f:
        f.write(big.getvalue())
        f.flush()
        _, w, h = SPB._to_jpeg(f.name)
    assert (w, h) == (SPB.JPEG_SIDE, SPB.JPEG_SIDE // 2)
    with tempfile.NamedTemporaryFile(suffix=".png") as f, pytest.raises(Exception):  # noqa: B017
        f.write(b"not a picture")
        f.flush()
        SPB._to_jpeg(f.name)
    assert SPB.publication_key("O-1", "f", "a", "reel") == SPB.publication_key(
        "O-1", "f", "a", "reel"
    )
    assert SPB.publication_key("O-1", "f", "a", "reel") != SPB.publication_key(
        "O-1", "f", "a", "story"
    )


async def test_a_png_is_converted_once_and_reused(
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
    made = await an_output(client, hub, owner, owner_session, su, co, ("art.png",))
    order, output, (art,) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    r = await tap(client, owner, order, {"output": output, "file_id": art, "kind": "post"})
    assert r.status_code == 202 and r.json()["file_name"] == "art.png", r.text
    job = await take(client, rn)
    [f] = job["args"]["files"]
    assert f["name"] == "art.jpg" and f["mime"] == "image/jpeg"
    jpeg = f["file_id"]
    # Instagram refused it: his next tap, as a story, sends the same JPEG (made once)
    await answer(client, rn, job["id"], None, exit_code=1, why="اینستاگرام نپذیرفت")
    r = await tap(client, owner, order, {"output": output, "file_id": art, "kind": "story"})
    assert r.status_code == 202, r.text
    again = await take(client, rn)
    assert again["args"]["files"][0]["file_id"] == jpeg
    assert await su.fetchval(
        "SELECT count(*) FROM files.files WHERE meta ->> 'jpeg_of' = $1", art
    ) == 1  # fmt: skip
    row = await su.fetchrow(
        "SELECT company_id, variant, created_by_kind FROM files.files WHERE id = $1::uuid", jpeg
    )
    assert (row["company_id"], row["variant"], row["created_by_kind"]) == (
        pc["id"],
        "original",
        "service",
    )


# ============================================ §53 the workshop's highest effort ==
async def test_a_workshop_turn_thinks_as_hard_as_it_can_unless_asked_for_less(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    co = (await new_company())["code"]
    rn = await workshop(client, hub, owner_session, su, version="0.3.5")
    out = await post_order(client, owner, f"برای {co} {words()} یک موشن‌گرافی بساز")
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    r = await run_ask(client, holder, {"work": work_ref, "brief": "موشن‌گرافی ATR را بساز"})
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    assert job["args"]["effort"] == "max" and job["args"]["model"] == "claude-opus-5-5"
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": "cs-eff-1", "result_fa": "ساخته شد.", "effort": "max"}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    made = await su.fetchval(
        "SELECT produced_with FROM cartable.deliverables WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1",
        wid,
    )
    import json as _json

    made = _json.loads(made) if isinstance(made, str) else made
    assert made["effort"] == "max" and made["model"] == "claude-opus-5-5"
    # the next turn of the same work keeps it unless the caller asks for less
    r = await run_ask(
        client, holder, {"work": work_ref, "brief": "رنگ را آبی کن", "effort": "medium"}
    )
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    assert job["args"]["effort"] == "medium"
    bad = await run_ask(client, holder, {"work": work_ref, "brief": "x", "effort": "ultra"})
    assert bad.status_code == 422, bad.text
