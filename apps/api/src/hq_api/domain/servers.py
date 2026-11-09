"""Company server runners (contract §26 ⟨1.8⟩, prompt 17), in the caller's
transaction. Nothing here talks to a company server: each server's own
`hq-runner` long-polls the hub over HTTPS (routes/servers.py) and the hub
answers with jobs; the hub never connects into a company server.

  servers     infra.servers: provisioned (a plan) or attached (a runner);
              state pending -> online <-> offline, revoked at detach
  pairings    the device-authorisation flow: the runner's device code (its
              sha256 only), the short user code the owner approves (🔏)
  runners     one credential per server (its sha256 only), rotated every
              24 h, revoked at detach (the runner stops on its next poll)
  jobs        one unit of work for one server (§26.2): queued -> running ->
              done | failed | cancelled, or awaiting_seal first for a
              destructive command the policy lists (§26.3: a
              `server_destructive` card, 🔏 server.destructive)
  events      the job's stdout / stderr / session events, masked before they
              are stored; the whole (masked) transcript goes to object
              storage when the job ends, owner-readable
  network     `netcheck` jobs: each runner measures the hub and every other
              attached server's private address; the latest result per link

Control (§26.3): a company's kill switch (or the holding's) refuses new jobs
(423 company_locked) and cancels its queued and running ones (the runner sees
the cancel on its next poll and kills the process group); a deploy freeze
refuses the jobs the hub classes as deploys (423 deploy_frozen). Every job,
and every command inside a `claude` job, is an Audit row (actor, server,
masked command, exit code, duration, digest).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import gzip
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import oversight_checks as C
from hq_api.domain.server_classify import (
    CATEGORIES as CATEGORIES,
)
from hq_api.domain.server_classify import (
    classify_detail as classify_detail,
)
from hq_api.domain.server_classify import (
    classify_path,
)
from hq_api.domain.server_classify import (
    is_deploy as is_deploy,
)
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor
from hq_common.redact import mask_secrets, scrub

log = logging.getLogger("hq_api.servers")

JOB_KINDS = ("map", "exec", "read", "write", "claude", "publish", "netcheck", "ledger")
OPEN = ("queued", "running", "awaiting_seal")
FINAL = ("done", "failed", "cancelled")
PAIR_TTL_S = 900
PAIR_INTERVAL_S = 5
ONLINE_S = 90  # a runner long-polls at most 30 s at a time: three missed polls = offline
ROTATE_GRACE_S = 600  # the previous credential still works this long after a rotation
DISPATCH_GRACE_S = 120  # beyond the job's own timeout, before the hub fails it
# ⟨1.10.1⟩ the runner (0.2.0) sends an event's text up to 64 000 characters and
# streams 10 MB of a job's output; the hub keeps all of it, and what came past
# the stream arrives whole with the result (`output_overflow`, a gzip artifact)
MAX_EVENT_TEXT = 192 * 1024
MAX_JOB_EVENTS_BYTES = 24 * 1024 * 1024  # what the hub keeps of one job's live output
INLINE_ANSWER = 256_000  # a claude job's answer kept inline in the result (the rest: the file)
OVERFLOW_TEXT_MAX = (
    64 * 1024 * 1024
)  # an artifact masked and stored as text up to this, else as gzip
MAX_READ_INLINE = 64 * 1024  # a read's content kept inline in the result (the rest: the file)
TOKEN_PREFIX = "hqr1_"  # noqa: S105 - the prefix of a runner credential, not one
USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
# ⟨2026-11-08⟩ the owner: «۱۲ مسیر قطع است» was port 22 alone — SSH between two companies' servers, closed by their
# firewalls on purpose and never a path of the holding's work (runners and every request go over HTTPS through the hub).
# It is no longer measured nor shown; a link stored for it before is left out of the map and of the reasons.
NETCHECK_SERVER_PORTS = (443, 80)
NETCHECK_HUB_PORT = 443
# ⟨1.24⟩ §42.2: a round trip (the runner's to the hub, a measured link) at least this long is slow
SLOW_MS = 300.0
LINK_WINDOW_S = 60  # at most one network.link per link in this window (but during an owner's check)
REASON_FA = {
    "no_poll": "runner این سرور دیگر به هاب سر نمیزند؛ هنوز معلوم نیست چرا",
    "runner_stopped": "سرور روشن است و در دسترس، ولی runner روی آن ایستاده است",
    "server_unreachable": "هیچ سروری به این سرور نمیرسد؛ خاموش است یا از شبکه جدا شده",
    "revoked": "این سرور از هلدینگ جدا شده است",
    "fallback_public": "شبکه‌ی خصوصی جواب نمیدهد؛ از راه اینترنت وصل است",
    "slow": "ارتباط این سرور با هاب کند است",
}
SERVICE = Principal(kind="service", code="servers", role="service")
TOOL_OF = {k: f"server.{k}" for k in JOB_KINDS}
SESSION_TYPES = (
    "message", "progress", "command", "file_change", "approval_request", "approval_result",
    "state", "error",
)  # fmt: skip
CATEGORY_FA = {
    "db_drop": "پاک کردن یا خالی کردن دیتابیس",
    "volume_delete": "پاک کردن volume داده",
    "backup_delete": "پاک کردن پشتیبان",
    "disk_wipe": "پاک کردن یا پارتیشن کردن دیسک",
    "access_change": "تغییر SSH، کاربرها یا فایروال همین سرور",
    "server_delete": "حذف سرور",
}
KIND_FA = {
    "map": "نقشه‌ی سرور",
    "exec": "فرمان",
    "read": "خواندن فایل",
    "write": "نوشتن فایل",
    "claude": "Claude Code",
    "publish": "انتشار",
    "netcheck": "سنجش شبکه",
    "ledger": "خواندن دفتر پرداخت",  # ⟨1.15⟩ §33.2 (runner 0.3.0)
}


# ------------------------------------------------------------------ helpers --
def hub_ip() -> str:
    """The hub's private address (contract §26.1a), the target of every netcheck."""
    return os.environ.get("HQ_HUB_PRIVATE_IP", "10.10.1.4").strip() or "10.10.1.4"


def now() -> datetime:
    return datetime.now(UTC)


def mask(text: str | None) -> str:
    """Secrets masked by name and pattern (§26.3); personal data kept for the owner."""
    return scrub(text or "", secrets_only=True)


def mask_value(value: Any) -> Any:
    return mask_secrets(value)


