from __future__ import annotations

import asyncio
import base64
import hashlib
import stat
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeHub, make_route, run
from test_run import drive

import hq_runner.jobs as jobs
from hq_runner.config import Config
from hq_runner.hub import Hub
from hq_runner.jobs import (
    JobContext,
    JobError,
    parse_publish_answer,
    run_netcheck,
    run_read,
    run_write,
)
from hq_runner.mask import Masker
from hq_runner.runner import Runner


class ListSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, type_: str, data: dict[str, Any]) -> None:
        self.events.append((type_, data))


def ctx(
    cfg: Config, args: dict[str, Any], hub: FakeHub | None = None, kind: str = "x"
) -> JobContext:
    route = make_route(hub or FakeHub())
    return JobContext(
        {"id": "j", "kind": kind, "args": args},
        Hub(route, lambda: cfg.runner_token),
        ListSink(),
        asyncio.Event(),
        Masker(),
        cfg,
    )  # type: ignore[arg-type]


# -- read / write ------------------------------------------------------------------------
def test_write_keeps_a_backup_and_read_returns_the_file(cfg: Config, tmp_path: Path) -> None:
    f = tmp_path / "app.env"
    f.write_text("OLD=1\n")
    f.chmod(0o640)
    res = run(run_write(ctx(cfg, {"path": str(f), "content": "NEW=2\n"})))
    assert res.exit_code == 0
    assert f.read_text() == "NEW=2\n"
    assert (tmp_path / "app.env.hq-bak").read_text() == "OLD=1\n"
    assert stat.S_IMODE(f.stat().st_mode) == 0o640  # the mode is kept
    assert res.output == {
        "path": str(f),
        "size": 6,
        "sha256": hashlib.sha256(b"NEW=2\n").hexdigest(),
        "backup": str(tmp_path / "app.env.hq-bak"),
    }
    res = run(run_read(ctx(cfg, {"path": str(f)})))
    assert res.exit_code == 0 and res.output is not None
    assert res.output["content"] == "NEW=2\n" and res.output["encoding"] == "utf8"


def test_write_new_binary_file_without_backup(cfg: Config, tmp_path: Path) -> None:
    f = tmp_path / "logo.bin"
    data = bytes(range(256))
    res = run(
        run_write(
            ctx(
                cfg, {"path": str(f), "content_b64": base64.b64encode(data).decode(), "mode": "600"}
            )
        )
    )
    assert res.output is not None and res.output["backup"] is None
    assert f.read_bytes() == data and stat.S_IMODE(f.stat().st_mode) == 0o600
    read = run(run_read(ctx(cfg, {"path": str(f)})))
    assert read.output is not None and read.output["encoding"] == "base64"
    assert base64.b64decode(read.output["content"]) == data


def test_read_write_limits(cfg: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "MAX_FILE_BYTES", 10)
    big = tmp_path / "big"
    big.write_bytes(b"x" * 11)
    with pytest.raises(JobError):
        run(run_read(ctx(cfg, {"path": str(big)})))
    with pytest.raises(JobError):
        run(run_write(ctx(cfg, {"path": str(tmp_path / "y"), "content": "x" * 11})))
    with pytest.raises(JobError):
        run(run_read(ctx(cfg, {"path": str(tmp_path / "missing")})))
    with pytest.raises(JobError):
        run(run_write(ctx(cfg, {"path": str(tmp_path / "no" / "dir" / "f"), "content": "x"})))


def test_read_and_write_through_the_runner(fake_hub: FakeHub, cfg: Config, tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("v1")
    fake_hub.jobs.append({"id": "w1", "kind": "write", "args": {"path": str(f), "content": "v2"}})
    fake_hub.jobs.append({"id": "r1", "kind": "read", "args": {"path": str(f)}})
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: {"w1", "r1"} <= fake_hub.results.keys()))
    assert fake_hub.results["w1"]["exit_code"] == 0
    assert fake_hub.result_output("r1")["content"] in ("v1", "v2")  # order of the two is not fixed
    assert f.read_text() == "v2"


# -- publish ---------------------------------------------------------------------------------
PUBLISH_CMD = (
    'test "$HQ_PUBLISH_COUNT" = 2 || exit 9; '
    'cmp -s "$HQ_PUBLISH_FILE_1" <(printf "IMG") || exit 8; '
    'test "$(cat "$HQ_PUBLISH_CAPTION_FILE")" = "$HQ_PUBLISH_CAPTION" || exit 7; '
    'echo "posting $(basename "$HQ_PUBLISH_FILE_2") with: $HQ_PUBLISH_CAPTION"; '
    'echo \'{"external_id": "1789", "url": "https://instagram.example/p/1789"}\''
)


def test_publish_downloads_runs_the_command_and_parses_its_answer(
    fake_hub: FakeHub, cfg: Config
) -> None:
    fake_hub.files = {"/api/v1/files/f1": b"IMG", "/api/v1/files/f2": b"VID"}
    fake_hub.jobs.append(
        {
            "id": "p1",
            "kind": "publish",
            "args": {
                "files": [
                    {"url": "/api/v1/files/f1", "name": "cover.jpg"},
                    {"url": "https://hq.coinepro.test/api/v1/files/f2", "name": "reel.mp4"},
                ],
                "caption": "سلام دنیا",
                "command": PUBLISH_CMD,
            },
        }
    )
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: "p1" in fake_hub.results))
    assert fake_hub.results["p1"]["exit_code"] == 0, fake_hub.events["p1"]
    assert fake_hub.result_output("p1") == {
        "external_id": "1789",
        "url": "https://instagram.example/p/1789",
    }
    assert any(t == "posting 02-reel.mp4 with: سلام دنیا" for t in fake_hub.texts("p1"))
    downloads = [r for r in fake_hub.requests if "/files/" in r[1]]
    assert len(downloads) == 2 and all(
        r[2]["authorization"].startswith("Bearer ") for r in downloads
    )


