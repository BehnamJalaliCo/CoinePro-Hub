"""Prompt 11 §4-§10's governance tools in the gateway (agents/tools.md v1.5,
contract §20.11): each validated, redacted and sent to its internal route with
the run's own token; none writes the charter or the matrix, none leaves the hub."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, TOKEN, Stub, call, gate

from hq_common import tool_status
from hq_gateway import governance as GV
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CEO = gate(employee="TY-CEO", kind="ceo", role="ceo", department=None, own_thread="TY-CEO")
NOW = "2026-10-22T08:00:00+00:00"
SOURCE = {"kind": "metric", "ref": "analytics:dau", "note": ""}


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=8000, tool_timeout_s=3)


class Api:
    def __init__(self, mock: respx.MockRouter) -> None:
        self.sent: list[tuple[str, str, Any, httpx.Headers]] = []
        mock.route(host="api.test", path__startswith="/internal/v1/governance/").mock(side_effect=self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else dict(request.url.params)
        self.sent.append((request.method, request.url.path, body, request.headers))
        path = request.url.path
        if path.endswith("/okr/draft"):
            return httpx.Response(200, json={"decision": "D-000042", "objectives": ["OB-0001"]})
        if path.endswith("/risks"):
            return httpx.Response(201, json={"ref": "RK-0001", "score": 20, "status": "open", "version": 1})
        if path.endswith("/authority"):
            return httpx.Response(200, json=[{"key": "hire.per_day", "limit": {"count_day": 5}}])
        return httpx.Response(200, json={"ok": True})


CALLS: list[tuple[str, dict[str, Any], str, str]] = [
    ("kpi.record", {"company": "TY", "key": "users.active", "value": 1200, "at": NOW, "source": SOURCE},
     "POST", "/internal/v1/governance/kpis/record"),
    ("okr.draft", {"company": "TY", "quarter": "1405-Q3", "objectives": [
        {"title_fa": "رشد", "key_results": [{"title_fa": "کاربر", "kpi": "users.active", "start": 1, "target": 2}]}]},
     "POST", "/internal/v1/governance/okr/draft"),
    ("okr.checkin", {"key_result": "KR-0001", "confidence": 0.7, "note_md": "خوب", "evidence": [SOURCE]},
     "POST", "/internal/v1/governance/okr/checkin"),
    ("outcome.note", {"ref": "OR-0001", "note_md": "نتیجه"}, "POST", "/internal/v1/governance/outcomes/note"),
    ("risk.raise", {"company": "TY", "title_fa": "ریسک", "category": "vendor", "likelihood": 4, "impact": 5},
     "POST", "/internal/v1/governance/risks"),
    ("risk.update", {"ref": "RK-0001", "version": 1, "impact": 2, "note": "کمتر شد"},
     "POST", "/internal/v1/governance/risks/update"),
    ("calendar.read", {"from": NOW, "to": NOW}, "GET", "/internal/v1/governance/calendar"),
    ("calendar.add", {"company": "TY", "kind": "campaign", "title_fa": "کمپین", "starts_at": NOW, "ends_at": NOW},
     "POST", "/internal/v1/governance/calendar"),
    ("authority.read", {}, "GET", "/internal/v1/governance/authority"),
    ("governance.read", {"what": "cards"}, "GET", "/internal/v1/governance/read"),
]  # fmt: skip


def test_the_ten_tools_are_live_and_in_the_ceos_charter() -> None:
    assert set(GV.TOOLS) <= set(T.TOOLS) and set(GV.TOOLS) <= tool_status.GATEWAY_TOOLS
    assert set(GV.TOOLS) <= set(LIB.allowed("ceo"))
    assert not {t for t in T.TOOLS if t.startswith(("charter.", "authority.")) and t != "authority.read"}


@pytest.mark.parametrize(("tool", "args", "method", "path"), CALLS)
async def test_each_tool_calls_its_route_with_the_runs_token(
    mock: respx.MockRouter, gw: Gateway, tool: str, args: dict[str, Any], method: str, path: str
) -> None:
    Stub(mock, CEO)
    api = Api(mock)
    out = await call(gw, tool, args)
    assert out["outcome"] == "ok", out
    (sent,) = api.sent
    assert (sent[0], sent[1]) == (method, path)
    assert sent[3]["authorization"] == f"Bearer {TOKEN}"
    if method == "POST":
        assert sent[3].get("idempotency-key")  # a retried step never writes twice


async def test_a_secret_in_a_risk_is_redacted_and_bad_input_is_refused(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CEO)
    api = Api(mock)
    key = "sk-ant-" + "a" * 40
    out = await call(gw, "risk.raise", {"company": "TY", "title_fa": "کلید", "body_md": f"کلید {key} نشت کرد",
                                        "category": "security", "likelihood": 3, "impact": 5})  # fmt: skip
    assert out["outcome"] == "ok"
    assert key not in api.sent[0][2]["body_md"]
    bad = await call(gw, "risk.raise", {"company": "TY", "title_fa": "x", "category": "weather",
                                        "likelihood": 9, "impact": 1})  # fmt: skip
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")
    bad = await call(gw, "calendar.add", {"company": "TY", "kind": "deploy", "title_fa": "x",
                                          "starts_at": NOW, "ends_at": NOW})  # fmt: skip
    assert bad["code"] == "invalid_args"  # a deploy comes from its card, never from calendar.add
    bad = await call(gw, "kpi.record", {"company": "TY", "key": "users.active", "value": 1, "at": NOW})
    assert bad["code"] == "invalid_args" and "source" in json.dumps(bad["fields"])


async def test_propose_carries_expected_and_the_cards_warnings(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    seen: list[dict[str, Any]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={"ref": "D-000050", "status": "pending", "warnings": ["expected_missing"]})

    mock.post(f"{API}/internal/v1/decisions").mock(side_effect=answer)
    mock.get(f"{API}/internal/v1/work/ref/W-000101").mock(
        return_value=httpx.Response(200, json={"id": "11111111-1111-1111-1111-111111111111", "ref": "W-000101"})
    )
    expected = {"metric_fa": "کاربر فعال", "kpi": "users.active", "baseline": 100, "target": 150, "by_days": 60}
    out = await call(gw, "propose", {"kind": "proposal", "title_fa": "کمپین", "expected": expected})
    assert out["outcome"] == "ok" and seen[0]["expected"] == expected
    out = await call(gw, "propose", {"kind": "proposal", "title_fa": "بی‌قول"})
    assert out["result"]["warnings"] == ["expected_missing"] and "expected" not in seen[1]
    bad = await call(gw, "propose", {"kind": "proposal", "title_fa": "x", "expected": {**expected, "by_days": 45}})
    assert bad["code"] == "invalid_args"
    for kind in ("authority_change", "risk_acceptance"):
        assert (await call(gw, "propose", {"kind": kind, "title_fa": "x"}))["outcome"] == "ok"
    assert (await call(gw, "propose", {"kind": "okr", "title_fa": "x"}))["code"] == "invalid_args"
