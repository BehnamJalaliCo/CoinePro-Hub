"""The legal counsel (prompt 13 §3, contract §22.4, §22.7).

Owner:
    GET  /legal/cases            ?company&status&cursor, newest first
    POST /legal/cases            {company, title_fa, kind, brief_md, file_ids?} · Idempotency-Key;
                                 the counsel (HQ-LGL) is woken with a work item
    GET  /legal/cases/{ref}      the case with its timeline and every email
    POST /legal/cases/{ref}/close  {note_fa?} · 409 while an email waits for its seal
Agent tools (the counsel only: OPA hq.internal, legal_voice.rego):
    POST /internal/v1/legal/cases              case.open   (A1)
    POST /internal/v1/legal/cases/{ref}/notes  case.note   (A1)
    POST /internal/v1/legal/cases/{ref}/emails email.draft (A1 -> an email_send card)
    GET  /internal/v1/legal/cases/{ref}/mail   mail.read   (A0, its own cases only)

The counsel is a holding role; a case belongs to the company it is about, so
its routes run over every company once the policy allowed the call. No route
here ever sends an email: the owner's seal on the card does, once.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import legal as L
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Actor, Model, Page

router = APIRouter(tags=["legal"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422)
CO = r"^[A-Z][A-Z0-9]{1,9}$"
CASE = r"^LC-[0-9]{4,}$"
Kind = Literal[
    "platform_restriction", "account_appeal", "takedown", "partner_dispute", "policy_review",
    "contract_review", "compliance", "other",
]  # fmt: skip
Status = Literal["open", "waiting_reply", "waiting_owner", "resolved", "closed"]


# ------------------------------------------------------------------ models --
class Counterpart(Model):
    name: str = Field(default="", max_length=200)
    channel: Literal["email", "form", "portal", "other"] = "other"
    address: str | None = Field(default=None, max_length=500)


class Deadline(Model):
    at: datetime
    what_fa: str = Field(min_length=1, max_length=500)


class TimelineEntry(BaseModel):
    at: datetime
    kind: Literal["note", "email_out", "email_in", "form", "decision"]
    ref: str | None
    summary_fa: str


class EmailAttachment(BaseModel):
    file_id: str
    name: str
    mime: str | None = None
    sha256: str


class Email(BaseModel):
    """EmailDraft plus its life (contract §22.7). ⟨1.6⟩ `state` also has
    `queued` (sealed, waiting to leave), `sending` and `failed`."""

    id: UUID
    case: str
    direction: Literal["out", "in"]
    state: Literal[
        "waiting_seal", "queued", "sending", "sent", "failed", "received", "superseded", "rejected"
    ]
    from_: str = Field(alias="from")
    to: list[str]
    cc: list[str]
    subject: str
    body_md: str
    attachments: list[EmailAttachment]
    lang: Literal["fa", "en"]
    digest: str | None
    decision_ref: str | None
    message_id: str
    at: datetime
    error: str | None = None

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class LegalCase(BaseModel):
    id: UUID
    ref: str
    company: str
    title_fa: str
    kind: Kind
    brief_md: str
    counterpart: dict[str, Any]
    status: Status
    counsel: str
    timeline: list[TimelineEntry]
    deadlines: list[dict[str, Any]]
    opened_by: Actor
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    version: int
    emails: list[Email] | None = None


class CaseIn(Model):
    company: str = Field(pattern=CO)
    title_fa: str = Field(min_length=1, max_length=300)
    kind: Kind
    brief_md: str = Field(default="", max_length=20000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=20)
    counterpart: Counterpart | None = None


class CloseIn(Model):
    note_fa: str | None = Field(default=None, max_length=2000)


class AgentCaseIn(Model):
    company: str = Field(pattern=CO)
    title_fa: str = Field(min_length=1, max_length=300)
    kind: Kind
    brief_md: str = Field(default="", max_length=20000)
    counterpart: Counterpart | None = None


class NoteIn(Model):
    kind: Literal["note", "form", "decision"]
    summary_fa: str = Field(min_length=1, max_length=4000)
    ref_link: str | None = Field(default=None, max_length=80)
    deadline: Deadline | None = None
    status: Literal["open", "waiting_reply", "resolved"] | None = None


class DraftIn(Model):
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=998)
    body_md: str = Field(min_length=1, max_length=100000)
    lang: Literal["fa", "en"]
    file_ids: list[UUID] = Field(default_factory=list, max_length=10)


class Drafted(BaseModel):
    case: str
    decision: str
    digest: str
    email: str
    from_: str = Field(alias="from")
    state: Literal["waiting_seal"]

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class MailOut(BaseModel):
    case: str
    status: Status
    emails: list[Email]


def _case(r: dict[str, Any]) -> LegalCase:
    return LegalCase.model_validate(r)


# ------------------------------------------------------------------- owner --
@router.get("/legal/cases", response_model=Page[LegalCase], responses=E)
async def list_cases(
    company: str | None = Query(default=None, pattern=CO),
    status: Status | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[LegalCase]:
    """The cases of every company (or one), newest first."""
    before_t, before_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            L.CASE_SQL
            + """ WHERE (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:st AS text) IS NULL OR k.status = :st)
                    AND (CAST(:bt AS timestamptz) IS NULL
                         OR (k.created_at, k.id) < (CAST(:bt AS timestamptz), CAST(:bid AS uuid)))
                  ORDER BY k.created_at DESC, k.id DESC LIMIT :lim""",
            co=company,
            st=status,
            bt=before_t,
            bid=before_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        return Page(items=[_case(await L.render_case(tx, r)) for r in items], next_cursor=nxt)


@router.post("/legal/cases", response_model=LegalCase, status_code=201, responses=E)
async def open_case(body: CaseIn, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """The owner opens a case: the counsel is woken with a work item
    (nothing runs while the holding is locked). Requires `Idempotency-Key`."""
    company = await ctx.hub.companies.find(body.company)
    if company is None:
        raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if body.file_ids:
            n = await tx.scalar(
                """SELECT count(*) FROM files.files WHERE id = ANY(:ids) AND variant = 'original'""",
                ids=body.file_ids,
            )
            if int(n) != len(set(body.file_ids)):
                raise ApiError(422, "validation_failed", fields={"file_ids": "unknown file"})
        case = await L.open_case(
            tx,
            ctx.who,
            company=company,
            title_fa=body.title_fa,
            kind=body.kind,
            brief_md=body.brief_md,
            counterpart=body.counterpart.model_dump(mode="json") if body.counterpart else None,
            file_ids=body.file_ids,
        )
        await L.wake(
            tx,
            case,
            f"{case['ref']}: {body.title_fa}",
            f"The owner opened case {case['ref']} ({body.kind}) for {body.company}.\n\n{body.brief_md}"
            + (f"\n\nFiles: {', '.join(str(f) for f in body.file_ids)}" if body.file_ids else ""),
            who=ctx.who,
            priority="P2",
        )
        result = _case(await L.render_case(tx, await L.load(tx, case["ref"]), full=True))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.get("/legal/cases/{ref}", response_model=LegalCase, responses=E)
async def get_case(ref: str, ctx: Ctx = Depends(owner_ctx)) -> LegalCase:
    """One case with its full timeline and every email (in and out)."""
    async with ctx.tx() as tx:
        return _case(await L.render_case(tx, await L.load(tx, ref), full=True))


@router.post("/legal/cases/{ref}/close", response_model=LegalCase, responses=E)
async def close_case(
    ref: str, body: CloseIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner closes a case; 409 while one of its emails waits for the seal."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        case = await L.load(tx, ref, lock=True)
        await L.close(tx, ctx.who, case, body.note_fa)
        result = _case(await L.render_case(tx, await L.load(tx, ref), full=True))
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


# --------------------------------------------------------- the counsel's --
async def _counsel(ctx: Ctx, op: str, **target: Any) -> None:
    if ctx.who.kind != "agent":
        raise ApiError(403, "policy_denied", "the legal counsel only")
    await allow(ctx, op, {"company": ctx.who.company, "charter": ctx.who.charter, **target})


def _wide(ctx: Ctx) -> Any:
    """A transaction over every company: a case is its company's, and the
    counsel (a holding role, allowed by the policy first) works on all."""

    class _Tx:
        async def __aenter__(self) -> Any:
            self._cm = ctx.hub.db.tx(await ctx.hub.companies.ids())
            return await self._cm.__aenter__()

        async def __aexit__(self, *exc: Any) -> Any:
            return await self._cm.__aexit__(*exc)

    return _Tx()


@internal_router.post("/legal/cases", response_model=LegalCase, status_code=201, responses=E)
async def counsel_open(
    body: AgentCaseIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """case.open (A1): a new case the calling counsel works. Requires `Idempotency-Key`."""
    await _counsel(ctx, "legal.case_open", case_company=body.company)
    company = await ctx.hub.companies.find(body.company)
    if company is None:
        raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
    async with _wide(ctx) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        me = await tx.one(
            "SELECT id, code, company_id FROM core.employees WHERE id = :e", e=ctx.who.employee_id
        )
        case = await L.open_case(
            tx,
            ctx.who,
            company=company,
            title_fa=body.title_fa,
            kind=body.kind,
            brief_md=body.brief_md,
            counterpart=body.counterpart.model_dump(mode="json") if body.counterpart else None,
            counsel_row=me,
        )
        result = _case(await L.render_case(tx, case))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@internal_router.post("/legal/cases/{ref}/notes", response_model=LegalCase, responses=E)
async def counsel_note(
    ref: str, body: NoteIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """case.note (A1): a note, a form's outcome or a decision on the
    timeline of one of the counsel's own cases; `deadline` adds one."""
    await _counsel(ctx, "legal.case_note")
    async with _wide(ctx) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        case = await L.own_case(tx, ctx.who, ref, lock=True)
        out = await L.note(
            tx,
            ctx.who,
            case,
            kind=body.kind,
            summary_fa=body.summary_fa,
            ref_link=body.ref_link,
            deadline=body.deadline.model_dump(mode="json") if body.deadline else None,
            status=body.status,
        )
        result = _case(await L.render_case(tx, out))
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


