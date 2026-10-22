"""The launch gate (owner decision 2026-10-22, docs/OWNER_REQUESTS_2026-10-17.md
round 8 #8): nothing that runs on its own calls a model or an outside service
until the owner launches the hub. Today the holding kill switch is engaged.

Every prompt 10 job that wakes by itself (a Temporal schedule, a worker
activity, a protocol, a pull, a sweep, a lifecycle message, an agent run it
would start) asks this module first and skips cleanly while a lock is set:
no model call, no external call, no new run, and a row or result that says
`skipped` with the lock.

    lock = await gate.automation_lock(tx, company_id)   # None | "holding" | "company" | "deploy_freeze"
    if lock:
        return gate.skipped(lock)

`holding_lock` is the holding's own state (its kill switch or deploy freeze);
`automation_lock` adds the company's (a company kill switch or freeze stops
that company's pulls and sends too). Both read control.lock_state(), the
same function the agent runner and the router use. A rule-only job that
touches no model and no outside service (the support retention sweep) does
not need the gate; it says so where it runs.
"""

from __future__ import annotations

from typing import Any

from hq_api.db import Tx

HOLDING = "holding"


class Locked(Exception):
    """Raised by require_unlocked; `lock` is the control.lock_state() value."""

    def __init__(self, lock: str) -> None:
        super().__init__(f"locked: {lock}")
        self.lock = lock


async def holding_lock(tx: Tx) -> str | None:
    """control.lock_state() of the holding company: "holding" while its kill
    switch is engaged, "deploy_freeze" during its freeze, else None."""
    state: str | None = await tx.scalar(
        """SELECT control.lock_state(c.id) FROM core.companies c
           WHERE c.kind = 'holding' ORDER BY c.created_at LIMIT 1"""
    )
    return state


async def automation_lock(tx: Tx, company_id: Any | None = None) -> str | None:
    """The holding's lock first, then the company's (kill switch, freeze)."""
    lock = await holding_lock(tx)
    if lock is not None or company_id is None:
        return lock
    state: str | None = await tx.scalar("SELECT control.lock_state(:co)", co=company_id)
    return state


async def require_unlocked(tx: Tx, company_id: Any | None = None) -> None:
    lock = await automation_lock(tx, company_id)
    if lock is not None:
        raise Locked(lock)


REASONS = {
    "holding": "holding_locked",
    "company": "company_locked",
    "deploy_freeze": "deploy_freeze",
}


def skipped(lock: str, **extra: Any) -> dict[str, Any]:
    """The result of a job that did nothing because of a lock:
    {"skipped": true, "reason": "holding_locked" | "company_locked" | "deploy_freeze"}."""
    return {"skipped": True, "reason": REASONS.get(lock, lock), **extra}
