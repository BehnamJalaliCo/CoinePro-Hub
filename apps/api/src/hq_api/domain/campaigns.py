"""One campaign calendar (contract §31.5 ⟨1.13⟩).

`GET /campaign-calendar` merges what is planned to go out, from every source, into
one list of `CampaignCalendarItem`s and marks the conflicts by code:

  line         the production lines' runs (§30). Read lazily: if the engine's tables are
               not there (or look different), the source is skipped, never an error
  newsletter   growth.newsletter_campaigns with a send time (§31.3)
  ad           the ad campaigns that spent in the window (§31.6; optional like `line`)
  campaign     growth.campaigns (a goal over a span of days)
  manual       growth.calendar_manual (the owner's own items)

A conflict: two posts on one channel (company and platform) closer than the spacing in
settings, or a post on an Iranian holiday (apps/api/seed/calendar/holidays.yaml, the
change calendar's data). The calendar marks; it never moves or blocks anything.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from hq_api.db import Tx
from hq_api.domain import gov_calendar as GC
from hq_api.domain.gov_common import zone
from hq_api.errors import ApiError
from hq_api.schemas import Model

log = logging.getLogger("hq_api.campaigns")

Kind = Literal["line", "newsletter", "ad", "campaign", "manual"]
MAX_SPAN_DAYS = 93
PLATFORM = r"^[a-z][a-z0-9_]{1,40}$"
CAMPAIGN_STATES = "^(planned|running|done|cancelled)$"
LINE_SKIP = ("cancelled", "skipped")


class CampaignCalendarItem(Model):
    day: date
    at: datetime | None
    company: str
    kind: Kind
    ref: str
    title_fa: str
    platform: str | None
    state: str
    conflict_fa: str | None = None


class HolidayDay(Model):
    day: date
    title_fa: str


class CampaignCalendar(Model):
    start: date = Field(serialization_alias="from")
    to: date
    items: list[CampaignCalendarItem]
    holidays: list[HolidayDay]


class CampaignIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    title_fa: str = Field(min_length=1, max_length=200)
    goal_fa: str = Field(default="", max_length=1000)
    starts: date
    ends: date
    channels: list[str] = Field(default_factory=list, max_length=20)
    budget: float | None = Field(default=None, ge=0)
    state: str = Field(default="planned", pattern=CAMPAIGN_STATES)


class CampaignPut(Model):
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    goal_fa: str | None = Field(default=None, max_length=1000)
    starts: date | None = None
    ends: date | None = None
    channels: list[str] | None = Field(default=None, max_length=20)
    budget: float | None = Field(default=None, ge=0)
    state: str | None = Field(default=None, pattern=CAMPAIGN_STATES)


class Campaign(Model):
    id: UUID
    company: str
    title_fa: str
    goal_fa: str
    starts: date
    ends: date
    channels: list[str]
    budget: float | None
    state: str


class ManualIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    day: date
    at: AwareDatetime | None = None
    title_fa: str = Field(min_length=1, max_length=200)
    platform: str | None = Field(default=None, pattern=PLATFORM)


class ManualPut(Model):
    day: date | None = None
    at: AwareDatetime | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    platform: str | None = Field(default=None, pattern=PLATFORM)
    state: str | None = Field(default=None, pattern="^(planned|done|cancelled)$")


# ------------------------------------------------------------- pure rules --
def valid_channels(channels: list[str]) -> list[str]:
    import re

    out: list[str] = []
    for c in channels:
        if not re.fullmatch(PLATFORM, c):
            raise ApiError(
                422, "validation_failed", fields={"channels": f"{c!r} is not a platform"}
            )
        if c not in out:
            out.append(c)
    return out


def check_span(starts: date, ends: date) -> None:
    if ends < starts:
        raise ApiError(422, "validation_failed", fields={"ends": "not before the start"})


YEARS = (2000, 2100)  # the calendar's reach: outside it a day cannot become an instant


def check_window(start: date, to: date) -> None:
    for name, d in (("from", start), ("to", to)):
        if not YEARS[0] <= d.year <= YEARS[1]:
            raise ApiError(
                422, "validation_failed", fields={name: f"between {YEARS[0]} and {YEARS[1]}"}
            )
    if to < start:
        raise ApiError(422, "validation_failed", fields={"to": "not before from"})
    if (to - start).days > MAX_SPAN_DAYS:
        raise ApiError(422, "validation_failed", fields={"to": f"at most {MAX_SPAN_DAYS} days"})


def mark_conflicts(
    items: list[CampaignCalendarItem], spacing_min: int, holidays: dict[date, list[str]]
) -> None:
    """Fill `conflict_fa` in place. Spacing: items of one company and platform with a
    time, closer than `spacing_min`; both are marked. Holiday: any item that publishes
    (not a campaign's span) on a holiday."""
    gap = timedelta(minutes=spacing_min)
    groups: dict[tuple[str, str], list[CampaignCalendarItem]] = {}
    for it in items:
        if it.at is not None and it.platform and it.kind != "campaign" and it.state != "cancelled":
            groups.setdefault((it.company, it.platform), []).append(it)
    for rows in groups.values():
        rows.sort(key=lambda i: i.at or datetime.min.replace(tzinfo=UTC))
        for a, b in pairwise(rows):
            if a.at is not None and b.at is not None and b.at - a.at < gap:
                note = f"دو انتشار در یک کانال کمتر از {spacing_min} دقیقه با هم فاصله دارند"
                a.conflict_fa = a.conflict_fa or note
                b.conflict_fa = b.conflict_fa or note
    for it in items:
        if it.kind != "campaign" and it.day in holidays and it.state != "cancelled":
            note = "روز تعطیل: " + "، ".join(holidays[it.day])
            it.conflict_fa = f"{it.conflict_fa}؛ {note}" if it.conflict_fa else note


# ------------------------------------------------------------ the sources --
Source = Callable[
    [Tx, datetime, datetime, str, UUID | None, dict[UUID, str]],
    Awaitable[list[CampaignCalendarItem]],
]


def _day(at: datetime, tz: str) -> date:
    return at.astimezone(zone(tz)).date()


async def _optional(tx: Tx, table: str) -> bool:
    return bool(await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table))


