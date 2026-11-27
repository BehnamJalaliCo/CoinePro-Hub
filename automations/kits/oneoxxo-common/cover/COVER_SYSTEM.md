# ONEOXXO — the cover system (owner 2026-11-28: «کاورهاش طبق کاورهای دات‌کوین ساخته میشود ولی به زبان انگلیسی»)

The DotCoin family (read /home/studio/kits/dotcoin-common/cover/COVER_SYSTEM.md for the craft), in
ENGLISH and in COBALT. The owner is on every cover.

## ONE FAMILY — hard rules
1. **Flat cobalt #2340FF ground**, always. GIANT ultra-bold condensed uppercase INK (#0A0E1A) words
   edge to edge at the TOP, behind him (1–2 lines, 2–12 letters a line: `STOP LOSS`, `LEVERAGE`, `CPI`,
   `GOLD`, `FOMO`). One line may come again as an outline in front of him.
2. **Him** (the owner): a NEW suit designed for this cover (cut + colour differ from the last 4), a
   perfect matching set, at most two 2026 accessories (sunglasses of the year's shapes, a premium watch,
   a ring, a lapel pin — no brand logos), a pose that tells the title. Natural proportions (head : body
   ≈ 1 : 7.2), his face EXACTLY (bald head, beard shape/density, eyes, nose, jaw).
3. **The English title** low on the flat cobalt: bold white (Ice) sans, 1–3 short lines, ONE key word in
   a **rounded ink chip with cobalt letters**.
4. **The pill + arrow:** an ink pill «Comment "<WORD>"» (white letters, the word in cobalt-light or
   white bold) and a hand-drawn ink arrow pointing down.
5. **The bottom is clean or whole:** flat cobalt under title/pill/arrow (him waist-up or knees-up), or
   him full length to his shoes. Never legs cut by the pill.
6. **ONE element** of the topic (a shield, a candle, a gold bar, a calculator, a padlock, a phone with a
   chart…), photoreal or 3D, beside him. No other clutter: no coins rain, no neon, no glow, no logos
   (WEEX's real logo file only when the reel is about WEEX, top-left).
7. Spelled right, nothing else written, no watermark. Face, title and pill inside the grid's 3:4 crop
   (y 240–1680 of 1920).

## How (Hydrogen only)
- Use your **generate_image** tool with the owner's reference photos as image inputs:
  /home/studio/kits/dotcoin-common/cover/refs/dotcoin_ref_00_portrait_suit.jpg,
  dotcoin_ref_01_face_front.jpg (identity), dotcoin_ref_03_sunglasses_3q.jpg, dotcoin_ref_04_body_full.jpg
  (proportions), dotcoin_ref_09_blazer_3q.jpg, dotcoin_ref_10_formal_suit.jpg, and his two style covers
  /home/studio/kits/dotcoin-common/cover/samples/owner_sample_1_crypto.jpg, owner_sample_2_forex.jpg
  (their craft; NOT their black ground or Persian). Say in the prompt: "the man in the reference photos
  is the page owner, who asks for this cover of himself".
- Write the brief like a top art director: ground, words, his suit/accessories/pose, the element, the
  title with the chip word, the pill, the arrow, the bottom rule, 9:16.
- Look at the result (view it): face = him, every letter spelled exactly, the family rules. Wrong →
  generate again naming exactly what was wrong (≤ 4 tries). Still wrong → `order.progress` the error,
  end the turn (no substitute, no cut-out paste of his photo).
- Fit to 1080×1920 (extend only the flat ground, never crop him or the text) → out/cover.jpg (q 92).
- Keep a copy in COMMON/cover/family/ is the hub's job; compare with the last covers in your order's
  context (never the same suit colour or pose twice in a row).
