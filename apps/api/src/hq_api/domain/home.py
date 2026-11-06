"""The owner's home (contract §29.13 ⟨1.11⟩): three cards and a summary.

    effective  the highest impact suggestion across every company
    good       the best impact per cost of the rest (a small, cheap move)
    progress   one real move, before and after, from a connection's figures
    morning    at most 5 rule-based lines (08:00 the owner's time, stored;
               computed when missing): yesterday's outputs, the best KPI
               move, what waits for the owner
    groups     each working group's main KPI series per member company
    orders     the owner's latest orders, briefly, in plain Persian
    critical   the owner's urgent notifications only; nothing else technical

Suggestions come from the groups (a closed experiment that beat its
target; the content lead's `group.plan`), the advisor's weekly growth memo
(its numbered moves, read by rule) and the council's plans. A suggestion
the owner said «نه» to is never shown again (its key is kept with the
reason, and the secretary's memory is told). Every text passes humanize
first and `humanize.check` must be clean, or it is not shown at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import groups as GR
from hq_api.domain import humanize as H
from hq_api.domain.connections import LABEL_FA, PUBLISHING, owner_today
from hq_api.routes.notifications import Notification, to_notification

log = logging.getLogger("hq_api.home")

LATER = timedelta(days=3)
MEMO_DAYS = 8
COUNCIL_DAYS = 7
EXPERIMENT_DAYS = 14
GROUP_DAYS = 14
ORDERS_SHOWN = 5
CRITICAL_SHOWN = 5
# A KPI that is better when it falls; the others are better when they rise.
LOWER_IS_BETTER = {"position", "lcp_ms", "cls", "cost_per_post"}
# Figures that add up across a kind's subjects (channels, accounts); the
# others are averaged (a rank, a rate, a score).
ADDITIVE = {"followers", "views", "reach", "impressions", "clicks", "sessions", "users",
            "conversions", "likes", "comments", "saves", "shares", "videos", "posts",
            "profile_views", "published"}  # fmt: skip
KEY_FA = {
    "followers": "دنبال‌کننده",
    "views": "بازدید",
    "reach": "دسترسی",
    "impressions": "نمایش در گوگل",
    "clicks": "کلیک از گوگل",
    "ctr": "نرخ کلیک در گوگل",
    "position": "رتبه‌ی میانگین در گوگل",
    "sessions": "بازدید سایت",
    "users": "کاربر سایت",
    "conversions": "تبدیل در سایت",
    "performance": "امتیاز سرعت سایت",
    "lcp_ms": "زمان نمایش صفحه",
    "cls": "جابه‌جایی صفحه",
    "likes": "پسند",
    "comments": "نظر",
    "saves": "ذخیره",
    "shares": "اشتراک",
    "videos": "ویدیو",
}
KIND_FA = {
    "search_console": "گوگل",
    "ga4": "سایت",
    "instagram": "اینستاگرام",
    "telegram": "تلگرام",
    "youtube": "یوتیوب",
    "pagespeed": "سایت",
}
NUMBERED = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?([0-9۰-۹]{1,2})[.)\-–:]\s*(.+)$")


# ------------------------------------------------------------------ shapes --
class Suggestion(BaseModel):
    id: UUID
    kind: Literal["effective", "good"]
    company: str
    title_fa: str
    why_fa: str
    impact_fa: str
    cost_fa: str
    source: Literal["council", "group", "advisor"]
    state: Literal["new", "run", "later", "no"]
    reason_fa: str | None
    order_ref: str | None
    created_at: datetime
    name_fa: str | None = None  # ⟨additive⟩ the company's name


class Point(BaseModel):
    value: float
    at: date


class Progress(BaseModel):
    id: UUID
    company: str
    title_fa: str
    before: Point
    after: Point
    kpi: str
    source: str
    work_ref: str | None
    name_fa: str | None = None  # ⟨additive⟩


class SeriesPoint(BaseModel):
    day: date
    value: float


class HomeKpi(BaseModel):
    key: str
    title_fa: str
    unit: str
    series: list[SeriesPoint]
    source: str | None = None  # ⟨additive⟩


class HomeCompany(BaseModel):
    code: str
    name_fa: str
    kpi: HomeKpi | None


class HomeGroup(BaseModel):
    key: str
    title_fa: str
    companies: list[HomeCompany]


class HomeOrder(BaseModel):
    ref: str
    text_fa: str
    state: str
    summary_fa: str


class Cards(BaseModel):
    effective: Suggestion | None
    good: Suggestion | None
    progress: Progress | None


class Home(BaseModel):
    cards: Cards
    morning: list[str]
    groups: list[HomeGroup]
    orders: list[HomeOrder]
    critical: list[Notification]


# ---------------------------------------------------------------- plain text --
def clean(text: str | None, limit: int) -> str:
    """The owner's plain Persian: humanized, one line per paragraph, cut."""
    out = H.humanize(re.sub(r"[*_`#>]+", " ", text or ""))
    return out[:limit].strip()


