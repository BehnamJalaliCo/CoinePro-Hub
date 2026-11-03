"""Long voice (contract §29.5): a recording of the owner sent to the hub's
speech to text in chunks (≤ 90 s each), joined into one text. Owner only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel
from temporalio.client import WorkflowFailureError

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import voice as V
from hq_api.errors import ApiError, responses
from hq_api.routes.files import (
    RAW_BODY,
    Engine,
    Prepared,
    Segment,
    Upload,
    _failure_type,
    prepare_upload,
    store_upload,
)
from hq_api.schemas import Model

router = APIRouter(tags=["files"])
E = responses(401, 403, 404, 409, 410, 413, 415, 422, 429, 503)


class SessionIn(Model):
    purpose: Literal["order", "rule", "message", "note"] = "order"


class Session(BaseModel):
    id: UUID
    purpose: str
    state: Literal["open", "finished", "expired"]
    chunks: int
    seconds: float
    # ⟨additive⟩ the limits the app records within
    max_s: int
    chunk_max_s: int = V.CHUNK_MAX_S
    expires_at: datetime


class ChunkOut(BaseModel):
    n: int
    file_id: UUID
    duration_s: float
    chunks: int
    seconds: float


class LongTranscript(BaseModel):
    text: str
    duration_s: float
    chunks: int
    segments: list[Segment]
    # ⟨additive⟩ the engine of the chunks (as /transcribe)
    engine: Engine | None = None


def _session(ctx: Ctx, s: dict[str, Any]) -> Session:
    return Session(
        id=s["id"],
        purpose=s["purpose"],
        state=s["state"],
        chunks=len(V.chunks_of(s)),
        seconds=float(s["seconds"] or 0),
        max_s=ctx.hub.settings.stt_session_max_s,
        expires_at=s["used_at"] + V.IDLE,
    )


def _speech_on(ctx: Ctx) -> None:
    if not ctx.hub.settings.stt_url:
        raise ApiError(409, "channel_not_configured", "speech recognition is off on this hub")


@router.post("/transcribe/sessions", response_model=Session, status_code=201, responses=E)
async def start_session(body: SessionIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.11⟩ §29.5 a long voice: its chunks follow (PUT …/chunks/{n}), then
    …/finish. Unused for 30 minutes it expires. 503 while speech is off.
    Requires `Idempotency-Key`."""
    _speech_on(ctx)
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await tx.one(
            """INSERT INTO owner.voice_sessions (company_id, purpose) VALUES (:co, :p) RETURNING *""",
            co=holding.id,
            p=body.purpose,
        )
        out = _session(ctx, s)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.put(
    "/transcribe/sessions/{id}/chunks/{n}",
    response_model=ChunkOut,
    responses=E,
    openapi_extra=RAW_BODY,
)
async def put_chunk(
    id: UUID,
    request: Request,
    n: int = Path(ge=0, le=999),
    ctx: Ctx = Depends(owner_ctx),
) -> ChunkOut:
    """⟨1.11⟩ §29.5 chunk n of a long voice: raw audio (the types of an
    upload), at most 90 seconds, in order (the first is 0 or 1), idempotent
    per n (the same bytes again change nothing; other bytes replace it). The
    whole session holds at most `STT_SESSION_MAX_S` seconds (413)."""
    async with ctx.tx() as tx:
        s = await V.load(tx, id)
        if s["state"] != "open":
            raise ApiError(409, "validation_failed", f"the session is {s['state']}")
        if V.place(V.chunks_of(s), n) is None:
            V.add_chunk(V.chunks_of(s), n, {"n": n, "sha256": "", "duration_s": 0}, 0)
    up = await Upload.receive(request, ctx.hub.storage.scratch(), only={"audio"})
    try:
        probed = (await prepare_upload(ctx, up)).info
        seconds = float(probed.get("duration_s") or 0)
        if seconds > V.CHUNK_MAX_S + V.SLACK_S:
            raise ApiError(
                413, "validation_failed", fields={"duration": f"at most {V.CHUNK_MAX_S} s a chunk"}
            )
        async with ctx.tx() as tx:
            s = await V.load(tx, id, lock=True)
            if s["state"] != "open":
                raise ApiError(409, "validation_failed", f"the session is {s['state']}")
            chunks = V.chunks_of(s)
            i = V.place(chunks, n)
            if i is not None and i < len(chunks) and chunks[i].get("sha256") == up.sha256:
                c = chunks[i]  # the same chunk again: as it was
                await tx.exec(
                    "UPDATE owner.voice_sessions SET used_at = now() WHERE id = :id", id=id
                )
                return ChunkOut(n=n, file_id=c["file_id"], duration_s=float(c["duration_s"]),
                                chunks=len(chunks), seconds=float(s["seconds"]))  # fmt: skip
            fid, _ = await store_upload(
                ctx, tx, up, f"voice-{str(id)[:8]}-{n:03d}", Prepared(probed), purpose=s["purpose"]
            )
            entry = {
                "n": n,
                "file_id": str(fid),
                "sha256": up.sha256,
                "duration_s": round(seconds, 2),
                "at": datetime.now(UTC).isoformat(),
            }
            chunks, total, _new = V.add_chunk(chunks, n, entry, ctx.hub.settings.stt_session_max_s)
            await tx.exec(
                """UPDATE owner.voice_sessions SET chunks = CAST(:c AS jsonb), seconds = :s,
                       used_at = now() WHERE id = :id""",
                c=json.dumps(chunks),
                s=total,
                id=id,
            )
            return ChunkOut(n=n, file_id=fid, duration_s=entry["duration_s"], chunks=len(chunks),
                            seconds=total)  # fmt: skip
    finally:
        up.discard()


