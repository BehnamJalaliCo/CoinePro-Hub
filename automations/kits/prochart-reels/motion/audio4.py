# -*- coding: utf-8 -*-
"""Sound for reel 1: our own music bed + small effects on the approved cues + the final voice, mixed for Instagram.

Usage: build/asr/venv/bin/python -I motion/audio4.py motion/T.json qc/voice_final.wav OUT.wav
- Music: made here (no licence issue): 95 BPM, Am–F–C–G pad, soft bass and pulse, light hats; calm in the warning,
  two strong hits on the slogan, a last hit on «پرو چارت», fades out at the end. About 22 dB under the voice and
  ducked a little more while the voice speaks.
- Effects: whoosh / tick / click / pop / ping / snap / stamp / flip / typing, on the times of the edit (T).
- Mix: voice to -14 LUFS, whole mix -14 LUFS, true peak under -1 dBTP (limiter at 4x oversampling).
"""
import json
import re
import subprocess
import sys

import numpy as np

SR = 48000
BPM = 95
BEAT = 60 / BPM


def load_voice(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def lufs(x):
    p = "/tmp/_lufs_probe.wav"
    write(p, x)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", err[err.rfind("Summary:"):]).group(1))


def write(path, x, fmt="pcm_f32le"):
    ch = 1 if x.ndim == 1 else x.shape[1]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(ch), "-i", "-", "-c:a", fmt, path],
                   input=x.astype(np.float32).tobytes(), check=True)


