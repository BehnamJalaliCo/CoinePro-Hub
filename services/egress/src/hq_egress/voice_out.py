"""The voice layer's outbound call (prompt 23, contract §32.5): Gemini speech, nothing else.

Code calls it (the worker, on hq-egress-api), never an agent. Channel `gemini-tts`:

    POST /v1/voice/gemini
      {channel: "gemini-tts", op: "models_get" | "speak", model, key, voice?, text?}
      -> {outcome: ok | blocked | error, code, data, entries}

models_get  GET https://generativelanguage.googleapis.com/v1beta/models/<model>  (free: metadata
            only; it proves the key is valid and the model exists for it)
speak       POST .../models/<model>:generateContent with responseModalities AUDIO and one prebuilt
            voice: the answer is reduced here to {audio_b64, mime, usage} (the provider's own
            token counts, `usageMetadata`); nothing else of Google's answer goes on.

The host is fixed (generativelanguage.googleapis.com, https, port 443): the call names a model and
a voice, never a URL. The key arrives with the call (the worker reads it from OpenBao for this one
call; egress holds no secret of its own and has no route to OpenBao) and goes into the
`x-goog-api-key` header only: never into a URL, an entry (host, status, sizes and time only), a
log line, an error or the answer (scrubbed in every form).

Google's refusals are reduced to stable codes (the caller maps them to plain Persian):
`bad_key` (400/401: the key is not valid or has expired), `no_model_access` (403/404: no access to
the speech model, or the API is not enabled for the key's project), `billing_off` (billing is not
enabled: the free tier has no quota for speech models, or Google says so), `quota` (429: the
quota is spent), `bad_request` (the request was refused as malformed), `upstream_error` (anything
else, 5xx included), `no_audio` (an answer without speech). `blocked` is for anything outside the
allow-lists here (`bad_model`, `bad_voice`, `bad_text`, `bad_token`, `op_not_allowed`) and the
guard's own reasons.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_egress.accounts import scrub
from hq_egress.guard import Blocked
from hq_egress.net import CALL_ENTRIES, Entry, FetchError, track
from hq_egress.proxy import entries_json

log = logging.getLogger("hq_egress.voice")
router = APIRouter()

TOOL = "voice.gemini"
CLS = "A1"  # a metered read-like call: it changes nothing outside the provider's meter
HOST = "generativelanguage.googleapis.com"
API = f"https://{HOST}/v1beta"
MODEL = re.compile(r"^gemini-[a-z0-9][a-z0-9.-]{1,58}$")
VOICE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,40}$")
KEY = re.compile(r"^[A-Za-z0-9._~-]{20,200}$")
TEXT_MAX = 2000
ANSWER_MAX = 12 * 1024 * 1024  # base64 speech of a sentence is a few hundred KB; this is a bound
SPEAK_FIELDS = ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["gemini-tts"]
    op: str = Field(min_length=1, max_length=20)
    model: str = Field(min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=300, repr=False)
    voice: str | None = Field(default=None, max_length=60)
    text: str | None = Field(default=None, max_length=TEXT_MAX + 1)


class Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _answer(
    outcome: str, data: Any, entries: list[Entry], code: str | None, key: str
) -> JSONResponse:
    body = {
        "outcome": outcome,
        "code": code,
        "data": scrub(data, [key]),
        "entries": entries_json(entries),
    }
    return JSONResponse(body, status_code=200)


# ------------------------------------------------------------ the request --
def _request(a: CallIn) -> tuple[str, str, bytes | None]:
    """(method, url, body) of an allowed call, else Refused."""
    if a.op not in ("models_get", "speak"):
        raise Refused("op_not_allowed")
    if not KEY.match(a.key):
        raise Refused("bad_token")
    if not MODEL.match(a.model):
        raise Refused("bad_model")
    if a.op == "models_get":
        if a.voice is not None or a.text is not None:
            raise Refused("op_not_allowed")
        return "GET", f"{API}/models/{a.model}", None
    if a.voice is None or not VOICE.match(a.voice):
        raise Refused("bad_voice")
    if a.text is None or not a.text.strip() or len(a.text) > TEXT_MAX:
        raise Refused("bad_text")
    body = {
        "contents": [{"parts": [{"text": a.text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a.voice}}},
        },
    }
    return "POST", f"{API}/models/{a.model}:generateContent", json.dumps(body).encode()


# ------------------------------------------------------------- the answer --
def _error_parts(parsed: Any) -> tuple[str, str, str]:
    """(status, message, reason) of Google's error body, lower-cased; read here, never passed on."""
    err = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(err, dict):
        return "", "", ""
    status = str(err.get("status") or "").lower()
    message = str(err.get("message") or "").lower()
    reason = ""
    for d in err.get("details") or []:
        if isinstance(d, dict) and d.get("reason"):
            reason = str(d["reason"]).lower()
            break
    return status, message, reason