def digest_of(value: Any) -> str:
    canon = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_runner_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def new_user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalise_user_code(code: str) -> str:
    """The owner's typing (Persian digits, lower case, no dash) in the one shape."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    raw = "".join(ch for ch in code.translate(table).upper() if ch.isalnum())
    return f"{raw[:4]}-{raw[4:8]}" if len(raw) == 8 else raw


def shown_cmd(kind: str, args: dict[str, Any]) -> str:
    """What a job does, as the activity and the stream show it (masked)."""
    if kind == "exec":
        return mask(str(args.get("cmd") or ""))[:2000]
    if kind in ("read", "write"):
        return f"{kind} {args.get('path') or ''}"[:2000]
    if kind == "claude":
        return mask(str(args.get("prompt") or args.get("brief") or ""))[:300]
    if kind == "publish":
        return mask(str(args.get("command") or ""))[:2000]
    if kind == "netcheck":
        return (
            "netcheck "
            + " ".join(f"{t.get('host')}:{t.get('port')}" for t in args.get("targets") or [])[:1990]
        )
    if kind == "ledger":  # ⟨1.15⟩ §33.2: the contract name, nothing else
        return f"ledger {args.get('contract')}"
    return kind


def shown_args(kind: str, args: dict[str, Any]) -> dict[str, Any]:
    """A job's arguments for the owner and the activity: masked, without the
    bytes of a write or the signed URLs of a publish."""
    out = {k: v for k, v in args.items() if k not in ("content", "files", "signed")}
    if kind == "write" and "content" in args:
        out["bytes"] = len(str(args.get("content") or ""))
    if kind == "publish":
        out["files"] = [
            {"name": f.get("name"), "mime": f.get("mime")} for f in args.get("files") or []
        ]
    if "cmd" in out:
        out["cmd"] = mask(str(out["cmd"]))
    if "brief" in out:
        out["brief"] = mask(str(out["brief"]))[:2000]
    if "prompt" in out:
        out["prompt"] = mask(str(out["prompt"]))[:2000]
    return mask_value(out)  # type: ignore[no-any-return]


def online(row: dict[str, Any]) -> bool:
    seen: datetime | None = row.get("last_seen_at")
    return seen is not None and seen > now() - timedelta(seconds=ONLINE_S)


def state_of(row: dict[str, Any]) -> str:
    """pending · online · offline · revoked (a provisioned server without a runner: offline)."""
    st = row.get("state")
    if st in ("pending", "revoked"):
        return str(st)
    if st is None:
        return "offline"
    return "online" if online(row) else "offline"


def principal_of(kind: str, code: str) -> Principal:
    if kind == "owner":
        return Principal(kind="owner", code="owner", role="owner")
    if kind == "agent":
        return Principal(kind="agent", code=code, role="employee")
    return Principal(kind="service", code=code, role="service")


def actor_of(kind: str, code: str) -> Actor:
    a = actor(kind, code)
    assert a is not None
    return a


# ------------------------------------------------------------------- models --
class ServerOut(BaseModel):
    """§26.4 GET /infra/servers (the provisioner's fields kept, ⟨1.8⟩ extended)."""

    id: UUID
    company: str
    name: str
    origin: Literal["provisioned", "attached"]
    private_ip: str | None
    user: str | None
    hostname: str | None
    os: str | None = None
    runner_version: str | None
    via: Literal["private", "public"] | None
    state: Literal["pending", "online", "offline", "revoked"]
    last_seen_at: datetime | None
    map_at: datetime | None
    hub_rtt_ms: float | None = None
    # the provisioner's (null for an attached server)
    hetzner_id: int | None = None
    plan: str | None = None
    ipv4: str | None = None
    ipv6: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Job(BaseModel):
    """§26.2 (plus the company, the card, the session and the result)."""

    id: UUID
    server: UUID
    company: str
    kind: str
    actor: Actor
    on_behalf: str | None = None
    args: dict[str, Any]
    state: Literal["queued", "running", "awaiting_seal", "done", "failed", "cancelled"]
    category: str | None = None
    decision_ref: str | None = None
    session_ref: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    duration_ms: int | None = None
    summary_fa: str | None
    error_code: str | None = None
    transcript_url: str | None
    result: dict[str, Any] | None = None


class ServerCall(BaseModel):
    """One row of a server's activity (§26.4): a job, or a command inside a
    `claude` job (tool server.exec, the job's session)."""

    id: str
    at: datetime
    actor: Actor
    tool: str
    kind: str | None = None
    args: dict[str, Any] | None = None
    summary_fa: str | None = None
    cmd_masked: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    session_ref: str | None = None
    transcript_url: str | None = None
    server: str
    state: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


SERVER_SQL = """
    SELECT s.*, c.code AS company, p.ref AS plan_ref
    FROM infra.servers s JOIN core.companies c ON c.id = s.company_id
    LEFT JOIN provisioning.plans p ON p.id = s.plan_id
"""
JOB_SQL = """
    SELECT j.*, c.code AS company, s.name AS server_name, d.ref AS decision_ref,
           ws.ref AS session_ref
    FROM infra.server_jobs j JOIN core.companies c ON c.id = j.company_id
    JOIN infra.servers s ON s.id = j.server_id
    LEFT JOIN cartable.decisions d ON d.id = j.decision_id
    LEFT JOIN workshop.sessions ws ON ws.id = j.session_id
"""


def render_server(r: dict[str, Any]) -> ServerOut:
    return ServerOut(
        id=r["id"],
        company=r["company"],
        name=r["name"],
        origin=r["origin"],
        private_ip=r["private_ip"],
        user=r["work_user"],
        hostname=r["hostname"],
        os=r["os"],
        runner_version=r["runner_version"],
        via=r["via"],
        state=state_of(r),
        last_seen_at=r["last_seen_at"],
        map_at=r["map_at"],
        hub_rtt_ms=float(r["hub_rtt_ms"]) if r["hub_rtt_ms"] is not None else None,
        hetzner_id=r["hetzner_id"],
        plan=r.get("plan_ref"),
        ipv4=r["ipv4"],
        ipv6=r["ipv6"],
        labels=r["labels"] or {},
        created_at=r["created_at"],
    )


def transcript_path(j: dict[str, Any]) -> str | None:
    if not j.get("transcript_file_id"):
        return None
    return f"/api/v1/infra/servers/{j['server_id']}/jobs/{j['id']}/transcript"


def duration_ms(j: dict[str, Any]) -> int | None:
    a, b = j.get("started_at") or j.get("dispatched_at"), j.get("finished_at")
    if a is None or b is None:
        return None
    return max(0, int((b - a).total_seconds() * 1000))


def render_job(j: dict[str, Any]) -> Job:
    return Job(
        id=j["id"],
        server=j["server_id"],
        company=j["company"],
        kind=j["kind"],
        actor=actor_of(j["actor_kind"], j["actor_code"]),
        on_behalf=j["on_behalf_code"],
        args=shown_args(j["kind"], j["args"] or {}),
        state=j["state"],
        category=j["category"],
        decision_ref=j.get("decision_ref"),
        session_ref=j.get("session_ref"),
        created_at=j["created_at"],
        started_at=j["started_at"] or j["dispatched_at"],
        finished_at=j["finished_at"],
        exit_code=j["exit_code"],
        duration_ms=duration_ms(j),
        summary_fa=j["summary_fa"],
        error_code=j["error_code"],
        transcript_url=transcript_path(j),
        result=j["result"],
    )


def call_state(state: str) -> str:
    """A job's state as the stream's server.call says it (running · done · failed)."""
    if state in ("queued", "running", "awaiting_seal"):
        return "running"
    return "done" if state == "done" else "failed"


async def load_server(tx: Tx, ref: str | UUID, *, company: str | None = None,
                      lock: bool = False) -> dict[str, Any]:  # fmt: skip
    """A server by its id, or by its name within `company`."""
    try:
        sid = UUID(str(ref))
    except ValueError:
        sid = None
    tail = " FOR UPDATE OF s" if lock else ""
    if sid is not None:
        row = await tx.first(SERVER_SQL + " WHERE s.id = :id" + tail, id=sid)
    else:
        row = await tx.first(
            SERVER_SQL
            + " WHERE lower(s.name) = lower(:n) AND (CAST(:co AS text) IS NULL OR c.code = :co)"
            + " ORDER BY s.origin = 'attached' DESC, s.created_at DESC LIMIT 1"
            + tail,
            n=str(ref),
            co=company,
        )
    if row is None or (company is not None and row["company"] != company):
        raise ApiError(404, "not_found", "no such server")
    return row


async def load_job(tx: Tx, job_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        JOB_SQL + " WHERE j.id = :id" + (" FOR UPDATE OF j" if lock else ""), id=job_id
    )


async def seal_required(tx: Tx) -> list[str]:
    row = await tx.first("SELECT seal_required FROM control.server_policy WHERE id")
    if row is None:
        return list(CATEGORIES)
    return [c for c in CATEGORIES if c in (row["seal_required"] or [])]


# ---------------------------------------------------------------- events --
def rtt_tier(ms: Any) -> str | None:
    """⟨1.24⟩ §42.2 a round trip's tier: normal or slow (None when not measured)."""
    if ms is None:
        return None
    return "slow" if float(ms) >= SLOW_MS else "normal"


async def reason_of(tx: Tx, s: dict[str, Any]) -> str | None:
    """⟨1.24⟩ §42.2 why a server is as it is, inferred by the hub (a client never infers offline
    from silence): offline and another server reached its ports since its runner went silent →
    `runner_stopped`; measured since and nobody reached it → `server_unreachable`; not measured
    since → `no_poll`. Online over the public fallback → `fallback_public`; a slow round trip →
    `slow`; revoked → `revoked`; else None."""
    st = state_of(s)
    if st == "revoked":
        return "revoked"
    if st == "offline":
        row = await tx.first(
            """SELECT count(*) AS n, bool_or(ok) AS reached FROM infra.network_links
               WHERE to_key = :k AND from_server_id <> :id AND port = ANY(CAST(:ports AS int[]))
                 AND (CAST(:since AS timestamptz) IS NULL OR at >= CAST(:since AS timestamptz))""",
            k=str(s["id"]),
            id=s["id"],
            ports=list(NETCHECK_SERVER_PORTS),
            since=s.get("last_seen_at"),
        )
        if row is None or not row["n"]:
            return "no_poll"
        return "runner_stopped" if row["reached"] else "server_unreachable"
    if st == "online":
        if s.get("via") == "public":
            return "fallback_public"
        if rtt_tier(s.get("hub_rtt_ms")) == "slow":
            return "slow"
    return None


def state_since(s: dict[str, Any]) -> datetime | None:
    """When the server's state began (rows from before 0058 without it: their last contact
    when offline, else the row's last change)."""
    since: datetime | None = s.get("state_since")
    if since is None:
        since = s.get("last_seen_at") if state_of(s) == "offline" else s.get("updated_at")
    return since


async def emit_state(tx: Tx, s: dict[str, Any], *, prev: str | None = None) -> None:
    """`server.state` (§26.4) with ⟨1.24⟩ §42.2's additive fields: the state before (`prev`, the
    same state when only the route or the round trip changed), since when, why (and in plain
    words), the round trip and the open jobs. The reason said is kept on the server."""
    reason = await reason_of(tx, s)
    open_jobs = await tx.scalar(
        "SELECT count(*) FROM infra.server_jobs WHERE server_id = :s AND state = ANY(:open)",
        s=s["id"],
        open=list(OPEN),
    )
    if reason != s.get("state_reason"):
        await tx.exec(
            "UPDATE infra.servers SET state_reason = :r WHERE id = :id", r=reason, id=s["id"]
        )
    since = state_since(s)
    await events.emit(
        tx,
        s["company"],
        "server.state",
        str(s["id"]),
        {
            "server": str(s["id"]),
            "company": s["company"],
            "name": s["name"],
            "state": state_of(s),
            "via": s["via"],
            "last_seen_at": s["last_seen_at"].isoformat() if s["last_seen_at"] else None,
            "prev_state": prev,
            "since": since.isoformat() if since else None,
            "reason": reason,
            "reason_fa": REASON_FA.get(reason) if reason else None,
            "hub_rtt_ms": float(s["hub_rtt_ms"]) if s.get("hub_rtt_ms") is not None else None,
            "open_jobs": int(open_jobs or 0),
        },
    )


async def emit_call(tx: Tx, j: dict[str, Any], *, cmd: str | None = None,
                    exit_code: int | None = None, ms: int | None = None,
                    state: str | None = None, tool: str | None = None,
                    summary: str | None = None) -> None:  # fmt: skip
    """§26.5 `server.call`: one per job start and end (and per command inside
    a `claude` job), summary only."""
    a = actor_of(j["actor_kind"], j["actor_code"])
    await events.emit(
        tx,
        j["company"],
        "server.call",
        str(j["server_id"]),
        {
            "server": str(j["server_id"]),
            "company": j["company"],
            "actor": a.model_dump(),
            "tool": tool or TOOL_OF.get(j["kind"], "server.exec"),
            "summary_fa": (summary if summary is not None else j.get("summary_fa"))
            or KIND_FA.get(j["kind"], j["kind"]),
            "cmd_masked": cmd if cmd is not None else shown_cmd(j["kind"], j["args"] or {}),
            "exit_code": exit_code if exit_code is not None else j.get("exit_code"),
            "duration_ms": ms if ms is not None else duration_ms(j),
            "session_ref": j.get("session_ref"),
            "state": state or call_state(j["state"]),
            "job": str(j["id"]),
            "kind": j["kind"],
            **({"code": j["error_code"]} if j.get("error_code") else {}),
        },
    )


# ---------------------------------------------------------------- pairing --
async def pair(tx: Tx, company: dict[str, Any], payload: dict[str, Any], ip_hash: str | None
               ) -> dict[str, Any]:  # fmt: skip
    """POST /runners/pair: a pending pairing; the device code is returned once."""
    device = secrets.token_urlsafe(32)
    for _ in range(5):
        code = new_user_code()
        if not await tx.scalar(
            "SELECT 1 FROM infra.runner_pairings WHERE user_code = :c AND state = 'pending'", c=code
        ):
            break
    await tx.exec(
        """INSERT INTO infra.runner_pairings (company_id, device_sha256, user_code, payload,
               ip_hash, expires_at)
           VALUES (:co, :d, :u, CAST(:p AS jsonb), :ip, now() + make_interval(secs => :ttl))""",
        co=company["id"],
        d=token_digest(device),
        u=code,
        p=json.dumps(payload, ensure_ascii=False),
        ip=ip_hash,
        ttl=PAIR_TTL_S,
    )
    return {
        "device_code": device,
        "user_code": code,
        "expires_in": PAIR_TTL_S,
        "interval": PAIR_INTERVAL_S,
    }


PAIRING_SQL = """
    SELECT p.*, c.code AS company FROM infra.runner_pairings p
    JOIN core.companies c ON c.id = p.company_id
    WHERE p.user_code = :u ORDER BY p.created_at DESC LIMIT 1
"""


async def pairing_by_code(tx: Tx, user_code: str, *, lock: bool = False) -> dict[str, Any]:
    """The newest pairing of a code: 404 invalid_user_code, 410 expired_token,
    409 code_used (approved already)."""
    code = normalise_user_code(user_code)
    row = await tx.first(PAIRING_SQL + (" FOR UPDATE OF p" if lock else ""), u=code)
    if row is None:
        raise ApiError(404, "invalid_user_code", "no pairing with this code")
    if row["state"] != "pending":
        raise ApiError(409, "code_used", "this code was approved already")
    if row["expires_at"] <= now():
        raise ApiError(410, "expired_token", "the code expired (15 minutes)")
    return row


async def approve(tx: Tx, who: Principal, p: dict[str, Any], step_up_id: UUID) -> dict[str, Any]:
    """The owner approved the code (🔏 server.attach on company:<CODE>): the
    server row exists now (state pending until the runner takes its token)."""
    info = p["payload"] or {}
    name = str(info.get("name") or "")[:63]
    existing = await tx.first(
        SERVER_SQL + " WHERE s.company_id = :co AND lower(s.name) = lower(:n) FOR UPDATE OF s",
        co=p["company_id"],
        n=name,
    )
    prev = None
    if existing is not None:
        live = await tx.scalar(
            "SELECT 1 FROM infra.runners WHERE server_id = :s AND revoked_at IS NULL",
            s=existing["id"],
        )
        if live and existing["state"] != "revoked":
            raise ApiError(
                409, "validation_failed", fields={"name": f"{name} already has a runner"}
            )
        sid = existing["id"]
        prev = state_of(existing)
        await tx.exec(
            """UPDATE infra.servers SET state = 'pending', hostname = :h, os = :os,
                   runner_version = :v, private_ip = COALESCE(:ip, private_ip), work_user = :u,
                   via = NULL, updated_at = now(), state_since = now()
               WHERE id = :id""",
            id=sid,
            h=info.get("hostname"),
            os=info.get("os"),
            v=info.get("runner_version"),
            ip=info.get("private_ip"),
            u=info.get("user"),
        )
    else:
        sid = await tx.scalar(
            """INSERT INTO infra.servers (company_id, origin, name, hostname, os, runner_version,
                   private_ip, work_user, state, state_since)
               VALUES (:co, 'attached', :n, :h, :os, :v, :ip, :u, 'pending', now()) RETURNING id""",
            co=p["company_id"],
            n=name,
            h=info.get("hostname"),
            os=info.get("os"),
            v=info.get("runner_version"),
            ip=info.get("private_ip"),
            u=info.get("user"),
        )
    await tx.exec(
        """UPDATE infra.runner_pairings SET state = 'approved', approved_by_kind = 'owner',
               approved_by_code = :c, approved_at = now(), step_up_id = :su, server_id = :s
           WHERE id = :id""",
        id=p["id"],
        c=who.code,
        su=step_up_id,
        s=sid,
    )
    s = await load_server(tx, sid)
    await audit.record(
        tx,
        who,
        company_id=p["company_id"],
        action="server.attach",
        action_class="A2",
        target_kind="server",
        target_ref=f"{s['company']}:{s['name']}",
        summary=f"paired {info.get('hostname') or '-'} ({info.get('private_ip') or '-'}), "
        f"runner {info.get('runner_version') or '-'}; pending its token",
        step_up=True,
    )
    await emit_state(tx, s, prev=prev)
    return s


async def claim_token(tx: Tx, device_code: str) -> dict[str, Any]:
    """POST /runners/token: 428 authorization_pending until approved, then the
    credential once (only its sha256 is kept); 410 for an expired or used code."""
    p = await tx.first(
        """SELECT * FROM infra.runner_pairings WHERE device_sha256 = :d FOR UPDATE""",
        d=token_digest(device_code),
    )
    if p is None:
        raise ApiError(401, "unauthenticated", "unknown device code")
    if p["state"] == "claimed":
        raise ApiError(410, "expired_token", "the credential was handed out already")
    if p["state"] == "pending":
        if p["expires_at"] <= now():
            raise ApiError(410, "expired_token", "the code expired (15 minutes)")
        raise ApiError(428, "authorization_pending", "the owner has not approved the code yet")
    token = new_runner_token()
    await tx.exec(
        """UPDATE infra.runners SET revoked_at = now(), revoked_by_kind = 'system',
               revoked_by_code = 'pairing'
           WHERE server_id = :s AND revoked_at IS NULL""",
        s=p["server_id"],
    )
    await tx.exec(
        """INSERT INTO infra.runners (company_id, server_id, pairing_id, token_sha256)
           VALUES (:co, :s, :p, :t)""",
        co=p["company_id"],
        s=p["server_id"],
        p=p["id"],
        t=token_digest(token),
    )
    await tx.exec(
        "UPDATE infra.runner_pairings SET state = 'claimed', claimed_at = now() WHERE id = :id",
        id=p["id"],
    )
    prev = state_of(await load_server(tx, p["server_id"]))
    await tx.exec(
        """UPDATE infra.servers SET state = 'online', last_seen_at = now(), updated_at = now(),
               state_since = now()
           WHERE id = :id""",
        id=p["server_id"],
    )
    s = await load_server(tx, p["server_id"])
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=p["company_id"],
        action="server.runner_token",
        action_class="A1",
        target_kind="server",
        target_ref=f"{s['company']}:{s['name']}",
        summary="the runner took its credential",
    )
    await emit_state(tx, s, prev=prev)
    return {"runner_token": token, "server_id": str(p["server_id"]), "rotate_after_s": 86400}


