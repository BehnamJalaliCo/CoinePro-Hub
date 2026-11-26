"""⟨2026-11-26⟩ The owner for @bitmart: a new posting hour every day, from five, in no order."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from hq_api.domain import flows as FL

HOURS = ("12:40", "14:55", "17:20", "19:45", "22:10")


def _flow(rotate: str = "day_shuffle") -> FL.Flow:
    base = next(iter(FL.FLOWS.values()))
    return replace(base, key="bitmart_reels", start=date(2026, 11, 27), hours=HOURS, rotate=rotate)


def test_every_round_uses_each_hour_once_in_a_shuffled_order() -> None:
    f = _flow()
    seen_orders = set()
    for k in range(12):
        days = [f.start + timedelta(days=k * 5 + i) for i in range(5)]
        idx = [FL.hour_index(f, d) for d in days]
        assert sorted(idx) == [0, 1, 2, 3, 4]
        seen_orders.add(tuple(idx))
    assert len(seen_orders) > 3  # not one fixed order
    assert (0, 1, 2, 3, 4) not in seen_orders or len(seen_orders) > 1


def test_never_the_same_hour_two_days_running() -> None:
    f = _flow()
    prev = None
    for d in range(300):
        i = FL.hour_index(f, f.start + timedelta(days=d))
        assert i != prev
        prev = i


def test_the_same_day_always_gets_the_same_hour() -> None:
    f = _flow()
    day = f.start + timedelta(days=17)
    assert FL.hour_index(f, day) == FL.hour_index(f, day)


def test_without_rotate_the_hour_follows_the_week() -> None:
    f = _flow(rotate="")
    day = f.start + timedelta(days=8)
    assert FL.hour_index(f, day) == FL.week_of(f, day)
