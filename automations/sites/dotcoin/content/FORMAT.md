# Content format (read by build.py)

## Articles: `content/articles/<slug>.md`

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

## پرسش‌های پرتکرار

### <question>؟
<answer paragraph>
```

Rules: Persian digits (۰-۹) in the text, ZWNJ (‌) where Persian needs it, no price numbers,
no signals or predictions, no hype, no warnings or disclaimers, no politics. Every fact true.

## Glossary: `content/glossary.txt`
One term per line: `slug | Persian term | English term | one-line Persian definition`.
Lines starting with `#` are comments.
