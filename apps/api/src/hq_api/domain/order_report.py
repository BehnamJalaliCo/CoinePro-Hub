"""Every order is answered (contract §29.2, the owner's ask 2 of 2026-11-02).

One report per order of the owner (owner.order_reports, F-…), over every work
item the order made: its root works (owner.orders.routes[].work_ref), their
children and the requests made from them, in any company.

    received -> planned (the assignee's plan, `order.ack`) -> in_progress
             -> waiting | blocked -> delivered | failed | cancelled

What happens, by code (no model):
- the dispatcher's receipt «دریافت شد؛ به … سپرده شد» at once
  (`on_order_routed`, called after routing; a report made later writes it too);
- steps: the plan, each `order.progress`, each hand-over and each output;
- blockers, detected on every change and every few minutes, each with its
  one-tap fix (`no_employee` hire, `hiring_closed` hiring.open, `locked`
  lock.open, `series_unsealed` series.seal, `budget` budget.add, `player_down`
  player.auto, `connection_missing` connection.guide; `no_progress` and
  `talk_loop` have none);
- timers (the worker's tick): 10 minutes without a plan wakes the CEO with a
  small work item; 2 hours without a step the CEO must report; 6 hours the
  owner hears why (one decision-level notification, domain business);
- talk without output: more than ORDER_TALK_LIMIT agent runs on the order
  without a (complete) output stop the order's open runs;
- the end: «چه شد» · «چه ماند» · «از شما چه لازم است», and one report
  notification.
Every text the owner reads passes humanize (§29.7).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import kits as KT
from hq_api.domain import notify
from hq_api.domain import split as SP
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor

STATES = (
    "received", "planned", "in_progress", "waiting", "blocked", "delivered", "failed", "cancelled",
)  # fmt: skip
ENDED = ("delivered", "failed", "cancelled")
BLOCKERS = (
    "no_employee", "hiring_closed", "locked", "series_unsealed", "budget", "player_down",
    "connection_missing", "no_progress", "talk_loop", "kit_unsealed",
)  # fmt: skip
FIX_OF = {
    "no_employee": "hire",
    "hiring_closed": "hiring.open",
    "locked": "lock.open",
    "series_unsealed": "series.seal",
    "budget": "budget.add",
    "player_down": "player.auto",
    "connection_missing": "connection.guide",
    "kit_unsealed": "kit.create",
}
FIX_ACTIONS = tuple(FIX_OF.values())
FIX_LABEL_FA = {
    "hire": "استخدام کن",
    "hiring.open": "استخدام را باز کن",
    "lock.open": "قفل را باز کن",
    "series.seal": "سری انتشار را مُهر کن",
    "budget.add": "بودجه را بیشتر کن",
    "player.auto": "بازیکن خودکار شود",
    "connection.guide": "راهنمای اتصال",
    "kit.create": "شرکت را بساز",
}
MAX_STEPS = 30
OPEN = W.OPEN
CLOSED = W.CLOSED
SERVICE = Principal(kind="service", code="orders", role="service")
# A run that a budget stopped (the work's envelope, the company's or the hub's cap).
BUDGET_CODES = ("budget", "budget_used_up", "daily_cap", "token_cap", "budget_exhausted")
CONNECTION_CODES = ("channel_not_configured", "account_not_configured", "connection_missing")
# The seat a media order needs (MEDIA department, the content group's seats).
OUTPUT_ROLE = {"reel": "motion_designer", "post": "visual_designer", "story": "visual_designer"}
OUTPUT_WORDS = {
    "reel": ("کلیپ", "ریلز", "ویدیو", "موشن"),
    "story": ("استوری",),
    "post": ("پست", "کاروسل"),
}
NUDGE = "فرمان {ref}: "  # the title of the CEO's small work items of an order


# ------------------------------------------------------------------ models --
class Assigned(BaseModel):
    company: str
    code: str
    title_fa: str


class Ack(BaseModel):
    at: datetime
    by: Actor
    plan_fa: str
    assigned: list[Assigned] = Field(default_factory=list)
    due_at: datetime | None = None


class Route(BaseModel):
    companies: list[str] = Field(default_factory=list)
    department: str | None = None
    collaborators: list[str] = Field(default_factory=list)
    output_kind: str = "other"
    budget_tokens: int | None = None
    mode: str = "single"
    player: str = "auto"


class Step(BaseModel):
    at: datetime
    who_fa: str
    what_fa: str


class Fix(BaseModel):
    action: str
    label_fa: str
    target: str | None = None


class Blocker(BaseModel):
    kind: Literal[
        "no_employee", "hiring_closed", "locked", "series_unsealed", "budget", "player_down",
        "connection_missing", "no_progress", "talk_loop", "kit_unsealed",
    ]  # fmt: skip
    title_fa: str
    detail_fa: str
    since: datetime
    fix: Fix | None = None


class Output(BaseModel):
    ref: str
    title_fa: str
    kind: Literal["final", "part", "partial"]


class Summary(BaseModel):
    done_fa: str
    left_fa: str
    need_fa: str


class Turn(BaseModel):
    """⟨1.16⟩ §34.3 the holder's open question to the owner (`order.ask`)."""

    question_fa: str
    at: datetime
    by: Actor
    who_fa: str


