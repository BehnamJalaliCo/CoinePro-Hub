from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from conftest import FAKE_CLAUDE, FakeHub, make_route, run
from test_run import drive

from hq_runner.claude_job import hook_settings, session_events, usage_from_result
from hq_runner.config import Config, save
from hq_runner.mask import Masker
from hq_runner.runner import Runner


class ClassifyServer:
    """The hub's /runners/classify for the hook process (a separate process
    cannot reach the in-memory MockTransport)."""

    def __init__(self, token: str) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, str]]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.calls.append((body, dict(self.headers)))
                if (
                    self.path != "/api/v1/runners/classify"
                    or self.headers.get("Authorization") != f"Bearer {token}"
                ):
                    self.send_response(401)
                    self.end_headers()
                    return
                answer = {"category": "db_drop" if "DROP DATABASE" in body["cmd"] else None}
                data = json.dumps(answer).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def classify(cfg: Config) -> Iterator[ClassifyServer]:
    srv = ClassifyServer(cfg.runner_token)
    yield srv
    srv.server.shutdown()


def test_claude_job_streams_session_events_and_hook_blocks_drop_database(
    fake_hub: FakeHub,
    cfg: Config,
    cfg_path: Path,
    classify: ClassifyServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg.hub = classify.url  # where the hook process reaches the hub
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    brief = "Clean up. [[bash:psql -c 'DROP DATABASE prod']] [[bash:ls -la]]"
    fake_hub.jobs.append(
        {
            "id": "cl1",
            "kind": "claude",
            "args": {"brief": brief, "cwd": str(repo), "session_id": "sess-42"},
        }
    )
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)
    run(drive(runner, lambda: "cl1" in fake_hub.results, within=60))

    # The CLI ran as the contract says, in the repository, with the temporary hook settings.
    rec = json.loads(record.read_text())
    argv = rec["argv"]
    assert argv[:2] == ["-p", brief]
    assert argv[argv.index("--output-format") + 1] == "stream-json" and "--verbose" in argv
    assert argv[argv.index("--resume") + 1] == "sess-42"
    assert rec["cwd"] == str(repo)
    hook = rec["settings"]["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Bash" and "classify-hook --job cl1" in hook["hooks"][0]["command"]
    assert not Path(argv[argv.index("--settings") + 1]).exists()  # removed after the run

    # Both Bash commands were classified by the hub, with the runner token.
    cmds = [c[0]["cmd"] for c in classify.calls]
    assert cmds == ["psql -c 'DROP DATABASE prod'", "ls -la"]
    assert all(c[0].keys() == {"cmd"} for c in classify.calls)
    assert classify.calls[0][1]["X-HQ-Runner-Job"] == "cl1"

    events = [e["data"] for e in fake_hub.events["cl1"] if e["type"] == "session_event"]
    types = [e["type"] for e in events]
    assert types[0] == "state" and types[-1] == "state"
    assert [e["data"]["cmd"] for e in events if e["type"] == "command"] == cmds
    results = [e["data"] for e in events if e["type"] == "progress" and "is_error" in e["data"]]
    assert (
        results[0]["is_error"] is True
        and "Blocked by HQ" in results[0]["text"]
        and "db_drop" in results[0]["text"]
    )
    assert results[1]["is_error"] is False
    approval = [e for e in events if e["type"] == "approval_request"]
    assert approval and approval[0]["data"]["category"] == "db_drop"
    message = next(e for e in events if e["type"] == "message")
    assert "DB_PASSWORD=[redacted]" in message["data"]["text"]
    assert all("hunter2" not in json.dumps(e) for e in fake_hub.events["cl1"])

    result = fake_hub.results["cl1"]
    assert result["exit_code"] == 0
    assert result["usage"]["input_tokens"] == 120 and result["usage"]["output_tokens"] == 30
    assert (
        result["usage"]["cache_read_tokens"] == 50 and result["usage"]["cache_write_tokens"] == 70
    )
    assert result["usage"]["thinking_tokens"] == 4 and result["usage"]["cost_usd"] == 0.0123
    assert fake_hub.result_output("cl1")["session_id"] == "sess-42"
    assert fake_hub.result_output("cl1")["result_fa"] == "Done."


def test_claude_job_cancel(fake_hub: FakeHub, cfg: Config, cfg_path: Path, tmp_path: Path) -> None:
    cfg.claude_bin = str(FAKE_CLAUDE)
    save(cfg, cfg_path)
    fake_hub.jobs.append(
        {"id": "cl2", "kind": "claude", "args": {"brief": "[[fake:sleep]]", "cwd": str(tmp_path)}}
    )
    runner = Runner(cfg, make_route(fake_hub), cfg_path=cfg_path, persist_state=False)

    async def scenario() -> None:
        task = asyncio.create_task(drive(runner, lambda: "cl2" in fake_hub.results, within=30))
        while not any(e["type"] == "session_event" for e in fake_hub.events.get("cl2", [])):
            await asyncio.sleep(0.05)
        fake_hub.cancels.append("cl2")
        start = time.monotonic()
        await task
        assert time.monotonic() - start < 10

    run(scenario())
    assert fake_hub.results["cl2"]["exit_code"] == 130


def test_claude_missing_cwd_fails(fake_hub: FakeHub, cfg: Config) -> None:
    cfg.claude_bin = str(FAKE_CLAUDE)
    fake_hub.jobs.append(
        {"id": "cl3", "kind": "claude", "args": {"brief": "x", "cwd": "/nonexistent/repo"}}
    )
    runner = Runner(cfg, make_route(fake_hub), persist_state=False)
    run(drive(runner, lambda: "cl3" in fake_hub.results))
    assert fake_hub.results["cl3"]["exit_code"] == 2


def test_session_event_conversion() -> None:
    m = Masker()
    edit = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/r/a.py"}},
                {"type": "tool_use", "id": "t2", "name": "Grep", "input": {"pattern": "x"}},
                {"type": "thinking", "thinking": "..."},
            ]
        },
    }
    evs = session_events(edit, m)
    assert [e["type"] for e in evs] == ["file_change", "progress"]
    assert evs[0]["data"]["path"] == "/r/a.py" and evs[0]["summary_fa"] and evs[0]["at"]
    assert session_events({"type": "stream_event"}, m) == []
    usage = usage_from_result({"type": "result", "usage": {"input_tokens": 1, "output_tokens": 2}})
    assert usage["input_tokens"] == 1 and usage["cache_read_tokens"] == 0
    assert hook_settings("j")["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
