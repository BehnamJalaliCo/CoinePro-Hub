"""Every order is answered (contract §29.2, the owner's ask 2 of 2026-11-02).

One report per order of the owner (owner.order_reports, F-…), over every work
item the order made: its root works (owner.orders.routes[].work_ref), their
children and the requests made from them, in any company.

    received -> planned (the assignee's plan, `order.ack`) -> in_progress
             -> waiting | blocked -> delivered | failed | cancelled

What happens, by code (no model):
- the dispatcher's receipt «دریافت شد؛ به … سپرده شد» at once
  (`on_order_routed`, called after routing; a report made later writes it too);
- steps: the plan and each `order.progress` (⟨2026-11-07⟩ W9 D: no longer a line per hand-over
  or per output; the outputs are listed as themselves, the holder's plan names who got what);
- blockers, detected on every change and every few minutes, each with its
  one-tap fix (`no_employee` hire, `hiring_closed` hiring.open, `locked`
  lock.open, `series_unsealed` series.seal, `player_down` player.auto,
  `connection_missing` connection.guide; `no_progress` and `talk_loop` have
  none; ⟨2026-11-08⟩ `budget` only for a company's month envelope on a hire:
  an owner's order has no token cap);
- timers (the worker's tick): 10 minutes without a plan wakes the CEO with a
  small work item; 2 hours without a step the CEO must report; 6 hours the
  owner hears why (one decision-level notification, domain business);
- talk without output: more than ORDER_TALK_LIMIT agent runs on the order
  without a (complete) output stop the order's open runs;
- the end: «چه شد» · «چه ماند» · «از شما چه لازم است», and one report
  notification.
- ⟨1.17⟩ §35.1 the order no longer ends by itself: when its root works are delivered the session
  is `ready` (badge, one notification) and waits for the owner's close (domain.sessions), which
  alone sets `ended_at`; the report keeps refreshing while open.
Every text the owner reads passes humanize (§29.7).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import kits as KT
from hq_api.domain import notify
from hq_api.domain import session_shapes as SS
from hq_api.domain import split as SP
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.domain.connections import KINDS as CN_KINDS
from hq_api.principal import Principal
from hq_api.schemas import Actor, FileRef, actor

log = logging.getLogger("hq_api.order_report")
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
    # ⟨2026-11-08⟩ audit M4, M10: the month envelope (readiness §29.9 has it), the media tools
    "envelope.set": "پاکت ماه را تعیین کن",
    "media.on": "ابزار رسانه را روشن کن",
}
# ⟨2026-11-08⟩ audit M10: a tool's refusal for a missing account, in words, and what fixes it
# (never a guide that does not exist: a sign-in or a player's account has no page of its own yet)
TOOL_CONNECTION_FA: dict[str, tuple[str, str, str | None, str | None]] = {
    "substitute.call": (
        "بازیکن بیرونی وارد حسابش نیست",
        "ChatGPT، Gemini یا DeepSeek باید در صفحه‌ی بازیکن‌ها وارد شود.",
        None,
        None,
    ),
    "speech.make": (
        "گوینده وارد حسابش نیست",
        "Google AI Studio روی هاب یک بار ورود میخواهد؛ بعد صدای گوینده‌ی ریلز ساخته میشود.",
        None,
        None,
    ),
}
# ⟨2026-11-08⟩ the owner's decisions: the hub's own media tools are not his business; a refusal of
# these tools is never a blocker, a readiness item or a step of the owner's (video is the
# workshop's). ⟨2026-11-10⟩ `speech.make` left this list: the narrator of content is on (he
# switched off only his own voice talk), and AI Studio signed out is his one sign-in.
SILENT_TOOLS = ("media.render", "media.item", "media.on")
IG_SETUP_STEP_FA = "تیم فنی حساب‌های اینستاگرام را از راه {server} به هاب معرفی میکند"
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


def route_company(rep: dict[str, Any]) -> str | None:
    route = _j(rep.get("route")) or {}
    cos = route.get("companies") or []
    return str(cos[0]) if cos else None


UNCAPPED_FA = "سقف مصرف این کار برداشته شد؛ کار ادامه دارد"  # ⟨2026-11-08⟩ budget.add, no figure


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


class Ask(BaseModel):
    """⟨1.17⟩ §35.4 one question of the open turn (a second `order.ask` joins the same turn)."""

    question_fa: str
    at: datetime
    by: Actor
    who_fa: str


class Turn(BaseModel):
    """⟨1.16⟩ §34.3 the holder's open question to the owner (`order.ask`); `question_fa` holds
    every open question, `asks` each one."""

    question_fa: str
    at: datetime
    by: Actor
    who_fa: str
    asks: list[Ask] = Field(default_factory=list)


class OrderCard(BaseModel):
    """⟨2026-11-10⟩ A card of this order that waits for a decision, shown IN its session (the
    owner, in his session: «بیار مهر کنم» — the holder had said «کارت منتظر مُهر شماست» and the
    card was on another page). The owner seals any of them from here (`POST
    /decisions/{ref}/approve`, its own step-up); one routed to a CEO or a manager says so."""

    ref: str
    kind: str
    title_fa: str
    by_fa: str | None = None  # who proposed it
    waits_fa: str  # «منتظر مُهر شما» · «منتظر تصمیم مدیرعامل …»
    with_owner: bool  # false: an agent (the CEO, a manager) decides it; the owner still may
    seal: Literal["passkey", "tap"]
    created_at: datetime


class SessionPublish(BaseModel):
    """⟨2026-11-10⟩ §44.5 one «تأیید و انتشار» of a session (domain.session_publish): the publish
    job on IG-Hub's server and where it stands."""

    job: str | None = None
    output: str | None = None
    file_id: str
    file_name: str | None = None
    cover_name: str | None = None  # a reel's cover, when the owner chose one
    channel: Literal["instagram"] = "instagram"
    kind: Literal["reel", "post", "story", "carousel"]
    account: str | None = None
    # ⟨§46⟩ `scheduled`: IG-Hub holds it for `scheduled_at`
    # ⟨§51⟩ `cancelled`: he took it back before it went out
    state: Literal[
        "publishing", "scheduled", "published", "failed", "waiting_seal", "waiting_setup",
        "cancelled",
    ]  # fmt: skip
    url: str | None = None
    note_fa: str | None = None
    at: datetime | None = None
    published_at: datetime | None = None
    # ⟨§45⟩ true: the hub sent it on the owner's standing permission (no tap)
    auto: bool = False
    # ⟨§46⟩ the time it is set for; the word viewers comment for its link; a carousel's files
    scheduled_at: datetime | None = None
    comment: str | None = None
    files: int = 1


