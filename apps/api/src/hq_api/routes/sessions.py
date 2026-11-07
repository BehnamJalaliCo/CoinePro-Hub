"""⟨1.17⟩ Every order a session (contract §35.1-§35.3): the owner's routes.

    GET    /sessions?state=open|closed|all&limit&cursor   Page[SessionCard]: open ones by badge
                                                        (your_turn, ready, stuck, moving), newest first
    POST   /orders/{ref}/participants {kind, key}      a person (any persona key) or a player
                                                        (gpt | gemini | deepseek) joins the session
    DELETE /orders/{ref}/participants/{key}            leaves (never the holder)
    POST   /orders/{ref}/tasks {title_fa}              a line of the plan, the owner's
    PATCH  /orders/{ref}/tasks/{id} {title_fa?, state?, n?}
    POST   /orders/{ref}/close {verdict, note?}        the owner's OK (or cancel): the only end of
                                                        an order (Idempotency-Key)
    POST   /orders/{ref}/reopen                        ended_at cleared, the holder woken
    POST   /orders/{ref}/hide · /unhide                 off every list; nothing is deleted
    POST   /orders/{ref}/pace {pace}                   «با من / خودکار» at any time: the holder's
                                                        next run reads the new pace
    GET    /orders/{ref}/erase/preview                 ⟨1.19⟩ §37.1 what an erase would remove and
                                                        what stays (nothing changes)
    POST   /orders/{ref}/erase                         ⟨1.19⟩ 🔏 session.erase (target = ref): the
                                                        session gone for good (Idempotency-Key)

Owner only (owner_ctx), as the order report's routes are. Every write is audited (A1/A2).
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import erase as ER
from hq_api.domain import order_report as OR
from hq_api.domain import session_memory as MEM
from hq_api.domain import sessions as SE
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["orders"])
E = responses(401, 403, 404, 409, 422)
PERSONA_KEY = (
    r"^(secretary|overseer|assistant|advisor|[a-z][a-z0-9_]{1,40}@[A-Z][A-Z0-9]{1,9}"
    r"|player:(gpt|gemini|deepseek)|gpt|gemini|deepseek)$"
)


async def _report(tx: Any, ref: str) -> OR.OrderReport:
    out = await OR.report(tx, ref)
    if out is None:
        raise ApiError(404, "not_found", f"order {ref}", message_fa=SE.NOT_FOUND_FA)
    return out


# ---------------------------------------------------------------- the list --
@router.get("/sessions", response_model=Page[SE.SessionCard], responses=E)
async def list_order_sessions(
    state: Literal["open", "closed", "all"] = "open",
    limit: int = Query(default=30, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[SE.SessionCard]:
    """The owner's sessions (contract §35.3): open ones by badge, `your_turn` first, each group
    newest `last_at` first; `closed` the archive; hidden ones only with `all`."""
    async with ctx.tx() as tx:
        return await SE.cards(tx, state=state, limit=limit, cursor=cursor)


# ------------------------------------------------------------ participants --
class ParticipantIn(Model):
    kind: Literal["person", "player"]
    key: str = Field(pattern=PERSONA_KEY)


@router.post("/orders/{ref}/participants", response_model=OR.OrderReport, responses=E)
async def add_participant(
    ref: str, body: ParticipantIn, ctx: Ctx = Depends(owner_ctx)
) -> OR.OrderReport:
    """A person (any persona key: a manager of any company as role@CODE, the advisor, the
    overseer, the assistant) or a player (`gpt`, `gemini`, `deepseek`; one signed out answers
    409) joins the session's talk and may be asked (`to`) or heard with «نظر همه»."""
    key = body.key
    if body.kind == "player" and key.startswith("player:"):
        key = key.split(":", 1)[1]
    async with ctx.tx() as tx:
        added = await SE.add_participant(ctx, tx, ref, body.kind, key)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="session.participant", action_class="A1",
                        target_kind="order", target_ref=ref, summary=f"+{added}")  # fmt: skip
        return await _report(tx, ref)


