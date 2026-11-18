# DIRECTION — how the DotCoin.me SEO day thinks

The goal is the owner's: **every day more of Iran's crypto learners find dotcoin.me on Google, and
the pages that matter reach page one.** A good day moves a real number (impressions, position,
clicks, pages indexed) or builds the page that will. A bad day adds words nobody searches for.

## 1. White hat, always (Google's spam policies; a violation can sink the whole domain)
- **Never:** pages made for search engines rather than people (thin, spun, auto-rewritten, the same
  page with another keyword), keyword stuffing, hidden text or links, cloaking, doorway pages, bought,
  swapped or comment links, private networks, fake reviews or ratings (no AggregateRating/Review
  markup on our own pages), FAQ or other markup that is not visible on the page, a fake «updated»
  date (`updated:` only after a real content change), scraping another site's text.
- **Always:** one page per intent, written to be the best answer in Persian (clear, true, complete,
  current), the author's real byline (the build adds it), sources for facts, honest dates.
- **The site's own rules** (S/content/FORMAT.md, owner): no prices or price numbers, no signals or
  predictions, no «which coin to buy», no hype, no warnings or disclaimers, no politics, no legal,
  sanctions or tax content, no RTL/LTR scramble or overflow (zero tolerance), no /go/ link inside a
  lesson (the sponsored links live in the templates).
- **Never touch** what others own: the long videos' lessons (topics.md slugs: made with their
  video), the reel articles' `reel:`, `youtube:`, `idea:`, `date:` fields, build.py, the templates, CSS,
  JS, vip.json (TradeYar's facts), exchanges.json. A code problem you see goes in report.md.

## 2. The data first
Search Console is the truth about Google; the suggest tool is the truth about what people type; the
competitors' pages are the bar to beat. Never a guessed volume. A young property (few impressions)
is in its **indexing phase**: then the day's work is (a) every page indexed (internal links to the
unindexed, the sitemap, the index requests the hub makes), (b) new pages on clusters with strong
suggest evidence, (c) technical health. Once impressions arrive, the **ranking phase** begins and
§3's order rules.

## 3. The day's priorities, in this order
1. **Something broken** (the hub's applied.json says a package was refused or a file left out; the
   audit's errors; live_check FAIL lines; a page Google dropped from the index): fix first.
2. **Experiments due:** judge them (keep, or roll the change back; §5).
3. **Striking distance** (position 4.5–20 with impressions): the page that ranks gets the missing
   sub-question as a section, a FAQ answer, a better H2, internal links from strong pages, a fresher
   fact. The query must clearly match the page's intent; else it is a new cluster.
4. **CTR gaps** (≥ 80 impressions, CTR well under its position's yardstick): a better `seo_title`
   (≤ 60 characters, the query's words first, a concrete promise) and `description` (110–160
   characters, the answer's hook); one rewrite per page per 14 days.
5. **The new page** (every day, never skipped for the above): the best cluster by evidence: a query
   with impressions and no page of its own, then TOPIC_MAP by priority. It must be the best Persian
   page for its intent: deeper on the sub-questions than the top results, clearer, current.
6. **Internal links and site structure:** every new page gets links in and out; orphans get links;
   hub pages (/learn/, the cornerstones) point at the clusters; anchors describe the target.
7. **Freshness:** a lesson whose facts aged (a network upgrade, a fee change) gets the fact and an
   `updated:` date.

## 4. On-page rules for a page (new or improved)
- **Title (`seo_title`):** the primary query's words early, ≤ 60 characters with « | دات‌کوین» (the
  build adds the suffix only while it fits), unique.
- **H1 (`title`):** natural, the query's meaning; one per page (the build makes it).
- **Description:** 110–160 characters, a reason to click, the primary query once.
- **The first 100 words** answer the query; the answer box (40–60 words) is complete on its own
  (featured snippets and AI answers quote it).
- **Structure:** H2 per sub-question (from suggest), a table for comparisons, numbered steps for a
  process, a worked example with everyday numbers (never a price prediction), a short FAQ.
- **Structured data** is the build's (Article, FAQPage of the visible FAQ, BreadcrumbList,
  VideoObject when a video exists): keep the fields that feed it complete and true.
- **Links:** 4–8 internal (descriptive anchors), 1–3 external to primary sources (`sources`), never
  to a competitor's article as a source of facts.
- **Keyword use:** natural; the primary query in title, H1 meaning, first paragraph, one H2 and the
  description; variants once each where they read naturally (KEYWORDS.md's spelling policy).

## 5. Measurement (every change is an experiment)
- Before a change: its baseline from the digest (the page's and the query's 28-day impressions,
  clicks, CTR, position). After: judged at +14 days (CTR, position) and +28 days (impressions,
  clicks). A loss with the same position (CTR lower) → roll the title/description back. A section
  that did not lift a striking query in 28 days → try a stronger page structure or internal links,
  not more words.
- Small numbers lie: under 50 impressions, write «too little data» and wait; never call a winner.
- LOG.md is the memory: what was tried, what happened, what was learned. Read the last 14 days of it
  before deciding; never repeat a change that lost.

## 6. The owner's weekly lines (week.fa.txt, the Saturday day only)
3–5 short Persian lines, numbers first, no jargon: the week's Google impressions and clicks against
the week before, the new pages (how many, one or two names), the best move (a query or a page and its
position), the index (pages indexed of all), the VIP page (its impressions; its clicks when the hub
could read them). Nothing else: the owner reads it in his weekly summary.

## 7. TradeYar's VIP on the site
/vip/ and the lesson block are the site's commercial goal: keep them healthy every day (live_check:
the page, its date, every /go/vip-* hop to TradeYar's tracker and on to the bot or the exchange). Grow
/vip/'s search reach through the cluster «سیگنال ارز دیجیتال / کانال سیگنال» (TOPIC_MAP #1, #40):
educational pages that answer the questions honestly and link to /vip/ in their text where it truly
helps (an internal link, never a /go/ link). /vip/'s own text (content/pages/vip.md) may be improved
for search like any page; TradeYar's facts (the free membership, 50 USDT, 30 USDT to stay, Ourbit or
LBank through TradeYar's link, the UID to @TradeYarSignalBot) must stay exactly as TradeYar states
them (https://trade-future.ir/vip): if they changed, say it in report.md (the hub updates vip.json).

## 8. Known and accepted
- Cloudflare adds `Content-Signal: …` to robots.txt (its managed AI-crawl policy): Lighthouse calls it
  an unknown directive; Google ignores it. Not ours to change.
- Search Console data lags two to three days; the newest days in the trend are partial.
- «Request indexing» is Google's to refuse (a daily cap; for a new property it may answer «problem
  submitting»): the hub tries the URLs you put first, and the sitemap, internal links and IndexNow
  carry the rest.
