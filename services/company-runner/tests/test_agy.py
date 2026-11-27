"""⟨0.4.0⟩ A workshop turn on Antigravity (agy, Gemini 4 Hydrogen): the executor chosen by the
model, agy's argv, its stream-json mapped to the hub's SessionEvents, the hub's tools over MCP,
resume across executors, usage under the agy model, and agy-build (the builder command)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import FAKE_CLAUDE, TESTING, FakeHub, make_route, run
from test_run import drive

from hq_runner import agy_build, agy_job
from hq_runner.config import Config, save
from hq_runner.hub import Hub
from hq_runner.mask import Masker
from hq_runner.runner import Runner

FAKE_AGY = TESTING / "fake_agy.py"
CID = "c5279625-8fda-4363-b907-2136c41372b7"


@pytest.fixture
def agy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This server's own agy login (in the runner user's home) and the fake CLI."""
    home = tmp_path / "home"
    login = home / ".gemini" / "antigravity-cli"
    login.mkdir(parents=True)
    (login / "antigravity-oauth-token").write_text("{}")
    (login / "conversations").mkdir()
    (login / "conversations" / "other-company.pb").write_text("secret talk")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HQ_RUNNER_AGY_BIN", str(FAKE_AGY))
    monkeypatch.setenv("HQ_RUNNER_WORKSPACES", str(tmp_path / "hq-workspace"))
    agy_job._INSTALLED[:] = [0.0, False]
    return home


def test_argv_has_no_print_flag_and_takes_the_brief_on_stdin() -> None:
    argv = agy_build.argv_for("/x/agy", model="gemini-4-hydrogen-xhigh", resume=CID, timeout_s=600)
    assert argv[:5] == ["/x/agy", "--input-format", "stream-json", "--output-format", "stream-json"]
    assert "-p" not in argv and "--print" not in argv
    assert argv[argv.index("--model") + 1] == "gemini-4-hydrogen-xhigh"
    assert argv[argv.index("--conversation") + 1] == CID
    assert argv[argv.index("--print-timeout") + 1] == "600s"
    assert argv[-1] == "--dangerously-skip-permissions"
    assert "--conversation" not in agy_build.argv_for("a", model=None, resume=None, timeout_s=None)
    line = json.loads(agy_build.user_line("- a Markdown list"))
    assert line == {"event": "user", "message": {"role": "user", "content": "- a Markdown list"}}


def test_executor_and_resume_rules() -> None:
    assert agy_job.is_agy("gemini-4-hydrogen-xhigh") and not agy_job.is_agy("claude-opus-5-5")
    assert not agy_job.is_agy(None)
    assert agy_job.conversation_of(f"agy:{CID}") == CID
    assert agy_job.conversation_of("0b0e…claude-session") is None
    assert agy_job.conversation_of("agy:../../x") is None
    assert agy_job.conversation_of(None) is None


REAL = [
    {"event": "init", "conversation_id": CID,
     "init": {"model": "gemini-4-hydrogen-low", "cwd": "/w", "tools": []}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 2, "state": "ACTIVE",
     "step_type": "tool", "tool_name": "write_file",
     "tool_info": {"name": "write_file", "parameters": {"Path": "/w/out/hello.txt"}}}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 4, "state": "ACTIVE",
     "step_type": "tool", "tool_name": "run_command",
     "tool_info": {"name": "run_command", "parameters": {"CommandLine": "cat hello.txt"}}}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 4, "state": "DONE",
     "step_type": "tool", "tool_name": "run_command", "tool_info": {"name": "run_command",
     "parameters": {"CommandLine": "cat hello.txt"}, "output": "hydrogen DB_PASSWORD=hunter2"}}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 5, "state": "ACTIVE",
     "step_type": "subagent", "tool_name": "invoke_subagent"}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 6, "state": "ACTIVE",
     "step_type": "agent_response", "text_delta": "DO"}},
    {"event": "step_update", "step_update": {"conversation_id": CID, "step_index": 6, "state": "DONE",
     "step_type": "agent_response", "text_delta": "NE\n", "usage": {"input_tokens": 2311,
     "output_tokens": 16, "thinking_tokens": 11, "cache_read_tokens": 8300}}},
    {"event": "result", "result": {"conversation_id": CID, "status": "SUCCESS", "response": "DONE\n",
     "duration_seconds": 4.9, "num_turns": 1, "usage": {"input_tokens": 22832, "output_tokens": 178,
     "thinking_tokens": 82, "cache_read_tokens": 8300, "total_tokens": 23010}}},
]  # fmt: skip


