"""An automation from one sentence (contract §31.7 ⟨1.13⟩).

Rule first, model last. The owner writes one Persian sentence; ONE router call
(task class `automation_compile`, a mid model, a low token cap, a strict JSON
schema) translates it into `{trigger, conditions, actions}`. Nothing the model
says runs unchecked:

- `validate_rule` is code: only the allow-listed triggers (`schedule` RRULE,
  `event` of a known stream type, `metric` of a connection key) and actions
  (`work.create`, `line.run`, `line.pause`, `notify.owner`, `notify.lead`,
  `ad.pause`, `n8n.run`) with their own arguments survive; anything else is
  refused at compile time with a plain Persian reason.
- `preview_fa` is built by code from the validated rule, so the owner reads what
  will really run, never the model's own description.
- ⟨2026-11-07⟩ **a role never refuses a rule.** `work.create.role` as a model writes it («نویسنده»,
  `scriptwriter@PC`, `PC-SCRIPT`, `Scriptwriter`, `content writer`) is normalised by code against the
  company's real roles (`Roles`: the charters its active employees hold and its departments' teams,
  the charter library's titles): an employee code is that employee's role, `role@CODE` is the role,
  a Persian or English title is the charter with that title; a role nobody in the company holds goes
  to the matching department's manager, else the CEO, and the preview says so. The owner (2026-11-07)
  pressed «اجرا» three times on a «نقش کارمند درست نیست» for a valid intention; never again.
- Every refusal of another field names the field and what is allowed, in one plain line.
- Nothing runs before the owner's seal (🔏 `automation.seal`); a sealed
  automation's sentence and rule never change (a trigger in the database).
- Running is code: `tick` (schedules and metrics, every few minutes) and the
  event consumer (rows of the events outbox after the seal), never a model.
  Every run is in the Audit and in growth.automation_runs, once per occurrence
  key. A failing automation turns itself off after FAILURES_OFF failures in a
  row and tells the owner; one that fires too fast is stopped the same way.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel

from hq_api import audit, events, workflows_client
from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gate, groups, humanize, notify, recurrence
from hq_api.errors import ApiError
from hq_api.lines import signing
from hq_api.principal import Principal
from hq_common.redact import scrub

log = logging.getLogger("hq_api.automations")

TASK_CLASS = "automation_compile"
MODEL = "claude-sonnet-5-5"  # a mid model: one sentence, one rule
MAX_OUTPUT_TOKENS = 900
SERVICE = Principal(kind="service", code="automations", role="service")
FAILURES_OFF = 3  # failures in a row that turn an automation off
MAX_PER_HOUR = 20  # more runs that acted in an hour turn it off (a loop of its own events)
MAX_ACTIONS = 5
MAX_CONDITIONS = 3
LOOKBACK = timedelta(hours=2)  # a schedule's occurrence is still run this late
EVENT_BATCH = 25
# core.outbox.id is taken at insert, not at commit: a transaction still open may
# hold a lower id than rows already visible. The event cursor therefore only
# passes rows older than this (created_at is the emitting transaction's start);
# newer rows are read again each tick and a run's key keeps them to one run.
EVENT_SETTLE = timedelta(minutes=30)
N8N_POST: Callable[..., Awaitable[int]] | None = None  # tests put a fake webhook here

TRIGGER_KINDS = ("schedule", "event", "metric")
ACTION_KINDS = (
    "work.create",
    "line.run",
    "line.pause",
    "notify.owner",
    "notify.lead",
    "ad.pause",
    "n8n.run",
)
OPS = ("<", "<=", ">", ">=", "==", "!=")
AGGS = ("last", "sum", "avg", "min", "max")
# The stream types an automation may wait for (a type that never comes never fires).
# `automation.run` is not among them: an automation never waits for automations.
EVENT_TYPES: dict[str, str] = {
    "work.completed": "یک کار تمام شد",
    "deliverable.created": "یک خروجی تازه رسید",
    "decision.created": "یک کارت تصمیم تازه آمد",
    "decision.decided": "یک کارت تصمیم تصمیم‌گیری شد",
    "media.item": "یک محتوای رسانه‌ای تغییر کرد",
    "revenue.day": "درآمد یک روز ثبت شد",
    "revenue.alert": "هشدار درآمد آمد",
    "support.message": "پیام تازه‌ای به پشتیبانی رسید",
    "rescue.updated": "یک پرونده‌ی نجات مشتری تغییر کرد",
    "connection.updated": "یک اتصال خوانده شد",
    "group.run": "روال یک گروه کاری اجرا شد",
    "lifecycle.sent": "یک پیام چرخه‌ی مشتری فرستاده شد",
    "ad.paused": "یک کمپین تبلیغاتی متوقف شد",
    "ad.resumed": "یک کمپین تبلیغاتی دوباره روشن شد",
}
METRIC_CONNECTIONS = (*CN.KINDS, "hub")
DAYS_FA = {
    "MO": "دوشنبه",
    "TU": "سه‌شنبه",
    "WE": "چهارشنبه",
    "TH": "پنجشنبه",
    "FR": "جمعه",
    "SA": "شنبه",
    "SU": "یکشنبه",
}
OPS_FA = {
    "<": "کمتر از",
    "<=": "کمتر یا برابر",
    ">": "بیشتر از",
    ">=": "بیشتر یا برابر",
    "==": "برابر با",
    "!=": "غیر از",
}
AGG_FA = {"last": "آخرین مقدار", "sum": "جمع", "avg": "میانگین", "min": "کمترین", "max": "بیشترین"}
CODE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
LINE = re.compile(r"^LN-[0-9]{4,}$")
WORKFLOW = re.compile(r"^[a-z0-9][a-z0-9_-]{1,60}$")
ROLE = re.compile(r"^[a-z][a-z_]{1,30}$")
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "‌": " ", "‏": "", "‎": ""})

# Every action: its arguments (required first), and whether it acts inside a company.
ACTION_ARGS: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {
    "work.create": (("title_fa",), ("brief_fa", "role", "priority", "company"), True),
    "line.run": (("line",), ("company",), True),
    "line.pause": (("line",), ("reason_fa", "company"), True),
    "notify.owner": (("title_fa",), ("body_fa",), False),
    "notify.lead": (("title_fa",), ("body_fa", "company"), True),
    "ad.pause": (("platform", "campaign"), ("company",), True),
    "n8n.run": (("workflow",), ("company",), False),
}


class Compiled(BaseModel):
    rule: dict[str, Any] | None
    preview_fa: str | None
    refused_fa: list[str]


# ------------------------------------------------------------------- roles --
class Roles(BaseModel):
    """⟨2026-11-07⟩ The company's real roles: the compiler's instructions and the normaliser."""

    held: dict[str, str] = {}  # role key -> title_fa: an active employee's, or a department team's
    employees: dict[str, str] = {}  # employee code -> role key (active, not system)
    managers: dict[str, str] = {}  # department code -> its manager's role key
    ceo: str | None = None
    titles: dict[str, str] = {}  # normalised title (Persian or English) -> role key (the library)
    departments: dict[str, str] = {}  # role key -> the charter's department code
    department: str | None = None  # the proposer's department (a manager's): the fallback manager

    def manager_of(self, department: str | None) -> str | None:
        return self.managers.get(department) if department else None


def norm_word(v: str) -> str:
    """A role as written, comparable: lowercase, Arabic letters to Persian, one space."""
    return " ".join(str(v).translate(_ARABIC).lower().replace("_", " ").replace("-", " ").split())


def role_titles(lib: Any) -> dict[str, str]:
    """role key -> title_fa of every charter (for the preview), {} without a library."""
    roles = getattr(lib, "roles", None) or {}
    return {k: str(c.title_fa) for k, c in roles.items()}


async def company_roles(
    tx: Tx, hub: Any, company_code: str, *, department: str | None = None
) -> Roles:
    """What `role` may mean in this company: its active employees' roles and codes, its
    departments' managers and teams (the template's), the CEO; and the charter library's titles."""
    from hq_api.domain import templates as T

    co = await tx.first("SELECT id, template FROM core.companies WHERE code = :c", c=company_code)
    out = Roles(department=department)
    lib = getattr(hub, "charters", None)
    roles = getattr(lib, "roles", None) or {}
    for key, c in roles.items():
        for t in (c.title_fa, c.title_en):
            if t:
                out.titles.setdefault(norm_word(str(t)), key)
        if c.department:
            out.departments[key] = str(c.department)
    if co is None:
        return out
    rows = await tx.all(
        """SELECT e.code, e.role, e.kind, e.title_fa, d.code AS department
           FROM core.employees e LEFT JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND e.status = 'active' AND e.kind <> 'system'
             AND e.role IS NOT NULL
           ORDER BY e.hired_at""",
        co=co["id"],
    )
    for r in rows:
        role = str(r["role"])
        out.employees[str(r["code"])] = role
        out.held.setdefault(role, str(r["title_fa"] or role))
        if r["kind"] == "ceo" and out.ceo is None:
            out.ceo = role
        if r["kind"] in ("manager", "ceo") and r["department"]:
            out.managers.setdefault(str(r["department"]), role)
    depts = await tx.all("SELECT code FROM core.departments WHERE company_id = :co", co=co["id"])
    for d in depts:
        code = str(d["code"])
        for t in T.team_of(T.department(co["template"], code), lib, code):
            out.held.setdefault(str(t["role"]), str(t["title_fa"]))
    return out


