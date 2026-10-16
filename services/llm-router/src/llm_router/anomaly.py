"""Simple usage-anomaly rule (the lesson of TradeYar's 20k calls/day):

an actor_ref is anomalous when its calls in the current hour exceed
`factor` x the median of its hourly calls over the previous 7 days (hours
without calls count as 0), and at least `min_calls`.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable

HOURS_7D = 7 * 24


def threshold(hourly_counts: Iterable[int], *, factor: float, min_calls: int) -> float:
    counts = list(hourly_counts)
    counts += [0] * max(0, HOURS_7D - len(counts))
    return max(float(min_calls), factor * statistics.median(counts))


def is_anomalous(
    current_hour_calls: int,
    hourly_counts: Iterable[int],
    *,
    factor: float = 3.0,
    min_calls: int = 30,
) -> tuple[bool, float]:
    limit = threshold(hourly_counts, factor=factor, min_calls=min_calls)
    return current_hour_calls > limit, limit
