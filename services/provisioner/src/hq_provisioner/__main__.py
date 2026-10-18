"""`python -m hq_provisioner`: the API on :8110 (hq-prov, the api only) and the
run loop (a thread: it asks the api for the next sealed plan every
PROVISIONER_POLL_S seconds, or at once after POST /v1/wake)."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import uvicorn

from hq_common import heartbeat, logs
from hq_provisioner.app import build_app
from hq_provisioner.config import Settings
from hq_provisioner.hub import Hub, HubError
from hq_provisioner.runner import Runner
from hq_provisioner.vault import NotConfigured, Vault

log = logging.getLogger("hq_provisioner")
API_TOKEN_TTL_S = 600.0


class TokenCache:
    """The provisioner's own api token (not the Hetzner one), re-read from
    OpenBao every 10 minutes."""

    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.value = ""
        self.at = 0.0
        self.lock = threading.Lock()

    def __call__(self) -> str:
        with self.lock:
            if not self.value or time.monotonic() - self.at > API_TOKEN_TTL_S:
                self.value = self.vault.api_token()
                self.at = time.monotonic()
            return self.value


def loop(runner: Runner, wake: threading.Event, beat: dict[str, float], poll_s: float) -> None:
    while True:
        beat["loop"] = time.monotonic()
        try:
            while runner.tick():
                beat["loop"] = time.monotonic()
        except (HubError, NotConfigured) as exc:
            log.warning("provisioner: %s", type(exc).__name__, extra={"detail": str(exc)[:200]})
        except Exception:
            log.exception("provisioner: loop error")
        wake.wait(poll_s)
        wake.clear()


async def serve(s: Settings) -> None:
    vault = Vault(s.openbao_addr, s.approle_file)
    hub = Hub(s.hub_url, TokenCache(vault))
    runner = Runner(s, vault, hub)
    wake = threading.Event()
    beat = {"loop": time.monotonic()}
    threading.Thread(target=loop, args=(runner, wake, beat, s.poll_s), daemon=True).start()
    api = uvicorn.Server(
        uvicorn.Config(
            build_app(s, vault, wake),
            host="0.0.0.0",
            port=s.port,
            log_config=None,
            access_log=False,
            proxy_headers=False,
            server_header=False,
        )
    )

    async def check() -> dict[str, Any]:
        # A run's long waits (boot, the callback) keep the loop busy for up to
        # an hour: the loop counts as alive while it is inside one.
        fresh = time.monotonic() - beat["loop"] < max(4 * s.poll_s, s.callback_wait_s + 300)
        return {"ok": api.started and fresh}

    await asyncio.gather(api.serve(), heartbeat.run(check))


def main() -> None:
    s = Settings()
    logs.setup("provisioner", s.log_level)
    asyncio.run(serve(s))


if __name__ == "__main__":
    main()
