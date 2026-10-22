"""The support desk (prompt 10 §4-§6, §11; contract §19.3-§19.4, §19.6).

Owner (/api/v1):
  GET   /support/channels                      ?company
  POST  /support/channels/{company}/{kind}/pause   no step-up (stopping is always safe)
  PATCH /support/channels/{company}/{kind}     If-Match · {auto_send?, state?: "live"}; widening
                                               (kb_grounded, or a paused channel that already
                                               went live back to live) 🔏 support.channel =
                                               company/kind@auto_send; never-live -> 409
                                               shadow_not_passed
  GET   /support/conversations[/{ref}]         mystery conversations are never listed or counted
  POST  /support/conversations/{ref}/reply     the owner's answer, through the guard (no exception);
                                               422 send_blocked · Idempotency-Key (required)
  POST  /support/conversations/{ref}/teach     the answer (if it waits) + a KbArticle proposal ·
                                               Idempotency-Key (required)
  POST  /support/conversations/{ref}/close
  GET   /support/queue                         the teaching queue, oldest first
  GET · POST /support/kb · POST /support/kb/{ref}/approve 🔏 support.kb = ref@version ·
  POST  /support/kb/{ref}/retire
  POST  /support/history                       {company, file_id}: the private shadow suite
  GET   /support/shadow · POST /support/shadow/{company}/run
Agents (/internal/v1): kb.search (GET /support/kb), kb.propose (POST /support/kb),
  support.draft, support.handoff, support.mystery; OPA ops kb.read, kb.propose,
  support.draft, support.handoff, support.mystery (support.rego, support_desk.rego).
A customer's text is stored only through domain.support.store_inbound (masked
first) and read by a model only through domain.support.model_view.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import desk, kb, shadow
from hq_api.domain import support as S
from hq_api.domain import work as W
from hq_api.errors import ApiError, problem_response, responses
from hq_api.http import check_version, if_match
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model, Page
from hq_api.security import stepup
from hq_common import customer_mask

router = APIRouter(tags=["support"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428, 429)
KB_REF = r"^KB-[0-9]{4,6}$"
CONV_REF = r"^SC-[0-9]{6,}$"
ChannelKind = Literal["telegram_business", "telegram_bot", "chatwoot", "product_bot"]


# ------------------------------------------------------------------ models --
class SupportConversationDetail(BaseModel):
    conversation: desk.Conversation
    messages: list[desk.SupportMessage]


class SupportChannelPatch(Model):
    auto_send: Literal["kb_verbatim", "kb_grounded", "off"] | None = None
    state: Literal["live"] | None = None


class SupportPauseIn(Model):
    reason: str | None = Field(default=None, max_length=300)


class SupportReplyIn(Model):
    body: str = Field(min_length=1, max_length=4000)


class SupportTeachIn(Model):
    message_id: UUID | None = None
    answer_md: str = Field(min_length=1, max_length=4000)
    generalise: bool = True


class SupportTeachOut(BaseModel):
    message: desk.SupportMessage | None
    article: kb.KbArticle


class KbArticleIn(Model):
    company: str = Field(pattern=CODE)
    kind: Literal["faq", "policy", "procedure", "referral", "official_link", "safety"]
    key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.]{1,60}$")
    question_fa: str = Field(min_length=1, max_length=1000)
    variants: list[str] = Field(default_factory=list, max_length=50)
    answer_md: str = Field(min_length=1, max_length=8000)
    variables: list[kb.KbVariable] = Field(default_factory=list, max_length=20)
    links: list[kb.KbLink] = Field(default_factory=list, max_length=20)
    codes: list[kb.KbCode] = Field(default_factory=list, max_length=20)
    ref: str | None = Field(default=None, pattern=KB_REF)
    expiry_days: int = Field(default=180, ge=1, le=3650)


class KbApproveIn(Model):
    version: int | None = Field(default=None, ge=1)


class SupportHistoryIn(Model):
    company: str = Field(pattern=CODE)
    file_id: UUID


class SupportHistoryOut(BaseModel):
    id: UUID
    company: str
    state: Literal["queued", "parsing", "done", "failed"]
    format: str | None
    pairs_found: int | None
    cases_kept: int | None
    topics: dict[str, int]
    suite: str | None
    error: str | None


# ----------------------------------------------------------------- helpers --
async def _company(ctx: Ctx, code: str) -> Any:
    co = await ctx.hub.companies.find(code)
    if co is None:
        raise ApiError(404, "not_found", f"no company {code}")
    return co


async def _conv_out(ctx: Ctx, r: dict[str, Any]) -> desk.Conversation:
    return desk.render_conversation(r, await ctx.hub.companies.code_of(r["company_id"]))


async def _message_out(tx: Any, row: dict[str, Any]) -> desk.SupportMessage:
    ref = await tx.scalar(
        "SELECT ref FROM support.conversations WHERE id = :id", id=row["conversation_id"]
    )
    return desk.render_message(row, str(ref))


# ---------------------------------------------------------------- channels --
@router.get("/support/channels", response_model=list[desk.SupportChannel], responses=E)
async def list_channels(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[desk.SupportChannel]:
    """Every customer channel of each company (made on first use with its
    defaults: not_configured, kb_verbatim). The mystery channel is PR-043's."""
    companies = [await _company(ctx, company)] if company else await ctx.hub.companies.all()
    out: list[desk.SupportChannel] = []
    async with ctx.tx() as tx:
        for co in companies:
            if co.kind == "holding" and not company:
                continue
            for kind in desk.LIVE_KINDS:
                out.append(desk.render_channel(await S.channel(tx, co.id, kind), co.code))
    return out


