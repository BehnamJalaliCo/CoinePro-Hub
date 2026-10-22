"""The agents' internet on the api's side (prompt 07 §2.5-§2.8, contract §18.7):
the data guard, the limits, the service accounts and the log.

The egress service carries a request out; before it may, the api checks what
would leave (no employee code, internal reference, personal data or secret),
the run's and the company's limits, and the service account: the company may
use it, the owner gave it a secret, and a call other than GET/HEAD is one its
policy lists as non-committing. Anything else that commits is `needs_owner`.
"""

from __future__ import annotations

import base64
import binascii
import posixpath
import re
import unicodedata
from typing import Any
from urllib.parse import unquote, unquote_plus, urlsplit
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
# An employee code starts with its company's code (FX-TECH-MGR, HQ-ADV). A
# known code counts in any case (fx-tech-mgr); an unknown one when it is
# written as codes are: upper case, with a company's code first.
EMPLOYEE = re.compile(
    r"(?<![A-Za-z0-9-])([A-Za-z][A-Za-z0-9]{1,9})-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?(?![A-Za-z0-9])"
)
MAX_TEXT = 300_000

# A call's reservation (written by reserve before the request leaves; its
# `call_id` is its own id) counts until the call's own entries arrive (their
# `call_id` names it): a call whose answer is lost still counts, a call that
# was logged counts once. An aggregated row counts its `requests`.
SETTLED = """(l.call_id = l.id AND EXISTS (SELECT 1 FROM egress.log s
                                            WHERE s.call_id = l.id AND s.id <> l.id))"""
# "This run": its own rows; a call with no run (none should come: an agent's
# token names its run) counts the actor's run-less rows of the day as one
# run, so an empty run_id never switches the per-run caps off (7.1).
THIS_RUN = """(l.run_id IS NOT DISTINCT FROM CAST(:run AS uuid)
               AND (CAST(:run AS uuid) IS NOT NULL OR l.actor = :actor))"""
USAGE_SQL = f"""
    WITH day AS (
        SELECT (date_trunc('day', now() AT TIME ZONE tz) AT TIME ZONE tz) AS start,
               ((date_trunc('day', now() AT TIME ZONE tz) + interval '1 day') AT TIME ZONE tz) AS next
        FROM (SELECT COALESCE((SELECT timezone FROM owner.settings WHERE id = 1), 'Asia/Tehran') AS tz) t
    )
    SELECT COALESCE(sum(l.requests) FILTER (WHERE {THIS_RUN}), 0) AS run_requests,
           COALESCE(sum(l.bytes_in + l.bytes_out) FILTER (WHERE {THIS_RUN}), 0) AS run_bytes,
           COALESCE(sum(l.ms) FILTER (WHERE {THIS_RUN} AND l.kind = 'browse'), 0) AS run_browse_ms,
           COALESCE(sum(l.requests), 0) AS day_requests,
           COALESCE(sum(l.bytes_in + l.bytes_out), 0) AS day_bytes,
           (SELECT ceil(extract(epoch FROM d.next - now()))::int FROM day d) AS day_reset_s
    FROM egress.log l, day
    WHERE l.company_id = :co AND l.at >= day.start AND NOT {SETTLED}
"""  # noqa: S608 - composed from module constants; values are bound
# Retry-After of `egress_limit` (7.1): the company's day comes back at the
# owner's midnight; a run's own caps never do (an agent token lives an hour).
RUN_RETRY_AFTER_S = 3600
KINDS = {"web.search": "search", "web.browse": "browse"}
# Where an outgoing value can hide its data (contract §18.13, 7.1):
# percent-encoding (any depth), compatibility forms (full-width), other
# dashes, invisible marks, Persian and Arabic-Indic digits, base64 and hex.
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
DASHES = re.compile("[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")
INVISIBLE = re.compile("[\u00ad\u034f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
B64_RUN = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
HEX_RUN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){8,}(?![0-9A-Fa-f])")
MAX_RUNS = 200


def decoded(text: str) -> str:
    """`text` as its reader sees it: percent-decoded until it no longer
    changes, NFKC, every dash a hyphen, no invisible mark, Latin digits."""
    for _ in range(10):
        once = unquote_plus(text)
        if once == text:
            break
        text = once
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE.sub("", DASHES.sub("-", text))
    return text.translate(DIGITS)


def _b64(run: str) -> list[bytes]:
    raw = run.rstrip("=")
    padded = raw + "=" * (-len(raw) % 4)
    out: list[bytes] = []
    for alt in (None, b"-_"):
        try:
            out.append(base64.b64decode(padded, altchars=alt, validate=True))
        except (binascii.Error, ValueError):
            continue
    return out


def _hidden(text: str) -> list[str]:
    """The text inside base64 and hex runs of 16+ characters (readable only)."""
    blobs = [bytes.fromhex(m.group(0)) for m in HEX_RUN.finditer(text)][:MAX_RUNS]
    for m in list(B64_RUN.finditer(text))[:MAX_RUNS]:
        blobs += _b64(m.group(0))
    out: list[str] = []
    for blob in blobs:
        try:
            t = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if t and sum(ch.isprintable() or ch.isspace() for ch in t) >= 0.9 * len(t):
            out.append(decoded(t))
    return out


