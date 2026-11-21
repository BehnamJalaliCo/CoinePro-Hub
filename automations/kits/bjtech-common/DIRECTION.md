# @behnamjalali.tech — DIRECTION: the LUMEN language (owner 2026-11-18)

The owner: «این پیج باید فوق‌العاده متفاوت از چهار پیج دیگه باشه … موشن‌گرافی و همه چیزش به‌روز و پریمیوم،
پریمیوم‌ترین حالت ممکن که کاربر واقعا تفاوت رو حس بکنه». The page is «Behnam Jalali | AI & Tech» (bio: «ساده،
کاربردی و بدون حرف اضافه»). Its language is **LUMEN**: an AI-native interface on ink — glass panels, live code and
terminals, real benchmark bars and counters, and ONE signature light, the **spectral edge** (the iridescent glow an
AI assistant wears when it thinks). Nothing of Pro-Chart, Zarib×100, ipoxxo or DotCoin is ever reused: not their
colours, fonts, voice-over voice (except Arlo, the owner's choice), covers, music or layouts.

The bar is `KIT/example/` of bjtech-reels (Claude Fable 5.2, 62 s): read its NOTES.md and contact_sheet.jpg.

## 0. The hard rule
⟨2026-11-21⟩ the owner: «اینجوری به همه لو میدی ما داریم چیکار میکنیم». **Never about ourselves:** no topic, line, card, caption or example about our holding, its companies or agents, our automations, workshop, accounts, tools or how this page's content is made. The `behind` lane is retired (every row `taken`); the page talks about AI and tech in the world, never about its own kitchen.

## 1. The five things a viewer must feel
1. **It is live.** Something is always being computed: a caret blinks, a number counts, a bar grows, code types,
   the camera breathes. Never a still slide.
2. **It is precise.** Real numbers, real names, real sources (a `source:` line in mono under every chart). Persian
   letter-perfect, Latin names in Latin, digits in Persian outside Latin runs.
3. **It is calm and expensive.** Ink, air, one light. Few colours at once; generous margins; no clutter, no emoji,
   no stock-photo collage, no cheap glitch, no shaking text.
4. **It ends.** Every reel and video lands: what happened / where it stands today / what it means for YOU, then one
   memorable closing line. Never an open loop (the owner's rule for every page, 2026-11-18).
5. **It is never silent.** The narrator (Arlo) speaks every reel and video; a take with no voice is never made
   into a video (the hub's NEVER_SILENT rule; a spent voice quota = wait and remake, late but with a voice).

## 2. Colour
- **Ink** `#05060A` (the canvas), ink-2 `#0B0D15` (panels), hairlines `rgba(255,255,255,.13)`, text `#F2F4F8`,
  muted `#8B91A5`. Grain 4–5 % (fights banding on Instagram's 8-bit SDR).
- **The spectrum** (the brand's light, never a fill of a whole area): `#7B61FF → #3D8BFF → #22D3EE → #3CFFB5 →
  #FFD166 → #FF5FA2`. Used for: the spectral edge, key words, the hero number, the highlighted bar, the caption
  caret, the progress line, the handle's dot.
- **The pillar accent** (one per video, its kicker chip and panel accents): repo mint `#3CFFB5`, model violet
  `#9B87FF`, news red `#FF4D5E`, tool cyan `#22D3EE`, trick amber `#FFD166`, behind pink `#FF5FA2`, explain blue
  `#3D8BFF`.
- **Content colour is free inside frames** (an official launch image, a product screenshot, an AI still keep their
  own colours, framed by a glass card with a spectral ring).
- **Meaning colours:** green `#3CFFB5` = good / up / yes, red `#FF6B7A` = old / down / no, amber = a twist.

## 3. Type
- **Persian: Estedad** (OFL, /home/studio/kits/fonts-bj): Black 900 for heads, ExtraBold 800 captions, Bold 700
  body. **Latin names: Geist** (OFL; Black for product names). **Code, sources, the handle: Geist Mono.**
- Captions are the **token stream**: the narration appears word by word like an AI answer streaming, the newest
  word white, the rest 80 %, key words in the spectrum, a spectral caret after the last word; at most two rows on
  screen (a long line pages); x 80–1000, baseline y 1440 on a reel (clear of Instagram's right rail and bottom UI).
- On-screen numbers in Persian digits (`fa()`); a Latin run (GPT-6.2, $8, 49.1%) stays Latin and isolated.
  No full stop, «،» or «؛» at the end of on-screen text. No word ever touches a frame edge or a panel border.

## 3.1 The handle and the counters (the owner, 2026-11-19; HARD)
- **The page's round profile logo beside every «behnamjalali.tech» handle** (stories, reels, Shorts, long videos,
  thumbnails, Telegram pictures, the end card): `COMMON/brand/logo_round.png` (the real Instagram profile picture,
  a clean circle with a thin spectral rim; `COMMON/tools/make_logo.py` makes it again only when the profile picture
  changes). Never a coloured dot. card.py, the stage (`brand`) and KIT/templates of Telegram draw it themselves.
- **A counter is «n از m» in Persian digits only, one right-to-left run**: never «۷ از 12» (mixed digits scramble
  their order). card.py's `badge` goes through `counter()` (any digits in, «۷ از ۱۲» out, refused if mixed); on the
  stage write `COUNTER(n, of)`, never a template string with numbers; `COMMON/tools/test_card.py` checks both.

## 4. Motion
- **The stage, not a new engine:** KIT/motion/stage.html is the API (PANEL, TERM, CODE, BARS, STAT, BIG, HEAD,
  CHIP, IMG, NET, STREAM, CAM, EDGE …). A scene is parameters and shots; a helper of your own lives in scenes.js.
- **Easing:** out-quint for arrivals (E.o5), in-out-cubic for camera, a spring only for something that lands
  (a chip, a check). Never linear except a counter's last digit.
- **The camera always breathes** (`CAM`: micro drift + a 4 % punch on a beat). One push per shot at most.
- **Transitions (the look's family, §6):** scan (a light bar wipes), zoom (push through a panel), slide (panels
  slide with motion blur and a spectral seam), iris (a spectral ring opens), dissolve (only into the call to
  action). Every transition 0.36–0.45 s.
- **Retention:** the hook is fully drawn at 0.0 s (title + hero; the voice starts ≤ 0.35 s); a pattern interrupt
  every 2–3.5 s (a shot, a `BEAT`: a bar lands, a counter stops, a chip, a punch-in); `reel.py --timeline` prints
  the longest stretch: ≤ 3.5 s. The question chip (`CONFIG.gap`) opens by a third and flips to the answer at the
  payoff. The spectral edge glows only three times: the hook, the payoff, the end card.
- **The edit's sound** (motion/sound.py): the page's own bed (glassy FM bells, a warm sub pulse, an airy pad),
  soft UI blips on the beats, low whooshes on the transitions, the boot chime on frame 0, the resolve chord on the
  end card. Never a hit or a boom. Mix −14 LUFS, voice −16, true peak < −1 dBTP, audio QC 0 clicks / 0 cuts / 0
  bursts on the voice AND the file's own audio.
  **Zero tolerance (the owner, 2026-11-18):** every voice file (the raw take, voice_raw, voice_final) passes 0/0/0;
  a flagged take is ALWAYS remade with a new speech.make, never judged a detector edge, never kept because the mix passes.

## 5. Pictures (AI stills are allowed only as pictures, never as text, never as video)
- **Never a video from Gemini, ChatGPT or any AI video model (owner rule).** All motion is Claude's code.
- **An official launch image** (the vendor's og:image or the image on its own announcement page) is the hero of
  any news or model video; label it «تصویر رسمی <vendor>».
- **AI stills** (substitute.call creative, kind image, player gpt AND player gemini, keep the better): concept art
  for explainers and behind-the-scenes (a 3D glass object, a data centre, a hand on a phone, abstract light),
  9:16 or 16:9, ALWAYS "no text, no letters, no numbers, no logos, no watermark", the page's palette (ink, one
  pillar light, a touch of spectrum). Read every picture; warped, wrong or with letters = ask again (≤ 2 more).
- **Screens of products**: draw them in code (a terminal, a chat, an editor, a repo card) rather than a fake
  screenshot; a real screenshot only of a public page, never with a person's data.
- No person's face except the owner's (his profile photo on the end card). People as silhouettes or hands only.

## 5.1 Covers and thumbnails are NOT LUMEN (the owner, 2026-11-18)
The reel covers and the YouTube thumbnails keep the page's own established cover family exactly (its posts before
the automation): cover/COVER_SYSTEM.md — the owner's navy background with blue light lines, a heavy white
IRANYekanX title with an electric-blue key word, one neon element on black. The videos are LUMEN; the covers are
the page's old family.

## 6. The look of the day (variety without chaos)
N = the day of the year (+3 for the evening reel, +5 for a breaking reel). `CONFIG.look`:
- `tr` = N % 5: 0 scan · 1 zoom · 2 slide · 3 iris · 4 scan with zoom on the payoff;
- `bg` = (N // 5) % 4: 0 grid floor · 1 aurora · 2 dot field · 3 grid with the pillar's light;
- `mood` (sound.py): 0 night lab · 1 bright launch · 2 deep focus · 3 breaking (only the breaking kit).
Shots may override `bg` (`aurora` for a reveal, `void` for code, `dots` for a list). Never the same look two days
running on the same slot; write the look in direction/CONTRACT.md.

## 6.1 Long videos hold to the last second (the owner, 2026-11-18)
«از فن‌هایی باید استفاده بکنی که تا ثانیه آخر مخاطب رو نگه داره»: the cold open at the climax with a question by 8 s,
an end-loop promised by 30 s, a cliffhanger at every chapter's end, re-hooks at 25/50/75 %, something new every 4–6 s
(nothing static over 6 s), a human at the centre, the visible chapter bar, the payoff in the last 60 s and an outro
≤ 15 s. The numbers and the gate: bjtech-longform/README.md «Retention» and `tools/long.py retention`.

## 7. Words (the narrator's script)
- Casual, warm, exact Persian with «تو»: «ساده، کاربردی و بدون حرف اضافه». No hype words without a number behind
  them («انقلابی»، «باورنکردنی» only when a number proves it). No «سلام دوستان», no intro: the first sentence IS
  the hook.
- Names as SPOKEN in Persian letters in voice.txt («کلود فِیبل پنج و دو», «جی‌پی‌تی شش و دو آسترا»); on screen the
  real Latin name (`CONFIG.caps`). Numbers spoken in words, shown in digits.
- 110–135 words for a reel (Arlo reads about 2.25 words a second; 45–60 s), one line per beat.
- **The ending (hard rule):** after the payoff, 2–3 short lines: where it stands today / what it means for you /
  one closing line (a takeaway, a full circle to the hook). Then the call to action line (the comment word).
- True facts only, every number from a source checked TODAY (the vendor's own page first); when sources disagree
  say the careful version. No politics, sanctions, legal matters, ways around a country's restrictions or filters,
  medical or financial advice, no fear-mongering, nothing about any government.
- The Telegram channel (brand/config.json `telegram`) is named in the caption and the DM, and on the end card;
  never as a voice ad.

## 8. QC (every reel; under 8 = redo; at least 2 still rounds)
Score each shot /10: the idea, the type, the clarity, the motion, the retention. Check letter by letter: no glued
words, nothing clipped, nothing under the top 250 px or in the bottom 380 px, nothing behind the right rail
(x > 980 between y 1000 and 1750). Then the timeline (longest ≤ 3.5 s), the sound (0/0/0), the contact sheet of
the FINAL file every 2 s (`reel.py --sheet`) read whole.
