"""`hq-runner run`: long-polls the hub for jobs, runs at most two at a time,
streams their events, posts their results, honours cancels and rotates the
token every 24 h. Every poll is also the heartbeat (via, round trip, version).

Stops for good on 401 (exit 3: pair again) and on revocation (exit 4); the
systemd unit does not restart on those two exit codes.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import gzip
import logging
import signal
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hq_runner import __version__
from hq_runner.claude_job import run_claude
from hq_runner.config import Config, save, save_state
from hq_runner.events import MAX_OUTPUT_BYTES, EventSink
from hq_runner.hub import (
    Backoff,
    Hub,
    HubError,
    JobGone,
    Revoked,
    Transient,
    Unauthorized,
    with_retry,
)
from hq_runner.inventory import run_map
from hq_runner.jobs import (
    Handler,
    JobContext,
    JobError,
    JobResult,
    run_exec,
    run_netcheck,
    run_publish,
    run_read,
    run_write,
)
from hq_runner.mask import Masker
from hq_runner.net import Route
from hq_runner.proc import EXIT_CANCELLED

log = logging.getLogger("hq_runner.runner")

MAX_JOBS = 2
EXIT_OK = 0
EXIT_REPAIR = 3
EXIT_REVOKED = 4
# A hard ceiling per kind on top of each job's own timeout (seconds).
KIND_CEILING_S = {
    "map": 300,
    "read": 120,
    "write": 120,
    "netcheck": 120,
    "exec": 3700,
    "publish": 3700,
    "claude": 4 * 3600 + 120,
}
PROCESS_KINDS = {"exec", "claude", "publish"}

HANDLERS: dict[str, Handler] = {
    "map": run_map,
    "exec": run_exec,
    "read": run_read,
    "write": run_write,
    "claude": run_claude,
    "publish": run_publish,
    "netcheck": run_netcheck,
}


@dataclass
class Running:
    job: dict[str, Any]
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class Fatal(Exception):
    def __init__(self, exit_code: int, message: str):
        super().__init__(message)
        self.exit_code = exit_code


ARTIFACT_GZ_MAX = 20 * 1024 * 1024  # the result body carries it as base64 (the hub takes 32 MB)


def with_overflow(result: JobResult, sink: EventSink) -> JobResult:
    """⟨0.2.0⟩ the output past the live stream, whole, as one gzip artifact of
    the result (`output_overflow`). Only when even that is over
    ARTIFACT_GZ_MAX does its beginning go, and the result says from which
    byte it is kept; nothing is cut without saying so."""
    path = sink.overflow_path
    raw = Path(path).read_bytes() if path else b""
    kept_from = 0
    packed = gzip.compress(raw, compresslevel=6)
    for keep in (64 * 1024 * 1024, 16 * 1024 * 1024):
        if len(packed) <= ARTIFACT_GZ_MAX:
            break
        kept_from = max(0, len(raw) - keep)
        packed = gzip.compress(raw[kept_from:], compresslevel=6)
    art: dict[str, Any] = {
        "encoding": "gzip+base64",
        "b64": base64.b64encode(packed).decode() if len(packed) <= ARTIFACT_GZ_MAX else "",
        "bytes": len(raw),
        "kept_from_byte": kept_from,
        "dropped_bytes": sink.dropped_bytes,
    }
    output = dict(result.output or {})
    output["output_overflow"] = art
    note = f" خروجی بیش از ۱۰ مگابایت بود؛ {len(raw)} بایتِ بعدی کامل به‌صورت فایل پیوست شد."
    if kept_from or sink.dropped_bytes or not art["b64"]:
        note = (
            f" خروجی بسیار بزرگ بود؛ از بایت {kept_from} پیوست شد"
            f" و {sink.dropped_bytes} بایت فراتر از سقف دیسک نگه داشته نشد."
        )
    return JobResult(result.exit_code, result.summary_fa + note, result.usage, output)


class Runner:
    def __init__(
        self,
        cfg: Config,
        route: Route,
        *,
        cfg_path: Path | None = None,
        max_jobs: int = MAX_JOBS,
        handlers: dict[str, Handler] | None = None,
        sleep: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep,
        backoff: Backoff | None = None,
        persist_state: bool = True,
        max_output: int = MAX_OUTPUT_BYTES,
    ) -> None:
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.route = route
        self.hub = Hub(route, lambda: self.cfg.runner_token)
        self.max_jobs = max_jobs
        self.handlers = handlers or HANDLERS
        self.sleep = sleep
        self.backoff = backoff or Backoff()
        self.persist_state = persist_state
        self.max_output = max_output
        self.slots = asyncio.Semaphore(max_jobs)
        self.running: dict[str, Running] = {}
        self.stop_event = asyncio.Event()
        self.fatal: Fatal | None = None
        self.last_ok: float | None = None

    @property
    def masker(self) -> Masker:
        return Masker([self.cfg.runner_token])

    # -- lifecycle ---------------------------------------------------------------------
    def stop(self) -> None:
        self.stop_event.set()

    def fail(self, exc: HubError) -> None:
        if self.fatal is not None:
            return
        if isinstance(exc, Unauthorized):
            self.fatal = Fatal(
                EXIT_REPAIR,
                "the hub no longer accepts this runner's token; run `hq-runner pair` again",
            )
        elif isinstance(exc, Revoked):
            self.fatal = Fatal(EXIT_REVOKED, "this server was detached in HQ; the runner stops")
            self.cfg.state = "revoked"
            if self.persist_state:
                with contextlib.suppress(OSError):
                    save(self.cfg, self.cfg_path)
        else:
            return
        self.stop_event.set()

    async def run(self) -> int:
        if self.cfg.state == "revoked":
            log.error("this server was detached in HQ; pair it again to use it")
            return EXIT_REVOKED
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, self.stop)
        await self.route.select()
        log.info(
            "hq-runner %s started for server %s via %s",
            __version__,
            self.cfg.server_id,
            self.route.via,
        )
        try:
            await self.poll_loop()
        finally:
            await self.shutdown()
            for sig in (signal.SIGTERM, signal.SIGINT):
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)
        if self.fatal:
            log.error("%s", self.fatal)
            self.write_state("stopped")
            return self.fatal.exit_code
        self.write_state("stopped")
        return EXIT_OK

    async def shutdown(self) -> None:
        for r in self.running.values():
            r.cancel.set()
        tasks = [r.task for r in self.running.values() if r.task]
        if tasks:
            await asyncio.wait(tasks, timeout=30)
        await self.route.aclose()

    def write_state(self, state: str) -> None:
        if not self.persist_state:
            return
        with contextlib.suppress(OSError):
            save_state(
                {
                    "state": state,
                    "server_id": self.cfg.server_id,
                    "via": self.route.via,
                    "hub_rtt_ms": self.route.rtt_ms,
                    "version": __version__,
                    "last_ok_at": self.last_ok,
                    "running_jobs": len(self.running),
                    "updated_at": time.time(),
                },
                self.cfg_path,
            )

    # -- polling -------------------------------------------------------------------------
    async def maybe_rotate(self) -> None:
        if not self.cfg.rotation_due():
            return
        token = await self.hub.rotate()
        self.cfg.runner_token = token
        self.cfg.rotated_at = time.time()
        if self.persist_state:
            save(self.cfg, self.cfg_path)
        log.info("runner token rotated")

    async def poll_once(self) -> None:
        await self.route.refresh()
        await self.maybe_rotate()
        free = max(0, self.max_jobs - len(self.running))
        nxt = await self.hub.next_job(free)
        self.last_ok = time.time()
        self.backoff.reset()
        for jid in nxt.cancels:
            r = self.running.get(jid)
            if r is not None:
                log.info("job %s cancelled by the hub", jid)
                r.cancel.set()
        if nxt.job is not None:
            self.start_job(nxt.job)
        self.write_state("online")

    async def poll_loop(self) -> None:
        while not self.stop_event.is_set():
            poll = asyncio.create_task(self.poll_once())
            stopper = asyncio.create_task(self.stop_event.wait())
            await asyncio.wait({poll, stopper}, return_when=asyncio.FIRST_COMPLETED)
            stopper.cancel()
            if not poll.done():
                poll.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await poll
                break
            try:
                poll.result()
            except (Unauthorized, Revoked) as exc:
                self.fail(exc)
            except Transient as exc:
                delay = self.backoff.next()
                log.warning("hub not reachable (%s); retrying in %.1fs", exc, delay)
                self.write_state("offline")
                await self._sleep_or_stop(delay)
            except HubError as exc:
                delay = self.backoff.next()
                log.warning("hub refused the poll (%s); retrying in %.1fs", exc, delay)
                await self._sleep_or_stop(delay)

    async def _sleep_or_stop(self, delay: float) -> None:
        sleeper = asyncio.create_task(self.sleep(delay))
        stopper = asyncio.create_task(self.stop_event.wait())
        await asyncio.wait({sleeper, stopper}, return_when=asyncio.FIRST_COMPLETED)
        sleeper.cancel()
        stopper.cancel()

    # -- jobs ------------------------------------------------------------------------------
    def start_job(self, job: dict[str, Any]) -> None:
        jid = str(job.get("id", ""))
        if not jid or jid in self.running:
            return
        r = Running(job)
        self.running[jid] = r
        r.task = asyncio.create_task(self.run_job(r))

    async def run_job(self, r: Running) -> None:
        jid = str(r.job["id"])
        try:
            # Above the limit a job waits here for a free slot (the hub may hand
            # out one more while a cancel is being delivered).
            async with self.slots:
                if r.cancel.is_set():
                    await self.post_result(
                        jid, JobResult(EXIT_CANCELLED, "کار پیش از شروع لغو شد.")
                    )
                    return
                await self.execute(r)
        finally:
            self.running.pop(jid, None)

    async def execute(self, r: Running) -> None:
        jid = str(r.job["id"])
        kind = str(r.job.get("kind", ""))
        sink = EventSink(
            self.hub, jid, on_gone=r.cancel.set, on_fatal=self.fail, max_output=self.max_output
        )
        sink.start()
        ctx = JobContext(r.job, self.hub, sink, r.cancel, self.masker, self.cfg, self.cfg_path)
        log.info("job %s (%s) started", jid, kind)
        handler = self.handlers.get(kind)
        try:
            if handler is None:
                result = JobResult(2, f"نوع کار «{kind}» را این runner نمیشناسد.")
            else:
                ceiling = KIND_CEILING_S.get(kind, 3700)
                result = await asyncio.wait_for(self._guarded(handler, ctx), ceiling)
        except JobError as exc:
            result = JobResult(exc.exit_code, exc.summary_fa)
        except TimeoutError:
            r.cancel.set()
            result = JobResult(124, "کار به سقف زمان رسید و متوقف شد.")
        except Exception:
            log.exception("job %s failed inside the runner", jid)
            result = JobResult(1, "کار به خطای داخلی runner خورد.")
        if r.cancel.is_set() and result.exit_code == 0 and kind not in PROCESS_KINDS:
            result = JobResult(EXIT_CANCELLED, "کار لغو شد.")
        await sink.close()
        log.info("job %s (%s) finished with exit code %s", jid, kind, result.exit_code)
        try:
            if sink.overflow_path is not None or sink.dropped_bytes:
                result = await asyncio.to_thread(with_overflow, result, sink)
            if not sink.dead:
                await self.post_result(jid, result)
        finally:
            sink.discard_overflow()

    async def _guarded(self, handler: Handler, ctx: JobContext) -> JobResult:
        """Runs the handler; a cancel stops handlers that have no process of their own."""
        task = asyncio.create_task(handler(ctx))
        canceller = asyncio.create_task(ctx.cancel.wait())
        try:
            done, _ = await asyncio.wait({task, canceller}, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                return task.result()
            # Process-backed handlers kill their group and return on their own.
            grace = 15 if ctx.job.get("kind") in PROCESS_KINDS else 0.5
            try:
                return await asyncio.wait_for(asyncio.shield(task), grace)
            except TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                return JobResult(EXIT_CANCELLED, "کار لغو شد.")
        finally:
            canceller.cancel()
            if not task.done():
                task.cancel()

    async def post_result(self, jid: str, result: JobResult) -> None:
        body: dict[str, Any] = {"exit_code": result.exit_code, "summary_fa": result.summary_fa}
        if result.usage is not None:
            body["usage"] = result.usage
        if result.output is not None:
            body["data"] = result.output
        try:
            await with_retry(lambda: self.hub.post_result(jid, body), attempts=10, sleep=self.sleep)
        except JobGone:
            log.info("job %s was already closed on the hub", jid)
        except (Unauthorized, Revoked) as exc:
            self.fail(exc)
        except HubError as exc:
            log.error("job %s: result not delivered (%s)", jid, exc)
