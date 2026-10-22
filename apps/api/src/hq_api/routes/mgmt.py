"""Management tools, part B (prompt 12 §4-§8, §10-§12; contract §21.4-§21.9):
briefings, department ranks, HR rounds, the deploy card's diff, waste, ROI,
quick notes and their promotion, claims and the agent health board.

Owner routes are reads (and the notes). The internal routes serve the TTS
one-shot (principal `tts`: claim a briefing, send its audio back) and the
agent tool `claim.verdict` (the fact checker, the overseer, QC).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import briefings as B
from hq_api.domain import claims as CL
from hq_api.domain import decisions as D
from hq_api.domain import deploy_diff, hr, rankings, roi
from hq_api.domain import notes as N
from hq_api.domain import waste as WASTE
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.routes.internal import allow
from hq_api.schemas import Actor, FileRef, Model, Page

router = APIRouter(tags=["management"])
internal_router = APIRouter(tags=["internal"])
# Mounted before the runs router, so /runs/health is not read as /runs/{id}.
first_router = APIRouter(tags=["management"])
E = responses(401, 403, 404, 409, 422)
CO = r"^[A-Z][A-Z0-9]{1,9}$"
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
MAX_AUDIO = 20 * 1024 * 1024


# ------------------------------------------------------------------ models --
class Voice(BaseModel):
    engine: Literal["piper"]
    version: str
    voice: str
    license: str


class Briefing(BaseModel):
    id: UUID
    ref: str
    kind: Literal["morning", "ceo_letter"]
    company: str
    period: dict[str, date]
    deliverable_ref: str
    text_md: str
    audio: FileRef | None
    audio_state: Literal["pending", "ready", "off", "failed"]
    voice: Voice | None
    created_at: datetime


class DepartmentRank(BaseModel):
    period: Literal["week", "month"]
    key: str
    company: str
    department: str
    score: float
    parts: dict[str, float | None]
    employees: int
    rank_company: int
    rank_holding: int | None
    trend: list[float]
    computed_at: datetime


class HrEmployee(BaseModel):
    code: str
    title_fa: str
    score: float | None
    score_prev: float | None
    stars: float | None
    efficiency: float | None
    owner_avg: float | None
    failed_share: float
    findings_open: int
    refuted_claims: int
    probation_until: datetime | None
    flags: list[
        Literal[
            "promote_candidate", "coach", "demote_candidate", "dismiss_candidate", "probation_end"
        ]
    ]


class HrRound(BaseModel):
    id: UUID
    ref: str
    company: str
    month: str
    state: Literal["drafting", "proposed", "done"]
    evaluator: Actor
    due_at: datetime
    employees: list[HrEmployee]
    deliverable_ref: str | None
    decisions: list[str]
    teachings: list[str]


class DiffFile(BaseModel):
    path: str
    status: Literal["added", "modified", "removed", "renamed"]
    additions: int
    deletions: int
    binary: bool
    patch: str | None
    truncated: bool
    secret_masked: bool


class WasteTop(BaseModel):
    employee: str | None = None
    run_id: str | None = None
    work_ref: str | None = None
    tokens: int


class WasteItem(BaseModel):
    category: Literal[
        "failed_runs", "cancelled_work", "no_progress_runs", "retry_loops", "router_errors",
        "duplicate_calls", "cache_miss", "over_model",
    ]  # fmt: skip
    tokens: int
    usd: Decimal
    count: int
    top: list[WasteTop]


class WasteDay(BaseModel):
    day: date
    company: str | None
    total_tokens: int
    total_usd: Decimal
    waste_tokens: int
    waste_usd: Decimal
    share: float
    vs_7d: float | None
    items: list[WasteItem]


class Attributed(BaseModel):
    rescued: int | None = None
    resolved_conversations: int | None = None


class RoiRow(BaseModel):
    by: Literal["employee", "department", "company"]
    key: str
    company: str
    period: Literal["week", "month"]
    period_key: str
    cost_usd: Decimal
    accepted: int
    avg_rating: float | None
    value_points: float
    cost_per_accepted_usd: Decimal | None
    attributed: Attributed
    revenue_usd: Decimal | None
    net_usd: Decimal | None
    roi: float | None
    trend: list[float]


class PromotedTo(BaseModel):
    kind: Literal["work", "order", "errand"]
    ref: str


class OwnerNote(BaseModel):
    id: UUID
    ref: str
    text_md: str
    source: Literal["text", "voice"]
    file_id: UUID | None
    tags: list[str]
    status: Literal["open", "promoted", "archived"]
    promoted_to: PromotedTo | None
    created_at: datetime
    updated_at: datetime
    version: int


class OwnerNoteIn(Model):
    text_md: str = Field(min_length=1, max_length=20000)
    source: Literal["text", "voice"] = "text"
    file_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class OwnerNotePatch(Model):
    text_md: str | None = Field(default=None, min_length=1, max_length=20000)
    tags: list[str] | None = Field(default=None, max_length=20)
    status: Literal["archived"] | None = None


class NotePromoteIn(Model):
    to: Literal["work", "order", "errand"]
    company: str | None = Field(default=None, pattern=CO)
    title: str | None = Field(default=None, min_length=1, max_length=300)


class ClaimEvidence(Model):
    kind: str = Field(min_length=1, max_length=40)
    ref: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=1000)


class Claim(BaseModel):
    id: UUID
    ref: str
    company: str
    deliverable: str
    employee: str | None
    claim_md: str
    verdict: Literal["confirmed", "refuted", "unverifiable"]
    checked_by: Actor
    protocol: str | None
    evidence: list[dict[str, str]]
    at: datetime


class ClaimIn(Model):
    deliverable: str = Field(pattern=r"^O-[0-9]+$")
    claim_md: str = Field(min_length=1, max_length=2000)
    verdict: Literal["confirmed", "refuted", "unverifiable"]
    evidence: list[ClaimEvidence] = Field(default_factory=list, max_length=20)
    protocol: str | None = Field(default=None, pattern=r"^PR-[0-9]{3,}$")


class AgentHealth(BaseModel):
    employee: str
    company: str
    period: Literal["7d", "30d"]
    runs: int
    failed_share: float
    refused_share: float
    retry_loops: int
    owner_returns: int
    claims_checked: int
    refuted: int
    refuted_share: float | None
    cost_usd: Decimal
    flags: list[Literal["truth", "reliability", "loops"]]


class TtsJob(BaseModel):
    id: UUID
    ref: str
    script: str
    voice: str | None


class TtsFail(Model):
    error: str = Field(min_length=1, max_length=300)


# --------------------------------------------------------------- briefings --
async def _briefing(tx: Any, row: dict[str, Any]) -> Briefing:
    return Briefing.model_validate(await B.render(tx, row))


@router.get("/briefings", response_model=Page[Briefing], responses=E)
async def list_briefings(
    kind: Literal["morning", "ceo_letter"] | None = None,
    company: str | None = Query(default=None, pattern=CO),
    limit: int = Query(default=30, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Briefing]:
    """The spoken briefings, newest first (§21.4)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            B.SQL
            + """ WHERE (CAST(:k AS text) IS NULL OR b.kind = :k)
                    AND (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:at AS timestamptz) IS NULL
                         OR (b.created_at, b.id) < (CAST(:at AS timestamptz), CAST(:aid AS uuid)))
                  ORDER BY b.created_at DESC, b.id DESC LIMIT :n""",
            k=kind,
            co=company,
            at=after_t,
            aid=after_id,
            n=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=[await _briefing(tx, r) for r in items], next_cursor=nxt)


