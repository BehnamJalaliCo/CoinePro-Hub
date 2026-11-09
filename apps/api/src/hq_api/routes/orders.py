"""Voice orders (contract §17.4) and the holding's secretary (§29.4): POST
/orders/preview answers the `Route` an order would take (one line for the
owner to confirm or edit); POST /orders follows a given route exactly, or
lets the secretary decide (rules, its memory, then one light-model call,
then the advisor), and carries it out in one transaction: one root work in
the first company, one requested child work per collaborator, a council only
for an outside question or when the owner says so, an inside question to the
company's own Claude on its server. GET /orders lists them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator

from hq_api import idempotency, pagination, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import decisions as Dec
from hq_api.domain import dispatch as D
from hq_api.domain import humanize, recurrence
from hq_api.domain import links as LK
from hq_api.domain import orders as O
from hq_api.domain import players as PL
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
    """⟨1.9⟩ contract §27.3: a voice order whose phone recogniser was not
    available comes with its audio (`file_id`) and no text: the hub
    transcribes it (nothing leaves the hub)."""

    text: str = Field(default="", max_length=10000)
    source: Literal["voice", "text"] = "text"
    file_id: UUID | None = None
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    # ⟨1.11⟩ §29.4 the preview's route, possibly edited by the owner: followed exactly
    route: D.Route | None = None
    # ⟨2026-11-09⟩ §34.1 the owner's own answer to «با من یا خودکار؟», asked when the session is
    # made: it wins over the words (`step` «با من», `auto` «خودکار»); absent, the words decide
    pace: Literal["auto", "step"] | None = None

    @model_validator(mode="after")
    def _text_or_audio(self) -> OrderIn:
        if not self.text.strip() and not (self.source == "voice" and self.file_id):
            raise ValueError("text, or a voice order's audio (source voice, file_id)")
        return self


async def _hub_transcript(ctx: Ctx, file_id: UUID) -> str:
    """The order's audio as text: its stored transcript, else the hub's
    speech to text now (503 while it is off)."""
    async with ctx.tx() as tx:
        stored = await tx.first(
            """SELECT p.transcript, f.kind FROM files.files f
               LEFT JOIN files.processing p ON p.file_id = f.id WHERE f.id = :id""",
            id=file_id,
        )
    if stored is None:
        raise ApiError(422, "validation_failed", fields={"file_id": "unknown file"})
    if (stored["transcript"] or "").strip():
        return str(stored["transcript"])
    if not ctx.hub.settings.stt_url:
        raise ApiError(503, "channel_not_configured", "speech recognition is off on this hub")
    try:
        out = await workflows_client.transcribe(
            ctx.hub, str(file_id), ctx.hub.settings.transcribe_wait_s
        )
    except Exception as exc:
        raise ApiError(
            503, "channel_not_configured", "speech recognition is not available on this hub"
        ) from exc
    text = str(out.get("text") or "").strip()
    if not text:
        raise ApiError(422, "validation_failed", fields={"file_id": "no speech in the audio"})
    return text


class OrderRoute(BaseModel):
    company: str
    to: str
    kind: Literal["work", "code", "meeting", "question", "kit"]
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
    # ⟨1.11⟩ §29.4 the route it followed (the secretary's, or the owner's edit)
    route: D.Route | None = None
    # ⟨1.16⟩ §34.1 step by step with its holder, or carried to the end on its own
    pace: Literal["auto", "step"] = "auto"
    # ⟨1.16⟩ §34.2 a step order's live talk with its holder (CV-…), open at once
    talk_ref: str | None = None


class OrderRecord(OrderOut):
    text: str
    source: Literal["voice", "text"]
    file_id: UUID | None
    created_at: datetime


def _record(r: dict[str, Any]) -> OrderRecord:
    route = r.get("route")
    return OrderRecord(
        ref=r["ref"],
        summary_fa=r["summary_fa"],
        routes=[OrderRoute(**x) for x in r["routes"]],
        routed_by=r["routed_by"],
        route=D.Route.model_validate(route) if isinstance(route, dict) else None,
        pace=r.get("pace") or "auto",
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


@dataclass
class Secretary:
    """What the secretary decided for one order (before the transaction)."""

    route: D.Route
    draft: D.Draft
    routed_by: str
    sc: D.Context
    correction: dict[str, Any] | None = None
    # ⟨2026-11-09⟩ the owner's chosen pace (OrderIn.pace); None: read from the words (O.pace_of)
    pace: str | None = None


async def secretary(
    ctx: Ctx, text: str, hint: str | None, given: D.Route | None = None
) -> Secretary:
    """§29.4: the rules and the memory first; one light-model call (the
    worker's order_routing) only when the company or the department is still
    open; the advisor when nothing places it. A given route is followed
    exactly (checked against what exists) and, when it changes what the rules
    were sure of, remembered as the owner's correction. Outside any
    transaction (the model may take seconds)."""
    async with ctx.tx() as tx:
        sc = await D.context(tx, text)
    d = sc.directory
    dr = D.by_rules(text, d, hint, online=set(sc.online), memory=sc.memory)
    if given is not None:
        route = D.check_route(given.model_copy(deep=True), sc)
        route.collaborators = [c for c in route.collaborators if c != route.companies[0]]
        route.preview_fa = D.preview_line(route, d, sc.names)
        return Secretary(route, dr, "rules", sc, D.corrected(dr, route))
    if dr.open():
        answer = await workflows_client.route_order(ctx.hub, O.model_request(text, d))
        D.apply_model(dr, O.check_model({"routes": (answer or {}).get("routes")}, d), d)
    if dr.kind in ("work", "code", "meeting") and not dr.companies:
        if d.get("advisor") is None:
            raise ApiError(422, "validation_failed", fields={"text": "no route and no advisor"})
        dr.kind, dr.by, dr.mode = "question", "advisor", "single"
        dr.output_kind, dr.count = "answer", None
        dr.why = ["مسیر فرمان روشن نبود؛ مشاور هلدینگ کمک میکند که به کجا برود"]
        dr.confidence = D.confidence(dr)
    return Secretary(D.complete(dr, d, sc.names), dr, dr.by, sc)


class PreviewIn(Model):
    text: str = Field(min_length=1, max_length=10000)
    source: Literal["voice", "text"] = "text"
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")


@router.post("/orders/preview", response_model=D.Route, responses=E)
async def preview_order(body: PreviewIn, ctx: Ctx = Depends(owner_ctx)) -> D.Route:
    """⟨1.11⟩ §29.4 the secretary's route for an order, before it is sent:
    the companies (the first holds the root work), the department, the
    collaborators, the output and its count, the budget, single or council,
    the player and one plain line (`preview_fa`) with how sure it is and why.
    Nothing is stored; send it back (edited or not) as `route` of POST
    /orders and it is followed exactly."""
    s = await secretary(ctx, scrub(body.text), body.company)
    return await _along_links(ctx, s)


LINKED_WHY_FA = "شرکت‌های وصل‌شده به آن را کنارش پیشنهاد دادم"


async def _along_links(ctx: Ctx, s: Secretary) -> D.Route:
    """⟨1.17⟩ §35.6 the preview suggests collaborators along the `on` links of the order's company
    that fit its output (publishing -> `publishes`, a report -> `feeds`, sales, support, else
    `serves`). Only a suggestion: the route the owner sends back is followed exactly, and an order
    sent without a route is never widened."""
    r = s.route
    if r.kind != "work" or r.collaborators or len(r.companies) != 1:
        return r
    async with ctx.tx() as tx:
        codes = await LK.suggest(tx, r.companies[0], r.output_kind, r.department)
    if not codes:
        return r
    r = r.model_copy(deep=True)
    r.collaborators = codes
    r.preview_fa = D.preview_line(r, s.sc.directory, s.sc.names)
    r.why_fa = humanize.humanize("؛ ".join(x for x in (r.why_fa, LINKED_WHY_FA) if x))[:1000]
    return r


async def due_at(tx: Tx, text: str) -> datetime:
    """The end of the owner's day O.due_days(text) days from today: an order's
    work is in the planner (06.1 §2)."""
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    z = recurrence.zone(tz)
    day = datetime.now(z).date() + timedelta(days=O.due_days(text))
    return datetime.combine(day, time(23, 59), z).astimezone(UTC)


async def _work(
    ctx: Ctx,
    tx: Tx,
    r: O.Route,
    ref: str,
    text: str,
    title: str,
    *,
    meeting: bool = False,
    budget: int | None = None,
    player: str | None = None,
    mode: str | None = None,
    assignee: str | None = None,
    requested_by: UUID | None = None,
    pace: str | None = None,
) -> dict[str, Any]:
    co = await ctx.hub.companies.by_code(r.company)
    # ⟨1.16⟩ §34.1 the holder is told how the owner wants it carried out (step by step or to the
    # end): the owner's own choice when he made the session, else what the words say
    brief = f"{text}\n\n(فرمان {ref} مدیر کل)\n\n{O.pace_brief(ref, pace or O.pace_of(text))}"
    due = await due_at(tx, text)
    if player is None and mode is None:
        # ⟨1.9⟩ §27.1: «با جی‌پی‌تی / با جمنای / با دیپ‌سیک / شورا» in the order
        player, mode = PL.from_voice(text)
    common: dict[str, Any] = {
        "company_id": co.id,
        "company_code": co.code,
        "title": ("جلسه: " if meeting else "") + title,
        "brief": brief,
        "kind": "one_off",
        "priority": "P2",
        "due_at": due,
        "player": player,
        "mode": mode,
        # ⟨2026-11-08⟩ the owner: «کلا بودجه رو سقفشو بردار … همش برای یه کاری باید کار بخوابه»:
        # no token budget on a work of an owner's order (`budget` is the secretary's estimate for
        # the preview, never a cap; the charters' per-run limits still bound each run)
        "budget": None,
        "requested_by_work_id": requested_by,
    }
    try:
        w = await W.create(
            tx, ctx.who, department_code=r.department, assignee_code=assignee, **common
        )
    except ApiError:
        if r.department is None or assignee is not None:
            raise
        # The department has no active manager: the CEO receives it instead.
        r.note_fa = "این بخش مدیر فعالی نداشت؛ مدیرعامل شرکت دریافتش کرد"
        w = await W.create(tx, ctx.who, **common)
    if mode == "council":
        await PL.start_council(tx, ctx.hub, w)
    r.to = w["a_code"]
    r.refs["work_ref"] = w["ref"]
    await ctx.audit(
        tx,
        company_id=co.id,
        action="work.create",
        action_class="A2",
        target_kind="work",
        target_ref=w["ref"],
        summary=f"order {ref}: one_off P2 to {w['a_code']}, due {due:%Y-%m-%d}"
        + (f", requested by {requested_by}" if requested_by else ""),
    )
    return w


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


async def _advisor_work(
    ctx: Ctx, tx: Tx, r: O.Route, adv: dict[str, Any], ref: str, text: str, title: str
) -> None:
    """⟨1.17⟩ §35.1 a `question` single: the advisor's work is the order's root (its answer the
    deliverable), so the order has a holder and a session from the first second."""
    code = str(adv.get("code") or "")
    company = str(adv.get("company") or "")
    if not code or not company:
        return
    hr = O.Route(company, code, "work")
    try:
        w = await _work(ctx, tx, hr, ref, text, f"پرسش: {title}"[:300], assignee=code,
                        player="auto", mode="single")  # fmt: skip
    except ApiError:
        return  # the thread A message still carries the question
    r.refs["work_ref"] = w["ref"]


async def _code_holder(
    ctx: Ctx, tx: Tx, r: O.Route, s: Secretary, ref: str, text: str, title: str
) -> None:
    """⟨1.17⟩ §35.1 a `code` order: the company's technical manager (its CEO when there is none)
    holds the order beside the workshop session: a root work that follows the session, reports
    its steps and delivers when the session has."""
    first = r.company
    co = s.sc.directory["companies"][first]
    tech = co["managers"].get("TECH")
    code = tech or co["ceo"]
    if not code:
        return
    where = (
        f"سشن کارگاه کد {r.refs['session_ref']} کار کد را انجام میدهد"
        if r.refs.get("session_ref")
        else "سشن کارگاه کد پس از مُهر مدیر کل باز میشود"
        if r.refs.get("decision_ref")
        else "کارگاه کد هنوز باز نشده است"
    )
    hr = O.Route(first, code, "work", department="TECH" if tech else None)
    note = (
        f"{text}\n\nYou hold this order for the owner; the code itself is done in the Code "
        f"Workshop ({where}). Follow it, report each real step with order.progress, ask the owner "
        "only what the workshop cannot decide, and deliver when the workshop has delivered."
    )
    try:
        w = await _work(ctx, tx, hr, ref, note, f"پیگیری کد: {title}"[:300], assignee=code,
                        player="auto", mode="single", pace=s.pace)  # fmt: skip
    except ApiError:
        return
    r.refs["work_ref"] = w["ref"]


async def _code(
    ctx: Ctx,
    tx: Tx,
    r: O.Route,
    ref: str,
    text: str,
    title: str,
    later: list[Any],
    routed_by: str = "rules",
) -> None:
    ws = await WS.workspace(tx, r.workspace or r.to)
    rt = getattr(ctx.hub, "workshop", None)
    # A route the model found acts on its own only when a rule agrees (06.1 §3).
    auto = routed_by == "rules" or O.rule_confirms_code(text)
    running = await tx.first(
        WS.SESSION_SQL
        + """ WHERE s.workspace_id = :ws AND s.state = ANY(:active) AND s.held IS NULL
              AND s.external_id IS NOT NULL
              ORDER BY s.updated_at DESC LIMIT 1""",
        ws=ws["id"],
        active=list(WS.ACTIVE),
    )
    if not auto:
        r.note_fa = "کار کد را مدل تشخیص داد و هیچ قاعده‌ای تأییدش نکرد؛ سشن خودکار باز نشد و منتظر مهر مدیر کل است"
        running = grant = None
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
    if auto:
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
            why=f"فرمان {ref} مدیر کل؛ برای این workspace مجوز فعالی نیست."
            if auto
            else f"فرمان {ref} مدیر کل؛ مسیر کد را مدل یافت و قاعده‌ای تأییدش نکرد.",
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


async def _server(
    ctx: Ctx, tx: Tx, rt: D.Route, sc: D.Context, ref: str, text: str, title: str
) -> O.Route:
    """§29.8 an inside question: a work for the company's CTO (its CEO when
    there is none) answered by the company's own Claude on its server, a
    capped claude job; the CTO's own run makes no model call meanwhile."""
    code = rt.companies[0]
    co = sc.directory["companies"][code]
    tech = co["managers"].get("TECH")
    r = O.Route(code, tech or co["ceo"] or "", "work", department="TECH" if tech else None)
    w = await _work(ctx, tx, r, ref, text, title, budget=rt.budget_tokens, player="auto",
                    mode="single")  # fmt: skip
    job = await D.ask_server(tx, ctx.hub, w, sc.online[code], text, rt.budget_tokens)
    r.note_fa = "پاسخ را Claude سرور خود شرکت از روی داده‌ی واقعی میدهد"
    await W.event(
        tx, w, "server_job", ctx.who, {"job": str(job["id"]), "server": job["server_name"]}
    )
    return r


