"""⟨2026-11-14⟩ The n8n flows (domain/flows.py) on the automations board, step by step.

The owner: «یدونه اتوماسیون n8n داریم که باید توی اتوماسیون ها باشه و مرحله به مرحله کارهایی که
میکنه رو توی اتوماسیون نشون بده … هر اتوماسیونی که ست میشه». Each flow is a board item
`N8:<key>` (kind `n8n`) that opens the same page as a §59.7 flow: its steps from n8n's call to the
owner's notice, its days as runs (`F-…`, the day's order) newest first, today's cost, the switch.
A day's page (`GET /line-runs/F-…`) shows each step's state, read by code from what the day left:
the work and its turns, the files of its outputs, IG-Hub's answers, the notices. No model call.

The switch is the hub's (owner.settings.flows_off): n8n still calls at its hour and the hub makes
nothing. The page's other controls (run now, pause, skip, hour, budget, replies) belong to §59
flows; here they answer 409 in Persian: these are set with the hub's Claude.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.domain import flows as FL
from hq_api.domain import order_report as OR
from hq_api.domain import session_publish as SPB
from hq_api.errors import ApiError
from hq_api.lines import store

REF = re.compile(r"^N8:([a-z][a-z0-9_]{0,40})$")
ORDER_REF = re.compile(r"^F-[0-9]{4,}$")
OPUS = "claude-opus-5-5"
NOT_HERE_FA = "این اتوماسیون را Claude سرور هاب تنظیم میکند؛ همین را در گفتگو بگو."
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def ref_of(key: str) -> str:
    return f"N8:{key}"


def flow_of(ref: str) -> FL.Flow | None:
    m = REF.fullmatch(ref)
    return FL.FLOWS.get(m.group(1)) if m else None


def load(ref: str) -> FL.Flow:
    flow = flow_of(ref)
    if flow is None:
        raise ApiError(404, "not_found", f"no automation {ref}")
    return flow


def not_here() -> ApiError:
    return ApiError(409, "validation_failed", "an n8n flow is set by the hub's Claude",
                    message_fa=NOT_HERE_FA)  # fmt: skip


# ---------------------------------------------------------------- the steps --
def _step(key: str, title: str, kind: str, helper: str, out: str = "", inp: str = "",
          rules: tuple[str, ...] = (), model: str | None = None) -> FS.FlowStep:  # fmt: skip
    return FS.FlowStep(
        key=key, title_fa=title, kind=kind, helper=helper,
        model=model, effort="max" if model else None, input_fa=inp, output_fa=out,
        rules_fa=list(rules),
    )  # fmt: skip


def _model(flow: FL.Flow) -> str:
    """The model its workshop turns run on today (⟨2026-11-15⟩ a flow may name its own)."""
    return FL.model_on(flow, datetime.now(_tz()).date()) or OPUS


def recipe(flow: FL.Flow) -> str:
    """⟨2026-11-15⟩ Which steps a flow has: «stories», a Zarib×100 reel, or the Pro-Chart reel."""
    if flow.stories:
        return "stories"
    if flow.recipe:  # ⟨2026-11-16⟩ ipoxxo: Zarib×100's premium recipe on its own page
        return "zaribsad" if flow.recipe == "ipoxxo" else flow.recipe  # (⟨11-17⟩ «dotcoin»)
    return "zaribsad" if "/zaribsad-" in flow.kit else "reel"


# ⟨2026-11-16⟩ what a stories flow's own steps say, by its page (the default: Zarib×100's)
STORY_TEXT: dict[str, dict[str, tuple[str, str]]] = {
    "": {
        "data": ("داده‌ی بازار و کارنامه‌ی VIP", "قیمت‌ها، ترس و طمع، آمار سیگنال‌ها از سایت تریدیار"),
        "dm": ("جواب دایرکت با سه دکمه", "comment.txt: ورود رایگان VIP، ثبت‌نام LBank، راهنما"),
        "rule": ("جواب دایرکت استوری‌ها", "هر کس کلمه‌ی امروز را بفرستد، دعوت VIP با سه دکمه میگیرد"),
    },
    # ⟨2026-11-17⟩ DotCoin.me: the day's lesson in twelve slides from ONE ChatGPT chat
    "dotcoin": {
        "data": ("درس روز از بانک ایده‌ها", "یک موضوع آموزشی تازه، در ۱۲ قدم"),
        "pictures": (
            "۱۲ اسلاید با ChatGPT در یک گفتگو",
            "سه لایه‌ی رنگ: خردلی و مشکی برند، محتوای تمام‌رنگی، سبز و قرمز معنا",
        ),
        "compose": ("نشان پیج، شماره‌ی اسلاید و کلمه‌ی امروز روی هر اسلاید", ""),
        "dm": ("جواب دایرکت با خلاصه‌ی درس", "comment.txt: خلاصه‌ی درس روز در چند خط"),
        "rule": ("جواب دایرکت استوری‌ها", "هر کس کلمه‌ی امروز را بفرستد، خلاصه‌ی درس را میگیرد"),
    },
    "ipoxxo": {
        "data": (
            "ایده‌های روز از بانک ایده‌ها",
            "سه ایده‌ی تبلیغی تازه برای جذب از اینستاگرام به کانال",
        ),
        "dm": ("جواب دایرکت با دکمه‌ی کانال", "comment.txt: لینک کانال تلگرام t.me/ipoxxo"),
        "rule": (
            "جواب دایرکت استوری‌ها",
            "هر کس «لینک» را ریپلای کند، لینک کانال رایگان را در دایرکت میگیرد",
        ),
    },
}


# the lane (who does it) of each step: one row per lane on the app's canvas
LANE = {
    "n8n": "n8n", "order": "hub", "package": "hub", "report": "hub",
    "schedule": "ighub", "publish": "ighub", "replies": "ighub", "rule": "ighub",
    "script": "chatgpt", "keyart": "chatgpt", "cover_gpt": "chatgpt", "pictures": "chatgpt",
    "voice": "voice",
}  # fmt: skip


def _head(flow: FL.Flow) -> list[FS.FlowStep]:
    at = flow.trigger_at.translate(FA_DIGITS)
    day = "همان روز" if flow.same_day else "روز بعد"
    if flow.stories:
        when = f"{len(flow.stories)} استوری، از {flow.stories[0]} تا {flow.stories[-1]}"
    else:
        when = "ساعت انتشار در دور چهار هفته‌ای: " + "، ".join(
            h or "پربازدیدترین ساعت" for h in flow.hours
        )
    cap = f"سقف هزینه‌ی هر روز {int(flow.usd_cap)} دلار؛ بیشتر شد، کار میایستد و خبر میرسد"
    rules = [when.translate(FA_DIGITS), cap.translate(FA_DIGITS)]
    if flow.cycle:
        rules.append("نوع روز به نوبت: " + "، ".join(flow.cycle))
    if flow.pair:
        rules.append("ریلز دوم روز؛ هیچ‌وقت هم‌ساعت ریلز اول نیست")
    return [
        _step("n8n", "n8n روند را روشن میکند", "n8n", "code", inp=f"هر روز ساعت {at} تهران",
              out=f"درخواست امضاشده به هاب برای {day}"),
        _step("order", "سفارش روز در هاب", "order", "code",
              out=f"یک جلسه‌ی خودکار در کارگاه، روی {_model(flow)}؛ بی پرسش و بی انتظار",
              rules=tuple(rules)),
    ]  # fmt: skip


def _tail(flow: FL.Flow) -> list[FS.FlowStep]:
    what = f"ریلز و استوری @{flow.account}" if flow.story else f"ریلز @{flow.account}"
    return [
        _step("package", "بسته‌ی کامل", "package", "code",
              rules=(f"تا هر {'شش' if flow.story else 'پنج'} فایل نرسیده، چیزی منتشر نمیشود",)),
        _step("schedule", "زمان‌بندی روی IG-Hub", "publish", "ighub", out=what),
        _step("publish", "انتشار در ساعت خودش", "publish", "ighub"),
        _step("replies", "کامنت هوشمند و جواب استوری" if flow.story else "کامنت هوشمند",
              "publish", "ighub", out="دایرکت با دکمه‌ی لینک، ده جواب عمومی"),
        _step("report", "خبر به مدیر کل", "report", "code",
              out="«آماده شد» و «منتشر شد» با لینک"),
    ]  # fmt: skip


def steps_of(flow: FL.Flow) -> list[FS.FlowStep]:
    """What the flow does, in order (the kit's README for the workshop's part); ⟨2026-11-17⟩ a
    flow's own effort on its model's steps (DotCoin.me: xhigh)."""
    steps = _steps_of(flow)
    if not flow.effort:
        return steps
    return [s.model_copy(update={"effort": flow.effort}) if s.model else s for s in steps]


def _steps_of(flow: FL.Flow) -> list[FS.FlowStep]:
    m = _model(flow)
    kind = recipe(flow)
    if kind == "stories":
        n = len(flow.stories)
        posts = [
            _step(f"s{i}", f"استوری {i}".translate(FA_DIGITS), "publish", "ighub",
                  inp=f"ساعت {hm}".translate(FA_DIGITS), out=f"story_{i}.jpg")
            for i, hm in enumerate(flow.stories, 1)
        ]  # fmt: skip
        own = STORY_TEXT.get(flow.recipe) or {}
        txt = own or STORY_TEXT[""]
        word = (
            _step("word", f"کلمه‌ی ثابت «{flow.story_word}»", "workshop", "workshop", model=m,
                  rules=("هر روز همین کلمه؛ جواب همیشه همان لینک است",))
            if flow.story_word
            else _step("word", "کلمه‌ی امروز", "workshop", "workshop", model=m,
                       rules=("کلمه‌ی تازه؛ هیچ‌وقت کلمه‌ای که پیش از این گرفته شده",))
        )  # fmt: skip
        return [
            *_head(flow),
            _step("data", txt["data"][0], "workshop", "code", out=txt["data"][1]),
            word,
            _step("pictures", txt["pictures"][0], "workshop", "gpt", out=txt["pictures"][1],
                  rules=(("بی انیمه، بی جمله‌ی هشدار",) if "pictures" not in own else ()))
            if "pictures" in txt
            else _step("pictures", f"{n} عکس واقعی با ChatGPT".translate(FA_DIGITS), "workshop",
                       "gpt", out="عکس تازه‌ی همان روز، بی متن", rules=("بی انیمه، بی جمله‌ی هشدار",)),
            _step("compose", txt["compose"][0] if "compose" in txt
                  else "متن، نشان پیج و دعوت روی هر عکس", "workshop", "workshop", model=m,
                  out=f"story_1.jpg تا story_{n}.jpg".translate(FA_DIGITS)),
            _step("dm", txt["dm"][0], "workshop", "workshop", model=m, out=txt["dm"][1]),
            _step("package", "بسته‌ی روز", "package", "code",
                  rules=("تا همه‌ی عکس‌ها و جواب دایرکت نرسیده، چیزی منتشر نمیشود",)),
            _step("schedule", "زمان‌بندی روی IG-Hub", "publish", "ighub",
                  out=f"هر استوری در ساعت خودش روی @{flow.account}",
                  rules=("ساعتی که بیش از نیم ساعت گذشته باشد جا میماند",)),
            *posts,
            _step("rule", txt["rule"][0], "publish", "ighub", out=txt["rule"][1]),
            _step("report", "خبر به مدیر کل", "report", "code", out="«آماده شد» با کلمه‌ی امروز"),
        ]  # fmt: skip
    if kind == "dotcoin":
        # ⟨2026-11-17⟩ DotCoin.me: a look of its own from its own Pinterest search, every reel
        topic = ("درس روز از بانک ایده‌ها (آموزشی)" if "آموزشی" in flow.cycle
                 else "خبر مهم روز با داده‌ی همان لحظه (اطلاع‌رسانی)")  # fmt: skip
        return [
            *_head(flow),
            _step("topic", topic, "workshop", "workshop", out="topic.txt", model=m),
            _step("inspire", "جستجو و دانلود نمونه از پینترست", "workshop", "workshop", model=m,
                  out="۴ تا ۸ نمونه‌ی همین ریلز و سبک آن در CONTRACT.md",
                  rules=("هر ریلز سبک خودش؛ هیچ‌وقت سبک ریلز قبلی",)),
            _step("script", "سناریو با ChatGPT", "workshop", "gpt", out="متن گوینده",
                  rules=("فقط آموزشی و اطلاع‌رسانی؛ بی پیش‌بینی قیمت و سیگنال",)),
            _step("voice", "صدای گوینده (Arlo)", "workshop", "aistudio", out="فایل صدا"),
            _step("voice_check", "بازبینی صدا، نام‌ها و زمان هر کلمه", "workshop", "code"),
            _step("keyart", "تصویرها با ChatGPT و Gemini", "workshop", "gpt",
                  out="تصویرهای بی متن، به سبک نمونه‌ها"),
            _step("direction", "کارگردانی: نماها، دوربین، ترنزیشن و صدا", "workshop", "workshop",
                  model=m, rules=("سه لایه‌ی رنگ: برند خردلی و مشکی، محتوا آزاد، سبز و قرمز معنا",)),
            _step("render", "موشن‌گرافی، یک بار رندر ۶۰ فریم", "workshop", "workshop",
                  out="video.mp4", model=m, rules=("فونت IRANYekanX Pro، تمیز و شارپ",)),
            _step("cover", "کاور کامل با ChatGPT از فولدر مدیر کل", "workshop", "gpt",
                  out="cover.jpg", rules=("خود مدیر کل با کت‌وشلوار تازه؛ هر حرف فارسی چک میشود",)),
            _step("texts", "کپشن، کلمه‌ی کامنت و خلاصه‌ی دایرکت", "workshop", "workshop",
                  out="caption.txt، comment.txt", model=m),
            *_tail(flow),
        ]  # fmt: skip
    if kind == "zaribsad":
        topic = ("ارز روز و داده‌های واقعی آن" if "coin" in flow.key
                 else "ایده‌ی تبلیغی تازه برای کانال رایگان ipoxxo، از بانک ایده‌ها"
                 if flow.recipe == "ipoxxo"
                 else "موضوع روز به نوع روز، با داده‌ی همان لحظه")  # fmt: skip
        return [
            *_head(flow),
            _step("topic", topic, "workshop", "workshop", out="topic.txt", model=m),
            _step("inspire", "ایده از پینترست و ریلزهای تاپ", "workshop", "workshop", model=m,
                  out="۳ تا ۶ نمونه‌ی سطح بالا، هر روز تازه"),
            _step("script", "سناریو با ChatGPT", "workshop", "gpt", out="متن گوینده",
                  rules=("بی جمله‌ی هشدار؛ هر عدد از داده‌ی همان روز",)),
            _step("voice", "صدای گوینده (Cruz)", "workshop", "aistudio", out="فایل صدا"),
            _step("voice_check", "بازبینی صدا، نام برندها و زمان هر کلمه", "workshop", "code"),
            _step("keyart", "تصویرهای کلیدی با ChatGPT", "workshop", "gpt",
                  out="دست‌کم شش تصویر واقعی یا سه‌بعدی، بی متن"),
            _step("direction", "کارگردانی: نماها، دوربین، ترنزیشن و صدا", "workshop", "workshop",
                  model=m),
            _step("render", "موشن‌گرافی پرمیوم، یک بار رندر ۶۰ فریم", "workshop", "workshop",
                  out="video.mp4", model=m, rules=("تمیز و شارپ؛ بی ذره و تاری، بی ضربه‌ی صدا",)),
            *([_step("story", "برش استوری", "workshop", "code", out="story.mp4 (حداکثر ۵۹٫۸ ثانیه)")]
              if flow.story else []),
            _step("cover", "کاور از پک کاور با ChatGPT", "workshop", "gpt", out="cover.jpg",
                  rules=("سه رنگ پیج، عنوان با فونت خودمان، یک المان از موضوع",)),
            _step("texts", "کپشن، کلمه‌ی کامنت و دایرکت", "workshop", "workshop",
                  out="caption.txt، comment.txt", model=m),
            *_tail(flow),
        ]  # fmt: skip
    return [
        *_head(flow),
        _step("topic", "موضوع روز از بانک موضوع‌ها", "workshop", "workshop", out="topic.txt",
              model=m),
        _step("script", "سناریو", "workshop", "gpt", out="متن گوینده",
              rules=("اگر ChatGPT جواب نداد، Claude خودش مینویسد",)),
        _step("voice", "صدای گوینده", "workshop", "gemini", out="فایل صدا"),
        _step("voice_check", "بازبینی صدا و زمان هر کلمه", "workshop", "code"),
        _step("direction", "کارگردانی و تدوین روی کاغذ", "workshop", "workshop", model=m),
        _step("render", "ساخت ویدیو، یک بار رندر", "workshop", "workshop", out="video.mp4",
              model=m),
        _step("story", "برش استوری", "workshop", "code", out="story.mp4 (حداکثر ۵۹٫۸ ثانیه)"),
        _step("cover", "کاور با المان همان روز", "workshop", "workshop", out="cover.jpg",
              model=m),
        _step("texts", "کپشن و متن کامنت", "workshop", "workshop",
              out="caption.txt، comment.txt", model=m),
        *_tail(flow),
    ]  # fmt: skip


LANES = ("n8n", "hub", "workshop", "chatgpt", "voice", "ighub")


def _lane(s: FS.FlowStep) -> str:
    if s.key in LANE:
        return LANE[s.key]
    return {"gpt": "chatgpt", "ighub": "ighub"}.get(str(s.helper), "workshop")


def graph_of(flow: FL.Flow) -> FS.FlowGraph:
    """⟨2026-11-15⟩ The flow's map, as n8n draws one: a node per step on its lane, left to right
    in time; a stories flow fans out from its schedule to its stories, one row each, and its reply
    rule follows the first that goes out."""
    steps = steps_of(flow)
    posts = [s.key for s in steps if s.key[0] == "s" and s.key[1:].isdigit()]
    nodes: list[FS.FlowGraphNode] = []
    edges: list[FS.FlowGraphEdge] = []
    col, prev = 0, None
    for s in steps:
        if s.key in posts:
            row = posts.index(s.key)
            nodes.append(FS.FlowGraphNode(key=s.key, title_fa=s.title_fa, kind=s.kind,
                                          helper=s.helper, lane="ighub", col=col, row=row,
                                          note_fa=s.input_fa))  # fmt: skip
            edges.append(FS.FlowGraphEdge(source="schedule", target=s.key, label_fa=s.input_fa))
            if s.key == posts[-1]:
                col, prev = col + 1, posts[0]
            continue
        nodes.append(FS.FlowGraphNode(key=s.key, title_fa=s.title_fa, kind=s.kind, helper=s.helper,
                                      lane=_lane(s), col=col, note_fa=s.output_fa, model=s.model))  # fmt: skip
        if prev is not None:
            label = "وقتی اولین استوری رفت" if posts and prev == posts[0] else ""
            edges.append(FS.FlowGraphEdge(source=prev, target=s.key, label_fa=label))
        prev, col = s.key, col + 1
    return FS.FlowGraph(lanes=[x for x in LANES if any(n.lane == x for n in nodes)],
                        nodes=nodes, edges=edges)  # fmt: skip


WORKSHOP = ("topic", "script", "voice", "voice_check", "direction", "render", "story", "cover",
            "texts", "inspire", "keyart", "data", "word", "pictures", "compose", "dm")  # fmt: skip
FILE_OF = {"topic": ("topic.txt",), "render": ("video.mp4",), "story": ("story.mp4",),
           "cover": ("cover.jpg", "cover.png"), "texts": ("caption.txt", "comment.txt"),
           "dm": ("comment.txt",)}  # fmt: skip


# ---------------------------------------------------------------- the days --
def _tz() -> ZoneInfo:
    return ZoneInfo(FL.TEHRAN)


async def _days(
    tx: Tx, flow: FL.Flow, limit: int, before: str | None = None
) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT w.id, w.ref, w.status, w.company_id, w.created_at, w.closed_at,
                  w.run_meta -> 'flow' AS flow
           FROM work.work w
           WHERE w.run_meta -> 'flow' ->> 'key' = :k AND w.parent_id IS NULL
             AND (CAST(:b AS text) IS NULL OR w.run_meta -> 'flow' ->> 'order' < :b)
           ORDER BY w.created_at DESC LIMIT :n""",
        k=flow.key, b=before, n=limit,
    )  # fmt: skip
    return [{**dict(r), "flow": OR._j(r["flow"]) or {}} for r in rows]