@router.get("/briefings/latest", response_model=Briefing, responses=E)
async def latest_briefing(
    kind: Literal["morning", "ceo_letter"] = "morning",
    company: str | None = Query(default=None, pattern=CO),
    ctx: Ctx = Depends(owner_ctx),
) -> Briefing:
    """The latest briefing of a kind (404 while there is none)."""
    async with ctx.tx() as tx:
        row = await tx.first(
            B.SQL
            + """ WHERE b.kind = :k AND (CAST(:co AS text) IS NULL OR c.code = :co)
                  ORDER BY b.created_at DESC LIMIT 1""",
            k=kind,
            co=company,
        )
        if row is None:
            raise ApiError(404, "not_found")
        return await _briefing(tx, row)


@router.get("/briefings/{ref}", response_model=Briefing, responses=E)
async def get_briefing(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Briefing:
    async with ctx.tx() as tx:
        return await _briefing(tx, await tx.one(B.SQL + " WHERE b.ref = :r", r=ref))


# ---------------------------------------------------------------- rankings --
@router.get("/rankings/departments", response_model=list[DepartmentRank], responses=E)
async def department_ranks(
    period: Literal["week", "month"] = "week",
    key: str | None = Query(default=None, pattern=r"^[0-9]{4}-[0-9]{2}(-[0-9]{2})?$"),
    company: str | None = Query(default=None, pattern=CO),
    ctx: Ctx = Depends(owner_ctx),
) -> list[DepartmentRank]:
    """The departments of a closed period (default: the latest), best first."""
    async with ctx.tx() as tx:
        if key is None:
            key = await tx.scalar(
                "SELECT key FROM people.department_ranks WHERE period = :p ORDER BY key DESC LIMIT 1",
                p=period,
            )
        rows = await tx.all(
            """SELECT r.*, c.code AS company FROM people.department_ranks r
               JOIN core.companies c ON c.id = r.company_id
               WHERE r.period = :p AND r.key = :k AND (CAST(:co AS text) IS NULL OR c.code = :co)
               ORDER BY r.score DESC, c.code, r.department""",
            p=period,
            k=key,
            co=company,
        )
    return [DepartmentRank.model_validate(rankings.render(r)) for r in rows]


# ---------------------------------------------------------------- HR rounds --
@router.get("/hr/rounds", response_model=list[HrRound], responses=E)
async def list_hr_rounds(
    company: str | None = Query(default=None, pattern=CO),
    month: str | None = Query(default=None, pattern=r"^1[34][0-9]{2}-(0[1-9]|1[0-2])$"),
    ctx: Ctx = Depends(owner_ctx),
) -> list[HrRound]:
    """The monthly HR rounds, newest first (§21.5)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT r.*, c.code AS company FROM people.hr_rounds r JOIN core.companies c ON c.id = r.company_id
               WHERE (CAST(:co AS text) IS NULL OR c.code = :co) AND (CAST(:m AS text) IS NULL OR r.month = :m)
               ORDER BY r.created_at DESC LIMIT 200""",
            co=company,
            m=month,
        )
    return [HrRound.model_validate(hr.render(r, r["company"])) for r in rows]


