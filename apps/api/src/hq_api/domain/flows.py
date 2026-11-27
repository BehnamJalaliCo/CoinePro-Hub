"""⟨2026-11-13⟩ A working group's daily run, started by n8n, from the first second to the post.

The owner (F-0018): «بحث دکمه نیست باید اتوماتیک پشت صحنه انجام بشه … اون دکمه انتشارم قرار
نیست دیگه من بزنم و قراره اتوماتیک و اتوماسیونی باشه توسط n8n», «باید از اولین و تا آخرین لحظه
اتوماسیون بشه», and the hours: «۷ روز ساعت ۹:۳۰ به وقت تهران، ۷ روز ساعت ۱۴:۰۰ و ۷ روز ساعت
۱۹:۳۰ و هفته چهارم برحسب آنالیز بازدید ساعتی منتشر میشه که بیشتر بازدید رو داشته», «گزارش
کوتاه به من رو توی آپ توسط نوتیف بده».

A flow is one order a day (a session, held by the company's CEO as a direct session on the
workshop, at the owner's pace «خودکار»), made by n8n's signed call: its brief points at the
company's fixed kit (the files and rules of the session the flow was born in) and says when the
post goes out. When a direct turn of it leaves the whole package in `out/` (the video, its
story cut, the cover, `caption.txt`, `comment.txt`), the hub schedules the reel and the story on
IG-Hub for that hour (the reel's comment rule with it; the story's rule follows by itself), tells
the owner in one notification, and closes the session: nothing goes on spending. When the reel is
out, one more notification says so with its link.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import order_report as OR
from hq_api.domain import session_publish as SPB
from hq_api.principal import Principal

if TYPE_CHECKING:
    from starlette.requests import Request

log = logging.getLogger("hq_api.flows")

FLOW = Principal(kind="service", code="flow", role="service")
TEHRAN = "Asia/Tehran"
MONTHS_FA = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر",
             "دی", "بهمن", "اسفند")  # fmt: skip
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
# ⟨1.39⟩ §61.1 a flow's days: Saturday = 0 … Friday = 6
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class Flow:
    key: str
    company: str
    account: str
    title_fa: str
    kit: str
    # the first day of the four weeks; each week its hour, the fourth the best one (None)
    start: date
    hours: tuple[str | None, ...]
    story: bool = True
    budget_tokens: int = 3_000_000
    # ⟨2026-11-14⟩ the n8n workflow that calls it and when (Tehran), for the automations board
    n8n: str = ""
    trigger_at: str = "13:00"
    # ⟨2026-11-14⟩ the day's cost cap (USD); the owner for TradeYar: «هزینه هیچ محدودیتی نیست»,
    # so its flows keep only a guard against a run that never ends
    usd_cap: Decimal = Decimal("10")
    # ⟨2026-11-14⟩ a flow whose reel turns in a round (TradeYar's 12:00: education, an exchange's
    # campaign, the news and the market): the day's kind, from the first day, goes in its brief
    cycle: tuple[str, ...] = ()
    # ⟨2026-11-15⟩ the model its workshop turns run on ("" = the workshop's own, Opus 5.5); a test
    # flow publishes nothing (account "")
    model: str = ""
    # ⟨2026-11-15⟩ the first day the model makes (None = every day); the days before keep the
    # workshop's own
    model_from: date | None = None
    # ⟨2026-11-15⟩ the owner: «پرو چارت رو روزی دو تا بکنیم»: a second flow of the same page names
    # the first; its hour never falls on the first one's
    pair: str = ""
    # ⟨2026-11-15⟩ a stories flow (the owner: «استوری ضریب صد روزانه ۷ عدد»): the hours (Tehran) of
    # the day's picture stories, one each; the day's reply rule answers the account's story replies
    stories: tuple[str, ...] = ()
    # ⟨2026-11-15⟩ n8n makes the day it is called on (the page's news cannot wait a day); else
    # the next day
    same_day: bool = False
    # ⟨2026-11-16⟩ a stories flow whose replies are always answered on ONE word (the owner's
    # «لینک رو ریپلای کن»): every day's rule has it; IG-Hub answers with the oldest one,
    # whose reply is the same channel link ("" = a fresh word every day)
    story_word: str = ""
    # ⟨2026-11-16⟩ the steps the automations map shows («zaribsad», «dotcoin»; "" = by the kit)
    recipe: str = ""
    # ⟨2026-11-16⟩ the effort of its workshop turns ("" = the build's own, max); the owner for
    # DotCoin.me: «سازنده ویدیو مدل فیبل ۵.۲ افورت اکسترا» (xhigh)
    effort: str = ""
    # ⟨2026-11-16⟩ a line of its own at the end of the order (a size limit, say)
    note_fa: str = ""
    # ⟨1.39⟩ §61.1 what its row (automations.flows) holds besides; a flow of FLOWS with no row (the
    # migration's seed, a test's flow) has no ref, is on unless owner.settings.flows_off names it
    ref: str = ""
    state: str = "on"
    paused_until: date | None = None
    skips: tuple[date, ...] = ()
    days: tuple[int, ...] = ALL_DAYS
    channel: str = "instagram"
    version: int = 0
    # ⟨2026-11-17⟩ what a day makes: `reel` (and its stories), `stories`, or `video` (DotCoin's long
    # YouTube video: the hub's host uploader publishes it at the hour, never IG-Hub). ⟨2026-11-18⟩
    # `article`: a site's SEO day (dotcoin.me: a new long page and the day's fixes as one package;
    # the hub's host publisher checks it and puts it on the site at the hour, never IG-Hub)
    kind: str = "reel"
    # ⟨2026-11-26⟩ the owner for @bitmart: «ساعتش در روز برای پست متغیر از ۵ ساعت مختلف باشه و انتخاب ساعت‌ها
    # هم بدون ترتیب باشه»: `day_shuffle` = a new hour of `hours` EVERY day, each hour once in every round of
    # len(hours) days, the round's order shuffled (never the same hour two days running); "" = by week
    rotate: str = ""


# ⟨2026-11-18⟩ the kinds whose day never goes to IG-Hub (the hub's own host publisher takes it)
OFF_IG_KINDS = ("video", "article", "tg_post")  # (⟨2026-11-19⟩ a page's Telegram channel)


# ⟨2026-11-17⟩ DotCoin.me's twelve story slides a day, about one an hour (never on a reel's minute)
DOTCOIN_STORY_HOURS = (
    *("09:00", "10:15", "11:30", "12:30", "14:00", "15:00"),
    *("16:00", "17:15", "18:30", "19:30", "21:30", "23:00"),
)

# ⟨2026-11-17⟩ the owner: «هر چی اتوماسیونه بذار روی مدل اوپس ۵.۵ با افورت اکسترا»: every flow on
# Opus 5.5 at extra-high effort from its next day (a day already started keeps the model and effort
# its run_meta holds: «اگر الان در حال ساخت هستند بذار بسازه»)
XHIGH = "xhigh"

FLOWS = {
    "prochart_reels": Flow(
        key="prochart_reels",
        company="PC",
        account="theprochart",
        title_fa="ریلز روزانه‌ی پروچارت",
        kit="/home/studio/kits/prochart-reels",
        start=date(2026, 11, 14),
        hours=("09:30", "14:00", "19:30", None),
        n8n="hqFlowProchartReels1",
        model="claude-opus-5-5",
        effort=XHIGH,
    ),
    # ⟨2026-11-15⟩ the owner: «اگر بخواییم پرو چارت رو روزی دو تا بکنیم … اگر آره اونم هر روز دو تا
    # باشه»: the bank holds 730 topics (two a day for a year); the same kit, made later in the day,
    # at an hour of its own (each of the three hours tried two weeks of four)
    "prochart_reels_2": Flow(
        key="prochart_reels_2",
        company="PC",
        account="theprochart",
        title_fa="ریلز دوم پروچارت",
        kit="/home/studio/kits/prochart-reels",
        start=date(2026, 11, 14),  # (the first flow's weeks)
        hours=("19:30", "09:30", "14:00", None),
        n8n="hqFlowProchartReels2",
        trigger_at="16:30",
        pair="prochart_reels",
        model="claude-opus-5-5",
        effort=XHIGH,
    ),
    # ⟨2026-11-14⟩ the owner: TradeYar's page (@zarib100x since 11-26), a coin-profile reel at 19:00 every day
    # (what the coin is, how it was built, its advantages, today's price, its year), the video made
    # by Claude alone in code, the end inviting to buy on WEEX or LBank; cost has no limit
    # ⟨2026-11-14⟩ the owner: @zaribsad's 12:00 reel turns every day: education, an exchange's
    # campaign with the referral link, the news and the market; the news cannot be made a day
    # ahead, so every kind is made the same morning (n8n at 07:00 Tehran for that day)
    "zaribsad_noon": Flow(
        key="zaribsad_noon",
        company="TY",
        account="zarib100x",
        title_fa="ریلز چرخشی ضریب صد",
        kit="/home/studio/kits/zaribsad-noon",
        # (2026-11-15 is the owner's ZEC remake, the page's first reel: the round starts the day after)
        start=date(2026, 11, 16),
        hours=("12:00", "12:00", "12:00", "12:00"),
        budget_tokens=10_000_000,  # (the route allows at most 10M; the USD cap is the guard)
        n8n="hqFlowZaribsadNoon1",
        trigger_at="07:00",
        usd_cap=Decimal("100"),
        cycle=("آموزش", "کمپین صرافی", "خبر و بازار"),
        # ⟨2026-11-15⟩ the owner, after the two ZEC reels side by side: «با مدل فیبل ۵.۲ برای ضریب صد؛
        # ریلز امروز رو که هیچ، ولی از فردا»
        model="claude-opus-5-5",
        effort=XHIGH,
        same_day=True,
    ),
    "zaribsad_coin": Flow(
        key="zaribsad_coin",
        company="TY",
        account="zarib100x",
        title_fa="ریلز معرفی ارز ضریب صد",
        kit="/home/studio/kits/zaribsad-coin",
        start=date(2026, 11, 15),
        hours=("19:00", "19:00", "19:00", "19:00"),
        budget_tokens=10_000_000,  # (the route allows at most 10M; the USD cap is the guard)
        n8n="hqFlowZaribsadCoin1",
        trigger_at="14:00",
        usd_cap=Decimal("100"),
        model="claude-opus-5-5",
        effort=XHIGH,  # (as the 12:00 one: from tomorrow)
        same_day=True,
    ),
    # ⟨2026-11-15⟩ the owner: «اتوماسیون استوری ضریب صد روزانه ۷ عدد که مطالبی باشه که برای کاربر
    # جذاب باشه که وارد کانال سیگنال بشه و جواب‌های دایرکت استوری طوری باشه که کاربر رو ترغیب بکنه
    # برای ورود به کانال سیگنال vip»: seven photoreal picture stories a day, made the same morning
    "zaribsad_stories": Flow(
        key="zaribsad_stories",
        company="TY",
        account="zarib100x",
        title_fa="استوری‌های روزانه‌ی ضریب صد",
        kit="/home/studio/kits/zaribsad-stories",
        start=date(2026, 11, 16),
        hours=("08:30",),
        story=False,
        budget_tokens=10_000_000,
        n8n="hqFlowZaribsadStories1",
        trigger_at="06:00",
        usd_cap=Decimal("60"),
        model="claude-opus-5-5",
        effort=XHIGH,
        stories=("08:30", "10:30", "13:30", "15:30", "17:30", "20:30", "22:30"),
        same_day=True,
    ),
    # ⟨2026-11-17⟩ the owner («هم کاور و هم ریلز عالی بود»): the daily DotCoin.me
    # package, phase one. Two reels a day at fixed hours, «ساعت دو ریلز عالیه»: 13:00 educational,
    # 20:30 informational, each built the same day (the news cannot wait; the educational one has
    # the night for its Pinterest search, the owner: «باید توی n8n تایم داده بشه بهش»). Every comment
    # with the reel's word gets the lesson's summary in a DM («کامنت ها جواب دایرکت بگیرند»; the
    # site's link joins it later). Colour in three layers (kit 5f960440).
    "dotcoin_reels": Flow(
        key="dotcoin_reels",
        company="IG",
        account="dotcoinme",
        title_fa="ریلز آموزشی دات‌کوین",
        kit="/home/studio/kits/dotcoin-reels",
        start=date(2026, 11, 17),
        hours=("13:00", "13:00", "13:00", "13:00"),
        story=False,  # (the page's stories are their own flow)
        budget_tokens=10_000_000,
        n8n="hqFlowDotcoinReels1",
        trigger_at="00:30",
        same_day=True,
        usd_cap=Decimal("100"),
        cycle=("آموزشی",),
        model="claude-opus-5-5",
        effort=XHIGH,
        recipe="dotcoin",
        note_fa=(
            "به‌جز این‌ها، out/article.md (مقاله‌ی همین ریلز برای سایت dotcoin.me) را هم طبق کیت بنویس؛ "
            "لینک و دکمه‌ی مقاله در comment.txt می‌آید."
        ),
    ),
    "dotcoin_reels_2": Flow(
        key="dotcoin_reels_2",  # gitleaks:allow (a flow's name, not a key)
        company="IG",
        account="dotcoinme",
        title_fa="ریلز اطلاع‌رسانی دات‌کوین",
        kit="/home/studio/kits/dotcoin-reels",
        start=date(2026, 11, 17),
        hours=("20:30", "20:30", "20:30", "20:30"),
        story=False,
        budget_tokens=10_000_000,
        n8n="hqFlowDotcoinReels2",
        trigger_at="15:00",  # (the day's news as late as the build allows)
        same_day=True,
        usd_cap=Decimal("100"),
        cycle=("اطلاع‌رسانی",),
        model="claude-opus-5-5",
        effort=XHIGH,
        pair="dotcoin_reels",
        recipe="dotcoin",
        note_fa=(
            "به‌جز این‌ها، out/article.md (مقاله‌ی همین ریلز برای سایت dotcoin.me) را هم طبق کیت بنویس؛ "
            "لینک و دکمه‌ی مقاله در comment.txt می‌آید."
        ),
    ),
    # ⟨2026-11-17⟩ the owner: «ریلز عکس نداریم اصلا، منظورم تعدادی عکس برای استوری که هم آموزشی باشه و در
    # آینده هر وقت گفتم تبلیغاتی باشه» (12-15 a day), and «چت جی پی تی میتونه ۱۰ الی ۱۵ عکس رو یکجا
    # طراحی بکنه و تحویل بده در اسلاید های مجزا»: the day's lesson in twelve slides from ONE ChatGPT
    # chat (substitute.call images), one an hour or so through the day; a fresh reply word a day,
    # answered with the lesson's summary
    "dotcoin_stories": Flow(
        key="dotcoin_stories",
        company="IG",
        account="dotcoinme",
        title_fa="استوری‌های آموزشی دات‌کوین",
        kit="/home/studio/kits/dotcoin-stories",
        start=date(2026, 11, 17),
        hours=("09:00",),
        story=False,
        budget_tokens=10_000_000,
        n8n="hqFlowDotcoinStories1",
        trigger_at="04:00",
        usd_cap=Decimal("60"),
        model="claude-opus-5-5",
        effort=XHIGH,
        stories=DOTCOIN_STORY_HOURS,
        same_day=True,
        recipe="dotcoin",
    ),
}


def model_on(flow: Flow, day: date) -> str:
    """⟨2026-11-15⟩ The model a flow's day is made on ("" = the workshop's own)."""
    return flow.model if flow.model_from is None or day >= flow.model_from else ""


# --------------------------------------------------------- ⟨1.39⟩ the rows --
# §61.1 the flows are rows (automations.flows) the owner edits from the app; FLOWS above is only
# the migration's seed and, for a key no row has, the fallback (a test's own flow)
FLOW_SQL = """SELECT f.*, c.code AS company FROM automations.flows f
    JOIN core.companies c ON c.id = f.company_id"""


def _jd(v: Any) -> dict[str, Any]:
    got = json.loads(v) if isinstance(v, str) else v
    return dict(got or {})


def from_row(r: Any) -> Flow:
    """The in-memory flow of one automations.flows row."""
    s = _jd(r["schedule"])
    return Flow(
        key=str(r["key"]), company=str(r["company"]), account=str(r["account"] or ""),
        title_fa=str(r["title_fa"]), kit=str(r["kit"]), start=date.fromisoformat(str(s["start"])),
        hours=tuple(s.get("hours") or ()), story=bool(r["story"]),
        budget_tokens=int(r["budget_tokens"]), n8n=str(r["n8n"] or ""),
        trigger_at=str(s.get("trigger_at") or "13:00"), usd_cap=Decimal(str(r["usd_cap"])),
        cycle=tuple(r["cycle"] or ()), model=str(r["model"] or ""), model_from=r["model_from"],
        pair=str(r["pair"] or ""), stories=tuple(s.get("stories") or ()),
        same_day=bool(s.get("same_day")), story_word=str(r["story_word"] or ""),
        recipe=str(r["recipe"] or ""), effort=str(r["effort"] or ""), note_fa=str(r["note_fa"] or ""),
        ref=str(r["ref"]), state=str(r["state"]), paused_until=r["paused_until"],
        skips=tuple(r["skips"] or ()), days=tuple(int(d) for d in s.get("days") or ALL_DAYS),
        channel=str(r["channel"]), version=int(r["version"]), kind=str(r["kind"] or "reel"),
        rotate=str(s.get("rotate") or ""),
    )  # fmt: skip


async def active_flows(tx: Tx | None, *, on_only: bool = False) -> dict[str, Flow]:
    """Every flow the hub runs, by key: its rows (ref order), then a key of FLOWS no row has (the
    test fallback). `on_only`: those whose state is `on`."""
    out: dict[str, Flow] = {}
    if tx is not None:
        out = {str(r["key"]): from_row(r) for r in await tx.all(FLOW_SQL + " ORDER BY f.ref")}
    for key, flow in FLOWS.items():
        out.setdefault(key, flow)
    if on_only:
        off = await off_keys(tx) if tx is not None else set()
        out = {k: f for k, f in out.items() if f.state == "on" and (f.ref or k not in off)}
    return out


async def flow_by_key(tx: Tx | None, key: str) -> Flow | None:
    """One flow: its row, else (no row has the key) FLOWS' (the test fallback), else None."""
    if tx is not None and key:
        row = await tx.first(FLOW_SQL + " WHERE f.key = :k", k=key)
        if row is not None:
            return from_row(row)
    return FLOWS.get(key)


