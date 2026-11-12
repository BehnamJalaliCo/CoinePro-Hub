"""⟨1.15⟩ Prompt 24 (contract §33.2-§33.3): the companies' payments, read and reconciled, and the
revenue board (code only).

Owner (/api/v1; OPA hq.money):
    GET   /companies/{code}/payment-sources       the company's sources (public addresses only)
    POST  /companies/{code}/payment-sources       🔏 payment.source (target: SHA-256 of the exact
                                                  body): add or change one; a ledger source needs
                                                  the company's runner paired
    POST  /payment-sources/{id}/read              Idempotency-Key: read one source now (a ledger
                                                  job on the runner, or the chain through egress),
                                                  then the company is reconciled
    GET   /companies/{code}/payments              ?status&from&to&limit&cursor, newest first
    GET   /companies/{code}/reconcile             ?from&to: the reconcile per day
    GET   /revenue/board                          ?company: the RevenueBoard
Agents (/internal/v1):
    POST  /money/read                             the same reads for the company's CEO and FIN
                                                  manager (the SALES manager: the leads), the
                                                  advisor (any company's board); read only

Money is read, never moved: nothing here approves, rejects, refunds or extends anything in a
company system, signs a transaction or holds a key.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from hq_api import idempotency, pagination
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import affiliate_gaps as AG
from hq_api.domain import gate
from hq_api.domain import leads as L
from hq_api.domain import money_jobs as MJ
from hq_api.domain import payments as P
from hq_api.domain import revenue_board as RB
from hq_api.errors import ApiError, responses
from hq_api.routes.agent_tools import read_tx
from hq_api.schemas import CODE, Page
from hq_api.security import stepup

router = APIRouter(tags=["money"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423, 428)
E502 = {**E, 502: E[422]}
STATUS = Literal["matched", "ledger_only", "chain_only", "amount_mismatch", "pending_chain"]


async def policy(ctx: Ctx, op: str, company: str | None) -> None:
    await ctx.hub.policy.require(
        "money", {"principal": ctx.who.opa(), "op": op, "target": {"company": company}}
    )


async def company_of(ctx: Ctx, code: str) -> Any:
    """A company (never the holding: it takes no payments)."""
    try:
        co = await ctx.hub.companies.by_code(code)
    except ApiError as exc:
        raise ApiError(
            404, "not_found", "no such company", message_fa="این شرکت پیدا نشد."
        ) from exc
    if co.kind == "holding":
        raise ApiError(404, "not_found", "no such company", message_fa="این شرکت پیدا نشد.")
    return co


def day_arg(request: Request, name: str) -> date | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={name: "YYYY-MM-DD"}) from exc


# ------------------------------------------------------------------ sources --
@router.get(
    "/companies/{code}/payment-sources", response_model=list[P.PayPaymentSource], responses=E
)
async def list_payment_sources(
    code: str, ctx: Ctx = Depends(owner_ctx)
) -> list[P.PayPaymentSource]:
    """⟨1.15⟩ §33.2 where the company's payments are read from: its own ledger (through its runner)
    and its public USDT addresses on BSC and TRON; each with its state, the last read and the plain
    reason of its last error."""
    co = await company_of(ctx, code)
    await policy(ctx, "source.read", co.code)
    async with ctx.tx() as tx:
        return [P.render_source(r) for r in await P.list_sources(tx, co.id)]


@router.post(
    "/companies/{code}/payment-sources",
    response_model=P.PayPaymentSource,
    status_code=201,
    responses=E,
)
async def put_payment_source(
    code: str, body: P.PayPaymentSourceIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.15⟩ §33.2 🔏 (`payment.source`, target = SHA-256 of the exact body): add a source, or change
    the one already there. `ledger`: the company's own records through its paired runner (the query
    lives on the company server; this names at most the runner's `server`). `chain`: a PUBLIC
    address (`network` bsc_usdt or trc20_usdt) the transfers are read to. No key is ever asked for
    or kept. Honours `Idempotency-Key`."""
    co = await company_of(ctx, code)
    await policy(ctx, "source.write", co.code)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who)
        if idem and idem.replay:
            return idem.replay
        step_up_id = await stepup.consume(
            tx, request, ctx.who, "payment.source", await stepup.body_target(request)
        )
        row, created = await P.put_source(tx, co.id, co.code, body)
        await ctx.audit(
            tx,
            company_id=co.id,
            action="payment.source",
            action_class="A2",
            target_kind="payment_source",
            target_ref=str(row["id"]),
            summary=f"{'added' if created else 'changed'} {body.kind}"
            + (f" {body.network}" if body.network else "")
            + ("" if body.enabled else " (off)"),
            step_up=step_up_id is not None,
        )
        await ctx.interaction(
            tx,
            company_id=co.id,
            kind="setting",
            action="payment.source",
            target_kind="payment_source",
            target_ref=str(row["id"]),
        )
        out = P.render_source(row)
        if idem:
            await idem.store(tx, 201, out.model_dump(mode="json"))
    return out