@router.get("/hr/rounds/{ref}", response_model=HrRound, responses=E)
async def get_hr_round(ref: str, ctx: Ctx = Depends(owner_ctx)) -> HrRound:
    async with ctx.tx() as tx:
        r = await tx.one(
            """SELECT r.*, c.code AS company FROM people.hr_rounds r JOIN core.companies c ON c.id = r.company_id
               WHERE r.ref = :r""",
            r=ref,
        )
    return HrRound.model_validate(hr.render(r, r["company"]))


# ------------------------------------------------------- the deploy diff --
@router.get("/decisions/{ref}/diff", response_model=DiffFile, responses=E)
async def decision_diff(
    ref: str, file: str = Query(min_length=1, max_length=1000), ctx: Ctx = Depends(owner_ctx)
) -> DiffFile:
    """One file's whole patch of a deploy card (≤ 2000 lines), masked like the card's."""
    async with ctx.tx() as tx:
        d = await D.load(tx, ref)
    if d["kind"] != "deploy":
        raise ApiError(404, "not_found", "not a deploy card")
    if not (d["payload"] or {}).get("diff"):
        raise ApiError(404, "not_found", "this card has no diff")
    return DiffFile.model_validate(
        await deploy_diff.file_patch(ctx.hub, d["payload"], file, d["company_id"])
    )


# -------------------------------------------------------------------- waste --
async def _company_id(ctx: Ctx, code: str | None) -> tuple[UUID | None, str | None]:
    if code is None:
        return None, None
    co = await ctx.hub.companies.by_code(code)
    return co.id, co.code


