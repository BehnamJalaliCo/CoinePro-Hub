"""⟨1.39⟩ Contract §61 (prompt 39, P1): the automations as data, edited in the app.

The owner: «بخش اتوماسیون خیلی مبتدیه و باید یک قسمت مهم آپ باشه با کلی فیچر … و با قابلیت
تغییرات». Every daily flow is a row of automations.flows (seeded from domain/flows.py FLOWS by
migration 0070); domain/flows.py reads it (`active_flows`, `flow_by_key`) and its clock starts each
day (§61.2). Here: the FlowDef the apps read, the options a save may pick from, the save itself (a
new version with its changes in Persian, `If-Match`, §61.4's checks, 🔏 automation.budget past
the month envelope), and the switch, the pause, the skip and run-now.

Nothing here is a second automation system: a flow's day is still the order of domain/flows.start,
its page and its days are still those of flow_view (`N8:<key>` resolves to the same row).
"""

from __future__ import annotations

import contextlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.domain import flows as FL
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model

AF_REF = re.compile(r"^AF-[0-9]{4,}$")
HM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
EFFORTS = ("high", "xhigh", "max")
USD_MIN, USD_MAX = 1, 500
STORIES_MAX, CYCLE_MAX, NOTE_MAX, WEEKS_MAX, WORD_MAX, TITLE_MAX = 15, 7, 2000, 8, 40, 300
LEAD_MIN = 90  # §61.4 a publish hour of the same day is this long after the build starts
DAYS_A_MONTH = 30
FA_DIGITS = FL.FA_DIGITS
TZ = ZoneInfo(FL.TEHRAN)
HUB_FA = "Claude سرور هاب"
OWNER_FA = "مدیر کل"
SEED_NOTE_FA = "ساخته شد از روند کدی هاب"
DAY_NAMES_FA = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")
EFFORT_FA = {"high": "زیاد", "xhigh": "خیلی زیاد", "max": "بیشترین"}
KIND_FA = {"reel": "ریلز", "stories": "استوری", "short": "شورت", "video": "ویدیو",
           "article": "مقاله", "tg_post": "پست تلگرام"}  # fmt: skip

# §61.4 one Persian line per field
HOUR_FA = "ساعت باید به شکل ۱۴:۰۰ باشد"
SAME_MINUTE_FA = "این ساعت با ریلز {hm} همین پیج هم‌دقیقه است"
SAME_MINUTE_STORY_FA = "این ساعت با استوری {hm} همین پیج هم‌دقیقه است"
LEAD_FA = "هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد"
CAP_FA = "سقف روز باید بین ۱ و ۵۰۰ دلار باشد"
STORIES_MAX_FA = "حداکثر ۱۵ استوری"
STORIES_MIN_FA = "دست‌کم یک ساعت استوری لازم است"
STORIES_HERE_FA = "ساعت استوری فقط برای اتوماسیون استوری است"
TWICE_FA = "این ساعت دو بار آمده است: {hm}"
HOURS_COUNT_FA = "دست‌کم یک و حداکثر ۸ ساعت انتشار لازم است (یکی برای هر هفته‌ی دور)"
MODEL_FA = "این مدل در فهرست مدل‌های مجاز نیست"
EFFORT_BAD_FA = "سطح فکر باید یکی از high، xhigh یا max باشد"
CYCLE_FA = "چرخه حداکثر ۷ نوع دارد و هر نوع حداکثر ۴۰ نویسه است"
DAYS_FA = "دست‌کم یک روز از شنبه (۰) تا جمعه (۶) را انتخاب کن، هر کدام یک بار"
NOTE_FA = "یادداشت حداکثر ۲۰۰۰ نویسه است"
DATE_FA = "تاریخ باید به شکل ۲۰۲۶-۱۱-۱۸ باشد"
WORD_FA = "برای کلمه‌ی ثابت، خود کلمه را بنویس (حداکثر ۴۰ نویسه)"
WORD_MODE_FA = "حالت کلمه باید fixed یا fresh باشد"
TITLE_FA = "عنوان باید ۱ تا ۳۰۰ نویسه باشد"
UNTIL_FA = "پایان توقف باید روزی بعد از امروز باشد"
PAST_DAY_FA = "این روز گذشته است"
NOT_FOUND_FA = "این اتوماسیون پیدا نشد."
OK_FA = "روبه‌راه"
LAST_FAILED_FA = "اجرای آخر به نتیجه نرسید"
N8N_DOWN_FA = "n8n خاموش است؛ هاب خودش اجرا کرد"
CLOCK_DOWN_FA = "ساعت اتوماسیون‌ها کار نمیکند"


# ------------------------------------------------------------------ shapes --
class FlowDefSchedule(BaseModel):
    hours: list[str | None]
    best_week: bool
    days: list[int]
    stories: list[str]
    trigger_at: str
    same_day: bool
    start: date
    when_fa: str = ""


class FlowDefBudget(BaseModel):
    usd_cap: float
    month_estimate_usd: float
    envelope_usd: float | None = None
    envelope_left_usd: float | None = None
    over_envelope: bool = False


class FlowDefNext(BaseModel):
    build_at: datetime
    publish_at: datetime
    kind_fa: str | None = None


class FlowDefToday(BaseModel):
    runs: int = 0
    published: int = 0
    cost_usd: float = 0.0


class FlowDefHealth(BaseModel):
    state: Literal["ok", "warn", "down"] = "ok"
    note_fa: str = ""


Kind = Literal["reel", "stories", "short", "video", "article", "tg_post"]


class FlowDef(BaseModel):
    ref: str
    key: str
    company: str
    company_fa: str
    channel: str
    account: str
    title_fa: str
    kit: str
    kit_fa: str
    kind: Kind
    state: Literal["on", "off", "paused"]
    paused_until: date | None = None
    schedule: FlowDefSchedule
    model: str
    model_fa: str
    effort: Literal["high", "xhigh", "max"]
    budget: FlowDefBudget
    cycle: list[str] = Field(default_factory=list)
    story_word_mode: Literal["fixed", "fresh"]
    story_word: str | None = None
    note_fa: str | None = None
    pair: str | None = None
    recipe: str | None = None
    version: int
    next: FlowDefNext | None = None
    today: FlowDefToday = Field(default_factory=FlowDefToday)
    month_cost_usd: float = 0.0
    health: FlowDefHealth = Field(default_factory=FlowDefHealth)
    alerts_open: int = 0
    legacy_ref: str
    created_at: datetime
    updated_at: datetime


class FlowList(BaseModel):
    items: list[FlowDef]
    health: list[FS.Health] = Field(default_factory=list)
    today: FlowDefToday = Field(default_factory=FlowDefToday)


class ModelOption(BaseModel):
    id: str
    name_fa: str
    efforts: list[str]


class UsdRange(BaseModel):
    min: int = USD_MIN
    max: int = USD_MAX


class Kit(BaseModel):
    key: str
    title_fa: str
    about_fa: str = ""
    kinds: list[str] = Field(default_factory=list)
    avg_usd: float | None = None
    avg_minutes: float | None = None
    used_on: list[str] = Field(default_factory=list)


class FlowOptions(BaseModel):
    models: list[ModelOption]
    efforts: list[str] = Field(default_factory=lambda: list(EFFORTS))
    usd_cap: UsdRange = Field(default_factory=UsdRange)
    stories_max: int = STORIES_MAX
    cycle_max: int = CYCLE_MAX
    note_max: int = NOTE_MAX
    kits: list[Kit] = Field(default_factory=list)


class FlowDefSchedulePatch(Model):
    """Any part of the schedule; `best_week` follows the hours (a null hour is that week's best)."""

    hours: list[str | None] | None = Field(default=None, max_length=50)
    best_week: bool | None = None
    days: list[int] | None = Field(default=None, max_length=50)
    stories: list[str] | None = Field(default=None, max_length=50)
    trigger_at: str | None = Field(default=None, max_length=20)
    same_day: bool | None = None
    start: str | None = Field(default=None, max_length=20)


class FlowDefPatch(Model):
    schedule: FlowDefSchedulePatch | None = None
    model: str | None = Field(default=None, max_length=100)
    effort: str | None = Field(default=None, max_length=20)
    usd_cap: float | None = None
    cycle: list[str] | None = Field(default=None, max_length=50)
    story_word_mode: str | None = Field(default=None, max_length=20)
    story_word: str | None = Field(default=None, max_length=200)
    note_fa: str | None = Field(default=None, max_length=10_000)
    title_fa: str | None = Field(default=None, max_length=1000)
    note_change_fa: str | None = Field(default=None, max_length=500)


