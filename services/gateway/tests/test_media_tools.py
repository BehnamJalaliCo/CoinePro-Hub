"""Prompt 13 §2 (contract §22.2, agents/tools.md v1.6): the media studio's
tools through the gateway: each role holds only its own (media.review is
the media director's alone), text leaves redacted, a composition's source
leaves exactly as written (the api checks it against the schema)."""

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

MOTION = gate(employee="TY-MEDIA-03", kind="employee", role="motion_designer", department="MEDIA")
SCRIPT = gate(employee="TY-MEDIA-01", kind="employee", role="scriptwriter", department="MEDIA")
DIRECTOR = gate(employee="TY-MEDIA-MGR", kind="manager", role="media_director", department="MEDIA")
SOURCE = (
    '<html lang="fa" dir="rtl"><body><div style="color:#F2B705">ali@example.com</div>'
    "<script>anime({targets: 'div'})</script></body></html>"
)


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_the_media_tools_are_registered_and_media_review_is_the_directors_alone() -> None:
    for tool in ("media.item", "media.render", "media.voice", "media.review", "series.propose"):
        assert tool in T.TOOLS and tool in LIB.tools, tool
    holders = {r for r, c in LIB.roles.items() if "media.review" in c.tools}
    assert holders == {"media_director"}


async def test_a_composition_leaves_as_written_and_a_script_redacted(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, MOTION)
    seen: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers.get("idempotency-key")
        return httpx.Response(200, json={"ref": "MI-0001", "state": "rendering", "hint_fa": "ok"})

    mock.post(f"{API}/internal/v1/media/item").mock(side_effect=handle)
    body = {
        "ref": "MI-0001",
        "step": "composition",
        "composition": {"format": "html", "source": SOURCE},
    }
    out = await call(gw, "media.item", body)
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", "MI-0001"), out
    assert seen[0]["composition"]["source"] == SOURCE  # never rewritten here
    Stub(mock, SCRIPT)
    script = {"text_fa": "تماس: ali@example.com", "sources": []}
    out = await call(gw, "media.item", {"ref": "MI-0001", "step": "script", "script": script})
    assert out["outcome"] == "ok"
    assert "ali@example.com" not in seen[1]["script"]["text_fa"]
    bad = await call(gw, "media.item", {"ref": "X-1", "step": "script"})
    assert bad["code"] == "invalid_args"


async def test_a_role_without_the_tool_is_refused_before_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, MOTION)
    route = mock.post(f"{API}/internal/v1/media/review")
    out = await call(gw, "media.review", {"ref": "MI-0001", "verdict": "pass", "note_md": "x"})
    assert out["outcome"] == "denied" and not route.called
    Stub(mock, DIRECTOR)
    route.mock(return_value=httpx.Response(200, json={"ref": "MI-0001", "state": "scheduled"}))
    out = await call(gw, "media.review", {"ref": "MI-0001", "verdict": "pass", "note_md": "قبول"})
    assert (out["outcome"], out["class"]) == ("ok", "A2"), out


async def test_series_propose_and_render_reach_their_routes(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, DIRECTOR)
    keys: list[str | None] = []

    def series(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers.get("idempotency-key"))
        return httpx.Response(200, json={"ref": "SR-0001", "state": "proposed"})

    mock.post(f"{API}/internal/v1/media/series/propose").mock(side_effect=series)
    body = {
        "company": "TY",
        "title_fa": "سطح‌های هفته",
        "kind": "reel",
        "targets": [
            {"channel": "telegram", "account": "telegram-ty", "placement": "telegram_post"}
        ],
        "schedule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
        "format": {"aspect": "9:16", "duration_s": 30},
    }
    out = await call(gw, "series.propose", body)
    assert (out["outcome"], out["ref"]) == ("ok", "SR-0001") and keys[0]
    Stub(mock, MOTION)
    mock.post(f"{API}/internal/v1/media/render").mock(
        return_value=httpx.Response(200, json={"ref": "MI-0001", "detail": {"queued": True}})
    )
    out = await call(gw, "media.render", {"ref": "MI-0001"})
    assert (out["outcome"], out["class"]) == ("ok", "A2"), out
