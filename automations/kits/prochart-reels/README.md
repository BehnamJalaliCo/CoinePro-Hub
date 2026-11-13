# Pro-Chart daily reel — the kit (from session F-0018, 2026-11-13)

You are the day's session, started by the daily automation (n8n) on the owner's standing order.
Work alone: never `order.ask`, never wait for an approval, never send a preview. You ARE on the
workshop: do every step yourself, in your own turns, in this folder. NEVER call `workshop.run` (a
separate run loses this session; when a turn of yours stops, the hub wakes this same session). The hub publishes
your package by itself at the hour your order names, turns the smart comment and the story reply on,
tells the owner, and closes the session. KIT = /home/studio/kits/prochart-reels (read only: never edit
it; copy what you change into your own folder).

## Spend little (the owner's rule)
- Read THIS file; open anything else in the kit only when a step needs it. NEVER read
  examples/day1/STATE-F-0018.md whole (grep it when a step fails).
- Keep every command's output short (`| tail -5`, `-q`, `-v error`). No frame dumps, no long logs.
- One turn does as many steps as fit. At the start record the plan with `order.ack` (the steps below):
  the hub keeps waking you while steps are open. Mark each done with `order.progress`.
- Render with at most 2 workers (the workshop has 4 GB); close Chromium after each use:
  `pkill -f "[c]hrome-linux64/chrome"` (with the brackets).

## Fixed rules (owner, F-0018 — never change)
- Colours: ONLY pure black #000000 and mustard #D4A64A, everywhere (video, cover, character, end card).
  Up candles solid mustard, down candles hollow with a mustard outline. No other colour, no white.
- Font IRANYekanX (KIT/fonts, KIT/fontpack_raw). Logo: KIT/coverkit2/logo.
- Video: 1080×1920, 60 fps, 60–90 s (owner: 1:00–1:30), animation AND motion graphics together in every
  scene: every word and sentence becomes motion; text rises word by word; scene changes with a diagonal
  mustard band; no frame still longer than 3 s; no price figures. The character «پرو» (toon.js) acts
  out every sentence, lips follow the voice.
- Inspiration each day from a similar reel or Pinterest (KIT/tools/pin_*.py), different every day; if
  none fits, the direction and edit are yours (Opus 5.5, highest effort). Direction is on paper
  (edit.json), the video is built ONCE as the final output.
- Voice: `speech.make` with voice "Cruz" only, NO style, NO narrator.set. Casual Persian with «تو».
  Fixed slogan at the end: KIT/qc/slogan.ogg («اول نمودار، بعد تصمیم — پرو چارت»).
- Caption: SEO text, at most 5 hashtags. Comment and DM texts: no hashtags.
- The comment link: https://pro-chart.com/next/?utm_source=instagram&utm_medium=dm&utm_campaign=reelNNN_<slug>
  (always /next/: the root drops the utm).
- Cover: template «الف» (mustard block on top, black title), made by YOU with KIT/tools/cover2.py,
  exactly like KIT/examples/day1/cover.jpg (owner: the Pro-Chart cover is Opus's, same look every day).

## The day, step by step
0. **Setup** (in your folder):
   `mkdir -p script qc direction build out in && cp -r KIT/motion KIT/tools ./ && cp KIT/direction/edit_template.py direction/edit.py`
   `ln -sfn KIT/asr build/asr && ln -sfn KIT/venv-render build/.venv`
1. **Topic:** take the next title of KIT/bank/bank.json (day, series, title, angle, anchor) that is not
   used: `topic.claim` it (the hub refuses a repeat: take the next). Write `out/topic.txt` (the title).
2. **Script** (ChatGPT in the loop when it answers; if it is down, write it yourself and go on):
   `substitute.call` with player gpt, ONE ask for: a 140–160 word casual
   script for 60–75 s on the topic (with the angle and the anchor), the comment keyword said in the
   video (one word, e.g. «بازپخش»), the caption (≤5 hashtags), the DM reply (≤600 chars, warm, emoji,
   steps), 10 public replies under a comment (short, warm, each with an emoji, all different).
   Its answer comes later (queued): do the setup and the inspiration meanwhile; don't poll.
   Fix the script yourself (facts about Pro-Chart from KIT/examples and the anchor; no promise of
   profit; the risk line). Keep it in `script/voice.txt`; the video must SAY the keyword.
3. **Voice:** `speech.make` (voice Cruz, the script). The file lands in `in/`. Then:
   `build/asr/venv/bin/python -I tools/asr_words.py build/asr/models <voice> qc/asr.txt qc/asr.json`
   `python3 -I tools/qc_compare.py script/voice.txt qc/asr.txt qc/qc.json` — a wrong word: remake ONLY
   that sentence. Then `tools/assemble_voice.py <voice> qc/asr.json KIT/qc/slogan.ogg qc/voice_final.wav`
   (it also removes the click at the start and the hiss at the end) and `python3 -I tools/audio_qc.py qc/voice_final.wav`.
4. **Word times:** `build/asr/venv/bin/python -I tools/word_times.py script/voice.txt qc/asr.json qc/voice_final.wav direction/word_times.json`
5. **Direction and edit (on paper):** rewrite the BEATS of `direction/edit.py` for today's script (the
   day-1 file is the model: KIT/examples/day1/day1_edit.json), then
   `python3 -I direction/edit.py direction/word_times.json direction/edit.json`. Write today's character
   shots in `motion/toon.js` (the day-1 shots are the model) and the sound cues `motion/T.json`
   (model: KIT/examples/day1/T.json).
