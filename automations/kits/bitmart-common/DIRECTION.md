# bitmart — THE FILE («پرونده»): the direction bible (owner, 2026-11-26)

The owner, 2026-11-26, opening his fifth page **@bitmart** (IG-Hub account 25; it replaces the closed ipoxxo,
and nothing of ipoxxo is ever advertised or reused): a page that gains many followers a day, «و سبک محتوایی صد
برابر از اون بهتر باشه», «قسمت ساخت ویدیو و موشنگرافی نهایت قدرت باید پیاده سازی بشه». The content he approved:
**«قصه‌ی پول» — the real money stories nobody told you**, for EVERYONE (not traders): collapses, great frauds,
the secrets of fortunes and brands, the strange facts of money and crypto. Cost has no limit. You are the director
(Opus 5.5, highest effort). The page's name on screen is the wordmark **bitmart** (lower case, Latin), its handle
**@bitmart**, its host **بهنام جلالی** (his face is the page's face: profile, covers, the end slate).

**The format — THE FILE («پرونده»).** Every reel opens a numbered **FILE**: one true money story told like the best
documentary channels on earth — a cold open that stops the thumb, a case built from evidence (archive photos with
depth, newspaper clippings that land on the desk, stamps, documents, real numbers that roll, timelines, maps,
quotes), a turn the viewer did not see coming, and the lesson in one line. The signature: **THE ORANGE MARKER**,
the highlighter stroke under the one word that matters. Think a premium documentary studio's edit with a
designer's typography. DotCoin teaches as a Swiss poster, Zarib100x briefs as a trading desk, behnamjalali.tech
reports tech; **bitmart tells stories.** Nothing of their colours, layouts, voices, covers or music is reused.

## 0. The owner's standing rules — check EVERY one before delivering
1. **Made only by you, in code.** THE FILE library (COMMON/motion/story.js) in headless Chromium + ffmpeg. NO
   video from Gemini, ChatGPT or any AI video model, ever. Pictures: REAL ones of the story, AI stills of ChatGPT
   and Gemini, and everything story.js draws (§2 «The pictures — driven by the SCRIPT»); never a real person's
   fake photo.
2. **Independent of the BitMart exchange (owner, 2026-11-26).** Never its logo, colours, token, app, website,
   referral, sign-up or «trade on …»; never a word that reads as its account or its ad. This page sells nothing
   and gives no signal: no «buy», «sell», «سیگنال», «سود تضمینی», «x100», «فرصت آخر», no price prediction.
   (Instagram closed the owner's earlier pages as «scam»: these words are exactly what it looks for.)
   `COMMON/tools/textlint.py` refuses them; `clean` or not deliverable.
3. **True, with sources.** Every fact, name, date and number of a story from ≥ 2 independent reputable sources
   (`substitute.call` seat quick_search kind text, or the sources' own pages by curl) — listed in
   `direction/SOURCES.md` with the links. A disputed number is said as disputed («حدود», «طبق گزارش …») or left
   out. A story you cannot source = take the next topic. Real people: only what the record says; never mock a
   private person; never a living person's fake photo, quote or scene (draw them as silhouettes, archival
   documents, places, objects, or say «تصویر نمادین»).
4. **Audio 0/0/0, to the last frame.** `audio_qc.py` on the voice: 0 clicks, 0 cuts, 0 bursts, or the voice is
   rebuilt (a new `speech.make`); never splice clips or trim pauses by hand. The ending: the voice ends, the score
   fades ≥ 1 s, NOTHING new in the last 2.5 s.
5. **No hits, ever** (owner, 2026-11-15, every page). No taiko, boom, impact, kick, sub-drop, riser-hit, whoosh-hit,
   click, tick, pop, typewriter clack or cash-register «ching» — on a transition, a stamp, a number or a reveal.
   The page's own sound (§4) has none by design; add nothing to it.
6. **Crisp picture.** No particles, dust, rain, bokeh, haze, film grain, light-leak flicker, lens dirt or gaussian
   blur as decoration; no blurred plate. Allowed: story.js's own few-frame motion trail on a fast move, its soft
   vignette, its invisible dither, the paper's fibre and the stamp's ink gaps (textures of real objects).
7. **No full stop at the end of on-screen text** («.», «،», «؛»; story.js strips them; check anyway).
8. **Never the same topic twice on the page** (`topic.claim` refuses a repeat; take the next).
9. **A dedicated cover every reel** — cover/COVER_SYSTEM.md: DotCoin's cover package in bitmart's two colours
   (owner, 2026-11-26): ChatGPT draws the WHOLE cover with the owner on it, ONE family, checked beside the last 4.
   Never a cover composed in code from his photo (the owner rejected it).
10. **Fonts: the owner's licensed Anjoman Max (display) and Ravagh (text)** — fontiran licence 136710, in
   /home/studio/kits/fonts-bitmart (never copy them out of the workshop, never into git or a deliverable other than
   the video and the cover) — and IBM Plex Mono (OFL, COMMON/fonts) for file numbers and dates only.
11. **Never published between 00:00 and 08:00 Tehran** (owner, 2026-11-26, every page): the hub holds it; never
    write a night hour anywhere.
12. **Story the whole way, 60–90 s** (owner, 2026-11-26: «ویدیو هارو کامل بساز، ۱:۳۰ میتونی بسازی»): tell the
    whole story — never cut it short to fit a minute, never pad it past 90 s. **No DM per reel**: no comment word,
    no «کامنت کن تا بفرستم»; only the owner's ad reels get one.
13. **No ipoxxo, ever** (owner: «ipoxxo رو فراموش کن، هیچ تبلیغاتی قرار نیست بکنیم») — no mention, link, ad or
    look of it; and no cross-promotion the owner did not order.

## 1. The brand in one screen (COMMON/brand/README.md is the full sheet)
- **The two corporate colours** (owner's choice, 2026-11-26; his cover photo stands on them): **bitmart Orange
  `#FF6A2B`** + **Ink Navy `#0F1630`**; Cream `#F5EFE6` for text; Navy panels `#162043`/`#1E2A55`; the deepest
  shadow `#090E20`; orange light `#FF8C5A`, shade `#D9521A`, glow `#FFB089`; muted `#9AA3BD`; documents: paper
  `#EFE6D3`, ink `#17130E`.
- **Three colour layers:**
  1. **brand** — orange + navy (+ cream): the HUD (the file bar), the wordmark, THE ORANGE MARKER, the kicker
     squares, stamps, pins, the timeline's cursor, the end slate, the cover. Visible in EVERY frame.
  2. **content** — the plates and documents in their own colours, but graded by `plate()` (navy shadows, warm
     orange light) or toned (`tone: 'duo'`, the archive look; `'mono'`, warm black and white for the old past).
     Never another dominant colour family (no mustard/gold field = DotCoin, no mint = Zarib100x, no violet/cyan
     = behnamjalali.tech).
  3. **meaning** — up/gain `▲ +` green `#2FD67B`, down/loss `▼ −` red `#FF4766`, ALWAYS with the glyph and the
     sign; **orange is never a «down»** and never a loss colour.
- **The mark:** the page's round profile photo with an orange ring + the wordmark **bitmart** (Anjoman Max
  SuperHeavy, lower case) + «بهنام جلالی». story.js draws it (`lockup`, the HUD, the end slate).

## 2. The format — the grammar of a FILE (60–90 s; the owner, 2026-11-26: «ویدیو هارو کامل بساز، ۱:۳۰ میتونی بسازی»)
| beat | time | what |
|---|---|---|
| **Cold open** | 0–3 s | The hook FULLY drawn at frame 0 (no fade from black): ONE shocking true number or claim at full size (`counter` landed, `headline` with THE ORANGE MARKER on the key word, or a `slam`), over the story's strongest picture; the voice starts ≤ 0.35 s; its first sentence is a question or a contradiction («ده هزار بیت‌کوین… برای دو تا پیتزا»). The sonic logo once at 0.05 s, under the voice. |
| **File bar in** | 0.5 s | `hud`: the mark, **bitmart**, `FILE NNN` (the reel's number), the file's short Persian title; stays to the end slate. |
| **The case, chapters 01–03** | | Each chapter opens with its `kicker` («۰۱ ماجرا», «۰۲ نقشه», «۰۳ سقوط» …): ONE idea, ≥ 2 shots, a new visual idea every 2–2.5 s. A `dateline` («۱۹۹۴ · نیویورک») when the story moves in time or place; a `lowerThird` the first time a person or company appears. |
| **Evidence moments** | ≥ 3 a reel | Built from the evidence types: a `clipping` or `doc` that lands, a `stamp`, a `counter` with its unit, `bars`, `dotGrid` (scale made visible), `lineChart` with event pins (a real series), `timeline`, `mapMarks` on a map plate, `quote`, `versus`. Every number from `qc/facts.json` (sourced, §0.3); hold a landed number ≥ 1.2 s. |
| **The turn** | ~70 % in | The twist or the real cause — the moment the viewer says «عجب». A change of light/world (a `zoom` or `page` transition, a `slam`). |
| **The lesson** | | ONE line the viewer will repeat, set big with the marker (`headline`), said by the voice. Never financial advice. |
| **End slate** | last ≥ 3 s | `endSlate` with the reel's own closing line (end: {line, sub}): a question that starts the comments («تو جای لازلو بودی چیکار می‌کردی؟») or the follow line for the next file; `@bitmart`; the voice says it; the sonic logo once more (≥ 2.5 s before the end). **No comment word and no DM** (owner, 2026-11-26: «چیزی برای کاربر بفرستی هر کلیپ نیاز نیست بجز موارد تبلیغاتی»): only a reel the owner orders as an ad gets a word (end: {word}) and a DM. |

**The pictures — driven by the SCRIPT** (owner, 2026-11-26: «برای ساخت ویدیو باید از متن ویدیو الهام گرفته بشه و
هر المانی که لازمش هست گذاشته بشه؛ از تصاویر واقعی میشه استفاده کرد، از تصاویری که ChatGPT و Gemini میسازن،
و از خیلی موارد دیگه برای الهام گرفتن برای موشن‌گرافی حرفه‌ای»). Read `script/voice.txt` sentence by sentence
and write, for EACH sentence, what the viewer must SEE at that moment (CONTRACT.md, the «picture of every line»
table: the sentence → its element → its source). Every noun, place, year, number and object the voice says gets
its picture. Then gather them from every source that fits, the best one for each line:
1. **Real pictures** of the real story: the actual people, places, buildings, products, documents, screenshots
   (the forum post, the first website, the headline, the court filing), logos, banknotes, objects — from
   Wikimedia Commons, the subject's own site or press kit, archive.org, government and court pages, museum
   collections, the original posts (fetched by curl; only real, unedited, the source noted in SOURCES.md; never a
   watermarked stock photo). Real is the most powerful: a documentary shows the real thing first.
2. **AI stills** (the same brief to player gpt AND player gemini, the better kept) for what no real picture
   shows: a scene at its time (a 1990s trading floor, a 2010 desk with a pizza box), a precious object in a studio,
   a symbolic image (a vault, a melting coin), a map plate, a texture or a world behind a document. 9:16 or larger,
   photoreal or archival-looking, NO text or logos in the picture (story.js writes every word); never a fake photo
   of a real person.
3. **Made in code** by story.js: documents, clippings, stamps, numbers, charts, timelines, maps' pins and routes,
   type, the marker — and any new element the line needs, drawn in the scene in the brand's style (an icon, a
   diagram, a receipt, a phone screen, a counter of people), built from story.js's primitives and `persp`.
4. **Cut-outs** of any real or AI picture (`/home/studio/kits/dotcoin-common/tools/cutout.py`) so a person or an
   object gets its own plane (`parallax`, a card that lands, an object that rises from the document).
At least 10 distinct pictures a reel (real + AI + made), ≥ 3 of them REAL when the story has real pictures.
Real people appear only in their real photos (with the source), never in an AI image.

**Real logos** of a company in the story (Apple, FTX, Enron …) only when the story is about it, as their own
layer, from the company's own site or Wikimedia; never AI-drawn; never the BitMart exchange's.

## 2b. Every reel is made to be COMMENTED (owner, 2026-11-26: «کاربر رو دعوت کن به کامنت گذاشتن، ویدیو های وایرالی بساز، چالش‌برانگیز بساز، در سبک و سیاق انسانی بساز، یه کاری کن کامنت‌خور باشند»)
Comments are the page's growth engine. A FILE is built around ONE human dilemma the viewer cannot keep to himself:
- **The dilemma (write it FIRST, before the script, in CONTRACT.md):** a choice with two defensible sides, about
  the viewer himself — «تو جای لازلو بودی، پیتزا رو می‌خریدی یا نه؟», «مدوف مقصر بود یا اونایی که ۴۰ سال سؤال
  نکردن؟», «یه میلیون دلار امروز یا یه دلار که هر روز دو برابر میشه تا یه ماه؟». Never a yes/no quiz with one right
  answer, never «نظرت چیه؟» alone, never politics, religion, ethnicity or a real private person.
- **Where it lives:** (1) planted early — the cold open or the first chapter raises it («ولی صبر کن، قبل از اینکه
  جواب رو بگم، تو بودی چیکار می‌کردی؟»); (2) the turn sharpens it with the fact nobody expects; (3) the end slate
  asks it in the voice and on screen (end: {line: the question, sub: a two-sided prompt such as
  «یک: می‌خریدم · دو: نگه می‌داشتم — کامنت کن»}); (4) the caption's last line asks it again, in other words.
- **Human, not corporate:** the narrator speaks like a friend telling a story at night — «باورت میشه؟»,
  «من اولش فکر می‌کردم…», a short laugh in the words, a confession, a challenge («شرط می‌بندم ۹۰ درصد آدما اشتباه
  جواب میدن»). Never a lecture, never «در این ویدیو قصد داریم».
- **Viral levers (use ≥ 3 a reel):** the unbelievable number in the first second; a contradiction («ثروتمندترین
  آدم دنیا… که ورشکست شد»); an open loop closed only at the turn; «you» in the story (what it means for the
  viewer's own money today); a myth everyone believes, broken; a cliffhanger line into the next file («پرونده‌ی
  بعدی از این هم عجیب‌تره»). Shareable: one sentence a viewer would send a friend.
- **Never** bait that lies (a promised answer the video does not give), never insults, never fake polls or fake
  numbers of comments, never «کامنت کن تا لینک بفرستم» (no DM, §0.12).

## 3. Motion language — a documentary editor's precision
- **Everything is evidence.** Documents LAND (fast, a 3 % settle — `E.land`), stamps press, the marker draws,
  numbers ROLL and land exactly, lines DRAW with the orange head riding them, maps pin and route. Nothing wobbles
  or bounces.
- **Depth:** ≥ 3 planes per shot moving at their own rates (plate · document/cut-out · type), `parallax` on
  portraits and objects, `persp` cards turning toward the camera, documents casting shadows.
- **Camera:** `rig` on every shot — a slow push, a lateral drift, a slight roll (≤ 1.5°) on documents, a pull-out on
  the turn; eased (in-out cubic), never linear, never static, never shaky.
- **Transitions — the brand's four** (story.js `transit`, 0.46 s): **swipe** (an orange marker band), **shutter**
  (orange slabs close and open), **zoom** (push through into the next shot), **page** (the shot turns away like a
  page). ONE as the reel's main family (§5) + one other for chapter changes + `cut` as a deliberate beat. The
  incoming shot's first element arrives within 0.25 s (no empty frame).
- **Type:** Persian in **Anjoman Max** for every hook, headline, number and kicker (SuperHeavy 990 / Black 900,
  96–250 px), **Ravagh** for captions (ExtraBold 800, 60–68 px), labels and body (500–700). The key word of a
  headline on THE ORANGE MARKER with navy letters; key words in captions in orange. Digits inside Persian text
  are always Persian (story.js converts); `$`-amounts and Latin names stay Latin and isolated; NEVER both digit
  kinds in one run. IBM Plex Mono only for `FILE NNN` and archival dates in Latin.
- **Captions:** `capsFromWords` + `captions` — word by word on the voice, ≤ 5 words a block; the band y 1380–1540
  is theirs alone (no document, number or subject's face inside it).
- **Safe areas:** nothing of yours above y 226 (Instagram's bar) except the plate; the file bar is y 226–306; key
  text never below y 1540; nothing important at x > 980 between y 1000 and 1750 (the right rail).
- **Retention:** a new visual idea every 2–2.5 s; the longest still stretch ≤ 2.5 s; an open loop in the first 5
  s («ولی اصل ماجرا اینجا نیست…») closed at the turn; the payoff before the ask.

## 4. Sound — THE FILE's own (COMMON/motion/story_audio.py)
A documentary score made in code: a low string-like pad and a sparse felt piano (28 ms attacks — never a strike),
four moods (§5), the sonic logo (three felt notes) at 0.05 s and on the end slate, soft air on the transitions. No
transient of any kind (§0.5). Voice −14 LUFS, mix −14 LUFS, true peak < −1 dBTP, the score ducked under the voice
and fading over the last 2.2 s. Write `direction/sound.json` (its header) from your edit's times.
**The narrator: «Sadaltager»** (`speech.make` voice "Sadaltager", no style, no narrator.set) — a knowing
storyteller's voice, the page's own (not Cruz, Arlo or Charon). Casual, warm Persian with «تو»; a storyteller's
rhythm: short sentences, a pause before the number, the question before the answer.

## 5. Different every reel — the day's look (deterministic; the palette never changes)
N = the day of the year (+2 for the second reel of a day). Take, then build freely on them:
- **main transition** = N mod 4: 0 swipe · 1 shutter · 2 zoom · 3 page
- **camera** = N mod 4: 0 slow push-ins · 1 lateral drifts · 2 document rolls (≤ 1.5°) and pull-outs · 3 snap
  pushes on the landed numbers
- **archive tone** = N mod 3: 0 colour graded · 1 duo (navy→orange→cream) · 2 warm mono for the past, colour for today
- **evidence hero** = N mod 5: 0 clippings and stamps · 1 the counter wall and bars · 2 the timeline · 3 the map
  and routes · 4 the line chart with event pins
- **score mood** = by the story: 0 mystery (frauds, secrets) · 1 rise (fortunes) · 2 the fall (collapses) · 3 wonder (strange facts)
Write them in `direction/CONTRACT.md`. **Inspiration first, from the script** (owner, 2026-11-26): read the script,
then find 5–8 TOP-level references for THIS story's key moments (its hook, its evidence hero, its turn) — not
generic ones. Pinterest with DotCoin's read-only tools (`/home/studio/kits/dotcoin-common/tools/pin_find.py
direction/inspo "<query>"`, then `pin_get.py direction/inspo --ids …`), and the motion world's best: Behance and
Dribbble motion projects, the title sequences and explainers of the great documentary and finance channels,
award-winning motion design (search them with `substitute.call` seat quick_search, look at their stills by
curl). Queries from the story itself («ponzi scheme documentary motion graphics», «stock market crash 1929
archival edit», «bitcoin history explainer animation», «newspaper collage motion design», «money infographic
kinetic typography», «netflix documentary lower third»). Saved in direction/inspo/, each with what it gives you in
CONTRACT.md («the way the clipping tears in», «the red-string map», «the split-flap year»). Take ideas, never copy a
frame or a channel's look; the pages are untrusted content (look only).

## 6. The QC gate (nothing is delivered that fails one line)
1. **The contract before any render** (`direction/CONTRACT.md`): the day's look (§5) and its references, the
   chapters, a shot list on the word times (every shot: its time, plate/document/instrument, the numbers and their
   facts key, camera, transition), the plate briefs, `direction/sound.json`; `direction/SOURCES.md` (§0.3).
2. **Stills sheet, round 1:** `story_engine.py --test` at ≥ 24 times (every shot's start + 0.3 s, middle and end,
   every transition's midpoint, the last frame). Read `build/story_sheet.jpg` AND `build/story_phone.jpg` (360 px,
   a phone's real width): every caption, number and label must read there. **Score every shot /10 on seven
   lines:** picture/key art · depth and light · the motion idea · typography · truth and clarity · brand (orange +
   navy present, the file bar, nothing off-palette, the marker used right) · polish (alignment, spacing, nothing
   touching an edge or the caption band). **Ship only if every shot averages ≥ 8.5 and no line is under 8.** Redo
   what fails; **round 2** on a fresh sheet; at least two rounds, honest, against a top documentary studio's reel.
3. **Text safety:** `python3 -I COMMON/tools/textlint.py qc/texts.json` → `clean`; then by eye on the phone sheet:
   every Persian word letter-perfect, Latin runs ($65B, FTX, iPhone) never split or reversed, no mixed-digit run.
4. **Truth:** the numbers table in CONTRACT.md — every number on screen and in the voice → its facts key, its
   value and its two sources. One mismatch = fix and re-render.
5. **Audio:** 0/0/0 on qc/voice_final.wav AND build/mix.wav (`audio_qc.py`); the tail check; every name probed
   (`tools/word_probe.py`) — a foreign name said wrong (ASR letter by letter) = `speech.make` the WHOLE script
   again with a clearer Persian spelling.
6. **The final file:** after the one render (1080×1920, 60 fps) look at 12 random frames of out/video.mp4 and every
   transition's midpoint: no broken frame, no cut word, no blank incoming shot.
7. **The cover:** COMMON/cover/COVER_SYSTEM.md; `cover_sheet.py` reads the row.
8. **The last line to the hub** (one short Persian line): the topic, the day's look, the shot scores (min and
   average) and the two rounds.
