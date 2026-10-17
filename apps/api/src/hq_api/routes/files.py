"""Owner files (prompt 6 §2, contract §17.1): upload, download with Range,
metadata. A raw body (no multipart): the type is decided by its first bytes,
the size limit of that kind holds while it streams in, an image is cleaned
(EXIF/GPS gone) before it is stored, a video or an audio file is probed for
its duration and processed by the worker (poster, key frames, sound track,
transcript). Until it is attached in a thread an upload belongs to the
holding."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError

from hq_api import idempotency, media, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.errors import ApiError, problem_response, responses
from hq_api.schemas import FileRef

router = APIRouter(tags=["files"])
E = responses(401, 403, 404, 413, 415, 422)
RAW_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}
CHUNK = 1024 * 1024
# One image is decoded at a time in this process (a 40 MP photo is ~160 MB).
_IMAGE_SLOT = asyncio.Semaphore(1)


def file_name(raw: str | None) -> str:
    """X-File-Name: percent-encoded UTF-8, no path, no control characters."""
    name = unquote(raw or "", errors="replace")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return name[:255] or "file"


class Upload:
    """A body streamed to a scratch file: its type from the first bytes, the
    limit of that kind enforced as it arrives, its SHA-256 on the way."""

    def __init__(self, path: Path, mime: str, kind: media.Kind, size: int, sha256: str) -> None:
        self.path, self.mime, self.kind, self.size, self.sha256 = path, mime, kind, size, sha256

    @classmethod
    async def receive(cls, request: Request, scratch: Path, only: set[str] | None = None) -> Upload:
        head = b""
        mime: str | None = None
        kind: media.Kind | None = None
        size = 0
        digest = hashlib.sha256()
        fh = await asyncio.to_thread(open, scratch, "wb")
        try:
            async for chunk in request.stream():
                size += len(chunk)
                digest.update(chunk)
                if kind is None:
                    head += chunk
                    if len(head) < media.HEAD_BYTES and size < 1024:
                        continue
                    got = media.check_type(request.headers.get("content-type"), head)
                    if isinstance(got, str):
                        raise ApiError(415, "validation_failed", fields={"Content-Type": got})
                    mime, kind = got
                    if only is not None and kind.kind not in only:
                        raise ApiError(
                            415, "validation_failed", fields={"Content-Type": "audio only"}
                        )
                    chunk = head
                if size > kind.max_bytes:  # held while streaming, not after
                    raise ApiError(
                        413,
                        "validation_failed",
                        fields={"body": f"at most {kind.max_bytes // media.MB} MB for {kind.kind}"},
                    )
                await asyncio.to_thread(fh.write, chunk)
            if kind is None:  # a body shorter than any signature
                got = media.check_type(request.headers.get("content-type"), head)
                if isinstance(got, str) or not head:
                    raise ApiError(
                        415, "validation_failed", fields={"Content-Type": "empty or unknown"}
                    )
                mime, kind = got
                await asyncio.to_thread(fh.write, head)
        except BaseException:
            await asyncio.to_thread(fh.close)
            await asyncio.to_thread(scratch.unlink, missing_ok=True)
            raise
        await asyncio.to_thread(fh.close)
        assert mime is not None
        assert kind is not None
        return cls(scratch, mime, kind, size, digest.hexdigest())

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)


async def store_upload(
    ctx: Ctx, tx: Any, up: Upload, name: str, *, purpose: str | None = None
) -> tuple[UUID, bool]:
    """Stores an upload for the owner (holding), in `tx` -> (file id, needs
    processing)."""
    hub = ctx.hub
    holding = await hub.companies.holding()
    info: dict[str, Any] = {}
    if up.kind.kind in ("video", "audio"):
        try:
            info = await media.probe(str(up.path))
        except (ValueError, TimeoutError) as exc:
            up.discard()
            raise ApiError(
                415, "validation_failed", fields={"body": "not a playable file"}
            ) from exc
        if up.kind.max_seconds and (info.get("duration_s") or 0) > up.kind.max_seconds:
            up.discard()
            raise ApiError(
                413,
                "validation_failed",
                fields={"duration": f"at most {up.kind.max_seconds // 60} min for {up.kind.kind}"},
            )
    if up.kind.kind == "image":
        data = await asyncio.to_thread(up.path.read_bytes)
        up.discard()
        async with _IMAGE_SLOT:
            try:
                img = await asyncio.to_thread(media.clean_image, data, up.mime)
            except (ValueError, OSError) as exc:
                raise ApiError(
                    415, "validation_failed", fields={"body": f"not a readable image ({exc})"[:120]}
                ) from exc
        key, sha = await hub.storage.put(img.original)
        thumb_key, thumb_sha = await hub.storage.put(img.thumb)
        agent_key, agent_sha = await hub.storage.put(img.agent)
        fid = await F.insert(
            tx,
            company_id=holding.id,
            name=name,
            mime=up.mime,
            size=len(img.original),
            sha256=sha,
            storage_key=key,
            kind="image",
            by_kind="owner",
            by_code=ctx.who.code,
            width=img.width,
            height=img.height,
        )
        for variant, vkey, vsha, vdata, vmime in (
            ("thumb", thumb_key, thumb_sha, img.thumb, "image/webp"),
            ("agent", agent_key, agent_sha, img.agent, "image/jpeg"),
        ):
            await F.insert(
                tx,
                company_id=holding.id,
                name=f"{variant}-{name}",
                mime=vmime,
                size=len(vdata),
                sha256=vsha,
                storage_key=vkey,
                kind="image",
                by_kind="service",
                by_code="media",
                variant=variant,
                parent_id=fid,
            )
        await _audit(ctx, tx, holding.id, fid, up)
        return fid, False
    key, sha, size = await hub.storage.commit(up.path)
    fid = await F.insert(
        tx,
        company_id=holding.id,
        name=name,
        mime=up.mime,
        size=size,
        sha256=sha,
        storage_key=key,
        kind=up.kind.kind,
        by_kind="owner",
        by_code=ctx.who.code,
        width=info.get("width"),
        height=info.get("height"),
        duration_s=info.get("duration_s"),
    )
    processing = up.kind.kind in ("video", "audio")
    if processing:
        await tx.exec(
            """INSERT INTO files.processing (file_id, company_id, stt)
               VALUES (:f, :co, CAST(:stt AS jsonb))""",
            f=fid,
            co=holding.id,
            stt=json.dumps({"purpose": purpose} if purpose else {}),
        )
    await _audit(ctx, tx, holding.id, fid, up)
    return fid, processing


async def _audit(ctx: Ctx, tx: Any, company_id: UUID, fid: UUID, up: Upload) -> None:
    await ctx.audit(
        tx,
        company_id=company_id,
        action="file.upload",
        action_class="A1",
        target_kind="file",
        target_ref=str(fid),
        summary=f"{up.kind.kind} {up.mime}, {up.size} bytes",
    )


@router.post("/files", response_model=FileRef, status_code=201, responses=E, openapi_extra=RAW_BODY)
async def upload_file(request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Owner only. Raw body, `Content-Type` = the file's type, `X-File-Name` =
    UTF-8 name, percent-encoded; `Idempotency-Key` as every POST. Images
    (jpeg, png, webp, heic ≤ 20 MB), video (mp4, webm, quicktime ≤ 200 MB,
    ≤ 10 min), audio (m4a/aac, ogg/opus, webm, wav, mpeg ≤ 25 MB, ≤ 15 min),
    pdf (≤ 30 MB). The type is checked by content, the size while streaming.
    `201 FileRef` (`status: processing` for video and audio)."""
    name = file_name(request.headers.get("x-file-name"))
    up = await Upload.receive(request, ctx.hub.storage.scratch())
    try:
        async with ctx.tx() as tx:
            # The key with the streamed body's hash; the claim rolls back with a failure.
            idem = await idempotency.claim(tx, request, ctx.who, body_sha256=up.sha256)
            if idem and idem.replay:
                return idem.replay
            fid, processing = await store_upload(ctx, tx, up, name)
            ref = F.render(await F.load(tx, fid))
            if idem:
                await idem.store(tx, 201, ref.model_dump(mode="json"))
    finally:
        up.discard()  # a no-op once the bytes moved into the store
    if processing:
        await workflows_client.file_uploaded(ctx.hub, str(fid))
    return ref


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
INLINE = ("image/", "video/", "audio/")


