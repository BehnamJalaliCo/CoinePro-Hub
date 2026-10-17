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
                return {"ref": ref, "result": "applied", **result}
            except ActivityError as err:
                if _cause_type(err) == "HoldingLocked":
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


@workflow.defn(name="CeoDaily")
class CeoDaily:
    """The CEOs' daily report runs (prompt 05 §6): built, switched off by default."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        result: dict[str, Any] = await _act("ceo_daily", limit=LONG)
        return result


WORKFLOWS = [
    AgentRun,
    SiteChecks,
    CeoDaily,
    DecisionLifecycle,
    RecurringRun,
    Maintenance,
    Reconcile,
    NotificationDigest,
    MorningReport,
    AuditVerify,
    ScoreJob,
]
