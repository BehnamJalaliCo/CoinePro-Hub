"""The support desk's tools (prompt 10 §12, agents/tools.md v1.5): what each
sends to the api, what the model gets back, and that none of them sends free
text to a customer (support.draft is only a draft; the api's code decides)."""

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

AGENT = gate(employee="TY-SALES-01", kind="employee", role="support_agent", department="SALES")
LEAD = gate(employee="TY-SALES-02", kind="employee", role="support_lead", department="SALES")
RESCUE = gate(employee="TY-SALES-03", kind="employee", role="referral_rescue", department="SALES")
OVERSEER = gate(
    employee="HQ-OVR", company="HQ", kind="overseer", role="overseer", department="OVS",
    scope="holding",
)  # fmt: skip


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


async def test_kb_search_reads_the_companys_articles(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, AGENT)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"ref": "KB-0001", "version": 2, "score": 1.0}])

    mock.get(f"{API}/internal/v1/support/kb").mock(side_effect=handle)
    out = await call(gw, "kb.search", {"q": "حداقل موجودی", "kind": "faq"})
    assert (out["outcome"], out["class"]) == ("ok", "A0"), out
    assert out["result"] == {
        "articles": [{"ref": "KB-0001", "version": 2, "score": 1.0}],
        "count": 1,
    }
    assert seen[0].url.params["kind"] == "faq" and "company" not in seen[0].url.params


async def test_a_draft_goes_to_the_api_which_decides(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, AGENT)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(
            {"body": json.loads(request.content), "idem": request.headers.get("idempotency-key")}
        )
        return httpx.Response(
            200,
            json={"decision": "waiting_owner", "problems": [],
                  "message": {"status": "draft", "blocked_reasons": [], "checks": {"guard": "pass"}}},
        )  # fmt: skip

    mock.post(f"{API}/internal/v1/support/conversations/SC-000123/draft").mock(side_effect=handle)
    args = {"conversation": "SC-000123", "body_md": "حداقل موجودی 100 USDT است.",
            "kb_refs": ["KB-0001@2"], "confidence": 0.8}  # fmt: skip
    out = await call(gw, "support.draft", args)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "SC-000123"), out
    assert out["result"]["decision"] == "waiting_owner" and seen[0]["idem"]
    assert seen[0]["body"] == {
        "body_md": args["body_md"],
        "kb_refs": ["KB-0001@2"],
        "confidence": 0.8,
    }
    bad = await call(gw, "support.draft", {**args, "kb_refs": ["KB-0001"]})  # a ref without version
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args") and len(seen) == 1
    worse = await call(gw, "support.draft", {**args, "confidence": 2})
    assert worse["code"] == "invalid_args"


async def test_handoff_and_proposals_for_the_support_people(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, LEAD)
    mock.post(f"{API}/internal/v1/support/conversations/SC-000124/handoff").mock(
        return_value=httpx.Response(200, json={"ref": "SC-000124", "state": "waiting_owner"})
    )
    mock.post(f"{API}/internal/v1/support/kb").mock(
        return_value=httpx.Response(
            201,
            json={
                "ref": "KB-0009",
                "version": 1,
                "kind": "faq",
                "status": "proposed",
                "expires_at": "2027-04-20T00:00:00Z",
                "answer_md": "x",
            },
        )
    )
    out = await call(gw, "support.handoff", {"conversation": "SC-000124", "reason": "complaint"})
    assert (out["outcome"], out["result"]) == (
        "ok",
        {"conversation": "SC-000124", "state": "waiting_owner"},
    )
    prop = await call(
        gw, "kb.propose",
        {"company": "TY", "kind": "faq", "question_fa": "سؤال", "answer_md": "جواب", "source_ref": "SC-000124"},
    )  # fmt: skip
    assert (prop["outcome"], prop["class"], prop["ref"]) == ("ok", "A1", "KB-0009@1")
    assert "answer_md" not in prop["result"]
    # The lead does not draft: that tool is not in its charter.
    no = await call(
        gw,
        "support.draft",
        {"conversation": "SC-000124", "body_md": "x", "kb_refs": [], "confidence": 0.5},
    )
    assert (no["outcome"], no["code"]) == ("denied", "tool_not_in_charter")


async def test_the_rescue_specialist_has_no_send_tool(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, RESCUE)
    for tool in ("support.draft", "support.handoff", "support.mystery", "message.owner"):
        out = await call(gw, tool, {})
        assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), tool


async def test_the_mystery_customer_is_the_overseers(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, OVERSEER)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"result": "deferred", "conversation": None})

    mock.post(f"{API}/internal/v1/support/mystery").mock(side_effect=handle)
    out = await call(
        gw, "support.mystery", {"company": "TY", "question_fa": "حداقل موجودی چقدر است؟"}
    )
    assert (out["outcome"], out["class"], out["result"]["result"]) == ("ok", "A2", "deferred"), out
    both = await call(
        gw, "support.mystery", {"company": "TY", "question_fa": "x", "conversation": "SC-000001"}
    )
    neither = await call(gw, "support.mystery", {"company": "TY"})
    assert both["code"] == neither["code"] == "invalid_args" and len(seen) == 1
