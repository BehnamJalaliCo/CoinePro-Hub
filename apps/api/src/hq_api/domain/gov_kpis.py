"""The three cards and the live scorecard (prompt 11 §4, contract §20.4, M2).

KPI       governance.kpis: a definition per company and key, on one of the
          three cards (stability, growth, safety_cost); its source is a query
          of the closed REGISTRY below (reviewed code, never SQL from data) or
          `manual` (kpi.record only, with a source)
values    governance.kpi_values, append-only: the collector (every 15 minutes,
          no model) writes a value when it changed or the last one is an hour
          old; the definition row caches the last value
states    ok | stale (older than freshness_hours: «قدیمی») | no_source (no
          value: a query whose source is not built or has no data, a manual
          KPI never recorded). A missing value is never zero.
holding   the holding's own KPIs plus the companies' KPIs aggregated by key
          with each KPI's `aggregate` (sum, avg, min, max)
score     attainment(): the "KPI" part (35%) of the company score: the
          weighted progress of the active quarter's key results when an OKR
          is active (gov_okr), else the share of scorecard KPIs at target
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gov_common as G
from hq_api.errors import ApiError
from hq_api.principal import Principal

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "kpis" / "standard.yaml"
CARDS = ("stability", "growth", "safety_cost")
TREND_DAYS = 30
APPEND_EVERY = timedelta(hours=1)  # an unchanged value is written at most hourly
KEY = r"^[a-z][a-z0-9_.]{1,60}$"


@dataclass
class Measure:
    value: float
    at: datetime
    ref: str
    note: str = ""

    def source_ref(self, query: str) -> dict[str, str]:
        return {"kind": "query", "ref": f"{query}:{self.ref}"[:500], "note": self.note[:1000]}


@dataclass
class Ctx:
    tx: Tx
    company_id: UUID
    code: str
    now: datetime
    tz: str


QueryFn = Callable[[Ctx], Awaitable[Measure | None]]


@dataclass(frozen=True)
class Query:
    key: str
    fn: QueryFn
    needs: tuple[str, ...] = ()  # tables that must exist (prompt 10's)
    holding: bool = False  # a query of the holding's own card


REGISTRY: dict[str, Query] = {}


def query(
    key: str, *, needs: tuple[str, ...] = (), holding: bool = False
) -> Callable[[QueryFn], QueryFn]:
    def register(fn: QueryFn) -> QueryFn:
        REGISTRY[key] = Query(key, fn, needs, holding)
        return fn

    return register


async def available(tx: Tx) -> set[str]:
    """The registry keys whose sources exist in this database."""
    out = set()
    for key, q in REGISTRY.items():
        if all([await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=t) for t in q.needs]):
            out.add(key)
    return out


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


async def _month_start(c: Ctx) -> datetime:
    return G.local_midnight(G.jalali_month_start(G.today(c.tz, c.now)), c.tz)


async def _has_sites(c: Ctx) -> bool:
    return bool(
        await c.tx.scalar(
            "SELECT 1 FROM ops.sites WHERE company_id = :co AND enabled AND NOT canary LIMIT 1",
            co=c.company_id,
        )
    )


# ---------------------------------------------------------------- health --
@query("health.uptime_24h")
async def uptime_24h(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT count(*) FILTER (WHERE k.ok) AS ok, count(*) AS n, max(k.at) AS at
           FROM ops.checks k JOIN ops.sites s ON s.id = k.site_id
           WHERE k.company_id = :co AND s.enabled AND NOT s.canary AND k.at > :since""",
        co=c.company_id,
        since=c.now - timedelta(hours=24),
    )
    if r is None or not r["n"]:
        return None
    return Measure(
        round(100.0 * r["ok"] / r["n"], 3), r["at"], "ops.checks:24h", f"{r['n']} checks"
    )


@query("health.p95_latency_ms")
async def p95_latency(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY k.latency_ms) AS p95, max(k.at) AS at
           FROM ops.checks k JOIN ops.sites s ON s.id = k.site_id
           WHERE k.company_id = :co AND s.enabled AND NOT s.canary AND k.ok AND k.latency_ms IS NOT NULL
             AND k.at > :since""",
        co=c.company_id,
        since=c.now - timedelta(hours=24),
    )
    if r is None or r["p95"] is None:
        return None
    return Measure(round(float(r["p95"]), 1), r["at"], "ops.checks:24h")


@query("health.open_incidents")
async def open_incidents(c: Ctx) -> Measure | None:
    if not await _has_sites(c):
        return None
    n = await c.tx.scalar(
        "SELECT count(*) FROM ops.incidents WHERE company_id = :co AND closed_at IS NULL",
        co=c.company_id,
    )
    return Measure(float(n), c.now, "ops.incidents:open")


@query("health.tls_min_days")
async def tls_min_days(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT min(x.days) AS days, max(x.at) AS at FROM (
               SELECT DISTINCT ON (k.site_id) k.tls_days_left AS days, k.at
               FROM ops.checks k JOIN ops.sites s ON s.id = k.site_id
               WHERE k.company_id = :co AND s.enabled AND NOT s.canary AND k.tls_days_left IS NOT NULL
                 AND k.at > :since
               ORDER BY k.site_id, k.at DESC) x""",
        co=c.company_id,
        since=c.now - timedelta(hours=24),
    )
    if r is None or r["days"] is None:
        return None
    return Measure(float(r["days"]), r["at"], "ops.checks:tls")