async def carry_out(
    ctx: Ctx, tx: Tx, s: Secretary, ref: str, text: str, later: list[Any]
) -> list[O.Route]:
    """The route, in the order's transaction: what each company receives."""
    rt, d = s.route, s.sc.directory
    title = " ".join(text.split())[:80] or ref
    first = rt.companies[0]
    co = d["companies"][first]
    if rt.kind == "kit":
        # §31.2 a new company is only drafted: the order report holds the kit
        # card, no work item exists, nothing is created before the owner seals
        return [O.Route(first, rt.kit or "", "kit", summary_fa=rt.preview_fa)]
    if rt.kind == "server":
        return [await _server(ctx, tx, rt, s.sc, ref, text, title)]
    if rt.kind == "question" and rt.mode == "single":
        adv = d.get("advisor") or {}
        r = O.Route(first, adv.get("code") or "", "question")
        await _question(ctx, tx, r, ref, text, s.routed_by)
        await _advisor_work(ctx, tx, r, adv, ref, text, title)
        return [r]
    if rt.kind == "question":
        # §29.8 an outside question: the council v2, captained by the company's
        # CEO (the holding has none: its advisor)
        adv = d.get("advisor") or {}
        lead = co["ceo"] or (adv.get("code") if adv.get("company") == first else None)
        if lead is None:
            raise ApiError(422, "validation_failed", fields={"route": "nobody leads the council"})
        r = O.Route(first, lead, "work")
        await _work(ctx, tx, r, ref, text, title, budget=rt.budget_tokens, player=rt.player,
                    mode="council", assignee=lead, pace=s.pace)  # fmt: skip
        return [r]
    if rt.kind == "code" and co["workspaces"]:
        ws = str(
            s.draft.workspace if s.draft.workspace in co["workspaces"] else co["workspaces"][0]
        )
        r = O.Route(first, ws, "code", workspace=ws)
        await _code(ctx, tx, r, ref, text, title, later, s.routed_by)
        await _code_holder(ctx, tx, r, s, ref, text, title)
        return [r]
    dept = rt.department if rt.kind != "meeting" else None
    if rt.kind == "code":  # no workspace: the company's technical manager
        dept = "TECH" if "TECH" in (s.sc.names.get(first) or {}) else None
    kind = "meeting" if rt.kind == "meeting" else "work"
    root = O.Route(first, co["ceo"] or "", kind, department=dept)
    try:
        w = await _work(ctx, tx, root, ref, text, title, meeting=kind == "meeting",
                        budget=rt.budget_tokens, player=rt.player, mode=rt.mode,
                        pace=s.pace)  # fmt: skip
    except ApiError as exc:
        if exc.status != 422 or co["ceo"]:
            raise
        # ⟨1.17⟩ §35.1 nobody in the company can take it: the order is still recorded, the
        # secretary holds it and proposes the hire in its session (never ownerless)
        root.note_fa = (
            "این شرکت مدیری ندارد؛ منشی هلدینگ فرمان را نگه داشت و استخدام را پیشنهاد میکند"
        )
        return [root]
    out = [root]
    for c in dict.fromkeys([*rt.companies[1:], *rt.collaborators]):
        if c == first:
            continue
        cdept = rt.department if rt.department in (s.sc.names.get(c) or {}) else None
        child = O.Route(c, d["companies"][c]["ceo"] or "", "work", department=cdept)
        await _work(ctx, tx, child, ref, text, f"همکاری با {co['name_fa'] or first}: {title}"[:300],
                    player=rt.player, mode="single", requested_by=w["id"], pace=s.pace)  # fmt: skip
        out.append(child)
    return out


