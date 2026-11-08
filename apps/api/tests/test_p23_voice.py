"""Prompt 23 (contract §32.5-§32.6): the voice layer. The key is written once and never comes
back; the light goes checking -> ok/failing with a plain Persian reason per Google refusal; the
chain walks on a failure or the owner's cap (Piper last, the voice never stops); every sentence
writes one usage row (the provider's tokens x the price in force that day); the meter, the
projection and the owner's settings; Piper's queue for the hub's TTS one-shot; RLS.

Nothing leaves the test: the worker's provider call runs against a fake egress (the real
`remote.run`, the real Opus encoding and the real file store), and the transport to the worker is
a local one."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from hq_api import events
from hq_api.hub import Hub
from hq_api.voice import audio, catalog, jobs, remote, store, transport
from hq_api.voice import engines as voice_engines
from hq_api.voice import speaker as S
from hq_api.voice.base import (
    EngineAudio,
    EngineFailed,
    SpeakRequest,
    VoiceChoice,
    VoiceUnavailable,
)
from hq_api.voice.engines import piper as piper_mod
from hq_api.voice.engines.gemini import GeminiEngine
from hq_api.voice.engines.piper import PiperEngine
from hq_common.openbao import SecretNotFound

from .conftest import TTS_TOKEN, agent_headers, step_up
from .p10_support import holding_switch

TTS = {"Authorization": f"Bearer {TTS_TOKEN}"}
KEY = "AIza" + "S" * 35  # a Google API key's shape (fake)
FLASH = "gemini-3.8-flash-tts"
LITE = "gemini-3.8-flash-lite-tts"
PATH = "hq/voice/google"
PCM_2S = b"\x01\x02" * 24_000 * 2  # two seconds of 24 kHz 16-bit mono
TEXT_TOKENS, AUDIO_TOKENS = 7, 50  # what the fake provider counts for two seconds


# ------------------------------------------------------------------ fakes --
class FakeBao:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.writes: list[tuple[str, dict[str, Any]]] = []

    async def read_kv(self, path: str) -> dict[str, Any]:
        if path not in self.data:
            raise SecretNotFound(path)
        return {"secret": self.data[path]}

    async def write_kv(self, path: str, data: dict[str, Any]) -> None:
        self.writes.append((path, data))
        self.data[path] = data["secret"]


class FakeEgress:
    """The egress service's POST /v1/voice/gemini: answers by op and model; `fail` maps an op
    (or `*`) to the stable code Google's refusal becomes (voice_out.classify)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail: dict[str, str] = {}
        self.fail_models: dict[str, str] = {}
        self.counts = (TEXT_TOKENS, AUDIO_TOKENS)

    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(body))
        code = (
            self.fail_models.get(body["model"]) or self.fail.get(body["op"]) or self.fail.get("*")
        )
        if code:
            return {"outcome": "error", "code": code, "data": None}
        if body["op"] == "models_get":
            return {
                "outcome": "ok",
                "code": None,
                "data": {"model": f"models/{body['model']}", "methods": ["generateContent"]},
            }
        text, audio_tokens = self.counts
        return {
            "outcome": "ok",
            "code": None,
            "data": {
                "audio_b64": base64.b64encode(PCM_2S).decode(),
                "mime": "audio/L16;codec=pcm;rate=24000",
                "usage": {
                    "text_tokens": text,
                    "audio_tokens": audio_tokens,
                    "total_tokens": text + audio_tokens,
                },
            },
        }


