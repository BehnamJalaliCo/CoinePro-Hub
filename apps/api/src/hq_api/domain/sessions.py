"""Every order a session (contract §35.1-§35.3, §35.7; the owner, 2026-11-06).

«هر فرمان من باید یک سشن خودش رو داشته باشه تا بتونیم به نتیجه برسونیم و کار رو که اوکی کردیم و همه
چی تموم شد سشن بایگانی بشه یا پاک بشه»

    the session     the order itself: its report (owner.order_reports), its live talk (§34.2) and
                    its plan (owner.session_tasks). It opens with the order and never ends by
                    itself: `close` (the owner's OK) is the only end; `reopen` undoes it; `hide`
                    takes it off every list (nothing is deleted).
    the badge       by code (§35.2): closed · your_turn · ready · stuck · moving; a change streams
                    `session.updated` (topic orders)
    the brief       «چه شد · حالا چه · از تو چه», always filled
    participants    the holder, people (any persona key) and players (ChatGPT, Gemini, DeepSeek
                    through their seats), kept in the talk's `present`
    tasks           the holder's steps (`order.ack`) and the owner's own lines, ticked as they go
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from hq_api import events, pagination
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import notify
from hq_api.domain import order_report as OR
from hq_api.domain import session_activity as SA
from hq_api.domain.session_shapes import (
    Badge,
    Brief,
    Holder,
    Participant,
    SessionCard,
    SessionState,
    SessionTask,
    TaskCount,
)
from hq_api.errors import ApiError
from hq_api.schemas import Page

__all__ = [
    "Badge", "Brief", "Holder", "Participant", "SessionCard", "SessionState", "SessionTask",
    "TaskCount",
]  # fmt: skip
PLAYERS = ("gpt", "gemini", "deepseek")
PLAYER_FA = {"gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
FIXED_FA = {"secretary": "منشی هلدینگ", "overseer": "ناظر کل", "assistant": "دستیار شخصی",
            "advisor": "مشاور کل"}  # fmt: skip
PROGRESS_HOURS = int(os.environ.get("ORDER_PROGRESS_HOURS", "2"))
CLOSE_REASON = "the owner closed the session"
OWNER_FA = "مدیر کل"
CARDS_MAX = 50
NOT_FOUND_FA = "این فرمان پیدا نشد."


# ------------------------------------------------------------------ shapes --
class View(BaseModel):
    """What a report and a card share, computed once per order."""

    session: SessionState
    brief: Brief
    tasks: list[SessionTask]
    participants: list[Participant]
    holder: Holder | None


# ------------------------------------------------------------------- badge --
def _title(text: str | None, limit: int = 80) -> str:
    one = " ".join((text or "").split())
    plain = HZ.humanize(one) or one
    return plain[:limit].rstrip() or "فرمان"


async def decisions_pending(tx: Tx, work_ids: list[Any]) -> bool:
    """A pending owner-visible decision of one of the order's works."""
    if not work_ids:
        return False
    return bool(
        await tx.scalar(
            """SELECT 1 FROM cartable.decisions WHERE status = 'pending' AND owner_visible
                 AND work_id = ANY(:ids) LIMIT 1""",
            ids=work_ids,
        )
    )


