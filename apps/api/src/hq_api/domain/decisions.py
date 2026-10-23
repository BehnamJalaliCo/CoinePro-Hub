"""Decisions (contract §5.1, OPERATING_MODEL §1.7 decision cycle).

propose -> (owner, or a CEO within its authority, decides) -> resolution
M-xxxx -> message to the proposer -> effect (applied by the worker's
DecisionLifecycle workflow: hire, recurring approval, dismissal, budget
change) -> follow-up work when needed. Authority is policy (OPA), not code.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import errands, hiring, mcp, notify, org, oversight, recurring, stars
from hq_api.domain import substitutes as S
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, Model, actor
from hq_api.workshop import domain as workshop

KINDS = (
    "hire",
    "dismissal",
    "recurring_approval",
    "deploy",
    "a3_action",
    "proposal",
    "budget_change",
    "evaluation",
    "code_session",
    "errand_action",
    "lesson_adoption",
    "protocol",
    "company_found",
    "server_plan",
    "tool_enable",
    # ⟨1.5⟩ prompt 10 (contract §19.9): a template, a lifecycle rule, a channel's go-live
    "message_template",
    "lifecycle_rule",
    "support_go_live",
    # ⟨1.6⟩ prompt 13 (contract §22.6): a series sealed on its digest, an item to
    # publish outside a sealed series, a role written on demand
    "media_series",
    "media_publish",
    "role_new",
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
    "code_session": "A1",
    # ⟨1.4⟩ an errand's external commitment (contract §18.3): the owner's seal
    "errand_action": "A3",
    "lesson_adoption": "A1",
    "protocol": "A1",
    # ⟨1.4⟩ prompt 09 (contract §18.8): founding a company is the owner's seal;
    # a server plan spends money (the A3 seal, on the plan's digest).
    "company_found": "A2",
    "server_plan": "A3",
    "tool_enable": "A2",
    # ⟨1.5⟩ sealing a rule is the owner's A3 approval in advance (§19.5); a
    # channel's go-live lets approved answers reach customers without the owner
    "message_template": "A2",
    "lifecycle_rule": "A3",
    "support_go_live": "A3",
    # ⟨1.6⟩ the seal on a series is the owner's A3 approval in advance of its
    # items (§22.0); a role is a new charter, sealed like a hire
    "media_series": "A3",
    "media_publish": "A3",
    "role_new": "A2",
}
# Kinds whose approval needs the owner's step-up (🔏) besides every A3.
# code_session: its seal is the grant (contract §17.3), so it is sealed like one.
# protocol (prompt 08 §2): a new or changed oversight protocol is the owner's seal.
# tool_enable: the seal re-enables an MCP server with its new listing (§18.13).
# lesson_adoption: every new kind of §18.10 is sealed with step-up (§18.15).
STEP_UP_KINDS = (
    "hire",
    "dismissal",
    "budget_change",
    "code_session",
    "protocol",
    "company_found",
    "tool_enable",
    "lesson_adoption",
    # ⟨1.5⟩ all three are sealed with step-up (contract §19.9)
    "message_template",
    "lifecycle_rule",
    "support_go_live",
    # ⟨1.5⟩ prompt 12 §6: a monthly HR evaluation is the owner's seal (§21.12)
    "evaluation",
    # ⟨1.6⟩ all sealed with step-up (contract §22.6)
    "media_series",
    "media_publish",
    "role_new",
)
# ⟨1.6⟩ cards only code writes (series.propose, the media pipeline, a role
# draft's gates); an agent's or the owner's `propose` of one is refused.
SYSTEM_CARD_KINDS = ("media_series", "media_publish", "role_new")
# ⟨1.5⟩ applied in the deciding transaction, bound to their payload (§19.9)
SEALED_CARD_KINDS = ("message_template", "lifecycle_rule", "support_go_live")
EFFECT_KINDS = (
    "hire",
    "dismissal",
    "recurring_approval",
    "budget_change",
    "code_session",
    "lesson_adoption",
    "protocol",
    "company_found",
    "evaluation",  # ⟨1.5⟩ promote / demote / dismiss / confirm (prompt 12 §6)
    "media_publish",  # ⟨1.6⟩ the item is published through the official APIs
    "role_new",  # ⟨1.6⟩ the draft becomes an active charter
)
FOLLOW_UP_KINDS = ("deploy", "a3_action", "proposal", "errand_action")
Effort = Literal["low", "medium", "high", "xhigh", "max"]
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"


# ----------------------------------------------------------------- payloads --
class Quota(Model):
    tokens: int | None = Field(default=None, ge=0)
    usd: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=6)


class HirePayload(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    # The charter the new employee runs with (agents/roles/<role>.md, prompt 05 §2):
    # required for approval; the proposer names it (an `employee` charter).
    role: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=200)
    title_en: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=5000)
    duties: list[str] = Field(default_factory=list, max_length=50)
    model: str = Field(min_length=3, max_length=100)
    effort: Effort
    permissions: list[str] = Field(default_factory=list, max_length=50)
    quota_estimate_month: Quota | None = None
    # Whom the new employee reports to (an active employee of the same company);
    # by default the department's manager.
    reports_to: str | None = Field(default=None, pattern=EMP)


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
    # ⟨1.5⟩ the card is bound to it, diff or not (contract §21.6)
    head_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    diff_stat: str = Field(default="", max_length=2000)
    ci: dict[str, Any] = Field(default_factory=dict)
    tests: dict[str, Any] = Field(default_factory=dict)
    rollout: str = Field(default="", max_length=2000)
    # ⟨1.5⟩ written by the api from the repository, never by the proposer (§21.6)
    diff: dict[str, Any] | None = None
    diff_unavailable: Literal["no_access", "too_large", "fetch_failed"] | None = None
    # ⟨1.5⟩ the substitute's second code review (§21.13), read from its call
    # when the card is shown (the payload never changes); never the proposer's
    second_review: dict[str, Any] | None = None


class A3Payload(Model):
    # mcp_call (prompt 07 §3, 7.1 §2.10): an MCP tool the owner registered as
    # A3; made by the api itself when an agent calls it (target
    # "<server>/<tool>", the arguments with only their secrets masked, so the
    # owner sees recipients and amounts, their SHA-256 and the registration's).
    # Approving it runs that one call once, in the follow-up run.
    action: Literal[
        "publish", "customer_message", "group_message", "restart", "price_change", "mcp_call"
    ]
    target: str = Field(min_length=1, max_length=300)
    preview: str = Field(default="", max_length=20000)
    args_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    server: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{1,39}$")
    tool: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.:/-]{0,127}$")
    args: dict[str, Any] | None = None
    registration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ListingDiff(Model):
    added: list[str] = Field(default_factory=list, max_length=500)
    removed: list[str] = Field(default_factory=list, max_length=500)
    changed: list[str] = Field(default_factory=list, max_length=500)


class ToolEnablePayload(Model):
    """An MCP server switched off because its listing changed (contract
    §18.13): the owner's seal re-enables it with exactly this listing."""

    key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,39}$")
    listing_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff: ListingDiff
    registration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ProposalPayload(Model):
    okr: str = Field(default="", max_length=500)
    cost: str = Field(default="", max_length=1000)
    risk: str = Field(default="", max_length=1000)
    expected_impact: str = Field(default="", max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=10)


