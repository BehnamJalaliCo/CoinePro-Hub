"""The oversight token share (prompt 08 §2.3)."""

from __future__ import annotations

import pytest

from hq_common import oversight_share as S


def test_parse_share() -> None:
    assert S.parse_share(None) == S.parse_share("") == S.parse_share("  ") == 0.2
    assert S.parse_share("0.35") == 0.35 and S.parse_share("0") == 0.0 and S.parse_share("1") == 1.0
    for bad in ("-0.1", "1.5", "nan", "inf", "a fifth"):
        with pytest.raises(ValueError):
            S.parse_share(bad)


def test_limit_and_spent() -> None:
    assert S.limit(600_000, 0.2) == 120_000
    assert S.limit(0, 0.2) == 0  # a daily cap of 0 is nothing: no share either
    assert S.limit(1000, 7.0) == 1000 and S.limit(1000, -1.0) == 0
    assert not S.spent(119_999, 600_000, 0.2) and S.spent(120_000, 600_000, 0.2)
    assert S.spent(0, 0, 0.2)  # cap 0: spent before anything runs
    assert S.spent(0, 1000, 0.0)  # share 0: only critical protocols run
    assert S.ROLES == ("overseer", "inspector") and S.CRITICAL == "critical"