@router.post("/payment-sources/{id}/read", response_model=P.PayReadResult, responses=E502)
async def read_payment_source(id: UUID, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.15⟩ §33.2 the owner reads one source now (`Idempotency-Key` required). A ledger source
        collects its finished job and queues the next `ledger` job on the company's runner (it answers
        at once with `queued`; the rows are stored when the runner reports; a runner that is missing or
    too old is the source's `last_error_fa`); a chain source is scanned
        through egress and the company is reconciled. A chain that answers badly is a 502 with a plain
        reason (the same reason is kept on the source)."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        src = await tx.first(P.SOURCE_SQL + " WHERE s.id = :id", id=id)
        if src is None:
            raise ApiError(404, "not_found", "no such source", message_fa="این منبع پیدا نشد.")
        await policy(ctx, "source.pull", src["company"])
        lock = await gate.automation_lock(tx, src["company_id"])
        if lock:
            raise ApiError(423, "company_locked", f"locked: {lock}")
        await ctx.audit(
            tx,
            company_id=src["company_id"],
            action="payment.read",
            action_class="A0",
            target_kind="payment_source",
            target_ref=str(src["id"]),
            summary=f"{src['kind']} read by the owner",
        )
        result = P.PayReadResult(source=P.render_source(src))
        if src["kind"] == "ledger":
            src = await P.load_source(tx, id, lock=True)
            got = await P.read_ledger(tx, src)
            await P.emit_read(tx, src, queued=bool(got.get("queued")), error=bool(got.get("error")))
            result = P.PayReadResult(
                source=P.render_source(await P.load_source(tx, id)),
                queued=bool(got.get("queued")),
                payments=int(got.get("ingested") or 0),
            )
            if idem:
                await idem.store(tx, 200, result.model_dump(mode="json"))
    if src["kind"] == "ledger":
        await MJ.reconcile_company(ctx.hub, src["company_id"])
        return result
    # The claim is committed above and answered only below: a failure in between gives the
    # key back, so the app's retry with the same key reads again (not 409 «still running»).
    try:
        got = await MJ.read_now(ctx.hub, id)
        if got.get("error"):
            raise ApiError(
                502,
                "connector_failed",
                str(got["error"]),
                message_fa=str(got.get("reason_fa") or ""),
            )
        async with ctx.tx() as tx:
            result = P.PayReadResult(
                source=P.render_source(await P.load_source(tx, id)),
                transfers=int(got.get("transfers") or 0),
                pages=int(got.get("pages") or 0),
            )
            if idem:
                await idem.store(tx, 200, result.model_dump(mode="json"))
    except Exception:
        if idem:
            async with ctx.tx() as tx:
                await idem.release(tx)
        raise
    return result


# ----------------------------------------------------------------- payments --
async def payments_page(
    tx: Any,
    company_id: UUID,
    *,
    status: str | None,
    start: date | None,
    end: date | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    after_t, after_id = pagination.time_id(cursor)
    rows = await tx.all(
        """SELECT p.*, c.code AS company FROM money.payments p
           JOIN core.companies c ON c.id = p.company_id
           WHERE p.company_id = :co
             AND (CAST(:st AS text) IS NULL OR p.status = :st)
             AND (CAST(:f AS date) IS NULL OR p.paid_at >= CAST(:f AS date))
             AND (CAST(:t AS date) IS NULL OR p.paid_at < CAST(:t AS date) + 1)
             AND (CAST(:after_t AS timestamptz) IS NULL
                  OR (p.paid_at, p.id) < (CAST(:after_t AS timestamptz), CAST(:after_id AS uuid)))
           ORDER BY p.paid_at DESC, p.id DESC LIMIT :lim""",
        co=company_id,
        st=status,
        f=start,
        t=end,
        after_t=after_t,
        after_id=after_id,
        lim=limit + 1,
    )
    return pagination.page(rows, limit, ("paid_at", "id"))


@router.get("/companies/{code}/payments", response_model=Page[P.PayPayment], responses=E)
async def list_payments(
    code: str,
    request: Request,
    status: STATUS | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[P.PayPayment]:
    """⟨1.15⟩ §33.2 the company's payments, newest first: the ledger's rows (a pseudonymous customer,
    never a name) and the transfers nobody claimed (`chain_only`), each with its reconcile status
    and a plain note. `from`/`to` are UTC days (inclusive)."""
    co = await company_of(ctx, code)
    await policy(ctx, "payment.read", co.code)
    start, end = day_arg(request, "from"), day_arg(request, "to")
    async with ctx.tx() as tx:
        items, nxt = await payments_page(
            tx, co.id, status=status, start=start, end=end, limit=limit, cursor=cursor
        )
    return Page(items=[P.render_payment(r) for r in items], next_cursor=nxt)


async def reconcile_days(
    tx: Any, company_id: UUID, code: str, start: date | None, end: date | None
) -> list[P.PayReconcile]:
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=29)
    if start > end or (end - start).days >= 400:
        raise ApiError(422, "validation_failed", fields={"from": "at most 400 days, from <= to"})
    rows = await tx.all(
        """SELECT * FROM money.reconcile_days WHERE company_id = :co AND day BETWEEN :f AND :t
           ORDER BY day DESC""",
        co=company_id,
        f=start,
        t=end,
    )
    return [
        P.PayReconcile(
            company=code,
            day=r["day"].isoformat(),
            ledger_count=r["ledger_count"],
            chain_count=r["chain_count"],
            matched=r["matched"],
            ledger_only=r["ledger_only"],
            chain_only=r["chain_only"],
            amount_mismatch=r["amount_mismatch"],
            pending_chain=r["pending_chain"],
            note_fa=r["note_fa"],
        )
        for r in rows
    ]


@router.get("/companies/{code}/reconcile", response_model=list[P.PayReconcile], responses=E)
async def get_reconcile(
    code: str, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> list[P.PayReconcile]:
    """⟨1.15⟩ §33.2 the reconcile per UTC day, newest first (default: the last 30 days, at most
    400): the ledger's rows and the chain's transfers, and how many were matched, `ledger_only`
    (approved without money), `chain_only` (money without a customer), short or still waiting for
    the chain. Computed daily and after every read of the owner."""
    co = await company_of(ctx, code)
    await policy(ctx, "reconcile.read", co.code)
    start, end = day_arg(request, "from"), day_arg(request, "to")
    async with ctx.tx() as tx:
        return await reconcile_days(tx, co.id, co.code, start, end)


# -------------------------------------------------------------------- board --
@router.get("/revenue/board", response_model=RB.RevenueBoard, responses=E)
async def revenue_board(
    company: str | None = Query(default=None, pattern=CODE), ctx: Ctx = Depends(owner_ctx)
) -> RB.RevenueBoard:
    """⟨1.15⟩ §33.3 the revenue board, every figure by code from the stored payments and costs:
    MRR by month (each payment spread over its period), new, churned and active customers, ARPU,
    churn rate, LTV, CAC, payback, cohorts, Holt's forecast with its band (only with 4 complete
    months), ROI against tokens, voice and ads, and the cost of each output. Without `company`:
    every company together."""
    co = await company_of(ctx, company) if company else None
    await policy(ctx, "board.read", co.code if co else None)
    async with ctx.tx() as tx:
        return await RB.build(tx, co.id if co else None, co.code if co else None)


# ------------------------------------------------------------------- agents --
class MoneyReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    what: Literal[
        "sources", "payments", "reconcile", "board", "leads", "pipeline", "affiliate_gaps"
    ]
    company: str | None = Field(default=None, pattern=CODE)
    status: STATUS | None = None
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None
    limit: int = Field(default=50, ge=1, le=pagination.MAX_LIMIT)
    cursor: str | None = Field(default=None, max_length=500)


OPS = {
    "sources": "source.read",
    "payments": "payment.read",
    "reconcile": "reconcile.read",
    "board": "board.read",
    "leads": "lead.read",
    "pipeline": "lead.read",
    "affiliate_gaps": "affiliate.read",
}


@internal_router.post("/money/read", responses=E)
async def money_read(body: MoneyReadIn, ctx: Ctx = Depends(internal_ctx)) -> dict[str, Any]:
    """⟨1.15⟩ §33.2-§33.5 (A0, read only): a company's sources, payments, reconcile, revenue board,
    leads, pipeline or affiliate gaps, for its CEO and FIN manager (its SALES manager: the leads),
    and any company's board for the holding's advisor. The company is the agent's own unless the
    advisor names one; a missing and a forbidden company answer the same 403."""
    if not ctx.who.is_agent:
        raise ApiError(403, "policy_denied", "agents only")
    wanted = body.company or ctx.who.company
    await policy(ctx, OPS[body.what], wanted)
    co = await company_of(ctx, str(wanted))
    async with read_tx(ctx) as tx:
        if body.what == "sources":
            items: Any = [P.render_source(r) for r in await P.list_sources(tx, co.id)]
            return {"items": [i.model_dump(mode="json") for i in items]}
        if body.what == "payments":
            rows, nxt = await payments_page(
                tx, co.id, status=body.status, start=body.from_, end=body.to,
                limit=body.limit, cursor=body.cursor,
            )  # fmt: skip
            return {
                "items": [P.render_payment(r).model_dump(mode="json") for r in rows],
                "next_cursor": nxt,
            }
        if body.what == "reconcile":
            days = await reconcile_days(tx, co.id, co.code, body.from_, body.to)
            return {"items": [d.model_dump(mode="json") for d in days]}
        if body.what == "board":
            board = await RB.build(tx, co.id, co.code)
            return board.model_dump(mode="json")
        if body.what == "pipeline":
            pipe = await L.pipeline(tx, {"id": co.id, "code": co.code}, write=False)
            return pipe.model_dump(mode="json")
        if body.what == "affiliate_gaps":
            gaps = await AG.listing(tx, co.id)
            return {"items": [g.model_dump(mode="json") for g in gaps]}
        rows = await tx.all(
            L.LEAD_SQL + " WHERE l.company_id = :co ORDER BY l.created_at DESC, l.id DESC LIMIT :n",
            co=co.id,
            n=body.limit,
        )
        return {"items": [L.render(r, []).model_dump(mode="json") for r in rows]}
