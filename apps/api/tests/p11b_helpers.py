"""Shared setup of prompt 11 §4-§10's tests (the governance half): the
worker's scoped transaction, the governance activities, a manual KPI, a CEO
proposal through the internal API, the holding switch (p10_support)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hq_api.domain import gov_authority, gov_calendar, gov_checks, oversight
from hq_api.domain import gov_common as G
from hq_api.domain import gov_kpis as K
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.governance_activities import GovernanceActivities

from .conftest import agent_headers, idem

__all__ = ["acts", "ceo", "governance_seeded", "manual_kpi", "propose", "quarter", "record", "txf"]


@pytest.fixture(autouse=True)
async def governance_seeded(hub: Hub, owner_db: Any) -> None:
    """The seed's governance part (as the owner role hq): another file's 0009
    migration round trip (test_hiring) empties the tables for the rest of the
    session, as it does the protocols (test_people's `seeded`)."""
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        holding = await hub.companies.holding()
        await oversight.seed_protocols(tx, holding.id, hub.charters.root)
        await gov_authority.seed(tx)
        await gov_calendar.seed_holidays(tx)
        await gov_checks.activate(tx)


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


def acts(hub: Hub) -> GovernanceActivities:
    """The worker's governance activities: no router, no gateway at all."""
    return GovernanceActivities(hub, txf(hub))


def quarter() -> str:
    return G.quarter_of(G.today("Asia/Tehran"))


async def ceo(co: dict[str, Any]) -> dict[str, str]:
    return await agent_headers(f"{co['code']}-CEO")


async def manual_kpi(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    co: dict[str, Any],
    key: str | None = None,
    *,
    card: str = "growth",
    target: float | None = None,
    scorecard: bool = False,
    aggregate: str = "sum",
    freshness_hours: int = 168,
) -> str:
    """A manual KPI added by the owner (PUT /kpis/{company})."""
    key = key or f"test.k{uuid.uuid4().hex[:10]}"
    r = await client.get(f"/api/v1/kpis/{co['code']}", headers=owner)
    assert r.status_code == 200, r.text
    body = {
        "kpis": [
            {"key": key, "source": {"kind": "manual"}, "card": card, "name_fa": f"سنجه‌ی {key}",
             "target": target, "scorecard": scorecard, "aggregate": aggregate,
             "freshness_hours": freshness_hours},
        ]
    }  # fmt: skip
    r = await client.put(
        f"/api/v1/kpis/{co['code']}",
        headers={**owner, "If-Match": str(r.json()["version"])},
        json=body,
    )
    assert r.status_code == 200, r.text
    return key


async def record(
    client: httpx.AsyncClient,
    co: dict[str, Any],
    key: str,
    value: float,
    at: datetime | None = None,
) -> httpx.Response:
    return await client.post(
        "/internal/v1/governance/kpis/record",
        headers={**await ceo(co), **idem()},
        json={
            "company": co["code"],
            "key": key,
            "value": value,
            "at": (at or datetime.now(UTC)).isoformat(),
            "source": {"kind": "metric", "ref": "analytics:dashboard", "note": "test"},
        },
    )


async def propose(
    client: httpx.AsyncClient, co: dict[str, Any], title: str = "پیشنهاد", **extra: Any
) -> dict[str, Any]:
    """A low-risk A1 proposal by the company's CEO."""
    body = {"kind": "proposal", "title": title, "payload": {}, "risk": "low",
            "quota_estimate": {"usd": "1"}, **extra}  # fmt: skip
    r = await client.post("/internal/v1/decisions", headers={**await ceo(co), **idem()}, json=body)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def card_of(client: httpx.AsyncClient, owner: dict[str, str], co: str, key: str) -> Any:
    r = await client.get("/api/v1/cards", headers=owner, params={"company": co})
    assert r.status_code == 200, r.text
    for c in r.json():
        for k in c["kpis"]:
            if k["key"] == key:
                return k
    return None


def j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


__all__ += ["K", "card_of", "j"]