def shown(*texts: str) -> bool:
    """Every text of a card is clean (§29.7) or the card is not shown."""
    return all(not H.check(t) for t in texts if t)


def norm_title(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.translate(H._ARABIC))).strip().lower()


def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------- suggestions --
SUGGESTION_SQL = """
    SELECT s.*, c.code AS company, c.name_fa FROM owner.suggestions s
    JOIN core.companies c ON c.id = s.company_id
"""


def render_suggestion(r: dict[str, Any], slot: str | None = None) -> Suggestion:
    return Suggestion(
        id=r["id"],
        kind=slot or r["kind"],
        company=r["company"],
        name_fa=r.get("name_fa"),
        title_fa=r["title_fa"],
        why_fa=r["why_fa"],
        impact_fa=r["impact_fa"],
        cost_fa=r["cost_fa"],
        source=r["source"],
        state=r["state"],
        reason_fa=r["reason_fa"],
        order_ref=r["order_ref"],
        created_at=r["created_at"],
    )


async def add_suggestion(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    title_fa: str,
    why_fa: str,
    impact_fa: str,
    cost_fa: str,
    impact: int,
    cost: int,
    source: str,
    key: str,
    source_ref: str | None = None,
) -> dict[str, Any] | None:
    """A suggestion for the home, once per key. Never one whose text is not
    clean after humanize, and never one the owner already said «نه» to
    (its key, or the same title for the same company)."""
    title, why = clean(title_fa, 300), clean(why_fa, 1000)
    impact_t, cost_t = clean(impact_fa, 300), clean(cost_fa, 300)
    if not title or not shown(title, why, impact_t, cost_t):
        return None
    refused = await tx.all(
        "SELECT title_fa FROM owner.suggestions WHERE company_id = :co AND state = 'no'",
        co=company_id,
    )
    if norm_title(title) in {norm_title(r["title_fa"]) for r in refused}:
        return None
    impact, cost = max(1, min(5, int(impact))), max(1, min(5, int(cost)))
    kind = "effective" if impact >= 4 or (impact >= 3 and cost >= 3) else "good"
    sid = await tx.scalar(
        """INSERT INTO owner.suggestions (company_id, kind, title_fa, why_fa, impact_fa, cost_fa,
               impact, cost, source, source_ref, key)
           VALUES (:co, :kind, :t, :w, :i, :c, :ni, :nc, :src, :ref, :key)
           ON CONFLICT (key) DO NOTHING RETURNING id""",
        co=company_id,
        kind=kind,
        t=title,
        w=why,
        i=impact_t,
        c=cost_t,
        ni=impact,
        nc=cost,
        src=source,
        ref=(source_ref or "")[:200] or None,
        key=key[:300],
    )
    if sid is None:
        return None
    await events.emit(tx, company_code, "suggestion.updated", str(sid), {"state": "new"})
    return await tx.one(SUGGESTION_SQL + " WHERE s.id = :id", id=sid)


def memo_moves(body: str) -> list[tuple[str, str]]:
    """The numbered moves of an advisor's growth memo: (first line, the
    lines under it), read by rule; at most three."""
    moves: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        m = NUMBERED.match(line)
        if m:
            moves.append((m.group(2).strip(), []))
        elif moves and line.strip():
            moves[-1][1].append(line.strip())
    return [(t, " ".join(rest)) for t, rest in moves[:3]]


