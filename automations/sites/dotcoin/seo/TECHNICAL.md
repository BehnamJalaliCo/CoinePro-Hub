# dotcoin.me: technical SEO

Static site from `build.py` → `dist/` → Cloudflare Pages, zone `dotcoin.me` on Cloudflare
(nameservers checked 2026-11-17: `junade` / `lara.ns.cloudflare.com`; no A/AAAA records yet).
Pages behaviour quoted from developers.cloudflare.com/pages/configuration/{serving-pages,headers}.

## 1. URLs, canonical, trailing slash

- **Canonical host:** `https://dotcoin.me` (apex, HTTPS). Everything else redirects there (§2).
- **Every page is `dir/index.html` in `dist/`** and is linked as `/dir/` with the trailing slash:
  `/`, `/learn/`, `/learn/cold-wallet/`, `/glossary/`, `/exchanges/weex/`, `/about/`.
  Files stay files: `/sitemap.xml`, `/robots.txt`, `/feed.xml`, `/img/…`.
- Pages already redirects `/x.html` → `/x` and `/x/index.html` → `/x/`; the build must not
  create `x.html` files next to `x/index.html`. Check that `/learn/cold-wallet` (no slash)
  redirects to `/learn/cold-wallet/` (CHECKLIST §2); links never rely on it.
- **`<link rel="canonical">`** on every indexable page: absolute, self-referencing, the exact
  slash form: `<link rel="canonical" href="https://dotcoin.me/learn/cold-wallet/">`. Query
  strings (`?utm_…`, `?igsh=…` from Instagram) are dropped from the canonical.
- The canonical, `og:url`, the sitemap `<loc>`, the JSON-LD `url`/`@id` and every internal link
  use the same string. Heading ids are ASCII (`id="faq"`) so fragments are not `%`-encoded.
- No pagination, no tag pages, no date archives, no `?page=`.

## 2. Hosts and redirects

| Request | Result | How |
|---|---|---|
| `http://…` | 301 → `https://…` | Cloudflare SSL/TLS → Edge Certificates → **Always Use HTTPS: on** |
| `https://www.dotcoin.me/<path>?<q>` | **301** → `https://dotcoin.me/<path>?<q>` | Rules → **Redirect Rules** (Single Redirect): `http.host eq "www.dotcoin.me"` → dynamic `concat("https://dotcoin.me", http.request.uri.path)`, 301, preserve query string. DNS: `www` CNAME → `dotcoin.me`, **proxied** (orange cloud), or the rule never runs. `_redirects` cannot do host-level redirects. |
| `https://<project>.pages.dev/<path>` | 301 → `https://dotcoin.me/<path>` | Account → **Bulk Redirects**: source `<project>.pages.dev`, target `https://dotcoin.me`, subpath matching + preserve path suffix + preserve query string, **without** "include subdomains" (so preview builds still work). Belt and braces: the `X-Robots-Tag: noindex` rule in `_headers` (§6). |
| `<hash>.<project>.pages.dev` previews | `X-Robots-Tag: noindex` | Pages does this itself. |

## 3. The `<head>` of every page

```html
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>…</title>
<meta name="description" content="…">
<link rel="canonical" href="https://dotcoin.me/…/">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<link rel="preload" href="/fonts/yekan-400.woff2" as="font" type="font/woff2" crossorigin>
<style>/* all critical CSS inline */</style>
<meta property="og:type" content="article">          <!-- "website" on non-lessons -->
<meta property="og:site_name" content="دات‌کوین">
<meta property="og:locale" content="fa_IR">
<meta property="og:title" content="…">               <!-- the title without the suffix -->
<meta property="og:description" content="…">
<meta property="og:url" content="https://dotcoin.me/…/">
<meta property="og:image" content="https://dotcoin.me/img/learn/<slug>-1200x630.jpg">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="…">
<meta property="article:published_time" content="2026-11-18T12:00:00+03:30">   <!-- lessons -->
<meta property="article:modified_time" content="2026-11-18T12:00:00+03:30">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="alternate" type="application/atom+xml" title="دات‌کوین" href="/feed.xml">
<meta name="theme-color" content="#F3C242">
<script type="application/ld+json">{ "@context":"https://schema.org", "@graph":[ … ] }</script>
</head>
```

