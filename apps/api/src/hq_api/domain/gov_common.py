"""Shared pieces of prompt 11 §4-§10 (the governance half): the owner's time
zone, Jalali quarters and months, a source reference, canonical hashes."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from hq_api.db import Tx
from hq_api.worker.jalali import to_jalali

DEFAULT_TZ = "Asia/Tehran"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
_NUMBER = re.compile(r"-?[0-9]+(?:[.,][0-9]+)?")
QUARTER = r"^1[3-9][0-9]{2}-Q[1-4]$"


class Source(BaseModel):
    """{kind, ref, note} (contract §16.3 citations, §20.4 source_ref)."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    ref: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=1000)


async def owner_tz(tx: Tx) -> str:
    return str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or DEFAULT_TZ)


def zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def local_midnight(d: date, tz: str) -> datetime:
    return datetime.combine(d, time.min, zone(tz)).astimezone(UTC)


def from_jalali(jy: int, jm: int, jd: int) -> date:
    """The Gregorian date of a Jalali date (searched around 1 Farvardin)."""
    start = date(jy + 621, 3, 14)
    for i in range(380):
        d = start + timedelta(days=i)
        if to_jalali(d) == (jy, jm, jd):
            return d
    raise ValueError(f"no Jalali date {jy}-{jm}-{jd}")


def quarter_of(d: date) -> str:
    """1405-Q3 = Mehr to Azar."""
    jy, jm, _ = to_jalali(d)
    return f"{jy}-Q{(jm - 1) // 3 + 1}"


def quarter_bounds(quarter: str) -> tuple[date, date]:
    """[first day, first day of the next quarter)."""
    jy, q = int(quarter[:4]), int(quarter[-1])
    start = from_jalali(jy, 3 * (q - 1) + 1, 1)
    end = from_jalali(jy + 1, 1, 1) if q == 4 else from_jalali(jy, 3 * q + 1, 1)
    return start, end


def next_quarter(quarter: str) -> str:
    jy, q = int(quarter[:4]), int(quarter[-1])
    return f"{jy + 1}-Q1" if q == 4 else f"{jy}-Q{q + 1}"


def jalali_month_start(d: date) -> date:
    _, _, day = to_jalali(d)
    return d - timedelta(days=day - 1)


def today(tz: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(zone(tz)).date()


def number(text: Any) -> float | None:
    """The first number in a text (Persian or Latin digits), else None."""
    if isinstance(text, bool):
        return None
    if isinstance(text, int | float | Decimal):
        return float(text)
    m = _NUMBER.search(str(text or "").translate(_DIGITS))
    return float(m.group(0).replace(",", ".")) if m else None


def canonical_json(value: Any) -> str:
    """Sorted keys, no spaces, UTF-8 as is (the step-up targets' form)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def num(value: Any) -> float | None:
    return None if value is None else float(value)