class BudgetScope(Model):
    scope_type: Literal["holding", "company", "department", "role", "task_class"]
    scope_ref: str = Field(min_length=1, max_length=100)


class BudgetChangePayload(Model):
    scope: BudgetScope
    period: Literal["day", "month"]
    token_limit: int | None = Field(default=None, gt=0)
    usd_limit: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)


class EvaluationEvidence(Model):
    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=1000)


class EvaluationChange(Model):
    model: str | None = Field(default=None, min_length=3, max_length=100)
    effort: Effort | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)
    quota_estimate_month: Quota | None = None


class EvaluationPayload(Model):
    """⟨1.5⟩ payload v2 (contract §21.5); a v1 card's `evidence` was a text."""

    employee: str = Field(pattern=EMP)
    recommendation: Literal["promote", "demote", "dismiss", "confirm"]
    change: EvaluationChange | None = None
    transfer_to: str | None = Field(default=None, pattern=EMP)
    round: str | None = Field(default=None, pattern=r"^HR-[0-9]{4,}$")
    evidence: list[EvaluationEvidence] | str = Field(default_factory=list)
    unflagged: bool | None = None
    override_reason: str | None = Field(default=None, min_length=1, max_length=2000)


class CodeSessionPayload(Model):
    """A Code Workshop session asked for (contract §17.3): the owner's seal
    creates the grant (workspace, actions, the USD cap per session, an expiry
    `days` after the seal); the driver (the proposer by default) then opens
    the session through the internal API."""

    workspace: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]{2,20}$")
    actions: list[Literal["read", "edit", "run", "push_branch", "open_pr"]] = Field(
        min_length=1, max_length=5
    )
    budget_usd: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)
    days: int = Field(default=7, ge=1, le=90)
    driver: str | None = Field(default=None, pattern=EMP)
    title: str = Field(default="", max_length=300)
    brief: str = Field(default="", max_length=20000)
    area: str = Field(default="", max_length=300)


