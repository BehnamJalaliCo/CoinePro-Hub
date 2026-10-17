"""HTTP API of claude-runtime. Callers: llm-router only (token), Prometheus (/metrics).

Secrets (OpenBao, read at start; `make claude-token` restarts the service):
    kv/claude-runtime/config  {"router_token_sha256", "metrics_token_sha256"}
    kv/claude-runtime/oauth   {"token"}  (CLAUDE_CODE_OAUTH_TOKEN; may be absent)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ConfigDict, Field

from claude_runtime import __version__
from claude_runtime.config import Settings
from claude_runtime.runner import ClaudeRunner, Delta, Message, Outcome, RunSpec
from hq_common import heartbeat, tokens
from hq_common.openbao import OpenBaoClient, SecretNotFound

log = logging.getLogger("claude_runtime")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


class RunMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    model: str = Field(min_length=1, max_length=100)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    system: str | None = None
    messages: list[RunMessage] = Field(min_length=1)
    json_schema: dict[str, Any] | None = None
    timeout_s: int = Field(ge=1, le=3600)
    # The call's hard output cap (prompt 5.1 §2.6), given to the CLI.
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)

    def spec(self) -> RunSpec:
        return RunSpec(
            self.call_id,
            self.model,
            self.effort,
            self.system,
            tuple(Message(m.role, m.content) for m in self.messages),
            self.json_schema,
            self.timeout_s,
            self.max_output_tokens,
        )


class Metrics:
    def __init__(self) -> None:
        r = self.registry = CollectorRegistry()
        self.runs = Counter(
            "claude_runtime_runs_total", "Runs by status", ["model", "status"], registry=r
        )
        self.seconds = Histogram(
            "claude_runtime_run_seconds",
            "Run duration",
            ["model"],
            registry=r,
            buckets=(0.5, 1, 2, 5, 10, 20, 40, 80, 160, 320, 640),
        )
        self.active = Gauge("claude_runtime_active_runs", "Runs in progress", registry=r)
        self.oauth = Gauge(
            "claude_runtime_oauth_configured", "1 when a subscription token is set", registry=r
        )
        self.quota = Counter(
            "claude_runtime_quota_signals_total", "Usage-limit signals from the CLI", registry=r
        )

    def record(self, o: Outcome) -> None:
        model = o.model or "-"
        self.runs.labels(model, o.status).inc()
        self.seconds.labels(model).observe(o.duration_ms / 1000)
        if o.status == "quota_exhausted":
            self.quota.inc()


@dataclass
class State:
    settings: Settings
    metrics: Metrics = field(default_factory=Metrics)
    router_token_sha256: str = ""
    metrics_token_sha256: str = ""
    oauth_token: str | None = field(default=None, repr=False)
    runner: ClaudeRunner | None = None
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)


async def _json(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


class GuardMiddleware:
    def __init__(self, app: Any, state: State) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        st = self.state
        if st.runner is None:
            await _json(send, 503, b'{"error":"starting"}')
            return
        token = tokens.bearer(dict(scope["headers"]).get(b"authorization", b"").decode("latin-1"))
        expected = (
            st.metrics_token_sha256 if scope["path"] == "/metrics" else st.router_token_sha256
        )
        if token is None or not tokens.matches(token, expected):
            await _json(send, 401, b'{"error":"unauthorized"}')
            return
        await self.app(scope, receive, send)


def build_app(state: State) -> FastAPI:
    app = FastAPI(
        title="claude-runtime", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Any, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"error": "invalid_request", "details": errors}, status_code=422)

    def runner() -> ClaudeRunner:
        assert state.runner is not None
        return state.runner

    @app.post("/v1/run")
    async def run(body: RunBody) -> JSONResponse:
        state.metrics.active.inc()
        try:
            outcome = await runner().run(body.spec())
        finally:
            state.metrics.active.dec()
        state.metrics.record(outcome)
        log.info(
            "run finished",
            extra={
                "call_id": body.call_id,
                "model": outcome.model,
                "status": outcome.status,
                "error_class": outcome.error_class,
                "duration_ms": outcome.duration_ms,
            },
        )
        return JSONResponse(outcome.as_json())

    @app.post("/v1/run/stream")
    async def run_stream(body: RunBody) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            state.metrics.active.inc()
            try:
                async for item in runner().stream(body.spec()):
                    if isinstance(item, Delta):
                        yield f"event: delta\ndata: {json.dumps({'text': item.text})}\n\n"
                    else:
                        state.metrics.record(item)
                        log.info(
                            "run finished",
                            extra={
                                "call_id": body.call_id,
                                "model": item.model,
                                "status": item.status,
                                "error_class": item.error_class,
                                "duration_ms": item.duration_ms,
                            },
                        )
                        yield f"event: result\ndata: {json.dumps(item.as_json())}\n\n"
            finally:
                state.metrics.active.dec()

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/v1/status")
    async def status() -> dict[str, Any]:
        r = runner()
        return {
            "version": __version__,
            "oauth_configured": bool(state.oauth_token),
            "active_runs": r.active,
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        state.metrics.oauth.set(1 if state.oauth_token else 0)
        return Response(generate_latest(state.metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app


async def _start(state: State) -> None:
    s = state.settings
    bao = OpenBaoClient(s.openbao_addr, s.approle_file)
    delay = 2.0
    while True:
        try:
            cfg = await bao.read_kv("claude-runtime/config")
            state.router_token_sha256 = str(cfg["router_token_sha256"])
            state.metrics_token_sha256 = str(cfg["metrics_token_sha256"])
            try:
                state.oauth_token = (
                    str((await bao.read_kv("claude-runtime/oauth"))["token"]) or None
                )
            except SecretNotFound:
                state.oauth_token = None
            break
        except Exception as exc:  # noqa: BLE001 - wait for OpenBao
            log.warning("waiting for openbao", extra={"error_type": type(exc).__name__})
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
    await bao.aclose()
    state.runner = ClaudeRunner(
        lambda: state.oauth_token,
        s.workdir_root,
        cli_path=s.cli_path,
        max_concurrency=s.max_concurrency,
    )
    state.metrics.oauth.set(1 if state.oauth_token else 0)
    log.info("runtime ready", extra={"oauth_configured": bool(state.oauth_token)})


def create_app(settings: Settings | None = None) -> Any:
    state = State(settings or Settings())
    app = build_app(state)

    async def health() -> dict[str, Any]:
        return {
            "ok": state.runner is not None,
            "oauth": "configured" if state.oauth_token else "missing",
        }

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.tasks = [
            asyncio.create_task(_start(state)),
            asyncio.create_task(heartbeat.run(health)),
        ]
        try:
            yield
        finally:
            for t in state.tasks:
                t.cancel()

    app.router.lifespan_context = lifespan
    return GuardMiddleware(app, state)
