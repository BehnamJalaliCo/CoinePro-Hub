"""The council v2's owner routes (contract §29.8): «اجرا کن» makes an order
of the captain's plan; the fact pack the members read."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
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
    Requires `Idempotency-Key`."""
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
