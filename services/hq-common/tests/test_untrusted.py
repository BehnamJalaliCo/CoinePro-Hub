"""hq_common.untrusted (prompt 07.1 §1.2): every parse of outside content runs
in a child process with hard limits, and the parent always gets an answer."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from hq_common import untrusted as U

QUICK = U.Limits(memory_mb=128, cpu_s=5, deadline_s=10)


@pytest.fixture(autouse=True)
def one_slot() -> Iterator[None]:
    U.set_slots(1)
    yield
    U.set_slots(1)


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


async def test_a_job_answers_with_its_value_and_the_childs_usage() -> None:
    got = await U.run("untrusted_jobs:echo", data=b"hello", kwargs={"suffix": "!"}, limits=QUICK)
    assert got.ok and got.value == "hello!" and got.killed is None and got.error is None
    assert got.usage["VmPeak"] > 0 and got.usage["cpu_s"] >= 0
    assert gone(U._spawned[-1])


async def test_a_refused_file_is_an_error_not_a_kill() -> None:
    got = await U.run("untrusted_jobs:refuse", limits=QUICK)
    assert not got.ok and got.killed is None
    assert got.error == "ValueError: not a file this job accepts"
    assert got.reason.startswith("ValueError")


async def test_the_memory_limit_stops_the_child() -> None:
    got = await U.run("untrusted_jobs:hog", kwargs={"mb": 400}, limits=QUICK)
    assert not got.ok and got.killed == "memory" and got.reason == "stopped: memory"


async def test_the_cpu_limit_stops_the_child() -> None:
    started = time.monotonic()
    got = await U.run("untrusted_jobs:spin", limits=U.Limits(cpu_s=1, deadline_s=20))
    assert not got.ok and got.killed == "cpu"
    assert time.monotonic() - started < 10


async def test_the_deadline_kills_the_child() -> None:
    started = time.monotonic()
    got = await U.run("untrusted_jobs:sleep", kwargs={"seconds": 60}, limits=U.Limits(deadline_s=1))
    assert not got.ok and got.killed == "deadline"
    assert time.monotonic() - started < 5
    assert gone(U._spawned[-1])


async def test_an_answer_over_the_cap_is_not_read() -> None:
    got = await U.run("untrusted_jobs:big_answer", kwargs={"mb": 6}, limits=U.Limits(memory_mb=256))
    assert not got.ok and got.killed == "answer"


async def test_the_child_has_no_secret_and_its_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HQ_DB_PASSWORD", "never-in-the-child")
    got = await U.run("untrusted_jobs:inside", limits=U.Limits(memory_mb=150, cpu_s=7))
    assert got.ok, got
    seen = got.value
    assert "HQ_DB_PASSWORD" not in seen["env"]
    assert set(seen["env"]) <= {
        "PATH", "LANG", "LC_CTYPE", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
        "MALLOC_ARENA_MAX", "OMP_NUM_THREADS",
    }  # fmt: skip
    assert seen["as"] == [150 * U.MIB, 150 * U.MIB]
    assert seen["cpu"] == [7, 9] and seen["fsize"] == [0, 0] and seen["core"] == [0, 0]
    assert seen["oom"] == "1000" and seen["cwd"] == "/"


async def test_the_child_writes_only_what_its_limits_allow(tmp_path: Path) -> None:
    out = tmp_path / "out"
    got = await U.run("untrusted_jobs:write", kwargs={"path": str(out), "size": 1024}, limits=QUICK)
    assert not got.ok  # RLIMIT_FSIZE 0: no file at all
    got = await U.run(
        "untrusted_jobs:write",
        kwargs={"path": str(out), "size": 1024},
        limits=U.Limits(memory_mb=128, write_mb=1),
    )
    assert got.ok and got.value == 1024


async def test_children_queue_for_their_slot_and_give_up_at_the_deadline() -> None:
    slow = asyncio.create_task(U.run("untrusted_jobs:sleep", kwargs={"seconds": 3}, limits=QUICK))
    await asyncio.sleep(0.5)
    started = time.monotonic()
    busy = await U.run("untrusted_jobs:echo", data=b"x", limits=U.Limits(deadline_s=1))
    assert busy.killed == "busy" and time.monotonic() - started < 2
    assert (await slow).ok
    U.set_slots(2)
    a, b = await asyncio.gather(
        U.run("untrusted_jobs:sleep", kwargs={"seconds": 1}, limits=QUICK),
        U.run("untrusted_jobs:sleep", kwargs={"seconds": 1}, limits=QUICK),
    )
    assert a.ok and b.ok


async def test_a_cancelled_caller_kills_its_child() -> None:
    task = asyncio.create_task(U.run("untrusted_jobs:sleep", kwargs={"seconds": 60}, limits=QUICK))
    await asyncio.sleep(1.0)
    pid = U._spawned[-1]
    assert not gone(pid)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gone(pid)
