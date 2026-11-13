#!/usr/bin/env python3
"""Build the final narration: clean the take, swap its spoken slogan for the fixed, checked slogan clip.

Usage: build/asr/venv/bin/python -I tools/assemble_voice.py MAIN_AUDIO MAIN_ASR.json SLOGAN_AUDIO OUT.wav [OUT.json]

Why (QC findings, 2026-11-13): every file from the speech path starts with a ~25 ms click and ends with a ~170 ms
burst of broadband noise after the last word, and the decoded Opus goes up to +4 dBFS. So this tool
- works in 32-bit float end to end (nothing is clipped before the gain is set),
- cuts the head click and the tail noise of both clips (speech-envelope based, ASR only to find the slogan),
- cuts the take inside the silence before its own slogan («اول …», last occurrence) and keeps the take's own pause,
- matches the slogan clip's speech level to the slogan it replaces, so the end does not jump,
- adds a clean lead (0.25 s) and tail (0.60 s) of digital silence, short fades at every joint (no clicks),
- sets the whole to -16 LUFS with one linear gain and a gentle limiter only if the true peak would pass -1.5 dBTP.
Writes OUT.wav (48 kHz, mono, 24-bit) and a JSON with every cut point and level.
"""
import json
import re
import subprocess
import sys

import numpy as np

SR = 48000
HOP = 0.01
LEAD, TAIL = 0.25, 0.60


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def env_db(x):
    h = int(HOP * SR)
    n = len(x) // h
    fr = x[: n * h].reshape(n, h)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)


def head_onset(e, thr=-40.0, sustain=0.08):
    """First sustained speech frame, skipping a short loud blip at the very start (the click)."""
    i0 = 0
    quiet = np.flatnonzero(e[:30] < -50)
    if quiet.size and quiet[0] <= 8:  # loud for at most 80 ms, then quiet: that is the click, not speech
        i0 = int(quiet[0])
    need = int(sustain / HOP)
    for i in range(i0, len(e) - need):
        if e[i] > thr and e[i:i + need].mean() > thr:
            return i, i0
    return i0, i0


def tail_end(e, thr=-45.0, junk_max=0.40, gap_min=0.08):
    """End of the last speech, ignoring a short loud burst after a quiet gap at the very end (the noise)."""
    n = len(e)
    k = n - 1
    while k >= 0 and e[k] > -40:
        k -= 1
    junk = None
    tail_len = (n - 1 - k) * HOP
    if 0 < tail_len <= junk_max:
        g = k
        while g >= 0 and e[g] < -55:
            g -= 1
        if (k - g) * HOP >= gap_min:
            junk = (k + 1) * HOP
            n = g + 1
    idx = np.flatnonzero(e[:n] > thr)
    end = (idx[-1] + 1) if idx.size else n
    return end, junk


def gated_rms_db(x):
    e = env_db(x)
    top = e.max()
    sel = e[e > top - 30]
    return float(10 * np.log10(np.mean(10 ** (sel / 10))))


def fade(x, fin=0.01, fout=0.04):
    y = x.copy()
    a, b = int(fin * SR), int(fout * SR)
    if a:
        y[:a] *= np.linspace(0, 1, a)
    if b:
        y[-b:] *= np.linspace(1, 0, b)
    return y


def ffmpeg_stats(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = err[err.rfind("Summary:"):]
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s)
    return lufs, (float(tp.group(1)) if tp and tp.group(1) != "-inf" else None)


def write_wav(path, x, fmt="pcm_f32le"):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", fmt, "-y", path],
                   input=x.astype(np.float32).tobytes(), check=True)


