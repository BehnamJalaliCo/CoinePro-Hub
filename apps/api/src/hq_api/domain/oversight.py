"""The Chief Overseer (prompt 08 §2, contract §18.1): protocols, their runs,
findings, challenges, the owner's standing orders, holds, compliance and
watch mode.

Rules kept here, in one place:
- A protocol version is a new row (append-only); the owner seals it (step-up)
  or approves a `protocol` decision. The seed (agents/protocols/oversight.yaml)
  only adds refs that do not exist yet.
- A finding is answered by one actor of the company (the protocol's
  answerable role there); it is `verified` only with evidence of the fix,
  and only by the overseer or the owner.
- A hold stops its target until the OWNER releases or cancels it; nobody
  else, the overseer included, can (no API path exists for them). A release
  lets the action go on; a cancel cancels the action itself (contract
  §18.15): nothing held ever runs after a cancel.
- Watch mode holds and stops, never approves; a target the owner released or
  decided in the same watch period is not held again.
- A paused (or draft) protocol is refused on every path: no run, no result,
  no finding (contract §18.15).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from hq_api import audit, events, interactions
from hq_api.db import Tx
from hq_api.domain import notify
from hq_api.domain import recurrence as R
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Model
from hq_api.worker.jalali import to_jalali
from hq_common import oversight_share

AREAS = (
    "truth", "authority", "money", "safety", "quality", "delivery", "security", "data",
    "people", "product", "owner",
)  # fmt: skip
METHODS = ("rule", "sample", "llm", "reconcile", "blind_test", "mystery", "drill")
CODE_METHODS = ("rule", "reconcile")  # checked by code wherever a checker exists
QC_METHODS = ("sample", "blind_test", "mystery", "drill")  # work for QC (the inspector)
SEVERITIES = ("info", "low", "medium", "high", "critical")
SEVERITY_DUE_H = {"critical": 4, "high": 24, "medium": 72, "low": 168, "info": 336}
FINDING_STATUSES = ("open", "acknowledged", "fixing", "fixed", "verified", "disputed", "closed")
ANSWERER_STATUSES = ("acknowledged", "fixing", "fixed", "disputed")
OVERSEER_STATUSES = ("verified", "closed")
OWNER_STATUSES = ("verified", "closed", "disputed")
HOLD_KINDS = ("decision", "session", "work", "employee", "tool", "story")
# A card the overseer holds by itself while the owner is away (watch mode).
WATCH_HOLD_CLASSES = ("A3",)
WATCH_HOLD_KINDS = ("hire", "dismissal", "budget_change", "code_session", "deploy", "protocol")
PROTOCOL_FILE = "protocols/oversight.yaml"
log = logging.getLogger("hq_api.oversight")
# ⟨1.5⟩ the keys a protocol of the file may carry; any other is ignored with a
# warning, never an error (contract §21.12: a later key must not break a seed)
PROTOCOL_KEYS = frozenset(
    {"ref", "area", "method", "schedule", "scope", "severity", "answerable", "status",
     "title_fa", "check", "evidence", "calendar"}
)  # fmt: skip
CALENDARS = ("gregorian", "jalali")
OVERSEER = "OVR"
QC = "OVS-MGR"


# ------------------------------------------------------------------ models --
class LastRun(BaseModel):
    """A protocol's last finished run (contract §18.15: never `skipped`)."""

    at: datetime
    result: Literal["pass", "fail", "partial", "deferred"]
    findings: int


class Protocol(BaseModel):
    id: UUID
    ref: str
    title_fa: str
    area: str
    check_md: str
    method: str
    schedule: str
    scope: str
    evidence_md: str
    severity: str
    answerable: str
    status: str
    version: int
    sealed_at: datetime | None
    last_run: LastRun | None = None
    # ⟨1.5⟩ jalali: BYMONTHDAY is a day of the Jalali month (contract §21.12)
    calendar: Literal["gregorian", "jalali"] = "gregorian"


class ProtocolIn(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    area: Literal[
        "truth", "authority", "money", "safety", "quality", "delivery", "security", "data",
        "people", "product", "owner",
    ]  # fmt: skip
    check_md: str = Field(min_length=1, max_length=20000)
    method: Literal["rule", "sample", "llm", "reconcile", "blind_test", "mystery", "drill"]
    schedule: str = Field(min_length=6, max_length=200)
    scope: Literal["holding", "company", "department"]
    evidence_md: str = Field(default="", max_length=5000)
    severity: Literal["info", "low", "medium", "high", "critical"]
    answerable: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    status: Literal["active", "paused", "draft"] = "active"
    calendar: Literal["gregorian", "jalali"] = "gregorian"


class Evidence(Model):
    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=1000)


class HistoryItem(BaseModel):
    at: datetime
    by: Actor
    status: str
    note: str


class FindingFix(BaseModel):
    kind: Literal["work", "workshop", "decision"]
    ref: str | None = None
    summary_fa: str | None = None


class Finding(BaseModel):
    id: UUID
    ref: str
    company: str
    protocol: str | None
    severity: str
    title_fa: str
    body_md: str
    evidence: list[dict[str, Any]]
    status: str
    answerable: Actor
    due_at: datetime
    opened_at: datetime
    closed_at: datetime | None
    history: list[HistoryItem] = Field(default_factory=list)
    # ⟨1.10⟩ §28.3 the watch: its kind, and the overseer's proposed fix (in
    # words, and as something for the owner's seal: a work item, a Code
    # Workshop session or a card)
    kind: Literal["security", "app_health", "code", "growth", "holding"] | None = None
    fix_md: str | None = None
    fix: FindingFix | None = None


class Challenge(BaseModel):
    id: UUID
    ref: str
    company: str
    period: str
    title_fa: str
    brief_md: str
    criteria: list[dict[str, Any]]
    due_at: datetime
    status: str
    score: int | None
    judge: Actor
    work_ref: str | None


class StandingOrder(BaseModel):
    id: UUID
    ref: str
    text_md: str
    source: str
    file_id: UUID | None
    applies_to: str
    status: str
    version: int
    sealed_at: datetime | None


class HoldAction(BaseModel):
    kind: str
    ref: str
    summary_fa: str
    payload_digest: str | None


class Hold(BaseModel):
    id: UUID
    ref: str
    company: str
    action: HoldAction
    reason_md: str
    held_by: Actor
    held_at: datetime
    watch: bool
    state: str
    decided_by: Actor | None
    decided_at: datetime | None


class Compliance(BaseModel):
    company: str
    score: float
    by_area: dict[str, float]
    findings_open: dict[str, int]
    protocols: dict[str, int]
    trend: list[float]


class WatchReport(BaseModel):
    on: bool
    since: datetime | None
    until: datetime | None
    reason: str | None
    summary_md: str
    held: list[str]
    urgent: list[str]
    findings: list[str]
    report_at: datetime | None


def _who(kind: str, code: str) -> Actor:
    if kind == "owner":
        return Actor(kind="owner", code="owner", display_fa="مدیر کل")
    if kind == "system":
        return Actor(kind="service", code=code)
    return Actor(kind="agent", code=code)


def _kind_of(who: Principal) -> str:
    return "owner" if who.is_owner else ("agent" if who.is_agent else "system")


# --------------------------------------------------------------- protocols --
PROTOCOL_SQL = """
    SELECT p.*, r.started_at AS last_at, r.result AS last_result, r.findings AS last_findings
    FROM oversight.current_protocols p
    LEFT JOIN LATERAL (
        SELECT started_at, result, findings FROM oversight.protocol_runs pr
        WHERE pr.protocol_ref = p.ref AND pr.result <> 'pending'
        ORDER BY pr.started_at DESC LIMIT 1
    ) r ON true
"""


