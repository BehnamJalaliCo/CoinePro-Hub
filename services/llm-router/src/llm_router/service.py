"""The call path: every model call in the holding goes through RouterService.

admit:    validate -> resolve assignment -> budgets -> priority slot ->
          breaker / quota guard (alternative only for transferable P0-P3)
          -> ledger row (status running) -> call.started event
complete: breaker verdict -> cost from our price table -> ledger row +
          usage counters (+ opt-in transcript) -> call.finished event
Fail closed: no ledger row, no model call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import asyncpg

from hq_common import oversight_share
from llm_router import anomaly, events, ledger
from llm_router.assignment import AssignmentError, apply_request, resolve, scope_chain
from llm_router.backends.base import (
    ERROR,
    OK,
    QUOTA,
    REFUSAL,
    Backend,
    BackendCall,
    BackendResult,
    ChatMessage,
    Delta,
)
from llm_router.breaker import STATE_VALUE, CircuitBreaker, Permit, State
from llm_router.budget import (
    Check,
    Consumption,
    check,
    decide,
    next_period_start,
    period_start,
)
from llm_router.config import Settings
from llm_router.cost_ratio import CostRatioWatch
from llm_router.db import Database
from llm_router.events import Events
from llm_router.metrics import Metrics
from llm_router.pricing import cost_usd
from llm_router.quota import QuotaController, Thresholds, Throttled
from llm_router.registry import Company, Connection, Registry, Snapshot, TaskClass
from llm_router.scheduler import PriorityScheduler, QueueRejected, QueueTimeout
from llm_router.schemas import RunRequest, RunResponse, UsageOut
from llm_router.uuid7 import uuid7

log = logging.getLogger("llm_router.service")


class RouterError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str = "",
        *,
        retry_after: int | None = None,
        call_id: str | None = None,
    ) -> None:
        super().__init__(message or code)
        self.status_code = status_code
        self.code = code
        self.message = message or code
        self.retry_after = retry_after
        self.call_id = call_id


@dataclass
class Plan:
    req: RunRequest
    caller: str
    company: Company
    holding: Company
    task: TaskClass
    connection: Connection
    model: str
    effort: str | None
    scopes: list[ledger.ScopeKey]
    row: ledger.CallRow
    breaker: CircuitBreaker
    permit: Permit
    started_mono: float
    fallback_from: str | None = None
    verdict: bool = False
    finished: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def rls_scope(self) -> set[str]:
        return {self.company.id, self.holding.id}


def _usage_scopes(
    chain: list[tuple[str, str]], company: Company, holding: Company
) -> list[ledger.ScopeKey]:
    """Owner company of each scope: holding-wide refs belong to the holding."""
    keys = []
    for scope_type, ref in chain:
        qualified = scope_type in ("company", "department") or ref.startswith(f"{company.code}:")
        owner = company if qualified else holding
        if scope_type == "holding":
            owner = holding
        keys.append(ledger.ScopeKey(owner.id, scope_type, ref))
    return keys


def _sse(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


class RouterService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        registry: Registry,
        events_: Events,
        metrics: Metrics,
        scheduler: PriorityScheduler,
        backends: Mapping[str, Backend],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        quota: QuotaController | None = None,
    ) -> None:
        self.s = settings
        self.db = db
        self.registry = registry
        self.events = events_
        self.metrics = metrics
        self.scheduler = scheduler
        self.backends = backends
        self.now = now
        self.breakers: dict[str, CircuitBreaker] = {}
        self._anomaly_seen: set[tuple[str, str]] = set()
        self.cost_ratio = CostRatioWatch(now=now)
        self._locks: dict[str, tuple[str | None, float]] = {}
        self.quota = quota or QuotaController(
            db,
            events_,
            thresholds=Thresholds(
                warn_5h=settings.quota_warn_5h,
                limit_5h=settings.quota_limit_5h,
                warn_7d=settings.quota_warn_7d,
                limit_7d=settings.quota_limit_7d,
            ),
            now=now,
        )
        metrics.capacity.set(scheduler.capacity)

    # --------------------------------------------------------- kill switch --
    async def lock_state(self, company_id: str) -> str | None:
        """'holding' | 'company' | 'deploy_freeze' | None (control.lock_state,
        apps/api migration 0005), cached for 2 s. Without the control schema
        (a router-only database) nothing is locked."""
        now = time.monotonic()
        hit = self._locks.get(company_id)
        if hit is not None and now - hit[1] < 2.0:
            return hit[0]
        try:
            async with self.db.scoped({company_id}) as conn:
                state = await conn.fetchval("SELECT control.lock_state($1::uuid)", company_id)
        except (asyncpg.UndefinedFunctionError, asyncpg.InvalidSchemaNameError):
            state = None
        self._locks[company_id] = (state, now)
        return None if state is None else str(state)

    # ------------------------------------------------------------ breakers --
    def breaker_for(self, conn: Connection) -> CircuitBreaker:
        b = self.breakers.get(conn.id)
        if b is None:
            b = self.breakers[conn.id] = CircuitBreaker(conn.key)
            if conn.status == "quota_exhausted":
                b.restore_quota(
                    conn.status_changed_at.timestamp(),
                    conn.quota_reset_at.timestamp() if conn.quota_reset_at else None,
                )
        return b

    def _publish_breaker(self, conn: Connection, b: CircuitBreaker) -> None:
        self.metrics.breaker_state.labels(conn.key).set(STATE_VALUE[b.state])
        quota = b.state is not State.CLOSED and b.snapshot.reason == "quota"
        self.metrics.quota_exhausted.labels(conn.key).set(1 if quota else 0)

    # --------------------------------------------------------------- admit --
    async def admit(self, req: RunRequest, caller: str, max_input_chars: int) -> Plan:
        snap = await self.registry.get()
        company = snap.companies.get(req.company_code)
        if company is None or company.status != "active":
            raise RouterError(422, "unknown_company", f"no active company {req.company_code!r}")
        # Kill switch (contract §9): while the holding's or the company's switch
        # is engaged only P0 (war room / SEV1) runs. A deploy freeze stops write
        # actions, not thinking, so it does not block calls.
        if req.priority > 0 and await self.lock_state(company.id) in ("holding", "company"):
            self.metrics.queue_rejections.labels(f"P{req.priority}", "kill_switch").inc()
            raise RouterError(423, "company_locked", "the kill switch is engaged; only P0 runs")
        task = snap.task_classes.get(req.task_class)
        if task is None:
            raise RouterError(422, "unknown_task_class", f"no task class {req.task_class!r}")
        if req.timeout_s > self.s.max_timeout_s:
            raise RouterError(
                422, "timeout_too_long", f"timeout_s is capped at {self.s.max_timeout_s}"
            )
        if req.input_chars() > max_input_chars:
            raise RouterError(
                413, "input_too_large", f"input is limited to {max_input_chars} characters"
            )
        holding = snap.holding

        chain = scope_chain(
            holding=holding.code,
            company=company.code,
            department=req.department,
            role=req.role,
            task_class=task.key,
            employee=req.employee,
        )
        try:
            resolved = resolve(snap.assignments, chain)
            connection = snap.connections[resolved.connection_id]
            model, effort = apply_request(
                resolved,
                requested_model=req.model,
                requested_effort=req.effort,
                allowed_models=list(connection.models),
                default_model=connection.default_model,
            )
        except AssignmentError as exc:
            raise RouterError(422, "assignment", str(exc)) from exc

        now = self.now()
        row = ledger.CallRow(
            id=str(uuid7()),
            started_at=now,
            company_id=company.id,
            actor_ref=req.actor_ref,
            task_class=task.key,
            priority=req.priority,
            caller=caller,
            department=req.department,
            work_ref=req.work_ref,
            connection_id=connection.id,
            provider=connection.provider,
            model=model,
            effort=effort,
            meta={
                "assignment": list(resolved.trail),
                **(req.meta or {}),
                # how many images the model saw (never their bytes)
                **({"images": len(req.images())} if req.images() else {}),
            },
        )
        scopes = _usage_scopes(chain, company, holding)
        rls = {company.id, holding.id}

        # Quota Controller (prompt 05 §8): at `warning` P4 waits, at `limited` P3-P4.
        # While the breaker is open and cooling (usage limit hit), the breaker path
        # below decides instead (alternatives, quota_exhausted); a half-open probe
        # is checked like any request (prompt 5.1 §2.4).
        try:
            if not self.breaker_for(connection).cooling():
                self.quota.check(connection.id, connection.kind, req.priority)
        except Throttled as exc:
            self.metrics.queue_rejections.labels(f"P{req.priority}", f"quota_{exc.status}").inc()
            async with self.db.scoped(rls) as conn:
                await ledger.record_decision(conn, row, "rate_limited", f"quota_{exc.status}")
            raise RouterError(
                429 if req.priority >= 4 else 503,
                "quota_throttled",
                f"the subscription quota is {exc.status}: P{req.priority} waits",
                retry_after=exc.retry_after,
                call_id=row.id,
            ) from exc

        await self._check_budgets(snap, req, company, chain, row, rls, now)
        await self._check_oversight_share(req, company, holding, row, rls, now)

        try:
            await self.scheduler.acquire(req.priority, timeout=req.timeout_s)
        except QueueRejected as exc:
            self.metrics.queue_rejections.labels(f"P{req.priority}", exc.reason).inc()
            raise RouterError(
                429 if req.priority >= 4 else 503,
                exc.reason,
                "the queue is full; try again",
                retry_after=exc.retry_after_s,
            ) from exc
        except QueueTimeout as exc:
            self.metrics.queue_rejections.labels(f"P{req.priority}", "queue_timeout").inc()
            raise RouterError(504, "queue_timeout", "no slot within timeout_s") from exc
        self._gauges()

        plan: Plan | None = None
        try:
            plan = await self._pick_connection(
                snap, req, task, company, holding, connection, model, effort, scopes, row
            )
            async with self.db.scoped(rls) as conn:
                await ledger.insert_call(conn, plan.row)
        except RouterError:
            self.scheduler.release()
            self._gauges()
            raise
        except Exception as exc:
            self.scheduler.release()
            self._gauges()
            if plan is not None:
                plan.breaker.release_probe(plan.permit)
            log.exception("ledger insert failed", extra={"call_id": row.id})
            raise RouterError(503, "ledger_unavailable", "the ledger is unavailable") from exc

        await self.events.publish(events.call_subject(company.code, "started"), self._event(plan))
        return plan

    async def _check_budgets(
        self,
        snap: Snapshot,
        req: RunRequest,
        company: Company,
        chain: list[tuple[str, str]],
        row: ledger.CallRow,
        rls: set[str],
        now: datetime,
    ) -> None:
        budgets = [b for key in chain for b in snap.budgets.get(key, [])]
        if not budgets:
            return
        async with self.db.scoped(rls | {b.company_id for b in budgets}) as conn:
            usage = await ledger.load_usage(
                conn, [(b.scope_type, b.scope_ref, b.period) for b in budgets], now
            )
        checks = [
            check(b, usage.get((b.scope_type, b.scope_ref, b.period), Consumption()))
            for b in budgets
        ]
        decision = decide(req.priority, checks, now)
        for c in decision.alerts:
            await self._budget_alert(snap, c, now)
        if not decision.allowed:
            self.metrics.budget_rejections.labels(company.code).inc()
            self.metrics.calls.labels(
                company.code, "-", row.model or "-", "rejected_budget", f"P{req.priority}"
            ).inc()
            async with self.db.scoped(rls) as conn:
                await ledger.record_decision(conn, row, "rejected_budget", "budget_exhausted")
            raise RouterError(
                429,
                "budget_exhausted",
                "a budget for this call is used up",
                retry_after=decision.retry_after_s,
                call_id=row.id,
            )
        if decision.exhausted:
            row.meta["budget_over"] = [
                f"{c.budget.scope_type}:{c.budget.scope_ref}" for c in decision.exhausted
            ]

    async def _check_oversight_share(
        self,
        req: RunRequest,
        company: Company,
        holding: Company,
        row: ledger.CallRow,
        rls: set[str],
        now: datetime,
    ) -> None:
        """The oversight share (prompt 08 §2.3, contract §18.1 v1.4.4): the
        holding's overseer and QC together stop at OVERSIGHT_DAILY_SHARE of
        AGENT_DAILY_TOKEN_CAP per UTC day, like a budget at 100% but for every
        priority; only a `critical` protocol's run still goes."""
        cap = oversight_share.limit(self.s.agent_daily_token_cap, self.s.oversight_daily_share)
        if req.role not in oversight_share.ROLES or company.id != holding.id:
            return
        if (req.meta or {}).get("severity") == oversight_share.CRITICAL:
            return
        keys = [("role", f"{holding.code}:{role}", "day") for role in oversight_share.ROLES]
        async with self.db.scoped({holding.id}) as conn:
            usage = await ledger.load_usage(conn, keys, now)
        used = sum(c.tokens for c in usage.values())
        if not oversight_share.spent(
            used, self.s.agent_daily_token_cap, self.s.oversight_daily_share
        ):
            return
        self.metrics.budget_rejections.labels(company.code).inc()
        self.metrics.calls.labels(
            company.code, "-", row.model or "-", "rejected_budget", f"P{req.priority}"
        ).inc()
        async with self.db.scoped(rls) as conn:
            await ledger.record_decision(conn, row, "rejected_budget", "oversight_share")
        retry = max(1, int((next_period_start("day", now) - now).total_seconds()))
        raise RouterError(
            429,
            "budget_exhausted",
            f"the oversight share of today's token cap is used up ({used}/{cap})",
            retry_after=retry,
            call_id=row.id,
        )

    async def _budget_alert(self, snap: Snapshot, c: Check, now: datetime) -> None:
        owner = snap.companies_by_id.get(c.budget.company_id)
        code = owner.code if owner else "UNKNOWN"
        self.metrics.budget_alerts.labels(code, str(c.level)).inc()
        await self.events.publish(
            events.budget_subject(code),
            {
                "type": "budget",
                "level": c.level,
                "percent": c.percent,
                "company": code,
                "scope_type": c.budget.scope_type,
                "scope_ref": c.budget.scope_ref,
                "period": c.budget.period,
                "tokens_used": c.used.tokens,
                "usd_used": str(c.used.usd),
                "token_limit": c.budget.token_limit,
                "usd_limit": str(c.budget.usd_limit) if c.budget.usd_limit else None,
                "at": now.isoformat(),
            },
        )
        try:
            async with self.db.scoped({c.budget.company_id}) as conn:
                await ledger.set_budget_alert(
                    conn, c.budget.id, c.level, period_start(c.budget.period, now)
                )
            self.registry.invalidate()
        except Exception:
            log.exception("budget alert state not saved", extra={"budget_id": c.budget.id})

    async def _pick_connection(
        self,
        snap: Snapshot,
        req: RunRequest,
        task: TaskClass,
        company: Company,
        holding: Company,
        connection: Connection,
        model: str,
        effort: str | None,
        scopes: list[ledger.ScopeKey],
        row: ledger.CallRow,
    ) -> Plan:
        def plan_for(conn: Connection, permit: Permit, mdl: str, fallback_from: str | None) -> Plan:
            row.connection_id, row.provider, row.model = conn.id, conn.provider, mdl
            if fallback_from:
                row.meta["fallback_from"] = fallback_from
            return Plan(
                req,
                row.caller,
                company,
                holding,
                task,
                conn,
                mdl,
                effort,
                scopes,
                row,
                self.breaker_for(conn),
                permit,
                time.monotonic(),
                fallback_from,
            )

        if connection.status == "disabled":
            raise RouterError(
                503, "connection_disabled", f"connection {connection.key} is disabled"
            )
        breaker = self.breaker_for(connection)
        permit = breaker.allow()
        self._publish_breaker(connection, breaker)
        if permit is not None:
            return plan_for(connection, permit, model, None)

        # Primary unavailable. §1.6: only transferable work, only P0-P3, only
        # to a connection that is switched on.
        if req.priority <= 3 and task.transferable:
            for alt in snap.fallbacks():
                if alt.id == connection.id or alt.kind != "api":
                    continue
                alt_model = req.model if req.model in alt.models else alt.default_model
                if not alt_model:
                    continue
                alt_breaker = self.breaker_for(alt)
                alt_permit = alt_breaker.allow()
                if alt_permit is not None:
                    return plan_for(alt, alt_permit, alt_model, connection.key)

        reason = breaker.snapshot.reason or "unavailable"
        status = QUOTA if reason == "quota" else ERROR
        code = "quota_exhausted" if reason == "quota" else "circuit_open"
        retry = breaker.retry_after_s()
        self.metrics.calls.labels(
            company.code, connection.key, model, status, f"P{req.priority}"
        ).inc()
        async with self.db.scoped({company.id, holding.id}) as conn:
            await ledger.record_decision(conn, row, status, code)
        raise RouterError(
            429 if req.priority >= 4 else 503,
            code,
            f"connection {connection.key} is unavailable ({reason}) and no alternative is on",
            retry_after=retry,
            call_id=row.id,
        )

    # ------------------------------------------------------------ complete --
    def _call(self, plan: Plan) -> BackendCall:
        return BackendCall(
            call_id=plan.row.id,
            connection=plan.connection,
            model=plan.model,
            effort=plan.effort,
            system=plan.req.system,
            messages=tuple(
                ChatMessage(m.role, m.text(), m.parts()) for m in plan.req.as_messages()
            ),
            json_schema=plan.req.json_schema,
            timeout_s=plan.req.timeout_s,
            actor_ref=plan.req.actor_ref,
            max_output_tokens=min(plan.req.max_output_tokens, self.s.max_output_tokens)
            if plan.req.max_output_tokens
            else None,
        )

    def _backend(self, plan: Plan) -> Backend:
        return self.backends[plan.connection.kind]

    async def _verdict(self, plan: Plan, result: BackendResult) -> None:
        b, conn = plan.breaker, plan.connection
        was_quota = b.snapshot.reason == "quota" and b.state is not State.CLOSED
        if result.status in (OK, REFUSAL):
            b.on_success(plan.permit)
        elif result.status == QUOTA:
            b.on_quota(plan.permit, result.quota_resets_at)
        else:
            b.on_failure(plan.permit)
        plan.verdict = True
        self._publish_breaker(conn, b)
        snap = b.snapshot
        try:
            if result.status == QUOTA and snap.state is State.OPEN:
                assert snap.opened_at is not None
                assert snap.retry_at is not None
                async with self.db.scoped(plan.rls_scope) as c:
                    await ledger.set_connection_status(
                        c,
                        conn.id,
                        "quota_exhausted",
                        result.error_class or "quota",
                        datetime.fromtimestamp(snap.opened_at, UTC),
                        datetime.fromtimestamp(snap.retry_at, UTC),
                    )
                self.registry.invalidate()
            elif was_quota and snap.state is State.CLOSED:
                async with self.db.scoped(plan.rls_scope) as c:
                    await ledger.set_connection_status(
                        c, conn.id, "enabled", None, self.now(), None
                    )
                self.registry.invalidate()
        except Exception:
            log.exception("connection status not saved", extra={"connection": conn.key})

    async def _observe_quota(self, conn: Connection, result: BackendResult) -> None:
        if conn.kind != "claude_subscription":
            return
        try:
            if result.rate_limit:
                await self.quota.observe(conn.id, conn.key, result.rate_limit)
            if result.status == QUOTA:
                resets = (
                    datetime.fromtimestamp(result.quota_resets_at, UTC)
                    if result.quota_resets_at
                    else None
                )
                # No reset time in the error (every billing_error): the hold ends
                # when the breaker probes again, never "for good".
                snap = self.breaker_for(conn).snapshot
                retry = (
                    datetime.fromtimestamp(snap.retry_at, UTC)
                    if snap.state is State.OPEN and snap.retry_at is not None
                    else None
                )
                await self.quota.on_quota_guard(conn.id, conn.key, resets, fallback=retry)
        except Exception:
            log.exception("quota state not updated", extra={"connection": conn.key})

    async def quota_scan(self) -> int:
        """Periodic Quota Controller pass (resets, ledger windows)."""
        snap = await self.registry.get()
        subs = {c.id: c.key for c in snap.connections.values() if c.kind == "claude_subscription"}
        return len(await self.quota.scan(subs, set(snap.companies_by_id)))

    async def complete(self, plan: Plan, result: BackendResult) -> RunResponse:
        await self._verdict(plan, result)
        await self._observe_quota(plan.connection, result)
        now = self.now()
        latency_ms = int((time.monotonic() - plan.started_mono) * 1000)
        conn = plan.connection
        usage = result.usage
        cost = equiv = priced = None
        if usage is not None:
            # Our price table is the only cost source (owner decision, prompt 04 §9).
            priced = cost_usd(conn.pricing, result.model or plan.model, usage)
            if priced is None:
                priced = cost_usd(conn.pricing, plan.model, usage)
            if conn.kind == "api":
                cost = priced
            else:
                equiv = priced
        meta: dict[str, Any] = {}
        if result.sdk_cost_usd is not None:
            meta["sdk_cost_usd"] = str(result.sdk_cost_usd)
        if usage is not None and usage.cache_write_1h_tokens is not None:
            meta["cache_write_1h_tokens"] = usage.cache_write_1h_tokens
        if result.stop_reason:
            meta["stop_reason"] = result.stop_reason
        if result.effort_applied is not None:
            meta["effort_applied"] = result.effort_applied
        if result.compare_cost_usd is not None:
            meta["litellm_cost_usd"] = str(result.compare_cost_usd)
        if result.rate_limit:
            meta["rate_limit"] = {
                k: result.rate_limit.get(k) for k in ("status", "window", "utilization")
            }
        fin = ledger.Finish(
            status=result.status,
            finished_at=now,
            usage=usage,
            cost_usd=cost,
            equiv_cost_usd=equiv,
            latency_ms=latency_ms,
            error_class=result.error_class,
            model=result.model,
            meta=meta,
        )
        try:
            async with self.db.scoped(plan.rls_scope) as c:
                await ledger.finish_call(c, plan.row, fin)
                if usage is not None:
                    await ledger.add_usage(
                        c, plan.scopes, now, usage.total, cost or equiv or Decimal(0)
                    )
                if plan.req.store_transcript and result.status in (OK, REFUSAL):
                    await ledger.insert_transcript(
                        c,
                        plan.row.id,
                        plan.company.id,
                        self.s.transcript_retention_days,
                        {
                            "system": plan.req.system,
                            # an image stays out of the transcript: its type and size only
                            "messages": [m.without_bytes() for m in plan.req.as_messages()],
                        },
                        result.text,
                        result.structured,
                        now,
                    )
            plan.finished = True
        except Exception:
            log.exception("ledger finish failed", extra={"call_id": plan.row.id})

        model = result.model or plan.model
        code = plan.company.code
        self.metrics.calls.labels(
            code, conn.key, model, result.status, f"P{plan.req.priority}"
        ).inc()
        self.metrics.latency.labels(conn.key, model).observe(latency_ms / 1000)
        if usage is not None:
            for kind, n in (
                ("input", usage.input_tokens),
                ("output", usage.output_tokens),
                ("cache_read", usage.cache_read_tokens),
                ("cache_write", usage.cache_write_tokens),
                ("thinking", usage.thinking_tokens or 0),
            ):
                if n:
                    self.metrics.tokens.labels(code, conn.key, model, kind).inc(n)
        if cost:
            self.metrics.cost.labels(code, conn.key, "real").inc(float(cost))
        if equiv:
            self.metrics.cost.labels(code, conn.key, "equiv").inc(float(equiv))
        if result.sdk_cost_usd is not None and priced:
            await self._watch_cost_ratio(conn.key, model, result.sdk_cost_usd, priced)

        response = RunResponse(
            call_id=plan.row.id,
            status=result.status,
            text=result.text,
            json_output=result.structured,
            usage=UsageOut(**usage.__dict__) if usage else None,
            connection=conn.key,
            model=model,
            effort=plan.effort,
            cost_usd=str(cost) if cost is not None else None,
            equiv_cost_usd=str(equiv) if equiv is not None else None,
            latency_ms=latency_ms,
            error_class=result.error_class,
        )
        await self.events.publish(
            events.call_subject(code, "finished"),
            {**self._event(plan), **response.model_dump(exclude={"text", "json_output"})},
        )
        log.info(
            "call finished",
            extra={
                "call_id": plan.row.id,
                "company": code,
                "actor_ref": plan.req.actor_ref,
                "task_class": plan.task.key,
                "priority": plan.req.priority,
                "connection": conn.key,
                "model": model,
                "status": result.status,
                "error_class": result.error_class,
                "latency_ms": latency_ms,
                "tokens": usage.total if usage else 0,
            },
        )
        return response

    def release(self, plan: Plan) -> None:
        if not plan.verdict:
            plan.breaker.release_probe(plan.permit)
        self.scheduler.release()
        self._gauges()

    # ----------------------------------------------------------------- run --
    async def run(self, req: RunRequest, caller: str, max_input_chars: int) -> RunResponse:
        plan = await self.admit(req, caller, max_input_chars)
        try:
            try:
                result = await self._backend(plan).run(self._call(plan))
            except Exception:
                log.exception("backend raised", extra={"call_id": plan.row.id})
                result = BackendResult(ERROR, error_class="backend_exception")
            return await self.complete(plan, result)
        finally:
            self.release(plan)

    async def stream(
        self, req: RunRequest, caller: str, max_input_chars: int
    ) -> AsyncIterator[str]:
        plan = await self.admit(req, caller, max_input_chars)

        async def gen() -> AsyncIterator[str]:
            result: BackendResult | None = None
            try:
                yield _sse(
                    "start",
                    {
                        "call_id": plan.row.id,
                        "connection": plan.connection.key,
                        "model": plan.model,
                    },
                )
                async for item in self._backend(plan).stream(self._call(plan)):
                    if isinstance(item, Delta):
                        yield _sse("delta", {"text": item.text})
                    else:
                        result = item
                response = await self.complete(
                    plan, result or BackendResult(ERROR, error_class="stream_without_result")
                )
                yield _sse("end", response.model_dump(by_alias=True))
            except (asyncio.CancelledError, GeneratorExit):
                if not plan.finished:
                    await asyncio.shield(
                        self.complete(plan, BackendResult(ERROR, error_class="client_disconnected"))
                    )
                raise
            finally:
                self.release(plan)

        return gen()

    # ------------------------------------------------------------- helpers --
    def _event(self, plan: Plan) -> dict[str, Any]:
        return {
            "call_id": plan.row.id,
            "company": plan.company.code,
            "actor_ref": plan.req.actor_ref,
            "work_ref": plan.req.work_ref,
            "department": plan.req.department,
            "task_class": plan.task.key,
            "priority": plan.req.priority,
            "connection": plan.connection.key,
            "model": plan.model,
            "effort": plan.effort,
            "fallback_from": plan.fallback_from,
            "started_at": plan.row.started_at.isoformat(),
        }

    def _gauges(self) -> None:
        self.metrics.active.set(self.scheduler.active)
        for p in range(5):
            self.metrics.queue_depth.labels(f"P{p}").set(self.scheduler.waiting(p))

    async def connections_view(self) -> list[dict[str, Any]]:
        snap = await self.registry.get()
        out = []
        for c in sorted(snap.connections.values(), key=lambda c: (c.fallback_priority or 0, c.key)):
            b = self.breaker_for(c)
            out.append(
                {
                    "key": c.key,
                    "kind": c.kind,
                    "provider": c.provider,
                    "display_name": c.display_name,
                    "status": c.status,
                    "breaker": b.state.value,
                    "breaker_reason": b.snapshot.reason,
                    "retry_after_s": b.retry_after_s(),
                    "models": list(c.models),
                    "default_model": c.default_model,
                    "fallback_priority": c.fallback_priority,
                    "quota_reset_at": c.quota_reset_at.isoformat() if c.quota_reset_at else None,
                }
            )
        return out

    # --------------------------------------------------------- maintenance --
    async def _all_companies(self) -> set[str]:
        return set((await self.registry.get()).companies_by_id)

    async def maintenance(self) -> dict[str, int]:
        scope = await self._all_companies()
        async with self.db.scoped(scope) as conn:
            parts = await conn.fetchval("SELECT llm.ensure_calls_partitions(3)")
            purged = await conn.fetchval("SELECT llm.purge_expired_transcripts()")
        return {"partitions_created": int(parts), "transcripts_purged": int(purged)}

    async def close_stale(self) -> int:
        async with self.db.scoped(await self._all_companies()) as conn:
            return await ledger.close_stale_running(conn, older_than_s=self.s.max_timeout_s + 300)

    async def _watch_cost_ratio(
        self, connection: str, model: str, sdk_cost: Decimal, priced: Decimal
    ) -> None:
        self.metrics.sdk_cost.labels(connection, model).inc(float(sdk_cost))
        self.metrics.priced_cost.labels(connection, model).inc(float(priced))
        ratio, alert = self.cost_ratio.observe(connection, model, sdk_cost, priced)
        if ratio is not None:
            self.metrics.sdk_cost_ratio.labels(connection, model).set(float(ratio))
        if alert is not None:
            self.metrics.cost_ratio_alerts.inc()
            log.warning("sdk cost estimate drifts from the price table", extra=alert)
            await self.events.publish(events.COST_RATIO_SUBJECT, alert)

    async def anomaly_scan(self) -> list[dict[str, Any]]:
        snap = await self.registry.get()
        alerts = []
        async with self.db.scoped(set(snap.companies_by_id)) as conn:
            hour = await conn.fetchval("SELECT date_trunc('hour', now())")
            current = await conn.fetch(
                """SELECT actor_ref, company_id::text, count(*) AS n FROM llm.calls
                   WHERE started_at >= $1 GROUP BY 1, 2 HAVING count(*) > $2""",
                hour,
                self.s.anomaly_min_calls,
            )
            for r in current:
                history = await conn.fetch(
                    """SELECT count(*) AS n FROM llm.calls
                       WHERE actor_ref = $1
                         AND started_at >= $2::timestamptz - interval '7 days'
                         AND started_at < $2::timestamptz
                       GROUP BY date_trunc('hour', started_at)""",
                    r["actor_ref"],
                    hour,
                )
                hit, limit = anomaly.is_anomalous(
                    int(r["n"]),
                    [int(h["n"]) for h in history],
                    factor=self.s.anomaly_factor,
                    min_calls=self.s.anomaly_min_calls,
                )
                key = (r["actor_ref"], hour.isoformat())
                if hit and key not in self._anomaly_seen:
                    self._anomaly_seen.add(key)
                    company = snap.companies_by_id.get(r["company_id"])
                    alert = {
                        "type": "llm_anomaly",
                        "actor_ref": r["actor_ref"],
                        "company": company.code if company else None,
                        "calls_this_hour": int(r["n"]),
                        "threshold": limit,
                        "hour": hour.isoformat(),
                    }
                    alerts.append(alert)
                    self.metrics.anomalies.inc()
                    await self.events.publish(events.ANOMALY_SUBJECT, alert)
        if len(self._anomaly_seen) > 10_000:
            self._anomaly_seen.clear()
        return alerts
