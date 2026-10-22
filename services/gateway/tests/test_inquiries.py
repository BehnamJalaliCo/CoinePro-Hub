"""Prompt 08 §3, §5 tools: inquiries, errands, the owner's planner, workshop.read."""

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


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


KEY = "sk-" + "ant-" + "api03-" + "Qq9" * 14
PA = gate(employee="HQ-PA", company="HQ", kind="assistant", role="assistant", scope="holding",
          department=None, own_thread="P", work_ref=None)  # fmt: skip
ADV = gate(employee="HQ-ADV", company="HQ", kind="advisor", role="advisor", scope="holding",
           department=None, own_thread="A", work_ref=None)  # fmt: skip


async def test_inquiry_ask_and_answer(mock: respx.MockRouter, gw: Gateway) -> None:
    sent: list[dict[str, Any]] = []

    def asked(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(
            201,
            json={
                "ref": "Q-0007",
                "status": "open",
                "due_at": "2026-10-19T08:00:00Z",
                "work_ref": "W-000900",
            },
        )

    mock.post(f"{API}/internal/v1/inquiries").mock(side_effect=asked)
    s = Stub(mock, ADV)
    out = await call(
        gw, "inquiry.ask", {"to": "FX-CEO", "question_md": f"کلید {KEY} چیست؟", "due_in_hours": 24}
    )
    assert (out["outcome"], out["ref"], out["class"]) == ("ok", "Q-0007", "A1"), out
    assert out["result"] == {
        "inquiry": "Q-0007",
        "to": "FX-CEO",
        "due_at": "2026-10-19T08:00:00Z",
        "work": "W-000900",
    }
    assert KEY not in json.dumps(sent)  # what leaves is redacted
    assert s.opa_inputs[-1]["action"]["class"] == "A1"
    bad = await call(gw, "inquiry.ask", {"to": "FX-CEO", "question_md": "x", "due_in_hours": "24"})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")  # strict: no "24"
    # The CEO answers (its own tool); the advisor's charter has no inquiry.answer.
    no = await call(gw, "inquiry.answer", {"ref": "Q-0007", "answer_md": "x"})
    assert (no["outcome"], no["code"]) == ("denied", "tool_not_in_charter")
    mock.post(f"{API}/internal/v1/inquiries/Q-0007/answer").mock(
        return_value=httpx.Response(
            200,
            json={
                "ref": "Q-0007",
                "status": "answered",
                "answer_message_ref": "A-0042",
                "thread_ref": "A",
            },
        )
    )
    Stub(mock, gate(employee="FX-CEO", company="FX", kind="ceo", role="ceo", department=None))
    ok = await call(
        gw,
        "inquiry.answer",
        {
            "ref": "Q-0007",
            "answer_md": "فروش ۱۲۰",
            "evidence": [{"kind": "metric", "ref": "sales"}],
        },
    )
    assert ok["outcome"] == "ok" and ok["result"] == {
        "inquiry": "Q-0007", "status": "answered", "message": "A-0042", "thread": "A",
    }  # fmt: skip


async def test_errand_tools_and_the_planner(mock: respx.MockRouter, gw: Gateway) -> None:
    errand = {
        "ref": "E-0003",
        "status": "working",
        "steps": [{"kind": "search"}],
        "decision_ref": None,
    }
    mock.post(f"{API}/internal/v1/errands/E-0003/steps").mock(
        return_value=httpx.Response(200, json=errand)
    )
    mock.post(f"{API}/internal/v1/errands/E-0003/finish").mock(
        return_value=httpx.Response(200, json={**errand, "status": "done"})
    )
    planned: list[dict[str, Any]] = []

    def plan(request: httpx.Request) -> httpx.Response:
        planned.append(json.loads(request.content))
        return httpx.Response(201, json={"ref": "PL-0001", "at": "2026-10-20T06:00:00Z"})

    mock.post(f"{API}/internal/v1/planner").mock(side_effect=plan)
    s = Stub(mock, PA)
    out = await call(
        gw,
        "errand.step",
        {"ref": "E-0003", "kind": "search", "summary_fa": "جستجو", "data": {"q": KEY}},
    )
    assert (out["outcome"], out["class"]) == ("ok", "A2") and out["result"]["steps"] == 1
    done = await call(gw, "errand.finish", {"ref": "E-0003", "result_md": "نتیجه"})
    assert done["result"]["status"] == "done"
    pl = await call(gw, "planner.add", {"title_fa": "تمدید", "at": "2026-10-20T06:00:00Z"})
    assert pl["ref"] == "PL-0001" and planned[0]["at"].startswith("2026-10-20T06:00:00")
    assert all(r["tool"] in ("errand.step", "errand.finish", "planner.add") for r in s.records)
    bad = await call(gw, "errand.step", {"ref": "E-3", "kind": "search", "summary_fa": "x"})
    assert bad["code"] == "invalid_args"
    # Only the assistant has them.
    Stub(mock, ADV)
    assert (await call(gw, "planner.add", {"title_fa": "x", "at": "2026-10-20T06:00:00Z"}))[
        "code"
    ] == "tool_not_in_charter"


async def test_workshop_read(mock: respx.MockRouter, gw: Gateway) -> None:
    seen: list[httpx.Request] = []

    def read(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"session": {"ref": "S-0001"}, "events": []})

    mock.get(f"{API}/internal/v1/workshop/sessions/S-0001").mock(side_effect=read)
    Stub(mock, ADV)
    out = await call(gw, "workshop.read", {"session_ref": "S-0001", "after": 3})
    assert (out["outcome"], out["ref"], out["class"]) == ("ok", "workshop:S-0001", "A0")
    assert seen[0].url.params["after"] == "3"
    assert (await call(gw, "workshop.read", {"session_ref": "../x"}))["code"] == "invalid_args"
