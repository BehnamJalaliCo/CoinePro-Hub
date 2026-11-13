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

⟨2026-11-11⟩ An open, unfinished session never goes silent (the owner's order session F-0011 read
«آرام» for twelve hours while a ChatGPT draft sat in a queue). Open = not closed and an open root
or an open plan task. An outside call (ChatGPT, Gemini, DeepSeek) or a voice job of the order's
works is someone working (a Worker of kind `call`) until its deadline; past it, it is not live
and the cause names it. The idle wake is an explicit turn (the brief says nothing runs and what
to do) and is capped: at most IDLE_WAKES_MAX since the owner's last word, and a woken run that
only narrated makes the session `stuck` at once, with one sentence and one notification.

Rule-based, no model. Nothing here is stored in a column of its own: the wake is the run it
queued, the notification its row, the step its line.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
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
from hq_api.domain import work as W

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
STUCK_TITLE_FA = "فرمان تو گیر کرده است: {text}"
UNKNOWN_WHY_FA = "نمیدانیم چرا؛ «ادامه بده» را بزن."
# ⟨2026-11-11⟩ the idle wake is capped: at most this many since the owner's last word, then stuck
IDLE_WAKES_MAX = 2
# what a woken run may do and still have done nothing (narration): reading and reporting
NARRATION_TOOLS = (
    "order.progress", "activity.set", "work.progress", "memory.write", "memory.read", "work.get",
    "message.owner", "message.thread", "knowledge.search", "files.read", "company.state",
    "connection.read",
)  # fmt: skip
STUCK_IDLE_FA = (
    "مسئول {k} بار دوباره سر کار آمد ولی کار جلو نرفت؛ آخرین کار: {last}؛ "
    "کار {n} («{title}») مانده است."
)
STUCK_PLAN_FA = "کسی روی این جلسه کار نمیکند؛ آخرین کار: {last}؛ کار {n} («{title}») مانده است."
LAST_WORDS = 120  # the end of the last step, as the apps show it (lastWordsFa)
_SENTENCE_END = re.compile(r"(?<=[.!؟?])\s+")
STUCK_CALL_FA = "{who} {seat} را آماده نکرد ({why}) و بعد از آن کار جلو نرفت."
READY_WAITING_FA = "منتظر تأیید تو"
REOPENED_FA = "کار مسئول دوباره باز شد: کار {n} از برنامه مانده است"
PLAN_DONE_FA = "همه‌ی کارهای برنامه انجام شد؛ خروجی آماده‌ی تأیید توست"
CLAUDE_WAIT_PREFIX = "هر دو اکانت Claude پر است"
CLAUDE_WAIT_FA = CLAUDE_WAIT_PREFIX + "؛ {when} شروع میکند"
CLAUDE_WAIT_SOON_FA = CLAUDE_WAIT_PREFIX + "؛ تا یکی جا باز کند شروع میکند"
# an outside call or a voice job working for the session (kind `call`)
CALL_DOING_FA = "{seat} را آماده میکند"
CALL_QUEUED_FA = "در صف {player}: {seat}"
# ⟨2026-11-11⟩ a call past its deadline the reaper has not ended yet (substitutes.pending_for's
# `ending`): still shown, as ending, for at most ENDING_GRACE (the reaper runs every minute); past
# that it is not live and the cause names it
CALL_ENDING_FA = "{player} جواب نداد؛ تمام میشود…"
ENDING_GRACE = timedelta(minutes=5)
VOICE_WHO_FA = "گوینده‌ی هوش مصنوعی"
VOICE_SEAT_FA = "صدا"
VOICE_DEADLINE = timedelta(minutes=12)  # the SpeechMake activity's 600 s and a margin
VOICE_WHY_FA: dict[str, str] = {
    "signed_out": "از حسابش بیرون افتاده بود",
    "channel_not_configured": "مرورگرش در دسترس نبود",
    "company_locked": "کارها قفل بود",
    "timeout": "جوابش طول کشید",
    "invalid_args": "متن درست نبود",
}
VOICE_WHY_DEFAULT_FA = "خطای داخلی"
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
    ("owner_reply:", "حرف تو را گرفت و دارد فکر میکند"),
    ("side_word:", "حرف تو را گرفت و دارد فکر میکند"),  # ⟨1.35⟩ §57.3 a side talk's word
    ("nudge:", "گفتی ادامه بده؛ دارد فکر میکند"),
    ("pace:step:", "روش کار «با من» شد؛ دارد فکر میکند"),
    ("pace:auto:", "روش کار «خودکار» شد؛ دارد فکر میکند"),
    ("child_", "بخشی از کار رسید؛ دارد فکر میکند"),
    ("joined:", "همکار تازه به جلسه آمد؛ دارد فکر میکند"),
    ("session_reopened:", "جلسه دوباره باز شد؛ دارد فکر میکند"),
    ("session_idle:", "دوباره سر کار آمد"),
    ("uncapped:", "سقف مصرف برداشته شد؛ ادامه میدهد"),
    # ⟨2026-11-09⟩ §43 the workshop
    ("workshop_done:", "کارگاه کارش را تحویل داد؛ نگاهش میکند"),
    ("owner_turn_over:", "تو جواب دادی؛ کارش را ادامه میدهد"),
    ("workspace_failed:", "کار کارگاه به نتیجه نرسید؛ دلیلش را میگوید"),
    # ⟨2026-11-11⟩ an outside call or a voice ended after the run that asked for it
    ("speech_done:", "صدای گوینده آماده شد؛ کارش را ادامه میدهد"),
    ("speech_failed:", "ساخت صدا به نتیجه نرسید؛ با بقیه‌ی کار ادامه میدهد"),
    ("creative_done:", "تصویر بازیکن بیرونی رسید؛ نگاهش میکند"),
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
    "company_locked": "کلید توقف شرکت روشن بود.",
    "no_reply": "جوابی نوشته نشد.",
    "player_call": "کار را به بازیکن بیرونی داد.",
    # ⟨2026-11-09⟩ «با من»: the session waits for the owner's answer
    "owner_turn": "منتظر جواب تو ماند؛ با جواب تو ادامه میدهد.",
}
# ⟨2026-11-11⟩ the quota codes are said by no_silence.quota_why_fa, with the reset time when the
# run carries it («اکانت‌های Claude پر است؛ از ساعت 03:30 دوباره کار میکند»)
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
    "order.ask": ("از تو پرسید", "از تو پرسید"),
    "work.delegate": ("کار را به {x} سپرد", "کار را به یکی از همکاران سپرد"),
    "work.request": ("کار را به {x} سپرد", "کار را به شرکت دیگری سپرد"),
    "work.split": ("کار را چند بخش کرد", "کار را چند بخش کرد"),
    "work.accept": ("کار را گرفت", "کار را گرفت"),
    "work.progress": ("پیشرفت کار را ثبت کرد", "پیشرفت کار را ثبت کرد"),
    "hire.decide": ("درباره‌ی استخدام تصمیم گرفت", "درباره‌ی استخدام تصمیم گرفت"),
    "propose": ("پیشنهادی برای تو نوشت", "پیشنهادی برای تو نوشت"),
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
    "message.owner": ("برای تو پیام نوشت", "برای تو پیام نوشت"),
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


