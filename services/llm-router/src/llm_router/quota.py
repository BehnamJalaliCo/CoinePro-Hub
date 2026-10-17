"""Quota Controller (prompt 05 §8, contract §16.5, OPERATING_MODEL §1.13): code,
no model. It keeps the subscription's quota state and throttles admission.

Sources, most reliable first:
  1. sdk_rate_limit_event  the CLI's rate-limit event of each run (status
                           allowed | allowed_warning | rejected, window,
                           utilization, reset) - claude-runtime passes it on
  2. quota_guard           a usage-limit error (the breaker's quota state)
  3. ledger_window         tokens on the subscription in the last 5 hours /
                           7 days against configured thresholds (0 = off)
State: ok | warning | limited. At `warning` P4 waits; at `limited` only P0-P2
run. Each change of state is persisted (llm.quota_status), published once on
hq.alerts.quota (the core turns it into budget.alert + a 🔵 notification) and
exposed through GET /api/v1/treasury/quota. A reset time that has passed
brings the state back to ok.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from llm_router.db import Database
from llm_router.events import Events

log = logging.getLogger("llm_router.quota")

QUOTA_SUBJECT = "hq.alerts.quota"
OK, WARNING, LIMITED = "ok", "warning", "limited"
RANK = {OK: 0, WARNING: 1, LIMITED: 2}
SDK_STATUS = {"allowed": OK, "allowed_warning": WARNING, "rejected": LIMITED}
# Priorities that wait in each state (P0 war room ... P4 background).
PAUSED = {OK: (), WARNING: (4,), LIMITED: (3, 4)}
DEFAULT_RETRY_S = 300
SDK_FRESH = timedelta(hours=6)  # an SDK observation older than this no longer decides


@dataclass(frozen=True)
class QuotaState:
    connection_id: str
    status: str = OK
    window: str | None = None
    utilization: Decimal | None = None
    resets_at: datetime | None = None
    source: str = "reset"
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def paused(self) -> tuple[int, ...]:
        return PAUSED[self.status]


@dataclass(frozen=True)
class Thresholds:
    """Ledger-window thresholds in tokens (input + output + cache); 0 = off."""

    warn_5h: int = 0
    limit_5h: int = 0
    warn_7d: int = 0
    limit_7d: int = 0

    @property
    def on(self) -> bool:
        return any((self.warn_5h, self.limit_5h, self.warn_7d, self.limit_7d))


class Throttled(Exception):
    def __init__(self, status: str, retry_after: int) -> None:
        super().__init__(status)
        self.status = status
        self.retry_after = retry_after


class QuotaController:
    def __init__(
        self,
        db: Database | None,
        events: Events | None,
        *,
        thresholds: Thresholds | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db = db
        self.events = events
        self.thresholds = thresholds or Thresholds()
        self.now = now
        self.states: dict[str, QuotaState] = {}

    # ------------------------------------------------------------- reading --
    async def load(self) -> int:
        """The persisted state (survives a restart)."""
        if self.db is None:
            return 0
        async with self.db.scoped(set()) as conn:
            rows = await conn.fetch(
                """SELECT connection_id::text AS cid, status, window_kind, utilization, resets_at,
                          source, observed_at, changed_at FROM llm.quota_status"""
            )
        for r in rows:
            self.states[r["cid"]] = QuotaState(
                connection_id=r["cid"],
                status=r["status"],
                window=r["window_kind"],
                utilization=r["utilization"],
                resets_at=r["resets_at"],
                source=r["source"],
                observed_at=r["observed_at"],
                changed_at=r["changed_at"],
            )
        return len(rows)

    def state(self, connection_id: str) -> QuotaState:
        s = self.states.get(connection_id) or QuotaState(connection_id)
        if s.status != OK and s.resets_at is not None and s.resets_at <= self.now():
            return replace(s, status=OK, source="reset")
        return s

    def check(self, connection_id: str, kind: str, priority: int) -> None:
        """Admission: raises Throttled when this priority waits in the current state."""
        if kind != "claude_subscription":
            return
        s = self.state(connection_id)
        if priority in s.paused():
            retry = DEFAULT_RETRY_S
            if s.resets_at is not None:
                retry = max(30, min(3600, int((s.resets_at - self.now()).total_seconds())))
            raise Throttled(s.status, retry)

    # ------------------------------------------------------------- writing --
    async def observe(
        self, connection_id: str, connection_key: str, rate_limit: dict[str, Any] | None
    ) -> QuotaState | None:
        """One run's rate-limit event (the SDK's own view of the subscription)."""
        if not rate_limit:
            return None
        status = SDK_STATUS.get(str(rate_limit.get("status")))
        if status is None:
            return None
        util = rate_limit.get("utilization")
        resets = rate_limit.get("resets_at")
        window = rate_limit.get("window")
        return await self._set(
            connection_id,
            connection_key,
            status,
            "sdk_rate_limit_event",
            window=str(window)[:40] if isinstance(window, str) else None,
            utilization=Decimal(str(util)).quantize(Decimal("0.0001"))
            if isinstance(util, int | float) and 0 <= util <= 1
            else None,
            resets_at=datetime.fromtimestamp(float(resets), UTC)
            if isinstance(resets, int | float) and resets > 0
            else None,
        )

    async def on_quota_guard(
        self, connection_id: str, connection_key: str, resets_at: datetime | None
    ) -> QuotaState | None:
        """A usage-limit error: the subscription is limited until its reset."""
        return await self._set(
            connection_id, connection_key, LIMITED, "quota_guard", resets_at=resets_at
        )

    async def scan(self, subscriptions: dict[str, str], companies: set[str]) -> list[QuotaState]:
        """Periodic: resets that passed, and the ledger windows (when configured).
        `subscriptions`: connection id -> key; `companies`: every company id (the
        subscription is shared by all of them)."""
        changed: list[QuotaState] = []
        for cid, key in subscriptions.items():
            cur = self.states.get(cid)
            if cur is not None and cur.status != OK and self.state(cid).status == OK:
                s = await self._set(cid, key, OK, "reset", force=True)
                if s is not None:
                    changed.append(s)
                continue
            if not self.thresholds.on or self.db is None:
                continue
            fresh_sdk = (
                cur is not None
                and cur.source == "sdk_rate_limit_event"
                and self.now() - cur.observed_at < SDK_FRESH
            )
            if fresh_sdk:
                continue  # the SDK's own figure decides while it is fresh
            level = await self._ledger_level(cid, companies)
            if cur is None or level != cur.status:
                s = await self._set(cid, key, level, "ledger_window", force=True)
                if s is not None:
                    changed.append(s)
        return changed

    async def _ledger_level(self, connection_id: str, companies: set[str]) -> str:
        assert self.db is not None
        now = self.now()
        async with self.db.scoped(companies) as conn:
            row = await conn.fetchrow(
                """SELECT COALESCE(sum(t) FILTER (WHERE started_at >= $2), 0) AS t5h,
                          COALESCE(sum(t), 0) AS t7d
                   FROM (SELECT started_at, input_tokens + output_tokens + cache_read_tokens
                                            + cache_write_tokens AS t
                         FROM llm.calls WHERE connection_id = $1::uuid AND started_at >= $3) c""",
                connection_id,
                now - timedelta(hours=5),
                now - timedelta(days=7),
            )
        t5h, t7d = int(row["t5h"]), int(row["t7d"])
        th = self.thresholds
        if (th.limit_5h and t5h >= th.limit_5h) or (th.limit_7d and t7d >= th.limit_7d):
            return LIMITED
        if (th.warn_5h and t5h >= th.warn_5h) or (th.warn_7d and t7d >= th.warn_7d):
            return WARNING
        return OK

    async def _set(
        self,
        connection_id: str,
        connection_key: str,
        status: str,
        source: str,
        *,
        window: str | None = None,
        utilization: Decimal | None = None,
        resets_at: datetime | None = None,
        force: bool = False,
    ) -> QuotaState | None:
        now = self.now()
        prev = self.state(connection_id)
        # A weaker source never lowers what a stronger one reported while it holds
        # (a quota-guard 'limited' stays until its reset even if a later event says ok).
        if (
            not force
            and prev.status == LIMITED
            and prev.source == "quota_guard"
            and source == "sdk_rate_limit_event"
            and RANK[status] < RANK[LIMITED]
            and (prev.resets_at is None or prev.resets_at > now)
        ):
            return None
        changed = status != prev.status
        new = QuotaState(
            connection_id=connection_id,
            status=status,
            window=window if window is not None else (prev.window if not changed else None),
            utilization=utilization,
            resets_at=resets_at if status != OK else None,
            source=source,
            observed_at=now,
            changed_at=now if changed else prev.changed_at,
        )
        self.states[connection_id] = new
        await self._persist(new)
        if changed:
            log.info(
                "subscription quota state changed",
                extra={
                    "connection": connection_key,
                    "from": prev.status,
                    "to": status,
                    "source": source,
                },
            )
            if self.events is not None:
                await self.events.publish(
                    QUOTA_SUBJECT,
                    {
                        "type": "quota",
                        "connection": connection_key,
                        "status": status,
                        "previous": prev.status,
                        "window": new.window,
                        "utilization": str(new.utilization)
                        if new.utilization is not None
                        else None,
                        "resets_at": new.resets_at.isoformat() if new.resets_at else None,
                        "source": source,
                        "paused_priorities": [f"P{p}" for p in new.paused()],
                        "at": now.isoformat(),
                    },
                )
        return new

    async def _persist(self, s: QuotaState) -> None:
        if self.db is None:
            return
        try:
            async with self.db.scoped(set()) as conn:
                await conn.execute(
                    """INSERT INTO llm.quota_status (connection_id, status, window_kind,
                           utilization, resets_at, source, observed_at, changed_at)
                       VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT (connection_id) DO UPDATE SET status = EXCLUDED.status,
                           window_kind = EXCLUDED.window_kind, utilization = EXCLUDED.utilization,
                           resets_at = EXCLUDED.resets_at, source = EXCLUDED.source,
                           observed_at = EXCLUDED.observed_at, changed_at = EXCLUDED.changed_at""",
                    s.connection_id,
                    s.status,
                    s.window,
                    s.utilization,
                    s.resets_at,
                    s.source,
                    s.observed_at,
                    s.changed_at,
                )
        except Exception:
            log.exception("quota state not saved", extra={"connection_id": s.connection_id})
