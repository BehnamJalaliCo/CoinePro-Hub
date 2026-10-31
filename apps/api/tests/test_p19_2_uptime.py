"""Prompt 19.2: a site's `uptime_24h` is a fraction 0..1 everywhere it is
served (the owner's sites list and the agents' health.sites tool); the
apps showed 10000.0% when the hub sent a percent they multiplied again."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from .conftest import agent_headers

pytestmark = pytest.mark.usefixtures("relay")


async def _site(su: Any, co: dict[str, Any], oks: list[bool]) -> str:
    await su.execute("SELECT ops.ensure_check_partitions(1)")
    url = f"https://up-{co['code'].lower()}.example.com/"
    site = await su.fetchval(
        "INSERT INTO ops.sites (company_id, url) VALUES ($1, $2) RETURNING id", co["id"], url
    )
    now = datetime.now(UTC)
    for i, ok in enumerate(oks):
        await su.execute(
            """INSERT INTO ops.checks (site_id, company_id, at, ok, status, latency_ms)
               VALUES ($1, $2, $3, $4, 200, 90)""",
            site,
            co["id"],
            now - timedelta(minutes=5 * (i + 1)),
            ok,
        )
    return url


async def test_uptime_is_a_fraction_on_both_routes(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    up = await _site(su, co, [True] * 7 + [False])  # 7 of 8: 0.875
    r = await client.get(f"/api/v1/ops/sites?company={co['code']}", headers=owner)
    assert r.status_code == 200, r.text
    site = next(s for s in r.json() if s["url"] == up)
    assert site["uptime_24h"] == 0.875

    h = await agent_headers(f"{co['code']}-CEO")
    r = await client.get(f"/internal/v1/health/sites?company={co['code']}", headers=h)
    assert r.status_code == 200, r.text
    site = next(s for s in r.json()["sites"] if s["url"] == up)
    assert site["uptime_24h"] == 0.875

    whole = await new_company()
    url = await _site(su, whole, [True] * 3)
    r = await client.get(f"/api/v1/ops/sites?company={whole['code']}", headers=owner)
    got = next(s for s in r.json() if s["url"] == url)["uptime_24h"]
    assert got == 1.0  # never 100.0


async def test_the_unit_is_written_in_the_api_document(app: Any) -> None:
    schemas = app.openapi()["components"]["schemas"]
    for model in ("Site", "SiteHealth"):
        text = str(schemas[model]["properties"]["uptime_24h"])
        assert "FRACTION 0..1" in text and "'maximum': 1" in text, model
