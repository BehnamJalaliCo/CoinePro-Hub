"""⟨0.3.2⟩ contract §43, the holding's workshop: a workspace turn that ended well sends the files
it left in `out/` to the hub, once per content, and its result names them."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE, FakeHub, make_route, run
from test_run import drive

from hq_runner import outbox as O
from hq_runner import workspace as W
from hq_runner.config import Config, save
from hq_runner.runner import Runner

REF = "W-000501"


@pytest.fixture
def spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "hq-workspace"
    monkeypatch.setenv("HQ_RUNNER_WORKSPACES", str(root))
    return root


def turn(jid: str, brief: str = "make the reel") -> dict[str, object]:
    return {"id": jid, "kind": "claude", "args": {"brief": brief, "workspace": REF, "hands": True}}


def out_dir(spaces: Path) -> Path:
    d = spaces / REF / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runner_for(fake_hub: FakeHub, cfg: Config, cfg_path: Path) -> Runner:
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    return Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)


def test_a_turn_sends_its_out_files_and_the_result_names_them(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path, tmp_path: Path
) -> None:
    out = out_dir(spaces)
    (out / "reel.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 64)
    (out / "covers").mkdir()
    (out / "covers" / "کاور.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"p" * 64)
    (out / "notes.md").write_text("# ATR", encoding="utf-8")
    (out / "build.sh").write_text("echo", encoding="utf-8")  # not a deliverable type
    (out / ".cache").mkdir()
    (out / ".cache" / "frame.png").write_bytes(b"x")  # hidden: never sent, never listed
    outside = tmp_path / "secret.txt"
    outside.write_text("no", encoding="utf-8")
    os.symlink(outside, out / "link.txt")  # a link: never followed
    fake_hub.jobs.append(turn("h1"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h1" in fake_hub.results, within=60))
    res = fake_hub.results["h1"]
    assert res["exit_code"] == 0
    sent = fake_hub.uploads["h1"]
    assert [u["name"] for u in sent] == ["covers/کاور.png", "notes.md", "reel.mp4"]
    assert [u["type"] for u in sent] == ["image/png", "text/markdown", "video/mp4"]
    assert sent[2]["data"].startswith(b"\x00\x00\x00\x18ftypmp42")
    data = res["data"]
    assert data["files"] == [u["id"] for u in sent]
    assert data["files_skipped"] == [{"name": "build.sh", "why": O.TYPE_FA}]
    assert "3 فایل از out/ به ستاد رفت" in res["summary_fa"]
    assert set(W.sent_of(REF, cfg_path)) == {"covers/کاور.png", "notes.md", "reel.mp4"}

    # the next turn of the same work sends only what is new or changed
    (out / "notes.md").write_text("# ATR v2", encoding="utf-8")
    fake_hub.jobs.append(turn("h2", "darker colours"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h2" in fake_hub.results, within=60))
    assert [u["name"] for u in fake_hub.uploads["h2"]] == ["notes.md"]
    assert fake_hub.results["h2"]["data"]["files"] == [fake_hub.uploads["h2"][0]["id"]]


def test_a_failed_turn_sends_nothing(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path
) -> None:
    (out_dir(spaces) / "half.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    fake_hub.jobs.append(turn("h3", "[[fake:error]]"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h3" in fake_hub.results, within=60))
    assert fake_hub.results["h3"]["exit_code"] != 0
    assert "h3" not in fake_hub.uploads
    assert "files" not in (fake_hub.result_output("h3") or {})


def test_a_refused_file_is_listed_and_the_rest_still_go(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path
) -> None:
    out = out_dir(spaces)
    (out / "a.pdf").write_bytes(b"%PDF-1.7\n")
    (out / "b.txt").write_text("ok", encoding="utf-8")
    fake_hub.refuse_names = {"a.pdf"}
    fake_hub.jobs.append(turn("h4"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h4" in fake_hub.results, within=60))
    data = fake_hub.result_output("h4")
    assert [u["name"] for u in fake_hub.uploads["h4"]] == ["b.txt"]
    assert data["files_skipped"] == [{"name": "a.pdf", "why": O.REFUSED_FA}]
    # a refused file is not recorded as sent: the next turn tries it again
    assert set(W.sent_of(REF, cfg_path)) == {"b.txt"}


def test_a_plain_claude_job_never_sends_files(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    (repo / "out" / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    fake_hub.jobs.append({"id": "h5", "kind": "claude", "args": {"brief": "hi", "cwd": str(repo)}})
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h5" in fake_hub.results, within=60))
    assert fake_hub.uploads == {} and "files" not in fake_hub.result_output("h5")


def test_limits_on_size_and_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setitem(O.TYPES, ".png", ("image/png", 10))
    (out / "big.png").write_bytes(b"x" * 11)
    for i in range(O.MAX_FILES + 2):
        (out / f"n{i:02d}.txt").write_text(str(i), encoding="utf-8")
    send, skipped = O.candidates(tmp_path, {})
    assert len(send) == O.MAX_FILES
    assert {"name": "big.png", "why": O.SIZE_FA} in skipped
    assert sum(1 for s in skipped if s["why"] == O.MANY_FA) == 2
    # nothing in out/, or out/ a link: nothing at all
    assert O.candidates(tmp_path / "none", {}) == ([], [])
