"""From the run registry to Temporal (prompt 05 §2): every queued run gets
exactly one AgentRun workflow (id agent-run-<run id>).

Runs are queued by database triggers (work reaching an agent, a child's
deliverable, the owner writing in an agent's thread) and by the schedules.
The dispatcher wakes on NOTIFY hq_runs and polls every few seconds. There is
no process per role: a role costs nothing until a run is queued for it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import asyncpg
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from hq_api.hub import Hub

log = logging.getLogger("hq_api.agents.dispatch")
PRIORITY_ORDER = "array_position(ARRAY['P0','P1','P2','P3','P4'], priority)"


def workflow_id(run_id: Any) -> str:
    return f"agent-run-{run_id}"


class Dispatcher:
    def __init__(self, hub: Hub, client: Client, task_queue: str, interval_s: float = 3.0) -> None:
        self.hub = hub
        self.client = client
        self.task_queue = task_queue
        self.interval_s = interval_s
        self._wake = asyncio.Event()

    async def once(self, limit: int = 50) -> int:
        started = 0
        async with self.hub.db.tx(await self.hub.companies.ids()) as tx:
            rows = await tx.all(
                f"""SELECT id FROM agents.runs WHERE state = 'queued' AND dispatched_at IS NULL
                    ORDER BY {PRIORITY_ORDER}, queued_at LIMIT :lim FOR UPDATE SKIP LOCKED""",  # noqa: S608 - constant
                lim=limit,
            )
            for r in rows:
                try:
                    await self.client.start_workflow(
                        "AgentRun",
                        str(r["id"]),
                        id=workflow_id(r["id"]),
                        task_queue=self.task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
                    )
                    started += 1
                except WorkflowAlreadyStartedError:
                    pass
                await tx.exec(
                    "UPDATE agents.runs SET dispatched_at = now() WHERE id = :id", id=r["id"]
                )
        return started

    async def _listen(self) -> None:
        s = self.hub.settings
        while True:
            conn = None
            try:
                conn = await asyncpg.connect(
                    host=s.db_host,
                    port=s.db_port,
                    database=s.db_name,
                    user=s.db_user,
                    password=s.db_password,
                )
                closed = asyncio.Event()
                conn.add_termination_listener(lambda *_, ev=closed: ev.set())
                await conn.add_listener("hq_runs", lambda *_: self._wake.set())
                await closed.wait()
            except Exception:  # noqa: BLE001 - reconnect
                await asyncio.sleep(2)
            finally:
                if conn is not None:
                    with contextlib.suppress(Exception):
                        await conn.close()

    async def run(self) -> None:
        listener = asyncio.create_task(self._listen())
        try:
            while True:
                try:
                    await self.once()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - keep dispatching
                    log.warning("dispatch pass failed")
                self._wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=self.interval_s)
        finally:
            listener.cancel()