def badge_of(
    rep: dict[str, Any],
    state: str,
    works: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    *,
    decision_pending: bool,
    now: datetime | None = None,
    pulse: SA.Pulse | None = None,
) -> tuple[str, str]:
    """(badge, reason_fa) by code (contract §35.2). ⟨1.23⟩ §41.3 with the session's `pulse`:
    `moving` only while a run is queued or running now; idle for two thresholds → `stuck` with the
    cause; idle for less → still `moving`, saying since when nobody works."""
    now = now or datetime.now(UTC)
    if rep.get("closed_at") is not None or rep.get("ended_at") is not None:
        head = {"delivered": "تحویل شد و بسته شد", "cancelled": "لغو شد و بسته شد"}.get(
            state, "بسته شد"
        )
        return "closed", head
    turn = OR._j(rep.get("turn"))
    if turn:
        who = turn.get("who_fa") or "مسئول"
        return "your_turn", HZ.humanize(f"{who} میپرسد: {turn.get('question_fa') or ''}")[:300]
    fixable = [b for b in blockers if b.get("fix")]
    if fixable:
        b = fixable[0]
        return "your_turn", f"{b['title_fa']}؛ {b['fix']['label_fa']}"[:300]
    if decision_pending:
        return "your_turn", "یک کارت منتظر تصمیم توست"
    roots = [w for w in works if w["is_root"]]
    # ⟨2026-11-11⟩ an output delivered while the plan still has open tasks is not the end: the
    # session is not `ready` (the sweep opens the root again and wakes its holder)
    plan_open = pulse is not None and bool(pulse.open_tasks) and state == "delivered"
    if state in OR.ENDED and not plan_open:
        if state == "delivered":
            return "ready", "کار تحویل شد؛ منتظر تأیید و بستن توست"
        if state == "cancelled":
            return "ready", "کارها لغو شد؛ منتظر بستن توست"
        return "ready", "کار به نتیجه نرسید؛ منتظر تصمیم و بستن توست"
    if roots and all(w["status"] not in OR.OPEN for w in roots) and not plan_open:
        return "ready", "کارها تمام شد؛ منتظر تأیید و بستن توست"
    stuck = [b for b in blockers if not b.get("fix")]
    if rep.get("talk_stopped_at") is not None:
        return "stuck", "گیر کرد: کارمندها چند بار کار کردند و خروجی ندادند"
    if stuck:
        return "stuck", str(stuck[0]["title_fa"])[:300]
    steps = OR._j(rep.get("steps")) or []
    if pulse is not None:
        if pulse.live:
            doing = pulse.doing_fa or (
                f"{steps[-1].get('who_fa')}: {steps[-1].get('what_fa')}" if steps else None
            )
            return "moving", f"در حال کار: {doing}"[:300] if doing else "در حال کار"
        if pulse.stuck_fa:
            return "stuck", pulse.stuck_fa[:300]
    last = _last_at(rep)
    if roots and now - last >= timedelta(hours=PROGRESS_HOURS):
        return "stuck", f"از {PROGRESS_HOURS} ساعت پیش قدمی برداشته نشده"
    if pulse is not None and roots:
        minutes = int(pulse.idle.total_seconds() // 60)
        if minutes >= 1:
            return "moving", f"از {minutes} دقیقه پیش کسی کار نمیکند؛ مسئول بیدار میشود"[:300]
    if steps:
        s = steps[-1]
        return "moving", f"{s.get('who_fa')}: {s.get('what_fa')}"[:300]
    return "moving", "در جریان است"


def _last_at(rep: dict[str, Any]) -> datetime:
    cands = [rep.get("last_step_at"), rep.get("acked_at"), rep.get("created_at")]
    found = [c for c in cands if isinstance(c, datetime)]
    return max(found) if found else datetime.now(UTC)


BRIEF_CHARS = 90  # ⟨2026-11-07⟩ W9 D: each line of the brief, one short plain line


def short(text: str, limit: int = BRIEF_CHARS) -> str:
    """One line of at most `limit` characters, cut at a word when it must be."""
    one = " ".join((text or "").split())
    if len(one) <= limit:
        return one
    cut = one[: limit - 1]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip("،؛:,; ") + "…"


def brief_of(
    badge: str,
    reason_fa: str,
    rep: dict[str, Any],
    outputs: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, str]:
    """«چه شد · حالا چه · از تو چه», always filled, each one short plain line (≤ BRIEF_CHARS)."""
    finals = [o for o in outputs if o.get("kind") != "partial"]
    steps = OR._j(rep.get("steps")) or []
    if finals:
        names = "، ".join(str(o["title_fa"]) for o in finals[-3:])
        done = f"{len(finals)} خروجی تحویل شد: {names}"
    elif len(steps) > 1:
        done = f"آخرین قدم: {steps[-1].get('what_fa')}"
    else:
        done = "دریافت شد؛ هنوز قدمی برداشته نشده"
    doing = [t for t in tasks if t["state"] == "doing"]
    todo = [t for t in tasks if t["state"] == "todo"]
    if badge in ("closed", "your_turn", "ready", "stuck"):
        now = reason_fa
    elif doing:
        now = f"در حال انجام: {doing[0]['title_fa']}"
    elif todo:
        now = f"قدم بعدی: {todo[0]['title_fa']}"
    else:
        now = reason_fa
    if badge == "your_turn":
        turn = OR._j(rep.get("turn"))
        need = "جواب تو" if turn else reason_fa.split("؛")[-1].strip() or "تصمیم تو"
    elif badge == "ready":
        need = "تأیید و بستن"
    elif badge == "stuck":
        need = "یک نگاه: چرا جلو نمیرود"
    else:
        need = "چیزی لازم نیست"
    return {
        "done_fa": short(HZ.humanize(done)),
        "now_fa": short(HZ.humanize(now)),
        "need_fa": short(HZ.humanize(need)),
    }


# ------------------------------------------------------------------- tasks --
def render_task(r: dict[str, Any]) -> SessionTask:
    return SessionTask(
        id=r["id"],
        n=r["n"],
        title_fa=r["title_fa"],
        state=r["state"],
        by=r["by"],
        who_fa=r.get("who_fa"),
        work_ref=r.get("work_ref"),
    )


async def tasks_of(tx: Tx, order_id: UUID) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await tx.all(
            "SELECT * FROM owner.session_tasks WHERE order_id = :o ORDER BY n, created_at",
            o=order_id,
        )
    ]


