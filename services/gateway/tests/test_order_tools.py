"""Prompt 25 (contract §34, agents/tools.md v1.16): the tools of whoever works on an owner's order.
Before it, the api and the policy had order.ack and order.progress but no tool reached them: an
order's holder could never answer the owner. Every role holds them now; each reaches its api route
with the run's token, its text leaving redacted."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_common.charters import EVERY_ROLE_TOOLS, SHARED_TOOLS
from hq_gateway import orders as OT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CEO = gate(employee="PC-CEO", company="PC", kind="ceo", role="ceo", department=None)


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_every_role_holds_the_order_tools() -> None:
    assert set(EVERY_ROLE_TOOLS) == {"order.ack", "order.progress", "order.ask"}
    assert set(OT.TOOLS) == set(EVERY_ROLE_TOOLS) | {"automation.propose"}
    assert set(OT.TOOLS) <= set(T.TOOLS) and set(OT.TOOLS) <= tool_status.GATEWAY_TOOLS
    for tool in OT.TOOLS:
        assert LIB.tools[tool].cls == "A1", tool
    assert LIB.roles, "the charters load"
    for role, charter in LIB.roles.items():
        held = set(SHARED_TOOLS) & set(charter.tools)
        assert held == (set() if charter.kind == "system" else set(SHARED_TOOLS)), role
    # ⟨2026-11-06⟩ every working role asks the outside players (the policy names its seats)
    assert "substitute.call" in SHARED_TOOLS


async def test_each_tool_reaches_its_route_with_the_runs_token(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    seen: dict[str, dict[str, Any]] = {}

    def route(name: str) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            seen[name] = json.loads(request.content)
            assert request.headers.get("authorization")
            return httpx.Response(200, json={"ref": "F-0153", "state": "waiting"})

        return answer

    for name in ("ack", "progress", "ask"):
        mock.post(f"{API}/internal/v1/orders/F-0153/{name}").mock(side_effect=route(name))
    out = await call(
        gw, "order.ack", {"ref": "F-0153", "plan_fa": "سه مرحله", "assigned": ["PC-MEDIA-MGR"]}
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "F-0153"), out
    assert seen["ack"]["assigned"] == ["PC-MEDIA-MGR"] and seen["ack"]["due_at"] is None
    assert seen["ack"]["steps"] == []
    # ⟨1.17⟩ the plan's steps become the session's tasks; a step ticks them by number
    out = await call(
        gw, "order.ack",
        {"ref": "F-0153", "plan_fa": "سه مرحله", "steps": ["کارگروه", "سه ریلز", " "]},
    )  # fmt: skip
    assert out["outcome"] == "ok" and seen["ack"]["steps"] == ["کارگروه", "سه ریلز"]
    out = await call(gw, "order.progress", {"ref": "F-0153", "step_fa": "کارگروه ساخته شد"})
    assert out["outcome"] == "ok" and seen["progress"] == {
        "step_fa": "کارگروه ساخته شد",
        "done": [],
    }
    out = await call(
        gw, "order.progress", {"ref": "F-0153", "step_fa": "ریلزها آماده شد", "done": [2, 2, 1]}
    )
    assert out["outcome"] == "ok" and seen["progress"]["done"] == [2, 1]
    bad = await call(gw, "order.progress", {"ref": "F-0153", "step_fa": "x", "done": ["1"]})
    assert bad["code"] == "invalid_args"
    out = await call(
        gw, "order.ask", {"ref": "F-0153", "question_fa": "به ali@example.com پیام بدهم؟"}
    )
    assert out["outcome"] == "ok" and out["result"] == {"order": "F-0153", "state": "waiting"}
    assert "ali@example.com" not in seen["ask"]["question_fa"]  # redacted on its way out
    bad = await call(gw, "order.ask", {"ref": "W-000153", "question_fa": "ادامه بدهم؟"})
    assert bad["code"] == "invalid_args"


async def test_an_order_the_agent_does_not_work_on_is_refused_by_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    mock.post(f"{API}/internal/v1/orders/F-0001/ask").mock(
        return_value=httpx.Response(
            403, json={"code": "policy_denied", "message": "not an order you work on"}
        )
    )
    out = await call(gw, "order.ask", {"ref": "F-0001", "question_fa": "ادامه بدهم؟"})
    assert out["outcome"] == "denied" and out["code"] == "policy_denied"
