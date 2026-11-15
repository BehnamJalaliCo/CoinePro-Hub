"""One Zarib×100 story picture (1080×1920 JPEG): a photoreal key-art background with the page's
brand layer on top, in IRANYekanX Eco, rendered by Chromium (Persian shaped right).

Usage: VENV/bin/python -I tools/story_card.py spec.json
spec = {
  "bg": "in/CR-0061.png",            # the AI picture (any size; cropped to fill 9:16)
  "focus": "50% 35%",                # optional: the picture's point kept in the crop
  "kicker": "کارنامه‌ی سیگنال",       # the small teal label
  "headline": "۸۱ برد از [۱۳۳] سیگنال", # big title; [..] = the key word in teal
  "lines": ["۳۰ روز گذشته، همه در کانال VIP"],   # 0–3 short lines
  "rows": [["نرخ برد", "۶۱٪"], ["ضریب سود", "۲٫۱"]], # optional data card, 0–4 rows
  "foot": "آمار از سایت تریدیار، ۲۳ آبان",   # optional small line (a source, a date)
  "cta_word": "الماس",               # the day's reply word (the CTA bar), or "" for none
  "cta": "رو ریپلای کن تا لینک VIP رایگان برات بیاد",  # optional, after the word
  "layout": "bottom",                # bottom | top | center: where the text block sits
  "out": "out/story_1.jpg"
}
No full stop at the end of any line, and no warning or disclaimer line (the owner). Instagram covers the top ~230 px (the bar) and
the bottom ~300 px (the reply box): the text stays between them."""

import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FONTS = Path("/home/studio/kits/fonts-eco")
BRAND = Path("/home/studio/kits/zaribsad-common/brand")
NAVY, TEAL, WHITE = "#030B26", "#0FB5AE", "#F4F7FF"


def esc(t: str) -> str:
    t = re.sub(r"[.。]\s*$", "", str(t).strip())  # never a full stop at the end
    return html.escape(t)


def key(t: str) -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', esc(t))


def page(s: dict) -> str:
    rows = "".join(f'<div class="row"><span>{esc(a)}</span><b>{esc(b)}</b></div>' for a, b in s.get("rows") or [])
    lines = "".join(f"<p>{key(x)}</p>" for x in (s.get("lines") or [])[:3])
    word = str(s.get("cta_word") or "").strip()
    cta = (f'<div class="cta"><span class="w">«{esc(word)}»</span> {esc(s.get("cta") or "رو ریپلای کن تا لینک VIP رایگان برات بیاد")}</div>'
           if word else "")
    foot = f'<div class="foot">{esc(s["foot"])}</div>' if s.get("foot") else ""
    place = {"top": "flex-start", "center": "center"}.get(str(s.get("layout") or "bottom"), "flex-end")
    scrim = {"top": "180deg", "center": "180deg"}.get(str(s.get("layout") or "bottom"), "0deg")
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>
@font-face {{ font-family: Eco; font-weight: 400; src: url("file://{FONTS}/IRANYekanXFaNum-Regular.ttf"); }}
@font-face {{ font-family: Eco; font-weight: 700; src: url("file://{FONTS}/IRANYekanXFaNum-Bold.ttf"); }}
@font-face {{ font-family: EcoEn; font-weight: 700; src: url("file://{FONTS}/IRANYekanX-Bold.ttf"); }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: 1080px; height: 1920px; background: {NAVY}; font-family: Eco; color: {WHITE}; overflow: hidden; }}
.bg {{ position: absolute; inset: 0; background: url("file://{Path(s['bg']).resolve()}") center/cover no-repeat;
      background-position: {esc(s.get('focus') or '50% 40%')}; }}
.scrim {{ position: absolute; inset: 0; background: linear-gradient({scrim}, rgba(3,11,38,.94) 0%, rgba(3,11,38,.82) 34%, rgba(3,11,38,.0) 66%); }}
.mark {{ position: absolute; top: 250px; right: 64px; display: flex; align-items: center; gap: 18px;
        background: rgba(3,11,38,.72); border: 2px solid {TEAL}; border-radius: 60px; padding: 10px 26px 10px 12px; }}
.mark img {{ width: 72px; height: 72px; border-radius: 50%; border: 3px solid {TEAL}; }}
.mark b {{ font-family: EcoEn; font-size: 34px; font-weight: 700; direction: ltr; }}
.box {{ position: absolute; left: 64px; right: 64px; top: 380px; bottom: 330px; display: flex; flex-direction: column;
       justify-content: {place}; gap: 26px; }}
.kick {{ align-self: flex-start; background: {TEAL}; color: {NAVY}; font-weight: 700; font-size: 38px; padding: 8px 28px; border-radius: 40px; }}
h1 {{ font-size: 92px; line-height: 1.22; font-weight: 700; }}
.k {{ color: {TEAL}; }}
p {{ font-size: 46px; line-height: 1.5; font-weight: 400; }}
.card {{ background: rgba(3,11,38,.86); border: 2px solid {TEAL}; border-radius: 34px; padding: 18px 36px; }}
.row {{ display: flex; justify-content: space-between; align-items: baseline; padding: 14px 0; font-size: 44px;
       border-bottom: 1px solid rgba(15,181,174,.35); }}
.row:last-child {{ border-bottom: 0; }}
.row b {{ color: {TEAL}; font-size: 54px; }}
.cta {{ background: {WHITE}; color: {NAVY}; font-size: 42px; font-weight: 700; border-radius: 30px; padding: 24px 34px; line-height: 1.45; }}
.cta .w {{ color: {TEAL}; background: {NAVY}; border-radius: 16px; padding: 2px 16px; }}
.foot {{ font-size: 30px; opacity: .78; }}
</style></head><body><div class="bg"></div><div class="scrim"></div>
<div class="mark"><img src="file://{BRAND}/profile_round.png"><b>Zarib×100</b></div>
<div class="box">{f'<div class="kick">{esc(s["kicker"])}</div>' if s.get("kicker") else ""}
<h1>{key(s.get("headline") or "")}</h1>{lines}{f'<div class="card">{rows}</div>' if rows else ""}{cta}{foot}</div>
</body></html>"""


def main(spec_path: str) -> None:
    s = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(s["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "story.html"
        page_file.write_text(page(s), encoding="utf-8")
        png = Path(tmp) / "story.png"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--allow-file-access-from-files"])
            try:
                pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
                pg.goto(page_file.as_uri())
                pg.wait_for_timeout(400)
                pg.evaluate("document.fonts.ready")
                pg.screenshot(path=str(png), full_page=False)
            finally:
                b.close()
        from PIL import Image

        Image.open(png).convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    subprocess.run(["pkill", "-f", "[c]hromium-1243/chrome-linux64/chrome"], check=False)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
