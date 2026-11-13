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

import itertools
import json
import logging
import re
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

log = logging.getLogger("hq_api.order_turns")

OWNER_FA = "مدیر کل"
DIALOGUE_STEPS = 12
MAX_ASKS = 10  # the asks one open owner's turn keeps (each asker is woken by the reply)
# ⟨1.23⟩ §41.2 what the holder's brief says about the plan (its run brief and «The order you hold»)
PLAN_INSTRUCTION = (
    "Work the plan task by task, in order: do the next open task now; tick each one you finish "
    "with `order.progress` (`done: [n]`, one plain Persian line of what it produced). The moment a "
    "task cannot go on (something only the owner knows, decides or must connect), ask the owner ONE "
    "short question with `order.ask` and finish the run. Never stop silently: a run that ends "
    "without a step, a question or a deliverable is a stall the owner sees at once. A task that "
    "makes something none of your tools makes (a motion graphic or any video made without a "
    "camera, a site page, a PDF report, a data file, anything) goes to the holding's workshop "
    "with `workshop.run` (⟨2026-11-09⟩ Claude Code with hands on the hub): write the whole ask and "
    "finish the run; its files come back into this session and you ask the owner «تأیید یا "
    "اصلاح؟». Never answer that a tool is missing. A filmed video (a person on camera) is done "
    "when the media team delivers the «بسته‌ی ساخت ویدیو» (script, shot list, on-screen text, "
    "voice text, caption, hashtags, cover prompt) for the owner to shoot. Publishing, after the "
    "owner approves, goes on through IG-Hub. Instagram, for every company, is read and published "
    "through IG-Hub: never an owner's step for it. ⟨2026-11-09⟩ In a STEP-BY-STEP order («با من»): "
    "a step you hand to a colleague is done only when its output came back, so hand it over and "
    "finish the run without asking (its output wakes you), then report the whole step and ask; "
    "while the owner has not answered, nothing of this order runs, yours or a colleague's."
)
# ⟨1.23⟩ §41.2 an item of the owner's numbered list: Persian, Arabic-Indic or Latin digits, then
# «-», «.», «)», «:» or «،»
NUM_ITEM = re.compile(r"^\s*[(\[]?([0-9۰-۹٠-٩]{1,2})\s*[-.)\]:،–—]\s*(.*?)\s*$")
INLINE_ITEM = re.compile(r"(?:(?<=\s)|^)([0-9۰-۹٠-٩]{1,2})\s*[-.)،:]\s+")
PLAN_STEP_FA = "برنامه: {n} کار از حرف مدیر کل"
PLAN_ASIDE_FA = "؛ برنامه همین گام‌های توست و به ترتیب خودت، برنامه‌ی قبلی مسئول کنار رفت"
MAX_PLAN_ITEMS = 30
# ⟨2026-11-08⟩ audit B1: in a working session the owner's word is the order's word by code; a
# question is answered by the talk alone
QUESTION_MARKS = ("؟", "?")
QUESTION_WORDS = (
    "چرا", "چه", "چی", "چیه", "چیست", "کی", "کجا", "کجاست", "آیا", "چطور", "چطوری", "چگونه", "کدام",
    "کدوم", "چند", "چندتا", "مگه", "مگر", "یعنی",
)  # fmt: skip
OWNER_SAID = 3
# ⟨2026-11-09⟩ the owner's word on an order is as long as a talk turn (TalkTurnIn.text): F-0013 and F-0014's
# replies were longer than the old 2000 and the hub refused them (422 `text`)
OWNER_WORD_MAX = 10000
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
    lead = "**سؤال از تو** · " if ask else ""  # ⟨2026-11-11⟩ the owner is «تو»
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
def keep_asks(asks: list[dict[str, Any]], cap: int = MAX_ASKS) -> list[dict[str, Any]]:
    """At most `cap` asks: the first (the turn's asker) and the newest always stay. An asker's
    repeated ask goes before anyone's only one, so the reply still wakes every asker it can."""
    out = list(asks)

    def code(a: dict[str, Any]) -> Any:
        by = a.get("by")
        return by.get("code") if isinstance(by, dict) else None

    while len(out) > max(cap, 2):
        codes = [code(a) for a in out]
        repeated = [i for i in range(1, len(out) - 1) if codes.count(codes[i]) > 1]
        out.pop(repeated[0] if repeated else 1)
    return out


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
    n_asks = len(asks)  # the line's key, as before the cap
    # The newest ask is kept (asks[:10] dropped it): its asker is woken by the reply too.
    asks = keep_asks(asks)
    first = asks[0]
    turn = {
        **first,
        "question_fa": "\n".join(str(a["question_fa"]) for a in asks)[:4000],
        "asks": asks,
    }
    await tx.exec(
        """UPDATE owner.order_reports SET turn = CAST(:t AS jsonb), last_step_at = now(),
               updated_at = now()
           WHERE id = :id""",
        t=json.dumps(turn, ensure_ascii=False),
        id=rep["id"],
    )
    await OR._append_steps(tx, rep["id"], [OR._step(who_name, "سؤال از تو: " + question)])
    await OR._close_nudges(tx, ref, "مسئول از مدیر کل پرسید (order.ask)")
    from hq_api.domain import session_activity as SA

    await SA.emit_safe(tx, ref, SA.make_line(
        f"ask:{ref}:{n_asks}", who_name, "سؤال از تو: " + question, kind="ask",
        state="running", company=who.company,
    ))  # fmt: skip  # ⟨1.24⟩ §42.2
    talked = await to_talk(tx, rep, who.code, question, ask=True)
    order = await OR.load_order(tx, ref)
    text = " ".join(((order or {}).get("text") or "").split())[:80]
    holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="decision",
        title_fa=f"نوبت توست: {text}"[:300],
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