class ErrandActionPayload(Model):
    """⟨1.4⟩ The external commitment of an errand (contract §18.3), prepared to
    the last click: exactly what will happen, what it costs and how it is
    undone. Approved or not, no agent makes it (the owner takes the step)."""

    errand: str = Field(pattern=r"^E-[0-9]{4,}$")
    action: Literal["pay", "buy", "book", "sign_up", "send", "security_change", "other"]
    target: str = Field(min_length=1, max_length=300)  # the site, shop or recipient
    details_md: str = Field(min_length=1, max_length=20000)
    cost: str = Field(default="", max_length=300)  # as shown, e.g. "2,400,000 تومان"
    amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    undo_md: str = Field(min_length=1, max_length=5000)  # the way back
    deadline: datetime | None = None


class LessonAdoptionPayload(Model):
    """A CEO's answer to a lesson of the best company (contract §18.4): adopt
    it with a plan, or not with the reason; the owner decides."""

    lesson: str = Field(pattern=r"^L-[0-9]{4,}$")
    adopt: bool = True
    plan_md: str = Field(default="", max_length=10000)


class KpiTarget(Model):
    name_fa: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)


class TeamMember(Model):
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    model: str = Field(min_length=3, max_length=100)
    monthly_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    title_fa: str | None = Field(default=None, max_length=200)


class CompanyFoundPayload(Model):
    """⟨1.4⟩ The proposal of a founding (contract §18.8 Founding.proposal): the
    company as data, its team and roadmap; its server plan is sealed apart."""

    founding: str = Field(pattern=r"^C-[0-9]{4,}$")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    name_fa: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    departments: list[str] = Field(min_length=1, max_length=20)
    kpis: list[KpiTarget] = Field(default_factory=list, max_length=30)
    team: list[TeamMember] = Field(default_factory=list, max_length=30)
    roadmap_md: str = Field(default="", max_length=20000)
    monthly_usd: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    plan: str | None = Field(default=None, pattern=r"^PV-[0-9]{4,}$")


class ServerPlanPayload(Model):
    """⟨1.4⟩ A server plan to seal (contract §18.8): the seal is bound to its
    digest at /provisioning/plans/{ref}/seal, never through the cartable."""

    plan: str = Field(pattern=r"^PV-[0-9]{4,}$")
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")


class ProtocolPayload(Model):
    """An oversight protocol (contract §18.1) the overseer proposes: a new one
    (ref empty) or a new version of one (an edit, a pause, a resume)."""

    ref: str | None = Field(default=None, pattern=r"^PR-[0-9]{3,}$")
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


class MessageTemplatePayload(Model):
    """⟨1.5.1⟩ {template: Template, sha256}: an agent's proposal arrives as
    {template: {purpose, body_fa, variables?, ref?}} and the api writes the
    proposed template version and its sha256 into the card."""

    template: dict[str, Any]
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class LifecycleRulePayload(Model):
    """⟨1.5.1⟩ {rule: LifecycleRule, template: "TM-…@v", limits}: proposed as
    {rule: {kind, template, channel, trigger?, limits?, ref?}}."""

    rule: dict[str, Any]
    template: str | None = Field(default=None, pattern=r"^TM-[0-9]{4,6}@[0-9]+$")
    limits: dict[str, Any] | None = None


class SupportGoLivePayload(Model):
    """⟨1.5.1⟩ {company, channel, auto_send, verbatim_threshold,
    grounded_threshold, shadow_report}: made by the system on a passed run."""

    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    channel: Literal["telegram_business", "telegram_bot", "chatwoot", "product_bot"]
    auto_send: Literal["kb_verbatim", "kb_grounded", "off"]
    verbatim_threshold: float | None = Field(default=None, ge=0, le=1)
    grounded_threshold: float | None = Field(default=None, ge=0, le=1)
    shadow_report: dict[str, Any]


