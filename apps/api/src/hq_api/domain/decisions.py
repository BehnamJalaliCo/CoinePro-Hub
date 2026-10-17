"""Decisions (contract §5.1, OPERATING_MODEL §1.7 decision cycle).

propose -> (owner, or a CEO within its authority, decides) -> resolution
M-xxxx -> message to the proposer -> effect (applied by the worker's
DecisionLifecycle workflow: hire, recurring approval, dismissal, budget
change) -> follow-up work when needed. Authority is policy (OPA), not code.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import notify, org, recurring
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Model, actor

KINDS = (
    "hire",
    "dismissal",
    "recurring_approval",
    "deploy",
    "a3_action",
    "proposal",
    "budget_change",
    "evaluation",
)
ACTION_CLASS = {
    "hire": "A2",
    "dismissal": "A2",
    "recurring_approval": "A2",
    "deploy": "A3",
    "a3_action": "A3",
    "proposal": "A1",
    "budget_change": "A2",
    "evaluation": "A1",
}
# Kinds whose approval needs the owner's step-up (🔏) besides every A3.
STEP_UP_KINDS = ("hire", "dismissal", "budget_change")
EFFECT_KINDS = ("hire", "dismissal", "recurring_approval", "budget_change")
FOLLOW_UP_KINDS = ("deploy", "a3_action", "proposal")
Effort = Literal["low", "medium", "high", "xhigh", "max"]
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"


# ----------------------------------------------------------------- payloads --
class Quota(Model):
    tokens: int | None = Field(default=None, ge=0)
    usd: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=6)


class HirePayload(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    title_fa: str = Field(min_length=1, max_length=200)
    title_en: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=5000)
    duties: list[str] = Field(default_factory=list, max_length=50)
    model: str = Field(min_length=3, max_length=100)
    effort: Effort
    permissions: list[str] = Field(default_factory=list, max_length=50)
    quota_estimate_month: Quota | None = None


class DismissalPayload(Model):
    employee: str = Field(pattern=EMP)
    reason: str = Field(min_length=1, max_length=5000)
    transfer_to: str | None = Field(default=None, pattern=EMP)


class RecurringPayload(Model):
    work_id: UUID
    escrow: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None


class DeployPayload(Model):
    repo: str = Field(min_length=1, max_length=200)
    pr_url: str = Field(pattern=r"^https://", max_length=500)
    diff_stat: str = Field(default="", max_length=2000)
    ci: dict[str, Any] = Field(default_factory=dict)
    tests: dict[str, Any] = Field(default_factory=dict)
    rollout: str = Field(default="", max_length=2000)


class A3Payload(Model):
    action: Literal["publish", "customer_message", "group_message", "restart", "price_change"]
    target: str = Field(min_length=1, max_length=300)
    preview: str = Field(default="", max_length=20000)


class ProposalPayload(Model):
    okr: str = Field(default="", max_length=500)
    cost: str = Field(default="", max_length=1000)
    risk: str = Field(default="", max_length=1000)
    expected_impact: str = Field(default="", max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=10)


class BudgetChangePayload(Model):
    scope: dict[str, str]
    period: Literal["day", "month"]
    token_limit: int | None = Field(default=None, gt=0)
    usd_limit: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)


class EvaluationPayload(Model):
    employee: str = Field(pattern=EMP)
    recommendation: Literal["promote", "demote", "dismiss"]
    evidence: str = Field(default="", max_length=5000)


PAYLOADS: dict[str, type[Model]] = {
    "hire": HirePayload,
    "dismissal": DismissalPayload,
    "recurring_approval": RecurringPayload,
    "deploy": DeployPayload,
    "a3_action": A3Payload,
    "proposal": ProposalPayload,
    "budget_change": BudgetChangePayload,
    "evaluation": EvaluationPayload,
}


class DecisionIn(Model):
    kind: Literal[
        "hire",
        "dismissal",
        "recurring_approval",
        "deploy",
        "a3_action",
        "proposal",
        "budget_change",
        "evaluation",
    ]
    title: str = Field(min_length=1, max_length=300)
    what: str = Field(default="", max_length=20000)
    why: str = Field(default="", max_length=20000)
    work_id: UUID | None = None
    quota_estimate: Quota | None = None
    risk: Literal["low", "medium", "high"] = "low"
    risk_note: str | None = Field(default=None, max_length=2000)
    reversible: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None


# ------------------------------------------------------------------ output --
class Seal(BaseModel):
    sealed_at: datetime
    method: str
    step_up_id: UUID | None


class QuotaOut(BaseModel):
    tokens: int | None
    usd: Decimal | None


class Decision(BaseModel):
    id: UUID
    ref: str
    company: str
    kind: str
    action_class: str
    title: str
    what: str
    why: str
    proposer: Actor
    work_id: UUID | None
    quota_estimate: QuotaOut
    risk: str
    risk_note: str | None
    reversible: bool
    payload: dict[str, Any]
    status: str
    expires_at: datetime | None
    decided_at: datetime | None
    decided_by: Actor | None
    seal: Seal | None
    note: str | None
    reason_code: str | None
    resolution: str | None
    thread: str | None
    digital_ceo_prediction: dict[str, Any] | None = None
    effect_status: str
    version: int
    created_at: datetime


DECISION_SQL = """
    SELECT d.*, c.code AS company, r.ref AS resolution
    FROM cartable.decisions d
    JOIN core.companies c ON c.id = d.company_id
    LEFT JOIN cartable.resolutions r ON r.id = d.resolution_id
