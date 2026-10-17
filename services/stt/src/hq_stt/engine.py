"""Speech engines behind one interface.

WhisperEngine  faster-whisper (CTranslate2, int8, CPU), the pinned model from
               the volume, language fa, beam 5, VAD. Loaded on first use and
               freed after the idle time, so an unused service gives its
               memory back.
FakeEngine     tests and CI: decodes WAV with the standard library, returns
               fixture text (by the audio's sha256), "" for silence. Never
               downloads or loads a model.

The engines are synchronous (CPU-bound); the HTTP layer runs them in a
thread, one at a time.
"""

from __future__ import annotations

import contextlib
import ctypes
import gc
import hashlib
import io
import json
import logging
import math
import time
import wave
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from hq_common import persian
from hq_stt import lock
from hq_stt.config import Settings

log = logging.getLogger("hq_stt.engine")
SAMPLE_RATE = 16_000


class TooLong(Exception):
    """The audio is longer than the duration cap."""


class Undecodable(Exception):
    """The bytes are not audio the decoder understands."""


@dataclass
class Segment:
    start_s: float
    end_s: float
    text: str


@dataclass
class Transcript:
    text_raw: str
    duration_s: float
    confidence: float
    segments: list[Segment] = field(default_factory=list)
    load_s: float = 0.0
    transcribe_s: float = 0.0

    @property
    def text(self) -> str:
        return persian.normalise(self.text_raw)


class Engine(Protocol):
    name: str
    model: str
    version: str

    @property
    def loaded(self) -> bool: ...

    def transcribe(self, data: bytes) -> Transcript: ...

    def unload(self) -> bool: ...


def _trim_heap() -> None:
    """Hand freed memory back to the OS (glibc keeps it otherwise)."""
    with contextlib.suppress(OSError, AttributeError):  # not glibc: nothing to trim
        ctypes.CDLL("libc.so.6").malloc_trim(0)


def confidence_of(parts: list[tuple[float, float, float]]) -> float:
    """(duration, avg_logprob, no_speech_prob) per segment -> 0..1, weighted by
    duration: exp(avg_logprob) x (1 - no_speech_prob). 0.0 without speech."""
    total = sum(max(d, 0.0) for d, _, _ in parts)
    if total <= 0:
        return 0.0
    score = sum(
        max(d, 0.0) * math.exp(min(lp, 0.0)) * (1.0 - min(max(ns, 0.0), 1.0)) for d, lp, ns in parts
    )
    return round(min(max(score / total, 0.0), 1.0), 3)


