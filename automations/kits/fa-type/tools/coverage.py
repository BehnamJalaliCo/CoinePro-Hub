# -*- coding: utf-8 -*-
"""fa-type — which characters a font file really draws (2026-11-27). For CANVAS engines (reels, bitmart's
story engine, bjtech's stage), whose fillText the DOM gate cannot see: a character the font lacks is drawn
by a system font, silently. Each character is measured in the font with two very different fallbacks; a
width that changes with the fallback = not in the font.

  VENV/bin/python -I /home/studio/kits/fa-type/tools/coverage.py FONT.ttf [FONT2.ttf …] [--chars "…"]
  VENV/bin/python -I /home/studio/kits/fa-type/tools/coverage.py --texts texts.json FONT.ttf …
      (texts.json: any JSON; every string in it is checked against the fonts: exit 2 if a character of
       a string is in none of them)
Default characters: digits (Persian, Arabic, Latin), «٬ ٫ ٪ % , . / : ÷ × = + − -», arrows, triangles,
dots, ticks, quotes and Persian punctuation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fatype as F  # noqa: E402

DEFAULT = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩0123456789٬٫٪%,./:÷×=+−-←→↑↓▲▼►◄·•✓✔«»“”’‘،؛؟…—–$€"

JS = """async ([fonts, chars]) => {
  const out = {};
  const faces = await Promise.all(fonts.map((u, i) => new FontFace('F' + i, `url(${u})`).load()));
  faces.forEach(f => document.fonts.add(f));
  const c = document.createElement('canvas').getContext('2d');
  const w = (fam, ch) => { c.font = `100px ${fam}`; return c.measureText(ch).width; };
  for (const ch of chars) {
    out[ch] = fonts.map((_, i) => Math.abs(w(`F${i}, monospace`, ch) - w(`F${i}, serif`, ch)) < 0.01 &&
                                 Math.abs(w(`F${i}, monospace`, ch) - w(`F${i}, cursive`, ch)) < 0.01);
  }
  return out;
}"""


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)


def main(a):
    if not a:
        print(__doc__)
        return 1
    texts = None
    chars = DEFAULT
    if "--texts" in a:
        i = a.index("--texts")
        texts = list(strings(json.loads(Path(a[i + 1]).read_text(encoding="utf-8"))))
        a = a[:i] + a[i + 2:]
        chars = "".join(sorted({ch for s in texts for ch in s if not ch.isspace() and ch not in "‌‏‎"}))
    if "--chars" in a:
        i = a.index("--chars")
        chars = a[i + 1]
        a = a[:i] + a[i + 2:]
    fonts = [Path(x).resolve() for x in a]
    from playwright.sync_api import sync_playwright

    import tempfile

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        page_file = Path(tmp) / "cov.html"  # a file:// page, so file:// fonts load
        page_file.write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
        b = p.chromium.launch(executable_path=F.CHROME, headless=True, args=["--allow-file-access-from-files"])
        try:
            pg = b.new_page()
            pg.goto(page_file.as_uri())
            got = pg.evaluate(JS, [[f.as_uri() for f in fonts], list(dict.fromkeys(chars))])
        finally:
            b.close()
    missing_all = [ch for ch, cov in got.items() if not any(cov)]
    for i, f in enumerate(fonts):
        lack = "".join(ch for ch, cov in got.items() if not cov[i])
        print(f"{f.name}: lacks {lack or 'nothing'}")
    if texts is not None:
        bad = [s for s in texts if any(ch in missing_all for ch in s)]
        for s in bad:
            print(f"✗ in none of the fonts: «{s}» ({''.join(ch for ch in s if ch in missing_all)})")
        print("TEXTS OK" if not bad else f"{len(bad)} string(s) would fall to a system font")
        return 0 if not bad else 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
