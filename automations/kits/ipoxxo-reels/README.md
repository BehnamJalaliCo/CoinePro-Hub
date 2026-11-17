# ipoxxo (@ipoxxo.vpn) — the daily reels: gripping edutainment, ipoxxo the sponsor (owner 2026-11-17)

The owner, 2026-11-17: «تنها اتوماسیونی که جواب نگرفته ipoxxo هستش که ویدیوهاش ضعیفن و به درد پیج نمیخورند. من
نظرم اینه که محتوا سرگرمی یا علمی بسازیم یا محتوایی که مخاطب تا ثانیه آخر میخکوب بشه و روی ویدیو تبلیغات کانال
تلگرام رو بذاریم و آخرش بگیم اسپانسر این ویدیو ipoxxo پروکسی و vpn کاملا رایگان، لینکشو میخوای تو کپشن نوشتم».

So the page posts NO direct ads any more. Every reel is a gripping 30–60 s story of science, curiosity, a
mystery or a true story, and the FREE Telegram channel **t.me/ipoxxo** (free proxies and VPN configs) is its
**sponsor**: a readable badge on the video, the sponsor line in the voice right after the payoff, an end card,
and the link in the caption. Any comment still gets the channel's link in a DM.

You are the day's session, started by n8n the evening before (two reels a day: your order's title says
«ریلز اول», the noon reel, or «ریلز دوم», the evening one). Work alone: never `order.ask`, never wait for an
approval, never send a preview. You ARE on the workshop: do every step yourself, in this folder, over as many
turns as it takes (keep `NOTES.md` current: the topic, its sources, what is done, what is next). NEVER call
`workshop.run`. The hub publishes your package at the hour in your order and closes the session.

KIT = /home/studio/kits/ipoxxo-reels (read only, except topics.md's status column through tools/topic.py).
COMMON = /home/studio/kits/ipoxxo-common. PCKIT = /home/studio/kits/prochart-reels (its voice tools only).
PY = /home/studio/kits/prochart-reels/venv-render/bin/python; export PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.
ASR = build/asr/venv/bin/python; M = the Whisper model: `M=$(ls -d build/asr/models/models--Systran--faster-whisper-large-v3/snapshots/*/)`.

## FIRST read COMMON/DIRECTION.md (the premium bar), then `KIT/example/` — the bar of this kit
`example/NOTES.md` (the sample reel 2026-11-17: script, sources, timing, scores, what was redone),
`example/scenes.js` (its scenes on the stage), `example/contact_sheet.jpg` (a frame every 2 s of the final file).

## The owner's rules (never change)
- **Edutainment, not an ad.** The story is the reel. The channel appears ONLY as the sponsor: the badge
  (the stage draws it from 1.9 s), the sponsor line, the end card. No other word about proxies in the voice.
- **The sponsor line** is the voice's LAST line, right after the payoff (a one-line kicker may sit between,
  ≤ 4 s), exactly this text (its spelling is what makes Cruz say the names right; checked 2026-11-17):
  `اسپانسر این ویدیو، آی پی اوکسو؛ پروکسی و وی پی اِنِ کاملاً رایگان. لینکش توی کپشنه.`
- **True facts only.** Every number and claim from a source you checked today; the sources in NOTES.md. When
  sources disagree, say the careful version («حدود», «تقریباً»). No politics, sanctions, legal matters, war as a
  subject, religion, medical advice or fear-mongering; nothing about any government or country's rules.
- **Length 30–60 s** (what the story needs); 1080×1920, 60 fps. Voice «Cruz» by `speech.make`, NO style, NO
  narrator.set; casual Persian with «تو». Font IRANYekanX Eco only; Persian digits on screen; NO full stop,
  «،» or «؛» at the end of on-screen text.
- **Every reel looks different** (DIRECTION §5, the look of the day) and premium: AI stills from ChatGPT AND
  Gemini, each checked by looking; every motion is yours, in code.

## The retention structure (the owner's; score every reel on it, under 8 = redo)
1. **Hook in the first 1.5 s.** Frame 0 is fully drawn (the hero still + the hook title); the voice starts
   by 0.35 s with the most surprising claim or a question the viewer cannot leave. No intro, no greeting.
2. **A curiosity gap kept open:** name the question by about a third of the reel (a big moment, e.g. a
   full-screen «چرا؟»), keep it on screen (`CONFIG.gap`: the chip under the badge), pay it off near the end
   (70–85 % of the reel; the chip flips to the answer).
3. **A pattern interrupt every 2–4 s:** a cut, a punch-in, a counter landing, a new layer, a new still.
   `reel.py --timeline` prints the longest stretch without a shot change or a `BEAT`: ≤ 3.5 s (4 s is the limit).
4. **No dead frame:** the camera never stops (`CAM` always drifts); no empty stage; captions word by word.
5. **Payoff → the sponsor line at once (≈ 4–6 s) → the end card** (≈ 2.4 s; the stage draws both).
6. **The loop:** the end card sits on the hook's still, so the replay feels continuous.

