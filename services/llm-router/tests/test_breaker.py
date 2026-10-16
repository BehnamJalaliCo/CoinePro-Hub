import pytest

from llm_router.breaker import CircuitBreaker, Permit, Snapshot, State


class Clock:
    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t


def make(clock: Clock) -> CircuitBreaker:
    return CircuitBreaker(
        "c",
        failure_threshold=3,
        base_cooldown_s=30,
        max_cooldown_s=100,
        quota_backoff_s=60,
        max_quota_backoff_s=200,
        clock=clock,
    )


def test_open_breaker_without_start_time_is_impossible() -> None:
    with pytest.raises(ValueError):
        Snapshot(State.OPEN, reason="quota")
    with pytest.raises(ValueError):
        Snapshot(State.OPEN, reason="quota", opened_at=10.0, retry_at=5.0)
    with pytest.raises(ValueError):
        Snapshot(State.CLOSED, probe_in_flight=True)


def test_opens_after_threshold_then_single_probe_closes() -> None:
    clock = Clock()
    b = make(clock)
    for _ in range(2):
        p = b.allow()
        assert p is not None and not p.probe
        b.on_failure(p)
    assert b.state is State.CLOSED
    b.on_failure(b.allow() or Permit(False))
    snap = b.snapshot
    assert snap.state is State.OPEN and snap.reason == "failures"
    assert snap.opened_at == 1_000.0 and snap.retry_at == 1_030.0
    assert b.allow() is None
    assert b.retry_after_s() == 31
    clock.t = 1_030.0
    probe = b.allow()
    assert probe is not None and probe.probe
    assert b.state is State.HALF_OPEN
    assert b.allow() is None  # exactly one probe in half-open
    b.on_success(probe)
    assert b.state is State.CLOSED
    assert b.retry_after_s() == 0


def test_failed_probe_reopens_with_longer_cooldown() -> None:
    clock = Clock()
    b = make(clock)
    for _ in range(3):
        b.on_failure(b.allow() or Permit(False))
    clock.t += 30
    probe = b.allow()
    assert probe is not None
    b.on_failure(probe)
    snap = b.snapshot
    assert snap.state is State.OPEN and snap.retry_at == clock.t + 60
    clock.t += 60
    probe = b.allow()
    assert probe is not None
    b.on_failure(probe)
    assert b.snapshot.retry_at == clock.t + 100  # capped at max_cooldown_s


def test_success_resets_failure_count_and_late_results_are_ignored() -> None:
    clock = Clock()
    b = make(clock)
    early = b.allow()
    assert early is not None
    b.on_failure(b.allow() or Permit(False))
    b.on_success(b.allow() or Permit(False))
    assert b.snapshot.consecutive_failures == 0
    for _ in range(3):
        b.on_failure(b.allow() or Permit(False))
    assert b.state is State.OPEN
    b.on_failure(early)  # a non-probe result arriving late does not move an open breaker
    b.on_success(early)
    assert b.state is State.OPEN


def test_quota_uses_reported_reset_time() -> None:
    clock = Clock()
    b = make(clock)
    b.on_quota(b.allow(), resets_at=5_000.0)
    snap = b.snapshot
    assert (snap.state, snap.reason, snap.opened_at, snap.retry_at) == (
        State.OPEN,
        "quota",
        1_000.0,
        5_000.0,
    )
    clock.t = 4_999.0
    assert b.allow() is None
    clock.t = 5_000.0
    probe = b.allow()
    assert probe is not None and probe.probe
    b.on_success(probe)
    assert b.state is State.CLOSED


def test_quota_without_reset_time_backs_off_and_doubles() -> None:
    clock = Clock()
    b = make(clock)
    b.on_quota(None, resets_at=None)
    assert b.snapshot.retry_at == 1_060.0
    clock.t = 1_060.0
    probe = b.allow()
    assert probe is not None
    b.on_quota(probe, resets_at=None)
    assert b.snapshot.retry_at == 1_060.0 + 120
    clock.t += 120
    b.on_quota(b.allow(), resets_at=100.0)  # a reset time in the past is ignored
    assert b.snapshot.retry_at == clock.t + 200  # capped


def test_cancelled_probe_lets_another_probe_run() -> None:
    clock = Clock()
    b = make(clock)
    b.on_quota(None, resets_at=1_010.0)
    clock.t = 1_010.0
    probe = b.allow()
    assert probe is not None
    b.release_probe(probe)
    again = b.allow()
    assert again is not None and again.probe


def test_restore_quota_never_open_forever() -> None:
    clock = Clock()
    b = make(clock)
    b.restore_quota(opened_at=900.0, retry_at=None)
    assert b.snapshot.retry_at == 960.0
    assert b.allow() is not None  # 960 < now(1000): probe allowed
    b2 = make(clock)
    b2.restore_quota(opened_at=900.0, retry_at=2_000.0)
    assert b2.allow() is None and b2.snapshot.retry_at == 2_000.0
