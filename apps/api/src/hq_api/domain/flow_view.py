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


def steps_of(flow: FL.Flow) -> list[FS.FlowStep]:
    """What the flow does, in order (the kit's README for the workshop's part)."""
    hours = "، ".join(h or "پربازدیدترین ساعت" for h in flow.hours)
    at = flow.trigger_at.translate(FA_DIGITS)
    return [
        _step("n8n", "n8n روند را روشن میکند", "n8n", "code", inp=f"هر روز ساعت {at} تهران",
              out="درخواست امضاشده به هاب برای روز بعد"),
        _step("order", "سفارش روز در هاب", "order", "code",
              out="یک جلسه‌ی خودکار برای مدیرعامل شرکت؛ بی پرسش و بی انتظار",
              rules=(f"ساعت انتشار در دور چهار هفته‌ای: {hours}".translate(FA_DIGITS),
                     "سقف هزینه‌ی هر روز ۱۰ دلار؛ بیشتر شد، کار میایستد و خبر میرسد")),
        _step("topic", "موضوع روز از بانک موضوع‌ها", "workshop", "workshop", out="topic.txt",
              model=OPUS),
        _step("script", "سناریو", "workshop", "gpt", out="متن گوینده",
              rules=("اگر ChatGPT جواب نداد، Claude خودش مینویسد",)),
        _step("voice", "صدای گوینده", "workshop", "gemini", out="فایل صدا"),
        _step("voice_check", "بازبینی صدا و زمان هر کلمه", "workshop", "code"),
        _step("direction", "کارگردانی و تدوین روی کاغذ", "workshop", "workshop", model=OPUS),
        _step("render", "ساخت ویدیو، یک بار رندر", "workshop", "workshop", out="video.mp4",
              model=OPUS),
        _step("story", "برش استوری", "workshop", "code", out="story.mp4 (حداکثر ۵۹٫۸ ثانیه)"),
        _step("cover", "کاور با المان همان روز", "workshop", "workshop", out="cover.jpg",
              model=OPUS),
        _step("texts", "کپشن و متن کامنت", "workshop", "workshop",
              out="caption.txt، comment.txt", model=OPUS),
        _step("package", "بسته‌ی کامل", "package", "code",
              rules=("تا هر شش فایل نرسیده، چیزی منتشر نمیشود",)),
        _step("schedule", "زمان‌بندی روی IG-Hub", "publish", "ighub",
              out=f"ریلز و استوری @{flow.account}" if flow.story else f"ریلز @{flow.account}"),
        _step("publish", "انتشار در ساعت خودش", "publish", "ighub"),
        _step("replies", "کامنت هوشمند و جواب استوری", "publish", "ighub"),
        _step("report", "خبر به مدیر کل", "report", "code",
              out="«آماده شد» و «منتشر شد» با لینک"),
    ]  # fmt: skip


WORKSHOP = ("topic", "script", "voice", "voice_check", "direction", "render", "story", "cover",
            "texts")  # fmt: skip
FILE_OF = {"topic": ("topic.txt",), "render": ("video.mp4",), "story": ("story.mp4",),
           "cover": ("cover.jpg", "cover.png"), "texts": ("caption.txt", "comment.txt")}  # fmt: skip


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
                  OR args ? 'rule_for' AS rule, state, finished_at, result
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
    scheduled = [j for j in jobs if not j["rule"] and j["state"] == "done"
                 and str((OR._j(j["result"]) or {}).get("external_id") or "").startswith("pub:")]  # fmt: skip
    out = [j for j in jobs if not j["rule"] and j["state"] == "done"
           and not str((OR._j(j["result"]) or {}).get("external_id") or "pub:").startswith("pub:")]  # fmt: skip
    failed = [j for j in jobs if j["state"] == "failed"]
    rules = [j for j in jobs if j["rule"]]
    reel_url = next((str((OR._j(j["result"]) or {}).get("url") or "") or None
                     for j in out if j["kind"] == "reel"), None)  # fmt: skip
    return {"meta": meta, "turns": [dict(t) for t in turns], "files": newest,
            "scheduled": scheduled, "out": out, "failed": failed, "rules": rules,
            "said": [dict(x) for x in said], "usd": usd, "tokens": int(tokens or 0),
            "reel_url": reel_url}  # fmt: skip