class MediaSeriesPayload(Model):
    """⟨1.6⟩ A series proposed for the owner's seal (contract §22.2): sealed on
    the series page on its digest (POST /media/series/{ref}/seal), never by
    the cartable's approve."""

    series: str = Field(pattern=r"^SR-[0-9]{4,}$")
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    title_fa: str = Field(min_length=1, max_length=200)
    kind: Literal["reel", "story", "post", "carousel"]
    auto_publish: bool = False
    max_per_day: int = Field(ge=1, le=20)
    schedule: str = Field(min_length=5, max_length=500)
    targets: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class MediaPlacement(Model):
    channel: Literal["telegram", "instagram"]
    placement: Literal[
        "telegram_post", "telegram_story", "instagram_reel", "instagram_story", "instagram_post"
    ]
    account: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,40}$")
    via: Literal["api", "manual"]
    blocked: str | None = Field(default=None, max_length=40)


class MediaPublishPayload(Model):
    """⟨1.6.1⟩ An item to publish outside a sealed series or after a failed
    check (contract §22.7): approving it publishes it (A3)."""

    item: str = Field(pattern=r"^MI-[0-9]{4,}$")
    series: str | None = Field(default=None, pattern=r"^SR-[0-9]{4,}$")
    kind: Literal["reel", "story", "post", "carousel"]
    title_fa: str = Field(min_length=1, max_length=300)
    why: str = Field(default="", max_length=2000)
    placements: list[MediaPlacement] = Field(default_factory=list, max_length=10)
    render: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class RoleNewPayload(Model):
    """⟨1.6.1⟩ A role written on demand for the owner's seal (contract §22.7)."""

    draft: str = Field(pattern=r"^RD-[0-9]{4,}$")
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    department: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,11}$")
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=3, max_length=100)
    effort: Effort
    limits: dict[str, Any]
    tools_count: int = Field(ge=0, le=200)
    review: dict[str, Any] | None = None
    eval_score: float | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


