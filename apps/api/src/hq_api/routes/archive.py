"""The archive of record (prompt 14, contract §23): the owner's API.

Every transaction here first sets the reader's clearance (archive.clearance,
SET LOCAL): the owner sees everything, and the database's policies decide.
Uploads arrive through §17.1 (`POST /files`); intake scans, hashes and
extracts their text before any record holds them (`422 secret_in_document`).
The owner files, seals (🔏 archive.seal on the manifest), declassifies
(🔏 archive.declassify), changes the schema (🔏 archive.schema / clearance on
the body hash), releases a hold (🔏 archive.hold.release) and seals the
disposal card; nothing is deleted except by that card's seal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from hq_api import http, idempotency
from hq_api.archive import cards as AC
from hq_api.archive import clearance as CL
from hq_api.archive import fixity as FX
from hq_api.archive import records as R
from hq_api.archive import reminders as RM
from hq_api.archive import retention as RT
from hq_api.archive import schema as SC
from hq_api.archive import search as SE
from hq_api.archive import sources as SRC
from hq_api.archive import store as ST
from hq_api.archive import vocab as V
from hq_api.archive.common import J, dumps, invalid
from hq_api.context import Ctx, owner_ctx
from hq_api.errors import ApiError, responses
from hq_api.routes.files import disposition
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["archive"])
E = responses(401, 403, 404, 409, 422, 423)
AR = r"^AR-[0-9]{6,}$"
CO = r"^[A-Z][A-Z0-9]{1,9}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"
State = Literal["draft", "filed", "sealed", "superseded", "disposed"]


# ------------------------------------------------------------------ models --
class Target(Model):
    kind: str = Field(pattern=r"^[a-z_]{2,30}$")
    ref: str = Field(min_length=1, max_length=80)


class LinkIn(Model):
    kind: str = Field(pattern=KEY)
    to: Target


class PartyRole(Model):
    party: str = Field(pattern=r"^PT-[0-9]{4,}$")
    role_fa: str = Field(default="", max_length=120)


class RecordIn(Model):
    scope: str = Field(pattern=CO)
    class_: str | None = Field(default=None, alias="class", pattern=KEY)
    title_fa: str = Field(min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str | None = Field(default=None, pattern=KEY)
    folder: str | None = Field(default=None, pattern=r"^FP-[0-9]{4,}$")
    file_ids: list[UUID] = Field(default_factory=list, max_length=20)
    parties: list[PartyRole] = Field(default_factory=list, max_length=50)
    links: list[LinkIn] = Field(default_factory=list, max_length=20)
    file: bool = False
    note_fa: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RecordPatch(Model):
    title_fa: str | None = Field(default=None, min_length=1, max_length=300)
    metadata: dict[str, Any] | None = None
    folder: str | None = Field(default=None, pattern=r"^FP-[0-9]{4,}$")
    parties: list[PartyRole] | None = None
    level: str | None = Field(default=None, pattern=KEY)
    class_: str | None = Field(default=None, alias="class", pattern=KEY)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class VersionIn(Model):
    file_ids: list[UUID] = Field(min_length=1, max_length=20)
    note_fa: str | None = Field(default=None, max_length=2000)


class SealIn(Model):
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImportIn(Model):
    scope: str = Field(pattern=CO)
    file_ids: list[UUID] = Field(min_length=1, max_length=50)
    class_: str | None = Field(default=None, alias="class", pattern=KEY)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class IntakeIn(Model):
    file_ids: list[UUID] = Field(min_length=1, max_length=20)


class PartyIn(Model):
    kind: str = Field(pattern=KEY)
    name_fa: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    identifiers: dict[str, Any] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list, max_length=200)


class PartyPatch(Model):
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    identifiers: dict[str, Any] | None = None
    scopes: list[str] | None = None
    status: Literal["active", "retired"] | None = None


class HoldScope(Model):
    records: list[str] | None = Field(default=None, max_length=500)
    folders: list[str] | None = Field(default=None, max_length=100)
    classes: list[str] | None = Field(default=None, max_length=100)
    parties: list[str] | None = Field(default=None, max_length=100)
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HoldIn(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    case: str | None = Field(default=None, pattern=r"^LC-[0-9]{4,}$")
    reason_md: str = Field(min_length=1, max_length=20000)
    scope: HoldScope


class RetireIn(Model):
    part: str = Field(pattern=r"^[a-z_]{2,20}$")
    key: str = Field(min_length=1, max_length=80)
    version: int = Field(ge=1)


class Record(BaseModel):
    """Record (contract §23.1, §23.12): what the reader may see of it."""

    model_config = ConfigDict(extra="allow")
    ref: str
    scope: str
    title_fa: str
    level: str
    state: State
    version: int


class SchemaPut(BaseModel):
    part: str
    key: str
    version: int | None
    impact: dict[str, int]
    row: dict[str, Any] | None
    dry_run: bool = False


class SearchOut(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class IntakeOut(BaseModel):
    files: list[dict[str, Any]]
    suggestion: dict[str, Any] | None


# ----------------------------------------------------------------- helpers --
def _render_ok(x: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(dumps(x))
    return out


async def _record_out(ctx: Ctx, tx: Any, ref: str, *, full: bool = True) -> dict[str, Any]:
    r = await R.load(tx, ref)
    return _render_ok(await R.render(tx, r, CL.EVERYTHING, full=full))


def _intake_out(it: ST.Intake) -> dict[str, Any]:
    return {
        "file_id": str(it.file_id),
        "name": it.name,
        "mime": it.mime,
        "size_bytes": it.size,
        "sha256": it.sha256,
        "pages": it.pages,
        "text_state": it.text_state,
        "ocr_confidence": it.ocr_confidence,
        "low_confidence_pages": it.low_pages,
        "ocr_queued": it.ocr_wanted,
    }


def _txf(ctx: Ctx) -> Any:
    async def scoped() -> Any:
        return ctx.hub.db.tx(await ctx.hub.companies.ids())

    class _Tx:
        async def __aenter__(self) -> Any:
            self._cm = await scoped()
            tx = await self._cm.__aenter__()
            await CL.full(tx)
            return tx

        async def __aexit__(self, *exc: Any) -> Any:
            return await self._cm.__aexit__(*exc)

    return lambda: _Tx()


async def _after(ctx: Ctx, intakes: list[ST.Intake]) -> None:
    """After the record's transaction committed: the owner's waiting uploads
    are the archive's now (their plaintext and variants go); every object a
    committed transaction destroyed is removed."""
    txf = _txf(ctx)
    for it in intakes:
        if it.waiting:
            async with txf() as tx:
                f = await tx.first(ST.UPLOAD_SQL + " WHERE f.id = :id", id=it.file_id)
            if f is not None and ST.waiting_upload(f):
                await ST.destroy_upload(ctx.hub, txf, f)
    await RT.destroy_queued(ctx.hub, txf)


# ----------------------------------------------------------------- records --
@router.get("/archive/records", response_model=Page[Record], responses=E)
async def list_records(
    scope: str | None = Query(default=None, pattern=CO),
    class_: str | None = Query(default=None, alias="class", pattern=KEY),
    folder: str | None = Query(default=None, pattern=r"^FP-[0-9]{4,}$"),
    level: str | None = Query(default=None, pattern=KEY),
    state: State | None = None,
    party: str | None = Query(default=None, pattern=r"^PT-[0-9]{4,}$"),
    q: str | None = Query(default=None, max_length=200),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    expiring_within_days: int | None = Query(default=None, ge=0, le=3650),
    held: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Only what the reader's clearance allows (the owner: everything)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        rows, nxt = await SE.listing(
            tx,
            scope=scope,
            cls=class_,
            folder=folder,
            level=level,
            state=state,
            party=party,
            q=q,
            date_from=from_,
            date_to=to,
            expiring_within_days=expiring_within_days,
            held=held,
            limit=limit,
            cursor=cursor,
        )
        items = [_render_ok(await R.render(tx, r, CL.EVERYTHING, full=False)) for r in rows]
    return {"items": items, "next_cursor": nxt}


@router.get("/archive/records/{ref}", response_model=Record, responses=E)
async def get_record(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The record with its versions, links, holds and reminders (an access-log row)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref)
        out = _render_ok(await R.render(tx, r, CL.EVERYTHING))
        await R.log_access(tx, ctx.who, r, "metadata")
    return out


@router.post("/archive/records", response_model=Record, status_code=201, responses=E)
async def create_record(body: RecordIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """`file: true` files it at once (complete: every required field and file);
    else a draft. Requires `Idempotency-Key`."""
    txf = _txf(ctx)
    idempotency.read_key(request, required=True)
    async with txf() as tx:
        scope = await tx.first(
            "SELECT id, code, kind FROM core.companies WHERE code = :c", c=body.scope
        )
        if scope is None:
            raise invalid({"scope": "unknown company"})
        cls = await R.resolve_class(tx, body.class_, body.scope)
        folder = await R.resolve_folder(tx, body.folder, scope["id"], scope["code"], cls)
        lv = await R.resolve_level(tx, body.level, cls, folder)
    intakes = await ST.intake(ctx.hub, txf, ctx.who, body.file_ids, holding_ok=True)
    stored = await ST.ingest(ctx.hub, intakes, encrypt_it=bool(lv["encrypt"]))
    try:
        async with ctx.tx() as tx:
            await CL.full(tx)
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                await ST.discard(ctx.hub, stored)
                return idem.replay
            r = await R.create(
                tx,
                ctx.who,
                scope=scope,
                cls=cls,
                title_fa=body.title_fa,
                metadata=body.metadata,
                lv=lv,
                folder=folder,
                stored=stored,
                parties=[p.model_dump() for p in body.parties],
                links=[link.model_dump() for link in body.links],
                file_now=body.file,
                source_kind="owner",
                note_fa=body.note_fa,
            )
            out = _render_ok(await R.render(tx, r, CL.EVERYTHING))
            if idem:
                await idem.store(tx, 201, out)
    except BaseException:
        await ST.discard(ctx.hub, stored)
        raise
    await _after(ctx, intakes)
    return out


@router.patch("/archive/records/{ref}", response_model=Record, responses=E)
async def patch_record(
    ref: str, body: RecordPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """`If-Match` · title_fa, metadata, folder, parties, class (a draft), level.
    A sealed record is 409 sealed_record except a PATCH whose only field is
    `level`; raising is free, lowering takes 🔏 `archive.declassify`
    (target `ref@version:level`). A level that encrypts (or no longer does)
    stores the files again: the old copies go once the change committed."""
    expected = http.if_match(request)
    data = body.model_dump(exclude_unset=True, by_alias=True)
    txf = _txf(ctx)
    new_level = data.pop("level", None)
    restore: list[dict[str, Any]] = []
    async with txf() as tx:
        r = await R.load(tx, ref)
        http.check_version(r["version"], expected)
        R.require_live(r)
        lv = None
        if new_level is not None and new_level != r["level"]:
            lv = await SC.level(tx, new_level)
            if lv is None or lv["status"] != "active":
                raise invalid({"level": "an active level"})
            cur = await SC.level(tx, r["level"])
            if cur is not None and bool(lv["encrypt"]) != bool(cur["encrypt"]):
                restore = await tx.all(
                    "SELECT * FROM archive.record_files WHERE record_id = :r AND destroyed_at IS NULL",
                    r=r["id"],
                )
    new_objects: list[tuple[dict[str, Any], str, str, str | None]] = []
    if lv is not None and restore:
        v = ST.vault(ctx.hub)
        if v is None:
            raise ApiError(503, "channel_not_configured", "the archive-secret key is not available")
        try:
            for f in restore:
                plain = await ST.read(ctx.hub, f)
                wrapped = None
                blob = plain
                if lv["encrypt"]:
                    dek, wrapped = await v.new_key()
                    blob = ST.encrypt(dek, plain, str(f["file_id"]).encode())
                key, sha = await ctx.hub.storage.put(blob)
                new_objects.append((f, key, sha, wrapped))
        except BaseException:
            for _f, key, _s, _w in new_objects:
                await ctx.hub.storage.destroy(key)
            raise
    try:
        async with ctx.tx() as tx:
            await CL.full(tx)
            r = await R.load(tx, ref, lock=True)
            http.check_version(r["version"], expected)
            step_up = False
            if lv is not None:
                await R.require_not_held(tx, r)
                if lv["rank"] < r["level_rank"]:
                    await stepup.consume(
                        tx,
                        request,
                        ctx.who,
                        "archive.declassify",
                        f"{ref}@{r['version']}:{lv['key']}",
                    )
                    step_up = True
            if data:
                r = await R.patch(tx, ctx.who, r, data, CL.EVERYTHING)
            if lv is not None:
                for f, key, sha, wrapped in new_objects:
                    await tx.exec(
                        """INSERT INTO archive.destroy_queue (company_id, storage_key, why, ref)
                           VALUES (:co, :k, 'restore', :r)""",
                        co=r["company_id"],
                        k=f["storage_key"],
                        r=ref,
                    )
                    await tx.exec(
                        """UPDATE archive.record_files SET storage_key = :k, stored_sha256 = :s, encrypted = :e,
                               wrapped_dek = :w WHERE id = :id""",
                        id=f["id"],
                        k=key,
                        s=sha,
                        e=bool(lv["encrypt"]),
                        w=wrapped,
                    )
                await tx.exec(
                    "UPDATE archive.records SET level = :l, level_rank = :lr WHERE id = :id",
                    l=lv["key"],
                    lr=lv["rank"],
                    id=r["id"],
                )
                await R.log_access(
                    tx,
                    ctx.who,
                    r,
                    "level",
                    step_up=step_up,
                    level_from=r["level"],
                    level_to=lv["key"],
                )
                await ctx.audit(
                    tx,
                    company_id=r["company_id"],
                    action="archive.declassify" if step_up else "archive.raise_level",
                    action_class="A2",
                    target_kind="archive_record",
                    target_ref=ref,
                    summary=f"{r['level']} -> {lv['key']}",
                    step_up=step_up,
                )
                r = await R.load(tx, ref)
                await R.emit(tx, r, "record.updated", change="level")
            out = _render_ok(await R.render(tx, await R.load(tx, ref), CL.EVERYTHING))
    except BaseException:
        for _f, key, _s, _w in new_objects:
            await ctx.hub.storage.destroy(key)
        raise
    await RT.destroy_queued(ctx.hub, txf)
    return out


@router.post("/archive/records/{ref}/file", response_model=Record, responses=E)
async def file_record(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """`If-Match` · a completed draft becomes `filed`."""
    expected = http.if_match(request)
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref, lock=True)
        http.check_version(r["version"], expected)
        await R.file_draft(tx, ctx.who, r)
        return await _record_out(ctx, tx, ref)


@router.post("/archive/records/{ref}/versions", response_model=Record, status_code=201, responses=E)
async def add_version(
    ref: str, body: VersionIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new version (also under a legal hold); on a sealed record the old one
    is superseded and the record goes back to `filed`. Requires `Idempotency-Key`."""
    txf = _txf(ctx)
    idempotency.read_key(request, required=True)
    async with txf() as tx:
        r = await R.load(tx, ref)
        R.require_live(r)
        lv = await SC.level(tx, r["level"])
    intakes = await ST.intake(ctx.hub, txf, ctx.who, body.file_ids, holding_ok=True)
    stored = await ST.ingest(ctx.hub, intakes, encrypt_it=bool(lv and lv["encrypt"]))
    try:
        async with ctx.tx() as tx:
            await CL.full(tx)
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                await ST.discard(ctx.hub, stored)
                return idem.replay
            r = await R.load(tx, ref, lock=True)
            await R.add_version(tx, ctx.who, r, stored, body.note_fa)
            out = await _record_out(ctx, tx, ref)
            if idem:
                await idem.store(tx, 201, out)
    except BaseException:
        await ST.discard(ctx.hub, stored)
        raise
    await _after(ctx, intakes)
    return out


