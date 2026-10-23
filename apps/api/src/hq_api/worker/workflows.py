"""Workflows (deterministic; activities are called by name, so the sandbox
imports nothing but temporalio). See activities.py for the side effects.

The holding kill switch pauses agent workflows (decision effects,
recurring runs) but never reports, digests, audit verification, scores or
escalation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy, SearchAttributeKey
from temporalio.exceptions import ActivityError, ApplicationError

from hq_api.worker.mgmt_workflows import P12B_WORKFLOWS

SCHEDULED_START = SearchAttributeKey.for_datetime("TemporalScheduledStartTime")
SHORT = timedelta(seconds=30)
LONG = timedelta(minutes=5)
RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2), maximum_interval=timedelta(minutes=1), maximum_attempts=5
)
EFFECT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
    non_retryable_error_types=["HoldingLocked", "EffectRejected"],
)


async def _act(name: str, *args: Any, limit: timedelta = SHORT, retry: RetryPolicy = RETRY) -> Any:
    return await workflow.execute_activity(
        name, args=list(args), start_to_close_timeout=limit, retry_policy=retry
    )


def _cause_type(err: ActivityError) -> str | None:
    cause = err.cause
    return cause.type if isinstance(cause, ApplicationError) else None


@workflow.defn(name="DecisionLifecycle")
class DecisionLifecycle:
    """Waits for the verdict (or the expiry), then applies an approved
    decision's effect; the effect waits while the holding is locked."""

    def __init__(self) -> None:
        self._signals = 0

    @workflow.signal(name="decided")
    def decided(self) -> None:
        self._signals += 1

    def _after(self, seen: int) -> Callable[[], bool]:
        return lambda: self._signals > seen

    @workflow.run
    async def run(self, ref: str) -> dict[str, Any]:
        while True:
            seen = self._signals
            state = await _act("decision_state", ref)
            if state["status"] != "pending":
                break
            expires_in = state.get("expires_in_s")
            if expires_in is not None and expires_in <= 0:
                timed_out = True
            else:
                timeout = timedelta(seconds=expires_in) if expires_in is not None else None
                try:
                    await workflow.wait_condition(self._after(seen), timeout=timeout)
                    timed_out = False
                except TimeoutError:
                    timed_out = True
            if timed_out:
                r = await _act("decision_expire", ref)
                if r["expired"]:
                    return {"ref": ref, "result": "expired"}
        if state["status"] != "approved" or state["effect_status"] != "pending":
            return {"ref": ref, "result": state["status"], "effect": state["effect_status"]}
        while True:
            lock = await _act("holding_locked")
            if lock["locked"]:
                await workflow.sleep(timedelta(seconds=lock["retry_in_s"]))
                continue
            try:
                result = await _act(
                    "decision_apply_effect", ref, limit=timedelta(minutes=2), retry=EFFECT_RETRY
                )
                if result.get("effect") == "cancelled":  # the owner cancelled its hold
                    return {"ref": ref, **result, "result": "cancelled"}
                return {"ref": ref, "result": "applied", **result}
            except ActivityError as err:
                if _cause_type(err) == "HoldingLocked":
                    # A company switch or a hold: wait like the holding lock,
                    # never spin (prompt 08.1 §2.4).
                    await workflow.sleep(timedelta(seconds=lock["retry_in_s"]))
                    continue
                cause = err.cause
                message = str(cause.message if isinstance(cause, ApplicationError) else err)
                await _act("decision_effect_failed", ref, message[:500])
                return {"ref": ref, "result": "effect_failed"}


@workflow.defn(name="RecurringRun")
class RecurringRun:
    """The action of a recurring work's Schedule: one run per occurrence."""

    @workflow.run
    async def run(self, work_id: str, occurrence: str | None = None) -> dict[str, Any]:
        if occurrence is None:
            at = workflow.info().typed_search_attributes.get(SCHEDULED_START) or workflow.now()
            occurrence = at.isoformat()
        result: dict[str, Any] = await _act("recurring_run", work_id, occurrence)
        return result


