"""Step-up check (contract §2 🔏): a single-use token, 120 s, bound to the
session, the action and the target, consumed in the action's transaction."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common.tokens import digest

HEADER = "x-step-up"


async def consume(tx: Tx, request: Request, who: Principal, action: str, target: str) -> UUID:
    if not who.is_owner:
        raise ApiError(403, "forbidden")
    token = request.headers.get(HEADER)
    if not token:
        raise ApiError(403, "step_up_required", f"step-up for {action} on {target}")
    row = await tx.first(
        """SELECT id, session_id, action, target, expires_at, used_at
           FROM auth.step_ups WHERE token_sha256 = :h FOR UPDATE""",
        h=digest(token),
    )
    if (
        row is None
        or row["session_id"] != who.session_id
        or row["action"] != action
        or row["target"] != target
        or row["used_at"] is not None
    ):
        raise ApiError(403, "step_up_invalid")
    alive = await tx.scalar("SELECT :exp > now()", exp=row["expires_at"])
    if not alive:
        raise ApiError(403, "step_up_invalid", "expired")
    await tx.exec("UPDATE auth.step_ups SET used_at = now() WHERE id = :id", id=row["id"])
    sid: UUID = row["id"]
    return sid
