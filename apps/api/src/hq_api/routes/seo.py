"""⟨1.13⟩ Prompt 22 part 3 (contract §31.4): SEO rank and competitors. Owner only.

GET/POST/PUT/DELETE /companies/{code}/keywords[/{id}]      the keywords we watch
GET  /companies/{code}/ranks?days                          daily positions (Search Console;
                                                           SearXNG ones marked approximate)
GET/POST/PUT/DELETE /companies/{code}/competitors[/{id}]   the competitors we watch
GET  /companies/{code}/competitors/daily?days              their public daily figures

The daily read is the worker's (domain/seo.py); no model reads a figure.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import seo as S
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["growth"])
E = responses(401, 403, 404, 409, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
MAX_PER_COMPANY = 200


def _patch(body: Any, allowed: tuple[str, ...]) -> dict[str, Any]:
    got = body.model_dump(exclude_unset=True)
    return {k: v for k, v in got.items() if k in allowed}


async def _update(
    tx: Any, table: str, rid: UUID, company_id: UUID, fields: dict[str, Any]
) -> dict[str, Any]:
    if not fields:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"})
    # the column names come from the pydantic models above, never from the request
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await tx.first(
        f"UPDATE growth.{table} SET {sets}, updated_at = now() WHERE id = :id AND company_id = :co RETURNING *",  # noqa: S608
        id=rid,
        co=company_id,
        **fields,
    )
    if row is None:
        raise ApiError(404, "not_found")
    return dict(row)


# -------------------------------------------------------------- keywords --
@router.get("/companies/{code}/keywords", response_model=list[S.Keyword], responses=E)
async def list_company_keywords(
    code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[S.Keyword]:
    """The company's keywords with their latest known position (Search Console first)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await S.keywords_of(tx, company)


@router.post("/companies/{code}/keywords", response_model=S.Keyword, status_code=201, responses=E)
async def create_company_keyword(
    body: S.KeywordIn, code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> S.Keyword:
    """A keyword to watch for a site (the phrase as people type it)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        if (
            int(
                await tx.scalar(
                    "SELECT count(*) FROM growth.keywords WHERE company_id = :c", c=company.id
                )
                or 0
            )
            >= MAX_PER_COMPANY
        ):
            raise ApiError(422, "validation_failed", fields={"phrase": "too many keywords"})
        exists = await tx.scalar(
            "SELECT 1 FROM growth.keywords WHERE company_id = :c AND site = :s AND phrase = :p",
            c=company.id,
            s=body.site.lower(),
            p=body.phrase.strip(),
        )
        if exists:
            raise ApiError(409, "version_conflict", "this keyword exists already")
        row = await tx.one(
            """INSERT INTO growth.keywords (company_id, phrase, site, target_url, state)
               VALUES (:c, :p, :s, :u, :st) RETURNING *""",
            c=company.id,
            p=body.phrase.strip(),
            s=body.site.lower(),
            u=body.target_url,
            st=body.state,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="keyword.create",
            action_class="A1",
            target_kind="keyword",
            target_ref=str(row["id"]),
        )
        return S.keyword_out(code, dict(row))


@router.put("/companies/{code}/keywords/{keyword_id}", response_model=S.Keyword, responses=E)
async def update_company_keyword(
    keyword_id: UUID,
    body: S.KeywordPut,
    code: str = Path(pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> S.Keyword:
    """Change the phrase, the site, the target page or pause it."""
    company = await ctx.hub.companies.by_code(code)
    fields = _patch(body, ("phrase", "site", "target_url", "state"))
    if fields.get("site"):
        fields["site"] = fields["site"].lower()
    async with ctx.tx() as tx:
        row = await _update(tx, "keywords", keyword_id, company.id, fields)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="keyword.update",
            action_class="A1",
            target_kind="keyword",
            target_ref=str(keyword_id),
        )
        return S.keyword_out(code, row)


@router.delete("/companies/{code}/keywords/{keyword_id}", status_code=204, responses=E)
async def delete_company_keyword(
    keyword_id: UUID, code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> Response:
    """Stop watching a keyword; its past positions go with it."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        n = await tx.exec(
            "DELETE FROM growth.keywords WHERE id = :id AND company_id = :c",
            id=keyword_id,
            c=company.id,
        )
        if not n:
            raise ApiError(404, "not_found")
        await ctx.audit(
            tx,
            company_id=company.id,
            action="keyword.delete",
            action_class="A1",
            target_kind="keyword",
            target_ref=str(keyword_id),
        )
    return Response(status_code=204)


