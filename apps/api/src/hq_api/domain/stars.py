"""Stars, the company score, efficiency and lessons (contract §18.4, prompt 08 §4).

CEOs give their employees 0-5 stars a week (Saturday..Friday, owner zone)
against the company's rubric; a star without a reason or evidence is kept but
not counted, and the overseer may un-count one (star.audit). The owner gives
no stars; the owner's 1-10 rating stays its own part of the employee score
(§1.16, domain/scoring.py).

    company score = 35% KPI + 20% challenges + 15% compliance + 15% people
                    + 15% efficiency;  company stars = score / 20

Every part is 0..100; a part without data is left out and the weights are
renormalised (the same rule as the employee score), so a company is never
punished for a missing feed: no KPI store exists yet, and challenges and
compliance come from the overseer's tables (prompt 08 §2) when they exist.

Efficiency comes from the ledger only (agents.runs, llm.calls, the owner's
ratings), never from what an agent reports:
    company  = 40% envelope discipline (month use <= envelope: 100; above: 0)
             + 30% waste (100 x (1 - share of tokens in failed or refused runs
                         and in work that never delivered))
             + 30% cost per accepted deliverable against the holding median
    employee = 50% tokens per accepted deliverable against its department median
             + 25% failed-run share (100 x (1 - share))
             + 25% estimate accuracy (month use within +-25% of the hire
                   estimate, prorated to the day: 100; then linear to 0 at +-100%)
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import hiring, notify
from hq_api.domain import work as W
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.worker.jalali import to_jalali
from hq_common.redact import scrub

WEIGHTS = {"kpi": 0.35, "challenges": 0.20, "compliance": 0.15, "people": 0.15, "efficiency": 0.15}
COMPANY_EFFICIENCY = {"envelope": 0.40, "waste": 0.30, "cost": 0.30}
EMPLOYEE_EFFICIENCY = {"cost": 0.50, "failed": 0.25, "estimate": 0.25}
MIN_EFFICIENCY_WEIGHT = 15  # percent of a rubric (owner, 2026-10-17)
ACCEPTED_FROM = 6  # the owner's rating that makes a deliverable accepted (as scoring.py)
INFLATION_SHARE = 0.70  # more fives than this in a company's week is flagged
INFLATION_MIN = 3  # ... once it has at least this many counted stars
TREND = 4  # earlier periods shown in a trend


# ------------------------------------------------------- pure arithmetic --
def weighted(parts: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """Weighted mean over the parts that have data (weights renormalised)."""
    present = {k: v for k, v in parts.items() if v is not None and k in weights}
    if not present:
        return None
    total = sum(weights[k] for k in present)
    return sum(weights[k] * float(v) for k, v in present.items()) / total


def company_score(parts: dict[str, float | None]) -> tuple[float | None, float | None]:
    """(score 0..100, stars 0..5) of a company from its five parts."""
    score = weighted(parts, WEIGHTS)
    if score is None:
        return None, None
    score = round(max(0.0, min(100.0, score)), 1)
    return score, round(score / 20, 2)


def against_median(own: float | None, med: float | None) -> float | None:
    """100 at or below the median cost, falling with the ratio above it."""
    if own is None or med is None:
        return None
    if own <= 0:
        return 100.0
    return round(100 * min(1.0, med / own), 1)


def share_part(share: float | None) -> float | None:
    """100 x (1 - share): no waste (or no failed run) scores 100."""
    if share is None:
        return None
    return round(100 * (1 - max(0.0, min(1.0, share))), 1)


def estimate_part(ratio: float | None) -> float | None:
    """Actual / estimated use: within +-25% scores 100, then linear to 0 at +-100%."""
    if ratio is None:
        return None
    off = abs(ratio - 1)
    if off <= 0.25:
        return 100.0
    return round(100 * max(0.0, 1 - (off - 0.25) / 0.75), 1)


def company_efficiency(
    *,
    used: float | None,
    envelope: float | None,
    waste_share: float | None,
    cost_per_accepted: float | None,
    holding_median: float | None,
) -> float | None:
    env = None
    if envelope is not None and envelope > 0 and used is not None:
        env = 100.0 if used <= envelope else 0.0
    value = weighted(
        {
            "envelope": env,
            "waste": share_part(waste_share),
            "cost": against_median(cost_per_accepted, holding_median),
        },
        COMPANY_EFFICIENCY,
    )
    return None if value is None else round(value, 1)


def employee_efficiency(
    *,
    tokens_per_accepted: float | None,
    dept_median: float | None,
    failed_share: float | None,
    estimate_ratio: float | None,
) -> float | None:
    value = weighted(
        {
            "cost": against_median(tokens_per_accepted, dept_median),
            "failed": share_part(failed_share),
            "estimate": estimate_part(estimate_ratio),
        },
        EMPLOYEE_EFFICIENCY,
    )
    return None if value is None else round(value, 1)


def inflated(stars: list[float]) -> bool:
    """More than 70% fives among a company's counted stars of a period."""
    return (
        len(stars) >= INFLATION_MIN
        and sum(1 for s in stars if s >= 5) / len(stars) > INFLATION_SHARE
    )


