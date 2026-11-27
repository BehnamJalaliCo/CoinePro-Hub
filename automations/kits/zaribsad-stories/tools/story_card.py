"""One Zarib100x story picture (1080×1920 JPEG): a photoreal key-art background with the page's
brand layer on top (the page's colours: wine-black, Zarib Mint, oxblood, ivory; IRANYekanX Pro + IBM Plex; COMMON/brand/README.md),
rendered by Chromium (Persian shaped right, Latin runs isolated).

Usage: VENV/bin/python -I tools/story_card.py spec.json
spec = {
  "bg": "in/CR-0061.png",            # the AI picture (any size; cropped to fill 9:16)
  "focus": "50% 35%",                # optional: the picture's point kept in the crop
  "tab": "VIP · RECORD 30D",         # optional: the mono tab in the top bar (Latin, upper case)
  "kicker": "کارنامه‌ی سیگنال",       # the small label with the mint bar
  "headline": "۸۱ برد از [۱۳۳] سیگنال", # big title; [..] = the key word in the mint chip
  "lines": ["۳۰ روز گذشته، همه در کانال VIP"],   # 0–3 short lines
  "rows": [["نرخ برد", "۶۱٪"], ["ضریب سود", "۲/۱"]], # optional data card, 0–4 rows; a signed change («+2.1%», «−3.4%») gets ▲/▼ and its meaning colour
  "foot": "آمار از سایت تریدیار، ۲۳ آبان",   # optional small line (a source, a date)
  "cta_word": "الماس",               # the day's reply word (the CTA bar), or "" for none
  "cta": "رو ریپلای کن تا لینک VIP رایگان برات بیاد",  # optional, after the word
  "layout": "bottom",                # bottom | top | center: where the text block sits
  "out": "out/story_1.jpg"
}
No full stop at the end of any line, and no warning or disclaimer line (the owner). Instagram covers the top ~230 px (the bar) and
the bottom ~300 px (the reply box): the text stays between them. The top bar (the mark + «Zarib100x») sits at y 246–322."""

import html
import json
import os
import re
import sys
import tempfile

# ⟨2026-11-27⟩ the TYPE GATE (fa-type: after DotCoin's broken figures of F-0246): before the screenshot,
# Chrome's own report of the font that drew every glyph (a system-font fallback fails), text out of its box
# or over other text; a failing picture is not written (exit 2)
for _c in (os.environ.get("FATYPE", ""), "/home/studio/kits/fa-type",
           os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fa-type")):
    if _c and os.path.exists(os.path.join(_c, "fatype.py")):
        sys.path.insert(0, _c)
        break
import fatype as F  # noqa: E402
from pathlib import Path

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
PRO = Path("/home/studio/kits/fonts-pro")
COMMON = Path(os.environ.get("ZARIB_COMMON") or "/home/studio/kits/zaribsad-common")
OWN = COMMON / "fonts"
BRAND = COMMON / "brand"
# Zarib100x (COMMON/brand/README.md, 2026-11-26): wine-black ground, Zarib Mint accent, oxblood light, ivory text
GR, PN, MINT, OX, OXL, TX, MU = "#160A0E", "#241016", "#83CAAD", "#461A23", "#6B2A37", "#F4EFE6", "#A8979B"


def esc(t: str) -> str:
    t = re.sub(r"[.。،؛]\s*$", "", str(t).strip())  # never a full stop at the end
    return html.escape(t)


FA_DIG = str.maketrans("0123456789.,%", "۰۱۲۳۴۵۶۷۸۹/٬٪")  # ⟨2026-11-27⟩ decimals «/» (fa-type)


def iso(t: str) -> str:
    """Digits and Latin runs inside Persian (the font has Latin digits): a run with a Latin letter or $
    (Zarib100x, SOL/USDT, 50 USDT) stays Latin, isolated LTR; a run of digits alone becomes Persian digits."""
    out, last = [], 0
    for m in re.finditer(r"[A-Za-z0-9$][A-Za-z0-9$%.,/:+\-×#@_ ]*[A-Za-z0-9%$]|[A-Za-z0-9$]", t):
        out.append(html.escape(t[last:m.start()]))
        r = m.group(0)
        out.append(f'<bdi dir="ltr">{html.escape(r)}</bdi>' if re.search(r"[A-Za-z$]", r) else r.translate(FA_DIG))
        last = m.end()
    out.append(html.escape(t[last:]))
    return "".join(out)  # the text, html-escaped, with its runs set


def key(t: str) -> str:  # never a full stop at the end; escaped; digits/Latin runs set; [..] = the key word
    t = re.sub(r"[.。،؛]\s*$", "", str(t).strip())
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', iso(t))


UP, DN = "#35E06E", "#FF4D57"


def value(v: str) -> str:
    """A data-card value. A signed change («+2.1%», «−3.4%», «-۵٪») is a MEANING: ▲ + green or ▼ − red, the
    glyph always with the colour (COMMON/brand/README.md: mint is close to green, so colour alone never says it)."""
    t = str(v).strip()
    if re.match(r"^[+▲]", t):
        return f'<bdi dir="ltr" style="color:{UP}">{F.symbols("▲")}+{key(t.lstrip("+▲ "))}</bdi>'
    if re.match(r"^[-−▼]", t):
        return f'<bdi dir="ltr" style="color:{DN}">{F.symbols("▼")}−{key(t.lstrip("-−▼ "))}</bdi>'
    return key(t)


def faces() -> str:
    rows = [("ZF", PRO / "IRANYekanX-ExtraBlack.ttf", 950), ("ZF", PRO / "IRANYekanX-ExtraBold.ttf", 800),
            ("ZF", PRO / "IRANYekanX-Bold.ttf", 700), ("ZF", PRO / "IRANYekanX-Regular.ttf", 400),
            ("ZM", OWN / "IBMPlexMono-Medium.ttf", 500), ("ZM", OWN / "IBMPlexMono-SemiBold.ttf", 600),
            ("ZC", OWN / "IBMPlexSansCondensed-Bold.ttf", 700)]
    return "".join(f'@font-face{{font-family:{f};font-weight:{w};src:url("file://{p}");}}' for f, p, w in rows)


def page(s: dict) -> str:
    rows = "".join(f'<div class="row"><span>{key(a)}</span><b>{value(b)}</b></div>' for a, b in s.get("rows") or [])
    lines = "".join(f"<p>{key(x)}</p>" for x in (s.get("lines") or [])[:3])
    word = str(s.get("cta_word") or "").strip()
    cta = (f'<div class="cta"><span class="w">{esc(word)}</span><span>{key(s.get("cta") or "رو ریپلای کن تا لینک VIP رایگان برات بیاد")}</span></div>'
           if word else "")
    foot = f'<div class="foot">{key(s["foot"])}</div>' if s.get("foot") else ""
    lay = str(s.get("layout") or "bottom")
    place = {"top": "flex-start", "center": "center"}.get(lay, "flex-end")
    scrim = {"top": "180deg", "center": "180deg"}.get(lay, "0deg")
    tab = esc(s.get("tab") or "")  # optional mono tab (Latin): «VIP · RECORD 30D», «MARKET · 08:30»
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}{F.SYM_CSS}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: 1080px; height: 1920px; background: {GR}; font-family: ZF; color: {TX}; overflow: hidden; }}
.bg {{ position: absolute; inset: 0; background: url("file://{Path(s['bg']).resolve()}") center/cover no-repeat;
      background-position: {esc(s.get('focus') or '50% 40%')}; }}