class PublishComment(BaseModel):
    """⟨§46⟩ A comment rule for one post: who comments one of `keywords` on it gets `reply`
    in private (with `link` as a button) and, when given, one of `public_replies`."""

    keywords: list[str] = Field(default_factory=list)
    reply: str = ""
    link: str | None = None
    button: str | None = None
    public_replies: list[str] = Field(default_factory=list)


class SessionRoutine(BaseModel):
    """⟨1.31⟩ §50 A standing routine as the session (and the app) shows it (domain.routines).
    `when_fa`: its schedule in plain Persian; `preview_fa`: what each run does, written by code
    from the checked rule; `next_at`: its next run while it is `on`."""

    ref: str
    company: str | None = None
    sentence_fa: str
    when_fa: str
    preview_fa: str
    state: Literal["proposed", "on", "off"]
    next_at: datetime | None = None
    last_run_at: datetime | None = None
    runs: int = 0
    order: str | None = None
    note_fa: str | None = None


class BestHour(BaseModel):
    """⟨§49⟩ The hour a company's Instagram account does best at (domain.best_hour). `hour`
    («HH:MM», the owner's zone) and `at` (its next occurrence) are null while the data is too
    thin (`enough: false`); `note_fa` says what it rests on, or what is missing. `basis` is what
    is counted: likes and comments (IG-Hub reads no views or reach)."""

    account: str | None = None
    hour: str | None = None
    at: datetime | None = None
    enough: bool = False
    posts: int = 0
    days: int = 0
    basis: Literal["likes_comments"] = "likes_comments"
    note_fa: str = "آمار پست‌های این حساب هنوز از IG-Hub خوانده نشده است"
    read_at: datetime | None = None


