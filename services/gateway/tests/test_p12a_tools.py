"""Prompt 12 part A's tools (agents/tools.md v1.5): memo.write (A1, the
advisor) and substitute.call (A0): what each sends to the api, that agent
text is redacted on the way, and who may call them."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

ADVISOR = gate(employee="HQ-ADV", company="HQ", kind="advisor", role="advisor", scope="holding")
ASSISTANT = gate(
    employee="HQ-PA", company="HQ", kind="assistant", role="assistant", scope="holding"
)
DEV = gate(employee="TY-TECH-01", kind="employee", role="sre", department="TECH")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


MEMO = {
    "decision": "D-000123",
    "decision_version": 2,
    "summary_fa": "تأیید با یک شرط",
    "recommendation": "approve",
    "confidence": 0.7,
    "options": [{"title_fa": "تأیید", "pros_md": "سریع", "cons_md": "ایمیل a@b.example"}],
    "against_md": "هزینه برگشت‌ناپذیر است.",
    "risks": [{"title_fa": "هزینه", "likelihood": "low", "impact": "high", "mitigation_fa": "سقف"}],
    "questions": ["چرا حالا؟"],
    "citations": [{"kind": "decision", "ref": "D-000123"}],
}


async def test_memo_write_sends_the_memo_redacted_with_its_idempotency_key(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, ADVISOR)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(
            {"body": json.loads(request.content), "idem": request.headers.get("idempotency-key")}
        )
        return httpx.Response(
            200, json={"ref": "DM-0007", "state": "ready", "citations_dropped": 1}
        )

    mock.post(f"{API}/internal/v1/advisor/memos").mock(side_effect=handle)
    out = await call(gw, "memo.write", MEMO)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "DM-0007"), out
    assert out["result"] == {"ref": "DM-0007", "state": "ready", "citations_dropped": 1}
    body = seen[0]["body"]
    assert seen[0]["idem"] and body["decision"] == "D-000123" and body["against_md"]
    assert "a@b.example" not in json.dumps(body, ensure_ascii=False)  # masked on the way


async def test_memo_write_needs_the_case_against_and_is_the_advisors(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, ADVISOR)
    out = await call(gw, "memo.write", {**MEMO, "against_md": ""})
    assert (out["outcome"], out["code"]) == ("error", "invalid_args"), out
    Stub(mock, ASSISTANT)
    denied = await call(gw, "memo.write", MEMO)
    assert (denied["outcome"], denied["code"]) == ("denied", "tool_not_in_charter"), denied


async def test_substitute_call_asks_the_api_and_returns_its_labelled_answer(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, ASSISTANT)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"state": "queued", "call": "c-1"})

    mock.post(f"{API}/internal/v1/substitutes/call").mock(side_effect=handle)
    out = await call(
        gw, "substitute.call", {"seat": "assistant_errand", "input_md": "خلاصه کن: ali@x.example"}
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "c-1"), out
    assert seen[0]["seat"] == "assistant_errand" and "ali@x.example" not in seen[0]["input_md"]
    # The api's refusals come back as they are.
    mock.post(f"{API}/internal/v1/substitutes/call").mock(
        return_value=httpx.Response(
            503, json={"code": "channel_not_configured", "message_fa": "خارج شده"}
        )
    )
    off = await call(gw, "substitute.call", {"seat": "assistant_errand", "input_md": "x"})
    assert (off["outcome"], off["code"]) == ("error", "channel_not_configured")
    mock.post(f"{API}/internal/v1/substitutes/call").mock(
        return_value=httpx.Response(429, json={"code": "rate_limited"})
    )
    limited = await call(gw, "substitute.call", {"seat": "assistant_errand", "input_md": "x"})
    assert (limited["outcome"], limited["code"]) == ("denied", "rate_limited")


async def test_substitute_call_is_not_every_roles(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, DEV)
    out = await call(gw, "substitute.call", {"seat": "content_draft", "input_md": "x"})
    assert (out["outcome"], out["code"]) == ("denied", "tool_not_in_charter"), out


def test_the_new_tools_are_on_the_build_list() -> None:
    assert {"memo.write", "substitute.call"} <= tool_status.GATEWAY_TOOLS
    assert {"memo.write", "substitute.call"} <= set(T.TOOLS)
