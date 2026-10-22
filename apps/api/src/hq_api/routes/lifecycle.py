"""Templates, lifecycle rules and NPS (prompt 10 §7, contract §19.5), under
/growth beside the funnel and rescue routes (routes/growth.py).

Owner (/api/v1):
  GET  /growth/templates · POST /growth/templates (proposed; a new version of `ref`)
  POST /growth/templates/{ref}/seal   🔏 growth.template = ref@version:sha256 of the body
  GET  /growth/rules · POST /growth/rules (proposed; no agent is needed)
  POST /growth/rules/{ref}/seal       🔏 growth.rule = ref@version -> active; its template
                                      version must be sealed and current, else 409
                                      template_not_sealed
  POST /growth/rules/{ref}/pause      no step-up · /resume 🔏 growth.rule = ref@version
  GET  /growth/nps
An agent proposes a template or a rule with `propose` (decision kinds
message_template / lifecycle_rule); the card's seal is the same seal.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import lifecycle as L
from hq_api.errors import ApiError, responses
from hq_api.schemas import CODE, Model
from hq_api.security import stepup

router = APIRouter(tags=["growth"])
E = responses(401, 403, 404, 409, 422)
TM_REF = r"^TM-[0-9]{4,6}$"
LR_REF = r"^LR-[0-9]{4,6}$"
Purpose = Literal["welcome", "reactivation", "rescue", "nps", "holding_reply", "safety", "csat"]
RuleKind = Literal["welcome", "reactivation", "rescue", "nps", "csat"]
ChannelKind = Literal["telegram_business", "telegram_bot", "chatwoot", "product_bot"]


class MessageTemplateIn(Model):
    company: str = Field(pattern=CODE)
    purpose: Purpose
    body_fa: str = Field(min_length=1, max_length=4000)
    variables: list[str] = Field(default_factory=list, max_length=20)
    ref: str | None = Field(default=None, pattern=TM_REF)


class GrowthSealIn(Model):
    version: int | None = Field(default=None, ge=1)


class LifecycleTrigger(Model):
    event: Literal["signup", "referral_failed", "conversation_closed"] | None = None
    after_hours: int | None = Field(default=None, ge=0, le=24 * 90)
    inactive_days: int | None = Field(default=None, ge=1, le=3650)
    rrule: str | None = Field(default=None, min_length=6, max_length=200)
    sample: int | None = Field(default=None, ge=1, le=10000)


class LifecycleRuleIn(Model):
    company: str = Field(pattern=CODE)
    kind: RuleKind
    template: str = Field(pattern=r"^TM-[0-9]{4,6}@[0-9]+$")
    channel: ChannelKind = "telegram_bot"
    trigger: LifecycleTrigger = Field(default_factory=LifecycleTrigger)
    limits: L.LifecycleLimits = Field(default_factory=L.LifecycleLimits)
    ref: str | None = Field(default=None, pattern=LR_REF)


async def _company(ctx: Ctx, code: str) -> Any:
    co = await ctx.hub.companies.find(code)
    if co is None:
        raise ApiError(404, "not_found", f"no company {code}")
    return co


async def _companies(ctx: Ctx, code: str | None) -> list[Any]:
    if code:
        return [await _company(ctx, code)]
    return [c for c in await ctx.hub.companies.all() if c.kind != "holding"]


@router.get("/growth/templates", response_model=list[L.MessageTemplate], responses=E)
async def list_message_templates(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[L.MessageTemplate]:
    """Every version of each company's templates (the first holding_reply,
    safety, csat and nps drafts are made on first use, proposed)."""
    out: list[L.MessageTemplate] = []
    async with ctx.tx() as tx:
        for co in await _companies(ctx, company):
            await L.ensure_seed(tx, co.id)
            rows = await tx.all(
                "SELECT * FROM growth.templates WHERE company_id = :co ORDER BY ref, version DESC",
                co=co.id,
            )
            out += [L.render_template(r, co.code) for r in rows]
    return out


@router.post("/growth/templates", response_model=L.MessageTemplate, status_code=201, responses=E)
async def propose_template(
    body: MessageTemplateIn, ctx: Ctx = Depends(owner_ctx)
) -> L.MessageTemplate:
    """The owner's template (or a new version of `ref`; a new version pauses
    every active rule on it until a rule version on the new one is sealed)."""
    co = await _company(ctx, body.company)
    async with ctx.tx() as tx:
        row = await L.propose_template(
            tx, company_id=co.id, purpose=body.purpose, body_fa=body.body_fa,
            variables=body.variables, by_kind="owner", by_code="owner", ref=body.ref,
        )  # fmt: skip
        await ctx.audit(
            tx, company_id=co.id, action="growth.template_propose", action_class="A1",
            target_kind="template", target_ref=f"{row['ref']}@{row['version']}",
        )  # fmt: skip
    return L.render_template(row, co.code)


@router.post("/growth/templates/{ref}/seal", response_model=L.MessageTemplate, responses=E)
async def seal_template(
    ref: str, body: GrowthSealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> L.MessageTemplate:
    """🔏 `growth.template`, target `ref@version:sha256` (the body's SHA-256:
    a seal for one company's template never fits another's with the same
    text, whose ref differs). The latest proposed version when none is given."""
    async with ctx.tx() as tx:
        t = await L.template(tx, ref, body.version)
        step_up_id = await stepup.consume(tx, request, ctx.who, "growth.template", L.seal_target(t))
        row = await L.seal_template(tx, ref, t["version"], step_up_id=step_up_id)
        company = await ctx.hub.companies.code_of(row["company_id"])
        await ctx.audit(
            tx, company_id=row["company_id"], action="growth.template_seal", action_class="A3",
            target_kind="template", target_ref=f"{ref}@{row['version']}", step_up=True,
        )  # fmt: skip
    return L.render_template(row, company)


@router.get("/growth/rules", response_model=list[L.LifecycleRule], responses=E)
async def list_rules(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[L.LifecycleRule]:
    """Every version of each company's rules, with the last 30 days' sends
    and opt-outs; welcome and reactivation say they have no candidates until
    the products send their events (CR-009/010)."""
    out: list[L.LifecycleRule] = []
    async with ctx.tx() as tx:
        for co in await _companies(ctx, company):
            await L.ensure_seed(tx, co.id)
            rows = await tx.all(
                L.RULE_SQL + " WHERE r.company_id = :co ORDER BY r.ref, r.version DESC", co=co.id
            )
            out += [L.render_rule(r, co.code) for r in rows]
    return out


@router.post("/growth/rules", response_model=L.LifecycleRule, status_code=201, responses=E)
async def create_rule(body: LifecycleRuleIn, ctx: Ctx = Depends(owner_ctx)) -> L.LifecycleRule:
    """The owner's own rule (or a new version of `ref`) -> proposed; it runs
    only once sealed (🔏) on a sealed template version."""
    co = await _company(ctx, body.company)
    tref, _, tver = body.template.partition("@")
    async with ctx.tx() as tx:
        row = await L.create_rule(
            tx, company_id=co.id, kind=body.kind, template_ref=tref, template_version=int(tver),
            channel=body.channel, trigger=body.trigger.model_dump(exclude_none=True),
            limits=body.limits.model_dump(), by_kind="owner", by_code="owner", ref=body.ref,
        )  # fmt: skip
        await ctx.audit(
            tx, company_id=co.id, action="growth.rule_propose", action_class="A1",
            target_kind="lifecycle_rule", target_ref=f"{row['ref']}@{row['version']}",
        )  # fmt: skip
    return L.render_rule(row, co.code)


async def _activate(
    ctx: Ctx, request: Request, ref: str, version: int | None, action: str
) -> L.LifecycleRule:
    async with ctx.tx() as tx:
        r = await L.rule(tx, ref, version)
        step_up_id = await stepup.consume(
            tx, request, ctx.who, "growth.rule", f"{ref}@{r['version']}"
        )
        row = await L.seal_rule(tx, ref, r["version"], step_up_id=step_up_id)
        company = await ctx.hub.companies.code_of(row["company_id"])
        await ctx.audit(
            tx, company_id=row["company_id"], action=action, action_class="A3",
            target_kind="lifecycle_rule", target_ref=f"{ref}@{row['version']}", step_up=True,
        )  # fmt: skip
    return L.render_rule(row, company)


@router.post("/growth/rules/{ref}/seal", response_model=L.LifecycleRule, responses=E)
async def seal_rule(
    ref: str, body: GrowthSealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> L.LifecycleRule:
    """🔏 `growth.rule`, target `ref@version` -> active (the owner's A3
    approval in advance); 409 template_not_sealed when its template version
    is not the sealed current one."""
    return await _activate(ctx, request, ref, body.version, "growth.rule_seal")


@router.post("/growth/rules/{ref}/pause", response_model=L.LifecycleRule, responses=E)
async def pause_rule(ref: str, ctx: Ctx = Depends(owner_ctx)) -> L.LifecycleRule:
    """Stops the rule at once (no step-up)."""
    async with ctx.tx() as tx:
        row = await L.pause_rule(tx, ref, "owner")
        company = await ctx.hub.companies.code_of(row["company_id"])
        await ctx.audit(
            tx, company_id=row["company_id"], action="growth.rule_pause", action_class="A1",
            target_kind="lifecycle_rule", target_ref=ref,
        )  # fmt: skip
    return L.render_rule(row, company)


@router.post("/growth/rules/{ref}/resume", response_model=L.LifecycleRule, responses=E)
async def resume_rule(
    ref: str, body: GrowthSealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> L.LifecycleRule:
    """🔏 `growth.rule`, target `ref@version`: a paused rule runs again (its
    template version still sealed and current)."""
    return await _activate(ctx, request, ref, body.version, "growth.rule_resume")


@router.get("/growth/nps", response_model=list[L.NpsWave], responses=E)
async def list_nps(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[L.NpsWave]:
    """The quarterly NPS waves (NP-<year>Q<q>-<CO>), newest first: sample,
    sent, responses, promoters/passives/detractors and the score once closed."""
    out: list[L.NpsWave] = []
    async with ctx.tx() as tx:
        for co in await _companies(ctx, company):
            rows = await tx.all(
                "SELECT * FROM growth.nps_waves WHERE company_id = :co ORDER BY opens_at DESC",
                co=co.id,
            )
            out += [L.render_wave(r, co.code) for r in rows]
    return out
