"""Organisation (contract §3): companies, templates, departments, employees,
org chart. Companies are data: adding one is a record plus a template."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import org, templates
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.schemas import CODE, DEPT_CODE, EmployeeRef, Model, Page, employee_ref
from hq_api.security import stepup

router = APIRouter(tags=["organisation"])
E = responses(401, 403, 404, 409, 422)


# ------------------------------------------------------------------ models --
class CompanyCounts(BaseModel):
    employees_active: int
    work_open: int
    decisions_pending: int


class Company(BaseModel):
    id: UUID
    code: str
    kind: str
    name_fa: str | None
    name_en: str | None
    color_index: int | None
    status: str
    template: str | None
    kill_switch: str
    deploy_freeze_until: datetime | None
    counts: CompanyCounts
    version: int
    created_at: datetime


class CompanyCreate(Model):
    code: str = Field(pattern=CODE)
    name_fa: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    color_index: int | None = Field(default=None, ge=1, le=8)
    template: str = Field(default="standard", pattern=r"^[a-z][a-z0-9_]{1,40}$")


class CompanyPatch(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    color_index: int | None = Field(default=None, ge=1, le=8)
    status: Literal["active", "paused", "archived"] | None = None


class Template(BaseModel):
    key: str
    name_fa: str
    name_en: str
    departments: list[str]


class Department(BaseModel):
    id: UUID
    company: str
    code: str
    name_fa: str
    name_en: str
    manager_title_fa: str
    manager_title_en: str
    manager: EmployeeRef | None
    status: str
    sort: int
    version: int


class DepartmentCreate(Model):
    code: str = Field(pattern=DEPT_CODE)
    name_fa: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    manager_title_fa: str = Field(min_length=1, max_length=120)
    manager_title_en: str = Field(min_length=1, max_length=120)
    sort: int = Field(default=100, ge=0, le=10000)


class DepartmentPatch(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    manager_title_fa: str | None = Field(default=None, min_length=1, max_length=120)
    manager_title_en: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "paused", "archived"] | None = None
    sort: int | None = Field(default=None, ge=0, le=10000)


class WorkBrief(BaseModel):
    id: UUID
    ref: str
    title: str
    status: str
    priority: str
    due_at: datetime | None
    created_at: datetime


class RatingBrief(BaseModel):
    deliverable: str
    score: int
    rated_at: datetime


class EmployeeDetail(org.Employee):
    recent_work: list[WorkBrief]
    recent_ratings: list[RatingBrief]


class EmployeePatch(Model):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class Dismiss(Model):
    reason: str = Field(min_length=1, max_length=2000)
    transfer_to: str | None = Field(default=None, max_length=40)


class DismissResult(BaseModel):
    employee: str
    status: str
    moved_work: int
    knowledge_transfer_work: str


class ChartNode(BaseModel):
    code: str
    kind: str
    title_fa: str
    display_name: str | None
    department: str | None
    status: str
    activity: str
    children: list[ChartNode]


class Chart(BaseModel):
    company: str
    roots: list[ChartNode]


# --------------------------------------------------------------- companies --
COMPANY_SQL = """
    SELECT c.id, c.code, c.kind, c.name_fa, c.name_en, c.color_index, c.status, c.template,
           c.version, c.created_at,
           COALESCE(k.state, 'released') AS kill_switch,
           (SELECT max(f.until) FROM control.deploy_freezes f
             WHERE f.company_id = c.id AND f.lifted_at IS NULL AND f.until > now()) AS deploy_freeze_until,
           (SELECT count(*) FROM core.employees e WHERE e.company_id = c.id AND e.status = 'active')
               AS employees_active,
           (SELECT count(*) FROM work.work w WHERE w.company_id = c.id
             AND w.status IN ('queued', 'in_progress', 'waiting', 'delivered')) AS work_open,
           (SELECT count(*) FROM cartable.decisions d WHERE d.company_id = c.id AND d.status = 'pending')
               AS decisions_pending
    FROM core.companies c
    LEFT JOIN control.kill_switches k ON k.company_id = c.id
