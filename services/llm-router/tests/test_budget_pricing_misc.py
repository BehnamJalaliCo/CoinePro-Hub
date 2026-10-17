import importlib.util
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from llm_router import anomaly, budget
from llm_router.budget import Budget, Consumption
from llm_router.cost_ratio import CostRatioWatch
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


ROUTER_DIR = Path(__file__).resolve().parents[1]


def _seed_pricing() -> dict[str, object]:
    data = yaml.safe_load((ROUTER_DIR / "seed" / "connections.yaml").read_text())
    pricing: dict[str, object] = next(
        c["pricing"] for c in data["connections"] if c["key"] == "claude-max"
    )
    return pricing


def test_official_prices_tiers_and_one_hour_writes() -> None:
    pricing = _seed_pricing()
    for model in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"):
        entry = pricing[model]
        assert isinstance(entry, dict)
        assert entry["source_url"].startswith("https://platform.claude.com/")
        assert entry["as_of"] == "2026-10-17"  # re-checked on the official page (prompt 04.1)
    # The real smoke call of prompt 03: 2 in, 4 out, 525 cache writes (5-minute).
    smoke = Usage(input_tokens=2, output_tokens=4, cache_write_tokens=525)
    assert cost_usd(pricing, "claude-haiku-5-5", smoke) == Decimal("0.000068")
    # The same writes with the 1-hour TTL cost 0.20 instead of 0.125 per 1M.
    one_hour = Usage(
        input_tokens=2, output_tokens=4, cache_write_tokens=525, cache_write_1h_tokens=525
    )
    assert cost_usd(pricing, "claude-haiku-5-5", one_hour) == Decimal("0.000107")
    # A prompt over 100,000 tokens pays every long-prompt rate (cache reads count).
    long = Usage(input_tokens=60_000, output_tokens=1_000, cache_read_tokens=50_000)
    assert cost_usd(pricing, "claude-haiku-5-5", long) == Decimal("0.035000")
    at_limit = Usage(input_tokens=50_000, output_tokens=1_000, cache_read_tokens=50_000)
    assert cost_usd(pricing, "claude-haiku-5-5", at_limit) == Decimal("0.006000")
    # A 1h count larger than the writes never prices more than the writes.
    odd = Usage(cache_write_tokens=10, cache_write_1h_tokens=99)
    assert cost_usd(pricing, "claude-sonnet-5-5", odd) == Decimal("0.000040")
    # No 1-hour rate: 1-hour writes are priced as 5-minute writes.
    no_1h_rate = {"m": {"input": 1, "output": 1, "cache_write": 2}}
    assert cost_usd(no_1h_rate, "m", odd) == Decimal("0.000020")
    assert cost_usd({"m": {"input": 1}}, "m", smoke) is None  # incomplete entry


def test_latest_price_migration_matches_the_seed() -> None:
    path = ROUTER_DIR / "migrations" / "versions" / "0006_prices_reverified.py"
    spec = importlib.util.spec_from_file_location("m0006", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert _seed_pricing() == module.PRICES


def test_cost_ratio_alert_after_one_hour_and_rearm() -> None:
    t = [datetime(2026, 10, 16, 8, 0, tzinfo=UTC)]
    watch = CostRatioWatch(now=lambda: t[0])

    def step(minutes: int, sdk: str, ours: str) -> tuple[Decimal | None, dict[str, object] | None]:
        t[0] += timedelta(minutes=minutes)
        return watch.observe("claude-max", "claude-haiku-5-5", Decimal(sdk), Decimal(ours))

    assert step(0, "0.001", "0.001") == (Decimal(1), None)
    ratio, alert = step(1, "0.010", "0.001")  # 0.011 / 0.002 = 5.5: above since now
    assert ratio == Decimal("5.5") and alert is None
    assert step(30, "0.003", "0.001")[1] is None  # 30 min above: not yet
    ratio, alert = step(30, "0.003", "0.001")  # 60 min above: one alert
    assert alert is not None and alert["type"] == "llm.cost_ratio"
    assert alert["window_minutes"] == 60 and alert["since"] == "2026-10-16T08:01:00+00:00"
    assert alert["ratio"] == "5.33"  # 0.016 / 0.003: the 08:00 sample left the window
    assert step(5, "0.003", "0.001")[1] is None  # still above: no repeat
    assert step(5, "0.000", "0.010")[1] is None  # back below 2: re-armed
    assert step(1, "0.500", "0.001")[1] is None  # above again: the hour starts over
    assert step(61, "0.500", "0.001")[1] is not None
    # No priced cost in the window: no ratio, nothing to judge.
    assert watch.ratio("claude-max", "other") is None
    assert watch.observe("claude-max", "free", Decimal("0.1"), Decimal(0)) == (None, None)


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
