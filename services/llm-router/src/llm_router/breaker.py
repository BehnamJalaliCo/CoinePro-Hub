"""Circuit breaker and quota guard for one connection.

closed -> open -> half_open (exactly ONE probe request) -> closed
                                   \\-> probe fails -> open (longer cooldown)

Two ways to open:
  - failures: `failure_threshold` consecutive errors/timeouts
  - quota:    the provider said the quota is used up; reopens at the reported
              reset time, or after a doubling backoff when none was reported

Hard rule (the TradeYar Claude Intel lock-up): an open breaker ALWAYS has
opened_at and retry_at. A state that would stay open forever cannot be built;
Snapshot enforces it on every transition and on restore from the database.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


STATE_VALUE = {State.CLOSED: 0, State.HALF_OPEN: 1, State.OPEN: 2}  # for metrics


@dataclass(frozen=True)
class Snapshot:
    state: State
    reason: str | None = None  # "failures" | "quota" while open/half-open
    opened_at: float | None = None
    retry_at: float | None = None
    consecutive_failures: int = 0
    probe_in_flight: bool = False

    def __post_init__(self) -> None:
        if self.state is State.OPEN and (
            self.opened_at is None or self.retry_at is None or self.retry_at < self.opened_at
        ):
            raise ValueError("an open breaker needs opened_at and retry_at >= opened_at")
        if self.state is State.CLOSED and self.probe_in_flight:
            raise ValueError("a closed breaker has no probe")


@dataclass(frozen=True)
class Permit:
    probe: bool


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        base_cooldown_s: float = 30.0,
        max_cooldown_s: float = 600.0,
        quota_backoff_s: float = 300.0,
        max_quota_backoff_s: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.base_cooldown_s = base_cooldown_s
        self.max_cooldown_s = max_cooldown_s
        self.base_quota_backoff_s = quota_backoff_s
        self.max_quota_backoff_s = max_quota_backoff_s
        self._clock = clock
        self._cooldown_s = base_cooldown_s
        self._quota_backoff_s = quota_backoff_s
        self._snap = Snapshot(State.CLOSED)

    # -- state ---------------------------------------------------------------
    @property
    def snapshot(self) -> Snapshot:
        return self._snap

    @property
    def state(self) -> State:
        return self._snap.state

    def _set(self, **changes: object) -> None:
        values = {**self._snap.__dict__, **changes}
        self._snap = Snapshot(**values)

    def _open(self, reason: str, retry_at: float) -> None:
        now = self._clock()
        self._set(
            state=State.OPEN,
            reason=reason,
            opened_at=now,
            retry_at=max(retry_at, now),
            probe_in_flight=False,
        )

    def _close(self) -> None:
        self._cooldown_s = self.base_cooldown_s
        self._quota_backoff_s = self.base_quota_backoff_s
        self._snap = Snapshot(State.CLOSED)

    def retry_after_s(self) -> int:
        """Seconds until the next probe may run (0 when not open)."""
        if self._snap.state is not State.OPEN or self._snap.retry_at is None:
            return 0
        return max(1, int(self._snap.retry_at - self._clock()) + 1)

    # -- requests ------------------------------------------------------------
    def allow(self) -> Permit | None:
        snap = self._snap
        if snap.state is State.CLOSED:
            return Permit(probe=False)
        if snap.state is State.OPEN:
            assert snap.retry_at is not None
            if self._clock() < snap.retry_at:
                return None
            self._set(state=State.HALF_OPEN, probe_in_flight=True)
            return Permit(probe=True)
        if snap.probe_in_flight:
            return None  # half-open: exactly one probe at a time
        self._set(probe_in_flight=True)
        return Permit(probe=True)

    def on_success(self, permit: Permit) -> None:
        if permit.probe or self._snap.state is State.CLOSED:
            self._close()

    def on_failure(self, permit: Permit) -> None:
        if permit.probe:
            self._cooldown_s = min(self._cooldown_s * 2, self.max_cooldown_s)
            self._open("failures", self._clock() + self._cooldown_s)
        elif self._snap.state is State.CLOSED:
            failures = self._snap.consecutive_failures + 1
            if failures >= self.failure_threshold:
                self._open("failures", self._clock() + self._cooldown_s)
            else:
                self._set(consecutive_failures=failures)

    def on_quota(self, permit: Permit | None, resets_at: float | None) -> None:
        now = self._clock()
        if resets_at is not None and resets_at > now:
            retry_at = resets_at
        else:
            retry_at = now + self._quota_backoff_s
            self._quota_backoff_s = min(self._quota_backoff_s * 2, self.max_quota_backoff_s)
        self._open("quota", retry_at)

    def release_probe(self, permit: Permit) -> None:
        """The probe ended without a verdict (cancelled): let another one try."""
        if permit.probe and self._snap.state is State.HALF_OPEN:
            self._set(probe_in_flight=False)

    def restore_quota(self, opened_at: float, retry_at: float | None) -> None:
        """Rebuild a quota-open breaker from the database after a restart."""
        if retry_at is None:
            retry_at = opened_at + self._quota_backoff_s
        self._snap = Snapshot(
            State.OPEN, reason="quota", opened_at=opened_at, retry_at=max(retry_at, opened_at)
        )
