"""Templates, lifecycle rules, NPS and CSAT (prompt 10 §7, contract §19.5).

A rule-sent message is a SEALED template under a SEALED rule (sealing the
rule is the owner's A3 approval in advance), within the rule's limits, after
the outbound guard, and never while the holding (or the company) is locked.
There is no free text from an agent to a customer anywhere here.

  templates   propose_template (owner, or an agent's message_template card),
              seal_template (🔏 growth.template = ref@version:sha256 of the
              body: a seal never fits another company's template with the
              same text, its ref differs); a new version pauses every active
              rule on the template until a rule version on the new one is
              sealed
  rules       create_rule (owner, or an agent's lifecycle_rule card) ->
              proposed; seal_rule (🔏 growth.rule = ref@version) -> active,
              only on a sealed, current template version (else 409
              template_not_sealed); pause (no step-up), resume (🔏)
  send        send_template(): THE entry point for every rule-sent message
              (rescue follow-ups, welcome, reactivation, NPS, CSAT): the gate,
              dedupe, the rule and its template, opt-out, per-customer days,
              the daily cap, quiet hours (Tehran), Telegram's rules, the
              guard, a live channel; queued for the worker (desk.send)
  NPS         a quarterly wave (NP-<year>Q<q>-<CO>) of a random sample of
              customers with a conversation in the last 90 days; answers
              0..10 with an optional comment (comments go to the feedback
              inbox); score = %promoters - %detractors
  CSAT        on close, the sealed csat template; a 1..5 reply is the
              conversation's csat
  seed        every company gets proposed holding_reply and safety templates
              (signature «پشتیبانی Coine») and proposed csat and nps rules,
              on first use (no fixed number of companies)
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import desk, gate
from hq_api.domain import support as S
from hq_api.errors import ApiError
from hq_common import customer_mask

PURPOSES = ("welcome", "reactivation", "rescue", "nps", "holding_reply", "safety", "csat")
RULE_KINDS = ("welcome", "reactivation", "rescue", "nps", "csat")
TEHRAN = ZoneInfo("Asia/Tehran")
VAR = re.compile(r"\{([a-z][a-z0-9_]{0,40})\}")
DEFAULT_LIMITS: dict[str, Any] = {
    "per_customer_days": 30,
    "daily_cap": 50,
    "quiet_hours": ["22:00", "09:00"],
    "max_follow_ups": 2,
}
NPS_RRULE = "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=10;BYMINUTE=0"
NPS_EPOCH = datetime(2026, 1, 1, tzinfo=TEHRAN)
NPS_DAYS_OPEN = 14
NPS_SAMPLE = 50
SEED_TEMPLATES = {
    "holding_reply": desk.HOLDING_DEFAULT,
    "safety": desk.SAFETY_DEFAULT,
    "csat": "از ۱ تا ۵ چقدر از پاسخ پشتیبانی راضی بودید؟ فقط یک عدد بفرستید.\n— پشتیبانی Coine",
    "nps": (
        "از ۰ تا ۱۰ چقدر احتمال دارد ما را به دوستتان پیشنهاد کنید؟ یک عدد و اگر خواستید "
        "یک جمله بفرستید.\n— پشتیبانی Coine"
    ),
}
# Until the products send signup / vip_activated (CR-009, CR-010) these have no candidates.
NO_SOURCE_YET = {
    "welcome": "تا رسیدن رویداد signup از محصول (CR-009/010) کاندیدی ندارد.",
    "reactivation": "تا رسیدن رویدادهای فعالیت از محصول (CR-009/010) کاندیدی ندارد.",
}


# ------------------------------------------------------------------ shapes --
class MessageTemplate(BaseModel):
    id: UUID
    ref: str
    company: str
    version: int
    purpose: str
    body_fa: str
    variables: list[str]
    status: Literal["proposed", "sealed", "retired"]
    sealed_at: datetime | None
    sha256: str
    seal_target: str = Field(description="the step-up target of POST …/seal: ref@version:sha256")


class LifecycleLimits(BaseModel):
    per_customer_days: int = Field(default=30, ge=1, le=3650)
    daily_cap: int = Field(default=50, ge=1, le=100000)
    quiet_hours: list[str] = Field(
        default_factory=lambda: ["22:00", "09:00"], min_length=2, max_length=2
    )
    max_follow_ups: int = Field(default=2, ge=0, le=20)


class LifecycleRule(BaseModel):
    id: UUID
    ref: str
    company: str
    version: int
    kind: str
    trigger: dict[str, Any]
    template: str
    channel: str
    limits: dict[str, Any]
    status: Literal["proposed", "active", "paused", "retired"]
    paused_reason: str | None
    decision_ref: str | None
    sent_30d: int
    opt_outs_30d: int
    note_fa: str | None = None


class NpsWave(BaseModel):
    ref: str
    company: str
    quarter: str
    state: Literal["open", "closed"]
    sample: int
    sent: int
    responses: int
    score: int | None
    promoters: int
    passives: int
    detractors: int
    opens_at: datetime
    closes_at: datetime
    comments_to_feedback: int


def body_sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def seal_target(t: dict[str, Any]) -> str:
    return f"{t['ref']}@{t['version']}:{t['sha256']}"


def render_template(r: dict[str, Any], company: str) -> MessageTemplate:
    return MessageTemplate(
        id=r["id"], ref=r["ref"], company=company, version=r["version"], purpose=r["purpose"],
        body_fa=r["body_fa"], variables=list(r["variables"] or []), status=r["status"],
        sealed_at=r["sealed_at"], sha256=r["sha256"], seal_target=seal_target(r),
    )  # fmt: skip


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def render_rule(r: dict[str, Any], company: str) -> LifecycleRule:
    return LifecycleRule(
        id=r["id"], ref=r["ref"], company=company, version=r["version"], kind=r["kind"],
        trigger=_j(r["trigger"]) or {}, template=f"{r['template_ref']}@{r['template_version']}",
        channel=r["channel"], limits=_j(r["limits"]) or {}, status=r["status"],
        paused_reason=r["paused_reason"], decision_ref=r.get("decision_ref"),
        sent_30d=int(r.get("sent_30d") or 0), opt_outs_30d=int(r.get("opt_outs_30d") or 0),
        note_fa=NO_SOURCE_YET.get(r["kind"]),
    )  # fmt: skip


RULE_SQL = """SELECT r.*, d.ref AS decision_ref,
                     (SELECT count(*) FROM growth.sends s WHERE s.rule_id = r.id AND s.status = 'sent'
                        AND s.at > now() - interval '30 days') AS sent_30d,
                     (SELECT count(*) FROM growth.opt_outs o WHERE o.company_id = r.company_id
                        AND o.at > now() - interval '30 days'
                        AND EXISTS (SELECT 1 FROM growth.sends s2 WHERE s2.rule_id = r.id
                                      AND s2.subject = o.subject)) AS opt_outs_30d
              FROM growth.rules r LEFT JOIN cartable.decisions d ON d.id = r.decision_id"""


def render_wave(r: dict[str, Any], company: str) -> NpsWave:
    return NpsWave(
        ref=r["ref"], company=company, quarter=r["quarter"], state=r["state"], sample=r["sample"],
        sent=r["sent"], responses=r["responses"], score=r["score"], promoters=r["promoters"],
        passives=r["passives"], detractors=r["detractors"], opens_at=r["opens_at"],
        closes_at=r["closes_at"], comments_to_feedback=r["comments_to_feedback"],
    )  # fmt: skip


# --------------------------------------------------------------- templates --
def check_variables(body: str, declared: list[str]) -> None:
    used = set(VAR.findall(body))
    unknown = sorted(used - set(declared))
    if unknown:
        raise ApiError(
            422,
            "validation_failed",
            fields={"variables": f"undeclared in the body: {', '.join(unknown)[:200]}"},
        )


async def propose_template(
    tx: Tx,
    *,
    company_id: UUID,
    purpose: str,
    body_fa: str,
    variables: list[str],
    by_kind: Literal["owner", "agent", "service"],
    by_code: str,
    ref: str | None = None,
) -> dict[str, Any]:
    if purpose not in PURPOSES:
        raise ApiError(422, "validation_failed", fields={"purpose": "unknown purpose"})
    body = body_fa.strip()
    check_variables(body, variables)
    if by_kind == "agent":
        body = customer_mask.quote(body, max_chars=4000)
    version = 1
    if ref is not None:
        prev = await tx.first(
            """SELECT company_id, purpose, max(version) OVER () AS top FROM growth.templates
               WHERE ref = :r LIMIT 1""",
            r=ref,
        )
        if prev is None or prev["company_id"] != company_id:
            raise ApiError(404, "not_found", f"no template {ref} in this company")
        if prev["purpose"] != purpose:
            raise ApiError(
                422, "validation_failed", fields={"purpose": f"{ref} is {prev['purpose']}"}
            )
        version = int(prev["top"]) + 1
    row = await tx.one(
        """INSERT INTO growth.templates (ref, company_id, version, purpose, body_fa, variables, sha256,
               proposed_by_kind, proposed_by_code)
           VALUES (COALESCE(:ref, 'TM-' || lpad(nextval('growth.template_ref_seq')::text, 4, '0')),
                   :co, :v, :p, :b, :vars, :sha, :bk, :bc)
           RETURNING *""",
        ref=ref,
        co=company_id,
        v=version,
        p=purpose,
        b=body,
        vars=sorted(set(variables))[:20],
        sha=body_sha(body),
        bk=by_kind,
        bc=by_code[:64],
    )
    if ref is not None:
        # A new version stops every active rule on this template until a rule
        # version on the new one is sealed (contract §19.5).
        await tx.exec(
            """UPDATE growth.rules SET status = 'paused', paused_reason = 'template_new_version',
                   updated_at = now()
               WHERE company_id = :co AND template_ref = :r AND status = 'active'""",
            co=company_id,
            r=ref,
        )
    return row


async def template(tx: Tx, ref: str, version: int | None = None) -> dict[str, Any]:
    row = await tx.first(
        """SELECT * FROM growth.templates WHERE ref = :r AND (CAST(:v AS int) IS NULL OR version = :v)
           ORDER BY version DESC LIMIT 1""",
        r=ref,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no template {ref}")
    return row


async def seal_template(
    tx: Tx,
    ref: str,
    version: int,
    *,
    step_up_id: UUID | None,
    decision_id: UUID | None = None,
    sha256: str | None = None,
) -> dict[str, Any]:
    t = await tx.first(
        "SELECT * FROM growth.templates WHERE ref = :r AND version = :v FOR UPDATE",
        r=ref,
        v=version,
    )
    if t is None:
        raise ApiError(404, "not_found", f"no template {ref}@{version}")
    if sha256 is not None and t["sha256"] != sha256:
        raise ApiError(409, "decision_not_pending", "the template changed since the card")
    if t["status"] != "proposed":
        raise ApiError(409, "validation_failed", f"{ref}@{version} is {t['status']}")
    await tx.exec(
        """UPDATE growth.templates SET status = 'retired', updated_at = now()
           WHERE ref = :r AND status = 'sealed'""",
        r=ref,
    )
    return await tx.one(
        """UPDATE growth.templates SET status = 'sealed', sealed_at = now(), seal_step_up_id = :su,
               decision_id = COALESCE(:d, decision_id), updated_at = now()
           WHERE id = :id RETURNING *""",
        id=t["id"],
        su=step_up_id,
        d=decision_id,
    )


async def current_sealed(tx: Tx, ref: str, version: int) -> bool:
    """The rule's template version is sealed AND no newer version exists."""
    rows = await tx.all(
        "SELECT version, status FROM growth.templates WHERE ref = :r ORDER BY version DESC", r=ref
    )
    if not rows:
        return False
    top = rows[0]
    return int(top["version"]) == version and top["status"] == "sealed"