@router.post(
    "/support/channels/{company}/{kind}/pause",
    response_model=desk.SupportChannel,
    responses=E,
)
async def pause_channel(
    company: str, kind: ChannelKind, body: SupportPauseIn, ctx: Ctx = Depends(owner_ctx)
) -> desk.SupportChannel:
    """Stops automatic answers on the channel at once (no step-up: stopping
    is always safe). Going live again is a widening (🔏)."""
    co = await _company(ctx, company)
    async with ctx.tx() as tx:
        await S.channel(tx, co.id, kind)
        row = await tx.one(
            """UPDATE support.channels SET state = CASE WHEN state = 'live' THEN 'paused' ELSE state END,
                   paused_at = now(), paused_reason = :r, updated_at = now()
               WHERE company_id = :co AND kind = :k RETURNING *""",
            co=co.id,
            k=kind,
            r=body.reason or "owner",
        )
        await ctx.audit(
            tx, company_id=co.id, action="support.channel_pause", action_class="A1",
            target_kind="support_channel", target_ref=f"{co.code}/{kind}",
            summary=body.reason or "",
        )  # fmt: skip
        await ctx.emit(tx, co.code, "support.channel", f"{co.code}/{kind}", {"state": row["state"]})
    return desk.render_channel(row, co.code)


@router.patch("/support/channels/{company}/{kind}", response_model=desk.SupportChannel, responses=E)
async def patch_channel(
    company: str,
    kind: ChannelKind,
    body: SupportChannelPatch,
    request: Request,
    ctx: Ctx = Depends(owner_ctx),
) -> desk.SupportChannel:
    """`If-Match` (the channel's version). Widening — to `kb_grounded`, or a
    paused channel that already went live back to `live` — needs 🔏
    `support.channel` with target `company/kind@auto_send` (the resulting
    auto_send); narrowing to `kb_verbatim` or `off` needs none. A channel
    that never went live cannot be put live here: 409 shadow_not_passed
    (only a sealed support_go_live card does that)."""
    expected = if_match(request)
    co = await _company(ctx, company)
    async with ctx.tx() as tx:
        await S.channel(tx, co.id, kind)
        ch = await tx.one(
            "SELECT * FROM support.channels WHERE company_id = :co AND kind = :k FOR UPDATE",
            co=co.id,
            k=kind,
        )
        check_version(ch["version"], expected)
        auto_send = body.auto_send or ch["auto_send"]
        to_live = body.state == "live" and ch["state"] != "live"
        if body.state == "live" and ch["live_since"] is None:
            raise ApiError(409, "shadow_not_passed", "this channel never went live: a go-live card")
        widening = to_live or (body.auto_send == "kb_grounded" and ch["auto_send"] != "kb_grounded")
        step_up_id = None
        if widening:
            step_up_id = await stepup.consume(
                tx, request, ctx.who, "support.channel", f"{co.code}/{kind}@{auto_send}"
            )
        row = await tx.one(
            """UPDATE support.channels SET auto_send = :a,
                   state = CASE WHEN :live THEN 'live' ELSE state END,
                   paused_at = CASE WHEN :live THEN NULL ELSE paused_at END,
                   paused_reason = CASE WHEN :live THEN NULL ELSE paused_reason END,
                   updated_at = now()
               WHERE company_id = :co AND kind = :k RETURNING *""",
            a=auto_send,
            live=to_live,
            co=co.id,
            k=kind,
        )
        await ctx.audit(
            tx, company_id=co.id, action="support.channel", action_class="A3" if widening else "A1",
            target_kind="support_channel", target_ref=f"{co.code}/{kind}",
            summary=f"auto_send={auto_send}" + (", live" if to_live else ""),
            step_up=step_up_id is not None,
        )  # fmt: skip
        await ctx.emit(
            tx, co.code, "support.channel", f"{co.code}/{kind}",
            {"state": row["state"], "auto_send": row["auto_send"]},
        )  # fmt: skip
    return desk.render_channel(row, co.code)


