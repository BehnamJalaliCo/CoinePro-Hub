"""⟨2026-11-09⟩ F-0014: the media director's series.propose was refused three times in a row
(unknown check names, the schedule, an account and topics written as people write them). The
shapes an agent naturally writes are read as meant; a real mistake is still refused by field."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from hq_api.routes.media import CHECK_NAMES, SeriesProposeIn


def _series(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "company": "PC",
        "title_fa": "ریلز روزانه‌ی پروچارت",
        "kind": "reel",
        "targets": [
            {"channel": "instagram", "account": "theprochart", "placement": "instagram_reel"}
        ],
        "schedule": "FREQ=DAILY;BYHOUR=10;BYMINUTE=0",
        "format": {"aspect": "9:16", "duration_s": 30},
    }
    return {**base, **over}


def test_the_shapes_an_agent_writes_are_read_as_meant() -> None:
    s = SeriesProposeIn.model_validate(
        _series(
            targets=[
                {"channel": "instagram", "account": " @TheProChart ", "placement": "instagram_reel"}
            ],
            topics=["ATR", "RSI", "حمایت و مقاومت"],
            checks=["Brand", "accuracy", "QC"],
        )
    )
    assert s.targets[0].account == "theprochart"
    assert s.topics is not None and s.topics.pool == ["ATR", "RSI", "حمایت و مقاومت"]
    assert s.checks == list(CHECK_NAMES)  # an unknown check: all seven, never fewer
    kept = SeriesProposeIn.model_validate(_series(checks=["brand", "qc"]))
    assert kept.checks == ["brand", "qc"]


def test_a_real_mistake_is_still_refused_by_its_field() -> None:
    with pytest.raises(ValidationError) as exc:
        SeriesProposeIn.model_validate(_series(kind="podcast"))
    assert exc.value.errors()[0]["loc"] == ("kind",)
    with pytest.raises(ValidationError):
        SeriesProposeIn.model_validate(
            _series(targets=[{"channel": "x", "account": "a b", "placement": "instagram_reel"}])
        )
