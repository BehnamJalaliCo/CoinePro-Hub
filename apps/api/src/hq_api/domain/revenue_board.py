"""⟨1.15⟩ Prompt 24 (contract §33.3): the revenue board, computed by code only.

From the company's ledger payments (money.payments, origin `ledger`; a `ledger_only` row, an approved
payment whose money never arrived, is left out; a short payment counts what arrived; a store's in-app
billing counts as a customer, never as an amount) and the costs the hub already holds:

- **MRR:** each paid amount spread evenly over its period (a payment without a period covers
  `default_period_days` from its time), summed per calendar month (UTC).
- **active / new / churned:** a customer is active in a month a period of theirs overlaps; new in the
  month of their first period; churned in the month their coverage ended when no renewal followed
  within `churn_grace_days` (and that time has passed).
- **churn_rate** = churned ÷ active over the last `churn_window_months` complete months; **LTV** = ARPU ÷
  churn_rate, null when churn is 0 or fewer than `min_months_ltv` complete months exist.
- **CAC** = (the month's ads spend + the tokens of the company's GROWTH department) ÷ its new paying
  customers, for the last complete month; **payback** = CAC ÷ that month's ARPU.
- **cohorts:** customers by the month of their first period; the share still active each month after.
- **forecast:** Holt's linear trend on the complete months' MRR with a ±z·σ band of its one-step
  residuals, only with `forecast_min_months` complete months; `forecast_basis_fa` says so in one line.
- **roi** and **cost_per_output** over the board's months.

The numbers are data in seed/payments/chain.yaml (`board`). No model is ever called here.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.domain import payments as P

Q6 = Decimal("0.000001")
ZERO = Decimal(0)


class RevBoardMonth(BaseModel):
    month: str
    mrr_usdt: Decimal
    new_customers: int
    churned: int
    active: int
    arpu_usdt: Decimal | None


class RevBoardCohort(BaseModel):
    start_month: str
    size: int
    retained: list[float]


class RevBoardForecast(BaseModel):
    month: str
    mrr_usdt: Decimal
    low: Decimal
    high: Decimal


class RevBoardRoiCost(BaseModel):
    tokens: Decimal
    voice: Decimal
    ads: Decimal
    servers: Decimal | None = None


class RevBoardRoi(BaseModel):
    revenue_usdt: Decimal
    cost_usd: RevBoardRoiCost
    ratio: float | None


class RevBoardOutputCost(BaseModel):
    kind: Literal["line_run", "deliverable", "order"]
    count: int
    usd_each: Decimal | None


class RevenueBoard(BaseModel):
    company: str | None
    period: Literal["month"] = "month"
    months: list[RevBoardMonth]
    churn_rate: float | None
    ltv_usdt: Decimal | None
    cac_usdt: Decimal | None
    payback_months: float | None
    cohorts: list[RevBoardCohort]
    forecast: list[RevBoardForecast]
    forecast_basis_fa: str
    roi: RevBoardRoi
    cost_per_output: list[RevBoardOutputCost]


# ------------------------------------------------------------------ pieces --
@dataclass(frozen=True)
class Pay:
    customer: str | None
    amount: Decimal
    start: datetime
    end: datetime


def conf() -> dict[str, Any]:
    b = P.cfg()["board"]
    assert isinstance(b, dict)
    return b


def month_start(d: date | datetime) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def label(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def q(v: Decimal) -> Decimal:
    return v.quantize(Q6)


def effective_amount(r: dict[str, Any]) -> Decimal:
    """What a ledger row brought: nothing for a store's billing (counted, never summed); what
    arrived for a short payment; else the ledger's amount."""
    if r["kind"] == "store" or r["amount_usdt"] is None:
        return ZERO
    if r["status"] == "amount_mismatch":
        return Decimal(r["chain_amount"] or 0)
    return Decimal(r["amount_usdt"])


def to_pays(rows: list[dict[str, Any]], default_days: int) -> list[Pay]:
    out = []
    for r in rows:
        start = r["period_start"] or r["paid_at"]
        end = r["period_end"] or (start + timedelta(days=default_days))
        out.append(Pay(r["customer"], effective_amount(r), start, end))
    return out


def overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def mrr(pays: list[Pay], m0: datetime, m1: datetime) -> Decimal:
    total = ZERO
    for p in pays:
        span = (p.end - p.start).total_seconds()
        if span <= 0 or p.amount == 0:
            continue
        share = overlap(p.start, p.end, m0, m1) / span
        if share > 0:
            total += p.amount * Decimal(repr(share))
    return total


def segments(pays: list[Pay], grace: timedelta) -> dict[str, list[tuple[datetime, datetime]]]:
    """Each customer's coverage, periods closer than `grace` merged into one segment."""
    by: dict[str, list[tuple[datetime, datetime]]] = {}
    for p in sorted(pays, key=lambda x: x.start):
        if p.customer is None:
            continue
        segs = by.setdefault(p.customer, [])
        if segs and p.start <= segs[-1][1] + grace:
            segs[-1] = (segs[-1][0], max(segs[-1][1], p.end))
        else:
            segs.append((p.start, p.end))
    return by


def holt(series: list[float], alpha: float, beta: float, horizon: int) -> tuple[list[float], float]:
    """Holt's linear trend: the next `horizon` values and σ of the one-step residuals (from the
    third value on: the first two set the level and the trend)."""
    level, trend = series[0], series[1] - series[0]
    residuals: list[float] = []
    for i, y in enumerate(series[1:], 1):
        fc = level + trend
        if i >= 2:
            residuals.append(y - fc)
        new_level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    sigma = statistics.pstdev(residuals) if residuals else 0.0
    return [level + h * trend for h in range(1, horizon + 1)], sigma


# ------------------------------------------------------------------- board --
async def _scalar(tx: Tx, sql: str, **kw: Any) -> Decimal:
    return Decimal(await tx.scalar(sql, **kw) or 0)


async def build(
    tx: Tx, company_id: UUID | None, company_code: str | None, now: datetime | None = None
) -> RevenueBoard:
    now = now or datetime.now(UTC)
    c = conf()
    rows = await tx.all(
        """SELECT customer, kind, status, amount_usdt, chain_amount, paid_at, period_start, period_end
           FROM money.payments
           WHERE origin = 'ledger' AND status <> 'ledger_only'
             AND (CAST(:co AS uuid) IS NULL OR company_id = :co)""",
        co=company_id,
    )
    pays = to_pays(rows, int(c["default_period_days"]))
    current = month_start(now)
    first_allowed = add_months(current, -(int(c["months"]) - 1))
    first = max(first_allowed, min((month_start(p.start) for p in pays), default=current))
    first = min(first, current)  # every period ahead (prepaid): still this month's board
    months_d = []
    m = first
    while m <= current:
        months_d.append(m)
        m = add_months(m, 1)
    grace = timedelta(days=int(c["churn_grace_days"]))
    segs = segments(pays, grace)
    first_seen = {cu: s[0][0] for cu, s in segs.items()}
    churn_at = [  # the end of a segment nobody renewed (and the grace has passed)
        (cu, e) for cu, ss in segs.items() for i, (_, e) in enumerate(ss)
        if i < len(ss) - 1 or e + grace <= now
    ]  # fmt: skip
    months: list[RevBoardMonth] = []
    active_sets: dict[date, set[str]] = {}
    for m in months_d:
        m0, m1 = at(m), at(add_months(m, 1))
        active = {cu for cu, ss in segs.items() if any(overlap(a, b, m0, m1) > 0 for a, b in ss)}
        active_sets[m] = active
        value = mrr(pays, m0, m1)
        months.append(
            RevBoardMonth(
                month=label(m),
                mrr_usdt=q(value),
                new_customers=sum(1 for t0 in first_seen.values() if m0 <= t0 < m1),
                churned=sum(1 for _, e in churn_at if m0 <= e < m1),
                active=len(active),
                arpu_usdt=q(value / len(active)) if active else None,
            )
        )
    complete = [x for x, d in zip(months, months_d, strict=True) if at(add_months(d, 1)) <= now]
    window = complete[-int(c["churn_window_months"]) :]
    act = sum(x.active for x in window)
    churn_rate = round(sum(x.churned for x in window) / act, 4) if act else None
    arpu_w = sum((x.mrr_usdt for x in window), ZERO) / act if act else None
    ltv = (
        q(arpu_w / Decimal(repr(churn_rate)))
        if churn_rate and arpu_w is not None and len(complete) >= int(c["min_months_ltv"])
        else None
    )
    cac, payback = await _cac(tx, company_id, months_d, complete, months, now)
    cohorts = _cohorts(first_seen, months_d, active_sets)
    forecast, basis = _forecast(complete, months_d, c)
    roi, per_output = await _costs(tx, company_id, at(months_d[0]), now, months)
    return RevenueBoard(
        company=company_code,
        months=months,
        churn_rate=churn_rate,
        ltv_usdt=ltv,
        cac_usdt=cac,
        payback_months=payback,
        cohorts=cohorts,
        forecast=forecast,
        forecast_basis_fa=basis,
        roi=roi,
        cost_per_output=per_output,
    )


