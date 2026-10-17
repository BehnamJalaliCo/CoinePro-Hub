"""FastAPI app: the internal HTTP API of llm-router (no public port).

Every path needs a token: callers use their service token on /v1/*, and
Prometheus uses the metrics token on /metrics. There is no unauthenticated
endpoint (the container healthcheck reads a heartbeat file instead).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from hq_common import heartbeat, tokens
from hq_common.openbao import OpenBaoClient
from llm_router import __version__
from llm_router.auth import Caller, CallerDirectory, RateLimiter
from llm_router.backends.base import Backend
from llm_router.backends.claude_runtime import ClaudeRuntimeBackend
from llm_router.backends.fake import FakeBackend
from llm_router.backends.litellm_backend import LiteLLMBackend
from llm_router.config import Settings
from llm_router.db import Database
from llm_router.events import Events
from llm_router.metrics import Metrics
from llm_router.registry import Registry
from llm_router.scheduler import PriorityScheduler
from llm_router.schemas import RunRequest
from llm_router.service import RouterError, RouterService

log = logging.getLogger("llm_router")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


@dataclass
class State:
    settings: Settings
    metrics: Metrics = field(default_factory=Metrics)
    callers: CallerDirectory = field(default_factory=CallerDirectory)
    limiter: RateLimiter = field(default_factory=RateLimiter)
    service: RouterService | None = None
    db: Database | None = None
    events: Events | None = None
    bao: OpenBaoClient | None = None
    metrics_token_sha256: str = ""
    runtime_token: str = ""
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.service is not None


async def _json(
    send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]] | None = None
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), *(headers or [])],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


class GuardMiddleware:
    """Authentication for every path and a hard request-body cap."""

    def __init__(self, app: Any, state: State) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        st = self.state
        if not st.ready:
            await _json(send, 503, b'{"error":"starting"}', [(b"retry-after", b"5")])
            return
        headers = dict(scope["headers"])
        token = tokens.bearer(headers.get(b"authorization", b"").decode("latin-1"))
        if scope["path"] == "/metrics":
            if token is None or not tokens.matches(token, st.metrics_token_sha256):
                await _json(send, 401, b'{"error":"unauthorized"}')
                return
        else:
            caller = st.callers.lookup(token)
            if caller is None:
                await _json(send, 401, b'{"error":"unauthorized"}')
                return
            allowed, retry = st.limiter.allow(caller.name, caller.rpm)
            if not allowed:
                st.metrics.rate_limited.labels(caller.name).inc()
                await _json(
                    send, 429, b'{"error":"rate_limited"}', [(b"retry-after", str(retry).encode())]
                )
                return
            scope.setdefault("state", {})["caller"] = caller

        limit = st.settings.max_body_bytes
        length = headers.get(b"content-length")
        if length is not None and int(length) > limit:
            await _json(send, 413, b'{"error":"body_too_large"}')
            return
        seen = 0
        started = False

        async def counted_receive() -> MutableMapping[str, Any]:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return message

        async def tracked_send(message: MutableMapping[str, Any]) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except _TooLarge:
            if not started:
                await _json(send, 413, b'{"error":"body_too_large"}')


def _router_error(exc: RouterError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    body: dict[str, Any] = {"error": exc.code, "message": exc.message}
    if exc.call_id:
        body["call_id"] = exc.call_id
    return JSONResponse(body, status_code=exc.status_code, headers=headers)


def build_app(state: State) -> FastAPI:
    app = FastAPI(
        title="llm-router", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.hq = state

    @app.exception_handler(RouterError)
    async def _on_router_error(_: Request, exc: RouterError) -> JSONResponse:
        return _router_error(exc)

    @app.exception_handler(RequestValidationError)
    async def _on_invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted values back (they may hold prompt text).
        errors = [
            {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse({"error": "invalid_request", "details": errors}, status_code=422)

    def _caller(request: Request) -> Caller:
        caller: Caller = request.state.caller
        return caller

    def _service() -> RouterService:
        assert state.service is not None
        return state.service

    @app.post("/v1/run")
    async def run(req: RunRequest, request: Request) -> JSONResponse:
        caller = _caller(request)
        resp = await _service().run(req, caller.name, caller.max_input_chars)
        return JSONResponse(resp.model_dump(by_alias=True))

    @app.post("/v1/run/stream")
    async def run_stream(req: RunRequest, request: Request) -> StreamingResponse:
        caller = _caller(request)
        gen = await _service().stream(req, caller.name, caller.max_input_chars)
        return StreamingResponse(
            gen,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        svc = _service()
        db_ok = False
        with contextlib.suppress(Exception):
            db_ok = state.db is not None and await state.db.ping()
        return {
            "status": "ok" if db_ok else "degraded",
            "version": __version__,
            "db": db_ok,
            "nats": bool(state.events and state.events.connected),
            "queue": {
                "active": svc.scheduler.active,
                "capacity": svc.scheduler.capacity,
                "waiting": {f"P{p}": svc.scheduler.waiting(p) for p in range(5)},
            },
        }

    @app.get("/v1/connections")
    async def connections() -> dict[str, Any]:
        return {"connections": await _service().connections_view()}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(state.metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app


def create_app(settings: Settings | None = None) -> Any:
    """Production app: secrets from OpenBao, then DB, NATS and the backends."""
    state = State(settings or Settings())
    app = build_app(state)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        starter = asyncio.create_task(_start(state))
        state.tasks.append(starter)
        state.tasks.append(asyncio.create_task(heartbeat.run(lambda: _health(state))))
        try:
            yield
        finally:
            for t in state.tasks:
                t.cancel()
            if state.events:
                with contextlib.suppress(Exception):
                    await state.events.close()
            if state.db:
                await state.db.close()

    app.router.lifespan_context = lifespan
    return GuardMiddleware(app, state)


async def _health(state: State) -> dict[str, Any]:
    if not state.ready or state.db is None:
        return {"ok": False}
    return {"ok": await state.db.ping(), "nats": bool(state.events and state.events.connected)}


async def _load_secrets(state: State) -> None:
    assert state.bao is not None
    cfg = await state.bao.read_kv("llm-router/config")
    state.runtime_token = str(cfg["runtime_token"])
    state.metrics_token_sha256 = str(cfg["metrics_token_sha256"])
    callers = await state.bao.read_kv("llm-router/callers")
    n = state.callers.load(
        callers,
        default_rpm=state.settings.default_rpm,
        default_max_input_chars=state.settings.default_max_input_chars,
    )
    log.info("secrets loaded", extra={"callers": n})


async def _retry(what: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    delay = 2.0
    while True:
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - keep trying until dependencies are up
            log.warning(
                "waiting for dependency",
                extra={"dependency": what, "error_type": type(exc).__name__},
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def _start(state: State) -> None:
    s = state.settings
    state.bao = OpenBaoClient(s.openbao_addr, s.approle_file)
    await _retry("openbao", lambda: _load_secrets(state))
    state.db = await _retry("postgres", lambda: Database.connect(s))
    events = Events(
        s.nats_url,
        s.nats_user,
        s.nats_password,
        on_failure=lambda _subject: state.metrics.event_failures.inc(),
    )
    state.events = events

    async def connect_events() -> None:
        await _retry("nats", events.connect)

    state.tasks.append(asyncio.create_task(connect_events()))
    bao = state.bao
    backends: dict[str, Backend] = {
        "claude_subscription": ClaudeRuntimeBackend(s.runtime_url, lambda: state.runtime_token),
        "api": LiteLLMBackend(bao.read_kv),
    }
    if s.fake_backend:  # test environments only (prompt 05 §2); never in production
        backends["fake"] = FakeBackend()
        log.warning("fake model backend is on (test environment)")
    db = state.db
    assert db is not None
    service = RouterService(
        s,
        db,
        Registry(db, s.registry_ttl_s),
        events,
        state.metrics,
        PriorityScheduler(
            s.max_concurrency,
            s.reserved_high,
            s.p4_max_waiting,
            s.max_waiting,
            s.queue_retry_after_s,
        ),
        backends,
    )
    await _retry("quota", service.quota.load)
    closed = await _retry("ledger", service.close_stale)
    done = await _retry("maintenance", service.maintenance)
    log.info("router ready", extra={"stale_closed": closed, **done})
    state.service = service
    state.tasks += [
        asyncio.create_task(_every(60, lambda: _load_secrets(state), "callers")),
        asyncio.create_task(_every(6 * 3600, service.maintenance, "maintenance")),
        asyncio.create_task(_every(s.anomaly_interval_s, service.anomaly_scan, "anomaly")),
        asyncio.create_task(_every(s.quota_interval_s, service.quota_scan, "quota")),
    ]


async def _every(seconds: float, fn: Callable[[], Awaitable[Any]], name: str) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await fn()
        except Exception as exc:  # noqa: BLE001 - background jobs never stop the service
            log.warning(
                "background job failed", extra={"job": name, "error_type": type(exc).__name__}
            )
