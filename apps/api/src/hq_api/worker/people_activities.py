"""Temporal activities for stars (prompt 08 §4, contract §18.4).

stars_reminder  Friday 18:00 (owner zone): each CEO gets "this week's stars"
stars_rollup    daily 08:00 (owner zone): on Saturday the week that just
                ended (Saturday..Friday), on the 1st of a Jalali month the
                month that just ended; the weekly best company gets its story
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from temporalio import activity

from hq_api.domain import hiring, stories
from hq_api.domain import stars as S
from hq_api.hub import Hub
from hq_api.worker.jalali import to_jalali


class PeopleActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.stars_reminder, self.stars_rollup]

    @activity.defn(name="stars_reminder")
    async def stars_reminder(self) -> dict[str, Any]:
        async with self._tx() as tx:
            today = datetime.now(await S.owner_zone(tx)).date()
            made = await S.remind(tx, S.saturday_of(today))
        return {"work": made}

    @activity.defn(name="stars_rollup")
    async def stars_rollup(self, day: str | None = None) -> dict[str, Any]:
        """`day` (YYYY-MM-DD, owner zone) for tests and catch-up; default today."""
        out: dict[str, Any] = {}
        async with self._tx() as tx:
            today = date.fromisoformat(day) if day else datetime.now(await S.owner_zone(tx)).date()
            if today.weekday() == 5:  # Saturday: the week Saturday..Friday that just ended
                start = S.saturday_of(today) - timedelta(days=7)
                week = await S.rollup(tx, "week", start.isoformat(), *S.week_window(start))
                out["week"] = {k: week[k] for k in ("key", "created", "best_company")}
                if week["created"] and week["best_company"]:
                    await self._best_story(tx, week)
            if to_jalali(today)[2] == 1:  # the 1st of a Jalali month: the month that ended
                start = hiring.jalali_month_start(today - timedelta(days=1))
                month = await S.rollup(tx, "month", S.jalali_key(start), start, today)
                out["month"] = {k: month[k] for k in ("key", "created", "best_company")}
        return out

    async def _best_story(self, tx: Any, week: dict[str, Any]) -> None:
        data = week["data"]
        best = week["best_company"]
        row = next(c for c in data["companies"] if c["company"] == best)
        top = next((e for e in data["employees"] if e["company"] == best), None)
        co = await tx.one("SELECT id FROM core.companies WHERE code = :c", c=best)
        figures = [
            {"label_fa": "ستاره‌ی شرکت", "value": str(row["stars"])},
            {"label_fa": "امتیاز", "value": str(row["score"])},
        ]
        if top:
            figures.append({"label_fa": "بهترین کارمند", "value": top["code"][-16:]})
        await stories.system(
            tx,
            company_id=co["id"],
            company_code=best,
            kind="stars",
            title_fa=f"شرکت برتر هفته: {best}",
            body_fa=(
                f"هفته‌ی {week['key']}: {best} با {row['stars']} ستاره اول شد"
                + (f"؛ بهترین کارمندش {top['code']} با {top['stars']} ستاره." if top else ".")
            ),
            figures=figures,
            links={"period": f"week:{week['key']}", **({"employee": top["code"]} if top else {})},
            event_key=f"stars:week:{week['key']}",
        )