@workflow.defn(name="Maintenance")
class Maintenance:
    """Every 5 minutes: overdue escalation, reconciliation and purges. One
    step failing never stops the others."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name in (
            "escalate_overdue",
            "end_expired_escrows",
            "reconcile_decisions",
            "reconcile_schedules",
            "requeue_runs",
            "purge",
            "backups_ingest",
            "inquiries_late",
            "oversight_tick",
        ):
            try:
                out[name] = await _act(name, limit=LONG, retry=RetryPolicy(maximum_attempts=3))
            except ActivityError:
                out[name] = {"error": True}
        return out


@workflow.defn(name="Reconcile")
class Reconcile:
    """Started by the API after schedule-affecting changes."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("reconcile_schedules", limit=LONG)
        return result


@workflow.defn(name="NotificationDigest")
class NotificationDigest:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("flush_digest", limit=LONG)
        return result


@workflow.defn(name="MorningReport")
class MorningReport:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("morning_report", limit=LONG)
        return result


@workflow.defn(name="AuditVerify")
class AuditVerify:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("audit_verify", limit=timedelta(minutes=30))
        return result


@workflow.defn(name="StarsReminder")
class StarsReminder:
    """Friday 18:00 (owner zone): the CEOs' "this week's stars" (prompt 08 §4)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("stars_reminder", limit=timedelta(minutes=10))
        return result


@workflow.defn(name="StarsRollup")
class StarsRollup:
    """Daily 08:00 (owner zone): Saturday's weekly roll-up, the Jalali month's
    on its 1st (prompt 08 §4); idempotent per period."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("stars_rollup", limit=timedelta(minutes=30))
        return result


@workflow.defn(name="SupportRetention")
class SupportRetention:
    """Daily 04:15 (owner zone): customer texts older than SUPPORT_RETENTION_DAYS
    are removed, the rows stay (prompt 10 §1.4). Rule-only: runs while locked."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_retention", limit=timedelta(minutes=30))
        return result


# ------------------------------------------- prompt 10 §2, §3, §8 (revenue) --
# Each activity asks hq_api.domain.gate first: while the holding (or the
# company) is locked a pull is recorded `skipped` and nothing leaves the hub.
ONCE = RetryPolicy(maximum_attempts=1)  # a long pull is never run twice at once


# ------------------------------------------- prompt 12 part A (§1, §9.1) --
# The advisor's sweep is rule-only until it would wake the advisor (the
# launch gate decides); the web jobs and the daily pass ask the gate too.
ONCE_P12 = RetryPolicy(maximum_attempts=1)  # a web job is never sent twice


@workflow.defn(name="AdvisorSweep")
class AdvisorSweep:
    """Every 2 min: failed memos, automatic memos, proactive triggers."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("advisor_sweep", limit=timedelta(minutes=5))
        return result


@workflow.defn(name="SubstituteWebJobs")
class SubstituteWebJobs:
    """Every minute: the substitutes' queued web calls through egress."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act(
            "substitute_web_jobs", limit=timedelta(minutes=15), retry=ONCE_P12
        )
        return result


@workflow.defn(name="SubstituteDaily")
class SubstituteDaily:
    """Daily 09:15 Tehran: the value-ratio notice (Jalali 15th), the model lists."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("substitute_daily", limit=timedelta(minutes=5))
        return result


@workflow.defn(name="RevenuePulls")
class RevenuePulls:
    """07:00 Tehran (`scheduled`: the day before, or the first 90-day
    backfill) and 11:00 / 18:00 (`retry`: days still incomplete): the queued
    pulls, one after the other (the exchange's rate limit is one bucket)."""

    @workflow.run
    async def run(self, kind: str) -> dict[str, Any]:
        planned: dict[str, Any] = await _act("revenue_plan", kind, limit=LONG)
        results = []
        for pull_id in planned.get("queued") or []:
            results.append(
                await _act("revenue_pull", pull_id, limit=timedelta(hours=3), retry=ONCE)
            )
        return {**planned, "results": results}