# ⟨2026-11-07⟩ the everyday words for the media charters (the working groups' seat titles say them
# so: content.yaml's «نویسنده» is the scriptwriter, whose charter title is «سناریست»)
ROLE_WORDS = {
    "نویسنده": "scriptwriter", "سناریست": "scriptwriter", "سناریونویس": "scriptwriter",
    "کارگردان": "video_director", "کارگردان ریلز": "video_director",
    "طراح": "visual_designer", "طراح تصویر": "visual_designer", "طراح گرافیک": "visual_designer",
    "موشن": "motion_designer", "موشن دیزاینر": "motion_designer", "سازنده ریلز": "motion_designer",
    "گوینده": "voice_producer", "صداگذار": "voice_producer", "سازنده صدا": "voice_producer",
    "مسئول انتشار": "publisher", "ناشر": "publisher",
    "تحلیلگر": "content_analyst", "تحلیلگر عملکرد": "content_analyst",
    "مدیر محتوا": "media_director", "مدیر رسانه": "media_director",
}  # fmt: skip


def normalize_role(raw: Any, roles: Roles | None) -> tuple[str | None, str | None]:
    """(the role key the work goes to, a plain note when it is not the one written). Never
    refuses: a role nobody holds goes to the matching department's manager, else the CEO, else to
    nobody (the work's own default: its department's manager, else the CEO)."""
    if raw is None:
        return None, None
    word = " ".join(str(raw).split())
    if not word:
        return None, None
    if roles is None:
        key = word.lower()
        return (key, None) if ROLE.match(key) else (None, _unknown_note(word, None))
    bare = word.split("@", 1)[0].strip() if "@" in word else word
    if bare.upper() in roles.employees:  # an employee's code: that employee's role
        return roles.employees[bare.upper()], None
    plain = norm_word(bare)
    key = plain.replace(" ", "_")
    if key in roles.held:
        return key, None
    tight = plain.replace(" ", "")  # `script-writer`, `Script Writer`: scriptwriter
    hit = roles.titles.get(plain) or next(
        (k for k in roles.held if k.replace("_", "") == tight), None
    )
    if hit is None:
        hit = next((k for t, k in roles.titles.items() if t.replace(" ", "") == tight), None)
    if hit is None:  # ⟨2026-11-07⟩ the company's own title for it («نویسنده» is PC's scriptwriter)
        hit = next(
            (k for k, t in roles.held.items()
             if norm_word(t) == plain or norm_word(t).replace(" ", "") == tight),
            None,
        )  # fmt: skip
    if hit is None:  # the everyday word the owner and the models use for a charter
        hit = ROLE_WORDS.get(plain) or ROLE_WORDS.get(tight)
    if hit is None and len(plain) >= 4:  # «مدیر رسانه» for «مدیر رسانه و طراحی»
        hit = next((k for t, k in roles.titles.items() if plain in t or t in plain), None)
    charter = hit or (key if key in roles.departments or key == roles.ceo else None)
    if charter is not None and charter in roles.held:
        return charter, None
    # nobody in the company holds it: the charter's department manager, else the proposer's
    # department manager, else the CEO
    manager = (
        roles.manager_of(roles.departments.get(charter or ""))
        or roles.manager_of(roles.department)
        or roles.ceo
    )
    if manager is None:
        return None, _unknown_note(word, None)
    return manager, _unknown_note(word, roles.held.get(manager, manager))


def _unknown_note(word: str, who_title: str | None) -> str:
    who = f"به {who_title}" if who_title else "به مدیر مربوط، وگرنه مدیرعامل"
    return f"کسی با نقش «{word[:40]}» در این شرکت نیست؛ این کار {who} داده میشود."


# ---------------------------------------------------------------- validation --
class Refused(Exception):
    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


def _text(v: Any, name: str, lo: int, hi: int, *, required: bool = True) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise Refused(f"«{name}» نوشته نشده است.")
        return None
    if not isinstance(v, str):
        raise Refused(f"«{name}» باید متن باشد.")
    out = " ".join(scrub(v).split())
    if not lo <= len(out) <= hi:
        raise Refused(f"«{name}» باید بین {lo} و {hi} نویسه باشد.")
    return out