def day_index(day: date) -> int:
    """§61.1 Saturday = 0 … Friday = 6."""
    return (day.weekday() + 2) % 7


# ------------------------------------------------------------ the owner's switch --
OFF_WHY_FA = "این اتوماسیون خاموش است؛ با کلیدش در بخش اتوماسیون‌ها روشن میشود"


PAUSED_WHY_FA = "این اتوماسیون تا {until} متوقف است"
PAUSED_NO_END_FA = "این اتوماسیون متوقف است؛ با کلیدش در بخش اتوماسیون‌ها روشن میشود"
SKIPPED_WHY_FA = "مدیر کل این روز را رد کرده است"
NOT_ITS_DAY_FA = "این روز از روزهای این اتوماسیون نیست"
NOT_STARTED_FA = "این اتوماسیون از {start} شروع میشود"
# ⟨2026-11-18⟩ an automation an event starts, never the clock (@behnamjalali.tech's breaking news:
# domain/flow_events.py, called by the hub's watcher); its row is on the board like any other
EVENT_RECIPES = ("breaking",)
EVENT_FA = "این اتوماسیون با خبر تازه شروع میشود، نه با ساعت"


def on_event(flow: Flow) -> bool:
    return flow.recipe in EVENT_RECIPES


async def off_keys(tx: Tx) -> set[str]:
    """⟨2026-11-14⟩ the flows the owner switched off on the automations board (owner.settings).
    ⟨1.39⟩ a row's switch is its `state` (§61.2); this list holds only the keys no row has."""
    got = await tx.scalar("SELECT flows_off FROM owner.settings WHERE id = 1")
    return {str(k) for k in got or []}


async def is_off(tx: Tx, flow: Flow) -> bool:
    return flow.state == "off" if flow.ref else flow.key in await off_keys(tx)


def held_why(flow: Flow, day: date) -> str | None:
    """⟨1.39⟩ §61.2 why the clock (and n8n's call) makes nothing for this day: paused before its
    `paused_until`, the owner's skip, a day not among its `days`. ⟨2026-11-18⟩ A day before its
    `start` too: the clock looks at yesterday and today (or today and tomorrow), and a flow made to
    start tomorrow was started the same day (W-000625)."""
    if day < flow.start:
        return NOT_STARTED_FA.format(start=fa_day(flow.start))
    if flow.state == "paused":
        if flow.paused_until is None:
            return PAUSED_NO_END_FA
        if day < flow.paused_until:
            return PAUSED_WHY_FA.format(until=fa_day(flow.paused_until))
    if on_event(flow):
        return EVENT_FA
    if day in flow.skips:
        return SKIPPED_WHY_FA
    if day_index(day) not in flow.days:
        return NOT_ITS_DAY_FA
    return None