# ------------------------------------------------------------- periods --
async def owner_zone(tx: Tx) -> ZoneInfo:
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    return ZoneInfo(str(tz))


def saturday_of(day: date) -> date:
    """The Saturday that starts `day`'s week (Saturday..Friday)."""
    return day - timedelta(days=(day.weekday() - 5) % 7)


def jalali_key(day: date) -> str:
    y, m, _ = to_jalali(day)
    return f"{y:04d}-{m:02d}"


def week_window(saturday: date) -> tuple[date, date]:
    return saturday, saturday + timedelta(days=7)


def month_window(any_day: date) -> tuple[date, date]:
    """The Jalali month containing `any_day`: [first day, first day of the next)."""
    start = hiring.jalali_month_start(any_day)
    nxt = hiring.jalali_month_start(start + timedelta(days=32))
    return start, nxt


def at(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


# --------------------------------------------------------------- rubrics --
def validate_rubric(criteria: list[dict[str, Any]]) -> None:
    keys = [c["key"] for c in criteria]
    if len(set(keys)) != len(keys):
        raise ApiError(422, "validation_failed", fields={"criteria": "keys must be unique"})
    total = sum((Decimal(str(c["weight"])) for c in criteria), Decimal(0))
    if abs(total - 100) > Decimal("0.01"):
        raise ApiError(422, "validation_failed", fields={"criteria": "the weights add up to 100"})
    eff = next((c for c in criteria if c["key"] == "efficiency"), None)
    if eff is None or Decimal(str(eff["weight"])) < MIN_EFFICIENCY_WEIGHT:
        raise ApiError(
            422,
            "validation_failed",
            fields={"criteria": f"an `efficiency` criterion of at least {MIN_EFFICIENCY_WEIGHT}%"},
        )


async def latest_rubric(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT r.*, c.code AS company FROM people.star_rubrics r
           JOIN core.companies c ON c.id = r.company_id
           WHERE r.company_id = :co ORDER BY r.version DESC LIMIT 1""",
        co=company_id,
    )


async def write_rubric(
    tx: Tx, who: Principal, company_id: UUID, criteria: list[dict[str, Any]], rules_md: str
) -> dict[str, Any]:
    validate_rubric(criteria)
    version = await tx.scalar(
        "SELECT COALESCE(max(version), 0) + 1 FROM people.star_rubrics WHERE company_id = :co",
        co=company_id,
    )
    await tx.exec(
        """INSERT INTO people.star_rubrics (company_id, version, criteria, rules_md, by_kind, by_code)
           VALUES (:co, :v, CAST(:c AS jsonb), :rules, :k, :code)""",
        co=company_id,
        v=version,
        c=json.dumps(criteria, ensure_ascii=False, default=str),
        rules=scrub(rules_md),
        k=who.kind,
        code=who.code,
    )
    row = await latest_rubric(tx, company_id)
    assert row is not None
    return row


# ----------------------------------------------------------------- stars --
STAR_SQL = """
    SELECT s.*, e.code AS employee, c.code AS company FROM people.stars s
    JOIN core.employees e ON e.id = s.employee_id JOIN core.companies c ON c.id = s.company_id
"""


async def give(
    tx: Tx,
    who: Principal,
    *,
    employee_code: str,
    week: date,
    stars: Decimal,
    criteria: dict[str, Decimal],
    reason_md: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """One CEO's stars for one employee of its own company and week (a second
    give for the same week replaces the first until that week is rolled up)."""
    emp = await tx.first(
        "SELECT id, company_id, kind, status FROM core.employees WHERE code = :c", c=employee_code
    )
    if emp is None or emp["company_id"] != who.company_id:
        raise ApiError(403, "policy_denied", "stars only for your own company's employees")
    if emp["kind"] in ("system", "ceo") or emp["status"] == "dismissed":
        raise ApiError(422, "validation_failed", fields={"employee": "not an employee you rate"})
    if week.weekday() != 5:
        raise ApiError(422, "validation_failed", fields={"week": "a Saturday (the week's start)"})
    zone = await owner_zone(tx)
    if week > saturday_of(datetime.now(zone).date()):
        raise ApiError(422, "validation_failed", fields={"week": "not a future week"})
    if await tx.scalar("SELECT people.week_rolled_up(:w)", w=week):
        raise ApiError(409, "validation_failed", "that week is already rolled up")
    rubric = await latest_rubric(tx, who.company_id) if who.company_id else None
    if rubric is not None:
        known = {c["key"] for c in rubric["criteria"]}
        unknown = sorted(set(criteria) - known)
        if unknown:
            raise ApiError(
                422,
                "validation_failed",
                fields={"criteria": f"not in the rubric: {', '.join(unknown)}"},
            )
    reason = scrub(reason_md.strip())
    counted = bool(reason) and bool(evidence)
    params = {
        "co": who.company_id,
        "emp": emp["id"],
        "week": week,
        "stars": stars,
        "crit": json.dumps({k: float(v) for k, v in criteria.items()}),
        "reason": reason,
        "ev": json.dumps(evidence, ensure_ascii=False),
        "counted": counted,
        "rv": rubric["version"] if rubric else None,
        "k": who.kind,
        "c": who.code,
    }
    await tx.exec(
        """INSERT INTO people.stars (company_id, employee_id, week, stars, criteria, reason_md, evidence,
               counted, rubric_version, by_kind, by_code)
           VALUES (:co, :emp, :week, :stars, CAST(:crit AS jsonb), :reason, CAST(:ev AS jsonb), :counted,
                   :rv, :k, :c)
           ON CONFLICT (employee_id, week) DO UPDATE SET
               stars = EXCLUDED.stars, criteria = EXCLUDED.criteria, reason_md = EXCLUDED.reason_md,
               evidence = EXCLUDED.evidence, counted = EXCLUDED.counted,
               rubric_version = EXCLUDED.rubric_version, by_kind = EXCLUDED.by_kind,
               by_code = EXCLUDED.by_code, overseer_note = NULL, audited_by = NULL, audited_at = NULL,
               updated_at = now()""",
        **params,
    )
    return await tx.one(
        STAR_SQL + " WHERE s.employee_id = :emp AND s.week = :week", emp=emp["id"], week=week
    )


async def audit(tx: Tx, who: Principal, star_id: UUID, counted: bool, note: str) -> dict[str, Any]:
    """The overseer marks a star counted or not, with the reason (star.audit)."""
    row = await tx.first("SELECT id FROM people.stars WHERE id = :id", id=star_id)
    if row is None:
        raise ApiError(404, "not_found")
    await tx.exec(
        """UPDATE people.stars SET counted = :counted, overseer_note = :note, audited_by = :by,
               audited_at = now(), updated_at = now() WHERE id = :id""",
        id=star_id,
        counted=counted,
        note=scrub(note)[:2000],
        by=who.code,
    )
    return await tx.one(STAR_SQL + " WHERE s.id = :id", id=star_id)


# ----------------------------------------------------------- the ledger --
async def _table(tx: Tx, name: str) -> bool:
    return bool(await tx.scalar("SELECT to_regclass(:n) IS NOT NULL", n=name))


async def _oversight_parts(
    tx: Tx, company_id: UUID, start: datetime, end: datetime
) -> tuple[float | None, float | None]:
    """(challenges, compliance) 0..100 from the overseer's tables (prompt 08
    §2), None while those tables do not exist (the part is left out)."""
    challenges = compliance = None
    if await _table(tx, "oversight.challenges"):
        v = await tx.scalar(
            """SELECT avg(score) FROM oversight.challenges
               WHERE company_id = :co AND score IS NOT NULL AND due_at >= :s AND due_at < :e""",
            co=company_id,
            s=start,
            e=end,
        )
        challenges = float(v) if v is not None else None
    if await _table(tx, "oversight.compliance"):
        v = await tx.scalar(
            """SELECT score FROM oversight.compliance
               WHERE company_id = :co AND day < CAST(:e AS date) ORDER BY day DESC LIMIT 1""",
            co=company_id,
            e=end,
        )
        compliance = float(v) if v is not None else None
    return challenges, compliance


TOKENS = "(r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens)"
ACCEPTED = f"""(SELECT x.score FROM cartable.ratings x WHERE x.deliverable_id = dl.id
                ORDER BY x.version_no DESC LIMIT 1) >= {ACCEPTED_FROM}"""  # noqa: S608 - module constants


async def company_figures(
    tx: Tx, start: datetime, end: datetime, month_start: datetime
) -> list[dict[str, Any]]:
    """Per active operating company: the ledger figures of [start, end)."""
    rows = await tx.all(
        f"""SELECT c.id, c.code,
               (SELECT b.token_limit FROM llm.budgets b
                 WHERE b.company_id = c.id AND b.scope_type = 'company' AND b.scope_ref = c.code
                   AND b.period = 'month' AND b.enabled) AS envelope,
               (SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                                    + COALESCE(k.cache_read_tokens, 0) + COALESCE(k.cache_write_tokens, 0)), 0)
                  FROM llm.calls k WHERE k.company_id = c.id AND k.started_at >= :ms AND k.started_at < :e)
                 AS used_month,
               (SELECT COALESCE(sum({TOKENS}), 0) FROM agents.runs r
                 WHERE r.company_id = c.id AND r.queued_at >= :s AND r.queued_at < :e) AS run_tokens,
               (SELECT COALESCE(sum({TOKENS}), 0) FROM agents.runs r LEFT JOIN work.work w ON w.id = r.work_id
                 WHERE r.company_id = c.id AND r.queued_at >= :s AND r.queued_at < :e
                   AND (r.state IN ('failed', 'refused') OR w.status IN ('failed', 'cancelled'))) AS waste,
               (SELECT COALESCE(sum(COALESCE(k.cost_usd, 0) + COALESCE(k.equiv_cost_usd, 0)), 0)
                  FROM llm.calls k WHERE k.company_id = c.id AND k.started_at >= :s AND k.started_at < :e)
                 AS cost_usd,
               (SELECT count(*) FROM cartable.deliverables dl
                 WHERE dl.company_id = c.id AND dl.created_at >= :s AND dl.created_at < :e AND {ACCEPTED})
                 AS accepted
           FROM core.companies c WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code""",  # noqa: S608 - composed from module constants; values are bound
        s=start,
        e=end,
        ms=month_start,
    )
    return [dict(r) for r in rows]


async def employee_figures(
    tx: Tx,
    company_ids: list[UUID],
    start: datetime,
    end: datetime,
    month_start: datetime,
    month_days: int,
    elapsed_days: int,
) -> dict[UUID, dict[str, Any]]:
    """Per employee of those companies: the ledger figures of [start, end)."""
    rows = await tx.all(
        f"""SELECT e.id, e.code, e.company_id, e.department_id, e.title_fa,
               (SELECT COALESCE(sum({TOKENS}), 0) FROM agents.runs r
                 WHERE r.employee_id = e.id AND r.queued_at >= :s AND r.queued_at < :e) AS tokens,
               (SELECT count(*) FROM agents.runs r
                 WHERE r.employee_id = e.id AND r.queued_at >= :s AND r.queued_at < :e
                   AND r.state IN ('done', 'failed', 'refused')) AS runs,
               (SELECT count(*) FROM agents.runs r
                 WHERE r.employee_id = e.id AND r.queued_at >= :s AND r.queued_at < :e
                   AND r.state IN ('failed', 'refused')) AS failed,
               (SELECT count(*) FROM cartable.deliverables dl
                 WHERE dl.producer_id = e.id AND dl.created_at >= :s AND dl.created_at < :e AND {ACCEPTED})
                 AS accepted,
               (SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                                    + COALESCE(k.cache_read_tokens, 0) + COALESCE(k.cache_write_tokens, 0)), 0)
                  FROM llm.calls k WHERE k.actor_ref = e.code AND k.started_at >= :ms AND k.started_at < :e)
                 AS used_month,
               (SELECT COALESCE((d.payload->'quota_estimate_month'->>'tokens')::bigint, d.quota_tokens)
                  FROM cartable.decisions d WHERE d.id = e.hired_by_decision_id) AS estimate
           FROM core.employees e
           WHERE e.company_id = ANY(:cos) AND e.kind NOT IN ('system') AND e.status <> 'dismissed'""",  # noqa: S608 - module constants; values bound
        s=start,
        e=end,
        ms=month_start,
        cos=company_ids,
    )
    out: dict[UUID, dict[str, Any]] = {}
    for r in rows:
        d = dict(r)
        d["tokens_per_accepted"] = (
            float(d["tokens"]) / int(d["accepted"]) if int(d["accepted"] or 0) > 0 else None
        )
        d["failed_share"] = int(d["failed"]) / int(d["runs"]) if int(d["runs"] or 0) > 0 else None
        est = d["estimate"]
        prorated = float(est) * elapsed_days / month_days if est and month_days else None
        d["estimate_ratio"] = float(d["used_month"]) / prorated if prorated else None
        out[d["id"]] = d
    by_dept: dict[Any, list[float]] = {}
    for d in out.values():
        if d["tokens_per_accepted"] is not None:
            by_dept.setdefault(d["department_id"], []).append(d["tokens_per_accepted"])
    for d in out.values():
        values = by_dept.get(d["department_id"])
        d["efficiency"] = employee_efficiency(
            tokens_per_accepted=d["tokens_per_accepted"],
            dept_median=median(values) if values else None,
            failed_share=d["failed_share"],
            estimate_ratio=d["estimate_ratio"],
        )
    return out


# --------------------------------------------------------------- roll-up --
async def rollup(tx: Tx, period: str, key: str, start_day: date, end_day: date) -> dict[str, Any]:
    """The roll-up of one closed period (idempotent: an existing one is kept)."""
    existing = await tx.first(
        "SELECT * FROM people.star_rollups WHERE period = :p AND key = :k", p=period, k=key
    )
    if existing is not None:
        return {"created": False, "best_company": existing["best_company"], "key": key}
    zone = await owner_zone(tx)
    start, end = at(start_day, zone), at(end_day, zone)
    last_day = end_day - timedelta(days=1)
    m_start, m_end = month_window(last_day)
    month_start = at(m_start, zone)
    companies = await company_figures(tx, start, end, month_start)
    costs = [
        float(c["cost_usd"]) / int(c["accepted"]) for c in companies if int(c["accepted"] or 0) > 0
    ]
    holding_median = median(costs) if costs else None
    emps = await employee_figures(
        tx,
        [c["id"] for c in companies],
        start,
        end,
        month_start,
        (m_end - m_start).days,
        (end_day - m_start).days if end_day <= m_end else (m_end - m_start).days,
    )
    star_rows = await tx.all(
        """SELECT s.employee_id, s.company_id, s.stars FROM people.stars s
           WHERE s.counted AND s.week >= :a AND s.week < :b""",
        a=start_day,
        b=end_day,
    )
    stars_of: dict[UUID, list[float]] = {}
    for s in star_rows:
        stars_of.setdefault(s["employee_id"], []).append(float(s["stars"]))
    previous = await tx.all(
        """SELECT data FROM people.star_rollups WHERE period = :p ORDER BY starts_on DESC LIMIT :n""",
        p=period,
        n=TREND,
    )
    company_rows: list[dict[str, Any]] = []
    inflation: list[str] = []
    for c in companies:
        mine = [
            v
            for e, vs in stars_of.items()
            if emps.get(e, {}).get("company_id") == c["id"]
            for v in vs
        ]
        people = round(sum(mine) / len(mine) * 20, 1) if mine else None
        waste_share = (
            float(c["waste"]) / float(c["run_tokens"]) if float(c["run_tokens"] or 0) > 0 else None
        )
        cost = float(c["cost_usd"]) / int(c["accepted"]) if int(c["accepted"] or 0) > 0 else None
        efficiency = company_efficiency(
            used=float(c["used_month"]),
            envelope=float(c["envelope"]) if c["envelope"] is not None else None,
            waste_share=waste_share,
            cost_per_accepted=cost,
            holding_median=holding_median,
        )
        challenges, compliance = await _oversight_parts(tx, c["id"], start, end)
        parts = {
            "kpi": None,  # no KPI store yet: left out (contract note)
            "challenges": challenges,
            "compliance": compliance,
            "people": people,
            "efficiency": efficiency,
        }
        score, cstars = company_score(parts)
        trend = [
            next(
                (x["score"] for x in p["data"].get("companies", []) if x["company"] == c["code"]),
                None,
            )
            for p in reversed(previous)
        ]
        company_rows.append(
            {
                "company": c["code"],
                "stars": cstars,
                "score": score,
                "parts": parts,
                "trend": [t for t in trend if t is not None]
                + ([score] if score is not None else []),
            }
        )
        if inflated(mine):
            inflation.append(c["code"])
    ranked = sorted(
        (r for r in company_rows if r["score"] is not None), key=lambda r: -float(r["score"])
    )
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    for r in company_rows:
        r.setdefault("rank", None)
    best = ranked[0]["company"] if ranked else None
    employees: list[dict[str, Any]] = []
    for emp_id, values in stars_of.items():
        e = emps.get(emp_id)
        if e is None:
            continue
        employees.append(
            {
                "code": e["code"],
                "company": next(c["code"] for c in companies if c["id"] == e["company_id"]),
                "title_fa": e["title_fa"],
                "stars": round(sum(values) / len(values), 2),
                "count": len(values),
                "efficiency": e["efficiency"],
            }
        )
    employees.sort(key=lambda x: (-x["stars"], x["code"]))
    for i, x in enumerate(employees, 1):
        x["rank_holding"] = i
        x["rank_company"] = 1 + sum(
            1 for y in employees if y["company"] == x["company"] and y["stars"] > x["stars"]
        )
        x["trend"] = [
            next(
                (y["stars"] for y in p["data"].get("employees", []) if y["code"] == x["code"]), None
            )
            for p in reversed(previous)
        ]
        x["trend"] = [t for t in x["trend"] if t is not None] + [x["stars"]]
    data = {"companies": company_rows, "employees": employees, "inflation": inflation}
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    await tx.exec(
        """INSERT INTO people.star_rollups (company_id, period, key, starts_on, ends_on, best_company, data)
           VALUES (:co, :p, :k, :a, :b, :best, CAST(:d AS jsonb))""",
        co=holding,
        p=period,
        k=key,
        a=start_day,
        b=end_day,
        best=best,
        d=json.dumps(data, ensure_ascii=False, default=float),
    )
    holding_code = await tx.scalar("SELECT code FROM core.companies WHERE id = :id", id=holding)
    await events.emit(
        tx,
        holding_code,
        "stars.rollup",
        f"{period}:{key}",
        {"period": period, "key": key, "best": best},
    )
    for code in inflation:
        await star_inflation(tx, code, period, key)
    return {"created": True, "best_company": best, "key": key, "data": data}


async def star_inflation(tx: Tx, company_code: str, period: str, key: str) -> None:
    """More than 70% fives: the overseer's finding (prompt 08 §2, fork P8a)
    when its table exists; until it is wired, the owner's report line.
    HOOK(oversight): the merge replaces the notification with finding.raise."""
    co = await tx.one("SELECT id FROM core.companies WHERE code = :c", c=company_code)
    await notify.raise_notification(
        tx,
        company_id=co["id"],
        company_code=company_code,
        level="report",
        title_fa=f"تورم ستاره در {company_code}: بیش از ۷۰٪ پنج ستاره ({period} {key})",
        body_fa="ناظر کل باید ستاره‌های این دوره را بازبینی کند (star.audit).",
        link_kind="stars",
        link_ref=f"{period}:{key}"[:100],
        source_kind="service",
        source_code="stars",
    )


# --------------------------------------------------------------- lessons --
LESSON_SQL = """
    SELECT l.*, c.code AS source_company,
           COALESCE((SELECT jsonb_agg(jsonb_build_object('company', ac.code, 'status', a.status,
                                                         'decision_ref', a.decision_ref, 'work_ref', a.work_ref)
                                      ORDER BY ac.code)
                     FROM knowledge.lesson_adoptions a JOIN core.companies ac ON ac.id = a.company_id
                     WHERE a.lesson_id = l.id), '[]') AS adoption
    FROM knowledge.lessons l JOIN core.companies c ON c.id = l.company_id
