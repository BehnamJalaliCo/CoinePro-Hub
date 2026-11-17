# dotcoin.me: the Persian keyword map

Research date: 2026-11-17. Written by the SEO engineer, phase 1.

## Method and sources (read this first)

- **Question and variant mining:** Google's public suggest endpoint
  (`suggestqueries.google.com/complete/search?client=firefox&hl=fa&gl=ir&q=…`), about 90 seed
  queries. A suggestion only proves that people type the phrase; it says nothing about volume.
- **What ranks:** web searches for the main queries, then the top pages fetched and parsed
  (title, meta description, H1–H3, JSON-LD types, dates, page size):
  - arzdigital.com/blog/what-is-cold-wallet/
  - tabdeal.org/academy/what-are-cold-wallets/
  - khanesarmaye.com/cold-wallet/
  - blog.faradars.org/بلاک-چین-چیست/
  - zoomit.ir/economics/371342-blockchain/
  - arzdigital.com/blog/bitcoin-halving-price-effect/
  - tabdeal.org/academy/what-is-stablecoin/
  - khanesarmaye.com/exchange/weex/
  - iranbroker.net/exchange/lbank/
- **Search volumes are unknown.** Nothing here is a guessed number. "Signal" below means how much
  Google suggest shows for the phrase: **strong** (the bare term plus «چیست» plus several
  modifiers), **medium** (a few crypto completions), **weak** (one completion, or other meanings
  win), **none** (no suggestion). After launch, replace the signals with Search Console data.

## What the SERP looks like (the competition)

| Site | Pattern | Notes |
|---|---|---|
| arzdigital.com | «X یا English چیست؟ - ارزدیجیتال», 12–19 H2, FAQ + FAQPage | strong brand, some pages old (halving page: updated 2023) |
| tabdeal.org/academy | «X چیست؟ هر آنچه … باید بدانید - آکادمی تبدیل» | an exchange's academy; product lists inside education; updates 2024 |
| khanesarmaye.com | «X چیست و انواع آن کدامند؟ - خانه سرمایه», FAQ + FAQPage | fresh (Oct 2026); also ranks for every exchange page |
| blog.faradars.org | Persian slugs, 10k-word pages, FAQ + FAQPage | very long, technical (Byzantine generals) |
| zoomit.ir | NewsArticle, video at the top, FAQ | broad tech brand |
| iranbroker.net | exchange reviews with AggregateRating/Review, HowTo, updated daily | the hardest exchange SERP |
| plisio.net/fa | machine-translated feel | ranks anyway: the bar on clarity is low |

What this means for dotcoin.me:
- Every result is long (4k–11k words of page text, 11–22 H2). None is **short and clear** for a
  beginner. Our edge: one idea explained with one everyday example, a 40–60-word answer at the top,
  the reel, and a short FAQ. Depth comes from covering the sub-questions, not from padding.
- Most pages use «سوالات متداول» with FAQPage. Copy the habit (visible FAQ), not the hope: Google
  shows FAQ rich results only for well-known government and health sites since August 2023. The
  FAQ still answers the long-tail questions and feeds Bing and AI answers.
- Several competitors put AggregateRating/Review on their own articles and exchange pages. That
  breaks Google's review-snippet rules. We never do it.
- Many top pages are stale (2023–2024). Visible, honest update dates are an edge.
- Exchange SERPs reward a straight answer to «… برای ایرانیان تحریم است؟»: khanesarmaye's WEEX page
  ranks with the title «صرافی ویکس برای ایرانیان؛ شرایط و ریسک» and quotes the official terms.

## Spelling and variant policy

Google matches most space / half-space (ZWNJ) variants, but joined forms («بلاکچین») and
colloquial forms («چیه», «یعنی چی») are separate strings. The rule:

1. **Body text, titles, H1:** the standard written form with ZWNJ (see TECHNICAL.md §7).
2. **The query form** (usually with a plain space) appears where people type it: a FAQ question
   written as people ask it, or the glossary's «به شکل … هم نوشته می‌شود» line.
3. Never repeat variants just to have them; one natural appearance is enough.