6. **Sound:** `build/asr/venv/bin/python -I motion/audio4.py motion/T.json qc/voice_final.wav build/mix.wav`
7. **Check stills (yours only):** `build/.venv/bin/python -I motion/engine6.py --test 0.5,15,30,45` and look
   at build/e6_sheet.jpg. Fix only what is wrong: no text or badge hidden behind the character, no empty
   placeholder screen (draw what the line says), every scene with motion.
8. **Render once:** `build/.venv/bin/python -I motion/engine6.py --render --fps 60 --workers 2 --chunks 8`
   then `build/.venv/bin/python -I motion/engine6.py --encode --out out/video.mp4 --audio build/mix.wav`.
   A stopped render resumes from its finished chunks. Then `rm -rf build/seg6 build/e6test`.
9. **Story cut:** `ffmpeg -v error -y -i out/video.mp4 -t 59.8 -af afade=t=out:st=59.3:d=0.5 -c:v libx264 -crf 17 -c:a aac out/story.mp4`
   (Instagram's story is 60 s at most).
10. **Cover:** first draw TODAY'S middle element as `build/element.svg` (owner: «المان وسطش هر روز تغییر کنه
    نسبت به موضوع»): an SVG about the day's topic in a 900×480 box (viewBox="0 0 900 480"), ONLY
    #000000 and #D4A64A (opacity allowed), solid mustard shapes and mustard outlines on black, at most
    3 short Persian labels (font-size ≥ 30). Examples: an indicator → its line and the signal on the
    candles; the screener → a filtered table with a funnel; the calendar → a calendar page with a
    marked event; a market → its symbol chips and a chart; replay → the hidden future «؟». NEVER the
    day-1 replay chart for another topic (`--element candles` is for a replay topic only).
    `build/.venv/bin/python -I tools/cover2.py build/cover.png A "<series>" "<title 1>" "<title 2>" "<subtitle>" --element build/element.svg`
    (it refuses any other colour) then `ffmpeg -v error -y -i build/cover.png -q:v 2 out/cover.jpg`.
    Look at the cover once (build/cover.png): the element must say the topic at a glance.
11. **Texts:** `out/caption.txt` (≤5 hashtags; ends with the keyword ask «👇 کلمه‌ی «…» رو کامنت کن…», the risk
    line and the slogan). `out/comment.txt`, one `label: value` a line:
    `keyword: <the word said in the video>` · `match: any` (every comment on the reel gets the DM; the
    story and DM replies answer the keyword only) · `reply: <the DM text>` (one `reply:` line per line of
    the message: a greeting, a line per numbered step 1️⃣ 2️⃣ …, the risk line) · `link: <the utm link>` ·
    `button: <≤20 chars, e.g. ورود به پرو چارت>` · ten `public: <reply>` lines.
12. **Deliver:** out/ holds ONLY video.mp4, story.mp4, cover.jpg, caption.txt, comment.txt, topic.txt.
    `order.progress` done; the hub takes it from there. Say one short Persian line; no links.

## Where things are
- motion/engine6.py (render), engine5_template.html (motion graphics), toon.js (the character), audio4.py (music + mix)
- tools/: asr_words, qc_compare, word_probe, word_times, assemble_voice, audio_qc, cover2, pin_* (Pinterest)
- examples/day1/: the first reel's script, edit, word times, T, caption, comment, topic, cover, frames sheet, NOTES
- bank/: 365 topics (bank.json) and check_dupes.py
