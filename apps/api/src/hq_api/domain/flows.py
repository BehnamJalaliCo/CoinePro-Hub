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

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import order_report as OR
from hq_api.domain import session_publish as SPB
from hq_api.principal import Principal

log = logging.getLogger("hq_api.flows")

FLOW = Principal(kind="service", code="flow", role="service")
TEHRAN = "Asia/Tehran"
MONTHS_FA = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر",
             "دی", "بهمن", "اسفند")  # fmt: skip
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


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


FLOWS = {
    "prochart_reels": Flow(
        key="prochart_reels",
        company="PC",
        account="theprochart",
        title_fa="ریلز روزانه‌ی پروچارت",
        kit="/home/studio/kits/prochart-reels",
        start=date(2026, 11, 14),
        hours=("09:30", "14:00", "19:30", None),
    ),
}


def week_of(flow: Flow, day: date) -> int:
    """0, 1, 2, 3: the day's week in the four-week round (it starts again after the fourth)."""
    return max(0, (day - flow.start).days) // 7 % len(flow.hours)


def fa_day(day: date) -> str:
    from hq_api.worker.jalali import to_jalali

    _, jm, jd = to_jalali(day)
    return f"{jd} {MONTHS_FA[jm - 1]}".translate(FA_DIGITS)


async def slot_of(tx: Tx, flow: Flow, day: date, company_id: UUID) -> tuple[datetime, str]:
    """When the day's post goes out (UTC) and how it was chosen, in Persian. The fourth week takes
    the hour the account's posts did best at (§49); too little data yet: the first week's hour."""
    tz = ZoneInfo(TEHRAN)
    hm = flow.hours[week_of(flow, day)]
    why = "ساعت ثابت این هفته"
    if hm is None:
        from hq_api.domain import best_hour as BH

        got = await BH.best(tx, company_id, flow.account, TEHRAN)
        if got.enough and got.hour:
            hm, why = str(got.hour), "پربازدیدترین ساعت"
        else:
            hm, why = flow.hours[0] or "09:30", "داده‌ی بازدید هنوز کم است؛ ساعت هفته‌ی اول"
    hh, mm = (int(x) for x in str(hm).split(":"))
    at = datetime.combine(day, time(hh, mm), tz).astimezone(UTC)
    return at, why


def at_fa(at: datetime) -> str:
    local = at.astimezone(ZoneInfo(TEHRAN))
    return f"{fa_day(local.date())} ساعت {local:%H:%M}".translate(FA_DIGITS)


def brief_of(flow: Flow, day: date, at: datetime) -> str:
    """The order's text: what the day's session makes, from the kit, and when it goes out."""
    return (
        f"{flow.title_fa}، {fa_day(day)} (انتشار خودکار {at_fa(at)} به وقت تهران)\n\n"
        f"این فرمان را اتوماسیون روزانه (n8n) داده است، به دستور مدیر کل. کار خودکار است: از کسی "
        f"چیزی نپرس، order.ask نزن و منتظر تأیید نمان.\n"
        f"روند، قاعده‌ها و همه‌ی ابزارها در کیت ثابت است: {flow.kit}/README.md. اول همان را بخوان و "
        f"قدم‌به‌قدم انجام بده؛ چیز دیگری از کیت را جز به نیاز نخوان و هیچ فایلی از کیت را عوض نکن.\n"
        f"تحویل: فقط این‌ها در out/: video.mp4 (ریلز)، story.mp4 (همان ویدیو، حداکثر ۵۹٫۸ ثانیه)، "
        f"cover.jpg، caption.txt، comment.txt و topic.txt. وقتی همه در out/ بود، ستاد خودش ریلز و "
        f"استوری را برای {at_fa(at)} روی @{flow.account} زمان‌بندی میکند، کامنت هوشمند و جواب "
        f"استوری را روشن میکند، به مدیر کل خبر میدهد و این جلسه را میبندد."
    )


# --------------------------------------------------------------------- start --
async def start(
    ctx: Any, request: Any, background: Any, key: str, day: date | None
) -> dict[str, Any]:
    """The day's order (one per flow and day: the caller's `Idempotency-Key` makes a second call
    the first one's answer). Returns {order, work, publish_at, why_fa}."""
    from hq_api.domain import dispatch as D
    from hq_api.errors import ApiError
    from hq_api.routes.orders import OrderIn, place_order

    flow = FLOWS.get(key)
    if flow is None:
        raise ApiError(404, "not_found", f"no flow {key}")
    async with ctx.hub.db.tx(await ctx.hub.companies.ids()) as tx:
        co = await tx.first("SELECT id FROM core.companies WHERE code = :c", c=flow.company)
        if co is None:
            raise ApiError(409, "validation_failed", f"no company {flow.company}")
        tomorrow = datetime.now(ZoneInfo(TEHRAN)).date() + timedelta(days=1)
        the_day = day or tomorrow
        # one order per flow and day, whatever calls again (a key expires in 24 hours); a day
        # whose work failed or was cancelled may be made again
        made = await tx.first(
            """SELECT ref, run_meta -> 'flow' AS flow FROM work.work
               WHERE run_meta -> 'flow' ->> 'key' = :k AND run_meta -> 'flow' ->> 'day' = :d
                 AND status NOT IN ('failed', 'cancelled')
               ORDER BY created_at DESC LIMIT 1""",
            k=flow.key,
            d=the_day.isoformat(),
        )
        if made is not None:
            m = OR._j(made["flow"]) or {}
            return {"order": str(m.get("order") or ""), "work": str(made["ref"]),
                    "publish_at": str(m.get("publish_at") or ""), "why_fa": "پیش از این ساخته شده"}  # fmt: skip
        at, why = await slot_of(tx, flow, the_day, co["id"])
    body = OrderIn(
        text=brief_of(flow, the_day, at),
        company=flow.company,
        route=D.Route(
            companies=[flow.company],
            kind="work",
            budget_tokens=flow.budget_tokens,
            why_fa=f"اتوماسیون روزانه: {flow.title_fa}",
        ),
        pace="auto",
    )
    out = await place_order(ctx, request, background, body)
    # the first call's answer, or (the same key again) its stored replay
    got = out.model_dump() if hasattr(out, "model_dump") else json.loads(bytes(out.body))
    ref = str(got["ref"])
    work_ref = next((r.get("work_ref") for r in got.get("routes") or [] if r.get("work_ref")), None)
    meta = {"key": flow.key, "day": the_day.isoformat(), "publish_at": at.isoformat(),
            "account": flow.account, "story": flow.story, "order": ref}  # fmt: skip
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