async def runner_by_token(tx: Tx, token: str) -> dict[str, Any] | None:
    """The live runner of a credential (or of the previous one within the
    grace after a rotation); the comparison is constant-time on the digest."""
    h = token_digest(token)
    row = await tx.first(
        """SELECT r.*, s.name AS server_name, s.state AS server_state, c.code AS company
           FROM infra.runners r JOIN infra.servers s ON s.id = r.server_id
           JOIN core.companies c ON c.id = r.company_id
           WHERE r.revoked_at IS NULL
             AND (r.token_sha256 = :h OR (r.prev_sha256 = :h AND r.prev_valid_until > now()))""",
        h=h,
    )
    if row is None:
        return None
    if not (
        hmac.compare_digest(row["token_sha256"], h)
        or (row["prev_sha256"] is not None and hmac.compare_digest(row["prev_sha256"], h))
    ):
        return None
    if row["server_state"] == "revoked":
        return None
    row["current"] = hmac.compare_digest(row["token_sha256"], h)
    return row


async def rotate(tx: Tx, runner: dict[str, Any]) -> dict[str, Any]:
    token = new_runner_token()
    await tx.exec(
        """UPDATE infra.runners SET prev_sha256 = token_sha256,
               prev_valid_until = now() + make_interval(secs => :g),
               token_sha256 = :t, rotated_at = now()
           WHERE id = :id""",
        id=runner["id"],
        t=token_digest(token),
        g=ROTATE_GRACE_S,
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=runner["company_id"],
        action="server.rotate",
        action_class="A1",
        target_kind="server",
        target_ref=f"{runner['company']}:{runner['server_name']}",
        summary="runner credential rotated",
    )
    return {"runner_token": token, "rotate_after_s": 86400}


async def seen(tx: Tx, runner: dict[str, Any], via: str | None, rtt: float | None,
               version: str | None = None) -> None:  # fmt: skip
    """A poll: the server is online, its route and its round trip to the hub. `server.state`
    when it comes online, its route changes or ⟨1.24⟩ its round trip changes tier."""
    s = await load_server(tx, runner["server_id"], lock=True)
    was = state_of(s)
    await tx.exec(
        """UPDATE infra.servers SET last_seen_at = now(), state = 'online',
               via = COALESCE(:via, via), hub_rtt_ms = COALESCE(:rtt, hub_rtt_ms),
               runner_version = COALESCE(:v, runner_version),
               state_since = CASE WHEN CAST(:back AS boolean) THEN now() ELSE state_since END
           WHERE id = :id""",
        id=s["id"],
        via=via,
        rtt=rtt,
        v=version,
        back=was != "online",
    )
    await tx.exec("UPDATE infra.runners SET last_used_at = now() WHERE id = :id", id=runner["id"])
    tier = rtt is not None and rtt_tier(rtt) != rtt_tier(s.get("hub_rtt_ms"))
    if was != "online" or (via and via != s["via"]) or tier:
        await emit_state(tx, await load_server(tx, s["id"]), prev=was)


