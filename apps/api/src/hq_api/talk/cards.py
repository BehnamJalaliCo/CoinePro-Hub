"""Work comes out of talk only through a card the owner taps (contract §32,
§32.3, §32.4). A card runs the EXISTING route of its kind, with that route's
own checks, confirmations and step-ups; talk never makes work by itself:

    order       the dispatcher (§29.4: secretary() then record_order), the
                route preset to a manager's company/department
    ask         the same, as an order for an answer (output_kind `answer`);
                the deliverable comes back into the conversation as a turn of
                the persona («جواب آمد») with a notification (on_outputs,
                called where the order report records outputs)
    minutes     «اجرا کن»: one order per task through the dispatcher, in one
                transaction, each linked to the conversation (CV-…)
    hire        the manager's hiring proposal (§18.11): a `hire` decision it
                proposes, decided as usual (hiring closed: 403 hiring_closed)
    decision    a `proposal` card for the owner's cartable (§20)
    planner     an item in the owner's planner (§18.3)
    rule        POST /rules (§29.3): a proposed rule, sealed later 🔏
    automation  §31.7: one compile, then a `proposed` automation (sealed later 🔏)
    invite      the manager joins the conversation (§32.4); ⟨2026-11-06⟩ `{player}` in a session:
                ChatGPT, Gemini or DeepSeek joins it (sessions.add_participant)

⟨1.17⟩ §35.4 in a session (a talk bound to an order) the cards run the order's own routes and
every result is a step of the order (its report refreshed, so it streams):
    order       the owner's next word on THAT order (§34.3 reply), never a new order
    hire        any persona, the company explicit: the seat filled by code (§29.10 auto hiring)
    delegate    {to, text}: a child work of the order's root for that employee / department / role
    budget      {tokens}: more tokens for the order's root work (§29.6)
    group       {company, group}: the company joins the working group (§29.11)
    line        {company, template}: a production line from a template (§30), its own seal
A closed session runs no card (409).

⟨2026-11-07⟩ W9 B: inside a session NO card makes a new order (the owner: «همش اینور و اونور … این
بروکراسی اداری چیه»; his «go find why» had become two new orders to the advisor):
    ask         the asked person joins THIS session and the question is a child work of this order
                assigned to them (the holder's company: under the root; another company or the
                holding's advisor: a work requested by the root, in the order's tree); its answer
                comes back as that person's turn here («جواب آمد»)
    minutes     its tasks are child works of this order (a department named: its manager; another
                company: its CEO, requested by the root), else plan tasks of the session
    the rest    keep their effect; the result is one short line in the session (a step and a turn)

A card that fails stays visible as `failed` with its plain reason, and may be
run again (with the owner's edits). Running a done card answers what it made.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Request
from pydantic import BaseModel, ValidationError

from hq_api import events, workflows_client
from hq_api.context import Ctx
from hq_api.db import Tx
from hq_api.domain import decisions as Dec
from hq_api.domain import errands as ER
from hq_api.domain import notify
from hq_api.errors import CODES, ApiError
from hq_api.principal import Principal
from hq_api.talk import data, personas, store
from hq_api.talk.personas import Persona
from hq_api.talk.scrub import clean

log = logging.getLogger("hq_api.talk.cards")
TALK = Principal(kind="service", code="talk", role="service")
DEPT = r"^[A-Z][A-Z0-9]{1,11}$"
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
EMP = r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
OWNER_FA = "مدیر کل"
LABEL_FA = {
    "order": "فرمان", "ask": "پرسش", "hire": "استخدام", "decision": "کارت تصمیم", "planner": "یادآوری",
    "rule": "قاعده", "automation": "خودکارسازی", "minutes": "صورت‌جلسه", "invite": "دعوت",
    "delegate": "سپردن کار", "budget": "بودجه", "group": "کارگروه", "line": "خط تولید",
    "playbook": "کارگروه از جلسه",
}  # fmt: skip
CLOSED_FA = "این جلسه بسته شده است؛ برای ادامه آن را دوباره باز کن."


def _fail(why: str, field: str = "payload") -> ApiError:
    return ApiError(422, "validation_failed", fields={field: why[:200]}, message_fa=why)


def sub_request(request: Request, i: int, body: dict[str, Any]) -> Request:
    """The request a card's route sees: its own Idempotency-Key derived from the
    card run's (so a retried run replays each step instead of doing it twice)
    and its own body."""
    raw = request.headers.get("idempotency-key") or ""
    try:
        base = UUID(raw)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", fields={"Idempotency-Key": "required"}) from exc
    key = uuid.uuid5(base, f"talk-card-step-{i}")
    headers = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"idempotency-key"]
    headers.append((b"idempotency-key", str(key).encode()))
    payload = json.dumps(body, ensure_ascii=False, default=str).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request({**request.scope, "headers": headers}, receive)


async def persona_of_card(
    tx: Tx, hub: Any, card: dict[str, Any], conv: dict[str, Any] | None = None
) -> Persona:
    key = await tx.scalar("SELECT persona FROM talk.turns WHERE id = :t", t=card["turn_id"])
    return await personas.resolve_in(tx, hub, str(key or "secretary"), conv, store_voice=False)


def proposer(p: Persona) -> Principal:
    """The persona as the proposer of its cards (the manager proposes its hire)."""
    emp = p.employee
    if emp is None or emp.get("status") != "active":
        return TALK
    return Principal(
        kind="agent",
        code=str(emp["code"]),
        role=str(emp["kind"]),
        company=p.company,
        company_id=p.company_id,
        department=emp.get("department"),
        employee_id=emp["id"],
        status=emp["status"],
        charter=p.role,
        scope="company" if p.is_manager else "holding",
    )


# ----------------------------------------------------------------- orders --
async def _route(
    ctx: Ctx, text: str, company: str | None, department: str | None, *, answer: bool
) -> Any:
    """The dispatcher's decision for one order of a card (outside a transaction:
    the light model may be asked)."""
    from hq_api.routes.orders import secretary

    s = await secretary(ctx, text, company)
    if company and company in s.sc.directory["companies"] and s.route.kind in ("work", "meeting"):
        s.route.companies = [company, *[c for c in s.route.companies if c != company]]
        if department and department in (s.sc.names.get(company) or {}):
            s.route.department = department
    if answer:
        s.route.output_kind = "answer"
    return s


async def _orders(
    ctx: Ctx, items: list[dict[str, Any]], ref: str, *, answer: bool
) -> tuple[list[str], list[Any]]:
    from hq_api.routes.orders import record_order

    decided = []
    for it in items:
        text = clean(" ".join(str(it.get("text") or "").split()))[0]
        if len(text) < 2:
            raise _fail("متن فرمان خالی است.")
        if it.get("due"):
            text += f" (تا {it['due']})"
        text += f"\n\n(از گفتگوی {ref})"
        co = it.get("company") if isinstance(it.get("company"), str) else None
        dept = it.get("department") if isinstance(it.get("department"), str) else None
        decided.append((text, co, await _route(ctx, text, co, dept, answer=answer)))
    later: list[Any] = []
    made: list[str] = []
    async with ctx.tx() as tx:
        for text, co, s in decided:
            out = await record_order(
                ctx, tx, s, text, later, source="text", hint=co, remember=False
            )
            made.append(out.ref)
    return made, later


# ------------------------------------------------------------------- run --
RUNNING_FA = "این کارت در حال اجراست؛ کمی بعد دوباره نگاه کنید."


async def run(
    ctx: Ctx,
    request: Request,
    background: BackgroundTasks,
    card_id: UUID,
    edits: dict[str, Any] | None,
) -> store.TalkCardRun:
    """One run of a card at a time (audit 2026-11-11: a doubled tap, or a second device, ran an
    order card twice: two orders, two agent runs). The card's steps commit in their own
    transactions, so the guard is a transaction-scoped advisory lock held on its own connection
    for the whole run; it is released when the run ends, also on a crash. A second run while the
    first is still going is refused (409); once the first is done, a run answers what it made."""
    async with ctx.hub.db.raw() as guard:
        locked = await guard.scalar(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(:k, 0))", k=f"talk.card:{card_id}"
        )
        if not locked:
            raise ApiError(409, "validation_failed", "the card is running", message_fa=RUNNING_FA)
        return await _run(ctx, request, background, card_id, edits)


async def _run(
    ctx: Ctx,
    request: Request,
    background: BackgroundTasks,
    card_id: UUID,
    edits: dict[str, Any] | None,
) -> store.TalkCardRun:
    async with ctx.tx() as tx:
        card = await tx.first("SELECT * FROM talk.cards WHERE id = :id", id=card_id)
        if card is None:
            raise ApiError(404, "not_found", "unknown card", message_fa="این کارت پیدا نشد.")
        card = dict(card)
        if card["state"] == "done":
            return store.TalkCardRun(made=list(card["made"]), card=store.render_card(card))
        if card["state"] == "dismissed":
            raise ApiError(409, "validation_failed", "the card was dismissed",
                           message_fa="این کارت کنار گذاشته شده است.")  # fmt: skip
        conv = dict(
            await tx.one(
                "SELECT * FROM talk.conversations WHERE id = :c", c=card["conversation_id"]
            )
        )
        if conv.get("closed_at") is not None:
            raise ApiError(409, "validation_failed", "the session is closed", message_fa=CLOSED_FA)
        p = await persona_of_card(tx, ctx.hub, card, conv)
    payload = {**(store._j(card["payload"]) or {}), **(edits or {})}
    payload = json.loads(clean(json.dumps(payload, ensure_ascii=False, default=str))[0])
    later: list[Any] = []
    note: list[str] = []  # ⟨2026-11-07⟩ the one line the session shows for what the card made
    try:
        made, later = await _carry_out(ctx, request, card, conv, p, payload, note)
    except ApiError as exc:
        why = exc.message_fa or CODES.get(exc.code, CODES["internal_error"])[2]
        await _mark(ctx, card, "failed", [], why, payload)
        await _order_step(ctx, conv, card, payload, why)
        raise
    except Exception:
        # audit 2026-11-11: any other fault (a bad number in the payload, a database or router
        # error) also leaves the card `failed` with its plain reason (§32), never `offered`
        why = CODES["internal_error"][2]
        try:
            await _mark(ctx, card, "failed", [], why, payload)
            await _order_step(ctx, conv, card, payload, why)
        except Exception:
            log.exception("talk card %s: could not mark it failed", card["id"])
        raise
    row = await _mark(ctx, card, "done", made, None, payload)
    await _order_step(ctx, conv, card, payload, None, note[0] if note else None)
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return store.TalkCardRun(made=made, card=store.render_card(row))


async def _mark(
    ctx: Ctx,
    card: dict[str, Any],
    state: str,
    made: list[str],
    reason: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    async with ctx.tx() as tx:
        row = await tx.one(
            """UPDATE talk.cards SET state = :st, made = CAST(:m AS text[]), reason_fa = :r,
                   payload = CAST(:p AS jsonb), updated_at = now()
               WHERE id = :id RETURNING *""",
            st=state,
            m=made[:50],
            r=(reason or None) and str(reason)[:500],
            p=json.dumps(payload, ensure_ascii=False, default=str),
            id=card["id"],
        )
        holding = await ctx.hub.companies.holding()
        ref = await tx.scalar(
            "SELECT ref FROM talk.conversations WHERE id = :c", c=card["conversation_id"]
        )
        await events.emit(tx, holding.code, "talk.card", ref,
                          {"card": str(card["id"]), "kind": card["kind"], "state": state, "made": made})  # fmt: skip
        await ctx.audit(
            tx,
            company_id=card["company_id"],
            action="talk.card",
            action_class="A0" if state == "failed" else "A1",
            target_kind="talk_card",
            target_ref=str(card["id"]),
            summary=f"{card['kind']} {state}" + (f": {', '.join(made)}" if made else ""),
        )
        return dict(row)


async def _order_step(
    ctx: Ctx,
    conv: dict[str, Any],
    card: dict[str, Any],
    payload: dict[str, Any],
    why: str | None,
    line: str | None = None,
) -> None:
    """⟨1.17⟩ §35.4 what a card made (or why it did not) is a step of the session's order, and
    the report is refreshed so `order.report` streams. The bound `order` card is the reply itself
    (its own step): only the refresh. ⟨2026-11-07⟩ W9 B: what a card made is also one short line
    in the session's talk (the holder's turn, by code), so the owner reads it where he is."""
    ref = conv.get("order_ref")
    if not ref:
        return
    from hq_api.domain import order_report as OR
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE

    async with ctx.tx() as tx:
        if card["kind"] == "order":
            await OR.refresh(tx, str(ref))
            return
        label = LABEL_FA.get(card["kind"], card["kind"])
        title = str(payload.get("title_fa") or payload.get("text") or card["title_fa"])[:200]
        done = line or f"{label} انجام شد: {title}"
        what = f"{label} انجام نشد: {why}" if why is not None else done
        # ⟨1.22⟩ §40.1 a card done is one line of the session's memory (a failed one is not)
        await SE.step(tx, str(ref), OWNER_FA, what, remember_line=done if why is None else None)
        if why is None and card["kind"] != "invite":  # an invite writes its own «آمد» line
            locked = await store.conversation(tx, conv["ref"], lock=True)
            said = clean(what)[0][:400]
            await OT.post_turn(tx, locked, OT.holder_key(locked), said, said)


async def _carry_out(
    ctx: Ctx,
    request: Request,
    card: dict[str, Any],
    conv: dict[str, Any],
    p: Persona,
    payload: dict[str, Any],
    note: list[str] | None = None,
) -> tuple[list[str], list[Any]]:
    kind, ref = card["kind"], conv["ref"]
    text = str(payload.get("text") or card["body_fa"] or card["title_fa"])
    note = [] if note is None else note
    if conv.get("order_ref") and kind == "ask":
        # ⟨2026-11-07⟩ W9 B: never a new order from inside a session
        return await _session_ask(ctx, conv, p, payload, text, note, card=card)
    if conv.get("order_ref") and kind == "minutes":
        return await _session_minutes(ctx, conv, payload, note)
    if kind == "order" and conv.get("order_ref"):
        # ⟨1.16⟩ §34.2 a talk bound to an order: the owner's word goes onto that same order
        from hq_api.domain import order_turns as OT

        async with ctx.tx() as tx:
            out = await OT.reply(tx, str(conv["order_ref"]), text)
            woken = ", ".join(out["woken"]) or "nothing"
            await ctx.audit(tx, company_id=card["company_id"], action="order.reply",
                            action_class="A1", target_kind="order", target_ref=conv["order_ref"],
                            summary=f"the owner's word from {ref}; woken: {woken}")  # fmt: skip
        return [str(conv["order_ref"])], []
    if kind in data.SESSION_CARDS:
        return await _session_card(ctx, request, card, conv, payload, text, note)
    if kind in ("order", "ask"):
        if p.consult_only and kind == "order":
            raise _fail("این نقش فقط مشورت میدهد و فرمان نمیسازد.", "kind")
        item = {
            "text": text,
            "company": payload.get("company"),
            "department": payload.get("department"),
        }
        if p.is_manager:  # §32.4: the route is preset to the manager's company/department
            item["company"] = p.company
            item["department"] = payload.get("department") or (p.employee or {}).get("department")
        return await _orders(ctx, [item], ref, answer=kind == "ask")
    if kind == "minutes":
        tasks = [t for t in payload.get("tasks") or [] if isinstance(t, dict)]
        if not tasks:
            raise _fail("صورت‌جلسه کاری برای اجرا ندارد.", "payload.tasks")
        items = [{"text": t.get("title_fa"), "company": t.get("company"),
                  "department": t.get("department"), "due": t.get("due")} for t in tasks]  # fmt: skip
        return await _orders(ctx, items, ref, answer=False)
    if kind == "invite" and payload.get("player") is not None:
        return await _invite_player(ctx, conv, payload)
    if kind == "invite":
        async with ctx.tx() as tx:
            key = await personas.invite_key(tx, ctx.hub, str(payload.get("role") or ""),
                                            str(payload.get("company") or ""))  # fmt: skip
            mp = await personas.resolve(tx, ctx.hub, key)
            locked = await store.conversation(tx, ref, lock=True)
            await join_with_notice(tx, ctx.hub, locked, mp)
        return [key], []
    if kind == "planner":
        try:
            at = datetime.fromisoformat(str(payload.get("at") or ""))
            if at.tzinfo is None:  # audit 2026-11-11: a time without an offset is the owner's
                from hq_api.domain.gov_common import owner_tz, zone

                async with ctx.tx() as tx:
                    at = at.replace(tzinfo=zone(await owner_tz(tx)))
            body = ER.PlannerIn(title_fa=str(payload.get("title_fa") or card["title_fa"])[:200], at=at,
                                note=(str(payload.get("note"))[:2000] if payload.get("note") else None))  # fmt: skip
        except (ValueError, ValidationError) as exc:
            raise _fail("زمان یادآوری روشن نیست.", "payload.at") from exc
        async with ctx.tx() as tx:
            holding = await ctx.hub.companies.holding()
            row = await ER.add_planner_item(tx, ctx.who, holding.id, body)
            await ctx.audit(tx, company_id=holding.id, action="planner.add", action_class="A1",
                            target_kind="planner", target_ref=row["ref"], summary=f"from {ref}")  # fmt: skip
        return [row["ref"]], []
    if kind == "rule":
        from hq_api.routes.rules import RuleIn, add_rule

        out = await add_rule(RuleIn(text=text), sub_request(request, 0, {"text": text}), ctx)
        return [_ref_of(out)], []
    if kind == "automation":
        from hq_api.domain import automations as AU
        from hq_api.routes.automations import AutomationIn, add_automation

        sentence = str(payload.get("sentence_fa") or text)[:1000]
        company = payload.get("company") if isinstance(payload.get("company"), str) else None
        company = company or p.company_code  # ⟨2026-11-06⟩ a manager's: its own company
        # ⟨2026-11-07⟩ the proposer's department: its manager takes a work for a role nobody holds
        compiled = await AU.compile_sentence(
            ctx.hub, sentence, company, department=(p.employee or {}).get("department")
        )
        if compiled.rule is None:
            raise _fail(
                compiled.refused_fa[0] if compiled.refused_fa else "این جمله به قاعده تبدیل نشد."
            )
        auto = {"rule": compiled.rule, "sentence_fa": sentence, "company": company}
        out = await add_automation(AutomationIn(**auto), sub_request(request, 0, auto), ctx)
        # ⟨2026-11-07⟩ the one line of the session: what was set up, and what code changed
        changed = [x for x in (compiled.preview_fa or "").split("\n") if x.startswith("کسی با نقش")]
        title = str(payload.get("title_fa") or card["title_fa"])[:120]
        note.append(" ".join([f"خودکارسازی ثبت شد: {title}؛ تا مُهر تو اجرا نمیشود.", *changed]))
        return [_ref_of(out)], []
    if kind in ("decision", "hire"):
        return await _decision(ctx, card, p, payload, text)
    raise _fail("این نوع کارت شناخته نیست.", "kind")


def _ref_of(out: Any) -> str:
    if isinstance(out, BaseModel):
        return str(out.ref)  # type: ignore[attr-defined]
    body = json.loads(bytes(out.body)) if hasattr(out, "body") else {}  # an idempotent replay
    return str(body.get("ref"))


# ----------------------------------------------- the session: ask and minutes (W9 B) --
HOLDING_FIXED = ("advisor", "overseer", "assistant")


async def _holding_fixed(tx: Tx, role: str) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT e.code, e.role, e.title_fa, c.id AS company_id, c.code AS company, c.kind AS company_kind,
                  c.name_fa AS company_fa
           FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.role = :r AND e.status = 'active' ORDER BY e.hired_at LIMIT 1""",
        r=role,
    )