@workflow.defn(name="RevenuePull")
class RevenuePull:
    """One pull the owner asked for (POST /revenue/accounts/{id}/pull)."""

    @workflow.run
    async def run(self, pull_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await _act(
            "revenue_pull", pull_id, limit=timedelta(hours=1), retry=ONCE
        )
        return result


@workflow.defn(name="RescueFollowUps")
class RescueFollowUps:
    """Hourly: due rescue cases under the company's sealed rescue rule."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("rescue_follow_ups", limit=LONG)
        return result


@workflow.defn(name="FeedbackBatch")
class FeedbackBatch:
    """Nightly: the pending feedback signals in one light-model call per company."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("feedback_batch", limit=timedelta(minutes=30))
        return result


@workflow.defn(name="SupportWeekly")
class SupportWeekly:
    """Saturday: the week's support figures to each support lead."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_weekly", limit=timedelta(minutes=15))
        return result


# ⟨1.5⟩ the support desk (prompt 10 §4-§7, §11): every activity asks the launch
# gate first and does nothing while the holding or the company is locked.
@workflow.defn(name="SupportInbound")
class SupportInbound:
    """One stored customer message through the rules, then its sends."""

    @workflow.run
    async def run(self, message_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_inbound", message_id, limit=LONG)
        return result


@workflow.defn(name="SupportSend")
class SupportSend:
    """One queued outbound message (the owner's reply, an approved draft)."""

    @workflow.run
    async def run(self, message_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_send", message_id, limit=LONG)
        return result


@workflow.defn(name="SupportSweep")
class SupportSweep:
    """Every SUPPORT_HANDOFF_DIGEST_MIN minutes: expiry, reminders, the
    owner's handoff line, held lifecycle sends, NPS waves (gated)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_sweep", limit=timedelta(minutes=10))
        return result


@workflow.defn(name="SupportShadow")
class SupportShadow:
    """One shadow run of the support charter on the company's private suite."""

    @workflow.run
    async def run(self, run_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await _act("support_shadow_run", run_id, limit=timedelta(hours=3))
        return result


@workflow.defn(name="ScoreJob")
class ScoreJob:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("score_job", limit=timedelta(minutes=30))
        return result


# Agent runs (prompt 05 §2). The conversation lives inside run_execute only:
# activity inputs and results (kept in Temporal's history) carry ids and
# metadata, never a prompt, a model output or a tool payload.
RUN_LIMIT = timedelta(minutes=58)
BUSY_WAIT = timedelta(seconds=30)
BUSY_MAX_S = 2 * 3600


@workflow.defn(name="AgentRun")
class AgentRun:
    """claim (wait while the employee is busy) -> execute -> finished."""

    @workflow.run
    async def run(self, run_id: str) -> dict[str, Any]:
        waited = 0
        while True:
            claim: dict[str, Any] = await _act("run_claim", run_id)
            if claim["state"] != "busy":
                break
            if waited >= BUSY_MAX_S:
                result: dict[str, Any] = await _act(
                    "run_finalize", run_id, "refused", "busy_timeout"
                )
                return result
            await workflow.sleep(BUSY_WAIT)
            waited += int(BUSY_WAIT.total_seconds())
        if claim["state"] != "running":
            return claim
        try:
            result = await workflow.execute_activity(
                "run_execute",
                args=[run_id],
                start_to_close_timeout=RUN_LIMIT,
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            result = await _act("run_finalize", run_id, "failed", "runtime_error")
        return result


@workflow.defn(name="SiteChecks")
class SiteChecks:
    """Every 5 minutes: the rule-based site checks, then the hub's own snapshot."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name in ("site_checks", "hub_health"):
            try:
                out[name] = await _act(name, limit=LONG, retry=RetryPolicy(maximum_attempts=2))
            except ActivityError:
                out[name] = {"error": True}
        return out


@workflow.defn(name="ProtocolRun")
class ProtocolRun:
    """One scheduled run of an oversight protocol (prompt 08 §2): code checks
    it, or it becomes the overseer's work."""

    @workflow.run
    async def run(self, ref: str) -> dict[str, Any]:
        result: dict[str, Any] = await _act(
            "protocol_run", ref, limit=LONG, retry=RetryPolicy(maximum_attempts=2)
        )
        return result


@workflow.defn(name="OversightWeekly")
class OversightWeekly:
    """Saturday: the week's challenges for every company without one."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("oversight_weekly", limit=LONG)
        return result


@workflow.defn(name="CeoDaily")
class CeoDaily:
    """The CEOs' daily report runs (prompt 05 §6): built, switched off by default."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("ceo_daily", limit=LONG)
        return result


MEDIA_LIMIT = timedelta(minutes=30)  # a 10-minute video: frames, sound track, Whisper on CPU
EVAL_LIMIT = timedelta(minutes=90)  # a suite: two model calls per case


@workflow.defn(name="EvalRun")
class EvalRun:
    """One academy eval run (prompt 08 §7): each case answered by the role
    under test and scored by the judge; tried once (every call costs tokens)."""

    @workflow.run
    async def run(self, run_id: str) -> dict[str, Any]:
        try:
            result: dict[str, Any] = await workflow.execute_activity(
                "academy_eval_run",
                args=[run_id],
                start_to_close_timeout=EVAL_LIMIT,
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as err:
            # A crash or a timeout (8.1 §2.11): the run is failed, never left
            # `running` holding the academy's monthly cap.
            await _act("academy_eval_failed", run_id, str(err.cause or err)[:200])
            return {"run": run_id, "failed": True}
        return result


@workflow.defn(name="FileProcess")
class FileProcess:
    """An owner video or audio upload (prompt 6 §2): poster, key frames, sound
    track and transcript; file.ready or file.failed at the end."""

    @workflow.run
    async def run(self, file_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await workflow.execute_activity(
            "file_process",
            args=[file_id],
            start_to_close_timeout=MEDIA_LIMIT,
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        return result


@workflow.defn(name="BrandTrace")
class BrandTrace:
    """One brand version (prompt 9.1 §2): the owner's logo traced into a
    vector mark by code in a sandboxed child (no model, no network)."""

    @workflow.run
    async def run(self, brand_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await workflow.execute_activity(
            "brand_trace",
            args=[brand_id],
            start_to_close_timeout=timedelta(minutes=3),  # the child's own deadline is 60 s
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        return result


@workflow.defn(name="Transcribe")
class Transcribe:
    """POST /transcribe (prompt 6 §3): one audio file to exact Persian text; the
    api waits for this result."""

    @workflow.run
    async def run(self, file_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await workflow.execute_activity(
            "transcribe_file",
            args=[file_id],
            start_to_close_timeout=MEDIA_LIMIT,
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=2, non_retryable_error_types=["SttUnavailable", "TooLong"]
            ),
        )
        return result


@workflow.defn(name="OrderRouting")
class OrderRouting:
    """The light model's routing of one owner order (prompt 06 §5), awaited by
    the api (which cannot reach llm-router). A failure is an empty answer: the
    order then goes to the advisor."""

    @workflow.run
    async def run(self, req: dict[str, Any]) -> dict[str, Any]:
        try:
            out: dict[str, Any] = await _act(
                "order_route",
                req,
                limit=timedelta(seconds=90),
                retry=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError:
            out = {"routes": None, "status": "error"}
        return out


WORKFLOWS = [
    SupportInbound,
    SupportSend,
    SupportSweep,
    SupportShadow,
    EvalRun,
    ProtocolRun,
    OversightWeekly,
    FileProcess,
    BrandTrace,
    Transcribe,
    AgentRun,
    SiteChecks,
    CeoDaily,
    OrderRouting,
    DecisionLifecycle,
    RecurringRun,
    Maintenance,
    Reconcile,
    NotificationDigest,
    MorningReport,
    AuditVerify,
    ScoreJob,
    StarsReminder,
    StarsRollup,
    SupportRetention,
    RevenuePulls,
    RevenuePull,
    RescueFollowUps,
    FeedbackBatch,
    SupportWeekly,
    AdvisorSweep,
    SubstituteWebJobs,
    SubstituteDaily,
    *P12B_WORKFLOWS,  # prompt 12 part B (mgmt_workflows.py)
]
