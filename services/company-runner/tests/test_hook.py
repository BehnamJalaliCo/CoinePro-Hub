from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
import pytest

from hq_runner import hook
from hq_runner.config import Config, save


def hub(
    category: str | None = None, status: int = 200
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"code": "boom"})
        cmd = json.loads(request.content)["cmd"]
        return httpx.Response(
            200, json={"category": category if "DROP" in cmd or "rm -rf" in cmd else None}
        )

    return httpx.MockTransport(handle), seen


def call(payload: object, transport: httpx.MockTransport) -> tuple[int, str]:
    err = io.StringIO()
    code = hook.main(
        "job-1", stdin=io.StringIO(json.dumps(payload)), stderr=err, transport=transport
    )
    return code, err.getvalue()


@pytest.fixture(autouse=True)
def paired(cfg: Config, cfg_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    save(cfg, cfg_path)
    log = tmp_path / "hook.jsonl"
    monkeypatch.setenv("HQ_RUNNER_HOOK_EVENTS", str(log))
    monkeypatch.setenv("HQ_RUNNER_VIA", "public")
    return log


def bash(cmd: str) -> dict[str, object]:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}}


def test_blocks_a_seal_required_command(paired: Path) -> None:
    transport, seen = hub("db_drop")
    code, err = call(bash("sudo -u postgres psql -c 'DROP DATABASE prod'"), transport)
    assert code == 2
    assert "db_drop" in err and "seal" in err
    assert json.loads(seen[0].content) == {"cmd": "sudo -u postgres psql -c 'DROP DATABASE prod'"}
    assert seen[0].headers["authorization"].startswith("Bearer ")
    assert seen[0].url.path == "/api/v1/runners/classify"
    assert json.loads(paired.read_text().splitlines()[0])["category"] == "db_drop"


def test_allows_an_ordinary_command() -> None:
    transport, _ = hub("db_drop")
    assert call(bash("git status"), transport) == (0, "")


def test_other_tools_are_not_classified() -> None:
    transport, seen = hub("db_drop")
    assert call({"tool_name": "Edit", "tool_input": {"file_path": "x"}}, transport)[0] == 0
    assert seen == []


def test_fails_closed_when_the_hub_cannot_answer() -> None:
    transport, _ = hub(status=503)
    code, err = call(bash("ls"), transport)
    assert code == 2 and "could not be classified" in err


def test_fails_closed_when_not_paired(cfg_path: Path) -> None:
    cfg_path.unlink()
    transport, _ = hub()
    assert call(bash("ls"), transport)[0] == 2
