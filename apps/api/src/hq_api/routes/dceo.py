"""The digital CEO, prediction only (prompt 12 §13, contract §21.10), owner only.

    GET  /digital-ceo                          {stats: [30d, 90d, all], settings, hidden}
    GET  /digital-ceo/predictions              ?correct&kind&cursor; decided cards only
                                               (all while reveal is "before")
    GET  /digital-ceo/principles               the current version of each
    POST /digital-ceo/principles               the owner adds one (active)
    PUT  /digital-ceo/principles/{ref}         edit or retire = a new version · If-Match
    POST /digital-ceo/principles/{ref}/accept  a proposed principle becomes active
Stream: dceo.scored on topic `dceo` (after the decision only).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from hq_api import pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import dceo as DC
from hq_api.errors import ApiError, responses
from hq_api.http import if_match
from hq_api.schemas import Page

router = APIRouter(tags=["digital-ceo"])
E = responses(401, 404, 409, 422, 428)
REF = r"^DP-[0-9]{3,9}$"


@router.get("/digital-ceo", response_model=DC.DigitalCeo, responses=E)
async def overview(ctx: Ctx = Depends(owner_ctx)) -> DC.DigitalCeo:
    """Accuracy (clean predictions only), the baseline against the model,
    Brier, calibration in 0.1 buckets, by kind; the settings; how many hidden
    predictions exist (the `before` setting warns below 30)."""
    async with ctx.tx() as tx:
        return await DC.overview(tx)


@router.get("/digital-ceo/predictions", response_model=Page[DC.Prediction], responses=E)
async def predictions(
    correct: bool | None = None,
    kind: str | None = Query(default=None, pattern=r"^[a-z_]{2,40}$"),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[DC.Prediction]:
    """The predictions of decided cards (every one while reveal is `before`),
    newest first; `?correct&kind&cursor`."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        before = (await DC.settings(tx)).get("reveal") == "before"
        rows = await tx.all(
            """SELECT p.* FROM dceo.predictions p
               WHERE (p.actual IS NOT NULL OR :before)
                 AND (CAST(:c AS boolean) IS NULL OR p.correct = :c)
                 AND (CAST(:k AS text) IS NULL OR p.decision_kind = :k)
                 AND (CAST(:t AS timestamptz) IS NULL
                      OR (p.made_at, p.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
               ORDER BY p.made_at DESC, p.id DESC LIMIT :lim""",
            before=before,
            c=correct,
            k=kind,
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("made_at", "id"))
    return Page(items=[DC.render_prediction(r) for r in items], next_cursor=nxt)


@router.get("/digital-ceo/principles", response_model=list[DC.Principle], responses=E)
async def principles(
    status: Literal["proposed", "active", "retired"] | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[DC.Principle]:
    """The current version of each principle (`?status`)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT * FROM dceo.current_principles
               WHERE (CAST(:s AS text) IS NULL OR status = :s) ORDER BY ref""",
            s=status,
        )
    return [DC.render_principle(r) for r in rows]


@router.post("/digital-ceo/principles", response_model=DC.Principle, status_code=201, responses=E)
async def add_principle(
    body: DC.PrincipleIn, response: Response, ctx: Ctx = Depends(owner_ctx)
) -> DC.Principle:
    """The owner adds a principle (active at once, version 1)."""
    async with ctx.tx() as tx:
        row = await DC.add_principle(
            tx, ctx.who, text_fa=body.text_fa,
            sources=[s.model_dump() for s in body.sources], status="active", edited=True,
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="dceo.principle_add",
            target_kind="principle", target_ref=row["ref"], data={},
        )  # fmt: skip
    response.headers["ETag"] = f'"{row["version"]}"'
    return DC.render_principle(row)


@router.put("/digital-ceo/principles/{ref}", response_model=DC.Principle, responses=E)
async def edit_principle(
    body: DC.PrincipleEdit,
    request: Request,
    response: Response,
    ref: str = Path(pattern=REF),
    ctx: Ctx = Depends(owner_ctx),
) -> DC.Principle:
    """Edit or retire: a new version (the old ones stay visible). `If-Match: <version>`."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        row = await DC.edit_principle(tx, ctx.who, ref, body, expected)
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="dceo.principle_edit",
            target_kind="principle", target_ref=ref, data={"status": body.status},
        )  # fmt: skip
    response.headers["ETag"] = f'"{row["version"]}"'
    return DC.render_principle(row)


@router.post("/digital-ceo/principles/{ref}/accept", response_model=DC.Principle, responses=E)
async def accept_principle(
    response: Response, ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> DC.Principle:
    """A proposed principle becomes active (a new version)."""
    async with ctx.tx() as tx:
        row = await DC.accept_principle(tx, ctx.who, ref)
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="dceo.principle_accept",
            target_kind="principle", target_ref=ref, data={},
        )  # fmt: skip
    response.headers["ETag"] = f'"{row["version"]}"'
    return DC.render_principle(row)


@router.get(
    "/digital-ceo/principles/{ref}/versions", response_model=list[DC.Principle], responses=E
)
async def principle_versions(
    ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> list[DC.Principle]:
    """Every version of one principle (the owner always sees what is recorded)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            "SELECT * FROM dceo.principles WHERE ref = :r ORDER BY version DESC", r=ref
        )
    if not rows:
        raise ApiError(404, "not_found", "no such principle")
    return [DC.render_principle(r) for r in rows]
