"""⟨1.37⟩ Contract §59.9-§59.10 (prompt 38): the automations board, its health, the owner's day, the
calendar and an automation's audit; the one switch for every kind that is not a flow.

Everything that runs by itself, in one list (`board`):
- `flow` (§59.7): `growth.automations` of kind `flow`; its line's last run, the next occurrence
  and today's cost; opens `automation/<ref>`;
- `routine` (§50): a standing routine (kind `routine`, or `source.routine` as `routines.make`
  writes it); opens its session (`session/<order>`), else the automations of a sentence;
- `standing_publish` (§45): one per member whose publish word is `auto` (and one the owner
  switched off here, so he can switch it on again); ref `SP:<group>:<company>`; opens
  `groups/<key>`;
- `line` (§30): a scheduled production line that is no flow's; opens `lines/<ref>`;
- `rule` (§31.7): the automations of a sentence; `proposed` waits for its seal (`switchable:
  false`); opens the automations of a sentence;
- `archive` (§23.7): `archive.automations` (`AU-…`); opens `archive-settings/automations/<ref>`.

The health of the road (`health`) is read by code: n8n's last tick (`growth.flow_clock`), IG-Hub's
last answer (its newest finished `publish` job), each company's publish path (§44.5), the helpers'
browser (ChatGPT signed in, §21.13), AI Studio (its last answer, domain/speech_make.py) and the
workshop's last turn. Nothing technical is the owner's step (§34.4): a note says who does it.

Planned occurrences of a flow (`occurrences`) are computed here from its schedule (a fixed `at`, or
`best` → the account's best hour of §49, else the fixed one, else DEFAULT_AT; `days` or every
day) in the owner's zone; domain/flow_auto.py owns the flow's own clock (the two are unified at
integration).
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from functools import partial
from typing import Any, Literal
from uuid import UUID

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import automations as AU
from hq_api.domain import run_results as RR
from hq_api.domain.flow_shapes import (
    AuditLine,
    AutoCalendar,
    AutomationBoard,
    BoardItem,
    BoardLast,
    BoardToday,
    CalendarDay,
    CalendarEntry,
    DayItem,
    DayPublished,
    DaySummary,
    Health,
)
from hq_api.domain.gov_common import local_midnight, owner_tz, today, zone
from hq_api.errors import ApiError
from hq_api.principal import Principal

SP_REF = re.compile(r"^SP:([a-z][a-z0-9_]{1,40}):([A-Z][A-Z0-9]{1,9})$")
AT_REF = re.compile(r"^AT-[0-9]{4,}$")
LN_REF = re.compile(r"^LN-[0-9]{4,}$")
AU_REF = re.compile(r"^AU-[0-9]{4,}$")
REF = r"^(AT-[0-9]{4,}|LN-[0-9]{4,}|AU-[0-9]{4,}|SP:[a-z][a-z0-9_]{1,40}:[A-Z][A-Z0-9]{1,9}|N8:[a-z][a-z0-9_]{0,40})$"
CLOCK = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
DEFAULT_AT = "18:00"  # a `best` flow whose account has too few posts and no fixed hour
DAY_INDEX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
DAY_FA = {
    "SA": "شنبه", "SU": "یکشنبه", "MO": "دوشنبه", "TU": "سه‌شنبه", "WE": "چهارشنبه",
    "TH": "پنجشنبه", "FR": "جمعه",
}  # fmt: skip
N8N_QUIET = timedelta(minutes=10)
DAY_MIN, DAY_MAX = date(2020, 1, 1), date(2200, 12, 31)  # a day the calendar can name
CALENDAR_DAYS_MAX = 62
AHEAD = timedelta(days=15)
SYSTEM_FA = "سامانه"
OWNER_FA = "مدیر کل"
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
KIND_FA = {"reel": "ریلز", "post": "پست", "image": "پست", "carousel": "اسلاید", "story": "استوری"}
# a line run's state as the calendar says it
CalState = Literal["planned", "skipped", "running", "done", "failed"]
CAL_STATE: dict[str, CalState] = {
    "queued": "running", "running": "running", "waiting": "running", "done": "done",
    "failed": "failed", "skipped": "skipped", "cancelled": "skipped",
}  # fmt: skip
ARCHIVE_ON_FA = {
    "filed": "هر بار که سندی بایگانی شود",
    "sealed": "هر بار که سندی مُهر شود",
    "reminder_due": "وقتی یادآوری سررسید شود",
    "retention_due": "وقتی مدت نگهداری سر برسد",
    "hold_set": "وقتی سندی توقیف شود",
    "version_added": "هر بار که نسخه‌ی تازه‌ای اضافه شود",
}

# ------------------------------------------------------------- the day's words --
TODAY_FA = "امروز: {what}"
NOTHING_FA = "امروز چیزی منتشر نشد: {why}"
WENT_OUT_FA = "{kind} «{title}» منتشر شد"
NO_FLOW_FA = "هنوز اتوماسیون روشنی نیست"
WHY_OFF_FA = "خاموش است"
WHY_PAUSED_FA = "در مکث است"
WHY_LATER_FA = "نوبت امروز ساعت {at} است"
WHY_NONE_FA = "امروز نوبتی نداشت"
WHY_RUNNING_FA = "هنوز در حال ساخت است"
WHY_WAITING_FA = "منتظر مانده است"
WHY_FAILED_FA = "یک قدم انجام نشد"
WHY_SKIPPED_FA = "این نوبت رد شد"
SUMMARY_TITLE_FA = "خلاصه‌ی امروز اتوماسیون‌ها"
SUMMARY_KEPT = timedelta(days=8)  # a day's summary is looked for in the audit this far back
LATIN = re.compile(r"https?://\S+|[A-Za-z][A-Za-z0-9_.:/@-]*")

# --------------------------------------------------------------- the health --
N8N_OK_FA = "n8n هر دقیقه سر میزند"
N8N_IDLE_FA = "هنوز اتوماسیونی به n8n نیاز ندارد"
N8N_WARN_FA = "n8n خاموش است؛ هاب خودش اجرا کرد"
IGHUB_NONE_FA = "IG-Hub هنوز به هاب وصل نشده؛ تیم فنی وصلش میکند"
IGHUB_DOWN_FA = "IG-Hub جواب نمیدهد؛ تیم فنی پیگیری میکند"
IGHUB_FAILED_FA = "آخرین کار IG-Hub انجام نشد؛ تیم فنی پیگیری میکند"
IGHUB_OK_FA = "IG-Hub آخرین کارش را درست انجام داد"
IGHUB_IDLE_FA = "IG-Hub وصل است"
PATH_OK_FA = "مسیر انتشار همه‌ی شرکت‌ها آماده است"
PATH_IDLE_FA = "هنوز شرکتی خودکار منتشر نمیکند"
PATH_WARN_FA = "مسیر انتشار {names} هنوز آماده نیست؛ تیم فنی راهش می‌اندازد"
BROWSER_OK_FA = "مرورگر کمکی در ChatGPT وارد است"
BROWSER_WARN_FA = "مرورگر کمکی از ChatGPT بیرون افتاده؛ تیم فنی دوباره واردش میکند"
AISTUDIO_OK_FA = "گوینده در AI Studio وارد است"
AISTUDIO_IDLE_FA = "این روزها صدایی ساخته نشده؛ با اولین صدا معلوم میشود"
AISTUDIO_WARN_FA = "AI Studio از حساب بیرون افتاده؛ یک بار ورود لازم است"
WORKSHOP_NONE_FA = "کارگاه هنوز راه نیفتاده؛ کار تیم فنی است"
WORKSHOP_DOWN_FA = "کارگاه خاموش است؛ تیم فنی روشنش میکند"
WORKSHOP_FAILED_FA = "آخرین نوبت کارگاه کامل نشد"
WORKSHOP_OK_FA = "آخرین نوبت کارگاه انجام شد"
WORKSHOP_IDLE_FA = "کارگاه آماده است"
UNREAD_FA = "وضعیت این بخش خوانده نشد"

# ---------------------------------------------------------------- the audit --
ACTION_FA = {
    "automation.state": "روشن و خاموش",
    "automation.seal": "مُهر",
    "automation.propose": "پیشنهاد",
    "automation.routine": "ساخت روال",
    "automation.pause": "مکث",
    "automation.skip": "رد کردن یک نوبت",
    "automation.run_now": "اجرای همین حالا",
    "automation.patch": "تغییر تنظیمات",
    "automation.schedule": "ساعت",
    "automation.account": "حساب",
    "automation.story": "استوری",
    "automation.mode": "حالت انتشار",
    "automation.budget": "بودجه",
    "automation.replies": "جواب‌ها",
    "automation.title": "نام",
    "automation.made": "ساخته شد",
    "playbook.use": "به کار گرفتن کارگروه",
    "group.publish": "انتشار خودکار",
    "group.member": "عضویت در کارگروه",
    "line.state": "روشن و خاموش خط",
    "line.mode": "حالت خط",
    "line.update": "تغییر خط",
}
WORD_FA = {
    "on": "روشن", "off": "خاموش", "paused": "مکث", "proposed": "پیشنهادی", "auto": "خودکار",
    "ask": "هر بار بپرس", "active": "روشن", "retired": "خاموش", "draft": "پیش‌نویس",
    "true": "بله", "false": "نه", "fixed": "ساعت ثابت", "best": "بهترین ساعت",
}  # fmt: skip
SAFE_WORD = re.compile(r"^[@$0-9A-Za-z_.:+-]{1,40}$")


# ------------------------------------------------------------------ helpers --
def _obj(raw: Any) -> dict[str, Any]:
    got = json.loads(raw) if isinstance(raw, str) else raw
    return dict(got) if isinstance(got, dict) else {}


def _usd(v: Any) -> float:
    return round(float(v), 6) if isinstance(v, int | float | Decimal) else 0.0


def fa_num(n: int | float) -> str:
    return str(int(n)).translate(FA_DIGITS)


def _routine(row: dict[str, Any]) -> bool:
    return row.get("kind") == "routine" or bool(_obj(row.get("source")).get("routine"))


def check_day(d: date, field: str) -> None:
    if not DAY_MIN <= d <= DAY_MAX:
        raise ApiError(422, "validation_failed", fields={field: "a day from 2020 to 2200"})


def _when(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, date):
        return datetime.combine(v, time(12), UTC)
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


# -------------------------------------------------------- a flow's occurrences --
def occurrences(
    schedule: dict[str, Any], tz: str, start: datetime, end: datetime, clock: str
) -> list[datetime]:
    """The flow's publish times in [start, end): `clock` («HH:MM», the owner's zone) on each of
    its `days` (every day when it names none)."""
    m = CLOCK.fullmatch(clock or "")
    if m is None or end <= start:
        return []
    z = zone(tz)
    days = {DAY_INDEX[d] for d in schedule.get("days") or [] if d in DAY_INDEX}
    d, last = start.astimezone(z).date(), end.astimezone(z).date()
    out: list[datetime] = []
    for _ in range(400):
        if d > last:
            break
        if not days or d.weekday() in days:
            t = datetime.combine(d, time(int(m.group(1)), int(m.group(2))), z).astimezone(UTC)
            if start <= t < end:
                out.append(t)
        d += timedelta(days=1)
    return out


async def clock_of(tx: Tx, row: dict[str, Any], tz: str) -> str:
    """The flow's publish hour: `best` → the account's best hour (§49) once there is enough, else
    its fixed `at`, else DEFAULT_AT."""
    from hq_api.domain import best_hour as BH
    from hq_api.domain import session_publish as SPB

    sch = _obj(row.get("schedule"))
    at = str(sch.get("at") or "")
    fixed = at if CLOCK.fullmatch(at) else None
    if sch.get("mode") == "best":
        account = row.get("account")
        if not account:
            accounts = (await SPB._route(tx, row["company_id"]))["accounts"]
            account = accounts[0] if len(accounts) == 1 else None
        got = await BH.best(tx, row["company_id"], account, tz)
        if got.hour:
            return got.hour
    return fixed or DEFAULT_AT


def skip_days(raw: Any, tz: str) -> set[date]:
    """The owner's days a flow skips (each skip names its occurrence: a time, or a day)."""
    got = raw
    if isinstance(raw, str):
        try:
            got = json.loads(raw)
        except ValueError:
            got = []
    out: set[date] = set()
    z = zone(tz)
    for s in got if isinstance(got, list) else []:
        if isinstance(s, dict) and s.get("skip") is False:
            continue
        v = s.get("at") if isinstance(s, dict) else s
        text = str(v or "")
        if len(text) == 10:  # a day
            with contextlib.suppress(ValueError):
                out.add(date.fromisoformat(text))
            continue
        t = _when(v)
        if t is not None:
            out.add(t.astimezone(z).date())
    return out


