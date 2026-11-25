# Zarib100x — the cover system: THE BRIEF CARD (owner, 2026-11-26)

Every reel cover of @Zarib100x (the 12:00 and the 19:00) is ONE family, so the grid reads as one premium desk:
an obsidian card with violet crop-mark corners; a photoreal hero plate in its upper part, lit violet; under it the
mono tag (COIN / LESSON / CAMPAIGN / MARKET / NEWS + a ticker or a label), one real number when the reel has one,
the Persian title in IRANYekanX Pro ExtraBlack with its key word in the violet chip, the Zarib Line, and the
lockup «Zarib100x» with the brief's number. `samples/` holds two (their plates are code-drawn stand-ins; yours is
ChatGPT's photoreal plate). `board.png` is the style board ChatGPT gets with the plate brief.

**Why this way:** ChatGPT draws the PICTURE (what it is best at); the TYPE is set by our tool in our fonts, so every
letter is exact and every cover sits in the same family to the pixel. No cover with a misspelled Persian word, no
cover that drifts off the family. (DotCoin's covers are the owner himself on mustard; Zarib100x has no person on
the cover — the subject is the market.)

## ONE FAMILY — hard rules
1. **Only `tools/cover_compose.py` sets the cover's type layer.** Never a cover typed by ChatGPT or Gemini, never a
   frame of the video, never another layout.
2. **The ground is obsidian** (#0A0814), the light violet (#8A3FFC). The plate's subject in its own natural colours
   (a coin's own colours, metal, glass), lit by violet; nothing else colourful.
3. **Title:** 2–5 Persian words in 1–2 lines, the reel's hook at its most striking, ONE key word in the chip; no
   full stop; the tool fits both lines to one size (96–138 px) or refuses (shorten it). A number only if it is
   the reel's real number (`number`, `number_dir` = its meaning colour).
4. **The row check before delivery:** `PY -I COMMON/tools/cover_sheet.py out/cover.jpg qc/cover_sheet.jpg` prints
   `ground ok`, `zline ok`, `ticks ok` (exit 0) and puts the cover beside the page's last 4. Read the sheet: the
   same family, AND a different plate subject, title and tag from the four beside it. Then
   `cp out/cover.jpg qc/z100x_cover.jpg` (tomorrow's row reads it).

## How to make it (the reel's cover step — send the plate brief EARLY, with the reel's plates)
1. **The brief line** in direction/CONTRACT.md: kind · tag · title (+ key word) · number (or none) · the plate's
   subject (ONE object or scene that tells the topic at a glance: the coin as a precious object; a glass hourglass
   for a stop loss; a sealed vault door for a campaign's bonus; a skyline at the opening bell for the market …) ·
   its camera (low angle / three-quarter / macro / top-down).
2. **The plate:** `substitute.call` seat **creative**, kind **image**, placement **other**, player **gpt**, with
   `file_ids: ["<COVER_BOARD_ID>"]` (the table below) so the hub runs it as ChatGPT's **cover** task with the
   board attached; `input_md` = the brief below. The SAME brief once more with player **gemini** (no file_ids;
   Gemini takes text only). Keep the better one.
   *While the id below says PENDING (the board is not registered as a TradeYar file yet), send the gpt call
   without `file_ids`: the brief alone is complete.*
3. **Look at it** (Read): photoreal or a premium 3D render, crisp, ONE subject in the upper ~60 %, the lower ~35 %
   clean dark obsidian, violet light, NO text, letters, numbers, logos (except a coin's real logo ON the coin when
   that is the subject), no particles, haze, bokeh or grain. Wrong: ask again (≤ 2 more), saying exactly what.
   No image maker answers (limit, down): `order.progress` «کاور منتظر تصویر» and ask again next turn; never a
   code-drawn plate, never a video frame.
4. **Compose:** a spec (the tool's docstring) → `PY -I COMMON/tools/cover_compose.py build/cover.json` →
   `out/cover.jpg` (1080×1920; Instagram's grid crops: 3:4 = y 240–1680, 1:1 = y 420–1500 — the tag, the title and
   the Zarib Line are inside both).
5. **Check:** Read out/cover.jpg at full size (every letter, the chip on the right word, the number = the reel's),
   then the row check (rule 4).

### The reference file (IG-Hub / hub files of TradeYar)
| id | what |
|---|---|
| `PENDING` | `zaribsad-common/cover/board.png` — the style board (colours, the two sample covers, the plate rules). The hub's Claude registers it as a TradeYar file and puts its id here (and again after a files wipe). |

### The plate brief (fill every «…»)
```
Make ONE vertical 9:16 picture (1080x1920) for the cover of «Zarib100x», a premium Persian crypto-trading page.
If a board is attached, it is a STYLE GUIDE ONLY: never copy the board, its text, its swatches or its sample
covers into the picture.

THE PICTURE: …ONE SUBJECT (the coin as a precious object / an hourglass / a vault door / …)…, …CAMERA (low
three-quarter angle / macro / top-down)…, photorealistic, 4K ultra-detailed, razor-sharp, shot on a full-frame
cinema camera (or: a premium 3D product render).
LIGHT AND COLOUR: a near-black obsidian background with a violet tint (#0A0814); a violet (#8A3FFC) key light and
rim light from the upper right; the subject in its own natural colours and materials; deep, clean shadows.
Nothing else colourful.
COMPOSITION: the subject in the UPPER 60% of the frame, centred or slightly right; the LOWER 35% is clean, empty,
dark obsidian (our title goes there) — no objects, no reflections, no floor detail there.
NEVER: text, letters, numbers, logos (…except the coin's own real logo on the coin…), UI, screens with readable
content, watermarks, frames, borders, particles, smoke, haze, rain, bokeh, lens flares, film grain, blur,
people's faces, anime or cartoon style.
Premium, minimal, cinematic, high contrast; the subject must read as a small square in the grid.
```

### The spec (cover_compose.py)
```
{"plate": "in/<the picture>", "focus": "50% 40%", "kind": "COIN", "tag": "SOL/USDT",
 "title": ["سولانا [نصف] شد", "حالا چی؟"], "number": "-48.8%", "number_dir": "down",
 "brief": <the reel's NNN>, "out": "out/cover.jpg"}
```
- kind: the 19:00 reel `COIN` (tag = `<SYMBOL>/USDT`); the 12:00 reel by its kind — آموزش `LESSON` (tag = the
  idea in 1–3 Latin words, e.g. `STOP LOSS`, `RISK / REWARD`), کمپین صرافی `CAMPAIGN` (tag = the exchange, e.g.
  `WEEX`), خبر و بازار `MARKET` or `NEWS` (tag = e.g. `BTC/USDT`, `FEAR & GREED`).

## Never
- A cover typed by an image model; a video frame as the cover; a code-drawn plate.
- TradeYar's logo or any logo but a coin's or an exchange's real one as the subject itself.
- Another ground than obsidian; mustard, gold, teal or navy as a dominant colour; a person's face.
- A cover delivered without its row check.
