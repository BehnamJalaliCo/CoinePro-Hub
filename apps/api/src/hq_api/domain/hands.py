"""⟨2026-11-09⟩ The workshop: hands for any task (contract §43, docs/WORKSHOP_HANDS.md).

The owner: «اپ وسیله‌ی ارتباط است؛ سرور کامپیوتر است و Claude روی سرور مغز و دست دارد». Every
working role of every company hands a task none of its tools covers to the holding's workshop
(`workshop.run`): Claude Code with a whole computer, on the holding's own paired server (a
locked-down user on the hub host with its own hq-runner, runner >= RUNNER_MIN). Nothing here is
about one kind of task: the brief is the agent's words, the workshop decides how.

A turn is a workspace turn (§33.10) of the caller's work on the workshop server: the same folder
`~/hq-workspace/<W-ref>` and the same Claude session on every later call for that work (a fix is
the next call). Opus 5.5, no token cap, TURN_TIMEOUT_S (60 minutes): past it the runner stops it
and the work's assignee gets a run with the reason (never a silent stall).

When the turn ends (workspace.after_job): its answer and the files it left in `out/` (sent by the
runner as it ends, attached to the work's company) become an output of that work, with open and
download in the session. A child work is delivered by it (its parent's holder is woken as for any
child); a root work (the order itself) stays open and its holder gets a run (`workshop_done:`) to
show the owner and ask «تأیید یا اصلاح؟». A failed turn wakes the holder with the reason.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import servers as SV
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.workshop import domain as WD
from hq_api.workshop import server_sessions as SS

RUNNER_MIN = "0.3.2"  # the runner that sends `out/` back
MODEL = "claude-opus-5-5"
PERMISSION_MODE = "acceptEdits"  # non-interactive: the tools below run without asking
ALLOWED_TOOLS = (
    "Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep",
    "WebFetch", "WebSearch", "TodoWrite", "Task", "Agent",
)  # fmt: skip
TURN_TIMEOUT_S = 3600
# the session's own limit inside the turn: what is left is for sending `out/` before the hub's
# sweep (the job's timeout + 120 s) could fail a turn that ended well
SESSION_TIMEOUT_S = TURN_TIMEOUT_S - 180
OUT_DIR = "out"
DONE_REASON = WS.DONE_REASON
BRIEF_CHARS = 20000
FILES_MAX = WS.FILES_MAX


class WorkshopRun(BaseModel):
    job: str
    work_ref: str
    state: str  # starting | working
    turn: int
    path: str
    server: str


def is_hands(j: dict[str, Any]) -> bool:
    return bool((j.get("args") or {}).get("hands"))


async def workshop_server(tx: Tx) -> dict[str, Any] | None:
    """The holding's paired server on runner >= RUNNER_MIN (an online one first), or None."""
    rows = await tx.all(
        """SELECT s.id, s.runner_version FROM infra.servers s
           JOIN core.companies c ON c.id = s.company_id
           WHERE c.kind = 'holding' AND s.origin = 'attached' AND s.state IN ('online', 'offline')
           ORDER BY (s.state = 'online') DESC, s.created_at"""
    )
    for r in rows:
        if WS.version_ok(r["runner_version"], RUNNER_MIN):
            return await SV.load_server(tx, r["id"])
    return None


async def the_work(tx: Tx, who: Principal, ref: str | None) -> dict[str, Any]:
    """The work the turn is for: `ref` (assigned to the caller), else the caller's run's work."""
    if ref:
        w = await tx.first("SELECT id FROM work.work WHERE ref = :r", r=ref)
        if w is None:
            raise ApiError(404, "not_found", fields={"work": "no such work item"})
        w = await W.load(tx, w["id"])
        if w["assignee_id"] != who.employee_id:
            raise ApiError(403, "policy_denied", fields={"work": "a work item assigned to you"})
    else:
        wid = await tx.scalar(
            "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid) AND employee_id = :e",
            r=who.run_id,
            e=who.employee_id,
        )
        if wid is None:
            raise ApiError(
                422,
                "validation_failed",
                fields={"work": "this run has no work item: name one assigned to you"},
            )
        w = await W.load(tx, wid)
    if w["status"] in W.CLOSED:
        raise ApiError(409, "work_closed", fields={"work": f"{w['ref']} is {w['status']}"})
    return w


def compose(w: dict[str, Any], who: Principal, ask: str, first: bool) -> str:
    """The turn's brief: the workshop's ground rules (plain), then the agent's ask as written."""
    lines = [
        f"# کار {w['ref']}: {w['title']}",
        "",
        f"درخواست‌دهنده: {who.code} از شرکت {w['company']}. تو Claude Code در کارگاه هلدینگ هستی: "
        "یک کامپیوتر کامل با ffmpeg، Chromium (Playwright برای python)، node، python و فونت "
        "IRANYekanX، و اینترنت. هر چه لازم داری (کتابخانه، ابزار، کد) را خودت در همین پوشه نصب "
        "کن یا بساز (npm و pip در همین پوشه، بی sudo).",
        f"پوشه‌ی ماندگار همین کار: {WS.path_of(w['ref'])}. نوبت بعدی همین کار همین پوشه و همین نشست "
        "را میبیند.",
        f"**هر فایل تحویلی را در پوشه‌ی {OUT_DIR}/ بگذار**؛ فقط همین فایل‌ها با لینک در جلسه به "
        "مالک میرسند. نوع‌های قابل تحویل: ویدیو (mp4، webm، mov؛ تا ۲۰۰MB و ۱۰ دقیقه)، تصویر "
        "(png، jpg، webp)، PDF، متن و Markdown، ZIP، صدا. فایل کهنه‌ای را که دیگر تحویلی نیست از "
        f"{OUT_DIR}/ بردار.",
        "حدود ۵۵ دقیقه وقت داری (سقف این نوبت). اگر کار بزرگ است، اول نسخه‌ای کامل و قابل "
        f"دیدن در {OUT_DIR}/ بساز و بعد بهترش کن.",
        "پاسخ نهایی‌ات کوتاه و فارسی باشد: چه ساختی، هر فایل out/ چیست، و چه چیزی تأیید مالک را "
        "میخواهد.",
        "منتشر نکن، پول نده، به کسی پیام نده و حساب نساز: انتشار بعد از تأیید مالک از راه ستاد است. "
        "بیرون از این پوشه کاری نکن. هیچ رمزی را چاپ نکن. هر دستور ویرانگر منتظر مُهر مالک میماند.",
        "",
        "## خواسته" if first else "## خواسته‌ی تازه (ادامه‌ی همین کار، همین پوشه)",
        ask[:BRIEF_CHARS],
    ]
    return "\n".join(lines)