async def set_on(tx: Tx, who: Principal, key: str, on: bool) -> bool:
    """The owner's switch on one flow: True when it changed (audit `flow.switch`). ⟨1.39⟩ a row's
    switch writes its `state` (`on` ends a pause too; audit `automation.flow.state`)."""
    flow = await flow_by_key(tx, key)
    if flow is None:
        return False
    if flow.ref:
        from hq_api.domain import flow_defs as FD

        return await FD.switch(tx, who, flow, "on" if on else "off")
    off = await off_keys(tx)
    if (key not in off) == on:
        return False
    off = (off - {key}) if on else (off | {key})
    await tx.exec("UPDATE owner.settings SET flows_off = :k WHERE id = 1", k=sorted(off))
    co = await tx.one("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
    await audit.record(
        tx, who, company_id=co["id"], action="flow.switch", action_class="A2",
        target_kind="flow", target_ref=f"N8:{key}",
        summary=f"{'off -> on' if on else 'on -> off'} (n8n {flow.n8n or '-'})",
    )  # fmt: skip
    return True


def week_of(flow: Flow, day: date) -> int:
    """0, 1, 2, 3: the day's week in the four-week round (it starts again after the fourth)."""
    return max(0, (day - flow.start).days) // 7 % len(flow.hours)


def _round_order(key: str, n: int, k: int) -> list[int]:
    """Round k's order of the n hours: shuffled, the same every time it is asked (seeded by the
    flow's key and the round)."""
    import random

    order = list(range(n))
    random.Random(f"{key}:{k}").shuffle(order)  # noqa: S311 (a schedule, not a secret)
    return order


def hour_index(flow: Flow, day: date) -> int:
    """⟨2026-11-26⟩ Which of the flow's hours the day posts at: by week (week_of), or, `day_shuffle`,
    a different hour every day in an unordered round (no hour twice in a round, never the same hour
    two days running across rounds)."""
    n = len(flow.hours)
    if flow.rotate != "day_shuffle" or n < 2:
        return week_of(flow, day)
    d = max(0, (day - flow.start).days)
    k, i = divmod(d, n)
    order = _round_order(flow.key, n, k)
    if k > 0 and order[0] == _round_order(flow.key, n, k - 1)[-1]:
        order[0], order[1] = order[1], order[0]
    return order[i]


def fa_day(day: date) -> str:
    from hq_api.worker.jalali import to_jalali

    _, jm, jd = to_jalali(day)
    return f"{jd} {MONTHS_FA[jm - 1]}".translate(FA_DIGITS)


async def slot_of(tx: Tx, flow: Flow, day: date, company_id: UUID) -> tuple[datetime, str]:
    """When the day's post goes out (UTC) and how it was chosen, in Persian. The fourth week takes
    the hour the account's posts did best at (§49); too little data yet: the first week's hour."""
    tz = ZoneInfo(TEHRAN)
    hm = flow.stories[0] if flow.stories else flow.hours[hour_index(flow, day)]
    why = "ساعت ثابت این هفته"
    if flow.stories:
        why = "ساعت اولین استوری روز"
    elif flow.rotate == "day_shuffle":
        why = "ساعت چرخشی امروز"
    if hm is None:
        from hq_api.domain import best_hour as BH

        got = await BH.best(tx, company_id, flow.account, TEHRAN)
        if got.enough and got.hour:
            hm, why = str(got.hour), "پربازدیدترین ساعت"
        else:
            hm, why = flow.hours[0] or "09:30", "داده‌ی بازدید هنوز کم است؛ ساعت هفته‌ی اول"
    sibling = await flow_by_key(tx, flow.pair) if flow.pair else None
    if sibling is not None and not sibling.pair:
        theirs, _ = await slot_of(tx, sibling, day, company_id)
        their_hm = theirs.astimezone(tz).strftime("%H:%M")
        if _minutes(their_hm) == _minutes(str(hm)):
            # (both on the best hour) the tried hour farthest from the first one's, of both flows'
            # hours (⟨2026-11-16⟩ a flow may have one fixed hour)
            hm = max(
                (h for h in (*sibling.hours, *flow.hours) if h),
                key=lambda h: abs(_minutes(h) - _minutes(their_hm)),
            )
            why = "ساعت دور از ریلز اول روز"
    hh, mm = (int(x) for x in str(hm).split(":"))
    at = datetime.combine(day, time(hh, mm), tz).astimezone(UTC)
    return at, why


def _minutes(hm: str) -> int:
    hh, mm = (int(x) for x in hm.split(":"))
    return hh * 60 + mm


def story_times(flow: Flow, day: date) -> list[datetime]:
    """⟨2026-11-15⟩ When each of a stories flow's pictures goes out (UTC)."""
    tz = ZoneInfo(TEHRAN)
    out = []
    for hm in flow.stories:
        hh, mm = (int(x) for x in hm.split(":"))
        out.append(datetime.combine(day, time(hh, mm), tz).astimezone(UTC))
    return out


def at_fa(at: datetime) -> str:
    local = at.astimezone(ZoneInfo(TEHRAN))
    return f"{fa_day(local.date())} ساعت {local:%H:%M}".translate(FA_DIGITS)


def kind_of(flow: Flow, day: date) -> str:
    """The day's kind in a flow's round («» for a flow without one)."""
    if not flow.cycle or day < flow.start:
        return ""
    return flow.cycle[(day - flow.start).days % len(flow.cycle)]


# ⟨2026-11-18⟩ the owner: «نباید محتوای تکراری ارسال بشه». DotCoin's 11-18 reel («بلاک‌چین با یک
# مثال ساده») was 11-17's («بلاک‌چین مثل دفتر دنگ سفر») again: that one was made by hand, so the
# kit's bank never marked it. Every day's order now carries what the page already has.
DONE_KINDS = {
    "reel": ("reel",),
    "video": ("video",),
    "stories": ("story",),
    "tg_post": ("tg_post",),
}
DONE_MAX_CHARS = 4500  # (the order's text is at most 10 000 characters)
DONE_SQL = """SELECT coalesce(nullif(topic_fa, ''), title_fa) AS t, max(at) AS at
    FROM media.publications WHERE account = :a AND kind = ANY(:k)
      AND state IN ('scheduled', 'publishing', 'published', 'held') AND NOT source ? 'trial_of'
    GROUP BY 1 ORDER BY max(at) DESC LIMIT 300"""
NO_REPEAT_FA = (
    "قاعده‌ی مالک، تکرار ممنوع: موضوع‌هایی که این پیج تا امروز منتشر کرده یا در صف دارد (تازه‌ترین "
    "اول): {done}.\nموضوع امروز باید با همه‌ی این‌ها فرق کند. همان موضوع با عنوان، مثال، زاویه یا "
    "سبک دیگر هم تکرار است. فقط خبر واقعاً تازه درباره‌ی همان چیز تکرار نیست. اگر موضوع بانک کیت "
    "در این فهرست بود، آن را در بانک «استفاده‌شده» علامت بزن و موضوع بعدی را بردار."
)


# ⟨2026-11-18⟩ a page's long YouTube videos are not IG publications: their days carry `topic_fa`
# (set when the day is queued for YouTube), so «never the same topic twice» holds for them too
VIDEO_DONE_SQL = """SELECT run_meta -> 'flow' ->> 'topic_fa' AS t, max(created_at) AS at
    FROM work.work WHERE parent_id IS NULL AND run_meta -> 'flow' ->> 'account' = :a
      AND run_meta -> 'flow' ->> 'kind' = 'video' AND run_meta -> 'flow' ? 'topic_fa'
    GROUP BY 1 ORDER BY max(created_at) DESC LIMIT 300"""


async def published_topics(tx: Tx, flow: Flow) -> list[str]:
    """The page's topics already out or queued, of this flow's kind of output (newest first)."""
    kinds = DONE_KINDS["stories"] if flow.stories else DONE_KINDS.get(flow.kind, ("reel",))
    rows = await tx.all(DONE_SQL, a=flow.account, k=list(kinds))
    if flow.kind == "video" and not flow.stories:
        rows = sorted([*rows, *await tx.all(VIDEO_DONE_SQL, a=flow.account)],
                      key=lambda r: r["at"], reverse=True)  # fmt: skip
    out: list[str] = []
    size = 0
    for r in rows:
        t = " ".join(str(r["t"] or "").split())[:90]
        if not t or t in out:
            continue
        size += len(t) + 4
        if size > DONE_MAX_CHARS:
            break
        out.append(t)
    return out


def no_repeat(done: list[str] | None) -> str:
    if not done:
        return ""
    return "\n" + NO_REPEAT_FA.format(done="، ".join(f"«{t}»" for t in done))


def stories_brief(flow: Flow, day: date, used: list[str], done: list[str] | None = None) -> str:
    """⟨2026-11-15⟩ A stories flow's order: the day's pictures, their hours, the words taken."""
    n = len(flow.stories)
    hours = "، ".join(f"{i}) {hm}" for i, hm in enumerate(flow.stories, 1)).translate(FA_DIGITS)
    taken = "، ".join(f"«{w}»" for w in used) if used else "هنوز هیچ"
    word = (
        f"کلمه‌ی ریپلای این پیج ثابت است و هر روز همین است: «{flow.story_word}». همان را در "
        "comment.txt (keyword) و روی هر استوری بگذار؛ کلمه‌ی تازه نساز."
        if flow.story_word
        else f"کلمه‌هایی که پیش از این برای جواب استوری‌های این پیج گرفته شده و دیگر کار نمیکند: "
        f"{taken}. کلمه‌ی امروز باید تازه باشد."
    )
    return (
        f"{flow.title_fa}، {fa_day(day)}: {n} استوری عکس، هر کدام در ساعت خودش (تهران): {hours}.\n\n"
        "این فرمان را اتوماسیون روزانه (n8n) داده است، به دستور مدیر کل. کار خودکار است: از کسی "
        "چیزی نپرس، order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
        "قدم‌به‌قدم انجام بده؛ هیچ فایلی از کیت را عوض نکن.\n"
        f"تحویل: فقط این‌ها در out/: story_1.jpg تا story_{n}.jpg (۱۰۸۰×۱۹۲۰، به ترتیب ساعت‌ها)، "
        "comment.txt (کلمه‌ی امروز، جواب دایرکت و دکمه‌ها) و topic.txt. وقتی همه در out/ بود، ستاد "
        "هر استوری را برای ساعت خودش روی "
        f"@{flow.account} زمان‌بندی میکند، جواب دایرکت استوری را با کلمه‌ی امروز روشن میکند، به "
        "مدیر کل خبر میدهد و این جلسه را میبندد.\n" + word + no_repeat(done)
    )


# ⟨2026-11-18⟩ the owner's rule, in every video's brief (zaribsad's 11-18 reel went out with music
# only: the voice's quota was spent and the session read it as «signed out» and went on)
NEVER_SILENT_FA = (
    "قاعده‌ی مالک: ویدیو هرگز بی‌صدای گوینده ساخته، تحویل یا منتشر نمی‌شود. اگر speech.make صدا "
    "نداد (مثلاً «سهمیه تمام شده»)، هیچ ویدیویی در out/ نگذار: صبر کن و بعد از تازه شدن سهمیه "
    "(ساعت ۱۱:۳۰ تهران) دوباره بساز، حتی اگر ساعت انتشار بگذرد؛ دیر و با صدا، نه سر وقت و بی‌صدا. "
    "برای صدا از مالک «ورود» نخواه."
)


# ⟨2026-11-18⟩ a page's long video without a site (@behnamjalali.tech): YouTube only, 8-15 minutes
LONG_NO_SITE_FA = (
    "تحویل: فقط این‌ها در out/: video.mp4 (۱۹۲۰×۱۰۸۰، ۸ تا ۱۵ دقیقه)، thumbnail.jpg، meta.json، "
    "subtitles.fa.srt، chapters.txt، caption.txt (همان توضیحات یوتیوب) و topic.txt؛ video.mp4 آخر از همه. "
    "وقتی همه در out/ بود، ستاد ویدیو را در ساعتش روی کانال یوتیوب همین پیج منتشر میکند (اگر صدا از "
    "بررسی‌اش رد شود)، به مدیر کل خبر میدهد و این جلسه را میبندد.\n"
)


def video_brief(flow: Flow, day: date, at: datetime) -> str:
    """⟨2026-11-17⟩ A long-video day (DotCoin's YouTube): made over several workshop turns from the
    kit; the hub's host uploader (automations/sites/dotcoin/youtube_long.py --due) publishes it on
    YouTube at the hour, once, after its own checks, and puts the article on the site. ⟨2026-11-18⟩
    Another page's (no site): the video alone (LONG_NO_SITE_FA)."""
    if flow.account != "dotcoin.me":
        return (
            f"{flow.title_fa}، {fa_day(day)} (انتشار خودکار روی یوتیوب {at_fa(at)} به وقت تهران)\n\n"
            "این فرمان را اتوماسیون هاب داده است، به دستور مدیر کل. کار خودکار است: از کسی چیزی نپرس، "
            "order.ask نزن و منتظر تأیید نمان.\n"
            f"روند، قاعده‌ها و همه‌ی ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
            "قدم‌به‌قدم انجام بده؛ ساخت چند نوبت طول میکشد و NOTES.md در هر نوبت جای کار را نگه میدارد. "
            "هیچ فایلی از کیت را عوض نکن.\n"
            + LONG_NO_SITE_FA
            + NEVER_SILENT_FA
            + (f"\n\n{flow.note_fa}" if flow.note_fa else "")
        )
    return (
        f"{flow.title_fa}، {fa_day(day)} (انتشار خودکار روی یوتیوب {at_fa(at)} به وقت تهران)\n\n"
        "این فرمان را اتوماسیون هاب داده است، به دستور مدیر کل. کار خودکار است: از کسی چیزی نپرس، "
        "order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و همه‌ی ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
        "قدم‌به‌قدم انجام بده؛ ساخت چند نوبت طول میکشد و NOTES.md در هر نوبت جای کار را نگه میدارد. "
        "هیچ فایلی از کیت را عوض نکن.\n"
        "تحویل: فقط این‌ها در out/: video.mp4 (۱۹۲۰×۱۰۸۰، ۸ تا ۱۰ دقیقه)، thumbnail.jpg، meta.json، "
        "subtitles.fa.srt، chapters.txt، caption.txt (همان توضیحات یوتیوب)، article.md و topic.txt؛ "
        "video.mp4 آخر از همه. وقتی همه در out/ بود، ستاد ویدیو را در ساعتش روی یوتیوب دات‌کوین "
        "منتشر میکند (اگر صدا و مقاله از بررسی‌اش رد شوند)، مقاله را روی dotcoin.me میگذارد، به مدیر "
        "کل خبر میدهد و این جلسه را میبندد.\n"
        + NEVER_SILENT_FA
        + (f"\n\n{flow.note_fa}" if flow.note_fa else "")
    )


# ⟨2026-11-18⟩ what an SEO day's package is: the session's out/ (the runner sends .zip, .md and .txt)
ARTICLE_PACKAGE = "package.zip"
ARTICLE_SUMMARY = "summary.fa.txt"
ARTICLE_WEEK = "week.fa.txt"
SATURDAY = 5  # date.weekday(): the owner's week starts on Saturday (Tehran)


def article_brief(flow: Flow, day: date, at: datetime) -> str:
    """⟨2026-11-18⟩ A site's SEO day (dotcoin.me, the owner: «اتوماسیون سئو … فوق متخصص … هر روز بیشتر
    دیده شدن و به صفحه اول گوگل اومدن»): the day's data read by the hub before the turn, one new long
    page for a keyword cluster and the day's fixes to live pages, as ONE package; the hub's host
    publisher (automations/sites/dotcoin/seo.py --due) checks it, puts it on the site at the hour
    and asks Google (Search Console) and IndexNow to index what changed. White-hat only."""
    week = (
        f"امروز شنبه است: {ARTICLE_WEEK} را هم بنویس، ۳ تا ۵ خط کوتاه فارسی برای خلاصه‌ی هفتگی مدیر کل "
        "(دیده‌شدن هفته در گوگل با عدد، صفحه‌های تازه، بهترین حرکت جایگاه، کلیک‌های VIP اگر خوانده شد).\n"
        if day.weekday() == SATURDAY
        else ""
    )
    return (
        f"{flow.title_fa}، {fa_day(day)} (انتشار خودکار روی سایت {at_fa(at)} به وقت تهران)\n\n"
        "این فرمان را اتوماسیون هاب داده است، به دستور مدیر کل. کار خودکار است: از کسی چیزی نپرس، "
        "order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و همه‌ی ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
        "قدم‌به‌قدم انجام بده؛ کار چند نوبت طول میکشد و NOTES.md در هر نوبت جای کار را نگه میدارد. "
        "هیچ فایلی از کیت را عوض نکن.\n"
        f"روز این فرمان: {day.isoformat()}. داده‌ی امروز (Search Console، وضعیت ایندکس، نقشه‌ی سایت، "
        "کارنامه‌ی روزهای پیش) را ستاد پیش از این نوبت در پوشه‌ی ورودی همین روز گذاشته است (کیت جایش را میگوید).\n"
        "تحویل امروز: یک صفحه‌ی تازه‌ی بلند و پژوهش‌شده برای یک خوشه‌ی کلیدواژه، به‌علاوه‌ی بهینه‌سازی‌های "
        "امروز روی صفحه‌های موجود، همه در یک بسته. فقط این‌ها در out/: report.md، "
        f"{ARTICLE_SUMMARY} (یک خط فارسی: کار امروز)، topic.txt (خط اول عنوان صفحه‌ی تازه) و "
        f"{ARTICLE_PACKAGE} (ساخته‌ی ابزار pack کیت) آخر از همه.\n"
        + week
        + "وقتی بسته رسید، ستاد این جلسه را میبندد و در ساعتش، بعد از بررسی خودش (ساخت کامل سایت، قفل "
        "راست‌به‌چپ، سرریز در عرض موبایل)، آن را روی dotcoin.me منتشر میکند، نقشه‌ی سایت را تازه میکند و "
        "برای صفحه‌های تازه و تغییرکرده درخواست ایندکس میفرستد (Search Console و IndexNow).\n"
        "فقط سئوی سفید: بی صفحه‌ی کم‌مایه یا بازنویسی ماشینی، بی خرید و تبادل لینک، بی پنهان‌کاری؛ هر عدد "
        "و هر ادعا از منبع اصلی، و هیچ متن حقوقی یا سلب مسئولیت."
        + (f"\n\n{flow.note_fa}" if flow.note_fa else "")
    )


def brief_of(
    flow: Flow, day: date, at: datetime, used: list[str] | None = None,
    done: list[str] | None = None, ig: list[str] | None = None,
) -> str:  # fmt: skip
    """The order's text: what the day's session makes, from the kit, and when it goes out.
    `done`: the page's topics already out or queued (⟨2026-11-18⟩ never a second time); `ig`: a
    Telegram day's page's own recent reels (⟨2026-11-19⟩ never their copy)."""
    if flow.kind == "tg_post":
        from hq_api.domain import tg_posts as TG

        return TG.brief(flow, day, at, done, ig)
    if flow.stories:
        return stories_brief(flow, day, used or [], done)
    if flow.kind == "video":
        return video_brief(flow, day, at) + no_repeat(done)
    if flow.kind == "article":
        # (the site's own rules keep its pages unique: seo_pack refuses a live lesson's topic)
        return article_brief(flow, day, at)
    kind = kind_of(flow, day)
    return (
        f"{flow.title_fa}، {fa_day(day)} (انتشار خودکار {at_fa(at)} به وقت تهران)\n\n"
        + (f"نوع ریلز امروز: «{kind}» (کیت، بخش همین نوع).\n" if kind else "")
        + "این فرمان را اتوماسیون روزانه (n8n) داده است، به دستور مدیر کل. کار خودکار است: از کسی "
        f"چیزی نپرس، order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و همه‌ی ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
        f"قدم‌به‌قدم انجام بده؛ چیز دیگری از کیت را جز به نیاز نخوان و هیچ فایلی از کیت را عوض نکن.\n"
        + (
            f"تحویل: فقط این‌ها در out/: video.mp4 (ریلز)، story.mp4 (همان ویدیو، حداکثر ۵۹٫۸ ثانیه)، "
            f"cover.jpg، caption.txt، comment.txt و topic.txt. وقتی همه در out/ بود، ستاد خودش ریلز و "
            f"استوری را برای {at_fa(at)} روی @{flow.account} زمان‌بندی میکند، کامنت هوشمند و جواب "
            f"استوری را روشن میکند، به مدیر کل خبر میدهد و این جلسه را میبندد."
            if flow.story
            # ⟨2026-11-16⟩ a page whose stories are their own flow: the reel goes out alone
            else f"تحویل: فقط این‌ها در out/: video.mp4 (ریلز)، cover.jpg، caption.txt، comment.txt و "
            f"topic.txt (استوری نه). وقتی همه در out/ بود، ستاد خودش ریلز را برای {at_fa(at)} روی "
            f"@{flow.account} زمان‌بندی میکند، کامنت هوشمند را روشن میکند، به مدیر کل خبر میدهد و "
            f"این جلسه را میبندد."
        )
        + f"\n{NEVER_SILENT_FA}"
        + no_repeat(done)
        + (f"\n\n{flow.note_fa}" if flow.note_fa else "")
    )


# --------------------------------------------------------------------- start --
def n8n_key(key: str, day: date) -> UUID:
    """⟨1.39⟩ The `Idempotency-Key` n8n's flow-*.json sends for a day: sha256 of
    `flow:<key>:<day>` shaped as a version-5 UUID. The hub's clock sends the same one."""
    h = hashlib.sha256(f"flow:{key}:{day.isoformat()}".encode()).hexdigest()
    variant = format((int(h[16], 16) & 3) | 8, "x")
    return UUID(f"{h[:8]}-{h[8:12]}-5{h[13:16]}-{variant}{h[17:20]}-{h[20:32]}")


def clock_request(key: str, day: date, again: str = "") -> Request:
    """⟨1.39⟩ §61.2 the hub's clock places a day's order as n8n's own call does: the same path,
    body (`{"day":…}`) and key, so whichever of the two comes second answers the first one's order
    (the «one order a day» lock), and no HTTP request is needed. `again`: a day made before (the
    owner's run-now of a failed day) takes a key of its own."""
    from starlette.requests import Request

    body = json.dumps({"day": day.isoformat()}, separators=(",", ":")).encode()
    path = f"/internal/v1/flows/{key}/run"
    scope = {
        "type": "http", "method": "POST", "path": path, "raw_path": path.encode(),
        "root_path": "", "scheme": "http", "query_string": b"", "server": ("api", 8000),
        "client": ("127.0.0.1", 0), "http_version": "1.1",
        "headers": [(b"idempotency-key", str(n8n_key(key + again, day)).encode()),
                    (b"content-type", b"application/json")],
    }  # fmt: skip
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


async def start(
    ctx: Any, request: Any, background: Any, key: str, day: date | None, *, forced: bool = False
) -> dict[str, Any]:
    """The day's order (one per flow and day: the caller's `Idempotency-Key` makes a second call
    the first one's answer). Returns {order, work, publish_at, why_fa}. ⟨1.39⟩ The flow is its row
    (§61.1); a day it is off, paused, skipped or not one of its days makes nothing, unless `forced`
    (the owner's run-now)."""
    from hq_api.domain import dispatch as D
    from hq_api.errors import ApiError
    from hq_api.routes.orders import OrderIn, place_order

    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        flow = await flow_by_key(tx, key)
        if flow is None:
            raise ApiError(404, "not_found", f"no flow {key}")
        co = await tx.first("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
        if co is None:
            raise ApiError(409, "validation_failed", f"no company {flow.company}")
        if not forced and await is_off(tx, flow):
            # ⟨2026-11-14⟩ switched off on the board: n8n's call makes nothing
            return {"order": "", "work": None, "publish_at": "", "why_fa": OFF_WHY_FA}
        tomorrow = datetime.now(ZoneInfo(TEHRAN)).date() + timedelta(days=1)
        the_day = day or tomorrow
        if not forced and (held := held_why(flow, the_day)) is not None:
            return {"order": "", "work": None, "publish_at": "", "why_fa": held}
        # one order per flow and day, whatever calls again (a key expires in 24 hours); a day
        # whose work failed or was cancelled may be made again, unless its package went out
        # (⟨2026-11-14⟩ F-0022: the session closed as the reel was scheduled, and closing it
        # cancels a root still open: that day is made all the same)
        made = await tx.first(
            """SELECT ref, run_meta -> 'flow' AS flow FROM work.work
               WHERE run_meta -> 'flow' ->> 'key' = :k AND run_meta -> 'flow' ->> 'day' = :d
                 AND (status NOT IN ('failed', 'cancelled') OR run_meta -> 'flow' ? 'sent'
                      OR close_reason = :dup)
               ORDER BY created_at DESC LIMIT 1""",
            k=flow.key,
            d=the_day.isoformat(),
            dup=DUPLICATE_DAY,
        )
        if made is not None:
            m = OR._j(made["flow"]) or {}
            return {"order": str(m.get("order") or ""), "work": str(made["ref"]),
                    "publish_at": str(m.get("publish_at") or ""), "why_fa": "پیش از این ساخته شده"}  # fmt: skip
        at, why = await slot_of(tx, flow, the_day, co["id"])
        ig: list[str] = []
        if flow.kind == "tg_post":
            from hq_api.domain import tg_posts as TG

            # ⟨2026-11-19⟩ no Telegram day is made before its channel and its bot's token are set
            if not forced and (held := await TG.connected(tx, co["id"], flow.account)) is not None:
                return {"order": "", "work": None, "publish_at": "", "why_fa": held}
            ig = await TG.reel_topics(tx, flow.account)
        if not forced and flow.ref and await published_day(tx, flow, the_day, at):
            # ⟨2026-11-17⟩ its work wiped, its package scheduled: never a second one
            return {"order": "", "work": None, "publish_at": "", "why_fa": MADE_PUBLISHED_FA}
        used = await story_words(tx, flow.account) if flow.stories and not flow.story_word else []
        # (a site's SEO day keeps its pages unique by the site's own rules, not by the page's posts)
        done = await published_topics(tx, flow) if flow.account and flow.kind != "article" else []
    body = OrderIn(
        text=brief_of(flow, the_day, at, used, done, ig),
        company=flow.company,
        route=D.Route(
            companies=[flow.company],
            kind="work",
            # ⟨2026-11-18⟩ a row above the route's bound (AF-0015 at 30M) failed the clock every
            # minute from its first day: the estimate is clamped, never the day
            budget_tokens=max(10_000, min(flow.budget_tokens, D.ROUTE_TOKENS_MAX)),
            why_fa=f"اتوماسیون روزانه: {flow.title_fa}",
        ),
        pace="auto",
    )
    out = await place_order(ctx, request, background, body)
    # the first call's answer, or (the same key again) its stored replay
    got = out.model_dump() if hasattr(out, "model_dump") else json.loads(bytes(out.body))
    ref = str(got["ref"])
    work_ref = next((r.get("work_ref") for r in got.get("routes") or [] if r.get("work_ref")), None)
    model = model_on(flow, the_day)
    meta = {"key": flow.key, "day": the_day.isoformat(), "publish_at": at.isoformat(),
            "account": flow.account, "story": flow.story, "order": ref,
            **({"kind": flow.kind} if flow.kind in OFF_IG_KINDS else {}),
            **({"model": model} if model else {}),
            **({"effort": flow.effort} if flow.effort else {})}  # fmt: skip
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        if work_ref:
            await tx.exec(
                """UPDATE work.work SET run_meta = coalesce(run_meta, '{}'::jsonb)
                       || jsonb_build_object('flow', CAST(:m AS jsonb))
                   WHERE ref = :w AND NOT (coalesce(run_meta, '{}'::jsonb) ? 'flow')""",
                w=work_ref,
                m=_json(meta),
            )
        await audit.record(
            tx, FLOW, company_id=co["id"], action="flow.run", action_class="A2",
            target_kind="order", target_ref=ref,
            summary=f"{flow.key} for {the_day} (publish {at.isoformat()}, {why}); work {work_ref}",
        )  # fmt: skip
    return {"order": ref, "work": work_ref, "publish_at": at.isoformat(), "why_fa": why}


# ------------------------------------------------------- ⟨1.39⟩ the one clock --
CLOCK_WHO = Principal(kind="owner", code="owner", role="owner")  # (n8n's call is the owner's too)
DAY_SQL = """SELECT 1 FROM work.work WHERE parent_id IS NULL
    AND run_meta -> 'flow' ->> 'key' = :k AND run_meta -> 'flow' ->> 'day' = :d LIMIT 1"""
DUPLICATE_DAY = "duplicate_day"  # a work's close_reason: a second order of a day, never made again
# ⟨2026-11-26⟩ a reel's Trial Reel copy (trial_reels.py, `source.trial_of`) is never a flow's day
PUBLISHED_SQL = """SELECT ref FROM media.publications
    WHERE state NOT IN ('failed', 'cancelled') AND NOT source ? 'trial_of' AND (
        (source ->> 'flow_key' = :k AND source ->> 'day' = :d)
        OR (account = :a AND kind = :kind AND at >= :lo AND at < :hi
            AND coalesce(source ->> 'flow_key', '') IN ('', :k)))
    ORDER BY at LIMIT 1"""
OWN_PUBLISHED_SQL = """SELECT ref FROM media.publications
    WHERE state NOT IN ('failed', 'cancelled') AND source ->> 'flow_key' = :k AND source ->> 'day' = :d
    ORDER BY at LIMIT 1"""
PUBLISHED_BEFORE, PUBLISHED_AFTER = timedelta(hours=1), timedelta(hours=3)
MADE_PUBLISHED_FA = "بسته‌ی این روز پیش از این زمان‌بندی یا منتشر شده است"


async def published_day(tx: Tx, flow: Flow, day: date, at: datetime | None = None) -> str | None:
    """⟨2026-11-17⟩ the day's package is out (or scheduled), read from what was published (§60.1),
    not only from its work: the owner's wipe of 07:24Z took that morning's works, and a day made
    before §60 has no flow on its rows (live: 7 false `late` alerts and 2 duplicate days). Its
    publication row (this flow and day), or a post of the flow's page and kind, scheduled or
    published, from an hour before its hour to three hours after its last one, that no other flow
    claims. The publication's ref, or None. ONE rule for the clock, n8n's call and the alerts."""
    if not flow.account:
        return None
    if flow.kind in OFF_IG_KINDS:
        # ⟨2026-11-18⟩ a long video or a site's day is never a post of the page: only its own row
        got = await tx.scalar(OWN_PUBLISHED_SQL, k=flow.key, d=day.isoformat())
        return str(got) if got else None
    if at is None:
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
        at, _ = await slot_of(tx, flow, day, co)
    last = story_times(flow, day)[-1] if flow.stories else at
    got = await tx.scalar(
        PUBLISHED_SQL, k=flow.key, d=day.isoformat(), a=flow.account,
        kind="story" if flow.stories else "reel", lo=at - PUBLISHED_BEFORE,
        hi=last + PUBLISHED_AFTER,
    )  # fmt: skip
    return str(got) if got else None


async def day_made(tx: Tx, flow: Flow, day: date, at: datetime | None = None) -> bool:
    """The day is made: any work of it (failed, cancelled or a duplicate: the clock never makes a
    day twice), or its package already scheduled or out (published_day)."""
    if await tx.scalar(DAY_SQL, k=flow.key, d=day.isoformat()):
        return True
    return await published_day(tx, flow, day, at) is not None


N8N_GRACE = timedelta(minutes=2)


async def n8n_guard(tx: Tx, key: str, day: date | None, now: datetime | None = None) -> str | None:
    """⟨1.39⟩ §61.2 why n8n's per-flow call (flow-*.json, its own old hour) makes nothing for a
    flow with a row: the row's build hour for that day has not come (two minutes' grace), it is
    off, paused, or the day is skipped or not one of its days. None: the call goes on (start()'s
    «one order a day» answers a day already made)."""
    flow = await flow_by_key(tx, key)
    if flow is None or not flow.ref:
        return None
    if flow.state == "off":
        return "off"
    the_day = day or datetime.now(ZoneInfo(TEHRAN)).date() + timedelta(days=1)
    held = held_why(flow, the_day)
    if held is not None:
        if held.startswith(NOT_STARTED_FA.split("{", 1)[0]):
            return "not_started"
        return {SKIPPED_WHY_FA: "skipped", NOT_ITS_DAY_FA: "not_its_day"}.get(held, "paused")
    if (now or datetime.now(UTC)) < trigger_of(flow, the_day) - N8N_GRACE:
        return "before_trigger"
    return None


def trigger_of(flow: Flow, day: date) -> datetime:
    """When the order of the day `day` (the day it goes out) is placed (UTC): its `trigger_at`
    (Tehran) that day when `same_day`, else the day before."""
    tz = ZoneInfo(TEHRAN)
    hh, mm = (int(x) for x in flow.trigger_at.split(":"))
    on = day if flow.same_day else day - timedelta(days=1)
    return datetime.combine(on, time(hh, mm), tz).astimezone(UTC)


async def due_days(tx: Tx, now: datetime) -> list[tuple[Flow, date]]:
    """§61.2 every row `on` whose order time has come for a day not yet past its publish time,
    that is one of its days and has no run yet (any run: a failed day is never re-made by the
    clock). A pause whose `paused_until` has come ends here."""
    today = now.astimezone(ZoneInfo(TEHRAN)).date()
    ended = await tx.all(
        """UPDATE automations.flows f SET state = 'on', paused_until = NULL, updated_at = now()
           FROM core.companies c WHERE c.id = f.company_id AND f.state = 'paused'
             AND f.paused_until <= :t RETURNING f.ref, c.code AS company""",
        t=today,
    )
    from hq_api import events

    for r in ended:
        await events.emit(
            tx, r["company"], "automation.changed", r["ref"], {"ref": r["ref"], "state": "on"}
        )
    out = []
    for flow in (await active_flows(tx)).values():
        if not flow.ref or flow.state == "off":
            continue
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
        first = today + timedelta(days=0 if flow.same_day else 1)
        for day in (first - timedelta(days=1), first):
            if trigger_of(flow, day) > now or held_why(flow, day) is not None:
                continue
            if await tx.scalar(DAY_SQL, k=flow.key, d=day.isoformat()):
                continue
            at, _ = await slot_of(tx, flow, day, co)
            if now >= at:  # (its hour has gone: the day is left, as n8n would have left it)
                continue
            if await day_made(tx, flow, day, at):
                continue
            out.append((flow, day))
    return out


async def clock(
    hub: Any, now: datetime | None = None, *, quiet_since: datetime | None = None
) -> list[str]:
    """⟨1.39⟩ §61.2 the hub's own clock, run by n8n's minute tick (`hq-flows`) and by its own
    backup when n8n is silent (flow_auto.due): every day due starts as n8n's per-flow call would
    (clock_request), so a second call of the same day is that day's answer. The orders made."""
    from fastapi import BackgroundTasks

    from hq_api.context import Ctx
    from hq_api.errors import ApiError

    now = now or datetime.now(UTC)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        days = await due_days(tx, now)
    made = []
    for flow, day in days:
        request = clock_request(flow.key, day)
        later = BackgroundTasks()
        try:
            got = await start(Ctx(hub=hub, who=CLOCK_WHO, request=request), request, later,
                              flow.key, day)  # fmt: skip
        except ApiError as exc:  # (n8n's own call of the same day is being placed right now)
            log.warning("the clock left a day", extra={"flow": flow.key, "code": exc.code})
            continue
        except Exception:  # (one flow's day never stops the others)
            log.exception("the clock could not start a day", extra={"flow": flow.key})
            continue
        await later()
        if got.get("order"):
            made.append(str(got["order"]))
    # ⟨2026-11-24⟩ the keeper, with the same clock (never stops it)
    try:
        await keep(hub, now)
    except Exception:  # (the clock goes on)
        log.exception("the automations' keeper did not run")
    # ⟨1.39⟩ §61.6 the alerts, with the same clock (never stops it)
    from hq_api.domain import flow_alerts as AL
    from hq_api.domain import notify

    try:
        push = await AL.sweep(hub, now, quiet_since=quiet_since)
        if push:
            await notify.deliver_pending(hub, push)
    except Exception:  # (the clock goes on)
        log.exception("the automations' alerts were not swept")
    return made


# ⟨2026-11-24⟩ THE KEEPER. The owner: «نباید سیستم قطع باشد و هیچ کاری نکند بجز مواقعی که حساب
# مسدود یا لیمیت خورده باشد». 11-22..24 every day's session failed its turns (the Claude account was
# disabled), spent its FLOW_CONTINUE_MAX continues in a minute and then sat open with nothing queued:
# nothing ever woke it again, and no automation made anything for three days. Every KEEP_EVERY_MIN
# minutes the clock wakes the open sessions of today's (and tomorrow's) flow days that have nothing
# queued or running and were quiet for KEEP_IDLE, while a Claude account has room (all of them
# disabled or full: nothing to do, the only wait the owner accepts); at most KEEP_MAX wakes a session
# in 24 hours and KEEP_BATCH a pass (the workshop takes two turns at a time).
KEEP_EVERY_MIN = 10
KEEP_IDLE = timedelta(minutes=20)
KEEP_MAX = 24
KEEP_BATCH = 8
KEPT = "flow_kept"
KEEP_SQL = """SELECT w.id, w.ref, w.company_id, w.run_meta -> 'flow' ->> 'order' AS "order"
  FROM work.work w
 WHERE w.parent_id IS NULL AND w.run_meta ? 'flow' AND w.status = ANY(:open)
   AND w.assignee_id IS NOT NULL
   AND w.run_meta -> 'flow' ->> 'day' >= :today
   AND coalesce(w.run_meta -> 'flow' ->> 'order', '') <> ''
   AND EXISTS (SELECT 1 FROM owner.order_reports r
                WHERE r.ref = w.run_meta -> 'flow' ->> 'order' AND r.closed_at IS NULL)
   AND NOT EXISTS (SELECT 1 FROM infra.server_jobs j WHERE j.kind = 'claude' AND j.work_ref = w.ref
                     AND j.state IN ('queued', 'dispatched', 'running'))
   AND NOT EXISTS (SELECT 1 FROM agents.runs r WHERE r.work_id = w.id
                     AND r.state IN ('queued', 'claimed', 'running'))
   AND coalesce((SELECT max(e.at) FROM work.work_events e WHERE e.work_id = w.id), w.created_at)
       < :quiet_before
   AND (SELECT count(*) FROM work.work_events e WHERE e.work_id = w.id AND e.kind = :kept
          AND e.at > :since) < :keep_max
 ORDER BY w.run_meta -> 'flow' ->> 'day', w.created_at
 LIMIT :batch"""


UNSENT_BATCH = 20
UNSENT_SQL = """SELECT w.id, w.ref FROM work.work w
 WHERE w.parent_id IS NULL AND w.run_meta ? 'flow' AND w.status = 'delivered'
   AND NOT (w.run_meta -> 'flow' ? 'sent')
   AND w.run_meta -> 'flow' ->> 'day' >= :since
   AND w.run_meta -> 'flow' ->> 'day' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
 ORDER BY w.run_meta -> 'flow' ->> 'publish_at' NULLS LAST, w.created_at
 LIMIT :batch"""


def _day_before(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


async def claude_room(tx: Tx) -> bool:
    """A Claude account the workshop may use has room now (switched on, not full)."""
    from hq_api.domain import servers as SV

    keys = [k for k, _ in SV.RUNNER_ACCOUNTS]
    on = await tx.scalar(
        "SELECT count(*) FROM llm.connections WHERE key = ANY(:k) AND status IN ('enabled', 'ready')",
        k=keys,
    )
    return bool(on) and await SV.accounts_room_at(tx) is None


async def keep(hub: Any, now: datetime, *, force: bool = False) -> list[str]:
    """The keeper's pass (see KEEP_EVERY_MIN): the sessions it woke."""
    from hq_api.domain import direct as DR
    from hq_api.domain import servers as SV
    from hq_api.domain import work as W

    if not force and now.minute % KEEP_EVERY_MIN:
        return []
    today = now.astimezone(ZoneInfo(TEHRAN)).date().isoformat()
    woke: list[str] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(
            KEEP_SQL, open=list(W.OPEN), today=today, quiet_before=now - KEEP_IDLE,
            kept=KEPT, since=now - timedelta(hours=24), keep_max=KEEP_MAX, batch=KEEP_BATCH,
        )  # fmt: skip
        # ⟨2026-11-26⟩ the owner: «هیچ ریلزی هیچ اتوماسیونی جا بمونه، هیچ وقت قابل بخشش نیست».
        # bjtech_reels_2 of 11-25 (W-001216) was delivered but never sent (a wipe took its first
        # turn's texts), and a delivered day is not open, so the pass above never saw it: every
        # delivered day of today and yesterday that is not sent goes through the publish path again
        unsent = await tx.all(UNSENT_SQL, since=_day_before(today), batch=UNSENT_BATCH)
    for u in unsent:
        got = await after_delivered(hub, u["id"])
        if got != "sent":
            log.warning("the keeper ran a delivered day that was never sent",
                        extra={"work": str(u["ref"]), "got": got})  # fmt: skip
    # ⟨2026-11-24⟩ a day whose whole package is in but was never sent (its last turn broke after
    # it wrote out/, so no deliver came): sent now, not woken (no account needed for that)
    left = []
    for r in rows:
        if await after_delivered(hub, r["id"]) in (None, "open"):
            left.append(r)
    if not left:
        return []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        # ⟨2026-11-27⟩ no Claude room but the Hydrogen fallback can take the turns: woken too
        if not await claude_room(tx) and not await SV.hydrogen_ready(tx):
            return []
        for r in left:
            if await over_cap(tx, r["id"]):
                continue
            run = await tx.scalar(
                "SELECT work.wake_assignee(:w, :r)",
                w=r["id"],
                r=f"{DR.CONTINUE_REASON}{r['order']}",
            )
            if run is None:
                continue
            await W.event(
                tx, dict(r), KEPT, FLOW, {"run": str(run), "why": "idle, an account has room"}
            )
            woke.append(str(r["ref"]))
    if woke:
        log.info("the keeper woke idle flow sessions", extra={"works": woke})
    return woke


STORY_WORDS_SQL = """SELECT DISTINCT kw FROM infra.server_jobs j,
        jsonb_array_elements_text(j.args -> 'meta' -> 'rule' -> 'keywords') AS kw
    WHERE j.kind = 'publish' AND j.args ->> 'account' = :a
      AND j.args -> 'rule_for' ->> 'trigger' = 'story_reply' AND j.state IN ('queued', 'running', 'done')"""


async def story_words(tx: Tx, account: str) -> list[str]:
    """⟨2026-11-15⟩ The words the account's story replies are already answered on. IG-Hub answers
    a story reply with the OLDEST rule that has its word: a taken word never reaches a new rule."""
    rows = await tx.all(STORY_WORDS_SQL, a=account)
    words = sorted({str(r["kw"]).replace("\u200c", "").replace(" ", "") for r in rows})
    return [w for w in words if w][:500]


def _json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


# ------------------------------------------------------------ the day's cap --
# ⟨2026-11-13⟩ the F-0018 usage audit (P4): a day aims at about $6 (the turns' own cost, as the hub
# books it since the audit: llm.calls.equiv_cost_usd). ⟨1.39⟩ the owner, 2026-11-17: «ریلزو که
# نمیتونم پاکت بدم اومدیم به محدودیت خورد یعنی نمیخواد ریلز رو بسازه؟ حتما باید بسازه»: cost
# never holds a flow. A day past its cap goes on to the end (only the workshop turn's own time
# bounds it); the flow's page shows a `cap_reached` alert, and nobody is notified.
FLOW_USD_CAP = Decimal("10")


async def spent_usd(tx: Tx, work_ref: str) -> Decimal:
    got = await tx.scalar(
        "SELECT COALESCE(SUM(equiv_cost_usd), 0) FROM llm.calls WHERE work_ref = :w", w=work_ref
    )
    return Decimal(str(got or 0))


async def over_cap(tx: Tx, work_id: UUID) -> bool:
    """A flow's day past its cap: marked once (`capped`, audit `flow.capped`) with a `cap_reached`
    alert on its row (§61.6, no notification). Never holds anything: always False."""
    w = await flow_of_work(tx, work_id)
    if w is None:
        return False
    usd = await spent_usd(tx, str(w["ref"]))
    meta = w["flow"]
    flow = await flow_by_key(tx, str(meta.get("key")))
    cap = flow.usd_cap if flow else FLOW_USD_CAP
    if usd < cap or meta.get("capped"):
        return False
    meta["capped"] = f"{usd:.2f}"
    await tx.exec(
        "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))"
        " WHERE id = :w",
        w=w["id"],
        m=_json(meta),
    )
    if flow is not None and flow.ref:
        from hq_api.domain import flow_alerts as AL

        await AL.open_alert(
            tx, flow, "cap_reached",
            AL.CAP_REACHED_FA.format(usd=f"{usd:.2f}".translate(FA_DIGITS),
                                     cap=f"{cap:.0f}".translate(FA_DIGITS)),
            day=date.fromisoformat(str(meta["day"])) if meta.get("day") else None,
        )  # fmt: skip
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.capped", action_class="A1",
        target_kind="work", target_ref=str(w["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: ${usd:.2f} >= ${cap} (goes on: no hold)",
    )  # fmt: skip
    return False


# ------------------------------------------------------------ the package --
READY_TITLE_FA = "{title} آماده شد"
# (a notification keeps Persian only: no handle, no link; the session has them)
READY_BODY_FA = (
    "برای {at} به وقت تهران زمان‌بندی شد؛ استوری، کامنت هوشمند و جواب استوری خودکار است. "
    "موضوع: {topic}"
)
OUT_TITLE_FA = "{title} منتشر شد"
OUT_BODY_FA = (
    "کامنت هوشمند روشن است؛ استوری هم منتشر میشود و جواب استوری خودکار است. نشانی در جلسه است."
)
FAILED_TITLE_FA = "{title}: انتشار انجام نشد"


async def flow_of_work(tx: Tx, work_id: UUID) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT w.id, w.ref, w.company_id, w.status, w.run_meta -> 'flow' AS flow, c.code AS company
           FROM work.work w JOIN core.companies c ON c.id = w.company_id WHERE w.id = :w""",
        w=work_id,
    )
    if row is None or not row["flow"]:
        return None
    return {**dict(row), "flow": OR._j(row["flow"]) or {}}


async def package(tx: Tx, w: dict[str, Any], *, need_cover: bool = True) -> dict[str, Any] | None:
    """The day's package from every finished output of its work, the newest file of each name (a
    session delivers it over several turns: F-0020 sent the cover and the texts first, the video and
    the story in a later turn). None until a video and `caption.txt` are both there. `d`: the output
    of the video (the publication's own); the texts are read from their own outputs."""
    rows = await tx.all(
        SPB.OUTPUT_SQL + " WHERE d.work_id = :w AND d.company_id = :co"
        " ORDER BY d.created_at DESC LIMIT 30",
        w=w["id"],
        co=w["company_id"],
    )
    newest: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    finished_later = False
    for r in rows:
        d = dict(r)
        # an unfinished turn's files count once a later turn of the session finished (⟨2026-11-14⟩
        # F-0023: the first turn wrote the cover and the texts, then stopped; the second sent only
        # the videos, as the texts had not changed); never on their own
        if (OR._j(d.get("produced_with")) or {}).get("unfinished"):
            if not finished_later:
                continue
        else:
            finished_later = True
        for f in await SPB._files(tx, d):
            newest.setdefault(str(f["name"] or "").strip().lower(), (dict(f), d))
    flow = await flow_by_key(tx, str((w.get("flow") or {}).get("key") or ""))
    if (w.get("flow") or {}).get("kind") == "tg_post" or (
        flow is not None and flow.kind == "tg_post"
    ):
        return _telegram_package(newest)
    if flow is not None and flow.stories:
        return _stories_package(flow, newest)
    if (w.get("flow") or {}).get("kind") == "article" or (
        flow is not None and flow.kind == "article"
    ):
        return _article_package(newest)
    files = [f for f, _ in newest.values()]
    reel, story = _split(files)
    caption = next((newest[n] for n in SPB.CAPTION_NAMES if n in newest), None)
    if (
        reel is None
        and caption is not None
        and (
            (flow is not None and flow.kind == "video")
            or (w.get("flow") or {}).get("kind") == "video"
        )
        and await _video_left_in_out(tx, caption[1], str(w.get("ref") or ""))
    ):
        # ⟨2026-11-18⟩ W-000636: a 10-minute 1080p60 video (710 MB) is over the hub's file limit, so
        # the runner leaves it in out/ (files_skipped); the host uploader reads out/ itself
        topic = newest.get("topic.txt")
        return {"d": caption[1], "reel": None, "story": None, "cover": None,
                "caption_d": caption[1], "comment_d": None, "topic_d": topic[1] if topic else None}  # fmt: skip
    if reel is None or caption is None:
        return None
    covers = [f for f, _ in newest.values()
              if str(f["mime"]).startswith("image/") and str(f["name"] or "").lower().startswith("cover")]  # fmt: skip
    if not covers and need_cover and (flow is None or flow.kind == "reel"):
        # ⟨2026-11-19⟩ DotCoin's P-000122 went out with a video frame: its session never made
        # cover.jpg, and a reel was published without one. A reel's day waits for its cover
        # (_publish wakes the session once to make it).
        return None
    comment = next((newest[n] for n in SPB.COMMENT_NAMES if n in newest), None)
    topic = newest.get("topic.txt")
    owner_of = {id(f): d for f, d in newest.values()}
    return {
        "d": owner_of[id(reel)],
        "reel": reel,
        "story": story,
        "cover": covers[0] if covers else None,
        "caption_d": caption[1],
        "comment_d": comment[1] if comment else None,
        "topic_d": topic[1] if topic else None,
    }


COVER_MISSING_FA = (
    "ریلز و کپشن رسید ولی out/cover.jpg نیست. هیچ ریلزی بی کاور منتشر نمیشود (دستور مالک): "
    "کاور را دقیقاً در خانواده‌ی کاورهای همین پیج بساز (کیت، بخش کاور)، در out/ بگذار و تحویل بده."
)


async def _ask_for_cover(tx: Tx, w: dict[str, Any]) -> bool:
    """A reel day whose video and caption are in but not its cover: the session is woken once to
    make it (`cover_asked` on the run). True when it was woken now."""
    meta = w.get("flow") or {}
    if meta.get("cover_asked") or meta.get("kind") in OFF_IG_KINDS:
        return False
    pkg = await package(tx, w, need_cover=False)
    if pkg is None or pkg.get("cover") is not None or pkg.get("reel") is None:
        return False
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow,cover_asked}',
               to_jsonb(CAST(:t AS text))) WHERE id = :w""",
        t=datetime.now(UTC).isoformat(),
        w=w["id"],
    )
    order = str(meta.get("order") or "")
    rep = await OR.ensure(tx, order) if order else None
    if rep is not None:  # (always a step: a turn already queued reads it in its brief)
        await OR._append_steps(tx, rep["id"], [OR._step("سامانه", COVER_MISSING_FA)])
    await tx.scalar(
        "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"cover_missing:{order or w['ref']}"
    )
    return True


# ⟨2026-11-24⟩ THE LAST GATE. The owner: «از تکراری بودن ریلز های پروچارت جلوگیری بشه». @theprochart
# said «۴۴ الگو، دو خانواده» twice on 11-24 (its two flows, each with its own empty ledger) and
# «میله‌ای OHLC» on 11-21 and 11-22. The topic ledger now spans the page (topics.scope_of_work);
# this is the gate behind it: a reel whose topic (topic.txt, its first line) the page already has
# out or set, by any flow or day, is not sent. Its session is woken to make the day again on a new
# topic, REPEAT_WAKES times at most; past that the day waits (a step on its report says why).
REPEAT_WAKES = 2
REPEAT_SCAN = 500
REPEAT_SQL = """SELECT topic_fa, coalesce(published_at, scheduled_at, created_at) AS at,
       coalesce(source ->> 'work', '') AS work
  FROM media.publications
 WHERE account = :a AND kind = 'reel' AND state NOT IN ('cancelled', 'failed')
   AND coalesce(topic_fa, '') <> '' AND coalesce(source ->> 'work', '') <> :w
   AND NOT source ? 'trial_of'
 ORDER BY created_at DESC LIMIT :n"""
TOPIC_REPEAT_FA = (
    "موضوع این ریلز («{topic}») پیش از این در همین پیج رفته است ({at}). تکرار ممنوع است (دستور "
    "مالک): منتشر نشد. یک موضوع تازه بردار (ثبت موضوع) و ریلز، کپشن، کاور و فایل موضوعِ تازه را "
    "دوباره بساز و تحویل بده."
)
TOPIC_REPEAT_HELD_FA = (
    "موضوع این ریلز («{topic}») باز هم تکراری بود؛ این روز منتشر نمیشود تا موضوع تازه برسد."
)
_TOPIC_CHARS = str.maketrans(
    {"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "‌": " "}
    | {c: str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
    | {c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
)


def topic_key(text: str) -> str:
    """A topic as compared: Arabic letters and Persian/Arabic digits as Persian/ASCII, no
    half-space, punctuation, diacritics or case."""
    t = str(text or "").translate(_TOPIC_CHARS).casefold()
    return "".join(ch for ch in t if ch.isalnum())


async def repeat_of(tx: Tx, account: str, topic: str, work_ref: str) -> dict[str, Any] | None:
    """The page's reel (another work's, out or set) on the same topic, if any."""
    key = topic_key(topic)
    if not key:
        return None
    rows = await tx.all(REPEAT_SQL, a=account, w=work_ref, n=REPEAT_SCAN)
    return next((dict(r) for r in rows if topic_key(r["topic_fa"]) == key), None)


async def _hold_repeat(
    tx: Tx, w: dict[str, Any], meta: dict[str, Any], topic: str, seen: dict[str, Any]
) -> str:
    """A reel day on a topic its page already has: not sent; its session woken to make it again
    on a new topic (REPEAT_WAKES times at most)."""
    asked = int(meta.get("repeats") or 0)
    meta["repeats"] = asked + 1
    meta["repeat_of"] = str(seen.get("work") or "")
    await tx.exec(
        "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))"
        " WHERE id = :w",
        w=w["id"],
        m=_json(meta),
    )
    order = str(meta.get("order") or "")
    at = seen.get("at")
    said = (
        TOPIC_REPEAT_FA.format(topic=topic[:120], at=at_fa(at) if at else "—")
        if asked < REPEAT_WAKES
        else TOPIC_REPEAT_HELD_FA.format(topic=topic[:120])
    )
    rep = await OR.ensure(tx, order) if order else None
    if rep is not None:
        await OR._append_steps(tx, rep["id"], [OR._step("سامانه", said)])
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.topic_repeat", action_class="A1",
        target_kind="work", target_ref=str(w["ref"]),
        summary=f"{meta.get('account')}: «{topic[:120]}» again (first {seen.get('work')})",
    )  # fmt: skip
    if asked < REPEAT_WAKES:
        await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"topic_repeat:{order or w['ref']}"
        )
    log.warning(
        "flow reel topic repeated: not sent",
        extra={"work": str(w["ref"]), "account": meta.get("account"), "of": seen.get("work")},
    )
    return "repeat"


# ⟨2026-11-27⟩ THE ART GATE. The owner, after DotCoin's stories went out with a set the session drew itself
# (F-0246: ChatGPT failed, Gemini was signed out, its own HTML drew the figures in a system font): «همیشه اگر
# خطا داد ساخته نشه، خطا برطرف بشه بعد ساخته بشه، هیچ اشتباهی پیش نیاد». A stories flow whose pictures are
# ChatGPT's art is not sent unless this work's ChatGPT calls really drew them (done image calls of the
# work, at least one picture a story): a substitute set is held, its session woken to ask ChatGPT again,
# ART_WAKES times at most; past that the day waits on its report (the cause is fixed first, then it goes).
ART_FROM: dict[str, str] = {"dotcoin_stories": "gpt"}
ART_WAKES = 6
ART_SQL = """SELECT coalesce(sum(greatest(coalesce(c.images, 1), 1)), 0)
  FROM substitutes.creatives cr JOIN substitutes.calls c ON c.id = cr.call_id
 WHERE cr.work_id = :w AND cr.player = :p AND c.state = 'done' AND cr.kind = 'image'"""
ART_MISSING_FA = (
    "این روز منتشر نشد: تصویرهای استوری باید کارِ {player} باشد، ولی فراخوانی موفقِ {player} برای "
    "این کار فقط {got} تصویر داده (لازم: {need}). دستور مالک: «اگر خطا داد ساخته نشه، خطا برطرف بشه بعد "
    "ساخته بشه» — هیچ مجموعه‌ی جایگزین یا ساخت خودمان منتشر نمیشود. دوباره از {player} بخواه (کیت، "
    "قدم ۴)؛ اگر باز خطا داد، خطا را دقیق در گزارش بگو و منتظر رفعش بمان. دیر رفتن اشکالی ندارد."
)
ART_HELD_FA = (
    "این روز هنوز منتشر نشده: تصویرهای {player} نرسیده‌اند ({got} از {need}). تا خطای مسیر {player} "
    "برطرف نشود، چیزی ساخته و منتشر نمیشود."
)


async def _art_missing(tx: Tx, w: dict[str, Any], meta: dict[str, Any], need: int) -> str | None:
    """None = the stories' art really came from their player; else the day is held ("art")."""
    player = ART_FROM.get(str(meta.get("key") or ""))
    if not player:
        return None
    got = int(await tx.scalar(ART_SQL, w=w["id"], p=player) or 0)
    if got >= need:
        return None
    asked = int(meta.get("art_wakes") or 0)
    meta["art_wakes"] = asked + 1
    await tx.exec(
        "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))"
        " WHERE id = :w",
        w=w["id"],
        m=_json(meta),
    )
    name = {"gpt": "ChatGPT", "gemini": "Gemini"}.get(player, player)
    said = (ART_MISSING_FA if asked < ART_WAKES else ART_HELD_FA).format(
        player=name, got=got, need=need
    )
    order = str(meta.get("order") or "")
    rep = await OR.ensure(tx, order) if order else None
    if rep is not None:
        await OR._append_steps(tx, rep["id"], [OR._step("سامانه", said)])
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.art_missing", action_class="A1",
        target_kind="work", target_ref=str(w["ref"]),
        summary=f"{meta.get('account')}: {got} of {need} pictures from {name}: not sent",
    )  # fmt: skip
    if asked < ART_WAKES:
        await tx.scalar(
            "SELECT work.wake_assignee(:w, :r)", w=w["id"], r=f"art_missing:{order or w['ref']}"
        )
    log.warning(
        "flow stories without their art: not sent",
        extra={"work": str(w["ref"]), "account": meta.get("account"), "got": got, "need": need},
    )
    return "art"