"""


def _company(r: dict[str, Any]) -> Company:
    return Company(
        **{
            k: r[k]
            for k in (
                "id",
                "code",
                "kind",
                "name_fa",
                "name_en",
                "color_index",
                "status",
                "template",
                "kill_switch",
                "deploy_freeze_until",
                "version",
                "created_at",
            )
        },
        counts=CompanyCounts(
            employees_active=r["employees_active"],
            work_open=r["work_open"],
            decisions_pending=r["decisions_pending"],
        ),
    )


@router.get("/companies", response_model=list[Company], responses=E)
async def list_companies(
    status: Literal["active", "paused", "archived"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    ctx: Ctx = Depends(owner_ctx),
) -> list[Company]:
    """Holding first, then by code; built for 40+ companies."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            COMPANY_SQL
            + """ WHERE (CAST(:status AS text) IS NULL OR c.status = :status)
                    AND (CAST(:q AS text) IS NULL OR c.code ILIKE '%' || core.like_escape(:q) || '%'
                         OR core.fa_normalize(COALESCE(c.name_fa, ''))
                            LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%'
                         OR c.name_en ILIKE '%' || core.like_escape(:q) || '%')
                  ORDER BY c.kind = 'holding' DESC, c.code""",
            status=status,
            q=q,
        )
    return [_company(r) for r in rows]


@router.get("/companies/{code}", response_model=Company, responses=E)
async def get_company(code: str, ctx: Ctx = Depends(owner_ctx)) -> Company:
    """One company with its counters, kill switch and deploy freeze."""
    async with ctx.tx() as tx:
        return _company(await tx.one(COMPANY_SQL + " WHERE c.code = :code", code=code))


@router.post("/companies", response_model=Company, status_code=201, responses=E)
async def create_company(
    body: CompanyCreate, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Company:
    """🔏 step-up `company.create` on the new code. Departments and leadership
    positions come from the template file, all in one transaction."""
    if templates.template(body.template) is None or body.template == "holding":
        raise ApiError(422, "validation_failed", fields={"template": "unknown template"})
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "company.create", body.code)
        if await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=body.code):
            raise ApiError(409, "validation_failed", fields={"code": "already exists"})
        # One company creation picks a free colour slot at a time (no two take the same).
        await tx.exec("SELECT pg_advisory_xact_lock(hashtext('core.companies.color_index'))")
        row = await tx.one(
            """INSERT INTO core.companies (code, name, kind, name_fa, name_en, color_index, template)
               VALUES (:code, :name_en, 'company', :name_fa, :name_en,
                       COALESCE(:ci, (SELECT min(slot) FROM generate_series(1, 8) AS slot
                                     WHERE slot NOT IN (SELECT color_index FROM core.companies
                                                        WHERE color_index IS NOT NULL))), :tpl)
               RETURNING id""",
            code=body.code,
            name_fa=body.name_fa,
            name_en=body.name_en,
            ci=body.color_index,
            tpl=body.template,
        )
        await tx.rescope([*await ctx.scope(), row["id"]])
        added = await templates.apply(tx, row["id"], body.code, body.template)
        await ctx.audit(
            tx,
            company_id=row["id"],
            action="company.create",
            action_class="A2",
            target_kind="company",
            target_ref=body.code,
            summary=f"created from template {body.template}: {added}",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=row["id"],
            kind="edit",
            action="company.create",
            target_kind="company",
            target_ref=body.code,
            data={"template": body.template},
        )
        await ctx.emit(tx, body.code, "control.changed", body.code, {"change": "company.created"})
        result = _company(await tx.one(COMPANY_SQL + " WHERE c.id = :id", id=row["id"]))
    ctx.hub.companies.invalidate()
    return result