def onepole(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def env(n, att, rel):
    e = np.ones(n)
    a, r = min(int(att * SR), n), min(int(rel * SR), n)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def note(f):
    return 440.0 * 2 ** ((f - 69) / 12)


def add(buf, start, sig, gain=1.0):
    i = int(start * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def music(T, n):
    t_end = n / SR
    L, R = np.zeros(n), np.zeros(n)
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G
    bar = 4 * BEAT
    k, t0 = 0, 0.0
    rng = np.random.default_rng(5)
    while t0 < t_end:
        ch = chords[k % 4]
        dur = min(bar + 0.6, t_end - t0)
        m = int(dur * SR)
        tt = np.arange(m) / SR
        e = env(m, 0.45, 0.6)
        for j, nn in enumerate(ch):
            f = note(nn)
            for side, det in ((L, -1.2), (R, 1.3)):
                sig = (np.sin(2 * np.pi * (f + det * 0.2) * tt) + 0.35 * np.sin(2 * np.pi * (f / 2 + det * 0.1) * tt)
                       + 0.12 * np.sin(2 * np.pi * 2 * f * tt))
                add(side, t0, sig * e, 0.05)
        # bass on beats 1 and 3
        for b in (0, 2):
            bt = t0 + b * BEAT
            if bt < t_end:
                m2 = int(0.5 * SR)
                tb = np.arange(m2) / SR
                sig = np.sin(2 * np.pi * note(ch[0] - 12) * tb) * np.exp(-tb * 6)
                add(L, bt, sig, 0.10)
                add(R, bt, sig, 0.10)
        t0 += bar
        k += 1
    # pulse (soft kick) on every beat, hats on off-beats
    kick_n = int(0.22 * SR)
    tk = np.arange(kick_n) / SR
    kick = np.sin(2 * np.pi * (55 * tk + 30 * (1 - np.exp(-tk * 25)) / 25)) * np.exp(-tk * 16)
    hat_n = int(0.04 * SR)
    hat = np.diff(rng.standard_normal(hat_n + 1)) * np.exp(-np.arange(hat_n) / SR * 90)
    pulse_L, pulse_R = np.zeros(n), np.zeros(n)
    b = 0
    while b * BEAT < t_end:
        tb = b * BEAT
        drums = T["b0"] - 0.1 <= tb < T["k10"] - 0.05  # no drums in the opening (tension) and the warning
        if drums:
            add(pulse_L, tb, kick, 0.18)
            add(pulse_R, tb, kick, 0.18)
        if tb >= 0.6 and tb < T["k10"]:
            add(pulse_L, tb + BEAT / 2, hat, 0.012)
            add(pulse_R, tb + BEAT / 2, hat, 0.016)
        b += 1
    L += pulse_L
    R += pulse_R
    # riser into the brand (shot 2)
    rn = int(1.2 * SR)
    tr_ = np.arange(rn) / SR
    noise = onepole(rng.standard_normal(rn), 0.25) * (tr_ / tr_[-1]) ** 2
    add(L, T["b0"] - 1.2, noise, 0.05)
    add(R, T["b0"] - 1.2, noise, 0.05)
    # section levels: calm in the warning, slogan hits, fade at the end
    tt = np.arange(n) / SR
    lvl = np.ones(n)
    lvl *= np.interp(tt, [0, T["k10"], T["k10"] + .6, T["e0"] - .2, T["e0"]], [1, 1, .5, .5, .9])
    lvl *= np.interp(tt, [0, T["end"] - 2.2, T["end"]], [1, 1, 0])
    L *= lvl
    R *= lvl
    hit_n = int(1.2 * SR)
    th = np.arange(hit_n) / SR
    hit = (np.sin(2 * np.pi * (50 * th + 40 * (1 - np.exp(-th * 20)) / 20)) * np.exp(-th * 7)
           + 0.4 * sum(np.sin(2 * np.pi * note(nn) * th) for nn in (57, 60, 64, 69)) * np.exp(-th * 3.2) * 0.25)
    for at, g in ((T["e1"] + .1, .30), (T["e2"] + .1, .34), (T["e3"] + .1, .26)):
        add(L, at, hit, g)
        add(R, at, hit, g)
    return np.stack([L, R], axis=1)


def mx(*xs):
    out = np.zeros(max(len(x) for x in xs))
    for x in xs:
        out[: len(x)] += x
    return out


def sfx_bank():
    rng = np.random.default_rng(11)

    def t(d):
        return np.arange(int(d * SR)) / SR

    def whoosh(d=0.5, bright=0.35):
        x = t(d)
        nz = rng.standard_normal(len(x))
        lo = onepole(nz, 0.05 + bright * np.sin(np.pi * x / d).mean())
        return lo * np.sin(np.pi * x / d) ** 2 * 1.6

    def tone(f, d, dec, harm=0.0):
        x = t(d)
        return (np.sin(2 * np.pi * f * x) + harm * np.sin(2 * np.pi * 2 * f * x)) * np.exp(-x * dec)

    def noise_burst(d, dec, hp=True):
        nz = rng.standard_normal(int(d * SR))
        if hp:
            nz = np.diff(np.concatenate([[0], nz]))
        return nz * np.exp(-t(d) * dec)

    def sweep(f0, f1, d, dec):
        x = t(d)
        f = f0 + (f1 - f0) * x / d
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * dec)

    return {
        "whoosh": whoosh(0.5), "rewind": whoosh(0.6, 0.6)[::-1], "tick": tone(2400, 0.05, 90) * 0.6,
        "click": mx(tone(1300, 0.04, 120) * 0.6, noise_burst(0.02, 200) * 0.15), "pop": sweep(700, 300, 0.09, 30),
        "ping": tone(1568, 0.5, 9, 0.3) * 0.5, "snap": noise_burst(0.03, 140) * 0.5,
        "stamp": mx(sweep(110, 40, 0.35, 9) * 1.2, noise_burst(0.08, 50) * 0.35),
        "flip": noise_burst(0.16, 25, hp=False) * np.abs(np.sin(np.pi * t(0.16) / 0.04)) * 0.5,
        "key": mx(tone(900, 0.05, 110) * 0.5, noise_burst(0.03, 160) * 0.2),
        "shine": (tone(2637, 0.4, 8) + tone(3322, 0.4, 9) + tone(4186, 0.4, 10)) * 0.18,
        "strike": noise_burst(0.25, 12, hp=True) * np.sin(np.pi * t(0.25) / 0.25) * 0.45,
    }


def cues(T):
    c = [(0.02, "whoosh", .7), (0.55, "tick", 1), (T["rew"], "rewind", .9)]
    c += [(a + .2, "whoosh", .8) for a in T["slash"]]
    c += [(T["mark"], "pop", .7), (T["pill"], "click", 1), (T["b1"] - .45, "whoosh", .7), (T["rw0"], "rewind", .7),
          (T["ld"], "tick", 1)] + [(a, "tick", .9) for a in T["st"]]
    c += [(T["tip"], "pop", .6), (T["q"], "whoosh", .5), (T["card"], "pop", .6), (T["cal"], "flip", .9),
          (T["eye"], "tick", .9), (T["code"], "whoosh", .5), (T["dec"], "pop", .7), (T["k1"], "key", 1),
          (T["k2"], "key", 1), (T["buy"], "tick", 1), (T["sl"], "snap", 1), (T["tp"], "snap", 1),
          (T["newc"], "click", 1), (T["r0"], "whoosh", .6)] + [(a, "ping", .7) for a in T["rows"]]
    c += [(T["fsl"], "shine", 1), (T["ftp"], "shine", 1), (T["stx"], "pop", .6), (T["stamp"], "stamp", 1),
          (T["money"], "whoosh", .5), (T["strike"], "strike", 1)]
    tw = T["type1"] - T["type0"]
    c += [(T["type0"] + k * tw / 6, "key", .8) for k in range(6)] + [(T["dm"], "whoosh", .6), (T["e4"], "ping", .6)]
    return c


def main() -> None:
    T = json.load(open(sys.argv[1], encoding="utf-8"))
    voice = load_voice(sys.argv[2])
    out = sys.argv[3]
    n = int(round(T["end"] * SR))
    v = np.zeros(n)
    v[: min(n, len(voice))] = voice[:n]
    v *= 10 ** ((-14.0 - lufs(v)) / 20)
    mus = music(T, n)
    ml = lufs(mus)
    mus *= 10 ** ((-14.0 - 22.0 - ml) / 20)
    # duck the music a little more while the voice speaks (smooth 120 ms envelope)
    h = int(0.05 * SR)
    pw = np.convolve(v ** 2, np.ones(h) / h, mode="same")
    act = np.clip((10 * np.log10(pw + 1e-12) + 45) / 15, 0, 1)
    act = np.convolve(act, np.ones(int(0.12 * SR)) / int(0.12 * SR), mode="same")
    mus *= (1 - 0.35 * act)[:, None]
    fx = np.zeros(n)
    bank = sfx_bank()
    for at, name, g in cues(T):
        add(fx, max(at, 0), bank[name], g)
    fl = lufs(fx)
    fx *= 10 ** ((-14.0 - 20.0 - fl) / 20)
    mix = mus + (v + fx)[:, None]
    tmp = out + ".pre.wav"
    write(tmp, mix)
    g = -14.0 - lufs(mix)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
                    f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.87:attack=2:release=60:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", out], check=True)
    import os
    os.remove(tmp)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    print(json.dumps({"lufs": float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1)),
                      "true_peak": re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ).group(1),
                      "music_under_voice_db": 22, "fx_under_voice_db": 20, "cues": len(cues(T)), "dur": n / SR}))


if __name__ == "__main__":
    main()
