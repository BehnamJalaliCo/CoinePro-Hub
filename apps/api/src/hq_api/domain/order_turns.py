"""The owner's order answered live (contract §34, v1.16; the owner, 2026-11-06).

«به محض فرمان باید اون مسئول اون قسمت در کسری از ثانیه به خط و گوش به فرمان وایسه با من حرف
بزنه و مرحله به مرحله با من پیش بره یا یه فرمان کلی بدم خودش بره همه کارهارو بکنه»

    the holder      the assignee of the order's first root work (the employee who answers for it)
    order.ask       (A1, the holder or anyone working on the order) one short question to the
                    owner: the report's `turn`, the order `waiting` on the owner, a step, one
                    notification to the owner at once, and the line in the live talk
    reply           (the owner) the answer: a step «مدیر کل: …», the turn cleared, and the asker's
                    work runs again at once with the dialogue in its brief
    the live talk   one conversation per order with the holder's persona (POST /orders/{ref}/talk;
                    a step order opens it at once); the holder's steps and questions come into it
                    as its turns, and what the owner tells the holder there becomes a card that
                    goes onto this same order (a reply), never a new order
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import notify
from hq_api.domain import order_report as OR
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.talk.scrub import clean

OWNER_FA = "مدیر کل"
DIALOGUE_STEPS = 12
FIXED_PERSONAS = ("advisor", "overseer", "assistant")


# ------------------------------------------------------------------ helpers --
async def holder(tx: Tx, ref: str) -> dict[str, Any] | None:
    """The order's holder: the assignee of its first open root work (else its first root)."""
    order = await OR.load_order(tx, ref)
    if order is None:
        return None
    works = [w for w in await OR.tree(tx, OR.root_refs(order)) if w["is_root"] and w["a_code"]]
    if not works:
        return None
    w = next((x for x in works if x["status"] in OR.OPEN), works[0])
    emp = await tx.first(
        """SELECT e.id, e.code, e.role, e.kind, e.title_fa, e.status, c.code AS company,
                  c.kind AS company_kind, c.name_fa AS company_fa
           FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE e.code = :c""",
        c=w["a_code"],
    )
    if emp is None:
        return None
    return {**dict(emp), "work_id": w["id"], "work_ref": w["ref"], "work_status": w["status"]}


def persona_key(h: dict[str, Any]) -> str:
    """The talk persona of a holder: `role@CODE` in an operating company; the holding's fixed
    persona of its role; else the secretary."""
    if h["company_kind"] != "holding":
        return f"{h['role']}@{h['company']}"
    return str(h["role"]) if h["role"] in FIXED_PERSONAS else "secretary"


async def _bound(tx: Tx, rep: dict[str, Any]) -> dict[str, Any] | None:
    ref = rep.get("conversation_ref")
    if not ref:
        return None
    return await tx.first("SELECT * FROM talk.conversations WHERE ref = :r FOR UPDATE", r=ref)