async def add_task(
    tx: Tx,
    rep: dict[str, Any],
    *,
    title_fa: str,
    by: str,
    who_fa: str | None = None,
    who_code: str | None = None,
    work_ref: str | None = None,
    state: str = "todo",
) -> dict[str, Any]:
    title = HZ.humanize(" ".join(title_fa.split())) or " ".join(title_fa.split())
    if not title:
        raise ApiError(422, "validation_failed", fields={"title_fa": "empty"},
                       message_fa="عنوان کار خالی است.")  # fmt: skip
    n = int(
        await tx.scalar(
            "SELECT COALESCE(max(n), 0) + 1 FROM owner.session_tasks WHERE order_id = :o",
            o=rep["order_id"],
        )
    )
    row = await tx.one(
        """INSERT INTO owner.session_tasks (company_id, order_id, ref, n, title_fa, state, by, who_fa,
               who_code, work_ref)
           VALUES (:co, :o, :r, :n, :t, :st, :by, :who, :code, :w) RETURNING *""",
        co=rep["company_id"],
        o=rep["order_id"],
        r=rep["ref"],
        n=n,
        t=title[:300],
        st=state,
        by=by,
        who=(who_fa or None) and HZ.humanize(who_fa)[:200],
        code=who_code,
        w=work_ref,
    )
    return dict(row)


async def patch_task(
    tx: Tx,
    rep: dict[str, Any],
    task_id: UUID,
    *,
    title_fa: str | None,
    state: str | None,
    n: int | None,
) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM owner.session_tasks WHERE id = :id AND order_id = :o FOR UPDATE",
        id=task_id,
        o=rep["order_id"],
    )
    if row is None:
        raise ApiError(404, "not_found", "unknown task", message_fa="این کار در فهرست نیست.")
    if n is not None and n != row["n"]:
        total = int(
            await tx.scalar(
                "SELECT count(*) FROM owner.session_tasks WHERE order_id = :o", o=rep["order_id"]
            )
        )
        n = max(1, min(n, total))
        if n < row["n"]:
            await tx.exec(
                """UPDATE owner.session_tasks SET n = n + 1, updated_at = now()
                   WHERE order_id = :o AND n >= :a AND n < :b""",
                o=rep["order_id"],
                a=n,
                b=row["n"],
            )
        else:
            await tx.exec(
                """UPDATE owner.session_tasks SET n = n - 1, updated_at = now()
                   WHERE order_id = :o AND n > :a AND n <= :b""",
                o=rep["order_id"],
                a=row["n"],
                b=n,
            )
    title = None
    if title_fa is not None:
        title = (HZ.humanize(" ".join(title_fa.split())) or " ".join(title_fa.split()))[:300]
        if not title:
            raise ApiError(422, "validation_failed", fields={"title_fa": "empty"},
                           message_fa="عنوان کار خالی است.")  # fmt: skip
    out = await tx.one(
        """UPDATE owner.session_tasks
           SET title_fa = COALESCE(:t, title_fa), state = COALESCE(:st, state), n = COALESCE(:n, n),
               updated_at = now()
           WHERE id = :id RETURNING *""",
        t=title,
        st=state,
        n=n,
        id=task_id,
    )
    return dict(out)


async def agent_tasks(
    tx: Tx, rep: dict[str, Any], who_code: str, who_fa: str, steps: list[str]
) -> int:
    """`order.ack` with `steps`: the holder's plan as the session's tasks (a title already in the
    list is not added twice)."""
    have = {t["title_fa"] for t in await tasks_of(tx, rep["order_id"])}
    added = 0
    for s in steps[:20]:
        title = HZ.humanize(" ".join(str(s).split())) or " ".join(str(s).split())
        if not title or title[:300] in have:
            continue
        await add_task(tx, rep, title_fa=title, by="agent", who_fa=who_fa, who_code=who_code)
        have.add(title[:300])
        added += 1
    return added


async def tick_tasks(
    tx: Tx, rep: dict[str, Any], done: list[int], *, who_fa: str | None = None,
    company: str | None = None,
) -> int:  # fmt: skip
    """`order.progress` with `done`: those task numbers are done (⟨1.24⟩ §42.2 each one a `task`
    line on the session's stream)."""
    if not done:
        return 0
    rows = await tx.all(
        """UPDATE owner.session_tasks SET state = 'done', updated_at = now()
           WHERE order_id = :o AND n = ANY(:ns) AND state <> 'done' RETURNING n, title_fa""",
        o=rep["order_id"],
        ns=[int(x) for x in done[:50]],
    )
    for t in rows:
        await SA.emit_safe(tx, str(rep["ref"]), SA.make_line(
            f"task:{rep['ref']}:{t['n']}", who_fa or "مسئول", f"کار {t['n']} انجام شد: {t['title_fa']}",
            kind="task", state="done", company=company, task_n=int(t["n"]),
        ))  # fmt: skip
    return len(rows)


# ------------------------------------------------------------ participants --
def is_player(key: str) -> bool:
    return key.startswith("player:")


async def title_of(tx: Tx, key: str) -> tuple[str, str | None]:
    """(title_fa, company) of a persona key, from the records (no model, no hub)."""
    if is_player(key):
        return PLAYER_FA.get(key.split(":", 1)[1], key), None
    if key in FIXED_FA:
        return FIXED_FA[key], None
    role, _, code = key.partition("@")
    emp = await tx.first(
        """SELECT e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE c.code = :co AND e.role = :r AND e.status <> 'dismissed'
           ORDER BY (e.status = 'active') DESC, e.hired_at LIMIT 1""",
        co=code,
        r=role,
    )
    if emp is None:
        return key, code or None
    return OR.who_fa(emp["title_fa"], emp["company_fa"]), code or None


