"""The media studio (prompt 13 §2, contract §22.2 and §22.7).

The owner (prefix /api/v1):
    GET · POST  /media/series                  ?company&status&cursor · a `draft`
    GET · PUT   /media/series/{ref}            If-Match; a sealed series edited -> `proposed`
    POST        /media/series/{ref}/seal       🔏 media.series on the digest, body {digest}
    POST        /media/series/{ref}/pause · /retire
    GET · POST  /media/items                   ?company&series&state&cursor · a one-off
    GET         /media/items/{ref}
    POST        /media/items/{ref}/publish     🔏 decision.approve on its card (the card's approval)
    POST        /media/items/{ref}/unpublish   🔏 media.unpublish on the ref
    GET         /media/limits                  each publishing account's own limit and use
The agents' tools (prefix /internal/v1, through the gateway):
    POST /media/item · /media/render · /media/review · /media/series/propose
    (media.voice, POST /media/voice, is the voice registry's: routes/voices.py)
The one-shot (prefix /internal/v1, service token):
    POST /media/render/claim · GET /media/render/{id}/files/{file_id}
    POST /media/render/{id}/output · /done · /fail          (service `media`)
    (an item's narration is a job of the voice registry's queue, spoken by the
    TTS one-shot from /internal/v1/voices/jobs/*; studio.on_narration moves
    the item on when it is ready)
The one public route (prefix /public/v1, through Caddy only with the domain):
    GET  /media/{token}   one file for ≤ 15 minutes (Instagram fetches it); else 404
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hq_api import idempotency, media, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.domain import studio as S
from hq_api.domain import studio_publish as P
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Actor, FileRef, Model, Page, actor
from hq_api.security import stepup

router = APIRouter(tags=["media"])
internal_router = APIRouter(tags=["internal"])
public_router = APIRouter(tags=["media"])
E = responses(401, 403, 404, 409, 422, 428, 429)
IE = responses(401, 403, 404, 409, 422, 423)
Kind = Literal["reel", "story", "post", "carousel"]
Placement = Literal[
    "telegram_post", "telegram_story", "instagram_reel", "instagram_story", "instagram_post"
]
CheckKey = Literal["brand", "red_lines", "risk_warning", "facts", "rights", "platform", "qc"]
ItemState = Literal[
    "scripting",
    "directing",
    "composing",
    "voicing",
    "rendering",
    "checking",
    "review",
    "scheduled",
    "published",
    "waiting_owner",
    "held",
    "failed",
    "rejected",
]
ACCOUNT = r"^[a-z0-9][a-z0-9_.-]{1,40}$"
MAX_OUTPUT = 100 * 1024 * 1024
OUTPUT_TYPES = {
    "video": ("video/mp4",),
    "image": ("image/jpeg", "image/png"),
    "poster": ("image/jpeg", "image/png"),
    "captions": ("text/vtt",),
}


# ------------------------------------------------------------------ models --
class SeriesTarget(Model):
    channel: Literal["telegram", "instagram"]
    account: str = Field(pattern=ACCOUNT)
    placement: Placement


class SeriesTopics(Model):
    pool: list[str] = Field(default_factory=list, max_length=200)
    rule_fa: str | None = Field(default=None, max_length=1000)


class FormatVoice(Model):
    voice_id: str = Field(min_length=1, max_length=80)


class FormatOverlay(Model):
    cta_fa: str | None = Field(default=None, max_length=120)
    mark: bool = True


class SeriesFormat(Model):
    aspect: Literal["9:16", "4:5", "1:1", "16:9"]
    duration_s: int | None = Field(default=None, ge=3, le=180)
    voice: FormatVoice | None = None
    captions: bool = True
    music: Literal["none", "library"] = "none"
    overlay: FormatOverlay = Field(default_factory=FormatOverlay)


class SeriesIn(Model):
    company: str = Field(pattern=CODE)
    title_fa: str = Field(min_length=1, max_length=200)
    kind: Kind
    targets: list[SeriesTarget] = Field(min_length=1, max_length=10)
    schedule: str = Field(min_length=5, max_length=500)
    topics: SeriesTopics | None = None
    format: SeriesFormat
    checks: list[CheckKey] = Field(
        default_factory=lambda: cast(list[CheckKey], list(S.CHECK_KEYS)), max_length=7
    )
    auto_publish: bool = False
    max_per_day: int | None = Field(default=None, ge=1, le=20)


class SeriesProposeIn(SeriesIn):
    """series.propose: the series and why (both shown on the card)."""

    what_fa: str = Field(default="", max_length=20000)
    why_fa: str = Field(default="", max_length=20000)


class SealIn(Model):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class Today(BaseModel):
    made: int
    published: int


class Series(BaseModel):
    id: UUID
    ref: str
    company: str
    title_fa: str
    kind: str
    targets: list[dict[str, Any]]
    schedule: str
    topics: dict[str, Any] | None
    format: dict[str, Any]
    checks: list[str]
    auto_publish: bool
    max_per_day: int
    status: str
    digest: str
    version: int
    sealed_at: datetime | None
    proposed_by: Actor | None = None
    decision_ref: str | None = None
    next_at: list[datetime] = Field(default_factory=list)
    today: Today | None = None
    items_total: int = 0
    created_at: datetime
    updated_at: datetime
    status_note_fa: str | None = None


class ItemIn(Model):
    company: str = Field(pattern=CODE)
    kind: Literal["reel", "story", "post", "carousel", "design"]
    brief_md: str = Field(min_length=1, max_length=20000)
    series: str | None = Field(default=None, pattern=r"^SR-[0-9]{4,}$")
    title_fa: str | None = Field(default=None, min_length=1, max_length=300)


class Composition(BaseModel):
    format: str
    sha256: str
    by: Actor | None
    version: int


class Cost(BaseModel):
    tokens: int
    usd: Decimal


class MediaItem(BaseModel):
    id: UUID
    ref: str
    company: str
    series: str | None
    kind: str
    title_fa: str
    state: str
    script: dict[str, Any] | None
    direction: dict[str, Any] | None
    composition: Composition | None
    assets: list[FileRef]
    voice: FileRef | None
    render: FileRef | None
    captions: FileRef | None
    checks: list[dict[str, Any]]
    qc: dict[str, Any] | None
    publish: list[dict[str, Any]]
    decision_ref: str | None
    ai_generated: bool = True
    cost: Cost
    created_at: datetime
    updated_at: datetime
    version: int
    brief_md: str | None = None
    topic_fa: str | None = None
    deliverable_ref: str | None = None
    state_note_fa: str | None = None
    pages: list[FileRef] = Field(default_factory=list)
    publish_at: datetime | None = None


class PlatformLimit(BaseModel):
    account: str
    channel: str
    company: str
    per_24h: int | None
    used_24h: int
    resets_at: datetime | None
    note_fa: str | None


class StepIn(Model):
    """media.item (agents/tools.md)."""

    ref: str = Field(pattern=r"^MI-[0-9]{4,}$")
    step: Literal["script", "direction", "composition", "brief"]
    script: dict[str, Any] | None = None
    direction: dict[str, Any] | None = None
    composition: dict[str, Any] | None = None
    brief_md: str | None = Field(default=None, max_length=20000)


class RefIn(Model):
    ref: str = Field(pattern=r"^MI-[0-9]{4,}$")


class MediaReviewIn(Model):
    ref: str = Field(pattern=r"^MI-[0-9]{4,}$")
    verdict: Literal["pass", "changes", "reject"]
    note_md: str = Field(default="", max_length=20000)


class ToolOut(BaseModel):
    ref: str
    state: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    hint_fa: str | None = None


class RenderJob(BaseModel):
    id: UUID
    item: str
    company: str
    kind: str
    purpose: str
    composition: dict[str, Any]
    outputs: list[dict[str, Any]]
    duration_s: float | None
    fps: int
    assets: list[dict[str, Any]]
    voice: dict[str, Any] | None
    music: None = None
    captions: list[dict[str, Any]]
    overlay: dict[str, Any]
    brand: dict[str, Any]
    safe_zone: dict[str, float]
    limits: dict[str, Any]


class RenderDone(Model):
    metrics: dict[str, Any] = Field(default_factory=dict)
    violations: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class RenderFail(Model):
    error: str = Field(min_length=1, max_length=500)


class OutputOut(BaseModel):
    file_id: UUID


# ------------------------------------------------------------- rendering --
def _series(v: dict[str, Any]) -> Series:
    return Series(
        **{
            k: v[k]
            for k in (
                "id",
                "ref",
                "company",
                "title_fa",
                "kind",
                "targets",
                "schedule",
                "topics",
                "format",
                "checks",
                "auto_publish",
                "max_per_day",
                "status",
                "digest",
                "version",
                "sealed_at",
                "created_at",
                "updated_at",
            )
        },
        proposed_by=actor(v["proposed_by_kind"], v["proposed_by_code"]),
        decision_ref=v.get("decision_ref"),
        next_at=v.get("next_at") or [],
        today=Today(**v["today"]) if v.get("today") else None,
        items_total=int(v.get("items_total") or 0),
        status_note_fa=v.get("status_note_fa"),
    )


async def _item(tx: Any, r: dict[str, Any]) -> MediaItem:
    ids = [*(r.get("assets") or [])]
    for k in ("voice_file_id", "render_file_id", "captions_file_id"):
        if r.get(k):
            ids.append(r[k])
    page_ids = [UUID(p["file_id"]) for p in r.get("pages") or [] if p.get("file_id")]
    refs = await F.refs(tx, ids + page_ids)
    work_refs = [s["work"] for s in r.get("steps") or [] if s.get("work")]
    cost = await tx.first(
        "SELECT COALESCE(sum(tokens_used), 0) AS t, COALESCE(sum(usd_used), 0) AS u FROM work.work WHERE ref = ANY(:r)",
        r=work_refs,
    )
    by = None
    if r.get("composition_by_code"):
        by = actor(r["composition_by_kind"], r["composition_by_code"])
    return MediaItem(
        id=r["id"],
        ref=r["ref"],
        company=r["company"],
        series=r.get("series_ref"),
        kind=r["kind"],
        title_fa=r["title_fa"],
        state=r["state"],
        script=r.get("script"),
        direction=r.get("direction"),
        composition=Composition(
            format=r["composition_format"],
            sha256=r["composition_sha256"],
            by=by,
            version=int(r["composition_n"]),
        )
        if r.get("composition_sha256")
        else None,
        assets=[refs[i] for i in r.get("assets") or [] if i in refs],
        voice=refs.get(r["voice_file_id"]) if r.get("voice_file_id") else None,
        render=refs.get(r["render_file_id"]) if r.get("render_file_id") else None,
        captions=refs.get(r["captions_file_id"]) if r.get("captions_file_id") else None,
        checks=list(r.get("checks") or []),
        qc=r.get("qc"),
        publish=list(r.get("publish") or []),
        decision_ref=r.get("decision_ref"),
        cost=Cost(tokens=int(cost["t"] or 0), usd=Decimal(cost["u"] or 0)),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        version=r["version"],
        brief_md=r.get("brief_md"),
        topic_fa=r.get("topic_fa"),
        deliverable_ref=r.get("deliverable_ref"),
        state_note_fa=r.get("state_note_fa"),
        pages=[refs[i] for i in page_ids if i in refs],
        publish_at=r.get("publish_at"),
    )


async def _audit(
    ctx: Ctx,
    tx: Any,
    company_id: UUID,
    action: str,
    cls: str,
    kind: str,
    ref: str,
    summary: str = "",
    step_up: bool = False,
) -> None:
    await ctx.audit(
        tx,
        company_id=company_id,
        action=action,
        action_class=cls,
        target_kind=kind,
        target_ref=ref,
        summary=summary,
        step_up=step_up,
    )


# ----------------------------------------------------------------- series --
@router.get("/media/series", response_model=Page[Series], responses=E)
async def list_series(
    company: str | None = Query(default=None, pattern=CODE),
    status: Literal["draft", "proposed", "sealed", "paused", "retired"] | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Series]:
    """Newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.SERIES_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:st AS text) IS NULL OR s.status = :st)
                    AND (CAST(:t AS timestamptz) IS NULL
                         OR (s.created_at, s.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
                  ORDER BY s.created_at DESC, s.id DESC LIMIT :lim""",
            co=company,
            st=status,
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=[_series(await S.series_view(tx, r)) for r in items], next_cursor=nxt)


@router.post("/media/series", response_model=Series, status_code=201, responses=E)
async def create_series(body: SeriesIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A `draft`: nothing runs until the owner seals it. Requires `Idempotency-Key`."""
    co = await ctx.hub.companies.by_code(body.company)
    if co.kind == "holding":
        raise ApiError(422, "validation_failed", fields={"company": "an operating company"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await S.create_series(
            tx, ctx.who, co.id, co.code, body.model_dump(mode="json"), status="draft"
        )
        await _audit(ctx, tx, co.id, "series.create", "A1", "series", s["ref"], s["digest"][:16])
        out = _series(await S.series_view(tx, s))
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/media/series/{ref}", response_model=Series, responses=E)
async def get_series(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Series:
    """One series with its next runs and today's count (§22.7)."""
    async with ctx.tx() as tx:
        return _series(await S.series_view(tx, await S.load_series(tx, ref)))


@router.put("/media/series/{ref}", response_model=Series, responses=E)
async def put_series(
    ref: str, body: SeriesIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Series:
    """`If-Match: <version>`. A sealed (or paused) series edited goes back to
    `proposed`: its seal no longer covers it, nothing publishes by itself until
    it is sealed again."""
    expected = if_match(request)
    async with ctx.tx() as tx:
        s = await S.load_series(tx, ref, lock=True)
        check_version(s["version"], expected)
        out = await S.update_series(tx, s, body.model_dump(mode="json"))
        await _audit(
            ctx,
            tx,
            s["company_id"],
            "series.update",
            "A1",
            "series",
            ref,
            f"{s['status']} -> {out['status']}",
        )
        return _series(await S.series_view(tx, out))


@router.post("/media/series/{ref}/seal", response_model=Series, responses=E)
async def seal_series(
    ref: str, body: SealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Series:
    """🔏 step-up `media.series`, target = the series `digest` (the body
    repeats it; a series changed since -> 409 version_conflict). Resumes a
    paused series and decides its pending media_series card."""
    async with ctx.tx() as tx:
        s = await S.load_series(tx, ref, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "media.series", body.digest)
        out = await S.seal_series(tx, ctx.hub, ctx.who, s, body.digest, su)
        await _audit(
            ctx,
            tx,
            s["company_id"],
            "series.seal",
            "A3",
            "series",
            ref,
            body.digest[:16],
            True,
        )
        await ctx.interaction(
            tx,
            company_id=s["company_id"],
            kind="decision",
            action="series.seal",
            target_kind="series",
            target_ref=ref,
            data={"digest": body.digest},
        )
        view = _series(await S.series_view(tx, out))
    if out.get("decision_ref"):
        await workflows_client.decision_decided(ctx.hub, out["decision_ref"])
    return view


@router.post("/media/series/{ref}/pause", response_model=Series, responses=E)
async def pause_series(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Series:
    """No step-up (stopping is always safe); sealing it again resumes it."""
    async with ctx.tx() as tx:
        s = await S.load_series(tx, ref, lock=True)
        out = await S.set_series_status(
            tx, s, "paused", "مالک متوقف کرد؛ با مُهر دوباره ادامه میدهد."
        )
        await _audit(ctx, tx, s["company_id"], "series.pause", "A1", "series", ref)
        return _series(await S.series_view(tx, out))


@router.post("/media/series/{ref}/retire", response_model=Series, responses=E)
async def retire_series(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Series:
    """No step-up: a retired series makes nothing and stays for the record."""
    async with ctx.tx() as tx:
        s = await S.load_series(tx, ref, lock=True)
        out = await S.set_series_status(tx, s, "retired", None)
        await _audit(ctx, tx, s["company_id"], "series.retire", "A1", "series", ref)
        return _series(await S.series_view(tx, out))


# ------------------------------------------------------------------ items --
@router.get("/media/items", response_model=Page[MediaItem], responses=E)
async def list_items(
    company: str | None = Query(default=None, pattern=CODE),
    series: str | None = Query(default=None, pattern=r"^SR-[0-9]{4,}$"),
    state: ItemState | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[MediaItem]:
    """Newest first."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.ITEM_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:sr AS text) IS NULL OR s.ref = :sr)
                    AND (CAST(:st AS text) IS NULL OR i.state = :st)
                    AND (CAST(:t AS timestamptz) IS NULL
                         OR (i.created_at, i.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
                  ORDER BY i.created_at DESC, i.id DESC LIMIT :lim""",
            co=company,
            sr=series,
            st=state,
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=[await _item(tx, r) for r in items], next_cursor=nxt)


@router.get("/media/items/{ref}", response_model=MediaItem, responses=E)
async def get_item(ref: str, ctx: Ctx = Depends(owner_ctx)) -> MediaItem:
    """One item: every step's record, its files, checks, review and publish rows."""
    async with ctx.tx() as tx:
        return await _item(tx, await S.load_item(tx, ref))


@router.post("/media/items", response_model=MediaItem, status_code=201, responses=E)
async def create_item(body: ItemIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A one-off (it always ends as a card); `design` is a UI mockup for the
    CTO, never published. Requires `Idempotency-Key`."""
    co = await ctx.hub.companies.by_code(body.company)
    if co.kind == "holding":
        raise ApiError(422, "validation_failed", fields={"company": "an operating company"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        series = None
        if body.series:
            series = await S.load_series(tx, body.series)
            if series["company_id"] != co.id:
                raise ApiError(
                    422, "validation_failed", fields={"series": "a series of this company"}
                )
            if body.kind == "design":
                raise ApiError(
                    422, "validation_failed", fields={"series": "a design has no series"}
                )
        title = body.title_fa or body.brief_md.strip().splitlines()[0][:120]
        item = await S.create_item(
            tx,
            ctx.hub,
            ctx.who,
            company_id=co.id,
            company=co.code,
            kind=body.kind,
            title_fa=title,
            brief_md=body.brief_md,
            series=series,
            one_off=True,
        )
        await _audit(
            ctx, tx, co.id, "media_item.create", "A1", "media_item", item["ref"], body.kind
        )
        out = await _item(tx, item)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post("/media/items/{ref}/publish", response_model=MediaItem, responses=E)
async def publish_item(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.6.1⟩ The one path to publish outside a sealed series is the item's
    `media_publish` card: this approves it (🔏 `decision.approve` on the
    card's ref, `Idempotency-Key`), exactly as the cartable does. An item
    without a pending card: its series not sealed -> 409 series_not_sealed."""
    async with ctx.tx() as tx:
        item = await S.load_item(tx, ref)
        card = await tx.first(
            "SELECT ref FROM cartable.decisions WHERE id = :d AND status = 'pending'",
            d=item.get("decision_id"),
        )
    if card is None:
        if item.get("series_ref") and item.get("series_status") != "sealed":
            raise ApiError(
                409, "series_not_sealed", f"{item['series_ref']} is {item.get('series_status')}"
            )
        raise ApiError(409, "validation_failed", f"{ref} is {item['state']}: no card waits for you")
    from hq_api.routes.decisions import _decide

    await _decide(ctx, request, card["ref"], "approved", note=None)
    async with ctx.tx() as tx:
        return await _item(tx, await S.load_item(tx, ref))


@router.post("/media/items/{ref}/unpublish", response_model=MediaItem, responses=E)
async def unpublish_item(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> MediaItem:
    """🔏 step-up `media.unpublish`, target = the ref. Deletes the post through
    the same API where the platform allows it (a Telegram channel message);
    otherwise its row says `remove_by_hand`. The item becomes `rejected`."""
    async with ctx.tx() as tx:
        item = await S.load_item(tx, ref, lock=True)
        su = await stepup.consume(tx, request, ctx.who, "media.unpublish", ref)
        out = await P.request_unpublish(tx, item, su)
        await _audit(
            ctx, tx, item["company_id"], "media.unpublish", "A3", "media_item", ref, step_up=True
        )
        view = await _item(tx, out)
    await workflows_client.media(ctx.hub, "MediaUnpublish", ref)
    return view


@router.get("/media/limits", response_model=list[PlatformLimit], responses=E)
async def platform_limits(ctx: Ctx = Depends(owner_ctx)) -> list[PlatformLimit]:
    """Each operating company's publishing accounts (`telegram-<co>`,
    `instagram-<co>`): the platform's own 24-hour limit and its use."""
    async with ctx.tx() as tx:
        return [PlatformLimit(**r) for r in await P.limits(tx, getattr(ctx.hub, "bao", None))]


# --------------------------------------------------------- agents' tools --
def _agent(ctx: Ctx) -> UUID:
    """The calling agent's company (an agent only)."""
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    return ctx.who.company_id


async def _work_of_run(tx: Any, ctx: Ctx) -> UUID | None:
    if not ctx.who.run_id:
        return None
    w: UUID | None = await tx.scalar(
        "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid)", r=ctx.who.run_id
    )
    return w


@internal_router.post("/media/item", response_model=ToolOut, responses=IE)
async def tool_item(body: StepIn, ctx: Ctx = Depends(internal_ctx)) -> ToolOut:
    """media.item (A1): the current step of an item, by the role that owns it.
    A composition is checked against the schema before it is stored (422
    names the rule)."""
    co_id = _agent(ctx)
    await allow(ctx, "media.item", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        out = await S.write_step(
            tx, ctx.hub, ctx.who, body.model_dump(mode="json", exclude_none=True)
        )
        await _audit(ctx, tx, co_id, "media.item", "A1", "media_item", body.ref, body.step)
    return ToolOut(
        ref=out["ref"],
        state=out["state"],
        detail={"step": body.step, "composition": out.get("composition")},
        hint_fa=out.get("hint"),
    )


@internal_router.post("/media/render", response_model=ToolOut, responses=IE)
async def tool_render(body: RefIn, ctx: Ctx = Depends(internal_ctx)) -> ToolOut:
    """media.render (A2): a preview of the item's composition in the sandboxed
    render worker; the files arrive on the item."""
    co_id = _agent(ctx)
    await allow(ctx, "media.render", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        out = await S.request_render(tx, ctx.hub, ctx.who, body.ref)
        await _audit(ctx, tx, co_id, "media.render", "A2", "media_item", body.ref)
    return ToolOut(
        ref=body.ref,
        detail={"queued": out["queued"], "purpose": out["purpose"]},
        hint_fa=out["hint"],
    )


@internal_router.post("/media/review", response_model=ToolOut, responses=IE)
async def tool_review(body: MediaReviewIn, ctx: Ctx = Depends(internal_ctx)) -> ToolOut:
    """media.review (A2, the media director only): the `qc` check. Never publishes."""
    co_id = _agent(ctx)
    await allow(ctx, "media.review", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        out = await S.review(tx, ctx.hub, ctx.who, body.model_dump(mode="json"))
        await _audit(ctx, tx, co_id, "media.review", "A2", "media_item", body.ref, body.verdict)
    return ToolOut(ref=body.ref, state=out["state"], detail={"verdict": body.verdict})


@internal_router.post("/media/series/propose", response_model=ToolOut, responses=IE)
async def tool_series(
    body: SeriesProposeIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """series.propose (A1, the media director): a `proposed` series and its
    `media_series` card for the owner's seal. Requires `Idempotency-Key`."""
    co_id = _agent(ctx)
    await allow(ctx, "series.propose", {"company": ctx.who.company, "charter": ctx.who.charter})
    if body.company != ctx.who.company:
        raise ApiError(422, "validation_failed", fields={"company": "your own company"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await S.propose_series(
            tx,
            ctx.who,
            co_id,
            ctx.who.company,
            body.model_dump(mode="json"),
            await _work_of_run(tx, ctx),
        )
        await _audit(ctx, tx, co_id, "series.propose", "A1", "series", s["ref"], s["card"])
        out = ToolOut(
            ref=s["ref"],
            state=s["status"],
            detail={"card": s["card"], "digest": s["digest"]},
            hint_fa="کارت برای مُهر مالک رفت؛ تا مُهر هیچ آیتمی ساخته نمیشود.",
        )
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    if s.get("card"):
        await workflows_client.decision_created(ctx.hub, s["card"])
    return out


# -------------------------------------------------- the render one-shot --
async def _service(ctx: Ctx, code: str, op: str) -> None:
    if ctx.who.kind != "service" or ctx.who.code != code:
        raise ApiError(403, "policy_denied", f"the {code} service only")
    await allow(ctx, op, {})


@internal_router.post(
    "/media/render/claim",
    response_model=RenderJob,
    responses={**IE, 204: {"description": "nothing to render"}},
)
async def render_claim(ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The oldest queued render job; 204 while there is none, while the
    holding is locked, or while the job's company is locked."""
    await _service(ctx, "media", "media.jobs")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        job = await S.claim_render(tx, ctx.hub)
    if job is None:
        return Response(status_code=204)
    return RenderJob(**job)


@internal_router.get("/media/render/{id}/files/{file_id}", responses=IE)
async def render_file(id: UUID, file_id: UUID, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The raw bytes of one asset (or the voice) the claimed job lists."""
    await _service(ctx, "media", "media.jobs")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        j = await S.job_for(tx, id)
        if str(file_id) not in S.job_file_ids(j):
            raise ApiError(404, "not_found")
        f = await F.load(tx, file_id)
    data = await ctx.hub.storage.get(f["storage_key"])
    return Response(content=data, media_type=f["mime"])


@internal_router.post(
    "/media/render/{id}/output",
    response_model=OutputOut,
    status_code=201,
    responses=IE,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def render_output(
    id: UUID,
    request: Request,
    name: str = Query(pattern=r"^[a-z][a-z0-9_-]{0,30}$"),
    kind: Literal["video", "image", "poster", "captions"] = Query(),
    width: int | None = Query(default=None, ge=1, le=8192),
    height: int | None = Query(default=None, ge=1, le=16384),
    duration_s: float | None = Query(default=None, ge=0, le=900),
    ctx: Ctx = Depends(internal_ctx),
) -> OutputOut:
    """One output file of the claimed job (raw body). Its type is checked by
    its bytes, its size while it streams (the output's own cap), a video by
    ffprobe (§17.1's processing); a poster becomes the video's `poster` variant."""
    await _service(ctx, "media", "media.jobs")
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime not in OUTPUT_TYPES[kind]:
        raise ApiError(
            415, "validation_failed", fields={"Content-Type": " or ".join(OUTPUT_TYPES[kind])}
        )
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        j = await S.job_for(tx, id)
    spec_out = next((o for o in (j["spec"] or {}).get("outputs") or [] if o["name"] == name), None)
    if spec_out is None:
        raise ApiError(422, "validation_failed", fields={"name": "not an output of this job"})
    cap = (
        min(int(spec_out.get("max_bytes") or MAX_OUTPUT), MAX_OUTPUT)
        if kind in ("video", "image")
        else 5 * 1024 * 1024
    )
    scratch = ctx.hub.storage.scratch()
    head = b""
    try:
        size = 0
        with await asyncio.to_thread(open, scratch, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > cap:
                    raise ApiError(413, "validation_failed", f"too_large: over {cap} bytes")
                if len(head) < 64:
                    head += chunk[: 64 - len(head)]
                await asyncio.to_thread(fh.write, chunk)
        _sniff(kind, mime, head)
        if kind == "video":
            info = await media.probe(str(scratch))
            duration_s = info.get("duration_s") or duration_s
            width, height = info.get("width") or width, info.get("height") or height
        key, sha, size = await ctx.hub.storage.commit(scratch)
    finally:
        await asyncio.to_thread(scratch.unlink, missing_ok=True)
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        j = await S.job_for(tx, id)
        item = await tx.one("SELECT ref FROM media.items WHERE id = :i", i=j["item_id"])
        parent = None
        if kind == "poster":
            parent = next(
                (
                    UUID(f["file_id"])
                    for f in j["files"] or []
                    if f["name"] == name and f["kind"] == "video"
                ),
                None,
            )
        fid = await F.insert(
            tx,
            company_id=j["company_id"],
            name=f"{item['ref']}-{name}.{_ext(mime)}",
            mime=mime,
            size=size,
            sha256=sha,
            storage_key=key,
            kind="document" if kind == "captions" else ("video" if kind == "video" else "image"),
            by_kind="service",
            by_code="media",
            variant="poster" if parent else "original",
            parent_id=parent,
            width=width,
            height=height,
            duration_s=duration_s,
        )
        await S.render_output(
            tx,
            j,
            name=name,
            kind=kind,
            file_id=fid,
            width=width,
            height=height,
            duration_s=duration_s,
            size=size,
        )
    return OutputOut(file_id=fid)


def _sniff(kind: str, mime: str, head: bytes) -> None:
    ok = {
        "video/mp4": head[4:8] == b"ftyp",
        "image/jpeg": head[:3] == b"\xff\xd8\xff",
        "image/png": head[:8] == b"\x89PNG\r\n\x1a\n",
        "text/vtt": head.lstrip(b"\xef\xbb\xbf")[:6] == b"WEBVTT",
    }.get(mime, False)
    if not ok:
        raise ApiError(422, "validation_failed", fields={"body": f"not a {mime} file"})


def _ext(mime: str) -> str:
    return {"video/mp4": "mp4", "image/jpeg": "jpg", "image/png": "png", "text/vtt": "vtt"}.get(
        mime, "bin"
    )


@internal_router.post(
    "/media/render/{id}/done", status_code=204, response_class=Response, responses=IE
)
async def render_done(id: UUID, body: RenderDone, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The job finished; `violations` are requests the page tried at runtime
    (aborted): the item goes back to its composer with them."""
    await _service(ctx, "media", "media.jobs")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        j = await S.job_for(tx, id)
        await S.render_done(tx, ctx.hub, j, body.metrics, body.violations)
    return Response(status_code=204)


@internal_router.post(
    "/media/render/{id}/fail", status_code=204, response_class=Response, responses=IE
)
async def render_fail(id: UUID, body: RenderFail, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The job could not render; retried up to three times (not a schema refusal)."""
    await _service(ctx, "media", "media.jobs")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        j = await S.job_for(tx, id)
        await S.render_failed(tx, ctx.hub, j, body.error)
    return Response(status_code=204)


# ------------------------------------------------------- the public file --
@public_router.api_route("/media/{token}", methods=["GET", "HEAD"], include_in_schema=False)
async def public_file(token: str, request: Request) -> Response:
    """One render file for ≤ 15 minutes, by a signed token (Instagram fetches
    it from here); any other URL, an expired or forged token: 404 (no
    existence oracle)."""
    hub = request.app.state.hub
    file_id = P.verify(hub, token)
    if file_id is None:
        return _not_found()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        f = await tx.first(
            """SELECT f.storage_key, f.mime, f.size FROM files.files f
               WHERE f.id = :id AND f.created_by_kind = 'service' AND f.created_by_code IN ('media', 'substitutes')""",
            id=file_id,
        )
    if f is None:
        return _not_found()
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Length": str(f["size"]),
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type=f["mime"], headers=headers)
    path = hub.storage.local_path(f["storage_key"])

    def chunks() -> Any:
        with open(path, "rb") as fh:
            while block := fh.read(1024 * 1024):
                yield block

    return StreamingResponse(chunks(), media_type=f["mime"], headers=headers)


def _not_found() -> Response:
    return Response(
        status_code=404,
        content=json.dumps({"status": 404, "code": "not_found"}),
        media_type="application/json",
    )
