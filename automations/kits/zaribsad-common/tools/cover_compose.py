"""Zarib100x — the cover, composed exactly (cover/COVER_SYSTEM.md): ChatGPT's hero plate (no text in it) under
the family's fixed type layer, rendered by Chromium in the brand fonts. Every cover of the page comes out of
this one template: the grid reads as one family.

usage: PY -I COMMON/tools/cover_compose.py spec.json
spec = {
  "plate": "in/CR-0123.png",        # ChatGPT's picture (the cover task with the board attached); any size, cover-fit
  "focus": "50% 40%",               # optional: the plate's point kept in the crop
  "kind": "COIN",                   # COIN | LESSON | CAMPAIGN | MARKET | NEWS (the mono tag; one of these five)
  "tag": "SOL/USDT",                # the tag's second part (Latin, mono): a ticker, «LESSON 07», an exchange…
  "title": ["سولانا [نصف] شد", "حالا چی؟"],   # 1–2 lines, 2–5 words in all; [..] = the key word (violet chip)
  "number": "-48.8%",               # optional: ONE real number of the reel (Latin, condensed); "" for none
  "number_dir": "down",             # up | down | flat: the number's meaning colour
  "brief": 41,                      # the reel's brief number (zn/zs NNN) — the small mono counter
  "out": "out/cover.jpg"
}
Prints the file. No full stop at the end of the title (stripped). Persian is shaped by Chromium (IRANYekanX
Pro ExtraBlack); Latin runs are isolated LTR. Check the result at full size AND with cover_sheet.py."""

import html
import json
import re
import sys
import tempfile
from pathlib import Path

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
PRO = Path("/home/studio/kits/fonts-pro")
COMMON = Path(__file__).resolve().parent.parent
OWN = COMMON / "fonts"
MARK = COMMON / "brand" / "profile_round.png"
OB, OB2, VI, VIL, PT, MU, UP, DN = "#0A0814", "#141022", "#8A3FFC", "#B28CFF", "#EEEAF8", "#9A95B3", "#19C37D", "#F2445A"
KINDS = {"COIN", "LESSON", "CAMPAIGN", "MARKET", "NEWS"}


def clean(t: str) -> str:  # raw text, never a full stop at the end (escaped later by iso)
    return re.sub(r"[.،؛:]+\s*$", "", str(t).strip())


FA_DIG = str.maketrans("0123456789.,%", "۰۱۲۳۴۵۶۷۸۹٫٬٪")


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


def key(t: str) -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', iso(clean(t)))


def faces() -> str:
    rows = [("ZF", PRO / "IRANYekanX-ExtraBlack.ttf", 950), ("ZF", PRO / "IRANYekanX-Bold.ttf", 700),
            ("ZF", PRO / "IRANYekanX-Regular.ttf", 400), ("ZM", OWN / "IBMPlexMono-Medium.ttf", 500),
            ("ZM", OWN / "IBMPlexMono-SemiBold.ttf", 600), ("ZC", OWN / "IBMPlexSansCondensed-Bold.ttf", 700)]
    return "".join(f'@font-face{{font-family:{f};font-weight:{w};src:url("file://{p}");}}' for f, p, w in rows)


def page(s: dict) -> str:
    kind = str(s.get("kind") or "COIN").upper()
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {sorted(KINDS)}")
    lines = [ln for ln in (s.get("title") or []) if str(ln).strip()][:2]
    if not lines:
        raise SystemExit("a title is required")
    num = str(s.get("number") or "").strip()
    col = {"up": UP, "down": DN}.get(str(s.get("number_dir") or "flat"), PT)
    num_html = f'<div class="num" style="color:{col}">{html.escape(num.replace("-", "−"))}</div>' if num else ""
    brief = f"BRIEF {int(s.get('brief') or 0):03d}" if s.get("brief") else "BRIEF"
    plate = Path(s["plate"]).resolve()
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;background:{OB};overflow:hidden;color:{PT};font-family:ZF}}
.plate{{position:absolute;left:0;right:0;top:0;height:1300px;background:url("file://{plate}") center/cover no-repeat;
  background-position:{html.escape(str(s.get('focus') or '50% 40%'))}}}