# -------------------------------------------------------------- treasury --
async def _cost_since(c: Ctx, since: datetime, *, every_company: bool = False) -> float:
    v = await c.tx.scalar(
        """SELECT coalesce(sum(cost_usd), 0) FROM llm.calls
           WHERE started_at >= :s AND (CAST(:all AS boolean) OR company_id = :co)""",
        s=since,
        all=every_company,
        co=c.company_id,
    )
    return float(v or 0)


@query("treasury.cost_month_usd")
async def cost_month(c: Ctx) -> Measure:
    start = await _month_start(c)
    return Measure(round(await _cost_since(c, start), 6), c.now, f"llm.calls:{start.date()}..")


@query("treasury.agents_cost_month_usd", holding=True)
async def agents_cost_month(c: Ctx) -> Measure:
    start = await _month_start(c)
    v = await _cost_since(c, start, every_company=True)
    return Measure(round(v, 6), c.now, f"llm.calls:all:{start.date()}..")


@query("treasury.budget_use_pct")
async def budget_use(c: Ctx) -> Measure | None:
    b = await c.tx.first(
        """SELECT usd_limit, token_limit FROM llm.budgets
           WHERE company_id = :co AND scope_type = 'company' AND scope_ref = :code AND period = 'month'
             AND enabled""",
        co=c.company_id,
        code=c.code,
    )
    if b is None or (not b["usd_limit"] and not b["token_limit"]):
        return None
    start = await _month_start(c)
    if b["usd_limit"]:
        used = await _cost_since(c, start)
        return Measure(round(100.0 * used / float(b["usd_limit"]), 2), c.now, "llm.budgets:usd")
    tokens = await c.tx.scalar(
        """SELECT coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0) FROM llm.calls
           WHERE company_id = :co AND started_at >= :s""",
        co=c.company_id,
        s=start,
    )
    return Measure(
        round(100.0 * float(tokens) / float(b["token_limit"]), 2), c.now, "llm.budgets:tokens"
    )


@query("treasury.cost_per_accepted")
async def cost_per_accepted(c: Ctx) -> Measure | None:
    start = await _month_start(c)
    accepted = await c.tx.scalar(
        """SELECT count(*) FROM cartable.deliverables dl
           WHERE dl.company_id = :co AND dl.created_at >= :s
             AND (SELECT x.score FROM cartable.ratings x WHERE x.deliverable_id = dl.id
                  ORDER BY x.version_no DESC LIMIT 1) >= 6""",
        co=c.company_id,
        s=start,
    )
    if not accepted:
        return None
    cost = await _cost_since(c, start)
    return Measure(
        round(cost / int(accepted), 6), c.now, "llm.calls/cartable.ratings", f"{accepted} accepted"
    )


# ------------------------------------------------------- work, oversight --
@query("work.on_time_rate")
async def on_time(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT count(*) FILTER (WHERE closed_at <= due_at) AS ok, count(*) AS n FROM work.work
           WHERE company_id = :co AND status = 'done' AND due_at IS NOT NULL AND closed_at > :since""",
        co=c.company_id,
        since=c.now - timedelta(days=30),
    )
    if r is None or not r["n"]:
        return None
    return Measure(
        round(100.0 * r["ok"] / r["n"], 2), c.now, "work.work:30d", f"{r['n']} with a due date"
    )


@query("work.overdue_open")
async def overdue_open(c: Ctx) -> Measure:
    n = await c.tx.scalar(
        """SELECT count(*) FROM work.work WHERE company_id = :co AND kind <> 'recurring'
             AND status IN ('queued', 'in_progress', 'waiting') AND due_at < :now""",
        co=c.company_id,
        now=c.now,
    )
    return Measure(float(n), c.now, "work.work:overdue")


@query("oversight.compliance")
async def compliance(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT score, computed_at, day FROM oversight.compliance
           WHERE company_id = :co ORDER BY day DESC LIMIT 1""",
        co=c.company_id,
    )
    if r is None:
        return None
    return Measure(float(r["score"]), r["computed_at"], f"oversight.compliance:{r['day']}")