.scrim {{ position: absolute; inset: 0; background: linear-gradient({scrim}, rgba(22,10,14,.95) 0%, rgba(22,10,14,.84) 36%, rgba(22,10,14,0) 68%); }}
.glow {{ position: absolute; inset: 0; background: radial-gradient(900px 600px at 85% 10%, rgba(107,42,55,.55), rgba(22,10,14,0) 70%); }}
.bar {{ position: absolute; top: 246px; left: 56px; right: 56px; height: 76px; display: flex; align-items: center; justify-content: space-between;
       direction: ltr; background: rgba(22,10,14,.74); border: 2px solid rgba(244,239,230,.14); border-radius: 18px; padding: 0 22px 0 12px; }}
.bar .lk {{ display: flex; align-items: center; gap: 14px; font-family: ZC; font-weight: 700; font-size: 36px; }}
.bar img {{ width: 54px; height: 54px; border-radius: 50%; border: 3px solid {MINT}; }}
.bar .x {{ color: {MINT}; }}
.bar .tb {{ font-family: ZM; font-weight: 500; font-size: 24px; letter-spacing: 2px; color: {MU}; }}
.bar .dot {{ display: inline-block; width: 14px; height: 14px; border-radius: 50%; background: {MINT}; margin-left: 12px; vertical-align: middle; }}
.box {{ position: absolute; left: 64px; right: 64px; top: 380px; bottom: 330px; display: flex; flex-direction: column;
       justify-content: {place}; gap: 26px; }}
.kick {{ align-self: flex-start; display: flex; align-items: center; gap: 14px; font-weight: 800; font-size: 38px; }}
.kick::before {{ content: ""; width: 10px; height: 44px; background: {MINT}; border-radius: 3px; }}
h1 {{ font-size: 96px; line-height: 1.22; font-weight: 950; }}
.k {{ background: {MINT}; color: {GR}; border-radius: 18px; padding: 0 14px; }}
p {{ font-size: 46px; line-height: 1.5; font-weight: 400; }}
p .k {{ background: none; color: {MINT}; padding: 0; font-weight: 700; }}
.card {{ background: rgba(36,16,22,.88); border: 2px solid rgba(244,239,230,.14); border-top: 5px solid {MINT}; border-radius: 26px; padding: 14px 36px; }}
.row {{ display: flex; justify-content: space-between; align-items: baseline; padding: 14px 0; font-size: 42px;
       border-bottom: 1px solid rgba(244,239,230,.12); }}
.row:last-child {{ border-bottom: 0; }}
.row b {{ font-size: 56px; font-weight: 950; color: {TX}; }}
.cta {{ display: flex; align-items: center; gap: 22px; background: {TX}; color: {GR}; font-size: 40px; font-weight: 800; border-radius: 26px;
       padding: 22px 28px; line-height: 1.4; }}
.cta .w {{ flex: none; color: {GR}; background: {MINT}; border-radius: 16px; padding: 6px 22px; font-weight: 950; font-size: 48px; }}
.foot {{ font-size: 30px; color: {MU}; }}
</style></head><body><div class="bg"></div><div class="scrim"></div><div class="glow"></div>
<div class="bar"><div class="lk"><img src="file://{BRAND}/profile_round.png"><span>Zarib<span class="x">100x</span></span></div>
<div class="tb">{tab}<span class="dot"></span></div></div>
<div class="box">{f'<div class="kick">{key(s["kicker"])}</div>' if s.get("kicker") else ""}
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
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(400)
                pg.evaluate("document.fonts.ready")
                if not F.guard(pg, out, "zaribsad-stories/story_card", numbers="any", overlap=False):
                    raise SystemExit(2)
                pg.screenshot(path=str(png), full_page=False)
            finally:
                b.close()
        from PIL import Image

        Image.open(png).convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
