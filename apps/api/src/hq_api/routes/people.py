"""Stars, lessons, stories and the CEOs' hire decisions (contract §18.4, §18.11,
§18.12; prompt 08 §4, §8, §9).

The owner reads (`/stars…`, `/lessons`, `/stories…`) and marks stories seen or
welcomes a hire; agents write through the Tool Gateway: `star.rubric` and
`star.give` (CEO, own company), `star.audit` (overseer), `lesson.write`
(overseer, AI Ops head), `story.post` (CEOs and holding heads), `hire.decide`
(a CEO, on the cards it is the approver of).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import files as F
from hq_api.domain import hiring, scoring
from hq_api.domain import stars as S
from hq_api.domain import stories as ST
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Actor, FileRef, Model, Page, actor

router = APIRouter(tags=["people"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
CO = r"^[A-Z][A-Z0-9]{1,9}$"
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"


# ------------------------------------------------------------------ models --
class Criterion(Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    name_fa: str = Field(min_length=1, max_length=100)
    weight: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    description_md: str = Field(default="", max_length=2000)


class StarRubric(BaseModel):
    company: str
    version: int
    criteria: list[dict[str, Any]]
    rules_md: str
    by: Actor | None
    status: Literal["draft", "active"]
    updated_at: datetime


class Evidence(Model):
    kind: str = Field(min_length=1, max_length=20)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=500)


class Star(BaseModel):
    id: UUID
    employee: str
    company: str
    week: date
    stars: float
    by: Actor | None
    reason_md: str
    evidence: list[dict[str, Any]]
    criteria: dict[str, float]
    counted: bool
    overseer_note: str | None
    created_at: datetime


class CompanyStanding(BaseModel):
    company: str
    stars: float | None
    score: float | None
    parts: dict[str, float | None]
    rank: int | None
    trend: list[float]


class EmployeeStanding(BaseModel):
    code: str
    company: str
    title_fa: str
    stars: float
    count: int
    rank_company: int
    rank_holding: int
    trend: list[float]
    efficiency: float | None


class StarRollup(BaseModel):
    period: Literal["week", "month"]
    key: str
    best_company: str | None
    companies: list[CompanyStanding]
    employees: list[EmployeeStanding]
    lessons: list[str]


class Adoption(BaseModel):
    company: str
    status: Literal["proposed", "adopted", "rejected"]
    decision_ref: str | None
    work_ref: str | None = None


class Lesson(BaseModel):
    id: UUID
    ref: str
    source_company: str
    period: str
    title_fa: str
    body_md: str
    evidence: list[dict[str, Any]]
    adoption: list[Adoption]
    created_at: datetime


class Figure(Model):
    label_fa: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=16)


class StoryLinks(Model):
    employee: str | None = Field(default=None, pattern=EMP)
    deliverable: str | None = Field(default=None, max_length=20)
    decision: str | None = Field(default=None, max_length=20)
    work: str | None = Field(default=None, max_length=20)
    period: str | None = Field(default=None, pattern=ST.PERIOD)
    # ⟨additive⟩ the metric a milestone reached, by name (§18.15: a milestone
    # links work, a deliverable or a metric), e.g. "users_active".
    metric: str | None = Field(default=None, pattern=ST.METRIC)


class Story(BaseModel):
    id: UUID
    ref: str
    company: str
    kind: Literal["hire", "deliverable", "stars", "milestone", "post"]
    author: Actor | None
    title_fa: str
    body_fa: str
    figures: list[dict[str, str]]
    media: FileRef | None
    links: dict[str, str]
    created_at: datetime
    expires_at: datetime
    seen: bool
    welcomed: bool


class StoryRing(BaseModel):
    company: str
    unseen: int
    latest_at: datetime
    items: list[Story]


class Seen(Model):
    refs: list[str] = Field(min_length=1, max_length=200)


class SeenOut(BaseModel):
    seen: int


# ------------------------------------------------------------- renderers --
def _rubric(r: dict[str, Any], *, latest: bool = True) -> StarRubric:
    return StarRubric(
        company=r["company"],
        version=r["version"],
        criteria=S.rubric_criteria(list(r["criteria"])),  # weights are numbers (§18.15)
        rules_md=r["rules_md"],
        by=actor(r["by_kind"], r["by_code"]),
        status="active" if latest else "draft",
        updated_at=r["created_at"],
    )


def _star(r: dict[str, Any]) -> Star:
    return Star(
        id=r["id"],
        employee=r["employee"],
        company=r["company"],
        week=r["week"],
        stars=float(r["stars"]),
        by=actor(r["by_kind"], r["by_code"]),
        reason_md=r["reason_md"],
        evidence=list(r["evidence"]),
        criteria={k: float(v) for k, v in (r["criteria"] or {}).items()},
        counted=r["counted"],
        overseer_note=r["overseer_note"],
        created_at=r["created_at"],
    )


def _lesson(r: dict[str, Any]) -> Lesson:
    return Lesson(
        id=r["id"],
        ref=r["ref"],
        source_company=r["source_company"],
        period=r["period"],
        title_fa=r["title_fa"],
        body_md=r["body_md"],
        evidence=list(r["evidence"]),
        adoption=[Adoption.model_validate(a) for a in r["adoption"]],
        created_at=r["created_at"],
    )


async def _stories(tx: Tx, rows: list[dict[str, Any]]) -> list[Story]:
    media = await F.refs(tx, [r["media_file_id"] for r in rows if r["media_file_id"]])
    return [
        Story(
            id=r["id"],
            ref=r["ref"],
            company=r["company"],
            kind=r["kind"],
            author=actor(r["author_kind"], r["author_code"]),
            title_fa=r["title_fa"],
            body_fa=r["body_fa"],
            figures=list(r["figures"]),
            media=media.get(r["media_file_id"]) if r["media_file_id"] else None,
            links=dict(r["links"]),
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            seen=r["seen_at"] is not None,
            welcomed=r["welcomed_at"] is not None,
        )
        for r in rows
    ]


# ------------------------------------------------------------ owner: stars --
@router.get("/stars/rubrics", response_model=list[StarRubric], responses=E)
async def list_rubrics(ctx: Ctx = Depends(owner_ctx)) -> list[StarRubric]:
    """The active rubric of every company that has one (CEOs write them)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT DISTINCT ON (r.company_id) r.*, c.code AS company FROM people.star_rubrics r
               JOIN core.companies c ON c.id = r.company_id
               ORDER BY r.company_id, r.version DESC"""
        )
    return sorted((_rubric(r) for r in rows), key=lambda x: x.company)


@router.get("/stars/rubrics/{company}", response_model=StarRubric, responses=E)
async def get_rubric(company: str, ctx: Ctx = Depends(owner_ctx)) -> StarRubric:
    """One company's active star rubric (404 while its CEO has written none)."""
    co = await ctx.hub.companies.by_code(company)
    async with ctx.tx() as tx:
        row = await S.latest_rubric(tx, co.id)
    if row is None:
        raise ApiError(404, "not_found")
    return _rubric(row)


