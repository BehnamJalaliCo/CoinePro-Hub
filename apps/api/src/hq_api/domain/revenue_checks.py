"""PR-103 by code (prompt 10 §11.2, agents/protocols/oversight.yaml): the
revenue radar's figures reconcile with the affiliate data they came from.

Every pull keeps, per page of every endpoint, the page's figures as egress
reduced them and their SHA-256 (revenue.days.source.pages; the raw page holds
balances and never leaves egress). For each day of the last three settled
days the check recomputes from those pages: the commission per coin, its
USDT value at the recorded close (USDT at par), the day's total, the new
invitees and those over the minimum; and `complete` must mean "no gap and
every page present". A difference is a finding (one open finding per account
and day). Rule-only: no model, no outside call. The protocol stays `paused`
in its file until the owner's affiliate keys make the radar live.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from hq_api.domain import affiliate as A
from hq_api.domain.oversight_checks import CheckCtx, Checked, Problem, check

HEX64 = re.compile(r"^[0-9a-f]{64}$")
DAYS = 3
CENT = Decimal("0.00000001")


def _d(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def reconcile(row: dict[str, Any]) -> list[str]:
    """What does not add up in one RevenueDay (empty: it reconciles)."""
    src = row.get("source") or {}
    pages = [p for p in src.get("pages") or [] if isinstance(p, dict)]
    wrong: list[str] = []
    if any(not HEX64.match(str(p.get("sha256") or "")) for p in pages):
        wrong.append("a page without its hash")
    gaps = row.get("gaps") or []
    if row["complete"] and gaps:
        wrong.append("complete with gaps")
    if row["complete"] and not any(
        p.get("endpoint") == "commission/stats/symbol/list" for p in pages
    ):
        wrong.append("complete without its commission pages")
    coins: dict[str, Decimal] = {}
    prices: dict[str, Decimal] = {"usdt": Decimal(1)}
    invitees = minimum = 0
    for p in pages:
        sums = p.get("sums") or {}
        if p.get("endpoint") == "commission/stats/symbol/list":
            for coin, amount in sums.items():
                v = _d(amount)
                if v is not None:
                    coins[coin] = coins.get(coin, Decimal(0)) + v
        elif p.get("endpoint") == "invite/user/team/list":
            invitees += int(sums.get("invitees") or 0)
            minimum += int(sums.get("min_balance") or 0)
        elif p.get("endpoint") == "kline":
            for coin, close in sums.items():
                v = _d(close)
                if v is not None:
                    prices[coin] = v
    total = Decimal(0)
    seen: set[str] = set()
    for c in row.get("by_coin") or []:
        coin = str(c.get("coin"))
        seen.add(coin)
        amount, usdt = _d(c.get("amount")), _d(c.get("usdt"))
        if amount is None or amount != coins.get(coin):
            wrong.append(f"{coin}: amount {c.get('amount')} vs pages {coins.get(coin)}")
        if usdt is not None:
            total += usdt
            price = prices.get(coin)
            if (
                price is None
                or amount is None
                or (amount * price).quantize(CENT) != usdt.quantize(CENT)
            ):
                wrong.append(f"{coin}: usdt {usdt} vs amount x close {price}")
        elif row["complete"]:
            wrong.append(f"{coin}: complete without a price")
    for coin in sorted(set(coins) - seen):
        wrong.append(f"{coin}: in the pages, not in the day")
    commission = _d(row["commission_usdt"]) or Decimal(0)
    if commission.quantize(CENT) != total.quantize(CENT):
        wrong.append(f"commission_usdt {commission} vs coins {total}")
    if row["new_invitees"] != invitees:
        wrong.append(f"new_invitees {row['new_invitees']} vs pages {invitees}")
    if row.get("min_balance_invitees") is not None and row["min_balance_invitees"] != minimum:
        wrong.append(f"min_balance_invitees {row['min_balance_invitees']} vs pages {minimum}")
    return wrong


@check("PR-103")
async def revenue_reconciles(ctx: CheckCtx) -> Checked:
    since = A.last_settled_day(ctx.now) - timedelta(days=DAYS - 1)
    rows = await ctx.tx.all(
        """SELECT d.*, c.code AS company FROM revenue.days d JOIN core.companies c ON c.id = d.company_id
           WHERE d.day >= :s ORDER BY d.day""",
        s=since,
    )
    problems = []
    looked: dict[str, Any] = {}
    for r in rows:
        looked[r["company"]] = r["company_id"]
        wrong = reconcile(r)
        if not wrong:
            continue
        hashes = ", ".join(
            str(p.get("sha256"))[:12]
            for p in (r["source"] or {}).get("pages") or []
            if isinstance(p, dict)
        )
        problems.append(
            Problem(
                r["company_id"],
                r["company"],
                f"ارقام رادار درآمد {r['day']} با داده‌ی خام افیلیت نمیخواند",
                "; ".join(wrong[:10]) + (f"\n\npages: {hashes[:600]}" if hashes else ""),
                f"revenue:{r['account_id']}:{r['day']}",
                [
                    {
                        "kind": "log",
                        "ref": f"revenue:{r['account_id']}:{r['day']}",
                        "note": hashes[:300],
                    }
                ],
            )
        )
    return Checked(problems, looked, notes=f"{len(rows)} revenue days reconciled")
