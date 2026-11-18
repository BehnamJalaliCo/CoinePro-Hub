"""⟨2026-11-18⟩ @behnamjalali.tech's automations (the owner's last page: tech & AI): what the hub needed.

- A flow is never started for a day before its first day (ipoxxo_reels_3, made on 11-18 for 11-19, ran
  on 11-18 too).
- An event's flow (recipe «breaking»: the breaking-news flash story and its full reel) is a row on the
  board that the clock never starts; the hub's watcher starts it once per news item (flow_events), and the
  same item never twice.
- create_by_hub makes a stories flow too (its hours, a fixed or fresh reply word).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import flow_defs as FD
from hq_api.domain import flow_events as EV
from hq_api.domain import flows as FL
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_p39_flows import OPUS, a_flow, all_off, fk, seed, tomorrow

WORKS = """SELECT count(*) FROM work.work WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'key' = $1"""


async def test_a_flow_never_starts_a_day_before_its_first_day(
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = await new_company()
    key = fk()
    first = tomorrow() + timedelta(days=1)
    await seed(
        su, monkeypatch, a_flow(co["code"], key, start=first, same_day=True, trigger_at="09:00")
    )
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            flow = await FL.flow_by_key(tx, key)
        assert flow is not None and flow.ref
        assert FL.held_why(flow, tomorrow()) is not None and FL.held_why(flow, first) is None
        # the clock at tomorrow's build hour: the day before the first day is left
        await FL.clock(hub, FL.trigger_of(flow, tomorrow()) + timedelta(minutes=1))
        assert await su.fetchval(WORKS, key) == 0
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert (
                await FL.n8n_guard(tx, key, tomorrow(), FL.trigger_of(flow, tomorrow()))
                == "not_started"
            )
        # its first day starts as always
        await FL.clock(hub, FL.trigger_of(flow, first) + timedelta(minutes=1))
        assert await su.fetchval(WORKS, key) == 1
    finally:
        await all_off(su, key)


async def test_an_event_flow_is_never_started_by_the_clock_and_each_news_item_runs_once(
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    co = await new_company()
    reel, flash, plain = fk(), fk(), fk()
    await seed(
        su, monkeypatch,
        a_flow(co["code"], reel, recipe="breaking", story=True, trigger_at="09:00"),
        a_flow(co["code"], flash, recipe="breaking", stories=("12:00",), hours=("12:00",), trigger_at="09:00"),
        a_flow(co["code"], plain, trigger_at="09:00"),
    )  # fmt: skip
    item = {"id": "openai:gpt-6.2-astra", "vendor": "OpenAI", "title": "Introducing GPT-6.2 <b>Astra</b>",
            "url": "https://openai.com/index/introducing-gpt-6-2/", "image": "https://images.ctfassets.net/x.png",
            "summary": "A new frontier model."}  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            r_flow = await FL.flow_by_key(tx, reel)
        assert r_flow is not None and FL.on_event(r_flow)
        assert FL.held_why(r_flow, tomorrow()) == FL.EVENT_FA
        # the clock passes both event flows by, on any day (the plain one is made)
        await FL.clock(hub, FL.trigger_of(r_flow, tomorrow()) + timedelta(minutes=1))
        assert await su.fetchval(WORKS, reel) == 0 and await su.fetchval(WORKS, flash) == 0
        assert await su.fetchval(WORKS, plain) == 1
        # the watcher's call: one run per item and flow
        now = datetime.now(UTC)
        got = await EV.start_event(hub, reel, item, lead_min=100, now=now)
        assert got["new"] and got["order"] and got["work"]
        again = await EV.start_event(hub, reel, dict(item, title="the same item, seen again"))
        assert not again["new"] and again["why_fa"] == EV.MADE_FA and again["work"] == got["work"]
        assert await su.fetchval(WORKS, reel) == 1
        meta = await su.fetchval(
            "SELECT run_meta -> 'flow' FROM work.work WHERE ref = $1", got["work"])  # fmt: skip
        meta = meta if isinstance(meta, dict) else __import__("json").loads(meta)
        assert meta["event"]["id"] == "openai:gpt-6.2-astra" and meta["story"] is True
        assert "asap" not in meta and datetime.fromisoformat(meta["publish_at"]) >= now + timedelta(
            minutes=99
        )
        text = await su.fetchval(
            "SELECT text FROM owner.orders WHERE ref = $1", got["order"])  # fmt: skip
        assert "<b>" not in text and "GPT-6.2" in text and FL.NEVER_SILENT_FA in text
        # the flash story: out the moment its package is in
        f = await EV.start_event(hub, flash, item, now=now)
        fm = await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE ref = $1", f["work"])
        fm = fm if isinstance(fm, dict) else __import__("json").loads(fm)
        assert f["new"] and fm["asap"] is True and datetime.fromisoformat(fm["publish_at"]) == now
        # a plain flow and a flow switched off make nothing
        assert (await EV.start_event(hub, plain, dict(item, id="x:1")))["why_fa"] == EV.NOT_EVENT_FA
        await all_off(su, reel)
        off = await EV.start_event(hub, reel, dict(item, id="anthropic:fable-5.3"))
        assert not off["new"] and off["why_fa"] == EV.OFF_FA
        with pytest.raises(ApiError):
            await EV.start_event(hub, reel, dict(item, id="BAD ID"))
    finally:
        await all_off(su, reel, flash, plain)


def test_a_breaking_reel_waits_out_the_night() -> None:
    flow = a_flow("XX", "k", recipe="breaking")
    # 23:30 UTC = 03:00 Tehran: moved to 08:30 Tehran (05:00 UTC)
    night = datetime(2026, 11, 20, 23, 30, tzinfo=UTC)
    at = EV.publish_at(flow, night, 30)
    assert at == datetime(2026, 11, 21, 5, 0, tzinfo=UTC)
    day = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    assert EV.publish_at(flow, day, 100) == day + timedelta(minutes=100)


async def test_the_hub_makes_a_stories_flow_with_its_hours_and_word(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    from .test_w19_publish_time import connected

    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = fk()
    sch = {"hours": ["08:45"], "trigger_at": "05:00", "same_day": True, "start": tomorrow().isoformat(),
           "stories": ["08:45", "10:15", "11:40"]}  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            made = await FD.create_by_hub(
                tx, hub, key=key, account="pro.chart", kit="/home/studio/kits/p39-stories",
                title_fa="استوری‌های آزمایشی", kind="stories", schedule=sch, model=OPUS, effort="xhigh",
                usd_cap=60, budget_tokens=10_000_000, recipe="bjtech", story_word="لینک",
                cycle=("خبر", "آموزش"),
            )  # fmt: skip
        assert made.kind == "stories" and made.schedule.stories == ["08:45", "10:15", "11:40"]
        assert made.story_word == "لینک" and made.story_word_mode == "fixed"
        assert made.cycle == ["خبر", "آموزش"]
        async with hub.db.tx(await hub.companies.ids()) as tx:
            flow = await FL.flow_by_key(tx, key)
        assert (
            flow is not None and flow.stories == ("08:45", "10:15", "11:40") and flow.story is False
        )
        with pytest.raises(ApiError):  # kind stories without its hours
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await FD.create_by_hub(
                    tx, hub, key=fk(), account="pro.chart", kit="/home/studio/kits/p39-stories",
                    title_fa="بی ساعت", kind="stories", schedule=dict(sch, stories=[]), model=OPUS,
                    effort="xhigh", usd_cap=60, budget_tokens=10_000_000,
                )  # fmt: skip
    finally:
        await all_off(su, key)


def test_the_pages_flows_have_their_own_map() -> None:
    """The automations map: the page's reels on the LUMEN steps, its stories with their own texts, the
    breaking news starting at the watcher (never «n8n every day at …»)."""
    from hq_api.domain import flow_view as FV

    reel = a_flow("XX", "bj_reel", recipe="bjtech")
    stories = a_flow("XX", "bj_st", recipe="bjtech", stories=("08:45", "10:15"), hours=("08:45",))
    flash = a_flow("XX", "bj_flash", recipe="breaking", stories=("12:00",), hours=("12:00",))
    news = a_flow("XX", "bj_news", recipe="breaking", story=True)
    for f in (reel, stories, flash, news):
        g = FV.graph_of(f)
        assert g.nodes and g.edges
    keys = [s.key for s in FV.steps_of(reel)]
    assert keys[:3] == ["n8n", "order", "topic"] and "render" in keys and "cover" in keys
    st = FV.steps_of(stories)
    assert any("تلگرام" in s.title_fa for s in st) and not any("VIP" in s.title_fa for s in st)
    first = FV.steps_of(news)[0]
    assert first.title_fa == "دیده‌بان خبرهای فوری" and "هر روز" not in first.input_fa
    assert FV.steps_of(flash)[0].title_fa == "دیده‌بان خبرهای فوری"


FLASH_COMMENT = (
    "keyword: آسترا\nreply: این هم اطلاعیه‌ی رسمی\nreply: https://openai.com/index/introducing-gpt-6-2-astra-sol\n"
    "button: کانال تلگرام | https://t.me/behnamjalali_tech"
)


async def test_a_flash_story_goes_out_at_once_and_a_skipped_news_item_closes_unpublished(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The watcher's flash run: its one story is published the moment the package is in (no hour to
    wait for); a run whose session wrote only out/skip.txt (not real, not new) is closed, unpublished."""
    from .test_p17_runners import take
    from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
    from .test_w19_publish_time import connected
    from .test_w26_flows import a_pic

    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = fk()
    await seed(su, monkeypatch, a_flow(co["code"], key, account="pro.chart", recipe="breaking",
                                       stories=("12:00",), hours=("12:00",), trigger_at="09:00"))  # fmt: skip
    ws = await workshop(client, hub, owner_session, su)
    publish_sql = ("SELECT args FROM infra.server_jobs WHERE kind = 'publish'"
                   " AND args -> 'session' ->> 'order' = $1")  # fmt: skip

    async def deliver(event_id: str, sent: list[tuple[str, str, bytes]]) -> tuple[str, str]:
        got = await EV.start_event(hub, key, {"id": event_id, "vendor": "OpenAI", "title": "GPT-6.2 Astra",
                                              "url": "https://openai.com/index/introducing-gpt-6-2-astra-sol"})  # fmt: skip
        order, work_ref = got["order"], got["work"]
        wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1",
            work_ref,
        )
        await refuse_queued(su, str(wid))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "خبر فوری"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        files = []
        for name, ctype, data in sent:
            r = await send_file(client, ws, job["id"], name, ctype, data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        await refuse_queued(su, str(wid))
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "تمام.",
                  "data": {"session_id": f"cs-{event_id}", "result_fa": "تمام.", "files": files}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        return order, work_ref

    try:
        order, _ = await deliver("openai:gpt-6.2-astra", [
            ("story_1.png", "image/png", a_pic(1)), ("comment.txt", "text/plain", FLASH_COMMENT.encode()),
            ("topic.txt", "text/plain", "خبر فوری: OpenAI GPT-6.2 Astra".encode())])  # fmt: skip
        jobs = [j["args"] if isinstance(j["args"], dict) else __import__("json").loads(j["args"])
                for j in await su.fetch(publish_sql, order)]  # fmt: skip
        assert len(jobs) == 1 and jobs[0]["kind"] == "story"
        assert not jobs[0]["meta"].get("scheduled_at")  # out at once
        # a news item the session found not real: closed, nothing published
        order2, work2 = await deliver(
            "x:not-real", [("skip.txt", "text/plain", "فقط یک مقاله بود".encode())]
        )
        assert await su.fetch(publish_sql, order2) == []
        meta = await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE ref = $1", work2)
        meta = meta if isinstance(meta, dict) else __import__("json").loads(meta)
        assert meta["skipped"] == "فقط یک مقاله بود" and meta.get("sent")
        assert await su.fetchval(
            "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", order2)  # fmt: skip
        assert await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'flow.skip' AND target_ref = $1", order2) == 1  # fmt: skip
    finally:
        await all_off(su, key)


def test_a_long_video_of_a_page_without_a_site_never_names_dotcoins_channel() -> None:
    """The long-video order was DotCoin's text («یوتیوب دات‌کوین», «article.md», «dotcoin.me»); another page's
    asks for the video alone, 8-15 minutes, on its own channel."""
    from datetime import date as d

    flow = a_flow(
        "XX",
        "bj_long",
        account="behnamjalali.tech",
        kind="video",
        kit="/home/studio/kits/bjtech-longform",
    )
    at = datetime(2026, 11, 19, 16, 30, tzinfo=UTC)
    text = FL.brief_of(flow, d(2026, 11, 19), at)
    assert "دات‌کوین" not in text and "dotcoin.me" not in text and "article.md" not in text
    assert "۸ تا ۱۵ دقیقه" in text and "subtitles.fa.srt" in text and FL.NEVER_SILENT_FA in text
    dot = a_flow("XX", "dc_long", account="dotcoin.me", kind="video")
    assert "یوتیوب دات‌کوین" in FL.brief_of(dot, d(2026, 11, 19), at)


def test_a_flash_storys_order_names_the_reply_words_already_taken() -> None:
    flow = a_flow("XX", "bj_flash", recipe="breaking", stories=("12:00",), hours=("12:00",))
    at = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    item = {"id": "x:y", "vendor": "OpenAI", "title": "t"}
    text = EV.event_brief(flow, item, at, [], ["آسترا", "مدل"])
    assert "«آسترا»" in text and "باید تازه باشد" in text and "story_1.jpg" in text
    assert "باید تازه باشد" not in EV.event_brief(flow, item, at, [], [])
