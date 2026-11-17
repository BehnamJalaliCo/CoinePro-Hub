# Content format (read by build.py)

## Articles: `content/articles/<slug>.md` (by hand) and `content/auto/<slug>.md` (the hub's, sync.py)

A slug is unique across both folders (the build stops on a duplicate). Optional fields: `youtube:`
(a YouTube id or link: a player under the reel) and, for the hub's articles, pillar `news`.

```
---
title: <Persian title>
slug: <english-kebab-case>
pillar: basics | security | exchange | market | defi | myths | terms   (bank/ideas.json pillars)
idea: <id in automations/kits/dotcoin-reels/bank/ideas.json, or empty>
date: YYYY-MM-DD
en: <ONE OR TWO GIANT ENGLISH WORDS, uppercase>
motif: chain | vault | halving | peg | generic
description: <meta description, one Persian sentence, 120-160 characters>
lead: <the standfirst under the title, 1-2 Persian sentences>
reel: <Instagram reel URL, or empty>
answer: <«پاسخ کوتاه»: the answer in 40-60 Persian words, complete on its own (featured snippets quote it)>
sources:
- <label> | <https URL of a primary source>   (1-3 lines, rendered as «منابع»)
updated: <YYYY-MM-DD, only after a real content change: dateModified, sitemap lastmod>
summary:
- <one line>
- <3 to 5 lines>
steps:
- <short title> | <one sentence>
- <exactly 5 steps: the lesson as 5 slides>
---

<intro paragraphs>

## <section heading>
Paragraphs, **bold**, lists (`- ` / `1. `), blockquotes (`> `), links `[text](url)`.
Tables: `| a | b |` rows, the first row is the header, a `|---|---|` row is skipped.
Inline code `x` is LTR. A line that is only one `code` span, or a ``` fence, becomes an LTR code block
that wraps inside its box (a hash, an address). Latin terms (SHA-256, USDT TRC20, a URL) need no markup:
the build isolates every Latin run in the Persian text and fails on a page it could not fix (build.py, bidi).

## پرسش‌های پرتکرار

### <question>؟
<answer paragraph>
```

Rules: Persian digits (۰-۹) in the text, ZWNJ (‌) where Persian needs it, no price numbers,
no signals or predictions, no hype, no warnings or disclaimers, no politics. Every fact true.

## Glossary: `content/glossary.txt`
One term per line: `slug | Persian term | English term | one-line Persian definition`.
Lines starting with `#` are comments.

SEO rules for every lesson: `seo/ARTICLE_BRIEF.md`; the acceptance checks: `seo/CHECKLIST.md`.
