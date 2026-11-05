"""The holding's usage in the advisor's words (contract §33.1 ⟨1.15⟩).

Numbers by code, words by a model:

- `build_pack` is code. One `UsagePack` of a period from the Token Treasury (the
  domains of `spend.by_domain`, the companies, the heaviest runs), the voice meter
  (`talk.voice_usage`), the lines (§30) and the ads (§31.6), against the period
  before it, with the anomalies a rule finds.
- `write_words` is ONE router call (task class `usage_report`, a mid model, low
  effort, at most 4 000 output tokens, a strict schema `{lines_fa: [3..8],
  saving_fa}`): what happened, where it was high and why, one saving. Code checks
  the answer: plain Persian, and every figure of the text is one of the pack's
  (a text with a made-up figure is never kept). When the model cannot answer, a
  short text is written by code (`words: "code"`), so a report always exists.
- A report is stored as UR-0001 ...; the daily one is made at 07:55 (Tehran) and
  its first three lines reach the morning summary; the weekly one (Saturday 09:00)
  is posted in the advisor's thread `A` with the pack under «جزئیات». The talk
  reads the latest stored text aloud: no new model call.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from hq_api import audit, events, workflows_client
from hq_api.db import Tx
from hq_api.domain import humanize, spend
from hq_api.domain.gov_common import owner_tz, zone
from hq_api.principal import Principal

log = logging.getLogger("hq_api.usage")


def mid_model() -> str:
    """The mid model of the one-sentence calls (the automations' choice), read lazily."""
    from hq_api.domain.automations import MODEL

    return MODEL


TASK_CLASS = "usage_report"
MAX_OUTPUT_TOKENS = 4000
SERVICE = Principal(kind="service", code="usage", role="service")
PERIODS = ("day", "week")
SPAN_DAYS = {"day": 1, "week": 7}
TOP_RUNS = 5
LINES_MIN, LINES_MAX = 3, 8
MORNING_LINES = 3
# a domain that is the largest share must never be the technical ones (prompt 20 finding 6)
TECH_DOMAINS = ("catalogue", "oversight", "server")
SPIKE_RATIO = 2.0  # tokens at least this many times the period before
VOICE_SHARE = 0.25  # the voice meter above this share of the period's spend
FAILED_SHARE = 0.10  # failed calls above this share of the period's calls

Ask = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


# ------------------------------------------------------------------- shapes --
class UsageDomainRow(BaseModel):
    domain: str
    tokens: int
    usd_equiv: float
    share: float


class UsageCompanyRow(BaseModel):
    company: str
    tokens: int
    usd_equiv: float
    share: float


class UsageRunRow(BaseModel):
    ref: str
    role: str | None
    tokens: int


class UsageLines(BaseModel):
    runs: int
    tokens: int


class UsageVsPrev(BaseModel):
    tokens_pct: float | None
    usd_pct: float | None


class UsageAnomaly(BaseModel):
    kind: Literal["tech_domain_largest", "spike", "voice_high", "failed_calls"]
    note: str


class UsagePack(BaseModel):
    period: Literal["day", "week"]
    from_: datetime = Field(alias="from")
    to: datetime
    by_domain: list[UsageDomainRow]
    by_company: list[UsageCompanyRow]
    top_runs: list[UsageRunRow]
    voice_usd: float
    lines: UsageLines
    ads_spend_usd: float
    vs_prev: UsageVsPrev
    anomalies: list[UsageAnomaly]

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class UsageText(BaseModel):
    lines_fa: list[str]
    saving_fa: str


class UsageReport(BaseModel):
    ref: str
    period: Literal["day", "week"]
    from_: datetime = Field(alias="from")
    to: datetime
    pack: UsagePack
    text: UsageText | None
    words: Literal["model", "code"] = "model"
    at: datetime

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


# ------------------------------------------------------------------ windows --
def window(period: str, tz: str, now: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the last COMPLETE period in the owner's zone: yesterday for a
    day, the 7 days before today for a week (both in UTC)."""
    z = zone(tz)
    today = now.astimezone(z).date()
    end = datetime.combine(today, time(0), z)
    start = datetime.combine(today - timedelta(days=SPAN_DAYS[period]), time(0), z)
    return start.astimezone(UTC), end.astimezone(UTC)


def _pct(now: float, before: float) -> float | None:
    return round(100.0 * (now - before) / before, 1) if before > 0 else None


# --------------------------------------------------------------------- pack --
async def _totals(tx: Tx, start: datetime, end: datetime) -> tuple[int, float, int, int]:
    """(tokens, usd, calls, failed calls) of every call in [start, end)."""
    row = await tx.one(
        f"""SELECT {spend.TOKENS_SQL} AS tokens,
                   COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd,
                   count(*) AS calls,
                   count(*) FILTER (WHERE c.status IN ('error', 'timeout')) AS failed
            FROM llm.calls c WHERE c.started_at >= :s AND c.started_at < :e""",  # noqa: S608
        s=start,
        e=end,
    )
    return int(row["tokens"]), float(row["usd"]), int(row["calls"]), int(row["failed"])


async def build_pack(tx: Tx, period: str, tz: str, now: datetime) -> UsagePack:
    start, end = window(period, tz, now)
    prev_start = start - (end - start)
    tokens, usd, calls, failed = await _totals(tx, start, end)
    p_tokens, p_usd, _, _ = await _totals(tx, prev_start, start)

    domains = await spend.by_domain(tx, start, end)
    by_domain = [
        UsageDomainRow(
            domain=d["domain"],
            tokens=d["tokens"],
            usd_equiv=round(float(d["usd"]), 4),
            share=round(d["share_pct"] / 100.0, 4),
        )
        for d in domains
    ]
    rows = await tx.all(
        f"""SELECT co.code AS company, {spend.TOKENS_SQL} AS tokens,
                   COALESCE(sum(COALESCE(c.cost_usd, 0) + COALESCE(c.equiv_cost_usd, 0)), 0) AS usd
            FROM llm.calls c JOIN core.companies co ON co.id = c.company_id
            WHERE c.started_at >= :s AND c.started_at < :e
            GROUP BY co.code ORDER BY tokens DESC, co.code LIMIT 20""",  # noqa: S608
        s=start,
        e=end,
    )
    by_company = [
        UsageCompanyRow(
            company=r["company"],
            tokens=int(r["tokens"]),
            usd_equiv=round(float(r["usd"]), 4),
            share=round(int(r["tokens"]) / tokens, 4) if tokens else 0.0,
        )
        for r in rows
    ]
    runs = await tx.all(
        """SELECT COALESCE(w.ref, 'run-' || substr(r.id::text, 1, 8)) AS ref, r.charter_role AS role,
                  r.input_tokens + r.output_tokens + r.cache_read_tokens + r.cache_write_tokens AS tokens
           FROM agents.runs r LEFT JOIN work.work w ON w.id = r.work_id
           WHERE r.created_at >= :s AND r.created_at < :e
           ORDER BY tokens DESC, r.id LIMIT :n""",
        s=start,
        e=end,
        n=TOP_RUNS,
    )
    top_runs = [
        UsageRunRow(ref=r["ref"], role=r["role"], tokens=int(r["tokens"]))
        for r in runs
        if int(r["tokens"]) > 0
    ]
    voice = await tx.scalar(
        "SELECT COALESCE(sum(usd), 0) FROM talk.voice_usage WHERE at >= :s AND at < :e",
        s=start,
        e=end,
    )
    ln = await tx.one(
        """SELECT count(*) AS runs, COALESCE(sum(tokens), 0) AS tokens FROM lines.runs
           WHERE at >= :s AND at < :e AND NOT dry""",
        s=start,
        e=end,
    )
    z = zone(tz)
    ads = await tx.scalar(
        "SELECT COALESCE(sum(spend), 0) FROM growth.ad_daily WHERE day >= :a AND day < :b",
        a=start.astimezone(z).date(),
        b=end.astimezone(z).date(),
    )
    vs = UsageVsPrev(tokens_pct=_pct(tokens, p_tokens), usd_pct=_pct(usd, p_usd))
    anomalies = _anomalies(by_domain, vs, float(voice or 0), usd, calls, failed, p_tokens)
    return UsagePack(
        period=period,
        **{"from": start},
        to=end,
        by_domain=by_domain,
        by_company=by_company,
        top_runs=top_runs,
        voice_usd=round(float(voice or 0), 4),
        lines=UsageLines(runs=int(ln["runs"]), tokens=int(ln["tokens"])),
        ads_spend_usd=round(float(ads or 0), 2),
        vs_prev=vs,
        anomalies=anomalies,
    )


def _anomalies(
    by_domain: list[UsageDomainRow],
    vs: UsageVsPrev,
    voice_usd: float,
    usd: float,
    calls: int,
    failed: int,
    prev_tokens: int,
) -> list[UsageAnomaly]:
    out: list[UsageAnomaly] = []
    if by_domain and by_domain[0].domain in TECH_DOMAINS and by_domain[0].share >= 0.5:
        title = spend.DOMAIN_FA.get(by_domain[0].domain, by_domain[0].domain)
        out.append(
            UsageAnomaly(
                kind="tech_domain_largest",
                note=f"بیشترین سهم مصرف با «{title}» است، نه با کار شرکت‌ها.",
            )
        )
    if prev_tokens > 0 and vs.tokens_pct is not None and vs.tokens_pct >= (SPIKE_RATIO - 1) * 100:
        out.append(
            UsageAnomaly(kind="spike", note=f"مصرف توکن {vs.tokens_pct:g}٪ بیشتر از دوره‌ی قبل است.")
        )
    if usd > 0 and voice_usd / usd >= VOICE_SHARE:
        out.append(UsageAnomaly(kind="voice_high", note="هزینه‌ی صدا سهم بزرگی از مصرف دارد."))
    if calls and failed / calls >= FAILED_SHARE:
        out.append(
            UsageAnomaly(kind="failed_calls", note="بخش قابل‌توجهی از فراخوانی‌های مدل ناموفق بود.")
        )
    return out


# -------------------------------------------------------------------- words --
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMBER = re.compile(r"\d[\d,٬]*(?:[.٫]\d+)?")


def _numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUMBER.findall(text.translate(_DIGITS)):
        try:
            out.append(float(m.replace(",", "").replace("٬", "").replace("٫", ".")))
        except ValueError:
            continue
    return out


def _leaves(x: Any, out: list[float]) -> None:
    if isinstance(x, bool):
        return
    if isinstance(x, int | float):
        out.append(float(x))
    elif isinstance(x, dict):
        for v in x.values():
            _leaves(v, out)
    elif isinstance(x, list):
        for v in x:
            _leaves(v, out)


def allowed_numbers(pack: UsagePack) -> list[float]:
    """Every figure the text may mention: the pack's numbers, their percentages
    and roundings, and the dates of the period."""
    raw: list[float] = []
    _leaves(pack.model_dump(mode="json", by_alias=True, exclude={"from_", "to"}), raw)
    for d in (pack.from_, pack.to):
        raw += [float(d.year), float(d.month), float(d.day)]
    out: list[float] = []
    for v in raw:
        out += [v, abs(v), round(v), round(v, 1), round(v, 2), v * 100, round(v * 100)]
    # a total the reader may add up: tokens and money of the whole
    out.append(float(sum(r.tokens for r in pack.by_domain)))
    out.append(float(sum(r.usd_equiv for r in pack.by_domain)))
    return out


def numbers_ok(text: str, pack: UsagePack) -> bool:
    """True when every figure of `text` above 10 is one of the pack's (within one
    percent). Small counts («سه خط») are words, not figures."""
    allowed = allowed_numbers(pack)
    for n in _numbers(text):
        if n <= 10:
            continue
        if not any(abs(a - n) <= max(0.51, 0.01 * abs(a)) for a in allowed):
            return False
    return True


def _plain(s: str) -> str | None:
    t = humanize.humanize(" ".join(str(s).split()))
    if not t or humanize.check(t) or humanize.persian_share(t) < 0.4:
        return None
    return t


def checked_text(raw: Any, pack: UsagePack) -> UsageText | None:
    """The model's answer, or None when it is not what the report may say."""
    if not isinstance(raw, dict) or set(raw) - {"lines_fa", "saving_fa"}:
        return None
    lines = raw.get("lines_fa")
    saving = raw.get("saving_fa")
    if not isinstance(lines, list) or not isinstance(saving, str):
        return None
    if not LINES_MIN <= len(lines) <= LINES_MAX:
        return None
    out: list[str] = []
    for x in lines:
        t = _plain(x) if isinstance(x, str) else None
        if t is None or len(t) > 300:
            return None
        out.append(t)
    s = _plain(saving)
    if s is None or len(s) > 400:
        return None
    if not numbers_ok(" ".join([*out, s]), pack):
        return None
    return UsageText(lines_fa=out, saving_fa=s)


def fmt_tokens(n: int) -> str:
    return f"{n:,}"


def fallback_text(pack: UsagePack) -> UsageText:
    """The short report written by code when the model gave nothing usable."""
    tokens = sum(r.tokens for r in pack.by_domain)
    usd = sum(r.usd_equiv for r in pack.by_domain)
    span = "دیروز" if pack.period == "day" else "هفته‌ی گذشته"
    first = f"{span} {fmt_tokens(tokens)} توکن مصرف شد (معادل حدود {usd:.2f} دلار)"
    if pack.vs_prev.tokens_pct is not None:
        more = pack.vs_prev.tokens_pct >= 0
        first += f"؛ {abs(pack.vs_prev.tokens_pct):g}٪ {'بیشتر' if more else 'کمتر'} از دوره‌ی قبل."
    else:
        first += "."
    lines = [first]
    top = pack.by_domain[0] if pack.by_domain else None
    if top is not None:
        title = spend.DOMAIN_FA.get(top.domain, top.domain)
        lines.append(f"بیشترین سهم با «{title}» بود ({round(top.share * 100, 1):g}٪).")
    else:
        lines.append("مصرفی ثبت نشد.")
    lines += [a.note for a in pack.anomalies[:2]] or ["نکته‌ی غیرعادی دیده نشد."]
    if pack.ads_spend_usd > 0:
        lines.append(f"هزینه‌ی تبلیغات {pack.ads_spend_usd:.2f} دلار بود.")
    while len(lines) < LINES_MIN:
        lines.append("مصرف صدا و خط‌های تولید در جزئیات آمده است.")
    saving = "برای صرفه‌جویی، از بخش پرمصرف شروع کنید."
    if top is not None:
        saving = f"برای صرفه‌جویی، اول سقف مصرف «{spend.DOMAIN_FA.get(top.domain, top.domain)}» را ببینید."
    return UsageText(lines_fa=[_plain(x) or x for x in lines[:LINES_MAX]], saving_fa=saving)


MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "lines_fa": {
                        "type": "array",
                        "minItems": LINES_MIN,
                        "maxItems": LINES_MAX,
                        "items": {"type": "string", "maxLength": 300},
                    },
                    "saving_fa": {"type": "string", "maxLength": 400},
                },
                "required": ["lines_fa", "saving_fa"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}