@query("oversight.findings_open_high")
async def findings_high(c: Ctx) -> Measure:
    n = await c.tx.scalar(
        """SELECT count(*) FROM oversight.findings WHERE company_id = :co
             AND status NOT IN ('verified', 'closed') AND severity IN ('high', 'critical')""",
        co=c.company_id,
    )
    return Measure(float(n), c.now, "oversight.findings:open")


@query("stars.company_score")
async def company_score(c: Ctx) -> Measure | None:
    rows = await c.tx.all(
        """SELECT key, data, created_at FROM people.star_rollups WHERE period = 'week'
           ORDER BY starts_on DESC LIMIT 1"""
    )
    for r in rows:
        for x in (r["data"] or {}).get("companies") or []:
            if x.get("company") == c.code and x.get("score") is not None:
                return Measure(
                    float(x["score"]), r["created_at"], f"people.star_rollups:{r['key']}"
                )
    return None


# --------------------------------------------- prompt 10: revenue, funnel --
async def _revenue(c: Ctx, column: str) -> Measure | None:
    end = G.today("Asia/Shanghai", c.now)  # settled days are T+1 at UTC+8 (prompt 10 §2)
    start = end - timedelta(days=7)
    r = await c.tx.first(
        f"""SELECT sum({column}) AS v, count(*) AS days, max(pulled_at) AS at FROM revenue.days
            WHERE company_id = :co AND complete AND day >= :a AND day < :b""",  # noqa: S608 - a fixed column
        co=c.company_id,
        a=start,
        b=end,
    )
    if r is None or not r["days"]:
        return None  # no account, or no complete day: not connected, never zero
    return Measure(
        float(r["v"] or 0), r["at"], f"revenue.days:{start}..{end}", f"{r['days']} complete days"
    )


@query("revenue.commission_7d_usdt", needs=("revenue.days",))
async def commission_7d(c: Ctx) -> Measure | None:
    return await _revenue(c, "commission_usdt")


@query("revenue.new_invitees_7d", needs=("revenue.days",))
async def invitees_7d(c: Ctx) -> Measure | None:
    return await _revenue(c, "new_invitees")


async def _funnel(c: Ctx) -> dict[str, Any] | None:
    rows = await c.tx.all(
        """SELECT stage, sum(count) AS n, max(updated_at) AS at FROM growth.funnel_days
           WHERE company_id = :co AND day >= :a GROUP BY stage""",
        co=c.company_id,
        a=G.today(c.tz, c.now) - timedelta(days=7),
    )
    if not rows:
        return None
    out: dict[str, Any] = {r["stage"]: float(r["n"]) for r in rows}
    out["_at"] = max(r["at"] for r in rows)
    return out


@query("funnel.signups_7d", needs=("growth.funnel_days",))
async def signups_7d(c: Ctx) -> Measure | None:
    f = await _funnel(c)
    if f is None or "signup" not in f:
        return None
    return Measure(f["signup"], f["_at"], "growth.funnel_days:7d")


@query("funnel.conversion_7d", needs=("growth.funnel_days",))
async def conversion_7d(c: Ctx) -> Measure | None:
    f = await _funnel(c)
    if f is None or not f.get("signup"):
        return None
    return Measure(
        round(100.0 * f.get("vip_active", 0.0) / f["signup"], 2), f["_at"], "growth.funnel_days:7d"
    )


@query("support.csat_30d", needs=("support.conversations",))
async def csat_30d(c: Ctx) -> Measure | None:
    r = await c.tx.first(
        """SELECT avg(csat) AS v, count(*) AS n, max(updated_at) AS at FROM support.conversations
           WHERE company_id = :co AND csat IS NOT NULL AND NOT mystery AND updated_at > :since""",
        co=c.company_id,
        since=c.now - timedelta(days=30),
    )
    if r is None or not r["n"]:
        return None
    return Measure(
        round(float(r["v"]), 2), r["at"], "support.conversations:30d", f"{r['n']} answers"
    )


# --------------------------------------------------------- the hub itself --
async def _hub(c: Ctx) -> dict[str, Any] | None:
    return await c.tx.first(
        "SELECT at, data FROM ops.hub_health WHERE company_id = :co", co=c.company_id
    )


@query("hub.services_up_pct", holding=True)
async def services_up(c: Ctx) -> Measure | None:
    h = await _hub(c)
    raw = str(((h or {}).get("data") or {}).get("services_up") or "")
    if h is None or "/" not in raw:
        return None
    up, total = (G.number(x) for x in raw.split("/", 1))
    if not total:
        return None
    return Measure(round(100.0 * float(up or 0) / float(total), 2), h["at"], "ops.hub_health", raw)


