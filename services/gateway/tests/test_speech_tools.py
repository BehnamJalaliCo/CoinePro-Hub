"""⟨2026-11-06⟩ speech.make through the gateway (agents/tools.md): live, held by the five media roles
only, A1; `{text_fa, voice?, style?}` starts a voice (redacted text, an Idempotency-Key), `{job}`
asks for its answer; anything else never reaches the api; a refusal comes back in Persian."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from test_gateway import API, LIB, OPA, Stub, call, gate

from hq_common import tool_status
from hq_gateway import media as MT
from hq_gateway import tools as T
from hq_gateway.gateway import Gateway, Opa

PRODUCER = gate(employee="TY-MEDIA-04", kind="employee", role="voice_producer", department="MEDIA")
PUBLISHER = gate(employee="TY-MEDIA-06", kind="employee", role="publisher", department="MEDIA")
JOB = "0193e7a1-0000-7000-8000-0000000000aa"
ROLES = {"media_director", "voice_producer", "video_director", "motion_designer", "scriptwriter"}


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
def gw() -> Gateway:
    return Gateway(LIB, T.Api(API, 5), Opa(OPA), max_result_chars=4000, tool_timeout_s=2)


def test_speech_make_is_live_and_the_media_roles_hold_it() -> None:
    assert "speech.make" in MT.TOOLS and "speech.make" in tool_status.GATEWAY_TOOLS
    assert LIB.tools["speech.make"].cls == "A1"
    holders = {r for r, c in LIB.roles.items() if "speech.make" in c.tools}
    assert holders == ROLES


async def test_it_starts_a_voice_then_reads_its_answer(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, PRODUCER)
    seen: list[httpx.Request] = []

    def start(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            202, json={"job": JOB, "state": "running", "engine": "aistudio", "hint_fa": "صبر کن"}
        )

    mock.post(f"{API}/internal/v1/speech/make").mock(side_effect=start)
    out = await call(
        gw,
        "speech.make",
        {"text_fa": "تماس: ali.rezaei@example.com", "voice": "Puck", "style": "گرم"},
    )
    assert (out["outcome"], out["class"], out["ref"]) == ("ok", "A1", JOB), out
    assert out["hint_fa"] == "صبر کن"
    body: dict[str, Any] = json.loads(seen[0].content)
    assert body["voice"] == "Puck" and body["style"] == "گرم"
    assert "ali.rezaei@example.com" not in body["text_fa"]  # redacted before it leaves
    assert seen[0].headers.get("idempotency-key")
    fid = "11111111-2222-3333-4444-555555555555"
    mock.get(f"{API}/internal/v1/speech/make/{JOB}").mock(
        return_value=httpx.Response(
            200, json={"job": JOB, "state": "done", "engine": "aistudio", "file_id": fid}
        )
    )
    out = await call(gw, "speech.make", {"job": JOB})
    assert (out["outcome"], out["ref"]) == ("ok", fid) and out["result"]["state"] == "done", out


async def test_bad_input_and_other_roles_never_reach_the_api(
    mock: respx.MockRouter, gw: Gateway
) -> None:
    Stub(mock, PRODUCER)
    post = mock.post(f"{API}/internal/v1/speech/make")
    for bad in (
        {},
        {"text_fa": "x", "job": JOB},
        {"job": JOB, "voice": "Puck"},
        {"text_fa": "x", "voice": "Kore 2"},
        {"text_fa": ""},
        {"job": "not-a-uuid"},
        {"text_fa": "ا" * 5001},
    ):
        out = await call(gw, "speech.make", bad)
        assert out["code"] == "invalid_args", (bad, out)
    assert not post.called
    Stub(mock, PUBLISHER)
    out = await call(gw, "speech.make", {"text_fa": "متن"})
    assert out["outcome"] == "denied" and not post.called


async def test_signed_out_comes_back_in_persian(mock: respx.MockRouter, gw: Gateway) -> None:
    Stub(mock, PRODUCER)
    mock.post(f"{API}/internal/v1/speech/make").mock(
        return_value=httpx.Response(
            503,
            json={
                "code": "channel_not_configured",
                "message_fa": "مالک باید با make aistudio-web-login وارد شود.",
            },
        )
    )
    out = await call(gw, "speech.make", {"text_fa": "متن"})
    assert (out["outcome"], out["code"]) == ("error", "channel_not_configured"), out
    assert "make aistudio-web-login" in out["hint_fa"]
