# seo/auto: the daily SEO automation's own memory (flow dotcoin_seo, kit dotcoin-seo)

Written by the day's session (in its package, through `tools/seo_pack.py`), applied by the hub
(`seo.py`), versioned here so every day learns from the days before. Never edited by hand while
the flow runs.

| File | What | Rule |
|---|---|---|
| `TOPIC_MAP.md` | every keyword cluster: its page, primary and secondary queries, intent, status, links | one cluster = one page; a long video's slug (kit dotcoin-longform's topics.md) is never an SEO page |
| `LOG.md` | one dated block per day: what changed (page, field, before → after), why (the data), what to measure | append only, newest last |
| `EXPERIMENTS.json` | each measurable change: page, query, baseline (impressions, clicks, CTR, position over 28 days), the day to judge it, the verdict | judged at +14 and +28 days; a loss is rolled back the next day |
| `KEYWORDS.json` | the keyword bank: query → page, Google suggest evidence, Search Console figures once they exist | refreshed from Search Console every day |

The facts behind the site's pages and the brief of a lesson stay in `seo/ARTICLE_BRIEF.md`,
`seo/KEYWORDS.md`, `seo/PAGE_PLAN.md`, `seo/TECHNICAL.md` and `seo/CHECKLIST.md` (phase 1 and 2).