async def detach(tx: Tx, who: Principal, s: dict[str, Any], step_up_id: UUID) -> dict[str, Any]:
    """🔏 server.detach: the credential is revoked at once and the server's
    open jobs are cancelled; the row stays (nothing is deleted)."""
    await tx.exec(
        """UPDATE infra.runners SET revoked_at = now(), revoked_by_kind = :k, revoked_by_code = :c
           WHERE server_id = :s AND revoked_at IS NULL""",
        s=s["id"],
        k=who.kind,
        c=who.code,
    )
    prev = state_of(s)
    await tx.exec(
        """UPDATE infra.servers SET state = 'revoked', updated_at = now(), state_since = now()
           WHERE id = :id""",
        id=s["id"],
    )
    for j in await tx.all(
        JOB_SQL + " WHERE j.server_id = :s AND j.state = ANY(:open) FOR UPDATE OF j",
        s=s["id"],
        open=list(OPEN),
    ):
        await cancel(tx, j, "server_detached", "سرور جدا شد؛ کار لغو شد")
    await audit.record(
        tx,
        who,
        company_id=s["company_id"],
        action="server.detach",
        action_class="A2",
        target_kind="server",
        target_ref=f"{s['company']}:{s['name']}",
        summary="runner revoked",
        step_up=step_up_id is not None,
    )
    s = await load_server(tx, s["id"])
    await emit_state(tx, s, prev=prev)
    return s


# ------------------------------------------------------------------- jobs --
async def check_lock(tx: Tx, company_id: UUID, *, deploy: bool) -> str | None:
    """423 company_locked under a kill switch (the company's or the
    holding's); 423 deploy_frozen for a deploy under a freeze. Returns the lock."""
    lock = await tx.scalar("SELECT control.lock_state(:co)", co=company_id)
    if lock in ("holding", "company"):
        raise ApiError(423, "company_locked", f"locked: {lock}")
    if lock == "deploy_freeze" and deploy:
        raise ApiError(423, "deploy_frozen", "a deploy freeze holds this company")
    return str(lock) if lock else None


# ⟨19.3⟩ §28.6: a claude job's allow-list (runner 0.2.1 hands it to Claude Code
# as --allowedTools); the same shape the runner accepts
ALLOWED_TOOL = re.compile(r"^(?:[A-Z][A-Za-z]{1,30}|Bash\([^()\n\x00]{1,200}\))$")
MAX_ALLOWED_TOOLS = 200


def allowed_tools_ok(v: Any) -> bool:
    return (
        isinstance(v, list)
        and len(v) <= MAX_ALLOWED_TOOLS
        and all(isinstance(t, str) and ALLOWED_TOOL.match(t) for t in v)
    )


def check_args(kind: str, args: dict[str, Any]) -> None:
    bad: dict[str, str] = {}
    if kind == "exec" and not str(args.get("cmd") or "").strip():
        bad["cmd"] = "required"
    if kind in ("read", "write") and not str(args.get("path") or "").strip():
        bad["path"] = "required"
    if kind == "claude" and not (str(args.get("brief") or args.get("prompt") or "").strip()):
        bad["brief"] = "required"
    if kind == "publish" and not str(args.get("command") or "").strip():
        bad["command"] = "required"
    if kind == "ledger" and args.get("contract") != "ledger_v1":
        bad["contract"] = "ledger_v1"
    if kind == "claude" and "allowed_tools" in args and not allowed_tools_ok(args["allowed_tools"]):
        bad["allowed_tools"] = "a list of tool names or Bash(<prefix>) patterns"
    if bad:
        raise ApiError(422, "validation_failed", fields=bad)


async def create_job(
    tx: Tx,
    *,
    server: dict[str, Any],
    kind: str,
    args: dict[str, Any],
    actor_kind: str,
    actor_code: str,
    on_behalf: str | None = None,
    work_ref: str | None = None,
    summary: str = "",
    timeout_s: int = 600,
    session_id: UUID | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """A job for one server: refused while the company is locked (423) or,
    for a deploy, frozen; a destructive command the policy lists waits for
    the owner's seal (`awaiting_seal` and a `server_destructive` card)."""
    if kind not in JOB_KINDS:
        raise ApiError(422, "validation_failed", fields={"kind": "unknown job kind"})
    if state_of(server) == "revoked":
        raise ApiError(409, "validation_failed", fields={"server": "detached (revoked)"})
    check_args(kind, args)
    hit: tuple[str, str] | None = None
    deploy = False
    if kind == "exec":
        hit = classify_detail(str(args["cmd"]))
        deploy = is_deploy(str(args["cmd"]))
    elif kind == "write":
        hit = classify_path(str(args["path"]))
    elif kind == "publish":
        hit = classify_detail(str(args["command"]))
    await check_lock(tx, server["company_id"], deploy=deploy)
    sealed = await seal_required(tx)
    waits = hit is not None and hit[0] in sealed
    row = await tx.one(
        """INSERT INTO infra.server_jobs (company_id, server_id, kind, actor_kind, actor_code,
               on_behalf_code, work_ref, args, args_sha256, summary_in, state, category, pattern,
               deploy, timeout_s, session_id)
           VALUES (:co, :s, :k, :ak, :ac, :ob, :wr, CAST(:args AS jsonb), :sha, :sum, :st, :cat,
                   :pat, :dep, :t, :sess)
           RETURNING id""",
        co=server["company_id"],
        s=server["id"],
        k=kind,
        ak=actor_kind,
        ac=actor_code[:64],
        ob=on_behalf,
        wr=work_ref,
        args=json.dumps(args, ensure_ascii=False),
        sha=digest_of(args),
        sum=mask(summary)[:2000],
        st="awaiting_seal" if waits else "queued",
        cat=hit[0] if hit else None,
        pat=hit[1] if hit else None,
        dep=deploy,
        t=max(1, min(int(timeout_s), 3600)),
        sess=session_id,
    )
    j = await load_job(tx, row["id"])
    cmd = shown_cmd(kind, args)
    await audit.record(
        tx,
        principal_of(actor_kind, actor_code),
        company_id=server["company_id"],
        action="server.job",
        action_class="A2" if kind in ("exec", "write", "claude", "publish") else "A0",
        target_kind="server_job",
        target_ref=str(j["id"]),
        summary=f"{server['name']} {kind} queued"
        + (f" ({hit[0]}: awaiting seal)" if waits and hit else "")
        + (f" on behalf of {on_behalf}" if on_behalf else "")
        + f": {cmd[:300]} sha256:{j['args_sha256'][:16]}",
        request_id=request_id,
    )
    if waits:
        assert hit is not None
        j = await raise_seal(tx, j, server, hit[0], hit[1], cmd, cwd=args.get("cwd"))
    return j


async def raise_seal(
    tx: Tx,
    j: dict[str, Any],
    server: dict[str, Any],
    category: str,
    pattern: str,
    cmd: str,
    *,
    cwd: str | None = None,
    session_ref: str | None = None,
    cmd_sha256: str | None = None,
) -> dict[str, Any]:
    """The `server_destructive` card (A3, 🔏 server.destructive on
    <CODE>:<server>); the job waits in `awaiting_seal` until it is decided."""
    a = actor_of(j["actor_kind"], j["actor_code"])
    payload = {
        "server": {"id": str(server["id"]), "name": server["name"]},
        "server_name": server["name"],
        "company": server["company"],
        "category": category,
        "cmd": cmd[:4000],
        "cmd_sha256": cmd_sha256 or hashlib.sha256(cmd.encode()).hexdigest(),
        "cwd": cwd,
        "tool": TOOL_OF.get(j["kind"], "server.exec"),
        "actor": a.model_dump(),
        "session_ref": session_ref or j.get("session_ref"),
        "job": str(j["id"]),
        "detected_by": "pattern",
        "pattern": pattern,
    }
    din = D.DecisionIn(
        kind="server_destructive",
        title=f"کار ویرانگر روی {server['company']}:{server['name']}: {CATEGORY_FA[category]}"[
            :300
        ],
        what=f"`{cmd[:1500]}`" + (f"\n\nدر `{cwd}`" if cwd else ""),
        why=f"دسته‌ی «{CATEGORY_FA[category]}» در سیاست سرورها منتظر مُهر توست "
        f"(الگو: {pattern}). درخواست از {a.code}.",
        risk="high",
        reversible=False,
        payload=payload,
    )
    d = await D.propose(
        tx,
        SERVICE,
        company_id=server["company_id"],
        company_code=server["company"],
        body=din,
        thread_code=None,
    )
    await tx.exec(
        "UPDATE infra.server_jobs SET decision_id = :d, state = 'awaiting_seal' WHERE id = :id",
        d=d["id"],
        id=j["id"],
    )
    j = await load_job(tx, j["id"])
    await events.emit(
        tx,
        server["company"],
        "server.awaiting_seal",
        str(server["id"]),
        {
            "server": str(server["id"]),
            "company": server["company"],
            "decision_ref": d["ref"],
            "category": category,
            "cmd_masked": cmd[:2000],
            "tool": payload["tool"],
            "job": str(j["id"]),
            "session_ref": payload["session_ref"],
        },
    )
    return j


async def on_decided(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """A `server_destructive` card was decided: sealed -> the job goes on
    (queued again, or running again for a command inside a `claude` job);
    rejected or returned -> the job (or that one command) does not run."""
    jobs = await tx.all(JOB_SQL + " WHERE j.decision_id = :d FOR UPDATE OF j", d=d["id"])
    for j in jobs:
        if j["state"] != "awaiting_seal":
            continue
        if verdict == "approved":
            # A command inside a running claude job: the job was dispatched already.
            state = "running" if j["dispatched_at"] else "queued"
            await tx.exec(
                "UPDATE infra.server_jobs SET state = :st WHERE id = :id", st=state, id=j["id"]
            )
            if j["session_id"]:
                await tx.exec(
                    "UPDATE workshop.sessions SET state = 'working' WHERE id = :s AND state = 'waiting_approval'",
                    s=j["session_id"],
                )
        elif j["kind"] == "claude" and j["dispatched_at"]:
            # Only that command is refused; the session goes on without it.
            await tx.exec(
                "UPDATE infra.server_jobs SET state = 'running' WHERE id = :id", id=j["id"]
            )
        else:
            await cancel(tx, j, "seal_refused", "مدیر کل اجازه‌ی این کار ویرانگر را نداد")
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=d["company_id"],
        action="server.seal",
        action_class="A3",
        target_kind="decision",
        target_ref=d["ref"],
        summary=f"{verdict}: {len(jobs)} job(s)",
    )


async def cancel(tx: Tx, j: dict[str, Any], code: str, summary_fa: str) -> dict[str, Any]:
    """Cancelled (the runner sees it on its next poll if it runs it)."""
    if j["state"] in FINAL:
        return j
    await tx.exec(
        """UPDATE infra.server_jobs SET state = 'cancelled', finished_at = now(), error_code = :c,
               cancel_reason = :c, summary_fa = :s
           WHERE id = :id""",
        id=j["id"],
        c=code,
        s=summary_fa[:2000],
    )
    j = await load_job(tx, j["id"])
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=j["company_id"],
        action="server.cancel",
        action_class="A1",
        target_kind="server_job",
        target_ref=str(j["id"]),
        summary=f"{j['server_name']} {j['kind']} cancelled: {code}",
    )
    if j["dispatched_at"]:
        await emit_call(tx, j, state="failed")
    if j["session_id"]:
        await _session_end(tx, j, "stopped", code, summary_fa)
    return j


