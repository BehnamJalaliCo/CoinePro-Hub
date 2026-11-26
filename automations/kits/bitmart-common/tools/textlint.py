# -*- coding: utf-8 -*-
"""bitmart — the text-safety gate (DIRECTION §6.3): every on-screen string and the post's texts.

usage: python3 -I COMMON/tools/textlint.py [qc/texts.json] [out/caption.txt out/comment.txt …]
  qc/texts.json  the strings the page drew (story_engine.py --test writes it; story/cover specs: pass the
                 spec .json files too — their text fields are read)
  *.txt          caption / comment / topic: the page-name and wording rules
Exits 1 and lists every problem; 0 = clean. Run it before the render and again before delivery.
"""
import json
import re
import sys
from pathlib import Path

FA_DIG, EN_DIG = "۰۱۲۳۴۵۶۷۸۹", "0123456789"
# the page is NOT the exchange of the same name (owner, 2026-11-26): nothing may read as its account, its ad,
# its referral, or a trading signal (the page's pages were closed as «scam» before)
EXCHANGE = re.compile(r"صرافی\s*(ی\s*)?بیت\s*‌?\s*مارت|bitmart\s*(exchange|\.com|global|token|bmx)|BMX\b|رفرال|referral|کد\s*دعوت|ثبت\s*‌?\s*نام\s*کن", re.I)
SIGNAL = re.compile(r"سیگنال|سود\s*تضمینی|تضمینی|پامپ|pump|x\s*100|۱۰۰\s*برابر\s*(می|کن)|همین\s*الان\s*بخر|بخرید|فرصت\s*آخر|پولدار\s*شو|درآمد\s*دلاری", re.I)
DM_BAIT = re.compile(r"(بیا|بیاید)\s*دایرکت|لینک\s*(تو|در)\s*بیو|link in bio", re.I)
BRAND_SPELL = {"بیت مارت": "bitmart (Latin, lower case) — on screen and in texts"}


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
    if EXCHANGE.search(s):
        bad.append("reads as the BitMart exchange / a referral — the page is independent (owner, 2026-11-26)")
    if SIGNAL.search(s):
        bad.append("signal / promise / buy-now wording — never on this page")
    if DM_BAIT.search(s):
        bad.append("«come to the DM» / «link in bio» — never")
    for w, r in BRAND_SPELL.items():
        if w in s:
            bad.append(f"«{w}» — {r}")
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
            if "http" in p.read_text(encoding="utf-8"):
                problems.append("caption.txt: a link — none in the caption")
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