@router.post("/orders", response_model=OrderOut, status_code=201, responses=E)
async def create_order(
    body: OrderIn, request: Request, background: BackgroundTasks, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """Routes an order of the owner (typed, or from `/transcribe`). ⟨1.11⟩
    §29.4 with `route` (the preview's, possibly edited) it is followed
    exactly, and a change of what the secretary was sure of is remembered;
    without, the secretary decides: its memory and the rules (company,
    department by title or by the output it owns, output and count, inside
    or outside question), then the light model only when the company or the
    department is still open, then the advisor. work -> one root work in the
    first company (its department's manager, or the CEO) and one requested
    work per collaborator; code -> a running session of the workspace, else
    a new session under a live grant, else a `code_session` decision;
    question -> the advisor (thread A); an outside question or «شورا» -> the
    council; an inside question -> the company's own Claude on its server
    (a capped job); meeting -> a work item for the CEO. What agents and
    models read is masked. Requires `Idempotency-Key`."""
    return await place_order(ctx, request, background, body)


async def place_order(
    ctx: Ctx,
    request: Request,
    background: BackgroundTasks,
    body: OrderIn,
    *,
    remember: bool = True,
) -> Any:
    """One order, end to end (POST /orders, and «اجرا کن» of a council's
    plan with `remember=False`: a route the hub wrote is no correction)."""
    raw = body.text if body.text.strip() else await _hub_transcript(ctx, body.file_id)  # type: ignore[arg-type]
    text = scrub(raw)
    seen = await _seen(ctx, request)
    s = None if seen else await secretary(ctx, text, body.company, body.route)
    if s is not None:
        s.pace = body.pace
    later: list[Any] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        if s is None:  # the first request's key expired this very moment: send it again
            raise ApiError(409, "idempotency_conflict", "retry with a new Idempotency-Key")
        if body.file_id and not await tx.scalar(
            "SELECT 1 FROM files.files WHERE id = :id", id=body.file_id
        ):
            raise ApiError(422, "validation_failed", fields={"file_id": "unknown file"})
        result = await record_order(
            ctx, tx, s, text, later, source=body.source, file_id=body.file_id,
            hint=body.company, remember=remember, edited=body.route is not None,
        )  # fmt: skip
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return result


async def record_order(
    ctx: Ctx,
    tx: Tx,
    s: Secretary,
    text: str,
    later: list[Any],
    *,
    source: str,
    file_id: UUID | None = None,
    hint: str | None = None,
    remember: bool = True,
    edited: bool = False,
) -> OrderOut:
    """One routed order, in the caller's transaction: its F-ref, the works
    its route makes, the record, the stream, the Audit and the order report.
    POST /orders and a talk card («اجرا کن», contract §32.3) share it."""
    ref: str = await tx.scalar("SELECT 'F-' || lpad(nextval('owner.order_ref_seq')::text, 4, '0')")
    routes = await carry_out(ctx, tx, s, ref, text, later)
    routed_by = s.routed_by
    holding = await ctx.hub.companies.holding()
    out = [r.out() for r in routes]
    summary = O.summary_of(text, routes, await _names(tx, routes))
    pace = s.pace or O.pace_of(text)
    await tx.exec(
        """INSERT INTO owner.orders (ref, company_id, text, source, file_id, company_hint,
               routes, routed_by, summary_fa, route, pace)
           VALUES (:ref, :co, :text, :src, :fid, :hint, CAST(:routes AS jsonb), :by, :sum,
                   CAST(:route AS jsonb), :pace)""",
        pace=pace,
        ref=ref,
        co=holding.id,
        text=text,
        src=source,
        fid=file_id,
        hint=hint,
        routes=_json(out),
        by=routed_by,
        sum=summary[:2000],
        route=_json(s.route.model_dump(mode="json")),
    )
    if s.correction is not None and remember:
        await D.remember(tx, "correction", text, s.correction, order_ref=ref)
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
    if out:  # ⟨1.24⟩ §42.2 the order leaves the hub for its holder's company
        from hq_api.domain import live as LV

        to = str(out[0]["company"])
        await LV.flow(tx, src="hub", dst=to, kind="order", ref=ref, root_ref=out[0].get("work_ref"),
                      label_fa=f"فرمان مدیر کل به {await LV.name_of(tx, to)}")  # fmt: skip
    await ctx.audit(
        tx,
        company_id=holding.id,
        action="order.route",
        action_class="A2",
        target_kind="order",
        target_ref=ref,
        summary=f"{routed_by}: "
        + ", ".join(f"{x['kind']}->{x['to']}" for x in out)
        + (" (the owner's route)" if edited else ""),
    )
    await ctx.interaction(
        tx,
        company_id=holding.id,
        kind="order",
        action="order.create",
        target_kind="order",
        target_ref=ref,
        data={
            "source": source,
            "routes": len(out),
            "routed_by": routed_by,
            "edited": s.correction is not None and remember,
        },
    )
    await _report(tx, ref)
    # ⟨1.17⟩ §35.1 every order is a session: its live talk with its holder (the secretary when
    # nobody holds it) is open at once, whatever the pace and the kind
    from hq_api.domain import order_turns as OT

    talk_ref = await OT.open_talk(ctx, tx, ref)
    return OrderOut(
        ref=ref,
        summary_fa=summary,
        routes=[OrderRoute(**x) for x in out],
        routed_by=routed_by,
        route=s.route,
        pace=pace,
        talk_ref=talk_ref,
    )


async def _report(tx: Tx, ref: str) -> None:
    """§29.2 the order report hears of every routed order (the secretary's
    receipt: «دریافت شد؛ به … سپرده شد»)."""
    from hq_api.domain import order_report

    await order_report.on_order_routed(tx, ref)


async def _names(tx: Tx, routes: list[O.Route]) -> dict[str, str]:
    """⟨1.17⟩ W6 i: the owner reads plain names in `summary_fa`, never employee or workspace
    codes: {route.to: its name}."""
    codes = [r.to for r in routes if r.to]
    if not codes:
        return {}
    out: dict[str, str] = {}
    for e in await tx.all(
        """SELECT e.code, e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = ANY(:c)""",
        c=codes,
    ):
        title = (e["title_fa"] or "").strip() or "کارمند"
        out[e["code"]] = f"{title} {e['company_fa']}".strip() if e["company_fa"] else title
    for w in await tx.all(
        "SELECT code, title_fa FROM workshop.workspaces WHERE code = ANY(:c)", c=codes
    ):
        out.setdefault(w["code"], f"کارگاه کد {w['title_fa'] or w['code']}")
    for r in routes:
        if r.kind == "kit":
            out.setdefault(r.to, "پیش‌نمایش شرکت تازه")
    return out


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