async def _employee_row(tx: Tx, code: str) -> dict[str, Any]:
    return dict(
        await tx.one(
            """SELECT e.code, e.role, e.title_fa, c.id AS company_id, c.code AS company,
                      c.kind AS company_kind, c.name_fa AS company_fa
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
            c=code,
        )
    )


async def _named_company(
    ctx: Ctx, tx: Tx, parent: dict[str, Any], text: str, memory: str | None
) -> str | None:
    """⟨2026-11-08⟩ audit M3 (the owner met Pro-Chart's CTO when he meant IG-Hub's): the company
    a card's words point at when none is named — a company of the holding by code or name, or a
    paired server's name (its company) — in the card's text first, then in the session's memory
    («تا اینجا»). None when nothing points elsewhere (the holder's company then)."""
    from hq_api.domain import orders as O

    d = await O.directory(tx)
    servers = await tx.all(
        """SELECT s.name, c.code FROM infra.servers s JOIN core.companies c ON c.id = s.company_id
           WHERE c.kind = 'company' AND c.status = 'active' AND (s.state IS NULL OR s.state <> 'revoked')
           ORDER BY length(s.name) DESC"""
    )
    for source, companies_too in ((text, True), (memory or "", False)):
        # (the memory names every company whose person joined: only a server named there points
        # anywhere; the card's own words may name a company)
        if not source:
            continue
        if companies_too:
            norm = O.normalise(source)
            named = [c for c in O.companies_named(norm, d) if not d["companies"][c].get("holding")]
            named = [c for c in named if c != parent["company"]]
            if len(named) > 1:
                # several match (a short name inside a longer one): a code written out wins, then
                # the one whose matching name is the longest
                by_code = [c for c in named if O.has(norm, c)]
                if len(by_code) == 1:
                    return str(by_code[0])

                def longest(code: str, norm: str = norm) -> int:
                    c = d["companies"][code]
                    names = [c.get("name_fa") or "", c.get("name_en") or ""]
                    return max(
                        (len(O.normalise(n)) for n in names if n and O.has(norm, n)), default=0
                    )

                ranked = sorted(named, key=longest, reverse=True)
                if longest(ranked[0]) > longest(ranked[1]):
                    return str(ranked[0])
            if len(named) == 1:
                return str(named[0])
        low = source.lower()
        hits = [
            str(s["code"])
            for s in servers
            if re.search(
                rf"(?<![A-Za-z0-9_.-]){re.escape(str(s['name']).lower())}(?![A-Za-z0-9_.-])", low
            )
        ]
        hits = [h for h in dict.fromkeys(hits) if h != parent["company"]]
        if len(hits) == 1:
            return hits[0]
    return None


async def _asked(
    ctx: Ctx,
    tx: Tx,
    parent: dict[str, Any],
    to: str,
    company: str | None,
    *,
    text: str = "",
    memory: str | None = None,
) -> dict[str, Any]:
    """Who a session's `ask` is for: a fixed persona of the holding by name; a person of another
    company named (`company`: an employee code, a department's manager, a role, else its CEO); a
    person of the holder's company (code, department, role); nobody named: the holding's advisor.
    ⟨2026-11-08⟩ (the owner: «رفت یکی رو از یه شرکت دیگه آورد که اصلا نمیدونست توی شرکتش چه خبره»)
    a full employee code (`IG-CTO`) names that very person and so their company, whatever company
    the card says — a card that names a different company is refused in one line, never answered
    by the wrong company's person; a role is matched whatever its case (`CTO`, `cto`)."""
    to = (to or "").strip()
    if to.lower() in HOLDING_FIXED or (not to and not company):
        row = await _holding_fixed(tx, to.lower() or "advisor")
        if row is None:
            raise _fail("مشاور کل در هلدینگ نیست.", "payload.to")
        return dict(row)
    if re.fullmatch(EMP, to):
        row = await tx.first(
            """SELECT e.code, c.code AS company FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id
               WHERE e.code = :c AND e.status = 'active' AND e.kind <> 'system'""",
            c=to,
        )
        if row is not None:
            if company and company != row["company"]:
                raise _fail(
                    f"{to} در شرکت {row['company']} است، نه {company}؛ یکی از این دو را بگو.",
                    "payload.company",
                )
            return await _employee_row(tx, str(row["code"]))
    if not company and (text or memory):
        company = await _named_company(ctx, tx, parent, text, memory)
    if company and company != parent["company"]:
        co = await ctx.hub.companies.find(company)
        if co is None or co.kind == "holding":
            raise _fail("این شرکت را نمیشناسم.", "payload.company")
        code = await _delegate_target(tx, co.id, to or "ceo")
        return await _employee_row(tx, code)
    code = await _delegate_target(tx, parent["company_id"], to)
    return await _employee_row(tx, code)


async def _child_of_order(
    ctx: Ctx,
    tx: Tx,
    parent: dict[str, Any],
    emp: dict[str, Any],
    *,
    title: str,
    brief: str,
) -> dict[str, Any]:
    """A work of the order for `emp`: a child of the root in the holder's company; in another
    company (or the holding) a work requested by the root, which the order's tree follows."""
    from hq_api.domain import work as W

    if emp["company_id"] == parent["company_id"]:
        return await W.delegate(tx, ctx.who, parent, to_code=str(emp["code"]), title=title,
                                brief=brief, priority=None, due_at=None, budget=None)  # fmt: skip
    return await W.create(
        tx,
        ctx.who,
        company_id=emp["company_id"],
        company_code=str(emp["company"]),
        title=title,
        brief=brief,
        kind="one_off",
        priority=str(parent["priority"]),
        assignee_code=str(emp["code"]),
        requested_by_work_id=parent["id"],
    )


async def _join(ctx: Ctx, tx: Tx, ref: str, conv: dict[str, Any], emp: dict[str, Any]) -> str:
    """The asked person joins this session (the existing participant path), unless already here;
    the persona key the answer comes back under."""
    from hq_api.domain import order_turns as OT
    from hq_api.domain import sessions as SE

    key = OT.persona_key(emp)
    if key != conv.get("holder") and key not in (conv.get("present") or []):
        try:
            key = await SE.add_participant(ctx, tx, ref, "person", key)
        except ApiError as exc:
            if exc.status != 409:  # the holder is already here: fine
                raise
    return key


ASK_BRIEF_MEMORY_CHARS = 4000


def ask_brief(
    question: str,
    *,
    ref: str,
    title_fa: str,
    holder_fa: str,
    why_fa: str | None,
    memory_md: str | None,
    plan: list[dict[str, Any]],
) -> str:
    """⟨2026-11-08⟩ what the asked person's work carries, so they know what is going on: the
    question, which session (its title and order), who asks and why (the card's own words), the
    session's memory («تا اینجا», §40.1) and its plan; and how the answer comes back."""
    lines = [
        question,
        "",
        f"## جلسه: {title_fa}",
        f"فرمان {ref} مدیر کل؛ {holder_fa} شما را به این جلسه آورد و این را میپرسد.",
    ]
    if why_fa:
        lines.append(f"چرا: {why_fa}")
    if memory_md:
        lines += ["", "## تا اینجا (حافظه‌ی جلسه)", memory_md[:ASK_BRIEF_MEMORY_CHARS]]
    if plan:
        lines += ["", "## برنامه‌ی جلسه"]
        lines += [f"{t['n']}. {t['title_fa']} [{t['state']}]" for t in plan[:30]]
    lines += [
        "",
        "(جواب را با deliver بده: به همان جلسه برمیگردد و شما در آن حاضر هستید. کسی را به فرمان "
        "تازه حواله نکن.)",
    ]
    return "\n".join(lines)


async def _session_ask(
    ctx: Ctx,
    conv: dict[str, Any],
    p: Persona,
    payload: dict[str, Any],
    text: str,
    note: list[str],
    *,
    card: dict[str, Any] | None = None,
) -> tuple[list[str], list[Any]]:
    """⟨2026-11-07⟩ W9 B: a question for someone else, answered IN THIS session: they join, the
    question is a work of this order assigned to them, and the answer is their turn here.
    ⟨2026-11-08⟩ the person is the one the card names (its company, or a full code), and their
    work carries the session's title, memory and plan and the holder's words."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import sessions as SE

    question = clean(" ".join(str(payload.get("text") or text).split()))[0]
    if len(question) < 2:
        raise _fail("متن پرسش خالی است.", "payload.text")
    to = str(payload.get("to") or payload.get("role") or "").strip()
    company = payload.get("company") if isinstance(payload.get("company"), str) else None
    async with ctx.tx() as tx:
        ref, parent = await _root_work(ctx, tx, conv)
        rep = await OR.ensure(tx, ref)
        order = await OR.load_order(tx, ref)
        emp = await _asked(
            ctx, tx, parent, to, company,
            text=f"{question} {(card or {}).get('body_fa') or ''}",
            memory=(rep or {}).get("memory_md"),
        )  # fmt: skip
        key = await _join(ctx, tx, ref, conv, emp)
        who = OR.who_fa(
            emp["title_fa"], None if emp["company_kind"] == "holding" else emp["company_fa"]
        )
        why = clean(" ".join(str((card or {}).get("body_fa") or "").split()))[0][:600] or None
        child = await _child_of_order(
            ctx,
            tx,
            parent,
            emp,
            title=f"پرسش مدیر کل: {question}"[:300],
            brief=ask_brief(
                question,
                ref=ref,
                title_fa=SE._title((order or {}).get("text")),
                holder_fa=p.title_fa,
                why_fa=why if why and why != question else None,
                memory_md=(rep or {}).get("memory_md"),
                plan=await SE.tasks_of(tx, rep["order_id"]) if rep is not None else [],
            ),
        )
        if rep is not None:
            await SE.add_task(tx, rep, title_fa=f"پاسخ به: {question}"[:300], by="owner",
                              who_fa=who, who_code=str(emp["code"]), work_ref=str(child["ref"]))  # fmt: skip
        payload["asked"] = key  # the answer comes back as this persona's turn
        await ctx.audit(tx, company_id=parent["company_id"], action="work.ask", action_class="A2",
                        target_kind="work", target_ref=child["ref"],
                        summary=f"from session {conv['ref']} to {emp['code']}")  # fmt: skip
    note.append(f"پرسش به {who} سپرده شد؛ جوابش همین‌جا می‌آید.")
    return [str(child["ref"])], []


async def _session_minutes(
    ctx: Ctx, conv: dict[str, Any], payload: dict[str, Any], note: list[str]
) -> tuple[list[str], list[Any]]:
    """⟨2026-11-07⟩ W9 B: the minutes' tasks become works of this order (a department named: its
    manager; another company named: its CEO), else plan tasks of the session; never new orders."""
    from hq_api.domain import order_report as OR
    from hq_api.domain import sessions as SE

    tasks = [t for t in payload.get("tasks") or [] if isinstance(t, dict)]
    if not tasks:
        raise _fail("صورت‌جلسه کاری برای اجرا ندارد.", "payload.tasks")
    made: list[str] = []
    works = 0
    async with ctx.tx() as tx:
        ref, parent = await _root_work(ctx, tx, conv)
        rep = await OR.ensure(tx, ref)
        for t in tasks:
            title = clean(" ".join(str(t.get("title_fa") or "").split()))[0]
            if len(title) < 2:
                continue
            due = f" (تا {t['due']})" if t.get("due") else ""
            co = t.get("company") if isinstance(t.get("company"), str) else None
            dept = str(t.get("department") or "").strip()
            emp: dict[str, Any] | None = None
            if dept or (co and co != parent["company"]):
                try:
                    emp = await _asked(ctx, tx, parent, dept, co)
                except ApiError:
                    emp = None  # nobody by that name: the task stays on the plan
            if emp is not None:
                child = await _child_of_order(
                    ctx, tx, parent, emp,
                    title=title[:300],
                    brief=f"{title}{due}\n\n(از صورت‌جلسه‌ی فرمان {ref} مدیر کل)",
                )  # fmt: skip
                works += 1
                made.append(str(child["ref"]))
                if rep is not None:
                    who = OR.who_fa(emp["title_fa"], emp["company_fa"])
                    await SE.add_task(tx, rep, title_fa=title + due, by="owner", who_fa=who,
                                      who_code=str(emp["code"]), work_ref=str(child["ref"]))  # fmt: skip
            elif rep is not None:
                row = await SE.add_task(tx, rep, title_fa=title + due, by="owner")
                made.append(str(row["id"]))
        if not made:
            raise _fail("صورت‌جلسه کاری برای اجرا ندارد.", "payload.tasks")
        await ctx.audit(tx, company_id=parent["company_id"], action="session.minutes",
                        action_class="A2", target_kind="order", target_ref=ref,
                        summary=f"{len(made)} tasks ({works} works) from {conv['ref']}")  # fmt: skip
    note.append(f"صورت‌جلسه: {len(made)} کار به همین فرمان اضافه شد.")
    return made, []


# ------------------------------------------------------------ the session --
async def _root_work(ctx: Ctx, tx: Tx, conv: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The order a session is, and its holder's root work (open)."""
    from hq_api.domain import order_turns as OT
    from hq_api.domain import work as W

    ref = conv.get("order_ref")
    if not ref:
        raise _fail("این کارت فقط در جلسه‌ی فرمان کار میکند.", "kind")
    h = await OT.holder(tx, str(ref))
    if h is None or h.get("work_id") is None:
        raise _fail("این فرمان کار بازی ندارد که چیزی به آن اضافه شود.", "kind")
    w = await W.load(tx, h["work_id"], lock=True)
    if w["status"] not in W.OPEN:
        raise _fail("کار اصلی این فرمان بسته شده است.", "kind")
    return str(ref), w


async def _delegate_target(tx: Tx, company_id: UUID, to: str) -> str:
    """`to`: an employee code of the company, a department code (its manager) or a charter role."""
    if re.fullmatch(EMP, to):
        row = await tx.first(
            """SELECT code FROM core.employees WHERE code = :c AND company_id = :co
                 AND status = 'active' AND kind <> 'system'""",
            c=to,
            co=company_id,
        )
        if row is not None:
            return str(row["code"])
    if re.fullmatch(DEPT, to):
        row = await tx.first(
            """SELECT e.code FROM core.employees e JOIN core.departments d ON d.id = e.department_id
               WHERE e.company_id = :co AND d.code = :d AND e.kind = 'manager' AND e.status = 'active'
               ORDER BY e.hired_at LIMIT 1""",
            co=company_id,
            d=to,
        )
        if row is not None:
            return str(row["code"])
    row = await tx.first(
        """SELECT code FROM core.employees WHERE company_id = :co AND lower(role) = lower(:r)
             AND status = 'active' AND kind <> 'system' ORDER BY hired_at LIMIT 1""",
        co=company_id,
        r=to,
    )
    if row is None:
        raise _fail("کسی با این نام یا نقش در این شرکت نیست.", "payload.to")
    return str(row["code"])


async def _session_card(
    ctx: Ctx,
    request: Request,
    card: dict[str, Any],
    conv: dict[str, Any],
    payload: dict[str, Any],
    text: str,
    note: list[str] | None = None,
) -> tuple[list[str], list[Any]]:
    kind = card["kind"]
    if kind == "delegate":
        from hq_api.domain import order_report as OR
        from hq_api.domain import sessions as SE
        from hq_api.domain import work as W

        to = str(payload.get("to") or "").strip()
        what = clean(" ".join(str(payload.get("text") or text).split()))[0]
        company = payload.get("company") if isinstance(payload.get("company"), str) else None
        if not to or len(what) < 2:
            raise _fail("به کی و چه کاری؟ هر دو لازم است.", "payload")
        async with ctx.tx() as tx:
            ref, parent = await _root_work(ctx, tx, conv)
            rep = await OR.ensure(tx, ref)
            # ⟨2026-11-08⟩ audit M3: `company` like `ask`; a company or a server the words name
            # (the text, then the session's memory) resolves the person before the holder's company
            emp = await _asked(
                ctx, tx, parent, to, company,
                text=f"{what} {card.get('body_fa') or ''}", memory=(rep or {}).get("memory_md"),
            )  # fmt: skip
            code = str(emp["code"])
            if emp["company_id"] != parent["company_id"]:
                await _join(ctx, tx, ref, conv, emp)  # the person comes into this session
            child = await _child_of_order(
                ctx,
                tx,
                parent,
                emp,
                title=what[:300],
                brief=f"{what}\n\n(فرمان {ref} مدیر کل؛ از جلسه‌ی فرمان سپرده شد)",
            )
            if rep is not None:
                who = OR.who_fa(
                    emp["title_fa"], None if emp["company_kind"] == "holding" else emp["company_fa"]
                )
                await SE.add_task(tx, rep, title_fa=what, by="owner", who_fa=who, who_code=code,
                                  work_ref=str(child["ref"]))  # fmt: skip
            await ctx.audit(tx, company_id=parent["company_id"], action="work.delegate",
                            action_class="A2", target_kind="work", target_ref=child["ref"],
                            summary=f"from session {conv['ref']} to {code}")  # fmt: skip
        return [str(child["ref"])], []
    if kind == "budget":
        from hq_api.domain import work as W

        try:
            tokens = int(payload.get("tokens") or 0)
        except (TypeError, ValueError) as exc:
            raise _fail("چند واحد مصرف؟ یک عدد لازم است.", "payload.tokens") from exc
        if tokens <= 0 or tokens > 10_000_000:
            raise _fail("چند واحد مصرف؟ یک عدد لازم است.", "payload.tokens")
        async with ctx.tx() as tx:
            ref, w = await _root_work(ctx, tx, conv)
            await W.add_budget(tx, w, tokens, ctx.who)
            await ctx.audit(tx, company_id=w["company_id"], action="work.budget", action_class="A2",
                            target_kind="work", target_ref=w["ref"],
                            summary=f"+{tokens} tokens from session {conv['ref']}")  # fmt: skip
        return [str(w["ref"])], []
    if kind == "group":
        from hq_api.domain import groups as GR

        code = str(payload.get("company") or "")
        key = str(payload.get("group") or "")
        if not re.fullmatch(CODE, code) or not key:
            raise _fail("شرکت و کارگروه هر دو لازم است.", "payload")
        company = await ctx.hub.companies.find(code)
        if company is None:  # ⟨2026-11-06⟩ plain words, in a session or outside one
            raise _fail("این شرکت را نمیشناسم.", "payload.company")
        async with ctx.tx() as tx:
            if await tx.first("SELECT 1 FROM growth.groups WHERE key = :k", k=key) is None:
                raise _fail("این کارگروه را نمیشناسم.", "payload.group")
            grow = await GR.row_of(tx, key, lock=True)
            await tx.exec(
                """INSERT INTO growth.memberships (company_id, group_id) VALUES (:co, :g)
                   ON CONFLICT (group_id, company_id) DO NOTHING""",
                co=company.id,
                g=grow["id"],
            )
            await GR.set_member_state(tx, grow, company.id, "on")
            await GR.reconcile_members(tx, grow, fill=False)
            await ctx.audit(tx, company_id=company.id, action="group.member", action_class="A2",
                            target_kind="group", target_ref=key,
                            summary=f"membership on from session {conv['ref']}")  # fmt: skip
            await ctx.emit(tx, code, "group.run", None, {"group": key, "membership": "on"})
        return [key], []
    if kind == "line":
        from hq_api.routes.lines import LineIn, create_company_line

        code = str(payload.get("company") or "")
        template = str(payload.get("template") or "")
        if not re.fullmatch(CODE, code) or not template:
            raise _fail("شرکت و الگوی خط تولید هر دو لازم است.", "payload")
        try:
            body = LineIn(
                template=template,
                title_fa=str(payload.get("title_fa") or card["title_fa"])[:200],
            )
        except ValidationError as exc:
            raise _fail("الگوی خط تولید شناخته نیست.", "payload.template") from exc
        out = await create_company_line(
            code, body, sub_request(request, 0, body.model_dump(mode="json")), ctx
        )
        return [_ref_of(out)], []
    if kind == "playbook":
        return await _playbook_card(ctx, conv, payload, note)
    raise _fail("این نوع کارت شناخته نیست.", "kind")


async def _playbook_card(
    ctx: Ctx, conv: dict[str, Any], payload: dict[str, Any], note: list[str] | None
) -> tuple[list[str], list[Any]]:
    """⟨1.22⟩ §40.2 the `playbook` card: with a `draft`, the holder's rewrite of the session's
    draft in the owner's words (stored through the same normaliser as PATCH; a sealed playbook
    refuses); without one, the card «کارگروه از این جلسه» the draft posted: nothing to do but
    point at it (the owner opens, edits and seals it on its page)."""
    from hq_api.domain import playbooks as PB

    ref = str(payload.get("playbook") or "").strip().upper()
    if not PB.REF.match(ref):
        raise _fail("شناسه‌ی کارگروه (playbook) روشن نیست.", "payload.playbook")
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else None
    async with ctx.tx() as tx:
        row = await PB.row_of(tx, ref)
        if str((store._j(row["source"]) or {}).get("order") or "") != str(conv.get("order_ref")):
            raise _fail("این کارگروه از جلسه‌ی دیگری است.", "payload.playbook")
        if draft is None:
            if note is not None:
                note.append(f"کارگروه {ref} آماده‌ی بازبینی است؛ در صفحه‌اش باز، ویرایش و مُهر کن.")
            return [ref], []
        notes: list[str] = []
        out = await PB.patch(tx, ctx.hub, ref, draft, notes=notes)
        await ctx.audit(tx, company_id=row["company_id"], action="playbook.edit", action_class="A1",
                        target_kind="playbook", target_ref=ref,
                        summary=f"rewritten from session {conv['ref']} (v{out['version']})")  # fmt: skip
    if note is not None:
        note.append(
            " ".join([f"پیش‌نویس کارگروه {ref} بازنویسی شد (نسخه‌ی {out['version']}).", *notes])
        )
    return [ref], []


async def _decision(
    ctx: Ctx, card: dict[str, Any], p: Persona, payload: dict[str, Any], text: str
) -> tuple[list[str], list[Any]]:
    who = proposer(p)
    if card["kind"] == "hire" and (not p.is_manager or who.kind != "agent"):
        # ⟨1.17⟩ §35.4 any persona may propose a hire for a company named explicitly: the seat
        # is filled by code (§29.10, automatic hiring with its own checks), as the order fix does
        from hq_api.domain import hiring

        code = str(payload.get("company") or "")
        role = str(payload.get("role") or "ceo")
        if not re.fullmatch(CODE, code):
            raise _fail("شرکتِ این استخدام را روشن بگو.", "payload.company")
        company = await ctx.hub.companies.by_code(code)
        async with ctx.tx() as tx:
            out = await hiring.auto_fill(
                tx, company.id, role, charters=ctx.hub.charters, reason=text[:2000]
            )
            await ctx.audit(tx, company_id=company.id, action="hire.auto", action_class="A2",
                            target_kind="employee", target_ref=str(out["employee"]),
                            summary=f"{role} for {code} from a talk card")  # fmt: skip
            # ⟨2026-11-07⟩ §39 hired from inside a session: the new employee joins it at once
            from hq_api.domain import sessions as SE

            charter = ctx.hub.charters.get(role) if ctx.hub.charters is not None else None
            await SE.join_hired(tx, str(out["employee"]), role, code,
                                charter.title_fa if charter is not None else role,
                                conversation_id=card["conversation_id"])  # fmt: skip
        return [str(out["employee"])], []
    if card["kind"] == "hire":
        lib = ctx.hub.charters
        role = str(payload.get("role") or "")
        charter = lib.get(role) if lib is not None else None
        if charter is None:
            raise _fail("نقشِ این استخدام منشور ندارد.", "payload.role")
        try:
            tokens = int(payload.get("tokens_month") or charter.limits.tokens_per_run * 30)
        except (TypeError, ValueError) as exc:
            why = "سهمیه‌ی ماهانه‌ی این استخدام باید یک عدد باشد."
            raise _fail(why, "payload.tokens_month") from exc
        hire = {
            "company": p.company,
            "department": payload.get("department") or (p.employee or {}).get("department"),
            "role": role,
            "title_fa": str(payload.get("title_fa") or charter.title_fa)[:200],
            "title_en": str(payload.get("title_en") or charter.title_en)[:200],
            "reason": str(payload.get("why_fa") or text)[:5000],
            "model": str(payload.get("model") or charter.model),
            "effort": str(payload.get("effort") or charter.effort),
            "quota_estimate_month": {"tokens": tokens},
        }  # fmt: skip
        body = Dec.DecisionIn(kind="hire", title=f"استخدام: {hire['title_fa']}"[:300],
                              what=str(card["body_fa"] or hire["reason"])[:20000],
                              why=hire["reason"], payload=hire)  # fmt: skip
    else:
        body = Dec.DecisionIn(
            kind="proposal",
            title=str(payload.get("title_fa") or card["title_fa"])[:300],
            what=str(payload.get("what_fa") or card["body_fa"] or card["title_fa"])[:20000],
            why=str(payload.get("why_fa") or f"از گفتگوی مالک با {p.title_fa}")[:20000],
        )
    async with ctx.tx() as tx:
        co = await ctx.hub.companies.by_id(p.company_id)
        d = await Dec.propose(
            tx,
            who,
            company_id=co.id,
            company_code=co.code,
            body=body,
            thread_code=None,
            charters=ctx.hub.charters,
            company_kind=co.kind,
        )
    return [d["ref"]], [("decision", d["ref"])]


# -------------------------------------------------------------- invites --
NO_SESSION_FA = (
    "ChatGPT، Gemini و DeepSeek فقط در جلسه‌ی یک فرمان به گفتگو می‌آیند؛ "
    "این کار را به شکل فرمان بده تا جلسه‌اش باز شود."
)


async def _invite_player(
    ctx: Ctx, conv: dict[str, Any], payload: dict[str, Any]
) -> tuple[list[str], list[Any]]:
    """⟨2026-11-06⟩ `invite {player}`: ChatGPT, Gemini or DeepSeek joins the session of the order
    this talk is bound to (§35.4, the same path as the owner's «+»); outside a session, refused."""
    from hq_api.domain import sessions as SE

    player = str(payload.get("player") or "").strip().lower()
    player = player.split(":", 1)[1] if player.startswith("player:") else player
    if player not in SE.PLAYERS:
        raise _fail("بازیکن را از میان ChatGPT، Gemini و DeepSeek انتخاب کن.", "payload.player")
    ref = conv.get("order_ref")
    if not ref:
        raise _fail(NO_SESSION_FA, "payload.player")
    async with ctx.tx() as tx:
        added = await SE.add_participant(ctx, tx, str(ref), "player", player)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="session.participant", action_class="A1",
                        target_kind="order", target_ref=str(ref),
                        summary=f"+{added} from {conv['ref']}")  # fmt: skip
    return [added], []


async def join_with_notice(tx: Tx, hub: Any, conv: dict[str, Any], p: Persona) -> dict[str, Any]:
    """§32.4: the manager joins and answers next; code writes the one line."""
    from hq_api.talk.engine import join

    joined = await join(tx, conv, p)
    n = int(conv["turns"]) + 1
    await tx.exec(
        """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, show_md,
               say_fa, state, finished_at)
           VALUES (:c, :co, :n, 'persona', :p, 'system', :line, :line, 'done', now())""",
        c=conv["id"],
        co=p.company_id,
        n=n,
        p=p.key,
        line=joined["notice_fa"],
    )
    await tx.exec(
        "UPDATE talk.conversations SET turns = :n, last_turn_at = now() WHERE id = :id",
        n=n,
        id=conv["id"],
    )
    conv["turns"] = n
    return joined


# --------------------------------------------- an ask's answer comes back --
async def on_outputs(tx: Tx, order_ref: str, outputs: list[dict[str, Any]]) -> int:
    """New outputs of an order: when the order came from an `ask` card, each
    deliverable comes back into that conversation as a turn of the persona
    («جواب آمد») with one notification (§32.2). Once per deliverable."""
    if not outputs:
        return 0
    rows = await tx.all(
        """SELECT d.ref, d.title, d.summary, d.body, w.ref AS work_ref FROM cartable.deliverables d
           JOIN work.work w ON w.id = d.work_id WHERE d.ref = ANY(:refs)""",
        refs=[o["ref"] for o in outputs],
    )
    by_ref = {r["ref"]: dict(r) for r in rows}
    # ⟨2026-11-07⟩ W9 B: a session's ask made a work of the same order; its deliverable (a part
    # of the order) answers that card, under the asked person's persona
    cards = await tx.all(
        """SELECT * FROM talk.cards WHERE kind = 'ask'
             AND (:r = ANY(made) OR made && CAST(:works AS text[])) FOR UPDATE""",
        r=order_ref,
        works=[str(r["work_ref"]) for r in rows],
    )
    posted = 0
    for card in cards:
        mine = order_ref in (card["made"] or [])
        for o in outputs:
            d = by_ref.get(o["ref"])
            if d is None or o["ref"] in (card["answered"] or []):
                continue
            if mine and o.get("kind") == "part":
                continue
            if not mine and d["work_ref"] not in (card["made"] or []):
                continue
            await _post_answer(tx, dict(card), d)
            await tx.exec(
                """UPDATE talk.cards SET answered = array_append(answered, :d), updated_at = now()
                   WHERE id = :id""",
                d=o["ref"],
                id=card["id"],
            )
            card = dict(card)
            card["answered"] = [*(card["answered"] or []), o["ref"]]
            posted += 1
    return posted


async def _post_answer(tx: Tx, card: dict[str, Any], d: dict[str, Any]) -> None:
    conv = await tx.one(
        "SELECT * FROM talk.conversations WHERE id = :c FOR UPDATE", c=card["conversation_id"]
    )
    # ⟨2026-11-07⟩ a session's ask: the asked person's own persona answers
    asked = (store._j(card["payload"]) or {}).get("asked")
    persona = asked or await tx.scalar(
        "SELECT persona FROM talk.turns WHERE id = :t", t=card["turn_id"]
    )
    title = clean(str(d["title"]))[0][:200]
    body = clean(str(d["summary"] or d["body"] or ""))[0][:6000]
    n = int(conv["turns"]) + 1
    say = f"جواب آمد: {title}"[:400]
    show = f"**جواب آمد** ({d['ref']}): {title}\n\n{body}".strip()
    await tx.exec(
        """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, say_fa,
               show_md, state, finished_at)
           VALUES (:c, :co, :n, 'persona', :p, 'system', :say, :show, 'done', now())""",
        c=conv["id"],
        co=card["company_id"],
        n=n,
        p=persona or "secretary",
        say=say,
        show=show[:20000],
    )
    await tx.exec(
        "UPDATE talk.conversations SET turns = :n, last_turn_at = now(), updated_at = now() WHERE id = :id",
        n=n,
        id=conv["id"],
    )
    holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await events.emit(
        tx, holding["code"], "talk.turn", conv["ref"], {"state": "done", "answer": d["ref"]}
    )
    await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="report",
        title_fa=f"جواب آمد: {title}"[:300],
        body_fa=f"در گفتگوی {conv['ref']}"[:4000],
        link_kind="conversation",
        link_ref=conv["ref"],
        source_kind="service",
        source_code="talk",
        domain="business",
    )
