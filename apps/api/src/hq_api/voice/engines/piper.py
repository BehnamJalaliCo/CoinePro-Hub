"""Piper, the local voice (contract §32.5, §22.3): free, on the hub, always the chain's last link.

The hub's Persian voice is the TTS service (services/tts): Piper on the CPU, encoded to Ogg/Opus
with opusenc. It is a one-shot that claims work from the api; this adapter queues one sentence in
`talk.voice_jobs` (the third queue of that one-shot, beside the briefings and the bake-off) and
waits for the file. Latency is the one-shot's: a sentence is spoken within about a second while
the service runs in its serving mode (`TTS_SERVE_S`, see infra/tts/run-once.sh); on the plain
two-minute timer a turn would time out here and go on in text. Piper has no speed of its own, so
the done route applies the persona's rate to its file.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api.speech import fa_speech_script
from hq_api.voice import catalog
from hq_api.voice.base import EngineAudio, EngineFailed

WAIT_S = 25.0  # how long a turn waits for its sentence before it goes on in text
POLL_S = 0.3
DEFAULT_VOICE = "fa_IR-amir-medium"
MAX_SCRIPT = 2000


def voice_of(name: str) -> str:
    known = {v["name"] for v in catalog.load().piper_voices}
    return name if name in known else DEFAULT_VOICE


class PiperEngine:
    def __init__(self, key: str) -> None:
        self.key = key

    async def speak(self, hub: Any, text: str, voice: str, rate: float) -> EngineAudio:
        if not getattr(hub.settings, "tts", False):
            raise EngineFailed(
                "صدای ساده‌ی روی هاب هنوز روشن نشده است.", state="missing", code="piper_off"
            )
        script = fa_speech_script(text)[:MAX_SCRIPT].strip()
        if not script:
            raise EngineFailed("متنی برای گفتن نبود.", state="failing", code="empty_text")
        holding = await hub.companies.holding()
        async with hub.db.tx([holding.id]) as tx:
            job_id: UUID = await tx.scalar(
                """INSERT INTO talk.voice_jobs (company_id, voice, script, rate)
                   VALUES (:co, :v, :s, :r) RETURNING id""",
                co=holding.id,
                v=voice_of(voice),
                s=script,
                r=Decimal(str(round(max(0.5, min(2.0, rate)), 2))),
            )
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            async with hub.db.tx([holding.id]) as tx:
                row = await tx.first(
                    "SELECT state, file_id, seconds, error FROM talk.voice_jobs WHERE id = :id",
                    id=job_id,
                )
            if row and row["state"] == "done":
                return EngineAudio(
                    pcm_or_file=str(row["file_id"]),
                    mime="audio/ogg",
                    seconds=float(row["seconds"] or 0),
                    audio_tokens=0,
                    text_tokens=0,
                )
            if row and row["state"] in ("failed", "cancelled"):
                raise EngineFailed("صدای ساده نتوانست بگوید.", state="failing", code="piper_failed")
            await asyncio.sleep(POLL_S)
        with contextlib.suppress(Exception):  # a sentence that comes late must not be spoken
            async with hub.db.tx([holding.id]) as tx:
                await tx.exec(
                    """UPDATE talk.voice_jobs SET state = 'cancelled', updated_at = now()
                       WHERE id = :id AND state IN ('queued', 'claimed')""",
                    id=job_id,
                )
        raise EngineFailed("صدای ساده جواب نداد.", state="failing", code="piper_timeout")

    async def check(self, hub: Any) -> tuple[str, str | None]:
        if not getattr(hub.settings, "tts", False):
            return "missing", "صدای ساده‌ی روی هاب هنوز روشن نشده است."
        return "ok", None
