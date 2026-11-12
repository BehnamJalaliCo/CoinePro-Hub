"""⟨1.19⟩ Erasing for good from the archive, one output, and an agent's proposal (contract §37.2,
§37.3). The session's own erase is in routes/sessions.py (§37.1).

    GET  /archive/records/{ref}/erase/preview   what the record's erase removes (nothing changes)
    POST /archive/records/{ref}/erase           🔏 archive.erase (target = ref): the archive's own
                                                disposal run now; a held record is 409 (message_fa
                                                names the hold). Idempotency-Key
    GET  /deliverables/{ref}/erase/preview      what the output's erase removes
    POST /deliverables/{ref}/erase              🔏 output.erase (target = ref): one output and its
                                                files, its pending cards withdrawn; its work stays
                                                (its order says «خروجی پاک شد»). Idempotency-Key
    /internal/v1/erase/propose                  erase.propose (A1, every working role): a card
                                                `erase` to the owner with the preview's counts, for
                                                what the agent can read; its seal runs the erase

Owner only for the erases (owner_ctx); every erase writes one audit line (A3, the counts) and the
stored objects it freed are destroyed after the commit.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import decisions as D
from hq_api.domain import erase as ER
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup

router = APIRouter(tags=["erase"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
RECORD = r"^AR-[0-9]{6,}$"
OUTPUT = r"^O-[0-9]{6,}$"


async def _erase(ctx: Ctx, request: Request, kind: str, ref: str) -> Any:
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if kind == "archive_record":
            from hq_api.archive import clearance as CL

            await CL.full(tx)
        await stepup.consume(tx, request, ctx.who, ER.ACTION[kind], ref)
        out = await ER.erase(tx, ctx.who, kind, ref, step_up=True, request_id=ctx.request_id)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    await ER.destroy_after(ctx.hub)
    return out


# ---------------------------------------------------------------- archive --
@router.get("/archive/records/{ref}/erase/preview", response_model=ER.ErasePreview, responses=E)
async def erase_record_preview(ref: str, ctx: Ctx = Depends(owner_ctx)) -> ER.ErasePreview:
    """What erasing this record removes (its files) and what stays (a tombstone with only the
    ref, the date and «به دستور مدیر کل»; one audit line). A held record says so first."""
    from hq_api.archive import clearance as CL

    async with ctx.tx() as tx:
        await CL.full(tx)
        return await ER.record_preview(tx, ref)


@router.post("/archive/records/{ref}/erase", response_model=ER.Erased, responses=E)
async def erase_record(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `archive.erase` (target = the ref): the archive's own disposal (§23.5) run now instead of
    on its schedule: the record's files destroyed and the record removed (disposed); its
    tombstone keeps only the ref, the date and «به دستور مدیر کل». A record under a legal hold
    answers 409 with `message_fa` naming the hold. Requires `Idempotency-Key`."""
    return await _erase(ctx, request, "archive_record", ref)


# ----------------------------------------------------------------- output --
@router.get("/deliverables/{ref}/erase/preview", response_model=ER.ErasePreview, responses=E)
async def erase_output_preview(ref: str, ctx: Ctx = Depends(owner_ctx)) -> ER.ErasePreview:
    """What erasing this output removes (it and the files only it carried) and what stays (the
    work it belongs to; an archive record filed from it; one audit line)."""
    from hq_api.archive import clearance as CL

    async with ctx.tx() as tx:
        # the archived copy is counted in archive.records, whose policies hide every row
        # from a transaction without a clearance: the owner's is full
        await CL.full(tx)
        return await ER.output_preview(tx, ref)


@router.post("/deliverables/{ref}/erase", response_model=ER.Erased, responses=E)
async def erase_output(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `output.erase` (target = the ref): one output and its files, the notifications that
    point at it, its pending cards withdrawn; the work it belongs to stays and its order's story
    says «خروجی پاک شد». Requires `Idempotency-Key`."""
    return await _erase(ctx, request, "output", ref)


# ------------------------------------------------------------- the agents --
class ProposeIn(Model):
    kind: Literal["session", "archive_record", "output"]
    ref: str = Field(pattern=r"^(F-[0-9]{4,}|AR-[0-9]{6,}|O-[0-9]{6,})$")
    why_fa: str = Field(min_length=2, max_length=2000)


PREFIX = {"session": "F-", "archive_record": "AR-", "output": "O-"}


@internal_router.post("/erase/propose", response_model=D.Decision, status_code=201, responses=E)
async def erase_propose(body: ProposeIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """erase.propose (A1, every working role): an agent proposes erasing a session, an archive
    record or an output for good: a decision card `erase` to the owner with the preview's counts.
    The policy lets a role propose only what it can read (an order it works on, an output of its
    company or of an order it works on, a record within its clearance; a holding-scope role reads
    every company). An agent never erases anything itself. Requires `Idempotency-Key`."""
    if not ctx.who.is_agent or ctx.who.company_id is None or ctx.who.company is None:
        raise ApiError(403, "policy_denied", "agents only")
    if not body.ref.startswith(PREFIX[body.kind]):
        raise ApiError(422, "validation_failed", fields={"ref": f"a {body.kind} ref"})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        can, company = await ER.readable(tx, ctx.who, body.kind, body.ref)
        await allow(
            ctx,
            "erase.propose",
            {"company": company, "kind": body.kind, "readable": can},
        )
        if not can:
            raise ApiError(403, "policy_denied", "not something you can read")
        d = await ER.propose(tx, ctx.who, body.kind, body.ref, body.why_fa)
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,
            action="erase.propose",
            action_class="A1",
            target_kind="decision",
            target_ref=d["ref"],
            summary=f"{body.kind} {body.ref}",
        )
        result = D.render(d)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    await workflows_client.decision_created(ctx.hub, result.ref)
    return result
