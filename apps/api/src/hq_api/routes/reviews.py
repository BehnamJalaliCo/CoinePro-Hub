"""The weekly review with the advisor (prompt 12 §3, contract §21.3), owner only.

    GET   /reviews/weekly                      newest first (?cursor)
    GET   /reviews/weekly/current              this week's (404 while there is none)
    POST  /reviews/weekly/{ref}/start          -> the whole WeeklyReview
    PATCH /reviews/weekly/{ref}/items/{n}      {status, owner_note?} · If-Match
    POST  /reviews/weekly/{ref}/finish         the minutes as a deliverable O-… by HQ-ADV
Stream: review.updated on topic `reviews`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from hq_api import pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import reviews as RV
from hq_api.errors import ApiError, responses
from hq_api.http import if_match
from hq_api.schemas import Page

router = APIRouter(tags=["reviews"])
E = responses(401, 404, 409, 422, 428)
REF = r"^WR-[0-9]{4,9}$"


def _etag(response: Response, row: dict[str, object]) -> None:
    response.headers["ETag"] = f'"{row["version"]}"'


@router.get("/reviews/weekly", response_model=Page[RV.WeeklyReview], responses=E)
async def list_reviews(
    limit: int = Query(default=20, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[RV.WeeklyReview]:
    """The weekly reviews, newest week first (`?cursor`)."""
    after = pagination.decode(cursor, 1)
    try:
        before = date.fromisoformat(str(after[0])) if after else None
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"cursor": "invalid"}) from exc
    async with ctx.tx() as tx:
        rows = await tx.all(
            RV.REVIEW_SQL
            + """ WHERE (CAST(:a AS date) IS NULL OR r.week < CAST(:a AS date))
                  ORDER BY r.week DESC LIMIT :lim""",
            a=before,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("week",))
    return Page(items=[RV.render(r) for r in items], next_cursor=nxt)


@router.get("/reviews/weekly/current", response_model=RV.WeeklyReview, responses=E)
async def current_review(response: Response, ctx: Ctx = Depends(owner_ctx)) -> RV.WeeklyReview:
    """This week's review (or the newest still open); 404 while there is none."""
    async with ctx.tx() as tx:
        row = await RV.current(tx)
    if row is None:
        raise ApiError(404, "not_found", "no weekly review yet")
    _etag(response, row)
    return RV.render(row)


@router.post("/reviews/weekly/{ref}/start", response_model=RV.WeeklyReview, responses=E)
async def start_review(
    response: Response, ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> RV.WeeklyReview:
    """The owner starts the review (its time runs from now)."""
    async with ctx.tx() as tx:
        row = await RV.start(tx, ctx.who, ref)
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="review.start",
            target_kind="review", target_ref=ref, data={},
        )  # fmt: skip
    _etag(response, row)
    return RV.render(row)


@router.patch("/reviews/weekly/{ref}/items/{n}", response_model=RV.WeeklyReview, responses=E)
async def patch_item(
    body: RV.ItemPatch,
    request: Request,
    response: Response,
    ref: str = Path(pattern=REF),
    n: int = Path(ge=1, le=RV.MAX_ITEMS),
    ctx: Ctx = Depends(owner_ctx),
) -> RV.WeeklyReview:
    """One item: `done`, `deferred` (or `open` again) and a note. `If-Match: <version>`."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        row = await RV.patch_item(tx, ctx.who, ref, n, body, expected)
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="review.item",
            target_kind="review", target_ref=ref,
            data={"n": n, "status": body.status, "note": body.owner_note is not None},
        )  # fmt: skip
    _etag(response, row)
    return RV.render(row)


@router.post("/reviews/weekly/{ref}/finish", response_model=RV.WeeklyReview, responses=E)
async def finish_review(
    response: Response, ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> RV.WeeklyReview:
    """The minutes (the items, their status and notes, the duration) as a
    deliverable O-… by HQ-ADV."""
    async with ctx.tx() as tx:
        row = await RV.finish(tx, ctx.hub, ctx.who, ref)
        await ctx.interaction(
            tx, company_id=row["company_id"], kind="edit", action="review.finish",
            target_kind="review", target_ref=ref,
            data={"minutes": row["minutes_ref"], "duration_s": row["duration_s"]},
        )  # fmt: skip
    _etag(response, row)
    return RV.render(row)