VIDEO_LEFT_SQL = """SELECT 1 FROM infra.server_jobs j,
        jsonb_array_elements(coalesce(j.result -> 'files_skipped', '[]'::jsonb)) s
    WHERE j.state = 'done' AND s ->> 'name' = 'video.mp4'
      AND (j.id = CAST(:j AS uuid) OR (:ref <> '' AND j.kind = 'claude' AND j.args ->> 'workspace' = :ref))
    LIMIT 1"""
NO_JOB = "00000000-0000-0000-0000-000000000000"


async def _video_left_in_out(tx: Tx, d: dict[str, Any], ref: str = "") -> bool:
    """Whether the turn that delivered this output finished with its `video.mp4` left in out/ (over
    the file limit): a long video's package is complete without the video among the outputs.
    ⟨2026-11-21⟩ W-000752: the caption came a turn before the video (00:33Z, the video 00:45Z), so
    any finished turn of the same work (`ref`) that left `video.mp4` counts too."""
    job = (OR._j(d.get("produced_with")) or {}).get("job")
    try:
        jid = str(UUID(str(job)))
    except ValueError:  # (none, or not a job's id: not such a turn)
        jid = ""
    if not jid and not ref:
        return False
    return bool(await tx.scalar(VIDEO_LEFT_SQL, j=jid or NO_JOB, ref=ref))


