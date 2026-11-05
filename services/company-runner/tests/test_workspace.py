"""⟨0.3.0⟩ contract §33.10: the `claude` job's `args.workspace`, the hub's
close of a work and the 30-day sweep."""

from __future__ import annotations

import json
import logging
import stat
import time
from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE, FakeHub, make_route, run
from test_run import drive

from hq_runner import workspace as W
from hq_runner.config import Config, save
from hq_runner.runner import Runner


@pytest.fixture
def spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "hq-workspace"
    monkeypatch.setenv("HQ_RUNNER_WORKSPACES", str(root))
    return root


def claude_job(jid: str, **args: object) -> dict[str, object]:
    return {"id": jid, "kind": "claude", "args": {"brief": "build it", **args}}


def test_a_claude_job_works_in_its_own_persistent_folder(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    spaces: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    # args.cwd is ignored when a workspace is named: the work's folder is the place
    fake_hub.jobs.append(claude_job("w1", workspace="W-000123", cwd=str(repo)))
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "w1" in fake_hub.results, within=60))
    folder = spaces / "W-000123"
    assert json.loads(record.read_text())["cwd"] == str(folder)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(spaces.stat().st_mode) == 0o700
    assert fake_hub.results["w1"]["exit_code"] == 0
    assert fake_hub.result_output("w1")["workspace"] == {"ref": "W-000123", "path": str(folder)}

    # The next turn (a resume) finds the folder as the last one left it.
    (folder / "notes.md").write_text("half done", encoding="utf-8")
    fake_hub.jobs.append(claude_job("w2", workspace="W-000123", session_id="sess-1"))
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "w2" in fake_hub.results, within=60))
    rec = json.loads(record.read_text())
    assert rec["cwd"] == str(folder) and rec["argv"][rec["argv"].index("--resume") + 1] == "sess-1"
    assert (folder / "notes.md").read_text(encoding="utf-8") == "half done"
    state = json.loads(W.state_file(cfg_path).read_text(encoding="utf-8"))
    assert set(state) == {"W-000123"} and state["W-000123"]["closed_at"] is None
    assert stat.S_IMODE(W.state_file(cfg_path).stat().st_mode) == 0o600


@pytest.mark.parametrize("name", ["../etc", "W-1", "/tmp/x", "W-000123/..", 7, ""])
def test_a_workspace_is_only_ever_a_work_ref(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path, name: object
) -> None:
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    fake_hub.jobs.append(claude_job("bad", workspace=name))
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "bad" in fake_hub.results))
    res = fake_hub.results["bad"]
    assert res["exit_code"] == 2 and "W-000123" in res["summary_fa"]
    assert not spaces.exists() or not any(spaces.iterdir())


def test_the_hubs_close_is_recorded_and_the_sweep_removes_after_30_days(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    spaces: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="hq_runner.workspace")
    W.prepare("W-000777", cfg_path)
    W.prepare("W-000778", cfg_path)
    (spaces / "W-000777" / "out.txt").write_text("x", encoding="utf-8")
    fake_hub.closed.append({"workspace": "W-000777", "closed_at": "2025-01-01T00:00:00Z"})
    fake_hub.closed.append({"workspace": "../../etc", "closed_at": "2025-01-01T00:00:00Z"})
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    # The close is recorded (and logged), then the runner's daily sweep, which
    # runs on its first poll, removes the folder: its work closed long ago.
    run(drive(runner, lambda: not (spaces / "W-000777").exists()))
    messages = [r.message for r in caplog.records]
    assert any("W-000777: the hub closed its work at 2025-01-01T00:00:00Z" in m for m in messages)
    assert any("W-000777 removed" in m for m in messages)
    assert any("invalid workspace name" in m for m in messages)
    state = W.load(cfg_path)
    assert "W-000777" not in state and state["W-000778"]["closed_at"] is None
    assert (spaces / "W-000778").is_dir()
    # A second close of the same work is a no-op.
    assert W.close([{"workspace": "W-000778", "closed_at": "2026-11-04T00:00:00Z"}], cfg_path) == [
        "W-000778"
    ]
    assert W.close(["W-000778"], cfg_path) == []


def test_the_sweep_keeps_a_folder_until_30_days_after_its_close(
    cfg_path: Path, spaces: Path
) -> None:
    W.prepare("W-000900", cfg_path)
    closed = time.time()
    W.close([{"workspace": "W-000900", "closed_at": W._iso(closed)}], cfg_path)
    assert W.sweep(cfg_path, now=closed + 29 * 86400) == []
    assert (spaces / "W-000900").is_dir()
    assert W.sweep(cfg_path, now=closed + 30 * 86400 + 1) == ["W-000900"]
    assert not (spaces / "W-000900").exists()
    assert W.load(cfg_path) == {}
    # A workspace never closed by the hub is never swept.
    W.prepare("W-000901", cfg_path)
    assert W.sweep(cfg_path, now=closed + 400 * 86400) == []