class PublishPanel(BaseModel):
    """⟨2026-11-10⟩ §44.5 what the output's page shows of «تأیید و انتشار»: the session the
    output belongs to, the company's accounts, and this output's publishes. ⟨§45⟩ `tap`: the
    output can be published by a tap (any output of a company's work; `order` is null for one of
    no session, e.g. a working group's daily output); `caption`: the caption its package carries
    (`caption.txt` among its files), for the sheet; `group`, `mode`: the working group whose
    routine made it and the owner's standing word for it (`auto`: it goes out by itself)."""

    order: str | None = None
    channel: Literal["instagram"] = "instagram"
    accounts: list[str] = Field(default_factory=list)
    ready: bool = False
    publishes: list[SessionPublish] = Field(default_factory=list)
    tap: bool = False
    caption: str | None = None
    # ⟨§46⟩ the comment rule its package carries (`comment.txt`), for the sheet
    comment: PublishComment | None = None
    group: str | None = None
    group_fa: str | None = None
    mode: Literal["ask", "auto"] | None = None
    # ⟨§49⟩ the hour this account's posts do best at, once there is a month of them (else null)
    best: BestHour | None = None


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
    # ⟨1.17⟩ §35.2 the session: its state and badge, the brief «چه شد · حالا چه · از تو چه», the
    # plan and who is present (domain.sessions)
    session: SS.SessionState | None = None
    brief: SS.Brief | None = None
    tasks: list[SS.SessionTask] = Field(default_factory=list)
    participants: list[SS.Participant] = Field(default_factory=list)
    # ⟨1.18⟩ §36.3 the owner's files of the session (every file of the owner's turns), newest first
    files: list[FileRef] = Field(default_factory=list)
    # ⟨1.22⟩ §40.1 the session's memory («تا اینجا»; read-only: code and a small model keep it)
    memory_md: str | None = None
    # ⟨2026-11-10⟩ the order's cards that wait for a decision, oldest first (sealed from the session)
    cards: list[OrderCard] = Field(default_factory=list)
    # ⟨2026-11-10⟩ §44.5 what the owner published from this session («تأیید و انتشار»), newest first
    publishes: list[SessionPublish] = Field(default_factory=list)
    # ⟨1.31⟩ §50 the standing routines the owner asked for in this session («کارمند ۲۴ ساعته»),
    # newest first; each is switched with POST /automations/{ref}/state
    routines: list[SessionRoutine] = Field(default_factory=list)
    # ⟨1.32⟩ §54 true: the session is direct now (its holder works as one Claude Code session on
    # the workshop, with the hub's tools); false: the workshop cannot take it and the holder
    # works the classic way
    direct: bool = False


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
    rep = await tx.first("SELECT ended_at, state FROM owner.order_reports WHERE ref = :r", r=ref)
    draft = kit_of(order or {})
    return (
        draft is not None
        and draft["kit"] == kit
        and (rep is None or (rep["ended_at"] is None and rep["state"] != "delivered"))
    )


async def kit_sealed(tx: Tx, ref: str, code: str, name_fa: str) -> None:
    """The owner sealed the kit card: the order is delivered (its company exists). ⟨1.17⟩ §35.1
    the session stays open (`ready`) until the owner closes it."""
    rep = await ensure(tx, ref)
    if rep is None or rep["ended_at"] is not None or rep["state"] == "delivered":
        return
    done = HZ.humanize(f"شرکت {name_fa} ({code}) از روی پیش‌نمایش ساخته شد")
    await _append_steps(tx, rep["id"], [_step("سامانه", done)])
    await tx.exec(
        """UPDATE owner.order_reports
           SET state = 'delivered', blockers = '[]'::jsonb, last_step_at = now(),
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
    await refresh(tx, ref)  # the badge: ready


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
    action: str | None = None,
) -> dict[str, Any]:
    """A blocker and its one-tap fix (none without a target to act on); `action` overrides the
    kind's default fix (⟨2026-11-08⟩ `envelope.set`, `media.on`)."""
    action = action or FIX_OF.get(kind)
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


async def _ig_setup(
    tx: Tx, rep: dict[str, Any], work_id: UUID | None, company_code: str | None
) -> None:
    """⟨2026-11-08⟩ a run of the order met Instagram not registered here: the holding's technical
    work (IG-Hub's CTO, else AIOPS) is made once, under the order's work, and the session gets one
    technical step, once. Never fails the report."""
    from hq_api.domain import connections as CN

    if company_code is None:
        return
    try:
        async with tx.conn.begin_nested():
            co_id = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=company_code)
            if co_id is None:
                return
            ref = await CN.ensure_ig_setup_work(tx, co_id, requested_by=work_id)
            if ref is None:
                return
            line = IG_SETUP_STEP_FA.format(server=CN.ig_hub()["server"])
            steps = _j(rep.get("steps")) or []
            if all(s.get("what_fa") != HZ.humanize(line) for s in steps):
                await _append_steps(tx, rep["id"], [_step("سامانه", line)])
    except Exception:  # noqa: BLE001 - the technical work never fails the owner's report
        log.warning("ig setup work could not be made", extra={"company": company_code})


