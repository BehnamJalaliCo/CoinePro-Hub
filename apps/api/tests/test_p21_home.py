"""Prompt 21 part 3 (contract §29.13): the owner's home. Three cards (one
effective and one good suggestion across every companies, one real move);
a «نه» is kept with its reason, told to the secretary's memory and never
shown again; «اجرا کن» makes an order through POST /orders; progress comes
only from real figures; nothing technical but the critical notifications;
every string the owner reads passes humanize.check."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import home as HM
from hq_api.domain import humanize as H
from hq_api.hub import Hub

from .conftest import idem

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture
async def quiet(hub: Hub, su: Any) -> Any:
    """The other tests' open suggestions out of the way (later, far away), so
    the cards are this test's own (the generator has run first)."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await HM.generate(tx)
    await su.execute(
        """UPDATE owner.suggestions SET state = 'later', later_until = now() + interval '10 years'
           WHERE state = 'new' OR (state = 'later' AND later_until <= now())"""
    )
    yield


async def suggest(hub: Hub, co: dict[str, Any], title: str, impact: int, cost: int,
                  source: str = "group") -> dict[str, Any] | None:  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return await HM.add_suggestion(
            tx,
            company_id=co["id"],
            company_code=co["code"],
            title_fa=title,
            why_fa="عددهای هفته‌ی گذشته این را نشان میدهد.",
            impact_fa="فالوور هفتگی حدود 20٪ بیشتر",
            cost_fa="دو کار کوچک",
            impact=impact,
            cost=cost,
            source=source,
            key=f"test:{co['code']}:{title}",
        )


def strings(home: dict[str, Any]) -> list[str]:
    out: list[str] = list(home["morning"])
    for card in ("effective", "good"):
        s = home["cards"][card]
        if s:
            out += [s["title_fa"], s["why_fa"], s["impact_fa"], s["cost_fa"]]
    if home["cards"]["progress"]:
        out.append(home["cards"]["progress"]["title_fa"])
    for g in home["groups"]:
        out.append(g["title_fa"])
        for c in g["companies"]:
            out.append(c["name_fa"])
            if c["kpi"]:
                out += [c["kpi"]["title_fa"], c["kpi"]["unit"]]
    for o in home["orders"]:
        out += [o["text_fa"], o["summary_fa"]]
    return out


