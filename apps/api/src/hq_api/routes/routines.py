"""⟨1.31⟩ §50 A standing routine from one sentence («کارمند ۲۴ ساعته»).

POST /routines            {sentence_fa, company?, order?}: one compile (§31.7), then, when the
                          sentence is a plain routine (a schedule that makes work or tells
                          someone), it is `on` at once: the owner's sentence is the seal
GET  /routines            the routines the owner (or a session's holder for him) started this
                          way, newest first (filter by `company` or `order`)

Switched off and on again with POST /automations/{ref}/state (no step-up). The agents' way in is
`automation.propose` (routes/automations.py), which makes the same thing when the owner's own
words in that session ask for it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import automations as AU
from hq_api.domain import order_report as OR
from hq_api.domain import routines as RT
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model
from hq_common.redact import scrub

router = APIRouter(tags=["automations"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
ORDER = r"^F-[0-9]{4,}$"


class RoutineIn(Model):
    sentence_fa: str = Field(min_length=3, max_length=1000)
    company: str | None = Field(default=None, pattern=CODE)
    # the session it is said in: the routine is listed there and the session says so
    order: str | None = Field(default=None, pattern=ORDER)


@router.post("/routines", response_model=RT.SessionRoutine, status_code=201, responses=E)
async def make_routine(body: RoutineIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.31⟩ §50 «کارمند ۲۴ ساعته»: one Persian sentence becomes a standing routine, `on` at
    once. No card, no step-up: a routine only makes work for a role of the company (inside its
    month envelope) or tells the owner something, on a schedule, and one tap switches it off
    (`POST /automations/{ref}/state`). `company`: whose routine it is (left out with `order`:
    the session's company; left out without: the holding's). `422` when the sentence does not
    compile to a rule, or the rule is more than a routine (an event or a number as its
    trigger, a line, an ad, an n8n flow: that is an automation the owner seals, §31.7); nothing
    is made then. Requires `Idempotency-Key`."""
    company = body.company
    order = None
    if body.order is not None:
        async with ctx.tx() as tx:
            rep = await OR.ensure(tx, body.order)
            row = await OR.load_order(tx, body.order) if rep is not None else None
            if rep is None or row is None:
                raise ApiError(404, "not_found", f"order {body.order}")
            order = body.order
            if company is None:
                code = await tx.scalar(
                    """SELECT c.code FROM work.work w JOIN core.companies c ON c.id = w.company_id
                       WHERE w.ref = ANY(:refs) AND c.kind <> 'holding'
                       ORDER BY w.created_at LIMIT 1""",
                    refs=OR.root_refs(row),
                )
                company = str(code) if code else None
    compiled = await AU.compile_sentence(ctx.hub, body.sentence_fa, company)
    if compiled.rule is None:
        why = compiled.refused_fa[0] if compiled.refused_fa else "این جمله به قاعده تبدیل نشد."
        raise ApiError(422, "validation_failed", fields={"sentence_fa": why[:200]}, message_fa=why)
    if not RT.is_routine(compiled.rule):
        raise ApiError(
            422, "validation_failed", fields={"sentence_fa": "not a plain routine"},
            message_fa=RT.NOT_ROUTINE_FA,
        )  # fmt: skip
    sentence = scrub(" ".join(body.sentence_fa.split()))
    titles = AU.role_titles(ctx.hub.charters)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        co = await ctx.hub.companies.by_code(company) if company else holding
        row = await RT.make(
            tx, company_id=co.id, scoped=company is not None, sentence=sentence,
            rule=compiled.rule, order=order, by=ctx.who,
        )  # fmt: skip
        await ctx.audit(
            tx,
            company_id=co.id,
            action="automation.routine",
            action_class="A2",
            target_kind="automation",
            target_ref=row["ref"],
            summary="a standing routine from the owner's own sentence"
            + (f" in {order}" if order else ""),
        )
        out = RT.view(row, company, titles, await owner_tz(tx))
        await RT.say(
            tx, order, RT.MADE_FA.format(what=f"{out.when_fa}، {out.preview_fa}"), owner=True
        )
        await ctx.emit(tx, co.code, "automation.run", row["ref"], {"state": "on", "routine": True})
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/routines", response_model=list[RT.SessionRoutine], responses=E)
async def list_routines(
    company: str | None = Query(default=None, pattern=CODE),
    order: str | None = Query(default=None, pattern=ORDER),
    ctx: Ctx = Depends(owner_ctx),
) -> list[RT.SessionRoutine]:
    """⟨1.31⟩ §50 The standing routines made from one sentence, newest first: each with its
    schedule and what a run does in plain Persian, its next run, and its switch (`state`)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT a.*, c.code AS company_code FROM growth.automations a
               JOIN core.companies c ON c.id = a.company_id
               WHERE a.source ->> 'routine' = 'true'
                 AND (CAST(:co AS text) IS NULL OR (a.scope = 'company' AND c.code = :co))
                 AND (CAST(:o AS text) IS NULL OR a.source ->> 'order' = :o)
               ORDER BY a.created_at DESC LIMIT 200""",
            co=company,
            o=order,
        )
        tz = await owner_tz(tx)
    titles = AU.role_titles(ctx.hub.charters)
    return [RT.view(dict(r), r["company_code"], titles, tz) for r in rows]