async def _from_experiments(tx: Tx, now: datetime) -> int:
    rows = await tx.all(
        """SELECT x.id, x.company_id, x.hypothesis_fa, x.target, x.result, c.code AS company,
                  c.name_fa
           FROM growth.experiments x JOIN core.companies c ON c.id = x.company_id
           WHERE x.closed_at > :since AND x.result IS NOT NULL AND x.result >= x.target
             AND x.kept IS NOT FALSE AND c.status = 'active'""",
        since=now - timedelta(days=EXPERIMENT_DAYS),
    )
    made = 0
    for r in rows:
        name = r["name_fa"] or r["company"]
        got = await add_suggestion(
            tx,
            company_id=r["company_id"],
            company_code=r["company"],
            title_fa=f"ادامه‌ی آزمایش موفق {name}: {r['hypothesis_fa'][:120]}",
            why_fa=(f"عدد هدف {fmt(float(r['target']))} بود و نتیجه {fmt(float(r['result']))} شد."),
            impact_fa="همین رشد هر هفته تکرار میشود.",
            cost_fa="تقریباً بی هزینه‌ی تازه؛ همان کار هر روز گروه است.",
            impact=3,
            cost=1,
            source="group",
            key=f"experiment:{r['id']}",
        )
        made += got is not None
    return made


async def _from_memos(tx: Tx, now: datetime) -> int:
    memos = await tx.all(
        """SELECT m.ref, m.body, m.created_at FROM msg.messages m
           JOIN msg.threads t ON t.id = m.thread_id
           WHERE t.kind = 'advisor' AND m.author_kind = 'agent' AND m.created_at > :since
             AND m.body LIKE '%یادداشت رشد%'
           ORDER BY m.created_at DESC LIMIT 50""",
        since=now - timedelta(days=MEMO_DAYS),
    )
    if not memos:
        return 0
    companies = await tx.all(
        "SELECT id, code, name_fa FROM core.companies WHERE kind = 'company' AND status = 'active'"
    )
    made = 0
    for m in memos:
        head = m["body"].split("\n", 1)[0]
        co = next(
            (
                c
                for c in companies
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(c['code'])}(?![A-Za-z0-9])", head)
                or (c["name_fa"] and c["name_fa"] in head)
            ),
            None,
        )
        if co is None:
            continue
        for i, (title, why) in enumerate(memo_moves(m["body"])):
            got = await add_suggestion(
                tx,
                company_id=co["id"],
                company_code=co["code"],
                title_fa=title,
                why_fa=why or "از یادداشت رشد هفتگی مشاور.",
                impact_fa="از یادداشت رشد هفتگی مشاور؛ اثرش در یادداشت آمده است.",
                cost_fa="یک فرمان به مدیرعامل همان شرکت.",
                impact=4 - min(i, 2),
                cost=2,
                source="advisor",
                key=f"advisor:{m['ref']}:{i + 1}",
                source_ref=m["ref"],
            )
            made += got is not None
    return made


