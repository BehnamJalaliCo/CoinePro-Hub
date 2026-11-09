"""⟨2026-11-09⟩ The owner's second Claude subscription (kv/claude-runtime/oauth-2): the companies
have no subscription of their own, so a Claude Code job a company server's runner picks up runs on
it. Its token goes with the job at pickup only, never in the stored args."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from hq_api.domain import servers as SV


def _job(kind: str) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "kind": kind,
        "args": {"brief": "x"} if kind == "claude" else {"cmd": "uptime"},
        "timeout_s": 600,
        "created_at": datetime.now(UTC),
        "session_ref": None,
        "actor_kind": "owner",
        "actor_code": "OWNER",
        "server_id": uuid4(),
        "company": "PC",
    }


def test_a_claude_job_runs_on_the_hubs_second_account() -> None:
    token = "sk-ant-oat01-" + "x" * 95
    hub = SimpleNamespace(secrets=SimpleNamespace(runner_claude_token=token))
    job = _job("claude")
    out = SV.runner_job(job, hub)
    assert out["claude_oauth"] == token
    assert "claude_oauth" not in job["args"] and "claude_oauth" not in out["args"]
    assert "claude_oauth" not in SV.runner_job(_job("exec"), hub)
    plain = SimpleNamespace(secrets=SimpleNamespace(runner_claude_token=""))
    assert "claude_oauth" not in SV.runner_job(_job("claude"), plain)
