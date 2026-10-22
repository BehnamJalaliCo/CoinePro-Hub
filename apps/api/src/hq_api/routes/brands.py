"""The company's brand and seal (prompt 9.1 §3, contract §18.14). Owner only:
an agent token is 403 on every route here.

POST /companies/{code}/brand                      a new version from a logo (202)
GET  /companies/{code}/brand                      the active and the newest proposed
GET  /companies/{code}/brand/versions             every version, newest first
POST /companies/{code}/brand/{version}/retrace    the same file, other options (202)
POST /companies/{code}/brand/{version}/activate   🔏 company.brand, target = digest
GET  /brands                                      every active brand, ETag / 304
The tracing is code (no model) in the worker's sandboxed child; nothing here
calls a model or anything outside the hub.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import brands as BR
from hq_api.errors import responses
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["brand"])
E = responses(401, 403, 404, 409, 422)


class BrandOptionsIn(Model):
    colors: int | None = Field(default=None, ge=1, le=4)
    detail: int = Field(default=3, ge=1, le=5)


class BrandIn(Model):
    file_id: UUID
    part: Literal["mark", "wordmark"] = "mark"
    options: BrandOptionsIn | None = None


class RetraceIn(Model):
    options: BrandOptionsIn = Field(default_factory=BrandOptionsIn)


class ActivateIn(Model):
    """Empty: the seal is the step-up on the version's digest."""


def _opts(o: BrandOptionsIn | None) -> dict[str, Any]:
    o = o or BrandOptionsIn()
    return {"colors": o.colors, "detail": o.detail}


async def _start(ctx: Ctx, brand_id: UUID) -> None:
    await workflows_client.brand_trace(ctx.hub, str(brand_id))


async def _record(
    ctx: Ctx,
    tx: Any,
    r: dict[str, Any],
    action: str,
    summary: str,
    *,
    action_class: str = "A1",
    step_up: bool = False,
    kind: str = "edit",
) -> None:
    """One audit row and the owner's interaction for one change."""
    ref = f"{r['company_code']}@{r['version']}"
    await ctx.audit(
        tx,
        company_id=r["company_id"],
        action=action,
        action_class=action_class,
        target_kind="brand",
        target_ref=ref,
        summary=summary[:300],
        step_up=step_up,
    )
    await ctx.interaction(
        tx,
        company_id=r["company_id"],
        kind=kind,
        action=action,
        target_kind="brand",
        target_ref=ref,
        data={"version": r["version"], "part": r["part"]},
    )


@router.post(
    "/companies/{code}/brand", response_model=BR.CompanyBrand, status_code=202, responses=E
)
async def upload_brand(
    code: str, body: BrandIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new version from the owner's logo (`file_id` from POST /files: PNG,
    best with transparency; WebP or JPEG with the warning «بدون شفافیت»), the
    other part carried over from the active version. `processing` until the
    media worker has traced it (then `brand.updated`). Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await BR.upload(tx, ctx.who, code, body.file_id, body.part, _opts(body.options))
        await _record(ctx, tx, r, "brand.upload", f"{body.part} from file {body.file_id}")
        out = BR.render(r)
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    await _start(ctx, r["id"])
    return out


@router.get("/companies/{code}/brand", response_model=BR.CompanyBrandView, responses=E)
async def get_brand(code: str, ctx: Ctx = Depends(owner_ctx)) -> BR.CompanyBrandView:
    """The active version and, if any, the newest `proposed` one."""
    async with ctx.tx() as tx:
        co = await BR.company_row(tx, code)
        return await BR.view(tx, co["id"])


@router.get("/companies/{code}/brand/versions", response_model=Page[BR.CompanyBrand], responses=E)
async def brand_versions(
    code: str,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = Query(default=None, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[BR.CompanyBrand]:
    """Every version, newest first."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        co = await BR.company_row(tx, code)
        rows = await tx.all(
            BR.BRAND_SQL
            + """ WHERE b.company_id = :co AND (CAST(:after AS int) IS NULL OR b.version < :after)
                  ORDER BY b.version DESC LIMIT :n""",
            co=co["id"],
            after=int(after[0]) if after else None,
            n=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("version",))
    return Page[BR.CompanyBrand](items=[BR.render(r) for r in items], next_cursor=nxt)


@router.post(
    "/companies/{code}/brand/{version}/retrace",
    response_model=BR.CompanyBrand,
    status_code=202,
    responses=E,
)
async def retrace_brand(
    code: str, version: int, body: RetraceIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new `processing` version from the same file with other options.
    Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await BR.retrace(tx, ctx.who, code, version, _opts(body.options))
        await _record(ctx, tx, r, "brand.retrace", f"from version {version}: {_opts(body.options)}")
        out = BR.render(r)
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    await _start(ctx, r["id"])
    return out


@router.post(
    "/companies/{code}/brand/{version}/activate", response_model=BR.CompanyBrand, responses=E
)
async def activate_brand(
    code: str,
    version: int,
    request: Request,
    body: ActivateIn | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> BR.CompanyBrand:
    """🔏 step-up `company.brand`, target = the version's `digest`, which the
    server recomputes from the stored version: a version that changed after
    the owner saw it is not sealed. The previous active version is retired."""
    async with ctx.tx() as tx:
        co = await BR.company_row(tx, code)
        BR.no_holding(co)
        r = await BR.load(tx, co["id"], version, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "company.brand", BR.digest_of(r))
        out, prev = await BR.activate(tx, ctx.who, co, r, step_up_id=su)
        await _record(
            ctx,
            tx,
            out,
            "brand.activate",
            f"sealed {BR.digest_of(out)[:12]}" + (f", version {prev} retired" if prev else ""),
            action_class="A2",
            step_up=True,
            kind="decision",
        )
        return BR.render(out)


@router.get(
    "/brands", response_model=BR.Brands, responses={**E, 304: {"description": "Not modified"}}
)
async def all_brands(request: Request, response: Response, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Every active brand in one response; the clients draw every company's
    mark and seal from it. `ETag`; `If-None-Match` -> `304`."""
    async with ctx.tx() as tx:
        out = await BR.brands(tx)
    headers = {"ETag": out.etag, "Cache-Control": "private, no-cache"}
    wanted = request.headers.get("if-none-match") or ""
    tags = {t.strip().removeprefix("W/") for t in wanted.split(",") if t.strip()}
    if out.etag in tags or "*" in tags:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return out