async def _has_column(tx: Tx, schema: str, table: str, column: str) -> bool:
    return bool(
        await tx.scalar(
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema = :s AND table_name = :t AND column_name = :c""",
            s=schema,
            t=table,
            c=column,
        )
    )


async def _from_councils(tx: Tx, now: datetime) -> int:
    plan = "k.plan_md" if await _has_column(tx, "work", "councils", "plan_md") else "NULL"
    rows = await tx.all(
        f"""SELECT k.id, k.company_id, c.code AS company, c.kind AS company_kind,
                   {plan} AS plan_md, d.title AS title, w.title AS work_title
            FROM work.councils k JOIN core.companies c ON c.id = k.company_id
            JOIN work.work w ON w.id = k.work_id
            LEFT JOIN cartable.deliverables d ON d.ref = k.synthesis_ref
            WHERE k.state = 'done' AND k.updated_at > :since""",  # noqa: S608 - a column name
        since=now - timedelta(days=COUNCIL_DAYS),
    )
    made = 0
    for r in rows:
        if r["company_kind"] != "company":
            continue
        title = r["title"] or r["work_title"]
        why = (r["plan_md"] or "").strip().splitlines()
        got = await add_suggestion(
            tx,
            company_id=r["company_id"],
            company_code=r["company"],
            title_fa=f"اجرای برنامه‌ی شورا: {title}",
            why_fa=" ".join(why[:3]) or "برنامه‌ی نهایی شورای مدل‌ها آماده است.",
            impact_fa="برنامه‌ی شورا با گام‌ها و زمان‌بندی‌اش.",
            cost_fa="چند کار برای همان شرکت؛ هزینه در برنامه آمده است.",
            impact=3,
            cost=3,
            source="council",
            key=f"council:{r['id']}",
        )
        made += got is not None
    return made


async def generate(tx: Tx, now: datetime | None = None) -> int:
    """The rule-based generator (the morning tick, and GET /home when the day
    has none yet). The content lead's suggestions come by group.plan."""
    now = now or datetime.now(UTC)
    made = 0
    for fn in (_from_experiments, _from_memos, _from_councils):
        try:
            async with tx.conn.begin_nested():
                made += await fn(tx, now)
        except Exception:
            log.warning("suggestion source failed", extra={"source": fn.__name__}, exc_info=True)
    return made


async def choose(
    tx: Tx, now: datetime | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(effective, good) across every company: the highest impact, then the
    best impact per cost of the rest. Never a «نه»; a «بعداً» after its time."""
    now = now or datetime.now(UTC)
    rows = await tx.all(
        SUGGESTION_SQL
        + """ WHERE c.status = 'active'
              AND (s.state = 'new' OR (s.state = 'later' AND s.later_until <= :now))
            ORDER BY s.created_at DESC LIMIT 200""",
        now=now,
    )
    rows = [r for r in rows if shown(r["title_fa"], r["why_fa"], r["impact_fa"], r["cost_fa"])]
    if not rows:
        return None, None
    effective = max(rows, key=lambda r: (r["impact"], r["impact"] / r["cost"], r["created_at"]))
    rest = [r for r in rows if r["id"] != effective["id"]]
    good = (
        max(rest, key=lambda r: (r["impact"] / r["cost"], -r["cost"], r["created_at"]))
        if rest
        else None
    )
    return effective, good


async def remember_no(tx: Tx, s: dict[str, Any], reason_fa: str | None) -> None:
    """The secretary's memory (§29.4, dispatch.remember kind `no`): read first
    by every preview; the reason is kept on the suggestion either way."""
    from hq_api.domain import dispatch

    try:
        async with tx.conn.begin_nested():
            await dispatch.remember(
                tx,
                "no",
                reason_fa or s["title_fa"],
                {"suggestion": str(s["id"]), "company": s["company"], "title_fa": s["title_fa"],
                 "reason_fa": reason_fa},
            )  # fmt: skip
    except Exception:  # noqa: BLE001 - the suggestion keeps its own reason
        log.warning("dispatch memory refused a no")


def order_text(s: dict[str, Any]) -> str:
    """What the order of a suggestion says (rules route it: the company's
    name first; no question mark, so it is work, not a question)."""
    name = s.get("name_fa") or s["company"]
    body = f"{name}: {s['title_fa']}. اثر مورد انتظار: {s['impact_fa']}"
    return re.sub(r"[؟?]", ".", body)[:1000]


# ------------------------------------------------------------------ progress --
def better(key: str, before: float, after: float) -> float:
    """The relative improvement (0 when it got worse or did not move)."""
    if before == 0:
        return 0.0 if after <= 0 or key in LOWER_IS_BETTER else 1.0
    change = (after - before) / abs(before)
    return max(0.0, -change if key in LOWER_IS_BETTER else change)


async def _daily_totals(tx: Tx, since: date, until: date) -> list[dict[str, Any]]:
    """Each company's figure per (kind, key, day), the subjects added up (or
    averaged for a rank, a rate or a score). Connections only, never `hub`."""
    return await tx.all(
        """SELECT m.company_id, c.code AS company, c.name_fa, m.kind, m.key, m.day,
                  CASE WHEN m.key = ANY(:additive) THEN sum(m.value) ELSE avg(m.value) END AS value,
                  min(m.source) AS source
           FROM growth.metrics_daily m JOIN core.companies c ON c.id = m.company_id
           WHERE m.kind <> 'hub' AND m.day BETWEEN :since AND :until AND c.status = 'active'
           GROUP BY m.company_id, c.code, c.name_fa, m.kind, m.key, m.day""",
        additive=sorted(ADDITIVE),
        since=since,
        until=until,
    )


def _moves(
    totals: list[dict[str, Any]], after_from: date, before_lo: date, before_hi: date
) -> list[dict[str, Any]]:
    """For each series: its latest point on or after `after_from`, and the
    point closest to a week before it within [before_lo, before_hi]."""
    series: dict[tuple[Any, str, str], list[dict[str, Any]]] = {}
    for r in totals:
        series.setdefault((r["company_id"], r["kind"], r["key"]), []).append(r)
    out: list[dict[str, Any]] = []
    for (_, kind, key), pts in series.items():
        pts.sort(key=lambda r: r["day"])
        after = pts[-1]
        if after["day"] < after_from:
            continue
        olds = [p for p in pts if before_lo <= p["day"] <= before_hi and p["day"] < after["day"]]
        if not olds:
            continue
        before = olds[0]
        b, a = float(before["value"]), float(after["value"])
        gain = better(key, b, a)
        if gain <= 0:
            continue
        out.append({"kind": kind, "key": key, "before": before, "after": after, "gain": gain})
    out.sort(key=lambda m: m["gain"], reverse=True)
    return out


def move_title(m: dict[str, Any]) -> str:
    name = m["after"]["name_fa"] or m["after"]["company"]
    what = KEY_FA.get(m["key"], m["key"])
    where = KIND_FA.get(m["kind"], LABEL_FA.get(m["kind"], ""))
    b, a = float(m["before"]["value"]), float(m["after"]["value"])
    return f"{what} {where} {name} از {fmt(round(b, 2))} به {fmt(round(a, 2))} رسید"


async def generate_progress(tx: Tx, today: date) -> int:
    """Real moves of the last week, before and after, from the connections'
    own figures only; each move once (its key)."""
    totals = await _daily_totals(tx, today - timedelta(days=14), today)
    made = 0
    for m in _moves(totals, today - timedelta(days=3), today - timedelta(days=12),
                    today - timedelta(days=5))[:10]:  # fmt: skip
        title = clean(move_title(m), 300)
        if not shown(title):
            continue
        a, b = m["after"], m["before"]
        key = f"progress:{a['company']}:{m['kind']}:{m['key']}:{a['day'].isoformat()}"
        sid = await tx.scalar(
            """INSERT INTO owner.progress (company_id, title_fa, kpi, kind, before_value, before_at,
                   after_value, after_at, source, key)
               VALUES (:co, :t, :kpi, :kind, :bv, :ba, :av, :aa, :src, :key)
               ON CONFLICT (key) DO NOTHING RETURNING id""",
            co=a["company_id"],
            t=title,
            kpi=m["key"],
            kind=m["kind"],
            bv=float(b["value"]),
            ba=b["day"],
            av=float(a["value"]),
            aa=a["day"],
            src=m["kind"],
            key=key,
        )
        made += sid is not None
    return made


PROGRESS_SQL = """
    SELECT p.*, c.code AS company, c.name_fa FROM owner.progress p
    JOIN core.companies c ON c.id = p.company_id
"""


def render_progress(r: dict[str, Any]) -> Progress:
    return Progress(
        id=r["id"],
        company=r["company"],
        name_fa=r.get("name_fa"),
        title_fa=r["title_fa"],
        before=Point(value=float(r["before_value"]), at=r["before_at"]),
        after=Point(value=float(r["after_value"]), at=r["after_at"]),
        kpi=r["kpi"],
        source=r["source"],
        work_ref=r["work_ref"],
    )


async def best_progress(tx: Tx, today: date) -> dict[str, Any] | None:
    """The best real move of the last week (by its relative gain)."""
    rows = await tx.all(
        PROGRESS_SQL + " WHERE p.after_at > :since ORDER BY p.created_at DESC LIMIT 50",
        since=today - timedelta(days=7),
    )
    rows = [r for r in rows if shown(r["title_fa"])]
    if not rows:
        return None
    return max(
        rows,
        key=lambda r: (
            better(r["kpi"], float(r["before_value"]), float(r["after_value"])),
            r["after_at"],
        ),
    )


# ------------------------------------------------------------------ morning --
async def morning_lines(tx: Tx, tz: str, today: date) -> list[str]:
    """At most five plain Persian lines, by rule."""
    yesterday = today - timedelta(days=1)
    lines: list[str] = []
    outputs = int(
        await tx.scalar(
            """SELECT count(*) FROM cartable.deliverables d JOIN core.companies c ON c.id = d.company_id
               WHERE c.kind = 'company' AND (d.created_at AT TIME ZONE :tz)::date = :day""",
            tz=tz,
            day=yesterday,
        )
        or 0
    )
    published = int(
        await tx.scalar(
            """SELECT COALESCE(sum(value), 0) FROM growth.metrics_daily
               WHERE kind = 'hub' AND key = 'published' AND day = :day""",
            day=yesterday,
        )
        or 0
    )
    if outputs or published:
        lines.append(f"دیروز {outputs} خروجی تحویل شد و {published} پست منتشر شد.")
    else:
        lines.append("دیروز خروجی تازه‌ای تحویل نشد و پستی منتشر نشد.")
    totals = await _daily_totals(tx, yesterday - timedelta(days=2), yesterday)
    moves = _moves(totals, yesterday, yesterday - timedelta(days=2), yesterday - timedelta(days=1))
    if moves:
        lines.append(f"بهترین حرکت دیروز: {move_title(moves[0])}.")
    decisions = int(
        await tx.scalar(
            """SELECT count(*) FROM cartable.decisions
               WHERE status = 'pending' AND approver_kind IS NULL AND owner_visible"""
        )
        or 0
    )
    suggestions = int(
        await tx.scalar("SELECT count(*) FROM owner.suggestions WHERE state = 'new'") or 0
    )
    if decisions or suggestions:
        lines.append(f"منتظر شما: {decisions} تصمیم و {suggestions} پیشنهاد.")
    unlinked = await tx.all(
        """SELECT k.kind, c.name_fa, c.code FROM growth.connections k
           JOIN core.companies c ON c.id = k.company_id
           WHERE c.status = 'active' AND k.kind = ANY(:pub) AND k.state <> 'connected'
           ORDER BY c.code, k.kind LIMIT 4""",
        pub=list(PUBLISHING),
    )
    if unlinked:
        names = [f"{KIND_FA.get(r['kind'], '')} {r['name_fa'] or r['code']}" for r in unlinked[:3]]
        more = " و بیشتر" if len(unlinked) > 3 else ""
        lines.append("هنوز وصل نیست: " + "، ".join(names) + more + ".")
    open_orders = int(
        await tx.scalar(
            """SELECT count(*) FROM owner.orders o
               WHERE o.created_at > now() - interval '14 days'
                 AND EXISTS (SELECT 1 FROM jsonb_array_elements(o.routes) r
                             JOIN work.work w ON w.ref = r ->> 'work_ref'
                             WHERE w.status IN ('queued', 'in_progress', 'waiting'))"""
        )
        or 0
    )
    if open_orders:
        lines.append(f"فرمان‌های در جریان شما: {open_orders}.")
    base = [x for x in (clean(line, 300) for line in lines) if x and shown(x)][:5]
    # ⟨1.15⟩ §33.1 (2026-11-06): of the usage, only a company over its money budget,
    # one plain line in dollars, inside the 5
    from hq_api.domain import usage

    spent = [
        x for x in (clean(line, 300) for line in await usage.morning_lines(tx, tz, today)) if x
    ]
    spent = [x for x in spent if shown(x)][: usage.MORNING_LINES]
    return base[: 5 - len(spent)] + spent


async def store_morning(tx: Tx, holding_id: UUID, day: date, lines: list[str]) -> None:
    await tx.exec(
        """INSERT INTO growth.home_mornings (company_id, day, lines) VALUES (:co, :d, CAST(:l AS jsonb))
           ON CONFLICT (day) DO UPDATE SET lines = EXCLUDED.lines, at = now()""",
        co=holding_id,
        d=day,
        l=json.dumps(lines[:5], ensure_ascii=False),
    )


async def morning_tick(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """08:00 the owner's time: suggestions, progress and the 5 lines, by rule
    (no model, no outside call: the launch gate is not needed)."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
        today = owner_today(tz, now)
        made = await generate(tx, now)
        progress = await generate_progress(tx, today)
        lines = await morning_lines(tx, tz, today)
        await store_morning(tx, holding.id, today, lines)
        await events.emit(tx, holding.code, "home.updated", None, {"morning": len(lines)})
    return {"suggestions": made, "progress": progress, "morning": len(lines)}


# --------------------------------------------------------------------- home --
ORDER_STATE_FA = {
    "received": "دریافت شد",
    "in_progress": "در جریان",
    "waiting": "منتظر",
    "delivered": "تحویل شد",
    "failed": "ناموفق",
    "cancelled": "لغو شد",
}


async def order_state(tx: Tx, o: dict[str, Any]) -> str:
    """The order's state from its work items (prompt 21 part 1's order
    report names it too; this is the brief form)."""
    if o.get("state"):
        return str(o["state"])
    refs = [r.get("work_ref") for r in o.get("routes") or [] if r.get("work_ref")]
    if not refs:
        return "received"
    sts = [
        r["status"]
        for r in await tx.all("SELECT status FROM work.work WHERE ref = ANY(:refs)", refs=refs)
    ]
    if any(s == "in_progress" for s in sts):
        return "in_progress"
    if any(s in ("queued", "waiting") for s in sts):
        return "waiting" if all(s == "waiting" for s in sts) else "in_progress"
    if sts and all(s in ("done", "delivered") for s in sts):
        return "delivered"
    if any(s == "failed" for s in sts):
        return "failed"
    return "cancelled" if sts else "received"


async def orders(tx: Tx) -> list[HomeOrder]:
    state_col = (
        "o.state" if await _has_column(tx, "owner", "orders", "state") else "NULL::text AS state"
    )
    rows = await tx.all(
        f"""SELECT o.ref, o.text, o.summary_fa, o.routes, {state_col}
            FROM owner.orders o ORDER BY o.created_at DESC LIMIT :n""",  # noqa: S608 - a column
        n=ORDERS_SHOWN,
    )
    out = []
    for o in rows:
        st = await order_state(tx, o)
        text = clean(" ".join(str(o["text"] or "").split())[:160], 160)
        summary = clean(o["summary_fa"], 300)
        if not shown(text):
            text = ORDER_STATE_FA.get(st, "فرمان شما")
        if not shown(summary):
            summary = ORDER_STATE_FA.get(st, "")
        out.append(HomeOrder(ref=o["ref"], text_fa=text, state=st, summary_fa=summary))
    return out


async def critical(tx: Tx) -> list[Notification]:
    """Only the owner's urgent notifications (§29.1: nothing else technical
    on the home). When prompt 21 part 1's routing columns exist, only the
    rows it made owner-visible."""
    from hq_api.domain.notify import COLUMNS

    visible = await _has_column(tx, "notify", "notifications", "owner_visible")
    rows = await tx.all(
        f"""SELECT {COLUMNS} FROM notify.notifications n JOIN core.companies c ON c.id = n.company_id
            WHERE n.level = 'urgent' AND n.delivered_in_app AND n.read_at IS NULL
              AND n.created_at > now() - interval '7 days'
              {"AND n.owner_visible" if visible else ""}
            ORDER BY n.created_at DESC LIMIT :n""",  # noqa: S608 - module constants
        n=CRITICAL_SHOWN,
    )
    return [to_notification(r) for r in rows]


async def group_kpis(tx: Tx, today: date, days: int = GROUP_DAYS) -> list[HomeGroup]:
    out = []
    for grow in await GR.rows(tx):
        g = GR.render(grow)
        if g.state != "on":
            continue
        comps = []
        for m in await GR.members(tx, grow["id"]):
            if m["company_status"] != "active":
                continue
            chosen: HomeKpi | None = None
            for k in g.kpis:
                series = await GR.kpi_series(tx, m["company_id"], k, days, today)
                kpi = HomeKpi(key=k.key, title_fa=k.title_fa, unit=k.unit, source=k.source,
                              series=[SeriesPoint(**p) for p in series])  # fmt: skip
                if chosen is None:
                    chosen = kpi
                if series and any(p["value"] for p in series):
                    chosen = kpi
                    break
            comps.append(
                HomeCompany(code=m["company"], name_fa=m["name_fa"] or m["company"], kpi=chosen)
            )
        out.append(HomeGroup(key=g.key, title_fa=g.title_fa, companies=comps))
    return out


async def build(hub: Any, now: datetime | None = None) -> Home:
    """GET /home: the morning is the stored one of today (computed and stored
    when the tick has not run yet), the cards chosen now."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
        today = owner_today(tz, now)
        stored = await tx.scalar("SELECT lines FROM growth.home_mornings WHERE day = :d", d=today)
        if stored is None:
            await generate(tx, now)
            await generate_progress(tx, today)
            lines = await morning_lines(tx, tz, today)
            await store_morning(tx, holding.id, today, lines)
        else:
            lines = [str(x) for x in stored]
        effective, good = await choose(tx, now)
        prog = await best_progress(tx, today)
        return Home(
            cards=Cards(
                effective=render_suggestion(effective, "effective") if effective else None,
                good=render_suggestion(good, "good") if good else None,
                progress=render_progress(prog) if prog else None,
            ),
            morning=[x for x in lines if shown(x)][:5],
            groups=await group_kpis(tx, today),
            orders=await orders(tx),
            critical=await critical(tx),
        )


def plan_key(company: str, day: date, title: str) -> str:
    digest = hashlib.sha256(norm_title(title).encode()).hexdigest()[:12]
    return f"group:{company}:{day.isoformat()}:{digest}"
