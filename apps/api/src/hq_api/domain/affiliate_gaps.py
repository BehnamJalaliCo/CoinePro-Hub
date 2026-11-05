"""Affiliate follow-up: commission due against received (contract §33.5 ⟨1.15⟩).

From the radar's daily rows (§19.1, `revenue.days`) code computes, per account and month,
what is **due** (the commission the exchange's own figures show for the month) and compares
it with what was **received** (said by the owner or the FIN manager: the exchange pays
outside the hub; `sales.affiliate_receipts`). After the exchange's settlement window
(`seed/sales/affiliate.yaml`, data) a gap above `gap_pct` (5%) opens a follow-up: a planner
item for the company's FIN manager with the figures and a message drafted for the exchange
(task class `sales_followup`, never sent). A receipt that brings the gap under the line
closes it. A month with a day not pulled completely is not judged (a figure is never guessed).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from hq_api import audit, workflows_client
from hq_api.db import Tx
from hq_api.domain import humanize, leads
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.affiliate_gaps")


def mid_model() -> str:
    """The mid model of the one-sentence calls (the automations' choice), read lazily."""
    from hq_api.domain.automations import MODEL

    return MODEL

SEED = Path(__file__).resolve().parents[3] / "seed" / "sales" / "affiliate.yaml"
SERVICE = Principal(kind="service", code="sales", role="service")
MONTHS_BACK = 12
Ask = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class SalesAffiliateGap(BaseModel):
    company: str
    account: str
    exchange: str
    month: date
    due_usdt: Decimal
    received_usdt: Decimal
    gap_usdt: Decimal
    gap_pct: float
    state: Literal["waiting", "ok", "open", "closed"]
    settles_on: date
    work_ref: str | None
    draft_fa: str | None


class SalesAffiliateReceipt(BaseModel):
    company: str
    account: str
    month: date
    received_usdt: Decimal
    note_fa: str | None
    at: datetime


def settings() -> dict[str, Any]:
    data = yaml.safe_load(SEED.read_text(encoding="utf-8")) or {}
    window = data.get("settlement_window_days") or {}
    return {
        "gap_pct": float(data.get("gap_pct", 5)),
        "windows": {str(k): int(v) for k, v in window.items()},
    }


def window_days(exchange: str, cfg: dict[str, Any] | None = None) -> int:
    w = (cfg or settings())["windows"]
    return int(w.get(exchange, w.get("default", 15)))


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def settles_on(month: date, exchange: str, cfg: dict[str, Any] | None = None) -> date:
    """The day after which the month's commission should have been paid."""
    return next_month(month) + timedelta(days=window_days(exchange, cfg))


def parse_month(text: str) -> date:
    m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])(?:-01)?", text.strip())
    if m is None:
        raise ApiError(
            422, "validation_failed", fields={"month": "YYYY-MM"},
            message_fa="ماه را به شکل 2026-10 بنویسید.",
        )  # fmt: skip
    return date(int(m.group(1)), int(m.group(2)), 1)


# ------------------------------------------------------------------- figures --
async def figures(
    tx: Tx, company_id: Any | None, account_id: Any | None, since: date, until: date
) -> list[dict[str, Any]]:
    """Per account and month in [since, until): due (the sum of the complete days), the number
    of days, how many were incomplete, and what was received."""
    return await tx.all(
        """WITH d AS (
               SELECT a.id AS account_id, a.company_id, a.exchange, date_trunc('month', x.day)::date AS month,
                      COALESCE(sum(x.commission_usdt) FILTER (WHERE x.complete), 0) AS due,
                      count(*) AS days, count(*) FILTER (WHERE NOT x.complete) AS incomplete
               FROM revenue.accounts a JOIN revenue.days x ON x.account_id = a.id
               WHERE x.day >= :since AND x.day < :until
                 AND (CAST(:co AS uuid) IS NULL OR a.company_id = :co)
                 AND (CAST(:acc AS uuid) IS NULL OR a.id = :acc)
               GROUP BY a.id, a.company_id, a.exchange, date_trunc('month', x.day)
           )
           SELECT d.*, c.code AS company, a.service_account AS account,
                  COALESCE((SELECT sum(r.received_usdt) FROM sales.affiliate_receipts r
                            WHERE r.account_id = d.account_id AND r.month = d.month), 0) AS received,
                  EXISTS (SELECT 1 FROM sales.affiliate_receipts r
                          WHERE r.account_id = d.account_id AND r.month = d.month) AS told
           FROM d JOIN core.companies c ON c.id = d.company_id
                  JOIN revenue.accounts a ON a.id = d.account_id
           ORDER BY d.month DESC, c.code, a.service_account""",
        co=company_id,
        acc=account_id,
        since=since,
        until=until,
    )


