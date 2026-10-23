"""The meeting room (prompt 11 §1, contract §20.1, §20.12).

Owner (/api/v1):
  GET   /meetings                      ?type&company&state&from&to (Page)
  POST  /meetings                      an ad-hoc meeting {type, company?, starts_at, items?} · Idempotency-Key
  GET · PUT /meetings/settings         the MeetingType list; PUT 🔏 meetings.settings = sha256 of the body
  GET   /meetings/{ref}                the agenda, the budget estimate, trimmed_fa, the drafts
  PATCH /meetings/{ref}                reorder or skip items, LOWER the budget, presence (If-Match)
  GET   /meetings/{ref}/turns          ?item&after (whispers: the owner's only)
  POST  /meetings/{ref}/speak          the owner's word (jumps the queue) · Idempotency-Key (required)
  POST  /meetings/{ref}/control        next_round | skip_item | end | raise_budget (only the owner raises)
Agents (/internal/v1, only inside their own pending turn):
  POST /meetings/{ref}/statement · /challenge · /whisper · /minutes;  POST /meetings/items
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import Field

from hq_api import http, idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import meeting_flow as F
from hq_api.domain import meetings as MT
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import CODE, Model, Page
from hq_api.security import stepup

router = APIRouter(tags=["meetings"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428)
REF = r"^MT-[0-9]{4,}$"
RefP = Path(pattern=REF)


class MeetingSourceIn(Model):
    kind: str = Field(pattern=r"^[a-z][a-z_]{1,20}$")
    ref: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class MeetingOwnerItemIn(Model):
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=8000)
    sources: list[MeetingSourceIn] = Field(default_factory=list, max_length=20)
    companies: list[str] = Field(default_factory=list, max_length=50)


class MeetingCreateIn(Model):
    type: Literal["board", "company", "strategy"]
    company: str | None = Field(default=None, pattern=CODE)
    starts_at: datetime
    items: list[MeetingOwnerItemIn] = Field(default_factory=list, max_length=MT.MAX_ITEMS)


class MeetingItemOrder(Model):
    id: UUID
    n: int = Field(ge=1, le=50)
    skip: bool = False


class MeetingPatchIn(Model):
    items: list[MeetingItemOrder] | None = Field(default=None, max_length=50)
    budget_cap: int | None = Field(default=None, ge=0)
    owner_presence: Literal["live", "summary", "audio"] | None = None


class MeetingSpeakIn(Model):
    text: str | None = Field(default=None, min_length=1, max_length=8000)
    file_id: UUID | None = None


class MeetingControlIn(Model):
    action: Literal["next_round", "skip_item", "end", "raise_budget"]
    tokens: int | None = Field(default=None, ge=1, le=10_000_000)


# ------------------------------------------------------------------ owner --
@router.get("/meetings", response_model=Page[MT.Meeting], responses=E)
async def list_meetings(
    type: Literal["board", "company", "standup", "war_room", "postmortem", "strategy"]
    | None = None,
    company: str | None = Query(default=None, pattern=CODE),
    state: Literal["scheduled", "prep", "live", "closing", "ended", "cancelled"] | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[MT.Meeting]:
    """Newest start first; a standup that changed nothing is not listed."""
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            MT.MEETING_SQL
            + """ WHERE (CAST(:type AS text) IS NULL OR m.type = :type)
                    AND (CAST(:co AS text) IS NULL OR c.code = :co)
                    AND (CAST(:state AS text) IS NULL OR m.state = :state)
                    AND (CAST(:from_ AS timestamptz) IS NULL OR m.starts_at >= :from_)
                    AND (CAST(:to AS timestamptz) IS NULL OR m.starts_at < :to)
                    AND NOT (m.type = 'standup' AND m.end_reason = 'no_change')
                    AND (CAST(:after_t AS timestamptz) IS NULL
                         OR (m.starts_at, m.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                  ORDER BY m.starts_at DESC, m.id DESC LIMIT :lim""",
            type=type,
            co=company,
            state=state,
            from_=from_,
            to=to,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("starts_at", "id"))
        return Page(items=[await MT.render(tx, m) for m in items], next_cursor=nxt)


@router.post("/meetings", response_model=MT.Meeting, status_code=201, responses=E)
async def create_meeting(
    body: MeetingCreateIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner's ad-hoc meeting: the same speaker rule, budget and daily share
    as a scheduled one (the share and the daily cap decide `written` at the
    start). A `company` meeting names its company; board and strategy are the
    holding's. Requires `Idempotency-Key`."""
    if body.type == "company" and not body.company:
        raise ApiError(
            422, "validation_failed", fields={"company": "a company meeting names its company"}
        )
    if body.type == "company":
        co = await ctx.hub.companies.find(body.company or "")
        if co is None or co.kind == "holding":
            raise ApiError(422, "validation_failed", fields={"company": "an operating company"})
    else:
        co = await ctx.hub.companies.holding()
    starts_at = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=UTC)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        t = await MT.type_row(tx, body.type)
        m = await MT.create(
            tx, t=t, company={"id": co.id, "code": co.code}, starts_at=starts_at, origin="owner",
            by_kind="owner", by_code=ctx.who.code,
        )  # fmt: skip
        assert m is not None
        # The owner's own meeting gets its agenda at once (the owner's items first).
        m = await MT.prepare(tx, m, owner_items=[i.model_dump() for i in body.items])
        await ctx.audit(
            tx, company_id=co.id, action="meeting.create", action_class="A1", target_kind="meeting",
            target_ref=m["ref"], summary=f"{body.type} at {body.starts_at.isoformat()}",
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=co.id, kind="order", action="meeting.create", target_kind="meeting", target_ref=m["ref"],
        )  # fmt: skip
        out = await MT.render(tx, m)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/meetings/settings", response_model=list[MT.MeetingType], responses=E)
async def meeting_settings(ctx: Ctx = Depends(owner_ctx)) -> list[MT.MeetingType]:
    """The meeting types (MeetingType) the owner edits, each with its version."""
    async with ctx.tx() as tx:
        return [MT.render_type(t) for t in await MT.types(tx)]


@router.put("/meetings/settings", response_model=list[MT.MeetingType], responses=E)
async def update_meeting_settings(
    body: MT.MeetingSettingsIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> list[MT.MeetingType]:
    """🔏 `meetings.settings`, target = the SHA-256 of the exact body. Each row
    carries its own `version` (409 version_conflict when it moved)."""
    target = await stepup.body_target(request)
    async with ctx.tx() as tx:
        step_up_id = await stepup.consume(tx, request, ctx.who, "meetings.settings", target)
        rows = await MT.update_types(tx, body, ctx.who.code)
        hid = await MT.holding_id(tx)
        await ctx.audit(
            tx, company_id=hid, action="meetings.settings", action_class="A2", target_kind="meetings",
            target_ref="settings", summary=", ".join(t.key for t in body.types), step_up=step_up_id is not None,
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=hid, kind="setting", action="meetings.settings", target_kind="meetings",
            target_ref="settings", data={"types": [t.key for t in body.types]},
        )  # fmt: skip
        return [MT.render_type(t) for t in rows]


@router.get("/meetings/{ref}", response_model=MT.Meeting, responses=E)
async def get_meeting(ref: str = RefP, ctx: Ctx = Depends(owner_ctx)) -> MT.Meeting:
    """Before `live` this is what the owner sees and edits: the agenda, the
    budget estimate and what the code trimmed."""
    async with ctx.tx() as tx:
        return await MT.render(tx, await MT.load(tx, ref))


@router.patch("/meetings/{ref}", response_model=MT.Meeting, responses=E)
async def patch_meeting(
    body: MeetingPatchIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(owner_ctx)
) -> MT.Meeting:
    """Before the start: reorder or skip items, LOWER the budget (raising is
    POST …/control raise_budget, the owner's only), the owner's presence. If-Match."""
    expected = http.if_match(request)
    async with ctx.tx() as tx:
        m = await MT.load(tx, ref, lock=True)
        http.check_version(m["version"], expected)
        if m["state"] not in ("scheduled", "prep"):
            raise ApiError(
                409, "validation_failed", f"{ref} is {m['state']}: edit it before it starts"
            )
        if body.budget_cap is not None:
            if m["budget_cap"] is None or body.budget_cap > m["budget_cap"]:
                raise ApiError(
                    422, "validation_failed",
                    fields={"budget_cap": "PATCH only lowers it; raise it with control raise_budget"},
                )  # fmt: skip
            await tx.exec(
                "UPDATE meetings.meetings SET budget_cap = :b WHERE id = :id",
                b=body.budget_cap,
                id=m["id"],
            )
        if body.owner_presence:
            await tx.exec(
                "UPDATE meetings.meetings SET owner_presence = :p WHERE id = :id",
                p=body.owner_presence,
                id=m["id"],
            )
        if body.items:
            known = {it["id"] for it in await MT.items_of(tx, m["id"])}
            for it in body.items:
                if it.id not in known:
                    raise ApiError(
                        422,
                        "validation_failed",
                        fields={"items": f"{it.id} is not an item of {ref}"},
                    )
                await tx.exec(
                    """UPDATE meetings.items SET n = :n, state = CASE WHEN :skip THEN 'skipped'
                           WHEN state = 'skipped' THEN 'waiting' ELSE state END WHERE id = :id""",
                    n=it.n,
                    skip=it.skip,
                    id=it.id,
                )
        m = await MT.load(tx, ref, lock=True)
        if body.owner_presence:
            s = dict(m["settings"] or {})
            s["whispers_wanted"] = body.owner_presence == "live"
            await tx.exec("UPDATE meetings.meetings SET settings = CAST(:s AS jsonb) WHERE id = :id",
                          s=json.dumps(s), id=m["id"])  # fmt: skip
            m = await MT.load(tx, ref, lock=True)
        m = await MT.refresh_budget(tx, m)
        await ctx.audit(
            tx, company_id=m["company_id"], action="meeting.edit", action_class="A1", target_kind="meeting",
            target_ref=ref, summary=", ".join(k for k in body.model_fields_set),
        )  # fmt: skip
        return await MT.render(tx, m)


@router.get("/meetings/{ref}/turns", response_model=MT.MeetingTurnsPage, responses=E)
async def meeting_turns(
    ref: str = RefP,
    item: UUID | None = None,
    after: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> MT.MeetingTurnsPage:
    """The turns in order, with their claims; the advisor's whispers too (the
    owner's only: no agent route returns them)."""
    async with ctx.tx() as tx:
        m = await MT.load(tx, ref)
        return await MT.render_turns(tx, m, item=item, after=after, limit=limit, owner=True)


@router.post("/meetings/{ref}/speak", response_model=MT.MeetingTurn, status_code=201, responses=E)
async def owner_speak(
    body: MeetingSpeakIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The owner takes the floor (text, or a voice note already transcribed by
    POST /transcribe): it jumps the queue. 409 meeting_not_live unless live.
    Requires `Idempotency-Key` (a repeat makes one turn)."""
    if not body.text and not body.file_id:
        raise ApiError(422, "validation_failed", fields={"text": "text or a voice file"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        m = await MT.load(tx, ref, lock=True)
        text = body.text or ""
        if body.file_id:
            transcript = await tx.scalar(
                "SELECT transcript FROM files.processing WHERE file_id = :f AND transcript IS NOT NULL",
                f=body.file_id,
            )
            if not transcript:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={"file_id": "no transcript yet (POST /transcribe)"},
                )
            text = (text + "\n" + str(transcript)).strip()
        turn = await F.owner_speaks(tx, m, text, body.file_id)
        await ctx.audit(
            tx, company_id=m["company_id"], action="meeting.speak", action_class="A1", target_kind="meeting",
            target_ref=ref, summary=f"turn {turn['n']}",
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=m["company_id"], kind="message", action="meeting.speak", target_kind="meeting",
            target_ref=ref, data={"turn": turn["n"]},
        )  # fmt: skip
        out = (
            await MT.render_turns(tx, m, item=None, after=turn["n"] - 1, limit=1, owner=False)
        ).items[0]
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post("/meetings/{ref}/control", response_model=MT.Meeting, responses=E)
async def meeting_control(
    body: MeetingControlIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """next_round, skip_item, end, raise_budget {tokens}: only the owner raises
    a budget, even mid-meeting (every other caller: 403)."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        m = await MT.load(tx, ref, lock=True)
        m = await F.control(tx, m, body.action, body.tokens)
        await ctx.audit(
            tx, company_id=m["company_id"], action=f"meeting.{body.action}", action_class="A1", target_kind="meeting",
            target_ref=ref, summary=f"+{body.tokens}" if body.tokens else "",
        )  # fmt: skip
        await ctx.interaction(
            tx, company_id=m["company_id"], kind="control", action=f"meeting.{body.action}", target_kind="meeting",
            target_ref=ref, data={"tokens": body.tokens},
        )  # fmt: skip
        out = await MT.render(tx, await MT.load(tx, ref))
        if idem:
            await idem.store(tx, 200, out.model_dump(mode="json"))
    return out


# ----------------------------------------------------------------- agents --
class MeetingClaimSource(Model):
    kind: str = Field(pattern=r"^[a-z][a-z_]{1,20}$")
    ref: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class MeetingClaimIn(Model):
    text_fa: str = Field(min_length=1, max_length=1000)
    source: MeetingClaimSource | None = None


class MeetingStanceIn(Model):
    draft: UUID | None = None
    vote: Literal["support", "oppose", "abstain"]
    reason_fa: str = Field(min_length=1, max_length=500)


class MeetingStatementIn(Model):
    item: int = Field(ge=1, le=50)
    statement_md: str = Field(min_length=1, max_length=8000)
    claims: list[MeetingClaimIn] = Field(default_factory=list, max_length=20)
    draft_md: str | None = Field(default=None, max_length=8000)
    stance: MeetingStanceIn | None = None


class MeetingChallengeIn(Model):
    item: int = Field(ge=1, le=50)
    claim: UUID | None = None
    statement_md: str = Field(min_length=1, max_length=8000)
    claims: list[MeetingClaimIn] = Field(default_factory=list, max_length=20)


class MeetingWhisperIn(Model):
    item: int = Field(ge=1, le=50)
    text_md: str = Field(min_length=1, max_length=4000)
    sources: list[MeetingClaimSource] = Field(default_factory=list, max_length=10)


class MeetingMinutesIn(Model):
    summary_md: str = Field(min_length=1, max_length=4000)


class MeetingItemRequestIn(Model):
    type: Literal["board", "company", "strategy", "postmortem"]
    company: str = Field(pattern=CODE)
    title_fa: str = Field(min_length=1, max_length=300)
    brief_md: str = Field(default="", max_length=8000)
    sources: list[MeetingClaimSource] = Field(default_factory=list, max_length=10)


def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


async def _read_scope(ctx: Ctx) -> list[Any]:
    """The speaker's own read scope (a holding-scope role reads every company)."""
    return await ctx.hub.companies.ids() if ctx.who.scope == "holding" else [ctx.who.company_id]


async def _turn(
    ctx: Ctx,
    request: Request,
    ref: str,
    op: str,
    kind: str,
    item: int,
    claims: list[MeetingClaimIn],
    **kw: Any,
) -> Any:
    _agent(ctx)
    await allow(ctx, op, {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.hub.db.tx(await _read_scope(ctx)) as rtx:
        await rtx.exec("SET TRANSACTION READ ONLY")
        checked = await F.check_claims(rtx, [c.model_dump() for c in claims])
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        m = await MT.load(tx, ref, lock=True)
        turn = await F.record_statement(
            tx, m, ctx.who, item_n=item, claims=checked, kind=kind, **kw
        )
        await ctx.audit(
            tx, company_id=ctx.who.company_id, action=op, action_class="A1", target_kind="meeting",  # type: ignore[arg-type]
            target_ref=f"{ref}/T{turn['n']}",
            summary=f"{sum(c['status'] == 'sourced' for c in checked)}/{len(checked)} claims sourced",
        )  # fmt: skip
        statuses = await tx.all(
            "SELECT id, status FROM meetings.claims WHERE turn_id = :t ORDER BY n",
            t=turn["id"],
        )
        draft = await tx.scalar("SELECT id FROM meetings.drafts WHERE turn_id = :t", t=turn["id"])
        out = {
            "ref": f"{ref}/T{turn['n']}",
            "meeting": ref,
            "turn": turn["n"],
            "kind": turn["kind"],
            "claims": [{"id": str(c["id"]), "status": c["status"]} for c in statuses],
            "draft": str(draft) if draft else None,
        }
        if idem:
            await idem.store(tx, 201, out)
    return out


@internal_router.post("/meetings/{ref}/statement", status_code=201, responses=E)
async def agent_statement(
    body: MeetingStatementIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """meeting.statement: the speaker's own pending turn only (a statement, or
    the vote with `stance`); claims checked like citations (§16.3)."""
    return await _turn(
        ctx, request, ref, "meeting.statement", "statement", body.item, body.claims,
        statement_md=body.statement_md, draft_md=body.draft_md,
        stance=body.stance.model_dump(mode="json") if body.stance else None,
    )  # fmt: skip


@internal_router.post("/meetings/{ref}/challenge", status_code=201, responses=E)
async def agent_challenge(
    body: MeetingChallengeIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """meeting.challenge: the devil's advocate (oversight) at the end of round 1."""
    return await _turn(
        ctx, request, ref, "meeting.challenge", "challenge", body.item, body.claims,
        statement_md=body.statement_md, draft_md=None, stance=None, challenge_of=body.claim,
    )  # fmt: skip


@internal_router.post("/meetings/{ref}/whisper", status_code=201, responses=E)
async def agent_whisper(
    body: MeetingWhisperIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """meeting.whisper: the advisor's note, for the owner only."""
    _agent(ctx)
    await allow(ctx, "meeting.whisper", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        m = await MT.load(tx, ref, lock=True)
        w = await F.record_whisper(
            tx,
            m,
            ctx.who,
            item_n=body.item,
            text_md=body.text_md,
            sources=[s.model_dump() for s in body.sources],
        )
        await ctx.audit(
            tx, company_id=ctx.who.company_id, action="meeting.whisper", action_class="A1",  # type: ignore[arg-type]
            target_kind="meeting", target_ref=ref, summary=f"item {body.item}",
        )  # fmt: skip
        out = {
            "ref": f"{ref}/W{body.item}",
            "meeting": ref,
            "item": body.item,
            "kept": w is not None,
        }
        if idem:
            await idem.store(tx, 201, out)
    return out


@internal_router.post("/meetings/{ref}/minutes", responses=E)
async def agent_minutes(
    body: MeetingMinutesIn, request: Request, ref: str = RefP, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """meeting.minutes: the secretary's summary, from sourced claims only."""
    _agent(ctx)
    await allow(ctx, "meeting.minutes", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        m = await MT.load(tx, ref, lock=True)
        await F.record_minutes(tx, m, ctx.who, body.summary_md)
        await ctx.audit(
            tx, company_id=ctx.who.company_id, action="meeting.minutes", action_class="A1",  # type: ignore[arg-type]
            target_kind="meeting", target_ref=ref,
        )  # fmt: skip
        out = {"ref": ref, "meeting": ref}
        if idem:
            await idem.store(tx, 200, out)
    return out


@internal_router.post("/meetings/items", status_code=201, responses=E)
async def agent_meeting_item(
    body: MeetingItemRequestIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """meeting.item: an agenda item for the next meeting of a type (board and
    strategy are the holding's; company and postmortem the company's)."""
    _agent(ctx)
    await allow(ctx, "meeting.item", {"company": body.company, "type": body.type})
    holding = await ctx.hub.companies.holding()
    target = (
        holding
        if body.type in ("board", "strategy")
        else await ctx.hub.companies.find(body.company)
    )
    if target is None:
        raise ApiError(422, "validation_failed", fields={"company": "unknown company"})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        await ctx.ensure_unlocked(tx, ctx.who.company_id)  # type: ignore[arg-type]
        row = await tx.one(
            """INSERT INTO meetings.requests (company_id, type, for_company_id, title_fa, brief_md, sources, by_kind,
                   by_code)
               VALUES (:co, :t, :for_co, :title, :brief, CAST(:src AS jsonb), 'agent', :by) RETURNING ref""",
            co=ctx.who.company_id,
            t=body.type,
            for_co=target.id,
            title=body.title_fa,
            brief=body.brief_md,
            src=json.dumps([s.model_dump() for s in body.sources], ensure_ascii=False),
            by=ctx.who.code,
        )
        await ctx.audit(
            tx, company_id=ctx.who.company_id, action="meeting.item", action_class="A1",  # type: ignore[arg-type]
            target_kind="meeting_request", target_ref=row["ref"], summary=f"{body.type} {target.code}",
        )  # fmt: skip
        out = {"ref": row["ref"], "type": body.type, "company": target.code, "status": "open"}
        if idem:
            await idem.store(tx, 201, out)
    return out
