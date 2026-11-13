"""⟨1.35⟩ §57 The session's team, one person at a time: the owner's routes.

    GET  /orders/{ref}/team                       SessionTeam: the holder, the media seats of a
                                                  content session (filled or empty), the people
                                                  present; the narrator of the order's company
    GET  /orders/{ref}/team/{code}/lines          Page[SideLine] newest last (?limit&before); the
                                                  newest page marks the seat read
    POST /orders/{ref}/team/{code}/say {text}     the owner's word to one person of the session
                                                  -> {line, work_ref, woken} (Idempotency-Key)
    POST /orders/{ref}/team/hire {role}           an empty media seat filled at once by his own
                                                  hire -> SessionTeam (Idempotency-Key)

Owner only (owner_ctx), no step-up (his word in his own session). Every write is audited.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import session_team as ST
from hq_api.errors import responses
from hq_api.schemas import Model, Page
from hq_api.talk.scrub import clean

router = APIRouter(tags=["orders"])
E = responses(401, 403, 404, 409, 422, 423, 429)


class TeamSayIn(Model):
    text: str = Field(min_length=1, max_length=ST.TEXT_MAX)


class TeamHireIn(Model):
    role: Literal["scriptwriter", "video_director", "motion_designer"]


@router.get("/orders/{ref}/team", response_model=ST.SessionTeam, responses=E)
async def session_team(ref: str, ctx: Ctx = Depends(owner_ctx)) -> ST.SessionTeam:
    """⟨1.35⟩ §57.1 The session's team, in order: the holder (`holder: true`, no side talk); the
    media seats `scriptwriter` «نویسنده», `video_director` «کارگردان» and `motion_designer`
    «موشن‌گرافی» of a content session (a media role in it, an order from a working group, or a
    company with a narrator), each filled by the person of the session with that role, else
    `state: empty` and `key: role:<role>`; then the other people present (players excluded).
    `state: working` while a run of theirs in this order is queued or running. `last`: the side
    talk's last line (≤ 160 chars); `unread`: the person's lines the owner has not read.
    `narrator`: §48's narrator of the order's company, or null."""
    async with ctx.tx() as tx:
        return await ST.team(tx, ref)


@router.get("/orders/{ref}/team/{code}/lines", response_model=Page[ST.SideLine], responses=E)
async def session_team_lines(
    ref: str,
    code: str,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    before: str | None = Query(default=None, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[ST.SideLine]:
    """⟨1.35⟩ §57.2 The side talk with one person of the session, newest last; `next_cursor`
    (as `before`) reads older lines. Reading the newest page marks the seat read (`unread` 0). A
    code that is not a seat of the session (and never had a side talk in it): 404."""
    async with ctx.tx() as tx:
        return await ST.lines(tx, ref, code, limit=limit, before=before)


@router.post("/orders/{ref}/team/{code}/say", response_model=ST.SayOut, responses=E)
async def session_team_say(
    ref: str, code: str, body: TeamSayIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.35⟩ §57.3 The owner's word to one person of the session (a filled seat other than the
    holder: the holder's word is `/reply`, 409). It joins the person's open work of this order
    (which runs again now with the side talk in its brief), else a side work is made for them,
    requested by the order's root: no plan task, never a part the root's delivery waits for; it
    closes by itself once its run answered and left nothing open («گفتگو جواب گرفت»). The main
    session gets one step per burst («مدیر کل: با …»). An ended session: 409; a code not in the
    team: 404. Requires `Idempotency-Key`; no step-up."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        text = clean(body.text)[0]
        out = await ST.say(ctx, tx, ref, code, text)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="session.side_word",
            action_class="A1",
            target_kind="order",
            target_ref=ref,
            summary=f"to {code}; {out.work_ref}" + ("" if out.woken else ", not running"),
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="message",
            action="session.side_word",
            target_kind="order",
            target_ref=ref,
            data={"seat": code, "work": out.work_ref, "woken": out.woken, "chars": len(text)},
        )
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


@router.post("/orders/{ref}/team/hire", response_model=ST.SessionTeam, responses=E)
async def session_team_hire(
    ref: str, body: TeamHireIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.35⟩ §57.5 An empty media seat filled at once: the owner's own hire in his session (by
    code, his approval's hard checks: the model offered, the estimate, the hires a day; no month
    envelope required), with the role's charter defaults (model, effort, 30 runs as the monthly
    estimate); the newcomer joins the session (§39). An active employee of that role in the
    company who is not in the session yet joins it instead (nobody new is hired). A hard check
    that refuses answers its own code with `message_fa`; nothing is made. A filled seat: 409.
    Requires `Idempotency-Key`; no step-up."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await ST.hire(ctx, tx, ref, body.role)
        holding = await ctx.hub.companies.holding()
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="decision",
            action="session.hire",
            target_kind="order",
            target_ref=ref,
            data={"role": body.role},
        )
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out