def render_protocol(r: dict[str, Any]) -> Protocol:
    last = None
    if r.get("last_at"):
        last = LastRun(at=r["last_at"], result=r["last_result"], findings=r["last_findings"])
    return Protocol(
        id=r["id"],
        ref=r["ref"],
        title_fa=r["title_fa"],
        area=r["area"],
        check_md=r["check_md"],
        method=r["method"],
        schedule=r["schedule"],
        scope=r["scope"],
        evidence_md=r["evidence_md"],
        severity=r["severity"],
        answerable=r["answerable"],
        status=r["status"],
        version=r["version"],
        sealed_at=r["sealed_at"],
        last_run=last,
        calendar=r.get("calendar") or "gregorian",
    )


def protocol_file(root: str | Path) -> list[dict[str, Any]]:
    """The protocols of agents/protocols/oversight.yaml (data, read-only)."""
    path = Path(root) / PROTOCOL_FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for p in data.get("protocols") or []:
        unknown = sorted(set(p) - PROTOCOL_KEYS)
        if unknown:
            log.warning("protocol %s: unknown keys ignored: %s", p.get("ref"), ", ".join(unknown))
        calendar = str(p.get("calendar") or "gregorian")
        if calendar not in CALENDARS:
            log.warning("protocol %s: unknown calendar %r, gregorian used", p.get("ref"), calendar)
            calendar = "gregorian"
        out.append(
            {
                "ref": str(p["ref"]),
                "title_fa": str(p["title_fa"]),
                "area": str(p["area"]),
                "check_md": " ".join(str(p["check"]).split()),
                "method": str(p["method"]),
                "schedule": str(p["schedule"]),
                "scope": str(p["scope"]),
                "evidence_md": str(p.get("evidence") or ""),
                "severity": str(p["severity"]),
                "answerable": str(p["answerable"]),
                "status": str(p.get("status") or "active"),
                "calendar": calendar,
            }
        )
    return out


def validate_protocol(data: dict[str, Any]) -> dict[str, Any]:
    """ProtocolIn plus a schedule the scheduler can run (an RRULE of §14)."""
    p = ProtocolIn.model_validate(data).model_dump()
    try:
        R.parse(p["schedule"])
    except ApiError as exc:
        raise ApiError(
            422, "validation_failed", fields={"schedule": "not a supported RRULE"}
        ) from exc
    return p


async def seed_protocols(tx: Tx, holding_id: UUID, root: str | Path) -> int:
    """Version 1 of every protocol of the file whose ref does not exist yet
    (later versions are the owner's; the seed never overwrites them)."""
    added = 0
    for p in protocol_file(root):
        if await tx.scalar("SELECT 1 FROM oversight.protocols WHERE ref = :r", r=p["ref"]):
            continue
        validate_protocol({k: v for k, v in p.items() if k != "ref"})
        await tx.exec(
            """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md,
                   method, schedule, scope, evidence_md, severity, answerable, status, source,
                   created_by_kind, created_by_code, calendar)
               VALUES (:co, :ref, 1, :title_fa, :area, :check_md, :method, :schedule, :scope,
                       :evidence_md, :severity, :answerable, :status, 'seed', 'service', 'seed',
                       :calendar)""",
            co=holding_id,
            **p,
        )
        added += 1
    await activate_pr082(tx)
    from hq_api.domain import dceo  # ⟨1.5⟩ prompt 12 §13: PR-121 on a fresh database

    await dceo.activate(tx)
    return added


# ⟨1.5⟩ prompt 12 §6.7: PR-082 (the monthly HR round) becomes active on the 3rd
# of the Jalali month, a new version over the seeded, paused one. Migration
# 0027_1 does the same on a database seeded before it; this covers a fresh one.
# It never runs on its own while the holding is locked (protocol_run skips).
PR082 = "PR-082"
PR082_SCHEDULE = "FREQ=MONTHLY;BYMONTHDAY=3;BYHOUR=10;BYMINUTE=0"
PR082_CHECK = (
    "Each month's HR round ran for every active operating company and the holding, with its "
    "monthly HR report, and an `evaluation` card for every flagged employee (and only with "
    "evidence and `override_reason` for an unflagged one)."
)


async def activate_pr082(tx: Tx) -> bool:
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended('hq:protocol:PR-082', 0))")
    cur = await tx.first("SELECT * FROM oversight.current_protocols WHERE ref = :r", r=PR082)
    if cur is None or cur["version"] != 1 or cur["source"] != "seed" or cur["status"] != "paused":
        return False
    await tx.exec(
        """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
               schedule, scope, evidence_md, severity, answerable, status, source, created_by_kind,
               created_by_code, calendar)
           VALUES (:co, :ref, 2, :title, :area, :check, :method, :schedule, :scope, :evidence,
                   :severity, :answerable, 'active', 'seed', 'service', 'prompt-12', 'jalali')""",
        co=cur["company_id"],
        ref=PR082,
        title=cur["title_fa"],
        area=cur["area"],
        check=PR082_CHECK,
        method=cur["method"],
        schedule=PR082_SCHEDULE,
        scope=cur["scope"],
        evidence=cur["evidence_md"],
        severity=cur["severity"],
        answerable=cur["answerable"],
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=cur["company_id"],
        action="oversight.protocol_activate",
        action_class="A1",
        target_kind="protocol",
        target_ref=f"{PR082}@2",
        summary="prompt 12: active on the 3rd of the Jalali month",
    )
    return True


def jalali_due(p: dict[str, Any], today: date) -> bool:
    """A `jalali` protocol runs only on its BYMONTHDAY of the Jalali month
    (its Temporal schedule fires daily at the hour); a gregorian one always."""
    if (p.get("calendar") or "gregorian") != "jalali":
        return True
    days = R.parse(p["schedule"]).by_month_day
    return not days or to_jalali(today)[2] in days


async def protocols(
    tx: Tx, *, area: str | None = None, status: str | None = None
) -> list[Protocol]:
    rows = await tx.all(
        PROTOCOL_SQL
        + " WHERE (CAST(:a AS text) IS NULL OR p.area = :a) AND (CAST(:s AS text) IS NULL OR p.status = :s)"
        " ORDER BY p.ref",
        a=area,
        s=status,
    )
    return [render_protocol(r) for r in rows]


async def load_protocol(tx: Tx, ref: str) -> dict[str, Any]:
    return await tx.one(PROTOCOL_SQL + " WHERE p.ref = :r", r=ref, not_found="not_found")


async def protocol_in_force(tx: Tx, ref: str) -> dict[str, Any] | None:
    """The protocol's current version when it is `active`; None when it is
    paused, a draft or unknown (every event-driven path skips it then)."""
    p = await tx.first(PROTOCOL_SQL + " WHERE p.ref = :r", r=ref)
    return p if p is not None and p["status"] == "active" else None


def require_active(p: dict[str, Any]) -> None:
    """A paused protocol has no run, no result and no finding (§18.15)."""
    if p.get("status") != "active":
        raise ApiError(
            409,
            "validation_failed",
            f"protocol {p.get('ref')} is {p.get('status')}",
            fields={"protocol": f"{p.get('status')}: no run, result or finding"},
        )


