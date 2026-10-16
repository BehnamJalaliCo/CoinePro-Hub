"""Priority admission with a reserved slot.

capacity      concurrent model calls (3 on the lean profile)
reserved_high slots only P0-P2 may use; P3/P4 run only while
              active < capacity - reserved_high
Waiters are served by priority, FIFO within a priority. A P4 that cannot
start right away is rejected ("try again", Retry-After) once
p4_max_waiting P4 requests are already queued; every priority is rejected
when the queue holds max_waiting requests. The durable queue comes later
(Temporal); this one lives in memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

HIGH_MAX_PRIORITY = 2  # P0..P2 may use the reserved slot


class QueueRejected(Exception):
    def __init__(self, reason: str, retry_after_s: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after_s = retry_after_s


class QueueTimeout(Exception):
    pass


@dataclass(order=True)
class _Waiter:
    priority: int
    seq: int
    future: asyncio.Future[None] = field(compare=False)


class PriorityScheduler:
    def __init__(
        self,
        capacity: int,
        reserved_high: int = 1,
        p4_max_waiting: int = 4,
        max_waiting: int = 32,
        retry_after_s: int = 30,
    ) -> None:
        if capacity < 1 or not 0 <= reserved_high < capacity:
            raise ValueError("need capacity >= 1 and 0 <= reserved_high < capacity")
        self.capacity = capacity
        self.reserved_high = reserved_high
        self.p4_max_waiting = p4_max_waiting
        self.max_waiting = max_waiting
        self.retry_after_s = retry_after_s
        self.active = 0
        self._waiters: list[_Waiter] = []
        self._seq = itertools.count()

    def _can_start(self, priority: int) -> bool:
        if priority <= HIGH_MAX_PRIORITY:
            return self.active < self.capacity
        return self.active < self.capacity - self.reserved_high

    def waiting(self, priority: int | None = None) -> int:
        return sum(1 for w in self._waiters if priority is None or w.priority == priority)

    async def acquire(self, priority: int, timeout: float) -> None:  # noqa: ASYNC109 - bounded wait is the API
        ahead = any(w.priority <= priority for w in self._waiters)
        if not ahead and self._can_start(priority):
            self.active += 1
            return
        if priority >= 4 and self.waiting(4) >= self.p4_max_waiting:
            raise QueueRejected("queue_full_background", self.retry_after_s)
        if len(self._waiters) >= self.max_waiting:
            raise QueueRejected("queue_full", self.retry_after_s)
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        waiter = _Waiter(priority, next(self._seq), fut)
        self._waiters.append(waiter)
        self._waiters.sort()
        try:
            await asyncio.wait_for(fut, timeout)
        except (TimeoutError, asyncio.CancelledError) as exc:
            if fut.done() and not fut.cancelled():
                self.release()  # granted at the last moment: hand the slot on
            else:
                self._discard(waiter)
            if isinstance(exc, TimeoutError):
                raise QueueTimeout() from None
            raise

    def _discard(self, waiter: _Waiter) -> None:
        waiter.future.cancel()
        with contextlib.suppress(ValueError):
            self._waiters.remove(waiter)

    def release(self) -> None:
        if self.active <= 0:
            raise RuntimeError("release() without acquire()")
        self.active -= 1
        self._dispatch()

    def _dispatch(self) -> None:
        for waiter in list(self._waiters):
            if waiter.future.done():
                self._waiters.remove(waiter)
                continue
            if self._can_start(waiter.priority):
                self._waiters.remove(waiter)
                self.active += 1
                waiter.future.set_result(None)

    @contextlib.asynccontextmanager
    async def slot(self, priority: int, timeout: float) -> AsyncIterator[None]:  # noqa: ASYNC109
        await self.acquire(priority, timeout)
        try:
            yield
        finally:
            self.release()
