"""Prompt 25 (contract §35.5): the owner's office — the home as his workspace. «اون صفحه خانه دفتر
مدیر کله فضای کار منه باید همه چیز دمه دستم باشه». One read: his open sessions (his turn first),
the cards only he decides (owner-visible), the month's money in dollars, the critical notices, the
suggestions of any subject, and the canvas of companies and their links. No per-group block."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from hq_api.domain import humanize
from hq_api.domain import office as OF
from hq_api.hub import Hub

from .conftest import agent_headers
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture


async def test_the_office_holds_sessions_approvals_money_and_the_canvas(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    out = await post_order(
        client, owner, f"برای {co['code']} گزارش فروش هفته را آماده کن {words()}"
    )
    holder = out["routes"][0]["to"]
    r = await client.post(
        f"/internal/v1/orders/{out['ref']}/ask",
        headers=await agent_headers(holder),
        json={"question_fa": "گزارش را برای کدام هفته بسازم؟"},
    )
    assert r.status_code == 200, r.text
    # a technical card waits for its handler, a business card for the owner
    tech = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
               proposer_code, domain, owner_visible)
           VALUES ($1, 'proposal', 'A1', 'کارت فنی', 'agent', $2, 'infra', false) RETURNING ref""",
        co["id"],
        f"{co['code']}-CEO",
    )
    biz = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
               proposer_code) VALUES ($1, 'proposal', 'A1', 'کارت کسب‌وکار', 'agent', $2) RETURNING ref""",
        co["id"],
        f"{co['code']}-CEO",
    )
    r = await client.get("/api/v1/office", headers=owner)
    assert r.status_code == 200, r.text
    o = r.json()
    assert set(o) == {
        "sessions", "approvals", "approvals_total", "money", "critical", "suggestions", "canvas",
    }  # fmt: skip
    # his turn first; the session carries the question in plain words
    assert o["sessions"][0]["badge"] == "your_turn"
    mine = next(s for s in o["sessions"] if s["ref"] == out["ref"])
    assert mine["badge"] == "your_turn" and mine["conversation_ref"]
    refs = {d["ref"] for d in o["approvals"]}
    assert tech not in refs and (biz in refs or o["approvals_total"] > len(o["approvals"]))
    # money in dollars, one plain line, never tokens
    assert o["money"]["line_fa"] and "توکن" not in o["money"]["line_fa"]
    assert humanize.check(o["money"]["line_fa"]) == []
    # the canvas: the hub and the company
    codes = {n["code"] for n in o["canvas"]["nodes"]}
    assert co["code"] in codes and any(n["kind"] == "holding" for n in o["canvas"]["nodes"])


async def test_the_offices_month_starts_in_the_owners_zone(hub: Hub, su: Any) -> None:
    """Audit: «this month» is cut at the owner's month start, not UTC's (as the treasury does)."""
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1")
    z = ZoneInfo(tz or "Asia/Tehran")
    start = datetime(2020, 3, 1, tzinfo=z)
    for at, cost in ((start - timedelta(minutes=30), "1000"), (start + timedelta(minutes=30), "7")):
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
                   input_tokens, output_tokens, status, cost_usd)
               VALUES (gen_random_uuid(), $1, (SELECT id FROM core.companies WHERE kind = 'holding' LIMIT 1),
                       'HQ-TEST', 'general', 3, 'office_test', 0, 0, 'ok', $2)""",
            at, Decimal(cost),
        )  # fmt: skip
    expected = await su.fetchval(
        "SELECT COALESCE(sum(cost_usd), 0) FROM llm.calls WHERE started_at >= $1", start
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        m = await OF.money(tx, start + timedelta(hours=1))
    assert m.spend_month_usd == Decimal(expected)
