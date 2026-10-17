"""claude-runtime against the real Agent SDK driving a fake CLI (no quota used)."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

import httpx
import pytest

from claude_runtime.config import Settings
from claude_runtime.main import GuardMiddleware, State, build_app
from claude_runtime.quota import Signals, classify
from claude_runtime.render import render
from claude_runtime.runner import ClaudeRunner, Delta, Message, Outcome, RunSpec, usage_from
from hq_common import tokens

FAKE = Path(__file__).resolve().parents[1] / "testing" / "fake_claude.py"
CALL_ID = "0192f0c0-0000-7000-8000-000000000001"


@pytest.fixture
def fake_cli(tmp_path: Path) -> str:
    # The source tree is mounted read-only; copy the fake CLI somewhere executable.
    target = tmp_path / "claude"
    shutil.copy(FAKE, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return str(target)


@pytest.fixture
def runner(tmp_path: Path, fake_cli: str) -> ClaudeRunner:
    os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"
    return ClaudeRunner(
        lambda: "oauth-test-token", tmp_path / "runs", cli_path=fake_cli, max_concurrency=2
    )


def spec(prompt: str = "say OK", **kw: Any) -> RunSpec:
    base: dict[str, Any] = {
        "call_id": CALL_ID,
        "model": "claude-haiku-5-5",
        "effort": "low",
        "system": "Be brief.",
        "messages": (Message("user", prompt),),
        "json_schema": None,
        "timeout_s": 20,
    }
    base.update(kw)
    return RunSpec(**base)


async def test_run_ok_usage_and_safety_flags(runner: ClaudeRunner, tmp_path: Path) -> None:
    rec = tmp_path / "rec.json"
    os.environ["FAKE_CLAUDE_RECORD"] = str(rec)
    try:
        out = await runner.run(spec())
    finally:
        del os.environ["FAKE_CLAUDE_RECORD"]
    assert (out.status, out.text, out.model) == ("ok", "OK", "claude-haiku-5-5")
    assert out.usage == {
        "input_tokens": 12,
        "output_tokens": 3,
        "cache_read_tokens": 5,
        "cache_write_tokens": 7,
        "cache_write_1h_tokens": 4,
        "thinking_tokens": 2,
    }
    assert out.total_cost_usd == pytest.approx(0.0000123)
    assert out.effort_applied is True
    seen = json.loads(rec.read_text())
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == ""  # no tools at all
    assert argv[argv.index("--effort") + 1] == "low"
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert "--strict-mcp-config" in argv and "--setting-sources=" in argv
    assert "--system-prompt" not in argv  # never in argv ...
    assert seen["system_prompt"] == "Be brief."  # ... only in the run's file
    assert "say OK" not in " ".join(argv)  # the prompt goes over stdin
    assert seen["has_oauth_token"] and not seen["has_api_key"]
    assert seen["cwd_entries"] == []  # an empty working directory
    assert seen["home"].startswith(str(tmp_path / "runs"))
    assert list((tmp_path / "runs").iterdir()) == []  # wiped after the run


async def test_the_output_cap_reaches_the_cli(runner: ClaudeRunner, tmp_path: Path) -> None:
    """prompt 5.1 §2.6: a step's hard output cap is the CLI's own limit."""
    rec = tmp_path / "rec.json"
    os.environ["FAKE_CLAUDE_RECORD"] = str(rec)
    try:
        await runner.run(spec(max_output_tokens=777))
        capped = json.loads(rec.read_text())["max_output_tokens"]
        await runner.run(spec())
        free = json.loads(rec.read_text())["max_output_tokens"]
    finally:
        del os.environ["FAKE_CLAUDE_RECORD"]
    assert (capped, free) == ("777", None)


async def test_stream_and_structured_output(runner: ClaudeRunner) -> None:
    items = [i async for i in runner.stream(spec(json_schema={"type": "object"}))]
    assert [i.text for i in items if isinstance(i, Delta)] == ["O", "K"]
    final = items[-1]
    assert isinstance(final, Outcome) and final.structured == {"answer": "OK"}


@pytest.mark.parametrize(
    ("marker", "status", "error_class"),
    [
        ("[[fake:quota]]", "quota_exhausted", "usage_limit"),
        ("[[fake:ratelimit]]", "rate_limited", "rate_limit"),
        ("[[fake:error]]", "error", "error_during_execution"),
        ("[[fake:refusal]]", "refusal", "refusal"),
        ("[[fake:auth]]", "error", "auth_failed"),
        ("[[fake:auth401]]", "error", "auth_failed"),
    ],
)
async def test_failure_modes(
    runner: ClaudeRunner, marker: str, status: str, error_class: str
) -> None:
    out = await runner.run(spec(marker))
    assert (out.status, out.error_class) == (status, error_class)
    if status == "quota_exhausted":
        assert out.quota_resets_at and out.quota_resets_at > 1_700_000_000
        assert out.text is None


async def test_rate_limit_state_is_reported(runner: ClaudeRunner) -> None:
    """The Quota Controller's source (prompt 05 §8): the latest rate-limit event."""
    warn = await runner.run(spec("[[fake:warning]] hi"))
    assert warn.status == "ok"
    assert warn.rate_limit is not None
    assert warn.rate_limit["status"] == "allowed_warning"
    assert warn.rate_limit["window"] == "five_hour"
    assert warn.rate_limit["utilization"] == 0.85
    assert warn.rate_limit["resets_at"] and warn.rate_limit["resets_at"] > 1_700_000_000
    assert warn.as_json()["rate_limit"] == warn.rate_limit
    rejected = await runner.run(spec("[[fake:quota]]"))
    assert rejected.rate_limit is not None and rejected.rate_limit["status"] == "rejected"
    plain = await runner.run(spec("hello"))
    assert plain.rate_limit is None


