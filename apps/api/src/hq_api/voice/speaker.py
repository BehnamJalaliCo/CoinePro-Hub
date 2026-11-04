"""The voice layer's entry for the talk engine (contract §32.5–32.6): `speak` walks the chain.

STUB on build/w3: the voice layer's builder replaces the body (engines, cap, usage rows, files).
Until then every call raises VoiceUnavailable and the turn goes on in text. Tests of the talk
engine set OVERRIDE to a fake Speaker.
"""

from __future__ import annotations

from typing import Any

from hq_api.voice.base import SpeakRequest, Speaker, SpeechOut, VoiceUnavailable

OVERRIDE: Speaker | None = None


async def speak(hub: Any, req: SpeakRequest) -> SpeechOut:
    if OVERRIDE is not None:
        return await OVERRIDE(hub, req)
    raise VoiceUnavailable("صدا هنوز آماده نیست؛ جواب را بخوانید.")
