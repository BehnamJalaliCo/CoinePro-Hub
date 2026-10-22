"""The funnel and referral rescue (prompt 10 §3, contract §19.2): the §3 half
of the growth area (routes/growth.py holds §7's templates, rules and NPS).

Owner (/api/v1):
    GET  /growth/funnel           ?company&period=week|month — a stage without a source is
                                  `connected: false, count: null`; no rate is estimated
    GET  /growth/rescue           ?company&state&cursor (newest first)
    GET  /growth/rescue/{ref}
Agents (/internal/v1):
    POST /growth/funnel/read      funnel.read (A0)
    POST /growth/rescue/{ref}/update   rescue.update (A2, the rescue specialist): a note,
                                  lost or opted_out; `rescued` only after referral.check
                                  said "our invitee". It sends nothing.
    POST /growth/referral-check   referral.check (A0, the support agent, the rescue
                                  specialist): the cached answer, or the connector's grant
                                  for the gateway (invite/user/info, the company's signer)
    POST /growth/referral-check/result   the connector's reduced answer: recorded, the
                                  rescue case opened or closed -> {invitee, meets_minimum}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from hq_api import pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import affiliate as A
from hq_api.domain import egress as G
from hq_api.domain import funnel as F
from hq_api.domain import gate
from hq_api.domain import rescue as R
from hq_api.domain import revenue as V
from hq_api.errors import ApiError, responses
from hq_api.routes.agent_tools import _company, read_tx
from hq_api.routes.internal import allow
from hq_api.routes.revenue import ConnectorEntry, signer_account
from hq_api.schemas import CODE, Model, Page

router = APIRouter(tags=["growth"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 429)
EXCHANGE = r"^[a-z][a-z0-9_-]{1,30}$"
RC = r"^RC-[0-9]{6,}$"
STAGE = Literal["visit", "signup", "referral_verified", "min_balance", "vip_active"]
CASE_STATE = Literal["open", "contacted", "rescued", "lost", "opted_out"]


class FunnelStage(Model):
    key: STAGE
    label_fa: str
    count: int | None = None
    connected: bool
    source: Literal["affiliate", "product_events", "support", "analytics"] | None = None


class Conversion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    from_: STAGE = Field(alias="from")
    to: STAGE
    rate: float | None = None


class Leak(Model):
    stage: STAGE
    note_fa: str
    rate: float
    median_rate: float


class Funnel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    company: str
    period: Literal["week", "month"]
    from_: str = Field(alias="from")
    to: str
    stages: list[FunnelStage]
    conversions: list[Conversion]
    leaks: list[Leak]


class RescueStep(Model):
    at: datetime
    kind: Literal["check", "message", "follow_up", "note"]
    template: str | None = None
    result_fa: str


class RescueCase(Model):
    id: str
    ref: str
    company: str
    source: Literal["support", "product"]
    conversation: str | None = None
    exchange: str
    subject: str
    state: CASE_STATE
    steps: list[RescueStep]
    opened_at: datetime
    rescued_at: datetime | None = None
    closed_at: datetime | None = None


async def _company_row(ctx: Ctx, code: str) -> Any:
    try:
        return await ctx.hub.companies.by_code(code)
    except ApiError as exc:
        raise ApiError(404, "not_found", "no such company") from exc


# ------------------------------------------------------------------ owner --
@router.get("/growth/funnel", response_model=Funnel, responses=E)
async def growth_funnel(
    company: str = Query(pattern=CODE),
    period: Literal["week", "month"] = "week",
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """The company's funnel over the last settled week (7 days) or month (30)."""
    co = await _company_row(ctx, company)
    async with ctx.tx() as tx:
        return Funnel.model_validate(await F.funnel(tx, co.id, co.code, period))


@router.get("/growth/rescue", response_model=Page[RescueCase], responses=E)
async def rescue_list(
    company: str | None = Query(default=None, pattern=CODE),
    state: CASE_STATE | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Rescue cases, newest first. The rescue rate is the client's
    rescued / (rescued + lost) (contract §19.9 ⟨1.5.1⟩)."""
    co = (await _company_row(ctx, company)).id if company else None
    at, after = pagination.time_id(cursor)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT r.*, c.code AS company FROM growth.rescue_cases r
               JOIN core.companies c ON c.id = r.company_id
               WHERE (CAST(:co AS uuid) IS NULL OR r.company_id = CAST(:co AS uuid))
                 AND (CAST(:st AS text) IS NULL OR r.state = :st) AND NOT r.mystery
                 AND (CAST(:at AS timestamptz) IS NULL
                      OR (r.opened_at, r.id) < (CAST(:at AS timestamptz), CAST(:id AS uuid)))
               ORDER BY r.opened_at DESC, r.id DESC LIMIT :n""",
            co=str(co) if co else None,
            st=state,
            at=at,
            id=str(after) if after else None,
            n=limit + 1,
        )
        items, nxt = pagination.page(rows, limit, ("opened_at", "id"))
        out = [RescueCase.model_validate(await R.case_out(tx, r)) for r in items]
    return Page[RescueCase](items=out, next_cursor=nxt)


