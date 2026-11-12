"""⟨1.11⟩ Prompt 21 part 3 (contract §29.13): the owner's home.

GET  /home                          three cards (effective, good, progress), the
                                    morning's 5 lines, each group's KPI per
                                    company, the latest orders, critical only
POST /home/suggestions/{id}         {action: run|later|no, reason_fa?}: run makes an
                                    order (POST /orders, the same path as the
                                    owner's own; Idempotency-Key required);
                                    no keeps the reason (never shown again)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import home as HM
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model

router = APIRouter(tags=["home"])
E = responses(401, 403, 404, 409, 422)


class ActIn(Model):
    action: Literal["run", "later", "no"]
    reason_fa: str | None = Field(default=None, max_length=1000)
    # ⟨1.17⟩ §35.1 «اجرا کن» from inside a session: the suggestion continues that order (the
    # owner's word on it, a reply), never a new F-ref
    order_ref: str | None = Field(default=None, pattern=r"^F-[0-9]{4,}$")


@router.get("/home", response_model=HM.Home, responses=E)
async def get_home(ctx: Ctx = Depends(owner_ctx)) -> HM.Home:
    """§29.13 what the owner sees first: one effective and one good
    suggestion chosen across every company (never one said «نه» to), one
    real move with its figures before and after, the morning's lines, each
    working group's KPI series, the latest orders and only the critical
    notifications. Every text is plain Persian (§29.7)."""
    return await HM.build(ctx.hub)


async def _make_order(
    ctx: Ctx, request: Request, background: BackgroundTasks, s: dict[str, Any]
) -> str:
    """«اجرا کن»: an order through POST /orders exactly as the owner's own
    (its routing, its report), with the request's Idempotency-Key."""
    from hq_api.routes import orders as OR

    body = OR.OrderIn(text=HM.order_text(s), source="text", company=s["company"])
    out = await OR.create_order(body=body, request=request, background=background, ctx=ctx)
    if isinstance(out, JSONResponse):  # a retry with the same key: the stored answer
        stored = json.loads(bytes(out.body)) if 200 <= out.status_code < 300 else None
        out = stored if isinstance(stored, dict) else None
    ref = out.get("ref") if isinstance(out, dict) else getattr(out, "ref", None)
    if not isinstance(ref, str):
        raise ApiError(409, "validation_failed", "the order was not made")
    return ref


async def _continue_order(ctx: Ctx, ref: str, s: dict[str, Any]) -> str:
    """⟨1.17⟩ §35.1 «اجرا کن» inside a session: the suggestion is the owner's next word on that
    open order (a reply); its holder runs again at once."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import order_turns as OT

    async with ctx.tx() as tx:
        text = f"اجرا کن: {HM.order_text(s)}"[:2000]
        out = await OT.reply(tx, ref, text)
        rep = await OR.ensure(tx, ref)
        if rep is not None:
            await OT.to_talk_owner(tx, rep, text)
        woken = ", ".join(out["woken"]) or "nothing"
        await ctx.audit(tx, company_id=s["company_id"], action="order.reply", action_class="A1",
                        target_kind="order", target_ref=ref,
                        summary=f"a suggestion from the session; woken: {woken}")  # fmt: skip
        await OR.refresh(tx, ref)
    return ref


@router.post("/home/suggestions/{id}", response_model=HM.Suggestion, responses=E)
async def act_on_suggestion(
    id: UUID,
    body: ActIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> HM.Suggestion:
    """`run`: an order is made from the suggestion (§29.4) and linked to it;
    `later`: hidden for three days; `no`: never shown again, its reason kept
    here and in the secretary's memory. A suggestion already run answers
    as it is (its order made once)."""
    if body.action == "run":
        idempotency.read_key(request, required=True)
    # Two acts on one suggestion at once (a double tap, the web and the phone,
    # each with its own key) wait for each other until the first has linked its
    # order: the second then sees it, and no second order is made. The lock is
    # held on its own connection; the order and the link use their own.
    async with ctx.hub.db.raw() as lock:
        await lock.exec(
            "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"hq:suggestion:{id}"
        )
        return await _act(ctx, id, body, request, background)


async def _act(
    ctx: Ctx, id: UUID, body: ActIn, request: Request, background: BackgroundTasks
) -> HM.Suggestion:
    async with ctx.tx() as tx:
        s = await tx.one(HM.SUGGESTION_SQL + " WHERE s.id = :id", id=id)
    if s["state"] == "run" and s["order_ref"]:
        return HM.render_suggestion(s)
    order_ref = None
    if body.action == "run" and body.order_ref:
        order_ref = await _continue_order(ctx, body.order_ref, s)
    elif body.action == "run":
        order_ref = await _make_order(ctx, request, background, s)
    now = datetime.now(UTC)
    reason = HM.clean(body.reason_fa, 1000) if body.reason_fa else None
    async with ctx.tx() as tx:
        s = await tx.one(HM.SUGGESTION_SQL + " WHERE s.id = :id FOR UPDATE OF s", id=id)
        if s["state"] == "run" and s["order_ref"]:
            return HM.render_suggestion(s)
        await tx.exec(
            """UPDATE owner.suggestions SET state = :st, reason_fa = COALESCE(:r, reason_fa),
                   order_ref = COALESCE(:o, order_ref), decided_at = :now, updated_at = :now,
                   later_until = CASE WHEN :st = 'later' THEN CAST(:until AS timestamptz) ELSE NULL END
               WHERE id = :id""",
            id=id,
            st=body.action,
            r=reason,
            o=order_ref,
            now=now,
            until=now + HM.LATER,
        )
        if body.action == "no":
            await HM.remember_no(tx, s, reason)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=s["company_id"],
            action="suggestion.decide",
            action_class="A2",
            target_kind="suggestion",
            target_ref=str(id),
            summary=f"{body.action}" + (f" -> order {order_ref}" if order_ref else ""),
        )
        await ctx.interaction(
            tx,
            company_id=s["company_id"],
            kind="decision",
            action="suggestion.decide",
            target_kind="suggestion",
            target_ref=str(id),
            data={"action": body.action, "order": order_ref, "source": s["source"]},
        )
        await ctx.emit(
            tx,
            s["company"],
            "suggestion.updated",
            str(id),
            {"state": body.action, "order": order_ref},
        )
        await ctx.emit(tx, holding.code, "home.updated", None, {"suggestion": str(id)})
        return HM.render_suggestion(await tx.one(HM.SUGGESTION_SQL + " WHERE s.id = :id", id=id))
