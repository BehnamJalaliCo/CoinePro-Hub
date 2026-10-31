"""⟨1.10⟩ Prompt 19 (contract §28.2-§28.3): the company catalogue and the
apps' own error reports.

    POST /companies/{code}/catalogue      the owner starts a run (202; a run
                                          still going is answered as it is)
    GET  /companies/{code}/catalogue      the latest (404 while there is none)
    POST /client/errors                   an app's error log (masked on the
                                          device, again here; a repeated entry
                                          is kept once)
    GET  /client/errors?app&version&from  the owner (and, through the
                                          gateway, the overseer)
    /internal/v1/catalogue                company.catalogue (A1): a CEO for its
                                          own company, the watch for any
    /internal/v1/client/errors            client.errors (A0): the oversight
                                          roles and the platform SRE
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from hq_api import pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import catalogue as CAT
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model, Page
from hq_common.redact import scrub

router = APIRouter(tags=["watch"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
ENTRY_TEXT = 2000


# ---------------------------------------------------------------- catalogue --
async def _start(ctx: Ctx, code: str, by_kind: str, by_code: str) -> CAT.Catalogue:
    company = await ctx.hub.companies.by_code(code)
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        c, started = await CAT.start(tx, ctx.hub, company, by_kind=by_kind, by_code=by_code)
        if started:
            await ctx.audit(
                tx,
                company_id=company.id,
                action="catalogue.start",
                action_class="A1",
                target_kind="company",
                target_ref=company.code,
                summary=f"{len(c['jobs'])} read-only jobs on its servers",
            )
        return CAT.render(c)


@router.post(
    "/companies/{code}/catalogue", response_model=CAT.Catalogue, status_code=202, responses=E
)
async def start_catalogue(code: str, ctx: Ctx = Depends(owner_ctx)) -> CAT.Catalogue:
    """§28.2 the deep catalogue of a company: one read-only `claude` job per
    section on every paired server (the server's map when its Claude Code is
    not there), merged into one deliverable and filed in the archive as a
    `report` record. A run still going is answered as it is."""
    return await _start(ctx, code, "owner", "owner")


@router.get("/companies/{code}/catalogue", response_model=CAT.Catalogue, responses=E)
async def get_catalogue(code: str, ctx: Ctx = Depends(owner_ctx)) -> CAT.Catalogue:
    """The latest catalogue of the company (running, done or failed)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        c = await CAT.latest(tx, company.id)
    if c is None:
        raise ApiError(404, "not_found", "this company has no catalogue yet")
    if c["state"] == "done" and not c["record_ref"]:
        await CAT.file_done(ctx.hub, c["id"])  # filed late (the archive was away)
        async with ctx.tx() as tx:
            c = await CAT.latest(tx, company.id)
        assert c is not None
    return CAT.render(c)


class CatalogueIn(Model):
    company: str | None = Field(default=None, pattern=CODE)
    start: bool = False


@internal_router.post("/catalogue", response_model=CAT.Catalogue, responses=E)
async def agent_catalogue(body: CatalogueIn, ctx: Ctx = Depends(internal_ctx)) -> CAT.Catalogue:
    """company.catalogue: the latest catalogue of the company; `start: true`
    (or none yet) starts a run. The CEO's answer to "go through the server
    and extract everything" (§28.2), never a summary of its own."""
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    code = body.company or who.company
    assert code is not None
    await allow(ctx, "catalogue.start", {"company": code, "charter": who.charter})
    company = await ctx.hub.companies.by_code(code)
    if not body.start:
        async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
            c = await CAT.latest(tx, company.id)
        if c is not None and (c["state"] == "running" or c["state"] == "done"):
            return CAT.render(c)
    return await _start(ctx, code, "agent", who.code)


# ---------------------------------------------------- the apps' error reports --
class ErrorEntry(BaseModel):
    """One entry of an app's own error log (the app's fields; others kept)."""

    model_config = {"extra": "allow"}
    id: int | None = None
    at: datetime
    kind: str = Field(pattern=r"^[a-z_]{1,30}$")
    level: Literal["error", "warning", "info"] = "error"
    screen: str | None = Field(default=None, max_length=200)
    method: str | None = Field(default=None, max_length=10)
    path: str | None = Field(default=None, max_length=500)
    status: int | None = None
    code: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=4000)


class ClientErrorsIn(Model):
    app: Literal["android", "web"]
    version: str = Field(min_length=1, max_length=60)
    entries: list[ErrorEntry] = Field(min_length=1, max_length=500)


class ClientErrorsOut(BaseModel):
    accepted: int


