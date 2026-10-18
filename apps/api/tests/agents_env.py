"""The agent runtime under test (prompt 05 §2, §12): llm-router with the FAKE
model, the Tool Gateway and the api, all in this process; the runner runs on
the worker's hub. No real model call is ever made in CI."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx

sys.path[:0] = ["/w/llm-router/src", "/w/gateway/src"]

from hq_gateway.app import State as GwState  # noqa: E402
from hq_gateway.app import build_app as gateway_app  # noqa: E402
from hq_gateway.config import Settings as GwSettings  # noqa: E402
from hq_gateway.gateway import Gateway as GatewayCore  # noqa: E402
from hq_gateway.gateway import Opa  # noqa: E402
from hq_gateway.tools import Api as GatewayApi  # noqa: E402
from llm_router.backends.fake import FakeBackend  # noqa: E402
from llm_router.config import Settings as RouterSettings  # noqa: E402
from llm_router.db import Database as RouterDB  # noqa: E402
from llm_router.events import Events  # noqa: E402
from llm_router.main import GuardMiddleware  # noqa: E402
from llm_router.main import State as RouterState  # noqa: E402
from llm_router.main import build_app as router_app  # noqa: E402
from llm_router.metrics import Metrics  # noqa: E402
from llm_router.registry import Registry  # noqa: E402
from llm_router.scheduler import PriorityScheduler  # noqa: E402
from llm_router.service import RouterService  # noqa: E402

from hq_api.agents.clients import Gateway, LivePush, Router  # noqa: E402
from hq_api.agents.runner import Runner  # noqa: E402
from hq_api.hub import Hub  # noqa: E402
from hq_common.tokens import digest  # noqa: E402


@dataclass
class AgentsEnv:
    fake: FakeBackend
    router: Router
    gateway: Gateway
    live: LivePush
    runner: Runner
    service: RouterService
    whub: Hub
    close: Any
    core: Any = None  # the gateway itself (tests wire a fake egress into core.api.egress)


async def build(
    api_app: Any, whub: Hub, host: str, router_token: str, gateway_token: str
) -> AgentsEnv:
    rs = RouterSettings(
        db_host=host,
        db_user="llm_router",
        db_password=os.environ.get("LLM_ROUTER_DB_PASSWORD", ""),
        nats_url=os.environ.get("TEST_NATS_URL", "nats://nats:4222"),
        nats_password=os.environ.get("NATS_PASSWORD", ""),
        max_concurrency=6,
        registry_ttl_s=0,
    )
    rdb = await RouterDB.connect(rs, max_size=4)
    events = Events(rs.nats_url, rs.nats_user, rs.nats_password)
    await events.connect()
    fake = FakeBackend()
    service = RouterService(
        rs,
        rdb,
        Registry(rdb, 0),
        events,
        Metrics(),
        PriorityScheduler(6, 1, 4, 32, 7),
        {"claude_subscription": fake, "fake": fake, "api": fake},
    )
    rstate = RouterState(rs)
    rstate.service, rstate.db, rstate.events = service, rdb, events
    rstate.callers.load(
        {
            "callers": {
                "hq-agents": {
                    "token_sha256": digest(router_token),
                    "rpm": 100_000,
                    "max_input_chars": 500_000,
                }
            }
        },
        default_rpm=60,
        default_max_input_chars=200_000,
    )
    router_asgi = GuardMiddleware(router_app(rstate), rstate)
    api_transport = httpx.ASGITransport(app=api_app)
    core = GatewayCore(
        whub.charters,
        GatewayApi("http://api.test", 15, transport=api_transport),
        Opa(whub.settings.opa_url),
        max_result_chars=8000,
        tool_timeout_s=20,
    )
    gstate = GwState(GwSettings())
    gstate.gateway, gstate.worker_digest = core, digest(gateway_token)
    router = Router(
        "http://router.test", lambda: router_token, transport=httpx.ASGITransport(app=router_asgi)
    )
    gateway = Gateway(
        "http://gateway.test",
        lambda: gateway_token,
        transport=httpx.ASGITransport(app=gateway_app(gstate)),
    )
    live = LivePush("http://api.test", transport=api_transport)
    runner = Runner(whub, router, gateway, live)

    async def close() -> None:
        await router.aclose()
        await gateway.aclose()
        await core.api.aclose()
        await core.opa.aclose()
        await events.close()
        await rdb.close()

    return AgentsEnv(fake, router, gateway, live, runner, service, whub, close, core)
