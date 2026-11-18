# dotcoin.me — the site

Static site for DotCoin.me (crypto education in plain Persian, by Behnam Jalali), built by a
stdlib-only Python generator and deployed to Cloudflare Pages (project `dotcoin`, direct upload).

```
content/site.json            site-wide facts (name, URL, socials, "today" lesson, ideas bank path)
content/pages/*.md           the fixed pages: home, learn, glossary, exchanges, about, 404
content/articles/<slug>.md   one lesson per file (format: content/FORMAT.md)
content/auto/<slug>.md       the hub's daily lessons (sync.py; only on branch site/dotcoin-content)
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
sync.py                      the hub's article.md files -> content/auto -> commit, push, deploy
seo.py                       the daily SEO automation's host side (seo/auto/README.md, kit dotcoin-seo)
content/vip.json             TradeYar's VIP: its links (TradeYar's tracker), codes, conditions
content/vip_stats.json       TradeYar's public record for /vip/ (seo.py --vip-stats; never by hand)
content/pages/vip.md         /vip/'s text: SEO fields, what it gives, the three steps, the FAQ
tools/review.py              the phone review: 390 px light and dark (+ 1440, 920): overflow, shots
tools/seo_pack.py            the SEO day's package: make (the session) and check (the hub's gate)
tools/test_seo.py            the package rules and the 3-way apply
```

`private/`, `dist/` and `.venv/` are git-ignored: the fonts and the owner's logo (and every file
made from it) are never committed; deploy.sh copies them from the studio kits at build time.

## Adding a lesson (one per reel)

1. Write `content/articles/<slug>.md` (format in content/FORMAT.md; slug = English topic noun,
   kebab-case; set `idea:` to the ideas.json id so the topic leaves the «در راه» list).
2. Put the reel URL in `reel:` when it exists (else the block links to the Instagram page).
3. `./deploy.sh` (or `./deploy.sh --no-deploy` to look first). To make it «درس امروز» on the home
   page, set `"today"` in content/site.json to its slug.

## The daily lessons (sync.py, from 2026-11-17)

Every DotCoin reel's session (kit dotcoin-reels; the educational AND the informational reel) leaves
`out/article.md` (seo/ARTICLE_BRIEF.md): the same reel's lesson or news, expanded. Or, when the
reel's lesson was written by hand before (content/articles), `attach: <slug>` alone.
`dotcoin-site-sync.timer` (infra/systemd, every 15 minutes, user Hub) runs `sync.py` from the
content worktree `/home/Hub/sites/dotcoin-content` (branch `site/dotcoin-content`, used only by
the sync). It reads the hub (read only), validates, writes `content/auto/<slug>.md`, makes the
reel's web copy (`/media/<slug>.mp4` + `.jpg` + `.json`, H.264 720x1280 ~2 Mbit/s, in
`/home/Hub/sites/dotcoin-media`, never in git), fills `reel:` once the reel is out, commits, pushes
and deploys, only when something is new or changed (an idle run is one local DB query, no log).

- **Never a duplicate:** one source (`instagram:<work ref>`; later `youtube:<video id>`) -> one
  slug; a slug or a topic (`keyword`/`title`) is never published twice; an article bound to
  another source is never overwritten (logged and skipped).
- **On the page:** the reel at the top of the lesson (poster = its cover, `preload="none"`,
  muted until started, `playsinline`, controls), the Instagram link under it, a `VideoObject` in
  the JSON-LD; an optional `youtube:` field (id or link) adds a YouTube player.
- State: `/home/Hub/sites/dotcoin-sync.json`; log: `journalctl -u dotcoin-site-sync`.

**The live site is deployed from the content worktree.** A site change made on
`server/dotcoin-site` is merged into `site/dotcoin-content` (in that worktree) before the next
deploy; a deploy from anywhere else would drop the daily lessons and their videos.

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

## TradeYar's VIP (owner, 2026-11-18: «تبلیغات کانال سیگنال vip»)

`/vip/` explains the free VIP (an account opened with TradeYar's link on Ourbit or LBank, at least
50 USDT in it, the UID sent to @TradeYarSignalBot; to stay, the balance never under 30 USDT), with
TradeYar's own numbers (content/vip_stats.json, its public API only: closed trades and days, win
rate, profit factor, symbols, with the source and the date) and its FAQ. Every lesson carries ONE
VIP block after its sources (never between paragraphs, never a pop-up); the menu ends with a
«سیگنال VIP» pill (header, drawer, footer). Every outgoing link is TradeYar's tracker
(`trade-future.ir/go/vip|ourbit|lbank?src=dotcoin&goal=…&pl=<placement>`) behind the site's own
`/go/vip-<placement>/` (302, robots-disallowed, `rel="sponsored nofollow"`), so TradeYar counts each
placement; seo.py also reads the clicks from Cloudflare once the token has Analytics Read.

## The daily SEO automation (flow dotcoin_seo, from 2026-11-19)

The hub's workshop makes one SEO day a day (kit `automations/kits/dotcoin-seo`); `seo.py`
(dotcoin-seo.timer, every 10 minutes, user Hub) reads Search Console in the youtube-web profile
before the build (recipe tasks gsc_*), hands the session its input pack
(/home/studio/seo-inputs/dotcoin/<day>/), and at the publish hour applies the day's package
(tools/seo_pack.py's rules, a 3-way merge per file, the full build and its bidi lint, tools/review.py
at 390 px light and dark), commits, runs the site sync (deploy), then IndexNow and «Request indexing».
Its memory is `seo/auto/` (topic map, log, experiments, keyword bank). IndexNow's key is
`content/site.json` `indexnow` (public by design: served at `/<key>.txt`).