async def new_version(
    tx: Tx,
    who: Principal,
    holding_id: UUID,
    data: dict[str, Any],
    *,
    ref: str | None,
    source: Literal["owner", "decision"],
    step_up_id: UUID | None = None,
    decision_id: UUID | None = None,
) -> dict[str, Any]:
    """A new protocol (ref None: the next PR- number) or a new version of one
    (an edit, a pause or a resume), sealed now."""
    p = validate_protocol(data)
    if ref is None:
        n = await tx.scalar(
            "SELECT coalesce(max(substring(ref from 4)::int), 0) + 1 FROM oversight.protocols"
        )
        ref = f"PR-{n:03d}"
        version = 1
    else:
        current = await tx.scalar(
            "SELECT max(version) FROM oversight.protocols WHERE ref = :r", r=ref
        )
        if current is None:
            raise ApiError(404, "not_found", f"protocol {ref}")
        version = int(current) + 1
    await tx.exec(
        """INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method,
               schedule, scope, evidence_md, severity, answerable, status, source, sealed_at,
               sealed_step_up_id, decision_id, created_by_kind, created_by_code, calendar)
           VALUES (:co, :ref, :v, :title_fa, :area, :check_md, :method, :schedule, :scope, :evidence_md,
                   :severity, :answerable, :status, :src, now(), :su, :dec, :bk, :bc, :calendar)""",
        co=holding_id,
        ref=ref,
        v=version,
        src=source,
        su=step_up_id,
        dec=decision_id,
        bk="owner" if who.is_owner else "service",
        bc=who.code,
        **p,
    )
    return await load_protocol(tx, ref)


# ------------------------------------------------------------------- runs --
async def start_run(
    tx: Tx, protocol: dict[str, Any], *, by_kind: str = "system", by_code: str = "oversight"
) -> dict[str, Any]:
    return await tx.one(
        """INSERT INTO oversight.protocol_runs (company_id, protocol_id, protocol_ref, version, method,
               by_kind, by_code)
           VALUES (:co, :p, :ref, :v, :m, :bk, :bc) RETURNING *""",
        co=protocol["company_id"],
        p=protocol["id"],
        ref=protocol["ref"],
        v=protocol["version"],
        m=protocol["method"],
        bk=by_kind,
        bc=by_code,
    )


async def finish_run(
    tx: Tx,
    run_id: UUID,
    result: str,
    *,
    findings: int = 0,
    per_company: dict[str, str] | None = None,
    notes: str = "",
    by: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return await tx.one(
        """UPDATE oversight.protocol_runs SET result = :res, finished_at = now(), findings = :f,
               per_company = CAST(:pc AS jsonb), notes = :n,
               by_kind = coalesce(:bk, by_kind), by_code = coalesce(:bc, by_code)
           WHERE id = :id RETURNING *""",
        id=run_id,
        res=result,
        f=findings,
        pc=json.dumps(per_company or {}),
        n=notes[:20000],
        bk=by[0] if by else None,
        bc=by[1] if by else None,
    )


def per_company_result(result: str, covered: list[str], failing: list[str]) -> dict[str, str]:
    """A model run's pass or fail for every company it covered (contract
    §18.15): a company with one of the run's findings fails; a `fail` with no
    finding named fails every covered company; the others pass."""
    out = dict.fromkeys(covered, "fail" if result == "fail" and not failing else "pass")
    out |= dict.fromkeys(failing, "fail")
    return out


async def oversight_tokens_today(tx: Tx) -> int:
    """Tokens the overseer and QC moved today (UTC, the day of the agents'
    daily cap): every model call of their runs, from the router's ledger."""
    n = await tx.scalar(
        """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                               + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
           FROM llm.calls
           WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
             AND meta ? 'run_id' AND split_part(meta ->> 'charter', '@', 1) = ANY(:roles)""",
        roles=list(oversight_share.ROLES),
    )
    return int(n or 0)


async def share_spent(tx: Tx, daily_cap: int, share: float) -> bool:
    """The oversight share of today's token cap is used up (prompt 08 §2.3;
    a cap of 0 is nothing, so its share is spent from the start)."""
    if oversight_share.limit(daily_cap, share) <= 0:
        return True
    return oversight_share.spent(await oversight_tokens_today(tx), daily_cap, share)


async def deferred_due(tx: Tx) -> list[str]:
    """Protocols whose latest run was deferred before today (UTC): the next
    day they go first, the most severe and the oldest first."""
    rows = await tx.all(
        """SELECT r.protocol_ref AS ref FROM (
               SELECT DISTINCT ON (protocol_ref) protocol_ref, result, started_at
               FROM oversight.protocol_runs ORDER BY protocol_ref, started_at DESC) r
           JOIN oversight.current_protocols p ON p.ref = r.protocol_ref AND p.status = 'active'
           WHERE r.result = 'deferred'
             AND r.started_at < date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
           ORDER BY array_position(CAST(:sev AS text[]), p.severity), r.started_at""",
        sev=list(reversed(SEVERITIES)),
    )
    return [str(r["ref"]) for r in rows]


def run_tokens(charters: Any, role: str, configured: int) -> int:
    """A protocol run's work budget: HQ_OVERSIGHT_RUN_TOKENS, never above the
    assignee's charter (tokens_per_run; overseer v2 and advisor v3: 200K)."""
    charter = charters.get(role) if charters is not None else None
    if charter is None:
        return configured
    cap: int = charter.limits.tokens_per_run
    return max(1, min(configured, cap))


async def model_runs_today(tx: Tx, tz: str) -> int:
    """Protocol runs handed to the overseer or QC today (owner's day), counted
    under a transaction lock so that two runs never both take the last place."""
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended('oversight:model_runs', 0))")
    start = day_start(datetime.now(UTC), tz)
    n: int = await tx.scalar(
        "SELECT count(*) FROM oversight.protocol_runs WHERE work_id IS NOT NULL AND started_at >= :s",
        s=start,
    )
    return n


