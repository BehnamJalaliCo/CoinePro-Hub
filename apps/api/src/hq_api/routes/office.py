"""The owner's office (contract §35.5): GET /office, his workspace in one read — the open sessions
(his turn first), the cards only he decides, the month's money, the critical notices, the
suggestions and the canvas of companies and their links. `GET /home` stays for older apps."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import office as OF
from hq_api.errors import responses

router = APIRouter(tags=["office"])
E = responses(401, 403)


@router.get("/office", response_model=OF.Office, responses=E)
async def get_office(ctx: Ctx = Depends(owner_ctx)) -> OF.Office:
    """The office: sessions (≤ 30, as GET /sessions), approvals (owner-visible, ≤ 10, and their
    total), money (dollars, one plain line), critical (owner-visible only), suggestions (any
    subject), canvas (as GET /links). Code only, no model."""
    async with ctx.tx() as tx:
        return await OF.build(tx)
