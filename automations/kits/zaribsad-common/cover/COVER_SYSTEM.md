# Zarib100x — the cover package: THE MINT ARCH (owner, 2026-11-26)

The owner: «کاورش رو باید چت جی پی تی بزنه یا جمنای، خیلی باید حرفه‌ای باشه و مثل دات‌کوین براش یه پکیج درست کن».
So, as on DotCoin, **ChatGPT draws the WHOLE cover** — the owner himself, the arch, the words, the Persian title, the
chip and the pill — from this package: his photos, the style board and two sample covers (all registered as
TradeYar files, below), and a precise brief. Every @Zarib100x reel cover (12:00 and 19:00) is ONE family.

**The family (the page's own, never DotCoin's):** a dark wine ground with a soft oxblood light; behind him a tall
**mint arch** (a rectangle with a semicircular top — the mint of his profile photo); him in front, waist up or knees
up, in a new suit; at the top a small «Zarib100x» (left) and a short English tag (right, e.g. `COIN · SOL/USDT`);
the heavy ivory Persian title under him, its key word in a **rounded mint chip with dark letters**; under it an
**ivory-outlined pill** «کلمه‌ی «…» رو کامنت کن» with the word in mint. No giant English words, no mustard, no arrow
(those are DotCoin's). Colours: wine-black #160A0E, oxblood #461A23, Zarib Mint #83CAAD, ivory #F4EFE6
(brand/README.md); only his suit, accessories and the element keep their own colours.

## ONE FAMILY — hard rules
1. **Always the dark wine ground and the mint arch behind him**, the small «Zarib100x» and the tag at the top, the
   ivory title with ONE word in the mint chip, the ivory pill. Never another ground, never a mint ground, never the
   arch missing.
2. **The bottom is clean:** his body ends behind the title (waist up or knees up) and fades into the dark ground;
   never legs or shoes under the title, never a body cut by the pill.
3. **The row check before delivery:** `PY -I COMMON/tools/cover_sheet.py out/cover.jpg qc/cover_sheet.jpg` must print
   `ground ok`, `arch ok`, `chip ok` (exit 0) and puts the cover beside the page's last 4 (the covers earlier
   sessions kept as qc/z100x_cover.jpg; the samples fill the row at first). Read the sheet: the same family, AND a
   suit, pose, element and title that differ from the four beside it. Then `cp out/cover.jpg qc/z100x_cover.jpg`.

## New with every cover
- **A suit designed for this cover**, in colours that sit on mint and wine: oxblood/burgundy, charcoal, ivory or
  cream, camel, chocolate brown, bottle green, black tuxedo, chalk-stripe grey, double-breasted navy-black … — a
  different cut and colour each time, with a perfect set (shirt, tie or open collar, pocket square). Never a mint
  suit (it would vanish into the arch).
- **2026 accessories, at most two:** optical frames or sunglasses of this year's shapes, a premium watch, a lapel pin,
  a ring — no visible brand logos.
- **A pose that tells the title:** arms crossed, pointing at the title, index finger up, holding the element, hand
  on chin, adjusting a cuff, three-quarter turn …
- **ONE element of the reel**, photoreal, in his hand or beside him: the coin itself as a precious object (its real
  logo on it), an hourglass for a stop loss, a key, a vault door detail, a phone with a plain glowing screen, a gift
  box for a campaign, a newspaper for the market …
- **Anatomy and identity:** his face exactly as photos 1–2 (bald head, eyes, eyebrows, nose, full dark beard and its
  shape, jaw; glasses only when briefed), natural proportions (head : body ≈ 1 : 7.2), normal hands.

## How to make it (send it EARLY, with the reel's plates)
1. **The brief line** in direction/CONTRACT.md: tag · title (+ the chip word) · the comment word · his framing (waist
   up / knees up) and side (centre / left / right of the arch) · pose · suit · accessories · element. Pick a suit, a
   pose and an element that differ from the last 4 covers (`ls -t /home/studio/hq-workspace/*/qc/z100x_cover.jpg | head -4`, Read them).
2. **ONE `substitute.call`:** seat **creative**, kind **image**, placement **other**, player **gpt**,
   `file_ids` = ALL EIGHT ids below in that order (his five photos, the board, the two samples) — the hub runs it as
   ChatGPT's cover task with the files attached — `input_md` = the brief below, every «…» filled. ChatGPT down or
   refusing: the same call with player **gemini** WITHOUT file_ids (Gemini takes text only) as the second source.
3. **Look at it** (Read) as the strictest art director, beside the two samples:
   - the Persian title and the pill letter by letter EXACTLY as asked (no missing, extra or swapped letter, the right
     dots, right to left), the chip around the right word, «Zarib100x» and the tag spelled right;
   - his face (the man of photos 1 and 2), proportions, hands; the suit, accessories and element as briefed;
   - THE FAMILY (rules 1–2); crisp, no particles, haze, grain or glow on the picture; nothing else written;
   - the row check (rule 3).
   Wrong: ask again (≤ 2 more), saying exactly what was wrong («the word «…» was written «…»», «the arch is missing»,
   «his legs show under the title: end his body behind the title»).
