"""In-memory view of the registry tables, refreshed every few seconds.

Companies, connections, task classes, assignments and budgets change rarely
(by the owner, later from the app); calls read them from this cache.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from llm_router.assignment import Assignment
from llm_router.budget import Budget
from llm_router.db import Database


@dataclass(frozen=True)
class Company:
    id: str
    code: str
    name: str
    kind: str
    status: str


@dataclass(frozen=True)
class Connection:
    id: str
    key: str
    kind: str
    provider: str
    display_name: str
    status: str
    status_changed_at: datetime
    quota_reset_at: datetime | None
    secret_ref: str | None
    api_base: str | None
    models: tuple[str, ...]
    default_model: str | None
    pricing: dict[str, Any]
    limits: dict[str, Any]
    fallback_priority: int | None


@dataclass(frozen=True)
class TaskClass:
    key: str
    transferable: bool


@dataclass
class Snapshot:
    companies: dict[str, Company] = field(default_factory=dict)  # by code
    companies_by_id: dict[str, Company] = field(default_factory=dict)
    connections: dict[str, Connection] = field(default_factory=dict)  # by id
    task_classes: dict[str, TaskClass] = field(default_factory=dict)
    assignments: dict[tuple[str, str], Assignment] = field(default_factory=dict)
    budgets: dict[tuple[str, str], list[Budget]] = field(default_factory=dict)
    loaded_at: float = 0.0

    @property
    def holding(self) -> Company:
        for c in self.companies.values():
            if c.kind == "holding":
                return c
        raise LookupError("no holding company in core.companies")

    def connection_by_key(self, key: str) -> Connection | None:
        return next((c for c in self.connections.values() if c.key == key), None)

    def fallbacks(self) -> list[Connection]:
        """Alternative connections (§1.6), in fallback order."""
        alts = [
            c
            for c in self.connections.values()
            if c.fallback_priority is not None and c.status == "enabled"
        ]
        return sorted(alts, key=lambda c: (c.fallback_priority or 0, c.key))


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def load(db: Database) -> Snapshot:
    snap = Snapshot(loaded_at=time.monotonic())
    async with db.pool.acquire() as conn:
        for r in await conn.fetch("SELECT id::text, code, name, kind, status FROM core.companies"):
            c = Company(**dict(r))
            snap.companies[c.code] = c
            snap.companies_by_id[c.id] = c
        for r in await conn.fetch(
            """SELECT id::text, key, kind, provider, display_name, status, status_changed_at,
                      quota_reset_at, secret_ref, api_base, models, default_model, pricing,
                      limits, fallback_priority FROM llm.connections"""
        ):
            d = dict(r)
            d["models"] = tuple(_json(d["models"]))
            d["pricing"] = _json(d["pricing"])
            d["limits"] = _json(d["limits"])
            snap.connections[d["id"]] = Connection(**d)
        for r in await conn.fetch("SELECT key, transferable FROM llm.task_classes"):
            snap.task_classes[r["key"]] = TaskClass(r["key"], r["transferable"])
        for r in await conn.fetch(
            "SELECT scope_type, scope_ref, connection_id::text, model, effort FROM llm.assignments"
        ):
            snap.assignments[(r["scope_type"], r["scope_ref"])] = Assignment(
                r["connection_id"], r["model"], r["effort"]
            )
    async with db.scoped(snap.companies_by_id) as conn:
        for r in await conn.fetch(
            """SELECT id::text, company_id::text, scope_type, scope_ref, period, token_limit,
                      usd_limit, alert_level, alert_period_start
               FROM llm.budgets WHERE enabled"""
        ):
            d = dict(r)
            d["usd_limit"] = Decimal(d["usd_limit"]) if d["usd_limit"] is not None else None
            b = Budget(**d)
            snap.budgets.setdefault((b.scope_type, b.scope_ref), []).append(b)
    return snap


class Registry:
    def __init__(self, db: Database, ttl_s: float) -> None:
        self._db = db
        self._ttl = ttl_s
        self._snap: Snapshot | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> Snapshot:
        snap = self._snap
        if snap is not None and time.monotonic() - snap.loaded_at < self._ttl:
            return snap
        async with self._lock:
            if self._snap is None or time.monotonic() - self._snap.loaded_at >= self._ttl:
                self._snap = await load(self._db)
            return self._snap

    def invalidate(self) -> None:
        self._snap = None
