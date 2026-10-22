"""The meetings' daily token share (prompt 11 §1.2, contract §20.1)."""

from __future__ import annotations

import pytest

from hq_common import meetings_share as S


def test_parse_share() -> None:
    assert S.parse_share(None) == S.parse_share("") == S.parse_share("  ") == 0.15
    assert S.DEFAULT_SHARE == 0.15
    assert S.parse_share("0.3") == 0.3 and S.parse_share("0") == 0.0 and S.parse_share("1") == 1.0
    for bad in ("-0.01", "1.01", "nan", "inf", "-inf", "a seventh"):
        with pytest.raises(ValueError) as exc:
            S.parse_share(bad)
        if bad != "a seventh":  # not a number at all: float()'s own message
            assert "MEETINGS_DAILY_SHARE must be a fraction between 0 and 1" in str(exc.value)


def test_limit_and_spent() -> None:
    assert S.limit(600_000, 0.15) == 90_000
    assert S.limit(0, 0.15) == 0 and S.limit(-5, 0.15) == 0  # a cap of 0 is nothing
    assert S.limit(1000, 7.0) == 1000 and S.limit(1000, -1.0) == 0
    assert not S.spent(89_999, 600_000, 0.15) and S.spent(90_000, 600_000, 0.15)
    assert S.spent(0, 0, 0.15)  # cap 0: spent before anything runs
    assert S.spent(0, 1000, 0.0)  # share 0: only the war room goes on
    assert S.WAR_ROOM == "war_room"