def plans(row: dict[str, Any], at: datetime) -> bool:
    """Whether an occurrence at `at` is meant to run (on; paused only after its `until`)."""
    if row["state"] == "on":
        return True
    until = row.get("paused_until")
    return row["state"] == "paused" and until is not None and at >= until


def flow_when_fa(schedule: dict[str, Any]) -> str:
    if str(schedule.get("when_fa") or "").strip():
        return str(schedule["when_fa"]).strip()
    days = [d for d in schedule.get("days") or [] if d in DAY_FA]
    every = "هر " + " و ".join(DAY_FA[d] for d in days) if days and len(days) < 7 else "هر روز"
    at = str(schedule.get("at") or "")
    if schedule.get("mode") == "best":
        return f"{every}، بهترین ساعت صفحه"
    return f"{every} ساعت {at}" if CLOCK.fullmatch(at) else every


async def next_of(
    tx: Tx, row: dict[str, Any], tz: str, now: datetime
) -> tuple[datetime | None, str]:
    """(the next occurrence that will run, the clock it runs at)."""
    if row["state"] not in ("on", "paused"):
        return None, ""
    clock = await clock_of(tx, row, tz)
    skips = skip_days(row.get("skips"), tz)
    z = zone(tz)
    for t in occurrences(_obj(row.get("schedule")), tz, now, now + AHEAD, clock):
        if plans(row, t) and t.astimezone(z).date() not in skips:
            return t, clock
    return None, clock


