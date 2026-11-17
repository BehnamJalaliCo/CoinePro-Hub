# dotcoin.me — the site

Static site for DotCoin.me (crypto education in plain Persian, by Behnam Jalali), built by a
stdlib-only Python generator and deployed to Cloudflare Pages (project `dotcoin`, direct upload).

```
content/site.json            site-wide facts (name, URL, socials, "today" lesson, ideas bank path)
content/pages/*.md           the fixed pages: home, learn, glossary, exchanges, about, 404
content/articles/<slug>.md   one lesson per file (format: content/FORMAT.md)
content/glossary.txt         `slug | term | English | definition`, one per line
content/exchanges.json       THE one place for each exchange's link, code, button, logo
content/exchanges/<slug>.md  the exchange pages' text (SEO fields, features, steps, body, FAQ)
templates/base.html          the page shell (head, header, footer); templates/og.html = OG card
static/css/site.css          all styles (inlined into every page); every colour is a token
static/js/site.js            theme toggle, reveals, stepper, filters, live chain canvas
static/exchanges/            exchange logos, as downloaded from the official sites
tools/prep_assets.py         fonts -> woff2 subsets, logo -> sizes/favicons (into private/)
tools/render.py              headless Chromium: OG cards (dist/og/*.jpg) and review screenshots
build.py                     content -> dist/
deploy.sh                    assets (if missing) -> build -> OG cards -> wrangler pages deploy
```

`private/`, `dist/` and `.venv/` are git-ignored: the fonts and the owner's logo (and every file
made from it) are never committed; deploy.sh copies them from the studio kits at build time.

## Adding a lesson (one per reel)

1. Write `content/articles/<slug>.md` (format in content/FORMAT.md; slug = English topic noun,
   kebab-case; set `idea:` to the ideas.json id so the topic leaves the «در راه» list).
2. Put the reel URL in `reel:` when it exists (else the block links to the Instagram page).
3. `./deploy.sh` (or `./deploy.sh --no-deploy` to look first). To make it «درس امروز» on the home
   page, set `"today"` in content/site.json to its slug.

## How a page's SEO fields are set

Every page takes its SEO from its own front matter; build.py never invents them.

| field | used for | default when empty |
|---|---|---|
| `title` | the visible H1 (articles, fixed pages) | — |
| `seo_title` | `<title>` | `title` + ` \| دات‌کوین` |
| `description` | `<meta name="description">`, OG/Twitter description | — (always set it, 120–155 chars) |
| `og_title`, `og_description` | Open Graph + Twitter card | `seo_title` / `description` |
| `og_en`, `og_kicker` | the giant English word and the chip on the generated OG image | `en` / the pillar |
| `noindex: true` | `<meta name="robots" content="noindex">`, left out of the sitemap | indexed |
| `date`, `updated` | Article `datePublished` / `dateModified`, sitemap `lastmod` (fixed and exchange pages: `updated`) | the newest lesson's date, never the build date |
| `answer`, `sources` | lessons: the «پاسخ کوتاه» box and the «منابع» list | not shown |

Exchange pages: `title` (→ `<title>`), `h1`, `description`, `lead` in content/exchanges/<slug>.md.

- **Canonical:** always `https://dotcoin.me` + the page path (trailing slash).
- **OG image:** one per page, rendered from templates/og.html to `/og/<key>.jpg` (1200×630).
- **JSON-LD:** one `@graph` per page, built in build.py by page type: Organization (`#org`),
  WebSite (`#website`) and Person (`/about/#behnam`) on the home page; CollectionPage + ItemList on
  /learn/ and /exchanges/; Article + FAQPage + BreadcrumbList on lessons; DefinedTermSet on
  /glossary/; WebPage + FAQPage on exchange pages; AboutPage on /about/; none on the 404.
- **Also generated:** `sitemap.xml` (indexable pages), `robots.txt` (Disallow /go/), `feed.xml`,
  `site.webmanifest`, `_headers` (security headers, long cache for /assets/, `X-Robots-Tag:
  noindex` on *.pages.dev), `_redirects` (`/go/<exchange>/` → the referral link, 302).
- **Persian text** is normalised at build time (Arabic ی/ک and Arabic-Indic digits → Persian);
  Latin names with digits (BIP39) keep Latin digits through a tiny digits-only font.

## Hosts

dotcoin.me and www.dotcoin.me are custom domains of the Pages project (proxied CNAMEs to
dotcoin.pages.dev). www → apex is a Cloudflare Redirect Rule when the token may write zone
rulesets; until then the page head sends www visitors to the apex (canonical points there too).