PAYLOADS: dict[str, type[Model]] = {
    "hire": HirePayload,
    "dismissal": DismissalPayload,
    "recurring_approval": RecurringPayload,
    "deploy": DeployPayload,
    "a3_action": A3Payload,
    "proposal": ProposalPayload,
    "budget_change": BudgetChangePayload,
    "evaluation": EvaluationPayload,
    "code_session": CodeSessionPayload,
    "errand_action": ErrandActionPayload,
    "lesson_adoption": LessonAdoptionPayload,
    "protocol": ProtocolPayload,
    "company_found": CompanyFoundPayload,
    "server_plan": ServerPlanPayload,
    "tool_enable": ToolEnablePayload,
    "message_template": MessageTemplatePayload,
    "lifecycle_rule": LifecycleRulePayload,
    "support_go_live": SupportGoLivePayload,
    "media_series": MediaSeriesPayload,
    "media_publish": MediaPublishPayload,
    "role_new": RoleNewPayload,
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
        "code_session",
        "errand_action",
        "lesson_adoption",
        "protocol",
        "company_found",
        "server_plan",
        "tool_enable",
        "message_template",
        "lifecycle_rule",
        "support_go_live",
        "media_series",
        "media_publish",
        "role_new",
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
    # ⟨1.4.3⟩ who decides the card: null = the owner; a company's CEO for
    # delegated hires (§18.11, prompt 8)
    approver: Actor | None = None
    work_id: UUID | None
    quota_estimate: QuotaOut
    risk: str
    risk_note: str | None
    reversible: bool
    payload: dict[str, Any]
    # The owner's amendments (applied on top of `payload` by the effect).
    amendments: dict[str, Any] | None = None
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
    # ⟨1.5⟩ the advisor's memos on this card (contract §21.1), oldest first
    memos: list[dict[str, Any]] = Field(default_factory=list)
    # ⟨1.5⟩ cartable reminders (contract §21.8): hours waiting, the thresholds sent
    waiting_h: float | None = None
    reminders: list[dict[str, Any]] = Field(default_factory=list)


DECISION_SQL = """
    SELECT d.*, c.code AS company, r.ref AS resolution,
           (SELECT COALESCE(jsonb_agg(jsonb_build_object('ref', m.ref, 'mode', m.mode, 'state', m.state)
                                      ORDER BY m.created_at), '[]'::jsonb)
              FROM advisor.memos m WHERE m.decision_id = d.id) AS memos,
           (SELECT COALESCE(jsonb_agg(jsonb_build_object('at', x.at, 'kind', x.kind) ORDER BY x.at), '[]')
              FROM owner.decision_reminders x WHERE x.decision_id = d.id) AS reminders,
           (SELECT jsonb_build_object('state', s.state, 'player', s.player, 'model', s.model,
                                      'result', s.result)
              FROM substitutes.calls s
             WHERE d.kind = 'deploy' AND s.purpose_kind = 'decision' AND s.purpose_ref = d.ref
               AND s.seat = 'code_review'
             ORDER BY s.created_at DESC LIMIT 1) AS second_review_call
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
        approver=actor(r.get("approver_kind"), r.get("approver_code")),
        work_id=r["work_id"],
        quota_estimate=QuotaOut(tokens=r["quota_tokens"], usd=r["quota_usd"]),
        risk=r["risk"],
        risk_note=r["risk_note"],
        reversible=r["reversible"],
        payload=_with_review(r),
        amendments=r["amendments"],
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
        memos=list(r.get("memos") or []),
        waiting_h=_waiting_h(r),
        reminders=list(r.get("reminders") or []),
    )


def _with_review(r: dict[str, Any]) -> dict[str, Any]:
    """A deploy card's payload with its `second_review` (prompt 12 §7 x §9.1):
    the latest code_review call's findings, or null while there is none."""
    if r["kind"] != "deploy":
        return dict(r["payload"])
    call = r.get("second_review_call")
    if isinstance(call, str):
        call = json.loads(call)
    return {**r["payload"], "second_review": S.second_review_of(call)}


def _waiting_h(r: dict[str, Any]) -> float | None:
    """Hours the card waited for its decision (until now while pending)."""
    end: datetime | None = r["decided_at"] or (
        datetime.now(UTC) if r["status"] == "pending" else None
    )
    start: datetime | None = r.get("created_at")
    if end is None or start is None:
        return None
    return round((end - start).total_seconds() / 3600, 1)


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT 1 FROM cartable.decisions WHERE ref = :ref FOR UPDATE", ref=ref)
    return await tx.one(DECISION_SQL + " WHERE d.ref = :ref", ref=ref)


def amended(
    kind: str, payload: dict[str, Any], amendments: dict[str, Any] | None
) -> dict[str, Any]:
    """The payload the effect uses: the original with the owner's amendments
    applied on top, validated like a proposal (422 when it no longer is one)."""
    if not amendments:
        return payload
    return validate_payload(kind, {**payload, **amendments})


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


def check_hire_role(
    payload: dict[str, Any], company_kind: str, charters: Any, *, required: bool
) -> None:
    """A hire's `role` must be an existing employee charter whose scope fits the
    company (company / holding) and whose department (if it has one) is the
    hire's department. 422 validation_failed otherwise."""
    role = payload.get("role")
    if role is None:
        if required:
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.role": "a charter (agents/roles) is required"},
            )
        return
    charter = charters.get(role) if charters is not None else None
    if charter is None:
        raise ApiError(422, "validation_failed", fields={"payload.role": f"no charter {role!r}"})
    if charter.kind != "employee":
        raise ApiError(
            422, "validation_failed", fields={"payload.role": f"{role} is a {charter.kind} charter"}
        )
    scope = "holding" if company_kind == "holding" else "company"
    if charter.scope != scope:
        raise ApiError(
            422, "validation_failed", fields={"payload.role": f"{role} is a {charter.scope} role"}
        )
    if charter.department and charter.department != payload["department"]:
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.department": f"{role} works in {charter.department}"},
        )


