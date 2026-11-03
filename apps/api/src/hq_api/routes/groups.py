"""⟨1.11⟩ Prompt 21 part 3 (contract §29.9, §29.11): working groups and each
company's readiness for them.

    GET  /groups                              every group (defined in data)
    GET  /groups/{key}
    GET  /groups/{key}/members                each member company and its seats
    PUT  /groups/{key}/members/{code}         {state: on|paused} (the owner's pause)
    GET  /groups/{key}/runs?company&limit&cursor   the routines' history, newest first
    PUT  /groups/{key}/routines/{routine}     {state: on|paused}
    GET  /groups/{key}/kpis?company&days      each member's KPI series (real figures)
    GET  /groups/{key}/experiments?company
    GET  /companies/{code}/readiness?group=content
    POST /companies/{code}/readiness/fix      {group, action, target}: one tap on
                                              a failed check's fix (§29.9)
    /internal/v1/groups/plan                  group.plan (A1): the content lead's
                                              plan of the day, and a suggestion for
                                              the owner's home
    /internal/v1/experiments                  experiment.write (A1): the analyst's
                                              or the lead's experiment of the week
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import groups as GR
from hq_api.domain import home as HM
from hq_api.domain import readiness as RD
from hq_api.domain.connections import owner_today
from hq_api.domain.gov_common import owner_tz
from hq_api.domain.watch import owner_week
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model, Page

router = APIRouter(tags=["groups"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"


class StateIn(Model):
    state: Literal["on", "paused"]


class KpiSeries(BaseModel):
    key: str
    title_fa: str
    unit: str
    source: str
    series: list[dict[str, Any]]


class CompanyKpis(BaseModel):
    code: str
    name_fa: str
    kpis: list[KpiSeries]


class GroupKpis(BaseModel):
    group: str
    days: int
    companies: list[CompanyKpis]


async def _group(ctx: Ctx, tx: Any, key: str, *, lock: bool = False) -> dict[str, Any]:
    return await GR.row_of(tx, key, lock=lock)


@router.get("/groups", response_model=list[GR.Group], responses=E)
async def list_groups(ctx: Ctx = Depends(owner_ctx)) -> list[GR.Group]:
    """§29.11 every working group (seed/groups/*.yaml), its seats, routines
    (with the owner's pauses), KPIs and the connections it needs."""
    async with ctx.tx() as tx:
        return [GR.render(r) for r in await GR.rows(tx)]


@router.get("/groups/{key}", response_model=GR.Group, responses=E)
async def get_group(key: str, ctx: Ctx = Depends(owner_ctx)) -> GR.Group:
    """§29.11 one working group as its data defines it: seats, routines,
    KPIs, the connections it needs, who may join."""
    async with ctx.tx() as tx:
        return GR.render(await _group(ctx, tx, key))


@router.get("/groups/{key}/members", response_model=list[GR.Membership], responses=E)
async def list_members(key: str, ctx: Ctx = Depends(owner_ctx)) -> list[GR.Membership]:
    """Every member company (an eligible company joins by itself) with each
    seat and the employee in it (`null`: empty, filled by automatic hiring)."""
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key)
        g = GR.render(grow)
        return [GR.render_member(m, g) for m in await GR.members(tx, grow["id"])]


@router.put("/groups/{key}/members/{code}", response_model=GR.Membership, responses=E)
async def set_member(
    key: str, code: str, body: StateIn, ctx: Ctx = Depends(owner_ctx)
) -> GR.Membership:
    """The owner pauses (or resumes) a company's membership: a paused member
    runs no routine and asks no hire."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key)
        cur = await GR.member(tx, grow["id"], company.id, lock=True)
        if cur["state"] != body.state:
            await GR.set_member_state(tx, grow, company.id, body.state)
            await ctx.audit(
                tx,
                company_id=company.id,
                action="group.member",
                action_class="A2",
                target_kind="group",
                target_ref=f"{key}:{code}",
                summary=f"membership {body.state}",
            )
            await ctx.interaction(
                tx,
                company_id=company.id,
                kind="setting",
                action="group.member",
                target_kind="group",
                target_ref=f"{key}:{code}",
                data={"state": body.state},
            )
            await ctx.emit(tx, code, "group.run", None, {"group": key, "membership": body.state})
        return GR.render_member(await GR.member(tx, grow["id"], company.id), GR.render(grow))


@router.get("/groups/{key}/runs", response_model=Page[GR.RoutineRun], responses=E)
async def list_group_runs(
    key: str,
    company: str | None = Query(default=None, pattern=CODE),
    routine: str | None = Query(default=None, pattern=KEY),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[GR.RoutineRun]:
    """The routines' history, newest period first: each run, the work item it made
    (or why it was skipped)."""
    c0, c1 = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key)
        found = await tx.all(
            GR.RUN_SQL
            + """ WHERE x.group_id = :g AND (CAST(:co AS text) IS NULL OR c.code = :co)
                  AND (CAST(:r AS text) IS NULL OR x.routine = :r)
                  AND (CAST(:c0 AS timestamptz) IS NULL
                       OR (x.occurrence_at, x.id) < (CAST(:c0 AS timestamptz), CAST(:c1 AS uuid)))
                ORDER BY x.occurrence_at DESC, x.id DESC LIMIT :n""",
            g=grow["id"],
            co=company,
            r=routine,
            c0=c0,
            c1=c1,
            n=limit + 1,
        )
    items, nxt = pagination.page(found, limit, ("occurrence_at", "id"))
    return Page(items=[GR.render_run(r) for r in items], next_cursor=nxt)


@router.put("/groups/{key}/routines/{routine}", response_model=GR.Group, responses=E)
async def set_routine(
    key: str, routine: str, body: StateIn, ctx: Ctx = Depends(owner_ctx)
) -> GR.Group:
    """The owner pauses (or resumes) a routine for every member; the pause
    survives a new version of the group's file."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key, lock=True)
        await GR.set_routine_state(tx, grow, routine, body.state)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="group.routine",
            action_class="A2",
            target_kind="group",
            target_ref=f"{key}:{routine}",
            summary=f"routine {body.state}",
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="group.routine",
            target_kind="group",
            target_ref=f"{key}:{routine}",
            data={"state": body.state},
        )
        return GR.render(await _group(ctx, tx, key))


@router.get("/groups/{key}/kpis", response_model=GroupKpis, responses=E)
async def group_kpis(
    key: str,
    company: str | None = Query(default=None, pattern=CODE),
    days: int = Query(default=30, ge=1, le=365),
    ctx: Ctx = Depends(owner_ctx),
) -> GroupKpis:
    """Each member's KPI series (growth.metrics_daily: the connections' daily
    read and the hub's own counts; a KPI the hub cannot read has no points)."""
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key)
        g = GR.render(grow)
        today = owner_today(await owner_tz(tx))
        out = []
        for m in await GR.members(tx, grow["id"]):
            if company is not None and m["company"] != company:
                continue
            kpis = [
                KpiSeries(
                    key=k.key,
                    title_fa=k.title_fa,
                    unit=k.unit,
                    source=k.source,
                    series=await GR.kpi_series(tx, m["company_id"], k, days, today),
                )
                for k in g.kpis
            ]
            out.append(
                CompanyKpis(code=m["company"], name_fa=m["name_fa"] or m["company"], kpis=kpis)
            )
    return GroupKpis(group=key, days=days, companies=out)


@router.get("/groups/{key}/experiments", response_model=list[GR.Experiment], responses=E)
async def list_experiments(
    key: str,
    company: str | None = Query(default=None, pattern=CODE),
    ctx: Ctx = Depends(owner_ctx),
) -> list[GR.Experiment]:
    """One experiment a week per company, newest week first."""
    async with ctx.tx() as tx:
        grow = await _group(ctx, tx, key)
        found = await tx.all(
            GR.EXPERIMENT_SQL
            + """ WHERE x.group_id = :g AND (CAST(:co AS text) IS NULL OR c.code = :co)
                ORDER BY x.week DESC, c.code LIMIT 200""",
            g=grow["id"],
            co=company,
        )
    return [GR.render_experiment(r) for r in found]


@router.get("/companies/{code}/readiness", response_model=RD.Readiness, responses=E)
async def get_readiness(
    code: str,
    group: str = Query(default="content", pattern=KEY),
    ctx: Ctx = Depends(owner_ctx),
) -> RD.Readiness:
    """§29.9 every check of the company for the group, each failed one with
    its one-tap fix (hire, hiring.open, envelope.set, connection.guide,
    series.propose, media.on, lock.open, runner.check, group.resume)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        return await RD.check(tx, ctx.hub, company, group)


class ReadinessFixIn(Model):
    group: str = Field(default="content", pattern=KEY)
    action: str = Field(pattern=r"^[a-z]+(\.[a-z]+)?$", max_length=40)
    target: str | None = Field(default=None, max_length=120)


# what the app does itself (a guide, a page, a setting): nothing to run here
APP_FIXES = ("connection.guide", "envelope.set", "media.on", "runner.check")


@router.post("/companies/{code}/readiness/fix", response_model=RD.Readiness, responses=E)
async def fix_readiness(
    code: str, body: ReadinessFixIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> RD.Readiness:
    """§29.9 one tap on a failed check's fix, with the same actions (and the
    same step-ups) as the order report's: `hire` fills the seat (automatic
    hiring, §29.10), `hiring.open` (🔏), `lock.open` (🔏), `group.resume`,
    `series.propose` (a work item for the company's media director). A fix the
    app does itself (a guide, the month's envelope, the media tools, the
    runner) answers the readiness unchanged."""
    from hq_api.domain import work as W
    from hq_api.routes import order_report as ORR

    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        target = body.target or ""
        if body.action == "group.resume":
            key = target.partition(":")[0] or body.group
            grow = await _group(ctx, tx, key)
            await GR.set_member_state(tx, grow, company.id, "on")
            summary = f"membership of {key} on"
        elif body.action == "series.propose":
            mgr = await tx.first(
                """SELECT e.code FROM core.employees e JOIN core.departments d ON d.id = e.department_id
                   WHERE e.company_id = :co AND d.code = 'MEDIA' AND e.role = 'media_director'
                     AND e.status = 'active' LIMIT 1""",
                co=company.id,
            )
            if mgr is None:
                raise ApiError(409, "not_ready", "no media director yet: hire the seat first")
            kind = target.partition(":")[2] or "instagram"
            w = await W.create(
                tx,
                ctx.who,
                company_id=company.id,
                company_code=company.code,
                title="پیشنهاد سری انتشار",
                brief=(
                    f"Propose a publishing series for the company's {kind} channel with series.propose "
                    "(start with auto_publish false), from the content group's plan and the analyst's numbers."
                ),
                kind="one_off",
                priority="P2",
                assignee_code=mgr["code"],
                budget=W.BudgetIn(tokens=120_000),
            )
            summary = f"series proposal asked ({w['ref']})"
        elif body.action in ("hire", "hiring.open", "lock.open"):
            summary = await ORR._apply_fix(
                ctx,
                tx,
                request,
                ORR.FixIn(action=body.action, target=body.target),
                body.target,
                {},
                [],
            )
        elif body.action in APP_FIXES:
            return await RD.check(tx, ctx.hub, company, body.group)
        else:
            raise ApiError(422, "validation_failed", fields={"action": "not a readiness fix"})
        await ctx.audit(
            tx,
            company_id=company.id,
            action="readiness.fix",
            action_class="A2",
            target_kind="company",
            target_ref=company.code,
            summary=f"{body.action} {target}: {summary}"[:500],
            step_up=body.action in ("hiring.open", "lock.open"),
        )
        return await RD.check(tx, ctx.hub, company, body.group)


# ------------------------------------------------------------ agent tools --
class PlanItem(Model):
    seat: str = Field(pattern=KEY)
    title_fa: str = Field(min_length=1, max_length=300)
    series: str | None = Field(default=None, max_length=40)
    why_fa: str | None = Field(default=None, max_length=1000)


class SuggestionIn(Model):
    title_fa: str = Field(min_length=3, max_length=300)
    why_fa: str = Field(default="", max_length=1000)
    impact_fa: str = Field(default="", max_length=300)
    cost_fa: str = Field(default="", max_length=300)
    impact: int = Field(default=3, ge=1, le=5)
    cost: int = Field(default=2, ge=1, le=5)


class PlanIn(Model):
    group: str = Field(default="content", pattern=KEY)
    company: str | None = Field(default=None, pattern=CODE)
    items: list[PlanItem] = Field(default_factory=list, max_length=10)
    note_fa: str | None = Field(default=None, max_length=2000)
    suggestion: SuggestionIn | None = None


class PlanOut(BaseModel):
    group: str
    company: str
    plan_at: datetime | None
    items: int
    suggestion: HM.Suggestion | None
    # why a suggestion was not kept (its text was not plain Persian, or the
    # owner said «نه» to the same idea)
    note: str | None = None


async def _agent_company(ctx: Ctx, code: str | None) -> Any:
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    return await ctx.hub.companies.by_code(code or str(who.company))


@internal_router.post("/groups/plan", response_model=PlanOut, responses=E)
async def agent_group_plan(body: PlanIn, ctx: Ctx = Depends(internal_ctx)) -> PlanOut:
    """group.plan: the content lead's plan of the day (at most ten items, each
    with its seat) and, optionally, ONE suggestion for the owner's home
    («پیشنهاد مؤثر» / «پیشنهاد خوب», source `group`)."""
    company = await _agent_company(ctx, body.company)
    await allow(ctx, "group.plan", {"company": company.code, "charter": ctx.who.charter})
    now = datetime.now(UTC)
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await ctx.ensure_unlocked(tx, company.id)
        grow = await GR.row_of(tx, body.group)
        g = GR.render(grow)
        seats = {s.seat for s in g.seats}
        bad = [i.seat for i in body.items if i.seat not in seats]
        if bad:
            raise ApiError(422, "validation_failed", fields={"items": f"no such seat: {bad[0]}"})
        await GR.member(tx, grow["id"], company.id)  # 404 when it is not a member
        plan_at = None
        if body.items or body.note_fa:
            plan = {
                "items": [i.model_dump(exclude_none=True) for i in body.items],
                "note_fa": body.note_fa,
                "by": ctx.who.code,
            }
            await GR.store_plan(tx, grow, company.id, plan, now)
            plan_at = now
        sug = None
        note = None
        if body.suggestion is not None:
            s = body.suggestion
            today = owner_today(await owner_tz(tx), now)
            row = await HM.add_suggestion(
                tx,
                company_id=company.id,
                company_code=company.code,
                title_fa=s.title_fa,
                why_fa=s.why_fa,
                impact_fa=s.impact_fa,
                cost_fa=s.cost_fa,
                impact=s.impact,
                cost=s.cost,
                source="group",
                key=HM.plan_key(company.code, today, s.title_fa),
                source_ref=ctx.who.code,
            )
            if row is None:
                note = "not kept: not plain Persian after rewriting, already filed, or refused by the owner"
            else:
                sug = HM.render_suggestion(row)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="group.plan",
            action_class="A1",
            target_kind="group",
            target_ref=f"{g.key}:{company.code}",
            summary=f"{len(body.items)} items" + (", a suggestion" if sug else ""),
        )
        await ctx.emit(
            tx, company.code, "group.run", None, {"group": g.key, "plan": len(body.items)}
        )
    return PlanOut(
        group=g.key, company=company.code, plan_at=plan_at, items=len(body.items),
        suggestion=sug, note=note,
    )  # fmt: skip


class ExperimentIn(Model):
    group: str = Field(default="content", pattern=KEY)
    company: str | None = Field(default=None, pattern=CODE)
    week: date | None = None
    hypothesis_fa: str | None = Field(default=None, min_length=3, max_length=1000)
    metric: str | None = Field(default=None, pattern=KEY)
    target: float | None = None
    baseline: float | None = None
    result: float | None = None
    kept: bool | None = None
    note_fa: str | None = Field(default=None, max_length=1000)


@internal_router.post("/experiments", response_model=GR.Experiment, responses=E)
async def agent_experiment(body: ExperimentIn, ctx: Ctx = Depends(internal_ctx)) -> GR.Experiment:
    """experiment.write: the week's experiment of the company (hypothesis,
    metric, the figure to beat), and its close with the result (kept or not)."""
    company = await _agent_company(ctx, body.company)
    await allow(ctx, "experiment.write", {"company": company.code, "charter": ctx.who.charter})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await ctx.ensure_unlocked(tx, company.id)
        grow = await GR.row_of(tx, body.group)
        await GR.member(tx, grow["id"], company.id)
        tz = await owner_tz(tx)
        week = body.week or date.fromisoformat(owner_week(datetime.now(UTC), tz))
        row = await GR.write_experiment(
            tx,
            grow,
            company.id,
            week=week,
            by=ctx.who.code,
            hypothesis_fa=body.hypothesis_fa,
            metric=body.metric,
            target=body.target,
            baseline=body.baseline,
            result=body.result,
            kept=body.kept,
            note_fa=body.note_fa,
        )
        await ctx.audit(
            tx,
            company_id=company.id,
            action="experiment.write",
            action_class="A1",
            target_kind="experiment",
            target_ref=str(row["id"]),
            summary=f"week {week}: " + ("closed" if row["closed_at"] else "open"),
        )
        await ctx.emit(
            tx, company.code, "group.run", None,
            {"group": body.group, "experiment": str(row["id"]), "closed": bool(row["closed_at"])},
        )  # fmt: skip
    return GR.render_experiment(row)
