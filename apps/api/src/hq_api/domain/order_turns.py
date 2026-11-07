"""The owner's order answered live (contract §34, v1.16; §35.1, §35.4, v1.17; the owner,
2026-11-06).

«به محض فرمان باید اون مسئول اون قسمت در کسری از ثانیه به خط و گوش به فرمان وایسه با من حرف
بزنه و مرحله به مرحله با من پیش بره یا یه فرمان کلی بدم خودش بره همه کارهارو بکنه»

    the holder      the assignee of the order's first open root work (the employee who answers for
                    it); ⟨1.17⟩ when nobody holds it (a kit before its seal, a company without a
                    manager) the holding's secretary does: never ownerless
    order.ask       (A1, the holder or anyone working on the order) one short question to the
                    owner: the report's `turn`, the order `waiting` on the owner, a step, one
                    notification to the owner at once, and the line in the live talk; ⟨1.17⟩ a
                    second ask while the turn is open joins it (both questions)
    reply           (the owner) the answer: a step «مدیر کل: …», the turn cleared, and the askers'
                    works (else the holder's) run again at once with the dialogue in their brief;
                    a reply after a talk-loop stop restarts the order deliberately; ⟨1.19⟩ §37.4 a
                    word after delivery (the session `ready`, not closed) is a revision: the
                    holder's delivered root work goes back to `in_progress` and the holder is woken
    the live talk   one conversation per order with the holder's persona (opened on routing for
                    every order, §35.1); the holder's steps and questions come into it as its
                    turns, and what the owner tells the holder there becomes a card that goes
                    onto this same order (a reply), never a new order
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.domain import humanize as HZ
from hq_api.domain import notify
from hq_api.domain import order_report as OR
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.talk.scrub import clean

OWNER_FA = "مدیر کل"
DIALOGUE_STEPS = 12
FIXED_PERSONAS = ("advisor", "overseer", "assistant")
RESTARTED_FA = "فرمان با پاسخ مدیر کل دوباره راه افتاد"
REVISION_FA = "کار تحویل‌شده با حرف تازه‌ی مدیر کل دوباره باز شد"
DELIVERED = ("delivered", "done")
OWNER = Principal(kind="owner", code="owner", role="owner")


# ------------------------------------------------------------------ helpers --
EMP_SQL = """SELECT e.id, e.code, e.role, e.kind, e.title_fa, e.status, c.code AS company,
                    c.kind AS company_kind, c.name_fa AS company_fa
             FROM core.employees e JOIN core.companies c ON c.id = e.company_id"""


async def secretary(tx: Tx) -> dict[str, Any] | None:
    """The holding's secretary (a system employee of the holding, migration 0043)."""
    row = await tx.first(
        EMP_SQL
        + " WHERE c.kind = 'holding' AND e.role = 'holding_secretary' ORDER BY e.hired_at LIMIT 1"
    )
    if row is None:
        return None
    return {**dict(row), "work_id": None, "work_ref": None, "work_status": None}


async def holder(tx: Tx, ref: str) -> dict[str, Any] | None:
    """The order's holder: the assignee of its first open root work (else its first root);
    ⟨1.17⟩ §35.1 the secretary when nobody holds it (never ownerless)."""
    order = await OR.load_order(tx, ref)
    if order is None:
        return None
    works = [w for w in await OR.tree(tx, OR.root_refs(order)) if w["is_root"] and w["a_code"]]
    if not works:
        return await secretary(tx)
    w = next((x for x in works if x["status"] in OR.OPEN), works[0])
    emp = await tx.first(EMP_SQL + " WHERE e.code = :c", c=w["a_code"])
    if emp is None:
        return await secretary(tx)
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
    row = await tx.first("SELECT * FROM talk.conversations WHERE ref = :r FOR UPDATE", r=ref)
    return dict(row) if row is not None else None


