"""The council v2's owner routes (contract §29.8): «اجرا کن» makes an order
of the captain's plan; the fact pack the members read."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import dispatch as D
from hq_api.domain import orders as O
from hq_api.domain import players as PL
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.routes.orders import OrderIn, OrderOut, place_order

router = APIRouter(tags=["work"])
E = responses(401, 403, 404, 409, 422)


class FactPack(BaseModel):
    """§29.8 `FactPack`: the hub's own figures (no secret, no personal data)."""

    ref: str
    work_ref: str
    company: str
    at: str
    figures: list[dict[str, Any]]
    recent_posts: list[dict[str, Any]]
    notes_fa: str


@router.post("/work/{id}/council/run", response_model=OrderOut, status_code=201, responses=E)
async def run_plan(
    id: UUID, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.11⟩ §29.8 «اجرا کن»: the captain's plan becomes an order (§29.4) of
    the council's company (its CEO splits it), single mode, the plan's
    budget. Once per council (409 when it already ran, or has no plan yet).
    Requires `Idempotency-Key`. ⟨1.17⟩ §35.1 a council held inside a session (its work
    belongs to an owner's open order) continues that same order: the plan is the owner's
    word on it (a reply), never a new F-ref."""
    async with ctx.tx() as tx:
        c = await PL.council_of(tx, id)
        if c is None:
            raise ApiError(404, "not_found", "this work has no council")
        if c.get("order_ref"):
            raise ApiError(409, "validation_failed", "the plan was already sent as an order")
        if c["state"] != "done" or not c.get("plan_md"):
            raise ApiError(409, "validation_failed", "the council has no plan yet")
        w = await W.load(tx, id)
        sc = await D.context(tx, c["plan_md"])
        same = await _same_order(ctx, tx, request, w, c)
        if same is not None:
            return same
    d = sc.directory
    company = w["company"]
    if d["companies"].get(company, {}).get("holding"):
        named = D.companies_in_order(O.normalise(c["plan_md"]), d)
        company = next((x for x in named if not d["companies"][x]["holding"]), "")
    if not company or not d["companies"][company]["ceo"]:
        raise ApiError(409, "validation_failed", "the plan names no company with a CEO to run it")
    kind, count, _ = D.output_of(O.normalise(c["plan_md"]))
    output = "plan" if kind in ("other", "report", "plan") else kind
    route = D.Route(
        companies=[company],
        department=None,
        output_kind=output,
        count=count,
        budget_tokens=D.budget_of(output, count),
        mode="single",
        player="auto",
        kind="work",
        why_fa="برنامه‌ی شورا؛ مدیرعامل شرکت آن را میان بخش‌ها تقسیم میکند",
        confidence=1.0,
    )
    text = f"اجرای برنامه‌ی شورا: {w['title']}\n\n{c['plan_md']}"[:10000]
    out = await place_order(
        ctx, request, background, OrderIn(text=text, source="text", route=route), remember=False
    )
    if isinstance(out, Response):  # a replay: the order was made, the council may lack it
        ref = json.loads(bytes(out.body)).get("ref")
        if not ref:
            return out
    else:
        ref = out["ref"] if isinstance(out, dict) else out.ref
    async with ctx.tx() as tx:
        await tx.exec(
            """UPDATE work.councils SET order_ref = :r, updated_at = now()
               WHERE work_id = :w AND order_ref IS NULL""",
            r=ref,
            w=id,
        )
        fresh = await PL.council_of(tx, id)
        if fresh is not None:
            await PL._emit(tx, w["company"], fresh)
    return out


class _NoOpenWork(Exception):
    """OT.reply refused the word (nothing open or delivered on the order)."""


async def _same_order(
    ctx: Ctx, tx: Any, request: Request, w: dict[str, Any], c: dict[str, Any]
) -> OrderOut | None:
    """⟨1.17⟩ §35.1 the council's work belongs to an open order: «اجرا کن» is the owner's word
    on it («اجرا کن: …» with the plan), the holder runs again at once; the council is linked to
    that order. None when the work is in no open order (a new order is made as before)."""
    from hq_api import idempotency
    from hq_api.domain import order_report as OR
    from hq_api.domain import order_turns as OT
    from hq_api.routes.orders import _record

    ref = await OR.order_of_work(tx, w["id"])
    if ref is None:
        return None
    rep = await OR.ensure(tx, ref)
    if rep is None or rep["ended_at"] is not None:
        return None
    text = f"اجرا کن: برنامه‌ی شورا را اجرا کن.\n\n{c['plan_md']}"[:2000]
    try:
        # in a savepoint: when the order has no open work, the claim goes back with the
        # reply's writes, so place_order can claim the same key for the new order
        async with tx.conn.begin_nested():
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay  # type: ignore[return-value]
            try:
                out = await OT.reply(tx, ref, text)
            except ApiError as exc:
                raise _NoOpenWork from exc
    except _NoOpenWork:
        return None  # no open work on the order: a new order as before
    await OT.to_talk_owner(tx, rep, text)
    await tx.exec(
        """UPDATE work.councils SET order_ref = :r, updated_at = now()
           WHERE work_id = :w AND order_ref IS NULL""",
        r=ref,
        w=w["id"],
    )
    woken = ", ".join(out["woken"]) or "nothing"
    await ctx.audit(tx, company_id=rep["company_id"], action="order.reply", action_class="A1",
                    target_kind="order", target_ref=ref,
                    summary=f"the council's plan of {w['ref']}; woken: {woken}")  # fmt: skip
    await OR.refresh(tx, ref)
    fresh = await PL.council_of(tx, w["id"])
    if fresh is not None:
        await PL._emit(tx, w["company"], fresh)
    row = await tx.one("SELECT * FROM owner.orders WHERE ref = :r", r=ref)
    rec = _record({**dict(row), "routes": OR._j(row["routes"]), "route": OR._j(row["route"])})
    shape = rec.model_dump(include=set(OrderOut.model_fields))
    shape["talk_ref"] = rep.get("conversation_ref")
    result = OrderOut(**shape)
    if idem:
        await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.get("/fact-packs/{ref}", response_model=FactPack, responses=E)
async def fact_pack(ref: str, ctx: Ctx = Depends(owner_ctx)) -> FactPack:
    """⟨1.11⟩ §29.8 the fact pack a council's members read (under «جزئیات»)."""
    async with ctx.tx() as tx:
        c = await tx.first(PL.COUNCIL_SQL + " WHERE k.fact_pack_ref = :r", r=ref)
    if c is None or not c.get("fact_pack"):
        raise ApiError(404, "not_found", "no such fact pack")
    pack = dict(c["fact_pack"])
    return FactPack(
        ref=ref,
        work_ref=c["work_ref"],
        company=str(pack.get("company") or ""),
        at=str(pack.get("at") or ""),
        figures=list(pack.get("figures") or []),
        recent_posts=list(pack.get("recent_posts") or []),
        notes_fa=str(pack.get("notes_fa") or ""),
    )
