#!/usr/bin/env python3
"""Technical QC of a narration file: duration, loudness, peak, long silences, and the seams.

Usage: python3 -I tools/audio_qc.py AUDIO [OUT.json]
(numpy is needed; without it the tool runs itself again with the kit's venv, build/asr/venv.)
Rules (reels narration): duration 60–90 s; no inner silence > 0.8 s (−40 dBFS);
true peak ≤ −1 dBTP after mastering; integrated loudness is normalised to −14 LUFS at mux time.

The seams (the owner, 2026-11-17: «تق» or a short choke at the end of some paragraphs ruins the
reel). Any one of these FAILS the file (checks.no_clicks_cuts_bursts false, exit code 1); the voice
is then rebuilt (a new speech.make, or tools/voice_seams.py), never patched by hand:
- click: a blip of at most 50 ms between two quiet stretches of 50 ms or more that is about as
  loud as the speech (Gemini's head click: 20-30 ms, 2-7 dB over the speech level, 100 ms or more
  of quiet after it; a natural "t" release next to a pause is 7 dB or more under it, a stop
  between two words has under 50 ms of quiet on a side), or a sample-to-sample jump standing far above its 20 ms
  surroundings (ratio ≥ 7) and at least 3x the speech RMS (a cut without a fade; speech ≤ 2.4x);
- cut: speech level (held for 20 ms) falling to near-silence (speech level − 40 dB, held 30 ms) in
  8 ms or less (a 4 ms window; a natural word end takes 24 ms or more);
- burst: broadband noise (20-75 % of its energy above 3 kHz, 3 dB or more over the speech level)
  for 60 ms or more, or a broadband segment (25-75 % above 3 kHz) of 60-400 ms after a
  quiet gap, not softer than the speech by more than 3 dB (Gemini's tail burst: ~170 ms, 9-13 dB
  over the speech, 40-48 % above 3 kHz; a sibilant word like «تصمیم» is 85 % and stays).
Tuned on the raw takes of W-000605/607/609 (every inner joint flagged) and on the same takes
cleaned by the hub's seams (no finding).
"""
import json
import os
import re
import subprocess
import sys

try:
    import numpy as np
except ImportError:  # the kit's venv has numpy; the system python may not
    if not os.environ.get("AUDIO_QC_REEXEC"):
        here = os.path.dirname(os.path.abspath(__file__))
        for py in ("build/asr/venv/bin/python", os.path.join(here, "..", "build", "asr", "venv", "bin", "python"),
                   "/home/studio/kits/prochart-reels/asr/venv/bin/python"):
            if os.path.exists(py):
                os.environ["AUDIO_QC_REEXEC"] = "1"
                os.execv(py, [py, "-I", os.path.abspath(__file__), *sys.argv[1:]])
    raise SystemExit("audio_qc: numpy is missing; run it with build/asr/venv/bin/python -I")

SR = 48000
HOP_S = 0.005


def run(args):
    return subprocess.run(args, capture_output=True, text=True).stderr


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def runs(mask):
    if not mask.size:
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def hf_share(x, cut_hz=3000.0):
    if x.size < 16:
        return 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / SR)
    total = float(spec.sum())
    return float(spec[freqs > cut_hz].sum() / total) if total > 0 else 0.0


def level_of(x):
    return float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12)) if x.size else -120.0


