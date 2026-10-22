"""The premium advisor (prompt 12 §1, contract §21.1).

Owner (/api/v1):
    POST /decisions/{ref}/memo     {mode} -> 202 DecisionMemo; idempotent per card,
                                   mode and card version; a decided card -> 409
    GET  /decisions/{ref}/memo     ?mode (default standard) -> the latest memo, or 404
    GET  /advisor/memos            ?decision&cursor (newest first)
    GET  /advisor/triggers         ?since&kind (newest first)
Agents (/internal/v1):
    POST /advisor/memos            memo.write (A1, the advisor only, pending cards only)
Stream: memo.ready and advisor.proactive on topic `advisor`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from hq_api import pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import advisor as A
from hq_api.domain import decisions as D
from hq_api.errors import ApiError, responses
from hq_api.routes.agent_tools import read_tx
from hq_api.routes.internal import allow
from hq_api.schemas import Page

router = APIRouter(tags=["advisor"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
DREF = r"^D-[0-9]{4,9}$"


@router.post("/decisions/{ref}/memo", response_model=A.DecisionMemo, status_code=202, responses=E)
async def request_memo(
    ref: str, body: A.MemoIn, response: Response, ctx: Ctx = Depends(owner_ctx)
) -> A.DecisionMemo:
    """The advisor's memo on a pending card (standard, or `devil`: why not).
    The same card, mode and version again answers the same memo. 423 while
    the holding's kill switch is engaged (no model runs before launch)."""
    async with ctx.tx() as tx:
        d = await D.load(tx, ref, lock=True)
        memo, created = await A.request(tx, ctx.hub, ctx.who, d, body.mode, "owner")
        if created:
            await ctx.interaction(
                tx,
                company_id=memo["company_id"],
                kind="decision",
                action="memo.request",
                target_kind="memo",
                target_ref=memo["ref"],
                data={"decision": ref, "mode": body.mode},
            )
    response.headers["Location"] = f"/api/v1/decisions/{ref}/memo?mode={body.mode}"
    return A.render(memo)


@router.get("/decisions/{ref}/memo", response_model=A.DecisionMemo, responses=E)
async def get_memo(
    ref: str,
    mode: Literal["standard", "devil"] = "standard",
    ctx: Ctx = Depends(owner_ctx),
) -> A.DecisionMemo:
    """The card's latest memo in this mode (any version), or 404."""
    async with ctx.tx() as tx:
        row = await tx.first(
            A.MEMO_SQL
            + """ WHERE m.decision_ref = :r AND m.mode = :m
                  ORDER BY m.decision_version DESC, m.created_at DESC LIMIT 1""",
            r=ref,
            m=mode,
        )
    if row is None:
        raise ApiError(404, "not_found", "no memo for this card yet")
    return A.render(row)


@router.get("/advisor/memos", response_model=Page[A.DecisionMemo], responses=E)
async def list_memos(
    decision: str | None = Query(default=None, pattern=DREF),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[A.DecisionMemo]:
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            A.MEMO_SQL
            + """ WHERE (CAST(:d AS text) IS NULL OR m.decision_ref = :d)
                    AND (CAST(:t AS timestamptz) IS NULL
                         OR (m.created_at, m.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
                  ORDER BY m.created_at DESC, m.id DESC LIMIT :lim""",
            d=decision,
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[A.render(r) for r in items], next_cursor=nxt)


@router.get("/advisor/triggers", response_model=list[A.AdvisorTrigger], responses=E)
async def list_triggers(
    since: datetime | None = None,
    kind: Literal[
        "budget",
        "quota",
        "compliance",
        "incident",
        "revenue",
        "waiting_decisions",
        "finding",
        "okr",
    ]
    | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[A.AdvisorTrigger]:
    """The rule triggers (newest first, at most 200): `sent` woke the advisor,
    `deferred` waited (the holding locked or the owner zone spent), `capped`
    went over the day's proactive_per_day."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT t.*, c.code AS company FROM advisor.triggers t
               LEFT JOIN core.companies c ON c.id = t.subject_company_id
               WHERE (CAST(:s AS timestamptz) IS NULL OR t.fired_at >= :s)
                 AND (CAST(:k AS text) IS NULL OR t.kind = :k)
               ORDER BY t.fired_at DESC LIMIT 200""",
            s=since,
            k=kind,
        )
    return [A.render_trigger(r) for r in rows]


# ------------------------------------------------------------- memo.write --
@internal_router.post("/advisor/memos", response_model=A.DecisionMemo, responses=E)
async def memo_write(body: A.MemoWrite, ctx: Ctx = Depends(internal_ctx)) -> A.DecisionMemo:
    """memo.write (A1): the advisor's memo on a pending card. A decided card
    is 409 decision_not_pending; another version of the card 409
    version_conflict; an empty `against_md` 422; an invented citation is
    dropped and counted (`citations_dropped`)."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "memo.write", {"decision": body.decision, "charter": ctx.who.charter})
    holding = await ctx.hub.companies.holding()
    # The advisor reads every company (holding scope, OPA above): the card may
    # be any company's; the memo is the holding's. Citations: its read scope.
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await ctx.ensure_unlocked(tx, holding.id)
        async with read_tx(ctx) as rtx:
            row = await A.write(tx, rtx, ctx.who, body, ctx.hub)
    return A.render(row)


def memo_ids(rows: list[dict[str, Any]]) -> list[UUID]:
    return [r["id"] for r in rows]
