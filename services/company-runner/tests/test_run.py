from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from conftest import HUB, FakeHub, fast_probe, make_route, no_dns, run

from hq_runner.config import Config, load
from hq_runner.hub import Backoff
from hq_runner.jobs import JobContext, JobResult
from hq_runner.net import Route
from hq_runner.runner import EXIT_REPAIR, EXIT_REVOKED, Runner

ROTATED = "hqr1_rotated_1_" + "ABCDEFGHIJKLMNOP"


async def drive(runner: Runner, until: Callable[[], bool], within: float = 20.0) -> int:
    task = asyncio.create_task(runner.run())
    deadline = time.monotonic() + within
    while not until() and not task.done():
        assert time.monotonic() < deadline, "condition not reached in time"
        await asyncio.sleep(0.02)
    runner.stop()
    return await asyncio.wait_for(task, 30)


def exec_job(jid: str, cmd: str, **args: Any) -> dict[str, Any]:
    return {"id": jid, "kind": "exec", "state": "queued", "args": {"cmd": cmd, **args}}


def test_exec_streams_lines_masks_secrets_and_posts_result(
    fake_hub: FakeHub, cfg: Config, tmp_path: Path
) -> None:
    fake_hub.jobs.append(
        exec_job(
            "j1",
            "echo hello; echo oops >&2; echo DB_PASSWORD=s3cr3tvalue; "
            "echo 'Authorization: Bearer abcdefghijklmnop'; pwd; exit 3",
            cwd=str(tmp_path),
        )
    )
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    assert run(drive(runner, lambda: "j1" in fake_hub.results)) == 0
    out = fake_hub.texts("j1")
    assert out[0] == "hello"
    assert "DB_PASSWORD=[redacted]" in out
    assert "Authorization: Bearer [redacted]" in out
    assert str(tmp_path) in out
    assert fake_hub.texts("j1", "stderr") == ["oops"]
    assert all("s3cr3tvalue" not in str(e) for e in fake_hub.events["j1"])
    seqs = [e["seq"] for e in fake_hub.events["j1"]]
    assert seqs == sorted(seqs) and seqs[0] == 1 and len(set(seqs)) == len(seqs)
    assert fake_hub.results["j1"]["exit_code"] == 3
    assert fake_hub.results["j1"]["summary_fa"]


def test_poll_is_the_heartbeat(fake_hub: FakeHub, cfg: Config) -> None:
    runner = Runner(cfg, make_route(fake_hub, "10.10.1.4"), persist_state=False)
    polls = lambda: [r for r in fake_hub.requests if "/jobs/next" in r[1]]  # noqa: E731
    run(drive(runner, lambda: len(polls()) >= 2))
    url, headers = polls()[0][1], polls()[0][2]
    q = httpx.URL(url).params
    assert q["via"] == "private" and q["slots"] == "2" and q["hub_rtt_ms"] == "1.5"
    assert headers["x-hq-runner-via"] == "private"
    assert headers["x-hq-runner-hub-rtt-ms"] == "1.5"
    assert headers["x-hq-runner-version"]
    assert headers["authorization"] == f"Bearer {cfg.runner_token}"


def _pid_alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def test_cancel_kills_the_process_group(fake_hub: FakeHub, cfg: Config, tmp_path: Path) -> None:
    pidfile = tmp_path / "child.pid"
    fake_hub.jobs.append(exec_job("j2", f"sleep 60 & echo $! > {pidfile}; echo started; wait"))
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)

    async def scenario() -> int:
        task = asyncio.create_task(drive(runner, lambda: "j2" in fake_hub.results))
        while not (pidfile.exists() and pidfile.read_text().strip()):
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.2)
        fake_hub.cancels.append("j2")
        start = time.monotonic()
        code = await task
        assert time.monotonic() - start < 10
        return code

    assert run(scenario()) == 0
    assert fake_hub.results["j2"]["exit_code"] == 130
    child = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _pid_alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(child)