def _json(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


# ------------------------------------------------------------ the day's cap --
# ⟨2026-11-13⟩ the F-0018 usage audit (P4): a day aims at about $6 and stops at $10 (the turns'
# own cost, as the hub books it since the audit: llm.calls.equiv_cost_usd). A work's token budget
# grows with every workshop turn, so it never held a direct session; this does.
FLOW_USD_CAP = Decimal("10")
CAPPED_TITLE_FA = "{title} به سقف هزینه‌ی روز رسید"
CAPPED_BODY_FA = (
    "هزینه‌ی ساخت امروز به {usd} دلار رسید و ادامه‌ی خودکار متوقف شد؛ بسته کامل نشده است. "
    "اگر بخواهی، همین روز را دوباره راه می‌اندازم."
)


async def spent_usd(tx: Tx, work_ref: str) -> Decimal:
    got = await tx.scalar(
        "SELECT COALESCE(SUM(equiv_cost_usd), 0) FROM llm.calls WHERE work_ref = :w", w=work_ref
    )
    return Decimal(str(got or 0))


async def over_cap(tx: Tx, work_id: UUID) -> bool:
    """A flow's day past its cap: no more turns by themselves; the owner hears it once."""
    w = await flow_of_work(tx, work_id)
    if w is None:
        return False
    usd = await spent_usd(tx, str(w["ref"]))
    if usd < FLOW_USD_CAP:
        return False
    meta = w["flow"]
    if not meta.get("capped"):
        meta["capped"] = f"{usd:.2f}"
        await tx.exec(
            "UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))"
            " WHERE id = :w",
            w=w["id"],
            m=_json(meta),
        )
        flow = FLOWS.get(str(meta.get("key")))
        from hq_api.domain import notify

        await notify.raise_notification(
            tx,
            company_id=w["company_id"],
            company_code=str(w["company"]),
            level="report",
            title_fa=CAPPED_TITLE_FA.format(title=flow.title_fa if flow else "انتشار روزانه")[:300],
            body_fa=CAPPED_BODY_FA.format(usd=f"{usd:.0f}".translate(FA_DIGITS)),
            link_kind="order",
            link_ref=str(meta.get("order") or w["ref"]),
            source_kind="system",
            source_code="flow",
        )
        await audit.record(
            tx, FLOW, company_id=w["company_id"], action="flow.capped", action_class="A1",
            target_kind="work", target_ref=str(w["ref"]),
            summary=f"{meta.get('key')} {meta.get('day')}: ${usd:.2f} >= ${FLOW_USD_CAP}",
        )  # fmt: skip
    return True


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


async def package(tx: Tx, w: dict[str, Any]) -> dict[str, Any] | None:
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
    for r in rows:
        d = dict(r)
        if (OR._j(d.get("produced_with")) or {}).get("unfinished"):
            continue
        for f in await SPB._files(tx, d):
            newest.setdefault(str(f["name"] or "").strip().lower(), (dict(f), d))
    files = [f for f, _ in newest.values()]
    reel, story = _split(files)
    caption = next((newest[n] for n in SPB.CAPTION_NAMES if n in newest), None)
    if reel is None or caption is None:
        return None
    covers = [f for f, _ in newest.values()
              if str(f["mime"]).startswith("image/") and str(f["name"] or "").lower().startswith("cover")]  # fmt: skip
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
        return "open"
    d, reel, story = pkg["d"], pkg["reel"], pkg["story"]
    route = await SPB._route(tx, w["company_id"])
    account = str(meta.get("account") or "")
    if not route["ready"] or account not in route["accounts"]:
        return "route"
    caption = (await SPB._text_of(tx, hub, pkg["caption_d"], SPB.CAPTION_NAMES) or "").strip()
    comment = await SPB.comment_of(tx, hub, pkg["comment_d"]) if pkg["comment_d"] else None
    topic_d = pkg["topic_d"]
    topic = (
        (await SPB._text_of(tx, hub, topic_d, ("topic.txt",)) or "").strip().splitlines()
        if topic_d
        else []
    )
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
        )  # fmt: skip
        sent.append((what, str(j["id"])))
    meta["sent"] = datetime.now(UTC).isoformat()
    await tx.exec(
        """UPDATE work.work SET run_meta = jsonb_set(run_meta, '{flow}', CAST(:m AS jsonb))
           WHERE id = :w""",
        w=w["id"],
        m=_json(meta),
    )
    flow = FLOWS.get(str(meta.get("key")))
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
    flow = FLOWS.get(str(meta.get("key")))
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
