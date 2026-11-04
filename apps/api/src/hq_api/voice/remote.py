"""The provider calls, as the worker makes them (contract §32.5).

The worker reads the provider's key from OpenBao (`kv/hq/voice/<provider>`) for this one call,
sends it with the call to egress (channel `gemini-tts`, host generativelanguage.googleapis.com
only) and drops it; the key is never kept, logged, returned or stored by the hub. A speech call's
answer (raw PCM) is encoded to Ogg/Opus here and stored as a file, so what goes back through
Temporal is a file id and the provider's own token counts.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any, Protocol

import httpx

from hq_api.voice import audio, catalog
from hq_common.openbao import OpenBaoError, SecretNotFound

log = logging.getLogger("hq_api.voice.remote")

TIMEOUT_S = 45.0
CHANNEL = "gemini-tts"
RATE = re.compile(r"rate=(\d{4,6})")


class Egress(Protocol):
    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]: ...


class EgressVoice:
    """POST /v1/voice/gemini on egress (the worker is on hq-egress-api)."""

    async def call(self, hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        url = hub.settings.support_egress_url.rstrip("/") + "/v1/voice/gemini"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
                resp = await http.post(url, json=body)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("voice egress call failed", extra={"error": type(exc).__name__})
            return {"outcome": "error", "code": "upstream_error", "data": None}
        return (
            out
            if isinstance(out, dict)
            else {"outcome": "error", "code": "upstream_error", "data": None}
        )


OVERRIDE: Egress | None = None  # tests put a fake egress here


def egress() -> Egress:
    return OVERRIDE or EgressVoice()


async def key_of(hub: Any, provider: str) -> str | None:
    """The provider's key for one call; None when it was never given or was removed."""
    path = catalog.load().providers[provider].kv_path
    bao = getattr(hub, "bao", None)
    if not path or bao is None:
        return None
    try:
        data = await bao.read_kv(path)
    except SecretNotFound:
        return None
    except OpenBaoError:
        log.warning("openbao could not be read for a voice call")
        return None
    value = str(data.get("secret") or "").strip()
    return value or None


def _fail(code: str) -> dict[str, Any]:
    return {"outcome": "error", "code": code, "data": None}


def _rate_of(mime: str) -> int:
    m = RATE.search(mime)
    return int(m.group(1)) if m else audio.PCM_RATE


async def run(hub: Any, op: str, args: dict[str, Any]) -> dict[str, Any]:
    """One provider call: {outcome, code, data} (the egress answer, speech already stored)."""
    cat = catalog.load()
    provider = str(args.get("provider") or "")
    if provider != "google" or provider not in cat.providers:
        return _fail("op_not_allowed")
    key = await key_of(hub, provider)
    if key is None:
        return _fail("no_key")
    body: dict[str, Any] = {
        "channel": CHANNEL,
        "op": op,
        "model": str(args.get("model") or ""),
        "key": key,
    }
    if op == "speak":
        body |= {"voice": args.get("voice"), "text": args.get("text")}
    del key
    out = await egress().call(hub, body)
    del body
    if out.get("outcome") != "ok":
        return {"outcome": out.get("outcome", "error"), "code": out.get("code"), "data": None}
    if op != "speak":
        return {"outcome": "ok", "code": None, "data": out.get("data")}
    return await _stored(hub, out.get("data") or {}, args)


async def _stored(hub: Any, data: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    try:
        pcm = base64.b64decode(str(data.get("audio_b64") or ""), validate=True)
    except (binascii.Error, ValueError):
        return _fail("no_audio")
    mime = str(data.get("mime") or "")
    if not pcm or _rate_of(mime) != audio.PCM_RATE:
        return _fail("no_audio")  # only 24 kHz 16-bit mono PCM is understood
    rate = float(args.get("rate") or 1.0)
    blob, out_mime, seconds = await audio.encode(pcm, rate)
    holding = await hub.companies.holding()
    ext = "ogg" if out_mime == audio.OGG else "wav"
    name = f"{str(args.get('name') or 'voice')[:100]}.{ext}"
    file_id = await audio.store(hub, holding.id, blob, name=name, mime=out_mime, seconds=seconds)
    usage = data.get("usage") or {}
    return {
        "outcome": "ok",
        "code": None,
        "data": {
            "file_id": str(file_id),
            "mime": out_mime,
            "seconds": round(seconds, 3),
            "text_tokens": int(usage.get("text_tokens") or 0),
            "audio_tokens": int(usage.get("audio_tokens") or 0),
        },
    }
