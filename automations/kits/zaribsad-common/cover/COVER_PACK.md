# Zarib ×100 (@zaribsad) — the cover pack (owner, 2026-11-15)

The owner: «یه فایل پک برای کاور zaribsad درست کن که ۳ یا ۲ رنگ خاص توش به کار رفته باشه که رنگ
سازمانیمون باشه، که هر بار خواست کاور بسازه اونو بده به چت جی پی تی تا چت جی پی تی هم تایتل بذاره با
فونت خودمون و یک المان مناسب با موضوع بذاره.»

Every reel's cover (the 12:00 and the 19:00) is made by **ChatGPT from this pack**: the page's three
colours, the title in our font, and ONE element of the reel's topic. The grid of the page then reads
as one brand.

## The pack
- `board.png` (1080×1920; source `board.svg`, rendered with the Eco fonts): the three colours with
  their codes and shares, the title font's specimen, the layout (title in the central square, the
  element, the 1:1 and 4:5 grid crops). **In the hub it is TradeYar's file
  `6d4768ed-ffe7-415e-8814-bb750e72b6fd`** — attach it by that id.
- The colours (TradeYar's registered brand, the hub's brand row for TY):
  - **Navy #030B26** — the background, ~70 %
  - **Teal #0FB5AE** — light, glow, rim light, the title's key word, ~20 %
  - **Off-white #F4F7FF** — the title, ~10 %
  The element may carry its own natural colour where the topic needs it (a gold coin, an exchange's
  real colour), never the title or the background.
- The title font: **IRANYekanX Eco, Bold** (/home/studio/kits/fonts-eco). ChatGPT cannot load a font
  file: it copies the letterforms from the board's specimen (heavy, geometric, even stroke, round
  counters, flat terminals — never calligraphic, never Nastaliq, never a thin or serif face).

## How to make the cover (the kit's cover step)
1. Choose the title: 2–4 Persian words, the reel's hook at its most striking (e.g. «پول نامرئی»),
   and its ONE key word for the teal. Choose the element: one object or scene that tells the topic at
   a glance (the coin itself as a 3D object, a sealed glowing letter, a chart line breaking out, an
   exchange gift box …) — never a person's face unless the reel is about a person.
2. ONE `substitute.call`: seat **creative**, kind **image**, placement **other**, player **gpt**,
   `file_ids: ["6d4768ed-ffe7-415e-8814-bb750e72b6fd"]`, `input_md` = the brief below filled in.
   (The hub runs it as ChatGPT's cover task with the board attached; Gemini cannot take attachments.)
3. Look at it (Read): the title letter by letter (every dot and every letter joined right), the
   key word in teal, the colours, the element, nothing else written, the title inside the central
   square. Wrong: ask again (≤ 2 more), saying exactly what was wrong.
4. Still wrong letters after 3 tries: ONE more call with the same brief but «leave the title area
   empty — no text at all», and set the title yourself in IRANYekanX Eco Bold (white #F4F7FF, the key
   word teal #0FB5AE, the board's size and place). Our font, exactly.
5. Upscale to 1080×1920 (Lanczos), check the 1:1 and 4:5 crops (the title survives both),
   `out/cover.jpg` (quality 92).

## The brief (fill the three «…»)
```
Make ONE new vertical 9:16 Instagram reel cover (1080x1920) for the Persian crypto page «Zarib×100».
The attached picture is our brand board: a STYLE GUIDE ONLY. Do not copy the board, its swatches,
its labels or its layout sketch into the cover.

Follow the board exactly:
- Colours: only deep navy #030B26 (background, about 70%), teal #0FB5AE (light, glow, rim light and
  the key word, about 20%) and off-white #F4F7FF (the title, about 10%). The element may keep its own
  natural colour; nothing else.
- Title: the Persian words «…TITLE…» — exactly these letters, right to left, nothing added or
  changed — big and bold in the board's title font (the heavy geometric Persian sans-serif of the
  specimen «پول نامرئی»: even stroke, round counters, flat ends; never calligraphic). Off-white, with
  the word «…KEY WORD…» in teal. At most two lines, inside the central square of the frame (it must
  survive a 1:1 and a 4:5 crop), in its upper half.
- Element: …ONE ELEMENT OF THE TOPIC…, under or behind the title, cinematic 3D or premium
  illustration, teal rim light, depth, soft glow, clean navy space around it.
- Nothing else: no other words, letters, numbers, logos, watermarks, frames, borders or UI.
- Premium, clean, cinematic, high contrast; readable as a small square in the grid.
```

## Never
- No TradeYar logo (or any logo but a real coin's or exchange's when the topic is that coin or
  exchange, as the element itself). See COMMON/brand/README.md.
- Never a frame of the video as the cover.