async def _day_by_order(tx: Tx, order: str) -> dict[str, Any] | None:
    row = await tx.first(
        """SELECT w.id, w.ref, w.status, w.company_id, w.created_at, w.closed_at,
                  w.run_meta -> 'flow' AS flow
           FROM work.work w
           WHERE w.run_meta -> 'flow' ->> 'order' = :o AND w.parent_id IS NULL
           ORDER BY w.created_at DESC LIMIT 1""",
        o=order,
    )
    return {**dict(row), "flow": OR._j(row["flow"]) or {}} if row is not None else None


async def _facts(tx: Tx, d: dict[str, Any]) -> dict[str, Any]:
    """What the day left, read by code: its turns, its files, IG-Hub's answers, the cost."""
    meta, order = d["flow"], str(d["flow"].get("order") or "")
    turns = await tx.all(
        """SELECT state, started_at, finished_at FROM infra.server_jobs
           WHERE work_ref = :w AND kind = 'claude' ORDER BY created_at""",
        w=d["ref"],
    )
    files = await tx.all(
        """SELECT f.id, lower(trim(f.name)) AS name, dl.created_at
           FROM cartable.deliverables dl
           JOIN files.files f ON f.id = ANY(dl.attachments) AND f.variant = 'original'
           WHERE dl.work_id = :w ORDER BY dl.created_at""",
        w=d["id"],
    )
    jobs = await tx.all(
        """SELECT args ->> 'kind' AS kind, args -> 'meta' ->> 'rule_for' IS NOT NULL
                  OR args ? 'rule_for' AS rule, state, error_code, finished_at, result,
                  lower(args -> 'session' ->> 'file_name') AS file_name,
                  args -> 'session' ->> 'file_id' AS file_id
           FROM infra.server_jobs
           WHERE kind = 'publish' AND (args -> 'session' ->> 'order' = :o
                                       OR args -> 'rule_for' ->> 'order' = :o)
           ORDER BY created_at""",
        o=order,
    )
    said = await tx.all(
        """SELECT title_fa, created_at FROM notify.notifications
           WHERE source_code = 'flow' AND link_ref = :o ORDER BY created_at""",
        o=order,
    )
    usd = await FL.spent_usd(tx, str(d["ref"]))
    tokens = await tx.scalar(
        """SELECT COALESCE(SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                  + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)
           FROM llm.calls WHERE work_ref = :w""",
        w=d["ref"],
    )
    newest: dict[str, dict[str, Any]] = {}
    for f in files:
        newest[str(f["name"])] = dict(f)
    # ⟨2026-11-15⟩ one post is one record: its newest job (§46: IG-Hub's answer to the hub's
    # question about a scheduled post is a new job of the same file), and a cancelled one is gone
    post: dict[tuple[str, str], dict[str, Any]] = {}
    for j in jobs:
        if not j["rule"]:
            post[(str(j["kind"]), str(j["file_id"] or j["file_name"] or ""))] = j
    live = [j for j in post.values() if not _ext(j).startswith(SPB.CANCELLED)
            and str(j["error_code"] or "") != SPB.CANCEL_CODE]  # fmt: skip
    jobs = [j for j in jobs if j["rule"] or any(j is x for x in live)]
    scheduled = [j for j in live if j["state"] == "done" and _ext(j).startswith(SPB.PENDING)]
    out = [j for j in live if j["state"] == "done" and _ext(j)
           and not _ext(j).startswith(SPB.PENDING)]  # fmt: skip
    failed = [j for j in jobs if j["state"] == "failed"]
    rules = [j for j in jobs if j["rule"]]
    reel_url = next((str((OR._j(j["result"]) or {}).get("url") or "") or None
                     for j in out if j["kind"] == "reel"), None)  # fmt: skip
    return {"meta": meta, "turns": [dict(t) for t in turns], "files": newest, "jobs": jobs,
            "scheduled": scheduled, "out": out, "failed": failed, "rules": rules,
            "said": [dict(x) for x in said], "usd": usd, "tokens": int(tokens or 0),
            "reel_url": reel_url, "dropped": bool(post) and not live}  # fmt: skip


