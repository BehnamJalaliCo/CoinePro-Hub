# DotCoin long-form topic bank

One long YouTube video (8–10 min) and one NEW lesson on dotcoin.me a day, from 2026-11-18; 122 topics
(about four months). Written by the SEO engineer 2026-11-17 from `automations/sites/dotcoin/seo/`
(KEYWORDS, PAGE_PLAN, ARTICLE_BRIEF). This file is the bank; `bank/topics.json` is retired.

## How the kit uses it

1. Take the **first row with status `free`** whose slug is not live
   (`curl -s -4 https://dotcoin.me/sitemap.xml | grep -o '/learn/[a-z0-9-]*/'`) and not in the hub's
   long-video state; claim it (`topic.claim` «دات‌کوین ویدیو بلند: <title>»; refused = the next row).
2. When the video is uploaded, set the row's status to `used:<YYYY-MM-DD>` (the upload day, Tehran),
   here and in git. A row is used once, ever. Never reorder or delete rows; new topics go at the end.
3. The slug is the lesson's URL: `https://dotcoin.me/learn/<slug>/`. Every slug here is reserved
   (PAGE_PLAN §7): no reel and no other article takes it; a reel on one of these topics joins the
   lesson once it is live (sync.py).
4. **Links:** lesson slugs (`/learn/<slug>/`); `exchanges` = `/exchanges/`. Link only the ones that are
   live on the day (every link points to a lesson that is live now or comes earlier in this list).
5. **Keyword:** the Persian query as people type it (Google suggest), the article's `keyword:`;
   intent: `what-is`, `how-to`, `compare`, `coin` (a coin deep-dive), `story` (history), `myth`.
6. The lesson follows `seo/ARTICLE_BRIEF.md`: answer box, FAQ, sources, internal links; no prices, no
   predictions, no signals, nothing on sanctions, legal status or country rules, no disclaimers.

## The bank

| # | status | slug | title | keyword | intent | pillar | angle | links |
|---|---|---|---|---|---|---|---|---|

