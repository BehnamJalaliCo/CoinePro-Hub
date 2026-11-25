# -*- coding: utf-8 -*-
"""Zarib100x — the text-safety gate (DIRECTION §6.4): every on-screen string and the post's texts.

usage: python3 -I COMMON/tools/textlint.py [qc/texts.json] [out/caption.txt out/comment.txt …]
  qc/texts.json  the strings the page drew (desk_engine.py --test writes it; story/cover specs: pass the
                 spec .json files too — their text fields are read)
  *.txt          caption / comment / topic: the page-name and wording rules
Exits 1 and lists every problem; 0 = clean. Run it before the render and again before delivery.
"""
import json
import re
import sys
from pathlib import Path

FA_DIG, EN_DIG = "۰۱۲۳۴۵۶۷۸۹", "0123456789"
OLD_NAMES = re.compile(r"zaribsad|Zarib\s*[×x]\s*100(?!x)|Zarib ×100|ضریب\s*صد(?!\s*ایکس)", re.I)
NO_RISK = re.compile(r"تضمین|توصیه‌?\s*ی?\s*مالی|ریسک بالایی|مسئولیت|past performance|not financial advice", re.I)
BRAND_SPELL = {"ویفنس": "ویکس"}


def strings_of(path: Path) -> list:
    if path.suffix == ".json":
        d = json.loads(path.read_text(encoding="utf-8"))
        out = []

        def walk(v):
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
            elif isinstance(v, dict):
                for k, x in v.items():
                    if k not in ("bg", "plate", "out", "focus", "layout", "kind", "number_dir"):
                        walk(x)
        walk(d)
        return out
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def screen_issues(s: str) -> list:
    bad = []
    t = s.strip()
    if re.search(r"[.،؛]\s*$", t) and not re.search(r"\d\.$", t):
        bad.append("ends with a full stop / «،» / «؛»")
    for tok in re.findall(r"[\d۰-۹٫٬.,]+", t):
        if any(c in FA_DIG for c in tok) and any(c in EN_DIG for c in tok):
            bad.append(f"mixed Persian and Latin digits in «{tok}»")
    if "ـ" in t:
        bad.append("kashida (ـ) — never stretch letters")
    if re.search(r"[يك]", t):
        bad.append("Arabic ي/ك — use Persian ی/ک")
    if "  " in t:
        bad.append("double space")
    return bad


def text_issues(s: str) -> list:
    bad = []
    if OLD_NAMES.search(s):
        bad.append("the old page name — the page is Zarib100x (@Zarib100x)")
    if NO_RISK.search(s):
        bad.append("a risk / disclaimer / guarantee line — the owner: none, we advertise")
    for w, r in BRAND_SPELL.items():
        if w in s:
            bad.append(f"«{w}» — the brand is «{r}»")
    return bad


def main() -> int:
    problems = []
    for a in sys.argv[1:]:
        p = Path(a)
        if not p.exists():
            problems.append(f"{a}: missing")
            continue
        screen = p.suffix == ".json"
        for s in strings_of(p):
            for b in (screen_issues(s) if screen else []) + text_issues(s):
                problems.append(f"{p.name}: «{s[:60]}» — {b}")
        if p.name == "caption.txt":
            tags = re.findall(r"#\S+", p.read_text(encoding="utf-8"))
            if len(tags) != 3:
                problems.append(f"caption.txt: {len(tags)} hashtags — exactly 3")
        if p.name == "comment.txt":
            txt = p.read_text(encoding="utf-8")
            if "#" in re.sub(r"https?://\S+", "", txt):
                problems.append("comment.txt: a hashtag — none in the DM / replies")
            for ln in txt.splitlines():
                if ln.startswith("button:") and len(ln.split("|")[0][7:].strip()) > 20:
                    problems.append(f"comment.txt: button title over 20 characters: {ln[:50]}")
    for x in problems:
        print(x)
    print("textlint:", "clean" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
