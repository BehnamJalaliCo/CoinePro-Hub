"""⟨2026-11-06⟩ linked.read through the gateway (agents/tools.md, contract §35.6): registered and
live, held by every role but a system one, reaching its api route with the run's token and the
exact query, `ref` only with `outputs`, the api's refusal (no link) passed on in Persian, and the
answer redacted again."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, TOKEN, Stub, call, gate

from hq_common import tool_status
from hq_common.charters import SHARED_TOOLS
from hq_gateway import linked as LT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

WRITER = gate(employee="TY-MEDIA-01", kind="employee", role="scriptwriter", department="MEDIA")
SECRET = "sk-ant-api03-" + "Q" * 40


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_linked_read_is_live_and_every_working_role_holds_it() -> None:
    assert set(LT.TOOLS) == {"linked.read"} and "linked.read" in T.TOOLS
    assert "linked.read" in tool_status.GATEWAY_TOOLS and "linked.read" in SHARED_TOOLS
    assert LIB.tools["linked.read"].cls == "A0"
    for role, charter in LIB.roles.items():
        held = "linked.read" in charter.tools
        assert held == (charter.kind != "system"), role


async def test_it_asks_the_api_with_the_runs_token_and_the_answer_is_redacted(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, WRITER)
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {
            "company": "FX",
            "name_fa": "کوینه‌پرو اف‌ایکس",
            "what": "outputs",
            "via": "link",
            "output": {"ref": "O-000042", "title": "گزارش", "summary": "خلاصه",
                       "producer": "مدیرعامل", "at": "2026-11-06T08:00:00Z",
                       "body": f"کلید {SECRET} نباید برسد", "truncated": False},
        }  # fmt: skip
        return httpx.Response(200, json=body)

    mock.get(f"{API}/internal/v1/linked/read").mock(side_effect=answer)
    out = await call(gw, "linked.read", {"company": "FX", "what": "outputs", "ref": "O-000042"})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A0", "FX:outputs:O-000042"), out
    sent = seen[0]
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    assert dict(sent.url.params) == {"company": "FX", "what": "outputs", "ref": "O-000042"}
    assert SECRET not in str(out["result"]) and out["result"]["via"] == "link"
    out = await call(gw, "linked.read", {"company": "FX", "what": "kpis"})
    assert out["outcome"] == "ok" and dict(seen[1].url.params) == {"company": "FX", "what": "kpis"}
    out = await call(gw, "linked.read", {"company": "IG", "what": "profile"})
    assert out["outcome"] == "ok" and out["ref"] == "IG:profile"
    assert dict(seen[2].url.params) == {"company": "IG", "what": "profile"}


async def test_bad_input_never_reaches_the_api_and_a_refusal_comes_back_plain(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, WRITER)
    route = mock.get(f"{API}/internal/v1/linked/read")
    for bad in (
        {"company": "FX", "what": "secrets"},
        {"company": "fx", "what": "kpis"},
        {"what": "kpis"},
        {"company": "FX", "what": "outputs", "ref": "W-000001"},
        {"company": "FX", "what": "kpis", "extra": 1},
    ):
        out = await call(gw, "linked.read", bad)
        assert out["code"] == "invalid_args", (bad, out)
    out = await call(gw, "linked.read", {"company": "FX", "what": "kpis", "ref": "O-000001"})
    assert out["code"] == "invalid_args" and "outputs" in out["hint_fa"]
    assert not route.called
    route.mock(
        return_value=httpx.Response(
            403,
            json={"code": "policy_denied", "message_fa": "این دو شرکت به هم وصل نیستند."},
        )
    )
    out = await call(gw, "linked.read", {"company": "GX", "what": "kpis"})
    assert (out["outcome"], out["code"]) == ("denied", "policy_denied"), out
    assert out["hint_fa"] == "این دو شرکت به هم وصل نیستند."
