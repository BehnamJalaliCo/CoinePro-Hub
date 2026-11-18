#!/usr/bin/env python3
"""The SEO day's package rules (tools/seo_pack.py) and the hub's 3-way apply (seo.py).

    python3 -I automations/sites/dotcoin/tools/test_seo.py

Runs in a throwaway git copy of the site's content (no hub, no network, no deploy): the session's
side (`make`), the hub's gate (`check`), and the apply onto a worktree that moved meanwhile.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # automations/sites/dotcoin
REL = "automations/sites/dotcoin"


def sh(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def make_repo(where: Path) -> Path:
    """The site's content, sync.py and a long-video bank, committed."""
    site = where / REL
    (site / "content").mkdir(parents=True)
    for d in ("articles", "pages", "exchanges"):
        shutil.copytree(HERE / "content" / d, site / "content" / d)
    (site / "content" / "auto").mkdir()
    shutil.copy2(HERE / "content" / "glossary.txt", site / "content" / "glossary.txt")
    shutil.copy2(HERE / "sync.py", site / "sync.py")
    (site / "seo" / "auto").mkdir(parents=True)
    (site / "seo" / "auto" / "LOG.md").write_text("# log\n", "utf-8")
    (site / "build.py").write_text("# the generator\n", "utf-8")
    topics = where / "automations/kits/dotcoin-longform/topics.md"
    topics.parent.mkdir(parents=True)
    topics.write_text("| # | Status | Slug | Keyword |\n|---|---|---|---|\n"
                      "| 1 | used:2026-11-17 | `ethereum` | اتریوم چیست |\n"
                      "| 2 | free | `bitcoin-mining` | ماینینگ بیت کوین چیست |\n", "utf-8")
    sh(where, "init", "-q", "-b", "main")
    sh(where, "config", "user.email", "t@t")
    sh(where, "config", "user.name", "t")
    sh(where, "add", "-A")
    sh(where, "commit", "-q", "-m", "base")
    return where


