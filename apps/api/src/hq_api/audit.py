"""Audit rows (contract §8): one per mutation, in the same transaction.

The chain (seq, prev_hash, hash) is computed by the database trigger. Only
references and a short summary are written, never a body or a secret.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.principal import Principal

SYSTEM = Principal(kind="service", code="system", role="system")


async def record(
    tx: Tx,
    actor: Principal,
    *,
    company_id: UUID,
    action: str,
    action_class: str,
    target_kind: str,
    target_ref: str,
    summary: str = "",
    step_up: bool = False,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> None:
    actor_kind = "system" if actor is SYSTEM else actor.kind
    await tx.exec(
        """INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action,
               action_class, target_kind, target_ref, request_id, ip_hash, step_up, summary)
           VALUES (:ak, :ac, :pk, :co, :action, :cls, :tk, :tr, :rid, :ip, :su, :summary)""",
        ak=actor_kind,
        ac=actor.code,
        pk=actor_kind,
        co=company_id,
        action=action,
        cls=action_class,
        tk=target_kind,
        tr=target_ref[:200],
        rid=request_id,
        ip=ip_hash,
        su=step_up,
        summary=summary[:500],
    )


async def verify(tx: Tx) -> dict[str, Any]:
    return await tx.one("SELECT ok, checked, first_bad_seq FROM audit.verify_chain()")