@query("hub.backup_age_hours", holding=True)
async def backup_age(c: Ctx) -> Measure | None:
    h = await _hub(c)
    age = (((h or {}).get("data") or {}).get("backup") or {}).get("age_hours")
    if h is None or G.number(age) is None:
        return None
    return Measure(float(G.number(age) or 0), h["at"], "ops.hub_health:backup")


# ------------------------------------------------------------------- seed --
def load_seed(path: Path = SEED_FILE) -> dict[str, dict[str, list[dict[str, Any]]]]:
    data: dict[str, dict[str, list[dict[str, Any]]]] = (
        yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    )
    return data


def _definition(k: dict[str, Any], card: str, origin: str) -> dict[str, Any]:
    manual = k.get("source") == "manual"
    return {
        "key": k["key"],
        "card": card,
        "name_fa": k["name_fa"],
        "unit": k.get("unit") or "",
        "direction": k.get("direction", "up"),
        "source": {"kind": "manual"} if manual else {"kind": "query", "query": k["key"]},
        "freshness_hours": int(k.get("freshness_hours", 24)),
        "target": k.get("target"),
        "target_max": k.get("target_max"),
        "scorecard": bool(k.get("scorecard", False)),
        "aggregate": k.get("aggregate", "sum"),
        "origin": origin,
    }


async def seed_company(tx: Tx, company_id: UUID, kind: str) -> int:
    """The company's first KPIs (once): a founding's proposed KPIs (manual,
    growth card) with the standard stability and safety cards, else the whole
    standard set. Only registry queries are seeded."""
    if await tx.scalar("SELECT 1 FROM governance.kpi_sets WHERE company_id = :co", co=company_id):
        return 0
    seed = load_seed()["holding" if kind == "holding" else "company"]
    founding = await tx.scalar(
        """SELECT proposal->'kpis' FROM core.foundings
           WHERE new_company_id = :co AND jsonb_typeof(proposal->'kpis') = 'array'
             AND jsonb_array_length(proposal->'kpis') > 0
           ORDER BY created_at DESC LIMIT 1""",
        co=company_id,
    )
    rows: list[dict[str, Any]] = []
    for card in CARDS:
        if card == "growth" and founding:
            for i, k in enumerate(founding[:30], 1):
                rows.append(
                    _definition(
                        {"key": f"founding.k{i}", "source": "manual", "name_fa": str(k.get("name_fa"))[:200],
                         "target": G.number(k.get("target")), "freshness_hours": 168, "scorecard": True},
                        "growth",
                        "founding",
                    )
                )  # fmt: skip
            continue
        for k in seed.get(card) or []:
            if k.get("source") != "manual" and k["key"] not in REGISTRY:
                continue  # never a source the registry does not have
            rows.append(_definition(k, card, "standard"))
    await tx.exec(
        "INSERT INTO governance.kpi_sets (company_id, seeded_from) VALUES (:co, :f)",
        co=company_id,
        f="founding" if founding else "standard",
    )
    for r in rows:
        await _insert(tx, company_id, r)
    return len(rows)


async def _insert(tx: Tx, company_id: UUID, r: dict[str, Any]) -> dict[str, Any]:
    return await tx.one(
        """INSERT INTO governance.kpis (company_id, key, card, name_fa, unit, direction, source,
               freshness_hours, target, target_max, scorecard, aggregate, origin)
           VALUES (:co, :key, :card, :name_fa, :unit, :direction, CAST(:source AS jsonb), :freshness_hours,
                   :target, :target_max, :scorecard, :aggregate, :origin)
           RETURNING *""",
        co=company_id,
        **{**r, "source": json.dumps(r["source"])},
    )


async def seed_all(tx: Tx) -> int:
    n = 0
    for c in await tx.all(
        "SELECT id, kind FROM core.companies WHERE status = 'active' ORDER BY code"
    ):
        n += await seed_company(tx, c["id"], c["kind"])
    return n


# ---------------------------------------------------------------- collect --
async def _store(
    tx: Tx,
    k: dict[str, Any],
    value: float,
    at: datetime,
    source_ref: dict[str, Any],
    by: tuple[str, str],
) -> bool:
    """Cache the value on the definition; append it when it changed or the
    last appended one is an hour old. True when a row was appended."""
    last = await tx.first(
        "SELECT value, at FROM governance.kpi_values WHERE kpi_id = :k ORDER BY at DESC LIMIT 1",
        k=k["id"],
    )
    append = last is None or float(last["value"]) != value or at - last["at"] >= APPEND_EVERY
    if append:
        await tx.exec(
            """INSERT INTO governance.kpi_values (company_id, kpi_id, at, value, source_ref, recorded_by_kind,
                   recorded_by_code)
               VALUES (:co, :k, :at, :v, CAST(:ref AS jsonb), :bk, :bc)""",
            co=k["company_id"],
            k=k["id"],
            at=at,
            v=value,
            ref=json.dumps(source_ref, ensure_ascii=False),
            bk=by[0],
            bc=by[1],
        )
    if k["last_at"] is None or at >= k["last_at"]:
        await tx.exec(
            """UPDATE governance.kpis SET last_value = :v, last_at = :at, last_source_ref = CAST(:ref AS jsonb),
                   stale_since = NULL WHERE id = :k""",
            v=value,
            at=at,
            ref=json.dumps(source_ref, ensure_ascii=False),
            k=k["id"],
        )
    return append


