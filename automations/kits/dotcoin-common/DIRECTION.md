# DotCoin.me — the direction bible (owner, 2026-11-16)

The owner: the fourth page must be **different** from the other three — its look, its voice, its
cover. «سبک تصویری چیزی که توی پیج های دیگه رعایت نشده باید اینجا رعایت بشه: از پینترست الهام گرفته
بشه؛ هر ویدیو مختص خودش بره توی پینترست جستجو بشه و دانلود بشه و نمونش رو به سازنده ویدیو داده بشه.»
You are that maker: Opus 5.5, extra-high effort (the owner, 2026-11-17). Cost has no limit; the bar is a top studio's.

## 0. The owner's rules — check EVERY one before delivering
1. **Educational and informational only** («فقط آموزشی و اطلاع رسانی»): every reel teaches one thing
   clearly or tells one piece of real news clearly. No hype, no "buy this coin", no price
   prediction, no signal, no promise of profit; no warning or disclaimer lines either (the owner's
   taste on every page). Every fact true; a number only from a real source you checked today.
2. **Its own look, from its own Pinterest search, every reel** (§1). Never the look of the page's
   last reel; never the look of Pro-Chart, Zarib×100 or ipoxxo (no navy/cyan neon, no glassy
   crypto-neon, no Eco font).
3. **The brand: three colour layers** (brand/README.md; the owner, 2026-11-17):
   - **brand:** mustard #F3C242 + black (+ white) on the mark, titles, key-word chips, subtitles,
     the call to action, the first and the last frame, and the cover;
   - **content:** full colour, as the reel's look asks;
   - **meaning:** green = up, red = down, a coin in its own colours.

   Also IRANYekanX Pro, and the page's round photo as its mark.
4. **The narrator: Arlo** — `speech.make` with voice "Arlo", NO style, NO narrator.set (the same
   settings Cruz has on the other pages; the owner: «همون تنظیمات ولی … Arlo به جای Cruz»). A clear,
   friendly teacher's Persian with «تو»; calm pace, never shouting.
5. **Names said right.** In `script/voice.txt` every name in plain Persian letters as spoken
   («بیت‌کوین», «اتریوم», «تتر», «بایننس», «متامسک», «دات‌کوین», «لِجر»…); never Latin letters in the voice
   text. Probe each name after the voice (`tools/word_probe.py`), remake a sentence said wrong.
6. **A cover from the owner's cover system, every reel** (cover/COVER_SYSTEM.md): the owner himself,
   a new suit and accessories each time; never a video frame.
7. **No full stop at the end of on-screen text** («.», «،», «؛»). Persian digits on screen.
8. **Crisp:** no grain, haze, bokeh or blur on the picture; motion blur only on a fast move. Give
   smooth gradients an invisible dither (±1 level), so they do not band after the 8-bit re-encode.
9. **No politics, no religion, no person's face but the owner's** (and his only from his own photos
   or the cover). Real people only as anonymous hands or silhouettes.
10. **Clean audio to the last frame:** the voice ends, the music fades ≥ 1 s, no hit or new sound in
   the last 2 s (`ffmpeg -sseof -2.5 -i out/video.mp4 -af astats=metadata=1:reset=1 -f null -`).

## 1. Pinterest first — the reel's own look (the core of this page)
Before any design, for THIS reel only:
1. **Search:** `COMMON/tools/pin_find.py direction/inspo "<query>" "<query>" …` → about 25 pins a
   query in `found.json` and numbered contact sheets (`found_sheet_*.jpg`, «#n», VIDEO marked).
   (Pinterest walls its search for signed-out visitors; this tool reads the results its own page
   loads. The Pro-Chart kit's pin_search.py finds nothing now — do not use it.) 6–10 queries, two
   kinds:
   - the topic as a visual («crypto wallet security illustration», «bitcoin halving infographic»,
     «blockchain explained motion», «stablecoin concept art» …);
   - a style family that fits it, in any palette: the content layer is free, and mustard/yellow +
     black families are welcome but not required («yellow black editorial
     motion design», «swiss typography motion poster», «kinetic typography reel yellow»,
     «paper cut collage animation», «isometric 3d explainer», «bold minimal infographic animation»,
     «brutalist grid motion», «halftone retro poster», «3d clay render explainer», «risograph
     illustration», «split-screen editorial layout» …). Use different families on different days.
2. **Look** at the sheets (Read). Choose the 4–8 BEST pins — top-level craft that suits the idea,
   video pins welcome — and **download them**: `COMMON/tools/pin_get.py direction/inspo --ids
   <n> <n> …` (the original pictures, the videos with 4 frames each, `sheet.jpg`, `pins.json`).
   Read `direction/inspo/sheet.jpg` closely: these are the maker's references.
3. **Write in `direction/CONTRACT.md`:** the queries, each chosen pin (its link and file), and what
   you take from it (a layout, a type treatment, a transition, a texture, a camera move, a way to
   draw a diagram). Then **the look of this reel in one paragraph**, derived from those references
   and set into the brand: the three colour layers of brand/README.md (the content's own palette,
   with the mustard/black brand layer on top) and IRANYekanX Pro. Take ideas; never copy a
   frame, a character or someone's artwork.
4. If Pinterest gives nothing usable (blocked, empty), say so in one line in CONTRACT.md and use top
   design references you know (Swiss posters, editorial magazines, top explainer channels) — never
   stop the day for it.

## 2. Pictures and graphics
- The reel is built by you in code (HTML/Canvas/SVG/WebGL in headless Chromium + ffmpeg). Diagrams,
  charts, UI mock-ups and type are designed by you, in the brand.
- AI STILL images where the look calls for them (a scene, an object, a texture): `substitute.call`
  seat creative, kind image, placement other — player **gpt** (ChatGPT) and player **gemini** (the
  owner: ChatGPT and Gemini together): photoreal, 3D render or illustration, as the reel's look
  asks; ALWAYS "no text, no letters, no numbers, no logos, no watermark". Look at each (Read);
  wrong = again (≤ 2 more). Cut subjects out with `COMMON/tools/cutout.py`.
- A coin's or a company's logo only as its real file (a press kit or the official site), never
  redrawn by an AI.

## 3. Motion, type and sound
- **Camera and motion:** follow the reel's look; every motion eased, never linear; a new visual idea
  every 1.5–2.5 s; the hook in the first 1.5 s (a question or a surprising true fact, said and shown
  at once).
- **Type:** IRANYekanX Pro, kinetic, word by word or line by line as the look asks; the key word of
  each sentence in mustard (on black) or on a black chip (on mustard). Safe area: the top 220 px
  and the bottom 380 px free of key text. Latin only for names that are Latin on screen
  (Bitcoin, BTC, a ticker) and the giant English words.
- **The mark:** the page's round photo small in a corner during the reel (≤ 90 px, 70 % opacity) or
  only at the end, as the look allows; the end card always shows it with **dotcoin.me** and the call
  to action (follow, save; the comment ask when the reel has one).
- **Sound:** a music bed matched to the look (`motion/audio4.py`, your own cue list), ducked under
  the voice, about −14 LUFS; soft, designed transitions; no booms or hits under the voice.

## 4. Quality control — the strictest art director
1. The contract (§1.3) before any render: the look, the shot list on the word times, every asset.
2. Stills at 12+ times on one sheet; score EVERY shot /10 (idea, craft vs. the references, type,
   clarity, brand). Under 8 is redone; at least 2 rounds.
3. Render once (1080×1920, 60 fps); look at the final file at 8 random times.
4. In your last line to the hub: the topic, the look and its references (pin links), the scores.
