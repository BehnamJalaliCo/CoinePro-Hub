# @behnamjalali.tech — the daily long YouTube video (owner 2026-11-18: «۸ تا ۱۰، ۱۲، ۱۵ دقیقه هر روز»)

One video a day on the channel @behnamjalali-tech (flow `bjtech_long`: built from 01:30 Tehran, out at 20:00
Tehran), 8–15 minutes, rendered 1920×1080 30 fps and delivered 2560×1440 (owner 2026-11-26: the highest quality;
`long.py concat` lifts it), Persian voice-over (Arlo), complete: title, description with chapters,
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

## Retention — HARD (the owner, 2026-11-18: «از فن‌هایی باید استفاده بکنی که تا ثانیه آخر مخاطب رو نگه داره»)
A video that fails `python3 -I KIT/tools/long.py retention` is re-cut, NEVER delivered. Times are seconds in the WHOLE
video (the chapters back to back).
1. **Cold open, 0–8 s:** start at the climax (the moment itself, the shock, the stakes) and SAY one burning question by
   8 s. No logo, no «سلام», no channel intro, no «سابسکرایب» before the end.
2. **Open loops:** by 30 s promise a payoff that comes only at the END («و آخرش …»). Keep 1–2 loops open at all times;
   close one only after the next is open.
3. **Chapter cliffhangers:** every chapter but the last ends on a question or a turn the next chapter answers — never a
   summary. A turn that is not a question is written into `script/retention.json` `cliffs`.
4. **Re-hooks at ~25 %, 50 %, 75 % (±45 s):** a «ولی…», a twist or the stakes raised, WITH a visual pattern interrupt.
5. **Pattern interrupts:** something new on screen every 4–6 s (a camera move, kinetic type, a diagram building, a cut,
   a BEAT that really changes the frame); NOTHING static over 6 s; a clear visual or sound change every 20–40 s (a
   new scene type, a music turn, a beat of silence).
6. **Story spine:** a human at the centre (their stakes and feelings), tension rising, an emotional peak, the payoff,
   then «برای تو یعنی چه».
7. **Visible progress:** the slim chapter progress bar over the whole video (`long.py bar` writes each chapter's
   place; the stage draws it) and chapter cards that NAME what is coming («فصل ۴: حرکتی که هیچ انسانی نمی‌زد»).
8. **Ending:** the payoff and the takeaway land within the last 60 s; the outro (Telegram + the next video's tease) is
   ≤ 15 s, so nobody leaves before the end.
9. **QC with numbers** — `script/retention.json`:
   `{"hook_question_at": 6.1, "open_loop_at": 24.0, "open_loop_closes_at": "ch07", "rehooks": {"25": 151, "50": 302,
   "75": 455}, "payoff_at": 560, "outro_s": 12, "cliffs": {"03": "<the turn line>"}}` → `long.py retention` PASS (the
   longest stretch with nothing new ≤ 6 s in every chapter, read from its real timeline; the hook question by 8 s; the
   loop by 30 s; every chapter's end; the re-hooks; the payoff in the last 60 s; the outro ≤ 15 s). NOTES.md lists the
   timestamps.

## Turn 1 — topic, script, voice
1. **Topic:** the day's lane by the Tehran weekday: Saturday `deep` · Sunday `build` · Monday `compare` · Tuesday
   `explain` · Wednesday `story` · Thursday `career` · Friday `deep` (⟨2026-11-21⟩ `behind` retired: COMMON/DIRECTION.md §0). `python3 -I KIT/tools/topic.py next --lane
   <lane>` → `topic.claim` «bjtech-long: <topic>» → `topic.py mark <#> --slot long --publish "<the order's day>"`.
   A model or product of the last 48 hours (your order's no-repeat list has no long video of it) may replace the
   lane's row: a `deep` on it, from the vendor's own pages. → `out/topic.txt` (line 1 the title; line 2 «سبک: …»).
2. **Research:** the row's source, the vendor's pages, ONE `substitute.call` seat `quick_search` (player deepseek)
   for the key numbers with their sources. Every fact + link in NOTES.md.
3. **Structure** `script/chapters.json` (`[{"n": 0, "title": "…"}, …]`), written to the Retention rules above:
   chapter 0 the cold open (25–40 s: the climax, the burning question by 8 s, the end-loop by 30 s, no intro);
   7–11 chapters, each opening on `CHAPTER(...)` with a title that names what is coming and its re-hook question,
   each ending on a question or a turn; the re-hooks planned at 25/50/75 %; the last chapter the payoff in its last
   60 s and an outro ≤ 15 s (Telegram + tomorrow's tease). Write `script/retention.json` with the planned times. 1,250–2,000 words (Arlo ≈ 2.25 words a second → 9–15 minutes with the chapter cards).
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
10.1 Before the first render and again before concat: `python3 -I KIT/tools/long.py bar` (the progress bar's places)
    and `python3 -I KIT/tools/long.py retention` (the real timelines; fix and re-render a chapter that fails).
11. `python3 -I KIT/tools/long.py concat` (each chapter lifted to 2560×1440 once, ~2 min a chapter; «AGAIN» after
    ~7 minutes = run it again) → out/video.mp4 (8–15 minutes, 2560×1440) → its own audio: `ffmpeg -v error -i
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
