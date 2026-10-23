"""`python -m hq_egress`: the API on :8090 (the gateway's network), the
browser's proxy on :3128, the gateway's proxy on :3129 and the provisioner's
on :3130 (prompt 09: CONNECT to api.hetzner.cloud only), in one process;
prompt 12 §9.1 adds the substitute runner's on :3131 (CONNECT to its CLIs'
hosts only), the profile browser's on :3132 (one job's bucket, its site's own
hosts only) and the owner's sign-in window's on :3133 (the recipes' hosts)."""

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
    provisioner = Proxy(
        guard,
        buckets,
        mode="provisioner",
        clients=s.provisioner_proxy_clients,
        allowed_hosts=s.provisioner_hosts,
    )
    substitutes = Proxy(
        guard,
        buckets,
        mode="substitutes",
        clients=s.substitutes_proxy_clients,
        allowed_hosts=s.substitutes_hosts,
    )
    web = Proxy(guard, buckets, mode="profile", clients=s.web_proxy_clients)
    login = Proxy(
        guard,
        buckets,
        mode="login",
        clients=s.login_proxy_clients,
        allowed_hosts=frozenset().union(*(r.sign_in_hosts() for r in state.recipes.values())),
    )
    servers = [
        await browser.serve("0.0.0.0", s.browser_proxy_port),
        await gateway.serve("0.0.0.0", s.gateway_proxy_port),
        await provisioner.serve("0.0.0.0", s.provisioner_proxy_port),
        await substitutes.serve("0.0.0.0", s.substitutes_proxy_port),
        await web.serve("0.0.0.0", s.web_proxy_port),
        await login.serve("0.0.0.0", s.login_proxy_port),
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
