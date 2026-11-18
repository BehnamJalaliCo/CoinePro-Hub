# The covers (reel) and thumbnails (YouTube) — EXACTLY the page's own established covers

⟨2026-11-18⟩ The owner: «کاورش هم نگاه کن ببین چطوری ساخته شده … دقیقا عین کاور های قبلی ریلز هاش ساخته بشه». The
page's 24 posts before the automation all share ONE cover family; every new cover is that family, never a new
look (the LUMEN look is the VIDEO's, not the cover's). Read with the eyes: `refs/old_reel_covers.jpg` (its reel
covers) and `refs/old_post_covers.jpg` (its posts), and the new ones beside them in `refs/new_vs_old.jpg`.

## What the family is (measured on the 14 old reel covers)
- **The background:** `background.jpg` — the owner's own (sent 2026-11-18): dark navy, glowing electric-blue
  diagonal light lines top-left and bottom-right, two small dot grids. The same on every cover; never another.
- **The title:** a heavy Persian display (IRANYekanX ExtraBlack, the owner's licensed pack in fonts-pro), WHITE,
  2–4 short lines, centred in the top third (or a left block, «split»), with ONE or TWO key words in an
  electric-blue gradient (#5CB8FF → #2A86FF → #1A5CFF) and a soft blue glow. Latin names in Geist Black, white
  to blue. Short and punchy: «مدل جدید GPT»، «سریع‌تر کد بزن!»، «لیمیتت تموم شد؟ اینو ببین!».
- **A small grey line** under the title (sometimes) with a short blue light bar under it; **a blue pill** on top
  (sometimes): «آموزش قدم‌به‌قدم»، «پروژه متن‌باز»، «خبر داغ».
- **ONE glowing neon element** under the title (or beside it in «split»): a 3D neon-blue icon or illustration of
  the topic — a brain chip, a terminal window, two logos linked by a light beam, a game controller with «AI», a
  star burst. Made by ChatGPT AND Gemini (substitute.call creative, kind image, the better of the two) ON PURE
  BLACK, so card.py blends its black away: brief "a single glowing neon electric-blue 3D icon of <the subject>,
  premium tech illustration, centered, on a pure black background, no text, no letters, no numbers, no
  watermark" (a real product's logo only as the vendor draws it). No person, no face (the old covers have none).
- **No** LUMEN spectrum, no mustard, no frame, no handle text on the cover.

## The reel cover (1080×1920, `out/cover.jpg`)
`PY -I COMMON/tools/card.py direction/cover.json out/cover.jpg`, the spec:
```
{"type": "cover", "layout": "top", "chip": "<optional pill>", "title": "<line 1>|<line 2>", "keys": ["<blue word>"],
 "latin": "<optional Latin name>", "latin_first": false, "sub": "<optional small grey line>",
 "element": "assets/use/<element on black>.png", "element_top": 900, "element_h": 640, "top": 300, "px": 112}
```
- `layout` `top` (most covers: the title on top, the element under it) or `split` (the title a block on the left,
  the element on the right: «سریع‌تر کد بزن!»); `|` breaks a title line where you want it.
- Keep the title inside y 300–900 (Instagram's grid crops the top and bottom of a 9:16 cover).
- No element yet (a picture refused twice): `"element_text": "</>"` (or «{ }», «AI») draws a neon glyph.
- Read the result at full size: every letter, nothing on an edge (`card.py` prints `ok` or `overflow`).

## The YouTube thumbnail (1280×720, `out/thumbnail.jpg`) — the same family, wide
`{"type": "thumb", "chip": "ویدیوی کامل", "title": "<2–3 words>|<the hook>", "keys": […], "latin": "…",
"element": "assets/use/<element on black>.png"}` — the background cropped wide, the title on the right with its
blue key word, the element on the left. Two candidates; keep the one that reads at 160 px wide.

## A session that already made a cover in the old LUMEN style
Make it again with this file's spec (the same title and element; the old one is never published).