"""


def render(r: dict[str, Any]) -> Decision:
    proposer = actor(r["proposer_kind"], r["proposer_code"])
    assert proposer is not None
    return Decision(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        kind=r["kind"],
        action_class=r["action_class"],
        title=r["title"],
        what=r["what"],
        why=r["why"],
        proposer=proposer,
        work_id=r["work_id"],
        quota_estimate=QuotaOut(tokens=r["quota_tokens"], usd=r["quota_usd"]),
        risk=r["risk"],
        risk_note=r["risk_note"],
        reversible=r["reversible"],
        payload=r["payload"],
        status=r["status"],
        expires_at=r["expires_at"],
        decided_at=r["decided_at"],
        decided_by=actor(r["decided_by_kind"], r["decided_by_code"]),
        seal=Seal(sealed_at=r["seal_at"], method=r["seal_method"], step_up_id=r["seal_step_up_id"])
        if r["seal_at"]
        else None,
        note=r["note"],
        reason_code=r["reason_code"],
        resolution=r["resolution"],
        thread=r["thread_code"],
        effect_status=r["effect_status"],
        version=r["version"],
        created_at=r["created_at"],
    )


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT 1 FROM cartable.decisions WHERE ref = :ref FOR UPDATE", ref=ref)
    return await tx.one(DECISION_SQL + " WHERE d.ref = :ref", ref=ref)


def validate_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        model: Model = PAYLOADS[kind].model_validate(payload)
    except ValidationError as exc:
        fields = {
            "payload." + ".".join(str(p) for p in e["loc"]): e["msg"][:200]
            for e in exc.errors()[:20]
        }
        raise ApiError(422, "validation_failed", fields=fields) from exc
    out: dict[str, Any] = json.loads(model.model_dump_json(exclude_none=True))
    return out


async def known_model(tx: Tx, model: str) -> bool:
    return bool(
        await tx.scalar("SELECT EXISTS (SELECT 1 FROM llm.connections WHERE models ? :m)", m=model)
    )


# ----------------------------------------------------------------- propose --
async def propose(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    company_code: str,
    body: DecisionIn,
    thread_code: str | None,
) -> dict[str, Any]:
    payload = validate_payload(body.kind, body.payload)
    if body.kind == "hire":
        if payload["company"] != company_code:
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.company": "must be the proposer's company"},
            )
        if not await tx.scalar(
            "SELECT 1 FROM core.departments WHERE company_id = :co AND code = :d",
            co=company_id,
            d=payload["department"],
        ):
            raise ApiError(
                422, "validation_failed", fields={"payload.department": "unknown in this company"}
            )
        if not await known_model(tx, payload["model"]):
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.model": "no connection offers this model"},
            )
    if body.kind in ("dismissal", "evaluation"):
        emp = await tx.first(
            "SELECT company_id, status FROM core.employees WHERE code = :c", c=payload["employee"]
        )
        if emp is None or emp["company_id"] != company_id:
            raise ApiError(
                422, "validation_failed", fields={"payload.employee": "unknown in this company"}
            )
    if body.kind == "recurring_approval":
        w = await tx.first(
            "SELECT company_id, kind FROM work.work WHERE id = :id", id=payload["work_id"]
        )
        if w is None or w["company_id"] != company_id or w["kind"] != "recurring":
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.work_id": "a recurring work of this company"},
            )
    if body.work_id and not await tx.scalar(
        "SELECT 1 FROM work.work WHERE id = :id AND company_id = :co",
        id=body.work_id,
        co=company_id,
    ):
        raise ApiError(422, "validation_failed", fields={"work_id": "unknown work of this company"})
    row = await tx.one(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, what, why,
               proposer_kind, proposer_code, work_id, quota_tokens, quota_usd, risk, risk_note,
               reversible, payload, expires_at, thread_code)
           VALUES (:co, :kind, :cls, :title, :what, :why, :pk, :pc, :work, :qt, :qu, :risk, :rn, :rev,
                   CAST(:payload AS jsonb), :exp, :thread)
           RETURNING ref""",
        co=company_id,
        kind=body.kind,
        cls=ACTION_CLASS[body.kind],
        title=body.title,
        what=body.what,
        why=body.why,
        pk=who.kind,
        pc=who.code,
        work=body.work_id,
        qt=body.quota_estimate.tokens if body.quota_estimate else None,
        qu=body.quota_estimate.usd if body.quota_estimate else None,
        risk=body.risk,
        rn=body.risk_note,
        rev=body.reversible,
        payload=json.dumps(payload, ensure_ascii=False),
        exp=body.expires_at,
        thread=thread_code,
    )
    d = await load(tx, row["ref"])
    await events.emit(
        tx,
        company_code,
        "decision.created",
        d["ref"],
        {
            "kind": d["kind"],
            "risk": d["risk"],
            "proposer": who.code,
            "action_class": d["action_class"],
        },
    )
    await notify.raise_notification(
        tx,
        company_id=company_id,
        company_code=company_code,
        level="decision",
        title_fa=f"تصمیم تازه {d['ref']}: {d['title'][:120]}",
        body_fa=f"پیشنهاد {who.code} · ریسک {d['risk']} · {'برگشت‌پذیر' if d['reversible'] else 'برگشت‌ناپذیر'}",
        link_kind="decision",
        link_ref=d["ref"],
        source_kind=who.kind,
        source_code=who.code,
    )
    return d