@router.get("/stars", response_model=Page[Star], responses=E)
async def list_stars(
    company: str | None = Query(default=None, pattern=CO),
    week: date | None = None,
    employee: str | None = Query(default=None, pattern=EMP),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Star]:
    """Stars given by the CEOs, newest week first (`counted` false: no reason or
    evidence, or the overseer's audit)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.STAR_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:week AS date) IS NULL OR s.week = :week)
                    AND (CAST(:emp AS text) IS NULL OR e.code = :emp)
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (s.created_at, s.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY s.created_at DESC, s.id DESC LIMIT :lim""",
            co=company,
            week=week,
            emp=employee,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[_star(r) for r in items], next_cursor=nxt)


@router.get("/stars/rollup", response_model=StarRollup, responses=E)
async def get_rollup(
    period: Literal["week", "month"] = "week",
    key: str | None = Query(default=None, pattern=r"^[0-9]{4}-[0-9]{2}(-[0-9]{2})?$"),
    ctx: Ctx = Depends(owner_ctx),
) -> StarRollup:
    """The roll-up of a closed period (default: the last one): companies by
    score (parts kpi, challenges, compliance, people, efficiency; a part
    without data is null and left out of the score), employees by stars."""
    async with ctx.tx() as tx:
        row = await tx.first(
            """SELECT * FROM people.star_rollups WHERE period = :p AND (CAST(:k AS text) IS NULL OR key = :k)
               ORDER BY starts_on DESC LIMIT 1""",
            p=period,
            k=key,
        )
        if row is None:
            raise ApiError(404, "not_found")
        lessons = await tx.all(
            "SELECT ref FROM knowledge.lessons WHERE period = :p ORDER BY ref",
            p=f"{period}:{row['key']}",
        )
    data = row["data"]
    return StarRollup(
        period=row["period"],
        key=row["key"],
        best_company=row["best_company"],
        companies=[CompanyStanding.model_validate(c) for c in data.get("companies", [])],
        employees=[EmployeeStanding.model_validate(e) for e in data.get("employees", [])],
        lessons=[r["ref"] for r in lessons],
    )


