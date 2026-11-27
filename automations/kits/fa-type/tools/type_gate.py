# -*- coding: utf-8 -*-
"""fa-type — the type gate from the command line (2026-11-27).

  VENV/bin/python -I /home/studio/kits/fa-type/tools/type_gate.py page.html [--out pic.png]
        [--size 1080x1920] [--bands 0:370,1390:1920] [--fonts IRANYekanX,Estedad]
      Opens an HTML page in the kits' Chromium and gates it (fonts actually used for every glyph,
      failed @font-face, text off its box/chip/column/the picture, text over text, the number
      rules). With --out the picture is written ONLY when it passes. Exit 0 pass, 2 fail.

  VENV/bin/python -I /home/studio/kits/fa-type/tools/type_gate.py --text "…" ["…" …]
  VENV/bin/python -I /home/studio/kits/fa-type/tools/type_gate.py --json spec.json
      The number and letter rules on strings (a spec's every string value). Prints the corrected
      form (fatype.normalize) beside each problem. Exit 0 clean, 2 problems.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fatype as F  # noqa: E402

SKIP_KEYS = {"bg", "out", "src", "focus", "layout", "theme", "kind", "tone", "plate", "font", "fonts"}


def strings(v, key=""):
    if isinstance(v, str):
        if key not in SKIP_KEYS:
            yield v
    elif isinstance(v, list):
        for x in v:
            yield from strings(x, key)
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from strings(x, k)


def lint_many(items):
    bad = 0
    for s in items:
        probs = F.lint(s, persian=F._persianish(s))
        if probs:
            bad += 1
            print(f"✗ «{s}»\n    → «{F.normalize(s)}»")
            for p in probs:
                print("    -", p)
    print("TEXT OK" if not bad else f"{bad} string(s) break the rules")
    return 0 if not bad else 2


def main(a):
    if not a:
        print(__doc__)
        return 1
    if a[0] == "--text":
        return lint_many(a[1:])
    if a[0] == "--json":
        return lint_many(list(strings(json.loads(Path(a[1]).read_text(encoding="utf-8")))))
    page = Path(a[0])
    opt = {a[i]: a[i + 1] for i in range(1, len(a) - 1, 2)}
    w, h = (int(x) for x in opt.get("--size", "1080x1920").split("x"))
    bands = [tuple(int(y) for y in b.split(":")) for b in opt["--bands"].split(",")] if "--bands" in opt else None
    fonts = tuple(x for x in opt.get("--fonts", "").split(",") if x)
    out = opt.get("--out")
    if out:
        v = F.render(page.read_text(encoding="utf-8"), out, size=(w, h), bands=bands, fonts_allowed=fonts, tool="fa-type/type_gate")
        F.report(v, out)
        return 0 if v["ok"] else 2
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=F.CHROME, headless=True, args=["--allow-file-access-from-files"])
        try:
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.goto(page.resolve().as_uri())
            pg.wait_for_timeout(300)
            v = F.gate(pg, bands=bands, fonts_allowed=fonts)
        finally:
            b.close()
    F.report(v, page)
    return 0 if v["ok"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
