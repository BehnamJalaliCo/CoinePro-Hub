"""Prompt 21 part 2 (contract §29.5): long voice in chunks. The hub's speech
to text is faked at the worker's boundary (workflows_client.transcribe), so
nothing reaches a real whisper."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import voice as V
from hq_api.hub import Hub

from .conftest import idem, service_headers
from .test_files_media import audio


@pytest.fixture
def stt(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Speech on; each chunk's file answers its own text (by upload order)."""
    if not hub.settings.stt_url:
        monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url="http://stt.test"))
    state: dict[str, Any] = {"texts": {}, "calls": []}

    async def transcribe(hub_: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        state["calls"].append(file_id)
        text = state["texts"].get(file_id, "")
        return {
            "text": text,
            "duration_s": 2.0,
            "segments": [{"start_s": 0.5, "end_s": 1.5, "text": text}],
            "engine": {"name": "faster-whisper", "model": "small", "version": "test"},
        }

    monkeypatch.setattr(workflows_client, "transcribe", transcribe)
    return state


async def start(client: httpx.AsyncClient, owner: dict[str, str]) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/transcribe/sessions", headers={**owner, **idem()}, json={"purpose": "order"}
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def put(
    client: httpx.AsyncClient, owner: dict[str, str], sid: str, n: int, data: bytes
) -> httpx.Response:
    return await client.put(
        f"/api/v1/transcribe/sessions/{sid}/chunks/{n}",
        content=data,
        headers={**owner, "Content-Type": "audio/wav"},
    )


async def test_chunks_in_order_idempotent_and_joined(
    client: httpx.AsyncClient, owner: dict[str, str], stt: dict[str, Any], tmp_path: Path
) -> None:
    s = await start(client, owner)
    assert s["state"] == "open" and s["max_s"] == 1200 and s["chunk_max_s"] == 90
    one, two = audio(tmp_path, "wav", 2), audio(tmp_path, "wav", 3)
    r0 = await put(client, owner, s["id"], 0, one)
    assert r0.status_code == 200, r0.text
    assert r0.json()["chunks"] == 1 and 1.5 <= r0.json()["duration_s"] <= 2.5
    # out of order: refused, nothing kept
    gap = await put(client, owner, s["id"], 2, two)
    assert gap.status_code == 422
    r1 = await put(client, owner, s["id"], 1, two)
    assert r1.status_code == 200 and r1.json()["chunks"] == 2
    # the same chunk again: as it was (no new file)
    again = await put(client, owner, s["id"], 1, two)
    assert again.status_code == 200 and again.json()["file_id"] == r1.json()["file_id"]
    assert again.json()["chunks"] == 2
    stt["texts"][r0.json()["file_id"]] = "سلام مدير كل"  # Arabic letters: normalised
    stt["texts"][r1.json()["file_id"]] = "این فرمان دوم است"
    r = await client.post(f"/api/v1/transcribe/sessions/{s['id']}/finish", headers=owner)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["text"] == "سلام مدیر کل این فرمان دوم است"
    assert out["chunks"] == 2 and out["duration_s"] == 4.0
    assert [seg["start_s"] for seg in out["segments"]] == [0.5, 2.5]  # one time line
    assert stt["calls"] == [r0.json()["file_id"], r1.json()["file_id"]]  # in order
    # finished: the same text again, nothing sent twice; no more chunks
    r = await client.post(f"/api/v1/transcribe/sessions/{s['id']}/finish", headers=owner)
    assert r.json()["text"] == out["text"] and len(stt["calls"]) == 2
    late = await put(client, owner, s["id"], 2, one)
    assert late.status_code == 409


async def test_a_session_holds_twenty_minutes_and_a_chunk_ninety_seconds(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    stt: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hub.settings.stt_session_max_s == 1200  # STT_SESSION_MAX_S, 20 minutes
    s = await start(client, owner)
    long = await put(client, owner, s["id"], 0, audio(tmp_path, "wav", 92))
    assert long.status_code == 413, long.text
    monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_session_max_s=4))
    s = await start(client, owner)
    assert (await put(client, owner, s["id"], 1, audio(tmp_path, "wav", 3))).status_code == 200
    over = await put(client, owner, s["id"], 2, audio(tmp_path, "wav", 3))
    assert over.status_code == 413, over.text
    got = (await client.get(f"/api/v1/transcribe/sessions/{s['id']}", headers=owner)).json()
    assert got["chunks"] == 1  # the refused chunk is not kept
    # the pure rules
    with pytest.raises(Exception):  # noqa: B017
        V.add_chunk([], 5, {"n": 5, "sha256": "x", "duration_s": 1}, 1200)
    assert V.place([{"n": 1}], 2) == 1 and V.place([{"n": 1}], 1) == 0


async def test_an_unused_session_expires(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    stt: dict[str, Any],
    tmp_path: Path,
) -> None:
    s = await start(client, owner)
    old = await start(client, owner)
    await su.execute(
        "UPDATE owner.voice_sessions SET used_at = now() - interval '31 minutes' WHERE id = ANY($1::uuid[])",
        [uuid.UUID(s["id"]), uuid.UUID(old["id"])],
    )
    r = await put(client, owner, s["id"], 0, audio(tmp_path, "wav", 2))
    assert r.status_code == 410 and r.json()["code"] == "session_expired"
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await V.expire(tx) >= 2
    state = await su.fetchval(
        "SELECT state FROM owner.voice_sessions WHERE id = $1", uuid.UUID(old["id"])
    )
    assert state == "expired"
    fin = await client.post(f"/api/v1/transcribe/sessions/{old['id']}/finish", headers=owner)
    assert fin.status_code == 410


async def test_owner_only_and_off_while_speech_is_off(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    r = await client.post(
        "/api/v1/transcribe/sessions",
        headers={**service_headers(), **idem()},
        json={"purpose": "order"},
    )
    assert r.status_code in (401, 403)
    monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url=""))
    r = await client.post(
        "/api/v1/transcribe/sessions", headers={**owner, **idem()}, json={"purpose": "rule"}
    )
    assert r.status_code == 503
