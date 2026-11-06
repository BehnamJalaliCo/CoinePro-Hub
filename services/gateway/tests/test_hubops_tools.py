"""⟨1.20⟩ hub.ops through the gateway (contract §38.1, agents/tools.md): live, held by the holding's
technical charters only; its class is decided per call (A0 reads and {job}, A2 operations, A1 for an
A3 one that only proposes the owner's card); `awaiting_seal` comes back as a refusal with the card;
a denied operation comes back with the owner's step in Persian."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_gateway import hubops as HT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

SRE = gate(employee="HQ-AIOPS-02", company="HQ", kind="employee", role="hub_platform_sre",
           department="AIOPS", scope="holding")  # fmt: skip
MEDIA = gate(employee="PC-MEDIA-01", company="PC", kind="manager", role="media_director",
             department="MEDIA")  # fmt: skip


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_hub_ops_is_live_and_only_the_technical_charters_hold_it() -> None:
    assert "hub.ops" in HT.TOOLS and "hub.ops" in tool_status.GATEWAY_TOOLS
    row = LIB.tools["hub.ops"]
    assert set(row.classes) == {"A0", "A1", "A2"}
    holders = {r for r, c in LIB.roles.items() if "hub.ops" in c.tools}
    assert holders == {"aiops_head", "hub_platform_sre", "cto"}


def _job(state: str, **extra: Any) -> dict[str, Any]:
    return {"job": {"ref": "HJ-000007", "op": "status", "state": state, **extra}}


async def test_a_read_is_a0_and_its_job_is_read_again(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock, SRE)
    seen: list[httpx.Request] = []

    def start(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={**_job("queued"), "hint_fa": "دوباره بپرس"})

    mock.post(f"{API}/internal/v1/hubops").mock(side_effect=start)
    out = await call(gw, "hub.ops", {"op": "logs", "args": {"service": "api", "lines": 50}})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "HJ-000007"), out
    assert json.loads(seen[0].content) == {"op": "logs", "args": {"service": "api", "lines": 50}}
    assert s.opa_inputs[-1]["action"]["class"] == "A0"
    mock.get(f"{API}/internal/v1/hubops/HJ-000007").mock(
        return_value=httpx.Response(200, json=_job("done", output="api  running  healthy"))
    )
    out = await call(gw, "hub.ops", {"job": "HJ-000007"})
    assert out["outcome"] == "ok" and out["result"]["state"] == "done", out


async def test_classes_per_op(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock, SRE)
    mock.post(f"{API}/internal/v1/hubops").mock(
        return_value=httpx.Response(201, json=_job("queued"))
    )
    for args, cls in (
        ({"op": "status"}, "A0"),
        ({"op": "restart", "args": {"service": "worker"}}, "A2"),
        ({"op": "profile", "args": {"name": "media", "on": True}}, "A2"),
        ({"op": "profile", "args": {"name": "media", "on": True, "turn_off": ["ocr"]}}, "A1"),
        ({"op": "n8n.create", "args": {"name": "x", "workflow_json": {"nodes": [{}]}}}, "A1"),
    ):
        out = await call(gw, "hub.ops", args)
        assert out["class"] == cls, (args, out)
        assert s.opa_inputs[-1]["action"]["class"] == cls


async def test_awaiting_seal_is_a_refusal_with_the_card(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, SRE)
    mock.post(f"{API}/internal/v1/hubops").mock(
        return_value=httpx.Response(
            201, json={**_job("awaiting_seal", decision_ref="D-000123"), "hint_fa": "مُهر"}
        )
    )
    out = await call(
        gw, "hub.ops", {"op": "n8n.create", "args": {"name": "x", "workflow_json": {"nodes": [{}]}}}
    )
    assert (out["outcome"], out["code"], out["ref"]) == ("denied", "awaiting_seal", "D-000123")


async def test_denied_op_comes_back_with_the_owners_step(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, SRE)
    mock.post(f"{API}/internal/v1/hubops").mock(
        return_value=httpx.Response(
            403, json={"code": "policy_denied", "message_fa": "فایروال فقط از کنسول هتزنر."}
        )
    )
    out = await call(gw, "hub.ops", {"op": "ufw"})
    assert (out["outcome"], out["code"]) == ("denied", "policy_denied"), out
    assert "هتزنر" in out["hint_fa"]


async def test_bad_input_and_other_roles_never_reach_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, SRE)
    post = mock.post(f"{API}/internal/v1/hubops")
    for bad in ({}, {"op": "status", "job": "HJ-000001"}, {"job": "J-1"}, {"op": ""}):
        out = await call(gw, "hub.ops", bad)
        assert out["code"] == "invalid_args", (bad, out)
    assert not post.called
    Stub(mock, MEDIA)
    out = await call(gw, "hub.ops", {"op": "status"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter") and not post.called