MODEL_SYSTEM = (
    "You are the holding's general advisor writing the usage report for the owner, in plain, warm, "
    "human Persian (the owner is not technical: no code words, no English words, no ids). "
    'Answer exactly {"routes": [{"lines_fa": [3 to 8 short sentences], "saving_fa": one sentence}]}. '
    "lines_fa: what happened in the period, where the use was high and why (from the pack only), "
    "and how it compares to the period before. saving_fa: ONE concrete saving the owner could make. "
    "Use ONLY the figures that are in the pack, copied as they are (you may round); never compute a "
    "new total, never invent a figure, a company or a cause the pack does not show. "
    "If the pack shows an anomaly, name it plainly. Put no preamble."
)


def model_request(holding_code: str, pack: UsagePack) -> dict[str, Any]:
    return {
        "company_code": holding_code,
        "actor_ref": "usage",
        "task_class": TASK_CLASS,
        "priority": 3,
        "model": mid_model(),  # a mid model
        "effort": "low",
        "system": MODEL_SYSTEM,
        "prompt": json.dumps(
            {"period": pack.period, "pack": pack.model_dump(mode="json", by_alias=True)},
            ensure_ascii=False,
        ),
        "json_schema": MODEL_SCHEMA,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 90,
        # the advisor's voice: the Token Treasury books it under the advisor's domain
        "meta": {"purpose": "usage_report", "charter": "advisor"},
    }


