"""Morning report (prompt 04 §6.5): rule-based, no model behind it. Real
numbers of every box and every company, written by HQ-SYS as a Deliverable
in the holding, plus a 🔵 notification. The model-written version arrives
with prompt 5; this one stays as its factual base."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from hq_api.db import Tx
from hq_api.domain import feedback as FB
from hq_api.worker.jalali import jalali_long, jalali_str

RISK_FA = {"high": "بالا", "medium": "متوسط", "low": "کم"}


def title(day: date) -> str:
    return f"گزارش صبحگاهی {jalali_str(day)} / {day.isoformat()}"


def work_title(day: date) -> str:
    return f"Morning report {day.isoformat()}"


async def gather(tx: Tx, now: datetime, tz: str) -> dict[str, Any]:
    z = ZoneInfo(tz)
    today = now.astimezone(z).date()
    y_start = datetime.combine(today - timedelta(days=1), time.min, z).astimezone(UTC)
    y_end = datetime.combine(today, time.min, z).astimezone(UTC)
    risks = {
        r["risk"]: r["n"]
        for r in await tx.all(
            "SELECT risk, count(*) AS n FROM cartable.decisions WHERE status = 'pending' GROUP BY risk"
        )
    }
    deliverables = await tx.one(
        """SELECT count(*) FILTER (WHERE dl.created_at >= now() - interval '24 hours') AS new_24h,
                  count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM cartable.ratings r
                                                     WHERE r.deliverable_id = dl.id)) AS unrated
           FROM cartable.deliverables dl"""
    )
    unread = await tx.scalar("SELECT COALESCE(sum(last_seq - owner_read_seq), 0) FROM msg.threads")
    companies = await tx.all(
        """SELECT c.code, c.name_fa, c.kind, COALESCE(k.state, 'released') AS kill_switch,
                  (SELECT count(*) FROM cartable.decisions d WHERE d.company_id = c.id AND d.status = 'pending')
                      AS decisions_pending,
                  (SELECT count(*) FROM work.work w WHERE w.company_id = c.id
                     AND w.status IN ('queued', 'in_progress', 'waiting')) AS work_open,
                  (SELECT count(*) FROM work.work w WHERE w.company_id = c.id
                     AND w.status IN ('queued', 'in_progress', 'waiting') AND w.due_at < now()) AS work_overdue,
                  (SELECT count(*) FROM cartable.deliverables dl WHERE dl.company_id = c.id
                     AND dl.created_at >= now() - interval '24 hours') AS deliverables_new,
                  (SELECT COALESCE(sum(COALESCE(x.input_tokens, 0) + COALESCE(x.output_tokens, 0)
                                       + COALESCE(x.cache_read_tokens, 0) + COALESCE(x.cache_write_tokens, 0)), 0)
                     FROM llm.calls x WHERE x.company_id = c.id AND x.started_at >= :ys AND x.started_at < :ye)
                      AS tokens_yesterday,
                  (SELECT COALESCE(sum(COALESCE(x.cost_usd, 0) + COALESCE(x.equiv_cost_usd, 0)), 0)
                     FROM llm.calls x WHERE x.company_id = c.id AND x.started_at >= :ys AND x.started_at < :ye)
                      AS usd_yesterday,
                  (SELECT count(*) FROM llm.calls x WHERE x.company_id = c.id
                     AND x.started_at >= :ys AND x.started_at < :ye) AS calls_yesterday
           FROM core.companies c LEFT JOIN control.kill_switches k ON k.company_id = c.id
           WHERE c.status <> 'archived'
           ORDER BY c.kind = 'holding' DESC, c.code""",
        ys=y_start,
        ye=y_end,
    )
    budgets = await tx.all(
        """SELECT c.code AS company, b.scope_type, b.scope_ref, b.period, b.alert_level
           FROM llm.budgets b JOIN core.companies c ON c.id = b.company_id
           WHERE b.enabled AND b.alert_level > 0 ORDER BY b.alert_level DESC, c.code"""
    )
    return {
        "today": today,
        "risks": risks,
        "deliverables": deliverables,
        "unread": int(unread or 0),
        "companies": companies,
        "budgets": budgets,
        # Saturdays (prompt 10 §8.3): the week's support figures of a company
        # without a support lead, figures only.
        "support_week": await FB.morning_lines(tx, today) if today.weekday() == 5 else [],
        # Prompt 12 §9.1.7: one line per substitute player (the month's use).
        "substitutes": await _substitute_lines(tx),
        # ⟨1.5⟩ prompt 12 §8, §11: rule-only lines (the waste of yesterday, the
        # owner's waiting cards by age); no model, no outside call
        **await _p12b_lines(tx, today, now),
    }


async def _p12b_lines(tx: Tx, today: date, now: datetime) -> dict[str, Any]:
    from hq_api.domain import notes as NOTES
    from hq_api.domain import waste as WASTE

    yesterday = await WASTE.day_of(tx, today - timedelta(days=1), None)
    return {
        "waste_line": WASTE.morning_line(yesterday),
        "reminders_line": await NOTES.morning_line(tx, now),
    }


async def _substitute_lines(tx: Tx) -> list[str]:
    from hq_api.domain import substitutes

    return [f"- {line}" for line in await substitutes.report_lines(tx)]


def render(data: dict[str, Any]) -> tuple[str, str]:
    """(summary, markdown body) in Persian; numbers in Latin digits (D1)."""
    today: date = data["today"]
    risks = data["risks"]
    pending = sum(risks.values())
    dl = data["deliverables"]
    summary = (
        f"{pending} تصمیم در انتظار، {dl['new_24h']} خروجی تازه ({dl['unrated']} بی‌امتیاز)، "
        f"{data['unread']} پیام نخوانده."
    )
    lines = [
        f"# گزارش صبحگاهی — {jalali_long(today)} ({today.isoformat()})",
        "",
        "> نسخه‌ی قاعده‌محور، بدون مدل: همه‌ی عددها مستقیم از دیتابیس هاب.",
        "",
        "## صندوق‌ها",
        f"- **کارتابل تصمیم:** {pending} مورد در انتظار"
        + (
            " ("
            + "، ".join(
                f"ریسک {RISK_FA[k]}: {risks[k]}" for k in ("high", "medium", "low") if risks.get(k)
            )
            + ")"
            if pending
            else ""
        ),
        f"- **کارتابل خروجی:** {dl['new_24h']} خروجی در ۲۴ ساعت گذشته؛ {dl['unrated']} خروجی هنوز امتیاز ندارد",
        f"- **پیام‌ها:** {data['unread']} پیام نخوانده",
        *[data[k] for k in ("reminders_line", "waste_line") if data.get(k)],
        "",
        "## شرکت‌ها",
        "| شرکت | تصمیم در انتظار | کار باز | عقب‌افتاده | خروجی تازه "
        "| فراخوانی مدل دیروز | توکن دیروز | هزینه‌ی دیروز (USD) | کلید توقف |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in data["companies"]:
        usd = Decimal(c["usd_yesterday"]).quantize(Decimal("0.0001"))
        lines.append(
            f"| {c['name_fa'] or c['code']} ({c['code']}) | {c['decisions_pending']} | {c['work_open']} | "
            f"{c['work_overdue']} | {c['deliverables_new']} | {c['calls_yesterday']} | {c['tokens_yesterday']} | "
            f"{usd} | {'فعال' if c['kill_switch'] == 'engaged' else '—'} |"
        )
    lines += ["", "## بودجه‌ها"]
    if data["budgets"]:
        for b in data["budgets"]:
            lines.append(
                f"- {b['company']} · {b['scope_type']}:{b['scope_ref']} ({b['period']}): به {b['alert_level']}٪ رسیده"
            )
    else:
        lines.append("- هیچ بودجه‌ای به آستانه‌ی هشدار (۷۰٪) نرسیده است.")
    if data.get("support_week"):
        lines += ["", "## پشتیبانی هفته (شرکت‌های بی‌سرپرست پشتیبانی)", *data["support_week"]]
    if data.get("substitutes"):
        lines += ["", "## بازیکن‌های ذخیره", *data["substitutes"]]
    engaged = [c["code"] for c in data["companies"] if c["kill_switch"] == "engaged"]
    if engaged:
        lines += ["", f"**کلید توقف فعال:** {', '.join(engaged)}"]
    return summary, "\n".join(lines) + "\n"


# ---------------------------------------------------- the rewrite (prompt 05 §6)
REWRITE_SYSTEM = (
    "You are the editor of the owner's morning report of the CoinePro holding. Rewrite the report "
    "you are given as clear, warm, concise Persian prose for the owner (مدیر کل): lead with what "
    "matters, group related items, keep every heading's meaning. Rules: use ONLY the facts and the "
    "numbers that are in the report - never add, drop, round or recompute a number; keep every code "
    "and ref (W-…, D-…, O-…, TY-CEO) exactly as written; write numbers, money, tokens and codes in "
    "Latin digits as they are. No preamble, no closing remarks: only the report in markdown."
)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _numbers(text: str) -> set[str]:
    import re

    return set(re.findall(r"\d+(?:[.,/]\d+)*", text.translate(_DIGITS)))


def same_numbers(source: str, rewrite: str) -> bool:
    """Every number of the rewrite appears in the source (no new figures)."""
    allowed = _numbers(source)
    return all(n in allowed or n.replace(",", "") in allowed for n in _numbers(rewrite))
