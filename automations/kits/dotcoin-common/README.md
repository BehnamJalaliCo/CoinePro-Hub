# DotCoin.me (Instagram @DotCoinMe since 2026-11-26 — username dotcoinme, was @dotcoin.me; site dotcoin.me; «Dot Coin | بهنام جلالی») — what every DotCoin kit shares

The owner's fourth page (2026-11-16), under IG-Hub (company IG), designed anew: nothing of its look,
voice or cover is taken from Pro-Chart or Zarib×100.

- DIRECTION.md — the direction bible: the owner's rules, the Pinterest-first look, the voice (Arlo).
- cover/COVER_SYSTEM.md — the owner's own cover system (he is on every cover, a new suit each time;
  ONE family since 2026-11-19: always the mustard ground, a clean or full-length bottom).
- brand/README.md — the two colours, the fonts, the page's mark.
- tools/cutout.py — a person or subject cut out (ISNet, onnxruntime) as RGBA.
- tools/cover_compose.py — the cover composed exactly (Chromium): ground, giant English words behind
  the cut-out, the Persian title bar, the topic's real logo.
- tools/cover_sheet.py — the cover's row check: the new cover beside the last 4 (cover/family/) and
  a ground check; run it and read the sheet before every delivery.
- tools/pin_find.py — Pinterest search (signed out: read from the page's own results), numbered sheets.
- tools/pin_get.py — the chosen pins downloaded (pictures, videos, 4 frames each) + a sheet.

Beside the kit on the workshop only (personal or licensed, never in git):
- /home/studio/kits/dotcoin-common/brand/profile_ig.jpg, logo_round.png — the page's photo (its mark).
- /home/studio/kits/dotcoin-common/cover/refs/ — the owner's reference photos (also IG-Hub files,
  their ids in cover/COVER_SYSTEM.md).
- /home/studio/kits/dotcoin-common/cover/family/ — the page's newest 4 PUBLISHED reel covers, named
  <YYYY-MM-DDTHHMMZ>_<P-ref>_<sha8>.jpg (the row tools/cover_sheet.py compares with). Kept current
  automatically: the DotCoin site's youtube.py (dotcoin-youtube.timer, every 15 minutes) writes them
  from the hub's media.publications covers after each pass and removes the rest.
- /home/studio/kits/fonts-pro — IRANYekanX Pro (the owner's licence) + Anton and Bebas Neue (OFL).
- /home/studio/kits/models/isnet-general-use.onnx — the cut-out model (Apache-2.0).
Run the tools with /home/studio/kits/prochart-reels/venv-render/bin/python and
PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.

## TYPE GATE (2026-11-27, every page — /home/studio/kits/fa-type/README.md)
DotCoin's stories of 11-27 went out with figures a SYSTEM font drew (zeros as squares, «٬» as «’»):
an improvised renderer named a font it never loaded. From now on cover_compose.py gates the cover.
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
