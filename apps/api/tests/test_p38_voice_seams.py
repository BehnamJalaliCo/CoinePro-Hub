"""⟨2026-11-17⟩ The owner: «تق» or a short choke at the end of some paragraphs in every reel
(voice/seams.py, speech_make.join_audio / api_speak / cleaned).

Every Gemini clip starts with a short click and ends with a burst of broadband noise after its last
word; a long text is read in parts, and the parts were joined burst | digital silence | click.
Synthetic parts carry the same three faults (a head click, a tail burst, a level step):
- each part loses its click and its burst, a clean part and a short last word are left alone;
- the joined voice has no jump at any joint and no click or burst energy there, a paragraph pause
  of PART_PAUSE_S between one speech end and the next onset, and one level across the parts;
- through the hub's own path (Opus in, Opus out), a multi-part voice and a single clip alike.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from hq_api.domain import speech_make as SM
from hq_api.voice import audio as AU
from hq_api.voice import seams

RATE = AU.PCM_RATE
F64 = NDArray[np.float64]


def rms_db(x: F64) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12))


def speech(seconds: float, level_db: float, seed: int = 0) -> F64:
    """A voiced, speech-like stretch: harmonics of a gliding 140 Hz voice under 4 Hz syllables,
    30 ms edges, at `level_db` RMS (nothing above 2 kHz, as voiced speech)."""
    t = np.arange(int(seconds * RATE)) / RATE
    f0 = 140 + 15 * np.sin(2 * np.pi * 0.7 * t + seed)
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    x = sum((0.8**k) * np.sin(k * phase) for k in range(1, 12))
    x = x * (0.55 - 0.45 * np.cos(2 * np.pi * 4 * t))
    edge = int(0.03 * RATE)
    x[:edge] *= np.linspace(0, 1, edge)
    x[-edge:] *= np.linspace(1, 0, edge)
    return np.asarray(x * 10 ** (level_db / 20) / np.sqrt(np.mean(x * x)), dtype=np.float64)


def raw_part(level_db: float, seed: int, *, click: bool = True, burst: bool = True) -> F64:
    """[click 25 ms][quiet 150 ms][speech 1.2 s][quiet 250 ms][burst 170 ms][quiet 20 ms], with a
    -72 dB noise floor and a small DC offset, as Gemini's clips come."""
    rng = np.random.default_rng(seed)
    pieces: list[F64] = []
    n = int(0.025 * RATE)
    pieces.append(
        rng.standard_normal(n) * np.exp(-np.arange(n) / (0.004 * RATE)) * 0.6
        if click
        else np.zeros(n)
    )
    pieces += [np.zeros(int(0.15 * RATE)), speech(1.2, level_db, seed), np.zeros(int(0.25 * RATE))]
    if burst:
        noise = np.convolve(rng.standard_normal(int(0.17 * RATE)), [1.0, 0.8, 0.5], "same")
        pieces.append(noise * 10 ** (-10 / 20) / np.sqrt(np.mean(noise * noise)))
    pieces.append(np.zeros(int(0.02 * RATE)))
    x = np.concatenate(pieces)
    return np.asarray(x + rng.standard_normal(x.size) * 10 ** (-72 / 20) + 0.002, dtype=np.float64)


def active_runs(y: F64) -> list[tuple[float, float]]:
    """(start, end) seconds of every stretch above -50 dBFS (5 ms frames; a flicker of up to
    20 ms under the line inside a stretch, as Opus leaves at a soft onset, does not split it)."""
    hop = int(seams.HOP_S * RATE)
    db = seams.frames_db(y, hop)
    out: list[tuple[float, float]] = []
    for a, b in seams.runs(db > -50):
        if out and a * seams.HOP_S - out[-1][1] <= 0.02:
            out[-1] = (out[-1][0], b * seams.HOP_S)
        else:
            out.append((a * seams.HOP_S, b * seams.HOP_S))
    return out


def loud_noise_frames(y: F64) -> int:
    """5 ms frames that are loud (> -40 dBFS) and broadband (> 20 % of energy above 3 kHz)."""
    hop = int(seams.HOP_S * RATE)
    n = y.size // hop
    fr = y[: n * hop].reshape(n, hop)
    return sum(1 for f in fr if rms_db(f) > -40 and seams.hf_share(f, RATE) > 0.2)


def test_a_part_loses_its_head_click_and_tail_burst() -> None:
    raw = raw_part(-20, 1)
    p = seams.clean_part(raw, RATE)
    assert p.speech and p.click_s == 0.0
    assert p.burst_s == pytest.approx(0.025 + 0.15 + 1.2 + 0.25, abs=0.01)
    start, stop = p.cut
    assert 0.025 < start < 0.175 and stop < 0.025 + 0.15 + 1.2 + 0.25  # in quiet on both sides
    assert 0.175 - start == pytest.approx(seams.HEAD_KEEP_S, abs=0.006)
    assert loud_noise_frames(p.x) == 0 and loud_noise_frames(raw) > 20
    assert abs(float(p.x.mean())) < 1e-3  # the DC went
    assert p.x[0] == 0.0 and abs(p.x[-1]) < 1e-6  # faded in and out
    assert p.level_db == pytest.approx(-20, abs=4)  # the median 5 ms frame, under the RMS