def test_the_stream_becomes_the_hubs_session_events() -> None:
    masker = Masker(literals=["hunter2"])
    text: dict[int, str] = {}
    events = [e for obj in REAL for e in agy_job.session_events(obj, masker, text)]
    types = [e["type"] for e in events]
    assert types == ["state", "file_change", "command", "progress", "progress", "message", "state"]
    assert (
        events[0]["data"]["session_id"] == f"agy:{CID}" and events[0]["data"]["executor"] == "agy"
    )
    assert (
        events[1]["data"]["path"] == "/w/out/hello.txt"
        and events[1]["data"]["tool"] == "write_file"
    )
    assert events[2]["data"] == {"cmd": "cat hello.txt", "tool_use_id": "agy-4"}
    assert events[3]["data"]["tool_use_id"] == "agy-4" and "hunter2" not in json.dumps(events)
    assert events[4]["data"]["tool"] == "invoke_subagent"
    assert events[5]["data"]["text"] == "DONE\n"
    assert events[6]["data"]["state"] == "done" and events[6]["data"]["duration_ms"] == 4900
    meter = agy_job.AgyMeter()
    stream = agy_build.Stream()
    for obj in REAL:
        meter.add(obj)
        stream.add(obj)
    assert meter.total == 2311 + 16 + 11
    u = agy_job.usage_of(stream.result, meter, "gemini-4-hydrogen-low", f"agy:{CID}")
    assert u == {"input_tokens": 22832, "output_tokens": 178, "cache_read_tokens": 8300,
                 "cache_write_tokens": 0, "thinking_tokens": 82, "cost_usd": 0.0,
                 "model": "gemini-4-hydrogen-low", "session_id": f"agy:{CID}", "executor": "agy"}  # fmt: skip
    assert stream.files == ["/w/out/hello.txt"] and stream.response == "DONE\n"
    assert stream.total_tokens == 23010


def test_a_gemini_turn_runs_on_agy_with_the_hubs_tools(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, tmp_path: Path, agy_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    record = tmp_path / "agy.json"
    monkeypatch.setenv("FAKE_AGY_RECORD", str(record))
    monkeypatch.setenv("HQ_RUNNER_SANDBOX", "off")
    cfg.claude_bin = str(FAKE_CLAUDE)  # never started for a Gemini turn
    save(cfg, cfg_path)
    fake_hub.tools = [
        {"name": "order_ask", "description": "ask", "input_schema": {"type": "object"}}
    ]
    fake_hub.tool_answer = lambda body: {"outcome": "ok", "class": "A1", "code": None, "ref": None,
                                         "result": {"asked": True}}  # fmt: skip
    brief = '- build it [[cmd:echo hi]] [[write:out/a.txt]] [[tool:order_ask:{"q": 1}]]'
    fake_hub.jobs.append(
        {"id": "ag1", "kind": "claude",
         "args": {"brief": brief, "workspace": "W-000901", "model": "gemini-4-hydrogen-xhigh",
                  "effort": "max", "tools": "hub", "sandbox": "auto", "session_id": f"agy:{CID}",
                  "allowed_tools": ["Bash"]}}
    )  # fmt: skip
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "ag1" in fake_hub.results, within=60))
    got = fake_hub.results["ag1"]
    assert got["exit_code"] == 0, got
    rec = json.loads(record.read_text())
    argv = rec["argv"]
    assert argv[argv.index("--model") + 1] == "gemini-4-hydrogen-xhigh"
    assert argv[argv.index("--conversation") + 1] == CID
    assert rec["brief"] == brief and brief not in argv
    work = tmp_path / "hq-workspace" / "W-000901"
    assert rec["cwd"] == str(work) and (work / "out" / "a.txt").is_file()
    # its own home with this server's login, never the shared ~/.gemini (other turns' talks)
    assert rec["home"] == str(tmp_path / "hq-workspace" / ".hq" / "W-000901" / "home")
    assert rec["login"] is True
    assert not (Path(rec["home"]) / ".gemini" / "antigravity-cli" / "conversations").exists()
    assert list(rec["mcp"]["mcpServers"]) == ["hq"] and "type" not in rec["mcp"]["mcpServers"]["hq"]
    out = got["data"]
    assert out["executor"] == "agy" and out["session_id"] == f"agy:{CID}"
    assert out["tool_calls"] == 1 and "call order_ask -> error=False" in out["result_fa"]
    assert any(p.endswith("out/a.txt") for p in out["files_changed"])
    assert got["usage"]["model"] == "gemini-4-hydrogen-xhigh" and got["usage"]["executor"] == "agy"
    assert got["usage"]["input_tokens"] == 100 and got["usage"]["cost_usd"] == 0.0
    events = [e["data"] for e in fake_hub.events["ag1"] if e["type"] == "session_event"]
    assert [e["data"]["cmd"] for e in events if e["type"] == "command"] == ["echo hi"]
    assert "Hydrogen" in got["summary_fa"]
    # the turn's MCP config (its key) is not left behind
    assert not (Path(rec["home"]) / ".gemini/config/mcp_config.json").exists()