.fade{{position:absolute;left:0;right:0;top:760px;height:560px;background:linear-gradient(180deg,rgba(10,8,20,0),{OB} 92%)}}
.ground{{position:absolute;left:0;right:0;top:1300px;bottom:0;background:{OB}}}
.glow{{position:absolute;inset:0;background:radial-gradient(900px 700px at 80% 22%,rgba(138,63,252,.20),rgba(10,8,20,0) 70%)}}
.frame{{position:absolute;left:36px;right:36px;top:236px;bottom:236px;border:2px solid rgba(238,234,248,.16);border-radius:6px}}
.tick{{position:absolute;width:44px;height:44px;border-color:{VI};border-style:solid;border-width:0}}
.t1{{left:30px;top:230px;border-left-width:6px;border-top-width:6px}} .t2{{right:30px;top:230px;border-right-width:6px;border-top-width:6px}}
.t3{{left:30px;bottom:230px;border-left-width:6px;border-bottom-width:6px}} .t4{{right:30px;bottom:230px;border-right-width:6px;border-bottom-width:6px}}
.block{{position:absolute;left:84px;right:84px;top:900px;height:560px;display:flex;flex-direction:column;justify-content:flex-end;gap:18px}}
.row{{display:flex;align-items:flex-end;justify-content:space-between;direction:ltr}}
.tag{{direction:ltr;display:flex;align-items:center;gap:16px;font-family:ZM;font-weight:600;font-size:34px;letter-spacing:3px;padding-bottom:8px}}
.tag .kd{{background:{VI};color:{PT};padding:6px 18px;border-radius:8px}} .tag .tk{{color:{PT}}}
.num{{direction:ltr;font-family:ZC;font-weight:700;font-size:112px;line-height:1}}
.title{{font-weight:950;font-size:138px;line-height:1.24;text-align:right}}
.title div{{white-space:nowrap}}
.title .k{{background:{VI};border-radius:24px;padding:0 20px}}
.zline{{position:absolute;left:84px;right:84px;top:1488px;height:5px;background:{VI};box-shadow:0 0 18px rgba(138,63,252,.9)}}
.foot{{position:absolute;left:84px;right:84px;top:1520px;display:flex;align-items:center;justify-content:space-between;direction:ltr}}
.lock{{display:flex;align-items:center;gap:16px;font-family:ZC;font-weight:700;font-size:44px}}
.lock img{{width:64px;height:64px;border-radius:50%;border:3px solid {VI}}} .lock .x{{color:{VIL}}}
.brief{{font-family:ZM;font-weight:500;font-size:28px;color:{MU};letter-spacing:3px}}
</style></head><body>
<div class="plate"></div><div class="fade"></div><div class="ground" style="top:1300px"></div><div class="glow"></div>
<div class="frame"></div><div class="tick t1"></div><div class="tick t2"></div><div class="tick t3"></div><div class="tick t4"></div>
<div class="block"><div class="row">{num_html or '<div></div>'}<div class="tag"><span class="kd">{kind}</span><span class="tk">{html.escape(str(s.get('tag') or ''))}</span></div></div>
<div class="title" id="ti">{"".join(f"<div>{key(x)}</div>" for x in lines)}</div></div>
<div class="zline"></div>
<div class="foot"><div class="lock"><img src="file://{MARK}"><span>Zarib<span class="x">100x</span></span></div><div class="brief">{brief}</div></div>
<script>
// one size for every line: the largest (≤ 138 px, ≥ 96 px) at which every line fits the 912 px column
const ti=document.getElementById('ti');let px=138;
const fit=()=>Array.from(ti.children).every(d=>d.scrollWidth<=912);
document.fonts.ready.then(()=>{{while(px>96&&!fit()){{px-=2;ti.style.fontSize=px+'px';}}document.body.dataset.fit=fit()?'ok':'overflow';}});
</script></body></html>"""


def render(html_text: str, out: Path) -> None:
    from playwright.sync_api import sync_playwright
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "c.html"
        f.write_text(html_text, encoding="utf-8")
        png = Path(tmp) / "c.png"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--allow-file-access-from-files", "--no-sandbox"])
            try:
                pg = b.new_page(viewport={"width": 1080, "height": 1920})
                pg.goto(f.as_uri())
                pg.evaluate("document.fonts.ready")
                pg.wait_for_function("!!document.body.dataset.fit", timeout=10000)
                if pg.evaluate("document.body.dataset.fit") != "ok":
                    raise SystemExit("the title does not fit in two lines at 96 px: shorten it")
                pg.wait_for_timeout(200)
                pg.screenshot(path=str(png))
            finally:
                b.close()
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.open(png).convert("RGB").save(out, "JPEG", quality=93, optimize=True)


def main(spec_path: str) -> None:
    s = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(s.get("out") or "out/cover.jpg")
    render(page(s), out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
