"""Child processes of jobs: own process group, streamed output, timeout and
cancel kill the whole group."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

KILL_GRACE_S = 5.0
CHUNK = 64 * 1024
MAX_LINE = 64 * 1024

LineFn = Callable[[str], None]


@dataclass
class ProcResult:
    exit_code: int
    reason: str | None  # None | "timeout" | "cancelled"
    duration_ms: int


EXIT_TIMEOUT = 124
EXIT_CANCELLED = 130


def kill_group(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, sig)


async def _pump(stream: asyncio.StreamReader, on_line: LineFn, max_line: int = MAX_LINE) -> None:
    pending = b""
    while True:
        chunk = await stream.read(CHUNK)
        if not chunk:
            break
        pending += chunk
        while True:
            nl = pending.find(b"\n")
            if nl < 0:
                break
            on_line(pending[:nl].decode("utf-8", "replace").rstrip("\r"))
            pending = pending[nl + 1 :]
        while len(pending) > max_line:
            on_line(pending[:max_line].decode("utf-8", "replace"))
            pending = pending[max_line:]
    if pending:
        on_line(pending.decode("utf-8", "replace").rstrip("\r"))


async def run_streamed(
    argv: list[str],
    *,
    cwd: str | None,
    env: Mapping[str, str] | None,
    limit_s: float,
    cancel: asyncio.Event,
    on_stdout: LineFn,
    on_stderr: LineFn,
    max_line: int = MAX_LINE,
) -> ProcResult:
    """Runs argv in a new session (its own process group). On timeout or
    cancel the group gets SIGTERM, then SIGKILL after a grace period. A line
    longer than `max_line` comes in pieces (⟨0.2.0⟩ the claude job's stream
    of JSON lines raises it so its final answer is one whole line)."""
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    pumps = [
        asyncio.create_task(_pump(proc.stdout, on_stdout, max_line)),
        asyncio.create_task(_pump(proc.stderr, on_stderr)),
    ]
    waiter = asyncio.create_task(proc.wait())
    cancelled = asyncio.create_task(cancel.wait())
    reason: str | None = None
    try:
        done, _ = await asyncio.wait(
            {waiter, cancelled}, timeout=limit_s, return_when=asyncio.FIRST_COMPLETED
        )
        if waiter not in done:
            reason = "cancelled" if cancelled in done else "timeout"
            kill_group(proc.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(asyncio.shield(waiter), KILL_GRACE_S)
            except TimeoutError:
                kill_group(proc.pid, signal.SIGKILL)
                await waiter
            # On timeout or cancel nothing of the group survives.
            kill_group(proc.pid, signal.SIGKILL)
        _, open_pumps = await asyncio.wait(pumps, timeout=2.0)
        if open_pumps:
            # A background child still holds the job's output pipes: it goes too.
            # (A child started with its output redirected, e.g. `nohup x >log &`, is left alone.)
            kill_group(proc.pid, signal.SIGKILL)
            await asyncio.wait(open_pumps, timeout=KILL_GRACE_S)
    finally:
        cancelled.cancel()
        for p in pumps:
            p.cancel()
        if proc.returncode is None:  # the runner itself is being cancelled
            kill_group(proc.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), KILL_GRACE_S)
    code = proc.returncode if proc.returncode is not None else -9
    if reason == "timeout":
        code = EXIT_TIMEOUT
    elif reason == "cancelled":
        code = EXIT_CANCELLED
    elif code < 0:
        code = 128 - code
    return ProcResult(code, reason, int((time.monotonic() - start) * 1000))


async def capture(
    argv: list[str],
    *,
    limit_s: float = 15.0,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """stdout of a short read-only command, or None when the tool is missing,
    fails or takes too long. Used by the inventory."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), limit_s)
    except TimeoutError:
        kill_group(proc.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            await proc.wait()
        return None
    if proc.returncode != 0:
        return None
    return out.decode("utf-8", "replace")
