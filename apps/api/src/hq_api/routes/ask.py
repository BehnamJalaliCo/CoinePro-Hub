"""«از هاب بپرس» (prompt 12 §2, contract §21.2).

Owner (/api/v1, owner only):
    POST /ask           {q (<= 500), scope?: {companies?, kinds?}} -> 202 Ask; Idempotency-Key
    GET  /ask/{ref}     one ask
    GET  /ask           ?cursor (history, newest first)
Agents (/internal/v1):
    POST /ask/answer    ask.answer (A1, the Hub Librarian only)
Stream: ask.answered on topic `ask`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import ask as AK
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Page

router = APIRouter(tags=["ask"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428)


@router.post("/ask", response_model=AK.Ask, status_code=202, responses=E)
async def ask(
    body: AK.AskIn, request: Request, response: Response, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """One question, one short answer with exact citations. The search is
    code; nothing found answers at once with no model call (`found: 0`).
    Otherwise the Hub Librarian answers from the passages found (`answering`,
    then `ask.answered`). 423 while the holding's kill switch is engaged and a
    model would be needed. Requires `Idempotency-Key`."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row, _ = await AK.create(tx, ctx.hub, ctx.who, body)
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="message",
            action="ask.create",
            target_kind="ask",
            target_ref=row["ref"],
            data={"found": row["found"], "scope": body.scope is not None},
        )
        out = AK.render(row)
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    response.headers["Location"] = f"/api/v1/ask/{row['ref']}"
    return out


@router.get("/ask", response_model=Page[AK.Ask], responses=E)
async def list_asks(
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[AK.Ask]:
    """The owner's asks, newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            AK.ASK_SQL
            + """ WHERE (CAST(:t AS timestamptz) IS NULL
                         OR (a.created_at, a.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
                  ORDER BY a.created_at DESC, a.id DESC LIMIT :lim""",
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[AK.render(r) for r in items], next_cursor=nxt)


@router.get("/ask/{ref}", response_model=AK.Ask, responses=E)
async def get_ask(ref: str, ctx: Ctx = Depends(owner_ctx)) -> AK.Ask:
    async with ctx.tx() as tx:
        row = await tx.first(AK.ASK_SQL + " WHERE a.ref = :r", r=ref)
    if row is None:
        raise ApiError(404, "not_found", "no such ask")
    return AK.render(row)


@internal_router.post("/ask/answer", response_model=AK.Ask, responses=E)
async def ask_answer(body: AK.AnswerIn, ctx: Ctx = Depends(internal_ctx)) -> AK.Ask:
    """ask.answer (A1): the librarian's answer, only from the passages the
    search returned; a citation outside them is dropped and counted; an
    answer with no valid citation is `failed`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "ask.answer", {"ask": body.ask, "charter": ctx.who.charter})
    holding = await ctx.hub.companies.holding()
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await ctx.ensure_unlocked(tx, holding.id)
        row = await AK.answer(tx, ctx.hub, ctx.who, body)
    return AK.render(row)
