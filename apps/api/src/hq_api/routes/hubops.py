"""The hub run from the app (contract §38): hub operations and the owner's services page.

Agents (/internal/v1; the holding's technical roles only, by the policy hq.internal `hubops.*`):
    POST /hubops {op, args?}             one operation of the catalogue (domain/hub_ops.py): queued,
                                         or `awaiting_seal` with a 🔏 hub_op card for an A3 one
    GET  /hubops/{ref}?wait_s            the requester's job (output masked, ≤ 64 KB)
The hub-ops dispatcher (service principal `hubops`, its own token; /internal/v1):
    POST /hubops/claim                   one queued job (none while the holding's kill switch is on)
    POST /hubops/{ref}/done              {exit_code, output, refused?}: masked again here
    POST /hubops/snapshot                the host's memory, caps and switches (≤ every 60 s)
Owner (/api/v1):
    GET  /hubops?limit                   the recent jobs, in plain Persian
    GET  /hub/services                   HubServices: the optional services, the core ones, memory
    POST /hub/services/{key}             {on, turn_off?} (Idempotency-Key; no passkey) -> 202 HubJob
    GET  /hub/jobs/{ref}                 HubJob
Stream: hub.job on topic `hub`.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from hq_api import idempotency
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import hub_ops as H
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow

router = APIRouter(tags=["hub"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428, 429, 503)
REF = r"^HJ-[0-9]{6,}$"
WAIT_MAX_S = 15


# ----------------------------------------------------------------- shapes --
class HubOpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str = Field(min_length=1, max_length=60)
    args: dict[str, Any] = Field(default_factory=dict)


class Blocking(BaseModel):
    key: str
    title_fa: str
    mem_cap_mb: float


class HubJob(BaseModel):
    """§38.3 a hub job as the owner's app sees it."""

    ref: str
    op: str
    title_fa: str
    state: Literal["queued", "running", "done", "failed", "refused", "awaiting_seal"]
    result_fa: str | None
    blocking: list[Blocking] = Field(default_factory=list)
    requested_by: str
    decision_ref: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class HubMemory(BaseModel):
    total_mb: float | None
    budget_mb: float | None
    caps_mb: float | None
    free_mb: float | None


class HubService(BaseModel):
    key: str
    title_fa: str
    what_fa: str
    state: Literal["on", "off", "starting", "failed"]
    optional: bool
    mem_cap_mb: float
    mem_used_mb: float | None
    can_toggle: bool
    note_fa: str | None


class HubServices(BaseModel):
    memory: HubMemory | None
    services: list[HubService]
    at: datetime | None


class SwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: StrictBool
    turn_off: list[str] = Field(default_factory=list, max_length=7)


def _hub_job(j: dict[str, Any]) -> HubJob:
    v = H.view(j, with_output=False)
    return HubJob(
        ref=v["ref"],
        op=v["op"],
        title_fa=v["title_fa"],
        state=v["state"],
        result_fa=v["result_fa"],
        blocking=[Blocking(**b) for b in v["blocking"]],
        requested_by=v["requested_by"],
        decision_ref=v["decision_ref"],
        created_at=v["created_at"],
        finished_at=v["finished_at"],
    )


# ------------------------------------------------------------------ agents --
def _agent_target(ctx: Ctx, holding_id: Any, c: H.Checked | None, mode: str) -> dict[str, Any]:
    who = ctx.who
    return {
        "charter": who.charter,
        "holding": who.company_id == holding_id,
        "class": c.cls if c else "A0",
        "op": c.op.name if c else None,
        "mode": mode,
    }


async def _holding_id(ctx: Ctx) -> Any:
    return (await ctx.hub.companies.holding()).id


def _charter_holds(ctx: Ctx) -> None:
    lib = ctx.hub.charters
    who = ctx.who
    if (
        lib is not None
        and lib.get(who.charter) is not None
        and "hub.ops" not in lib.allowed(who.charter)
    ):
        raise ApiError(403, "policy_denied", "hub.ops is not in the charter",
                       message_fa=NOT_YOURS_FA)  # fmt: skip


NOT_YOURS_FA = (
    "کار روی خود هاب با مدیر عملیات هوش مصنوعی و SRE سکوی هاب است: با work.request به AIOPS بگو "
    "دقیقاً چه کاری لازم است."
)


async def _agent_gate(ctx: Ctx, c: H.Checked | None, mode: str) -> Any:
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    hid = await _holding_id(ctx)
    if not H.is_technical(who, holding_id=hid):
        raise ApiError(
            403, "policy_denied", "the holding's technical roles only", message_fa=NOT_YOURS_FA
        )
    _charter_holds(ctx)
    op = {"read": "hubops.read", "run": "hubops.run", "propose": "hubops.propose"}[mode]
    await allow(ctx, op, _agent_target(ctx, hid, c, mode))
    return hid


