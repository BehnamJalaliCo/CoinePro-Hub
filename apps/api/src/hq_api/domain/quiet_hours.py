"""⟨2026-11-26⟩ The owner: «هیچی مابین ساعت ۱۲ شب تا ۸ صبح به وقت تهران نباید منتشر بشه، چه استوری چه
ریلز چه شورت چه ویدیو بلند هیچی … ولی ساختشون ایرادی نداره». Nothing goes out between 00:00 and
08:00 Tehran, on any channel; making things in those hours is fine. Whatever would go out in the
night waits for the morning: OPEN_AT, a little after 08:00, as IG-Hub may move an item up to six
minutes either way."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")
QUIET_FROM = time(0, 0)  # the night starts at midnight …
QUIET_TO = time(8, 0)  # … and ends at 08:00 Tehran
OPEN_AT = time(8, 10)  # the first moment anything may go out (IG-Hub's ±6 min stays after 08:00)


def is_quiet(at: datetime) -> bool:
    """`at` falls in the night (Tehran)."""
    local = at.astimezone(TEHRAN).time()
    return QUIET_FROM <= local < OPEN_AT


def out_of_night(at: datetime) -> datetime:
    """`at` as it is, or, in the night, the same morning's OPEN_AT (Tehran), in UTC."""
    if not is_quiet(at):
        return at
    local = at.astimezone(TEHRAN)
    return datetime.combine(local.date(), OPEN_AT, tzinfo=TEHRAN).astimezone(UTC)


def night_between(start: datetime, end: datetime) -> timedelta:
    """How much of [start, end) was night: a post the night held is not late for those hours."""
    if end <= start:
        return timedelta(0)
    total = timedelta(0)
    day = start.astimezone(TEHRAN).date() - timedelta(days=1)
    last = end.astimezone(TEHRAN).date()
    while day <= last:
        a = datetime.combine(day, QUIET_FROM, tzinfo=TEHRAN)
        b = datetime.combine(day, OPEN_AT, tzinfo=TEHRAN)
        lo, hi = max(a, start), min(b, end)
        if hi > lo:
            total += hi - lo
        day += timedelta(days=1)
    return total