def _number(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise Refused(f"«{name}» باید عدد باشد.")
    return float(v)


def metric_of(raw: Any, *, named: str = "شرط عددی") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise Refused(f"{named} درست نوشته نشده است.")
    extra = set(raw) - {"kind", "connection", "key", "op", "value", "window_days", "agg"}
    if extra:
        raise Refused(f"{named} چیزی دارد که شناخته نمیشود: {', '.join(sorted(map(str, extra)))}.")
    conn, key, op = raw.get("connection"), raw.get("key"), raw.get("op")
    if conn not in METRIC_CONNECTIONS:
        raise Refused("اتصال این عدد را نمیشناسم؛ فقط اتصال‌های خود هاب مجازند.")
    if not isinstance(key, str) or not KEY.match(key):
        raise Refused("نام عدد درست نیست.")
    if op not in OPS:
        raise Refused("مقایسه‌ی عدد درست نیست.")
    window = raw.get("window_days", 1)
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 90:
        raise Refused("بازه‌ی عدد باید بین ۱ تا ۹۰ روز باشد.")
    agg = raw.get("agg", "last")
    if agg not in AGGS:
        raise Refused("روش جمع‌بندی عدد درست نیست.")
    return {
        "connection": conn,
        "key": key,
        "op": op,
        "value": _number(raw.get("value"), "مقدار"),
        "window_days": window,
        "agg": agg,
    }


def trigger_of(raw: Any, company: str | None) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("kind") not in TRIGGER_KINDS:
        raise Refused("آغازگر کار مشخص نیست؛ فقط زمان‌بندی، یک رویداد یا یک عدد مجاز است.")
    kind = raw["kind"]
    if kind == "schedule":
        if set(raw) - {"kind", "rrule"}:
            raise Refused("زمان‌بندی چیز اضافه دارد.")
        try:
            rule = recurrence.parse(str(raw.get("rrule") or ""))
        except ApiError as exc:
            raise Refused("زمان‌بندی درست نیست؛ مثلاً «هر روز ساعت ۹» یا «هر شنبه ساعت ۸».") from exc
        return {"kind": "schedule", "rrule": rule.rrule()}
    if kind == "event":
        if set(raw) - {"kind", "type"}:
            raise Refused("رویداد چیز اضافه دارد.")
        if raw.get("type") not in EVENT_TYPES:
            raise Refused("این رویداد در فهرست رویدادهای مجاز نیست.")
        return {"kind": "event", "type": raw["type"]}
    if company is None:
        raise Refused("برای سنجیدن یک عدد باید نام شرکت را هم بگویید.")
    return {"kind": "metric", **metric_of(raw, named="عدد")}


def action_of(
    raw: Any,
    company: str | None,
    known: set[str],
    roles: Roles | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    kind = raw.get("kind") if isinstance(raw, dict) else None
    if kind not in ACTION_KINDS:
        raise Refused(
            "این کار در فهرست کارهای مجاز نیست؛ فقط ساخت کار، اجرا یا توقف خط، خبر به مدیر کل "
            "یا مسئول شرکت، توقف کمپین تبلیغاتی و اجرای یک جریان خودکار آماده مجازند."
        )
    args = raw.get("args", {})
    required, optional, needs_company = ACTION_ARGS[kind]
    if not isinstance(args, dict):
        raise Refused(f"ورودی «{kind}» درست نیست.")
    if set(args) - {*required, *optional}:
        raise Refused(
            f"«{kind}» ورودی ناشناخته دارد: {', '.join(sorted(map(str, set(args) - {*required, *optional})))}."
        )
    out: dict[str, Any] = {}
    for name in (*required, *optional):
        v = args.get(name)
        if name in ("title_fa", "reason_fa"):
            got = _text(v, name, 1, 200, required=name in required)
        elif name in ("brief_fa", "body_fa"):
            got = _text(v, name, 1, 2000, required=name in required)
        elif name == "line":
            got = v if isinstance(v, str) and LINE.match(v) else None
            if got is None:
                raise Refused("«خط تولید» (line) باید شماره‌ی یک خط باشد، مثل LN-0001.")
        elif name == "workflow":
            got = v if isinstance(v, str) and WORKFLOW.match(v) else None
            if got is None:
                raise Refused(
                    "«جریان خودکار» (workflow) باید نام یک جریان موجود باشد: حرف و عدد کوچک و خط تیره."
                )
        elif name == "role":
            # ⟨2026-11-07⟩ never a refusal: the company's role, else its manager, else nobody
            got, note = normalize_role(v, roles)
            if note and notes is not None:
                notes.append(note)
        elif name == "priority":
            got = v if v in (None, "P0", "P1", "P2", "P3", "P4") else "!"
            if got == "!":
                raise Refused("«اولویت» (priority) باید یکی از P0 تا P4 باشد.")
        elif name == "platform":
            if v not in ("google_ads", "meta_ads"):
                raise Refused("«پلتفرم» (platform) باید google_ads یا meta_ads باشد.")
            got = v
        elif name == "campaign":
            if not (isinstance(v, str) and v.isdigit() and len(v) <= 30):
                raise Refused("«کمپین» (campaign) باید شناسه‌ی عددی کمپین باشد.")
            got = v
        else:  # company
            got = v
            if v is not None:
                if not (isinstance(v, str) and CODE.match(v) and v in known):
                    raise Refused(
                        "«شرکت» (company) باید کد یکی از شرکت‌های هلدینگ باشد: "
                        + ", ".join(sorted(known))
                        + "."
                    )
                if company is not None and v != company:
                    raise Refused("یک خودکارسازی شرکتی فقط داخل شرکت خودش کار میکند.")
        if got is not None:
            out[name] = got
    if needs_company and company is None and "company" not in out:
        raise Refused("برای این کار باید نام شرکت را بگویید.")
    return {"kind": kind, "args": out}


def validate_rule(
    raw: Any,
    company: str | None,
    known: set[str],
    roles: Roles | None = None,
    notes: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """The rule as the model gave it, checked by code: (the normalised rule, [])
    or (None, the plain Persian reasons). Only this shape ever runs. ⟨2026-11-07⟩ `roles` is the
    company's (company_roles): a role is normalised, never refused; `notes` collects what code
    changed, for the preview."""
    reasons: list[str] = []
    if not isinstance(raw, dict) or set(raw) - {"trigger", "conditions", "actions"}:
        return None, ["قاعده درست ساخته نشد؛ جمله را ساده‌تر بنویسید."]
    out: dict[str, Any] = {}
    try:
        out["trigger"] = trigger_of(raw.get("trigger"), company)
    except Refused as exc:
        reasons.append(exc.why)
    conds = raw.get("conditions") or []
    if not isinstance(conds, list) or len(conds) > MAX_CONDITIONS:
        reasons.append(f"شرط‌ها باید حداکثر {MAX_CONDITIONS} تا باشند.")
    elif conds and company is None:
        reasons.append("برای شرط عددی باید نام شرکت را هم بگویید.")
    else:
        out["conditions"] = []
        for c in conds:
            try:
                out["conditions"].append(metric_of(c))
            except Refused as exc:
                reasons.append(exc.why)
    acts = raw.get("actions")
    if not isinstance(acts, list) or not 1 <= len(acts) <= MAX_ACTIONS:
        reasons.append(f"باید یک تا {MAX_ACTIONS} کار تعریف شده باشد.")
    else:
        out["actions"] = []
        for a in acts:
            try:
                out["actions"].append(action_of(a, company, known, roles, notes))
            except Refused as exc:
                reasons.append(exc.why)
    if reasons:
        return None, list(dict.fromkeys(reasons))
    out.setdefault("conditions", [])
    return out, []


# ------------------------------------------------------------------ preview --
def at_fa(hours: tuple[int, ...], minutes: tuple[int, ...]) -> str:
    """Every time of day the rule runs (each hour with each minute), never only
    the first: what the owner seals is what runs."""
    if len(hours) * len(minutes) <= 6:
        return "ساعت " + " و ".join(f"{h:02d}:{m:02d}" for h in hours for m in minutes)
    return (
        f"ساعت‌های {' و '.join(map(str, hours))}، "
        f"دقیقه‌ی {' و '.join(map(str, minutes))}"
    )


def when_fa(rrule: str) -> str:
    r = recurrence.parse(rrule)
    hh = at_fa(r.by_hour, r.by_minute) if r.by_hour else None
    if r.freq == "HOURLY":
        mins = " و ".join(map(str, r.by_minute))
        every = "هر ساعت" if r.interval == 1 else f"هر {r.interval} ساعت"
        return f"{every}، دقیقه‌ی {mins}"
    if r.freq == "DAILY":
        return f"هر روز {hh}"
    if r.freq == "WEEKLY":
        return f"هر {' و '.join(DAYS_FA[recurrence.DAYS[d]] for d in r.by_day)} {hh}"
    return f"هر ماه، روز {' و '.join(map(str, r.by_month_day))} {hh}"


def num_fa(v: float) -> str:
    return str(int(v)) if float(v) == int(v) else f"{v:.4f}".rstrip("0")


def metric_fa(m: dict[str, Any]) -> str:
    conn = "آمار خود هاب" if m["connection"] == "hub" else CN.LABEL_FA[m["connection"]]
    span = "" if m["window_days"] == 1 else f" در {m['window_days']} روز اخیر ({AGG_FA[m['agg']]})"
    return f"«{m['key']}» از {conn}{span} {OPS_FA[m['op']]} {num_fa(m['value'])} باشد"


def action_fa(a: dict[str, Any], company: str | None, titles: dict[str, str] | None = None) -> str:
    g = a["args"]
    where = g.get("company") or company
    at = f" برای شرکت {where}" if where else ""
    k = a["kind"]
    if k == "work.create":
        role = (titles or {}).get(g.get("role") or "", g.get("role"))
        who = f" برای «{role}»" if role else ""
        return f"یک کار تازه{at}{who} با عنوان «{g['title_fa']}» ساخته میشود"
    if k == "line.run":
        return f"خط تولید «{g['line']}»{at} یک بار اجرا میشود"
    if k == "line.pause":
        return f"خط تولید «{g['line']}»{at} متوقف میشود (بعداً با دست شما دوباره روشن میشود)"
    if k == "notify.owner":
        return f"برای شما این خبر فرستاده میشود: «{g['title_fa']}»"
    if k == "notify.lead":
        return f"مسئول رشد{at} با این عنوان خبردار میشود: «{g['title_fa']}»"
    if k == "ad.pause":
        return (
            f"کمپین {g['campaign']} در {CN.LABEL_FA[g['platform']]}{at} متوقف میشود "
            "(بودجه تغییر نمیکند)"
        )
    return f"جریان خودکار آماده «{g['workflow']}»{at} با امضای هاب فراخوانده میشود"


def preview_fa(
    rule: dict[str, Any],
    company: str | None,
    titles: dict[str, str] | None = None,
    notes: list[str] | None = None,
) -> str:
    """What this rule really does, in plain Persian, built from the validated rule (never from
    the model's words); `titles` names a role by its charter's title, `notes` says what code
    changed (a role nobody holds)."""
    t = rule["trigger"]
    if t["kind"] == "schedule":
        when = when_fa(t["rrule"]) + " (به وقت شما)"
    elif t["kind"] == "event":
        when = f"هر بار که این اتفاق بیفتد: {EVENT_TYPES[t['type']]}"
    else:
        when = "روزی که " + metric_fa(t)
    lines = [f"زمان: {when}."]
    if rule["conditions"]:
        lines.append("به شرط اینکه " + " و ".join(metric_fa(c) for c in rule["conditions"]) + ".")
    lines.append("آن‌وقت این کارها انجام میشود:")
    lines += [f"{i}. {action_fa(a, company, titles)}." for i, a in enumerate(rule["actions"], 1)]
    lines += list(dict.fromkeys(notes or []))
    lines.append(
        "غیر از این‌ها هیچ کار دیگری نمیکند: بودجه‌ای را بالا نمیبرد، چیزی را حذف نمیکند و "
        "تا مُهر شما نخورد اجرا نمیشود."
    )
    return "\n".join(lines)


# -------------------------------------------------------------------- compile --
ARG_PROPS = {
    k: {"type": "string", "maxLength": 2000}
    for k in (
        "title_fa",
        "brief_fa",
        "body_fa",
        "reason_fa",
        "role",
        "priority",
        "line",
        "platform",
        "campaign",
        "workflow",
        "company",
    )
}
METRIC_PROPS: dict[str, Any] = {
    "connection": {"type": "string", "enum": list(METRIC_CONNECTIONS)},
    "key": {"type": "string", "maxLength": 41},
    "op": {"type": "string", "enum": list(OPS)},
    "value": {"type": "number"},
    "window_days": {"type": "integer", "minimum": 1, "maximum": 90},
    "agg": {"type": "string", "enum": list(AGGS)},
}
RULE_OBJECT: dict[str, Any] = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "properties": {
        "trigger": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string", "enum": list(TRIGGER_KINDS)},
                "rrule": {"type": "string", "maxLength": 200},
                "type": {"type": "string", "enum": list(EVENT_TYPES)},
                **METRIC_PROPS,
            },
            "required": ["kind"],
        },
        "conditions": {
            "type": "array",
            "maxItems": MAX_CONDITIONS,
            "items": {"type": "object", "additionalProperties": False, "properties": METRIC_PROPS},
        },
        "actions": {
            "type": "array",
            "maxItems": MAX_ACTIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": list(ACTION_KINDS)},
                    "args": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": ARG_PROPS,
                    },
                },
                "required": ["kind", "args"],
            },
        },
    },
}
MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "rule": RULE_OBJECT,
                    "refused_fa": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {"type": "string", "maxLength": 200},
                    },
                },
                "required": ["rule", "refused_fa"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}