4. **Persian still wrong after 3 tries (the fallback, only then):** ONE more call with the same brief but «leave the
   area under him EMPTY — no Persian title, no pill, no chip (keep «Zarib100x» and the tag at the top)», then set the
   title, the chip and the pill yourself on that picture:
   `PY -I COMMON/tools/cover_compose.py build/cover.json` with `{"background": "in/<picture>", "title": ["…", "…"],
   "word": "<comment word>", "out": "out/cover.jpg"}` (IRANYekanX Pro, the family's exact chip and pill).
5. **Size:** fit to 1080×1920 (Lanczos; extend the dark ground at the sides if narrower than 9:16, never crop his
   head or the title) → `out/cover.jpg` (quality 92). His face and the title inside the grid's 3:4 crop (y 240–1680).
6. **The row check on the final file** (rule 3), then `cp out/cover.jpg qc/z100x_cover.jpg`. No image maker answers
   (limit, down): `order.progress` «کاور منتظر ChatGPT» and ask again next turn; never a cut-out of his photo pasted
   by you, never a frame of the video.

### The eight files (TradeYar files on the hub; the originals in /home/studio/kits/zaribsad-common/cover/refs/ and cover/samples/, board.png)
| # | id | what |
|---|---|---|
| 1 | `f7ffb453-84a0-44c6-88c8-71bb216e3385` | photo 1 — the page's profile: oxblood suit, glasses, mint backdrop (identity) |
| 2 | `8a00bac5-fb3f-4eeb-942b-c6ef916a68d8` | photo 2 — his face, front (identity) |
| 3 | `4ba82a8f-9fe1-4f53-addb-63cd8ef6d5a1` | photo 3 — sunglasses, three-quarter |
| 4 | `719ca865-bea4-4954-8f1e-314ec86fcf11` | photo 4 — full body (proportions) |
| 5 | `7bf0f32b-e8f3-4bbd-828d-eb347df4414e` | photo 5 — formal suit and tie |
| 6 | `41d8da66-8ca9-47b1-8815-6d3ae6272b73` | the style board (cover/board.png) |
| 7 | `ed2402ab-ac52-4e7a-9fb2-4419920114c0` | sample cover 1 «سولانا نصف شد» (cover/samples/sample_1_coin.jpg) |
| 8 | `ef442a3e-3902-46bb-a0ac-4498ba20863d` | sample cover 2 «حد ضرر» (cover/samples/sample_2_lesson.jpg) |
(files.files is in the hub wipe: after a wipe the hub's Claude registers these again — company TY — and puts the new
ids here. The samples were composed in code from his photos to show the family; his face and suit are real, the new
covers must be new designs.)

### The brief (fill every «…»; keep the Persian EXACT)
```
I attach my cover package. Photos 1-5 are ME, the page owner (Behnam), who asks for this cover of himself.
Image 6 is my style board; images 7 and 8 are two sample covers of my page: follow THEIR style exactly, with a new
design. Never copy the board's labels or swatches into the cover.

Make ONE new vertical 9:16 Instagram reel cover (1080x1920) for my page Zarib100x (a premium Persian crypto-trading page).

THE STYLE (as in images 7 and 8): a dark wine background (#160A0E) with a soft oxblood (#461A23) studio light; behind
me a tall flat MINT (#83CAAD) arch — a rectangle with a semicircular top — from the upper part of the frame down to my
chest; me in front of the arch as a clean, sharp, premium studio photo; at the very top a small «Zarib100x» on the left
(«Zarib» ivory, «100x» mint) and a small English tag on the right; under me the Persian title in a heavy geometric
Persian sans-serif (like IRANYekanX ExtraBlack), ivory #F4EFE6, centred, with ONE word inside a rounded MINT box with
dark wine letters; under the title an ivory-outlined pill. Minimal, high contrast, very premium, readable as a small
square in the grid. No texture, no grain, no glow, no particles.

THIS COVER: me …WAIST UP / KNEES UP…, …centred / slightly left / slightly right… in front of the arch; my body ends
behind the title and fades into the dark background — nothing of me under the title, no legs.

ME: exactly the man of photos 1 and 2 — bald head, the same eyes, eyebrows, nose, full dark beard and jaw; do not
change or beautify my face. Natural proportions as in photos 4 and 5 (head to body about 1:7.2). Pose: …. Expression: ….
OUTFIT, designed for this cover: …a tailored suit (cut, colour, fabric — never mint), shirt, tie or open collar,
pocket square… — a perfect, current 2026 menswear set that looks great on mint and wine.
ACCESSORIES of 2026 (at most two): …. No visible brand logos.
ELEMENT (one, fits the video): …, photoreal, …in my hand / beside me….

THE TEXT — write these EXACTLY, letter by letter, nothing added, nothing changed:
- Top left, small: «Zarib100x». Top right, small, English: «…TAG…».
- Persian title, right to left: line 1 «…»; line 2 «…»; the word «…» inside the rounded mint box with dark letters.
- The pill (ivory outline, ivory letters): «کلمه‌ی «…» رو کامنت کن», with the word «…» in mint.
Write every Persian word with normal, compact letter joins: no kashida, no stretched strokes.
No other words, letters, numbers, logos or watermarks anywhere (a coin's own real logo only on the coin element).
Keep my face and the Persian title inside the central 3:4 area of the frame.
```

## Never
- Another ground than dark wine; the arch missing; mustard, giant English words or an arrow (DotCoin's).
- Legs or a body under the title; a cover delivered without its row check.
- An AI-made logo; a video frame as the cover; Persian with a wrong letter (check every one); a cut-out of his photo
  pasted by you as the cover (the samples were made that way only to show the family).
- TradeYar's logo, or any logo but a coin's or an exchange's real one on the element.
