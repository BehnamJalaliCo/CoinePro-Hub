"""The internet tools in the gateway (prompt 07 §2): reserve at the api, carry
out at egress, log, and the model's result (untrusted web data, no secret)."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa
from hq_gateway.web import Egress

EGRESS = "http://egress.test"
SECRET = "acct-" + "Q" * 30
FILE_ID = "0193e7a1-0000-7000-8000-00000000abcd"


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    """The gateway without egress wired (EGRESS_URL empty)."""
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def gw_web() -> Gateway:
    api = T.Api(API, 5, egress=Egress(EGRESS, 5))
    return Gateway(LIB, api, Opa(OPA), max_result_chars=8000, tool_timeout_s=3)


class Net:
    """The api's egress routes and the egress service, recording what was sent."""

    def __init__(self, mock: respx.MockRouter) -> None:
        self.reserved: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.logged: list[dict[str, Any]] = []
        self.uploads: list[httpx.Request] = []
        self.reserve_answer: tuple[int, dict[str, Any]] = (
            200,
            {"max_bytes": 1000, "requests_left": 9, "browser_s_left": 60, "account": None},
        )
        self.egress_answer: dict[str, Any] = {
            "outcome": "ok",
            "data": {"results": []},
            "entries": [],
        }
        mock.post(f"{API}/internal/v1/egress/reserve").mock(side_effect=self._reserve)
        mock.post(f"{API}/internal/v1/egress/log").mock(side_effect=self._log)
        mock.post(f"{API}/internal/v1/files").mock(side_effect=self._upload)
        mock.post(url__startswith=f"{EGRESS}/v1/").mock(side_effect=self._egress)

    def _reserve(self, request: httpx.Request) -> httpx.Response:
        self.reserved.append(json.loads(request.content))
        status, body = self.reserve_answer
        return httpx.Response(status, json=body)

    def _log(self, request: httpx.Request) -> httpx.Response:
        self.logged.append(json.loads(request.content))
        return httpx.Response(204)

    def _upload(self, request: httpx.Request) -> httpx.Response:
        self.uploads.append(request)
        return httpx.Response(201, json={"id": FILE_ID, "mime": "image/png", "size": 9})

    def _egress(self, request: httpx.Request) -> httpx.Response:
        self.sent.append({"path": request.url.path, **json.loads(request.content)})
        return httpx.Response(200, json=self.egress_answer)


ENTRY = {"tool": "web.search", "method": "GET", "host": "searxng", "kind": "search", "status": 200,
         "bytes_in": 10, "bytes_out": 0, "ms": 5, "blocked_reason": None, "class": "A0"}  # fmt: skip


async def test_search_reserves_carries_out_and_logs(mock: respx.MockRouter) -> None:
    s, net = Stub(mock), Net(mock)
    net.egress_answer = {
        "outcome": "ok",
        "data": {
            "results": [{"title": "t", "url": "https://e.com", "snippet": "x"}],
            "source": "web",
        },
        "entries": [ENTRY],
    }
    out = await call(gw_web(), "web.search", {"q": "persian calendar", "site": "example.com"})
    assert out["outcome"] == "ok" and out["class"] == "A0"
    assert out["result"]["results"][0]["url"] == "https://e.com"
    assert net.reserved[-1]["strings"] == ["persian calendar", "example.com"]
    assert net.reserved[-1]["class"] == "A0" and net.reserved[-1]["tool"] == "web.search"
    ctx = net.sent[-1]["ctx"]
    assert (ctx["company"], ctx["actor"], ctx["max_bytes"]) == ("TY", "TY-TECH-MGR", 1000)
    assert net.logged[-1]["entries"] == [ENTRY]
    assert s.records[-1]["tool"] == "web.search" and s.records[-1]["class"] == "A0"


