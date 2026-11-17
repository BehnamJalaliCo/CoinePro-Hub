# DotCoin.me (@dotcoin.me) — the long YouTube videos — the kit (owner 2026-11-17)

The owner: «ویدیو بلند هفته ای ۳ تا … در سبک ریلز هایی که ساختی پرمیوم و سطح بالا ، ۸ الی ۱۰ دقیقه باید
باشه ، و هر ویدیو باید کپشن و کاور و همه چیزش کامله کامل باشه». Three a week (Sat / Mon / Wed), each
8–10 minutes, 1920×1080, 30 fps, a Persian voice-over (Arlo), the DotCoin reels' look, and complete:
title, description with chapters, tags, thumbnail, sidecar subtitles and its own article on dotcoin.me.
The first one: «اتریوم چیست؟» (2026-11-17, slug `ethereum`).

You are the video's session on the holding's workshop (user `studio`), **Opus 5.5 at extra-high effort**.
Work alone: never `order.ask`, never wait for an approval. NEVER call `workshop.run` (you ARE on it).
A turn has at most 60 minutes, so the video is made over several turns (below); every step writes its
result to the folder, so the next turn continues where this one stopped. Read `NOTES.md` first in every
turn (create it in turn 1) and keep it current: decisions, what is done, what is next.

KIT = /home/studio/kits/dotcoin-longform (read only). COMMON = /home/studio/kits/dotcoin-common.
REELS = /home/studio/kits/dotcoin-reels (its `site/` copies: ARTICLE_BRIEF, PAGE_PLAN, glossary, sync.py).
PCKIT = /home/studio/kits/prochart-reels (its TOOLS only: the voice QC and the ASR).
PY = /home/studio/kits/prochart-reels/venv-render/bin/python (numpy, PIL, playwright);
export PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.

