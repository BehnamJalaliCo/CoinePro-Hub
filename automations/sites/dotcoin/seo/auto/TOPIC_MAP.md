# The SEO topic map: one cluster, one page

The clusters the daily SEO session may build a NEW page for. It picks the day's cluster from
Search Console first (a query the site already shows for with no page of its own, a striking-
distance query a new page would serve better), then from this map by priority, after checking
Google suggest that day. Statuses: `candidate` → `live:<date>` (its page) → `refreshed:<date>`.

**Never here** (somebody else owns them; the package gate refuses them):
- the long videos' 122 lessons (kit dotcoin-longform `topics.md`): their page is made with their
  video, and a page made earlier would stop that video's upload;
- the live lessons and their topic keys (`seo/PAGE_PLAN.md` §7);
- prices, predictions, signals, «which coin to buy», sanctions, legal or tax questions.

The reel bank's ideas (`ideas.json`, `PAGE_PLAN.md` §5) may become an SEO page when the data says
it is the day's best opportunity; the reel made later on that topic then joins the page (sync.py)
instead of writing a second one.

| # | Slug | Primary query | Secondary queries | Intent | Pillar | Links (to / from) | Priority | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | `crypto-signal` | سیگنال ارز دیجیتال چیست | کانال سیگنال ارز دیجیتال، سیگنال فیوچرز، سیگنال رایگان | info → VIP | market | /vip/, futures-trading (when live), stop-loss | P1 | candidate |
| 2 | `tether` | تتر چیست | تتر چیست به زبان ساده، تتر usdt، پشتوانه تتر | info | basics | stablecoin, usdt-networks, how-to-buy-crypto | P1 | candidate |
| 3 | `crypto-for-beginners` | آموزش ارز دیجیتال از صفر | شروع ارز دیجیتال، ارز دیجیتال برای مبتدی ها | hub / path | basics | every cornerstone lesson | P1 | candidate |
| 4 | `price-action` | پرایس اکشن چیست | آموزش پرایس اکشن، پرایس اکشن ارز دیجیتال | info | market | technical-analysis (video), support-resistance | P1 | candidate |
| 5 | `kyc` | احراز هویت صرافی ارز دیجیتال | kyc چیست، مدارک احراز هویت صرافی | info / how-to | exchange | how-to-buy-crypto, /exchanges/ | P1 | candidate |
| 6 | `usdc` | usdc چیست | یو اس دی سی، فرق تتر و usdc | info | basics | stablecoin, tether | P1 | candidate |
| 7 | `margin-trading` | معاملات مارجین چیست | مارجین ترید، کراس و ایزوله | info | market | leverage, futures-trading (video) | P1 | candidate |
| 8 | `altseason` | آلت سیزن چیست | فصل آلت کوین ها، شاخص آلت سیزن | info | market | altcoins (video), bitcoin-dominance | P1 | candidate |
| 9 | `bitcoin-etf` | ای تی اف بیت کوین چیست | etf بیت کوین، بلک راک بیت کوین | info | market | bitcoin, news lessons | P1 | candidate |
| 10 | `open-interest` | اوپن اینترست چیست | open interest در ارز دیجیتال | info | market | funding-rate (video), long-short (video) | P1 | candidate |
| 11 | `pump-and-dump` | پامپ و دامپ چیست | پامپ چیست، کانال پامپ | info / safety | myths | crypto-scams (video), rug-pull (video) | P1 | candidate |
| 12 | `bollinger-bands` | باند بولینگر چیست | اندیکاتور بولینگر | info | market | rsi-indicator (video), moving-average (video) | P2 | candidate |
| 13 | `ichimoku` | ایچیموکو چیست | آموزش ایچیموکو، ابر ایچیموکو | info | market | technical-analysis (video) | P2 | candidate |
| 14 | `divergence` | واگرایی در تحلیل تکنیکال | واگرایی rsi، واگرایی مثبت و منفی | info | market | rsi-indicator (video), macd (video) | P2 | candidate |
| 15 | `elliott-wave` | امواج الیوت چیست | آموزش امواج الیوت | info | market | technical-analysis (video), fibonacci (video) | P2 | candidate |
| 16 | `trend-line` | خط روند چیست | رسم خط روند، شکست خط روند | info / how-to | market | support-resistance, chart-patterns (video) | P2 | candidate |
| 17 | `stochastic` | اندیکاتور استوکاستیک | استوکاستیک rsi | info | market | rsi-indicator (video) | P2 | candidate |
| 18 | `scalping` | اسکالپ چیست | اسکالپ در ارز دیجیتال، اسکالپینگ | info | market | trading-psychology (video), risk-management | P2 | candidate |
| 19 | `swing-trading` | سوئینگ ترید چیست | معامله نوسانی | info | market | scalping, day-trading | P2 | candidate |
| 20 | `day-trading` | دی تریدینگ چیست | ترید روزانه ارز دیجیتال | info | market | scalping, swing-trading | P2 | candidate |
| 21 | `trading-plan` | پلن معاملاتی چیست | نوشتن پلن معاملاتی | how-to | market | risk-management, trading-psychology (video) | P2 | candidate |
| 22 | `risk-reward` | ریسک به ریوارد چیست | نسبت ریسک به ریوارد | info | market | stop-loss, take-profit (video) | P2 | candidate |
| 23 | `stablecoin-depeg` | دی پگ استیبل کوین | چرا استیبل کوین دی پگ می شود | info | basics | stablecoin, terra-luna-collapse (video) | P2 | candidate |
| 24 | `layer-1` | لایه یک بلاک چین چیست | لایه اول، شبکه لایه یک | info | defi | layer-2, blockchain-trilemma (video) | P2 | candidate |
| 25 | `rollup` | رول آپ چیست | zk rollup، optimistic rollup | info | defi | layer-2, zero-knowledge-proof (video) | P2 | candidate |
| 26 | `sidechain` | ساید چین چیست | زنجیره جانبی | info | defi | layer-2, crypto-bridge | P3 | candidate |
| 27 | `blockchain-use-cases` | کاربرد بلاک چین | کاربردهای بلاک چین در زندگی | info | basics | blockchain | P2 | candidate |
| 28 | `crypto-vs-stocks` | ارز دیجیتال یا بورس | فرق ارز دیجیتال و سهام | comparison | basics | cryptocurrency, bitcoin-vs-gold (video) | P2 | candidate |
| 29 | `tether-vs-usdc` | فرق تتر و usdc | تتر یا usdc | comparison | basics | tether, usdc | P3 | candidate |
| 30 | `bitcoin-address-types` | انواع آدرس بیت کوین | آدرس سگویت، تپروت، legacy | info | security | wallet-address (video), send-bitcoin-guide (video) | P3 | candidate |
| 31 | `honeypot-token` | توکن هانی پات چیست | ارز هانی پات، تشخیص هانی پات | safety | security | rug-pull (video), crypto-scams (video) | P2 | candidate |
| 32 | `crypto-faucet` | فاست ارز دیجیتال چیست | faucet | info | basics | airdrop | P3 | candidate |
| 33 | `testnet` | تست نت چیست | تست نت و مین نت | info | basics | ethereum | P3 | candidate |
| 34 | `crypto-glossary-beginner` | اصطلاحات ارز دیجیتال | واژه های ارز دیجیتال برای مبتدی | hub | terms | /glossary/ | P3 | candidate |
| 35 | `crypto-exchange-guide` | صرافی ارز دیجیتال چیست | صرافی ارز دیجیتال چطور کار می کند | info | exchange | cex-vs-dex, /exchanges/ | P2 | candidate |
| 36 | `referral-code` | کد رفرال چیست | کد دعوت صرافی، رفرال | info | exchange | /exchanges/, /vip/ | P2 | candidate |
| 37 | `limit-stop-order` | سفارش استاپ لیمیت چیست | stop limit، تفاوت استاپ مارکت و استاپ لیمیت | info | market | market-vs-limit-order, stop-loss | P2 | candidate |
| 38 | `oco-order` | سفارش oco چیست | سفارش او سی او | info | market | limit-stop-order, take-profit (video) | P3 | candidate |
| 39 | `liquidation-price` | قیمت لیکوئید شدن | محاسبه قیمت لیکوئید | info | market | leverage, margin-trading | P2 | candidate |
| 40 | `crypto-signal-checklist` | بهترین کانال سیگنال ارز دیجیتال | چطور کانال سیگنال معتبر را بشناسیم | info → VIP | market | crypto-signal, /vip/ | P1 | candidate |