async def cancel_locked(tx: Tx) -> list[dict[str, Any]]:
    """A kill switch was engaged: the open jobs of every locked company are
    cancelled (contract §26.3)."""
    rows = await tx.all(
        JOB_SQL
        + """ WHERE j.state = ANY(:open) AND control.lock_state(j.company_id) IN ('holding', 'company')
              FOR UPDATE OF j""",
        open=list(OPEN),
    )
    return [await cancel(tx, j, "company_locked", "کلید توقف شرکت: کار لغو شد") for j in rows]


async def dispatch(
    tx: Tx, runner: dict[str, Any], *, hold_claude: bool = False
) -> dict[str, Any] | None:
    """The oldest queued job of the runner's server, now running; None when
    there is none (or the company is locked: nothing new starts).
    ⟨2026-11-09⟩ `hold_claude`: both Claude accounts are full, so a Claude Code job stays queued
    (it starts once either has room, as the hub's own calls wait) and the other kinds go on."""
    lock = await tx.scalar("SELECT control.lock_state(:co)", co=runner["company_id"])
    if lock in ("holding", "company"):
        return None
    row = await tx.first(
        """SELECT id FROM infra.server_jobs WHERE server_id = :s AND state = 'queued'
             AND (NOT CAST(:hold AS boolean) OR kind <> 'claude')
           ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""",
        s=runner["server_id"],
        hold=hold_claude,
    )
    if row is None:
        return None
    await tx.exec(
        """UPDATE infra.server_jobs SET state = 'running', dispatched_at = now(),
               started_at = COALESCE(started_at, now())
           WHERE id = :id""",
        id=row["id"],
    )
    j = await load_job(tx, row["id"])
    if j["session_id"]:
        await tx.exec(
            "UPDATE workshop.sessions SET state = 'working' WHERE id = :s AND state IN ('starting', 'idle')",
            s=j["session_id"],
        )
        await _session_emit(tx, j["session_id"])
    await emit_call(tx, j, state="running")
    return j


async def cancels_for(tx: Tx, runner: dict[str, Any]) -> list[str]:
    """Jobs the runner was given and that were cancelled since: told once."""
    rows = await tx.all(
        """UPDATE infra.server_jobs SET cancel_delivered_at = now()
           WHERE server_id = :s AND state = 'cancelled' AND dispatched_at IS NOT NULL
             AND cancel_delivered_at IS NULL
           RETURNING id""",
        s=runner["server_id"],
    )
    return [str(r["id"]) for r in rows]


# ⟨2026-11-09⟩ the owner: «هر وقت سوییچ انجام شد به کلود یک همه چیز بیاد روی یک». A company
# server's Claude Code job runs on the account the hub itself is on: the main subscription while it
# has room, the second one once the main is at 99% or refused, and the main again once its window
# resets. Both full: the job waits in the queue (as the hub's calls wait) instead of failing.
# The same rule as llm-router's QuotaController.near_full, read from what the router persisted.
RUNNER_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("claude-max", "runner_claude_token_main"),
    ("claude-max-2", "runner_claude_token"),
)
ACCOUNT_NEAR_FULL = Decimal("0.99")
# an older "ok" observation no longer decides (the router's SDK_FRESH)
ACCOUNT_SDK_FRESH = timedelta(hours=6)
ACCOUNTS_SQL = """SELECT c.key, c.status AS connection_status, q.status, q.utilization,
       q.resets_at, q.observed_at
  FROM llm.connections c LEFT JOIN llm.quota_status q ON q.connection_id = c.id
 WHERE c.key = ANY(CAST(:keys AS text[]))"""


def account_full(row: dict[str, Any] | None, now: datetime) -> bool:
    """A subscription at 99% of its window or refused, while that window holds."""
    if row is None or row.get("status") is None:
        return False
    resets = row.get("resets_at")
    if resets is not None and resets <= now:
        return False  # its window has reset
    util = row.get("utilization")
    near = util is not None and Decimal(str(util)) >= ACCOUNT_NEAR_FULL
    if row["status"] == "limited":
        return True
    if row["status"] == "ok":
        seen = row.get("observed_at")
        return near and seen is not None and seen > now - ACCOUNT_SDK_FRESH
    return near


async def runner_claude_account(tx: Tx, hub: Any) -> tuple[str, bool]:
    """(the token a Claude Code job takes now, whether Claude Code jobs wait). No token at all
    (neither account stored): ("", False), the server's own login. Every stored account full:
    ("", True), the jobs stay queued until one has room."""
    sec = getattr(hub, "secrets", None)
    stored = [(k, str(getattr(sec, attr, "") or "")) for k, attr in RUNNER_ACCOUNTS]
    stored = [(k, t) for k, t in stored if t]
    if not stored:
        return "", False
    rows = {str(r["key"]): dict(r) for r in await tx.all(ACCOUNTS_SQL, keys=[k for k, _ in stored])}
    now = await tx.scalar("SELECT now()")
    full = False
    for key, token in stored:
        r = rows.get(key)
        if r is not None and r["connection_status"] not in ("enabled", "ready"):
            continue  # switched off on the hub too
        if account_full(r, now):
            full = True
            continue
        return token, False
    return "", full


def runner_job(j: dict[str, Any], hub: Any, *, claude_token: str = "") -> dict[str, Any]:
    """What the runner gets: the exact arguments (it runs them), the timeout
    and, for a publish, fresh signed hub URLs of the rendered files."""
    args = dict(j["args"] or {})
    if j["kind"] == "publish":
        from hq_api.domain import studio_publish as P

        args["files"] = [
            {**f, "url": P.public_url(hub, UUID(str(f["file_id"])))}
            for f in args.get("files") or []
        ]
    out = {
        "id": str(j["id"]),
        "kind": j["kind"],
        "args": args,
        "timeout_s": j["timeout_s"],
        "created_at": j["created_at"].isoformat(),
        "session_ref": j.get("session_ref"),
        "actor": actor_of(j["actor_kind"], j["actor_code"]).model_dump(),
        "server": str(j["server_id"]),
        "company": j["company"],
    }
    # ⟨2026-11-09⟩ the owner: the companies have no Claude subscription of their own. A Claude Code
    # job runs on the hub's account of the moment (runner_claude_account): its token goes with the
    # job at pickup (over the runner's HTTPS), only into that process's environment; never in the
    # job's stored args, the events or a log. Without a token (or for any other kind) the server's
    # own login is used.
    if j["kind"] == "claude" and claude_token:
        out["claude_oauth"] = claude_token
    return out


def _clean_event(type_: str, data: Any) -> dict[str, Any]:
    d = data if isinstance(data, dict) else {"text": str(data)}
    if type_ in ("stdout", "stderr"):
        text = str(d.get("text") if "text" in d else d.get("data") or "")
        return {"text": mask(text[:MAX_EVENT_TEXT])}
    out = mask_value(d)
    blob = json.dumps(out, ensure_ascii=False, default=str)
    if len(blob) > MAX_EVENT_TEXT:
        out = {
            "truncated": True,
            "type": d.get("type"),
            "summary_fa": str(d.get("summary_fa") or "")[:500],
        }
    return out  # type: ignore[no-any-return]


async def add_events(tx: Tx, j: dict[str, Any], items: list[dict[str, Any]]) -> int:
    """A batch from the runner, numbered by its own seq (a replay is ignored);
    masked before it is stored; a `command` inside a claude job is an Audit
    row and a server.call; a session event joins the job's CodeSession."""
    added = 0
    used = int(
        await tx.scalar(
            "SELECT COALESCE(sum(length(data::text)), 0) FROM infra.server_job_events WHERE job_id = :j",
            j=j["id"],
        )
        or 0
    )
    top = int(j["last_seq"])
    for it in items:
        seq, type_ = int(it["seq"]), str(it["type"])
        data = _clean_event(type_, it.get("data"))
        size = len(json.dumps(data, ensure_ascii=False))
        if used + size > MAX_JOB_EVENTS_BYTES and type_ in ("stdout", "stderr"):
            continue  # the cap: the rest of a flood is not kept (the runner caps too)
        n = await tx.exec(
            """INSERT INTO infra.server_job_events (job_id, company_id, seq, type, data)
               VALUES (:j, :co, :seq, :t, CAST(:d AS jsonb)) ON CONFLICT (job_id, seq) DO NOTHING""",
            j=j["id"],
            co=j["company_id"],
            seq=seq,
            t=type_,
            d=json.dumps(data, ensure_ascii=False, default=str),
        )
        if not n:
            continue
        added += 1
        used += size
        top = max(top, seq)
        if type_ == "session_event" and j["session_id"]:
            await _session_event(tx, j, data)
    if top > int(j["last_seq"]):
        await tx.exec(
            "UPDATE infra.server_jobs SET last_seq = :s WHERE id = :id", s=top, id=j["id"]
        )
    return added


