"""Prompt 17 (contract §26.2, agents/tools.md v1.8): the company servers'
tools through the gateway: the charters hold them as §26.2 says, a call
becomes a job on the api, another company's server only for the holding's
platform SRE and the overseer or through an accepted cross-company request,
a destructive command answers awaiting_seal with its card."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_gateway import servers as S
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CTO = gate()
SRE_HQ = gate(employee="HQ-AIOPS-01", company="HQ", kind="employee", role="hub_platform_sre",
              department="AIOPS", scope="holding")  # fmt: skip
ANALYST = gate(employee="TY-FIN-01", kind="employee", role="revenue_analyst", department="FIN")
SUPPORT = gate(employee="TY-SALES-01", kind="employee", role="support_agent", department="SALES")
JOB = "0193e7a1-0000-7000-8000-0000000000aa"
ALL = ("server.map", "server.read", "server.exec", "server.write", "server.claude")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=8000, tool_timeout_s=25)


def job(state: str = "done", **over: Any) -> dict[str, Any]:
    return {
        "job": {"id": JOB, "kind": "exec", "state": state, "exit_code": 0 if state == "done" else None,
                "decision_ref": None, **over},
        "output": {"stdout": "ok\n", "stderr": ""},
        "map": None,
        "hint_fa": None,
    }  # fmt: skip


def test_the_tools_and_the_charters_of_section_26_2() -> None:
    for tool in ALL:
        assert tool in T.TOOLS and tool in LIB.tools, tool
    assert {t: LIB.tools[t].cls for t in ALL} == {
        "server.map": "A0", "server.read": "A0", "server.exec": "A2", "server.write": "A2",
        "server.claude": "A2",
    }  # fmt: skip
    for role in ("ceo", "cto", "sre", "hub_platform_sre", "overseer"):
        assert set(ALL) <= set(LIB.allowed(role)), role
    for role in ("revenue_analyst", "media_director", "scriptwriter", "ui_designer"):
        have = {t for t in ALL if t in LIB.allowed(role)}
        assert have == {"server.map", "server.read", "server.exec"}, role
    for role in ("support_agent", "advisor", "assistant", "librarian", "secretary"):
        assert not set(ALL) & set(LIB.allowed(role)), role


async def test_a_call_is_a_job_and_waits_for_it(mock: respx.MockRouter, gw: Gateway) -> None:
    s = Stub(mock, CTO)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(201, json=job())

    mock.post(f"{API}/internal/v1/servers/jobs").mock(side_effect=handle)
    out = await call(gw, "server.exec", {"server": "web-1", "cmd": "docker ps", "timeout_s": 30})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", f"job:{JOB}"), out
    assert seen[0] == {"kind": "exec", "server": "web-1", "args": {"cmd": "docker ps", "timeout_s": 30,
                       "sudo": False}, "wait_s": S.WAIT_S}  # fmt: skip
    assert out["result"]["output"]["stdout"] == "ok\n"
    assert s.records[-1]["tool"] == "server.exec"
    # A job still running: read it again with {job}.
    mock.get(f"{API}/internal/v1/servers/jobs/{JOB}").mock(
        return_value=httpx.Response(200, json=job("running"))
    )
    again = await call(gw, "server.exec", {"job": JOB})
    assert again["outcome"] == "ok" and again["result"]["job"]["state"] == "running"
    bad = await call(gw, "server.exec", {"server": "web-1"})
    assert bad["code"] == "invalid_args"


async def test_a_destructive_command_waits_for_the_seal(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CTO)
    mock.post(f"{API}/internal/v1/servers/jobs").mock(
        return_value=httpx.Response(
            201, json={**job("awaiting_seal", decision_ref="D-000042"), "hint_fa": "منتظر مُهر"}
        )
    )
    out = await call(gw, "server.exec", {"server": "web-1", "cmd": "dropdb prod"})
    assert (out["outcome"], out["code"], out["ref"]) == ("denied", "awaiting_seal", "D-000042"), out
    assert out["hint_fa"] == "منتظر مُهر"


async def test_another_companys_server(mock: respx.MockRouter, gw: Gateway) -> None:
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json=job())

    route = mock.post(f"{API}/internal/v1/servers/jobs").mock(side_effect=handle)
    # A company agent without a work item to cite: refused before the api.
    Stub(mock, gate(work_ref=None))
    out = await call(gw, "server.read", {"server": "ig", "company": "FX", "path": "/etc/hosts"})
    assert (out["outcome"], out["code"]) == ("denied", "other_company") and not route.called
    # With its work item (the cross-company request it made): the api checks the CEO's acceptance.
    Stub(mock, CTO)
    out = await call(gw, "server.read", {"server": "ig", "company": "FX", "path": "/etc/hosts"})
    assert (
        out["outcome"] == "ok"
        and seen[-1]["via_work"] == "W-000101"
        and seen[-1]["company"] == "FX"
    )
    # The api refuses one no CEO accepted.
    mock.post(f"{API}/internal/v1/servers/jobs").mock(
        return_value=httpx.Response(403, json={"code": "policy_denied", "message_fa": "نه"})
    )
    out = await call(gw, "server.read", {"server": "ig", "company": "FX", "path": "/etc/hosts"})
    assert (out["outcome"], out["code"]) == ("denied", "policy_denied")
    # The holding's platform SRE: every server, no request needed.
    mock.post(f"{API}/internal/v1/servers/jobs").mock(side_effect=handle)
    Stub(mock, {**SRE_HQ, "work_ref": None})
    out = await call(gw, "server.exec", {"server": "ig", "company": "FX", "cmd": "uptime"})
    assert out["outcome"] == "ok" and "via_work" not in seen[-1]


async def test_the_charter_decides(mock: respx.MockRouter, gw: Gateway) -> None:
    route = mock.post(f"{API}/internal/v1/servers/jobs").mock(
        return_value=httpx.Response(201, json=job())
    )
    Stub(mock, SUPPORT)
    out = await call(gw, "server.map", {"server": "web-1"})
    assert out["code"] == "tool_not_in_charter" and not route.called
    Stub(mock, ANALYST)
    out = await call(gw, "server.write", {"server": "web-1", "path": "/tmp/x", "content": "x"})
    assert out["code"] == "tool_not_in_charter"
    out = await call(gw, "server.exec", {"server": "web-1", "cmd": "tail -n 50 /var/log/app.log"})
    assert out["outcome"] == "ok"


async def test_map_without_a_server_lists_them(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CTO)
    mock.get(f"{API}/internal/v1/servers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "s1",
                    "company": "TY",
                    "name": "web-1",
                    "state": "online",
                    "via": "private",
                    "map_at": None,
                    "hostname": "web-1",
                    "private_ip": "10.10.1.3",
                }
            ],
        )
    )
    out = await call(gw, "server.map", {})
    assert out["outcome"] == "ok" and out["result"]["servers"][0]["name"] == "web-1"


async def test_a_brief_leaves_redacted_a_command_as_written(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CTO)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json=job("running"))

    mock.post(f"{API}/internal/v1/servers/jobs").mock(side_effect=handle)
    await call(
        gw, "server.claude", {"server": "web-1", "brief": "ایمیل ali@example.com را درست کن"}
    )
    assert "ali@example.com" not in seen[0]["args"]["brief"] and seen[0]["kind"] == "claude"
    await call(gw, "server.exec", {"server": "web-1", "cmd": "grep -r ali@example.com /srv/app"})
    assert seen[1]["args"]["cmd"] == "grep -r ali@example.com /srv/app"
