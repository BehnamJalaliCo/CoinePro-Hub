"""⟨1.15⟩ Prompt 24 (contract §33.1, §33.4, §33.5): usage in the advisor's words, the small
CRM of each company, affiliate follow-up.

    GET   /usage/reports                          ?period&limit&cursor, newest first
    POST  /usage/reports                          {period}: one now (a model call; the same
                                                  period made in the last minute is returned)
    GET   /companies/{code}/leads                 ?stage&source&q&limit&cursor
    POST  /companies/{code}/leads                 a lead by hand (a pseudonym and a display name only)
    GET   /leads/{ref}  PATCH /leads/{ref}        stage, value, next step, assignee (If-Match)
    POST  /leads/{ref}/draft                      the follow-up text; never sent
    GET   /companies/{code}/pipeline              counts and value by stage, win rate, median days
    GET   /revenue/affiliate-gaps                 ?company&state: due against received
    POST  /revenue/affiliate-receipts             what arrived for an account's month

Owner only here (OPA `hq.money`, which also lets a company's CEO, FIN and SALES managers
read in their company when a tool asks). The model is called only by `POST /usage/reports`
and `POST /leads/{ref}/draft`; nothing here sends a message to anyone.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import affiliate_gaps as AG
from hq_api.domain import leads as L
from hq_api.domain import usage as U
from hq_api.errors import ApiError, responses
from hq_api.http import check_version, if_match
from hq_api.schemas import Model, Page
from hq_common.redact import scrub

router = APIRouter(tags=["sales"])
E = responses(401, 403, 404, 409, 422, 428)
COMPANY = r"^[A-Z][A-Z0-9]{1,9}$"
REF = r"^LD-[0-9]{6,}$"


async def _policy(ctx: Ctx, op: str, target: dict[str, Any] | None = None) -> None:
    await ctx.hub.policy.require(
        "money", {"principal": ctx.who.opa(), "op": op, "target": target or {}}
    )


async def _company(ctx: Ctx, code: str) -> Any:
    co = await ctx.hub.companies.by_code(code)
    if co.kind == "holding":
        raise ApiError(404, "not_found", message_fa="این شرکت پیدا نشد.")
    return co


# -------------------------------------------------------------------- usage --
class UsageReportIn(Model):
    period: Literal["day", "week"]


@router.get("/usage/reports", response_model=Page[U.UsageReport], responses=E)
async def list_usage_reports(
    period: Literal["day", "week"] | None = None,
    limit: int = Query(default=20, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[U.UsageReport]:
    """⟨1.15⟩ §33.1 the holding's usage reports, newest first: the pack (numbers by code from the
    Token Treasury, the voice meter, the lines and the ads) and the advisor's words."""
    await _policy(ctx, "usage.read")
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT * FROM sales.usage_reports
               WHERE (CAST(:p AS text) IS NULL OR period = :p)
                 AND (CAST(:after_t AS timestamptz) IS NULL
                      OR (at, id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
               ORDER BY at DESC, id DESC LIMIT :lim""",
            p=period,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("at", "id"))
    return Page(items=[U.render(r) for r in items], next_cursor=nxt)


@router.post("/usage/reports", response_model=U.UsageReport, status_code=201, responses=E)
async def make_usage_report(body: UsageReportIn, ctx: Ctx = Depends(owner_ctx)) -> U.UsageReport:
    """⟨1.15⟩ §33.1 the owner asks for a report now: the last complete day or week, the pack by
    code and ONE model call for the words (task class `usage_report`); when the model gives
    nothing usable the words are written by code (`words: "code"`). The same period asked for
    twice within a minute returns the first report."""
    await _policy(ctx, "usage.make")
    async with ctx.tx() as tx:
        recent = await tx.first(
            """SELECT * FROM sales.usage_reports WHERE period = :p AND made_by = 'owner'
                 AND at > :since ORDER BY at DESC LIMIT 1""",
            p=body.period,
            since=datetime.now(UTC) - timedelta(seconds=60),
        )
    if recent is not None:
        return U.render(recent)
    row = await U.make(ctx.hub, body.period, made_by="owner", who=ctx.who)
    return U.render(row)


# -------------------------------------------------------------------- leads --
@router.get("/companies/{code}/leads", response_model=Page[L.Lead], responses=E)
async def list_leads(
    code: str,
    stage: str | None = Query(default=None, pattern=r"^[a-z][a-z0-9_]{1,30}$"),
    source: Literal["support", "telegram", "site", "payment", "referral", "manual"] | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[L.Lead]:
    """⟨1.15⟩ §33.4 a company's leads, newest first. A lead is a pseudonym and a display name; the
    contact details stay in the company's own systems."""
    co = await _company(ctx, code)
    await _policy(ctx, "lead.read", {"company": co.code})
    after_t, after_id = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            L.LEAD_SQL
            + """ WHERE l.company_id = :co
                   AND (CAST(:stage AS text) IS NULL OR l.stage = :stage)
                   AND (CAST(:source AS text) IS NULL OR l.source = :source)
                   AND (CAST(:q AS text) IS NULL OR l.ref = :q
                        OR core.fa_normalize(COALESCE(l.name_fa, '')) LIKE
                           '%' || core.like_escape(core.fa_normalize(:q)) || '%')
                   AND (CAST(:after_t AS timestamptz) IS NULL
                        OR (l.created_at, l.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
                 ORDER BY l.created_at DESC, l.id DESC LIMIT :lim""",
            co=co.id,
            stage=stage,
            source=source,
            q=q,
            after_t=after_t,
            after_id=after_id,
            lim=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("created_at", "id"))
        out = [L.render(r, await L.events_of(tx, r["id"], 10)) for r in items]
    return Page(items=out, next_cursor=nxt)


@router.post("/companies/{code}/leads", response_model=L.Lead, status_code=201, responses=E)
async def create_lead(
    code: str, body: L.LeadIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.15⟩ §33.4 a lead by hand (or from outside: `site`, `referral`). `contact` is a pseudonym
    (a phone number or an address is refused); without one the hub makes one. A second lead with
    the same pseudonym is the first one. Honours `Idempotency-Key`."""
    co = await _company(ctx, code)
    await _policy(ctx, "lead.write", {"company": co.code})
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        a = await L.check_assignee(tx, co.id, body.assignee.model_dump() if body.assignee else None)
        row, _ = await L.create(
            tx,
            ctx.who,
            {"id": co.id, "code": co.code},
            source=body.source,
            contact=body.contact,
            name_fa=body.name_fa,
            value_usdt=body.value_usdt,
            next_at=body.next_at,
            next_fa=body.next_fa,
            assignee=a,
            note_fa=body.note_fa or "",
        )
        out = L.render(row, await L.events_of(tx, row["id"]))
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.get("/leads/{ref}", response_model=L.Lead, responses=E)
async def get_lead(ref: str, ctx: Ctx = Depends(owner_ctx)) -> L.Lead:
    """⟨1.15⟩ §33.4 one lead with its trail (stage moves, reminders, drafts, payments)."""
    async with ctx.tx() as tx:
        row = await L.load(tx, _ref(ref))
        await _policy(ctx, "lead.read", {"company": row["company"]})
        return L.render(row, await L.events_of(tx, row["id"], 200))


def _ref(ref: str) -> str:
    if not re.match(REF, ref):
        raise ApiError(404, "not_found", message_fa="این سرنخ پیدا نشد.")
    return ref


@router.patch("/leads/{ref}", response_model=L.Lead, responses=E)
async def patch_lead(
    ref: str, body: L.LeadPatch, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> L.Lead:
    """⟨1.15⟩ §33.4 change a lead: its stage (a stage of its company; a lost one may carry
    `lost_reason_fa`), value, display name, next step and time (the reminder is made at
    `next_at`), assignee, or a note. `If-Match` is the lead's version."""
    expected = if_match(request)
    sent = body.model_fields_set
    async with ctx.tx() as tx:
        row = await L.load(tx, _ref(ref), lock=True)
        await _policy(ctx, "lead.write", {"company": row["company"]})
        check_version(row["version"], expected)
        changed: list[str] = []
        if "stage" in sent and body.stage is not None:
            row = await L.move(tx, row, body.stage, lost_reason_fa=body.lost_reason_fa)
            changed.append("stage")
        sets: dict[str, Any] = {}
        if "name_fa" in sent and body.name_fa is not None:
            sets["name_fa"] = " ".join(scrub(body.name_fa).split())[:200]
        if "value_usdt" in sent:
            sets["value_usdt"] = body.value_usdt
        if "next_at" in sent:
            sets["next_at"] = body.next_at
            sets["reminded_for"] = None
        if "next_fa" in sent:
            sets["next_fa"] = " ".join(scrub(body.next_fa).split())[:300] if body.next_fa else None
        if "lost_reason_fa" in sent and "stage" not in sent:
            sets["lost_reason_fa"] = (
                " ".join(scrub(body.lost_reason_fa).split())[:300] if body.lost_reason_fa else None
            )
        if "assignee" in sent:
            a = await L.check_assignee(
                tx, row["company_id"], body.assignee.model_dump() if body.assignee else None
            )
            sets["assignee_kind"], sets["assignee_code"] = a if a else (None, None)
            changed.append("assignee")
        if sets:
            cols = ", ".join(f"{k} = :{k}" for k in sets)
            await tx.exec(
                f"UPDATE sales.leads SET {cols} WHERE id = :id",  # noqa: S608 - fixed column names
                id=row["id"],
                **sets,
            )
            changed += [
                k for k in sets if k not in ("reminded_for", "assignee_kind", "assignee_code")
            ]
        row = await L.load(tx, ref)
        if body.note_fa:
            await L.add_event(tx, row, "note", " ".join(scrub(body.note_fa).split()))
            changed.append("note")
        if changed:
            await ctx.audit(
                tx,
                company_id=row["company_id"],
                action="lead.update",
                action_class="A1",
                target_kind="lead",
                target_ref=ref,
                summary=", ".join(dict.fromkeys(changed)),
            )
            await L._emit(tx, row, "updated")
        return L.render(row, await L.events_of(tx, row["id"], 200))


@router.post("/leads/{ref}/draft", response_model=L.LeadDraft, responses=E)
async def draft_lead(ref: str, ctx: Ctx = Depends(owner_ctx)) -> L.LeadDraft:
    """⟨1.15⟩ §33.4 a follow-up text for this lead in the company's voice: ONE mid-model call (task
    class `sales_followup`), checked by the outbound guard (§19.6). The draft is returned and
    never sent; sending goes through the guard and the approval rules as they are."""
    async with ctx.tx() as tx:
        row = await L.load(tx, _ref(ref))
    await _policy(ctx, "lead.draft", {"company": row["company"]})
    return await L.draft(ctx.hub, ref)


@router.get("/companies/{code}/pipeline", response_model=L.LeadPipeline, responses=E)
async def get_pipeline(code: str, ctx: Ctx = Depends(owner_ctx)) -> L.LeadPipeline:
    """⟨1.15⟩ §33.4 the company's pipeline: leads and their value by stage (stages are the
    company's own data), the win rate (won / (won + lost)) and the median days in each open stage."""
    co = await _company(ctx, code)
    await _policy(ctx, "lead.read", {"company": co.code})
    async with ctx.tx() as tx:
        return await L.pipeline(tx, {"id": co.id, "code": co.code})


# ------------------------------------------------------------ affiliate gaps --
class SalesReceiptIn(Model):
    account_id: UUID
    month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    received_usdt: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    note_fa: str | None = Field(default=None, max_length=300)


@router.get("/revenue/affiliate-gaps", response_model=list[AG.SalesAffiliateGap], responses=E)
async def affiliate_gaps(
    company: str | None = Query(default=None, pattern=COMPANY),
    state: Literal["waiting", "ok", "open", "closed"] | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> list[AG.SalesAffiliateGap]:
    """⟨1.15⟩ §33.5 the commission due against the commission received, per account and month
    (the last twelve): `waiting` until the exchange's settlement window passes, `ok` within 5%,
    `open` above it (a follow-up for the FIN manager with a drafted message), `closed` once paid."""
    co = await ctx.hub.companies.by_code(company) if company else None
    await _policy(ctx, "affiliate.read", {"company": co.code if co else None})
    async with ctx.tx() as tx:
        rows = await AG.listing(tx, co.id if co else None)
    return [r for r in rows if state is None or r.state == state]


@router.post(
    "/revenue/affiliate-receipts",
    response_model=AG.SalesAffiliateReceipt,
    status_code=201,
    responses=E,
)
async def affiliate_receipt(
    body: SalesReceiptIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.15⟩ §33.5 say what the exchange paid for an account's month (it pays outside the hub);
    a gap that this brings under 5% closes. Receipts add up and are never changed, so this
    requires `Idempotency-Key` (a retried request never books the money twice)."""
    await _policy(ctx, "affiliate.receive")
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await AG.receive(
            tx,
            ctx.who,
            account_id=body.account_id,
            month=AG.parse_month(body.month),
            received_usdt=body.received_usdt,
            note_fa=body.note_fa,
        )
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out
