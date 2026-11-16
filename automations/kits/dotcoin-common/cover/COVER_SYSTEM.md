# DotCoin.me — the cover system (the owner's own, Behnam_Cover_System_v1, + his words of 2026-11-16)

The owner is on every cover. «هر کاور یک کت و شلوار خاص برای من طراحی میشه با ست عالی با اکسسوری
های روز دنیا مثلا عینک ریبن ۲۰۲۶، سال رنگ های متنوع و تایتل مناسب ویدیو و المان مناسب ویدیو و دو
رنگ سازمانیشم همون دو رنگی.» The selected style: a flat ground, GIANT condensed English words behind
him (he overlaps them), the Persian title low in a bar. Minimal, high contrast, readable as a small
square in the grid.

## THE TARGET LOOK — the owner's own two sample covers (2026-11-16)
`/home/studio/kits/dotcoin-common/cover/samples/owner_sample_1_crypto.jpg` and
`owner_sample_2_forex.jpg` (he made them with ChatGPT from his pack). READ BOTH before every cover.
What they show:
- a black ground (B), the giant mustard English words EDGE TO EDGE (`CRYPTO CHANNEL`,
  `FOREX CHANNEL`), him in front of them;
- the Persian title set STRAIGHT ON THE GROUND (no bar): big and heavy, one line mustard or white,
  the key word in a **rounded mustard chip with black letters** («کریپتو», «فارکس»);
- the call to action in a **pill with a mustard outline** («کلمه «فارکس» را اینجا بفرست», the word in
  mustard) and a **hand-drawn mustard arrow** down toward the comments;
- sample 1: waist up, arms crossed, glasses, the title centred under him; sample 2: full body on
  the right, hands in pockets, the title in the free column on his left.

**The layout changes cover to cover** (the owner: «نه صرفا کلمه پشت سر باشه، میتونه متفاوت هم
باشه جای نوشته»): the words behind him, in front of him, as an outline over him, at the top, at
the bottom, or in a column; the title under him, beside him, or at the top; him on the left, the
right or the centre, full body, knees up or waist up. Never the same layout twice in a row; the
samples set the bar for craft, not one fixed template. `cover_compose.py` takes any of them.

## The fixed rules (his pack)
- **Two colours only for the design:** mustard **#F3C242** and black **#000000** (white only small).
  - **A:** mustard ground + black English words + black title bar (white Persian, mustard key word).
  - **B:** black ground + mustard English words + mustard title bar (black Persian, white key word).
  - The covers alternate A/B/A/B in the grid: **the day's first reel = A, the second = B** (a pilot
    = B, like the owner's samples).
- **English backdrop:** ultra-bold condensed UPPERCASE (Anton or Bebas Neue), 1–2 lines, 2–12
  letters a line, behind the subject; one line may be drawn again as an outline in front of him
  (the reference's «PAGE»). Short and strong: `COLD WALLET`, `SEED PHRASE`, `HALVING`, `NEWS`, `DCA`.
- **Persian title:** IRANYekanX Pro (Black / ExtraBlack / Heavy; the owner gives this font freer
  hands), 1–3 short lines, 72–110 px at 1080, ONE key word in a chip (or a number highlighted),
  set on the ground as in the samples (a solid bar only now and then, for variety). Never typed by
  an AI: set by `cover_compose.py`.
- **The call to action on the cover** when the reel has one (a comment word): the pill + the arrow
  of sample 2; otherwise the title alone.
- **Anatomy:** natural proportions — head : full body ≈ 1 : 7.2 (6.9–7.5), shoulders 2.6–3.0 head
  widths; never a big head; normal hands.
- **Identity:** his face exactly — bald head, eye spacing, eyebrows, nose, beard shape and density,
  jaw. Clothes and pose change every cover.
- **Clean:** no candles, coins, charts, neon, glow, particles, lens flares or 3D money by default;
  ONE support element that fits the video (below).
- **Logos:** a brand's real file, only when the reel is about it (top-left zone); never an AI logo.
- **Master 2160×3840, export 1080×1920.** Face, title and key element inside the critical safe zone
  (1080 units: x 60–1020, y 280–1650) and the grid's 3:4 crop (y 240–1680).

## New with every cover (the owner, 2026-11-16)
- **A suit designed for this cover:** a different cut and colour each time (charcoal, navy, camel,
  olive, burgundy, cream, bottle green, chalk-stripe, double-breasted, a tuxedo for a big news
  day…), with a perfect matching set (shirt, tie or open collar, pocket square, shoes when seen).
- **The day's accessories of 2026:** e.g. Ray-Ban-style sunglasses of the year's shapes, a premium
  watch, a ring, a lapel pin — tasteful, at most two at once, **no visible brand logos**.
- **A pose that tells the title:** pointing at the camera, index finger up, arms crossed, holding the
  element, thinking, surprised, seated on a designer chair, three-quarter, adjusting a cuff…
- **The title fits the video; the element fits the video:** one object or symbol of the reel's
  idea (a hardware wallet, a padlock, a newspaper, a key, a calendar page, a magnifier, a phone…),
  photoreal or 3D, cut out; or drawn by you in the two colours.

## How to make it (the reel's cover step)
1. **Brief line** in direction/CONTRACT.md: Palette / Pose / Suit / Accessories / English words /
   Persian title + key word / Element / Logo.
2. **The picture of him — ONE `substitute.call`:** seat **creative**, kind **image**, placement
   **other**, player **gpt**, `file_ids` = all six references below, `input_md` = the brief below.
3. **Look at it** (Read): the face is HIS (compare with ref 01 and ref 00), anatomy, hands, the suit
   and accessories as briefed, no text or logo anywhere. Wrong: ask again (≤ 2 more), saying what
   was wrong.
4. **Cut out:** `COMMON/tools/cutout.py assets/cover_me.png assets/cover_me_cut.png --trim`. The
   element: its own picture (gpt or gemini, plain background) → cutout.py; or your SVG/PNG.
5. **Compose:** choose today's layout (above; different from the page's last cover), write
   `direction/cover.json` (the spec in `COMMON/tools/cover_compose.py`'s header: english_box and
   english_layer, title_box, chip, cta, arrow …) → `cover_compose.py direction/cover.json out/` →
   out/cover.jpg (+ cover_4k.png, cover_crops.jpg). Read `out/cover_crops.jpg` beside the owner's
   samples: as clean and strong as they are, his face and the title inside the 3:4 crop, the words
   readable small, the Persian letter by letter. Tune and compose again until it is right. Remove
   cover_4k.png and cover_crops.jpg from out/ at the end.

