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
  set on the ground as in the samples (a solid bar only now and then, for variety). ChatGPT writes
  it (the owner's way, 2026-11-16); you check every letter, and set it yourself only as the last
  resort (step 4 below).
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

## How to make it (the reel's cover step) — ChatGPT makes the WHOLE cover (owner, 2026-11-16)
The owner, after the first sample: «کاور جالب نشده؛ باید فولدر رو به چت جی پی تی بدی و دقیقا مدل و
استایل رو توضیح بدی، خودش میسازه؛ به شخصیت من توی فولدر اشاره کن و بگو چه شکلی و چه استایلی داشته
باشه.» So the cover is made the way he made his two samples: ChatGPT gets his folder (his photos and
his two covers as images, the pack's rules as text) and a precise brief, and draws the finished
cover itself — him, the words, the Persian title, the chip, the pill, the arrow.

1. **Brief line** in direction/CONTRACT.md: Palette / Layout / Pose / Suit / Accessories / English
   words / Persian title (+ the chip word) / Call to action / Element.
2. **ONE `substitute.call`:** seat **creative**, kind **image**, placement **other**, player **gpt**,
   `file_ids` = ALL EIGHT files below (his six photos, then his two covers), `input_md` = the brief
   below, every «…» filled.
3. **Look at it** (Read) as the strictest art director, beside his two samples:
   - the Persian text letter by letter EXACTLY as asked (no missing, extra or swapped letter, the
     right dots, right-to-left), the chip around the right word, the English words spelled right;
   - his face (bald head, beard, eyes, nose, jaw: the man of photos 00 and 01), natural proportions,
     hands; the suit and accessories as briefed;
   - the two colours only, the layout as briefed, nothing else written, as clean as his samples.
   Wrong: ask again (≤ 2 more), saying exactly what was wrong («the word «…» was written «…»»).
4. **Still wrong letters after 3 tries:** ONE more call asking for the same cover WITHOUT any Persian
   text (its place left empty), then set the Persian yourself on it with
   `COMMON/tools/cover_compose.py` and `"background": "<that picture>"` (IRANYekanX Pro).
5. **Size:** fit to 1080×1920 (Lanczos; crop to 9:16 only on the ground, never on him or the text) →
   `out/cover.jpg` (quality 92). His face and the title must sit inside the grid's 3:4 crop
   (y 240–1680).

### The eight files (IG-Hub; the originals on the workshop)
| id | what |
|---|---|
| `172c9d70-666c-45fa-8d91-d9a6035e240a` | photo 1 — the page's portrait, suit and tie (identity) |
| `a0206bfc-9ce0-4728-8a5a-a8c5070c1a8f` | photo 2 — his face, front (the identity reference) |
| `3dcffaee-f67e-4619-8875-5f0f897f06a1` | photo 3 — sunglasses, three-quarter |
| `4e9a9e0a-a3a2-42a7-b3b8-0de9a14ea6c5` | photo 4 — full body (proportions) |
| `e22f93a7-0de4-4566-b1e1-a35b92598135` | photo 5 — blazer, three-quarter |
| `24f42402-34a5-4c80-aa2b-397f8f30a7fc` | photo 6 — formal suit and tie (torso) |
| `3617566d-05be-46cf-bd20-692d76df804d` | image 7 — HIS cover «CRYPTO CHANNEL» (the target style) |
| `23b125b7-3259-4a55-92aa-5cb43d6e56cf` | image 8 — HIS cover «FOREX CHANNEL» (the target style) |
(files.files is in the hub wipe: after a wipe, the hub's Claude registers them again and puts the
new ids here. The originals: cover/refs/ and cover/samples/.)

### The brief (fill every «…»; keep the Persian EXACT)
```
I attach my cover folder. Photos 1-6 are ME, the page owner (Behnam), who asks for this cover of
himself. Images 7 and 8 are two covers I already made: follow THEIR style exactly, with a new design.

Make ONE new vertical 9:16 Instagram reel cover (1080x1920) for my page DotCoin (dotcoin.me).

THE STYLE (as in images 7 and 8): a flat …BLACK #000000 / MUSTARD #F3C242… background; GIANT
ultra-bold condensed UPPERCASE English words in …mustard #F3C242 / black…, edge to edge; me as a
clean, sharp, premium studio photo cut-out; the Persian title in a heavy geometric Persian sans-serif
(like IRANYekanX Black, as in images 7 and 8), set straight on the background; ONE key word inside a
rounded mustard box with black letters; a pill with a mustard outline for the call to action and a
hand-drawn mustard arrow. Only black, mustard #F3C242 and white. Minimal, high contrast, premium,
readable as a small square in the grid.

THIS COVER'S LAYOUT: …e.g. "the English words at the top behind me; me full body on the right; the
Persian title and the pill in the free column on my left" — or another layout, different from the
last cover: the words in front of me / at the bottom / as an outline over me; me left / centre /
right; full body / knees up / waist up…

ME: exactly the man of photos 1 and 2 — bald head, the same eyes, eyebrows, nose, full dark beard and
jaw; do not change or beautify my face. Natural body proportions as in photos 4 and 6 (head to body
about 1:7.2; never a big head). Pose: …. Expression: ….
OUTFIT, designed for this cover: …a tailored suit (cut, colour, fabric), shirt, tie or open collar,
pocket square, shoes if seen… — a perfect, current 2026 menswear set.
ACCESSORIES of 2026 (at most two): …e.g. premium sunglasses or optical frames of this year's shapes,
a watch… — no visible brand logos.
ELEMENT (one, fits the video): ….

THE TEXT — write these EXACTLY, letter by letter, nothing added, nothing changed:
- English, giant: «…» (line 1) «…» (line 2)
- Persian title, right to left: line 1 «…» in …white/mustard…; line 2 «…» in …white…; the word «…»
  inside the rounded mustard box with black letters.
- The pill: «…», with the word «…» in mustard. The arrow points down toward the caption.
No other words, letters, numbers, logos or watermarks anywhere.
Keep my face and the Persian title inside the central 3:4 area of the frame.
```

## Never
- An AI-made logo; a video frame as the cover; Persian with a wrong letter (check every one).
- Neon yellow or gold instead of #F3C242; a third dominant colour.
- More than two English lines; a long, small Persian title; his face outside the 3:4 crop.