async def test_three_cards_and_a_no_is_remembered_and_never_shown_again(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    quiet: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b = await new_company(), await new_company()
    big = await suggest(hub, a, "سری ریلز روزانه را برای این شرکت مُهر کنید", 5, 4)
    cheap = await suggest(hub, b, "زمان انتشار استوری را به ساعت ۲۱ ببرید", 2, 1)
    mid = await suggest(hub, b, "یک پست کاروسل آموزشی در هفته اضافه شود", 3, 3)
    assert big and cheap and mid
    assert big["kind"] == "effective" and cheap["kind"] == "good"
    home = (await client.get("/api/v1/home", headers=owner)).json()
    assert home["cards"]["effective"]["id"] == str(big["id"])  # the highest impact
    assert home["cards"]["good"]["id"] == str(cheap["id"])  # the best impact per cost of the rest
    assert (
        home["cards"]["effective"]["kind"] == "effective"
        and home["cards"]["good"]["kind"] == "good"
    )
    # «نه»: the reason kept, the secretary's memory told, never shown again
    told: list[tuple[str, str, dict[str, Any]]] = []
    fake = types.ModuleType("hq_api.domain.dispatch")

    async def remember(tx: Any, kind: str, text_fa: str, data: dict[str, Any]) -> None:
        told.append((kind, text_fa, data))

    fake.remember = remember  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hq_api.domain.dispatch", fake)
    r = await client.post(f"/api/v1/home/suggestions/{big['id']}", headers=owner,
                          json={"action": "no", "reason_fa": "این شرکت هنوز تیم رسانه ندارد"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["reason_fa"]) == ("no", "این شرکت هنوز تیم رسانه ندارد")
    assert told and told[0][0] == "suggestion_no" and "تیم رسانه" in told[0][1]
    home = (await client.get("/api/v1/home", headers=owner)).json()
    shown = {home["cards"]["effective"]["id"], (home["cards"]["good"] or {}).get("id")}
    assert str(big["id"]) not in shown and str(mid["id"]) in shown
    assert await suggest(hub, a, "سری ریلز روزانه را برای این شرکت مُهر کنید", 5, 4) is None
    # «بعداً»: hidden for now
    r = await client.post(f"/api/v1/home/suggestions/{mid['id']}", headers=owner,
                          json={"action": "later"})  # fmt: skip
    assert r.json()["state"] == "later"
    home = (await client.get("/api/v1/home", headers=owner)).json()
    assert str(mid["id"]) not in {(home["cards"][k] or {}).get("id") for k in ("effective", "good")}
    # «اجرا کن»: an order through POST /orders (Idempotency-Key), made once
    assert (await client.post(f"/api/v1/home/suggestions/{cheap['id']}", headers=owner,
                              json={"action": "run"})).status_code == 422  # fmt: skip
    r = await client.post(f"/api/v1/home/suggestions/{cheap['id']}", headers={**owner, **idem()},
                          json={"action": "run"})  # fmt: skip
    assert r.status_code == 200, r.text
    ref = r.json()["order_ref"]
    assert r.json()["state"] == "run" and ref.startswith("F-")
    order = await su.fetchrow("SELECT text, routes FROM owner.orders WHERE ref = $1", ref)
    assert "استوری" in order["text"]
    again = await client.post(f"/api/v1/home/suggestions/{cheap['id']}", headers={**owner, **idem()},
                              json={"action": "run"})  # fmt: skip
    assert again.json()["order_ref"] == ref
    assert await su.fetchval("SELECT count(*) FROM owner.orders WHERE ref = $1", ref) == 1
    home = (await client.get("/api/v1/home", headers=owner)).json()
    assert ref in {o["ref"] for o in home["orders"]}
    for text in strings(home):
        assert H.check(text) == [], text


async def test_a_text_that_cannot_be_plain_is_never_shown(
    hub: Hub, new_company: Callable[..., Any], quiet: Any
) -> None:
    co = await new_company()
    dirty = await suggest(hub, co, "کار W-000094 به IG-AIOPS-MGR سپرده شد و delivered شد", 3, 2)
    assert dirty is not None and H.check(dirty["title_fa"]) == []
    assert "W-000094" not in dirty["title_fa"]
    english = await suggest(hub, co, "Publish three reels every day on the main page", 4, 2)
    assert english is None


def test_the_advisors_memo_moves_are_read_by_rule() -> None:
    body = (
        "یادداشت رشد TY\n\n"
        "1. سری ریلز آموزشی حد ضرر را راه بیندازید\n"
        "   چرا: بازدید ریلزهای آموزشی دو برابر بود.\n"
        "2) صفحه‌ی فرود ثبت‌نام را کوتاه کنید\n"
        "۳- کانال تلگرام را به سایت وصل کنید\n"
        "4. چهارمی خوانده نمیشود\n"
    )
    moves = HM.memo_moves(body)
    assert [m[0] for m in moves] == [
        "سری ریلز آموزشی حد ضرر را راه بیندازید",
        "صفحه‌ی فرود ثبت‌نام را کوتاه کنید",
        "کانال تلگرام را به سایت وصل کنید",
    ]
    assert "دو برابر" in moves[0][1]


async def test_progress_comes_only_from_real_figures(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    up, flat, hub_only = await new_company(), await new_company(), await new_company()
    today = datetime.now(TEHRAN).date()

    async def put(co: dict[str, Any], kind: str, key: str, day: date, value: float) -> None:
        await su.execute(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES ($1, $2, $3, $4, 's', $5, $2)
               ON CONFLICT (company_id, kind, day, key, subject) DO UPDATE SET value = EXCLUDED.value""",
            co["id"], kind, day, key, value,
        )  # fmt: skip

    await put(up, "telegram", "followers", today - timedelta(days=8), 1200)
    await put(up, "telegram", "followers", today - timedelta(days=1), 1350)
    await put(up, "search_console", "position", today - timedelta(days=9), 18)
    await put(up, "search_console", "position", today - timedelta(days=2), 9)
    await put(flat, "telegram", "followers", today - timedelta(days=8), 500)
    await put(flat, "telegram", "followers", today - timedelta(days=1), 480)  # fell: no progress
    await put(hub_only, "hub", "published", today - timedelta(days=8), 1)
    await put(hub_only, "hub", "published", today - timedelta(days=1), 3)  # the hub's: never
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await HM.generate_progress(tx, today)
        await HM.generate_progress(tx, today)  # each move once
    rows = await su.fetch(
        """SELECT p.company_id, p.kpi, p.kind, p.before_value, p.after_value, p.before_at, p.after_at,
                  p.title_fa FROM owner.progress p WHERE p.company_id = ANY($1::uuid[]) ORDER BY p.kpi""",
        [up["id"], flat["id"], hub_only["id"]],
    )
    assert [(r["company_id"], r["kpi"]) for r in rows] == [
        (up["id"], "followers"),
        (up["id"], "position"),
    ]
    followers, position = rows
    assert (float(followers["before_value"]), float(followers["after_value"])) == (1200.0, 1350.0)
    assert (float(position["before_value"]), float(position["after_value"])) == (18.0, 9.0)
    for r in rows:
        real = await su.fetchval(
            """SELECT value FROM growth.metrics_daily WHERE company_id = $1 AND kind = $2
                 AND day = $3""",
            r["company_id"], r["kind"], r["after_at"],
        )  # fmt: skip
        assert float(real) == float(r["after_value"])  # a real figure, never a guess
        assert H.check(r["title_fa"]) == [] and "از" in r["title_fa"] and "رسید" in r["title_fa"]
    # the rank's move (18 -> 9, half) beats the followers' (12.5%)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        best = await HM.best_progress(tx, today)
    assert best is not None
    if best["company_id"] == up["id"]:
        assert best["kpi"] == "position"


async def test_the_morning_is_at_most_five_plain_lines_and_nothing_technical_but_critical(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    for level, title in (("urgent", "سایت محصول از دسترس خارج شد"), ("info", "دیسک سرور پر شد"),
                         ("report", "گزارش فنی هفته")):  # fmt: skip
        await su.execute(
            """INSERT INTO notify.notifications (company_id, level, title_fa, source_kind, source_code,
                   delivered_in_app)
               VALUES ($1, $2, $3, 'service', 'watch', true)""",
            co["id"], level, title,
        )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lines = await HM.morning_lines(tx, "Asia/Tehran", datetime.now(TEHRAN).date())
    assert 1 <= len(lines) <= 5 and all(H.check(x) == [] for x in lines), lines
    await su.execute("DELETE FROM growth.home_mornings WHERE day = $1", datetime.now(TEHRAN).date())
    out = await HM.morning_tick(hub, datetime.now(UTC))
    assert 1 <= out["morning"] <= 5
    r = await client.get("/api/v1/home", headers=owner)
    assert r.status_code == 200, r.text
    home = r.json()
    assert len(home["morning"]) <= 5
    crit = [n for n in home["critical"] if n["company"] == co["code"]]
    assert [n["title_fa"] for n in crit] == ["سایت محصول از دسترس خارج شد"]
    assert all(n["level"] == "urgent" for n in home["critical"])
    assert any(g["key"] == "content" for g in home["groups"])
    for text in strings(home):
        assert H.check(text) == [], text


async def test_the_councils_plan_and_the_closed_experiment_become_suggestions(
    hub: Hub, su: Any, new_company: Callable[..., Any], quiet: Any
) -> None:
    co = await new_company()
    group = await su.fetchval("SELECT id FROM growth.groups WHERE key = 'content'")
    exp = await su.fetchval(
        """INSERT INTO growth.experiments (company_id, group_id, week, hypothesis_fa, metric, target,
               result, kept, created_by_code, closed_at)
           VALUES ($1, $2, $3, 'ریلز کوتاه‌تر بیشتر دیده میشود', 'views', 1000, 1300, true, 'x', now())
           RETURNING id""",
        co["id"], group, date.today() - timedelta(days=7),
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        made = await HM.generate(tx)
        again = await HM.generate(tx)
    assert made >= 1 and again == 0
    s = await su.fetchrow(
        "SELECT source, title_fa, state, why_fa FROM owner.suggestions WHERE key = $1",
        f"experiment:{exp}",
    )
    assert s["source"] == "group" and s["state"] == "new" and "1300" in s["why_fa"]
    assert H.check(s["title_fa"]) == []
    assert isinstance(exp, UUID)
