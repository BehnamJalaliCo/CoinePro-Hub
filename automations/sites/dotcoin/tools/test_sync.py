#!/usr/bin/env python3
"""sync.py never makes a second article for a lesson that is already on the site.

    python3 -I automations/sites/dotcoin/tools/test_sync.py

Runs on a throwaway content tree (no hub, no git, no deploy): the real lessons are copied into it,
then reel articles are fed to sync.ingest() the way the hub feeds them.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # automations/sites/dotcoin
TMP = Path(tempfile.mkdtemp(prefix="dotcoin-sync-test-"))
SITE = TMP / "automations" / "sites" / "dotcoin"
(SITE / "content").mkdir(parents=True)
shutil.copytree(HERE / "content" / "articles", SITE / "content" / "articles")
if (HERE / "content" / "auto").is_dir():
    shutil.copytree(HERE / "content" / "auto", SITE / "content" / "auto")
os.environ.update(DOTCOIN_CONTENT_WT=str(TMP), DOTCOIN_SYNC_HOME=str(TMP), DOTCOIN_MEDIA=str(TMP / "media"))
spec = importlib.util.spec_from_file_location("dotcoin_sync", HERE / "sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
sync.log = lambda msg: LOG.append(msg)
LOG: list[str] = []
JOB = {"job": "test-job"}


def reel_article(slug: str, title: str, keyword: str = "", idea: str = "") -> bytes:
    """A complete reel article as the kit writes it (valid on its own)."""
    steps = "\n".join(f"- قدم {i} | جمله‌ی قدم {i}." for i in range(1, 6))
    body = " ".join(["این یک متن آزمایشی برای سنجش همگام‌سازی است."] * 60)
    return f"""---
title: {title}
seo_title: {title} | دات‌کوین
slug: {slug}
pillar: basics
idea: {idea}
date: 2026-11-20
updated: 2026-11-20
keyword: {keyword}
en: TEST
motif: generic
description: {"توضیح آزمایشی برای سنجش. " * 6}
lead: یک مقدمه‌ی کوتاه.
answer: {"پاسخ کوتاه آزمایشی " * 14}
reel:
sources:
- منبع | https://bitcoin.org/bitcoin.pdf
summary:
- یک
- دو
- سه
steps:
{steps}
---

{body}

## پرسش‌های پرتکرار

### پرسش؟
پاسخ.
""".encode()


class NoSecondArticle(unittest.TestCase):
    def setUp(self):
        self.state = {"files": {}, "sources": {}}
        LOG.clear()

    def feed(self, ws: str, raw: bytes, dry: bool = False) -> str:
        return sync.ingest(self.state, f"f-{ws}-{len(LOG)}", ws, raw, JOB, dry, live=None)

    def bound(self, ws: str) -> str | None:
        return (self.state["sources"].get(f"instagram:{ws}") or {}).get("slug")

    def test_same_slug_joins(self):
        self.feed("W-000901", reel_article("bitcoin", "بیت‌کوین دقیقاً چیه؟", idea="2"))
        self.assertEqual(self.bound("W-000901"), "bitcoin")
        self.assertFalse((SITE / "content" / "auto" / "bitcoin.md").exists())

    def test_same_idea_other_slug_joins(self):
        self.feed("W-000902", reel_article("bitcoin-basics", "بیت‌کوین به زبان خیلی ساده", idea="2"))
        self.assertEqual(self.bound("W-000902"), "bitcoin")

    def test_same_topic_no_idea_joins(self):
        self.feed("W-000903", reel_article("crypto-explained", "رمزارز را بشناس", keyword="ارز دیجیتال چیست"))
        self.assertEqual(self.bound("W-000903"), "cryptocurrency")

    def test_alias_keyword_joins(self):
        self.feed("W-000904", reel_article("what-crypto", "کریپتو یعنی چه", keyword="رمز ارز چیست"))
        self.assertEqual(self.bound("W-000904"), "cryptocurrency")

    def test_explicit_attach_joins(self):
        self.feed("W-000905", b"---\nattach: usdt-networks\n---\n")
        self.assertEqual(self.bound("W-000905"), "usdt-networks")

    def test_second_reel_on_a_bound_lesson_is_skipped(self):
        self.feed("W-000906", b"---\nattach: crypto-wallet\n---\n")
        self.feed("W-000907", reel_article("crypto-wallet", "کیف پول ارز دیجیتال", idea=""))
        self.assertEqual(self.bound("W-000906"), "crypto-wallet")
        self.assertIsNone(self.bound("W-000907"))
        self.assertTrue(any("already belongs to instagram:W-000906" in m for m in LOG), LOG)

    def test_new_topic_still_becomes_its_own_article(self):
        self.feed("W-000908", reel_article("seed-phrase", "عبارت بازیابی چیست؟", keyword="سید فریز چیست", idea="8"),
                  dry=True)
        self.assertTrue(any("would write seed-phrase" in m for m in LOG), LOG)

    def test_every_cornerstone_is_on_disk(self):
        lessons = sync.local_articles()
        for slug in ("cryptocurrency", "bitcoin", "crypto-wallet", "how-to-buy-crypto", "usdt-networks"):
            self.assertIn(slug, lessons)


if __name__ == "__main__":
    try:
        r = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if r.wasSuccessful() else 1)
