# -*- coding: utf-8 -*-
"""bitmart — THE FILE's sound (DIRECTION §4): the page's own documentary score, its sonic logo and soft air
on the transitions, mixed under the voice for Instagram. Made here, in code (no licence issue), to the owner's
rule: NO hit, boom, kick, click, tick, riser-impact or any percussive transient, anywhere. Every sound has a
soft attack (≥ 25 ms); the score breathes by its volume, never by drums.

The score: a low string-like pad (detuned, few harmonics, 0.7 s attacks) under a sparse FELT PIANO motif
(soft-attack notes, a warm decay) — a storyteller's score, not a trading desk's.

usage: build/asr/venv/bin/python -I COMMON/motion/story_audio.py direction/sound.json qc/voice_final.wav build/mix.wav
direction/sound.json = {
  "end": 64.0,                 # the video's end (window.END)
  "mood": 1,                   # DIRECTION §5: 0 mystery · 1 rise · 2 the fall · 3 wonder
  "air": [2.6, 6.1, 9.5],      # the transitions' times: a soft airy breath (sin² envelope, 16 dB under the voice)
  "lift": [[0, 2.6], [58.0, 61.2]],  # spans where the score opens up (the hook, the turn, the ask)
  "slate": 61.2                # the end slate: the sonic logo (once at 0.05 s, once here; ≥ 2.5 s before the end)
}
The voice to −14 LUFS, the score about 20 dB under it and ducked while the voice speaks, the mix −14 LUFS,
true peak under −1 dBTP; the score fades out over the last 2.2 s, nothing new starts in the last 2.5 s."""
import json
import os
import re
import subprocess
import sys

import numpy as np

SR = 48000
MOODS = {  # (bpm, chords as MIDI notes, pad brightness, the piano's notes per bar)
    0: (68, [(45, 52, 57, 60), (41, 48, 53, 57), (43, 50, 55, 58), (40, 47, 52, 56)], 0.20, 3),  # mystery: Am, F, Gm, E
    1: (88, [(48, 55, 60, 64), (45, 52, 57, 60), (41, 48, 53, 57), (43, 50, 55, 59)], 0.40, 4),  # rise: C, Am, F, G
    2: (62, [(38, 45, 50, 53), (34, 41, 46, 50), (36, 43, 48, 51), (33, 40, 45, 49)], 0.15, 2),  # the fall: Dm, Bb, Cm, A
    3: (80, [(41, 48, 53, 57), (43, 50, 55, 59), (41, 48, 53, 59), (36, 43, 48, 52)], 0.35, 4),  # wonder: F lydian
}


def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def smooth(x, ms):
    k = max(1, int(ms / 1000 * SR))
    return np.convolve(x, np.ones(k) / k, mode="same")


def add(buf, at, sig, g=1.0):
    i = int(max(0, at) * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * g


def adsr(n, a, r):
    e = np.ones(n)
    ai, ri = min(n, int(a * SR)), min(n, int(r * SR))
    if ai:
        e[:ai] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ai))  # raised-cosine attack: no click, no transient
    if ri:
        e[-ri:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, ri))
    return e


def felt(f, d, g=1.0):
    """A felt piano note: 28 ms attack (never a strike), a warm body (2nd/3rd harmonics fading faster), a
    long soft decay."""
    t = np.arange(int(d * SR)) / SR
    body = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3.5)
            + 0.12 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 6))
    return body * np.exp(-t * 1.6) * adsr(len(t), 0.028, 0.35) * g


def logo():
    """The bitmart motif: three felt notes — up a fourth, then the sixth above — ~1.8 s, 28 ms attacks."""
    out = np.zeros(int(2.1 * SR))
    for k, (m, at) in enumerate(((64, 0.0), (69, 0.18), (76, 0.40))):
        add(out, at, felt(note(m), 1.6, 0.55 - k * 0.07))
    return out


def lufs(x, tmp):
    write(tmp, x)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", tmp, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", err[err.rfind("Summary:"):]).group(1))


def write(path, x):
    ch = 1 if x.ndim == 1 else x.shape[1]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", "-", "-c:a", "pcm_f32le", path],
                   input=x.astype(np.float32).tobytes(), check=True)


