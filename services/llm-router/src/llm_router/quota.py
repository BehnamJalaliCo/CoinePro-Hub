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
exposed through GET /api/v1/treasury/quota.

Each window the CLI reports (five_hour, seven_day, ...), the quota guard and
the ledger windows keep their own state; the connection's state is the worst
of them that still holds, so one window being fine never lifts another's
limit. A non-ok state always ends (prompt 5.1 §2.4): at the reset time the
provider reported, else at the breaker's retry time (a usage-limit error), else
HOLD after it was seen. The end is persisted with it, so a restart keeps it.
"""

from __future__ import annotations

import json
import logging
import re
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
SDK, GUARD, LEDGER = "sdk_rate_limit_event", "quota_guard", "ledger_window"
# Priorities that wait in each state (P0 war room ... P4 background).
PAUSED = {OK: (), WARNING: (4,), LIMITED: (3, 4)}
DEFAULT_RETRY_S = 300
SDK_FRESH = timedelta(hours=6)  # an SDK observation older than this no longer decides
HOLD = timedelta(hours=5)  # how long a state whose end is unknown holds
WINDOW = re.compile(r"[a-z0-9_]{2,40}")  # the same rule as llm.quota_status.window_kind
MAX_WINDOWS = 16


def valid_window(window: Any) -> bool:
    return isinstance(window, str) and WINDOW.fullmatch(window) is not None


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
    # resets_at is the hold this controller chose (the breaker's retry time or
    # HOLD), not a reset time the provider reported.
    estimated: bool = False

    def paused(self) -> tuple[int, ...]:
        return PAUSED[self.status]

    def holds(self, now: datetime) -> bool:
        """Not ok and not lapsed yet (a non-ok state always carries resets_at)."""
        return self.status != OK and self.resets_at is not None and self.resets_at > now

    def as_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "window": self.window,
            "utilization": str(self.utilization) if self.utilization is not None else None,
            "resets_at": self.resets_at.isoformat() if self.resets_at else None,
            "source": self.source,
            "observed_at": self.observed_at.isoformat(),
            "estimated": self.estimated,
        }

    @classmethod
    def from_json(cls, connection_id: str, d: dict[str, Any]) -> QuotaState:
        def at(v: Any) -> datetime | None:
            return datetime.fromisoformat(v) if isinstance(v, str) else None

        observed = at(d.get("observed_at")) or datetime.now(UTC)
        return cls(
            connection_id=connection_id,
            status=d["status"] if d.get("status") in RANK else OK,
            window=d["window"] if valid_window(d.get("window")) else None,
            utilization=Decimal(d["utilization"]) if d.get("utilization") else None,
            resets_at=at(d.get("resets_at")),
            source=str(d.get("source") or "reset"),
            observed_at=observed,
            changed_at=observed,
            estimated=bool(d.get("estimated")),
        )


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
        # The state last saved and announced, per connection ...
        self.states: dict[str, QuotaState] = {}
        # ... and what it is made of: connection -> window (or source) -> state.
        self.windows: dict[str, dict[str, QuotaState]] = {}

    # ------------------------------------------------------------- reading --
    async def load(self) -> int:
        """The persisted state (survives a restart)."""
        if self.db is None:
            return 0
        async with self.db.scoped(set()) as conn:
            rows = await conn.fetch(
                """SELECT connection_id::text AS cid, status, window_kind, utilization, resets_at,
                          source, observed_at, changed_at, resets_estimated, windows
                   FROM llm.quota_status"""
            )
        for r in rows:
            cid = r["cid"]
            s = QuotaState(
                connection_id=cid,
                status=r["status"],
                window=r["window_kind"],
                utilization=r["utilization"],
                resets_at=r["resets_at"],
                source=r["source"],
                observed_at=r["observed_at"],
                changed_at=r["changed_at"],
                estimated=r["resets_estimated"],
            )
            self.states[cid] = s
            saved = json.loads(r["windows"]) if isinstance(r["windows"], str) else r["windows"]
            windows = {k: QuotaState.from_json(cid, v) for k, v in (saved or {}).items()}
            if not windows and s.status != OK:  # saved before windows were kept
                windows[_key(s.source, s.window)] = s
            self.windows[cid] = windows
        return len(rows)

    def state(self, connection_id: str) -> QuotaState:
        """The worst window that still holds; ok when none does."""
        now = self.now()
        cur = self.states.get(connection_id) or QuotaState(connection_id)
        windows = self.windows.get(connection_id, {})
        holding = [w for w in windows.values() if w.holds(now)]
        if holding:
            top = max(holding, key=lambda w: (RANK[w.status], w.resets_at or now))
            return replace(
                top,
                observed_at=max(w.observed_at for w in windows.values()),
                changed_at=cur.changed_at if top.status == cur.status else now,
            )
        latest = max(windows.values(), key=lambda w: w.observed_at, default=None)
        if latest is not None and latest.status == OK:
            return replace(latest, window=None, changed_at=cur.changed_at)
        if cur.status == OK:
            return cur
        return QuotaState(
            connection_id, OK, source="reset", observed_at=cur.observed_at, changed_at=now
        )

    def check(self, connection_id: str, kind: str, priority: int) -> None:
        """Admission: raises Throttled when this priority waits in the current state."""
        if kind != "claude_subscription":
            return
        s = self.state(connection_id)
        if priority in s.paused():
            retry = DEFAULT_RETRY_S
            if s.resets_at is not None:
                left = int((s.resets_at - self.now()).total_seconds())
                # An estimated end is only an upper bound: look again soon.
                retry = max(30, min(DEFAULT_RETRY_S if s.estimated else 3600, left))
            raise Throttled(s.status, retry)

    # ------------------------------------------------------------- writing --
    async def observe(
        self, connection_id: str, connection_key: str, rate_limit: dict[str, Any] | None
    ) -> QuotaState | None:
        """One run's rate-limit event (the SDK's own view of the subscription).
        Returns the connection's state when this event changed it, else None."""
        if not rate_limit:
            return None
        status = SDK_STATUS.get(str(rate_limit.get("status")))
        if status is None:
            return None
        util = rate_limit.get("utilization")
        resets = rate_limit.get("resets_at")
        window = rate_limit.get("window")
        if window is not None and not valid_window(window):
            # Refused here, not by the table's CHECK (which would lose the whole row).
            log.warning(
                "quota window refused",
                extra={"connection": connection_key, "window": repr(window)[:60]},
            )
            window = None
        return await self._observe(
            connection_id,
            connection_key,
            QuotaState(
                connection_id,
                status,
                window=window,
                utilization=Decimal(str(util)).quantize(Decimal("0.0001"))
                if isinstance(util, int | float) and 0 <= util <= 1
                else None,
                resets_at=datetime.fromtimestamp(float(resets), UTC)
                if isinstance(resets, int | float) and resets > 0
                else None,
                source=SDK,
            ),
        )

    async def on_quota_guard(
        self,
        connection_id: str,
        connection_key: str,
        resets_at: datetime | None,
        *,
        fallback: datetime | None = None,
    ) -> QuotaState | None:
        """A usage-limit error: the subscription is limited until its reset, or,
        when none could be read (every billing_error), until `fallback` (the
        breaker's retry time) or HOLD. Returns the state when it changed."""
        return await self._observe(
            connection_id,
            connection_key,
            QuotaState(connection_id, LIMITED, resets_at=resets_at, source=GUARD),
            fallback=fallback,
        )

    async def scan(self, subscriptions: dict[str, str], companies: set[str]) -> list[QuotaState]:
        """Periodic: holds that lapsed, and the ledger windows (when configured).
        `subscriptions`: connection id -> key; `companies`: every company id (the
        subscription is shared by all of them). Returns the states it saved."""
        changed: list[QuotaState] = []
        for cid, key in subscriptions.items():
            cur = self.states.get(cid)
            first = False
            if self.thresholds.on and self.db is not None:
                windows = self.windows.setdefault(cid, {})
                if self._sdk_fresh(cid):
                    windows.pop(LEDGER, None)  # the SDK's own figure decides while it is fresh
                else:
                    level = await self._ledger_level(cid, companies)
                    now = self.now()
                    windows[LEDGER] = QuotaState(
                        cid,
                        level,
                        resets_at=now + HOLD if level != OK else None,
                        source=LEDGER,
                        observed_at=now,
                        estimated=level != OK,
                    )
                    first = cur is None
            new = self.state(cid)
            if first or (cur is not None and new.status != cur.status):
                changed.append(await self._commit(cid, key, new))
        return changed

    def _sdk_fresh(self, connection_id: str) -> bool:
        now = self.now()
        return any(
            w.source == SDK and now - w.observed_at < SDK_FRESH
            for w in self.windows.get(connection_id, {}).values()
        )

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

    async def _observe(
        self,
        connection_id: str,
        connection_key: str,
        seen: QuotaState,
        *,
        fallback: datetime | None = None,
    ) -> QuotaState | None:
        """One window's new state, then the connection's state from all of them."""
        now = self.now()
        seen = replace(seen, observed_at=now, changed_at=now)
        if seen.status == OK:
            seen = replace(seen, resets_at=None, estimated=False)
        elif seen.resets_at is None or seen.resets_at <= now:
            # The end is unknown: never "for good".
            end = fallback if fallback is not None and fallback > now else now + HOLD
            seen = replace(seen, resets_at=end, estimated=True)
        windows = self.windows.setdefault(connection_id, {})
        windows[_key(seen.source, seen.window)] = seen
        prev = self.states.get(connection_id) or QuotaState(connection_id)
        new = await self._commit(connection_id, connection_key, self.state(connection_id))
        return new if new.status != prev.status else None

    async def _commit(self, connection_id: str, connection_key: str, new: QuotaState) -> QuotaState:
        """Save the connection's state (and its windows); announce a change once."""
        now = self.now()
        prev = self.states.get(connection_id) or QuotaState(connection_id)
        changed = new.status != prev.status
        new = replace(new, changed_at=now if changed else prev.changed_at)
        self.states[connection_id] = new
        self._prune(connection_id, now)
        await self._persist(new, self.windows.get(connection_id, {}))
        if changed:
            log.info(
                "subscription quota state changed",
                extra={
                    "connection": connection_key,
                    "from": prev.status,
                    "to": new.status,
                    "source": new.source,
                },
            )
            if self.events is not None:
                await self.events.publish(
                    QUOTA_SUBJECT,
                    {
                        "type": "quota",
                        "connection": connection_key,
                        "status": new.status,
                        "previous": prev.status,
                        "window": new.window,
                        "utilization": str(new.utilization)
                        if new.utilization is not None
                        else None,
                        "resets_at": new.resets_at.isoformat() if new.resets_at else None,
                        "source": new.source,
                        "paused_priorities": [f"P{p}" for p in new.paused()],
                        "at": now.isoformat(),
                    },
                )
        return new

    def _prune(self, connection_id: str, now: datetime) -> None:
        """Windows that no longer hold and are older than SDK_FRESH tell nothing;
        at most MAX_WINDOWS are kept (the most recent)."""
        windows = self.windows.get(connection_id, {})
        keep = {k: w for k, w in windows.items() if w.holds(now) or now - w.observed_at < SDK_FRESH}
        if len(keep) > MAX_WINDOWS:
            keep = dict(
                sorted(keep.items(), key=lambda kv: kv[1].observed_at, reverse=True)[:MAX_WINDOWS]
            )
        self.windows[connection_id] = keep

    async def _persist(self, s: QuotaState, windows: dict[str, QuotaState]) -> None:
        if self.db is None:
            return
        try:
            async with self.db.scoped(set()) as conn:
                await conn.execute(
                    """INSERT INTO llm.quota_status (connection_id, status, window_kind,
                           utilization, resets_at, source, observed_at, changed_at,
                           resets_estimated, windows)
                       VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                       ON CONFLICT (connection_id) DO UPDATE SET status = EXCLUDED.status,
                           window_kind = EXCLUDED.window_kind, utilization = EXCLUDED.utilization,
                           resets_at = EXCLUDED.resets_at, source = EXCLUDED.source,
                           observed_at = EXCLUDED.observed_at, changed_at = EXCLUDED.changed_at,
                           resets_estimated = EXCLUDED.resets_estimated,
                           windows = EXCLUDED.windows""",
                    s.connection_id,
                    s.status,
                    s.window if s.status != OK else None,
                    s.utilization,
                    s.resets_at if s.status != OK else None,
                    s.source,
                    s.observed_at,
                    s.changed_at,
                    s.estimated and s.status != OK,
                    json.dumps({k: w.as_json() for k, w in windows.items()}),
                )
        except Exception:
            log.exception("quota state not saved", extra={"connection_id": s.connection_id})


def _key(source: str, window: str | None) -> str:
    """Where a state is kept: the SDK by its window, the guard and the ledger apart."""
    if source == SDK:
        return f"sdk:{window}" if window else "sdk"
    return source
