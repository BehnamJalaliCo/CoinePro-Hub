"""⟨2026-11-13⟩ A working group's daily run, started by n8n (domain/flows.py).

The owner: «اون دکمه انتشارم قرار نیست دیگه من بزنم و قراره اتوماتیک و اتوماسیونی باشه توسط
n8n»; the hours: a week at 09:30 Tehran, a week at 14:00, a week at 19:30, the fourth at the hour
with the most views; and «گزارش کوتاه به من رو توی آپ توسط نوتیف بده».
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import flows as FL
from hq_api.hub import Hub

from .conftest import idem
from .test_p13a_media import mp4
from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
from .test_w17_session_publish import a_png
from .test_w19_publish_time import answer, connected

START = date(2026, 11, 14)
COMMENT = (
    "keyword: بازپخش\nmatch: any\nreply: لینک امروز\nlink: https://pro-chart.com/next/\n"
    "button: ورود به پرو چارت\npublic: برات دایرکت شد ✅"
)


def a_flow(company: str, key: str = "t") -> FL.Flow:
    return FL.Flow(key=key, company=company, account="pro.chart", title_fa="ریلز آزمایشی",
                   kit="/kit", start=START, hours=("09:30", "14:00", "19:30", None))  # fmt: skip


async def test_the_four_weeks_have_their_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    f = a_flow("PC")
    tz = ZoneInfo(FL.TEHRAN)
    for offset, hm in ((0, "09:30"), (6, "09:30"), (7, "14:00"), (14, "19:30"), (28, "09:30")):
        at, _ = await FL.slot_of(None, f, START + timedelta(days=offset), None)  # type: ignore[arg-type]
        assert at.astimezone(tz).strftime("%H:%M") == hm, offset
    # the fourth week: the hour the account did best at, else the first week's
    from hq_api.domain import best_hour as BH

    async def best(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(enough=True, hour="21:00")

    monkeypatch.setattr(BH, "best", best)
    at, why = await FL.slot_of(None, f, START + timedelta(days=21), None)  # type: ignore[arg-type]
    assert at.astimezone(tz).strftime("%H:%M") == "21:00" and "پربازدید" in why

    async def thin(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(enough=False, hour=None)

    monkeypatch.setattr(BH, "best", thin)
    at, _ = await FL.slot_of(None, f, START + timedelta(days=22), None)  # type: ignore[arg-type]
    assert at.astimezone(tz).strftime("%H:%M") == "09:30"
    text = FL.brief_of(f, START, at)
    assert "/kit/README.md" in text and "order.ask" in text and "story.mp4" in text
    assert FL.NEVER_SILENT_FA in text  # ⟨2026-11-18⟩ never a silent reel, whatever the voice says


def test_a_rotating_flow_names_the_days_kind_in_its_brief() -> None:
    """⟨2026-11-14⟩ TradeYar's 12:00 reel turns (education, an exchange's campaign, the news and
    the market): the day's kind goes in the order's text; a flow without a round says nothing."""
    from dataclasses import replace

    flow = replace(a_flow("TY"), cycle=("آموزش", "کمپین صرافی", "خبر و بازار"))
    at = datetime(2026, 11, 15, 8, 30, tzinfo=UTC)
    kinds = [FL.kind_of(flow, START + timedelta(days=d)) for d in range(4)]
    assert kinds == ["آموزش", "کمپین صرافی", "خبر و بازار", "آموزش"]
    assert "«کمپین صرافی»" in FL.brief_of(flow, START + timedelta(days=1), at)
    assert "نوع ریلز امروز" not in FL.brief_of(a_flow("PC"), START, at)
    assert FL.kind_of(flow, START - timedelta(days=1)) == ""  # before its first day: no kind
    real = FL.FLOWS["zaribsad_noon"]
    assert real.company == "TY" and real.trigger_at == "07:00" and real.hours[0] == "12:00"
    assert FL.FLOWS["zaribsad_coin"].trigger_at == "14:00" and FL.FLOWS["zaribsad_coin"].n8n


async def test_n8n_starts_the_day_and_the_package_goes_out_at_its_hour(
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
    ig_rn = await connected(client, hub, owner_session, ig, pc["code"])
    fk = f"t{uuid.uuid4().hex[:8]}"  # (the test DB keeps earlier runs' days)
    monkeypatch.setattr(FL, "FLOWS", {fk: a_flow(pc["code"], fk)})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)

    # n8n's call must be signed
    r = await client.post(f"/internal/v1/flows/{fk}/run", json={"day": day.isoformat()})
    assert r.status_code == 401, r.text
    # the day's order: once per key
    key = idem()
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **key}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    got = r.json()
    at = datetime.fromisoformat(got["publish_at"])
    assert at.astimezone(ZoneInfo(FL.TEHRAN)).strftime("%H:%M") in ("09:30", "14:00", "19:30")
    again = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **key}, json={"day": day.isoformat()}
    )
    assert again.json()["order"] == got["order"]
    # another key, the same day: still the one order
    third = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert third.json()["order"] == got["order"] and third.json()["work"] == got["work"]
    order, work_ref = got["order"], got["work"]
    w = await su.fetchrow(
        "SELECT id, run_meta -> 'flow' AS flow FROM work.work WHERE ref = $1", work_ref
    )
    assert w["flow"] is not None
    assert await su.fetchval("SELECT pace FROM owner.orders WHERE ref = $1", order) == "auto"

    # the day's turn leaves the whole package: it goes out by itself, at its hour
    ws = await workshop(client, hub, owner_session, su)
    holder = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1",
        work_ref,
    )
    # a turn the API refused for a moment: the day's own session goes on (a direct turn), never
    # a classic run that has no workshop and gives the work up
    await refuse_queued(su, str(w["id"]))
    r = await run_ask(client, holder, {"work": work_ref, "brief": "بسته‌ی امروز"})
    assert r.status_code == 201, r.text
    job = await take(client, ws)
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 1, "summary_fa": "نشست Claude با کد خروج 1 تمام شد."},
        headers=ws["h"],
    )
    assert r.status_code == 200, r.text
    assert (
        await su.fetchval(
            "SELECT reason FROM agents.runs WHERE work_id = $1 ORDER BY created_at DESC LIMIT 1",
            w["id"],
        )
        == f"continue:{order}"
    )
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) != "failed"
    await refuse_queued(su, str(w["id"]))
    r = await run_ask(client, holder, {"work": work_ref, "brief": "بسته‌ی امروز"})
    assert r.status_code == 201, r.text
    job = await take(client, ws)
    # F-0020: the package comes over two turns (the cover and the texts, then the video and the
    # story): nothing goes out before the whole package, then it goes out from both outputs;
    # F-0023 (2026-11-14): the first of them stopped unfinished (exit 1) after writing its files
    # ⟨2026-11-19⟩ the cover comes last here: a reel never goes out without one (P-000122), the
    # session is woken once to make it, and the day goes out when it is in
    turns = (
        (("caption.txt", "text/plain", "کپشن #پرو_چارت".encode()),
         ("comment.txt", "text/plain", COMMENT.encode()),
         ("topic.txt", "text/plain", f"بازپخش {fk}".encode())),
        (("video.mp4", "video/mp4", mp4(2)), ("story.mp4", "video/mp4", mp4(1))),
        (("cover.png", "image/png", a_png(1)),),
    )  # fmt: skip
    for n, sent in enumerate(turns):
        if n:
            await refuse_queued(su, str(w["id"]))
            r = await run_ask(client, holder, {"work": work_ref, "brief": "ویدیو"})
            assert r.status_code == 201, r.text
            job = await take(client, ws)
        files = []
        for name, ctype, data in sent:
            r = await send_file(client, ws, job["id"], name, ctype, data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        await refuse_queued(su, str(w["id"]))
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0 if n else 1, "summary_fa": "تمام شد.",
                  "data": {"session_id": "cs-flow-1", "result_fa": "آماده.", "files": files}},
            headers=ws["h"],
        )  # fmt: skip
        assert r.status_code == 200, r.text
        if n < 2:
            assert not await su.fetchval(
                "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish'"
                " AND args -> 'session' ->> 'order' = $1",
                order,
            )
        if n == 1:  # the video and the texts are in, the cover is not: asked for, once
            asked = await su.fetchval(
                "SELECT run_meta -> 'flow' ->> 'cover_asked' FROM work.work WHERE id = $1", w["id"]
            )
            assert asked
            steps = await su.fetchval(
                "SELECT steps::text FROM owner.order_reports WHERE ref = $1", order
            )
            assert "بی کاور منتشر نمیشود" in steps
            assert await su.fetchval(
                "SELECT count(*) FROM agents.runs WHERE work_id = $1 AND state = 'queued'", w["id"]
            ) == 1  # fmt: skip
    jobs = await su.fetch(
        "SELECT id, args FROM infra.server_jobs WHERE kind = 'publish'"
        " AND args -> 'session' ->> 'order' = $1 ORDER BY created_at",
        order,
    )
    kinds = {}
    for j in jobs:
        a = j["args"] if isinstance(j["args"], dict) else __import__("json").loads(j["args"])
        kinds[a["kind"]] = a
    assert set(kinds) == {"reel", "story"}
    reel, story = kinds["reel"], kinds["story"]
    assert reel["meta"]["scheduled_at"] == at.isoformat() == story["meta"]["scheduled_at"]
    assert reel["files"][0]["name"] == "video.mp4" and story["files"][0]["name"] == "story.mp4"
    assert reel["meta"]["comment"]["match"] == "any" and reel["caption"].startswith("کپشن")
    assert len(reel["meta"]["comment"]["public_replies"]) == 10
    assert "comment" not in story["meta"]
    # the owner hears it once; the session is closed (nothing goes on spending)
    said = await su.fetch(
        "SELECT title_fa FROM notify.notifications WHERE source_code = 'flow' AND link_ref = $1",
        order,
    )
    assert [x["title_fa"] for x in said] == ["ریلز آزمایشی آماده شد"]
    assert await su.fetchval(
        "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", order
    )
    # a second turn's files never send it twice
    from hq_api.domain import flows as FL2

    assert await FL2.after_delivered(hub, w["id"]) == "sent"
    # F-0022: closing the session may cancel the day's root; a day whose package went out is made
    await su.execute(
        "UPDATE work.work SET status = 'cancelled', closed_at = now()"
        " WHERE id = $1 AND status IN ('queued', 'in_progress', 'waiting')",
        w["id"],
    )
    fourth = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert fourth.json()["order"] == order and fourth.json()["work"] == work_ref, fourth.text

    # IG-Hub published the reel: the owner hears it with its link
    taken = await take(client, ig_rn)
    await answer(client, ig_rn, taken["id"], {"external_id": "17866260483693371",
                                               "url": "https://www.instagram.com/reel/x/"})  # fmt: skip
    if taken["args"]["kind"] == "reel":
        out = await su.fetchval(
            "SELECT body_fa FROM notify.notifications WHERE source_code = 'flow'"
            " AND title_fa = 'ریلز آزمایشی منتشر شد' AND link_ref = $1",
            order,
        )
        assert out is not None and "کامنت هوشمند روشن است" in out
    assert datetime.now(UTC) < at


async def test_a_day_stops_at_its_cap_and_builds_on_the_highest_effort(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The F-0018 usage audit, P1 and P4 (the owner's word): «max» only where the video is made,
    «xhigh» for the rest. ⟨1.39⟩ the owner, 2026-11-17: cost never holds a flow: a day past its cap
    is marked once and goes on; nobody is notified."""
    from hq_api.domain import direct as DR

    pc = await new_company()
    fk = f"t{uuid.uuid4().hex[:8]}"  # (the test DB keeps earlier runs' days)
    monkeypatch.setattr(FL, "FLOWS", {fk: a_flow(pc["code"], fk)})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=3)
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    order, work_ref = r.json()["order"], r.json()["work"]
    w = await su.fetchrow("SELECT id, company_id FROM work.work WHERE ref = $1", work_ref)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await DR.effort_of(tx, {"id": w["id"]}) == "max"
        assert await DR.effort_of(tx, {"id": uuid.uuid4()}) == "xhigh"  # any other session
        assert await FL.over_cap(tx, w["id"]) is False
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, work_ref,
               task_class, priority, caller, provider, model, cost_usd, equiv_cost_usd, status)
           VALUES (gen_random_uuid(), now(), now(), $1, 'X', $2, 'server_claude', 3,
                   'company_runner', 'anthropic', 'claude-opus-5-5', 0, 10.5, 'ok')""",
        w["company_id"],
        work_ref,
    )
    for _ in range(2):
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await FL.over_cap(tx, w["id"]) is False
    meta = await su.fetchval("SELECT run_meta -> 'flow' ->> 'capped' FROM work.work WHERE id = $1",
                             w["id"])  # fmt: skip
    assert meta == "10.50"
    said = await su.fetch(
        "SELECT title_fa FROM notify.notifications WHERE source_code = 'flow' AND link_ref = $1",
        order,
    )
    assert said == []
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'flow.capped' AND target_ref = $1",
        work_ref,
    ) == 1  # fmt: skip


async def test_a_flow_runs_its_turns_on_its_own_model(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-15⟩ the owner: «مدل فیبل … رو هم یکبار امتحان کنیم برای ساخت ویدیو ریلز» (Fable 5.2): a flow
    that names a model runs its workshop turns on it (only a model of the workshop's list); every
    other flow keeps the workshop's own (Opus 5.5). The owner's choice for @zaribsad: «از فردا»: a
    model with a first day leaves the days before it on the workshop's own. ⟨2026-11-20⟩ the owner:
    «نباید مدلی از فیبل استفاده بکنه»: Fable left the workshop's list, so a flow that still names it
    runs on the workshop's own model whatever its first day."""
    from dataclasses import replace

    from hq_api.domain import hands as HANDS

    co = await new_company()
    ws = await workshop(client, hub, owner_session, su)
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)
    fable = "claude-fable-5-2"
    # ⟨2026-11-17⟩ the owner: every automation on Opus 5.5 at extra-high effort
    for key, f in FL.FLOWS.items():
        assert (f.model, f.effort, f.model_from) == ("claude-opus-5-5", "xhigh", None), key
        assert FL.model_on(f, date(2026, 11, 18)) == "claude-opus-5-5"
    for model, since, want in (
        (fable, None, HANDS.MODEL),
        ("", None, HANDS.MODEL),
        (fable, day + timedelta(days=1), HANDS.MODEL),
        (fable, day, HANDS.MODEL),
        ("claude-opus-5-5", day, "claude-opus-5-5"),
    ):
        fk = f"m{uuid.uuid4().hex[:8]}"
        flow = replace(a_flow(co["code"], fk), model=model, model_from=since)
        monkeypatch.setattr(FL, "FLOWS", {fk: flow})
        r = await client.post(
            f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
        )
        assert r.status_code == 201, r.text
        work_ref = r.json()["work"]
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id "
            "WHERE w.ref = $1",
            work_ref,
        )
        wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
        await refuse_queued(su, str(wid))
        r = await run_ask(client, holder, {"work": work_ref, "brief": "بسته‌ی امروز"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        assert job["args"]["model"] == want, job["args"]
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={"exit_code": 0, "summary_fa": "تمام."},
            headers=ws["h"],
        )
        assert r.status_code == 200, r.text


async def test_the_second_reel_of_a_page_never_shares_the_first_ones_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-15⟩ The owner: «پرو چارت رو روزی دو تا بکنیم»: the second flow of the page takes the
    other tried hours; on the best-hour week, the tried hour farthest from the first reel's."""
    from hq_api.domain import best_hour as BH

    async def best(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(enough=True, hour="19:30")

    monkeypatch.setattr(BH, "best", best)
    one, two = FL.FLOWS["prochart_reels"], FL.FLOWS["prochart_reels_2"]
    assert two.pair == one.key and two.account == one.account and two.kit == one.kit
    tz = ZoneInfo(FL.TEHRAN)
    for offset in range(56):
        day = one.start + timedelta(days=offset)
        a, _ = await FL.slot_of(None, one, day, None)  # type: ignore[arg-type]
        b, why = await FL.slot_of(None, two, day, None)  # type: ignore[arg-type]
        assert a.astimezone(tz).strftime("%H:%M") != b.astimezone(tz).strftime("%H:%M"), offset
        if FL.week_of(one, day) == 3:
            assert b.astimezone(tz).strftime("%H:%M") == "09:30" and "دور" in why


def test_a_story_dm_carries_up_to_three_buttons() -> None:
    from hq_api.domain import session_publish as SPB

    got = SPB.parse_comment(STORIES_COMMENT)
    assert got is not None and got["keywords"] == ["الماس"]
    assert [b["title"] for b in got["buttons"]] == ["ورود رایگان VIP", "ثبت‌نام LBank", "راهنما"]
    body = SPB.rule_body("story_reply", got, "zaribsad", [], "k")
    assert body["match"] == "contains" and len(body["buttons"]) == 3
    assert body["buttons"][0]["url"].startswith("https://trade-future.ir/go/vip")
    # a fourth, or one that is no https link, is left out
    more = STORIES_COMMENT + "\nbutton: چهارم | https://x.test/4\nbutton: بد | http://x.test"
    assert len(SPB.parse_comment(more)["buttons"]) == 3  # type: ignore[index]


def a_pic(i: int) -> bytes:
    """A picture of its own for each of seven (a_png's colour tops out after four)."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (20 * i, 90, 140)).save(buf, format="PNG")
    return buf.getvalue()


STORIES_COMMENT = (
    "keyword: الماس\nreply: سلام 👋 کانال VIP تریدیار رایگان است\nreply: 1️⃣ با لینک ما حساب بساز\n"
    "button: ورود رایگان VIP | https://trade-future.ir/go/vip?src=ig&goal=V&pl=story-t\n"
    "button: ثبت‌نام LBank | https://trade-future.ir/go/lbank?src=ig&goal=R&pl=story-t\n"
    "button: راهنما | https://trade-future.ir/guides/tradeyar-free-vip"
)


async def test_the_days_stories_go_out_each_at_its_hour_with_the_days_reply_rule(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-15⟩ The owner: «اتوماسیون استوری ضریب صد روزانه (هفت عدد) … جواب‌های دایرکت استوری
    طوری باشه که کاربر رو ترغیب بکنه برای ورود به کانال سیگنال vip»."""
    from dataclasses import replace

    from hq_api.domain import session_publish as SPB

    ig, ty = await new_company(), await new_company()
    ig_rn = await connected(client, hub, owner_session, ig, ty["code"])
    fk = f"s{uuid.uuid4().hex[:8]}"
    hours = ("08:30", "10:30", "13:30", "15:30", "17:30", "20:30", "22:30")
    flow = replace(a_flow(ty["code"], fk), story=False, stories=hours, hours=("08:30",))
    monkeypatch.setattr(FL, "FLOWS", {fk: flow})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    got = r.json()
    order, work_ref = got["order"], got["work"]
    assert datetime.fromisoformat(got["publish_at"]) == FL.story_times(flow, day)[0]
    brief = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", order)
    assert "story_7.jpg" in brief and "کلمه‌ی امروز باید تازه باشد" in brief
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    holder = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.ref = $1",
        work_ref,
    )
    ws = await workshop(client, hub, owner_session, su)
    await refuse_queued(su, str(wid))
    r = await run_ask(client, holder, {"work": work_ref, "brief": "استوری‌های امروز"})
    assert r.status_code == 201, r.text
    job = await take(client, ws)
    sent = [(f"story_{i}.png", "image/png", a_pic(i)) for i in range(1, 7)]  # one is missing
    sent += [("comment.txt", "text/plain", STORIES_COMMENT.encode()),
             ("topic.txt", "text/plain", "کارنامه‌ی هفته".encode())]  # fmt: skip
    files = []
    for name, ctype, data in sent:
        r = await send_file(client, ws, job["id"], name, ctype, data)
        assert r.status_code == 201, r.text
        files.append(r.json()["id"])
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "شش تا.",
              "data": {"session_id": "cs-st-1", "result_fa": "شش.", "files": files}},
        headers=ws["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    count_sql = (
        "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish'"
        " AND args -> 'session' ->> 'order' = $1"
    )
    assert await su.fetchval(count_sql, order) == 0  # nothing before the seventh
    await refuse_queued(su, str(wid))
    r = await run_ask(client, holder, {"work": work_ref, "brief": "هفتمی"})
    assert r.status_code == 201, r.text
    job = await take(client, ws)
    r = await send_file(client, ws, job["id"], "story_7.png", "image/png", a_pic(7))
    assert r.status_code == 201, r.text
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "هفتمی.",
              "data": {"session_id": "cs-st-1", "result_fa": "تمام.", "files": [r.json()["id"]]}},
        headers=ws["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    jobs = await su.fetch(
        "SELECT id, args FROM infra.server_jobs WHERE kind = 'publish'"
        " AND args -> 'session' ->> 'order' = $1",
        order,
    )
    args = [j["args"] if isinstance(j["args"], dict) else __import__("json").loads(j["args"])
            for j in jobs]  # fmt: skip
    assert len(args) == 7 and {a["kind"] for a in args} == {"story"}
    when = sorted(datetime.fromisoformat(a["meta"]["scheduled_at"]) for a in args)
    assert when == FL.story_times(flow, day)
    by_time = {a["meta"]["scheduled_at"]: a for a in args}
    first = by_time[FL.story_times(flow, day)[0].isoformat()]
    assert first["session"]["file_name"] == "story_1.png" and first["caption"] == ""
    assert first["files"][0]["mime"] == "image/jpeg"  # (every picture goes as a JPEG)
    assert "comment" not in first["meta"]
    assert first["meta"]["story_rule"]["keywords"] == ["الماس"]
    assert len(first["meta"]["story_rule"]["buttons"]) == 3
    said = await su.fetchval(
        "SELECT body_fa FROM notify.notifications WHERE source_code = 'flow' AND link_ref = $1",
        order,
    )
    assert said is not None and "الماس" in said and "۷ استوری" in said
    assert await su.fetchval(
        "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", order
    )
    # the first story is out: the day's reply rule, with its three buttons; one rule a day
    first_job = next(str(j["id"]) for j, a in zip(jobs, args, strict=True) if a is first)
    out = first["session"]["output"]
    rules_sql = (
        "SELECT args FROM infra.server_jobs WHERE args -> 'rule_for' ->> 'trigger' = 'story_reply'"
        " AND args ->> 'account' = $1 AND args -> 'rule_for' ->> 'output' = $2 ORDER BY created_at"
    )
    before = len(await su.fetch(rules_sql, "pro.chart", out))
    await answer(client, ig_rn, first_job, {"external_id": "17900000000000001", "url": None})
    made = await su.fetch(rules_sql, "pro.chart", out)
    assert len(made) == before + 1
    rule = [m["args"] if isinstance(m["args"], dict) else __import__("json").loads(m["args"])
            for m in made][-1]["meta"]["rule"]  # fmt: skip
    assert rule["trigger"] == "story_reply" and rule["keywords"] == ["الماس"]
    assert rule["buttons"][0]["title"] == "ورود رایگان VIP"
    second = next(str(j["id"]) for j, a in zip(jobs, args, strict=True)
                  if a["session"]["output"] == out and a is not first)  # fmt: skip
    await answer(client, ig_rn, second, {"external_id": "17900000000000002", "url": None})
    assert len(await su.fetch(rules_sql, "pro.chart", out)) == before + 1
    # the next day's brief names the word as taken
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert "الماس" in await FL.story_words(tx, "pro.chart")
    # the owner sees it as a map (the owner: «به صورت گرافیکی ببینم روند کار رو مثل خود n8n»): a
    # node per step on its lane, the seven stories fanned out, the day's run colouring each one
    page = await client.get(f"/api/v1/automations/N8:{fk}", headers=owner)
    assert page.status_code == 200, page.text
    g = page.json()["graph"]
    posts = [n for n in g["nodes"] if n["key"][0] == "s" and n["key"][1:].isdigit()]
    assert [n["key"] for n in posts] == [f"s{i}" for i in range(1, 8)]
    assert {n["col"] for n in posts} == {posts[0]["col"]} and [n["row"] for n in posts] == list(
        range(7)
    )
    assert {(e["source"], e["target"]) for e in g["edges"]} >= {("schedule", "s7"), ("s1", "rule")}
    assert g["lanes"][0] == "n8n" and "chatgpt" in g["lanes"] and "ighub" in g["lanes"]
    run = await client.get(f"/api/v1/line-runs/{order}", headers=owner)
    assert run.status_code == 200, run.text
    states = {x["key"]: x["state"] for x in run.json()["steps"]}
    assert {n["key"] for n in g["nodes"]} == set(states)
    assert (
        states["s1"] == "done" and sorted(states[f"s{i}"] for i in range(1, 8)).count("done") == 2
    )
    assert [states[f"s{i}"] for i in range(1, 8)].count("waiting") == 5
    assert states["compose"] == states["pictures"] == states["dm"] == "done"
    assert states["schedule"] == "done" and run.json()["state"] == "waiting"
    # its card on the board carries the same day's node colours (the strip under the card)
    board = await client.get("/api/v1/automations/board?kind=n8n", headers=owner)
    assert board.status_code == 200, board.text
    card = next(i for i in board.json()["items"] if i["ref"] == f"N8:{fk}")
    assert card["last"]["steps"] == [{"key": x["key"], "state": x["state"]}
                                     for x in run.json()["steps"]]  # fmt: skip
    assert SPB.view  # (the module is the one the hub runs)


