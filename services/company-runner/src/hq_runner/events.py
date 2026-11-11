"""One job's event stream to the hub: numbered, batched, retried.

⟨0.2.0⟩ Nothing is dropped: stdout/stderr beyond MAX_OUTPUT_BYTES (the part
streamed live) goes on to a private spool file (up to SPOOL_MAX_BYTES on
disk), which the runner sends with the result as one gzip artifact.

A batch stays under MAX_POST_BYTES (the hub refuses a body over 8 MB); a hub
that is away longer than one retry window gets the same batch again on the
next round, so an outage leaves no gap in the session's events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from typing import Any

from hq_runner.hub import Hub, HubError, JobGone, Revoked, Transient, Unauthorized, with_retry

log = logging.getLogger("hq_runner.events")

MAX_OUTPUT_BYTES = 10 * 1024 * 1024
SPOOL_MAX_BYTES = 512 * 1024 * 1024
FLUSH_EVERY_S = 0.5
MAX_BATCH_EVENTS = 200
MAX_BATCH_BYTES = 512 * 1024
MAX_POST_BYTES = 4 * 1024 * 1024  # one POST of events: well under the hub's 8 MB body cap


def _size(event: dict[str, Any]) -> int:
    """The bytes an event takes in the POST body (httpx sends UTF-8 JSON)."""
    return len(json.dumps(event, ensure_ascii=False, default=str).encode())


class EventSink:
    """Collects events of one job and posts them in batches of
    {seq, type, data}. stdout/stderr text beyond MAX_OUTPUT_BYTES is not
    streamed (one notice says so) but spooled to a private file, kept whole
    up to SPOOL_MAX_BYTES (`overflow_bytes`, `dropped_bytes` say how much);
    other events are never dropped."""

    def __init__(
        self,
        hub: Hub,
        job_id: str,
        *,
        on_gone: Callable[[], None] | None = None,
        on_fatal: Callable[[HubError], None] | None = None,
        max_output: int = MAX_OUTPUT_BYTES,
        flush_every: float = FLUSH_EVERY_S,
        spool_max: int = SPOOL_MAX_BYTES,
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
        self.spool_max = spool_max
        self.overflow_bytes = 0
        self.dropped_bytes = 0
        self._spool_dir: str | None = None
        self._spool: Any = None
        self._buf: list[dict[str, Any]] = []
        self._buf_bytes = 0
        self._wake = asyncio.Event()
        self._closed = False
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._limit = MAX_BATCH_EVENTS  # halved after a 413, back once a batch went through
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
                        {
                            "text": f"output over {self.max_output // (1024 * 1024)} MB: the rest "
                            "comes whole with the result (a gzip artifact)"
                        },
                    )
                self.output_bytes += size
                self._overflow(type_, str(data.get("text", "")))
                return
            self.output_bytes += size
        self._append(type_, data)

    def _overflow(self, type_: str, text: str) -> None:
        raw = (text if type_ == "stdout" else f"[stderr] {text}").encode()
        if self.overflow_bytes + len(raw) > self.spool_max:
            self.dropped_bytes += len(raw)
            return
        if self._spool is None:
            self._spool_dir = tempfile.mkdtemp(prefix="hq-output-")
            os.chmod(self._spool_dir, 0o700)
            self._spool = open(  # noqa: SIM115 - kept open for the job's life
                os.path.join(self._spool_dir, "overflow.log"), "wb"
            )
        self._spool.write(raw)
        self.overflow_bytes += len(raw)

    @property
    def overflow_path(self) -> str | None:
        if self._spool is None or self._spool_dir is None:
            return None
        self._spool.flush()
        return os.path.join(self._spool_dir, "overflow.log")

    def discard_overflow(self) -> None:
        if self._spool is not None:
            with contextlib.suppress(OSError):
                self._spool.close()
        if self._spool_dir is not None:
            shutil.rmtree(self._spool_dir, ignore_errors=True)
        self._spool, self._spool_dir = None, None

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

    def _take(self) -> list[dict[str, Any]]:
        """The next batch: up to `_limit` events and MAX_POST_BYTES (always at least one)."""
        batch: list[dict[str, Any]] = []
        total = 0
        for e in self._buf[: self._limit]:
            size = _size(e)
            if batch and total + size > MAX_POST_BYTES:
                break
            batch.append(e)
            total += size
        return batch

    def _set_buf(self, buf: list[dict[str, Any]]) -> None:
        self._buf, self._buf_bytes = buf, sum(len(str(e["data"])) for e in buf)

    async def flush(self) -> None:
        async with self._lock:
            while self._buf and not self.dead:
                batch = self._take()
                self._set_buf(self._buf[len(batch) :])

                async def post(b: list[dict[str, Any]] = batch) -> None:
                    await self.hub.post_events(self.job_id, b)

                try:
                    await with_retry(post)
                    self._limit = MAX_BATCH_EVENTS
                except JobGone:
                    self.dead = True
                    if self.on_gone:
                        self.on_gone()
                except Transient as exc:
                    # the hub is away longer than one retry window: the batch goes back to the
                    # front and the next round sends it again (the hub skips a seq it has)
                    self._set_buf(batch + self._buf)
                    log.warning("job %s: events not delivered yet (%s)", self.job_id, exc)
                    return
                except (Unauthorized, Revoked) as exc:
                    self.dead = True
                    if self.on_fatal:
                        self.on_fatal(exc)
                    else:  # pragma: no cover
                        log.warning("job %s: events refused (%s)", self.job_id, exc)
                except HubError as exc:
                    if exc.status == 413 and len(batch) > 1:
                        # too big for the hub after all: the same events again in smaller posts
                        self._limit = max(1, len(batch) // 2)
                        self._set_buf(batch + self._buf)
                        continue
                    # this batch is refused (one event too big, or not valid): it alone is
                    # lost, the job's later events and its result still go
                    log.warning(
                        "job %s: %d events refused (%s)", self.job_id, len(batch), exc.code or exc
                    )

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.flush()