async def start(
    tx: Tx,
    who: Principal,
    server: dict[str, Any],
    w: dict[str, Any],
    *,
    brief: str,
    title: str | None,
    request_id: str | None = None,
) -> WorkshopRun:
    """The turn on the workshop for the work (its workspace made or resumed), or the turn that
    still runs (`state: working`, nothing new). 409 for a workspace the owner stopped or one on a
    company's own server."""
    w = await W.load(tx, w["id"], lock=True)
    ws = await WS.of_work(tx, w["id"], lock=True)
    if ws is not None and ws["server_id"] != server["id"]:
        raise ApiError(409, "workspace_elsewhere")
    if ws is not None and ws["state"] == "stopped":
        raise ApiError(409, "workshop_stopped")
    if ws is not None and (busy := await WS.busy_job(tx, ws)) is not None:
        return WorkshopRun(
            job=str(busy["id"]),
            work_ref=w["ref"],
            state="working",
            turn=int(ws["turns"]),
            path=WS.path_of(w["ref"]),
            server=server["name"],
        )
    session = None
    if ws is not None and ws.get("session_id") is not None and ws["state"] != "failed":
        s = await WD.load(tx, ws["session_id"])
        session = s if s["state"] not in WD.FINAL else None
    extra = {
        "workspace": w["ref"],
        "hands": True,
        "model": MODEL,
        "permission_mode": PERMISSION_MODE,
        "allowed_tools": list(ALLOWED_TOOLS),
        "timeout_s": SESSION_TIMEOUT_S,
    }
    text = compose(w, who, brief, first=session is None)
    if session is None:
        s, job = await SS.open_session(
            tx,
            who,
            server=server,
            driver=who.code,
            title=(title or f"{w['ref']}: {w['title']}")[:300],
            brief=text,
            cwd=WS.path_of(w["ref"]),
            actor=("agent", who.code),
            work_ref=w["ref"],
            request_id=request_id,
            holding_driver=True,  # a driver of any company: the workshop is everyone's
            extra_args=extra,
            timeout_s=TURN_TIMEOUT_S,
        )
        if ws is None:
            ws = await tx.one(
                """INSERT INTO work.workspaces (company_id, work_id, work_ref, server_id,
                       session_id, state, turns, last_job_id)
                   VALUES (:co, :w, :ref, :s, :sess, 'starting', 1, :j) RETURNING *""",
                co=w["company_id"],
                w=w["id"],
                ref=w["ref"],
                s=server["id"],
                sess=s["id"],
                j=job["id"],
            )
        else:  # a failed (or finished) session: a fresh one in the same folder
            ws = await tx.one(
                """UPDATE work.workspaces SET session_id = :sess, state = 'starting',
                       turns = turns + 1, last_job_id = :j, note_fa = NULL, updated_at = now()
                   WHERE id = :id RETURNING *""",
                sess=s["id"],
                j=job["id"],
                id=ws["id"],
            )
    else:
        job = await SS.steer(
            tx, who, session, text, request_id=request_id, extra_args=extra,
            timeout_s=TURN_TIMEOUT_S,
        )  # fmt: skip
        ws = await tx.one("SELECT * FROM work.workspaces WHERE id = :id", id=ws["id"])  # type: ignore[index]
    if w["status"] == "queued":
        await W.set_status(tx, w, "in_progress", accepted_at=datetime.now(UTC))
    await W.event(
        tx, w, "workspace_turn", who,
        {"server": server["name"], "job": str(job["id"]), "turn": ws["turns"], "hands": True},
    )  # fmt: skip
    for co_id in dict.fromkeys((w["company_id"], server["company_id"])):
        await audit.record(
            tx,
            who,
            company_id=co_id,
            action="workshop.run",
            action_class="A2",
            target_kind="work",
            target_ref=w["ref"],
            summary=f"turn {ws['turns']} of {w['ref']} on the workshop "
            f"({server['company']}:{server['name']}); job {job['id']}",
            request_id=request_id,
        )
    await events.emit(
        tx, w["company"], "work.updated", w["ref"],
        {"workspace": "starting", "server": server["name"], "turn": ws["turns"], "hands": True},
    )  # fmt: skip
    return WorkshopRun(
        job=str(job["id"]),
        work_ref=w["ref"],
        state="starting",
        turn=int(ws["turns"]),
        path=WS.path_of(w["ref"]),
        server=server["name"],
    )