# ------------------------------------------------------------------ decide --
async def within_quota(tx: Tx, decision: dict[str, Any]) -> bool:
    """A CEO may approve recurring work only inside the company's monthly
    budget (§1.4): active escrows' monthly caps + this one <= the budget."""
    if decision["kind"] != "recurring_approval":
        return False
    budget = await tx.first(
        """SELECT usd_limit FROM llm.budgets b JOIN core.companies c ON c.id = b.company_id
           WHERE b.company_id = :co AND b.scope_type = 'company' AND b.scope_ref = c.code
             AND b.period = 'month' AND b.enabled""",
        co=decision["company_id"],
    )
    if budget is None or budget["usd_limit"] is None:
        return False
    escrow = await tx.first(
        "SELECT usd_cap_per_month FROM work.escrows WHERE work_id = :w",
        w=decision["payload"].get("work_id"),
    )
    if escrow is None:
        return False
    committed = await tx.scalar(
        "SELECT COALESCE(sum(usd_cap_per_month), 0) FROM work.escrows WHERE company_id = :co AND status = 'active'",
        co=decision["company_id"],
    )
    return bool(
        Decimal(committed) + Decimal(escrow["usd_cap_per_month"]) <= Decimal(budget["usd_limit"])
    )


def opa_input(who: Principal, d: dict[str, Any], quota_ok: bool) -> dict[str, Any]:
    return {
        "principal": who.opa(),
        "decision": {
            "kind": d["kind"],
            "company": d["company"],
            "action_class": d["action_class"],
            "payload": d["payload"],
        },
        # No approved content calendar exists in v1, so CEO approval of a
        # publish (§1.12) is not reachable yet; the policy already supports it.
        "context": {"within_quota": quota_ok, "in_content_calendar": False},
    }


async def post_system_message(
    tx: Tx, thread_code: str | None, body: str, links: dict[str, str]
) -> str | None:
    if not thread_code:
        return None
    t = await tx.first("SELECT id FROM msg.threads WHERE code = :c", c=thread_code)
    if t is None:
        return None
    m = await tx.one(
        "SELECT ref, company_id FROM msg.post(:t, 'service', 'system', :body, CAST(:links AS jsonb), NULL, 'system')",
        t=t["id"],
        body=body,
        links=json.dumps(links),
    )
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=m["company_id"])
    await events.emit(
        tx, code, "message.created", m["ref"], {"thread": thread_code, "author": "system"}
    )
    ref: str = m["ref"]
    return ref


