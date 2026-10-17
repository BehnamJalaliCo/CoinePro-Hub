"""Watch the SDK's own cost estimate against our price table.

Our table is the source of every cost figure (owner decision, prompt 04 §9);
the SDK's `total_cost_usd` is kept only to notice when the two drift apart
(e.g. a CLI that prices an unknown model at another model's rates).

Per (connection, model): ratio = sum(sdk) / sum(ours) over a rolling window
(1 h). When the ratio stays above `threshold` (2x) for `hold` (1 h) without
dropping back, one alert is raised; it re-arms only after the ratio returns
to <= threshold. The state is judged at every observation (every call).
Alerts go to NATS `hq.alerts.llm.cost_ratio` (events.COST_RATIO_SUBJECT).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any


@dataclass
class _Series:
    samples: deque[tuple[datetime, Decimal, Decimal]] = field(default_factory=deque)
    above_since: datetime | None = None
    alerted: bool = False


class CostRatioWatch:
    def __init__(
        self,
        *,
        window: timedelta = timedelta(hours=1),
        hold: timedelta = timedelta(hours=1),
        threshold: Decimal = Decimal(2),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.window, self.hold, self.threshold, self._now = window, hold, threshold, now
        self._series: dict[tuple[str, str], _Series] = {}

    def ratio(self, connection: str, model: str) -> Decimal | None:
        s = self._series.get((connection, model))
        if s is None:
            return None
        ours = sum((o for _, _, o in s.samples), Decimal(0))
        if ours <= 0:
            return None
        return sum((k for _, k, _ in s.samples), Decimal(0)) / ours

    def observe(
        self, connection: str, model: str, sdk_cost: Decimal, our_cost: Decimal
    ) -> tuple[Decimal | None, dict[str, Any] | None]:
        """Record one call; returns (current ratio, alert payload or None)."""
        now = self._now()
        s = self._series.setdefault((connection, model), _Series())
        s.samples.append((now, sdk_cost, our_cost))
        while s.samples and s.samples[0][0] < now - self.window:
            s.samples.popleft()
        ratio = self.ratio(connection, model)
        if ratio is None or ratio <= self.threshold:
            s.above_since, s.alerted = None, False
            return ratio, None
        if s.above_since is None:
            s.above_since = now
        if s.alerted or now - s.above_since < self.hold:
            return ratio, None
        s.alerted = True
        return ratio, {
            "type": "llm.cost_ratio",
            "connection": connection,
            "model": model,
            "ratio": str(ratio.quantize(Decimal("0.01"))),
            "since": s.above_since.isoformat(),
            "window_minutes": int(self.window.total_seconds() // 60),
            "at": now.isoformat(),
        }
