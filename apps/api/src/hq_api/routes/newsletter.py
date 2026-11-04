"""⟨1.13⟩ Prompt 22 part 3 (contract §31.3): the company's newsletter (Listmonk).

GET  /companies/{code}/newsletter             lists with counts, the last campaigns
POST /companies/{code}/newsletter/campaigns   {subject, body, content_type?, list_id?}: a draft
POST /newsletter/campaigns/{id}/schedule      {at}: 🔏 newsletter.send (target = the campaign id)
                                              when the list is over the size limit
GET  /newsletter/campaigns/{id}               the campaign with Listmonk's live figures

Owner only. Subscribers, their consent and the unsubscribe link stay in Listmonk.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import newsletter as NL
from hq_api.errors import ApiError, responses
from hq_api.security import stepup

router = APIRouter(tags=["growth"])
E = responses(401, 403, 404, 409, 422, 423, 503)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"


@router.get("/companies/{code}/newsletter", response_model=NL.NewsletterOut, responses=E)
async def get_company_newsletter(
    code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> NL.NewsletterOut:
    """The company's lists (with subscriber counts when Listmonk answers), its
    size limit and its last campaigns. Off or unreachable: the stored rows and a
    Persian note, never an error."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await NL.overview(ctx.hub, tx, company)


@router.post(
    "/companies/{code}/newsletter/campaigns",
    response_model=NL.CampaignOut,
    status_code=201,
    responses=E,
)
async def create_newsletter_campaign(
    body: NL.NewsletterCampaignIn, code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> NL.CampaignOut:
    """A campaign as a draft in Listmonk for the company's list (made on first
    use). Nothing is sent: a send is scheduled with `schedule`."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        out = await NL.create_campaign(ctx.hub, tx, company, body)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="newsletter.campaign",
            action_class="A2",
            target_kind="newsletter_campaign",
            target_ref=str(out.id),
            summary="draft made",
        )
        await NL.announce(tx, code, out)
    return out


@router.post(
    "/newsletter/campaigns/{campaign_id}/schedule", response_model=NL.CampaignOut, responses=E
)
async def schedule_newsletter_campaign(
    campaign_id: UUID,
    body: NL.NewsletterScheduleIn,
    request: Request,
    ctx: Ctx = Depends(owner_ctx),
) -> NL.CampaignOut:
    """The send time (in the future). 🔏 `newsletter.send` (target = the campaign
    id) when the list has more subscribers than the size limit; a small list
    needs no seal. Listmonk then sends it by itself at that time."""
    at = NL.future_or_raise(body.at)
    async with ctx.tx() as tx:
        row = await NL.get_row(tx, campaign_id, lock=True)
        lm = await NL.client_for(ctx.hub)
        size = await NL.list_size(lm, row["list_id"])
        sealed = NL.needs_seal(size, ctx.hub.settings.newsletter_size_limit)
        if sealed:
            await stepup.consume(tx, request, ctx.who, "newsletter.send", str(campaign_id))
        if row["state"] not in ("draft", "scheduled"):
            raise ApiError(409, "version_conflict", "campaign is already sending or finished")
        await NL.schedule(lm, row, at)
        await tx.exec(
            "UPDATE growth.newsletter_campaigns SET state = 'scheduled', send_at = :at, "
            "list_size = :n, updated_at = now() WHERE id = :id",
            id=campaign_id,
            at=at,
            n=size,
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="newsletter.send",
            action_class="A3" if sealed else "A2",
            target_kind="newsletter_campaign",
            target_ref=str(campaign_id),
            summary=f"scheduled to {size} subscribers",
            step_up=sealed,
        )
        out = await NL.detail(ctx.hub, tx, campaign_id)
        await NL.announce(tx, row["company"], out)
    return out


@router.get("/newsletter/campaigns/{campaign_id}", response_model=NL.CampaignOut, responses=E)
async def get_newsletter_campaign(
    campaign_id: UUID, ctx: Ctx = Depends(owner_ctx)
) -> NL.CampaignOut:
    """The campaign with Listmonk's sent, open, click and bounce counts."""
    async with ctx.tx() as tx:
        return await NL.detail(ctx.hub, tx, campaign_id)