async def decide(
    tx: Tx,
    who: Principal,
    d: dict[str, Any],
    verdict: Literal["approved", "rejected", "returned"],
    *,
    note: str | None,
    reason_code: str | None = None,
    amendments: dict[str, Any] | None = None,
    step_up_id: UUID | None = None,
) -> dict[str, Any]:
    if d["status"] != "pending":
        raise ApiError(409, "decision_not_pending", f"{d['ref']} is {d['status']}")
    effect = "pending" if verdict == "approved" and d["kind"] in EFFECT_KINDS else "none"
    await tx.exec(
        """UPDATE cartable.decisions SET status = :st, decided_at = now(), decided_by_kind = :k,
               decided_by_code = :c, note = :note, reason_code = :rc, amendments = CAST(:am AS jsonb),
               seal_at = CASE WHEN CAST(:su AS uuid) IS NULL THEN NULL ELSE now() END,
               seal_method = CASE WHEN CAST(:su AS uuid) IS NULL THEN NULL ELSE 'passkey_uv' END,
               seal_step_up_id = :su, effect_status = :eff
           WHERE id = :id""",
        id=d["id"],
        st=verdict,
        k=who.kind,
        c=who.code,
        note=note,
        rc=reason_code,
        am=json.dumps(amendments) if amendments else None,
        su=step_up_id,
        eff=effect,
    )
    resolution = None
    if verdict == "approved":
        # Resolutions are append-only: the follow-up work (if any) exists first
        # and the resolution row records it from the start.
        ref = await tx.scalar("SELECT cartable.next_resolution_ref()")
        follow = None
        if d["kind"] in FOLLOW_UP_KINDS and d["proposer_kind"] == "agent":
            follow = await follow_up(tx, who, d, ref)
        resolution = await record_resolution(
            tx,
            who,
            company_id=d["company_id"],
            title=d["title"],
            body=(d["what"] or "") + (f"\n\nیادداشت مدیر کل: {note}" if note else ""),
            decision_id=d["id"],
            sent_to=[d["proposer_code"]] if d["proposer_kind"] == "agent" else [],
            ref=ref,
            follow_up_work_id=follow["id"] if follow else None,
        )
        await tx.exec(
            "UPDATE cartable.decisions SET resolution_id = :r WHERE id = :id",
            r=resolution["id"],
            id=d["id"],
        )
        body = f"تصمیم {d['ref']} تأیید شد · مصوبه‌ی {resolution['ref']}"
    elif verdict == "rejected":
        body = f"تصمیم {d['ref']} رد شد" + (f" (دلیل: {reason_code})" if reason_code else "")
    else:
        body = f"تصمیم {d['ref']} با یادداشت برگشت خورد"
    if note:
        body += f"\n\n{note}"
    links = {"decision": d["ref"]}
    if resolution:
        links["resolution"] = resolution["ref"]
    await post_system_message(tx, d["thread_code"], body, links)
    await events.emit(
        tx,
        d["company"],
        "decision.decided",
        d["ref"],
        {
            "status": verdict,
            "kind": d["kind"],
            "resolution": resolution["ref"] if resolution else None,
        },
    )
    return await load(tx, d["ref"])


async def record_resolution(
    tx: Tx,
    who: Principal,
    *,
    company_id: UUID,
    title: str,
    body: str,
    decision_id: UUID | None = None,
    message_id: UUID | None = None,
    sent_to: list[str] | None = None,
    ref: str | None = None,
    follow_up_work_id: UUID | None = None,
) -> dict[str, Any]:
    return await tx.one(
        """INSERT INTO cartable.resolutions (ref, company_id, title, body, source_decision_id,
               source_message_id, sealed_by_kind, sealed_by_code, sent_to, follow_up_work_id)
           VALUES (COALESCE(:ref, cartable.next_resolution_ref()), :co, :title, :body, :dec, :msg, :k, :c,
                   :to, :fw)
           RETURNING id, ref""",
        ref=ref,
        co=company_id,
        title=title[:300],
        body=body[:50000],
        dec=decision_id,
        msg=message_id,
        k="owner" if who.is_owner else "agent",
        c=who.code,
        to=sent_to or [],
        fw=follow_up_work_id,
    )


async def follow_up(
    tx: Tx, who: Principal, d: dict[str, Any], resolution_ref: str
) -> dict[str, Any]:
    """Approved deploy/A3/proposal: a work item for the proposer to carry it out."""
    w = await W.create(
        tx,
        who,
        company_id=d["company_id"],
        company_code=d["company"],
        title=f"Carry out {resolution_ref}: {d['title']}"[:300],
        brief=f"Approved decision {d['ref']} (resolution {resolution_ref}).",
        kind="one_off",
        priority="P2",
        assignee_code=d["proposer_code"],
    )
    await W.event(tx, w, "follow_up_of", who, {"decision": d["ref"], "resolution": resolution_ref})
    return w