def _ext(j: dict[str, Any]) -> str:
    """A publish job's answer from IG-Hub: `pub:<id>` (held for its hour), the post's id, or ""."""
    return str((OR._j(j["result"]) or {}).get("external_id") or "")


def _state(d: dict[str, Any], f: dict[str, Any]) -> tuple[str, str]:
    """The day as a run: queued · running · waiting · done · failed · cancelled, and one line."""
    meta = f["meta"]
    running = any(t["state"] in ("queued", "running") for t in f["turns"])
    flow = FL.FLOWS.get(str(meta.get("key")))
    if flow is not None and flow.stories and (f["out"] or f["scheduled"]):
        # ⟨2026-11-15⟩ the day's stories: done when none is still waiting for its hour
        posts = [j for j in f["jobs"] if j["kind"] == "story" and not j["rule"]]
        n_out = len([j for j in posts if j in f["out"]])
        n_wait = len([j for j in posts if j not in f["out"] and j["state"] != "failed"])
        if not n_wait:
            return "done", f"{n_out} استوری منتشر شد".translate(FA_DIGITS)
        return "waiting", f"{n_out} از {n_out + n_wait} استوری منتشر شد".translate(FA_DIGITS)
    if f["reel_url"]:
        return "done", "منتشر شد"
    if f["failed"] and not f["scheduled"]:
        return "failed", "انتشار روی IG-Hub نشد"
    if f["dropped"]:
        return "cancelled", "انتشارش لغو شد"
    if meta.get("sent") or f["scheduled"]:
        at = meta.get("publish_at")
        when = FL.at_fa(datetime.fromisoformat(str(at))) if at else ""
        return "waiting", f"زمان‌بندی شد برای {when}".strip()
    if meta.get("capped"):
        return "failed", f"به سقف هزینه‌ی روز رسید ({meta['capped']} دلار)"
    if d["status"] == "failed":
        return "failed", "ساخت به نتیجه نرسید"
    if d["status"] == "cancelled":
        return "cancelled", "لغو شد"
    if running:
        return "running", "در کارگاه ساخته میشود"
    return ("running" if f["turns"] else "queued"), "منتظر نوبت کارگاه"