@router.get(
    "/files/{id}",
    response_class=Response,
    responses={
        **E,
        200: {"content": {"application/octet-stream": {}}, "description": "The file"},
        206: {"description": "A byte range of it"},
        416: {"description": "Range not satisfiable"},
    },
)
async def get_file(
    id: UUID,
    request: Request,
    variant: Literal["original", "thumb", "poster"] = Query(default="original"),
    ctx: Ctx = Depends(owner_ctx),
) -> Response:
    """The file or its `thumb`/`poster`; `Range` supported (video playback). The
    row is read under RLS before any byte is."""
    async with ctx.tx() as tx:
        f = await tx.one(
            "SELECT id, name, mime, storage_key, sha256, size FROM files.files WHERE id = :id",
            id=id,
        )
        if variant != "original":
            v = await tx.first(
                """SELECT id, name, mime, storage_key, sha256, size FROM files.files
                   WHERE parent_id = :id AND variant = :v""",
                id=id,
                v=variant,
            )
            if v is None:
                raise ApiError(404, "not_found", f"no {variant} for this file")
            f = v
    path = ctx.hub.storage.local_path(f["storage_key"])
    try:
        total = (await asyncio.to_thread(path.stat)).st_size
    except OSError as exc:
        raise ApiError(404, "not_found", "file content missing") from exc
    name = _SAFE_NAME.sub("_", f["name"])[:120] or "file"
    disposition = "inline" if f["mime"].startswith(INLINE) else "attachment"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{name}"',
        "X-Content-Sha256": f["sha256"],
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
    }
    start, end, status = 0, total - 1, 200
    raw = request.headers.get("range")
    if raw:
        m = _RANGE.match(raw.strip())
        if m is None or (not m.group(1) and not m.group(2)):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
        else:  # the last N bytes
            start = max(total - int(m.group(2)), 0)
        if start > end or start >= total:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        _read(path, start, end), status_code=status, media_type=f["mime"], headers=headers
    )