| Concept | Standard (use in text) | Variants people type | Note |
|---|---|---|---|
| blockchain | بلاک‌چین | بلاک چین، بلاکچین | all three are suggested; «بلاک چین چیست به زبان ساده» in both |
| crypto (generic) | ارز دیجیتال | رمزارز، رمز ارز، کریپتو | «ارز دیجیتال» dominates suggest; «رمزارز» is mostly a news brand; «کریپتو چیست به زبان ساده» exists |
| bitcoin | بیت‌کوین | بیت کوین، BTC | query form is «بیت کوین» |
| stablecoin | استیبل‌کوین | استیبل کوین، ارز پایدار | |
| wallet | کیف پول | کیف‌پول، ولت، wallet | write «کیف پول» with a space (standard and query form) |
| cold / hot wallet | کیف پول سرد / گرم | کیف پول سخت‌افزاری، cold wallet، کیف پول داغ | |
| seed phrase | عبارت بازیابی | سید فریز، seed، کلمات بازیابی | «سید فریز چیست» and «عبارت بازیابی چند کلمه است» both suggested |
| halving | هاوینگ | هاوینگ بیت کوین، نصف شدن پاداش | |
| tether | تتر | USDT، تتر trc20 | |
| exchange | صرافی | اکسچنج | |
| WEEX | ویکس | weex، صرافی weex | users type the Latin name most |
| LBank | ال‌بانک | ال بانک، lbank | users type «ال بانک» with a space; use it in the title and H1 |
| Ourbit | اوربیت | ourbit، صرافی ourbit | |
| stop loss | حد ضرر | استاپ لاس، استاپ‌لاس | query form «استاپ لاس» is far stronger than «حد ضرر» |
| leverage | اهرم | لوریج، لیکویید | query form «لوریج» |
| market cap | ارزش بازار | مارکت کپ | query form «مارکت کپ» |
| dominance | دامیننس | دامیننس بیت کوین، دامیننس تتر | |

In articles whose query form is the loanword (استاپ لاس، لوریج، مارکت کپ، دامیننس): the loanword
goes in the title and H1, the Persian word in the first paragraph and the glossary.

## Clusters by intent

Priority: **P1** build first / keep strongest; **P2** next; **P3** later or inside another page.
"Target" is the one page that owns the cluster; other pages link to it and never compete with it.

### A. Learn (hub intent)

| # | Cluster | Main query | Variants and questions (from suggest) | Signal | Target | P |
|---|---|---|---|---|---|---|
| A1 | learn crypto | آموزش ارز دیجیتال | آموزش ارز دیجیتال از صفر، … رایگان، … با گوشی، یادگیری ارز دیجیتال، یادگیری ارز دیجیتال چقدر طول میکشد، چطور ارز دیجیتال یاد بگیرم | strong | `/` (home) + `/learn/` | P1 |
| A2 | crypto basics | ارز دیجیتال چیست | ارز دیجیتال چیست به زبان ساده، … و چه کاربردی دارد، … و چگونه کار میکند، رمز ارز چیست، کریپتو چیست به زبان ساده، تفاوت ارز دیجیتال و فیات | strong | `/learn/cryptocurrency/` (NOT in the ideas bank: add it, see PAGE_PLAN §6) | P1 |
| A3 | learn blockchain | آموزش بلاک چین | آموزش بلاک چین به زبان ساده، فیلم آموزش بلاک چین | medium | `/learn/blockchain/` | P2 |

### B. What-is (definitional)

