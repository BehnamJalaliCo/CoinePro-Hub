# dotcoin.me: the SEO acceptance checklist

Run in phase 2 on the builder's `dist/` and on the live https://dotcoin.me, then after every
template change. **M** = must pass before the site counts as done; **S** = should, reported
with a reason when it does not. Each item names the rule it checks.

Shorthands: `D=automations/sites/dotcoin/dist`, `U=https://dotcoin.me`.
`H() { curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "$1"; }`

## 1. Build output (`dist/`)

| ID | Check | Level | How |
|---|---|---|---|
| 1.1 | Every page is `<dir>/index.html`; no `x.html` next to `x/index.html` | M | `find $D -name '*.html' ! -name index.html ! -name 404.html` → empty |
| 1.2 | `404.html`, `sitemap.xml`, `robots.txt`, `feed.xml`, `_headers`, `_redirects`, `favicon.ico`, `apple-touch-icon.png` at the root | M | `ls` |
| 1.3 | The pages of PAGE_PLAN §1 exist: `/`, `/learn/`, the published lessons, `/glossary/`, `/exchanges/` + 3, `/about/` | M | `ls` |
| 1.4 | No source files, drafts, `private/`, `.md`, keys or `.git` in `dist/` | M | `find $D -name '*.md' -o -name '.*'` → empty; gitleaks over `dist/` clean |

## 2. Live URLs and redirects (TECHNICAL §1–§2)

| ID | Request | Expected | Level |
|---|---|---|---|
| 2.1 | `H http://dotcoin.me/` | 301 → `https://dotcoin.me/` | M |
| 2.2 | `H https://www.dotcoin.me/learn/?a=1` | 301 → `https://dotcoin.me/learn/?a=1` | M |
| 2.3 | `H http://www.dotcoin.me/` | one or two hops, ends at `https://dotcoin.me/` | M |
| 2.4 | `H $U/learn/cold-wallet` (no slash) | 308/301 → `/learn/cold-wallet/` | M |
| 2.5 | `H $U/learn/cold-wallet/index.html` | redirect → `/learn/cold-wallet/` | M |
| 2.6 | `H $U/no-such-page/` | **404** (not 200, not the home page) | M |
| 2.7 | `H https://<project>.pages.dev/` | 301 → `https://dotcoin.me/`, or 200 with `X-Robots-Tag: noindex` | M |
| 2.8 | `H $U/go/weex/` (and lbank, ourbit, with and without slash) | 302 → the owner's referral URL | M |
| 2.9 | Every URL in `sitemap.xml` | 200, no redirect | M |

## 3. The head of every page (TECHNICAL §3, PAGE_PLAN §3)

| ID | Check | Level |
|---|---|---|
| 3.1 | `<html lang="fa" dir="rtl">`, `<meta charset="utf-8">`, viewport meta | M |
| 3.2 | Exactly one `<title>`, ≤ 60 chars, unique across the site; the lesson titles end with « \| دات‌کوین» when they fit | M |
| 3.3 | Exactly one meta description, 120–155 chars (404: any), unique across the site | M |
| 3.4 | `<link rel="canonical">` absolute, `https://dotcoin.me/…/`, equal to the page's own URL (404: none) | M |
| 3.5 | Robots meta: indexable pages `index, follow, max-image-preview:large…`; 404 `noindex` | M |
| 3.6 | Exactly one `<h1>`; heading levels never skip (H2 → H4) | M |
| 3.7 | OG: `og:type`, `og:title`, `og:description`, `og:url` (= canonical), `og:image` absolute 1200×630 (file exists), `og:image:alt`, `og:locale` `fa_IR`, `og:site_name`; `twitter:card` `summary_large_image` | M |
| 3.8 | Lessons: `article:published_time` / `article:modified_time` equal the JSON-LD dates | M |
| 3.9 | Favicon, apple-touch-icon, feed `<link rel="alternate">` present | S |
| 3.10 | Titles and descriptions follow PAGE_PLAN for the pages it lists (exact strings) | S |

## 4. Structured data (PAGE_PLAN §2–§3)

