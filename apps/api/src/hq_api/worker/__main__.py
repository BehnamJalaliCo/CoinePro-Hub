"""`python -m hq_api.worker`: the Temporal worker of the holding core.

Connects as the database role hq_worker, to NATS (live stream + bridge),
to Temporal (task queue `hq-core`) and to OpenBao for the push channels'
credentials (missing credentials only switch the channels off). Ensures
the schedules on start, then runs the worker, the bridge and a file
heartbeat until SIGTERM.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from hq_api import secrets as secret_store
from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database
from hq_api.events import Bus
from hq_api.hub import Hub
from hq_api.policy import Policy
from hq_api.secrets import Secrets
from hq_api.storage import LocalStorage
from hq_api.worker.activities import Activities
from hq_api.worker.bridge import Bridge
from hq_api.worker.workflows import WORKFLOWS
from hq_common import heartbeat, logs
from hq_common.openbao import OpenBaoClient, OpenBaoError

log = logging.getLogger("hq_api.worker")
SECRETS_REFRESH_S = 300


async def load_secrets(bao: OpenBaoClient | None) -> Secrets:
    if bao is None:
        return Secrets()
    try:
        return await secret_store.load(bao, api_config=False)
    except OpenBaoError:
        log.warning("openbao unavailable; push channels stay off until the next refresh")
        return Secrets()


async def refresh_secrets(hub: Hub, bao: OpenBaoClient | None) -> None:
    """Pick up channel credentials added later; keep the current ones while
    OpenBao is unreachable."""
    if bao is None:
        # Nothing to refresh; never end (main stops when any task ends).
        await asyncio.Event().wait()
        return
    while True:
        await asyncio.sleep(SECRETS_REFRESH_S)
        try:
            hub.secrets = await secret_store.load(bao, api_config=False)
        except OpenBaoError:
            continue
        hub.channels = None  # rebuilt lazily with the new credentials


def health(hub: Hub, client: Client) -> Any:
    async def check() -> dict[str, Any]:
        db_ok = await hub.db.ping()
        bus_ok = hub.bus is not None and hub.bus.connected
        temporal_ok = await client.service_client.check_health()
        return {
            "ok": bool(db_ok and bus_ok and temporal_ok),
            "db": db_ok,
            "bus": bus_ok,
            "temporal": temporal_ok,
        }

    return check


async def main(stop: asyncio.Event | None = None) -> None:
    """Runs until SIGTERM/SIGINT (or until `stop` is set, for tests)."""
    s = Settings()
    logs.setup("hq-worker", s.log_level)
    db = Database.create(s, pool_size=4)
    bus = Bus(s)
    await bus.connect()
    bao = OpenBaoClient(s.openbao_addr, s.approle_file) if s.openbao_addr else None
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    hub = Hub(
        settings=s,
        db=db,
        companies=Companies(db),
        secrets=await load_secrets(bao),
        policy=Policy(s.opa_url),
        storage=LocalStorage(s.files_root),
        bus=bus,
        temporal=client,
    )
    acts = Activities(hub, client)
    try:
        result = await acts.reconcile_schedules()
        log.info(
            "schedules ensured",
            extra={"fixed": result["fixed"], "recurring": len(result["recurring"])},
        )
    except Exception:  # noqa: BLE001 - Maintenance retries every 5 minutes
        log.warning("could not ensure schedules at start")

    # A small workflow cache: the holding's workflows are short and few at a time
    # (measured RSS ~95 MiB with it); the default (1000) would grow without need.
    worker = Worker(
        client,
        task_queue=s.task_queue,
        workflows=WORKFLOWS,
        activities=acts.all(),
        max_cached_workflows=100,
    )
    if stop is None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    tasks = [
        asyncio.create_task(worker.run(), name="temporal-worker"),
        asyncio.create_task(Bridge(hub).run(), name="bridge"),
        asyncio.create_task(heartbeat.run(health(hub, client)), name="heartbeat"),
        asyncio.create_task(refresh_secrets(hub, bao), name="secrets"),
    ]
    log.info("worker running", extra={"task_queue": s.task_queue})
    stopper = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait([stopper, *tasks], return_when=asyncio.FIRST_COMPLETED)
    for t in done:
        if t is not stopper and t.exception() is not None:
            log.error("worker task failed", extra={"task": t.get_name()}, exc_info=t.exception())
    log.info("shutting down")
    await worker.shutdown()
    for t in tasks[1:]:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    if hub.channels is not None and hasattr(hub.channels, "aclose"):
        with contextlib.suppress(Exception):
            await hub.channels.aclose()
    await hub.policy.aclose()
    if bao is not None:
        await bao.aclose()
    await bus.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
