"""One DotCoin.me (@DotCoinMe) story slide (1080×1920 JPEG): ChatGPT's designed slide with the
page's frame on top — the round mark with «DotCoinMe», the slide's number and the day's reply word —
in IRANYekanX Pro, rendered by Chromium (Persian shaped right). (2026-11-17, the owner: the day's
educational stories designed by ChatGPT in one chat, «اسلاید های مجزا».)

Usage: VENV/bin/python -I tools/slide_frame.py spec.json
spec = {
  "bg": "in/slide_03.png",          # ChatGPT's slide (any size; cropped to fill 9:16)
  "focus": "50% 50%",               # optional: the point kept in the crop
  "n": 3, "of": 12,                 # the slide's number (shown «۳ از ۱۲»); 0 = none
  "word": "کیف‌پول",                 # the day's reply word (the CTA bar), "" = no bar
  "cta": "رو دایرکت کن تا خلاصه‌ی درس برات بیاد",   # optional, after the word
  "mark": true,                     # the round mark + «DotCoinMe» (false: the slide has it)
  # the FALLBACK only (a slide whose Persian ChatGPT got wrong, made again without text):
  "headline": "کیف‌پول [سرد] چیه؟",   # [..] = the key word on a mustard chip
  "lines": ["کلید تو، بیرون از اینترنت"], # 0–4 short lines
  "layout": "bottom",               # bottom | top | center: where that text block sits
  "out": "out/story_3.jpg"
}
No full stop at the end of any line. Instagram covers the top ~230 px (the bar) and the bottom
~300 px (the reply box): the frame sits just inside them."""

import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FONTS = Path("/home/studio/kits/fonts-pro")
BRAND = Path("/home/studio/kits/dotcoin-common/brand")
MUSTARD, BLACK, WHITE = "#F3C242", "#000000", "#FFFFFF"
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def esc(t: str) -> str:
    t = re.sub(r"[.。،؛]\s*$", "", str(t).strip())  # never a full stop at the end
    return html.escape(t)


def key(t: str) -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', esc(t))


def page(s: dict) -> str:
    n, of = int(s.get("n") or 0), int(s.get("of") or 0)
    count = f'<div class="num">{f"{n} از {of}".translate(FA)}</div>' if n and of else ""
    word = str(s.get("word") or "").strip()
    cta = (
        f'<div class="cta"><span class="w">«{esc(word)}»</span> '
        f'{esc(s.get("cta") or "رو دایرکت کن تا خلاصه‌ی درس برات بیاد")}</div>'
        if word
        else ""
    )
    mark = (
        f'<div class="mark"><img src="file://{BRAND}/logo_round.png"><b>DotCoin<span class="k2">Me</span></b></div>'
        if s.get("mark", True)
        else ""
    )
    head = str(s.get("headline") or "").strip()
    text = ""
    if head:
        lines = "".join(f"<p>{key(x)}</p>" for x in (s.get("lines") or [])[:4])
        place = {"top": "flex-start", "center": "center"}.get(str(s.get("layout") or "bottom"), "flex-end")
        text = f'<div class="box" style="justify-content:{place}"><h1>{key(head)}</h1>{lines}</div>'
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>
@font-face {{ font-family: Yk; font-weight: 400; src: url("file://{FONTS}/IRANYekanXFaNum-Regular.ttf"); }}
@font-face {{ font-family: Yk; font-weight: 600; src: url("file://{FONTS}/IRANYekanXFaNum-DemiBold.ttf"); }}
@font-face {{ font-family: Yk; font-weight: 800; src: url("file://{FONTS}/IRANYekanXFaNum-ExtraBold.ttf"); }}
@font-face {{ font-family: Yk; font-weight: 900; src: url("file://{FONTS}/IRANYekanXFaNum-Black.ttf"); }}
@font-face {{ font-family: YkEn; font-weight: 800; src: url("file://{FONTS}/IRANYekanX-ExtraBold.ttf"); }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: 1080px; height: 1920px; background: {BLACK}; font-family: Yk; color: {WHITE}; overflow: hidden; }}
.bg {{ position: absolute; inset: 0; background: url("file://{Path(s["bg"]).resolve()}") center/cover no-repeat;
      background-position: {esc(s.get("focus") or "50% 50%")}; }}
.mark {{ position: absolute; top: 246px; right: 56px; display: flex; align-items: center; gap: 14px;
        background: rgba(0,0,0,.78); border: 2px solid {MUSTARD}; border-radius: 60px; padding: 8px 24px 8px 10px; }}
.mark img {{ width: 64px; height: 64px; border-radius: 50%; }}
.mark b {{ font-family: YkEn; font-size: 30px; font-weight: 800; direction: ltr; color: {WHITE}; }}
.k2 {{ color: {MUSTARD}; }}
.num {{ position: absolute; top: 258px; left: 56px; background: {MUSTARD}; color: {BLACK}; font-weight: 800;
       font-size: 32px; padding: 8px 24px; border-radius: 40px; }}
.box {{ position: absolute; left: 64px; right: 64px; top: 380px; bottom: 470px; display: flex; flex-direction: column; gap: 22px; }}
h1 {{ font-size: 88px; line-height: 1.25; font-weight: 900; text-shadow: 0 4px 18px rgba(0,0,0,.55); }}
.k {{ background: {MUSTARD}; color: {BLACK}; border-radius: 22px; padding: 0 18px; }}
p {{ font-size: 46px; line-height: 1.55; font-weight: 600; text-shadow: 0 3px 14px rgba(0,0,0,.6); }}
.cta {{ position: absolute; left: 56px; right: 56px; bottom: 318px; background: rgba(0,0,0,.86); color: {WHITE};
       border: 3px solid {MUSTARD}; font-size: 38px; font-weight: 800; border-radius: 34px; padding: 20px 30px; line-height: 1.45; text-align: center; }}
.cta .w {{ color: {BLACK}; background: {MUSTARD}; border-radius: 16px; padding: 2px 16px; }}
</style></head><body><div class="bg"></div>{mark}{count}{text}{cta}</body></html>"""


def main(spec_path: str) -> None:
    s = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(s["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "slide.html"
        page_file.write_text(page(s), encoding="utf-8")
        png = Path(tmp) / "slide.png"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True,
                                  args=["--allow-file-access-from-files"])  # fmt: skip
            try:
                pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
                pg.goto(page_file.as_uri())
                pg.wait_for_timeout(400)
                pg.evaluate("document.fonts.ready")
                pg.screenshot(path=str(png), full_page=False)
            finally:
                b.close()
        from PIL import Image

        Image.open(png).convert("RGB").save(out, "JPEG", quality=93, optimize=True)
    subprocess.run(["pkill", "-f", "[c]hromium-1243/chrome-linux64/chrome"], check=False)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
