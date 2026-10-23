"""Roles written on demand (prompt 13 §1.1, contract §22.5, §22.7).

Owner:
    GET  /roles/drafts                 ?company&department&state&cursor (newest first)
    GET  /roles/drafts/{ref}
    POST /roles/drafts                 {company, department, brief_md}: the owner asks;
                                       the department's manager is woken to write it
    POST /roles/drafts/{ref}/retire    no step-up: no new hire on it; its employees run on
Agents (internal):
    POST /roles/drafts                 role.draft (A1): the department's manager writes it
    POST /roles/drafts/{ref}/decide    role.decide (A2): a CEO, own company, delegated hiring
    POST /roles/drafts/{ref}/review    skill.review with an RD- ref: the overseer's review
Stream: role.updated on topic `people`.
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import role_drafts as RD
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, DEPT_CODE, Model, Page

log = logging.getLogger("hq_api.routes.role_drafts")

router = APIRouter(tags=["people"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
EI = responses(401, 403, 404, 409, 422, 423)


class DraftRequest(Model):
    company: str = Field(pattern=CODE)
    department: str = Field(pattern=DEPT_CODE)
    brief_md: str = Field(min_length=1, max_length=10000)


class DecideIn(Model):
    verdict: Literal["approve", "reject", "return"]
    note: str | None = Field(default=None, max_length=5000)


class RoleReviewIn(Model):
    version: int = Field(default=1, ge=1, le=100000)
    verdict: Literal["pass", "changes", "reject"]
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description="a pass needs injection, secrets, conflicts, policy and ceiling all true",
    )
    notes_md: str = Field(min_length=1, max_length=4000)
    sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="the sha256 of the text the reviewer was shown; another one is 422",
    )


class DraftBrief(Model):
    """What an agent gets back: the state, never the whole body again."""

    ref: str
    role: str | None
    state: str
    state_note_fa: str | None
    originality: RD.Originality | None
    sha256: str | None
    eval_run: dict[str, Any] | None = None


def _brief(r: dict[str, Any]) -> DraftBrief:
    d = RD.render(r)
    return DraftBrief(
        ref=d.ref,
        role=d.role,
        state=d.state,
        state_note_fa=d.state_note_fa,
        originality=d.originality,
        sha256=d.sha256,
        eval_run=d.eval_run,
    )


# ------------------------------------------------------------------- owner --
@router.get("/roles/drafts", response_model=Page[RD.RoleDraft], responses=E)
async def list_drafts(
    company: str | None = Query(default=None, pattern=CODE),
    department: str | None = Query(default=None, pattern=DEPT_CODE),
    state: Literal["drafting", "in_review", "eval", "proposed", "active", "rejected", "retired"]
    | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[RD.RoleDraft]:
    """Every role draft, newest first (the owner's view: the full charter text)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            RD.DRAFT_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:dept AS text) IS NULL OR d.code = :dept)
                    AND (CAST(:st AS text) IS NULL OR r.state = :st)
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (r.created_at, r.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY r.created_at DESC, r.id DESC LIMIT :lim""",
            co=company,
            dept=department,
            st=state,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[RD.render(r) for r in items], next_cursor=nxt)


@router.get("/roles/drafts/{ref}", response_model=RD.RoleDraft, responses=E)
async def get_draft(ref: str, ctx: Ctx = Depends(owner_ctx)) -> RD.RoleDraft:
    async with ctx.tx() as tx:
        return RD.render(await RD.load(tx, ref))


@router.post("/roles/drafts", response_model=RD.RoleDraft, status_code=201, responses=E)
async def request_draft(body: DraftRequest, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner asks for a role («یه تدوینگر پادکست میخوام»): a `drafting` draft
    and one work item that wakes the department's manager to write it. Takes
    `Idempotency-Key`."""
    co = await ctx.hub.companies.by_code(body.company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        r = await RD.request(
            tx,
            ctx.who,
            company_id=co.id,
            company_code=co.code,
            department=body.department,
            brief_md=body.brief_md,
        )
        out = RD.render(r)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post("/roles/drafts/{ref}/retire", response_model=RD.RoleDraft, responses=E)
async def retire_draft(ref: str, ctx: Ctx = Depends(owner_ctx)) -> RD.RoleDraft:
    """No step-up (as from its story): no new hire on it; employees on it keep
    running until they are moved or dismissed."""
    async with ctx.tx() as tx:
        r = await RD.retire(tx, ctx.who, await RD.load(tx, ref, lock=True))
        return RD.render(r)


# ------------------------------------------------------------------ agents --
async def _run_work(ctx: Ctx, tx: Any) -> UUID | None:
    if not ctx.who.run_id:
        return None
    w: UUID | None = await tx.scalar(
        "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid)", r=ctx.who.run_id
    )
    return w


@internal_router.post("/roles/drafts", response_model=DraftBrief, status_code=201, responses=EI)
async def write_draft(
    body: RD.RoleDraftIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """role.draft (A1): the department's manager writes the role. Outside the
    ceiling: 422 (fields name each problem), nothing stored. Requires
    `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "role.draft", {"company": body.company, "department": body.department})
    # Over every company: the overseer's review item is the holding's.
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await RD.write(
            tx, ctx.who, body, lib=ctx.hub.charters, run_work_id=await _run_work(ctx, tx)
        )
        out = _brief(r)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@internal_router.post("/roles/drafts/{ref}/decide", response_model=DraftBrief, responses=EI)
async def decide_draft(
    ref: str, body: DecideIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """role.decide (A2): the company's CEO, while hiring is delegated, a draft
    of its own company that passed review and eval and still fits the ceiling.
    Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        r = await RD.load(tx, ref, lock=True)
        await allow(ctx, "role.decide", {"company": r["company"]})
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await RD.decide_by_ceo(tx, ctx.who, r, body.verdict, body.note, lib=ctx.hub.charters)
        out = _brief(r)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@internal_router.post("/roles/drafts/{ref}/review", response_model=DraftBrief, responses=EI)
async def review_draft(
    ref: str, body: RoleReviewIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """skill.review with an RD- ref (the overseer, QC, AI Safety): a pass needs
    the five checks and the sha256 of the text shown; it queues the draft's own
    eval run. Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "skill.review", {"company": ctx.who.company})
    run_id: str | None = None
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        r = await RD.load(tx, ref, lock=True)
        r = await RD.record_review(
            tx,
            r,
            who=ctx.who,
            version=body.version,
            verdict=body.verdict,
            checks=body.checks,
            notes_md=body.notes_md,
            sha=body.sha256,
        )
        if body.verdict == "pass":
            try:  # refused before anything of the run is written (academy_budget)
                run = await RD.queue_eval(tx, ctx.hub.settings, r, ctx.who)
                run_id = str(run["id"])
            except ApiError as exc:
                if exc.code != "academy_budget":
                    raise
                r = await RD.load(tx, ref)
                await RD._set(tx, r, state_note_fa="سقف ماهانه‌ی آکادمی پر است؛ آزمون صف نشد")
        out = _brief(await RD.load(tx, ref))
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    if run_id is not None:
        await workflows_client.eval_run(ctx.hub, run_id)
    return out
