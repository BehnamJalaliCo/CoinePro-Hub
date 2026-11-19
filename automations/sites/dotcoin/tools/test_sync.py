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
        self.feed("W-000908", reel_article("network-fee-test", "کارمزد شبکه از کجا میاد؟",
                                           keyword="کارمزد آزمایشی شبکه", idea="9999"), dry=True)
        self.assertTrue(any("would write network-fee-test" in m for m in LOG), LOG)

    def test_every_cornerstone_is_on_disk(self):
        lessons = sync.local_articles()
        for slug in ("cryptocurrency", "bitcoin", "crypto-wallet", "how-to-buy-crypto", "usdt-networks"):
            self.assertIn(slug, lessons)


COVER_A, COVER_B = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"


class PosterIsTheCover(unittest.TestCase):
    """⟨2026-11-19⟩ the article's poster is the reel's real cover (its publication's), never a frame when a
    cover exists; a cover made or replaced after the article makes the poster again, the video stays."""

    def setUp(self):
        LOG.clear()
        sync.MEDIA.mkdir(parents=True, exist_ok=True)
        (sync.MEDIA / "seed-test.mp4").write_bytes(b"video")
        self.src = {"key": "instagram:W-000990", "w": "W-000990", "slug": "seed-test", "media": "v-1",
                    "reel": "https://www.instagram.com/reel/AbC/"}
        self.job = {"w": "W-000990", "job": "j", "video": "v-1", "cover": COVER_A,
                    "url": "https://www.instagram.com/reel/AbC/", "at": ""}

    def test_due_when_the_poster_is_a_frame_or_an_older_cover(self):
        for poster in (None, "frame", COVER_B):
            self.src["poster"] = poster
            self.assertTrue(sync.poster_due(self.src, self.job), poster)

    def test_not_due_when_it_is_the_cover_or_there_is_none(self):
        self.src["poster"] = COVER_A
        self.assertFalse(sync.poster_due(self.src, self.job))
        self.src["poster"], self.job["cover"] = "frame", None
        self.assertFalse(sync.poster_due(self.src, self.job))

    def test_three_failed_tries_then_left(self):
        self.src.update(poster="frame", poster_tries=3)
        self.assertFalse(sync.poster_due(self.src, self.job))

    def test_the_query_prefers_the_publications_cover_never_its_frame(self):
        q = sync.JOBS_SQL
        self.assertIn("media.publications", q)
        self.assertLess(q.index("media.publications"), q.index("j.args -> 'files'"))
        self.assertIn("x ->> 'role' = 'cover'", q)
        self.assertNotIn("'thumb'", q)

    def test_a_pass_remakes_only_the_poster(self):
        made: list[str] = []
        sync.save_state({"files": {}, "sources": {self.src["key"]: dict(self.src, poster="frame")}})
        saved = {k: getattr(sync, k) for k in ("new_articles", "reel_jobs", "make_media", "make_poster",
                                               "push", "deploy", "commit")}
        sync.new_articles = lambda done: []
        sync.reel_jobs = lambda: {"W-000990": self.job}
        sync.make_media = lambda *a: self.fail("the video stays as it is")
        sync.make_poster = lambda slug, src, job: made.append(slug) or src.update(poster=job["cover"]) or True
        sync.push = sync.deploy = lambda *a: None
        sync.commit = lambda msg: False
        try:
            import argparse
            self.assertEqual(sync.one_pass(argparse.Namespace(import_file=None, workspace=None, dry_run=False)), 0)
            self.assertEqual(made, ["seed-test"])
            self.assertEqual(sync.load_state()["sources"][self.src["key"]]["poster"], COVER_A)
            made.clear()
            sync.one_pass(argparse.Namespace(import_file=None, workspace=None, dry_run=False))
            self.assertEqual(made, [])  # once the poster is the cover: nothing again
        finally:
            for k, v in saved.items():
                setattr(sync, k, v)


if __name__ == "__main__":
    try:
        r = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if r.wasSuccessful() else 1)