def test_a_fixed_story_word_and_a_reel_without_its_story_in_the_brief() -> None:
    from dataclasses import replace

    at = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
    st = replace(FL.FLOWS["zaribsad_stories"], story_word="لینک")
    text = FL.brief_of(st, date(2026, 11, 17), at, ["الماس"])
    assert "«لینک»" in text and "کلمه‌ی تازه نساز" in text and "الماس" not in text
    # the fresh-word flows keep their list of taken words
    fresh = replace(st, story_word="")
    assert "«الماس»" in FL.brief_of(fresh, date(2026, 11, 17), at, ["الماس"])
    reel = FL.brief_of(replace(FL.FLOWS["dotcoin_reels"], story=False), date(2026, 11, 17), at)
    assert "story.mp4" not in reel and "استوری نه" in reel and "video.mp4" in reel
    assert FL.NEVER_SILENT_FA in reel and FL.NEVER_SILENT_FA not in FL.brief_of(
        st, date(2026, 11, 17), at
    )
    assert "story.mp4" in FL.brief_of(a_flow("PC"), START, at)


async def test_a_flows_effort_is_its_own_and_never_below_the_build_effort() -> None:
    """A flow's session runs at the flow's own effort (xhigh), never below the build effort; a
    direct turn keeps the direct effort."""
    from hq_api.domain import direct as DR

    class Tx:
        def __init__(self, row: dict[str, Any] | None) -> None:
            self.row = row

        async def first(self, *_: Any, **__: Any) -> dict[str, Any] | None:
            return self.row

    w = {"id": None}
    assert await DR.effort_of(Tx({"flow": True, "effort": "xhigh"}), w) == "xhigh"  # type: ignore[arg-type]
    assert await DR.effort_of(Tx({"flow": True, "effort": None}), w) == DR.BUILD_EFFORT  # type: ignore[arg-type]
    assert await DR.effort_of(Tx({"flow": True, "effort": "low"}), w) == DR.BUILD_EFFORT  # type: ignore[arg-type]
    assert await DR.effort_of(Tx({"flow": False, "effort": None}), w) == DR.DIRECT_EFFORT  # type: ignore[arg-type]


