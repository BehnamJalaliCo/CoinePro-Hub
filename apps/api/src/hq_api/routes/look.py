"""⟨1.33⟩ Contract §55: what the 1.0.1 look reads that no page read before.

    GET /publish-desk        owner   everything ready to go out, set to go out, and gone out
    GET /treasury/limits     owner   the Claude accounts (each its window) and today's meter

Both only read. The live work line and the session's mood (§55.1) ride on
`GET /orders/{ref}/activity`; one row per publication (§55.4) on the report and the panel.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import limits as LM
from hq_api.domain import publish_desk as PD
from hq_api.errors import responses

router = APIRouter(tags=["look"])
E = responses(401, 403, 404, 422)


@router.get("/publish-desk", response_model=PD.PublishDesk, responses=E)
async def publish_desk(
    company: str | None = Query(default=None, max_length=10), ctx: Ctx = Depends(owner_ctx)
) -> PD.PublishDesk:
    """§55.2 The publish desk: `ready` (an output of the last 14 days that carries a video or a
    picture and has no publication that stands), `queue` (held for its time, or on its way;
    soonest first) and `done` (the last 7 days, newest first). The card's tap is the output's
    own `POST /deliverables/{ref}/publish`; its cancel `POST /publishes/{job}/cancel`."""
    co = (await ctx.hub.companies.by_code(company)).id if company else None
    async with ctx.tx() as tx:
        return await PD.desk(tx, ctx.hub, co)


@router.get("/treasury/limits", response_model=LM.Limits, responses=E)
async def treasury_limits(ctx: Ctx = Depends(owner_ctx)) -> LM.Limits:
    """§55.3 The owner's Claude accounts, each with how full its window is and when it resets
    (`working`: the one the hub is on now), `waiting` (every account is full), and today's meter:
    what the agents spent today against their daily cap (marks at 70%, 90% and 100%)."""
    async with ctx.tx() as tx:
        return await LM.read(tx, ctx.hub)