# ----------------------------------------------------------- conversations --
@router.get("/support/conversations", response_model=Page[desk.Conversation], responses=E)
async def list_conversations(
    company: str | None = Query(default=None, pattern=CODE),
    state: Literal["open", "waiting_owner", "answered", "closed"] | None = None,
    channel: ChannelKind | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[desk.Conversation]:
    """Newest first. Mystery conversations (PR-043) are never listed."""
    co = await _company(ctx, company) if company else None
    after_at, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            desk.CONV_SQL  # noqa: S608 - module constants; values are bound
            + """ WHERE NOT c.mystery
                  AND (CAST(:co AS uuid) IS NULL OR c.company_id = :co)
                  AND (CAST(:st AS text) IS NULL OR c.state = :st)
                  AND (CAST(:ch AS text) IS NULL OR c.channel = :ch)
                  AND (CAST(:q AS text) IS NULL OR EXISTS (
                        SELECT 1 FROM support.messages m WHERE m.conversation_id = c.id
                          AND m.search @@ plainto_tsquery('simple', core.fa_normalize(:q))))
                  AND (CAST(:aa AS timestamptz) IS NULL OR (c.last_message_at, c.id) < (:aa, :ai))
                ORDER BY c.last_message_at DESC, c.id DESC LIMIT :lim""",
            co=co.id if co else None,
            st=state,
            ch=channel,
            q=q,
            aa=after_at,
            ai=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("last_message_at", "id"))
    return Page(items=[await _conv_out(ctx, r) for r in items], next_cursor=nxt)


@router.get("/support/conversations/{ref}", response_model=SupportConversationDetail, responses=E)
async def get_conversation(ref: str, ctx: Ctx = Depends(owner_ctx)) -> SupportConversationDetail:
    """One conversation with its messages, oldest first (bodies masked)."""
    async with ctx.tx() as tx:
        conv = await desk.conversation(tx, ref)
        msgs = await desk.messages(tx, conv["id"])
    return SupportConversationDetail(
        conversation=await _conv_out(ctx, conv),
        messages=[desk.render_message(m, ref) for m in msgs],
    )


