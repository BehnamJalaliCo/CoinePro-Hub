"""⟨1.37⟩ Contract §59.4, §59.7-§59.10 (prompt 38): the flow automations, the use form, the board,
the owner's day, and n8n's clock (`/internal/v1/flows/tick`, `/internal/v1/flows/summary`).

Included before `routes/automations.py`, so `/automations/board`, `/automations/today` and
`/automations/calendar` are matched before `/automations/{ref}`.

The flow (domain/flow_auto.py), owner only, each a tap (no step-up), `Idempotency-Key` on POST,
audited `automation.<verb>` with before and after:

    POST  /playbooks/{ref}/use            UseForm -> 201 PlaybookUsed; `dry: true` -> 200 UsePreview
    GET   /automations/{ref}/runs         ?limit=20&before= -> FlowRuns
    POST  /automations/{ref}/run-now      -> 201 FlowRunRef; 409 budget_reached past the day's cap
    POST  /automations/{ref}/pause        {until?} -> FlowAutomation
    POST  /automations/{ref}/skip         {at?, skip} -> FlowAutomation
    PATCH /automations/{ref}              {schedule?, account?, story?, mode?, budget?, title_fa?}
                                          -> FlowAutomation (a cap raised past the company's month
                                          envelope: 🔏 automation.budget on `<ref>:<per_day_usd>`)
    POST  /internal/v1/flows/tick         n8n each minute, HMAC-signed (X-HQ-Signature), as a
                                          line's callback; 401 unsigned

`GET /automations/{ref}` and `POST /automations/{ref}/state` stay in routes/automations.py (one
path for every kind): a flow's answer is its FlowAutomation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import flow_auto as FA
from hq_api.domain import flow_shapes as FS
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.lines import engine, signing
from hq_api.routes.lines import n8n_secret

router = APIRouter(tags=["automations"])
internal_router = APIRouter(tags=["flows"])
E = responses(401, 403, 404, 409, 422)
AT = r"^AT-[0-9]{4,}$"
PB = r"^PB-[0-9]{4,}$"


class TickOut(BaseModel):
    source: str
    made: int = 0
    skipped: int = 0
    runs: list[str] = Field(default_factory=list)
    idle: str | None = None


# ------------------------------------------------------------- §59.4 the use form --
@router.post(
    "/playbooks/{ref}/use",
    response_model=FA.PlaybookUsed | FS.UsePreview,
    status_code=201,
    responses=E,
)
async def use_playbook(
    ref: str, body: FS.UseForm, request: Request, response: Response,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:  # fmt: skip
    """⟨1.37⟩ §59.4 «در شرکت دیگر به کار ببر»: one form. `dry: true` → `UsePreview` (each day in
    plain Persian, the first publish time, the cost from the playbook's last 30 days, and the
    warnings; `by_hub`: the hub settles it, never the owner's step); nothing is made. Without `dry`
    (`Idempotency-Key`; audit `playbook.use`, A3; his tap, no step-up): the membership with its
    version pinned (default the newest sealed), its seats (hired inside the month envelope), the
    flow's line, the standing word and the flow automation → `201 PlaybookUsed`. 409 «این شرکت
    همین کارگروه را دارد» when the company already runs this playbook's flow."""
    out = await FA.use(ctx, request, ref, body)
    if isinstance(out, FS.UsePreview):
        response.status_code = 200
    return out


# ------------------------------------------------------------ §59.7 the controls --
@router.get("/automations/{ref}/runs", response_model=FS.FlowRuns, responses=E)
async def flow_runs(
    ref: str,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> FS.FlowRuns:
    """⟨1.37⟩ §59.8 the flow's runs, newest first, each with its topic, cost and results;
    `before`: the previous page's `next_cursor`."""
    async with ctx.tx() as tx:
        return await FA.runs(tx, await FA.load(tx, ref), limit, before)


@router.post(
    "/automations/{ref}/run-now", response_model=FS.FlowRunRef, status_code=201, responses=E
)
async def flow_run_now(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.37⟩ §59.7 a run now: today's occurrence when it has no run yet (it publishes at its
    hour), else an extra run, not the day's (it publishes at once). 409 `budget_reached` when
    the day's cap is spent. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await FA.run_now(ctx, tx, ref)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    if out.state == "queued":
        await engine.kick(ctx.hub, out.ref)
    return out


@router.post("/automations/{ref}/pause", response_model=FS.FlowAutomation, responses=E)
async def flow_pause(
    ref: str, body: FS.FlowPauseIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.37⟩ §59.7 `paused` till `until` (then on by itself), or till `state: on`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await FA.pause(ctx, tx, ref, body.until)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.post("/automations/{ref}/skip", response_model=FS.FlowAutomation, responses=E)
async def flow_skip(
    ref: str, body: FS.FlowSkipIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.37⟩ §59.7 the next occurrence (or the one at `at`) skipped; `skip: false` undoes it."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        out = await FA.skip(ctx, tx, ref, body.at, body.skip)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.patch("/automations/{ref}", response_model=FS.FlowAutomation, responses=E)
async def flow_patch(
    ref: str, body: FS.FlowPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> FS.FlowAutomation:
    """⟨1.37⟩ §59.7 the flow's hour, account, story, mode, budget or title: a tap. Lowering a cap
    is a tap; raising one is a tap while the day's cap × 30 stays inside the company's USD month
    budget (§18.11), else 🔏 `automation.budget` on `<ref>:<per_day_usd>`. A run waiting on its
    budget looks again at once."""
    async with ctx.tx() as tx:
        if await FA.kind_of(tx, ref) not in (None, "flow"):
            raise ApiError(409, "validation_failed", "only a flow is changed here",
                           message_fa="این اتوماسیون از روند روزانه نیست.")  # fmt: skip
        out, budget = await FA.patch(ctx, tx, request, ref, body)
        waiting = await FA.waiting_runs(tx, await FA.load(tx, ref)) if budget else []
    for run in waiting:
        await engine.wake(ctx.hub, run)
    return out


# ------------------------------------------------------------------ n8n's clock --
@internal_router.post("/flows/tick", response_model=TickOut, responses=responses(401))
async def flows_tick(request: Request, hub: Hub = Depends(get_hub)) -> TickOut:
    """⟨1.37⟩ §59.7 n8n's minute (workflow `hq-flows`), signed like a line's callback
    (`X-HQ-Signature: t=<ts>,v1=hmac_sha256(secret, "<t>.<body>")`, kv/hq/n8n): the clock is
    stamped and every flow whose occurrence is due starts, once per occurrence (`trigger: n8n`).
    The body is not read (`{}`)."""
    raw = await request.body()
    if not signing.verify(await n8n_secret(hub), raw, request.headers.get(signing.HEADER)):
        raise ApiError(401, "unauthenticated", "bad signature")
    return TickOut.model_validate(await FA.due(hub, source="n8n"))