class ClientError(BaseModel):
    id: str
    app: str
    version: str
    at: datetime
    kind: str
    level: str
    screen: str | None
    status: int | None
    code: str | None
    message: str | None
    entry: dict[str, Any]
    received_at: datetime


def _masked(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)[:ENTRY_TEXT]
    if isinstance(value, dict):
        return {str(k)[:60]: _masked(v) for k, v in list(value.items())[:60]}
    if isinstance(value, list):
        return [_masked(v) for v in value[:60]]
    return value


def fingerprint(e: ErrorEntry) -> str:
    """The same entry sent twice is kept once: its id, time, kind and path."""
    raw = json.dumps([e.id, e.at.isoformat(), e.kind, e.path, e.status, e.code], default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/client/errors", response_model=ClientErrorsOut, responses=E)
async def post_client_errors(
    body: ClientErrorsIn, ctx: Ctx = Depends(owner_ctx)
) -> ClientErrorsOut:
    """§28.3 an app's own error log, in batches (masked on the device and
    again here); the overseer's daily app health reads them."""
    holding = await ctx.hub.companies.holding()
    accepted = 0
    async with ctx.tx() as tx:
        for e in body.entries:
            entry = _masked(e.model_dump(mode="json", exclude_none=True))
            n = await tx.exec(
                """INSERT INTO ops.client_errors (company_id, app, version, entry_id, at, kind, level,
                       screen, status, code, message, fingerprint, entry)
                   VALUES (:co, :app, :v, :eid, :at, :kind, :level, :screen, :status, :code, :msg,
                           :fp, CAST(:entry AS jsonb))
                   ON CONFLICT (app, version, fingerprint) DO NOTHING""",
                co=holding.id,
                app=body.app,
                v=scrub(body.version)[:60],
                eid=e.id,
                at=e.at,
                kind=e.kind,
                level=e.level,
                screen=scrub(e.screen)[:200] if e.screen else None,
                status=e.status,
                code=scrub(e.code)[:80] if e.code else None,
                msg=scrub(e.message or e.title or "")[:2000] or None,
                fp=fingerprint(e),
                entry=json.dumps(entry, ensure_ascii=False),
            )
            accepted += int(bool(n))
    return ClientErrorsOut(accepted=accepted)


CLIENT_SQL = "SELECT * FROM ops.client_errors e"


async def _errors(
    tx: Tx,
    app: str | None,
    version: str | None,
    since: datetime | None,
    limit: int,
    cursor: str | None,
) -> Page[ClientError]:
    at, last = pagination.time_id(cursor)
    rows = await tx.all(
        CLIENT_SQL
        + """ WHERE (CAST(:app AS text) IS NULL OR e.app = :app)
                AND (CAST(:v AS text) IS NULL OR e.version = :v)
                AND (CAST(:since AS timestamptz) IS NULL OR e.at >= :since)
                AND (CAST(:cat AS timestamptz) IS NULL OR (e.received_at, e.id) < (:cat, :cid))
              ORDER BY e.received_at DESC, e.id DESC LIMIT :n""",
        app=app,
        v=version,
        since=since,
        cat=at,
        cid=last,
        n=limit + 1,
    )
    items, nxt = pagination.page(rows, limit, ("received_at", "id"))
    return Page(
        items=[
            ClientError(
                id=str(r["id"]), app=r["app"], version=r["version"], at=r["at"], kind=r["kind"],
                level=r["level"], screen=r["screen"], status=r["status"], code=r["code"],
                message=r["message"], entry=r["entry"], received_at=r["received_at"],
            )
            for r in items
        ],
        next_cursor=nxt,
    )  # fmt: skip


@router.get("/client/errors", response_model=Page[ClientError], responses=E)
async def get_client_errors(
    app: Literal["android", "web"] | None = None,
    version: str | None = Query(default=None, max_length=60),
    since: datetime | None = Query(default=None, alias="from"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[ClientError]:
    """The apps' error reports, newest first."""
    async with ctx.tx() as tx:
        return await _errors(tx, app, version, since, limit, cursor)


@internal_router.get("/client/errors", response_model=Page[ClientError], responses=E)
async def agent_client_errors(
    app: Literal["android", "web"] | None = None,
    version: str | None = Query(default=None, max_length=60),
    since: datetime | None = Query(default=None, alias="from"),
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = None,
    ctx: Ctx = Depends(internal_ctx),
) -> Page[ClientError]:
    """client.errors: the daily app health's input (§28.3)."""
    who = ctx.who
    if not who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    holding = await ctx.hub.companies.holding()
    await allow(ctx, "client_errors.read", {"company": holding.code, "charter": who.charter})
    async with ctx.hub.db.tx([holding.id]) as tx:
        return await _errors(tx, app, version, since, limit, cursor)
