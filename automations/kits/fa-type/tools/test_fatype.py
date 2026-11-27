# -*- coding: utf-8 -*-
"""fa-type's own proof (2026-11-27): every failure DotCoin's F-0246 slides had must be caught, and a
clean page must pass. Run after any change to fatype.py:
    VENV/bin/python -I /home/studio/kits/fa-type/tools/test_fatype.py
Exit 0 = all cases right."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fatype as F  # noqa: E402

FONTS = "/home/studio/kits/fonts-pro"
HEAD = (f'<!doctype html><html dir="rtl"><meta charset="utf-8"><style>'
        f'@font-face{{font-family:Yk;font-weight:900;src:url("file://{FONTS}/IRANYekanXFaNum-Black.ttf")}}'
        f'@font-face{{font-family:Yk;font-weight:500;src:url("file://{FONTS}/IRANYekanXFaNum-Medium.ttf")}}'
        'body{margin:0;width:1080px;height:1920px;background:#F4F0E6;font-family:Yk;font-weight:500}'
        '.k{background:#F3C242;border-radius:16px;padding:0 14px}</style><body>')
CASES = {
    # what F-0246 did: the figures in a family the page never loaded → a system font drew them
    "system font for the figures": (HEAD + '<div style="position:absolute;top:500px;right:60px;font-family:\'IRANYekanX FaNum\';'
                                    'font-weight:950;font-size:200px">۵٬۰۰۰</div>', "SYSTEM font"),
    "a face that fails to load": (HEAD.replace("IRANYekanXFaNum-Medium.ttf", "IRANYekanXFaNum-Nope.ttf")
                                  + '<p style="position:absolute;top:600px;right:60px;font-size:60px">حساب ۵۰۰۰ دلاری</p>', "did not load"),
    "apostrophe as separator": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">حساب ۵’۰۰۰ دلاری</p>', "apostrophe"),
    "latin digits": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">قیمت 60480 دلار</p>', "Latin digit"),
    "decimal as full stop": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">رشد ۹.۶٪</p>', "decimal mark"),
    "minus beside a figure": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">افت (۹/۶٪-)</p>', "minus"),
    "chip narrower than its text": (HEAD + '<h1 style="position:absolute;top:500px;right:60px;font-size:96px;font-weight:900">ترس امروز: '
                                    '<span class="k" style="display:inline-block;width:200px;white-space:nowrap">۱۲ از ۱۰۰</span></h1>', "overflows its box"),
    "text over text": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">حد ضرر جدید ۸٪</p>'
                       '<p style="position:absolute;top:615px;right:90px;font-size:60px">ضرر می‌شه ۱۰۰ دلار</p>', "text over text"),
    "arrow the font lacks": (HEAD + '<p style="position:absolute;top:600px;right:60px;font-size:60px">۴٪ ← ۱۲۵۰ دلار</p>', "SYSTEM font"),
    "text in the calm band": (HEAD + '<p style="position:absolute;top:1500px;right:60px;font-size:60px">حجم پوزیشن</p>', "calm band"),
    "column too narrow": (HEAD + '<div style="position:absolute;top:600px;right:60px;width:300px;white-space:nowrap;font-size:60px">'
                          'حد ضرر زیر کف: ۵۸٬۰۶۰ دلار</div>', "wider or taller"),
    "clean page": (HEAD + '<h1 style="position:absolute;top:500px;right:60px;left:60px;font-size:96px;font-weight:900">ترس امروز: '
                   '<span class="k">۱۲ از ۱۰۰</span></h1><p style="position:absolute;top:760px;right:60px;left:60px;font-size:52px">'
                   'ورود: ۶۰٬۴۸۰ دلار، حد ضرر ۴٪، حجم ۱۲۵۰ دلار، حدود ۰/۰۲۱ بیت‌کوین</p>', None),
}


def main() -> int:
    import tempfile

    from playwright.sync_api import sync_playwright

    wrong = 0
    tmp = Path(tempfile.mkdtemp())
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=F.CHROME, headless=True, args=["--allow-file-access-from-files"])
        try:
            for name, (html, expect) in CASES.items():
                pg = b.new_page(viewport={"width": 1080, "height": 1920})
                f = tmp / "case.html"
                f.write_text(html, encoding="utf-8")
                pg.goto(f.as_uri())  # (file://: a page from set_content may not load file:// fonts)
                pg.wait_for_timeout(200)
                v = F.gate(pg, bands=[(0, 370), (1390, 1920)])
                pg.close()
                # the case's own failure, and (but for the font cases) the fonts all loaded
                fonts_fine = not any("did not load" in q for q in v["problems"]) or expect == "did not load"
                hit = (any(expect in q for q in v["problems"]) and fonts_fine) if expect else v["ok"]
                wrong += not hit
                print(("ok   " if hit else "WRONG"), name, "" if hit else v["problems"])
        finally:
            b.close()
            for f in tmp.iterdir():
                f.unlink()
            tmp.rmdir()
    nums = {(5000, None): "۵۰۰۰", (60480, None): "۶۰٬۴۸۰", (9.6, None): "۹/۶", (0.0207, 3): "۰/۰۲۱", (1250000, None): "۱٬۲۵۰٬۰۰۰"}
    for (x, d), want in nums.items():
        got = F.num(x, d)
        wrong += got != want
        print(("ok   " if got == want else "WRONG"), f"num({x}) = {got}")
    for s, want in {"۵’۰۰۰": "۵۰۰۰", "60,480": "۶۰٬۴۸۰", "۹.۶٪": "۹/۶٪", "۹٫۶٪": "۹/۶٪", "۱٬۲۵۰ دلار": "۱۲۵۰ دلار"}.items():
        got = F.normalize(s)
        wrong += got != want
        print(("ok   " if got == want else "WRONG"), f"normalize({s}) = {got}")
    print("ALL RIGHT" if not wrong else f"{wrong} WRONG")
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main())
