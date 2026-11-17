# -*- coding: utf-8 -*-
"""ipoxxo reel sound (KIT/motion/sound.py): our own music bed (no licence issue), soft swishes on the designed
transitions, the final voice, mixed for Instagram.

usage (in the day's folder, after `reel.py --timeline`):
  PY -I motion/sound.py            -> build/mix.wav (+ build/voice_track.wav, the narration on the timeline)
Reads build/timeline.json (END, the mood 0..3, the shots and their transitions, the open question and its
payoff, the sponsor line) and qc/voice_final.wav.

The bed follows the edit: calm under the hook, layers come in as the question opens, the most energy just
before the payoff, then a short drop ON the payoff (a pattern interrupt for the ear), warm under the sponsor,
and a fade over the last 2.4 s: nothing new starts in the last 2 s. NO hits, ever (DIRECTION §4): no boom,
impact, sub-drop or percussive cue; the swishes are airy and at least 12 dB under the voice.
Moods (DIRECTION §5): 0 dark cinematic pulse · 1 upbeat electronic · 2 lo-fi chill · 3 epic hybrid.
Levels: voice -16 LUFS, the bed 16 dB under it and ducked 3.5 dB more while the voice speaks, the whole
mix -14 LUFS, true peak under -1 dBTP (a limiter at 4x oversampling). Then check it:
  build/asr/venv/bin/python -I tools/audio_qc.py build/mix.wav qc/mix.audioqc.json   (0 clicks, cuts, bursts)
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()
SR = 48000
MOODS = {
    0: {"bpm": 96, "prog": [(50, 53, 57, 62), (46, 50, 53, 58), (41, 45, 48, 53), (48, 52, 55, 60)], "arp": 4, "bright": .6},
    1: {"bpm": 112, "prog": [(53, 57, 60, 65), (48, 52, 55, 60), (50, 53, 57, 62), (46, 50, 53, 58)], "arp": 2, "bright": 1.0},
    2: {"bpm": 82, "prog": [(51, 55, 58, 62), (48, 51, 55, 58), (53, 56, 60, 63), (46, 50, 53, 56)], "arp": 2, "bright": .5},
    3: {"bpm": 90, "prog": [(48, 51, 55, 60), (44, 48, 51, 56), (51, 55, 58, 63), (46, 50, 53, 58)], "arp": 2, "bright": .8},
}


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def write(path, x, codec="pcm_f32le"):
    ch = 1 if x.ndim == 1 else x.shape[1]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", "-", "-c:a", codec, path],
                   input=x.astype(np.float32).tobytes(), check=True)


def lufs_of(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = err[err.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s).group(1))


def lufs(x):
    p = os.path.join(ROOT, "build", "_probe.wav")
    write(p, x)
    v = lufs_of(p)[0]
    os.remove(p)
    return v


def add(buf, t, sig, g=1.0):
    i = int(round(t * SR))
    if i >= len(buf) or i + len(sig) <= 0:
        return
    a, b = max(0, i), min(len(buf), i + len(sig))
    buf[a:b] += sig[a - i:b - i] * g


def env(n, att, rel):
    e = np.ones(n)
    a, r = min(int(att * SR), n), min(int(rel * SR), n)
    if a:
        e[:a] = np.linspace(0, 1, a) ** 1.5
    if r:
        e[-r:] *= np.linspace(1, 0, r) ** 1.5
    return e


def pad(freqs, d, bright):
    t = np.arange(int(d * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for det in (-.11, .11):
            ph = 2 * np.pi * f * (1 + det / 100) * t
            s += np.sin(ph) + .3 * bright * np.sin(2 * ph) + .12 * bright * np.sin(3 * ph)
    return s / (2.6 * len(freqs)) * env(len(t), .8, 1.1)


def pluck(f, d=.42, bright=1.0):
    t = np.arange(int(d * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + .3 * bright * np.sin(4 * np.pi * f * t) * np.exp(-t * 9)
    return s * np.exp(-t * 7.5) * np.minimum(1, t * 400)


def bass(f, d):
    t = np.arange(int(d * SR)) / SR
    return (np.sin(2 * np.pi * f * t) + .25 * np.sin(4 * np.pi * f * t)) * env(len(t), .015, .12) * np.exp(-t * 1.6)


def hat(seed):
    r = np.random.default_rng(seed)
    n = int(.045 * SR)
    x = np.diff(r.standard_normal(n + 1))
    return x * np.exp(-np.arange(n) / SR * 95) * .18


def noise(d, seed, smooth=24):
    r = np.random.default_rng(seed)
    x = r.standard_normal(int(d * SR))
    k = np.ones(smooth) / smooth
    return np.convolve(x, k, mode="same")


def swish(d=.38, seed=3):
    x = noise(d, seed, 10) - noise(d, seed + 1, 60)  # an airy band, no low end
    tt = np.linspace(0, 1, len(x))
    return x * np.sin(np.pi * tt) ** 2.2


def energy_curve(tl, n):
    tt = np.arange(n) / SR
    end = tl["end"]
    gap = tl.get("gap") or {}
    sp = tl.get("sponsor") or {"s": end - 4, "e": end - 2.4}
    g_at = float(gap.get("at", min(6.0, end * .15)))
    pay = float(gap.get("close", sp["s"] - 6))
    xs = [0, max(.1, g_at - .5), g_at + .5, pay - .9, pay - .05, pay + .05, pay + .75, sp["s"] - .2, sp["s"] + .3, end - 2.4, end]
    ys = [.35, .45, .7, 1.0, 1.0, .22, .9, .85, .6, .55, 0.0]
    order = np.argsort(xs)
    return np.interp(tt, np.array(xs)[order], np.array(ys)[order]), pay


def music(tl, n):
    m = MOODS.get(int(tl.get("mood") or 0) % 4)
    beat = 60 / m["bpm"]
    bar = 4 * beat
    end = tl["end"]
    stop = end - 2.0  # nothing new starts in the last 2 s
    L, R = np.zeros(n), np.zeros(n)
    e, pay = energy_curve(tl, n)
    at = lambda t: float(e[min(n - 1, max(0, int(t * SR)))])
    k, t0 = 0, 0.0
    while t0 < stop:
        ch = m["prog"][k % 4]
        d = min(bar + 1.0, end - t0)
        p = pad([hz(x) for x in ch], d, m["bright"])
        add(L, t0, p, .55)
        add(R, t0, p, .55)
        if at(t0 + .1) >= .5:
            for b in range(4):
                tb = t0 + b * beat
                if tb > stop:
                    break
                g = .55 * min(1, (at(tb) - .45) * 4)
                for sub in ((0, .5) if m["bpm"] < 100 else (0,)):
                    bs = bass(hz(ch[0] - 12), beat * .48)
                    add(L, tb + sub * beat, bs, g)
                    add(R, tb + sub * beat, bs, g)
        if at(t0 + .1) >= .6:
            notes = [ch[1] + 12, ch[3] + 12, ch[2] + 12, ch[3] + 24, ch[2] + 12, ch[1] + 24, ch[0] + 24, ch[3] + 12]
            steps = 4 * m["arp"]
            for j in range(steps):
                tt = t0 + j * beat / m["arp"]
                if tt > stop:
                    break
                g = .26 * min(1, (at(tt) - .55) * 3) * (1 if j % 2 == 0 else .7)
                pl = pluck(hz(notes[j % len(notes)]), .42, m["bright"])
                pan = .3 if j % 2 else -.3
                add(L, tt, pl, g * (1 - pan))
                add(R, tt, pl, g * (1 + pan))
        if at(t0 + .1) >= .75:
            for b in range(4):
                tt = t0 + b * beat + beat / 2
                if tt > stop:
                    break
                h = hat(int(tt * 1000))
                add(L, tt, h, .5)
                add(R, tt, h, .65)
        k += 1
        t0 += bar
    # a soft swell into the payoff (air, no hit) and the drop on it
    rs = noise(1.6, 11, 30) * np.linspace(0, 1, int(1.6 * SR)) ** 2.5
    rs[-int(.12 * SR):] *= np.linspace(1, 0, int(.12 * SR))
    add(L, pay - 1.6, rs, .05)
    add(R, pay - 1.6, rs, .05)
    level = .35 + .65 * e
    L *= level
    R *= level
    return np.stack([L, R], axis=1)


def swishes(tl, n, sponsor_s):
    out = np.zeros((n, 2))
    for k, s in enumerate(tl["shots"]):
        if s["at"] < .4 or s["tr"] in ("cut", "match") or s["at"] > sponsor_s - .3:
            continue
        sw = swish(.4, 30 + k)
        pan = .25 if k % 2 else -.25
        add(out[:, 0], s["at"] - .22, sw, 1 - pan)
        add(out[:, 1], s["at"] - .22, sw, 1 + pan)
    return out


def main():
    tl = json.load(open(os.path.join(ROOT, "build", "timeline.json"), encoding="utf-8"))
    end = float(tl["end"])
    n = int(round(end * SR))
    v = load(os.path.join(ROOT, "qc", "voice_final.wav"))[:n]
    v = np.pad(v, (0, n - len(v)))
    v *= 10 ** ((-16.0 - lufs(v)) / 20)
    write(os.path.join(ROOT, "build", "voice_track.wav"), v)
    sp = (tl.get("sponsor") or {}).get("s", end)
    mus = music(tl, n)
    mus *= 10 ** ((-16.0 - 16.0 - lufs(mus)) / 20)
    sw = swishes(tl, n, sp)
    if np.abs(sw).max() > 0:
        sw *= 10 ** ((-16.0 - 24.0 - lufs(sw)) / 20) if lufs(sw) > -70 else 0
    h = int(.05 * SR)
    pw = np.convolve(v ** 2, np.ones(h) / h, mode="same")
    act = np.clip((10 * np.log10(pw + 1e-12) + 45) / 15, 0, 1)
    act = np.convolve(act, np.ones(int(.2 * SR)) / int(.2 * SR), mode="same")
    duck = 10 ** (-3.5 * act / 20)
    fade = np.ones(n)
    f = int(2.4 * SR)
    fade[-f:] = np.linspace(1, 0, f) ** 1.6
    mix = (mus * duck[:, None] + sw) * fade[:, None] + v[:, None]
    tmp = os.path.join(ROOT, "build", "mix.pre.wav")
    write(tmp, mix)
    g = -14.0 - lufs_of(tmp)[0]
    out = os.path.join(ROOT, "build", "mix.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
                    f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.87:attack=2:release=60:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", out], check=True)
    os.remove(tmp)
    lu, tp = lufs_of(out)
    print(json.dumps({"mix": "build/mix.wav", "lufs": lu, "true_peak": tp, "dur": round(end, 2),
                      "mood": int(tl.get("mood") or 0), "swishes": sum(1 for s in tl["shots"] if s["tr"] not in ("cut", "match"))}))


if __name__ == "__main__":
    sys.exit(main())
