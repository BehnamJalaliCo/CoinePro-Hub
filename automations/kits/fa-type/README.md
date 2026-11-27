# fa-type — Persian typography and the TYPE GATE for every page (2026-11-27)

**Why.** DotCoin's stories of 2026-11-27 (F-0246) went out with broken figures: the session drew the
slides with its own HTML whose big figures named a font the page never loaded. Chromium silently drew
them in a SYSTEM font (DejaVu / Liberation): Persian zeros as heavy squares, «٬» as an apostrophe
(«۵’■■■»), «٫» like «ر», and a chip «۱۲ از ۱۰۰» ran out of its box. Nobody checked. The owner: «با فونت
خراب … این اشتباه ها تکرار نشه». This kit makes that impossible for any text our tools draw.

## The tools
- `fatype.py` — import it from any kit tool (`sys.path.insert(0, "/home/studio/kits/fa-type")`):
  - `num(x, decimals=None, pct=False)` — a figure by the rules; `fa(s)` digits only;
    `normalize(text)` — a string's figures put right; `lint(text)` — the rules' problems.
  - `gate(page, bands=…, fonts_allowed=…, max_weight=…)` — on an open Playwright page (fonts loaded):
    Chrome's own report of the font that drew every text node (CDP `CSS.getPlatformFontsForNode`);
    a system font = FAIL; a failed @font-face = FAIL; text off the picture, out of its box or chip,
    wider/taller than its column, over other text, or inside a calm band (unless in `[data-frame]`) =
    FAIL; the number rules on every visible string = FAIL.
  - `render(html, out, …)` — open, gate, and write the picture ONLY when it passes (a failing page
    writes nothing and removes an old file of that name); `record` appends the verdict with the
    picture's sha256 to `qc/type_gate.jsonl` (a deliver check can prove every delivered file passed).
  - `symbols(html)` + `SYM_CSS` — «← → ▲ ▼ · • ✓» as inline SVG: IRANYekanX and Estedad lack them
    (they fell to Liberation Serif in the proof).
- `tools/type_gate.py page.html [--out pic.png] [--bands 0:370,1390:1920] [--fonts IRANYekanX]` — gate any
  page; `--text "…"` / `--json spec.json` — lint strings and print the corrected form.
- `tools/test_fatype.py` — the gate's own proof: the failures of F-0246 (system font for figures, a
  face that does not load, «’» in a figure, Latin digits, «.» decimals, «-» beside a figure, a chip
  narrower than its text, text over text, an arrow the font lacks, text in the calm band, a column
  too narrow) are each caught, and a clean page passes. Run it after any change here.

## The number rules (every page, every tool, every brief to ChatGPT/Gemini)
- Persian digits only: ۰۱۲۳۴۵۶۷۸۹ — never 0–9 in Persian text, never the Arabic ٠١٢٣٤٥٦٧٨٩.
- Up to 4 digits: NO separator («۵۰۰۰», «۱۲۵۰», «۲۰۲۶»). 5 digits and more: «٬» (U+066C) every three
  («۶۰٬۴۸۰», «۱٬۲۵۰٬۰۰۰»). IRANYekanX and Estedad draw «٬» as a clean low comma.
- Decimals: «/» («۹/۶»), the Persian press's mark, drawn the same by every font. Never «.» or «,», and
  never «٫» (U+066B): AnjomanMax (bitmart) and Estedad (bjtech) draw it as a hook that reads like «ر»,
  IRANYekanX Medium like a comma (proof sheet 2026-11-27). The engines' `fa()` now write «/».
- Percent: «٪» right after the number («۹/۶٪»).
- No «-»/«+» beside a figure (it flips with the direction): «افت ۹/۶٪», «رشد ۲٪», or ▼/▲ with the
  meaning colour. Ranges with «تا» («۵ تا ۱۰»).
- Persian «ی ک», never Arabic «ي ك». Never «’ ' ‘» in a figure.
- A figure next to another figure through a sign («۵۰ ÷ ۴٪ = ۱۲۵۰») is isolated (`<bdi>`) by the tools.

## Fonts and weights
- Only fonts loaded by @font-face from the kits (fonts-pro IRANYekanX Pro, fonts-eco, fonts-bj Estedad /
  Geist, the page's own). Never a family the page did not load, never `sans-serif` as the font that
  draws Persian. The FaNum files for Persian digits (IRANYekanX); IRANYekanX non-FaNum draws Persian
  digits the same way.
- Figures at most Black (900). ExtraBlack (950) only for words, never for big figures.

## Where it runs (2026-11-27)
- dotcoin-stories: `slide_frame.py` (on ChatGPT's slide only), `deliver_check.py`. (`slide_fallback.py`, the tested
  fallback built the same morning, was RETIRED the same day by the owner's rule: no substitute, ever — a failed
  path is retried, its error reported and fixed, then the day is made.)
- zaribsad-stories `story_card.py`, bjtech-common `card.py`, bitmart-common `cover_make.py`,
  dotcoin-common and zaribsad-common `cover_compose.py`: the gate before the screenshot; a failing
  card is not written.
- Videos (reels engines) draw thousands of frames: their text strings go through `type_gate.py --json`
  (or `fatype.lint`) before the render, and one still per scene through the gate.
