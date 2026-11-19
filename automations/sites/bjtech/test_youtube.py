#!/usr/bin/env python3
"""youtube.py's own rules (stdlib unittest, nothing leaves the host):
    BJ_REPO=$PWD python3 -I automations/sites/bjtech/test_youtube.py"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("bj_youtube", Path(__file__).with_name("youtube.py"))
assert _spec is not None and _spec.loader is not None
Y = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(Y)

CAPTION = """🔴 فوری: Gemini رسید به گوشی‌های کم‌حافظه‌ی اندروید
گوگل اپ Gemini رو برای گوشی‌های Android Go از نو ساخته
کلمه‌ی «جمنای» رو کامنت کن تا لینک رسمی رو دایرکت بگیری 👇
📌 خبرها و ابزارهای هوش مصنوعی هر روز در تلگرام:
https://t.me/behnamjalali_tech
#جمنای #هوش_مصنوعی #گوگل #Shorts"""
LINKS = {"telegram": "https://t.me/behnamjalali_tech", "instagram": "https://www.instagram.com/behnamjalali.tech"}


class Shorts(unittest.TestCase):
    def test_title_is_the_hook_without_emoji_with_shorts(self) -> None:
        t = Y.make_title(CAPTION)
        self.assertEqual(t, "فوری: Gemini رسید به گوشی‌های کم‌حافظه‌ی اندروید #Shorts")
        long = Y.make_title("واژه " * 40)
        self.assertLessEqual(len(long), 100)
        self.assertTrue(long.endswith("… #Shorts"))
        self.assertEqual(Y.make_title("#فقط_هشتگ"), "هوش مصنوعی و تکنولوژی #Shorts")

    def test_description_keeps_the_text_and_says_each_link_once(self) -> None:
        d = Y.make_description(CAPTION, LINKS)
        self.assertEqual(d.count("https://t.me/behnamjalali_tech"), 1)
        self.assertIn("https://www.instagram.com/behnamjalali.tech", d)
        self.assertNotIn("کامنت", d)
        self.assertIn("گوگل اپ Gemini رو برای گوشی‌های Android Go از نو ساخته", d)
        tags = d.rsplit("\n\n", 1)[-1].split()
        self.assertLessEqual(len(tags), 5)
        self.assertNotIn("#Shorts", tags)
        self.assertEqual(tags[:3], ["#جمنای", "#هوش_مصنوعی", "#گوگل"])
        self.assertNotIn("<", Y.make_description("a <b> c", LINKS))

    def test_a_short_goes_whole_only_when_youtube_takes_it_as_it_is(self) -> None:
        ok = {"format": {"duration": "58.4"},
              "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                           "width": 1080, "height": 1920}, {"codec_type": "audio", "codec_name": "aac"}]}
        self.assertTrue(Y.whole_short(ok, 66_000_000))
        self.assertFalse(Y.whole_short(ok, Y.UPLOAD_CAP + 1))
        wide = {**ok, "streams": [{**ok["streams"][0], "width": 1920, "height": 1080}]}
        self.assertFalse(Y.whole_short(wide, 1000))
        hevc = {**ok, "streams": [{**ok["streams"][0], "codec_name": "hevc"}]}
        self.assertFalse(Y.whole_short(hevc, 1000))
        self.assertFalse(Y.whole_short({**ok, "format": {"duration": "181"}}, 1000))

    def test_an_upload_is_tried_again_only_before_its_file_went_in(self) -> None:
        first = Y.attach_step()
        self.assertEqual(first, 2)  # goto, wait, attach: YouTube keeps a draft from the attach on
        self.assertTrue(Y.may_retry({"ok": False, "error": "recipe_failed", "step": "1:wait"}, first))
        self.assertFalse(Y.may_retry({"ok": False, "error": "recipe_failed", "step": "2:attach"}, first))
        self.assertFalse(Y.may_retry({"ok": False, "error": "recipe_failed", "step": "5:fill"}, first))
        self.assertTrue(Y.may_retry({"ok": False, "error": "busy"}, first))
        self.assertTrue(Y.may_retry({"ok": False, "error": "http_422", "detail": "x"}, first))
        self.assertTrue(Y.may_retry({"ok": False, "error": "off", "detail": "ConnectError"}, first))
        self.assertFalse(Y.may_retry({"ok": False, "error": "off", "detail": "no answer from egress in time"}, first))
        self.assertFalse(Y.may_retry({"ok": False, "error": "timeout", "step": "20:wait"}, first))
        self.assertFalse(Y.may_retry({"ok": True}, first))

    def test_the_thumbnail_is_due_only_for_an_uploaded_short(self) -> None:
        self.assertTrue(Y.thumb_due({"status": "done", "video_id": "abcdefghijk"}))
        self.assertFalse(Y.thumb_due({"status": "done", "video_id": "abcdefghijk", "thumb_set": "yes"}))
        self.assertFalse(Y.thumb_due({"status": "done", "video_id": "abcdefghijk", "thumb_tries": 3}))
        self.assertFalse(Y.thumb_due({"status": "check", "video_id": "abcdefghijk"}))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
