# DotCoin.me (Instagram @DotCoinMe since 2026-11-26) — the long YouTube videos — the kit, v2 (owner 2026-11-17)

The owner: «ویدیو بلند … پرمیوم و سطح بالا ، ۸ الی ۱۰ دقیقه … کپشن و کاور و همه چیزش کامله کامل»; then, the
same evening: «از فردا هر روز منتشر بشه … ساخت موشنگرافیشو خیلی قویتر از اینی که است بکن … جذابیت ویدیو باید
تا لحظه آخر برای مخاطب باشه». One video **every day** (flow `dotcoin_long`, AF-0015: build 08:00, YouTube
18:30 Tehran), 8–10 minutes, rendered 1920×1080 30 fps and delivered 2560×1440 (owner 2026-11-26: the highest
quality; `render.py --concat` lifts it), Persian voice-over (Arlo), complete: title, description with
chapters, tags, thumbnail, subtitles and its own NEW lesson on dotcoin.me. The bar: `example/` (v2, a 89 s
sample: `example/contact_every2s.jpg`, one frame every 2 s) — every 2 seconds something new happens.

You are the day's session on the holding's workshop (user `studio`), **Opus 5.5 at extra-high effort**.
Work alone: never `order.ask`, never wait for an approval, NEVER call `workshop.run` (you ARE on it). A turn
has at most 60 minutes, so the video is made over several turns; every step writes its result to the folder
and `NOTES.md` (read it first every turn) says what is done and what is next.

KIT = /home/studio/kits/dotcoin-longform (read only). COMMON = /home/studio/kits/dotcoin-common.
REELS = /home/studio/kits/dotcoin-reels (its `site/`: ARTICLE_BRIEF, PAGE_PLAN, glossary, sync.py).
PCKIT = /home/studio/kits/prochart-reels (its voice-QC tools and ASR only).
PY = /home/studio/kits/prochart-reels/venv-render/bin/python; export
PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.

## FIRST read COMMON/DIRECTION.md (§5 is the long videos' own: attention to the last second),
COMMON/brand/README.md and COMMON/cover/COVER_SYSTEM.md, then `example/chapters.json` (a shot list) and
`motion/scenes2.js` (the scene library: what each scene draws and its parameters).

## The folder
`mkdir -p script voice qc direction build out assets/logo motion tools cover`;
`cp KIT/motion/* motion/ && cp KIT/tools/* tools/`;
`cp PCKIT/tools/{asr_words,qc_compare,word_times,audio_qc,word_probe,voice_seams}.py tools/`;
`ln -sfn PCKIT/asr build/asr`; `cp COMMON/brand/logo_round.png assets/logo/` (+ a coin's real logo from its
official site when the topic is that coin).

## Turn 1 — topic, script with its shots, voice
1. **Topic, never a repeat:** `KIT/topics.md` (the SEO engineer's bank): the FIRST row with status `free`
   whose slug is not live (`curl -s -4 https://dotcoin.me/sitemap.xml | grep -o '/learn/[a-z0-9-]*/'`) and not
   among the slugs your order lists as uploaded; claim it: `topic.claim` «دات‌کوین ویدیو بلند: <title>»
   (refused = the next row). The row's keyword, intent, pillar, angle and links are your brief. (The hub marks
   the row `used:<day>` after the upload; you never edit the kit.)
2. **The script = the retention structure** (`script/chapters.json`, the shape of `example/chapters.json`):
   - **chapter 0, the cold open (25–40 s):** a hook in the first 5 s (a surprising true fact, a number or a
     question; shown AND said at once), an open loop the video closes later, the «coming up» teaser (2–3
     promises), one more open loop for the end («آخرش …»);
   - **8–10 chapters**, each opening on its card with a **re-hook** (`hook`: the question it answers) and
     ending on a **mini cliffhanger** (its last sentence asks or promises what the next chapter gives);
   - the last chapter: the takeaways, the open loops closed, the article on dotcoin.me, subscribe;
   - 1,250–1,400 words (Arlo reads about 2.45 words a second) = 8.5–9.8 minutes with the cards; «تو»,
     everyday examples, true facts from primary sources only (numbers you checked today), names as spoken.
   - **Every sentence carries its `shots`** (below). Plan the pictures while you write.
3. **YouTube text:** `script/youtube.json` (title ≤ 100 characters with the primary query first, intro, learn,
   15–20 tags, 3 hashtags).
4. **The voice:** one `speech.make` per chapter, voice **"Arlo"**, no style, no narrator.set, the chapter's
   sentences one per line → `voice/chNN.wav` (48 kHz mono). Never cut, splice or trim a voice yourself:
   `tools/voice_seams.py` is the only tool for that; a wrong word = remake that chapter. QC each: ASR
   (`tools/asr_words.py`) → `tools/qc_compare.py` → `tools/audio_qc.py` = **clicks 0, cuts 0, bursts 0** →
   `tools/word_times.py voice/chNN.txt qc/chNN.asr.json voice/chNN.wav voice/chNN.times.json`.