@router.get("/companies/{code}/ranks", response_model=list[S.RankPoint], responses=E)
async def list_company_ranks(
    code: str = Path(pattern=CODE),
    days: int = Query(default=30, ge=1, le=365),
    ctx: Ctx = Depends(owner_ctx),
) -> list[S.RankPoint]:
    """Daily positions of the last `days`, newest first. A SearXNG position is
    `approximate` with a Persian note; a missing position (null) means the site was
    not on the page, never zero."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await S.ranks_of(tx, company, days)


# ----------------------------------------------------------- competitors --
@router.get(
    "/companies/{code}/competitors/daily", response_model=list[S.CompetitorPoint], responses=E
)
async def list_company_competitor_daily(
    code: str = Path(pattern=CODE),
    days: int = Query(default=30, ge=1, le=365),
    ctx: Ctx = Depends(owner_ctx),
) -> list[S.CompetitorPoint]:
    """The competitors' public daily figures (pages, new_pages, subscribers, views,
    videos, members, serp_visible, serp_best), each with its source."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await S.competitor_points(tx, company, days)


@router.get("/companies/{code}/competitors", response_model=list[S.Competitor], responses=E)
async def list_company_competitors(
    code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[S.Competitor]:
    """The competitors the company watches."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        rows = await tx.all(
            "SELECT * FROM growth.competitors WHERE company_id = :c ORDER BY created_at",
            c=company.id,
        )
    return [S.competitor_out(code, dict(r)) for r in rows]


@router.post(
    "/companies/{code}/competitors", response_model=S.Competitor, status_code=201, responses=E
)
async def create_company_competitor(
    body: S.CompetitorIn, code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> S.Competitor:
    """A competitor with whichever public handles we know: site (sitemap), YouTube
    channel id, Telegram channel, Instagram (named only; no free API reads it)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        if (
            int(
                await tx.scalar(
                    "SELECT count(*) FROM growth.competitors WHERE company_id = :c", c=company.id
                )
                or 0
            )
            >= MAX_PER_COMPANY
        ):
            raise ApiError(422, "validation_failed", fields={"name_fa": "too many competitors"})
        row = await tx.one(
            """INSERT INTO growth.competitors (company_id, name_fa, site, instagram, youtube, telegram, state)
               VALUES (:c, :n, :s, :i, :y, :t, :st) RETURNING *""",
            c=company.id,
            n=body.name_fa.strip(),
            s=body.site.lower() if body.site else None,
            i=body.instagram,
            y=body.youtube,
            t=body.telegram,
            st=body.state,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="competitor.create",
            action_class="A1",
            target_kind="competitor",
            target_ref=str(row["id"]),
        )
        return S.competitor_out(code, dict(row))


@router.put(
    "/companies/{code}/competitors/{competitor_id}", response_model=S.Competitor, responses=E
)
async def update_company_competitor(
    competitor_id: UUID,
    body: S.CompetitorPut,
    code: str = Path(pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> S.Competitor:
    """Change a competitor's handles or pause it."""
    company = await ctx.hub.companies.by_code(code)
    fields = _patch(body, ("name_fa", "site", "instagram", "youtube", "telegram", "state"))
    if fields.get("site"):
        fields["site"] = fields["site"].lower()
    async with ctx.tx() as tx:
        row = await _update(tx, "competitors", competitor_id, company.id, fields)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="competitor.update",
            action_class="A1",
            target_kind="competitor",
            target_ref=str(competitor_id),
        )
        return S.competitor_out(code, row)


@router.delete("/companies/{code}/competitors/{competitor_id}", status_code=204, responses=E)
async def delete_company_competitor(
    competitor_id: UUID, code: str = Path(pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> Response:
    """Stop watching a competitor; its past figures go with it."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        n = await tx.exec(
            "DELETE FROM growth.competitors WHERE id = :id AND company_id = :c",
            id=competitor_id,
            c=company.id,
        )
        if not n:
            raise ApiError(404, "not_found")
        await ctx.audit(
            tx,
            company_id=company.id,
            action="competitor.delete",
            action_class="A1",
            target_kind="competitor",
            target_ref=str(competitor_id),
        )
    return Response(status_code=204)