# ------------------------------------------------------------------ the rows --
FLOW_SQL = """
SELECT a.*, c.code AS company_code, c.name_fa AS company_fa, p.title_fa AS playbook_fa,
       l.id AS line_id
FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
LEFT JOIN owner.playbooks p ON p.ref = a.playbook
LEFT JOIN lines.lines l ON l.ref = a.line
WHERE a.kind = 'flow' AND (CAST(:co AS text) IS NULL OR c.code = :co)
ORDER BY a.created_at"""


async def flows(tx: Tx, company: str | None = None) -> list[dict[str, Any]]:
    return await tx.all(FLOW_SQL, co=company)


async def _last_runs(tx: Tx, line_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    if not line_ids:
        return {}
    rows = await tx.all(
        """SELECT DISTINCT ON (line_id) line_id, id, ref, state, at, ended_at, note_fa
           FROM lines.runs WHERE line_id = ANY(:ids) AND dry = false
           ORDER BY line_id, at DESC, ref DESC""",
        ids=line_ids,
    )
    return {r["line_id"]: r for r in rows}


async def _cost_since(tx: Tx, line_ids: list[UUID], since: datetime) -> dict[UUID, float]:
    if not line_ids:
        return {}
    rows = await tx.all(
        """SELECT line_id, sum(usd_equiv) AS usd FROM lines.runs
           WHERE line_id = ANY(:ids) AND at >= :t GROUP BY line_id""",
        ids=line_ids,
        t=since,
    )
    return {r["line_id"]: _usd(r["usd"]) for r in rows}


def _last(run: dict[str, Any] | None) -> BoardLast | None:
    if run is None:
        return None
    return BoardLast(
        at=run["ended_at"] or run["at"], state=run["state"], note_fa=run["note_fa"] or ""
    )


async def _flow_items(
    tx: Tx, company: str | None, tz: str, now: datetime, day_start: datetime
) -> list[BoardItem]:
    rows = await flows(tx, company)
    ids = [r["line_id"] for r in rows if r["line_id"] is not None]
    last, cost = await _last_runs(tx, ids), await _cost_since(tx, ids, day_start)
    out = []
    for r in rows:
        nxt, _ = await next_of(tx, r, tz, now)
        out.append(
            BoardItem(
                ref=r["ref"], kind="flow", title_fa=r.get("title_fa") or r["sentence_fa"], company=r["company_code"],
                company_fa=r["company_fa"], playbook=r["playbook"], playbook_fa=r["playbook_fa"],
                version=r["playbook_version"], when_fa=flow_when_fa(_obj(r["schedule"])),
                state=r["state"], switchable=r["state"] != "proposed",
                last=_last(last.get(r["line_id"])), next_at=nxt,
                cost_today_usd=cost.get(r["line_id"], 0.0), opens=f"automation/{r['ref']}",
            )
        )  # fmt: skip
    return out


def _rule_when(rule: dict[str, Any]) -> str:
    t = rule.get("trigger") or {}
    try:
        if t.get("kind") == "schedule":
            return AU.when_fa(str(t.get("rrule") or ""))
        if t.get("kind") == "event":
            return f"هر بار که {AU.EVENT_TYPES[t['type']]}"
        if t.get("kind") == "metric":
            return "روزی که " + AU.metric_fa(t)
    except Exception:  # noqa: BLE001 - shown without its time rather than not at all
        return ""
    return ""


async def _rule_items(tx: Tx, company: str | None, tz: str) -> list[BoardItem]:
    from hq_api.domain import routines as RT

    rows = await tx.all(
        """SELECT a.*, c.code AS company_code, c.name_fa AS company_fa FROM growth.automations a
           JOIN core.companies c ON c.id = a.company_id
           WHERE a.kind <> 'flow'
             AND (CAST(:co AS text) IS NULL OR (a.scope = 'company' AND c.code = :co))
           ORDER BY a.created_at""",
        co=company,
    )
    out = []
    for r in rows:
        rule = _obj(r["rule"])
        mine = r["scope"] == "company"
        routine = _routine(r)
        rrule = str((rule.get("trigger") or {}).get("rrule") or "")
        nxt = RT.next_run(rrule, tz) if rrule and r["state"] == "on" else None
        failed = int(r["failures_in_row"] or 0) > 0
        last = (
            BoardLast(at=r["last_run_at"], state="failed" if failed else "done",
                      note_fa=r["last_error_fa"] or "")
            if r["last_run_at"] is not None
            else None
        )  # fmt: skip
        order = _obj(r.get("source")).get("order")
        out.append(
            BoardItem(
                ref=r["ref"], kind="routine" if routine else "rule", title_fa=r["sentence_fa"],
                company=r["company_code"] if mine else None,
                company_fa=r["company_fa"] if mine else None, when_fa=_rule_when(rule),
                state=r["state"], switchable=r["state"] != "proposed", last=last, next_at=nxt,
                opens=f"session/{order}" if routine and order else "automations/sentence",
            )
        )  # fmt: skip
    return out


def _sp_when(rule: dict[str, Any]) -> str:
    to = f" در @{rule['account']}" if rule.get("account") else ""
    if rule.get("best"):
        return f"در بهترین ساعت صفحه{to}"
    if rule.get("at"):
        return f"ساعت {rule['at']}{to}"
    return f"همین که بسته آماده شد{to}"


SP_STATE = {
    "published": "done", "failed": "failed", "scheduled": "running", "publishing": "running",
    "waiting_seal": "waiting", "cancelled": "cancelled",
}  # fmt: skip
SP_NOTE = {"published": "منتشر شد", "failed": "منتشر نشد", "scheduled": "زمان‌بندی شد"}


async def _standing_items(tx: Tx, company: str | None) -> list[BoardItem]:
    from hq_api.domain import session_publish as SPB

    rows = await tx.all(
        """SELECT g.key, g.title_fa, m.publish, m.state AS member_state, c.code, c.name_fa
           FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
           JOIN core.companies c ON c.id = m.company_id
           WHERE (m.publish ->> 'mode' = 'auto' OR m.publish ? 'off')
             AND (CAST(:co AS text) IS NULL OR c.code = :co)
           ORDER BY g.key, c.code""",
        co=company,
    )
    out = []
    for r in rows:
        raw = _obj(r["publish"])
        rule = SPB.rule_of(raw)
        on = rule["mode"] == "auto"
        shown = rule if on else SPB.rule_of(raw.get("off") or {})
        job = await tx.first(
            f"""SELECT {SPB.JOB_COLS} FROM infra.server_jobs j
                WHERE j.kind = 'publish' AND j.args -> 'standing' ->> 'group' = :g
                  AND j.args -> 'session' ->> 'company' = :co
                ORDER BY j.created_at DESC LIMIT 1""",  # noqa: S608 - columns from code
            g=r["key"], co=r["code"],
        )  # fmt: skip
        last = None
        if job is not None:
            v = SPB.view(dict(job))
            last = BoardLast(at=v.published_at or job["finished_at"] or job["created_at"],
                             state=SP_STATE.get(v.state, v.state),
                             note_fa=SP_NOTE.get(v.state, ""))  # fmt: skip
        state: Literal["on", "off", "paused"] = (
            ("paused" if r["member_state"] == "paused" else "on") if on else "off"
        )
        out.append(
            BoardItem(
                ref=f"SP:{r['key']}:{r['code']}", kind="standing_publish",
                title_fa=f"انتشار خودکار «{r['title_fa']}»", company=r["code"],
                company_fa=r["name_fa"], when_fa=_sp_when(shown), state=state, last=last,
                opens=f"groups/{r['key']}",
            )
        )  # fmt: skip
    return out


async def _line_items(tx: Tx, company: str | None, tz: str, day_start: datetime) -> list[BoardItem]:
    from hq_api.lines import store as LS

    rows = await tx.all(
        """SELECT l.id, l.ref, l.title_fa, l.schedule, l.state, c.code, c.name_fa
           FROM lines.lines l JOIN core.companies c ON c.id = l.company_id
           WHERE l.schedule IS NOT NULL AND (CAST(:co AS text) IS NULL OR c.code = :co)
             AND NOT EXISTS (SELECT 1 FROM growth.automations a
                             WHERE a.kind = 'flow' AND a.line = l.ref)
           ORDER BY l.created_at""",
        co=company,
    )
    ids = [r["id"] for r in rows]
    last, cost = await _last_runs(tx, ids), await _cost_since(tx, ids, day_start)
    out = []
    for r in rows:
        try:
            when = AU.when_fa(str(r["schedule"]))
        except Exception:  # noqa: BLE001 - shown without its time rather than not at all
            when = ""
        out.append(
            BoardItem(
                ref=r["ref"], kind="line", title_fa=r["title_fa"], company=r["code"],
                company_fa=r["name_fa"], when_fa=when, state="on" if r["state"] == "on" else "off",
                last=_last(last.get(r["id"])), next_at=LS.next_at(r, tz),
                cost_today_usd=cost.get(r["id"], 0.0), opens=f"lines/{r['ref']}",
            )
        )  # fmt: skip
    return out


async def _archive_items(tx: Tx) -> list[BoardItem]:
    from hq_api.archive import clearance as CL

    await CL.full(tx)
    rows = await tx.all(
        """SELECT a.ref, a.title_fa, a.on_event, a.status,
                  (SELECT x.at FROM archive.automation_runs x WHERE x.automation_id = a.id
                   ORDER BY x.at DESC LIMIT 1) AS last_at,
                  (SELECT x.outcome FROM archive.automation_runs x WHERE x.automation_id = a.id
                   ORDER BY x.at DESC LIMIT 1) AS last_outcome
           FROM archive.automations a ORDER BY a.ref"""
    )
    return [
        BoardItem(
            ref=r["ref"], kind="archive", title_fa=r["title_fa"],
            when_fa=ARCHIVE_ON_FA.get(r["on_event"], ""),
            state="on" if r["status"] == "active" else "off",
            last=BoardLast(at=r["last_at"], state=r["last_outcome"]) if r["last_at"] else None,
            opens=f"archive-settings/automations/{r['ref']}",
        )
        for r in rows
    ]  # fmt: skip


async def board_today(tx: Tx, day_start: datetime) -> BoardToday:
    """Today's runs of every line (flows and plain lines), what went out (the runs' publications
    and the standing word's), and their cost."""
    row = await tx.first(
        """SELECT count(*) AS runs, COALESCE(sum(usd_equiv), 0) AS usd,
                  COALESCE(sum(jsonb_array_length(published)), 0) AS published
           FROM lines.runs WHERE at >= :t AND dry = false""",
        t=day_start,
    )
    standing = await tx.scalar(
        """SELECT count(*) FROM infra.server_jobs j
           WHERE j.kind = 'publish' AND j.state = 'done' AND j.args ? 'standing'
             AND j.finished_at >= :t AND NOT (j.args -> 'meta' ? 'check')
             AND NOT (j.args -> 'meta' ? 'cancel')""",
        t=day_start,
    )
    return BoardToday(
        runs=int(row["runs"] if row else 0),
        published=int(row["published"] if row else 0) + int(standing or 0),
        cost_usd=_usd(row["usd"] if row else 0),
    )


async def board(
    tx: Tx, hub: Any, company: str | None = None, kind: str | None = None
) -> AutomationBoard:
    """§59.10 everything that runs by itself, with the road's health and today's figures."""
    tz = await owner_tz(tx)
    now = datetime.now(UTC)
    start = local_midnight(today(tz, now), tz)
    items: list[BoardItem] = []
    if kind in (None, "n8n"):
        # ⟨2026-11-14⟩ the n8n flows (domain/flows.py), each with its steps on its page
        from hq_api.domain import flow_view as FV

        items += await FV.board_items(tx, hub, company)
    if kind in (None, "flow"):
        items += await _flow_items(tx, company, tz, now, start)
    if kind in (None, "routine", "rule"):
        items += [x for x in await _rule_items(tx, company, tz) if kind in (None, x.kind)]
    if kind in (None, "standing_publish"):
        items += await _standing_items(tx, company)
    if kind in (None, "line"):
        items += await _line_items(tx, company, tz, start)
    if kind in (None, "archive") and company is None:
        items += await _archive_items(tx)
    return AutomationBoard(
        items=items, health=await health(tx, hub, now), today=await board_today(tx, start)
    )


# ---------------------------------------------------------------- the health --
async def _n8n(tx: Tx, now: datetime) -> Health:
    tick = await tx.scalar("SELECT max(last_tick_at) FROM growth.flow_clock")
    if tick is not None and tick > now - N8N_QUIET:
        return Health(key="n8n", state="ok", note_fa=N8N_OK_FA)
    on = await tx.scalar(
        "SELECT count(*) FROM growth.automations WHERE kind = 'flow' AND state IN ('on', 'paused')"
    )
    if not on:
        return Health(key="n8n", state="ok", note_fa=N8N_IDLE_FA)
    return Health(key="n8n", state="warn", note_fa=N8N_WARN_FA)


async def _ighub(tx: Tx) -> Health:
    from hq_api.domain import connections as CN
    from hq_api.domain import servers as SV

    where = CN.ig_hub()
    try:
        srv = await SV.load_server(tx, where["server"], company=where["company"])
    except ApiError:
        return Health(key="ighub", state="warn", note_fa=IGHUB_NONE_FA)
    if SV.state_of(srv) != "online":
        return Health(key="ighub", state="down", note_fa=IGHUB_DOWN_FA)
    last = await tx.first(
        """SELECT state FROM infra.server_jobs
           WHERE server_id = :s AND kind = 'publish' AND state IN ('done', 'failed')
           ORDER BY finished_at DESC NULLS LAST LIMIT 1""",
        s=srv["id"],
    )
    if last is None:
        return Health(key="ighub", state="ok", note_fa=IGHUB_IDLE_FA)
    if last["state"] == "failed":
        return Health(key="ighub", state="warn", note_fa=IGHUB_FAILED_FA)
    return Health(key="ighub", state="ok", note_fa=IGHUB_OK_FA)


async def _publish_path(tx: Tx) -> Health:
    from hq_api.domain import session_publish as SPB

    rows = await tx.all(
        """SELECT DISTINCT c.id, c.name_fa, c.code FROM core.companies c
           WHERE EXISTS (SELECT 1 FROM growth.automations a WHERE a.company_id = c.id
                           AND a.kind = 'flow' AND a.state IN ('on', 'paused'))
              OR EXISTS (SELECT 1 FROM growth.memberships m WHERE m.company_id = c.id
                           AND m.publish ->> 'mode' = 'auto')
           ORDER BY c.code"""
    )
    if not rows:
        return Health(key="publish_path", state="ok", note_fa=PATH_IDLE_FA)
    missing = [
        r["name_fa"] or r["code"] for r in rows if not (await SPB._route(tx, r["id"]))["ready"]
    ]
    if missing:
        return Health(
            key="publish_path", state="warn", note_fa=PATH_WARN_FA.format(names="، ".join(missing))
        )
    return Health(key="publish_path", state="ok", note_fa=PATH_OK_FA)


async def _browser(tx: Tx) -> Health:
    web = await tx.scalar("SELECT web_state FROM substitutes.players WHERE player = 'gpt'")
    if web == "signed_in":
        return Health(key="helpers_browser", state="ok", note_fa=BROWSER_OK_FA)
    return Health(key="helpers_browser", state="warn", note_fa=BROWSER_WARN_FA)


async def _aistudio(tx: Tx) -> Health:
    from hq_api.domain import speech_make as SM

    got = (await SM.speech_state(tx))["aistudio"]
    if got == "signed_in":
        return Health(key="aistudio", state="ok", note_fa=AISTUDIO_OK_FA)
    if got == "signed_out":
        return Health(key="aistudio", state="warn", note_fa=AISTUDIO_WARN_FA)
    return Health(key="aistudio", state="ok", note_fa=AISTUDIO_IDLE_FA)


async def _workshop(tx: Tx) -> Health:
    from hq_api.domain import hands
    from hq_api.domain import servers as SV

    srv = await hands.workshop_server(tx)
    if srv is None:
        return Health(key="workshop", state="warn", note_fa=WORKSHOP_NONE_FA)
    if SV.state_of(srv) != "online":
        return Health(key="workshop", state="down", note_fa=WORKSHOP_DOWN_FA)
    last = await tx.first(
        """SELECT state FROM infra.server_jobs
           WHERE server_id = :s AND kind = 'claude' AND state IN ('done', 'failed')
           ORDER BY finished_at DESC NULLS LAST LIMIT 1""",
        s=srv["id"],
    )
    if last is None:
        return Health(key="workshop", state="ok", note_fa=WORKSHOP_IDLE_FA)
    if last["state"] == "failed":
        return Health(key="workshop", state="warn", note_fa=WORKSHOP_FAILED_FA)
    return Health(key="workshop", state="ok", note_fa=WORKSHOP_OK_FA)


async def health(tx: Tx, hub: Any, now: datetime | None = None) -> list[Health]:
    """The road a flow takes, read by code; one part that cannot be read never hides the rest."""
    del hub
    now = now or datetime.now(UTC)
    out = []
    parts: list[tuple[str, Callable[[], Awaitable[Health]]]] = [
        ("n8n", partial(_n8n, tx, now)), ("ighub", partial(_ighub, tx)),
        ("publish_path", partial(_publish_path, tx)), ("helpers_browser", partial(_browser, tx)),
        ("aistudio", partial(_aistudio, tx)), ("workshop", partial(_workshop, tx)),
    ]  # fmt: skip
    for key, part in parts:
        try:
            async with tx.conn.begin_nested():
                out.append(await part())
        except Exception:  # noqa: BLE001 - this part is not readable now; the others are
            out.append(Health.model_validate({"key": key, "state": "warn", "note_fa": UNREAD_FA}))
    return out


# --------------------------------------------------------------- the switch --
async def _emit_changed(tx: Tx, company: str, ref: str, state: str) -> None:
    await events.emit(tx, company, "automation.changed", ref, {"ref": ref, "state": state})


async def _switch_routine(tx: Tx, row: dict[str, Any], state: str, who: Principal) -> None:
    before = row["state"]
    if before == "proposed":
        raise ApiError(409, "validation_failed", f"{row['ref']} is not sealed yet")
    if before != state:
        await tx.exec(
            """UPDATE growth.automations SET state = :st, failures_in_row = 0,
                   last_error_fa = CASE WHEN :st = 'on' THEN NULL ELSE last_error_fa END,
                   off_reason = CASE WHEN :st = 'off' THEN 'owner' ELSE NULL END,
                   event_cursor = CASE WHEN :st = 'on' AND state = 'off' THEN :cur
                                       ELSE event_cursor END,
                   updated_at = now() WHERE id = :id""",
            st=state, cur=await AU.max_outbox(tx), id=row["id"],
        )  # fmt: skip
    await audit.record(
        tx, who, company_id=row["company_id"], action="automation.state", action_class="A2",
        target_kind="automation", target_ref=row["ref"], summary=f"{before} -> {state}",
    )  # fmt: skip
    await _emit_changed(tx, row["company_code"], row["ref"], state)


async def _switch_standing(
    tx: Tx, hub: Any, key: str, code: str, state: str, who: Principal
) -> None:
    """Off is «هر بار بپرس» (`ask`, §45.1); the word given before is kept under `off`, so on
    gives it back (its account, story and hour; `since` from now)."""
    from hq_api.domain import session_publish as SPB

    company = await hub.companies.by_code(code)
    g = await tx.one("SELECT id FROM growth.groups WHERE key = :k", k=key)
    m = await tx.one(
        """SELECT publish FROM growth.memberships WHERE group_id = :g AND company_id = :co
           FOR UPDATE""",
        g=g["id"], co=company.id,
    )  # fmt: skip
    raw = _obj(m["publish"])
    before = SPB.rule_of(raw)["mode"]
    after = "auto" if state == "on" else "ask"
    if after == "auto" and before != "auto":
        prev = SPB.rule_of(raw.get("off") or {})
        await SPB.set_rule(
            tx, g["id"], company.id, mode="auto", account=prev["account"], story=prev["story"],
            at=prev["at"], best=prev["best"],
        )  # fmt: skip
    elif after == "ask" and before == "auto":
        kept = {
            k: raw[k] for k in ("mode", "account", "story", "at", "best", "since", "by") if k in raw
        }
        await SPB.set_rule(tx, g["id"], company.id, mode="ask")
        await tx.exec(
            """UPDATE growth.memberships
               SET publish = publish || jsonb_build_object('off', CAST(:p AS jsonb))
               WHERE group_id = :g AND company_id = :co""",
            p=json.dumps(kept, ensure_ascii=False), g=g["id"], co=company.id,
        )  # fmt: skip
    await audit.record(
        tx, who, company_id=company.id, action="group.publish", action_class="A3",
        target_kind="group", target_ref=f"{key}:{code}",
        summary=f"the owner's standing permission to publish, from the board: {before} -> {after}",
    )  # fmt: skip
    await events.emit(tx, code, "group.run", None, {"group": key, "publish": after})
    await _emit_changed(tx, code, f"SP:{key}:{code}", state)


async def _switch_line(tx: Tx, hub: Any, ref: str, state: str, who: Principal) -> None:
    from hq_api.lines import store as LS

    row = await LS.load(tx, ref, lock=True)
    target = "on" if state == "on" else "paused"
    await hub.policy.require(
        "lines",
        {"principal": who.opa(), "op": "line.state", "target": {"line": ref, "state": target},
         "context": {"step_up": False}},
    )  # fmt: skip
    before = row["state"]
    if before != target:
        row = await LS.set_state(tx, row, target)
    await audit.record(
        tx, who, company_id=row["company_id"], action="line.state", action_class="A2",
        target_kind="line", target_ref=ref, summary=f"{before} -> {target}",
    )  # fmt: skip
    await events.emit(
        tx, row["company"], "line.updated", ref, {"version": row["version"], "state": target}
    )
    await _emit_changed(tx, row["company"], ref, state)


async def _switch_archive(tx: Tx, hub: Any, ref: str, state: str, who: Principal) -> None:
    """On/off is its status (`active` · `retired`): no step-up, he sealed it once (§59.10)."""
    from hq_api.archive import clearance as CL

    await CL.full(tx)
    row = await tx.one(
        "SELECT id, company_id, status FROM archive.automations WHERE ref = :r FOR UPDATE", r=ref
    )
    target = "active" if state == "on" else "retired"
    if row["status"] != target:
        await tx.exec(
            "UPDATE archive.automations SET status = :s, updated_at = now() WHERE id = :id",
            s=target, id=row["id"],
        )  # fmt: skip
    await audit.record(
        tx, who, company_id=row["company_id"], action="automation.state", action_class="A2",
        target_kind="archive_automations", target_ref=ref, summary=f"{row['status']} -> {target}",
    )  # fmt: skip
    holding = await hub.companies.holding()
    await events.emit(tx, holding.code, "schema.changed", ref, {"part": "automations"})
    await _emit_changed(tx, holding.code, ref, state)


async def switch(tx: Tx, hub: Any, ref: str, state: str, who: Principal) -> bool:
    """The owner's switch on a board item of kind `routine`, `standing_publish` (`SP:<group>:<co>`),
    `line` (`LN-…`) or `archive` (`AU-…`): True when this module handled `ref`, False for a ref it
    does not know (a §31.7 rule then goes on as before)."""
    if state not in ("on", "off"):
        raise ApiError(422, "validation_failed", fields={"state": "on or off"})
    if (m := SP_REF.fullmatch(ref)) is not None:
        await _switch_standing(tx, hub, m.group(1), m.group(2), state, who)
        return True
    if LN_REF.fullmatch(ref):
        await _switch_line(tx, hub, ref, state, who)
        return True
    if AU_REF.fullmatch(ref):
        await _switch_archive(tx, hub, ref, state, who)
        return True
    if AT_REF.fullmatch(ref):
        row = await tx.first(
            """SELECT a.*, c.code AS company_code FROM growth.automations a
               JOIN core.companies c ON c.id = a.company_id WHERE a.ref = :r FOR UPDATE OF a""",
            r=ref,
        )
        if row is None or row["kind"] == "flow" or not _routine(row):
            return False
        await _switch_routine(tx, row, state, who)
        return True
    return False


# ------------------------------------------------------------ the owner's day --
async def topics_of(tx: Tx, run_ids: list[UUID]) -> dict[UUID, str]:
    """The topic each run's `topic` step chose (its title, else its text's first line)."""
    if not run_ids:
        return {}
    rows = await tx.all(
        """SELECT DISTINCT ON (run_id) run_id, output FROM lines.step_runs
           WHERE run_id = ANY(:ids) AND kind = 'topic' AND state = 'done'
           ORDER BY run_id, ended_at DESC NULLS LAST""",
        ids=run_ids,
    )
    out: dict[UUID, str] = {}
    for r in rows:
        o = _obj(r["output"])
        data = _obj(o.get("data"))
        text = str(data.get("title_fa") or data.get("topic_fa") or "").strip()
        if not text:
            text = next((x.strip() for x in str(o.get("text") or "").splitlines() if x.strip()), "")
        if text:
            out[r["run_id"]] = text[:120]
    return out


DAY_RUNS_SQL = """
SELECT r.id, r.ref, r.line_id, r.state, r.at, r.occurrence_at, r.published, r.note_fa,
       r.usd_equiv
FROM lines.runs r
WHERE r.line_id = ANY(:ids) AND r.dry = false
  AND COALESCE(r.occurrence_at, r.at) >= :a AND COALESCE(r.occurrence_at, r.at) < :b
ORDER BY COALESCE(r.occurrence_at, r.at), r.ref"""


def _why(row: dict[str, Any], run: dict[str, Any] | None, later: datetime | None, tz: str) -> str:
    """Why nothing of this flow went out today, plainly."""
    if run is not None:
        note = str(run["note_fa"] or "").strip()
        st = run["state"]
        if st in ("queued", "running"):
            return note or WHY_RUNNING_FA
        if st == "waiting":
            return note or WHY_WAITING_FA
        if st == "failed":
            return note or WHY_FAILED_FA
        if st in ("skipped", "cancelled"):
            return note or WHY_SKIPPED_FA
        if note:
            return note
    if row["state"] == "off":
        return WHY_OFF_FA
    if row["state"] == "paused":
        return WHY_PAUSED_FA
    if later is not None:
        return WHY_LATER_FA.format(
            at=later.astimezone(zone(tz)).strftime("%H:%M").translate(FA_DIGITS)
        )
    return WHY_NONE_FA


def persian_only(text: str) -> str:
    """The notification's words: no Latin word and no link (the notifier would drop them
    mid-sentence), no empty «»."""
    out = LATIN.sub("", text)
    out = re.sub(r"«\s*»", "", out)
    out = re.sub(r"\s+([،؛:»])", r"\1", re.sub(r"(«)\s+", r"\1", out))
    return re.sub(r"\s{2,}", " ", out).strip()


def _sum(values: list[int | None]) -> int | None:
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _went_out(title: str, kind: str, item: DayItem) -> str:
    parts = [WENT_OUT_FA.format(kind=KIND_FA.get(kind, "پست"), title=title)]
    for n, word in ((item.comments, "کامنت"), (item.dms_sent, "دایرکت"), (item.clicks, "کلیک")):
        if n is not None:
            parts.append(f"{fa_num(n)} {word}")
    return "، ".join(parts)


async def day_summary(tx: Tx, day: date | None = None) -> DaySummary:
    """§59.9 the owner's day (his zone): each flow's runs of that day, what went out, its figures
    and cost, and one line for all of them."""
    tz = await owner_tz(tx)
    now = datetime.now(UTC)
    d = day or today(tz, now)
    check_day(d, "day")
    a, b = local_midnight(d, tz), local_midnight(d + timedelta(days=1), tz)
    rows = await flows(tx)
    ids = [r["line_id"] for r in rows if r["line_id"] is not None]
    runs = await tx.all(DAY_RUNS_SQL, ids=ids, a=a, b=b) if ids else []
    results = await RR.results_of(tx, [r["id"] for r in runs])
    topics = await topics_of(tx, [r["id"] for r in runs])
    items: list[DayItem] = []
    clauses: list[str] = []
    reasons: list[str] = []
    for row in rows:
        mine = [r for r in runs if r["line_id"] == row["line_id"]]
        if not mine and row["state"] == "off":
            continue
        out_runs = [r for r in mine if RR.entries(r["published"])]
        published: list[DayPublished] = []
        for r in out_runs:
            res = results.get(r["id"])
            for p in RR.entries(r["published"]):
                url = RR.permalink_of(p) or (
                    (res.story_permalink if p.get("kind") == "story" else res.permalink)
                    if res is not None
                    else None
                )
                if url:
                    published.append(DayPublished(kind=str(p.get("kind") or "post"), url=url))
        figs = [results[r["id"]] for r in out_runs if r["id"] in results]
        last = mine[-1] if mine else None
        later = None
        if not mine and d == today(tz, now) and row["state"] == "on":
            nxt, _ = await next_of(tx, row, tz, now)
            later = nxt if nxt is not None and nxt < b else None
        item = DayItem(
            automation=row["ref"],
            title_fa=(row.get("title_fa") or row["sentence_fa"]),
            company_fa=row["company_fa"] or "",
            state=last["state"] if last else ("planned" if later else row["state"]),
            published=published,
            comments=_sum([f.comments for f in figs]), dms_sent=_sum([f.dms_sent for f in figs]),
            clicks=_sum([f.clicks for f in figs]),
            cost_usd=round(sum(_usd(r["usd_equiv"]) for r in mine), 6) if mine else None,
            note_fa="" if out_runs else _why(row, last, later, tz),
        )  # fmt: skip
        items.append(item)
        if out_runs:
            first = out_runs[-1]
            post, story = RR.main_entry(first["published"])
            kind = str((post or story or {}).get("kind") or "post")
            title = topics.get(first["id"]) or (row.get("title_fa") or row["sentence_fa"])
            clauses.append(_went_out(title, kind, item))
        else:
            reasons.append(f"«{row.get('title_fa') or row['sentence_fa']}» {item.note_fa}")
    if clauses:
        line = TODAY_FA.format(what="؛ ".join(clauses + reasons))
    elif reasons:
        why = reasons[0].split("» ", 1)[1] if len(reasons) == 1 else "؛ ".join(reasons)
        line = NOTHING_FA.format(why=why)
    else:
        line = NOTHING_FA.format(why=NO_FLOW_FA)
    return DaySummary(
        day=d.isoformat(), line_fa=line, items=items,
        cost_usd=round(sum(i.cost_usd or 0.0 for i in items), 6),
    )  # fmt: skip


async def send_summary(hub: Any, day: date | None = None) -> tuple[DaySummary, bool]:
    """n8n's 21:30 call: ONE notification of the day (and the stream's `automation.summary`); a
    second call of the same day sends nothing (False)."""
    from hq_api.domain import notify

    holding = await hub.companies.holding()
    pushed: list[UUID] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
        d = day or today(tz)
        await tx.exec(
            "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"automation.summary:{d}"
        )
        summary = await day_summary(tx, d)
        sent = await tx.scalar(
            """SELECT 1 FROM audit.entries WHERE company_id = :co AND at >= :t
                 AND action = 'automation.summary' AND target_ref = :d LIMIT 1""",
            co=holding.id, t=datetime.now(UTC) - SUMMARY_KEPT, d=d.isoformat(),
        )  # fmt: skip
        if sent:
            return summary, False
        row = await notify.raise_notification(
            tx, company_id=holding.id, company_code=holding.code, level="report",
            title_fa=SUMMARY_TITLE_FA, body_fa=persian_only(summary.line_fa), link_kind="automation",
            source_kind="system", source_code="automations", domain="business", category="news",
        )  # fmt: skip
        if row.get("push_now"):
            pushed.append(row["id"])
        await audit.record(
            tx, Principal(kind="service", code="n8n", role="service"), company_id=holding.id,
            action="automation.summary", action_class="A1", target_kind="automation_day",
            target_ref=d.isoformat(), summary=f"the day's summary, {len(summary.items)} flow(s)",
        )  # fmt: skip
        await events.emit(
            tx, holding.code, "automation.summary", None,
            {"day": d.isoformat(), "line_fa": summary.line_fa},
        )  # fmt: skip
    if pushed:
        await notify.deliver_pending(hub, pushed)
    return summary, True


# ------------------------------------------------------------- the calendar --
async def calendar(
    tx: Tx, start_day: date, end_day: date, company: str | None = None
) -> AutoCalendar:
    """§59.10 each flow's days from `start_day` to `end_day` (both in, the owner's zone): its runs
    with their states, and its planned occurrences ahead (`skipped` when the owner skipped one)."""
    check_day(start_day, "from")
    check_day(end_day, "to")
    if end_day < start_day or (end_day - start_day).days >= CALENDAR_DAYS_MAX:
        raise ApiError(
            422, "validation_failed", fields={"to": f"from..to, at most {CALENDAR_DAYS_MAX} days"}
        )
    tz = await owner_tz(tx)
    z = zone(tz)
    now = datetime.now(UTC)
    a, b = local_midnight(start_day, tz), local_midnight(end_day + timedelta(days=1), tz)
    rows = await flows(tx, company)
    ids = [r["line_id"] for r in rows if r["line_id"] is not None]
    runs = await tx.all(DAY_RUNS_SQL, ids=ids, a=a, b=b) if ids else []
    topics = await topics_of(tx, [r["id"] for r in runs])
    days: dict[date, list[CalendarEntry]] = {}
    for row in rows:
        mine = [r for r in runs if r["line_id"] == row["line_id"]]
        ran = set()
        for r in mine:
            at = r["occurrence_at"] or r["at"]
            ran.add(at.astimezone(z).date())
            days.setdefault(at.astimezone(z).date(), []).append(
                CalendarEntry(
                    ref=row["ref"], at=at, title_fa=(row.get("title_fa") or row["sentence_fa"]),
                    company_fa=row["company_fa"] or "", topic_fa=topics.get(r["id"]),
                    state=CAL_STATE.get(r["state"], "done"),
                )
            )  # fmt: skip
        if row["state"] not in ("on", "paused"):
            continue
        clock = await clock_of(tx, row, tz)
        skips = skip_days(row.get("skips"), tz)
        for t in occurrences(_obj(row["schedule"]), tz, max(a, now), b, clock):
            local = t.astimezone(z).date()
            if local in ran or not plans(row, t):
                continue
            days.setdefault(local, []).append(
                CalendarEntry(
                    ref=row["ref"], at=t, title_fa=(row.get("title_fa") or row["sentence_fa"]),
                    company_fa=row["company_fa"] or "",
                    state="skipped" if local in skips else "planned",
                )
            )  # fmt: skip
    out = []
    d = start_day
    while d <= end_day:
        out.append(
            CalendarDay(day=d.isoformat(), items=sorted(days.get(d, []), key=lambda e: e.at))
        )
        d += timedelta(days=1)
    return AutoCalendar(days=out)


# ---------------------------------------------------------------- the audit --
def _word(w: str) -> str | None:
    return WORD_FA.get(w) or (w if SAFE_WORD.fullmatch(w) else None)


def summary_fa(action: str, summary: str) -> str:
    """An audit row as the owner reads it: what changed, and «from → to» when the row says it in
    words this list knows (an English sentence is never shown)."""
    label = ACTION_FA.get(action, "تغییر")
    text = summary.strip()
    tail = text.rsplit(":", 1)[-1] if "->" in text else text
    if "->" in tail:
        before, after = (_word(x.strip()) for x in tail.split("->", 1))
        if before and after:
            return f"{label}: از {before} به {after}"
    elif text in WORD_FA:
        return f"{label}: {WORD_FA[text]}"
    return label


async def _subject(tx: Tx, hub: Any, ref: str) -> tuple[list[str], list[UUID], datetime]:
    """(the target refs its audit rows name, the companies they are on, since when)."""
    holding = await hub.companies.holding()
    if (m := SP_REF.fullmatch(ref)) is not None:
        company = await hub.companies.by_code(m.group(2))
        row = await tx.one(
            """SELECT m.joined_at FROM growth.memberships m JOIN growth.groups g ON g.id = m.group_id
               WHERE g.key = :k AND m.company_id = :co""",
            k=m.group(1), co=company.id,
        )  # fmt: skip
        return [ref, f"{m.group(1)}:{m.group(2)}"], [company.id], row["joined_at"]
    if LN_REF.fullmatch(ref):
        row = await tx.one("SELECT company_id, created_at FROM lines.lines WHERE ref = :r", r=ref)
        return [ref], [row["company_id"]], row["created_at"]
    if AU_REF.fullmatch(ref):
        from hq_api.archive import clearance as CL

        await CL.full(tx)
        row = await tx.one("SELECT created_at FROM archive.automations WHERE ref = :r", r=ref)
        return [ref], [holding.id], row["created_at"]
    if AT_REF.fullmatch(ref):
        row = await tx.one(
            "SELECT company_id, created_at, line FROM growth.automations WHERE ref = :r", r=ref
        )
        return [ref], [row["company_id"], holding.id], row["created_at"]
    from hq_api.domain import flow_view as FV

    if (flow := FV.flow_of(ref)) is not None:
        company = await hub.companies.by_code(flow.company)
        return [ref], [company.id, holding.id], datetime(2026, 11, 13, tzinfo=UTC)
    raise ApiError(404, "not_found", f"no automation {ref}")


async def audit_of(tx: Tx, hub: Any, ref: str, limit: int = 50) -> list[AuditLine]:
    """§59.10 every change of one automation (its switch, hour, account, mode, budget, replies),
    newest first, from the audit log."""
    refs, companies, since = await _subject(tx, hub, ref)
    rows = await tx.all(
        """SELECT e.at, e.actor_kind, e.actor_code, e.action, e.summary,
                  emp.title_fa AS actor_fa
           FROM audit.entries e LEFT JOIN core.employees emp
             ON e.actor_kind = 'agent' AND emp.code = e.actor_code
           WHERE e.company_id = ANY(:cos) AND e.at >= :since
             AND (e.target_ref = ANY(:refs) OR (e.action = 'playbook.use' AND e.summary LIKE :like))
           ORDER BY e.seq DESC LIMIT :n""",
        cos=companies, since=since - timedelta(minutes=5), refs=refs, like=f"%{ref}%", n=limit,
    )  # fmt: skip
    out = []
    for r in rows:
        who = (
            OWNER_FA
            if r["actor_kind"] == "owner"
            else (r["actor_fa"] or r["actor_code"])
            if r["actor_kind"] == "agent"
            else SYSTEM_FA
        )
        out.append(
            AuditLine(
                at=r["at"],
                who_fa=who,
                action=r["action"],
                summary_fa=summary_fa(r["action"], str(r["summary"] or "")),
            )
        )
    return out