async def company_charters(tx: Tx, charters: Any, company_id: Any) -> Any:
    """⟨1.6⟩ The file charters plus the company's active role drafts (§22.5):
    a hire may name either; a draft only in its own company and department."""
    from hq_api.domain import role_drafts

    return await role_drafts.overlay(tx, charters, company_id)


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
    charters: Any = None,
    company_kind: str = "company",
    notify_owner: bool = True,
) -> dict[str, Any]:
    await hiring.require_open(tx, who, body.kind)  # before any card exists (§18.11)
    payload = validate_payload(body.kind, body.payload)
    if body.kind == "hire":
        # ⟨1.6⟩ a role written on demand is a charter of its company (§22.5)
        charters = await company_charters(tx, charters, company_id)
        check_hire_role(payload, company_kind, charters, required=who.is_agent)
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
        if payload.get("reports_to") and not await tx.scalar(
            """SELECT 1 FROM core.employees
               WHERE code = :c AND company_id = :co AND status = 'active' AND kind <> 'system'""",
            c=payload["reports_to"],
            co=company_id,
        ):
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.reports_to": "an active employee of this company"},
            )
    if body.kind in ("dismissal", "evaluation"):
        emp = await tx.first(
            "SELECT company_id, status FROM core.employees WHERE code = :c", c=payload["employee"]
        )
        if emp is None or emp["company_id"] != company_id:
            raise ApiError(
                422, "validation_failed", fields={"payload.employee": "unknown in this company"}
            )
    if body.kind == "evaluation":
        from hq_api.domain import hr

        payload = await hr.check_proposal(tx, payload, company_id)
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
    if body.kind == "code_session":
        ws = await tx.first(
            "SELECT company_id, status FROM workshop.workspaces WHERE code = :c",
            c=payload["workspace"],
        )
        if ws is None or ws["company_id"] != company_id:
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.workspace": "a workspace of this company"},
            )
        if who.is_agent and not payload.get("driver"):
            payload["driver"] = who.code  # the proposer drives the session it asked for
        if payload.get("driver") and not await tx.scalar(
            """SELECT 1 FROM core.employees
               WHERE code = :c AND company_id = :co AND status = 'active' AND kind <> 'system'""",
            c=payload["driver"],
            co=company_id,
        ):
            raise ApiError(
                422,
                "validation_failed",
                fields={"payload.driver": "an active employee of this company"},
            )
    if body.kind == "server_plan" and who.kind != "service":
        # A plan's card is the system's (server.plan or a founding makes it);
        # its seal is bound to the plan's digest (contract §18.8).
        raise ApiError(
            422, "validation_failed", fields={"kind": "a server plan comes from server.plan"}
        )
    if body.kind in SYSTEM_CARD_KINDS and who.kind != "service":
        # ⟨1.6⟩ series.propose, the media pipeline and a role draft's gates make
        # these cards, each bound to what it shows (contract §22.6)
        raise ApiError(
            422, "validation_failed", fields={"kind": f"a {body.kind} card is made by code"}
        )
    if body.kind == "support_go_live" and who.kind != "service":
        # ⟨1.5⟩ only a passed shadow run makes this card (contract §19.4)
        raise ApiError(409, "shadow_not_passed", "a go-live card comes from a passed shadow run")
    if body.kind in ("message_template", "lifecycle_rule"):
        from hq_api.domain import lifecycle

        payload = await lifecycle.card_payload(
            tx, who, company_id, company_code, body.kind, payload
        )
    if body.kind == "company_found":
        from hq_api.domain import founding

        await founding.check_proposal(tx, payload, company_id)
    # Still open: no card yet, or its card came back without an answer
    # (returned, expired, withdrawn), so the lesson may be proposed again.
    if body.kind == "lesson_adoption" and not await tx.scalar(
        """SELECT 1 FROM knowledge.lesson_adoptions a
           WHERE a.lesson_ref = :ref AND a.company_id = :co AND a.status = 'proposed'
             AND (a.decision_ref IS NULL OR EXISTS (
                  SELECT 1 FROM cartable.decisions x WHERE x.ref = a.decision_ref
                     AND x.status IN ('returned', 'expired', 'withdrawn')))""",
        ref=payload["lesson"],
        co=company_id,
    ):
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.lesson": "a lesson offered to this company and still open"},
        )
    if body.work_id and not await tx.scalar(
        "SELECT 1 FROM work.work WHERE id = :id AND company_id = :co",
        id=body.work_id,
        co=company_id,
    ):
        raise ApiError(422, "validation_failed", fields={"work_id": "unknown work of this company"})
    # ⟨1.4.3⟩ delegated hiring: an operating company's agent hire card is its
    # CEO's to decide (contract §18.11); the owner's own cards stay the owner's.
    approver = (
        await hiring.approver_for(tx, company_id, company_kind)
        if body.kind == "hire" and who.is_agent
        else None
    )
    row = await tx.one(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, what, why,
               proposer_kind, proposer_code, work_id, quota_tokens, quota_usd, risk, risk_note,
               reversible, payload, expires_at, thread_code, approver_kind, approver_code)
           VALUES (:co, :kind, :cls, :title, :what, :why, :pk, :pc, :work, :qt, :qu, :risk, :rn, :rev,
                   CAST(:payload AS jsonb), :exp, :thread, :ak, :ac)
           RETURNING ref""",
        ak="agent" if approver else None,
        ac=approver,
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
    if body.kind == "company_found":
        from hq_api.domain import founding

        await founding.proposed(tx, d, payload)
    if body.kind == "evaluation":
        from hq_api.domain import hr

        await hr.on_proposed(tx, d)
    if body.kind == "lesson_adoption":  # one answer per lesson and company
        await tx.exec(
            """UPDATE knowledge.lesson_adoptions SET decision_ref = :d, updated_at = now()
               WHERE lesson_ref = :ref AND company_id = :co""",
            d=d["ref"],
            ref=payload["lesson"],
            co=company_id,
        )
    if approver:
        # The CEO is woken by a work item for the card (contract §18.11); the
        # owner hears of the hire through its story and the digest.
        await W.create(
            tx,
            Principal(kind="service", code="hiring", role="service"),
            company_id=company_id,
            company_code=company_code,
            title=f"تصمیم درباره‌ی {d['ref']}: {d['title']}"[:300],
            brief=(
                f"کارت استخدام {d['ref']} ({who.code}) با تو است. با hire.decide "
                "(approve / reject / return) و یک یادداشت تصمیم بگیر؛ پاکت ماهانه‌ی شرکت، "
                "برآورد ماهانه و مدل انتخاب‌شده را بسنج (مدل قوی‌تر از نیاز کار، کارایی را کم میکند)."
            ),
            kind="one_off",
            priority="P2",
            assignee_code=approver,
        )
        # Watch mode holds a card a CEO decides as well (contract §18.15).
        await oversight.hold_if_watching(tx, d)
        return d
    if not notify_owner:  # the owner wrote it (a direct hire): nothing to tell them
        return d
    await oversight.hold_if_watching(tx, d)
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
            # Nobody approves their own proposal (contract §5.1 v1.1).
            "proposer": {"kind": d["proposer_kind"], "code": d["proposer_code"]},
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
    charters: Any = None,
) -> dict[str, Any]:
    if d["status"] != "pending":
        raise ApiError(409, "decision_not_pending", f"{d['ref']} is {d['status']}")
    if verdict == "approved":
        # A hold (the overseer's, or watch mode's) stops the approval until the
        # owner releases it; rejecting or returning stays possible.
        await oversight.require_not_held(tx, "decision", d["ref"])
    if verdict == "approved" and d["kind"] == "hire":
        # Every approval, whoever approves (contract §18.11): refused with a
        # stable code before anything changes, so no employee is made.
        charters = await company_charters(tx, charters, d["company_id"])
        await hiring.check_approval(
            tx, d, amended("hire", d["payload"], amendments), charters, by_ceo=who.is_agent
        )
    if verdict == "approved" and d["kind"] == "evaluation":
        # ⟨1.5⟩ prompt 12 §6: promote / demote under the hire checks of §18.11,
        # before anything changes (409 envelope_exceeded)
        from hq_api.domain import hr

        await hr.check_approval(tx, d, amended("evaluation", d["payload"], amendments))
    if verdict in ("rejected", "returned") and d["kind"] == "company_found":
        from hq_api.domain import founding

        await founding.proposal_declined(tx, d, verdict)
    if verdict == "rejected" and d["kind"] == "lesson_adoption":
        await stars.adoption_decided(
            tx, d["payload"]["lesson"], d["company_id"], "rejected", d["ref"]
        )
    if verdict == "returned" and d["kind"] == "lesson_adoption":
        await stars.adoption_reopened(tx, d["payload"]["lesson"], d["company_id"], d["ref"])
    if d["kind"] == "hire" and d.get("approver_code") and who.code != d["approver_code"]:
        # The owner decided a CEO's card first: the CEO's «decide D-…» item closes.
        await hiring.close_decide_items(tx, [d["ref"]], f"{d['ref']}: مالک خودش تصمیم گرفت")
    effect = "pending" if verdict == "approved" and d["kind"] in EFFECT_KINDS else "none"
    server = None
    sealed_as_is = d["kind"] == "tool_enable" or (
        d["kind"] == "a3_action" and (d["payload"] or {}).get("action") == "mcp_call"
    )
    if verdict == "approved" and amendments and sealed_as_is:
        # Bound to exactly what it shows (a listing; a call's arguments and their hash).
        raise ApiError(
            422, "validation_failed", fields={"amendments": "this card is sealed as it is"}
        )
    if verdict == "approved" and d["kind"] == "tool_enable":
        # Bound to the listing it shows: superseded (409) when the server changed.
        server = await mcp.sealed_listing(tx, d)
        effect = "applied"
    if verdict == "approved" and d["kind"] in SEALED_CARD_KINDS:
        if amendments:
            raise ApiError(
                422, "validation_failed", fields={"amendments": "this card is sealed as it is"}
            )
        # ⟨1.5⟩ bound to its payload: a template, rule or shadow report that
        # changed since the card supersedes it (409, nothing changes)
        from hq_api.domain import lifecycle

        await lifecycle.apply_card(tx, d, step_up_id)
        effect = "applied"
    await tx.exec(
        """UPDATE cartable.decisions SET status = :st, decided_at = now(), decided_by_kind = :k,
               decided_by_code = :c, note = :note, reason_code = :rc, amendments = CAST(:am AS jsonb),
               seal_at = CASE WHEN CAST(:su AS uuid) IS NULL THEN NULL ELSE now() END,
               seal_method = CASE WHEN CAST(:su AS uuid) IS NULL THEN NULL ELSE 'passkey_uv' END,
               seal_step_up_id = :su, effect_status = :eff,
               effect_applied_at = CASE WHEN :eff = 'applied' THEN now() ELSE NULL END
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
    if server is not None:
        await mcp.enable_listing(tx, server)
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
    if d["kind"] == "errand_action":  # the errand goes on, whatever the verdict
        await errands.on_decided(tx, d, verdict)
    if d["kind"] == "role_new" and verdict in ("rejected", "returned"):
        from hq_api.domain import role_drafts

        await role_drafts.card_decided(tx, {**d, "note": note}, verdict, who)
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
    p = amended(d["kind"], d["payload"], d["amendments"])
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
            role=p.get("role"),
            reports_to=p.get("reports_to"),
        )
        await tx.exec(
            "SELECT llm.put_assignment('role', :ref, NULL, :model, :effort, :note)",
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
        await hiring.after_hire(tx, d, emp["code"], p)
        result = {"employee": emp["code"]}
    elif d["kind"] == "lesson_adoption":
        status = "adopted" if p.get("adopt", True) else "rejected"
        await stars.adoption_decided(tx, p["lesson"], d["company_id"], status, d["ref"])
        result = {"lesson": p["lesson"], "adoption": status}
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
    elif d["kind"] == "protocol":
        # The seal is the new version; the decision id is on it, so a retried
        # effect never adds a second one.
        done = await tx.first(
            "SELECT ref, version FROM oversight.protocols WHERE decision_id = :d", d=d["id"]
        )
        if done is None:
            fields = {k: v for k, v in p.items() if k != "ref"}
            holding_id = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
            proto = await oversight.new_version(
                tx,
                actor_principal(d),
                holding_id,
                fields,
                ref=p.get("ref"),
                source="decision",
                step_up_id=d["seal_step_up_id"],
                decision_id=d["id"],
            )
            done = {"ref": proto["ref"], "version": proto["version"]}
        result = {"protocol": f"{done['ref']}@{done['version']}"}
    elif d["kind"] == "company_found":
        from hq_api.domain import founding

        result = await founding.found_company(tx, d, p)
    elif d["kind"] == "evaluation":
        from hq_api.domain import hr

        result = await hr.apply(tx, d, p)
    elif d["kind"] == "code_session":
        # The seal is the grant; the decision's id is unique on the grant, so a
        # retried effect never makes a second one.
        g = await tx.first("SELECT ref FROM workshop.grants WHERE decision_id = :d", d=d["id"])
        if g is None and d["seal_step_up_id"] is None:
            # Its seal is the grant (contract §5.1 v1.4.3): never one without the step-up.
            raise ApiError(409, "validation_failed", "a code_session is granted only when sealed")
        if g is None:
            g = await workshop.create_grant(
                tx,
                actor_principal(d),
                workshop.direct_audit(actor_principal(d)),
                workspace_code=p["workspace"],
                actions=list(p["actions"]),
                driver_code=p.get("driver"),
                budget_usd=Decimal(str(p["budget_usd"])),
                expires_at=await tx.scalar(
                    "SELECT now() + make_interval(days => :n)", n=int(p.get("days", 7))
                ),
                decision_id=d["id"],
                sealed=d["seal_step_up_id"] is not None,
            )
            await post_system_message(
                tx,
                d["thread_code"],
                f"مجوز کارگاه {g['ref']} برای {p['workspace']} صادر شد · سقف ${p['budget_usd']} برای هر سشن",
                {"decision": d["ref"], "grant": g["ref"]},
            )
        result = {"grant": g["ref"]}
    elif d["kind"] == "role_new":
        # ⟨1.6⟩ the draft the card showed becomes an active charter (§22.5)
        from hq_api.domain import role_drafts

        result = await role_drafts.apply_card(tx, d, actor_principal(d))
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
