"""The substitute players (prompt 12 §9.1, contract §21.13).

Owner (/api/v1):
    GET  /substitutes                                   both players and DeepSeek
    PUT  /substitutes/{player}/seats 🔏                  substitute.seats (body hash) · If-Match
    POST /substitutes/{player}/web/logout 🔏             substitute.web_logout (player)
    POST /connections/{id}/login 🔏                      connection.login (id) -> 201 SubstituteLogin
    GET  /connections/{id}/login/{login_id}             poll while waiting
    POST /connections/{id}/login/{login_id}/code        {code} write-only, auth_code, <= 10 min
    POST /connections/{id}/logout 🔏                     connection.logout (id)
    GET·POST /creatives, GET /creatives/{ref}, POST /creatives/{ref}/accept|reject
Agents (/internal/v1):
    POST /substitutes/call                              substitute.call (A0)
The runner's dispatcher (service principal `substitutes`, /internal/v1):
    POST /substitutes/jobs/claim, POST /substitutes/jobs/{id}/done,
    POST /substitutes/logins/{id}/started, POST /substitutes/logins/{id}/code
Stream: substitute.updated on `treasury`, creative.updated on `creatives`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import files as F
from hq_api.domain import substitutes as S
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.routes.notifications import if_match
from hq_api.schemas import Page, actor
from hq_api.security import stepup

router = APIRouter(tags=["substitutes"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428, 429, 503)
CR = r"^CR-[0-9]{4,9}$"


def _player(p: str) -> str:
    if p not in S.PLAYERS:
        raise ApiError(404, "not_found")
    return p


async def _one(ctx: Ctx, tx: Any, player: str) -> S.Substitute:
    rows = await S.render_all(tx, player)
    if not rows:
        raise ApiError(404, "not_found")
    return rows[0]


@router.get("/substitutes", response_model=list[S.Substitute], responses=E)
async def list_substitutes(ctx: Ctx = Depends(owner_ctx)) -> list[S.Substitute]:
    """Sign-in, status, models, capabilities, seats (with today's use) and the
    Jalali month's use of each player (`value_ratio` = equiv_usd ÷ price_usd;
    null for a free account)."""
    async with ctx.tx() as tx:
        return await S.render_all(tx)


@router.put("/substitutes/{player}/seats", response_model=S.Substitute, responses=E)
async def put_seats(
    player: str, body: list[S.SeatIn], request: Request, ctx: Ctx = Depends(owner_ctx)
) -> S.Substitute:
    """The player's seats as a whole list (a seat left out is switched off).
    🔏 substitute.seats on the SHA-256 of the exact body; If-Match = version."""
    _player(player)
    version = if_match(request)
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        sid = await stepup.consume(
            tx, request, ctx.who, "substitute.seats", await stepup.body_target(request)
        )
        await S.put_seats(tx, player, body, version)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="substitute.seats",
            action_class="A2",
            target_kind="substitute",
            target_ref=player,
            summary=", ".join(
                f"{s.seat}:{s.via}:{s.per_day}{'' if s.enabled else ':off'}" for s in body
            )[:500],
            step_up=sid is not None,
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="setting",
            action="substitute.seats",
            target_kind="substitute",
            target_ref=player,
            data={"seats": [s.model_dump() for s in body]},
        )
        await ctx.emit(tx, holding.code, "substitute.updated", player, {"change": "seats"})
        return await _one(ctx, tx, player)


@router.post("/substitutes/{player}/web/logout", response_model=S.Substitute, responses=E)
async def web_logout(player: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> S.Substitute:
    """Wipes the signed-in browser profile (egress, on the worker's next
    pass); signing in again is the owner's terminal (`make <x>-web-login`)."""
    _player(player)
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        sid = await stepup.consume(tx, request, ctx.who, "substitute.web_logout", player)
        await S.web_logout(tx, player)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="substitute.web_logout",
            action_class="A2",
            target_kind="substitute",
            target_ref=player,
            step_up=sid is not None,
        )
        await ctx.emit(tx, holding.code, "substitute.updated", player, {"change": "web_logout"})
        return await _one(ctx, tx, player)


async def _connection(tx: Any, id: UUID) -> dict[str, Any]:
    row = await tx.first("SELECT id, key, kind FROM llm.connections WHERE id = :id", id=id)
    if row is None:
        raise ApiError(404, "not_found")
    if row["kind"] != "subscription":
        raise ApiError(409, "not_ready", "only a substitute player's subscription signs in here")
    return dict(row)