async def post_turn(tx: Tx, conv: dict[str, Any], persona: str, say: str, show: str) -> UUID:
    """One turn of the persona in the conversation, by the system (no model); its id."""
    n = int(conv["turns"]) + 1
    tid: UUID = await tx.scalar(
        """INSERT INTO talk.turns (conversation_id, company_id, n, by_kind, persona, source, say_fa,
               show_md, state, finished_at)
           VALUES (:c, :co, :n, 'persona', :p, 'system', :say, :show, 'done', now()) RETURNING id""",
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
    return tid


def holder_key(conv: dict[str, Any]) -> str:
    return str(conv.get("holder") or conv["persona"])


async def _speaker(tx: Tx, conv: dict[str, Any], code: str) -> tuple[str, str]:
    """(the persona key a step of employee `code` is written under, the prefix shown): the
    speaker's own key when it is in the talk (the holder or a participant), else the holder's
    with the speaker named (⟨1.17⟩ W6 c: never the newcomer's key for the holder's steps)."""
    emp = await tx.first(EMP_SQL + " WHERE e.code = :c", c=code)
    hk = holder_key(conv)
    if emp is None or code == conv.get("holder_code"):
        return hk, ""
    own = persona_key(dict(emp))
    if own != hk and own in (conv.get("present") or []):
        return own, ""
    return hk, f"{emp['title_fa']}: "


async def to_talk(tx: Tx, rep: dict[str, Any], code: str, text: str, *, ask: bool = False) -> bool:
    """A step or a question of someone working on the order, into its live talk (when it has one):
    under the speaker's own persona when it is present, else the holder's."""
    conv = await _bound(tx, rep)
    if conv is None:
        return False
    key, who = await _speaker(tx, conv, code)
    lead = "**سؤال از شما** · " if ask else ""
    plain = HZ.humanize(text) or text
    await post_turn(tx, conv, key, f"{who}{plain}", f"{lead}{who}{plain}")
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
    """`order.ask`: the owner's turn on the order; ⟨1.17⟩ §35.4 a second ask while the turn is
    open joins it (both questions; the reply wakes both askers)."""
    rep = await OR.ensure(tx, ref)
    assert rep is not None
    emp = await tx.one(
        """SELECT e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=who.code,
    )
    who_name = OR.who_fa(emp["title_fa"], emp["company_fa"])
    question = " ".join(question_fa.split())[:1000]
    one = {
        "question_fa": question,
        "at": datetime.now(UTC).isoformat(),
        "by": {"kind": "agent", "code": who.code},
        "who_fa": HZ.humanize(who_name) or who_name,
    }
    open_turn = OR._j(rep.get("turn")) or {}
    asks = [a for a in open_turn.get("asks") or [] if isinstance(a, dict)] or (
        [{k: open_turn[k] for k in ("question_fa", "at", "by", "who_fa")}] if open_turn else []
    )
    asks.append(one)
    first = asks[0]
    turn = {
        **first,
        "question_fa": "\n".join(str(a["question_fa"]) for a in asks)[:4000],
        "asks": asks[:10],
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
def _asker_codes(turn: dict[str, Any]) -> list[str]:
    codes = [
        str(a["by"]["code"])
        for a in turn.get("asks") or []
        if isinstance(a, dict) and isinstance(a.get("by"), dict) and a["by"].get("code")
    ]
    first = (turn.get("by") or {}).get("code")
    if first and first not in codes:
        codes.insert(0, str(first))
    return list(dict.fromkeys(codes))


async def _waits_on_owner(tx: Tx, works: list[dict[str, Any]], w: dict[str, Any]) -> bool:
    """A `waiting` work waits on the owner when no open child of its own holds it (W6 h)."""
    return not any(
        x["parent_id"] == w["id"] and x["status"] in OR.OPEN for x in works if x is not w
    )


async def _why_not_woken(tx: Tx, w: dict[str, Any]) -> str:
    lock = await tx.scalar("SELECT control.lock_state(:co)", co=w["company_id"])
    if lock is not None:
        return "شرکت قفل است و تا قفل باز نشود کار راه نمیافتد"
    if not w.get("a_code"):
        return "کار مسئولی ندارد"
    if w["status"] not in OR.OPEN:
        return "کار بسته شده است"
    return "کار راه نیفتاد؛ دوباره تلاش میشود"


async def _reopen_delivered(tx: Tx, ref: str, works: list[dict[str, Any]]) -> dict[str, Any] | None:
    """⟨1.19⟩ §37.4 the root work a word after delivery goes back to: the holder's delivered root
    (its assignee is the holder), else any delivered root (a `delivered` one before an accepted
    `done` one, the newest first), back to `in_progress` (work.reopen). None when the order has
    no delivered root."""
    roots = [w for w in works if w["is_root"] and w["status"] in DELIVERED]
    if not roots:
        return None
    h = await holder(tx, ref)
    code = h["code"] if h else None
    roots.sort(
        key=lambda w: (
            w["a_code"] != code,
            w["status"] != "delivered",
            -w["updated_at"].timestamp(),
        )
    )
    for w in roots:
        if await tx.scalar("SELECT work.reopen(:w)", w=w["id"]):
            await W.event(
                tx, w, "reopened", OWNER, {"order": ref, "why": "owner_word_after_delivery"}
            )
            return {**w, "status": "in_progress"}
    return None


async def reply(tx: Tx, ref: str, text: str) -> dict[str, Any]:
    """The owner's word on the order: a step, the turn cleared, and the askers' works (else the
    holder's) run again at once. Answers {work_ref, run_id, woken: [work refs], why_fa}; a reply
    that wakes nothing says why in a step (never a silent «runs again»). ⟨1.19⟩ §37.4 with nothing
    open but the session not closed (`ready`), the word is a revision: the holder's delivered root
    work goes back to `in_progress` with the word as its next step and the holder is woken; only an
    order with nothing delivered or open left answers 409."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    if rep["ended_at"] is not None:
        raise ApiError(409, "validation_failed", "the order has ended",
                       message_fa="این جلسه بسته شده است؛ برای ادامه آن را دوباره باز کنید.")  # fmt: skip
    words = " ".join(text.split())[:2000]
    if len(words) < 1:
        raise ApiError(422, "validation_failed", fields={"text": "empty"},
                       message_fa="متن پاسخ خالی است.")  # fmt: skip
    turn = OR._j(rep.get("turn")) or {}
    order = await OR.load_order(tx, ref)
    assert order is not None
    works = await OR.tree(tx, OR.root_refs(order))
    targets: list[dict[str, Any]] = []
    for code in _asker_codes(turn):
        t = next((w for w in works if w["a_code"] == code and w["status"] in OR.OPEN), None)
        if t is not None and all(x["id"] != t["id"] for x in targets):
            targets.append(t)
    if not targets:
        root = next((w for w in works if w["is_root"] and w["status"] in OR.OPEN), None)
        if root is not None:
            targets.append(root)
    revised = None
    if not targets:
        revised = await _reopen_delivered(tx, ref, works)
        if revised is not None:
            targets.append(revised)
    if not targets:
        raise ApiError(409, "validation_failed", "no open work on the order",
                       message_fa="کار بازی روی این فرمان نمانده است؛ فرمان تازه بدهید.")  # fmt: skip
    steps = [OR._step(OWNER_FA, words)]
    if revised is not None:
        steps.append(OR._step("سامانه", REVISION_FA))
    if rep["talk_stopped_at"] is not None:
        # ⟨1.17⟩ W6 a: a reply after a talk-loop stop restarts the order deliberately
        await tx.exec(
            "UPDATE owner.order_reports SET talk_stopped_at = NULL WHERE id = :id", id=rep["id"]
        )
        steps.append(OR._step("سامانه", RESTARTED_FA))
    await tx.exec(
        """UPDATE owner.order_reports SET turn = NULL, last_step_at = now(),
               progress_nudged_at = NULL, owner_told_at = NULL, updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
    )
    woken: list[str] = []
    runs: list[str] = []
    why: str | None = None
    for t in targets:
        if t["status"] == "waiting" and await _waits_on_owner(tx, works, t):
            await tx.exec(
                "UPDATE work.work SET status = 'in_progress' WHERE id = :w AND status = 'waiting'",
                w=t["id"],
            )
        run_id = await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=t["id"], r=f"owner_reply:{ref}"
        )
        if run_id is not None:
            woken.append(str(t["ref"]))
            runs.append(str(run_id))
        elif why is None:
            why = await _why_not_woken(tx, t)
    if not woken and why:
        steps.append(OR._step("سامانه", f"جواب رسید ولی {why}"))
    await OR._append_steps(tx, rep["id"], steps)
    return {
        "work_ref": targets[0]["ref"],
        "run_id": runs[0] if runs else None,
        "woken": woken,
        "why_fa": None if woken else why,
    }


# -------------------------------------------------------------- the talk --
async def open_talk(ctx: Any, tx: Tx, ref: str) -> str | None:
    """The order's live talk with its holder: the one it has, else a new one (work mode). ⟨1.17⟩
    §35.1 opened on routing for every order; the secretary holds an order nobody can and her
    first turn proposes the hire."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    if rep.get("conversation_ref"):
        return str(rep["conversation_ref"])
    h = await holder(tx, ref)
    if h is None:
        return None
    from hq_api.talk import service as TS
    from hq_api.talk import store

    order = await OR.load_order(tx, ref)
    text = " ".join(((order or {}).get("text") or "").split())
    key = persona_key(h)
    try:
        conv = await TS.new_conversation(
            ctx, tx, key, "work", f"فرمان: {text}"[:200], employee_code=str(h["code"])
        )
    except ApiError:
        key = "secretary"
        conv = await TS.new_conversation(ctx, tx, key, "work", f"فرمان: {text}"[:200])
        h = await secretary(tx) or h
    await tx.exec(
        """UPDATE talk.conversations SET order_ref = :r, holder = :h, holder_code = :c
           WHERE id = :id""",
        r=ref,
        h=key,
        c=h["code"],
        id=conv["id"],
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
    kit = OR.kit_of(order or {})
    hire: dict[str, Any] | None = None
    if turn:
        first = f"سلام، {who} هستم. منتظر جواب شما هستم: {turn['question_fa']}"
    elif kit is not None:
        first = (
            f"سلام، {who} هستم. پیش‌نمایش شرکت تازه آماده است؛ تا مُهر نکنید چیزی ساخته نمیشود. "
            "همین‌جا بگویید چه چیزی را عوض کنم."
        )
    elif h.get("work_id") is None:
        company = _company_of(order or {})
        first = (
            f"سلام، {who} هستم. این فرمان هنوز مسئولی ندارد؛ کسی در شرکت نیست که آن را بگیرد. "
            "پیشنهادم استخدام یک مدیرعامل است؛ با کارت زیر همین حالا انجام میشود."
        )
        hire = {"company": company, "role": "ceo"}
    elif order and order.get("pace") == "step":
        first = f"سلام، {who} هستم و این فرمان با من است. مرحله‌به‌مرحله با شما جلو میروم؛ بگویید از کجا شروع کنم."
    else:
        first = f"سلام، {who} هستم و این فرمان با من است. هر چه بگویید روی همین فرمان انجام میشود."
    tid = await post_turn(tx, conv, key, first, first)
    if hire is not None and hire["company"]:
        row = await store.add_card(
            tx,
            conversation_id=conv["id"],
            turn_id=tid,
            company_id=conv["company_id"],
            kind="hire",
            title_fa=f"استخدام مدیرعامل برای {hire['company']}",
            body_fa="این فرمان بی‌مسئول مانده است؛ با استخدام، مدیرعامل تازه آن را میگیرد.",
            payload=hire,
        )
        holding = await tx.one("SELECT code FROM core.companies WHERE kind = 'holding' LIMIT 1")
        await events.emit(tx, holding["code"], "talk.card", conv["ref"],
                          {"card": str(row["id"]), "kind": "hire", "state": "offered"})  # fmt: skip
    return str(conv["ref"])


def _company_of(order: dict[str, Any]) -> str | None:
    for r in OR._j(order.get("routes")) or []:
        if isinstance(r, dict) and r.get("company"):
            return str(r["company"])
    given = OR._j(order.get("route"))
    if isinstance(given, dict) and given.get("companies"):
        return str(given["companies"][0])
    return None


async def talk_brief(tx: Tx, order_ref: str) -> dict[str, Any] | None:
    """What a talk bound to an order knows of it (by code): the order, how it is carried out, the
    owner's open turn, the plan, the last steps and what blocks it."""
    rep = await tx.first("SELECT * FROM owner.order_reports WHERE ref = :r", r=order_ref)
    order = await OR.load_order(tx, order_ref)
    if rep is None or order is None:
        return None
    from hq_api.domain import sessions as SE

    steps = OR._j(rep["steps"]) or []
    tasks = await SE.tasks_of(tx, rep["order_id"])
    out = {
        "order": order_ref,
        "text": " ".join(str(order.get("text") or "").split())[:1500],
        "pace": order.get("pace") or "auto",
        "state": rep["state"],
        "badge": rep.get("badge"),
        "owner_turn": OR._j(rep.get("turn")),
        "plan": [
            f"{t['n']}. {t['title_fa']} [{t['state']}]" for t in tasks if t["state"] != "dropped"
        ],
        "steps": [f"{s.get('who_fa')}: {s.get('what_fa')}" for s in steps[-DIALOGUE_STEPS:]],
        "blockers": [b.get("title_fa") for b in OR._j(rep["blockers"]) or []],
        "outputs": [o.get("title_fa") for o in OR._j(rep["outputs"]) or []],
        # ⟨1.18⟩ §36.3 the owner's files of this order, newest first: read one with files.read
        # {"file_id": id}; a font is used by naming it (overlay.font_file_id, a media item's style)
        "files": [_file_line(f) for f in await F.of_order(tx, rep["order_id"])],
    }
    # ⟨2026-11-07⟩ W9 C: the session's last failed cards, for the holder to fix itself
    failed = await failed_cards(tx, rep.get("conversation_ref"))
    if failed:
        out["failed_cards"] = failed
    return out


FAILED_CARDS = 3


async def failed_cards(tx: Tx, conversation_ref: str | None) -> list[dict[str, Any]]:
    """⟨2026-11-07⟩ W9 C: the last failed cards of a session (kind, title, the exact refusal and
    the payload fields involved), newest first, so the holder reads why and offers the card again
    corrected, instead of sending the owner elsewhere."""
    if not conversation_ref:
        return []
    rows = await tx.all(
        """SELECT c.kind, c.title_fa, c.reason_fa, c.payload FROM talk.cards c
           JOIN talk.conversations v ON v.id = c.conversation_id
           WHERE v.ref = :r AND c.state = 'failed' ORDER BY c.updated_at DESC LIMIT :l""",
        r=conversation_ref,
        l=FAILED_CARDS,
    )
    out = []
    for r in rows:
        payload = OR._j(r["payload"]) or {}
        out.append(
            {
                "kind": r["kind"],
                "title_fa": r["title_fa"],
                "reason_fa": r["reason_fa"],
                "payload": {str(k): str(v)[:300] for k, v in payload.items() if k != "asked"},
            }
        )
    return out


def _file_line(f: dict[str, Any]) -> dict[str, Any]:
    ref = F.render(f)
    out: dict[str, Any] = {"id": str(ref.id), "name": ref.name, "kind": ref.kind}
    if ref.meta is not None and ref.meta.family:
        out["family"] = ref.meta.family
    return out


# ---------------------------------------------------------------- the files --
FILE_STEP_FA = "فایل از مدیر کل: "
SYSTEM_FA = "سامانه"


def _name(name: str) -> str:
    return " ".join("".join(ch for ch in name if ch.isprintable()).split())[:120] or "فایل"


async def add_files(
    tx: Tx, ref: str, files: list[dict[str, Any]], turn_id: UUID | None
) -> list[UUID]:
    """⟨1.18⟩ §36.3 the owner's files of a session's turn go with its order: each one a file of
    the order (once) and a step «فایل از مدیر کل: <name>» (the owner's own name for it, never
    rewritten). The ids added."""
    rep = await OR.ensure(tx, ref)
    if rep is None or not files:
        return []
    holding = await OR._holding(tx)
    added: list[UUID] = []
    steps: list[dict[str, Any]] = []
    for f in files:
        new = await tx.scalar(
            """INSERT INTO owner.order_files (company_id, order_id, file_id, turn_id, added_at)
               VALUES (:co, :o, :f, :t, clock_timestamp())
               ON CONFLICT (order_id, file_id) DO NOTHING RETURNING id""",
            co=holding["id"],
            o=rep["order_id"],
            f=f["id"],
            t=turn_id,
        )
        if new is not None:
            added.append(f["id"])
            steps.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "who_fa": SYSTEM_FA,
                    "what_fa": FILE_STEP_FA + _name(str(f["name"])),
                }
            )
    await OR._append_steps(tx, rep["id"], steps)
    return added


async def dialogue(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    """For a run on an order's work: the order and its dialogue with the owner (newest last)."""
    ref = await OR.order_of_work(tx, work_id)
    if ref is None:
        return None
    return await talk_brief(tx, ref)
