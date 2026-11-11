"""The owner's links between companies and his canvas (contract §35.6).

GET /links -> Canvas (the nodes and every link); POST /links, PATCH /links/{id} (a link is turned
`off`, never deleted); PUT /canvas/nodes/{code} (where the owner put a company). Every write is
audited (A1) and tells the stream (`links.updated`, topic holding)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from hq_api.companies import Company
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import links as L
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model

router = APIRouter(tags=["links"])
E = responses(401, 404, 409, 422)


class Placed(Model):
    code: str
    x: float
    y: float


@router.get("/links", response_model=L.Canvas, response_model_by_alias=True, responses=E)
async def get_links(ctx: Ctx = Depends(owner_ctx)) -> L.Canvas:
    """The canvas: every active company and the holding as a node (where the owner put it, one
    plain line of what it is doing, the owner's orders open in it) and every link between
    companies, `on` and `off`, with the works open along it."""
    async with ctx.tx() as tx:
        return await L.canvas(tx)


@router.post(
    "/links",
    response_model=L.CompanyLink,
    response_model_by_alias=True,
    status_code=201,
    responses=E,
)
async def add_link(body: L.LinkIn, ctx: Ctx = Depends(owner_ctx)) -> L.CompanyLink:
    """A link `from` -> `to` of a kind (`serves`, `publishes`, `feeds`, `sells`, `supports`) with
    the owner's purpose in one line. The hub is linked to every company already. 409 when the
    same link exists (turn it on again with PATCH)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        link_id = await L.create(tx, holding.id, body)
        await _tell(ctx, tx, holding, link_id, f"link {body.from_} -> {body.to} ({body.kind}) made")
        return await L.get(tx, link_id)


@router.patch(
    "/links/{link_id}", response_model=L.CompanyLink, response_model_by_alias=True, responses=E
)
async def change_link(
    link_id: UUID, body: L.LinkPatch, ctx: Ctx = Depends(owner_ctx)
) -> L.CompanyLink:
    """Changes a link's kind, purpose or state (`off` stops it; nothing is deleted)."""
    if body.kind is None and body.purpose_fa is None and body.state is None:
        raise ApiError(
            422,
            "validation_failed",
            fields={"body": "kind, purpose_fa or state"},
            message_fa="چیزی برای تغییر نفرستادی.",
        )
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        await L.update(tx, link_id, body)
        sent = ", ".join(sorted(body.model_dump(exclude_none=True)))
        await _tell(ctx, tx, holding, link_id, f"link changed: {sent}")
        return await L.get(tx, link_id)


@router.put("/canvas/nodes/{code}", response_model=Placed, responses=E)
async def place_node(code: str, body: L.NodePlace, ctx: Ctx = Depends(owner_ctx)) -> Placed:
    """Where the owner put a company on his canvas (x, y in 0..1)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        await L.place(tx, code, body.x, body.y)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="canvas.place",
            action_class="A1",
            target_kind="canvas_node",
            target_ref=code,
            summary=f"{code} at {body.x:.3f}, {body.y:.3f}",
        )
        await ctx.emit(tx, holding.code, "links.updated", None, {"node": code})
    return Placed(code=code, x=body.x, y=body.y)


async def _tell(ctx: Ctx, tx: Tx, holding: Company, link_id: UUID, summary: str) -> None:
    await ctx.audit(
        tx,
        company_id=holding.id,
        action="link.write",
        action_class="A1",
        target_kind="link",
        target_ref=str(link_id),
        summary=summary[:400],
    )
    await ctx.emit(tx, holding.code, "links.updated", str(link_id), {})
