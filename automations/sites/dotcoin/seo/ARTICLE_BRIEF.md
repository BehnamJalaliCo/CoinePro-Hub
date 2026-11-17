# The article brief: one reel → one lesson on dotcoin.me

The hub's daily automation follows this to turn the day's DotCoin reel into a lesson at
`/learn/<slug>/`. It extends the builder's `content/FORMAT.md` (the front matter and Markdown
body that `build.py` reads); build.py reads `seo_title`, `answer`, `sources` and `updated` since phase 2.
Keyword research: KEYWORDS.md. Page rules: PAGE_PLAN.md §3.3. Technical rules: TECHNICAL.md.

## 1. Inputs

- the reel's idea (`ideas.json`: id, pillar, title, angle) or the news story;
- `script/voice.txt` (what Arlo said) and the caption: the facts are already checked there;
- the reel URL once published, the cover, the comment word;
- PAGE_PLAN.md §4/§5 for this idea (slug, primary query, title), if the idea is listed;
- the list of existing lessons and glossary slugs (for links).

⟨2026-11-17, the owner⟩ **Every reel gets its article, written by the same session from the same
script, topic and facts, expanded.** A news reel («اطلاع‌رسانی») gets a news article (§10). A reel
whose lesson already exists by hand (content/articles: the idea's PAGE_PLAN slug is live) writes
`out/article.md` as `---\nattach: <slug>\n---` only: the hub puts the reel into that lesson.

## 2. Before writing: the keyword step

1. Take the primary query from PAGE_PLAN.md. Not listed: run Google suggest
   (`suggestqueries.google.com/complete/search?client=firefox&hl=fa&gl=ir&q=<term>`) for the
   term, «<term> چیست», «<term> یعنی چه», «آیا <term>», «فرق <term>».
2. Primary = the most specific «… چیست» form that suggest shows for the term. Secondary = 2–5
   other completions with the same intent. Questions for the FAQ = completions phrased as
   questions.
3. Drop completions about price, prediction, «امروز», religion, politics, bypassing rules.
4. Check the slug and the primary query do not belong to another lesson (PAGE_PLAN §5,
   cannibalisation pairs). If they do, pick the narrower angle or make this lesson a section of
   the other one.

## 3. Front matter

```
---
title: <H1: the full question in written Persian, e.g. «کیف پول سرد چیست و چه فرقی با کیف پول گرم دارد؟»>
seo_title: <the <title> without the suffix, ≤ 60 chars; build.py adds « | دات‌کوین» (11 chars) only when the total stays ≤ 60, so aim for ≤ 49>
slug: <§6>
pillar: basics | security | exchange | market | defi | myths | terms
idea: <ideas.json id>
date: <YYYY-MM-DD publish day, Tehran time>
updated: <YYYY-MM-DD; equals date until a real content change, §8>
keyword: <the primary query, as people type it; build.py ignores it>
keywords: <2-5 secondary queries, comma-separated; for the automation's own checks, build.py ignores it>
en: <ONE OR TWO GIANT ENGLISH WORDS>
motif: chain | vault | halving | peg | generic
description: <meta description, 120-155 chars, §4.3>
lead: <1-2 sentences under the H1>
answer: <the «پاسخ کوتاه» box, 40-60 words, §4.2>
reel: <Instagram reel URL>
sources:
- <label> | <https URL of a primary source>   (1-3 lines)
summary:
- <3-5 one-line takeaways>
steps:
- <short title> | <one sentence>   (exactly 5)
---
```

## 4. The text

### 4.1 Structure (in this order)

1. **H1** (`title`): contains the primary query's words in standard spelling.
2. **lead**: 1–2 sentences: whom it helps and what they will understand.
3. **«پاسخ کوتاه» box** (`answer`): the definition or answer in 40–60 words, complete on its
   own, starting with the term («کیف پول سرد کیف پولی است که …»). This is what Google's
   featured snippet and AI answers quote.
4. **byline** (built by the template): «نوشته‌ی بهنام جلالی» → `/about/` · «انتشار: <Jalali>»
   · «بازبینی: <Jalali>» when `updated` ≠ `date` · reading time.
5. **reel block** (built by the template): the cover as a poster image, a play mark and a plain
   link «این درس را در اینستاگرام ببین» → `reel`. Never Instagram's embed script.
6. **Body: 4–7 H2 sections.** The default arc, adapted to the topic:
   - `<term> چیست؟` / what it is (the everyday example from the reel goes here)
   - `<term> چطور کار می‌کند؟` (H3s for the parts, at most 4)
   - `چرا مهم است؟` / what it changes for the reader
   - a comparison (a real `<table>` when two things are compared: سرد/گرم، مارکت/لیمیت)
   - `اشتباه‌های رایج` (security, exchange and market pillars)
   - the link to the next step («قدم بعدی: …»)
   Each H2 is a question or a plain noun phrase, ≤ 60 chars, with a secondary query in at least
   one of them.
7. **«خلاصه در ۵ قدم»** (`steps`, rendered by the template).
8. **H2 `پرسش‌های پرتکرار`**: 3–6 H3 questions from §2 (written as people ask, ending in «؟»),
   each answered in 40–80 words, self-contained (no «همان‌طور که گفتیم»).
9. **«منابع»**: 1–3 primary sources (the protocol's own docs, the whitepaper, the issuer's page,
   the exchange's official page). Not competitors' blogs, not Wikipedia alone.
10. **«درس‌های مرتبط»** (template, same pillar first).

### 4.2 Length and depth

- **1,000–1,800 words** in total (FAQ included). P1 topics at the upper end; P3 topics 700–1,000.
  Competitors run 4,000–10,000 words; we win on clarity and on answering every sub-question
  from §2, not on size. No filler, no history lessons the reader did not ask for.
- One idea per lesson. A second idea that needs more than one paragraph is a link to its own
  lesson (or a line in the refresh queue).

### 4.3 Keyword use

- Primary query (standard spelling): in `seo_title`, H1, the answer box, the first 100 words,
  one H2, the meta description, the first image's alt if it describes the image truthfully.
- Secondary queries: in H2s and FAQ questions, once each. The loanword form (استاپ لاس، لوریج،
  مارکت کپ) leads when it is the stronger query; the Persian word appears in the first paragraph.
- Spelling variants («بلاک چین», «بلاکچین»): not in lessons; they live in the glossary line
  (KEYWORDS.md, spelling policy).
- Never: keyword lists, repeated phrases for density, hidden text, a question in the FAQ that
  the page does not really answer.
- **meta description:** 120–155 chars, says what the reader gets, includes the primary query
  and 1–2 secondary ideas, no «در این مقاله» opener, no clickbait, no prices.

### 4.4 Voice and typography

- Plain written Persian, friendly «تو» like the reels, but written forms («چیست», «می‌خواهی»),
  not spoken spelling («چیه», «میخوای»), except inside a FAQ question taken verbatim from
  suggest («… یعنی چی؟» is allowed there).
- Educational: no hype, no price numbers, no predictions, no signals, no disclaimers, no
  politics. Every fact true and checkable in «منابع».
- Persian digits in prose; Latin digits only in tickers and network names (TRC20, BEP20).
- ZWNJ and ی/ک normalised (TECHNICAL.md §7). English terms once, in parentheses, at first use:
  «حد ضرر (Stop Loss)».

## 5. Internal links

- **3–8 contextual links per lesson**, in the body text, not only in the footer blocks:
  - the **first** mention of each glossary term → `/glossary/#<term-slug>` (at most 4 per
    lesson; never the same term twice);
  - 1–3 links to other lessons where the reader needs the background or the next step;
  - pillars `exchange` and `market`: one contextual link to `/exchanges/` or an exchange page
    where the text talks about doing it on an exchange. Never the `/go/` referral link inside a
    lesson; referral buttons live on `/exchanges/*` only.
- **Anchor text** = the target's topic in natural words («کیف پول سرد», «شبکه‌ی TRC20»); never
  «اینجا», «کلیک کنید», never the full title, never the same anchor for two different targets.
- **Link format:** the canonical form only: `/learn/cold-wallet/` (with the slash), no
  `index.html`, no domain for internal links, no `?` parameters.
- **Related lessons:** build.py picks 3 (same pillar first); the beginner path lives in `content/site.json` → `path`.
- **Back-links (the refresh job, §8):** after publishing, find the 2 most relevant older lessons
  that mention the new topic and link their first mention to the new lesson; add the term's
  «درس کامل» link in the glossary.
- Links only to lessons that exist (the build fails on a broken internal link, CHECKLIST §5).

## 6. Slug rules

- English, lowercase ASCII `a-z0-9`, words joined by `-`, 1–4 words, the topic noun:
  `cold-wallet`, `usdt-networks`, `bitcoin-halving`. No `what-is-`, no dates, no stop words, no
  Persian (a Persian slug turns into a 100-character `%D8…` string when shared in a DM).
- Unique across `/learn/`; not one of the reserved words (PAGE_PLAN §1).
- Use PAGE_PLAN §4/§5's slug when the idea is listed.
- **Never change a published slug.** If it must change: add `/learn/<old>/ /learn/<new>/ 301`
  to `_redirects` in the same commit, update every internal link, keep the redirect forever.

## 7. Images and alt text

- **Files:** English kebab-case names that describe the image (`cold-wallet-vs-hot-wallet.webp`),
  WebP or AVIF for the page, JPG for `og:image`. Always `width` and `height` attributes.
- **Required per lesson:**
  - the hero/poster (the reel cover or a designed image), ≥ 1200 px wide, 16:9 crop
    `img/learn/<slug>-1200x675.jpg` (used as `og:image` and in Article `image`);
  - 0–3 in-body diagrams or screenshots when they explain something the text cannot.
- **Alt text:**
  - Persian, describes what the image shows, ≤ 125 characters, no «تصویر» / «عکس» prefix.
  - Diagrams: what the diagram says («مقایسه‌ی کیف پول سرد و گرم: اتصال به اینترنت، سرعت و
    امنیت»).
  - The owner's photo: «بهنام جلالی در حال توضیح <topic>».
  - Screenshots (exchange pages): the step («صفحه‌ی ثبت‌نام صرافی ویکس با فیلد ایمیل و کد دعوت»).
  - Decorative images (patterns, the brand mark): `alt=""`.
  - The primary query appears in at most one alt, and only if it is literally true.
- Hero: `fetchpriority="high"`, never `loading="lazy"`; the rest: `loading="lazy"
  decoding="async"`.

## 8. Dates, updates and the refresh policy

- `date` never changes. `updated` (shown as «بازبینی», `dateModified`, sitemap `lastmod`)
  changes **only for a real content change**: a new or corrected fact, a new section, a new FAQ
  answer. Typos, styling, link additions: no date change (fake freshness is a spam signal).
- **Review cadence:**
  - exchange pages (`/exchanges/*`): monthly, and on any change of fees, terms or the referral
    link;
  - time-sensitive lessons (halving, fees, networks, staking yields if ever mentioned): quarterly;
  - every other lesson: yearly.
- **Refresh triggers from Search Console** (monthly, per URL, last 28 days):
  - average position 3–10 and CTR under 2%: rewrite `seo_title` and `description` only;
  - position 8–20: add the missing sub-question(s) from the queries report as an H2 or FAQ;
  - impressions for a query the lesson does not answer: add it, or start a new lesson if it is a
    different intent;
  - two lessons ranking for the same query: merge the weaker into the stronger (301).
- Every refresh is a git commit with a one-line reason; `updated` moves only when the content did.

## 9. The automation's self-check before publishing

1. the final `<title>` ≤ 60 chars; `description` 120–155; the primary query in title, H1,
   answer box, first 100 words, one H2.
2. `answer` 40–60 words; FAQ 3–6 questions, every answer 40–80 words; FAQ JSON-LD = visible text.
3. 3–8 contextual internal links, all to existing pages, canonical form; no `/go/` link.
4. Slug unique, ASCII, not reserved.
5. No price numbers, no predictions, no disclaimers, no «در این مقاله».
6. ی/ک and digits normalised; no double spaces; ZWNJ where needed.
7. Hero image 1200×675 exists; every `<img>` has `alt` (or `alt=""` if decorative), `width`,
   `height`.
8. 1–3 sources, all primary.
9. `python3 build.py` passes its checks (CHECKLIST.md §§3–5) before the deploy.

## 10. News articles (the informational reel, from 2026-11-17)

The same session writes them from its own `qc/news.json` and the reel's script: the ONE story of
the reel, expanded, never another story.

- **Front matter:** as §3, with `pillar: news`, `idea:` empty, `motif: generic` (or the closest),
  `keyword`: the story's main query as people type it (e.g. «ای تی اف بیت کوین»).
- **Slug:** English kebab-case, 2-6 words naming the story (`bitcoin-etf-outflows`); a date only
  when the same story could come back (`fed-rate-decision-2026-11`). Unique like any slug (§6).
- **Body, 600-1,000 words:** «چه اتفاقی افتاد؟» (the facts, with the day), «چرا مهم است؟», «برای
  تو چه معنایی دارد؟» (what a beginner should understand, link to the lesson that explains the
  concept), «قدم بعدی»; then 2-4 FAQ. No predictions, no advice to buy or sell; a price only as
  the news file gives it, with «در لحظه‌ی نوشتن این خبر».
- **Sources:** the story's own links from the news file (1-3), the primary one first.
- **Self-check:** §9 and `sync.py --check` as for a lesson.
