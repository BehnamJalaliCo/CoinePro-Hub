# -*- coding: utf-8 -*-
"""DotCoin stories — the check before delivery (2026-11-27, after F-0246's broken figures).

Usage (in the workspace): VENV/bin/python -I KIT/tools/deliver_check.py [--n 12]
Exit 0 = the set may be delivered; exit 2 = it may NOT (every reason listed). It checks:
  1. out/ holds story_1.jpg … story_N.jpg (1080×1920), comment.txt and topic.txt, nothing else;
  2. every story_K.jpg is byte for byte a picture slide_frame.py made and the TYPE GATE passed
     (its sha256 in qc/type_gate.jsonl with ok=true): a picture copied in from anywhere else, an
     improvised render or a failed one cannot go out;
  3. qc/scores.md scores every slide with its typography («type» for slide K, out of 10) and no slide
     is under 8.5 overall or under 9 for typography;
  4. comment.txt has its keyword line and the summary keeps the number rules for any figure.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _c in (os.environ.get("FATYPE", ""), "/home/studio/kits/fa-type", str(HERE.parent.parent / "fa-type")):
    if _c and Path(_c, "fatype.py").exists():
        sys.path.insert(0, _c)
        break
import fatype as F  # noqa: E402


def main(argv: list[str]) -> int:
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 12
    bad: list[str] = []
    out = Path("out")
    want = {f"story_{k}.jpg" for k in range(1, n + 1)} | {"comment.txt", "topic.txt"}
    have = {p.name for p in out.iterdir()} if out.is_dir() else set()
    for m in sorted(want - have):
        bad.append(f"out/{m} is missing")
    for x in sorted(have - want):
        bad.append(f"out/{x} must not be in out/ (only story_1..{n}.jpg, comment.txt, topic.txt)")
    passed: set[str] = set()
    log = Path(F.GATE_LOG)
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ok") and str(r.get("tool", "")).endswith("slide_frame") and r.get("sha256"):
                passed.add(r["sha256"])
    else:
        bad.append(f"{F.GATE_LOG} is missing: frame every slide with tools/slide_frame.py")
    from PIL import Image

    for k in range(1, n + 1):
        p = out / f"story_{k}.jpg"
        if not p.exists():
            continue
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if sha not in passed:
            bad.append(f"{p}: not a picture slide_frame.py made with the type gate passed (re-frame it; never copy a picture into out/)")
        with Image.open(p) as im:
            if im.size != (1080, 1920):
                bad.append(f"{p}: {im.size[0]}×{im.size[1]}, not 1080×1920")
    scores = Path("qc/scores.md")
    if not scores.exists():
        bad.append("qc/scores.md is missing")
    else:
        txt = scores.read_text(encoding="utf-8")
        for k in range(1, n + 1):
            m = re.search(rf"(?m)^\s*\|?\s*{k}\s*\|.*?\|\s*([0-9.]+)\s*\|\s*type\s*([0-9.]+)", txt)
            if not m:
                bad.append(f"qc/scores.md: no row «| {k} | … | <score> | type <score> |» for slide {k}")
                continue
            total, typo = float(m.group(1)), float(m.group(2))
            if total < 8.5:
                bad.append(f"slide {k}: score {total} under 8.5 — redo it")
            if typo < 9:
                bad.append(f"slide {k}: typography {typo} under 9 — redo it (README step 5)")
    c = out / "comment.txt"
    if c.exists():
        ct = c.read_text(encoding="utf-8")
        if not re.search(r"(?m)^keyword:\s*\S", ct):
            bad.append("comment.txt has no «keyword:» line")
        for line in ct.splitlines():
            body = line.split(":", 1)[1] if ":" in line else line
            for prob in F.lint(body):
                if "Arabic «ي/ك»" in prob or "apostrophe" in prob or "Arabic-Indic" in prob:
                    bad.append(f"comment.txt: {prob}")
    if bad:
        print(f"NOT DELIVERABLE ({len(bad)}):")
        for b in bad:
            print("  -", b)
        return 2
    print(f"DELIVERABLE: {n} stories, every one framed and type-gated, scores and typography ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