def _when(d: dict[str, Any]) -> datetime | None:
    at = d["flow"].get("publish_at")
    return datetime.fromisoformat(str(at)) if at else None


async def _topic(tx: Tx, hub: Any, d: dict[str, Any], f: dict[str, Any]) -> str | None:
    t = f["files"].get("topic.txt")
    if t is None or hub is None:
        return None
    got = (await store.step_files(tx, [str(t["id"])], getattr(hub, "storage", None))).get(
        str(t["id"])
    )
    lines = ((got.text if got else None) or "").strip().splitlines()
    return lines[0][:300] if lines else None


async def run_ref(tx: Tx, hub: Any, d: dict[str, Any]) -> FS.FlowRunRef:
    f = await _facts(tx, d)
    state, note = _state(d, f)
    return FS.FlowRunRef(
        ref=str(d["flow"].get("order") or d["ref"]), at=_when(d) or d["created_at"],
        state=state, topic_fa=await _topic(tx, hub, d, f), note_fa=note,
        cost_usd=float(round(f["usd"], 2)),
        results=FS.RunResults(permalink=f["reel_url"]) if f["reel_url"] else None,
    )  # fmt: skip


async def runs(
    tx: Tx, hub: Any, ref: str, limit: int = 20, before: str | None = None
) -> FS.FlowRuns:
    flow = load(ref)
    days = await _days(tx, flow, limit + 1, before)
    items = [await run_ref(tx, hub, d) for d in days[:limit]]
    nxt = items[-1].ref if len(days) > limit and items else None
    return FS.FlowRuns(items=items, next_cursor=nxt)


