"""The owner's office: the home as his workspace (contract §35.5, the owner, 2026-11-06: «اون صفحه
خانه دفتر مدیر کله فضای کار منه باید همه چیز دمه دستم باشه»).

    sessions      his open orders as sessions (§35.2), his turn first
    approvals     the cards only he decides, owner-visible (§29.1), oldest first
    money         this month's revenue read from the companies' ledgers and the hub's pay-per-use
                  spend, in dollars, one plain line (no tokens)
    critical      only the owner-visible critical notices (§29.1)
    suggestions   the home's suggestions (§29.13), any subject; «اجرا کن» opens a session
    canvas        the companies, the hub and the links the owner draws (§35.6)

Nothing on it is fixed to one subject: no per-group block. Code only, no model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import gov_common as GC
from hq_api.domain import home as H
from hq_api.domain import links as L
from hq_api.domain import sessions as S
from hq_api.domain.session_shapes import SessionCard
from hq_api.routes.notifications import Notification

SESSIONS = 30
APPROVALS = 10
SUGGESTIONS = 6


class OfficeMoney(BaseModel):
    revenue_month_usd: Decimal | None
    spend_month_usd: Decimal
    budget_month_usd: Decimal | None
    line_fa: str


class Office(BaseModel):
    sessions: list[SessionCard]
    approvals: list[D.Decision]
    approvals_total: int
    money: OfficeMoney
    critical: list[Notification]
    suggestions: list[H.Suggestion]
    canvas: L.Canvas


def _usd(v: Decimal) -> str:
    return f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"


async def money(tx: Tx, now: datetime) -> OfficeMoney:
    """The month in dollars: revenue only when a company's ledger has been read (else null), the
    hub's pay-per-use spend (subscriptions are fixed and not counted here)."""
    # The owner's month (owner.settings.timezone), as the treasury's default range cuts it.
    local = now.astimezone(GC.zone(await GC.owner_tz(tx)))
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    sources = await tx.scalar("SELECT count(*) FROM money.payments WHERE origin = 'ledger'")
    revenue: Decimal | None = None
    if sources:
        revenue = Decimal(
            await tx.scalar(
                """SELECT COALESCE(sum(amount_usdt), 0) FROM money.payments
                   WHERE origin = 'ledger' AND status <> 'ledger_only' AND paid_at >= :s""",
                s=start,
            )
            or 0
        )
    spend = Decimal(
        await tx.scalar(
            "SELECT COALESCE(sum(cost_usd), 0) FROM llm.calls WHERE started_at >= :s", s=start
        )
        or 0
    )
    if revenue is None:
        line = f"هزینه‌ی این ماه {_usd(spend)}؛ درآمد هنوز خوانده نشده است."
    else:
        line = f"درآمد این ماه {_usd(revenue)} · هزینه {_usd(spend)}"
    return OfficeMoney(
        revenue_month_usd=revenue, spend_month_usd=spend, budget_month_usd=None, line_fa=line
    )


async def approvals(tx: Tx) -> tuple[list[D.Decision], int]:
    """The cards only the owner decides and he sees (§29.1), oldest first."""
    rows = await tx.all(
        D.DECISION_SQL
        + """ WHERE d.status = 'pending' AND d.approver_code IS NULL AND d.owner_visible
              ORDER BY d.created_at, d.ref LIMIT :n""",
        n=APPROVALS,
    )
    total = await tx.scalar(
        """SELECT count(*) FROM cartable.decisions
           WHERE status = 'pending' AND approver_code IS NULL AND owner_visible"""
    )
    return [D.render(dict(r)) for r in rows], int(total or 0)


async def suggestions(tx: Tx, now: datetime) -> list[H.Suggestion]:
    """The newest open suggestions of any subject, the home's two chosen ones first."""
    effective, good = await H.choose(tx, now)
    rows = await tx.all(
        H.SUGGESTION_SQL
        + """ WHERE c.status = 'active'
              AND (s.state = 'new' OR (s.state = 'later' AND s.later_until <= :now))
            ORDER BY s.created_at DESC LIMIT 50""",
        now=now,
    )
    first = [x for x in (effective, good) if x is not None]
    seen = {x["id"] for x in first}
    rest = [
        r
        for r in rows
        if r["id"] not in seen and H.shown(r["title_fa"], r["why_fa"], r["impact_fa"], r["cost_fa"])
    ]
    out = [
        H.render_suggestion(x, slot) for x, slot in zip(first, ("effective", "good"), strict=False)
    ]
    out += [H.render_suggestion(r) for r in rest]
    return out[:SUGGESTIONS]


async def build(tx: Tx, now: datetime | None = None) -> Office:
    now = now or datetime.now(UTC)
    page = await S.cards(tx, state="open", limit=SESSIONS)
    items, total = await approvals(tx)
    return Office(
        sessions=page.items,
        approvals=items,
        approvals_total=total,
        money=await money(tx, now),
        critical=await H.critical(tx),
        suggestions=await suggestions(tx, now),
        canvas=await L.canvas(tx),
    )


def as_dict(o: Office) -> dict[str, Any]:
    return o.model_dump(mode="json")
