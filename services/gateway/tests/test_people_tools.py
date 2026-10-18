"""The gateway's stars, lessons, stories and hire.decide tools (prompt 08 §4,
§8, §9): the paths, the redaction on the way out, the input checks."""

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


CEO = gate(employee="TY-CEO", kind="ceo", role="ceo", department=None, own_thread="TY-CEO")
OVR = gate(
    employee="HQ-OVR", company="HQ", kind="overseer", role="overseer", department="OVS",
    scope="holding", own_thread="N",
)  # fmt: skip


def _capture(mock: respx.MockRouter, path: str, answer: dict[str, Any]) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(
            {"body": json.loads(request.content), "idem": request.headers.get("idempotency-key")}
        )
        return httpx.Response(200, json=answer)

    mock.post(f"{API}{path}").mock(side_effect=handle)
    return seen


async def test_a_ceo_decides_a_hire_and_gives_stars(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    seen = _capture(
        mock,
        "/internal/v1/hires/D-000042/decide",
        {"ref": "D-000042", "status": "approved", "resolution": "M-0007", "payload": {"x": 1}},
    )
    out = await call(
        gw, "hire.decide", {"ref": "D-000042", "verdict": "approve", "note": "در پاکت"}
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A2", "D-000042"), out
    assert out["result"] == {"ref": "D-000042", "status": "approved", "resolution": "M-0007"}
    assert seen[0]["body"] == {"verdict": "approve", "note": "در پاکت"} and seen[0]["idem"]
    bad = await call(gw, "hire.decide", {"ref": "D-000042", "verdict": "maybe"})
    assert (bad["outcome"], bad["code"]) == ("error", "invalid_args")
    phone = "0912" + "345" + "6789"
    stars = _capture(
        mock,
        "/internal/v1/stars",
        {
            "id": "s1",
            "employee": "TY-TECH-MGR",
            "week": "2026-10-10",
            "stars": 4.5,
            "counted": True,
        },
    )
    out = await call(
        gw,
        "star.give",
        {
            "employee": "TY-TECH-MGR",
            "week": "2026-10-10",
            "stars": 4.5,
            "reason_md": f"پاسخ به مشتری {phone}",
            "evidence": [{"kind": "work", "ref": "W-000101"}],
        },
    )
    assert out["outcome"] == "ok" and out["ref"] == "star:s1"
    assert phone not in json.dumps(stars[0]["body"], ensure_ascii=False)  # redacted on the way out
    over = await call(
        gw, "star.give", {"employee": "TY-TECH-MGR", "week": "2026-10-10", "stars": 6}
    )
    assert over["code"] == "invalid_args"


async def test_stories_and_the_overseers_tools(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, CEO)
    _capture(mock, "/internal/v1/stories", {"ref": "ST-000009", "kind": "post", "title_fa": "x"})
    out = await call(gw, "story.post", {"kind": "post", "title_fa": "رکورد", "body_fa": "فروش"})
    assert out["outcome"] == "ok" and out["ref"] == "ST-000009" and out["class"] == "A1"
    long = await call(gw, "story.post", {"kind": "post", "title_fa": "ب" * 61})
    assert long["code"] == "invalid_args"  # 60 characters at most
    denied = await call(
        gw,
        "star.audit",
        {"star_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12, "counted": False, "note": "x"},
    )
    assert (denied["outcome"], denied["code"]) == ("denied", "tool_not_in_charter")


async def test_the_overseer_audits_and_writes_lessons(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, OVR)
    star = "0193e7a1-0000-7000-8000-00000000abcd"
    _capture(mock, f"/internal/v1/stars/{star}/audit", {"id": star, "counted": False})
    out = await call(gw, "star.audit", {"star_id": star, "counted": False, "note": "بی‌شاهد"})
    assert out["outcome"] == "ok" and out["ref"] == f"star:{star}"
    _capture(mock, "/internal/v1/lessons", {"ref": "L-0003"})
    out = await call(
        gw,
        "lesson.write",
        {"source_company": "TY", "period": "week:2026-10-10", "title_fa": "درس", "body_md": "متن"},
    )
    assert out["outcome"] == "ok" and out["ref"] == "L-0003"
    assert set(T.TOOLS) >= {
        "star.rubric",
        "star.give",
        "star.audit",
        "lesson.write",
        "story.post",
        "hire.decide",
    }