async def detect(
    tx: Tx, rep: dict[str, Any], order: dict[str, Any], works: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every blocker of an open order, by code (contract §29.2's table)."""
    now = datetime.now(UTC)
    since_of = {b["kind"] + str(b.get("title_fa")) + str((b.get("fix") or {}).get("target")): b["since"]
                for b in _j(rep["blockers"]) or []}  # fmt: skip
    out: list[dict[str, Any]] = []

    def add(
        kind: str, title: str, detail: str, target: str | None = None, action: str | None = None
    ) -> None:
        # one blocker per kind, wording and target (⟨2026-11-08⟩ two tools' missing accounts of the
        # same kind are two lines, each with its own fix or none)
        b = _blocker(kind, title, detail, now, target, action)
        b["since"] = since_of.get(kind + b["title_fa"] + str(target), b["since"])
        if all(
            x["kind"] != kind
            or x["title_fa"] != b["title_fa"]
            or (x["fix"] or {}).get("target") != target
            for x in out
        ):
            out.append(b)

    draft = kit_of(order)
    if draft is not None and rep["state"] != "delivered":  # sealed: the company exists
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
    company_of = {w["id"]: w["company"] for w in works}
    for c in codes:
        if c["code"] == "hiring_closed" and hiring_state != "open":
            add("hiring_closed", "استخدام بسته است", "یک کارمند خواست کسی را استخدام کند و نشد.",
                "holding")  # fmt: skip
        elif c["code"] in ("envelope_exceeded", "envelope_required"):
            # ⟨2026-11-08⟩ audit M4: both are the month envelope's, with its one-tap fix
            co = company_of.get(c["work_id"]) or route_company(rep)
            full = c["code"] == "envelope_exceeded"
            add("budget",
                "پاکت ماه شرکت پر است" if full else "پاکت ماه شرکت تعیین نشده",
                "استخدام تازه در پاکت ماه این شرکت جا نشد." if full
                else "تا پاکت ماه شرکت تعیین نشود، استخدامی انجام نمیشود.",
                co, "envelope.set")  # fmt: skip
        elif c["tool"] == "speech.make" and c["code"] in (
            "signed_out",
            "expired",
            *CONNECTION_CODES,
        ):
            # ⟨2026-11-10⟩ the narrator: a blocker only while AI Studio is signed out NOW (the
            # owner's one sign-in); once a voice was made it is gone
            from hq_api.domain import speech_make as SM

            if (await SM.speech_state(tx)).get("aistudio") == "signed_out":
                title, detail, action, target = TOOL_CONNECTION_FA["speech.make"]
                add("connection_missing", title, detail, target, action)
        elif c["code"] in CONNECTION_CODES:
            # ⟨2026-11-08⟩ audit M10: the tool in words; a fix only where a page for it exists
            tool = str(c["tool"] or "")
            if tool in SILENT_TOOLS:
                continue  # the hub's own media tools: never the owner's (the owner, 2026-11-08)
            if tool in TOOL_CONNECTION_FA:
                title, detail, action, target = TOOL_CONNECTION_FA[tool]
                add("connection_missing", title, detail, target, action)
            elif tool == "instagram":
                # ⟨2026-11-08⟩ the owner: Instagram is on IG-Hub for every company; no blocker —
                # the technical work that registers the accounts is made by code, under this
                # order, and the session reads one technical step
                await _ig_setup(tx, rep, c["work_id"], company_of.get(c["work_id"]))
            elif tool in CN_KINDS:
                add("connection_missing", "یک اتصال وصل نیست",
                    "کار به حسابی نیاز دارد که هنوز وصل نشده است.", tool)  # fmt: skip
            else:
                add("connection_missing", "یک اتصال وصل نیست",
                    "کار به حسابی نیاز دارد که هنوز وصل نشده است.", None)  # fmt: skip
    # ⟨2026-11-08⟩ the owner: «کلا بودجه رو سقفشو بردار»: a work of an owner's order has no token
    # budget (routes/orders), so no `budget` blocker is raised for it; a run that reached its own
    # per-run cap delivered what it had and the session's sweep wakes the holder (§41.3)
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
    rep: dict[str, Any],
    works: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    order: dict[str, Any] | None = None,
) -> str:
    roots = [w for w in works if w["is_root"]]
    if not roots:
        if any(b["kind"] == "kit_unsealed" for b in blockers):
            return "waiting"
        if rep["state"] == "delivered" and kit_of(order or {}) is not None:
            return "delivered"  # a sealed kit (no work item ever)
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
                                    "turn", "conversation_ref", "badge", "closed_at", "hidden_at")}  # fmt: skip
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
    # ⟨2026-11-07⟩ W9 D (the owner: «این بروکراسی اداری چیه»): no step that only says a work was
    # handed over («به … سپرده شد»: the holder's own plan and the card's line say it) and no
    # «سامانه: خروجی رسید» repeating an output that is listed under `outputs` itself; a new work
    # or a new output still moves the story's clock (`last_step_at`)
    known = set(rep["work_refs"] or [])
    seen = {o["ref"] for o in _j(rep["outputs"]) or []}
    moved = any(w["ref"] not in known for w in works) or any(o["ref"] not in seen for o in outputs)
    # ⟨1.17⟩ §35.1 the order ends only by the owner's close (ended_at is the close's): while the
    # session is open the report keeps moving, delivered root works make it `ready`
    ended = rep["ended_at"] is not None
    blockers = [] if ended else await detect(tx, rep, order, works)
    state = rep["state"] if ended else state_of(rep, works, blockers, order)
    summary = _j(rep["summary"])
    if not ended and state in ENDED and works:  # a sealed kit keeps its own summary
        summary = summary_of(state, works, outputs, blockers)
    await tx.exec(
        """UPDATE owner.order_reports
           SET state = :st, blockers = CAST(:b AS jsonb), outputs = CAST(:o AS jsonb),
               summary = CAST(:sm AS jsonb), work_refs = :refs, route = CAST(:route AS jsonb),
               last_step_at = CASE WHEN :moved THEN now() ELSE last_step_at END,
               updated_at = now()
           WHERE id = :id""",
        st=state,
        b=json.dumps(blockers, ensure_ascii=False),
        o=json.dumps(outputs, ensure_ascii=False),
        sm=json.dumps(summary, ensure_ascii=False) if summary else None,
        refs=[w["ref"] for w in works],
        route=json.dumps(_route(order, works), ensure_ascii=False),
        moved=moved,
        id=rep["id"],
    )
    # ⟨1.14⟩ §32.2 an order made by a talk `ask` card: its answer goes back into
    # the conversation as a turn («جواب آمد»), once per deliverable
    from hq_api.domain import sessions as SE
    from hq_api.talk import cards as talk_cards

    await talk_cards.on_outputs(tx, ref, [o for o in outputs if o["ref"] not in seen])
    rep = dict(await tx.one("SELECT * FROM owner.order_reports WHERE id = :id", id=rep["id"]))
    # ⟨1.17⟩ §35.2 the badge, by code; a change streams `session.updated`
    pending = await SE.decisions_pending(tx, [w["id"] for w in works])
    # ⟨1.23⟩ §41.3 `moving` only while a run is queued or running; idle too long is `stuck`
    from hq_api.domain import session_activity as SA

    pulse = await SA.read_pulse(tx, rep, works)
    badge, _ = SE.badge_of(rep, state, works, blockers, decision_pending=pending, pulse=pulse)
    if badge != rep["badge"]:
        await SE.badge_changed(tx, rep, badge, order)
        rep["badge"] = badge
    digest = _digest(rep)
    if digest != rep["digest"]:
        await tx.exec(
            "UPDATE owner.order_reports SET digest = :d WHERE id = :id", d=digest, id=rep["id"]
        )
        holding = await _holding(tx)
        await events.emit(tx, holding["code"], "order.report", ref, {"state": state})
    return rep


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
    works = await tree(tx, root_refs(order))
    ids = [w["id"] for w in works]
    from hq_api.domain import files as F
    from hq_api.domain import sessions as SE

    out = render(
        rep,
        order,
        parts=await SP.views(tx, ids) if ids else [],
        workspaces=await WS.progress(tx, ids) if ids else [],
        session=await SE.view(tx, rep, order, works=works),
    )
    out.files = [F.render(f) for f in await F.of_order(tx, rep["order_id"])]  # ⟨1.18⟩ §36.3
    if rep.get("ended_at") is None:
        out.cards = await cards_of(tx, order, works)
    from hq_api.domain import session_publish as SPB

    out.publishes = await SPB.of_order(tx, rep["ref"])
    from hq_api.domain import routines as RT

    out.routines = await RT.of_order(tx, rep["ref"])
    from hq_api.domain import direct as DR

    out.direct = await DR.server_for(tx) is not None
    return out


