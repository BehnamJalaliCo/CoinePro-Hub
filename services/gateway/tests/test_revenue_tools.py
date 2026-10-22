"""Prompt 10's revenue and growth tools in the gateway (contract §19.10) and the
worker's connector route (contract §19.1): the api decides who may, egress
signs and reduces, the gateway never hands back a secret or a balance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, TOKEN, WORKER, Stub, call, gate

from hq_common import tool_status
from hq_gateway import revenue as RV
from hq_gateway import tools as T
from hq_gateway.app import State, build_app
from hq_gateway.config import Settings
from hq_gateway.gateway import Gateway, Opa
from hq_gateway.web import Egress

EGRESS = "http://egress.test"
SECRET = "ak-" + "P" * 29 + ":" + "sk-" + "R" * 40
WORKER_API = "worker-api-token-" + "z" * 40
ACCOUNT = {"key": "lbank-aff-ty", "site": "affiliate.lbank.test", "secret": SECRET,
           "inject": {"kind": "signer", "signer": "lbank-v2"}, "ports": [], "allow": []}  # fmt: skip
ENTRY = {"tool": "referral.check", "method": "POST", "host": "affiliate.lbank.test", "kind": "request",
         "status": 200, "bytes_in": 80, "bytes_out": 300, "ms": 20, "blocked_reason": None, "class": "A0"}  # fmt: skip
GRANT = {"adapter": "lbank-affiliate-v2", "endpoint": "invite/user/info", "params": {"uid": "12345"},
         "local": {"min_balance": "100"}, "reservation": "0193e7a1-0000-7000-8000-0000000000aa",
         "max_bytes": 1000}  # fmt: skip
SUPPORT = gate(employee="TY-SALES-01", kind="employee", role="support_agent", department="SALES")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


def gw_egress() -> Gateway:
    api = T.Api(API, 5, egress=Egress(EGRESS, 5))
    return Gateway(LIB, api, Opa(OPA), max_result_chars=8000, tool_timeout_s=3)


class Lbank:
    """The api's referral-check routes and egress's connector, recorded."""

    def __init__(self, mock: respx.MockRouter) -> None:
        self.checks: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.check_answer: dict[str, Any] = {
            "done": False,
            "grant": {**GRANT, "account": dict(ACCOUNT)},
        }
        self.egress_answer: dict[str, Any] = {
            "outcome": "ok", "code": None, "data": {"invitee": True, "meets_minimum": True}, "entries": [ENTRY],
        }  # fmt: skip
        mock.post(f"{API}/internal/v1/growth/referral-check").mock(side_effect=self._check)
        mock.post(f"{API}/internal/v1/growth/referral-check/result").mock(side_effect=self._result)
        mock.post(f"{EGRESS}/v1/connectors/call").mock(side_effect=self._egress)

    def _check(self, request: httpx.Request) -> httpx.Response:
        self.checks.append(json.loads(request.content))
        return httpx.Response(200, json=self.check_answer)

    def _result(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.results.append(body)
        return httpx.Response(200, json={"invitee": body["invitee"], "meets_minimum": body["meets_minimum"],
                                         "rescue": {"ref": "RC-000007", "state": "rescued"},
                                         "checked_at": "2026-10-22T08:00:00+00:00", "balance": "120.5"})  # fmt: skip

    def _egress(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(json.loads(request.content))
        return httpx.Response(200, json=self.egress_answer)


async def test_referral_check_answers_invitee_and_minimum_only(mock: respx.MockRouter) -> None:
    Stub(mock, SUPPORT)
    net = Lbank(mock)
    gw = gw_egress()
    out = await call(gw, "referral.check", {"company": "TY", "exchange": "lbank", "uid": "12345"})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "referral:lbank"), out
    assert out["result"] == {"invitee": True, "meets_minimum": True,
                             "rescue": {"ref": "RC-000007", "state": "rescued"}}  # fmt: skip
    # Egress got the signer account for this one call; nothing else ever did.
    sent = net.sent[0]
    assert sent["account"]["secret"] == SECRET and sent["tool"] == "referral.check"
    assert (sent["endpoint"], sent["params"], sent["local"]) == ("invite/user/info", {"uid": "12345"},
                                                                 {"min_balance": "100"})  # fmt: skip
    assert sent["ctx"]["actor"] == "TY-SALES-01" and sent["ctx"]["company"] == "TY"
    result = net.results[0]
    assert (
        result["ok"] is True and result["reservation"] == net.check_answer["grant"]["reservation"]
    )
    assert result["entries"][0]["tool"] == "referral.check" and "account" not in result
    for blob in (json.dumps(out), json.dumps(result)):
        assert SECRET not in blob and "sk-" not in blob and "120.5" not in blob
    # A fresh cached answer: no egress call at all.
    net.check_answer = {
        "done": True,
        "invitee": False,
        "meets_minimum": None,
        "cached": True,
        "rescue": None,
    }
    out = await call(gw, "referral.check", {"company": "TY", "exchange": "lbank", "uid": "12345"})
    assert out["result"] == {"invitee": False, "meets_minimum": None} and len(net.sent) == 1
    # An answer egress could not get: the api records the failure.
    net.check_answer = {"done": False, "grant": {**GRANT, "account": dict(ACCOUNT)}}
    net.egress_answer = {"outcome": "error", "code": "upstream_error", "data": {"error_code": 10002},
                         "entries": [ENTRY]}  # fmt: skip
    mock.post(f"{API}/internal/v1/growth/referral-check/result").mock(
        return_value=httpx.Response(502, json={"code": "connector_failed"})
    )
    out = await call(gw, "referral.check", {"company": "TY", "exchange": "lbank", "uid": "12345"})
    assert (out["outcome"], out["code"]) == ("error", "connector_failed")
    # Inputs: never a raw balance or any other field.
    bad = await call(gw, "referral.check", {"company": "TY", "exchange": "lbank", "uid": "1 2"})
    assert bad["code"] == "invalid_args"


async def test_the_rescue_specialist_has_no_sending_tool(mock: respx.MockRouter) -> None:
    allowed = set(LIB.allowed("referral_rescue"))
    assert {"rescue.update", "referral.check", "funnel.read"} <= allowed
    assert not allowed & {"notify", "message.owner", "support.draft"}
    Stub(
        mock,
        gate(employee="TY-SALES-02", kind="employee", role="referral_rescue", department="SALES"),
    )
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ref": "RC-000003", "state": "lost"})

    mock.post(f"{API}/internal/v1/growth/rescue/RC-000003/update").mock(side_effect=handle)
    out = await call(
        gw_egress(), "rescue.update", {"ref": "RC-000003", "state": "lost", "note_fa": "تمام شد"}
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "RC-000003"), out
    assert seen[0].headers.get("idempotency-key") and json.loads(seen[0].content)["state"] == "lost"


async def test_the_reads_and_feedback_tag_reach_their_routes(mock: respx.MockRouter) -> None:
    Stub(mock, gate(employee="TY-CEO", kind="ceo", role="ceo", department=None))
    rev = mock.post(f"{API}/internal/v1/revenue/read").mock(
        return_value=httpx.Response(200, json={"company": "TY", "total_usdt": "32", "days": []})
    )
    out = await call(gw_egress(), "revenue.read", {"from": "2026-10-01", "to": "2026-10-21"})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "revenue:TY"), out
    assert json.loads(rev.calls.last.request.content) == {
        "from": "2026-10-01",
        "to": "2026-10-21",
        "by": "day",
    }
    fun = mock.post(f"{API}/internal/v1/growth/funnel/read").mock(
        return_value=httpx.Response(200, json={"company": "TY", "stages": []})
    )
    out = await call(gw_egress(), "funnel.read", {"company": "TY", "period": "month"})
    assert (
        out["outcome"] == "ok" and json.loads(fun.calls.last.request.content)["period"] == "month"
    )
    Stub(
        mock, gate(employee="TY-SALES-03", kind="employee", role="support_lead", department="SALES")
    )
    tag = mock.post(f"{API}/internal/v1/feedback/tag").mock(
        return_value=httpx.Response(200, json={"ref": "FB-000004", "count": 2, "created": False})
    )
    out = await call(gw_egress(), "feedback.tag", {"source_ref": "SC-000042", "kind": "bug", "area": "deposit",
                                                   "title_fa": "واریز دیر میرسد، ali@example.com"})  # fmt: skip
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "FB-000004"), out
    assert "ali@example.com" not in tag.calls.last.request.content.decode()
    assert {"revenue.read", "funnel.read", "rescue.update", "feedback.tag",
                                         "referral.check"} <= tool_status.GATEWAY_TOOLS  # fmt: skip


async def test_the_workers_connector_never_returns_the_secret(
    mock: respx.MockRouter, tmp_path: Path
) -> None:
    pulled: list[httpx.Request] = []
    logged: list[dict[str, Any]] = []
    sent: list[dict[str, Any]] = []

    def pull(request: httpx.Request) -> httpx.Response:
        pulled.append(request)
        return httpx.Response(200, json={"account": dict(ACCOUNT), "reservation": "0193e7a1-0000-7000-8000-0000000000bb",
                                         "max_bytes": 2000})  # fmt: skip

    def egress(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"outcome": "ok", "code": None,
                                         "data": {"rows": [{"coin": "usdt", "amount": "12"}], "page_rows": 1},
                                         "entries": [{**ENTRY, "tool": "revenue.pull"}]})  # fmt: skip

    def log(request: httpx.Request) -> httpx.Response:
        logged.append(json.loads(request.content))
        return httpx.Response(204)

    base = f"{API}/internal/v1/egress/connectors/lbank-affiliate-v2"
    mock.post(f"{base}/pull").mock(side_effect=pull)
    mock.post(f"{base}/log").mock(side_effect=log)
    mock.post(f"{EGRESS}/v1/connectors/call").mock(side_effect=egress)
    digest = tmp_path / "worker-token.sha256"
    digest.write_text(hashlib.sha256(WORKER.encode()).hexdigest())
    state = State(Settings(worker_token_file=str(digest)))
    state.load_digest()
    state.gateway = gw_egress()
    body = {"token": WORKER_API, "company": "TY", "exchange": "lbank", "adapter": "lbank-affiliate-v2",
            "endpoint": "commission/stats/symbol/list", "params": {"startTime": 1, "endTime": 2, "tradeType": 10},
            "local": {}}  # fmt: skip
    transport = httpx.ASGITransport(app=build_app(state))
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
        assert (await c.post("/v1/connectors/call", json=body)).status_code == 401
        assert (await c.post("/v1/connectors/call", headers={"Authorization": f"Bearer {TOKEN}"},
                             json=body)).status_code == 401  # an agent's token is not the worker's  # fmt: skip
        r = await c.post(
            "/v1/connectors/call", headers={"Authorization": f"Bearer {WORKER}"}, json=body
        )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out == {
        "outcome": "ok",
        "code": None,
        "data": {"rows": [{"coin": "usdt", "amount": "12"}], "page_rows": 1},
    }
    assert pulled[0].headers["authorization"] == f"Bearer {WORKER_API}"
    assert json.loads(pulled[0].content) == {"company": "TY", "exchange": "lbank",
                                             "endpoint": "commission/stats/symbol/list", "tool": "revenue.pull"}  # fmt: skip
    assert sent[0]["account"]["secret"] == SECRET and sent[0]["ctx"]["actor"] == "worker"
    assert logged[0]["reservation"] == "0193e7a1-0000-7000-8000-0000000000bb"
    assert logged[0]["entries"][0]["tool"] == "revenue.pull"
    for blob in (r.text, json.dumps(logged)):
        assert SECRET not in blob and "sk-" not in blob
    # A refusal of the api comes back as its code; egress is never called.
    mock.post(f"{base}/pull").mock(
        return_value=httpx.Response(423, json={"code": "company_locked"})
    )
    out = await RV.connector_call(state.gateway.api, RV.ConnectorCallIn(**body))
    assert (out["outcome"], out["code"]) == ("denied", "company_locked") and len(sent) == 1
