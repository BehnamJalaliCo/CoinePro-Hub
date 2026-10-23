"""`python -m hq_api`: the core API (/api/v1 behind Caddy, /internal/v1 on hq-internal).

Startup waits (with backoff) for OpenBao, Postgres, NATS and OPA; Temporal is
optional at runtime (the worker reconciles). Background tasks: the outbox
relay, the heartbeat file (container healthcheck) and a secrets refresh.
The OpenAPI document is not served here: the committed openapi/hq-api.v1.json
is the published contract.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import uvicorn
from fastapi import FastAPI

from hq_api import secrets, workflows_client
from hq_api.app import create_app
from hq_api.channels import Channels
from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database
from hq_api.domain import founding, gov_authority
from hq_api.events import Bus, OutboxRelay
from hq_api.hub import Hub
from hq_api.live import LiveHub
from hq_api.policy import Policy
from hq_api.storage import LocalStorage
from hq_api.workshop import service as workshop
from hq_common import charters, heartbeat, logs
from hq_common.openbao import OpenBaoClient

log = logging.getLogger("hq_api")
SECRETS_REFRESH_S = 300.0


async def retry(what: str, fn: Callable[[], Awaitable[Any]]) -> Any:
    delay = 2.0
    while True:
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - wait for dependencies
            log.warning(
                "waiting for dependency",
                extra={"dependency": what, "error_type": type(exc).__name__},
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def build(s: Settings) -> tuple[Hub, OpenBaoClient]:
    bao = OpenBaoClient(s.openbao_addr, s.approle_file)
    sec = await retry("openbao", lambda: secrets.load(bao))
    db = Database.create(s)
    await retry("postgres", db.ping)
    bus = Bus(s)
    await retry("nats", bus.connect)
    policy = Policy(s.opa_url)

    async def opa_ready() -> None:
        if not await policy.healthy():
            raise ConnectionError("opa not healthy")

    await retry("opa", opa_ready)
    hub = Hub(
        settings=s,
        db=db,
        companies=Companies(db),
        secrets=sec,
        policy=policy,
        storage=LocalStorage(s.files_root),
        bus=bus,
    )
    hub.bao = bao
    hub.channels = Channels(hub)
    hub.charters = charters.load()
    hub.live = LiveHub()
    for problem in hub.charters.problems:
        log.warning("charter problem", extra={"problem": problem[:300]})
    try:
        hub.temporal = await workflows_client.connect(s.temporal_address, s.temporal_namespace)
    except Exception:  # noqa: BLE001 - optional at runtime; the worker reconciles
        log.warning("temporal unavailable at start; continuing without it")
    return hub, bao


async def refresh_secrets(hub: Hub, bao: OpenBaoClient) -> None:
    while True:
        await asyncio.sleep(SECRETS_REFRESH_S)
        try:
            hub.secrets = await secrets.load(bao)
        except Exception:  # noqa: BLE001 - keep the last good secrets
            log.warning("secrets refresh failed; keeping the previous ones")


async def health(hub: Hub) -> dict[str, Any]:
    ok = await hub.db.ping()
    return {"ok": ok and bool(hub.bus and hub.bus.connected), "temporal": hub.temporal is not None}


def make_app(s: Settings) -> FastAPI:
    tasks: list[asyncio.Task[Any]] = []

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hub, bao = await build(s)
        app.state.hub = hub
        assert hub.bus is not None
        if s.outbox_relay:
            tasks.append(asyncio.create_task(OutboxRelay(s, hub.db, hub.bus).run()))
        tasks.append(asyncio.create_task(refresh_secrets(hub, bao)))
        tasks.append(asyncio.create_task(heartbeat.run(lambda: health(hub))))
        # ⟨1.5⟩ prompt 11 §7: the authority matrix to OPA at start (then at every use)
        tasks.append(asyncio.create_task(gov_authority.push_at_start(hub)))
        hub.workshop = await workshop.build(hub)
        if hub.workshop is not None:
            tasks.append(asyncio.create_task(workshop.loop(hub)))
        if s.provisioner_url:
            # PR-063 (prompt 09): the Hetzner project's servers, read-only
            tasks.append(asyncio.create_task(founding.inventory_loop(hub)))
            # Review 9.2 §2.3: builds the provisioner went quiet on (rule-only)
            tasks.append(asyncio.create_task(founding.reaper_loop(hub)))
        log.info(
            "api ready",
            extra={"login_configured": s.login_configured, "workshop": workshop.meta_runtime(hub)},
        )
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if hub.channels is not None:
                with contextlib.suppress(Exception):
                    await hub.channels.aclose()
            await hub.policy.aclose()
            await bao.aclose()
            await hub.bus.close()
            await hub.db.close()

    # The OpenAPI document is not served: the committed file is the contract.
    return create_app(lifespan=lifespan, openapi_url=None)


def main() -> None:
    s = Settings()
    logs.setup("hq-api", s.log_level)
    uvicorn.run(
        make_app(s),
        host="0.0.0.0",
        port=s.listen_port,
        log_config=None,
        server_header=False,
        # hq_api.security.deps reads Caddy's X-Forwarded-For itself.
        proxy_headers=False,
        # The app logs method, route template and status (no query strings,
        # which can carry search text); uvicorn's own access line would not.
        access_log=False,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    main()