async def _read(path: Path, start: int, end: int) -> AsyncIterator[bytes]:
    fh = await asyncio.to_thread(open, path, "rb")
    try:
        await asyncio.to_thread(fh.seek, start)
        left = end - start + 1
        while left > 0:
            block = await asyncio.to_thread(fh.read, min(CHUNK, left))
            if not block:
                break
            left -= len(block)
            yield block
    finally:
        await asyncio.to_thread(fh.close)


@router.get("/files/{id}/meta", response_model=FileRef, responses=E)
async def file_meta(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> FileRef:
    """The FileRef (poll while `processing`; the stream also sends `file.ready`)."""
    async with ctx.tx() as tx:
        return F.render(await F.load(tx, id))


# ------------------------------------------------------------- transcribe --
class Segment(BaseModel):
    start_s: float
    end_s: float
    text: str


class Engine(BaseModel):
    name: str
    model: str
    version: str


class Transcript(BaseModel):
    text: str
    language: Literal["fa"] = "fa"
    duration_s: float
    confidence: float = Field(ge=0, le=1)
    segments: list[Segment]
    file_id: UUID
    engine: Engine


@router.post(
    "/transcribe",
    response_model=Transcript,
    responses=responses(401, 403, 409, 413, 415, 422, 503),
    openapi_extra=RAW_BODY,
)
async def transcribe(
    request: Request,
    purpose: Literal["message", "order", "note"] = Query(default="message"),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Owner only. Raw audio (types and limits as for uploads: ≤ 25 MB, ≤ 15 min)
    -> exact Persian text: self-hosted Whisper (nothing leaves the hub), the
    deterministic normaliser, and the light model's punctuation pass when it
    changes no more than 8% of the words. The audio is kept as a file
    (`file_id`); attach it to a message and the message is a voice transcript."""
    name = file_name(request.headers.get("x-file-name")) or "voice"
    up = await Upload.receive(request, ctx.hub.storage.scratch(), only={"audio"})
    try:
        async with ctx.tx() as tx:
            idem = await idempotency.claim(tx, request, ctx.who, body_sha256=up.sha256)
            if idem and idem.replay:
                return idem.replay
            fid, _ = await store_upload(ctx, tx, up, name, purpose=purpose)
    finally:
        up.discard()
    try:
        out = await workflows_client.transcribe(
            ctx.hub, str(fid), ctx.hub.settings.transcribe_wait_s
        )
    except WorkflowFailureError as exc:
        if _failure_type(exc) == "TooLong":
            err = ApiError(413, "validation_failed", fields={"duration": "too long"})
        else:
            err = ApiError(
                503, "channel_not_configured", "speech recognition is not available on this hub"
            )
        if idem:  # a retry with the same key gets the same answer
            async with ctx.tx() as tx:
                body = json.loads(bytes(problem_response(request, err).body))
                await idem.store(tx, err.status, body)
        raise err from exc
    result = Transcript(
        text=out["text"],
        duration_s=out["duration_s"],
        confidence=min(max(out["confidence"], 0.0), 1.0),
        segments=[Segment(**seg) for seg in out["segments"]],
        file_id=fid,
        engine=Engine(**{"name": "", "model": "", "version": "", **out["engine"]}),
    )
    if idem:
        async with ctx.tx() as tx:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


def _failure_type(exc: WorkflowFailureError) -> str | None:
    cause: Any = exc.cause
    while cause is not None:
        if isinstance(cause, ApplicationError):
            return cause.type
        cause = getattr(cause, "cause", None)
    return None
