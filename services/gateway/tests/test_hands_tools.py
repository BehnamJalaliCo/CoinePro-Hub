"""⟨2026-11-09⟩ The workshop (contract §43): `workshop.run`, hands for any task, held by every
working role; the gateway hands the brief (redacted) to the api and answers at once."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_common.charters import SHARED_TOOLS
from hq_gateway import hands as H
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

WRITER = gate(
    employee="PC-MED-02", company="PC", kind="employee", role="scriptwriter", department="MED",
    work_ref="W-000501",
)  # fmt: skip


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_every_working_role_holds_the_workshop() -> None:
    assert set(H.TOOLS) == {"workshop.run", "workshop.stop"}
    assert set(H.TOOLS) <= set(T.TOOLS) and set(H.TOOLS) <= tool_status.GATEWAY_TOOLS
    assert {"workshop.run", "workshop.stop"} <= set(SHARED_TOOLS)
    assert LIB.tools["workshop.run"].cls == "A2"
    # ⟨2026-11-10⟩ whoever may start a turn may stop its own, with no grant of its own (A1)
    assert LIB.tools["workshop.stop"].cls == "A1"
    for role, charter in LIB.roles.items():
        for tool in ("workshop.run", "workshop.stop"):
            assert (tool in charter.tools) == (charter.kind != "system"), (role, tool)


async def test_the_brief_goes_redacted_and_the_run_is_told_to_finish(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    stub = Stub(mock, WRITER)
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "job": "0193e7a1-0000-7000-8000-0000000000aa",
                "work_ref": "W-000501",
                "state": "starting",
                "turn": 1,
                "path": "~/hq-workspace/W-000501",
                "server": "workshop",
            },
        )

    mock.post(f"{API}/internal/v1/workshop/runs").mock(side_effect=answer)
    out = await call(
        gw,
        "workshop.run",
        {"brief": "موشن‌گرافی ATR؛ تماس: ali@example.com", "title": "ATR"},
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "W-000501"), out
    assert out["result"] == {
        "job": "0193e7a1-0000-7000-8000-0000000000aa",
        "work_ref": "W-000501",
        "state": "starting",
        "turn": 1,
        "path": "~/hq-workspace/W-000501",
    }
    assert out["hint_fa"] == H.DONE_FA[: T.HINT_CHARS]
    [req] = seen
    body: dict[str, Any] = json.loads(req.content)
    assert "ali@example.com" not in body["brief"] and "work" not in body
    assert req.headers.get("authorization") and req.headers.get("idempotency-key")
    # the gateway's class check: an A2 action of the role, own company
    [opa] = stub.opa_inputs
    assert opa["action"] == {"class": "A2", "name": "workshop.run", "company": "PC"}


async def test_a_busy_workshop_is_not_an_error(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, WRITER)
    mock.post(f"{API}/internal/v1/workshop/runs").mock(
        return_value=httpx.Response(
            200,
            json={
                "job": "0193e7a1-0000-7000-8000-0000000000ab",
                "work_ref": "W-000501",
                "state": "working",
                "turn": 2,
            },
        )
    )
    out = await call(gw, "workshop.run", {"brief": "اصلاح: رنگ‌ها تیره‌تر", "work": "W-000501"})
    assert out["outcome"] == "ok" and out["result"]["state"] == "working"
    assert out["hint_fa"] == H.BUSY_FA[: T.HINT_CHARS]


async def test_an_absent_workshop_passes_its_reason(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, WRITER)
    mock.post(f"{API}/internal/v1/workshop/runs").mock(
        return_value=httpx.Response(
            409,
            json={"code": "workshop_unavailable", "message_fa": "کارگاه هنوز روشن نیست."},
        )
    )
    out = await call(gw, "workshop.run", {"brief": "یک گزارش PDF"})
    assert out["outcome"] != "ok" and out["code"] == "workshop_unavailable", out


async def test_a_bad_work_ref_never_reaches_the_api(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, WRITER)
    route = mock.post(f"{API}/internal/v1/workshop/runs")
    out = await call(gw, "workshop.run", {"brief": "x", "work": "../etc"})
    assert out["outcome"] == "error" and out["code"] == "invalid_args"
    assert not route.called


async def test_a_step_order_names_the_plan_task_and_the_holder_can_stop_its_turn(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    """⟨2026-11-10⟩ «با من»: the turn carries the plan task it is for (the api refuses any but
    the next one), and the holder stops a turn it started (the owner's recording: «نمیتوانم
    بگویم آن سفارش متوقف شده است، چون این کار در دست من نیست»)."""
    Stub(mock, WRITER)
    seen: list[dict[str, Any]] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            409,
            json={
                "code": "not_next_step",
                "fields": {"task": "the plan's next open task is 2: متن گفتار"},
                "message_fa": "فقط کار بعدی برنامه شروع میشود.",
            },
        )

    mock.post(f"{API}/internal/v1/workshop/runs").mock(side_effect=refuse)
    out = await call(gw, "workshop.run", {"brief": "ریلز را بساز", "task": 4})
    assert seen == [{"brief": "ریلز را بساز", "task": 4}]
    assert out["outcome"] != "ok" and out["code"] == "not_next_step", out
    assert "2" in out["fields"]["task"]

    stop = mock.post(f"{API}/internal/v1/workshop/stop").mock(
        return_value=httpx.Response(
            200,
            json={
                "work_ref": "W-000501",
                "stopped": True,
                "job": "0193e7a1-0000-7000-8000-0000000000aa",
            },
        )
    )
    out = await call(gw, "workshop.stop", {"reason": "مالک گفت اشتباه بود"})
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "W-000501"), out
    assert out["result"]["stopped"] is True and out["hint_fa"] == H.STOPPED_FA[: T.HINT_CHARS]
    assert json.loads(stop.calls.last.request.content) == {"reason": "مالک گفت اشتباه بود"}


async def test_the_ledger_tools_and_the_effort_of_a_turn(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    """⟨1.31⟩ contract §47, §48, §53: `topic.claim` and `narrator.set` are every working role's
    (A1); a taken topic comes back as its own code with the hint to choose another; a turn's
    `effort` goes to the api only when it is given."""
    from hq_gateway import ledger as L

    assert set(L.TOOLS) == {"topic.claim", "narrator.set"} <= set(T.TOOLS)
    assert set(L.TOOLS) <= tool_status.GATEWAY_TOOLS and set(L.TOOLS) <= set(SHARED_TOOLS)
    assert LIB.tools["topic.claim"].cls == "A1" and LIB.tools["narrator.set"].cls == "A1"
    for role, charter in LIB.roles.items():
        assert ("topic.claim" in charter.tools) == (charter.kind != "system"), role
    Stub(mock, WRITER)
    seen: list[Any] = []

    def claimed(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={
                "entry": {"id": "0193e7a1-0000-7000-8000-0000000000bb", "kind": "topic",
                          "title_fa": "اندیکاتور ATR", "url": None, "by": "PC-MED-02"},
                "new": True,
                "group": "pb_1",
            },
        )  # fmt: skip

    route = mock.post(f"{API}/internal/v1/topics/claim").mock(side_effect=claimed)
    out = await call(gw, "topic.claim", {"title_fa": "اندیکاتور ATR"})
    assert (out["outcome"], out["class"]) == ("ok", "A1"), out
    assert seen == [{"kind": "topic", "title_fa": "اندیکاتور ATR"}]
    assert out["result"] == {"kind": "topic", "title_fa": "اندیکاتور ATR", "url": None,
                             "new": True, "group": "pb_1"}  # fmt: skip
    assert out["hint_fa"] == L.CLAIMED_FA[: T.HINT_CHARS]
    route.mock(
        return_value=httpx.Response(
            409,
            json={"type": "urn:coinepro-hq:problem:topic_taken", "title": "Topic already said",
                  "status": 409, "code": "topic_taken", "message_fa": "این پیش‌تر گفته شده",
                  "fields": {"title_fa": "taken: «اندیکاتور ATR» (2026-11-09)", "recent": "الف؛ ب"}},
        )
    )  # fmt: skip
    out = await call(gw, "topic.claim", {"title_fa": "معرفی اندیکاتور ATR"})
    assert out["outcome"] != "ok" and out["code"] == "topic_taken", out
    assert out["hint_fa"] == L.TAKEN_FA[: T.HINT_CHARS] and "recent" in out["fields"]

    narrator = mock.post(f"{API}/internal/v1/narrator").mock(
        return_value=httpx.Response(
            200, json={"company": "PC", "set": True, "voice": "Charon", "style_fa": "آرام"}
        )
    )
    out = await call(gw, "narrator.set", {"voice": "Charon", "style_fa": "آرام"})
    assert (out["outcome"], out["ref"]) == ("ok", "PC"), out
    assert json.loads(narrator.calls.last.request.content) == {
        "voice": "Charon",
        "style_fa": "آرام",
    }
    assert out["result"] == {"company": "PC", "voice": "Charon", "style_fa": "آرام"}

    started = {
        "job": "0193e7a1-0000-7000-8000-0000000000aa",
        "work_ref": "W-000501",
        "state": "starting",
        "turn": 1,
        "path": "~/hq-workspace/W-000501",
        "server": "workshop",
    }
    runs = mock.post(f"{API}/internal/v1/workshop/runs").mock(
        return_value=httpx.Response(201, json=started)
    )
    await call(gw, "workshop.run", {"brief": "رنگ را آبی کن", "effort": "medium"})
    assert json.loads(runs.calls.last.request.content) == {
        "brief": "رنگ را آبی کن",
        "effort": "medium",
    }
    await call(gw, "workshop.run", {"brief": "موشن را بساز"})
    assert json.loads(runs.calls.last.request.content) == {"brief": "موشن را بساز"}
    bad = await call(gw, "workshop.run", {"brief": "x", "effort": "ultra"})
    assert bad["outcome"] != "ok", bad