def judge(
    row: dict[str, Any], today: date, cfg: dict[str, Any]
) -> tuple[str, Decimal, float, date]:
    """(state, gap, gap %, settles on) of one account-month: `waiting` before the window or
    while a day is incomplete, `ok` within the line, `open` above it."""
    due = Decimal(row["due"])
    received = Decimal(row["received"])
    gap = due - received
    pct = float(round(gap / due * 100, 4)) if due > 0 else 0.0
    settle = settles_on(row["month"], row["exchange"], cfg)
    if today <= settle or int(row["incomplete"]) > 0 or due <= 0:
        return "waiting", gap, pct, settle
    return ("open" if pct > cfg["gap_pct"] else "ok"), gap, pct, settle


async def stored(tx: Tx, account_id: Any, month: date) -> dict[str, Any] | None:
    return await tx.first(
        "SELECT * FROM sales.affiliate_gaps WHERE account_id = :a AND month = :m", a=account_id, m=month
    )


async def listing(
    tx: Tx, company_id: Any | None, today: date | None = None
) -> list[SalesAffiliateGap]:
    cfg = settings()
    today = today or datetime.now(UTC).date()
    since = month_start(today.replace(year=today.year - 1))
    out: list[SalesAffiliateGap] = []
    for r in await figures(tx, company_id, None, since, next_month(today)):
        state, gap, pct, settle = judge(r, today, cfg)
        g = await stored(tx, r["account_id"], r["month"])
        if g is not None and g["state"] == "closed" and state in ("ok", "waiting"):
            state = "closed"
        out.append(
            SalesAffiliateGap(
                company=r["company"],
                account=r["account"],
                exchange=r["exchange"],
                month=r["month"],
                due_usdt=Decimal(r["due"]),
                received_usdt=Decimal(r["received"]),
                gap_usdt=gap,
                gap_pct=pct,
                state=state,  # type: ignore[arg-type]
                settles_on=settle,
                work_ref=g["work_ref"] if g else None,
                draft_fa=g["draft_fa"] if g else None,
            )
        )
    return out


# -------------------------------------------------------------------- drafts --
SCHEMA = leads.FOLLOWUP_SCHEMA
SYSTEM = (
    "You draft ONE short message in Persian from a company's finance manager to the affiliate "
    "support of an exchange, about a commission that has not been paid in full. "
    'Answer exactly {"routes": [{"draft_fa": <the message>}]}. Polite, plain, at most five '
    "sentences. State the month, the commission due, the amount received and the gap, using ONLY "
    "the figures in the notes, copied as they are; ask them to check the month's settlement. "
    "Never ask for or write a password, a key or a code, invent no figure, promise nothing. "
    "Put no preamble."
)


def request(holding_code: str, g: dict[str, Any], company_name: str) -> dict[str, Any]:
    return {
        "company_code": holding_code,
        "actor_ref": "sales",
        "task_class": leads.TASK_CLASS,
        "priority": 3,
        "model": mid_model(),
        "effort": "low",
        "system": SYSTEM,
        "prompt": json.dumps(
            {
                "company": company_name,
                "exchange": g["exchange"],
                "month": g["month"].isoformat()[:7],
                "due_usdt": f"{Decimal(g['due']):.2f}",
                "received_usdt": f"{Decimal(g['received']):.2f}",
                "gap_usdt": f"{Decimal(g['gap']):.2f}",
                "gap_pct": f"{g['pct']:.1f}",
            },
            ensure_ascii=False,
        ),
        "json_schema": SCHEMA,
        "max_output_tokens": leads.MAX_OUTPUT_TOKENS,
        "timeout_s": 60,
        "meta": {"purpose": "affiliate_gap"},
    }