# ----------------------------------------------------------------- effects --
async def apply_effect(tx: Tx, ref: str, who: Principal) -> dict[str, Any]:
    """Idempotent: only a decision with effect_status 'pending' is applied."""
    d = await load(tx, ref, lock=True)
    if d["effect_status"] != "pending":
        return {"ref": ref, "effect": d["effect_status"], "changed": False}
    p = d["payload"]
    result: dict[str, Any] = {}
    if d["kind"] == "hire":
        emp = await org.hire(
            tx,
            company_id=d["company_id"],
            company_code=d["company"],
            department_code=p["department"],
            title_fa=p["title_fa"],
            title_en=p["title_en"],
            duties=p.get("duties", []),
            permissions=p.get("permissions", []),
            decision_id=d["id"],
        )
        await tx.exec(
            """INSERT INTO llm.assignments (scope_type, scope_ref, model, effort, note)
               VALUES ('role', :ref, :model, :effort, :note)
               ON CONFLICT (scope_type, scope_ref) DO UPDATE
                   SET model = EXCLUDED.model, effort = EXCLUDED.effort, note = EXCLUDED.note, updated_at = now()""",
            ref=f"{d['company']}:{emp['code']}",
            model=p["model"],
            effort=p["effort"],
            note=f"hired by {d['ref']}",
        )
        await post_system_message(
            tx,
            d["thread_code"],
            f"کارمند {emp['code']} استخدام شد ({p['title_fa']}) · {p['model']} / {p['effort']}",
            {"decision": d["ref"], "employee": emp["code"]},
        )
        await events.emit(
            tx,
            d["company"],
            "employee.updated",
            emp["code"],
            {"change": "hired", "decision": d["ref"]},
        )
        result = {"employee": emp["code"]}
    elif d["kind"] == "recurring_approval":
        tpl = await W.load(tx, p["work_id"])
        run = await recurring.activate(tx, tpl, actor_principal(d), decision_id=d["id"])
        result = {"work": tpl["ref"], "first_run": run["ref"] if run else None}
        await post_system_message(
            tx,
            d["thread_code"],
            f"کار دائمی {tpl['ref']} فعال شد" + (f" · اجرای اول {run['ref']}" if run else ""),
            {"decision": d["ref"], "work": tpl["ref"]},
        )
    elif d["kind"] == "dismissal":
        emp = await tx.one(
            "SELECT id, code, kind, status, company_id, department_id FROM core.employees WHERE code = :c FOR UPDATE",
            c=p["employee"],
        )
        result = await org.dismiss(tx, emp, reason=p["reason"], transfer_to=p.get("transfer_to"))
        await events.emit(
            tx, d["company"], "employee.updated", emp["code"], {"status": "dismissed"}
        )
    elif d["kind"] == "budget_change":
        scope = p["scope"]
        await tx.exec(
            """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit, usd_limit)
               VALUES (:co, :st, :sr, :per, :tl, :ul)
               ON CONFLICT (scope_type, scope_ref, period) DO UPDATE
                   SET token_limit = EXCLUDED.token_limit, usd_limit = EXCLUDED.usd_limit, enabled = true,
                       updated_at = now()""",
            co=d["company_id"],
            st=scope.get("scope_type", "company"),
            sr=scope.get("scope_ref", d["company"]),
            per=p["period"],
            tl=p.get("token_limit"),
            ul=p.get("usd_limit"),
        )
        result = {
            "budget": f"{scope.get('scope_type', 'company')}:{scope.get('scope_ref', d['company'])}"
        }
    await tx.exec(
        "UPDATE cartable.decisions SET effect_status = 'applied', effect_applied_at = now() WHERE id = :id",
        id=d["id"],
    )
    return {"ref": ref, "effect": "applied", "changed": True, **result}


def actor_principal(d: dict[str, Any]) -> Principal:
    """Who approved, as a principal (for records written by the effect)."""
    if d["decided_by_kind"] == "owner":
        return Principal(kind="owner", code="owner", role="owner")
    return Principal(kind="agent", code=d["decided_by_code"], role="ceo")


async def mark_effect_failed(tx: Tx, ref: str, error: str) -> None:
    await tx.exec(
        """UPDATE cartable.decisions SET effect_status = 'failed', effect_error = :e
           WHERE ref = :ref AND effect_status = 'pending'""",
        ref=ref,
        e=error[:500],
    )
