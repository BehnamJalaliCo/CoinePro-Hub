"""The voice registry and the bake-off (prompt 13 §4, contract §22.3, §22.7).

Owner:
    GET  /media/voices                 every candidate with its licence, measured numbers and samples
    POST /media/voices/{id}/score      {score: 1..10} the owner's blind listening
    POST /media/voices/{id}/activate   🔏 voice.activate (target = id); a non-commercial voice
                                       needs {accept_non_commercial: true} (422 without); an
                                       unmeasured or uninstalled one 409 not_ready
    GET  /media/voices/reference       the owner's own recorded voice (404 when none)
    POST /media/voices/reference       {file_id}: an owner audio upload of 1-3 minutes
TTS one-shot (service `tts`, beside /internal/v1/tts for the briefings):
    POST /internal/v1/voices/jobs/claim      a bake-off sample or a narration (204: none, or locked)
    POST /internal/v1/voices/jobs/{id}/done  its Ogg/Opus (raw body) ?duration_s&synth_s&peak_mb
    POST /internal/v1/voices/jobs/{id}/fail
Agent tool:
    POST /internal/v1/media/voice            media.voice (A2, the voice producer)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from hq_api import idempotency, media, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.domain import voices as V
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import FileRef, Model
from hq_api.security import stepup

router = APIRouter(tags=["media"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
VOICE_ID = r"^[a-z0-9][a-z0-9_.-]{1,60}$"
MAX_AUDIO = 20 * 1024 * 1024


class VoiceSample(BaseModel):
    script: str
    title_fa: str
    text_fa: str
    file: FileRef | None
    duration_s: float
    rtf: float
    peak_mb: float | None


class Voice(BaseModel):
    """Contract §22.2 and §22.7; ⟨1.6⟩ `installed` (the hub's TTS image runs
    it), `measured_on` (the CPU it was measured on) and `version` beside."""

    id: str
    engine: str
    name_fa: str
    licence: str
    licence_commercial: bool
    rtf: float | None
    mem_mb: float | None
    owner_score: int | None
    status: Literal["candidate", "active", "retired"]
    speaker: Literal["model", "owner"]
    clones: bool
    installed: bool
    samples: list[VoiceSample]
    note_fa: str | None
    measured_at: datetime | None
    measured_on: str | None
    version: int


class ScoreIn(Model):
    score: int = Field(ge=1, le=10)


class ActivateIn(Model):
    accept_non_commercial: bool = False


class ReferenceIn(Model):
    file_id: UUID


class Reference(BaseModel):
    file: FileRef | None
    duration_s: float
    created_at: datetime
    state: Literal["processing", "ready", "rejected"]
    reason_fa: str | None


class SpeechJob(BaseModel):
    id: UUID
    kind: Literal["sample", "narration"]
    ref: str
    engine: str
    voice: str | None
    script: str


class JobFail(Model):
    error: str = Field(min_length=1, max_length=300)


class JobDone(BaseModel):
    job: str
    state: Literal["done"]
    file: str


class VoiceIn(Model):
    ref: str = Field(pattern=r"^MI-[0-9]{4,}$")
    text_fa: str = Field(min_length=1, max_length=20000)
    voice_id: str | None = Field(default=None, pattern=VOICE_ID)


class VoiceUsed(BaseModel):
    id: str
    name_fa: str
    licence: str
    licence_commercial: bool


class Narration(BaseModel):
    job: str
    item: str
    state: Literal["queued"]
    voice: VoiceUsed
    spoken_chars: int


async def _voice(tx: Any, voice_id: str) -> Voice:
    row = await V.one(tx, voice_id)
    samples = await V.samples_of(tx, [row["id"]])
    return Voice.model_validate(V.render(row, samples.get(row["id"], [])))


# ------------------------------------------------------------------- owner --
@router.get("/media/voices", response_model=list[Voice], responses=E)
async def list_voices(ctx: Ctx = Depends(owner_ctx)) -> list[Voice]:
    """The registry (one row per engine and speaker), with the bake-off
    samples for the owner's blind listening; `licence_commercial: false` is
    shown on every use."""
    async with ctx.tx() as tx:
        return [Voice.model_validate(v) for v in await V.all_voices(tx)]


@router.post("/media/voices/{id}/score", response_model=Voice, responses=E)
async def score_voice(id: str, body: ScoreIn, ctx: Ctx = Depends(owner_ctx)) -> Voice:
    """The owner's blind listening score, 1 to 10."""
    async with ctx.tx() as tx:
        await V.score(tx, ctx.who, id, body.score)
        return await _voice(tx, id)