async def _cac(
    tx: Tx,
    company_id: UUID | None,
    months_d: list[date],
    complete: list[RevBoardMonth],
    months: list[RevBoardMonth],
    now: datetime,
) -> tuple[Decimal | None, float | None]:
    if not complete:
        return None, None
    last = complete[-1]
    d = months_d[months.index(last)]
    m0, m1 = at(d), at(add_months(d, 1))
    if last.new_customers == 0:
        return None, None
    ads = await _scalar(
        tx,
        """SELECT sum(spend) FROM growth.ad_daily WHERE day >= :a AND day < :b
             AND (CAST(:co AS uuid) IS NULL OR company_id = :co)""",
        a=d,
        b=add_months(d, 1),
        co=company_id,
    )
    growth = await _scalar(
        tx,
        """SELECT sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)) FROM llm.calls
           WHERE started_at >= :a AND started_at < :b AND department = 'GROWTH'
             AND (CAST(:co AS uuid) IS NULL OR company_id = :co)""",
        a=m0,
        b=m1,
        co=company_id,
    )
    del now
    cac = q((ads + growth) / last.new_customers)
    payback = (
        round(float(cac / last.arpu_usdt), 2) if last.arpu_usdt and last.arpu_usdt > 0 else None
    )
    return cac, payback


def _cohorts(
    first_seen: dict[str, datetime], months_d: list[date], active: dict[date, set[str]]
) -> list[RevBoardCohort]:
    out = []
    for i, m in enumerate(months_d):
        members = {cu for cu, t0 in first_seen.items() if month_start(t0) == m}
        if not members:
            continue
        retained = [
            round(100.0 * len(members & active[later]) / len(members), 1) for later in months_d[i:]
        ]
        out.append(RevBoardCohort(start_month=label(m), size=len(members), retained=retained))
    return out


def _forecast(
    complete: list[RevBoardMonth], months_d: list[date], c: dict[str, Any]
) -> tuple[list[RevBoardForecast], str]:
    need = int(c["forecast_min_months"])
    if len(complete) < need:
        return [], (f"پیش‌بینی نیست: {len(complete)} ماه کامل داده هست و دست‌کم {need} ماه لازم است.")
    series = [float(x.mrr_usdt) for x in complete]
    values, sigma = holt(series, float(c["holt_alpha"]), float(c["holt_beta"]),
                         int(c["forecast_months"]))  # fmt: skip
    band = float(c["band_z"]) * sigma
    last = months_d[len(complete) - 1]
    out = []
    for h, v in enumerate(values, 1):
        mid = max(0.0, v)
        out.append(
            RevBoardForecast(
                month=label(add_months(last, h)),
                mrr_usdt=q(Decimal(repr(mid))),
                low=q(Decimal(repr(max(0.0, v - band)))),
                high=q(Decimal(repr(max(0.0, v + band)))),
            )
        )
    basis = (
        f"روند خطی هولت روی MRR {len(complete)} ماه کامل؛ بازه ±{c['band_z']} انحراف معیار خطاهای "
        "پیش‌بینی یک‌ماهه است."
    )
    if not math.isfinite(sigma):  # (never with finite inputs)
        return [], basis
    return out, basis