| # | Cluster | Main query | Variants and questions | Signal | Target | P |
|---|---|---|---|---|---|---|
| B1 | blockchain | بلاک چین چیست | بلاکچین چیست، بلاک چین چیست به زبان ساده، بلاکچین چیست و چگونه کار میکند، بلاک چین بیت کوین، بلاک چین اکسپلورر، آیا بلاکچین کلاهبرداری است | strong | `/learn/blockchain/` | P1 |
| B2 | cold / hot wallet | کیف پول سرد چیست | کیف پول سرد و گرم، کیف پول گرم چیست، کیف پول سخت افزاری، تراست ولت کیف پول سرد است یا گرم، بهترین کیف پول سرد، کیف پول ارز دیجیتال چیست | strong | `/learn/cold-wallet/` | P1 |
| B3 | halving | هاوینگ بیت کوین چیست | هاوینگ یعنی چی، هاوینگ بعدی بیت کوین کی است، هاوینگ بیت کوین ۲۰۲۸، آخرین هاوینگ بیت کوین کی بود | strong | `/learn/bitcoin-halving/` | P1 |
| B4 | stablecoin / tether | استیبل کوین چیست | استیبل کوین یعنی چه، استیبل کوین های معروف، استیبل کوین تتر با چه ارزی نسبت ثابت دارد، تتر چیست، آیا تتر همان دلار است، استیبل کوین طلا، استیبل کوین های غیر متمرکز | strong | `/learn/stablecoin/` | P1 |
| B5 | bitcoin | بیت کوین چیست | … به زبان ساده، … و چه کاربردی دارد، چرا بیت کوین ارزش دارد، فرق بیت کوین و اتریوم، فرق بیت کوین و تتر، فرق ساتوشی با بیت کوین | strong | `/learn/bitcoin/` | P1 |
| B6 | coin vs token | تفاوت کوین و توکن | کوین و توکن چیست، تفاوت کوین و توکن به زبان ساده، تفاوت میم کوین و توکن | strong | `/learn/coin-vs-token/` | P1 |
| B7 | market metrics | مارکت کپ چیست | دامیننس بیت کوین، دامیننس چیست، دامیننس تتر، شاخص ترس و طمع کریپتو، شاخص ترس و طمع چیست، حجم معاملات چیست | strong | one article each (PAGE_PLAN §5) | P1 |
| B8 | trading basics | استاپ لاس چیست | استاپ لاس یعنی چی، لوریج چیست، لیکویید شدن یعنی چی، سفارش لیمیت چیست، سفارش استاپ لیمیت چیست، حمایت و مقاومت چیست، کندل شناسی، کندل دوجی | strong | one article each | P1 |
| B9 | DeFi / web3 | استیکینگ چیست | ایردراپ چیست، استخر نقدینگی چیست، لایه دوم اتریوم، بریج ارز دیجیتال چیست، وایت پیپر چیست، اوراکل چیست (other meanings win) | medium–strong | one article each | P1–P2 |
| B10 | behaviour | فومو چیست | فومو در ترید، فومو یعنی چی، مدیریت ریسک و سرمایه، استراتژی dca چیست، خرید پله ای ارز دیجیتال | medium | one article each | P2 |

### C. How-to and safety

| # | Cluster | Main query | Variants and questions | Signal | Target | P |
|---|---|---|---|---|---|---|
| C1 | tether networks | تتر trc20 | تتر trc20 چیست، کارمزد شبکه trc20، کارمزد شبکه ترون، کارمزد شبکه bep20، شبکه ترون همون trc20 است، کارمزد شبکه erc20 | strong (Iran-specific) | `/learn/usdt-networks/` | P1 |
| C2 | wrong network | انتخاب اشتباه شبکه انتقال ارز دیجیتال | چطور ارز دیجیتال را به کیف پول انتقال دهیم | medium | `/learn/wrong-network/` | P2 |
| C3 | seed phrase | سید فریز چیست | عبارت بازیابی چند کلمه است، عبارت بازیابی کیف پول، کلید خصوصی کیف پول | medium–strong | `/learn/seed-phrase/` | P1 |
| C4 | scams | فیشینگ ارز دیجیتال | فیشینگ ارز دیجیتال چیست، ایردراپ جعلی، آیا تتر کلاهبرداری است | weak–medium | `/learn/crypto-phishing/` | P2 |
| C5 | network fee | کارمزد شبکه | کارمزد شبکه اتریوم، کارمزد شبکه بیت کوین، گس فی (no suggestions) | medium | `/learn/network-fee/` | P2 |
| C6 | buy crypto | چطور ارز دیجیتال بخریم | آموزش خرید ارز دیجیتال، چگونه ارز دیجیتال بخریم با گوشی | strong, owned by Iranian exchanges («از نوبیتکس») | `/learn/how-to-buy-crypto/` (not in the bank) → links `/exchanges/` | P2 |

### D. Exchange sign-up (commercial / transactional)

