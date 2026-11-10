"""The session shows its work live and never stalls (contract §41, v1.23; the owner, 2026-11-08,
on his Pro-Chart reels session F-0011: «جاهایی که کار انجام دادن و ول کردند رفتند نه استریم زنده
ای … مثل خودت که کلود کدی از کار کردنت آدم میفهمه کار میکنی»).

    activity        §41.1 `GET /orders/{ref}/activity`: who is working now (the queued and running
                    runs of the order's works), the last 30 lines (a run started, each of its steps,
                    how it ended) in plain Persian, and — when nobody works — since when, what the
                    owner is asked, or why it is stuck. The lines come from agents.runs and
                    agents.steps of the order's tree, by code.
    text_fa         the step's own summary humanized (§29.7); when that is empty or still carries a
                    ref, a tool key, a code or raw English, the tools it used in words (TOOLS_FA):
                    «سایت pro-chart را خواند»، «از ChatGPT پرسید»، «صدا ساخت»، «خروجی تحویل داد».
    stream          `session.activity {order, line, working}` on every run start, step and end of
                    a work of an order with a session (the runner calls `on_run`; a failure here
                    never fails a run).
    the pulse       §41.3 `live` (a run queued or running now: the badge `moving`), the story clock
                    (the last step), how long the session has been idle, the idle wake of this
                    period (a run with reason `session_idle:<ref>`), and `stuck_fa` once it is idle
                    for two thresholds: the cause in the owner's words (the last refused or failed
                    run, a blocker, an empty seat, a sign-in or key, else «نمیدانیم چرا»).
    the sweep       every few minutes (order_report.tick): idle for SESSION_IDLE_MINUTES and not
                    waiting on the owner → the holder is woken once with the plan's next task;
                    idle another threshold → `stuck`, a step and ONE owner notification with the
                    cause.
    nudge           §41.3 `POST /orders/{ref}/nudge`: «ادامه بده»; the holder is woken now.

Rule-based, no model. Nothing here is stored in a column of its own: the wake is the run it
queued, the notification its row, the step its line.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import humanize as HZ
from hq_api.domain import no_silence as NS
from hq_api.domain import notify
from hq_api.domain import order_report as OR

log = logging.getLogger("hq_api.session_activity")

IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "10"))
LAST_LINES = 30
RUNS_READ = 60
TEXT_CHARS = 200
IDLE_REASON = "session_idle:{ref}"
NUDGE_REASON = "nudge:{ref}"
SYSTEM_FA = "سامانه"
OWNER_FA = "مدیر کل"
WOKEN_FA = "مسئول دوباره سر کار آمد: ادامه از کار {n}"
WOKEN_NO_TASK_FA = "مسئول دوباره سر کار آمد"
NOT_WOKEN_FA = "مسئول بیدار نشد: {why}"
NUDGED_FA = "مدیر کل گفت ادامه بده"
STUCK_FA = "گیر کرد: {why}"
STUCK_TITLE_FA = "فرمان شما گیر کرده است: {text}"
UNKNOWN_WHY_FA = "نمیدانیم چرا؛ «ادامه بده» را بزنید."
PLAYER_FA = {
    "gpt": "ChatGPT",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "aistudio": "Google AI Studio",
}
DONE_FA = "این دور کارش را تمام کرد"
STARTED_FA = "شروع کرد: {title}"
# ⟨2026-11-09⟩ the owner: every run read «شروع کرد: <the session's title>», even the one his own word
# woke, and he could not tell whether he was heard. A run says why it started (agents.runs.reason, the
# wake's reason); the first run of a work, or one woken for no named reason, still says what it began.
START_WHY_FA: tuple[tuple[str, str], ...] = (
    ("owner_reply:", "حرف شما را گرفت و دارد فکر میکند"),
    ("nudge:", "گفتید ادامه بده؛ دارد فکر میکند"),
    ("pace:step:", "روش کار «با من» شد؛ دارد فکر میکند"),
    ("pace:auto:", "روش کار «خودکار» شد؛ دارد فکر میکند"),
    ("child_", "بخشی از کار رسید؛ دارد فکر میکند"),
    ("joined:", "همکار تازه به جلسه آمد؛ دارد فکر میکند"),
    ("session_reopened:", "جلسه دوباره باز شد؛ دارد فکر میکند"),
    ("session_idle:", "دوباره سر کار آمد"),
    ("uncapped:", "سقف مصرف برداشته شد؛ ادامه میدهد"),
    # ⟨2026-11-09⟩ §43 the workshop
    ("workshop_done:", "کارگاه کارش را تحویل داد؛ نگاهش میکند"),
    ("owner_turn_over:", "شما جواب دادید؛ کارش را ادامه میدهد"),
    ("workspace_failed:", "کار کارگاه به نتیجه نرسید؛ دلیلش را میگوید"),
)
STOPPED_FA = "کار متوقف شد: {why}"
GENERIC_FA = "کار کرد"
# How a run ended, in the owner's words (no_silence.RUN_WHY_FA has the refusals of a claim; these
# are the ends of a run that started).
END_WHY_FA: dict[str, str] = {
    "limit_reached": "سقف قدم‌های این دور رسید.",
    "budget": "سقف مصرف این دور رسید.",
    "invalid_output": "مدل جواب درستی نداد.",
    "model_error": "مدل جواب نداد.",
    "quota_throttled": "سهمیه‌ی مدل پر بود.",
    "company_locked": "کلید توقف شرکت روشن بود.",
    "no_reply": "جوابی نوشته نشد.",
    "player_call": "کار را به بازیکن بیرونی داد.",
    # ⟨2026-11-09⟩ «با من»: the session waits for the owner's answer
    "owner_turn": "منتظر جواب شما ماند؛ با جواب شما ادامه میدهد.",
}
SKIP_END = ("work_closed", "meeting_gone")
# (with a hint, without one): the tools of a step in words; «…» never a tool key, a ref or a code.
TOOLS_FA: dict[str, tuple[str, str]] = {
    "web.read": ("سایت {x} را خواند", "یک سایت را خواند"),
    "web.browse": ("سایت {x} را خواند", "یک سایت را خواند"),
    "http.request": ("از سایت {x} داده گرفت", "از یک سایت داده گرفت"),
    "web.search": ("در وب جست‌وجو کرد", "در وب جست‌وجو کرد"),
    "substitute.call": ("از {x} پرسید", "از بازیکن بیرونی پرسید"),
    "speech.make": ("صدا ساخت", "صدا ساخت"),
    "media.item": ("ویدیو ساخت", "ویدیو ساخت"),
    "media.render": ("ویدیو ساخت", "ویدیو ساخت"),
    "deliver": ("خروجی تحویل داد", "خروجی تحویل داد"),
    "order.ack": ("برنامه‌اش را ثبت کرد", "برنامه‌اش را ثبت کرد"),
    "order.progress": ("یک قدم را گزارش داد", "یک قدم را گزارش داد"),
    "order.ask": ("از شما پرسید", "از شما پرسید"),
    "work.delegate": ("کار را به {x} سپرد", "کار را به یکی از همکاران سپرد"),
    "work.request": ("کار را به {x} سپرد", "کار را به شرکت دیگری سپرد"),
    "work.split": ("کار را چند بخش کرد", "کار را چند بخش کرد"),
    "work.accept": ("کار را گرفت", "کار را گرفت"),
    "work.progress": ("پیشرفت کار را ثبت کرد", "پیشرفت کار را ثبت کرد"),
    "hire.decide": ("درباره‌ی استخدام تصمیم گرفت", "درباره‌ی استخدام تصمیم گرفت"),
    "propose": ("پیشنهادی برای شما نوشت", "پیشنهادی برای شما نوشت"),
    "files.read": ("فایل را خواند", "فایل را خواند"),
    "linked.read": ("داده‌ی شرکت {x} را خواند", "داده‌ی شرکت دیگری را خواند"),
    "connection.read": ("اتصال‌های شرکت را دید", "اتصال‌های شرکت را دید"),
    "connection.set": ("اتصال شرکت را ثبت کرد", "اتصال شرکت را ثبت کرد"),
    "company.state": ("وضعیت شرکت را دید", "وضعیت شرکت را دید"),
    "knowledge.search": ("در دانش هلدینگ گشت", "در دانش هلدینگ گشت"),
    "memory.write": ("یادداشتی برای خودش نوشت", "یادداشتی برای خودش نوشت"),
    "memory.read": ("یادداشت‌هایش را خواند", "یادداشت‌هایش را خواند"),
    "work.get": ("کار را خواند", "کار را خواند"),
    "server.map": ("سرور {x} را نگاه کرد", "سرور را نگاه کرد"),
    "server.read": ("فایلی از سرور خواند", "فایلی از سرور خواند"),
    "server.exec": ("روی سرور دستوری اجرا کرد", "روی سرور دستوری اجرا کرد"),
    "server.write": ("فایلی روی سرور نوشت", "فایلی روی سرور نوشت"),
    "server.claude": ("کار را به کلود سرور داد", "کار را به کلود سرور داد"),
    "workshop.run": ("کار را به کارگاه داد تا بسازد", "کار را به کارگاه داد تا بسازد"),
    "workshop.stop": ("کار کارگاه را متوقف کرد", "کار کارگاه را متوقف کرد"),
    "automation.propose": ("خودکارسازی پیشنهاد داد", "خودکارسازی پیشنهاد داد"),
    "message.owner": ("برای شما پیام نوشت", "برای شما پیام نوشت"),
    "message.thread": ("پیامی نوشت", "پیامی نوشت"),
    "inquiry.ask": ("از همکاری پرسید", "از همکاری پرسید"),
    "inquiry.answer": ("به پرسشی جواب داد", "به پرسشی جواب داد"),
    "mcp.call": ("از یک ابزار بیرونی داده گرفت", "از یک ابزار بیرونی داده گرفت"),
}
SILENT_TOOLS = ("activity.set",)
_EMP_CODE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(?:-[A-Z0-9]+)?$")
_CO_CODE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


# ------------------------------------------------------------------ shapes --
LineKind = Literal["start", "step", "end", "wake", "ask", "join", "task", "memory"]
LineState = Literal["running", "done", "failed"]


class ActivityLine(BaseModel):
    """§41.1, and ⟨1.24⟩ §42.2 additive: `id` (`<run>:<n>`, 0 the start, `<run>:end` the end;
    `task:<ref>:<n>`, `join:<code>`), `company` (the actor's), `kind`, `state`, `task_n`."""

    id: str
    at: datetime
    who_fa: str
    company: str | None = None
    text_fa: str
    kind: LineKind = "step"
    state: LineState = "done"
    task_n: int | None = None


class Worker(BaseModel):
    who_fa: str
    company_fa: str
    work_title_fa: str
    started_at: datetime
    step: int
    doing_fa: str


class SessionActivity(BaseModel):
    working: list[Worker] = Field(default_factory=list)
    last: list[ActivityLine] = Field(default_factory=list)
    idle_since: datetime | None = None
    waiting_fa: str | None = None
    stuck_fa: str | None = None


# ------------------------------------------------------------- the words --
def hint_of(tool: str, args: Any) -> str | None:
    """What of a tool's arguments the owner may read beside the verb (the runner stores it with
    the step's actions): a site's name, a player's name, a company or an employee code (resolved
    to a title when shown). Never the text, a path or a command."""
    if not isinstance(args, dict):
        return None
    if tool in ("web.read", "web.browse", "http.request"):
        host = urlsplit(str(args.get("url") or "")).hostname or ""
        parts = [p for p in host.lower().split(".") if p and p != "www"]
        if len(parts) >= 2:
            return parts[-2][:40]
        return parts[0][:40] if parts else None
    if tool == "substitute.call":
        player = str(args.get("player") or "")
        return PLAYER_FA.get(player)
    if tool == "linked.read":
        co = str(args.get("company") or "")
        return co if _CO_CODE.match(co) else None
    if tool in ("work.delegate", "work.request"):
        to = str(args.get("to") or args.get("assignee") or args.get("company") or "")
        return to[:40] if to and (_EMP_CODE.match(to) or _CO_CODE.match(to)) else None
    if tool == "server.map":
        name = str(args.get("server") or "")
        return name[:40] if name and HZ.check(name) == [] else None
    return None


def _cut(text: str, limit: int = TEXT_CHARS) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    cut = one[: limit - 1]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip("،؛:,; ") + "…"


def plain(text: str | None) -> str | None:
    """The text as the owner may read it, or None when the rules cannot make it plain."""
    out = HZ.humanize(text)
    if not out or HZ.check(out):
        return None
    return _cut(out)


def tools_text(actions: list[Any], names: dict[str, str] | None = None) -> str:
    """The tools of a step in plain Persian verbs (at most three, each once); a refused or failed
    call says so."""
    names = names or {}
    phrases: list[str] = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        tool = str(a.get("tool") or "")
        if tool in SILENT_TOOLS:
            continue
        with_hint, bare = TOOLS_FA.get(tool, (GENERIC_FA, GENERIC_FA))
        hint = a.get("hint")
        hint = names.get(str(hint), str(hint)) if hint else None
        text = with_hint.format(x=hint) if hint and "{x}" in with_hint else bare
        if HZ.check(text):
            text = bare
        if a.get("outcome") not in (None, "ok"):
            text += " (نشد)"
        if text not in phrases:
            phrases.append(text)
        if len(phrases) >= 3:
            break
    return "؛ ".join(phrases) if phrases else GENERIC_FA


def step_text(
    summary_fa: str | None, actions: list[dict[str, Any]], names: dict[str, str] | None = None
) -> str:
    """§41.1 a step in the owner's words: its own summary when plain, else its tools."""
    return plain(summary_fa) or tools_text(actions, names)


def end_text(state: str, code: str | None, partial: bool = False) -> str | None:
    """How a run ended, as a line; None when nothing is worth a line."""
    if code in SKIP_END:
        return None
    if state == "done":
        if code in END_WHY_FA and code != "player_call":
            why = END_WHY_FA[code]
            return f"{why} خروجی ناقص داد." if partial else why
        if code == "player_call":
            return END_WHY_FA[code]
        return DONE_FA
    if code in END_WHY_FA:
        return STOPPED_FA.format(why=END_WHY_FA[code])
    why, _fix = NS.RUN_WHY_FA.get(code or "", NS.RUN_WHY_DEFAULT)
    return STOPPED_FA.format(why=why)


def title_text(title: str | None) -> str:
    return plain(title) or "کار"


def start_text(reason: str | None, title: str) -> str:
    """The first line of a run: why it started (START_WHY_FA), else what it began."""
    why = reason or ""
    for prefix, text in START_WHY_FA:
        if why.startswith(prefix):
            return text
    return STARTED_FA.format(title=title)


async def _names(tx: Tx, hints: set[str]) -> dict[str, str]:
    """Employee and company codes among the hints, as the owner names them."""
    out: dict[str, str] = {}
    emp = [h for h in hints if _EMP_CODE.match(h)]
    co = [h for h in hints if _CO_CODE.match(h)]
    if emp:
        rows = await tx.all(
            """SELECT e.code, e.title_fa, c.name_fa FROM core.employees e
               JOIN core.companies c ON c.id = e.company_id WHERE e.code = ANY(:c)""",
            c=emp,
        )
        for r in rows:
            out[r["code"]] = OR.who_fa(r["title_fa"], r["name_fa"])
    if co:
        rows = await tx.all("SELECT code, name_fa FROM core.companies WHERE code = ANY(:c)", c=co)
        for r in rows:
            out[r["code"]] = str(r["name_fa"] or r["code"])
    return out


# ---------------------------------------------------------------- reading --
RUNS_SQL = """
SELECT r.id, r.state, r.error_code, r.partial, r.queued_at, r.started_at, r.finished_at, r.steps,
       r.reason, w.ref AS work_ref, w.title AS work_title, e.title_fa, c.name_fa AS company_fa,
       c.code AS company
FROM agents.runs r JOIN work.work w ON w.id = r.work_id
JOIN core.employees e ON e.id = r.employee_id JOIN core.companies c ON c.id = w.company_id
WHERE r.work_id = ANY(:ids) AND r.trigger NOT IN ('talk', 'direct')
ORDER BY r.queued_at DESC LIMIT :lim
"""
STEPS_SQL = """
SELECT s.run_id, s.n, s.at, s.summary_fa, s.actions FROM agents.steps s
WHERE s.run_id = ANY(:runs) ORDER BY s.at, s.n
"""


async def _runs_and_steps(
    tx: Tx, work_ids: list[Any], limit: int = RUNS_READ
) -> tuple[list[dict[str, Any]], dict[Any, list[dict[str, Any]]]]:
    if not work_ids:
        return [], {}
    runs = [dict(r) for r in await tx.all(RUNS_SQL, ids=work_ids, lim=limit)]
    steps: dict[Any, list[dict[str, Any]]] = {r["id"]: [] for r in runs}
    if runs:
        for s in await tx.all(STEPS_SQL, runs=[r["id"] for r in runs]):
            row = dict(s)
            row["actions"] = OR._j(row.get("actions")) or []
            steps[row["run_id"]].append(row)
    return runs, steps


async def activity(
    tx: Tx, rep: dict[str, Any], works: list[dict[str, Any]], *, pulse: Pulse | None = None
) -> SessionActivity:
    """§41.1 the session's live activity (the report refreshed by the caller)."""
    ids = [w["id"] for w in works]
    runs, steps = await _runs_and_steps(tx, ids)
    hints: set[str] = set()
    for rows in steps.values():
        for s in rows:
            for a in s["actions"]:
                if isinstance(a, dict) and a.get("hint"):
                    hints.add(str(a["hint"]))
    names = await _names(tx, hints) if hints else {}
    lines: list[ActivityLine] = []
    working: list[Worker] = []
    for r in runs:
        who = OR.who_fa(r["title_fa"], r["company_fa"])
        title = title_text(r["work_title"])
        own = steps.get(r["id"]) or []
        live = r["state"] in ("queued", "running")
        final: LineState = "running" if live else ("done" if r["state"] == "done" else "failed")
        rid = str(r["id"])
        if r["started_at"] is not None:
            lines.append(
                ActivityLine(
                    id=line_id(rid, 0),
                    at=r["started_at"],
                    who_fa=who,
                    company=r["company"],
                    text_fa=start_text(r.get("reason"), title),
                    kind="start",
                    state="running" if live else final,
                )
            )
        for s in own:
            lines.append(
                ActivityLine(
                    id=line_id(rid, int(s["n"])),
                    at=s["at"],
                    who_fa=who,
                    company=r["company"],
                    text_fa=step_text(s["summary_fa"], s["actions"], names),
                    kind="step",
                    state="running" if live else final,
                )
            )
        if live:
            if own:
                doing = step_text(own[-1]["summary_fa"], own[-1]["actions"], names)
            else:
                doing = (
                    "در صف اجرا"
                    if r["state"] == "queued"
                    else start_text(r.get("reason"), "").removesuffix(": ")
                )
            working.append(
                Worker(
                    who_fa=who,
                    company_fa=str(r["company_fa"] or ""),
                    work_title_fa=title,
                    started_at=r["started_at"] or r["queued_at"],
                    step=int(r["steps"] or 0),
                    doing_fa=doing,
                )
            )
        elif r["finished_at"] is not None:
            end = end_text(str(r["state"]), r["error_code"], bool(r.get("partial")))
            if end:
                lines.append(
                    ActivityLine(
                        id=end_id(rid),
                        at=r["finished_at"],
                        who_fa=who,
                        company=r["company"],
                        text_fa=end,
                        kind="end",
                        state=final,
                    )
                )
    for t in await live_turns(tx, ids):  # ⟨2026-11-10⟩ the workshop's turn is someone working
        # ⟨1.32⟩ §54 a direct turn is the session's own holder at work, by its own name
        direct = bool(t.get("direct")) and bool(t.get("holder_fa"))
        if direct:
            who = str(t["holder_fa"])
            doing = DIRECT_DOING_FA if t["state"] == "running" else DIRECT_QUEUED_FA
        else:
            who = WORKSHOP_WHO_FA if t["hands"] else SERVER_WHO_FA
            doing = TURN_DOING_FA if t["state"] == "running" else TURN_QUEUED_FA
        working.append(
            Worker(
                who_fa=who,
                company_fa=str(t["company_fa"] or ""),
                work_title_fa=title_text(t["work_title"]),
                started_at=t["started_at"] or t["created_at"],
                step=int(t["turns"] or 0),
                doing_fa=doing,
            )
        )
    lines.sort(key=lambda x: x.at)
    merged: dict[str, ActivityLine] = {}
    for ln in lines:  # the later line of an id wins
        merged.pop(ln.id, None)
        merged[ln.id] = ln
    last = list(merged.values())[-LAST_LINES:]
    working.sort(key=lambda w: w.started_at)
    pulse = pulse or await read_pulse(tx, rep, works)
    turn = OR._j(rep.get("turn")) or {}
    waiting = None
    if turn:
        who = turn.get("who_fa") or "مسئول"
        waiting = _cut(HZ.humanize(f"{who} میپرسد: {turn.get('question_fa') or ''}"), 300)
    idle_since = None
    if not working:
        idle_since = max([pulse.clock, *[x.at for x in lines]]) if lines else pulse.clock
    return SessionActivity(
        working=working,
        last=last,
        idle_since=idle_since,
        waiting_fa=waiting,
        stuck_fa=pulse.stuck_fa if not working else None,
    )


# ---------------------------------------------------------------- the pulse --
@dataclass
class Pulse:
    live: bool  # a run queued or running now (the badge `moving`)
    clock: datetime  # the story clock: the last step, the plan, the receipt
    idle: timedelta  # how long since the clock, when not live
    woken: dict[str, Any] | None  # the idle wake of this period (reason session_idle:<ref>)
    stuck_fa: str | None  # idle past two thresholds: the cause in the owner's words
    doing_fa: str | None = None  # the live run's last line

    @property
    def threshold(self) -> timedelta:
        return timedelta(minutes=IDLE_MINUTES)


def clock_of(rep: dict[str, Any]) -> datetime:
    """The story clock: the last step (it moves on every step, output, plan and owner's word), else
    the plan, else the receipt."""
    for c in (rep.get("last_step_at"), rep.get("acked_at"), rep.get("created_at")):
        if isinstance(c, datetime):
            return c
    return datetime.now(UTC)


async def live_run(tx: Tx, work_ids: list[Any]) -> dict[str, Any] | None:
    if not work_ids:
        return None
    row = await tx.first(
        """SELECT r.id, r.state, r.steps, r.employee_id FROM agents.runs r
           WHERE r.work_id = ANY(:ids) AND r.state IN ('queued', 'running') AND r.trigger NOT IN ('talk', 'direct')
           ORDER BY (r.state = 'running') DESC, r.queued_at LIMIT 1""",
        ids=work_ids,
    )
    return dict(row) if row is not None else None


TURN_OPEN = ("queued", "running", "awaiting_seal")  # infra.server_jobs: a turn not ended
WORKSHOP_WHO_FA = "کارگاه هلدینگ"
SERVER_WHO_FA = "Claude روی سرور شرکت"
TURN_DOING_FA = "دارد میسازد؛ هر نوبت تا ۶۰ دقیقه"
TURN_QUEUED_FA = "در صف کارگاه"
DIRECT_DOING_FA = "دارد روی فرمان شما کار میکند؛ هر نوبت تا ۶۰ دقیقه"
DIRECT_QUEUED_FA = "همین حالا شروع میکند"


async def live_turns(tx: Tx, work_ids: list[Any]) -> list[dict[str, Any]]:
    """⟨2026-11-10⟩ The workshop (or company-server) turns of these works that still run. A turn
    is live work although no agent run is: the holder's run ended when it handed the task over,
    and the turn may take an hour. Without this the session read as idle, the holder was woken
    after ten minutes and the owner was told «گیر کرد» while the workshop was building."""
    if not work_ids:
        return []
    rows = await tx.all(
        """SELECT ws.work_id, ws.turns, j.state, j.created_at, j.started_at,
                  COALESCE(j.args ->> 'hands', '') = 'true' AS hands,
                  COALESCE(j.args ->> 'direct', '') = 'true' AS direct, e.title_fa AS holder_fa,
                  w.title AS work_title, c.name_fa AS company_fa, c.code AS company
           FROM work.workspaces ws JOIN infra.server_jobs j ON j.id = ws.last_job_id
           JOIN work.work w ON w.id = ws.work_id JOIN core.companies c ON c.id = w.company_id
           LEFT JOIN core.employees e ON e.code = j.actor_code AND j.actor_kind = 'agent'
           WHERE ws.work_id = ANY(:ids) AND j.state = ANY(:open)
           ORDER BY j.created_at""",
        ids=work_ids,
        open=list(TURN_OPEN),
    )
    return [dict(r) for r in rows]


async def read_pulse(
    tx: Tx, rep: dict[str, Any], works: list[dict[str, Any]], *, minutes: int | None = None
) -> Pulse:
    """§41.3 where the session stands: live, idle (since the clock), woken this period, stuck."""
    ids = [w["id"] for w in works]
    now = datetime.now(UTC)
    clock = clock_of(rep)
    live = await live_run(tx, ids)
    doing = None
    if live is not None:
        last = await tx.first(
            "SELECT summary_fa, actions FROM agents.steps WHERE run_id = :r ORDER BY n DESC LIMIT 1",
            r=live["id"],
        )
        if last is not None:
            doing = step_text(last["summary_fa"], OR._j(last["actions"]) or [])
    turns = await live_turns(tx, ids) if live is None else []
    if turns:
        doing = TURN_DOING_FA if turns[0]["state"] == "running" else TURN_QUEUED_FA
    woken = None
    if ids:
        row = await tx.first(
            """SELECT id, state, error_code, queued_at, finished_at FROM agents.runs
               WHERE work_id = ANY(:ids) AND reason = :r AND queued_at > :clock
               ORDER BY queued_at DESC LIMIT 1""",
            ids=ids,
            r=IDLE_REASON.format(ref=rep["ref"]),
            clock=clock,
        )
        woken = dict(row) if row is not None else None
    idle = max(now - clock, timedelta(0))
    T = timedelta(minutes=IDLE_MINUTES if minutes is None else minutes)
    stuck = None
    open_roots = [w for w in works if w["is_root"] and w["status"] in OR.OPEN]
    if (
        live is None
        and not turns
        and open_roots
        and rep.get("ended_at") is None
        and not OR._j(rep.get("turn"))
        and idle >= 2 * T
    ):
        stuck = await stuck_cause(tx, rep, works, clock)
    return Pulse(live=live is not None or bool(turns), clock=clock, idle=idle, woken=woken,
                 stuck_fa=stuck, doing_fa=doing)  # fmt: skip


# ----------------------------------------------------------------- the cause --
async def stuck_cause(
    tx: Tx, rep: dict[str, Any], works: list[dict[str, Any]], clock: datetime
) -> str:
    """Why the session does not move, in the owner's words, with what fixes it: the last refused or
    failed run, a blocker of the report, a sign-in or key a step needed, an empty seat of the
    company's working group; else «نمیدانیم چرا»."""
    ids = [w["id"] for w in works]
    last = await tx.first(
        # ⟨2026-11-10⟩ only what ended since the session last moved (an old refusal the order got
        # past is not why it stands now), and never the hold for the owner's own answer
        """SELECT state, error_code, note FROM agents.runs
           WHERE work_id = ANY(:ids) AND state IN ('refused', 'failed') AND trigger NOT IN ('talk', 'direct')
             AND error_code IS NOT NULL AND error_code <> 'owner_turn'
             AND COALESCE(finished_at, queued_at) >= CAST(:since AS timestamptz) - interval '10 minutes'
           ORDER BY COALESCE(finished_at, queued_at) DESC LIMIT 1""",
        ids=ids,
        since=clock,
    )
    if last is not None and last["error_code"] not in SKIP_END:
        code = str(last["error_code"])
        if code in NS.RUN_WHY_FA:
            why, fix = NS.RUN_WHY_FA[code]
            return f"{why} {fix}"
        if code in END_WHY_FA:
            return f"{END_WHY_FA[code]} «ادامه بده» را بزنید."
    for b in OR._j(rep.get("blockers")) or []:
        if not isinstance(b, dict):
            continue
        label = (b.get("fix") or {}).get("label_fa")
        head = str(b.get("title_fa") or "")
        return f"{head}؛ {label}" if label else head or UNKNOWN_WHY_FA
    bad = await tx.all(
        """SELECT a ->> 'tool' AS tool, a ->> 'code' AS code FROM agents.runs r
           JOIN agents.steps s ON s.run_id = r.id
           CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
           WHERE r.work_id = ANY(:ids) AND s.at >= CAST(:since AS timestamptz) - interval '1 day'
             AND a ->> 'outcome' IS DISTINCT FROM 'ok' AND a ->> 'code' IS NOT NULL
           ORDER BY s.at DESC LIMIT 20""",
        ids=ids,
        since=clock,
    )
    for a in bad:
        tool, code = str(a["tool"] or ""), str(a["code"] or "")
        if tool == "speech.make":
            # ⟨2026-11-10⟩ the narrator of content is on (what the owner switched off is his own
            # voice talk): AI Studio signed out is his one sign-in, said plainly
            if code in ("signed_out", "channel_not_configured", "expired"):
                return (
                    "گوینده (Google AI Studio) روی هاب وارد حسابش نیست؛ یک بار ورود لازم است "
                    "و بعد صدا ساخته میشود."
                )
            continue
        if code in OR.CONNECTION_CODES:
            # (2026-11-08) never «اینستاگرام وصل نیست» and never the owner's step
            return "یک اتصال فنی هنوز آماده نیست؛ تیم فنی هلدینگ خودش آن را تنظیم میکند."
        if code in ("signed_out", "not_ready", "unavailable", "expired", "limited"):
            return "بازیکن بیرونی وارد حسابش نیست؛ در صفحه‌ی بازیکن‌ها واردش کنید."
    seat = await tx.first(
        """SELECT g.title_fa AS group_fa, s ->> 'title_fa' AS seat_fa, s -> 'blocked' ->> 'why_fa' AS why
           FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           CROSS JOIN LATERAL jsonb_array_elements(m.seats) s
           WHERE m.company_id = ANY(:cos) AND s -> 'blocked' IS NOT NULL
             AND jsonb_typeof(s -> 'blocked') = 'object'
           ORDER BY m.updated_at DESC LIMIT 1""",
        cos=list({w["company_id"] for w in works}),
    )
    if seat is not None:
        return (
            f"جایگاه «{seat['seat_fa'] or 'کارمند'}» در کارگروه «{seat['group_fa'] or ''}» خالی ماند: "
            f"{seat['why'] or ''}"
        ).strip()
    return UNKNOWN_WHY_FA


# ------------------------------------------------------------------ the stream --
def line_id(run_id: str, n: int) -> str:
    """§42.2 a run's line: its id and the step number (0 the start)."""
    return f"{run_id}:{n}"


def end_id(run_id: str) -> str:
    """§42.2 the run's end: a line of its own, so no step's text is lost."""
    return f"{run_id}:end"


def make_line(
    id_: str,
    who_fa: str,
    text_fa: str,
    *,
    kind: str,
    state: str,
    company: str | None = None,
    task_n: int | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": id_,
        "at": (at or datetime.now(UTC)).isoformat(),
        "who_fa": who_fa,
        "company": company,
        "text_fa": text_fa,
        "kind": kind,
        "state": state,
        "task_n": task_n,
    }


async def working_count(tx: Tx, ref: str) -> int:
    n = await tx.scalar(
        """WITH ws AS (SELECT w.id FROM work.work w JOIN owner.order_reports o ON o.ref = :r
                       WHERE w.ref = ANY(o.work_refs))
           SELECT (SELECT count(*) FROM agents.runs r
                   WHERE r.state IN ('queued', 'running') AND r.trigger NOT IN ('talk', 'direct')
                     AND r.work_id IN (SELECT id FROM ws))
                + (SELECT count(*) FROM work.workspaces t
                   JOIN infra.server_jobs j ON j.id = t.last_job_id
                   WHERE t.work_id IN (SELECT id FROM ws) AND j.state = ANY(:open))""",
        r=ref,
        open=list(TURN_OPEN),
    )  # ⟨2026-11-10⟩ a workshop turn that still runs counts as someone working
    return int(n or 0)


async def emit(tx: Tx, order: str, line: dict[str, Any], working: int | None = None) -> None:
    """`session.activity {order, working, line}` on the holding's stream (topic `orders`)."""
    holding = await OR._holding(tx)
    if working is None:
        working = await working_count(tx, order)
    await events.emit(tx, holding["code"], "session.activity", order,
                      {"order": order, "line": line, "working": working})  # fmt: skip


async def emit_safe(tx: Tx, order: str, line: dict[str, Any]) -> None:
    """A line that never fails its caller (a hire joining, a task ticked, an ask)."""
    try:
        async with tx.conn.begin_nested():
            await emit(tx, order, line)
    except Exception:  # noqa: BLE001 - the stream never fails the writer
        log.warning("session.activity could not be emitted", extra={"order": order})


async def on_run(
    tx: Tx,
    run: dict[str, Any],
    emp: dict[str, Any],
    kind: str,
    *,
    n: int | None = None,
    summary: str | None = None,
    actions: list[dict[str, Any]] | None = None,
    state: str | None = None,
    code: str | None = None,
    partial: bool = False,
) -> None:
    """The runner's run.started / run.step / run.finished, as one `session.activity` line on the
    holding's stream when the run's work belongs to an order with a session. Never fails a run:
    a savepoint of its own, a warning in the log."""
    work_id = run.get("work_id")
    if work_id is None or run.get("trigger") == "talk":
        return
    try:
        async with tx.conn.begin_nested():
            ref = await OR.order_of_work(tx, work_id)
            if ref is None:
                return
            rid = str(run.get("id"))
            if kind == "started":
                title = await tx.scalar("SELECT title FROM work.work WHERE id = :w", w=work_id)
                text: str | None = start_text(run.get("reason"), title_text(title))
                lid, lkind, lstate = line_id(rid, 0), "start", "running"
            elif kind == "step":
                text = step_text(summary, actions or [])
                lid, lkind, lstate = line_id(rid, int(n or 0)), "step", "running"
            else:
                text = end_text(state or "done", code, partial)
                lid, lkind = end_id(rid), "end"
                lstate = "done" if state == "done" else "failed"
            if text is None:
                return
            co = await tx.first(
                "SELECT code, name_fa FROM core.companies WHERE id = :c", c=run["company_id"]
            )
            who = OR.who_fa(emp.get("title_fa"), co["name_fa"] if co else None)
            line = make_line(lid, who, text, kind=lkind, state=lstate,
                             company=str(co["code"]) if co else None)  # fmt: skip
            await emit(tx, ref, line, await working_count(tx, ref))
    except Exception:  # noqa: BLE001 - the stream never fails a run
        log.warning("session.activity could not be emitted", extra={"run": str(run.get("id"))})


# ------------------------------------------------------------------- the wake --
async def next_task(tx: Tx, order_id: UUID) -> dict[str, Any] | None:
    """The plan's next open task (doing first, then the lowest todo)."""
    row = await tx.first(
        """SELECT n, title_fa, state FROM owner.session_tasks WHERE order_id = :o
             AND state IN ('doing', 'todo') ORDER BY (state = 'doing') DESC, n LIMIT 1""",
        o=order_id,
    )
    return dict(row) if row is not None else None


async def wake_holder(
    tx: Tx, ref: str, reason: str, *, step_fa: str | None = None, who_fa: str = SYSTEM_FA
) -> dict[str, Any]:
    """The holder's open root work runs again (work.wake_assignee, one queued run per work).
    Answers {run_id, work_ref, why_fa}; `step_fa` (with the next task's number as {n}) is written
    as a step when the wake took, else a step says why not. The clock does not move."""
    from hq_api.domain import order_turns as OT

    rep = await OR.ensure(tx, ref)
    if rep is None:
        return {"run_id": None, "work_ref": None, "why_fa": "این فرمان پیدا نشد"}
    h = await OT.holder(tx, ref)
    out: dict[str, Any] = {"run_id": None, "work_ref": None, "why_fa": None}
    if h is None or h.get("work_id") is None:
        out["why_fa"] = "کار مسئولی ندارد"
    elif h.get("work_status") not in OR.OPEN:
        out["why_fa"] = "کار مسئول بسته شده است"
    else:
        run_id = await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=h["work_id"], r=reason[:200]
        )
        out["work_ref"] = str(h["work_ref"])
        if run_id is not None:
            out["run_id"] = str(run_id)
            # §42.2 the wake as a line: the queued run's start updates it when it begins
            await emit_safe(tx, ref, make_line(
                line_id(str(run_id), 0), OR.who_fa(h["title_fa"], h["company_fa"]),
                WOKEN_NO_TASK_FA, kind="wake", state="running", company=str(h["company"]),
            ))  # fmt: skip
        else:
            lock = await tx.scalar("SELECT control.lock_state(:co)", co=await tx.scalar(
                "SELECT company_id FROM work.work WHERE id = :w", w=h["work_id"]))  # fmt: skip
            out["why_fa"] = (
                "شرکت قفل است و تا قفل باز نشود کار راه نمیافتد"
                if lock is not None
                else "کار راه نیفتاد؛ دوباره تلاش میشود"
            )
    if step_fa is not None:
        if out["run_id"] is not None:
            task = await next_task(tx, rep["order_id"])
            line = step_fa.format(n=task["n"]) if task and "{n}" in step_fa else step_fa
            if task is None and "{n}" in step_fa:
                line = WOKEN_NO_TASK_FA
        else:
            line = NOT_WOKEN_FA.format(why=out["why_fa"])
        await OR._append_steps(tx, rep["id"], [OR._step(who_fa, line)])
    return out


