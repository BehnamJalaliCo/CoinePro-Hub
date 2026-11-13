#!/usr/bin/env python3
"""Word-level QC: script vs. heard transcript (Persian), phonetic char alignment.

Usage: python3 -I tools/qc_compare.py SCRIPT.txt TRANSCRIPT.txt [OUT.json]
Prints, per script line: heard text, and script words whose sounds were not found.
"""
import difflib
import json
import re
import sys

DIAC = re.compile(r"[ً-ٰٟـ]")
PUNCT = re.compile(r"[\s‌‏‎،؛؟?!.:…«»\"'()\-–—,;]+")
PHON = str.maketrans({
    "ض": "ز", "ظ": "ز", "ذ": "ز", "ث": "س", "ص": "س", "ط": "ت", "ح": "ه",
    "غ": "ق", "ع": "ا", "آ": "ا", "أ": "ا", "إ": "ا", "ة": "ه", "ي": "ی",
    "ك": "ک", "ؤ": "و", "ئ": "ی",
})


def phon(word: str) -> str:
    w = word.replace("اً", "ان")
    w = DIAC.sub("", w)
    w = PUNCT.sub("", w)
    return w.translate(PHON)


def main() -> None:
    script_path, heard_path = sys.argv[1], sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    lines = [l.strip() for l in open(script_path, encoding="utf-8") if l.strip()]
    heard = open(heard_path, encoding="utf-8").read().strip()

    # script chars -> (line, word)
    s_chars, s_owner, words = [], [], []
    for li, line in enumerate(lines):
        for w in line.split():
            p = phon(w)
            words.append({"line": li, "word": w, "phon": p, "n": len(p), "hit": 0})
            for ch in p:
                s_chars.append(ch)
                s_owner.append(len(words) - 1)
    # heard chars -> index in original heard text
    h_chars, h_pos = [], []
    for m in re.finditer(r"\S+", heard):
        p = phon(m.group())
        # map each phonetic char back to the word's span
        for ch in p:
            h_chars.append(ch)
            h_pos.append((m.start(), m.end()))
    sm = difflib.SequenceMatcher(None, "".join(s_chars), "".join(h_chars), autojunk=False)
    line_span = {}
    matched_h = [False] * len(h_chars)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            wi = s_owner[a + k]
            words[wi]["hit"] += 1
            matched_h[b + k] = True
            li = words[wi]["line"]
            st, en = h_pos[b + k]
            lo, hi = line_span.get(li, (st, en))
            line_span[li] = (min(lo, st), max(hi, en))
    report = []
    for li, line in enumerate(lines):
        ws = [w for w in words if w["line"] == li]
        flagged = [
            {"word": w["word"], "ratio": round(w["hit"] / w["n"], 2)}
            for w in ws if w["n"] and w["hit"] / w["n"] < 0.6
        ]
        span = line_span.get(li)
        report.append({
            "n": li + 1,
            "script": line,
            "heard": heard[span[0]:span[1]] if span else "",
            "flagged": flagged,
        })
    # heard material that matched nothing in the script (possible extra words)
    extra, cur = [], None
    for i, ok in enumerate(matched_h):
        if not ok:
            st, en = h_pos[i]
            if cur and st <= cur[1] + 1:
                cur = (cur[0], max(cur[1], en))
            else:
                if cur:
                    extra.append(heard[cur[0]:cur[1]])
                cur = (st, en)
    if cur:
        extra.append(heard[cur[0]:cur[1]])
    total = sum(w["n"] for w in words)
    hit = sum(min(w["hit"], w["n"]) for w in words)
    summary = {"script_words": len(words), "sound_match": round(hit / total, 3),
               "extra_heard": extra}
    for r in report:
        print(f"[{r['n']}] {r['script']}")
        print(f"    heard: {r['heard']}")
        if r["flagged"]:
            print("    !! " + ", ".join(f"{f['word']}({f['ratio']})" for f in r["flagged"]))
    print(json.dumps(summary, ensure_ascii=False))
    if out_path:
        json.dump({"lines": report, "summary": summary}, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