def _asker_works(works: list[dict[str, Any]], turn: dict[str, Any]) -> list[dict[str, Any]]:
    """The open works of whoever asked the owner (one per asker, in the order they asked)."""
    targets: list[dict[str, Any]] = []
    for code in _asker_codes(turn):
        t = next((w for w in works if w["a_code"] == code and w["status"] in OR.OPEN), None)
        if t is not None and all(x["id"] != t["id"] for x in targets):
            targets.append(t)
    return targets


async def _wake_for_owner(
    tx: Tx, works: list[dict[str, Any]], t: dict[str, Any], reason: str
) -> Any:
    """A work that waited for the owner runs again on his word (`waiting` → `in_progress` when no
    open child of its own holds it). Answers the run id, or None when nothing was woken."""
    if t["status"] == "waiting" and await _waits_on_owner(tx, works, t):
        await tx.exec(
            "UPDATE work.work SET status = 'in_progress' WHERE id = :w AND status = 'waiting'",
            w=t["id"],
        )
    return await tx.scalar("SELECT work.wake_assignee(:w, :r)", w=t["id"], r=reason)


async def answered_by_nudge(tx: Tx, ref: str, rep: dict[str, Any]) -> list[str]:
    """⟨2026-11-10⟩ «ادامه بده» while the order waits for the owner is his answer to whoever
    asked: the turn is cleared, a talk-loop stop is lifted, and every asker's work runs again
    with his word (a colleague who asked is not left asleep because only the holder is woken).
    Answers the refs woken; the holder itself is woken by the caller."""
    turn = OR._j(rep.get("turn")) or {}
    order = await OR.load_order(tx, ref)
    works = await OR.tree(tx, OR.root_refs(order)) if order is not None else []
    if rep.get("talk_stopped_at") is not None:
        await OR._append_steps(tx, rep["id"], [OR._step("سامانه", RESTARTED_FA)])
    await tx.exec(
        """UPDATE owner.order_reports SET last_step_at = now(), progress_nudged_at = NULL,
               owner_told_at = NULL, turn = NULL, talk_stopped_at = NULL, updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
    )
    woken: list[str] = []
    for t in _asker_works(works, turn):
        if await _wake_for_owner(tx, works, t, f"nudge:{ref}") is not None:
            woken.append(str(t["ref"]))
    await OR.resume_held(tx, ref)
    return woken


async def reply(tx: Tx, ref: str, text: str) -> dict[str, Any]:
    """The owner's word on the order: a step, the turn cleared, and the askers' works (else the
    holder's) run again at once. Answers {work_ref, run_id, woken: [work refs], why_fa}; a reply
    that wakes nothing says why in a step (never a silent «runs again»). ⟨1.19⟩ §37.4 with nothing
    open but the session not closed (`ready`), the word is a revision: the holder's delivered root
    work goes back to `in_progress` with the word as its next step and the holder is woken; only an
    order with nothing delivered or open left answers 409."""
    # an empty word is refused first, whatever the order
    words = " ".join(text.split())[:OWNER_WORD_MAX]
    if len(words) < 1:
        raise ApiError(422, "validation_failed", fields={"text": "empty"},
                       message_fa="متن پاسخ خالی است.")  # fmt: skip
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa="این فرمان پیدا نشد.")
    if rep["ended_at"] is not None:
        raise ApiError(409, "validation_failed", "the order has ended",
                       message_fa="این جلسه بسته شده است؛ برای ادامه آن را دوباره باز کن.")  # fmt: skip
    turn = OR._j(rep.get("turn")) or {}
    order = await OR.load_order(tx, ref)
    assert order is not None
    works = await OR.tree(tx, OR.root_refs(order))
    targets = _asker_works(works, turn)
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
                       message_fa="کار بازی روی این فرمان نمانده است؛ فرمان تازه بده.")  # fmt: skip
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
        run_id = await _wake_for_owner(tx, works, t, f"owner_reply:{ref}")
        if run_id is not None:
            woken.append(str(t["ref"]))
            runs.append(str(run_id))
        elif why is None:
            why = await _why_not_woken(tx, t)
    if not woken and why:
        steps.append(OR._step("سامانه", f"جواب رسید ولی {why}"))
    # ⟨2026-11-09⟩ «با من»: what waited for this answer (a colleague's part) goes on too
    await OR.resume_held(tx, ref)
    await OR._append_steps(tx, rep["id"], steps)
    # ⟨1.23⟩ §41.2 a numbered list is the plan: read from his own lines (a list item per line,
    # «۱.متن» or «1– …»), not the one-line step text, else the line-based parser never runs
    await plan_from_owner(tx, ref, text[: 2 * OWNER_WORD_MAX])
    return {
        "work_ref": targets[0]["ref"],
        "run_id": runs[0] if runs else None,
        "woken": woken,
        "why_fa": None if woken else why,
    }


# ------------------------------------------------------------ the owner's plan --
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def numbered_items(text: str) -> list[str]:
    """⟨1.23⟩ §41.2 the items of a numbered list in the owner's words: lines that start with a
    number and a mark («۱ -», «1.», «۱)», «2:»), each item possibly running over the lines that
    follow; two items at least, else nothing. A list written in one line (its numbers running
    1, 2, 3 …) is read too."""
    items: list[str] = []
    cur: list[str] | None = None
    for raw in (text or "").splitlines():
        m = NUM_ITEM.match(raw)
        if m:
            if cur is not None:
                items.append(" ".join(" ".join(cur).split()))
            cur = [m.group(2)]
        elif cur is not None and raw.strip():
            cur.append(raw.strip())
        elif cur is not None and not raw.strip():
            continue
    if cur is not None:
        items.append(" ".join(" ".join(cur).split()))
    if len(items) < 2:
        items = []
        one = " ".join((text or "").split())
        parts = INLINE_ITEM.split(one)
        # parts: [lead, n1, text1, n2, text2, …]
        if len(parts) >= 5:
            seq = [int(p.translate(_DIGITS)) for p in parts[1::2]]
            if seq[0] == 1 and all(b == a + 1 for a, b in itertools.pairwise(seq)):
                items = [" ".join(p.split()) for p in parts[2::2]]
    out = [i for i in items if len(i) >= 2]
    return out[:MAX_PLAN_ITEMS] if len(out) >= 2 else []


async def plan_from_owner(tx: Tx, ref: str, text: str) -> int:
    """⟨1.23⟩ §41.2 the owner's numbered steps become the session's plan tasks, in order, by code
    (an item the plan already has is not added again); one step «برنامه: N کار از حرف مدیر کل».
    ⟨2026-11-10⟩ His steps ARE the plan, in his order: the holder's own tasks that are still open
    step aside (dropped) and the plan is numbered again from 1, done tasks first. Before, his
    nine steps were appended after the holder's five, so «ساخت ریلز» (the holder's 4) ran before
    his «متن گفتار» and «صدا» (which had become 7 and 8). Answers how many were added."""
    from hq_api.domain import sessions as SE

    items = numbered_items(text)
    if not items:
        return 0
    rep = await OR.ensure(tx, ref)
    if rep is None or rep.get("ended_at") is not None:
        return 0

    def norm(v: Any) -> str:
        return " ".join(str(v).split())

    tasks = await SE.tasks_of(tx, rep["order_id"])
    live = {norm(t["title_fa"]) for t in tasks if t["state"] != "dropped"}
    gone = {norm(t["title_fa"]) for t in tasks if t["state"] == "dropped"}
    wanted: list[str] = []  # his steps, in his order
    for item in items:
        title = norm(HZ.humanize(item) or item)[:300]
        if title and title not in wanted:
            wanted.append(title)
    # a step the plan already has (the holder wrote it, or an earlier word of his) stays as it is;
    # one he removed himself is not brought back by a repeat of the list
    titles = [t for t in wanted if t not in live and t not in gone]
    if not titles:
        return 0  # the same list again: nothing is added, nothing steps aside
    aside = [
        t["id"]
        for t in tasks
        if t["by"] == "agent"
        and t["state"] in ("todo", "doing")
        and norm(t["title_fa"]) not in wanted
    ]
    if aside:
        await tx.exec(
            """UPDATE owner.session_tasks SET state = 'dropped', updated_at = now()
               WHERE id = ANY(:ids)""",
            ids=aside,
        )
    for title in titles:
        await SE.add_task(tx, rep, title_fa=title, by="owner", who_fa=OWNER_FA)
    await renumber_plan(tx, rep["order_id"], first=wanted)
    line = PLAN_STEP_FA.format(n=len(titles))
    if aside:
        line += PLAN_ASIDE_FA
    await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, line)])
    await SE.remember(tx, rep["id"], line)
    return len(titles)


async def renumber_plan(tx: Tx, order_id: Any, *, first: list[str] | None = None) -> None:
    """The plan's numbers run 1, 2, 3 … over what is still in it: done tasks first (in the order
    they stood), then the open ones — the owner's own list (`first`, its titles in his order)
    before any other — then the dropped ones. A number the owner reads is the place in the plan."""
    from hq_api.domain import sessions as SE

    tasks = await SE.tasks_of(tx, order_id)
    place = {t: i for i, t in enumerate(first or [])}

    def title(t: dict[str, Any]) -> str:
        return " ".join(str(t["title_fa"]).split())

    done = [t for t in tasks if t["state"] == "done"]
    open_ = [t for t in tasks if t["state"] not in ("done", "dropped")]
    his = sorted((t for t in open_ if title(t) in place), key=lambda t: place[title(t)])
    rest = [t for t in open_ if title(t) not in place]
    order = done + his + rest + [t for t in tasks if t["state"] == "dropped"]
    for n, t in enumerate(order, start=1):
        if int(t["n"]) != n:
            await tx.exec("UPDATE owner.session_tasks SET n = :n WHERE id = :id", n=n, id=t["id"])


def is_question(text: str) -> bool:
    """Whether the owner's word is a question (a mark, or a question word first)."""
    one = " ".join((text or "").split())
    if not one:
        return False
    if any(m in one for m in QUESTION_MARKS):
        return True
    first = one.split()[0].strip("«»\"'،,")
    return first in QUESTION_WORDS