- `lang="fa"` and `dir="rtl"` on `<html>`; Latin runs inside Persian (`TRC20`, wallet
  addresses) in `<bdi>` or `<span dir="ltr">`, so punctuation does not jump.
- JSON-LD `inLanguage`: `"fa"` (same as `lang`). No `hreflang` (one language, one URL each).
- Times: ISO 8601 with `+03:30` (Iran has had no DST since 2022). Visible dates are Jalali
  inside `<time datetime="2026-11-18">۲۷ آبان ۱۴۰۵</time>`.
- **OG image:** 1200×630 JPG, ≤ 300 KB, absolute URL, one per lesson (made from the cover art
  with the Persian title readable at phone size), a site default for other pages. JPG because
  Telegram, WhatsApp and Instagram DM previews are where these links travel.
- Meta keywords: not used (ignored by Google and Bing).
- JSON-LD types and nodes per page: PAGE_PLAN.md §2–§3.

## 4. sitemap.xml, robots.txt, feed

**`/sitemap.xml`:** generated by `build.py` from the pages it writes.
- Only indexable, canonical, status-200 URLs: `/`, `/learn/`, every lesson, `/glossary/`,
  `/exchanges/` and the three exchange pages, `/about/`. Never `404.html`, `/go/…`, images.
- `<lastmod>` = the page's `updated` date (`YYYY-MM-DD`), only moved by a real content change
  (ARTICLE_BRIEF §8). `/` and `/learn/` take the newest lesson's date. No `<changefreq>` or
  `<priority>` (Google ignores both).
- One file until 50,000 URLs. Submitted once in Search Console and Bing (§10); Google retired the
  sitemap ping endpoint in 2023, so no pings.

**`/robots.txt`:**
```
User-agent: *
Disallow: /go/

Sitemap: https://dotcoin.me/sitemap.xml
```
Check after every Cloudflare change that the served file is ours: Cloudflare's "managed
robots.txt" and AI-crawler blocking (Security → Bots / AI Crawl Control) can prepend or change
it. Search engines must be allowed; whether AI training crawlers are allowed is the owner's
setting (default here: allow, an educational site gains from being cited).

**`/feed.xml`:** Atom, the 20 newest lessons (title, link, `updated`, summary). Feed readers
use it, Google accepts it as a second sitemap, Bing picks up new URLs from it.

## 5. 404

- `dist/404.html` **must exist.** Without a top-level `404.html` Pages assumes a single-page
  app and answers every unknown path with the home page and status 200 (soft 404s, duplicate
  home pages in the index).
- With it, Pages serves it with status 404. The page: `<meta name="robots" content="noindex">`,
  no canonical, no JSON-LD, the site header, H1 «این صفحه پیدا نشد», links to `/`, `/learn/`,
  `/glossary/`, `/exchanges/` and the 6 newest lessons.
- Removed pages: a 301 to the closest page in `_redirects` (not a 404) when a close page exists.

## 6. Cloudflare Pages files: `_headers` and `_redirects`

Both go in `dist/` (copied from `static/` by the build). Pages limits: 100 header rules,
2,000 characters per line; `_redirects` up to 2,000 static and 100 dynamic rules; a matching
redirect wins over headers.

**`_headers`:**
```
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  X-Frame-Options: DENY

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/fonts/*
  Cache-Control: public, max-age=31536000, immutable

/img/*
  Cache-Control: public, max-age=2592000

https://:project.pages.dev/*
  X-Robots-Tag: noindex
```
- `/assets/*` (CSS/JS) must have content-hashed names (`site.3f9a1c.css`) for `immutable` to
  be safe. Fonts: their names change when the file changes (`yekan-400.v2.woff2`), or move them
  to `/fonts/v1/…`.
