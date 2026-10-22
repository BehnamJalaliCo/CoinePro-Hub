"""HTTP API of the Tool Gateway (hq-core only, no published port).

    POST /v1/tools/call   the runtime (worker) only: {token, step, index, tool, args}
    POST /v1/connectors/call  the worker only: one call of a connector of code
                          (prompt 10 §2.2: the revenue pulls; hq_gateway.revenue)
    GET  /v1/health       the runtime only
There is no unauthenticated endpoint: the container healthcheck reads a
heartbeat file. Bodies are capped; validation errors never echo values.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_common import charters, heartbeat, tokens
from hq_gateway import __version__
from hq_gateway.config import Settings
from hq_gateway.gateway import Gateway, Opa
from hq_gateway.mcp import SdkOpener
from hq_gateway.revenue import ConnectorCallIn, connector_call
from hq_gateway.tools import Api
from hq_gateway.web import Egress

log = logging.getLogger("hq_gateway")


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=2000)
    step: int = Field(ge=1, le=50)
    index: int = Field(default=0, ge=0, le=50)
    tool: str = Field(min_length=1, max_length=80)
    args: Any = None


class State:
    def __init__(self, settings: Settings, gateway: Gateway | None = None) -> None:
        self.settings = settings
        self.gateway = gateway
        self.worker_digest = ""

    def load_digest(self) -> None:
        path = Path(self.settings.worker_token_file)
        self.worker_digest = path.read_text().strip() if path.exists() else ""


class BodyLimit:
    """Caps a request body that has no Content-Length (chunked) while it is
    read: more than `max_bytes` is answered 413 before the app sees any of it."""

    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, receive, send)  # a disconnect: nothing to read
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                await JSONResponse({"error": "body_too_large"}, status_code=413)(
                    scope, receive, send
                )
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        replayed = False

        async def replay() -> Any:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def build_app(state: State) -> FastAPI:
    app = FastAPI(
        title="tool-gateway", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.gw = state
    # Inside the guard below (added later = outer): the runtime is authenticated first.
    app.add_middleware(BodyLimit, max_bytes=state.settings.max_body_bytes)

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Any:
        token = tokens.bearer(request.headers.get("authorization"))
        if (
            not state.worker_digest
            or token is None
            or not tokens.matches(token, state.worker_digest)
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        length = request.headers.get("content-length")
        if length is not None and (
            not length.isdigit() or int(length) > state.settings.max_body_bytes
        ):
            return JSONResponse({"error": "body_too_large"}, status_code=413)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"error": "invalid_request", "details": errors}, status_code=422)

    @app.post("/v1/tools/call")
    async def call(body: CallIn) -> JSONResponse:
        assert state.gateway is not None
        out = await state.gateway.call(body.token, body.step, body.index, body.tool, body.args)
        return JSONResponse(out.as_json())

    @app.post("/v1/connectors/call")
    async def connector(body: ConnectorCallIn) -> JSONResponse:
        assert state.gateway is not None
        return JSONResponse(await connector_call(state.gateway.api, body))

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        assert state.gateway is not None
        return {"status": "ok", "version": __version__, "roles": len(state.gateway.lib.roles)}

    return app


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()
    state = State(s)
    app = build_app(state)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        lib = charters.load()
        for problem in lib.problems:
            log.warning("charter problem", extra={"problem": problem[:300]})
        state.load_digest()
        egress = Egress(s.egress_url, s.tool_timeout_s) if s.egress_url else None
        api, opa = Api(s.api_url, s.call_timeout_s, egress=egress), Opa(s.opa_url)
        state.gateway = Gateway(
            lib,
            api,
            opa,
            max_result_chars=s.max_result_chars,
            tool_timeout_s=s.tool_timeout_s,
            deadline_s=s.deadline_s,
            # MCP servers (prompt 07 §3): http ones only through the egress proxy.
            mcp_opener=SdkOpener(s.egress_proxy_url, s.mcp_timeout_s),
        )

        async def check() -> dict[str, Any]:
            state.load_digest()  # a rotated digest file is picked up
            return {"ok": bool(state.worker_digest) and bool(lib.roles), "roles": len(lib.roles)}

        import asyncio

        beat = asyncio.create_task(heartbeat.run(check))
        try:
            yield
        finally:
            beat.cancel()
            await api.aclose()
            await opa.aclose()

    app.router.lifespan_context = lifespan
    return app
