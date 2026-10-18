"""The gateway's server.plan (prompt 09 §3): the fixed software keys, the
path, the plan's fields back to the model."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import provisioning as P
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


CTO = gate(employee="TY-TECH-MGR", kind="manager", role="cto", department="TECH")
PLAN = {
    "company": "TY",
    "name": "ty-app-1",
    "type": "cpx42",
    "location": "fsn1",
    "private_network": True,
    "firewall": [
        {"protocol": "tcp", "port": "22", "sources": ["198.51.100.7/32"], "note_fa": "SSH"}
    ],
    "software": list(P.SOFTWARE),
    "work_user": "ty",
    "repo": "behnamjalalico/ty-app",
}


async def test_a_cto_plans_a_server_with_known_software_only(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CTO)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(
            {"body": json.loads(request.content), "idem": request.headers.get("idempotency-key")}
        )
        return httpx.Response(
            201,
            json={"ref": "PV-0007", "company": "TY", "monthly_eur": "26.99", "digest": "a" * 64,
                  "state": "proposed", "decision_ref": "D-000101", "problems": [], "firewall": []},
        )  # fmt: skip

    mock.post(f"{API}/internal/v1/provisioning/plans").mock(side_effect=handle)
    out = await call(gw, "server.plan", PLAN)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "PV-0007"), out
    assert out["result"]["monthly_eur"] == "26.99" and "firewall" not in out["result"]
    assert seen[0]["body"]["software"] == list(P.SOFTWARE) and seen[0]["idem"]
    # An unknown key never reaches the api.
    bad = await call(gw, "server.plan", {**PLAN, "software": ["docker", "kubernetes-cluster"]})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")
    assert len(seen) == 1
