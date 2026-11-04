"""⟨1.13⟩ Prompt 22 part 3 (contract §31.5): one campaign calendar. Owner only.

GET  /campaign-calendar?from&to&company?      every planned post, newsletter, ad campaign,
                                              campaign and manual item in one list, conflicts
                                              marked (`/calendar` is the change calendar, §20)
GET/POST/PUT/DELETE /campaigns[/{id}]         a goal over a span of days, its channels and budget
POST/PUT/DELETE /campaign-calendar/items[/{id}]   the owner's own items

Stream: `campaign.updated` (topic growth) on every change.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import campaigns as CP
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["growth"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"


@router.get(
    "/campaign-calendar",
    response_model=CP.CampaignCalendar,
    response_model_by_alias=True,
    responses=E,
)
async def get_campaign_calendar(
    start: date = Query(alias="from"),
    to: date = Query(),
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> CP.CampaignCalendar:
    """The merged calendar of up to 93 days: line runs (§30, when the engine is
    there), newsletters, ad campaigns, campaigns and manual items. `conflict_fa` names a
    conflict (two posts on one channel closer than the spacing, a holiday); nothing is
    moved or blocked."""
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        return await CP.build(
            tx, start, to, ctx.hub.settings.campaign_post_spacing_min, await owner_tz(tx), co
        )


@router.get("/campaigns", response_model=list[CP.Campaign], responses=E)
async def list_growth_campaigns(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[CP.Campaign]:
    """Campaigns, the newest start first; `company` narrows to one."""
    co = await ctx.hub.companies.by_code(company) if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT g.*, c.code FROM growth.campaigns g JOIN core.companies c ON c.id = g.company_id
               WHERE (CAST(:co AS uuid) IS NULL OR g.company_id = :co) ORDER BY g.starts DESC, g.created_at""",
            co=co.id if co else None,
        )
    return [CP.campaign_out(r["code"], dict(r)) for r in rows]


@router.post("/campaigns", response_model=CP.Campaign, status_code=201, responses=E)
async def create_growth_campaign(body: CP.CampaignIn, ctx: Ctx = Depends(owner_ctx)) -> CP.Campaign:
    """A campaign: a title, a goal in plain Persian, its days, channels (platform names) and an optional budget."""
    CP.check_span(body.starts, body.ends)
    channels = CP.valid_channels(body.channels)
    company = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        row = await tx.one(
            """INSERT INTO growth.campaigns (company_id, title_fa, goal_fa, starts, ends, channels, budget, state)
               VALUES (:co, :t, :g, :s, :e, :ch, :b, :st) RETURNING *""",
            co=company.id,
            t=body.title_fa.strip(),
            g=body.goal_fa,
            s=body.starts,
            e=body.ends,
            ch=channels,
            b=body.budget,
            st=body.state,
        )
        out = CP.campaign_out(company.code, dict(row))
        await ctx.audit(
            tx,
            company_id=company.id,
            action="campaign.create",
            action_class="A1",
            target_kind="campaign",
            target_ref=str(out.id),
        )
        await ctx.emit(
            tx,
            company.code,
            "campaign.updated",
            str(out.id),
            {"kind": "campaign", "state": out.state},
        )
    return out


async def _campaign_row(tx: Any, campaign_id: UUID) -> dict[str, Any]:
    row = await tx.first(
        "SELECT g.*, c.code FROM growth.campaigns g JOIN core.companies c ON c.id = g.company_id "
        "WHERE g.id = :id FOR UPDATE OF g",
        id=campaign_id,
    )
    if row is None:
        raise ApiError(404, "not_found")
    return dict(row)


