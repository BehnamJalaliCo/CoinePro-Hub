"""H2 (2026-11-08): `connection.set` through the gateway: registered and live, held by the CEO, the
CTO, the media director and the DevOps engineer; it reaches its api route with the run's token and
the exact body (a command as written, a title redacted), refuses bad input before the api, and
passes the api's refusal (a secret, a command that is not read-only) on in Persian."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, TOKEN, Stub, call, gate

from hq_common import tool_status
from hq_gateway import connections as CT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

CTO = gate()  # TY-TECH-MGR, cto, TECH
LEAD = gate(employee="TY-MEDIA-MGR", kind="manager", role="media_director", department="MEDIA")
WRITER = gate(employee="TY-MEDIA-01", kind="employee", role="scriptwriter", department="MEDIA")


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_connection_set_is_live_and_held_by_the_right_roles() -> None:
    assert set(CT.TOOLS) == {"connection.set"} and "connection.set" in T.TOOLS
    assert "connection.set" in tool_status.GATEWAY_TOOLS and LIB.tools["connection.set"].cls == "A2"
    holders = {r for r, c in LIB.roles.items() if "connection.set" in c.tools}
    assert holders == {"ceo", "cto", "media_director", "devops_engineer"}, holders


async def test_it_reaches_the_api_with_the_body_as_given(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, CTO)
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"company": "PC", "kind": "instagram", "state": "connected",
                                         "config": {"accounts": ["pro.chart"]}, "secret": "missing",
                                         "last_read_at": None, "last_error_fa": None, "daily": []})  # fmt: skip

    mock.post(f"{API}/internal/v1/connections/set").mock(side_effect=answer)
    cmd = "cat /srv/ig/daily.json"
    out = await call(gw, "connection.set", {
        "company": "PC", "kind": "instagram", "accounts": ["@pro.chart", "pro_chart2"],
        "via": "ig_hub", "server": {"company": "IG", "name": "IG-Hub"}, "read_command": cmd,
    })  # fmt: skip
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "PC:instagram"), out
    sent = json.loads(seen[0].content)
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert sent == {"company": "PC", "kind": "instagram", "accounts": ["@pro.chart", "pro_chart2"],
                    "via": "ig_hub", "server": {"company": "IG", "name": "IG-Hub"},
                    "read_command": cmd}  # fmt: skip
    # a title is prose and leaves redacted; a command is code and leaves as written
    out = await call(gw, "connection.set", {
        "kind": "telegram", "channels": [{"chat": "@coinepro", "title_fa": "کانال ali@example.com"}],
    })  # fmt: skip
    assert out["outcome"] == "ok"
    sent = json.loads(seen[1].content)
    assert "ali@example.com" not in sent["channels"][0]["title_fa"]


async def test_bad_input_never_reaches_the_api_and_refusals_come_back_plain(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, LEAD)
    route = mock.post(f"{API}/internal/v1/connections/set")
    for bad in (
        {"kind": "myspace", "accounts": ["x"]},
        {"kind": "instagram"},  # nothing to set
        {"kind": "instagram", "accounts": ["bad account!"]},
        {"kind": "instagram", "via": "direct"},
        {"kind": "telegram", "channels": [{"chat": "coinepro"}]},
        {"kind": "instagram", "accounts": ["@x"], "token": "abc"},
        {"kind": "search_console", "site_url": "ftp://x"},
    ):
        out = await call(gw, "connection.set", bad)
        assert out["code"] == "invalid_args", (bad, out)
    assert not route.called
    route.mock(return_value=httpx.Response(422, json={
        "code": "validation_failed", "fields": {"read_command": "a read-only command"},
        "message_fa": "این دستور فقط‌خواندنی نیست.",
    }))  # fmt: skip
    out = await call(gw, "connection.set", {"kind": "instagram", "read_command": "rm -rf /srv"})
    assert (out["outcome"], out["code"]) == ("error", "validation_failed"), out
    assert out["hint_fa"] == "این دستور فقط‌خواندنی نیست."
    # a role without the tool: refused before the api
    Stub(mock, WRITER)
    out = await call(gw, "connection.set", {"kind": "instagram", "accounts": ["@x"]})
    assert out["outcome"] == "denied"