@router.post("/media/voices/{id}/activate", response_model=Voice, responses=E)
async def activate_voice(
    id: str, body: ActivateIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Voice:
    """🔏 `voice.activate` (target = the voice id): the voice every new
    briefing and narration speaks with. Non-commercial: only with
    `accept_non_commercial: true`; not installed or not measured: 409."""
    async with ctx.tx() as tx:
        v = await V.one(tx, id)
        if v["runtime"] is None or v["measured_at"] is None:
            raise ApiError(409, "not_ready", f"{id} is not installed and measured on the hub")
        if not v["licence_commercial"] and not body.accept_non_commercial:
            raise ApiError(
                422,
                "validation_failed",
                "a non-commercial voice needs the owner's explicit acceptance",
                fields={"accept_non_commercial": "required for a non-commercial licence"},
            )
        step = await stepup.consume(tx, request, ctx.who, "voice.activate", id)
        await V.activate(
            tx,
            ctx.who,
            id,
            accept_non_commercial=body.accept_non_commercial,
            step_up=step is not None,
        )
        return await _voice(tx, id)


@router.get("/media/voices/reference", response_model=Reference, responses=E)
async def get_reference(ctx: Ctx = Depends(owner_ctx)) -> Reference:
    """The owner's recorded voice; 404 when there is none."""
    async with ctx.tx() as tx:
        ref = await V.reference(tx)
    if ref is None:
        raise ApiError(404, "not_found", "no reference recording yet")
    return Reference.model_validate(ref)


@router.post("/media/voices/reference", response_model=Reference, status_code=201, responses=E)
async def set_reference(body: ReferenceIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner only: an audio upload of 1-3 minutes of clean speech
    (POST /files first). Kept like any owner file; never attached, never
    sent anywhere. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        result = Reference.model_validate(await V.set_reference(tx, ctx.who, body.file_id))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# ---------------------------------------------------------- TTS one-shot --
async def _tts(ctx: Ctx, op: str) -> None:
    if ctx.who.kind != "service" or ctx.who.code != "tts":
        raise ApiError(403, "policy_denied", "the tts service only")
    await allow(ctx, op, {})


@internal_router.post(
    "/voices/jobs/claim",
    response_model=SpeechJob,
    responses={**E, 204: {"description": "nothing to say, or the holding is locked"}},
)
async def claim_job(ctx: Ctx = Depends(internal_ctx)) -> Any:
    """The next bake-off sample or narration; 204 when there is none and
    always while the holding is locked (nothing is spoken then)."""
    await _tts(ctx, "voices.claim")
    async with ctx.tx() as tx:
        job = await V.claim(tx)
    if job is None:
        return Response(status_code=204)
    return SpeechJob(**job)


@internal_router.post(
    "/voices/jobs/{id}/done",
    response_model=JobDone,
    responses=E,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def job_done(
    id: UUID,
    request: Request,
    duration_s: float | None = Query(default=None, ge=0, le=7200),
    synth_s: float | None = Query(default=None, ge=0, le=36000),
    peak_mb: float | None = Query(default=None, ge=0, le=65536),
    ctx: Ctx = Depends(internal_ctx),
) -> JobDone:
    """The job's audio (raw Ogg/Opus, ≤ 20 MB) with its measurement. It goes
    through §17.1 like an upload: the type is read from the bytes, ffprobe
    gives its length, and a processing row hands it to the media worker."""
    await _tts(ctx, "voices.done")
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
                if len(head) < 64:
                    head += chunk[: 64 - len(head)]
                await asyncio.to_thread(fh.write, chunk)
        checked = media.check_type("audio/ogg", head)
        if isinstance(checked, str):
            raise ApiError(
                422, "validation_failed", fields={"body": f"not an Ogg stream ({checked})"}
            )
        try:
            info = await media.probe(str(scratch))
        except (ValueError, TimeoutError) as exc:
            raise ApiError(422, "validation_failed", fields={"body": "not playable audio"}) from exc
        seconds = float(info.get("duration_s") or duration_s or 0)
        if seconds <= 0:
            raise ApiError(422, "validation_failed", fields={"body": "no audio in it"})
        async with ctx.tx() as tx:
            j = await V.job(tx, id)
            if j["state"] not in ("claimed", "queued"):
                raise ApiError(409, "validation_failed", f"the job is {j['state']}")
        key, sha, size = await ctx.hub.storage.commit(scratch)
    finally:
        await asyncio.to_thread(scratch.unlink, missing_ok=True)
    async with ctx.tx() as tx:
        j = await V.job(tx, id)
        name = f"voice-{str(j['id'])[:8]}.ogg"  # neutral: the listening is blind
        fid = await F.insert(
            tx, company_id=j["company_id"], name=name, mime="audio/ogg", size=size, sha256=sha,
            storage_key=key, kind="audio", by_kind="service", by_code="tts", duration_s=seconds,
        )  # fmt: skip
        await tx.exec(
            """INSERT INTO files.processing (file_id, company_id, stt)
               VALUES (:f, :co, CAST('{}' AS jsonb))""",
            f=fid,
            co=j["company_id"],
        )
        out = await V.finish(
            tx, j, file_id=fid, duration_s=seconds, synth_s=synth_s, peak_mb=peak_mb
        )
    await workflows_client.file_uploaded(ctx.hub, str(fid))  # §17.1: the media worker's pass
    return JobDone.model_validate(out)


@internal_router.post(
    "/voices/jobs/{id}/fail", status_code=204, response_class=Response, responses=E
)
async def job_fail(id: UUID, body: JobFail, ctx: Ctx = Depends(internal_ctx)) -> Response:
    """The voice could not be made; after three tries the job is `failed`."""
    await _tts(ctx, "voices.done")
    async with ctx.tx() as tx:
        await V.fail(tx, await V.job(tx, id), body.error)
    return Response(status_code=204)


# ------------------------------------------------------------ media.voice --
@internal_router.post("/media/voice", response_model=Narration, status_code=202, responses=E)
async def media_voice(body: VoiceIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """`media.voice` (A2, the voice producer): the item's narration is queued
    for the TTS one-shot with the active voice (or the one named); the
    result's licence fields are shown on every use. Requires `Idempotency-Key`."""
    if ctx.who.kind != "agent" or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "media.voice", {"company": ctx.who.company, "charter": ctx.who.charter})
    # The registry is the holding's: read over every company, write the job
    # in the agent's own company only (the policy allowed nothing more).
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await V.narrate(
            tx,
            ctx.who,
            company_id=ctx.who.company_id,
            ref=body.ref,
            text_fa=body.text_fa,
            voice_id=body.voice_id,
        )
        result = Narration.model_validate(out)
        if idem:
            await idem.store(tx, 202, result.model_dump(mode="json"))
    return result