async def collect(tx: Tx, now: datetime | None = None) -> dict[str, Any]:
    """Every active company's query KPIs, by code (no model, no outside call);
    then the stale marks (an event once per stale episode)."""
    now = now or datetime.now(UTC)
    tz = await G.owner_tz(tx)
    have = await available(tx)
    measured = appended = 0
    no_source: list[str] = []
    stale: list[str] = []
    for co in await tx.all(
        "SELECT id, code, kind FROM core.companies WHERE status = 'active' ORDER BY code"
    ):
        await seed_company(tx, co["id"], co["kind"])
        ctx = Ctx(tx, co["id"], co["code"], now, tz)
        for k in await tx.all(
            "SELECT * FROM governance.kpis WHERE company_id = :co AND status = 'active' ORDER BY key",
            co=co["id"],
        ):
            src = k["source"] or {}
            if src.get("kind") == "query":
                q = REGISTRY.get(str(src.get("query")))
                m = await q.fn(ctx) if q is not None and q.key in have else None
                if q is None or m is None:
                    no_source.append(f"{co['code']}:{k['key']}")
                else:
                    measured += 1
                    appended += await _store(
                        tx, k, float(m.value), m.at, m.source_ref(q.key), ("rule", "kpi-collector")
                    )
                    k = await tx.one("SELECT * FROM governance.kpis WHERE id = :id", id=k["id"])
            if k["last_at"] is not None and now - k["last_at"] > timedelta(
                hours=k["freshness_hours"]
            ):
                if k["stale_since"] is None:
                    await tx.exec(
                        "UPDATE governance.kpis SET stale_since = :n WHERE id = :id",
                        n=now,
                        id=k["id"],
                    )
                    await events.emit(
                        tx, co["code"], "kpi.stale", k["key"],
                        {"card": k["card"], "at": k["last_at"].isoformat(), "freshness_hours": k["freshness_hours"]},
                    )  # fmt: skip
                stale.append(f"{co['code']}:{k['key']}")
    return {"measured": measured, "appended": appended, "no_source": len(no_source), "stale": stale}


# -------------------------------------------------------------- the cards --
class CardKpi(BaseModel):
    key: str
    name_fa: str
    unit: str
    card: str
    direction: str
    value: float | None
    at: datetime | None
    source_ref: dict[str, Any] | None
    target: float | None
    target_max: float | None = None
    trend: list[float | None]
    state: str  # ok | stale | no_source


class Card(BaseModel):
    company: str
    card: str
    kpis: list[CardKpi]


class ScoreRow(BaseModel):
    company: str
    name_fa: str | None = None
    kpis: list[CardKpi]


class Kpi(BaseModel):
    id: UUID
    company: str
    key: str
    card: str
    name_fa: str
    unit: str
    direction: str
    source: dict[str, Any]
    freshness_hours: int
    target: float | None
    target_max: float | None
    scorecard: bool
    aggregate: str
    status: str
    version: int


class KpiSet(BaseModel):
    company: str
    version: int
    kpis: list[Kpi]


class KpiValue(BaseModel):
    kpi: str
    at: datetime
    value: float
    source_ref: dict[str, Any]


def state_of(k: dict[str, Any], now: datetime, have: set[str]) -> str:
    src = k["source"] or {}
    if k["last_at"] is None or (src.get("kind") == "query" and src.get("query") not in have):
        return "no_source"
    if now - k["last_at"] > timedelta(hours=k["freshness_hours"]):
        return "stale"
    return "ok"


async def trends(
    tx: Tx, kpi_ids: list[UUID], tz: str, now: datetime
) -> dict[UUID, list[float | None]]:
    """30 days per KPI: the day's last value, null on a day without one."""
    days = [G.today(tz, now) - timedelta(days=i) for i in range(TREND_DAYS - 1, -1, -1)]
    out: dict[UUID, list[float | None]] = {k: [None] * TREND_DAYS for k in kpi_ids}
    if not kpi_ids:
        return out
    rows = await tx.all(
        """SELECT kpi_id, (at AT TIME ZONE :tz)::date AS d, (array_agg(value ORDER BY at DESC))[1] AS v
           FROM governance.kpi_values WHERE kpi_id = ANY(:ids) AND at >= :since
           GROUP BY kpi_id, (at AT TIME ZONE :tz)::date""",
        tz=tz,
        ids=kpi_ids,
        since=G.local_midnight(days[0], tz),
    )
    index = {d: i for i, d in enumerate(days)}
    for r in rows:
        i = index.get(r["d"])
        if i is not None:
            out[r["kpi_id"]][i] = float(r["v"])
    return out


