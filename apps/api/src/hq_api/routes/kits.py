"""A ready company with one order: company kits (contract §31.2). Owner only.

GET  /kits                          every kit (data: seed/kits/*.yaml)
GET  /kits/{key}                    what one kit makes
POST /companies/from-kit/preview    {kit, code, name_fa, name_en}: what would
                                    be created; nothing is written
POST /companies/from-kit            🔏 company.create, target = the SHA-256 of
                                    the body: the company with its team,
                                    group memberships, KPIs, connections
                                    (`not_connected`) and its lines as drafts
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import kits as K
from hq_api.domain import order_report as OR
from hq_api.domain import org
from hq_api.errors import ApiError, responses
from hq_api.routes.org import COMPANY_SQL, Company, _company
from hq_api.schemas import CODE, Model
from hq_api.security import stepup

router = APIRouter(tags=["kits"])
E = responses(401, 403, 404, 409, 422, 428)
KIT_KEY = r"^[a-z][a-z0-9_]{1,40}$"


class KitCompanyIn(Model):
    kit: str = Field(pattern=KIT_KEY)
    code: str = Field(pattern=CODE)
    name_fa: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    color_index: int | None = Field(default=None, ge=1, le=8)
    # the order (F-0001) whose kit card this seals: its report ends as delivered
    order: str | None = Field(default=None, pattern=r"^F-[0-9]{4,}$")


class KitPreview(BaseModel):
    """What POST /companies/from-kit would make now. Nothing was written."""

    kit: K.KitSummary
    code: str
    name_fa: str
    name_en: str
    code_free: bool
    problems: list[str] = Field(default_factory=list)
    nothing_written: bool = True


class KitCreated(BaseModel):
    company: Company
    kit: str
    team: dict[str, int] = Field(description="departments, employees (positions), threads added")
    groups: list[str] = Field(description="the working groups it joined")
    kpis: int
    connections: int = Field(description="created `not_connected`")
    lines: list[K.KitLine] = Field(description="its lines as drafts")
    lines_pending: list[K.KitLine] = Field(
        default_factory=list,
        description="lines not made yet (the engine is absent, or one refused)",
    )
    groups_pending: list[str] = Field(default_factory=list)
    todo_fa: list[str] = Field(description="what the owner still has to connect or do")


@router.get("/kits", response_model=list[K.KitSummary], responses=E)
async def list_kits(ctx: Ctx = Depends(owner_ctx)) -> list[K.KitSummary]:
    """Every company kit: its team template, groups, lines, KPIs, connections."""
    return [K.describe(k) for k in sorted(K.kits())]


@router.get("/kits/{key}", response_model=K.KitSummary, responses=E)
async def get_kit(key: str, ctx: Ctx = Depends(owner_ctx)) -> K.KitSummary:
    """One kit and what the owner still has to do after a company is made from it."""
    return K.describe(key)


async def _problems(ctx: Ctx, body: KitCompanyIn) -> list[str]:
    async with ctx.tx() as tx:
        taken = await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=body.code)
    return ["این کد را شرکت دیگری دارد"] if taken else []


@router.post("/companies/from-kit/preview", response_model=KitPreview, responses=E)
async def preview_company_from_kit(body: KitCompanyIn, ctx: Ctx = Depends(owner_ctx)) -> KitPreview:
    """What a company made from the kit would get, and whether the code is free.
    Nothing is written."""
    summary = K.describe(body.kit)
    problems = await _problems(ctx, body)
    return KitPreview(
        kit=summary,
        code=body.code,
        name_fa=body.name_fa,
        name_en=body.name_en,
        code_free=not problems,
        problems=problems,
    )


@router.post("/companies/from-kit", response_model=KitCreated, status_code=201, responses=E)
async def create_company_from_kit(
    body: KitCompanyIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> KitCreated:
    """🔏 step-up `company.create`, target = the SHA-256 of the exact body.
    One transaction: the company and its team (the template's departments and
    leadership, asleep), its group memberships, its KPIs, its connections
    (`not_connected`) and its lines as drafts. No server is made (founding is
    separate). While the lines engine is not on the hub, `lines_pending` lists
    the lines instead. `todo_fa`: what the owner still has to connect."""
    kit = K.kit(body.kit)
    await ctx.hub.policy.require(
        "kits",
        {"principal": ctx.who.opa(), "op": "company.from_kit", "target": {"kit": body.kit}},
    )
    async with ctx.tx() as tx:
        await stepup.consume(
            tx, request, ctx.who, "company.create", await stepup.body_target(request)
        )
        if await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=body.code):
            raise ApiError(409, "validation_failed", fields={"code": "already exists"})
        if body.order and not await OR.kit_order_open(tx, body.order, body.kit):
            raise ApiError(
                409, "validation_failed", fields={"order": "not an open kit order of this kit"}
            )
        company_id = await org.insert_company(
            tx,
            code=body.code,
            name_fa=body.name_fa,
            name_en=body.name_en,
            color_index=body.color_index,
            template=kit["team_template"],
        )
        await tx.rescope([*await ctx.scope(), company_id])
        made = await K.create(tx, company_id, body.code, body.kit)
        await ctx.audit(
            tx,
            company_id=company_id,
            action="company.create_from_kit",
            action_class="A2",
            target_kind="company",
            target_ref=body.code,
            summary=(
                f"kit {body.kit}: team {made['team']}, groups {made['groups']}, "
                f"kpis {made['kpis']}, connections {made['connections']}, "
                f"lines {len(made['lines'])} (pending {len(made.get('lines_pending', []))})"
            ),
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=company_id,
            kind="edit",
            action="company.create_from_kit",
            target_kind="company",
            target_ref=body.code,
            data={"kit": body.kit, "order": body.order},
        )
        await ctx.emit(tx, body.code, "control.changed", body.code, {"change": "company.created"})
        if body.order:
            await OR.kit_sealed(tx, body.order, body.code, body.name_fa)
        company = _company(await tx.one(COMPANY_SQL + " WHERE c.id = :id", id=company_id))
    ctx.hub.companies.invalidate()
    return _answer(company, body.kit, made)


def _answer(company: Company, kit: str, made: dict[str, Any]) -> KitCreated:
    return KitCreated(
        company=company,
        kit=kit,
        team=made["team"],
        groups=made["groups"],
        kpis=made["kpis"],
        connections=made["connections"],
        lines=[K.KitLine(**x) for x in made["lines"]],
        lines_pending=[K.KitLine(**x) for x in made.get("lines_pending", [])],
        groups_pending=made.get("groups_pending", []),
        todo_fa=made["todo_fa"],
    )
