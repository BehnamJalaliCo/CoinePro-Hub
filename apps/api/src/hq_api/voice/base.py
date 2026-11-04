"""The one interface between the talk engine and the voice layer (contract §32.5–32.6).

The talk engine (hq_api.talk) owns conversations, turns and cards; it asks the voice layer to
speak one sentence for one persona and gets back a SpeechOut. The voice layer owns engines,
keys, the light, the meter, the owner's cap and the fallback chain: `speak` walks the chain
itself (the persona's engine first, then `owner.settings.voice.chain`, Piper last), writes the
usage row with the provider's own token counts, and never raises for a provider's failure while
an engine is left in the chain. Only when every engine failed (Piper included) it raises
VoiceUnavailable, and the turn goes on in text.

Adapters (hq_api.voice.engines.*) implement Engine; the registry maps an engine key of
seed/voice/engines.yaml to its adapter; tests swap in fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class VoiceChoice:
    engine: str  # an engine key of seed/voice/engines.yaml, e.g. "gemini-3.8-flash-tts"
    voice: str  # the engine's voice name, e.g. "Kore"
    rate: float = 1.0  # 0.8..1.25


@dataclass(frozen=True)
class SpeechOut:
    file_id: str  # the stored audio (Opus), one sentence
    seconds: float
    engine: str  # the engine that actually spoke (may differ from the choice after a fallback)
    audio_tokens: int  # the provider's own count (usageMetadata); 0 for a local engine
    text_tokens: int
    usd: Decimal  # tokens × the price in force at that moment; 0 for a local engine
    fell_back_fa: str | None = (
        None  # one plain line when the chain moved on («سقف ماه پر شد؛ با صدای ساده ادامه میدهم»)
    )


@dataclass(frozen=True)
class SpeakRequest:
    text: str  # one sentence, already free of secrets (the talk engine scrubs every turn)
    choice: VoiceChoice
    persona: str  # persona key or role@CODE, for the meter's by_persona
    conversation_ref: str  # CV-…, the audio file belongs to it
    turn_id: str
    seq: int  # the sentence's order in the turn


class VoiceUnavailable(Exception):
    """Every engine of the chain failed; `reason_fa` is shown once in the chat."""

    def __init__(self, reason_fa: str) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa


class EngineFailed(Exception):
    """One engine could not speak; the chain moves on. `state` is the light it leaves."""

    def __init__(
        self, reason_fa: str, *, state: str = "failing", code: str = "engine_failed"
    ) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa
        self.state = state  # "failing" | "capped" | "missing"
        self.code = code


@dataclass(frozen=True)
class EngineAudio:
    pcm_or_file: bytes | str  # raw audio bytes, or a file id when the engine stored it already
    mime: str  # e.g. "audio/L16;rate=24000" or "audio/ogg"
    seconds: float
    audio_tokens: int
    text_tokens: int


class Engine(Protocol):
    key: str

    async def speak(self, hub: Any, text: str, voice: str, rate: float) -> EngineAudio:
        """Speak one sentence or raise EngineFailed with a plain Persian reason."""
        ...

    async def check(self, hub: Any) -> tuple[str, str | None]:
        """The light: ("ok"|"missing"|"failing", reason_fa). Free calls only (metadata)."""
        ...


class Speaker(Protocol):
    """What the talk engine calls (hq_api.voice.speaker.speak implements it)."""

    async def __call__(self, hub: Any, req: SpeakRequest) -> SpeechOut: ...