class FlowDefStateIn(Model):
    state: Literal["on", "off"]


class FlowDefPauseIn(Model):
    until: date | None = None


class FlowDefSkipIn(Model):
    day: date
    skip: bool = True


class FlowDefRunNowIn(Model):
    day: date | None = None


class FlowDefRunNow(BaseModel):
    run: FS.FlowRunRef


# ------------------------------------------------------------------- bodies --
def schedule_of(flow: FL.Flow) -> dict[str, Any]:
    out = {
        "hours": list(flow.hours), "best_week": None in flow.hours, "days": list(flow.days),
        "stories": list(flow.stories), "trigger_at": flow.trigger_at, "same_day": flow.same_day,
        "start": flow.start.isoformat(),
    }  # fmt: skip
    if getattr(flow, "rotate", ""):  # ⟨2026-11-26⟩ a new hour every day (FL.hour_index)
        out["rotate"] = flow.rotate
    return out


def body_of(flow: FL.Flow) -> dict[str, Any]:
    """§61.1 a version's body: every field a save may change."""
    return {
        "title_fa": flow.title_fa, "schedule": schedule_of(flow), "model": flow.model,
        "effort": flow.effort or "max", "usd_cap": float(flow.usd_cap), "cycle": list(flow.cycle),
        "story_word_mode": "fixed" if flow.story_word else "fresh",
        "story_word": flow.story_word or None, "note_fa": flow.note_fa or None,
    }  # fmt: skip


def seed_rows() -> list[dict[str, Any]]:
    """Migration 0070's seed: every flow of FLOWS as it is in code, the pilots too."""
    return [
        {
            "ord": i,
            "key": f.key,
            "company": f.company,
            "channel": f.channel,
            "account": f.account,
            "title_fa": f.title_fa,
            "kit": f.kit,
            "kind": "stories" if f.stories else "reel",
            "schedule": schedule_of(f),
            "story": f.story,
            "model": f.model,
            "model_from": f.model_from.isoformat() if f.model_from else None,
            "effort": f.effort or "max",
            "usd_cap": str(f.usd_cap),
            "budget_tokens": f.budget_tokens,
            "cycle": list(f.cycle),
            "story_word": f.story_word or None,
            "n8n": f.n8n,
            "pair": f.pair or None,
            "recipe": f.recipe or None,
            "note_fa": f.note_fa or None,
            "body": body_of(f),
        }
        for i, f in enumerate(FL.FLOWS.values())
    ]


# ------------------------------------------------------------ Persian lines --
def fa(v: Any) -> str:
    return str(v).translate(FA_DIGITS)


def model_name(model: str) -> str:
    """`claude-opus-5-5` → «Opus 5.5» (the apps never write a model's name of their own)."""
    if not model:
        return "Opus 5.5"
    if model.startswith("gemini-4-hydrogen-"):  # ⟨2026-11-27⟩ Antigravity's Gemini 4 Hydrogen
        return f"Hydrogen 4 ({model.removeprefix('gemini-4-hydrogen-')})"
    parts = model.removeprefix("claude-").split("-")
    nums = [p for p in parts if p.isdigit()]
    words = [p.capitalize() for p in parts if not p.isdigit()]
    return " ".join([*words, ".".join(nums)]).strip() if nums else model


def _hours_fa(hours: list[Any]) -> str:
    return fa("، ".join(h if h else "پربازدیدترین ساعت" for h in hours)) or "—"


def _days_fa(days: list[Any]) -> str:
    got = sorted({int(d) for d in days if isinstance(d, int) and 0 <= d <= 6})
    if got == list(FL.ALL_DAYS):
        return "هر روز"
    return "، ".join(DAY_NAMES_FA[d] for d in got) or "—"


def _value_fa(field: str, v: Any) -> str:
    if v is None or v == "" or v == []:
        return "—"
    if field == "schedule.hours":
        return _hours_fa(list(v))
    if field == "schedule.stories":
        return fa("، ".join(v))
    if field == "schedule.days":
        return _days_fa(list(v))
    if field == "schedule.same_day":
        return "همان روز انتشار" if v else "روز پیش از انتشار"
    if field == "schedule.start":
        try:
            return FL.fa_day(date.fromisoformat(str(v)))
        except ValueError:
            return fa(v)
    if field == "model":
        return model_name(str(v))
    if field == "effort":
        return EFFORT_FA.get(str(v), str(v))
    if field == "usd_cap":
        return fa(f"{Decimal(str(v)).normalize():f} دلار")
    if field == "cycle":
        return "، ".join(str(x) for x in v)
    if field == "story_word_mode":
        return "ثابت" if v == "fixed" else "هر روز تازه"
    return fa(str(v)[:200])


LABEL_FA = {
    "title_fa": "عنوان", "schedule.hours": "ساعت انتشار هفته‌های دور",
    "schedule.days": "روزهای هفته", "schedule.stories": "ساعت استوری‌ها",
    "schedule.trigger_at": "شروع ساخت", "schedule.same_day": "روز ساخت",
    "schedule.start": "شروع دور هفته‌ها", "model": "مدل", "effort": "سطح فکر",
    "usd_cap": "سقف هزینه‌ی روز", "cycle": "چرخه‌ی نوع‌ها", "story_word_mode": "کلمه‌ی جواب استوری",
    "story_word": "کلمه‌ی ثابت", "note_fa": "یادداشت",
}  # fmt: skip


def _flat(body: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in body.items() if k != "schedule"}
    for k, v in (body.get("schedule") or {}).items():
        if k != "best_week":
            out[f"schedule.{k}"] = v
    return out


