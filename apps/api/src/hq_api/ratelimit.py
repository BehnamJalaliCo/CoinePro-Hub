"""In-process sliding-window rate limits (contract §1: 429 + Retry-After).

One api replica today; the interface stays the same if it moves to Valkey.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from hq_api.errors import ApiError


class RateLimiter:
    def __init__(
        self, window_s: float = 60.0, *, max_keys: int = 50_000, sweep_every: int = 1_000
    ) -> None:
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._max_keys = max_keys
        self._sweep_every = sweep_every
        self._calls = 0

    def check(self, key: str, limit: int, *, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and q[0] <= t - self._window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, math.ceil(q[0] + self._window - t))
            raise ApiError(429, "rate_limited", headers={"Retry-After": str(retry)})
        q.append(t)
        # Forget idle keys now and then, not on every call: the scan is O(keys).
        self._calls += 1
        if self._calls >= self._sweep_every:
            self._calls = 0
            if len(self._hits) > self._max_keys:
                self._forget_idle(t)

    def _forget_idle(self, t: float) -> None:
        # check() appends after popping, so a deque is rarely empty; a key is
        # idle once its newest hit has left the window.
        cutoff = t - self._window
        for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[k]
