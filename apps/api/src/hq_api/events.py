"""Events (contract §7, §13): `hq.core.<company>.<type>` on JetStream stream
HQ_CORE (30 days). Metadata only: never a message body, prompt or secret.

Writers call `emit()` inside their transaction (transactional outbox, so a
committed change is never without its event and a rolled-back one never
has one). `OutboxRelay` publishes pending rows with Nats-Msg-Id = event id
(JetStream de-duplicates retries) and marks them published.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import nats
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

from hq_api.config import Settings
from hq_api.db import Database, Tx

log = logging.getLogger("hq_api.events")

STREAM = "HQ_CORE"
SUBJECTS = "hq.core.>"
RETENTION_S = 30 * 24 * 3600

# SSE topic -> event type prefixes (contract §7)
TOPICS: dict[str, tuple[str, ...]] = {
    "work": ("work.",),
    "decisions": ("decision.",),
    "deliverables": ("deliverable.",),
    "messages": ("message.",),
    "notifications": ("notification.",),
    "activity": ("activity.", "employee."),
    "llm": ("llm.", "budget."),
    "control": ("control.", "presence.", "hiring."),
    # ⟨1.4.1⟩ the agent runs: run.started, run.step, run.finished
    "runs": ("run.",),
}


def subject(company_code: str, type_: str) -> str:
    return f"hq.core.{company_code}.{type_}"


def envelope(
    company_code: str, type_: str, ref: str | None, data: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": type_,
        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "company": company_code,
        "ref": ref,
        "data": data,
    }


async def emit(
    tx: Tx,
    company_code: str,
    type_: str,
    ref: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    env = envelope(company_code, type_, ref, data or {})
    await tx.exec(
        """INSERT INTO core.outbox (event_id, subject, payload)
           VALUES (:id, :subject, CAST(:payload AS jsonb))""",
        id=env["id"],
        subject=subject(company_code, type_),
        payload=json.dumps(env, default=str),
    )


class Bus:
    """NATS + JetStream connection shared by the relay, the SSE bridge and the worker."""

    def __init__(self, s: Settings) -> None:
        self._s = s
        self.nc: Any = None
        self.js: Any = None

    @property
    def connected(self) -> bool:
        return bool(self.nc is not None and self.nc.is_connected)

    async def connect(self) -> None:
        self.nc = await nats.connect(
            self._s.nats_url,
            user=self._s.nats_user,
            password=self._s.nats_password,
            name="hq-api",
            max_reconnect_attempts=-1,
        )
        self.js = self.nc.jetstream()
        cfg = StreamConfig(
            name=STREAM,
            subjects=[SUBJECTS],
            retention=RetentionPolicy.LIMITS,
            storage=StorageType.FILE,
            max_age=RETENTION_S,
            duplicate_window=120,
        )
        try:
            await self.js.add_stream(cfg)
        except Exception:  # noqa: BLE001 - exists already: make it match
            await self.js.update_stream(cfg)

    async def close(self) -> None:
        if self.nc is not None:
            with contextlib.suppress(Exception):
                await self.nc.drain()

    async def publish(
        self, subject_: str, payload: dict[str, Any], msg_id: str | None = None
    ) -> int:
        headers = {"Nats-Msg-Id": msg_id} if msg_id else None
        ack = await self.js.publish(
            subject_, json.dumps(payload, default=str).encode(), headers=headers
        )
        return int(ack.seq)


class OutboxRelay:
    """Publishes core.outbox rows in order; woken by NOTIFY hq_outbox."""

    def __init__(self, s: Settings, db: Database, bus: Bus) -> None:
        self._s = s
        self._db = db
        self._bus = bus
        self._wake = asyncio.Event()

    async def drain_once(self, limit: int = 200) -> int:
        if not self._bus.connected:
            return 0
        sent = 0
        async with self._db.raw() as tx:
            rows = await tx.all(
                """SELECT id, event_id, subject, payload FROM core.outbox
                   WHERE published_at IS NULL ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED""",
                limit=limit,
            )
            done: list[int] = []
            for r in rows:
                try:
                    await self._bus.publish(r["subject"], r["payload"], msg_id=str(r["event_id"]))
                except Exception:  # noqa: BLE001 - NATS down: retry later, keep order
                    log.warning("outbox publish failed; will retry")
                    break
                done.append(r["id"])
            if done:
                await tx.exec(
                    "UPDATE core.outbox SET published_at = now() WHERE id = ANY(:ids)", ids=done
                )
                sent = len(done)
        return sent

    async def _listen(self) -> None:
        while True:
            conn = None
            try:
                conn = await asyncpg.connect(
                    host=self._s.db_host,
                    port=self._s.db_port,
                    database=self._s.db_name,
                    user=self._s.db_user,
                    password=self._s.db_password,
                )
                closed = asyncio.Event()
                conn.add_termination_listener(lambda *_, ev=closed: ev.set())
                await conn.add_listener("hq_outbox", lambda *_: self._wake.set())
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
                    while await self.drain_once() > 0:
                        pass
                except Exception:  # noqa: BLE001 - keep relaying
                    log.warning("outbox relay pass failed")
                self._wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
        finally:
            listener.cancel()
