"""⟨21⟩ Every order is answered (contract §29.2) and the delegation budget
(§29.6), the routes; the destructive cards a CTO decides (§29.1, §29.15).

    GET  /orders/{ref}/report            the owner: the order's report (state,
                                         plan, steps, blockers with their fix,
                                         outputs, the end summary)
    POST /orders/{ref}/fix               the owner: one blocker's fix
                                         {action, target, tokens?}; the step-up
                                         is the underlying action's own:
                                           hire             none (§29.10)
                                           hiring.open      🔏 hiring.start on `holding`
                                           lock.open        🔏 kill_switch.release on the
                                                            scope, deploy_freeze.lift on
                                                            company:<CODE>, oversight.release
                                                            on the hold
                                           series.seal      🔏 media.series on the digest
                                           budget.add       none ({tokens})
                                           player.auto      none
                                           connection.guide none (the app opens the guide)
    /internal/v1/orders/{ref}/ack        order.ack (A1): the assignee's plan
    /internal/v1/orders/{ref}/progress   order.progress (A1): one step
    /internal/v1/work/{ref}/budget       work.budget (A2): a CEO, its company's
                                         work, inside the month envelope
    /internal/v1/cards/{ref}/decide      card.decide (A2): the agent approver of
                                         a card (a company's CTO, a
                                         server_destructive card)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, internal_ctx, owner_ctx
from hq_api.domain import control, hiring
from hq_api.domain import decisions as D
from hq_api.domain import order_report as OR
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.routes.internal import allow
from hq_api.schemas import Model
from hq_api.security import stepup
from hq_common.tokens import digest

router = APIRouter(tags=["orders"])
internal_router = APIRouter(tags=["internal"])
E = responses(401, 403, 404, 409, 422, 423)
REF = r"^F-[0-9]{4,}$"


async def _all(ctx: Ctx) -> Any:
    """Every company's view: an order spans companies (and its report is the
    holding's row); what an agent may do is checked by the code here."""
    return ctx.hub.db.tx(await ctx.hub.companies.ids())


# ------------------------------------------------------------------- owner --
@router.get("/orders/{ref}/report", response_model=OR.OrderReport, responses=E)
async def order_report(ref: str, ctx: Ctx = Depends(owner_ctx)) -> OR.OrderReport:
    """The order's report, brought up to date now (contract §29.2)."""
    async with ctx.tx() as tx:
        out = await OR.report(tx, ref)
    if out is None:
        raise ApiError(404, "not_found", f"order {ref}")
    return out


class FixIn(Model):
    action: Literal[
        "hire", "hiring.open", "lock.open", "series.seal", "budget.add", "player.auto",
        "connection.guide",
    ]  # fmt: skip
    target: str | None = Field(default=None, max_length=120)
    tokens: int | None = Field(default=None, gt=0, le=10_000_000)


def _blocker_for(rep: dict[str, Any], action: str, target: str | None) -> dict[str, Any] | None:
    for b in OR._j(rep["blockers"]) or []:
        fix = b.get("fix") or {}
        if fix.get("action") == action and (target is None or fix.get("target") == target):
            return dict(b)
    return None