@router.get("/treasury/waste", response_model=WasteDay | list[WasteDay], responses=E)
async def treasury_waste(
    day: date | None = None,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    company: str | None = Query(default=None, pattern=CO),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """`?day` -> one WasteDay (default yesterday); `?from&to` -> the days of
    [from, to] (at most 92). No prompt or reply text, only figures and refs."""
    cid, code = await _company_id(ctx, company)
    async with ctx.tx() as tx:
        if from_ is not None or to is not None:
            if from_ is None or to is None or to < from_ or (to - from_).days > 91:
                raise ApiError(
                    422, "validation_failed", fields={"from": "from <= to, at most 92 days"}
                )
            out = []
            d = from_
            while d <= to:
                out.append(
                    WasteDay.model_validate(WASTE.render(await WASTE.day_of(tx, d, cid), code))
                )
                d += timedelta(days=1)
            return out
        if day is None:
            tz = (
                await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
            )
            day = datetime.now(ZoneInfo(str(tz))).date() - timedelta(days=1)
        return WasteDay.model_validate(WASTE.render(await WASTE.day_of(tx, day, cid), code))


# ---------------------------------------------------------------------- ROI --
@router.get("/treasury/roi", response_model=list[RoiRow], responses=E)
async def treasury_roi(
    by: Literal["employee", "department", "company"] = "company",
    period: Literal["week", "month"] = "month",
    key: str | None = Query(default=None, pattern=r"^[0-9]{4}-[0-9]{2}(-[0-9]{2})?$"),
    company: str | None = Query(default=None, pattern=CO),
    ctx: Ctx = Depends(owner_ctx),
) -> list[RoiRow]:
    """ROI by code (§21.7): revenue, net and roi for companies only; an
    employee's or a department's are always null."""
    async with ctx.tx() as tx:
        rows = await roi.rows(tx, by, period, key, company)
    return [RoiRow.model_validate(r) for r in rows]


# -------------------------------------------------------------------- notes --
@router.get("/notes", response_model=Page[OwnerNote], responses=E)
async def list_notes(
    status: Literal["open", "promoted", "archived"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[OwnerNote]:
    """The owner's quick notes, newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            N.NOTE_SQL
            + """ WHERE (CAST(:st AS text) IS NULL OR n.status = :st)
                    AND (CAST(:q AS text) IS NULL OR n.text_md ILIKE '%' || :q || '%' OR :q = ANY(n.tags))
                    AND (CAST(:at AS timestamptz) IS NULL
                         OR (n.created_at, n.id) < (CAST(:at AS timestamptz), CAST(:aid AS uuid)))
                  ORDER BY n.created_at DESC, n.id DESC LIMIT :lim""",
            st=status,
            q=q.strip() if q and q.strip() else None,
            at=after_t,
            aid=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[OwnerNote.model_validate(N.render(r)) for r in items], next_cursor=nxt)


@router.post("/notes", response_model=OwnerNote, status_code=201, responses=E)
async def create_note(body: OwnerNoteIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A quick note (no model runs on it). Requires `Idempotency-Key`."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if body.file_id and not await tx.scalar(
            "SELECT 1 FROM files.files WHERE id = :id", id=body.file_id
        ):
            raise ApiError(422, "validation_failed", fields={"file_id": "unknown file"})
        row = await N.create(
            tx,
            holding.id,
            holding.code,
            text_md=body.text_md,
            source=body.source,
            file_id=body.file_id,
            tags=body.tags,
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="note.create",
            action_class="A1",
            target_kind="note",
            target_ref=row["ref"],
            summary=body.source,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="edit",  # the owner's own writing (owner.interactions kinds)
            action="note.create",
            target_kind="note",
            target_ref=row["ref"],
            data={"source": body.source, "tags": len(body.tags)},
        )
        result = OwnerNote.model_validate(N.render(row))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.patch(
    "/notes/{ref}", response_model=OwnerNote, responses=responses(401, 404, 409, 422, 428)
)
async def patch_note(
    ref: str, body: OwnerNotePatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> OwnerNote:
    """Text, tags or `status: "archived"`; `If-Match: <version>`. No delete."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        n = await tx.one(N.NOTE_SQL + " WHERE n.ref = :r FOR UPDATE", r=ref)
        check_version(int(n["version"]), expected)
        if body.status == "archived" and n["status"] == "promoted":
            raise ApiError(409, "validation_failed", "a promoted note stays as it is")
        row = await tx.one(
            """UPDATE owner.notes SET text_md = COALESCE(:t, text_md), tags = COALESCE(:tags, tags),
                   status = COALESCE(:st, status)
               WHERE id = :id RETURNING *""",
            t=body.text_md,
            tags=N.clean_tags(body.tags) if body.tags is not None else None,
            st=body.status,
            id=n["id"],
        )
        await ctx.audit(
            tx,
            company_id=n["company_id"],
            action="note.update",
            action_class="A1",
            target_kind="note",
            target_ref=ref,
            summary=", ".join(sorted(body.model_dump(exclude_none=True))),
        )
    return OwnerNote.model_validate(N.render(row))


def _ref_of(out: Any) -> str:
    """The ref of what an owner route made (its model, or a replayed response)."""
    if hasattr(out, "ref"):
        return str(out.ref)
    return str(json.loads(bytes(out.body))["ref"])


def _shim(request: Request, body: bytes, key: str) -> Request:
    """The same request with a deterministic Idempotency-Key, for an existing
    owner route (the note's promotion goes through it, never around it)."""
    headers = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"idempotency-key"]
    headers.append((b"idempotency-key", key.encode()))
    shim = Request({**request.scope, "headers": headers}, request.receive)
    shim._body = body
    return shim


@router.post("/notes/{ref}/promote", response_model=OwnerNote, responses=E)
async def promote_note(
    ref: str,
    body: NotePromoteIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> OwnerNote:
    """A note becomes a work item (§4; `company` required), an order (§17.4)
    or an errand (§18.3), made by the existing path, and the link is kept."""
    async with ctx.tx() as tx:
        n = await tx.one(N.NOTE_SQL + " WHERE n.ref = :r", r=ref)
    if n["status"] != "open":
        raise ApiError(409, "validation_failed", f"{ref} is {n['status']}")
    title = body.title or (" ".join(n["text_md"].split())[:80] or ref)
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"hq:note-promote:{n['id']}:{body.to}"))
    raw = await request.body()
    if body.to == "work":
        if not body.company:
            raise ApiError(422, "validation_failed", fields={"company": "required for work"})
        from hq_api.routes import work as work_routes

        w = await work_routes.create_work(
            work_routes.WorkCreate(company=body.company, title=title, brief=n["text_md"]),
            _shim(request, raw, key),
            ctx,
        )
        made = _ref_of(w)
    elif body.to == "order":
        from hq_api.routes import orders as order_routes

        o = await order_routes.create_order(
            order_routes.OrderIn(text=n["text_md"][:10000], company=body.company),
            _shim(request, raw, key),
            background,
            ctx,
        )
        made = _ref_of(o)
    else:
        from hq_api.domain import errands as R
        from hq_api.routes import errands as errand_routes

        e = await errand_routes.create_errand(
            R.ErrandIn(brief_md=n["text_md"], title_fa=title[:200]), _shim(request, raw, key), ctx
        )
        made = _ref_of(e)
    async with ctx.tx() as tx:
        row = await tx.one(
            """UPDATE owner.notes SET status = 'promoted', promoted_kind = :k, promoted_ref = :r
               WHERE id = :id AND status = 'open' RETURNING *""",
            k=body.to,
            r=str(made),
            id=n["id"],
        )
        await ctx.audit(
            tx,
            company_id=n["company_id"],
            action="note.promote",
            action_class="A1",
            target_kind="note",
            target_ref=ref,
            summary=f"{body.to} {made}",
        )
    return OwnerNote.model_validate(N.render(row))


# ------------------------------------------------------- claims and health --
@router.get("/claims", response_model=Page[Claim], responses=E)
async def list_claims(
    company: str | None = Query(default=None, pattern=CO),
    employee: str | None = Query(default=None, pattern=EMP),
    verdict: Literal["confirmed", "refuted", "unverifiable"] | None = None,
    limit: int = Query(default=30, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Claim]:
    """Checked claims, newest first (§21.9)."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            CL.CLAIM_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:emp AS text) IS NULL OR q.employee_code = :emp)
                    AND (CAST(:v AS text) IS NULL OR q.verdict = :v)
                    AND (CAST(:at AS timestamptz) IS NULL
                         OR (q.at, q.id) < (CAST(:at AS timestamptz), CAST(:aid AS uuid)))
                  ORDER BY q.at DESC, q.id DESC LIMIT :lim""",
            co=company,
            emp=employee,
            v=verdict,
            at=after_t,
            aid=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return Page(items=[Claim.model_validate(CL.render(r)) for r in items], next_cursor=nxt)


@first_router.get("/runs/health", response_model=Page[AgentHealth], responses=E)
async def runs_health(
    company: str | None = Query(default=None, pattern=CO),
    period: Literal["7d", "30d"] = "7d",
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[AgentHealth]:
    """The agent health board: one row per employee (by code), flags by rule."""
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        rows = await CL.health(tx, period, company)
    if after:
        rows = [r for r in rows if r["employee"] > str(after[0])]
    items, nxt = pagination.page(rows[: limit + 1], limit, ("employee",))
    return Page(items=[AgentHealth.model_validate(r) for r in items], next_cursor=nxt)


# --------------------------------------------------------- agents: claims --
@internal_router.post("/claims", response_model=Claim, status_code=201, responses=E)
async def claim_verdict(body: ClaimIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """`claim.verdict` (A2): the fact checker, the overseer and QC; a refuted
    claim needs evidence (422). Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "claim.verdict", {"company": ctx.who.company, "charter": ctx.who.charter})
    if body.verdict == "refuted" and not body.evidence:
        raise ApiError(
            422, "validation_failed", fields={"evidence": "a refuted claim needs evidence"}
        )
    holding = await ctx.hub.companies.holding()
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await CL.record(
            tx,
            ctx.who,
            deliverable_ref=body.deliverable,
            claim_md=body.claim_md,
            verdict=body.verdict,
            evidence=[e.model_dump() for e in body.evidence],
            protocol=body.protocol,
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="claim.verdict",
            action_class="A2",
            target_kind="claim",
            target_ref=row["ref"],
            summary=f"{body.deliverable}: {body.verdict}",
        )
        result = Claim.model_validate(CL.render(row))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# --------------------------------------------------------- the TTS one-shot --
async def _tts(ctx: Ctx, op: str) -> None:
    if ctx.who.kind != "service" or ctx.who.code != "tts":
        raise ApiError(403, "policy_denied", "the tts service only")
    await allow(ctx, op, {})


@internal_router.post(
    "/tts/claim", response_model=TtsJob, responses={**E, 204: {"description": "nothing to say"}}
)
async def tts_claim(ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The oldest pending briefing's spoken script; 204 when there is none or
    while the holding is locked (nothing is generated then)."""
    await _tts(ctx, "tts.claim")
    async with ctx.tx() as tx:
        job = await B.claim(tx)
    if job is None:
        return Response(status_code=204)
    return TtsJob(**job)


@internal_router.post(
    "/tts/{id}/done",
    response_model=Briefing,
    responses=E,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"audio/ogg": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def tts_done(
    id: UUID,
    request: Request,
    duration_s: float | None = Query(default=None, ge=0, le=7200),
    ctx: Ctx = Depends(internal_ctx),
) -> Briefing:
    """The briefing's audio (raw Ogg/Opus body, ≤ 20 MB)."""
    await _tts(ctx, "tts.done")
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime != "audio/ogg":
        raise ApiError(415, "validation_failed", fields={"Content-Type": "audio/ogg"})
    scratch = ctx.hub.storage.scratch()
    head = b""
    try:
        size = 0
        with await asyncio.to_thread(open, scratch, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_AUDIO:
                    raise ApiError(413, "validation_failed", "audio too large")
                if len(head) < 4:
                    head += chunk[:4]
                await asyncio.to_thread(fh.write, chunk)
        if not head.startswith(b"OggS"):
            raise ApiError(422, "validation_failed", fields={"body": "not an Ogg stream"})
        key, sha, size = await ctx.hub.storage.commit(scratch)
    finally:
        await asyncio.to_thread(scratch.unlink, missing_ok=True)
    async with ctx.tx() as tx:
        await B.finish(tx, id, key=key, sha=sha, size=size, duration_s=duration_s)
        return await _briefing(tx, await tx.one(B.SQL + " WHERE b.id = :id", id=id))


@internal_router.post("/tts/{id}/fail", status_code=204, response_class=Response, responses=E)
async def tts_fail(id: UUID, body: TtsFail, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The voice could not be made; after three tries the briefing is `failed`."""
    await _tts(ctx, "tts.done")
    async with ctx.tx() as tx:
        await B.fail(tx, id, body.error)
    return Response(status_code=204)
