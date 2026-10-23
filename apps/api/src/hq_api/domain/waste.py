"""The daily waste report (prompt 12 §8, contract §21.7). Code only, no model.

For one owner-local day, from the ledger (llm.calls) and the runs
(agents.runs, work.work): what was spent on nothing. Every category is
counted on its own (its tokens, dollars, count and the five largest items);
the day's waste is the union of the calls flagged by any of them, so a call
is never counted twice in the share.

  failed_runs       calls of runs that ended `failed` or `refused`
  cancelled_work    calls of runs whose work was later cancelled
  no_progress_runs  calls of `done` runs that left no deliverable and no work
                    event of the employee in the run (PR-022's definition)
  retry_loops       calls of runs on a work item that had >= 3 runs that day
                    and no progress on it that day
  router_errors     calls that failed (error, timeout, refusal) and still cost
  duplicate_calls   a call whose request hash was seen in the 10 minutes
                    before (the router keeps only the hash, never the text)
  cache_miss        an input above 10 000 tokens with a prefix hash seen in the
                    hour before, and no cache read
  over_model        a model above the default assignment of its task class
                    (tiers: haiku < sonnet < opus)

No prompt or reply text is read or stored: only counts, tokens, dollars,
codes, run ids and work refs. llm.waste_daily keeps one row per company and
day plus the holding's total (scope 'holding'); efficiency stars (§18.4) read
the same rows (`share_between`), so one day has one waste figure.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from hq_api import audit
from hq_api.db import Tx

CATEGORIES = (
    "failed_runs",
    "cancelled_work",
    "no_progress_runs",
    "retry_loops",
    "router_errors",
    "duplicate_calls",
    "cache_miss",
    "over_model",
)
TOP = 5
LOOP_RUNS = 3
DUPLICATE_WINDOW_S = 600
CACHE_INPUT = 10_000
CACHE_WINDOW_S = 3600
ALERT_SHARE = 0.15  # a share above this raises a `report` notification
ERROR_STATES = ("error", "timeout", "refusal")
TIERS = {"haiku": 1, "sonnet": 2, "opus": 3}

TOKENS = (
    "(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)"
    " + COALESCE(k.cache_read_tokens, 0) + COALESCE(k.cache_write_tokens, 0))"
)
USD = "(COALESCE(k.cost_usd, 0) + COALESCE(k.equiv_cost_usd, 0))"

# One row per call of the window, with what each rule needs (no text).
CALLS_SQL = f"""
    SELECT k.id, k.company_id, k.started_at, k.actor_ref, k.work_ref, k.task_class, k.model,
           k.status, k.input_tokens, COALESCE(k.cache_read_tokens, 0) AS cache_read,
           {TOKENS} AS tokens, {USD} AS usd,
           k.meta->>'run_id' AS run_id, k.meta->>'request_sha256' AS request_sha,
           k.meta->>'prefix_sha256' AS prefix_sha
    FROM llm.calls k
    WHERE k.started_at >= :s AND k.started_at < :e AND k.status <> 'running'
"""  # noqa: S608 - module constants only

RUNS_SQL = """
    SELECT r.id::text AS id, r.company_id, r.state, r.work_id, w.ref AS work_ref, w.status AS work_status,
           e.code AS employee, r.started_at, r.finished_at, r.queued_at,
           EXISTS (SELECT 1 FROM cartable.deliverables dl
                    WHERE dl.work_id = r.work_id AND dl.producer_id = r.employee_id
                      AND dl.created_at >= COALESCE(r.started_at, r.queued_at)
                      AND dl.created_at <= COALESCE(r.finished_at, now())) AS delivered,
           EXISTS (SELECT 1 FROM work.work_events ev
                    WHERE ev.work_id = r.work_id AND ev.actor_code = e.code
                      AND ev.at >= COALESCE(r.started_at, r.queued_at)
                      AND ev.at <= COALESCE(r.finished_at, now())) AS moved
    FROM agents.runs r
    JOIN core.employees e ON e.id = r.employee_id
    LEFT JOIN work.work w ON w.id = r.work_id
    WHERE r.id::text = ANY(:ids) OR (r.queued_at >= :s AND r.queued_at < :e)
