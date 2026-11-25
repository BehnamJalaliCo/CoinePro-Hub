# What every Zarib100x kit shares (zaribsad-noon, zaribsad-coin, zaribsad-stories) — THE DESK (2026-11-26)

The page @Zarib100x (was @zaribsad; TradeYar, company TY). Its look, voice and cover were redesigned on the owner's
order of 2026-11-26: «even higher than DotCoin, different in level, type and everything». Read in this order:
- `DIRECTION.md` — the bible: the owner's rules, the format (THE DESK: every reel a BRIEF), motion, sound, the
  day's look, the QC gate.
- `brand/README.md` — the two colours (Zarib Violet #8A3FFC + Obsidian #0A0814), three layers, type, the mark;
  `brand/board.png` the board; `brand/tokens.json`.
- `cover/COVER_SYSTEM.md` — the cover: ONE family, ChatGPT draws the plate, the tool sets the type.
- `motion/README.md` — THE DESK library (desk.js), its engine (desk_engine.py) and its sound (desk_audio.py);
  `motion/sample/` a working sample brief.
- The narrator: **Charon** (`speech.make` voice "Charon", no style, no narrator.set) — the desk's anchor: an
  informative, measured male voice; not Cruz (Pro-Chart), not Arlo (DotCoin, behnamjalali.tech).

Tools (PY = /home/studio/kits/prochart-reels/venv-render/bin/python, PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright):
- `tools/tape.py` — the HUD's price tape (real tickers, the morning of the build) → qc/tape.json.
- `tools/textlint.py` — the text gate: on-screen strings, caption, comment (old names, full stops, mixed digits,
  kashida, Arabic ي/ك, disclaimers, «ویفنس», hashtag count, button length).
- `tools/cover_compose.py` — the cover from ChatGPT's plate + the family's type layer.
- `tools/cover_sheet.py` — the cover's row check beside the last 4.
- `tools/make_board.py` — renders brand/board.png and cover/board.png again (after a new profile photo).
- `fonts/` — IBM Plex Mono and IBM Plex Sans Condensed (SIL OFL 1.1, `OFL-IBMPlex.txt`).
