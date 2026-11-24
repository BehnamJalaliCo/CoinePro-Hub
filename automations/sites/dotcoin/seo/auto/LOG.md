# The SEO log (newest last)

Each day's block: the data it started from (Search Console window, the numbers that drove the
decision), every change (URL, field, before → after), the new page, the index requests and the
experiments opened. The hub's own results (applied, left out, IndexNow, «Request indexing») are in
the next day's input pack (applied.json); the session copies the outcome here the day after.

## 2026-11-18 — the automation starts (built by the hub's Claude)
- Search Console (sc-domain:dotcoin.me, verified 2026-11-17, sitemap submitted 13 pages): the
  Performance report has no impressions yet (the property is two days old).
- URL inspection 2026-11-18: /learn/cryptocurrency/, /learn/stablecoin/, /learn/usdt-networks/ and
  /learn/hash/ are on Google; /learn/ethereum/ is «Crawled - currently not indexed» with no
  referring sitemap (Google read the sitemap before the page existed: submitted again).
- «Request indexing» answered «We had a problem submitting your indexing request» for every URL
  tried that day (Google's own refusal for a brand-new property); IndexNow and the sitemap carry
  the new pages meanwhile, and the request is tried again each day.
- /vip/ (TradeYar's free VIP channel) and the lesson block went live the same day.

## 2026-11-22 — the daily session (F-0152)
- **Earlier days (applied.json):** 2026-11-20 (W-000720) «waiting: out/ lacks package.zip», nothing
  published; 2026-11-21 (W-000780) «blocked: the phone review found -1 problem(s)», nothing
  published. -1 is not a finding count (the hub's review gave no count: a crash or a timeout on
  its side); the session cannot read the hub's shots. Today's package is reviewed with the same
  tool (0 findings) and its own pages only.
- **Data (Search Console, 28 days to 2026-11-21):** 22 impressions, 0 clicks, position 52.4.
  Queries: کد رفرال lbank 5 (63), کد رفرال اوربیت 4 (48.8), صرافی weex 2, ال بانک ثبت نام 2,
  ثبت نام در lbank 1, صرافی ویکس 1, دپوزیت چیست 1 (88). Pages: /exchanges/lbank/ 10,
  /exchanges/ourbit/ 4, /exchanges/weex/ 3, /learn/usdt-networks/ 2 (7.5). Indexing phase:
  22 of 29 sitemap URLs on Google; not on Google: /, coin-vs-token, metamask-guide,
  tether-reserves-sp-warning, smart-contract, bitcoin-mining, ethereum. No experiment due.
- **New page:** /learn/referral-code/ «کد رفرال چیست و در صرافی ارز دیجیتال چطور کار می‌کند؟»
  (TOPIC_MAP #36). Why: the only queries with impressions are referral/sign-up queries for our
  exchanges; suggest «کد رفرال» leads with «کد رفرال چیست» and gives the FAQ (کجاست، تغییر کد
  رفرال در ال بانک، چگونه کد رفرال بگیریم، بروکر چیست). Sources: LBank's referral FAQ, WEEX's
  referral help article (read 2026-11-22). Links out: 3 exchange pages, /exchanges/, /vip/,
  how-to-buy-crypto, glossary cex. Glossary: + referral-code, + uid.
- **Changes (one sentence each, a contextual link; no date change: link additions only):**
  - /exchanges/lbank/, /exchanges/ourbit/, /exchanges/weex/, section «کد دعوت/رفرال هنگام
    ثبت‌نام…»: + link «کد رفرال چیست» → /learn/referral-code/ (links in for the new page).
  - /learn/bitcoin/ (mining section) → /learn/bitcoin-mining/ (not on Google).
  - /learn/crypto-wallet/ (hot wallets) → /learn/metamask-guide/ (not on Google).
  - /learn/cryptocurrency/ (tokens) → /learn/coin-vs-token/ (not on Google).
  - /learn/stablecoin/ (fiat-backed) → /learn/tether-reserves-sp-warning/ (not on Google).
- **Measure:** the four unindexed targets' URL inspection on 2026-12-06 (exp-2026-11-22-02…05);
  /learn/referral-code/ indexed and its queries from 2026-12-06 (exp-2026-11-22-01).

## 2026-11-24 — the daily session (F-0182)
- **Earlier days (applied.json):** 2026-11-22 (W-001021) done: every file applied, deployed, IndexNow 200,
  sitemap submitted, /learn/referral-code/ live; «Request indexing» refused («We had a problem submitting
  your indexing request»). 2026-11-23 (F-0167): no package reached the hub (the session stalled before
  packing), nothing published that day.
- **Data (Search Console, 28 days to 2026-11-23):** 35 impressions, 1 click (CTR 2.9%), position 42.7.
  Pages: /exchanges/lbank/ 14 (59.3), /learn/usdt-networks/ 7 impr, 1 click (6.4), /exchanges/ourbit/ 6
  (46.3), /exchanges/weex/ 3, /learn/bitcoin-halving/ 2 (26), /glossary/ 2, /learn/hash/ 1 (2).
  Queries: کد رفرال lbank 7 (60.1), کد رفرال اوربیت 6 (46.3), ال بانک ثبت نام 4 (65.3), صرافی weex 2,
  هاوینگ بعدی بیت کوین 1 (8), دپوزیت چیست 1 (88). No striking-distance query and no CTR gap (all under
  50 impressions: too little data). Indexing phase: 25 of 32 sitemap URLs on Google. Not on Google: /
  (never crawled), referral-code, coin-vs-token, smart-contract, bitcoin-mining, ethereum,
  blackrock-ibit-outflows-end-2026-11. metamask-guide and tether-reserves-sp-warning are now on Google
  (targets of 2026-11-22's links; judged 2026-12-06). Experiments due: 0.
- **Health:** build + audit 0 errors / 0 warnings (32 pages); live_check all ok (/vip/, every /go/vip-*
  hop, robots keeps /go/ out); Lighthouse mobile on /exchanges/lbank/, /learn/referral-code/, /vip/:
  performance 99, accessibility 100, best practices 100, SEO 92 (robots Content-Signal, known, §8).
- **New page:** /learn/crypto-signal/ «سیگنال ارز دیجیتال چیست و چطور درست از آن استفاده کنیم؟»
  (TOPIC_MAP #1, DIRECTION §7: the VIP cluster). Evidence: suggest «سیگنال ارز دیجیتال» --deep, 148
  completions (چیست، یعنی چی، چگونه استفاده کنیم، رایگان، پولی، فیوچرز، با هوش مصنوعی، پامپ، کانال …).
  Top results (arzdigital, updated 2024-04) give no numbers: our page adds position sizing from the
  stop-loss, leverage vs risk, win rate × average win/loss and profit factor with a worked table, why a
  follower's result differs. Sources: LBank's TP/SL help article, CFTC's pump-and-dump advisory (a fact
  only). Links out: glossary stop-loss, take-profit, futures, leverage; /vip/; how-to-buy-crypto;
  /exchanges/; blackrock-ibit-outflows-end-2026-11. Glossary: + signal, take-profit, deposit.
- **Changes (link additions and glossary lines: no `updated:` change):**
  - /vip/, FAQ «کارنامه‌ی سیگنال‌ها را کجا ببینم؟»: + one sentence → /learn/crypto-signal/ (links in).
  - /learn/referral-code/, VIP paragraph: + one sentence → /learn/crypto-signal/ (links in).
  - /learn/blockchain/, «بلاک‌چین به چه کاری می‌آید»: + one sentence on smart contracts →
    /learn/smart-contract/ (not on Google; its only links in were coin-vs-token, itself unindexed, and solana).
  - /learn/crypto-signal/ → /learn/blackrock-ibit-outflows-end-2026-11/ (its first contextual link in).
  - /glossary/: + deposit «واریز (دپوزیت)» for the query «دپوزیت چیست» (1 impression, too little data).
- **Index requests first:** /learn/crypto-signal/, / (the home page has never been crawled),
  /learn/smart-contract/.
- **Measure (2026-12-08):** exp-2026-11-24-01…04: crypto-signal indexed and its queries; smart-contract
  and blackrock-ibit-outflows-end-2026-11 URL inspection; «دپوزیت چیست» position. The home page's
  inspection tomorrow.
