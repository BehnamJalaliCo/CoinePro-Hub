#!/usr/bin/env python3
"""Script words with real times: align the written script to the heard words (Whisper) of the final voice.

Usage: build/asr/venv/bin/python -I tools/word_times.py SCRIPT.txt ASR.json VOICE.wav OUT.json
1) Real pauses come from the voice itself (envelope < -45 dB for >= 0.12 s).
2) Whisper glues word edges, so each heard word is first fitted to the pauses: one that starts inside a pause
   starts at its end, one that ends inside a pause ends at its start, and a pause inside one heard word cuts off
   the smaller side.
3) Phonetic, character-level alignment (same folding as qc_compare) gives every script word the time of the
   characters it matched, split by character position, so «پرو چارت» ↔ «پروچارت» and «نه با» ↔ «نبا» work.
OUT.json: {"duration", "pauses": [[start, end]], "lines": [{"n", "text", "start", "end", "words": [{"w", "s", "e"}]}]}
"""
import difflib
import json
import re
import subprocess
import sys

import numpy as np

DIAC = re.compile(r"[ً-ٰٟـ]")
PUNCT = re.compile(r"[\s‌‏‎،؛؟?!.:…«»\"'()\-–—,;]+")
FOLD = str.maketrans({"ض": "ز", "ظ": "ز", "ذ": "ز", "ث": "س", "ص": "س", "ط": "ت", "ح": "ه", "غ": "ق", "ع": "ا",
                      "آ": "ا", "أ": "ا", "إ": "ا", "ة": "ه", "ي": "ی", "ك": "ک", "ؤ": "و", "ئ": "ی"})


def phon(w):
    w = w.replace("اً", "ان")
    return PUNCT.sub("", DIAC.sub("", w)).translate(FOLD)


def pauses(path, thr=-45.0, min_len=0.12, hop=0.01):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    h = int(hop * 16000)
    n = len(x) // h
    e = 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9)
    out, r = [], None
    for i, v in enumerate(list(e) + [0.0]):
        if v < thr:
            r = i if r is None else r
        else:
            if r is not None and (i - r) * hop >= min_len:
                out.append([round(r * hop, 2), round(i * hop, 2)])
            r = None
    return out, len(x) / 16000


def fit_to_pauses(heard, ps):
    for hw in heard:
        for a, b in ps:
            s, e = hw["s"], hw["e"]
            if min(e, b) - max(s, a) <= 0.02:
                continue
            if s >= a - 0.06:
                hw["s"] = min(b, e - 0.05)
            elif e <= b + 0.06:
                hw["e"] = max(a, s + 0.05)
            elif (a - s) < (e - b):
                hw["s"] = b
            else:
                hw["e"] = a


def main() -> None:
    script, asr_json, voice, out = sys.argv[1:5]
    lines = [l.strip() for l in open(script, encoding="utf-8") if l.strip()]
    heard = json.load(open(asr_json, encoding="utf-8"))["words"]
    ps, dur = pauses(voice)
    fit_to_pauses(heard, ps)
    sw, s_chars, s_owner = [], [], []
    for li, line in enumerate(lines):
        for w in line.split():
            sw.append({"line": li, "w": w, "hits": []})
            for c in phon(w):
                s_chars.append(c)
                s_owner.append(len(sw) - 1)
    h_chars, h_time = [], []
    for hw in heard:
        p = phon(hw["w"]) or "_"
        L = len(p)
        for k, c in enumerate(p):
            h_chars.append(c)
            h_time.append((hw["s"] + (hw["e"] - hw["s"]) * k / L, hw["s"] + (hw["e"] - hw["s"]) * (k + 1) / L))
    sm = difflib.SequenceMatcher(None, "".join(s_chars), "".join(h_chars), autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            sw[s_owner[a + k]]["hits"].append(h_time[b + k])
    for w in sw:
        if w["hits"]:
            w["s"], w["e"] = min(h[0] for h in w["hits"]), max(h[1] for h in w["hits"])
    for i, w in enumerate(sw):  # words nobody heard: share the gap between the neighbours
        if "s" not in w:
            prev_e = next((sw[j]["e"] for j in range(i - 1, -1, -1) if "e" in sw[j]), 0.0)
            nxt_s = next((sw[j]["s"] for j in range(i + 1, len(sw)) if "s" in sw[j]), prev_e + 0.3)
            w["s"], w["e"] = prev_e, max(nxt_s, prev_e + 0.05)
    for i in range(1, len(sw)):  # keep order
        sw[i]["s"] = max(sw[i]["s"], sw[i - 1]["s"])
        sw[i]["e"] = max(sw[i]["e"], sw[i]["s"] + 0.05)
    res_lines = []
    for li, line in enumerate(lines):
        ws = [w for w in sw if w["line"] == li]
        res_lines.append({"n": li + 1, "text": line, "start": round(ws[0]["s"], 2), "end": round(ws[-1]["e"], 2),
                          "words": [{"w": w["w"], "s": round(w["s"], 2), "e": round(w["e"], 2)} for w in ws]})
    json.dump({"duration": round(dur, 2), "pauses": ps, "lines": res_lines}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    for l in res_lines:
        print(l["n"], l["start"], l["end"], len(l["words"]))


if __name__ == "__main__":
    main()
