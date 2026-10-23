"""Prompt 12 §12 (agents/tools.md v1.5): `claim.verdict`, the fact check of
one claim (A2: the fact checker, the overseer, QC; a refuted claim needs
evidence; the claim is redacted on the way)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CHECKER = gate(
    employee="HQ-OVS-01", company="HQ", kind="employee", role="fact_checker", department="OVS",
    scope="holding",
)  # fmt: skip
STAFF = gate(employee="TY-GROWTH-01", kind="employee", role="sre", department="GROWTH")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


async def test_a_checked_claim_goes_to_the_api_redacted(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CHECKER)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={"ref": "CL-0001", "deliverable": "O-000012", "employee": "TY-CEO", "verdict": "refuted",
                  "at": "2031-01-01T00:00:00Z", "evidence": [], "claim_md": "x"},
        )  # fmt: skip

    mock.post(f"{API}/internal/v1/claims").mock(side_effect=handle)
    out = await call(
        gw,
        "claim.verdict",
        {
            "deliverable": "O-000012",
            "claim_md": "رشد ۲۰٪ (ali@example.com)",
            "verdict": "refuted",
            "evidence": [{"kind": "metric", "ref": "users.active", "note": "۱۲٪"}],
        },
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "CL-0001"), out
    assert set(out["result"]) == {"ref", "deliverable", "employee", "verdict", "at"}
    assert "ali@example.com" not in seen[0]["claim_md"]


async def test_a_refuted_claim_without_evidence_never_reaches_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CHECKER)
    route = mock.post(f"{API}/internal/v1/claims")
    out = await call(
        gw, "claim.verdict", {"deliverable": "O-1", "claim_md": "x", "verdict": "refuted"}
    )
    assert (out["outcome"], out["code"]) == ("error", "validation_failed") and not route.called
    bad = await call(
        gw, "claim.verdict", {"deliverable": "D-1", "claim_md": "x", "verdict": "confirmed"}
    )
    assert bad["code"] == "invalid_args"


async def test_an_ordinary_employee_has_no_claim_tool(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, STAFF)
    out = await call(
        gw, "claim.verdict", {"deliverable": "O-1", "claim_md": "x", "verdict": "confirmed"}
    )
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter")