@router.patch(
    "/companies/{code}", response_model=Company, responses=responses(401, 403, 404, 409, 422, 428)
)
async def update_company(
    code: str, body: CompanyPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Company:
    """`name_*`, `color_index`, `status` (`archived` only with 🔏 `company.archive`).
    The code never changes. Requires `If-Match: <version>`."""
    expected = if_match(request)
    fields = body.model_dump(exclude_unset=True)
    async with ctx.tx() as tx:
        cur = await tx.one(
            "SELECT id, kind, version, status FROM core.companies WHERE code = :c FOR UPDATE",
            c=code,
        )
        check_version(cur["version"], expected)
        step = False
        if fields.get("status") == "archived" and cur["status"] != "archived":
            if cur["kind"] == "holding":
                raise ApiError(
                    422, "validation_failed", fields={"status": "the holding cannot be archived"}
                )
            await stepup.consume(tx, request, ctx.who, "company.archive", code)
            step = True
        if fields:
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            await tx.exec(
                f"UPDATE core.companies SET {sets} WHERE id = :id",  # noqa: S608 - names from the model
                id=cur["id"],
                **fields,
            )
        await ctx.audit(
            tx,
            company_id=cur["id"],
            action="company.update",
            action_class="A2",
            target_kind="company",
            target_ref=code,
            summary="fields: " + ",".join(sorted(fields)),
            step_up=step,
        )
        await ctx.interaction(
            tx,
            company_id=cur["id"],
            kind="edit",
            action="company.update",
            target_kind="company",
            target_ref=code,
            data={"fields": sorted(fields)},
        )
        await ctx.emit(tx, code, "control.changed", code, {"change": "company.updated"})
        result = _company(await tx.one(COMPANY_SQL + " WHERE c.id = :id", id=cur["id"]))
    ctx.hub.companies.invalidate()
    return result


@router.get("/templates", response_model=list[Template], responses=E)
async def list_templates(ctx: Ctx = Depends(owner_ctx)) -> list[Template]:
    """Company templates available for POST /companies (seed/templates/*.yaml)."""
    return [
        Template(
            key=k,
            name_fa=t.get("name_fa", k),
            name_en=t.get("name_en", k),
            departments=[d["code"] for d in t.get("departments") or []],
        )
        for k, t in templates.templates().items()
    ]


# ------------------------------------------------------------- departments --
DEPT_SQL = f"""
    SELECT d.id, c.code AS company, d.code, d.name_fa, d.name_en, d.manager_title_fa,
           d.manager_title_en, d.status, d.sort, d.version, {org.ref_cols("m", "m_")}
    FROM core.departments d
    JOIN core.companies c ON c.id = d.company_id
    LEFT JOIN core.employees m ON m.department_id = d.id AND m.kind IN ('manager', 'inspector')
                               AND m.status <> 'dismissed'
"""  # noqa: S608 - composed from module constants; values are bound


def _dept(r: dict[str, Any]) -> Department:
    return Department(
        **{
            k: r[k]
            for k in (
                "id",
                "company",
                "code",
                "name_fa",
                "name_en",
                "manager_title_fa",
                "manager_title_en",
                "status",
                "sort",
                "version",
            )
        },
        manager=employee_ref(r, "m_"),
    )


@router.get("/companies/{code}/departments", response_model=list[Department], responses=E)
async def list_departments(code: str, ctx: Ctx = Depends(owner_ctx)) -> list[Department]:
    """The company's departments with their managers, in display order."""
    co = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        rows = await tx.all(
            DEPT_SQL + " WHERE d.company_id = :co ORDER BY d.sort, d.code", co=co.id
        )
    return [_dept(r) for r in rows]


@router.post(
    "/companies/{code}/departments", response_model=Department, status_code=201, responses=E
)
async def create_department(
    code: str, body: DepartmentCreate, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Department:
    """🔏 step-up `department.create` on the company code. Adds the manager
    position and the department's threads too."""
    co = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        await stepup.consume(tx, request, ctx.who, "department.create", code)
        row = await tx.first(
            """INSERT INTO core.departments (company_id, code, name_fa, name_en, manager_title_fa,
                   manager_title_en, sort)
               VALUES (:co, :code, :nfa, :nen, :mfa, :men, :sort)
               ON CONFLICT (company_id, code) DO NOTHING RETURNING id""",
            co=co.id,
            code=body.code,
            nfa=body.name_fa,
            nen=body.name_en,
            mfa=body.manager_title_fa,
            men=body.manager_title_en,
            sort=body.sort,
        )
        if row is None:
            raise ApiError(409, "validation_failed", fields={"code": "already exists"})
        ceo = await org.ceo_of(tx, co.id)
        mgr_code = f"{code}-{body.code}-MGR"
        mgr = await tx.one(
            """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, reports_to)
               VALUES (:co, :d, :code, 'manager', :tfa, :ten, :rt) RETURNING id""",
            co=co.id,
            d=row["id"],
            code=mgr_code,
            tfa=body.manager_title_fa,
            ten=body.manager_title_en,
            rt=ceo["id"] if ceo else None,
        )
        await tx.exec(
            """INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
               VALUES (:code, 'manager', :co, :e, :t) ON CONFLICT (code) DO NOTHING""",
            code=mgr_code,
            co=co.id,
            e=mgr["id"],
            t=body.manager_title_fa,
        )
        await tx.exec(
            """INSERT INTO msg.threads (code, kind, company_id, department_id, title_fa)
               VALUES (:code, 'department', :co, :d, :t) ON CONFLICT (code) DO NOTHING""",
            code=f"{code}-{body.code}",
            co=co.id,
            d=row["id"],
            t=body.name_fa,
        )
        await ctx.audit(
            tx,
            company_id=co.id,
            action="department.create",
            action_class="A2",
            target_kind="department",
            target_ref=f"{code}-{body.code}",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="edit",
            action="department.create",
            target_kind="department",
            target_ref=f"{code}-{body.code}",
        )
        await ctx.emit(tx, code, "employee.updated", mgr_code, {"change": "position.created"})
        return _dept(await tx.one(DEPT_SQL + " WHERE d.id = :id", id=row["id"]))


@router.patch(
    "/departments/{company}/{dept}",
    response_model=Department,
    responses=responses(401, 403, 404, 409, 422, 428),
)
async def update_department(
    company: str, dept: str, body: DepartmentPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Department:
    """Requires `If-Match: <version>`. The code never changes."""
    expected = if_match(request)
    co = await ctx.hub.companies.by_code(company)
    fields = body.model_dump(exclude_unset=True)
    async with ctx.tx() as tx:
        cur = await tx.one(
            "SELECT id, version FROM core.departments WHERE company_id = :co AND code = :d FOR UPDATE",
            co=co.id,
            d=dept,
        )
        check_version(cur["version"], expected)
        if fields:
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            await tx.exec(
                f"UPDATE core.departments SET {sets} WHERE id = :id",  # noqa: S608 - names from the model
                id=cur["id"],
                **fields,
            )
        await ctx.audit(
            tx,
            company_id=co.id,
            action="department.update",
            action_class="A2",
            target_kind="department",
            target_ref=f"{company}-{dept}",
            summary="fields: " + ",".join(sorted(fields)),
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="edit",
            action="department.update",
            target_kind="department",
            target_ref=f"{company}-{dept}",
            data={"fields": sorted(fields)},
        )
        return _dept(await tx.one(DEPT_SQL + " WHERE d.id = :id", id=cur["id"]))


# --------------------------------------------------------------- employees --
async def _render_many(ctx: Ctx, tx: Tx, rows: list[dict[str, Any]]) -> list[org.Employee]:
    holding = await ctx.hub.companies.holding()
    assignments = await org.Assignments.load(tx, holding.code)
    trend = await org.trends(tx, [r["id"] for r in rows])
    return [
        org.render(r, assignments, trend.get(r["id"], [None] * 12), ctx.hub.charters) for r in rows
    ]


@router.get("/employees", response_model=Page[org.Employee], responses=E)
async def list_employees(
    company: list[str] | None = Query(default=None),
    department: str | None = Query(default=None, pattern=DEPT_CODE),
    kind: Literal["ceo", "manager", "employee", "advisor", "inspector", "system"] | None = None,
    status: Literal["active", "paused", "dismissed"] | None = None,
    activity: Literal["sleeping", "working", "waiting", "error"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[org.Employee]:
    """Sorted by code."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        rows = await tx.all(
            org.EMPLOYEE_SQL
            + """ WHERE (CAST(:companies AS text[]) IS NULL OR c.code = ANY(:companies))
                    AND (CAST(:dept AS text) IS NULL OR d.code = :dept)
                    AND (CAST(:kind AS text) IS NULL OR e.kind = :kind)
                    AND (CAST(:status AS text) IS NULL OR e.status = :status)
                    AND (CAST(:activity AS text) IS NULL OR e.activity = :activity)
                    AND (CAST(:q AS text) IS NULL OR e.code ILIKE '%' || core.like_escape(:q) || '%'
                         OR core.fa_normalize(e.title_fa || ' ' || COALESCE(e.display_name, ''))
                            LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                    AND (CAST(:after AS text) IS NULL OR e.code > :after)
                  ORDER BY e.code LIMIT :lim""",
            companies=company,
            dept=department,
            kind=kind,
            status=status,
            activity=activity,
            q=q,
            after=after[0] if after else None,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("code",))
        return Page(items=await _render_many(ctx, tx, items), next_cursor=nxt)


@router.get("/employees/{code}", response_model=EmployeeDetail, responses=E)
async def get_employee(code: str, ctx: Ctx = Depends(owner_ctx)) -> EmployeeDetail:
    """Includes the last 20 work items and ratings."""
    async with ctx.tx() as tx:
        row = await org.load_employee(tx, code)
        emp = (await _render_many(ctx, tx, [row]))[0]
        work = await tx.all(
            """SELECT id, ref, title, status, priority, due_at, created_at FROM work.work
               WHERE assignee_id = :id ORDER BY created_at DESC LIMIT 20""",
            id=row["id"],
        )
        ratings = await tx.all(
            """SELECT DISTINCT ON (r.deliverable_id) d.ref AS deliverable, r.score, r.rated_at
               FROM cartable.ratings r JOIN cartable.deliverables d ON d.id = r.deliverable_id
               WHERE d.producer_id = :id ORDER BY r.deliverable_id, r.version_no DESC""",
            id=row["id"],
        )
    ratings.sort(key=lambda r: r["rated_at"], reverse=True)
    return EmployeeDetail(
        **emp.model_dump(),
        recent_work=[WorkBrief(**w) for w in work],
        recent_ratings=[RatingBrief(**r) for r in ratings[:20]],
    )


@router.patch(
    "/employees/{code}",
    response_model=org.Employee,
    responses=responses(401, 403, 404, 409, 422, 428),
)
async def update_employee(
    code: str, body: EmployeePatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> org.Employee:
    """`display_name` only. Requires `If-Match: <version>`."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        cur = await tx.one(
            "SELECT id, company_id, version FROM core.employees WHERE code = :c FOR UPDATE", c=code
        )
        check_version(cur["version"], expected)
        await tx.exec(
            "UPDATE core.employees SET display_name = :n WHERE id = :id",
            id=cur["id"],
            n=body.display_name,
        )
        await ctx.audit(
            tx,
            company_id=cur["company_id"],
            action="employee.update",
            action_class="A2",
            target_kind="employee",
            target_ref=code,
            summary="display_name",
        )
        await ctx.interaction(
            tx,
            company_id=cur["company_id"],
            kind="edit",
            action="employee.rename",
            target_kind="employee",
            target_ref=code,
        )
        await ctx.emit(
            tx, await ctx.hub.companies.code_of(cur["company_id"]), "employee.updated", code
        )
        return (await _render_many(ctx, tx, [await org.load_employee(tx, code)]))[0]


async def _set_status(ctx: Ctx, code: str, status: str) -> org.Employee:
    async with ctx.tx() as tx:
        cur = await tx.one(
            "SELECT id, company_id, status FROM core.employees WHERE code = :c FOR UPDATE", c=code
        )
        if cur["status"] == "dismissed":
            raise ApiError(409, "validation_failed", "dismissed employees cannot change status")
        await tx.exec(
            "UPDATE core.employees SET status = :s WHERE id = :id", id=cur["id"], s=status
        )
        action = "employee.pause" if status == "paused" else "employee.resume"
        await ctx.audit(
            tx,
            company_id=cur["company_id"],
            action=action,
            action_class="A2",
            target_kind="employee",
            target_ref=code,
        )
        await ctx.interaction(
            tx,
            company_id=cur["company_id"],
            kind="edit",
            action=action,
            target_kind="employee",
            target_ref=code,
        )
        await ctx.emit(
            tx,
            await ctx.hub.companies.code_of(cur["company_id"]),
            "employee.updated",
            code,
            {"status": status},
        )
        return (await _render_many(ctx, tx, [await org.load_employee(tx, code)]))[0]


@router.post("/employees/{code}/pause", response_model=org.Employee, responses=E)
async def pause_employee(code: str, ctx: Ctx = Depends(owner_ctx)) -> org.Employee:
    """Stops new work being routed to the employee; open work stays."""
    return await _set_status(ctx, code, "paused")


@router.post("/employees/{code}/resume", response_model=org.Employee, responses=E)
async def resume_employee(code: str, ctx: Ctx = Depends(owner_ctx)) -> org.Employee:
    """Routes new work to the employee again."""
    return await _set_status(ctx, code, "active")


@router.post("/employees/{code}/dismiss", response_model=DismissResult, responses=E)
async def dismiss_employee(
    code: str, body: Dismiss, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> DismissResult:
    """🔏 step-up `employee.dismiss` on the code. Status `dismissed` (final; the
    code is retired forever), open work returns to the manager, and a
    knowledge-transfer work item is created for the runtime (§1.3)."""
    async with ctx.tx() as tx:
        emp = await tx.one(
            "SELECT id, code, kind, status, company_id, department_id FROM core.employees WHERE code = :c FOR UPDATE",
            c=code,
        )
        await stepup.consume(tx, request, ctx.who, "employee.dismiss", code)
        result = await org.dismiss(tx, emp, reason=body.reason, transfer_to=body.transfer_to)
        await ctx.audit(
            tx,
            company_id=emp["company_id"],
            action="employee.dismiss",
            action_class="A2",
            target_kind="employee",
            target_ref=code,
            summary=f"transfer to {body.transfer_to or 'manager'}",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=emp["company_id"],
            kind="edit",
            action="employee.dismiss",
            target_kind="employee",
            target_ref=code,
            data={"reason": body.reason, "transfer_to": body.transfer_to},
        )
        co_code = await ctx.hub.companies.code_of(emp["company_id"])
        await ctx.emit(tx, co_code, "employee.updated", code, {"status": "dismissed"})
        await ctx.emit(
            tx,
            co_code,
            "work.created",
            result["knowledge_transfer_work"],
            {"kind": "knowledge_transfer"},
        )
    return DismissResult(employee=code, status="dismissed", **result)


@router.get("/org/{company}/chart", response_model=Chart, responses=E)
async def org_chart(company: str, ctx: Ctx = Depends(owner_ctx)) -> Chart:
    """CEO -> managers -> employees, with live `activity` (dismissed excluded)."""
    co = await ctx.hub.companies.by_code(company)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT e.id, e.code, e.kind, e.title_fa, e.display_name, d.code AS department, e.status,
                      e.activity, e.reports_to
               FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
               WHERE e.company_id = :co AND e.status <> 'dismissed'
               ORDER BY d.sort NULLS FIRST, e.kind <> 'manager', e.code""",
            co=co.id,
        )
    nodes = {
        r["id"]: ChartNode(
            code=r["code"],
            kind=r["kind"],
            title_fa=r["title_fa"],
            display_name=r["display_name"],
            department=r["department"],
            status=r["status"],
            activity=r["activity"],
            children=[],
        )
        for r in rows
    }
    roots: list[ChartNode] = []
    for r in rows:
        parent = nodes.get(r["reports_to"]) if r["reports_to"] else None
        (parent.children if parent else roots).append(nodes[r["id"]])
    return Chart(company=company, roots=roots)


# ------------------------------------------------------------ direct hire --
DIRECT_REASON = "استخدام مستقیم مالک"


class DirectHireIn(Model):
    """The owner hires directly (contract §18.11)."""

    company: str = Field(pattern=CODE)
    department: str = Field(pattern=DEPT_CODE)
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title_fa: str = Field(min_length=1, max_length=200)
    title_en: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=3, max_length=100)
    effort: D.Effort | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=5000)
    duties: list[str] = Field(default_factory=list, max_length=50)
    reports_to: str | None = Field(default=None, pattern=D.EMP)
    quota_estimate_month: D.Quota | None = None


class DirectHire(BaseModel):
    employee: org.Employee
    decision: D.Decision


@router.post(
    "/org/hires",
    response_model=DirectHire,
    status_code=201,
    responses=responses(401, 403, 404, 422),
)
async def direct_hire(body: DirectHireIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`hire.direct`, target = SHA-256 of the exact body) the owner hires
    directly: a `hire` decision proposed **and** sealed by the owner in one
    transaction (approved, resolution M-…), then the employee. The same checks
    as an agent's proposal (the charter `role` must fit the company and the
    department); `model`, `effort` and `title_en` default to the charter's."""
    target = hashlib.sha256(await request.body()).hexdigest()
    co = await ctx.hub.companies.by_code(body.company)
    charter = ctx.hub.charters.get(body.role) if ctx.hub.charters is not None else None
    payload: dict[str, Any] = {
        "company": co.code,
        "department": body.department,
        "role": body.role,
        "title_fa": body.title_fa,
        "title_en": body.title_en or (charter.title_en if charter else body.title_fa),
        "reason": body.reason or DIRECT_REASON,
        "duties": body.duties,
        "model": body.model or (charter.model if charter else ""),
        "effort": body.effort or (charter.effort if charter else "medium"),
    }
    if body.reports_to:
        payload["reports_to"] = body.reports_to
    if body.quota_estimate_month:
        payload["quota_estimate_month"] = body.quota_estimate_month.model_dump(
            mode="json", exclude_none=True
        )
    # Before the step-up is consumed: the charter must fit (422 otherwise).
    D.check_hire_role(payload, co.kind, ctx.hub.charters, required=True)
    async with ctx.tx() as tx:
        # A retry after a lost answer replays it (the step-up is single-use).
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        su = await stepup.consume(tx, request, ctx.who, "hire.direct", target)
        d = await D.propose(
            tx,
            ctx.who,
            company_id=co.id,
            company_code=co.code,
            body=D.DecisionIn(
                kind="hire",
                title=f"استخدام مستقیم: {body.title_fa}"[:300],
                what=f"{body.title_fa} ({body.role}) در {co.code}-{body.department}",
                why=payload["reason"],
                quota_estimate=body.quota_estimate_month,
                payload=payload,
            ),
            thread_code=None,
            charters=ctx.hub.charters,
            company_kind=co.kind,
            notify_owner=False,
        )
        d = await D.decide(tx, ctx.who, d, "approved", note=None, step_up_id=su)
        out = await D.apply_effect(tx, d["ref"], ctx.who)
        await ctx.audit(
            tx,
            company_id=co.id,
            action="hire.direct",
            action_class="A2",
            target_kind="employee",
            target_ref=out["employee"],
            summary=f"{body.role} in {co.code}-{body.department} ({d['ref']})",
            step_up=True,
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="decision",
            action="hire.direct",
            target_kind="decision",
            target_ref=d["ref"],
            data={"employee": out["employee"], "role": body.role},
        )
        row = await org.load_employee(tx, out["employee"])
        employee = (await _render_many(ctx, tx, [row]))[0]
        decision = D.render(await D.load(tx, d["ref"]))
        result = DirectHire(employee=employee, decision=decision)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result
