"""FastAPI application: /api/v1 (owner), /internal/v1 (agents, services).

OpenAPI 3.1 comes from this app and is committed to openapi/hq-api.v1.json
(CI fails when it drifts). operationId = the handler's name (stable).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from hq_api import __version__, errors, media
from hq_api.errors import ApiError, problem_response
from hq_api.hub import Hub
from hq_api.openapi_examples import add_examples
from hq_api.routes import (
    agent_tools,
    audit_control,
    auth,
    backups,
    decisions,
    deliverables,
    egress,
    errands,
    files,
    inbox,
    inquiries,
    internal,
    messages,
    meta,
    notifications,
    orders,
    org,
    owner,
    runs,
    stream,
    tools,
    treasury,
    work,
    workshop,
)

log = logging.getLogger("hq_api.access")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# Raw-body uploads and their own size caps (checked again while streaming).
UPLOAD_PATHS = ("/internal/v1/files", "/api/v1/files", "/api/v1/transcribe")


def upload_limit(path: str, max_file: int, max_body: int) -> int:
    if path == "/api/v1/files":
        return media.VIDEO.max_bytes  # the largest kind; each kind is held to its own
    if path == "/api/v1/transcribe":
        return media.AUDIO.max_bytes
    return max_file if path in UPLOAD_PATHS else max_body


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    hub: Hub | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    *,
    openapi_url: str | None = "/api/v1/openapi.json",
) -> FastAPI:
    app = FastAPI(
        title="CoinePro HQ Core API",
        version="1.0.0",
        summary="Holding core: identity, organisation, work, inboxes, notifications, audit.",
        description=(
            "Contract: contracts/HQ_CORE_API_v1.md. Public endpoints live under /api/v1 "
            "(owner only, passkey sessions); /internal/v1 is for agents and services and is "
            "never routed by the public edge. Errors are application/problem+json with a "
            "stable `code` and a Persian `message_fa`."
        ),
        generate_unique_id_function=_operation_id,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=openapi_url,
        servers=[{"url": "/"}],
    )
    if hub is not None:
        app.state.hub = hub
    errors.install(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id", "")
        request.state.request_id = rid if _REQUEST_ID.match(rid) else str(uuid.uuid4())
        settings = request.app.state.hub.settings
        limit = upload_limit(request.url.path, settings.max_file_bytes, settings.max_body_bytes)
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return problem_response(
                request, ApiError(413, "validation_failed", "request body too large")
            )
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = request.scope.get("route")
        log.info(
            "request",
            extra={
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": request.state.request_id,
            },
        )
        return response

    for module in (
        meta,
        auth,
        org,
        work,
        decisions,
        deliverables,
        files,
        messages,
        inbox,
        notifications,
        owner,
        audit_control,
        treasury,
        stream,
        runs,
        workshop,
        orders,
        backups,
        tools,
        egress,
        inquiries,
        errands,
    ):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(internal.router, prefix="/internal/v1")
    app.include_router(agent_tools.router, prefix="/internal/v1")
    app.include_router(workshop.internal_router, prefix="/internal/v1")
    app.include_router(tools.internal_router, prefix="/internal/v1")
    app.include_router(egress.internal_router, prefix="/internal/v1")
    app.include_router(inquiries.internal_router, prefix="/internal/v1")
    app.include_router(errands.internal_router, prefix="/internal/v1")
    app.state.version = __version__

    plain_openapi = app.openapi

    def openapi_with_examples() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = add_examples(plain_openapi())
        return app.openapi_schema

    app.openapi = openapi_with_examples  # type: ignore[method-assign]
    return app


async def _noop(_: FastAPI) -> AsyncIterator[None]:
    yield


def openapi_document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()