# --------------------------------------------------------------- the page --
def next_trigger(flow: FL.Flow, now: datetime | None = None) -> datetime:
    tz = _tz()
    now = (now or datetime.now(UTC)).astimezone(tz)
    hh, mm = (int(x) for x in flow.trigger_at.split(":"))
    at = datetime.combine(now.date(), time(hh, mm), tz)
    if at <= now:
        at += timedelta(days=1)
    return at.astimezone(UTC)


def when_fa(flow: FL.Flow, day: date | None = None) -> str:
    if flow.stories:
        return (f"هر روز {flow.trigger_at} ساخت، {len(flow.stories)} استوری از {flow.stories[0]} "
                f"تا {flow.stories[-1]}").translate(FA_DIGITS)  # fmt: skip
    hm = flow.hours[FL.week_of(flow, day)] if day else None
    when = "امروز" if flow.same_day else "فردا"
    publish = f"، انتشار {when} {hm}" if hm else f"، انتشار {when}"
    return f"هر روز {flow.trigger_at} ساخت{publish}".translate(FA_DIGITS)


async def _today_cost(tx: Tx, flow: FL.Flow) -> tuple[int, float]:
    start = datetime.combine(datetime.now(_tz()).date(), time(0, 0), _tz()).astimezone(UTC)
    row = await tx.first(
        """SELECT count(DISTINCT w.id) AS n, COALESCE(SUM(c.equiv_cost_usd), 0) AS usd
           FROM work.work w LEFT JOIN llm.calls c ON c.work_ref = w.ref AND c.started_at >= :s
           WHERE w.run_meta -> 'flow' ->> 'key' = :k AND w.parent_id IS NULL
             AND (w.created_at >= :s OR c.id IS NOT NULL)""",
        k=flow.key, s=start,
    )  # fmt: skip
    return (int(row["n"] or 0), float(round(Decimal(str(row["usd"] or 0)), 2))) if row else (0, 0.0)


