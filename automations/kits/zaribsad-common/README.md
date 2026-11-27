# What every Zarib100x kit shares (zaribsad-noon, zaribsad-coin, zaribsad-stories) — THE DESK (2026-11-26)

The page @Zarib100x (was @zaribsad; TradeYar, company TY). Its look, voice and cover were redesigned on the owner's
order of 2026-11-26: «even higher than DotCoin, different in level, type and everything». Read in this order:
- `DIRECTION.md` — the bible: the owner's rules, the format (THE DESK: every reel a BRIEF), motion, sound, the
  day's look, the QC gate.
- `brand/README.md` — the two colours from the profile photo (Zarib Mint #83CAAD + Oxblood #461A23), three layers, the meaning rule (▲/▼), type, the mark;
  `brand/board.png` the board; `brand/tokens.json`.
- `cover/COVER_SYSTEM.md` — the cover package: ChatGPT draws the WHOLE cover with the owner (DotCoin-style), ONE family (the mint arch), 8 TradeYar files; refs/ on the workshop only.
- `motion/README.md` — THE DESK library (desk.js), its engine (desk_engine.py) and its sound (desk_audio.py);
  `motion/sample/` a working sample brief.
- The narrator: **Charon** (`speech.make` voice "Charon", no style, no narrator.set) — the desk's anchor: an
  informative, measured male voice; not Cruz (Pro-Chart), not Arlo (DotCoin, behnamjalali.tech).

Tools (PY = /home/studio/kits/prochart-reels/venv-render/bin/python, PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright):
- `tools/tape.py` — the HUD's price tape (real tickers, the morning of the build) → qc/tape.json.
- `tools/textlint.py` — the text gate: on-screen strings, caption, comment (old names, full stops, mixed digits,
  kashida, Arabic ي/ك, disclaimers, «ویفنس», hashtag count, button length).
- `tools/cover_compose.py` — the FALLBACK only: the Persian title, chip and pill set on ChatGPT's picture (and the samples).
- `tools/cover_sheet.py` — the cover's row check beside the last 4.
- `tools/make_board.py` — renders brand/board.png and cover/board.png again (after a new profile photo).
- `fonts/` — IBM Plex Mono and IBM Plex Sans Condensed (SIL OFL 1.1, `OFL-IBMPlex.txt`).

## TYPE GATE (2026-11-27, every page — /home/studio/kits/fa-type/README.md)
DotCoin's stories of 11-27 went out with figures a SYSTEM font drew (zeros as squares, «٬» as «’»):
an improvised renderer named a font it never loaded. From now on desk.js draws ▲/▼ as shapes and writes decimals «/»; cover_compose.py gates the cover.
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