WorkerKind = Literal["run", "workshop", "direct", "server", "call"]
Mood = Literal["thinking", "working", "waiting", "stuck", "idle"]
MOOD_FA: dict[str, str] = {
    "thinking": "فکر میکند",
    "working": "کار میکند",
    "waiting": "منتظر تو",
    "stuck": "گیر کرده",
    "idle": "آرام",
}


class Worker(BaseModel):
    """⟨1.33⟩ §55.1 additive: `kind` (an agent's run, the workshop's turn, the holder's own direct
    turn, a company server's turn), `cap_s` (a turn's time cap; the ring fills against it),
    `last_fa` and `last_at` (the last thing a live turn did, in the owner's words).
    ⟨2026-11-11⟩ additive kind `call`: an outside model (ChatGPT, Gemini, DeepSeek) or the AI
    narrator working for the session; `cap_s` is its deadline from `started_at`."""

    who_fa: str
    company_fa: str
    work_title_fa: str
    started_at: datetime
    step: int
    doing_fa: str
    kind: WorkerKind = "run"
    cap_s: int | None = None
    last_fa: str | None = None
    last_at: datetime | None = None


class SessionActivity(BaseModel):
    working: list[Worker] = Field(default_factory=list)
    last: list[ActivityLine] = Field(default_factory=list)
    idle_since: datetime | None = None
    waiting_fa: str | None = None
    stuck_fa: str | None = None
    # ⟨1.33⟩ §55.1 where the session stands, in one word (the «چراغ حال»)
    mood: Mood = "idle"
    mood_fa: str = MOOD_FA["idle"]


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


# an outcome that is not `ok` yet is no failure: the owner's card was raised and waits for him
# (an A3 proposal, or a destructive command of server.* / hub.ops waiting for his seal)
NOT_A_FAILURE = ("a3_requires_decision", "awaiting_seal")


def failed_action(a: dict[str, Any]) -> bool:
    """⟨2026-11-11⟩ Whether a step's action did not happen (the runner's `any_failed` rule)."""
    return a.get("outcome") not in (None, "ok") and a.get("code") not in NOT_A_FAILURE


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
        if failed_action(a):
            text += " (نشد)"
        if text not in phrases:
            phrases.append(text)
        if len(phrases) >= 3:
            break
    return "؛ ".join(phrases) if phrases else GENERIC_FA


def step_text(
    summary_fa: str | None, actions: list[dict[str, Any]], names: dict[str, str] | None = None
) -> str:
    """§41.1 a step in the owner's words: its own summary when plain, else its tools.
    ⟨2026-11-11⟩ When an action of the step did not happen (refused, failed, skipped), its tools'
    real outcome, never the model's summary (written before any tool ran: it may claim it)."""
    if any(
        isinstance(a, dict) and failed_action(a) and str(a.get("tool") or "") not in SILENT_TOOLS
        for a in actions
    ):
        return tools_text(actions, names)
    return plain(summary_fa) or tools_text(actions, names)


