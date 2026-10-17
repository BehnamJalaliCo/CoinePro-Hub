"""The Code Workshop (contract §17.3): workspaces, grants, sessions, their
events (list and SSE), the owner's steering, approvals and stop; and the
internal API through which a grant's driver opens and steers sessions.

Runtime calls never run inside the request's transaction: the record is
committed first, then the runtime works as a background task of the same
request (the reply is the record as committed, which an Idempotency-Key
replay returns too).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import EMPLOYEE_CODE, Model, Page
from hq_api.security import stepup
from hq_api.workshop import domain as D
from hq_api.workshop import service
from hq_common.redact import scrub

router = APIRouter(tags=["workshop"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
EP = responses(401, 403, 404, 409, 422, 423, 503)
HEARTBEAT_S = 15.0
POLL_S = 0.5
WORKSPACE_CODE = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]{2,20}$"
Effort = Literal["low", "medium", "high", "xhigh", "max"]
Action = Literal["read", "edit", "run", "push_branch", "open_pr"]


class PolicyIn(Model):
    branch_prefix: str = Field(default="hq/", pattern=r"^hq/$")
    may_open_pr: bool = True
    merge: Literal["owner_seal"] = "owner_seal"
    deploy: Literal["owner_seal"] = "owner_seal"


class WorkspaceIn(Model):
    code: str = Field(pattern=WORKSPACE_CODE)
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
    default_branch: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._/-]+$")
    title_fa: str = Field(min_length=1, max_length=200)
    policy: PolicyIn = Field(default_factory=PolicyIn)
    status: Literal["active", "paused"] = "active"


class GrantIn(Model):
    workspace: str = Field(pattern=WORKSPACE_CODE)
    actions: list[Action] = Field(min_length=1, max_length=5)
    driver: str | None = Field(default=None, pattern=EMPLOYEE_CODE)
    budget_usd: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)
    expires_at: datetime


class SessionIn(Model):
    grant: str = Field(pattern=r"^G-[0-9]{4,}$")
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(default="", max_length=20000)
    attachments: list[UUID] = Field(default_factory=list, max_length=10)
    model: str | None = Field(default=None, min_length=3, max_length=100)
    effort: Effort | None = None
    # ⟨additive⟩ the part of the repository the session writes (a path prefix; "" = all)
    area: str = Field(default="", max_length=300, pattern=r"^[A-Za-z0-9._/-]*$")


class SessionMessageIn(Model):
    body: str = Field(min_length=1, max_length=20000)
    attachments: list[UUID] = Field(default_factory=list, max_length=10)


class ApprovalIn(Model):
    allow: bool
    note: str | None = Field(default=None, max_length=2000)


# ------------------------------------------------------------- workspaces --
@router.get("/workshop/workspaces", response_model=list[D.Workspace], responses=E)
async def list_workspaces(
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    ctx: Ctx = Depends(owner_ctx),
) -> list[D.Workspace]:
    """The repositories sessions may work on (data: seeded, then the owner's list)."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            D.WORKSPACE_SQL
            + " WHERE (CAST(:co AS text) IS NULL OR c.code = :co) ORDER BY c.code, w.code",
            co=company,
        )
    return [D.render_workspace(r) for r in rows]


@router.put("/workshop/workspaces", response_model=list[D.Workspace], responses=E)
async def put_workspaces(
    body: list[WorkspaceIn], request: Request, ctx: Ctx = Depends(owner_ctx)
) -> list[D.Workspace]:
    """🔏 (`workshop.workspaces`, target = SHA-256 of the exact body): the whole
    list. A workspace left out is paused, never deleted; a workspace keeps its
    company; the branch prefix is always hq/ and merge and deploy stay with
    the owner's seal."""
    codes = [w.code for w in body]
    if len(set(codes)) != len(codes):
        raise ApiError(422, "validation_failed", fields={"code": "each workspace once"})
    async with ctx.tx() as tx:
        await stepup.consume(
            tx, request, ctx.who, "workshop.workspaces", await stepup.body_target(request)
        )
        ids = {c.code: c.id for c in await ctx.hub.companies.all()}
        rows = await D.put_workspaces(tx, ctx.audit, [w.model_dump() for w in body], ids)
        await ctx.interaction(
            tx,
            company_id=(await ctx.hub.companies.holding()).id,
            kind="setting",
            action="workshop.workspaces",
            target_kind="workspace",
            target_ref="*",
            data={"codes": codes},
        )
    return [D.render_workspace(r) for r in rows]


