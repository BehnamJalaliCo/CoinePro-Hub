"""One campaign calendar (contract §31.5 ⟨1.13⟩).

`GET /campaign-calendar` merges what is planned to go out, from every source, into
one list of `CalendarItem`s and marks the conflicts by code:

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

from pydantic import Field

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


class CalendarItem(Model):
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
    items: list[CalendarItem]
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
    at: datetime | None = None
    title_fa: str = Field(min_length=1, max_length=200)
    platform: str | None = Field(default=None, pattern=PLATFORM)


class ManualPut(Model):
    day: date | None = None
    at: datetime | None = None
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


def check_window(start: date, to: date) -> None:
    if to < start:
        raise ApiError(422, "validation_failed", fields={"to": "not before from"})
    if (to - start).days > MAX_SPAN_DAYS:
        raise ApiError(422, "validation_failed", fields={"to": f"at most {MAX_SPAN_DAYS} days"})


def mark_conflicts(
    items: list[CalendarItem], spacing_min: int, holidays: dict[date, list[str]]
) -> None:
    """Fill `conflict_fa` in place. Spacing: items of one company and platform with a
    time, closer than `spacing_min`; both are marked. Holiday: any item that publishes
    (not a campaign's span) on a holiday."""
    gap = timedelta(minutes=spacing_min)
    groups: dict[tuple[str, str], list[CalendarItem]] = {}
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
    [Tx, datetime, datetime, str, UUID | None, dict[UUID, str]], Awaitable[list[CalendarItem]]
]


def _day(at: datetime, tz: str) -> date:
    return at.astimezone(zone(tz)).date()


async def _optional(tx: Tx, table: str) -> bool:
    return bool(await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table))


async def _manual(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CalendarItem]:
    rows = await tx.all(
        "SELECT * FROM growth.calendar_manual WHERE day BETWEEN :a AND :b "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        a=_day(lo, tz),
        b=_day(hi, tz),
        co=co,
    )
    return [
        CalendarItem(
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
) -> list[CalendarItem]:
    a, b = _day(lo, tz), _day(hi, tz)
    rows = await tx.all(
        "SELECT * FROM growth.campaigns WHERE starts <= :b AND ends >= :a "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        a=a,
        b=b,
        co=co,
    )
    return [
        CalendarItem(
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
) -> list[CalendarItem]:
    rows = await tx.all(
        "SELECT * FROM growth.newsletter_campaigns WHERE send_at >= :lo AND send_at < :hi "
        "AND (CAST(:co AS uuid) IS NULL OR company_id = :co)",
        lo=lo,
        hi=hi,
        co=co,
    )
    return [
        CalendarItem(
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
) -> list[CalendarItem]:
    """The engine's runs (§30). Its tables are another part's: if they are not there,
    or are shaped differently, the source gives nothing."""
    if not (await _optional(tx, "lines.runs") and await _optional(tx, "lines.lines")):
        return []
    try:
        async with tx.conn.begin_nested():
            rows = await tx.all(
                """SELECT r.ref AS run_ref, r.state, r.at, l.company_id, l.platform, l.title_fa
                   FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id
                   WHERE r.at >= :lo AND r.at < :hi AND (CAST(:co AS uuid) IS NULL OR l.company_id = :co)""",
                lo=lo,
                hi=hi,
                co=co,
            )
    except Exception:
        log.info("the lines tables look different; the line source is skipped", exc_info=True)
        return []
    return [
        CalendarItem(
            day=_day(r["at"], tz),
            at=r["at"],
            company=codes.get(r["company_id"], "-"),
            kind="line",
            ref=str(r["run_ref"]),
            title_fa=str(r["title_fa"]),
            platform=r["platform"],
            state=str(r["state"]),
        )
        for r in rows
        if str(r["state"]) not in LINE_SKIP
    ]


async def _ads(
    tx: Tx, lo: datetime, hi: datetime, tz: str, co: UUID | None, codes: dict[UUID, str]
) -> list[CalendarItem]:
    """Ad campaigns that spent in the window (the ads part's growth.ad_daily), optional."""
    if not await _optional(tx, "growth.ad_daily"):
        return []
    try:
        async with tx.conn.begin_nested():
            rows = await tx.all(
                """SELECT company_id, platform, campaign_id, min(day) AS first_day, max(day) AS last_day
                   FROM growth.ad_daily WHERE day BETWEEN :a AND :b
                     AND (CAST(:co AS uuid) IS NULL OR company_id = :co)
                   GROUP BY company_id, platform, campaign_id""",
                a=_day(lo, tz),
                b=_day(hi, tz),
                co=co,
            )
    except Exception:
        log.info("the ads tables look different; the ad source is skipped", exc_info=True)
        return []
    return [
        CalendarItem(
            day=r["first_day"],
            at=None,
            company=codes.get(r["company_id"], "-"),
            kind="ad",
            ref=f"{r['platform']}:{r['campaign_id']}",
            title_fa=f"تبلیغ {r['platform']} · {r['campaign_id']}",
            platform=None,
            state="running",
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
    items: list[CalendarItem] = []
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