async def owner_word(tx: Tx, ref: str, text: str, *, work_mode: bool) -> dict[str, Any]:
    """⟨2026-11-08⟩ audit B1 (the owner: his nine steps reached nobody): in a working session every
    owner turn that is not a question is the order's word by code — `reply` (the step «مدیر کل:
    …», the open turn cleared, the holder woken with the dialogue in its brief) — and a numbered
    list in it is the plan (§41.2). A question, or a consult-mode talk, feeds the plan only. An
    order with nothing to wake (ended, nothing open or delivered) is left to the talk. Answers
    {replied, woken, tasks}."""
    out: dict[str, Any] = {"replied": False, "woken": [], "tasks": 0}
    words = " ".join((text or "").split())
    if not words:
        return out
    if work_mode and not is_question(words):
        try:
            async with tx.conn.begin_nested():
                got = await reply(tx, ref, text)  # its own lines: the plan is read from them
            out.update(replied=True, woken=got["woken"])
            return out  # reply() read the plan already
        except ApiError:
            pass  # ended, or nothing open: the talk alone carries it
    out["tasks"] = await plan_from_owner(tx, ref, text[: 2 * OWNER_WORD_MAX])
    return out


async def owner_said(tx: Tx, conversation_ref: str | None, n: int = OWNER_SAID) -> list[str]:
    """⟨2026-11-08⟩ audit B1: the owner's last turns in the session, verbatim (newest last), for
    the holder's run brief: the prose a plan task's title cannot hold (a slogan, a speaker, «every
    time different»)."""
    if not conversation_ref:
        return []
    rows = await tx.all(
        """SELECT t.text FROM talk.turns t JOIN talk.conversations c ON c.id = t.conversation_id
           WHERE c.ref = :r AND t.by_kind = 'owner' AND t.text IS NOT NULL AND t.text <> ''
           ORDER BY t.n DESC LIMIT :n""",
        r=conversation_ref,
        n=n,
    )
    return [str(r["text"])[:4000] for r in reversed(rows)]