async def _costs(
    tx: Tx, company_id: UUID | None, start: datetime, end: datetime, months: list[RevBoardMonth]
) -> tuple[RevBoardRoi, list[RevBoardOutputCost]]:
    kw: dict[str, Any] = {"s": start, "e": end, "co": company_id}
    co = "(CAST(:co AS uuid) IS NULL OR company_id = :co)"
    tokens = await _scalar(
        tx,
        f"""SELECT sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)) FROM llm.calls
            WHERE started_at >= :s AND started_at < :e AND {co}""",  # noqa: S608 - constants
        **kw,
    )
    voice = await _scalar(
        tx,
        f"SELECT sum(usd) FROM talk.voice_usage WHERE at >= :s AND at < :e AND {co}",  # noqa: S608
        **kw,
    )
    ads = await _scalar(
        tx,
        f"""SELECT sum(spend) FROM growth.ad_daily WHERE day >= CAST(:s AS date)
              AND day <= CAST(:e AS date) AND {co}""",  # noqa: S608 - constants
        s=start.date(),
        e=end.date(),
        co=company_id,
    )
    revenue = sum((x.mrr_usdt for x in months), ZERO)
    cost = tokens + voice + ads
    roi = RevBoardRoi(
        revenue_usdt=q(revenue),
        cost_usd=RevBoardRoiCost(tokens=q(tokens), voice=q(voice), ads=q(ads), servers=None),
        ratio=round(float(revenue / cost), 4) if cost > 0 else None,
    )
    runs = await tx.one(
        f"""SELECT count(*) AS n, COALESCE(sum(usd_equiv), 0) AS usd FROM lines.runs
            WHERE NOT dry AND state = 'done' AND at >= :s AND at < :e AND {co}""",  # noqa: S608
        **kw,
    )
    deliverables = int(
        await tx.scalar(
            f"""SELECT count(*) FROM cartable.deliverables
                WHERE created_at >= :s AND created_at < :e AND {co}""",  # noqa: S608
            **kw,
        )
        or 0
    )
    orders = int(
        await tx.scalar(
            f"""SELECT count(*) FROM work.work WHERE depth = 0 AND created_by_kind = 'owner'
                  AND created_at >= :s AND created_at < :e AND {co}""",  # noqa: S608
            **kw,
        )
        or 0
    )

    def each(total: Decimal, n: int) -> Decimal | None:
        return q(total / n) if n else None

    n_runs = int(runs["n"])
    return roi, [
        RevBoardOutputCost(kind="line_run", count=n_runs, usd_each=each(Decimal(runs["usd"]), n_runs)),
        RevBoardOutputCost(kind="deliverable", count=deliverables, usd_each=each(tokens, deliverables)),
        RevBoardOutputCost(kind="order", count=orders, usd_each=each(tokens, orders)),
    ]  # fmt: skip


async def payments_by_company(
    tx: Tx, start: datetime, end: datetime, company_id: UUID | None = None
) -> dict[str, dict[str, Any]]:
    """§33.3 `by_source` of GET /revenue/summary: per company, the USDT that reached its own
    addresses in [start, end) (matched and short payments: what arrived; money without a
    customer too) and the count of a store's billing (counted, never summed)."""
    rows = await tx.all(
        """SELECT c.code AS company,
                  COALESCE(sum(CASE WHEN p.status IN ('matched', 'amount_mismatch', 'chain_only')
                                    THEN COALESCE(p.chain_amount, 0) ELSE 0 END), 0) AS usdt,
                  count(*) FILTER (WHERE p.kind = 'store') AS store
           FROM money.payments p JOIN core.companies c ON c.id = p.company_id
           WHERE p.paid_at >= :s AND p.paid_at < :e
             AND (CAST(:co AS uuid) IS NULL OR p.company_id = :co)
           GROUP BY c.code""",
        s=start,
        e=end,
        co=company_id,
    )
    return {r["company"]: {"usdt": Decimal(r["usdt"]), "store": int(r["store"])} for r in rows}