def internal_data(
    strings: list[str], company_codes: set[str], employee_codes: frozenset[str] = frozenset()
) -> str | None:
    """Why this must not leave the hub, or None. Checked as written and after
    decoding (contract §18.13): an encoded e-mail, ref or code is still one."""
    raw = "\n".join(s for s in strings if s)[:MAX_TEXT]
    if not raw:
        return None
    plain = decoded(raw)
    for text in (raw, plain, *_hidden(plain)):
        reason = _internal(text, company_codes, employee_codes)
        if reason:
            return reason
    return None


def _internal(text: str, company_codes: set[str], employee_codes: frozenset[str]) -> str | None:
    if scrub(text) != text:
        return "personal_or_secret_data"
    if INTERNAL_REF.search(text):
        return "internal_reference"
    for m in EMPLOYEE.finditer(text):
        code = m.group(0)
        if code.upper() in employee_codes or (code.isupper() and m.group(1) in company_codes):
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


def retry_after(settings: Any, u: dict[str, Any]) -> int:
    """Seconds until a refused call could go: the owner's next day when the
    company's day caps are spent, else (a run's own caps) an agent token's hour."""
    day_spent = (
        int(u["day_requests"]) >= settings.egress_day_requests
        or int(u["day_bytes"]) >= settings.egress_day_bytes
    )
    return max(1, int(u.get("day_reset_s") or 1)) if day_spent else RUN_RETRY_AFTER_S


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
    path = clean_path(parts.path or "/")
    if path is None:
        return False
    for rule in policy.get("allow") or []:
        if not isinstance(rule, dict):
            continue
        methods = [str(m).upper() for m in rule.get("methods") or [rule.get("method", "")]]
        prefix = str(rule.get("path_prefix") or "")
        if method in methods and prefix.startswith("/") and path.startswith(prefix):
            return True
    return False


def clean_path(raw: str) -> str | None:
    """The path as the server will see it, or None when it can be read two
    ways: a dot segment, an encoded dot, slash or backslash (at any depth of
    percent-encoding), a backslash or an empty segment
    (`/api/search/../../v1/charges` is sent as `/v1/charges`)."""
    path = raw
    for _ in range(5):
        low = path.lower()
        if any(x in low for x in ("%2e", "%2f", "%5c", "\\", "//")):
            return None
        if any(seg in (".", "..") for seg in path.split("/")):
            return None
        once = unquote(path)
        if once == path:
            break
        path = once
    else:
        return None
    if posixpath.normpath(path) not in (path, path.rstrip("/")):
        return None
    return unquote(raw)


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
        # The non-committing calls, for web.browse too: the browser refuses any
        # other call than GET/HEAD (contract §18.13, 7.1).
        "allow": [
            {
                "methods": [str(m).upper() for m in r.get("methods") or []][:5],
                "path_prefix": str(r.get("path_prefix") or "")[:500],
            }
            for r in policy.get("allow") or []
            if isinstance(r, dict)
        ][:50],
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
    call_id: UUID | str | None = None,
) -> int:
    n = 0
    for e in entries:
        await tx.exec(
            """INSERT INTO egress.log (company_id, actor, run_id, tool, kind, class, method, host, status,
                   bytes_in, bytes_out, ms, blocked_reason, requests, call_id)
               VALUES (:co, :actor, CAST(:run AS uuid), :tool, :kind, :cls, :method, :host, :status,
                   :bi, :bo, :ms, :br, :n, CAST(:call AS uuid))""",
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
            n=e.get("requests", 1),
            call=str(call_id) if call_id else None,
        )
        n += 1
    return n


async def reserve_row(
    tx: Tx, *, company_id: UUID, actor: str, run_id: str | None, entry: dict[str, Any]
) -> str:
    """The call's row, written before its request leaves (call_id = its id)."""
    row = await tx.one(
        """INSERT INTO egress.log (id, call_id, company_id, actor, run_id, tool, kind, class, method, host)
           SELECT x.id, x.id, :co, :actor, CAST(:run AS uuid), :tool, :kind, :cls, :method, :host
           FROM (SELECT gen_random_uuid() AS id) x
           RETURNING id""",
        co=company_id,
        actor=actor[:60],
        run=run_id,
        tool=entry["tool"],
        kind=entry["kind"],
        cls=entry["class"],
        method=entry["method"],
        host=entry["host"],
    )
    return str(row["id"])


async def own_reservation(tx: Tx, reservation: UUID, *, actor: str, run_id: str | None) -> bool:
    """`reservation` is an open call row of this agent's run (RLS: its company)."""
    found = await tx.all(
        f"""SELECT 1 FROM egress.log l
            WHERE l.id = :r AND l.call_id = l.id AND l.actor = :actor
              AND l.run_id IS NOT DISTINCT FROM CAST(:run AS uuid) AND NOT {SETTLED}""",  # noqa: S608 - module constants
        r=reservation,
        actor=actor[:60],
        run=run_id,
    )
    return bool(found)


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
# A settled reservation is not listed: its call's own entries are.
LIVE = "NOT " + SETTLED
