"""The holding live, seeded (contract §42.3 ⟨1.24⟩): one owner read the live views start from.

    GET /api/v1/live/summary    LiveSummary: people by their §29.14 state, sessions by badge,
                                approvals, urgent unread, servers, today's tokens, the kill
                                switches and one row per company (any number of them, from data)

`seq` is read before anything else: it is the last sequence of the stream `/stream` serves, whose
`id:` is that same JetStream sequence; a client applies the summary, then opens the stream with
`Last-Event-ID: <seq>` and receives every event after it (an event already counted here may come
once more; none is lost). Null while the event bus is down. Missing figures are null, never zero.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import live as LV
from hq_api.errors import responses

router = APIRouter(tags=["live"])
E = responses(401, 403)


@router.get("/live/summary", response_model=LV.LiveSummary, responses=E)
async def live_summary(ctx: Ctx = Depends(owner_ctx)) -> LV.LiveSummary:
    """The seed of every live view (K-2 of design/LIVE_VIEWS.md): a fixed handful of aggregate
    queries whatever the number of companies; `seq` to resume the stream right after it."""
    seq = await LV.stream_seq(ctx.hub)  # first: every event up to it is in what is counted below
    companies = await ctx.hub.companies.all()
    async with ctx.tx() as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        return await LV.summary(tx, companies, seq)
