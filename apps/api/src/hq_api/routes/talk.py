"""⟨1.14⟩ Prompt 23 (contract §32.1-§32.4, §32.7-§32.9): the owner's talk with
the holding secretary, the overseer, the assistant, the advisor and any
manager of any company. Owner only (OPA hq.talk); the /voice/* routes are the
voice layer's.

    GET   /talk/personas
    PUT   /talk/personas/{key}               {voice?, engine?, rate?, effort?}
    GET   /talk/conversations                ?persona&q&cursor&limit (FTS as §5.3)
    POST  /talk/conversations                {persona, role?, company?, mode?, title_fa?} -> 201
    GET   /talk/conversations/{ref}          with its turns page (?cursor: after turn n)
    PATCH /talk/conversations/{ref}          {mode?, title_fa?}
    POST  /talk/conversations/{ref}/turns    {text, source, client_id?, to?, file_ids?} -> 202 {turn, events}
    POST  /talk/conversations/{ref}/invite   {role, company}
    POST  /talk/conversations/{ref}/minutes  -> 202 {turn, events}: one minutes card
    GET   /talk/turns/{id}/events            SSE: text, say, audio, card, invite, meter, tool, done, error
    POST  /talk/turns/{id}/stop              barge-in
    POST  /talk/cards/{id}/run               {payload?} -> {made, card}: the card's own route
    POST  /talk/cards/{id}/dismiss

A turn never answers 5xx: when the brain or the worker is not there, the
answer is the plain line of §32.2 (the owner's words are kept)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field, model_validator

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model, Page
from hq_api.talk import cards as K
from hq_api.talk import data, personas, service, store
from hq_api.talk.personas import Persona

router = APIRouter(tags=["talk"])
E = responses(401, 403, 404, 409, 422)
HEARTBEAT_S = 15.0
POLL_S = 0.2
PERSONA_KEY = (
    r"^(secretary|overseer|assistant|advisor|[a-z][a-z0-9_]{1,40}@[A-Z][A-Z0-9]{1,9}"
    r"|player:(gpt|gemini|deepseek))$"
)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
ROLE = r"^[a-z][a-z0-9_]{1,40}$"
Effort = Literal["low", "medium", "high", "xhigh", "max"]


async def _policy(ctx: Ctx, op: str, target: dict[str, Any] | None = None) -> None:
    await ctx.hub.policy.require(
        "talk", {"principal": ctx.who.opa(), "op": op, "target": target or {}}
    )


def render_persona(p: Persona) -> store.TalkPersona:
    return store.TalkPersona(
        key=p.key,
        kind=p.kind,
        role=p.role,
        title_fa=p.title_fa,
        company=p.company_code,
        voice=store.TalkVoice(engine=p.voice.engine, voice=p.voice.voice, rate=p.voice.rate),
        brain=store.TalkBrain(effort=p.effort),
        tools=list(p.tools),
        face=p.face,
        consult_only=p.consult_only,
        cards=list(p.cards),
    )


# --------------------------------------------------------------- personas --
@router.get("/talk/personas", response_model=list[store.TalkPersona], responses=E)
async def talk_list_personas(ctx: Ctx = Depends(owner_ctx)) -> list[store.TalkPersona]:
    """The fixed personas (secretary, overseer, assistant, advisor) and every
    manager already called into a conversation (role@CODE), with the voice,
    the effort and the read tools each speaks with."""
    await _policy(ctx, "persona.read")
    out = []
    async with ctx.tx() as tx:
        keys = ["secretary", "overseer", "assistant", "advisor"]
        keys += [
            r["key"]
            for r in await tx.all("SELECT key FROM talk.personas WHERE key LIKE '%@%' ORDER BY key")
        ]
        for key in keys:
            with contextlib.suppress(ApiError):  # a manager who has left is not listed
                out.append(
                    render_persona(await personas.resolve(tx, ctx.hub, key, store_voice=False))
                )
    return out


class TalkPersonaIn(Model):
    voice: str | None = Field(default=None, min_length=1, max_length=60)
    engine: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{1,60}$")
    rate: float | None = Field(default=None, ge=0.8, le=1.25)
    effort: Effort | None = None


@router.put("/talk/personas/{key}", response_model=store.TalkPersona, responses=E)
async def talk_update_persona(
    key: str, body: TalkPersonaIn, ctx: Ctx = Depends(owner_ctx)
) -> store.TalkPersona:
    """The owner's choice of a persona's voice, engine, rate and effort (the
    charter is not editable here). An engine must be one of the voice layer's."""
    await _policy(ctx, "persona.update", {"persona": key})
    engines = [str(e) for e in data.voices().get("engines") or []]
    if body.engine is not None and engines and body.engine not in engines:
        raise ApiError(422, "validation_failed", fields={"engine": "unknown engine"},
                       message_fa="این موتور صدا شناخته نیست.")  # fmt: skip
    async with ctx.tx() as tx:
        p = await personas.resolve(tx, ctx.hub, key)
        await tx.exec(
            """INSERT INTO talk.personas (company_id, key, engine, voice, rate, effort)
               VALUES (:co, :k, :e, :v, :r, :ef)
               ON CONFLICT (key) DO UPDATE SET
                   engine = COALESCE(EXCLUDED.engine, talk.personas.engine),
                   voice = COALESCE(EXCLUDED.voice, talk.personas.voice),
                   rate = COALESCE(EXCLUDED.rate, talk.personas.rate),
                   effort = COALESCE(EXCLUDED.effort, talk.personas.effort),
                   updated_at = now()""",
            co=p.company_id,
            k=p.key,
            e=body.engine,
            v=body.voice,
            r=body.rate,
            ef=body.effort,
        )
        await ctx.audit(tx, company_id=p.company_id, action="talk.persona", action_class="A1",
                        target_kind="persona", target_ref=p.key,
                        summary=", ".join(k for k, v in body.model_dump().items() if v is not None))  # fmt: skip
        return render_persona(await personas.resolve(tx, ctx.hub, key))


