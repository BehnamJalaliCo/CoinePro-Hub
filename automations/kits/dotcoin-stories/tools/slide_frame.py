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
~300 px (the reply box): the frame sits just inside them.

⟨2026-11-27⟩ THE TYPE GATE (fa-type, after DotCoin's broken figures of F-0246): every text of the frame
and of the fallback text block is set by the number rules, drawn ONLY by IRANYekanX (Chrome reports the
font of every glyph: a system-font fallback fails), stays inside its box/chip and off the other text.
A failing slide is NOT written (exit 2) and qc/type_gate.jsonl records every verdict with the picture's
sha256 (tools/deliver_check.py reads it). The words ChatGPT drew INTO the slide are not text to the gate:
the session reads them (README step 5, the typography check)."""

import html
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _c in (os.environ.get("FATYPE", ""), "/home/studio/kits/fa-type", str(HERE.parent.parent / "fa-type")):
    if _c and Path(_c, "fatype.py").exists():
        sys.path.insert(0, _c)
        break
import fatype as F  # noqa: E402

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FONTS = Path("/home/studio/kits/fonts-pro")
BRAND = Path("/home/studio/kits/dotcoin-common/brand")
MUSTARD, BLACK, WHITE = "#F3C242", "#000000", "#FFFFFF"
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
BANDS = [(0, 370), (1390, 1920)]  # the frame's own zones: only [data-frame] text may sit there


def esc(t: str) -> str:
    t = re.sub(r"[.。،؛]\s*$", "", F.normalize(str(t)).strip())  # never a full stop at the end
    t = F.symbols(html.escape(t))
    return re.sub(r"[۰-۹]+(?:[/\u066c][۰-۹]+)*٪?", lambda m: f"<bdi>{m.group(0)}</bdi>", t)


def key(t: str) -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', esc(t))


def mustard_under(bg: str) -> bool:
    """⟨2026-11-27⟩ Whether the slide is mustard where the number chip sits (a mustard chip would vanish)."""
    try:
        from PIL import Image, ImageOps

        with Image.open(bg) as im:
            im = ImageOps.fit(im.convert("RGB"), (1080, 1920))
            r, g, b = im.crop((40, 250, 300, 330)).resize((1, 1)).getpixel((0, 0))
        return abs(r - 243) + abs(g - 194) + abs(b - 66) < 110
    except Exception:  # noqa: BLE001 - no picture yet: the usual chip
        return False


def page(s: dict) -> str:
    n, of = int(s.get("n") or 0), int(s.get("of") or 0)
    dark = mustard_under(str(s.get("bg") or ""))
    count = f'<div class="num{" dark" if dark else ""}" data-frame><bdi>{F.fa(n)}</bdi> از <bdi>{F.fa(of)}</bdi></div>' if n and of else ""
    word = str(s.get("word") or "").strip()
    cta = (
        f'<div class="cta" data-frame><span class="w">«{esc(word)}»</span> '
        f'{esc(s.get("cta") or "رو دایرکت کن تا خلاصه‌ی درس برات بیاد")}</div>'
        if word
        else ""
    )
    mark = (
        f'<div class="mark" data-frame><img src="file://{BRAND}/logo_round.png"><b>DotCoin<span class="k2">Me</span></b></div>'
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
{F.SYM_CSS}
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
.num.dark {{ background: {BLACK}; color: {MUSTARD}; }}
.box {{ position: absolute; left: 64px; right: 64px; top: 380px; bottom: 470px; display: flex; flex-direction: column; gap: 22px; }}
h1 {{ font-size: 88px; line-height: 1.25; font-weight: 900; text-shadow: 0 4px 18px rgba(0,0,0,.55); }}
.k {{ background: {MUSTARD}; color: {BLACK}; border-radius: 22px; padding: 0 18px; }}
p {{ font-size: 46px; line-height: 1.55; font-weight: 600; text-shadow: 0 3px 14px rgba(0,0,0,.6); }}
.cta {{ position: absolute; left: 56px; right: 56px; bottom: 318px; background: rgba(0,0,0,.86); color: {WHITE};
       border: 3px solid {MUSTARD}; font-size: 38px; font-weight: 800; border-radius: 34px; padding: 20px 30px; line-height: 1.45; text-align: center; }}
.cta .w {{ color: {BLACK}; background: {MUSTARD}; border-radius: 16px; padding: 2px 16px; }}
</style></head><body><div class="bg"></div>{mark}{count}{text}{cta}</body></html>"""


def main(spec_path: str) -> int:
    s = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(s["out"])
    verdict = F.render(page(s), out, bands=BANDS, fonts_allowed=("IRANYekanX",), tool="dotcoin-stories/slide_frame")
    F.report(verdict, out)
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