async def _manual(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CampaignCalendarItem]:
    rows = await tx.all(
        "SELECT * FROM growth.calendar_manual WHERE day BETWEEN :a AND :b "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        a=_day(lo, tz),
        b=_day(hi, tz),
        co=co,
    )
    return [
        CampaignCalendarItem(
            day=r["day"],
            at=r["at"],
            company=codes.get(r["company_id"], "-"),
            kind="manual",
            ref=str(r["id"]),
            title_fa=r["title_fa"],
            platform=r["platform"],
            state=r["state"],
        )
        for r in rows
    ]


async def _campaigns(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CampaignCalendarItem]:
    a, b = _day(lo, tz), _day(hi, tz)
    rows = await tx.all(
        "SELECT * FROM growth.campaigns WHERE starts <= :b AND ends >= :a "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        a=a,
        b=b,
        co=co,
    )
    return [
        CampaignCalendarItem(
            day=max(r["starts"], a),
            at=None,
            company=codes.get(r["company_id"], "-"),
            kind="campaign",
            ref=str(r["id"]),
            title_fa=r["title_fa"],
            platform=None,
            state=r["state"],
        )
        for r in rows
    ]


async def _newsletters(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CampaignCalendarItem]:
    rows = await tx.all(
        "SELECT * FROM growth.newsletter_campaigns WHERE send_at >= :lo AND send_at < :hi "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        lo=lo,
        hi=hi,
        co=co,
    )
    return [
        CampaignCalendarItem(
            day=_day(r["send_at"], tz),
            at=r["send_at"],
            company=codes.get(r["company_id"], "-"),
            kind="newsletter",
            ref=str(r["id"]),
            title_fa=f"خبرنامه: {r['subject']}",
            platform="newsletter",
            state=r["state"],
        )
        for r in rows
    ]


