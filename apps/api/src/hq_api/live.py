"""Replies being written (contract §16.3): an in-memory fan-out per thread.

The runtime pushes `reply.*` events of a run into the api process
(POST /internal/v1/threads/{code}/live); the owner's clients listen on
GET /api/v1/threads/{code}/live. Deltas live only here, for the seconds the
reply takes: never stored, never on NATS, never logged. One api replica
today; the same interface fits a shared bus later.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

QUEUE_SIZE = 512


class LiveHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[tuple[str, dict[str, Any]]]]] = defaultdict(set)

    def subscribe(self, thread: str) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        q: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subs[thread].add(q)
        return q

    def unsubscribe(self, thread: str, q: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        subs = self._subs.get(thread)
        if subs is not None:
            subs.discard(q)
            if not subs:
                del self._subs[thread]

    def listeners(self, thread: str) -> int:
        return len(self._subs.get(thread, ()))

    def publish(self, thread: str, type_: str, data: dict[str, Any]) -> int:
        """Non-blocking: a listener that cannot keep up loses deltas, never the stream."""
        sent = 0
        for q in list(self._subs.get(thread, ())):
            try:
                q.put_nowait((type_, data))
                sent += 1
            except asyncio.QueueFull:
                continue
        return sent
