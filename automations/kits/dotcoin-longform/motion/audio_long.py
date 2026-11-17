# -*- coding: utf-8 -*-
"""DotCoin long video sound: our own editorial bed (no licence issue) under the chapter voices.

Music: 90 BPM, two progressions that alternate by chapter (Dm9-Bbmaj7-Fmaj7-C6 / Fmaj7-Am7-Bbmaj7-C), a soft pad,
muted plucks, a round sub bass, a soft kick and light hats; each chapter card gets a swell and a soft bell; the
end card fades the bed out (nothing new in the last 2.5 s). The bed sits about 22 dB under the voice and is ducked
a little more while the voice speaks. Voice -16 LUFS, the whole mix -14 LUFS, true peak under -1 dBTP.

The voices are whole chapter files placed at their chapter's offset (never cut or spliced here).
usage: PY -I motion/audio_long.py  -> build/mix.wav (+ build/voice_track.wav)
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 48000
BPM = 90
BEAT = 60 / BPM
BAR = 4 * BEAT
PROG = [[(50, 53, 57, 60, 64), (46, 50, 53, 57, 62), (41, 45, 48, 52, 57), (48, 52, 55, 57, 62)],
        [(41, 45, 48, 52, 57), (45, 48, 52, 55, 60), (46, 50, 53, 57, 62), (48, 52, 55, 60, 64)]]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def write(path, x, codec="pcm_f32le"):
    ch = 1 if x.ndim == 1 else x.shape[1]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", "-", "-c:a", codec, path],
                   input=x.astype(np.float32).tobytes(), check=True)


def lufs_of(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = err[err.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s).group(1)


def lufs(x):
    p = os.path.join(ROOT, "build/_probe.wav")
    write(p, x)
    v = lufs_of(p)[0]
    os.remove(p)
    return v


def add(buf, t, sig, g=1.0):
    i = int(t * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    a, b = max(0, i), min(len(buf), i + len(sig))
    buf[a:b] += sig[a - i:b - i] * g


def env(n, att, rel):
    e = np.ones(n, dtype=np.float32)
    a, r = min(int(att * SR), n), min(int(rel * SR), n)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def pluck(f, d=0.55):
    t = np.arange(int(d * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    return (s * np.exp(-t * 8) * np.minimum(1, t * 300)).astype(np.float32)


def pad(freqs, d):
    t = np.arange(int(d * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for det in (-0.12, 0.12):
            s += np.sin(2 * np.pi * f * (1 + det / 100) * t + det)
    return (s / (2 * len(freqs)) * env(len(t), 0.9, 1.0)).astype(np.float32)


def bass(f, d):
    t = np.arange(int(d * SR)) / SR
    return (np.sin(2 * np.pi * f * t) * env(len(t), 0.02, 0.3) * np.exp(-t * 0.8)).astype(np.float32)


def kick():
    t = np.arange(int(0.35 * SR)) / SR
    f = 50 + 70 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)).astype(np.float32)


def hat(seed):
    r = np.random.default_rng(seed)
    n = int(0.05 * SR)
    x = r.standard_normal(n).astype(np.float32)
    x = np.diff(x, prepend=0)
    return x * np.exp(-np.arange(n) / SR * 90).astype(np.float32) * 0.25


def tick(f):
    t = np.arange(int(0.06 * SR)) / SR
    return (np.sin(2 * np.pi * f * t) * np.exp(-t * 70) * np.minimum(1, t * 2000)).astype(np.float32)


def bell(f):
    t = np.arange(int(2.2 * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3)
    return (s * np.exp(-t * 2.2) * np.minimum(1, t * 200)).astype(np.float32)


def swell(d=1.6):
    r = np.random.default_rng(7)
    n = int(d * SR)
    x = r.standard_normal(n).astype(np.float32)
    k = 60
    x = np.convolve(x, np.ones(k) / k, mode="same").astype(np.float32)  # soft noise
    e = np.linspace(0, 1, n) ** 2
    e[-int(0.25 * SR):] *= np.linspace(1, 0, int(0.25 * SR))
    return x * e.astype(np.float32) * 3


def music(tl, n):
    L, R = np.zeros(n, dtype=np.float32), np.zeros(n, dtype=np.float32)
    total = n / SR
    off = 0.0
    for c in tl:
        prog = PROG[c["id"] % 2]
        start, end = off, off + c["end"]
        k, t0 = 0, start
        last_chapter = c["id"] == tl[-1]["id"]
        stop = end - (3.2 if last_chapter else 0)
        while t0 < stop - 0.2:
            ch = prog[k % 4]
            d = min(BAR + 0.9, stop - t0 + 0.9)
            p = pad([hz(m) for m in ch[:4]], d) * 0.55
            add(L, t0, p)
            add(R, t0, p)
            add(L, t0, bass(hz(ch[0] - 12), BAR) * 0.7)
            add(R, t0, bass(hz(ch[0] - 12), BAR) * 0.7)
            arp = [ch[1] + 12, ch[3] + 12, ch[2] + 12, ch[4] + 12, ch[2] + 12, ch[3] + 12, ch[1] + 12, ch[4]]
            for j, m in enumerate(arp):
                tt = t0 + j * BEAT / 2
                if tt > stop:
                    break
                pl = pluck(hz(m)) * (0.32 if j % 2 == 0 else 0.22)
                pan = 0.35 if j % 2 else -0.35
                add(L, tt, pl * (1 - pan))
                add(R, tt, pl * (1 + pan))
            if c["id"] not in (0,) or t0 > start + 6:
                for b in range(4):
                    tt = t0 + b * BEAT
                    if tt > stop:
                        break
                    if b in (0, 2):
                        add(L, tt, kick() * 0.5)
                        add(R, tt, kick() * 0.5)
                    hh = hat(int(tt * 100))
                    add(L, tt + BEAT / 2, hh * 0.6)
                    add(R, tt + BEAT / 2, hh * 0.8)
            k += 1
            t0 += BAR
        if c["id"] > 0:  # the chapter card: a swell into it and a soft bell on it
            sw = swell()
            add(L, start - 1.4, sw * 0.5)
            add(R, start - 1.4, sw * 0.5)
            b = bell(hz(prog[0][2] + 24)) * 0.5
            add(L, start + 0.1, b)
            add(R, start + 0.1, b)
        # a soft tick as each headline lands (not in the last 2.5 s)
        for snt in c["sent"]:
            tt = start + snt["s"]
            if snt.get("h") and tt < total - 2.6:
                tk = tick(1400 if c["id"] % 2 else 1250) * 0.18
                add(L, tt, tk * 0.9)
                add(R, tt, tk)
        off = end
    # the end: fade over the last 3 s, nothing new in the last 2.5 s
    f = int(3.0 * SR)
    fade = np.linspace(1, 0, f, dtype=np.float32) ** 1.5
    L[-f:] *= fade
    R[-f:] *= fade
    return np.stack([L, R], axis=1)


def main():
    tl = json.load(open(os.path.join(ROOT, "build/timeline.json"), encoding="utf-8"))["chapters"]
    total = sum(c["end"] for c in tl)
    n = int(round(total * SR))
    v = np.zeros(n, dtype=np.float32)
    off = 0.0
    for c in tl:
        vp = os.path.join(ROOT, f"voice/ch{c['id']:02d}.wav")
        if os.path.exists(vp):
            add(v, off + c["vo"], load(vp))
        else:
            print(f"no voice for chapter {c['id']}", file=sys.stderr)
        off += c["end"]
    v *= 10 ** ((-16.0 - lufs(v)) / 20)
    write(os.path.join(ROOT, "build/voice_track.wav"), v)
    mus = music(tl, n)
    mus *= 10 ** ((-16.0 - 22.0 - lufs(mus)) / 20)
    h = int(0.05 * SR)
    pw = np.convolve(v.astype(np.float64) ** 2, np.ones(h) / h, mode="same")
    act = np.clip((10 * np.log10(pw + 1e-12) + 45) / 15, 0, 1)
    act = np.convolve(act, np.ones(int(0.15 * SR)) / int(0.15 * SR), mode="same").astype(np.float32)
    mus *= (1 - 0.4 * act)[:, None]
    mix = mus + v[:, None]
    tmp = os.path.join(ROOT, "build/mix.pre.wav")
    write(tmp, mix)
    g = -14.0 - lufs_of(tmp)[0]
    out = os.path.join(ROOT, "build/mix.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
                    f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.87:attack=2:release=60:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", out], check=True)
    os.remove(tmp)
    lu, tp = lufs_of(out)
    print(json.dumps({"lufs": lu, "true_peak": tp, "dur": round(total, 2)}))


if __name__ == "__main__":
    main()