def test_publish_refuses_files_outside_the_hub(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.jobs.append(
        {
            "id": "p2",
            "kind": "publish",
            "args": {
                "files": [{"url": "https://evil.example/x.jpg"}],
                "command": "echo '{\"external_id\": 1}'",
            },
        }
    )
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: "p2" in fake_hub.results))
    assert fake_hub.results["p2"]["exit_code"] == 1
    assert not any("evil.example" in r[1] for r in fake_hub.requests)


def test_publish_without_an_answer_fails(fake_hub: FakeHub, cfg: Config) -> None:
    fake_hub.jobs.append(
        {"id": "p3", "kind": "publish", "args": {"files": [], "command": "echo done"}}
    )
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: "p3" in fake_hub.results))
    assert fake_hub.results["p3"]["exit_code"] == 1


def test_parse_publish_answer() -> None:
    assert parse_publish_answer(["log", '{"external_id": 5, "url": null}', "bye"]) == {
        "external_id": "5",
        "url": None,
    }
    assert parse_publish_answer(['{"id": 1}', "not json {"]) is None


# -- netcheck ------------------------------------------------------------------------------------
def test_netcheck_reports_each_port(cfg: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> Any:
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        open_port = server.sockets[0].getsockname()[1]
        closed = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        closed_port = closed.sockets[0].getsockname()[1]
        closed.close()
        await closed.wait_closed()

        async def no_ping(ip: str) -> None:
            return None

        monkeypatch.setattr(jobs, "ping", no_ping)
        hub_srv = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.2", 0)
        hub_port = hub_srv.sockets[0].getsockname()[1]
        cfg.hub_ip = "127.0.0.2"  # the hub's private address (another loopback address here)
        c = ctx(
            cfg,
            {
                "targets": [
                    {"name": "trade-yar", "ip": "127.0.0.1", "ports": [open_port, closed_port]}
                ]
            },
        )
        c.hub.route.port = hub_port  # the hub's port on its private address
        try:
            return await run_netcheck(c)
        finally:
            server.close()
            hub_srv.close()

    res = run(scenario())
    assert res.exit_code == 0
    out = res.output
    assert (
        set(out) == {"from", "via", "results"}
        and out["from"] == "fx-main"
        and out["via"] == "public"
    )
    assert [r["name"] for r in out["results"]] == ["hub", "trade-yar", "trade-yar"]
    for r in out["results"]:
        assert set(r) == {"name", "ip", "port", "ok", "ms", "error"}
    assert (
        out["results"][0]["ok"] and out["results"][1]["ok"] and out["results"][1]["ms"] is not None
    )
    assert out["results"][2]["ok"] is False and out["results"][2]["error"]


def test_netcheck_with_ping_and_bad_targets(cfg: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ping(ip: str) -> tuple[bool, float | None, str | None]:
        return (True, 0.3, None)

    async def refuse(ip: str, port: int, limit_s: float) -> float:
        raise TimeoutError

    monkeypatch.setattr(jobs, "ping", fake_ping)
    res = run(
        run_netcheck(
            ctx(cfg, {"targets": [{"name": "pc", "ip": "10.10.1.1", "ports": [22]}]}), probe=refuse
        )
    )
    assert res.output["results"] == [
        {"name": "pc", "ip": "10.10.1.1", "port": None, "ok": True, "ms": 0.3, "error": None},
        {"name": "pc", "ip": "10.10.1.1", "port": 22, "ok": False, "ms": None, "error": "timeout"},
    ]
    for bad in ([{"ip": "not-an-ip", "ports": [1]}], [{"ip": "10.0.0.1", "ports": [70000]}], "x"):
        with pytest.raises(JobError):
            run(run_netcheck(ctx(cfg, {"targets": bad})))


def test_netcheck_accepts_one_port_targets_and_echoes_their_key(
    cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_ping(ip: str) -> None:
        return None

    async def answer(ip: str, port: int, limit_s: float) -> float:
        assert limit_s == 3.0
        if port == 22:
            raise ConnectionRefusedError(111, "Connection refused")
        return 0.8

    monkeypatch.setattr(jobs, "ping", no_ping)
    cfg.hub_ip = "10.10.1.4"
    targets = [
        {"to": "hub", "host": "10.10.1.4", "port": 443},
        {"to": "srv-2", "host": "10.10.1.3", "port": 22},
        {"to": "srv-2", "host": "10.10.1.3", "port": 443},
    ]
    res = run(run_netcheck(ctx(cfg, {"targets": targets, "timeout_ms": 3000}), probe=answer))
    rows = res.output["results"]
    assert [(r["to"], r["port"], r["ok"]) for r in rows] == [
        ("hub", 443, True),
        ("srv-2", 22, False),
        ("srv-2", 443, True),
    ]
    assert rows[1]["error"] == "Connection refused" and rows[1]["ip"] == "10.10.1.3"