"""


def tier(model: str | None) -> int | None:
    m = (model or "").lower()
    for name, t in TIERS.items():
        if name in m:
            return t
    return None


def day_window(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    return start, datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)


async def _zone(tx: Tx) -> ZoneInfo:
    tz = await tx.scalar("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    return ZoneInfo(str(tz))


async def _defaults(tx: Tx) -> dict[str, str | None]:
    """The default model of each task class (its own assignment, else the holding's)."""
    rows = await tx.all(
        "SELECT scope_type, scope_ref, model FROM llm.assignments WHERE scope_type IN ('task_class', 'holding')"
    )
    holding = next((r["model"] for r in rows if r["scope_type"] == "holding" and r["model"]), None)
    out: dict[str, str | None] = {"*": holding}
    for r in rows:
        if r["scope_type"] == "task_class" and r["model"]:
            out[r["scope_ref"]] = r["model"]
    return out


def classify(
    calls: list[dict[str, Any]],
    runs: dict[str, dict[str, Any]],
    defaults: dict[str, str | None],
) -> dict[str, set[Any]]:
    """Which calls each category flags (pure; ids of llm.calls rows)."""
    flagged: dict[str, set[Any]] = {c: set() for c in CATEGORIES}
    by_work: dict[Any, list[dict[str, Any]]] = {}
    for r in runs.values():
        if r["work_id"] is not None:
            by_work.setdefault(r["work_id"], []).append(r)
    loop_works = {
        w
        for w, rs in by_work.items()
        if len(rs) >= LOOP_RUNS and not any(x["delivered"] or x["moved"] for x in rs)
    }
    seen_request: dict[str, datetime] = {}
    seen_prefix: dict[str, datetime] = {}
    for c in sorted(calls, key=lambda x: x["started_at"]):
        run = runs.get(c["run_id"] or "")
        if run is not None:
            if run["state"] in ("failed", "refused"):
                flagged["failed_runs"].add(c["id"])
            if run["work_status"] == "cancelled":
                flagged["cancelled_work"].add(c["id"])
            if run["state"] == "done" and not run["delivered"] and not run["moved"]:
                flagged["no_progress_runs"].add(c["id"])
            if run["work_id"] in loop_works:
                flagged["retry_loops"].add(c["id"])
        if c["status"] in ERROR_STATES and (
            int(c["tokens"] or 0) > 0 or Decimal(c["usd"] or 0) > 0
        ):
            flagged["router_errors"].add(c["id"])
        at: datetime = c["started_at"]
        req = c["request_sha"]
        if req:
            before = seen_request.get(req)
            if before is not None and (at - before).total_seconds() <= DUPLICATE_WINDOW_S:
                flagged["duplicate_calls"].add(c["id"])
            seen_request[req] = at
        prefix = c["prefix_sha"]
        if prefix:
            before = seen_prefix.get(prefix)
            if (
                before is not None
                and (at - before).total_seconds() <= CACHE_WINDOW_S
                and int(c["input_tokens"] or 0) > CACHE_INPUT
                and int(c["cache_read"] or 0) == 0
            ):
                flagged["cache_miss"].add(c["id"])
            seen_prefix[prefix] = at
        default = defaults.get(c["task_class"]) or defaults.get("*")
        used, wanted = tier(c["model"]), tier(default)
        if used is not None and wanted is not None and used > wanted:
            flagged["over_model"].add(c["id"])
    return flagged


def summarise(
    calls: list[dict[str, Any]],
    runs: dict[str, dict[str, Any]],
    flagged: dict[str, set[Any]],
) -> dict[str, Any]:
    """Totals and the categories of one set of calls (one company, or all)."""
    by_id = {c["id"]: c for c in calls}
    total_tokens = sum(int(c["tokens"] or 0) for c in calls)
    total_usd = sum((Decimal(c["usd"] or 0) for c in calls), Decimal(0))
    union: set[Any] = set()
    items = []
    for cat in CATEGORIES:
        ids = [i for i in flagged[cat] if i in by_id]
        union.update(ids)
        mine = [by_id[i] for i in ids]
        run_ids = {c["run_id"] for c in mine if c["run_id"]}
        count = len(run_ids) if cat in CATEGORIES[:4] else len(mine)
        groups: dict[tuple[Any, ...], int] = {}
        for c in mine:
            run = runs.get(c["run_id"] or "")
            key = (
                c["actor_ref"],
                c["run_id"],
                c["work_ref"] or (run or {}).get("work_ref"),
            )
            groups[key] = groups.get(key, 0) + int(c["tokens"] or 0)
        top = [
            {
                k: v
                for k, v in {
                    "employee": g[0],
                    "run_id": g[1],
                    "work_ref": g[2],
                    "tokens": t,
                }.items()
                if v is not None
            }
            for g, t in sorted(groups.items(), key=lambda x: (-x[1], str(x[0])))[:TOP]
        ]
        items.append(
            {
                "category": cat,
                "tokens": sum(int(c["tokens"] or 0) for c in mine),
                "usd": str(sum((Decimal(c["usd"] or 0) for c in mine), Decimal(0))),
                "count": count,
                "top": top,
            }
        )
    waste = [by_id[i] for i in union]
    waste_tokens = sum(int(c["tokens"] or 0) for c in waste)
    waste_usd = sum((Decimal(c["usd"] or 0) for c in waste), Decimal(0))
    return {
        "total_tokens": total_tokens,
        "total_usd": total_usd,
        "waste_tokens": waste_tokens,
        "waste_usd": waste_usd,
        "share": round(waste_tokens / total_tokens, 6) if total_tokens else 0.0,
        "items": items,
    }


async def compute(tx: Tx, day: date) -> dict[UUID | None, dict[str, Any]]:
    """{company_id: summary, ..., None: the holding total} for one day."""
    zone = await _zone(tx)
    s, e = day_window(day, zone)
    calls = [dict(r) for r in await tx.all(CALLS_SQL, s=s, e=e)]
    ids = sorted({c["run_id"] for c in calls if c["run_id"]})
    runs = {r["id"]: dict(r) for r in await tx.all(RUNS_SQL, ids=ids, s=s, e=e)}
    flagged = classify(calls, runs, await _defaults(tx))
    out: dict[UUID | None, dict[str, Any]] = {None: summarise(calls, runs, flagged)}
    companies = await tx.all("SELECT id FROM core.companies WHERE status <> 'archived'")
    for co in companies:
        mine = [c for c in calls if c["company_id"] == co["id"]]
        out[co["id"]] = summarise(mine, runs, flagged)
    return out


async def _vs_7d(tx: Tx, day: date, scope: str, company_id: UUID, share: float) -> float | None:
    """The relative change of the share against the 7 days before (stored rows)."""
    avg = await tx.scalar(
        """SELECT avg(share) FROM llm.waste_daily
           WHERE scope = :sc AND company_id = :co AND day >= :a AND day < :d""",
        sc=scope,
        co=company_id,
        a=day - timedelta(days=7),
        d=day,
    )
    if avg is None or float(avg) == 0:
        return None
    return round((share - float(avg)) / float(avg), 6)


async def store(tx: Tx, day: date) -> list[dict[str, Any]]:
    """Compute and keep the day (a re-run replaces the day's figures)."""
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
    figures = await compute(tx, day)
    rows = []
    for co, f in figures.items():
        scope = "holding" if co is None else "company"
        cid = holding if co is None else co
        vs = await _vs_7d(tx, day, scope, cid, float(f["share"]))
        row = await tx.one(
            """INSERT INTO llm.waste_daily (company_id, scope, day, total_tokens, total_usd, waste_tokens,
                   waste_usd, share, vs_7d, items)
               VALUES (:co, :sc, :d, :tt, :tu, :wt, :wu, :sh, :vs, CAST(:items AS jsonb))
               ON CONFLICT (day, scope, company_id) DO UPDATE SET total_tokens = EXCLUDED.total_tokens,
                   total_usd = EXCLUDED.total_usd, waste_tokens = EXCLUDED.waste_tokens,
                   waste_usd = EXCLUDED.waste_usd, share = EXCLUDED.share, vs_7d = EXCLUDED.vs_7d,
                   items = EXCLUDED.items, computed_at = now()
               RETURNING *""",
            co=cid,
            sc=scope,
            d=day,
            tt=f["total_tokens"],
            tu=f["total_usd"],
            wt=f["waste_tokens"],
            wu=f["waste_usd"],
            sh=f["share"],
            vs=vs,
            items=json.dumps(f["items"], ensure_ascii=False),
        )
        rows.append(row)
    if holding is not None:
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=holding,
            action="waste.day",
            action_class="A1",
            target_kind="waste",
            target_ref=day.isoformat(),
            summary=f"{len(rows)} row(s), figures only",
        )
    return rows