# ------------------------------------------------------------ never a silent stall --
async def wake_holder(tx: Tx, ref: str, reason: str) -> dict[str, Any]:
    """⟨1.23⟩ §41.3 the holder's open root work runs again (one queued run per work); answers
    {run_id, work_ref, why_fa}."""
    from hq_api.domain import session_activity as SA

    return await SA.wake_holder(tx, ref, reason)


async def wake_or_say(tx: Tx, ref: str, reason: str) -> dict[str, Any]:
    """⟨2026-11-08⟩ audit M11: the holder woken, or a step that says why not («مسئول بیدار نشد:
    …»: a lock, a closed work, a stopped order) — never a silent NULL. The one helper every cause
    uses (a hire joined, a child delivered, the pace switched, the session reopened)."""
    from hq_api.domain import session_activity as SA

    out = await SA.wake_holder(tx, ref, reason)
    if out["run_id"] is None and out.get("why_fa"):
        rep = await OR.ensure(tx, ref)
        if rep is not None:
            await OR._append_steps(
                tx, rep["id"], [OR._step(SYSTEM_FA, SA.NOT_WOKEN_FA.format(why=out["why_fa"]))]
            )
    return out


async def on_child_closed(tx: Tx, work: dict[str, Any], what: str) -> dict[str, Any] | None:
    """⟨1.23⟩ §41.3 a child work (or a requested work) of an order was delivered or failed: the
    holder is woken so the order goes on (the holder itself delivering wakes nobody). Answers the
    wake, or None when the work is a root or belongs to no session."""
    if work.get("parent_id") is None and work.get("requested_by_work_id") is None:
        return None
    ref = await OR.order_of_work(tx, work["id"])
    if ref is None:
        return None
    rep = await OR.ensure(tx, ref)
    if rep is None or rep.get("ended_at") is not None:
        return None
    h = await holder(tx, ref)
    if h is None or h.get("work_id") is None or h["work_id"] == work["id"]:
        return None
    return await wake_or_say(tx, ref, f"child_{what}:{work['ref']}")


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
        first = f"سلام، {who} هستم. منتظر جواب تو هستم: {turn['question_fa']}"
    elif kit is not None:
        first = (
            f"سلام، {who} هستم. پیش‌نمایش شرکت تازه آماده است؛ تا مُهر نکنی چیزی ساخته نمیشود. "
            "همین‌جا بگو چه چیزی را عوض کنم."
        )
    elif h.get("work_id") is None:
        company = _company_of(order or {})
        first = (
            f"سلام، {who} هستم. این فرمان هنوز مسئولی ندارد؛ کسی در شرکت نیست که آن را بگیرد. "
            "پیشنهادم استخدام یک مدیرعامل است؛ با کارت زیر همین حالا انجام میشود."
        )
        hire = {"company": company, "role": "ceo"}
    elif order and order.get("pace") == "step":
        first = f"سلام، {who} هستم و این فرمان با من است. مرحله‌به‌مرحله با تو جلو میروم؛ بگو از کجا شروع کنم."
    else:
        first = f"سلام، {who} هستم و این فرمان با من است. هر چه بگویی روی همین فرمان انجام میشود."
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