- HTML, `sitemap.xml`, `robots.txt`, `feed.xml`: keep Pages' default (`max-age=0,
  must-revalidate` + ETag), so a new lesson is live at once and still costs a 304 at most.
- Optional (phase 2, after checking nothing breaks):
  `Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'self' https://static.cloudflareinsights.com; connect-src 'self' https://cloudflareinsights.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
  (JSON-LD blocks are data, CSP does not block them.)

**`_redirects`:**
```
# referral links: one place to change a code; robots.txt keeps /go/ out of the index
/go/weex/    <WEEX referral URL from the owner>    302
/go/weex     <WEEX referral URL from the owner>    302
/go/lbank/   <LBank referral URL from the owner>   302
/go/lbank    <LBank referral URL from the owner>   302
/go/ourbit/  <Ourbit referral URL from the owner>  302
/go/ourbit   <Ourbit referral URL from the owner>  302
# moved lessons (ARTICLE_BRIEF §6): /learn/<old>/ /learn/<new>/ 301
```
- Every referral button: `<a href="/go/weex/" rel="sponsored nofollow noopener" target="_blank">`.
  `rel="sponsored"` is what Google's link-spam policy asks of affiliate links.

**Dashboard settings (zone dotcoin.me):**
- SSL/TLS: Full (strict); Always Use HTTPS on; Minimum TLS 1.2; HSTS on only after a week of
  clean HTTPS (`max-age=15552000`, no `preload` at first).
