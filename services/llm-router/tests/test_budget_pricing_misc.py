from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from llm_router import anomaly, budget
from llm_router.budget import Budget, Consumption
from llm_router.pricing import Usage, cost_usd
from llm_router.uuid7 import uuid7

NOW = datetime(2026, 10, 16, 15, 30, tzinfo=UTC)


def b(**kw: object) -> Budget:
    base: dict[str, object] = {
        "id": "b1",
        "company_id": "ty",
        "scope_type": "company",
        "scope_ref": "TY",
        "period": "day",
        "token_limit": 1000,
        "usd_limit": None,
    }
    base.update(kw)
    return Budget(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("tokens", "level"),
    [(0, 0), (699, 0), (700, 70), (899, 70), (900, 90), (999, 90), (1000, 100), (5000, 100)],
)
def test_levels(tokens: int, level: int) -> None:
    assert budget.check(b(), Consumption(tokens=tokens)).level == level


def test_usd_limit_and_worst_of_both() -> None:
    bb = b(token_limit=1000, usd_limit=Decimal("10"))
    c = budget.check(bb, Consumption(tokens=100, usd=Decimal("9.5")))
    assert c.level == 90 and c.percent == 95.0


def test_p4_rejected_at_100_with_retry_after_until_next_period() -> None:
    day = budget.check(b(), Consumption(tokens=1000))
    d = budget.decide(4, [day], NOW)
    assert not d.allowed and d.exhausted == (day,)
    assert d.retry_after_s == int((datetime(2026, 10, 17, tzinfo=UTC) - NOW).total_seconds())
    month = budget.check(b(id="m", period="month"), Consumption(tokens=2000))
    d2 = budget.decide(4, [day, month], NOW)
    assert d2.retry_after_s == int((datetime(2026, 11, 1, tzinfo=UTC) - NOW).total_seconds())


@pytest.mark.parametrize("priority", [0, 1, 2, 3])
def test_p0_to_p3_run_at_100_and_alert(priority: int) -> None:
    c = budget.check(b(), Consumption(tokens=1500))
    d = budget.decide(priority, [c], NOW)
    assert d.allowed and d.retry_after_s is None
    assert d.alerts == (c,) and d.exhausted == (c,)


def test_alerts_once_per_level_per_period() -> None:
    today = date(2026, 10, 16)
    at70 = b(alert_level=70, alert_period_start=today)
    assert budget.decide(2, [budget.check(at70, Consumption(tokens=750))], NOW).alerts == ()
    crossed = budget.decide(2, [budget.check(at70, Consumption(tokens=950))], NOW)
    assert [c.level for c in crossed.alerts] == [90]
    stale = b(alert_level=90, alert_period_start=date(2026, 10, 15))  # yesterday's alert
    assert [
        c.level
        for c in budget.decide(2, [budget.check(stale, Consumption(tokens=750))], NOW).alerts
    ] == [70]
    assert budget.decide(2, [budget.check(b(), Consumption(tokens=10))], NOW).alerts == ()


def test_periods() -> None:
    assert budget.period_start("month", NOW) == date(2026, 10, 1)
    assert budget.next_period_start("month", datetime(2026, 12, 31, 23, tzinfo=UTC)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )
    with pytest.raises(ValueError):
        budget.period_start("week", NOW)


def test_pricing_per_million() -> None:
    pricing = {
        "claude-haiku-5-5": {
            "input": 0.10,
            "output": 0.50,
            "cache_read": 0.01,
            "cache_write": 0.125,
        }
    }
    u = Usage(
        input_tokens=1_000_000,
        output_tokens=2_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=8,
    )
    assert cost_usd(pricing, "claude-haiku-5-5", u) == Decimal("1.110001")
    assert cost_usd(pricing, "unknown", u) is None
    assert u.total == 4_000_008


def test_uuid7_layout_and_order() -> None:
    a, c = uuid7(1_700_000_000_000), uuid7(1_700_000_000_001)
    assert a.version == 7 and a.variant == "specified in RFC 4122"
    assert a.int >> 80 == 1_700_000_000_000
    assert a < c
    assert uuid7().version == 7


def test_anomaly_rule() -> None:
    quiet = [1] * 20  # 20 active hours of 1 call, the rest 0 -> median 0
    assert anomaly.is_anomalous(30, quiet) == (False, 30.0)
    assert anomaly.is_anomalous(31, quiet)[0]
    busy = [100] * 168  # steady 100/hour -> threshold 300
    assert anomaly.is_anomalous(300, busy) == (False, 300.0)
    assert anomaly.is_anomalous(301, busy)[0]