async def test_browse_with_an_account_is_a2_and_stores_its_files(mock: respx.MockRouter) -> None:
    s, net = Stub(mock), Net(mock)
    net.reserve_answer = (200, {"max_bytes": 5000, "account": {"key": "ga", "site": "example.com",
                                                               "secret": SECRET}})  # fmt: skip
    png = base64.b64encode(b"\x89PNG data").decode()
    net.egress_answer = {
        "outcome": "ok",
        "data": {
            "steps": [{"i": 0, "do": "goto", "ok": True}],
            "final_url": "https://example.com/",
        },
        "entries": [{**ENTRY, "tool": "web.browse", "kind": "browse", "class": "A2"}],
        "files": [
            {"kind": "screenshot", "step": 1, "name": "s.png", "mime": "image/png", "data_b64": png}
        ],
    }
    steps = [{"do": "goto", "url": "https://example.com/"}, {"do": "screenshot"}]
    out = await call(gw_web(), "web.browse", {"steps": steps, "account": "ga"})
    assert out["outcome"] == "ok" and out["class"] == "A2"
    assert s.opa_inputs[-1]["action"]["class"] == "A2"  # the call's own class went to OPA
    assert net.sent[-1]["account"]["secret"] == SECRET  # to egress, for this call only
    assert SECRET not in json.dumps(out)  # never to the model
    assert out["result"]["files"] == [{"file_id": FILE_ID, "kind": "screenshot", "mime": "image/png",
                                       "size": 9, "step": 1}]  # fmt: skip
    assert net.uploads[-1].headers["content-type"] == "image/png"
    assert net.uploads[-1].url.params["name"] == "s.png"
    # Without an account the same browse is A0.
    net.reserve_answer = (200, {"max_bytes": 5000, "account": None})
    out = await call(gw_web(), "web.browse", {"steps": steps})
    assert out["class"] == "A0" and s.opa_inputs[-1]["action"]["class"] == "A0"


async def test_refusals_come_back_with_their_codes(mock: respx.MockRouter) -> None:
    Stub(mock)
    net = Net(mock)
    net.reserve_answer = (403, {"code": "internal_data", "message_fa": "داده‌ی داخلی"})
    out = await call(gw_web(), "web.search", {"q": "status of W-000123"})
    assert (out["outcome"], out["code"]) == ("denied", "internal_data") and not net.sent
    net.reserve_answer = (429, {"code": "egress_limit"})
    assert (await call(gw_web(), "web.read", {"url": "https://e.com/"}))["code"] == "egress_limit"
    net.reserve_answer = (403, {"code": "needs_owner"})
    out = await call(
        gw_web(), "http.request", {"method": "POST", "url": "https://e.com/pay", "json": {"a": 1}}
    )
    assert (out["outcome"], out["code"], out["class"]) == ("denied", "needs_owner", "A2")
    assert "propose" in out["hint_fa"]
    net.reserve_answer = (200, {"max_bytes": 1, "account": None})
    net.egress_answer = {"outcome": "blocked", "code": "needs_owner", "data": {"blocked": {"step": 0}},
                         "entries": []}  # fmt: skip
    out = await call(gw_web(), "web.browse", {"steps": [{"do": "click", "target": "#buy"}]})
    assert (out["outcome"], out["code"]) == ("denied", "needs_owner") and out["hint_fa"]
    net.egress_answer = {"outcome": "blocked", "code": "private_address", "entries": [ENTRY]}
    out = await call(gw_web(), "web.read", {"url": "https://intranet.example/"})
    assert (out["outcome"], out["code"]) == ("denied", "private_address") and net.logged


async def test_classes_inputs_and_wiring(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock)
    Net(mock)
    out = await call(gw_web(), "http.request", {"method": "GET", "url": "https://api.e.com/v1"})
    assert out["class"] == "A0"
    out = await call(
        gw_web(), "http.request", {"method": "GET", "url": "https://api.e.com/v1", "account": "ga"}
    )
    assert out["class"] == "A2"
    for bad in (
        {"method": "GET", "url": "ftp://e.com"},
        {"method": "GET", "url": "https://e.com", "headers": {"X-A": "1\r\nInjected: yes"}},
        {"method": "TRACE", "url": "https://e.com"},
    ):
        out = await call(gw_web(), "http.request", bad)
        assert (out["outcome"], out["code"]) == ("error", "invalid_args"), bad
    bad = await call(
        gw_web(), "web.browse", {"steps": [{"do": "goto", "url": "javascript:alert(1)"}]}
    )
    assert bad["code"] == "invalid_args"
    # Without egress wired: refused before anything leaves.
    out = await call(gw, "web.search", {"q": "anything"})
    assert (out["outcome"], out["code"]) == ("error", "channel_not_configured")
    # egress.recent is not in the CTO's charter; the security analyst has it.
    assert (await call(gw_web(), "egress.recent", {}))["code"] == "tool_not_in_charter"
    s.gate = gate(employee="HQ-SEC-01", company="HQ", kind="employee", role="security_analyst",
                  scope="holding", department="OVS")  # fmt: skip
    mock.get(f"{API}/internal/v1/egress/recent").mock(
        return_value=httpx.Response(200, json={"items": [], "next_cursor": None})
    )
    out = await call(gw_web(), "egress.recent", {"blocked": True})
    assert out["outcome"] == "ok" and out["result"] == {"items": [], "next_cursor": None}
