"""Recurring work schedules: an RRULE (RFC 5545) subset that maps exactly
onto a Temporal Schedule calendar spec in the schedule's time zone, plus
occurrence expansion for the planner and the first run.

Supported: FREQ=HOURLY|DAILY|WEEKLY|MONTHLY, BYDAY (weekly), BYMONTHDAY
(monthly), BYHOUR, BYMINUTE, UNTIL, and INTERVAL only for HOURLY with a
divisor of 24 (so every day restarts at local midnight, like the calendar
spec). Missing parts get explicit defaults: BYMINUTE=0; BYHOUR=9 (daily,
weekly, monthly); BYDAY=MO (weekly); BYMONTHDAY=1 (monthly). Anything else
is rejected with a clear error instead of a silently different schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

from hq_api.errors import ApiError

DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
FREQS = ("HOURLY", "DAILY", "WEEKLY", "MONTHLY")
ALLOWED = {"FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYHOUR", "BYMINUTE", "UNTIL"}


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int
    by_day: tuple[int, ...]  # 0 = Monday
    by_month_day: tuple[int, ...]
    by_hour: tuple[int, ...]
    by_minute: tuple[int, ...]
    until: datetime | None

    def rrule(self) -> str:
        """The normalised rule (stored, and what the planner expands)."""
        parts = [f"FREQ={self.freq}"]
        if self.interval > 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.by_day:
            parts.append("BYDAY=" + ",".join(DAYS[d] for d in self.by_day))
        if self.by_month_day:
            parts.append("BYMONTHDAY=" + ",".join(map(str, self.by_month_day)))
        if self.by_hour:
            parts.append("BYHOUR=" + ",".join(map(str, self.by_hour)))
        parts.append("BYMINUTE=" + ",".join(map(str, self.by_minute)))
        if self.until:
            parts.append("UNTIL=" + self.until.strftime("%Y%m%dT%H%M%SZ"))
        return ";".join(parts)


def _bad(why: str) -> ApiError:
    return ApiError(422, "validation_failed", fields={"schedule.rrule": why})


def _ints(value: str, lo: int, hi: int, name: str) -> tuple[int, ...]:
    try:
        out = tuple(sorted({int(v) for v in value.split(",")}))
    except ValueError as exc:
        raise _bad(f"{name} must be numbers") from exc
    if not out or out[0] < lo or out[-1] > hi:
        raise _bad(f"{name} out of range {lo}..{hi}")
    return out


def parse(rrule: str) -> Rule:
    text = rrule.strip().removeprefix("RRULE:")
    parts: dict[str, str] = {}
    for item in filter(None, text.split(";")):
        if "=" not in item:
            raise _bad("expected KEY=VALUE pairs separated by ';'")
        k, v = item.split("=", 1)
        k = k.strip().upper()
        if k not in ALLOWED:
            raise _bad(f"{k} is not supported")
        parts[k] = v.strip().upper()
    freq = parts.get("FREQ", "")
    if freq not in FREQS:
        raise _bad(f"FREQ must be one of {', '.join(FREQS)}")
    interval = _ints(parts.get("INTERVAL", "1"), 1, 24, "INTERVAL")[0]
    if interval > 1 and (freq != "HOURLY" or 24 % interval):
        raise _bad("INTERVAL is supported only for HOURLY, as a divisor of 24")
    by_day: tuple[int, ...] = ()
    if freq == "WEEKLY":
        try:
            by_day = tuple(sorted({DAYS.index(d) for d in parts.get("BYDAY", "MO").split(",")}))
        except ValueError as exc:
            raise _bad("BYDAY takes MO..SU without ordinals") from exc
    elif "BYDAY" in parts:
        raise _bad("BYDAY only with FREQ=WEEKLY")
    by_month_day: tuple[int, ...] = ()
    if freq == "MONTHLY":
        by_month_day = _ints(parts.get("BYMONTHDAY", "1"), 1, 28, "BYMONTHDAY")
    elif "BYMONTHDAY" in parts:
        raise _bad("BYMONTHDAY only with FREQ=MONTHLY")
    if freq == "HOURLY":
        if "BYHOUR" in parts:
            raise _bad("BYHOUR is not used with FREQ=HOURLY")
        by_hour: tuple[int, ...] = ()
    else:
        by_hour = _ints(parts.get("BYHOUR", "9"), 0, 23, "BYHOUR")
    by_minute = _ints(parts.get("BYMINUTE", "0"), 0, 59, "BYMINUTE")
    until = None
    if "UNTIL" in parts:
        try:
            until = datetime.strptime(parts["UNTIL"].rstrip("Z"), "%Y%m%dT%H%M%S").replace(
                tzinfo=UTC
            )
        except ValueError as exc:
            raise _bad("UNTIL must be YYYYMMDDTHHMMSSZ") from exc
    return Rule(freq, interval, by_day, by_month_day, by_hour, by_minute, until)


def zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(
            422, "validation_failed", fields={"schedule.timezone": "unknown time zone"}
        ) from exc


def occurrences(
    rule: Rule, tz: str, start: datetime, end: datetime, *, limit: int = 1000
) -> list[datetime]:
    """Occurrences in [start, end) as UTC datetimes (wall-clock times in `tz`)."""
    z = zone(tz)
    # Start the expansion at local midnight the day before: every supported
    # rule restarts daily (or is pinned to weekdays/month days), so the
    # result does not depend on when it is computed.
    day0 = start.astimezone(z).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=1
    )
    raw = rule.rrule()
    if rule.until:
        raw = raw.replace("UNTIL=" + rule.until.strftime("%Y%m%dT%H%M%SZ"), "")
        raw = raw.rstrip(";")
    out: list[datetime] = []
    for local in rrulestr(raw, dtstart=day0.replace(tzinfo=None)):
        at = local.replace(tzinfo=z).astimezone(UTC)
        if rule.until and at > rule.until:
            break
        if at < start:
            continue
        if at >= end or len(out) >= limit:
            break
        out.append(at)
    return out


def next_at(rule: Rule, tz: str, after: datetime | None = None) -> datetime | None:
    start = after or datetime.now(UTC)
    found = occurrences(rule, tz, start, start + timedelta(days=62), limit=1)
    return found[0] if found else None