async def _session_event(tx: Tx, j: dict[str, Any], data: dict[str, Any]) -> None:
    from hq_api.workshop import domain as W

    s = await W.load(tx, j["session_id"], lock=True)
    if s["state"] in W.FINAL:
        return
    type_ = str(data.get("type") or "progress")
    if type_ not in SESSION_TYPES:
        type_ = "progress"
    raw = data.get("data")
    inner: dict[str, Any] = raw if isinstance(raw, dict) else {}
    summary = str(data.get("summary_fa") or data.get("summary") or "")[:2000]
    if type_ == "state" and inner.get("session_id"):
        await tx.exec(
            "UPDATE workshop.sessions SET external_id = :x WHERE id = :id",
            x=str(inner["session_id"])[:200],
            id=s["id"],
        )
    await W.append(tx, s, type_, summary, inner, actor=(j["actor_kind"], j["actor_code"]))
    if type_ == "command":
        cmd = mask(str(inner.get("cmd") or ""))[:2000]
        code = inner.get("exit_code")
        secs = inner.get("duration_s")
        ms = int(float(secs) * 1000) if isinstance(secs, int | float) else None
        await audit.record(
            tx,
            principal_of(j["actor_kind"], j["actor_code"]),
            company_id=j["company_id"],
            action="server.command",
            action_class="A2",
            target_kind="server_job",
            target_ref=str(j["id"]),
            summary=f"{j['server_name']} {s['ref']}: {cmd[:300]} -> exit {code} in {ms}ms "
            f"sha256:{hashlib.sha256(cmd.encode()).hexdigest()[:16]}",
        )
        await emit_call(
            tx,
            j,
            cmd=cmd,
            exit_code=code if isinstance(code, int) else None,
            ms=ms,
            state="failed" if isinstance(code, int) and code != 0 else "done",
            tool="server.exec",
            summary=summary or "فرمان در Claude Code",
        )


async def _session_emit(tx: Tx, session_id: UUID) -> None:
    from hq_api.workshop import domain as W

    await W.emit_state(tx, await W.load(tx, session_id))


async def _session_end(
    tx: Tx, j: dict[str, Any], state: str, code: str | None, summary: str
) -> None:
    """The job behind a company-server session ended: done -> the session
    waits for the next message (idle); failed or cancelled -> it ends."""
    from hq_api.workshop import domain as W

    s = await W.load(tx, j["session_id"], lock=True)
    if s["state"] in W.FINAL:
        return
    if state == "idle":
        await tx.exec("UPDATE workshop.sessions SET state = 'idle' WHERE id = :id", id=s["id"])
        s = await W.load(tx, s["id"])
        await W.append(tx, s, "state", summary or "Claude Code کارش را تمام کرد", {"state": "idle"})
        await W.emit_state(tx, s)
        return
    await W.finish(tx, s, state, code, summary)