# ⟨2026-11-10⟩ the owner: «جلسه‌ها پیش‌فرض مستقیم باشند» («این برو بیا و هی مهر بکن و اینو مجوز بده و
# بروکراسی اداری بازی … آزار و اذیت میده منو … مثل همین سشنی که من با تو صحبت میکنم»)
DIRECT_RULE = (
    "This session is DIRECT (the owner's default): you are the one who does this order, as one "
    "capable person with hands would. Read what you need, make it with your own tools and the "
    "workshop (`workshop.run`), show him the result and ask only what is truly his to decide. Do "
    "not delegate or split a step, do not raise a card for an internal thing, and do not send a "
    "part to the CEO, the CTO or another team when a tool of yours or the workshop does it. Hand "
    "a part over only when the owner names who should do it, or when the step needs a right you "
    "do not have (say which, in one line). A hire happens only when his own words ask for one: "
    "then `propose` it once and go on (the hub decides it at once, with no card for him). His "
    "«تأیید» in this session is his approval of what you showed him: never tell him to go and "
    "seal something elsewhere for an internal step."
)
# ⟨2026-11-11⟩ the owner's session F-0011 went silent for twelve hours after «پیش‌نویس متن از
# ChatGPT خواسته شد و در صف است»: the holder read a queued call as done and ended its run
ASYNC_RULE = (
    "A tool that answers `queued` or `running` has NOT finished: say so in one plain line, never "
    "as done. Two kinds. (1) substitute.call (an outside model's text or a creative), speech.make "
    "and workshop.run wake you when they end: carry on with the plan's other open tasks (or do "
    "that part yourself with your own model) and finish the run; the answer comes as a new work, "
    "a run `speech_done:` / `creative_done:` / `workshop_done:`, and a call that failed, was "
    "skipped or passed its deadline wakes you too, with the reason. (2) A tool answered with a "
    "`job` you poll yourself (server.exec, server.write, server.claude, hub.ops, and speech.make "
    "while your run still works): call it again with `{job}` until it is `done` or `failed`; "
    "nothing wakes you for those. Under `waiting_on` are this order's outside calls still "
    "pending, under `ended_without_answer` the ones that ended with no answer: never wait for "
    "those, do that part yourself."
)
IDLE_WAKE_RULE = (
    "WOKEN BY THE HUB ({k} of at most {cap}): nothing of this order is running — no run, no "
    "workshop turn, no outside call, no voice job — and the owner is not asked anything. {left} "
    "{ended}Continue task {n} now with your own tools and your own model, or ask the owner ONE "
    "short question with `order.ask` about what blocks you. Do not only narrate: a run that only "
    "reports with `order.progress` (or reads and writes nothing) marks this session «گیر کرد» "
    "to the owner at once."
)
# ⟨2026-11-11⟩ «با من»: the next task has not started and the owner has not said go; the wake
# never tells the holder to start it (step_rule binds the run)
IDLE_STEP_RULE = (
    "WOKEN BY THE HUB ({k} of at most {cap}): nothing of this order is running and the owner is "
    "not asked anything. This order is STEP BY STEP («با من»): task {n} «{title}» is next but the "
    "owner has not told you to start it. {ended}Do NOT start task {n}, even if you asked him "
    "«تأیید یا اصلاح؟» in plain words before: without his word no next task starts. Show the "
    "owner what the last task produced (or, if nothing is ready, where it stands) in one plain "
    "line and ask him with `order.ask` (so the session waits for him): «تأیید یا اصلاح؟», or "
    "whether to start task {n}. Do not only narrate: a "
    "run that only reports with `order.progress` marks this session «گیر کرد» to the owner at "
    "once."
)
IDLE_DONE_RULE = (
    "WOKEN BY THE HUB ({k} of at most {cap}): nothing of this order is running and every task of "
    "the plan is done. {ended}Deliver the final output now with `deliver` (the owner approves it "
    "in the session), or ask the owner with `order.ask` what the next step is."
)


