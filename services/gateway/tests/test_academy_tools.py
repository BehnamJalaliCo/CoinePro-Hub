"""The skill library's and the academy's gateway tools (prompt 08 §6-§7)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa


@pytest.fixture
def mock() -> AsyncIterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


REVIEW = {"verdict": "pass", "checks": {"injection": True}, "notes_md": "clean"}


async def test_skill_review_routes_by_ref(mock: respx.MockRouter, gw: Gateway) -> None:
    """The overseer reviews a skill version or a teaching with one tool."""
    s = Stub(
        mock,
        gate(employee="HQ-OVR", company="HQ", kind="overseer", role="overseer", scope="holding"),
    )
    skill = mock.post(f"{API}/internal/v1/skills/SK-101/review").mock(
        return_value=httpx.Response(
            200, json={"ref": "SK-101", "version": 2, "status": "in_review"}
        )
    )
    teach = mock.post(f"{API}/internal/v1/academy/teach/TE-0007/review").mock(
        return_value=httpx.Response(200, json={"ref": "TE-0007", "status": "proposed"})
    )
    out = await call(gw, "skill.review", {"ref": "SK-101", "version": 2, **REVIEW})
    assert (out["outcome"], out["ref"], out["class"]) == ("ok", "SK-101@2", "A2"), out
    assert json.loads(skill.calls.last.request.content)["verdict"] == "pass"
    assert "sha256" not in json.loads(skill.calls.last.request.content)
    # 8.1 §1.6: the sha256 of the text the work item showed goes through.
    sha = "ab" * 32
    out = await call(gw, "skill.review", {"ref": "SK-101", "version": 2, **REVIEW, "sha256": sha})
    assert json.loads(skill.calls.last.request.content)["sha256"] == sha, out
    bad = await call(gw, "skill.review", {"ref": "SK-101", **REVIEW, "sha256": "not-a-sha"})
    assert bad["code"] == "invalid_args"
    out = await call(gw, "skill.review", {"ref": "TE-0007", **REVIEW})
    assert (out["outcome"], out["ref"]) == ("ok", "TE-0007") and teach.called
    bad = await call(gw, "skill.review", {"ref": "W-000101", **REVIEW})
    assert bad["code"] == "invalid_args"
    assert s.opa_inputs[-1]["action"]["name"] == "skill.review"
    # The overseer runs no eval and drafts no teaching (the AI Ops head does).
    assert (await call(gw, "eval.run", {}))["code"] == "tool_not_in_charter"
    assert (await call(gw, "teach.draft", {}))["code"] == "tool_not_in_charter"


async def test_eval_run_and_teach_draft(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(
        mock,
        gate(
            employee="HQ-AIOPS-MGR",
            company="HQ",
            kind="manager",
            role="aiops_head",
            scope="holding",
        ),
    )
    run = mock.post(f"{API}/internal/v1/academy/evals/run").mock(
        return_value=httpx.Response(202, json={"id": "e1", "status": "queued"})
    )
    out = await call(
        gw,
        "eval.run",
        {"suite": "EV-001", "subject": {"kind": "skill", "ref": "SK-101", "version": 2}},
    )
    assert (out["outcome"], out["ref"], out["class"]) == ("ok", "eval:e1", "A2"), out
    assert json.loads(run.calls.last.request.content)["subject"]["kind"] == "skill"
    bad = await call(
        gw, "eval.run", {"suite": "X-1", "subject": {"kind": "skill", "ref": "a", "version": 1}}
    )
    assert bad["code"] == "invalid_args"
    draft = mock.post(f"{API}/internal/v1/academy/teach/TE-0007/draft").mock(
        return_value=httpx.Response(200, json={"ref": "TE-0007", "status": "proposed"})
    )
    phone = "0912" + "345" + "6789"
    out = await call(
        gw,
        "teach.draft",
        {"ref": "TE-0007", "proposal": {"kind": "charter_rule", "diff_md": f"Never call {phone}."}},
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "TE-0007"), out
    assert phone not in draft.calls.last.request.content.decode()  # redacted on its way out
    # A CEO has none of these tools.
    Stub(mock, gate(employee="TY-CEO", kind="ceo", role="ceo"))
    for tool in ("skill.review", "eval.run", "teach.draft"):
        assert (await call(gw, tool, {}))["code"] == "tool_not_in_charter", tool