@router.post("/archive/records/{ref}/seal", response_model=Record, responses=E)
async def seal_record(
    ref: str, body: SealIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 `archive.seal`, target = the current version's `manifest_sha256`; the
    server recomputes it and refuses a mismatch (409 seal_mismatch)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref, lock=True)
        R.require_live(r)
        await R.require_not_held(tx, r)
        if r["state"] != "filed":
            raise ApiError(
                409, "validation_failed", f"{ref} is {r['state']}: only a filed record is sealed"
            )
        again = await R.current_manifest(tx, r)
        if body.manifest_sha256 != again:
            raise ApiError(409, "seal_mismatch", "the manifest changed since you saw it")
        su = await stepup.consume(tx, request, ctx.who, "archive.seal", body.manifest_sha256)
        await R.seal(tx, ctx.who, r, body.manifest_sha256, su)
        await ctx.interaction(
            tx,
            company_id=r["company_id"],
            kind="decision",
            action="archive.seal",
            target_kind="archive_record",
            target_ref=ref,
            data={"manifest": again},
        )
        return await _record_out(ctx, tx, ref)


@router.post("/archive/records/{ref}/links", status_code=201, responses=E)
async def add_link(ref: str, body: LinkIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """One link of a link kind of the schema (423 while held)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        r = await R.load(tx, ref, lock=True)
        R.require_live(r)
        await R.require_not_held(tx, r)
        await R.add_link(tx, ctx.who, r, body.kind, body.to.model_dump())
        await ctx.audit(
            tx,
            company_id=r["company_id"],
            action="archive.link",
            action_class="A1",
            target_kind="archive_record",
            target_ref=ref,
            summary=f"{body.kind} {body.to.kind}:{body.to.ref}",
        )
        r = await R.load(tx, ref)
        await R.emit(tx, r, "record.updated", change="link")
        links = await R.render_links(tx, r)
        out = _render_ok(
            next(x for x in links if x["kind"] == body.kind and x["to_ref"] == body.to.ref)
        )
        if idem:
            await idem.store(tx, 201, out)
    return out


@router.delete("/archive/records/{ref}/links", status_code=204, responses=E)
async def remove_link(
    ref: str,
    kind: str = Query(pattern=KEY),
    to_kind: str = Query(pattern=r"^[a-z_]{2,30}$"),
    to_ref: str = Query(min_length=1, max_length=80),
    ctx: Ctx = Depends(owner_ctx),
) -> Response:
    """Removes an unsealed link (a sealed one never: 409 sealed_record)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref, lock=True)
        R.require_live(r)
        await R.require_not_held(tx, r)
        await R.remove_link(tx, ctx.who, r, kind, to_kind, to_ref)
        await ctx.audit(
            tx,
            company_id=r["company_id"],
            action="archive.unlink",
            action_class="A1",
            target_kind="archive_record",
            target_ref=ref,
            summary=f"{kind} {to_kind}:{to_ref}",
        )
        await R.emit(tx, r, "record.updated", change="unlink")
    return Response(status_code=204)


