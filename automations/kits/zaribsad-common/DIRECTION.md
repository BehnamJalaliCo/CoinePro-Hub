# Zarib ×100 (@zaribsad) — the direction bible: the PREMIUM bar (owner, 2026-11-14)

The owner, again and again: «کیفیت پرمیوم، نه یک چیز ساده», «به شدت سطح بالا», «انیمه در سطح واقعی،
تمیز و هر بار متفاوت». Cost has no limit. The first reel (ZEC, 2026-11-14) was clean but FLAT —
flat icons on a dark background, no key art, little depth. **That is the floor, not the target.**
Every reel must look like the work of a top motion studio or an anime opening: rich key art, depth,
light, camera, designed transitions, sound design. If a shot would not stop a thumb, it is not done.

## 0. The owner's corrections on reel 1 (2026-11-14) — check EVERY one before delivering
1. **Brand names must be SAID right.** The voice said «ویفنس» instead of «ویکس» (WEEX). In
   `script/voice.txt` write every exchange, coin and brand name in plain Persian letters as it is
   spoken (ویکس، ال‌بنک، اوربیت، تریدیار، زی‌کش…; never Latin letters in the voice text). After the
   voice: probe EACH brand word (`tools/word_probe.py` on its time span, or ASR on that sentence)
   and compare letter by letter; a wrong one: remake that sentence with a clearer spelling (e.g.
   «وی‌اِکس») until it is right. A brand said wrong = the reel is not deliverable.
2. **Real audio QC, to the last frame.** Reel 1 ended with a hit/thump nobody checked. The ending:
   the voice ends, the music fades out over ≥ 1 s, NO hit, boom, click or new sound in the last
   2 s. Check the final file: `ffmpeg -sseof -2.5 -i out/video.mp4 -af astats=metadata=1:reset=1 -f null -`
   (peak in the tail must fall, never jump); also check the start (no click) and every cue's
   level against the voice. Listen-proxy every SFX: none louder than the voice.
3. **No full stop at the end of on-screen captions.** Kinetic captions and titles never end with
   «.», «،» or «؛» (Reel 1 put a dot after every line). Questions and exclamations only when the
   line truly is one. The voice text keeps its punctuation; the screen does not.
4. **A dedicated cover, every reel.** Not a frame of the video: made by ChatGPT from the cover pack
   (COMMON/cover/COVER_PACK.md, owner 2026-11-15) — the page's three colours (navy, teal, white),
   a bold 2–4 word Persian title in our font, one element of the topic; a clean composition that
   reads at grid size (also check it cropped to 1:1 and 4:5: the title must survive both crops).

5. **(2026-11-15) No TradeYar logo, anywhere.** The first reel ended on the trade-future.ir logo; the
   owner: it is not Zarib×100's. The page's mark is its round profile photo + «Zarib×100» +
   «بهنام جلالی» (COMMON/brand/). Check the last 3 seconds and the cover for any other logo.
6. **(2026-11-15) The cover follows the cover pack** (COMMON/cover/COVER_PACK.md): the brand's three
   colours, the title in our font, one element of the topic.

7. **(2026-11-15) Crisp picture, no hits.** The ZEC draft had particles/rain/grain and blur that
   made it look low quality, and percussive hits between paragraphs: §3 and §4 forbid both now;
   check the stills for haze and every sentence boundary for a jump.

## 1. Choose the track per topic (write it and why in direction/CONTRACT.md)
- **ANIME** (a story, a person, fear and greed, a lesson told as a scene, news drama): limited-TV
  anime done for real — AI key art of a consistent cast and painted backgrounds; cel-shaded look;
  multi-plane parallax (3–5 planes); camera push, pan, shake on impacts; speed lines, impact frames,
  smears; character changes on twos; anticipation and overshoot; mouth flaps from the voice
  loudness (closed in silence), blinks; light effects (rim light, glow) — sharp, never hazy.
- **CINEMATIC MOTION GRAPHICS** (how a thing works, data, prices, a coin, a mechanism): 3D-feeling
  depth (perspective, layered glass cards, parallax), light sweeps and a clean glow, a colour grade;
  every plate SHARP (no depth-of-field blur, no particles, no grain); real data visualised (animated charts and
  counters from the facts); photoreal or 3D-render key art as the world behind the graphics.
- **HYBRID**: an anime host or guide character leading the viewer through motion-graphics cards.

## 2. Key art — mandatory
- **At least 6 AI-made images per reel**, each the hero of its shot (never a flat icon as a shot's
  main visual; icons only as small secondary UI). `substitute.call` seat creative, kind image,
  placement other: player **gpt** (ChatGPT) for anime / illustration, player **gemini** (Gemini,
  its «Argon» model) for photoreal. One brief per image: subject, pose and expression, framing
  (9:16 full plate, or a single subject on a flat plain background for cut-out), light, palette,
  style anchors, cast anchors (the same character described the same way every time), and
  ALWAYS "no text, no letters, no numbers, no logos, no watermark".
