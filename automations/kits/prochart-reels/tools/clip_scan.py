#!/usr/bin/env python3
"""Find over-full-scale stretches in a decoded narration (float), to tell codec overshoot from real clipping.

Usage: build/asr/venv/bin/python -I tools/clip_scan.py AUDIO [ASR.json]
Prints: samples over 1.0, the 0.1 s windows where they sit, and (with ASR words) which word each window is in.
Flat-topped runs (>= 3 equal samples near the max before decoding) cannot be seen after Opus, so the test is
how often and how far the decoded wave goes over 1.0 and whether it sits on a few loud syllables.
"""
import json
import subprocess
import sys

import numpy as np


def load(path, sr=48000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy(), sr


def main() -> None:
    x, sr = load(sys.argv[1])
    words = json.load(open(sys.argv[2], encoding="utf-8"))["words"] if len(sys.argv) > 2 else []
    a = np.abs(x)
    over = np.flatnonzero(a > 1.0)
    win = 0.1
    spots = {}
    for i in over:
        k = round(int(i / (sr * win)) * win, 1)
        spots.setdefault(k, [0, 0.0])
        spots[k][0] += 1
        spots[k][1] = max(spots[k][1], float(a[i]))
    def word_at(t):
        for w in words:
            if w["s"] - 0.05 <= t <= w["e"] + 0.05:
                return w["w"]
        return ""
    rows = [{"t": k, "n": v[0], "max": round(v[1], 3), "word": word_at(k + win / 2)} for k, v in sorted(spots.items())]
    res = {"samples": int(x.size), "over_1": int(over.size), "over_1_pct": round(100 * over.size / x.size, 4),
           "peak": round(float(a.max()), 3), "peak_dbfs": round(20 * np.log10(float(a.max())), 2),
           "windows": len(rows), "top": sorted(rows, key=lambda r: -r["max"])[:8]}
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