class WhisperEngine:
    name = "faster-whisper"

    def __init__(self, s: Settings) -> None:
        self.s = s
        self.model = s.model
        self.pinned = lock.load(s.lock_file, s.model)
        self.version = f"{self._library_version()}+{self.pinned.revision[:12]}"
        self._model: Any = None

    @staticmethod
    def _library_version() -> str:
        try:
            import faster_whisper

            return str(faster_whisper.__version__)
        except ImportError:  # pragma: no cover - only in the test image
            return "absent"

    def verify(self) -> None:
        lock.verify(self.pinned, self.s.model_dir)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> float:
        if self._model is not None:
            return 0.0
        from faster_whisper import WhisperModel

        started = time.monotonic()
        self._model = WhisperModel(
            str(self.s.model_dir),
            device="cpu",
            compute_type=self.s.compute_type,
            cpu_threads=self.s.cpu_threads,
            num_workers=1,
            local_files_only=True,
        )
        took = time.monotonic() - started
        log.info("model loaded", extra={"model": self.model, "seconds": round(took, 2)})
        return took

    def unload(self) -> bool:
        if self._model is None:
            return False
        self._model = None
        gc.collect()
        _trim_heap()
        log.info("model unloaded", extra={"model": self.model})
        return True

    def decode(self, data: bytes) -> Any:
        from faster_whisper.audio import decode_audio

        try:
            return decode_audio(io.BytesIO(data), sampling_rate=SAMPLE_RATE)
        except Exception as exc:
            raise Undecodable(type(exc).__name__) from exc

    def transcribe(self, data: bytes) -> Transcript:
        samples = self.decode(data)
        duration = len(samples) / SAMPLE_RATE
        if duration > self.s.max_duration_s:
            raise TooLong(f"{duration:.0f} s")
        load_s = self._load()
        started = time.monotonic()
        segments, _info = self._model.transcribe(
            samples,
            language=self.s.language,
            beam_size=self.s.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        out: list[Segment] = []
        parts: list[tuple[float, float, float]] = []
        for seg in segments:
            text = str(seg.text).strip()
            if not text:
                continue
            out.append(Segment(round(seg.start, 2), round(seg.end, 2), text))
            parts.append((seg.end - seg.start, seg.avg_logprob, seg.no_speech_prob))
        return Transcript(
            text_raw=" ".join(s.text for s in out),
            duration_s=round(duration, 2),
            confidence=confidence_of(parts),
            segments=out,
            load_s=round(load_s, 2),
            transcribe_s=round(time.monotonic() - started, 2),
        )


SILENCE_PEAK = 300  # of 32767: about -40 dBFS


def peak(pcm: bytes, width: int) -> int:
    """The loudest sample of PCM audio, on a 16-bit scale (0 for no audio)."""
    if not pcm:
        return 0
    if width == 1:
        return max(abs(b - 128) for b in pcm) * 256
    if width == 2:
        a = array("h")
        a.frombytes(pcm[: len(pcm) // 2 * 2])
        return max((abs(x) for x in a), default=0)
    return 32767  # other widths: never taken for silence


class FakeEngine:
    """Tests and CI: never a model. A fixture (STT_FAKE_FIXTURES, JSON keyed by
    the audio's sha256: "text" or {"text", "duration_s"}) answers any format;
    otherwise WAV is decoded with the standard library: "" for silence, a
    fixed sentence for anything else; other bytes are undecodable."""

    name = "fake"
    version = "0"

    def __init__(self, s: Settings) -> None:
        self.s = s
        self.model = "fake"
        self._loaded = False
        raw = json.loads(Path(s.fake_fixtures).read_text("utf-8")) if s.fake_fixtures else {}
        self.fixtures: dict[str, dict[str, Any]] = {
            k: (v if isinstance(v, dict) else {"text": v}) for k, v in raw.items()
        }

    @property
    def loaded(self) -> bool:
        return self._loaded

    def unload(self) -> bool:
        was, self._loaded = self._loaded, False
        return was

    def _result(self, text: str, duration: float) -> Transcript:
        if duration > self.s.max_duration_s:
            raise TooLong(f"{duration:.0f} s")
        self._loaded = True
        if not text:
            return Transcript("", round(duration, 2), 0.0)
        return Transcript(text, round(duration, 2), 0.9, [Segment(0.0, round(duration, 2), text)])

    def transcribe(self, data: bytes) -> Transcript:
        fixture = self.fixtures.get(hashlib.sha256(data).hexdigest())
        if fixture is not None:
            return self._result(str(fixture.get("text", "")), float(fixture.get("duration_s", 1.0)))
        try:
            with wave.open(io.BytesIO(data)) as w:
                rate, frames, width = w.getframerate(), w.getnframes(), w.getsampwidth()
                pcm = w.readframes(frames)
        except (wave.Error, EOFError) as exc:
            raise Undecodable("not a WAV file") from exc
        duration = frames / rate if rate else 0.0
        if peak(pcm, width) < SILENCE_PEAK:
            return self._result("", duration)
        return self._result("این یک متن آزمایشی است", duration)


def build(s: Settings) -> Engine:
    if s.engine == "fake":
        return FakeEngine(s)
    if s.engine == "whisper":
        return WhisperEngine(s)
    raise ValueError(f"unknown STT_ENGINE {s.engine!r}")