@router.post("/orders/{ref}/fix", response_model=OR.OrderReport, responses=E)
async def fix_order(
    ref: str, body: FixIn, request: Request, ctx: Ctx = Depends(owner_ctx)
) -> OR.OrderReport:
    """One tap on a blocker's fix (contract §29.2's table). The fix must be one
    of the report's blockers now (`budget.add` also on any open work of the
    order); each runs the owner's existing action, with its own step-up."""
    later: list[str] = []
    async with ctx.tx() as tx:
        rep = await OR.ensure(tx, ref)
        if rep is None:
            raise ApiError(404, "not_found", f"order {ref}")
        rep = await OR.refresh(tx, ref)
        assert rep is not None
        order = await OR.load_order(tx, ref)
        works = await OR.tree(tx, OR.root_refs(order or {}))
        b = _blocker_for(rep, body.action, body.target)
        target = body.target or ((b or {}).get("fix") or {}).get("target")
        in_tree = {w["ref"]: w for w in works}
        if b is None and not (body.action == "budget.add" and target in in_tree):
            raise ApiError(409, "validation_failed", "no blocker of this order has that fix now")
        summary = await _apply_fix(ctx, tx, request, body, target, in_tree, later)
        await ctx.audit(
            tx,
            company_id=rep["company_id"],
            action="order.fix",
            action_class="A2",
            target_kind="order",
            target_ref=ref,
            summary=f"{body.action} {target or ''}: {summary}"[:500],
            step_up=body.action in ("hiring.open", "lock.open", "series.seal"),
        )
        await ctx.interaction(
            tx,
            company_id=rep["company_id"],
            kind="decision",
            action="order.fix",
            target_kind="order",
            target_ref=ref,
            data={"action": body.action, "target": target, "tokens": body.tokens},
        )
        out = await OR.report(tx, ref)
    for d in later:
        await workflows_client.decision_decided(ctx.hub, d)
    assert out is not None
    return out


async def _apply_fix(
    ctx: Ctx,
    tx: Any,
    request: Request,
    body: FixIn,
    target: str | None,
    works: dict[str, dict[str, Any]],
    later: list[str],
) -> str:
    holding = await ctx.hub.companies.holding()
    if body.action == "hire":
        code, _, role = (target or "").partition(":")
        company = await ctx.hub.companies.by_code(code)
        out = await hiring.auto_fill(tx, company.id, role, charters=ctx.hub.charters)
        return f"employee {out['employee']}"
    if body.action == "hiring.open":
        await _consume_either(
            tx, request, ctx, [("hiring.start", "holding"), ("hiring.open", target or "holding")]
        )
        await hiring.start(
            tx, ctx.who, holding_id=holding.id, holding_code=holding.code, mode="auto",
            charters=ctx.hub.charters,
        )  # fmt: skip
        return "hiring open (auto)"
    if body.action == "lock.open":
        return await _open_lock(ctx, tx, request, target or "")
    if body.action == "series.seal":
        from hq_api.domain import studio as S

        s = await S.load_series(tx, target or "", lock=True)
        su = await _consume_either(
            tx, request, ctx, [("media.series", s["digest"]), ("series.seal", target or "")]
        )
        out = await S.seal_series(tx, ctx.hub, ctx.who, s, s["digest"], su)
        if out.get("decision_ref"):
            later.append(str(out["decision_ref"]))
        return f"series {target} sealed"
    if body.action == "budget.add":
        if not body.tokens:
            raise ApiError(422, "validation_failed", fields={"tokens": "how many tokens to add"})
        w = works.get(target or "")
        if w is None or w["status"] not in W.OPEN:
            raise ApiError(409, "validation_failed", "an open work of this order")
        new = await W.add_budget(tx, w, body.tokens, ctx.who)
        return f"+{body.tokens} tokens on {w['ref']} (budget {new})"
    if body.action == "player.auto":
        w = works.get(target or "")
        if w is None:
            raise ApiError(409, "validation_failed", "a work of this order")
        await tx.exec("UPDATE work.work SET player = 'auto' WHERE id = :id", id=w["id"])
        await W.add_budget(tx, w, 0, ctx.who)  # goes on, with the hub's own player
        return f"{w['ref']} plays auto"
    return "guide"  # connection.guide: the app opens /connections/guides/{kind}


async def _consume_either(tx: Any, request: Request, ctx: Ctx, pairs: list[tuple[str, str]]) -> Any:
    """A fix's step-up: signed on the hub's own action and target (the first
    pair) or on the fix's own action and target (the apps sign a fix as it
    is named); either is single-use, bound to the session, 120 s."""
    token = request.headers.get(stepup.HEADER)
    if token:
        row = await tx.first(
            "SELECT action, target FROM auth.step_ups WHERE token_sha256 = :h",
            h=digest(token),
        )
        for action, tgt in pairs:
            if row is not None and row["action"] == action and row["target"] == tgt:
                return await stepup.consume(tx, request, ctx.who, action, tgt)
    return await stepup.consume(tx, request, ctx.who, *pairs[0])


