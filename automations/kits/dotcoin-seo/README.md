# DotCoin.me — the daily SEO day — the kit (owner 2026-11-18)

The owner: «اتوماسیون سئو سایت دات کوین رو راه اندازی بکن که یه اتوماسیون فوق متخصص باید باشه که هر روز
بیشتر دیده شدن و به صفحه اول گوگل اومدن تلاش بکنه». Every day (flow `dotcoin_seo`), one session makes
dotcoin.me more visible in Google, white-hat only: it reads the data, decides like a senior SEO,
writes ONE new long, well-researched page for a keyword cluster, improves the live pages the data
points at, records every change and its measured effect, and hands the hub ONE package. The hub
checks it again, puts it on the site at the hour, and asks Google and IndexNow to index it.

You are the day's session on the holding's workshop (user `studio`), **Opus 5.5 at extra-high effort**.
Work alone: never `order.ask`, never wait for an approval, NEVER call `workshop.run` (you ARE on it).
A turn has at most 60 minutes: the day takes about three turns; `NOTES.md` (read it FIRST every turn)
says what is done and what is next. Never edit the kit (read only).

KIT = /home/studio/kits/dotcoin-seo. The day's input pack (made by the hub before this order):
/home/studio/seo-inputs/dotcoin/<the day in your order>/ (`in/` after setup). S = `site/automations/sites/dotcoin`
(your copy of the site's source). PY = /home/studio/kits/prochart-reels/venv-render/bin/python (Playwright,
Pillow); python3 for everything else.

## FIRST read KIT/DIRECTION.md (the doctrine: what wins, what is forbidden, how a change is judged),
then S/seo/ARTICLE_BRIEF.md (the lesson format and its quality bar), S/content/FORMAT.md,
S/seo/auto/README.md, S/seo/auto/TOPIC_MAP.md and the newest blocks of S/seo/auto/LOG.md.

## Turn 1 — the data, the audit, the plan (≈ 40 min)
1. `bash KIT/tools/setup.sh <day>` (once: it makes `site/` as a git copy tagged `base`, `in/`, `out/`,
   `NOTES.md`). A missing pack is said in NOTES.md and report.md; the day goes on from the live site.
2. `in/errors.json` (what the hub could not read today), `in/applied.json` (what yesterday's package
   became: applied, left out and why, IndexNow, «Request indexing»). Write yesterday's outcome into
   today's LOG.md block (the session that made it could not see it).
3. `python3 -I KIT/tools/gsc_digest.py in/ S --json work/digest.json > work/digest.md` and read it all:
   totals and trend, day over day, week over week, striking distance, CTR gaps, pages, new queries,
   the index state of every URL, the experiments due.
4. `bash KIT/tools/build.sh` (the whole site from your copy: its bidi lint, then the SEO audit of every
   page into work/audit.md: titles, descriptions, canonicals, one H1, JSON-LD, alt, broken internal
   links, orphans, the sitemap). An error found there is today's fix if it is in content.
5. `python3 -I KIT/tools/live_check.py` (the live pages, /vip/ and its tracked links, robots) and
   `bash KIT/tools/lighthouse.sh` on 3 live URLs (the top page by impressions, the newest page, /vip/).
