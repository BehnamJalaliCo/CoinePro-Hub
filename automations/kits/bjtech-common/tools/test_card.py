#!/usr/bin/env python3
"""The page's handle and counters (the owner, 2026-11-19), checked without a browser:
    python3 -I COMMON/tools/test_card.py
- a counter is «n از m» in Persian digits only, one RTL run: card.py's counter() turns any digits into it and
  check_counter() refuses a mixed one; a story's HTML draws it so;
- every handle pill shows the round profile logo (COMMON/brand/logo_round.png), never the coloured dot;
- the stage (REELS/motion/stage.html) draws the logo in its handle pill and every «… از …» counter through COUNTER()."""
import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.environ.get("BJ_STAGE", os.path.join(HERE, "..", "..", "bjtech-reels", "motion", "stage.html"))
_spec = importlib.util.spec_from_file_location("bj_card", os.path.join(HERE, "card.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


class Counters(unittest.TestCase):
    def test_any_digits_in_persian_digits_out(self):
        for given in ("۷ از 12", "7 از 12", "7/12", "۷/۱۲", "7 of 12", " ۷ از ۱۲ "):
            self.assertEqual(C.counter(given), "۷ از ۱۲", given)

    def test_a_mixed_or_odd_counter_is_refused(self):
        for bad in ("۷ از 12", "7 از ۱۲", "۱۲ ۷", "از ۱۲"):
            with self.assertRaises(ValueError, msg=bad):
                C.check_counter(bad)
        with self.assertRaises(ValueError):
            C.counter("هفت از دوازده")

    def test_a_storys_counter_is_one_rtl_run_of_persian_digits(self):
        page = C.page({"type": "story", "pillar": "news", "title": "تیتر", "badge": "۷ از 12", "layout": "list",
                       "list": ["یک"]}, 1080, 1920)
        m = re.search(r'<div class="counter"[^>]*><bdi dir="rtl">([^<]*)</bdi></div>', page)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "۷ از ۱۲")
        # (a list's markers too: Persian digits on screen)
        self.assertEqual(re.findall(r'<div class="li"><b>([^<]*)</b>', page), ["۱"])
        self.assertIn("direction:rtl", C.CSS if hasattr(C, "CSS") else page)


class Handle(unittest.TestCase):
    def test_every_handle_pill_shows_the_round_logo(self):
        self.assertTrue(os.path.exists(C.LOGO_FILE))
        for kind in ("story", "flash", "cover"):
            page = C.page({"type": kind, "lumen": True, "pillar": "news", "title": "تیتر"}, 1080, 1920)
            pills = re.findall(r'<div class="handle"[^>]*>(.*?)</div>', page)
            self.assertTrue(pills, kind)
            for pill in pills:
                self.assertIn('class="logo"', pill, kind)
                self.assertNotIn('class="dot"', pill, kind)

    def test_the_stage_draws_the_logo_and_counts_with_counter(self):
        stage = open(STAGE, encoding="utf-8").read()
        self.assertIn("/*LOGOR*/", stage)
        brand = stage[stage.index("function brand("):stage.index("function chapterChip(")]
        self.assertIn("X.drawImage(LOGOR", brand)
        i = stage.index("function COUNTER(")
        rest = stage[:i] + stage[stage.index("\n}\n", i):]  # (COUNTER's own body is the one place it is written)
        self.assertFalse(re.search(r"\$\{[^}]*\}\s*از\s*\$\{", rest), "a counter as a template string")
        self.assertGreaterEqual(rest.count("COUNTER("), 2)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
