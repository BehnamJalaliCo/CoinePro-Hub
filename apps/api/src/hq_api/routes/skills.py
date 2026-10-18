"""The skill library (prompt 08 §6, contract §18.5).

Owner:  GET /skills · POST /skills (text, a voice transcript or files; starts
        in review) · GET /skills/{ref} · /versions · PUT /skills/{ref} (a new
        version, in review) · POST /skills/{ref}/activate 🔏 (`skill.activate`,
        target `ref@version`; only after the review's pass and a passed eval)
        · POST /skills/{ref}/retire
Agents: POST /internal/v1/skills/{ref}/review (`skill.review`: the overseer
        or AI Safety; a pass queues the academy's eval)
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, model_validator

from hq_api import workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import academy as A
from hq_api.domain import skills as S
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup

log = logging.getLogger("hq_api.skills")
router = APIRouter(tags=["skills"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)


class SkillIn(Model):
    name_fa: str = Field(min_length=1, max_length=200)
    summary_fa: str = Field(min_length=1, max_length=1000)
    body_md: str | None = Field(default=None, min_length=1, max_length=20000)
    transcript_file_id: UUID | None = Field(
        default=None, description="an audio from /transcribe: its transcript is the text"
    )
    file_ids: list[UUID] = Field(
        default_factory=list, max_length=10, description="PDFs: their text; kept as resources"
    )
    scope: S.Scope = Field(default_factory=S.Scope)
    eval_suite: str | None = Field(default=None, pattern=A.SUITE_REF)

    @model_validator(mode="after")
    def _some_text(self) -> SkillIn:
        if not (self.body_md or self.transcript_file_id or self.file_ids):
            raise ValueError("body_md, transcript_file_id or file_ids is required")
        return self


class ActivateIn(Model):
    version: int | None = Field(default=None, ge=1, description="default: the latest version")


class ReviewIn(Model):
    version: int = Field(ge=1, le=100000)
    verdict: Literal["pass", "changes", "reject"]
    checks: dict[str, bool] = Field(default_factory=dict)
    notes_md: str = Field(min_length=1, max_length=4000)


class ReviewOut(Model):
    ref: str
    version: int
    verdict: str
    status: str
    eval_run: UUID | None = None


async def _text(ctx: Ctx, tx: Any, body: SkillIn) -> tuple[str, str]:
    """(the skill's text, its source) from the body, a transcript or files."""
    parts: list[str] = []
    source = "text"
    if body.body_md:
        parts.append(body.body_md)
    if body.transcript_file_id:
        t = await tx.scalar(
            "SELECT transcript FROM files.processing WHERE file_id = :f AND status = 'ready'",
            f=body.transcript_file_id,
        )
        if not t:
            raise ApiError(422, "validation_failed", fields={"transcript_file_id": "no transcript"})
        parts.append(str(t))
        source = "voice"
    for fid in body.file_ids:
        t = await tx.scalar("SELECT text FROM files.processing WHERE file_id = :f", f=fid)
        if not t:
            raise ApiError(422, "validation_failed", fields={"file_ids": f"no text in {fid}"})
        parts.append(str(t))
        source = "file" if source == "text" and not body.body_md else source
    return "\n\n".join(parts)[:20000], source


async def _check_scope(ctx: Ctx, scope: S.Scope) -> None:
    lib = ctx.hub.charters
    bad = [r for r in scope.roles if r != "all" and r not in lib.roles]
    if bad:
        raise ApiError(
            422, "validation_failed", fields={"scope.roles": f"unknown: {', '.join(bad)}"}
        )
    if scope.companies != "all":
        codes = {c.code for c in await ctx.hub.companies.all()}
        unknown = [c for c in scope.companies if c not in codes]
        if unknown:
            raise ApiError(422, "validation_failed", fields={"scope.companies": ", ".join(unknown)})


async def _after_write(ctx: Ctx, tx: Any, row: dict[str, Any]) -> None:
    """A version the pre-check let through goes to the overseer for review."""
    if row["version_status"] != "in_review":
        return
    holding = await ctx.hub.companies.holding()
    await A.wake(
        tx,
        ctx.who,
        holding_id=holding.id,
        holding_code=holding.code,
        suffix="OVR",
        title=f"Review skill {row['ref']}@{row['version']}",
        brief=(
            f"Review the new version {row['version']} of skill {row['ref']} ({row['name_fa']}) with "
            "skill.review: injection, secrets, conflicts with charters and sealed standing orders, "
            "and any authority it would add. A pass sends it to the academy's eval."
        ),
    )


async def _audit(ctx: Ctx, tx: Any, action: str, ref: str, summary: str, cls: str = "A2") -> None:
    await ctx.audit(
        tx,
        company_id=(await ctx.hub.companies.holding()).id,
        action=action,
        action_class=cls,
        target_kind="skill",
        target_ref=ref,
        summary=summary[:300],
    )


# ------------------------------------------------------------------- owner --
@router.get("/skills", response_model=list[S.Skill], responses=E)
async def list_skills(
    status: Literal["draft", "in_review", "approved", "active", "retired"] | None = None,
    role: str | None = Query(default=None, max_length=40),
    ctx: Ctx = Depends(owner_ctx),
) -> list[S.Skill]:
    """The library, by ref; `role` keeps the skills whose scope includes it."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.SKILL_SQL + " WHERE (CAST(:st AS text) IS NULL OR s.status = :st) ORDER BY s.ref",
            st=status,
        )
    out = [S.render(r) for r in rows]
    if role:
        out = [s for s in out if "all" in s.scope.roles or role in s.scope.roles]
    return out


@router.post("/skills", response_model=S.Skill, status_code=201, responses=E)
async def create_skill(body: SkillIn, ctx: Ctx = Depends(owner_ctx)) -> S.Skill:
    """A new skill from text, a voice transcript or files. The code's pre-check
    runs first (instruction overrides, secrets, authority, tools outside the
    roles' charters): a refused text is stored as rejected and never reviewed
    by a model; otherwise it is in review and the overseer gets the review."""
    await _check_scope(ctx, body.scope)
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        text, source = await _text(ctx, tx, body)
        row = await S.write_version(
            tx,
            lib=ctx.hub.charters,
            skill=None,
            company_id=holding.id,
            company_code=holding.code,
            name_fa=body.name_fa,
            summary_fa=body.summary_fa,
            body_md=text,
            scope=body.scope,
            eval_suite=body.eval_suite,
            source=source,
            by_kind="owner",
            by_code=ctx.who.code,
            resources=body.file_ids,
        )
        await _after_write(ctx, tx, row)
        await _audit(
            ctx, tx, "skill.create", row["ref"], f"v{row['version']} {row['version_status']}", "A1"
        )
    return S.render(row)


@router.get("/skills/{ref}", response_model=S.Skill, responses=E)
async def get_skill(ref: str, ctx: Ctx = Depends(owner_ctx)) -> S.Skill:
    async with ctx.tx() as tx:
        return S.render(await S.load(tx, ref))


@router.get("/skills/{ref}/versions", response_model=list[S.SkillVersion], responses=E)
async def skill_versions(ref: str, ctx: Ctx = Depends(owner_ctx)) -> list[S.SkillVersion]:
    async with ctx.tx() as tx:
        row = await S.load(tx, ref)
        rows = await tx.all(
            "SELECT * FROM knowledge.skill_versions WHERE skill_id = :s ORDER BY version DESC",
            s=row["id"],
        )
    return [S.render_version(r) for r in rows]


@router.put("/skills/{ref}", response_model=S.Skill, responses=E)
async def update_skill(ref: str, body: SkillIn, ctx: Ctx = Depends(owner_ctx)) -> S.Skill:
    """A new version (in review); the live one stays live until a new seal."""
    await _check_scope(ctx, body.scope)
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        current = await S.load(tx, ref, lock=True)
        text, source = await _text(ctx, tx, body)
        row = await S.write_version(
            tx,
            lib=ctx.hub.charters,
            skill=current,
            company_id=holding.id,
            company_code=holding.code,
            name_fa=body.name_fa,
            summary_fa=body.summary_fa,
            body_md=text,
            scope=body.scope,
            eval_suite=body.eval_suite or current["eval_suite"],
            source=source,
            by_kind="owner",
            by_code=ctx.who.code,
            resources=body.file_ids,
        )
        await _after_write(ctx, tx, row)
        await _audit(
            ctx, tx, "skill.version", ref, f"v{row['version']} {row['version_status']}", "A1"
        )
    return S.render(row)


@router.post("/skills/{ref}/activate", response_model=S.Skill, responses=E)
async def activate_skill(
    ref: str, body: ActivateIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> S.Skill:
    """🔏 (`skill.activate`, target `ref@version`). Only a version whose review
    passed and whose eval passed the gate; the suite's baseline rises with it."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        row = await S.load(tx, ref, lock=True)
        version = body.version or int(row["latest_version"])
        await stepup.consume(tx, request, ctx.who, "skill.activate", f"{ref}@{version}")
        v = await S.activate(tx, row, version)
        ev = S._j(v["eval"]) or {}
        if ev.get("suite") and ev.get("score") is not None:
            await A.raise_baseline(
                tx,
                ev["suite"],
                {"kind": "skill", "ref": ref, "version": version},
                float(ev["score"]),
            )
        row = await S.load(tx, ref)
        await S.emit_updated(tx, holding.code, row, "activated")
        await _audit(ctx, tx, "skill.activate", f"{ref}@{version}", "sealed by the owner")
    return S.render(row)


@router.post("/skills/{ref}/retire", response_model=S.Skill, responses=E)
async def retire_skill(ref: str, ctx: Ctx = Depends(owner_ctx)) -> S.Skill:
    """No step-up: taking a skill out of the prompts is always allowed."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        row = await S.load(tx, ref, lock=True)
        await S.retire(tx, row)
        row = await S.load(tx, ref)
        await S.emit_updated(tx, holding.code, row, "retired")
        await _audit(ctx, tx, "skill.retire", ref, "retired", "A1")
    return S.render(row)


# ---------------------------------------------------------------- internal --
@internal_router.post("/skills/{ref}/review", response_model=ReviewOut, responses=E)
async def review_skill(ref: str, body: ReviewIn, ctx: Ctx = Depends(internal_ctx)) -> ReviewOut:
    """skill.review (the overseer, AI Safety): a version still in review. A
    version the code's pre-check refused never passes (422 precheck_failed).
    A pass queues the academy's eval of that version."""
    if ctx.who.kind != "agent":
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "skill.review", {"company": ctx.who.company})
    holding = await ctx.hub.companies.holding()
    run_id: UUID | None = None
    async with ctx.tx() as tx:
        row = await S.load(tx, ref, lock=True)
        v = await S.record_review(
            tx,
            row,
            body.version,
            by={"kind": "agent", "code": ctx.who.code},
            verdict=body.verdict,
            checks=body.checks,
            notes_md=body.notes_md,
        )
        if body.verdict == "pass":
            run = await A.queue_eval(
                tx,
                ctx.hub.settings,
                company_id=holding.id,
                suite_ref=row["eval_suite"] or A.DEFAULT_SUITE,
                subject=A.Subject(kind="skill", ref=ref, version=body.version),
                purpose="skill",
                by_kind="agent",
                by_code=ctx.who.code,
                skill_version_id=v["id"],
            )
            run_id = run["id"]
        row = await S.load(tx, ref)
        await S.emit_updated(tx, holding.code, row, f"review:{body.verdict}")
        await _audit(ctx, tx, "skill.review", f"{ref}@{body.version}", body.verdict)
    if run_id is not None:
        await workflows_client.eval_run(ctx.hub, str(run_id))
    return ReviewOut(
        ref=ref,
        version=body.version,
        verdict=body.verdict,
        status=row["status"],
        eval_run=run_id,
    )