6. **The plan, in NOTES.md** (DIRECTION §3 decides the order):
   - the experiments due: judged (keep / roll back), with the numbers;
   - today's NEW page: its cluster (TOPIC_MAP, or a query from Search Console with no page of its
     own), its slug, primary and secondary queries, intent, the 4–8 live lessons it links to and the
     2–3 that will link to it; check it is not a long video's (`site/automations/kits/dotcoin-longform/
     topics.md`) nor a live lesson's topic (S/seo/PAGE_PLAN.md §7);
   - 2–5 improvements to live pages, each with the data that asks for it and what will measure it.

## Turn 2 — research and write the new page (≈ 50 min)
7. Research like an expert, not a summariser: `python3 -I KIT/tools/suggest.py "<primary>" --deep` (the
   real questions people type: the FAQ and the H2s), the top results for the primary query (what they
   cover, what they miss, how old they are), and the PRIMARY sources (the protocol's docs, the
   whitepaper, the exchange's own help page, a regulator or a central bank only for a fact, never for
   advice). Every number and claim checked today, from its source.
8. Write `S/content/articles/<slug>.md` (ARTICLE_BRIEF + FORMAT): 1,500–2,500 words of real teaching,
   the answer box (40–60 words, complete on its own), 5–8 H2 that each answer one sub-question, a
   table where two or more things are compared, a worked everyday example, 4–6 FAQ from the suggest
   questions, 1–3 primary sources in `sources`, 4–8 links to live lessons with descriptive anchors,
   `date:` the day, `keyword:` the primary query, `keywords:` its close variants, `pillar`, `motif`,
   `en` (one or two giant English words), 5 `steps`, 3–5 `summary` lines. Persian as the brief says:
   «تو», short sentences, ZWNJ, Persian digits, Latin names left as they are (the build isolates them).
9. Link TO it from the 2–3 most related live lessons (one sentence each where it truly helps the
   reader; never a list of links), and add its terms to `S/content/glossary.txt` when they are missing.

## Turn 3 — improvements, the gate, the package (≈ 45 min)
10. Make the day's improvements (DIRECTION §4: titles and descriptions for CTR, a missing sub-question
    section for a striking-distance query, internal links to an orphan or a page Google has not
    indexed, a FAQ answer, an outdated fact refreshed with `updated:`, a broken link). One change per
    page per experiment; every change logged.
11. The automation's memory (S/seo/auto/): today's block in LOG.md (the data you started from, every
    change: URL, field, before → after, why; the new page; what to measure and when), EXPERIMENTS.json
    (each measurable change: id, page, query, change, baseline from the digest, `judge_on` = +14 days),
    TOPIC_MAP.md (the cluster `live:<day>`; new clusters you found, with their evidence),
    KEYWORDS.json (the queries you saw today: page, suggest evidence, Search Console figures).
12. **The gate — nothing ships without it:** `bash KIT/tools/build.sh` (exit 0: the bidi lint and the
    audit's errors 0), then `bash KIT/tools/review.sh <the new page> <every changed page> /vip/` and
    READ EVERY PART in shots/ (phone light, phone dark, desktop, 920 px): no Latin run out of place, no
    clipped or overflowing text, tables inside their box, the page complete. Its findings must be 0.
    Fix and run again until it is clean (the hub runs the same checks and refuses on any finding).
13. `bash KIT/tools/pack.sh <day> "<the new page's title>" /learn/<slug>/ [the 1–3 other URLs to index
    first]` -> out/package.zip (it refuses what the hub would refuse: fix and pack again).
14. **Deliver** (out/ holds ONLY these): `report.md` (Persian: the data, the decisions and why, the new
    page, every change, the measurements, what failed today), `summary.fa.txt` (one Persian line: the
    day's work), `topic.txt` (line 1: the new page's title), on a **Saturday** also `week.fa.txt`
    (DIRECTION §6), and **package.zip LAST**: the zip and summary.fa.txt make the day's package; the
    hub closes the session. `order.progress` done: the new page, the number of changes, one Persian line.

## What the hub does with it (not the session)
At the hour, `seo.py --due` (automations/sites/dotcoin, dotcoin-seo.timer) checks the package with the
same rules (tools/seo_pack.py), applies each file with a 3-way merge (a file the site changed meanwhile
in a conflicting way is left out and reported in tomorrow's applied.json), refreshes the VIP's numbers,
builds the whole site, reviews every touched page at 390 px light and dark, commits, deploys through
the site sync, checks the new page live, pings IndexNow (Bing, Yandex) for every new or changed URL,
submits the sitemap again and asks Search Console to index the URLs you put first (Google's own daily
cap). Any failure of its checks means NOTHING of the day is published: the reason is in tomorrow's
applied.json, and fixing it is tomorrow's first task.