class OrderReport(BaseModel):
    ref: str
    text_fa: str
    at: datetime
    state: Literal[
        "received", "planned", "in_progress", "waiting", "blocked", "delivered", "failed",
        "cancelled",
    ]  # fmt: skip
    ack: Ack | None = None
    route: Route
    steps: list[Step] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)
    outputs: list[Output] = Field(default_factory=list)
    summary: Summary | None = None
    updated_at: datetime
    # ⟨additive⟩ §31.2 the secretary's draft of «یک شرکت تازه …»: a kit card, no work item
    kit: KT.KitCard | None = None
    # ⟨additive⟩ §33.7 the order's works split into parallel parts, each split's parts side by side
    parts: list[SP.WorkSplit] = Field(default_factory=list)
    # ⟨additive⟩ §33.10 the order's works done on a company's own server: each workspace's progress
    workspaces: list[WS.WorkspaceProgress] = Field(default_factory=list)
    # ⟨1.16⟩ §34 step by step with its holder or to the end on its own; the holder's open question
    # (the owner's turn: the order is `waiting` on the owner); the live talk with the holder
    pace: Literal["auto", "step"] = "auto"
    turn: Turn | None = None
    conversation_ref: str | None = None


# ----------------------------------------------------------------- reading --
def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def root_refs(order: dict[str, Any]) -> list[str]:
    """The work refs the order's routes made (its root works)."""
    out: list[str] = []
    for r in _j(order.get("routes")) or []:
        ref = r.get("work_ref") if isinstance(r, dict) else None
        if ref and ref not in out:
            out.append(str(ref))
    return out


async def load_order(tx: Tx, ref: str) -> dict[str, Any] | None:
    """The order row (with whatever columns it has: the secretary's route is
    read when the table carries one)."""
    row = await tx.first("SELECT to_jsonb(o) AS raw FROM owner.orders o WHERE o.ref = :r", r=ref)
    if row is None:
        return None
    raw = _j(row["raw"])
    raw["id"] = UUID(str(raw["id"]))
    raw["created_at"] = datetime.fromisoformat(str(raw["created_at"]))
    return dict(raw)


TREE_SQL = """
WITH RECURSIVE t(id) AS (
    SELECT w.id FROM work.work w WHERE w.ref = ANY(CAST(:roots AS text[]))
    UNION
    SELECT c.id FROM work.work c JOIN t ON c.parent_id = t.id OR c.requested_by_work_id = t.id
)
SELECT w.id, w.ref, w.title, w.status, w.parent_id, w.root_id, w.requested_by_work_id, w.depth,
       w.company_id, c.code AS company, c.name_fa AS company_fa, d.code AS department,
       a.code AS a_code, a.title_fa AS a_title_fa, a.kind AS a_kind, a.role AS a_role,
       w.player, w.mode, w.progress_pct, w.budget_tokens, w.tokens_used, w.created_at,
       w.updated_at, w.created_by_kind, w.ref = ANY(CAST(:roots AS text[])) AS is_root
FROM work.work w JOIN core.companies c ON c.id = w.company_id
LEFT JOIN core.departments d ON d.id = w.department_id
LEFT JOIN core.employees a ON a.id = w.assignee_id
WHERE w.id IN (SELECT id FROM t)
ORDER BY w.created_at, w.ref
"""


async def tree(tx: Tx, roots: list[str]) -> list[dict[str, Any]]:
    if not roots:
        return []
    return await tx.all(TREE_SQL, roots=roots)


def who_fa(title_fa: str | None, company_fa: str | None) -> str:
    """An employee as the owner names it: its title and its company."""
    title = (title_fa or "").strip() or "کارمند"
    return f"{title} {company_fa}".strip() if company_fa else title


def receipt_text(works: list[dict[str, Any]]) -> str:
    names = [who_fa(w["a_title_fa"], w["company_fa"]) for w in works if w["is_root"]]
    if not names:
        return "دریافت شد؛ در صف رسیدگی است"
    return "دریافت شد؛ به " + " و ".join(dict.fromkeys(names)) + " سپرده شد"


def _step(who: str, what: str, at: datetime | None = None) -> dict[str, Any]:
    return {
        "at": (at or datetime.now(UTC)).isoformat(),
        "who_fa": HZ.humanize(who) or "سامانه",
        "what_fa": HZ.humanize(what) or "-",
    }


async def _holding(tx: Tx) -> dict[str, Any]:
    return await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")


async def ensure(tx: Tx, ref: str) -> dict[str, Any] | None:
    """The order's report (made now, with the receipt, when there is none
    yet: an order routed before this report existed, or a router that did
    not call `on_order_routed`)."""
    rep = await tx.first("SELECT * FROM owner.order_reports WHERE ref = :r FOR UPDATE", r=ref)
    if rep is not None:
        return rep
    order = await load_order(tx, ref)
    if order is None:
        return None
    roots = root_refs(order)
    works = await tree(tx, roots)
    kit = kit_of(order)
    first = _step(
        "منشی هلدینگ",
        (
            "دریافت شد؛ پیش‌نمایش شرکت تازه آماده است و منتظر مُهر شماست"
            if kit
            else receipt_text(works)
        ),
        order["created_at"],
    )
    await tx.exec(
        """INSERT INTO owner.order_reports (company_id, order_id, ref, steps, work_refs, route,
               created_at)
           VALUES (:co, :o, :r, CAST(:steps AS jsonb), :refs, CAST(:route AS jsonb), :at)
           ON CONFLICT (order_id) DO NOTHING""",
        co=order["company_id"],
        o=order["id"],
        r=ref,
        steps=json.dumps([first], ensure_ascii=False),
        refs=[w["ref"] for w in works],
        route=json.dumps(_route(order, works), ensure_ascii=False),
        at=order["created_at"],
    )
    made: dict[str, Any] = await tx.one(
        "SELECT * FROM owner.order_reports WHERE ref = :r FOR UPDATE", r=ref
    )
    return made


async def on_order_routed(tx: Tx, order_ref: str) -> dict[str, Any] | None:
    """The dispatcher's receipt, at once («دریافت شد؛ به … سپرده شد»): call it
    in the routing transaction, after owner.orders has the order."""
    rep = await ensure(tx, order_ref)
    if rep is None:
        return None
    holding = await _holding(tx)
    await events.emit(tx, holding["code"], "order.report", order_ref, {"state": rep["state"]})
    return rep


