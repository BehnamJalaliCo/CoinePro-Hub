"""Budgets: token and USD limits per scope and period (day/month, UTC).

Before every call the router checks every budget on the call's scopes:
  - 70% and 90%: alert event (once per level per period)
  - 100%: P4 (background) is rejected (rejected_budget); P0-P3 still run
    and alert. USD counts real API spend plus, for subscription calls, the
    SDK's equivalent cost (a proxy for quota consumption).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

THRESHOLDS = (70, 90, 100)
BACKGROUND_PRIORITY = 4


@dataclass(frozen=True)
class Budget:
    id: str
    company_id: str
    scope_type: str
    scope_ref: str
    period: str  # "day" | "month"
    token_limit: int | None
    usd_limit: Decimal | None
    alert_level: int = 0
    alert_period_start: date | None = None


@dataclass(frozen=True)
class Consumption:
    tokens: int = 0
    usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class Check:
    budget: Budget
    used: Consumption
    percent: float
    level: int  # 0, 70, 90 or 100


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after_s: int | None
    exhausted: tuple[Check, ...]
    alerts: tuple[Check, ...]  # checks whose level is new for this period


def period_start(period: str, now: datetime) -> date:
    d = now.astimezone(UTC).date()
    if period == "day":
        return d
    if period == "month":
        return d.replace(day=1)
    raise ValueError(f"unknown period {period!r}")


def next_period_start(period: str, now: datetime) -> datetime:
    start = period_start(period, now)
    if period == "day":
        nxt = start + timedelta(days=1)
    else:
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=UTC)


def percent_used(budget: Budget, used: Consumption) -> float:
    pcts = [0.0]
    if budget.token_limit:
        pcts.append(100.0 * used.tokens / budget.token_limit)
    if budget.usd_limit:
        pcts.append(float(100 * used.usd / budget.usd_limit))
    return max(pcts)


def level_for(percent: float) -> int:
    reached = [t for t in THRESHOLDS if percent >= t]
    return reached[-1] if reached else 0


def check(budget: Budget, used: Consumption) -> Check:
    pct = percent_used(budget, used)
    return Check(budget, used, round(pct, 2), level_for(pct))


def decide(priority: int, checks: list[Check], now: datetime) -> Decision:
    exhausted = tuple(c for c in checks if c.level >= 100)
    alerts = tuple(
        c
        for c in checks
        if c.level > 0
        and (
            c.budget.alert_period_start != period_start(c.budget.period, now)
            or c.level > c.budget.alert_level
        )
    )
    if exhausted and priority >= BACKGROUND_PRIORITY:
        # Blocked until every exhausted budget has rolled over.
        reset = max(next_period_start(c.budget.period, now) for c in exhausted)
        retry = max(1, int((reset - now).total_seconds()))
        return Decision(False, retry, exhausted, alerts)
    return Decision(True, None, exhausted, alerts)
