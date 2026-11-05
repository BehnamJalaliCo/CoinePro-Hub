"""The company journey (contract §33.8 ⟨1.15⟩).

Stages are data: the default list below, or the list of the kit a company was made from
(`seed/kits/*.yaml` `journey:`, kept in growth.journey_plans). A stage is reached BY CODE from rows
that already exist, never by a model and never by hand:

  company        the company row                      (always)
  server         a paired server (infra.runners)      (a runner credential was made for it)
  first_publish  a real (not dry) line run that published
  visitors       the first day with visitors in the analytics connection's figures
  leads          the first lead      (the sales table, read only if it exists on this hub)
  payments       the first payment   (money.payments, read only if it exists)
  paying         `min` distinct paying customers (money.payments, same rule)
  break_even     a month whose revenue covers its costs (tokens and ads), revenue from money.payments

A table of another part that is not there (or does not answer as expected) leaves its stage
unreached, without an error. Once reached a stage stays reached (growth.journey_stages keeps the
first time and the evidence). The one line `next_fa` is written by ONE mid-model call (task class
`journey_next`) only when a stage changes; a model that is down or answers badly is replaced by a
line made by code, never an error.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from hq_api import events, workflows_client
from hq_api.db import Tx
from hq_api.domain import humanize
from hq_api.domain.automations import MODEL as MID_MODEL
from hq_api.errors import ApiError

log = logging.getLogger("hq_api.journey")

TASK_CLASS = "journey_next"
MAX_OUTPUT_TOKENS = 400
KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
RULE_KINDS = (
    "company", "server", "first_publish", "visitors", "leads", "payments", "paying", "break_even",
)  # fmt: skip
# The tables of the other parts of prompt 24; each is read only when it exists on this hub.
LEAD_TABLES = ("sales.leads", "growth.leads")
PAYMENTS_TABLE = "money.payments"
PAID_STATUSES = ("matched", "chain_only", "amount_mismatch")
ANALYTICS_KINDS = ("ga4", "hub")
VISITOR_KEYS = ("sessions", "users")
DEFAULT_PAYING = 10

DEFAULT_STAGES: tuple[dict[str, Any], ...] = (
    {"key": "founded", "title_fa": "تأسیس", "rule": {"kind": "company"}},
    {"key": "server_ready", "title_fa": "سرور آماده", "rule": {"kind": "server"}},
    {"key": "first_content", "title_fa": "اولین محتوا", "rule": {"kind": "first_publish"}},
    {"key": "first_visitor", "title_fa": "اولین بازدیدکننده", "rule": {"kind": "visitors"}},
    {"key": "first_lead", "title_fa": "اولین سرنخ", "rule": {"kind": "leads"}},
    {"key": "first_payment", "title_fa": "اولین پرداخت", "rule": {"kind": "payments"}},
    {
        "key": "ten_paying",
        "title_fa": "ده مشتری پرداخت‌کننده",
        "rule": {"kind": "paying", "min": DEFAULT_PAYING},
    },
    {"key": "break_even", "title_fa": "سربه‌سر", "rule": {"kind": "break_even"}},
)


# ------------------------------------------------------------------ shapes --
class JourneyEvidence(BaseModel):
    kind: str
    ref: str | None = None


class JourneyStage(BaseModel):
    key: str
    title_fa: str
    reached_at: datetime | None = None
    evidence: JourneyEvidence | None = None


class Journey(BaseModel):
    """Where one company is on its way from founding to break-even."""

    company: str
    stages: list[JourneyStage]
    current: str
    next_fa: str | None = None
    days_in_stage: int


class JourneyEvent(BaseModel):
    at: datetime
    company: str
    stage: str
    title_fa: str


class JourneyBoard(BaseModel):
    """Every company's journey, and all reached stages on one timeline (newest first)."""

    journeys: list[Journey]
    timeline: list[JourneyEvent]