@router.post(
    "/connections/{id}/login", response_model=S.SubstituteLogin, status_code=201, responses=E
)
async def start_login(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The CLI's own headless sign-in (a device code, or a browserless auth
    code). 🔏 connection.login on the connection id. 409 not_ready when the
    CLI has none, or while the runner is off: the app shows the terminal
    command (`make chatgpt-login`, `make gemini-login`)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        conn = await _connection(tx, id)
        sid = await stepup.consume(tx, request, ctx.who, "connection.login", str(id))
        login = await S.start_login(tx, ctx.hub, ctx.who, conn)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.login",
            action_class="A2",
            target_kind="connection",
            target_ref=conn["key"],
            summary="headless sign-in started",
            step_up=sid is not None,
        )
    # The runner reports the verification URL within seconds; the app polls.
    for _ in range(10):
        if login["verification_url"]:
            break
        await asyncio.sleep(1.0)
        async with ctx.tx() as tx:
            login = await tx.one("SELECT * FROM substitutes.logins WHERE id = :id", id=login["id"])
    return S.render_login(login)


async def _login(tx: Any, id: UUID, login_id: UUID) -> dict[str, Any]:
    conn = await _connection(tx, id)
    row = await tx.first(
        "SELECT * FROM substitutes.logins WHERE id = :l AND connection_key = :k",
        l=login_id,
        k=conn["key"],
    )
    if row is None:
        raise ApiError(404, "not_found")
    return dict(row)


@router.get("/connections/{id}/login/{login_id}", response_model=S.SubstituteLogin, responses=E)
async def get_login(id: UUID, login_id: UUID, ctx: Ctx = Depends(owner_ctx)) -> S.SubstituteLogin:
    async with ctx.tx() as tx:
        return S.render_login(await _login(tx, id, login_id))


@router.post(
    "/connections/{id}/login/{login_id}/code", response_model=S.SubstituteLogin, responses=E
)
async def give_code(
    id: UUID, login_id: UUID, body: S.LoginCode, ctx: Ctx = Depends(owner_ctx)
) -> S.SubstituteLogin:
    """Write-only (covered by the start's step-up): an `auth_code` sign-in's
    code while it waits, at most 10 minutes; it is never shown, logged or
    audited, and handed to the runner once."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        row = await S.give_code(tx, await _login(tx, id, login_id), body.code)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.login_code",
            action_class="A1",
            target_kind="connection",
            target_ref=row["connection_key"],
            summary="code given (not stored in the audit)",
        )
        return S.render_login(row)


@router.post("/connections/{id}/logout", response_model=S.Substitute, responses=E)
async def logout(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> S.Substitute:
    """Removes the stored CLI sign-in. 🔏 connection.logout on the id."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        conn = await _connection(tx, id)
        sid = await stepup.consume(tx, request, ctx.who, "connection.logout", str(id))
        p = await S.logout(tx, ctx.hub, ctx.who, conn)
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="connection.logout",
            action_class="A2",
            target_kind="connection",
            target_ref=conn["key"],
            step_up=sid is not None,
        )
        await ctx.emit(tx, holding.code, "substitute.updated", p["player"], {"change": "logout"})
        return await _one(ctx, tx, p["player"])


