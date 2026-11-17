"""Clean seams in a voice read in parts (the owner, 2026-11-17: «تق» or a short choke at the end
of some paragraphs, in every reel).

Gemini's speech (the API and the AI Studio page alike) puts a click of 20-30 ms at the very start
of every clip and a burst of broadband noise of ~170 ms after its last word, past a short quiet
gap. Measured on the raw takes of W-000605/607/609: the burst sits 9-13 dB ABOVE the speech
(about -10 dBFS RMS, peaks past full scale) with 40-48 % of its energy above 3 kHz, where voiced
speech has under 5 %. A long text is read in parts (speech_make.api_parts) and every inner joint
used to be: burst, digital silence, click.

So each part is cleaned before the join (and a single clip too):
- the DC offset is removed;
- the head click (a blip of at most 80 ms in the first 250 ms, then at least 50 ms of quiet) is
  skipped, and the part starts 25 ms before its sustained speech;
- the tail burst (the last segment: at most 400 ms, after at least 50 ms of quiet, noise-like and
  not softer than the speech by more than 6 dB) is dropped, and the part ends 70 ms after its last
  speech falls under the quiet line (the natural decay);
- a raised-cosine fade in (10 ms) and out (30 ms); both cuts lie in quiet already;
- each part's active-speech level is matched to the median of the parts (6 dB at most);
- the parts are joined by a paragraph pause (PAUSE_S from one speech end to the next onset), with
  a short lead and tail of silence, and the whole is kept under -1 dBFS by one gain.

Pure numpy on float samples, no hub imports: the reels kits' tools/voice_seams.py carries the same
steps, and the kits' tools/audio_qc.py fails any file with a click, a hard cut or a burst left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]

HOP_S = 0.005  # the envelope's frame
QUIET_DB = -50.0  # the quiet line: under it is a pause (or under the speech level - 30 dB)
CLICK_ZONE_S = 0.25  # a head click starts this close to the clip's start
CLICK_MAX_S = 0.08
CLICK_GAP_S = 0.05  # and is followed by at least this much quiet before the speech
BURST_MAX_S = 0.40
BURST_GAP_S = 0.05  # the burst comes after at least this much quiet
BURST_HF = 0.25  # its share of energy above HF_CUT_HZ (voiced speech < 0.05; the burst 0.40-0.48)
BURST_LEVEL_DB = -6.0  # and it is at least this loud against the speech level
HF_CUT_HZ = 3000.0
HEAD_KEEP_S = 0.025  # kept before the speech onset
TAIL_KEEP_S = 0.07  # kept after the speech end: the natural decay
FADE_IN_S = 0.010
FADE_OUT_S = 0.030
LEVEL_SPAN_DB = 6.0  # a part's level is moved at most this much
PEAK_MAX = 10 ** (-1.0 / 20)  # -1 dBFS
PAUSE_S = 0.35  # from one part's speech end to the next part's onset
LEAD_S = 0.10
TAIL_S = 0.25


@dataclass
class Part:
    """One cleaned part: the samples, where its speech starts and ends in them, and what was cut."""

    x: F64
    onset: int = 0
    end: int = 0
    level_db: float = -120.0
    speech: bool = False
    click_s: float | None = None  # where a head click was cut (seconds into the raw part)
    burst_s: float | None = None  # where a tail burst was cut
    cut: tuple[float, float] = field(default=(0.0, 0.0))  # the raw part's span that was kept


def frames_db(x: F64, hop: int) -> F64:
    """RMS of each frame of `hop` samples, in dBFS."""
    n = len(x) // hop
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    fr = x[: n * hop].reshape(n, hop)
    return 20.0 * np.log10(np.sqrt(np.mean(fr * fr, axis=1)) + 1e-12)


def runs(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """[start, end) of every run of True."""
    if not mask.size:
        return []
    m = np.concatenate(([0], mask.astype(np.int8), [0]))
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist(), strict=True))


def level_of(x: F64) -> float:
    return float(20.0 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12)) if x.size else -120.0


def hf_share(x: F64, rate: int, cut_hz: float = HF_CUT_HZ) -> float:
    """The share of the energy above `cut_hz` (0..1)."""
    if x.size < 16:
        return 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / rate)
    total = float(spec.sum())
    return float(spec[freqs > cut_hz].sum() / total) if total > 0 else 0.0


def speech_level(db: F64) -> float:
    """The active speech level: the median frame among those within 35 dB of the loudest."""
    if not db.size:
        return -120.0
    sel = db[db > max(-60.0, float(db.max()) - 35.0)]
    return float(np.median(sel)) if sel.size else -120.0


def fade(x: F64, rate: int, fin_s: float = FADE_IN_S, fout_s: float = FADE_OUT_S) -> F64:
    """Raised-cosine fade in and out, in place on a copy."""
    y = x.copy()
    a = min(int(fin_s * rate), y.size // 2)
    b = min(int(fout_s * rate), y.size // 2)
    if a > 0:
        y[:a] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    if b > 0:
        y[y.size - b :] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(b) + 1) / b)
    return y


def clean_part(raw: F64, rate: int) -> Part:
    """One clip without its DC, head click and tail burst, cut in quiet and faded (see above)."""
    x = np.asarray(raw, dtype=np.float64)
    x = x - float(x.mean()) if x.size else x
    hop = max(1, int(rate * HOP_S))
    db = frames_db(x, hop)
    if not db.size or float(db.max()) < -60.0:  # nothing to speak of: kept as it is, faded
        return Part(fade(x, rate), 0, x.size, cut=(0.0, x.size / rate))
    level = speech_level(db)
    quiet = min(QUIET_DB, level - 30.0)
    segs = runs(db > quiet)
    click_s: float | None = None
    click_end = 0
    while len(segs) > 1:
        a, b = segs[0]
        if (
            a * HOP_S > CLICK_ZONE_S
            or (b - a) * HOP_S > CLICK_MAX_S
            or (segs[1][0] - b) * HOP_S < CLICK_GAP_S
        ):
            break
        click_s = a * HOP_S if click_s is None else click_s
        click_end = b * hop
        segs.pop(0)
    burst_at: int | None = None
    for _ in range(2):  # at most two trailing pieces of junk
        if len(segs) < 2:
            break
        a, b = segs[-1]
        piece = x[a * hop : b * hop]
        if (
            (b - a) * HOP_S > BURST_MAX_S
            or (a - segs[-2][1]) * HOP_S < BURST_GAP_S
            or hf_share(piece, rate) < BURST_HF
            or level_of(piece) < level + BURST_LEVEL_DB
        ):
            break
        burst_at = a * hop
        segs.pop()
    if not segs:
        return Part(fade(x, rate), 0, x.size, cut=(0.0, x.size / rate))
    onset, spend = segs[0][0] * hop, segs[-1][1] * hop
    start = max(0, onset - int(HEAD_KEEP_S * rate))
    if click_s is not None:
        start = max(start, min(onset, click_end + int(0.01 * rate)))
    stop = min(x.size, spend + int(TAIL_KEEP_S * rate))
    if burst_at is not None:
        stop = max(spend, min(stop, burst_at - int(0.02 * rate)))
    y = fade(x[start:stop], rate)
    return Part(
        y,
        onset=onset - start,
        end=spend - start,
        level_db=speech_level(frames_db(y, hop)),
        speech=True,
        click_s=click_s,
        burst_s=None if burst_at is None else burst_at / rate,
        cut=(start / rate, stop / rate),
    )


def join_parts(raws: list[F64], rate: int, pause_s: float = PAUSE_S) -> tuple[F64, dict[str, Any]]:
    """The parts cleaned, level-matched and joined; and what was done (for the log)."""
    parts = [clean_part(r, rate) for r in raws]
    levels = [p.level_db for p in parts if p.speech]
    target = float(np.median(levels)) if levels else 0.0
    gains = [
        float(np.clip(target - p.level_db, -LEVEL_SPAN_DB, LEVEL_SPAN_DB))
        if p.speech and len(levels) > 1
        else 0.0
        for p in parts
    ]
    pieces: list[F64] = [np.zeros(int(LEAD_S * rate))]
    for i, (p, g) in enumerate(zip(parts, gains, strict=True)):
        pieces.append(p.x * 10 ** (g / 20.0))
        if i < len(parts) - 1:
            kept = (p.x.size - p.end) + parts[i + 1].onset
            pieces.append(np.zeros(max(int(0.05 * rate), int(pause_s * rate) - kept)))
    pieces.append(np.zeros(int(TAIL_S * rate)))
    y = np.concatenate(pieces)
    peak = float(np.abs(y).max()) if y.size else 0.0
    scale = PEAK_MAX / peak if peak > PEAK_MAX else 1.0
    y = y * scale
    info: dict[str, Any] = {
        "parts": len(parts),
        "clicks_cut": sum(p.click_s is not None for p in parts),
        "bursts_cut": sum(p.burst_s is not None for p in parts),
        "gains_db": [round(g, 2) for g in gains],
        "peak_gain_db": round(float(20 * np.log10(scale)), 2),
        "seconds": round(y.size / rate, 2),
    }
    return y, info


def f32_to_s16(
    raw_f32: list[bytes], rate: int, pause_s: float = PAUSE_S
) -> tuple[bytes, dict[str, Any]]:
    """Little-endian float32 mono clips in, the joined voice as 16-bit PCM out."""
    arrays = [np.frombuffer(b, dtype="<f4").astype(np.float64) for b in raw_f32]
    y, info = join_parts(arrays, rate, pause_s)
    pcm = np.clip(np.round(y * 32767.0), -32768, 32767).astype("<i2")
    return pcm.tobytes(), info