def _state(d: dict[str, Any], f: dict[str, Any]) -> tuple[str, str]:
    """The day as a run: queued · running · waiting · done · failed · cancelled, and one line."""
    meta = f["meta"]
    running = any(t["state"] in ("queued", "running") for t in f["turns"])
    if f["reel_url"]:
        return "done", "منتشر شد"
    if f["failed"] and not f["scheduled"]:
        return "failed", "انتشار روی IG-Hub نشد"
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
    hm = flow.hours[FL.week_of(flow, day)] if day else None
    publish = f"، انتشار فردا {hm}" if hm else "، انتشار فردا"
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
        day = (trig.astimezone(_tz()) + timedelta(days=i)).date() + timedelta(days=1)
        if co["id"] is not None:
            at, _ = await FL.slot_of(tx, flow, day, co["id"])
            upcoming.append(FS.FlowOccurrence(at=at))
    tick = await tx.scalar("SELECT last_tick_at FROM growth.flow_clock LIMIT 1")
    made = await tx.scalar(
        "SELECT min(created_at) FROM work.work WHERE run_meta -> 'flow' ->> 'key' = :k", k=flow.key
    )
    tomorrow = (trig.astimezone(_tz())).date() + timedelta(days=1)
    return FS.FlowAutomation(
        ref=ref, kind="flow", company=flow.company, company_fa=co["name_fa"] or "",
        playbook=None, version=None, line=None, title_fa=flow.title_fa,
        state="off" if off else "on",
        schedule=FS.FlowSchedule(mode="fixed", at=flow.trigger_at, when_fa=when_fa(flow, tomorrow)),
        account=flow.account, story=flow.story, mode="auto",
        budget=FS.FlowBudget(per_run_usd=float(FL.FLOW_USD_CAP), per_day_usd=float(FL.FLOW_USD_CAP),
                             spent_today_usd=usd),
        steps=steps_of(flow), next=upcoming[0] if upcoming and not off else None,
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
        co = await _company(tx, flow)
        days = await _days(tx, flow, 1)
        last = await run_ref(tx, hub, days[0]) if days else None
        _, usd = await _today_cost(tx, flow)
        trig = next_trigger(flow)
        tomorrow = trig.astimezone(_tz()).date() + timedelta(days=1)
        out.append(FS.BoardItem(
            ref=ref_of(key), kind="n8n", title_fa=flow.title_fa, company=flow.company,
            company_fa=co["name_fa"] or None, when_fa=when_fa(flow, tomorrow),
            state="off" if key in off else "on", switchable=True,
            last=FS.BoardLast(at=last.at, state=last.state, note_fa=last.note_fa) if last else None,
            next_at=None if key in off else trig, cost_today_usd=usd,
            opens=f"automation/{ref_of(key)}",
        ))  # fmt: skip
    return out


# ------------------------------------------------------------ a day's page --
async def day_run(tx: Tx, hub: Any, order: str) -> store.LineRunOut | None:
    """`GET /line-runs/F-…` of a flow's day: each step's state, read by code. None: not a day."""
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
    files = await store.step_files(
        tx, [str(x["id"]) for x in f["files"].values()], getattr(hub, "storage", None)
    )
    turns = f["turns"]
    first = turns[0]["started_at"] if turns else None
    last_end = max((t["finished_at"] for t in turns if t["finished_at"]), default=None)
    running = any(t["state"] in ("queued", "running") for t in turns)
    have_video = "video.mp4" in f["files"]
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
        elif have_video:
            return "done", f["files"]["video.mp4"]["created_at"], []
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
            if f["scheduled"]:
                st, end = "done", sched_at
            elif f["failed"]:
                st, err = "failed", "IG-Hub نپذیرفت"
        elif s.key == "publish":
            if f["out"]:
                st, end = "done", out_at
            elif f["scheduled"]:
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
