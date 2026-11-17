#!/usr/bin/env python3
"""Clean voice seams: the kit's ONLY way to join clips, clean a clip or shorten pauses.

Usage:
  build/asr/venv/bin/python -I tools/voice_seams.py clean  IN OUT.wav            one take: no click, no tail noise
  build/asr/venv/bin/python -I tools/voice_seams.py join   IN1 IN2 [...] OUT.wav clips in order, as the hub joins parts
  build/asr/venv/bin/python -I tools/voice_seams.py pauses IN OUT.wav [MAX_S]    every pause longer than MAX_S
                                                                                 (default 0.45) shortened to MAX_S
Each prints a JSON line of what it did. OUT is 48 kHz mono 24-bit WAV. `clean` and `join` also cut a
take at each joint of digital silence inside it (a take the hub joined before 2026-11-17) and clean
both sides of it.

Why (the owner, 2026-11-17: «تق» or a short choke at the end of some paragraphs ruined the reels).
Every clip from Gemini's speech starts with a click of 20-30 ms and ends with a burst of broadband
noise (~170 ms, 9-13 dB ABOVE the speech, past a short quiet gap after the last word). The hub read
long texts in parts and joined them burst | silence | click; hand-made splices and pause trims
(silencedetect at -40 dB, 8 ms fades) added more. Since 2026-11-17 the hub cleans every part the
same way as `clean` here (apps/api/src/hq_api/voice/seams.py; keep the two in step):
- the DC offset is removed;
- the head click (a blip of at most 80 ms in the first 250 ms, then at least 50 ms of quiet) is
  skipped; the clip starts 25 ms before its sustained speech;
- the tail burst (the last segment: at most 400 ms, after at least 50 ms of quiet, noise-like and
  not softer than the speech by more than 6 dB) is dropped; the clip ends 70 ms after its speech;
- raised-cosine fades (10 ms in, 30 ms out), both in quiet;
- `join`: each clip's speech level matched to the median (6 dB at most), a paragraph pause of
  0.35 s from one speech end to the next onset, the whole under -1 dBFS by one gain.
`pauses` cuts ONLY inside near-silence (every frame under the speech level - 38 dB, and under
-60 dBFS), keeps half of MAX_S of it on each side and joins the two halves with raised-cosine fades,
so nothing audible is ever cut. assemble_voice.py mutes (in place, the timeline kept) any click or
burst that a take still carries. After any of these, tools/audio_qc.py must report 0 clicks, cuts
and bursts.
"""
import json
import subprocess
import sys

import numpy as np

SR = 48000
HOP_S = 0.005
QUIET_DB = -50.0
CLICK_ZONE_S, CLICK_MAX_S, CLICK_GAP_S = 0.25, 0.08, 0.05
BURST_MAX_S, BURST_GAP_S, BURST_HF, BURST_LEVEL_DB = 0.40, 0.05, 0.25, -6.0
HF_CUT_HZ = 3000.0
HEAD_KEEP_S, TAIL_KEEP_S = 0.025, 0.07
FADE_IN_S, FADE_OUT_S = 0.010, 0.030
LEVEL_SPAN_DB = 6.0
PEAK_MAX = 10 ** (-1.0 / 20)
PAUSE_S, LEAD_S, TAIL_S = 0.35, 0.10, 0.25
JOINT_DB, JOINT_MIN_S = -90.0, 0.10  # digital silence of a joint between parts (Gemini's own pauses stay above -85)


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def write_wav(path, x):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-c:a", "pcm_s24le", "-y", path], input=x.astype("<f4").tobytes(), check=True)


def frames_db(x, hop):
    n = len(x) // hop
    if n <= 0:
        return np.zeros(0)
    fr = x[: n * hop].reshape(n, hop)
    return 20.0 * np.log10(np.sqrt(np.mean(fr * fr, axis=1)) + 1e-12)


def runs(mask):
    if not mask.size:
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def level_of(x):
    return float(20.0 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12)) if x.size else -120.0


def hf_share(x, rate=SR, cut_hz=HF_CUT_HZ):
    if x.size < 16:
        return 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / rate)
    total = float(spec.sum())
    return float(spec[freqs > cut_hz].sum() / total) if total > 0 else 0.0