@router.get("/campaigns/{campaign_id}", response_model=CP.Campaign, responses=E)
async def get_growth_campaign(campaign_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> CP.Campaign:
    """One campaign."""
    async with ctx.tx() as tx:
        row = await _campaign_row(tx, campaign_id)
    return CP.campaign_out(row["code"], row)


@router.put("/campaigns/{campaign_id}", response_model=CP.Campaign, responses=E)
async def update_growth_campaign(
    campaign_id: UUID, body: CP.CampaignPut, ctx: Ctx = Depends(owner_ctx)
) -> CP.Campaign:
    """Change any field of a campaign."""
    fields = body.model_dump(exclude_unset=True)
    if "channels" in fields and fields["channels"] is not None:
        fields["channels"] = CP.valid_channels(fields["channels"])
    for k in ("title_fa", "starts", "ends", "channels", "state", "goal_fa"):
        if k in fields and fields[k] is None:
            raise ApiError(422, "validation_failed", fields={k: "cannot be empty"})
    if not fields:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"})
    async with ctx.tx() as tx:
        cur = await _campaign_row(tx, campaign_id)
        CP.check_span(fields.get("starts", cur["starts"]), fields.get("ends", cur["ends"]))
        sets = ", ".join(f"{k} = :{k}" for k in fields)  # the keys are the model's fields
        row = await tx.one(
            f"UPDATE growth.campaigns SET {sets}, updated_at = now() WHERE id = :id RETURNING *",  # noqa: S608
            id=campaign_id,
            **fields,
        )
        out = CP.campaign_out(cur["code"], dict(row))
        await ctx.audit(
            tx,
            company_id=cur["company_id"],
            action="campaign.update",
            action_class="A1",
            target_kind="campaign",
            target_ref=str(campaign_id),
        )
        await ctx.emit(
            tx,
            cur["code"],
            "campaign.updated",
            str(campaign_id),
            {"kind": "campaign", "state": out.state},
        )
    return out


@router.delete("/campaigns/{campaign_id}", status_code=204, responses=E)
async def delete_growth_campaign(campaign_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """Remove a campaign from the calendar (its posts and ads are not touched)."""
    async with ctx.tx() as tx:
        cur = await _campaign_row(tx, campaign_id)
        await tx.exec("DELETE FROM growth.campaigns WHERE id = :id", id=campaign_id)
        await ctx.audit(
            tx,
            company_id=cur["company_id"],
            action="campaign.delete",
            action_class="A1",
            target_kind="campaign",
            target_ref=str(campaign_id),
        )
        await ctx.emit(
            tx,
            cur["code"],
            "campaign.updated",
            str(campaign_id),
            {"kind": "campaign", "state": "deleted"},
        )
    return Response(status_code=204)


# ---------------------------------------------------------- manual items --
@router.post(
    "/campaign-calendar/items", response_model=CP.CalendarItem, status_code=201, responses=E
)
async def create_calendar_item(body: CP.ManualIn, ctx: Ctx = Depends(owner_ctx)) -> CP.CalendarItem:
    """An item of the owner's own on the calendar (a post he will make himself, a deadline)."""
    company = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        r = await tx.one(
            """INSERT INTO growth.calendar_manual (company_id, day, at, title_fa, platform)
               VALUES (:co, :d, :at, :t, :p) RETURNING *""",
            co=company.id,
            d=body.day,
            at=body.at,
            t=body.title_fa.strip(),
            p=body.platform,
        )
        await ctx.emit(
            tx,
            company.code,
            "campaign.updated",
            str(r["id"]),
            {"kind": "manual", "state": r["state"]},
        )
    return _manual_out(company.code, dict(r))


def _manual_out(code: str, r: dict[str, Any]) -> CP.CalendarItem:
    return CP.CalendarItem(
        day=r["day"],
        at=r["at"],
        company=code,
        kind="manual",
        ref=str(r["id"]),
        title_fa=r["title_fa"],
        platform=r["platform"],
        state=r["state"],
    )


@router.put("/campaign-calendar/items/{item_id}", response_model=CP.CalendarItem, responses=E)
async def update_calendar_item(
    item_id: UUID, body: CP.ManualPut, ctx: Ctx = Depends(owner_ctx)
) -> CP.CalendarItem:
    """Move, rename or mark an item done or cancelled."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"})
    for k in ("day", "title_fa", "state"):
        if k in fields and fields[k] is None:
            raise ApiError(422, "validation_failed", fields={k: "cannot be empty"})
    async with ctx.tx() as tx:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        row = await tx.first(
            f"UPDATE growth.calendar_manual SET {sets}, updated_at = now() WHERE id = :id RETURNING *",  # noqa: S608
            id=item_id,
            **fields,
        )
        if row is None:
            raise ApiError(404, "not_found")
        code = await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=row["company_id"])
        await ctx.emit(
            tx, code, "campaign.updated", str(item_id), {"kind": "manual", "state": row["state"]}
        )
    return _manual_out(code, dict(row))


@router.delete("/campaign-calendar/items/{item_id}", status_code=204, responses=E)
async def delete_calendar_item(item_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """Remove one of the owner's own items."""
    async with ctx.tx() as tx:
        row = await tx.first(
            "DELETE FROM growth.calendar_manual WHERE id = :id RETURNING company_id", id=item_id
        )
        if row is None:
            raise ApiError(404, "not_found")
        code = await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=row["company_id"])
        await ctx.emit(
            tx, code, "campaign.updated", str(item_id), {"kind": "manual", "state": "deleted"}
        )
    return Response(status_code=204)