### The references (IG-Hub files; the originals in /home/studio/kits/dotcoin-common/cover/refs)
| id | what |
|---|---|
| `172c9d70-666c-45fa-8d91-d9a6035e240a` | 00 — the page's portrait: suit and tie, studio light (identity) |
| `a0206bfc-9ce0-4728-8a5a-a8c5070c1a8f` | 01 — the primary face, front (identity reference) |
| `3dcffaee-f67e-4619-8875-5f0f897f06a1` | 03 — sunglasses, three-quarter |
| `4e9a9e0a-a3a2-42a7-b3b8-0de9a14ea6c5` | 04 — full body (proportions) |
| `e22f93a7-0de4-4566-b1e1-a35b92598135` | 09 — blazer, three-quarter |
| `24f42402-34a5-4c80-aa2b-397f8f30a7fc` | 10 — formal suit and tie (torso) |
(files.files is in the hub wipe: after a wipe, register them again — the hub's Claude does it — and
put the new ids here.)

### The brief (fill every «…»)
```
Use the attached photos of ONE real person (the page owner, who asked for this) to make a premium
Instagram reel-cover photo of him. A photo only: the layout, the words and the logo are added later.

IDENTITY: exactly the same man as photos 00 and 01: bald head, the same eye spacing, eyebrows, nose,
full dark beard (its shape and density), jaw. Do not beautify or change his face.
BODY: natural proportions as in photo 04 and 10: head to full body about 1:7.2, shoulders 2.6-3.0
head widths. Never enlarge the head.
FRAMING: …FULL BODY / KNEES UP / WAIST UP…, vertical 2:3, the whole figure in frame, centred, room
above the head.
POSE: …
OUTFIT: a tailored …SUIT (cut, colour, fabric)… with …SHIRT / TIE / POCKET SQUARE / SHOES…; a perfect,
current 2026 menswear set.
ACCESSORIES: …(at most two: e.g. 2026-style premium sunglasses, a watch)… — no visible brand logos.
EXPRESSION: …confident and friendly / curious / surprised…
BACKGROUND: a plain, seamless, evenly lit LIGHT-GREY studio backdrop, nothing else (it is cut out
later).
LIGHT: clean premium studio light, soft key, crisp edges, sharp focus, photorealistic, 4K detail.
NOTHING ELSE: no text, letters, numbers, logos, watermarks, props (unless named above), frames.
```
The element's own brief: «…the object…, alone, centred, on a plain light-grey background, studio
light, photorealistic (or premium 3D render), sharp, no text, no logos».

## Never
- Persian or English typed inside an AI picture; an AI-made logo; a video frame as the cover.
- Neon yellow or gold instead of #F3C242; a third dominant colour.
- More than two English lines; a long, small Persian title; his face outside the 3:4 crop.