async def _open_lock(ctx: Ctx, tx: Any, request: Request, target: str) -> str:
    """The owner's own release of what locks the order (each with its step-up)."""
    if target.startswith("hold:"):
        from hq_api.domain import oversight as O

        href = target.removeprefix("hold:")
        su = await stepup.consume(tx, request, ctx.who, "oversight.release", href)
        await O.decide_hold(tx, ctx.who, href, "released", "از گزارش فرمان آزاد شد", su)
        return f"hold {href} released"
    company = await control.resolve_scope(tx, target)
    state = await tx.scalar("SELECT control.lock_state(:co)", co=company["id"])
    if state == "deploy_freeze":
        scope = f"company:{company['code']}"
        await stepup.consume(tx, request, ctx.who, "deploy_freeze.lift", scope)
        ids = [f["id"] for f in await control.active_freezes(tx, company["id"])]
        await control.lift_deploy_freezes(tx, ctx.who, company, ids)
        return f"freezes lifted on {company['code']}"
    if state == "holding":
        company = await control.resolve_scope(tx, "holding")
        target = "holding"
    await stepup.consume(tx, request, ctx.who, "kill_switch.release", target)
    await control.set_kill_switch(tx, ctx.who, company, "released", "از گزارش فرمان باز شد")
    return f"kill switch released on {target}"


# -------------------------------------------------------------- the agents --
class AckIn(Model):
    plan_fa: str = Field(min_length=1, max_length=2000)
    assigned: list[str] = Field(default_factory=list, max_length=20)
    due_at: datetime | None = None


class ProgressIn(Model):
    step_fa: str = Field(min_length=1, max_length=1000)


def _agent(ctx: Ctx) -> None:
    if not ctx.who.is_agent or ctx.who.company_id is None:
        raise ApiError(403, "policy_denied", "agents only")


@internal_router.post("/orders/{ref}/ack", response_model=OR.OrderReport, responses=E)
async def order_ack(ref: str, body: AckIn, ctx: Ctx = Depends(internal_ctx)) -> OR.OrderReport:
    """order.ack (A1): the plan of an order's assignee (or its company's CEO):
    «فهمیدم؛ برنامه: …؛ به … سپردم؛ تحویل تا …», within 10 minutes."""
    _agent(ctx)
    async with await _all(ctx) as tx:
        assigned = await OR.may_speak(tx, ref, ctx.who)
        await allow(ctx, "order.ack", {"company": ctx.who.company, "assigned": assigned})
        if not assigned:
            raise ApiError(403, "policy_denied", "not an order you work on")
        await OR.acknowledge(
            tx,
            ctx.who,
            ref,
            plan_fa=body.plan_fa,
            assigned=[{"code": c} for c in body.assigned],
            due_at=body.due_at,
        )
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,  # type: ignore[arg-type]
            action="order.ack",
            action_class="A1",
            target_kind="order",
            target_ref=ref,
            summary=f"plan by {ctx.who.code}, {len(body.assigned)} assigned",
        )
        out = await OR.report(tx, ref)
    assert out is not None
    return out


@internal_router.post("/orders/{ref}/progress", response_model=OR.OrderReport, responses=E)
async def order_progress(
    ref: str, body: ProgressIn, ctx: Ctx = Depends(internal_ctx)
) -> OR.OrderReport:
    """order.progress (A1): one step of the order, in plain Persian."""
    _agent(ctx)
    async with await _all(ctx) as tx:
        assigned = await OR.may_speak(tx, ref, ctx.who)
        await allow(ctx, "order.progress", {"company": ctx.who.company, "assigned": assigned})
        if not assigned:
            raise ApiError(403, "policy_denied", "not an order you work on")
        await OR.progress(tx, ctx.who, ref, body.step_fa)
        await ctx.audit(
            tx,
            company_id=ctx.who.company_id,  # type: ignore[arg-type]
            action="order.progress",
            action_class="A1",
            target_kind="order",
            target_ref=ref,
            summary=body.step_fa[:200],
        )
        out = await OR.report(tx, ref)
    assert out is not None
    return out