def lesson(slug: str, title: str, keyword: str, words: int = 420) -> str:
    steps = "\n".join(f"- قدم {i} | جمله‌ی قدم {i}." for i in range(1, 6))
    body = " ".join(["این یک متن آزمایشی برای سنجش بسته‌ی سئوی روز است و فقط برای تست نوشته شده."] * (words // 14))
    return f"""---
title: {title}
seo_title: {title} | دات‌کوین
slug: {slug}
keyword: {keyword}
pillar: basics
date: 2026-11-20
en: TEST
motif: generic
description: این توضیح آزمایشی صفحه است و طولش آن‌قدر هست که از صد و ده نویسه بگذرد و قاعده‌ی توضیح متا را با یک جمله‌ی روشن رعایت کند.
lead: یک پیش‌درآمد کوتاه برای درس آزمایشی.
answer: این پاسخ کوتاه آزمایشی است که چند جمله دارد و برای سنجش قاعده‌ی پاسخ کوتاه نوشته شده و باید میان سی‌وپنج تا هفتاد واژه باشد تا هشداری ندهد و درس کامل به نظر برسد و همه‌ی چیزهای لازم را داشته باشد و خواننده را راضی کند.
sources:
- منبع آزمایشی | https://example.org/source
summary:
- خط یک
- خط دو
- خط سه
steps:
{steps}
---

{body}

## بخش یک
{body}

## پرسش‌های پرتکرار

### پرسش؟
پاسخ.
"""


class Pack(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dotcoin-seo-test-"))
        self.hub = make_repo(self.tmp / "hub")
        self.base = sh(self.hub, "rev-parse", "HEAD")
        # the session's copy: a fresh repo of the same files (its own commits), tagged base
        self.ses = self.tmp / "session"
        shutil.copytree(self.hub, self.ses, ignore=shutil.ignore_patterns(".git"))
        sh(self.ses, "init", "-q", "-b", "main")
        sh(self.ses, "config", "user.email", "s@s")
        sh(self.ses, "config", "user.name", "s")
        sh(self.ses, "add", "-A")
        sh(self.ses, "commit", "-q", "-m", "snapshot")
        sh(self.ses, "tag", "base")
        sys.path.insert(0, str(HERE / "tools"))
        import seo_pack

        self.P = seo_pack
        self.zip = self.tmp / "package.zip"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def site(self, root: Path) -> Path:
        return root / REL

    def test_a_new_lesson_and_an_edit_pack_and_pass_the_hubs_gate(self) -> None:
        s = self.site(self.ses)
        (s / "content/articles/crypto-signal.md").write_text(
            lesson("crypto-signal", "سیگنال ارز دیجیتال چیست", "سیگنال ارز دیجیتال چیست"), "utf-8")
        p = s / "content/articles/stablecoin.md"
        p.write_text(p.read_text("utf-8").replace("lead: قیمت", "lead: امروز قیمت"), "utf-8")
        (s / "seo/auto/LOG.md").write_text("# log\n- 2026-11-20: a new lesson\n", "utf-8")
        rc = self.P.make(self.ses, "base", self.zip, "2026-11-20", "سیگنال", ["/learn/crypto-signal/"], self.base)
        self.assertEqual(rc, 0)
        man, files, errs = self.P.check(self.zip, self.hub)
        self.assertEqual(errs, [])
        self.assertEqual(man["base"], self.base)
        self.assertEqual(man["new_urls"], ["/learn/crypto-signal/"])
        self.assertIn("/learn/stablecoin/", man["changed_urls"])
        self.assertEqual(len(files), 3)

    def test_the_gate_refuses_what_the_seo_day_may_never_do(self) -> None:
        s = self.site(self.ses)
        cases = {
            "a long video's slug": lambda: (s / "content/articles/bitcoin-mining.md").write_text(
                lesson("bitcoin-mining", "ماینینگ", "ماینینگ بیت کوین چیست"), "utf-8"),
            "the generator": lambda: (s / "build.py").write_text("# changed\n", "utf-8"),
            "a deletion": lambda: (s / "content/articles/stablecoin.md").unlink(),
            "a slug change": lambda: (s / "content/articles/stablecoin.md").write_text(
                (s / "content/articles/stablecoin.md").read_text("utf-8").replace("slug: stablecoin", "slug: stable"), "utf-8"),
            "a /go/ link": lambda: (s / "content/articles/stablecoin.md").write_text(
                (s / "content/articles/stablecoin.md").read_text("utf-8") + "\n[ثبت‌نام](/go/weex/)\n", "utf-8"),
            "a second article on a topic": lambda: (s / "content/articles/stablecoin-2.md").write_text(
                lesson("stablecoin-2", "استیبل‌کوین چیست و چرا قیمتش ثابت می‌ماند؟", "استیبل کوین چیست"), "utf-8"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                sh(self.ses, "reset", "-q", "--hard", "base")
                sh(self.ses, "clean", "-qfd")
                change()
                self.assertEqual(self.P.make(self.ses, "base", self.zip, "2026-11-20", hub_base=self.base), 1, name)

    def test_a_package_from_another_base_or_tampered_is_refused(self) -> None:
        s = self.site(self.ses)
        p = s / "content/articles/stablecoin.md"
        p.write_text(p.read_text("utf-8").replace("lead: قیمت", "lead: امروز قیمت"), "utf-8")
        self.assertEqual(self.P.make(self.ses, "base", self.zip, "2026-11-20", hub_base="0" * 40), 0)
        self.assertTrue(any("not in this repository" in e for e in self.P.check(self.zip, self.hub)[2]))
        self.assertEqual(self.P.make(self.ses, "base", self.zip, "2026-11-20", hub_base=self.base), 0)
        with zipfile.ZipFile(self.zip) as z:
            items = {n: z.read(n) for n in z.namelist()}
        items[f"files/{REL}/content/articles/stablecoin.md"] += b"\nx"
        with zipfile.ZipFile(self.zip, "w") as z:
            for n, b in items.items():
                z.writestr(n, b)
        self.assertTrue(any("sha256" in e for e in self.P.check(self.zip, self.hub)[2]))


class Apply(unittest.TestCase):
    """seo.apply_files: a file the site changed meanwhile is merged; a conflict is left out."""

    def test_the_apply_merges_or_leaves_out(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="dotcoin-seo-apply-"))
        try:
            hub = make_repo(tmp / "wt")
            base = sh(hub, "rev-parse", "HEAD")
            os.environ.update(DOTCOIN_CONTENT_WT=str(hub), DOTCOIN_SYNC_HOME=str(tmp))
            sys.path.insert(0, str(HERE))
            spec = importlib.util.spec_from_file_location("dotcoin_seo", HERE / "seo.py")
            seo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(seo)
            art = f"{REL}/content/articles/stablecoin.md"
            old = (hub / art).read_text("utf-8")
            # the session changed the lead; the site meanwhile got the reel link (another line)
            new = old.replace("lead: قیمت", "lead: امروز قیمت")
            (hub / art).write_text(old.replace("reel:", "reel: https://www.instagram.com/reel/x/"), "utf-8")
            sh(hub, "commit", "-qam", "reel link")
            gl = f"{REL}/content/glossary.txt"
            g_old = (hub / gl).read_text("utf-8")
            first = g_old.splitlines()[1] if g_old.splitlines()[0].startswith("#") else g_old.splitlines()[0]
            (hub / gl).write_text(g_old.replace(first, first + " (hub)"), "utf-8")  # the same line: a conflict
            sh(hub, "commit", "-qam", "glossary")
            man = {"base": base, "files": [{"path": art, "action": "edit"}, {"path": gl, "action": "edit"},
                                           {"path": f"{REL}/content/articles/new-one.md", "action": "add"}]}
            files = {art: new.encode(), gl: g_old.replace(first, first + " (seo)").encode(),
                     f"{REL}/content/articles/new-one.md": b"---\ntitle: x\n---\n"}
            applied, added, left = seo.apply_files(man, files)
            got = (hub / art).read_text("utf-8")
            self.assertIn("lead: امروز قیمت", got)
            self.assertIn("reel: https://www.instagram.com/reel/x/", got)
            self.assertIn(art, applied)
            self.assertTrue(any(gl in x for x in left))
            self.assertEqual(added, [f"{REL}/content/articles/new-one.md"])
            seo.undo(applied, added)
            self.assertEqual(sh(hub, "status", "--porcelain"), "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
