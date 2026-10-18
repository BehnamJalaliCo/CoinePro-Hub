"""Formal inquiries (prompt 08 §3, contract §18.2).

Owner: GET /inquiries (every inquiry). Agents (behind the Tool Gateway):
POST /internal/v1/inquiries (`inquiry.ask`: the overseer and the advisor ask
anyone, a CEO inside its own company) and POST /internal/v1/inquiries/{ref}/answer
(`inquiry.answer`: only the asked one). The asked employee is looked up only
after the policy allowed the question, under the asker's read scope, so a
refusal never tells whether a code exists in a company it cannot see.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import inquiries as Q
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import EMPLOYEE_CODE, Page

router = APIRouter(tags=["inquiries"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)


# ------------------------------------------------------------------- owner --
@router.get("/inquiries", response_model=Page[Q.Inquiry], responses=E)
async def list_inquiries(
    from_: str | None = Query(default=None, alias="from", pattern=EMPLOYEE_CODE),
    to: str | None = Query(default=None, pattern=EMPLOYEE_CODE),
    status: Literal["open", "answered", "late", "withdrawn"] | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Q.Inquiry]:
    """Newest first. The owner sees every inquiry."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            Q.SQL
            + """ WHERE (CAST(:f AS text) IS NULL OR q.from_code = :f)
                  AND (CAST(:t AS text) IS NULL OR q.to_code = :t)
                  AND (CAST(:st AS text) IS NULL OR q.status = :st)
                ORDER BY q.created_at DESC LIMIT :n""",
            f=from_,
            t=to,
            st=status,
            n=limit,
        )
    return Page(items=[Q.render(r) for r in rows])


# ------------------------------------------------------------------ agents --
@internal_router.post("/inquiries", response_model=Q.Inquiry, status_code=201, responses=E)
async def ask_inquiry(body: Q.InquiryIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """A formal question with a due time. Requires `Idempotency-Key`."""
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    holding_reader = ctx.who.scope == "holding"
    scope = await ctx.hub.companies.ids() if holding_reader else [ctx.who.company_id]
    async with ctx.hub.db.tx(scope) as rtx:
        await rtx.exec("SET TRANSACTION READ ONLY")
        target = await rtx.first(
            """SELECT e.id, e.code, e.kind, e.status, e.company_id, c.code AS company
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
            c=body.to,
        )
    await allow(
        ctx, "inquiry.ask", {"company": target["company"] if target else None, "to": body.to}
    )
    if target is None:  # a missing and a forbidden code answer the same
        raise ApiError(403, "policy_denied", "inquiry.ask_not_permitted")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        await tx.rescope(list(dict.fromkeys([ctx.who.company_id, target["company_id"]])))
        await ctx.ensure_unlocked(tx, target["company_id"])
        thread = await Q.asker_thread(tx, ctx.who)
        q = await Q.ask(tx, ctx.who, target, body, thread)
        await ctx.audit(
            tx,
            company_id=target["company_id"],
            action="inquiry.ask",
            action_class="A1",
            target_kind="inquiry",
            target_ref=q["ref"],
            summary=f"{ctx.who.code} -> {target['code']}, due in {body.due_in_hours} h",
        )
        result = Q.render(q)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json", by_alias=True))
    return result


@internal_router.post("/inquiries/{ref}/answer", response_model=Q.Inquiry, responses=E)
async def answer_inquiry(
    ref: str, body: Q.AnswerIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """The asked one's answer, delivered to the asker's thread with
    `links.inquiry`. Requires `Idempotency-Key`."""
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        q = await tx.first(Q.SQL + " WHERE q.ref = :r FOR UPDATE OF q", r=ref)
        await allow(
            ctx,
            "inquiry.answer",
            {"to": q["to_code"] if q else None, "company": q["company"] if q else None},
        )
        if q is None:
            raise ApiError(403, "policy_denied", "inquiry.answer_not_permitted")
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        # The asker's thread lives in the asker's company (its own thread with the owner).
        await tx.rescope(
            [c for c in dict.fromkeys([ctx.who.company_id, q["from_company_id"]]) if c]
        )
        out = await Q.answer(tx, ctx.who, q, body)
        await ctx.audit(
            tx,
            company_id=q["company_id"],
            action="inquiry.answer",
            action_class="A1",
            target_kind="inquiry",
            target_ref=ref,
            summary=f"to {q['from_code']} in {q['thread_code']}"
            + (" (late)" if q["status"] == "late" else ""),
        )
        result = Q.render(out)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json", by_alias=True))
    return result