@router.get("/lessons", response_model=list[Lesson], responses=E)
async def list_lessons(
    company: str | None = Query(default=None, pattern=CO),
    period: str | None = Query(default=None, max_length=30),
    ctx: Ctx = Depends(owner_ctx),
) -> list[Lesson]:
    """Lessons from the best companies with each other company's adoption."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.LESSON_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:p AS text) IS NULL OR l.period = :p)
                  ORDER BY l.created_at DESC LIMIT 200""",
            co=company,
            p=period,
        )
    return [_lesson(r) for r in rows]


# ---------------------------------------------------------- owner: stories --
@router.get("/stories", response_model=list[StoryRing], responses=E)
async def list_stories(ctx: Ctx = Depends(owner_ctx)) -> list[StoryRing]:
    """Live stories (24 h), one ring per company: rings with unseen stories
    first, then by the latest; each ring's items oldest first."""
    async with ctx.tx() as tx:
        rows = await ST.live(tx)
        rendered = {s.ref: s for s in await _stories(tx, rows)}
    return [
        StoryRing(
            company=g["company"],
            unseen=g["unseen"],
            latest_at=g["latest_at"],
            items=[rendered[x["ref"]] for x in g["items"]],
        )
        for g in ST.rings(rows)
    ]


@router.get("/stories/archive", response_model=Page[Story], responses=E)
async def story_archive(
    company: str | None = Query(default=None, pattern=CO),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Story]:
    """Expired stories, newest first (the company's highlights)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            ST.STORY_SQL
            + """ WHERE s.expires_at <= now() AND (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND """
            + ST.NOT_HELD
            + """
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (s.created_at, s.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY s.created_at DESC, s.id DESC LIMIT :lim""",
            co=company,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=await _stories(tx, items), next_cursor=nxt)


@router.post("/stories/seen", response_model=SeenOut, responses=E)
async def stories_seen(body: Seen, ctx: Ctx = Depends(owner_ctx)) -> SeenOut:
    """Marks stories seen (no step-up)."""
    async with ctx.tx() as tx:
        n = await tx.exec(
            "UPDATE owner.stories SET seen_at = now() WHERE ref = ANY(:refs) AND seen_at IS NULL",
            refs=body.refs,
        )
    return SeenOut(seen=int(n or 0))


@router.post("/stories/{ref}/welcome", response_model=Story, responses=E)
async def welcome(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Story:
    """The owner welcomes a new hire (a `hire` story only, else 422): the new
    employee's CEO and manager hear of it in their threads (no step-up)."""
    async with ctx.tx() as tx:
        row = await tx.one(ST.STORY_SQL + " WHERE s.ref = :ref", ref=ref)
        if row["kind"] != "hire":
            raise ApiError(
                422, "validation_failed", fields={"ref": "only a hire story is welcomed"}
            )
        if row["welcomed_at"] is None:
            await tx.exec(
                "UPDATE owner.stories SET welcomed_at = now(), seen_at = COALESCE(seen_at, now()) WHERE id = :id",
                id=row["id"],
            )
            code = row["links"].get("employee")
            if code:
                emp = await tx.first(
                    """SELECT e.code, (SELECT b.code FROM core.employees b WHERE b.id = e.reports_to) AS boss
                       FROM core.employees e WHERE e.code = :c""",
                    c=code,
                )
                threads = {f"{row['company']}-CEO"}
                if emp and emp["boss"]:
                    threads.add(emp["boss"])
                for t in sorted(threads):
                    await D.post_system_message(
                        tx, t, f"مدیر کل به {code} خوشامد گفت.", {"employee": code}
                    )
                # A small positive part of the employee score (§18.12, §18.15): now.
                dept = await tx.scalar(
                    "SELECT department_id FROM core.employees WHERE code = :c", c=code
                )
                if dept is not None:
                    await scoring.recompute_department(tx, dept)
            await ctx.audit(
                tx,
                company_id=row["company_id"],
                action="story.welcome",
                action_class="A1",
                target_kind="story",
                target_ref=ref,
                summary=f"welcome {code or ''}",
            )
        row = await tx.one(ST.STORY_SQL + " WHERE s.ref = :ref", ref=ref)
        return (await _stories(tx, [row]))[0]


# ----------------------------------------------------------------- agents --
class RubricIn(Model):
    criteria: list[Criterion] = Field(min_length=1, max_length=12)
    rules_md: str = Field(default="", max_length=10000)


class StarIn(Model):
    employee: str = Field(pattern=EMP)
    week: date
    stars: Decimal = Field(ge=0, le=5, max_digits=2, decimal_places=1)
    criteria: dict[str, Decimal] = Field(default_factory=dict, max_length=12)
    reason_md: str = Field(default="", max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)

    @field_validator("stars")
    @classmethod
    def _half(cls, v: Decimal) -> Decimal:
        if not S.half_step(v):
            raise ValueError("whole or half stars: 0, 0.5, … 5")
        return v


class AuditIn(Model):
    counted: bool
    note: str = Field(min_length=1, max_length=2000)


class LessonIn(Model):
    source_company: str = Field(pattern=CO)
    period: str = Field(pattern=r"^(week|month):[0-9]{4}-[0-9]{2}(-[0-9]{2})?$")
    title_fa: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1, max_length=20000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)


class StoryIn(Model):
    kind: Literal["post", "milestone"]
    title_fa: str = Field(min_length=1, max_length=60)
    body_fa: str = Field(default="", max_length=280)
    figures: list[Figure] = Field(default_factory=list, max_length=3)
    file_id: UUID | None = None
    links: StoryLinks = Field(default_factory=StoryLinks)


class HireDecideIn(Model):
    verdict: Literal["approve", "reject", "return"]
    note: str | None = Field(default=None, max_length=5000)


def _ceo(ctx: Ctx) -> None:
    if ctx.who.role != "ceo":
        raise ApiError(403, "policy_denied", "a CEO only")


@internal_router.post("/stars/rubric", response_model=StarRubric, responses=E)
async def agent_rubric(body: RubricIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """star.rubric: the CEO's star rubric of its own company (a new version; an
    `efficiency` criterion of at least 15% is required). Requires `Idempotency-Key`."""
    _ceo(ctx)
    await allow(ctx, "star.rubric", {"company": ctx.who.company})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        assert ctx.who.company_id is not None
        row = await S.write_rubric(
            tx,
            ctx.who,
            ctx.who.company_id,
            [c.model_dump(mode="json") for c in body.criteria],
            body.rules_md,
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,
            action="star.rubric",
            action_class="A2",
            target_kind="star_rubric",
            target_ref=f"{row['company']}@{row['version']}",
            summary=f"{len(body.criteria)} criteria",
        )
        result = _rubric(row)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post("/stars", response_model=Star, responses=E)
async def agent_star(body: StarIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """star.give: a CEO's weekly stars for one employee of its own company (no
    reason or no evidence: kept, not counted). Requires `Idempotency-Key`."""
    _ceo(ctx)
    await allow(ctx, "star.give", {"company": ctx.who.company})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await S.give(
            tx,
            ctx.who,
            employee_code=body.employee,
            week=body.week,
            stars=body.stars,
            criteria=body.criteria,
            reason_md=body.reason_md,
            evidence=[e.model_dump() for e in body.evidence],
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="star.give",
            action_class="A2",
            target_kind="employee",
            target_ref=body.employee,
            summary=f"{body.stars} stars, week {body.week} ({'counted' if row['counted'] else 'not counted'})",
        )
        result = _star(row)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post("/stars/{star_id}/audit", response_model=Star, responses=E)
async def agent_star_audit(
    star_id: UUID, body: AuditIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """star.audit: the overseer marks a star counted or not, with the reason."""
    await allow(ctx, "star.audit", {"company": None})
    # The overseer audits any company's stars: a transaction over every company.
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await S.audit(tx, ctx.who, star_id, body.counted, body.note)
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="star.audit",
            action_class="A2",
            target_kind="star",
            target_ref=str(star_id),
            summary=f"counted={body.counted}",
        )
        result = _star(row)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post("/lessons", response_model=Lesson, status_code=201, responses=E)
async def agent_lesson(body: LessonIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """lesson.write (overseer, AI Ops head): a lesson from a company; every other
    company's CEO gets a work item to consider adopting it. Requires `Idempotency-Key`."""
    await allow(ctx, "lesson.write", {"company": body.source_company, "charter": ctx.who.charter})
    # A lesson reaches every other company (adoption work for its CEO).
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await S.write_lesson(
            tx,
            ctx.who,
            source_company=body.source_company,
            period=body.period,
            title_fa=body.title_fa,
            body_md=body.body_md,
            evidence=[e.model_dump() for e in body.evidence],
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="lesson.write",
            action_class="A1",
            target_kind="lesson",
            target_ref=row["ref"],
            summary=f"{body.source_company} {body.period}",
        )
        result = _lesson(row)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@internal_router.post("/stories", response_model=Story, status_code=201, responses=E)
async def agent_story(body: StoryIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """story.post (CEOs and holding heads): a story of its own company, at most 3
    a day per company (429 story_limit). Requires `Idempotency-Key`."""
    await allow(ctx, "story.post", {"company": ctx.who.company})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await ST.post(
            tx,
            ctx.who,
            kind=body.kind,
            title_fa=body.title_fa,
            body_fa=body.body_fa,
            figures=[f.model_dump() for f in body.figures],
            file_id=body.file_id,
            links=body.links.model_dump(exclude_none=True),
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="story.post",
            action_class="A1",
            target_kind="story",
            target_ref=row["ref"],
            summary=body.kind,
        )
        result = (await _stories(tx, [row]))[0]
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@internal_router.post("/hires/{ref}/decide", response_model=D.Decision, responses=E)
async def agent_hire_decide(
    ref: str, body: HireDecideIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """hire.decide: a CEO decides a hire card it is the approver of (hiring
    delegated, its own company; also its own proposals). Approval runs every
    hard check (charter, model, estimate, envelope, kill switch, 5 a day) in
    this transaction; a refusal makes no employee. Requires `Idempotency-Key`."""
    _ceo(ctx)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        try:
            d = await D.load(tx, ref, lock=True)
        except ApiError as exc:  # another company's card: refused, never "missing" (no oracle)
            raise ApiError(403, "policy_denied", "this card is not yours to decide") from exc
        if d["kind"] != "hire":
            raise ApiError(422, "validation_failed", fields={"ref": "a hire card"})
        await allow(ctx, "hire.decide", {"company": d["company"], "approver": d["approver_code"]})
        # Only while hiring is open in mode `delegated` (contract §18.15).
        current = await hiring.mode(tx)
        if current is None:
            raise ApiError(403, "hiring_closed")
        if current != "delegated":
            raise ApiError(403, "policy_denied", "hiring is in mode proposals: the owner decides")
        if d["approver_code"] != ctx.who.code:
            raise ApiError(403, "policy_denied", "this card is not yours to decide")
        verdict: Literal["approved", "rejected", "returned"] = {
            "approve": "approved",
            "reject": "rejected",
            "return": "returned",
        }[body.verdict]  # type: ignore[assignment]
        if verdict == "approved":
            company = await ctx.hub.companies.by_id(d["company_id"])
            D.check_hire_role(d["payload"], company.kind, ctx.hub.charters, required=True)
        await ctx.ensure_unlocked(tx, d["company_id"])
        out = await D.decide(
            tx, ctx.who, d, verdict, note=body.note, charters=ctx.hub.charters, hub=ctx.hub
        )
        await ctx.audit(
            tx,
            company_id=d["company_id"],
            action=f"hire.{body.verdict}",
            action_class="A2",
            target_kind="decision",
            target_ref=ref,
            summary=f"hire -> {verdict} by {ctx.who.code}",
        )
        result = D.render(out)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workflows_client.decision_decided(ctx.hub, ref)
    return result