def test_resume_across_executors_starts_afresh_in_the_same_folder(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, tmp_path: Path, agy_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    rec_agy, rec_claude = tmp_path / "agy.json", tmp_path / "claude.json"
    monkeypatch.setenv("FAKE_AGY_RECORD", str(rec_agy))
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(rec_claude))
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    # a Claude session's id on an agy turn: no --conversation, the brief says why
    fake_hub.jobs.append({"id": "x1", "kind": "claude", "args": {
        "brief": "go on", "cwd": str(repo), "model": "gemini-4-hydrogen-high", "resume": "sess-claude"}})  # fmt: skip
    # an agy conversation on a Claude turn (back on Claude after a fallback): no --resume
    fake_hub.jobs.append({"id": "x2", "kind": "claude", "args": {
        "brief": "go on", "cwd": str(repo), "model": "claude-opus-5-5", "resume": f"agy:{CID}"}})  # fmt: skip
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: {"x1", "x2"} <= set(fake_hub.results), within=60))
    a = json.loads(rec_agy.read_text())
    assert "--conversation" not in a["argv"] and a["brief"].startswith(agy_job.CONTINUED_FA)
    c = json.loads(rec_claude.read_text())
    assert "--resume" not in c["argv"]
    assert fake_hub.results["x1"]["exit_code"] == 0 and fake_hub.results["x2"]["exit_code"] == 0


def test_an_agy_error_fails_the_turn_with_its_reason(
    fake_hub: FakeHub, cfg: Config, cfg_path: Path, tmp_path: Path, agy_home: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    save(cfg, cfg_path)
    fake_hub.jobs.append({"id": "e1", "kind": "claude", "args": {
        "brief": "[[fake:error]]", "cwd": str(repo), "model": "gemini-4-hydrogen-xhigh"}})  # fmt: skip
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "e1" in fake_hub.results, within=60))
    got = fake_hub.results["e1"]
    assert got["exit_code"] == 1 and "model request failed" in got["summary_fa"]
    assert got["data"]["error_detail"] == "model request failed"


def test_the_runner_tells_the_hub_it_can_run_agy(
    agy_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = Hub(make_route(FakeHub()), lambda: None)
    assert hub.headers(False)["X-HQ-Runner-Agy"] == "1"
    monkeypatch.setenv("HQ_RUNNER_AGY", "off")
    agy_job._INSTALLED[:] = [0.0, False]
    assert "X-HQ-Runner-Agy" not in hub.headers(False)
    monkeypatch.delenv("HQ_RUNNER_AGY")
    (agy_home / ".gemini/antigravity-cli/antigravity-oauth-token").unlink()
    agy_job._INSTALLED[:] = [0.0, False]
    assert "X-HQ-Runner-Agy" not in hub.headers(False)


def test_agy_build_runs_a_build_and_reports_its_conversation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = tmp_path / "w"
    work.mkdir()
    brief = work / "brief.md"
    brief.write_text("[[cmd:echo built]] [[write:coin.txt]]")
    code = agy_build.main([str(work), str(brief), "--agy", str(FAKE_AGY), "--timeout", "60"])
    out = capsys.readouterr().out
    assert code == 0 and "AGY_STATUS=SUCCESS" in out and "tool run_command: echo built" in out
    cid = next(ln.split("=", 1)[1] for ln in out.splitlines() if "AGY_CONVERSATION_ID=" in ln)
    assert cid and (work / "coin.txt").is_file()
    state = json.loads((work / ".agy" / "state.json").read_text())
    assert state["status"] == "SUCCESS" and state["conversation_id"] == cid
    assert agy_build.main(["--status", str(work)]) == 0
    # a review round on the same conversation
    notes = work / "notes.md"
    notes.write_text("fix the colour")
    assert agy_build.main([str(work), str(notes), "--resume", cid, "--agy", str(FAKE_AGY)]) == 0
    assert f"AGY_CONVERSATION_ID={cid}" in capsys.readouterr().out
    # an error ends non-zero
    brief.write_text("[[fake:error]]")
    assert agy_build.main([str(work), str(brief), "--agy", str(FAKE_AGY)]) == 1


def test_agy_build_detached_is_followed_with_wait(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = tmp_path / "w"
    work.mkdir()
    brief = work / "brief.md"
    brief.write_text("[[cmd:echo detached]]")
    assert agy_build.main([str(work), str(brief), "--agy", str(FAKE_AGY), "--detach"]) == 0
    assert agy_build.main(["--wait", str(work), "--max", "60"]) == 0
    out = capsys.readouterr().out
    assert "echo detached" in out and "AGY_STATUS=SUCCESS" in out
    assert sys.executable  # the child ran this same file with this Python