def render(row: dict[str, Any], company: str | None) -> dict[str, Any]:
    """WasteDay (contract §21.7) from a stored row or a computed summary."""
    return {
        "day": row["day"],
        "company": company,
        "total_tokens": int(row["total_tokens"]),
        "total_usd": Decimal(row["total_usd"]),
        "waste_tokens": int(row["waste_tokens"]),
        "waste_usd": Decimal(row["waste_usd"]),
        "share": float(row["share"]),
        "vs_7d": float(row["vs_7d"]) if row.get("vs_7d") is not None else None,
        "items": list(row["items"]),
    }


async def day_of(tx: Tx, day: date, company_id: UUID | None) -> dict[str, Any]:
    """One day: the stored row, else computed now (the same code, not stored:
    the daily job does not run while the holding is locked)."""
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1")
    scope = "holding" if company_id is None else "company"
    row = await tx.first(
        "SELECT * FROM llm.waste_daily WHERE day = :d AND scope = :sc AND company_id = :co",
        d=day,
        sc=scope,
        co=holding if company_id is None else company_id,
    )
    if row is not None:
        return row
    f = (await compute(tx, day)).get(company_id) or summarise(
        [], {}, {c: set() for c in CATEGORIES}
    )
    return {"day": day, **f, "vs_7d": None}