class LocalTransport:
    """The worker's side, run right here (what Temporal's `VoiceCall` activity does)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, hub: Any, op: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((op, dict(args)))
        return await remote.run(hub, op, args)


class FakePiper:
    """The local engine without the TTS one-shot: a stored Ogg and no cost."""

    key = "piper"

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.fail = False
        self.spoken: list[tuple[str, str]] = []

    async def speak(self, hub: Any, text: str, voice: str, rate: float) -> EngineAudio:
        if self.fail:
            raise EngineFailed("صدای ساده نتوانست بگوید.", state="failing", code="piper_failed")
        self.spoken.append((text, voice))
        holding = await hub.companies.holding()
        blob = await audio.pcm_to_opus(PCM_2S)
        fid = await audio.store(
            hub, holding.id, blob, name="piper.ogg", mime="audio/ogg", seconds=2
        )
        return EngineAudio(str(fid), "audio/ogg", 2.0, 0, 0)

    async def check(self, hub: Any) -> tuple[str, str | None]:
        return "ok", None


@pytest.fixture(autouse=True)
async def voice(hub: Hub, su: Any) -> AsyncIterator[SimpleNamespace]:
    """Clean voice data, a fake secret store, a fake egress, the local transport, a fake Piper."""
    await su.execute("TRUNCATE talk.voice_usage, talk.engine_state, talk.voice_jobs")
    # these tests walk the chain down to Piper: the owner's local voice on (off by default, 2026-11-05)
    await su.execute("""UPDATE owner.settings SET voice = '{"local": true}'::jsonb WHERE id = 1""")
    bao, egress, local = FakeBao(), FakeEgress(), LocalTransport()
    piper = FakePiper(hub)
    old_bao, hub.bao = hub.bao, bao
    transport.OVERRIDE, remote.OVERRIDE = local, egress
    voice_engines.OVERRIDE["piper"] = piper  # type: ignore[assignment]
    S.OVERRIDE = None
    yield SimpleNamespace(bao=bao, egress=egress, local=local, piper=piper)
    await jobs.drain()
    hub.bao = old_bao
    transport.OVERRIDE = remote.OVERRIDE = None
    voice_engines.OVERRIDE.clear()
    await su.execute("UPDATE owner.settings SET voice = '{}'::jsonb WHERE id = 1")


# ---------------------------------------------------------------- helpers --
async def put_key(
    client: httpx.AsyncClient, hub: Hub, sess: dict[str, Any], key: str = KEY
) -> httpx.Response:
    su_h = await step_up(hub, sess["session_id"], "voice.secret", "google")
    return await client.put(
        "/api/v1/voice/providers/google/secret",
        headers={**sess["headers"], **su_h},
        json={"secret": key},
    )


async def arm(hub: Hub, voice: SimpleNamespace, su: Any) -> None:
    """A key that is set and checked: both Gemini engines ok (no check call made)."""
    voice.bao.data[PATH] = KEY
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await store.ensure_rows(tx, holding.id)
    await su.execute(
        "UPDATE talk.engine_state SET secret_set = true, state = 'ok' WHERE provider = 'google'"
    )


async def set_voice_settings(
    client: httpx.AsyncClient, owner: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    cur = await client.get("/api/v1/owner/settings", headers=owner)
    return await client.put(
        "/api/v1/owner/settings",
        headers={**owner, "If-Match": f'"{cur.json()["version"]}"'},
        json={"voice": body},
    )


def req(
    text: str = "سلام دنیا", engine: str = FLASH, voice: str = "Kore", seq: int = 0
) -> SpeakRequest:
    return SpeakRequest(
        text=text,
        choice=VoiceChoice(engine, voice, 1.0),
        persona="secretary",
        conversation_ref="CV-0001",
        turn_id="t1",
        seq=seq,
    )


async def usage_rows(su: Any) -> list[Any]:
    return await su.fetch("SELECT * FROM talk.voice_usage ORDER BY at, id")


async def engine_view(client: httpx.AsyncClient, owner: dict[str, str], key: str) -> dict[str, Any]:
    r = await client.get("/api/v1/voice/engines", headers=owner)
    assert r.status_code == 200, r.text
    return next(e for e in r.json() if e["key"] == key)


# ----------------------------------------------------------------- the key --
async def test_the_key_is_written_checked_and_never_comes_back(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    voice: SimpleNamespace,
    owner_session: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = owner_session["headers"]
    before = (await client.get("/api/v1/voice/engines", headers=h)).json()
    assert {e["key"]: e["state"] for e in before if e["provider"] == "google"} == {
        FLASH: "missing",
        LITE: "missing",
    }
    assert {e["key_pattern"] for e in before if e["provider"] == "google"} == {
        "AIza[0-9A-Za-z_-]{35}"
    }
    with caplog.at_level(logging.DEBUG):
        r = await put_key(client, hub, owner_session)
        assert r.status_code == 202 and r.json() == {"provider": "google", "state": "checking"}
        await jobs.drain()
    assert KEY not in r.text and voice.bao.data[PATH] == KEY
    assert voice.bao.writes == [(PATH, {"secret": KEY})]
    # the light: metadata for each model, then one spoken word each, whose cost is on the meter
    assert {e["key"]: e["state"] for e in (await client.get("/api/v1/voice/engines", headers=h)).json()
            if e["provider"] == "google"} == {FLASH: "ok", LITE: "ok"}  # fmt: skip
    ops = [(c["op"], c["model"]) for c in voice.egress.calls]
    assert ops == [("models_get", FLASH), ("speak", FLASH), ("models_get", LITE), ("speak", LITE)]
    assert {c["text"] for c in voice.egress.calls if c["op"] == "speak"} == {"سلام"}
    rows = await usage_rows(su)
    assert [(r["engine"], r["kind"], r["audio_tokens"]) for r in rows] == [
        (FLASH, "check", AUDIO_TOKENS),
        (LITE, "check", AUDIO_TOKENS),
    ]
    # the key is in no response, log, audit row, event, notification, interaction or voice row
    assert KEY not in caplog.text
    for sql in (
        "SELECT count(*) FROM audit.entries a WHERE a::text LIKE '%' || $1 || '%'",
        "SELECT count(*) FROM core.outbox o WHERE o::text LIKE '%' || $1 || '%'",
        "SELECT count(*) FROM notify.notifications n WHERE n::text LIKE '%' || $1 || '%'",
        "SELECT count(*) FROM owner.interactions i WHERE i::text LIKE '%' || $1 || '%'",
        "SELECT count(*) FROM talk.engine_state t WHERE t::text LIKE '%' || $1 || '%'",
        "SELECT count(*) FROM talk.voice_usage t WHERE t::text LIKE '%' || $1 || '%'",
    ):
        assert await su.fetchval(sql, KEY) == 0, sql
    audit = await su.fetchrow(
        "SELECT summary, step_up, action_class FROM audit.entries WHERE action = 'voice.secret' "
        "ORDER BY at DESC LIMIT 1"
    )
    assert audit["summary"] == "voice.secret set" and audit["step_up"] is True
    assert (await client.get("/api/v1/voice/meter?period=today", headers=h)).text.count(KEY) == 0


async def test_the_events_of_the_light_and_the_meter_are_sent(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    voice: SimpleNamespace,
    owner_session: dict[str, Any],
) -> None:
    await su.execute("DELETE FROM core.outbox WHERE subject LIKE '%.voice.%'")
    await put_key(client, hub, owner_session)
    await jobs.drain()
    ev = await su.fetch(
        "SELECT payload FROM core.outbox WHERE payload ->> 'type' LIKE 'voice.%' ORDER BY id"
    )
    got = [json.loads(e["payload"]) if isinstance(e["payload"], str) else e["payload"] for e in ev]
    engine_events = [
        (e["data"]["engine"], e["data"]["state"]) for e in got if e["type"] == "voice.engine"
    ]
    assert (FLASH, "checking") in engine_events and (LITE, "checking") in engine_events
    assert (FLASH, "ok") in engine_events and (LITE, "ok") in engine_events
    meters = [e for e in got if e["type"] == "voice.meter"]
    assert meters and set(meters[-1]["data"]) == {
        "today_usd",
        "month_usd",
        "cap_usd",
        "projected_usd",
    }
    assert meters[-1]["data"]["month_usd"] > 0
    assert any("voice." in p for p in events.TOPICS["talk"])


@pytest.mark.parametrize(
    ("where", "code", "reason"),
    [
        ("models_get", "bad_key", "کلید درست نیست؛ کلید تازه بدهید."),
        ("models_get", "no_model_access", "این کلید به مدل صدا دسترسی ندارد."),
        ("speak", "billing_off", "صورتحساب این پروژه فعال نیست."),
        ("speak", "quota", "سهمیه تمام شده است."),
        ("models_get", "upstream_error", "گوگل الان جواب درست نداد؛ بعداً دوباره امتحان میشود."),
        ("speak", "no_audio", "گوگل الان جواب درست نداد؛ بعداً دوباره امتحان میشود."),
    ],
)
async def test_the_light_goes_failing_with_the_plain_reason_of_each_google_refusal(
    client: httpx.AsyncClient,
    hub: Hub,
    voice: SimpleNamespace,
    owner_session: dict[str, Any],
    where: str,
    code: str,
    reason: str,
) -> None:
    voice.egress.fail[where] = code
    await put_key(client, hub, owner_session)
    await jobs.drain()
    h = owner_session["headers"]
    for key in (FLASH, LITE):
        e = await engine_view(client, h, key)
        assert e["state"] == "failing" and e["reason_fa"] == reason, key
        assert e["checked_at"] is not None


async def test_one_engine_can_fail_while_the_other_is_green(
    client: httpx.AsyncClient, hub: Hub, voice: SimpleNamespace, owner_session: dict[str, Any]
) -> None:
    voice.egress.fail_models[LITE] = "no_model_access"
    await put_key(client, hub, owner_session)
    await jobs.drain()
    h = owner_session["headers"]
    assert (await engine_view(client, h, FLASH))["state"] == "ok"
    lite = await engine_view(client, h, LITE)
    assert lite["state"] == "failing" and "دسترسی ندارد" in lite["reason_fa"]


async def test_a_key_that_cannot_be_checked_does_not_leave_the_light_yellow(
    client: httpx.AsyncClient, hub: Hub, voice: SimpleNamespace, owner_session: dict[str, Any]
) -> None:
    class Down:
        async def call(self, hub: Any, op: str, args: dict[str, Any]) -> dict[str, Any]:
            raise transport.TransportDown("no worker")

    transport.OVERRIDE = Down()
    await put_key(client, hub, owner_session)
    await jobs.drain()
    e = await engine_view(client, owner_session["headers"], FLASH)
    assert e["state"] == "failing" and "ارتباط" in e["reason_fa"]


async def test_the_key_needs_the_step_up_and_a_key_shape(
    client: httpx.AsyncClient, hub: Hub, voice: SimpleNamespace, owner_session: dict[str, Any]
) -> None:
    h = owner_session["headers"]
    r = await client.put("/api/v1/voice/providers/google/secret", headers=h, json={"secret": KEY})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, owner_session["session_id"], "voice.secret", "openai")
    r = await client.put(
        "/api/v1/voice/providers/google/secret", headers={**h, **wrong}, json={"secret": KEY}
    )
    assert r.status_code == 403
    bad = await step_up(hub, owner_session["session_id"], "voice.secret", "google")
    r = await client.put(
        "/api/v1/voice/providers/google/secret",
        headers={**h, **bad},
        json={"secret": "no spaces " * 4},
    )
    assert r.status_code == 422 and "کلید" in r.json()["message_fa"]
    assert voice.bao.writes == []  # nothing was written by the refused calls
    r2 = await client.put("/api/v1/voice/providers/nobody/secret", headers=h, json={"secret": KEY})
    assert r2.status_code == 422


async def test_the_key_can_be_removed_and_the_chain_moves_on(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    voice: SimpleNamespace,
    owner_session: dict[str, Any],
) -> None:
    await put_key(client, hub, owner_session)
    await jobs.drain()
    h = owner_session["headers"]
    no_step = await client.delete("/api/v1/voice/providers/google/secret", headers=h)
    assert no_step.status_code == 403
    su_h = await step_up(hub, owner_session["session_id"], "voice.secret", "google")
    r = await client.delete("/api/v1/voice/providers/google/secret", headers={**h, **su_h})
    assert r.status_code == 200 and r.json() == {"provider": "google", "state": "missing"}
    assert voice.bao.data[PATH] == ""
    assert (await engine_view(client, h, FLASH))["state"] == "missing"
    out = await S.speak(hub, req())
    assert out.engine == "piper" and out.fell_back_fa and "کلید" in out.fell_back_fa
    assert await su.fetchval("SELECT summary FROM audit.entries WHERE action = 'voice.secret' "
                             "ORDER BY at DESC LIMIT 1") == "voice.secret removed"  # fmt: skip


async def test_the_check_route_is_free_and_refuses_with_a_plain_reason(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    voice: SimpleNamespace,
    owner_session: dict[str, Any],
) -> None:
    h = owner_session["headers"]
    r = await client.post(f"/api/v1/voice/engines/{FLASH}/check", headers=h)
    assert r.status_code == 409 and "کلید" in r.json()["message_fa"]  # no key yet
    await arm(hub, voice, su)
    r = await client.post(f"/api/v1/voice/engines/{FLASH}/check", headers=h)
    assert r.status_code == 200 and r.json()["state"] == "ok"
    assert [c["op"] for c in voice.egress.calls] == ["models_get"]  # metadata only: free
    assert await su.fetchval("SELECT count(*) FROM talk.voice_usage") == 0
    voice.egress.fail["models_get"] = "bad_key"
    r = await client.post(f"/api/v1/voice/engines/{FLASH}/check", headers=h)
    assert r.status_code == 502 and r.json()["message_fa"] == "کلید درست نیست؛ کلید تازه بدهید."
    assert (await engine_view(client, h, FLASH))["state"] == "failing"
    assert (await client.post("/api/v1/voice/engines/none/check", headers=h)).status_code == 404


async def test_the_scheduled_recheck_is_metadata_only_and_waits_while_the_holding_is_locked(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    from hq_api.worker.voice_activities import VoiceActivities

    await arm(hub, voice, su)
    act = VoiceActivities(hub)
    out = await act.voice_check("*", False)
    assert out == {"engines": {FLASH: "ok", LITE: "ok"}}
    assert {c["op"] for c in voice.egress.calls} == {"models_get"}
    assert await su.fetchval("SELECT count(*) FROM talk.voice_usage") == 0
    voice.egress.calls.clear()
    async with holding_switch(su, "engaged"):
        assert await act.voice_check("*", False) == {"skipped": "locked"}
    assert voice.egress.calls == []
    assert transport.LOCAL.get() is False  # the activity leaves nothing behind
    assert {a.__name__ for a in act.all()} == {"voice_call", "voice_check"}


# ------------------------------------------------------------ the chain --
async def test_a_sentence_is_spoken_stored_and_metered_with_the_providers_own_counts(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    out = await S.speak(hub, req("سلام دنیا", seq=3))
    assert out.engine == FLASH and out.fell_back_fa is None
    assert (out.audio_tokens, out.text_tokens) == (AUDIO_TOKENS, TEXT_TOKENS)
    assert out.seconds == pytest.approx(2.0)
    expected = (
        Decimal(TEXT_TOKENS) * Decimal("0.50") + Decimal(AUDIO_TOKENS) * Decimal("9.00")
    ) / 1_000_000
    assert out.usd == expected
    (row,) = await usage_rows(su)
    assert (row["engine"], row["provider"], row["kind"], row["persona"]) == (
        FLASH,
        "google",
        "speech",
        "secretary",
    )
    assert (row["conversation_ref"], row["turn_id"], row["seq"], row["chars"]) == (
        "CV-0001",
        "t1",
        3,
        9,
    )
    assert (row["text_tokens"], row["audio_tokens"]) == (TEXT_TOKENS, AUDIO_TOKENS)
    assert row["usd"] == expected and float(row["seconds"]) == pytest.approx(2.0)
    price = json.loads(row["price"]) if isinstance(row["price"], str) else row["price"]
    assert (price["text_in_per_m"], price["audio_out_per_m"], price["source"]) == (
        "0.50",
        "9.00",
        "table",
    )
    # the audio is a file (Opus, in the OGG container) of the holding; the key went with the call only
    f = await su.fetchrow("SELECT * FROM files.files WHERE id = $1", UUID(out.file_id))
    assert f["mime"] == "audio/ogg" and f["kind"] == "audio" and f["name"] == "CV-0001-t1-3.ogg"
    assert (await hub.storage.get(f["storage_key"]))[:4] == b"OggS"
    (call,) = [c for c in voice.egress.calls if c["op"] == "speak"]
    assert call["key"] == KEY and call["voice"] == "Kore" and call["model"] == FLASH


async def test_the_persona_rate_speeds_the_sentence_without_changing_its_pitch(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    fast = SpeakRequest("سلام", VoiceChoice(FLASH, "Kore", 1.25), "assistant", "CV-0002", "t2", 0)
    out = await S.speak(hub, fast)
    assert out.seconds == pytest.approx(1.6)  # two seconds at 1.25x
    f = await su.fetchrow("SELECT duration_s FROM files.files WHERE id = $1", UUID(out.file_id))
    assert float(f["duration_s"]) == pytest.approx(1.6, abs=0.01)


async def test_flash_lite_has_its_own_cheaper_price(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    out = await S.speak(hub, req(engine=LITE))
    assert out.engine == LITE
    assert (
        out.usd
        == (Decimal(TEXT_TOKENS) * Decimal("0.50") + Decimal(AUDIO_TOKENS) * Decimal("6.00"))
        / 1_000_000
    )


async def test_the_owner_cap_moves_the_sentence_to_the_next_engine_and_says_so(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    await arm(hub, voice, su)
    holding = await hub.companies.holding()
    assert (await set_voice_settings(client, owner, {"month_cap_usd": 1.0})).status_code == 200
    # 0.0002 USD left: a Flash sentence (about 0.000235) does not fit, a Flash-Lite one (0.000157) does
    await su.execute(
        """INSERT INTO talk.voice_usage (company_id, engine, provider, usd) VALUES ($1, $2, 'google', $3)""",
        holding.id, FLASH, Decimal("0.9998"),
    )  # fmt: skip
    lite = await S.speak(hub, req())
    assert (
        lite.engine == LITE
        and lite.fell_back_fa == "سقف ماه پر شد؛ با Gemini 3.8 Flash-Lite ادامه میدهم."
    )
    # 0.00001 left: no paid sentence fits -> Piper, the free local voice, last
    await su.execute(
        """INSERT INTO talk.voice_usage (company_id, engine, provider, usd) VALUES ($1, $2, 'google', $3)""",
        holding.id, LITE, Decimal("0.00019"),
    )  # fmt: skip
    local = await S.speak(hub, req(seq=1))
    assert local.engine == "piper" and local.usd == 0 and local.audio_tokens == 0
    assert local.fell_back_fa == "سقف ماه پر شد؛ با صدای ساده ادامه میدهم."
    assert voice.piper.spoken[-1] == (
        "سلام دنیا",
        "fa_IR-mana-medium",
    )  # a woman's voice stays a woman's (Mana, 2026-11-05)
    # the cap is the owner's alone: speaking never raised it; the light is amber
    assert (await client.get("/api/v1/owner/settings", headers=owner)).json()["voice"][
        "month_cap_usd"
    ] == 1.0
    e = await engine_view(client, owner, FLASH)
    assert e["state"] == "capped" and "سقف" in e["reason_fa"]
    # raising the cap brings the paid voice back at once
    assert (await set_voice_settings(client, owner, {"month_cap_usd": 50})).status_code == 200
    assert (await engine_view(client, owner, FLASH))["state"] == "ok"
    assert (await S.speak(hub, req(seq=2))).engine == FLASH


async def test_an_engine_that_fails_hands_the_sentence_on_and_the_voice_never_stops(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    voice.egress.fail_models[FLASH] = "quota"
    out = await S.speak(hub, req())
    assert (
        out.engine == LITE
        and out.fell_back_fa == "سهمیه تمام شده است؛ با Gemini 3.8 Flash-Lite ادامه میدهم."
    )
    assert (
        await su.fetchval("SELECT state FROM talk.engine_state WHERE engine = $1", FLASH)
        == "failing"
    )
    # a known-failing engine is not called again at once (no cost, no wait)...
    voice.egress.calls.clear()
    again = await S.speak(hub, req(seq=1))
    assert again.engine == LITE and all(c["model"] == LITE for c in voice.egress.calls)
    # ...and every paid engine failing leaves Piper
    voice.egress.fail["*"] = "bad_key"
    last = await S.speak(hub, req(seq=2, engine=LITE))
    assert last.engine == "piper" and last.fell_back_fa and "ادامه میدهم" in last.fell_back_fa
    # a failed sentence costs nothing
    assert await su.fetchval("SELECT count(*) FROM talk.voice_usage WHERE engine = $1", FLASH) == 0
    # only when Piper fails too is the voice unavailable (the turn goes on in text)
    voice.piper.fail = True
    with pytest.raises(VoiceUnavailable) as e:
        await S.speak(hub, req(seq=3))
    assert "جواب را بخوانید" in e.value.reason_fa


async def test_a_failing_engine_is_tried_again_after_a_while(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    voice.egress.fail_models[FLASH] = "upstream_error"
    assert (await S.speak(hub, req())).engine == LITE
    voice.egress.fail_models.clear()
    assert (await S.speak(hub, req(seq=1))).engine == LITE  # still resting
    await su.execute("UPDATE talk.engine_state SET checked_at = now() - interval '3 minutes'")
    back = await S.speak(hub, req(seq=2))
    assert back.engine == FLASH and back.fell_back_fa is None
    assert await su.fetchval("SELECT state FROM talk.engine_state WHERE engine = $1", FLASH) == "ok"


async def test_a_persona_voice_is_translated_for_the_engines_down_the_chain(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    assert (
        S.voice_for(LITE, "Kore") == "Kore" and S.voice_for("piper", "Kore") == "fa_IR-mana-medium"
    )
    assert S.voice_for(FLASH, "fa_IR-amir-medium") == "Charon"  # a man's voice stays a man's
    assert S.voice_for(FLASH, "unknown") in {v["name"] for v in catalog.load().gemini_voices}
    voice.egress.fail_models[FLASH] = "quota"
    await S.speak(hub, req(voice="Puck"))
    assert voice.egress.calls[-1]["voice"] == "Puck"


async def test_a_next_price_applies_by_itself_after_its_date(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    await arm(hub, voice, su)
    yesterday = date.today() - timedelta(days=1)
    price = {
        "text_in_per_m": "0.50", "audio_out_per_m": "9.00", "audio_tokens_per_s": 25,
        "valid_until": (yesterday - timedelta(days=1)).isoformat(),
        "next": {"from": yesterday.isoformat(), "text_in_per_m": "1.00", "audio_out_per_m": "18.00"},
        "source_url": "owner", "as_of": "2026-11-04",
    }  # fmt: skip
    await su.execute("UPDATE talk.engine_state SET price_override = $1::jsonb WHERE engine = $2",
                     json.dumps(price), FLASH)  # fmt: skip
    out = await S.speak(hub, req())
    assert (
        out.usd
        == (Decimal(TEXT_TOKENS) * Decimal("1.00") + Decimal(AUDIO_TOKENS) * Decimal("18.00"))
        / 1_000_000
    )
    (row,) = await usage_rows(su)
    p = json.loads(row["price"]) if isinstance(row["price"], str) else row["price"]
    assert p["audio_out_per_m"] == "18.00" and p["source"] == "owner" and p["next_applied"] is True


def test_the_price_table_changes_on_its_day_and_warns_14_days_before() -> None:
    flash = catalog.load().engines[FLASH].price
    last, first = date(2026, 12, 31), date(2027, 1, 1)
    now, then = catalog.price_in_force(flash, last), catalog.price_in_force(flash, first)
    assert (now.text_in_per_m, now.audio_out_per_m, now.from_next) == (
        Decimal("0.50"),
        Decimal("9.00"),
        False,
    )
    assert (then.text_in_per_m, then.audio_out_per_m, then.from_next) == (
        Decimal("1.00"),
        Decimal("18.00"),
        True,
    )
    assert catalog.price_in_force(flash, date(2030, 1, 1)).audio_out_per_m == Decimal("18.00")
    lite = catalog.load().engines[LITE].price
    assert catalog.price_in_force(lite, last).audio_out_per_m == Decimal("6.00")
    assert catalog.price_in_force(lite, first).audio_out_per_m == Decimal("12.00")
    # the owner's note: only inside the 14 days before the day
    note = catalog.next_price_note(flash, date(2026, 12, 18))
    assert note and "از ۱ ژانویه قیمت دو برابر میشود" in note and "۱۴ روز مانده" in note
    assert catalog.next_price_note(flash, date(2026, 12, 17)) is None  # 15 days: not yet
    assert catalog.next_price_note(flash, first) is None  # it has begun
    assert catalog.next_price_note(catalog.load().engines["piper"].price, last) is None
    # a cut is announced as a cut
    cheaper = {
        **flash,
        "next": {"from": "2027-01-01", "text_in_per_m": "0.5", "audio_out_per_m": "4"},
    }
    assert "کم میشود" in (catalog.next_price_note(cheaper, date(2026, 12, 25)) or "")
    # the prices are data with their source and the day they were read
    assert (
        flash["source_url"].startswith("https://ai.google.dev/") and flash["as_of"] == "2026-11-04"
    )
    assert flash["audio_tokens_per_s"] == 25 and len(catalog.load().gemini_voices) == 30


# --------------------------------------------------------------- the meter --
async def test_the_meter_for_today_the_month_and_the_projection(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    await arm(hub, voice, su)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        clk = await store.clock(tx)
    await S.speak(hub, req())
    await S.speak(
        hub, SpeakRequest("سلام", VoiceChoice(LITE, "Charon", 1.0), "overseer", "CV-0003", "t3", 0)
    )
    earlier = Decimal("0.25")
    if clk.day_of_month > 1:  # a row of an earlier day of this month
        await su.execute(
            """INSERT INTO talk.voice_usage (company_id, engine, provider, persona, usd, seconds, audio_tokens, at)
               VALUES ($1, $2, 'google', 'secretary', $3, 10, 250, $4)""",
            holding.id, FLASH, earlier, clk.day_start - timedelta(minutes=1),
        )  # fmt: skip
    else:
        earlier = Decimal(0)
    one = (Decimal(TEXT_TOKENS) * Decimal("0.5") + Decimal(AUDIO_TOKENS) * Decimal("9")) / 1_000_000
    two = (Decimal(TEXT_TOKENS) * Decimal("0.5") + Decimal(AUDIO_TOKENS) * Decimal("6")) / 1_000_000
    today = (await client.get("/api/v1/voice/meter?period=today", headers=owner)).json()
    month = (await client.get("/api/v1/voice/meter?period=month", headers=owner)).json()
    assert today["period"] == "today" and month["period"] == "month"
    assert today["voice_usd"] == pytest.approx(float(one + two), abs=1e-6)
    assert month["voice_usd"] == pytest.approx(float(one + two + earlier), abs=1e-6)
    assert {e["engine"] for e in today["by_engine"]} == {FLASH, LITE}
    assert {p["persona"] for p in today["by_persona"]} == {"secretary", "overseer"}
    flash_row = next(e for e in today["by_engine"] if e["engine"] == FLASH)
    assert flash_row["audio_tokens"] == AUDIO_TOKENS and flash_row["seconds"] == pytest.approx(2.0)
    # the projection is the month so far, over the days gone, times the days of the month
    expected = float(one + two + earlier) / clk.day_of_month * clk.days_in_month
    assert month["projected_usd"] == pytest.approx(expected, abs=1e-5)
    assert today["projected_usd"] == month["projected_usd"] and today["cap_usd"] is None
    assert today["talk_tokens"] >= 0 and today["updated_at"]
    assert (await client.get("/api/v1/voice/meter?period=year", headers=owner)).status_code == 422


async def test_the_model_tokens_of_the_talk_come_from_the_routers_ledger(
    client: httpx.AsyncClient, hub: Hub, su: Any, owner: dict[str, str]
) -> None:
    before = (await client.get("/api/v1/voice/meter?period=today", headers=owner)).json()
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority, caller,
               status, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
               equiv_cost_usd)
           SELECT gen_random_uuid(), now(), id, 'HQ-SEC', 'talk_turn', 2, 'hq-agents', 'ok',
                  100, 20, 300, 40, 0, 0.5 FROM core.companies WHERE kind = 'holding'"""
    )
    after = (await client.get("/api/v1/voice/meter?period=today", headers=owner)).json()
    assert after["talk_tokens"] - before["talk_tokens"] == 460
    assert after["talk_usd_equiv"] - before["talk_usd_equiv"] == pytest.approx(0.5)
    await su.execute("DELETE FROM llm.calls WHERE task_class = 'talk_turn'")