async def participants_of(
    tx: Tx, rep: dict[str, Any], holder: dict[str, Any] | None
) -> list[Participant]:
    from hq_api.domain import order_turns as OT

    out: list[Participant] = []
    hkey = OT.persona_key(holder) if holder else None
    if holder is not None and hkey is not None:
        out.append(
            Participant(
                key=hkey,
                kind="holder",
                title_fa=OR.who_fa(holder["title_fa"], holder["company_fa"]),
                company=None if holder["company_kind"] == "holding" else holder["company"],
            )
        )
    conv = None
    if rep.get("conversation_ref"):
        conv = await tx.first(
            "SELECT present, holder FROM talk.conversations WHERE ref = :r",
            r=rep["conversation_ref"],
        )
    for key in (conv or {}).get("present") or []:
        if key == hkey or key == (conv or {}).get("holder") or any(p.key == key for p in out):
            continue
        title, company = await title_of(tx, str(key))
        out.append(
            Participant(
                key=str(key),
                kind="player" if is_player(str(key)) else "person",
                title_fa=title,
                company=company,
            )
        )
    return out


def _holder_card(h: dict[str, Any] | None) -> Holder | None:
    if h is None:
        return None
    return Holder(
        code=str(h["code"]),
        title_fa=OR.who_fa(h["title_fa"], h["company_fa"]),
        company=str(h["company"]),
        company_fa=str(h["company_fa"] or h["company"]),
    )


# --------------------------------------------------------------------- view --
async def view(
    tx: Tx,
    rep: dict[str, Any],
    order: dict[str, Any],
    *,
    works: list[dict[str, Any]] | None = None,
) -> View:
    """The session's state, brief, tasks and participants of one order (its report refreshed
    already)."""
    from hq_api.domain import order_turns as OT

    works = await OR.tree(tx, OR.root_refs(order)) if works is None else works
    blockers = OR._j(rep.get("blockers")) or []
    pending = await decisions_pending(tx, [w["id"] for w in works])
    pulse = await SA.read_pulse(tx, rep, works)
    badge, reason = badge_of(
        rep, rep["state"], works, blockers, decision_pending=pending, pulse=pulse
    )
    tasks = await tasks_of(tx, rep["order_id"])
    holder = await OT.holder(tx, rep["ref"])
    brief = brief_of(badge, reason, rep, OR._j(rep.get("outputs")) or [], tasks)
    return View(
        session=SessionState(
            state="closed" if rep.get("closed_at") is not None else "open",
            badge=badge,
            reason_fa=reason,
            closed_at=rep.get("closed_at"),
            hidden=rep.get("hidden_at") is not None,
            source=rep.get("source_playbook"),
        ),
        brief=Brief.model_validate(brief),
        tasks=[render_task(t) for t in tasks],
        participants=await participants_of(tx, rep, holder),
        holder=_holder_card(holder),
    )


async def card(tx: Tx, rep: dict[str, Any], order: dict[str, Any]) -> SessionCard:
    v = await view(tx, rep, order)
    return SessionCard(
        ref=rep["ref"],
        conversation_ref=rep.get("conversation_ref"),
        title_fa=_title(order.get("text")),
        holder=v.holder,
        badge=v.session.badge,
        reason_fa=v.session.reason_fa,
        brief=v.brief,
        pace=order.get("pace") or "auto",
        participants=v.participants,
        tasks=TaskCount(
            done=sum(1 for t in v.tasks if t.state == "done"),
            total=sum(1 for t in v.tasks if t.state != "dropped"),
        ),
        opened_at=order["created_at"],
        last_at=rep.get("last_step_at") or rep.get("updated_at") or order["created_at"],
        closed_at=rep.get("closed_at"),
        hidden=rep.get("hidden_at") is not None,
        source=rep.get("source_playbook"),
    )


async def cards(
    tx: Tx, *, state: str = "open", limit: int = 30, cursor: str | None = None
) -> Page[SessionCard]:
    """GET /sessions (and the office): open sessions by badge (your_turn, ready, stuck, moving),
    each newest `last_at` first; hidden ones only with `all`."""
    after = pagination.decode(cursor, 3)
    rows = await tx.all(
        """SELECT r.*, CASE r.badge WHEN 'your_turn' THEN 1 WHEN 'ready' THEN 2 WHEN 'stuck' THEN 3
                                   WHEN 'moving' THEN 4 ELSE 5 END AS rank,
                  COALESCE(r.last_step_at, r.updated_at, r.created_at) AS last_at
           FROM owner.order_reports r
           WHERE (:st = 'all' OR r.hidden_at IS NULL)
             AND (:st <> 'open' OR r.closed_at IS NULL)
             AND (:st <> 'closed' OR r.closed_at IS NOT NULL)
             AND (CAST(:rank AS int) IS NULL
                  OR (CASE r.badge WHEN 'your_turn' THEN 1 WHEN 'ready' THEN 2 WHEN 'stuck' THEN 3
                                   WHEN 'moving' THEN 4 ELSE 5 END,
                      -COALESCE(extract(epoch FROM COALESCE(r.last_step_at, r.updated_at, r.created_at)), 0),
                      r.id::text)
                     > (CAST(:rank AS int), -extract(epoch FROM CAST(:la AS timestamptz)), CAST(:id AS text)))
           ORDER BY rank, last_at DESC, r.id::text LIMIT :lim""",
        st=state,
        rank=int(after[0]) if after else None,
        la=after[1] if after else None,
        id=after[2] if after else None,
        lim=limit + 1,
    )
    items, nxt = pagination.page([dict(r) for r in rows], limit, ("rank", "last_at", "id"))
    out = []
    for r in items:
        order = await OR.load_order(tx, r["ref"])
        if order is None:
            continue
        out.append(await card(tx, r, order))
    return Page(items=out, next_cursor=nxt)