def end_text(
    state: str, code: str | None, partial: bool = False, *, reset_fa: str | None = None
) -> str | None:
    """How a run ended, as a line; None when nothing is worth a line. `reset_fa`: when a quota
    stopped it, the time its account has room again, in the owner's words («از ساعت 03:30»)."""
    if code in SKIP_END:
        return None
    quota = NS.quota_why_fa(code, reset_fa)
    if quota is not None and state != "done":
        return STOPPED_FA.format(why=quota)
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
    why = OR.base_reason(reason)  # ⟨2026-11-11⟩ a re-queued run says why it first started
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
# ⟨2026-11-11⟩ when a quota stopped a run, the time its account has room again, if the run carries
# it (read by name from the row: a column the runner may or may not have)
# (the runner keeps it on the run's last step: agents.steps.usage->>'retry_at')
RESET_SQL = (
    "(SELECT s.usage ->> 'retry_at' FROM agents.steps s WHERE s.run_id = r.id "
    "ORDER BY s.n DESC LIMIT 1)"
)
RUNS_SQL = f"""
SELECT r.id, r.state, r.error_code, r.partial, r.queued_at, r.started_at, r.finished_at, r.steps,
       r.reason, w.ref AS work_ref, w.title AS work_title, e.title_fa, c.name_fa AS company_fa,
       c.code AS company, {RESET_SQL} AS reset_raw
FROM agents.runs r JOIN work.work w ON w.id = r.work_id
JOIN core.employees e ON e.id = r.employee_id JOIN core.companies c ON c.id = w.company_id
WHERE r.work_id = ANY(:ids) AND r.trigger NOT IN ('talk', 'direct')
ORDER BY r.queued_at DESC LIMIT :lim
"""  # noqa: S608 - composed from module constants; values are bound
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
    zone = await owner_zone(tx)
    now = datetime.now(UTC)
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
            end = end_text(
                str(r["state"]), r["error_code"], bool(r.get("partial")),
                reset_fa=NS.when_fa(NS.parse_at(r.get("reset_raw"), r["finished_at"]), zone, now),
            )  # fmt: skip
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
    turns = await live_turns(tx, ids)
    wait_fa = await claude_wait_fa(tx, turns, zone, now)
    for t in turns:  # ⟨2026-11-10⟩ the workshop's turn is someone working
        # ⟨1.32⟩ §54 a direct turn is the session's own holder at work, by its own name
        direct = bool(t.get("direct")) and bool(t.get("holder_fa"))
        if direct:
            who = str(t["holder_fa"])
            doing = DIRECT_DOING_FA if t["state"] == "running" else DIRECT_QUEUED_FA
        else:
            who = WORKSHOP_WHO_FA if t["hands"] else SERVER_WHO_FA
            doing = TURN_DOING_FA if t["state"] == "running" else TURN_QUEUED_FA
        if t["state"] == "queued" and t.get("kind") == "claude" and wait_fa:
            doing = wait_fa  # ⟨2026-11-11⟩ both Claude accounts are full: not «همین حالا»
        last_fa, last_at = (
            await last_of_turn(tx, t["job_id"]) if t["state"] == "running" else (None, None)
        )
        working.append(
            Worker(
                who_fa=who,
                company_fa=str(t["company_fa"] or ""),
                work_title_fa=title_text(t["work_title"]),
                started_at=t["started_at"] or t["created_at"],
                step=int(t["turns"] or 0),
                doing_fa=doing,
                kind="direct" if direct else ("workshop" if t["hands"] else "server"),
                cap_s=int(t["timeout_s"]) if t.get("timeout_s") else None,
                last_fa=last_fa,
                last_at=last_at,
            )
        )
    # ⟨2026-11-11⟩ an outside call or a voice job of the order's works, until its deadline
    for c in await pending_outside(tx, works, now):
        working.append(
            Worker(
                who_fa=c["who_fa"],
                company_fa=c["company_fa"],
                work_title_fa=title_text(c["work_title"]),
                started_at=c["created_at"],
                step=0,
                doing_fa=c["doing_fa"],
                kind="call",
                cap_s=c["cap_s"],
                last_at=c["last_at"],
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
    elif (
        rep.get("badge") == "ready"
        and rep.get("closed_at") is None
        and rep.get("ended_at") is None
        and not pulse.open_tasks
    ):
        # ⟨2026-11-11⟩ the output is delivered and the owner approves it: never «آرام»
        waiting = READY_WAITING_FA
    idle_since = None
    if not working:
        idle_since = max([pulse.clock, *[x.at for x in lines]]) if lines else pulse.clock
    stuck = pulse.stuck_fa if not working else None
    mood = mood_of(working, waiting, stuck)
    return SessionActivity(
        working=working,
        last=last,
        idle_since=idle_since,
        waiting_fa=waiting,
        stuck_fa=stuck,
        mood=mood,
        mood_fa=MOOD_FA[mood],
    )


def mood_of(working: list[Worker], waiting: str | None, stuck: str | None) -> Mood:
    """⟨1.33⟩ §55.1 by code: someone works (a run with no step yet, or a turn that has done
    nothing yet, is still thinking); else it waits for the owner; else it is stuck; else calm.
    ⟨2026-11-11⟩ an outside call or a voice job pending is work (`working`)."""
    if working:
        moving = any(
            w.kind == "call" or (w.step > 0 if w.kind == "run" else w.last_fa is not None)
            for w in working
        )
        return "working" if moving else "thinking"
    if waiting:
        return "waiting"
    return "stuck" if stuck else "idle"


# ---------------------------------------------------------------- the pulse --
@dataclass
class Pulse:
    live: bool  # a run queued or running now (the badge `moving`)
    clock: datetime  # the story clock: the last step, the plan, the receipt
    idle: timedelta  # how long since the clock, when not live
    woken: dict[str, Any] | None  # the idle wake of this period (reason session_idle:<ref>)
    stuck_fa: str | None  # idle past two thresholds: the cause in the owner's words
    doing_fa: str | None = None  # the live run's last line
    # ⟨2026-11-11⟩ the plan's open tasks (todo, doing), the outside calls and voice jobs pending,
    # the idle wakes since the owner's last word, and whether they are spent (the cap reached,
    # or the last woken run only narrated): no further wake, the session is stuck
    open_tasks: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    wakes: int = 0
    spent: bool = False
    claude_wait_fa: str | None = None  # a Claude Code turn waits: both accounts are full
    owner_since: datetime | None = None  # the owner's last word on the order

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
DIRECT_DOING_FA = "دارد روی فرمان تو کار میکند؛ هر نوبت تا ۶۰ دقیقه"
DIRECT_QUEUED_FA = "همین حالا شروع میکند"


# ⟨1.33⟩ §55.1 the last thing a live turn did, from the events its runner sends as it works
TURN_TOOLS_FA: dict[str, str] = {
    "Bash": "دستور اجرا میکند",
    "Read": "فایل میخواند",
    "Grep": "در فایل‌ها میگردد",
    "Glob": "در فایل‌ها میگردد",
    "WebSearch": "در وب میگردد",
    "WebFetch": "صفحه‌ای را در وب میخواند",
    "TodoWrite": "برنامه‌اش را مرتب میکند",
    "Task": "بخشی از کار را جدا پیش میبرد",
}
TURN_FILE_FA = "فایل «{name}» را مینویسد"
TURN_COMMAND_FA = "دستور اجرا میکند"
TURN_EVENTS = 12
_HUB_TOOL = re.compile(r"^mcp__[A-Za-z0-9-]+__(.+)$")
_PERSIAN = re.compile(r"[\u0600-\u06FF]")
_SENTENCE = re.compile(r"(?<=[.!?؟…])\s|\n")


def _hub_tool(name: str) -> str | None:
    """`mcp__hq__order_ask` → `order.ask`: the hub's tool a direct turn called, by its own name."""
    m = _HUB_TOOL.match(name)
    if m is None:
        return None
    for tool in TOOLS_FA:
        if re.sub(r"[^A-Za-z0-9_-]", "_", tool) == m.group(1):
            return tool
    return None


def turn_line(kind: str, data: dict[str, Any]) -> str | None:
    """One event of a Claude Code turn as the owner may read it, or None when it says nothing he
    can read: its own Persian sentence, the file it writes (the name only), or the tool's verb.
    Never a command, a path or English text."""
    if kind == "message" and data.get("role") == "assistant":
        first = _SENTENCE.split(str(data.get("text") or "").strip(), maxsplit=1)[0].strip()
        if first and _PERSIAN.search(first):
            said = plain(first.lstrip("#*-• ").strip())
            return _cut(said, 120) if said else None
        return None
    if kind == "file_change":
        name = str(data.get("path") or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return TURN_FILE_FA.format(name=name[:60]) if name else None
    if kind == "command":
        return TURN_COMMAND_FA
    if kind == "progress" and data.get("tool"):
        tool = str(data["tool"])
        hub_tool = _hub_tool(tool)
        if hub_tool is not None:
            return None if hub_tool in SILENT_TOOLS else TOOLS_FA[hub_tool][1]
        return TURN_TOOLS_FA.get(tool)
    return None


async def last_of_turn(tx: Tx, job_id: Any) -> tuple[str | None, datetime | None]:
    rows = await tx.all(
        """SELECT data, at FROM infra.server_job_events
           WHERE job_id = :j AND type = 'session_event' ORDER BY seq DESC LIMIT :n""",
        j=job_id,
        n=TURN_EVENTS,
    )
    for r in rows:
        ev = OR._j(r["data"]) or {}
        raw = ev.get("data")
        inner: dict[str, Any] = raw if isinstance(raw, dict) else {}
        said = turn_line(str(ev.get("type") or ""), inner)
        if said:
            return said, r["at"]
    return None, None


async def live_turns(tx: Tx, work_ids: list[Any]) -> list[dict[str, Any]]:
    """⟨2026-11-10⟩ The workshop (or company-server) turns of these works that still run. A turn
    is live work although no agent run is: the holder's run ended when it handed the task over,
    and the turn may take an hour. Without this the session read as idle, the holder was woken
    after ten minutes and the owner was told «گیر کرد» while the workshop was building."""
    if not work_ids:
        return []
    rows = await tx.all(
        """SELECT ws.work_id, ws.turns, j.id AS job_id, j.timeout_s, j.state, j.created_at,
                  j.started_at, j.kind, COALESCE(j.args ->> 'hands', '') = 'true' AS hands,
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
    tx: Tx,
    rep: dict[str, Any],
    works: list[dict[str, Any]],
    *,
    minutes: int | None = None,
    hub: Any = None,
) -> Pulse:
    """§41.3 where the session stands: live, idle (since the clock), woken this period, stuck.
    ⟨2026-11-11⟩ An outside call or a voice job within its deadline is live too; the session is
    open while a root or a plan task is; stuck comes at once when the idle wakes are spent."""
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
    wait_fa = None
    if turns:
        doing = TURN_DOING_FA if turns[0]["state"] == "running" else TURN_QUEUED_FA
        wait_fa = await claude_wait_fa(tx, turns, await owner_zone(tx), now, hub)
        if wait_fa and turns[0]["state"] == "queued":
            doing = wait_fa
    calls = await pending_outside(tx, works, now) if live is None and not turns else []
    if calls:
        c = calls[0]
        doing = c["doing_fa"] if c["who_fa"] in c["doing_fa"] else f"{c['who_fa']}: {c['doing_fa']}"
    tasks = await open_tasks_of(tx, rep.get("order_id"))
    woken = None
    if ids:
        row = await tx.first(
            f"""SELECT r.id, r.state, r.error_code, r.queued_at, r.finished_at FROM agents.runs r
               WHERE r.work_id = ANY(:ids) AND {OR.BASE_REASON_SQL} = :r AND r.queued_at > :clock
               ORDER BY r.queued_at DESC LIMIT 1""",  # noqa: S608
            ids=ids,
            r=IDLE_REASON.format(ref=rep["ref"]),
            clock=clock,
        )
        woken = dict(row) if row is not None else None
    idle = max(now - clock, timedelta(0))
    T = timedelta(minutes=IDLE_MINUTES if minutes is None else minutes)
    stuck = None
    open_roots = [w for w in works if w["is_root"] and w["status"] in OR.OPEN]
    is_open = (
        rep.get("ended_at") is None
        and rep.get("closed_at") is None
        and bool(open_roots or (tasks and any(w["is_root"] for w in works)))
    )
    wakes: list[dict[str, Any]] = []
    spent = False
    since_word: datetime | None = None
    if is_open and ids:
        since_word = await owner_since(tx, rep, ids)
        tried = await idle_wakes(tx, rep, ids, since_word)
        wakes = [w for w in tried if not w["retry"]]  # a re-queued wake is the same wake
        if tried and all(w["state"] not in ("queued", "running") for w in tried):
            last_wake = tried[0]  # newest first
            # a run that ended normally having only read and reported; a failed run (a quota,
            # a model error) is the worker's to bring back, not the holder's narration
            narrated = (
                last_wake["started_at"] is not None
                and last_wake["state"] == "done"
                and not last_wake["acted"]
                and not last_wake["ticked"]
            )
            # ⟨2026-11-11⟩ spent only while the story has not moved past that wake's end: work
            # that came after it (a child's delivery, a reply, the owner) is judged afresh, by
            # the idle thresholds
            ended_at = last_wake["finished_at"]
            spent = (len(wakes) >= IDLE_WAKES_MAX or narrated) and (
                ended_at is None or clock <= ended_at
            )
    if (
        live is None
        and not turns
        and not calls
        and is_open
        and not OR._j(rep.get("turn"))
        and (idle >= 2 * T or spent)
    ):
        stuck = await stuck_cause(tx, rep, works, clock, wakes=len(wakes), tasks=tasks)
    return Pulse(live=live is not None or bool(turns) or bool(calls), clock=clock, idle=idle,
                 woken=woken, stuck_fa=stuck, doing_fa=doing, open_tasks=tasks, calls=calls,
                 wakes=len(wakes), spent=spent, claude_wait_fa=wait_fa,
                 owner_since=since_word)  # fmt: skip


# ------------------------------------------------- ⟨2026-11-11⟩ what keeps it open --
async def open_tasks_of(tx: Tx, order_id: Any) -> list[dict[str, Any]]:
    """The plan's open tasks (doing first, then todo by number); a task handed to a work of its
    own (a card's hand-over) is done once that work delivered (W.PLAN_OPEN_SQL's rule)."""
    if order_id is None:
        return []
    rows = await tx.all(
        """SELECT t.n, t.title_fa, t.state FROM owner.session_tasks t WHERE t.order_id = :o
             AND t.state IN ('doing', 'todo')
             AND NOT EXISTS (SELECT 1 FROM work.work c WHERE c.ref = t.work_ref
                               AND c.status IN ('delivered', 'done'))
           ORDER BY (t.state = 'doing') DESC, t.n""",
        o=order_id,
    )
    return [dict(r) for r in rows]


OWNER_WORD_LIKE = tuple(f"{p}%" for p in OR.OWNER_WORD_REASONS)


async def owner_since(tx: Tx, rep: dict[str, Any], ids: list[Any]) -> datetime:
    """When the owner last spoke on the order: his last step in the story (his word, «ادامه بده»,
    a pace), a run his word started, else the order's receipt. The idle wakes count from here."""
    since: datetime = rep.get("created_at") or datetime.now(UTC)
    for s in OR._j(rep.get("steps")) or []:
        if not isinstance(s, dict) or s.get("who_fa") != OWNER_FA:
            continue
        try:
            at = datetime.fromisoformat(str(s.get("at")))
        except ValueError:
            continue
        at = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
        since = max(since, at)
    if ids:
        run_at = await tx.scalar(
            f"""SELECT max(r.queued_at) FROM agents.runs r
               WHERE r.work_id = ANY(:ids) AND {OR.BASE_REASON_SQL} LIKE ANY(CAST(:w AS text[]))
                 AND r.reason = {OR.BASE_REASON_SQL}""",  # noqa: S608 - a re-queue is no new word
            ids=ids,
            w=list(OWNER_WORD_LIKE),
        )
        if run_at is not None:
            since = max(since, run_at)
    return since


HANDED_NOTE = "direct turn%"  # a classic run handed to a direct turn ends with this note


async def idle_wakes(
    tx: Tx, rep: dict[str, Any], ids: list[Any], since: datetime
) -> list[dict[str, Any]]:
    """The idle wakes of this order since `since`, newest first: each run's state, whether it did
    anything but read and report (`acted`) and whether it ticked a plan task (`ticked`).
    ⟨2026-11-11⟩ A wake the worker re-queued (`requeue:session_idle:…`) is listed with
    `retry` true: the same wake tried again, not one more. A wake handed to a direct turn (the
    classic run ends at once, `direct turn …`) is judged by that turn: the first direct run of
    the same work queued at or after it, its state and its window (a deliverable or a child work
    made in it is acting; a task done in it is a tick). Handed but no turn found (it waited for
    one still working): never counted as narration."""
    rows = await tx.all(
        f"""SELECT x.*,
                  CASE WHEN x.handed THEN (
                      x.direct_id IS NULL
                      OR EXISTS (SELECT 1 FROM cartable.deliverables dl
                                 WHERE dl.work_id = x.work_id AND dl.created_at >= x.started_at
                                   AND dl.created_at <= COALESCE(x.finished_at, now()))
                      OR EXISTS (SELECT 1 FROM work.work c
                                 WHERE (c.parent_id = x.work_id OR c.requested_by_work_id = x.work_id)
                                   AND c.created_at >= x.started_at
                                   AND c.created_at <= COALESCE(x.finished_at, now())))
                  ELSE EXISTS (
                      SELECT 1 FROM agents.steps s CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
                      WHERE s.run_id = x.id AND a ->> 'outcome' = 'ok'
                        AND NOT (a ->> 'tool' = ANY(CAST(:narr AS text[]))))
                  END AS acted,
                  EXISTS (SELECT 1 FROM owner.session_tasks t
                          WHERE t.order_id = :o AND t.state = 'done' AND x.started_at IS NOT NULL
                            AND t.updated_at >= x.started_at
                            AND t.updated_at <= COALESCE(x.finished_at, now())) AS ticked
           FROM (
               SELECT r.id, r.work_id, r.queued_at, r.reason <> {OR.BASE_REASON_SQL} AS retry,
                      COALESCE(r.note, '') LIKE :handed AS handed, d.id AS direct_id,
                      CASE WHEN COALESCE(r.note, '') LIKE :handed
                           THEN COALESCE(d.state, r.state) ELSE r.state END AS state,
                      CASE WHEN COALESCE(r.note, '') LIKE :handed
                           THEN d.started_at ELSE r.started_at END AS started_at,
                      CASE WHEN COALESCE(r.note, '') LIKE :handed
                           THEN COALESCE(d.finished_at, r.finished_at)
                           ELSE r.finished_at END AS finished_at
               FROM agents.runs r
               LEFT JOIN LATERAL (
                   SELECT d.id, d.state, d.started_at, d.finished_at FROM agents.runs d
                   WHERE d.trigger = 'direct' AND d.work_id = r.work_id
                     AND d.queued_at >= r.queued_at
                   ORDER BY d.queued_at LIMIT 1) d ON COALESCE(r.note, '') LIKE :handed
               WHERE r.work_id = ANY(:ids) AND {OR.BASE_REASON_SQL} = :reason
                 AND r.queued_at > :since) x
           ORDER BY x.queued_at DESC""",  # noqa: S608
        ids=ids,
        reason=IDLE_REASON.format(ref=rep["ref"]),
        since=since,
        narr=list(NARRATION_TOOLS),
        o=rep.get("order_id"),
        handed=HANDED_NOTE,
    )
    return [dict(r) for r in rows]


async def owner_zone(tx: Tx) -> Any:
    """The owner's time zone (owner.settings), for a time he reads."""
    from hq_api.domain import gov_common as G

    try:
        async with tx.conn.begin_nested():
            return G.zone(await G.owner_tz(tx))
    except Exception:  # noqa: BLE001 - a time is shown in the default zone rather than fail
        return G.zone(G.DEFAULT_TZ)


async def claude_wait_fa(
    tx: Tx, turns: list[dict[str, Any]], zone: Any, now: datetime, hub: Any = None
) -> str | None:
    """⟨2026-11-11⟩ When a queued Claude Code turn waits because both Claude accounts are full,
    the owner's sentence with the time one has room again; else None. With the hub (its stored
    accounts): servers.runner_claude_pick / room_at, the dispatcher's own rule; without it, every
    account the hub knows, read the same way. Never fails the caller."""
    if not any(t.get("state") == "queued" and t.get("kind") == "claude" for t in turns):
        return None
    from hq_api.domain import servers as SV

    at: datetime | bool | None
    try:
        async with tx.conn.begin_nested():
            if hub is not None:
                if not (await SV.runner_claude_pick(tx, hub)).hold:
                    return None
                at = await SV.room_at(tx, hub)
            else:
                at = await _room_at_known(tx, now)
                if at is False:
                    return None
    except Exception:  # noqa: BLE001
        log.warning("the Claude accounts could not be read")
        return None
    when = NS.when_fa(at, zone, now) if isinstance(at, datetime) else None
    return CLAUDE_WAIT_FA.format(when=when) if when else CLAUDE_WAIT_SOON_FA


async def _room_at_known(tx: Tx, now: datetime) -> datetime | bool | None:
    """Without the hub's secrets: False when an account the hub knows has room, else when the
    first one has room again (servers.room_at's reading: the latest reset of its full windows,
    the earliest such account; None when unknown)."""
    from hq_api.domain import servers as SV

    rows = [dict(r) for r in await tx.all(SV.ACCOUNTS_SQL, keys=[k for k, _ in SV.RUNNER_ACCOUNTS])]
    usable = [
        r for r in rows if r.get("connection_status") in ("enabled", "ready", "quota_exhausted")
    ]
    if not usable:
        return False
    best: datetime | None = None
    for r in usable:
        exhausted = r.get("connection_status") == "quota_exhausted" and (
            r.get("resets_at") is None or r["resets_at"] > now
        )
        if not (exhausted or SV.account_full(r, now)):
            return False  # one has room: the turn starts as soon as the runner asks
        full = [
            w for w in SV._windows(r).values() if isinstance(w, dict) and SV._window_full(w, now)
        ]
        if r.get("status") is not None and SV._window_full(r, now):
            full.append(r)
        ends = [e for e in (SV._at(w.get("resets_at")) for w in full) if e is not None]
        if not ends and r.get("resets_at") is not None:
            ends = [r["resets_at"]]
        if ends and (best is None or max(ends) < best):
            best = max(ends)
    return best


# ----------------------------------------- ⟨2026-11-11⟩ outside calls, voice jobs --
async def _substitute_calls(
    tx: Tx, works: list[dict[str, Any]], now: datetime, since: datetime | None = None
) -> list[dict[str, Any]]:
    """Per work: the substitute calls it made, pending (`since` None) or ended without an answer
    since `since` (substitutes.pending_for / ended_since), each with its work."""
    from hq_api.domain import substitutes as S

    out: list[dict[str, Any]] = []
    for w in works:
        if since is None and w["status"] not in (*OR.OPEN, "delivered"):
            continue
        try:
            async with tx.conn.begin_nested():
                rows = (
                    await S.pending_for(tx, [w["id"]], now)
                    if since is None
                    else await S.ended_since(tx, [w["id"]], since)
                )
        except Exception:  # noqa: BLE001 - the session's view never fails on an outside call
            log.warning("the outside calls could not be read", extra={"work": str(w["ref"])})
            continue
        out += [{**dict(r), "work": w} for r in rows]
    return out


VOICE_SQL = """
SELECT DISTINCT ON (a ->> 'ref') a ->> 'ref' AS job, r.work_id, r.company_id, s.at AS asked_at,
       st.at AS started_at,
       (SELECT e.summary FROM audit.entries e
         WHERE e.company_id = r.company_id AND e.action = 'speech.made' AND e.at >= st.at
           AND strpos(e.summary, a ->> 'ref') > 0
         ORDER BY e.at LIMIT 1) AS end_summary,
       (SELECT e.at FROM audit.entries e
         WHERE e.company_id = r.company_id AND e.action = 'speech.made' AND e.at >= st.at
           AND strpos(e.summary, a ->> 'ref') > 0
         ORDER BY e.at LIMIT 1) AS ended_at
FROM agents.runs r JOIN agents.steps s ON s.run_id = r.id
CROSS JOIN LATERAL jsonb_array_elements(s.actions) a
JOIN audit.entries st ON st.company_id = r.company_id AND st.action = 'speech.make'
     AND st.target_ref = a ->> 'ref' AND st.at >= CAST(:since AS timestamptz) - interval '1 hour'
WHERE r.work_id = ANY(:ids) AND s.at > :since AND a ->> 'tool' = 'speech.make'
  AND a ->> 'outcome' = 'ok' AND a ->> 'ref' IS NOT NULL
ORDER BY a ->> 'ref', s.at
"""


async def _voice_jobs(tx: Tx, ids: list[Any], since: datetime) -> list[dict[str, Any]]:
    """The voice jobs (`speech.make`) the order's works started since `since`: the job id is the
    ref its first answer gave (the start's own audit row confirms it), its end the `speech.made`
    row that names it (domain/speech_make)."""
    if not ids:
        return []
    try:
        async with tx.conn.begin_nested():
            return [dict(r) for r in await tx.all(VOICE_SQL, ids=ids, since=since)]
    except Exception:  # noqa: BLE001 - the session's view never fails on a voice job
        log.warning("the voice jobs could not be read")
        return []


def _voice_failed(summary: str | None) -> str | None:
    """The refusal code of an ended voice job (its `speech.made` summary), None when it is done."""
    m = re.search(r"failed: ([a-z_]+)", summary or "")
    return m.group(1) if m else None


async def pending_outside(
    tx: Tx, works: list[dict[str, Any]], now: datetime | None = None
) -> list[dict[str, Any]]:
    """⟨2026-11-11⟩ What works for the session outside a run: the substitute calls of its works
    (queued or running, within their deadline) and its voice jobs (within VOICE_DEADLINE), each as
    {who_fa, company_fa, work_title, doing_fa, created_at, cap_s, last_at, deadline_at}, oldest
    first."""
    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for c in await _substitute_calls(tx, works, now):
        w = c["work"]
        player, seat = str(c.get("player_fa") or "بازیکن بیرونی"), str(c.get("seat_fa") or "کار")
        created, deadline = c.get("created_at") or now, c.get("deadline_at")
        if c.get("ending") and (deadline is None or now > deadline + ENDING_GRACE):
            continue  # the reaper did not end it in time: not live, the cause names it
        if c.get("ending"):
            doing = CALL_ENDING_FA.format(player=player)
        elif c.get("state") == "running":
            doing = CALL_DOING_FA.format(seat=seat)
        else:
            doing = CALL_QUEUED_FA.format(player=player, seat=seat)
        out.append({
            "who_fa": player,
            "company_fa": str(w.get("company_fa") or ""),
            "work_title": w.get("title"),
            "doing_fa": doing,
            "created_at": created,
            "cap_s": max(int((deadline - created).total_seconds()), 1) if deadline else None,
            "last_at": c.get("claimed_at") or created,
            "deadline_at": deadline,
        })  # fmt: skip
    by_id = {w["id"]: w for w in works}
    for v in await _voice_jobs(tx, list(by_id), now - VOICE_DEADLINE):
        start = v["started_at"] or v["asked_at"]
        if v["ended_at"] is not None or start + VOICE_DEADLINE <= now:
            continue
        w = by_id.get(v["work_id"]) or {}
        out.append({
            "who_fa": VOICE_WHO_FA,
            "company_fa": str(w.get("company_fa") or ""),
            "work_title": w.get("title"),
            "doing_fa": CALL_DOING_FA.format(seat=VOICE_SEAT_FA),
            "created_at": start,
            "cap_s": int(VOICE_DEADLINE.total_seconds()),
            "last_at": start,
            "deadline_at": start + VOICE_DEADLINE,
        })  # fmt: skip
    out.sort(key=lambda c: c["created_at"])
    return out


async def ended_outside(
    tx: Tx, works: list[dict[str, Any]], since: datetime, now: datetime | None = None
) -> list[dict[str, Any]]:
    """⟨2026-11-11⟩ The outside calls and voice jobs of the order's works that ended without an
    answer at or after `since` (failed, skipped, or a voice past its deadline), newest first:
    {who_fa, seat_fa, state, code, why_fa, at}."""
    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for c in await _substitute_calls(tx, works, now, since):
        out.append({
            "who_fa": str(c.get("player_fa") or "بازیکن بیرونی"),
            "seat_fa": str(c.get("seat_fa") or "کار"),
            "state": str(c.get("state") or "failed"),
            "code": str(c.get("state_reason") or "").split(":", 1)[0].strip() or None,
            "why_fa": str(c.get("reason_fa") or VOICE_WHY_DEFAULT_FA),
            "at": c.get("finished_at") or now,
        })  # fmt: skip
    for c in await _substitute_calls(tx, works, now):
        deadline = c.get("deadline_at")
        if not c.get("ending") or deadline is None or now <= deadline + ENDING_GRACE:
            continue
        # past its deadline and its grace, still not ended: as good as ended without an answer
        running = c.get("state") == "running"
        out.append({
            "who_fa": str(c.get("player_fa") or "بازیکن بیرونی"),
            "seat_fa": str(c.get("seat_fa") or "کار"),
            "state": "failed",
            "code": "timeout" if running else "not_claimed",
            "why_fa": "جوابش طول کشید" if running else "نوبتش نرسید",
            "at": deadline,
        })  # fmt: skip
    for v in await _voice_jobs(tx, [w["id"] for w in works], since - VOICE_DEADLINE):
        start = v["started_at"] or v["asked_at"]
        code = _voice_failed(v["end_summary"]) if v["ended_at"] is not None else None
        if v["ended_at"] is None and start + VOICE_DEADLINE <= now:
            code, at = "timeout", start + VOICE_DEADLINE
        elif code is not None:
            at = v["ended_at"]
        else:
            continue  # done, or still within its deadline
        if at < since:
            continue
        out.append({
            "who_fa": VOICE_WHO_FA, "seat_fa": VOICE_SEAT_FA, "state": "failed", "code": code,
            "why_fa": VOICE_WHY_FA.get(code, VOICE_WHY_DEFAULT_FA), "at": at,
        })  # fmt: skip
    out.sort(key=lambda c: c["at"], reverse=True)
    return out


# ----------------------------------------------------------------- the cause --
async def stuck_cause(
    tx: Tx,
    rep: dict[str, Any],
    works: list[dict[str, Any]],
    clock: datetime,
    *,
    wakes: int = 0,
    tasks: list[dict[str, Any]] | None = None,
) -> str:
    """Why the session does not move, in the owner's words, with what fixes it: ⟨2026-11-11⟩ an
    outside call or a voice job that ended without an answer, the last refused or failed run, a
    blocker of the report, a sign-in or key a step needed, an empty seat of the company's working
    group; else what was last done and which task of the plan is left (`wakes`: how many times the
    holder was woken for nothing), and only with no plan «نمیدانیم چرا»."""
    ids = [w["id"] for w in works]
    since = clock - timedelta(minutes=10)
    for c in await ended_outside(tx, works, since):
        return STUCK_CALL_FA.format(who=c["who_fa"], seat=c["seat_fa"], why=c["why_fa"])
    last = await tx.first(
        # ⟨2026-11-10⟩ only what ended since the session last moved (an old refusal the order got
        # past is not why it stands now), and never the hold for the owner's own answer
        f"""SELECT r.state, r.error_code, r.note, r.finished_at, {RESET_SQL} AS reset_raw
           FROM agents.runs r
           WHERE r.work_id = ANY(:ids) AND r.state IN ('refused', 'failed')
             AND r.trigger NOT IN ('talk', 'direct')
             AND r.error_code IS NOT NULL AND r.error_code <> 'owner_turn'
             AND COALESCE(r.finished_at, r.queued_at) >= CAST(:since AS timestamptz) - interval '10 minutes'
           ORDER BY COALESCE(r.finished_at, r.queued_at) DESC LIMIT 1""",  # noqa: S608
        ids=ids,
        since=clock,
    )
    if last is not None and last["error_code"] not in SKIP_END:
        code = str(last["error_code"])
        now = datetime.now(UTC)
        reset = NS.parse_at(last.get("reset_raw"), last["finished_at"])
        quota = NS.quota_why_fa(code, NS.when_fa(reset, await owner_zone(tx), now))
        if quota is not None:
            return quota
        if code in NS.RUN_WHY_FA:
            why, fix = NS.RUN_WHY_FA[code]
            return f"{why} {fix}"
        if code in END_WHY_FA:
            return f"{END_WHY_FA[code]} «ادامه بده» را بزن."
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
            return "بازیکن بیرونی وارد حسابش نیست؛ در صفحه‌ی بازیکن‌ها واردش کن."
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
    tasks = await open_tasks_of(tx, rep.get("order_id")) if tasks is None else tasks
    if tasks:  # ⟨2026-11-11⟩ what was last done, and what is left
        nxt = tasks[0]
        last_fa = last_words(_last_step_fa(rep) or GENERIC_FA)
        title = _cut(str(nxt["title_fa"]), 60)
        if wakes:
            return STUCK_IDLE_FA.format(k=wakes, last=last_fa, n=nxt["n"], title=title)
        return STUCK_PLAN_FA.format(last=last_fa, n=nxt["n"], title=title)
    return UNKNOWN_WHY_FA


def last_words(text: str, limit: int = LAST_WORDS) -> str:
    """The END of a line, as the apps show «آخرین کار» (lastWordsFa): whole when it fits, else its
    last sentences that fit (else its last words) after «… »; never a stop or «؛» before the
    sentence's own «؛»."""
    one = " ".join(text.split())
    if len(one) > limit:
        out = ""
        for part in reversed([p for p in _SENTENCE_END.split(one) if p]):
            nxt = f"{part} {out}" if out else part
            if len(nxt) > limit:
                break
            out = nxt
        if not out:
            tail = one[-limit:]
            out = tail.split(" ", 1)[1] if " " in tail else tail
        one = f"… {out}"
    return one.rstrip(" .،؛…!؟?") or one


def _last_step_fa(rep: dict[str, Any]) -> str | None:
    """The story's last step written by someone working on it (not the system's own lines, not
    the owner's word)."""
    for s in reversed(OR._j(rep.get("steps")) or []):
        if not isinstance(s, dict) or s.get("who_fa") in (SYSTEM_FA, OWNER_FA, "منشی هلدینگ"):
            continue
        said = plain(str(s.get("what_fa") or ""))
        if said:
            return said
    return None


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
                raw = await tx.scalar(
                    """SELECT usage ->> 'retry_at' FROM agents.steps WHERE run_id = :r
                       ORDER BY n DESC LIMIT 1""",
                    r=run.get("id"),
                )
                now = datetime.now(UTC)
                reset = NS.when_fa(NS.parse_at(raw, now), await owner_zone(tx), now)
                text = end_text(state or "done", code, partial, reset_fa=reset)
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
    if (
        h is not None
        and h.get("work_id") is not None
        and h.get("work_status") not in OR.OPEN
        and rep.get("ended_at") is None
        and await open_tasks_of(tx, rep.get("order_id"))
        # ⟨2026-11-11⟩ the root was delivered with the plan unfinished: it opens again first
        and await reopen_for_plan(tx, ref) is not None
    ):
        h = await OT.holder(tx, ref)
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


async def reopen_for_plan(tx: Tx, ref: str) -> dict[str, Any] | None:
    """⟨2026-11-11⟩ The order's delivered root goes back to `in_progress` when its plan still has
    an open task (order_turns._reopen_delivered), with a step naming the task left. Answers the
    root reopened, or None (nothing delivered to reopen, or nothing left in the plan)."""
    from hq_api.domain import order_turns as OT

    rep = await OR.ensure(tx, ref)
    order = await OR.load_order(tx, ref)
    if rep is None or order is None or rep.get("ended_at") is not None:
        return None
    tasks = await open_tasks_of(tx, rep.get("order_id"))
    if not tasks:
        return None
    works = await OR.tree(tx, OR.root_refs(order))
    if any(w["is_root"] and w["status"] in OR.OPEN for w in works):
        return None
    root = await OT._reopen_delivered(tx, ref, works)
    if root is not None:
        await OR._append_steps(
            tx, rep["id"], [OR._step(SYSTEM_FA, REOPENED_FA.format(n=tasks[0]["n"]))]
        )
    return root


async def finish_plan(tx: Tx, works: list[dict[str, Any]]) -> list[str]:
    """⟨2026-11-11⟩ Every plan task is done and nothing runs: an open root whose last output is a
    complete one is delivered now (work.delivered_status still decides: an open child or a
    progress under 100 keeps it open). Answers the refs delivered."""
    done: list[str] = []
    for w in works:
        if not w["is_root"] or w["status"] not in OR.OPEN:
            continue
        last = await tx.scalar(
            """SELECT title FROM cartable.deliverables WHERE work_id = :w
               ORDER BY created_at DESC, ref DESC LIMIT 1""",
            w=w["id"],
        )
        if last is None or W.is_partial_title(last):
            continue
        status = await W.set_status(
            tx, w, "delivered", plan_open=False, delivered_at=datetime.now(UTC)
        )
        if status == "delivered":
            await W.event(tx, w, "delivered", OR.SERVICE, {"why": "plan_done"})
            await W.close_delivered_children(tx, w, OR.SERVICE)
            done.append(str(w["ref"]))
    return done


async def sweep(tx: Tx, ref: str, *, minutes: int | None = None, hub: Any = None) -> list[str]:
    """§41.3 the sweep of one session (order_report.tick, every few minutes): idle → the holder
    woken once («مسئول دوباره سر کار آمد: ادامه از کار N»); still idle a threshold later → `stuck`,
    a step and ONE owner notification naming the cause. What fired: idle_wake, stuck.
    ⟨2026-11-11⟩ also: `reopened` (the root was delivered with the plan unfinished: open again and
    the holder woken), `plan_done` (every task done and a complete output: the root delivered,
    the session ready), `claude_wait` (a turn waits for a Claude account: one step with the time).
    The wakes are capped (IDLE_WAKES_MAX since the owner's last word; none after a woken run that
    only narrated): then the session is stuck at once."""
    rep = await OR.ensure(tx, ref)
    if rep is None or rep.get("ended_at") is not None or rep.get("closed_at") is not None:
        return []
    if OR._j(rep.get("turn")):
        return []  # the owner's turn: nobody is woken, nothing is stuck
    order = await OR.load_order(tx, ref)
    if order is None:
        return []
    works = await OR.tree(tx, OR.root_refs(order))
    T = IDLE_MINUTES if minutes is None else minutes
    fired: list[str] = []
    if not any(w["is_root"] and w["status"] in OR.OPEN for w in works):
        # ⟨2026-11-11⟩ open = an open root OR an open plan task: a root delivered with tasks
        # left opens again and its holder is woken (once: the wake counts against the cap)
        if await reopen_for_plan(tx, ref) is None:
            return []
        fired.append("reopened")
        rep = await OR.ensure(tx, ref) or rep
        works = await OR.tree(tx, OR.root_refs(order))
        pulse = await read_pulse(tx, rep, works, minutes=T)
        if not pulse.live and not pulse.spent:
            await wake_holder(tx, ref, IDLE_REASON.format(ref=ref), step_fa=WOKEN_FA)
            fired.append("idle_wake")
        await OR.refresh(tx, ref)
        return fired
    pulse = await read_pulse(tx, rep, works, minutes=T, hub=hub)
    if pulse.live:
        if pulse.claude_wait_fa and not _stepped_since(rep, pulse.clock, CLAUDE_WAIT_PREFIX):
            await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, pulse.claude_wait_fa)])
            fired.append("claude_wait")
            await OR.refresh(tx, ref)
        return fired
    if (
        not pulse.open_tasks
        and await tx.scalar(
            "SELECT 1 FROM owner.session_tasks WHERE order_id = :o AND state <> 'dropped' LIMIT 1",
            o=rep["order_id"],
        )
        # ⟨2026-11-11⟩ the plan is done and nothing runs: a complete output makes it ready
        and await finish_plan(tx, works)
    ):
        await OR._append_steps(tx, rep["id"], [OR._step(SYSTEM_FA, PLAN_DONE_FA)])
        await OR.refresh(tx, ref)
        return ["plan_done"]
    threshold = timedelta(minutes=T)
    if (
        not pulse.spent
        and pulse.wakes < IDLE_WAKES_MAX
        and pulse.woken is None
        and pulse.idle >= threshold
        and not _stepped_since(rep, pulse.clock, "مسئول دوباره سر کار آمد", "مسئول بیدار نشد")
    ):
        await wake_holder(tx, ref, IDLE_REASON.format(ref=ref), step_fa=WOKEN_FA)
        fired.append("idle_wake")
        rep = await OR.ensure(tx, ref) or rep
    # once per stall: a spent session is told once since the owner's last word too
    told_since = pulse.clock
    if pulse.spent and pulse.owner_since is not None:
        told_since = max(pulse.clock, pulse.owner_since)
    if pulse.stuck_fa and not await _told_stuck(tx, rep, told_since):
        if not _stepped_since(rep, pulse.clock, "گیر کرد"):
            await OR._append_steps(
                tx, rep["id"], [OR._step(SYSTEM_FA, STUCK_FA.format(why=pulse.stuck_fa))]
            )
        holding = await OR._holding(tx)
        text = " ".join((order.get("text") or "").split())[:80]
        idle_m = int(pulse.idle.total_seconds() // 60)
        await notify.raise_notification(
            tx,
            company_id=holding["id"],
            company_code=holding["code"],
            level="decision",
            title_fa=STUCK_TITLE_FA.format(text=HZ.humanize(text) or text)[:300],
            body_fa=HZ.plain(
                (
                    f"از {idle_m} دقیقه پیش کسی روی این فرمان کار نمیکند"
                    if idle_m >= 1
                    else "مسئول دوباره سر کار آمد ولی کار جلو نرفت"
                ),
                pulse.stuck_fa,
                "در جلسه‌ی فرمان «ادامه بده» را بزن یا آنچه لازم است را درست کن",
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
