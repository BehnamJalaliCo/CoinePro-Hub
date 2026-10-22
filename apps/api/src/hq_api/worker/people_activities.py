"""Temporal activities for stars (prompt 08 §4, contract §18.4).

stars_reminder  Friday 18:00 (owner zone): each CEO gets "this week's stars"
stars_rollup    daily 08:00 (owner zone): on Saturday the week that just
                ended (Saturday..Friday), on the 1st of a Jalali month the
                month that just ended; the weekly best company gets its story,
                and (8.1 §2.15) each new roll-up gives the Chief Overseer one
                work item «درس از {بهترین شرکت}، {دوره}» to write its lessons

Both are rule-only (no model call). Whatever would wake an agent (a work
item: the CEOs' reminder, the overseer's lesson) is skipped while the
holding's kill switch is engaged (owner decision 2026-10-22).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from temporalio import activity

from hq_api.domain import hiring, stories
from hq_api.domain import stars as S
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.principal import Principal
from hq_api.worker.jalali import to_jalali

OVERSEER = "OVR"  # the holding's Chief Overseer: {holding}-OVR
PERIOD_FA = {"week": "هفته‌ی", "month": "ماه"}


class PeopleActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.stars_reminder, self.stars_rollup]

    async def _holding_locked(self, tx: Any) -> bool:
        holding = await self.hub.companies.holding()
        return await tx.scalar("SELECT control.lock_state(:h)", h=holding.id) is not None

    @activity.defn(name="stars_reminder")
    async def stars_reminder(self) -> dict[str, Any]:
        async with self._tx() as tx:
            if await self._holding_locked(tx):
                return {"work": [], "skipped": "holding_locked"}
            today = datetime.now(await S.owner_zone(tx)).date()
            made = await S.remind(tx, S.saturday_of(today))
        return {"work": made}

    async def _lesson_work(self, tx: Any, period: str, key: str, best: str | None) -> str | None:
        """The overseer's work item for a new roll-up's lessons (8.1 §2.15):
        once per period, only with a best company, never while the holding's
        kill switch is engaged (it would wake the overseer)."""
        if not best or await self._holding_locked(tx):
            return None
        holding = await self.hub.companies.holding()
        code = f"{holding.code}-{OVERSEER}"
        if not await tx.scalar(
            "SELECT 1 FROM core.employees WHERE code = :c AND status = 'active'", c=code
        ):
            return None
        title = f"درس از {best}، {PERIOD_FA.get(period, period)} {key}"
        if await tx.scalar(
            "SELECT 1 FROM work.work WHERE company_id = :co AND title = :t", co=holding.id, t=title
        ):
            return None
        w = await W.create(
            tx,
            Principal(kind="service", code="stars", role="service"),
            company_id=holding.id,
            company_code=holding.code,
            title=title,
            brief=(
                f"برآیند {period}:{key} بسته شد و شرکت برتر {best} است. با lesson.write "
                f"(source_company={best}, period={period}:{key}) درس‌هایی را که شرکت‌های دیگر باید "
                "از آن بگیرند با شاهد بنویس (برآیند در /stars/rollup)."
            ),
            kind="one_off",
            priority="P3",
            assignee_code=code,
        )
        return str(w["ref"])

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
                if week["created"]:
                    out["week"]["lesson_work"] = await self._lesson_work(
                        tx, "week", week["key"], week["best_company"]
                    )
            if to_jalali(today)[2] == 1:  # the 1st of a Jalali month: the month that ended
                start = hiring.jalali_month_start(today - timedelta(days=1))
                month = await S.rollup(tx, "month", S.jalali_key(start), start, today)
                out["month"] = {k: month[k] for k in ("key", "created", "best_company")}
                if month["created"]:
                    out["month"]["lesson_work"] = await self._lesson_work(
                        tx, "month", month["key"], month["best_company"]
                    )
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
