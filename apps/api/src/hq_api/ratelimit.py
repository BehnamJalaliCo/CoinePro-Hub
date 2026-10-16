"""In-process sliding-window rate limits (contract §1: 429 + Retry-After).

One api replica today; the interface stays the same if it moves to Valkey.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from hq_api.errors import ApiError


class RateLimiter:
    def __init__(self, window_s: float = 60.0) -> None:
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, *, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and q[0] <= t - self._window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, math.ceil(q[0] + self._window - t))
            raise ApiError(429, "rate_limited", headers={"Retry-After": str(retry)})
        q.append(t)
        if len(self._hits) > 50_000:  # forget idle keys
            for k in [k for k, v in self._hits.items() if not v]:
                del self._hits[k]
