# -*- coding: utf-8 -*-
"""@behnamjalali.tech LUMEN sound (KIT/motion/sound.py): the page's own sonic identity, made here in code (no
licence issue, never another page's bed): glassy FM bells, a warm sub pulse, an airy pad, soft UI blips on the
edit's beats, low airy whooshes on the designed transitions, the boot chime on frame 0 and the resolve chord under
the end card. Then the final voice, mixed for Instagram / YouTube.

usage (in the day's folder, after `reel.py --timeline`):
  PY -I KIT/motion/sound.py             -> build/mix.wav (+ build/voice_track.wav, the narration on the timeline)
Reads build/timeline.json (END, mood 0..3, the shots with their transitions, the beats, the gap's payoff, the
comment card, the end card) and qc/voice_final.wav.

The bed follows the edit: sparse under the hook, the pulse comes in with the open question, the most energy just
before the payoff, a short breath ON the payoff, warm under the call to action, the resolve chord on the end card;
nothing new starts in the last 1.6 s. Moods (DIRECTION §6): 0 night lab (88 bpm, minor) · 1 bright launch (108 bpm)
· 2 deep focus (80 bpm, sparse) · 3 breaking (100 bpm, tense, for the breaking-news kit).
Safety for the QC (tools/audio_qc.py): every sound has an attack of 6 ms or more and a smooth release (no click);
whooshes are low-passed under 2.5 kHz and 18 dB under the voice (no "burst"); no hit, no boom, no sub drop.
Levels: voice -16 LUFS, the bed 15 dB under it and ducked 4 dB more while the voice speaks, the UI layer 22 dB
under the voice, the whole mix -14 LUFS, true peak under -1 dBTP (a 4x oversampled limiter). Then check it:
  build/asr/venv/bin/python -I tools/audio_qc.py build/mix.wav qc/mix.audioqc.json   (0 clicks, cuts, bursts)
A long video (motion/WIDE) runs the same, chapter by chapter; `--no-voice` makes the bed alone (a chapter's music
under a voice joined later).
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()
SR = 48000
# chords as MIDI notes (root, third, fifth, colour); each mood its own harmonic world
MOODS = {
    0: {"bpm": 88, "prog": [(45, 52, 57, 60), (41, 48, 53, 57), (48, 55, 60, 64), (43, 50, 55, 59)], "bell": .9, "pulse": .8},
    1: {"bpm": 108, "prog": [(48, 55, 60, 64), (45, 52, 57, 60), (41, 48, 53, 57), (43, 50, 55, 62)], "bell": 1.0, "pulse": 1.0},
    2: {"bpm": 80, "prog": [(50, 57, 62, 65), (46, 53, 58, 62), (43, 50, 55, 58), (45, 52, 57, 60)], "bell": .6, "pulse": .55},
    3: {"bpm": 100, "prog": [(40, 47, 52, 55), (40, 47, 52, 58), (41, 48, 53, 56), (43, 50, 55, 58)], "bell": .8, "pulse": 1.1},
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
    """A smooth envelope: raised-cosine attack and release (never a step: the QC hears steps as clicks)."""
    e = np.ones(n)
    a, r = min(max(int(att * SR), int(.006 * SR)), n), min(max(int(rel * SR), int(.01 * SR)), n)
    e[:a] = .5 - .5 * np.cos(np.linspace(0, np.pi, a))
    e[-r:] *= .5 + .5 * np.cos(np.linspace(0, np.pi, r))
    return e


def lowpass(x, cut):
    """A gentle one-pole low-pass, run twice (12 dB/oct)."""
    a = np.exp(-2 * np.pi * cut / SR)
    for _ in range(2):
        y = np.empty_like(x)
        acc = 0.0
        for k in range(0, len(x), 4096):  # (blocks keep it quick enough in numpy)
            seg = x[k:k + 4096]
            out = np.empty_like(seg)
            for i, v in enumerate(seg):
                acc = (1 - a) * v + a * acc
                out[i] = acc
            y[k:k + 4096] = out
        x = y
    return x


def smooth_noise(d, seed, k):
    r = np.random.default_rng(seed)
    x = r.standard_normal(int(d * SR) + k)
    return np.convolve(x, np.ones(k) / k, mode="valid")[:int(d * SR)]


def bell(f, d=1.4, bright=1.0):
    """A glassy FM bell: a sine carrier, a 3.5x modulator whose index decays."""
    t = np.arange(int(d * SR)) / SR
    idx = 2.2 * bright * np.exp(-t * 6)
    s = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 3.5 * t))
    return s * np.exp(-t * 2.6) * env(len(t), .008, .25)


def pad(freqs, d, warm=1.0):
    t = np.arange(int(d * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for det in (-.14, 0, .14):
            ph = 2 * np.pi * f * (1 + det / 100) * t
            s += np.sin(ph) + .18 * warm * np.sin(2 * ph)
    s /= 3.2 * len(freqs)
    lfo = 1 + .12 * np.sin(2 * np.pi * .23 * t)
    return s * lfo * env(len(t), .9, 1.2)


def sub(f, d):
    t = np.arange(int(d * SR)) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 3.2) * env(len(t), .012, .18)


def blip(f, d=.16):
    t = np.arange(int(d * SR)) / SR
    return (np.sin(2 * np.pi * f * t) + .25 * np.sin(2 * np.pi * f * 2 * t)) * np.exp(-t * 26) * env(len(t), .006, .08)


def whoosh(d=.5, seed=3):
    x = smooth_noise(d, seed, 9) - smooth_noise(d, seed + 1, 80)
    tt = np.linspace(0, 1, len(x))
    x = x * np.sin(np.pi * tt) ** 2.4
    return lowpass(x, 2200.0)


def energy(tl, n):
    tt = np.arange(n) / SR
    end = tl["end"]
    gap = tl.get("gap") or {}
    cta = (tl.get("cta") or {}).get("at", end - 6)
    endcard = (tl.get("endcard") or {}).get("at", end - 2.6)
    g_at = float(gap.get("at", min(8.0, end * .15)))
    pay = float(gap.get("close", cta - 8))
    xs = [0, max(.1, g_at - .4), g_at + .6, pay - 1.0, pay - .05, pay + .08, pay + .9, cta - .2, cta + .3, endcard, end]
    ys = [.3, .4, .7, 1.0, 1.0, .25, .85, .8, .6, .5, .0]
    order = np.argsort(xs)
    return np.interp(tt, np.array(xs)[order], np.array(ys)[order]), pay, endcard


def bed(tl, n):
    m = MOODS.get(int(tl.get("mood") or 0) % 4)
    beat = 60 / m["bpm"]
    bar = 4 * beat
    end = tl["end"]
    stop = end - 1.6
    L, R = np.zeros(n), np.zeros(n)
    e, pay, endcard = energy(tl, n)
    at = lambda t: float(e[min(n - 1, max(0, int(t * SR)))])
    k, t0 = 0, 0.0
    while t0 < min(stop, endcard):
        ch = m["prog"][k % 4]
        d = min(bar + 1.2, end - t0)
        p = pad([hz(x) for x in ch], d)
        add(L, t0, p, .5)
        add(R, t0, p, .5)
        if at(t0 + .1) >= .45:  # the warm sub pulse, on every beat
            for b in range(4):
                tb = t0 + b * beat
                if tb > stop:
                    break
                g = .55 * m["pulse"] * min(1, (at(tb) - .4) * 3)
                s = sub(hz(ch[0] - 12), beat * .9)
                add(L, tb, s, g)
                add(R, tb, s, g)
        if at(t0 + .1) >= .55:  # glass bells on the off-beats, panned
            notes = [ch[2] + 12, ch[3] + 12, ch[1] + 24, ch[3] + 24, ch[2] + 24, ch[1] + 12]
            for j in range(8):
                tt = t0 + j * beat / 2 + beat / 4
                if tt > stop:
                    break
                g = .18 * m["bell"] * min(1, (at(tt) - .5) * 2.5) * (1 if j % 2 else .7)
                b = bell(hz(notes[j % len(notes)]), 1.2, m["bell"])
                pan = .35 if j % 2 else -.35
                add(L, tt, b, g * (1 - pan))
                add(R, tt, b, g * (1 + pan))
        k += 1
        t0 += bar
    # a soft air rise into the payoff, a breath on it
    rs = smooth_noise(1.8, 21, 40) * np.linspace(0, 1, int(1.8 * SR)) ** 2.6
    rs = lowpass(rs * env(len(rs), .2, .12), 2400.0)
    add(L, pay - 1.8, rs, .07)
    add(R, pay - 1.8, rs, .07)
    level = .35 + .65 * e
    L *= level
    R *= level
    # the resolve chord under the end card (the page's sign-off), and the boot chime on frame 0
    last = m["prog"][0]
    for j, x in enumerate((last[0] + 12, last[1] + 12, last[2] + 12, last[3] + 24)):
        b = bell(hz(x), min(2.4, end - endcard), .7)
        add(L, endcard + j * .07, b, .16)
        add(R, endcard + j * .07, b, .16)
    for j, x in enumerate((last[2] + 24, last[3] + 24)):
        b = bell(hz(x), 1.0, .8)
        add(L, .02 + j * .11, b, .12)
        add(R, .02 + j * .11, b, .12)
    return np.stack([L, R], axis=1)


def ui(tl, n):
    """Soft blips on the beats and airy whooshes on the designed transitions (the edit you can hear)."""
    out = np.zeros((n, 2))
    end = tl["end"]
    for k, s in enumerate(tl.get("shots") or []):
        if s["at"] < .4 or s["tr"] in ("cut", "dissolve") or s["at"] > end - 2:
            continue
        w = whoosh(.5, 40 + k)
        pan = .3 if k % 2 else -.3
        add(out[:, 0], s["at"] - .3, w, 1 - pan)
        add(out[:, 1], s["at"] - .3, w, 1 + pan)
    for k, b in enumerate(tl.get("beats") or []):
        t = float(b["t"])
        if t < .3 or t > end - 2:
            continue
        bl = blip(hz(84 + (k % 3) * 2), .16)
        add(out[:, 0], t, bl, .5)
        add(out[:, 1], t, bl, .5)
    return out


def main():
    tl = json.load(open(os.path.join(ROOT, "build", "timeline.json"), encoding="utf-8"))
    end = float(tl["end"])
    n = int(round(end * SR))
    with_voice = "--no-voice" not in sys.argv
    if with_voice:
        v = load(os.path.join(ROOT, "qc", "voice_final.wav"))[:n]
        v = np.pad(v, (0, n - len(v)))
        v *= 10 ** ((-16.0 - lufs(v)) / 20)
        write(os.path.join(ROOT, "build", "voice_track.wav"), v)
    else:
        v = np.zeros(n)
    mus = bed(tl, n)
    mus *= 10 ** ((-16.0 - 15.0 - lufs(mus)) / 20)
    fx = ui(tl, n)
    if np.abs(fx).max() > 0:
        lf = lufs(fx)
        fx *= 10 ** ((-16.0 - 22.0 - lf) / 20) if lf > -70 else 0
    h = int(.05 * SR)
    pw = np.convolve(v ** 2, np.ones(h) / h, mode="same")
    act = np.clip((10 * np.log10(pw + 1e-12) + 45) / 15, 0, 1)
    act = np.convolve(act, np.ones(int(.2 * SR)) / int(.2 * SR), mode="same")
    duck = 10 ** (-4.0 * act / 20)
    fade = np.ones(n)
    f = int(1.6 * SR)
    fade[-f:] = np.linspace(1, 0, f) ** 1.6
    mix = (mus * duck[:, None] + fx) * fade[:, None] + v[:, None]
    tmp = os.path.join(ROOT, "build", "mix.pre.wav")
    write(tmp, mix)
    g = -14.0 - lufs_of(tmp)[0]
    out = os.path.join(ROOT, "build", "mix.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
                    f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.87:attack=2:release=60:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", out], check=True)
    os.remove(tmp)
    lu, tp = lufs_of(out)
    print(json.dumps({"mix": "build/mix.wav", "lufs": lu, "true_peak": tp, "dur": round(end, 2), "voice": with_voice,
                      "mood": int(tl.get("mood") or 0), "whooshes": sum(1 for s in tl.get("shots") or [] if s["tr"] not in ("cut", "dissolve")),
                      "blips": len(tl.get("beats") or [])}))


if __name__ == "__main__":
    sys.exit(main())