async def _company(tx: Tx, flow: FL.Flow) -> dict[str, Any]:
    row = await tx.first(
        "SELECT id, code, name_fa FROM core.companies WHERE code = :c", c=flow.company
    )
    return dict(row) if row is not None else {"id": None, "code": flow.company, "name_fa": ""}


async def render(tx: Tx, hub: Any, ref: str) -> FS.FlowAutomation:
    flow = load(ref)
    co = await _company(tx, flow)
    off = flow.key in await FL.off_keys(tx)
    days = await _days(tx, flow, 1)
    last = await run_ref(tx, hub, days[0]) if days else None
    n, usd = await _today_cost(tx, flow)
    trig = next_trigger(flow)
    upcoming = []
    for i in range(14):
        day = (trig.astimezone(_tz()) + timedelta(days=i)).date() + timedelta(
            days=0 if flow.same_day else 1
        )
        if co["id"] is not None:
            at, _ = await FL.slot_of(tx, flow, day, co["id"])
            upcoming.append(FS.FlowOccurrence(at=at))
    tick = await tx.scalar("SELECT last_tick_at FROM growth.flow_clock LIMIT 1")
    made = await tx.scalar(
        "SELECT min(created_at) FROM work.work WHERE run_meta -> 'flow' ->> 'key' = :k", k=flow.key
    )
    tomorrow = (trig.astimezone(_tz())).date() + timedelta(days=0 if flow.same_day else 1)
    return FS.FlowAutomation(
        ref=ref, kind="flow", company=flow.company, company_fa=co["name_fa"] or "",
        playbook=None, version=None, line=None, title_fa=flow.title_fa,
        state="off" if off else "on",
        schedule=FS.FlowSchedule(mode="fixed", at=flow.trigger_at, when_fa=when_fa(flow, tomorrow)),
        account=flow.account, story=flow.story, mode="auto",
        budget=FS.FlowBudget(per_run_usd=float(flow.usd_cap), per_day_usd=float(flow.usd_cap),
                             spent_today_usd=usd),
        steps=steps_of(flow), graph=graph_of(flow), next=upcoming[0] if upcoming and not off else None,
        upcoming=[] if off else upcoming, last_run=last, today=FS.FlowToday(runs=n, cost_usd=usd),
        n8n=FS.FlowN8n(workflow=flow.n8n or "n8n", last_tick_at=tick),
        created_at=made or datetime.now(UTC), by_fa="Claude سرور هاب، به دستور مدیر کل",
    )  # fmt: skip


