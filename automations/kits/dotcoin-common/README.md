# DotCoin.me (@dotcoin.me, «Dot Coin | بهنام جلالی») — what every DotCoin kit shares

The owner's fourth page (2026-11-16), under IG-Hub (company IG), designed anew: nothing of its look,
voice or cover is taken from Pro-Chart, Zarib×100 or ipoxxo.

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