def speech_level(db):
    if not db.size:
        return -120.0
    sel = db[db > max(-60.0, float(db.max()) - 35.0)]
    return float(np.median(sel)) if sel.size else -120.0


def fade(x, rate=SR, fin_s=FADE_IN_S, fout_s=FADE_OUT_S):
    y = x.copy()
    a, b = min(int(fin_s * rate), y.size // 2), min(int(fout_s * rate), y.size // 2)
    if a > 0:
        y[:a] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    if b > 0:
        y[y.size - b:] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(b) + 1) / b)
    return y


def find_junk(x, rate=SR):
    """(click_end, burst_start, onset, speech_end) in samples of a DC-free clip; None when absent."""
    hop = max(1, int(rate * HOP_S))
    db = frames_db(x, hop)
    if not db.size or float(db.max()) < -60.0:
        return None, None, None, None
    level = speech_level(db)
    segs = runs(db > min(QUIET_DB, level - 30.0))
    click_end = None
    while len(segs) > 1:
        a, b = segs[0]
        if a * HOP_S > CLICK_ZONE_S or (b - a) * HOP_S > CLICK_MAX_S or (segs[1][0] - b) * HOP_S < CLICK_GAP_S:
            break
        click_end = b * hop
        segs.pop(0)
    burst = None
    for _ in range(2):
        if len(segs) < 2:
            break
        a, b = segs[-1]
        piece = x[a * hop: b * hop]
        if ((b - a) * HOP_S > BURST_MAX_S or (a - segs[-2][1]) * HOP_S < BURST_GAP_S
                or hf_share(piece, rate) < BURST_HF or level_of(piece) < level + BURST_LEVEL_DB):
            break
        burst = a * hop
        segs.pop()
    if not segs:
        return click_end, burst, None, None
    return click_end, burst, segs[0][0] * hop, segs[-1][1] * hop


def clean_part(raw, rate=SR):
    """{x, onset, end, level, click, burst}: one clip cut and faded (the hub's seams.clean_part)."""
    x = raw - float(raw.mean()) if raw.size else raw
    click_end, burst, onset, spend = find_junk(x, rate)
    if onset is None:
        return {"x": fade(x, rate), "onset": 0, "end": x.size, "level": -120.0, "speech": False,
                "click": click_end is not None, "burst": burst is not None}
    start = max(0, onset - int(HEAD_KEEP_S * rate))
    if click_end is not None:
        start = max(start, min(onset, click_end + int(0.01 * rate)))
    stop = min(x.size, spend + int(TAIL_KEEP_S * rate))
    if burst is not None:
        stop = max(spend, min(stop, burst - int(0.02 * rate)))
    y = fade(x[start:stop], rate)
    return {"x": y, "onset": onset - start, "end": spend - start, "speech": True,
            "level": speech_level(frames_db(y, max(1, int(rate * HOP_S)))),
            "click": click_end is not None, "burst": burst is not None,
            "kept_s": [round(start / rate, 3), round(stop / rate, 3)]}


def join_parts(raws, rate=SR, pause_s=PAUSE_S):
    parts = [clean_part(r, rate) for r in raws]
    levels = [p["level"] for p in parts if p["speech"]]
    target = float(np.median(levels)) if levels else 0.0
    gains = [float(np.clip(target - p["level"], -LEVEL_SPAN_DB, LEVEL_SPAN_DB)) if p["speech"] and len(levels) > 1
             else 0.0 for p in parts]
    pieces = [np.zeros(int(LEAD_S * rate))]
    for i, (p, g) in enumerate(zip(parts, gains)):
        pieces.append(p["x"] * 10 ** (g / 20.0))
        if i < len(parts) - 1:
            kept = (p["x"].size - p["end"]) + parts[i + 1]["onset"]
            pieces.append(np.zeros(max(int(0.05 * rate), int(pause_s * rate) - kept)))
    pieces.append(np.zeros(int(TAIL_S * rate)))
    y = np.concatenate(pieces)
    peak = float(np.abs(y).max()) if y.size else 0.0
    scale = PEAK_MAX / peak if peak > PEAK_MAX else 1.0
    info = {"parts": len(parts), "clicks_cut": sum(p["click"] for p in parts),
            "bursts_cut": sum(p["burst"] for p in parts), "gains_db": [round(g, 2) for g in gains],
            "peak_gain_db": round(float(20 * np.log10(scale)), 2), "seconds": round(y.size / rate, 2)}
    return y * scale, info