def main() -> None:
    main_audio, asr_json, slogan_audio, out = sys.argv[1:5]
    out_json = sys.argv[5] if len(sys.argv) > 5 else None
    m, s = load(main_audio), load(slogan_audio)
    em, es = env_db(m), env_db(s)

    # 1) take: head click and onset
    m_on, m_click = head_onset(em)
    m_start = max(m_on * HOP - 0.08, m_click * HOP)

    # 2) take: the silence before its own slogan («اول», last occurrence)
    words = json.load(open(asr_json, encoding="utf-8"))["words"]
    idx = max(i for i, w in enumerate(words) if re.sub(r"[^؀-ۿ]", "", w["w"]).startswith("اول"))
    prev_end, sl_start = words[idx - 1]["e"], words[idx]["s"]
    # Whisper glues word edges, so: first quiet run (< -50 dB, >= 0.1 s) that starts near the end of the
    # previous word; the pause lasts until the slogan's speech really starts (a breath in between is dropped).
    lo, hi = int((prev_end - 0.25) / HOP), int((sl_start + 0.30) / HOP)
    gap_i = None
    for i in range(max(lo, 0), min(hi, len(em) - 10)):
        if (em[i:i + 10] < -50).all():
            gap_i = i
            break
    if gap_i is None:
        raise SystemExit("no silence found before the slogan")
    j = gap_i
    while j < len(em) - 8 and not (em[j] > -40 and em[j:j + 8].mean() > -40):
        j += 1
    gap_start, gap_len = gap_i * HOP, (j - gap_i) * HOP
    cut = gap_start + 0.06
    pause = float(np.clip(gap_len, 0.45, 0.90))

    # 3) take's own slogan (for the level match) up to its speech end, ignoring the tail noise
    m_end_i, m_junk = tail_end(em)
    own_slogan = m[int((gap_start + gap_len) * SR): int(m_end_i * HOP * SR)]

    # 4) slogan clip: head click, onset, speech end before the tail noise
    s_on, s_click = head_onset(es)
    s_end_i, s_junk = tail_end(es)
    s_a = max(s_on * HOP - 0.03, s_click * HOP)
    s_b = min(s_end_i * HOP + 0.08, (s_junk - 0.02) if s_junk else len(s) / SR)
    clip = s[int(s_a * SR): int(s_b * SR)]
    match_db = gated_rms_db(own_slogan) - gated_rms_db(clip)
    clip = clip * 10 ** (match_db / 20)

    # 5) join with fades and digital silence
    body = fade(m[int(m_start * SR): int(cut * SR)], fin=0.01, fout=0.03)
    gap = max(pause - 0.06 - 0.03, 0.2)
    y = np.concatenate([np.zeros(int(LEAD * SR)), body, np.zeros(int(gap * SR)), fade(clip, 0.01, 0.05),
                        np.zeros(int(TAIL * SR))])

    # 6) loudness: one linear gain to -16 LUFS, limiter only if needed
    tmp = out + ".f32.wav"
    write_wav(tmp, y)
    lufs0, _ = ffmpeg_stats(tmp)
    gain = -16.0 - lufs0
    y = y * 10 ** (gain / 20)
    write_wav(tmp, y)
    lufs1, tp1 = ffmpeg_stats(tmp)
    limited = tp1 is not None and tp1 > -1.5
    # true-peak-aware: limit at 4x oversampling, so inter-sample peaks stay under about -1.5 dBTP too
    af = ("aresample=192000,alimiter=limit=0.84:attack=3:release=60:level=disabled,aresample=48000,"
          if limited else "")
    subprocess.run(["ffmpeg", "-v", "error", "-i", tmp, "-af", af + "aformat=sample_fmts=s32:channel_layouts=mono",
                    "-c:a", "pcm_s24le", "-ar", str(SR), "-y", out], check=True)
    import os
    os.remove(tmp)
    lufs2, tp2 = ffmpeg_stats(out)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                               capture_output=True, text=True).stdout)
    res = {
        "take": {"head_click_s": round(m_click * HOP, 2), "speech_onset_s": round(m_on * HOP, 2),
                 "start_cut_s": round(m_start, 3), "slogan_word_at": sl_start, "gap_start_s": round(gap_start, 2),
                 "gap_len_s": round(gap_len, 2), "cut_s": round(cut, 3), "tail_noise_at_s": m_junk},
        "slogan": {"head_click_s": round(s_click * HOP, 2), "speech_onset_s": round(s_on * HOP, 2),
                   "from_s": round(s_a, 3), "to_s": round(s_b, 3), "tail_noise_at_s": s_junk,
                   "level_match_db": round(match_db, 2)},
        "pause_before_slogan_s": round(pause, 2), "lead_s": LEAD, "tail_s": TAIL,
        "gain_db": round(gain, 2), "limiter": limited, "lufs": lufs2, "true_peak_dbtp": tp2,
        "out_duration_s": round(dur, 2), "slogan_starts_at_s": round(LEAD + (cut - m_start) + gap, 2),
    }
    print(json.dumps(res, ensure_ascii=False))
    if out_json:
        json.dump(res, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