| # | Cluster | Main query | Variants and questions | Signal | Target | P |
|---|---|---|---|---|---|---|
| D1 | WEEX | صرافی weex | صرافی ویکس، weex برای ایرانیان، صرافی weex برای ایرانیان تحریم است، صرافی weex برای کدام کشور است، صرافی weex معتبر است، weex دانلود، weex ورود، کارمزد weex، صرافی weex بونوس | strong | `/exchanges/weex/` | P1 |
| D2 | LBank | صرافی ال بانک | lbank، ال بانک برای ایرانیان، صرافی ال بانک برای ایرانیان تحریم است، ال بانک مال کجاست، ال بانک دانلود، ال بانک واریز ریالی دارد، کارمزد lbank، ال بانک ورود | strong | `/exchanges/lbank/` | P1 |
| D3 | Ourbit | صرافی اوربیت | ourbit، صرافی ourbit برای ایرانیان، … تحریم است، صرافی اوربیت معتبر است، صرافی اوربیت کلاهبرداری، صرافی اوربیت ثبت نام، ourbit دانلود، کد رفرال اوربیت | strong, fewer strong competitors (newer exchange) | `/exchanges/ourbit/` | P1 |
| D4 | foreign exchanges | صرافی خارجی برای ایرانیان | بهترین صرافی خارجی برای ایرانیان، صرافی خارجی معتبر، صرافی خارجی ارز دیجیتال، کد رفرال چیست | strong, very competitive | `/exchanges/` | P1 |
| D5 | CEX vs DEX | صرافی غیرمتمرکز | صرافی متمرکز و غیرمتمرکز، صرافی غیرمتمرکز برای ایرانیان | medium–strong | `/learn/cex-vs-dex/` | P2 |
| D6 | exchange fees | کارمزد صرافی ارز دیجیتال | کارمزد weex، کارمزد lbank | medium | `/learn/exchange-fees/` (general) + a fee section on each exchange page | P2 |

### E. Glossary

| # | Cluster | Main query | Variants | Signal | Target | P |
|---|---|---|---|---|---|---|
| E1 | crypto terms | اصطلاحات ارز دیجیتال | اصطلاحات ارز دیجیتال به زبان ساده، … pdf، اصطلاحات ترید ارز دیجیتال، واژه نامه ارز دیجیتال، ath چیست، tvl چیست، فاد چیست | strong | `/glossary/` | P1 |

### F. Brand

| # | Cluster | Main query | Variants | Signal | Target | P |
|---|---|---|---|---|---|---|
| F1 | brand | دات کوین | dotcoin، dotcoin.me، دات‌کوین بهنام جلالی | **contested:** «دات کوین» and «dotcoin» are dominated by the 2024 Telegram tap-game token Dotcoin (DTC): «دات کوین کی لیست میشه», «dotcoin price». «بهنام جلالی» suggests other people. | `/` + `/about/` | P1 |

Brand consequence: the site name in titles and schema must carry the domain or the person:
`دات‌کوین` in the title suffix, `WebSite.alternateName` = ["DotCoin.me", "Dot Coin"], and /about/
says in one plain line that dotcoin.me is an educational site, not a token.

## Intents we do NOT target

- Price, «امروز», «پیش بینی», «چرا بیت کوین ریخت»: no prices, no predictions (owner rule).
- «بهترین ارز برای سرمایه گذاری», «ارز ارزان آینده دار» as picks: the myth article (idea 39)
  answers the reasoning, never names picks.
- «بدون احراز هویت», «بدون تحریم», «با آی‌پی …», any bypass of an exchange's country rules or KYC.
- Religious rulings («حرام است»), politics, named people's projects («بلاک چین بابک زنجانی»).
- Navigational queries of other brands («نوبیتکس», «تبدیل», «کریپتو نگار»).

## The top 10 clusters (build order)

1. D1–D3 the three exchanges → `/exchanges/weex/`, `/exchanges/lbank/`, `/exchanges/ourbit/`
2. A1 آموزش ارز دیجیتال → `/` and `/learn/`
3. B1 بلاک چین چیست → `/learn/blockchain/`
4. B2 کیف پول سرد / گرم → `/learn/cold-wallet/`
5. B3 هاوینگ بیت کوین → `/learn/bitcoin-halving/`
6. B4 استیبل کوین / تتر → `/learn/stablecoin/`
7. E1 اصطلاحات ارز دیجیتال → `/glossary/`
8. C1 تتر trc20 / شبکه‌ها → `/learn/usdt-networks/`
9. B5 بیت کوین چیست → `/learn/bitcoin/`
10. D4 صرافی خارجی برای ایرانیان → `/exchanges/`

Raw suggest output of this research: kept out of the repo (it is only a snapshot); rerun the
endpoint above when you refresh this file.
