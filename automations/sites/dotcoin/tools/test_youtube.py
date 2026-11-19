#!/usr/bin/env python3
"""youtube.py: every Short gets its reel's own Instagram cover as its thumbnail, and never twice.

    python3 -I automations/sites/dotcoin/tools/test_youtube.py

Runs on a throwaway state (no hub, no profile, no upload): the hub's reads, egress and the video copy
are stubbed; the cover's own checks (sha256, YouTube's 2 MB) run for real (ffmpeg for the big one).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # automations/sites/dotcoin
TMP = Path(tempfile.mkdtemp(prefix="dotcoin-youtube-test-"))
os.environ.update(DOTCOIN_CONTENT_WT=str(TMP), DOTCOIN_SYNC_HOME=str(TMP / "home"),
                  DOTCOIN_YT_RECIPE=str(TMP / "recipe.yaml"))
(TMP / "home").mkdir()
spec = importlib.util.spec_from_file_location("dotcoin_youtube", HERE / "youtube.py")
Y = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Y)
LOG: list[str] = []
Y.log = LOG.append
STORE = TMP / "store"  # the hub's files, by storage key
STORE.mkdir()
COVER = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")  # a (tiny) JPEG's bytes


def put(data: bytes) -> tuple[str, str]:
    key = hashlib.md5(data).hexdigest()
    (STORE / key).write_bytes(data)
    return key, hashlib.sha256(data).hexdigest()


def fake_read_file(key, sha, size, cap, dest):  # the hub's storage, with youtube.py's own checks
    data = (STORE / str(key)).read_bytes()
    if not 0 < int(size) <= cap:
        raise ValueError("unexpected storage key or size")
    if sha and hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("sha256 mismatch")
    Path(dest).write_bytes(data)


def row(w: str, cover: bytes | None = COVER, mime: str = "image/jpeg") -> dict:
    r = {"w": w, "job": "00000000-0000-0000-0000-000000000001", "chain": "c" * 32, "caption": "یک درس\n#تست",
         "url": f"https://www.instagram.com/reel/{w}/", "key": "0" * 32, "sha": hashlib.sha256(w.encode()).hexdigest(),
         "size": 1000, "video": "00000000-0000-0000-0000-000000000002",
         "cover_key": None, "cover_sha": None, "cover_size": None, "cover_mime": None}
    if cover is not None:
        key, sha = put(cover)
        r.update(cover_key=key, cover_sha=sha, cover_size=len(cover), cover_mime=mime)
    return r


class Egress:
    """The profile's answers, by task; every call kept (its job and its file's bytes)."""

    def __init__(self, thumbnail: dict | None = None):
        self.calls: list[dict] = []
        self.answers = {"titles": {"ok": True, "text_md": "another Short"},
                        "upload": {"ok": True, "text_md": "https://youtube.com/shorts/AbCdEfGhIjK"},
                        "thumbnail": thumbnail or {"ok": True, "text_md": " ", "notes": {"thumbnail": "Upload file"}}}

    def __call__(self, task, prompt, timeout_s, **kw):
        f = kw.get("video") or kw.get("file")
        self.calls.append({"task": task, **{k: v for k, v in kw.items() if k not in ("video", "file")},
                           "bytes": Path(f).read_bytes() if f else None})
        return dict(self.answers[task])

    def tasks(self) -> list[str]:
        return [c["task"] for c in self.calls]


def args(**kw) -> argparse.Namespace:
    base = {"make_public": None, "task": None, "dry_run": False, "only": None, "unlisted": False}
    return argparse.Namespace(**{**base, **kw})


class Thumbnails(unittest.TestCase):
    def setUp(self) -> None:
        LOG.clear()
        if Y.STATE.exists():
            Y.STATE.unlink()
        self.rows: list[dict] = []
        Y.published_reels = lambda: self.rows
        Y.sync_slugs = lambda: {}
        Y.read_file = fake_read_file
        Y.fetch = lambda r, dest: Path(dest).write_bytes(b"reel")
        Y.make_upload_copy = lambda src, dest, work: Path(dest).write_bytes(b"video") and 30.0
        Y.link_article = lambda slug, url: self.fail("no article link in these tests")

    def state(self, uploads: dict) -> None:
        Y.save_state({"uploads": uploads})

    def up(self, w: str) -> dict:
        return Y.load_state()["uploads"][f"{Y.CHANNEL}|instagram:{w}"]

    def test_a_new_short_gets_its_reels_cover_on_the_same_pass(self) -> None:
        self.rows = [row("W-000900")]
        eg = Y.egress = Egress()
        self.assertEqual(Y.one_pass(args()), 0)
        self.assertEqual(eg.tasks(), ["titles", "upload", "thumbnail"])
        thumb = eg.calls[-1]
        self.assertEqual(thumb["video_id"], "AbCdEfGhIjK")
        self.assertEqual(thumb["bytes"], COVER)  # the Instagram cover itself, not a frame
        self.assertEqual(thumb["file_name"], "W-000900-cover.jpg")
        up = self.up("W-000900")
        self.assertEqual((up["status"], up["thumb_set"], up["thumb_tries"]), ("done", "yes", 1))
        self.assertEqual(up["thumb_sha"], self.rows[0]["cover_sha"])

    def test_an_older_short_gets_its_cover_and_is_never_uploaded_again(self) -> None:
        self.rows = [row("W-000901")]
        self.state({f"{Y.CHANNEL}|instagram:W-000901": {"status": "done", "video_id": "LYjwwCScVIg",
                                                         "url": "https://youtube.com/shorts/LYjwwCScVIg"}})
        eg = Y.egress = Egress()
        Y.one_pass(args())
        self.assertEqual(eg.tasks(), ["thumbnail"])
        self.assertEqual(eg.calls[0]["video_id"], "LYjwwCScVIg")
        self.assertEqual(self.up("W-000901")["thumb_set"], "yes")
        # the next pass is idle: nothing in the profile
        eg = Y.egress = Egress()
        Y.one_pass(args())
        self.assertEqual(eg.tasks(), [])

    def test_a_refused_thumbnail_is_tried_three_times_then_left(self) -> None:
        self.rows = [row("W-000902")]
        self.state({f"{Y.CHANNEL}|instagram:W-000902": {"status": "done", "video_id": "Bj2MRTSAq6w"}})
        eg = Y.egress = Egress(thumbnail={"ok": False, "error": "recipe_failed", "detail": "no input", "step": "3:attach"})
        for _ in range(5):
            Y.one_pass(args())
        self.assertEqual(eg.tasks(), ["thumbnail"] * 3)
        up = self.up("W-000902")
        self.assertEqual((up["thumb_set"], up["thumb_tries"]), ("no", 3))
        self.assertIn("3:attach", up["thumb_why"])

    def test_an_area_that_asks_for_verification_is_not_a_thumbnail(self) -> None:
        self.rows = [row("W-000903")]
        self.state({f"{Y.CHANNEL}|instagram:W-000903": {"status": "done", "video_id": "EJmFu397EaE"}})
        Y.egress = Egress(thumbnail={"ok": True, "text_md": "Verify your phone number to upload a custom thumbnail"})
        Y.one_pass(args())
        self.assertEqual(self.up("W-000903")["thumb_set"], "no")

    def test_a_busy_or_signed_out_profile_counts_no_try(self) -> None:
        self.rows = [row("W-000904")]
        self.state({f"{Y.CHANNEL}|instagram:W-000904": {"status": "done", "video_id": "TyYsNUfodio"}})
        Y.egress = Egress(thumbnail={"ok": False, "error": "busy", "detail": "one job per account at a time"})
        Y.one_pass(args())
        up = self.up("W-000904")
        self.assertEqual(up.get("thumb_tries"), 0)
        self.assertNotIn("thumb_set", up)
        Y.egress = Egress(thumbnail={"ok": False, "error": "expired", "detail": "signed out"})
        Y.one_pass(args())
        self.assertEqual(self.up("W-000904").get("thumb_tries"), 0)
        self.assertIn("signed_out_at", Y.load_state())

    def test_no_cover_no_video_id_or_a_check_upload_sends_nothing(self) -> None:
        self.rows = [row("W-000905", cover=None), row("W-000906"), row("W-000907")]
        self.state({f"{Y.CHANNEL}|instagram:W-000905": {"status": "done", "video_id": "AAAAAAAAAAA"},
                    f"{Y.CHANNEL}|instagram:W-000906": {"status": "check"},
                    f"{Y.CHANNEL}|instagram:W-000907": {"status": "exists"}})
        eg = Y.egress = Egress()
        Y.one_pass(args())
        self.assertEqual(eg.tasks(), [])
        self.assertEqual(self.up("W-000905")["thumb_set"], "none")  # YouTube's own frame stays
        self.assertNotIn("thumb_set", self.up("W-000906"))
        LOG.clear()
        Y.one_pass(args())  # then idle: no log
        self.assertEqual((eg.tasks(), LOG), ([], []))

    def test_a_tampered_cover_is_never_sent(self) -> None:
        r = row("W-000908")
        r["cover_sha"] = "0" * 64
        self.rows = [r]
        self.state({f"{Y.CHANNEL}|instagram:W-000908": {"status": "done", "video_id": "BBBBBBBBBBB"}})
        eg = Y.egress = Egress()
        for _ in range(4):
            Y.one_pass(args())
        self.assertEqual(eg.tasks(), [])
        self.assertTrue(any("sha256 mismatch" in ln for ln in LOG))
        self.assertEqual(self.up("W-000908")["thumb_tries"], 3)  # counted: never an endless retry

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_a_cover_over_2_mb_goes_as_a_jpeg_under_it(self) -> None:
        work = Path(tempfile.mkdtemp(dir=TMP))
        big = work / "big.png"
        Y.tool(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                "color=c=orange:s=1080x1920,noise=alls=100:allf=t", "-frames:v", "1", str(big)], work)
        data = big.read_bytes()
        self.assertGreater(len(data), Y.MAX_THUMB)
        pic = Y.cover_file(row("W-000909", cover=data, mime="image/png"), work)
        self.assertEqual(pic.suffix, ".jpg")
        self.assertLessEqual(pic.stat().st_size, Y.MAX_THUMB)
        self.assertEqual(pic.read_bytes()[:2], b"\xff\xd8")

    def test_the_hubs_query_reads_the_publications_cover(self) -> None:
        q = Y.REELS_SQL
        self.assertIn("media.publications", q)
        self.assertIn("thumb_file_id", q)
        self.assertIn("'cover'", q)  # the chain's publish job's cover file, when the publication has none
        for col in ("cover_key", "cover_sha", "cover_size", "cover_mime"):
            self.assertIn(f"AS {col}", q)


class CoverFamily(unittest.TestCase):
    """⟨2026-11-19⟩ the cover kit's row: always the newest 4 PUBLISHED covers, written file by file."""

    def setUp(self) -> None:
        LOG.clear()
        self.dir = TMP / "family"
        shutil.rmtree(self.dir, ignore_errors=True)
        Y.FAMILY, Y.FAMILY_AS = self.dir, ""
        Y.read_file = fake_read_file
        self.rows: list[dict] = []
        Y.sql = lambda q: [dict(r) for r in self.rows] if q == Y.FAMILY_SQL else self.fail(f"unexpected query {q[:40]}")

    def pub(self, ref: str, at: str, data: bytes, mime: str = "image/jpeg") -> dict:
        key, sha = put(data)
        return {"ref": ref, "at": at, "key": key, "sha": sha, "size": len(data), "mime": mime}

    def names(self) -> list[str]:
        return sorted(p.name for p in self.dir.iterdir())

    def test_the_row_is_exactly_the_newest_four_and_the_rest_goes(self) -> None:
        self.dir.mkdir()
        (self.dir / "2026-11-17_P-000073.jpg").write_bytes(b"a hand-placed old cover")
        (self.dir / ".tmp-left-over.jpg").write_bytes(b"x")
        self.rows = [self.pub(f"P-00012{i}", f"2026-11-1{9 - i}T0931Z", COVER + bytes([i])) for i in range(5)]
        self.assertEqual(Y.refresh_family(), "4 written, 2 removed")
        want = sorted(f"{r['at']}_{r['ref']}_{r['sha'][:8]}.jpg" for r in self.rows[:4])
        self.assertEqual(self.names(), want)
        for r in self.rows[:4]:
            self.assertEqual((self.dir / f"{r['at']}_{r['ref']}_{r['sha'][:8]}.jpg").read_bytes(),
                             (STORE / r["key"]).read_bytes())
        self.assertEqual(Y.refresh_family(), "")  # unchanged: nothing written, nothing said
        self.assertEqual(self.names(), want)

    def test_names_sort_by_publish_time(self) -> None:
        self.rows = [self.pub("P-000099", "2026-11-19T0931Z", COVER + b"1"),
                     self.pub("P-000200", "2026-11-18T1701Z", COVER + b"2")]
        Y.refresh_family()
        self.assertEqual([n.split("_")[1] for n in self.names()], ["P-000200", "P-000099"])

    def test_a_cover_replaced_after_publishing_replaces_its_file(self) -> None:
        self.rows = [self.pub("P-000122", "2026-11-19T0931Z", COVER + b"frame")]
        Y.refresh_family()
        self.rows = [self.pub("P-000122", "2026-11-19T0931Z", COVER + b"the real cover")]
        self.assertEqual(Y.refresh_family(), "1 written, 1 removed")
        self.assertEqual(len(self.names()), 1)
        self.assertEqual((self.dir / self.names()[0]).read_bytes(), COVER + b"the real cover")

    def test_a_tampered_or_odd_file_never_enters_the_row(self) -> None:
        bad = self.pub("P-000300", "2026-11-19T1701Z", COVER + b"x")
        bad["sha"] = "0" * 64
        with self.assertRaises(ValueError):
            self.rows = [bad]
            Y.refresh_family()
        self.rows = [self.pub("P-000301", "2026-11-19T1701Z", b"GIF89a", mime="image/gif")]
        self.assertEqual(Y.refresh_family(), "")
        self.assertFalse(self.dir.exists() and self.names())

    def test_the_query_takes_published_covers_never_a_frame(self) -> None:
        q = Y.FAMILY_SQL
        self.assertIn("'cover'", q)
        self.assertNotIn("'thumb'", q)
        self.assertIn("p.state = 'published'", q)
        self.assertIn("ORDER BY p.published_at DESC LIMIT 4", q)

    def test_every_pass_refreshes_it_a_dry_run_or_a_task_never(self) -> None:
        calls: list[str] = []
        real_pass, real_refresh, argv = Y.one_pass, Y.refresh_family, sys.argv
        Y.one_pass = lambda a: 0
        Y.refresh_family = lambda: calls.append("refresh") or "1 written, 0 removed"
        try:
            for extra, want in (([], 1), (["--dry-run"], 0), (["--task", "titles"], 0), (["--only", "W-000656"], 1)):
                calls.clear()
                sys.argv = ["youtube.py", *extra]
                self.assertEqual(Y.main(), 0)
                self.assertEqual(len(calls), want, extra)
        finally:
            Y.one_pass, Y.refresh_family, sys.argv = real_pass, real_refresh, argv


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