def card_kpi(
    k: dict[str, Any], trend: list[float | None], now: datetime, have: set[str]
) -> CardKpi:
    state = state_of(k, now, have)
    return CardKpi(
        key=k["key"],
        name_fa=k["name_fa"],
        unit=k["unit"],
        card=k["card"],
        direction=k["direction"],
        value=G.num(k["last_value"]) if state != "no_source" else None,
        at=k["last_at"] if state != "no_source" else None,
        source_ref=k["last_source_ref"] if state != "no_source" else None,
        target=G.num(k["target"]),
        target_max=G.num(k["target_max"]),
        trend=trend,
        state=state,
    )


async def company_kpis(
    tx: Tx, company_id: UUID, *, scorecard_only: bool = False
) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in await tx.all(
            """SELECT * FROM governance.kpis WHERE company_id = :co AND status = 'active'
                 AND (NOT CAST(:sc AS boolean) OR scorecard) ORDER BY card, key""",
            co=company_id,
            sc=scorecard_only,
        )
    ]


def _aggregate(agg: str, values: list[float]) -> float:
    if agg == "avg":
        return round(sum(values) / len(values), 6)
    if agg == "min":
        return min(values)
    if agg == "max":
        return max(values)
    return round(sum(values), 6)


async def cards(
    tx: Tx, company: Any, now: datetime | None = None, *, seed: bool = True
) -> list[Card]:
    """The three cards of a company, or of the holding (its own KPIs plus
    every operating company's, aggregated by key). `seed`: a company without
    KPIs gets the standard set first (not in an agent's read-only read)."""
    now = now or datetime.now(UTC)
    tz = await G.owner_tz(tx)
    have = await available(tx)
    if seed:
        await seed_company(tx, company.id, company.kind)
    own = await company_kpis(tx, company.id)
    trend = await trends(tx, [k["id"] for k in own], tz, now)
    by_card: dict[str, list[CardKpi]] = {c: [] for c in CARDS}
    for k in own:
        by_card[k["card"]].append(card_kpi(k, trend[k["id"]], now, have))
    if company.kind == "holding":
        for item in await aggregated(tx, company.id, tz, now, have):
            by_card[item.card].append(item)
    return [Card(company=company.code, card=c, kpis=by_card[c]) for c in CARDS]


async def aggregated(
    tx: Tx, holding_id: UUID, tz: str, now: datetime, have: set[str]
) -> list[CardKpi]:
    rows = [
        dict(r)
        for r in await tx.all(
            """SELECT k.* FROM governance.kpis k JOIN core.companies c ON c.id = k.company_id
               WHERE c.kind <> 'holding' AND c.status = 'active' AND k.status = 'active'
               ORDER BY k.key, c.code"""
        )
    ]
    trend = await trends(tx, [r["id"] for r in rows], tz, now)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["key"], []).append(r)
    out: list[CardKpi] = []
    for key, ks in groups.items():
        first = ks[0]
        states = [state_of(k, now, have) for k in ks]
        live = [k for k, s in zip(ks, states, strict=True) if s != "no_source"]
        agg = first["aggregate"]
        days: list[float | None] = []
        for i in range(TREND_DAYS):
            vals = [trend[k["id"]][i] for k in ks if trend[k["id"]][i] is not None]
            days.append(_aggregate(agg, [v for v in vals if v is not None]) if vals else None)
        targets = {G.num(k["target"]) for k in ks}
        out.append(
            CardKpi(
                key=key,
                name_fa=first["name_fa"],
                unit=first["unit"],
                card=first["card"],
                direction=first["direction"],
                value=_aggregate(agg, [float(k["last_value"]) for k in live]) if live else None,
                at=min(k["last_at"] for k in live) if live else None,
                source_ref={"kind": "aggregate", "ref": f"{agg}:{len(live)}", "note": "companies"}
                if live
                else None,
                target=targets.pop() if len(targets) == 1 and agg != "sum" else None,
                trend=days,
                state="no_source" if not live else ("stale" if "stale" in states else "ok"),
            )
        )
    return out


async def scorecards(tx: Tx, companies: list[Any], now: datetime | None = None) -> list[ScoreRow]:
    now = now or datetime.now(UTC)
    tz = await G.owner_tz(tx)
    have = await available(tx)
    out = []
    for co in companies:
        await seed_company(tx, co.id, co.kind)
        ks = await company_kpis(tx, co.id, scorecard_only=True)
        trend = await trends(tx, [k["id"] for k in ks], tz, now)
        out.append(
            ScoreRow(
                company=co.code,
                name_fa=co.name_fa,
                kpis=[card_kpi(k, trend[k["id"]], now, have) for k in ks],
            )
        )
    return out