def split_joints(raw, rate=SR):
    """A take cut in the middle of each joint of digital silence (the hub's parts before 2026-11-17)."""
    hop = max(1, int(rate * HOP_S))
    db = frames_db(raw, hop)
    cuts = [(a + b) // 2 * hop for a, b in runs(db < JOINT_DB) if (b - a) * HOP_S >= JOINT_MIN_S]
    return [p for p in np.split(raw, cuts) if p.size]


def mute_seams(raw, rate=SR):
    """The clip with every head click and tail burst muted IN PLACE (sample times kept): at its edges
    and at each joint of digital silence inside it (a take joined by the hub before 2026-11-17)."""
    hop = max(1, int(rate * HOP_S))
    db = frames_db(raw, hop)  # before the DC goes: digital silence is exact zeros only here
    x = raw - float(raw.mean()) if raw.size else raw.copy()
    joints = [(a * hop, b * hop) for a, b in runs(db < JOINT_DB) if (b - a) * HOP_S >= JOINT_MIN_S]
    bounds, cur = [], 0
    for a, b in joints:
        if a > cur:
            bounds.append((cur, a))
        cur = b
    if cur < x.size:
        bounds.append((cur, x.size))
    y, muted = x.copy(), []
    fin, fout = int(FADE_IN_S * rate), int(FADE_OUT_S * rate)
    for a, b in bounds:
        click_end, burst, onset, spend = find_junk(x[a:b], rate)
        if click_end is not None:
            cut = a + (min(onset, click_end + int(0.01 * rate)) if onset is not None else click_end)
            y[a:cut] = 0.0
            n = min(fin, b - cut)
            y[cut:cut + n] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / max(n, 1))
            muted.append({"click_s": round(a / rate, 3)})
        if burst is not None:
            cut = a + (max(spend, burst - int(0.02 * rate)) if spend is not None else burst)
            n = min(fout, cut - a)
            y[cut - n:cut] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(n) + 1) / max(n, 1))
            y[cut:b] = 0.0
            muted.append({"burst_s": round((a + burst) / rate, 3)})
    return y, {"joints": len(joints), "muted": muted}


def shorten_pauses(raw, max_s=0.45, rate=SR):
    """Every run of near-silence longer than max_s brought to max_s, cut in its middle with fades."""
    x = raw.copy()
    hop = max(1, int(rate * HOP_S))
    db = frames_db(x, hop)
    if not db.size:
        return x, {"cuts": []}
    near = min(-60.0, speech_level(db) - 38.0)
    f = int(0.010 * rate)
    keep = int(max_s / 2 * rate)
    pieces, cur, cuts = [], 0, []
    for a, b in runs(db < near):
        a, b = a * hop, b * hop
        if a == 0 or b >= x.size - hop or b - a <= int(max_s * rate):
            continue  # the file's own lead and tail stay; short pauses stay
        c0, c1 = a + keep, b - keep  # both halves lie inside the near-silence
        piece = x[cur:c0].copy()
        piece[-f:] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(f) + 1) / f)
        pieces.append(piece)
        x[c1:c1 + f] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(f) / f)
        cuts.append({"at_s": round(a / rate, 3), "from_s": round((b - a) / rate, 3), "to_s": max_s})
        cur = c1
    pieces.append(x[cur:])
    return np.concatenate(pieces), {"near_silence_db": round(near, 1), "cuts": cuts}


def main() -> None:
    if len(sys.argv) < 4 or sys.argv[1] not in ("clean", "join", "pauses"):
        raise SystemExit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "pauses":
        src, out = args[0], args[1]
        y, info = shorten_pauses(load(src), float(args[2]) if len(args) > 2 else 0.45)
        info["seconds"] = round(y.size / SR, 2)
    else:
        if cmd == "clean" and len(args) != 2:
            raise SystemExit("clean takes one clip: clean IN OUT.wav")
        *srcs, out = args
        y, info = join_parts([p for s in srcs for p in split_joints(load(s))])
    write_wav(out, y)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
