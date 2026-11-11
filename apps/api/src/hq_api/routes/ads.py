"""⟨1.13⟩ Prompt 22 part 3 (contract §31.6): ad budgets that stop by themselves.

GET    /companies/{code}/ads                  accounts (the two connection kinds), campaigns
                                              with their last 30 days, the last trips
GET    /companies/{code}/ad-rules             the company's rules
POST   /companies/{code}/ad-rules             a new rule (tightening only: no step-up)
PUT    /companies/{code}/ad-rules/{id}        🔏 ads.cap (target = the rule id) when it lets
                                              more money through
DELETE /companies/{code}/ad-rules/{id}        🔏 ads.cap (a guard taken away)
POST   /ads/campaigns/{platform}/{id}/resume  🔏 ads.resume (target <platform>:<id>)

Owner only. A campaign is only ever paused by a rule (code, in the worker) and
resumed by the owner here; no route or job raises a budget."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import ads as AD
from hq_api.domain import connections as CN
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model
from hq_api.security import stepup

router = APIRouter(tags=["ads"])
E = responses(401, 403, 404, 409, 422)
PLATFORM = "^(google_ads|meta_ads)$"
RULE_COLUMNS = (
    "scope",
    "daily_cap",
    "window_days",
    "min_roas",
    "min_spend_before_judging",
    "action",
    "state",
    "note_fa",
)


class Resumed(Model):
    platform: AD.Platform
    campaign_id: str
    company: str
    status: str


@router.get("/companies/{code}/ads", response_model=AD.Ads, responses=E)
async def get_company_ads(code: str, ctx: Ctx = Depends(owner_ctx)) -> AD.Ads:
    """⟨1.13⟩ §31.6 the company's ad accounts (Google Ads, Meta Ads: their
    connection state and what is missing), every campaign with its last 30 days
    (spend, clicks, conversions, revenue, ROAS) and the rules' last trips. Read
    by code each day through egress; empty until the connection is complete."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await AD.overview(tx, company)


@router.get("/companies/{code}/ad-rules", response_model=list[AD.AdRule], responses=E)
async def list_ad_rules(code: str, ctx: Ctx = Depends(owner_ctx)) -> list[AD.AdRule]:
    """⟨1.13⟩ §31.6 the company's budget rules, oldest first, each with a plain
    Persian summary of what it does."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        rows = await tx.all(
            "SELECT * FROM growth.ad_rules WHERE company_id = :co ORDER BY created_at, id",
            co=company.id,
        )
    return [AD.render_rule(r, company.code) for r in rows]


@router.post("/companies/{code}/ad-rules", response_model=AD.AdRule, status_code=201, responses=E)
async def add_ad_rule(
    code: str, body: AD.AdRuleIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.13⟩ §31.6 a new budget rule: a daily cap on a campaign's spend and/or a
    ROAS floor over a window once a minimum was spent; the action pauses the
    campaign (reversible) or only tells. A new rule only adds a guard, so it
    needs no step-up. Requires `Idempotency-Key`."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await tx.one(
            """INSERT INTO growth.ad_rules (company_id, platform, scope, daily_cap, window_days,
                   min_roas, min_spend_before_judging, action, state, note_fa)
               VALUES (:co, :p, :scope, :cap, :win, :roas, :min, :a, :st, :note) RETURNING *""",
            co=company.id,
            p=body.platform,
            scope=body.scope,
            cap=body.daily_cap,
            win=body.window_days,
            roas=body.min_roas,
            min=body.min_spend_before_judging,
            a=body.action,
            st=body.state,
            note=body.note_fa,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="ads.rule",
            action_class="A2",
            target_kind="ad_rule",
            target_ref=str(row["id"]),
            summary=f"added ({body.platform})",
        )
        result = AD.render_rule(row, company.code)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.put("/companies/{code}/ad-rules/{rule_id}", response_model=AD.AdRule, responses=E)
async def edit_ad_rule(
    code: str,
    rule_id: UUID,
    body: AD.AdRuleEdit,
    request: Request,
    ctx: Ctx = Depends(owner_ctx),
) -> AD.AdRule:
    """⟨1.13⟩ §31.6 change a rule. 🔏 `ads.cap` (target = the rule id) when the
    new rule lets more money through (a higher cap, a lower ROAS floor, a larger
    minimum before judging, a longer window, only telling instead of pausing,
    switched off, fewer or other campaigns); a tighter rule needs none. A null
    for a field that cannot be empty is 422."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        old = await tx.one(
            "SELECT * FROM growth.ad_rules WHERE id = :id AND company_id = :co FOR UPDATE",
            id=rule_id,
            co=company.id,
        )
        fields = body.model_dump(exclude_unset=True)
        for k in ("scope", "window_days", "min_spend_before_judging", "action", "state"):
            if k in fields and fields[k] is None:
                raise ApiError(422, "validation_failed", fields={k: "cannot be empty"})
        new = {**old, **fields}
        if new["daily_cap"] is None and new["min_roas"] is None:
            raise ApiError(422, "validation_failed", fields={"daily_cap": "a cap or a floor"})
        wider = AD.loosens(old, new)
        if wider:
            await stepup.consume(tx, request, ctx.who, "ads.cap", str(rule_id))
        row = await tx.one(
            """UPDATE growth.ad_rules SET scope = :scope, daily_cap = :cap, window_days = :win,
                   min_roas = :roas, min_spend_before_judging = :min, action = :a, state = :st,
                   note_fa = :note, updated_at = now() WHERE id = :id RETURNING *""",
            id=rule_id,
            scope=new["scope"],
            cap=new["daily_cap"],
            win=new["window_days"],
            roas=new["min_roas"],
            min=new["min_spend_before_judging"],
            a=new["action"],
            st=new["state"],
            note=new["note_fa"],
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="ads.cap" if wider else "ads.rule",
            action_class="A2",
            target_kind="ad_rule",
            target_ref=str(rule_id),
            summary="loosened" if wider else "tightened",
            step_up=wider,
        )
        return AD.render_rule(row, company.code)


