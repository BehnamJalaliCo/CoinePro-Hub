"""Prompt 21 part 3 (contract §29.11-§29.13, agents/tools.md v1.11): the
working groups' tools through the gateway: registered and live, each in
the charters that use it, reaching its api route with the run's token,
text leaving redacted."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_gateway import groups as GT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

LEAD = gate(employee="TY-MEDIA-MGR", kind="manager", role="media_director", department="MEDIA")
ANALYST = gate(employee="TY-MEDIA-05", kind="employee", role="content_analyst", department="MEDIA")
WRITER = gate(employee="TY-MEDIA-01", kind="employee", role="scriptwriter", department="MEDIA")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_the_tools_are_live_and_held_by_the_groups_seats() -> None:
    assert set(GT.TOOLS) == {"group.plan", "experiment.write", "connection.read"}
    assert set(GT.TOOLS) <= set(T.TOOLS) and set(GT.TOOLS) <= tool_status.GATEWAY_TOOLS
    for tool in GT.TOOLS:
        assert tool in LIB.tools, tool
    holders = {t: {r for r, c in LIB.roles.items() if t in c.tools} for t in GT.TOOLS}
    # ⟨2026-11-06⟩ the CEO too (groups.rego grants it the company's plan)
    assert holders["group.plan"] == {"media_director", "ceo"}
    assert holders["experiment.write"] == {"media_director", "content_analyst"}
    assert {"media_director", "content_analyst", "publisher", "scriptwriter", "visual_designer",
            "motion_designer"} <= holders["connection.read"]  # fmt: skip


async def test_each_tool_reaches_its_route_with_the_runs_token(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, LEAD)
    seen: list[dict[str, Any]] = []

    def plan(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(200, json={"group": "content", "company": "TY", "items": 1,
                                         "plan_at": None, "suggestion": None})  # fmt: skip

    mock.post(f"{API}/internal/v1/groups/plan").mock(side_effect=plan)
    body = {
        "items": [{"seat": "scriptwriter", "title_fa": "متن ریلز"}],
        "suggestion": {"title_fa": "تماس با ali@example.com برای همکاری", "impact": 4, "cost": 2},
    }
    out = await call(gw, "group.plan", body)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "group:content:TY"), out
    assert "ali@example.com" not in seen[0]["suggestion"]["title_fa"]  # redacted on its way out
    Stub(mock, ANALYST)
    mock.post(f"{API}/internal/v1/experiments").mock(
        return_value=httpx.Response(200, json={"id": "e1", "week": "2026-10-31"})
    )
    out = await call(gw, "experiment.write", {"hypothesis_fa": "ریلز کوتاه", "metric": "views",
                                              "target": 1000})  # fmt: skip
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "experiment:e1"), out
    params: list[dict[str, str]] = []

    def read(request: httpx.Request) -> httpx.Response:
        params.append(dict(request.url.params))
        return httpx.Response(
            200, json=[{"kind": "telegram", "state": "connected", "secret": "set"}]
        )

    mock.get(f"{API}/internal/v1/connections").mock(side_effect=read)
    out = await call(gw, "connection.read", {"kind": "telegram", "days": 3})
    assert (out["outcome"], out["class"]) == ("ok", "A0"), out
    assert params[0] == {"kind": "telegram", "days": "3"}
    bad = await call(gw, "connection.read", {"kind": "myspace"})
    assert bad["code"] == "invalid_args"


async def test_a_seat_without_the_tool_is_refused_before_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, WRITER)
    route = mock.post(f"{API}/internal/v1/groups/plan")
    out = await call(gw, "group.plan", {"items": []})
    assert out["outcome"] == "denied" and not route.called