def step_rule(nxt: dict[str, Any] | None) -> str:
    """⟨2026-11-10⟩ What a step-by-step order («با من») binds its holder to, said by code with the
    plan's next task in it (the owner: «چرا باید با من قدم‌به‌قدم جلو نره؟» — the holder read his
    «بیار مهر کنم» as leave to build a reel two steps early)."""
    head = (
        f"STEP BY STEP («با من»), enforced by the hub. The plan is the owner's, in his order; its "
        f"next open task is {nxt['n']}: «{nxt['title_fa']}». "
        if nxt
        else "STEP BY STEP («با من»), enforced by the hub. The plan has no open task: ask the "
        "owner what the next step is. "
    )
    return head + (
        "In this run do ONLY that task, and only when the owner's last word clearly tells you to "
        "start it (a plain yes, «شروع کن», «ادامه بده», or a clear choice of an option you "
        "offered). If his word asks for something else, or does not clearly choose (he asks to "
        "see or seal the cards, asks a question, gives a correction), do exactly what he asked, "
        "start NO task, and ask again in one short question. Never start a later task before an "
        "earlier open one, and never fold two tasks into one run. A task that makes something "
        "goes to the workshop with `workshop.run` and `task` set to that task's number: the hub "
        "refuses a turn for any other task. You can stop a workshop turn you started with "
        "`workshop.stop`: when the owner says it was wrong or says stop, stop it first, then "
        "answer. When a task's output is ready, show it, tick it (`order.progress`, `done`) and "
        "ask «تأیید یا اصلاح؟»; the next task starts only after his answer. A card that waits "
        "for his seal is shown to him in this session by the app: say which card it is, never "
        "send him to look for it."
    )


async def step_next(tx: Tx, work_id: Any) -> dict[str, Any] | None:
    """`{ref, n, title_fa}` of the next open plan task when the work's order is step by step
    («با من»), open, and has a plan; else None (a general order, no order, an empty plan)."""
    from hq_api.domain import sessions as SE

    ref = await OR.order_of_work(tx, work_id)
    if ref is None:
        return None
    row = await tx.first(
        """SELECT r.order_id FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
           WHERE r.ref = :r AND r.ended_at IS NULL AND o.pace = 'step'""",
        r=ref,
    )
    if row is None:
        return None
    tasks = [t for t in await SE.tasks_of(tx, row["order_id"]) if t["state"] != "dropped"]
    nxt = next((t for t in tasks if t["state"] == "doing"), None) or next(
        (t for t in tasks if t["state"] == "todo"), None
    )
    if nxt is None:
        return None
    return {"ref": ref, "n": int(nxt["n"]), "title_fa": str(nxt["title_fa"])}


