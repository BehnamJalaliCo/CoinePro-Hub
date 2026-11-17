# dotcoin.me: the page plan

Phase 1, 2026-11-17. Keywords and evidence: KEYWORDS.md. Technical rules: TECHNICAL.md.
All `<title>` lengths (≤ 60) and meta description lengths (≤ 155) below were counted by script,
ZWNJ included. Brand suffix: ` | دات‌کوین` (dropped where the title would pass 60).

## 1. URL structure

```
/                         home
/learn/                   all lessons, grouped by pillar + the beginner path
/learn/<slug>/            one lesson (one reel = one lesson)
/glossary/                one page, one anchor per term: /glossary/#<term-slug>
/exchanges/               the three exchanges side by side
/exchanges/weex/
/exchanges/lbank/
/exchanges/ourbit/
/about/                   who, why, how
/404.html                 served by Pages with status 404 (never indexed)
/go/<exchange>/           302 to the referral link (robots.txt Disallow, never in the sitemap)
/sitemap.xml  /robots.txt  /feed.xml
```

Rules:
- Every page is a directory URL with a trailing slash (`/learn/blockchain/`). Internal links
  always use that exact form. Details: TECHNICAL.md §1.
- Slugs are English, lowercase, kebab-case, the topic noun (`cold-wallet`, not `what-is-cold-wallet`).
  Reserved, never an article slug: `basics security exchange market defi myths terms page tag
  feed go search`. Full rules: ARTICLE_BRIEF.md §6.
- No `/learn/<pillar>/` pages yet: pillars are sections of `/learn/` with anchors
  (`/learn/#security`). Revisit when a pillar passes about 15 lessons (then add
  `/learn/topic/<pillar>/`; that path does not collide with any article).
- One glossary page, not one page per term: a one-line definition alone is a thin page. A term
  that earns a full article gets `/learn/<slug>/`, and its glossary line links there.

## 2. Site-wide elements

- **Header:** logo → `/`; nav: «آموزش‌ها» `/learn/` · «واژه‌نامه» `/glossary/` · «صرافی‌ها»
  `/exchanges/` · «درباره» `/about/`. Plain `<a>` links (crawlable), no JS menus.
