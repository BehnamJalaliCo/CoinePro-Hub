"""Prompt 6 §1.1: /treasury/breakdown?by=day (contract §10, ⟨1.3⟩)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx


async def _call(su: Any, company_id: Any, at: str, tokens: int) -> None:
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
               status, input_tokens, output_tokens, equiv_cost_usd)
           VALUES (gen_random_uuid(), $2, $1, 'test', 'general', 3, 'tests', 'ok', $3, 1, 0.5)""",
        company_id,
        datetime.fromisoformat(at),
        tokens,
    )


async def test_one_row_per_owner_day_with_zeros(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    company = await new_company()
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1")
    assert tz == "Asia/Tehran"  # +03:30
    # 21:00 UTC on the 10th is already the 11th in Tehran; nothing on the 12th.
    await _call(su, company["id"], "2026-09-10T08:00:00Z", 100)
    await _call(su, company["id"], "2026-09-10T21:00:00Z", 10)
    await _call(su, company["id"], "2026-09-13T05:00:00Z", 1)
    r = await client.get(
        "/api/v1/treasury/breakdown",
        headers=owner,
        params={
            "by": "day",
            "company": company["code"],
            "from": "2026-09-09T20:30:00Z",  # 2026-09-10 00:00 in Tehran
            "to": "2026-09-13T20:29:59Z",  # the end of the 13th in Tehran
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["key"] for x in rows] == ["2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"]
    assert [x["input_tokens"] for x in rows] == [100, 10, 0, 1]
    assert [x["calls"] for x in rows] == [1, 1, 0, 1]
    assert rows[2]["equiv_cost_usd"] in ("0", "0.000000", 0)
    bad = await client.get(
        "/api/v1/treasury/breakdown",
        headers=owner,
        params={"by": "day", "from": "2026-09-13T00:00:00Z", "to": "2026-09-10T00:00:00Z"},
    )
    assert bad.status_code == 422
    long = await client.get(
        "/api/v1/treasury/breakdown",
        headers=owner,
        params={"by": "day", "from": "2024-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
    )
    assert long.status_code == 422


async def test_dates_without_a_time_are_the_owners_days(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    """6.1 §1.3: `from=2026-10-01` (what the Android app sends) was a 500 (a
    naive datetime against aware ones). A bare date is the owner's day, `to`
    counts its own day, a time without a zone is the owner's time."""
    company = await new_company()
    await _call(su, company["id"], "2026-09-30T21:00:00Z", 7)  # 2026-10-01 00:30 in Tehran
    await _call(su, company["id"], "2026-10-02T20:00:00Z", 5)  # 2026-10-02 23:30 in Tehran
    await _call(su, company["id"], "2026-10-02T21:00:00Z", 1000)  # already the 3rd in Tehran
    for by in ("company", "day", "model", "task_class"):
        r = await client.get(
            "/api/v1/treasury/breakdown",
            headers=owner,
            params={"by": by, "company": company["code"], "from": "2026-10-01", "to": "2026-10-02"},
        )
        assert r.status_code == 200, (by, r.text)
        assert sum(x["input_tokens"] for x in r.json()) == 12, (by, r.json())
    naive = await client.get(
        "/api/v1/treasury/breakdown",
        headers=owner,
        params={
            "company": company["code"],
            "from": "2026-10-01T00:00:00",
            "to": "2026-10-01T01:00:00",
        },
    )
    assert naive.status_code == 200 and naive.json()[0]["input_tokens"] == 7
    what_if = await client.get(
        "/api/v1/treasury/what-if",
        headers=owner,
        params={
            "model": "claude-haiku-5-5",
            "company": company["code"],
            "from": "2026-10-01",
            "to": "2026-10-02",
        },
    )
    assert what_if.status_code == 200 and what_if.json()["calls"] == 2
    bad = await client.get("/api/v1/treasury/breakdown", headers=owner, params={"from": "1 Mehr"})
    assert bad.status_code == 422
    default = await client.get("/api/v1/treasury/breakdown", headers=owner, params={"by": "day"})
    assert default.status_code == 200
    first = default.json()[0]["key"]
    from datetime import UTC
    from zoneinfo import ZoneInfo

    assert (
        first
        == datetime.now(UTC).astimezone(ZoneInfo("Asia/Tehran")).date().replace(day=1).isoformat()
    )