# ------------------------------------------------------------------- rules --
def validate_limits(limits: dict[str, Any] | None) -> dict[str, Any]:
    merged = {**DEFAULT_LIMITS, **(limits or {})}
    out = LifecycleLimits(**merged).model_dump()
    for hhmm in out["quiet_hours"]:
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", hhmm):
            raise ApiError(422, "validation_failed", fields={"limits.quiet_hours": "HH:MM, Tehran"})
    return out


def validate_trigger(kind: str, trigger: dict[str, Any] | None) -> dict[str, Any]:
    t = dict(trigger or {})
    allowed = {"event", "after_hours", "inactive_days", "rrule", "sample"}
    extra = sorted(set(t) - allowed)
    if extra:
        raise ApiError(422, "validation_failed", fields={"trigger": f"unknown keys {extra}"[:200]})
    if kind == "nps":
        t.setdefault("rrule", NPS_RRULE)
        try:
            rrulestr(str(t["rrule"]), dtstart=NPS_EPOCH)
        except (ValueError, TypeError) as exc:
            raise ApiError(
                422, "validation_failed", fields={"trigger.rrule": "not an RRULE"}
            ) from exc
    if kind == "csat":
        t.setdefault("event", "conversation_closed")
    if kind == "welcome":
        t.setdefault("event", "signup")
    if kind == "rescue":
        t.setdefault("event", "referral_failed")
        t.setdefault("after_hours", 24)
    if kind == "reactivation":
        t.setdefault("inactive_days", 30)
    return t