@router.delete("/orders/{ref}/participants/{key}", response_model=OR.OrderReport, responses=E)
async def remove_participant(ref: str, key: str, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """The participant leaves the session (never the holder: 409)."""
    async with ctx.tx() as tx:
        await SE.remove_participant(ctx, tx, ref, key)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="session.participant", action_class="A1",
                        target_kind="order", target_ref=ref, summary=f"-{key}")  # fmt: skip
        return await _report(tx, ref)


# ------------------------------------------------------------------- tasks --
class TaskIn(Model):
    title_fa: str = Field(min_length=1, max_length=300)


class TaskPatch(Model):
    title_fa: str | None = Field(default=None, min_length=1, max_length=300)
    state: Literal["todo", "doing", "done", "dropped"] | None = None
    n: int | None = Field(default=None, ge=1, le=500)


@router.post("/orders/{ref}/tasks", response_model=SE.SessionTask, status_code=201, responses=E)
async def add_task(ref: str, body: TaskIn, ctx: Ctx = Depends(owner_ctx)) -> SE.SessionTask:
    """A line of the session's plan, the owner's own (the holder's come from `order.ack`)."""
    async with ctx.tx() as tx:
        rep = await SE._open(tx, ref)
        row = await SE.add_task(tx, rep, title_fa=body.title_fa, by="owner", who_fa=SE.OWNER_FA)
        await ctx.audit(tx, company_id=rep["company_id"], action="session.task", action_class="A1",
                        target_kind="order", target_ref=ref, summary=f"+ {row['n']}")  # fmt: skip
        await OR.refresh(tx, ref)
        return SE.render_task(row)


@router.patch("/orders/{ref}/tasks/{id}", response_model=SE.SessionTask, responses=E)
async def patch_task(
    ref: str, id: UUID, body: TaskPatch, ctx: Ctx = Depends(owner_ctx)
) -> SE.SessionTask:
    """The owner edits, moves (`n`), ticks or drops a line of the plan."""
    if body.title_fa is None and body.state is None and body.n is None:
        raise ApiError(422, "validation_failed", fields={"body": "nothing to change"},
                       message_fa="چیزی برای تغییر داده نشد.")  # fmt: skip
    async with ctx.tx() as tx:
        rep = await SE._open(tx, ref)
        row = await SE.patch_task(tx, rep, id, title_fa=body.title_fa, state=body.state, n=body.n)
        changed = ", ".join(k for k, v in body.model_dump().items() if v is not None)
        await ctx.audit(tx, company_id=rep["company_id"], action="session.task", action_class="A1",
                        target_kind="order", target_ref=ref, summary=f"{row['n']}: {changed}")  # fmt: skip
        await OR.refresh(tx, ref)
        return SE.render_task(row)


# --------------------------------------------------------- close · reopen --
class CloseIn(Model):
    verdict: Literal["ok", "cancel"]
    note: str | None = Field(default=None, max_length=2000)