# ------------------------------------------------------------ attainment --
def at_target(direction: str, value: float, target: float, target_max: float | None) -> bool:
    if direction == "down":
        return value <= target
    if direction == "range":
        return target <= value <= (target_max if target_max is not None else target)
    return value >= target


async def attainment(tx: Tx, company_id: UUID, now: datetime | None = None) -> float | None:
    """The KPI part of the company score, 0..100 (contract §20.4): the active
    quarter's weighted key-result progress when an OKR is active, else the
    share of scorecard KPIs with a value and a target that are at target."""
    from hq_api.domain import gov_okr

    now = now or datetime.now(UTC)
    okr = await gov_okr.active_progress(tx, company_id, now)
    if okr is not None:
        return round(100.0 * okr, 2)
    have = await available(tx)
    scored = [
        k
        for k in await company_kpis(tx, company_id, scorecard_only=True)
        if k["target"] is not None and state_of(k, now, have) != "no_source"
    ]
    if not scored:
        return None
    hit = sum(
        1
        for k in scored
        if at_target(
            k["direction"], float(k["last_value"]), float(k["target"]), G.num(k["target_max"])
        )
    )
    return round(100.0 * hit / len(scored), 2)


# ------------------------------------------------------------ definitions --
def render_kpi(r: dict[str, Any], code: str) -> Kpi:
    return Kpi(
        id=r["id"],
        company=code,
        key=r["key"],
        card=r["card"],
        name_fa=r["name_fa"],
        unit=r["unit"],
        direction=r["direction"],
        source=r["source"],
        freshness_hours=r["freshness_hours"],
        target=G.num(r["target"]),
        target_max=G.num(r["target_max"]),
        scorecard=r["scorecard"],
        aggregate=r["aggregate"],
        status=r["status"],
        version=r["version"],
    )


async def kpi_set(tx: Tx, company: Any) -> KpiSet:
    await seed_company(tx, company.id, company.kind)
    version = await tx.scalar(
        "SELECT version FROM governance.kpi_sets WHERE company_id = :co", co=company.id
    )
    rows = await tx.all(
        "SELECT * FROM governance.kpis WHERE company_id = :co ORDER BY card, key", co=company.id
    )
    return KpiSet(
        company=company.code, version=int(version), kpis=[render_kpi(r, company.code) for r in rows]
    )


class KpiSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern=r"^(query|manual)$")
    query: str | None = Field(default=None, pattern=KEY)


class KpiChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY)
    target: float | None = None
    target_max: float | None = None
    scorecard: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(active|paused)$")
    freshness_hours: int | None = Field(default=None, ge=1, le=8760)
    # a KPI of the registry (or manual) the company does not have yet
    source: KpiSourceIn | None = None
    card: str | None = Field(default=None, pattern=r"^(stability|growth|safety_cost)$")
    name_fa: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=20)
    direction: str | None = Field(default=None, pattern=r"^(up|down|range)$")
    aggregate: str | None = Field(default=None, pattern=r"^(sum|avg|min|max)$")


class KpiSetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpis: list[KpiChange] = Field(min_length=1, max_length=60)


EDITABLE = ("target", "target_max", "scorecard", "status", "freshness_hours", "name_fa", "unit", "card",
            "direction", "aggregate")  # fmt: skip
NULLABLE = ("target", "target_max")  # null clears a target


