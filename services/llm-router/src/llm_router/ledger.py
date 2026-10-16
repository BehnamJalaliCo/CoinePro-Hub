"""Token Treasury writes: one llm.calls row per call, plus usage counters.

Text (prompt, system, response) is never written here. Transcripts are a
separate, opt-in, expiring table.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg

from llm_router.budget import Consumption, period_start
from llm_router.pricing import Usage

PERIODS = ("day", "month")


@dataclass(frozen=True)
class ScopeKey:
    company_id: str  # owner of the scope (RLS)
    scope_type: str
    scope_ref: str


@dataclass
class CallRow:
    id: str
    started_at: datetime
    company_id: str
    actor_ref: str
    task_class: str
    priority: int
    caller: str
    department: str | None = None
    work_ref: str | None = None
    connection_id: str | None = None
    provider: str | None = None
    model: str | None = None
    effort: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Finish:
    status: str
    finished_at: datetime
    usage: Usage | None = None
    cost_usd: Decimal | None = None
    equiv_cost_usd: Decimal | None = None
    latency_ms: int | None = None
    error_class: str | None = None
    model: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


async def insert_call(conn: asyncpg.Connection, row: CallRow, status: str = "running") -> None:
    await conn.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, department, actor_ref, work_ref,
               task_class, priority, caller, connection_id, provider, model, effort, status, meta)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb)""",
        row.id,
        row.started_at,
        row.company_id,
        row.department,
        row.actor_ref,
        row.work_ref,
        row.task_class,
        row.priority,
        row.caller,
        row.connection_id,
        row.provider,
        row.model,
        row.effort,
        status,
        json.dumps(row.meta),
    )


async def finish_call(conn: asyncpg.Connection, row: CallRow, fin: Finish) -> None:
    u = fin.usage
    status = await conn.execute(
        """UPDATE llm.calls SET finished_at = $3, status = $4, error_class = $5,
               input_tokens = $6, output_tokens = $7, cache_read_tokens = $8,
               cache_write_tokens = $9, thinking_tokens = $10, cost_usd = $11,
               equiv_cost_usd = $12, latency_ms = $13, model = coalesce($14, model),
               meta = meta || $15::jsonb
           WHERE id = $1 AND started_at = $2""",
        row.id,
        row.started_at,
        fin.finished_at,
        fin.status,
        fin.error_class,
        u.input_tokens if u else None,
        u.output_tokens if u else None,
        u.cache_read_tokens if u else None,
        u.cache_write_tokens if u else None,
        u.thinking_tokens if u else None,
        fin.cost_usd,
        fin.equiv_cost_usd,
        fin.latency_ms,
        fin.model,
        json.dumps(fin.meta),
    )
    if status != "UPDATE 1":
        raise RuntimeError(f"ledger row {row.id} not updated ({status})")


async def record_decision(
    conn: asyncpg.Connection, row: CallRow, status: str, error_class: str
) -> None:
    """A call that was refused before reaching a model (budget, quota)."""
    await insert_call(conn, row, status=status)
    await conn.execute(
        "UPDATE llm.calls SET finished_at = started_at, error_class = $3, latency_ms = 0"
        " WHERE id = $1 AND started_at = $2",
        row.id,
        row.started_at,
        error_class,
    )


async def add_usage(
    conn: asyncpg.Connection, scopes: Iterable[ScopeKey], now: datetime, tokens: int, usd: Decimal
) -> None:
    rows = [
        (s.company_id, s.scope_type, s.scope_ref, p, period_start(p, now))
        for s in scopes
        for p in PERIODS
    ]
    if not rows:
        return
    await conn.execute(
        """INSERT INTO llm.usage (company_id, scope_type, scope_ref, period, period_start,
                                  calls, tokens, usd)
           SELECT r.company_id, r.scope_type, r.scope_ref, r.period, r.period_start, 1, $6, $7
           FROM unnest($1::uuid[], $2::text[], $3::text[], $4::text[], $5::date[])
                AS r(company_id, scope_type, scope_ref, period, period_start)
           ON CONFLICT (scope_type, scope_ref, period, period_start) DO UPDATE
           SET calls = llm.usage.calls + 1, tokens = llm.usage.tokens + EXCLUDED.tokens,
               usd = llm.usage.usd + EXCLUDED.usd, updated_at = now()""",
        [r[0] for r in rows],
        [r[1] for r in rows],
        [r[2] for r in rows],
        [r[3] for r in rows],
        [r[4] for r in rows],
        tokens,
        usd,
    )


async def load_usage(
    conn: asyncpg.Connection, keys: Iterable[tuple[str, str, str]], now: datetime
) -> dict[tuple[str, str, str], Consumption]:
    """(scope_type, scope_ref, period) -> consumption in the current period."""
    wanted = list(keys)
    if not wanted:
        return {}
    records = await conn.fetch(
        """SELECT u.scope_type, u.scope_ref, u.period, u.tokens, u.usd
           FROM llm.usage u
           JOIN unnest($1::text[], $2::text[], $3::text[], $4::date[]) AS k(t, r, p, s)
             ON u.scope_type = k.t AND u.scope_ref = k.r
            AND u.period = k.p AND u.period_start = k.s""",
        [k[0] for k in wanted],
        [k[1] for k in wanted],
        [k[2] for k in wanted],
        [period_start(k[2], now) for k in wanted],
    )
    return {
        (r["scope_type"], r["scope_ref"], r["period"]): Consumption(
            int(r["tokens"]), Decimal(r["usd"])
        )
        for r in records
    }


async def set_budget_alert(
    conn: asyncpg.Connection, budget_id: str, level: int, start: Any
) -> None:
    await conn.execute(
        "UPDATE llm.budgets SET alert_level = $2, alert_period_start = $3, updated_at = now()"
        " WHERE id = $1",
        budget_id,
        level,
        start,
    )


async def insert_transcript(
    conn: asyncpg.Connection,
    call_id: str,
    company_id: str,
    retention_days: int,
    request: dict[str, Any],
    response: str | None,
    structured: Any,
    now: datetime,
) -> None:
    await conn.execute(
        """INSERT INTO llm.transcripts
               (call_id, company_id, created_at, expires_at, request, response, structured)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb)""",
        call_id,
        company_id,
        now,
        now + timedelta(days=retention_days),
        json.dumps(request),
        response,
        json.dumps(structured) if structured is not None else None,
    )


async def close_stale_running(conn: asyncpg.Connection, older_than_s: int) -> int:
    """Rows left 'running' by a crash become errors (seen only at startup)."""
    status = await conn.execute(
        """UPDATE llm.calls SET status = 'error', error_class = 'interrupted', finished_at = now()
           WHERE status = 'running' AND started_at < now() - make_interval(secs => $1)""",
        older_than_s,
    )
    return int(status.split()[-1])


async def set_connection_status(
    conn: asyncpg.Connection,
    connection_id: str,
    status: str,
    reason: str | None,
    changed_at: datetime,
    reset_at: datetime | None,
) -> None:
    await conn.execute(
        """UPDATE llm.connections SET status = $2, status_reason = $3, status_changed_at = $4,
               quota_reset_at = $5, updated_at = now()
           WHERE id = $1 AND status <> 'disabled'""",
        connection_id,
        status,
        reason,
        changed_at,
        reset_at,
    )