def bed(S, n):
    bpm, chords, bright, per_bar = MOODS[int(S.get("mood", 0)) % 4]
    beat = 60 / bpm
    bar = 4 * beat
    t = np.arange(n) / SR
    L, R = np.zeros(n), np.zeros(n)
    k, t0 = 0, 0.0
    while t0 < n / SR:  # the pad: detuned saws softened (few harmonics), 0.6 s attack, overlapping bars
        ch = chords[k % len(chords)]
        m = int(min(bar + 0.8, n / SR - t0) * SR)
        if m <= 0:
            break
        tt = np.arange(m) / SR
        e = adsr(m, 0.6, 0.8)
        for mm in ch:
            f = note(mm)
            for side, det in ((L, -0.18), (R, 0.21)):
                sig = sum(np.sin(2 * np.pi * (f + det) * h * tt) / h ** (1.6 - bright) for h in (1, 2, 3))
                add(side, t0, sig * e, 0.035)
        sub = np.sin(2 * np.pi * note(ch[0] - 12) * tt) * adsr(m, 0.25, 0.6)  # the warm sub, legato
        add(L, t0, sub, 0.09)
        add(R, t0, sub, 0.09)
        # the felt piano: a few notes a bar from the chord, an octave up, unhurried (never on every beat)
        order = (3, 1, 2, 0) if k % 2 else (2, 3, 1, 0)
        for i in range(per_bar):
            at = t0 + i * bar / per_bar + (beat * 0.5 if i % 2 else 0)
            if at < n / SR - 2.5:
                sig = felt(note(ch[order[i % 4]] + 12), min(2.4, bar), 1.0)
                add(L if i % 2 else R, at, sig, 0.05)
                add(R if i % 2 else L, at + 0.012, sig, 0.02)
        t0 += bar
        k += 1
    pulse = 0.86 + 0.14 * (0.5 - 0.5 * np.cos(2 * np.pi * t / (2 * beat)))  # a slow breath of the volume: no transient
    lift = np.full(n, 0.72)
    for a, b in S.get("lift", []):
        lift = np.maximum(lift, np.interp(t, [a - 0.6, a, b, b + 0.6], [0.72, 1, 1, 0.72]))
    lvl = pulse * lift * np.interp(t, [0, 0.4, S["end"] - 2.2, S["end"]], [0, 1, 1, 0])
    return np.stack([L * lvl, R * lvl], 1)


def air(d=0.55):
    rng = np.random.default_rng(7)
    m = int(d * SR)
    x = np.arange(m) / SR
    nz = smooth(rng.standard_normal(m), 0.35)  # a gentle low-pass: air, not hiss
    return nz * np.sin(np.pi * x / d) ** 2 / (np.abs(nz).max() + 1e-9)


def main() -> None:
    S = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[3]
    tmp = out + ".tmp.wav"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[2], "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    voice = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    n = int(round(S["end"] * SR))
    v = np.zeros(n)
    v[: min(n, len(voice))] = voice[:n]
    v *= 10 ** ((-14.0 - lufs(v, tmp)) / 20)
    mus = bed(S, n)
    mus *= 10 ** ((-34.0 - lufs(mus, tmp)) / 20)
    act = np.clip((10 * np.log10(smooth(v ** 2, 50) + 1e-12) + 45) / 15, 0, 1)
    mus *= (1 - 0.35 * smooth(act, 150))[:, None]
    fx = np.zeros(n)
    last_ok = S["end"] - 2.5  # nothing new starts in the last 2.5 s
    for at in S.get("air", []):
        if at - 0.27 < last_ok:
            add(fx, at - 0.27, air(), 1.0)
    for at in (0.05, S.get("slate")):
        if at is not None and at < last_ok:
            add(fx, at, logo(), 1.0)
    if np.abs(fx).max() > 0:
        fx *= 10 ** ((-30.0 - lufs(fx, tmp)) / 20)  # 16 dB under the voice
    mix = mus + (v + fx)[:, None]
    write(tmp, mix)
    g = -14.0 - lufs(mix, tmp)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
                    f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.87:attack=5:release=80:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", out], check=True)
    os.remove(tmp)
    print("wrote", out, "mood", S.get("mood", 0))


if __name__ == "__main__":
    main()
