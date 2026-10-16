"""HTTP layer (auth on every path, limits), log hygiene, and backend adapters."""

from __future__ import annotations

import io
import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import asyncpg
import httpx
import pytest

from hq_common import logs, tokens
from llm_router.backends.base import BackendCall, BackendResult, ChatMessage, Delta
from llm_router.backends.claude_runtime import ClaudeRuntimeBackend
from llm_router.backends.litellm_backend import (
    LiteLLMBackend,
    classify_error,
    model_name,
    usage_from,
)
from llm_router.main import GuardMiddleware, State, build_app
from llm_router.registry import Connection

from .conftest import Captured, FakeBackend, ok_result

CALLER_TOKEN = tokens.new_token()
METRICS_TOKEN = tokens.new_token()
TEXT_MARKER = "ZEBRA-PROMPT-4471"  # must never appear in logs, events or the ledger


def make_state(settings: Any, service: Any, rpm: int = 1000) -> State:
    state = State(settings)
    state.service = service
    state.metrics = service.metrics
    state.db = service.db
    state.metrics_token_sha256 = tokens.digest(METRICS_TOKEN)
    state.callers.load(
        {"callers": {"tests": {"token_sha256": tokens.digest(CALLER_TOKEN), "rpm": rpm}}},
        default_rpm=60,
        default_max_input_chars=10_000,
    )
    return state


def client(state: State) -> httpx.AsyncClient:
    app = GuardMiddleware(build_app(state), state)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://router")


BODY = {
    "company_code": "TY",
    "actor_ref": "TY-TECH-01",
    "task_class": "general",
    "priority": "P2",
    "prompt": "hello",
    "timeout_s": 30,
}


