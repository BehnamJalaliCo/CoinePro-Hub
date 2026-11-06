"""Prompt 26 (contract §37.3, agents/tools.md v1.19): «پاکش کن» in words. Every working role
proposes an erase with `erase.propose`; the api makes the card, the owner's seal alone erases."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_common.charters import SHARED_TOOLS
from hq_gateway import erase as ET
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


def test_every_working_role_holds_erase_propose() -> None:
    assert set(ET.TOOLS) == {"erase.propose"}
    assert set(ET.TOOLS) <= set(T.TOOLS) and set(ET.TOOLS) <= tool_status.GATEWAY_TOOLS
    assert "erase.propose" in SHARED_TOOLS
    assert LIB.tools["erase.propose"].cls == "A1"
    for role, charter in LIB.roles.items():
        held = "erase.propose" in charter.tools
        assert held == (charter.kind != "system"), role


async def test_it_reaches_the_api_with_the_runs_token_and_an_idempotency_key(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "ref": "D-000901",
                "status": "pending",
                "kind": "erase",
                "payload": {"kind": "output", "ref": "O-000777", "counts": {"files": 2}},
            },
        )

    mock.post(f"{API}/internal/v1/erase/propose").mock(side_effect=answer)
    out = await call(
        gw,
        "erase.propose",
        {"kind": "output", "ref": "O-000777", "why_fa": "مدیر کل گفت پاکش کن؛ ali@example.com"},
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "D-000901"), out
    assert out["result"] == {
        "decision": "D-000901",
        "status": "pending",
        "erases": {"kind": "output", "ref": "O-000777"},
        "counts": {"files": 2},
    }
    [req] = seen
    body: dict[str, Any] = json.loads(req.content)
    assert body["kind"] == "output" and body["ref"] == "O-000777"
    assert "ali@example.com" not in body["why_fa"]  # redacted on its way out
    assert req.headers.get("authorization") and req.headers.get("idempotency-key")


async def test_a_bad_kind_or_ref_never_reaches_the_api(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    route = mock.post(f"{API}/internal/v1/erase/propose").mock(
        return_value=httpx.Response(201, json={})
    )
    for args in (
        {"kind": "company", "ref": "F-0001", "why_fa": "پاکش کن"},
        {"kind": "session", "ref": "W-000001", "why_fa": "پاکش کن"},
        {"kind": "session", "ref": "F-0001", "why_fa": ""},
    ):
        out = await call(gw, "erase.propose", args)
        assert out["code"] == "invalid_args", (args, out)
    assert not route.called


async def test_what_the_agent_cannot_read_is_refused_by_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    mock.post(f"{API}/internal/v1/erase/propose").mock(
        return_value=httpx.Response(
            403, json={"code": "policy_denied", "message": "not something you can read"}
        )
    )
    out = await call(gw, "erase.propose", {"kind": "session", "ref": "F-0001", "why_fa": "پاکش کن"})
    assert out["outcome"] == "denied" and out["code"] == "policy_denied"