@internal_router.post(
    "/legal/cases/{ref}/emails", response_model=Drafted, status_code=201, responses=E
)
async def counsel_draft(
    ref: str, body: DraftIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """email.draft (A1): the exact message becomes an `email_send` card for
    the owner's seal; a draft still waiting on this case is superseded (its
    card withdrawn). Nothing is sent here. Requires `Idempotency-Key`."""
    await _counsel(ctx, "legal.email_draft")
    async with _wide(ctx) as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        case = await L.own_case(tx, ctx.who, ref, lock=True)
        out = await L.draft(
            tx,
            ctx.hub,
            ctx.who,
            case,
            to=body.to,
            cc=body.cc,
            subject=body.subject,
            body_md=body.body_md,
            lang=body.lang,
            file_ids=body.file_ids,
        )
        result = Drafted.model_validate(out)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    await workflows_client.decision_created(ctx.hub, out["decision"])
    return result


@internal_router.get("/legal/cases/{ref}/mail", response_model=MailOut, responses=E)
async def counsel_mail(ref: str, ctx: Ctx = Depends(internal_ctx)) -> MailOut:
    """mail.read (A0): the masked emails of one of the counsel's own cases."""
    await _counsel(ctx, "legal.mail_read")
    async with _wide(ctx) as tx:
        await tx.exec("SET TRANSACTION READ ONLY")
        return MailOut.model_validate(await L.mail_read(tx, ctx.who, ref))
