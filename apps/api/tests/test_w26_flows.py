"""⟨2026-11-13⟩ A working group's daily run, started by n8n (domain/flows.py).

The owner: «اون دکمه انتشارم قرار نیست دیگه من بزنم و قراره اتوماتیک و اتوماسیونی باشه توسط
n8n»; the hours: a week at 09:30 Tehran, a week at 14:00, a week at 19:30, the fourth at the hour
with the most views; and «گزارش کوتاه به من رو توی آپ توسط نوتیف بده».
"""

from __future__ import annotations

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


def a_flow(company: str) -> FL.Flow:
    return FL.Flow(key="t", company=company, account="pro.chart", title_fa="ریلز آزمایشی",
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
    monkeypatch.setattr(FL, "FLOWS", {"t": a_flow(pc["code"])})
    day = datetime.now(ZoneInfo(FL.TEHRAN)).date() + timedelta(days=1)

    # n8n's call must be signed
    r = await client.post("/internal/v1/flows/t/run", json={"day": day.isoformat()})
    assert r.status_code == 401, r.text
    # the day's order: once per key
    key = idem()
    r = await client.post(
        "/api/v1/flows/t/run", headers={**owner, **key}, json={"day": day.isoformat()}
    )
    assert r.status_code == 201, r.text
    got = r.json()
    at = datetime.fromisoformat(got["publish_at"])
    assert at.astimezone(ZoneInfo(FL.TEHRAN)).strftime("%H:%M") in ("09:30", "14:00", "19:30")
    again = await client.post(
        "/api/v1/flows/t/run", headers={**owner, **key}, json={"day": day.isoformat()}
    )
    assert again.json()["order"] == got["order"]
    # another key, the same day: still the one order
    third = await client.post(
        "/api/v1/flows/t/run", headers={**owner, **idem()}, json={"day": day.isoformat()}
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
    r = await run_ask(client, holder, {"work": work_ref, "brief": "بسته‌ی امروز"})
    assert r.status_code == 201, r.text
    job = await take(client, ws)
    files = []
    for name, ctype, data in (
        ("video.mp4", "video/mp4", mp4(2)), ("story.mp4", "video/mp4", mp4(1)),
        ("cover.png", "image/png", a_png(1)), ("caption.txt", "text/plain", "کپشن #پرو_چارت".encode()),
        ("comment.txt", "text/plain", COMMENT.encode()), ("topic.txt", "text/plain", "بازپخش".encode()),
    ):  # fmt: skip
        r = await send_file(client, ws, job["id"], name, ctype, data)
        assert r.status_code == 201, r.text
        files.append(r.json()["id"])
    await refuse_queued(su, str(w["id"]))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": "cs-flow-1", "result_fa": "آماده.", "files": files}},
        headers=ws["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
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