def auth(token: str = CALLER_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_no_endpoint_without_authentication(
    su: asyncpg.Connection, settings: Any, make_service: Any
) -> None:
    state = make_state(settings, make_service())
    app = build_app(state)
    paths = {(m, r.path) for r in app.routes for m in getattr(r, "methods", set())} | {
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("GET", "/redoc"),
        ("GET", "/nope"),
    }
    assert ("POST", "/v1/run") in paths and ("GET", "/metrics") in paths
    async with client(state) as c:
        for method, path in sorted(paths):
            for headers in ({}, auth("wrong"), {"Authorization": "Basic x"}):
                r = await c.request(method, path, headers=headers, json=BODY)
                assert r.status_code == 401, (method, path, headers)
        assert (
            await c.get("/metrics", headers=auth())
        ).status_code == 401  # caller token is not enough
        m = await c.get("/metrics", headers=auth(METRICS_TOKEN))
        assert m.status_code == 200 and "llm_calls_total" in m.text
        assert (await c.get("/v1/health", headers=auth(METRICS_TOKEN))).status_code == 401
        for path in ("/docs", "/openapi.json", "/redoc"):  # no docs, even with a token
            assert (await c.get(path, headers=auth())).status_code == 404
    starting = State(settings)  # before secrets are loaded nothing is served
    async with client(starting) as c:
        assert (await c.get("/v1/health", headers=auth())).status_code == 503


async def test_api_run_health_connections_and_limits(
    su: asyncpg.Connection, settings: Any, make_service: Any
) -> None:
    state = make_state(settings, make_service())
    async with client(state) as c:
        r = await c.post("/v1/run", headers=auth(), json=BODY)
        assert r.status_code == 200, r.text
        body = r.json()
        assert (
            body["status"] == "ok"
            and body["connection"] == "claude-max"
            and body["usage"]["input_tokens"] == 100
        )
        h = await c.get("/v1/health", headers=auth())
        assert h.json()["db"] is True and h.json()["queue"]["capacity"] == 3
        conns = (await c.get("/v1/connections", headers=auth())).json()["connections"]
        assert {x["key"] for x in conns} >= {
            "claude-max",
            "anthropic-api",
            "openai",
            "google-gemini",
        }
        assert not any("secret" in k for x in conns for k in x)  # no secret refs or keys
        big = await c.post("/v1/run", headers=auth(), content=b"x" * (settings.max_body_bytes + 1))
        assert big.status_code == 413
        bad = await c.post(
            "/v1/run", headers=auth(), json={**BODY, "prompt": TEXT_MARKER, "priority": 9}
        )
        assert bad.status_code == 422 and TEXT_MARKER not in bad.text  # input is never echoed
    limited_state = make_state(settings, make_service(), rpm=2)
    async with client(limited_state) as c:
        assert (
            await c.post("/v1/run", headers=auth(), json={**BODY, "priority": 9})
        ).status_code == 422
        assert (await c.get("/v1/health", headers=auth())).status_code == 200
        limited = await c.post("/v1/run", headers=auth(), json=BODY)  # every request counts
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    state2 = make_state(settings, make_service())
    async with client(state2) as c:
        r = await c.post("/v1/run", headers=auth(), json={**BODY, "company_code": "ZZ"})
        assert r.status_code == 422 and r.json()["error"] == "unknown_company"
        s = await c.post("/v1/run/stream", headers=auth(), json=BODY)
        assert s.status_code == 200 and "event: end" in s.text


async def test_prompt_text_never_reaches_logs_events_or_ledger(
    su: asyncpg.Connection, settings: Any, make_service: Any, captured: Captured
) -> None:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logs.JsonFormatter("llm-router"))
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        backend = FakeBackend(
            ok_result(text=f"answer {TEXT_MARKER}"),
            BackendResult("error", error_class="server_error"),
            ok_result(text=f"streamed {TEXT_MARKER}"),
        )
        state = make_state(settings, make_service(subscription=backend))
        payload = {
            **BODY,
            "system": f"system {TEXT_MARKER}",
            "messages": [{"role": "user", "content": f"user {TEXT_MARKER}"}],
        }
        payload.pop("prompt")
        async with client(state) as c:
            assert (await c.post("/v1/run", headers=auth(), json=payload)).status_code == 200
            assert (await c.post("/v1/run", headers=auth(), json=payload)).status_code == 200
            assert (await c.post("/v1/run/stream", headers=auth(), json=payload)).status_code == 200
            await c.post("/v1/run", headers=auth(), json={**payload, "company_code": "ZZ"})
            await c.post("/v1/run", headers=auth(), json={**payload, "priority": 7})
        import asyncio

        await asyncio.sleep(0.3)
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    log_text = buf.getvalue()
    assert "call finished" in log_text  # metadata is logged ...
    assert TEXT_MARKER not in log_text  # ... text is not
    assert captured.messages and TEXT_MARKER not in captured.raw()
    rows = await su.fetch("SELECT row_to_json(c)::text AS j FROM llm.calls c")
    assert len(rows) == 3 and not any(TEXT_MARKER in r["j"] for r in rows)
    assert await su.fetchval("SELECT count(*) FROM llm.transcripts") == 0  # opt-in only


# ---------------------------------------------------------------- backends --
def _conn(**kw: Any) -> Connection:
    from datetime import UTC, datetime

    base: dict[str, Any] = {
        "id": "c",
        "key": "k",
        "kind": "api",
        "provider": "openai",
        "display_name": "x",
        "status": "enabled",
        "status_changed_at": datetime.now(UTC),
        "quota_reset_at": None,
        "secret_ref": "kv/llm-connections/openai",
        "api_base": None,
        "models": ("gpt-x",),
        "default_model": "gpt-x",
        "pricing": {},
        "limits": {},
        "fallback_priority": 2,
    }
    base.update(kw)
    return Connection(**base)


def _call(conn: Connection, **kw: Any) -> BackendCall:
    base: dict[str, Any] = {
        "call_id": "id1",
        "connection": conn,
        "model": "gpt-x",
        "effort": "high",
        "system": "sys",
        "messages": (ChatMessage("user", "hi"),),
        "json_schema": {"type": "object"},
        "timeout_s": 5,
    }
    base.update(kw)
    return BackendCall(**base)