async def board_items(tx: Tx, hub: Any, company: str | None) -> list[FS.BoardItem]:
    out = []
    off = await FL.off_keys(tx)
    for key, flow in FL.FLOWS.items():
        if company and company != flow.company:
            continue
        if not flow.account:
            continue  # ⟨2026-11-15⟩ a test flow (it publishes nothing): not an automation of the board
        co = await _company(tx, flow)
        days = await _days(tx, flow, 1)
        last = await run_ref(tx, hub, days[0]) if days else None
        day = await day_run(tx, hub, last.ref, with_files=False) if last else None
        _, usd = await _today_cost(tx, flow)
        trig = next_trigger(flow)
        tomorrow = trig.astimezone(_tz()).date() + timedelta(days=0 if flow.same_day else 1)
        out.append(FS.BoardItem(
            ref=ref_of(key), kind="n8n", title_fa=flow.title_fa, company=flow.company,
            company_fa=co["name_fa"] or None, when_fa=when_fa(flow, tomorrow),
            state="off" if key in off else "on", switchable=True,
            last=FS.BoardLast(
                at=last.at, state=last.state, note_fa=last.note_fa,
                steps=[FS.BoardStep(key=s.key, state=s.state) for s in day.steps] if day else None,
            ) if last else None,
            next_at=None if key in off else trig, cost_today_usd=usd,
            opens=f"automation/{ref_of(key)}",
        ))  # fmt: skip
    return out