@router.get("/growth/rescue/{ref}", response_model=RescueCase, responses=E)
async def rescue_get(ref: str, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """One rescue case with its steps (checks, rule messages, notes)."""
    async with ctx.tx() as tx:
        r = await tx.one(
            """SELECT r.*, c.code AS company FROM growth.rescue_cases r
               JOIN core.companies c ON c.id = r.company_id WHERE r.ref = :ref""",
            ref=ref,
        )
        return RescueCase.model_validate(await R.case_out(tx, r))


# ----------------------------------------------------------------- agents --
class FunnelReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=CODE)
    period: Literal["week", "month"] = "week"


@internal_router.post("/growth/funnel/read", responses=E)
async def funnel_read(body: FunnelReadIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """funnel.read (A0): the stages ("not connected" is never zero), the
    conversions, the leaks, and the period's rescue figures."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    co = await _company(ctx, "funnel.read", body.company, charter=ctx.who.charter)
    async with read_tx(ctx) as tx:
        out = await F.funnel(tx, co.id, co.code, body.period)
        start, end = F.period_range(body.period)
        out["rescue"] = await R.rate(tx, co.id, start, end)
    return Funnel.model_validate({k: v for k, v in out.items() if k != "rescue"}).model_dump(
        mode="json", by_alias=True
    ) | {"rescue": out["rescue"]}


class RescueUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: CASE_STATE
    note_fa: str = Field(min_length=1, max_length=1000)


@internal_router.post("/growth/rescue/{ref}/update", responses=E)
async def rescue_update(
    ref: str, body: RescueUpdateIn, ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    """rescue.update (A2): the specialist's note on a case of its company,
    and its closing as lost or opted_out; `rescued` only on a referral.check
    that said "our invitee" since the case opened. Nothing is sent."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    assert ctx.who.company is not None
    await allow(ctx, "rescue.update", {"company": ctx.who.company, "charter": ctx.who.charter})
    async with ctx.tx() as tx:
        case = await tx.first("SELECT * FROM growth.rescue_cases WHERE ref = :r FOR UPDATE", r=ref)
        if case is None:
            raise ApiError(404, "not_found")
        if case["state"] in R.CLOSED:
            raise ApiError(409, "validation_failed", "the case is closed")
        code = ctx.who.code
        if body.state in ("open", "contacted") or body.state == case["state"]:
            await R.add_step(tx, case, "note", body.note_fa, by_kind="agent", by_code=code)
            row = case
        elif body.state == "rescued":
            ours = await tx.scalar(
                """SELECT 1 FROM growth.referral_checks WHERE company_id = :co AND exchange = :ex
                     AND subject = :s AND ok AND invitee AND at >= :since LIMIT 1""",
                co=case["company_id"],
                ex=case["exchange"],
                s=case["subject"],
                since=case["opened_at"],
            )
            if not ours:
                raise ApiError(
                    422, "validation_failed",
                    fields={"state": "rescued only after referral.check says our invitee"},
                )  # fmt: skip
            row = await R.close_case(tx, case, ctx.who.company, "rescued", "invitee", body.note_fa,
                                     by_kind="agent", by_code=code)  # fmt: skip
        else:
            row = await R.close_case(tx, case, ctx.who.company, body.state, f"agent:{body.state}",
                                     body.note_fa, by_kind="agent", by_code=code)  # fmt: skip
        await ctx.audit(
            tx,
            company_id=case["company_id"],
            action="rescue.update",
            action_class="A2",
            target_kind="rescue_case",
            target_ref=ref,
            summary=f"{case['state']} -> {row['state']}",
        )
    return {"ref": ref, "state": row["state"]}


class ReferralCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern=CODE)
    exchange: str = Field(pattern=EXCHANGE)
    uid: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ReferralResultIn(ReferralCheckIn):
    reservation: UUID | None = None
    ok: bool
    invitee: bool | None = None
    meets_minimum: bool | None = None
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,59}$")
    entries: list[ConnectorEntry] = Field(default_factory=list, max_length=20)


async def _checker(ctx: Ctx, body: ReferralCheckIn) -> Any:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")
    await allow(ctx, "referral.check", {"company": body.company, "charter": ctx.who.charter})
    return await _company_row(ctx, body.company)


def _effect(case: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"ref": case["ref"], "state": case["state"]} if case else None