def test_a_clean_part_and_a_short_last_word_are_left_alone() -> None:
    p = seams.clean_part(raw_part(-20, 2, click=False, burst=False), RATE)
    assert p.click_s is None and p.burst_s is None
    assert (p.end - p.onset) / RATE == pytest.approx(1.2, abs=0.02)
    # a short voiced word after a pause at the very end is speech, not a burst
    word = np.concatenate([raw_part(-20, 3, click=False, burst=False), speech(0.2, -18, 4)])
    q = seams.clean_part(word, RATE)
    assert q.burst_s is None and q.cut[1] == pytest.approx(word.size / RATE, abs=0.01)
    # silence only: kept as it is (faded), never an error
    s = seams.clean_part(np.zeros(RATE), RATE)
    assert not s.speech and s.x.size == RATE


def test_joined_parts_have_clean_seams_a_paragraph_pause_and_one_level() -> None:
    raws = [raw_part(-20, 10), raw_part(-24, 11), raw_part(-20, 12)]
    y, info = seams.join_parts(raws, RATE, SM.PART_PAUSE_S)
    assert info["parts"] == 3 and info["clicks_cut"] == 3 and info["bursts_cut"] == 3
    assert info["gains_db"][1] == pytest.approx(4, abs=0.5)

    runs = active_runs(y)
    assert len(runs) == 3, runs  # three stretches of speech, nothing else above -50 dBFS
    for (_, end), (start, _) in pairwise(runs):
        assert start - end == pytest.approx(SM.PART_PAUSE_S, abs=0.015)
    assert runs[0][0] == pytest.approx(seams.LEAD_S + seams.HEAD_KEEP_S, abs=0.01)

    # no click or burst energy anywhere, no jump at any joint
    assert loud_noise_frames(y) == 0
    clean_ref = np.concatenate([speech(1.2, -20, s) for s in (10, 11, 12)])
    assert float(np.abs(np.diff(y)).max()) <= 1.05 * float(np.abs(np.diff(clean_ref)).max())
    for (_, end), (start, _) in pairwise(runs):
        gap = y[int((end + 0.015) * RATE) : int((start - 0.015) * RATE)]
        assert float(np.abs(gap).max()) < 10 ** (-50 / 20)  # quiet: only the decay, then zeros
        edge = y[int((start - 0.03) * RATE) : int((start + 0.03) * RATE)]
        assert seams.hf_share(edge, RATE) < 0.02  # the onset is the voice, not a click

    # one level: each part's speech within 0.5 dB of the others
    levels = [rms_db(y[int(a * RATE) : int(b * RATE)]) for a, b in runs]
    assert max(levels) - min(levels) < 0.5
    assert float(np.abs(y).max()) <= seams.PEAK_MAX + 1e-9


def test_a_level_step_is_moved_six_db_at_most() -> None:
    _, info = seams.join_parts([raw_part(-14, 20), raw_part(-30, 21), raw_part(-14, 22)], RATE)
    assert info["gains_db"][1] == seams.LEVEL_SPAN_DB


def s16(x: F64) -> bytes:
    return np.clip(np.round(x * 32767), -32768, 32767).astype("<i2").tobytes()


async def decoded(ogg: bytes) -> F64:
    return np.frombuffer(await SM._pcm_of(ogg, "f32le"), dtype="<f4").astype(np.float64)


async def test_the_hub_path_cleans_every_part_and_a_single_clip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through api_speak with Opus parts, as Gemini's API gives them: the joints and a voice of one
    part alike come out with no click, no burst, and the paragraph pause."""
    clips = [await AU.pcm_to_opus(s16(raw_part(-20, 30 + i))) for i in range(3)]
    asked: list[str] = []

    async def part(hub: Any, job: dict[str, Any], text: str, name: str) -> Any:
        asked.append(text)
        return clips[len(asked) - 1], AU.OGG

    monkeypatch.setattr(SM, "_api_text", part)
    text = "\n".join(f"بند {i}: " + "کلمه " * 60 for i in range(3))
    assert len(SM.api_parts(text)) == 3
    got = await SM.api_speak(None, {"job": "j-seams", "text": text, "voice": "Arlo", "by": "x"})
    assert got is not None and got[1] == AU.OGG
    y = await decoded(got[0])
    runs = active_runs(y)
    assert len(runs) == 3, runs
    for (_, end), (start, _) in pairwise(runs):
        assert start - end == pytest.approx(SM.PART_PAUSE_S, abs=0.03)
    assert loud_noise_frames(y) == 0

    asked.clear()
    one = await SM.api_speak(None, {"job": "j-one", "text": "سلام", "voice": "Arlo", "by": "x"})
    assert one is not None and one[1] == AU.OGG
    y1 = await decoded(one[0])
    assert len(active_runs(y1)) == 1 and loud_noise_frames(y1) == 0
    assert loud_noise_frames(await decoded(clips[0])) > 20  # the raw clip did have them


async def test_a_voice_that_cannot_be_read_is_kept_as_it_came() -> None:
    assert await SM.cleaned(b"not audio", "audio/wav", job="j") == (b"not audio", "audio/wav")
