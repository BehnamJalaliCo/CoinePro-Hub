"""Gemini speech (contract §32.5): `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`.

The call is made by the worker through egress (voice/transport.py, voice/remote.py); this adapter
only asks for it and turns the answer into the plain Persian reason the light shows. Google's own
words are never kept or shown: egress reduces every refusal to a stable code.
"""

from __future__ import annotations

from typing import Any

from hq_api.voice import transport
from hq_api.voice.base import EngineAudio, EngineFailed
from hq_api.voice.engines._ctx import FILE_NAME

PROVIDER = "google"
# code -> (the light it leaves, plain Persian reason, a retry might help)
REASONS: dict[str, tuple[str, str]] = {
    "no_key": ("missing", "کلید صدا داده نشده است؛ با دکمه‌ی کلید آن را بده."),
    "bad_key": ("failing", "کلید درست نیست؛ کلید تازه بده."),
    "no_model_access": ("failing", "این کلید به مدل صدا دسترسی ندارد."),
    "billing_off": ("failing", "صورتحساب این پروژه فعال نیست."),
    "quota": ("failing", "سهمیه تمام شده است."),
}
GENERIC = ("failing", "گوگل الان جواب درست نداد؛ بعداً دوباره امتحان میشود.")


def reason_of(code: str | None) -> tuple[str, str]:
    """(light, Persian reason) of an egress or worker code."""
    return REASONS.get(code or "", GENERIC)


class GeminiEngine:
    def __init__(self, key: str, model: str) -> None:
        self.key = key
        self.model = model

    def _args(self, **more: Any) -> dict[str, Any]:
        return {"provider": PROVIDER, "model": self.model, **more}

    async def speak(self, hub: Any, text: str, voice: str, rate: float) -> EngineAudio:
        try:
            out = await transport.call(
                hub,
                "speak",
                self._args(text=text, voice=voice, rate=rate, name=FILE_NAME.get()),
            )
        except transport.TransportDown as exc:
            raise EngineFailed(
                "ارتباط با سرویس صدا برقرار نشد.", state="failing", code="transport_down"
            ) from exc
        if out.get("outcome") != "ok":
            code = str(out.get("code") or "upstream_error")
            state, reason = reason_of(code)
            raise EngineFailed(reason, state=state, code=code)
        data = out.get("data") or {}
        return EngineAudio(
            pcm_or_file=str(data["file_id"]),
            mime=str(data.get("mime") or "audio/ogg"),
            seconds=float(data.get("seconds") or 0.0),
            audio_tokens=int(data.get("audio_tokens") or 0),
            text_tokens=int(data.get("text_tokens") or 0),
        )

    async def check(self, hub: Any) -> tuple[str, str | None]:
        """The free metadata call (`models.get`): the key is valid and the model is there for it."""
        try:
            out = await transport.call(hub, "models_get", self._args())
        except transport.TransportDown:
            return "failing", "ارتباط با سرویس صدا برقرار نشد."
        if out.get("outcome") == "ok":
            return "ok", None
        state, reason = reason_of(str(out.get("code") or "upstream_error"))
        return state, reason