async def test_the_warning_comes_once_at_the_owners_point(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    await arm(hub, voice, su)
    holding = await hub.companies.holding()
    await set_voice_settings(client, owner, {"month_cap_usd": 1.0, "warn_at": 0.5})
    await su.execute("DELETE FROM notify.notifications WHERE link_kind = 'voice_cap'")
    await S.speak(hub, req())
    assert (
        await su.fetchval("SELECT count(*) FROM notify.notifications WHERE link_kind = 'voice_cap'")
        == 0
    )
    await su.execute(
        "INSERT INTO talk.voice_usage (company_id, engine, provider, usd) VALUES ($1, $2, 'google', 0.5)",
        holding.id, FLASH,
    )  # fmt: skip
    await S.speak(hub, req(seq=1))
    await S.speak(hub, req(seq=2))
    rows = await su.fetch(
        """SELECT title_fa, body_fa, level, domain, owner_visible, critical_reason
           FROM notify.notifications WHERE link_kind = 'voice_cap'"""
    )
    assert len(rows) == 1 and "۵۰ درصد" in rows[0]["title_fa"].replace("50", "۵۰")
    assert "دلار" in rows[0]["body_fa"]
    # the warning is the head of AI operations' (2026-11-06), not the owner's
    assert (rows[0]["domain"], rows[0]["owner_visible"]) == ("infra", False)
    # a new cap is a new warning
    await set_voice_settings(client, owner, {"month_cap_usd": 0.9})
    await S.speak(hub, req(seq=3))
    assert (
        await su.fetchval("SELECT count(*) FROM notify.notifications WHERE link_kind = 'voice_cap'")
        == 2
    )
    # the cap itself is the owner's, as money, once
    await set_voice_settings(client, owner, {"month_cap_usd": 0.5})
    await S.speak(hub, req(seq=4))
    await S.speak(hub, req(seq=5))
    cap = await su.fetch(
        """SELECT owner_visible, critical_reason FROM notify.notifications
           WHERE link_kind = 'voice_cap' AND link_ref LIKE '%:cap'"""
    )
    assert [tuple(r) for r in cap] == [(True, "money")]


# ------------------------------------------------- settings, price, sample --
async def test_the_owner_settings_carry_the_voice_cap_and_chain_additively(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    got = (await client.get("/api/v1/owner/settings", headers=owner)).json()
    assert got["voice"] == {
        "enabled": False,  # ⟨2026-11-08⟩ the owner: voice is off until he turns it on
        "month_cap_usd": None,
        "warn_at": 0.8,
        "chain": ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "piper"],
        "local": True,
    }
    assert got["timezone"] and "council_roles" in got  # everything that was there is still there
    r = await set_voice_settings(client, owner, {"month_cap_usd": 12.5})
    assert r.status_code == 200 and r.json()["voice"]["month_cap_usd"] == 12.5
    assert r.json()["voice"]["warn_at"] == 0.8  # the fields left out keep their value
    r = await set_voice_settings(client, owner, {"chain": [LITE, "piper"], "warn_at": 0.9})
    assert r.json()["voice"] == {
        "enabled": False,
        "month_cap_usd": 12.5,
        "warn_at": 0.9,
        "chain": [LITE, "piper"],
        "local": True,
    }
    r = await set_voice_settings(client, owner, {"enabled": True})
    assert r.status_code == 200 and r.json()["voice"]["enabled"] is True
    r = await set_voice_settings(client, owner, {"enabled": False})
    assert r.json()["voice"]["enabled"] is False
    r = await set_voice_settings(client, owner, {"month_cap_usd": None})
    assert r.json()["voice"]["month_cap_usd"] is None  # null on purpose removes the cap
    assert (await set_voice_settings(client, owner, {"chain": ["nope"]})).status_code == 422
    assert (await set_voice_settings(client, owner, {"warn_at": 1.5})).status_code == 422
    assert (await set_voice_settings(client, owner, {"month_cap_usd": -1})).status_code == 422
    other = await client.get("/api/v1/owner/settings", headers=owner)
    ok = await client.put(
        "/api/v1/owner/settings",
        headers={**owner, "If-Match": f'"{other.json()["version"]}"'},
        json={"digest_minutes": other.json()["digest_minutes"]},
    )
    assert ok.status_code == 200 and ok.json()["voice"]["chain"] == [LITE, "piper"]  # not touched


async def test_the_chain_the_owner_set_is_the_order_the_sentence_walks(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    await arm(hub, voice, su)
    await set_voice_settings(client, owner, {"chain": [LITE, "piper"]})
    voice.egress.fail_models[FLASH] = "billing_off"
    out = await S.speak(hub, req())
    assert out.engine == LITE  # the persona's own engine first, then the owner's chain
    assert S.store.chain_for(FLASH, [LITE, "piper"]) == [FLASH, LITE, "piper"]
    assert S.store.chain_for("piper", [FLASH]) == ["piper"]  # the free voice never spends by itself
    assert S.store.chain_for("not-an-engine", []) == ["piper"]
    # the owner, 2026-11-05: the local voice off (the default) -> no Piper; what no engine says stays text
    assert S.store.chain_for(FLASH, [LITE, "piper"], local=False) == [FLASH, LITE]
    assert S.store.chain_for("piper", [FLASH], local=False) == [FLASH]
    assert S.store.chain_for("not-an-engine", [], local=False) == []
    assert S.store.settings_of(None)["local"] is False


async def test_the_owner_can_set_and_reset_a_price(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    await arm(hub, voice, su)
    before = await engine_view(client, owner, FLASH)
    assert (
        before["price"]["audio_out_per_m"] == 9.0
        and before["price"]["next"]["from"] == "2027-01-01"
    )
    assert (
        before["price"]["valid_until"] == "2026-12-31"
        and before["price"]["audio_tokens_per_s"] == 25
    )
    soon = (date.today() + timedelta(days=10)).isoformat()
    r = await client.put(
        f"/api/v1/voice/engines/{FLASH}/price",
        headers=owner,
        json={"text_in_per_m": 0.6, "audio_out_per_m": 10, "valid_until": soon,
              "next": {"from": soon, "text_in_per_m": 1, "audio_out_per_m": 20}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert (
        r.json()["price"]["audio_out_per_m"] == 10.0 and r.json()["price"]["source_url"] == "owner"
    )
    assert "خود مالک" in r.json()["note_fa"]
    out = await S.speak(hub, req())
    assert (
        out.usd
        == (Decimal(TEXT_TOKENS) * Decimal("0.6") + Decimal(AUDIO_TOKENS) * Decimal("10"))
        / 1_000_000
    )
    meter = (await client.get("/api/v1/voice/meter?period=month", headers=owner)).json()
    assert "قیمت دو برابر میشود" in (meter["price_note_fa"] or "")  # the 14-day warning
    again = await client.put(
        f"/api/v1/voice/engines/{FLASH}/price", headers=owner, json={"reset": True}
    )
    assert again.status_code == 200 and again.json()["price"]["audio_out_per_m"] == 9.0
    bad = [
        {"text_in_per_m": 1},  # both prices are needed
        {
            "text_in_per_m": 1,
            "audio_out_per_m": 1,
            "next": {"from": "2020-01-01", "text_in_per_m": 1, "audio_out_per_m": 1},
        },
        {
            "text_in_per_m": 1,
            "audio_out_per_m": 1,
            "valid_until": soon,
        },  # a day with nothing after it
        {"text_in_per_m": -1, "audio_out_per_m": 1},
    ]
    for body in bad:
        assert (
            await client.put(f"/api/v1/voice/engines/{FLASH}/price", headers=owner, json=body)
        ).status_code == 422
    free = await client.put(
        "/api/v1/voice/engines/piper/price", headers=owner, json={"reset": True}
    )
    assert free.status_code == 422
    assert (
        await client.put("/api/v1/voice/engines/none/price", headers=owner, json={"reset": True})
    ).status_code == 404


async def test_the_voices_of_each_engine(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    flash = (await client.get(f"/api/v1/voice/engines/{FLASH}/voices", headers=owner)).json()
    assert len(flash) == 30 and {
        "Kore",
        "Zephyr",
        "Puck",
        "Charon",
        "Fenrir",
        "Leda",
        "Orus",
        "Aoede",
    } <= {v["name"] for v in flash}
    kore = next(v for v in flash if v["name"] == "Kore")
    assert (
        kore["gender_fa"] == "زن"
        and next(v for v in flash if v["name"] == "Puck")["gender_fa"] == "مرد"
    )
    assert all(v["sample_file"] is None for v in flash)
    local = (await client.get("/api/v1/voice/engines/piper/voices", headers=owner)).json()
    assert local[0]["name"] == "fa_IR-amir-medium" and len(local) == 5  # Mana too (2026-11-05)
    assert (await client.get("/api/v1/voice/engines/none/voices", headers=owner)).status_code == 404
    every = (await client.get("/api/v1/voice/engines", headers=owner)).json()
    assert [e["key"] for e in every] == [FLASH, LITE, "piper"]
    assert [e["languages"] for e in every] == [130, 101, 1]
    assert every[2]["key_pattern"] is None and every[2]["price"]["audio_out_per_m"] == 0


async def test_a_sample_costs_on_the_meter_and_a_refusal_is_a_502(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    body = {"engine": FLASH, "voice": "Kore"}
    assert (await client.post("/api/v1/voice/sample", headers=owner, json=body)).status_code == 409
    await arm(hub, voice, su)
    r = await client.post("/api/v1/voice/sample", headers=owner, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["engine"] == FLASH and out["voice"] == "Kore" and out["audio_tokens"] == AUDIO_TOKENS
    assert out["usd"] == pytest.approx(0.0004535, abs=1e-9) and out["text"]
    assert await su.fetchval("SELECT kind FROM talk.voice_usage") == "sample"
    meter = (await client.get("/api/v1/voice/meter?period=today", headers=owner)).json()
    assert meter["voice_usd"] == pytest.approx(0.0004535, abs=1e-9)
    custom = await client.post(
        "/api/v1/voice/sample", headers=owner, json={**body, "text": "یک آزمون کوتاه"}
    )
    assert custom.json()["text"] == "یک آزمون کوتاه"
    # not a voice of the engine, a key in the text, nothing to say
    for bad in (
        {"engine": FLASH, "voice": "fa_IR-amir-medium"},
        {**body, "text": KEY},
        {"engine": "none", "voice": "Kore"},
    ):
        assert (await client.post("/api/v1/voice/sample", headers=owner, json=bad)).status_code in (
            404,
            422,
        )
    # the provider refuses: 502 with the plain reason, and the light says so
    voice.egress.fail["speak"] = "billing_off"
    r = await client.post("/api/v1/voice/sample", headers=owner, json=body)
    assert r.status_code == 502 and r.json()["message_fa"] == "صورتحساب این پروژه فعال نیست."
    assert (await engine_view(client, owner, FLASH))["state"] == "failing"
    # the cap stops a sample of a paid engine too
    voice.egress.fail.clear()
    await su.execute("UPDATE talk.engine_state SET state = 'ok'")
    await set_voice_settings(client, owner, {"month_cap_usd": 0})
    r = await client.post("/api/v1/voice/sample", headers=owner, json=body)
    assert r.status_code == 409 and "سقف" in r.json()["message_fa"]


async def test_every_route_is_the_owners_alone(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    del su, voice
    agent = await agent_headers("HQ-ADV")
    routes = [
        ("GET", "/api/v1/voice/engines", None),
        ("GET", f"/api/v1/voice/engines/{FLASH}/voices", None),
        ("GET", "/api/v1/voice/meter", None),
        ("PUT", "/api/v1/voice/providers/google/secret", {"secret": KEY}),
        ("DELETE", "/api/v1/voice/providers/google/secret", None),
        ("POST", f"/api/v1/voice/engines/{FLASH}/check", None),
        ("POST", "/api/v1/voice/sample", {"engine": FLASH, "voice": "Kore"}),
        ("PUT", f"/api/v1/voice/engines/{FLASH}/price", {"reset": True}),
    ]
    for method, path, body in routes:
        anon = await client.request(method, path, json=body)
        assert anon.status_code == 401, (method, path)
        denied = await client.request(method, path, headers=agent, json=body)
        assert denied.status_code == 403, (method, path)
    assert hub.bao is not None and not hub.bao.writes  # type: ignore[attr-defined]


async def test_rls_the_voice_rows_belong_to_the_holding(
    hub: Hub, su: Any, voice: SimpleNamespace, new_company: Callable[..., Any]
) -> None:
    await arm(hub, voice, su)
    await S.speak(hub, req())
    holding = await hub.companies.holding()
    other = (await new_company())["id"]
    for table in ("talk.voice_usage", "talk.engine_state"):
        async with hub.db.tx([other]) as tx:  # a company's own view
            assert await tx.scalar(f"SELECT count(*) FROM {table}") == 0
        async with hub.db.tx([]) as tx:
            assert await tx.scalar(f"SELECT count(*) FROM {table}") == 0
        async with hub.db.tx([holding.id]) as tx:
            assert await tx.scalar(f"SELECT count(*) FROM {table}") >= 1
    async with hub.db.tx([other]) as tx:
        with pytest.raises(Exception, match=r"row-level security|violates"):
            await tx.exec(
                "INSERT INTO talk.voice_usage (company_id, engine, provider) VALUES (:c, :e, 'google')",
                c=holding.id,
                e=FLASH,
            )
    # the usage rows are append-only: the owner's money record is never rewritten
    for sql in ("UPDATE talk.voice_usage SET usd = 0", "DELETE FROM talk.voice_usage"):
        with pytest.raises(Exception, match=r"append|cannot"):
            await su.execute(sql)
    assert await su.fetchval(
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'talk.voice_usage'::regclass"
    )
    assert await su.fetchval(
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'talk.engine_state'::regclass"
    )
    assert await su.fetchval(
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'talk.voice_jobs'::regclass"
    )


# ----------------------------------------------------- adapters, transport --
async def test_the_gemini_adapter_reads_the_light_from_the_metadata_call(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    del su
    eng = GeminiEngine(FLASH, FLASH)
    voice.bao.data[PATH] = KEY
    assert await eng.check(hub) == ("ok", None)
    voice.bao.data[PATH] = ""
    assert await eng.check(hub) == ("missing", "کلید صدا داده نشده است؛ با دکمه‌ی کلید آن را بدهید.")
    voice.bao.data[PATH] = KEY
    for code, want in (
        ("bad_key", ("failing", "کلید درست نیست؛ کلید تازه بدهید.")),
        ("billing_off", ("failing", "صورتحساب این پروژه فعال نیست.")),
        ("quota", ("failing", "سهمیه تمام شده است.")),
        ("no_key", ("missing", "کلید صدا داده نشده است؛ با دکمه‌ی کلید آن را بدهید.")),
    ):
        voice.egress.fail["models_get"] = code
        assert await eng.check(hub) == want
    voice.egress.fail.pop("models_get")
    with pytest.raises(EngineFailed) as e:
        voice.egress.fail["speak"] = "no_model_access"
        await eng.speak(hub, "سلام", "Kore", 1.0)
    assert e.value.code == "no_model_access" and e.value.state == "failing"


async def test_the_default_transport_asks_the_worker_through_temporal_and_sends_no_key(
    hub: Hub, voice: SimpleNamespace
) -> None:
    sent: list[dict[str, Any]] = []

    class FakeTemporal:
        async def execute_workflow(self, name: str, *, args: list[Any], **kw: Any) -> Any:
            sent.append({"name": name, "args": args, **kw})
            return {"outcome": "ok", "code": None, "data": {"model": "m", "methods": []}}

        async def start_workflow(self, name: str, *, args: list[Any], **kw: Any) -> Any:
            sent.append({"name": name, "args": args, **kw})

    transport.OVERRIDE = None
    old, hub.temporal = hub.temporal, FakeTemporal()
    try:
        out = await transport.call(hub, "models_get", {"provider": "google", "model": FLASH})
        assert out["outcome"] == "ok"
        assert sent[0]["name"] == "VoiceCall" and sent[0]["args"][0] == "models_get"
        assert sent[0]["task_queue"] == hub.settings.task_queue and KEY not in json.dumps(
            sent[0], default=str
        )
        await jobs.start_check(hub, "google", speech=True)
        assert sent[1]["name"] == "VoiceCheck" and sent[1]["args"] == ["google", True]
        assert not jobs._tasks
        hub.temporal = None
        with pytest.raises(transport.TransportDown):
            await transport.call(hub, "models_get", {})

        class Broken:
            async def execute_workflow(self, *a: Any, **k: Any) -> Any:
                raise RuntimeError("no worker")

        hub.temporal = Broken()
        with pytest.raises(transport.TransportDown):
            await transport.call(hub, "speak", {})
        # the worker's own activity calls the provider right where it runs
        token = transport.LOCAL.set(True)
        try:
            voice.bao.data.clear()
            assert (
                await transport.call(hub, "models_get", {"provider": "google", "model": FLASH})
            )["code"] == "no_key"
        finally:
            transport.LOCAL.reset(token)
    finally:
        hub.temporal = old


async def test_a_worker_call_for_an_unknown_provider_or_audio_is_refused_plainly(
    hub: Hub, voice: SimpleNamespace
) -> None:
    assert (await remote.run(hub, "speak", {"provider": "openai"}))["code"] == "op_not_allowed"
    voice.bao.data[PATH] = KEY

    async def odd(self: Any, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "outcome": "ok",
            "code": None,
            "data": {"audio_b64": "###", "mime": "audio/L16;rate=24000"},
        }

    class Odd:
        call = odd

    remote.OVERRIDE = Odd()  # type: ignore[assignment]
    assert (
        await remote.run(
            hub, "speak", {"provider": "google", "model": FLASH, "voice": "Kore", "text": "x"}
        )
    )["code"] == "no_audio"

    class Rate:
        async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
            return {
                "outcome": "ok",
                "code": None,
                "data": {
                    "audio_b64": base64.b64encode(PCM_2S).decode(),
                    "mime": "audio/L16;rate=16000",
                },
            }

    remote.OVERRIDE = Rate()
    assert (
        await remote.run(
            hub, "speak", {"provider": "google", "model": FLASH, "voice": "Kore", "text": "x"}
        )
    )["code"] == "no_audio"
    voice.egress.counts = (1, 1)
    remote.OVERRIDE = voice.egress


async def test_opus_is_made_on_the_hub_and_wav_is_the_documented_fallback() -> None:
    ogg = await audio.pcm_to_opus(PCM_2S)
    assert ogg[:4] == b"OggS" and len(ogg) < len(PCM_2S) // 5
    _blob, mime, seconds = await audio.encode(PCM_2S, 1.0)
    assert mime == audio.OGG and seconds == pytest.approx(2.0)
    wav = audio.wav_bytes(PCM_2S)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and len(wav) == len(PCM_2S) + 44
    with pytest.raises(audio.EncodeFailed):
        await audio.pcm_to_opus(b"")


# ----------------------------------------------------------- Piper's queue --
async def tts_service(
    client: httpx.AsyncClient, *, jobs_to_do: int = 1, fail: bool = False
) -> list[dict[str, Any]]:
    """The hub's TTS one-shot in serving mode, against the real internal routes."""
    done: list[dict[str, Any]] = []
    ogg = await audio.pcm_to_opus(PCM_2S)
    for _ in range(100):
        r = await client.post("/internal/v1/voices/talk/claim", headers=TTS)
        if r.status_code == 204:
            await asyncio.sleep(0.05)
            continue
        job = r.json()
        if fail:
            f = await client.post(
                f"/internal/v1/voices/talk/{job['id']}/fail", headers=TTS, json={"error": "boom"}
            )
            assert f.status_code == 204
        else:
            d = await client.post(
                f"/internal/v1/voices/talk/{job['id']}/done",
                headers={**TTS, "Content-Type": "audio/ogg"},
                params={"duration_s": 2.0},
                content=ogg,
            )
            assert d.status_code == 200, d.text
        done.append(job)
        if len(done) >= jobs_to_do:
            break
    return done


async def test_piper_speaks_through_the_hub_tts_queue(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    del voice
    voice_engines.OVERRIDE.clear()
    hub.settings = replace(hub.settings, tts=True)  # type: ignore[misc]
    try:
        piper = PiperEngine("piper")
        spoken, served = await asyncio.gather(
            piper.speak(hub, "قیمت ۱۲ دلار است", "fa_IR-ganji-medium", 1.25),
            tts_service(client),
        )
        (job,) = served
        assert job["voice"] == "fa_IR-ganji-medium" and "دلار" in job["script"]
        assert not any(
            ch.isdigit() for ch in job["script"]
        )  # the script is spoken Persian, no digits
        assert job["rate"] == 1.25
        assert spoken.mime == "audio/ogg" and spoken.audio_tokens == 0
        assert spoken.seconds == pytest.approx(1.6, abs=0.01)  # 2 s at 1.25x
        f = await su.fetchrow(
            "SELECT * FROM files.files WHERE id = $1", UUID(str(spoken.pcm_or_file))
        )
        assert f["mime"] == "audio/ogg" and f["created_by_code"] == "tts"
    finally:
        hub.settings = replace(hub.settings, tts=False)  # type: ignore[misc]


async def test_piper_through_the_speaker_is_free_and_writes_seconds(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    del voice
    voice_engines.OVERRIDE.clear()
    hub.settings = replace(hub.settings, tts=True)  # type: ignore[misc]
    try:
        out, _ = await asyncio.gather(
            S.speak(hub, req(engine="piper", voice="fa_IR-amir-medium")), tts_service(client)
        )
        assert out.engine == "piper" and out.usd == 0 and out.fell_back_fa is None
        (row,) = await usage_rows(su)
        assert (row["engine"], row["provider"], row["usd"], row["audio_tokens"]) == (
            "piper",
            "local",
            0,
            0,
        )
        assert float(row["seconds"]) == pytest.approx(2.0)
    finally:
        hub.settings = replace(hub.settings, tts=False)  # type: ignore[misc]


async def test_piper_that_is_off_or_slow_fails_plainly_and_a_late_sentence_is_not_spoken(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    del voice
    piper = PiperEngine("piper")
    with pytest.raises(EngineFailed) as off:  # HQ_TTS is not on
        await piper.speak(hub, "سلام", "x", 1.0)
    assert off.value.state == "missing" and off.value.code == "piper_off"
    assert await piper.check(hub) == ("missing", "صدای ساده‌ی روی هاب هنوز روشن نشده است.")
    hub.settings = replace(hub.settings, tts=True)  # type: ignore[misc]
    old = piper_mod.WAIT_S
    piper_mod.WAIT_S = 0.4
    try:
        assert await piper.check(hub) == ("ok", None)
        with pytest.raises(EngineFailed) as slow:
            await piper.speak(hub, "سلام", "x", 1.0)
        assert slow.value.code == "piper_timeout"
        assert await su.fetchval("SELECT state FROM talk.voice_jobs") == "cancelled"
        assert (await client.post("/internal/v1/voices/talk/claim", headers=TTS)).status_code == 204
        with pytest.raises(EngineFailed) as empty:
            await piper.speak(hub, "   ", "x", 1.0)
        assert empty.value.code == "empty_text"
    finally:
        piper_mod.WAIT_S = old
        hub.settings = replace(hub.settings, tts=False)  # type: ignore[misc]


async def test_the_talk_queue_routes_are_the_tts_services_alone_and_stop_while_locked(
    client: httpx.AsyncClient, hub: Hub, su: Any, voice: SimpleNamespace, owner: dict[str, str]
) -> None:
    del voice
    holding = await hub.companies.holding()
    job = await su.fetchval(
        "INSERT INTO talk.voice_jobs (company_id, voice, script) VALUES ($1, 'fa_IR-amir-medium', 'سلام.') RETURNING id",
        holding.id,
    )
    for headers in (owner, await agent_headers("HQ-ADV"), {}):
        r = await client.post("/internal/v1/voices/talk/claim", headers=headers)
        assert r.status_code in (401, 403)
    async with holding_switch(su, "engaged"):
        assert (await client.post("/internal/v1/voices/talk/claim", headers=TTS)).status_code == 204
    claimed = await client.post("/internal/v1/voices/talk/claim", headers=TTS)
    assert claimed.status_code == 200 and claimed.json()["id"] == str(job)
    # three failures end the sentence; a bad body is refused; an unknown job is a 404
    for n in range(3):
        assert (
            await client.post(
                f"/internal/v1/voices/talk/{job}/fail", headers=TTS, json={"error": "x"}
            )
        ).status_code == 204
        if n < 2:
            assert (
                await client.post("/internal/v1/voices/talk/claim", headers=TTS)
            ).status_code == 200
    assert await su.fetchval("SELECT state FROM talk.voice_jobs WHERE id = $1", job) == "failed"
    bad = await client.post(
        f"/internal/v1/voices/talk/{job}/done",
        headers={**TTS, "Content-Type": "audio/ogg"},
        content=b"nope",
    )
    assert bad.status_code == 422
    wrong = await client.post(
        f"/internal/v1/voices/talk/{job}/done",
        headers={**TTS, "Content-Type": "audio/mpeg"},
        content=b"x",
    )
    assert wrong.status_code == 415
    ghost = await client.post(
        "/internal/v1/voices/talk/00000000-0000-0000-0000-000000000000/done",
        headers={**TTS, "Content-Type": "audio/ogg"},
        content=await audio.pcm_to_opus(PCM_2S),
    )
    assert ghost.status_code == 404


def test_the_seed_file_is_the_source_of_engines_prices_and_voices() -> None:
    cat = catalog.load()
    assert list(cat.engines) == [FLASH, LITE, "piper"] and cat.default_chain[-1] == "piper"
    assert cat.providers["google"].key_pattern == "AIza[0-9A-Za-z_-]{35}"
    assert cat.providers["google"].host == "generativelanguage.googleapis.com"
    assert (
        cat.providers["google"].kv_path == "hq/voice/google"
        and cat.providers["local"].kv_path is None
    )
    assert cat.engines[FLASH].languages == 130 and cat.engines[LITE].languages == 101
    assert cat.voices_as_of == "2026-11-04"
    for e in cat.engines.values():
        assert str(e.price["as_of"]) == "2026-11-04" and e.price["source_url"].startswith(
            "https://"
        )
    with pytest.raises(ValidationError):
        from hq_api.routes.owner import VoiceSettingsIn

        VoiceSettingsIn(chain=["x"])


async def test_without_the_local_voice_a_sentence_no_remote_engine_says_stays_text(
    hub: Hub, su: Any, voice: SimpleNamespace
) -> None:
    """The owner, 2026-11-05: never a bad voice. The local voice off (the default) and no key given:
    nothing is spoken (VoiceUnavailable: the turn stays text) and Piper is never asked."""
    await su.execute("UPDATE owner.settings SET voice = '{}'::jsonb WHERE id = 1")
    req = SpeakRequest("سلام", VoiceChoice(FLASH, "Kore", 1.0), "secretary", "CV-0009", "t9", 0)
    with pytest.raises(VoiceUnavailable):
        await S.speak(hub, req)
    assert voice.piper.spoken == []