## FIRST read COMMON/DIRECTION.md, COMMON/brand/README.md and COMMON/cover/COVER_SYSTEM.md.
They are the owner's rules for this page; every one holds for the long video too (the three colour layers,
IRANYekanX Pro, Arlo, names said right, no full stop at the end of on-screen text, Persian digits on
screen, no face but the owner's, educational only, no hype, no prices, no disclaimers, clean audio to the
last frame). Then read `KIT/example/` (the first video's script, scenes and contact sheet): that is the bar.

## The folder
`mkdir -p script voice qc direction/inspo build out assets/logo motion tools cover`;
`cp KIT/tools/* tools/ && cp KIT/motion/* motion/` (the engine: scene.html, build.py, render.py,
audio_long.py); `cp PCKIT/tools/{asr_words,qc_compare,word_times,audio_qc,word_probe,voice_seams}.py tools/`;
`ln -sfn PCKIT/asr build/asr`; the logos you need into assets/logo (COMMON/brand/logo_round.png always;
a coin's logo only as its real file from its official site, e.g. ethereum.org/en/assets/).

## Turn 1 — topic, script, voice
1. **Topic, never a repeat** (the owner: no duplicate reel, article or YouTube video, ever):
   - the first entry of `KIT/bank/topics.json` with `"used": null` whose slug is NOT live
     (`curl -s -4 https://dotcoin.me/sitemap.xml | grep -o '/learn/[a-z0-9-]*/'`), not in the hub's
     long-video state (your order lists the slugs already uploaded) and not a cornerstone
     (`cryptocurrency`, `bitcoin`, `crypto-wallet`, `how-to-buy-crypto`, `usdt-networks`);
   - claim it: `topic.claim` «دات‌کوین ویدیو بلند: <title>» (refused = the next entry);
   - a deep, high-value topic that carries 8–10 minutes and a full article of its own; link it to the
     related live lessons (the article does it, step 11).
   → `script/chapters.json` (the shape of `KIT/example/chapters.json`): `slug`, `topic`, `title` and
   8–10 chapters: chapter 0 = the hook and the title (no card), then one chapter per sub-question of the
   topic, the comparison or the common mistakes, and the last = «جمع‌بندی» (the takeaways + the article on
   dotcoin.me + subscribe). Each chapter: `yt` (its YouTube chapter name), `card` (its Persian title),
   `en` (its giant English word), `s` = its sentences, each `{"v": the voice text, "h": the headline on
   screen, "k": the headline's key word}`.
2. **The script:** ONE `substitute.call` (player gpt) for the research and a first draft if it helps;
   you write and own every sentence. 1,150–1,300 words (Arlo reads about 2.4 words a second: 8–9 minutes
   of voice + the chapter cards = 8.5–10 minutes). A hook in the first sentence (a surprising true fact,
   shown at once), one clear idea per chapter, everyday examples, numbers only from a primary source you
   opened today (the protocol's own site, the whitepaper), names as spoken in Persian letters, «تو»,
   friendly. Check every fact: a wrong fact is the worst defect a lesson can have.
   - The YouTube text: `script/youtube.json` = {title (≤ 100 characters, the primary query first, e.g.
     «اتریوم چیست؟ آموزش کامل اتریوم به زبان ساده | …»), intro (2 lines), learn (6–9 bullets), tags
     (15–20, Persian queries first, then the English name), hashtags (3: the topic, #ارز_دیجیتال,
     #دات_کوین)}. The primary query from Google suggest (ARTICLE_BRIEF §2).
3. **The voice, chapter by chapter:** one `speech.make` per chapter with voice **"Arlo"** (no style, no
   narrator.set), the chapter's sentences one per line. The files arrive in `in/` next turn →
   `voice/chNN.wav` (48 kHz mono: `ffmpeg -i in/speech-….ogg -ar 48000 -ac 1 voice/chNN.wav`). The hub reads a
   long text in parts and joins them cleanly (since 2026-11-17: each part's head click and tail burst
   removed, a 0.35 s pause). Never cut, splice or trim a voice file yourself (the owner's rule: no click,
   «tak» or choke anywhere): `tools/voice_seams.py` is the ONLY way to clean, join or shorten pauses, and
   a wrong word = remake that chapter's whole voice. The chapters are never joined into one file: each
   whole chapter file is placed at its chapter's offset by audio_long.py (silence and the card between).
   - QC each chapter: `tools/asr_words.py` → `tools/qc_compare.py` (a wrong word: remake the chapter),
     `tools/word_probe.py` for every name, `tools/audio_qc.py voice/chNN.wav` = clicks 0, cuts 0, bursts 0
     (a take with a finding: ask `speech.make` again for that chapter; one in three takes can carry a
     burst; its duration rule is the reels' and does not apply here).
   - Word times: `build/asr/venv/bin/python -I tools/word_times.py <chapter text, one sentence a line>
     qc/chNN.asr.json voice/chNN.wav voice/chNN.times.json` (one timed line per sentence).

## Turn 2 — the look and the scenes
4. **Pinterest first (DIRECTION §1):** `COMMON/tools/pin_find.py direction/inspo "<the topic as a
   visual>" "<a style family>" …` (6 queries), read the sheets, `pin_get.py --ids …` 4–8 pins, and write
   `direction/CONTRACT.md`: the pins and what each gives, the look in one paragraph (the first video:
   «Swiss grid × isometric line-art in the topic's own colours», a mustard panel column with the chapter
   number and the kinetic headline; a different family is welcome for a new topic, inside the brand
   layers), the scene list per chapter.
5. **Build the scenes:** `motion/chapters.js` = one function `chN(t)` per chapter (the example's file is
   the pattern and its helpers in `scene.html` are yours: panel, headline, iso boxes, nodes, coins,
   tiles, chips, timelines, tables, counters). Every frame a pure function of time; things enter on the
   word that names them (`WT(i,'word')`), a new visual idea every 2–4 s, nothing static for long, and
   no empty stage while a sentence is spoken. Latin text with digits (ERC-20, 0x…, a URL) in the
   `YLB`/`YLK` fonts (the FaNum fonts turn digits Persian); a Persian line with a Latin piece through
   `rich()` pieces, never one mixed string.
6. `PY -I motion/build.py` (real times when `voice/chNN.times.json` exist, else an estimate), then QC
   stills: `PY -I motion/render.py --test N <t1,t2,…>` (one still at 75% of every sentence:
   `python3 -I tools/times.py N`). Score every scene /10 as the strictest art director (idea, craft,
   type, clarity, brand); under 8 is redone; at least 2 rounds. Check every Persian word on screen
   letter by letter: no RTL/LTR scramble, no overflow, no clipped text (the owner's zero tolerance).

## Turn 3 — render, sound, the file
7. **Render in chunks:** `PY -I motion/render.py --render 0,1,2,3,4 --workers 2 --parts 4`, then
   `--render 5,6,7,8,9`. A finished part (`build/ch/chNN_pP.mp4.done`) is never redone, so a turn that
   ends mid-render continues in the next one. At most 2 Chromium workers (the workshop has 4 GB),
   `pkill -f "[c]hrome-linux64/chrome"` after. About 55 ms a frame a worker.
8. **Sound:** `PY -I motion/audio_long.py` → build/mix.wav (the bed, its chapter swells and bells, the
   voices at their chapter offsets; voice −16 LUFS, mix −14 LUFS, true peak < −1 dBTP).
9. **The file:** `PY -I motion/render.py --concat` → out/video.mp4 (H.264 High, CRF 15, 30 fps, AAC 256k, about 100 MB for 10 min,
   faststart). Check: duration 8–10 min (`ffprobe`); `audio_qc.py` = clicks 0, cuts 0, bursts 0 on BOTH the
   narration (build/voice_track.wav → qc/voice_track.audioqc.json) and the final mix (build/mix.wav and the
   file's own audio → qc/mix.audioqc.json); the last 2.5 s silent of new sounds; and look at 12 random frames of the FINAL file. `PY -I motion/render.py --sheet`
   → qc/contact_sheet.jpg (6 frames a chapter): read it whole. Delete build/ch/*.mp4 parts after.

## Turn 4 — thumbnail, YouTube text, article, delivery
10. **Thumbnail (16:9, the owner's cover system):** ONE `substitute.call` seat creative, kind image,
    player gpt, with all EIGHT file ids of COVER_SYSTEM.md and the brief of `KIT/example/thumbnail_brief.txt`
    with this video's English word, Persian title, suit, accessories and pose (a new suit every video,
    the layout different from the last one, the top-left corner empty for the topic's real logo, the
    bottom-right free of face and text). Check his face and every letter (≤ 2 more tries, saying exactly
    what was wrong). Then `PY -I tools/thumb.py <the picture> <logo or ->` → out/thumbnail.jpg
    (1280×720, ≤ 2 MB; YouTube takes it only once the channel's phone verification has enabled custom
    thumbnails, «Intermediate features»; until then youtube_long.py uploads without it). The video's first frame must be strong on its own (the hook frame fully drawn
    at t = 0): YouTube shows it where a custom thumbnail cannot be set.
11. **YouTube text:** `python3 -I tools/yt_meta.py` → out/meta.json (title, description with the chapters
    from the real timeline, tags, category Education, slug, topic, article link), out/subtitles.fa.srt,
    out/chapters.txt. Chapters: 00:00 first, every chapter ≥ 10 s.
12. **The article** `out/article.md`: a NEW lesson at https://dotcoin.me/learn/<slug>/, full ARTICLE_BRIEF
    quality (REELS/site/ARTICLE_BRIEF.md, read it whole; the model is `KIT/example/article.md`):
    1,300–1,800 words, the primary query in title/H1/answer/first 100 words/one H2, the answer box 40–60
    words, 4–7 H2 (a real table for a comparison), 3–6 FAQ from Google suggest (40–80 words each),
    1–3 primary sources, 3–8 contextual links to live lessons and glossary anchors, written Persian.
    Front matter as the brief's §3 plus `youtube:` (left empty: the hub fills it after the upload) and
    `duration: PT<m>M<s>S`. `python3 -I REELS/site/sync.py --check out/article.md` must print `ok`.
13. **Deliver:** out/ holds ONLY video.mp4, thumbnail.jpg, meta.json, subtitles.fa.srt, chapters.txt,
    article.md and topic.txt (line 1 the title; line 2 «سبک: <the look>»). `order.progress` done: the
    topic, the length, the look and its pins, the scene scores, one short Persian line.

## What the hub does with it (not the session)
- **YouTube:** `automations/sites/dotcoin/youtube_long.py --video out/video.mp4 --thumb out/thumbnail.jpg
  --meta out/meta.json --unlisted` on the hub (the browser profile `youtube-web`, egress task
  `upload_long`; the YouTube Data API is NOT used: an unaudited project's uploads are locked private).
  One upload per video, ever: the key `youtube:@DotCoin-me|long:<slug>` and the file's sha256 in
  /home/Hub/sites/dotcoin-youtube.json; a title already on the channel is never uploaded again. The
  first videos go Unlisted; the owner makes them Public (`--make-public <slug>` on his word).
- **The article:** into the site's content (content/articles/<slug>.md on branch server/dotcoin-site →
  site/dotcoin-content), its `youtube:` set to the video's link; the site sync deploys it. The page
  shows the YouTube player at the top (no Instagram reel box) and a VideoObject in its JSON-LD.