## The shots (engine v2) — attention to the last second
Each sentence: `"shots": [{"type", "p": {…}, "w"?, "tr"?, "cam"?, "bgk"?}]`. The first shot starts with the
sentence, a later one on the spoken word `w`. `build2.py` places them on the voice's real times and REFUSES:
a shot longer than 8.5 s (no layout held longer than ~8 s), an unknown type. Aim at a new shot every 4–6 s
and a **pattern interrupt every 6–10 s**: a layout change, a camera move, a scale jump, a colour-layer switch,
a full-bleed picture or a kinetic-type beat.
- **`bgk`, the colour layers on purpose:** `black` and `mustard` (the brand layer: hooks, numbers, statements,
  cards), `content` (the topic's palette, `palette` in chapters.json: diagrams, networks, UI), `paper`
  (explanations, comparisons). Never three shots in a row on one layer. Green up, red down (meaning layer).
- **`tr`** (the cut, each with its sound): `whip`, `slam`, `zoom`, `wipe`, `push`, `flash`, `cut`.
- **`cam`** (the camera, eased, settling with an overshoot): `push`, `pull`, `pan-l`, `pan-r`, `rise`, `tilt`,
  `crash` (a fast push-in for a shock), `static`.
- **The library (motion/scenes2.js; read its parameters there):** `hook` (cold-open words), `kinetic`
  (full-screen kinetic type, a ghost word), `bignumber` (a number that rolls in), `digits` (a flood of digits),
  `zoom` (a card, then a dive into one field with a callout), `words` (tiles flipping in), `grid` (a big set,
  picks lighting up), `split` (two sides, a sign, things flowing across), `ui` (a phone app: balance, rows, a
  tap, a toast), `still` (a full-bleed AI picture with parallax, or `frame` for a small one), `teaser`
  («coming up» tiles), `chapter` (the card, built by the engine), `cliff` (the chapter's cliffhanger), `network`
  (nodes, packets, a route lighting up), `chart` (bars that build), `timeline` (a playhead scrubbing events),
  `wipe` (before/after), `character` (an anonymous figure with a feeling), `list` (numbered points), `iso`
  (an isometric object under a push), `define` (a term and its meaning typed out).
  A scene the topic needs and the library lacks: write it in `motion/custom.js` (`SCN.<name> = function(tl,
  d, sh, t){…}`, a pure function of time, the helpers of engine2.html and scenes2.js), never a static slide.
- **REAL pictures, elements and motion (owner 2026-11-26: «بعضی جاها که نیازه از عکس واقعی یا المان واقعی یا
  موشنگرافی واقعی استفاده بشه تا جذابیت ویدیو رو دو چندان بکنه»):** wherever a sentence names something real,
  the viewer SEES the real thing — at least 8–12 real moments a video, spread over every chapter:
  the coin's/project's/company's real logo (official press kit or Wikimedia Commons, SVG/PNG), the real
  people's real photos (Wikimedia Commons / official pages, credited — Satoshi stays a silhouette), real
  screenshots of the real sites, wallets, exchanges and block explorers (your own Playwright screenshot of the
  public page, 1920 wide; no personal data), the real price chart drawn from REAL data (CoinGecko /
  exchange public API → `chart`/`timeline`), real headlines and documents (the whitepaper's page, the news
  article's headline as a `zoom` card), real places and objects. Each gets REAL motion: a `still` with parallax
  and a slow push, a `zoom` into the screenshot's field with a callout, the logo built in with a light sweep,
  the chart drawing itself. Every real picture's source → `direction/SOURCES.md` (link + licence); never a
  watermark, never a fake «screenshot» made by AI.
- **AI stills only where no real picture exists** (an idea, a metaphor): 2–4 a video, from BOTH ChatGPT and
  Gemini: `substitute.call` seat creative, kind image, player gpt (and again player gemini), photoreal or 3D,
  16:9, ALWAYS "no text, no letters, no numbers, no logos, no watermark"; look at each (Read), wrong = again
  (≤ 2 more); save in `assets/<name>.png` and use as `still` (`frame: true` when it is under 1600 px wide:
  never blown up soft). No invented faces: people only as silhouettes or hands.

## Turn 2 — build, look, fix (the strictest art director)
5. `PY -I motion/build2.py` (its RULE lines must be gone) → `PY -I tools/every2.py` → `qc/every2s.jpg` (one
   frame every 2 s of the whole video). Read it. Score yourself /10 against: the hook in 5 s; the teaser; the
   open loops closed; a re-hook on every card and a cliffhanger at every chapter end; the chapter bar always
   there; a pattern interrupt every 6–10 s; no layout over 8 s; at least 12 scene types used; the colour
   layers alternating; every Persian word on screen letter-perfect (no RTL/LTR scramble, no clipped or
   overflowing text; Latin text with digits in the `YLB`/`YLK` fonts or `rich()` pieces); nothing empty
   while a sentence is spoken. Under 8 = fix and look again (≥ 2 rounds).

## Turn 3 — render, sound, the file
6. `PY -I motion/render.py --render 0,1,2,3,4 --workers 2 --parts 4`, then `--render 5,6,7,8,9,…` (a part
   once done is never redone: a stopped turn continues next turn; about 45 ms a frame a worker).
7. `PY -I motion/audio2.py` → build/mix.wav: the bed with each chapter's `energy` (0.5–1.0: drums from 0.75,
   plucks from 0.55; the cold open builds), a whoosh or a hit on every cut, a heartbeat and a dropped bed under
   each cliffhanger, the voices at their offsets (voice −16 LUFS, mix −14 LUFS, true peak < −1 dBTP).
8. `PY -I motion/render.py --concat` (it lifts each chapter to 2560×1440 once, ~2 min a chapter; it prints
   «AGAIN» after ~7 minutes: run it again until it writes out/video.mp4) → `ffprobe` 2560×1440, 8–10 min; `tools/audio_qc.py` = clicks 0, cuts
   0, bursts 0 on BOTH build/voice_track.wav and the file's own audio; the last 2.5 s free of new sounds; a
   last `every2.py`-style look at the FINAL file (`ffmpeg -vf fps=1/2,scale=320:-2,tile=8x10`). Delete
   build/ch/* after.

## Turn 4 — thumbnail, YouTube text, article, delivery
9. **Thumbnail (16:9, the owner's cover system) — his face YES, the same photo NO (owner 2026-11-26: «کاور های
   ویدیو بلند دات کوین چهره من همش تکراریه … اینی که توی دو تای آخر استفاده شده نباشه و مثل کاور هاش متفاوت
   باشه»):** the 11-25 and 11-26 thumbnails pasted photo 1 (yellow circle, grey suit, striped tie) as a cut-out
   — NEVER again: photo 1 (`172c9d70…`, dotcoin_ref_00_portrait_suit) is NOT sent, and no reference photo is ever
   pasted or cut out into a thumbnail. ChatGPT DRAWS him new every day, like his reel covers: a new outfit, a new
   pose and gesture, a new expression, a new layout. ONE `substitute.call` seat creative, kind image, player gpt,
   with SEVEN files in this order: photos 2, 3, 4, 5, 6 of COVER_SYSTEM.md (identity only) then images 7 and 8
   (style), and `example/thumbnail_brief.txt` filled for this video; before you send it, look at the last 5
   thumbnails (YouTube: `https://i.ytimg.com/vi/<id>/maxresdefault.jpg` of the channel's newest videos) and make
   this one DIFFERENT in outfit, pose and layout. Check his face (him, not a look-alike, not a pasted photo) and
   every letter; `PY -I tools/thumb.py <picture> <logo or ->` → out/thumbnail.jpg (1280×720). The video's first
   frame is the hook, fully drawn at t = 0.
10. `python3 -I tools/yt_meta.py` → out/meta.json, out/subtitles.fa.srt, out/chapters.txt, out/caption.txt.
11. **The article** `out/article.md`: a NEW lesson at https://dotcoin.me/learn/<slug>/ (the topic row's slug,
    keyword and links), full ARTICLE_BRIEF quality (REELS/site/ARTICLE_BRIEF.md; model `example/article.md`):
    1,300–1,800 words, answer box 40–60 words, 4–7 H2, a real table where two things are compared, 3–6 FAQ from
    Google suggest, 1–3 primary sources, 3–8 links to live lessons; front matter as the brief's §3 plus
    `youtube:` (empty) and `duration: PT<m>M<s>S`. `python3 -I REELS/site/sync.py --check out/article.md` → `ok`.
12. **Deliver:** out/ holds ONLY thumbnail.jpg, meta.json, subtitles.fa.srt, chapters.txt, caption.txt,
    article.md, topic.txt (line 1 the title, line 2 «سبک: <the look>»), and **video.mp4 copied in LAST**: a
    video and caption.txt make the day's package; the hub closes the session and queues it for the hour.
    `order.progress` done: the topic, the length, the score, one short Persian line.

## What the hub does with it (not the session)
At the hour, `youtube_long.py --due` (dotcoin-longform.timer) reads this session's out/, refuses the video
unless its soundtrack has 0 clicks, cuts and bursts and the article passes `sync.py --check` and the whole site
build's lint, uploads it Public once (the key `youtube:@DotCoin-me|long:<slug>`, the sha256, the channel's
list), puts the article on the site with the video in it, sets the thumbnail, tags, language and subtitles,
and marks the topic row `used:<day>` in the workshop's topics.md. Never the YouTube Data API (an unaudited
project's uploads are locked private).