## The day, step by step (`order.ack` these steps at the start; `order.progress` each one)
0. **Setup:** `mkdir -p script qc direction/inspo build out in assets/use motion tools`;
   `cp PCKIT/tools/{asr_words,qc_compare,word_times,assemble_voice,audio_qc,voice_seams,word_probe}.py tools/`;
   `ln -sfn PCKIT/asr build/asr && ln -sfn PCKIT/venv-render build/.venv`.
1. **Topic:** the order's «ریلز اول» → `--slot noon` (science, curiosity, how it works), «ریلز دوم» → `--slot evening`
   (true story, mystery, entertainment): `python3 -I KIT/tools/topic.py next --slot <slot>` → `topic.claim`
   «ipoxxo: <topic>»; refused = `topic.py mark <#> taken`, then `next` again. Claimed:
   `topic.py mark <#> --slot <slot> --publish "<the day and month of your order's «انتشار خودکار …», e.g. ۲۸ آبان>"`
   (→ `used:<YYYY-MM-DD>:<slot>`; the stories' 10:00 teaser reads it). → `out/topic.txt` (line 1 the topic; line 2
   «سبک: <the look, 3–6 words>»). Used up: invent one in the same spirit, add it at the end of topics.md with
   the next number and its source (`topic.py check` must pass), then claim and mark it.
2. **Facts:** ONE `substitute.call` seat `quick_search` (player deepseek) asking for the topic's key facts and
   numbers with their sources; open/compare with the row's `source`. Write the facts you will use and their
   links in NOTES.md. A fact you cannot confirm is left out. (Refused or down: the row's source and only what
   you are sure of.)
3. **Script** (yours; ChatGPT may draft, `substitute.call` player gpt, seat content_draft): one line per beat,
   **95–125 words** (Cruz reads about 2.2 words a second; the sample: 112 words = 54 s), the hook first, the
   question by a third, a new fact every line, the payoff, an optional one-line kicker, then the sponsor
   line exactly. Names and numbers as they are SAID, in Persian letters («دوازده کیلومتر», «اورست»); the
   screen shows digits (`CONFIG.caps`). → `script/voice.txt`.
4. **Voice:** `speech.make` (Cruz), the WHOLE script in one call. QC, in this order (a take that fails any step is
   remade with a new `speech.make`, the WHOLE script; never splice, never trim by hand — the owner, 2026-11-17):
   - `ASR -I tools/audio_qc.py in/<take> qc/take.audioqc.json` — 0 clicks, 0 cuts, 0 bursts (one take in three
     carries a burst: just ask again);
   - `ASR -I tools/asr_words.py $M in/<take> qc/asr.txt qc/asr.json` → `python3 -I tools/qc_compare.py
     script/voice.txt qc/asr.txt qc/qc.json`: every line heard (a WHOLE line missing = a dropped sentence:
     remake), and `tools/word_probe.py` on every name and on the sponsor line («آی پی اکسو», «وی پی این»);
   - pauses only with `ASR -I tools/voice_seams.py pauses in/<take> qc/voice_raw.wav 0.40`;
   - `ASR -I tools/assemble_voice.py qc/voice_raw.wav qc/asr.json - qc/voice_final.wav` →
     `ASR -I tools/audio_qc.py qc/voice_final.wav qc/voice_final.audioqc.json`: **0 clicks, 0 cuts, 0 bursts**;
   - word times on the FINAL voice: `ASR -I tools/asr_words.py $M qc/voice_final.wav qc/asr_final.txt
     qc/asr_final.json` → `ASR -I tools/word_times.py script/voice.txt qc/asr_final.json qc/voice_final.wav
     direction/word_times.json` (one timed line per script line).
5. **The look of the day** (DIRECTION §5: N = the day of the year, +3 for the evening reel → transition
   family, camera, support accent, music mood) and **inspiration** (DIRECTION §1.1, 3–5 Pinterest queries on the
   topic's visual world and on premium documentary motion design). One line in `direction/CONTRACT.md`.
6. **Key art: at least 6 stills, every brief to BOTH players.** `substitute.call` seat creative, kind image,
   placement other, once with player **gpt** and once with player **gemini**, the same brief (DIRECTION §2):
   photoreal or premium 3D, the topic's TRUE colours (not the brand's navy), 9:16, "no text, no letters, no
   numbers, no logos". Send them all at once and end the turn (`order.progress` «تصویرها در راه است»): the
   pictures reach `in/` at your next turn. Read every picture; keep the better of each pair; wrong (a fact
   shown wrong, warped, text in it): ask again saying what was wrong (≤ 2 more). A subject that must move
   on its own plane: `PY -I KIT/tools/cutout.py in/x.png assets/use/x.png --trim`. The kept ones →
   `assets/use/<name>.jpg|png` (the stage calls them by name). A texture for a whole world (strata, a
   starfield, a city map) is worth one of the six.
7. **Contract:** `direction/CONTRACT.md` — the idea and why it holds to the last second, the look, the
   question and where it is paid off, the shot list on the word times (an interrupt every 2–4 s), the stills
   per shot, the transitions, the sound mood. Then `NOTES.md`.
