"""The archive's agent tools (prompt 14 §9, contract §23.11; OPA archive.rego).

    GET  /internal/v1/archive/search          archive.search (A0)
    GET  /internal/v1/archive/records/{ref}   archive.read   (A0; metadata and text within clearance)
    POST /internal/v1/archive/records         archive.file   (A1; a draft, never filed by itself)
    POST /internal/v1/archive/records/{ref}/links  archive.link (A1)
    POST /internal/v1/archive/holds           archive.hold   (A2; the legal counsel, with its case)

The policy names who (the archivist and the legal counsel, both holding
roles; a hold the counsel's alone); the api re-checks the role and reads
under the agent's own clearance (archive.clearance: its role's grants,
capped at agents_max), so a record above it is never in any answer. Nothing
here files, seals, declassifies, disposes or releases: an agent's
`archive.file` is a draft, and on a draft the owner imported it is only a
suggestion the owner confirms (red line 4).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ConfigDict, Field

from hq_api import idempotency
from hq_api.archive import clearance as CL
from hq_api.archive import records as R
from hq_api.archive import retention as RT
from hq_api.archive import schema as SC
from hq_api.archive import search as SE
from hq_api.archive import store as ST
from hq_api.archive.common import J, dumps, invalid
from hq_api.context import Ctx, internal_ctx
from hq_api.errors import ApiError, responses
from hq_api.routes.archive import HoldIn, LinkIn, PartyRole
from hq_api.routes.internal import allow
from hq_api.schemas import Model

internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
CO = r"^[A-Z][A-Z0-9]{1,9}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"
TEXT_MAX = 60_000


class AgentFileIn(Model):
    scope: str = Field(pattern=CO)
    class_: str = Field(alias="class", pattern=KEY)
    title_fa: str = Field(min_length=1, max_length=300)
    file_ids: list[UUID] = Field(min_length=1, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str | None = Field(default=None, pattern=KEY)
    folder: str | None = Field(default=None, pattern=r"^FP-[0-9]{4,}$")
    parties: list[PartyRole] = Field(default_factory=list, max_length=20)
    links: list[LinkIn] = Field(default_factory=list, max_length=20)
    note_fa: str = Field(default="", max_length=4000)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _agent(ctx: Ctx) -> None:
    if ctx.who.kind != "agent" or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


def _co(ctx: Ctx) -> UUID:
    assert ctx.who.company_id is not None
    return ctx.who.company_id


async def _allow(ctx: Ctx, op: str, **target: Any) -> None:
    _agent(ctx)
    await allow(ctx, op, {"company": ctx.who.company, "charter": ctx.who.charter, **target})


class _Wide:
    """Every company (the archive's agents are holding roles, allowed by the
    policy first), under the agent's own clearance."""

    def __init__(self, ctx: Ctx, clearance: CL.Clearance) -> None:
        self.ctx, self.c = ctx, clearance

    async def __aenter__(self) -> Any:
        self._cm = self.ctx.hub.db.tx(await self.ctx.hub.companies.ids())
        tx = await self._cm.__aenter__()
        await CL.apply(tx, self.c)
        return tx

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._cm.__aexit__(*exc)


async def clearance_of(ctx: Ctx) -> CL.Clearance:
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        return await CL.of_agent(tx, ctx.who)


def _out(x: Any) -> Any:
    return json.loads(dumps(x))