def test_dotcoins_day_is_two_reels_at_fixed_hours_and_twelve_slides() -> None:
    """⟨2026-11-17⟩ The owner («هم کاور و هم ریلز عالی بود»; «ساعت دو ریلز عالیه»):
    an educational reel at 13:00 and an informational one at 20:30 every day, each built the same
    day on Opus 5.5 at extra-high effort (⟨11-17⟩, was Fable 5.2); the day's educational stories are twelve slides from one
    ChatGPT chat, with a fresh reply word a day. Each has its n8n workflow file, and the map shows
    DotCoin's own steps at its own effort."""
    import json
    from pathlib import Path

    from hq_api.domain import flow_view as FV

    one, two = FL.FLOWS["dotcoin_reels"], FL.FLOWS["dotcoin_reels_2"]
    st = FL.FLOWS["dotcoin_stories"]
    for f in (one, two, st):
        assert (f.company, f.account, f.model, f.effort) == (
            "IG", "dotcoinme", "claude-opus-5-5", "xhigh",
        )  # fmt: skip
        assert f.same_day and not f.story and f.recipe == "dotcoin"
    assert set(one.hours) == {"13:00"} and set(two.hours) == {"20:30"}
    assert (one.cycle, two.cycle, two.pair) == (("آموزشی",), ("اطلاع‌رسانی",), "dotcoin_reels")
    assert len(st.stories) == 12 and not st.story_word and st.kit.endswith("/dotcoin-stories")
    assert "13:00" not in st.stories and "20:30" not in st.stories  # (never on a reel's minute)
    day = date(2026, 11, 18)
    at = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
    assert "نوع ریلز امروز: «آموزشی»" in FL.brief_of(one, day, at)
    assert "نوع ریلز امروز: «اطلاع‌رسانی»" in FL.brief_of(two, day, at)
    assert "story_12.jpg" in FL.brief_of(st, day, at, [])
    # each n8n workflow calls its own flow at its own hour (Tehran); the repository's files (the
    # api's test image has apps/api only: there, this part is checked by the repository's run)
    here = Path(__file__).resolve()
    root = next((d / "automations/n8n" for d in here.parents if (d / "automations/n8n").is_dir()),
                None)  # fmt: skip
    pairs = ((one, "flow-dotcoin-reels.json"), (two, "flow-dotcoin-reels-2.json"),
             (st, "flow-dotcoin-stories.json"))  # fmt: skip
    for f, name in pairs if root is not None else ():
        wf = json.loads((root / name).read_text())
        assert wf["id"] == f.n8n and wf["settings"]["timezone"] == "Asia/Tehran"
        text = json.dumps(wf, ensure_ascii=False)
        hh, mm = (int(x) for x in f.trigger_at.split(":"))
        assert f'"{mm} {hh} * * *"' in text and f"/internal/v1/flows/{f.key}/run" in text
        assert f"flow:{f.key}:" in text
    # the map: DotCoin's own steps (Pinterest, Arlo, the owner's cover) at xhigh
    steps = FV.steps_of(one)
    keys = [s.key for s in steps]
    assert {"inspire", "voice", "cover", "texts"} <= set(keys)
    assert all(s.effort == "xhigh" for s in steps if s.model)
    assert any("Arlo" in s.title_fa for s in steps)
    slides = FV.steps_of(st)
    assert any("۱۲ اسلاید" in s.title_fa for s in slides)
    assert all(s.effort == "xhigh" for s in slides if s.model)
    # ⟨2026-11-17⟩ every flow's map shows its own effort (all xhigh now)
    assert all(s.effort == "xhigh" for s in FV.steps_of(FL.FLOWS["dotcoin_reels"]) if s.model)