async def cards_of(tx: Tx, order: dict[str, Any], works: list[dict[str, Any]]) -> list[OrderCard]:
    """The pending cards of the order: raised on one of its works, or by someone working on it
    since it began (as the series blocker reads them)."""
    from hq_api.domain import decisions as DC

    ids = [w["id"] for w in works]
    codes = [w["a_code"] for w in works if w["a_code"]]
    if not ids:
        return []
    rows = await tx.all(
        """SELECT d.ref, d.kind, d.action_class, d.title, d.approver_code, d.created_at,
                  p.title_fa AS by_title, pc.name_fa AS by_company, a.title_fa AS approver_title
           FROM cartable.decisions d
           LEFT JOIN core.employees p ON d.proposer_kind = 'agent' AND p.code = d.proposer_code
           LEFT JOIN core.companies pc ON pc.id = p.company_id
           LEFT JOIN core.employees a ON a.code = d.approver_code
           WHERE d.status = 'pending'
             AND (d.work_id = ANY(:ids) OR (d.proposer_kind = 'agent'
                  AND d.proposer_code = ANY(:codes) AND d.created_at >= :since))
           ORDER BY d.created_at LIMIT 20""",
        ids=ids,
        codes=codes,
        since=order["created_at"],
    )
    out: list[OrderCard] = []
    for d in rows:
        mine = d["approver_code"] is None
        who = HZ.humanize(str(d["approver_title"] or "")) or "مدیر شرکت"
        out.append(
            OrderCard(
                ref=d["ref"],
                kind=d["kind"],
                title_fa=HZ.humanize(str(d["title"])) or str(d["title"]),
                by_fa=who_fa(d["by_title"], d["by_company"]) if d["by_title"] else None,
                waits_fa="منتظر مُهر شما"
                if mine
                else f"منتظر تصمیم {who}؛ شما هم میتوانید مُهر کنید",
                with_owner=mine,
                seal="passkey" if DC.needs_step_up(dict(d)) else "tap",
                created_at=d["created_at"],
            )
        )
    return out