def test_exec_timeout(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.jobs.append(exec_job("j3", "echo before; sleep 30", timeout_s=1))
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    start = time.monotonic()
    run(drive(runner, lambda: "j3" in fake_hub.results))
    assert time.monotonic() - start < 10
    assert fake_hub.results["j3"]["exit_code"] == 124
    assert "before" in fake_hub.texts("j3")


def test_output_is_capped(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.jobs.append(exec_job("j4", "for i in $(seq 1 500); do echo line-$i-xxxxxxxxxx; done"))
    runner = Runner(cfg, make_route(fake_hub), persist_state=False, max_output=2000)
    run(drive(runner, lambda: "j4" in fake_hub.results))
    assert sum(len(t) for t in fake_hub.texts("j4")) <= 2000
    assert any("truncated" in t for t in fake_hub.texts("j4", "progress"))
    assert fake_hub.results["j4"]["exit_code"] == 0


def test_at_most_two_jobs_at_once(fake_hub: FakeHub, cfg: Config) -> None:
    active = 0
    peak = 0

    async def slow(ctx: JobContext) -> JobResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.3)
        active -= 1
        return JobResult(0, "ok")

    for i in range(5):
        fake_hub.jobs.append({"id": f"c{i}", "kind": "slow", "args": {}})
    runner = Runner(cfg, make_route(fake_hub), handlers={"slow": slow}, persist_state=False)
    run(drive(runner, lambda: len(fake_hub.results) == 5))
    assert peak == 2


def test_unknown_kind_fails_cleanly(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.jobs.append({"id": "u1", "kind": "teleport", "args": {}})
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: "u1" in fake_hub.results))
    assert fake_hub.results["u1"]["exit_code"] == 2


def test_401_stops_and_asks_to_pair_again(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.tokens = {"someone-else"}
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    assert run(asyncio.wait_for(runner.run(), 10)) == EXIT_REPAIR


def test_revoked_stops_and_is_remembered(fake_hub: FakeHub, cfg: Config, cfg_path: Path) -> None:
    fake_hub.revoked = True
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path)
    assert run(asyncio.wait_for(runner.run(), 10)) == EXIT_REVOKED
    saved = load(cfg_path)
    assert saved is not None and saved.state == "revoked"
    again = Runner(saved, make_route(fake_hub), cfg_path=cfg_path)
    assert run(again.run()) == EXIT_REVOKED


def test_token_rotates_every_24h(fake_hub: FakeHub, cfg: Config, cfg_path: Path) -> None:
    cfg.rotated_at = time.time() - 25 * 3600
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path)
    run(
        drive(
            runner,
            lambda: (
                fake_hub.rotations == 1 and any("/jobs/next" in r[1] for r in fake_hub.requests)
            ),
        )
    )
    assert fake_hub.rotations == 1
    saved = load(cfg_path)
    assert saved is not None and saved.runner_token == ROTATED
    assert os.stat(cfg_path).st_mode & 0o777 == 0o600
    nxt = next(r for r in fake_hub.requests if "/jobs/next" in r[1])
    assert nxt[2]["authorization"] == "Bearer hqr1_rotated_1_ABCDEFGHIJKLMNOP"
    assert "hqr1_rotated_1" not in cfg_path.with_name("state.json").read_text()


def test_network_errors_back_off_with_jitter(fake_hub: FakeHub, cfg: Config) -> None:
    failures = 4
    inner = fake_hub.transport()

    async def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal failures
        if failures > 0:
            failures -= 1
            raise httpx.ConnectError("unreachable", request=request)
        return await inner.handle_async_request(request)

    delays: list[float] = []

    async def record(d: float) -> None:
        delays.append(d)

    route = Route(
        HUB, None, transport=httpx.MockTransport(flaky), probe=fast_probe, resolver=no_dns
    )
    runner = Runner(
        cfg,
        route,
        sleep=record,
        backoff=Backoff(base=1.0, cap=60.0, rand=lambda: 1.0),
        persist_state=False,
    )
    run(drive(runner, lambda: any("/jobs/next" in r[1] for r in fake_hub.requests)))
    assert delays[:4] == [1.0, 2.0, 4.0, 8.0]
    jitter = Backoff(base=1.0, rand=lambda: 0.0)
    assert jitter.next() == 0.5
