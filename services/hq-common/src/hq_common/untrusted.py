"""Untrusted file processing (prompt 07.1 §1.2, 06.1 §1.4): every parse of an
image, PDF or HTML page that came from outside the hub (an owner upload, an
agent's download, a fetched page) runs here, in a CHILD process, never in the
service's own process or on its event loop.

- The child is a fresh interpreter (`python -m hq_common.untrusted`), with a
  minimal environment (no secret of the parent's), no inherited descriptors,
  `/` as its working directory and nothing but its own code on the path.
- Before it reads a byte of the file it limits itself: RLIMIT_AS (address
  space), RLIMIT_CPU (SIGXCPU at the soft limit, SIGKILL at the hard one),
  RLIMIT_FSIZE (what it may write), no core dumps, and oom_score_adj 1000 so
  that, if the container's memory runs out anyway, the kernel kills the child
  and not the service.
- The parent waits at most `deadline_s` of wall clock and then KILLS it (the
  ffmpeg pattern of the api's media code). A cancelled caller kills it too.
- Children run one or a few at a time per process (`slots`): a burst of
  uploads queues instead of multiplying the memory.
- The answer is one JSON document on a private pipe; stderr goes nowhere (a
  hostile file can make a parser warn a million times).

`run()` never raises for what the file does: it returns an Outcome that says
whether the job finished (`ok`, `value`), refused the file (`error`, the
job's own exception), or was stopped (`killed`: deadline, cpu, memory, crash,
busy, answer). What the caller records is its decision; the work stays here.

The limits below were measured (prompt 07.1; Python 3.12, Pillow 12.3,
pillow-heif 1.8, pypdf 6.19, lxml 6.1; VmPeak = address space):
- the interpreter alone: 39 MiB with lxml, 55-64 with pypdf, 72 with Pillow
  and pillow-heif; starting it costs 0.3-0.4 s;
- within 192 MiB: a 40 MP JPEG cleaned (image_meta) 67 MiB, a 12 MP HEIC
  177, a 30 MP PNG, a PDF with 5 MB of text 174 MiB and 8 s of CPU (the
  heaviest honest file: hence 20 s of CPU and a 30 s deadline);
- the reviewer's PDF bomb, 41 KB holding 20 MB of compressed operators,
  costs pypdf 28.9 s and 1161 MiB unlimited, and is stopped by the memory
  limit after 3.8 s;
- over the limit, refused rather than risked: a 24 MP HEIC (261 MiB), a
  24 MP WebP (428), 10 MB of dense HTML (259).
The api's container (384m full) holds its own ~105 MiB and one such child;
in the lean profile the kernel's OOM killer takes the child first.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import importlib
import importlib.util
import json
import os
import signal
import sys
import time
import weakref
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MIB = 1024 * 1024
MEMORY_MB = 192  # RLIMIT_AS of a child (measured, see above)
CPU_S = 20  # RLIMIT_CPU soft limit (hard = soft + 2)
DEADLINE_S = 30.0  # wall clock, then SIGKILL
MAX_ANSWER = 4 * MIB  # the child's JSON answer
EXIT_MEMORY = 3  # the child ran out of address space (MemoryError)
EXIT_ERROR = 4  # the job raised: the file is refused, not the child stopped


@dataclass(frozen=True)
class Limits:
    memory_mb: int = MEMORY_MB
    cpu_s: int = CPU_S
    deadline_s: float = DEADLINE_S
    write_mb: int = 0  # RLIMIT_FSIZE: 0 = the child writes no file at all


DEFAULT = Limits()


@dataclass
class Outcome:
    ok: bool
    value: Any = None
    error: str | None = None  # the job's own refusal (a broken or hostile file)
    killed: str | None = None  # deadline | cpu | memory | crash | busy | answer
    seconds: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)  # the child's peaks (KiB) and CPU

    @property
    def reason(self) -> str:
        if self.killed:
            return f"stopped: {self.killed}"
        return (self.error or "")[:200]


# ------------------------------------------------------------- the parent --
_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)
_spawned: list[int] = []  # pids, newest last (tests check that a child is gone)
_size = [1]


def set_slots(n: int) -> None:
    """Children at the same time in this process (default 1: the api, whose
    container holds one child at its limit; egress runs 2 so that one heavy
    page does not hold up every other read)."""
    _size[0] = max(1, n)
    _slots.clear()


def _slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _slots.get(loop)
    if sem is None:
        sem = _slots[loop] = asyncio.Semaphore(_size[0])
    return sem


def _root_of(module: str) -> str:
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        raise ValueError(f"no such module: {module}")
    depth = module.count(".") + (1 if spec.origin.endswith("__init__.py") else 0)
    return str(Path(spec.origin).parents[depth])


def _env(target: str) -> dict[str, str]:
    """Only what an interpreter needs: never the parent's secrets."""
    roots = [_root_of("hq_common"), _root_of(target.split(":", 1)[0])]
    path = list(dict.fromkeys(roots))
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONPATH": os.pathsep.join(path),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        # One malloc arena: each extra one reserves 64 MiB of address space.
        "MALLOC_ARENA_MAX": "1",
        "OMP_NUM_THREADS": "1",
    }


async def run(
    target: str,
    *,
    kwargs: dict[str, Any] | None = None,
    data: bytes | None = None,
    limits: Limits = DEFAULT,
) -> Outcome:
    """`target` = "module:function". The function gets `data` (when given)
    as its first argument and `kwargs`, and returns something JSON can hold."""
    started = time.monotonic()
    sem = _slot()
    try:
        await asyncio.wait_for(sem.acquire(), limits.deadline_s)
    except TimeoutError:
        return Outcome(False, killed="busy", seconds=time.monotonic() - started)
    try:
        left = max(1.0, limits.deadline_s - (time.monotonic() - started))
        return await _spawn(target, kwargs or {}, data, limits, left, started)
    finally:
        sem.release()


