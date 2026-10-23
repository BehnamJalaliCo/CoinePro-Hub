"""Temporal activities: every database or network side effect of the worker.

The worker acts for the holding: each transaction is scoped to every
company (role hq_worker, RLS still in force). Records it writes are
authored by the system principal (audit actor_kind 'system').
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError

from hq_api import audit, events, workflows_client
from hq_api.agents import checks
from hq_api.agents.clients import Gateway, LivePush, Router
from hq_api.agents.runner import Runner
from hq_api.db import Tx
from hq_api.domain import backups, inquiries, notify, oversight, recurrence, recurring, scoring
from hq_api.domain import decisions as D
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.worker import report, schedules
from hq_api.worker.academy_activities import AcademyActivities
from hq_api.worker.brand_activities import BrandActivities
from hq_api.worker.desk_activities import DeskActivities
from hq_api.worker.governance_activities import GovernanceActivities
from hq_api.worker.media_activities import MediaActivities
from hq_api.worker.meeting_activities import MeetingActivities
from hq_api.worker.mgmt_activities import MgmtActivities
from hq_api.worker.oversight_activities import OversightActivities
from hq_api.worker.people_activities import PeopleActivities
from hq_api.worker.revenue_activities import RevenueActivities
from hq_api.worker.support_activities import SupportActivities

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
        router: Router | None = None,
        gateway: Gateway | None = None,
        live: LivePush | None = None,
        checker: checks.Checker | None = None,
    ) -> None:
        self.hub = hub
        self.client = client or hub.temporal
        self.lock_poll_s = lock_poll_s
        self.escalation_gap_s = escalation_gap_s
        self.effect_max_attempts = effect_max_attempts
        s = hub.settings
        # The agent runtime's clients; their tokens are read at call time, so a
        # refresh of the secrets is picked up.
        self.router = router or Router(s.llm_router_url, lambda: self.hub.secrets.llm_router_token)
        self.gateway = gateway or Gateway(s.gateway_url, lambda: self.hub.secrets.gateway_token)
        self.live = live or LivePush(s.api_internal_url)
        self.checker = checker or checks.Checker()
        self.media = MediaActivities(hub, self.router, self._tx)
        self.brand = BrandActivities(hub, self._tx)
        self.people = PeopleActivities(hub, self._tx)
        self.academy = AcademyActivities(hub, self.router, self._tx)
        self.oversight = OversightActivities(hub, self._tx)
        self.support = SupportActivities(hub, self._tx)
        self.revenue = RevenueActivities(hub, self._tx, router=self.router)
        self.desk = DeskActivities(hub, self.router, self._tx)  # prompt 10 §4-§7, §11
        self.meetings = MeetingActivities(hub, self._tx)  # prompt 11 §1-§3
        self.governance = GovernanceActivities(hub, self._tx)  # prompt 11 §4-§10
        # prompt 12 part A: the advisor's sweep and the substitute players
        from hq_api.worker.management_activities import ManagementActivities

        self.management = ManagementActivities(hub, self._tx)
        self.mgmt = MgmtActivities(hub, self._tx)  # prompt 12 part B
        # prompt 12 §2, §3, §13: the corpus, asks, the weekly review, the digital CEO
        from hq_api.worker.owner_tools_activities import OwnerToolsActivities

        self.owner_tools = OwnerToolsActivities(hub, self._tx, router=self.router)
        from hq_api.worker.studio_activities import StudioActivities

        self.studio = StudioActivities(hub, self._tx)  # prompt 13: the media studio
        from hq_api.worker.legal_activities import LegalVoiceActivities

        self.legal_voice = LegalVoiceActivities(hub, self._tx)  # prompt 13, legal and voice

    def all(self) -> list[Any]:
        return [
            *self.meetings.all(),
            *self.studio.all(),
            *self.management.all(),
            *self.desk.all(),
            *self.mgmt.all(),
            *self.owner_tools.all(),
            *self.legal_voice.all(),
            *self.media.all(),
            *self.brand.all(),
            *self.people.all(),
            *self.academy.all(),
            *self.oversight.all(),
            *self.support.all(),
            *self.revenue.all(),
            *self.governance.all(),
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
            self.backups_ingest,
            self.inquiries_late,
            self.flush_digest,
            self.morning_report,
            self.audit_verify,
            self.score_job,
            self.run_claim,
            self.run_execute,
            self.run_finalize,
            self.requeue_runs,
            self.site_checks,
            self.hub_health,
            self.order_route,
            self.ceo_daily,
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
            if d["kind"] == "lesson_adoption":  # no answer: the lesson is open again (§18.15)
                from hq_api.domain import stars

                await stars.adoption_reopened(tx, d["payload"]["lesson"], d["company_id"], d["ref"])
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
            company_lock = await tx.scalar(
                "SELECT control.lock_state(company_id) FROM cartable.decisions WHERE ref = :r",
                r=ref,
            )
            if company_lock == "company":  # the company's own switch holds its effects too
                raise ApplicationError("the company kill switch is engaged", type=HOLDING_LOCKED)
            if await oversight.held(tx, "decision", ref):  # held for the owner: waits the same way
                raise ApplicationError("the decision is held by the overseer", type=HOLDING_LOCKED)
            if await tx.scalar(
                "SELECT kind = 'email_send' AND effect_status = 'pending' FROM cartable.decisions WHERE ref = :r",
                r=ref,
            ):
                # ⟨1.6⟩ the sealed email's one send (prompt 13 §3), in its own
                # transactions: claimed, sent, recorded; never sent twice.
                from hq_api.domain import legal

                sent = await legal.deliver(self.hub, self._tx, ref)
                if sent.get("email") == "failed":
                    raise ApplicationError(
                        f"email_not_sent: {sent.get('error')}"[:300],
                        type=EFFECT_REJECTED,
                        non_retryable=True,
                    )
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
        if result.get("changed") and result.get("item") and result.get("state") == "scheduled":
            # ⟨1.6⟩ an approved media_publish card: published now (after commit),
            # through the official APIs; the media sweep catches up otherwise.
            from hq_api.domain import studio_publish

            try:
                await studio_publish.publish_due(self.hub, only=str(result["item"]))
            except Exception:  # noqa: BLE001 - the item stays scheduled for the sweep
                log.warning("media publish after the card failed", extra={"ref": ref})
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
            if run is not None:
                await audit.record(
                    tx,
                    SYSTEM,
                    company_id=t["company_id"],
                    action="work.recurring_run",
                    action_class="A2",
                    target_kind="work",
                    target_ref=run["ref"],
                    summary=f"run of {t['ref']} at {at.isoformat()}",
                )
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
        for d in schedules.fixed(
            owner["morning_report_at"],
            owner["timezone"],
            ceo_daily=self.hub.settings.ceo_daily_reports,
            support_sweep_min=self.hub.settings.support_handoff_digest_min,
            meetings_paused=not self.hub.settings.meetings_schedules,
        ):
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
        # The overseer's protocols (prompt 08 §2): seeded from agents/, one
        # schedule each, and the weekly challenges.
        out["oversight"] = await self.oversight.reconcile(client, tq, owner["timezone"])
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
        ended = await self._end_stale_decision_workflows(hub)
        files = await self._resume_files(hub)
        brands = await self._resume_brands(hub)
        return {
            "pending": len(pending),
            "effects_resumed": len(stuck),
            "ended": ended,
            "files_resumed": files,
            "brands_resumed": brands,
        }

    async def _resume_brands(self, hub: Any) -> int:
        """Brand versions still processing whose trace never started (prompt
        9.1): started again. Rule-only (code, no model, nothing outside)."""
        async with self._tx() as tx:
            rows = await tx.all(
                """SELECT id FROM org.company_brands
                   WHERE state = 'processing' AND updated_at < now() - interval '10 minutes'
                   ORDER BY updated_at LIMIT 20"""
            )
        for r in rows:
            await workflows_client.brand_trace(hub, str(r["id"]))
        return len(rows)

    async def _resume_files(self, hub: Any) -> int:
        """Uploads still processing whose workflow never started (Temporal was
        down at upload): started again (one workflow id per file)."""
        async with self._tx() as tx:
            rows = await tx.all(
                """SELECT file_id FROM files.processing
                   WHERE status = 'processing' AND NOT (stt ? 'purpose')
                     AND updated_at < now() - interval '10 minutes' AND attempts < 3
                   ORDER BY created_at LIMIT 50"""
            )
        for r in rows:
            await workflows_client.file_uploaded(hub, str(r["file_id"]))
        return len(rows)

    async def _end_stale_decision_workflows(self, hub: Any) -> int:
        """A DecisionLifecycle still waiting for a card that is no longer pending
        (withdrawn by a migration or any path that could not signal) is woken,
        sees the card's state and ends with it (prompt 5.1 §1.3)."""
        client = self._client()
        refs: list[str] = []
        try:
            async for wf in client.list_workflows(
                f"WorkflowType = '{workflows_client.DECISION_WORKFLOW}' AND ExecutionStatus = 'Running'",
                limit=500,
            ):
                if wf.id.startswith("decision-"):
                    refs.append(wf.id.removeprefix("decision-"))
        except Exception:  # noqa: BLE001 - visibility unavailable: try at the next pass
            log.warning("could not list decision workflows")
            return 0
        if not refs:
            return 0
        async with self._tx() as tx:
            done = await tx.all(
                """SELECT ref FROM cartable.decisions WHERE ref = ANY(:refs)
                     AND status NOT IN ('pending', 'approved')""",
                refs=refs,
            )
        for r in done:
            await workflows_client.decision_decided(hub, r["ref"])
        return len(done)

    @activity.defn(name="end_expired_escrows")
    async def end_expired_escrows(self) -> dict[str, Any]:
        async with self._tx() as tx:
            rows = await tx.all(
                """SELECT e.work_id, e.company_id, w.ref FROM work.escrows e JOIN work.work w ON w.id = e.work_id
                   WHERE e.status = 'active' AND e.expires_at <= now()"""
            )
            for r in rows:
                await recurring.end(tx, r["work_id"])
                await audit.record(
                    tx,
                    SYSTEM,
                    company_id=r["company_id"],
                    action="escrow.expire",
                    action_class="A2",
                    target_kind="work",
                    target_ref=r["ref"],
                    summary="escrow expired; schedule ended",
                )
        return {"ended": len(rows)}

    @activity.defn(name="backups_ingest")
    async def backups_ingest(self) -> dict[str, Any]:
        """The host backup's status files -> backup.*, events and alerts (prompt 07 §1)."""
        return await backups.ingest(self.hub)

    @activity.defn(name="inquiries_late")
    async def inquiries_late(self) -> dict[str, Any]:
        """Formal inquiries past their due time (prompt 08 §3): late, the owner
        told once; they count against the asked company's compliance (PR-051).
        Nothing while the holding is locked: no agent can answer then."""
        async with self._tx() as tx:
            if await _holding_locked(tx):
                return {"late": 0, "skipped": "holding_locked"}
            rows = await inquiries.mark_late(tx)
        await self._push(rows)
        return {"late": len(rows)}

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
        """Once per owner-local day (a second run that day is a no-op). The
        rule-based report first; then (prompt 05 §6) a short Sonnet 5.5 pass
        rewrites it as fluent Persian - with no new number (every figure must
        come from the rule-based text, else the rewrite is dropped)."""
        now = datetime.now(UTC)
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
                {"work": w["ref"], "producer": f"{holding.code}-SYS"},
            )
            await events.emit(tx, holding.code, "work.completed", w["ref"], {"by": "system"})
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
        polished = (
            await self._polish_report(holding.code, body)
            if self.hub.settings.morning_report_llm
            else None
        )
        pushed: list[dict[str, Any]] = []
        link = dl["ref"]
        async with self._tx() as tx:
            if polished is not None:
                text, call = polished
                pdl = await tx.one(
                    """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
                           produced_with, usage)
                       VALUES (:co, :w, :p, :title, :summary, :body, CAST(:pw AS jsonb), CAST(:u AS jsonb))
                       RETURNING id, ref""",
                    co=holding.id,
                    w=w["id"],
                    p=sys_id,
                    title=title + " (متن خوش‌خوان)",
                    summary=summary,
                    body=text,
                    pw=json.dumps(
                        {
                            "model": call.model,
                            "effort": call.effort,
                            "connection": call.connection,
                            "label_fa": f"انجام‌شده با {call.model}; عددها از {dl['ref']}",
                        },
                        ensure_ascii=False,
                    ),
                    u=json.dumps(
                        {
                            "input_tokens": call.input_tokens,
                            "output_tokens": call.output_tokens,
                            "cache_read_tokens": call.cache_read_tokens,
                            "cache_write_tokens": call.cache_write_tokens,
                            "equiv_cost_usd": call.equiv_cost_usd or "0",
                        }
                    ),
                )
                link = pdl["ref"]
                await events.emit(
                    tx,
                    holding.code,
                    "deliverable.created",
                    pdl["ref"],
                    {"work": w["ref"], "producer": f"{holding.code}-SYS"},
                )
                await audit.record(
                    tx,
                    SYSTEM,
                    company_id=holding.id,
                    action="report.morning_rewrite",
                    action_class="A1",
                    target_kind="deliverable",
                    target_ref=pdl["ref"],
                    summary=f"rewritten from {dl['ref']} with {call.model}",
                )
            pushed.append(
                await notify.raise_notification(
                    tx,
                    company_id=holding.id,
                    company_code=holding.code,
                    level="report",
                    title_fa=title,
                    body_fa=summary,
                    link_kind="deliverable",
                    link_ref=link,
                )
            )
        rhythm = await notify.flush_rhythm(self.hub)
        # ⟨1.5⟩ prompt 12 §4: its voice (BR-…), same text; nothing while the holding is locked
        voiced = {"id": pdl["id"], "ref": pdl["ref"]} if polished is not None else dl
        briefing = await self.mgmt.morning_briefing(
            voiced, polished[0] if polished is not None else body
        )
        return {
            "created": True,
            "deliverable": dl["ref"],
            "rewritten": link if link != dl["ref"] else None,
            "work": w["ref"],
            "rhythm": _plain(rhythm),
            "briefing": briefing,
        }

    async def _polish_report(self, holding_code: str, body: str) -> tuple[str, Any] | None:
        if not self.hub.secrets.llm_router_token:
            return None
        call = await self.router.run(
            {
                "company_code": holding_code,
                "actor_ref": f"{holding_code}-SYS",
                "task_class": "summarize",
                "priority": 3,
                "model": "claude-sonnet-5-5",
                "effort": "medium",
                "system": report.REWRITE_SYSTEM,
                "prompt": body,
                "timeout_s": 180,
                "meta": {"purpose": "morning_report"},
            },
            180,
        )
        text = (call.text or "").strip()
        if not call.ok or not text or len(text) > 3 * len(body) + 500:
            log.info("morning report kept rule-based", extra={"status": call.status})
            return None
        if not report.same_numbers(body, text):
            log.warning("morning report rewrite dropped: it introduced a number")
            return None
        return text, call

    @activity.defn(name="audit_verify")
    async def audit_verify(self) -> dict[str, Any]:
        pushed: list[dict[str, Any]] = []
        anchor_file = self.hub.settings.audit_anchor_file or None
        async with self._tx() as tx:
            r = await audit.verify(tx, anchor_file=anchor_file)
            if r["ok"] and anchor_file:
                # Anchor the verified head outside Postgres (append-only file in the backup set).
                await audit.write_anchor(tx, anchor_file)
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
            "anchor": r["anchor"],
        }

    @activity.defn(name="score_job")
    async def score_job(self) -> dict[str, Any]:
        async with self._tx() as tx:
            n = await scoring.recompute_all(tx)
        return {"employees": n}

    # ------------------------------------------------------ agent runs --
    def _runner(self, *, heartbeat: bool = False) -> Runner:
        return Runner(
            self.hub,
            self.router,
            self.gateway,
            self.live,
            heartbeat=activity.heartbeat if heartbeat else None,
        )

    @activity.defn(name="run_claim")
    async def run_claim(self, run_id: str) -> dict[str, Any]:
        c = await self._runner().claim(run_id)
        return {"state": c.state, "final": c.final, "code": c.code}

    @activity.defn(name="run_execute")
    async def run_execute(self, run_id: str) -> dict[str, Any]:
        """Every step of one run, in this one activity (heartbeats in between)."""
        if not self.hub.secrets.runtime_ready:
            return await self._runner().finish(run_id, "failed", "runtime_not_configured")
        return await self._runner(heartbeat=True).execute(run_id)

    @activity.defn(name="run_finalize")
    async def run_finalize(self, run_id: str, state: str, code: str) -> dict[str, Any]:
        return await self._runner().finish(run_id, state, code)

    @activity.defn(name="requeue_runs")
    async def requeue_runs(self) -> dict[str, Any]:
        """Runs refused while a kill switch was engaged come back once it is
        released (the cause - open work, an unanswered message - still there);
        queued runs whose workflow never started are dispatched again."""
        requeued = 0
        async with self._tx() as tx:
            rows = await tx.all(
                """SELECT DISTINCT ON (r.employee_id, r.work_id, r.thread_id)
                          r.employee_id, r.work_id, r.thread_id, r.trigger, r.priority, r.state, r.error_code,
                          r.company_id, r.reason
                   FROM agents.runs r WHERE r.queued_at > now() - interval '24 hours'
                   ORDER BY r.employee_id, r.work_id, r.thread_id, r.queued_at DESC"""
            )
            for r in rows:
                if r["state"] != "refused" or r["error_code"] != "locked":
                    continue
                # still a kill switch or a deploy freeze: stays refused (prompt 5.1 §2.6)
                if (
                    await tx.scalar("SELECT control.lock_state(:co)", co=r["company_id"])
                    is not None
                ):
                    continue
                if r["work_id"] is not None and not await tx.scalar(
                    "SELECT 1 FROM work.work WHERE id = :w AND status IN ('queued', 'in_progress', 'waiting')",
                    w=r["work_id"],
                ):
                    continue
                if r["thread_id"] is not None and await tx.scalar(
                    """SELECT author_kind <> 'owner' FROM msg.messages WHERE thread_id = :t
                       ORDER BY seq DESC LIMIT 1""",
                    t=r["thread_id"],
                ):
                    continue  # answered meanwhile
                if await tx.scalar(
                    "SELECT agents.queue_run(:e, :tr, :w, :t, :reason, :p)",
                    e=r["employee_id"],
                    tr=r["trigger"],
                    w=r["work_id"],
                    t=r["thread_id"],
                    reason="requeue:" + (r["reason"] or "")[:180],
                    p=r["priority"],
                ):
                    requeued += 1
            stuck = await tx.exec(
                """UPDATE agents.runs SET dispatched_at = NULL
                   WHERE state = 'queued' AND dispatched_at < now() - interval '10 minutes'"""
            )
        return {"requeued": requeued, "redispatched": stuck}

    @activity.defn(name="site_checks")
    async def site_checks(self) -> dict[str, Any]:
        result = await checks.run_round(self.hub, self.checker)
        result["partitions_dropped"] = await checks.purge_old_checks(self.hub)
        return result

    @activity.defn(name="hub_health")
    async def hub_health(self) -> dict[str, Any]:
        data = await checks.hub_snapshot(self.hub)
        return {"services_up": data.get("services_up"), "keys": sorted(data)}

    @activity.defn(name="ceo_daily")
    async def ceo_daily(self) -> dict[str, Any]:
        """A short daily-report run for every company's CEO (off unless switched on)."""
        if not self.hub.settings.ceo_daily_reports:
            return {"queued": 0, "off": True}
        async with self._tx() as tx:
            ceos = await tx.all(
                """SELECT e.id FROM core.employees e JOIN core.companies c ON c.id = e.company_id
                   WHERE e.kind = 'ceo' AND e.status = 'active' AND c.status = 'active' AND c.kind = 'company'"""
            )
            queued = 0
            for c in ceos:
                queued += bool(
                    await tx.scalar(
                        "SELECT agents.queue_run(:e, 'schedule', NULL, NULL, 'daily_report', NULL)",
                        e=c["id"],
                    )
                )
        return {"queued": queued}

    # ---------------------------------------------------------- orders --
    @activity.defn(name="order_route")
    async def order_route(self, req: dict[str, Any]) -> dict[str, Any]:
        """The light model's routes for one owner order (prompt 06 §5). The
        request is built (and its text masked) by the api, which also checks
        the answer against the directory; nothing is trusted here."""
        if not self.hub.secrets.llm_router_token:
            return {"routes": None, "status": "no_router"}
        call = await self.router.run(req, int(req.get("timeout_s", 40)))
        if not call.ok:
            return {"routes": None, "status": call.status}
        out = call.structured
        if out is None and call.text:
            try:
                out = json.loads(call.text)
            except ValueError:
                out = None
        return {
            "routes": out.get("routes") if isinstance(out, dict) else None,
            "status": "ok",
            "model": call.model,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
        }

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
