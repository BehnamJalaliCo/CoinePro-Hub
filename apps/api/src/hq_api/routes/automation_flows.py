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
    ⟨39.1⟩ P2:
    GET   /automations/flows/{ref}/versions  -> [FlowVersion] (newest first, the changes in Persian)
    POST  /automations/flows/{ref}/rollback  {version} -> FlowDef (that body as the next version)
    GET   /automations/flows/{ref}/runs      ?limit=&before= -> {items, next}
    GET   /automations/flows/{ref}/health    -> state, last run, 30 days, cost, next, alerts
    GET   /automations/flows/{ref}/graph     -> the map of §59.7.1
    POST  /automations/flows                 a new automation from a kit -> 201 FlowDef (on, v1)
    GET   /automations/kits                  -> [Kit];  GET /automations/kits/{key}/graph
    POST  /automations/kits/request          {account, note_fa} -> 201 {order, work}: a direct session
    GET   /automations/week                  ?from= -> the week (§61.7)

Included before routes/flow_auto.py and routes/automations.py, so `/automations/flows…` is never
read as `/automations/{ref}`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import flow_defs as FD
from hq_api.domain import flow_shapes as FS
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


@router.post("/automations/flows", response_model=FD.FlowDef, status_code=201, responses=E)
async def create_automation_flow(
    body: FD.FlowDefCreate, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨39.1⟩ §61.5 «بساز و روشن کن»: a new automation from a kit for a registered page, checked as
    a save (422 invalid_flow), `on` at version 1; the hub's clock runs it (no n8n workflow).
    Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await FD.create(ctx, tx, body)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/automations/kits", response_model=list[FD.Kit], responses=E)
async def automation_kits(ctx: Ctx = Depends(owner_ctx)) -> list[FD.Kit]:
    """⟨39.1⟩ §61.5 the kits that run today, with the pages using them and their mean day."""
    async with ctx.tx() as tx:
        return await FD.kits(tx)


@router.get("/automations/kits/{key}/graph", response_model=FS.FlowGraph, responses=E)
async def automation_kit_graph(
    key: str = Path(max_length=100), ctx: Ctx = Depends(owner_ctx)
) -> FS.FlowGraph:
    """⟨39.1⟩ §61.5 a kit's map, before an automation is made from it."""
    async with ctx.tx() as tx:
        return await FD.kit_graph(tx, key)


@router.post(
    "/automations/kits/request", response_model=FD.KitRequestOut, status_code=201, responses=E
)
async def automation_kit_request(
    body: FD.KitRequestIn, request: Request, background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:  # fmt: skip
    """⟨39.1⟩ §61.5 «کیت تازه»: a direct session with the workshop for this page, as the DotCoin
    pilot was made; its sample comes to that session for the owner's yes. Requires
    `Idempotency-Key`."""
    return await FD.kit_request(ctx, request, background, body)


@router.get("/automations/week", response_model=FD.FlowWeek, responses=E)
async def automation_week(
    from_: date | None = Query(default=None, alias="from"), ctx: Ctx = Depends(owner_ctx)
) -> FD.FlowWeek:
    """⟨39.1⟩ §61.7 the automations' week (Saturday first): runs, posts, cost, each day's posts
    and plan, each page's line (`best` stays null until `insights`)."""
    async with ctx.tx() as tx:
        return await FD.week(tx, from_)


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


@router.get("/automations/flows/{ref}/versions", response_model=list[FD.FlowVersion], responses=E)
async def automation_flow_versions(ref: str, ctx: Ctx = Depends(owner_ctx)) -> list[FD.FlowVersion]:
    """⟨39.1⟩ §61.3 every version, newest first, with its changes in Persian; version 1 is «ساخته
    شد از روند کدی هاب» (or the kit it was made from)."""
    async with ctx.tx() as tx:
        return await FD.versions(tx, ref)


@router.post("/automations/flows/{ref}/rollback", response_model=FD.FlowDef, responses=E)
async def automation_flow_rollback(
    ref: str, body: FD.FlowRollbackIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨39.1⟩ §61.3 «برگشت به این نسخه»: that body saved again as the next version, through §61.4's
    checks; nothing is deleted (audit `automation.flow.rollback`)."""
    return await _tap(request, ctx, lambda tx: FD.rollback(ctx, tx, ref, body.version))


@router.get("/automations/flows/{ref}/runs", response_model=FD.FlowDefRuns, responses=E)
async def automation_flow_runs(
    ref: str,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None, max_length=40),
    ctx: Ctx = Depends(owner_ctx),
) -> FD.FlowDefRuns:
    """⟨39.1⟩ §61.3 the flow's days, newest first, each with its cost and its publications."""
    async with ctx.tx() as tx:
        return await FD.runs(tx, ctx.hub, ref, limit, before)


@router.get("/automations/flows/{ref}/health", response_model=FD.FlowDefHealthPage, responses=E)
async def automation_flow_health(ref: str, ctx: Ctx = Depends(owner_ctx)) -> FD.FlowDefHealthPage:
    """⟨39.1⟩ §61.3 the flow's health with its open alerts (§61.6)."""
    async with ctx.tx() as tx:
        return await FD.health_page(tx, ctx.hub, ref)


@router.get("/automations/flows/{ref}/graph", response_model=FS.FlowGraph, responses=E)
async def automation_flow_graph(ref: str, ctx: Ctx = Depends(owner_ctx)) -> FS.FlowGraph:
    """⟨39.1⟩ §61.3 the map of §59.7.1, from the flow's steps."""
    async with ctx.tx() as tx:
        return await FD.graph(tx, ref)
