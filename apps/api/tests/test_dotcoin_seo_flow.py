"""⟨2026-11-18⟩ A site's SEO day (flow kind `article`): DotCoin.me's daily SEO automation.

The owner: «اتوماسیون سئو سایت دات کوین رو راه اندازی بکن که یه اتوماسیون فوق متخصص باید باشه که هر
روز بیشتر دیده شدن و به صفحه اول گوگل اومدن تلاش بکنه». A row of automations.flows made by the hub
(create_by_hub, kind `article`, channel `web`); its day's order asks for ONE package (package.zip
with the day's new page and fixes, summary.fa.txt, on Saturdays week.fa.txt); the package is never
an IG-Hub post: the run is marked `site: queued` for the hub's host publisher (seo.py --due), the
session closes, nobody is notified (the owner hears of the SEO in the weekly summary only). And the
clock never makes a day before a flow's start (ipoxxo_reels_3 started the day it was made).
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from hq_api.domain import flow_defs as FD
from hq_api.domain import flow_view as FV
from hq_api.domain import flows as FL
from hq_api.hub import Hub

from .conftest import idem
from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
from .test_w19_publish_time import connected

TZ = ZoneInfo(FL.TEHRAN)
OPUS = "claude-opus-5-5"


def tomorrow() -> date:
    return datetime.now(TZ).date() + timedelta(days=1)


def seo_flow(**over: Any) -> FL.Flow:
    base = FL.Flow(
        key="dotcoin_seo_t", company="IG", account="dotcoin.me", title_fa="سئوی روزانه‌ی آزمایشی",
        kit="/home/studio/kits/dotcoin-seo", start=date(2026, 11, 20), hours=("08:00",),
        story=False, budget_tokens=10_000_000, trigger_at="22:00", model=OPUS, effort="xhigh",
        recipe="dotcoin_seo", channel="web", kind="article",
    )  # fmt: skip
    return replace(base, **over)


def a_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"base": "abc", "files": []}))
    return buf.getvalue()


def test_a_day_before_the_start_is_never_made() -> None:
    """The clock looks at yesterday and today (or today and tomorrow): a flow whose first day is
    tomorrow is held today, with the reason in Persian; from its first day on it runs."""
    f = seo_flow(start=date(2026, 11, 20))
    held = FL.held_why(f, date(2026, 11, 19))
    assert held is not None and held.startswith("این اتوماسیون از ")
    assert FL.held_why(f, date(2026, 11, 20)) is None
    assert FL.held_why(f, date(2026, 11, 21)) is None


def test_the_seo_brief_asks_for_one_package_never_a_reel() -> None:
    f = seo_flow(note_fa="یادداشت سئو")
    at = datetime(2026, 11, 20, 4, 30, tzinfo=UTC)
    text = FL.brief_of(f, date(2026, 11, 20), at)  # a Friday
    assert "/home/studio/kits/dotcoin-seo/README.md" in text and "order.ask" in text
    assert FL.ARTICLE_PACKAGE in text and FL.ARTICLE_SUMMARY in text and "2026-11-20" in text
    assert "video.mp4" not in text and "ریلز" not in text and "سفید" in text
    assert FL.ARTICLE_WEEK not in text and text.endswith("یادداشت سئو")
    saturday = FL.brief_of(f, date(2026, 11, 21), at + timedelta(days=1))
    assert FL.ARTICLE_WEEK in saturday


def test_the_seo_map_has_the_hosts_steps() -> None:
    steps = [s.key for s in FV.steps_of(seo_flow())]
    assert steps[:2] == ["n8n", "order"]
    assert {"gsc", "topic", "write", "fixes", "direction", "package", "site", "index"} <= set(steps)
    g = FV.graph_of(seo_flow())
    lanes = {n.key: n.lane for n in g.nodes}
    assert lanes["gsc"] == lanes["site"] == lanes["index"] == "hub" and lanes["write"] == "workshop"
    assert FD.kind_of_flow(seo_flow()) == "article"


async def test_the_hub_makes_an_seo_flow_and_its_day_goes_to_the_site_not_to_ig_hub(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = f"seo{uuid.uuid4().hex[:8]}"
    day = tomorrow()
    sch = {"hours": ["08:00"], "trigger_at": "22:00", "same_day": False, "days": list(range(7)),
           "start": day.isoformat(), "stories": [], "best_week": False}  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            made = await FD.create_by_hub(
                tx, hub, key=key, account="pro.chart", kit="/home/studio/kits/dotcoin-seo",
                title_fa="سئوی روزانه‌ی آزمایشی", kind="article", schedule=sch, model=OPUS,
                effort="xhigh", usd_cap=100, budget_tokens=10_000_000, recipe="dotcoin_seo",
                channel="web",
            )  # fmt: skip
        assert made.kind == "article" and made.channel == "web" and made.state == "on"
        async with hub.db.tx(await hub.companies.ids()) as tx:
            flow = await FL.flow_by_key(tx, key)
            assert flow is not None and flow.kind == "article"
            # the clock: nothing before its start, its first day once its build hour has come
            now = FL.trigger_of(flow, day) + timedelta(minutes=1)
            due = [(f.key, d) for f, d in await FL.due_days(tx, now)]
            assert (key, day) in due and (key, day - timedelta(days=1)) not in due
            early = [(f.key, d) for f, d in await FL.due_days(tx, now - timedelta(days=1))]
            assert all(k != key for k, _ in early)
            # a planned SEO day is an article in the publish centre, never a reel
            from hq_api.domain import publications as PB

            planned = [p for p in await PB.planned_today(tx, day) if p.title_fa == flow.title_fa]
            assert planned and planned[0].kind == "article"
        r = await client.post(
            f"/api/v1/flows/{key}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
        )
        assert r.status_code == 201, r.text
        got = r.json()
        order, work_ref = got["order"], got["work"]
        w = await su.fetchrow(
            "SELECT id, run_meta -> 'flow' AS flow FROM work.work WHERE ref = $1", work_ref
        )
        meta = w["flow"] if isinstance(w["flow"], dict) else json.loads(w["flow"])
        assert meta["kind"] == "article" and meta["day"] == day.isoformat()
        brief = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", order)
        assert FL.ARTICLE_PACKAGE in brief and "video.mp4" not in brief

        # the session's turn leaves the package (the zip last): queued for the site, no IG job
        ws = await workshop(client, hub, owner_session, su)
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id"
            " WHERE w.ref = $1",
            work_ref,
        )
        await refuse_queued(su, str(w["id"]))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "سئوی امروز"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        sent = (
            ("report.md", "text/markdown", "# گزارش روز".encode()),
            ("topic.txt", "text/plain", "کیف پول سخت‌افزاری چیست".encode()),
            ("summary.fa.txt", "text/plain", "صفحه‌ی تازه و ۴ بهینه‌سازی".encode()),
            ("week.fa.txt", "text/plain", "- نمایش هفته ۱۲۰\n- ۳ صفحه‌ی تازه\n".encode()),
            ("package.zip", "application/zip", a_zip()),
        )  # fmt: skip
        files = []
        for name, ctype, data in sent:
            r = await send_file(client, ws, job["id"], name, ctype, data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        await refuse_queued(su, str(w["id"]))
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "تمام شد.",
                  "data": {"session_id": "cs-seo-1", "result_fa": "آماده.", "files": files}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        assert not await su.fetchval(
            "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish'"
            " AND args -> 'session' ->> 'order' = $1",
            order,
        )
        raw = await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE id = $1", w["id"])
        meta = raw if isinstance(raw, dict) else json.loads(raw)
        assert meta["site"] == "queued" and meta.get("sent")
        assert meta["summary_fa"].startswith("صفحه‌ی تازه") and meta["topic_fa"].startswith("کیف")
        assert meta["week_fa"] == ["نمایش هفته ۱۲۰", "۳ صفحه‌ی تازه"]
        assert await su.fetchval(
            "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", order
        )
        assert not await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE source_code = 'flow' AND link_ref = $1",
            order,
        )
        n = await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'flow.publish' AND target_ref = $1",
            order,
        )
        assert n == 1
        # the day is made: the clock and the late alert see it; the week's lines reach the summary
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await FL.day_made(tx, flow, day)
            assert await FL.published_day(tx, flow, day) is None  # (no IG post is ever its own)
            lines = await FL.seo_week_lines(tx, datetime.now(UTC))
        i = lines.index(f"**{flow.title_fa}**")
        assert lines[i + 1 : i + 3] == ["- نمایش هفته ۱۲۰", "- ۳ صفحه‌ی تازه"]
        assert await FL.after_delivered(hub, w["id"]) == "sent"
    finally:
        await su.execute("UPDATE automations.flows SET state = 'off' WHERE key = $1", key)


def test_create_by_hub_takes_the_article_kind() -> None:
    assert "article" in FD.KINDS and "article" in FL.OFF_IG_KINDS and "video" in FL.OFF_IG_KINDS
    assert Decimal("100") <= FD.USD_MAX


async def test_a_long_video_over_the_file_limit_left_in_out_still_makes_its_day(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-18⟩ W-000636: a 10-minute 1080p60 video (710 MB) is over the hub's file limit, so
    the runner leaves it in out/ (`files_skipped`) and only the texts arrive. The day is queued for
    YouTube all the same (the host uploader reads out/ itself), and the session closes."""
    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = f"lv{uuid.uuid4().hex[:8]}"
    day = tomorrow()
    sch = {"hours": ["20:00"], "trigger_at": "01:30", "same_day": True, "days": list(range(7)),
           "start": day.isoformat(), "stories": [], "best_week": False}  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await FD.create_by_hub(
                tx, hub, key=key, account="pro.chart", kit="/home/studio/kits/bjtech-longform",
                title_fa="ویدیوی بلند آزمایشی", kind="video", schedule=sch, model=OPUS,
                effort="xhigh", usd_cap=150, budget_tokens=10_000_000,
            )  # fmt: skip
        r = await client.post(
            f"/api/v1/flows/{key}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
        )
        assert r.status_code == 201, r.text
        order, work_ref = r.json()["order"], r.json()["work"]
        w = await su.fetchrow("SELECT id FROM work.work WHERE ref = $1", work_ref)
        ws = await workshop(client, hub, owner_session, su)
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id"
            " WHERE w.ref = $1",
            work_ref,
        )
        await refuse_queued(su, str(w["id"]))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "ویدیوی بلند امروز"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        files = []
        for name, data in (("topic.txt", "حرکت ۳۷".encode()), ("caption.txt", "توضیحات".encode())):
            r = await send_file(client, ws, job["id"], name, "text/plain", data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        await refuse_queued(su, str(w["id"]))
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "تمام شد.",
                  "data": {"session_id": "cs-lv-1", "result_fa": "آماده.", "files": files,
                           "files_skipped": [{"name": "video.mp4", "why": "بزرگ‌تر از سقف"}]}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        raw = await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE id = $1", w["id"])
        meta = raw if isinstance(raw, dict) else json.loads(raw)
        assert meta.get("youtube") == "queued" and meta.get("sent")
        assert meta.get("topic_fa") == "حرکت ۳۷"
        # ⟨2026-11-18⟩ the page's long videos are in its «never twice» list too
        async with hub.db.tx(await hub.companies.ids()) as tx:
            lv = await FL.flow_by_key(tx, key)
            assert lv is not None and "حرکت ۳۷" in await FL.published_topics(tx, lv)
        assert await su.fetchval(
            "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", order
        )
        # an output with no turn behind it is never taken for one
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert not await FL._video_left_in_out(tx, {"produced_with": {}})
            assert not await FL._video_left_in_out(tx, {"produced_with": {"job": "x"}})
    finally:
        await su.execute("UPDATE automations.flows SET state = 'off' WHERE key = $1", key)


async def test_a_long_video_left_in_out_a_turn_after_its_caption_still_makes_its_day(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    no_model: list[Any],  # noqa: F811
) -> None:
    """⟨2026-11-21⟩ W-000752: the caption and the topic came in one turn (00:33Z), the video (745 MB,
    over the file limit) only in the next (00:45Z), which left nothing to deliver. The day stayed
    open and never went to YouTube. Any finished turn of the work that left `video.mp4` in out/
    completes it, and such a turn checks the day even with no file of its own."""
    ig, co = await new_company(), await new_company()
    await connected(client, hub, owner_session, ig, co["code"])
    key = f"lw{uuid.uuid4().hex[:8]}"
    day = tomorrow()
    sch = {"hours": ["20:00"], "trigger_at": "01:30", "same_day": True, "days": list(range(7)),
           "start": day.isoformat(), "stories": [], "best_week": False}  # fmt: skip
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await FD.create_by_hub(
                tx, hub, key=key, account="pro.chart", kit="/home/studio/kits/bjtech-longform",
                title_fa="ویدیوی بلند آزمایشی ۲", kind="video", schedule=sch, model=OPUS,
                effort="xhigh", usd_cap=150, budget_tokens=10_000_000,
            )  # fmt: skip
        r = await client.post(
            f"/api/v1/flows/{key}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
        )
        assert r.status_code == 201, r.text
        work_ref = r.json()["work"]
        w = await su.fetchrow("SELECT id FROM work.work WHERE ref = $1", work_ref)
        ws = await workshop(client, hub, owner_session, su)
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id"
            " WHERE w.ref = $1",
            work_ref,
        )

        async def meta() -> dict[str, Any]:
            raw = await su.fetchval(
                "SELECT run_meta -> 'flow' FROM work.work WHERE id = $1", w["id"]
            )
            return raw if isinstance(raw, dict) else json.loads(raw)

        # turn 1: the texts, no video yet
        await refuse_queued(su, str(w["id"]))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "ویدیوی بلند امروز"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        files = []
        for name, data in (("topic.txt", "چاه کولا".encode()), ("caption.txt", "توضیحات".encode())):
            r = await send_file(client, ws, job["id"], name, "text/plain", data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "متن‌ها آماده است.",
                  "data": {"session_id": "cs-lw-1", "result_fa": "متن‌ها آماده.", "files": files}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        assert not (await meta()).get("sent")
        # turn 2: only the video, left in out/ (nothing to deliver)
        await refuse_queued(su, str(w["id"]))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "رندر ویدیو"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "ویدیو آماده است.",
                  "data": {"session_id": "cs-lw-1", "result_fa": "ویدیو در out/ است.", "files": [],
                           "files_skipped": [{"name": "video.mp4", "why": "بزرگ‌تر از سقف"}]}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        m = await meta()
        assert m.get("youtube") == "queued" and m.get("sent") and m.get("topic_fa") == "چاه کولا"
    finally:
        await su.execute("UPDATE automations.flows SET state = 'off' WHERE key = $1", key)