async def create_rule(
    tx: Tx,
    *,
    company_id: UUID,
    kind: str,
    template_ref: str,
    template_version: int,
    channel: str,
    trigger: dict[str, Any] | None,
    limits: dict[str, Any] | None,
    by_kind: Literal["owner", "agent", "service"],
    by_code: str,
    ref: str | None = None,
) -> dict[str, Any]:
    if kind not in RULE_KINDS:
        raise ApiError(422, "validation_failed", fields={"kind": "unknown rule kind"})
    if channel not in S.CHANNELS or channel == "mystery":
        raise ApiError(422, "validation_failed", fields={"channel": "a customer channel"})
    t = await tx.first(
        "SELECT company_id, purpose FROM growth.templates WHERE ref = :r AND version = :v",
        r=template_ref,
        v=template_version,
    )
    if t is None or t["company_id"] != company_id:
        raise ApiError(422, "validation_failed", fields={"template": "a template of this company"})
    if t["purpose"] != kind:
        raise ApiError(422, "validation_failed", fields={"template": f"a {kind} template"})
    version = 1
    if ref is not None:
        prev = await tx.first(
            """SELECT company_id, kind, max(version) OVER () AS top FROM growth.rules
               WHERE ref = :r LIMIT 1""",
            r=ref,
        )
        if prev is None or prev["company_id"] != company_id:
            raise ApiError(404, "not_found", f"no rule {ref} in this company")
        if prev["kind"] != kind:
            raise ApiError(422, "validation_failed", fields={"kind": f"{ref} is {prev['kind']}"})
        version = int(prev["top"]) + 1
    row = await tx.one(
        """INSERT INTO growth.rules (ref, company_id, version, kind, trigger, template_ref,
               template_version, channel, limits, proposed_by_kind, proposed_by_code)
           VALUES (COALESCE(:ref, 'LR-' || lpad(nextval('growth.rule_ref_seq')::text, 4, '0')),
                   :co, :v, :k, CAST(:tr AS jsonb), :tref, :tv, :ch, CAST(:lim AS jsonb), :bk, :bc)
           RETURNING id""",
        ref=ref,
        co=company_id,
        v=version,
        k=kind,
        tr=json.dumps(validate_trigger(kind, trigger)),
        tref=template_ref,
        tv=template_version,
        ch=channel,
        lim=json.dumps(validate_limits(limits)),
        bk=by_kind,
        bc=by_code[:64],
    )
    return await tx.one(RULE_SQL + " WHERE r.id = :id", id=row["id"])