# -------------------------------------------------------------- the plan --
def normalize_stages(raw: Any) -> list[dict[str, Any]]:
    """A kit's `journey:` list as full stages; ValueError names the first fault. An entry may be a
    bare key of the default list, or `{key, title_fa?, rule?}`; a new key needs title_fa and rule."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise ValueError("journey is a list of 1 to 20 stages")
    base = {s["key"]: s for s in DEFAULT_STAGES}
    out: list[dict[str, Any]] = []
    for item in raw:
        entry = {"key": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or set(entry) - {"key", "title_fa", "rule"}:
            raise ValueError(f"a stage is a key or {{key, title_fa, rule}}: {item!r}")
        key = entry.get("key")
        if not isinstance(key, str) or not KEY.match(key) or any(s["key"] == key for s in out):
            raise ValueError(f"stage key invalid or repeated: {key!r}")
        known = base.get(key, {})
        title = entry.get("title_fa", known.get("title_fa"))
        rule = entry.get("rule", known.get("rule"))
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            raise ValueError(f"stage {key}: title_fa is required (at most 100 characters)")
        if not isinstance(rule, dict) or set(rule) - {"kind", "min"}:
            raise ValueError(f"stage {key}: rule is {{kind, min?}}")
        if rule.get("kind") not in RULE_KINDS:
            raise ValueError(f"stage {key}: rule.kind is one of {', '.join(RULE_KINDS)}")
        n = rule.get("min")
        if n is not None and (
            rule["kind"] != "paying" or not isinstance(n, int) or not 1 <= n <= 100000
        ):
            raise ValueError(f"stage {key}: `min` is a whole number for a `paying` rule only")
        out.append({"key": key, "title_fa": title.strip(), "rule": dict(rule)})
    return out


async def adopt_kit(tx: Tx, company_id: UUID, kit_key: str, kit: dict[str, Any]) -> bool:
    """A company made from a kit that has its own stages keeps them (called by kits.create)."""
    if not kit.get("journey"):
        return False
    await tx.exec(
        """INSERT INTO growth.journey_plans (company_id, kit, stages)
           VALUES (:co, :kit, CAST(:s AS jsonb)) ON CONFLICT (company_id) DO NOTHING""",
        co=company_id,
        kit=kit_key,
        s=json.dumps(normalize_stages(kit["journey"]), ensure_ascii=False),
    )
    return True


async def plan_of(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    row = await tx.first(
        "SELECT stages FROM growth.journey_plans WHERE company_id = :co", co=company_id
    )
    if row is None:
        return [dict(s) for s in DEFAULT_STAGES]
    stages = row["stages"]
    return list(json.loads(stages) if isinstance(stages, str) else stages)


# ------------------------------------------------------------ the evidence --
Found = tuple[datetime, str, str | None]  # (reached_at, evidence kind, evidence ref)


async def _exists(tx: Tx, table: str) -> bool:
    return bool(await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table))


async def _columns(tx: Tx, table: str) -> set[str]:
    schema, name = table.split(".")
    rows = await tx.all(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :n",
        s=schema,
        n=name,
    )
    return {r["column_name"] for r in rows}


async def _company(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    row = await tx.first("SELECT code, created_at FROM core.companies WHERE id = :co", co=co)
    return None if row is None else (row["created_at"], "company", row["code"])


async def _server(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    row = await tx.first(
        "SELECT created_at FROM infra.runners WHERE company_id = :co ORDER BY created_at LIMIT 1",
        co=co,
    )
    return None if row is None else (row["created_at"], "server", None)


async def _first_publish(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    row = await tx.first(
        """SELECT r.ref, min(CAST(p->>'at' AS timestamptz)) AS at
           FROM lines.runs r, jsonb_array_elements(r.published) p
           WHERE r.company_id = :co AND NOT r.dry AND jsonb_array_length(r.published) > 0
           GROUP BY r.ref ORDER BY min(CAST(p->>'at' AS timestamptz)) LIMIT 1""",
        co=co,
    )
    return None if row is None or row["at"] is None else (row["at"], "line_run", row["ref"])


async def _visitors(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    row = await tx.first(
        """SELECT day, key FROM growth.metrics_daily
           WHERE company_id = :co AND value > 0
             AND kind = ANY (CAST(:kinds AS text[])) AND key = ANY (CAST(:keys AS text[]))
           ORDER BY day LIMIT 1""",
        co=co,
        kinds=list(ANALYTICS_KINDS),
        keys=list(VISITOR_KEYS),
    )
    if row is None:
        return None
    return (
        datetime(row["day"].year, row["day"].month, row["day"].day, tzinfo=UTC),
        "metric",
        row["key"],
    )


async def _leads(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    for table in LEAD_TABLES:
        if not await _exists(tx, table):
            continue
        has_ref = "ref" in await _columns(tx, table)
        row = await tx.first(
            f"SELECT created_at AS at, {'ref' if has_ref else 'NULL::text AS ref'} "  # noqa: S608
            f"FROM {table} WHERE company_id = :co ORDER BY created_at LIMIT 1",
            co=co,
        )
        if row is not None:
            return row["at"], "lead", row["ref"]
    return None


async def _payments(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    if not await _exists(tx, PAYMENTS_TABLE):
        return None
    row = await tx.first(
        f"SELECT paid_at AS at FROM {PAYMENTS_TABLE} "  # noqa: S608
        "WHERE company_id = :co AND status = ANY (CAST(:st AS text[])) ORDER BY paid_at LIMIT 1",
        co=co,
        st=list(PAID_STATUSES),
    )
    return None if row is None else (row["at"], "payment", None)


async def _paying(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    if not await _exists(tx, PAYMENTS_TABLE):
        return None
    need = int(rule.get("min") or DEFAULT_PAYING)
    row = await tx.first(
        f"""SELECT first_at FROM (
                SELECT customer, min(paid_at) AS first_at FROM {PAYMENTS_TABLE}
                WHERE company_id = :co AND status = ANY (CAST(:st AS text[])) AND customer IS NOT NULL
                GROUP BY customer ORDER BY min(paid_at) OFFSET :skip LIMIT 1) t""",  # noqa: S608
        co=co,
        st=list(PAID_STATUSES),
        skip=need - 1,
    )
    return None if row is None else (row["first_at"], "customers", str(need))


async def _break_even(tx: Tx, co: UUID, rule: dict[str, Any]) -> Found | None:
    """The first month whose revenue (paid amounts) is at least its costs (the tokens' and the ads'
    dollars); a month with no revenue, or with no cost at all to break even against, never counts."""
    if not await _exists(tx, PAYMENTS_TABLE):
        return None
    rows = await tx.all(
        f"""WITH rev AS (
                SELECT date_trunc('month', paid_at) AS m, sum(amount_usdt) AS revenue
                FROM {PAYMENTS_TABLE}
                WHERE company_id = :co AND status = ANY (CAST(:st AS text[])) AND amount_usdt IS NOT NULL
                GROUP BY 1),
            tok AS (
                SELECT date_trunc('month', started_at) AS m,
                       sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)) AS cost
                FROM llm.calls WHERE company_id = :co GROUP BY 1),
            ads AS (
                SELECT date_trunc('month', CAST(day AS timestamptz)) AS m, sum(spend) AS cost
                FROM growth.ad_daily WHERE company_id = :co GROUP BY 1)
            SELECT rev.m AS month, rev.revenue,
                   COALESCE(tok.cost, 0) + COALESCE(ads.cost, 0) AS cost
            FROM rev LEFT JOIN tok ON tok.m = rev.m LEFT JOIN ads ON ads.m = rev.m
            WHERE rev.revenue > 0 AND COALESCE(tok.cost, 0) + COALESCE(ads.cost, 0) > 0
              AND rev.revenue >= COALESCE(tok.cost, 0) + COALESCE(ads.cost, 0)
            ORDER BY rev.m LIMIT 1""",  # noqa: S608
        co=co,
        st=list(PAID_STATUSES),
    )
    if not rows:
        return None
    month = rows[0]["month"]
    return min(datetime.now(UTC), _month_end(month)), "month", month.strftime("%Y-%m")


def _month_end(month: datetime) -> datetime:
    return month.replace(year=month.year + (month.month == 12), month=month.month % 12 + 1)


EVALUATORS = {
    "company": _company,
    "server": _server,
    "first_publish": _first_publish,
    "visitors": _visitors,
    "leads": _leads,
    "payments": _payments,
    "paying": _paying,
    "break_even": _break_even,
}


async def evaluate(tx: Tx, company_id: UUID, rule: dict[str, Any]) -> Found | None:
    """The stage's first time and evidence, or None. A table that is missing, or an answer that is
    not as expected, leaves the stage unreached (inside a savepoint: the caller's transaction lives)."""
    fn = EVALUATORS.get(str(rule.get("kind")))
    if fn is None:
        return None
    try:
        async with tx.conn.begin_nested():
            return await fn(tx, company_id, rule)
    except Exception as exc:  # noqa: BLE001 - another part's table may differ: unreached, not an error
        log.warning(
            "a journey stage could not be read",
            extra={"rule": rule.get("kind"), "error": type(exc).__name__},
        )
        return None


# ------------------------------------------------------------- the state --
def _build(
    company: str, plan: list[dict[str, Any]], reached: dict[str, dict[str, Any]],
    state: dict[str, Any] | None,
) -> Journey:  # fmt: skip
    stages = [
        JourneyStage(
            key=s["key"],
            title_fa=s["title_fa"],
            reached_at=reached[s["key"]]["reached_at"] if s["key"] in reached else None,
            evidence=JourneyEvidence(
                kind=reached[s["key"]]["evidence_kind"], ref=reached[s["key"]]["evidence_ref"]
            )
            if s["key"] in reached
            else None,
        )
        for s in plan
    ]
    current = current_of(plan, reached)
    since = reached[current]["reached_at"] if current in reached else None
    return Journey(
        company=company,
        stages=stages,
        current=current,
        next_fa=(state or {}).get("next_fa"),
        days_in_stage=max(0, (datetime.now(UTC) - since).days) if since else 0,
    )


def current_of(plan: list[dict[str, Any]], reached: dict[str, Any]) -> str:
    """The latest stage of the plan that is reached (the first stage when none is)."""
    got = [s["key"] for s in plan if s["key"] in reached]
    return got[-1] if got else str(plan[0]["key"])


def next_target(plan: list[dict[str, Any]], reached: dict[str, Any]) -> dict[str, Any] | None:
    return next((s for s in plan if s["key"] not in reached), None)


async def read(tx: Tx, company_id: UUID, code: str) -> Journey:
    plan = await plan_of(tx, company_id)
    rows = await tx.all("SELECT * FROM growth.journey_stages WHERE company_id = :co", co=company_id)
    state = await tx.first(
        "SELECT * FROM growth.journey_state WHERE company_id = :co", co=company_id
    )
    return _build(code, plan, {r["key"]: r for r in rows}, state)


# ------------------------------------------------------------ the one line --
SYSTEM = (
    "تو مشاور هلدینگ هستی. فقط یک جمله‌ی کوتاه و روشن فارسی بنویس که بگوید این شرکت در گام بعدی چه "
    "کاری انجام بدهد تا به مرحله‌ی بعدی مسیرش برسد. فقط از اطلاعات داده‌شده استفاده کن، عدد یا وعده‌ی "
    'تازه نساز. پاسخ: {"routes": {"next_fa": "<یک جمله>"}}. هیچ متن دیگری ننویس.'
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["routes"],
    "properties": {
        "routes": {
            "type": "object",
            "additionalProperties": False,
            "required": ["next_fa"],
            "properties": {"next_fa": {"type": "string", "minLength": 5, "maxLength": 300}},
        }
    },
}


def fallback_line(target: dict[str, Any] | None) -> str:
    if target is None:
        return "همه‌ی مرحله‌های مسیر شرکت رسیده است."
    return f"گام بعدی: «{target['title_fa']}»."


async def next_line(
    hub: Any, code: str, name_fa: str, plan: list[dict[str, Any]], reached: dict[str, Any]
) -> str:
    """ONE mid-model call; code's own line when there is nothing left to say or the model is down."""
    target = next_target(plan, reached)
    if target is None:
        return fallback_line(None)
    current = current_of(plan, reached)
    titles = {s["key"]: s["title_fa"] for s in plan}
    req = {
        "company_code": code,
        "actor_ref": f"{code}-JOURNEY",
        "task_class": TASK_CLASS,
        "priority": 1,
        "model": MID_MODEL,
        "effort": "low",
        "system": SYSTEM,
        "prompt": json.dumps(
            {
                "company": name_fa,
                "reached": [titles[s["key"]] for s in plan if s["key"] in reached],
                "current": titles[current],
                "next_stage": target["title_fa"],
            },
            ensure_ascii=False,
        ),
        "json_schema": SCHEMA,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 40,
        "meta": {"purpose": "journey_next"},
    }
    answer = await workflows_client.route_order(hub, req)
    line = (answer or {}).get("routes")
    text = " ".join(str(line.get("next_fa") or "").split())[:300] if isinstance(line, dict) else ""
    if text and humanize.persian_share(text) >= 0.6 and not humanize.check(text):
        return text
    return fallback_line(target)


async def refresh_company(hub: Any, company: Any) -> Journey:
    """Look at the rows once for this company (see `_refresh`)."""
    return (await _refresh(hub, company))[0]


async def _refresh(hub: Any, company: Any) -> tuple[Journey, bool]:
    """Record the stages reached; when one is new write the state, tell the stream and ask for the
    one line. (the journey, whether a stage changed)"""
    ids = await hub.companies.ids()
    changed = False
    async with hub.db.tx(ids) as tx:
        plan = await plan_of(tx, company.id)
        have = {
            r["key"]: r
            for r in await tx.all(
                "SELECT * FROM growth.journey_stages WHERE company_id = :co", co=company.id
            )
        }
        state = await tx.first(
            "SELECT * FROM growth.journey_state WHERE company_id = :co", co=company.id
        )
        newly: list[dict[str, Any]] = []
        for st in plan:
            if st["key"] in have:
                continue
            found = await evaluate(tx, company.id, st["rule"])
            if found is None:
                continue
            at, kind, ref = found
            await tx.exec(
                """INSERT INTO growth.journey_stages (company_id, key, reached_at, evidence_kind,
                                                      evidence_ref)
                   VALUES (:co, :k, :at, :kind, :ref) ON CONFLICT (company_id, key) DO NOTHING""",
                co=company.id,
                k=st["key"],
                at=at,
                kind=kind,
                ref=ref,
            )
            have[st["key"]] = {
                "key": st["key"],
                "reached_at": at,
                "evidence_kind": kind,
                "evidence_ref": ref,
            }
            newly.append(st)
        current = current_of(plan, have)
        changed = bool(newly) or state is None
        if changed:
            await tx.exec(
                """INSERT INTO growth.journey_state (company_id, current_key, changed_at)
                   VALUES (:co, :cur, now())
                   ON CONFLICT (company_id) DO UPDATE
                   SET current_key = :cur, changed_at = now(), updated_at = now()""",
                co=company.id,
                cur=current,
            )
            if state is not None:  # the first look is the baseline: no flood of past stages
                for st in newly:
                    await events.emit(
                        tx,
                        company.code,
                        "journey.stage",
                        st["key"],
                        {
                            "stage": st["key"],
                            "title_fa": st["title_fa"],
                            "current": current,
                            "reached_at": have[st["key"]]["reached_at"].isoformat(),
                        },
                    )
    if changed:
        line = await next_line(hub, company.code, company.name_fa or company.code, plan, have)
        target = next_target(plan, have)
        async with hub.db.tx(ids) as tx:
            await tx.exec(
                """UPDATE growth.journey_state SET next_fa = :n, next_for = :f, updated_at = now()
                   WHERE company_id = :co""",
                co=company.id,
                n=line,
                f=target["key"] if target else None,
            )
    async with hub.db.tx(ids) as tx:
        return await read(tx, company.id, company.code), changed


async def tick(hub: Any) -> int:
    """Every company once (the scheduled pass); returns how many had a stage change."""
    n = 0
    for company in await hub.companies.all():
        if company.kind == "holding":
            continue
        try:
            _, changed = await _refresh(hub, company)
        except Exception:  # noqa: BLE001 - one company never stops the others
            log.warning("journey refresh failed", extra={"company": company.code})
            continue
        n += 1 if changed else 0
    return n


async def board(hub: Any) -> JourneyBoard:
    journeys: list[Journey] = []
    events_: list[JourneyEvent] = []
    for company in await hub.companies.all():
        if company.kind == "holding":
            continue
        j = await refresh_company(hub, company)
        journeys.append(j)
        events_ += [
            JourneyEvent(at=s.reached_at, company=company.code, stage=s.key, title_fa=s.title_fa)
            for s in j.stages
            if s.reached_at is not None
        ]
    events_.sort(key=lambda e: e.at, reverse=True)
    return JourneyBoard(journeys=journeys, timeline=events_[:200])


def not_found(code: str) -> ApiError:
    return ApiError(404, "not_found", f"company {code}")