def figures_ok(text: str, g: dict[str, Any]) -> bool:
    """Every figure of the draft above 10 is one of the gap's own (the month's digits too)."""
    allowed = [
        float(Decimal(g["due"])), float(Decimal(g["received"])), float(Decimal(g["gap"])),
        g["pct"], float(g["month"].year), float(g["month"].month),
    ]  # fmt: skip
    allowed += [round(a) for a in allowed]
    for m in _NUMBER.findall(text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))):
        n = float(m.replace(",", ""))
        if n > 10 and not any(abs(a - n) <= max(0.51, 0.01 * abs(a)) for a in allowed):
            return False
    return True


def fallback_draft(g: dict[str, Any]) -> str:
    return (
        f"سلام؛ کمیسیون ماه {g['month'].isoformat()[:7]} حساب ما {Decimal(g['due']):.2f} تتر بوده و "
        f"{Decimal(g['received']):.2f} تتر به دست ما رسیده است؛ یعنی {Decimal(g['gap']):.2f} تتر "
        "کمتر. لطفاً تسویه‌ی این ماه را بررسی کنید و نتیجه را برای ما بنویسید. سپاسگزارم."
    )


async def draft_for(
    hub: Any, holding_code: str, g: dict[str, Any], company_name: str, ask: Ask | None = None
) -> str:
    call = ask or (lambda r: workflows_client.route_order(hub, r, 70.0))
    try:
        answer = await call(request(holding_code, g, company_name))
    except Exception:  # noqa: BLE001 - the plain text by code
        answer = None
    routes = (answer or {}).get("routes")
    text = leads.clean_draft(routes[0] if isinstance(routes, list) and len(routes) == 1 else None)
    if text is None or not figures_ok(text, g) or humanize.check(text):
        return fallback_draft(g)
    return text


# ---------------------------------------------------------------------- scan --
async def scan(hub: Any, ask: Ask | None = None, now: datetime | None = None) -> dict[str, int]:
    """Open the follow-ups that are due and close the ones that were paid. Idempotent: a
    month opens once; its figures are refreshed while it stays open."""
    from hq_api.domain import gate

    now = now or datetime.now(UTC)
    today = now.date()
    cfg = settings()
    out = {"opened": 0, "closed": 0, "refreshed": 0}
    holding = await hub.companies.holding()
    to_open: list[dict[str, Any]] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await gate.holding_lock(tx) is not None:
            return out
        since = month_start(today.replace(year=today.year - 1))
        for r in await figures(tx, None, None, since, next_month(today)):
            state, gap, pct, _ = judge(r, today, cfg)
            g = await stored(tx, r["account_id"], r["month"])
            row = {**r, "gap": gap, "pct": pct}
            if state == "open" and g is None:
                to_open.append(row)
            elif state == "open" and g is not None:
                if g["state"] == "closed" or Decimal(g["received_usdt"]) != Decimal(r["received"]):
                    await tx.exec(
                        """UPDATE sales.affiliate_gaps SET state = 'open', closed_at = NULL,
                               due_usdt = :d, received_usdt = :r, gap_usdt = :g, gap_pct = :p,
                               updated_at = now() WHERE id = :id""",
                        d=r["due"], r=r["received"], g=gap, p=pct, id=g["id"],
                    )  # fmt: skip
                    out["refreshed"] += 1
            elif state in ("ok",) and g is not None and g["state"] == "open":
                await _close(tx, g, r, gap, pct)
                out["closed"] += 1
    for row in to_open:
        company = await hub.companies.by_id(row["company_id"])
        text = await draft_for(hub, holding.code, row, company.name_fa or company.code, ask)
        async with hub.db.tx(await hub.companies.ids()) as tx:
            if await stored(tx, row["account_id"], row["month"]) is not None:
                continue
            co = {"id": company.id, "code": company.code, "name_fa": company.name_fa}
            month = row["month"].isoformat()[:7]
            ref = await leads.planner_item(
                tx, co, "FIN",
                title=f"پیگیری کمیسیون افیلیت {row['exchange']} ماه {month}",
                brief=(
                    f"طلب {Decimal(row['due']):.2f} تتر، دریافتی {Decimal(row['received']):.2f} تتر، "
                    f"کسری {Decimal(row['gap']):.2f} تتر ({row['pct']:.1f}٪).\n\nپیش‌نویس پیام (فرستاده نشده):\n{text}"
                ),
                due_at=now + timedelta(days=1),
            )  # fmt: skip
            await tx.exec(
                """INSERT INTO sales.affiliate_gaps (company_id, account_id, month, due_usdt, received_usdt,
                       gap_usdt, gap_pct, work_ref, draft_fa)
                   VALUES (:co, :a, :m, :d, :r, :g, :p, :w, :t) ON CONFLICT (account_id, month) DO NOTHING""",
                co=row["company_id"], a=row["account_id"], m=row["month"], d=row["due"], r=row["received"],
                g=row["gap"], p=row["pct"], w=ref if ref and ref.startswith("W-") else None, t=text,
            )  # fmt: skip
            await audit.record(
                tx, SERVICE, company_id=row["company_id"], action="affiliate.gap", action_class="A1",
                target_kind="affiliate_gap", target_ref=f"{row['account']}:{month}",
                summary=f"gap {row['pct']:.1f}% opened",
            )  # fmt: skip
            out["opened"] += 1
    return out