def changes_of(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    """§61.3 what a save changed, one Persian line each («چه عوض میشود»)."""
    b, a = _flat(before), _flat(after)
    return [
        {
            "field": k,
            "label_fa": LABEL_FA.get(k, k),
            "before_fa": _value_fa(k, b.get(k)),
            "after_fa": _value_fa(k, a.get(k)),
        }
        for k in LABEL_FA
        if b.get(k) != a.get(k)
    ]


# ------------------------------------------------------------------- reading --
async def load(tx: Tx, ref: str, *, lock: bool = False) -> FL.Flow:
    """A flow by its `AF-…` ref, or by the `N8:<key>` of §59.7.1. 404 when there is no row."""
    from hq_api.domain import flow_view as FV

    key = FV.key_of(ref)
    if AF_REF.fullmatch(ref):
        where, arg = "f.ref = :v", ref
    elif key is not None:
        where, arg = "f.key = :v", key
    else:
        raise ApiError(404, "not_found", f"no flow {ref}", message_fa=NOT_FOUND_FA)
    row = await tx.first(
        FL.FLOW_SQL + f" WHERE {where}" + (" FOR UPDATE OF f" if lock else ""),
        v=arg,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no flow {ref}", message_fa=NOT_FOUND_FA)
    return FL.from_row(row)


async def allowed_models(tx: Tx) -> list[str]:
    """§61.3 (39.1) the models a flow's workshop turn CAN run on: the workshop runner's own list
    (domain/hands.MODELS; ⟨2026-11-20⟩ Opus 5.5 only, never Fable), not the LLM router's (the flows
    run on the workshop). The
    owner's «every flow on Opus 5.5 at xhigh» is the rows' value, not this list."""
    del tx
    from hq_api.domain import hands as HANDS

    return list(HANDS.MODELS)


async def options(tx: Tx) -> FlowOptions:
    models = [ModelOption(id=m, name_fa=model_name(m), efforts=list(EFFORTS))
              for m in await allowed_models(tx)]  # fmt: skip
    kits: dict[str, Kit] = {}
    for flow in (await FL.active_flows(tx)).values():
        if not flow.ref:
            continue
        k = kit_key(flow)
        kit = kits.setdefault(k, Kit(key=k, title_fa=f"کیت {k}"))
        kind = kind_of_flow(flow)
        if kind not in kit.kinds:
            kit.kinds.append(kind)
        if flow.account and flow.account not in kit.used_on:
            kit.used_on.append(flow.account)
        kit.about_fa = "، ".join(x for x in (kit.about_fa, flow.title_fa) if x)[:500]
    return FlowOptions(models=models, kits=list(kits.values()))


def kind_of_flow(flow: FL.Flow) -> Kind:
    """What a day of it makes: its stories, DotCoin's long video (row kind `video`), ⟨2026-11-18⟩ a
    site's SEO day (row kind `article`), else a reel."""
    if flow.stories:
        return "stories"
    kind = getattr(flow, "kind", "")
    if kind == "video":
        return "video"
    return "article" if kind == "article" else "reel"


def kit_key(flow: FL.Flow) -> str:
    return flow.kit.rstrip("/").rsplit("/", 1)[-1] or flow.kit


async def _company(tx: Tx, code: str) -> dict[str, Any]:
    row = await tx.first("SELECT id, name_fa FROM core.companies WHERE code = :c", c=code)
    return dict(row) if row is not None else {"id": None, "name_fa": ""}


def _month_start(now: datetime) -> datetime:
    from hq_api.domain.gov_common import jalali_month_start

    first = jalali_month_start(now.astimezone(TZ).date())
    return datetime.combine(first, time(0, 0), TZ).astimezone(UTC)


async def month_estimate(tx: Tx, flow: FL.Flow, usd_cap: float) -> float:
    """§61.4 the day's cap × 30, with the account's other flows that are not off."""
    others = 0.0
    if flow.account:
        for f in (await FL.active_flows(tx)).values():
            if f.ref and f.key != flow.key and f.account == flow.account and f.state != "off":
                others += float(f.usd_cap)
    return round((usd_cap + others) * DAYS_A_MONTH, 2)


async def budget(tx: Tx, flow: FL.Flow) -> FlowDefBudget:
    """⟨1.39⟩ the owner, 2026-11-17: «این موارد پاکت نمیخواد»: no month envelope for what publishes;
    the cap is the day's aim (a day past it goes on), its month estimate shown beside it."""
    est = await month_estimate(tx, flow, float(flow.usd_cap))
    return FlowDefBudget(usd_cap=float(flow.usd_cap), month_estimate_usd=est)


async def next_of(tx: Tx, flow: FL.Flow, company_id: Any, now: datetime) -> FlowDefNext | None:
    """The next day the clock will start (its build and its publish), within two weeks."""
    if flow.state == "off" or company_id is None:
        return None
    today = now.astimezone(TZ).date()
    for i in range(15):
        day = today + timedelta(days=i)
        if FL.held_why(flow, day) is not None:
            continue
        build = FL.trigger_of(flow, day)
        at, _ = await FL.slot_of(tx, flow, day, company_id)
        if at <= now:
            continue
        if build < now and await FL.day_made(tx, flow, day, at):
            continue
        return FlowDefNext(build_at=build, publish_at=at, kind_fa=FL.kind_of(flow, day) or None)
    return None


async def _today(tx: Tx, flow: FL.Flow, now: datetime) -> tuple[FlowDefToday, float]:
    from hq_api.domain import flow_view as FV

    runs, usd = await FV._today_cost(tx, flow)
    start = datetime.combine(now.astimezone(TZ).date(), time(0, 0), TZ).astimezone(UTC)
    published = await tx.scalar(
        """SELECT count(*) FROM infra.server_jobs j
           WHERE j.kind = 'publish' AND j.state = 'done' AND j.finished_at >= :t
             AND NOT (j.args ? 'rule_for')
             AND coalesce(j.result ->> 'external_id', '') NOT IN ('')
             AND j.result ->> 'external_id' NOT LIKE 'pub:%'
             AND j.args -> 'session' ->> 'order' IN (
                 SELECT run_meta -> 'flow' ->> 'order' FROM work.work
                 WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'key' = :k)""",
        t=start,
        k=flow.key,
    )
    month = await tx.scalar(
        """SELECT COALESCE(SUM(c.equiv_cost_usd), 0) FROM llm.calls c JOIN work.work w
             ON w.ref = c.work_ref AND w.parent_id IS NULL
           WHERE w.run_meta -> 'flow' ->> 'key' = :k AND c.started_at >= :t""",
        k=flow.key,
        t=_month_start(now),
    )
    today = FlowDefToday(runs=runs, published=int(published or 0), cost_usd=usd)
    return today, round(float(Decimal(str(month or 0))), 2)


async def health_of(tx: Tx, hub: Any, flow: FL.Flow, now: datetime) -> FlowDefHealth:
    """P1: the clock's state and the last day's; the alerts of §61.6 are P2."""
    from hq_api.domain import flow_auto as FA
    from hq_api.domain import flow_view as FV

    clock = await tx.first(
        "SELECT max(last_tick_at) AS t, max(last_fallback_at) AS f FROM growth.flow_clock"
    )
    tick = clock["t"] if clock else None
    backup = clock["f"] if clock else None
    if tick is None or now - tick > FA.NO_TICK:
        if backup is not None and now - backup <= FA.NO_TICK:
            return FlowDefHealth(state="warn", note_fa=N8N_DOWN_FA)
        if tick is not None:
            return FlowDefHealth(state="down", note_fa=CLOCK_DOWN_FA)
    days = await FV._days(tx, flow, 1)
    if days:
        last = await FV.run_ref(tx, hub, days[0])
        if last.state == "failed":
            return FlowDefHealth(state="warn", note_fa=LAST_FAILED_FA)
    return FlowDefHealth(state="ok", note_fa=OK_FA)


async def render(tx: Tx, hub: Any, flow: FL.Flow, now: datetime | None = None) -> FlowDef:
    from hq_api.domain import flow_view as FV

    now = now or datetime.now(UTC)
    co = await _company(tx, flow.company)
    row = await tx.one(
        "SELECT id, created_at, updated_at FROM automations.flows WHERE ref = :r", r=flow.ref
    )
    alerts = await tx.scalar(
        "SELECT count(*) FROM automations.alerts WHERE flow_id = :f AND closed_at IS NULL",
        f=row["id"],
    )
    nxt = await next_of(tx, flow, co["id"], now)
    today, month = await _today(tx, flow, now)
    sch = schedule_of(flow)
    when_day = nxt.publish_at.astimezone(TZ).date() if nxt else None
    return FlowDef(
        ref=flow.ref, key=flow.key, company=flow.company, company_fa=co["name_fa"] or "",
        channel=flow.channel, account=flow.account, title_fa=flow.title_fa, kit=kit_key(flow),
        kit_fa=f"کیت {kit_key(flow)}", kind=kind_of_flow(flow),
        state=flow.state,
        paused_until=flow.paused_until,
        schedule=FlowDefSchedule(**{**sch, "start": flow.start}, when_fa=FV.when_fa(flow, when_day)),
        model=flow.model, model_fa=model_name(flow.model),
        effort=flow.effort or "max",
        budget=await budget(tx, flow), cycle=list(flow.cycle),
        story_word_mode="fixed" if flow.story_word else "fresh",
        story_word=flow.story_word or None, note_fa=flow.note_fa or None, pair=flow.pair or None,
        recipe=flow.recipe or None, version=flow.version, next=nxt, today=today,
        month_cost_usd=month, health=await health_of(tx, hub, flow, now),
        alerts_open=int(alerts or 0), legacy_ref=FV.ref_of(flow.key),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )  # fmt: skip


async def list_flows(
    tx: Tx, hub: Any, company: str | None, account: str | None, channel: str | None
) -> FlowList:
    from hq_api.domain import automation_board as BOARD

    now = datetime.now(UTC)
    items = []
    for flow in (await FL.active_flows(tx)).values():
        if not flow.ref or (company and flow.company != company):
            continue
        if (account and flow.account != account.lstrip("@")) or (
            channel and flow.channel != channel
        ):
            continue
        items.append(await render(tx, hub, flow, now))
    # the off ones last (§61.8), else in ref order
    items.sort(key=lambda d: (d.state == "off", d.ref))
    today = FlowDefToday(
        runs=sum(i.today.runs for i in items), published=sum(i.today.published for i in items),
        cost_usd=round(sum(i.today.cost_usd for i in items), 2),
    )  # fmt: skip
    return FlowList(items=items, health=await BOARD.health(tx, hub, now), today=today)


# ------------------------------------------------------------------ checking --
def _hm_ok(v: Any) -> bool:
    return isinstance(v, str) and HM.fullmatch(v) is not None


def _min(hm: str) -> int:
    hh, mm = (int(x) for x in hm.split(":"))
    return hh * 60 + mm


QUIET_END_MIN = 8 * 60
NIGHT_FA = "هیچ انتشاری بین ساعت ۰۰:۰۰ تا ۰۸:۰۰ به وقت تهران نیست؛ ساعتی از ۰۸:۰۰ به بعد بگذار."


async def errors_of(tx: Tx, flow: FL.Flow, body: dict[str, Any]) -> list[dict[str, str]]:
    """§61.4 what a save may hold: one Persian line per field (the first fault of each)."""
    errs: dict[str, str] = {}

    def bad(field: str, message: str) -> None:
        errs.setdefault(field, message)

    s = body["schedule"]
    hours, stories, trig = list(s["hours"]), list(s["stories"]), s["trigger_at"]
    if not 1 <= len(hours) <= WEEKS_MAX:
        bad("schedule.hours", HOURS_COUNT_FA)
    for h in hours:
        if h is not None and not _hm_ok(h):
            bad("schedule.hours", HOUR_FA)
    if not _hm_ok(trig):
        bad("schedule.trigger_at", HOUR_FA)
    stories_flow = bool(flow.stories)
    if not stories_flow and stories:
        bad("schedule.stories", STORIES_HERE_FA)
    if stories_flow and not stories:
        bad("schedule.stories", STORIES_MIN_FA)
    if len(stories) > STORIES_MAX:
        bad("schedule.stories", STORIES_MAX_FA)
    # ⟨2026-11-26⟩ the owner: nothing goes out between 00:00 and 08:00 Tehran (making is fine)
    for field, hs in (("schedule.hours", hours), ("schedule.stories", stories)):
        if any(h is not None and _hm_ok(h) and _min(h) < QUIET_END_MIN for h in hs):
            bad(field, NIGHT_FA)
    seen: set[str] = set()
    for h in stories:
        if not _hm_ok(h):
            bad("schedule.stories", HOUR_FA)
        elif h in seen:
            bad("schedule.stories", TWICE_FA.format(hm=fa(h)))
        seen.add(str(h))
    if s["same_day"] and _hm_ok(trig):
        for field, hs in (("schedule.hours", hours), ("schedule.stories", stories)):
            if any(_hm_ok(h) and _min(h) - _min(trig) < LEAD_MIN for h in hs):
                bad(field, LEAD_FA)
    days = s["days"]
    if (not days or len(set(days)) != len(days)
            or any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in days)):  # fmt: skip
        bad("schedule.days", DAYS_FA)
    try:
        date.fromisoformat(str(s["start"]))
    except ValueError:
        bad("schedule.start", DATE_FA)
    if flow.account:  # §61.4 never on the minute of the same page's reel (or story)
        for other in (await FL.active_flows(tx)).values():
            if other.key == flow.key or other.account != flow.account or not other.ref:
                continue
            # ⟨2026-11-17⟩ a long video goes to YouTube, never into the page's Instagram grid
            # (⟨2026-11-18⟩ nor a site's SEO day)
            if {getattr(flow, "kind", ""), getattr(other, "kind", "")} & set(FL.OFF_IG_KINDS):
                continue
            if stories_flow and not other.stories:
                hit = next((h for h in stories if h in other.hours), None)
                if hit:
                    bad("schedule.stories", SAME_MINUTE_FA.format(hm=fa(hit)))
            elif not stories_flow and other.stories:
                hit = next((h for h in hours if h and h in other.stories), None)
                if hit:
                    bad("schedule.hours", SAME_MINUTE_STORY_FA.format(hm=fa(hit)))
    if body["model"] not in await allowed_models(tx):
        bad("model", MODEL_FA)
    if body["effort"] not in EFFORTS:
        bad("effort", EFFORT_BAD_FA)
    try:
        cap = Decimal(str(body["usd_cap"]))
        if not (USD_MIN <= cap <= USD_MAX) or cap != cap.quantize(Decimal("0.01")):
            bad("usd_cap", CAP_FA)
    except (InvalidOperation, ValueError):
        bad("usd_cap", CAP_FA)
    cycle = body["cycle"]
    if len(cycle) > CYCLE_MAX or any(not str(c).strip() or len(str(c)) > WORD_MAX for c in cycle):
        bad("cycle", CYCLE_FA)
    if body["story_word_mode"] not in ("fixed", "fresh"):
        bad("story_word_mode", WORD_MODE_FA)
    elif body["story_word_mode"] == "fixed":
        w = (body.get("story_word") or "").strip()
        if not w or len(w) > WORD_MAX:
            bad("story_word", WORD_FA)
    if len(body.get("note_fa") or "") > NOTE_MAX:
        bad("note_fa", NOTE_FA)
    title = (body.get("title_fa") or "").strip()
    if not 1 <= len(title) <= TITLE_MAX:
        bad("title_fa", TITLE_FA)
    return [{"field": k, "message_fa": v} for k, v in errs.items()]


def merged(before: dict[str, Any], patch: FlowDefPatch) -> dict[str, Any]:
    """The body after a save: the fields the patch names, the rest as they were."""
    after: dict[str, Any] = json.loads(json.dumps(before))
    given = patch.model_dump(exclude_unset=True)
    sch = given.pop("schedule", None) or {}
    sch.pop("best_week", None)  # (it follows the hours)
    after["schedule"].update({k: v for k, v in sch.items() if v is not None})
    after["schedule"]["best_week"] = None in after["schedule"]["hours"]
    given.pop("note_change_fa", None)
    for k, v in given.items():
        if v is None and k not in ("story_word", "note_fa"):
            continue
        after[k] = v
    if isinstance(after.get("title_fa"), str):
        after["title_fa"] = " ".join(after["title_fa"].split())
    if after.get("story_word_mode") == "fresh":
        after["story_word"] = None
    if isinstance(after.get("story_word"), str):
        after["story_word"] = after["story_word"].strip() or None
    if not after.get("note_fa"):
        after["note_fa"] = None
    if isinstance(after.get("usd_cap"), int | float):
        after["usd_cap"] = float(after["usd_cap"])
    return after


# ------------------------------------------------------------------- saving --
async def _audit(
    tx: Tx, who: Principal, flow: FL.Flow, company_id: Any, verb: str, before: Any, after: Any,
    *, step_up: bool = False,
) -> None:  # fmt: skip
    """§61.3 `automation.flow.<verb>` with what it was and what it is now."""
    b = json.dumps(before, ensure_ascii=False, default=str)
    a = json.dumps(after, ensure_ascii=False, default=str)
    await audit.record(
        tx, who, company_id=company_id, action=f"automation.flow.{verb}", action_class="A2",
        target_kind="automation", target_ref=flow.ref, summary=f"{b} -> {a}"[:500], step_up=step_up,
    )  # fmt: skip


async def _changed(tx: Tx, flow: FL.Flow, state: str, version: int) -> None:
    await events.emit(tx, flow.company, "automation.changed", flow.ref,
                      {"ref": flow.ref, "state": state, "version": version})  # fmt: skip


async def switch(tx: Tx, who: Principal, flow: FL.Flow, state: str) -> bool:
    """§61.2 the owner's switch (`on` ends a pause too): True when it changed. The board's switch
    of `N8:<key>` comes here too (flows.set_on)."""
    if flow.state == state:
        return False
    co = await _company(tx, flow.company)
    await tx.exec(
        """UPDATE automations.flows SET state = :s, paused_until = NULL, updated_at = now()
           WHERE ref = :r""",
        s=state,
        r=flow.ref,
    )
    await _audit(tx, who, flow, co["id"], "state",
                 {"state": flow.state, "paused_until": flow.paused_until}, {"state": state})  # fmt: skip
    await _changed(tx, flow, state, flow.version)
    return True


async def patch(ctx: Any, tx: Tx, request: Any, ref: str, body: FlowDefPatch) -> FlowDef:
    """§61.3 a save: `If-Match` is the version it was read at (409 version_conflict otherwise)."""
    from hq_api.http import if_match

    want = if_match(request)
    flow, _ = await save(ctx, tx, request, ref, body, want)
    return await render(tx, ctx.hub, flow)


async def save(
    ctx: Any, tx: Tx, request: Any, ref: str, body: FlowDefPatch, want: int | None,
    verb: str = "update",
) -> tuple[FL.Flow, bool]:  # fmt: skip
    """A new version of the flow: §61.4's checks (422 invalid_flow); the cap is one tap, up or
    down (⟨1.39⟩ the owner, 2026-11-17: no envelope for what publishes); the changes in Persian,
    the audit `automation.flow.<verb>`, the event. Returns the flow as saved and whether anything
    changed."""
    flow = await load(tx, ref, lock=True)
    if want is not None and want != flow.version:
        raise ApiError(409, "version_conflict", f"{flow.ref} is at version {flow.version}")
    before = body_of(flow)
    after = merged(before, body)
    errors = await errors_of(tx, flow, after)
    if errors:
        raise ApiError(422, "invalid_flow", "the save holds fields it may not", errors=errors,
                       message_fa=errors[0]["message_fa"])  # fmt: skip
    changes = changes_of(before, after)
    if not changes:
        return flow, False
    co = await _company(tx, flow.company)
    rise = float(after["usd_cap"]) > float(before["usd_cap"])
    if ctx.who is not HUB:  # (the hub's own change, update_by_hub, is no principal's request)
        await ctx.hub.policy.require("lines", {
            "principal": ctx.who.opa(), "op": "flow.update",
            "target": {"automation": flow.ref, "budget_rise": rise, "over_envelope": False},
            "context": {"step_up": False},
        })  # fmt: skip
    version = flow.version + 1
    sch = after["schedule"]
    await tx.exec(
        """UPDATE automations.flows SET title_fa = :title, schedule = CAST(:sch AS jsonb),
               model = :model, model_from = CASE WHEN model = :model THEN model_from END,
               effort = :effort, usd_cap = :cap, cycle = :cycle, story_word = :word,
               note_fa = :note, version = :v, updated_at = now()
           WHERE ref = :r""",
        title=after["title_fa"], sch=json.dumps(sch, ensure_ascii=False), model=after["model"],
        effort=after["effort"], cap=Decimal(str(after["usd_cap"])), cycle=list(after["cycle"]),
        word=after["story_word"], note=after["note_fa"], v=version, r=flow.ref,
    )  # fmt: skip
    note = " ".join((body.note_change_fa or "").split()) or None
    await tx.exec(
        """INSERT INTO automations.flow_versions (company_id, flow_id, version, by_kind, by_code,
               by_fa, note_fa, changes, body)
           SELECT company_id, id, :v, :bk, :bc, :bf, :n, CAST(:ch AS jsonb), CAST(:b AS jsonb)
           FROM automations.flows WHERE ref = :r""",
        v=version, bk=ctx.who.kind, bc=ctx.who.code[:64],
        bf=OWNER_FA if ctx.who.is_owner else HUB_FA, n=note,
        ch=json.dumps(changes, ensure_ascii=False), b=json.dumps(after, ensure_ascii=False), r=flow.ref,
    )  # fmt: skip
    keys = {c["field"] for c in changes}
    flat_b, flat_a = _flat(before), _flat(after)
    await _audit(tx, ctx.who, flow, co["id"], verb,
                 {k: flat_b.get(k) for k in sorted(keys)} | {"version": flow.version},
                 {k: flat_a.get(k) for k in sorted(keys)} | {"version": version})  # fmt: skip
    fresh = await load(tx, flow.ref)
    await _changed(tx, fresh, fresh.state, version)
    return fresh, True


async def _policy(ctx: Any, op: str, flow: FL.Flow, **target: Any) -> None:
    await ctx.hub.policy.require("lines", {
        "principal": ctx.who.opa(), "op": op, "target": {"automation": flow.ref, **target},
        "context": {"step_up": False},
    })  # fmt: skip


async def set_state(ctx: Any, tx: Tx, ref: str, state: str) -> FlowDef:
    flow = await load(tx, ref, lock=True)
    await _policy(ctx, "flow.state", flow, state=state)
    await switch(tx, ctx.who, flow, state)
    return await render(tx, ctx.hub, await load(tx, ref))


async def pause(ctx: Any, tx: Tx, ref: str, until: date | None) -> FlowDef:
    """§61.2 `paused` (the clock skips the days before `until`; no `until`: till `state on`)."""
    flow = await load(tx, ref, lock=True)
    today = datetime.now(TZ).date()
    if until is not None and until <= today:
        raise ApiError(422, "invalid_flow", "until is not after today", message_fa=UNTIL_FA,
                       errors=[{"field": "until", "message_fa": UNTIL_FA}])  # fmt: skip
    await _policy(ctx, "flow.pause", flow)
    co = await _company(tx, flow.company)
    await tx.exec(
        """UPDATE automations.flows SET state = 'paused', paused_until = :u, updated_at = now()
           WHERE ref = :r""",
        u=until,
        r=flow.ref,
    )
    await _audit(tx, ctx.who, flow, co["id"], "pause",
                 {"state": flow.state, "paused_until": flow.paused_until},
                 {"state": "paused", "paused_until": until})  # fmt: skip
    await _changed(tx, flow, "paused", flow.version)
    return await render(tx, ctx.hub, await load(tx, ref))


async def skip(ctx: Any, tx: Tx, ref: str, day: date, on: bool) -> FlowDef:
    """§61.3 one day skipped by the clock (and by n8n's call); `skip: false` undoes it."""
    flow = await load(tx, ref, lock=True)
    if day < datetime.now(TZ).date():
        raise ApiError(422, "invalid_flow", "the day is past", message_fa=PAST_DAY_FA,
                       errors=[{"field": "day", "message_fa": PAST_DAY_FA}])  # fmt: skip
    await _policy(ctx, "flow.skip", flow)
    kept = {d for d in flow.skips if d >= datetime.now(TZ).date() - timedelta(days=7)}
    skips = sorted(kept | {day} if on else kept - {day})
    co = await _company(tx, flow.company)
    await tx.exec(
        "UPDATE automations.flows SET skips = :s, updated_at = now() WHERE ref = :r",
        s=skips,
        r=flow.ref,
    )
    await _audit(tx, ctx.who, flow, co["id"], "skip", {"day": day, "skip": day in flow.skips},
                 {"day": day, "skip": on})  # fmt: skip
    await _changed(tx, flow, flow.state, flow.version)
    return await render(tx, ctx.hub, await load(tx, ref))


MADE_SQL = """SELECT ref, run_meta -> 'flow' ->> 'order' AS run FROM work.work
    WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'key' = :k
      AND run_meta -> 'flow' ->> 'day' = :d
      AND (status NOT IN ('failed', 'cancelled') OR run_meta -> 'flow' ? 'sent'
           OR close_reason = 'duplicate_day')
    ORDER BY created_at DESC LIMIT 1"""


async def run_ref_of(tx: Tx, hub: Any, order: str) -> FS.FlowRunRef | None:
    from hq_api.domain import flow_view as FV

    d = await FV._day_by_order(tx, order)
    return await FV.run_ref(tx, hub, d) if d is not None else None


def default_day(flow: FL.Flow) -> date:
    """run-now without a day: the day the next post goes out (today for a same-day flow)."""
    return datetime.now(TZ).date() + timedelta(days=0 if flow.same_day else 1)


# ================================================================== P2 (39.1) ==
class FlowChange(BaseModel):
    field: str
    label_fa: str
    before_fa: str
    after_fa: str


class FlowVersion(BaseModel):
    version: int
    at: datetime
    by_fa: str
    note_fa: str | None = None
    changes: list[FlowChange] = Field(default_factory=list)
    body: dict[str, Any]


class FlowRollbackIn(Model):
    version: int = Field(ge=1)


class FlowDefRun(BaseModel):
    run: str
    day: date | None = None
    state: str
    topic_fa: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    cost_usd: float = 0.0
    publications: list[Any] = Field(default_factory=list)
    note_fa: str = ""


class FlowDefRuns(BaseModel):
    items: list[FlowDefRun] = Field(default_factory=list)
    next: str | None = None


class SuccessCount(BaseModel):
    ok: int = 0
    all: int = 0


class CostToday(BaseModel):
    today: float = 0.0
    month: float = 0.0


class FlowDefHealthPage(BaseModel):
    state: Literal["ok", "warn", "down"]
    note_fa: str
    last_run: FS.FlowRunRef | None = None
    success_30d: SuccessCount = Field(default_factory=SuccessCount)
    cost: CostToday = Field(default_factory=CostToday)
    next: FlowDefNext | None = None
    alerts: list[Any] = Field(default_factory=list)


class FlowDefCreate(Model):
    account: str = Field(min_length=1, max_length=100)
    channel: str = Field(default="instagram", max_length=40)
    kit: str = Field(min_length=1, max_length=100)
    title_fa: str = Field(min_length=1, max_length=1000)
    schedule: FlowDefSchedulePatch
    model: str = Field(max_length=100)
    effort: str = Field(max_length=20)
    usd_cap: float
    cycle: list[str] | None = Field(default=None, max_length=50)
    story_word_mode: str | None = Field(default=None, max_length=20)
    story_word: str | None = Field(default=None, max_length=200)


class KitRequestIn(Model):
    account: str = Field(min_length=1, max_length=100)
    note_fa: str = Field(min_length=1, max_length=2000)


class KitRequestOut(BaseModel):
    order: str
    work: str | None = None


class WeekTotals(BaseModel):
    runs: int = 0
    published: int = 0
    cost_usd: float = 0.0


class WeekDay(BaseModel):
    day: date
    published: int = 0
    planned: int = 0


class WeekAccount(BaseModel):
    company: str
    company_fa: str
    account: str
    runs: int = 0
    published: int = 0
    cost_usd: float = 0.0
    flows: int = 0
    best: Any | None = None


class FlowWeek(BaseModel):
    from_: date = Field(alias="from")
    to: date
    totals: WeekTotals = Field(default_factory=WeekTotals)
    by_day: list[WeekDay] = Field(default_factory=list)
    accounts: list[WeekAccount] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


ROLLBACK_FA = "برگشت به نسخه‌ی {v}"
NO_VERSION_FA = "این نسخه پیدا نشد."
NO_KIT_FA = "این کیت پیدا نشد."
NO_PAGE_FA = "این پیج در هیچ شرکتی ثبت نشده است."
MADE_FROM_KIT_FA = "ساخته شد از کیت {kit}"
KIT_ORDER_FA = (
    "کیت تازه برای پیج @{account}، به خواسته‌ی مدیر کل: {note}\n\n"
    "یک نمونه‌ی کوتاه بساز و همین‌جا برای دیدن مدیر کل بگذار (منتشر نمیشود). بعد از «بله» مدیر کل، "
    "کیت با همه‌ی قاعده‌ها و ابزارهایش در پوشه‌ی کیت‌های کارگارگاه ثبت میشود و در «کیت‌ها» می‌آید."
)


# --------------------------------------------------------------- the versions --
async def versions(tx: Tx, ref: str) -> list[FlowVersion]:
    """§61.3 every save of the flow, newest first; none is ever deleted."""
    flow = await load(tx, ref)
    rows = await tx.all(
        """SELECT v.* FROM automations.flow_versions v JOIN automations.flows f ON f.id = v.flow_id
           WHERE f.ref = :r ORDER BY v.version DESC""",
        r=flow.ref,
    )
    out = []
    for r in rows:
        changes = r["changes"]
        changes = json.loads(changes) if isinstance(changes, str) else changes
        body = r["body"]
        body = json.loads(body) if isinstance(body, str) else body
        out.append(FlowVersion(version=r["version"], at=r["at"], by_fa=r["by_fa"],
                               note_fa=r["note_fa"], changes=[FlowChange(**c) for c in changes or []],
                               body=dict(body or {})))  # fmt: skip
    return out


async def rollback(ctx: Any, tx: Tx, ref: str, version: int) -> FlowDef:
    """§61.3 «برگشت به این نسخه»: that version's body saved again as the next version, through
    §61.4's checks (422 invalid_flow); nothing is deleted. Audit `automation.flow.rollback`."""
    flow = await load(tx, ref, lock=True)
    body = await tx.scalar(
        """SELECT v.body FROM automations.flow_versions v JOIN automations.flows f ON f.id = v.flow_id
           WHERE f.ref = :r AND v.version = :v""",
        r=flow.ref,
        v=version,
    )
    if body is None:
        raise ApiError(404, "not_found", f"no version {version}", message_fa=NO_VERSION_FA)
    b = json.loads(body) if isinstance(body, str) else dict(body)
    sch = {k: v for k, v in (b.get("schedule") or {}).items() if k != "best_week"}
    patch = FlowDefPatch(
        schedule=FlowDefSchedulePatch(**sch), model=b.get("model"), effort=b.get("effort"),
        usd_cap=b.get("usd_cap"), cycle=b.get("cycle"), story_word_mode=b.get("story_word_mode"),
        story_word=b.get("story_word"), note_fa=b.get("note_fa"), title_fa=b.get("title_fa"),
        note_change_fa=ROLLBACK_FA.format(v=fa(version)),
    )  # fmt: skip
    saved, _ = await save(ctx, tx, ctx.request, flow.ref, patch, None, verb="rollback")
    return await render(tx, ctx.hub, saved)


# ------------------------------------------------------------------- the runs --
async def runs(tx: Tx, hub: Any, ref: str, limit: int, before: str | None) -> FlowDefRuns:
    """§61.3 the flow's days, newest first: state, topic, cost (llm.calls.equiv_cost_usd) and the
    day's publications (media.publications of this flow and day); the timeline stays
    `GET /line-runs/{run}`."""
    from hq_api.domain import flow_view as FV
    from hq_api.domain import publications as PB

    flow = await load(tx, ref)
    days = await FV._days(tx, flow, limit + 1, before)
    items = []
    for d in days[:limit]:
        r = await FV.run_ref(tx, hub, d)
        day = str(d["flow"].get("day") or "") or None
        rows = await tx.all(
            PB.SET_SQL
            + " WHERE p.source ->> 'flow_key' = :k AND p.source ->> 'day' = :d"
            + PB.SET_FIRST
            + " ORDER BY p.at, p.ref",
            k=flow.key,
            d=day,
        )
        items.append(FlowDefRun(
            run=r.ref, day=date.fromisoformat(day) if day else None, state=r.state,
            topic_fa=r.topic_fa, started_at=d["created_at"], ended_at=d["closed_at"],
            cost_usd=float(r.cost_usd or 0), publications=[PB._card(dict(x)) for x in rows],
            note_fa=r.note_fa,
        ))  # fmt: skip
    nxt = items[-1].run if len(days) > limit and items else None
    return FlowDefRuns(items=items, next=nxt)


# ----------------------------------------------------------------- the health --
async def health_page(tx: Tx, hub: Any, ref: str) -> FlowDefHealthPage:
    """§61.3 the flow's health: the clock's and the last day's, its open alerts, the last 30 days'
    success, today's and the month's cost, the next day."""
    from hq_api.domain import flow_alerts as AL
    from hq_api.domain import flow_view as FV

    now = datetime.now(UTC)
    flow = await load(tx, ref)
    h = await health_of(tx, hub, flow, now)
    alerts = await AL.of_flow(tx, flow)
    if alerts and h.state == "ok":
        h = FlowDefHealth(state="warn", note_fa=alerts[0].note_fa)
    if any(a.kind in ("late", "clock_missed") and a.notified for a in alerts):
        h = FlowDefHealth(state="down", note_fa=next(a.note_fa for a in alerts if a.notified))
    since = now - timedelta(days=30)
    days = [d for d in await FV._days(tx, flow, 60) if d["created_at"] >= since]
    refs = [await FV.run_ref(tx, hub, d) for d in days]
    ok = sum(1 for r in refs if r.state in ("done", "waiting"))
    co = await _company(tx, flow.company)
    today, month = await _today(tx, flow, now)
    return FlowDefHealthPage(
        state=h.state, note_fa=h.note_fa, last_run=refs[0] if refs else None,
        success_30d=SuccessCount(ok=ok, all=len(refs)), cost=CostToday(today=today.cost_usd, month=month),
        next=await next_of(tx, flow, co["id"], now), alerts=alerts,
    )  # fmt: skip


async def graph(tx: Tx, ref: str) -> FS.FlowGraph:
    """§61.3 the map of §59.7.1, from the flow's steps (its kit's recipe)."""
    from hq_api.domain import flow_view as FV

    return FV.graph_of(await load(tx, ref))


# ------------------------------------------------------------------- the kits --
async def kits(tx: Tx) -> list[Kit]:
    """§61.5 the kits that run today (the flows using them), with their last 30 days' mean cost
    and minutes per day."""
    got = (await options(tx)).kits
    since = datetime.now(UTC) - timedelta(days=30)
    flows = [f for f in (await FL.active_flows(tx)).values() if f.ref]
    for kit in got:
        keys = [f.key for f in flows if kit_key(f) == kit.key]
        row = await tx.first(
            """SELECT avg(c.usd) AS usd, avg(extract(epoch FROM (w.closed_at - w.created_at)) / 60)
                      FILTER (WHERE w.closed_at IS NOT NULL) AS minutes
               FROM work.work w LEFT JOIN LATERAL (
                   SELECT COALESCE(SUM(equiv_cost_usd), 0) AS usd FROM llm.calls
                   WHERE work_ref = w.ref) c ON true
               WHERE w.parent_id IS NULL AND w.created_at >= :s
                 AND w.run_meta -> 'flow' ->> 'key' = ANY(:k)""",
            s=since,
            k=keys,
        )
        if row is not None and row["usd"] is not None:
            kit.avg_usd = round(float(row["usd"]), 2)
        if row is not None and row["minutes"] is not None:
            kit.avg_minutes = round(float(row["minutes"]), 1)
    return got


HUB = Principal(kind="service", code="hub", role="service")
# (⟨2026-11-19⟩ tg_post: a page's Telegram channel)
KINDS = ("reel", "stories", "video", "article", "tg_post")


async def create_by_hub(
    tx: Tx, hub: Any, *, key: str, account: str, kit: str, title_fa: str, kind: str,
    schedule: dict[str, Any], model: str, effort: str, usd_cap: float, budget_tokens: int,
    note_fa: str = "", recipe: str = "", channel: str = "instagram", skips: tuple[date, ...] = (),
    story: bool = False, story_word: str = "", cycle: tuple[str, ...] = (),
) -> FlowDef:  # fmt: skip
    """⟨2026-11-17⟩ A new automation made by the hub itself (a kit no flow uses yet, e.g. DotCoin's
    long YouTube videos, kind `video`; ⟨2026-11-18⟩ its SEO days, kind `article`, channel `web`): the
    same checks as a save (§61.4), version 1 and its audit
    row, `on`; the hub's clock runs it. Not a route: the owner's own «بساز و روشن کن» is `create`.
    A key that exists is refused (a second call changes nothing). `skips`: days its clock leaves out
    (a first day the hub must not make yet). ⟨2026-11-18⟩ A stories flow (kind `stories`) names its
    hours in `schedule["stories"]`; `story_word` is its fixed reply word ("" = a fresh one a day);
    `story`: a reel flow posts its reel as a story too; `cycle`: the day's kinds in turn."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", key):
        raise ApiError(422, "invalid_flow", "bad key")
    if kind not in KINDS:
        raise ApiError(422, "invalid_flow", "bad kind")
    if (kind == "stories") != bool(schedule.get("stories")):
        raise ApiError(422, "invalid_flow", "a stories flow, and only it, names its story hours")
    from hq_api.domain.dispatch import ROUTE_TOKENS_MAX

    if not 10_000 <= budget_tokens <= ROUTE_TOKENS_MAX:  # (its day's order carries it: Route)
        raise ApiError(422, "invalid_flow", f"budget_tokens outside 10000..{ROUTE_TOKENS_MAX}")
    if key in await FL.active_flows(tx):
        raise ApiError(409, "conflict", f"the flow {key} exists")
    account = account.strip().lstrip("@")
    co = await company_of_account(tx, hub, account)
    if co is None:
        raise ApiError(422, "invalid_flow", "the page is not registered", message_fa=NO_PAGE_FA)
    start = date.fromisoformat(str(schedule["start"]))
    hours = tuple(schedule.get("hours") or ())
    draft = FL.Flow(
        key=key, company=co.code, account=account, title_fa=" ".join(title_fa.split()), kit=kit,
        start=start, hours=hours, budget_tokens=budget_tokens, n8n="",
        trigger_at=str(schedule.get("trigger_at") or "08:00"), usd_cap=Decimal(str(usd_cap)),
        model=model, same_day=bool(schedule.get("same_day", True)), recipe=recipe, effort=effort,
        note_fa=note_fa, days=tuple(int(d) for d in schedule.get("days") or FL.ALL_DAYS),
        channel=channel, stories=tuple(str(h) for h in schedule.get("stories") or ()),
        story=bool(story), story_word=" ".join(story_word.split()), cycle=tuple(cycle),
        rotate=str(schedule.get("rotate") or ""),
    )  # fmt: skip
    if getattr(draft, "kind", None) != kind:  # (FL.Flow without `kind`: a hub not yet deployed)
        object.__setattr__(draft, "kind", kind)
    after = body_of(draft)
    errors = await errors_of(tx, draft, after)
    if errors:
        raise ApiError(422, "invalid_flow", "the automation holds fields it may not", errors=errors,
                       message_fa=errors[0]["message_fa"])  # fmt: skip
    ref = await tx.scalar(
        """INSERT INTO automations.flows (key, company_id, channel, account, title_fa, kit, kind,
               state, schedule, story, model, effort, usd_cap, budget_tokens, cycle, story_word,
               n8n, pair, recipe, note_fa, skips)
           VALUES (:key, :co, :ch, :acc, :title, :kit, :kind, 'on', CAST(:sch AS jsonb), :story,
                   :model, :effort, :cap, :tokens, :cycle, :word, '', NULL, :recipe, :note, :skips)
           RETURNING ref""",
        key=key, co=co.id, ch=channel, acc=account, title=draft.title_fa, kit=kit, kind=kind,
        story=draft.story, word=draft.story_word or None, cycle=list(draft.cycle),
        sch=json.dumps(after["schedule"], ensure_ascii=False), model=model, effort=effort,
        cap=Decimal(str(usd_cap)), tokens=budget_tokens, recipe=recipe or None, note=note_fa or None,
        skips=sorted(skips),
    )  # fmt: skip
    flow = await load(tx, str(ref))
    await tx.exec(
        """INSERT INTO automations.flow_versions (company_id, flow_id, version, by_kind, by_code,
               by_fa, note_fa, body)
           SELECT company_id, id, 1, :bk, :bc, :bf, :n, CAST(:b AS jsonb)
           FROM automations.flows WHERE ref = :r""",
        bk=HUB.kind, bc=HUB.code, bf=HUB_FA, n=MADE_FROM_KIT_FA.format(kit=kit.rstrip("/").rsplit("/", 1)[-1]),
        b=json.dumps(body_of(flow), ensure_ascii=False), r=flow.ref,
    )  # fmt: skip
    await _audit(tx, HUB, flow, co.id, "create", None, body_of(flow) | {"kind": kind})
    await _changed(tx, flow, flow.state, flow.version)
    return await render(tx, hub, flow)


async def update_by_hub(
    tx: Tx, hub: Any, ref: str, body: FlowDefPatch, *, drop_skips: tuple[date, ...] = ()
) -> tuple[FL.Flow, bool]:
    """⟨2026-11-17⟩ A change the hub itself makes on the owner's word given elsewhere (his order to
    the hub's Claude, e.g. DotCoin's long videos every day): a new version through `save` (the
    same checks, the changes in Persian, audit `automation.flow.update`), as the hub's service.
    `drop_skips`: days skipped before that the change makes days again (audited too)."""
    from types import SimpleNamespace

    flow, changed = await save(SimpleNamespace(hub=hub, who=HUB), tx, None, ref, body, None)
    gone = [d for d in drop_skips if d in flow.skips]
    if gone:
        await tx.exec(
            "UPDATE automations.flows SET skips = :s, updated_at = now() WHERE ref = :r",
            s=sorted(set(flow.skips) - set(gone)),
            r=flow.ref,
        )
        co = await _company(tx, flow.company)
        await _audit(tx, HUB, flow, co["id"], "skip", {"skips": [d.isoformat() for d in flow.skips]},
                     {"skips": [d.isoformat() for d in sorted(set(flow.skips) - set(gone))]})  # fmt: skip
        flow = await load(tx, flow.ref)
    return flow, changed or bool(gone)


async def _kit_flow(tx: Tx, key: str) -> FL.Flow:
    flow = next((f for f in (await FL.active_flows(tx)).values() if f.ref and kit_key(f) == key),
                None)  # fmt: skip
    if flow is None:
        raise ApiError(404, "not_found", f"no kit {key}", message_fa=NO_KIT_FA)
    return flow


async def kit_graph(tx: Tx, key: str) -> FS.FlowGraph:
    """§61.5 a kit's map before an automation is made from it (the map of a flow using it)."""
    from hq_api.domain import flow_view as FV

    return FV.graph_of(await _kit_flow(tx, key))