def first_route(answer: dict[str, Any] | None) -> Any:
    routes = (answer or {}).get("routes")
    return routes[0] if isinstance(routes, list) and len(routes) == 1 else None


async def write_words(
    hub: Any, holding_code: str, pack: UsagePack, ask: Ask | None = None
) -> tuple[UsageText, Literal["model", "code"]]:
    call = ask or (lambda req: workflows_client.route_order(hub, req, 100.0))
    try:
        answer = await call(model_request(holding_code, pack))
    except Exception:  # noqa: BLE001 - the plain text by code answers
        log.warning("usage report: the model call failed")
        answer = None
    text = checked_text(first_route(answer), pack)
    if text is None:
        return fallback_text(pack), "code"
    return text, "model"


# ------------------------------------------------------------------ storage --
def render(r: dict[str, Any]) -> UsageReport:
    pack = r["pack"] if isinstance(r["pack"], dict) else json.loads(r["pack"])
    text = r["text"] if isinstance(r["text"], dict | type(None)) else json.loads(r["text"])
    return UsageReport(
        ref=r["ref"],
        period=r["period"],
        **{"from": r["from_at"]},
        to=r["to_at"],
        pack=UsagePack.model_validate(pack),
        text=UsageText.model_validate(text) if text else None,
        words=r["words"],
        at=r["at"],
    )


