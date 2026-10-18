"""The personal assistant's errands (prompt 08 §5, contract §18.3).

Owner: GET/POST /errands, GET /errands/{ref}, POST /errands/{ref}/cancel. A
new errand is posted in thread P as the owner's message (with
`links.errand`), which wakes the assistant. Agents (the assistant, behind the
Tool Gateway): `errand.step`, `errand.finish` and `planner.add`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import errands as R
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.routes.messages import post_message
from hq_api.schemas import Page

router = APIRouter(tags=["errands"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)


class PlannerItemOut(BaseModel):
    ref: str
    title_fa: str
    at: datetime
    note: str | None


# ------------------------------------------------------------------- owner --
@router.get("/errands", response_model=Page[R.Errand], responses=E)
async def list_errands(
    status: Literal["queued", "working", "waiting_owner", "done", "failed", "cancelled"]
    | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[R.Errand]:
    """Newest first."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            R.SQL
            + " WHERE (CAST(:st AS text) IS NULL OR e.status = :st) ORDER BY e.created_at DESC LIMIT :n",
            st=status,
            n=limit,
        )
        return Page(items=[await R.render(tx, r) for r in rows])


@router.post("/errands", response_model=R.Errand, status_code=201, responses=E)
async def create_errand(body: R.ErrandIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """An errand for the assistant: posted in thread P as the owner's message
    (its brief and files), which wakes the assistant. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        e = await R.open_errand(
            tx,
            holding.id,
            brief=body.brief_md,
            source=body.source,
            file_ids=body.file_ids,
            due_at=body.due_at,
            title=body.title_fa,
        )
        m = await post_message(
            ctx,
            tx,
            R.THREAD,
            body.brief_md,
            {"errand": e["ref"]},
            list(body.file_ids),
            checked=("errand",),
        )
        await R.opened_by(tx, e["ref"], m["ref"])
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="errand.create",
            action_class="A1",
            target_kind="errand",
            target_ref=e["ref"],
            summary=f"{body.source}, {len(body.file_ids)} file(s)",
        )
        result = await R.render(tx, await R.load(tx, e["ref"]))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.get("/errands/{ref}", response_model=R.Errand, responses=E)
async def get_errand(ref: str, ctx: Ctx = Depends(owner_ctx)) -> R.Errand:
    """One errand with its steps, result, files, decision and usage."""
    async with ctx.tx() as tx:
        return await R.render(tx, await R.load(tx, ref))


@router.post("/errands/{ref}/cancel", response_model=R.Errand, responses=E)
async def cancel_errand(ref: str, ctx: Ctx = Depends(owner_ctx)) -> R.Errand:
    """The owner stops an open errand (no step-up: stopping is always safe)."""
    async with ctx.tx() as tx:
        e = await R.cancel(tx, ref)
        await ctx.audit(
            tx,
            company_id=e["company_id"],
            action="errand.cancel",
            action_class="A1",
            target_kind="errand",
            target_ref=ref,
            summary="cancelled by the owner",
        )
        return await R.render(tx, e)


# ------------------------------------------------------------------ agents --
async def _assistant(ctx: Ctx, op: str) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, op, {"company": ctx.who.company})


@internal_router.post("/errands/{ref}/steps", response_model=R.Errand, responses=E)
async def errand_step(
    ref: str, body: R.StepIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """One step of the errand's trail (search, read, browse, request, draft,
    note, proposal). Requires `Idempotency-Key`."""
    await _assistant(ctx, "errand.write")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        e = await R.step(tx, ctx.who, ref, body)
        await ctx.audit(
            tx,
            company_id=e["company_id"],
            action="errand.step",
            action_class="A2",
            target_kind="errand",
            target_ref=ref,
            summary=body.kind,
        )
        result = await R.render(tx, e)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post("/errands/{ref}/finish", response_model=R.Errand, responses=E)
async def errand_finish(
    ref: str, body: R.FinishIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """The result: the errand is done and the result is posted in thread P.
    Requires `Idempotency-Key`."""
    await _assistant(ctx, "errand.write")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        e, message = await R.finish(tx, ctx.who, ref, body)
        await ctx.audit(
            tx,
            company_id=e["company_id"],
            action="errand.finish",
            action_class="A2",
            target_kind="errand",
            target_ref=ref,
            summary=f"result in {message}, {len(body.file_ids)} file(s)",
        )
        result = await R.render(tx, e)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post("/planner", response_model=PlannerItemOut, status_code=201, responses=E)
async def planner_add(body: R.PlannerIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """A dated item in the owner's planner (GET /planner). Requires `Idempotency-Key`."""
    await _assistant(ctx, "planner.add")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        await ctx.ensure_unlocked(tx, ctx.who.company_id)
        holding = await ctx.hub.companies.holding()
        row = await R.add_planner_item(tx, ctx.who, holding.id, body)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="planner.add",
            action_class="A2",
            target_kind="planner",
            target_ref=row["ref"],
            summary=str(body.at)[:40],
        )
        result = PlannerItemOut(
            ref=row["ref"], title_fa=row["title_fa"], at=row["at"], note=row["note"]
        )
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result
