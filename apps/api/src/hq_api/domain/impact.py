"""A decision's money impact (contract §33.6 ⟨1.15⟩).

`Decision.impact = {revenue_usdt|null, cost_usd|null, horizon_days, basis_fa,
kind: "measured"|"estimate"}|null`.

- **Measured by code** where the inputs exist, from rows the hub already holds:
  - `budget_change`: the delta of the card's limit against the budget now in force
    (a token limit is priced by what that scope really cost per token in the last
    30 days);
  - `hire`: the card's model x the monthly tokens it names, else the median monthly use
    of the same charter role, priced by the router's price table;
  - an ads cap (`ads.cap`) and a line's caps: a proposal or an A3 card that names them in
    `payload.impact_input` ({kind: "ads.cap", platform, campaign, new_daily_cap} or
    {kind: "line.caps", line, new_runs_per_day}) gets the extra spend of the new cap and,
    for ads, the revenue the campaign's own 14-day ROAS says it would bring; for a line,
    its last 14 days per run.
- **Estimate** (task class `decision_impact`, a mid model, ONE call per card, a strict
  schema) only for `proposal` and `a3_action` cards that carry no measurable input, and
  only while the card is pending: never for a card the owner has already decided. The
  basis always begins «تخمین» and the figures are checked by code (finite, not negative).
- `GET /decisions?sort=impact` orders by the size of the impact per 30 days.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from hq_api import workflows_client
from hq_api.db import Tx
from hq_api.domain import humanize, pricing
from hq_common.redact import scrub

log = logging.getLogger("hq_api.impact")


def mid_model() -> str:
    """The mid model of the one-sentence calls (the automations' choice), read lazily."""
    from hq_api.domain.automations import MODEL

    return MODEL


TASK_CLASS = "decision_impact"
MAX_OUTPUT_TOKENS = 900
MEASURED_KINDS = ("budget_change", "hire")
ESTIMATED_KINDS = ("proposal", "a3_action")
MAX_TRIES = 3
BATCH = 20
IN_SHARE = Decimal("0.7")  # a hire's tokens are priced as 70% input, 30% output
Ask = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class Impact(BaseModel):
    revenue_usdt: float | None = None
    cost_usd: float | None = None
    horizon_days: int = Field(ge=1, le=365)
    basis_fa: str
    kind: Literal["measured", "estimate"]


class ImpactInput(BaseModel):
    """What a proposal or A3 card may name so its impact is measured, not guessed."""

    kind: Literal["ads.cap", "line.caps"]
    platform: Literal["google_ads", "meta_ads"] | None = None
    campaign: str | None = Field(default=None, max_length=100)
    new_daily_cap: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    line: str | None = Field(default=None, pattern=r"^LN-[0-9]{4,}$")
    new_runs_per_day: int | None = Field(default=None, ge=0, le=1000)


def score(impact: dict[str, Any] | None) -> float:
    """The size of an impact per 30 days (the sort key; the same expression as SORT_SQL)."""
    if not impact:
        return 0.0
    mag = abs(float(impact.get("revenue_usdt") or 0)) + abs(float(impact.get("cost_usd") or 0))
    return mag * 30.0 / max(int(impact.get("horizon_days") or 1), 1)


SORT_SQL = """(CASE WHEN d.impact IS NULL THEN NULL ELSE
    (abs(COALESCE((d.impact->>'revenue_usdt')::numeric, 0))
     + abs(COALESCE((d.impact->>'cost_usd')::numeric, 0)))
    * 30.0 / greatest(COALESCE((d.impact->>'horizon_days')::numeric, 1), 1) END)"""
# ascending: the largest impact first, the cards without one last (`GET /decisions?sort=impact`)
SORT_KEY_SQL = f"COALESCE(-{SORT_SQL}, 1)"


def _num(v: Decimal | float | None) -> float | None:
    return None if v is None else round(float(v), 2)


def measured(
    revenue: Decimal | float | None, cost: Decimal | float | None, horizon: int, basis: str
) -> dict[str, Any] | None:
    if revenue is None and cost is None:
        return None
    return Impact(
        revenue_usdt=_num(revenue),
        cost_usd=_num(cost),
        horizon_days=horizon,
        basis_fa=basis[:600],
        kind="measured",
    ).model_dump()


# ---------------------------------------------------------------- measuring --
async def _cost_per_token(
    tx: Tx, scope_type: str, scope_ref: str, company_id: Any
) -> Decimal | None:
    """What a token of this scope really cost over the last 30 days."""
    where = {
        "holding": "TRUE",
        "company": "co.code = :ref",
        "department": "c.department = :ref",
        "role": "split_part(c.meta->>'charter', '@', 1) = :ref",
        "task_class": "c.task_class = :ref",
    }[scope_type]
    row = await tx.one(
        f"""SELECT COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd,
                   COALESCE(sum(COALESCE(c.input_tokens, 0) + COALESCE(c.output_tokens, 0)
                       + COALESCE(c.cache_read_tokens, 0) + COALESCE(c.cache_write_tokens, 0)), 0) AS tokens
            FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
            WHERE c.started_at > now() - interval '30 days' AND {where}""",  # noqa: S608 - constants
        ref=scope_ref,
    )
    del company_id
    return Decimal(row["usd"]) / Decimal(row["tokens"]) if Decimal(row["tokens"]) > 0 else None


async def measure_budget(tx: Tx, d: dict[str, Any]) -> dict[str, Any] | None:
    p = d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"])
    scope, period = p.get("scope") or {}, p.get("period")
    if period not in ("day", "month") or not scope:
        return None
    horizon = 30 if period == "month" else 1
    now_row = await tx.first(
        """SELECT token_limit, usd_limit FROM llm.budgets
           WHERE scope_type = :t AND scope_ref = :r AND period = :p LIMIT 1""",
        t=scope.get("scope_type"),
        r=scope.get("scope_ref"),
        p=period,
    )
    if now_row is None:
        return None  # no limit in force: there is nothing to take a delta from
    new_usd, new_tok = p.get("usd_limit"), p.get("token_limit")
    per = period_fa = "ماه" if period == "month" else "روز"
    if new_usd is not None and now_row["usd_limit"] is not None:
        delta = Decimal(str(new_usd)) - Decimal(now_row["usd_limit"])
        return measured(
            None, delta, horizon,
            f"سقف دلاری هر {per} از {now_row['usd_limit']:.2f} به {Decimal(str(new_usd)):.2f} دلار می‌رسد؛ "
            "بیشترین هزینه‌ی اضافه همین تفاوت است.",
        )  # fmt: skip
    if new_tok is not None and now_row["token_limit"] is not None:
        rate = await _cost_per_token(
            tx, str(scope.get("scope_type")), str(scope.get("scope_ref")), d["company_id"]
        )
        if rate is None:
            return None
        delta = (Decimal(int(new_tok)) - Decimal(int(now_row["token_limit"]))) * rate
        return measured(
            None, delta, horizon,
            f"سقف توکن هر {period_fa} از {int(now_row['token_limit']):,} به {int(new_tok):,} می‌رسد؛ "
            "با قیمت واقعی هر توکن این بخش در ۳۰ روز اخیر حساب شد.",
        )  # fmt: skip
    return None


async def measure_hire(tx: Tx, d: dict[str, Any]) -> dict[str, Any] | None:
    p = d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"])
    model = p.get("model")
    quota = p.get("quota_estimate_month") or {}
    if quota.get("usd") is not None:
        return measured(
            None, Decimal(str(quota["usd"])), 30,
            f"هزینه‌ی ماهانه‌ای که خود کارت برای این استخدام نوشته است ({model}).",
        )  # fmt: skip
    tokens = quota.get("tokens")
    basis_tokens = "توکن ماهانه‌ای که کارت نوشته است"
    if tokens is None and p.get("role"):
        rows = await tx.all(
            """SELECT sum(r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens)
                      AS t FROM agents.runs r
               WHERE r.charter_role = :role AND r.created_at > now() - interval '30 days'
               GROUP BY r.employee_id""",
            role=p["role"],
        )
        if rows:
            tokens = int(statistics.median(int(r["t"]) for r in rows))
            basis_tokens = f"میانه‌ی مصرف ماهانه‌ی همین نقش ({tokens:,} توکن)"
    if not tokens or not isinstance(model, str):
        return None
    table = await tx.first(
        "SELECT pricing FROM llm.connections WHERE pricing ? :m LIMIT 1", m=model
    )
    if table is None:
        return None
    pr = table["pricing"] if isinstance(table["pricing"], dict) else json.loads(table["pricing"])
    cost = pricing.cost_usd(
        pr, model,
        input_tokens=int(Decimal(int(tokens)) * IN_SHARE),
        output_tokens=int(Decimal(int(tokens)) * (1 - IN_SHARE)),
    )  # fmt: skip
    if cost is None:
        return None
    return measured(
        None,
        cost,
        30,
        f"{basis_tokens}، با قیمت مدل {model} در جدول قیمت هاب (۷۰٪ ورودی، ۳۰٪ خروجی).",
    )


async def measure_ads_cap(
    tx: Tx, company_id: Any, platform: str, campaign: str, new_cap: Decimal
) -> dict[str, Any] | None:
    """The extra spend a new daily cap allows over 30 days, and the revenue the campaign's
    own ROAS of the last 14 days says it would bring."""
    cur = await tx.first(
        """SELECT daily_cap FROM growth.ad_rules WHERE company_id = :co AND platform = :p
             AND state = 'on' AND daily_cap IS NOT NULL AND scope IN (:c, 'account')
           ORDER BY (scope = :c) DESC LIMIT 1""",
        co=company_id, p=platform, c=campaign,
    )  # fmt: skip
    day = await tx.one(
        """SELECT COALESCE(sum(spend), 0) AS spend, COALESCE(sum(revenue), 0) AS revenue
           FROM growth.ad_daily WHERE company_id = :co AND platform = :p AND campaign_id = :c
             AND day > current_date - 14""",
        co=company_id, p=platform, c=campaign,
    )  # fmt: skip
    if cur is None or Decimal(day["spend"]) <= 0:
        return None
    extra_day = new_cap - Decimal(cur["daily_cap"])
    cost = extra_day * 30
    roas = Decimal(day["revenue"]) / Decimal(day["spend"])
    revenue = cost * roas if cost > 0 else None
    return measured(
        revenue, cost, 30,
        f"سقف روزانه از {Decimal(cur['daily_cap']):.2f} به {new_cap:.2f} دلار می‌رسد؛ بازده تبلیغ این کمپین "
        f"در ۱۴ روز اخیر {roas:.2f} برابر بوده است.",
    )  # fmt: skip


async def measure_line_caps(
    tx: Tx, company_id: Any, line_ref: str, new_runs_per_day: int
) -> dict[str, Any] | None:
    # The card's own company only: the sweep's RLS scope sees every company.
    line = await tx.first(
        "SELECT id, caps FROM lines.lines WHERE ref = :r AND company_id = :co",
        r=line_ref,
        co=company_id,
    )
    if line is None:
        return None
    caps = line["caps"] if isinstance(line["caps"], dict) else json.loads(line["caps"])
    row = await tx.one(
        """SELECT count(*) AS n, COALESCE(sum(usd_equiv), 0) AS usd FROM lines.runs
           WHERE line_id = :l AND NOT dry AND state = 'done' AND at > now() - interval '14 days'""",
        l=line["id"],
    )
    if int(row["n"]) == 0:
        return None
    each = Decimal(row["usd"]) / int(row["n"])
    delta = (int(new_runs_per_day) - int(caps.get("runs_per_day") or 0)) * each * 30
    return measured(
        None, delta, 30,
        f"هر اجرای این خط در ۱۴ روز اخیر به‌طور میانگین {each:.2f} دلار خرج داشت؛ "
        f"سقف روزانه از {int(caps.get('runs_per_day') or 0)} به {new_runs_per_day} اجرا می‌رسد.",
    )  # fmt: skip


async def measure(tx: Tx, d: dict[str, Any]) -> dict[str, Any] | None:
    """The measured impact of a card, or None when its inputs are not there."""
    p = d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"])
    if d["kind"] == "budget_change":
        return await measure_budget(tx, d)
    if d["kind"] == "hire":
        return await measure_hire(tx, d)
    raw = p.get("impact_input") if d["kind"] in ESTIMATED_KINDS else None
    if not isinstance(raw, dict):
        return None
    try:
        inp = ImpactInput.model_validate(raw)
    except ValueError:
        return None
    if inp.kind == "ads.cap" and inp.platform and inp.campaign and inp.new_daily_cap is not None:
        return await measure_ads_cap(
            tx, d["company_id"], inp.platform, inp.campaign, inp.new_daily_cap
        )
    if inp.kind == "line.caps" and inp.line and inp.new_runs_per_day is not None:
        return await measure_line_caps(tx, d["company_id"], inp.line, inp.new_runs_per_day)
    return None


# --------------------------------------------------------------- estimating --
ESTIMATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "revenue_usdt": {"type": ["number", "null"], "minimum": 0},
                    "cost_usd": {"type": ["number", "null"], "minimum": 0},
                    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "basis_fa": {"type": "string", "maxLength": 500},
                },
                "required": ["revenue_usdt", "cost_usd", "horizon_days", "basis_fa"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}
