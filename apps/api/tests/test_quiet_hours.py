"""⟨2026-11-26⟩ The owner: nothing goes out between 00:00 and 08:00 Tehran, on any channel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from hq_api.domain import flow_events as EV
from hq_api.domain import flows as FL
from hq_api.domain import quiet_hours as QH

T = ZoneInfo("Asia/Tehran")


def at(h: int, m: int = 0, day: int = 26) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=T).astimezone(UTC)


def test_the_night_is_midnight_to_eight_tehran() -> None:
    assert QH.is_quiet(at(0, 0)) and QH.is_quiet(at(0, 40)) and QH.is_quiet(at(7, 59))
    # IG-Hub moves an item up to 6 minutes, so the morning opens at 08:10
    assert QH.is_quiet(at(8, 5))
    assert not QH.is_quiet(at(8, 10)) and not QH.is_quiet(at(13, 0)) and not QH.is_quiet(at(23, 59))


def test_a_time_in_the_night_waits_for_the_morning() -> None:
    assert QH.out_of_night(at(0, 40)) == at(8, 10)
    assert QH.out_of_night(at(3, 0)) == at(8, 10)
    assert QH.out_of_night(at(22, 0)) == at(22, 0)
    # the night's hours never count as late
    assert QH.night_between(at(23, 50, 25), at(8, 20)) == timedelta(hours=8, minutes=10)
    assert QH.night_between(at(9, 0), at(12, 0)) == timedelta(0)


def test_a_breaking_reel_never_goes_out_in_the_night() -> None:
    flow = next(iter(FL.FLOWS.values()))
    got = EV.publish_at(flow, at(23, 0, 25), 100)  # 00:40 Tehran
    assert got.astimezone(T).hour == 8 and got.astimezone(T).minute == 30
    assert EV.publish_at(flow, at(10, 0), 100) == at(11, 40)
