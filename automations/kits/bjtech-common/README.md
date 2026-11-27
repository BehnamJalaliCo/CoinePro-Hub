# bjtech-common — what every @behnamjalali.tech kit shares (owner 2026-11-18)

The page @behnamjalali.tech («Behnam Jalali | AI & Tech», IG-Hub account 3, company IG) and its YouTube channel
@behnamjalali-tech. Its own language, LUMEN: read `DIRECTION.md` first, every time.

- `DIRECTION.md` — the design language, the words, the pictures, the look of the day, the QC.
- `brand/config.json` — the page's links, the ONE place for them (Telegram t.me/behnamjalali_tech, YouTube
  @behnamjalali-tech): every caption, DM, end card and description reads it. Never hard-code a link elsewhere.
- `brand/profile.jpg`, `brand/profile_round.png` — the owner's profile photo (the end card's mark).
- `brand/README.md` — colours, fonts, the handle.
- `cover/COVER_SYSTEM.md`, `cover/background.jpg`, `cover/refs/` — the reel cover and the YouTube thumbnail: EXACTLY
  the page's own established family (the owner's navy background, 2026-11-18), set in code by `tools/card.py`.
- `tools/card.py` — every still of the page in code (cover, story card, breaking flash card, thumbnail), so every
  Persian letter is exact; an AI picture is only ever the picture inside a card.

Kits: `bjtech-reels` (two reels a day), `bjtech-stories` (12 story cards a day), `bjtech-breaking` (the breaking
news: the flash story and its full reel), `bjtech-longform` (the daily 8–15 minute YouTube video).
Fonts (OFL, outside git): /home/studio/kits/fonts-bj (Estedad 8.5, Geist 1.8.2, Geist Mono 1.8.2).

## TYPE GATE (2026-11-27, every page — /home/studio/kits/fa-type/README.md)
DotCoin's stories of 11-27 went out with figures a SYSTEM font drew (zeros as squares, «٬» as «’»):
an improvised renderer named a font it never loaded. From now on card.py gates every card; the stage engine writes decimals «/».
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
