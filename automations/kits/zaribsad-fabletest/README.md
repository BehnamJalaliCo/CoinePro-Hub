# A model test: the ZEC reel made by Claude Fable 5.2 (owner, 2026-11-15) — NOTHING is published

The owner: «مدل فیبل ۵.۲ رو هم یکبار امتحان کنیم برای ساخت ویدیو ریلز؛ اونم خیلی خفنه، تازه اومده،
میگن قویه ساخت ویدیوش». You ARE that test: Claude Fable 5.2, highest effort. The same reel was made
tonight by Opus 5.5 (F-0025); the owner compares the two and chooses the model for the daily reels.
This order publishes nothing: deliver the package to out/ and stop. Work alone: never `order.ask`.
Do not `topic.claim` (the topic is taken by the Opus reel). NEVER call `workshop.run`.

KIT = /home/studio/kits/zaribsad-fabletest · COMMON = /home/studio/kits/zaribsad-common ·
PCKIT = /home/studio/kits/prochart-reels (tools only) · PREV = /home/studio/kits/zec-redo-1115.

## Read first
1. COMMON/DIRECTION.md — the premium bar and the owner's corrections (§0: brand names said right,
   the audio tail, no full stops on screen, the cover from the pack, **no TradeYar logo**, and the
   newest: **a crisp picture — no particles, rain, bokeh, grain or blur — and no percussive hits
   between sentences or on transitions**).
2. COMMON/cover/COVER_PACK.md (the cover) and COMMON/brand/README.md (the page's own mark).
3. /home/studio/kits/zaribsad-noon/REDO_2026-11-15.md — what this reel is and what PREV holds.

## What you have (the same material the Opus build had — a fair test)
- PREV: the checked voice `qc/voice_final.wav` (79.7 s video; do NOT remake it), its words and word
  times (`script/voice.txt`, `direction/word_times.json`), the texts (`out/caption.txt`,
  `out/comment.txt`, `out/topic.txt` — keep the comment word «سایه»), the facts and the 1-year price
  series (`qc/`), the real logos (`assets/final`, `assets/dl`), the previous build's plumbing
  (`motion/engine6.py`, `tools/` — render, tail check, captions without end punctuation).
- PREV/ai: the 15 ChatGPT key-art images the Opus build used, and `WHAT_IS_WHAT.txt` naming each.
  You may ask ChatGPT for more (`substitute.call` seat creative, kind image, placement other, player
  gpt; they land in in/), and the cover from the pack.
- The page's mark: COMMON/brand/profile_round.png + «Zarib×100» + «بهنام جلالی».

## Your job
Be the director. Make this reel as a top motion studio would: the HYBRID track (the anime host
leading through premium motion-graphics cards), every shot designed, camera, depth by parallax,
designed transitions, kinetic Persian type in IRANYekanX Eco, the real data, clean sound (music bed,
the voice on top, NO hits). Your own look and your own edit — do not copy the Opus build's frames.
QC as DIRECTION §0 and §6 (stills at 16+ times, every shot ≥ 8/10, two rounds, the final file at 8
random times, the audio tail and every sentence boundary). Render 1080×1920 60 fps.

## Deliver
`mkdir -p script qc direction build out in assets motion tools` first. At the end out/ holds ONLY
video.mp4, story.mp4 (`ffmpeg -v error -y -i out/video.mp4 -t 59.8 -af afade=t=out:st=59.3:d=0.5 -c:v libx264 -crf 17 -c:a aac out/story.mp4`),
cover.jpg, caption.txt, comment.txt, topic.txt (copies of PREV's texts unless you improved them).
Your last `order.progress`: one Persian line — the track, the look, your shot scores, and what you
did differently. The hub does not publish it; the owner sees it next to the Opus reel.