@router.get(
    "/archive/records/{ref}/files/{file_id}",
    response_class=Response,
    responses={**E, 200: {"content": {"application/octet-stream": {}}, "description": "The file"}},
)
async def get_file(
    ref: str,
    file_id: UUID,
    request: Request,
    version: int | None = Query(default=None, ge=1),
    ctx: Ctx = Depends(owner_ctx),
) -> Response:
    """The file; a level with `watermark` is served watermarked (viewer, time,
    ref), a level with `step_up_to_view` takes 🔏 `archive.view` (target =
    ref). Every call is an access-log row."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref)
        f = await ST.file_row(tx, r["id"], file_id, version)
        if f["quarantined"]:
            raise ApiError(
                409,
                "secret_in_document",
                "a secret pattern was found in this file; it is not served",
            )
        lv = await SC.level(tx, r["level"])
        step_up = False
        if lv and lv["step_up_to_view"]:
            await stepup.consume(tx, request, ctx.who, "archive.view", ref)
            step_up = True
        # The row first: a download that fails after it is still a view.
        inline = f["mime"].startswith("image/")
        await R.log_access(
            tx,
            ctx.who,
            r,
            "view" if inline else "download",
            file_id=file_id,
            version_n=f["version_n"],
            step_up=step_up,
            watermarked=bool(lv and lv["watermark"]),
        )
    data = await ST.read(ctx.hub, f)
    mime = f["mime"]
    if lv and lv["watermark"]:
        data, mime = await ST.watermarked(ctx.hub, data, mime, R.watermark_text(ctx.who, ref))
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": disposition("inline" if inline else "attachment", f["name"]),
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
            "X-Content-Sha256": hashlib.sha256(data).hexdigest(),
            "X-Archive-Sha256": f["sha256"],
            "Cache-Control": "no-store",
        },
    )


@router.get("/archive/records/{ref}/access", responses=E)
async def access_log(ref: str, ctx: Ctx = Depends(owner_ctx)) -> list[dict[str, Any]]:
    """Owner only · who viewed or downloaded what, when (AccessRow, §23.12)."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        r = await R.load(tx, ref)
        rows = await tx.all(
            "SELECT * FROM archive.access_log WHERE record_id = :r ORDER BY at DESC, id DESC LIMIT 500",
            r=r["id"],
        )
    return [
        _render_ok(
            {
                "at": x["at"],
                "actor": {"kind": x["actor_kind"], "code": x["actor_code"]},
                "action": x["action"],
                "file_id": x["file_id"],
                "version": x["version_n"],
                "step_up": x["step_up"],
                "watermarked": x["watermarked"],
                "level_from": x["level_from"],
                "level_to": x["level_to"],
            }
        )
        for x in rows
    ]


