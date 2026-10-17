"""Gregorian -> Jalali (Solar Hijri) dates for the owner's reports.

The arithmetic 33-year-cycle algorithm (as in the widely used jalaali
conversion); exact for the years the hub will ever report on (it agrees
with the official calendar from 1178 to 1633 SH).
"""

from __future__ import annotations

from datetime import date

_G_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
MONTHS_FA = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)


def to_jalali(d: date) -> tuple[int, int, int]:
    gy, gm, gd = d.year, d.month, d.day
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + _G_DAYS_BEFORE_MONTH[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def jalali_str(d: date) -> str:
    y, m, day = to_jalali(d)
    return f"{y:04d}/{m:02d}/{day:02d}"


def jalali_long(d: date) -> str:
    y, m, day = to_jalali(d)
    return f"{day} {MONTHS_FA[m - 1]} {y}"
