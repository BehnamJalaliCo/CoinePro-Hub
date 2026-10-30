"""One job's event stream to the hub: numbered, batched, capped, retried."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from hq_runner.hub import Hub, HubError, JobGone, Transient, with_retry

log = logging.getLogger("hq_runner.events")

MAX_OUTPUT_BYTES = 10 * 1024 * 1024
FLUSH_EVERY_S = 0.5
MAX_BATCH_EVENTS = 200
MAX_BATCH_BYTES = 512 * 1024


class EventSink:
    """Collects events of one job and posts them in batches of
    {seq, type, data}. stdout/stderr text beyond MAX_OUTPUT_BYTES is dropped
    after one notice; other events are never dropped."""

    def __init__(
        self,
        hub: Hub,
        job_id: str,
        *,
        on_gone: Callable[[], None] | None = None,
        on_fatal: Callable[[HubError], None] | None = None,
        max_output: int = MAX_OUTPUT_BYTES,
        flush_every: float = FLUSH_EVERY_S,
    ) -> None:
        self.hub = hub
        self.job_id = job_id
        self.on_gone = on_gone
        self.on_fatal = on_fatal
        self.max_output = max_output
        self.flush_every = flush_every
        self.seq = 0
        self.output_bytes = 0
        self.truncated = False
        self._buf: list[dict[str, Any]] = []
        self._buf_bytes = 0
        self._wake = asyncio.Event()
        self._closed = False
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.dead = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def emit(self, type_: str, data: dict[str, Any]) -> None:
        if type_ in ("stdout", "stderr"):
            size = len(str(data.get("text", "")).encode())
            if self.output_bytes + size > self.max_output:
                if not self.truncated:
                    self.truncated = True
                    self._append(
                        "progress",
                        {"text": f"output truncated at {self.max_output // (1024 * 1024)} MB"},
                    )
                self.output_bytes += size
                return
            self.output_bytes += size
        self._append(type_, data)

    def _append(self, type_: str, data: dict[str, Any]) -> None:
        self.seq += 1
        self._buf.append({"seq": self.seq, "type": type_, "data": data})
        self._buf_bytes += len(str(data))
        if len(self._buf) >= MAX_BATCH_EVENTS or self._buf_bytes >= MAX_BATCH_BYTES:
            self._wake.set()

    async def _loop(self) -> None:
        while not self._closed:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self.flush_every)
            self._wake.clear()
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            while self._buf and not self.dead:
                batch, rest = self._buf[:MAX_BATCH_EVENTS], self._buf[MAX_BATCH_EVENTS:]
                self._buf, self._buf_bytes = rest, sum(len(str(e["data"])) for e in rest)

                async def post(b: list[dict[str, Any]] = batch) -> None:
                    await self.hub.post_events(self.job_id, b)

                try:
                    await with_retry(post)
                except JobGone:
                    self.dead = True
                    if self.on_gone:
                        self.on_gone()
                except Transient as exc:
                    log.warning("job %s: events could not be delivered (%s)", self.job_id, exc)
                except HubError as exc:
                    self.dead = True
                    if self.on_fatal:
                        self.on_fatal(exc)
                    else:  # pragma: no cover
                        log.warning("job %s: events refused (%s)", self.job_id, exc)

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.flush()