PICTURE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def _stories_package(
    flow: Flow, newest: dict[str, tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, Any] | None:
    """⟨2026-11-15⟩ A stories flow's day: `story_1` … `story_N` (pictures) and `comment.txt`, each
    with the output it came in. None until every one is there."""
    pics = []
    for i in range(1, len(flow.stories) + 1):
        got = next(
            (newest[f"story_{i}{e}"] for e in PICTURE_EXT if f"story_{i}{e}" in newest), None
        )
        if got is None or not str(got[0]["mime"]).startswith("image/"):
            return None
        pics.append(got)
    comment = next((newest[n] for n in SPB.COMMENT_NAMES if n in newest), None)
    if comment is None:
        return None
    topic = newest.get("topic.txt")
    return {
        "d": pics[0][1],
        "stories": pics,
        "comment_d": comment[1],
        "topic_d": topic[1] if topic else None,
    }


def _telegram_package(
    newest: dict[str, tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any] | None:
    """⟨2026-11-19⟩ A Telegram day: `telegram.txt` (its JSON, written last; or telegram.json) and every
    file of the session by its name (tg_posts.check finds each one it names). None until it is in."""
    from hq_api.domain import tg_posts as TG

    man = next((newest[n] for n in TG.TG_FILES if n in newest), None)
    if man is None:
        return None
    return {"d": man[1], "manifest": man[0], "files": {n: f for n, (f, _) in newest.items()}}


def _article_package(
    newest: dict[str, tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any] | None:
    """⟨2026-11-18⟩ A site's SEO day: `package.zip` (the changed files and their manifest, made by
    the kit's pack tool) and `summary.fa.txt`, each with the output it came in; `week.fa.txt` and
    `topic.txt` when there. None until both are in (the zip is written last)."""
    pkg = newest.get(ARTICLE_PACKAGE)
    summary = newest.get(ARTICLE_SUMMARY)
    if pkg is None or summary is None or str(pkg[0]["mime"]) != "application/zip":
        return None
    week, topic = newest.get(ARTICLE_WEEK), newest.get("topic.txt")
    return {
        "d": pkg[1],
        "zip": pkg[0],
        "summary_d": summary[1],
        "week_d": week[1] if week else None,
        "topic_d": topic[1] if topic else None,
    }


def _split(files: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The reel (a video not named story…) and its story cut (story…), else the reel itself."""
    videos = [f for f in files if str(f["mime"]).startswith("video/")]
    story = next((f for f in videos if str(f["name"] or "").lower().startswith("story")), None)
    reel = next((f for f in videos if f is not story), None)
    return reel, story or reel


async def after_delivered(hub: Any, work_id: UUID) -> str | None:
    """A direct turn of a flow's order left files: when they are the whole package, the reel and
    the story are scheduled for the flow's hour, the owner is told, the session is closed. Once.
    Never raises."""
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return await _publish(tx, hub, work_id)
    except Exception:  # a deliver is never undone by it
        log.exception("flow publish failed", extra={"work": str(work_id)})
        return None


async def _publish(tx: Tx, hub: Any, work_id: UUID) -> str | None:
    w = await flow_of_work(tx, work_id)
    if w is None:
        return None
    meta = w["flow"]
    if meta.get("sent"):
        return "sent"
    await tx.exec("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"flow:{w['ref']}")
    pkg = await package(tx, w)
    if pkg is None:
        if meta.get(
            "event"
        ):  # ⟨2026-11-18⟩ a breaking-news run its session skipped (not real or new)
            from hq_api.domain import flow_events as EV

            return await EV.close_skipped(tx, hub, w) or "open"
        await _ask_for_cover(tx, w)
        return "open"
    if meta.get("kind") == "tg_post":
        from hq_api.domain import tg_posts as TG

        return await TG.queue(tx, hub, w, meta, pkg)
    if meta.get("kind") == "video":
        return await _queue_video(tx, hub, w, meta, pkg)
    if meta.get("kind") == "article" or "zip" in pkg:
        return await _queue_article(tx, hub, w, meta, pkg)
    route = await SPB._route(tx, w["company_id"])
    account = str(meta.get("account") or "")
    if not route["ready"] or account not in route["accounts"]:
        return "route"
    if "stories" in pkg:
        if (held := await _art_missing(tx, w, meta, len(pkg["stories"]))) is not None:
            return held
        return await _publish_stories(tx, hub, w, meta, pkg, route, account)
    d, reel, story = pkg["d"], pkg["reel"], pkg["story"]
    caption = (await SPB._text_of(tx, hub, pkg["caption_d"], SPB.CAPTION_NAMES) or "").strip()
    comment = await SPB.comment_of(tx, hub, pkg["comment_d"]) if pkg["comment_d"] else None
    topic_d = pkg["topic_d"]
    topic = (
        (await SPB._text_of(tx, hub, topic_d, ("topic.txt",)) or "").strip().splitlines()
        if topic_d
        else []
    )
    if topic and (seen := await repeat_of(tx, account, topic[0], str(w["ref"]))) is not None:
        return await _hold_repeat(tx, w, meta, topic[0], seen)
    at = datetime.fromisoformat(str(meta["publish_at"]))
    when = at if at > datetime.now(UTC) + timedelta(minutes=2) else None
    order = str(meta.get("order") or "") or None
    sent = []
    pairs: tuple[tuple[SPB.Kind, dict[str, Any] | None], ...] = (
        ("reel", reel),
        ("story", story if meta.get("story") else None),
    )
    for what, f in pairs:
        if f is None:
            continue
        await SPB.lock_publication(tx, d["ref"], str(f["id"]), account, what)
        if await SPB.last_of(tx, d["ref"], str(f["id"]), account, what) is not None:
            continue
        j = await SPB._send(
            tx, FLOW, d, f, pkg["cover"] if what == "reel" else None,
            hub=hub, what=what, account=account, caption=caption if what == "reel" else "",
            route=route, order=order, scheduled_at=when,
            comment=comment if what == "reel" else None,
            publication={"flow_key": meta.get("key"), "day": meta.get("day"),
                         "topic_fa": topic[0] if topic else None},
        )  # fmt: skip
        sent.append((what, str(j["id"])))
    meta["sent"] = datetime.now(UTC).isoformat()
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))
           WHERE id = :w""",
        w=w["id"],
        m=_json(meta),
    )
    flow = await flow_by_key(tx, str(meta.get("key")))
    title = flow.title_fa if flow else "انتشار روزانه"
    from hq_api.domain import notify

    await notify.raise_notification(
        tx,
        company_id=w["company_id"],
        company_code=str(w["company"]),
        level="report",
        title_fa=READY_TITLE_FA.format(title=title)[:300],
        body_fa=READY_BODY_FA.format(at=at_fa(at), topic=(topic[0] if topic else "—"))[:1000],
        link_kind="order" if order else "deliverable",
        link_ref=order or str(d["ref"]),
        source_kind="system",
        source_code="flow",
    )
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.publish", action_class="A3",
        target_kind="order" if order else "deliverable", target_ref=order or str(d["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: {', '.join(f'{k} {v}' for k, v in sent)} "
        f"at {at.isoformat()} to @{account} (the owner's standing order of 2026-11-13)"[:500],
    )  # fmt: skip
    if order:
        # the day's work is done: nothing goes on spending (no playbook draft, no memory fold)
        from hq_api.domain import sessions as SE

        rep = await OR.ensure(tx, order)
        if rep is not None and rep.get("closed_at") is None:
            await SE.close(tx, order, "ok", "اتوماسیون روزانه: بسته زمان‌بندی شد", hub=hub)
    return "scheduled"


VIDEO_READY_BODY_FA = (
    "ویدیوی بلند امروز ساخته شد و {at} به وقت تهران روی یوتیوب دات‌کوین منتشر میشود، همراه مقاله‌اش "
    "روی dotcoin.me. موضوع: {topic}"
)
VIDEO_READY_OTHER_FA = (
    "ویدیوی بلند امروز ساخته شد و {at} به وقت تهران روی یوتیوب @{account} منتشر میشود. "
    "موضوع: {topic}"
)


async def _queue_video(
    tx: Tx, hub: Any, w: dict[str, Any], meta: dict[str, Any], pkg: dict[str, Any]
) -> str:
    """⟨2026-11-17⟩ A long-video day whose package is in: nothing goes to IG-Hub. The run is marked
    sent with `youtube: queued`; the hub's host uploader (youtube_long.py --due, a timer) reads the
    session's out/ and publishes it on YouTube at `publish_at`, once, after its checks. The owner
    hears it is ready and the session closes (nothing goes on spending)."""
    topic_d = pkg["topic_d"]
    topic = (
        (await SPB._text_of(tx, hub, topic_d, ("topic.txt",)) or "").strip().splitlines()
        if topic_d
        else []
    )
    at = datetime.fromisoformat(str(meta["publish_at"]))
    order = str(meta.get("order") or "") or None
    d = pkg["d"]
    meta["sent"] = datetime.now(UTC).isoformat()
    meta["youtube"] = "queued"
    if topic:  # (the page's «never twice» list reads it: published_topics)
        meta["topic_fa"] = " ".join(topic[0].split())[:300]
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))
           WHERE id = :w""",
        w=w["id"],
        m=_json(meta),
    )
    flow = await flow_by_key(tx, str(meta.get("key")))
    title = flow.title_fa if flow else "ویدیوی بلند"
    from hq_api.domain import notify

    await notify.raise_notification(
        tx,
        company_id=w["company_id"],
        company_code=str(w["company"]),
        level="report",
        title_fa=READY_TITLE_FA.format(title=title)[:300],
        body_fa=(
            VIDEO_READY_BODY_FA if meta.get("account") == "dotcoin.me" else VIDEO_READY_OTHER_FA
        ).format(
            at=at_fa(at), topic=(topic[0] if topic else "—"), account=meta.get("account") or ""
        )[:1000],
        link_kind="order" if order else "deliverable",
        link_ref=order or str(d["ref"]),
        source_kind="system",
        source_code="flow",
    )
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.publish", action_class="A3",
        target_kind="order" if order else "deliverable", target_ref=order or str(d["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: the long video {w['ref']} queued for "
        f"YouTube at {at.isoformat()} (youtube_long.py --due)"[:500],
    )  # fmt: skip
    if order:
        from hq_api.domain import sessions as SE

        rep = await OR.ensure(tx, order)
        if rep is not None and rep.get("closed_at") is None:
            await SE.close(tx, order, "ok", "اتوماسیون: ویدیوی بلند برای یوتیوب آماده شد", hub=hub)
    return "queued"


WEEK_LINES_MAX, WEEK_LINE_CHARS = 6, 300


async def _queue_article(
    tx: Tx, hub: Any, w: dict[str, Any], meta: dict[str, Any], pkg: dict[str, Any]
) -> str:
    """⟨2026-11-18⟩ A site's SEO day whose package is in: nothing goes to IG-Hub. The run is marked
    sent with `site: queued`, the day's line (and, on a Saturday, the week's lines for the owner's
    weekly summary) kept on it; the hub's host publisher (seo.py --due, a timer) reads the session's
    out/, checks it and puts it on the site at `publish_at`, once. No notification: the owner hears
    of the SEO only in the weekly summary (his standing rule: a real crisis, or the week)."""
    summary = (await SPB._text_of(tx, hub, pkg["summary_d"], (ARTICLE_SUMMARY,)) or "").strip()
    week_d = pkg.get("week_d")
    week = (await SPB._text_of(tx, hub, week_d, (ARTICLE_WEEK,)) or "") if week_d else ""
    topic_d = pkg.get("topic_d")
    topic = (await SPB._text_of(tx, hub, topic_d, ("topic.txt",)) or "").strip() if topic_d else ""
    order = str(meta.get("order") or "") or None
    d = pkg["d"]
    meta["sent"] = datetime.now(UTC).isoformat()
    meta["site"] = "queued"
    meta["summary_fa"] = " ".join(summary.split())[:WEEK_LINE_CHARS]
    if topic:
        meta["topic_fa"] = topic.splitlines()[0][:WEEK_LINE_CHARS]
    lines = [" ".join(x.split()).lstrip("-•* ").strip() for x in week.splitlines()]
    if any(lines):
        meta["week_fa"] = [x[:WEEK_LINE_CHARS] for x in lines if x][:WEEK_LINES_MAX]
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))
           WHERE id = :w""",
        w=w["id"],
        m=_json(meta),
    )
    at = datetime.fromisoformat(str(meta["publish_at"]))
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.publish", action_class="A3",
        target_kind="order" if order else "deliverable", target_ref=order or str(d["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: the SEO package of {w['ref']} queued for the "
        f"site at {at.isoformat()} (seo.py --due)"[:500],
    )  # fmt: skip
    if order:
        from hq_api.domain import sessions as SE

        rep = await OR.ensure(tx, order)
        if rep is not None and rep.get("closed_at") is None:
            await SE.close(tx, order, "ok", "اتوماسیون: بسته‌ی سئوی روز برای سایت آماده شد", hub=hub)
    return "queued"


SEO_WEEK_SQL = """SELECT w.run_meta -> 'flow' AS flow, f.title_fa FROM work.work w
    JOIN automations.flows f ON f.key = w.run_meta -> 'flow' ->> 'key'
    WHERE w.parent_id IS NULL AND w.run_meta -> 'flow' ->> 'kind' = 'article'
      AND w.run_meta -> 'flow' ? 'week_fa' AND w.created_at >= :since
    ORDER BY w.created_at DESC"""


async def seo_week_lines(tx: Tx, now: datetime) -> list[str]:
    """⟨2026-11-18⟩ The owner's weekly summary (the Saturday morning report): each SEO flow's newest
    week lines of the last eight days, under its title. Rule-based: the session wrote them."""
    out: list[str] = []
    seen: set[str] = set()
    for r in await tx.all(SEO_WEEK_SQL, since=now - timedelta(days=8)):
        m = OR._j(r["flow"]) or {}
        key = str(m.get("key") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(f"**{r['title_fa']}**")
        out += [f"- {x}" for x in (m.get("week_fa") or [])[:WEEK_LINES_MAX]]
    return out


LATE = timedelta(minutes=30)
# ⟨2026-11-24⟩ the owner: «استوری های جا مانده هم انجام بده … همه کار ها از فردا روی اصول اجرا بشوند».
# A story whose hour went by (the day was made late) goes out later the same day, in the middle of
# the widest gap left between the day's own hours, never closer than LATE_GAP to another and never
# after LATE_DAY_END (Tehran); one with no room left that day is left out.
LATE_START = timedelta(minutes=10)
LATE_GAP = timedelta(minutes=10)
LATE_DAY_END = time(23, 45)


def fill_late(slots: list[datetime], n: int, start: datetime, end: datetime) -> list[datetime]:
    """Up to `n` times between `start` and `end`, each in the middle of the widest gap left
    between the day's own hours (`slots`) and the ones already placed; sorted. Fewer when the
    day has no more room."""
    marks = sorted({start, end, *(t for t in slots if start < t < end)})
    out: list[datetime] = []
    while len(out) < n and start < end:
        width, a = max((b - a, a) for a, b in itertools.pairwise(marks))
        if width / 2 < LATE_GAP:
            break
        t = a + width / 2
        out.append(t)
        marks = sorted([*marks, t])
    return sorted(out)


STORIES_READY_TITLE_FA = "{title} آماده شد"
STORIES_READY_BODY_FA = (
    "{n} استوری امروز زمان‌بندی شد (اولی {at} به وقت تهران). کلمه‌ی جواب دایرکت: «{word}». "
    "موضوع روز: {topic}"
)


async def _publish_stories(
    tx: Tx, hub: Any, w: dict[str, Any], meta: dict[str, Any], pkg: dict[str, Any],
    route: dict[str, Any], account: str,
) -> str:  # fmt: skip
    """⟨2026-11-15⟩ Each picture of a stories flow at its own hour, with the day's reply rule (made
    when the first of them is out); an hour already gone by more than half an hour goes out later
    the same day, in a gap between its hours (⟨2026-11-24⟩; left out only when the day has no
    room). Sent again, it sends only what is not out or set yet."""
    flow = await flow_by_key(tx, str(meta["key"]))
    if flow is None:  # (package() read it already)
        return "open"
    comment = await SPB.comment_of(tx, hub, pkg["comment_d"])
    topic_d = pkg["topic_d"]
    topic = (
        (await SPB._text_of(tx, hub, topic_d, ("topic.txt",)) or "").strip().splitlines()
        if topic_d
        else []
    )
    now = datetime.now(UTC)
    # ⟨2026-11-18⟩ an event's stories (breaking news) go out the moment they are in
    times = (
        [now] * len(pkg["stories"])
        if meta.get("asap")
        else story_times(flow, date.fromisoformat(str(meta["day"])))
    )
    order = str(meta.get("order") or "") or None
    sent, late = [], []
    todo = []
    for i, ((f, d), at) in enumerate(zip(pkg["stories"], times, strict=False), 1):
        await SPB.lock_publication(tx, d["ref"], str(f["id"]), account, "story")
        if await SPB.last_of(tx, d["ref"], str(f["id"]), account, "story") is not None:
            continue  # out or set already (a day sent again sends only what is left)
        todo.append((i, f, d, at))
    # ⟨2026-11-24⟩ an hour gone by: later the same day, in the gaps between its own hours
    gone = [k for k, (_, _, _, at) in enumerate(todo) if at < now - LATE]
    day_end = datetime.combine(
        date.fromisoformat(str(meta["day"])), LATE_DAY_END, ZoneInfo(TEHRAN)
    ).astimezone(UTC)
    moved = fill_late([t for t in times if t >= now], len(gone), now + LATE_START, day_end)
    for k, at in zip(gone, moved, strict=False):
        todo[k] = (*todo[k][:3], at)
    late = [todo[k][0] for k in gone[len(moved) :]]
    for i, f, d, at in todo:
        if i in late:
            continue
        j = await SPB._send(
            tx, FLOW, d, f, None, hub=hub, what="story", account=account, caption="",
            route=route, order=order, scheduled_at=at if at > now + timedelta(minutes=2) else None,
            comment=comment,
            # ⟨1.39⟩ §60.1 the day's slides are one set: "{account}:{day}:{output}" and each place
            publication={"flow_key": meta.get("key"), "day": meta.get("day"),
                         "topic_fa": topic[0] if topic else None,
                         "set_key": f"{account}:{meta['day']}:{pkg['d']['ref']}", "n": i},
        )  # fmt: skip
        sent.append((i, str(j["id"])))
    meta["sent"] = now.isoformat()
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))
           WHERE id = :w""",
        w=w["id"],
        m=_json(meta),
    )
    from hq_api.domain import notify

    first = times[sent[0][0] - 1] if sent else times[0]
    await notify.raise_notification(
        tx,
        company_id=w["company_id"],
        company_code=str(w["company"]),
        level="report",
        title_fa=STORIES_READY_TITLE_FA.format(title=flow.title_fa)[:300],
        body_fa=STORIES_READY_BODY_FA.format(
            n=str(len(sent)).translate(FA_DIGITS),
            at=at_fa(first),
            word=((comment or {}).get("keywords") or ["—"])[0],
            topic=topic[0] if topic else "—",
        )[:1000],
        link_kind="order" if order else "deliverable",
        link_ref=order or str(pkg["d"]["ref"]),
        source_kind="system",
        source_code="flow",
    )
    await audit.record(
        tx, FLOW, company_id=w["company_id"], action="flow.publish", action_class="A3",
        target_kind="order" if order else "deliverable", target_ref=order or str(pkg["d"]["ref"]),
        summary=f"{meta.get('key')} {meta.get('day')}: stories {', '.join(f'{i} {j}' for i, j in sent)}"
        f"{f' (late, left out: {late})' if late else ''} to @{account}; rule word "
        f"{((comment or {}).get('keywords') or ['-'])[0]} (the owner's order of 2026-11-15)"[:500],
    )  # fmt: skip
    if order:
        from hq_api.domain import sessions as SE

        rep = await OR.ensure(tx, order)
        if rep is not None and rep.get("closed_at") is None:
            await SE.close(tx, order, "ok", "اتوماسیون روزانه: استوری‌ها زمان‌بندی شد", hub=hub)
    return "scheduled"


async def on_published(tx: Tx, args: dict[str, Any], done: Any) -> None:
    """A flow's reel went out (IG-Hub's success): the owner hears it with its link."""
    s = args.get("session") or {}
    if args.get("kind") != "reel" or not s.get("order"):
        return
    order = await OR.load_order(tx, str(s["order"]))
    if order is None:
        return
    row = await tx.first(
        """SELECT w.company_id, c.code, w.run_meta -> 'flow' AS flow FROM work.work w
           JOIN core.companies c ON c.id = w.company_id
           WHERE w.ref = ANY(:refs) AND w.run_meta ? 'flow' LIMIT 1""",
        refs=list(OR.root_refs(order)),
    )
    if row is None:
        return
    meta = OR._j(row["flow"]) or {}
    flow = await flow_by_key(tx, str(meta.get("key")))
    from hq_api.domain import notify

    await notify.raise_notification(
        tx,
        company_id=row["company_id"],
        company_code=str(row["code"]),
        level="report",
        title_fa=OUT_TITLE_FA.format(title=flow.title_fa if flow else "انتشار روزانه")[:300],
        body_fa=OUT_BODY_FA,
        link_kind="order",
        link_ref=str(s["order"]),
        source_kind="system",
        source_code="flow",
    )