def day_start(now: datetime, tz: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz))
    return datetime(local.year, local.month, local.day, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def week_key(now: datetime, tz: str) -> date:
    """The Saturday that starts the owner's week (Saturday to Friday)."""
    local = now.astimezone(ZoneInfo(tz)).date()
    return local - timedelta(days=(local.weekday() - 5) % 7)


# ---------------------------------------------------------------- findings --
FINDING_SQL = """
    SELECT f.*, c.code AS company, p.ref AS protocol
    FROM oversight.findings f JOIN core.companies c ON c.id = f.company_id
    LEFT JOIN oversight.protocols p ON p.id = f.protocol_id
"""


def render_finding(r: dict[str, Any], history: list[dict[str, Any]] | None = None) -> Finding:
    return Finding(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        protocol=r["protocol"],
        severity=r["severity"],
        title_fa=r["title_fa"],
        body_md=r["body_md"],
        evidence=list(r["evidence"] or []),
        status=r["status"],
        answerable=_who(r["answerable_kind"], r["answerable_code"]),
        due_at=r["due_at"],
        opened_at=r["opened_at"],
        closed_at=r["closed_at"],
        history=[
            HistoryItem(
                at=h["at"], by=_who(h["by_kind"], h["by_code"]), status=h["status"], note=h["note"]
            )
            for h in history or []
        ],
        kind=r.get("kind"),
        fix_md=r.get("fix_md"),
        fix=FindingFix.model_validate(r["fix"]) if r.get("fix") else None,
    )


async def load_finding(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        FINDING_SQL + " WHERE f.ref = :r" + (" FOR UPDATE OF f" if lock else ""),
        r=ref,
        not_found="not_found",
    )


async def history_of(tx: Tx, finding_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        "SELECT at, by_kind, by_code, status, note, evidence FROM oversight.finding_history"
        " WHERE finding_id = :f ORDER BY at, id",
        f=finding_id,
    )


async def answerer(tx: Tx, company_id: UUID, role: str | None) -> tuple[str, str]:
    """Who answers a finding in this company: the employee of the protocol's
    role (charter role, else kind), else the CEO, else the owner."""
    if role:
        code = await tx.scalar(
            """SELECT code FROM core.employees WHERE company_id = :co AND status = 'active'
                 AND (role = :r OR kind = :r) ORDER BY kind = :r DESC, created_at LIMIT 1""",
            co=company_id,
            r=role,
        )
        if code:
            return "agent", str(code)
    ceo = await tx.scalar(
        "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active'"
        " ORDER BY created_at LIMIT 1",
        co=company_id,
    )
    return ("agent", str(ceo)) if ceo else ("owner", "owner")


async def raise_finding(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    severity: str,
    title_fa: str,
    body_md: str = "",
    evidence: list[dict[str, Any]] | None = None,
    protocol: dict[str, Any] | None = None,
    run_id: UUID | None = None,
    answerable: str | None = None,
    due_in_hours: int | None = None,
    by_kind: str = "system",
    by_code: str = "oversight",
    dedupe_key: str | None = None,
    kind: str | None = None,
    fix_md: str | None = None,
    fix: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """(the finding, created?). A finding still open with the same key is the
    same finding: ⟨1.7.5⟩ its evidence brought up to date, not duplicated (an
    hourly rule found again), and no new notification. Only a higher severity
    opens a new finding (its key `<key>:<severity>`, as one key is open once;
    the owner hears of it); a closed one found again opens anew. A protocol
    that is not active raises nothing (409)."""
    if protocol is not None:
        require_active(protocol)
    if dedupe_key:
        dedupe_key = dedupe_key[:180]
        same = await tx.first(
            FINDING_SQL
            + " WHERE f.company_id = :co AND f.dedupe_key = ANY(CAST(:keys AS text[]))"
            + " AND f.status NOT IN ('verified', 'closed')"
            + " ORDER BY f.opened_at DESC LIMIT 1 FOR UPDATE OF f",
            co=company_id,
            keys=[dedupe_key, *(f"{dedupe_key}:{s}" for s in SEVERITIES)],
        )
        if same and SEVERITIES.index(severity) <= SEVERITIES.index(same["severity"]):
            return await _found_again(tx, same, evidence), False
        if same:
            dedupe_key = f"{dedupe_key}:{severity}"
    role = answerable or (protocol or {}).get("answerable")
    if answerable and "-" in answerable:  # an employee code given explicitly
        exists = await tx.scalar(
            "SELECT 1 FROM core.employees WHERE code = :c AND company_id = :co",
            c=answerable,
            co=company_id,
        )
        ak, ac = ("agent", answerable) if exists else await answerer(tx, company_id, None)
    else:
        ak, ac = await answerer(tx, company_id, role)
    hours = due_in_hours or SEVERITY_DUE_H.get(severity, 72)
    row = await tx.one(
        """INSERT INTO oversight.findings (company_id, protocol_id, run_id, severity, title_fa, body_md,
               evidence, answerable_kind, answerable_code, raised_by_kind, raised_by_code, dedupe_key,
               due_at, kind, fix_md, fix)
           VALUES (:co, :p, :run, :sev, :t, :b, CAST(:ev AS jsonb), :ak, :ac, :bk, :bc, :k,
                   now() + make_interval(hours => :h), :kind, :fix_md, CAST(:fix AS jsonb))
           RETURNING id, ref""",
        kind=kind,
        fix_md=fix_md[:20000] if fix_md else None,
        fix=json.dumps(fix, ensure_ascii=False) if fix else None,
        co=company_id,
        p=(protocol or {}).get("id"),
        run=run_id,
        sev=severity,
        t=title_fa[:300],
        b=body_md[:20000],
        ev=json.dumps(evidence or [], ensure_ascii=False),
        ak=ak,
        ac=ac,
        bk=by_kind,
        bc=by_code,
        k=dedupe_key[:200] if dedupe_key else None,
        h=hours,
    )
    await tx.exec(
        """INSERT INTO oversight.finding_history (finding_id, company_id, by_kind, by_code, status, note,
               evidence)
           VALUES (:f, :co, :bk, :bc, 'open', :n, CAST(:ev AS jsonb))""",
        f=row["id"],
        co=company_id,
        bk=by_kind,
        bc=by_code,
        n="",
        ev=json.dumps(evidence or [], ensure_ascii=False),
    )
    await events.emit(
        tx,
        company_code,
        "oversight.finding",
        row["ref"],
        {"severity": severity, "status": "open", "protocol": (protocol or {}).get("ref")},
    )
    f = await load_finding(tx, row["ref"])
    await _tell_owner(tx, f, company_code, by_kind, by_code)
    return f, True


def notice_level(f: dict[str, Any]) -> str:
    """⟨1.7.5⟩ A finding asks the owner to decide only when the owner answers
    it; one an employee answers is a report."""
    return "decision" if f["answerable_kind"] == "owner" else "report"


async def _tell_owner(
    tx: Tx, f: dict[str, Any], company_code: str, by_kind: str, by_code: str
) -> None:
    severity = f["severity"]
    if severity not in ("critical", "high"):
        return
    label = "بحرانی" if severity == "critical" else "جدی"
    await notify.raise_notification(
        tx,
        company_id=f["company_id"],
        company_code=company_code,
        level=notice_level(f),
        title_fa=f"یافته‌ی {label} ناظر کل: {f['title_fa']}"[:300],
        body_fa=str(f["body_md"] or "")[:1000],
        link_kind="finding",
        link_ref=f["ref"],
        source_kind="agent" if by_kind == "agent" else "system",
        source_code=by_code,
    )


async def _found_again(
    tx: Tx, f: dict[str, Any], evidence: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """The same open finding seen again: its evidence becomes today's (its
    text and severity stay as raised: they are immutable)."""
    if evidence:
        await tx.exec(
            """UPDATE oversight.findings SET evidence = CAST(:ev AS jsonb), updated_at = now()
               WHERE id = :id""",
            id=f["id"],
            ev=json.dumps(evidence, ensure_ascii=False),
        )
    return await load_finding(tx, f["ref"])


def _has_fix_evidence(history: list[dict[str, Any]]) -> bool:
    """A `fixed` step that carried its evidence (the verifier's own evidence
    never counts: verifying is checking someone else's fix)."""
    return any(h["status"] == "fixed" and list(h["evidence"] or []) for h in history)


async def in_chain(tx: Tx, f: dict[str, Any], code: str) -> bool:
    """The finding's answerable, or one of its managers up the chain (the
    company's CEO is the top of every chain)."""
    if f["answerable_kind"] != "agent":
        return False
    if f["answerable_code"] == code:
        return True
    return bool(
        await tx.scalar(
            """WITH RECURSIVE up AS (
                   SELECT e.id, e.reports_to, 0 AS depth FROM core.employees e WHERE e.code = :a
                   UNION ALL
                   SELECT m.id, m.reports_to, up.depth + 1 FROM core.employees m
                   JOIN up ON m.id = up.reports_to WHERE up.depth < 20)
               SELECT 1 FROM core.employees x
               WHERE x.code = :me AND x.company_id = :co AND x.status = 'active'
                 AND (x.id IN (SELECT id FROM up) OR x.kind = 'ceo')""",
            a=f["answerable_code"],
            me=code,
            co=f["company_id"],
        )
    )


async def update_finding(
    tx: Tx,
    who: Principal,
    ref: str,
    status: str,
    note: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Only the answerable (or its chain of command) moves it: acknowledged,
    fixing, fixed (with evidence of the fix), disputed. The overseer verifies
    only a `fixed` that carried evidence, and closes; the owner verifies,
    closes or disputes (contract §18.15)."""
    f = await load_finding(tx, ref, lock=True)
    if f["status"] == "closed":
        raise ApiError(409, "validation_failed", f"{ref} is closed")
    evidence = evidence or []
    if who.is_owner:
        if status not in OWNER_STATUSES:
            raise ApiError(
                422, "validation_failed", fields={"status": "owner: verified, closed or disputed"}
            )
    elif who.is_agent and status in OVERSEER_STATUSES:
        if who.role != "overseer":
            raise ApiError(
                403, "policy_denied", "only the overseer or the owner verifies or closes"
            )
    elif who.is_agent and status in ANSWERER_STATUSES:
        if not await in_chain(tx, f, who.code):
            raise ApiError(
                403, "policy_denied", "only the answerable or its chain of command answers"
            )
    elif who.is_agent:
        raise ApiError(422, "validation_failed", fields={"status": "not a finding status"})
    else:
        raise ApiError(403, "forbidden")
    if status == "fixed" and not evidence:
        raise ApiError(
            422, "validation_failed", fields={"evidence": "fixed needs evidence of the fix"}
        )
    if status == "verified" and (
        f["status"] != "fixed" or not _has_fix_evidence(await history_of(tx, f["id"]))
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"evidence": "verified only after a `fixed` that carried evidence of the fix"},
        )
    all_evidence = list(f["evidence"] or []) + evidence
    await tx.exec(
        """UPDATE oversight.findings SET status = :s, evidence = CAST(:ev AS jsonb), updated_at = now(),
               closed_at = CASE WHEN :s = 'closed' THEN now() ELSE NULL END
           WHERE id = :id""",
        id=f["id"],
        s=status,
        ev=json.dumps(all_evidence, ensure_ascii=False),
    )
    await tx.exec(
        """INSERT INTO oversight.finding_history (finding_id, company_id, by_kind, by_code, status, note,
               evidence)
           VALUES (:f, :co, :bk, :bc, :s, :n, CAST(:ev AS jsonb))""",
        f=f["id"],
        co=f["company_id"],
        bk=_kind_of(who),
        bc=who.code,
        s=status,
        n=note[:5000],
        ev=json.dumps(evidence, ensure_ascii=False),
    )
    await events.emit(
        tx, f["company"], "oversight.finding", ref, {"severity": f["severity"], "status": status}
    )
    return await load_finding(tx, ref)


# --------------------------------------------------------------- challenges --
CHALLENGE_SQL = """
    SELECT ch.*, c.code AS company, w.ref AS work_ref
    FROM oversight.challenges ch JOIN core.companies c ON c.id = ch.company_id
    LEFT JOIN work.work w ON w.id = ch.work_id
"""


def render_challenge(r: dict[str, Any]) -> Challenge:
    return Challenge(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        period=r["period"],
        title_fa=r["title_fa"],
        brief_md=r["brief_md"],
        criteria=list(r["criteria"] or []),
        due_at=r["due_at"],
        status=r["status"],
        score=r["score"],
        judge=_who(r["judge_kind"], r["judge_code"]),
        work_ref=r["work_ref"],
    )


async def load_challenge(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        CHALLENGE_SQL + " WHERE ch.ref = :r" + (" FOR UPDATE OF ch" if lock else ""),
        r=ref,
        not_found="not_found",
    )


async def issue_challenge(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    company_code: str,
    period: str,
    title_fa: str,
    brief_md: str,
    criteria: list[dict[str, Any]],
    due_at: datetime,
    judge: str | None,
    tz: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    if due_at <= now:
        raise ApiError(422, "validation_failed", fields={"due_at": "in the future"})
    key = (
        week_key(now, tz)
        if period == "week"
        else now.astimezone(ZoneInfo(tz)).date().replace(day=1)
    )
    judge_code = judge or who.code
    row = await tx.one(
        """INSERT INTO oversight.challenges (company_id, period, period_key, title_fa, brief_md, criteria,
               due_at, judge_kind, judge_code, issued_by_code)
           VALUES (:co, :p, :k, :t, :b, CAST(:cr AS jsonb), :due, 'agent', :j, :by) RETURNING ref""",
        co=company_id,
        p=period,
        k=key,
        t=title_fa[:300],
        b=brief_md[:20000],
        cr=json.dumps(criteria, ensure_ascii=False),
        due=due_at,
        j=judge_code,
        by=who.code,
    )
    return await load_challenge(tx, row["ref"])


async def submit_challenge(
    tx: Tx, who: Principal, ref: str, work_id: UUID | None, note: str
) -> dict[str, Any]:
    try:
        ch = await load_challenge(tx, ref, lock=True)
    except ApiError as exc:  # another company's (RLS) or none: the same answer
        raise ApiError(403, "policy_denied", "not this company's challenge") from exc
    if ch["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "another company's challenge")
    if ch["status"] not in ("issued", "accepted"):
        raise ApiError(409, "validation_failed", f"{ref} is {ch['status']}")
    await tx.exec(
        """UPDATE oversight.challenges SET status = 'submitted', work_id = :w, submit_note = :n,
               submitted_at = now(), updated_at = now() WHERE id = :id""",
        id=ch["id"],
        w=work_id,
        n=note[:5000],
    )
    return await load_challenge(tx, ref)


async def score_challenge(
    tx: Tx, who: Principal, ref: str, score: int, notes: str
) -> dict[str, Any]:
    ch = await load_challenge(tx, ref, lock=True)
    # The challenge's judge scores it (the overseer may too); QC scores only
    # the challenges it judges (prompt 08.1 §4).
    if not (who.code == ch["judge_code"] or who.role == "overseer"):
        raise ApiError(403, "policy_denied", "the judge scores")
    if ch["status"] not in ("submitted", "missed"):
        raise ApiError(409, "validation_failed", f"{ref} is {ch['status']}")
    await tx.exec(
        """UPDATE oversight.challenges SET status = 'scored', score = :s, score_notes = :n,
               scored_at = now(), updated_at = now() WHERE id = :id""",
        id=ch["id"],
        s=score,
        n=notes[:5000],
    )
    return await load_challenge(tx, ref)


async def sweep_missed(tx: Tx) -> int:
    """Challenges past due without a submission are missed (score 0 for the
    company score, unless the judge scores them later)."""
    return await tx.exec(
        """UPDATE oversight.challenges SET status = 'missed', updated_at = now()
           WHERE status IN ('issued', 'accepted') AND due_at < now()"""
    )


# ------------------------------------------------------------ standing orders --
def render_order(r: dict[str, Any]) -> StandingOrder:
    return StandingOrder(
        id=r["id"],
        ref=r["ref"],
        text_md=r["text_md"],
        source=r["source"],
        file_id=r["file_id"],
        applies_to=r["applies_to"],
        status=r["status"],
        version=r["version"],
        sealed_at=r["sealed_at"],
    )


async def sealed_orders(tx: Tx, role_kind: str) -> list[dict[str, Any]]:
    """Sealed standing orders for a role: the overseer's own and those for all."""
    applies = ["all", "overseer"] if role_kind == "overseer" else ["all"]
    return await tx.all(
        "SELECT ref, text_md, applies_to FROM oversight.orders WHERE status = 'sealed'"
        " AND applies_to = ANY(:a) ORDER BY sealed_at, ref",
        a=applies,
    )


def orders_section(orders: list[dict[str, Any]]) -> str:
    if not orders:
        return ""
    lines = [
        "# The owner's standing orders (sealed; they bind you like your charter)",
        *(f"- {o['ref']}: {' '.join(str(o['text_md']).split())}" for o in orders),
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------- holds --
HOLD_SQL = """
    SELECT h.*, c.code AS company FROM oversight.holds h JOIN core.companies c ON c.id = h.company_id
"""


def render_hold(r: dict[str, Any]) -> Hold:
    return Hold(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        action=HoldAction(
            kind=r["target_kind"],
            ref=r["target_ref"],
            summary_fa=r["summary_fa"],
            payload_digest=r["payload_digest"],
        ),
        reason_md=r["reason_md"],
        held_by=_who(r["held_by_kind"], r["held_by_code"]),
        held_at=r["held_at"],
        watch=r["watch"],
        state=r["state"],
        decided_by=_who("owner", "owner") if r["decided_by_kind"] else None,
        decided_at=r["decided_at"],
    )


async def held(tx: Tx, kind: str, ref: str) -> dict[str, Any] | None:
    """The open hold on a target, if any."""
    return await tx.first(
        HOLD_SQL + " WHERE h.target_kind = :k AND h.target_ref = :r AND h.state = 'held'",
        k=kind,
        r=ref,
    )


async def require_not_held(tx: Tx, kind: str, ref: str) -> None:
    h = await held(tx, kind, ref)
    if h is not None:
        raise ApiError(423, "held", f"{kind} {ref} is held ({h['ref']}) until the owner decides")


async def holds_for_run(tx: Tx, employee: str, work_ref: str | None) -> list[str]:
    """Open holds that stop a run's actions: on its employee, on one of its
    tools (`EMP:tool`, returned as `tool:<name>`), or on its work item."""
    rows = await tx.all(
        """SELECT ref, target_kind, target_ref FROM oversight.holds WHERE state = 'held'
             AND ((target_kind = 'employee' AND target_ref = :e)
               OR (target_kind = 'tool' AND split_part(target_ref, ':', 1) = :e)
               OR (target_kind = 'work' AND target_ref = :w)
               -- a held approved card stops its follow-up work too (8.1 §4)
               OR (target_kind = 'decision' AND target_ref IN (
                     SELECT d.ref FROM cartable.decisions d
                     JOIN cartable.resolutions r ON r.source_decision_id = d.id
                     JOIN work.work fw ON fw.id = r.follow_up_work_id WHERE fw.ref = :w)))""",
        e=employee,
        w=work_ref or "",
    )
    out = []
    for r in rows:
        if r["target_kind"] == "tool":
            out.append(f"tool:{r['target_ref'].split(':', 1)[1]}")
        else:
            out.append(r["ref"])
    return out


async def target_company(tx: Tx, kind: str, ref: str) -> tuple[UUID, str, str]:
    """(company id, company code, a short summary) of a hold's target; 404
    when it does not exist (looked up only after the policy allowed)."""
    q = {
        "decision": "SELECT d.company_id, d.title AS summary FROM cartable.decisions d WHERE d.ref = :r",
        "session": "SELECT s.company_id, s.title AS summary FROM workshop.sessions s WHERE s.ref = :r",
        "work": "SELECT w.company_id, w.title AS summary FROM work.work w WHERE w.ref = :r",
        "employee": "SELECT e.company_id, e.title_fa AS summary FROM core.employees e WHERE e.code = :r",
        "tool": "SELECT e.company_id, e.title_fa AS summary FROM core.employees e"
        " WHERE e.code = split_part(:r, ':', 1)",
    }.get(kind)
    if q is None:
        if kind == "story" and await tx.scalar("SELECT to_regclass('owner.stories') IS NOT NULL"):
            q = "SELECT s.company_id, s.title_fa AS summary FROM owner.stories s WHERE s.ref = :r"
        else:
            raise ApiError(
                422, "validation_failed", fields={"target.kind": f"one of {', '.join(HOLD_KINDS)}"}
            )
    row = await tx.first(q, r=ref)
    if row is None:
        raise ApiError(404, "not_found", f"{kind} {ref}")
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=row["company_id"])
    return row["company_id"], str(code), str(row["summary"] or "")[:500]


async def place_hold(
    tx: Tx,
    *,
    kind: str,
    ref: str,
    reason_md: str,
    by_kind: str,
    by_code: str,
    watch: bool = False,
    digest: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """(the hold, created?): one open hold per target. A held session stops at
    once (contract §18.15): the hold row carries it under `session` so the
    caller interrupts it on its runtime after the commit."""
    existing = await held(tx, kind, ref)
    if existing:
        return existing, False
    company_id, company, summary = await target_company(tx, kind, ref)
    session = None
    if kind == "session":
        from hq_api.workshop import domain as workshop

        session = await workshop.overseer_hold(tx, ref)
    row = await tx.one(
        """INSERT INTO oversight.holds (company_id, target_kind, target_ref, summary_fa, payload_digest,
               reason_md, held_by_kind, held_by_code, watch)
           VALUES (:co, :k, :r, :s, :d, :reason, :bk, :bc, :w) RETURNING ref""",
        co=company_id,
        k=kind,
        r=ref,
        s=summary,
        d=digest,
        reason=reason_md[:5000],
        bk=by_kind,
        bc=by_code,
        w=watch,
    )
    await events.emit(
        tx,
        company,
        "oversight.hold",
        row["ref"],
        {"state": "held", "target": {"kind": kind, "ref": ref}},
    )
    await notify.raise_notification(
        tx,
        company_id=company_id,
        company_code=company,
        level="decision",
        title_fa=f"ناظر کل نگه داشت: {summary or ref}"[:300],
        body_fa=reason_md[:1000],
        link_kind="hold",
        link_ref=row["ref"],
        source_kind="agent" if by_kind == "agent" else "system",
        source_code=by_code,
    )
    h = dict(await tx.one(HOLD_SQL + " WHERE h.ref = :r", r=row["ref"]))
    h["session"] = session
    return h, True


async def decide_hold(
    tx: Tx,
    who: Principal,
    ref: str,
    state: Literal["released", "cancelled"],
    note: str | None,
    step_up_id: UUID | None,
) -> dict[str, Any]:
    """The owner only (the routes are owner routes; this checks again).
    `released`: the action goes on. `cancelled` (contract §18.15): the action
    itself is cancelled, so nothing held ever runs after it: a pending card is
    rejected by the owner (note «لغو از hold»), a queued effect is cancelled
    (and the follow-up work of an approved card), a workshop session is
    stopped, a work item is cancelled; a held employee or tool is free again
    (its refused actions stay refused) and a held story is never shown. Both
    count as the owner's activity (watch mode). The result carries `session`
    (the record to interrupt, start or stop on its runtime) and `cancelled`."""
    if not who.is_owner:
        raise ApiError(403, "forbidden", "only the owner releases or cancels a hold")
    h = await tx.one(HOLD_SQL + " WHERE h.ref = :r FOR UPDATE OF h", r=ref, not_found="not_found")
    if h["state"] != "held":
        raise ApiError(409, "validation_failed", f"{ref} is {h['state']}")
    await tx.exec(
        """UPDATE oversight.holds SET state = :s, decided_by_kind = 'owner', decided_by_code = 'owner',
               decided_at = now(), decision_note = :n, step_up_id = :su WHERE id = :id""",
        id=h["id"],
        s=state,
        n=(note or "")[:2000] or None,
        su=step_up_id,
    )
    session = None
    cancelled: dict[str, Any] = {}
    if h["target_kind"] == "session":
        from hq_api.workshop import domain as workshop

        if state == "released":
            session = await workshop.overseer_release(tx, h["target_ref"])
        else:
            session = await workshop.overseer_cancel(tx, h["target_ref"])
            cancelled["session"] = session["state"] if session else None
    elif state == "cancelled":
        cancelled = await cancel_target(tx, who, h)
    await interactions.record(
        tx,
        who,
        company_id=h["company_id"],
        kind="decision",
        action="oversight.hold_release" if state == "released" else "oversight.hold_cancel",
        target_kind=h["target_kind"],
        target_ref=h["target_ref"],
        data={"hold": ref, **({"cancelled": cancelled} if cancelled else {})},
    )
    await events.emit(
        tx,
        h["company"],
        "oversight.hold",
        ref,
        {"state": state, "target": {"kind": h["target_kind"], "ref": h["target_ref"]}},
    )
    out = dict(await tx.one(HOLD_SQL + " WHERE h.ref = :r", r=ref))
    out["session"] = session
    out["cancelled"] = cancelled
    return out


CANCEL_NOTE = "لغو از hold"


async def cancel_target(tx: Tx, who: Principal, h: dict[str, Any]) -> dict[str, Any]:
    """What a cancelled hold cancels (contract §18.15), in the same transaction."""
    from hq_api.domain import decisions as D
    from hq_api.domain import work as W

    kind, ref = h["target_kind"], h["target_ref"]
    if kind == "decision":
        d = await tx.first("SELECT ref FROM cartable.decisions WHERE ref = :r", r=ref)
        if d is None:
            return {}
        d = await D.load(tx, ref, lock=True)
        if d["status"] == "pending":
            await D.decide(tx, who, d, "rejected", note=CANCEL_NOTE)
            return {"decision": "rejected"}
        out: dict[str, Any] = {}
        if d["status"] == "approved" and d["effect_status"] == "pending":
            await tx.exec(
                """UPDATE cartable.decisions SET effect_status = 'cancelled', effect_error = :n
                   WHERE id = :id AND effect_status = 'pending'""",
                id=d["id"],
                n=CANCEL_NOTE,
            )
            out["effect"] = "cancelled"
        if d["status"] == "approved":
            follow = await tx.scalar(
                "SELECT follow_up_work_id FROM cartable.resolutions WHERE source_decision_id = :id",
                id=d["id"],
            )
            if follow is not None and await _cancel_work(tx, W, who, follow):
                out["follow_up"] = "cancelled"
        return out
    if kind == "work":
        wid = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=ref)
        if wid is not None and await _cancel_work(tx, W, who, wid):
            return {"work": "cancelled"}
    return {}


async def _cancel_work(tx: Tx, W: Any, who: Principal, work_id: UUID) -> bool:
    """A work item and its open children, cancelled (as the owner's cancel)."""
    w = await W.load(tx, work_id, lock=True)
    if w["status"] in W.CLOSED:
        return False
    rows = await tx.all(
        """WITH RECURSIVE down AS (
               SELECT id FROM work.work WHERE id = :id
               UNION ALL SELECT c.id FROM work.work c JOIN down ON c.parent_id = down.id)
           UPDATE work.work SET status = 'cancelled', close_reason = :r, closed_at = now()
           WHERE id IN (SELECT id FROM down) AND status NOT IN ('done', 'cancelled', 'failed')
           RETURNING ref""",
        id=work_id,
        r=CANCEL_NOTE,
    )
    await tx.exec("UPDATE work.schedules SET status = 'ended' WHERE work_id = :id", id=work_id)
    await W.event(tx, w, "cancelled", who, {"reason": CANCEL_NOTE, "cascade": len(rows) - 1})
    for r in rows:
        await events.emit(tx, w["company"], "work.updated", r["ref"], {"status": "cancelled"})
    return True


# --------------------------------------------------------------- compliance --
PENALTY = {"critical": 25.0, "high": 10.0, "medium": 4.0, "low": 1.0, "info": 0.0}
LATE_INQUIRY_PENALTY = 2.0


async def compute_compliance(tx: Tx, company_id: UUID, *, days: int = 7) -> dict[str, Any]:
    """0..100 for one company: per area, the share of passed protocol checks
    of the last `days` days (a holding-wide run counts for every company it
    names); minus open findings by severity and late inquiries."""
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=company_id)
    # A deferred or skipped run is no result; a protocol paused now does not count.
    rows = await tx.all(
        """SELECT p.area, r.per_company ->> CAST(:code AS text) AS mine, r.result
           FROM oversight.protocol_runs r JOIN oversight.protocols p ON p.id = r.protocol_id
           JOIN oversight.current_protocols cp ON cp.ref = r.protocol_ref AND cp.status = 'active'
           WHERE r.result IN ('pass', 'fail', 'partial') AND r.started_at > now() - make_interval(days => :d)""",
        code=code,
        d=days,
    )
    tally: dict[str, list[int]] = {}
    passed = failed = 0
    for r in rows:
        result = r["mine"]
        if result is None:
            continue  # this run did not look at this company
        ok = 1 if result == "pass" else 0
        t = tally.setdefault(r["area"], [0, 0])
        t[0] += ok
        t[1] += 1
        passed += ok
        failed += 1 - ok
    by_area = {a: round(100.0 * ok / n, 1) for a, (ok, n) in tally.items() if n}
    open_rows = await tx.all(
        """SELECT severity, count(*) AS n FROM oversight.findings
           WHERE company_id = :co AND status NOT IN ('verified', 'closed') GROUP BY severity""",
        co=company_id,
    )
    open_counts = dict.fromkeys(("critical", "high", "medium", "low"), 0)
    penalty = 0.0
    for r in open_rows:
        if r["severity"] in open_counts:
            open_counts[r["severity"]] = int(r["n"])
        penalty += PENALTY.get(r["severity"], 0.0) * int(r["n"])
    if await tx.scalar("SELECT to_regclass('oversight.inquiries') IS NOT NULL"):
        late = await tx.scalar(
            "SELECT count(*) FROM oversight.inquiries WHERE company_id = :co AND status = 'late'",
            co=company_id,
        )
        penalty += LATE_INQUIRY_PENALTY * int(late or 0)
    base = sum(by_area.values()) / len(by_area) if by_area else 100.0
    score = max(0.0, min(100.0, base - penalty))
    return {
        "score": round(score, 2),
        "by_area": by_area,
        "findings_open": open_counts,
        "protocols": {"passed": passed, "failed": failed},
    }


async def store_compliance(tx: Tx, company_id: UUID, day: date) -> dict[str, Any]:
    c = await compute_compliance(tx, company_id)
    await tx.exec(
        """INSERT INTO oversight.compliance (company_id, day, score, by_area, findings_open, protocols)
           VALUES (:co, :d, :s, CAST(:a AS jsonb), CAST(:f AS jsonb), CAST(:p AS jsonb))
           ON CONFLICT (company_id, day) DO UPDATE SET score = EXCLUDED.score, by_area = EXCLUDED.by_area,
               findings_open = EXCLUDED.findings_open, protocols = EXCLUDED.protocols, computed_at = now()""",
        co=company_id,
        d=day,
        s=c["score"],
        a=json.dumps(c["by_area"]),
        f=json.dumps(c["findings_open"]),
        p=json.dumps(c["protocols"]),
    )
    return c


async def compliance_of(tx: Tx, company_ids: list[UUID]) -> list[Compliance]:
    out = []
    for co in company_ids:
        code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=co)
        rows = await tx.all(
            "SELECT day, score, by_area, findings_open, protocols FROM oversight.compliance"
            " WHERE company_id = :co ORDER BY day DESC LIMIT 30",
            co=co,
        )
        c: dict[str, Any]
        if rows:
            last = rows[0]
            c = {
                "score": float(last["score"]),
                "by_area": dict(last["by_area"]),
                "findings_open": dict(last["findings_open"]),
                "protocols": dict(last["protocols"]),
            }
        else:
            c = await compute_compliance(tx, co)
        out.append(
            Compliance(
                company=str(code),
                score=float(c["score"]),
                by_area={k: float(v) for k, v in c["by_area"].items()},
                findings_open={k: int(v) for k, v in c["findings_open"].items()},
                protocols={k: int(v) for k, v in c["protocols"].items()},
                trend=[float(r["score"]) for r in reversed(rows)],
            )
        )
    return out


# ------------------------------------------------------------------- watch --
async def open_watch(tx: Tx) -> dict[str, Any] | None:
    return await tx.first("SELECT * FROM oversight.watch WHERE until IS NULL")


async def watch_on(tx: Tx) -> bool:
    """For any company's transaction (the watch rows are the holding's)."""
    return bool(await tx.scalar("SELECT oversight.watch_on()"))


async def last_owner_activity(tx: Tx) -> datetime | None:
    at: datetime | None = await tx.scalar("SELECT max(at) FROM owner.interactions")
    return at


async def evaluate_watch(
    tx: Tx, holding_id: UUID, holding_code: str, now: datetime | None = None
) -> dict[str, Any]:
    """On with Khalvat, after `watch_after_hours` without the owner, or by the
    owner's own order; off when the reason is gone (the owner is back)."""
    now = now or datetime.now(UTC)
    w = await open_watch(tx)
    khalvat = bool(await tx.scalar("SELECT khalvat FROM owner.presence WHERE id = 1"))
    hours = int(await tx.scalar("SELECT watch_after_hours FROM owner.settings WHERE id = 1") or 6)
    last = await last_owner_activity(tx)
    away = last is None or now - last > timedelta(hours=hours)
    reason = "khalvat" if khalvat else ("inactivity" if away else None)
    if w is None:
        if reason is None:
            return {"on": False}
        await start_watch(tx, holding_id, holding_code, reason)
        return {"on": True, "started": reason}
    if w["reason"] == "owner":
        # On the owner's own order: it ends when the owner says so, or when the
        # owner acts again after it started.
        back = last is not None and last > w["since"] + timedelta(minutes=1) and not khalvat
        if back:
            await end_watch(tx, w, holding_code)
            return {"on": False, "ended": "owner_back"}
        return {"on": True}
    if reason is None:
        await end_watch(tx, w, holding_code)
        return {"on": False, "ended": w["reason"]}
    return {"on": True}


async def start_watch(tx: Tx, holding_id: UUID, holding_code: str, reason: str) -> dict[str, Any]:
    w = await open_watch(tx)
    if w is not None:
        return w
    row = await tx.one(
        "INSERT INTO oversight.watch (company_id, reason) VALUES (:co, :r) RETURNING *",
        co=holding_id,
        r=reason,
    )
    await hold_pending_cards(tx)
    await refresh_report(tx, holding_code)
    await events.emit(tx, holding_code, "oversight.watch", None, {"on": True, "reason": reason})
    return row


async def end_watch(tx: Tx, w: dict[str, Any], holding_code: str) -> None:
    await refresh_report(tx, holding_code)
    await tx.exec("UPDATE oversight.watch SET until = now() WHERE id = :id", id=w["id"])
    await events.emit(tx, holding_code, "oversight.watch", None, {"on": False})


def high_risk(d: dict[str, Any]) -> bool:
    return (
        d.get("risk") == "high"
        or d.get("action_class") in WATCH_HOLD_CLASSES
        or d.get("kind") in WATCH_HOLD_KINDS
    )


async def hold_if_watching(tx: Tx, d: dict[str, Any]) -> dict[str, Any] | None:
    """A high-risk card proposed while the owner is away is held for the owner
    (a card a CEO decides as well); a card the owner released or cancelled
    during this same watch period is not held again (contract §18.15)."""
    if d.get("status") != "pending" or not high_risk(d) or not await watch_on(tx):
        return None
    if await tx.scalar(
        """SELECT 1 FROM oversight.holds h
           WHERE h.target_kind = 'decision' AND h.target_ref = :r AND h.state <> 'held'
             AND h.decided_at >= oversight.watch_since()""",
        r=d["ref"],
    ):
        return None
    h, _ = await place_hold(
        tx,
        kind="decision",
        ref=d["ref"],
        reason_md="حالت نگهبان: مالک نیست؛ این کارت پرریسک تا بازگشت مالک نگه داشته شد.",
        by_kind="system",
        by_code=await overseer_code(tx),
        watch=True,
    )
    return h


async def overseer_code(tx: Tx) -> str:
    """The holding's Chief Overseer (its code is data, never hard-coded)."""
    code = await tx.scalar(
        """SELECT c.code || '-' || :o FROM core.companies c WHERE c.kind = 'holding' LIMIT 1""",
        o=OVERSEER,
    )
    return str(code or f"HQ-{OVERSEER}")


async def hold_pending_cards(tx: Tx) -> int:
    rows = await tx.all(
        "SELECT ref, kind, risk, action_class, status FROM cartable.decisions WHERE status = 'pending'"
    )
    n = 0
    for d in rows:
        if await hold_if_watching(tx, dict(d)):
            n += 1
    return n


async def refresh_report(tx: Tx, holding_code: str) -> dict[str, Any] | None:
    """The 'while you were away' report (PR-097), written by code from the
    records: holds placed, urgent notifications, findings opened since."""
    w = await open_watch(tx)
    if w is None:
        return None
    since = w["since"]
    held_rows = await tx.all(
        "SELECT ref, summary_fa FROM oversight.holds WHERE held_at >= :s ORDER BY held_at", s=since
    )
    urgent = await tx.all(
        "SELECT id, title_fa FROM notify.notifications WHERE level = 'urgent' AND created_at >= :s"
        " ORDER BY created_at",
        s=since,
    )
    found = await tx.all(
        "SELECT ref, severity, title_fa FROM oversight.findings WHERE opened_at >= :s ORDER BY opened_at",
        s=since,
    )
    lines = [f"حالت نگهبان از {since.isoformat(timespec='minutes')} (دلیل: {w['reason']})"]
    lines.append(f"- نگه‌داشته‌ها: {len(held_rows)}")
    lines += [f"  - {h['ref']}: {h['summary_fa']}" for h in held_rows[:20]]
    lines.append(f"- اعلان‌های فوری: {len(urgent)}")
    lines += [f"  - {u['title_fa']}" for u in urgent[:20]]
    lines.append(f"- یافته‌های تازه: {len(found)}")
    lines += [f"  - {f['ref']} ({f['severity']}): {f['title_fa']}" for f in found[:20]]
    report = {
        "held": [h["ref"] for h in held_rows],
        "urgent": [str(u["id"]) for u in urgent],
        "findings": [f["ref"] for f in found],
    }
    await tx.exec(
        """UPDATE oversight.watch SET summary_md = :s, report = CAST(:r AS jsonb), report_at = now()
           WHERE id = :id""",
        id=w["id"],
        s="\n".join(lines)[:20000],
        r=json.dumps(report),
    )
    return report


async def watch_report(tx: Tx) -> WatchReport:
    w = await open_watch(tx)
    if w is None:
        w = await tx.first("SELECT * FROM oversight.watch ORDER BY since DESC LIMIT 1")
    if w is None:
        return WatchReport(on=False, since=None, until=None, reason=None, summary_md="", held=[],
                           urgent=[], findings=[], report_at=None)  # fmt: skip
    rep = dict(w["report"] or {})
    return WatchReport(
        on=w["until"] is None,
        since=w["since"],
        until=w["until"],
        reason=w["reason"],
        summary_md=w["summary_md"],
        held=list(rep.get("held") or []),
        urgent=list(rep.get("urgent") or []),
        findings=list(rep.get("findings") or []),
        report_at=w["report_at"],
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