# ------------------------------------------------------------ intake, import --
@router.post("/archive/intake", response_model=IntakeOut, responses=E)
async def intake(body: IntakeIn, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """`{file_ids}` -> `{files, suggestion}`: the secret scan (`422
    secret_in_document`, the file is not kept), hashes and text extraction
    run here; the suggestion is the rules' (never filed by itself)."""
    items = await ST.intake(ctx.hub, _txf(ctx), ctx.who, body.file_ids, holding_ok=True)
    sug = next((it.suggestion for it in items if it.suggestion), None)
    return _render_ok({"files": [_intake_out(it) for it in items], "suggestion": sug})


@router.post("/archive/import", status_code=201, responses=E)
async def import_files(body: ImportIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """Owner · one `draft` per file for the archivist to classify, and one work
    item for it. Requires `Idempotency-Key`."""
    txf = _txf(ctx)
    idempotency.read_key(request, required=True)
    async with txf() as tx:
        scope = await tx.first(
            "SELECT id, code, kind FROM core.companies WHERE code = :c", c=body.scope
        )
        if scope is None:
            raise invalid({"scope": "unknown company"})
        cls = await R.resolve_class(tx, body.class_, body.scope)
    intakes = await ST.intake(ctx.hub, txf, ctx.who, body.file_ids, holding_ok=True)
    refs: list[str] = []
    all_stored: list[ST.Stored] = []
    try:
        async with ctx.tx() as tx:
            await CL.full(tx)
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay
            for it in intakes:
                folder = await R.resolve_folder(tx, None, scope["id"], scope["code"], cls)
                lv = await R.resolve_level(tx, None, cls, folder)
                stored = await ST.ingest(ctx.hub, [it], encrypt_it=bool(lv["encrypt"]))
                all_stored += stored
                sug = it.suggestion
                r = await R.create(
                    tx,
                    ctx.who,
                    scope=scope,
                    cls=cls,
                    title_fa=((sug or {}).get("title_fa") or it.name)[:300],
                    metadata={},
                    lv=lv,
                    folder=folder,
                    stored=stored,
                    parties=None,
                    links=None,
                    file_now=False,
                    source_kind="owner",
                    suggestion=sug,
                )
                refs.append(r["ref"])
            work = await RT.archivist_work(
                tx,
                f"دسته‌بندی {len(refs)} سند واردشده‌ی بایگانی ({body.scope})",
                "The owner imported these files as drafts. For each: read it (archive.read), choose the class, "
                "fill the fields from the document only (say where each one is), the parties, the level (never "
                "below the class's default) and the links, with archive.file on the same files; the owner files "
                "and seals.\n\n" + "\n".join(f"- {x}" for x in refs),
                priority="P3",
            )
            await ctx.audit(
                tx,
                company_id=scope["id"],
                action="archive.import",
                action_class="A1",
                target_kind="archive_record",
                target_ref=refs[0],
                summary=f"{len(refs)} draft(s)",
            )
            out = {"records": refs, "work": work}
            if idem:
                await idem.store(tx, 201, out)
    except BaseException:
        await ST.discard(ctx.hub, all_stored)
        raise
    await _after(ctx, intakes)
    return out


# ------------------------------------------------------------------ search --
@router.get("/archive/search", response_model=SearchOut, responses=E)
async def search(
    q: str | None = Query(default=None, max_length=200),
    scope: str | None = Query(default=None, pattern=CO),
    class_: str | None = Query(default=None, alias="class", pattern=KEY),
    level: str | None = Query(default=None, pattern=KEY),
    party: str | None = Query(default=None, pattern=r"^PT-[0-9]{4,}$"),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Persian-normalised full text over title, searchable fields and file
    text, clearance-filtered before ranking."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        return _render_ok(
            await SE.search(
                tx,
                q=q,
                scope=scope,
                cls=class_,
                level=level,
                party=party,
                date_from=from_,
                date_to=to,
                limit=limit,
                cursor=cursor,
            )
        )


# ------------------------------------------------------------------ schema --
@router.get("/archive/schema", responses=E)
async def get_schema(ctx: Ctx = Depends(owner_ctx)) -> dict[str, Any]:
    """Everything that describes the archive, the closed vocabulary and the parties."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        return _render_ok(await SC.everything(tx))


@router.put("/archive/schema/{part}/{key}", response_model=SchemaPut, responses=E)
async def put_schema(
    part: str,
    key: str,
    request: Request,
    dry_run: bool = Query(default=False),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """🔏 `archive.schema` (`archive.clearance` for clearance) on the body's
    SHA-256 · `If-Match` (a new key: `If-None-Match: *`; parts keyed by ref
    are created with key `new`) · `?dry_run=1`: the impact only."""
    raw = await request.body()
    try:
        body = json.loads(raw or b"null")
    except ValueError as exc:
        raise invalid({"body": "JSON"}) from exc
    async with ctx.tx() as tx:
        await CL.full(tx)
        row = await SC.current(tx, part, key, lock=True)
        checked = await SC.check(tx, part, key, body, row)
        impact = await SC.impact(tx, part, key, checked)
        if dry_run:
            return {
                "part": part,
                "key": key,
                "version": row["version"] if row else None,
                "impact": impact,
                "row": _render_ok(await SC.render_row(tx, part, row)) if row else None,
                "dry_run": True,
            }
        if row is None:
            if part not in V.REF_PARTS and request.headers.get("if-none-match", "").strip() != "*":
                raise ApiError(
                    428, "precondition_required", fields={"If-None-Match": "* for a new key"}
                )
        else:
            http.check_version(row["version"], http.if_match(request))
        action = "archive.clearance" if part == "clearance" else "archive.schema"
        await stepup.consume(tx, request, ctx.who, action, hashlib.sha256(raw).hexdigest())
        new = await SC.apply(tx, ctx.who, part, key, checked, row)
        new_key = SC.row_key(part, new)
        await AC.after_change(tx, part, new_key, impact)
        await ctx.audit(
            tx,
            company_id=new["company_id"],
            action=action,
            action_class="A2",
            target_kind=f"archive_{part}",
            target_ref=new_key,
            summary=f"v{new['version']} records {impact['records']}",
            step_up=True,
        )
        return {
            "part": part,
            "key": new_key,
            "version": new["version"],
            "impact": impact,
            "row": _render_ok(await SC.render_row(tx, part, new)),
            "dry_run": False,
        }


@router.post("/archive/schema/{part}/{key}/retire", response_model=SchemaPut, responses=E)
async def retire_schema(
    part: str, key: str, body: RetireIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """🔏 the same target (`archive.schema`, body hash); nothing that uses it is deleted."""
    if body.part != part or body.key != key:
        raise invalid({"body": "part and key must be the path's"})
    raw = await request.body()
    async with ctx.tx() as tx:
        await CL.full(tx)
        row = await SC.current(tx, part, key, lock=True)
        if row is None:
            raise ApiError(404, "not_found", f"no {part} {key}")
        http.check_version(row["version"], body.version)
        action = "archive.clearance" if part == "clearance" else "archive.schema"
        await stepup.consume(tx, request, ctx.who, action, hashlib.sha256(raw).hexdigest())
        new = await SC.retire(tx, part, row)
        impact = await SC.impact(tx, part, key, None)
        await AC.after_change(tx, part, key, {"records": impact["records"], "missing_required": 0})
        await ctx.audit(
            tx,
            company_id=new["company_id"],
            action=f"{action}_retire",
            action_class="A2",
            target_kind=f"archive_{part}",
            target_ref=key,
            summary=f"v{new['version']} retired",
            step_up=True,
        )
        return {
            "part": part,
            "key": key,
            "version": new["version"],
            "impact": impact,
            "row": _render_ok(await SC.render_row(tx, part, new)),
            "dry_run": False,
        }


# ----------------------------------------------------------------- parties --
async def _check_party(
    tx: Any, kind: str, identifiers: dict[str, Any], scopes: list[str]
) -> dict[str, Any]:
    pk = await tx.first(
        "SELECT * FROM archive.party_kinds WHERE key = :k AND status = 'active'", k=kind
    )
    if pk is None:
        raise invalid({"kind": "an active party kind"})
    fields = J(pk["identifier_fields"], [])
    clean, _m, errors = V.validate_metadata(fields, identifiers, complete=False)
    errors = {k.replace("metadata.", "identifiers."): v for k, v in errors.items()}
    for i, s in enumerate(scopes):
        if not await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=s):
            errors[f"scopes.{i}"] = "an existing company code"
    if errors:
        raise invalid(errors)
    return clean


@router.get("/archive/parties", responses=E)
async def list_parties(
    kind: str | None = Query(default=None, pattern=KEY),
    q: str | None = Query(default=None, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> list[dict[str, Any]]:
    async with ctx.tx() as tx:
        await CL.full(tx)
        rows = await tx.all(
            """SELECT * FROM archive.parties WHERE (CAST(:k AS text) IS NULL OR kind = :k)
                 AND (CAST(:q AS text) IS NULL OR core.fa_normalize(name_fa || ' ' || COALESCE(name_en, ''))
                      LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%')
               ORDER BY ref LIMIT 500""",
            k=kind,
            q=q,
        )
        return [_render_ok(await SC.render_party(tx, r)) for r in rows]


@router.post("/archive/parties", status_code=201, responses=E)
async def create_party(body: PartyIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A party of the registry. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        ids = await _check_party(tx, body.kind, body.identifiers, body.scopes)
        R.no_secret({"name_fa": body.name_fa, "identifiers": ids})
        h = await tx.one("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
        row = await tx.one(
            """INSERT INTO archive.parties (company_id, kind, name_fa, name_en, identifiers, scopes,
                   created_by_kind, created_by_code)
               VALUES (:co, :k, :n, :ne, CAST(:i AS jsonb), :s, 'owner', 'owner') RETURNING *""",
            co=h["id"],
            k=body.kind,
            n=body.name_fa.strip(),
            ne=body.name_en,
            i=dumps(ids),
            s=body.scopes,
        )
        await ctx.audit(
            tx,
            company_id=h["id"],
            action="archive.party_create",
            action_class="A1",
            target_kind="archive_party",
            target_ref=row["ref"],
            summary=body.kind,
        )
        out = _render_ok(await SC.render_party(tx, row))
        if idem:
            await idem.store(tx, 201, out)
    return out


@router.patch("/archive/parties/{ref}", responses=E)
async def patch_party(
    ref: str, body: PartyPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """`If-Match`."""
    expected = http.if_match(request)
    async with ctx.tx() as tx:
        await CL.full(tx)
        row = await tx.first("SELECT * FROM archive.parties WHERE ref = :r FOR UPDATE", r=ref)
        if row is None:
            raise ApiError(404, "not_found", f"no party {ref}")
        http.check_version(row["version"], expected)
        data = body.model_dump(exclude_unset=True)
        ids = J(row["identifiers"], {})
        if "identifiers" in data or "scopes" in data:
            ids = await _check_party(
                tx,
                row["kind"],
                data.get("identifiers", ids) or {},
                data.get("scopes") or list(row["scopes"] or []),
            )
        R.no_secret({"name_fa": data.get("name_fa") or "", "identifiers": ids})
        new = await tx.one(
            """UPDATE archive.parties SET name_fa = COALESCE(:n, name_fa), name_en = COALESCE(:ne, name_en),
                   identifiers = CAST(:i AS jsonb), scopes = COALESCE(:s, scopes), status = COALESCE(:st, status)
               WHERE id = :id RETURNING *""",
            id=row["id"],
            n=data.get("name_fa"),
            ne=data.get("name_en"),
            i=dumps(ids),
            s=data.get("scopes"),
            st=data.get("status"),
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="archive.party_update",
            action_class="A1",
            target_kind="archive_party",
            target_ref=ref,
            summary=",".join(sorted(data)),
        )
        return _render_ok(await SC.render_party(tx, new))


# ------------------------------------------------------------------- holds --
@router.get("/archive/holds", responses=E)
async def list_holds(
    state: Literal["active", "released"] | None = None, ctx: Ctx = Depends(owner_ctx)
) -> list[dict[str, Any]]:
    async with ctx.tx() as tx:
        await CL.full(tx)
        rows = await tx.all(
            RT.HOLD_SQL
            + " WHERE (CAST(:s AS text) IS NULL OR h.state = :s) ORDER BY h.placed_at DESC",
            s=state,
        )
        return [_render_ok(await RT.render_hold(tx, h)) for h in rows]


@router.post("/archive/holds", status_code=201, responses=E)
async def place_hold(body: HoldIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner places a legal hold. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        h = await RT.place(
            tx, ctx.who, body.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        out = _render_ok(await RT.render_hold(tx, h))
        if idem:
            await idem.store(tx, 201, out)
    return out


@router.post("/archive/holds/{ref}/release", responses=E)
async def release_hold(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 `archive.hold.release`, target = ref: the owner's alone."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        h = await tx.first(RT.HOLD_SQL + " WHERE h.ref = :r FOR UPDATE", r=ref)
        if h is None:
            raise ApiError(404, "not_found", f"no hold {ref}")
        su = await stepup.consume(tx, request, ctx.who, "archive.hold.release", ref)
        new = await RT.release(tx, h, su)
        return _render_ok(await RT.render_hold(tx, new))


# --------------------------------------------- reminders, retention, fixity --
@router.get("/archive/reminders", responses=E)
async def due_reminders(
    scope: str | None = Query(default=None, pattern=CO), ctx: Ctx = Depends(owner_ctx)
) -> list[dict[str, Any]]:
    async with ctx.tx() as tx:
        await CL.full(tx)
        return [_render_ok(x) for x in await RM.due_list(tx, scope=scope)]


@router.post("/archive/reminders/{id}/done", responses=E)
async def reminder_done(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> Any:
    async with ctx.tx() as tx:
        await CL.full(tx)
        return _render_ok(await RM.done(tx, ctx.who, id))


@router.get("/archive/retention/due", responses=E)
async def retention_due(ctx: Ctx = Depends(owner_ctx)) -> list[dict[str, Any]]:
    async with ctx.tx() as tx:
        await CL.full(tx)
        rows = await RT.due(tx)
    return [
        _render_ok({k: v for k, v in x.items() if k not in ("review_work", "kept")}) for x in rows
    ]


@router.get("/archive/fixity", responses=E)
async def fixity(ctx: Ctx = Depends(owner_ctx)) -> dict[str, Any]:
    """The last fixity run `{at, checked, failed: [ref], next_at}`."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        return _render_ok(await FX.last(tx))


# ----------------------------------------------------------------- sources --
@router.get("/archive/sources", responses=E)
async def get_sources(ctx: Ctx = Depends(owner_ctx)) -> list[dict[str, Any]]:
    async with ctx.tx() as tx:
        await CL.full(tx)
        return [_render_ok(x) for x in await SRC.listing(tx)]


@router.put("/archive/sources", responses=E)
async def put_sources(body: dict[str, bool], ctx: Ctx = Depends(owner_ctx)) -> list[dict[str, Any]]:
    """Owner · `{<key>: on}` for the switches that change."""
    async with ctx.tx() as tx:
        await CL.full(tx)
        out = await SRC.put(tx, body)
        h = await tx.one("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
        await ctx.audit(
            tx,
            company_id=h["id"],
            action="archive.sources",
            action_class="A1",
            target_kind="archive_sources",
            target_ref="sources",
            summary=", ".join(f"{k}={'on' if v else 'off'}" for k, v in sorted(body.items())),
        )
    return [_render_ok(x) for x in out]
