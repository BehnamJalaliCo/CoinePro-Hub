"""Step-up check (contract §2 🔏): a single-use token, 120 s, bound to the
session, the action and the target, consumed in the action's transaction."""

from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import Request

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common.tokens import digest

HEADER = "x-step-up"

# The owner, 2026-11-05 («بروکراسی خیلی شدیدی به کار رفته»): routine actions need no fingerprint. The plan's
# rule (PLAN_2026-11-02 v3 §1, Claude Duet's line): reading, drafting, preparing and running the holding
# are free; sending out, spending, signing away, deleting and opening access keep the passkey. These are
# the routine ones: their options call answers with the token itself (routes/auth.step_up_options).
LIGHT = frozenset(
    {
        "academy.approve",
        "archive.seal",
        "charter.seal",
        "company.archive",
        "company.brand",
        "company.create",
        "connection.logout",
        "connection.update",
        "department.create",
        "department.mandate",
        "growth.template",
        "hiring.start",
        "meetings.settings",
        "oversight.order",
        "oversight.release",
        # ⟨1.22⟩ §40.2-§40.3 a playbook sealed into a working group, or retired: running the
        # holding, nothing sent out or spent
        "playbook.retire",
        "playbook.seal",
        "rule.seal",
        "sites.update",
        "skill.activate",
        "substitute.web_logout",
        "support.kb",
        "voice.activate",
    }
)


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


async def body_target(request: Request) -> str:
    """Step-up target for a whole-body change (PUT /assignments, /budgets):
    the SHA-256 (hex) of the exact request body, so the signature covers what
    is changed, not just "something" (contract §10 v1.1)."""
    return hashlib.sha256(await request.body()).hexdigest()
