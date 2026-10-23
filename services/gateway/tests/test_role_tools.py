"""Prompt 13 §1.1 (contract §22.5, agents/tools.md v1.6): role.draft and
role.decide; a role written on demand runs with exactly the tools the api
sends for its draft; the overseer reviews a draft with skill.review (RD-)."""

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

MANAGER = gate(employee="TY-GROWTH-MGR", kind="manager", role="manager", department="GROWTH")
CEO = gate(employee="TY-CEO", kind="ceo", role="ceo", department=None)
DRAFTED = gate(
    employee="TY-GROWTH-07", kind="employee", role="podcast_editor", department="GROWTH",
    tools=["work.get", "deliver", "propose"],
)  # fmt: skip
OVERSEER = gate(
    employee="HQ-OVR", company="HQ", kind="overseer", role="overseer", department="OVS",
    scope="holding",
)  # fmt: skip


def draft(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "company": "TY",
        "department": "GROWTH",
        "role": "podcast_editor",
        "title_fa": "تدوینگر پادکست",
        "title_en": "Podcast Editor",
        "why_md": "هیچ منشوری تدوین صدا ندارد (ali@example.com).",
        "compared": ["content_writer"],
        "charter_md": "# Your role\nYou edit the podcast.",
        "tools": ["work.get", "deliver"],
        "model": "claude-haiku-5-5",
        "effort": "medium",
        "limits": {"steps_per_run": 4, "tokens_per_step": 20000, "tokens_per_run": 60000},
        "eval_cases": [
            {"id": f"c{i}", "input_md": "x", "rubric_md": "y", "weight": 1} for i in range(3)
        ],
    }
    body.update(over)
    return body


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


async def test_role_draft_goes_to_the_api_redacted(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, MANAGER)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(201, json={"ref": "RD-0001", "state": "in_review", "role": "x"})

    mock.post(f"{API}/internal/v1/roles/drafts").mock(side_effect=handle)
    out = await call(gw, "role.draft", draft())
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "RD-0001"), out
    assert "ali@example.com" not in seen[0]["why_md"] and "ref" not in seen[0]
    bad = await call(gw, "role.draft", draft(role="Bad Name"))
    assert bad["code"] == "invalid_args"


async def test_role_decide_is_a_ceos_a2(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    route = mock.post(f"{API}/internal/v1/roles/drafts/RD-0007/decide").mock(
        return_value=httpx.Response(200, json={"ref": "RD-0007", "state": "active"})
    )
    out = await call(gw, "role.decide", {"ref": "RD-0007", "verdict": "approve", "note": "ok"})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "RD-0007"), out
    assert json.loads(route.calls[0].request.content) == {"verdict": "approve", "note": "ok"}
    # A manager's charter has no role.decide.
    Stub(mock, MANAGER)
    out = await call(gw, "role.decide", {"ref": "RD-0007", "verdict": "approve"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter")


async def test_a_drafted_role_runs_with_the_tools_of_its_draft_only(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, DRAFTED)
    mock.get(f"{API}/internal/v1/work/ref/W-000101").mock(
        return_value=httpx.Response(200, json={"id": "1", "ref": "W-000101"})
    )
    out = await call(gw, "web.search", {"query": "x"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), out
    out = await call(gw, "hire.decide", {"ref": "D-000001", "verdict": "approve"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), out
    out = await call(gw, "work.get", {"ref": "W-000101"})
    assert out["outcome"] == "ok", out
    # A file charter's run ignores a tools list (never more than its charter).
    Stub(mock, gate(tools=["hire.decide"]))
    out = await call(gw, "hire.decide", {"ref": "D-000001", "verdict": "approve"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), out


async def test_the_overseer_reviews_a_draft_with_skill_review(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, OVERSEER)
    route = mock.post(f"{API}/internal/v1/roles/drafts/RD-0003/review").mock(
        return_value=httpx.Response(200, json={"ref": "RD-0003", "state": "eval"})
    )
    checks = dict.fromkeys(("injection", "secrets", "conflicts", "policy", "ceiling"), True)
    out = await call(
        gw,
        "skill.review",
        {"ref": "RD-0003", "verdict": "pass", "checks": checks, "notes_md": "ok"},
    )
    assert (out["outcome"], out["ref"]) == ("ok", "RD-0003"), out
    assert json.loads(route.calls[0].request.content)["checks"] == checks