"""


async def write_lesson(
    tx: Tx,
    who: Principal,
    *,
    source_company: str,
    period: str,
    title_fa: str,
    body_md: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """A lesson from a company; every other active operating company's CEO
    gets a work item to consider adopting it (decision kind lesson_adoption)."""
    src = await tx.first(
        "SELECT id, code, kind FROM core.companies WHERE code = :c AND status = 'active'",
        c=source_company,
    )
    if src is None:
        raise ApiError(422, "validation_failed", fields={"source_company": "unknown company"})
    row = await tx.one(
        """INSERT INTO knowledge.lessons (company_id, period, title_fa, body_md, evidence, by_kind, by_code)
           VALUES (:co, :p, :t, :b, CAST(:ev AS jsonb), :k, :c) RETURNING id, ref""",
        co=src["id"],
        p=period,
        t=scrub(title_fa),
        b=scrub(body_md),
        ev=json.dumps(evidence, ensure_ascii=False),
        k=who.kind,
        c=who.code,
    )
    others = await tx.all(
        """SELECT c.id, c.code, (SELECT e.code FROM core.employees e
                                  WHERE e.company_id = c.id AND e.kind = 'ceo' AND e.status = 'active'
                                  ORDER BY e.hired_at LIMIT 1) AS ceo
           FROM core.companies c
           WHERE c.kind = 'company' AND c.status = 'active' AND c.id <> :src ORDER BY c.code""",
        src=src["id"],
    )
    system = Principal(kind="service", code="stars", role="service")
    for o in others:
        work_ref = None
        if o["ceo"]:
            w = await W.create(
                tx,
                system,
                company_id=o["id"],
                company_code=o["code"],
                title=f"پیشنهاد به‌کارگیری درس {row['ref']}: {title_fa}"[:300],
                brief=(
                    f"درس {row['ref']} از {src['code']} ({period}):\n\n{scrub(body_md)}\n\n"
                    "اگر برای شرکتت به کار میآید، با propose از نوع lesson_adoption "
                    f"(payload: lesson={row['ref']}, adopt, plan_md) پیشنهادش بده؛ اگر نه، دلیلش را بنویس."
                )[:20000],
                kind="one_off",
                priority="P3",
                assignee_code=o["ceo"],
            )
            work_ref = w["ref"]
        await tx.exec(
            """INSERT INTO knowledge.lesson_adoptions (lesson_id, lesson_ref, company_id, work_ref)
               VALUES (:l, :ref, :co, :w)""",
            l=row["id"],
            ref=row["ref"],
            co=o["id"],
            w=work_ref,
        )
    return await tx.one(LESSON_SQL + " WHERE l.id = :id", id=row["id"])


async def adoption_decided(
    tx: Tx, lesson_ref: str, company_id: UUID, status: str, decision_ref: str
) -> None:
    await tx.exec(
        """UPDATE knowledge.lesson_adoptions SET status = :st, decision_ref = :d, updated_at = now()
           WHERE lesson_ref = :ref AND company_id = :co""",
        st=status,
        d=decision_ref,
        ref=lesson_ref,
        co=company_id,
    )


# -------------------------------------------------------------- reminder --
async def remind(tx: Tx, saturday: date) -> list[str]:
    """Friday 18:00: each active operating company's CEO gets one work item
    "this week's stars" (once per week and company)."""
    system = Principal(kind="service", code="stars", role="service")
    title = f"ستاره‌های هفته‌ی {saturday.isoformat()}"
    made: list[str] = []
    for c in await tx.all(
        """SELECT c.id, c.code, (SELECT e.code FROM core.employees e
                                  WHERE e.company_id = c.id AND e.kind = 'ceo' AND e.status = 'active'
                                  ORDER BY e.hired_at LIMIT 1) AS ceo
           FROM core.companies c WHERE c.kind = 'company' AND c.status = 'active' ORDER BY c.code"""
    ):
        if not c["ceo"] or await tx.scalar(
            "SELECT 1 FROM work.work WHERE company_id = :co AND title = :t", co=c["id"], t=title
        ):
            continue
        w = await W.create(
            tx,
            system,
            company_id=c["id"],
            company_code=c["code"],
            title=title,
            brief=(
                f"هفته‌ی {saturday.isoformat()} تا جمعه: به هر کارمند شرکتت با star.give طبق آیین‌نامه‌ی "
                "ستاره (star.rubric) ۰ تا ۵ ستاره بده، با یک جمله دلیل و شاهد (O-…، W-…). "
                "معیار کارایی دست‌کم ۱۵٪ وزن دارد. برآیند شنبه ساعت ۸ بسته میشود."
            ),
            kind="one_off",
            priority="P3",
            assignee_code=c["ceo"],
        )
        made.append(w["ref"])
    return made
