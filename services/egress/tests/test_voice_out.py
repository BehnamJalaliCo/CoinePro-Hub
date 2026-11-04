"""POST /v1/voice/gemini (prompt 23, contract §32.5): the `gemini-tts` channel against a fake
Gemini (no real call: the fetcher's client is a mock transport; the guard still checks every
name and address). The key goes in a header only and never comes back; Google's refusals become
stable codes; the answer is reduced to the speech and the provider's own token counts."""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_egress import voice_out as V
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.net import Fetcher
from hq_egress.proxy import Buckets

LOCAL = ipaddress.ip_network("127.0.0.1/32")
KEY = "AIza" + "K" * 35  # a Google API key's shape (fake)
MODEL = "gemini-3.8-flash-tts"
PCM = b"\x01\x02" * 24_000  # one second at 24 kHz, 16-bit mono
HUB = "hq.coinepro.com"


def google_error(status: int, name: str, message: str, reason: str | None = None) -> httpx.Response:
    err: dict[str, Any] = {"code": status, "message": message, "status": name}
    if reason:
        err["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]
    return httpx.Response(status, json={"error": err})


class Fakes:
    """Gemini by model: the good ones answer; a model named after a failure answers that failure
    (and echoes the key in its message, which must never come back)."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        assert request.url.host == V.HOST and request.url.scheme == "https"
        assert request.headers["x-goog-api-key"] == KEY
        assert KEY not in str(request.url)
        model = request.url.path.split("/models/")[1].split(":")[0]
        fail = {
            "gemini-bad-key": google_error(
                400, "INVALID_ARGUMENT", f"API key not valid ({KEY}).", "API_KEY_INVALID"
            ),
            "gemini-expired": google_error(400, "INVALID_ARGUMENT", "API key expired."),
            "gemini-unauth": google_error(401, "UNAUTHENTICATED", "no"),
            "gemini-denied": google_error(403, "PERMISSION_DENIED", "model access denied"),
            "gemini-gone": google_error(404, "NOT_FOUND", "model is not found"),
            "gemini-nobill": google_error(
                429, "RESOURCE_EXHAUSTED", "Quota exceeded ... limit: 0, model: x"
            ),
            "gemini-billing": google_error(
                400, "FAILED_PRECONDITION", "Please enable billing on your project"
            ),
            "gemini-quota": google_error(429, "RESOURCE_EXHAUSTED", "You exceeded your quota"),
            "gemini-malformed": google_error(400, "INVALID_ARGUMENT", "bad voice config"),
            "gemini-boom": httpx.Response(503, text="<html>down</html>"),
            "gemini-noaudio": httpx.Response(200, json={"candidates": [{"finishReason": "OTHER"}]}),
        }.get(model)
        if fail is not None:
            return fail
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "name": f"models/{model}",
                    "displayName": "TTS",
                    "inputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent"],
                },
            )
        doc = json.loads(request.content)
        assert doc["generationConfig"]["responseModalities"] == ["AUDIO"]
        voice = doc["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]
        assert voice["voiceName"] == "Kore"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": base64.b64encode(PCM).decode(),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 7,
                    "candidatesTokenCount": 25,
                    "totalTokenCount": 32,
                    "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 7}],
                    "candidatesTokensDetails": [{"modality": "AUDIO", "tokenCount": 25}],
                },
                "modelVersion": "secret-internal-name",
            },
        )


@pytest.fixture
async def egress() -> AsyncIterator[tuple[httpx.AsyncClient, Fakes]]:
    table = {V.HOST: ["142.250.0.95"]}

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such name")
        return table[host]

    guard = Guard(hub_hosts=frozenset({HUB}), resolver=resolve)
    fakes = Fakes()
    fetcher = Fetcher(guard, 5)
    await fetcher.http.aclose()
    fetcher.http = httpx.AsyncClient(transport=httpx.MockTransport(fakes), follow_redirects=False)
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({HUB}))
    state = State(settings, guard, Buckets(), fetcher=fetcher)
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, fakes
    await fetcher.aclose()


def call(op: str = "speak", model: str = MODEL, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"channel": "gemini-tts", "op": op, "model": model, "key": KEY}
    if op == "speak":
        body |= {"voice": "Kore", "text": "سلام"}
    return body | over


async def post(c: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    r = await c.post("/v1/voice/gemini", json=body)
    assert r.status_code == 200, r.text
    assert KEY not in r.text
    out: dict[str, Any] = r.json()
    return out


async def test_the_metadata_call_is_free_and_proves_the_model(
    egress: tuple[httpx.AsyncClient, Fakes],
) -> None:
    c, fakes = egress
    out = await post(c, call("models_get"))
    assert out["outcome"] == "ok" and out["code"] is None
    assert out["data"] == {"model": f"models/{MODEL}", "methods": ["generateContent"]}
    (seen,) = fakes.seen
    assert seen.method == "GET" and seen.url.path == f"/v1beta/models/{MODEL}"
    assert [e["host"] for e in out["entries"]] == [V.HOST]
    assert out["entries"][0]["status"] == 200


async def test_speech_is_reduced_to_the_audio_and_the_providers_own_counts(
    egress: tuple[httpx.AsyncClient, Fakes],
) -> None:
    c, fakes = egress
    out = await post(c, call())
    assert out["outcome"] == "ok"
    data = out["data"]
    assert set(data) == {"audio_b64", "mime", "usage"}  # nothing else of Google's answer goes on
    assert base64.b64decode(data["audio_b64"]) == PCM
    assert data["mime"].startswith("audio/L16")
    assert data["usage"] == {"text_tokens": 7, "audio_tokens": 25, "total_tokens": 32}
    (seen,) = fakes.seen
    assert seen.method == "POST" and seen.url.path.endswith(f"/models/{MODEL}:generateContent")
    assert KEY not in seen.content.decode()  # the key is a header only


@pytest.mark.parametrize(
    ("model", "code"),
    [
        ("gemini-bad-key", "bad_key"),
        ("gemini-expired", "bad_key"),
        ("gemini-unauth", "bad_key"),
        ("gemini-denied", "no_model_access"),
        ("gemini-gone", "no_model_access"),
        ("gemini-nobill", "billing_off"),
        ("gemini-billing", "billing_off"),
        ("gemini-quota", "quota"),
        ("gemini-malformed", "bad_request"),
        ("gemini-boom", "upstream_error"),
        ("gemini-noaudio", "no_audio"),
    ],
)
async def test_googles_refusals_become_stable_codes_and_never_echo_the_key(
    egress: tuple[httpx.AsyncClient, Fakes], model: str, code: str
) -> None:
    c, _ = egress
    out = await post(c, call(model=model))
    assert out["outcome"] == "error" and out["code"] == code
    assert out["data"] is None  # Google's own text is never passed on
    assert out["entries"][0]["status"] in (200, 400, 401, 403, 404, 429, 503)


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"op": "delete"}, "op_not_allowed"),
        ({"key": "short"}, "bad_token"),
        ({"key": "has space " + "x" * 30}, "bad_token"),
        ({"model": "gpt-4"}, "bad_model"),
        ({"model": "gemini-x/../../v1/files"}, "bad_model"),
        ({"voice": "../Kore"}, "bad_voice"),
        ({"voice": None}, "bad_voice"),
        ({"text": "  "}, "bad_text"),
        ({"text": "x" * (V.TEXT_MAX + 1)}, "bad_text"),
    ],
)
async def test_anything_outside_the_allow_lists_is_blocked_before_it_leaves(
    egress: tuple[httpx.AsyncClient, Fakes], over: dict[str, Any], code: str
) -> None:
    c, fakes = egress
    out = await post(c, call(**over))
    assert out["outcome"] == "blocked" and out["code"] == code
    assert fakes.seen == []  # nothing left


async def test_a_metadata_call_takes_no_voice_or_text(
    egress: tuple[httpx.AsyncClient, Fakes],
) -> None:
    c, fakes = egress
    out = await post(c, call("models_get", voice="Kore"))
    assert out["outcome"] == "blocked" and out["code"] == "op_not_allowed"
    assert fakes.seen == []


async def test_the_channel_name_and_extra_fields_are_closed(
    egress: tuple[httpx.AsyncClient, Fakes],
) -> None:
    c, fakes = egress
    for body in (call() | {"channel": "other"}, call() | {"url": "https://evil.example/"}):
        r = await c.post("/v1/voice/gemini", json=body)
        assert r.status_code == 422
    assert fakes.seen == []


async def test_only_the_one_host_can_be_reached(egress: tuple[httpx.AsyncClient, Fakes]) -> None:
    c, fakes = egress
    await post(c, call())
    await post(c, call("models_get"))
    assert {r.url.host for r in fakes.seen} == {"generativelanguage.googleapis.com"}


async def test_the_key_is_in_no_log_line(
    egress: tuple[httpx.AsyncClient, Fakes], caplog: pytest.LogCaptureFixture
) -> None:
    c, _ = egress
    with caplog.at_level(logging.DEBUG):
        await post(c, call(model="gemini-bad-key"))
        await post(c, call())
    assert KEY not in caplog.text


def test_the_counts_fall_back_to_the_candidates_total() -> None:
    assert V._counts(
        {"promptTokenCount": 4, "candidatesTokenCount": 50, "totalTokenCount": 54}
    ) == {
        "text_tokens": 4,
        "audio_tokens": 50,
        "total_tokens": 54,
    }
    assert V._counts(None) == {"text_tokens": 0, "audio_tokens": 0, "total_tokens": 0}


def test_classify_reads_google_without_passing_its_text_on() -> None:
    assert V.classify(500, None) == "upstream_error"
    assert V.classify(
        400, {"error": {"status": "INVALID_ARGUMENT", "message": "key not valid"}}
    ) == ("bad_key")
    assert V.classify(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "free tier"}}) == (
        "billing_off"
    )