@internal_router.get("/archive/search", responses=E)
async def agent_search(
    q: str | None = Query(default=None, max_length=200),
    scope: str | None = Query(default=None, pattern=CO),
    class_: str | None = Query(default=None, alias="class", pattern=KEY),
    party: str | None = Query(default=None, pattern=r"^PT-[0-9]{4,}$"),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """archive.search (A0): only what the role's clearance allows."""
    await _allow(ctx, "archive.search", scope=scope)
    c = await clearance_of(ctx)
    async with _Wide(ctx, c) as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        return _out(
            await SE.search(
                tx,
                q=q,
                scope=scope,
                cls=class_,
                party=party,
                date_from=from_,
                date_to=to,
                limit=limit,
            )
        )


@internal_router.get("/archive/records/{ref}", responses=E)
async def agent_read(
    ref: str,
    version: str | None = Query(default=None, max_length=6),
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """archive.read (A0): metadata (masked where the level asks) and the text
    of a version, within clearance; an access-log row."""
    await _allow(ctx, "archive.read", ref=ref)
    n = int(version) if version and version.isdigit() else None
    c = await clearance_of(ctx)
    async with _Wide(ctx, c) as tx:
        r = await R.load(tx, ref)
        out = await R.render(tx, r, c)
        if c.sees(r["level_rank"], r["company_id"]):
            text = await SE.text_of(tx, r, n)
            out["text"] = (text or "")[:TEXT_MAX] or None
        else:
            out["text"] = (
                None  # metadata only: the archivist's own filing above its content clearance
            )
        await R.log_access(
            tx, ctx.who, r, "metadata" if out["text"] is None else "view", version_n=n
        )
    return _out(out)


async def _usable(ctx: Ctx, tx: Any, file_ids: list[UUID]) -> None:
    """An agent files only files it may read: its scope's, or an owner upload
    a case of this counsel names."""
    for fid in file_ids:
        f = await tx.first(ST.UPLOAD_SQL + " WHERE f.id = :id", id=fid)
        if f is None:
            raise ApiError(422, "validation_failed", fields={"file_ids": f"unknown file {fid}"})
        if ST.waiting_upload(f) and not await tx.scalar(
            "SELECT 1 FROM legal.cases WHERE counsel_id = :e AND :f = ANY (file_ids)",
            e=ctx.who.employee_id,
            f=fid,
        ):
            raise ApiError(
                422, "validation_failed", fields={"file_ids": f"not a file you may read: {fid}"}
            )


@internal_router.post("/archive/records", status_code=201, responses=E)
async def agent_file(body: AgentFileIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """archive.file (A1): a draft from files, with the class and metadata it
    proposes. On a draft the owner imported (the same files) it is a
    suggestion the owner confirms. Requires `Idempotency-Key`."""
    await _allow(ctx, "archive.file", scope=body.scope)
    c = await clearance_of(ctx)
    data = body.model_dump(by_alias=True, mode="json")
    idempotency.read_key(request, required=True)
    async with _Wide(ctx, c) as tx:
        await ctx.ensure_unlocked(tx, _co(ctx))
        scope = await tx.first(
            "SELECT id, code, kind FROM core.companies WHERE code = :c", c=body.scope
        )
        if scope is None:
            raise invalid({"scope": "unknown company"})
        cls = await R.resolve_class(tx, body.class_, body.scope)
        draft = await tx.first(
            """SELECT r.ref FROM archive.records r
               WHERE r.state = 'draft' AND r.class_key IS NULL AND r.source_kind = 'owner'
                 AND (SELECT array_agg(f.file_id ORDER BY f.file_id) FROM archive.record_files f
                      WHERE f.record_id = r.id AND f.version_n = r.current_version)
                     = CAST(:ids AS uuid[])
               LIMIT 1""",
            ids=sorted(str(x) for x in body.file_ids),
        )
        if draft is None:
            await _usable(ctx, tx, body.file_ids)
    if draft is None:
        return await _new_draft(ctx, c, body, cls, data, request)
    async with _Wide(ctx, c) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await _suggest(ctx, tx, draft["ref"], cls, data)
        if idem:
            await idem.store(tx, 201, out)
    return out


async def _suggest(
    ctx: Ctx, tx: Any, ref: str, cls: dict[str, Any] | None, data: dict[str, Any]
) -> Any:
    """The archivist's proposal on an imported draft: shown to the owner, never
    applied by itself."""
    from hq_api.archive import vocab as V

    r = await R.load(tx, ref, lock=True)
    fields = list(cls["fields"]) if cls else []
    clean, missing, errors = V.validate_metadata(fields, data.get("metadata") or {}, complete=False)
    if errors:
        raise invalid(errors)
    R.no_secret(
        {"title_fa": data["title_fa"], "metadata": clean, "note_fa": data.get("note_fa") or ""}
    )
    sug = {
        "class": cls["key"] if cls else None,
        "title_fa": data["title_fa"],
        "metadata": clean,
        "parties": data.get("parties") or [],
        "links": data.get("links") or [],
        "level": data.get("level"),
        "folder": data.get("folder"),
        "by": "archivist",
        "agent": ctx.who.code,
        "note_fa": data.get("note_fa") or "",
    }
    await tx.exec(
        "UPDATE archive.records SET suggestion = CAST(:s AS jsonb) WHERE id = :id",
        id=r["id"],
        s=dumps(sug),
    )
    await ctx.audit(
        tx,
        company_id=r["company_id"],
        action="archive.suggest",
        action_class="A1",
        target_kind="archive_record",
        target_ref=ref,
        summary=f"{sug['class']} by {ctx.who.code}",
    )
    r = await R.load(tx, ref)
    await R.emit(tx, r, "record.updated", change="suggestion")
    return {
        "ref": ref,
        "state": "draft",
        "class": sug["class"],
        "level": r["level"],
        "missing": missing,
        "suggestion": _out(sug),
    }


async def _new_draft(
    ctx: Ctx,
    c: CL.Clearance,
    body: AgentFileIn,
    cls: dict[str, Any] | None,
    data: dict[str, Any],
    request: Request,
) -> Any:
    async with _Wide(ctx, c) as tx:
        scope = await tx.one(
            "SELECT id, code, kind FROM core.companies WHERE code = :c", c=body.scope
        )
        folder = await R.resolve_folder(tx, body.folder, scope["id"], scope["code"], cls)
        lv = await R.resolve_level(tx, body.level, cls, folder)
        default = await SC.level(tx, (cls or {}).get("default_level") or "internal")
        if default is not None and lv["rank"] < default["rank"]:
            raise invalid({"level": f"never below the class's default ({default['key']})"})
        if not c.files_at(lv["rank"], scope["id"]):
            raise ApiError(403, "clearance", "that level is above your clearance")
    txf = lambda: _Wide(ctx, c)  # noqa: E731
    intakes = await ST.intake(ctx.hub, txf, ctx.who, body.file_ids, holding_ok=True)
    stored = await ST.ingest(ctx.hub, intakes, encrypt_it=bool(lv["encrypt"]))
    try:
        async with _Wide(ctx, c) as tx:
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                await ST.discard(ctx.hub, stored)
                return idem.replay
            await ctx.ensure_unlocked(tx, _co(ctx))
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
                links=[x.model_dump() for x in body.links],
                file_now=False,
                source_kind="agent",
                note_fa=body.note_fa or None,
                suggestion={
                    "class": cls["key"] if cls else None,
                    "by": "archivist",
                    "agent": ctx.who.code,
                    "note_fa": body.note_fa,
                },
            )
            fields = list(cls["fields"]) if cls else []
            from hq_api.archive import vocab as V

            _c, missing, _e = V.validate_metadata(fields, J(r["metadata"], {}), complete=False)
            out = {
                "ref": r["ref"],
                "state": r["state"],
                "class": r["class_key"],
                "level": r["level"],
                "missing": missing,
                "suggestion": None,
            }
            if idem:
                await idem.store(tx, 201, out)
    except BaseException:
        await ST.discard(ctx.hub, stored)
        raise
    return out


@internal_router.post("/archive/records/{ref}/links", status_code=201, responses=E)
async def agent_link(
    ref: str, body: LinkIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """archive.link (A1): one link of a link kind of the schema."""
    await _allow(ctx, "archive.link", ref=ref)
    c = await clearance_of(ctx)
    async with _Wide(ctx, c) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, _co(ctx))
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
        await R.emit(tx, r, "record.updated", change="link")
        links = await R.render_links(tx, r)
        out = _out(next(x for x in links if x["kind"] == body.kind and x["to_ref"] == body.to.ref))
        if idem:
            await idem.store(tx, 201, out)
    return out


@internal_router.post("/archive/holds", status_code=201, responses=E)
async def agent_hold(body: HoldIn, request: Request, ctx: Ctx = Depends(internal_ctx)) -> Any:
    """archive.hold (A2): the legal counsel places a hold for one of its cases."""
    await _allow(ctx, "archive.hold", case=body.case)
    if ctx.who.charter != "legal_counsel":
        raise ApiError(403, "policy_denied", "the legal counsel only")
    c = await clearance_of(ctx)
    async with _Wide(ctx, c) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, _co(ctx))
        h = await RT.place(
            tx, ctx.who, body.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        out = _out(await RT.render_hold(tx, h))
        if idem:
            await idem.store(tx, 201, out)
    return out