async def shares_between(tx: Tx, start_day: date, end_day: date) -> dict[UUID, float | None]:
    """Each company's waste share of [start_day, end_day), from the same daily
    figures as the report (efficiency stars, §18.4): the stored day, else the
    day computed now. None for a company without tokens."""
    totals: dict[UUID, list[int]] = {}
    day = start_day
    while day < end_day:
        stored = await tx.all(
            "SELECT company_id, total_tokens, waste_tokens FROM llm.waste_daily"
            " WHERE day = :d AND scope = 'company'",
            d=day,
        )
        if stored:
            per = {
                r["company_id"]: (int(r["total_tokens"]), int(r["waste_tokens"])) for r in stored
            }
        else:
            per = {
                co: (int(f["total_tokens"]), int(f["waste_tokens"]))
                for co, f in (await compute(tx, day)).items()
                if co is not None
            }
        for co, (t, w) in per.items():
            acc = totals.setdefault(co, [0, 0])
            acc[0] += t
            acc[1] += w
        day += timedelta(days=1)
    return {co: (w / t if t else None) for co, (t, w) in totals.items()}


def morning_line(f: dict[str, Any]) -> str:
    """One line for the morning report (rule-only)."""
    if not int(f["total_tokens"]):
        return "- **هدررفت دیروز:** مصرفی ثبت نشد."
    top = max(f["items"], key=lambda i: int(i["tokens"]), default=None)
    pct = round(float(f["share"]) * 100, 1)
    usd = Decimal(f["waste_usd"]).quantize(Decimal("0.01"))
    line = f"- **هدررفت دیروز:** {f['waste_tokens']} توکن (${usd})، {pct}% از کل روز"
    if top is not None and int(top["tokens"]):
        line += f"؛ بیشترین: {top['category']}"
    return line