# ----------------------------------------------------------------- grants --
@router.get("/workshop/grants", response_model=list[D.Grant], responses=E)
async def list_grants(
    workspace: str | None = Query(default=None, pattern=WORKSPACE_CODE),
    active: bool | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[D.Grant]:
    """Newest first; `active=true`: not revoked and not expired."""
    async with ctx.tx() as tx:
        rows = await tx.all(
            D.GRANT_SQL
            + """ WHERE (CAST(:ws AS text) IS NULL OR w.code = :ws)
                  AND (CAST(:active AS boolean) IS NULL
                       OR (g.revoked_at IS NULL AND g.expires_at > now()) = :active)
                ORDER BY g.created_at DESC LIMIT 200""",
            ws=workspace,
            active=active,
        )
    return [D.render_grant(r) for r in rows]


@router.post("/workshop/grants", response_model=D.Grant, status_code=201, responses=E)
async def create_grant(body: GrantIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """🔏 (`workshop.grant`, target = SHA-256 of the exact body). The owner's
    permission for one workspace: actions, the driver (an agent of the
    workspace's company; none = the owner drives), the USD cap of each
    session, an expiry (at most 90 days). Agents ask with a `code_session`
    decision instead. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        await stepup.consume(
            tx, request, ctx.who, "workshop.grant", await stepup.body_target(request)
        )
        g = await D.create_grant(
            tx,
            ctx.who,
            ctx.audit,
            workspace_code=body.workspace,
            actions=list(body.actions),
            driver_code=body.driver,
            budget_usd=body.budget_usd,
            expires_at=body.expires_at,
        )
        await ctx.interaction(
            tx,
            company_id=g["company_id"],
            kind="setting",
            action="workshop.grant",
            target_kind="grant",
            target_ref=g["ref"],
            data={
                "workspace": body.workspace,
                "actions": list(body.actions),
                "driver": body.driver,
            },
        )
        result = D.render_grant(g)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.post("/workshop/grants/{ref}/revoke", response_model=D.Grant, responses=E)
async def revoke_grant(
    ref: str, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Immediate (no step-up, like a kill switch); the sessions running under
    it stop, their branches stay. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        g, stopped = await D.revoke_grant(tx, ctx.who, ctx.audit, ref)
        await ctx.interaction(
            tx,
            company_id=g["company_id"],
            kind="setting",
            action="workshop.revoke",
            target_kind="grant",
            target_ref=ref,
            data={"stopped": [s["ref"] for s in stopped]},
        )
        result = D.render_grant(g)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    background.add_task(service.stopped, ctx.hub, stopped)
    return result


# --------------------------------------------------------------- sessions --
@router.get("/workshop/sessions", response_model=Page[D.CodeSession], responses=E)
async def list_sessions(
    workspace: str | None = Query(default=None, pattern=WORKSPACE_CODE),
    state: Literal["starting", "working", "waiting_approval", "idle", "done", "failed", "stopped"]
    | None = None,
    driver: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[D.CodeSession]:
    """Newest first."""
    after = pagination.decode(cursor, 2)
    async with ctx.tx() as tx:
        rows = await tx.all(
            D.SESSION_SQL
            + """ WHERE (CAST(:ws AS text) IS NULL OR w.code = :ws)
                  AND (CAST(:st AS text) IS NULL OR s.state = :st)
                  AND (CAST(:dr AS text) IS NULL OR s.driver_code = :dr)
                  AND (CAST(:ca AS timestamptz) IS NULL
                       OR (s.created_at, s.id) < (CAST(:ca AS timestamptz), CAST(:cid AS uuid)))
                ORDER BY s.created_at DESC, s.id DESC LIMIT :lim""",
            ws=workspace,
            st=state,
            dr=driver,
            ca=after[0] if after else None,
            cid=after[1] if after else None,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[D.render_session(r) for r in items], next_cursor=nxt)


async def _open(ctx: Ctx, request: Request, background: BackgroundTasks, body: SessionIn) -> Any:
    rt = service.runtime(ctx.hub)  # 503 runtime_not_configured until the owner chooses
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if ctx.who.is_agent:
            g = await tx.one(D.GRANT_SQL + " WHERE g.ref = :r", r=body.grant, not_found="not_found")
            await allow(
                ctx,
                "workshop.session",
                {
                    "company": await ctx.hub.companies.code_of(g["company_id"]),
                    "driver": g["driver_code"],
                    "grant": body.grant,
                },
            )
            await ctx.ensure_unlocked(tx, g["company_id"])
        s = await D.open_session(
            tx,
            ctx.who,
            ctx.audit,
            grant_ref=body.grant,
            title=body.title,
            brief=body.brief,
            area=body.area,
            model=body.model or ctx.hub.settings.workshop_model,
            effort=body.effort or ctx.hub.settings.workshop_effort,
            runtime=rt.name,
        )
        if body.attachments:
            await D.append(
                tx,
                s,
                "message",
                "پیوست‌های شرح کار",
                {"attachments": [str(a) for a in body.attachments]},
                actor=(ctx.who.kind, ctx.who.code),
            )
        result = D.render_session(s)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    if not s["held"]:
        background.add_task(service.start, ctx.hub, s["id"])
    return result


@router.post("/workshop/sessions", response_model=D.CodeSession, status_code=201, responses=EP)
async def create_session(
    body: SessionIn, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner opens a session under a live grant (`503 runtime_not_configured`
    until the owner chooses the runtime; `423` while the company is locked).
    A writing session whose area another writing session holds waits
    (`held: work_lock`) and starts when that one ends. Requires `Idempotency-Key`."""
    return await _open(ctx, request, background, body)


@router.get("/workshop/sessions/{ref}", response_model=D.CodeSession, responses=E)
async def get_code_session(ref: str, ctx: Ctx = Depends(owner_ctx)) -> D.CodeSession:
    """One session with its usage so far."""
    async with ctx.tx() as tx:
        return D.render_session(await D.by_ref(tx, ref))


@router.get("/workshop/sessions/{ref}/events", response_model=Page[D.SessionEvent], responses=E)
async def list_session_events(
    ref: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[D.SessionEvent]:
    """Oldest first, after `after` (a seq); `next_cursor` is unused (ask again
    with `after` = the last seq)."""
    async with ctx.tx() as tx:
        s = await D.by_ref(tx, ref)
        rows = await tx.all(
            "SELECT * FROM workshop.events WHERE session_id = :s AND seq > :a ORDER BY seq LIMIT :l",
            s=s["id"],
            a=after,
            l=limit,
        )
    return Page(items=[D.render_event(r) for r in rows])


def _sse(ev: D.SessionEvent) -> str:
    return f"id: {ev.seq}\nevent: {ev.type}\ndata: {json.dumps(ev.model_dump(mode='json'), ensure_ascii=False)}\n\n"


@router.get("/workshop/sessions/{ref}/live", responses=E)
async def session_live(
    ref: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """SSE of `SessionEvent` (`event:` = its type, `id:` = its seq); resumes after
    `Last-Event-ID`. Ends after the session's last event once it is finished; a
    comment line every 15 s keeps the connection open meanwhile."""
    try:
        after = max(0, int(last_event_id or 0))
    except ValueError:
        after = 0
    async with ctx.tx() as tx:
        s = await D.by_ref(tx, ref)
    hub = ctx.hub
    scope = await ctx.scope()

    async def stream() -> AsyncIterator[str]:
        seq, idle = after, 0.0
        yield ": live\n\n"
        while True:
            if await request.is_disconnected():
                return
            async with hub.db.tx(scope) as tx:
                rows = await tx.all(
                    "SELECT * FROM workshop.events WHERE session_id = :s AND seq > :a ORDER BY seq LIMIT 200",
                    s=s["id"],
                    a=seq,
                )
                state = await tx.scalar(
                    "SELECT state FROM workshop.sessions WHERE id = :s", s=s["id"]
                )
            for r in rows:
                seq = r["seq"]
                yield _sse(D.render_event(r))
            if not rows and state in D.FINAL:
                return
            if rows:
                idle = 0.0
                continue
            await asyncio.sleep(POLL_S)
            idle += POLL_S
            if idle >= HEARTBEAT_S:
                idle = 0.0
                yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/workshop/sessions/{ref}/transcript", responses=E)
async def session_transcript(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Response:
    """⟨additive⟩ Owner only: the full session transcript (JSON lines, masked),
    stored when the session ended (rule 7). 404 before that."""
    async with ctx.tx() as tx:
        s = await D.by_ref(tx, ref)
        if not s["transcript_file_id"]:
            raise ApiError(404, "not_found", "no transcript yet")
        f = await tx.one(
            "SELECT storage_key, name FROM files.files WHERE id = :id", id=s["transcript_file_id"]
        )
    data = await ctx.hub.storage.get(f["storage_key"])
    return Response(
        data,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{f["name"]}"',
            "Cache-Control": "no-store",
        },
    )


async def _steer(
    ctx: Ctx, request: Request, background: BackgroundTasks, ref: str, body: SessionMessageIn
) -> Any:
    rt = service.runtime(ctx.hub)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await D.by_ref(tx, ref, lock=True)
        if ctx.who.is_agent:
            await allow(
                ctx,
                "workshop.message",
                {"company": s["company"], "driver": s["driver_code"], "session": ref},
            )
            await ctx.ensure_unlocked(tx, s["company_id"])
        if s["state"] in D.FINAL:
            raise ApiError(409, "validation_failed", fields={"session": f"{ref} is {s['state']}"})
        if s["runtime"] != rt.name:
            raise ApiError(
                409, "validation_failed", fields={"session": f"{ref} ran on {s['runtime']}"}
            )
        if s["held"] in ("work_lock", "budget"):
            raise ApiError(
                409, "validation_failed", fields={"session": f"{ref} waits ({s['held']})"}
            )
        s = await D.unhold_if_free(tx, s)  # 423 while the company is still locked
        text = scrub(body.body)
        seq = await D.append(
            tx,
            s,
            "message",
            text[:300],
            {"chars": len(body.body), "attachments": [str(a) for a in body.attachments] or None},
            actor=(ctx.who.kind, ctx.who.code),
        )
        await ctx.audit(
            tx,
            company_id=s["company_id"],
            action="workshop.message",
            action_class="A1",
            target_kind="code_session",
            target_ref=ref,
            summary=f"{len(body.body)} chars",
        )
        ev = D.render_event(
            await tx.one(
                "SELECT * FROM workshop.events WHERE session_id = :s AND seq = :q", s=s["id"], q=seq
            )
        )
        if idem:
            await idem.store(tx, 201, ev.model_dump(mode="json"))
    background.add_task(service.steer, ctx.hub, s["id"], text)
    return ev


@router.post(
    "/workshop/sessions/{ref}/messages",
    response_model=D.SessionEvent,
    status_code=201,
    responses=EP,
)
async def post_session_message(
    ref: str,
    body: SessionMessageIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """The owner steers a session in words (or voice, transcribed first). The
    text reaches the session masked; the event keeps a summary. A session
    paused by a lock goes on once the lock is lifted. Requires `Idempotency-Key`."""
    return await _steer(ctx, request, background, ref, body)


@router.post(
    "/workshop/sessions/{ref}/approvals/{approval_id}",
    response_model=D.SessionEvent,
    responses=EP,
)
async def answer_approval(
    ref: str,
    approval_id: str,
    body: ApprovalIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Answers an `approval_request` (push, opening a PR, a command outside the
    allow-list). 🔏 only to allow (`workshop.approval`, target
    `"{session_ref}/{approval_id}"`); a denial needs none. Requires `Idempotency-Key`."""
    if body.allow:
        service.runtime(ctx.hub)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await D.by_ref(tx, ref, lock=True)
        step_up_id = None
        if body.allow:
            step_up_id = await stepup.consume(
                tx, request, ctx.who, "workshop.approval", f"{ref}/{approval_id}"
            )
        if s["state"] in D.FINAL and body.allow:
            raise ApiError(409, "validation_failed", fields={"session": f"{ref} is {s['state']}"})
        ap = await D.answer_approval(
            tx, ctx.who, ctx.audit, s, approval_id, body.allow, body.note, step_up_id
        )
        await ctx.interaction(
            tx,
            company_id=s["company_id"],
            kind="decision",
            action="workshop.approval",
            target_kind="approval",
            target_ref=f"{ref}/{approval_id}",
            data={"allow": body.allow, "action": ap["action"]},
        )
        last = await tx.scalar("SELECT last_seq FROM workshop.sessions WHERE id = :id", id=s["id"])
        ev = D.render_event(
            await tx.one(
                "SELECT * FROM workshop.events WHERE session_id = :s AND seq = :q",
                s=s["id"],
                q=last,
            )
        )
        if idem:
            await idem.store(tx, 200, ev.model_dump(mode="json"))
    if s["state"] not in D.FINAL and getattr(ctx.hub, "workshop", None) is not None:
        background.add_task(service.answer, ctx.hub, s["id"], ap, body.allow)
    return ev


@router.post("/workshop/sessions/{ref}/stop", response_model=D.CodeSession, responses=E)
async def stop_session(
    ref: str, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Immediate; the branch stays. Stopping a finished session returns it as
    it is. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        s = await D.by_ref(tx, ref, lock=True)
        was_running = s["state"] not in D.FINAL
        if was_running:
            s = await D.finish(tx, s, "stopped", None, "مدیر کل سشن را متوقف کرد")
            await ctx.audit(
                tx,
                company_id=s["company_id"],
                action="workshop.stop",
                action_class="A1",
                target_kind="code_session",
                target_ref=ref,
                summary="stopped by the owner",
            )
        result = D.render_session(s)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    if was_running:
        background.add_task(service.stopped, ctx.hub, [s])
    return result


# --------------------------------------------------------------- internal --
@internal_router.get("/workshop/sessions", response_model=Page[D.CodeSession], responses=E)
async def agent_list_sessions(
    state: Literal["starting", "working", "waiting_approval", "idle", "done", "failed", "stopped"]
    | None = None,
    mine: bool = True,
    ctx: Ctx = Depends(internal_ctx),
) -> Page[D.CodeSession]:
    """An agent's company's sessions (`mine`: the ones it drives), newest first, 50."""
    await allow(ctx, "workshop.read", {"company": ctx.who.company})
    async with ctx.tx() as tx:
        rows = await tx.all(
            D.SESSION_SQL
            + """ WHERE (CAST(:st AS text) IS NULL OR s.state = :st)
                  AND (NOT :mine OR s.driver_code = :me)
                ORDER BY s.created_at DESC LIMIT 50""",
            st=state,
            mine=mine,
            me=ctx.who.code,
        )
    return Page(items=[D.render_session(r) for r in rows])


@internal_router.post(
    "/workshop/sessions", response_model=D.CodeSession, status_code=201, responses=EP
)
async def agent_create_session(
    body: SessionIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """The grant's driver opens a session under it (policy hq.internal
    `workshop.session`: the driver, its own company; A1; 423 while locked).
    Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "only a grant's driver opens a session")
    return await _open(ctx, request, background, body)


@internal_router.post(
    "/workshop/sessions/{ref}/messages",
    response_model=D.SessionEvent,
    status_code=201,
    responses=EP,
)
async def agent_post_session_message(
    ref: str,
    body: SessionMessageIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(internal_ctx),
) -> Any:
    """The session's driver steers it (`workshop.message`). Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "only the session's driver steers it")
    return await _steer(ctx, request, background, ref, body)