# ---------------------------------------------------------- conversations --
@router.get("/talk/conversations", response_model=Page[store.TalkConversation], responses=E)
async def talk_list_conversations(
    persona: str | None = Query(default=None, pattern=PERSONA_KEY),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[store.TalkConversation]:
    """The owner's conversations, the latest first; `persona` keeps those it took
    part in; `q` searches every turn's words (Persian-normalised full text, as
    §5.3: ی/ي, ک/ك and ZWNJ alike)."""
    await _policy(ctx, "conversation.read")
    after_at, after_id = pagination.time_id(cursor)  # typed: asyncpg binds by type
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT c.*, COALESCE(c.last_turn_at, c.started_at) AS sort_at FROM talk.conversations c
               WHERE (CAST(:p AS text) IS NULL OR :p = ANY(c.present) OR c.persona = :p)
                 AND (CAST(:q AS text) IS NULL OR EXISTS (
                        SELECT 1 FROM talk.turns t, LATERAL (SELECT core.fa_normalize(:q) AS nq) n
                        WHERE t.conversation_id = c.id
                          AND (t.search @@ plainto_tsquery('simple', n.nq)
                               OR core.fa_normalize(t.text || ' ' || COALESCE(t.show_md, ''))
                                  LIKE '%' || core.like_escape(n.nq) || '%')))
                 AND (CAST(:at AS timestamptz) IS NULL
                      OR (COALESCE(c.last_turn_at, c.started_at), c.id)
                         < (CAST(:at AS timestamptz), CAST(:id AS uuid)))
               ORDER BY sort_at DESC, c.id DESC LIMIT :l""",
            p=persona,
            q=q,
            at=after_at,
            id=after_id,
            l=limit + 1,
        )
        items, nxt = pagination.page([dict(r) for r in rows], limit, ("sort_at", "id"))
        return Page(items=[await store.render_conversation(tx, r) for r in items], next_cursor=nxt)


class TalkConversationIn(Model):
    persona: Literal["secretary", "overseer", "assistant", "advisor", "manager"] = "secretary"
    role: str | None = Field(default=None, pattern=ROLE)
    company: str | None = Field(default=None, pattern=CODE)
    mode: Literal["consult", "work"] = "consult"
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _manager(self) -> TalkConversationIn:
        if self.persona == "manager" and not (self.role and self.company):
            raise ValueError("a manager is role@company: give role and company")
        return self


@router.post(
    "/talk/conversations", response_model=store.TalkConversation, status_code=201, responses=E
)
async def talk_open_conversation(
    body: TalkConversationIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """A new conversation with a persona (a manager: role and company, e.g.
    ceo@TY), consult by default. `Idempotency-Key` optional."""
    await _policy(ctx, "conversation.create", {"persona": body.persona})
    key = f"{body.role}@{body.company}" if body.persona == "manager" else body.persona
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        row = await service.new_conversation(ctx, tx, key, body.mode, body.title_fa)
        out = await store.render_conversation(tx, row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/talk/conversations/{ref}", response_model=store.TalkConversationDetail, responses=E)
async def talk_get_conversation(
    ref: str,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> store.TalkConversationDetail:
    """One conversation with its turns: without `cursor` the latest `limit`
    turns, oldest first; with it, the turns after it (oldest first)."""
    await _policy(ctx, "conversation.read", {"ref": ref})
    after = pagination.decode(cursor, 1)
    async with ctx.tx() as tx:
        conv = await store.conversation(tx, ref)
        if after is None:
            rows = list(reversed(await tx.all(
                "SELECT * FROM talk.turns WHERE conversation_id = :c ORDER BY n DESC LIMIT :l",
                c=conv["id"], l=limit,
            )))  # fmt: skip
            nxt = None
        else:
            rows = await tx.all(
                "SELECT * FROM talk.turns WHERE conversation_id = :c AND n > :n ORDER BY n LIMIT :l",
                c=conv["id"],
                n=int(after[0]),
                l=limit + 1,
            )
            rows, nxt = pagination.page([dict(r) for r in rows], limit, ("n",))
        cards = await store.cards_of(tx, [r["id"] for r in rows])
        files = await store.turn_files(tx, [dict(r) for r in rows])
        base = await store.render_conversation(tx, conv)
        present = []
        for key in conv["present"] or []:
            with contextlib.suppress(ApiError):
                present.append(
                    render_persona(await personas.resolve(tx, ctx.hub, key, store_voice=False))
                )
        return store.TalkConversationDetail(
            **base.model_dump(),
            turns_page=store.TalkTurnPage(
                items=[store.render_turn(dict(r), ref, cards[r["id"]], files) for r in rows],
                next_cursor=nxt,
            ),
            personas=present,
        )


class TalkConversationPatch(Model):
    mode: Literal["consult", "work"] | None = None
    title_fa: str | None = Field(default=None, min_length=1, max_length=200)


@router.patch("/talk/conversations/{ref}", response_model=store.TalkConversation, responses=E)
async def talk_patch_conversation(
    ref: str, body: TalkConversationPatch, ctx: Ctx = Depends(owner_ctx)
) -> store.TalkConversation:
    """The working-meeting toggle (consult | work) and the title."""
    await _policy(ctx, "conversation.update", {"ref": ref})
    async with ctx.tx() as tx:
        conv = await store.conversation(tx, ref, lock=True)
        row = await tx.one(
            """UPDATE talk.conversations SET mode = COALESCE(:m, mode), title_fa = COALESCE(:t, title_fa),
                   updated_at = now() WHERE id = :id RETURNING *""",
            m=body.mode,
            t=body.title_fa,
            id=conv["id"],
        )
        return await store.render_conversation(tx, row)


# ------------------------------------------------------------------ turns --
class TalkTurnIn(Model):
    # ⟨1.18⟩ §36.2 may be empty when the turn carries files
    text: str = Field(max_length=10000)
    source: store.Source = "typed"
    client_id: str | None = Field(default=None, min_length=1, max_length=100)
    # ⟨1.17⟩ §35.4 in a session: the participant who answers (a persona key), or "all" (each
    # present participant once, then the holder sums up); default: the holder
    to: str | None = Field(default=None, pattern=r"^(all|" + PERSONA_KEY[2:-2] + r")$")
    # ⟨1.18⟩ §36.2 the owner's own uploads with these words (at most 10); in a session every
    # one of them belongs to the order (§36.3)
    file_ids: list[UUID] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _words_or_files(self) -> TalkTurnIn:
        if not self.text and not self.file_ids:
            raise ValueError("text is empty and no file is sent")
        return self


@router.post(
    "/talk/conversations/{ref}/turns",
    response_model=store.TalkTurnAccepted,
    status_code=202,
    responses=E,
)
async def talk_add_turn(
    ref: str,
    body: TalkTurnIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """The owner says something. The words are stored at once (a key-shaped
    string replaced by «[کلید حذف شد]»: it never reaches a log, the Audit or a
    model), the rules act first (back to the secretary, a manager called in,
    the mode, «یادت باشه», «صورت‌جلسه کن»), and the answer streams on
    `events` (SSE). Requires `Idempotency-Key`; the same `client_id` again
    answers the same turn. Never 5xx: without a brain, the plain line. ⟨1.17⟩ §35.4 in a
    session `to` names who answers (a participant's key; a player answers through its seat), or
    `all` («نظر همه»): every present participant once, then the holder sums up (`turns`); a
    closed session answers 409. ⟨1.18⟩ §36.2 `file_ids`: the owner's own uploads (at most 10;
    one unknown, not the owner's or already sent in a company's thread: 422 with `message_fa`),
    kept on the owner's turn (`files`) and seen by the persona's model; in a session each one
    becomes a file of the order (a step, `OrderReport.files`, the works' briefs)."""
    await _policy(ctx, "turn.create", {"ref": ref})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        answers, owner = await service.add_turns(
            ctx, tx, ref, body.text, body.source, body.client_id, to=body.to,
            files=body.file_ids or [],
        )  # fmt: skip
        answer = answers[0]
        started = await tx.scalar(
            "SELECT state = 'streaming' AND NOT EXISTS (SELECT 1 FROM talk.turn_events WHERE turn_id = :id) "
            "FROM talk.turns WHERE id = :id",
            id=answer,
        )
        out = store.TalkTurnAccepted(
            turn=await store.turn_out(tx, answer),
            owner_turn=await store.turn_out(tx, owner) if owner else None,
            events=service.EVENTS_PATH.format(id=answer),
            turns=[await store.turn_out(tx, a) for a in answers],
        )
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    if started:
        background.add_task(service.dispatch_all, ctx.hub, answers)
    return out


@router.post(
    "/talk/conversations/{ref}/minutes",
    response_model=store.TalkTurnAccepted,
    status_code=202,
    responses=E,
)
async def talk_make_minutes(
    ref: str, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """«صورت‌جلسه کن» by the button: one `minutes` card from the conversation so
    far (a 5-10 line summary, the decisions, the tasks with their company,
    department and due date the owner can edit), in an answer of the persona.
    «اجرا کن» on it makes one order per task. Requires `Idempotency-Key`."""
    await _policy(ctx, "minutes", {"ref": ref})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        answer, _ = await service.add_turn(ctx, tx, ref, "", "typed", None, directive="minutes")
        out = store.TalkTurnAccepted(
            turn=await store.turn_out(tx, answer),
            owner_turn=None,
            events=service.EVENTS_PATH.format(id=answer),
            turns=[await store.turn_out(tx, answer)],
        )
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    background.add_task(service.dispatch, ctx.hub, answer)
    return out


class TalkInviteIn(Model):
    role: str = Field(min_length=2, max_length=41)
    company: str = Field(pattern=CODE)
    # ⟨additive⟩ with role "manager": the department whose manager is meant (the app's «+» picker)
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,11}$")

    @model_validator(mode="after")
    def _department(self) -> TalkInviteIn:
        if self.role == "manager" and self.department is None:
            raise ValueError("a manager is named by its department")
        return self


@router.post(
    "/talk/conversations/{ref}/invite", response_model=store.TalkConversationDetail, responses=E
)
async def talk_invite(ref: str, body: TalkInviteIn, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A manager joins (`role` is its charter, e.g. ceo or media_director, or a
    department code whose manager is meant): role@company becomes present and
    answers next, with its own charter, voice and its company's reads only;
    code writes the one-line notice. Back to the secretary by her face or «منشی».
    ⟨1.17⟩ §35.4 `role` advisor | overseer | assistant: the holding's fixed persona joins."""
    await _policy(ctx, "invite", {"ref": ref, "company": body.company})
    async with ctx.tx() as tx:
        word = body.department if body.role == "manager" and body.department else body.role
        key = await personas.invite_key(tx, ctx.hub, word, body.company)
        p = await personas.resolve(tx, ctx.hub, key)
        conv = await store.conversation(tx, ref, lock=True)
        if conv.get("closed_at") is not None:
            raise ApiError(409, "validation_failed", "the session is closed",
                           message_fa=service.CLOSED_FA)  # fmt: skip
        if p.key == conv.get("holder"):
            raise ApiError(409, "validation_failed", "the holder is here already",
                           message_fa="مسئول فرمان خودش در جلسه است.")  # fmt: skip
        await K.join_with_notice(tx, ctx.hub, conv, p)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="talk.invite", action_class="A0",
                        target_kind="conversation", target_ref=ref, summary=key)  # fmt: skip
    return await talk_get_conversation(ref, None, 50, ctx)


# ----------------------------------------------------------------- stream --
def _sse(seq: int, type_: str, payload: Any) -> str:
    return f"id: {seq}\nevent: {type_}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/talk/turns/{id}/events", responses=E)
async def talk_turn_events(
    id: UUID,
    request: Request,
    after_q: int | None = Query(default=None, alias="after", ge=0, le=2**31 - 1),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """SSE of one answer (`event:` = its type, `id:` = its seq): `text` {delta}
    of show_md, `say` {seq, text} a finished spoken sentence, `audio` {seq,
    file_id, seconds, engine}, `tool` {names} (the app plays its short local
    sound), `card` (a TalkCard), `invite` {persona, title_fa, notice_fa},
    `meter`, `error` {code, reason_fa}, `done` {state, turn}. Resumes after
    `Last-Event-ID` (or `?after`); ends after `done`; a comment line every
    15 s keeps the connection open."""
    await _policy(ctx, "conversation.read", {"turn": str(id)})
    after = after_q or 0
    if last_event_id:
        with contextlib.suppress(ValueError):
            after = max(0, min(int(last_event_id[:12]), 2**31 - 1))
    async with ctx.tx() as tx:
        await store.turn(tx, id)
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
                    """SELECT seq, type, data FROM talk.turn_events WHERE turn_id = :t AND seq > :a
                       ORDER BY seq LIMIT 200""",
                    t=id,
                    a=seq,
                )
                state = await tx.scalar("SELECT state FROM talk.turns WHERE id = :t", t=id)
            ended = False
            for r in rows:
                seq = r["seq"]
                yield _sse(seq, r["type"], store._j(r["data"]))
                ended = ended or r["type"] == "done"
            if ended or (not rows and state in store.FINAL):
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


@router.post("/talk/turns/{id}/stop", response_model=store.TalkTurn, responses=E)
async def talk_stop_turn(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> store.TalkTurn:
    """Barge-in (§32.7): the owner started speaking. Generation ends within a
    moment and sentences not yet spoken are not synthesised (not billed). A
    finished turn answers as it is."""
    await _policy(ctx, "turn.stop", {"turn": str(id)})
    return await service.stop(ctx, id)


# ------------------------------------------------------------------ cards --
class TalkCardRunIn(Model):
    payload: dict[str, Any] | None = None


@router.post("/talk/cards/{id}/run", response_model=store.TalkCardRun, responses=E)
async def talk_run_card(
    id: UUID,
    body: TalkCardRunIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> store.TalkCardRun:
    """The owner taps a card (with edits in `payload`): it runs the existing
    route of its kind with that route's own checks and step-ups (order and ask:
    the dispatcher of §29.4; minutes: one order per task; hire: the manager's
    proposal; decision; planner; rule; automation: compiled, then proposed;
    invite). → `made`: the refs it made. A done card answers what it made.
    Requires `Idempotency-Key` (each step of the card derives its own)."""
    await _policy(ctx, "card.run", {"card": str(id)})
    idempotency.read_key(request, required=True)
    return await K.run(ctx, request, background, id, body.payload)


@router.post("/talk/cards/{id}/dismiss", response_model=store.TalkCard, responses=E)
async def talk_dismiss_card(id: UUID, ctx: Ctx = Depends(owner_ctx)) -> store.TalkCard:
    """The owner puts a card aside; nothing is made. A done card cannot be."""
    await _policy(ctx, "card.dismiss", {"card": str(id)})
    async with ctx.tx() as tx:
        card = await tx.first("SELECT * FROM talk.cards WHERE id = :id FOR UPDATE", id=id)
        if card is None:
            raise ApiError(404, "not_found", "unknown card", message_fa="این کارت پیدا نشد.")
        if card["state"] == "done":
            raise ApiError(409, "validation_failed", "the card was run",
                           message_fa="این کارت اجرا شده است.")  # fmt: skip
        row = await tx.one(
            "UPDATE talk.cards SET state = 'dismissed', updated_at = now() WHERE id = :id RETURNING *",
            id=id,
        )
        await ctx.audit(tx, company_id=card["company_id"], action="talk.card", action_class="A0",
                        target_kind="talk_card", target_ref=str(id), summary=f"{card['kind']} dismissed")  # fmt: skip
        return store.render_card(dict(row))