MODEL_SYSTEM = (
    "You turn ONE Persian sentence of a holding's owner into ONE automation rule as JSON, nothing else. "
    'Answer {"routes": [{"rule": <rule or null>, "refused_fa": [<plain Persian reasons>]}]}. '
    "A rule is {trigger, conditions, actions}. trigger.kind is one of: "
    "schedule (rrule: FREQ=HOURLY|DAILY|WEEKLY|MONTHLY with BYDAY, BYMONTHDAY, BYHOUR, BYMINUTE), "
    "event (type from the enum), metric (connection, key, op, value, window_days, agg). "
    "conditions: extra metric tests that must all hold. actions: up to five of "
    + ", ".join(ACTION_KINDS)
    + ", each {kind, args}. work.create needs title_fa (brief_fa, role, priority optional; role is one "
    "of the keys of `roles` in the input, the company's real roles, exactly as written there, never a "
    "person's name, a code or a translation; when none fits, leave role out); "
    "line.run and line.pause need line; notify.owner and notify.lead need title_fa (body_fa optional); "
    "ad.pause needs platform (google_ads|meta_ads) and campaign (digits); n8n.run needs workflow. "
    "You may only use these. If the sentence asks for anything else (spending money, raising a budget, "
    "deleting, sending to customers, changing code or servers, anything outside the list), put the "
    "rule as null or leave that action out, and say why in refused_fa in plain Persian. "
    "Never invent a number, a company or a line the sentence does not name. Put no preamble."
)


