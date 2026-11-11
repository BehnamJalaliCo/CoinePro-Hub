"""⟨0.3.4⟩ The workshop's wall between the companies (contract §43.9).

The owner, 2026-11-10: «نکته امنیتی هم اجرا بشه و کار راه بیفته نه اینکه گیر بکنه». A turn of
one company cannot read another company's work folder, the runner's token or this server's own
Claude transcripts; and a server where the wall cannot go up still runs the turn.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import FAKE_CLAUDE, FakeHub, make_route, run
from test_claude import ClassifyServer
from test_run import drive

from hq_runner import sandbox
from hq_runner.config import Config, save
from hq_runner.runner import Runner

TOKEN = "sk-ant-oat01-" + "w" * 95
needs_landlock = pytest.mark.skipif(
    sandbox.abi() < sandbox.MIN_ABI, reason="this kernel has no Landlock"
)


@pytest.fixture
def classify(cfg: Config) -> Any:
    srv = ClassifyServer(cfg.runner_token)
    yield srv
    srv.server.shutdown()


@pytest.fixture
def place(tmp_path: Path, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """A server: its home (the runner's folder in it), two works, and this server's ~/.claude."""
    home = tmp_path / "home"
    ws = home / "hq-workspace"
    for d in (ws / "W-000111", ws / "W-000222", home / ".claude" / "projects", home / ".cache"):
        d.mkdir(parents=True)
    (ws / "W-000222" / "notes.txt").write_text("the other company's file")
    (home / ".claude" / "projects" / "t.jsonl").write_text("another turn's transcript")
    (home / ".claude.json").write_text("{}")
    (home / ".npmrc").write_text("registry=https://example.invalid/")
    (home / ".cache" / "tool").write_text("installed")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HQ_RUNNER_WORKSPACES", str(ws))
    monkeypatch.delenv("HQ_RUNNER_SANDBOX", raising=False)
    sandbox.forget_probe()
    return {"home": home, "ws": ws, "cfg": cfg_path}


def the_plan(place: dict[str, Path]) -> sandbox.Plan:
    p = sandbox.plan("W-000111", place["ws"] / "W-000111", place["ws"], place["cfg"], None)
    sandbox.prepare(p)
    return p


# ------------------------------------------------------------------ the rules --
def test_every_entry_beside_the_closed_ones_is_open(tmp_path: Path) -> None:
    home = tmp_path / "h"
    for d in ("ws/W-1", "ws/W-2", ".config/hq-runner", ".config/git", ".cache", ".claude"):
        (home / d).mkdir(parents=True)
    (home / ".npmrc").write_text("x")
    os.symlink(home / "ws", home / "alias")  # a link to a closed folder opens nothing
    opened = sandbox.open_paths(
        [home / "ws", home / ".config" / "hq-runner", home / ".claude"], [home / "ws" / "W-1"]
    )
    assert str(home / ".cache") in opened and str(home / ".npmrc") in opened
    assert str(home / ".config" / "git") in opened and str(home / "ws" / "W-1") in opened
    for closed in ("ws", "ws/W-2", ".config", ".config/hq-runner", ".claude", "alias"):
        assert str(home / closed) not in opened, closed
    # no folder that holds a closed one is opened whole
    assert str(home) not in opened and str(tmp_path) not in opened and "/" not in opened
    assert "/usr" in opened and "/etc" in opened


def test_the_turns_home_links_what_is_open_and_keeps_what_the_work_made(tmp_path: Path) -> None:
    real, mine = tmp_path / "real", tmp_path / "mine"
    for d in ("hq-workspace/W-1", ".config/hq-runner", ".config/git", ".cache", ".claude"):
        (real / d).mkdir(parents=True)
    (real / ".npmrc").write_text("a")
    (real / ".config" / "hq-runner" / "config.json").write_text("token")
    (real / ".config" / "git" / "config").write_text("[user]")
    (real / ".claude.json").write_text("{}")
    closed = [real / "hq-workspace", real / ".config" / "hq-runner", real / ".claude",
              real / ".claude.json"]  # fmt: skip
    sandbox.make_home(real, mine, closed)
    assert sorted(os.listdir(mine)) == [".cache", ".config", ".npmrc"]
    assert os.readlink(mine / ".cache") == str(real / ".cache")
    assert not (mine / ".npmrc").is_symlink() and (mine / ".npmrc").read_text() == "a"
    # the folder that holds the runner's own is a folder of the turn's, without it
    assert not (mine / ".config").is_symlink() and os.listdir(mine / ".config") == ["git"]
    # what the work made stays; a link whose target went is removed; a new entry is linked
    (mine / ".bun").mkdir()
    (mine / ".npmrc").write_text("mine")
    (real / ".cache").rmdir()
    (real / ".local").mkdir()
    sandbox.make_home(real, mine, closed)
    assert sorted(os.listdir(mine)) == [".bun", ".config", ".local", ".npmrc"]
    assert (mine / ".npmrc").read_text() == "mine"


def test_a_session_is_found_on_the_other_side_of_the_wall(tmp_path: Path) -> None:
    real, mine, cwd = tmp_path / "real", tmp_path / "mine", "/home/studio/hq-workspace/W-000123"
    assert sandbox.project_dir(cwd) == "-home-studio-hq-workspace-W-000123"
    store = real / ".claude" / "projects" / sandbox.project_dir(cwd)
    (store / "abc-1").mkdir(parents=True)
    (store / "abc-1.jsonl").write_text("turn 1")
    (store / "abc-1" / "side.json").write_text("{}")
    (store / "other.jsonl").write_text("another session")
    assert sandbox.carry_session(real, mine, cwd, "abc-1") is True
    there = mine / ".claude" / "projects" / sandbox.project_dir(cwd)
    assert (there / "abc-1.jsonl").read_text() == "turn 1" and (
        there / "abc-1" / "side.json"
    ).exists()
    assert not (there / "other.jsonl").exists()
    assert sandbox.carry_session(real, mine, cwd, "../../etc") is False


# -------------------------------------------------------------------- the wall --
CHECK = r"""
import json, os, sys
def t(fn):
    try:
        fn()
        return "ok"
    except OSError as exc:
        return type(exc).__name__
ws, cfg, home = sys.argv[1:4]
print(json.dumps({
    "other_work": t(lambda: open(ws + "/W-000222/notes.txt").read()),
    "list_works": t(lambda: os.listdir(ws)),
    "runner_token": t(lambda: open(cfg).read()),
    "transcripts": t(lambda: os.listdir(home + "/.claude/projects")),
    "claude_json": t(lambda: open(home + "/.claude.json").read()),
    "own_write": t(lambda: open(ws + "/W-000111/a.txt", "w").write("x")),
    "own_move": t(lambda: os.rename(ws + "/W-000111/a.txt", os.environ["TMPDIR"] + "/a.txt")),
    "home_new": t(lambda: os.mkdir(os.environ["HOME"] + "/.newtool")),
    "home_tool": t(lambda: open(os.environ["HOME"] + "/.cache/tool").read()),
    "system": t(lambda: open("/etc/hostname").read()),
}))
"""


@needs_landlock
def test_a_walled_process_cannot_read_another_company_and_works_in_its_own(
    place: dict[str, Path], cfg: Config
) -> None:
    save(cfg, place["cfg"])
    p = the_plan(place)
    argv = sandbox.wrap(
        p, [sys.executable, "-c", CHECK, str(place["ws"]), str(place["cfg"]), str(place["home"])]
    )
    out = subprocess.run(argv, env=sandbox.env_of(p, dict(os.environ)), cwd=p.work,
                         capture_output=True, text=True, timeout=60, check=False)  # fmt: skip
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    for closed in ("other_work", "list_works", "runner_token", "transcripts", "claude_json"):
        assert seen[closed] == "PermissionError", (closed, seen)
    for opened in ("own_write", "own_move", "home_new", "home_tool", "system"):
        assert seen[opened] == "ok", (opened, seen)
    # the same without the wall reads them all: it is the wall that closes them
    plain = subprocess.run(argv[argv.index("--") + 1 :], env=sandbox.env_of(p, dict(os.environ)),
                           cwd=p.work, capture_output=True, text=True, timeout=60, check=False)  # fmt: skip
    assert json.loads(plain.stdout)["other_work"] == "ok"
    assert run(sandbox.probe(p, dict(os.environ), str(FAKE_CLAUDE))) is None


def test_the_hook_asks_the_runner_over_its_socket(tmp_path: Path) -> None:
    asked: list[str] = []

    async def classify(cmd: str) -> tuple[str | None, str | None]:
        asked.append(cmd)
        if "unreachable" in cmd:
            return None, "hub answered 503"
        return ("db_drop" if "DROP" in cmd else None), None

    async def main() -> list[tuple[str | None, str | None]]:
        # a path longer than a socket's own limit goes through its folder
        deep = tmp_path / ("d" * 60) / ("e" * 60)
        deep.mkdir(parents=True)
        server = await sandbox.serve_hook(deep / "hook.sock", classify)
        try:
            return [
                await asyncio.to_thread(sandbox.ask_hook_socket, str(deep / "hook.sock"), c)
                for c in ("ls", "psql -c 'DROP DATABASE x'", "unreachable")
            ]
        finally:
            server.close()
            await server.wait_closed()

    assert run(main()) == [(None, None), ("db_drop", None), (None, "hub answered 503")]
    assert asked == ["ls", "psql -c 'DROP DATABASE x'", "unreachable"]
    assert sandbox.ask_hook_socket(str(tmp_path / "none.sock"), "ls")[1] is not None  # fails closed


# -------------------------------------------------------------------- the turn --
def turn(jid: str, brief: str, **more: Any) -> dict[str, Any]:
    return {
        "id": jid,
        "kind": "claude",
        "claude_oauth": TOKEN,
        "args": {"brief": brief, "workspace": "W-000111", "sandbox": "auto", **more},
    }


def go(
    fake_hub: FakeHub, cfg: Config, place: dict[str, Path], job: dict[str, Any]
) -> dict[str, Any]:
    fake_hub.jobs.append(job)
    runner = Runner(cfg, make_route(fake_hub), cfg_path=place["cfg"], persist_state=False)
    run(drive(runner, lambda: job["id"] in fake_hub.results, within=90))
    return fake_hub.results[job["id"]]


@needs_landlock
def test_a_workshop_turn_runs_behind_the_wall(
    fake_hub: FakeHub,
    cfg: Config,
    place: dict[str, Path],
    classify: ClassifyServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = place["ws"] / "W-000111" / "rec.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    cfg.hub = classify.url
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, place["cfg"])
    other = place["ws"] / "W-000222" / "notes.txt"
    mine = place["ws"] / "W-000111" / "out" / "made.txt"
    brief = (
        f"Make it. [[fake:read:{other}]] [[fake:read:{place['cfg']}]] [[fake:write:{mine}]] "
        "[[bash:psql -c 'DROP DATABASE prod']] [[bash:ls]]"
    )
    result = go(fake_hub, cfg, place, turn("w1", brief, session_id="sess-1"))
    assert result["exit_code"] == 0, result
    assert result["data"]["sandbox"] == {"state": "on", "kind": "landlock"}

    rec = json.loads(record.read_text())
    private = place["ws"] / ".hq" / "W-000111"
    # the brief went in on stdin (no other turn reads it from the process list), the turn has
    # a home and a tmp of its own, and it was never told where the runner's token is
    assert rec["brief_on_stdin"] is True and brief not in rec["argv"]
    assert rec["home"] == str(private / "home") and rec["tmpdir"] == str(private / "tmp")
    assert rec["runner_config_env"] is None
    assert rec["cwd"] == str(place["ws"] / "W-000111")

    text = "\n".join(
        e["data"]["data"].get("text", "")
        for e in fake_hub.events["w1"]
        if e["type"] == "session_event" and e["data"]["type"] == "message"
    )
    assert f"read {other} -> PermissionError" in text
    assert f"read {place['cfg']} -> PermissionError" in text
    assert f"write {mine} -> ok" in text and mine.read_text() == "made"

    # the hook still classified both commands, through the runner (its token never went in)
    assert [c[0]["cmd"] for c in classify.calls] == ["psql -c 'DROP DATABASE prod'", "ls"]
    assert classify.calls[0][1]["X-HQ-Runner-Job"] == "w1"
    events = [e["data"] for e in fake_hub.events["w1"] if e["type"] == "session_event"]
    assert any(e["type"] == "approval_request" for e in events)
    assert not (private / "job").exists() and not (private / "tmp").exists()  # the turn's own


@needs_landlock
def test_a_walled_session_that_does_not_start_runs_without_the_wall_only_when_the_wall_broke(
    fake_hub: FakeHub, cfg: Config, place: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    record = place["ws"] / "W-000111" / "rec.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, place["cfg"])
    # the wall works on this server: a session that does not start behind it (its turn's own
    # files may stop it, on purpose) is never run again without it, and no other turn loses it
    result = go(fake_hub, cfg, place, turn("w2", "Make it. [[fake:wallfail]]"))
    assert result["exit_code"] != 0, result
    assert result["data"]["sandbox"] == {"state": "on", "kind": "landlock"}
    assert not record.exists()  # the CLI never ran unwalled
    result = go(fake_hub, cfg, place, turn("w2b", "hello"))
    assert result["exit_code"] == 0 and result["data"]["sandbox"]["state"] == "on"

    # the wall itself fails its probe now: the owner's `auto`, the turn runs without it
    real = sandbox._probe_once
    calls = [0]

    async def breaks_later(*a: Any) -> str | None:
        calls[0] += 1
        return await real(*a) if calls[0] == 1 else "the probe failed: broken"

    monkeypatch.setattr(sandbox, "_probe_once", breaks_later)
    sandbox.forget_probe()
    result = go(fake_hub, cfg, place, turn("w2c", "Make it. [[fake:wallfail]]"))
    assert result["exit_code"] == 0, result  # the work was done
    assert result["data"]["sandbox"] == {
        "state": "off",
        "why": "the walled session did not start",
    }
    rec = json.loads(record.read_text())
    assert rec["home"] == str(place["home"])


def test_what_the_last_turn_left_in_its_area_never_keeps_the_wall_down(
    place: dict[str, Path],
) -> None:
    """A turn could replace its tmp/ with a link, leave a folder it took its own rights away
    from, or put a file in place of its home: the next prepare puts that right (nothing is
    followed) instead of failing, which ran the next turn unwalled."""
    p = the_plan(place)
    target = place["ws"] / "W-000222"
    p.tmp.rmdir()
    p.tmp.symlink_to(target)
    p.job.rmdir()
    p.job.symlink_to("/nonexistent")
    sandbox.prepare(p)
    assert sandbox._is_real_dir(p.tmp) and not os.listdir(p.tmp)
    assert sandbox._is_real_dir(p.job) and (target / "notes.txt").exists()
    # a read-only folder (an extracted archive) inside tmp, and a file in place of the home
    (p.tmp / "ro" / "deep").mkdir(parents=True)
    (p.tmp / "ro" / "deep" / "f").write_text("x")
    os.chmod(p.tmp / "ro" / "deep", 0o500)
    os.chmod(p.tmp / "ro", 0o000)
    (p.home / ".claude").mkdir(exist_ok=True)
    (p.home / ".claude" / "kept").write_text("a session")
    sandbox.prepare(p)
    assert not os.listdir(p.tmp) and (p.home / ".claude" / "kept").exists()  # the home stays
    sandbox.remove(p.home)
    p.home.write_text("not a folder")
    sandbox.prepare(p)
    assert sandbox._is_real_dir(p.home) and (p.home / ".npmrc").is_file()
    # the end of a turn removes a link or an unwritable folder the same way
    sandbox.remove_quietly(p.tmp)
    assert not os.path.lexists(p.tmp)


def test_the_runner_never_writes_through_a_link_in_the_turns_home(tmp_path: Path) -> None:
    real, mine = tmp_path / "real", tmp_path / "mine"
    secret = tmp_path / "runner-config.json"
    secret.write_text("token")
    (real / ".config" / "hq-runner").mkdir(parents=True)
    (real / ".npmrc").write_text("registry")
    (real / ".gitconfig").write_text("[user]")
    closed = [real / ".config" / "hq-runner"]
    sandbox.make_home(real, mine, closed)
    # the turn makes a dotfile a folder holding a link to the runner's token, and puts a file
    # in place of the folder that holds a closed path
    (mine / ".npmrc").unlink()
    (mine / ".npmrc").mkdir()
    (mine / ".npmrc" / ".npmrc").symlink_to(secret)
    os.utime(mine / ".npmrc", (0, 0))
    sandbox.remove(mine / ".config")
    (mine / ".config").write_text("x")
    (mine / ".gitconfig").unlink()
    (mine / ".gitconfig").symlink_to(secret)
    sandbox.make_home(real, mine, closed)
    assert secret.read_text() == "token"
    assert sandbox._is_real_dir(mine / ".config")
    assert not (mine / ".gitconfig").is_symlink() and (mine / ".gitconfig").read_text() == "[user]"
    # a session carried into a home whose folders the turn replaced with links
    cwd = "/w/W-1"
    store = real / ".claude" / "projects" / sandbox.project_dir(cwd)
    (store / "s-1").mkdir(parents=True)
    (store / "s-1.jsonl").write_text("turn 1")
    (store / "s-1" / "side.json").write_text("{}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (mine / ".claude").mkdir()
    (mine / ".claude" / "projects").symlink_to(elsewhere)
    assert sandbox.carry_session(real, mine, cwd, "s-1") is True
    assert not os.listdir(elsewhere)
    there = mine / ".claude" / "projects" / sandbox.project_dir(cwd)
    assert (there / "s-1.jsonl").read_text() == "turn 1" and (there / "s-1" / "side.json").exists()
    # a link at the session's own file or inside its folder is replaced, not written through
    (there / "s-1.jsonl").unlink()
    (there / "s-1.jsonl").symlink_to(secret)
    (there / "s-1" / "side.json").unlink()
    (there / "s-1" / "side.json").symlink_to(secret)
    assert sandbox.carry_session(real, mine, cwd, "s-1") is True
    assert secret.read_text() == "token" and (there / "s-1.jsonl").read_text() == "turn 1"
    assert not (there / "s-1" / "side.json").is_symlink()


@needs_landlock
def test_the_probe_never_runs_in_a_works_folder(place: dict[str, Path], cfg: Config) -> None:
    """What a work's folder holds is its turns' doing: the probe has a place of its own, so one
    turn cannot fail it and bring the wall down for every company."""
    save(cfg, place["cfg"])
    p = the_plan(place)
    (p.work / ".hq-probe").mkdir()  # the old probe's file name, made a folder
    os.chmod(p.tmp, 0o500)
    assert run(sandbox.probe(p, dict(os.environ), str(FAKE_CLAUDE))) is None
    assert not [n for n in os.listdir(place["ws"] / ".hq") if n.startswith(".probe-")]


def test_the_wall_is_auto_and_never_in_the_way(
    fake_hub: FakeHub, cfg: Config, place: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, place["cfg"])
    # switched off on the server
    monkeypatch.setenv("HQ_RUNNER_SANDBOX", "off")
    result = go(fake_hub, cfg, place, turn("w3", "hello"))
    assert result["exit_code"] == 0 and result["data"]["sandbox"]["state"] == "off"
    assert "switched off" in result["data"]["sandbox"]["why"]
    monkeypatch.delenv("HQ_RUNNER_SANDBOX")
    # no account from the hub: the turn runs on this server's own login, which the wall hides
    job = turn("w4", "hello")
    del job["claude_oauth"]
    result = go(fake_hub, cfg, place, job)
    assert result["exit_code"] == 0 and "no Claude account" in result["data"]["sandbox"]["why"]
    # a kernel without Landlock
    monkeypatch.setattr(sandbox, "abi", lambda: 0)
    result = go(fake_hub, cfg, place, turn("w5", "hello"))
    assert result["exit_code"] == 0 and "no Landlock" in result["data"]["sandbox"]["why"]
    # a turn the hub did not ask to wall (a company's own server) says nothing of it
    job = turn("w6", "hello")
    del job["args"]["sandbox"]
    assert "sandbox" not in go(fake_hub, cfg, place, job)["data"]


def test_the_wrapper_refuses_to_run_a_command_it_could_not_wall(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sandbox, "abi", lambda: 0)
    assert sandbox.exec_main([], [], ["/bin/true"]) == sandbox.EXIT_NO_WALL
    assert "no Landlock" in capsys.readouterr().err