@router.post("/orders/{ref}/close", response_model=OR.OrderReport, responses=E)
async def close_session(
    ref: str,
    body: CloseIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """The owner's OK: `ok` — the order `delivered` (`cancelled` when it has no final output),
    its open works cancelled except the permanent structures it set up, the session closed and
    archived (its talk read-only); `cancel` — the same, `cancelled`. ⟨1.22⟩ §40.1 the session's
    memory is folded once more after the close. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        rep = await SE.close(tx, ref, body.verdict, body.note, hub=ctx.hub)
        if rep.get("conversation_ref"):
            background.add_task(MEM.fold_after_close, ctx.hub, ref)
        await ctx.audit(tx, company_id=rep["company_id"], action="session.close", action_class="A2",
                        target_kind="order", target_ref=ref,
                        summary=f"{body.verdict}: {rep['state']}")  # fmt: skip
        await ctx.interaction(tx, company_id=rep["company_id"], kind="decision",
                              action="session.close", target_kind="order", target_ref=ref,
                              data={"verdict": body.verdict, "state": rep["state"]})  # fmt: skip
        result = await _report(tx, ref)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@router.post("/orders/{ref}/reopen", response_model=OR.OrderReport, responses=E)
async def reopen_session(ref: str, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """`ended_at` cleared, the session open again, the holder woken."""
    async with ctx.tx() as tx:
        out = await SE.reopen(tx, ref)
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        await ctx.audit(tx, company_id=rep["company_id"], action="session.reopen", action_class="A2",
                        target_kind="order", target_ref=ref,
                        summary="woken: " + (", ".join(out["woken"]) or "nothing"))  # fmt: skip
        return await _report(tx, ref)


@router.post("/orders/{ref}/hide", response_model=OR.OrderReport, responses=E)
async def hide_session(ref: str, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """Off every list (nothing is deleted); `GET /sessions?state=all` still shows it."""
    return await _hide(ref, True, ctx)


@router.post("/orders/{ref}/unhide", response_model=OR.OrderReport, responses=E)
async def unhide_session(ref: str, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """Back on the lists."""
    return await _hide(ref, False, ctx)


class PaceIn(Model):
    pace: Literal["auto", "step"]


@router.post("/orders/{ref}/pace", response_model=OR.OrderReport, responses=E)
async def set_pace(ref: str, body: PaceIn, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """The owner switches how the order is carried out, at any time: `step` («با من»: one step,
    then the holder asks) or `auto` («خودکار»: the holder plans and goes to the end). A step says
    so, the holder's brief is rewritten and the holder is woken so its next run reads the new pace.
    A closed session answers 409."""
    async with ctx.tx() as tx:
        out = await SE.set_pace(tx, ref, body.pace)
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        await ctx.audit(tx, company_id=rep["company_id"], action="order.pace", action_class="A1",
                        target_kind="order", target_ref=ref,
                        summary=f"{body.pace}; woken: {', '.join(out['woken']) or 'nothing'}")  # fmt: skip
        return await _report(tx, ref)


async def _hide(ref: str, hidden: bool, ctx: Ctx) -> OR.OrderReport:
    async with ctx.tx() as tx:
        await SE.hide(tx, ref, hidden)
        rep = await OR.ensure(tx, ref)
        assert rep is not None
        await ctx.audit(tx, company_id=rep["company_id"], action="session.hide", action_class="A1",
                        target_kind="order", target_ref=ref, summary="hidden" if hidden else "shown")  # fmt: skip
        return await _report(tx, ref)


# ------------------------------------------------------------- erase (§37.1) --
@router.get("/orders/{ref}/erase/preview", response_model=ER.ErasePreview, responses=E)
async def erase_session_preview(ref: str, ctx: Ctx = Depends(owner_ctx)) -> ER.ErasePreview:
    """⟨1.19⟩ What erasing this session would remove (turns, files, outputs, works,
    notifications) and, in plain Persian, what stays (a working group or production line it set
    up, one audit line, the token and money figures). Nothing changes: the erase itself runs and
    is rolled back, so the counts are exactly the erase's."""
    async with ctx.tx() as tx:
        return await ER.session_preview(tx, ref)


@router.post("/orders/{ref}/erase", response_model=ER.Erased, responses=E)
async def erase_session(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.19⟩ 🔏 `session.erase` (target = the ref), open or closed, hidden or not. In one
    transaction: its open works cancelled, then gone for good the session (report, steps, tasks,
    participants), its talk (turns, their voice and files), the order's files, its outputs and
    their files, its pending cards (withdrawn), the notifications that point at it, its runs'
    transcripts. A guarded ledger row keeps no word of the order and leaves every list; a stored
    file is destroyed only when nothing that stays uses it. One audit line `session.erase` (A3)
    with the counts. Afterwards the order and its session answer 404. Requires `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        await stepup.consume(tx, request, ctx.who, "session.erase", ref)
        out = await ER.erase(tx, ctx.who, "session", ref, step_up=True, request_id=ctx.request_id)
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    await ER.destroy_after(ctx.hub)
    return out
