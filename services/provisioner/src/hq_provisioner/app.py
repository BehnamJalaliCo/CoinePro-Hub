"""The provisioner's small API, for the api only (hq-prov; other clients are
refused before anything is read):

GET  /v1/pricing?type=cpx42&location=fsn1  the monthly EUR cost (Hetzner /pricing)
GET  /v1/servers                           every server of the project (read-only, PR-063)
POST /v1/wake                              look for a sealed plan now (no body)

Without the owner's Hetzner token: 503 channel_not_configured.
"""

from __future__ import annotations

import ipaddress
import re
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from hq_provisioner.config import Settings
from hq_provisioner.hetzner import Hetzner, message
from hq_provisioner.vault import NotConfigured, Secrets

TYPE = re.compile(r"^[a-z]{2,4}[0-9]{1,3}$")


def problem(status: int, code: str, detail: str = "") -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail[:200]}, status_code=status)


def build_app(
    settings: Settings,
    secrets_: Secrets,
    wake: threading.Event,
    hetzner: Callable[[str], Hetzner] | None = None,
) -> FastAPI:
    make = hetzner or (lambda token: Hetzner(token, settings.hetzner_url, settings.hetzner_poll_s))
    app = FastAPI(title="provisioner", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def only_the_api(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            ip = ipaddress.ip_address(request.client.host if request.client else "")
        except ValueError:
            return problem(403, "forbidden")
        if not any(ip in net for net in settings.api_clients):
            return problem(403, "forbidden")
        return await call_next(request)

    def client() -> Hetzner:
        return make(secrets_.hetzner_token())

    @app.get("/v1/pricing")
    def pricing(
        type: str = Query(min_length=2, max_length=10),
        location: str = Query(min_length=2, max_length=10),
    ) -> Any:
        if not TYPE.match(type):
            return problem(422, "validation_failed", "type")
        try:
            return client().pricing(type, location)
        except NotConfigured as exc:
            return problem(503, "channel_not_configured", str(exc))
        except LookupError as exc:
            return problem(422, "validation_failed", str(exc))
        except Exception as exc:  # noqa: BLE001 - Hetzner unreachable or refusing
            return problem(502, "hetzner_unavailable", message(exc))

    @app.get("/v1/servers")
    def servers() -> Any:
        try:
            return {"items": client().servers()}
        except NotConfigured as exc:
            return problem(503, "channel_not_configured", str(exc))
        except Exception as exc:  # noqa: BLE001
            return problem(502, "hetzner_unavailable", message(exc))

    @app.post("/v1/wake", status_code=202)
    def wake_up() -> dict[str, bool]:
        wake.set()
        return {"ok": True}

    return app