| ID | Check | Level |
|---|---|---|
| 4.1 | Every `application/ld+json` block parses as JSON | M |
| 4.2 | Types per page: home = Organization + WebSite + WebPage; `/learn/` = CollectionPage + ItemList + BreadcrumbList; lesson = WebPage + Article + BreadcrumbList (+ FAQPage when a FAQ is visible); `/glossary/` = DefinedTermSet + DefinedTerm + BreadcrumbList; `/exchanges/` = WebPage + ItemList + FAQPage + BreadcrumbList; exchange = WebPage + FAQPage + BreadcrumbList; `/about/` = AboutPage + Person + Organization + BreadcrumbList | M |
| 4.3 | **Forbidden anywhere:** Review, AggregateRating, Rating, HowTo, FinancialService, an Organization node for an exchange, SearchAction without a real search page | M |
| 4.4 | FAQPage questions and answers equal the visible FAQ text (same count, same words) | M |
| 4.5 | BreadcrumbList items equal the visible breadcrumb; the last item has no `item` URL or the page's own canonical | M |
| 4.6 | Article: `headline` ≤ 110 chars, `image` ≥ 1200 px wide and the file exists, `datePublished`/`dateModified` ISO 8601 with `+03:30`, `author` → Person with `url`, `publisher` → Organization with `logo` | M |
| 4.7 | `@id`s are stable and shared (`/#org`, `/#website`, `/about/#behnam`); the same node never carries different values on two pages | M |
| 4.8 | Google Rich Results Test passes (no errors) for `/`, one lesson, `/glossary/`, one exchange page; validator.schema.org shows no errors | S |

## 5. Links (ARTICLE_BRIEF §5)

| ID | Check | Level |
|---|---|---|
| 5.1 | Every internal `href` resolves to a page in `dist/` (fragments included: `/glossary/#<slug>` ids exist) | M |
| 5.2 | Internal links use the canonical form: leading `/`, trailing slash for pages, no `index.html`, no `https://dotcoin.me` prefix, no `?` | M |
| 5.3 | Every lesson is linked from `/learn/` and from at least one other lesson or the home page (no orphans) | M |
| 5.4 | Lessons have 3–8 contextual links in the body; glossary terms linked on first mention only (≤ 4) | S |
| 5.5 | No `/go/` link inside `/learn/` pages; every `/go/` link has `rel` containing `sponsored` and `nofollow` | M |
| 5.6 | No anchor text «اینجا», «کلیک کنید», «لینک»; no empty anchors | S |
| 5.7 | External links: `https`, live (200 after redirects); sources point to primary sites | S |
| 5.8 | Nav and footer links are plain `<a href>` in the HTML (no JS-built menus) | M |

## 6. Content (ARTICLE_BRIEF §4, the owner's rules)

| ID | Check | Level |
|---|---|---|
| 6.1 | Each lesson: lead, «پاسخ کوتاه» 40–60 words, byline with author link, visible «انتشار» date (and «بازبینی» when updated), the reel link, «خلاصه در ۵ قدم», FAQ 3–6 with answers 40–80 words, 1–3 sources, related lessons | M |
| 6.2 | 1,000–1,800 words per lesson (P3: ≥ 700) | S |
| 6.3 | Primary query in title, H1, answer box, first 100 words, one H2 | S |
| 6.4 | No price numbers, predictions or signals: regex over text for `\$\s?[0-9۰-۹]`, `[0-9۰-۹][0-9۰-۹٬,]* ?دلار`, «پیش‌بینی قیمت», «سیگنال» → each hit reviewed by hand (history tables like the halving rewards are fine) | M |
| 6.5 | No disclaimer lines: «سلب مسئولیت», «توصیه‌ی مالی نیست», «مسئولیت … با خود» → none | M |
| 6.6 | `/about/` contains only owner-confirmed facts; the "not a token" line is there | M |
| 6.7 | Exchange pages: facts table with «بررسی‌شده در» date; the countries section quotes and links the official terms; no instructions to get around country rules or KYC | M |
| 6.8 | No duplicate or near-duplicate pages (two lessons owning the same primary query, PAGE_PLAN §5 pairs) | S |

## 7. Persian typography (TECHNICAL §7), over the text of every `dist/*.html`

| ID | Check | Level |
|---|---|---|
| 7.1 | No `ي` U+064A, `ى` U+0649, `ك` U+0643 anywhere (text, attributes, JSON-LD) | M |
| 7.2 | No Arabic-Indic digits U+0660–0669; no ASCII digits in Persian prose (allowed: URLs, code, tickers/network names, JSON-LD, attributes) | M |
| 7.3 | No tatweel U+0640; no `ۀ` U+06C0 | M |
| 7.4 | No doubled ZWNJ, no ZWNJ next to a space or at a word's end; no stray U+200E/U+200F | M |
| 7.5 | `«»`, `،`, `؛`, `؟` in Persian text; no space before them; no double spaces | S |
| 7.6 | Common ZWNJ forms right: `می‌`, `‌ها`, `‌ترین`, `‌ی` after silent ه (sample of 3 pages by eye) | S |