async def test_runtime_backend_run_stream_and_errors() -> None:
    result_json = {
        "status": "ok",
        "text": "OK",
        "model": "claude-haiku-5-5",
        "total_cost_usd": 0.0001,
        "usage": {
            "input_tokens": 3,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "thinking_tokens": None,
        },
        "stop_reason": "end_turn",
        "effort_applied": True,
    }
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        if request.url.path == "/v1/run":
            return httpx.Response(200, json=result_json)
        sse = f"event: delta\ndata: {json.dumps({'text': 'O'})}\n\nevent: result\ndata: {json.dumps(result_json)}\n\n"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    backend = ClaudeRuntimeBackend(
        "http://rt", lambda: "rt-token", transport=httpx.MockTransport(handler)
    )
    call = _call(_conn(kind="claude_subscription"), model="claude-haiku-5-5")
    r = await backend.run(call)
    assert (
        r.status == "ok" and r.sdk_cost_usd == Decimal("0.0001") and r.usage and r.usage.total == 4
    )
    items = [i async for i in backend.stream(call)]
    assert isinstance(items[0], Delta) and isinstance(items[-1], BackendResult)
    assert seen == ["Bearer rt-token", "Bearer rt-token"]

    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/run":
            return httpx.Response(500)
        raise httpx.ConnectError("down")

    bad = ClaudeRuntimeBackend("http://rt", lambda: "t", transport=httpx.MockTransport(failing))
    assert (await bad.run(call)).error_class == "runtime_http_500"
    last = [i async for i in bad.stream(call)][-1]
    assert isinstance(last, BackendResult) and last.error_class == "runtime_unreachable"

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    timeout = ClaudeRuntimeBackend("http://rt", lambda: "t", transport=httpx.MockTransport(slow))
    assert (await timeout.run(call)).status == "timeout"


class _RateLimitError(Exception):
    message = "Rate limit reached"


class _QuotaError(Exception):
    message = "You exceeded your current quota (insufficient_quota)"


_QuotaError.__name__ = _RateLimitError.__name__ = "RateLimitError"


async def test_litellm_backend_with_stubbed_completion() -> None:
    secrets_read: list[str] = []

    async def read_secret(path: str) -> dict[str, Any]:
        secrets_read.append(path)
        return {"api_key": "sk-test"}

    usage = SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=30,
        prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=12),
    )
    seen: dict[str, Any] = {}

    async def completion(**kwargs: Any) -> Any:
        seen.update(kwargs)
        if kwargs.get("stream"):

            async def chunks() -> Any:
                yield SimpleNamespace(
                    usage=None,
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="he"), finish_reason=None)
                    ],
                )
                yield SimpleNamespace(
                    usage=usage,
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="y"), finish_reason="stop")
                    ],
                )

            return chunks()
        return SimpleNamespace(
            model="gpt-x",
            usage=usage,
            choices=[SimpleNamespace(message=SimpleNamespace(content="hey"), finish_reason="stop")],
        )

    backend = LiteLLMBackend(read_secret, completion=completion)
    conn = _conn(api_base="https://compat.example/v1", provider="openai_compatible")
    r = await backend.run(_call(conn))
    assert (r.status, r.text) == ("ok", "hey")
    assert r.usage is not None
    assert (r.usage.input_tokens, r.usage.cache_read_tokens, r.usage.thinking_tokens) == (
        100,
        20,
        12,
    )
    assert seen["model"] == "openai/gpt-x" and seen["api_base"] == "https://compat.example/v1"
    assert seen["reasoning_effort"] == "high" and seen["response_format"]["type"] == "json_schema"
    assert seen["messages"][0] == {"role": "system", "content": "sys"}
    assert secrets_read == ["llm-connections/openai"]
    items = [i async for i in backend.stream(_call(conn))]
    final = items[-1]
    assert isinstance(final, BackendResult) and final.text == "hey"

    async def boom(**_: Any) -> Any:
        raise _QuotaError()

    assert (
        await LiteLLMBackend(read_secret, completion=boom).run(_call(conn))
    ).status == "quota_exhausted"
    assert classify_error(_RateLimitError()) == ("rate_limited", "RateLimitError")
    timeout_cls = type("Timeout", (Exception,), {})
    policy_cls = type("ContentPolicyViolationError", (Exception,), {})
    assert classify_error(timeout_cls())[0] == "timeout"
    assert classify_error(policy_cls())[0] == "refusal"
    assert classify_error(ValueError())[0] == "error"
    assert usage_from(None).total == 0
    assert model_name(_conn(provider="gemini"), "g") == "gemini/g"
    with pytest.raises(ValueError):
        model_name(_conn(provider="mystery"), "m")
    no_secret = _conn(secret_ref=None)
    assert (await backend.run(_call(no_secret))).status == "error"