@router.post("/support/conversations/{ref}/reply", response_model=desk.SupportMessage, responses=E)
async def reply(
    ref: str, body: SupportReplyIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner's answer, sent at once through the outbound guard like any
    other (no exception for asks_secret, profit_promise or red_line): 422
    send_blocked with `fields.blocked_reasons`, and the refused text is kept
    `blocked`. Requires `Idempotency-Key` (a phone's retry sends nothing twice)."""
    refused: ApiError | None = None
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        conv = await desk.conversation(tx, ref, lock=True)
        try:
            row = await desk.owner_send(tx, ctx.hub, conv, body.body)
        except ApiError as err:
            if err.code != "send_blocked":
                raise
            refused = err
            await desk.record_blocked(tx, conv, body.body, "owner")
            if idem:
                await idem.store(tx, 422, {"code": "send_blocked", "fields": err.fields})
        if refused is None:
            out = await _message_out(tx, row)
            await _taught(ctx, tx, conv, body.body, generalise=True)
            await _owner_audit(ctx, tx, conv, "support.reply", row["id"])
            if idem:
                await idem.store(tx, 200, out.model_dump(mode="json"))
        else:
            await _owner_audit(ctx, tx, conv, "support.reply_blocked", None)
    if refused is not None:
        return problem_response(request, refused)
    await workflows_client.support(ctx.hub, "SupportSend", str(row["id"]))
    return out


@router.post("/support/conversations/{ref}/teach", response_model=SupportTeachOut, responses=E)
async def teach_conversation(
    ref: str, body: SupportTeachIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Teaching mode: the owner's answer (or correction of the agent's draft)
    is sent when the conversation still waits, and becomes a proposed
    article (source owner_answer); with a support lead and `generalise`, the
    lead turns it into a general one (kb.propose). Requires `Idempotency-Key`."""
    refused: ApiError | None = None
    sent: dict[str, Any] | None = None
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        conv = await desk.conversation(tx, ref, lock=True)
        if body.message_id is not None and not await tx.scalar(
            "SELECT 1 FROM support.messages WHERE id = :m AND conversation_id = :c",
            m=body.message_id,
            c=conv["id"],
        ):
            raise ApiError(
                422, "validation_failed", fields={"message_id": "not in this conversation"}
            )
        if conv["state"] in ("waiting_owner", "open"):
            try:
                sent = await desk.owner_send(tx, ctx.hub, conv, body.answer_md)
            except ApiError as err:
                if err.code != "send_blocked":
                    raise
                refused = err
                await desk.record_blocked(tx, conv, body.answer_md, "owner")
                if idem:
                    await idem.store(tx, 422, {"code": "send_blocked", "fields": err.fields})
        if refused is None:
            article = await _taught(ctx, tx, conv, body.answer_md, generalise=body.generalise)
            out = SupportTeachOut(
                message=await _message_out(tx, sent) if sent else None,
                article=kb.render(article, await ctx.hub.companies.code_of(conv["company_id"])),
            )
            await _owner_audit(ctx, tx, conv, "support.teach", sent["id"] if sent else None)
            if idem:
                await idem.store(tx, 200, out.model_dump(mode="json"))
    if refused is not None:
        return problem_response(request, refused)
    if sent is not None:
        await workflows_client.support(ctx.hub, "SupportSend", str(sent["id"]))
    return out


async def _taught(
    ctx: Ctx, tx: Any, conv: dict[str, Any], answer: str, *, generalise: bool
) -> dict[str, Any]:
    """The owner's answer becomes a proposed faq of the conversation's
    company (masked; the question is the customer's last message, masked as
    a quote); the support lead, if hired, generalises it."""
    question = await tx.scalar(
        """SELECT body FROM support.messages WHERE conversation_id = :c AND direction = 'in'
             AND body IS NOT NULL ORDER BY at DESC LIMIT 1""",
        c=conv["id"],
    )
    article = await kb.propose(
        tx,
        company_id=conv["company_id"],
        kind="faq",
        question_fa=customer_mask.quote(str(question or "پرسش مشتری"), max_chars=1000),
        answer_md=customer_mask.quote(answer, max_chars=8000),
        by_kind="owner",
        by_code="owner",
        source={"kind": "owner_answer", "ref": conv["ref"]},
    )
    lead = await tx.first(
        """SELECT code FROM core.employees WHERE company_id = :co AND role = 'support_lead'
             AND status = 'active' LIMIT 1""",
        co=conv["company_id"],
    )
    if lead is not None and generalise and not conv["mystery"]:
        company = await ctx.hub.companies.code_of(conv["company_id"])
        await W.create(
            tx,
            desk.SYSTEM,
            company_id=conv["company_id"],
            company_code=company,
            title=f"تعمیم آموزش مالک: {article['ref']} ({conv['ref']})"[:300],
            brief=(
                f"The owner answered conversation {conv['ref']}; the raw proposal is "
                f"{article['ref']}@{article['version']}. Turn it into a GENERAL article with "
                "kb.propose (source_ref = the conversation, ref = the article): no customer data, "
                "variables marked as <name>, links and codes left for the owner. If it fits only "
                "that one customer, say so and propose nothing."
            ),
            kind="one_off",
            priority="P2",
            assignee_code=lead["code"],
        )
    return article


async def _owner_audit(
    ctx: Ctx, tx: Any, conv: dict[str, Any], action: str, message_id: UUID | None
) -> None:
    await ctx.audit(
        tx, company_id=conv["company_id"], action=action, action_class="A2",
        target_kind="support_conversation", target_ref=conv["ref"],
        summary=f"message {message_id}" if message_id else "blocked by the outbound guard",
    )  # fmt: skip
    company = await ctx.hub.companies.code_of(conv["company_id"])
    await ctx.emit(tx, company, "support.message", conv["ref"], {"author": "owner"})


@router.post("/support/conversations/{ref}/close", response_model=desk.Conversation, responses=E)
async def close_conversation(ref: str, ctx: Ctx = Depends(owner_ctx)) -> desk.Conversation:
    """Closed; the sealed csat rule (if active) asks the customer 1..5."""
    async with ctx.tx() as tx:
        conv = await desk.conversation(tx, ref, lock=True)
        await desk.close(tx, ctx.hub, conv, ctx.who)
        await ctx.audit(
            tx, company_id=conv["company_id"], action="support.close", action_class="A1",
            target_kind="support_conversation", target_ref=ref,
        )  # fmt: skip
        return await _conv_out(ctx, await desk.conversation(tx, ref))


@router.get("/support/queue", response_model=list[desk.QueueItem], responses=E)
async def teaching_queue(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[desk.QueueItem]:
    """What waits for the owner, oldest first: handoffs, drafts that did not
    go, the guard's refusals and the latest shadow run's disagreements."""
    co = await _company(ctx, company) if company else None
    items: list[desk.QueueItem] = []
    async with ctx.tx() as tx:
        for r in await desk.queue(tx, co.id if co else None):
            draft = None
            kind: Literal["handoff", "low_confidence", "blocked", "shadow_disagreement"] = "handoff"
            if r["draft_id"] is not None:
                m = await tx.one("SELECT * FROM support.messages WHERE id = :id", id=r["draft_id"])
                draft = desk.render_message(m, r["ref"])
                kind = "blocked" if m["status"] == "blocked" else "low_confidence"
            items.append(
                desk.QueueItem(
                    conversation=r["ref"],
                    kind=kind,
                    since=r["handoff_at"],
                    draft=draft,
                    company=await ctx.hub.companies.code_of(r["company_id"]),
                    reason=r["handoff_reason"],
                )
            )
        for s in await desk.shadow_disagreements(tx, co.id if co else None):
            for d in s["disagreements"] or []:
                items.append(
                    desk.QueueItem(
                        conversation=f"{s['suite_ref']}@{s['suite_version']}:{d.get('case')}",
                        kind="shadow_disagreement",
                        since=s["at"],
                        draft=None,
                        company=await ctx.hub.companies.code_of(s["company_id"]),
                        reason=str(d.get("note_fa") or d.get("verdict") or "")[:300],
                    )
                )
    items.sort(key=lambda i: i.since)
    return items


# ---------------------------------------------------------- knowledge base --
@router.get("/support/kb", response_model=list[kb.KbArticle], responses=E)
async def list_kb(
    company: str | None = Query(default=None, pattern=CODE),
    kind: Literal["faq", "policy", "procedure", "referral", "official_link", "safety"]
    | None = None,
    status: Literal["proposed", "approved", "expired", "retired"] | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> list[kb.KbArticle]:
    """Every version (newest first per ref), or a search when `q` is given."""
    co = await _company(ctx, company) if company else None
    async with ctx.tx() as tx:
        if q and co is not None:
            rows = await kb.search(
                tx, co.id, q, kinds=[kind] if kind else None, include_proposed=True, limit=50
            )
        else:
            rows = await tx.all(
                f"""SELECT a.*, {kb.USES_SQL} FROM support.kb_articles a
                    WHERE (CAST(:co AS uuid) IS NULL OR a.company_id = :co)
                      AND (CAST(:k AS text) IS NULL OR a.kind = :k)
                    ORDER BY a.ref, a.version DESC LIMIT 1000""",  # noqa: S608 - constants
                co=co.id if co else None,
                k=kind,
            )
    out = [kb.render(r, await ctx.hub.companies.code_of(r["company_id"])) for r in rows]
    return [a for a in out if status is None or a.status == status]


@router.post("/support/kb", response_model=kb.KbArticle, status_code=201, responses=E)
async def propose_kb(body: KbArticleIn, ctx: Ctx = Depends(owner_ctx)) -> kb.KbArticle:
    """The owner's article (or a new version of `ref`) -> proposed. Only the
    owner writes referral codes and links. Approving it is 🔏."""
    co = await _company(ctx, body.company)
    async with ctx.tx() as tx:
        row = await kb.propose(
            tx, company_id=co.id, kind=body.kind, key=body.key, question_fa=body.question_fa,
            variants=body.variants, answer_md=body.answer_md,
            variables=[v.model_dump() for v in body.variables],
            links=[x.model_dump() for x in body.links], codes=[x.model_dump() for x in body.codes],
            source={"kind": "owner"}, ref=body.ref, expiry_days=body.expiry_days,
            by_kind="owner", by_code="owner",
        )  # fmt: skip
        await ctx.audit(
            tx, company_id=co.id, action="support.kb_propose", action_class="A1",
            target_kind="kb_article", target_ref=f"{row['ref']}@{row['version']}",
        )  # fmt: skip
    return kb.render(row, co.code)


@router.post("/support/kb/{ref}/approve", response_model=kb.KbArticle, responses=E)
async def approve_kb(
    ref: str, body: KbApproveIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> kb.KbArticle:
    """🔏 `support.kb`, target `ref@version` (the latest proposed version
    when none is given): an approved article is what may reach a customer
    without the owner. The ref's earlier approved version is retired."""
    async with ctx.tx() as tx:
        version = body.version or await tx.scalar(
            """SELECT max(version) FROM support.kb_articles WHERE ref = :r AND status = 'proposed'""",
            r=ref,
        )
        if version is None:
            await kb.load(tx, ref)  # 404 when unknown
            raise ApiError(409, "validation_failed", f"{ref} has no proposed version")
        step_up_id = await stepup.consume(tx, request, ctx.who, "support.kb", f"{ref}@{version}")
        current = await kb.load(tx, ref, int(version))
        st = await S.settings(tx, current["company_id"])
        row = await kb.approve(
            tx, ref, int(version), step_up_id=step_up_id, expiry_days=int(st["kb_expiry_days"])
        )
        company = await ctx.hub.companies.code_of(row["company_id"])
        await ctx.audit(
            tx, company_id=row["company_id"], action="support.kb_approve", action_class="A3",
            target_kind="kb_article", target_ref=f"{ref}@{version}", step_up=True,
        )  # fmt: skip
        await ctx.emit(tx, company, "support.channel", ref, {"kb": "approved", "version": version})
    return kb.render(row, company)


@router.post("/support/kb/{ref}/retire", response_model=kb.KbArticle, responses=E)
async def retire_kb(ref: str, ctx: Ctx = Depends(owner_ctx)) -> kb.KbArticle:
    """Retired at once (no step-up: removing an answer is always safe)."""
    async with ctx.tx() as tx:
        row = await kb.retire(tx, ref)
        await ctx.audit(
            tx, company_id=row["company_id"], action="support.kb_retire", action_class="A1",
            target_kind="kb_article", target_ref=ref,
        )  # fmt: skip
        company = await ctx.hub.companies.code_of(row["company_id"])
    return kb.render(row, company)


# ------------------------------------------------------------------ shadow --
@router.post("/support/history", response_model=SupportHistoryOut, status_code=201, responses=E)
async def import_history(
    body: SupportHistoryIn, ctx: Ctx = Depends(owner_ctx)
) -> SupportHistoryOut:
    """The owner's real history (Telegram Desktop result.json, or a CSV of
    question,answer) -> up to 100 masked cases across topics -> the
    company's private suite support-shadow-<CO> (never leaves the company).
    Rule-only: no model."""
    co = await _company(ctx, body.company)
    async with ctx.tx() as tx:
        row = await shadow.import_history(
            tx, ctx.hub, company_id=co.id, company=co.code, file_id=body.file_id, by="owner"
        )
        await ctx.audit(
            tx, company_id=co.id, action="support.history", action_class="A1",
            target_kind="shadow_suite", target_ref=shadow.suite_ref(co.code),
            summary=f"{row['state']}: {row['cases_kept'] or 0} cases",
        )  # fmt: skip
    return SupportHistoryOut(
        id=row["id"], company=co.code, state=row["state"], format=row["format"],
        pairs_found=row["pairs_found"], cases_kept=row["cases_kept"],
        topics=dict(row["topics"] or {}),
        suite=f"{row['suite_ref']}@{row['suite_version']}" if row["suite_ref"] else None,
        error=row["error"],
    )  # fmt: skip


@router.get("/support/shadow", response_model=list[shadow.ShadowReport], responses=E)
async def shadow_reports(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> list[shadow.ShadowReport]:
    """The latest shadow run of each company (or of one)."""
    co = await _company(ctx, company) if company else None
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT DISTINCT ON (company_id) * FROM support.shadow_runs
               WHERE CAST(:co AS uuid) IS NULL OR company_id = :co
               ORDER BY company_id, at DESC""",
            co=co.id if co else None,
        )
    return [shadow.render_report(r, await ctx.hub.companies.code_of(r["company_id"])) for r in rows]


@router.post(
    "/support/shadow/{company}/run",
    response_model=shadow.ShadowReport,
    status_code=202,
    responses=E,
)
async def run_shadow(company: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """A shadow run of the support charter on the company's suite (academy
    tokens; the worker runs it, and only while the hub is not locked).
    Requires `Idempotency-Key`."""
    co = await _company(ctx, company)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row = await shadow.queue_run(
            tx, ctx.hub, company_id=co.id, company=co.code, by_kind="owner", by_code="owner"
        )
        await ctx.audit(
            tx, company_id=co.id, action="support.shadow_run", action_class="A1",
            target_kind="shadow_run", target_ref=str(row["id"]),
        )  # fmt: skip
        out = shadow.render_report(row, co.code)
        if idem:
            await idem.store(tx, 202, out.model_dump(mode="json"))
    await workflows_client.support(ctx.hub, "SupportShadow", str(row["id"]))
    return JSONResponse(out.model_dump(mode="json"), status_code=202)


# ---------------------------------------------------------------- internal --
class KbSearchHit(BaseModel):
    ref: str
    version: int
    kind: str
    key: str | None
    question_fa: str
    answer_md: str
    status: str
    score: float
    expires_at: datetime


class KbProposalIn(Model):
    company: str | None = Field(default=None, pattern=CODE)
    kind: Literal["faq", "policy", "procedure", "referral", "official_link", "safety"]
    question_fa: str = Field(min_length=1, max_length=1000)
    answer_md: str = Field(min_length=1, max_length=8000)
    variables: list[kb.KbVariable] = Field(default_factory=list, max_length=20)
    source_ref: str = Field(min_length=1, max_length=200)
    ref: str | None = Field(default=None, pattern=KB_REF)
    key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.]{1,60}$")
    variants: list[str] = Field(default_factory=list, max_length=50)


class SupportDraftIn(Model):
    body_md: str = Field(min_length=1, max_length=4000)
    kb_refs: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)


class SupportHandoffIn(Model):
    reason: Literal["no_kb", "low_confidence", "asked_for_human", "complaint", "security"]
    note_fa: str = Field(default="", max_length=1000)


class SupportMysteryIn(Model):
    company: str = Field(pattern=CODE)
    question_fa: str | None = Field(default=None, min_length=1, max_length=2000)
    conversation: str | None = Field(default=None, pattern=CONV_REF)


def _agent_company(ctx: Ctx, code: str | None) -> str:
    assert ctx.who.company is not None
    return code or ctx.who.company


@internal_router.get("/support/kb", response_model=list[KbSearchHit], responses=E)
async def kb_search(
    q: str = Query(min_length=2, max_length=200),
    company: str | None = Query(default=None, pattern=CODE),
    kind: Literal["faq", "policy", "procedure", "referral", "official_link", "safety"]
    | None = None,
    ctx: Ctx = Depends(internal_ctx),
) -> list[KbSearchHit]:
    """kb.search: the company's approved articles; the support people see
    proposed ones too. Another company's base: 403 (OPA kb.read)."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    code = _agent_company(ctx, company)
    await allow(ctx, "kb.read", {"company": code, "status": "approved", "charter": ctx.who.charter})
    proposed = True
    try:
        await allow(
            ctx, "kb.read", {"company": code, "status": "proposed", "charter": ctx.who.charter}
        )
    except ApiError:
        proposed = False
    co = await _company(ctx, code)
    async with ctx.tx() as tx:
        rows = await kb.search(
            tx, co.id, q, kinds=[kind] if kind else None, include_proposed=proposed, limit=10
        )
    return [
        KbSearchHit(
            ref=r["ref"],
            version=r["version"],
            kind=r["kind"],
            key=r["key"],
            question_fa=r["question_fa"],
            answer_md=r["answer_md"],
            status=kb.status_of(r),
            score=float(r["score"]),
            expires_at=r["expires_at"],
        )
        for r in rows
    ]


@internal_router.post("/support/kb", response_model=kb.KbArticle, status_code=201, responses=E)
async def kb_propose(body: KbProposalIn, ctx: Ctx = Depends(internal_ctx)) -> kb.KbArticle:
    """kb.propose: a proposed article (or version) of the agent's own
    company; never a link or a code (only the owner writes them)."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    code = _agent_company(ctx, body.company)
    await allow(ctx, "kb.propose", {"company": code, "charter": ctx.who.charter})
    co = await _company(ctx, code)
    async with ctx.tx() as tx:
        await ctx.ensure_unlocked(tx, co.id)
        row = await kb.propose(
            tx, company_id=co.id, kind=body.kind, key=body.key, question_fa=body.question_fa,
            variants=body.variants, answer_md=body.answer_md,
            variables=[v.model_dump() for v in body.variables],
            source={"kind": "agent", "ref": body.source_ref[:200]}, ref=body.ref,
            by_kind="agent", by_code=ctx.who.code,
        )  # fmt: skip
        await ctx.audit(
            tx, company_id=co.id, action="kb.propose", action_class="A1",
            target_kind="kb_article", target_ref=f"{row['ref']}@{row['version']}",
        )  # fmt: skip
    return kb.render(row, co.code)


class SupportDraftOut(BaseModel):
    decision: Literal["queued", "waiting_owner", "blocked"]
    message: desk.SupportMessage
    problems: list[str]


@internal_router.post(
    "/support/conversations/{ref}/draft", response_model=SupportDraftOut, responses=E
)
async def support_draft(
    ref: str, body: SupportDraftIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """support.draft: the code decides (grounded, the guard, the channel's
    auto_send): queued for the customer, waiting for the owner, or blocked.
    Requires `Idempotency-Key`."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    assert ctx.who.company is not None
    await allow(ctx, "support.draft", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await desk.draft(
            tx, ctx.hub, ctx.who, ref, body_md=body.body_md, kb_refs=body.kb_refs,
            confidence=body.confidence,
        )  # fmt: skip
        conv = await desk.conversation(tx, ref)
        await ctx.audit(
            tx, company_id=conv["company_id"], action="support.draft", action_class="A2",
            target_kind="support_conversation", target_ref=ref,
            summary=f"{out['decision']}: {','.join(out['problems'])[:200]}",
        )  # fmt: skip
        result = SupportDraftOut(
            decision=out["decision"],
            message=desk.render_message(out["message"], ref),
            problems=[str(p) for p in out["problems"] if p],
        )
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    if out["decision"] == "queued":
        await workflows_client.support(ctx.hub, "SupportSend", str(out["message"]["id"]))
    return result


@internal_router.post(
    "/support/conversations/{ref}/handoff", response_model=desk.Conversation, responses=E
)
async def support_handoff(
    ref: str, body: SupportHandoffIn, ctx: Ctx = Depends(internal_ctx)
) -> desk.Conversation:
    """support.handoff: the conversation waits for the owner; the customer
    gets the sealed holding reply."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    assert ctx.who.company is not None
    await allow(ctx, "support.handoff", {"company": ctx.who.company, "charter": ctx.who.charter})
    queued: list[UUID] = []
    async with ctx.tx() as tx:
        conv = await desk.conversation(tx, ref, lock=True)
        if conv["company_id"] != ctx.who.company_id or conv["state"] == "closed":
            raise ApiError(404, "not_found", f"no open conversation {ref}")
        out = await desk.handoff(tx, ctx.hub, conv, body.reason, note=body.note_fa, by=ctx.who.code)
        queued = desk._ids(out)
        await ctx.audit(
            tx, company_id=conv["company_id"], action="support.handoff", action_class="A2",
            target_kind="support_conversation", target_ref=ref, summary=body.reason,
        )  # fmt: skip
        result = await _conv_out(ctx, await desk.conversation(tx, ref))
    for m in queued:
        await workflows_client.support(ctx.hub, "SupportSend", str(m))
    return result


@internal_router.post("/support/mystery", responses=E)
async def support_mystery(
    body: SupportMysteryIn, ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    """support.mystery (the overseer only, PR-043): a mystery customer's
    question through the whole path on the `mystery` channel, which never
    reaches Telegram or Chatwoot and is left out of every statistic; a
    company with no live channel answers `deferred`. With `conversation`
    instead of a question: that mystery conversation's transcript."""
    await allow(ctx, "support.mystery", {"company": body.company, "charter": ctx.who.charter})
    co = await _company(ctx, body.company)
    holding = await ctx.hub.companies.holding()
    # The one widened scope: the target company (OPA allowed the overseer) and
    # the holding (its audit row).
    async with ctx.hub.db.tx([co.id, holding.id]) as tx:
        if body.conversation:
            out = await desk.mystery_transcript(tx, body.conversation)
            if not out["conversation"]:
                raise ApiError(404, "not_found", "no such mystery conversation")
            return out
        if not body.question_fa:
            raise ApiError(422, "validation_failed", fields={"question_fa": "required"})
        out = await desk.mystery(tx, ctx.hub, co.id, body.question_fa, by=ctx.who.code)
        await ctx.audit(
            tx, company_id=holding.id, action="support.mystery", action_class="A2",
            target_kind="support_conversation", target_ref=out.get("conversation") or co.code,
            summary=str(out.get("result")),
        )  # fmt: skip
    return out