def test_rate_limit_metadata_is_type_checked() -> None:
    from types import SimpleNamespace

    from claude_runtime.runner import rate_limit_of

    assert rate_limit_of(SimpleNamespace(status="weird")) is None
    odd = rate_limit_of(
        SimpleNamespace(status="allowed", rate_limit_type="x" * 99, utilization=7, resets_at=-1)
    )
    assert odd == {"status": "allowed", "window": None, "utilization": None, "resets_at": None}


async def test_timeout_and_missing_token(
    runner: ClaudeRunner, tmp_path: Path, fake_cli: str
) -> None:
    out = await runner.run(spec("[[fake:sleep]]", timeout_s=1))
    assert (out.status, out.error_class) == ("timeout", "timeout")
    no_token = ClaudeRunner(lambda: None, tmp_path / "r2", cli_path=fake_cli)
    assert (await no_token.run(spec())).error_class == "not_configured"
    broken = ClaudeRunner(lambda: "t", tmp_path / "r3", cli_path=str(tmp_path / "missing-cli"))
    assert (await broken.run(spec())).error_class.startswith("sdk_")


def test_quota_classifier_and_render() -> None:
    assert classify(Signals(rejected_resets_at=[None], text="limit|1800000000")).resets_at == 1.8e9
    assert classify(Signals(assistant_errors=["billing_error"])).status == "quota_exhausted"
    assert (
        classify(Signals(api_error_status=429, text="Claude usage limit reached")).status
        == "quota_exhausted"
    )
    assert classify(Signals(result_seen=False)).error_class == "no_result"
    assert (
        classify(Signals(result_seen=True, is_error=True, api_error_status=500)).error_class
        == "api_500"
    )
    assert classify(Signals(result_seen=True)).status == "ok"
    msgs = [Message("user", "hi"), Message("assistant", "hello"), Message("user", "more")]
    text = render(msgs)
    assert "<assistant>\nhello\n</assistant>" in text and text.endswith("as the assistant.")
    assert render([Message("user", "solo")]) == "solo"
    assert usage_from(None) is None
    # Older CLIs report neither the cache TTL split nor thinking tokens.
    bare = usage_from({"input_tokens": 3, "output_tokens": 1})
    assert bare is not None
    assert (bare["cache_write_1h_tokens"], bare["thinking_tokens"]) == (None, None)


async def test_http_api_auth_and_endpoints(runner: ClaudeRunner) -> None:
    router_token, metrics_token = tokens.new_token(), tokens.new_token()
    state = State(
        Settings(),
        router_token_sha256=tokens.digest(router_token),
        metrics_token_sha256=tokens.digest(metrics_token),
        oauth_token="x",
        runner=runner,
    )
    app = GuardMiddleware(build_app(state), state)
    body = {
        "call_id": CALL_ID,
        "model": "claude-haiku-5-5",
        "effort": "low",
        "system": None,
        "messages": [{"role": "user", "content": "hi"}],
        "json_schema": None,
        "timeout_s": 20,
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://rt") as c:
        for method, path in (
            ("POST", "/v1/run"),
            ("POST", "/v1/run/stream"),
            ("GET", "/v1/status"),
            ("GET", "/metrics"),
            ("GET", "/docs"),
            ("GET", "/nope"),
        ):
            assert (await c.request(method, path, json=body)).status_code == 401
            bad = {
                "Authorization": f"Bearer {metrics_token if path != '/metrics' else router_token}"
            }
            assert (await c.request(method, path, json=body, headers=bad)).status_code == 401
        auth = {"Authorization": f"Bearer {router_token}"}
        r = await c.post("/v1/run", json=body, headers=auth)
        assert r.status_code == 200 and r.json()["status"] == "ok"
        s = await c.post("/v1/run/stream", json=body, headers=auth)
        assert "event: delta" in s.text and "event: result" in s.text
        st = await c.get("/v1/status", headers=auth)
        assert st.json()["oauth_configured"] is True
        m = await c.get("/metrics", headers={"Authorization": f"Bearer {metrics_token}"})
        assert "claude_runtime_runs_total" in m.text
        bad_body = await c.post("/v1/run", json={**body, "call_id": "nope"}, headers=auth)
        assert bad_body.status_code == 422
    starting = State(Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=GuardMiddleware(build_app(starting), starting)),
        base_url="http://rt",
    ) as c:
        assert (await c.get("/v1/status")).status_code == 503