async def _close(tx: Tx, g: dict[str, Any], r: dict[str, Any], gap: Decimal, pct: float) -> None:
    await tx.exec(
        """UPDATE sales.affiliate_gaps SET state = 'closed', closed_at = now(), received_usdt = :r,
               gap_usdt = :g, gap_pct = :p, updated_at = now() WHERE id = :id""",
        r=r["received"], g=gap, p=pct, id=g["id"],
    )  # fmt: skip


async def receive(
    hub: Any, who: Principal, *, account_id: Any, month: date, received_usdt: Decimal, note_fa: str | None
) -> SalesAffiliateReceipt:
    """Record what arrived for an account's month and close its gap if that settles it."""
    if month != month_start(month):
        raise ApiError(422, "validation_failed", fields={"month": "the first of a month"})
    async with hub.db.tx(await hub.companies.ids()) as tx:
        acc = await tx.first(
            "SELECT a.id, a.company_id, a.exchange, a.service_account, c.code AS company "
            "FROM revenue.accounts a JOIN core.companies c ON c.id = a.company_id WHERE a.id = :i",
            i=account_id,
        )
        if acc is None:
            raise ApiError(404, "not_found", message_fa="این حساب پیدا نشد.")
        row = await tx.one(
            """INSERT INTO sales.affiliate_receipts (company_id, account_id, month, received_usdt, note_fa,
                   by_kind, by_code) VALUES (:co, :a, :m, :r, :n, :bk, :bc) RETURNING at""",
            co=acc["company_id"], a=acc["id"], m=month, r=received_usdt,
            n=(note_fa or None), bk=who.kind, bc=who.code,
        )  # fmt: skip
        await audit.record(
            tx, who, company_id=acc["company_id"], action="affiliate.receipt", action_class="A1",
            target_kind="affiliate_account", target_ref=f"{acc['service_account']}:{month.isoformat()[:7]}",
            summary=f"received {received_usdt}",
        )  # fmt: skip
        g = await stored(tx, acc["id"], month)
        if g is not None and g["state"] == "open":
            cfg = settings()
            for r in await figures(tx, None, acc["id"], month, next_month(month)):
                state, gap, pct, _ = judge(r, datetime.now(UTC).date(), cfg)
                if state == "ok":
                    await _close(tx, g, r, gap, pct)
        return SalesAffiliateReceipt(
            company=acc["company"], account=acc["service_account"], month=month,
            received_usdt=received_usdt, note_fa=note_fa, at=row["at"],
        )  # fmt: skip
