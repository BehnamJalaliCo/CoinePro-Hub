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
    invite      the manager joins the conversation (§32.4)

A card that fails stays visible as `failed` with its plain reason, and may be
run again (with the owner's edits). Running a done card answers what it made.
"""

from __future__ import annotations

import json
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
from hq_api.talk import personas, store
from hq_api.talk.personas import Persona
from hq_api.talk.scrub import clean

TALK = Principal(kind="service", code="talk", role="service")
DEPT = r"^[A-Z][A-Z0-9]{1,11}$"


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


async def persona_of_card(tx: Tx, hub: Any, card: dict[str, Any]) -> Persona:
    key = await tx.scalar("SELECT persona FROM talk.turns WHERE id = :t", t=card["turn_id"])
    return await personas.resolve(tx, hub, str(key or "secretary"), store_voice=False)


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
async def run(
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
        conv = await tx.one(
            "SELECT * FROM talk.conversations WHERE id = :c", c=card["conversation_id"]
        )
        p = await persona_of_card(tx, ctx.hub, card)
    payload = {**(store._j(card["payload"]) or {}), **(edits or {})}
    payload = json.loads(clean(json.dumps(payload, ensure_ascii=False, default=str))[0])
    later: list[Any] = []
    try:
        made, later = await _carry_out(ctx, request, card, conv, p, payload)
    except ApiError as exc:
        why = exc.message_fa or CODES.get(exc.code, CODES["internal_error"])[2]
        await _mark(ctx, card, "failed", [], why, payload)
        raise
    row = await _mark(ctx, card, "done", made, None, payload)
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


async def _carry_out(
    ctx: Ctx,
    request: Request,
    card: dict[str, Any],
    conv: dict[str, Any],
    p: Persona,
    payload: dict[str, Any],
) -> tuple[list[str], list[Any]]:
    kind, ref = card["kind"], conv["ref"]
    text = str(payload.get("text") or card["body_fa"] or card["title_fa"])
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
        compiled = await AU.compile_sentence(ctx.hub, sentence, company)
        if compiled.rule is None:
            raise _fail(
                compiled.refused_fa[0] if compiled.refused_fa else "این جمله به قاعده تبدیل نشد."
            )
        auto = {"rule": compiled.rule, "sentence_fa": sentence, "company": company}
        out = await add_automation(AutomationIn(**auto), sub_request(request, 0, auto), ctx)
        return [_ref_of(out)], []
    if kind in ("decision", "hire"):
        return await _decision(ctx, card, p, payload, text)
    raise _fail("این نوع کارت شناخته نیست.", "kind")


def _ref_of(out: Any) -> str:
    if isinstance(out, BaseModel):
        return str(out.ref)  # type: ignore[attr-defined]
    body = json.loads(bytes(out.body)) if hasattr(out, "body") else {}  # an idempotent replay
    return str(body.get("ref"))


async def _decision(
    ctx: Ctx, card: dict[str, Any], p: Persona, payload: dict[str, Any], text: str
) -> tuple[list[str], list[Any]]:
    who = proposer(p)
    if card["kind"] == "hire":
        if not p.is_manager or who.kind != "agent":
            raise _fail("استخدام را فقط مدیر همان شرکت پیشنهاد میدهد.", "kind")
        lib = ctx.hub.charters
        role = str(payload.get("role") or "")
        charter = lib.get(role) if lib is not None else None
        if charter is None:
            raise _fail("نقشِ این استخدام منشور ندارد.", "payload.role")
        hire = {
            "company": p.company,
            "department": payload.get("department") or (p.employee or {}).get("department"),
            "role": role,
            "title_fa": str(payload.get("title_fa") or charter.title_fa)[:200],
            "title_en": str(payload.get("title_en") or charter.title_en)[:200],
            "reason": str(payload.get("why_fa") or text)[:5000],
            "model": str(payload.get("model") or charter.model),
            "effort": str(payload.get("effort") or charter.effort),
            "quota_estimate_month": {"tokens": int(payload.get("tokens_month")
                                                   or charter.limits.tokens_per_run * 30)},
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
    cards = await tx.all(
        "SELECT * FROM talk.cards WHERE kind = 'ask' AND :r = ANY(made) FOR UPDATE", r=order_ref
    )
    posted = 0
    for card in cards:
        for o in outputs:
            if o["ref"] in (card["answered"] or []) or o.get("kind") == "part":
                continue
            d = await tx.first(
                "SELECT ref, title, summary, body FROM cartable.deliverables WHERE ref = :r",
                r=o["ref"],
            )
            if d is None:
                continue
            await _post_answer(tx, dict(card), dict(d))
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
    persona = await tx.scalar("SELECT persona FROM talk.turns WHERE id = :t", t=card["turn_id"])
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
