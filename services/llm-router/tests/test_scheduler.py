import asyncio

import pytest

from llm_router.scheduler import PriorityScheduler, QueueRejected, QueueTimeout


async def _hold(
    s: PriorityScheduler, p: int, log: list[str], tag: str, hold: asyncio.Event
) -> None:
    await s.acquire(p, timeout=5)
    log.append(tag)
    await hold.wait()
    s.release()


def test_invalid_config() -> None:
    with pytest.raises(ValueError):
        PriorityScheduler(capacity=1, reserved_high=1)


async def test_reserved_slot_is_kept_for_p0_to_p2() -> None:
    s = PriorityScheduler(capacity=3, reserved_high=1, p4_max_waiting=10)
    await s.acquire(3, 1)
    await s.acquire(4, 1)
    assert s.active == 2
    # a third background call must wait: the last slot is reserved
    with pytest.raises(QueueTimeout):
        await s.acquire(4, 0.05)
    with pytest.raises(QueueTimeout):
        await s.acquire(3, 0.05)
    assert s.waiting() == 0  # timed-out waiters are removed
    await s.acquire(2, 0.05)  # P2 takes the reserved slot at once
    assert s.active == 3


async def test_waiters_are_served_by_priority_then_fifo() -> None:
    s = PriorityScheduler(capacity=2, reserved_high=1, p4_max_waiting=10)
    hold = asyncio.Event()
    log: list[str] = []
    first = asyncio.create_task(_hold(s, 0, log, "first", hold))
    second = asyncio.create_task(_hold(s, 1, log, "second", hold))
    await asyncio.sleep(0.01)
    assert s.active == 2
    order: list[str] = []

    async def waiter(p: int, tag: str) -> None:
        await s.acquire(p, 5)
        order.append(tag)
        s.release()

    tasks = [
        asyncio.create_task(waiter(4, "p4")),
        asyncio.create_task(waiter(3, "p3-a")),
        asyncio.create_task(waiter(1, "p1")),
        asyncio.create_task(waiter(3, "p3-b")),
        asyncio.create_task(waiter(0, "p0")),
    ]
    await asyncio.sleep(0.01)
    assert s.waiting() == 5
    hold.set()
    await asyncio.gather(first, second, *tasks)
    assert order == ["p0", "p1", "p3-a", "p3-b", "p4"]
    assert s.active == 0


async def test_p4_rejected_with_retry_after_when_background_queue_full() -> None:
    s = PriorityScheduler(capacity=2, reserved_high=1, p4_max_waiting=1, retry_after_s=17)
    await s.acquire(4, 1)  # uses the only non-reserved slot
    waiting = asyncio.create_task(s.acquire(4, 5))
    await asyncio.sleep(0.01)
    with pytest.raises(QueueRejected) as exc:
        await s.acquire(4, 1)
    assert exc.value.retry_after_s == 17
    assert exc.value.reason == "queue_full_background"
    await s.acquire(1, 1)  # high priority still gets the reserved slot
    s.release()
    s.release()
    await waiting
    s.release()
    assert s.active == 0


async def test_queue_full_rejects_everyone() -> None:
    s = PriorityScheduler(capacity=1, reserved_high=0, max_waiting=1)
    await s.acquire(0, 1)
    pending = asyncio.create_task(s.acquire(0, 5))
    await asyncio.sleep(0.01)
    with pytest.raises(QueueRejected) as exc:
        await s.acquire(0, 1)
    assert exc.value.reason == "queue_full"
    s.release()
    await pending
    s.release()


async def test_cancelled_waiter_leaves_queue_and_slot_context() -> None:
    s = PriorityScheduler(capacity=1, reserved_high=0)
    async with s.slot(0, 1):
        t = asyncio.create_task(s.acquire(0, 5))
        await asyncio.sleep(0.01)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert s.waiting() == 0
    assert s.active == 0
    with pytest.raises(RuntimeError):
        s.release()