def render(
    rep: dict[str, Any],
    order: dict[str, Any],
    *,
    parts: list[SP.WorkSplit] | None = None,
    workspaces: list[WS.WorkspaceProgress] | None = None,
    session: Any = None,
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
        asks = [
            {**a, "by": actor(a["by"]["kind"], a["by"]["code"]),
             "question_fa": HZ.humanize(a.get("question_fa")) or "-"}
            for a in turn.get("asks") or []
            if isinstance(a, dict) and a.get("by")
        ]  # fmt: skip
        turn = {**turn, "by": actor(turn["by"]["kind"], turn["by"]["code"]),
                "question_fa": HZ.humanize(turn.get("question_fa")) or "-", "asks": asks}  # fmt: skip
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
        kit=kit_card(order, sealed=rep["ended_at"] is not None or rep["state"] == "delivered"),
        parts=parts or [],
        workspaces=workspaces or [],
        pace=order.get("pace") or "auto",
        turn=Turn.model_validate(turn) if turn else None,
        conversation_ref=rep.get("conversation_ref"),
        session=session.session if session is not None else None,
        brief=session.brief if session is not None else None,
        tasks=session.tasks if session is not None else [],
        participants=session.participants if session is not None else [],
        memory_md=rep.get("memory_md"),
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
    turn = _j(rep.get("turn"))
    roots = [w for w in works if w["is_root"]]
    if roots and all(w["status"] not in OPEN for w in roots):
        # ⟨1.17⟩ §35.1 the works are done: the session is `ready` and waits for the owner; no
        # timer nudges anyone
        return []
    if (
        turn
        and not turn.get("reminded_at")
        and (now - datetime.fromisoformat(str(turn["at"])) >= timedelta(hours=s.order_owner_hours))
    ):
        # ⟨1.17⟩ §35.4 an open turn reminds the owner once after order_owner_hours
        await _remind_turn(tx, rep, order, turn, s.order_owner_hours)
        fired.append("turn")
    if (
        rep["ack"] is None
        and rep["ack_nudged_at"] is None
        and not turn  # ⟨1.17⟩ the holder asked and waits: no «where is your plan» nudge
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
    if turn:
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
        runs = await idle_runs(tx, rep, works, created)
        limit = await talk_limit(tx, rep, s.order_talk_limit)
        if runs > limit:
            await stop_talk(tx, rep, works, runs)
            fired.append("talk_loop")
    return fired


# ⟨2026-11-08⟩ audit B3: the runs that count as «talk without output». A run that produced
# anything — a deliverable, an `order.progress`/`order.ack`, a child work, a hand-over — is work;
# a wake the hub itself queued (the idle sweep, the owner's reply, a child's delivery, failure or
# decline, a hire that joined, «ادامه بده», a lifted cap, the pace, a reopen) is never counted; the
# count starts again at the last step of the story (any progress).
WAKE_REASONS = (
    "session_idle:%", "owner_reply:%", "child_delivered:%", "child_failed:%", "child_cancelled:%",
    "joined:%", "nudge:%", "uncapped:%", "resume:%", "pace:%", "session_reopened:%",
    "owner_turn_over:%",
)  # fmt: skip
PRODUCTIVE_TOOLS = (
    "order.progress", "order.ack", "deliver", "work.delegate", "work.request", "work.split",
    "order.ask", "propose", "hire.decide",
)  # fmt: skip
TALK_LIMIT_PER_TASK = 3


async def idle_runs(
    tx: Tx, rep: dict[str, Any], works: list[dict[str, Any]], created: datetime
) -> int:
    """How many runs of the order's works produced nothing at all since the last complete
    deliverable and the last step of the story."""
    n = await tx.scalar(
        """SELECT count(*) FROM agents.runs r
           WHERE r.work_id = ANY(:ids) AND r.state IN ('running', 'done', 'failed')
             AND r.trigger NOT IN ('talk', 'direct')
             -- ⟨1.32⟩ §54 a run handed over to a direct turn did its work there
             AND COALESCE(r.note, '') NOT LIKE 'direct turn%'
             AND r.created_at > COALESCE(
                 (SELECT max(d.created_at) FROM cartable.deliverables d
                   WHERE d.work_id = ANY(:ids) AND NOT starts_with(d.title, :partial)),
                 :since)
             AND r.created_at > COALESCE(CAST(:last AS timestamptz), :since)
             AND NOT (r.reason LIKE ANY(CAST(:wakes AS text[])))
             AND NOT EXISTS (
                 SELECT 1 FROM agents.steps s CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
                 WHERE s.run_id = r.id AND a ->> 'outcome' = 'ok'
                   AND a ->> 'tool' = ANY(CAST(:tools AS text[])))
             AND NOT EXISTS (
                 SELECT 1 FROM work.work c
                 WHERE (c.parent_id = r.work_id OR c.requested_by_work_id = r.work_id)
                   AND c.created_at >= r.created_at
                   AND c.created_at <= COALESCE(r.finished_at, now()))""",
        ids=[w["id"] for w in works],
        partial=W.PARTIAL_PREFIX,
        since=created,
        last=rep.get("last_step_at"),
        wakes=list(WAKE_REASONS),
        tools=list(PRODUCTIVE_TOOLS),
    )
    return int(n or 0)


async def talk_limit(tx: Tx, rep: dict[str, Any], base: int) -> int:
    """The limit: the setting, and never below TALK_LIMIT_PER_TASK runs per plan task."""
    tasks = await tx.scalar(
        """SELECT count(*) FROM owner.session_tasks WHERE order_id = :o AND state <> 'dropped'""",
        o=rep["order_id"],
    )
    return max(int(base), TALK_LIMIT_PER_TASK * int(tasks or 0))


async def _remind_turn(
    tx: Tx, rep: dict[str, Any], order: dict[str, Any], turn: dict[str, Any], hours: int
) -> None:
    holding = await _holding(tx)
    text = " ".join((order.get("text") or "").split())[:80]
    await notify.raise_notification(
        tx,
        company_id=holding["id"],
        company_code=holding["code"],
        level="decision",
        title_fa=f"هنوز منتظر جواب شماست: {text}"[:300],
        body_fa=HZ.plain(
            f"{turn.get('who_fa') or 'مسئول'} {hours} ساعت پیش پرسید: {turn.get('question_fa') or ''}",
            "تا جواب ندهید این فرمان جلو نمیرود",
            "در جلسه‌ی فرمان جواب بدهید",
        )[:4000],
        link_kind="conversation" if rep.get("conversation_ref") else "order",
        link_ref=rep.get("conversation_ref") or rep["ref"],
        source_kind="service",
        source_code="orders",
        domain="business",
        owner_action=True,
    )
    await tx.exec(
        """UPDATE owner.order_reports
           SET turn = turn || jsonb_build_object('reminded_at', to_jsonb(now())), updated_at = now()
           WHERE id = :id""",
        id=rep["id"],
    )


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
    from hq_api.domain import session_activity as SA

    for ref in refs:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            fired = await timers(tx, hub.settings, ref)
            # ⟨1.23⟩ §41.3 never a silent stall: idle → the holder woken once; still idle → stuck
            try:
                async with tx.conn.begin_nested():
                    fired += await SA.sweep(tx, ref, minutes=hub.settings.session_idle_minutes)
            except Exception:  # one session's sweep never stops the tick
                log.exception("session sweep failed", extra={"order": ref})
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


# ⟨2026-11-09⟩ «با من» (the owner: «دکمه با من رو زدم و شروع کرده برای خودش کار رو جلو بردن»): while
# a step-by-step order waits for the owner's answer, nothing of it runs — not its holder, not a
# colleague it handed a part to. A run the owner's own word started is never held.
OWNER_WORD_REASONS = ("owner_reply:", "nudge:", "pace:", "owner_turn_over:", "session_reopened:")
OWNER_TURN_REASON = "owner_turn_over:"


async def owner_turn(tx: Tx, work_id: UUID | None) -> dict[str, Any] | None:
    """`{askers: {codes}, since: datetime}` (the latest ask) when the work's order is step by step
    («با من») and waits for the owner's answer (`turn` set, the session not ended); else None."""
    if work_id is None:
        return None
    ref = await order_of_work(tx, work_id)
    if ref is None:
        return None
    row = await tx.first(
        """SELECT r.turn FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
           WHERE r.ref = :r AND r.turn IS NOT NULL AND r.ended_at IS NULL AND o.pace = 'step'""",
        r=ref,
    )
    if row is None:
        return None
    turn = _j(row["turn"]) or {}
    asks = [a for a in turn.get("asks") or [turn] if isinstance(a, dict)]
    since = None
    for a in asks:
        with contextlib.suppress(TypeError, ValueError):
            at = datetime.fromisoformat(str(a.get("at")))
            since = at if since is None or at > since else since
    return {
        "askers": {
            str((a.get("by") or {}).get("code")) for a in asks if (a.get("by") or {}).get("code")
        },
        "since": since,
    }


def answers_owner(run: dict[str, Any], waiting: dict[str, Any]) -> bool:
    """Whether the run carries the owner's word on what the order waits for: his own word started
    it (`OWNER_WORD_REASONS`) and it was queued after the question. A word he said before the
    question was asked («ادامه بده» a moment before a colleague asked) does not answer it."""
    if not str(run.get("reason") or "").startswith(OWNER_WORD_REASONS):
        return False
    since, queued = waiting.get("since"), run.get("queued_at")
    return since is None or queued is None or queued >= since


async def held_for_owner(tx: Tx, run: dict[str, Any]) -> bool:
    """Whether a work run waits for the owner's answer (claim): a `work` run of a step-by-step
    order that waits for the owner, unless the owner's own word on that question started it."""
    if run.get("trigger") != "work" or run.get("work_id") is None:
        return False
    waiting = await owner_turn(tx, run["work_id"])
    return waiting is not None and not answers_owner(run, waiting)


async def resume_held(tx: Tx, ref: str) -> list[str]:
    """The order's open works whose last run was held for the owner's answer run again (the
    owner answered, said «ادامه بده», or made the order «خودکار»). Answers the refs woken."""
    rows = await tx.all(
        """SELECT DISTINCT ON (w.id) w.id, w.ref, r.state, r.error_code
           FROM work.work w JOIN agents.runs r ON r.work_id = w.id
           WHERE w.ref = ANY(CAST(:refs AS text[])) AND w.status IN ('queued', 'in_progress', 'waiting')
             AND r.trigger = 'work'
           ORDER BY w.id, r.queued_at DESC""",
        refs=[str(w["ref"]) for w in await tree(tx, root_refs(await load_order(tx, ref) or {}))],
    )
    woken: list[str] = []
    for r in rows:
        if r["state"] != "refused" or r["error_code"] != "owner_turn":
            continue
        if await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=r["id"], r=f"{OWNER_TURN_REASON}{ref}"
        ):
            woken.append(str(r["ref"]))
    return woken


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