ESTIMATE_SYSTEM = (
    "You estimate the money impact of ONE decision card of a holding, as JSON, nothing else. "
    'Answer {"routes": [{"revenue_usdt": number or null, "cost_usd": number or null, '
    '"horizon_days": integer, "basis_fa": <one or two plain Persian sentences>}]}. '
    "revenue_usdt is the extra revenue the decision could bring over the horizon, cost_usd the "
    "money it would cost; use null for a side you cannot estimate from the card. basis_fa says in "
    "plain Persian what the estimate rests on (only facts in the card). Use only the card; invent no "
    "market figure, no customer, no past result. If the card gives no basis for any figure, return "
    "null for both. Put no preamble."
)


def estimate_request(holding_code: str, d: dict[str, Any]) -> dict[str, Any]:
    p = d["payload"] if isinstance(d["payload"], dict) else json.loads(d["payload"])
    card = {
        "kind": d["kind"],
        "title": scrub(d["title"]),
        "what": scrub(d["what"] or "")[:3000],
        "why": scrub(d["why"] or "")[:3000],
        "payload": json.loads(scrub(json.dumps(p, ensure_ascii=False, default=str)[:4000]))
        if len(json.dumps(p, default=str)) <= 4000
        else {},
    }
    return {
        "company_code": holding_code,
        "actor_ref": "impact",
        "task_class": TASK_CLASS,
        "priority": 3,
        "model": mid_model(),
        "effort": "low",
        "system": ESTIMATE_SYSTEM,
        "prompt": json.dumps(card, ensure_ascii=False),
        "json_schema": ESTIMATE_SCHEMA,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 60,
        "meta": {"purpose": "decision_impact", "decision": d["ref"]},
    }


