"""Prompt 5.1 §3: the small fixes of the review."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.agents import checks

from .conftest import agent_headers

pytestmark = pytest.mark.usefixtures("relay")


async def test_a_missing_and_a_forbidden_company_answer_the_same(
    client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    """The policy decides before any lookup in another company: 403 both ways,
    never a 404 that tells the code does not exist."""
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    h = await agent_headers(f"{co}-CEO")
    for path in (
        "/internal/v1/company/state?company={c}",
        "/internal/v1/health/sites?company={c}",
        "/internal/v1/treasury/usage?scope={c}",
        "/internal/v1/knowledge/search?q=x&company={c}",
    ):
        got = {}
        for c in (other, "NOPE" + co[:3]):
            r = await client.get(path.format(c=c), headers=h)
            got[c] = (r.status_code, r.json().get("code"))
        assert set(got.values()) == {(403, "policy_denied")}, (path, got)


async def test_memory_writes_honour_the_idempotency_key(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    h = {**await agent_headers(f"{co}-CEO"), "Idempotency-Key": str(uuid.uuid4())}
    body = {"note": "یک یادداشت", "tags": ["t"]}
    first = await client.post("/internal/v1/memory", headers=h, json=body)
    again = await client.post("/internal/v1/memory", headers=h, json=body)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    n = await su.fetchval(
        """SELECT count(*) FROM core.employee_memory m JOIN core.employees e ON e.id = m.employee_id
           WHERE e.code = $1""",
        f"{co}-CEO",
    )
    assert n == 1


async def test_tool_call_caps_say_when_to_retry(
    client: httpx.AsyncClient, su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    h = await agent_headers(f"{co}-CEO")
    await su.execute(
        """UPDATE agents.runs r SET step_tool_calls_cap = 1 FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = $1 AND r.state = 'running'""",
        f"{co}-CEO",
    )
    codes = []
    for _ in range(3):
        r = await client.post(
            "/internal/v1/runs/self/reserve", headers=h, json={"tool": "work.get", "step": 1}
        )
        codes.append(r.status_code)
        if r.status_code == 429:
            assert r.json()["code"] == "rate_limited"
            assert int(r.headers["retry-after"]) > 0
    assert codes[0] == 200 and 429 in codes


async def test_live_replies_off_is_live_unavailable(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Any, su: Any
) -> None:
    live, hub.live = hub.live, None
    try:
        r = await client.get("/api/v1/threads/A/live", headers=owner)
        a = await client.post(
            "/internal/v1/threads/A/live", headers=await agent_headers("HQ-ADV"), content=b"{}\n"
        )
    finally:
        hub.live = live
        # The test token's run must not stay "running": the advisor's next real
        # run would be refused as busy.
        await su.execute(
            """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
               WHERE e.id = r.employee_id AND e.code = 'HQ-ADV' AND r.state = 'running'
                 AND r.reason = 'test'"""
        )
    assert (r.status_code, r.json()["code"]) == (503, "live_unavailable")
    assert (a.status_code, a.json()["code"]) == (503, "live_unavailable")


def test_incident_responders_are_data() -> None:
    """Who an incident goes to is seed data (prompt 5.1 §3), not code."""
    data = checks.responders()
    assert set(data) == {"company", "holding"} and all(data.values())
    assert not hasattr(checks, "RESPONDERS")  # no role names in the code
