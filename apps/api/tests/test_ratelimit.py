"""RateLimiter unit tests (no database or Temporal needed)."""

from __future__ import annotations

import pytest

from hq_api.errors import ApiError
from hq_api.ratelimit import RateLimiter


def test_limit_and_retry_after() -> None:
    rl = RateLimiter(window_s=60.0)
    rl.check("k", 2, now=0.0)
    rl.check("k", 2, now=1.0)
    with pytest.raises(ApiError) as exc:
        rl.check("k", 2, now=2.0)
    assert exc.value.status == 429
    rl.check("k", 2, now=60.5)  # the first hit has left the window


def test_idle_keys_are_forgotten() -> None:
    # Regression: deques are never empty after check(), so the old `if not v`
    # sweep deleted nothing and the dict grew without bound.
    rl = RateLimiter(window_s=60.0, max_keys=10, sweep_every=5)
    for i in range(20):
        rl.check(f"auth-ip:{i}", 5, now=float(i))
    assert len(rl._hits) == 20
    for i in range(5):
        rl.check(f"fresh:{i}", 5, now=1000.0)
    assert set(rl._hits) == {f"fresh:{i}" for i in range(5)}


def test_active_keys_survive_the_sweep() -> None:
    rl = RateLimiter(window_s=60.0, max_keys=2, sweep_every=1)
    rl.check("a", 5, now=0.0)
    rl.check("b", 5, now=30.0)
    rl.check("c", 5, now=59.0)
    assert set(rl._hits) == {"a", "b", "c"}
    rl.check("d", 5, now=61.0)
    assert set(rl._hits) == {"b", "c", "d"}