# ------------------------------------------------------------- the stream --
async def badge_changed(tx: Tx, rep: dict[str, Any], badge: str, order: dict[str, Any]) -> None:
    """The badge written and streamed (`session.updated`); the first `ready` tells the owner once."""
    await tx.exec(
        "UPDATE owner.order_reports SET badge = :b, updated_at = now() WHERE id = :id",
        b=badge,
        id=rep["id"],
    )
    holding = await OR._holding(tx)
    await events.emit(tx, holding["code"], "session.updated", rep["ref"], {"badge": badge})
    if badge == "ready" and rep.get("badge") not in ("ready", "closed"):  # not again on a reopen
        text = _title(order.get("text"))
        await notify.raise_notification(
            tx,
            company_id=holding["id"],
            company_code=holding["code"],
            level="report",
            title_fa=f"فرمان تو آماده‌ی تأیید است: {text}"[:300],
            body_fa=HZ.plain("کارهای این فرمان تمام شد", None, "تأیید و بستن جلسه"),
            link_kind="order",
            link_ref=rep["ref"],
            source_kind="service",
            source_code="orders",
            domain="business",
        )


# ---------------------------------------------------------- participants --
async def _open(tx: Tx, ref: str) -> dict[str, Any]:
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa=NOT_FOUND_FA)
    if rep.get("closed_at") is not None or rep.get("ended_at") is not None:
        raise ApiError(409, "validation_failed", "the session is closed",
                       message_fa="این جلسه بسته شده است؛ برای ادامه آن را دوباره باز کن.")  # fmt: skip
    return rep


async def _conversation(ctx: Any, tx: Tx, ref: str, rep: dict[str, Any]) -> dict[str, Any]:
    from hq_api.domain import order_turns as OT
    from hq_api.talk import store

    conv_ref = rep.get("conversation_ref") or await OT.open_talk(ctx, tx, ref)
    if conv_ref is None:
        raise ApiError(409, "validation_failed", "the order has no holder yet",
                       message_fa="هنوز کسی این فرمان را نگرفته است.")  # fmt: skip
    return await store.conversation(tx, str(conv_ref), lock=True)


async def _notice(tx: Tx, conv: dict[str, Any], key: str, line: str) -> None:
    from hq_api.domain import order_turns as OT

    await OT.post_turn(tx, conv, key, line, line)


async def add_participant(ctx: Any, tx: Tx, ref: str, kind: str, key: str) -> str:
    """POST /orders/{ref}/participants: a person (any persona key) or a player joins the
    session's talk; answers the persona key added."""
    from hq_api.domain import players as PL
    from hq_api.talk import personas

    rep = await _open(tx, ref)
    if kind == "player":
        if key not in PLAYERS:
            raise ApiError(422, "validation_failed", fields={"key": "gpt | gemini | deepseek"},
                           message_fa="بازیکن را از میان ChatGPT، Gemini و DeepSeek انتخاب کن.")  # fmt: skip
        why = await PL.availability(tx, key)
        if why is not None:
            off = f"{PLAYER_FA[key]} الان در دسترس نیست؛ اول در صفحه‌ی بازیکن‌ها واردش کن."
            raise ApiError(409, "validation_failed", f"the player is {why}", message_fa=off)
        pkey, title = f"player:{key}", PLAYER_FA[key]
    else:
        p = await personas.resolve(tx, ctx.hub, key)
        pkey, title = p.key, p.title_fa
    conv = await _conversation(ctx, tx, ref, rep)
    if pkey == conv.get("holder"):
        raise ApiError(409, "validation_failed", "the holder is already here",
                       message_fa="مسئول فرمان خودش در جلسه است.")  # fmt: skip
    present = list(dict.fromkeys([*(conv.get("present") or []), pkey]))[-20:]
    await tx.exec(
        "UPDATE talk.conversations SET present = :p, updated_at = now() WHERE id = :id",
        p=present,
        id=conv["id"],
    )
    conv["present"] = present
    await _notice(tx, conv, pkey, f"{title} آمد.")
    await OR._append_steps(tx, rep["id"], [OR._step(OWNER_FA, f"{title} به جلسه آمد")])
    await remember(tx, rep["id"], f"{title} به جلسه آمد")  # ⟨1.22⟩ §40.1
    return pkey


