"""The agents' internet on the api's side (prompt 07 §2.5-§2.8, contract §18.7):
the data guard, the limits, the service accounts and the log.

The egress service carries a request out; before it may, the api checks what
would leave (no employee code, internal reference, personal data or secret),
the run's and the company's limits, and the service account: the company may
use it, the owner gave it a secret, and a call other than GET/HEAD is one its
policy lists as non-committing. Anything else that commits is `needs_owner`.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common.redact import scrub

READ_METHODS = ("GET", "HEAD")
# Refs of the hub's own records (work, decisions, outputs; incidents, threads,
# sessions, foundings, plans, stories): never sent to a search engine or a site.
INTERNAL_REF = re.compile(
    r"(?<![A-Za-z0-9])(?:[WDO]-\d{6,}|(?:I|N|P|S|C|AP|PV|ST)-\d{4,6})(?![A-Za-z0-9])"
)
# An employee code starts with its company's code (FX-TECH-MGR, HQ-ADV).
EMPLOYEE = re.compile(
    r"(?<![A-Za-z0-9-])([A-Z][A-Z0-9]{1,9})-[A-Z0-9]+(?:-[A-Z0-9]+)?(?![A-Za-z0-9])"
)
MAX_TEXT = 300_000

USAGE_SQL = """
    WITH day AS (
        SELECT (date_trunc('day', now() AT TIME ZONE tz) AT TIME ZONE tz) AS start
        FROM (SELECT COALESCE((SELECT timezone FROM owner.settings WHERE id = 1), 'Asia/Tehran') AS tz) t
    )
    SELECT count(*) FILTER (WHERE run_id = CAST(:run AS uuid)) AS run_requests,
           COALESCE(sum(bytes_in + bytes_out) FILTER (WHERE run_id = CAST(:run AS uuid)), 0) AS run_bytes,
           COALESCE(sum(ms) FILTER (WHERE run_id = CAST(:run AS uuid) AND kind = 'browse'), 0) AS run_browse_ms,
           count(*) AS day_requests,
           COALESCE(sum(bytes_in + bytes_out), 0) AS day_bytes
    FROM egress.log, day
    WHERE company_id = :co AND at >= day.start
"""


def internal_data(strings: list[str], company_codes: set[str]) -> str | None:
    """Why this must not leave the hub, or None."""
    text = "\n".join(s for s in strings if s)[:MAX_TEXT]
    if not text:
        return None
    if scrub(text) != text:
        return "personal_or_secret_data"
    if INTERNAL_REF.search(text):
        return "internal_reference"
    if any(m.group(1) in company_codes for m in EMPLOYEE.finditer(text)):
        return "employee_code"
    return None


def limits_left(settings: Any, u: dict[str, Any]) -> dict[str, int]:
    return {
        "requests": min(
            settings.egress_run_requests - int(u["run_requests"]),
            settings.egress_day_requests - int(u["day_requests"]),
        ),
        "bytes": min(
            settings.egress_run_bytes - int(u["run_bytes"]),
            settings.egress_day_bytes - int(u["day_bytes"]),
        ),
        "browser_s": settings.egress_run_browser_s - int(u["run_browse_ms"]) // 1000,
    }


def covers(site: str, host: str) -> bool:
    site = site.lower().rstrip(".")
    return host == site or host.endswith("." + site)


def non_committing(policy: dict[str, Any], site: str, method: str, url: str | None) -> bool:
    """A call other than GET/HEAD is allowed only to the account's own host,
    on a (method, path prefix) the owner listed as non-committing."""
    if not url:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if not covers(site, host):
        return False
    path = parts.path or "/"
    for rule in policy.get("allow") or []:
        if not isinstance(rule, dict):
            continue
        methods = [str(m).upper() for m in rule.get("methods") or [rule.get("method", "")]]
        prefix = str(rule.get("path_prefix") or "")
        if method in methods and prefix.startswith("/") and path.startswith(prefix):
            return True
    return False


async def account(tx: Tx, bao: Any, key: str, company: str) -> dict[str, Any]:
    """The account for one call, with its secret (OpenBao kv/tools/accounts/<key>)."""
    row = await tx.one(
        "SELECT id, key, site, companies, policy FROM tools.accounts WHERE key = :k",
        k=key,
        not_found="not_found",
    )
    if row["companies"] is not None and company not in row["companies"]:
        raise ApiError(403, "policy_denied", "account_not_for_this_company")
    secret = await read_secret(bao, key)
    if not secret:
        raise ApiError(409, "account_not_configured")
    await tx.exec("UPDATE tools.accounts SET last_used_at = now() WHERE id = :id", id=row["id"])
    policy = row["policy"] or {}
    return {
        "key": row["key"],
        "site": row["site"],
        "secret": secret,
        "inject": policy.get("inject") or {"kind": "bearer"},
        "browse": policy.get("browse"),
        "ports": [int(p) for p in policy.get("ports") or [] if str(p).isdigit()][:5],
        "_policy": policy,
    }


async def read_secret(bao: Any, key: str) -> str | None:
    if bao is None:
        return None
    from hq_common.openbao import OpenBaoError

    try:
        data = await bao.read_kv(f"tools/accounts/{key}")
    except OpenBaoError:
        return None
    value = data.get("secret") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


async def has_secret(bao: Any, key: str) -> bool:
    return bool(await read_secret(bao, key))


async def record(
    tx: Tx,
    *,
    company_id: UUID,
    actor: str,
    run_id: str | None,
    entries: list[dict[str, Any]],
) -> int:
    n = 0
    for e in entries:
        await tx.exec(
            """INSERT INTO egress.log (company_id, actor, run_id, tool, kind, class, method, host, status,
                   bytes_in, bytes_out, ms, blocked_reason)
               VALUES (:co, :actor, CAST(:run AS uuid), :tool, :kind, :cls, :method, :host, :status,
                   :bi, :bo, :ms, :br)""",
            co=company_id,
            actor=actor[:60],
            run=run_id,
            tool=e["tool"],
            kind=e["kind"],
            cls=e["class"],
            method=e["method"],
            host=e["host"],
            status=e.get("status"),
            bi=e.get("bytes_in", 0),
            bo=e.get("bytes_out", 0),
            ms=e.get("ms", 0),
            br=e.get("blocked_reason"),
        )
        n += 1
    return n


def host_of(url: str | None) -> str:
    if not url:
        return "-"
    try:
        return (urlsplit(url).hostname or "-")[:255]
    except ValueError:
        return "-"


ENTRY_SQL = """
    SELECT l.id, l.at, c.code AS company, l.actor, l.run_id, l.tool, l.method, l.host, l.status,
           l.bytes_in, l.bytes_out, l.ms, l.blocked_reason, l.class, l.kind
    FROM egress.log l JOIN core.companies c ON c.id = l.company_id
"""
