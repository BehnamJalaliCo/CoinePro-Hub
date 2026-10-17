"""Voice orders (contract §17.4): POST /orders routes one order of the owner
(rules, then the light model, then the advisor) and carries each route out
in one transaction; GET /orders lists them with where each went."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, Field

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as Dec
from hq_api.domain import orders as O
from hq_api.domain import work as W
from hq_api.errors import ApiError, responses
from hq_api.principal import Principal
from hq_api.routes.messages import post_message
from hq_api.schemas import Model, Page
from hq_api.workshop import domain as WS
from hq_api.workshop import service
from hq_common.redact import scrub

router = APIRouter(tags=["orders"])
E = responses(401, 403, 404, 409, 422)
# Who proposes the code_session decision an order needs (no grant yet).
ORDERS = Principal(kind="service", code="orders", role="service")
CODE_SESSION_BUDGET_USD = Decimal("20")
CODE_SESSION_DAYS = 7


class OrderIn(Model):
    text: str = Field(min_length=1, max_length=10000)
    source: Literal["voice", "text"] = "text"
    file_id: UUID | None = None
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")


class OrderRoute(BaseModel):
    company: str
    to: str
    kind: Literal["work", "code", "meeting", "question"]
    work_ref: str | None = None
    session_ref: str | None = None
    decision_ref: str | None = None
    # ⟨additive⟩ the message posted (question, advisor); why a route stopped short
    message_ref: str | None = None
    note_fa: str | None = None


class OrderOut(BaseModel):
    ref: str
    summary_fa: str
    routes: list[OrderRoute]
    # ⟨additive⟩ rules | model | advisor
    routed_by: Literal["rules", "model", "advisor"]


class OrderRecord(OrderOut):
    text: str
    source: Literal["voice", "text"]
    file_id: UUID | None
    created_at: datetime


def _record(r: dict[str, Any]) -> OrderRecord:
    return OrderRecord(
        ref=r["ref"],
        summary_fa=r["summary_fa"],
        routes=[OrderRoute(**x) for x in r["routes"]],
        routed_by=r["routed_by"],
        text=r["text"],
        source=r["source"],
        file_id=r["file_id"],
        created_at=r["created_at"],
    )


async def _seen(ctx: Ctx, request: Request) -> bool:
    """Whether this Idempotency-Key was used already (then no model is asked
    again: the claim in the main transaction answers with the replay)."""
    key = idempotency.read_key(request, required=True)
    async with ctx.tx() as tx:
        return bool(
            await tx.scalar(
                """SELECT 1 FROM core.idempotency_keys WHERE principal = :p AND key = :k
                   AND created_at > now() - make_interval(hours => 24)""",
                p=f"{ctx.who.kind}:{ctx.who.code}",
                k=key,
            )
        )


async def _route(ctx: Ctx, text: str, hint: str | None) -> tuple[list[O.Route], str]:
    """Before the transaction (the model may take seconds)."""
    async with ctx.tx() as tx:
        d = await O.directory(tx)
    routes = O.by_rules(text, d, hint)
    if routes:
        return routes, "rules"
    answer = await workflows_client.route_order(ctx.hub, O.model_request(text, d))
    routes = O.check_model({"routes": (answer or {}).get("routes")}, d)
    if routes:
        return routes, "model"
    adv = d.get("advisor")
    if adv is None:
        raise ApiError(422, "validation_failed", fields={"text": "no route and no advisor"})
    return [O.Route(adv["company"], adv["code"], "question")], "advisor"


async def _work(
    ctx: Ctx, tx: Tx, r: O.Route, ref: str, text: str, title: str, *, meeting: bool = False
) -> None:
    co = await ctx.hub.companies.by_code(r.company)
    brief = f"{text}\n\n(فرمان {ref} مدیر کل)"
    try:
        w = await W.create(
            tx,
            ctx.who,
            company_id=co.id,
            company_code=co.code,
            title=("جلسه: " if meeting else "") + title,
            brief=brief,
            kind="one_off",
            priority="P2",
            department_code=r.department,
        )
    except ApiError:
        if r.department is None:
            raise
        # The department has no active manager: the CEO receives it instead.
        w = await W.create(
            tx,
            ctx.who,
            company_id=co.id,
            company_code=co.code,
            title=title,
            brief=brief,
            kind="one_off",
            priority="P2",
        )
    r.to = w["a_code"]
    r.refs["work_ref"] = w["ref"]
    await ctx.audit(
        tx,
        company_id=co.id,
        action="work.create",
        action_class="A2",
        target_kind="work",
        target_ref=w["ref"],
        summary=f"order {ref}: one_off P2 to {w['a_code']}",
    )


async def _question(ctx: Ctx, tx: Tx, r: O.Route, ref: str, text: str, routed_by: str) -> None:
    thread = await tx.scalar(
        "SELECT code FROM msg.threads WHERE kind = 'advisor' ORDER BY code LIMIT 1"
    )
    if thread is None:
        raise ApiError(422, "validation_failed", fields={"text": "the advisor has no thread"})
    lead = (
        "فرمان مدیر کل که مسیرش روشن نبود؛ لطفاً بگو به کجا برود یا خودت پیش ببر:"
        if routed_by == "advisor"
        else "پرسش مدیر کل:"
    )
    m = await post_message(ctx, tx, thread, f"{lead}\n\n{text}\n\n(فرمان {ref})", {})
    r.refs["message_ref"] = m["ref"]


async def _code(
    ctx: Ctx, tx: Tx, r: O.Route, ref: str, text: str, title: str, later: list[Any]
) -> None:
    ws = await WS.workspace(tx, r.workspace or r.to)
    rt = getattr(ctx.hub, "workshop", None)
    running = await tx.first(
        WS.SESSION_SQL
        + """ WHERE s.workspace_id = :ws AND s.state = ANY(:active) AND s.held IS NULL
              ORDER BY s.updated_at DESC LIMIT 1""",
        ws=ws["id"],
        active=list(WS.ACTIVE),
    )
    if running is not None and rt is not None:
        await WS.append(
            tx,
            running,
            "message",
            text[:300],
            {"chars": len(text)},
            actor=(ctx.who.kind, ctx.who.code),
        )
        r.refs["session_ref"] = running["ref"]
        later.append((service.steer, running["id"], f"{text}\n\n(فرمان {ref})"))
        return
    grant = await tx.first(
        WS.GRANT_SQL
        + """ WHERE g.workspace_id = :ws AND g.revoked_at IS NULL AND g.expires_at > now()
              ORDER BY g.created_at DESC LIMIT 1""",
        ws=ws["id"],
    )
    if grant is not None and rt is not None:
        s = await WS.open_session(
            tx,
            ctx.who,
            ctx.audit,
            grant_ref=grant["ref"],
            title=title,
            brief=f"{text}\n\n(فرمان {ref})",
            area="",
            model=ctx.hub.settings.workshop_model,
            effort=ctx.hub.settings.workshop_effort,
            runtime=rt.name,
        )
        r.refs["session_ref"] = s["ref"]
        if not s["held"]:
            later.append((service.start, s["id"]))
        return
    if grant is not None:
        r.note_fa = "مجوز هست ولی محل اجرای کارگاه هنوز انتخاب نشده"
        return
    co = await ctx.hub.companies.by_code(ws["company"])
    actions = [a for a in WS.ACTIONS if a != "open_pr" or WS.policy_of(ws)["may_open_pr"]]
    d = await Dec.propose(
        tx,
        ORDERS,
        company_id=co.id,
        company_code=co.code,
        body=Dec.DecisionIn(
            kind="code_session",
            title=f"سشن کارگاه کد برای {ws['code']}: {title}"[:300],
            what=text,
            why=f"فرمان {ref} مدیر کل؛ برای این workspace مجوز فعالی نیست.",
            risk="medium",
            payload={
                "workspace": ws["code"],
                "actions": actions,
                "budget_usd": str(CODE_SESSION_BUDGET_USD),
                "days": CODE_SESSION_DAYS,
                "title": title,
                "brief": text,
            },
        ),
        thread_code=None,
    )
    r.refs["decision_ref"] = d["ref"]
    later.append(("decision", d["ref"]))


@router.post("/orders", response_model=OrderOut, status_code=201, responses=E)
async def create_order(
    body: OrderIn, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Routes an order of the owner (typed, or from `/transcribe`): rules first
    (company, role and keyword names), then the light model, then the advisor
    only when it is still ambiguous. work -> the CEO or, when a department is
    named, its manager (the shortcut); code -> a running session of the
    workspace, else a new session under a live grant, else a `code_session`
    decision; question -> the advisor (thread A); meeting -> a work item for
    the CEO. What agents and models read is masked. Requires `Idempotency-Key`."""
    text = scrub(body.text)
    seen = await _seen(ctx, request)
    routes, routed_by = ([], "rules") if seen else await _route(ctx, text, body.company)
    later: list[Any] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if seen:  # the first request's key expired this very moment: send it again
            raise ApiError(409, "idempotency_conflict", "retry with a new Idempotency-Key")
        if body.file_id and not await tx.scalar(
            "SELECT 1 FROM files.files WHERE id = :id", id=body.file_id
        ):
            raise ApiError(422, "validation_failed", fields={"file_id": "unknown file"})
        ref: str = await tx.scalar(
            "SELECT 'F-' || lpad(nextval('owner.order_ref_seq')::text, 4, '0')"
        )
        title = " ".join(text.split())[:80] or ref
        for r in routes:
            if r.kind in ("work", "meeting"):
                await _work(
                    ctx, tx, r, ref, text, r.summary_fa or title, meeting=r.kind == "meeting"
                )
            elif r.kind == "question":
                await _question(ctx, tx, r, ref, text, routed_by)
            else:
                await _code(ctx, tx, r, ref, text, r.summary_fa or title, later)
        holding = await ctx.hub.companies.holding()
        out = [r.out() for r in routes]
        summary = O.summary_of(text, routes)
        await tx.exec(
            """INSERT INTO owner.orders (ref, company_id, text, source, file_id, company_hint,
                   routes, routed_by, summary_fa)
               VALUES (:ref, :co, :text, :src, :fid, :hint, CAST(:routes AS jsonb), :by, :sum)""",
            ref=ref,
            co=holding.id,
            text=text,
            src=body.source,
            fid=body.file_id,
            hint=body.company,
            routes=_json(out),
            by=routed_by,
            sum=summary[:2000],
        )
        await ctx.emit(
            tx,
            holding.code,
            "order.routed",
            ref,
            {
                "routes": [{k: x[k] for k in ("company", "kind", "to")} for x in out],
                "by": routed_by,
            },
        )
        await ctx.audit(
            tx,
            company_id=holding.id,
            action="order.route",
            action_class="A2",
            target_kind="order",
            target_ref=ref,
            summary=f"{routed_by}: " + ", ".join(f"{x['kind']}->{x['to']}" for x in out),
        )
        await ctx.interaction(
            tx,
            company_id=holding.id,
            kind="order",
            action="order.create",
            target_kind="order",
            target_ref=ref,
            data={"source": body.source, "routes": len(out), "routed_by": routed_by},
        )
        result = OrderOut(
            ref=ref,
            summary_fa=summary,
            routes=[OrderRoute(**x) for x in out],
            routed_by=routed_by,
        )
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return result


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


@router.get("/orders", response_model=Page[OrderRecord], responses=E)
async def list_orders(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=pagination.MAX_LIMIT),
    cursor: str | None = None,
    ctx: Ctx = Depends(owner_ctx),
) -> Page[OrderRecord]:
    """The owner's orders, newest first, with where each went (`?from&to`)."""
    after = pagination.decode(cursor, 2)
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT * FROM owner.orders
               WHERE (CAST(:f AS timestamptz) IS NULL OR created_at >= :f)
                 AND (CAST(:t AS timestamptz) IS NULL OR created_at < :t)
                 AND (CAST(:ca AS timestamptz) IS NULL
                      OR (created_at, id) < (CAST(:ca AS timestamptz), CAST(:cid AS uuid)))
               ORDER BY created_at DESC, id DESC LIMIT :lim""",
            f=from_,
            t=to,
            ca=after[0] if after else None,
            cid=after[1] if after else None,
            lim=limit + 1,
        )
    items, nxt = pagination.page(rows, limit, ("created_at", "id"))
    return Page(items=[_record(r) for r in items], next_cursor=nxt)