async def talk_brief(
    tx: Tx, order_ref: str, *, work_id: UUID | None = None, for_run: bool = False
) -> dict[str, Any] | None:
    """What a talk bound to an order knows of it (by code): the order, how it is carried out, the
    owner's open turn, the plan, the last steps and what blocks it. ⟨2026-11-11⟩ `for_run`: the
    brief of a run (dialogue, a direct turn's hand-over), never of the owner's talk; `work_id`:
    that run's work (none: the holder's own). Only that work's own running run, when the idle
    sweep started it, reads the `wake` instruction."""
    rep = await tx.first("SELECT * FROM owner.order_reports WHERE ref = :r", r=order_ref)
    order = await OR.load_order(tx, order_ref)
    if rep is None or order is None:
        return None
    from hq_api.domain import sessions as SE

    steps = OR._j(rep["steps"]) or []
    tasks = [t for t in await SE.tasks_of(tx, rep["order_id"]) if t["state"] != "dropped"]
    nxt = next((t for t in tasks if t["state"] == "doing"), None) or next(
        (t for t in tasks if t["state"] == "todo"), None
    )
    direct_turn = await _direct_now(tx)
    out: dict[str, Any] = {
        "order": order_ref,
        "text": " ".join(str(order.get("text") or "").split())[:1500],
        "pace": order.get("pace") or "auto",
        "state": rep["state"],
        "badge": rep.get("badge"),
        "owner_turn": OR._j(rep.get("turn")),
        # ⟨1.23⟩ §41.2 the plan: the owner's numbered steps and the holder's `order.ack` steps
        "plan": [{"n": t["n"], "title": t["title_fa"], "state": t["state"]} for t in tasks],
        "plan_next": nxt["n"] if nxt else None,
        "plan_instruction": PLAN_INSTRUCTION,
        # ⟨2026-11-10⟩ every session of the owner is direct by default (his decision, contract
        # §44.3): a classic run of the holder works by the same rule (do it yourself, no
        # hand-over, no internal card). ⟨2026-11-11⟩ `direct_turn`: whether the workshop can hold
        # the holder's direct turn now (its runner >= direct.RUNNER_MIN)
        "direct": True,
        "direct_rule": DIRECT_RULE,
        "direct_turn": direct_turn,
        "async_rule": ASYNC_RULE,
        # ⟨2026-11-10⟩ «با من»: the rule of this run, by code, with the next task named
        **({"step_rule": step_rule(nxt)} if (order.get("pace") or "auto") == "step" else {}),
        # ⟨2026-11-08⟩ audit B1: the owner's last words in the session, verbatim
        "owner_said": await owner_said(tx, rep.get("conversation_ref")),
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
    # ⟨1.22⟩ §40.1 the session's memory («تا اینجا»), its playbooks and the company's last
    # sessions: a session of thousands of lines keeps its thread, and sessions are not islands
    from hq_api.domain import playbooks as PB
    from hq_api.domain import session_memory as MEM

    if rep.get("memory_md"):
        out["memory_md"] = str(rep["memory_md"])
    if rep.get("source_playbook"):
        out["source_playbook"] = str(rep["source_playbook"])
        # the holder adapts it: every key it needs (roles, schedules, briefs), the owner's turn
        # carries only the plain words (PB.markdown)
        try:
            async with tx.conn.begin_nested():
                pb = await PB.render(tx, await PB.row_of(tx, str(rep["source_playbook"])))
            out["source_playbook_definition"] = pb.model_dump(
                mode="json", include={"title_fa", "purpose_fa", "platform", "seats", "routines",
                                      "kpis", "connections", "rules_fa"},
            )  # fmt: skip
        except Exception:  # noqa: BLE001 - the brief never fails on a playbook it cannot read
            log.warning("the source playbook could not be read", extra={"order": order_ref})
    books = await PB.of_order(tx, order_ref)
    if books:
        out["playbooks"] = books
    related = await MEM.related(tx, order_ref, _company_of(order))
    if related:
        out["related_sessions"] = related
    if for_run and work_id is not None:
        # ⟨1.35⟩ §57.3 a run of a work the owner spoke to in a side talk: that talk's last lines
        from hq_api.domain import session_team as ST

        try:
            async with tx.conn.begin_nested():
                side = await ST.run_brief(tx, dict(rep), work_id)
            if side is not None:
                out["side_talk"] = side
        except Exception:  # noqa: BLE001 - the brief never fails on what it adds
            log.warning("the side talk could not be read", extra={"order": order_ref})
    # ⟨2026-11-11⟩ what works for the order outside a run, what ended without an answer, and,
    # for a run the idle sweep started, the explicit turn: nothing runs, do task N or ask
    try:
        async with tx.conn.begin_nested():
            out = await _outside_and_wake(tx, dict(rep), order, out, work_id, for_run=for_run)
    except Exception:  # noqa: BLE001 - the brief never fails on what it adds
        log.warning("the order's outside work could not be read", extra={"order": order_ref})
    return out


async def _direct_now(tx: Tx) -> bool:
    """Whether the workshop can hold a direct turn now (direct.server_for)."""
    from hq_api.domain import direct as DR

    try:
        async with tx.conn.begin_nested():
            return await DR.server_for(tx) is not None
    except Exception:  # noqa: BLE001 - not direct when it cannot be told
        return False


def _outside_line(c: dict[str, Any], *, ended: bool) -> dict[str, Any]:
    at = c.get("at") if ended else c.get("created_at")
    line: dict[str, Any] = {
        "who": c.get("who_fa"),
        "makes": c.get("seat_fa") if ended else c.get("doing_fa"),
        "at": at.isoformat() if isinstance(at, datetime) else at,
    }
    if ended:
        line["state"] = c.get("state")
        line["why"] = c.get("code") or c.get("why_fa")
    else:
        dl = c.get("deadline_at")
        line["deadline"] = dl.isoformat() if isinstance(dl, datetime) else dl
    return line


async def _outside_and_wake(
    tx: Tx,
    rep: dict[str, Any],
    order: dict[str, Any],
    out: dict[str, Any],
    work_id: UUID | None,
    *,
    for_run: bool,
) -> dict[str, Any]:
    from hq_api.domain import session_activity as SA

    works = await OR.tree(tx, OR.root_refs(order))
    ids = [w["id"] for w in works]
    since = await SA.owner_since(tx, rep, ids)
    pending = await SA.pending_outside(tx, works)
    ended = await SA.ended_outside(tx, works, since)
    if pending:
        out["waiting_on"] = [_outside_line(c, ended=False) for c in pending]
    if ended:
        out["ended_without_answer"] = [_outside_line(c, ended=True) for c in ended[:10]]
    if not for_run:
        return out  # the owner's talk never reads the hub's wake instruction
    if work_id is None:
        h = await holder(tx, str(rep["ref"]))
        work_id = h.get("work_id") if h else None
    if work_id is None:
        return out
    # the briefed work's own running run (never a colleague's run on another work of the order)
    reason = await tx.scalar(
        """SELECT r.reason FROM agents.runs r WHERE r.work_id = :w AND r.state = 'running'
             AND r.trigger = 'work' ORDER BY r.started_at DESC NULLS LAST LIMIT 1""",
        w=work_id,
    )
    if not OR.base_reason(reason).startswith("session_idle:"):
        return out
    k = len([w for w in await SA.idle_wakes(tx, rep, ids, since) if not w["retry"]]) or 1
    # the open tasks as the hub counts them (one handed to a work that delivered is done)
    open_tasks = await SA.open_tasks_of(tx, rep.get("order_id"))
    nxt = open_tasks[0] if open_tasks else None
    said = "; ".join(
        f"{c['who_fa']} «{c['seat_fa']}» ({c.get('code') or c['why_fa']})" for c in ended[:5]
    )
    ended_txt = (
        f"These ended without an answer since the owner's last word: {said}. " if said else ""
    )
    if nxt is None:
        wake = IDLE_DONE_RULE.format(k=k, cap=SA.IDLE_WAKES_MAX, ended=ended_txt)
    elif (order.get("pace") or "auto") == "step" and nxt["state"] == "todo":
        wake = IDLE_STEP_RULE.format(
            k=k, cap=SA.IDLE_WAKES_MAX, n=nxt["n"], title=nxt["title_fa"], ended=ended_txt
        )
    else:
        left = (
            "Open tasks of the plan: "
            + "; ".join(f"{t['n']} «{t['title_fa']}»" for t in open_tasks)[:1500]
            + "."
        )
        wake = IDLE_WAKE_RULE.format(
            k=k, cap=SA.IDLE_WAKES_MAX, left=left, ended=ended_txt, n=nxt["n"]
        )
    return {"wake": wake, **out}  # first: the run reads it before anything else


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
    return await talk_brief(tx, ref, work_id=work_id, for_run=True)
