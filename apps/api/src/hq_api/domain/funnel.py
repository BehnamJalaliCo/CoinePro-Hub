"""The funnel and its leaks (prompt 10 §3.1-§3.3, contract §19.2).

    visit -> signup -> referral_verified -> min_balance -> vip_active

Only stages with a source are counted; a stage without one is
`connected: false, count: null` and no rate around it is ever estimated.
  visit               an analytics source (none yet): never connected
  signup, vip_active  the products' events (intake.events `signup`,
                      `vip_activated`), once the company's product source is
                      registered for that kind (CR-009/010); until then not
                      connected
  referral_verified   the affiliate team list: D's new invitees
                      (growth.funnel_days, written by every pull)
  min_balance         of those, the ones whose balance meets the company's
                      ONE sealed minimum (policy article vip.min_balance);
                      without that article, not connected

A leak: a conversion of the last week more than 30% below the median of the
four weeks before it -> one growth.leaks row (one per stage and week) with a
note, and one task for the company's SALES manager.
"""

from __future__ import annotations

import itertools
import statistics
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import affiliate as A
from hq_api.domain import work as W
from hq_api.errors import ApiError

STAGES = ("visit", "signup", "referral_verified", "min_balance", "vip_active")
LABELS = {
    "visit": "بازدید",
    "signup": "ثبت‌نام",
    "referral_verified": "ثبت‌نام با رفرال ما",
    "min_balance": "حداقل موجودی",
    "vip_active": "VIP فعال",
}
PRODUCT_KINDS = {"signup": "signup", "vip_active": "vip_activated"}
AFFILIATE = ("referral_verified", "min_balance")
LEAK_DROP = 0.7  # a rate below 70% of the median (a fall of more than 30%)


def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    end = today or A.last_settled_day()
    days = {"week": 7, "month": 30}[period]
    return end - timedelta(days=days - 1), end


async def record_affiliate_day(tx: Tx, company_id: UUID | str, day: date) -> None:
    """The two affiliate stages of one day, over every account of the company."""
    row = await tx.one(
        """SELECT COALESCE(sum(new_invitees), 0) AS ni, sum(min_balance_invitees) AS mb
           FROM revenue.days WHERE company_id = :co AND day = :d""",
        co=company_id,
        d=day,
    )
    for stage, count in (("referral_verified", row["ni"]), ("min_balance", row["mb"])):
        if count is None:
            continue
        await tx.exec(
            """INSERT INTO growth.funnel_days (company_id, day, stage, count, source)
               VALUES (:co, :d, :st, :n, 'affiliate')
               ON CONFLICT (company_id, day, stage) DO UPDATE SET count = EXCLUDED.count, updated_at = now()""",
            co=company_id,
            d=day,
            st=stage,
            n=int(count),
        )


async def _sources(tx: Tx, company_id: UUID | str) -> dict[str, str | None]:
    """Which stages have a source today, and which."""
    out: dict[str, str | None] = dict.fromkeys(STAGES)
    if await tx.scalar("SELECT 1 FROM revenue.days WHERE company_id = :co LIMIT 1", co=company_id):
        out["referral_verified"] = "affiliate"
        if await tx.scalar(
            """SELECT 1 FROM support.kb_articles WHERE company_id = :co AND kind = 'policy'
                 AND key = 'vip.min_balance' AND status = 'approved' AND expires_at > now() LIMIT 1""",
            co=company_id,
        ):
            out["min_balance"] = "affiliate"
    kinds = await tx.all(
        """SELECT unnest(kinds) AS k FROM intake.sources
           WHERE company_id = :co AND kind = 'product' AND enabled""",
        co=company_id,
    )
    have = {r["k"] for r in kinds}
    for stage, event in PRODUCT_KINDS.items():
        if event in have:
            out[stage] = "product_events"
    return out


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time(0, 0), A.UTC8),
        datetime.combine(end + timedelta(days=1), time(0, 0), A.UTC8),
    )


async def counts(
    tx: Tx, company_id: UUID | str, start: date, end: date, sources: dict[str, str | None]
) -> dict[str, int | None]:
    out: dict[str, int | None] = dict.fromkeys(STAGES)
    for stage in AFFILIATE:
        if sources.get(stage):
            out[stage] = int(
                await tx.scalar(
                    """SELECT COALESCE(sum(count), 0) FROM growth.funnel_days
                       WHERE company_id = :co AND stage = :st AND day BETWEEN :s AND :e""",
                    co=company_id,
                    st=stage,
                    s=start,
                    e=end,
                )
            )
    a, b = _bounds(start, end)
    for stage, event in PRODUCT_KINDS.items():
        if sources.get(stage):
            out[stage] = int(
                await tx.scalar(
                    """SELECT count(DISTINCT COALESCE(subject, event_id)) FROM intake.events
                       WHERE company_id = :co AND kind = :k AND state IN ('accepted', 'applied')
                         AND COALESCE(at, received_at) >= :a AND COALESCE(at, received_at) < :b""",
                    co=company_id,
                    k=event,
                    a=a,
                    b=b,
                )
            )
    return out