def classify(http_status: int, parsed: Any) -> str:
    """Google's refusal as one of the stable codes."""
    status, message, reason = _error_parts(parsed)
    if (
        "api_key_invalid" in reason
        or "api key not valid" in message
        or "api key expired" in message
    ):
        return "bad_key"
    if http_status == 401 or status == "unauthenticated":
        return "bad_key"
    if "billing" in message or "billing" in reason:
        return "billing_off"
    if http_status == 429 or status == "resource_exhausted":
        # a free-tier key has no quota at all for the speech models: `limit: 0`
        if "limit: 0" in message or "free tier" in message or "free_tier" in message:
            return "billing_off"
        return "quota"
    if http_status in (403, 404) or status in ("permission_denied", "not_found"):
        return "no_model_access"
    if http_status == 400 and status == "failed_precondition":
        return "billing_off" if "enable" in message and "billing" in message else "bad_request"
    if http_status == 400:
        return "bad_key" if "key" in message and "valid" in message else "bad_request"
    return "upstream_error"


def _counts(meta: Any) -> dict[str, int]:
    """The provider's own token counts: text in, audio out, total."""
    meta = meta if isinstance(meta, dict) else {}
    text = int(meta.get("promptTokenCount") or 0)
    total = int(meta.get("totalTokenCount") or 0)
    audio = 0
    for d in meta.get("candidatesTokensDetails") or []:
        if isinstance(d, dict) and str(d.get("modality") or "").upper() == "AUDIO":
            audio += int(d.get("tokenCount") or 0)
    if not audio:
        audio = int(meta.get("candidatesTokenCount") or 0)
    for d in meta.get("promptTokensDetails") or []:
        if isinstance(d, dict) and str(d.get("modality") or "").upper() == "TEXT":
            text = int(d.get("tokenCount") or text)
            break
    return {"text_tokens": text, "audio_tokens": audio, "total_tokens": total or text + audio}


def _speech(parsed: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(parsed, dict):
        return None, "no_audio"
    for cand in parsed.get("candidates") or []:
        content = cand.get("content") if isinstance(cand, dict) else None
        for part in (content or {}).get("parts") or []:
            inline = part.get("inlineData") if isinstance(part, dict) else None
            if isinstance(inline, dict) and isinstance(inline.get("data"), str) and inline["data"]:
                return {
                    "audio_b64": inline["data"],
                    "mime": str(inline.get("mimeType") or "audio/L16;rate=24000")[:60],
                    "usage": _counts(parsed.get("usageMetadata")),
                }, None
    return None, "no_audio"


def _outcome(a: CallIn, http_status: int, parsed: Any) -> tuple[str, str | None, Any]:
    if http_status != 200:
        return "error", classify(http_status, parsed), None
    if a.op == "models_get":
        if not isinstance(parsed, dict):
            return "error", "upstream_error", None
        methods = parsed.get("supportedGenerationMethods")
        return (
            "ok",
            None,
            {
                "model": str(parsed.get("name") or "")[:100],
                "methods": [str(m)[:40] for m in methods][:10] if isinstance(methods, list) else [],
            },
        )
    data, code = _speech(parsed)
    if data is None:
        return "error", code, None
    return "ok", None, data


# ---------------------------------------------------------------- the call --
@router.post("/v1/voice/gemini")
async def gemini(a: CallIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    entries: list[Entry] = []
    ctx_token = CALL_ENTRIES.set(entries)
    secret = a.key
    try:
        async with asyncio.timeout(state.settings.call_deadline_s):
            return await _call(state, a, entries)
    except TimeoutError:
        code = "call_timeout"
    except Exception as exc:  # noqa: BLE001 - the answer must still carry the entries
        log.warning("voice.gemini failed: %s", type(exc).__name__)
        code = "upstream_error"
    finally:
        CALL_ENTRIES.reset(ctx_token)
    for e in entries:
        if e.status is None and e.blocked_reason is None:
            e.blocked_reason = code
    return _answer("error", None, entries, code, secret)


async def _call(state: Any, a: CallIn, entries: list[Entry]) -> JSONResponse:
    secret = a.key
    try:
        method, url, body = _request(a)
        # The guard first (the fixed name, every address); the connection checks it again.
        target = state.guard.target(url)
        await state.guard.addresses(target.host, target.port)
    except Refused as r:
        track(Entry(TOOL, "POST", HOST, blocked_reason=r.code, cls=CLS))
        return _answer("blocked", None, entries, r.code, secret)
    except Blocked as b:
        track(Entry(TOOL, "POST", HOST, blocked_reason=b.reason, cls=CLS))
        return _answer("blocked", None, entries, b.reason, secret)
    headers = {"x-goog-api-key": a.key, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    start = time.monotonic()
    try:
        got = await state.fetcher.fetch(
            method,
            url,
            tool=TOOL,
            cls=CLS,
            headers=headers,
            content=body,
            max_bytes=ANSWER_MAX,
        )
    except Blocked as b:
        return _answer("blocked", None, entries, b.reason, secret)
    except FetchError:
        if entries:
            entries[-1].ms = entries[-1].ms or int((time.monotonic() - start) * 1000)
        return _answer("error", None, entries, "upstream_error", secret)
    try:
        parsed: Any = json.loads(bytes(got.body).decode("utf-8", "replace") or "null")
    except ValueError:
        parsed = None
    if got.truncated:
        return _answer("error", None, entries, "upstream_error", secret)
    outcome, code, data = _outcome(a, got.status, parsed)
    return _answer(outcome, data, entries, code, secret)
