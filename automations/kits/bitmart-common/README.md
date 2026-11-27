# What every bitmart kit shares (bitmart-reels) — THE FILE (2026-11-26)

The page **@bitmart** (IG-Hub account 25, company IG): «قصه‌ی پول», the owner's fifth page. Read in this order:
- `DIRECTION.md` — the bible: the owner's rules, the format (THE FILE: every reel a numbered money story),
  motion, sound, the day's look, the QC gate.
- `brand/README.md` — orange #FF6A2B + ink navy #0F1630, the three layers, the type, the mark, THE ORANGE MARKER;
  `brand/tokens.json`.
- `cover/COVER_SYSTEM.md` — the cover: DotCoin's package (the owner's own cover system) in bitmart's colours —
  ChatGPT draws the WHOLE cover from his nine files, the orange ground, the giant ink-navy English words.
- `motion/README.md` — the library (story.js), its engine (story_engine.py) and its sound (story_audio.py);
  `motion/sample/` a working sample.
- The narrator: **Sadaltager** (`speech.make` voice "Sadaltager", no style, no narrator.set) — a knowing storyteller.

Tools (PY = /home/studio/kits/prochart-reels/venv-render/bin/python, PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright):
- `tools/textlint.py` — the text gate (full stops, mixed digits, kashida, Arabic ي/ك, the exchange / signal /
  «come to the DM» words, hashtag count, no link in the caption).
- `tools/cover_make.py` — the FALLBACK only: the Persian title set on ChatGPT's 4th picture (after 3 wrong titles).
- `tools/cover_sheet.py` — the cover's row check beside the last 4 (ground / words).
- `fonts/` — IBM Plex Mono (OFL). The display and text fonts are the owner's licence: /home/studio/kits/fonts-bitmart.

## TYPE GATE (2026-11-27, every page — /home/studio/kits/fa-type/README.md)
DotCoin's stories of 11-27 went out with figures a SYSTEM font drew (zeros as squares, «٬» as «’»):
an improvised renderer named a font it never loaded. From now on the story engine draws ▲/▼ as shapes and writes decimals «/»; run `fa-type/tools/coverage.py --texts qc/texts.json <the page's fonts>` on its strings.
- Text on a picture comes ONLY from the kit's own tools; they run the type gate (Chrome's report of
  the font of every glyph: a system-font fallback, a face that did not load, text out of its box or
  chip fails) and a failing picture is NOT written (exit 2): fix the text and run again. Never your
  own HTML/Pillow text, never a font or weight the tools do not load, never a work-around.
- Signs the page's fonts lack are drawn as shapes by the tools (▲ ▼ ■ ← → · ✓: `fatype.symbols`, the
  engines' `tri()`); do not type them into Persian text yourself.
- Figures: Persian digits where the page writes Persian digits; up to 4 digits no separator, 5+ «٬»;
  decimals «/» («۲/۱»: the Arabic decimal mark reads like «ر» in AnjomanMax and Estedad); never
  «’» or «'» in a figure. Check strings: `VENV/bin/python -I /home/studio/kits/fa-type/tools/type_gate.py --json spec.json`.
- Read every picture at full size for the figures (crop if small) before delivery.