- Speed: Brotli and HTTP/3 on; **Early Hints on** (Pages turns the `<link rel="preload">` tags
  into `Link` headers by itself); **Rocket Loader off** (it rewrites scripts and delays them);
  minify in `build.py` (Cloudflare's Auto Minify is retired).
- Scrape Shield: Email Address Obfuscation off (it injects a script; the site shows no email).
- Caching → **Crawler Hints on** (tells Bing and Yandex about changed URLs through IndexNow).
- Bots: Bot Fight Mode off, or confirmed not to challenge verified bots (Googlebot, Bingbot).
  No "I'm Under Attack" or challenge rules on `/*`.
- Analytics: Cloudflare Web Analytics for the Pages project (no cookies, so no cookie banner).
- No Page Rule / Cache Rule "Cache Everything" is needed: Pages serves from its own edge store.

## 7. Persian typography (text that search engines read)

The build normalises every human-readable string: body text, `<title>`, meta description, OG
tags, `alt`, JSON-LD strings, the glossary. A build check fails on the "bad" column in `dist/`.

| Bad | Good | Note |
|---|---|---|
| `ي` U+064A, `ى` U+0649 | `ی` U+06CC | Arabic yeh → Persian yeh |
| `ك` U+0643 | `ک` U+06A9 | Arabic kaf → Persian keheh |
| `٠–٩` U+0660–0669, ASCII digits in prose | `۰–۹` U+06F0–06F9 | keep ASCII in URLs, code, tickers/network names (TRC20), JSON-LD numbers and dates, HTML attributes |
| `21,000,000` / `3.125` in prose | `۲۱٬۰۰۰٬۰۰۰` / `۳٫۱۲۵` | `٬` U+066C thousands, `٫` U+066B decimal |
| `ۀ` U+06C0 | `ه‌ی` | house style, as in the reels' text («کلمه‌ی») |
| `ـ` U+0640 tatweel | (removed) | |
| `,` `;` `?` `"…"` in Persian text | `،` `؛` `؟` `«…»` | |
| `می خواهم`, `کتاب ها`, `بزرگ ترین` | `می‌خواهم`, `کتاب‌ها`, `بزرگ‌ترین` | ZWNJ U+200C after می/نمی, before ها/های، تر/ترین، ای/ام after silent ه |
| ZWNJ doubled, next to a space, or at a word's end; stray U+200E/U+200F | (removed) | use `<bdi>` for mixed-direction runs instead of marks |
| double spaces, space before `،` `؛` `؟` | single space, none | |

- Slugs: ASCII only (ARTICLE_BRIEF §6), so ی/ک never reach a URL. If a search box is ever
  added, apply the same table to the query before matching.
- Search engines match ZWNJ and space forms of most words; joined forms («بلاکچین») are
  handled by the glossary line (KEYWORDS.md, spelling policy). After launch, compare the forms
  in Search Console's queries report and adjust titles if one form clearly dominates.

## 8. Speed: the Core Web Vitals budget

Targets (lab: Lighthouse mobile, simulated slow 4G; field: Search Console CWV report / CrUX
p75 once traffic exists):

| Metric | Budget |
|---|---|
| LCP | **< 2.0 s** on 4G mobile |
| CLS | **< 0.05** |
| INP | < 200 ms (the site has almost no JS) |
| TTFB | < 0.4 s (Pages edge) |
| Lighthouse mobile | Performance ≥ 95, SEO 100, Accessibility ≥ 95, Best Practices 100 |

Weight budget for a lesson's first view (compressed):

| Resource | Budget |
|---|---|
| HTML | ≤ 35 KB |
| CSS | ≤ 15 KB, inlined in `<style>` (no render-blocking stylesheet request) |
| Fonts | ≤ 2 files on first view, ≤ 50 KB together |
| Hero image | ≤ 100 KB on a phone (the 800w variant) |
| Own JS | 0 KB target, ≤ 5 KB if a menu needs it; plus the Cloudflare analytics beacon |
| Total | ≤ 250 KB |

**Fonts (IRANYekanX Pro, woff2):**
- The repo's files are already subset (22–24 KB each). Keep the subset: Arabic block
  U+0600–06FF (Persian letters, `؟ ، ؛ ٫ ٬`), Persian digits U+06F0–06F9, ZWNJ U+200C,
  `« »`, basic Latin for tickers. Declare it as `unicode-range` in each `@font-face`.
- `font-display: swap` on every `@font-face`.
- Use 2 weights on normal pages (400 body, 800 headings); 300/600/950 only where a page really
  uses them (an unused `@font-face` costs nothing; never preload it).
- Preload `yekan-400.woff2` on every page; preload the heading weight too only if the H1 is the
  LCP element (lessons without a hero image). Never preload Anton (the giant English words
  appear only on some pages).
- A metric-matched fallback (`@font-face` on `local("Tahoma")` with `size-adjust` /
  `ascent-override` / `descent-override`, values measured in phase 2) so the swap does not move
  the layout (CLS).

**Images:** AVIF or WebP with `srcset` (480w, 800w, 1200w) and `sizes`; `width`/`height` on
every `<img>`; the hero is the LCP element: `fetchpriority="high"`, never lazy; the rest
`loading="lazy" decoding="async"`. The reel block is a poster image + link, never an iframe.

**Never on the site:** Instagram/YouTube/X embeds, Google Fonts, jQuery, tag managers,
chat widgets, cookie banners (no cookies are set), `document.write`, client-side rendering of
content.

## 9. E-E-A-T (crypto is a "your money" topic: Google applies its highest quality bar)

- **Who:** every lesson has a byline «نوشته‌ی بهنام جلالی» → `/about/`, and the Person node
  in JSON-LD (`url` /about/, `sameAs` the Instagram page). `/about/` holds **only facts the
  owner gives or confirms** (PAGE_PLAN §3.7); nothing is invented to look authoritative.
- **When:** visible «انتشار» and «بازبینی» dates that match `datePublished` / `dateModified`;
  `dateModified` only moves for real changes (ARTICLE_BRIEF §8).
- **How we know:** each lesson ends with 1–3 primary sources; exchange facts carry a «بررسی‌شده
  در» date and a link to the official page.
- **Who pays:** `/about/` says in one plain sentence that the exchange buttons are referral
  links (owner's call); the links carry `rel="sponsored"`.
- **Consistency:** the same name, photo and Instagram link everywhere (site, schema, IG bio
  link → `https://dotcoin.me/`).
- **Disambiguation:** «دات‌کوین (dotcoin.me) یک سایت آموزشی است، نه یک توکن» on `/about/`
  (the Dotcoin DTC game token owns the brand query today; KEYWORDS F1).

## 10. Google Search Console and Bing Webmaster Tools

The owner signs in (his Google account owns the property). The hub adds the DNS records
through the Cloudflare API, so the owner never opens Cloudflare.

### 10.1 What the owner does (Persian, as it will be sent to him)

**گوگل سرچ کنسول (یک بار، حدود ۵ دقیقه):**
۱. این لینک را باز کن: https://search.google.com/search-console/welcome و با همان جیمیلی وارد شو
   که می‌خواهی سایت به نامش باشد.
۲. در کادر «Domain» بنویس `dotcoin.me` (بدون https و بدون www) و «Continue» را بزن.
۳. یک متن نشان می‌دهد که با `google-site-verification=` شروع می‌شود. دکمه‌ی «Copy» کنارش را بزن.
۴. همان متن را در جلسه بفرست. این متن رمز نیست؛ فقط ثابت می‌کند دامنه مال توست.
۵. هاب آن را در DNS سایت می‌گذارد و در جلسه خبر می‌دهد.
۶. بعد از خبر هاب، «Verify» را بزن. اگر پنجره را بسته بودی، دوباره همان لینک، همان
   `dotcoin.me` و «Verify». اگر پیدا نکرد، نیم ساعت بعد دوباره بزن.
۷. بعد از تأیید: در منوی کنار، «Sitemaps» را بزن، در کادر بنویس `sitemap.xml` و «Submit» را بزن.
۸. (اختیاری) اگر می‌خواهی هاب هر ماه گزارش جست‌وجو را خودش بخواند و درس‌ها را به‌روز کند:
   «Settings» ← «Users and permissions» ← «Add user»، نشانی‌ای را که هاب در جلسه می‌دهد بنویس،
   دسترسی «Restricted» و «Add».

**بینگ (بعد از گوگل، حدود ۲ دقیقه):**
۱. این لینک را باز کن: https://www.bing.com/webmasters و «Sign in» ← «Google» را بزن و با
   همان جیمیل وارد شو.
۲. گزینه‌ی «Import your sites from GSC» ← «Import» را بزن، اجازه بده، `dotcoin.me` را تیک بزن و
   «Import» را بزن. تمام؛ سایت‌مپ هم خودش می‌آید.
۳. فقط اگر این راه نشد: «Add your site manually» ← `https://dotcoin.me/` ← روش «DNS
   Verification». دو مقدار نشان می‌دهد (نام و مقصد)؛ هر دو را در جلسه بفرست. بعد از خبر هاب
   «Verify» را بزن.

### 10.2 What the hub does

- Token: a Cloudflare API token with **Zone → DNS → Edit** on the zone `dotcoin.me` only, read
  from the vault by name; never printed.
- Google (TXT on the apex; keep it forever, removing it un-verifies the property):
  ```
  curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
    -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
    --data '{"type":"TXT","name":"dotcoin.me","content":"\"google-site-verification=<value>\"","ttl":3600,"comment":"Google Search Console"}'
  ```
- Bing (only if the import fails): `{"type":"CNAME","name":"<name from Bing>","content":"verify.bing.com","proxied":false,"ttl":3600,"comment":"Bing Webmaster Tools"}`.
- Check before telling the owner: `dig +short TXT dotcoin.me @1.1.1.1` (and `@8.8.8.8`) shows
  the value; then tell him to press «Verify».
- After verification: URL Inspection → «Request indexing» for `/`, `/learn/`, the first 4
  lessons and `/exchanges/` (the owner can do this, or the hub through the Search Console API if
  step ۸ was done).

## 11. Watching it

- Search Console weekly for the first month: Pages report (indexed / not indexed and why), CWV
  report, the queries per lesson (ARTICLE_BRIEF §8 triggers). Then monthly.
- Bing Webmaster Tools: Site Scan once after launch; IndexNow submissions (from Crawler Hints).
- PageSpeed Insights on `/`, one lesson and one exchange page after every template change.