async def _chunk_text(ctx: Ctx, file_id: str) -> dict[str, Any]:
    """One chunk's transcript: the stored one, else the hub's speech to text now."""
    async with ctx.tx() as tx:
        p = await tx.first(
            """SELECT p.status, p.transcript, p.stt, f.duration_s FROM files.processing p
               JOIN files.files f ON f.id = p.file_id WHERE p.file_id = CAST(:id AS uuid)""",
            id=file_id,
        )
    stt = (p or {}).get("stt") or {}
    if p is not None and p["status"] == "ready" and p["transcript"] is not None:
        return {
            "text": p["transcript"],
            "duration_s": float(stt.get("duration_s") or p["duration_s"] or 0),
            "segments": stt.get("segments") or [],
            "engine": stt.get("engine") or {},
        }
    try:
        return await workflows_client.transcribe(
            ctx.hub, file_id, ctx.hub.settings.transcribe_wait_s
        )
    except WorkflowFailureError as exc:
        if _failure_type(exc) == "SttBusy":
            raise ApiError(
                429,
                "rate_limited",
                "speech recognition is busy; try again shortly",
                headers={"Retry-After": "30"},
            ) from exc
        raise ApiError(
            503, "channel_not_configured", "speech recognition is not available on this hub"
        ) from exc
    except RuntimeError as exc:
        raise ApiError(
            503, "channel_not_configured", "speech recognition is not available on this hub"
        ) from exc


@router.post("/transcribe/sessions/{id}/finish", response_model=LongTranscript, responses=E)
async def finish_session(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> LongTranscript:
    """⟨1.11⟩ §29.5 the whole text: every chunk through the hub's speech to
    text (on demand; a chunk already transcribed is not sent again), joined
    in order and normalised as one, its segments on one time line. A
    finished session answers its text again. 503 while speech is off."""
    async with ctx.tx() as tx:
        s = await V.load(tx, id)
        if s["state"] == "finished" and s["result"]:
            return LongTranscript.model_validate(s["result"])
        chunks = V.chunks_of(s)
    if not chunks:
        raise ApiError(422, "validation_failed", fields={"chunks": "no chunk was sent"})
    _speech_on(ctx)
    parts = [(c, await _chunk_text(ctx, str(c["file_id"]))) for c in chunks]
    out = V.join(parts)
    engine = next((p["engine"] for _, p in parts if p.get("engine")), None)
    result = LongTranscript(
        text=out["text"],
        duration_s=out["duration_s"],
        chunks=out["chunks"],
        segments=[Segment(**seg) for seg in out["segments"]],
        engine=Engine(**{"name": "", "model": "", "version": "", **engine}) if engine else None,
    )
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        n = await tx.exec(
            """UPDATE owner.voice_sessions SET state = 'finished', finished_at = now(), used_at = now(),
                   result = CAST(:r AS jsonb) WHERE id = :id AND state = 'open'""",
            r=json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
            id=id,
        )
        if n:
            await ctx.audit(
                tx,
                company_id=holding.id,
                action="voice.transcribe",
                action_class="A1",
                target_kind="voice_session",
                target_ref=str(id),
                summary=f"{s['purpose']}: {len(chunks)} chunks, {out['duration_s']} s",
            )
    return result


@router.get("/transcribe/sessions/{id}", response_model=Session, responses=E)
async def get_voice_session(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Session:
    """⟨additive⟩ a long voice's session: its chunks so far (to resume after
    a dropped connection)."""
    async with ctx.tx() as tx:
        return _session(ctx, await V.load(tx, id))
