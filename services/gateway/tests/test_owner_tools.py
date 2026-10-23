"""Prompt 12 §2 (agents/tools.md v1.5): `ask.answer`, the Hub Librarian's
answer to the owner's «از هاب بپرس» (A1; redacted on the way; the api checks
every citation against the retrieved passages), and `knowledge.search`'s new
kinds docs, code and notes."""

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

LIBRARIAN = gate(
    employee="HQ-LIB", company="HQ", kind="system", role="librarian", department=None,
    scope="holding",
)  # fmt: skip


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


async def test_the_librarians_answer_goes_to_the_api_redacted(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, LIBRARIAN)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"ref": "AK-0001", "state": "done", "citations": [{"kind": "resolution", "ref": "M-0007"}],
                  "citations_dropped": 1, "answer_md": "x"},
        )  # fmt: skip

    mock.post(f"{API}/internal/v1/ask/answer").mock(side_effect=handle)
    out = await call(
        gw,
        "ask.answer",
        {
            "ask": "AK-0001",
            "answer_md": "بودجه ۲۰۰ دلار است (ali@example.com).",
            "citations": [
                {"kind": "resolution", "ref": "M-0007"},
                {"kind": "code", "repo": "acme/x", "path": "a.py", "lines": [1, 60]},
            ],
        },
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "AK-0001"), out
    assert out["result"] == {
        "ref": "AK-0001",
        "state": "done",
        "citations": 1,
        "citations_dropped": 1,
    }
    assert "ali@example.com" not in seen[0]["answer_md"]
    assert seen[0]["citations"][1] == {
        "kind": "code",
        "repo": "acme/x",
        "path": "a.py",
        "lines": [1, 60],
    }


async def test_a_bad_ask_ref_never_reaches_the_api(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, LIBRARIAN)
    route = mock.post(f"{API}/internal/v1/ask/answer")
    out = await call(gw, "ask.answer", {"ask": "D-0001", "answer_md": "x"})
    assert out["code"] == "invalid_args" and not route.called


async def test_knowledge_search_passes_the_new_kinds(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, LIBRARIAN)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    mock.get(f"{API}/internal/v1/knowledge/search").mock(side_effect=handle)
    out = await call(gw, "knowledge.search", {"q": "پشتیبان", "kinds": ["docs", "code"]})
    assert out["outcome"] == "ok", out
    assert seen[0].url.params.get_list("kinds") == ["docs", "code"]
    bad = await call(gw, "knowledge.search", {"q": "پشتیبان", "kinds": ["secrets"]})
    assert bad["code"] == "invalid_args"