def kit_of(order: dict[str, Any]) -> dict[str, Any] | None:
    """⟨additive⟩ §31.2 the secretary's kit draft of an order ({kit, kit_name_fa}), or None."""
    given = _j(order.get("route"))
    if isinstance(given, dict) and given.get("kind") == "kit" and given.get("kit"):
        return {"kit": str(given["kit"]), "name_fa": given.get("kit_name_fa")}
    return None


async def kit_order_open(tx: Tx, ref: str, kit: str) -> bool:
    """Whether `ref` is an open order whose kit draft is this kit."""
    order = await load_order(tx, ref)
    rep = await tx.first("SELECT ended_at FROM owner.order_reports WHERE ref = :r", r=ref)
    draft = kit_of(order or {})
    return draft is not None and draft["kit"] == kit and (rep is None or rep["ended_at"] is None)


async def kit_sealed(tx: Tx, ref: str, code: str, name_fa: str) -> None:
    """The owner sealed the kit card: the order is delivered (its company exists)."""
    rep = await ensure(tx, ref)
    if rep is None or rep["ended_at"] is not None:
        return
    done = HZ.humanize(f"شرکت {name_fa} ({code}) از روی پیش‌نمایش ساخته شد")
    await _append_steps(tx, rep["id"], [_step("سامانه", done)])
    await tx.exec(
        """UPDATE owner.order_reports
           SET state = 'delivered', blockers = '[]'::jsonb, ended_at = now(), last_step_at = now(),
               summary = CAST(:sm AS jsonb), updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
        sm=json.dumps(
            {
                "done_fa": done,
                "left_fa": "اتصال حساب‌ها و روشن کردن خط‌ها مانده است",
                "need_fa": "اتصال‌ها را در صفحه‌ی شرکت وصل کنید",
            },
            ensure_ascii=False,
        ),
    )
    holding = await _holding(tx)
    await events.emit(tx, holding["code"], "order.report", ref, {"state": "delivered"})


def output_kind_of(text: str, route: dict[str, Any] | None = None) -> str:
    kind = (route or {}).get("output_kind")
    if isinstance(kind, str) and kind:
        return kind
    for k, words in OUTPUT_WORDS.items():
        if any(w in (text or "") for w in words):
            return k
    return "other"


def _route(order: dict[str, Any], works: list[dict[str, Any]]) -> dict[str, Any]:
    """The secretary's route when the order has one, else what the routes and
    the root works say."""
    given = _j(order.get("route"))
    roots = [w for w in works if w["is_root"]]
    first = roots[0] if roots else None
    companies = list(dict.fromkeys([w["company"] for w in roots])) or list(
        dict.fromkeys(str(r.get("company")) for r in _j(order.get("routes")) or [] if r)
    )
    out = {
        "companies": companies[:1] if companies else [],
        "department": first["department"] if first else None,
        "collaborators": companies[1:],
        "output_kind": output_kind_of(order.get("text") or ""),
        "budget_tokens": int(first["budget_tokens"]) if first and first["budget_tokens"] else None,
        "mode": (first or {}).get("mode") or "single",
        "player": (first or {}).get("player") or "auto",
    }
    if isinstance(given, dict):
        for k in out:
            if given.get(k) is not None:
                out[k] = given[k]
    return out


# --------------------------------------------------------------- the agents --
async def _assigned_works(tx: Tx, rep: dict[str, Any], who: Principal) -> list[dict[str, Any]]:
    """The order's works this agent may speak for: its own, or (a CEO) any
    of its company's."""
    order = await load_order(tx, rep["ref"])
    works = await tree(tx, root_refs(order or {}))
    mine = [w for w in works if w["a_code"] == who.code]
    if not mine and who.role == "ceo":
        mine = [w for w in works if w["company_id"] == who.company_id]
    return mine


async def may_speak(tx: Tx, ref: str, who: Principal) -> bool:
    rep = await ensure(tx, ref)
    return rep is not None and bool(await _assigned_works(tx, rep, who))


async def _close_nudges(tx: Tx, ref: str, why: str) -> None:
    """The CEO's small work items of this order are done with (cancelled)."""
    await tx.exec(
        """UPDATE work.work SET status = 'cancelled', close_reason = :why, closed_at = now()
           WHERE starts_with(title, :t) AND created_by_kind = 'service'
             AND created_by_code = 'orders' AND status IN ('queued', 'in_progress', 'waiting')""",
        t=NUDGE.format(ref=ref),
        why=why[:500],
    )


async def acknowledge(
    tx: Tx,
    who: Principal,
    ref: str,
    *,
    plan_fa: str,
    assigned: list[dict[str, Any]],
    due_at: datetime | None,
) -> dict[str, Any]:
    """`order.ack`: the assignee's plan («فهمیدم؛ برنامه: …؛ به … سپردم؛ تحویل تا …»)."""
    rep = await ensure(tx, ref)
    assert rep is not None
    emp = await tx.one(
        """SELECT e.code, e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=who.code,
    )
    names = await tx.all(
        """SELECT e.code, e.title_fa, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = ANY(:codes)""",
        codes=[str(a.get("code")) for a in assigned if a.get("code")],
    )
    by = {r["code"]: r for r in names}
    ack: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "by": {"kind": "agent", "code": who.code},
        "plan_fa": plan_fa[:2000],
        "assigned": [
            {"company": by[c]["company"], "code": c, "title_fa": by[c]["title_fa"]} for c in by
        ],
        "due_at": due_at.isoformat() if due_at else None,
    }
    who_name = who_fa(emp["title_fa"], emp["company_fa"])
    line = "فهمیدم؛ برنامه: " + plan_fa[:600]
    if ack["assigned"]:
        line += "؛ سپرده شد به " + " و ".join(a["title_fa"] for a in ack["assigned"])
    await tx.exec(
        """UPDATE owner.order_reports SET ack = CAST(:ack AS jsonb), acked_at = now(),
               last_step_at = now(), updated_at = now()
           WHERE id = :id""",
        ack=json.dumps(ack, ensure_ascii=False),
        id=rep["id"],
    )
    await _append_steps(tx, rep["id"], [_step(who_name, line)])
    await _close_nudges(tx, ref, "برنامه با order.ack ثبت شد")
    return rep


async def progress(tx: Tx, who: Principal, ref: str, step_fa: str) -> dict[str, Any]:
    """`order.progress`: one step in plain Persian."""
    rep = await ensure(tx, ref)
    assert rep is not None
    emp = await tx.one(
        """SELECT e.title_fa, c.name_fa AS company_fa FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id WHERE e.code = :c""",
        c=who.code,
    )
    await tx.exec(
        "UPDATE owner.order_reports SET last_step_at = now(), updated_at = now() WHERE id = :id",
        id=rep["id"],
    )
    await _append_steps(tx, rep["id"], [_step(who_fa(emp["title_fa"], emp["company_fa"]), step_fa)])
    await _close_nudges(tx, ref, "گزارش پیشرفت با order.progress ثبت شد")
    from hq_api.domain import order_turns as OT

    await OT.to_talk(tx, rep, who.code, step_fa)  # ⟨1.16⟩ §34.2 the live talk hears it too
    return rep


async def _append_steps(tx: Tx, report_id: UUID, steps: list[dict[str, Any]]) -> None:
    """New steps at the end; the oldest go past MAX_STEPS (the receipt stays first)."""
    if not steps:
        return
    cur = _j(await tx.scalar("SELECT steps FROM owner.order_reports WHERE id = :id", id=report_id))
    allx = list(cur or []) + steps
    if len(allx) > MAX_STEPS:
        allx = allx[:1] + allx[-(MAX_STEPS - 1) :]
    await tx.exec(
        "UPDATE owner.order_reports SET steps = CAST(:s AS jsonb), updated_at = now() WHERE id = :id",
        s=json.dumps(allx, ensure_ascii=False),
        id=report_id,
    )


# ----------------------------------------------------------------- blockers --
def _blocker(
    kind: str,
    title_fa: str,
    detail_fa: str,
    since: datetime | str,
    target: str | None = None,
) -> dict[str, Any]:
    """A blocker and its one-tap fix (none without a target to act on)."""
    action = FIX_OF.get(kind)
    fix = (
        {"action": action, "label_fa": FIX_LABEL_FA[action], "target": target}
        if action and target
        else None
    )
    return {
        "kind": kind,
        "title_fa": HZ.humanize(title_fa),
        "detail_fa": HZ.humanize(detail_fa),
        "since": since.isoformat() if isinstance(since, datetime) else str(since),
        "fix": fix,
    }


async def detect(
    tx: Tx, rep: dict[str, Any], order: dict[str, Any], works: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every blocker of an open order, by code (contract §29.2's table)."""
    now = datetime.now(UTC)
    since_of = {b["kind"] + str((b.get("fix") or {}).get("target")): b["since"]
                for b in _j(rep["blockers"]) or []}  # fmt: skip
    out: list[dict[str, Any]] = []

    def add(kind: str, title: str, detail: str, target: str | None = None) -> None:
        since = since_of.get(kind + str(target), now)
        b = _blocker(kind, title, detail, since, target)
        if all(x["kind"] != kind or (x["fix"] or {}).get("target") != target for x in out):
            out.append(b)

    draft = kit_of(order)
    if draft is not None:
        add(
            "kit_unsealed",
            "شرکت تازه منتظر مُهر شماست",
            "پیش‌نمایش آماده است و تا مُهر نکنید چیزی ساخته نمیشود.",
            draft["kit"],
        )
    open_works = [w for w in works if w["status"] in OPEN]
    ids = [w["id"] for w in works]
    # locked: a kill switch or a deploy freeze on a company of the order, or a hold
    for co_id, code, name in {(w["company_id"], w["company"], w["company_fa"]) for w in open_works}:
        lock = await tx.scalar("SELECT control.lock_state(:co)", co=co_id)
        if lock is not None:
            what = "فریز انتشار" if lock == "deploy_freeze" else "کلید توقف"
            scope = "holding" if lock == "holding" else f"company:{code}"
            add(
                "locked", f"{name or 'شرکت'} قفل است", f"{what} روشن است و کارها جلو نمیرود.", scope
            )
    held = await tx.all(
        """SELECT ref, target_ref FROM oversight.holds
           WHERE state = 'held' AND target_kind = 'work' AND target_ref = ANY(:refs)""",
        refs=[w["ref"] for w in open_works],
    )
    for h in held:
        add("locked", "یک کار نگه داشته شده", "ناظر کل این کار را تا تصمیم شما نگه داشته است.",
            f"hold:{h['ref']}")  # fmt: skip
    # what the agents' tools answered on the order's runs (hiring, budget, connections)
    codes = await tx.all(
        """SELECT DISTINCT a ->> 'code' AS code, a ->> 'tool' AS tool, r.work_id
           FROM agents.runs r JOIN agents.steps s ON s.run_id = r.id
           CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
           WHERE r.work_id = ANY(:ids) AND a ->> 'outcome' IS DISTINCT FROM 'ok'
             AND a ->> 'code' IS NOT NULL AND r.created_at >= :since""",
        ids=ids,
        since=order["created_at"],
    )
    hiring_state = await tx.scalar("SELECT core.hiring_state()")
    for c in codes:
        if c["code"] == "hiring_closed" and hiring_state != "open":
            add("hiring_closed", "استخدام بسته است", "یک کارمند خواست کسی را استخدام کند و نشد.",
                "holding")  # fmt: skip
        elif c["code"] == "envelope_exceeded":
            add("budget", "پاکت ماه شرکت پر است",
                "استخدام تازه در پاکت ماه این شرکت جا نشد.", None)  # fmt: skip
        elif c["code"] in CONNECTION_CODES:
            add("connection_missing", "یک اتصال وصل نیست",
                "کار به حسابی نیاز دارد که هنوز وصل نشده است.", str(c["tool"] or ""))  # fmt: skip
    # budget: the latest run of an open work stopped on a budget
    stopped = await tx.all(
        """SELECT DISTINCT ON (r.work_id) r.work_id, r.error_code, w.ref
           FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE r.work_id = ANY(:ids) AND r.state IN ('done', 'failed', 'refused')
           ORDER BY r.work_id, r.created_at DESC""",
        ids=[w["id"] for w in open_works],
    )
    for s in stopped:
        if s["error_code"] in BUDGET_CODES:
            add("budget", "بودجه‌ی این کار کم است",
                "کار در میانه ماند چون سقف مصرفش رسید.", s["ref"])  # fmt: skip
    # series_unsealed: a media item waits for a series card
    cards = await tx.all(
        """SELECT d.ref, d.payload ->> 'series' AS series FROM cartable.decisions d
           WHERE d.kind = 'media_series' AND d.status = 'pending'
             AND (d.work_id = ANY(:ids) OR (d.proposer_kind = 'agent' AND d.proposer_code = ANY(:codes)
                  AND d.created_at >= :since))""",
        ids=ids,
        codes=[w["a_code"] for w in works if w["a_code"]],
        since=order["created_at"],
    )
    for d in cards:
        add("series_unsealed", "سری انتشار منتظر مُهر شماست",
            "تا سری مُهر نشود، چیزی منتشر نمیشود.", d["series"] or d["ref"])  # fmt: skip
    # player_down: a work's named player is signed out, limited or off
    for w in open_works:
        if w["player"] in (None, "auto", "claude"):
            continue
        status = await tx.scalar(
            "SELECT status FROM substitutes.players WHERE player = :p", p=w["player"]
        )
        if status != "ready":
            add("player_down", "بازیکن انتخاب‌شده در دسترس نیست",
                "بازیکنی که برای این کار انتخاب شد الان کار نمیکند.", w["ref"])  # fmt: skip
    # no_employee: the media seat the order needs is empty
    route = _j(rep.get("route")) or {}
    kind = output_kind_of(order.get("text") or "", route)
    role = OUTPUT_ROLE.get(kind)
    for w in [x for x in open_works if x["is_root"]]:
        if role and (w["department"] == "MEDIA" or route.get("department") == "MEDIA"):
            has = await tx.scalar(
                """SELECT 1 FROM core.employees WHERE company_id = :co AND role = :r
                     AND status = 'active'""",
                co=w["company_id"],
                r=role,
            )
            if not has:
                add("no_employee", "کارمند لازم این کار نیست",
                    "رسانه‌ی این شرکت کسی را برای ساخت این خروجی ندارد.",
                    f"{w['company']}:{role}")  # fmt: skip
        dept = route.get("department")
        if dept and w["department"] and dept != w["department"]:
            add("no_employee", "دپارتمان مقصد کسی را ندارد",
                "کار به مدیرعامل رسید چون دپارتمان مقصد مدیری نداشت.", f"{w['company']}:{dept}")  # fmt: skip
    # no_progress: no plan within the minutes allowed (the timer marks it)
    if rep["ack"] is None and rep["ack_nudged_at"] is not None:
        add("no_progress", "هنوز برنامه‌ای نیامده",
            "مسئول کار در زمان مقرر برنامه نداد؛ مدیرعامل خبر شد.")  # fmt: skip
    if rep["talk_stopped_at"] is not None:
        out.append(
            _blocker(
                "talk_loop",
                "گیر کرد",
                "گیر کرد چون کارمندها چند بار کار کردند و هیچ خروجی ندادند؛ کارها متوقف شد.",
                rep["talk_stopped_at"],
            )
        )
    return out


# -------------------------------------------------------------------- state --
def state_of(
    rep: dict[str, Any], works: list[dict[str, Any]], blockers: list[dict[str, Any]]
) -> str:
    roots = [w for w in works if w["is_root"]]
    if not roots:
        if any(b["kind"] == "kit_unsealed" for b in blockers):
            return "waiting"
        return "planned" if rep["ack"] else "received"
    statuses = [w["status"] for w in roots]
    if all(s not in OPEN for s in statuses):
        if any(s in ("delivered", "done") for s in statuses):
            return "delivered"
        if all(s == "cancelled" for s in statuses):
            return "cancelled"
        return "failed"
    if _j(rep.get("turn")):  # ⟨1.16⟩ §34.3 the owner's turn: the holder asked and waits
        return "waiting"
    if blockers:
        return "blocked"
    if any(w["status"] == "waiting" for w in works if w["status"] in OPEN):
        return "waiting"
    if rep["ack"] is None:
        return "received" if all(w["status"] == "queued" for w in roots) else "in_progress"
    moved = len(works) > len(roots) or any(w["status"] != "queued" for w in roots)
    return "in_progress" if moved else "planned"


def summary_of(
    state: str,
    works: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, str]:
    finals = [o for o in outputs if o["kind"] != "partial"]
    if finals:
        names = "، ".join(o["title_fa"] for o in finals[-3:])
        done = f"{len(finals)} خروجی تحویل شد: {names}"
    elif state == "cancelled":
        done = "فرمان لغو شد"
    else:
        done = "هیچ خروجی کاملی تحویل نشد"
    left_works = [w for w in works if w["status"] in OPEN]
    failed = [w for w in works if w["status"] == "failed"]
    if left_works:
        left = f"{len(left_works)} کار باز ماند"
    elif failed:
        left = f"{len(failed)} کار ناموفق ماند"
    else:
        left = "چیزی نماند"
    fixable = [b for b in blockers if b.get("fix")]
    need = fixable[0]["fix"]["label_fa"] if fixable else "چیزی لازم نیست"
    return {"done_fa": HZ.humanize(done), "left_fa": HZ.humanize(left), "need_fa": need}


async def _outputs(tx: Tx, works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots = {w["id"] for w in works if w["is_root"]}
    rows = await tx.all(
        """SELECT ref, title, work_id, created_at FROM cartable.deliverables
           WHERE work_id = ANY(:ids) ORDER BY created_at, ref""",
        ids=[w["id"] for w in works],
    )
    out = []
    for r in rows:
        partial = W.is_partial_title(r["title"])
        kind = "partial" if partial else ("final" if r["work_id"] in roots else "part")
        out.append(
            {
                "ref": r["ref"],
                "title_fa": HZ.humanize(r["title"]) or "خروجی",
                "kind": kind,
                "at": r["created_at"].isoformat(),
            }
        )
    return out


def _digest(rep: dict[str, Any]) -> str:
    keep = {k: rep.get(k) for k in ("state", "ack", "steps", "blockers", "outputs", "summary",
                                    "turn", "conversation_ref")}  # fmt: skip
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()


async def refresh(tx: Tx, ref: str) -> dict[str, Any] | None:
    """Bring the report up to date: hand-overs and outputs as steps, the
    blockers, the state, and at the end the summary and its notification;
    `order.report` on the stream when anything changed."""
    rep = await ensure(tx, ref)
    if rep is None:
        return None
    order = await load_order(tx, ref)
    assert order is not None
    works = await tree(tx, root_refs(order))
    outputs = await _outputs(tx, works)
    new_steps: list[dict[str, Any]] = []
    known = set(rep["work_refs"] or [])
    for w in works:
        if w["ref"] not in known and not w["is_root"]:
            new_steps.append(
                _step("سامانه", f"به {who_fa(w['a_title_fa'], w['company_fa'])} سپرده شد")
            )
    seen = {o["ref"] for o in _j(rep["outputs"]) or []}
    for o in outputs:
        if o["ref"] not in seen:
            what = ("خروجی ناقص رسید: " if o["kind"] == "partial" else "خروجی رسید: ") + o[
                "title_fa"
            ]
            new_steps.append(_step("سامانه", what))
    ended = rep["ended_at"] is not None
    blockers = [] if ended else await detect(tx, rep, order, works)
    state = rep["state"] if ended else state_of(rep, works, blockers)
    summary = _j(rep["summary"])
    end_now = not ended and state in ENDED
    if end_now:
        summary = summary_of(state, works, outputs, blockers)
    await tx.exec(
        """UPDATE owner.order_reports
           SET state = :st, blockers = CAST(:b AS jsonb), outputs = CAST(:o AS jsonb),
               summary = CAST(:sm AS jsonb), work_refs = :refs, route = CAST(:route AS jsonb),
               ended_at = CASE WHEN :end THEN now() ELSE ended_at END,
               last_step_at = CASE WHEN :moved THEN now() ELSE last_step_at END,
               updated_at = now()
           WHERE id = :id""",
        st=state,
        b=json.dumps(blockers, ensure_ascii=False),
        o=json.dumps(outputs, ensure_ascii=False),
        sm=json.dumps(summary, ensure_ascii=False) if summary else None,
        refs=[w["ref"] for w in works],
        route=json.dumps(_route(order, works), ensure_ascii=False),
        end=end_now,
        moved=bool(new_steps),
        id=rep["id"],
    )
    await _append_steps(tx, rep["id"], new_steps)
    # ⟨1.14⟩ §32.2 an order made by a talk `ask` card: its answer goes back into
    # the conversation as a turn («جواب آمد»), once per deliverable
    from hq_api.talk import cards as talk_cards

    await talk_cards.on_outputs(tx, ref, [o for o in outputs if o["ref"] not in seen])
    rep = await tx.one("SELECT * FROM owner.order_reports WHERE id = :id", id=rep["id"])
    digest = _digest(dict(rep))
    if digest != rep["digest"]:
        await tx.exec(
            "UPDATE owner.order_reports SET digest = :d WHERE id = :id", d=digest, id=rep["id"]
        )
        holding = await _holding(tx)
        await events.emit(tx, holding["code"], "order.report", ref, {"state": state})
    if end_now:
        await _tell_end(tx, rep, order, state, summary or {})
    return dict(rep)


async def _tell_end(
    tx: Tx, rep: dict[str, Any], order: dict[str, Any], state: str, summary: dict[str, Any]
) -> None:
    holding = await _holding(tx)
    head = {"delivered": "فرمان شما تحویل شد", "failed": "فرمان شما به نتیجه نرسید",
            "cancelled": "فرمان شما لغو شد"}[state]  # fmt: skip
    text = " ".join((order.get("text") or "").split())[:80]
    body = HZ.plain(
        summary.get("done_fa", ""),
        summary.get("left_fa") if summary.get("left_fa") != "چیزی نماند" else None,
        summary.get("need_fa") if summary.get("need_fa") != "چیزی لازم نیست" else None,
    )
    await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="report",
        title_fa=f"{head}: {text}"[:300],
        body_fa=body[:4000],
        link_kind="order",
        link_ref=rep["ref"],
        source_kind="service",
        source_code="orders",
        domain="business",
    )


# ------------------------------------------------------------------- render --
async def report(tx: Tx, ref: str) -> OrderReport | None:
    rep = await refresh(tx, ref)
    if rep is None:
        return None
    order = await load_order(tx, ref)
    assert order is not None
    ids = [w["id"] for w in await tree(tx, root_refs(order))]
    return render(
        rep,
        order,
        parts=await SP.views(tx, ids) if ids else [],
        workspaces=await WS.progress(tx, ids) if ids else [],
    )


def render(
    rep: dict[str, Any],
    order: dict[str, Any],
    *,
    parts: list[SP.WorkSplit] | None = None,
    workspaces: list[WS.WorkspaceProgress] | None = None,
) -> OrderReport:
    ack = _j(rep["ack"])
    if ack:
        by = actor(ack["by"]["kind"], ack["by"]["code"])
        ack = {
            **ack,
            "by": by,
            "plan_fa": HZ.humanize(ack.get("plan_fa")) or "-",
        }
    turn = _j(rep.get("turn"))
    if turn:
        turn = {**turn, "by": actor(turn["by"]["kind"], turn["by"]["code"]),
                "question_fa": HZ.humanize(turn.get("question_fa")) or "-"}  # fmt: skip
    return OrderReport(
        ref=rep["ref"],
        text_fa=order.get("text") or "",
        at=order["created_at"],
        state=rep["state"],
        ack=Ack.model_validate(ack) if ack else None,
        route=Route.model_validate(_j(rep["route"]) or {}),
        steps=[Step.model_validate(s) for s in _j(rep["steps"]) or []],
        blockers=[Blocker.model_validate(b) for b in _j(rep["blockers"]) or []],
        outputs=[Output.model_validate(o) for o in _j(rep["outputs"]) or []],
        summary=Summary.model_validate(_j(rep["summary"])) if rep["summary"] else None,
        updated_at=rep["updated_at"],
        kit=kit_card(order, sealed=rep["ended_at"] is not None),
        parts=parts or [],
        workspaces=workspaces or [],
        pace=order.get("pace") or "auto",
        turn=Turn.model_validate(turn) if turn else None,
        conversation_ref=rep.get("conversation_ref"),
    )


def kit_card(order: dict[str, Any], *, sealed: bool) -> KT.KitCard | None:
    draft = kit_of(order)
    if draft is None or draft["kit"] not in KT.kits():
        return None
    summary = KT.describe(draft["kit"])
    return KT.KitCard(
        kit=draft["kit"],
        title_fa=summary.title_fa,
        name_fa=draft["name_fa"],
        sealed=sealed,
        summary=summary,
    )


async def list_fields(tx: Tx, refs: list[str]) -> dict[str, dict[str, Any]]:
    """For GET /orders: each order's `state` and `summary` (plain Persian
    lines; null while it runs), from the stored reports."""
    rows = await tx.all(
        "SELECT ref, state, summary FROM owner.order_reports WHERE ref = ANY(:r)", r=refs
    )
    out = {}
    for r in rows:
        s = _j(r["summary"])
        out[r["ref"]] = {"state": r["state"], "summary": s}
    return out


# ---------------------------------------------------------------- the timers --
async def _ceo_of(tx: Tx, works: list[dict[str, Any]]) -> dict[str, Any] | None:
    root = next((w for w in works if w["is_root"]), None)
    if root is None:
        return None
    return await tx.first(
        """SELECT e.code, c.code AS company, c.id AS company_id FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE e.company_id = :co AND e.kind = 'ceo' AND e.status = 'active'
           ORDER BY e.hired_at LIMIT 1""",
        co=root["company_id"],
    )


async def _nudge(
    tx: Tx, works: list[dict[str, Any]], ref: str, title: str, brief: str
) -> str | None:
    """A small work item for the CEO of the order's first company."""
    ceo = await _ceo_of(tx, works)
    if ceo is None:
        return None
    w = await W.create(
        tx,
        SERVICE,
        company_id=ceo["company_id"],
        company_code=ceo["company"],
        title=(NUDGE.format(ref=ref) + title)[:300],
        brief=brief,
        kind="one_off",
        priority="P1",
        assignee_code=ceo["code"],
    )
    return str(w["ref"])


async def stop_talk(tx: Tx, rep: dict[str, Any], works: list[dict[str, Any]], runs: int) -> None:
    """More than ORDER_TALK_LIMIT runs without an output: the order's queued
    runs are refused (a running one stops at its next step)."""
    await tx.exec(
        """UPDATE agents.runs SET state = 'refused', error_code = 'talk_loop', finished_at = now(),
               note = 'order stopped: too many runs without an output'
           WHERE state = 'queued' AND work_id = ANY(:ids)""",
        ids=[w["id"] for w in works],
    )
    await tx.exec(
        "UPDATE owner.order_reports SET talk_stopped_at = now(), updated_at = now() WHERE id = :id",
        id=rep["id"],
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=rep["company_id"],
        action="order.talk_loop",
        action_class="A2",
        target_kind="order",
        target_ref=rep["ref"],
        summary=f"{runs} agent runs without an output: the order's runs stopped",
    )


async def timers(tx: Tx, s: Any, ref: str) -> list[str]:
    """The order's timers, once each (contract §29.2): what fired."""
    rep = await ensure(tx, ref)
    if rep is None or rep["ended_at"] is not None:
        return []
    order = await load_order(tx, ref)
    assert order is not None
    works = await tree(tx, root_refs(order))
    if not works:
        return []
    fired: list[str] = []
    now = await tx.scalar("SELECT now()")
    created = order["created_at"]
    if (
        rep["ack"] is None
        and rep["ack_nudged_at"] is None
        and now - created >= timedelta(minutes=s.order_ack_minutes)
    ):
        await _nudge(
            tx, works, ref, "دریافت و برنامه",
            f"فرمان {ref} مدیر کل {s.order_ack_minutes} دقیقه بی‌پاسخ مانده است. همین حالا با "
            f"order.ack (ref={ref}) برنامه را ثبت کن: plan_fa، کسانی که کار را گرفتند و موعد تحویل.",
        )  # fmt: skip
        await tx.exec(
            "UPDATE owner.order_reports SET ack_nudged_at = now() WHERE id = :id", id=rep["id"]
        )
        fired.append("ack")
    last = max(x for x in (created, rep["acked_at"], rep["last_step_at"]) if x is not None)
    if _j(rep.get("turn")):
        # ⟨1.16⟩ §34.3 the holder asked and waits for the owner: no «no progress» nudge
        last = now
    if now - last >= timedelta(hours=s.order_progress_hours) and (
        rep["progress_nudged_at"] is None or rep["progress_nudged_at"] < last
    ):
        await _nudge(
            tx, works, ref, "گزارش پیشرفت",
            f"فرمان {ref} مدیر کل {s.order_progress_hours} ساعت است قدمی نداشته. با "
            f"order.progress (ref={ref}) بگو کجاست، چه چیزی مانده و چه چیزی گیر است.",
        )  # fmt: skip
        await tx.exec(
            "UPDATE owner.order_reports SET progress_nudged_at = now() WHERE id = :id",
            id=rep["id"],
        )
        fired.append("progress")
    if now - last >= timedelta(hours=s.order_owner_hours) and (
        rep["owner_told_at"] is None or rep["owner_told_at"] < last
    ):
        holding = await _holding(tx)
        why = [b["title_fa"] for b in _j(rep["blockers"]) or []]
        text = " ".join((order.get("text") or "").split())[:80]
        await notify.raise_notification(
            tx,
            company_id=holding["id"],
            company_code=holding["code"],
            level="decision",
            title_fa=f"فرمان شما {s.order_owner_hours} ساعت است جلو نرفته: {text}"[:300],
            body_fa=HZ.plain(
                f"از {s.order_owner_hours} ساعت پیش قدمی برداشته نشده است",
                "؛ ".join(why) if why else "مسئول کار گزارشی نداده است",
                "گزارش فرمان را ببینید و اگر دکمه‌ی رفعی هست بزنید",
            ),
            link_kind="order",
            link_ref=ref,
            source_kind="service",
            source_code="orders",
            domain="business",
        )
        await tx.exec(
            "UPDATE owner.order_reports SET owner_told_at = now() WHERE id = :id", id=rep["id"]
        )
        fired.append("owner")
    if rep["talk_stopped_at"] is None:
        runs = await tx.scalar(
            """SELECT count(*) FROM agents.runs r
               WHERE r.work_id = ANY(:ids) AND r.state IN ('running', 'done', 'failed')
                 AND r.created_at > COALESCE(
                     (SELECT max(d.created_at) FROM cartable.deliverables d
                       WHERE d.work_id = ANY(:ids) AND NOT starts_with(d.title, :partial)),
                     :since)""",
            ids=[w["id"] for w in works],
            partial=W.PARTIAL_PREFIX,
            since=created,
        )
        if int(runs or 0) > s.order_talk_limit:
            await stop_talk(tx, rep, works, int(runs))
            fired.append("talk_loop")
    return fired


async def tick(hub: Any) -> dict[str, Any]:
    """The worker's tick (every few minutes, rule-based): the reports of the
    owner's open orders (and of the last week's orders without one yet) are
    brought up to date and their timers run."""
    out: dict[str, Any] = {"orders": 0, "fired": {}}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out["resumed"] = await W.resume_waiting(tx)  # budget added, the player set to auto
        refs = [
            r["ref"]
            for r in await tx.all(
                """SELECT o.ref FROM owner.orders o
                   LEFT JOIN owner.order_reports r ON r.order_id = o.id
                   WHERE (r.id IS NULL AND o.created_at > now() - interval '7 days')
                      OR (r.id IS NOT NULL AND r.ended_at IS NULL)
                   ORDER BY o.created_at"""
            )
        ]
    for ref in refs:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            fired = await timers(tx, hub.settings, ref)
            await refresh(tx, ref)
        out["orders"] += 1
        if fired:
            out["fired"][ref] = fired
    return out


# ------------------------------------------------------------ the runner --
async def order_of_work(tx: Tx, work_id: UUID) -> str | None:
    """The order a work item belongs to (up its parents and its requests)."""
    ref: str | None = await tx.scalar(
        """WITH RECURSIVE up(id, hops) AS (
               SELECT CAST(:w AS uuid), 0
               UNION
               SELECT COALESCE(w.parent_id, w.requested_by_work_id), up.hops + 1
               FROM work.work w JOIN up ON w.id = up.id
               WHERE COALESCE(w.parent_id, w.requested_by_work_id) IS NOT NULL AND up.hops < 20)
           SELECT r.ref FROM owner.order_reports r
           WHERE r.work_refs && ARRAY(SELECT w.ref FROM work.work w WHERE w.id IN (SELECT id FROM up))
           ORDER BY r.created_at DESC LIMIT 1""",
        w=str(work_id),
    )
    return ref


async def stopped(tx: Tx, work_id: UUID | None) -> bool:
    """Whether the work's order was stopped for talking without output."""
    if work_id is None:
        return False
    ref = await order_of_work(tx, work_id)
    if ref is None:
        return False
    return bool(
        await tx.scalar(
            "SELECT talk_stopped_at IS NOT NULL FROM owner.order_reports WHERE ref = :r", r=ref
        )
    )