def model_request(
    masked: str, holding: str, company: str | None, roles: Roles | None = None
) -> dict[str, Any]:
    prompt: dict[str, Any] = {"company": company, "sentence": masked}
    if roles is not None and roles.held:
        prompt["roles"] = dict(sorted(roles.held.items()))
    return {
        "company_code": holding,
        "actor_ref": "automations",
        "task_class": TASK_CLASS,
        "priority": 1,
        "model": MODEL,
        "effort": "low",
        "system": MODEL_SYSTEM,
        "prompt": json.dumps(prompt, ensure_ascii=False),
        "json_schema": MODEL_SCHEMA,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 40,
        "meta": {"purpose": "automation_compile"},
    }


def _model_reasons(items: Any) -> list[str]:
    """The model's own refusals, kept only when they are short plain Persian."""
    out: list[str] = []
    for x in items if isinstance(items, list) else []:
        s = " ".join(str(x).split())[:200]
        if s and humanize.persian_share(s) >= 0.6 and not humanize.check(s):
            out.append(s)
    return out[:5]


async def compile_sentence(
    hub: Any, sentence: str, company: str | None, *, department: str | None = None
) -> Compiled:
    """ONE router call, then code decides what survives. ⟨2026-11-07⟩ the company's real roles go
    with the sentence and come back through the normaliser (`department`: the proposer's, whose
    manager takes a work for a role nobody holds)."""
    text = " ".join(scrub(sentence).split())
    if len(text) < 3:
        raise ApiError(422, "validation_failed", fields={"sentence_fa": "too short"},
                       message_fa="«جمله» (sentence_fa) باید دست‌کم سه نویسه باشد.")  # fmt: skip
    known = {c.code for c in await hub.companies.all() if c.kind != "holding"}
    if company is not None and company not in known:
        raise ApiError(404, "not_found", message_fa="این شرکت را نمیشناسم.")
    holding = await hub.companies.holding()
    roles: Roles | None = None
    if company is not None:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            roles = await company_roles(tx, hub, company, department=department)
    answer = await workflows_client.route_order(
        hub, model_request(text, holding.code, company, roles)
    )
    routes = (answer or {}).get("routes")
    if (
        not isinstance(routes, list)
        or len(routes) != 1
        or not isinstance(routes[0], dict)
        or not isinstance(routes[0].get("refused_fa", []), list)
    ):
        # 422, not a 5xx: the sentence could not be made a rule (never a server error; the apps show
        # message_fa and the owner writes it again more simply).
        raise ApiError(
            422,
            "validation_failed",
            "the model did not answer in the schema",
            message_fa="نتوانستم این جمله را به قاعده‌ی روشن تبدیل کنم؛ دوباره و ساده‌تر بنویسید.",
            fields={"sentence_fa": "not compiled"},
        )
    item = routes[0]
    refused = _model_reasons(item.get("refused_fa"))
    notes: list[str] = []
    rule, why = (
        validate_rule(item.get("rule"), company, known, roles, notes)
        if item.get("rule")
        else (None, [])
    )
    refused = list(dict.fromkeys([*why, *refused]))
    if rule is None:
        return Compiled(
            rule=None,
            preview_fa=None,
            refused_fa=refused
            or ["این جمله به یک کار روشن و مجاز تبدیل نشد؛ زمان و کار را دقیق‌تر بنویسید."],
        )
    preview = preview_fa(rule, company, role_titles(getattr(hub, "charters", None)), notes)
    return Compiled(rule=rule, preview_fa=preview, refused_fa=refused)


# --------------------------------------------------------------------- shapes --
class AutomationRun(BaseModel):
    key: str
    trigger: dict[str, Any]
    outcome: Literal["ok", "failed", "skipped"]
    steps: list[dict[str, Any]]
    error_fa: str | None
    at: datetime


class Automation(BaseModel):
    ref: str
    company: str | None
    sentence_fa: str
    rule: dict[str, Any]
    preview_fa: str
    state: Literal["proposed", "on", "off"]
    runs: int
    last_run_at: datetime | None
    n8n_workflow: str | None
    failures_in_row: int = 0
    last_error_fa: str | None = None
    off_reason: Literal["owner", "failures"] | None = None
    sealed_at: datetime | None = None
    created_at: datetime
    # ⟨1.31⟩ §50 a standing routine made from one sentence (`on` without a seal), and the
    # session it was asked in
    routine: bool = False
    order: str | None = None


class AutomationDetail(Automation):
    run_log: list[AutomationRun]


def n8n_of(rule: dict[str, Any]) -> str | None:
    return next((a["args"]["workflow"] for a in rule["actions"] if a["kind"] == "n8n.run"), None)


def render(
    a: dict[str, Any], company: str | None, titles: dict[str, str] | None = None
) -> Automation:
    rule = a["rule"] if isinstance(a["rule"], dict) else json.loads(a["rule"])
    src = a.get("source") or {}
    src = json.loads(src) if isinstance(src, str) else src
    return Automation(
        routine=bool(src.get("routine")),
        order=src.get("order"),
        ref=a["ref"],
        company=company if a["scope"] == "company" else None,
        sentence_fa=a["sentence_fa"],
        rule=rule,
        preview_fa=preview_fa(rule, company if a["scope"] == "company" else None, titles),
        state=a["state"],
        runs=a["runs"],
        last_run_at=a["last_run_at"],
        n8n_workflow=a["n8n_workflow"],
        failures_in_row=a["failures_in_row"],
        last_error_fa=a["last_error_fa"],
        off_reason=a["off_reason"],
        sealed_at=a["sealed_at"],
        created_at=a["created_at"],
    )


