"""⟨1.15⟩ Prompt 24 (contract §33.7, §33.10): agents in parallel and the company workspace.

POST /internal/v1/work/{id}/split   the parent's assignee (agent, A1, OPA hq.internal
                                    `work.split`): {parts: [{title_fa, role, brief}]}
GET  /work/{id}/split               owner: the parts side by side, and the merge
POST /work/{id}/stop                owner: stops the work's workspace (its turn on the
                                    company server cancelled); the work stays open
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hq_api import idempotency
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import split as SP
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow, escrow_of

router = APIRouter(tags=["work"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)


@internal_router.post("/work/{id}/split", response_model=SP.WorkSplit, status_code=201, responses=E)
async def split_work(
    id: UUID, body: SP.WorkSplitIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """⟨1.15⟩ §33.7 the parent's assignee splits its work into 2..PARALLEL_MAX (data) independent
    parts, each an ordinary child work with its own run and an equal share of the budget left (a
    share kept for the merge). Code refuses parts that depend on each other (`422`, the part named
    in `fields`); the depth limit of 2 stays (`409 delegation_depth_exceeded`). When every
    part has ended, ONE merge run of the parent's assignee is queued."""
    SP.check_parts(body.parts)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        w = await W.load(tx, id, lock=True)
        assignees: list[dict[str, Any]] = []
        for p in body.parts:  # a role held by several: each part to a different holder first
            assignees.append(await SP.resolve(tx, w, p.role, [a["code"] for a in assignees]))
        await allow(
            ctx,
            "work.split",
            {
                "assignee": w["a_code"],
                "company": w["company"],
                "max": SP.parallel_max(),
                "parts": [
                    {"to_role": a["kind"], "to_department": a["department"]} for a in assignees
                ],
            },
            escrow_classes=await escrow_of(tx, w),
        )
        await ctx.ensure_unlocked(tx, w["company_id"])
        await SP.split(tx, ctx.who, w, body.parts, assignees)
        await ctx.audit(
            tx,
            company_id=w["company_id"],
            action="work.split",
            action_class="A1",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"{len(body.parts)} parallel parts: " + ", ".join(a["code"] for a in assignees),
        )
        view = await SP.view(tx, w["id"])
        assert view is not None
        if idem:
            await idem.store(tx, 201, view.model_dump(mode="json"))
    return view


@router.get("/work/{id}/split", response_model=SP.WorkSplit, responses=E)
async def get_split(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> SP.WorkSplit:
    """⟨1.15⟩ §33.7 the work's parallel parts side by side (each part's state, output or why it
    failed) and the merge. 404 for a work that was never split."""
    async with ctx.tx() as tx:
        await W.load(tx, id)
        await SP.after_parent(tx, id)
        view = await SP.view(tx, id)
    if view is None:
        raise ApiError(404, "not_found", "this work has no parallel parts")
    return view


@router.post("/work/{id}/stop", response_model=WS.WorkStopped, responses=E)
async def stop_work(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> WS.WorkStopped:
    """⟨1.15⟩ §33.10 stop the work's workspace: its turn on the company server is cancelled (the
    runner kills its process group) and nothing more runs for the work until the owner sets another
    mode (`single` runs it on the hub) or cancels it. The work stays open."""
    async with ctx.tx() as tx:
        w = await W.load(tx, id, lock=True)
        return await WS.stop(tx, ctx.who, w)