async def latest(tx: Tx, period: str | None = None) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT * FROM sales.usage_reports WHERE (CAST(:p AS text) IS NULL OR period = :p)
           ORDER BY at DESC, ref DESC LIMIT 1""",
        p=period,
    )


async def make(
    hub: Any,
    period: str,
    *,
    made_by: Literal["schedule", "owner"],
    now: datetime | None = None,
    ask: Ask | None = None,
    who: Principal = SERVICE,
) -> dict[str, Any]:
    """The pack by code, the words by one model call, the report stored. A scheduled
    report exists once per period (a second tick finds it)."""
    now = now or datetime.now(UTC)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tz = await owner_tz(tx)
        start, _ = window(period, tz, now)
        if made_by == "schedule":
            have = await tx.first(
                "SELECT * FROM sales.usage_reports WHERE period = :p AND from_at = :f AND made_by = 'schedule'",
                p=period,
                f=start,
            )
            if have is not None:
                found: dict[str, Any] = have
                return found
        pack = await build_pack(tx, period, tz, now)
    text, words = await write_words(hub, holding.code, pack, ask)  # the slow part, outside a tx
    async with hub.db.tx(await hub.companies.ids()) as tx:
        row = await tx.first(
            """INSERT INTO sales.usage_reports (company_id, period, from_at, to_at, pack, text, words,
                   made_by)
               VALUES (:co, :p, :f, :t, CAST(:pack AS jsonb), CAST(:text AS jsonb), :w, :by)
               ON CONFLICT (period, from_at) WHERE made_by = 'schedule' DO NOTHING RETURNING *""",
            co=holding.id,
            p=period,
            f=pack.from_,
            t=pack.to,
            pack=json.dumps(pack.model_dump(mode="json", by_alias=True), ensure_ascii=False),
            text=json.dumps(text.model_dump(), ensure_ascii=False),
            w=words,
            by=made_by,
        )
        if row is None:  # a second tick won the race
            won: dict[str, Any] = await tx.one(
                "SELECT * FROM sales.usage_reports WHERE period = :p AND from_at = :f AND made_by = 'schedule'",
                p=period,
                f=pack.from_,
            )
            return won
        await audit.record(
            tx,
            who,
            company_id=holding.id,
            action="usage.report",
            action_class="A0",
            target_kind="usage_report",
            target_ref=row["ref"],
            summary=f"{period} report, words by {words}",
        )
        if made_by == "schedule" and period == "week":
            ref = await post_weekly(tx, row)
            if ref is not None:
                row = await tx.one(
                    """UPDATE sales.usage_reports SET delivered = delivered || CAST(:d AS jsonb)
                       WHERE id = :id RETURNING *""",
                    d=json.dumps({"thread": ref}),
                    id=row["id"],
                )
        await events.emit(tx, holding.code, "usage.report", row["ref"], {"period": period})
    made: dict[str, Any] = row
    return made


# ----------------------------------------------------------------- delivery --
def details_md(pack: UsagePack) -> str:
    """The pack under «جزئیات»: the figures, one line each (numbers in Latin digits)."""
    out = ["", "**جزئیات**"]
    for d in pack.by_domain:
        out.append(
            f"- {spend.DOMAIN_FA.get(d.domain, d.domain)}: {fmt_tokens(d.tokens)} توکن "
            f"({round(d.share * 100, 1):g}٪)، حدود {d.usd_equiv:.2f} دلار"
        )
    if pack.by_company:
        out.append(
            "- شرکت‌ها: "
            + "، ".join(f"{c.company} {fmt_tokens(c.tokens)}" for c in pack.by_company[:6])
        )
    out.append(
        f"- صدا: {pack.voice_usd:.2f} دلار · خط‌های تولید: {pack.lines.runs} اجرا، "
        f"{fmt_tokens(pack.lines.tokens)} توکن"
    )
    out.append(f"- تبلیغات: {pack.ads_spend_usd:.2f} دلار")
    return "\n".join(out)


def message_md(text: UsageText, pack: UsagePack, ref: str) -> str:
    body = [
        "**گزارش مصرف هفته**",
        "",
        *[f"- {x}" for x in text.lines_fa],
        "",
        f"**یک صرفه‌جویی:** {text.saving_fa}",
    ]
    return "\n".join(body) + "\n" + details_md(pack) + f"\n\n({ref})"


async def post_weekly(tx: Tx, row: dict[str, Any]) -> str | None:
    """The weekly report as a message of the advisor's thread `A`; None without
    that thread."""
    from hq_api.domain import decisions as D

    rep = render(row)
    if rep.text is None:
        return None
    return await D.post_system_message(
        tx, "A", message_md(rep.text, rep.pack, row["ref"]), {"usage_report": row["ref"]}
    )


async def morning_lines(tx: Tx, tz: str, today: date) -> list[str]:
    """The first three lines of yesterday's daily report, for the morning summary
    (none when there is none yet)."""
    z = zone(tz)
    end = datetime.combine(today, time(0), z).astimezone(UTC)
    row = await tx.first(
        """SELECT * FROM sales.usage_reports WHERE period = 'day' AND to_at = :e
           ORDER BY at DESC LIMIT 1""",
        e=end,
    )
    if row is None or not row["text"]:
        return []
    text = row["text"] if isinstance(row["text"], dict) else json.loads(row["text"])
    out = [_plain(x) for x in text.get("lines_fa", [])[:MORNING_LINES]]
    return [x for x in out if x]


def spoken(row: dict[str, Any]) -> tuple[str, str]:
    """(say, show) of a stored report, for the talk: its lines and its one saving,
    read as they were written."""
    text = row["text"] if isinstance(row["text"], dict) else json.loads(row["text"])
    lines = [str(x) for x in text.get("lines_fa", [])]
    saving = str(text.get("saving_fa") or "")
    say = " ".join([*lines, f"یک صرفه‌جویی: {saving}" if saving else ""]).strip()
    show = "\n".join(
        [
            f"**گزارش مصرف ({'روزانه' if row['period'] == 'day' else 'هفتگی'})**",
            "",
            *[f"- {x}" for x in lines],
        ]
        + ([f"\n**یک صرفه‌جویی:** {saving}"] if saving else [])
    )
    return say, show
