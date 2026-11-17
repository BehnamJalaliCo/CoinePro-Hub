# site/: what the day's session needs to write out/article.md (copies, read only)

Copied from automations/sites/dotcoin (branch server/dotcoin-site); refresh them from there when
the site's rules change:
- ARTICLE_BRIEF.md (seo/), PAGE_PLAN.md (seo/): the rules, the slugs and queries per idea;
- glossary.txt (content/): `slug | term | English | definition`, the `/glossary/#<slug>` anchors;
- example.md (content/articles/blockchain.md): a finished lesson, the model for the format;
- sync.py: only `python3 -I sync.py --check out/article.md` (the session's self-check).
