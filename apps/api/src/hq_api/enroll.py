"""`python -m hq_api.enroll` (`make owner-enroll`): a one-time enrolment link.

Run by the OWNER in their own terminal on the server. The link (valid 15
minutes, single use) is printed to that terminal only: never logged, never
written to a file. It is also the recovery path if every device is lost.
Refuses without a terminal, and while login is off (no domain / HTTPS).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
from datetime import datetime
from typing import TextIO

from hq_api.config import Settings
from hq_api.db import Database
from hq_common import logs
from hq_common.tokens import digest

log = logging.getLogger("hq_api.enroll")


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def issue(db: Database, ttl_s: int) -> tuple[str, datetime]:
    """Store a fresh enrolment token (SHA-256 only) -> (token, expires_at)."""
    token = new_token()
    async with db.raw() as tx:
        expires_at: datetime = await tx.scalar(
            """INSERT INTO auth.enrolment_tokens (token_sha256, expires_at)
               VALUES (:h, now() + make_interval(secs => :ttl)) RETURNING expires_at""",
            h=digest(token),
            ttl=ttl_s,
        )
    return token, expires_at


def link(s: Settings, token: str) -> str:
    # The fragment (#) is never sent to a server by the browser.
    return f"{s.public_origin}/enroll#token={token}"


async def _issue_with(s: Settings) -> tuple[str, datetime]:
    db = Database.create(s, pool_size=1)
    try:
        return await issue(db, s.enrolment_ttl_s)
    finally:
        await db.close()


def run(s: Settings, out: TextIO, err: TextIO) -> int:
    if not out.isatty():
        err.write(
            "owner-enroll: run this in an interactive terminal (the link is shown only there)\n"
        )
        return 2
    if not s.login_configured:
        err.write(
            "owner-enroll: login is not configured yet. Set HQ_SITE_ADDRESS in infra/compose/.env "
            "to the hub's domain (HTTPS) and run `make up` first.\n"
        )
        return 3
    token, expires_at = asyncio.run(_issue_with(s))
    out.write(
        "One-time enrolment link (single use, valid until "
        f"{expires_at:%Y-%m-%d %H:%M} UTC). Open it on the device that will hold the passkey:\n\n"
        f"  {link(s, token)}\n\n"
    )
    out.flush()
    log.info("enrolment link issued", extra={"expires_at": expires_at.isoformat()})
    return 0


def main() -> None:
    s = Settings()
    logs.setup("owner-enroll", s.log_level)
    sys.exit(run(s, sys.stdout, sys.stderr))


if __name__ == "__main__":
    main()