def _stepped_since(rep: dict[str, Any], clock: datetime, *prefixes: str) -> bool:
    """Whether a step with one of these openings was written after the clock (once per period)."""
    for s in OR._j(rep.get("steps")) or []:
        if not isinstance(s, dict):
            continue
        try:
            at = datetime.fromisoformat(str(s.get("at")))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        if at > clock and any(str(s.get("what_fa") or "").startswith(p) for p in prefixes):
            return True
    return False


async def _told_stuck(tx: Tx, rep: dict[str, Any], clock: datetime) -> bool:
    return bool(
        await tx.scalar(
            """SELECT 1 FROM notify.notifications
               WHERE link_kind = 'order' AND link_ref = :r AND source_code = 'sessions'
                 AND created_at > :since LIMIT 1""",
            r=rep["ref"],
            since=clock,
        )
    )


async def sweep(tx: Tx, ref: str, *, minutes: int | None = None) -> list[str]:
    """§41.3 the sweep of one session (order_report.tick, every few minutes): idle → the holder
    woken once («مسئول دوباره سر کار آمد: ادامه از کار N»); still idle a threshold later → `stuck`,
    a step and ONE owner notification naming the cause. What fired: idle_wake, stuck."""
    rep = await OR.ensure(tx, ref)
    if rep is None or rep.get("ended_at") is not None or rep.get("closed_at") is not None:
        return []
    if OR._j(rep.get("turn")):
        return []  # the owner's turn: nobody is woken, nothing is stuck
    order = await OR.load_order(tx, ref)
    if order is None:
        return []
    works = await OR.tree(tx, OR.root_refs(order))
    if not any(w["is_root"] and w["status"] in OR.OPEN for w in works):
        return []
    T = IDLE_MINUTES if minutes is None else minutes
    pulse = await read_pulse(tx, rep, works, minutes=T)
    if pulse.live:
        return []
    fired: list[str] = []
    threshold = timedelta(minutes=T)
    if (
        pulse.woken is None
        and pulse.idle >= threshold
        and not _stepped_since(rep, pulse.clock, "مسئول دوباره سر کار آمد", "مسئول بیدار نشد")
    ):
        await wake_holder(tx, ref, IDLE_REASON.format(ref=ref), step_fa=WOKEN_FA)
        fired.append("idle_wake")
        rep = await OR.ensure(tx, ref) or rep
    if pulse.stuck_fa and not await _told_stuck(tx, rep, pulse.clock):
        if not _stepped_since(rep, pulse.clock, "گیر کرد"):
            await OR._append_steps(
                tx, rep["id"], [OR._step(SYSTEM_FA, STUCK_FA.format(why=pulse.stuck_fa))]
            )
        holding = await OR._holding(tx)
        text = " ".join((order.get("text") or "").split())[:80]
        await notify.raise_notification(
            tx,
            company_id=holding["id"],
            company_code=holding["code"],
            level="decision",
            title_fa=STUCK_TITLE_FA.format(text=HZ.humanize(text) or text)[:300],
            body_fa=HZ.plain(
                f"از {int(pulse.idle.total_seconds() // 60)} دقیقه پیش کسی روی این فرمان کار نمیکند",
                pulse.stuck_fa,
                "در جلسه‌ی فرمان «ادامه بده» را بزنید یا آنچه لازم است را درست کنید",
            )[:4000],
            link_kind="order",
            link_ref=ref,
            source_kind="service",
            source_code="sessions",
            domain="business",
            owner_action=True,
        )
        fired.append("stuck")
    if fired:
        await OR.refresh(tx, ref)
    return fired