async def join_hired(
    tx: Tx,
    employee_code: str,
    role: str | None,
    company_code: str,
    title_fa: str,
    *,
    decision_ref: str | None = None,
    conversation_id: Any = None,
) -> list[str]:
    """⟨2026-11-07⟩ §39: whoever is hired from inside a session joins that same session (its
    talk) with one line, never a new order: a hire filled at once (`conversation_id`, the card's
    talk) or a hire card decided later (`decision_ref`, found in the session's `hire` cards).
    Answers the conversations joined."""
    from hq_api.talk import store

    if not role:
        return []
    if conversation_id is not None:
        rows = await tx.all(
            """SELECT ref, order_ref FROM talk.conversations
               WHERE id = :c AND order_ref IS NOT NULL AND closed_at IS NULL""",
            c=conversation_id,
        )
    elif decision_ref:
        rows = await tx.all(
            """SELECT DISTINCT c.ref, c.order_ref FROM talk.cards k
               JOIN talk.conversations c ON c.id = k.conversation_id
               WHERE k.kind = 'hire' AND :d = ANY(k.made)
                 AND c.order_ref IS NOT NULL AND c.closed_at IS NULL""",
            d=decision_ref,
        )
    else:
        return []
    key = f"{role}@{company_code}"
    line = f"{title_fa} استخدام شد و به همین جلسه آمد."
    joined: list[str] = []
    for r in rows:
        conv = await store.conversation(tx, str(r["ref"]), lock=True)
        if key != conv.get("holder"):
            present = list(dict.fromkeys([*(conv.get("present") or []), key]))[-20:]
            await tx.exec(
                "UPDATE talk.conversations SET present = :p, updated_at = now() WHERE id = :id",
                p=present,
                id=conv["id"],
            )
            conv["present"] = present
        await _notice(tx, conv, str(conv.get("holder") or conv["persona"]), line)
        rep = await OR.ensure(tx, str(r["order_ref"]))
        if rep is not None:
            await OR._append_steps(tx, rep["id"], [OR._step(OWNER_FA, line)])
            await remember(tx, rep["id"], line)  # ⟨1.22⟩ §40.1
            await SA.emit_safe(tx, str(r["order_ref"]), SA.make_line(
                f"join:{employee_code}", title_fa, line, kind="join", state="done",
                company=company_code,
            ))  # fmt: skip  # ⟨1.24⟩ §42.2
            # ⟨1.23⟩ §41.3 the holder is woken: the newcomer is here, the work goes on (or a
            # step says why not — audit M11)
            from hq_api.domain import order_turns as OT

            await OT.wake_or_say(tx, str(r["order_ref"]), f"joined:{employee_code}")
        joined.append(str(r["ref"]))
    return joined


async def join_from_order(
    tx: Tx, order_ref: str, company_id: Any, company_code: str, role: str | None
) -> list[str]:
    """⟨2026-11-10⟩ A hire the owner asked for in his session was made by code: the newest active
    employee of that role in the company joins that session (one line, the holder woken), as a
    hire from a talk card does. Needs a transaction that reaches every company."""
    if not role:
        return []
    emp = await tx.first(
        """SELECT code, title_fa FROM core.employees
           WHERE company_id = :co AND role = :r AND status = 'active'
           ORDER BY hired_at DESC LIMIT 1""",
        co=company_id,
        r=role,
    )
    conv = await tx.scalar(
        """SELECT c.id FROM talk.conversations c JOIN owner.order_reports r
             ON r.conversation_ref = c.ref WHERE r.ref = :ref AND c.closed_at IS NULL""",
        ref=order_ref,
    )
    if emp is None or conv is None:
        return []
    return await join_hired(
        tx, str(emp["code"]), role, company_code, str(emp["title_fa"]), conversation_id=conv
    )


async def remove_participant(ctx: Any, tx: Tx, ref: str, key: str) -> None:
    """DELETE /orders/{ref}/participants/{key}: never the holder."""
    rep = await _open(tx, ref)
    if not rep.get("conversation_ref"):
        raise ApiError(404, "not_found", "no such participant", message_fa="این کس در جلسه نیست.")
    conv = await _conversation(ctx, tx, ref, rep)
    if key == conv.get("holder"):
        raise ApiError(409, "validation_failed", "the holder stays",
                       message_fa="مسئول فرمان از جلسه بیرون نمیرود.")  # fmt: skip
    present = list(conv.get("present") or [])
    if key not in present:
        raise ApiError(404, "not_found", "no such participant", message_fa="این کس در جلسه نیست.")
    present.remove(key)
    await tx.exec(
        "UPDATE talk.conversations SET present = :p, updated_at = now() WHERE id = :id",
        p=present,
        id=conv["id"],
    )
    conv["present"] = present
    title, _ = await title_of(tx, key)
    await _notice(tx, conv, str(conv.get("holder") or conv["persona"]), f"{title} رفت.")
    await OR._append_steps(tx, rep["id"], [OR._step(OWNER_FA, f"{title} از جلسه رفت")])


