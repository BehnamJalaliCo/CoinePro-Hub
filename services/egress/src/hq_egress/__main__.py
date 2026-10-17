"""`python -m hq_egress`: the API on :8090 (the gateway's network), the
browser's proxy on :3128 and the gateway's proxy on :3129, in one process."""

from __future__ import annotations

import asyncio
from typing import Any

import uvicorn

from hq_common import heartbeat, logs
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.proxy import Buckets, Proxy


async def serve(s: Settings) -> None:
    guard = Guard(hub_hosts=s.hub_hosts)
    buckets = Buckets()
    state = State(s, guard, buckets)
    browser = Proxy(guard, buckets, mode="browser", clients=s.browser_proxy_clients)
    gateway = Proxy(guard, buckets, mode="gateway", clients=s.gateway_proxy_clients)
    servers = [
        await browser.serve("0.0.0.0", s.browser_proxy_port),
        await gateway.serve("0.0.0.0", s.gateway_proxy_port),
    ]
    api = uvicorn.Server(
        uvicorn.Config(
            build_app(state),
            host="0.0.0.0",
            port=s.api_port,
            log_config=None,
            access_log=False,
            proxy_headers=False,
            server_header=False,
        )
    )

    async def check() -> dict[str, Any]:
        return {"ok": all(srv.is_serving() for srv in servers) and api.started}

    await asyncio.gather(api.serve(), heartbeat.run(check))


def main() -> None:
    s = Settings()
    logs.setup("egress", s.log_level)
    asyncio.run(serve(s))


if __name__ == "__main__":
    main()
