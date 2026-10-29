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
    # ⟨1.3⟩ owner media: file.ready, file.failed
    "files": ("file.",),
    # ⟨1.3⟩ the Code Workshop (workshop.session, workshop.approval) and voice orders
    "workshop": ("workshop.",),
    "orders": ("order.",),
    # ⟨1.4⟩ the hourly backup: backup.done, backup.failed (contract §18.10)
    "backups": ("backup.",),
    # ⟨1.4⟩ formal inquiries (inquiry.answered, inquiry.late) and the assistant's
    # errands (errand.updated), contract §18.10
    "inquiries": ("inquiry.",),
    "errands": ("errand.",),
    # ⟨1.4⟩ prompt 08: stars.rollup (stars), story.created (stories), contract §18.10
    "stars": ("stars.", "rankings."),  # ⟨1.5⟩ rankings.updated (prompt 12 §5)
    "stories": ("story.",),
    # ⟨1.4⟩ the skill library and the academy (contract §18.10): skill.updated;
    # academy.eval (and academy.teaching)
    "skills": ("skill.",),
    "academy": ("academy.",),
    # ⟨1.4⟩ the Chief Overseer: oversight.finding, oversight.hold, oversight.watch
    "oversight": ("oversight.",),
    # ⟨1.4⟩ prompt 09: founding.updated, provision.step (contract §18.10)
    "founding": ("founding.", "provision."),
    # ⟨1.5⟩ prompt 10 (contract §19.9): revenue.day, revenue.alert; support.message,
    # support.queue, support.channel; rescue.updated, lifecycle.sent, nps.closed;
    # feedback.item
    "revenue": ("revenue.",),
    "support": ("support.",),
    "growth": ("rescue.", "lifecycle.", "nps."),
    "feedback": ("feedback.",),
    # ⟨1.4.6⟩ prompt 9.1: brand.updated (contract §18.14)
    "companies": ("brand.",),
    # ⟨1.5⟩ prompt 11 (contract §20.11): meeting.scheduled, .started, .turn, .claim,
    # .whisper (metadata only; the text is the owner's to read), .ended; the
    # governance topic; knowledge.updated, knowledge.expiring
    "meetings": ("meeting.",),
    "governance": ("charter.", "kpi.", "okr.", "outcome.", "risk.", "calendar."),
    "knowledge": ("knowledge.",),
    # ⟨1.5⟩ prompt 12 part A (contract §21.12): memo.ready, advisor.proactive;
    # substitute.updated; creative.updated
    "advisor": ("memo.", "advisor."),
    "treasury": ("substitute.",),
    "creatives": ("creative.",),
    # ⟨1.5⟩ prompt 12 part B (contract §21.12): briefing.ready, hr.round,
    # note.created, claim.verdict (decision.reminded is on `decisions`)
    "briefings": ("briefing.",),
    "people": ("hr.", "role."),  # ⟨1.6⟩ role.updated (contract §22.5)
    "notes": ("note.",),
    "quality": ("claim.",),
    # ⟨1.5⟩ prompt 12 §2, §3, §13 (contract §21.12): ask.answered, review.updated,
    # dceo.scored (after the owner's decision only)
    "ask": ("ask.",),
    "reviews": ("review.",),
    "dceo": ("dceo.",),
    # ⟨1.6⟩ prompt 13 (contract §22.6): media.item (and media.series)
    "media": ("media.",),
    # ⟨1.6⟩ prompt 13 (contract §22.6): legal.case
    "legal": ("legal.",),
    # ⟨1.7⟩ prompt 14 (contract §23.11): record.filed, record.updated,
    # record.sealed, reminder.due, hold.changed, fixity.failed, schema.changed
    "archive": ("record.", "reminder.", "hold.", "fixity.", "schema."),
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


async def _root(tx: Tx, type_: str, ref: str | None, data: dict[str, Any]) -> dict[str, Any] | None:
    """⟨1.7.4⟩ The owner's order a work belongs to (its root): for `work.*` the
    work is `ref`, for `deliverable.created` it is the deliverable's work."""
    if type_.startswith("work.") and ref:
        return await tx.first(
            """SELECT w.root_id, r.ref AS root_ref FROM work.work w
               LEFT JOIN work.work r ON r.id = w.root_id WHERE w.ref = :ref""",
            ref=ref,
        )
    if type_ == "deliverable.created" and ref:
        return await tx.first(
            """SELECT w.root_id, r.ref AS root_ref FROM cartable.deliverables dl
               JOIN work.work w ON w.id = dl.work_id LEFT JOIN work.work r ON r.id = w.root_id
               WHERE dl.ref = :ref""",
            ref=ref,
        )
    return None


async def emit(
    tx: Tx,
    company_code: str,
    type_: str,
    ref: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    data = dict(data or {})
    # ⟨1.7.4⟩ prompt 15.1: every work.* and deliverable.created event names the
    # owner's order it belongs to, so the app can tell which order moved.
    if (type_.startswith("work.") or type_ == "deliverable.created") and "root_id" not in data:
        root = await _root(tx, type_, ref, data)
        if root is not None and root.get("root_id") is not None:
            data["root_id"] = str(root["root_id"])
            data["root_ref"] = root.get("root_ref")
    env = envelope(company_code, type_, ref, data)
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