@internal_router.post("/growth/referral-check", responses=E)
async def referral_check(body: ReferralCheckIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """referral.check (A0), step one: a fresh cached answer is the answer
    (and does its rescue effect); else the company's cap (an hour) and the
    gate, then the connector's grant: the signer account for this one call,
    its egress reservation, the endpoint and the company's minimum."""
    co = await _checker(ctx, body)
    s = ctx.hub.settings
    subject = R.subject_of(ctx.hub, co.id, body.exchange, body.uid)
    opens = ctx.who.charter == "support_agent"
    async with ctx.tx() as tx:
        lock = await gate.automation_lock(tx, co.id)
        if lock is not None:
            raise ApiError(423, "company_locked", f"locked: {lock}")
        conv = await R.conversation_of(tx, co.id, body.exchange, body.uid)
        mystery = bool(conv and conv["mystery"])
        hit = (
            None
            if mystery
            else await R.cached_check(tx, co.id, body.exchange, subject, s.referral_check_cache_s)
        )
        if hit is not None or mystery:
            invitee = bool(hit["invitee"]) if hit else False
            meets = hit["meets_minimum"] if hit else None
            case = await R.apply_check(
                tx, company_id=co.id, company=co.code, exchange=body.exchange, subject=subject,
                invitee=invitee, conversation_id=conv["id"] if conv else None, mystery=mystery,
                opens=opens or conv is not None, by_code=ctx.who.code,
            )  # fmt: skip
            await R.record_check(
                tx, company_id=co.id, exchange=body.exchange, subject=subject, ok=not mystery,
                invitee=invitee, meets_minimum=meets, cached=not mystery,
                error_code="mystery" if mystery else None, conversation_id=conv["id"] if conv else None,
                rescue_case_id=case["id"] if case else None, mystery=mystery, by_kind="agent",
                by_code=ctx.who.code,
            )  # fmt: skip
            return {"done": True, "invitee": invitee, "meets_minimum": meets, "cached": hit is not None,
                    "rescue": _effect(case)}  # fmt: skip
        if await R.checks_last_hour(tx, co.id) >= s.referral_checks_per_hour:
            raise ApiError(429, "rate_limited", "referral.check: this company's hourly cap",
                           headers={"Retry-After": "600"})  # fmt: skip
        acct = await tx.first(
            "SELECT adapter FROM revenue.accounts WHERE company_id = :co AND exchange = :ex",
            co=co.id,
            ex=body.exchange,
        )
        if acct is None or acct["adapter"] not in A.ADAPTERS:
            raise ApiError(409, "account_not_configured", "no affiliate account for this exchange")
        spec = A.ADAPTERS[acct["adapter"]]
        account = await signer_account(ctx, tx, spec, co.id, co.code, body.exchange)
        floor = await V.min_balance(tx, co.id)
        reservation = await G.reserve_row(
            tx,
            company_id=co.id,
            actor=ctx.who.code,
            run_id=ctx.who.run_id,
            entry={"tool": "referral.check", "kind": "request", "class": "A0", "method": "POST",
                   "host": account["site"]},
        )  # fmt: skip
    return {
        "done": False,
        "grant": {
            "adapter": spec.name,
            "endpoint": "invite/user/info",
            "params": {"uid": body.uid},
            "local": {"min_balance": str(floor)} if floor is not None else {},
            "account": account,
            "reservation": reservation,
            "max_bytes": 256 * 1024,
        },
    }


@internal_router.post("/growth/referral-check/result", responses=E)
async def referral_check_result(
    body: ReferralResultIn, ctx: Ctx = Depends(internal_ctx)
) -> dict[str, Any]:
    """referral.check, step two (the gateway, after egress answered): the
    reduced answer recorded, its egress entries logged, the case opened
    ("not ours", in a conversation) or closed rescued ("ours")."""
    co = await _checker(ctx, body)
    subject = R.subject_of(ctx.hub, co.id, body.exchange, body.uid)
    async with ctx.tx() as tx:
        own = body.reservation is not None and await G.own_reservation(
            tx, body.reservation, actor=ctx.who.code, run_id=ctx.who.run_id
        )
        if not own:
            raise ApiError(403, "policy_denied", "no connector call of this run to settle")
        await G.record(
            tx, company_id=co.id, actor=ctx.who.code, run_id=ctx.who.run_id,
            entries=[e.model_dump(by_alias=True) for e in body.entries], call_id=body.reservation,
        )  # fmt: skip
        conv = await R.conversation_of(tx, co.id, body.exchange, body.uid)
        case = None
        ok = body.ok and body.invitee is not None
        if ok:
            case = await R.apply_check(
                tx, company_id=co.id, company=co.code, exchange=body.exchange, subject=subject,
                invitee=bool(body.invitee), conversation_id=conv["id"] if conv else None, mystery=False,
                opens=ctx.who.charter == "support_agent" or conv is not None, by_code=ctx.who.code,
            )  # fmt: skip
        await R.record_check(
            tx, company_id=co.id, exchange=body.exchange, subject=subject, ok=ok,
            invitee=body.invitee, meets_minimum=body.meets_minimum if body.invitee else None,
            cached=False, error_code=None if ok else (body.error_code or "connector_failed"),
            conversation_id=conv["id"] if conv else None, rescue_case_id=case["id"] if case else None,
            mystery=False, by_kind="agent", by_code=ctx.who.code,
        )  # fmt: skip
        await ctx.audit(
            tx,
            company_id=co.id,
            action="referral.check",
            action_class="A0",
            target_kind="rescue_case" if case else "referral_check",
            target_ref=case["ref"] if case else body.exchange,
            summary=("invitee" if body.invitee else "not_invitee")
            if ok
            else f"failed: {body.error_code}",
        )
    if not ok:
        raise ApiError(502, "connector_failed", "the exchange did not answer; try again later")
    return {
        "invitee": bool(body.invitee),
        "meets_minimum": body.meets_minimum if body.invitee else None,
        "rescue": _effect(case),
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
