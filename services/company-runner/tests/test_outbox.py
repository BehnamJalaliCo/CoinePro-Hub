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


def test_a_turn_stopped_at_its_time_limit_still_sends_what_it_made(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path
) -> None:
    """⟨0.3.3⟩ The hour passed: what the turn had left in `out/` goes to the hub with the failed
    result, so the owner gets it as an unfinished output."""
    (out_dir(spaces) / "draft.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 32)
    job = turn("h6", "[[fake:sleep]]")
    job["args"]["timeout_s"] = 1  # type: ignore[index]
    fake_hub.jobs.append(job)
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h6" in fake_hub.results, within=60))
    res = fake_hub.results["h6"]
    assert res["exit_code"] != 0 and "سقف زمان" in res["summary_fa"]
    assert [u["name"] for u in fake_hub.uploads["h6"]] == ["draft.mp4"]
    assert res["data"]["files"] == [fake_hub.uploads["h6"][0]["id"]]


def test_a_file_is_recorded_as_sent_only_when_the_result_arrived(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path
) -> None:
    """⟨0.3.3⟩ The hub closed the job before the result reached it (its sweep): the file is not
    recorded, and the next turn sends it again (before, it was never sent again and reached no
    output)."""
    (out_dir(spaces) / "a.txt").write_text("one", encoding="utf-8")
    fake_hub.jobs.append(turn("h7"))
    fake_hub.on_upload = lambda jid: fake_hub.gone_jobs.add(jid)  # gone once its file is in
    first = runner_for(fake_hub, cfg, cfg_path)
    run(drive(first, lambda: "h7" in fake_hub.uploads and not first.running, within=60))
    assert "h7" not in fake_hub.results
    assert W.sent_of(REF, cfg_path) == {}
    fake_hub.on_upload = None
    fake_hub.jobs.append(turn("h8"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h8" in fake_hub.results, within=60))
    assert [u["name"] for u in fake_hub.uploads["h8"]] == ["a.txt"]
    assert set(W.sent_of(REF, cfg_path)) == {"a.txt"}


def test_a_turn_finds_its_input_files_in_the_in_folder(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path
) -> None:
    """⟨0.3.3⟩ contract §43.8: the narration the hub made (or a logo, the owner's upload) is in
    `in/` of the work's folder before the session starts; a name is never a path; an input the
    hub does not serve stops the turn before it starts."""
    fid = "00000000-0000-4000-8000-0000000000aa"
    fake_hub.inputs[f"h9/{fid}"] = b"RIFF....WAVEfmt "
    fake_hub.inputs["h9/x"] = b"font-bytes"
    job = turn("h9")
    job["args"]["inputs"] = [  # type: ignore[index]
        {"file_id": fid, "name": "گوینده.wav", "mime": "audio/wav", "size": 16,
         "url": f"/api/v1/runners/jobs/h9/inputs/{fid}"},
        {"file_id": "x", "name": "../../.ssh/authorized_keys", "mime": "font/ttf", "size": 10,
         "url": "/api/v1/runners/jobs/h9/inputs/x"},
    ]  # fmt: skip
    fake_hub.jobs.append(job)
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h9" in fake_hub.results, within=60))
    assert fake_hub.results["h9"]["exit_code"] == 0, fake_hub.results["h9"]
    box = spaces / REF / "in"
    assert (box / "گوینده.wav").read_bytes() == b"RIFF....WAVEfmt "
    assert sorted(p.name for p in box.iterdir()) == ["authorized_keys", "گوینده.wav"]
    assert not (spaces.parent / ".ssh").exists()
    assert O.safe_name("..", 3) == "input-3" and O.safe_name("a/b\\c:d.png", 1) == "bcd.png"

    missing = turn("h10")
    missing["args"]["inputs"] = [  # type: ignore[index]
        {"file_id": "nope", "name": "v.mp4", "url": "/api/v1/runners/jobs/h10/inputs/nope"}
    ]
    fake_hub.jobs.append(missing)
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h10" in fake_hub.results, within=60))
    assert fake_hub.results["h10"]["exit_code"] != 0
    assert "ورودی" in fake_hub.results["h10"]["summary_fa"]


def test_a_link_planted_in_the_in_folder_never_redirects_an_input(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path, tmp_path: Path
) -> None:
    """A turn may leave links in `in/` (at the next input's `.part` name, or at its name): the
    hub's bytes still land in `in/` only, never in the file a link points to (another work's
    CLAUDE.md, the runner's own config)."""
    victim = spaces / "W-000777" / "CLAUDE.md"
    victim.parent.mkdir(parents=True)
    victim.write_text("company B's instructions", encoding="utf-8")
    other = tmp_path / "config.json"
    other.write_text("token", encoding="utf-8")
    box = spaces / REF / "in"
    box.mkdir(parents=True)
    os.symlink(victim, box / ".brief.md.part")
    os.symlink(other, box / "brief.md")
    os.symlink(other, box / ".logo.png.part")
    fake_hub.inputs["h11/a"] = b"# planted"
    fake_hub.inputs["h11/b"] = b"\x89PNG"
    job = turn("h11")
    job["args"]["inputs"] = [  # type: ignore[index]
        {"file_id": "a", "name": "brief.md", "url": "/api/v1/runners/jobs/h11/inputs/a"},
        {"file_id": "b", "name": "logo.png", "url": "/api/v1/runners/jobs/h11/inputs/b"},
    ]
    fake_hub.jobs.append(job)
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h11" in fake_hub.results, within=60))
    assert fake_hub.results["h11"]["exit_code"] == 0, fake_hub.results["h11"]
    assert victim.read_text(encoding="utf-8") == "company B's instructions"
    assert other.read_text(encoding="utf-8") == "token"
    for name, data in (("brief.md", b"# planted"), ("logo.png", b"\x89PNG")):
        assert not (box / name).is_symlink() and (box / name).read_bytes() == data
    assert sorted(p.name for p in box.iterdir()) == ["brief.md", "logo.png"]

    # in/ itself a link: the turn does not start, and nothing is written where it points
    sink = tmp_path / "elsewhere"
    sink.mkdir()
    for p in box.iterdir():
        p.unlink()
    box.rmdir()
    os.symlink(sink, box)
    fake_hub.inputs["h12/a"] = b"x"
    job = turn("h12")
    job["args"]["inputs"] = [  # type: ignore[index]
        {"file_id": "a", "name": "brief.md", "url": "/api/v1/runners/jobs/h12/inputs/a"}
    ]
    fake_hub.jobs.append(job)
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h12" in fake_hub.results, within=60))
    assert fake_hub.results["h12"]["exit_code"] != 0
    assert list(sink.iterdir()) == []


def test_a_file_swapped_for_a_link_after_the_list_is_never_sent(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, spaces: Path, tmp_path: Path
) -> None:
    """contract §43.9: a process the turn left running swaps a listed name (or the folder that
    holds it) for a link to the runner's token while an earlier file is being sent; the runner
    sends what it listed, or nothing, never what the link points to."""
    token = tmp_path / "runner" / "z.txt"
    token.parent.mkdir()
    token.write_text("hqr1_secret", encoding="utf-8")
    out = out_dir(spaces)
    (out / "a.txt").write_text("first", encoding="utf-8")
    (out / "sub").mkdir()
    (out / "sub" / "z.txt").write_text("mine", encoding="utf-8")
    (out / "z.txt").write_text("mine too", encoding="utf-8")

    def swap(jid: str) -> None:
        if len(fake_hub.uploads[jid]) == 1:  # a.txt is in: swap the two not yet sent
            (out / "z.txt").unlink()
            os.symlink(token, out / "z.txt")
            (out / "sub" / "z.txt").unlink()
            (out / "sub").rmdir()
            os.symlink(token.parent, out / "sub")

    fake_hub.on_upload = swap
    fake_hub.jobs.append(turn("h13"))
    run(drive(runner_for(fake_hub, cfg, cfg_path), lambda: "h13" in fake_hub.results, within=60))
    res = fake_hub.results["h13"]
    assert res["exit_code"] == 0, res
    assert [u["name"] for u in fake_hub.uploads["h13"]] == ["a.txt"]
    assert all(b"hqr1_secret" not in u["data"] for u in fake_hub.uploads["h13"])
    assert {s["name"] for s in res["data"]["files_skipped"]} == {"sub/z.txt", "z.txt"}