- **Footer:** the same four links, Instagram `https://www.instagram.com/dotcoin.me/`, the latest
  3 lessons, ©. No disclaimer text (owner's taste).
- **Breadcrumb** on every page except `/`: visible `<nav aria-label="breadcrumb">`
  («خانه › آموزش‌ها › بلاک‌چین») + BreadcrumbList JSON-LD with the same items.
- **JSON-LD:** one `<script type="application/ld+json">` per page holding an `@graph`. Shared
  nodes keep fixed `@id`s so pages reference them:
  - `https://dotcoin.me/#org` (Organization), `https://dotcoin.me/#website` (WebSite),
    `https://dotcoin.me/about/#behnam` (Person).
- **Not allowed anywhere:** Review, AggregateRating, Rating (we have no real user reviews; Google
  forbids self-serving review snippets); Organization markup for the exchanges; HowTo (Google
  dropped HowTo rich results in 2023); a fake SearchAction (Google retired the sitelinks search
  box in Nov 2024; add SearchAction only if a real `/search/` page ever exists).

## 3. Page by page

### 3.1 Home `/`

- **Primary:** آموزش ارز دیجیتال · **Secondary:** آموزش ارز دیجیتال به زبان ساده، آموزش ارز دیجیتال
  از صفر، یادگیری ارز دیجیتال رایگان، کریپتو چیست به زبان ساده، دات‌کوین
- **title:** `آموزش ارز دیجیتال به زبان ساده | دات‌کوین` (41)
- **description:** `آموزش ارز دیجیتال و بلاک‌چین به زبان ساده و فارسی، با بهنام جلالی: درس‌های کوتاه از صفر، واژه‌نامه‌ی اصطلاحات کریپتو و راهنمای صرافی‌ها.` (136)
- **H1:** `آموزش ارز دیجیتال به زبان ساده`
- **Outline:**
  - lead (2 sentences: what the site is, for whom: a beginner, one idea at a time)
  - H2 `از کجا شروع کنم؟`: the beginner path, 6 lessons in order (see 3.2)
  - H2 `تازه‌ترین درس‌ها`: the 6 newest lessons (card: title, one-line lead, date)
  - H2 `موضوع‌ها`: the 7 pillars, each → `/learn/#<pillar>`
  - H2 `واژه‌نامه‌ی ارز دیجیتال`: 8 popular terms → `/glossary/#…`, link «همه‌ی اصطلاحات»
  - H2 `صرافی‌ها`: one paragraph + link `/exchanges/` (no referral buttons on the home page)
  - H2 `دات‌کوین چیست؟`: 2–3 sentences, by Behnam Jalali, Instagram link, → `/about/`
- **Links out:** `/learn/`, 6 newest + 6 path lessons, `/glossary/`, `/exchanges/`, `/about/`, IG.
- **Links in:** every page (logo, breadcrumb root).
- **JSON-LD:** Organization (`name` «دات‌کوین», `alternateName` ["DotCoin.me", "Dot Coin"],
  `url`, `logo` ImageObject 384×384 PNG, `sameAs` [IG URL], `founder` → #behnam only if the owner
  confirms), WebSite (`name` «دات‌کوین», `alternateName`, `url`, `inLanguage` "fa",
  `publisher` → #org), WebPage (`isPartOf` #website, `about` #org).

### 3.2 Learn hub `/learn/`

- **Primary:** آموزش ارز دیجیتال از صفر · **Secondary:** یادگیری ارز دیجیتال، آموزش بلاک چین، آموزش
  کریپتو
- **title:** `آموزش‌های ارز دیجیتال از صفر | دات‌کوین` (39)
- **description:** `همه‌ی درس‌های دات‌کوین در یک جا: بلاک‌چین، بیت‌کوین، کیف پول و امنیت، صرافی، سواد بازار و دیفای؛ هر درس یک مفهوم با یک مثال ساده.` (129)
- **H1:** `آموزش ارز دیجیتال از صفر`
- **Outline:**
  - lead
  - H2 `مسیر یادگیری از صفر` (ordered list; grows as lessons exist): بلاک‌چین → بیت‌کوین →
    کوین و توکن → استیبل‌کوین → کیف پول سرد و گرم → عبارت بازیابی → شبکه‌ی تتر → صرافی متمرکز
    و غیرمتمرکز
  - H2 per pillar, in this order, each with `id` = the pillar key: `پایه‌ها` (basics),
    `امنیت و کیف پول` (security), `صرافی و خرید و فروش` (exchange), `سواد بازار` (market),
    `دیفای و وب۳` (defi), `باور غلط` (myths), `یک اصطلاح در یک دقیقه` (terms). Cards newest first.
- **Links:** out to every lesson; in from header, home, every lesson's breadcrumb.
- **JSON-LD:** CollectionPage + ItemList (`itemListElement` ListItem `position`, `url`, `name`
  for every lesson) + BreadcrumbList.

### 3.3 Lesson `/learn/<slug>/` (template)

Full rules: ARTICLE_BRIEF.md. In short:
- **title:** `<title question> | دات‌کوین` ≤ 60 · **description:** 120–155 · **H1:** the question
  in full form (may be longer than the title).
- **Outline skeleton:** H1 → lead → «پاسخ کوتاه» box (40–60 words) → byline + dates → reel
  block → 4–7 H2 → «خلاصه در ۵ قدم» → H2 «پرسش‌های پرتکرار» (H3 per question) → «منابع» →
  «درس بعدی» + 3 related lessons.
- **JSON-LD:** Article + WebPage + BreadcrumbList + FAQPage (only for the visible FAQ). Example:

```json
{"@context":"https://schema.org","@graph":[
 {"@type":"WebPage","@id":"https://dotcoin.me/learn/blockchain/","url":"https://dotcoin.me/learn/blockchain/",
  "name":"بلاک‌چین چیست؟ توضیح با یک مثال ساده","inLanguage":"fa",
  "isPartOf":{"@id":"https://dotcoin.me/#website"},
  "breadcrumb":{"@id":"https://dotcoin.me/learn/blockchain/#breadcrumb"},
  "primaryImageOfPage":{"@id":"https://dotcoin.me/learn/blockchain/#image"}},
 {"@type":"Article","@id":"https://dotcoin.me/learn/blockchain/#article",
  "headline":"بلاک‌چین چیست؟ با یک مثال ساده",
  "description":"<the meta description>",
  "image":[{"@type":"ImageObject","@id":"https://dotcoin.me/learn/blockchain/#image",
            "url":"https://dotcoin.me/img/learn/blockchain-1200x675.jpg","width":1200,"height":675}],
  "datePublished":"2026-11-18T12:00:00+03:30","dateModified":"2026-11-18T12:00:00+03:30",
  "author":{"@id":"https://dotcoin.me/about/#behnam"},
  "publisher":{"@id":"https://dotcoin.me/#org"},
  "mainEntityOfPage":{"@id":"https://dotcoin.me/learn/blockchain/"},
  "articleSection":"پایه‌ها","inLanguage":"fa"},
 {"@type":"Person","@id":"https://dotcoin.me/about/#behnam","name":"بهنام جلالی",
  "alternateName":"Behnam Jalali","url":"https://dotcoin.me/about/",
  "sameAs":["https://www.instagram.com/dotcoin.me/"]},
 {"@type":"BreadcrumbList","@id":"https://dotcoin.me/learn/blockchain/#breadcrumb","itemListElement":[
  {"@type":"ListItem","position":1,"name":"خانه","item":"https://dotcoin.me/"},
  {"@type":"ListItem","position":2,"name":"آموزش‌ها","item":"https://dotcoin.me/learn/"},
  {"@type":"ListItem","position":3,"name":"بلاک‌چین"}]},
 {"@type":"FAQPage","@id":"https://dotcoin.me/learn/blockchain/#faq","mainEntity":[
  {"@type":"Question","name":"آیا بلاک‌چین قابل هک است؟",
   "acceptedAnswer":{"@type":"Answer","text":"<the visible answer, same words>"}}]}
]}
```

(The Organization and WebSite nodes are full on the home page; other pages reference them by
`@id`. Including them on every page is also fine; never with different values.)

### 3.4 Glossary `/glossary/`

- **Primary:** اصطلاحات ارز دیجیتال · **Secondary:** اصطلاحات ارز دیجیتال به زبان ساده، واژه نامه ارز
  دیجیتال، اصطلاحات ترید ارز دیجیتال، «X چیست» for short terms (ath، tvl، فاد، هولد)
- **title:** `اصطلاحات ارز دیجیتال به زبان ساده | دات‌کوین` (44)
- **description:** `واژه‌نامه‌ی ارز دیجیتال: معنی ساده‌ی اصطلاحات کریپتو و ترید، از بلاک‌چین و تتر تا استاپ لاس، لوریج، دامیننس، ATH و TVL، به فارسی روان.` (134)
- **H1:** `واژه‌نامه‌ی ارز دیجیتال: اصطلاحات کریپتو به زبان ساده`
- **Outline:**
  - lead + a letter index (آ ا ب پ … ی, then A–Z for Latin-only terms such as ATH, TVL, DCA)
  - H2 per letter (`id="letter-<n>"`)
  - each term: `<h3 id="<term-slug>">بلاک‌چین (Blockchain)</h3>` + the one-line definition + an
    optional «به شکل «بلاک چین» و «بلاکچین» هم نوشته می‌شود.» line (the only place for spelling
    variants) + «درس کامل: …» link when `/learn/<slug>/` exists.
  - Sort with Persian collation (آ before ا; پ چ ژ گ in their Persian places), not code points.
- **Initial terms (≥ 40 at launch):** بلاک‌چین، بلوک، هش، نود، اجماع، استخراج (ماینینگ)، بیت‌کوین،
  ساتوشی، اتریوم، آلت‌کوین، کوین، توکن، میم‌کوین، استیبل‌کوین، تتر (USDT)، کیف پول، کیف پول سرد،
  کیف پول گرم، کلید خصوصی، کلید عمومی، عبارت بازیابی، آدرس کیف پول، شبکه (TRC20، ERC20، BEP20)،
  کارمزد شبکه (گس)، صرافی متمرکز (CEX)، صرافی غیرمتمرکز (DEX)، احراز هویت (KYC)، P2P، سفارش
  مارکت، سفارش لیمیت، استاپ لاس، لوریج، لیکویید شدن، اسپات، فیوچرز، مارکت کپ، دامیننس، حجم
  معاملات، کندل، حمایت، مقاومت، ATH، ATL، فومو، فاد، هولد، DCA، استیکینگ، استخر نقدینگی، ضرر
  ناپایدار، بریج، لایه دوم، اوراکل، ایردراپ، وایت‌پیپر، TVL، هاوینگ، فیشینگ، تأیید دومرحله‌ای (2FA).
- **Links:** out to lessons; in from every lesson (first mention of a term), home, header.
- **JSON-LD:** DefinedTermSet (`@id` `https://dotcoin.me/glossary/#set`, `name`, `inLanguage`)
  with `hasDefinedTerm`: one DefinedTerm per term (`@id`/`url` = `https://dotcoin.me/glossary/#<slug>`,
  `name`, `alternateName` = English and spelling variants, `description` = the visible line,
  `inDefinedTermSet` → #set) + BreadcrumbList.

### 3.5 Exchanges hub `/exchanges/`

- Owner's standing rule (2026-11-17): no page says anything about sanctions, legal status or country restrictions; the exchange pages carry the features, the signup steps and the code.
- **Primary:** صرافی خارجی ارز دیجیتال · **Secondary:** صرافی خارجی، کد رفرال چیست، صرافی ویکس،
  صرافی ال بانک، صرافی اوربیت
- **title:** `صرافی خارجی ارز دیجیتال: ویکس، ال بانک، اوربیت | دات‌کوین` (57)
- **description (as built):** `راهنمای سه صرافی ویکس (WEEX)، ال بانک (LBank) و اوربیت (Ourbit): امکانات هر کدام، رابط فارسی و ثبت‌نام قدم‌به‌قدم، به زبان ساده.`
- **H1:** `صرافی‌های ویکس، ال بانک و اوربیت`
- **Outline:** lead → H2 (visually hidden) «سه صرافی» + one card per exchange (logo, tagline, the
  code with each exchange's own label, the signup button, «معرفی و راهنمای ثبت‌نام») → «کد دعوت
  چطور کار می‌کند» (3 steps). No "best" claims, no ranking.
- **JSON-LD:** CollectionPage + ItemList (3 ListItems → the exchange pages) + BreadcrumbList.

### 3.6 Exchange pages `/exchanges/weex/`, `/exchanges/lbank/`, `/exchanges/ourbit/`

| | WEEX | LBank | Ourbit |
|---|---|---|---|
| Primary | صرافی weex | صرافی ال بانک | صرافی اوربیت |
| Secondary | صرافی ویکس، ثبت نام weex، weex دانلود، کد دعوت ویکس | lbank، ال بانک دانلود، کد دعوت ال بانک | ourbit، ourbit دانلود، کد رفرال اوربیت |
| title (as built) | `صرافی ویکس (WEEX): معرفی و ثبت‌نام قدم‌به‌قدم \| دات‌کوین` | `صرافی ال بانک (LBank): معرفی و ثبت‌نام قدم‌به‌قدم \| دات‌کوین` | `صرافی اوربیت (Ourbit): معرفی و ثبت‌نام قدم‌به‌قدم \| دات‌کوین` |
| H1 | `صرافی ویکس (WEEX) چیست و چطور ثبت‌نام کنیم؟` | `صرافی ال بانک (LBank) چیست و چطور ثبت‌نام کنیم؟` | `صرافی اوربیت (Ourbit) چیست و چطور ثبت‌نام کنیم؟` |
| code label (the exchange's own form) | «کد دعوت» | «کد دعوت» | «کد رفرال» |

- Name LBank «ال بانک» (with a space: every suggest completion is written so), not «ال‌بنک».
- **Outline (same for the three; X = the exchange):** H1 + lead + the CTA (signup button, the code
  chip, «سایت رسمی») → H2 «امکانات اصلی» → H2 «ثبت‌نام قدم‌به‌قدم» (an ordered list; the code
  step names the field exactly as the form does) → the body sections (what X is, the app, the
  code) → H2 «پرسش‌های پرتکرار» («آیا سایت X فارسی دارد؟», «برای احراز هویت در X چه چیزی لازم
  است؟», «اپلیکیشن X را از کجا بگیرم؟», «<label> X را کجا وارد کنم؟») → «صرافی‌های دیگر».
- **Referral link:** every CTA → `/go/<exchange>/` (302 in `_redirects`, from
  `content/exchanges.json`, the one place for links and codes), `rel="sponsored nofollow noopener"`.
- **Links in:** `/exchanges/`, home, the exchange-pillar lessons. **Out:** `/exchanges/`, the other
  two exchanges, `/learn/usdt-networks/` and `/learn/wrong-network/` once they exist.
- **JSON-LD:** WebPage + FAQPage + BreadcrumbList. **Not** Organization, Review, Rating,
  FinancialService or HowTo for the exchange.
- **Freshness:** `dateModified` = the page's `updated` front matter, else the newest lesson's date
  (never the build date); re-checked monthly (ARTICLE_BRIEF §8).

### 3.7 About `/about/`

- **Primary:** دات‌کوین · **Secondary:** بهنام جلالی، dotcoin.me، دات‌کوین چیست
- **title:** `درباره‌ی دات‌کوین و بهنام جلالی` (31)
- **description:** `دات‌کوین (dotcoin.me) سایت آموزش ارز دیجیتال به زبان ساده است، نوشته‌ی بهنام جلالی و همراه صفحه‌ی اینستاگرام @dotcoin.me؛ چه کسی، چرا و چطور.` (141)
- **H1:** `درباره‌ی دات‌کوین`
- **Outline:**
  - lead: «دات‌کوین (dotcoin.me) یک سایت آموزشی است، نه یک توکن یا صرافی.» (brand
    disambiguation from the Dotcoin DTC game token; KEYWORDS F1)
  - H2 `بهنام جلالی`: **only facts the owner gives or confirms** (photo with alt «بهنام جلالی»,
    what he does, since when). Nothing invented: no titles, no credentials, no numbers.
  - H2 `چطور درس‌ها ساخته می‌شوند`: one reel → one lesson; facts checked against primary
    sources (the «منابع» section of each lesson); dates shown; corrections welcome
  - H2 `صرافی‌ها و لینک‌های دعوت`: one plain sentence that the exchange buttons are the site's
    referral links (owner's call; it is a trust signal, not a warning)
  - H2 `ارتباط`: Instagram DM link (and an email if the owner wants one)
- **JSON-LD:** AboutPage + the full Person node (#behnam: `name`, `alternateName`, `url`,
  `image`, `sameAs` IG, `jobTitle` only if confirmed) + Organization (#org) + BreadcrumbList.

### 3.8 404

- **title:** `صفحه پیدا نشد | دات‌کوین` · `<meta name="robots" content="noindex">` · H1 `این صفحه
  پیدا نشد` · links: `/`, `/learn/`, `/glossary/`, `/exchanges/` + the 6 newest lessons. No
  JSON-LD. Never in the sitemap.

## 4. The first 4 lessons

Idea ids from `automations/kits/dotcoin-reels/bank/ideas.json`. FAQ questions come from Google
suggest (KEYWORDS.md); answers 40–80 words each.

### 4.1 `/learn/blockchain/` (idea 1, basics)

- **Primary:** بلاک چین چیست · **Secondary:** بلاک چین به زبان ساده، بلاکچین چیست و چگونه کار
  میکند، بلاک چین بیت کوین، بلاک چین اکسپلورر
- **title:** `بلاک‌چین چیست؟ توضیح با یک مثال ساده | دات‌کوین` (47)
- **description:** `بلاک‌چین چیست و چطور کار می‌کند؟ با مثال یک دفتر حساب مشترک که هزاران نفر نسخه‌ای از آن دارند، بلوک، هش، نود و فرق بلاک‌چین با بیت‌کوین را ساده بفهم.` (149)
- **H1:** `بلاک‌چین چیست؟ با یک مثال ساده`
- **Outline:**
  - پاسخ کوتاه (a shared ledger kept by thousands of computers; new pages join only when the
    network agrees; old pages cannot be changed quietly)
  - H2 `مثال دفتر حساب مشترک`
  - H2 `بلاک‌چین چطور کار می‌کند؟` · H3 `بلوک چیست؟` · H3 `هش؛ اثر انگشت هر بلوک` ·
    H3 `نودها و اجماع`
  - H2 `چرا نمی‌شود گذشته را عوض کرد؟`
  - H2 `بلاک‌چین و بیت‌کوین چه فرقی دارند؟`
  - H2 `بلاک‌چین کجا به کار می‌رود؟` (payments, stablecoins, tokens; no hype claims)
  - H2 `خلاصه در ۵ قدم`
  - H2 `پرسش‌های پرتکرار`: «بلاک‌چین به زبان ساده یعنی چه؟» · «آیا بلاک‌چین قابل هک است؟» ·
    «فرق بلاک‌چین و بیت‌کوین چیست؟» · «بلاک‌چین اکسپلورر چیست؟» · «آیا بلاک‌چین کلاهبرداری است؟»
    (answer: a technology, not a product; scams use its name)
  - منابع: bitcoin.org/bitcoin.pdf (the whitepaper), ethereum.org/learn
- **Links out:** glossary (بلوک، هش، نود، اجماع، استخراج), `/learn/bitcoin/`,
  `/learn/coin-vs-token/`, `/learn/cold-wallet/`; next lesson: `/learn/bitcoin/` (until it
  exists: `/learn/cold-wallet/`). **In:** home path, `/learn/` path step 1, glossary «بلاک‌چین»,
  every lesson that says «بلاک‌چین» first.

### 4.2 `/learn/cold-wallet/` (idea 9, security; the task's «کیف‌پول سرد چیست»)

- **Primary:** کیف پول سرد چیست · **Secondary:** کیف پول سرد و گرم، کیف پول گرم چیست، کیف پول سخت
  افزاری، تراست ولت کیف پول سرد است یا گرم، کیف پول ارز دیجیتال چیست
- **title:** `کیف پول سرد چیست؟ فرق کیف پول سرد و گرم | دات‌کوین` (50)
- **description:** `کیف پول سرد چیست و چه فرقی با کیف پول گرم دارد؟ کلید خصوصی کجا می‌ماند، انواع کیف پول سرد، کدام برای چه کاری، و جای امن عبارت بازیابی.` (134)
- **H1:** `کیف پول سرد چیست و چه فرقی با کیف پول گرم دارد؟`
- **Outline:**
  - پاسخ کوتاه (a wallet whose private key never touches the internet)
  - H2 `کیف پول ارز دیجیتال واقعاً چه چیزی را نگه می‌دارد؟` (the key, not the coins)
  - H2 `کیف پول گرم چیست؟`
  - H2 `کیف پول سرد چیست؟`
  - H2 `مقایسه‌ی کیف پول سرد و گرم` (a `<table>`: internet, speed, cost, fit)
  - H2 `انواع کیف پول سرد` · H3 `کیف پول سخت‌افزاری` · H3 `کیف پول کاغذی و فلزی` ·
    H3 `دستگاه همیشه آفلاین`
  - H2 `کدام برای چه کاری؟` (daily use vs long-term holding; no product ranking)
  - H2 `عبارت بازیابی را کجا نگه داریم؟` → `/learn/seed-phrase/`
  - H2 `خلاصه در ۵ قدم`
  - H2 `پرسش‌های پرتکرار`: «آیا تراست ولت کیف پول سرد است؟» (no: a software wallet on a phone
    is hot) · «عبارت بازیابی چند کلمه است؟» (usually 12 or 24) · «اگر کیف پول سخت‌افزاری گم شود
    چه می‌شود؟» · «آیا دارایی در صرافی در کیف پول سرد است؟»
  - منابع: the BIP-39 text (github.com/bitcoin/bips), ethereum.org/wallets
- **Links out:** glossary (کلید خصوصی، عبارت بازیابی، کیف پول گرم), `/learn/seed-phrase/`,
  `/learn/cex-vs-dex/`, `/learn/crypto-phishing/`; next: `/learn/seed-phrase/`.
  **In:** path step 5, glossary «کیف پول سرد»، «کیف پول گرم», security lessons, exchange pages
  (withdrawal section).

### 4.3 `/learn/bitcoin-halving/` (idea 5, basics)

- **Primary:** هاوینگ بیت کوین چیست · **Secondary:** هاوینگ یعنی چی، هاوینگ بعدی بیت کوین کی است،
  هاوینگ بیت کوین ۲۰۲۸، آخرین هاوینگ بیت کوین کی بود
- **title:** `هاوینگ بیت‌کوین چیست؟ هاوینگ بعدی کی است | دات‌کوین` (51)
- **description:** `هاوینگ بیت‌کوین یعنی نصف شدن پاداش استخراج در هر ۲۱۰٬۰۰۰ بلوک. تاریخچه‌ی هر چهار هاوینگ، هاوینگ بعدی حدود ۲۰۲۸، و اینکه هاوینگ چه چیزی را عوض می‌کند.` (149)
- **H1:** `هاوینگ بیت‌کوین یعنی چه؟`
- **Outline:**
  - پاسخ کوتاه (every 210,000 blocks, about four years, the new-coin reward per block halves)
  - H2 `پاداش استخراج چیست؟`
  - H2 `هاوینگ چطور کار می‌کند؟`
  - H2 `تاریخچه‌ی هاوینگ‌های بیت‌کوین`: a `<table>` (true dates):
    ۲۸ نوامبر ۲۰۱۲، بلوک ۲۱۰٬۰۰۰، ۵۰ → ۲۵ · ۹ ژوئیه‌ی ۲۰۱۶، بلوک ۴۲۰٬۰۰۰، ۲۵ → ۱۲٫۵ ·
    ۱۱ مه ۲۰۲۰، بلوک ۶۳۰٬۰۰۰، ۱۲٫۵ → ۶٫۲۵ · ۲۰ آوریل ۲۰۲۴ (۱ اردیبهشت ۱۴۰۳)، بلوک ۸۴۰٬۰۰۰،
    ۶٫۲۵ → ۳٫۱۲۵
  - H2 `هاوینگ بعدی بیت‌کوین کی است؟` (block 1,050,000; around 2028; the exact day depends on
    block times, so no exact date)
  - H2 `هاوینگ و سقف ۲۱ میلیون بیت‌کوین`
  - H2 `هاوینگ چه چیزی را عوض می‌کند؟` (new supply and miner income; history is not a price
    forecast: no price talk, owner rule)
  - H2 `خلاصه در ۵ قدم`
  - H2 `پرسش‌های پرتکرار`: «هاوینگ یعنی چه؟» · «آخرین هاوینگ بیت‌کوین کی بود؟» · «هاوینگ
    بعدی بیت‌کوین کی است؟» · «آیا آلت‌کوین‌ها هم هاوینگ دارند؟» (some, e.g. Litecoin; true) ·
    «بعد از آخرین هاوینگ چه می‌شود؟» (reward reaches zero around 2140; fees remain)
  - منابع: bitcoin.org/bitcoin.pdf, the Bitcoin Core source/BIP pages, a block explorer link
    for block 840,000
- **Links out:** glossary (استخراج، بلوک، ساتوشی), `/learn/bitcoin/`, `/learn/blockchain/`,
  `/learn/market-cap/`; next: `/learn/bitcoin/`. **In:** `/learn/bitcoin/`, glossary «هاوینگ».
- **Refresh:** quarterly, and on 2028 news (the "next halving" section is time-sensitive).

### 4.4 `/learn/stablecoin/` (idea 4, basics)

- **Primary:** استیبل کوین چیست · **Secondary:** استیبل کوین یعنی چه، استیبل کوین های معروف، تتر
  چیست، آیا تتر همان دلار است، استیبل کوین تتر با چه ارزی نسبت ثابت دارد، استیبل کوین طلا
- **title:** `استیبل‌کوین چیست؟ تتر و انواع ارز پایدار | دات‌کوین` (51)
- **description:** `استیبل‌کوین چیست و چرا قیمتش ثابت می‌ماند؟ پشتوانه و بازخرید، انواع استیبل‌کوین، تتر و USDC، آیا تتر همان دلار است و ریسک‌ها به زبان ساده.` (138)
- **H1:** `استیبل‌کوین چیست و چرا قیمتش ثابت می‌ماند؟`
- **Outline:**
  - پاسخ کوتاه (a token built to stay at one dollar, held there by reserves and redemption)
  - H2 `چرا به استیبل‌کوین نیاز داریم؟`
  - H2 `قیمت استیبل‌کوین چطور ثابت می‌ماند؟` (reserves, mint and redeem, arbitrage, plainly)
  - H2 `انواع استیبل‌کوین` · H3 `با پشتوانه‌ی دلار و اوراق` · H3 `با پشتوانه‌ی ارز دیجیتال` ·
    H3 `الگوریتمی` · H3 `با پشتوانه‌ی طلا`
  - H2 `استیبل‌کوین‌های شناخته‌شده`: USDT (Tether), USDC (Circle), DAI; facts only, no market
    figures
  - H2 `آیا تتر همان دلار است؟`
  - H2 `ریسک‌های استیبل‌کوین` (depeg; UST in May 2022 as the factual example; issuer and
    freeze risk) → this is teaching content, not a disclaimer
  - H2 `تتر روی کدام شبکه‌ها است؟` → `/learn/usdt-networks/`
  - H2 `خلاصه در ۵ قدم`
  - H2 `پرسش‌های پرتکرار`: «استیبل‌کوین یعنی چه؟» · «تتر چیست؟» · «آیا تتر همان دلار است؟» ·
    «استیبل‌کوین تتر با چه ارزی نسبت ثابت دارد؟» · «استیبل‌کوین طلا چیست؟»
  - منابع: tether.to transparency page, circle.com USDC page, the issuers' own docs
- **Links out:** glossary (تتر، شبکه، توکن), `/learn/coin-vs-token/`, `/learn/usdt-networks/`,
  `/learn/wrong-network/`, `/exchanges/` (one contextual link in the networks section);
  next: `/learn/usdt-networks/`. **In:** path step 4, glossary «استیبل‌کوین»، «تتر», exchange pages.

## 5. The next 30 lessons, by search opportunity

From the 40 remaining ideas in `ideas.json` (ids 1, 4, 5, 9 are §4). Order = P1 by signal, then
P2. **The reel picker decides the real order** (pillar rotation); this list is the recommended
order if the bank is reordered, and the priority each lesson gets when it is refreshed. Signals
as in KEYWORDS.md (suggest evidence, no volumes). Every lesson follows §3.3 and ARTICLE_BRIEF.md.

| # | Idea | Slug | Primary query | Secondary | Signal | P | `<title>` (chars) |
|---|---|---|---|---|---|---|---|
| 1 | 2 | `bitcoin` | بیت کوین چیست | بیت کوین چیست به زبان ساده، چرا بیت کوین ارزش دارد، فرق بیت کوین و اتریوم، سقف ۲۱ میلیون | strong | P1 | بیت‌کوین چیست؟ به زبان ساده و با یک مثال \| دات‌کوین (51) |
| 2 | 20 | `usdt-networks` | تتر trc20 | کارمزد شبکه trc20، کارمزد شبکه ترون، شبکه ترون همون trc20 است، تتر bep20 | strong | P1 | تتر را با کدام شبکه بفرستیم؟ TRC20، BEP20 یا ERC20 (50) |
| 3 | 3 | `coin-vs-token` | تفاوت کوین و توکن | کوین و توکن چیست، تفاوت کوین و توکن به زبان ساده | strong | P1 | تفاوت کوین و توکن به زبان ساده \| دات‌کوین (41) |
| 4 | 8 | `seed-phrase` | سید فریز چیست | عبارت بازیابی چند کلمه است، عبارت بازیابی کیف پول | medium–strong | P1 | عبارت بازیابی (سید فریز) چیست و کجا نگهش داریم؟ (47) |
| 5 | 6 | `market-cap` | مارکت کپ چیست | مارکت کپ ارزهای دیجیتال، ارزش بازار | strong | P1 | مارکت کپ چیست؟ ارزش بازار را درست بخوان \| دات‌کوین (50) |
| 6 | 18 | `stop-loss` | استاپ لاس چیست | استاپ لاس یعنی چی، حد ضرر، استاپ لاس در ترید | strong | P1 | استاپ لاس (حد ضرر) چیست؟ به زبان ساده \| دات‌کوین (48) |
| 7 | 29 | `leverage` | لوریج چیست | لیکویید شدن یعنی چی، لوریج در ترید | strong | P1 | لوریج چیست و لیکویید شدن یعنی چه؟ \| دات‌کوین (44) |
| 8 | 30 | `fear-and-greed-index` | شاخص ترس و طمع | شاخص ترس و طمع کریپتو، … بیت کوین، … چیست | strong | P1 | شاخص ترس و طمع کریپتو چیست؟ \| دات‌کوین (38) |
| 9 | 31 | `bitcoin-dominance` | دامیننس بیت کوین | دامیننس چیست، دامیننس تتر | strong | P1 | دامیننس بیت‌کوین چیست؟ به زبان ساده \| دات‌کوین (46) |
| 10 | 32 | `staking` | استیکینگ چیست | استیکینگ ارز دیجیتال، استیکینگ تتر | strong | P1 | استیکینگ چیست؟ پاداش، دوره‌ی قفل و ریسک‌ها \| دات‌کوین (53) |
| 11 | 44 | `airdrop` | ایردراپ چیست | ایردراپ های معتبر، نشانه‌ی ایردراپ واقعی | strong | P1 | ایردراپ چیست؟ نشانه‌های ایردراپ واقعی \| دات‌کوین (48) |
| 12 | 23 | `support-resistance` | حمایت و مقاومت چیست | حمایت و مقاومت در ترید | strong (shared with gold/forex) | P1 | حمایت و مقاومت چیست؟ با یک نمودار ساده \| دات‌کوین (49) |
| 13 | 24 | `candlestick` | کندل شناسی | کندل دوجی، نمودار شمعی | strong | P1 | کندل‌شناسی به زبان ساده؛ یک کندل را بخوان \| دات‌کوین (52) |
| 14 | 19 | `wrong-network` | انتخاب اشتباه شبکه انتقال ارز دیجیتال | چطور ارز دیجیتال را به کیف پول انتقال دهیم | medium | P2 | انتخاب شبکه‌ی اشتباه در انتقال ارز دیجیتال \| دات‌کوین (53) |
| 15 | 16 | `cex-vs-dex` | صرافی غیرمتمرکز | صرافی متمرکز و غیرمتمرکز | medium–strong | P2 | صرافی متمرکز و غیرمتمرکز چه فرقی دارند؟ \| دات‌کوین (50) |
| 16 | 17 | `market-vs-limit-order` | سفارش لیمیت چیست | سفارش مارکت، استاپ لیمیت | medium | P2 | سفارش مارکت و لیمیت چه فرقی دارند؟ \| دات‌کوین (45) |
| 17 | 42 | `whitepaper` | وایت پیپر چیست | وایت پیپر بیت کوین | medium | P2 | وایت‌پیپر چیست و چه چیزی را در آن بخوانیم؟ (42) |
| 18 | 26 | `fomo-fud` | فومو چیست | فومو در ترید، فاد چیست | medium | P2 | فومو و فاد چیست؟ تصمیم با برنامه \| دات‌کوین (43) |
| 19 | 27 | `dca` | استراتژی dca چیست | خرید پله ای ارز دیجیتال | medium | P2 | DCA یا خرید پله‌ای ارز دیجیتال چیست؟ \| دات‌کوین (47) |
| 20 | 28 | `risk-management` | مدیریت ریسک و سرمایه | اندازه‌ی پوزیشن | medium (generic) | P2 | مدیریت ریسک در ارز دیجیتال با یک قانون \| دات‌کوین (49) |
| 21 | 7 | `network-fee` | کارمزد شبکه | گس فی، کارمزد شبکه اتریوم، کارمزد شبکه بیت کوین | medium | P2 | کارمزد شبکه (گس فی) چیست و به چه بستگی دارد؟ (44) |
| 22 | 33 | `liquidity-pool` | استخر نقدینگی چیست | — | medium | P2 | استخر نقدینگی چیست؟ به زبان ساده \| دات‌کوین (43) |
| 23 | 11 | `crypto-phishing` | فیشینگ ارز دیجیتال | فیشینگ ارز دیجیتال چیست | weak–medium, high value | P2 | فیشینگ ارز دیجیتال چیست و چطور بشناسیمش؟ (40) |
| 24 | 40 | `is-bitcoin-anonymous` | آیا بیت کوین قابل ردیابی است | بیت کوین ناشناس | medium | P2 | آیا بیت‌کوین ناشناس است و قابل ردیابی است؟ (42) |
| 25 | 39 | `cheap-coin-myth` | ارز ارزان | ارز ارزان آینده دار (answered as reasoning, never picks) | strong, intent mismatch | P2 | ارز ارزان یعنی سود بیشتر؟ یک باور غلط \| دات‌کوین (48) |
| 26 | 21 | `p2p-trading` | پی تو پی ارز دیجیتال | p2p چیست (other meanings win) | weak | P2 | معامله‌ی P2P (پی‌تو‌پی) ارز دیجیتال چیست؟ \| دات‌کوین (52) |
| 27 | 22 | `exchange-fees` | کارمزد صرافی ارز دیجیتال | کارمزد weex، کارمزد lbank، اسپرد | medium | P2 | کارمزدهای صرافی ارز دیجیتال: معامله، برداشت، اسپرد (50) |
| 28 | 36 | `layer-2` | لایه دوم اتریوم | لایه دوم بیت کوین | medium | P2 | لایه دوم (Layer 2) چیست؟ به زبان ساده \| دات‌کوین (48) |
| 29 | 35 | `crypto-bridge` | بریج ارز دیجیتال چیست | سایت بریج ارز دیجیتال | medium | P2 | بریج ارز دیجیتال چیست؟ پل بین شبکه‌ها \| دات‌کوین (48) |
| 30 | 25 | `trading-volume` | حجم معاملات چیست | حجم معاملات ارز دیجیتال | medium (shared with bourse) | P2 | حجم معاملات در ارز دیجیتال چه می‌گوید؟ \| دات‌کوین (49) |

**The other 10 ideas (P3: thin search demand; their reels still become lessons, kept short and
linked hard from the glossary and the related P1/P2 lesson):**
10 `wallet-security-mistakes` (→ seed-phrase), 12 `fake-airdrop` (→ airdrop; target «ایردراپ
جعلی», never «ایردراپ چیست»), 13 `token-approval`, 14 `address-poisoning`, 15
`two-factor-authentication` (other meanings win), 34 `impermanent-loss` (→ liquidity-pool), 37
`oracle` (other meanings win), 38 `crypto-crime-myth`, 41 `ath-atl`, 43 `tvl`.

**Cannibalisation pairs (one owner each):** cold-wallet ↔ seed-phrase (wallets vs the words);
usdt-networks ↔ wrong-network ↔ network-fee (which network / the mistake / the fee mechanism);
airdrop ↔ fake-airdrop; stablecoin ↔ usdt-networks (what tether is / how to send it);
exchange-fees ↔ the fee section of each exchange page (general vs that exchange).

## 6. Lessons the bank does not have yet (recommended additions)

High-signal queries with no idea in the bank. Adding them is the owner's / hub's call; each
would be a cornerstone lesson:
1. `/learn/cryptocurrency/`: «ارز دیجیتال چیست به زبان ساده» (A2, strong; the site's biggest gap)
2. `/learn/how-to-buy-crypto/`: «چطور ارز دیجیتال بخریم» (C6) → the natural bridge to `/exchanges/`
3. `/learn/tether/`: «تتر چیست» (strong; today a section of `/learn/stablecoin/`; split only
   when the stablecoin lesson ranks)
4. `/learn/ethereum/`: «اتریوم چیست» (expected strong; not checked in this research)
5. `/learn/crypto-wallet/`: «کیف پول ارز دیجیتال چیست» (strong; general wallet lesson above
   cold-wallet)
