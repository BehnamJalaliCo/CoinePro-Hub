"""⟨1.39⟩ Contract §61.3 (prompt 39, P1): the automations as data (domain/flow_defs.py).

Owner only, each a tap (no step-up, but a cap raised past the company's USD month envelope: 🔏
automation.budget on `<ref>:<usd_cap>`), `Idempotency-Key` on POST, audited
`automation.flow.<verb>` with before and after, stream event `automation.changed {ref, state,
version}`. `{ref}` is `AF-…`, or the `N8:<key>` of §59.7.1.

    GET   /automations/flows                 ?company=&account=&channel= -> {items, health, today}
    GET   /automations/flows/options         -> the models (the LLM router's allowed list), efforts, caps
    GET   /automations/flows/{ref}           -> FlowDef
    PATCH /automations/flows/{ref}           If-Match: <version> -> FlowDef (a new version);
                                             409 version_conflict, 422 invalid_flow {errors}
    POST  /automations/flows/{ref}/state     {state: on|off} -> FlowDef
    POST  /automations/flows/{ref}/pause     {until?} -> FlowDef
    POST  /automations/flows/{ref}/skip      {day, skip} -> FlowDef
    POST  /automations/flows/{ref}/run-now   {day?} -> 201 {run}; 409 already_ran {run}

Included before routes/flow_auto.py and routes/automations.py, so `/automations/flows…` is never
read as `/automations/{ref}`.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import flow_defs as FD
from hq_api.domain import flows as FL
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["automations"])
E = responses(401, 403, 404, 409, 422, 428)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"


@router.get("/automations/flows", response_model=FD.FlowList, responses=E)
async def list_automation_flows(
    company: str | None = Query(default=None, pattern=CODE),
    account: str | None = Query(default=None, max_length=100),
    channel: str | None = Query(default=None, max_length=40),
    ctx: Ctx = Depends(owner_ctx),
) -> FD.FlowList:
    """⟨1.39⟩ §61.3 every automation (companies → pages → each one; the off ones last), the road's
    health (§59.10) and today's runs, posts and cost."""
    async with ctx.tx() as tx:
        return await FD.list_flows(tx, ctx.hub, company, account, channel)


@router.get("/automations/flows/options", response_model=FD.FlowOptions, responses=E)
async def automation_flow_options(ctx: Ctx = Depends(owner_ctx)) -> FD.FlowOptions:
    """⟨1.39⟩ §61.3 what a save may pick: the models of the LLM router's allowed list that the
    workshop runs (the apps never write a model's name), the efforts, the cap's range, the limits
    and the kits in use."""
    async with ctx.tx() as tx:
        return await FD.options(tx)


@router.get("/automations/flows/{ref}", response_model=FD.FlowDef, responses=E)
async def get_automation_flow(ref: str, ctx: Ctx = Depends(owner_ctx)) -> FD.FlowDef:
    """⟨1.39⟩ §61.1 one automation, with its next run, today's and the month's cost, its health."""
    async with ctx.tx() as tx:
        return await FD.render(tx, ctx.hub, await FD.load(tx, ref))


@router.patch("/automations/flows/{ref}", response_model=FD.FlowDef, responses=E)
async def patch_automation_flow(
    ref: str, body: FD.FlowDefPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> FD.FlowDef:
    """⟨1.39⟩ §61.3, §61.4 a save (`If-Match: <version>`): a new version with its changes in
    Persian; the next minute's clock reads it (nothing in n8n is edited). 409 `version_conflict`
    when the version moved; 422 `invalid_flow {errors: [{field, message_fa}]}`."""
    async with ctx.tx() as tx:
        return await FD.patch(ctx, tx, request, ref, body)


async def _tap(request: Request, ctx: Ctx, do: Any) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await do(tx)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.post("/automations/flows/{ref}/state", response_model=FD.FlowDef, responses=E)
async def automation_flow_state(
    ref: str, body: FD.FlowDefStateIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.39⟩ §61.2 the switch: `off` starts no day; `on` (a pause ends too)."""
    return await _tap(request, ctx, lambda tx: FD.set_state(ctx, tx, ref, body.state))


@router.post("/automations/flows/{ref}/pause", response_model=FD.FlowDef, responses=E)
async def automation_flow_pause(
    ref: str, body: FD.FlowDefPauseIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.39⟩ §61.2 `paused`: the clock skips the days before `until` (no `until`: till `on`)."""
    return await _tap(request, ctx, lambda tx: FD.pause(ctx, tx, ref, body.until))


@router.post("/automations/flows/{ref}/skip", response_model=FD.FlowDef, responses=E)
async def automation_flow_skip(
    ref: str, body: FD.FlowDefSkipIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.39⟩ §61.3 one day skipped (`skip: false` undoes it)."""
    return await _tap(request, ctx, lambda tx: FD.skip(ctx, tx, ref, body.day, body.skip))


@router.post(
    "/automations/flows/{ref}/run-now",
    response_model=FD.FlowDefRunNow,
    status_code=201,
    responses=E,
)
async def automation_flow_run_now(
    ref: str, body: FD.FlowDefRunNowIn, request: Request, background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:  # fmt: skip
    """⟨1.39⟩ §61.3 the day's run now (default: the day the next post goes out), the owner's own
    tap: even a day paused or skipped, or a flow off (a pilot, run by hand, is off for the clock).
    One run per flow and day: a day that has one answers 409 `already_ran` with it. The day's
    order is placed as the clock and n8n place it (the same key of that day), so whichever comes
    later answers this one. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        flow = await FD.load(tx, ref)
        await FD._policy(ctx, "flow.run", flow)
        day = body.day or FD.default_day(flow)
        made = await tx.first(FD.MADE_SQL, k=flow.key, d=day.isoformat())
        if made is not None:
            run = await FD.run_ref_of(tx, ctx.hub, str(made["run"] or ""))
            raise ApiError(409, "already_ran", f"{flow.ref} ran {day}",
                           run=run.model_dump(mode="json") if run else {"ref": made["run"]})  # fmt: skip
        # a day made before and failed is made again under a key of its own
        again = (
            f":{uuid.uuid4()}" if await tx.scalar(FL.DAY_SQL, k=flow.key, d=day.isoformat()) else ""
        )
    try:
        fake = FL.clock_request(flow.key, day, again)
        got = await FL.start(Ctx(hub=ctx.hub, who=ctx.who, request=fake), fake, background,
                             flow.key, day, forced=True)  # fmt: skip
    except BaseException:
        if idem:
            async with ctx.tx() as tx:
                await idem.release(tx)
        raise
    async with ctx.tx() as tx:
        run = await FD.run_ref_of(tx, ctx.hub, str(got.get("order") or ""))
        if run is None:
            if idem:
                await idem.release(tx)
            raise ApiError(409, "validation_failed", "no run was made",
                           message_fa=str(got.get("why_fa") or "اجرا ساخته نشد."))  # fmt: skip
        out = FD.FlowDefRunNow(run=run)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out