async def company_of_account(tx: Tx, hub: Any, account: str) -> Any | None:
    """The company whose registered pages (its publish path, §44.5) hold this account."""
    from hq_api.domain import session_publish as SPB

    for c in await hub.companies.all():
        if c.kind == "holding":
            continue
        route = await SPB._route(tx, c.id)
        if account in route["accounts"]:
            return c
    return None


def _slug(v: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", v.lower()).strip("_")
    return s if s[:1].isalpha() else f"f_{s}"


async def create(ctx: Any, tx: Tx, body: FlowDefCreate) -> FlowDef:
    """§61.5 «بساز و روشن کن»: a new automation from a kit for a registered page, checked as a save
    (§61.4), `on` at version 1. No n8n workflow: the hub's clock runs it."""
    account = body.account.strip().lstrip("@")
    co = await company_of_account(tx, ctx.hub, account)
    if co is None:
        raise ApiError(422, "invalid_flow", "the page is not registered", message_fa=NO_PAGE_FA,
                       errors=[{"field": "account", "message_fa": NO_PAGE_FA}])  # fmt: skip
    try:
        kit = await _kit_flow(tx, body.kit)
    except ApiError as exc:
        raise ApiError(422, "invalid_flow", "no such kit", message_fa=NO_KIT_FA,
                       errors=[{"field": "kit", "message_fa": NO_KIT_FA}]) from exc  # fmt: skip
    sch = body.schedule
    stories = tuple(sch.stories or ())
    hours = tuple(sch.hours or ((stories[0],) if stories else ()))
    taken = set(await FL.active_flows(tx))
    base = _slug(f"{account}_{kit_key(kit)}")[:36]
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    start = datetime.now(TZ).date()
    with contextlib.suppress(ValueError):
        start = date.fromisoformat(sch.start) if sch.start else start
    others = [f for f in (await FL.active_flows(tx)).values()
              if f.ref and f.account == account and not f.stories and not f.pair]  # fmt: skip
    draft = FL.Flow(
        key=key, company=co.code, account=account, title_fa=" ".join(body.title_fa.split()),
        kit=kit.kit, start=start, hours=hours, story=False, budget_tokens=kit.budget_tokens,
        n8n="", trigger_at=sch.trigger_at or kit.trigger_at, usd_cap=Decimal("1"),
        cycle=tuple(body.cycle or ()), model=body.model, pair=others[0].key if others and not stories else "",
        stories=stories, same_day=kit.same_day if sch.same_day is None else sch.same_day,
        story_word=(body.story_word or "") if body.story_word_mode == "fixed" else "",
        recipe=kit.recipe, effort=body.effort, days=tuple(sch.days) if sch.days else FL.ALL_DAYS,
        channel=body.channel,
    )  # fmt: skip
    after = body_of(draft) | {"usd_cap": body.usd_cap, "effort": body.effort,
                              "story_word_mode": body.story_word_mode or "fresh",
                              "story_word": body.story_word}  # fmt: skip
    after["schedule"]["start"] = sch.start or start.isoformat()
    errors = await errors_of(tx, draft, after)
    if errors:
        raise ApiError(422, "invalid_flow", "the automation holds fields it may not", errors=errors,
                       message_fa=errors[0]["message_fa"])  # fmt: skip
    await ctx.hub.policy.require("lines", {
        "principal": ctx.who.opa(), "op": "flow.use", "target": {"automation": key},
        "context": {"step_up": False},
    })  # fmt: skip
    ref = await tx.scalar(
        """INSERT INTO automations.flows (key, company_id, channel, account, title_fa, kit, kind,
               state, schedule, story, model, effort, usd_cap, budget_tokens, cycle, story_word,
               n8n, pair, recipe)
           VALUES (:key, :co, :ch, :acc, :title, :kit, :kind, 'on', CAST(:sch AS jsonb), false,
                   :model, :effort, :cap, :tokens, :cycle, :word, '', :pair, :recipe)
           RETURNING ref""",
        key=key, co=co.id, ch=body.channel, acc=account, title=draft.title_fa, kit=draft.kit,
        kind="stories" if stories else "reel", sch=json.dumps(after["schedule"], ensure_ascii=False),
        model=body.model, effort=body.effort, cap=Decimal(str(body.usd_cap)),
        tokens=draft.budget_tokens, cycle=list(draft.cycle),
        word=after["story_word"] if after["story_word_mode"] == "fixed" else None,
        pair=draft.pair or None, recipe=draft.recipe or None,
    )  # fmt: skip
    flow = await load(tx, str(ref))
    await tx.exec(
        """INSERT INTO automations.flow_versions (company_id, flow_id, version, by_kind, by_code,
               by_fa, note_fa, body)
           SELECT company_id, id, 1, :bk, :bc, :bf, :n, CAST(:b AS jsonb)
           FROM automations.flows WHERE ref = :r""",
        bk=ctx.who.kind, bc=ctx.who.code[:64], bf=OWNER_FA if ctx.who.is_owner else HUB_FA,
        n=MADE_FROM_KIT_FA.format(kit=kit_key(kit)), b=json.dumps(body_of(flow), ensure_ascii=False),
        r=flow.ref,
    )  # fmt: skip
    await _audit(tx, ctx.who, flow, co.id, "create", None, body_of(flow))
    await _changed(tx, flow, flow.state, flow.version)
    return await render(tx, ctx.hub, flow)


async def kit_request(ctx: Any, request: Any, background: Any, body: KitRequestIn) -> KitRequestOut:
    """§61.5 «کیت تازه»: a direct session with the workshop, as the owner's DotCoin pilot was made;
    its sample comes to that session for his yes. Requires `Idempotency-Key` (the order's)."""
    from hq_api.routes.orders import OrderIn, place_order

    account = body.account.strip().lstrip("@")
    async with ctx.tx() as tx:
        co = await company_of_account(tx, ctx.hub, account)
    if co is None:
        raise ApiError(422, "invalid_flow", "the page is not registered", message_fa=NO_PAGE_FA,
                       errors=[{"field": "account", "message_fa": NO_PAGE_FA}])  # fmt: skip
    text = KIT_ORDER_FA.format(account=account, note=" ".join(body.note_fa.split()))
    out = await place_order(ctx, request, background, OrderIn(text=text, company=co.code))
    got = out.model_dump() if hasattr(out, "model_dump") else json.loads(bytes(out.body))
    work = next((r.get("work_ref") for r in got.get("routes") or [] if r.get("work_ref")), None)
    return KitRequestOut(order=str(got["ref"]), work=work)


# ------------------------------------------------------------------- the week --
async def week(tx: Tx, from_: date | None) -> FlowWeek:
    """§61.7 the automations' week (Tehran, Saturday first): runs, posts and cost, each day's posts
    and what is planned, and each page's line. `best` waits for `insights` (null)."""
    today = datetime.now(TZ).date()
    start = from_ or today - timedelta(days=FL.day_index(today))
    end = start + timedelta(days=6)
    lo = datetime.combine(start, time(0, 0), TZ).astimezone(UTC)
    hi = datetime.combine(end + timedelta(days=1), time(0, 0), TZ).astimezone(UTC)
    flows = [f for f in (await FL.active_flows(tx)).values() if f.ref and f.account]
    pubs = await tx.all(
        """SELECT p.account, (p.at AT TIME ZONE 'Asia/Tehran')::date AS day, p.source ->> 'flow_key' AS k
           FROM media.publications p
           WHERE p.state = 'published' AND p.at >= :lo AND p.at < :hi
             AND p.source ->> 'flow_key' IS NOT NULL""",
        lo=lo,
        hi=hi,
    )
    works = await tx.all(
        """SELECT w.run_meta -> 'flow' ->> 'key' AS k,
                  (SELECT COALESCE(SUM(c.equiv_cost_usd), 0) FROM llm.calls c
                   WHERE c.work_ref = w.ref) AS usd
           FROM work.work w
           WHERE w.parent_id IS NULL AND w.run_meta ? 'flow'
             AND w.run_meta -> 'flow' ->> 'day' BETWEEN :a AND :b""",
        a=start.isoformat(),
        b=end.isoformat(),
    )
    by_day = []
    for i in range(7):
        day = start + timedelta(days=i)
        planned = 0
        if day >= today:
            for f in flows:
                # (⟨2026-11-18⟩ a long video or a site's SEO day is no post of the page's)
                if getattr(f, "kind", "") in FL.OFF_IG_KINDS:
                    continue
                if f.state == "on" and FL.held_why(f, day) is None:
                    planned += len(f.stories) or 1
        by_day.append(WeekDay(day=day, published=sum(1 for p in pubs if p["day"] == day),
                              planned=planned))  # fmt: skip
    accounts: dict[tuple[str, str], WeekAccount] = {}
    names = {r["code"]: r["name_fa"] or r["code"]
             for r in await tx.all("SELECT code, name_fa FROM core.companies")}  # fmt: skip
    key_of = {f.key: f for f in flows}
    for f in flows:
        accounts.setdefault((f.company, f.account), WeekAccount(
            company=f.company, company_fa=names.get(f.company, f.company), account=f.account,
        )).flows += 1  # fmt: skip
    for w in works:
        wf = key_of.get(str(w["k"]))
        if wf is not None:
            a = accounts[(wf.company, wf.account)]
            a.runs += 1
            a.cost_usd = round(a.cost_usd + float(w["usd"] or 0), 2)
    for p in pubs:
        pf = key_of.get(str(p["k"]))
        if pf is not None:
            accounts[(pf.company, pf.account)].published += 1
    items = sorted(accounts.values(), key=lambda a: (a.company, a.account))
    totals = WeekTotals(runs=sum(a.runs for a in items), published=len(pubs),
                        cost_usd=round(sum(a.cost_usd for a in items), 2))  # fmt: skip
    return FlowWeek(from_=start, to=end, totals=totals, by_day=by_day, accounts=items)


async def week_lines_fa(tx: Tx, from_: date | None = None) -> list[str]:
    """The same week in a few Persian lines (one per page), for the owner's weekly summary."""
    w = await week(tx, from_)
    return [
        fa(
            f"@{a.account} ({a.company_fa}): {a.published} انتشار، {a.runs} اجرا، "
            f"{a.cost_usd:.2f} دلار"
        )
        for a in w.accounts
    ]