# ---------------------------------------------------------------- creatives --
async def render_creatives(tx: Any, rows: list[dict[str, Any]]) -> list[S.Creative]:
    ids: list[UUID] = []
    for r in rows:
        ids += list(r["file_ids"] or [])
        if r["composed_file_id"]:
            ids.append(r["composed_file_id"])
    refs = await F.refs(tx, ids)
    out = []
    for r in rows:
        out.append(
            S.Creative(
                id=r["id"],
                ref=r["ref"],
                company=r["company"],
                kind=r["kind"],
                brief_md=r["brief_md"],
                prompt_md=r["prompt_md"] or "",
                placement=r["placement"],
                aspect=r["aspect"],
                duration_s=r["duration_s"],
                overlay=r["overlay"],
                composed=refs.get(r["composed_file_id"]) if r["composed_file_id"] else None,
                player=r["player"],
                model=r["model"],
                path=r["path"],
                state=r["state"],
                requested_by=actor(r["requested_by_kind"], r["requested_by_code"]),
                work_ref=r["work_ref"],
                errand_ref=r["errand_ref"],
                files=[refs[f] for f in r["file_ids"] or [] if f in refs],
                review_md=r["review_md"],
                source=r["source"],
                ai_generated=r["ai_generated"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                version=r["version"],
            )
        )
    return out


@router.get("/creatives", response_model=Page[S.Creative], responses=E)
async def list_creatives(
    company: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$"),
    state: Literal["queued", "generating", "review", "accepted", "rejected", "failed"]
    | None = None,
    kind: Literal["image", "video"] | None = None,
    limit: int = Query(default=30, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[S.Creative]:
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            S.CREATIVE_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:st AS text) IS NULL OR r.state = :st)
                    AND (CAST(:k AS text) IS NULL OR r.kind = :k)
                    AND (CAST(:t AS timestamptz) IS NULL
                         OR (r.created_at, r.id) < (CAST(:t AS timestamptz), CAST(:i AS uuid)))
                  ORDER BY r.created_at DESC, r.id DESC LIMIT :lim""",
            co=company,
            st=state,
            k=kind,
            t=after_t,
            i=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=await render_creatives(tx, items), next_cursor=nxt)


@router.post("/creatives", response_model=S.Creative, status_code=201, responses=E)
async def create_creative(
    body: S.CreativeIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner's ad image or video: the hub's own prompt from the brief and
    the placement (no text inside the picture; the Persian overlay is set by
    the hub). Requires `Idempotency-Key`."""
    co = await ctx.hub.companies.find(body.company)
    if co is None:
        raise ApiError(422, "validation_failed", fields={"company": "unknown"})
    if body.duration_s is not None and body.kind != "video":
        raise ApiError(422, "validation_failed", fields={"duration_s": "a video's length"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await S.create_creative(
            tx,
            ctx.hub,
            ctx.who,
            company_id=co.id,
            kind=body.kind,
            brief_md=body.brief_md,
            prompt_md=S.template_prompt(body.brief_md, body.placement, body.kind, body.duration_s),
            placement=body.placement,
            overlay=body.overlay,
            duration_s=body.duration_s,
            player=body.player,
        )
        await ctx.audit(
            tx,
            company_id=co.id,
            action="creative.create",
            action_class="A1",
            target_kind="creative",
            target_ref=row["ref"],
            summary=f"{body.kind} {body.placement}",
        )
        full = await tx.one(S.CREATIVE_SQL + " WHERE r.id = :id", id=row["id"])
        out = (await render_creatives(tx, [full]))[0]
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/creatives/{ref}", response_model=S.Creative, responses=E)
async def get_creative(ref: str, ctx: Ctx = Depends(owner_ctx)) -> S.Creative:
    async with ctx.tx() as tx:
        row = await tx.first(S.CREATIVE_SQL + " WHERE r.ref = :ref", ref=ref)
        if row is None:
            raise ApiError(404, "not_found")
        return (await render_creatives(tx, [row]))[0]


async def _decide(ctx: Ctx, ref: str, accept: bool, body: S.NoteIn) -> S.Creative:
    async with ctx.tx() as tx:
        await S.decide_creative(tx, ctx.hub, ctx.who, ref, accept, body.note)
        row = await tx.one(S.CREATIVE_SQL + " WHERE r.ref = :ref", ref=ref)
        return (await render_creatives(tx, [row]))[0]


@router.post("/creatives/{ref}/accept", response_model=S.Creative, responses=E)
async def accept_creative(ref: str, body: S.NoteIn, ctx: Ctx = Depends(owner_ctx)) -> S.Creative:
    """Accepting is not publishing: a post or a story is an A3 decision card."""
    return await _decide(ctx, ref, True, body)


@router.post("/creatives/{ref}/reject", response_model=S.Creative, responses=E)
async def reject_creative(ref: str, body: S.NoteIn, ctx: Ctx = Depends(owner_ctx)) -> S.Creative:
    return await _decide(ctx, ref, False, body)


# ------------------------------------------------------------ substitute.call --
@internal_router.post("/substitutes/call", responses=E)
async def substitute_call(body: S.CallIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """substitute.call (A0): one bounded question to a substitute player at a
    seat the role may use. Masked input only; the answer is labelled with
    its `source` and is never evidence. Refusals: channel_not_configured
    (signed out or off), rate_limited (the seat's daily cap, or the player
    is limited), policy_denied (a seat the role may not use, or input the
    data guard refuses); 423 while the holding is locked."""
    who = ctx.who
    if not who.is_agent or who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(
        ctx, "substitute.call", {"seat": body.seat, "charter": who.charter, "company": who.company}
    )
    hub = ctx.hub
    async with ctx.tx() as tx:
        reason = await S.guard(tx, hub, body.seat, body.input_md)
        if reason is not None:
            raise ApiError(403, "policy_denied", f"the input may not leave the hub: {reason}")
        if body.seat == "creative":
            assert body.placement is not None
            row = await S.create_creative(
                tx,
                hub,
                who,
                company_id=who.company_id,
                kind=body.kind,
                brief_md=body.input_md[:4000],
                prompt_md=body.input_md,
                placement=body.placement,
                overlay=body.overlay,
                duration_s=body.duration_s,
                player=body.player if body.player in ("gpt", "gemini") else None,
            )
            if row["state"] == "failed":
                call = await tx.one(
                    "SELECT * FROM substitutes.calls WHERE id = :id", id=row["call_id"]
                )
                raise S.refusal(str(call["state_reason"]))
            return {"creative": row["ref"], "state": row["state"]}
        call = await S.seat_call(
            tx,
            hub,
            who,
            seat=body.seat,
            input_md=body.input_md,
            company_id=who.company_id,
            player=body.player,
            checkout={"repo": body.repo, "head_sha": body.head_sha} if body.repo else None,
            file_ids=body.file_ids,
        )
        if call["state"] == "skipped":
            raise S.refusal(str(call["state_reason"]))
        await ctx.audit(
            tx,
            company_id=who.company_id,
            action="substitute.call",
            action_class="A0",
            target_kind="substitute",
            target_ref=call["player"],
            summary=f"{body.seat} queued",
        )
    waited = 0.0
    wait = float(hub.settings.substitute_wait_s)
    while waited < wait:
        await asyncio.sleep(1.0)
        waited += 1.0
        async with hub.db.tx([who.company_id]) as tx:
            c = await tx.one("SELECT * FROM substitutes.calls WHERE id = :id", id=call["id"])
            if c["state"] in ("done", "failed", "skipped"):  # answered here, not by a work item
                await tx.exec(
                    "UPDATE substitutes.calls SET delivered_at = now() WHERE id = :id AND delivered_at IS NULL",
                    id=c["id"],
                )
        if c["state"] == "done":
            res = c["result"] or {}
            if body.seat == "code_review":
                findings = res.get("findings") or S.parse_findings(str(res.get("text_md") or ""))
                return {"findings": findings, "source": S.source(c)}
            return {"text_md": res.get("text_md") or "", "source": S.source(c)}
        if c["state"] in ("failed", "skipped"):
            raise S.refusal(str(c["state_reason"] or "failed"))
    return {"state": "queued", "call": str(call["id"])}


# ---------------------------------------------------- the runner's dispatcher --
async def _service(ctx: Ctx) -> None:
    if ctx.who.kind != "service":
        raise ApiError(403, "policy_denied", "the substitutes dispatcher only")
    await allow(ctx, "substitutes.jobs", {})


@internal_router.post("/substitutes/jobs/claim", responses=E)
async def claim_job(ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """The next CLI job, one at a time for both players; none while the
    holding's kill switch is engaged."""
    await _service(ctx)
    async with ctx.tx() as tx:
        return await S.claim(tx)


@internal_router.post("/substitutes/jobs/{id}/done", responses=E)
async def job_done(id: UUID, body: S.DoneIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    await _service(ctx)
    async with ctx.tx() as tx:
        row = await S.finish(tx, ctx.hub, id, body)
    return {"state": row["state"]}


@internal_router.post("/substitutes/logins/{id}/started", responses=E)
async def login_started(
    id: UUID, body: S.LoginStarted, ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    await _service(ctx)
    async with ctx.tx() as tx:
        row = await S.login_started(tx, id, body)
    return {"state": row["state"]}


@internal_router.post("/substitutes/logins/{id}/code", responses=E)
async def login_code(id: UUID, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """The owner's pasted code, once; never logged."""
    await _service(ctx)
    async with ctx.tx() as tx:
        return await S.take_code(tx, id)