async def finish(
    tx: Tx,
    hub: Any,
    j: dict[str, Any],
    *,
    exit_code: int | None,
    summary_fa: str | None,
    usage: dict[str, Any] | None,
    data: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    """The runner's result: the job ends (done or failed), its transcript is
    stored, its kind's effect applied (the map, a read's content, the links
    of a netcheck, a publish's external id), its usage recorded."""
    if j["state"] in FINAL:
        return j
    ok = error is None and exit_code is not None and (j["kind"] == "exec" or exit_code == 0)
    state = "done" if ok else "failed"
    err = None
    if error:
        e = str(error).lower()
        err = e if re.fullmatch(r"[a-z][a-z0-9_]{1,40}", e) else "runner_error"
    elif not ok:
        err = "exit_nonzero" if exit_code is not None else "runner_error"
    result: dict[str, Any] | None = None
    data = dict(data or {})
    overflow = data.pop("output_overflow", None)
    if ok:
        result = await _apply(tx, hub, j, data)
    elif j["kind"] == "publish":
        await _apply_publish(tx, j, data or {}, False, err)
    if isinstance(overflow, dict):
        result = {**(result or {}), **await _store_overflow(tx, hub, j, overflow)}
    await tx.exec(
        """UPDATE infra.server_jobs SET state = :st, finished_at = now(), exit_code = :x,
               summary_fa = COALESCE(:s, summary_fa), error_code = :e,
               result = CAST(:r AS jsonb), usage = CAST(:u AS jsonb)
           WHERE id = :id""",
        id=j["id"],
        st=state,
        x=exit_code,
        s=mask(summary_fa)[:2000] if summary_fa else None,
        e=err,
        r=json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
        u=json.dumps(usage, default=str) if usage else None,
    )
    j = await load_job(tx, j["id"])
    await store_transcript(tx, hub, j)
    j = await load_job(tx, j["id"])
    ms = duration_ms(j)
    await audit.record(
        tx,
        principal_of(j["actor_kind"], j["actor_code"]),
        company_id=j["company_id"],
        action="server.job",
        action_class="A2" if j["kind"] in ("exec", "write", "claude", "publish") else "A0",
        target_kind="server_job",
        target_ref=str(j["id"]),
        summary=f"{j['server_name']} {j['kind']} {state}: {shown_cmd(j['kind'], j['args'])[:250]}"
        f" -> exit {exit_code} in {ms}ms sha256:{j['args_sha256'][:16]}",
    )
    if usage:
        await record_usage(tx, j, usage)
    if j["kind"] == "ledger":  # ⟨1.15⟩ §33.2: the payment rows are validated and stored at once
        from hq_api.domain import payments

        await payments.on_job_finished(tx, j)
    if j["session_id"]:
        if ok:
            await _session_end(tx, j, "idle", None, j["summary_fa"] or "")
        else:
            await _session_end(
                tx,
                j,
                "failed",
                err or "runtime_error",
                j["summary_fa"] or "اجرای Claude Code روی سرور نشد",
            )
    await emit_call(tx, j, exit_code=exit_code, ms=ms)
    return j


async def _apply(tx: Tx, hub: Any, j: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    kind = j["kind"]
    if kind == "map":
        m = data.get("map") if isinstance(data.get("map"), dict) else data
        m = mask_value(m)
        user = m.get("user") if isinstance(m, dict) else None
        if not (isinstance(user, str) and re.fullmatch(r"[a-z_][a-z0-9_.-]{0,31}", user)):
            user = None
        await tx.exec(
            """UPDATE infra.servers SET map = CAST(:m AS jsonb), map_at = now(),
                   work_user = COALESCE(:u, work_user)
               WHERE id = :id""",
            id=j["server_id"],
            m=json.dumps(m, ensure_ascii=False, default=str),
            u=user,
        )
        return {"map_at": now().isoformat()}
    if kind == "read":
        content = str(data.get("content") or "")
        enc = str(data.get("encoding") or "utf8")
        out: dict[str, Any] = {
            "path": j["args"].get("path"),
            "size": data.get("size"),
            "sha256": data.get("sha256"),
            "encoding": enc,
        }
        if enc == "utf8":
            masked = mask(content)
            out["content"] = masked[:MAX_READ_INLINE]
            out["truncated"] = len(masked) > MAX_READ_INLINE or bool(data.get("truncated"))
            if len(masked) > MAX_READ_INLINE:
                out["file_id"] = str(
                    await _store_file(tx, hub, j, masked.encode(), "read.txt", "text/plain")
                )
        else:
            out["content"] = None
            out["truncated"] = True
        return out
    if kind == "write":
        return {k: data.get(k) for k in ("path", "size", "sha256", "backup") if k in data}
    if kind == "netcheck":
        links = data.get("links") or data.get("results") or []
        return {"links": await store_links(tx, j, links)}
    if kind == "publish":
        return await _apply_publish(tx, j, data, True, None)
    if kind == "ledger":
        # ⟨1.15⟩ §33.2: the rows are pseudonymous by contract and are validated against
        # seed/payments/ledger_v1.yaml when the money domain ingests them; masking would
        # damage a hash, so only the contract's own keys are kept, as sent
        return {k: data[k] for k in ("contract", "rows", "next_cursor", "has_more") if k in data}
    if kind == "claude":
        sid = data.get("session_id")
        if sid and j["session_id"]:
            await tx.exec(
                "UPDATE workshop.sessions SET external_id = :x WHERE id = :id",
                x=str(sid)[:200],
                id=j["session_id"],
            )
        out = {k: mask_value(data.get(k))
               for k in ("session_id", "files_changed", "answer_chars", "answer_truncated")
               if k in data}  # fmt: skip
        # ⟨2026-11-09⟩ §43 the files a workspace turn sent from out/ (ids; checked by after_job)
        # and the ones it could not (name and why)
        files = data.get("files")
        if isinstance(files, list):
            out["files"] = [str(f)[:36] for f in files if isinstance(f, str)][:40]
        skipped = data.get("files_skipped")
        if isinstance(skipped, list):
            out["files_skipped"] = mask_value(
                [{"name": str(x.get("name"))[:300], "why": str(x.get("why"))[:200]}
                 for x in skipped if isinstance(x, dict)][:40]
            )  # fmt: skip
        answer = mask(str(data.get("result_fa") or ""))
        out["result_fa"] = answer
        if len(answer) > INLINE_ANSWER:
            # the whole answer in the file store, its head inline (full_answer reads it)
            fid = await _store_file(tx, hub, j, answer.encode(), "answer.md", "text/markdown")
            out.update(result_fa=answer[:INLINE_ANSWER], result_file=str(fid))
        return out
    return mask_value({k: v for k, v in data.items() if k != "content"})  # type: ignore[no-any-return]


async def full_answer(tx: Tx, hub: Any, j: dict[str, Any]) -> str:
    """A claude job's whole answer (from the file store when it was too long
    to keep inline in the result)."""
    res = j.get("result") or {}
    if res.get("result_file"):
        key = await tx.scalar(
            "SELECT storage_key FROM files.files WHERE id = CAST(:id AS uuid)",
            id=res["result_file"],
        )
        if key:
            data: bytes = await hub.storage.get(str(key))
            return data.decode("utf-8", "replace")
    return str(res.get("result_fa") or "")


async def _store_overflow(
    tx: Tx, hub: Any, j: dict[str, Any], art: dict[str, Any]
) -> dict[str, Any]:
    """⟨1.10.1⟩ the output that came past the live stream, kept whole as a
    file of the job: masked text up to OVERFLOW_TEXT_MAX, else the runner's
    (already masked) gzip as it came."""
    meta = {
        "bytes": int(art.get("bytes") or 0),
        "kept_from_byte": int(art.get("kept_from_byte") or 0),
        "dropped_bytes": int(art.get("dropped_bytes") or 0),
    }
    try:
        packed = base64.b64decode(str(art.get("b64") or ""), validate=True)
    except (binascii.Error, ValueError):
        return {"output_overflow": {**meta, "stored": False}}
    if not packed:
        return {"output_overflow": {**meta, "stored": False}}

    def unpack() -> bytes | None:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as g:
                raw = g.read(OVERFLOW_TEXT_MAX + 1)
        except (OSError, EOFError):
            return None
        return raw if len(raw) <= OVERFLOW_TEXT_MAX else None

    raw = await asyncio.to_thread(unpack)
    if raw is not None:
        text = await asyncio.to_thread(lambda: mask(raw.decode("utf-8", "replace")))
        fid = await _store_file(tx, hub, j, text.encode(), "output-rest.log", "text/plain")
    else:
        fid = await _store_file(tx, hub, j, packed, "output-rest.log.gz", "application/gzip")
    return {"output_file": str(fid), "output_overflow": {**meta, "stored": True}}


async def _store_file(
    tx: Tx, hub: Any, j: dict[str, Any], data: bytes, suffix: str, mime: str
) -> UUID:
    key, sha = await hub.storage.put(data)
    fid: UUID = await tx.scalar(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code)
           VALUES (:co, :name, :mime, :size, :sha, :key, 'service', 'servers') RETURNING id""",
        co=j["company_id"],
        name=f"job-{str(j['id'])[:8]}-{suffix}",
        mime=mime,
        size=len(data),
        sha=sha,
        key=key,
    )
    return fid


async def store_transcript(tx: Tx, hub: Any, j: dict[str, Any]) -> UUID | None:
    """The job's whole (masked) record, JSON lines, in object storage (§26.3)."""
    if j["transcript_file_id"]:
        return None
    rows = await tx.all(
        "SELECT seq, type, data, at FROM infra.server_job_events WHERE job_id = :j ORDER BY seq",
        j=j["id"],
    )
    head = {
        "job": str(j["id"]),
        "server": f"{j['company']}:{j['server_name']}",
        "kind": j["kind"],
        "actor": f"{j['actor_kind']}:{j['actor_code']}",
        "args": shown_args(j["kind"], j["args"] or {}),
        "state": j["state"],
        "exit_code": j["exit_code"],
        "created_at": j["created_at"].isoformat(),
        "finished_at": j["finished_at"].isoformat() if j["finished_at"] else None,
    }
    lines = [json.dumps(head, ensure_ascii=False, default=str)]
    lines += [
        json.dumps(
            {"seq": r["seq"], "at": r["at"].isoformat(), "type": r["type"], **r["data"]},
            ensure_ascii=False,
            default=str,
        )
        for r in rows
    ]
    data = ("\n".join(lines) + "\n").encode()
    fid = await _store_file(tx, hub, j, data, "transcript.jsonl", "application/x-ndjson")
    await tx.exec(
        "UPDATE infra.server_jobs SET transcript_file_id = :f WHERE id = :id", f=fid, id=j["id"]
    )
    return fid


async def record_usage(tx: Tx, j: dict[str, Any], usage: dict[str, Any]) -> None:
    """A `claude` job's usage (the server's own login) into the Token
    Treasury at its equivalent cost (contract §26.3), and onto its session."""

    def n(k: str) -> int:
        v = usage.get(k)
        return max(0, int(v)) if isinstance(v, int | float) and not isinstance(v, bool) else 0

    inp, out, think = n("input_tokens"), n("output_tokens"), n("thinking_tokens")
    cr, cw = (
        n("cache_read_tokens") or n("cache_read_input_tokens"),
        n("cache_write_tokens") or n("cache_creation_input_tokens"),
    )
    try:
        usd = Decimal(str(usage.get("cost_usd") or usage.get("total_cost_usd") or 0))
    except ArithmeticError:
        usd = Decimal(0)
    if usd < 0:
        usd = Decimal(0)
    if not (inp or out or cr or cw or think or usd):
        return
    await tx.exec(
        """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, work_ref,
               task_class, priority, caller, provider, model, input_tokens, output_tokens,
               cache_read_tokens, cache_write_tokens, thinking_tokens, cost_usd, equiv_cost_usd,
               status, meta)
           VALUES (gen_random_uuid(), COALESCE(:start, now()), now(), :co, :actor, :wr,
                   'server_claude', 3, 'company_runner', 'anthropic', :model, :inp, :out, :cr, :cw,
                   :th, 0, :usd, 'ok', CAST(:meta AS jsonb))""",
        start=j["started_at"],
        co=j["company_id"],
        actor=j["actor_code"],
        wr=j["work_ref"],
        model=str(usage.get("model") or "claude-code")[:100],
        inp=inp,
        out=out,
        cr=cr,
        cw=cw,
        th=think or None,
        usd=usd,
        meta=json.dumps(
            {
                "server_job": str(j["id"]),
                "server": j["server_name"],
                "session": j.get("session_ref"),
                # ⟨20.1⟩ prompt 20 finding 6: whose quota it spent (the
                # server's own Claude Code login, never the hub's) and for what
                "quota": "company_server",
                "via": "catalogue" if j["actor_code"] == "catalogue" else "server_claude",
            }
        ),
    )
    if j["session_id"]:
        await tx.exec(
            """UPDATE workshop.sessions SET usd = usd + :u, input_tokens = input_tokens + :i,
                   output_tokens = output_tokens + :o
               WHERE id = :id""",
            u=usd,
            i=inp,
            o=out,
            id=j["session_id"],
        )


async def sweep(tx: Tx) -> int:
    """Runners that stopped polling go offline; a running job past its
    timeout (and a grace) fails; nothing waits forever."""
    n = 0
    for s in await tx.all(
        SERVER_SQL
        + """ WHERE s.state = 'online' AND (s.last_seen_at IS NULL
                  OR s.last_seen_at < now() - make_interval(secs => :o)) FOR UPDATE OF s""",
        o=ONLINE_S,
    ):
        # ⟨1.24⟩ offline since its last contact
        await tx.exec(
            "UPDATE infra.servers SET state = 'offline', state_since = last_seen_at WHERE id = :id",
            id=s["id"],
        )
        await emit_state(tx, await load_server(tx, s["id"]), prev="online")
        n += 1
    for j in await tx.all(
        JOB_SQL
        + """ WHERE j.state = 'running' AND j.dispatched_at IS NOT NULL
              AND j.dispatched_at < now() - make_interval(secs => j.timeout_s + :g)
              FOR UPDATE OF j SKIP LOCKED""",
        g=DISPATCH_GRACE_S,
    ):
        await tx.exec(
            """UPDATE infra.server_jobs SET state = 'failed', finished_at = now(),
                   error_code = 'timed_out', summary_fa = 'کار در زمانش تمام نشد'
               WHERE id = :id""",
            id=j["id"],
        )
        j = await load_job(tx, j["id"])
        if j["session_id"]:
            await _session_end(tx, j, "failed", "timed_out", "کار در زمانش تمام نشد")
        await emit_call(tx, j)
        n += 1
    return n


# ---------------------------------------------------------------- network --
async def netcheck_targets(tx: Tx, hub_ip: str, server_id: UUID) -> list[dict[str, Any]]:
    """The hub (443) and every other attached server's private address (443, 80)."""
    targets: list[dict[str, Any]] = [{"to": "hub", "host": hub_ip, "port": NETCHECK_HUB_PORT}]
    for o in await tx.all(
        """SELECT id, private_ip FROM infra.servers
           WHERE origin = 'attached' AND id <> :s AND state IS DISTINCT FROM 'revoked'
             AND private_ip IS NOT NULL ORDER BY created_at""",
        s=server_id,
    ):
        targets += [
            {"to": str(o["id"]), "host": o["private_ip"], "port": p} for p in NETCHECK_SERVER_PORTS
        ]
    return targets


async def queue_netchecks(tx: Tx, hub_ip: str, who: Principal) -> list[dict[str, Any]]:
    """A `netcheck` job on every online runner (read-only, free of seals);
    a locked company's server is skipped."""
    out = []
    for s in await tx.all(
        SERVER_SQL + " WHERE s.origin = 'attached' AND s.state = 'online' ORDER BY c.code, s.name"
    ):
        if not online(s):
            continue
        if await tx.scalar("SELECT control.lock_state(:co)", co=s["company_id"]) in (
            "holding",
            "company",
        ):
            continue
        if await tx.scalar(
            """SELECT 1 FROM infra.server_jobs
               WHERE server_id = :s AND kind = 'netcheck' AND state IN ('queued', 'running')""",
            s=s["id"],
        ):
            continue
        targets = await netcheck_targets(tx, hub_ip, s["id"])
        out.append(
            await create_job(
                tx,
                server=s,
                kind="netcheck",
                args={"targets": targets, "timeout_ms": 3000},
                actor_kind=who.kind,
                actor_code=who.code,
                summary="سنجش شبکه",
                timeout_s=120,
            )
        )
    return out


async def store_links(tx: Tx, j: dict[str, Any], links: list[Any]) -> list[dict[str, Any]]:
    stored = []
    wanted = {
        (t.get("to"), int(t.get("port") or 0)): t for t in (j["args"] or {}).get("targets") or []
    }
    for item in links[:500]:
        if not isinstance(item, dict):
            continue
        to = str(item.get("to") or "")
        try:
            port = int(item.get("port") or 0)
        except (TypeError, ValueError):
            continue
        t = wanted.get((to, port))
        if t is None:
            continue  # only what the hub asked for
        ok = bool(item.get("ok"))
        ms = item.get("ms")
        ms = (
            float(ms)
            if isinstance(ms, int | float) and not isinstance(ms, bool) and ms >= 0
            else None
        )
        error = None if ok else str(item.get("error") or "unreachable")[:120]
        # ⟨1.24⟩ §42.2 network.link: when `ok` changes or the link crosses the slow line, at
        # most once a minute; every result of the owner's own check (POST /infra/network/check)
        old = await tx.first(
            """SELECT emitted_ok, emitted_slow,
                      emitted_at > now() - make_interval(secs => :w) AS recent
               FROM infra.network_links WHERE from_server_id = :f AND to_key = :to AND port = :p
               FOR UPDATE""",
            f=j["server_id"],
            to=to,
            p=port,
            w=LINK_WINDOW_S,
        )
        slow = ok and ms is not None and ms >= SLOW_MS
        told = None if old is None else (old["emitted_ok"], bool(old["emitted_slow"]))
        changed = told is None or told[0] is None or told != (ok, slow)
        tell = j["actor_kind"] == "owner" or (changed and not (old is not None and old["recent"]))
        row = await tx.one(
            """INSERT INTO infra.network_links (company_id, from_server_id, to_key, to_ip, port, ok,
                   ms, error, at, last_ok_at, job_id, since, emitted_at, emitted_ok, emitted_slow)
               VALUES (:co, :f, :to, :ip, :p, :ok, :ms, :e, now(), CASE WHEN :ok THEN now() END, :j,
                       now(), CASE WHEN CAST(:tell AS boolean) THEN now() END,
                       CASE WHEN CAST(:tell AS boolean) THEN CAST(:ok AS boolean) END,
                       CASE WHEN CAST(:tell AS boolean) THEN CAST(:slow AS boolean) END)
               ON CONFLICT (from_server_id, to_key, port) DO UPDATE SET to_ip = EXCLUDED.to_ip,
                   ok = EXCLUDED.ok, ms = EXCLUDED.ms, error = EXCLUDED.error, at = EXCLUDED.at,
                   last_ok_at = CASE WHEN EXCLUDED.ok THEN EXCLUDED.at ELSE infra.network_links.last_ok_at END,
                   job_id = EXCLUDED.job_id,
                   since = CASE WHEN infra.network_links.ok = EXCLUDED.ok
                                THEN infra.network_links.since ELSE EXCLUDED.since END,
                   emitted_at = COALESCE(EXCLUDED.emitted_at, infra.network_links.emitted_at),
                   emitted_ok = CASE WHEN CAST(:tell AS boolean) THEN EXCLUDED.emitted_ok
                                     ELSE infra.network_links.emitted_ok END,
                   emitted_slow = CASE WHEN CAST(:tell AS boolean) THEN EXCLUDED.emitted_slow
                                       ELSE infra.network_links.emitted_slow END
               RETURNING since, last_ok_at""",
            co=j["company_id"],
            f=j["server_id"],
            to=to,
            ip=str(t.get("host"))[:45],
            p=port,
            ok=ok,
            ms=ms,
            e=error,
            j=j["id"],
            tell=tell,
            slow=slow,
        )
        if tell:
            await emit_link(tx, j, to, port, ok, ms, error, row["since"], row["last_ok_at"])
        stored.append({"to": to, "port": port, "ok": ok, "ms": ms, "error": error})
    return stored


LINK_ERROR_FA = (
    ("timeout", "در زمانش جواب نداد"),
    ("timed out", "در زمانش جواب نداد"),
    ("refused", "درگاه بسته است؛ اتصال را رد کرد"),
    ("no route", "راهی به آن نیست"),
    ("unreachable", "در دسترس نیست"),
    ("reset", "اتصال را قطع کرد"),
)


def link_error_fa(ok: bool, error: str | None) -> str | None:
    """A failed link's error in plain Persian (never the runner's own words: no address)."""
    if ok:
        return None
    e = (error or "").lower()
    return next((fa for key, fa in LINK_ERROR_FA if key in e), "وصل نشد")


async def emit_link(tx: Tx, j: dict[str, Any], to: str, port: int, ok: bool, ms: float | None,
                    error: str | None, since: datetime, last_ok_at: datetime | None) -> None:  # fmt: skip
    """⟨1.24⟩ §42.2 `network.link` (topic `servers`): the measuring server, the hub or the other
    server by id, the port; never an address."""
    await events.emit(
        tx,
        j["company"],
        "network.link",
        f"{j['server_id']}:{to}:{port}",
        {
            "from": str(j["server_id"]),
            "to": to,
            "port": port,
            "ok": ok,
            "ms": ms,
            "error_fa": link_error_fa(ok, error),
            "since": since.isoformat(),
            "last_ok_at": last_ok_at.isoformat() if last_ok_at else None,
        },
    )


async def after_netcheck(hub: Any, j: dict[str, Any]) -> int:
    """⟨1.24⟩ §42.2 after a netcheck's result (in every company's view: the servers it measured
    belong to any company): an offline server whose reason the new measures change is told again."""
    targets = [
        str(t.get("to"))
        for t in (j.get("args") or {}).get("targets") or []
        if t.get("to") and t.get("to") != "hub"
    ]
    if not targets:
        return 0
    n = 0
    async with hub.db.tx(await hub.companies.ids()) as tx:
        for s in await tx.all(
            SERVER_SQL + " WHERE s.id = ANY(CAST(:ids AS uuid[])) FOR UPDATE OF s",
            ids=sorted(set(targets)),
        ):
            if state_of(s) != "offline" or await reason_of(tx, s) == s.get("state_reason"):
                continue
            await emit_state(tx, s, prev="offline")
            n += 1
    return n


async def network(tx: Tx, hub_ip: str, holding: str) -> dict[str, Any]:
    """GET /infra/network: the nodes (the hub and every attached server) and
    the latest result of each link."""
    servers = await tx.all(SERVER_SQL + " WHERE s.origin = 'attached' ORDER BY c.code, s.name")
    nodes: list[dict[str, Any]] = [
        {
            "id": "hub",
            "company": holding,
            "name": "hub",
            "private_ip": hub_ip,
            "via": None,
            "state": "online",
            "hub_rtt_ms": None,
        }
    ]
    nodes += [
        {
            "id": str(s["id"]),
            "company": s["company"],
            "name": s["name"],
            "private_ip": s["private_ip"],
            "via": s["via"],
            "state": state_of(s),
            "hub_rtt_ms": float(s["hub_rtt_ms"]) if s["hub_rtt_ms"] is not None else None,
        }
        for s in servers
    ]
    links = await tx.all(
        """SELECT l.* FROM infra.network_links l JOIN infra.servers s ON s.id = l.from_server_id
           WHERE s.origin = 'attached'
             AND (l.to_key = 'hub' OR l.port = ANY(CAST(:ports AS int[])))
           ORDER BY l.from_server_id, l.to_key, l.port""",
        ports=list(NETCHECK_SERVER_PORTS),
    )
    at = max((r["at"] for r in links), default=None)
    return {
        "at": at,
        "nodes": nodes,
        "links": [
            {
                "from": str(r["from_server_id"]),
                "to": r["to_key"],
                "port": r["port"],
                "ok": r["ok"],
                "ms": float(r["ms"]) if r["ms"] is not None else None,
                "error": r["error"],
                "at": r["at"],
            }
            for r in links
        ],
    }


# ---------------------------------------------------------------- publish --
async def _apply_publish(tx: Tx, j: dict[str, Any], data: dict[str, Any], ok: bool,
                         error: str | None) -> dict[str, Any]:  # fmt: skip
    """A `publish` job ended (§26.1b): its external id and url on the item."""
    from hq_api.domain import studio_publish as P

    ext = str(data.get("external_id") or "")[:200] or None
    url = str(data.get("url") or "")[:500] or None
    if url and not url.startswith(("https://", "http://")):
        url = None
    await P.runner_published(
        tx, j, ok and bool(ext), ext, url, None if ok and ext else (error or "publish_error")
    )
    return {"external_id": ext, "url": url}


# ----------------------------------------------------------- oversight --
PR_NETWORK = "PR-130"


@C.check(PR_NETWORK)
async def network_links_hold(ctx: C.CheckCtx) -> C.Checked:
    """Every link that worked still works (contract §26.1a): the latest
    measure of each link from a server to the hub or another server; a link
    that failed after having worked is a finding. The daily run also queues
    a fresh `netcheck` on every online runner (measured by the next run)."""
    await queue_netchecks(
        ctx.tx, hub_ip(), Principal(kind="service", code="oversight", role="service")
    )
    rows = await ctx.tx.all(
        """SELECT l.*, s.name AS from_name, c.code AS company, t.name AS to_name
           FROM infra.network_links l JOIN infra.servers s ON s.id = l.from_server_id
           JOIN core.companies c ON c.id = s.company_id
           LEFT JOIN infra.servers t ON l.to_key <> 'hub' AND t.id = CAST(NULLIF(l.to_key, 'hub') AS uuid)
           WHERE NOT l.ok AND l.last_ok_at IS NOT NULL AND s.state IS DISTINCT FROM 'revoked'
           ORDER BY c.code, s.name, l.to_key, l.port"""
    )
    problems = []
    for r in rows:
        target = "hub" if r["to_key"] == "hub" else (r["to_name"] or r["to_key"])
        problems.append(
            C.Problem(
                ctx.holding_id,
                ctx.holding,
                f"پیوند شبکه قطع شد: {r['company']}:{r['from_name']} → {target}:{r['port']}",
                f"{r['company']}:{r['from_name']} could reach {target} ({r['to_ip']}:{r['port']}) "
                f"at {r['last_ok_at'].isoformat()}, and cannot since {r['at'].isoformat()}: "
                f"{r['error'] or 'unreachable'}.",
                f"link-{r['from_server_id']}-{r['to_key']}-{r['port']}",
                [
                    {
                        "kind": "log",
                        "ref": "/infra/network",
                        "note": f"{r['error'] or 'unreachable'}"[:300],
                    }
                ],
            )
        )
    return C.Checked(problems, {ctx.holding: ctx.holding_id})