async def put_set(tx: Tx, who: Principal, company: Any, body: KpiSetIn, expected: int) -> list[str]:
    """The owner's definitions and targets (If-Match on the set's version).
    A new key needs a source; a query outside the registry is 422."""
    await seed_company(tx, company.id, company.kind)
    current = await tx.scalar(
        "SELECT version FROM governance.kpi_sets WHERE company_id = :co FOR UPDATE", co=company.id
    )
    if int(current) != expected:
        raise ApiError(409, "version_conflict", f"current version is {current}")
    have = await available(tx)
    changed: list[str] = []
    for i, c in enumerate(body.kpis):
        row = await tx.first(
            "SELECT * FROM governance.kpis WHERE company_id = :co AND key = :k",
            co=company.id,
            k=c.key,
        )
        if c.source is not None:
            if row is not None and c.source.model_dump(exclude_none=True) != row["source"]:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={f"kpis.{i}.source": "a KPI's source never changes"},
                )
            if c.source.kind == "query" and (
                c.source.query not in REGISTRY or c.source.query not in have
            ):
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={f"kpis.{i}.source": "not a query of the registry"},
                )
            if c.source.kind == "query" and c.source.query != c.key:
                raise ApiError(
                    422,
                    "validation_failed",
                    fields={f"kpis.{i}.key": "a query KPI is keyed by its query"},
                )
        if row is None:
            if c.source is None or c.card is None or c.name_fa is None:
                raise ApiError(
                    422, "validation_failed",
                    fields={f"kpis.{i}": "a new KPI needs source, card and name_fa"},
                )  # fmt: skip
            src = (
                {"kind": "manual"}
                if c.source.kind == "manual"
                else {"kind": "query", "query": c.source.query}
            )
            row = await _insert(
                tx,
                company.id,
                {"key": c.key, "card": c.card, "name_fa": c.name_fa, "unit": c.unit or "",
                 "direction": c.direction or "up", "source": src, "freshness_hours": c.freshness_hours or 24,
                 "target": c.target, "target_max": c.target_max, "scorecard": bool(c.scorecard),
                 "aggregate": c.aggregate or "sum", "origin": "owner"},
            )  # fmt: skip
            await _change(tx, row, {"created": True}, who)
            changed.append(c.key)
            continue
        fields: dict[str, Any] = {}
        for f in EDITABLE:
            v = getattr(c, f)
            if f in c.model_fields_set and (v is not None or f in NULLABLE):
                fields[f] = v
        diff = {
            f: v for f, v in fields.items() if (G.num(row[f]) if f in NULLABLE else row[f]) != v
        }
        if not diff:
            continue
        direction = diff.get("direction", row["direction"])
        if direction != "range" and diff.get("target_max", row["target_max"]) is not None:
            diff["target_max"] = None
        sets = ", ".join(f"{f} = :{f}" for f in diff)
        await tx.exec(
            f"UPDATE governance.kpis SET {sets}, version = version + 1, updated_at = now() WHERE id = :id",  # noqa: S608 - EDITABLE names
            id=row["id"],
            **diff,
        )
        await _change(tx, row, diff, who)
        changed.append(c.key)
    if changed:
        await tx.exec(
            "UPDATE governance.kpi_sets SET seeded_from = seeded_from WHERE company_id = :co",
            co=company.id,
        )
    return changed


async def _change(tx: Tx, row: dict[str, Any], change: dict[str, Any], who: Principal) -> None:
    await tx.exec(
        """INSERT INTO governance.kpi_changes (company_id, kpi_id, version, change, by_kind, by_code)
           VALUES (:co, :k, (SELECT version FROM governance.kpis WHERE id = :k), CAST(:c AS jsonb), :bk, :bc)""",
        co=row["company_id"],
        k=row["id"],
        c=json.dumps(change, ensure_ascii=False, default=str),
        bk=who.kind if who.kind in ("owner", "agent", "service") else "service",
        bc=who.code,
    )


async def values(
    tx: Tx, company_id: UUID, key: str, start: datetime, end: datetime
) -> list[KpiValue]:
    k = await tx.one(
        "SELECT id FROM governance.kpis WHERE company_id = :co AND key = :k", co=company_id, k=key
    )
    rows = await tx.all(
        """SELECT at, value, source_ref FROM governance.kpi_values
           WHERE kpi_id = :id AND at >= :a AND at < :b ORDER BY at LIMIT 2000""",
        id=k["id"],
        a=start,
        b=end,
    )
    return [
        KpiValue(kpi=key, at=r["at"], value=float(r["value"]), source_ref=r["source_ref"])
        for r in rows
    ]


# ------------------------------------------------------------ kpi.record --
class KpiRecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    key: str = Field(pattern=KEY)
    value: float = Field(allow_inf_nan=False)
    at: datetime
    source: G.EvidenceSource


async def record(tx: Tx, who: Principal, company_id: UUID, body: KpiRecordIn) -> dict[str, Any]:
    """A manual KPI's value, with its source (contract §20.4: kpi.record only)."""
    k = await tx.first(
        "SELECT * FROM governance.kpis WHERE company_id = :co AND key = :k",
        co=company_id,
        k=body.key,
    )
    if k is None:
        raise ApiError(404, "not_found", f"no KPI {body.key}")
    if (k["source"] or {}).get("kind") != "manual":
        raise ApiError(422, "validation_failed", fields={"key": "a query KPI is measured by code"})
    at = body.at if body.at.tzinfo else body.at.replace(tzinfo=UTC)
    if at > datetime.now(UTC) + timedelta(minutes=5):
        raise ApiError(422, "validation_failed", fields={"at": "not in the future"})
    ref = body.source.model_dump()
    await _store(
        tx, k, float(body.value), at, ref, ("agent" if who.is_agent else who.kind, who.code)
    )
    return {"key": body.key, "value": body.value, "at": at.isoformat(), "source_ref": ref}
