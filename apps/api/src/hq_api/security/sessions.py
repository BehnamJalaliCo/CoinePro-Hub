"""Owner sessions (contract §2): opaque tokens, stored as SHA-256 digests,
sliding 30 days, absolute 90 days, revocable, bound to the passkey/device."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.config import Settings
from hq_api.db import Tx
from hq_common.tokens import digest

COOKIE = "hq_session"


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def create(
    tx: Tx, s: Settings, *, passkey_id: UUID, client: str, device_name: str, ip_hash: str | None
) -> tuple[str, dict[str, Any]]:
    token = new_token()
    now = datetime.now(UTC)
    row = await tx.one(
        """INSERT INTO auth.sessions (token_sha256, passkey_id, client, device_name, ip_hash,
               expires_at, absolute_expires_at)
           VALUES (:h, :pk, :client, :name, :ip, :exp, :abs)
           RETURNING id, client, device_name, created_at, expires_at, absolute_expires_at""",
        h=digest(token),
        pk=passkey_id,
        client=client,
        name=device_name,
        ip=ip_hash,
        exp=now + timedelta(days=s.session_sliding_days),
        abs=now + timedelta(days=s.session_absolute_days),
    )
    return token, row


async def lookup(tx: Tx, s: Settings, token: str) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT s.id, s.passkey_id, s.client, s.device_name, s.created_at, s.last_used_at,
                  s.expires_at, s.absolute_expires_at
           FROM auth.sessions s JOIN auth.passkeys p ON p.id = s.passkey_id
           WHERE s.token_sha256 = :h AND s.revoked_at IS NULL AND p.revoked_at IS NULL
             AND s.expires_at > now() AND s.absolute_expires_at > now()""",
        h=digest(token),
    )
    if row is None:
        return None
    # Sliding expiry, written at most every 5 minutes.
    if row["last_used_at"] < datetime.now(UTC) - timedelta(minutes=5):
        await tx.exec(
            """UPDATE auth.sessions
               SET last_used_at = now(),
                   expires_at = least(now() + make_interval(days => :days), absolute_expires_at)
               WHERE id = :id""",
            id=row["id"],
            days=s.session_sliding_days,
        )
    return row


async def revoke(tx: Tx, session_id: UUID) -> None:
    await tx.exec(
        "UPDATE auth.sessions SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL",
        id=session_id,
    )