@router.delete("/companies/{code}/ad-rules/{rule_id}", status_code=204, responses=E)
async def delete_ad_rule(
    code: str, rule_id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Response:
    """⟨1.13⟩ §31.6 take a rule away: 🔏 `ads.cap` (target = the rule id), since
    a guard is gone."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        await tx.one(
            "SELECT id FROM growth.ad_rules WHERE id = :id AND company_id = :co FOR UPDATE",
            id=rule_id,
            co=company.id,
        )
        await stepup.consume(tx, request, ctx.who, "ads.cap", str(rule_id))
        await tx.exec("DELETE FROM growth.ad_rules WHERE id = :id", id=rule_id)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="ads.cap",
            action_class="A2",
            target_kind="ad_rule",
            target_ref=str(rule_id),
            summary="deleted",
            step_up=True,
        )
    return Response(status_code=204)


@router.post("/ads/campaigns/{platform}/{campaign_id}/resume", response_model=Resumed, responses=E)
async def resume_campaign(
    request: Request,
    platform: str = Path(pattern=PLATFORM),
    campaign_id: str = Path(pattern=r"^[0-9]{1,30}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> Resumed:
    """⟨1.13⟩ §31.6 a paused campaign on again, 🔏 `ads.resume` (target
    `<platform>:<campaign id>`). The platform's API is called first; if it does
    not answer, nothing changes and the step-up is not spent. The campaign is
    not judged again for a day."""
    async with ctx.tx() as tx:
        camp = await tx.one(
            """SELECT k.*, c.code AS company_code FROM growth.ad_campaigns k
               JOIN core.companies c ON c.id = k.company_id
               WHERE k.platform = :p AND k.campaign_id = :c ORDER BY k.created_at LIMIT 1
               FOR UPDATE OF k""",
            p=platform,
            c=campaign_id,
        )
        await stepup.consume(tx, request, ctx.who, "ads.resume", f"{platform}:{campaign_id}")
        if camp["status"] == "removed":
            raise ApiError(409, "validation_failed", "the campaign was removed at the platform")
        today = CN.owner_today(await owner_tz(tx))
        try:
            await AD.resume(
                ctx.hub, camp["company_id"], camp["company_code"], platform, campaign_id, today
            )
        except CN.ReadError as exc:
            raise ApiError(502, "channel_not_configured", message_fa=exc.reason_fa) from exc
        await tx.exec(
            """UPDATE growth.ad_campaigns SET status = 'active', paused_by = NULL,
                   paused_rule_id = NULL, paused_at = NULL, paused_reason_fa = NULL,
                   resumed_at = now(), updated_at = now() WHERE id = :id""",
            id=camp["id"],
        )
        await ctx.audit(
            tx,
            company_id=camp["company_id"],
            action="ads.resume",
            action_class="A2",
            target_kind="ad_campaign",
            target_ref=f"{platform}:{campaign_id}",
            summary="resumed",
            step_up=True,
        )
        await ctx.emit(
            tx,
            camp["company_code"],
            "ad.resumed",
            campaign_id,
            {"platform": platform, "campaign": campaign_id},
        )
        return Resumed(
            platform=platform,
            campaign_id=campaign_id,
            company=camp["company_code"],
            status="active",
        )