async def _spawn(
    target: str,
    kwargs: dict[str, Any],
    data: bytes | None,
    limits: Limits,
    deadline: float,
    started: float,
) -> Outcome:
    spec = json.dumps(
        {"target": target, "kwargs": kwargs, "stdin": data is not None, "limits": asdict(limits)}
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-P", "-s", "-B", "-m", "hq_common.untrusted", spec,
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=_env(target),
        cwd="/",
    )  # fmt: skip
    _spawned.append(proc.pid)
    del _spawned[:-64]
    answer = bytearray()

    async def collect() -> None:
        assert proc.stdout is not None
        if data is not None and proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(data)
                await proc.stdin.drain()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.close()
        while len(answer) <= MAX_ANSWER:
            chunk = await proc.stdout.read(64 * 1024)
            if not chunk:
                break
            answer.extend(chunk)
        if len(answer) <= MAX_ANSWER:
            await proc.wait()

    killed_by_us = False
    try:
        await asyncio.wait_for(collect(), deadline)
    except TimeoutError:
        killed_by_us = True
    finally:
        if proc.returncode is None:  # the deadline, an over-long answer, or a cancelled caller
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await asyncio.shield(proc.wait())
    return _outcome(proc.returncode, bytes(answer), killed_by_us, time.monotonic() - started)


def _outcome(code: int | None, answer: bytes, killed_by_us: bool, seconds: float) -> Outcome:
    if len(answer) > MAX_ANSWER:
        return Outcome(False, killed="answer", seconds=seconds)
    if killed_by_us:
        return Outcome(False, killed="deadline", seconds=seconds)
    try:
        doc = json.loads(answer) if answer and len(answer) <= MAX_ANSWER else None
    except ValueError:
        doc = None
    usage = doc.get("usage", {}) if isinstance(doc, dict) else {}
    if code == 0 and isinstance(doc, dict) and "value" in doc:
        return Outcome(True, value=doc["value"], seconds=seconds, usage=usage)
    if code == EXIT_ERROR and isinstance(doc, dict):
        return Outcome(False, error=str(doc.get("error"))[:300], seconds=seconds, usage=usage)
    if code == EXIT_MEMORY:
        killed = "memory"
    elif code in (-signal.SIGXCPU, -signal.SIGKILL):
        # SIGXCPU at the soft CPU limit; SIGKILL at the hard one or from the
        # kernel's OOM killer (the child is its first choice).
        killed = "cpu" if code == -signal.SIGXCPU else "memory"
    else:
        killed = "crash"
    return Outcome(False, killed=killed, seconds=seconds, usage=usage)


# -------------------------------------------------------------- the child --
def _limit(limits: dict[str, Any]) -> None:
    import resource

    with contextlib.suppress(OSError):
        Path("/proc/self/oom_score_adj").write_text("1000")
    mem = int(limits["memory_mb"]) * MIB
    cpu = int(limits["cpu_s"])
    write = int(limits["write_mb"]) * MIB
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (write, write))


def _usage() -> dict[str, Any]:
    import resource

    out: dict[str, Any] = {}
    with contextlib.suppress(OSError):
        for line in Path("/proc/self/status").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("VmPeak", "VmHWM"):
                out[key] = int(value.split()[0])  # KiB
    ru = resource.getrusage(resource.RUSAGE_SELF)
    out["cpu_s"] = round(ru.ru_utime + ru.ru_stime, 3)
    return out


def _answer(fd: int, doc: dict[str, Any]) -> None:
    raw = json.dumps(doc, ensure_ascii=False).encode()
    with os.fdopen(fd, "wb") as out:
        out.write(raw)


def _out_of_memory(exc: BaseException) -> bool:
    """A library that could not map memory (a shared object, a buffer)
    reports it as ImportError or OSError: still the address-space limit."""
    text = str(exc)
    return getattr(exc, "errno", None) == errno.ENOMEM or any(
        mark in text for mark in ("failed to map segment", "Cannot allocate memory")
    )


def child_main(argv: list[str]) -> int:
    import logging

    spec = json.loads(argv[0])
    _limit(spec["limits"])
    logging.disable(logging.CRITICAL)  # parsers' warnings about a hostile file: nowhere
    # The answer goes out on the original stdout; anything a library prints
    # goes to /dev/null instead.
    fd = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.close(devnull)
    try:
        data = sys.stdin.buffer.read() if spec["stdin"] else None
        module, _, name = spec["target"].partition(":")
        fn = getattr(importlib.import_module(module), name)
        value = fn(data, **spec["kwargs"]) if data is not None else fn(**spec["kwargs"])
    except MemoryError:
        os._exit(EXIT_MEMORY)  # nothing more can be allocated: no answer
    except Exception as exc:  # noqa: BLE001 - the file is refused; the parent decides
        if _out_of_memory(exc):
            os._exit(EXIT_MEMORY)
        try:
            _answer(fd, {"error": f"{type(exc).__name__}: {exc}"[:300], "usage": _usage()})
        except MemoryError:
            os._exit(EXIT_MEMORY)
        return EXIT_ERROR
    try:
        _answer(fd, {"value": value, "usage": _usage()})
    except MemoryError:
        os._exit(EXIT_MEMORY)
    return 0


if __name__ == "__main__":
    sys.exit(child_main(sys.argv[1:]))
