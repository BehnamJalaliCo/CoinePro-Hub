# -*- coding: utf-8 -*-
"""Zarib100x — THE DESK's sound (DIRECTION §4): the page's own music bed, its sonic logo and soft air on the
transitions, mixed under the voice for Instagram. Made here, in code (no licence issue), and made to the
owner's rule: NO hit, boom, kick, click, tick or any percussive transient, anywhere. Every sound has a soft
attack (≥ 25 ms); the bed pulses by its volume, never by drums.

usage: build/asr/venv/bin/python -I COMMON/motion/desk_audio.py direction/sound.json qc/voice_final.wav build/mix.wav
direction/sound.json = {
  "end": 64.0,                 # the video's end (window.END)
  "mood": 2,                   # DIRECTION §5: 0 late session · 1 opening bell · 2 risk-off · 3 momentum
  "air": [2.6, 6.1, 9.5],      # the transitions' times: a soft airy swish (sin² envelope, 14 dB under the voice)
  "lift": [[0, 2.6], [58.0, 61.2]],  # spans where the bed opens up (the hook, the call to action)
  "slate": 61.2                # the end slate: the sonic logo (once at 0.05 s, once here; ≥ 2.5 s before the end)
}
The voice to −14 LUFS, the bed about 20 dB under it and ducked while the voice speaks, the mix −14 LUFS,
true peak under −1 dBTP; the bed fades out over the last 2.2 s, nothing new starts in the last 2.5 s.
Check afterwards: COMMON/DIRECTION.md §6 (the tail, every sentence boundary, audio_qc on the voice)."""
import json
import os
import re
import subprocess
import sys

import numpy as np

SR = 48000
MOODS = {  # (bpm, chord roots/qualities as MIDI triads, pad brightness, arp on?)
    0: (84, [(50, 53, 57, 60), (46, 50, 53, 57), (43, 46, 50, 53), (45, 48, 52, 55)], 0.25, False),  # late session: Dm9 colour
    1: (100, [(48, 52, 55, 59), (45, 48, 52, 55), (41, 45, 48, 52), (43, 47, 50, 55)], 0.45, True),  # opening bell: Cmaj7
    2: (76, [(45, 48, 52, 55), (41, 45, 48, 52), (40, 43, 47, 50), (38, 41, 45, 48)], 0.18, False),  # risk-off: Am7, sparse
    3: (108, [(52, 55, 59, 62), (48, 52, 55, 59), (50, 53, 57, 60), (47, 50, 54, 57)], 0.40, True),  # momentum: Em9 drive
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


def bell(f, d, g=1.0):
    """A soft FM bell (the sonic logo's voice): 30 ms attack, long glassy decay."""
    t = np.arange(int(d * SR)) / SR
    mod = np.sin(2 * np.pi * f * 3.5 * t) * 1.2 * np.exp(-t * 3)
    return np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 2.2) * adsr(len(t), 0.03, 0.3) * g


def logo():
    """The Zarib100x motif: three rising notes (a fifth and an octave), each 30 ms attack, ~1.6 s."""
    out = np.zeros(int(1.9 * SR))
    for k, (m, at) in enumerate(((62, 0.0), (69, 0.16), (74, 0.32))):
        add(out, at, bell(note(m), 1.5, 0.5 - k * 0.08))
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
    bpm, chords, bright, arp = MOODS[int(S.get("mood", 0)) % 4]
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
        if arp:  # a soft arpeggio on eighths: 25 ms attacks, short glassy decay (never a tick)
            for i in range(8):
                at = t0 + i * beat / 2
                if at < n / SR:
                    f = note(ch[i % len(ch)] + 12)
                    d = int(0.38 * SR)
                    x = np.arange(d) / SR
                    s = np.sin(2 * np.pi * f * x) * np.exp(-x * 7) * adsr(d, 0.025, 0.08)
                    add(L if i % 2 else R, at, s, 0.025)
        t0 += bar
        k += 1
    pulse = 0.78 + 0.22 * (0.5 - 0.5 * np.cos(2 * np.pi * t / beat))  # the volume pulse on the beat: no transient
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