## 8. Images (ARTICLE_BRIEF §7)

| ID | Check | Level |
|---|---|---|
| 8.1 | Every `<img>` has `alt` (empty only for decorative), `width`, `height` | M |
| 8.2 | Alt text Persian, ≤ 125 chars, no «تصویر»/«عکس» prefix, not keyword-stuffed | S |
| 8.3 | The LCP image (hero) has `fetchpriority="high"` and no `loading="lazy"`; others lazy | M |
| 8.4 | `og:image` files 1200×630, ≤ 300 KB; Article image ≥ 1200 px wide | M |
| 8.5 | Page images WebP/AVIF with `srcset`/`sizes`; hero ≤ 100 KB at 800w | S |
| 8.6 | No Instagram/YouTube iframe or embed script | M |

## 9. Speed (TECHNICAL §8)

| ID | Check | Level |
|---|---|---|
| 9.1 | PageSpeed Insights, mobile, for `/`, one lesson, one exchange page: LCP < 2.0 s, CLS < 0.05, TBT < 100 ms | M |
| 9.2 | Lighthouse mobile: Performance ≥ 95, SEO = 100, Accessibility ≥ 95, Best Practices = 100 | S |
| 9.3 | Weight of a lesson's first view ≤ 250 KB; HTML ≤ 35 KB; CSS inline ≤ 15 KB; own JS ≤ 5 KB | S |
| 9.4 | Fonts: `font-display: swap` in every `@font-face`; `yekan-400.woff2` preloaded with `crossorigin`; ≤ 2 font files on first view; Anton never preloaded | M |
| 9.5 | No request to a third-party host except `static.cloudflareinsights.com` / `cloudflareinsights.com` | M |
| 9.6 | No render-blocking `<link rel="stylesheet">` or `<script>` without `defer`/`async` in `<head>` | S |

## 10. Sitemap, robots, feed (TECHNICAL §4)

| ID | Check | Level |
|---|---|---|
| 10.1 | `sitemap.xml` is valid XML, lists exactly the indexable pages (= the set of canonicals), absolute `https://dotcoin.me/…/` URLs | M |
| 10.2 | `<lastmod>` `YYYY-MM-DD` = each page's `updated`; no `changefreq`/`priority` | M |
| 10.3 | `curl $U/robots.txt` = our file (Disallow `/go/`, the Sitemap line); nothing prepended by Cloudflare that blocks Googlebot or Bingbot | M |
| 10.4 | `feed.xml` valid Atom, the newest lessons, absolute links | S |

## 11. Headers (TECHNICAL §6)

| ID | Check | Level |
|---|---|---|
| 11.1 | `/`: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` (or CSP `frame-ancestors`) present | S |
| 11.2 | Hashed assets and fonts: `Cache-Control: public, max-age=31536000, immutable`; HTML: `max-age=0, must-revalidate` + ETag | M |
| 11.3 | `Content-Encoding: br` (or gzip) on HTML, CSS, XML | S |
| 11.4 | No `X-Robots-Tag: noindex` on `dotcoin.me` pages | M |

## 12. Search engines (after the owner's steps, TECHNICAL §10)

| ID | Check | Level |
|---|---|---|
| 12.1 | `dig +short TXT dotcoin.me` shows the `google-site-verification` record | M |
| 12.2 | Search Console: domain property verified; `sitemap.xml` submitted and "Success" | M |
| 12.3 | URL Inspection: the home page, one lesson and one exchange page "URL is available to Google"; the rendered HTML has the content and JSON-LD | M |
| 12.4 | Bing Webmaster Tools: site imported or verified; sitemap known; Crawler Hints on | S |
| 12.5 | After 14 days: Pages report shows no "Duplicate without user-selected canonical", no "Soft 404", no `pages.dev` URLs | S |

## Result

Report: one line per failed **M** item (ID, page, what, the fix) and the **S** items not met.
Phase 2 fixes every **M** on `server/dotcoin-site` before the site is called done.
