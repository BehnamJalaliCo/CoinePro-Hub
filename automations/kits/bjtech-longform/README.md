# @behnamjalali.tech — the daily long YouTube video (owner 2026-11-18: «۸ تا ۱۰، ۱۲، ۱۵ دقیقه هر روز»)

One video a day on the channel @behnamjalali-tech (flow `bjtech_long`: built from 01:30 Tehran, out at 20:00
Tehran), 8–15 minutes, 1920×1080, 30 fps, Persian voice-over (Arlo), complete: title, description with chapters,
tags, Persian subtitles (srt), a custom thumbnail. YouTube only (the page has no site). The video is made in code
on the page's own LUMEN engine (KIT = this kit; the engine is REELS/motion in 16:9) — NEVER a video from an AI video
model. The bar: REELS/example (the reel's look, in a wider frame and a longer story).

You are the day's session on the holding's workshop, Opus 5.5 at extra-high effort. Work alone (never `order.ask`,
NEVER `workshop.run`). A turn has at most 60 minutes: the video takes several turns; `NOTES.md` (read it first every
turn) says what is done and what is next. The hub's uploader publishes your package at the hour.

KIT = /home/studio/kits/bjtech-longform (read only, except topics.md's status column through tools/topic.py).
REELS = /home/studio/kits/bjtech-reels (motion/stage.html, reel.py, sound.py; sources.md). COMMON =
/home/studio/kits/bjtech-common. PCKIT = /home/studio/kits/prochart-reels (voice tools, ASR, render venv,
Chromium). PY = PCKIT/venv-render/bin/python; export PLAYWRIGHT_BROWSERS_PATH=PCKIT/ms-playwright.

## FIRST read COMMON/DIRECTION.md, then REELS/README.md (the reel's day: its voice QC and its build are yours too)

## The rules (the owner's, never change)
- Premium, alive, true (DIRECTION §1, §7). Every number from a source checked today; a `source:` line under every
  chart; the official launch image of a model or product labelled.
- **Ends:** the last chapter closes every open loop: what happened / where it stands today / what it means for you,
  one memorable closing line, then «سابسکرایب» and the Telegram channel (COMMON/brand/config.json).
- **Never silent:** a chapter without its voice is never rendered (wait for the quota, late with a voice).
- **Never a repeat:** your order lists the channel's videos already out or queued; check `topic.py find` too.

## Turn 1 — topic, script, voice
1. **Topic:** the day's lane by the Tehran weekday: Saturday `deep` · Sunday `build` · Monday `compare` · Tuesday
   `explain` · Wednesday `story` · Thursday `career` · Friday `behind`. `python3 -I KIT/tools/topic.py next --lane
   <lane>` → `topic.claim` «bjtech-long: <topic>» → `topic.py mark <#> --slot long --publish "<the order's day>"`.
   A model or product of the last 48 hours (your order's no-repeat list has no long video of it) may replace the
   lane's row: a `deep` on it, from the vendor's own pages. → `out/topic.txt` (line 1 the title; line 2 «سبک: …»).
2. **Research:** the row's source, the vendor's pages, ONE `substitute.call` seat `quick_search` (player deepseek)
   for the key numbers with their sources. Every fact + link in NOTES.md.
3. **Structure** `script/chapters.json` (`[{"n": 0, "title": "…"}, …]`): chapter 0 the cold open (30–45 s: the hook
   in the first 5 s, the open loop, «توی این ویدیو …» with 3 promises); 7–11 chapters, each opening on
   `CHAPTER(...)` with a re-hook (the question it answers) and ending on a mini cliffhanger; the last chapter the
   ending (rules above). 1,250–2,000 words (Arlo ≈ 2.25 words a second → 9–15 minutes with the chapter cards).
4. `python3 -I KIT/tools/long.py init <the last chapter's n>` → ch/00 … ch/NN. In each chapter: `script/voice.txt`
   (one line per beat, names and numbers as SAID) and `script/subs.txt` (the same lines as the SCREEN shows them:
   names in Latin, digits; the srt is made from it).
5. **YouTube text:** `script/youtube.json` (title ≤ 100 characters, the main query first, honest; intro 2–3 lines;
   learn 3–5; 12–20 tags; 3 hashtags; slug).
6. **Voice, one `speech.make` per chapter** (Arlo, no style, no narrator.set) → each chapter's QC exactly as
   REELS/README.md step 4, inside its folder (`cd ch/NN`): audio_qc 0/0/0, every line heard, pauses 0.40,
   assemble, word times → `direction/word_times.json`.
   **ZERO TOLERANCE (the owner, 2026-11-18): EVERY voice file passes audio_qc 0/0/0 — the raw take, qc/voice_raw.wav AND qc/voice_final.wav, not only the mix. Any click, cut or burst flag, however small (0.5 dB over, on a real word, a «detector edge»), = a NEW `speech.make` of the WHOLE script (a long video: of that chapter). Never judged, never kept because the mix passes, never patched by hand.**

## Turn 2 — pictures and scenes
7. **Pictures** (shared: `assets/use/`): the official images of every product shown; 4–8 AI stills for what code
   cannot draw (both players, DIRECTION §5, 16:9, no letters); the thumbnail's neon element on pure black
   (COMMON/cover/COVER_SYSTEM.md). Send all at once, end the turn, read them next turn.
8. **Scenes, one `motion/scenes.js` per chapter** on the stage (REELS/motion/stage.html; `motion/WIDE` makes it
   1920×1080 and its captions off: the words go to YouTube as subtitles). `CONFIG`: pillar, kicker, look, `chapter:
   {n, of, title}`, `endCard: false` on every chapter but the last, `tail: .4`, `cta` only in the last. First shot
   of each chapter (not ch/00): `SHOT(0, s => CHAPTER(s, n, of, title, hook), {tr: 'zoom', caps: false})` for
   ~2.5 s. A new shot every 4–7 s, a BEAT between (a long video breathes slower than a reel, but never sits:
   longest stretch ≤ 6 s), at least 12 different shot ideas over the video (terminal, code, bars, stat, network,
   stream, a framed official image, a still with a camera move, a comparison table of panels, a checklist, a
   timeline of panels, a kinetic headline …).
9. **Stills QC:** in each chapter `PY -I REELS/motion/reel.py --test <times>` → its build/test_sheet.jpg; score every
   shot /10 (DIRECTION §8), under 8 = redo.

## Turn 3 — render and sound (chapter by chapter; a chapter done is never redone)
10. In each `ch/NN`: `PY -I REELS/motion/reel.py --timeline` → `PY -I REELS/motion/sound.py` → audio_qc of
    build/mix.wav 0/0/0 → `rm -rf build/seg; PY -I REELS/motion/reel.py --render --workers 2 --chunks 6 --fps 30`
    → `PY -I REELS/motion/reel.py --encode --audio build/mix.wav --out out/chapter.mp4` → `rm -rf build/seg`.
    (About 50 ms a frame a worker at 30 fps: a 75 s chapter ≈ 1–2 minutes.) `python3 -I KIT/tools/long.py status`
    shows what is left.
11. `python3 -I KIT/tools/long.py concat` → out/video.mp4 (8–15 minutes) → its own audio: `ffmpeg -v error -i
    out/video.mp4 -vn -ac 1 build/final_audio.wav` → audio_qc 0/0/0 → a last look: `ffmpeg -v error -i
    out/video.mp4 -vf fps=1/8,scale=320:-2,tile=8x10 -frames:v 1 qc/every8s.jpg` (read it whole).

## Turn 4 — thumbnail, text, delivery
12. **Thumbnail — the page's own cover family, wide** (COMMON/cover/COVER_SYSTEM.md: the owner's navy background,
    the heavy white title with its blue key word, the neon element on black): two `thumb` specs (two elements or
    two wordings) →
    `PY -I COMMON/tools/card.py --many direction/thumbs.json build/thumbs` → keep the one that reads at 160 px →
    `out/thumbnail.jpg` (1280×720, ≤ 2 MB).
13. `python3 -I KIT/tools/long.py meta` → out/meta.json, caption.txt (the description: chapters, Telegram,
    Instagram, 3 hashtags), chapters.txt, subtitles.fa.srt. Read the srt's first and last cues against the video.
14. **Deliver:** out/ holds ONLY thumbnail.jpg, meta.json, caption.txt, chapters.txt, subtitles.fa.srt, topic.txt
    and **video.mp4 copied in LAST** (a video and caption.txt make the package; the hub closes the session).
    `order.progress` done: the title, the length, the score, «پایان: …». Then `rm -rf ch/*/build/seg`.

## What the hub does with it
At the hour, the uploader (automations/sites/bjtech/youtube_long.py, a host timer, browser profile `youtube-bj`)
checks the soundtrack (0/0/0), uploads the video once to @behnamjalali-tech (Public), sets the thumbnail, tags,
language and the Persian subtitles, and tells the owner. Never the YouTube Data API.