| 1 | used:2026-11-17 | `ethereum` | اتریوم چیست؟ از قرارداد هوشمند تا گس و اثبات سهام | اتریوم چیست | coin | basics | رایانه‌ای جهانی که برنامه اجرا می‌کند؛ اتر، گس و اثبات سهام در یک تصویر | blockchain, bitcoin, usdt-networks, crypto-wallet |
| 2 | free | `bitcoin-mining` | استخراج بیت‌کوین چطور کار می‌کند؟ | ماینینگ بیت کوین چیست | what-is | basics | قرعه‌کشی‌ای که امنیت بیت‌کوین را می‌خرد: از حدس عدد تا پاداش بلاک | bitcoin, hash, bitcoin-halving, blockchain |
| 3 | free | `smart-contract` | قرارداد هوشمند چیست؟ | قرارداد هوشمند چیست | what-is | basics | دستگاه فروش خودکاری از جنس کد: قاعده‌هایی که خودشان اجرا می‌شوند | ethereum, blockchain, crypto-wallet |
| 4 | free | `metamask-guide` | آموزش متامسک قدم‌به‌قدم | آموزش متامسک | how-to | security | نصب، پشتیبان‌گیری، افزودن شبکه، دریافت و ارسال؛ بی یک اشتباه | crypto-wallet, cold-wallet, ethereum, usdt-networks |
| 5 | free | `solana` | سولانا چیست؟ | سولانا چیست | coin | basics | شبکه‌ی سریع: اثبات تاریخ، کارمزد کم و درس‌هایی که از قطعی‌ها گرفت | ethereum, smart-contract, blockchain, cryptocurrency |
| 6 | free | `bitcoin-history` | تاریخچه‌ی بیت‌کوین از ۲۰۰۸ تا امروز | تاریخچه بیت کوین | story | basics | از یک مقاله‌ی ۹ صفحه‌ای تا دارایی جهانی؛ نقطه‌های عطف به ترتیب | bitcoin, blockchain, bitcoin-halving, bitcoin-mining |
| 7 | free | `proof-of-stake` | اثبات سهام چیست؟ | اثبات سهام چیست | what-is | basics | اعتبارسنج، وثیقه و جریمه: شبکه چطور بی ماینر به توافق می‌رسد | ethereum, bitcoin-mining, blockchain |
| 8 | free | `trust-wallet-guide` | آموزش تراست ولت | آموزش تراست ولت | how-to | security | کیف‌پول گوشی، درست راه‌اندازی‌شده: پشتیبان، شبکه‌ها، توکن‌ها و دام‌ها | crypto-wallet, usdt-networks, cold-wallet, metamask-guide |
| 9 | free | `spot-vs-futures` | اسپات یا فیوچرز؟ فرق دو بازار صرافی | فرق اسپات و فیوچرز | compare | exchange | داشتن خود ارز در برابر قراردادی روی قیمتش؛ برای تو چه چیزی عوض می‌شود | how-to-buy-crypto, exchanges, cryptocurrency |
| 10 | free | `toncoin` | تون‌کوین و شبکه‌ی TON چیست؟ | تون کوین چیست | coin | basics | شبکه‌ای که از تلگرام آمد: کیف‌پول‌ها، جتون‌ها و راز رشد سریعش | usdt-networks, crypto-wallet, blockchain |
| 11 | free | `mt-gox` | ماجرای مت‌گاکس؛ سقوط اولین صرافی بزرگ بیت‌کوین | مت گاکس | story | security | بزرگ‌ترین صرافی بیت‌کوین چطور سکه‌هایش را از دست داد و درسش درباره‌ی نگه‌داری | bitcoin-history, crypto-wallet, cold-wallet |
| 12 | free | `block-explorer-guide` | آموزش بلاک اکسپلورر؛ تراکنش را خودت پیدا کن | بلاک اکسپلورر چیست | how-to | basics | هش تراکنش، تأییدها و کارمزد: هر تراکنشی را مثل یک حرفه‌ای بخوان | blockchain, hash, usdt-networks, bitcoin |
| 13 | free | `decentralized-finance` | دیفای چیست؟ مالی غیرمتمرکز به زبان ساده | دیفای چیست | what-is | defi | کارهای بانکی که با قرارداد هوشمند از نو ساخته شده‌اند: وام، سپرده، معامله | ethereum, smart-contract, stablecoin |
| 14 | free | `technical-analysis` | تحلیل تکنیکال چیست؟ | تحلیل تکنیکال چیست | what-is | market | نمودار چه می‌گوید و چه نمی‌گوید؛ روش، نه سیگنال | cryptocurrency, how-to-buy-crypto, exchanges |
| 15 | free | `bitcoin-energy` | بیت‌کوین چه ربطی به برق دارد؟ | بیت کوین و برق | myth | myths | چرا استخراج برق مصرف می‌کند، این برق از کجا می‌آید و معنای واقعی‌اش چیست | bitcoin-mining, bitcoin, proof-of-stake |
| 16 | free | `xrp` | ریپل (XRP) چیست؟ | ریپل چیست | coin | basics | دفتری ساخته‌شده برای پرداخت: اعتبارسنج‌ها، تسویه‌ی سریع و فرقش با بیت‌کوین | bitcoin, blockchain, cryptocurrency |
| 17 | free | `public-key-cryptography` | کلید عمومی و کلید خصوصی چطور کار می‌کنند؟ | کلید عمومی و خصوصی | what-is | security | صندوق پستی و کلیدش: امضایی که مالکیت را ثابت می‌کند بی‌آنکه رازی لو برود | crypto-wallet, hash, cold-wallet |
| 18 | free | `order-book` | اوردر بوک چیست و چطور خوانده می‌شود؟ | اوردر بوک چیست | what-is | exchange | خریداران یک طرف، فروشندگان طرف دیگر: عمق بازار، اسپرد و انجام سفارش | spot-vs-futures, how-to-buy-crypto, exchanges |
| 19 | free | `nft` | ان‌اف‌تی چیست؟ | ان اف تی چیست | what-is | defi | توکنی یکتا با یک مالک: اثر هنری، بلیت، آیتم بازی و آنچه واقعاً مال توست | ethereum, smart-contract, crypto-wallet |
| 20 | free | `satoshi-nakamoto` | ساتوشی ناکاموتو کیست؟ | ساتوشی ناکاموتو کیست | story | basics | بنیان‌گذار ناشناس: آنچه می‌دانیم، آنچه نمی‌دانیم و چرا مهم نیست | bitcoin, bitcoin-history, cryptocurrency |
| 21 | free | `bnb` | بی‌ان‌بی و BNB Chain چیست؟ | بی ان بی چیست | coin | basics | توکن یک صرافی که شبکه شد: BEP20، کارمزدها و اعتبارسنج‌ها | usdt-networks, ethereum, smart-contract |
| 22 | free | `tonkeeper-guide` | آموزش تون‌کیپر | آموزش تون کیپر | how-to | security | کیف‌پول TON از صفر: عبارت بازیابی، جتون‌ها، ممو و انتقال امن | toncoin, crypto-wallet, usdt-networks |
| 23 | free | `futures-trading` | معاملات فیوچرز چیست؟ | فیوچرز چیست | what-is | exchange | قرارداد، مارجین، فاندینگ و لیکویید شدن در یک تصویر روشن | spot-vs-futures, exchanges, order-book |
| 24 | free | `hard-fork` | فورک چیست؟ هارد فورک و سافت فورک | هارد فورک چیست | what-is | basics | وقتی یک بلاک‌چین قاعده‌هایش را عوض می‌کند: ارتقا، انشعاب و ارز تازه | blockchain, bitcoin, ethereum |
| 25 | free | `cardano` | کاردانو چیست؟ | کاردانو چیست | coin | basics | طراحی پژوهش‌محور: اوروبوروس، ADA و راه آرام و پیوسته | proof-of-stake, ethereum, smart-contract |
| 26 | free | `crypto-scams` | کلاهبرداری‌های رایج ارز دیجیتال | کلاهبرداری ارز دیجیتال | what-is | security | پنج الگویی که هر کلاهبرداری تکرار می‌کند و یک قاعده در برابر همه | crypto-wallet, cold-wallet, how-to-buy-crypto |
| 27 | free | `bitcoin-pizza-day` | روز پیتزای بیت‌کوین | روز پیتزا بیت کوین | story | basics | ۱۰٬۰۰۰ بیت‌کوین برای دو پیتزا: اولین خرید واقعی و درسی که داد | bitcoin-history, bitcoin, satoshi-nakamoto |
| 28 | free | `moving-average` | میانگین متحرک چیست؟ | میانگین متحرک | how-to | market | خطی که نویز را صاف می‌کند: SMA و EMA و اینکه معامله‌گرها چطور می‌خوانندش | technical-analysis, order-book, exchanges |
| 29 | free | `tron` | ترون چیست؟ | ترون چیست | coin | basics | شبکه‌ی تتر روزمره: انرژی، پهنای باند و TRX | usdt-networks, stablecoin, crypto-wallet |
| 30 | free | `tokenomics` | توکنومیکس چیست؟ | توکنومیکس چیست | what-is | basics | عرضه، آزادسازی، سوزاندن و انگیزه‌ها: اقتصاد یک توکن را پیش از هر چیز بخوان | cryptocurrency, bitcoin-halving, ethereum |
| 31 | free | `dogecoin` | دوج‌کوین چیست؟ | دوج کوین چیست | coin | basics | شوخی‌ای که یکی از بزرگ‌ترین ارزها شد: پیدایش، عرضه و جامعه | bitcoin, cryptocurrency, bitcoin-mining |
| 32 | free | `multisig` | کیف پول چندامضایی چیست؟ | کیف پول چند امضایی | what-is | security | دو کلید از سه کلید: نقطه‌ی شکست تک را حذف کن | crypto-wallet, public-key-cryptography, cold-wallet |
| 33 | free | `the-dao-hack` | هک DAO و تولد اتریوم کلاسیک | هک دائو | story | defi | اشکالی در ۲۰۱۶ که اتریوم را دو تکه کرد | ethereum, hard-fork, smart-contract |
| 34 | free | `rsi-indicator` | اندیکاتور RSI چیست؟ | اندیکاتور rsi | how-to | market | شتاب قیمت روی مقیاس صفر تا صد و معنای واقعی «اشباع خرید» | technical-analysis, moving-average, exchanges |
| 35 | free | `web3` | وب ۳ چیست؟ | وب ۳ چیست | what-is | defi | خواندن، نوشتن، مالک بودن: ایده‌ی وب ۳ و جایی که امروز ایستاده | ethereum, decentralized-finance, nft |
| 36 | free | `bitcoin-lightning` | شبکه‌ی لایتنینگ بیت‌کوین چیست؟ | لایتنینگ نتورک | what-is | basics | پرداخت‌های کوچک و فوری روی بیت‌کوین: کانال‌ها به زبان ساده | bitcoin, block-explorer-guide, hard-fork |
| 37 | free | `mempool` | ممپول چیست و چرا تراکنش گیر می‌کند؟ | ممپول چیست | what-is | basics | اتاق انتظار تراکنش‌ها: کارمزد، اولویت و انتقال‌های گیرکرده | block-explorer-guide, bitcoin-mining, usdt-networks |
| 38 | free | `copy-trading` | کپی ترید چیست؟ | کپی ترید چیست | what-is | exchange | دنبال کردن خودکار یک معامله‌گر دیگر: سازوکارش در صرافی و آنچه باید بسنجی | exchanges, spot-vs-futures, futures-trading |
| 39 | free | `polkadot` | پولکادات چیست؟ | پولکادات چیست | coin | basics | شبکه‌ای از شبکه‌ها: زنجیره‌ی رله، پاراچین‌ها و DOT | blockchain, proof-of-stake, ethereum |
| 40 | free | `rug-pull` | راگ پول چیست؟ | راگ پول | what-is | security | وقتی تیم نقدینگی را می‌کشد و می‌رود: نشانه‌ها پیش از خرید | crypto-scams, tokenomics, decentralized-finance |
| 41 | free | `terra-luna-collapse` | سقوط ترا و لونا | سقوط لونا | story | myths | یک استیبل‌کوین الگوریتمی چطور در چند روز برابری‌اش را از دست داد | stablecoin, decentralized-finance, tokenomics |
| 42 | free | `tradingview-guide` | آموزش تریدینگ ویو | آموزش تریدینگ ویو | how-to | market | نمودار، تایم‌فریم، اندیکاتور و هشدار با نسخه‌ی رایگان | technical-analysis, moving-average, rsi-indicator |
| 43 | free | `altcoins` | آلت‌کوین چیست؟ | آلت کوین چیست | what-is | basics | هر چه بیت‌کوین نیست: خانواده‌ها، کاربردها و راه تشخیصشان | cryptocurrency, bitcoin, ethereum |
| 44 | free | `chainlink` | چین‌لینک چیست؟ | چین لینک چیست | coin | defi | آوردن داده‌ی بیرون به بلاک‌چین: شبکه‌ی اوراکل و LINK | smart-contract, ethereum, decentralized-finance |
| 45 | free | `consensus-mechanisms` | الگوریتم اجماع چیست؟ | الگوریتم اجماع | what-is | basics | هزاران غریبه چطور بر سر یک دفتر توافق می‌کنند: اثبات کار، اثبات سهام و بیشتر | proof-of-stake, bitcoin-mining, blockchain |
| 46 | free | `exchange-account-security` | امنیت حساب صرافی؛ تنظیماتی که باید روشن کنی | امنیت حساب صرافی | how-to | security | اپ احراز هویت، کد ضدفیشینگ، فهرست آدرس مجاز و دستگاه‌های واردشده | exchanges, crypto-scams, how-to-buy-crypto |
| 47 | free | `avalanche` | آوالانچ چیست؟ | آوالانچ چیست | coin | basics | ساب‌نت‌ها و قطعیت سریع: آوالانچ و AVAX | ethereum, consensus-mechanisms, smart-contract |
| 48 | free | `market-cycles` | بازار گاوی و خرسی چیست؟ | بازار گاوی و خرسی | what-is | market | واژه‌های چرخه‌ی بازار، بی پیش‌بینی چرخه‌ی بعدی | bitcoin-halving, technical-analysis, bitcoin-history |
| 49 | free | `memecoins` | میم‌کوین چیست؟ | میم کوین چیست | what-is | myths | ارزهایی که از یک شوخی ساخته شده‌اند: چطور عرضه می‌شوند، چرا تند نوسان دارند | dogecoin, tokenomics, rug-pull |
| 50 | free | `utxo` | مدل UTXO بیت‌کوین چیست؟ | utxo چیست | what-is | basics | بیت‌کوین موجودی ندارد، سکه‌ی خرج‌نشده دارد: راز آدرس باقی‌مانده | bitcoin, block-explorer-guide, mempool |
| 51 | free | `hardware-wallet-setup` | راه‌اندازی کیف پول سخت‌افزاری قدم‌به‌قدم | راه اندازی کیف پول سخت افزاری | how-to | security | از جعبه تا اولین انتقال: بررسی اصالت، پشتیبان و آزمایش | cold-wallet, crypto-wallet, multisig |
| 52 | free | `shiba-inu` | شیبا اینو چیست؟ | شیبا چیست | coin | basics | از میم تا اکوسیستم: SHIB، عرضه و سوزاندن | memecoins, dogecoin, tokenomics |
| 53 | free | `funding-rate` | فاندینگ ریت چیست؟ | فاندینگ ریت | what-is | exchange | کارمزدی که قرارداد دائمی را به قیمت اسپات گره می‌زند | futures-trading, spot-vs-futures, exchanges |
| 54 | free | `ethereum-merge` | مرج اتریوم؛ خداحافظی اتریوم با ماینینگ | مرج اتریوم | story | basics | تغییر ۲۰۲۲ به اثبات سهام، قدم‌به‌قدم | ethereum, proof-of-stake, hard-fork |
| 55 | free | `dao` | دائو (DAO) چیست؟ | دائو چیست | what-is | defi | سازمان‌هایی که با رأی توکن و کد اداره می‌شوند | smart-contract, the-dao-hack, web3 |
| 56 | free | `litecoin` | لایت‌کوین چیست؟ | لایت کوین چیست | coin | basics | نقره‌ی بیت‌کوین: بلاک‌های سریع‌تر، الگوریتم اسکریپت و عرضه‌ی چهار برابر | bitcoin, bitcoin-mining, bitcoin-halving |
| 57 | free | `fundamental-analysis` | تحلیل فاندامنتال ارز دیجیتال | تحلیل فاندامنتال | how-to | market | تیم، کاربرد، توکنومیکس و پذیرش: سنجیدن پروژه، نه نمودار | tokenomics, technical-analysis, altcoins |
| 58 | free | `51-percent-attack` | حمله‌ی ۵۱ درصد چیست؟ | حمله ۵۱ درصد | what-is | security | مهاجمی که بیشتر قدرت شبکه را دارد چه می‌تواند بکند و چه نمی‌تواند | bitcoin-mining, consensus-mechanisms, hard-fork |
| 59 | free | `polygon` | پالیگان چیست؟ | پالیگان چیست | coin | basics | زنجیره‌ی کناری اتریوم که خانواده‌ای برای مقیاس‌پذیری شد: POL و کارمزدها | ethereum, smart-contract, usdt-networks |
| 60 | free | `crypto-myths` | ده باور غلط درباره‌ی ارز دیجیتال | باورهای غلط ارز دیجیتال | myth | myths | ده جمله‌ی پرتکرار که درست نیستند (جدا از سه باور غلط ریلزها) | cryptocurrency, bitcoin, blockchain |
| 61 | free | `dex-swap-guide` | آموزش سواپ در صرافی غیرمتمرکز | سواپ چیست | how-to | defi | کیف‌پول، شبکه، تنظیم لغزش و تأیید: اولین سواپ بی‌غافلگیری | metamask-guide, decentralized-finance, crypto-scams |
| 62 | free | `bitcoin-cash` | بیت‌کوین کش و جنگ اندازه‌ی بلاک | بیت کوین کش چیست | story | basics | انشعاب ۲۰۱۷ بر سر اندازه‌ی بلاک و آنچه هر طرف می‌خواست | hard-fork, bitcoin-history, bitcoin |
| 63 | free | `fibonacci` | فیبوناچی در تحلیل تکنیکال | فیبوناچی چیست | how-to | market | سطح‌های اصلاحی: چطور کشیده می‌شوند و چرا این‌قدر دیده می‌شوند | technical-analysis, tradingview-guide, moving-average |
| 64 | free | `proof-of-reserves` | اثبات ذخایر صرافی چیست؟ | اثبات ذخایر | what-is | exchange | صرافی چطور نشان می‌دهد دارایی کاربرانش را دارد: درخت مرکل به زبان ساده | exchanges, mt-gox, hash |
| 65 | free | `cosmos` | کازماس چیست؟ | کازماس چیست | coin | basics | اینترنت بلاک‌چین‌ها: IBC و ATOM | polkadot, proof-of-stake, blockchain |
| 66 | free | `yield-farming` | ییلد فارمینگ چیست؟ | ییلد فارمینگ | what-is | defi | کسب بازده با تأمین نقدینگی: این بازده از کجا می‌آید | decentralized-finance, tokenomics, rug-pull |
| 67 | free | `send-bitcoin-guide` | ارسال بیت‌کوین قدم‌به‌قدم | ارسال بیت کوین | how-to | basics | نوع آدرس، انتخاب کارمزد و تأییدها | bitcoin, mempool, utxo |
| 68 | free | `cypherpunks` | سایفرپانک‌ها؛ پیش از بیت‌کوین | سایفرپانک | story | basics | آدم‌ها و ایده‌هایی که بیت‌کوین را ممکن کردند | bitcoin-history, satoshi-nakamoto, public-key-cryptography |
| 69 | free | `trading-bots` | ربات معامله‌گر ارز دیجیتال چیست؟ | ربات ترید | what-is | exchange | ربات گرید، خرید دوره‌ای و سیگنال: چطور کار می‌کنند و چه کاری از آن‌ها برنمی‌آید | exchanges, copy-trading, spot-vs-futures |
| 70 | free | `near-protocol` | نیر پروتکل چیست؟ | نیر پروتکل | coin | basics | شاردینگ و حساب‌هایی با نام خوانا | ethereum, proof-of-stake, smart-contract |
| 71 | free | `zero-knowledge-proof` | اثبات دانش صفر چیست؟ | اثبات دانش صفر | what-is | basics | ثابت کن می‌دانی، بی‌آنکه بگویی: ایده‌ی پشت رول‌آپ‌های zk | public-key-cryptography, ethereum, hash |
| 72 | free | `wallet-address` | آدرس کیف پول چیست؟ | آدرس کیف پول | what-is | security | قالب‌ها، کنترل خطا، کد QR و ممو یا تگ در یک درس | crypto-wallet, usdt-networks, public-key-cryptography |
| 73 | free | `bitcoin-ordinals` | اوردینالز بیت‌کوین چیست؟ | اوردینالز | what-is | basics | نوشته روی ساتوشی‌ها: ان‌اف‌تی روی بیت‌کوین و بحث‌هایش | nft, bitcoin, utxo |
| 74 | free | `macd` | اندیکاتور MACD | اندیکاتور مکدی | how-to | market | دو میانگین متحرک و یک هیستوگرام، آرام خوانده‌شده | moving-average, rsi-indicator, tradingview-guide |
| 75 | free | `stellar` | استلار چیست؟ | استلار چیست | coin | basics | پرداخت و لنگرگاه‌ها: XLM به زبان ساده | xrp, stablecoin, blockchain |
| 76 | free | `biggest-crypto-hacks` | بزرگ‌ترین هک‌های تاریخ کریپتو | هک صرافی ارز دیجیتال | story | security | الگوهای پشت هک‌های بزرگ و درس هر کدام | mt-gox, crypto-scams, cold-wallet |
| 77 | free | `lending-protocols` | وام گرفتن در دیفای چطور کار می‌کند؟ | وام در دیفای | what-is | defi | وثیقه، ضریب سلامت و لیکویید شدن در پروتکل‌های وام | decentralized-finance, smart-contract, stablecoin |
| 78 | free | `long-short` | پوزیشن لانگ و شورت چیست؟ | لانگ و شورت | what-is | exchange | سود از بالا یا پایین رفتن: سازوکار، بی هیجان | futures-trading, funding-rate, spot-vs-futures |
| 79 | free | `uniswap` | یونی‌سواپ چیست؟ | یونی سواپ | coin | defi | صرافی‌ای بدون دفتر سفارش | dex-swap-guide, decentralized-finance, ethereum |
| 80 | free | `quantum-bitcoin` | آیا کامپیوتر کوانتومی بیت‌کوین را می‌شکند؟ | کامپیوتر کوانتومی بیت کوین | myth | myths | کامپیوتر کوانتومی چه چیزی را تهدید می‌کند، چه چیزی را نه، و برنامه‌ها | public-key-cryptography, hash, bitcoin |
| 81 | free | `token-launch` | عرضه‌ی اولیه‌ی توکن چیست؟ ICO، IDO و لانچ‌پد | ico چیست | what-is | exchange | توکن‌های تازه چطور به بازار می‌رسند و اول چه چیزی را باید خواند | tokenomics, rug-pull, exchanges |
| 82 | free | `difficulty-adjustment` | سختی شبکه‌ی بیت‌کوین چیست؟ | سختی شبکه بیت کوین | what-is | basics | ترموستاتی که بلاک‌ها را روی ده دقیقه نگه می‌دارد | bitcoin-mining, bitcoin, mempool |
| 83 | free | `sui` | سویی چیست؟ | سویی چیست | coin | basics | زبان Move و مدل شیء‌محور | solana, smart-contract, proof-of-stake |
| 84 | free | `market-maker` | مارکت میکر کیست؟ | مارکت میکر | what-is | exchange | چه کسی دفتر سفارش را پر نگه می‌دارد | order-book, exchanges, spot-vs-futures |
| 85 | free | `can-bitcoin-be-hacked` | آیا بیت‌کوین هک می‌شود؟ | هک بیت کوین | myth | myths | شبکه در برابر کیف‌پول تو: هک‌ها واقعاً کجا اتفاق می‌افتند | bitcoin, 51-percent-attack, crypto-scams |
| 86 | free | `liquid-staking` | لیکوئید استیکینگ چیست؟ | لیکوئید استیکینگ | what-is | defi | سپرده‌شده و همچنان نقد: توکن‌های استیکینگ نقد و بده‌بستان‌هایشان | proof-of-stake, decentralized-finance, ethereum-merge |
| 87 | free | `vitalik-buterin` | ویتالیک بوترین کیست؟ | ویتالیک بوترین | story | basics | نوجوانی که بیت‌کوینِ برنامه‌پذیر می‌خواست | ethereum, ethereum-merge, the-dao-hack |
| 88 | free | `chart-patterns` | الگوهای نموداری مهم | الگوهای نموداری | how-to | market | سر و شانه، مثلث و پرچم: چه هستند و چرا گاهی کار نمی‌کنند | technical-analysis, fibonacci, tradingview-guide |
| 89 | free | `real-world-assets` | توکنیزه کردن دارایی‌های واقعی (RWA) | rwa چیست | what-is | defi | اوراق، طلا و ملک به‌شکل توکن: سازوکار و پشتوانه | stablecoin, tokenomics, smart-contract |
| 90 | free | `ethereum-classic` | اتریوم کلاسیک چیست؟ | اتریوم کلاسیک | coin | basics | زنجیره‌ای که تاریخچه‌ی اصلی را نگه داشت | the-dao-hack, hard-fork, ethereum |
| 91 | free | `token-burn` | سوزاندن توکن چیست؟ | سوزاندن توکن | what-is | basics | حذف همیشگی سکه‌ها: چرا پروژه‌ها می‌سوزانند و چه چیزی عوض می‌شود | tokenomics, shiba-inu, bnb |
| 92 | free | `exchange-withdrawal-guide` | آموزش واریز و برداشت در صرافی | برداشت از صرافی | how-to | exchange | شبکه، آدرس، ممو، کارمزد و سقف: یک رفت و برگشت تمیز | exchanges, usdt-networks, wallet-address |
| 93 | free | `on-chain-analysis` | تحلیل آنچین چیست؟ | تحلیل آنچین | what-is | market | خواندن خود دفتر: جریان‌ها، دارندگان و فعالیت شبکه | block-explorer-guide, fundamental-analysis, utxo |
| 94 | free | `whales` | نهنگ‌های بازار ارز دیجیتال | نهنگ ارز دیجیتال | what-is | market | کیف‌پول‌های بزرگ، اینکه جابه‌جایی‌شان چه نشان می‌دهد و چطور دنبالشان می‌کنند | on-chain-analysis, block-explorer-guide, order-book |
| 95 | free | `tap-to-earn` | بازی‌های تپ تو ارن تلگرام چطور کار می‌کنند؟ | بازی تلگرامی ارز دیجیتال | what-is | myths | ضربه، امتیاز و ایردراپ: این بازی‌ها از کجا پول درمی‌آورند و چه کسی می‌پردازد | toncoin, tokenomics, crypto-scams |
| 96 | free | `crypto-payments` | پرداخت با ارز دیجیتال چطور کار می‌کند؟ | پرداخت با ارز دیجیتال | how-to | basics | از کد QR تا تأیید: استیبل‌کوین، لایتنینگ و درگاه‌های پرداخت | stablecoin, bitcoin-lightning, wallet-address |
| 97 | free | `hedera` | هدرا چیست؟ | هدرا چیست | coin | basics | هش‌گراف به‌جای بلاک | consensus-mechanisms, blockchain, proof-of-stake |
| 98 | free | `take-profit` | حد سود (تیک پرافیت) چیست؟ | تیک پرافیت | how-to | exchange | برنامه‌ی خروج را پیش از ورود بنویس | spot-vs-futures, order-book, exchanges |
| 99 | free | `blockchain-trilemma` | سه‌گانه‌ی بلاک‌چین چیست؟ | سه گانه بلاک چین | what-is | basics | امنیت، تمرکززدایی و سرعت: آیا فقط دو تا ممکن است؟ | consensus-mechanisms, solana, ethereum |
| 100 | free | `aave` | آوه (Aave) چیست؟ | آوه چیست | coin | defi | پروتکل وام، از نزدیک | lending-protocols, decentralized-finance, stablecoin |
| 101 | free | `crypto-portfolio` | سبد ارز دیجیتال را چطور مرتب کنیم؟ | سبد ارز دیجیتال | how-to | market | تقسیم دارایی، توازن دوباره و پیگیری، بی پیش‌بینی | fundamental-analysis, stablecoin, market-cycles |
| 102 | free | `arbitrage` | آربیتراژ ارز دیجیتال چیست؟ | آربیتراژ | what-is | exchange | یک ارز، دو قیمت: چرا این فاصله پیدا می‌شود و بسته می‌شود | order-book, exchanges, exchange-withdrawal-guide |
| 103 | free | `lost-bitcoins` | بیت‌کوین‌های گم‌شده | بیت کوین گم شده | story | security | کلیدهایی که برای همیشه گم شدند و درسشان درباره‌ی پشتیبان‌گیری | cold-wallet, crypto-wallet, bitcoin |
| 104 | free | `decentralized-storage` | ذخیره‌سازی غیرمتمرکز؛ فایل‌کوین و آرویو | فایل کوین چیست | coin | defi | نگه داشتن فایل بی شرکت ابری | blockchain, tokenomics, smart-contract |
| 105 | free | `ico-boom-2017` | حباب ICO در سال ۲۰۱۷ | حباب ico | story | myths | هزاران توکن در یک سال: چه شد و چه ماند | token-launch, tokenomics, rug-pull |
| 106 | free | `erc-20` | استاندارد ERC-20 چیست؟ | erc20 چیست | what-is | basics | قاعده‌های مشترکی که توکن‌ها را در هر کیف‌پولی کارا می‌کند | ethereum, smart-contract, usdt-networks |
| 107 | free | `bitcoin-node` | نود بیت‌کوین چیست و چطور اجرا می‌شود؟ | نود بیت کوین | how-to | basics | نسخه‌ی خودت از دفتر: چرا و چطور | bitcoin, blockchain, consensus-mechanisms |
| 108 | free | `evaluate-crypto-project` | چطور یک پروژه‌ی ارز دیجیتال را بررسی کنیم؟ | بررسی پروژه ارز دیجیتال | how-to | myths | فهرستی ده‌قدمی از سایت پروژه تا زمان‌بندی آزادسازی توکن | fundamental-analysis, tokenomics, rug-pull |
| 109 | free | `makerdao-dai` | دای و میکر دائو چیست؟ | دای چیست | coin | defi | دلاری با پشتوانه‌ی وثیقه‌ی رمزارزی | stablecoin, lending-protocols, dao |
| 110 | free | `defi-summer-2020` | تابستان دیفای ۲۰۲۰ | تابستان دیفای | story | defi | ییلد فارمینگ چطور در یک تابستان اوج گرفت | yield-farming, decentralized-finance, uniswap |
| 111 | free | `merkle-tree` | درخت مرکل چیست؟ | درخت مرکل | what-is | basics | یک بلاک چطور با چند هش ثابت می‌کند تراکنشی در آن است | hash, proof-of-reserves, blockchain |
| 112 | free | `phone-security` | امنیت گوشی برای کاربر ارز دیجیتال | امنیت گوشی ارز دیجیتال | how-to | security | سیم‌کارت، اپ‌ها، کلیپ‌بورد و پشتیبان: گوشی‌ای که کیف‌پولت در آن است را محکم کن | crypto-wallet, exchange-account-security, crypto-scams |
| 113 | free | `kaspa` | کاسپا چیست؟ | کاسپا چیست | coin | basics | اثبات کار با چند بلاک هم‌زمان: بلاک‌داگ | bitcoin-mining, consensus-mechanisms, blockchain |
| 114 | free | `nft-boom-2021` | جنون ان‌اف‌تی در سال ۲۰۲۱ | جنون nft | story | myths | از کریپتوپانک‌ها تا فروکش کردن هیجان | nft, ethereum, memecoins |
| 115 | free | `smart-wallets` | کیف پول هوشمند چیست؟ | کیف پول هوشمند | what-is | security | کیف‌پول به‌شکل قرارداد هوشمند: بازیابی اجتماعی و تراکنش بی‌گس | crypto-wallet, multisig, smart-contract |
| 116 | free | `trading-psychology` | روانشناسی معامله‌گری | روانشناسی ترید | how-to | market | برنامه، دفترچه‌ی معامله و سوگیری‌هایی که بیشترین هزینه را دارند | market-cycles, take-profit, crypto-portfolio |
| 117 | free | `decentralization` | تمرکززدایی واقعاً یعنی چه؟ | تمرکززدایی | what-is | basics | چه کسی می‌تواند شبکه را متوقف کند؟ سنجیدن تمرکززدایی | blockchain, consensus-mechanisms, bitcoin-node |
| 118 | free | `gamefi` | گیم‌فای چیست؟ | گیم فای | what-is | defi | اقتصاد بازی برای کسب درآمد و چرا بیشتر مدل‌ها شکستند | nft, tokenomics, tap-to-earn |
| 119 | free | `ethereum-upgrades` | ارتقاهای اتریوم از هوم‌استد تا امروز | ارتقا اتریوم | story | basics | ارتقاهای نام‌دار و اینکه هر کدام چه چیزی را عوض کرد | ethereum, ethereum-merge, hard-fork |
| 120 | free | `bitcoin-vs-gold` | بیت‌کوین یا طلا؟ مقایسه‌ی دو دارایی کمیاب | بیت کوین یا طلا | compare | basics | کمیابی، نگه‌داری، جابه‌جایی و نوسان: دو دارایی کنار هم، بی پیش‌بینی | bitcoin, bitcoin-halving, cold-wallet |
| 121 | free | `ai-crypto` | هوش مصنوعی و ارز دیجیتال؛ پروژه‌های AI روی بلاک‌چین | ارز دیجیتال هوش مصنوعی | what-is | defi | توکن‌های محاسبه، داده و عامل هوشمند: چه چیزی واقعاً روی زنجیره است | decentralized-storage, tokenomics, evaluate-crypto-project |
| 122 | free | `crypto-backup-plan` | برنامه‌ی پشتیبان دارایی دیجیتال | پشتیبان گیری کیف پول | how-to | security | برنامه‌ای نوشته‌شده برای کلیدها، دستگاه‌ها و دسترسی خانواده | cold-wallet, multisig, lost-bitcoins |
