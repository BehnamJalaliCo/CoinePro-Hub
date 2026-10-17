"""Temporal activities: every database or network side effect of the worker.

The worker acts for the holding: each transaction is scoped to every
company (role hq_worker, RLS still in force). Records it writes are
authored by the system principal (audit actor_kind 'system').
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError

from hq_api import audit, events, workflows_client
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import notify, recurrence, recurring, scoring
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.worker import report, schedules

log = logging.getLogger("hq_api.worker")
SYSTEM = audit.SYSTEM
HOLDING_LOCKED = "HoldingLocked"
EFFECT_REJECTED = "EffectRejected"


class Activities:
    def __init__(
        self,
        hub: Hub,
        client: Client | None = None,
        *,
        lock_poll_s: float = 60.0,
        escalation_gap_s: float = 3600.0,
        effect_max_attempts: int = 5,
    ) -> None:
        self.hub = hub
        self.client = client or hub.temporal
        self.lock_poll_s = lock_poll_s
        self.escalation_gap_s = escalation_gap_s
        self.effect_max_attempts = effect_max_attempts

    def all(self) -> list[Any]:
        return [
            self.decision_state,
            self.decision_expire,
            self.holding_locked,
            self.decision_apply_effect,
            self.decision_effect_failed,
            self.recurring_run,
            self.escalate_overdue,
            self.reconcile_schedules,
            self.reconcile_decisions,
            self.end_expired_escrows,
            self.purge,
            self.flush_digest,
            self.morning_report,
            self.audit_verify,
            self.score_job,
        ]

    def _tx(self) -> Any:
        return _ScopedTx(self.hub)

    async def _push(self, rows: list[dict[str, Any]]) -> None:
        ids = [r["id"] for r in rows if r.get("push_now")]
        if ids:
            await notify.deliver_pending(self.hub, ids)

    # -------------------------------------------------------- decisions --
    @activity.defn(name="decision_state")
    async def decision_state(self, ref: str) -> dict[str, Any]:
        async with self._tx() as tx:
            d = await tx.one(
                """SELECT status, effect_status, kind,
                          EXTRACT(EPOCH FROM (expires_at - now()))::float AS expires_in_s
                   FROM cartable.decisions WHERE ref = :ref""",
                ref=ref,
            )
        return dict(d)

    @activity.defn(name="decision_expire")
    async def decision_expire(self, ref: str) -> dict[str, Any]:
        async with self._tx() as tx:
            d = await D.load(tx, ref, lock=True)
            if d["status"] != "pending":
                return {"expired": False, "status": d["status"]}
            await tx.exec(
                "UPDATE cartable.decisions SET status = 'expired', decided_at = now() WHERE id = :id",
                id=d["id"],
            )
            await D.post_system_message(
                tx, d["thread_code"], f"تصمیم {ref} بدون پاسخ منقضی شد", {"decision": ref}
            )
            await events.emit(
                tx, d["company"], "decision.decided", ref, {"status": "expired", "kind": d["kind"]}
            )
            await audit.record(
                tx,
                SYSTEM,
                company_id=d["company_id"],
                action="decision.expire",
                action_class="A1",
                target_kind="decision",
                target_ref=ref,
                summary="expired without an answer",
            )
        return {"expired": True, "status": "expired"}

    @activity.defn(name="holding_locked")
    async def holding_locked(self) -> dict[str, Any]:
        async with self._tx() as tx:
            locked = await _holding_locked(tx)
        return {"locked": locked, "retry_in_s": self.lock_poll_s}

    @activity.defn(name="decision_apply_effect")
    async def decision_apply_effect(self, ref: str) -> dict[str, Any]:
        """Applies an approved decision's effect (idempotent). While the
        holding's kill switch is engaged the effect waits (HoldingLocked)."""
        async with self._tx() as tx:
            if await _holding_locked(tx):
                raise ApplicationError("the holding kill switch is engaged", type=HOLDING_LOCKED)
            try:
                result = await D.apply_effect(tx, ref, SYSTEM)
            except ApiError as exc:
                raise ApplicationError(
                    f"{exc.code}: {exc.detail or ''}"[:300],
                    type=EFFECT_REJECTED,
                    non_retryable=True,
                ) from exc
            if result.get("changed"):
                d = await D.load(tx, ref)
                await audit.record(
                    tx,
                    SYSTEM,
                    company_id=d["company_id"],
                    action="decision.effect",
                    action_class="A2",
                    target_kind="decision",
                    target_ref=ref,
                    summary=", ".join(
                        f"{k}={v}" for k, v in result.items() if k not in ("ref", "changed")
                    )[:500],
                )
        return {k: (str(v) if isinstance(v, UUID) else v) for k, v in result.items()}

    @activity.defn(name="decision_effect_failed")
    async def decision_effect_failed(self, ref: str, error: str) -> None:
        async with self._tx() as tx:
            await D.mark_effect_failed(tx, ref, error)
            d = await D.load(tx, ref)
            row = await notify.raise_notification(
                tx,
                company_id=d["company_id"],
                company_code=d["company"],
                level="urgent",
                title_fa=f"اجرای تصمیم {ref} شکست خورد",
                body_fa=error[:500],
                link_kind="decision",
                link_ref=ref,
            )
            await audit.record(
                tx,
                SYSTEM,
                company_id=d["company_id"],
                action="decision.effect_failed",
                action_class="A2",
                target_kind="decision",
                target_ref=ref,
                summary=error[:200],
            )
        await self._push([row])

    # -------------------------------------------------------- recurring --
    @activity.defn(name="recurring_run")
    async def recurring_run(self, work_id: str, occurrence: str) -> dict[str, Any]:
        """One occurrence of a recurring work -> a run work item (idempotent);
        skipped while the company or the holding is locked."""
        at = datetime.fromisoformat(occurrence)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        async with self._tx() as tx:
            t = await tx.first(
                "SELECT id, ref, company_id FROM work.work WHERE id = :id", id=work_id
            )
            if t is None:
                return {"created": False, "reason": "unknown work"}
            lock = await tx.scalar("SELECT control.lock_state(:co)", co=t["company_id"])
            if lock is not None:
                await tx.exec(
                    """INSERT INTO work.work_events (work_id, company_id, kind, actor_kind, actor_code, data)
                       VALUES (:w, :co, 'run_skipped', 'service', 'system', CAST(:data AS jsonb))""",
                    w=t["id"],
                    co=t["company_id"],
                    data='{"reason": "'
                    + str(lock)
                    + '", "occurrence_at": "'
                    + at.isoformat()
                    + '"}',
                )
                return {"created": False, "reason": f"locked: {lock}"}
            run = await recurring.create_run(tx, t["id"], at, SYSTEM)
        if run is None:
            return {"created": False, "reason": "exists or not active"}
        return {"created": True, "ref": run["ref"]}

    # ------------------------------------------------------- escalation --
    @activity.defn(name="escalate_overdue")
    async def escalate_overdue(self) -> dict[str, Any]:
        """Overdue work climbs one level at a time (§1.9 #5): 1 the manager,
        2 the CEO, 3 the owner (a 🟡 notification)."""
        escalated: list[str] = []
        rows_to_push: list[dict[str, Any]] = []
        async with self._tx() as tx:
            rows = await tx.all(
                """SELECT w.id, w.ref, w.title, w.company_id, c.code AS company, w.escalation_level,
                          w.department_id, a.id AS a_id, a.code AS a_code, a.kind AS a_kind,
                          r.code AS rt_code
                   FROM work.work w
                   JOIN core.companies c ON c.id = w.company_id
                   LEFT JOIN core.employees a ON a.id = w.assignee_id
                   LEFT JOIN core.employees r ON r.id = a.reports_to
                   WHERE w.due_at < now() AND w.status IN ('queued', 'in_progress', 'waiting')
                     AND w.escalation_level < 3
                     AND (w.escalated_at IS NULL OR w.escalated_at < now() - make_interval(secs => :gap))
                   ORDER BY w.due_at LIMIT 200
                   FOR UPDATE OF w SKIP LOCKED""",
                gap=self.escalation_gap_s,
            )
            for w in rows:
                level = w["escalation_level"] + 1
                target = None
                if level == 1:
                    target = w["rt_code"]
                    if target is None and w["department_id"] is not None:
                        target = await tx.scalar(
                            """SELECT code FROM core.employees WHERE department_id = :d
                               AND kind IN ('manager', 'inspector') AND status <> 'dismissed'""",
                            d=w["department_id"],
                        )
                elif level == 2:
                    target = await tx.scalar(
                        """SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo'
                           AND status <> 'dismissed'""",
                        co=w["company_id"],
                    )
                text = f"کار {w['ref']} از مهلتش گذشته است (پله‌ی {level} پیگیری)"
                if level < 3:
                    await D.post_system_message(tx, target, text, {"work": w["ref"]})
                else:
                    rows_to_push.append(
                        await notify.raise_notification(
                            tx,
                            company_id=w["company_id"],
                            company_code=w["company"],
                            level="decision",
                            title_fa=f"کار عقب‌افتاده {w['ref']}: {w['title'][:120]}",
                            body_fa=f"مسئول: {w['a_code'] or '—'}",
                            link_kind="work",
                            link_ref=w["ref"],
                        )
                    )
                    target = "owner"
                await tx.exec(
                    "UPDATE work.work SET escalation_level = :l, escalated_at = now() WHERE id = :id",
                    id=w["id"],
                    l=level,
                )
                await W.event(
                    tx,
                    {"id": w["id"], "company_id": w["company_id"]},
                    "escalated",
                    SYSTEM,
                    {"level": level, "to": target},
                )
                await events.emit(
                    tx, w["company"], "work.updated", w["ref"], {"escalation_level": level}
                )
                await audit.record(
                    tx,
                    SYSTEM,
                    company_id=w["company_id"],
                    action="work.escalate",
                    action_class="A1",
                    target_kind="work",
                    target_ref=w["ref"],
                    summary=f"level {level} -> {target or 'nobody'}",
                )
                escalated.append(f"{w['ref']}:{level}")
        await self._push(rows_to_push)
        return {"escalated": escalated}

    # ---------------------------------------------------- reconciliation --
    @activity.defn(name="reconcile_schedules")
    async def reconcile_schedules(self) -> dict[str, Any]:
        client = self._client()
        tq = self.hub.settings.task_queue
        async with self._tx() as tx:
            owner = await tx.one(
                "SELECT timezone, morning_report_at FROM owner.settings WHERE id = 1"
            )
            rows = await tx.all(
                """SELECT w.id, w.ref, w.company_id, w.status AS work_status, s.rrule, s.timezone,
                          s.status, s.temporal_schedule_id, e.status AS escrow_status, e.expires_at,
                          control.lock_state(w.company_id) AS lock
                   FROM work.schedules s JOIN work.work w ON w.id = s.work_id
                   JOIN work.escrows e ON e.work_id = w.id"""
            )
        out: dict[str, Any] = {"fixed": {}, "recurring": {}, "deleted": []}
        for d in schedules.fixed(owner["morning_report_at"], owner["timezone"]):
            out["fixed"][d.id] = await schedules.upsert(client, d, tq)
        wanted: set[str] = set()
        now = datetime.now(UTC)
        for r in rows:
            sid = f"{schedules.RECURRING_PREFIX}{r['ref']}"
            active = (
                r["status"] in ("active", "paused")
                and r["escrow_status"] == "active"
                and r["expires_at"] > now
                and r["work_status"] not in ("cancelled", "failed", "done")
            )
            if not active:
                if r["temporal_schedule_id"] and await schedules.delete(
                    client, r["temporal_schedule_id"]
                ):
                    out["deleted"].append(r["temporal_schedule_id"])
                if r["temporal_schedule_id"]:
                    async with self._tx() as tx:
                        await tx.exec(
                            "UPDATE work.schedules SET temporal_schedule_id = NULL WHERE work_id = :w",
                            w=r["id"],
                        )
                continue
            rule = recurrence.parse(r["rrule"])
            spec = schedules.recurring_spec(rule, r["timezone"], r["expires_at"])
            paused = r["lock"] is not None or r["status"] == "paused"
            desired = schedules.recurring(r["ref"], str(r["id"]), spec, paused)
            out["recurring"][sid] = await schedules.upsert(client, desired, tq)
            wanted.add(sid)
            if r["temporal_schedule_id"] != sid:
                async with self._tx() as tx:
                    await tx.exec(
                        "UPDATE work.schedules SET temporal_schedule_id = :s WHERE work_id = :w",
                        s=sid,
                        w=r["id"],
                    )
        for orphan in await schedules.existing_recurring(client) - wanted:
            if await schedules.delete(client, orphan):
                out["deleted"].append(orphan)
        return out

    @activity.defn(name="reconcile_decisions")
    async def reconcile_decisions(self) -> dict[str, Any]:
        async with self._tx() as tx:
            pending = await tx.all(
                "SELECT ref FROM cartable.decisions WHERE status = 'pending' ORDER BY created_at LIMIT 500"
            )
            stuck = await tx.all(
                """SELECT ref FROM cartable.decisions WHERE status = 'approved' AND effect_status = 'pending'
                     AND decided_at < now() - interval '2 minutes' ORDER BY decided_at LIMIT 200"""
            )
        hub = _with_client(self.hub, self._client())
        for r in pending:
            await workflows_client.decision_created(hub, r["ref"])
        for r in stuck:
            await workflows_client.decision_decided(hub, r["ref"])
        return {"pending": len(pending), "effects_resumed": len(stuck)}

    @activity.defn(name="end_expired_escrows")
    async def end_expired_escrows(self) -> dict[str, Any]:
        async with self._tx() as tx:
            rows = await tx.all(
                "SELECT work_id FROM work.escrows WHERE status = 'active' AND expires_at <= now()"
            )
            for r in rows:
                await recurring.end(tx, r["work_id"])
        return {"ended": len(rows)}

    @activity.defn(name="purge")
    async def purge(self) -> dict[str, Any]:
        """Expired single-use records only; never business data."""
        async with self._tx() as tx:
            keys = await tx.exec(
                "DELETE FROM core.idempotency_keys WHERE created_at < now() - interval '24 hours'"
            )
            challenges = await tx.exec(
                "DELETE FROM auth.challenges WHERE expires_at < now() - interval '1 day'"
            )
            step_ups = await tx.exec(
                """DELETE FROM auth.step_ups WHERE challenge_expires_at < now() - interval '1 day'
                     AND (expires_at IS NULL OR expires_at < now() - interval '1 day')"""
            )
            outbox = await tx.exec(
                "DELETE FROM core.outbox WHERE published_at < now() - interval '7 days'"
            )
        return {
            "idempotency_keys": keys,
            "challenges": challenges,
            "step_ups": step_ups,
            "outbox": outbox,
        }

    # ------------------------------------------------- reports and jobs --
    @activity.defn(name="flush_digest")
    async def flush_digest(self) -> dict[str, Any]:
        result: dict[str, Any] = _plain(await notify.flush_digest(self.hub))
        return result

    @activity.defn(name="morning_report")
    async def morning_report(self) -> dict[str, Any]:
        """Once per owner-local day (a second run that day is a no-op)."""
        now = datetime.now(UTC)
        pushed: list[dict[str, Any]] = []
        async with self._tx() as tx:
            tz = (
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            data = await report.gather(tx, now, tz)
            holding = await self.hub.companies.holding()
            if await tx.scalar(
                "SELECT 1 FROM work.work WHERE company_id = :co AND title = :t",
                co=holding.id,
                t=report.work_title(data["today"]),
            ):
                return {"created": False, "reason": "already sent today"}
            summary, body = report.render(data)
            title = report.title(data["today"])
            w = await W.create(
                tx,
                SYSTEM,
                company_id=holding.id,
                company_code=holding.code,
                title=report.work_title(data["today"]),
                brief="Rule-based morning report (no model).",
                kind="event",
                priority="P3",
                assignee_code=f"{holding.code}-SYS",
            )
            sys_id = await tx.scalar(
                "SELECT id FROM core.employees WHERE code = :c", c=f"{holding.code}-SYS"
            )
            dl = await tx.one(
                """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
                       produced_with)
                   VALUES (:co, :w, :p, :title, :summary, :body, CAST(:pw AS jsonb)) RETURNING id, ref""",
                co=holding.id,
                w=w["id"],
                p=sys_id,
                title=title,
                summary=summary,
                body=body,
                pw='{"label_fa": "قاعده‌محور، بدون مدل", "provider": "rules"}',
            )
            await W.set_status(tx, w, "done", delivered_at=now, closed_at=now)
            await W.event(tx, w, "delivered", SYSTEM, {"deliverable": dl["ref"]})
            await events.emit(
                tx,
                holding.code,
                "deliverable.created",
                dl["ref"],
                {"work": w["ref"], "producer": "HQ-SYS"},
            )
            await events.emit(tx, holding.code, "work.completed", w["ref"], {"by": "system"})
            pushed.append(
                await notify.raise_notification(
                    tx,
                    company_id=holding.id,
                    company_code=holding.code,
                    level="report",
                    title_fa=title,
                    body_fa=summary,
                    link_kind="deliverable",
                    link_ref=dl["ref"],
                )
            )
            await audit.record(
                tx,
                SYSTEM,
                company_id=holding.id,
                action="report.morning",
                action_class="A1",
                target_kind="deliverable",
                target_ref=dl["ref"],
                summary="rule-based morning report",
            )
        rhythm = await notify.flush_rhythm(self.hub)
        return {
            "created": True,
            "deliverable": dl["ref"],
            "work": w["ref"],
            "rhythm": _plain(rhythm),
        }

    @activity.defn(name="audit_verify")
    async def audit_verify(self) -> dict[str, Any]:
        pushed: list[dict[str, Any]] = []
        async with self._tx() as tx:
            r = await audit.verify(tx)
            if not r["ok"]:
                holding = await self.hub.companies.holding()
                pushed.append(
                    await notify.raise_notification(
                        tx,
                        company_id=holding.id,
                        company_code=holding.code,
                        level="urgent",
                        title_fa=f"زنجیره‌ی Audit شکسته است (از ردیف {r['first_bad_seq']})",
                        body_fa=f"{r['checked']} ردیف بررسی شد؛ نخستین ردیف نادرست: {r['first_bad_seq']}",
                        link_kind="audit",
                        link_ref=str(r["first_bad_seq"]),
                    )
                )
        await self._push(pushed)
        return {
            "ok": bool(r["ok"]),
            "checked": int(r["checked"]),
            "first_bad_seq": r["first_bad_seq"],
        }

    @activity.defn(name="score_job")
    async def score_job(self) -> dict[str, Any]:
        async with self._tx() as tx:
            n = await scoring.recompute_all(tx)
        return {"employees": n}

    # ---------------------------------------------------------- helpers --
    def _client(self) -> Client:
        if self.client is None:
            raise ApplicationError("no Temporal client", non_retryable=True)
        return self.client


class _ScopedTx:
    """`async with` a transaction scoped to every company (the worker's view)."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub
        self._cm: Any = None

    async def __aenter__(self) -> Tx:
        self._cm = self._hub.db.tx(await self._hub.companies.ids())
        tx: Tx = await self._cm.__aenter__()
        return tx

    async def __aexit__(self, *exc: Any) -> None:
        await self._cm.__aexit__(*exc)


async def _holding_locked(tx: Tx) -> bool:
    return bool(
        await tx.scalar(
            """SELECT EXISTS (SELECT 1 FROM control.kill_switches k JOIN core.companies c ON c.id = k.company_id
                              WHERE c.kind = 'holding' AND k.state = 'engaged')"""
        )
    )


class _ClientHub:
    """Duck-typed hub for workflows_client (needs .temporal and .settings)."""

    def __init__(self, hub: Hub, client: Client) -> None:
        self.temporal = client
        self.settings = hub.settings


def _with_client(hub: Hub, client: Client) -> Any:
    return hub if hub.temporal is client else _ClientHub(hub, client)


def _plain(value: Any) -> Any:
    """JSON-safe copy (UUIDs, datetimes) for activity results."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, UUID | datetime):
        return str(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    return value