def render_run(r: dict[str, Any]) -> AutomationRun:
    return AutomationRun(
        key=r["key"],
        trigger=r["trigger"],
        outcome=r["outcome"],
        steps=r["steps"],
        error_fa=r["error_fa"],
        at=r["at"],
    )


async def row_of(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    return await tx.one(
        f"""SELECT a.*, c.code AS company_code FROM growth.automations a
            JOIN core.companies c ON c.id = a.company_id WHERE a.ref = :r
            {"FOR UPDATE OF a" if lock else ""}""",  # noqa: S608 - a constant clause
        r=ref,
    )


# -------------------------------------------------------------------- metrics --
def aggregate(values: list[float], agg: str) -> float | None:
    if not values:
        return None
    return {
        "last": values[-1],
        "sum": sum(values),
        "avg": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }[agg]


def compare(op: str, a: float, b: float) -> bool:
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[op]


async def metric_value(
    tx: Tx, company_id: UUID, m: dict[str, Any], today: date
) -> tuple[float | None, date | None]:
    """The figure (per day: the sum over the subjects of that day) over the
    window, aggregated; and the latest day it has."""
    rows = await tx.all(
        """SELECT day, sum(value) AS v FROM growth.metrics_daily
           WHERE company_id = :co AND kind = :k AND key = :key AND day > :since AND day <= :today
           GROUP BY day ORDER BY day""",
        co=company_id,
        k=m["connection"],
        key=m["key"],
        since=today - timedelta(days=int(m["window_days"])),
        today=today,
    )
    return aggregate([float(r["v"]) for r in rows], m["agg"]), (rows[-1]["day"] if rows else None)


async def metrics_hold(tx: Tx, company_id: UUID, ms: list[dict[str, Any]], today: date) -> bool:
    for m in ms:
        v, _ = await metric_value(tx, company_id, m, today)
        if v is None or not compare(m["op"], v, float(m["value"])):
            return False
    return True


# -------------------------------------------------------------------- actions --
class ActionError(Exception):
    def __init__(self, reason_fa: str) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa


async def _company(tx: Tx, auto: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    code = args.get("company") or (auto["company_code"] if auto["scope"] == "company" else None)
    row = await tx.first("SELECT id, code, kind FROM core.companies WHERE code = :c", c=code)
    if row is None or row["kind"] == "holding":
        raise ActionError("شرکت این کار پیدا نشد.")
    return row


async def _work(tx: Tx, auto: dict[str, Any], args: dict[str, Any], *, lead: bool) -> str:
    from hq_api.domain import work as W

    co = await _company(tx, auto, args)
    if lead:
        assignee = await ads_lead(tx, co["id"])
    elif args.get("role"):
        assignee = (await groups.seat_holders(tx, co["id"], [args["role"]])).get(args["role"])
    else:
        assignee = None
    try:
        w = await W.create(
            tx,
            SERVICE,
            company_id=co["id"],
            company_code=co["code"],
            title=args["title_fa"],
            brief=args.get("brief_fa") or args.get("body_fa") or "",
            kind="one_off",
            priority=args.get("priority") or ("P2" if lead else "P3"),
            assignee_code=assignee,
        )
    except ApiError as exc:
        raise ActionError("کار ساخته نشد؛ کارمند این جایگاه در دسترس نیست.") from exc
    return f"کار {w['ref']} ساخته شد."


async def ads_lead(tx: Tx, company_id: UUID) -> str | None:
    from hq_api.domain import ads

    return await ads.growth_lead(tx, company_id)


def _lines() -> Any:
    try:
        from hq_api.lines import (  # type: ignore[attr-defined,unused-ignore]  # the lines engine (§30)
            engine,
            store,
        )
    except ImportError as exc:
        raise ActionError("موتور خط‌های تولید در این نسخه‌ی هاب هنوز نیست.") from exc
    return engine, store


async def _line(hub: Any, tx: Tx, auto: dict[str, Any], args: dict[str, Any], pause: bool) -> str:
    """A line of the company, by its ref (LN-0001): run it once (a run for the
    lines tick, started right after the commit), or pause it (reversible, by
    the owner's hand)."""
    engine, store = _lines()
    co = await _company(tx, auto, args)
    try:
        line = await store.load(tx, args["line"])
    except ApiError as exc:
        raise ActionError("این خط تولید پیدا نشد.") from exc
    if line["company_id"] != co["id"]:
        raise ActionError("این خط تولید مال این شرکت نیست.")
    if pause:
        if line["state"] == "paused":
            return f"خط «{args['line']}» از پیش متوقف بود."
        await store.set_state(tx, line, "paused")
        return f"خط «{args['line']}» متوقف شد."
    if line["state"] != "on":
        raise ActionError("این خط تولید روشن نیست؛ اجرا نمیشود.")
    try:
        run = await engine.start_run(tx, line, trigger="owner", who=SERVICE)
    except ApiError as exc:
        raise ActionError(exc.message_fa or "خط تولید این درخواست را نپذیرفت.") from exc
    auto.setdefault("_kicks", []).append(run["ref"])
    return (
        f"خط «{args['line']}» اجرا شد."
        if run["state"] != "skipped"
        else (f"اجرای خط «{args['line']}» رد شد: {run.get('note_fa') or 'سقف یا قفل'}")
    )


async def _notify_owner(tx: Tx, auto: dict[str, Any], args: dict[str, Any]) -> str:
    row = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1")
    await notify.raise_notification(
        tx,
        company_id=row["id"],
        company_code=row["code"],
        level="report",
        title_fa=args["title_fa"],
        body_fa=args.get("body_fa") or "",
        link_kind="automation",
        link_ref=auto["ref"],
        source_kind="system",
        source_code="automations",
        domain="business",  # the owner's own rule asked to be told
        owner_action=True,
    )
    return "خبر برای مدیر کل فرستاده شد."


async def _ad_pause(
    hub: Any, tx: Tx, auto: dict[str, Any], args: dict[str, Any], today: date
) -> str:
    from hq_api.domain import ads

    co = await _company(tx, auto, args)
    try:
        ctx = await ads._api_ctx(hub, co["id"], co["code"], args["platform"], today)
        try:
            await ads.set_status(ctx, args["campaign"], paused=True)
        finally:
            await ads._record_egress(hub, co["id"], ctx)
    except CN.ReadError as exc:
        raise ActionError(exc.reason_fa) from exc
    await tx.exec(
        """UPDATE growth.ad_campaigns SET status = 'paused', paused_by = 'rule', paused_at = now(),
               paused_reason_fa = :why, updated_at = now()
           WHERE company_id = :co AND platform = :p AND campaign_id = :c""",
        co=co["id"],
        p=args["platform"],
        c=args["campaign"],
        why=f"{auto['ref']}: خودکارسازی",
    )
    await events.emit(
        tx,
        co["code"],
        "ad.paused",
        args["campaign"],
        {"platform": args["platform"], "campaign": args["campaign"], "automation": auto["ref"]},
    )
    return f"کمپین {args['campaign']} متوقف شد."


def n8n_settings(hub: Any) -> str:
    return str(getattr(hub.settings, "n8n_url", "") or os.environ.get("HQ_N8N_URL", "")).rstrip("/")


async def _n8n(hub: Any, auto: dict[str, Any], args: dict[str, Any], key: str) -> str:
    """A signed webhook (HMAC-SHA256, the secret from OpenBao kv/hq/n8n): n8n
    holds no model key and calls no model (contract §30.4)."""
    url = n8n_settings(hub)
    if not url and N8N_POST is None:
        raise ActionError("موتور جریان‌های خودکار روی این هاب هنوز راه‌اندازی نشده است.")
    secret = None
    if getattr(hub, "bao", None) is not None:
        try:
            data = await hub.bao.read_kv("hq/n8n")
            secret = (data or {}).get("hmac_secret") or (data or {}).get("secret")
        except Exception:  # noqa: BLE001 - said plainly below, no detail
            secret = None
    if not secret:
        raise ActionError("رمز امضای جریان‌های خودکار در گاوصندوق هاب نیست.")
    body = json.dumps(
        {
            "automation": auto["ref"],
            "company": args.get("company") or auto["company_code"],
            "workflow": args["workflow"],
            "occurrence": key,
            "at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    ).encode()
    header = signing.sign(str(secret), body)
    target = f"{url}/webhook/{args['workflow']}"
    if N8N_POST is not None:
        status = await N8N_POST(target, body, {signing.HEADER: header})
    else:
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as http:
                resp = await http.post(
                    target,
                    content=body,
                    headers={signing.HEADER: header, "Content-Type": "application/json"},
                )
            status = resp.status_code
        except httpx.HTTPError as exc:
            raise ActionError("موتور جریان‌های خودکار پاسخ نداد.") from exc
    if not 200 <= status < 300:
        raise ActionError("موتور جریان‌های خودکار این درخواست را نپذیرفت.")
    return f"جریان «{args['workflow']}» فراخوانده شد."


async def run_action(
    hub: Any, tx: Tx, auto: dict[str, Any], a: dict[str, Any], key: str, today: date
) -> str:
    """One allow-listed action, by code. Raises ActionError with the plain reason."""
    k, args = a["kind"], a["args"]
    if k == "work.create":
        return await _work(tx, auto, args, lead=False)
    if k == "notify.lead":
        return await _work(tx, auto, args, lead=True)
    if k == "notify.owner":
        return await _notify_owner(tx, auto, args)
    if k == "line.run":
        return await _line(hub, tx, auto, args, pause=False)
    if k == "line.pause":
        return await _line(hub, tx, auto, args, pause=True)
    if k == "ad.pause":
        return await _ad_pause(hub, tx, auto, args, today)
    if k == "n8n.run":
        return await _n8n(hub, auto, args, key)
    raise ActionError("این کار مجاز نیست.")  # unreachable: validated at compile time


# ---------------------------------------------------------------------- firing --
async def fire(
    hub: Any,
    auto_id: UUID,
    key: str,
    trigger: dict[str, Any],
    today: date,
    *,
    now: datetime | None = None,
) -> str | None:
    """One occurrence of an automation, once per key: the conditions, the
    actions in order (the first failure stops the rest), the run, the Audit, the
    stream, and the switch-off after FAILURES_OFF failures in a row. Returns the
    outcome, or None when this key ran already (or the automation is not on)."""
    now = now or datetime.now(UTC)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        auto = await tx.first(
            """SELECT a.*, c.code AS company_code FROM growth.automations a
               JOIN core.companies c ON c.id = a.company_id
               WHERE a.id = :id AND a.state = 'on' FOR UPDATE OF a SKIP LOCKED""",
            id=auto_id,
        )
        if auto is None:
            return None
        if await tx.scalar(
            "SELECT 1 FROM growth.automation_runs WHERE automation_id = :a AND key = :k",
            a=auto_id,
            k=key,
        ):
            return None
        if await gate.automation_lock(tx, auto["company_id"]) is not None:
            return None
        rule = auto["rule"] if isinstance(auto["rule"], dict) else json.loads(auto["rule"])
        steps: list[dict[str, Any]] = []
        outcome, error = "ok", None
        # Only runs that acted (or failed) count toward the loop guard: a check
        # whose conditions did not hold did nothing and is never a failure.
        hourly = int(
            await tx.scalar(
                """SELECT count(*) FROM growth.automation_runs
                   WHERE automation_id = :a AND at > :s AND outcome <> 'skipped'""",
                a=auto_id,
                s=now - timedelta(hours=1),
            )
            or 0
        )
        if hourly >= MAX_PER_HOUR:
            outcome, error = "failed", "بیش از حد پشت سر هم اجرا شد؛ خاموش شد."
        elif rule["conditions"] and not await metrics_hold(
            tx, auto["company_id"], rule["conditions"], today
        ):
            outcome = "skipped"
            steps.append({"kind": "conditions", "ok": False, "note_fa": "شرط‌ها برقرار نبود."})
        else:
            for a in rule["actions"]:
                try:
                    async with tx.conn.begin_nested():
                        note = await run_action(hub, tx, auto, a, key, today)
                    steps.append({"kind": a["kind"], "ok": True, "note_fa": note})
                except ActionError as exc:
                    steps.append({"kind": a["kind"], "ok": False, "note_fa": exc.reason_fa})
                    outcome, error = "failed", exc.reason_fa
                    break
                except Exception:
                    log.warning(
                        "automation action failed", extra={"kind": a["kind"]}, exc_info=True
                    )
                    steps.append({"kind": a["kind"], "ok": False, "note_fa": "این کار انجام نشد."})
                    outcome, error = "failed", "این کار انجام نشد."
                    break
        await tx.exec(
            """INSERT INTO growth.automation_runs (company_id, automation_id, key, trigger, outcome,
                   steps, error_fa) VALUES (:co, :a, :k, CAST(:t AS jsonb), :o, CAST(:s AS jsonb), :e)""",
            co=auto["company_id"],
            a=auto_id,
            k=key,
            t=json.dumps(trigger, ensure_ascii=False),
            o=outcome,
            s=json.dumps(steps, ensure_ascii=False),
            e=error,
        )
        failures = 0 if outcome != "failed" else int(auto["failures_in_row"]) + 1
        if hourly >= MAX_PER_HOUR:
            failures = FAILURES_OFF
        off = failures >= FAILURES_OFF
        await tx.exec(
            """UPDATE growth.automations SET runs = runs + CASE WHEN :o = 'skipped' THEN 0 ELSE 1 END,
                   last_run_at = CASE WHEN :o = 'skipped' THEN last_run_at ELSE :now END,
                   failures_in_row = :f, last_error_fa = :e,
                   state = CASE WHEN :off THEN 'off' ELSE state END,
                   off_reason = CASE WHEN :off THEN 'failures' ELSE off_reason END,
                   updated_at = now() WHERE id = :id""",
            o=outcome,
            now=now,
            f=failures,
            e=error,
            off=off,
            id=auto_id,
        )
        await audit.record(
            tx,
            SERVICE,
            company_id=auto["company_id"],
            action="automation.run",
            action_class="A2",
            target_kind="automation",
            target_ref=auto["ref"],
            summary=f"{trigger.get('kind')} {key[:80]}: {outcome}"
            + (f" ({', '.join(s['kind'] for s in steps)})" if steps else ""),
        )
        await events.emit(
            tx,
            auto["company_code"],
            "automation.run",
            auto["ref"],
            {"outcome": outcome, "trigger": trigger.get("kind"), "state": "off" if off else "on"},
        )
        if off:
            holding = await tx.one(
                "SELECT id, code FROM core.companies WHERE kind = 'holding' LIMIT 1"
            )
            # Technical (2026-11-06): the error stays on the row and in the log, never in
            # the text. It is still the owner's: only the owner proposes and seals an
            # automation, and only he turns it on again.
            log.warning("automation %s turned itself off", auto["ref"], extra={"error": error})
            await notify.raise_notification(
                tx,
                company_id=holding["id"],
                company_code=holding["code"],
                level="report",
                title_fa=f"خودکارسازی «{str(auto['sentence_fa'])[:80]}» خاموش شد",
                body_fa=humanize.plain(
                    "چند بار پشت سر هم انجام نشد و خودش خاموش شد.",
                    None,
                    "اگر هنوز لازمش دارید، در اپ دوباره روشنش کنید.",
                ),
                link_kind="automation",
                link_ref=auto["ref"],
                source_kind="system",
                source_code="automations",
                domain="tech",
                owner_action=True,
            )
    if kicks := auto.get("_kicks"):  # the lines it queued start now (the lines tick would anyway)
        engine, _ = _lines()
        for ref in kicks:
            await engine.kick(hub, ref)
    return outcome


# ------------------------------------------------------------------------ tick --
async def max_outbox(tx: Tx) -> int:
    return int(await tx.scalar("SELECT COALESCE(max(id), 0) FROM core.outbox") or 0)


async def settled_outbox(tx: Tx) -> int:
    """The newest outbox id older than EVENT_SETTLE (by the database's clock):
    no transaction still open can hold an id at or below it."""
    return int(
        await tx.scalar(
            """SELECT COALESCE((SELECT id FROM core.outbox
                                WHERE created_at < now() - make_interval(secs => :s)
                                ORDER BY id DESC LIMIT 1), 0)""",
            s=EVENT_SETTLE.total_seconds(),
        )
        or 0
    )


async def tick(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """Every few minutes, by code: the schedules due (within LOOKBACK, after the
    seal), the metrics that hold (once per day of data), the events that came
    after the seal. Nothing while the holding or the company is locked."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"fired": 0, "failed": 0, "skipped": 0}
    ids = await hub.companies.ids()
    todo: list[tuple[UUID, str, dict[str, Any]]] = []
    settled: int | None = None
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        tz = await owner_tz(tx)
        today = CN.owner_today(tz, now)
        autos = await tx.all(
            """SELECT a.id, a.ref, a.company_id, a.scope, a.rule, a.sealed_at, a.event_cursor,
                      c.code AS company_code
               FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
               WHERE a.state = 'on' AND c.status = 'active' ORDER BY a.created_at"""
        )
        for a in autos:
            if await gate.automation_lock(tx, a["company_id"]) is not None:
                continue
            rule = a["rule"] if isinstance(a["rule"], dict) else json.loads(a["rule"])
            t = rule["trigger"]
            if t["kind"] == "schedule":
                found = recurrence.occurrences(
                    recurrence.parse(t["rrule"]),
                    tz,
                    max(now - LOOKBACK, a["sealed_at"]),
                    now + timedelta(seconds=1),
                )
                if found:
                    todo.append(
                        (
                            a["id"],
                            f"schedule:{found[-1].isoformat()}",
                            {"kind": "schedule", "occurrence": found[-1].isoformat()},
                        )
                    )
            elif t["kind"] == "metric":
                co = a["company_id"]
                v, day = await metric_value(tx, co, t, today)
                if v is not None and day is not None and compare(t["op"], v, float(t["value"])):
                    todo.append(
                        (
                            a["id"],
                            f"metric:{day.isoformat()}",
                            {
                                "kind": "metric",
                                "key": t["key"],
                                "value": round(v, 4),
                                "day": day.isoformat(),
                            },
                        )
                    )
            else:
                if settled is None:
                    settled = await settled_outbox(tx)
                rows = await tx.all(
                    """SELECT o.id, o.payload FROM core.outbox o
                       WHERE o.id > :cur AND o.payload ->> 'type' = :t
                         AND (:scope = 'holding' OR o.payload ->> 'company' = :co)
                         AND NOT EXISTS (SELECT 1 FROM growth.automation_runs r
                                         WHERE r.automation_id = :a
                                           AND r.key = 'event:' || (o.payload ->> 'id'))
                       ORDER BY o.id LIMIT :n""",
                    cur=a["event_cursor"],
                    t=t["type"],
                    scope=a["scope"],
                    co=a["company_code"],
                    a=a["id"],
                    n=EVENT_BATCH,
                )
                for r in rows:
                    p = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
                    todo.append(
                        (
                            a["id"],
                            f"event:{p.get('id')}",
                            {
                                "kind": "event",
                                "type": t["type"],
                                "ref": p.get("ref"),
                                "company": p.get("company"),
                            },
                        )
                    )
                # Never past a row that may still be in flight (see EVENT_SETTLE),
                # nor past the rows of a full batch not read yet.
                top = min(settled, rows[-1]["id"]) if len(rows) == EVENT_BATCH else settled
                await tx.exec(
                    "UPDATE growth.automations SET event_cursor = :c WHERE id = :id",
                    c=max(int(a["event_cursor"]), top),
                    id=a["id"],
                )
    for auto_id, key, trigger in todo:
        got = await fire(hub, auto_id, key, trigger, today, now=now)
        if got == "ok":
            out["fired"] += 1
        elif got == "failed":
            out["failed"] += 1
        elif got == "skipped":
            out["skipped"] += 1
    return out