# ------------------------------------------------------------ a day's page --
async def day_run(tx: Tx, hub: Any, order: str, with_files: bool = True) -> store.LineRunOut | None:
    """`GET /line-runs/F-…` of a flow's day: each step's state, read by code. None: not a day.
    `with_files=False` (the board's strip): the states only, no file read from the storage."""
    if not ORDER_REF.fullmatch(order):
        return None
    d = await _day_by_order(tx, order)
    if d is None:
        return None
    flow = FL.FLOWS.get(str(d["flow"].get("key")))
    if flow is None:
        return None
    f = await _facts(tx, d)
    state, note = _state(d, f)
    co = await _company(tx, flow)
    files = (
        await store.step_files(
            tx, [str(x["id"]) for x in f["files"].values()], getattr(hub, "storage", None)
        )
        if with_files
        else {}
    )
    turns = f["turns"]
    first = turns[0]["started_at"] if turns else None
    last_end = max((t["finished_at"] for t in turns if t["finished_at"]), default=None)
    running = any(t["state"] in ("queued", "running") for t in turns)
    n_stories = len(flow.stories)
    pics = [next((f["files"][f"story_{i}{e}"] for e in FL.PICTURE_EXT
                  if f"story_{i}{e}" in f["files"]), None) for i in range(1, n_stories + 1)]  # fmt: skip
    have_video = ("video.mp4" in f["files"]) if not n_stories else all(pics)
    final_at = (f["files"]["video.mp4"]["created_at"] if not n_stories
                else max(x["created_at"] for x in pics if x)) if have_video else None  # fmt: skip
    stopped = state in ("failed", "cancelled") and not f["scheduled"]
    sent_at = f["meta"].get("sent")
    sent = datetime.fromisoformat(str(sent_at)) if sent_at else None
    sched_at = max((j["finished_at"] for j in f["scheduled"] if j["finished_at"]), default=None)
    out_at = max((j["finished_at"] for j in f["out"] if j["finished_at"]), default=None)
    rules_done = [j for j in f["rules"] if j["state"] == "done"]
    said_out = [x for x in f["said"] if "منتشر شد" in str(x["title_fa"])]

    def made(key: str) -> tuple[str, datetime | None, list[Any]]:
        names = FILE_OF.get(key)
        if names:
            got = [f["files"][n] for n in names if n in f["files"]]
            if got and len(got) >= (1 if key == "cover" else len(names)):
                shown = [files[str(g["id"])] for g in got if str(g["id"]) in files]
                return "done", max(g["created_at"] for g in got), shown
        elif key == "compose" and n_stories:
            if have_video:
                shown = [files[str(x["id"])] for x in pics if x and str(x["id"]) in files]
                return "done", final_at, shown
        elif have_video:
            return "done", final_at, []
        if stopped:
            return "failed", None, []
        return ("running" if running else "pending"), None, []

    steps = []
    for s in steps_of(flow):
        st: str = "pending"
        start: datetime | None = None
        end: datetime | None = None
        outs: list[store.StepFile] = []
        err: str | None = None
        if s.key in ("n8n", "order"):
            st, start, end = "done", d["created_at"], d["created_at"]
        elif s.key in WORKSHOP:
            st, end, outs = made(s.key)
            start = first if st != "pending" else None
            if st == "failed":
                err = note
        elif s.key == "package":
            if sent or f["scheduled"]:
                st, end = "done", sent or sched_at
            elif stopped:
                st, err = "failed", note
        elif s.key == "schedule":
            if f["scheduled"] or f["out"]:  # (once out, it is no longer in IG-Hub's queue)
                st, end = "done", sched_at or sent
            elif f["failed"]:
                st, err = "failed", "IG-Hub نپذیرفت"
        elif s.key == "publish":
            if f["out"]:
                st, end = "done", out_at
            elif f["scheduled"]:
                st = "waiting"
        elif s.key[0] == "s" and s.key[1:].isdigit():
            # ⟨2026-11-15⟩ one story at its own hour
            i = int(s.key[1:])
            mine = [j for j in f["jobs"] if j["kind"] == "story" and not j["rule"]
                    and str(j["file_name"] or "").startswith(f"story_{i}.")]  # fmt: skip
            if any(j in f["out"] for j in mine):
                st, end = "done", max(j["finished_at"] for j in mine if j in f["out"])
            elif any(j["state"] == "failed" for j in mine) and not any(
                j in f["scheduled"] for j in mine
            ):
                st, err = "failed", "IG-Hub نپذیرفت"
            elif mine:  # (on its way to IG-Hub, or held there for its hour)
                st = "waiting"
            elif sent:
                st = "skipped"  # (its hour had gone by when the day was ready)
        elif s.key == "rule":
            if rules_done:
                st, end = "done", max((j["finished_at"] for j in rules_done if j["finished_at"]),
                                      default=None)  # fmt: skip
            elif f["scheduled"] or f["out"]:
                st = "waiting"
        elif s.key == "replies":
            if f["out"] and (rules_done or not flow.story):
                st, end = "done", max((j["finished_at"] for j in rules_done if j["finished_at"]),
                                      default=out_at)  # fmt: skip
            elif f["scheduled"]:
                st = "waiting"
        elif s.key == "report":
            # (the owner may delete a notice: a reel that is out was told with its link)
            if said_out or f["out"]:
                st, end = "done", said_out[-1]["created_at"] if said_out else out_at
            elif f["said"] or f["scheduled"]:
                st = "waiting"
        steps.append(store.StepRun(
            key=s.key, kind=s.kind, title_fa=s.title_fa, state=st,
            attempt=1, started_at=start or (end if st == "done" else None), ended_at=end,
            output=store.StepOutputOut(text=s.output_fa or None), via=s.helper or "code",
            tokens=0, usd_equiv=Decimal(0), error_fa=err, gate=None, sealed_at=None,
            sealed_by=None, reused=False, missing=[], helper=s.helper, model=s.model,
            effort=s.effort, outputs=outs,
        ))  # fmt: skip
    ended = (
        out_at
        if state == "done"
        else (d["closed_at"] if state in ("failed", "cancelled") else None)
    )
    minutes = (
        round(((last_end or datetime.now(UTC)) - first).total_seconds() / 60, 1) if first else None
    )
    published = [
        store.Published(platform="instagram", kind=str(j["kind"]),
                        external_id=str((OR._j(j["result"]) or {}).get("external_id") or "") or None,
                        at=j["finished_at"], url=(OR._j(j["result"]) or {}).get("url"),
                        permalink=(OR._j(j["result"]) or {}).get("url"))
        for j in f["out"]
    ]  # fmt: skip
    return store.LineRunOut(
        ref=order, line="", company=flow.company, title_fa=flow.title_fa, platform="instagram",
        line_version=1, trigger="n8n", dry=False, state=state,
        at=d["created_at"], ended_at=ended, steps=steps,
        cost=store.LineCost(tokens=f["tokens"], usd_equiv=f["usd"], usd=float(round(f["usd"], 2))),
        published=published, metrics=store.Metrics(), note_fa=note, decision=None, rerun_of=None,
        from_step=None, automation=ref_of(flow.key), company_fa=co["name_fa"] or None,
        topic_fa=await _topic(tx, hub, d, f),
        results=FS.RunResults(permalink=f["reel_url"]) if f["reel_url"] else None,
        minutes=minutes, occurrence_at=_when(d),
    )  # fmt: skip
