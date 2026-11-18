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
- **THE HERO IS THE COVER** (the coordinator's review, 2026-11-18): a BIG, glossy, glowing 3D object, 35–45 % of
  the height, with depth, reflections and a light bloom on its base — the star compass, the code window wired to
  the ChatGPT and GitHub tiles, the Claude ✳ and Docker 3D tiles on a glowing platform. For a product: its real
  logo as a glossy 3D glass tile on a glowing circular platform. Made by the hub's creative image call
  (substitute.call seat creative, kind image, player **gpt**, and the same brief to player **gemini**; keep the
  better): "A premium glossy 3D tech illustration for a social media cover: <the object: e.g. a floating rounded
  glass app tile showing the <vendor> logo>, glowing electric neon blue, a bright star burst of light behind it,
  standing on a glowing circular light platform with reflections, deep blue neon rim light, cinematic depth,
  centered, on a PURE BLACK background (#000000, nothing else). No text, no letters, no numbers, no watermark.
  Square image." card.py crushes its near-black and feathers its edges, so it melts into the navy.
  **A published cover NEVER uses a glyph:** card.py refuses a cover without `element`. A failed or wrong picture:
  ask again, or the other player; the cover waits for its hero. No person, no face.
- **No** LUMEN spectrum, no mustard, no frame, no handle text on the cover.

## The reel cover (1080×1920, `out/cover.jpg`)
`PY -I COMMON/tools/card.py direction/cover.json out/cover.jpg`, the spec:
```
{"type": "cover", "layout": "top", "chip": "<a short pill>", "title": "<line 1>|<line 2>", "keys": ["<blue word>"],
 "latin": "<the Latin name, big>", "latin_first": false, "sub": "<a small grey line>",
 "element": "assets/use/<the hero on black>.png", "top": 300}
```
- `layout` `top` (most covers: the title on top, the element under it) or `split` (the title a block on the left,
  the element on the right: «سریع‌تر کد بزن!»); `|` breaks a title line where you want it.
- Keep the title inside y 300–900 (Instagram's grid crops the top and bottom of a 9:16 cover).
- The title block is fitted to the width by card.py (`fit` 900 px, `px` the cap 190): short lines, big type,
  like the old covers; the hero is placed under the title block, whatever its height.
- Read the result at full size: every letter, nothing on an edge (`card.py` prints `ok` or `overflow`).

## The YouTube thumbnail (1280×720, `out/thumbnail.jpg`) — the same family, wide
`{"type": "thumb", "chip": "ویدیوی کامل", "title": "<2–3 words>|<the hook>", "keys": […], "latin": "…",
"element": "assets/use/<element on black>.png"}` — the background cropped wide, the title on the right with its
blue key word, the element on the left. Two candidates; keep the one that reads at 160 px wide.

## A session that already made a cover in the old LUMEN style
Make it again with this file's spec (the same title and element; the old one is never published).
