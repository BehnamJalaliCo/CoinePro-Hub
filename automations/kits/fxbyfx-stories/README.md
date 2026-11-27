# FXbyFX (@fxbyfx) — the day's 20 picture stories. YOU = DIRECTOR + EDITOR (Claude); HYDROGEN = BUILDER.
(owner 2026-11-28: «روزانه ۲۰ تا استوری»، «سطح کیفیت جهانی»، content by the hub's Claude, building only by Hydrogen)

Your job: research and WRITE the day's 20 stories' content (every headline, number, chart's data and source —
the series below), put it in build/BRIEF.md for Hydrogen with the design rules below, run
`/home/studio/bin/agy-build build build/BRIEF.md --detach` + `--wait build` until done, then review
build/qc/sheet.jpg and EVERY build/out/story_NN.jpg yourself (spelling, numbers, layout, brand, Persian typography perfect (fa-type gate)); anything below 9/10 → build/notes.md → `agy-build build build/notes.md --resume <id> --detach`
(≤ 3 rounds). Then copy build/out/story_01.jpg … story_20.jpg → out/story_1.jpg … out/story_20.jpg, write
out/comment.txt and out/topic.txt, deliver. Never draw the stories yourself. Never `order.ask`/`workshop.run`.
The rules and series below are what you put in the builder's brief (adapt paths to your folder).


KIT = /home/studio/kits/fxbyfx-stories, COMMON =
/home/studio/kits/fxbyfx-common (read COMMON/DIRECTION.md §0–§1 first: ENGLISH ONLY, the brand, the
never-list). PY = /home/studio/kits/prochart-reels/venv-render/bin/python;
export PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.

## The day: 20 stories, 1080×1920, posted by the hub at the 20 hours of your order
Four series of five, in this order (each story must also make sense alone):
1. **story_1–5 · MARKET PULSE** (morning): today's real numbers (BTC, ETH, gold, DXY, S&P 500 futures,
   EUR/USD; % change with ▲/▼ in the meaning colours), the day's calendar (CPI/Fed/NFP… with times in
   UTC), one "what to watch" line. Real data only (`search_web`/`read_url_content`, sources in
   qc/facts.md), "as of HH:MM UTC". No prediction.
2. **story_6–10 · ONE LESSON** in five slides: a worked example with real numbers (position sizing,
   R:R, liquidation price, compounding, drawdown recovery…), slide 10 = the checklist summary.
3. **story_11–15 · TRADER MIND**: a mistake → why it happens → the fix → a rule card → a question
   to the viewer ("Which one is you? Reply 1, 2 or 3").
4. **story_16–20 · DEEP DIVE / CASE**: a famous market event or a myth vs data, ending with the DM CTA.
Every story has the bottom bar «DM "<WORD>" for the full cheat sheet» (the day's word, fresh, uppercase,
tied to the lesson; never one already used — your order lists them) and the small ONEOXXO mark.

## Design
- Premium finance-media look (think Bloomberg × Apple keynote × a top trading creator): bold type,
  big numbers in JetBrains Mono, cobalt/ink/ice brand layer, full-colour content visuals, lots of
  contrast, one idea per story, ≤ 25 words, readable in 2 seconds. Each series has its own layout
  system, consistent inside the series.
- Visuals: your `generate_image` (no text inside the picture: you set all text yourself), clean
  charts you draw from real data, icons you draw. No other exchange's name/logo, no faces except the
  owner's.
- Build each story as HTML (fonts from /home/studio/kits/fonts-en and /home/studio/kits/fonts-pro),
  screenshot with Playwright at 1080×1920 → out/story_N.jpg (JPEG q 92, sRGB). Safe zone: nothing
  important above y 250 or below y 1650 except the bar.
- QC: a contact sheet of all 20 → qc/sheet.jpg; view it; score each /10 in qc/scores.md; redo any < 9.
  Check: no Persian/Arabic letters, spelling, every number in qc/facts.md.

## Files
- out/story_1.jpg … out/story_20.jpg
- out/comment.txt (the DM for the day's word):
  ```
  keyword: <WORD>
  reply: <hello tied to the lesson>
  reply: <the cheat sheet in 4–6 numbered lines with the real numbers>
  reply: <«Follow @oneoxxo — one sharp trading lesson every day»>
  ```
  ≤ 900 characters, no hashtags, no links.
- out/topic.txt: one line, the lesson's title + "style: <look>".
Deliver only these. Last `order.progress`: one line (the lesson, the look, stories redone).

## FXbyFX differences (override everything above that conflicts)
- PERSIAN ONLY (COMMON/DIRECTION.md §0 typography rules: Persian digits, rtl, <bdi> on pair names, ZWNJ, no
  line-end full stops); the fa-type gate (/home/studio/kits/fa-type) on every story.
- Brand: Dark #101713 ground, Lime #D4E532 accents, White #F5F5F5, Gray #858585; mark «FX×FX».
- Series: ۱–۵ نبض بازار فارکس (EUR/USD, XAU/USD, DXY, USD/JPY, GBP/USD…, تقویم اقتصادی به وقت تهران)،
  ۶–۱۰ یک درس مهارتی با مثال عددی، ۱۱–۱۵ ذهن معامله‌گر، ۱۶–۲۰ پرونده‌ی یک رویداد مشهور فارکس.
- The bar «کلمه‌ی «…» رو دایرکت کن»; comment.txt in Persian; no broker ever; no signals.