- Look at every image (Read it). Wrong, off-model, bad hands/faces/edges, text inside: regenerate
  (up to 2 more tries), else redesign that shot. Cut subjects out (flat background → alpha) to
  move them on their own plane. Upscale to fit 1080×1920 cleanly (Lanczos), never blurry.
- AI images are STILL assets only. Every motion is yours, in code. No AI video, ever.
- **Logos are REAL, never AI-drawn:** the coin's official logo from its facts (`logo`, CoinGecko),
  the exchange's logo from its own site (or its official press kit). Download with curl; vectorise
  or clean the edges if needed; place it as its own layer.
- **The page's own mark — NEVER TradeYar's logo** (owner, 2026-11-15: the trade-future.ir /
  coinepro.com «TY» logo is not Zarib×100's). When a reel wants the page's mark (its last seconds):
  COMMON/brand/profile_round.png (the page's round profile photo) + «Zarib×100» (Eco Bold) and
  «بهنام جلالی» (Eco Regular) — nothing else. See COMMON/brand/README.md.

## 3. Every shot
- **Camera:** never static. Push-in, dolly, parallax drift, slow rotation, rack focus, a whip on the
  transition. Eased curves (cubic/expo), never linear. Motion blur on fast moves (average 3–4
  sub-frames per frame, or a directional blur).
- **Depth and light:** at least 3 planes moving at their own rates (parallax); clean glow and light
  sweeps; a light vignette; ONE colour grade across the reel. **Crisp, never hazy** (owner,
  2026-11-15, on the ZEC draft: «یه تاری… یه ذراتی توی ویدیو هست که کیفیت رو خیلی پایین آورده»):
  NO particle, dust, rain, snow, bokeh or film-grain overlay; NO depth-of-field or gaussian blur on
  a key-art plate or a card; motion blur only for the few frames of a fast whip. The key art shows
  at its full sharpness (upscaled cleanly, never softened).
- **Typography:** IRANYekanX Eco only (/home/studio/kits/fonts-eco; Bold for headlines). Kinetic
  Persian captions word by word, the key word of each sentence popped in the accent colour; big
  numbers count up and LAND exactly on the fact (hold ≥ 1.2 s); captions in the safe area (keep
  the top 220 px and the bottom 380 px free of key text). Persian digits.
- **Transitions:** designed and motivated — match cut, whip pan with blur, mask/shape wipe,
  zoom-through, light flash, ink/smear wipe for anime. One family per reel; no plain cut unless
  it is a deliberate hit on the beat.
- **Pacing:** a new visual idea at least every 2–2.5 s; the hook in the first 1.5 s (a bold image
  and a line that makes them stay); the payoff before the call to action.

## 4. Sound
A music bed whose energy follows the edit (rise into the hook and the CTA), the music ducked under
the voice, the voice always clear, about −14 LUFS. (Use motion/audio4.py; write your own cue list.)
**No hits, ever** (owner, 2026-11-15, on the ZEC draft: between paragraphs «یه صدایی مثل انتهای صدایی
که توی ویدیو قبلی بود میاد»): no taiko, boom, impact, sub-drop, thump or any percussive cue on a
transition, a reveal, a number or between sentences; at most a very soft airy swish (≥ 12 dB under
the voice) on a big transition. Check EVERY sentence boundary of the final mix: astats on a 0.6 s
window around each pause between sentences — the peak must not jump above the music bed's level.

## 5. Different every time — the day's look (deterministic, so two days never match)
Let N = the day of the year. Take: transition family = N mod 7, camera language = N mod 6,
accent = N mod 5, music mood = N mod 4 from the tables below, then build on them freely.
- Transitions: 0 whip-pan blur · 1 mask/shape wipes · 2 zoom-through · 3 light-flash cuts ·
  4 ink/smear wipes · 5 match cuts on shapes · 6 glitch/RGB-split (clean, sparing)
- Camera: 0 slow push-ins · 1 lateral parallax dollies · 2 orbit/rotation · 3 handheld micro-drift ·
  4 crane up/down reveals · 5 snap zooms on beats
- Accent on the TradeYar navy #030B26: 0 teal #0FB5AE · 1 gold #E8B64C · 2 violet #8B7CF6 ·
  3 coral #FF6B5B · 4 electric blue #3DA5FF
- Music: 0 dark cinematic pulse · 1 upbeat electronic · 2 lo-fi anime chill · 3 epic orchestral hybrid

## 6. Quality control — be the strictest art director
1. Before any render: the contract (track, look of the day, shot list on the word times, the asset
   briefs, the transitions, the sound cues).
2. Stills: `--test` at 16+ times (every shot's start, middle and end), one contact sheet. Score
   EVERY shot /10 on: key art quality, depth and light, motion idea, typography, clarity, polish.
   Anything under 8 is redone. At least 2 rounds; compare honestly with a top studio's reel.
3. Render once (1080×1920, 60 fps; 30 fps only if 60 would not finish in time), then look at the
   final file at 8 random times; a broken frame, a cut word, a mismatched number: fix and re-render.
4. In your last line to the hub, give the track, the look of the day and your shot scores.
