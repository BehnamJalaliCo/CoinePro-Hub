"""⟨1.22⟩ A session becomes a working group the owner can give to any company (contract §40.2,
§40.3): the owner's routes.

    POST   /orders/{ref}/playbook               the holder drafts a playbook from the session
                                                 (Idempotency-Key) → Playbook (draft), a card in
                                                 the session
    GET    /playbooks?state=                     the library
    GET    /playbooks/{ref}
    PATCH  /playbooks/{ref}                      draft only; any field but ref, state, source
    POST   /playbooks/{ref}/seal {publish?}      the owner's tap (⟨§45⟩ no step-up since
                                                 2026-11-10): the working group in the database,
                                                 the session's company its first member, with his
                                                 standing word on publishing when he gives it
    POST   /playbooks/{ref}/apply {company, platform?, note_fa?, as_is?, publish?}
                                                 (Idempotency-Key) as_is: the company joins the
                                                 sealed group; else a new session for that company
                                                 with the playbook as its first word
    POST   /playbooks/{ref}/retire               the owner's tap: its routines stop for every
                                                 member; nothing deleted

Owner only (owner_ctx). Every write is audited (A1/A2); the seal and the retire are A3.
⟨§45⟩ The owner, 2026-11-10: the passkey is for money, deleting for good, keys and access, and a
destructive command on a server. Sealing a working group hires inside the month's envelope and
retiring it deletes nothing, so both are his tap; a client that still sends a step-up assertion
is answered the same.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import live as LV
from hq_api.domain import order_report as OR
from hq_api.domain import playbooks as PB
from hq_api.domain import sessions as SE
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model

router = APIRouter(tags=["playbooks"])
E = responses(401, 403, 404, 409, 422)


class SealIn(Model):
    """⟨§45⟩ The owner's standing word on publishing for the session's company, given with
    the seal (`PUT /groups/{key}/members/{code}/publish` changes it later)."""

    publish: PB.PublishRuleIn | None = None


async def _standing(ctx: Ctx, tx: Any, ref: str, company: Any, rule: PB.PublishRuleIn) -> None:
    """The owner's standing word for one member of the playbook's group, audited as his."""
    from hq_api.domain import session_publish as SPB

    row = await PB.row_of(tx, ref)
    if row.get("group_id") is None:
        return
    set_to = await SPB.set_rule(
        tx, row["group_id"], company.id, mode=rule.mode, account=rule.account,
        story=rule.story, at=rule.at, best=rule.best,
    )  # fmt: skip
    key = PB.group_key(ref)
    await ctx.audit(tx, company_id=company.id, action="group.publish", action_class="A3",
                    target_kind="group", target_ref=f"{key}:{company.code}",
                    summary=f"the owner's standing permission to publish: {set_to['mode']}")  # fmt: skip


async def _out(tx: Any, ref: str) -> PB.Playbook:
    return await PB.render(tx, await PB.row_of(tx, ref))


# ------------------------------------------------------------------- draft --
@router.post("/orders/{ref}/playbook", response_model=PB.Playbook, status_code=201, responses=E)
async def draft_playbook(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The holder drafts a working group from this session (open or closed): one model call over
    the memory, the plan, the people hired into it, its automations, lines and cards, checked by
    code (a seat's role must be a real charter, a routine's schedule a rule the calendar holds;
    the rest is dropped with a note in `note_fa`). Stored `draft`; a card «کارگروه از این جلسه»
    is posted in the session. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if await OR.ensure(tx, ref) is None:
            raise ApiError(404, "not_found", "unknown order", message_fa=SE.NOT_FOUND_FA)
    d, m, notes = await PB.draft(ctx, ref)
    async with ctx.tx() as tx:
        holding = await ctx.hub.companies.holding()
        row = await PB.store_draft(tx, holding.id, m, d, notes)
        await ctx.audit(tx, company_id=holding.id, action="playbook.draft", action_class="A1",
                        target_kind="playbook", target_ref=row["ref"],
                        summary=f"from {ref}: {len(d['seats'])} seats, {len(d['routines'])} routines")  # fmt: skip
        result = await PB.render(tx, row)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# ----------------------------------------------------------------- library --
@router.get("/playbooks", response_model=list[PB.Playbook], responses=E)
async def list_playbooks(
    state: Literal["draft", "sealed", "retired"] | None = None, ctx: Ctx = Depends(owner_ctx)
) -> list[PB.Playbook]:
    """The library: every playbook, newest first (`state` narrows it)."""
    async with ctx.tx() as tx:
        return await PB.listing(tx, state)


@router.get("/playbooks/{ref}", response_model=PB.Playbook, responses=E)
async def get_playbook(ref: str, ctx: Ctx = Depends(owner_ctx)) -> PB.Playbook:
    """One playbook: its seats, routines, KPIs, connections, rules, source and members."""
    async with ctx.tx() as tx:
        return await _out(tx, ref)


@router.patch("/playbooks/{ref}", response_model=PB.Playbook, responses=E)
async def patch_playbook(
    ref: str, body: PB.PlaybookPatch, ctx: Ctx = Depends(owner_ctx)
) -> PB.Playbook:
    """The owner edits the draft directly (draft only: 409 once sealed): any field of the shape
    but `ref`, `state`, `source`. What does not hold (an unknown role, a bad schedule) is dropped
    with a note in `note_fa`; `version` counts up."""
    async with ctx.tx() as tx:
        row = await PB.patch(tx, ctx.hub, ref, body.model_dump())
        holding = await ctx.hub.companies.holding()
        changed = ", ".join(k for k, v in body.model_dump().items() if v is not None)
        await ctx.audit(tx, company_id=holding.id, action="playbook.edit", action_class="A1",
                        target_kind="playbook", target_ref=ref, summary=changed)  # fmt: skip
        return await PB.render(tx, row)


# -------------------------------------------------------------------- seal --
@router.post("/playbooks/{ref}/seal", response_model=PB.Playbook, responses=E)
async def seal_playbook(
    ref: str, body: SealIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> PB.Playbook:
    """The owner's tap (⟨§45⟩ no step-up): the draft becomes a working group stored in the
    database (eligibility `chosen`: only the companies the owner gives it to) and the session's
    company its first member, the seats resolved to the people the session hired, the empty ones
    filled by automatic hiring inside the envelope; its routines run from their next time.
    `publish`: his standing word for that company (`auto`: each routine's package goes out by
    itself from the next run; left out: each waits for his tap)."""
    async with ctx.tx() as tx:
        row = await PB.seal(tx, ctx.hub, ref)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="playbook.seal", action_class="A3",
                        target_kind="playbook", target_ref=ref,
                        summary=f"group {PB.group_key(ref)}")  # fmt: skip
        src = PB._j(row["source"]) or {}
        first = await ctx.hub.companies.find(str(src.get("company") or ""))
        rule = body.publish if body is not None else None
        if rule is not None and first is not None and first.kind != "holding":
            await _standing(ctx, tx, ref, first, rule)
        await ctx.interaction(tx, company_id=holding.id, kind="decision", action="playbook.seal",
                              target_kind="playbook", target_ref=ref, data={"state": "sealed"})  # fmt: skip
        return await PB.render(tx, row)


# ------------------------------------------------------------------- apply --
@router.post("/playbooks/{ref}/apply", response_model=PB.PlaybookApplied, responses=E)
async def apply_playbook(
    ref: str,
    body: PB.PlaybookApplyIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Give the playbook to another company or platform. `as_is` (sealed only): the company joins
    the working group at once, no session. Else a new order for that company, held by its CEO
    (or the manager of the matching department), whose first word is the playbook as Markdown
    and the owner's note («این کارگروه را برای … روی … پیاده کن»); the holder adapts it there, and
    sealing the draft made from that session records `parent`. Requires `Idempotency-Key`."""
    from hq_api.routes.orders import record_order, secretary

    company = await ctx.hub.companies.find(body.company)
    if company is None or company.kind == "holding":
        raise ApiError(404, "not_found", "unknown company", message_fa="این شرکت را نمیشناسم.")
    if body.as_is:
        async with ctx.tx() as tx:
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay
            await PB.apply_as_is(tx, ctx.hub, ref, company)
            if body.publish is not None:  # ⟨§45⟩ his standing word for this company, with the gift
                await _standing(ctx, tx, ref, company, body.publish)
            await LV.playbook_flow(tx, await PB.row_of(tx, ref), company.code, None)
            await ctx.audit(tx, company_id=company.id, action="playbook.apply", action_class="A2",
                            target_kind="playbook", target_ref=ref, summary=f"as is: {company.code}")  # fmt: skip
            pb = await _out(tx, ref)
            member = next((x for x in pb.members if x.company == company.code), None)
            result = PB.PlaybookApplied(playbook=pb, member=member)
            if idem:
                await idem.store(tx, 200, result.model_dump(mode="json"))
        return result
    async with ctx.tx() as tx:
        idempotency.read_key(request, required=True)  # before the secretary's call
        row = await PB.row_of(tx, ref)
        if row["state"] == "retired":
            raise ApiError(409, "validation_failed", "the playbook is retired",
                           message_fa="این کارگروه بازنشسته شده است.")  # fmt: skip
        pb = await PB.render(tx, row)
    text = PB.apply_text(pb, company.name_fa or company.code, body.platform, body.note_fa)
    s = await secretary(ctx, text, company.code)
    later: list[Any] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await record_order(ctx, tx, s, text, later, source="text", hint=company.code,
                                 remember=False)  # fmt: skip
        await PB.mark_source(tx, out.ref, ref)
        await LV.playbook_flow(
            tx, row, company.code, out.routes[0].work_ref if out.routes else None
        )
        rep = await OR.ensure(tx, out.ref)
        if rep is not None and rep.get("conversation_ref"):
            from hq_api.domain import order_turns as OT

            await OT.to_talk_owner(tx, rep, text)
            await SE.remember(tx, rep["id"], f"این جلسه از کارگروه {ref} باز شد")
        await ctx.audit(tx, company_id=company.id, action="playbook.apply", action_class="A2",
                        target_kind="playbook", target_ref=ref,
                        summary=f"session {out.ref} for {company.code} ({body.platform or 'any'})")  # fmt: skip
        result = PB.PlaybookApplied(playbook=await _out(tx, ref), order=out.ref,
                                    conversation=out.talk_ref)  # fmt: skip
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return result


# ------------------------------------------------------------------ retire --
@router.post("/playbooks/{ref}/retire", response_model=PB.Playbook, responses=E)
async def retire_playbook(ref: str, ctx: Ctx = Depends(owner_ctx)) -> PB.Playbook:
    """The owner's tap (⟨§45⟩ no step-up): its routines stop for every member (the group `off`);
    nothing is deleted."""
    async with ctx.tx() as tx:
        row = await PB.retire(tx, ref)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="playbook.retire", action_class="A3",
                        target_kind="playbook", target_ref=ref, summary="retired")  # fmt: skip
        return await PB.render(tx, row)