# ------------------------------------------------------- close · reopen · hide --
async def close(
    tx: Tx, ref: str, verdict: str, note: str | None, *, hub: Any = None
) -> dict[str, Any]:
    """POST /orders/{ref}/close: the owner's OK (or cancel). The order `delivered` (or `cancelled`
    without a final output), its open works cancelled (the permanent structures it set up stay:
    groups, lines, automations, rules are not works), the session closed and its talk read-only."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa=NOT_FOUND_FA)
    if rep.get("closed_at") is not None:
        raise ApiError(409, "validation_failed", "the session is closed already",
                       message_fa="این جلسه پیش از این بسته شده است.")  # fmt: skip
    order = await OR.load_order(tx, ref)
    assert order is not None
    works = await OR.tree(tx, OR.root_refs(order))
    outputs = OR._j(rep.get("outputs")) or []
    finals = [o for o in outputs if o.get("kind") != "partial"]
    state = "cancelled"
    if verdict == "ok" and (finals or rep["state"] == "delivered"):
        state = "delivered"
    open_ids = [w["id"] for w in works if w["status"] in OR.OPEN]
    if open_ids:
        # (a run still queued on one of them ends as `work_closed` when the worker claims it)
        await tx.exec(
            """UPDATE work.work SET status = 'cancelled', close_reason = :why, closed_at = now()
               WHERE id = ANY(:ids)""",
            ids=open_ids,
            why=CLOSE_REASON,
        )
    await tx.exec(
        """UPDATE owner.session_tasks SET state = 'dropped', updated_at = now()
           WHERE order_id = :o AND state IN ('todo', 'doing')""",
        o=rep["order_id"],
    )
    summary = OR.summary_of(state, await OR.tree(tx, OR.root_refs(order)), outputs, [])
    if state == "cancelled" and verdict == "ok":
        summary["done_fa"] = HZ.humanize("فرمان بی خروجی نهایی بسته شد")
    await tx.exec(
        """UPDATE owner.order_reports
           SET state = :st, ended_at = now(), closed_at = now(), badge = 'closed', turn = NULL,
               blockers = '[]'::jsonb, summary = CAST(:sm AS jsonb), last_step_at = now(),
               updated_at = now()
           WHERE id = :id""",
        st=state,
        sm=json.dumps(summary, ensure_ascii=False),
        id=rep["id"],
    )
    line = "تأیید و بستن" if verdict == "ok" else "لغو و بستن"
    if note:
        line += f": {' '.join(note.split())[:500]}"
    await OR._append_steps(tx, rep["id"], [OR._step(OWNER_FA, line)])
    if rep.get("conversation_ref"):
        from hq_api.domain import order_turns as OT

        await OT.to_talk_owner(tx, rep, line)
        await tx.exec(
            "UPDATE talk.conversations SET closed_at = now(), updated_at = now() WHERE ref = :r",
            r=rep["conversation_ref"],
        )
    holding = await OR._holding(tx)
    await events.emit(tx, holding["code"], "session.updated", ref, {"badge": "closed"})
    fresh = await tx.one("SELECT * FROM owner.order_reports WHERE id = :id", id=rep["id"])
    await OR._tell_end(tx, dict(fresh), order, state, summary)
    await events.emit(tx, holding["code"], "order.report", ref, {"state": state})
    return dict(fresh)


async def reopen(tx: Tx, ref: str) -> dict[str, Any]:
    """POST /orders/{ref}/reopen: `ended_at` cleared, the session open, the holder woken."""
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa=NOT_FOUND_FA)
    if rep.get("closed_at") is None and rep.get("ended_at") is None:
        raise ApiError(409, "validation_failed", "the session is open",
                       message_fa="این جلسه باز است.")  # fmt: skip
    order = await OR.load_order(tx, ref)
    assert order is not None
    works = await OR.tree(tx, OR.root_refs(order))
    await tx.exec(
        """UPDATE owner.order_reports
           SET ended_at = NULL, closed_at = NULL, hidden_at = NULL, last_step_at = now(),
               progress_nudged_at = NULL, owner_told_at = NULL, updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
    )
    if rep.get("conversation_ref"):
        await tx.exec(
            "UPDATE talk.conversations SET closed_at = NULL, updated_at = now() WHERE ref = :r",
            r=rep["conversation_ref"],
        )
    if rep.get("closed_at") is not None:
        # ⟨2026-11-10⟩ the plan comes back with the session: the tasks the close dropped are open
        # again (the ones the owner removed himself, earlier, stay removed)
        await tx.exec(
            """UPDATE owner.session_tasks SET state = 'todo', updated_at = now()
               WHERE order_id = :o AND state = 'dropped' AND updated_at >= :at""",
            o=rep["order_id"],
            at=rep["closed_at"],
        )
    woken: list[str] = []
    for w in works:
        if w["is_root"] and w["status"] == "cancelled":
            reason = await tx.scalar(
                "SELECT close_reason FROM work.work WHERE id = :id", id=w["id"]
            )
            if reason != CLOSE_REASON:
                continue
            # ⟨1.19⟩ a closed work's status is guarded (work.before_update): work.reopen alone
            # brings it back (migration 0055)
            await tx.scalar("SELECT work.reopen(:id)", id=w["id"])
            rid = await tx.scalar(
                "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"session_reopened:{ref}"
            )
            if rid is not None:
                woken.append(str(w["ref"]))
    steps = [OR._step(OWNER_FA, "جلسه دوباره باز شد")]
    reopened = [w for w in works if w["is_root"] and w["status"] == "cancelled"]
    if reopened and not woken:  # ⟨2026-11-08⟩ audit M11: never a silent NULL
        from hq_api.domain import order_turns as OT

        why = await OT._why_not_woken(tx, {**reopened[0], "status": "in_progress"})
        steps.append(OR._step(SA.SYSTEM_FA, SA.NOT_WOKEN_FA.format(why=why)))
    await OR._append_steps(tx, rep["id"], steps)
    await OR.refresh(tx, ref)
    return {"woken": woken}