def seams(x):
    """Every click, hard cut and noise burst: [{"kind", "t", ...}] and the speech level used."""
    x = x - float(x.mean())
    h = int(HOP_S * SR)
    n = x.size // h
    if n < 10:
        return [], None
    fr = x[: n * h].reshape(n, h)
    db = 20 * np.log10(np.sqrt(np.mean(fr * fr, axis=1)) + 1e-12)
    loud = db[db > -70]
    if not loud.size or float(loud.max()) < -50:
        return [], None
    level = float(np.median(db[db > np.percentile(loud, 95) - 25]))  # the active speech level
    quiet = min(-50.0, level - 30.0)
    found = []

    # bursts (a): loud broadband frames, merged over gaps of up to 20 ms, for 60 ms or more
    spec = np.abs(np.fft.rfft(fr * np.hanning(h), axis=1)) ** 2
    freqs = np.fft.rfftfreq(h, 1.0 / SR)
    hf = spec[:, freqs > 3000].sum(axis=1) / (spec.sum(axis=1) + 1e-20)
    noisy = (db >= level + 3) & (hf >= 0.2) & (hf <= 0.75)
    merged = noisy.copy()
    for a, b in runs(~noisy):
        if 0 < a and b < n and (b - a) * HOP_S <= 0.02:
            merged[a:b] = True
    for a, b in runs(merged):
        if noisy[a:b].sum() * HOP_S >= 0.06:
            found.append({"kind": "burst", "t": round(a * HOP_S, 3), "len_s": round((b - a) * HOP_S, 3),
                          "over_speech_db": round(float(db[a:b][noisy[a:b]].mean()) - level, 1)})

    # segments between quiet stretches: clicks (short blips) and bursts (b)
    segs = runs(db > quiet)
    for i, (a, b) in enumerate(segs):
        gap_b = (a - segs[i - 1][1]) * HOP_S if i else a * HOP_S
        gap_a = (segs[i + 1][0] - b) * HOP_S if i + 1 < len(segs) else (n - b) * HOP_S
        span = (b - a) * HOP_S
        piece = x[a * h: b * h]
        if span <= 0.05 and (gap_b >= 0.05 or a == 0) and (gap_a >= 0.05 or b == n):
            top = float(db[a:b].max())
            if top >= level - 3:
                found.append({"kind": "click", "t": round(a * HOP_S, 3), "len_s": round(span, 3),
                              "over_speech_db": round(top - level, 1)})
        elif 0.06 <= span <= 0.40 and i > 0 and gap_b >= 0.04:
            lv = level_of(piece)
            if 0.25 <= hf_share(piece) <= 0.75 and lv >= level - 3:
                found.append({"kind": "burst", "t": round(a * HOP_S, 3), "len_s": round(span, 3),
                              "over_speech_db": round(lv - level, 1)})

    # clicks (b): a sample jump far above its 20 ms surroundings, at least 3x the speech RMS
    d = np.abs(np.diff(x, prepend=x[0]))
    c = np.concatenate(([0.0], np.cumsum(d * d)))
    idx = np.arange(d.size)
    lo, hi = np.clip(idx - 480, 0, d.size), np.clip(idx + 480, 0, d.size)
    local = np.sqrt((c[hi] - c[lo]) / np.maximum(hi - lo, 1)) + 1e-9
    s_rms = 10 ** (level / 20)
    spikes = np.flatnonzero((d / local >= 7) & (d >= 3 * s_rms))
    last = -SR
    for k in spikes.tolist():
        if k - last >= int(0.02 * SR):
            found.append({"kind": "click", "t": round(k / SR, 3), "len_s": 0.0,
                          "jump_x_speech": round(float(d[k] / s_rms), 1)})
        last = k

    # cuts: speech (held 20 ms) to near-silence (held 30 ms) in 8 ms or less, 4 ms window, 1 ms step
    c2 = np.concatenate(([0.0], np.cumsum(x * x)))
    st = np.arange(0, x.size - 192, 48)
    e4 = 10 * np.log10((c2[st + 192] - c2[st]) / 192 + 1e-24)
    m = e4.size
    near = e4 <= level - 40
    cn = np.concatenate(([0], np.cumsum(near)))
    stay = np.zeros(m, dtype=bool)
    stay[: m - 30] = (cn[30:m] - cn[: m - 30]) == 30
    held = e4 >= level - 12
    ch = np.concatenate(([0], np.cumsum(held)))
    loud_idx = np.flatnonzero(e4 >= level - 6)
    for k in np.flatnonzero(stay & ~np.concatenate(([False], stay[:-1]))).tolist():
        prev = loud_idx[loud_idx < k]
        if not prev.size:
            continue
        p = int(prev[-1])
        if k - p <= 8 and p >= 30 and ch[p] - ch[p - 30] >= 20:
            found.append({"kind": "cut", "t": round(p / 1000, 3), "fall_ms": int(k - p)})

    found.sort(key=lambda f: f["t"])
    dedup = []
    for f in found:
        if dedup and dedup[-1]["kind"] == f["kind"] and f["t"] - dedup[-1]["t"] < 0.1:
            continue
        dedup.append(f)
    return dedup, round(level, 1)


def main() -> None:
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
                            "-of", "json", src], capture_output=True, text=True).stdout
    info = json.loads(probe)
    dur = float(info["format"]["duration"])
    st = info["streams"][0]
    eb = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = eb[eb.rfind("Summary:"):]
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1))
    lra = float(re.search(r"LRA:\s+(-?[\d.]+) LU", summ).group(1))
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
    peak = float(tp.group(1)) if tp and tp.group(1) != "-inf" else None
    sd = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "silencedetect=noise=-40dB:d=0.8", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", sd)]
    ends = [(float(a), float(b)) for a, b in re.findall(r"silence_end: (-?[\d.]+) \| silence_duration: ([\d.]+)", sd)]
    sil = []
    for i, s in enumerate(starts):
        e, d = ends[i] if i < len(ends) else (dur, dur - s)
        edge = s <= 0.05 or e >= dur - 0.05
        sil.append({"start": round(max(s, 0), 2), "dur": round(d, 2), "edge": edge})
    inner = [s for s in sil if not s["edge"]]
    found, level = seams(load(src))
    count = {k: sum(f["kind"] == k for f in found) for k in ("click", "cut", "burst")}
    res = {
        "codec": st.get("codec_name"), "sample_rate": st.get("sample_rate"), "channels": st.get("channels"),
        "duration_s": round(dur, 2), "lufs_i": lufs, "lra": lra, "true_peak_dbtp": peak,
        "silences": sil, "inner_long_silences": inner,
        "speech_level_db": level, "seams": found,
        "clicks": count["click"], "cuts": count["cut"], "bursts": count["burst"],
        "checks": {
            "duration_60_90": 60 <= dur <= 90,
            "no_inner_silence_over_0_8s": not inner,
            "peak_below_0dbtp": peak is not None and peak < 0,
            "no_clicks_cuts_bursts": not found,
        },
    }
    print(json.dumps(res, ensure_ascii=False))
    if out:
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if found:
        where = ", ".join(f"{f['kind']} {f['t']:.2f}s" for f in found[:12])
        print(f"FAIL: {count['click']} clicks, {count['cut']} cuts, {count['burst']} bursts ({where}). "
              "Rebuild the voice (speech.make / tools/voice_seams.py); never patch it by hand.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