async def rule(tx: Tx, ref: str, version: int | None = None) -> dict[str, Any]:
    row = await tx.first(
        RULE_SQL
        + " WHERE r.ref = :r AND (CAST(:v AS int) IS NULL OR r.version = :v) ORDER BY r.version DESC LIMIT 1",
        r=ref,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no rule {ref}")
    return row


async def seal_rule(
    tx: Tx,
    ref: str,
    version: int,
    *,
    step_up_id: UUID | None,
    decision_id: UUID | None = None,
) -> dict[str, Any]:
    r = await tx.first(
        "SELECT * FROM growth.rules WHERE ref = :r AND version = :v FOR UPDATE", r=ref, v=version
    )
    if r is None:
        raise ApiError(404, "not_found", f"no rule {ref}@{version}")
    if r["status"] not in ("proposed", "paused"):
        raise ApiError(409, "validation_failed", f"{ref}@{version} is {r['status']}")
    if not await current_sealed(tx, r["template_ref"], r["template_version"]):
        raise ApiError(
            409,
            "template_not_sealed",
            f"{r['template_ref']}@{r['template_version']} is not the sealed current version",
        )
    await tx.exec(
        """UPDATE growth.rules SET status = 'retired', updated_at = now()
           WHERE ref = :r AND id <> :id AND status IN ('active', 'paused')""",
        r=ref,
        id=r["id"],
    )
    await tx.exec(
        """UPDATE growth.rules SET status = 'active', paused_reason = NULL,
               sealed_at = COALESCE(sealed_at, now()), seal_step_up_id = COALESCE(:su, seal_step_up_id),
               decision_id = COALESCE(:d, decision_id), updated_at = now()
           WHERE id = :id""",
        id=r["id"],
        su=step_up_id,
        d=decision_id,
    )
    return await rule(tx, ref, version)


async def pause_rule(tx: Tx, ref: str, reason: str = "owner") -> dict[str, Any]:
    r = await rule(tx, ref)
    await tx.exec(
        """UPDATE growth.rules SET status = 'paused', paused_reason = :why, updated_at = now()
           WHERE ref = :r AND status = 'active'""",
        r=ref,
        why=reason[:200],
    )
    return await rule(tx, ref, r["version"])


# ------------------------------------------------------------------- seeds --
async def ensure_seed(tx: Tx, company_id: UUID) -> None:
    """The company's first templates and rules, proposed (a new company
    needs no migration): holding_reply and safety; csat and nps with their
    conservative rules. Nothing is sealed: only the owner seals."""
    have = {
        r["purpose"]
        for r in await tx.all(
            "SELECT DISTINCT purpose FROM growth.templates WHERE company_id = :co", co=company_id
        )
    }
    for purpose, body in SEED_TEMPLATES.items():
        if purpose in have:
            continue
        t = await propose_template(
            tx, company_id=company_id, purpose=purpose, body_fa=body, variables=[],
            by_kind="service", by_code="seed",
        )  # fmt: skip
        if purpose in ("csat", "nps"):
            await create_rule(
                tx, company_id=company_id, kind=purpose, template_ref=t["ref"],
                template_version=t["version"], channel="telegram_bot",
                trigger={"sample": NPS_SAMPLE} if purpose == "nps" else None,
                limits={"per_customer_days": 90 if purpose == "nps" else 7,
                        "daily_cap": 30 if purpose == "nps" else 100, "max_follow_ups": 0},
                by_kind="service", by_code="seed",
            )  # fmt: skip


# -------------------------------------------------------------------- send --
def in_quiet_hours(limits: dict[str, Any], now: datetime) -> bool:
    start_s, end_s = (limits.get("quiet_hours") or DEFAULT_LIMITS["quiet_hours"])[:2]
    local = now.astimezone(TEHRAN).time()
    start = time.fromisoformat(start_s)
    end = time.fromisoformat(end_s)
    if start == end:
        return False
    return (local >= start or local < end) if start > end else (start <= local < end)


def render_body(t: dict[str, Any], variables: dict[str, str] | None) -> str:
    declared = set(t["variables"] or [])
    values = {k: str(v)[:200] for k, v in (variables or {}).items() if k in declared}

    def sub(m: re.Match[str]) -> str:
        return values.get(m.group(1), "")

    return VAR.sub(sub, t["body_fa"])


async def _record(
    tx: Tx,
    *,
    company_id: UUID,
    rule_row: dict[str, Any] | None,
    template_ref: str,
    subject: str,
    channel: str,
    dedupe_key: str,
    status: str,
    reason: str | None = None,
    blocked: tuple[str, ...] = (),
    message_id: UUID | None = None,
    rescue_case_id: UUID | None = None,
    nps_wave_id: UUID | None = None,
    follow_up: int | None = None,
) -> dict[str, Any]:
    row = await tx.first(
        """INSERT INTO growth.sends (company_id, rule_id, template, subject, channel, dedupe_key, status,
               reason, blocked_reasons, message_id, rescue_case_id, nps_wave_id, follow_up)
           VALUES (:co, :rule, :t, :s, :ch, :k, :st, :why, :br, :m, :rc, :w, :fu)
           ON CONFLICT (company_id, dedupe_key) DO UPDATE SET status = EXCLUDED.status,
               reason = EXCLUDED.reason, blocked_reasons = EXCLUDED.blocked_reasons,
               message_id = EXCLUDED.message_id
             WHERE growth.sends.status IN ('queued', 'no_channel') AND growth.sends.message_id IS NULL
           RETURNING *""",
        co=company_id,
        rule=rule_row["id"] if rule_row else None,
        t=template_ref,
        s=subject,
        ch=channel,
        k=dedupe_key[:200],
        st=status,
        why=reason,
        br=list(blocked),
        m=message_id,
        rc=rescue_case_id,
        w=nps_wave_id,
        fu=follow_up,
    )
    if row is None:
        row = await tx.one(
            "SELECT * FROM growth.sends WHERE company_id = :co AND dedupe_key = :k",
            co=company_id,
            k=dedupe_key[:200],
        )
    return row


def _out(row: dict[str, Any] | None, status: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "status": row["status"] if row else status,
        "reason": (row["reason"] if row else reason),
        "send_id": str(row["id"]) if row else None,
        "message_id": str(row["message_id"]) if row and row["message_id"] else None,
        "blocked_reasons": list(row["blocked_reasons"] or []) if row else [],
        "template": row["template"] if row else None,
    }


async def active_rule(
    tx: Tx, company_id: UUID, kind: str, rule_ref: str | None = None
) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT * FROM growth.rules WHERE company_id = :co AND kind = :k AND status = 'active'
             AND (CAST(:ref AS text) IS NULL OR ref = :ref)
           ORDER BY sealed_at DESC LIMIT 1""",
        co=company_id,
        k=kind,
        ref=rule_ref,
    )


async def send_template(
    tx: Tx,
    hub: Any,
    *,
    company_id: UUID,
    purpose: str,
    dedupe_key: str,
    subject: str | None = None,
    conversation_id: UUID | None = None,
    variables: dict[str, str] | None = None,
    rule_ref: str | None = None,
    rescue_case_id: UUID | None = None,
    nps_wave_id: UUID | None = None,
    follow_up: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Send one sealed template to one customer under the company's active,
    sealed rule of that kind (prompt 10 §7.3). Returns {status: queued |
    sent | blocked | skipped | no_channel | failed, reason, send_id,
    message_id, blocked_reasons}; `queued` with reason `quiet_hours` or
    `daily_cap` is retried by the sweep (same dedupe_key).

    The customer is found by `conversation_id` (preferred: a rescue case's
    or an NPS sample's conversation) or by its support `subject`. A rescue
    case's own subject (`uid:<exchange>`) reaches no channel by itself."""
    if purpose not in RULE_KINDS:
        raise ValueError(f"{purpose} is not a rule-sent purpose")
    now = now or datetime.now(UTC)
    lock = await gate.automation_lock(tx, company_id)
    if lock is not None:
        return {**gate.skipped(lock), "status": "skipped"}
    prior = await tx.first(
        "SELECT * FROM growth.sends WHERE company_id = :co AND dedupe_key = :k",
        co=company_id,
        k=dedupe_key[:200],
    )
    # Held (quiet hours, the daily cap) or not reachable yet (no channel): tried again.
    if prior is not None and not (
        prior["status"] in ("queued", "no_channel") and prior["message_id"] is None
    ):
        return _out(prior, prior["status"])
    r = await active_rule(tx, company_id, purpose, rule_ref)
    if r is None:
        return _out(None, "skipped", "no_active_rule")
    tref = f"{r['template_ref']}@{r['template_version']}"
    if not await current_sealed(tx, r["template_ref"], r["template_version"]):
        await pause_rule(tx, r["ref"], "template_not_sealed")
        return _out(None, "skipped", "template_not_sealed")
    limits = _j(r["limits"]) or DEFAULT_LIMITS
    conv: dict[str, Any] | None = None
    if conversation_id is not None:
        conv = await tx.first(
            "SELECT * FROM support.conversations WHERE id = :id AND company_id = :co",
            id=conversation_id,
            co=company_id,
        )
    if conv is None and subject is not None:
        conv = await tx.first(
            """SELECT c.* FROM support.conversations c JOIN support.customers k ON k.id = c.customer_id
               WHERE k.company_id = :co AND k.subject = :s ORDER BY c.last_message_at DESC LIMIT 1""",
            co=company_id,
            s=subject,
        )
    customer = (
        await tx.first("SELECT * FROM support.customers WHERE id = :id", id=conv["customer_id"])
        if conv
        else None
    )
    who = customer["subject"] if customer else subject
    if who is None:
        raise ValueError("send_template needs a subject or a conversation")
    common = {
        "company_id": company_id, "rule_row": r, "template_ref": tref, "subject": who,
        "channel": r["channel"], "dedupe_key": dedupe_key, "rescue_case_id": rescue_case_id,
        "nps_wave_id": nps_wave_id, "follow_up": follow_up,
    }  # fmt: skip
    if conv is None or customer is None or conv["mystery"]:
        return _out(await _record(tx, **common, status="no_channel", reason="no_conversation"), "")
    if await tx.scalar(
        "SELECT 1 FROM growth.opt_outs WHERE company_id = :co AND subject = :s",
        co=company_id,
        s=customer["subject"],
    ):
        return _out(await _record(tx, **common, status="skipped", reason="opted_out"), "")
    if await tx.scalar(
        """SELECT 1 FROM growth.sends WHERE company_id = :co AND rule_id IN
               (SELECT id FROM growth.rules WHERE ref = :ref) AND subject = :s AND status = 'sent'
             AND at > CAST(:now AS timestamptz) - make_interval(days => :d) AND dedupe_key <> :k
             AND (CAST(:rc AS uuid) IS NULL OR rescue_case_id IS DISTINCT FROM CAST(:rc AS uuid))
           LIMIT 1""",
        co=company_id,
        ref=r["ref"],
        s=customer["subject"],
        now=now,
        d=int(limits.get("per_customer_days", 30)),
        k=dedupe_key[:200],
        rc=rescue_case_id,
    ):  # a rescue case's own follow-ups go by after_hours and max_follow_ups
        return _out(await _record(tx, **common, status="skipped", reason="per_customer_days"), "")
    if in_quiet_hours(limits, now):
        return _out(await _record(tx, **common, status="queued", reason="quiet_hours"), "")
    sent_today = await tx.scalar(
        """SELECT count(*) FROM growth.sends WHERE company_id = :co AND rule_id = :rule
             AND status IN ('sent', 'queued') AND message_id IS NOT NULL
             AND at >= date_trunc('day', CAST(:now AS timestamptz) AT TIME ZONE 'Asia/Tehran')
                        AT TIME ZONE 'Asia/Tehran'""",
        co=company_id,
        rule=r["id"],
        now=now,
    )
    if int(sent_today or 0) >= int(limits.get("daily_cap", 50)):
        return _out(await _record(tx, **common, status="queued", reason="daily_cap"), "")
    ch = await S.channel(tx, company_id, conv["channel"])
    if conv["channel"] != r["channel"] or ch["state"] != "live":
        return _out(await _record(tx, **common, status="no_channel", reason="channel_not_live"), "")
    if not desk.telegram_allows(ch, conv, customer):
        return _out(await _record(tx, **common, status="no_channel", reason="telegram_rules"), "")
    t = await tx.one(
        "SELECT * FROM growth.templates WHERE ref = :r AND version = :v",
        r=r["template_ref"],
        v=r["template_version"],
    )
    # Every lifecycle message carries the safety line (contract §19.6).
    body = render_body(t, variables)
    composed = await desk.compose(tx, conv, body, with_safety=True)
    if not composed.verdict.ok:
        return _out(
            await _record(
                tx, **common, status="blocked", reason="guard", blocked=composed.verdict.reasons
            ),
            "",
        )
    msg = await desk.insert_out(
        tx, conv, author="rule", author_code=r["ref"], body=composed.text, status="queued",
        verdict=composed.verdict, template=tref,
    )  # fmt: skip
    row = await _record(tx, **common, status="queued", reason=None, message_id=msg["id"])
    await tx.exec("UPDATE growth.rules SET last_run_at = now() WHERE id = :id", id=r["id"])
    company = await hub.companies.code_of(company_id)
    await events.emit(tx, company, "lifecycle.sent", r["ref"], {"purpose": purpose, "queued": True})
    return _out(row, "queued")


async def retry_queued(tx: Tx, hub: Any, now: datetime | None = None) -> int:
    """Sends held by quiet hours or the daily cap, tried again (the sweep)."""
    rows = await tx.all(
        """SELECT s.*, r.kind FROM growth.sends s JOIN growth.rules r ON r.id = s.rule_id
           WHERE s.status = 'queued' AND s.message_id IS NULL AND s.at > now() - interval '7 days'
           ORDER BY s.at LIMIT 200"""
    )
    done = 0
    for s in rows:
        conv = await tx.first(
            """SELECT c.id FROM support.conversations c JOIN support.customers k ON k.id = c.customer_id
               WHERE k.company_id = :co AND k.subject = :s ORDER BY c.last_message_at DESC LIMIT 1""",
            co=s["company_id"],
            s=s["subject"],
        )
        out = await send_template(
            tx, hub, company_id=s["company_id"], purpose=s["kind"], dedupe_key=s["dedupe_key"],
            conversation_id=conv["id"] if conv else None, subject=s["subject"],
            rescue_case_id=s["rescue_case_id"], nps_wave_id=s["nps_wave_id"],
            follow_up=s["follow_up"], now=now,
        )  # fmt: skip
        done += int(out["status"] == "queued" and out["message_id"] is not None)
    return done


# --------------------------------------------------------------------- NPS --
def nps_score(promoters: int, passives: int, detractors: int) -> int | None:
    total = promoters + passives + detractors
    if total == 0:
        return None
    return round(100 * (promoters - detractors) / total)


def quarter_of(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


async def nps_due(tx: Tx, hub: Any, now: datetime | None = None) -> list[str]:
    """Open this quarter's wave for each company whose nps rule is active
    and whose rrule fired in the last 7 days; close waves past closes_at."""
    now = now or datetime.now(UTC)
    opened: list[str] = []
    for r in await tx.all("SELECT * FROM growth.rules WHERE kind = 'nps' AND status = 'active'"):
        trig = _j(r["trigger"]) or {}
        rr = rrulestr(str(trig.get("rrule") or NPS_RRULE), dtstart=NPS_EPOCH)
        last = rr.before(now.astimezone(TEHRAN), inc=True)
        if last is None or now - last > timedelta(days=7):
            continue
        quarter = quarter_of(last.date())
        if await tx.scalar(
            "SELECT 1 FROM growth.nps_waves WHERE company_id = :co AND quarter = :q",
            co=r["company_id"],
            q=quarter,
        ):
            continue
        company = await hub.companies.code_of(r["company_id"])
        wave = await tx.one(
            """INSERT INTO growth.nps_waves (ref, company_id, quarter, rule_id, opens_at, closes_at)
               VALUES (:ref, :co, :q, :rule, :o, :c) RETURNING *""",
            ref=f"NP-{quarter}-{company}",
            co=r["company_id"],
            q=quarter,
            rule=r["id"],
            o=now,
            c=now + timedelta(days=NPS_DAYS_OPEN),
        )
        sample = await tx.all(
            """SELECT DISTINCT ON (k.subject) c.id AS conversation_id, k.subject
               FROM support.conversations c JOIN support.customers k ON k.id = c.customer_id
               WHERE c.company_id = :co AND NOT c.mystery
                 AND c.last_message_at > CAST(:now AS timestamptz) - interval '90 days'
                 AND NOT EXISTS (SELECT 1 FROM growth.opt_outs o WHERE o.company_id = c.company_id
                                   AND o.subject = k.subject)
               ORDER BY k.subject, c.last_message_at DESC""",
            co=r["company_id"],
            now=now,
        )
        size = min(int(trig.get("sample") or NPS_SAMPLE), len(sample))
        chosen = random.SystemRandom().sample(sample, size) if size else []
        sent = 0
        for c in chosen:
            out = await send_template(
                tx, hub, company_id=r["company_id"], purpose="nps",
                dedupe_key=f"{wave['ref']}:{c['subject'][:32]}", conversation_id=c["conversation_id"],
                nps_wave_id=wave["id"], now=now,
            )  # fmt: skip
            sent += int(out["status"] == "queued" and out["message_id"] is not None)
        await tx.exec(
            "UPDATE growth.nps_waves SET sample = :n, sent = :s WHERE id = :id",
            n=size,
            s=sent,
            id=wave["id"],
        )
        opened.append(wave["ref"])
    for w in await tx.all(
        "SELECT * FROM growth.nps_waves WHERE state = 'open' AND closes_at <= :now", now=now
    ):
        await close_wave(tx, hub, w)
    return opened


async def close_wave(tx: Tx, hub: Any, w: dict[str, Any]) -> dict[str, Any]:
    c = await tx.one(
        """SELECT count(*) FILTER (WHERE score >= 9) AS p, count(*) FILTER (WHERE score BETWEEN 7 AND 8) AS pa,
                  count(*) FILTER (WHERE score <= 6) AS d, count(*) AS n
           FROM growth.nps_responses WHERE wave_id = :w""",
        w=w["id"],
    )
    score = nps_score(int(c["p"]), int(c["pa"]), int(c["d"]))
    row = await tx.one(
        """UPDATE growth.nps_waves SET state = 'closed', closed_at = now(), promoters = :p, passives = :pa,
               detractors = :d, responses = :n, score = :sc WHERE id = :id RETURNING *""",
        p=int(c["p"]),
        pa=int(c["pa"]),
        d=int(c["d"]),
        n=int(c["n"]),
        sc=score,
        id=w["id"],
    )
    company = await hub.companies.code_of(w["company_id"])
    await events.emit(
        tx, company, "nps.closed", w["ref"], {"score": score, "responses": int(c["n"])}
    )
    return row


# ------------------------------------------------------------ answers in --
async def take_answer(
    tx: Tx, hub: Any, conv: dict[str, Any], customer: dict[str, Any], msg: dict[str, Any]
) -> str | None:
    """A customer's 0..10 to an open NPS wave or 1..5 to a CSAT question is
    the answer (stored), not a new support case. Returns "nps" | "csat" | None."""
    body = msg["body"] or ""
    pending = await tx.first(
        """SELECT s.nps_wave_id, w.ref, w.company_id FROM growth.sends s
           JOIN growth.nps_waves w ON w.id = s.nps_wave_id AND w.state = 'open'
           WHERE s.company_id = :co AND s.subject = :sub AND s.status IN ('queued', 'sent')
             AND NOT EXISTS (SELECT 1 FROM growth.nps_responses r WHERE r.wave_id = w.id
                               AND r.subject = :sub)
           ORDER BY s.at DESC LIMIT 1""",
        co=conv["company_id"],
        sub=customer["subject"],
    )
    lead = desk.leading_number(body)
    score = lead[0] if lead and lead[0] <= 10 else None
    if pending is not None and score is not None:
        comment = (lead[1] if lead else "").strip(" .،,-:") or None
        resp = await tx.first(
            """INSERT INTO growth.nps_responses (wave_id, company_id, subject, score, comment, message_id)
               VALUES (:w, :co, :s, :sc, :c, :m) ON CONFLICT (wave_id, subject) DO NOTHING
               RETURNING id""",
            w=pending["nps_wave_id"],
            co=conv["company_id"],
            s=customer["subject"],
            sc=score,
            c=customer_mask.mask(comment).text[:2000] if comment else None,
            m=msg["id"],
        )
        if resp is None:
            return "nps"  # answered already (a retry)
        await tx.exec(
            "UPDATE growth.nps_waves SET responses = responses + 1 WHERE id = :w",
            w=pending["nps_wave_id"],
        )
        if comment:
            # The comment goes to the feedback inbox: the company's keywords
            # tag it at once (no model), else the nightly batch (§8.1).
            from hq_api.domain import feedback

            await feedback.ingest(
                tx, hub, company_id=conv["company_id"],
                company=await hub.companies.code_of(conv["company_id"]),
                source_ref=pending["ref"], text=comment, nps_response_id=resp["id"],
            )  # fmt: skip
            await tx.exec(
                "UPDATE growth.nps_waves SET comments_to_feedback = comments_to_feedback + 1 WHERE id = :w",
                w=pending["nps_wave_id"],
            )
        await _close_quietly(tx, conv)
        return "nps"
    csat = lead[0] if lead and not lead[1].strip() and 1 <= lead[0] <= 5 else None
    if csat is not None:
        prev = await tx.first(
            """SELECT id FROM support.conversations WHERE customer_id = :c AND state = 'closed'
                 AND csat IS NULL AND csat_asked_at > now() - make_interval(secs => :w)
               ORDER BY closed_at DESC LIMIT 1""",
            c=conv["customer_id"],
            w=desk.CSAT_WINDOW.total_seconds(),
        )
        if prev is not None:
            await tx.exec(
                "UPDATE support.conversations SET csat = :s WHERE id = :id", s=csat, id=prev["id"]
            )
            await _close_quietly(tx, conv)
            return "csat"
    return None


async def _close_quietly(tx: Tx, conv: dict[str, Any]) -> None:
    """The answer opened a fresh conversation only to carry the number: it
    is closed again at once (no support case, no statistic)."""
    if conv["state"] != "closed":
        n = await tx.scalar(
            "SELECT count(*) FROM support.messages WHERE conversation_id = :c", c=conv["id"]
        )
        if int(n or 0) <= 1:
            await tx.exec(
                """UPDATE support.conversations SET state = 'closed', closed_at = now(),
                       closed_by_kind = 'rule', closed_by_code = 'answer' WHERE id = :id""",
                id=conv["id"],
            )


async def on_closed(tx: Tx, hub: Any, conv: dict[str, Any]) -> dict[str, Any] | None:
    """CSAT after a conversation closes (the sealed csat rule, if active)."""
    if conv["mystery"]:
        return None
    out = await send_template(
        tx, hub, company_id=conv["company_id"], purpose="csat",
        dedupe_key=f"csat:{conv['ref']}", conversation_id=conv["id"],
    )  # fmt: skip
    if out.get("message_id"):
        await tx.exec(
            "UPDATE support.conversations SET csat_asked_at = now() WHERE id = :id", id=conv["id"]
        )
    return out


# ---------------------------------------------------------- decision cards --
def _parse_tref(value: str) -> tuple[str, int]:
    m = re.fullmatch(r"(TM-[0-9]{4,6})@([0-9]{1,6})", value or "")
    if not m:
        raise ApiError(422, "validation_failed", fields={"payload.rule.template": "TM-…@version"})
    return m.group(1), int(m.group(2))


async def card_payload(
    tx: Tx,
    who: Any,
    company_id: UUID,
    company_code: str,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """An agent's (or the owner's) message_template / lifecycle_rule card:
    the proposed template or rule version is written now and the card
    carries it (contract §19.9 ⟨1.5.1⟩ payload shapes)."""
    by_kind: Literal["owner", "agent", "service"] = (
        "owner" if who.kind == "owner" else "agent" if who.kind == "agent" else "service"
    )
    if kind == "message_template":
        t_in = payload.get("template") or {}
        row = await propose_template(
            tx,
            company_id=company_id,
            purpose=str(t_in.get("purpose") or ""),
            body_fa=str(t_in.get("body_fa") or ""),
            variables=[str(v) for v in t_in.get("variables") or []],
            by_kind=by_kind,
            by_code=who.code,
            ref=t_in.get("ref"),
        )
        rendered = json.loads(render_template(row, company_code).model_dump_json())
        return {"template": rendered, "sha256": row["sha256"]}
    r_in = payload.get("rule") or {}
    tref_, tver = _parse_tref(str(r_in.get("template") or ""))
    row = await create_rule(
        tx,
        company_id=company_id,
        kind=str(r_in.get("kind") or ""),
        template_ref=tref_,
        template_version=tver,
        channel=str(r_in.get("channel") or "telegram_bot"),
        trigger=r_in.get("trigger"),
        limits=r_in.get("limits"),
        by_kind=by_kind,
        by_code=who.code,
        ref=r_in.get("ref"),
    )
    rendered_rule = json.loads(render_rule(row, company_code).model_dump_json())
    return {"rule": rendered_rule, "template": f"{tref_}@{tver}", "limits": rendered_rule["limits"]}


async def apply_card(tx: Tx, d: dict[str, Any], step_up_id: UUID | None) -> dict[str, Any]:
    """The sealed card, bound to its payload: a template or rule that has a
    newer version since the card (or is no longer proposed) supersedes it."""
    p = d["payload"] or {}
    if d["kind"] == "support_go_live":
        from hq_api.domain import shadow

        return await shadow.apply_go_live(tx, d, step_up_id)
    if d["kind"] == "message_template":
        t = p.get("template") or {}
        ref, version = str(t.get("ref")), int(t.get("version") or 0)
        top = await tx.scalar("SELECT max(version) FROM growth.templates WHERE ref = :r", r=ref)
        if top is None or int(top) != version:
            raise ApiError(409, "decision_not_pending", f"{ref} has a newer version than the card")
        row = await seal_template(
            tx, ref, version, step_up_id=step_up_id, decision_id=d["id"], sha256=p.get("sha256")
        )
        return {"template": f"{row['ref']}@{row['version']}", "status": row["status"]}
    r = p.get("rule") or {}
    ref, version = str(r.get("ref")), int(r.get("version") or 0)
    current = await tx.first(
        "SELECT version, status FROM growth.rules WHERE ref = :r ORDER BY version DESC LIMIT 1",
        r=ref,
    )
    if current is None or int(current["version"]) != version or current["status"] != "proposed":
        raise ApiError(409, "decision_not_pending", f"{ref}@{version} changed since the card")
    row = await seal_rule(tx, ref, version, step_up_id=step_up_id, decision_id=d["id"])
    return {"rule": f"{row['ref']}@{row['version']}", "status": row["status"]}