class BudgetIn(Model):
    add_tokens: int = Field(gt=0, le=5_000_000)


class BudgetOut(BaseModel):
    ref: str
    budget_tokens: int | None
    tokens_used: int
    status: str


@internal_router.post("/work/{ref}/budget", response_model=BudgetOut, responses=E)
async def work_budget(
    ref: str, body: BudgetIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """work.budget (A2): a CEO gives a work of its own company more tokens
    («بودجه کم است، +X بدهم؟»), inside the company's month envelope (409
    envelope_exceeded); a waiting work goes on. Requires `Idempotency-Key`."""
    _agent(ctx)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        w = await tx.first(W.WORK_SQL + " WHERE w.ref = :r", r=ref)
        await allow(
            ctx, "work.budget", {"company": w["company"] if w else None, "role": ctx.who.role}
        )
        if w is None:
            raise ApiError(403, "policy_denied", "a work of your company")
        await ctx.ensure_unlocked(tx, w["company_id"])
        env = next((e for e in await hiring.envelopes(tx) if e.company == w["company"]), None)
        if (
            env is not None
            and env.tokens_month
            and env.used_month + body.add_tokens > env.tokens_month
        ):
            raise ApiError(
                409,
                "envelope_exceeded",
                f"{env.used_month} used + {body.add_tokens} > {env.tokens_month} this month",
            )
        await W.add_budget(tx, w, body.add_tokens, ctx.who)
        await ctx.audit(
            tx,
            company_id=w["company_id"],
            action="work.budget",
            action_class="A2",
            target_kind="work",
            target_ref=ref,
            summary=f"+{body.add_tokens} tokens by {ctx.who.code}",
        )
        row = await tx.one(
            "SELECT ref, budget_tokens, tokens_used, status FROM work.work WHERE id = :id",
            id=w["id"],
        )
        result = BudgetOut(
            ref=row["ref"],
            budget_tokens=row["budget_tokens"],
            tokens_used=int(row["tokens_used"]),
            status=row["status"],
        )
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    return result


class CardDecideIn(Model):
    verdict: Literal["approve", "reject", "return"]
    note: str | None = Field(default=None, max_length=5000)


@internal_router.post("/cards/{ref}/decide", response_model=D.Decision, responses=E)
async def card_decide(
    ref: str, body: CardDecideIn, request: Request, ctx: Ctx = Depends(internal_ctx)
) -> Any:
    """card.decide (A2), hire.decide's sibling: the agent approver of a card
    decides it (a company's CTO, its server_destructive cards; contract §29.1,
    §29.15). Anyone else: 403. Requires `Idempotency-Key`."""
    _agent(ctx)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        try:
            d = await D.load(tx, ref, lock=True)
        except ApiError as exc:  # another company's card: refused, never "missing"
            raise ApiError(403, "policy_denied", "this card is not yours to decide") from exc
        await allow(
            ctx,
            "card.decide",
            {"company": d["company"], "approver": d.get("approver_code"), "kind": d["kind"]},
        )
        if d["kind"] not in D.AGENT_CARD_KINDS or d.get("approver_code") != ctx.who.code:
            raise ApiError(403, "policy_denied", "this card is not yours to decide")
        await ctx.ensure_unlocked(tx, d["company_id"])
        verdict: Literal["approved", "rejected", "returned"] = {
            "approve": "approved",
            "reject": "rejected",
            "return": "returned",
        }[body.verdict]  # type: ignore[assignment]
        out = await D.decide(tx, ctx.who, d, verdict, note=body.note, hub=ctx.hub)
        await ctx.audit(
            tx,
            company_id=d["company_id"],
            action=f"card.{body.verdict}",
            action_class="A2",
            target_kind="decision",
            target_ref=ref,
            summary=f"{d['kind']} -> {verdict} by {ctx.who.code}",
        )
        result = D.render(out)
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    await workflows_client.decision_decided(ctx.hub, ref)
    return result
