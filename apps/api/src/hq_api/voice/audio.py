"""Audio on the hub: Google's raw speech to Ogg/Opus, and the sentence's file.

Where the encoding happens (decided here, contract §32.5 "encoded on the hub (Opus)"): the api
and worker image already carries ffmpeg with libopus (it is how the hub reads owner media, prompt
6 §2), so no new dependency is added. The hub TTS service (opusenc) encodes only its own Piper
output; Google's PCM is encoded by the worker that fetched it, so a Temporal payload carries a
file id and numbers, never audio. WAV is the documented fallback if ffmpeg is missing or refuses
the stream (the file keeps its true type).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api import media
from hq_api.domain import files as F

log = logging.getLogger("hq_api.voice.audio")

PCM_RATE = 24_000  # Gemini speech is raw 16-bit little-endian mono at 24 kHz
PCM_BYTES_PER_S = PCM_RATE * 2
OPUS_KBPS = "32"
ENCODE_LIMIT_S = 30.0
MAX_PCM_BYTES = 8 * 1024 * 1024  # a sentence is seconds long; this is minutes
OGG = "audio/ogg"
WAV = "audio/wav"


class EncodeFailed(Exception):
    pass


def pcm_seconds(pcm: bytes) -> float:
    return len(pcm) / PCM_BYTES_PER_S


def wav_bytes(pcm: bytes) -> bytes:
    """A minimal RIFF/WAVE header around 16-bit mono PCM (the documented fallback)."""
    import struct

    n = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + n)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, PCM_RATE, PCM_BYTES_PER_S, 2, 16)
        + b"data"
        + struct.pack("<I", n)
        + pcm
    )


def tempo_filter(rate: float) -> list[str]:
    """ffmpeg's pitch-keeping tempo for the persona's rate (0.8..1.25 here; ffmpeg takes 0.5..2)."""
    if abs(rate - 1.0) < 0.01:
        return []
    return ["-af", f"atempo={max(0.5, min(2.0, rate)):.3f}"]


async def pcm_to_opus(pcm: bytes, rate: float = 1.0) -> bytes:
    """Raw PCM to Ogg/Opus (speech tuned, 32 kbps), at `rate` times the speed."""
    if not pcm or len(pcm) > MAX_PCM_BYTES:
        raise EncodeFailed("pcm size")
    with tempfile.TemporaryDirectory(prefix="voice-") as tmp:
        src, out = Path(tmp) / "in.pcm", Path(tmp) / "out.ogg"
        await asyncio.to_thread(src.write_bytes, pcm)
        try:
            code, _, _ = await media.run_tool(
                "ffmpeg", "-hide_banner", "-nostdin", "-y", "-threads", media.FF_THREADS,
                "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", str(src),
                *tempo_filter(rate),
                "-c:a", "libopus", "-b:a", f"{OPUS_KBPS}k", "-application", "voip",
                "-f", "ogg", str(out),
                limit_s=ENCODE_LIMIT_S,
            )  # fmt: skip
        except (OSError, TimeoutError) as exc:
            raise EncodeFailed(type(exc).__name__) from exc
        if code != 0 or not out.is_file():
            raise EncodeFailed("ffmpeg")
        return await asyncio.to_thread(out.read_bytes)


async def ogg_with_tempo(ogg: bytes, rate: float) -> bytes:
    """An Ogg/Opus file again at `rate` times the speed (Piper's file, which has no rate of its
    own). Our own bytes from the hub's TTS one-shot, so the generic ffmpeg input rules apply."""
    if abs(rate - 1.0) < 0.01:
        return ogg
    with tempfile.TemporaryDirectory(prefix="voice-") as tmp:
        src, out = Path(tmp) / "in.ogg", Path(tmp) / "out.ogg"
        await asyncio.to_thread(src.write_bytes, ogg)
        try:
            code, _, _ = await media.run_tool(
                "ffmpeg", "-hide_banner", "-nostdin", "-y", "-threads", media.FF_THREADS,
                *media.ff_input(src), *tempo_filter(rate),
                "-c:a", "libopus", "-b:a", f"{OPUS_KBPS}k", "-application", "voip",
                "-f", "ogg", str(out),
                limit_s=ENCODE_LIMIT_S,
            )  # fmt: skip
        except (OSError, TimeoutError) as exc:
            raise EncodeFailed(type(exc).__name__) from exc
        if code != 0 or not out.is_file():
            raise EncodeFailed("ffmpeg")
        return await asyncio.to_thread(out.read_bytes)


async def encode(pcm: bytes, rate: float) -> tuple[bytes, str, float]:
    """(bytes, mime, seconds) of a sentence: Ogg/Opus, or WAV when Opus cannot be made."""
    seconds = pcm_seconds(pcm) / (rate if rate > 0 else 1.0)
    try:
        return await pcm_to_opus(pcm, rate), OGG, seconds
    except EncodeFailed:
        log.warning("opus encoding failed; keeping the sentence as WAV")
        return wav_bytes(pcm), WAV, pcm_seconds(pcm)


async def store(
    hub: Any, company_id: UUID, data: bytes, *, name: str, mime: str, seconds: float
) -> UUID:
    """The sentence as a file of the holding (the conversation's audio), by service `voice`."""
    key, sha = await hub.storage.put(data)
    async with hub.db.tx([company_id]) as tx:
        file_id: UUID = await F.insert(
            tx,
            company_id=company_id,
            name=name,
            mime=mime,
            size=len(data),
            sha256=sha,
            storage_key=key,
            kind="audio",
            by_kind="service",
            by_code="voice",
            duration_s=round(seconds, 3),
        )
    return file_id