async def hide(tx: Tx, ref: str, hidden: bool) -> None:
    rep = await OR.ensure(tx, ref)
    if rep is None:
        raise ApiError(404, "not_found", "unknown order", message_fa=NOT_FOUND_FA)
    await tx.exec(
        """UPDATE owner.order_reports SET hidden_at = CASE WHEN :h THEN now() ELSE NULL END,
               updated_at = now() WHERE id = :id""",
        h=hidden,
        id=rep["id"],
    )
    holding = await OR._holding(tx)
    await events.emit(
        tx, holding["code"], "session.updated", ref, {"badge": rep["badge"], "hidden": hidden}
    )


# ------------------------------------------------------------------- pace --
PACE_FA = {
    "step": "از این به بعد مرحله‌به‌مرحله با تو",
    "auto": "از این به بعد تا آخر خودش جلو میرود",
}


async def set_pace(tx: Tx, ref: str, pace: str) -> dict[str, Any]:
    """POST /orders/{ref}/pace: the owner switches «با من / خودکار» at any time. The order's pace,
    a step, the holder's brief rewritten (O.pace_brief) and the holder woken so its next run reads
    the new pace (its brief and the dialogue). Answers {pace, changed, woken}."""
    from hq_api.domain import orders as O

    rep = await _open(tx, ref)
    order = await OR.load_order(tx, ref)
    assert order is not None
    before = str(order.get("pace") or "auto")
    if before == pace:
        return {"pace": pace, "changed": False, "woken": []}
    await tx.exec("UPDATE owner.orders SET pace = :p WHERE id = :id", p=pace, id=order["id"])
    works = await OR.tree(tx, OR.root_refs(order))
    woken: list[str] = []
    for w in works:
        if not w["is_root"]:
            continue
        await tx.exec(
            "UPDATE work.work SET brief = replace(brief, :old, :new) WHERE id = :id",
            old=O.pace_brief(ref, before),
            new=O.pace_brief(ref, pace),
            id=w["id"],
        )
        if w["status"] in OR.OPEN:
            rid = await tx.scalar(
                "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"pace:{pace}:{ref}"
            )
            if rid is not None:
                woken.append(str(w["ref"]))
    if pace == "auto":  # ⟨2026-11-09⟩ nothing waits for the owner any more
        await OR.resume_held(tx, ref)
    steps = [OR._step(OWNER_FA, PACE_FA[pace])]
    if not woken and any(w["is_root"] and w["status"] in OR.OPEN for w in works):
        # ⟨2026-11-08⟩ audit M11: never a silent NULL
        from hq_api.domain import order_turns as OT

        root = next(w for w in works if w["is_root"] and w["status"] in OR.OPEN)
        why = await OT._why_not_woken(tx, root)
        steps.append(OR._step(SA.SYSTEM_FA, SA.NOT_WOKEN_FA.format(why=why)))
    await OR._append_steps(tx, rep["id"], steps)
    await tx.exec(
        "UPDATE owner.order_reports SET last_step_at = now(), updated_at = now() WHERE id = :id",
        id=rep["id"],
    )
    if rep.get("conversation_ref"):
        from hq_api.domain import order_turns as OT

        await OT.to_talk_owner(tx, rep, PACE_FA[pace])
    await OR.refresh(tx, ref)
    return {"pace": pace, "changed": True, "woken": woken}


# ------------------------------------------------------------------ steps --
async def step(
    tx: Tx, ref: str, who_fa: str, what_fa: str, *, remember_line: str | None = None
) -> None:
    """One line of the order's story («what a card made»), then the report refreshed (it streams).
    ⟨1.22⟩ §40.1 `remember_line`: the same (or a shorter) line into the session's memory."""
    rep = await OR.refresh(tx, ref)  # what the card made (a hand-over, an output) first
    if rep is None:
        return
    await OR._append_steps(tx, rep["id"], [OR._step(who_fa, what_fa)])
    await tx.exec(
        "UPDATE owner.order_reports SET last_step_at = now(), updated_at = now() WHERE id = :id",
        id=rep["id"],
    )
    if remember_line:
        await remember(tx, rep["id"], remember_line)
    await OR.refresh(tx, ref)


async def remember(tx: Tx, report_id: Any, line: str) -> None:
    """⟨1.22⟩ §40.1 one line into the session's memory, by code (domain.session_memory)."""
    from hq_api.domain import session_memory as MEM

    await MEM.remember(tx, report_id, line)
