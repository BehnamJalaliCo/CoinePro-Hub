# @behnamjalali.tech — the day's 12 stories (owner 2026-11-18: «۱۰ تا ۱۵ استوری در روز: آموزش، معرفی، تکنولوژی، خبرهای داغ»)

Flow `bjtech_stories`: built at 05:00 Tehran the same day, twelve picture stories, each at its hour (your order
lists them). Every story is a **LUMEN card set in code** (COMMON/tools/card.py, type `story`), so every Persian
letter is exact; the pictures inside the cards come from the vendors' official pages, ChatGPT and Gemini.

You are the day's session on the holding's workshop, Opus 5.5 at extra-high effort. Work alone (never
`order.ask`, never wait, NEVER `workshop.run`); keep `NOTES.md` current; the hub schedules every story at its hour
when out/ is complete and closes the session.

KIT = /home/studio/kits/bjtech-stories. COMMON = /home/studio/kits/bjtech-common. REELS =
/home/studio/kits/bjtech-reels (its topics.md, tools/topic.py and sources.md). PY = the render venv
(/home/studio/kits/prochart-reels/venv-render/bin/python); export
PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright.

## FIRST read COMMON/DIRECTION.md (§2 colour, §3 type, §5 pictures, §7 words)

## The day's plan (12 cards, in the order of the hours in your order)
| # | what | from |
|---|---|---|
| 1 | **خبر صبح**: the most important AI / tech news of the last night | REELS/sources.md (official feeds), checked on the vendor's page |
| 2 | **ترفند روز** (layout list: 3 steps) | `topic.py next --lane trick` |
| 3 | **ابزار روز** (hero: the tool's own picture) | `--lane tool` |
| 4 | **مدل در یک نگاه** (latin name, 3 lines: best for, price, context) | `--lane model`, re-checked on the vendor's pricing page |
| 5 | **teaser of reel 1** («ساعت ۱۳:۳۰ …», no spoiler of the payoff) | `topic.py day today` (reel 1's row once its session marked it; else its kind) |
| 6 | **خبر دوم** (another real news item of the last 24 h) | sources.md |
| 7 | **ساده بگم**: one concept in 3 short lines | `--lane explain` |
| 8 | **ریپوی روز** (hero: the repo's social preview; stars today) | `--lane repo` |
| 9 | **ساده بگم ۲**: a second concept in 3 short lines (⟨2026-11-21⟩ «پشت صحنه» retired: COMMON/DIRECTION.md §0) | `--lane explain` |
| 10 | **عدد روز** (layout stat: one striking, sourced number) | today's news or a checked fact |
| 11 | **teaser of reel 2** (tonight's news, 22:00) | today's top news (not the one of card 1 if reel 2 will cover it) |
| 12 | **جمع‌بندی امروز** (layout list: today's 3 things + the Telegram line) | cards 1–11 |
More hours in the order than 12: add «ساده بگم» / «ترفند» cards; fewer: drop from the middle. A breaking story
of the same news already out today (your order's no-repeat list): take the next news.

Every bank topic you use: `python3 -I REELS/tools/topic.py mark <#> --slot story --publish "<the order's day>"`
(a topic used by a reel is never a story the same week, and the reverse: `topic.py find` first).

## TYPE GATE (2026-11-27, every page — /home/studio/kits/fa-type/README.md)
DotCoin's stories of 11-27 went out with figures a SYSTEM font drew (zeros as squares, «٬» as «’»):
an improvised renderer named a font it never loaded. From now on COMMON/tools/card.py gates every card.
- Text on a picture comes ONLY from the kit's own tools; they run the type gate (Chrome's report of
  the font of every glyph: a system-font fallback, a face that did not load, text out of its box or
  chip fails) and a failing picture is NOT written (exit 2): fix the text and run again. Never your
  own HTML/Pillow text, never a font or weight the tools do not load, never a work-around.
- Signs the page's fonts lack are drawn as shapes by the tools (▲ ▼ ■ ← → · ✓: `fatype.symbols`, the
  engines' `tri()`); do not type them into Persian text yourself.
- Figures: Persian digits where the page writes Persian digits; up to 4 digits no separator, 5+ «٬»;
  decimals «/» («۲/۱»: the Arabic decimal mark reads like «ر» in AnjomanMax and Estedad); never
  «’» or «'» in a figure. Check strings: `VENV/bin/python -I /home/studio/kits/fa-type/tools/type_gate.py --json spec.json`.
- Read every picture at full size for the figures (crop if small) before delivery.

## Step by step
1. `mkdir -p in assets cards out qc direction`. Topics and facts for all 12 (open every source; numbers checked
   today; a repo's stars: `https://api.github.com/repos/<o>/<r>`). One line each in NOTES.md with its link.
2. **Pictures, all at once, then end the turn** (`order.progress` «تصویرها در راه است»):
   - the official ones yourself: a news item's / model's launch image (the announcement page's `og:image`), a
     repo's social preview, a tool's hero → `assets/`;
   - the rest (at least 5): ONE `substitute.call` seat creative, kind image, player **gpt**, `images: <n>` (one
     chat, n separate pictures, one brief each: DIRECTION §5, 9:16, ink-dark with one light in the card's pillar
     colour, "no text, no letters, no numbers, no logos, no watermark"), and the same briefs once to player
     **gemini**; keep the better of each pair.
3. **The cards:** `direction/cards.json` = a list of 12 specs (COMMON/tools/card.py's header; `name`:
   `story_1` … `story_12`; `badge` «۱ از ۱۲»; `pillar` per card; `kicker` its label from the table; a hero or a
   stat on at least 9 of 12; `source` on every news, model, repo and number card; the day's reply word on cards
   1, 4, 8 and 12 with a `cta` line). `PY -I COMMON/tools/card.py --many direction/cards.json cards` (every line
   must say `ok`; `overflow` = shorten) → `PY -I COMMON/tools/card.py --sheet cards qc/sheet.jpg` → read the sheet
   AND each card at full size: every letter, no word under the top 250 px or the bottom 340 px, no two cards that
   look alike in a row. Under 8/10 = redo. Then `cp cards/story_N.jpg out/story_N.jpg`.
4. **The reply word:** a fresh Persian word for today (your order lists the words already taken; never one of
   them), short and tied to the day («ابزار»، «ترفند»، «لینکها» …). `out/comment.txt`:
   ```
   keyword: <today's word>
   reply: <a warm first line>
   reply: <every resource of today's cards: one short line each, NAMED, never its URL; at most 6>
   reply: <«هر روز خبرها و ابزارهای هوش مصنوعی رو توی کانال تلگرامم می‌ذارم 👇»>
   button: <the most useful resource, ≤ 20 characters> | <its official https URL>
   button: <the second, optional> | <its official https URL>
   button: کانال تلگرام | <COMMON/brand/config.json telegram>
   ```
   **No link in a `reply:` line, ever (HARD):** Meta refuses this page's DM when its text holds a link
   (508/2534122, 2026-11-18). Links are `button:` lines only, at most three, Telegram always last; the reply
   ≤ 600 characters.
5. `out/topic.txt`: line 1 «استوری‌های <day>: <the 3 main subjects>». **Deliver:** out/ holds ONLY story_1.jpg …
   story_N.jpg (1080×1920, in the order of the hours), comment.txt, topic.txt. `order.progress` done: one Persian
   line — the 12 subjects in a few words, the word, the score.