def checked_estimate(raw: Any) -> dict[str, Any] | None:
    """The model's estimate, or None when it is not usable: figures finite and not
    negative, at least one of them present, a plain Persian basis."""
    if not isinstance(raw, dict) or set(raw) != {
        "revenue_usdt",
        "cost_usd",
        "horizon_days",
        "basis_fa",
    }:
        return None
    figures: dict[str, float | None] = {}
    for k in ("revenue_usdt", "cost_usd"):
        v = raw[k]
        if v is None:
            figures[k] = None
        elif isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v < 0:
            return None
        else:
            figures[k] = round(float(v), 2)
    horizon = raw["horizon_days"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 365:
        return None
    if figures["revenue_usdt"] is None and figures["cost_usd"] is None:
        return None
    basis = humanize.humanize(" ".join(str(raw["basis_fa"]).split()))
    if len(basis) < 8 or humanize.check(basis) or humanize.persian_share(basis) < 0.4:
        return None
    if not basis.startswith("تخمین"):
        basis = f"تخمین: {basis}"
    return Impact(
        revenue_usdt=figures["revenue_usdt"],
        cost_usd=figures["cost_usd"],
        horizon_days=horizon,
        basis_fa=basis[:600],
        kind="estimate",
    ).model_dump()


async def estimate(
    hub: Any, holding_code: str, d: dict[str, Any], ask: Ask | None = None
) -> dict[str, Any] | None:
    call = ask or (lambda r: workflows_client.route_order(hub, r, 70.0))
    try:
        answer = await call(estimate_request(holding_code, d))
    except Exception:  # noqa: BLE001 - tried again on the next tick, up to MAX_TRIES
        return None
    routes = (answer or {}).get("routes")
    return checked_estimate(routes[0] if isinstance(routes, list) and len(routes) == 1 else None)


# -------------------------------------------------------------------- sweep --
async def _store(tx: Tx, d: dict[str, Any], impact: dict[str, Any] | None) -> None:
    await tx.exec(
        """UPDATE cartable.decisions SET impact = CAST(:i AS jsonb), impact_tries = impact_tries + 1
           WHERE id = :id AND status = 'pending' AND impact IS NULL""",
        i=json.dumps(impact, ensure_ascii=False) if impact else None,
        id=d["id"],
    )


async def sweep(
    hub: Any, ask: Ask | None = None, now: datetime | None = None, *, only: list[Any] | None = None
) -> dict[str, int]:
    """Impact for the pending cards that have none: the measured ones by code, the estimates
    (proposal, a3_action) one model call per card. A card the owner has decided is never
    touched. Each card is tried at most MAX_TRIES times."""
    del now
    out = {"measured": 0, "estimated": 0, "skipped": 0}
    holding = await hub.companies.holding()
    todo: list[dict[str, Any]] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(
            """SELECT d.id, d.ref, d.kind, d.company_id, d.title, d.what, d.why, d.payload
               FROM cartable.decisions d
               WHERE d.status = 'pending' AND d.impact IS NULL AND d.impact_tries < :n
                 AND d.kind IN ('budget_change', 'hire', 'proposal', 'a3_action')
                 AND (CAST(:only AS uuid[]) IS NULL OR d.id = ANY(CAST(:only AS uuid[])))
               ORDER BY d.created_at LIMIT :lim""",
            n=MAX_TRIES,
            lim=BATCH,
            only=only,
        )
        for d in rows:
            m = await measure(tx, d)
            if m is not None:
                await _store(tx, d, m)
                out["measured"] += 1
            elif d["kind"] in ESTIMATED_KINDS:
                todo.append(d)
            else:
                await _store(tx, d, None)
                out["skipped"] += 1
    for d in todo:  # the slow part, outside a transaction: one call per card
        est = await estimate(hub, holding.code, d, ask)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await _store(tx, d, est)
        out["estimated" if est else "skipped"] += 1
    return out


def now_utc() -> datetime:
    return datetime.now(UTC)