8. **Build** `motion/scenes.js` on the kit's stage (`KIT/motion/stage.html`: its header is the API —
   `CONFIG`, `SHOT`, `BEAT`, `LN`/`WD`/`WF`, `plate`/`CAM`/`img`/`disc`, `T`/`HEAD`/`chip`/`gauge`/`ring`…).
   Model: `KIT/example/scenes.js`. Write parameters and shots, not a new engine; every frame a pure function of
   time; a helper of your own lives in scenes.js. `CONFIG`: the look, `gap`, `sponsorLine` (the last line's
   index), `caps` (the on-screen words with digits, the key words in cyan).
9. **Stills QC** (the strictest art director): `PY -I KIT/motion/reel.py --test <16+ times>` → read
   `build/test_sheet.jpg` (and single stills in build/test/ at full size where text is small). Score EVERY shot
   /10 (key art, motion idea, typography, clarity, retention); under 8 is redone; at least 2 rounds. Check every
   Persian word letter by letter (no glued words, no clipped text, nothing under the badge or in the bottom
   380 px), the hook frame at 0.0 s, the gap chip, the sponsor card and the end card.
10. **Sound:** `PY -I KIT/motion/reel.py --timeline` (longest ≤ 3.5 s) → `PY -I KIT/motion/sound.py` (the
    bed in the day's mood, soft swishes on the designed transitions, the drop on the payoff, −14 LUFS) →
    `ASR -I tools/audio_qc.py build/mix.wav qc/mix.audioqc.json`: 0 clicks, 0 cuts, 0 bursts.
11. **Render once:** `PY -I KIT/motion/reel.py --render --workers 2 --chunks 8 --fps 60` (resumable; about
    3–4 minutes for 55 s) → `PY -I KIT/motion/reel.py --encode --audio build/mix.wav --out out/video.mp4`.
    Then: `--sheet --step 2` (→ qc/contact_sheet.jpg: read it whole) and `--frames 8` (→ build/final_frames.jpg);
    the file's own audio: `ffmpeg -v error -i out/video.mp4 -vn -ac 1 build/final_audio.wav` → audio_qc = 0/0/0;
    the tail: `ffmpeg -sseof -2.5 -i out/video.mp4 -af astats=metadata=1:reset=1 -f null -` (the peak falls).
    Broken: fix and render again (`rm -rf build/seg` first). Done: `rm -rf build/seg build/test`.
12. **Cover — COMMON/cover/COVER_PACK.md:** the title = the hook at its most striking (2–4 words, e.g.
    «عمیق‌ترین چاه دنیا»), the element = the reel's hero subject; ChatGPT with the board attached; check every
    letter; 1080×1920 `out/cover.jpg`. Never a video frame.
13. **Texts.** `out/caption.txt`:
    ```
    <the hook as a question or a bold line that stops the scroll>
    <2–4 short lines that deepen the mystery; never the payoff itself>
    <one line that asks for a comment, tied to the topic>

    🎬 اسپانسر این ویدیو: ipoxxo، پروکسی و VPN کاملاً رایگان 👇
    t.me/ipoxxo
    لینک رو دایرکت هم می‌خوای؟ هر کامنتی بذاری، برات می‌فرستم.

    #<the topic> #دانستنی #ipoxxo
    ```
    Exactly 3 hashtags. `out/comment.txt` (the hub makes the DM rule; every comment gets the DM), one
    `label: value` a line:
    ```
    keyword: لینک
    match: any
    reply: <a warm first line about the reel's topic>
    reply: <the sponsor: ipoxxo gives free Telegram proxies and V2Ray/VPN configs, fresh again and again>
    reply: <how to join: tap the button, then «Join»>
    button: ورود به کانال | https://t.me/ipoxxo
    public: <ten short public replies, all different: a line about the topic + that the DM is on its way>
    ```
    Timeless (no date, no "today's list").
14. **Deliver:** out/ holds ONLY video.mp4, cover.jpg, caption.txt, comment.txt, topic.txt. `order.progress`
    done: one short Persian line — the topic, the look, the shot scores and the retention score.

## Render safely
At most 2 Chromium workers (the workshop has 4 GB); `reel.py` closes Chromium after each use. Keep command
output short (`| tail -3`). Under `nice`.

## Where things are
- `motion/stage.html` (the stage: the API, the badge, the gap chip, the captions, the sponsor and end cards,
  the transitions), `motion/reel.py` (stills, timeline, render, encode, contact sheet), `motion/sound.py`
  (the music bed, the swishes, the mix).
- `tools/topic.py` (the bank), `tools/cutout.py` (cut-outs, the ISNet model in /home/studio/kits/models).
- `topics.md` — the bank (175 topics, two lanes, each with a source).
- `example/` — the sample reel of 2026-11-17 (Kola Superdeep Borehole): scenes.js, voice.txt, NOTES.md,
  CONTRACT.md, contact_sheet.jpg; its stills are in /home/studio/kits/ipoxxo-reels/example/assets (not in git).
- `bank/ideas.json` — the old ad ideas (2026-11-16), retired: never used for a reel again.
