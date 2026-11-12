"""Audit 2026-11-11 (fix group 18, routes): an audit citation that is no bigint, a blank note
made an order, the orders' second page, a zone-less time on a freeze, a challenge or Khalvat,
and revenue.read over more day rows than days_list's default cap."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from hq_api.domain import meeting_flow as MF
from hq_api.routes import messages as M

from .conftest import agent_headers, idem
from .p10_fakes import affiliate_account, settled


class CitedTx:
    """A Tx that finds every ref and keeps the audit ones it was asked to cast."""

    def __init__(self) -> None:
        self.cast: list[str] = []

    async def scalar(self, sql: str, **params: Any) -> Any:
        if "CAST(:r AS bigint)" in sql:
            self.cast.append(params["r"])
        return 1


async def test_an_audit_ref_that_is_no_bigint_is_dropped_not_cast() -> None:
    bad = ["۱۲۳", "²", "9" * 19]
    tx = CitedTx()
    cites = [M.Citation(kind="audit", ref=r) for r in [*bad, "42"]]
    kept, dropped = await M.validate_citations(tx, cites)  # type: ignore[arg-type]
    assert [c.ref for c in kept] == ["42"] and dropped == 3 and tx.cast == ["42"]
    tx = CitedTx()
    claims = [{"text": "x", "source": {"kind": "audit", "ref": r}} for r in [*bad, "42"]]
    out = await MF.check_claims(tx, claims)  # type: ignore[arg-type]
    assert [c["status"] for c in out] == ["unsourced"] * 3 + ["sourced"] and tx.cast == ["42"]


async def test_a_blank_note_made_an_order_is_a_422(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    r = await client.post("/api/v1/notes", headers={**owner, **idem()}, json={"text_md": "  \n "})
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/api/v1/notes/{r.json()['ref']}/promote", headers=owner, json={"to": "order"}
    )
    assert r.status_code == 422 and r.json()["code"] == "validation_failed", r.text


async def test_the_orders_second_page(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    for text in ("یک", "دو"):
        await su.execute(
            "INSERT INTO owner.orders (company_id, text, source) VALUES ($1, $2, 'text')",
            co["id"],
            text,
        )
    h = owner
    first = await client.get("/api/v1/orders", headers=h, params={"limit": 1})
    assert first.status_code == 200 and first.json()["next_cursor"], first.text
    second = await client.get(
        "/api/v1/orders", headers=h, params={"limit": 1, "cursor": first.json()["next_cursor"]}
    )
    assert second.status_code == 200, second.text
    a, b = first.json()["items"][0], second.json()["items"][0]
    at = datetime.fromisoformat
    assert a["ref"] != b["ref"] and at(b["created_at"]) <= at(a["created_at"])
    bad = await client.get("/api/v1/orders", headers=h, params={"cursor": "WyJ4IiwieSJd"})
    assert bad.status_code == 422


async def test_a_time_without_its_zone_is_a_422_not_a_500(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    naive = (datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None).isoformat()
    ovr = await agent_headers("HQ-OVR")
    r = await client.post(
        "/internal/v1/oversight/deploy-freeze",
        headers=ovr,
        json={"company": co, "until": naive, "reason": "بدون منطقه‌ی زمانی"},
    )
    assert r.status_code == 422, r.text
    r = await client.post(
        "/internal/v1/oversight/challenges",
        headers={**ovr, **idem()},
        json={"company": co, "title_fa": "چالش", "due_at": naive},
    )
    assert r.status_code == 422, r.text
    r = await client.put(
        "/api/v1/owner/presence",
        headers={**owner, **idem()},
        json={"khalvat": True, "until": naive},
    )
    assert r.status_code == 422, r.text


async def test_revenue_read_sums_the_whole_range_past_400_rows(
    client: httpx.AsyncClient, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    one = await affiliate_account(su, co)
    two = await affiliate_account(su, co, exchange="other", min_balance=None)
    end = settled(0)
    n = 250  # two accounts: 500 day rows, more than days_list's default 400
    for acct in (one, two):
        await su.execute(
            """INSERT INTO revenue.days (company_id, account_id, day, commission_usdt, new_invitees,
                   complete)
               SELECT $1, $2, d::date, 1, 1, true
               FROM generate_series($3::date - ($4 - 1), $3::date, interval '1 day') d""",
            co["id"], acct["id"], end, n,
        )  # fmt: skip
    body = {"from": (end - timedelta(days=n - 1)).isoformat(), "to": end.isoformat()}
    r = await client.post(
        "/internal/v1/revenue/read",
        headers=await agent_headers(f"{co['code']}-CEO"),
        json={**body, "by": "account"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert Decimal(out["total_usdt"]) == 2 * n and out["new_invitees"] == 2 * n
    assert sorted(Decimal(a["usdt"]) for a in out["accounts"]) == [n, n]