async def _lines(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CampaignCalendarItem]:
    """The production lines (§30): the engine's own calendar (every `on` line's planned
    occurrences and the runs made), imported lazily. Without the engine (no module, no
    tables) or if it answers in another shape, the source gives nothing, never an error."""
    try:
        from hq_api.lines import store as line_store
    except ImportError:
        return []
    if not (await _optional(tx, "lines.runs") and await _optional(tx, "lines.lines")):
        return []
    try:
        async with tx.conn.begin_nested():
            days = await line_store.calendar(tx, lo, hi, tz, co)
            titles = {
                r["ref"]: r["title_fa"]
                for r in await tx.all("SELECT ref, title_fa FROM lines.lines")
            }
        out = []
        for d in days:
            for it in d["items"]:
                if str(it["state"]) in LINE_SKIP:
                    continue
                out.append(
                    CampaignCalendarItem(
                        day=_day(it["at"], tz),
                        at=it["at"],
                        company=str(it["company"]),
                        kind="line",
                        ref=str(it["run"] or it["line"]),
                        title_fa=str(titles.get(it["line"]) or it["line"]),
                        platform=it["platform"],
                        state=str(it["state"]),
                    )
                )
    except Exception:
        log.info(
            "the lines calendar answered in another shape; the line source is skipped",
            exc_info=True,
        )
        return []
    return out


async def _ads(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CampaignCalendarItem]:
    """Ad campaigns that spent in the window (the ads part's growth.ad_daily, with the
    name and status of growth.ad_campaigns when that table is there), optional."""
    if not await _optional(tx, "growth.ad_daily"):
        return []
    named = await _optional(tx, "growth.ad_campaigns")
    join = (
        "LEFT JOIN growth.ad_campaigns c ON c.company_id = d.company_id "
        "AND c.platform = d.platform AND c.campaign_id = d.campaign_id"
        if named
        else ""
    )
    cols = (
        "max(c.name) AS name, max(c.status) AS status" if named else "NULL AS name, NULL AS status"
    )
    sql = (
        f"SELECT d.company_id, d.platform, d.campaign_id, min(d.day) AS first_day, {cols} "  # noqa: S608
        f"FROM growth.ad_daily d {join} WHERE d.day BETWEEN :a AND :b "
        "AND (CAST(:co AS uuid) IS NULL OR d.company_id = :co) "
        "GROUP BY d.company_id, d.platform, d.campaign_id"
    )
    try:
        async with tx.conn.begin_nested():
            rows = await tx.all(sql, a=_day(lo, tz), b=_day(hi, tz), co=co)
    except Exception:
        log.info("the ads tables look different; the ad source is skipped", exc_info=True)
        return []
    return [
        CampaignCalendarItem(
            day=r["first_day"],
            at=None,
            company=codes.get(r["company_id"], "-"),
            kind="ad",
            ref=f"{r['platform']}:{r['campaign_id']}",
            title_fa=f"تبلیغ {r['platform']} · {r['name'] or r['campaign_id']}",
            platform=None,
            state=str(r["status"] or "active"),
        )
        for r in rows
    ]


SOURCES: list[Source] = [_lines, _newsletters, _ads, _campaigns, _manual]


async def build(
    tx: Tx, start: date, to: date, spacing_min: int, tz: str, company: Any | None = None
) -> CampaignCalendar:
    """The merged, conflict-marked calendar of [start, to] (the owner's days)."""
    check_window(start, to)
    z = zone(tz)
    lo = datetime.combine(start, datetime.min.time(), z).astimezone(UTC)
    hi = datetime.combine(to + timedelta(days=1), datetime.min.time(), z).astimezone(UTC)
    codes = {r["id"]: r["code"] for r in await tx.all("SELECT id, code FROM core.companies")}
    co = company.id if company is not None else None
    items: list[CampaignCalendarItem] = []
    for src in SOURCES:
        items.extend(await src(tx, lo, hi, tz, co, codes))
    holidays = {d: t for d, t in GC.load_holidays().items() if start <= d <= to}
    mark_conflicts(items, spacing_min, holidays)
    items.sort(key=lambda i: (i.day, i.at or datetime.max.replace(tzinfo=UTC), i.company, i.ref))
    return CampaignCalendar(
        start=start,
        to=to,
        items=items,
        holidays=[HolidayDay(day=d, title_fa="، ".join(t)) for d, t in sorted(holidays.items())],
    )


def campaign_out(code: str, r: dict[str, Any]) -> Campaign:
    return Campaign(
        id=r["id"],
        company=code,
        title_fa=r["title_fa"],
        goal_fa=r["goal_fa"],
        starts=r["starts"],
        ends=r["ends"],
        channels=list(r["channels"] or []),
        budget=None if r["budget"] is None else float(r["budget"]),
        state=r["state"],
    )