@internal_router.post("/hubops", status_code=201, responses=E)
async def hub_op(body: HubOpIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """hub.ops: one operation of the fixed catalogue, for the holding's technical roles. A0 and
    A2 are queued for the hub-ops dispatcher; an A3 one raises a 🔏 `hub_op` card and waits in
    `awaiting_seal`. A denied operation answers 403 policy_denied with the owner's step
    (`message_fa`). Every one is audited."""
    c = H.check(body.op, body.args)  # 403 with the owner's step for a denied op, or 422
    mode = "read" if c.cls == "A0" else ("propose" if c.cls == "A3" else "run")
    await _agent_gate(ctx, c, mode)
    async with ctx.tx() as tx:
        h = await H.holding(tx)
        j = await H.create(
            tx,
            c,
            by=ctx.who,
            holding_id=h["id"],
            holding_code=h["code"],
            state="awaiting_seal" if c.cls == "A3" else "queued",
        )
        if c.cls == "A3":
            j = await H.seal_card(tx, j, c, by=ctx.who)
    return _agent_view(j)


def _agent_view(j: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"job": H.view(j)}
    if j["state"] == "awaiting_seal":
        out["hint_fa"] = (
            f"این کار مُهر مدیر کل میخواهد ({j['decision_ref']}); با همین job بعداً وضعش را ببین."
        )
    elif j["state"] in ("queued", "running"):
        out["hint_fa"] = "کار هنوز تمام نشده؛ با همین job دوباره بپرس."
    return out


@internal_router.get("/hubops/{ref}", responses=E)
async def hub_op_job(
    ref: str = Path(pattern=REF),
    wait_s: int = Query(default=0, ge=0, le=WAIT_MAX_S),
    ctx: Ctx = Depends(internal_ctx),
) -> dict[str, Any]:
    """The requester's own job, waiting up to `wait_s` for it to finish."""
    await _agent_gate(ctx, None, "read")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    while True:
        async with ctx.tx() as tx:
            j = await H.load(tx, ref)
        if j["requested_by"] != ctx.who.code:
            raise ApiError(404, "not_found", "no such hub job of yours")
        if j["state"] not in ("queued", "running") or loop.time() >= deadline:
            return _agent_view(j)
        await asyncio.sleep(1.0)


# -------------------------------------------------------------- dispatcher --
async def _dispatcher(ctx: Ctx) -> None:
    if ctx.who.kind != "service":
        raise ApiError(403, "policy_denied", "the hub-ops dispatcher only")
    await allow(ctx, "hubops.jobs", {})


@internal_router.post("/hubops/claim", responses=E)
async def hub_claim(ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """The next hub job, one at a time; none while the holding's kill switch is engaged."""
    await _dispatcher(ctx)
    async with ctx.tx() as tx:
        return await H.claim(tx)


@internal_router.post("/hubops/{ref}/done", responses=E)
async def hub_done(
    body: H.DoneIn, ref: str = Path(pattern=REF), ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    """A job's result (idempotent); the output is masked again and capped at 64 KB."""
    await _dispatcher(ctx)
    async with ctx.tx() as tx:
        j = await H.finish(tx, ref, body)
    return {"ref": j["ref"], "state": j["state"]}


@internal_router.post("/hubops/snapshot", responses=E)
async def hub_snapshot(body: H.SnapshotIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """The dispatcher's latest look at the host (memory, caps, use per container, switches)."""
    await _dispatcher(ctx)
    async with ctx.tx() as tx:
        await H.store_snapshot(tx, body)
    return {"ok": True}


# ------------------------------------------------------------------- owner --
@router.get("/hubops", response_model=list[HubJob], responses=E)
async def recent_hub_jobs(
    limit: int = Query(default=30, ge=1, le=100), ctx: Ctx = Depends(owner_ctx)
) -> list[HubJob]:
    """The recent hub jobs (the agents' and the owner's), newest first, with plain Persian titles."""
    async with ctx.tx() as tx:
        rows = await tx.all(H.JOB_SQL + " ORDER BY j.created_at DESC LIMIT :l", l=limit)
    return [_hub_job(dict(r)) for r in rows]


@router.get("/hub/services", response_model=HubServices, responses=E)
async def hub_services(ctx: Ctx = Depends(owner_ctx)) -> HubServices:
    """§38.3 the owner's «سرویس‌ها» page: each optional service with its switch and memory, the
    core ones, and the hub's memory from the dispatcher's latest snapshot (`memory` null while the
    dispatcher has never reported: the hub part is not installed yet)."""
    async with ctx.tx() as tx:
        return HubServices.model_validate(await H.services(tx))


@router.post(
    "/hub/services/{key}",
    response_model=HubJob,
    status_code=202,
    responses={**E, 202: {"model": HubJob, "description": "the switch's job"}},
)
async def switch_hub_service(
    key: str, body: SwitchIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Switch one optional service on or off (Idempotency-Key; no passkey: optional services
    only). `turn_off` switches those off first, in the same job. Over the memory budget the job
    ends `refused` with `blocking`: the optional services that are on, largest first."""
    if key not in H.PROFILES:
        raise ApiError(404, "not_found", "not an optional service")
    if not H.PROFILES[key].toggle:
        raise ApiError(409, "not_ready", f"{key} is not switched from here",
                       message_fa=H.PROFILES[key].note_fa)  # fmt: skip
    c = H.check("profile", {"name": key, "on": body.on, "turn_off": body.turn_off})
    c = dataclasses.replace(c, cls="A2")  # the owner's own word: no seal (§38.3)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        h = await H.holding(tx)
        j = await H.create(tx, c, by=ctx.who, holding_id=h["id"], holding_code=h["code"])
        await ctx.interaction(
            tx,
            company_id=h["id"],
            kind="setting",
            action="hub_service.switch",
            target_kind="hub_service",
            target_ref=key,
            data={"on": body.on, "turn_off": c.args["turn_off"], "job": j["ref"]},
        )
        out = _hub_job(j)
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    return JSONResponse(status_code=202, content=out.model_dump(mode="json"))


@router.get("/hub/jobs/{ref}", response_model=HubJob, responses=E)
async def hub_job(ref: str, ctx: Ctx = Depends(owner_ctx)) -> HubJob:
    """One hub job (the app polls it, or follows the stream's `hub.job`)."""
    if not ref.startswith("HJ-"):
        raise ApiError(404, "not_found", "no such hub job")
    async with ctx.tx() as tx:
        return _hub_job(await H.load(tx, ref))