async def post_turn(tx: Tx, conv: dict[str, Any], persona: str, say: str, show: str) -> None:
    """One turn of the persona in the conversation, by the system (no model)."""
    n = int(conv["turns"]) + 1
    await tx.exec(
        """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, say_fa,
               show_md, state, finished_at)
           VALUES (:c, :co, :n, 'persona', :p, 'system', :say, :show, 'done', now())""",
        c=conv["id"],
        co=conv["company_id"],
        n=n,
        p=persona,
        say=clean(say)[0][:400],
        show=clean(show)[0][:20000],
    )
    await tx.exec(
        """UPDATE talk.conversations SET turns = :n, last_turn_at = now(), updated_at = now()
           WHERE id = :id""",
        n=n,
        id=conv["id"],
    )
    conv["turns"] = n
    holding = await tx.one("SELECT code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await events.emit(tx, holding["code"], "talk.turn", conv["ref"], {"state": "done", "n": n})


async def to_talk(tx: Tx, rep: dict[str, Any], code: str, text: str, *, ask: bool = False) -> bool:
    """A step or a question of someone working on the order, into its live talk (when it has one):
    as the holder's persona's turn."""
    conv = await _bound(tx, rep)
    if conv is None:
        return False
    emp = await tx.first(
        """SELECT e.title_fa, e.role, c.code AS company, c.kind AS company_kind
           FROM core.employees e JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=code,
    )
    mine = emp is not None and persona_key(dict(emp)) == conv["persona"]
    who = "" if mine or emp is None else f"{emp['title_fa']}: "
    lead = "**سؤال از شما** · " if ask else ""
    plain = HZ.humanize(text) or text
    await post_turn(tx, conv, str(conv["persona"]), f"{who}{plain}", f"{lead}{who}{plain}")
    return True


async def to_talk_owner(tx: Tx, rep: dict[str, Any], text: str) -> bool:
    """The owner's word given on the order's page, into its live talk as the owner's turn."""
    conv = await _bound(tx, rep)
    if conv is None:
        return False
    n = int(conv["turns"]) + 1
    await tx.exec(
        """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, text,
               state, finished_at)
           VALUES (:c, :co, :n, 'owner', NULL, 'system', :t, 'done', now())""",
        c=conv["id"],
        co=conv["company_id"],
        n=n,
        t=clean(text)[0][:20000],
    )
    await tx.exec(
        """UPDATE talk.conversations SET turns = :n, last_turn_at = now(), updated_at = now()
           WHERE id = :id""",
        n=n,
        id=conv["id"],
    )
    return True


# -------------------------------------------------------------------- ask --
async def ask(tx: Tx, who: Principal, ref: str, question_fa: str) -> dict[str, Any]:
    """`order.ask`: the owner's turn on the order."""
    rep = await OR.ensure(tx, ref)
    assert rep is not None
    emp = await tx.one(
        """SELECT e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=who.code,
    )
    who_name = OR.who_fa(emp["title_fa"], emp["company_fa"])
    question = " ".join(question_fa.split())[:1000]
    turn = {
        "question_fa": question,
        "at": datetime.now(UTC).isoformat(),
        "by": {"kind": "agent", "code": who.code},
        "who_fa": HZ.humanize(who_name) or who_name,
    }
    await tx.exec(
        """UPDATE owner.order_reports SET turn = CAST(:t AS jsonb), last_step_at = now(),
               updated_at = now()
           WHERE id = :id""",
        t=json.dumps(turn, ensure_ascii=False),
        id=rep["id"],
    )
    await OR._append_steps(tx, rep["id"], [OR._step(who_name, "سؤال از شما: " + question)])
    await OR._close_nudges(tx, ref, "مسئول از مدیر کل پرسید (order.ask)")
    talked = await to_talk(tx, rep, who.code, question, ask=True)
    order = await OR.load_order(tx, ref)
    text = " ".join(((order or {}).get("text") or "").split())[:80]
    holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="decision",
        title_fa=f"نوبت شماست: {text}"[:300],
        body_fa=f"{who_name} میپرسد: {question}"[:4000],
        link_kind="conversation" if talked else "order",
        link_ref=rep["conversation_ref"] if talked else ref,
        source_kind="service",
        source_code="orders",
        domain="business",
        owner_action=True,
    )
    return rep


# ------------------------------------------------------------------ reply --
async def reply(tx: Tx, ref: str, text: str) -> dict[str, Any]:
    """The owner's word on the order: a step, the turn cleared, and the asker's work (else the
    holder's) runs again at once. Answers {work_ref, run_id}."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    if rep["ended_at"] is not None:
        raise ApiError(409, "validation_failed", "the order has ended",
                       message_fa="این فرمان تمام شده است؛ فرمان تازه بدهید.")  # fmt: skip
    words = " ".join(text.split())[:2000]
    if len(words) < 1:
        raise ApiError(422, "validation_failed", fields={"text": "empty"},
                       message_fa="متن پاسخ خالی است.")  # fmt: skip
    turn = OR._j(rep.get("turn")) or {}
    order = await OR.load_order(tx, ref)
    assert order is not None
    works = await OR.tree(tx, OR.root_refs(order))
    asker = (turn.get("by") or {}).get("code")
    target = next(
        (w for w in works if w["a_code"] == asker and w["status"] in OR.OPEN), None
    ) or next((w for w in works if w["is_root"] and w["status"] in OR.OPEN), None)
    if target is None:
        raise ApiError(409, "validation_failed", "no open work on the order",
                       message_fa="کار بازی روی این فرمان نمانده است؛ فرمان تازه بدهید.")  # fmt: skip
    await tx.exec(
        """UPDATE owner.order_reports SET turn = NULL, last_step_at = now(),
               progress_nudged_at = NULL, owner_told_at = NULL, updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
    )
    await OR._append_steps(tx, rep["id"], [OR._step(OWNER_FA, words)])
    await tx.exec(
        "UPDATE work.work SET status = 'in_progress' WHERE id = :w AND status = 'waiting'",
        w=target["id"],
    )
    run_id = await tx.scalar(
        "SELECT work.wake_assignee(:w, :r)", w=target["id"], r=f"owner_reply:{ref}"
    )
    return {"work_ref": target["ref"], "run_id": run_id}


# -------------------------------------------------------------- the talk --
async def open_talk(ctx: Any, tx: Tx, ref: str) -> str | None:
    """The order's live talk with its holder: the one it has, else a new one (work mode)."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    if rep.get("conversation_ref"):
        return str(rep["conversation_ref"])
    h = await holder(tx, ref)
    if h is None:
        return None
    from hq_api.talk import service as TS

    order = await OR.load_order(tx, ref)
    text = " ".join(((order or {}).get("text") or "").split())
    try:
        conv = await TS.new_conversation(ctx, tx, persona_key(h), "work", f"فرمان: {text}"[:200])
    except ApiError:
        conv = await TS.new_conversation(ctx, tx, "secretary", "work", f"فرمان: {text}"[:200])
    await tx.exec(
        "UPDATE talk.conversations SET order_ref = :r WHERE id = :id", r=ref, id=conv["id"]
    )
    await tx.exec(
        """UPDATE owner.order_reports SET conversation_ref = :c, updated_at = now()
           WHERE id = :id""",
        c=conv["ref"],
        id=rep["id"],
    )
    conv = dict(conv)
    who = OR.who_fa(h["title_fa"], h["company_fa"])
    turn = OR._j(rep.get("turn"))
    if turn:
        first = f"سلام، {who} هستم. منتظر جواب شما هستم: {turn['question_fa']}"
    elif order and order.get("pace") == "step":
        first = f"سلام، {who} هستم و این فرمان با من است. مرحله‌به‌مرحله با شما جلو میروم؛ بگویید از کجا شروع کنم."
    else:
        first = f"سلام، {who} هستم و این فرمان با من است. هر چه بگویید روی همین فرمان انجام میشود."
    await post_turn(tx, conv, str(conv["persona"]), first, first)
    return str(conv["ref"])


async def talk_brief(tx: Tx, order_ref: str) -> dict[str, Any] | None:
    """What a talk bound to an order knows of it (by code): the order, how it is carried out, the
    owner's open turn, the last steps and what blocks it."""
    rep = await tx.first("SELECT * FROM owner.order_reports WHERE ref = :r", r=order_ref)
    order = await OR.load_order(tx, order_ref)
    if rep is None or order is None:
        return None
    steps = OR._j(rep["steps"]) or []
    return {
        "order": order_ref,
        "text": " ".join(str(order.get("text") or "").split())[:1500],
        "pace": order.get("pace") or "auto",
        "state": rep["state"],
        "owner_turn": OR._j(rep.get("turn")),
        "steps": [f"{s.get('who_fa')}: {s.get('what_fa')}" for s in steps[-DIALOGUE_STEPS:]],
        "blockers": [b.get("title_fa") for b in OR._j(rep["blockers"]) or []],
        "outputs": [o.get("title_fa") for o in OR._j(rep["outputs"]) or []],
    }


async def dialogue(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    """For a run on an order's work: the order and its dialogue with the owner (newest last)."""
    ref = await OR.order_of_work(tx, work_id)
    if ref is None:
        return None
    return await talk_brief(tx, ref)
