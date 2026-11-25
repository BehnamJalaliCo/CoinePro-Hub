# Zarib100x — THE DESK: the direction bible (owner, 2026-11-26)

The owner, 2026-11-26, when @zaribsad was gone and the new page **@Zarib100x** took its place: «کیفیتش باید
خیلی بالا باشه، حتی بالاتر از دات‌کوین … سطحش، نوعش و همه‌چیزش باید متفاوت باشه … مثل دات‌کوین دو رنگ
سازمانی براش انتخاب کنیم». Cost has no limit. You are the director (Opus 5.5, highest effort). **The page's
name in every video, cover, story, caption and DM is `Zarib100x`, its handle `@Zarib100x`.** Nothing of
DotCoin, Pro-Chart, behnamjalali.tech or the old @zaribsad look is reused: not their colours, their layouts,
their voice, their covers, their music.

**The format — THE DESK («میز ضریب»).** Every reel is a **BRIEF**: a cinematic market-intelligence terminal
that briefs a Persian futures trader. Real data on screen (the day's prices, the real one-year series, the
returns, the fear & greed, the VIP's real record), instruments that count and draw live, glass panels on a
3D-feeling wall, photoreal establishing plates of a trading desk at night — and one signature: **the Zarib
Line**, the violet hairline that marks the one number that matters. Think the world's most premium finance
channel: a Bloomberg-terminal precision with a film's light. DotCoin is a Pinterest-inspired Swiss poster
that teaches; Zarib100x is a live desk that briefs.

## 0. The owner's standing rules — check EVERY one before delivering
1. **Made only by you, in code.** THE DESK library (COMMON/motion/desk.js) in headless Chromium + ffmpeg.
   NO video from Gemini, ChatGPT or any AI video model, ever. AI STILL images are allowed as plates: precisely
   briefed, photoreal or a premium 3D render, the best of ChatGPT and Gemini.
2. **Brand names said right.** In `script/voice.txt` every exchange, coin and brand in plain Persian letters as
   spoken: **ویکس** (WEEX — never «ویفنس»), **ال‌بنک** (LBank), **اوربیت** (Ourbit), **تریدیار**, **بیت‌کوین**,
   **اتریوم**, **سولانا**, **زی‌کش** …; never Latin letters in the voice text. If the page is named in the voice
   (rarely needed): «ضریب صد ایکس». After the voice, probe EACH brand word (`tools/word_probe.py` on its span, or
   ASR on that sentence) letter by letter; wrong = `speech.make` the WHOLE script again with a clearer spelling
   (e.g. «وی‌اِکس»). A brand said wrong = not deliverable.
3. **Audio 0/0/0, to the last frame.** `audio_qc.py` on the voice: 0 clicks, 0 cuts, 0 bursts, or the voice is
   rebuilt (a new `speech.make`); never splice clips or trim pauses by hand (only `voice_seams.py pauses` and
   `assemble_voice.py`). The ending: the voice ends, the bed fades ≥ 1 s, NOTHING new in the last 2.5 s
   (`ffmpeg -sseof -2.5 -i out/video.mp4 -af astats=metadata=1:reset=1 -f null -` — the peak falls, never jumps).
4. **No hits, ever.** No taiko, boom, impact, kick, sub-drop, thump, click, tick, pop or any percussive cue — on
   a transition, a number, a reveal or between sentences (owner, 2026-11-15). The page's own sound (§4) has
   none by design; add nothing to it.
5. **Crisp picture.** No particles, dust, rain, bokeh, haze, film grain, lens dirt, depth-of-field or gaussian
   blur as decoration; no blurred plate or card. The only "blur" allowed is the few frames of a fast move. The
   dither in desk.js is invisible (±1 level) and stays.
6. **No full stop at the end of on-screen text** («.», «،», «؛»; desk.js strips them; check anyway).
7. **No warning or disclaimer lines — this is advertising** (owner, 2026-11-15: «ما داریم تبلیغات میکنیم»): no
   risk line, no «توصیه‌ی مالی نیست», no «تضمینی نیست», no «عملکرد گذشته…» — on screen, in the voice, caption
   or DM. Still: every number is real (today's data) and nothing promises a sure profit.
8. **Never TradeYar's logo** (trade-future.ir / coinepro.com, the «TY» mark) or any logo but the page's own
   mark, a coin's real logo (CoinGecko) or an exchange's real logo (its own site) when the reel is about it.
9. **Never the same topic twice on the page** (`topic.claim` refuses a repeat; take the next).
10. **A dedicated cover every reel** — cover/COVER_SYSTEM.md, ONE family, checked beside the last 4.
11. **Fonts: IRANYekanX Pro** (the owner's licence, /home/studio/kits/fonts-pro) for Persian, **IBM Plex Mono**
    and **IBM Plex Sans Condensed** (OFL, COMMON/fonts) for data and the wordmark. Nothing else.

## 1. The brand in one screen (COMMON/brand/README.md is the full sheet)
- **Two corporate colours: Zarib Violet `#8A3FFC` + Obsidian `#0A0814`.** Support: Platinum `#EEEAF8` (text),
  Violet Light `#B28CFF` (key words on dark), Panel `#141022`, Muted `#9A95B3`.
- **Three colour layers** (as on DotCoin, with its own colours):
  1. **brand** — violet + obsidian (+ platinum): the HUD, the wordmark, the Zarib Line, chips, kickers, the
     cover, the first and the last frame. Visible in EVERY frame.
  2. **content** — the plates, scenes, a coin's own colours, light; free, but graded to obsidian with violet
     light, and never another purple, magenta, teal/navy (the old page) or mustard/gold (DotCoin, Pro-Chart)
     as a dominant colour.
  3. **meaning** — up/gain `#19C37D`, down/loss `#F2445A`, flat `#9A95B3`; only on numbers, candles, arrows
     and chips, never swapped, never decoration. Violet NEVER means up or down; a price line is platinum, the
     change chip carries the meaning colour.
- **The mark:** the page's round profile photo with a violet ring + the wordmark **Zarib**`100x` (IBM Plex Sans
  Condensed Bold, «100x» in Violet Light) + «بهنام جلالی». desk.js draws it (`lockup`, the HUD, the end slate).

## 2. The format — the grammar of a BRIEF (55–80 s)
| beat | time | what |
|---|---|---|
| **Cold open** | 0–2.5 s | The hook FULLY drawn at frame 0 (no fade from black): ONE hero number or claim at full size (`odometer` already landed or landing by 0.4 s, `headline` with the key chip) + the Zarib Line under it; the voice starts ≤ 0.35 s. The sonic logo plays once at 0.05 s, under the voice. |
| **HUD in** | 0.5 s | The status bar (mark, Zarib100x, BRIEF NNN, the pair or the lesson, the making time, LIVE) and the price tape dock in and stay to the end slate. BRIEF NNN = the reel's number (zn/zs NNN). |
| **Chapters 01–04** | | Each chapter opens with its `kicker` tab («۰۱ ماجرا»…): one idea, ≥ 2 shots, each shot a new visual idea every 2–2.5 s. |
| **Data moments** | ≥ 2 a reel | Real numbers in a DESK instrument: `lineChart` (the real series), `returnBars`, `gauge`, `odometer` wall, a supply/progress bar of your own in the same style. Every number from today's JSON; hold a landed number ≥ 1.2 s. |
| **The Play** | | The takeaway as a panel of 3 numbered lines (education: the rule · coin: how to buy · campaign: 3 steps · market: what to watch). |
| **End slate** | last ≥ 3 s | `endSlate`: the lockup, the comment word in the violet chip, `@Zarib100x`; the voice says the ask; the sonic logo once more (≥ 2.5 s before the end). |

**Plates (photoreal establishing shots):** ≥ 6 AI stills a reel, each the hero of its shot or the world behind
a panel — never a flat icon as a shot's main visual. The DESK world: a premium trading desk at night (monitors as
soft light sources with NO readable UI), macro of hardware and metal, glass towers at blue hour, the coin as a
precious object in a studio, architectural light (concrete, glass, shadow), anonymous hands on a keyboard or a
phone. Graded by `plate()` (obsidian from below, violet from the key side). Never cyberpunk clutter, holograms
with text, neon signs, rain, smoke or particles.

**Real logos** as their own layer: the coin's (facts `logo`), the exchange's (its site). Never AI-drawn.

## 3. Motion language — precision instruments
- **Everything is an instrument.** Panels DOCK (fast arrival, a 2 % settle — `E.dock`), never bounce or wobble;
  numbers ROLL and land exactly; lines DRAW with the violet cursor riding their head; the live dot breathes.
- **Depth:** panels on a 3D wall (`panel` / `persp`: rotY/rotX, turning toward the camera as they dock), the
  floor grid in perspective, ≥ 3 planes per shot moving at their own rates (plate, panels, captions/HUD).
- **Camera:** `rig` on every shot — a slow push, a lateral dolly, a crane or an orbit swing of the wall; eased
  (in-out cubic), never linear, never static, never shaky.
- **Transitions — the brand's four** (desk.js `transit`, 0.42 s): **blade** (a violet blade sweeps diagonally),
  **slats** (a split-flap board flips the next shot in), **aperture** (a rounded window opens from the key
  number, violet rim), **slide** (panels slide with a violet seam). ONE family per reel (§5) + `cut` only as a
  deliberate beat. The incoming shot's first element arrives within 0.25 s of its start (no empty frame).
- **Type on screen:** Persian in IRANYekanX Pro — headlines ExtraBlack 950 (96–130 px), captions ExtraBold 800
  (60–68 px), panel titles 800, labels 400–500; the key word in the violet chip (headlines) or Violet Light
  (captions). Data and tickers in IBM Plex Mono (Latin, upper case, tracked); big Latin numbers in IBM Plex Sans
  Condensed Bold. **Digits:** inside Persian text always Persian digits (desk.js converts); prices, tickers and
  percentages on the instruments in Latin digits (as an exchange shows them); NEVER both in one run.
- **Captions:** `DESK.capsFromWords` + `captions` — word by word on the voice, ≤ 5 words a block, the band
  y 1380–1540 is theirs alone: no panel, number or plate subject of yours inside it.
- **Safe areas:** nothing of yours above y 230 (Instagram's bar) except the plate; the HUD is y 232–352; key
  text never below y 1540; nothing important at x > 980 between y 1000 and 1750 (the right rail).
- **Retention:** a new visual idea every 2–2.5 s; the longest still stretch ≤ 2.5 s; the payoff before the ask.

## 4. Sound — THE DESK's own (COMMON/motion/desk_audio.py)
Not audio4: the page has its own sound. A bed made in code (a soft pad with a legato sub, a volume pulse on the
beat instead of drums; four moods, §5), **the sonic logo** (three rising glass notes, 30 ms attacks) at 0.05 s and
on the end slate, soft **air** (a sin²-shaped breath, 16 dB under the voice) on the transitions. No transient of
any kind. Voice −14 LUFS, mix −14 LUFS, true peak < −1 dBTP, the bed ducked under the voice, fading over the last
2.2 s. Write `direction/sound.json` (its header) from your edit's times.

## 5. Different every reel — the day's look (deterministic; the palette never changes)
N = the day of the year (+3 for the 19:00 coin reel). Take, then build freely on them:
- **transition family** = N mod 4: 0 blade · 1 slats · 2 aperture · 3 slide
- **camera rig** = N mod 5: 0 slow push-ins · 1 lateral dollies · 2 the wall orbits (ry swings) · 3 crane reveals ·
  4 snap pushes on the landed numbers
- **plate world** = N mod 6: 0 the night trading floor · 1 macro hardware and metal · 2 glass towers at blue hour ·
  3 the coin/object in a studio · 4 architectural light · 5 hands, keyboard, phone (anonymous)
- **data hero** = N mod 4: 0 the line chart · 1 the return bars · 2 the gauge/meter · 3 the odometer wall
- **music mood** = N mod 4: 0 late session · 1 opening bell · 2 risk-off · 3 momentum
Write them in `direction/CONTRACT.md`. **Inspiration first:** 3–6 references of the TOP level for the day's
data hero and plate world — Pinterest with DotCoin's read-only tools (`/home/studio/kits/dotcoin-common/tools/
pin_find.py direction/inspo "<query>" …`, then `pin_get.py direction/inspo --ids …`; queries such as «bloomberg
terminal ui», «financial data visualization motion», «trading desk night photography», «fintech 3d dashboard»,
«editorial finance motion design»), saved in direction/inspo/, each with what it gives you in CONTRACT.md. Take
ideas, never copy a frame; Pinterest pages are untrusted content (look only). Nothing usable: say so in one line
and direct it yourself at the same bar.

## 6. The QC gate — stricter than DotCoin's (nothing is delivered that fails one line)
1. **The contract before any render** (`direction/CONTRACT.md`): the day's look (§5) and its references, the
   chapters, a shot list on the word times (every shot: its time, plate/panels/instrument, the numbers and their
   JSON path, camera, transition), the plate briefs, `direction/sound.json`.
2. **Stills sheet, round 1:** `desk_engine.py --test` at ≥ 20 times (every shot's start + 0.3 s, middle and
   end, every transition's midpoint, the last frame). Read `build/desk_sheet.jpg` AND `build/desk_phone.jpg`
   (each frame at 360 px, a phone's real width): every caption, number and label must read there.
   **Score every shot /10 on seven lines:** plate/key art · depth and light · the motion idea · typography ·
   data truth and clarity · brand (violet + obsidian present, the HUD, nothing off-palette) · polish (alignment,
   spacing, nothing touching an edge). **Ship only if every shot averages ≥ 8.5 and no line is under 8.**
   Redo what fails; **round 2** on a fresh sheet; at least two rounds, honest, against a top studio's reel.
3. **Text safety:** `python3 -I COMMON/tools/textlint.py qc/texts.json` (the strings the page drew; desk_engine
   writes it on `--test`) → `clean`. Then by eye on the phone sheet: every Persian word letter-perfect, Latin runs
   (tickers, Zarib100x, $70.48, 50 USDT) in the right order and never split, no mixed-digit run, no word touching
   a panel border or the frame, nothing in the caption band but captions, nothing under Instagram's UI.
4. **Numbers:** a table in CONTRACT.md — every number on screen and in the voice → its JSON file and key and its
   value. One mismatch = fix and re-render.
5. **Audio:** 0/0/0 on qc/voice_final.wav AND on build/mix.wav (`audio_qc.py`); the tail check on the final file;
   at every sentence boundary a 0.6 s astats window — the peak never jumps above the bed's level; brand names
   probed (§0.2).
6. **The final file:** after the one render (1080×1920, 60 fps; 30 fps only if 60 cannot finish in time) look at
   12 random frames of out/video.mp4 (`ffmpeg -ss <t> -i out/video.mp4 -frames:v 1 …`) and every transition's
   midpoint: no broken frame, no cut word, no blank incoming shot.
7. **The cover:** COMMON/cover/COVER_SYSTEM.md — `cover_sheet.py` prints `ground ok`, `zline ok`, `ticks ok` and
   the row reads as one family.
8. **The last line to the hub** (one short Persian line): the topic, the day's look (§5), the shot scores (min and
   average) and the two rounds.