def rate(frm: int | None, to: int | None) -> float | None:
    if frm is None or to is None or frm <= 0:
        return None
    return min(1.0, to / frm)


async def funnel(
    tx: Tx, company_id: UUID | str, company: str, period: str, today: date | None = None
) -> dict[str, Any]:
    start, end = period_range(period, today)
    sources = await _sources(tx, company_id)
    n = await counts(tx, company_id, start, end, sources)
    stages = [
        {
            "key": s,
            "label_fa": LABELS[s],
            "count": n[s] if sources[s] else None,
            "connected": bool(sources[s]),
            "source": sources[s],
        }
        for s in STAGES
    ]
    conversions = [
        {"from": a, "to": b, "rate": rate(n[a], n[b]) if sources[a] and sources[b] else None}
        for a, b in itertools.pairwise(STAGES)
    ]
    leaks = await tx.all(
        """SELECT stage, note_fa, rate, median_rate FROM growth.leaks
           WHERE company_id = :co AND period_start BETWEEN :s AND :e ORDER BY created_at DESC""",
        co=company_id,
        s=start - timedelta(days=6),
        e=end,
    )
    return {
        "company": company,
        "period": period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "stages": stages,
        "conversions": conversions,
        "leaks": [
            {
                "stage": r["stage"],
                "note_fa": r["note_fa"],
                "rate": float(r["rate"]),
                "median_rate": float(r["median_rate"]),
            }
            for r in leaks
        ],
    }


async def detect_leaks(
    tx: Tx, company_id: UUID | str, company: str, today: date | None = None
) -> list[dict[str, Any]]:
    """Last week's conversions against the median of the four weeks before;
    a fall of more than 30% -> a leak (once per stage and week) and a task
    for the company's SALES manager. Rule-only; its caller holds the gate."""
    end = today or A.last_settled_day()
    sources = await _sources(tx, company_id)
    weeks = []
    for k in range(5):
        e = end - timedelta(days=7 * k)
        weeks.append(await counts(tx, company_id, e - timedelta(days=6), e, sources))
    found = []
    for a, b in itertools.pairwise(STAGES):
        if not (sources[a] and sources[b]):
            continue
        now_rate = rate(weeks[0][a], weeks[0][b])
        past = [r for r in (rate(w[a], w[b]) for w in weeks[1:]) if r is not None]
        if now_rate is None or len(past) < 2:
            continue
        median = float(statistics.median(past))
        if median <= 0 or now_rate >= LEAK_DROP * median:
            continue
        start = end - timedelta(days=6)
        note = (
            f"نرخ «{LABELS[a]}» ← «{LABELS[b]}» در هفته‌ی {start.isoformat()} تا {end.isoformat()} "
            f"{now_rate:.0%} بود؛ میانه‌ی چهار هفته‌ی قبل {median:.0%}."
        )
        row = await tx.first(
            """INSERT INTO growth.leaks (company_id, stage, period, period_start, rate, median_rate, note_fa)
               VALUES (:co, :st, 'week', :ps, :r, :m, :n)
               ON CONFLICT (company_id, stage, period, period_start) DO NOTHING RETURNING id""",
            co=company_id,
            st=b,
            ps=start,
            r=round(now_rate, 5),
            m=round(median, 5),
            n=note,
        )
        if row is None:
            continue
        work_id = None
        try:
            w = await W.create(
                tx,
                audit.SYSTEM,
                company_id=UUID(str(company_id)),
                company_code=company,
                title=f"نشتی قیف: {LABELS[b]}"[:200],
                brief=note
                + "\n\nعلت را از داده‌ها (funnel.read، revenue.read) پیدا کن و یک پیشنهاد مشخص بده.",
                kind="one_off",
                priority="P2",
                department_code="SALES",
            )
            work_id = w["id"]
        except ApiError:
            pass  # no SALES manager yet: the leak is on the funnel page all the same
        await tx.exec(
            "UPDATE growth.leaks SET work_id = :w WHERE id = :id", id=row["id"], w=work_id
        )
        found.append({"stage": b, "rate": now_rate, "median_rate": median, "work_id": work_id})
    return found