async def test_the_keeper_wakes_an_idle_day_only_while_an_account_has_room(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-24⟩ the owner: «نباید سیستم قطع باشد و هیچ کاری نکند بجز مواقعی که حساب مسدود یا
    لیمیت خورده باشد». A day's session with nothing queued or running, quiet for KEEP_IDLE, is woken
    by the clock's keeper while an account has room; never while none has, never twice at once, and
    at most KEEP_MAX times in 24 hours."""
    pc = await new_company()
    fk = f"t{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(FL, "FLOWS", {fk: a_flow(pc["code"], fk)})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=3)
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    work_ref = r.json()["work"]
    w = await su.fetchrow("SELECT id FROM work.work WHERE ref = $1", work_ref)
    # the day's turns all failed and its continues are spent: nothing queued, nothing running
    await su.execute(
        "UPDATE agents.runs SET state = 'failed', finished_at = now() WHERE work_id = $1"
        " AND state IN ('queued', 'claimed', 'running')",
        w["id"],
    )
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'failed' WHERE work_ref = $1 AND state IN ('queued', 'dispatched', 'running')",
        work_ref,
    )
    later = datetime.now(UTC) + timedelta(hours=1)  # quiet for an hour

    async def no_room(tx: Any) -> bool:
        return False

    async def room(tx: Any) -> bool:
        return True

    monkeypatch.setattr(FL, "claude_room", no_room)
    assert work_ref not in await FL.keep(hub, later, force=True)  # every account blocked or full
    monkeypatch.setattr(FL, "claude_room", room)
    assert work_ref in await FL.keep(hub, later, force=True)
    kept = await su.fetchval(
        "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'flow_kept'", w["id"]
    )
    assert kept == 1
    assert work_ref not in await FL.keep(hub, later, force=True)  # its run is queued now
    assert await FL.keep(hub, later.replace(minute=7), force=False) == []  # not the keeper's minute
    # at most KEEP_MAX wakes in 24 hours
    monkeypatch.setattr(FL, "KEEP_MAX", 1)
    await su.execute(
        "UPDATE agents.runs SET state = 'failed', finished_at = now() WHERE work_id = $1"
        " AND state IN ('queued', 'claimed', 'running')",
        w["id"],
    )
    assert work_ref not in await FL.keep(hub, later + timedelta(hours=1), force=True)


async def test_a_page_never_says_one_topic_twice_across_its_days_and_its_twin_flows(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-24⟩ each flow's day is a session with a ledger of its own, so @theprochart's two
    daily reels (prochart_reels, prochart_reels_2) both said «۴۴ الگو، دو خانواده» and the next
    day's was set to say it a third time. A day's topic is checked against every other day of the
    same page and family (the key without its trailing number); another family is its own."""
    from .conftest import agent_headers

    pc = await new_company()
    fk = f"t{uuid.uuid4().hex[:8]}"
    flows = {k: a_flow(pc["code"], k) for k in (fk, f"{fk}_2", f"{fk}x")}
    monkeypatch.setattr(FL, "FLOWS", flows)
    base = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=5)
    works = {}
    for i, k in enumerate(flows):
        r = await client.post(
            f"/api/v1/flows/{k}/run", headers={**owner, **idem()},
            json={"day": (base + timedelta(days=i)).isoformat()},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        works[k] = r.json()["work"]
    holder = await su.fetchval(
        "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id"
        " WHERE w.ref = $1",
        works[fk],
    )

    async def claim(k: str, title: str) -> httpx.Response:
        return await client.post(
            "/internal/v1/topics/claim", headers=await agent_headers(holder),
            json={"work": works[k], "title_fa": title},
        )  # fmt: skip

    r = await claim(fk, "۴۴ الگو، دو خانواده")
    assert r.status_code == 201, r.text
    # its twin flow on the same page, another day: the same topic is taken, the page's list said
    r = await claim(f"{fk}_2", "دو خانواده، ۴۴ الگو")
    assert r.status_code == 409 and r.json()["code"] == "topic_taken", r.text
    assert "۴۴ الگو" in r.json()["fields"]["recent"]
    r = await claim(f"{fk}_2", "دوئل با گذشته")
    assert r.status_code == 201, r.text
    # another family of the same page is its own (a story of the day's news is not a repeat)
    r = await claim(f"{fk}x", "۴۴ الگو، دو خانواده")
    assert r.status_code == 201, r.text


def test_a_topic_is_compared_without_its_spelling() -> None:
    """⟨2026-11-24⟩ the last gate's key: Arabic letters, Persian digits, half-spaces and
    punctuation do not make a topic new."""
    k = FL.topic_key
    assert k("۴۴ الگو، دو خانواده") == k("44 الگو دو  خانواده!") == k("٤٤ الگو - دو خانواده")
    assert k("میله‌ای OHLC") == k("میله ای ohlc") and k("كيف پول") == k("کیف پول")
    assert k("۴۴ الگو، دو خانواده") != k("دوئل با گذشته") and k("  ،، ") == ""


async def test_a_reel_on_a_topic_its_page_already_has_is_not_sent(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-24⟩ the owner: «از تکراری بودن ریلز های پروچارت جلوگیری بشه». A reel whose topic
    its page already has out or set (another flow's, another day's) is not sent: its session is
    woken to make it on a new topic, REPEAT_WAKES times, then the day waits; its own earlier
    send, or a cancelled one, is no repeat."""
    import dataclasses

    from hq_api.domain import session_publish as SPB

    pc = await new_company()
    fk = f"t{uuid.uuid4().hex[:8]}"
    page = f"rp.{fk}"
    monkeypatch.setattr(
        FL, "FLOWS", {fk: dataclasses.replace(a_flow(pc["code"], fk), account=page)}
    )
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=4)
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    order, work_ref = r.json()["order"], r.json()["work"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    pub = """INSERT INTO media.publications (company_id, account, kind, state, title_fa, topic_fa,
                 chain, source) VALUES ($1, $2, 'reel', $3, $4, $4, ARRAY[gen_random_uuid()], $5)"""
    await su.execute(pub, pc["id"], page, "cancelled", "دوئل با گذشته", '{"work": "W-0"}')
    await su.execute(pub, pc["id"], page, "published", "۴۴ الگو، دو خانواده", '{"work": "W-1"}')
    said = {"topic": "44 الگو؛ دو خانواده\n"}
    sent: list[str] = []

    async def package(tx: Any, w: Any, need_cover: bool = True) -> dict[str, Any]:
        return {"d": {"ref": "O-1"}, "reel": {"id": "f1"}, "story": None, "cover": {"id": "c"},
                "caption_d": None, "comment_d": None, "topic_d": {"ref": "O-1"}}  # fmt: skip

    async def route(tx: Any, co: Any) -> dict[str, Any]:
        return {"ready": True, "accounts": [page]}

    async def text_of(tx: Any, hub: Any, d: Any, names: Any) -> str:
        return said["topic"]

    async def send(*a: Any, **k: Any) -> dict[str, Any]:
        sent.append(k["what"])
        return {"id": uuid.uuid4()}

    async def nothing(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(FL, "package", package)
    monkeypatch.setattr(SPB, "_route", route)
    monkeypatch.setattr(SPB, "_text_of", text_of)
    monkeypatch.setattr(SPB, "_send", send)
    monkeypatch.setattr(SPB, "lock_publication", nothing)
    monkeypatch.setattr(SPB, "last_of", nothing)

    async def queued() -> int:
        return int(await su.fetchval(
            "SELECT count(*) FROM agents.runs WHERE work_id = $1 AND state = 'queued'"
            " AND reason LIKE 'topic_repeat:%'", wid,
        ))  # fmt: skip

    await su.execute(
        "UPDATE agents.runs SET state = 'failed', finished_at = now() WHERE work_id = $1"
        " AND state IN ('queued', 'claimed', 'running')",
        wid,
    )
    assert await FL.after_delivered(hub, wid) == "repeat"
    assert sent == [] and await queued() == 1
    steps = await su.fetchval("SELECT steps::text FROM owner.order_reports WHERE ref = $1", order)
    assert "تکرار ممنوع است" in steps and "44 الگو" in steps and "فایل موضوع" in steps
    meta = await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE id = $1", wid)
    meta = meta if isinstance(meta, dict) else __import__("json").loads(meta)
    assert meta["repeats"] == 1 and meta["repeat_of"] == "W-1" and "sent" not in meta
    for n in range(2, FL.REPEAT_WAKES + 2):  # made again on the same topic: woken, then held
        await su.execute(
            "UPDATE agents.runs SET state = 'failed', finished_at = now() WHERE work_id = $1"
            " AND state = 'queued'",
            wid,
        )
        assert await FL.after_delivered(hub, wid) == "repeat"
        assert await queued() == (1 if n <= FL.REPEAT_WAKES else 0)
    assert "باز هم تکراری بود" in await su.fetchval(
        "SELECT steps::text FROM owner.order_reports WHERE ref = $1", order
    )
    assert sent == []
    # a new topic (a cancelled one is free again): it goes out
    said["topic"] = "دوئل با گذشته"
    assert await FL.after_delivered(hub, wid) != "repeat"
    assert sent == ["reel"]


async def test_a_days_plan_never_closes_it_unsent_and_the_keeper_sends_a_whole_package(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-24⟩ W-001137 (a second reel of 11-24): its last turn broke, the session's
    plan was marked done and the day delivered with no video; nothing woke it again. A flow's day
    is done when it is sent: the plan never delivers it unsent, and the keeper sends a day whose
    whole package is in (no deliver came) instead of waking it."""
    from hq_api.domain import session_activity as SA

    pc = await new_company()
    fk = f"t{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(FL, "FLOWS", {fk: a_flow(pc["code"], fk)})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=6)
    r = await client.post(
        f"/api/v1/flows/{fk}/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    work_ref = r.json()["work"]
    w = await su.fetchrow(
        "SELECT id, company_id, assignee_id, status FROM work.work WHERE ref = $1", work_ref
    )
    await su.execute(
        "INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, category)"
        " VALUES ($1, $2, $3, 'بسته‌ی امروز', 'work')",
        w["company_id"], w["id"], w["assignee_id"],
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        works = [{"id": w["id"], "ref": work_ref, "is_root": True, "status": w["status"]}]
        assert await SA.finish_plan(tx, works) == []
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", w["id"]) == w["status"]

    await su.execute(
        "UPDATE agents.runs SET state = 'failed', finished_at = now() WHERE work_id = $1"
        " AND state IN ('queued', 'claimed', 'running')",
        w["id"],
    )
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'failed' WHERE work_ref = $1"
        " AND state IN ('queued', 'dispatched', 'running')",
        work_ref,
    )
    later = datetime.now(UTC) + timedelta(hours=1)
    tried: list[Any] = []

    async def whole(tx: Any, hub: Any, work_id: Any) -> str:
        tried.append(work_id)
        return "sent"

    async def room(tx: Any) -> bool:
        return True

    monkeypatch.setattr(FL, "_publish", whole)
    monkeypatch.setattr(FL, "claude_room", room)
    assert work_ref not in await FL.keep(hub, later, force=True)
    assert w["id"] in tried
    assert not await su.fetchval(
        "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'flow_kept'", w["id"]
    )
