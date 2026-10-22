"""ROI of agents, departments and companies (prompt 12 §10, contract §21.7).
Code only, computed when read, for a week (Saturday..Friday) or a Jalali
month of the owner's zone:

    cost_usd               the ledger (llm.calls: cost + equivalent cost)
    accepted               deliverables whose latest owner rating is >= 6
    avg_rating             the latest owner ratings of the period's deliverables
    value_points           Σ (rating / 10) over the accepted deliverables
    cost_per_accepted_usd  cost / accepted (null without an accepted one)
    attributed             records naming the employee: rescued referrals
                           (a rescue step of theirs on a case rescued in the
                           period) and support conversations they closed
    revenue_usd, net_usd, roi   COMPANIES ONLY (§19.1): the revenue radar's
                           commission; roi = revenue / cost. A company without
                           revenue has roi null, never 0; an employee's or a
                           department's revenue and roi are always null
                           (commission cannot be traced to one agent).
    trend                  roi for companies, cost per accepted otherwise,
                           over the earlier periods and this one
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from hq_api.db import Tx
from hq_api.domain import stars as S
from hq_api.errors import ApiError

ACCEPTED_FROM = 6
TREND = 4
Q = Decimal("0.000001")


def window(period: str, key: str | None, today: date) -> tuple[str, date, date]:
    """(period_key, first day, first day after) of a week or a Jalali month."""
    if period == "week":
        start = date.fromisoformat(key) if key else S.saturday_of(today)
        if start.weekday() != 5:
            raise ApiError(422, "validation_failed", fields={"key": "a Saturday (YYYY-MM-DD)"})
        return start.isoformat(), start, start + timedelta(days=7)
    if key:
        y, m = (int(x) for x in key.split("-")[:2])
        anchor = _jalali_day(y, m, today)
    else:
        anchor = today
    start, end = S.month_window(anchor)
    return S.jalali_key(start), start, end


def _jalali_day(y: int, m: int, today: date) -> date:
    """A Gregorian day inside Jalali month y-m (searched around today)."""
    from hq_api.worker.jalali import to_jalali

    probe = today
    for _ in range(0, 4000, 15):
        jy, jm, _d = to_jalali(probe)
        if (jy, jm) == (y, m):
            return probe
        probe -= timedelta(days=15) if (jy, jm) > (y, m) else timedelta(days=-15)
    raise ApiError(422, "validation_failed", fields={"key": "a Jalali month (YYYY-MM)"})


def earlier(period: str, start: date) -> date:
    """The first day of the period before."""
    if period == "week":
        return start - timedelta(days=7)
    return S.month_window(start - timedelta(days=1))[0]


async def _figures(tx: Tx, by: str, company: str | None, s: Any, e: Any) -> list[dict[str, Any]]:
    """The rows of one period (no trend), for the scope `by`."""
    if by == "employee":
        units = await tx.all(
            """SELECT e.code AS key, c.code AS company, ARRAY[e.code] AS codes
               FROM core.employees e JOIN core.companies c ON c.id = e.company_id
               WHERE e.kind <> 'system' AND c.status <> 'archived'
                 AND (CAST(:co AS text) IS NULL OR c.code = :co)
               ORDER BY c.code, e.code""",
            co=company,
        )
    elif by == "department":
        units = await tx.all(
            """SELECT d.code AS key, c.code AS company,
                      ARRAY(SELECT x.code FROM core.employees x WHERE x.department_id = d.id) AS codes
               FROM core.departments d JOIN core.companies c ON c.id = d.company_id
               WHERE c.status <> 'archived' AND (CAST(:co AS text) IS NULL OR c.code = :co)
               ORDER BY c.code, d.code""",
            co=company,
        )
    else:
        units = await tx.all(
            """SELECT c.code AS key, c.code AS company,
                      ARRAY(SELECT x.code FROM core.employees x WHERE x.company_id = c.id) AS codes
               FROM core.companies c WHERE c.status <> 'archived' AND c.kind = 'company'
                 AND (CAST(:co AS text) IS NULL OR c.code = :co)
               ORDER BY c.code""",
            co=company,
        )
    out = []
    for u in units:
        codes = list(u["codes"] or [])
        if by == "company":
            cost = await tx.scalar(
                """SELECT COALESCE(sum(COALESCE(k.cost_usd, 0) + COALESCE(k.equiv_cost_usd, 0)), 0)
                   FROM llm.calls k JOIN core.companies c ON c.id = k.company_id
                   WHERE c.code = :co AND k.started_at >= :s AND k.started_at < :e""",
                co=u["company"],
                s=s,
                e=e,
            )
        else:
            cost = await tx.scalar(
                """SELECT COALESCE(sum(COALESCE(k.cost_usd, 0) + COALESCE(k.equiv_cost_usd, 0)), 0)
                   FROM llm.calls k WHERE k.actor_ref = ANY(:codes) AND k.started_at >= :s AND k.started_at < :e""",
                codes=codes,
                s=s,
                e=e,
            )
        ratings = await tx.all(
            """SELECT rt.score FROM cartable.deliverables dl
               JOIN core.employees p ON p.id = dl.producer_id
               JOIN LATERAL (SELECT x.score FROM cartable.ratings x WHERE x.deliverable_id = dl.id
                             ORDER BY x.version_no DESC LIMIT 1) rt ON true
               WHERE p.code = ANY(:codes) AND dl.created_at >= :s AND dl.created_at < :e""",
            codes=codes,
            s=s,
            e=e,
        )
        scores = [int(r["score"]) for r in ratings]
        accepted = [x for x in scores if x >= ACCEPTED_FROM]
        rescued = await tx.scalar(
            """SELECT count(DISTINCT rc.id) FROM growth.rescue_cases rc
               WHERE rc.state = 'rescued' AND rc.rescued_at >= :s AND rc.rescued_at < :e
                 AND EXISTS (SELECT 1 FROM growth.rescue_steps st WHERE st.case_id = rc.id
                               AND st.by_kind = 'agent' AND st.by_code = ANY(:codes))""",
            codes=codes,
            s=s,
            e=e,
        )
        resolved = await tx.scalar(
            """SELECT count(*) FROM support.conversations sc
               WHERE sc.state = 'closed' AND sc.closed_at >= :s AND sc.closed_at < :e
                 AND sc.closed_by_kind = 'agent' AND sc.closed_by_code = ANY(:codes)""",
            codes=codes,
            s=s,
            e=e,
        )
        cost_d = Decimal(cost or 0)
        row: dict[str, Any] = {
            "by": by,
            "key": u["key"],
            "company": u["company"],
            "cost_usd": cost_d.quantize(Q),
            "accepted": len(accepted),
            "avg_rating": round(sum(scores) / len(scores), 2) if scores else None,
            "value_points": round(sum(x / 10 for x in accepted), 2),
            "cost_per_accepted_usd": (cost_d / len(accepted)).quantize(Q) if accepted else None,
            "attributed": {
                "rescued": int(rescued or 0),
                "resolved_conversations": int(resolved or 0),
            },
            "revenue_usd": None,
            "net_usd": None,
            "roi": None,
        }
        if by == "company":
            rev = await tx.first(
                """SELECT count(*) AS days, COALESCE(sum(d.commission_usdt), 0) AS usd
                   FROM revenue.days d JOIN core.companies c ON c.id = d.company_id
                   WHERE c.code = :co AND d.day >= CAST(:a AS date) AND d.day < CAST(:b AS date)""",
                co=u["company"],
                a=s.date() if hasattr(s, "date") else s,
                b=e.date() if hasattr(e, "date") else e,
            )
            if rev and int(rev["days"]) and Decimal(rev["usd"]) > 0:
                revenue = Decimal(rev["usd"]).quantize(Q)
                row["revenue_usd"] = revenue
                row["net_usd"] = (revenue - cost_d).quantize(Q)
                row["roi"] = round(float(revenue / cost_d), 4) if cost_d > 0 else None
        out.append(row)
    return out


async def rows(
    tx: Tx, by: str, period: str, key: str | None, company: str | None
) -> list[dict[str, Any]]:
    tz = ZoneInfo(
        str(await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran")
    )
    from datetime import datetime

    today = datetime.now(tz).date()
    period_key, start, end = window(period, key, today)
    current = await _figures(tx, by, company, S.at(start, tz), S.at(end, tz))
    history: list[list[dict[str, Any]]] = []
    a = start
    for _ in range(TREND):
        b = a
        a = earlier(period, a)
        history.append(await _figures(tx, by, company, S.at(a, tz), S.at(b, tz)))
    for r in current:
        r["period"] = period
        r["period_key"] = period_key
        trend = []
        for past in reversed(history):
            prev = next(
                (x for x in past if x["key"] == r["key"] and x["company"] == r["company"]), None
            )
            trend.append(_trend_value(prev))
        trend.append(_trend_value(r))
        r["trend"] = [t for t in trend if t is not None]
    return current


def _trend_value(r: dict[str, Any] | None) -> float | None:
    if r is None:
        return None
    if r["by"] == "company":
        roi_: float | None = r["roi"]
        return roi_
    v = r["cost_per_accepted_usd"]
    return float(v) if v is not None else None
