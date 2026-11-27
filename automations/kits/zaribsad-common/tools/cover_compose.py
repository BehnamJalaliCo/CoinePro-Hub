"""Zarib100x — the cover's type layer, set exactly (cover/COVER_SYSTEM.md). Two uses:

1. FALLBACK (the only use in a reel): ChatGPT drew the cover twice with a wrong Persian letter → it draws it
   once more with the title area EMPTY, and this tool sets the Persian title, its mint chip and the comment
   pill on that picture, in IRANYekanX Pro ExtraBlack:
     {"background": "in/CR-0123.png", "title": [...], "word": "الماس", "out": "out/cover.jpg"}
2. SAMPLES (make_board.py; never a reel's cover): the whole family drawn in code around a cut-out of the owner
   — the wine-black ground, the mint arch, the top line — to show ChatGPT the target:
     {"cutout": "build/him.png", "tag": "COIN · SOL/USDT", "title": [...], "word": "...", "out": "..."}

spec fields: title (1–2 lines, 2–6 words in all; [..] = the key word in the mint chip; no full stop) ·
word (the comment word for the pill «کلمه‌ی «…» رو کامنت کن», "" = no pill) · number + number_dir (optional,
samples only: a real number, ▲/▼ with its meaning colour) · focus (background crop point).
usage: PY -I COMMON/tools/cover_compose.py spec.json"""

import html
import json
import re
import os
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
COMMON = Path(__file__).resolve().parent.parent
OWN = COMMON / "fonts"
GR, OX, OXL, MINT, TX, MU, UP, DN = "#160A0E", "#461A23", "#6B2A37", "#83CAAD", "#F4EFE6", "#A8979B", "#35E06E", "#FF4D57"
FA_DIG = str.maketrans("0123456789.,%", "۰۱۲۳۴۵۶۷۸۹/٬٪")  # ⟨2026-11-27⟩ decimals «/» (fa-type)


def clean(t: str) -> str:  # raw text, never a full stop at the end (escaped later by iso)
    return re.sub(r"[.،؛:]+\s*$", "", str(t).strip())


def iso(t: str) -> str:
    """Digits and Latin runs inside Persian (the font has Latin digits): a run with a Latin letter or $
    stays Latin, isolated LTR; a run of digits alone becomes Persian digits. Returns escaped HTML."""
    out, last = [], 0
    for m in re.finditer(r"[A-Za-z0-9$][A-Za-z0-9$%.,/:+\-×#@_ ]*[A-Za-z0-9%$]|[A-Za-z0-9$]", t):
        out.append(html.escape(t[last:m.start()]))
        r = m.group(0)
        out.append(f'<bdi dir="ltr">{html.escape(r)}</bdi>' if re.search(r"[A-Za-z$]", r) else r.translate(FA_DIG))
        last = m.end()
    out.append(html.escape(t[last:]))
    return "".join(out)


def key(t: str) -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="k">{m.group(1)}</span>', iso(clean(t)))


def faces() -> str:
    rows = [("ZF", PRO / "IRANYekanX-ExtraBlack.ttf", 950), ("ZF", PRO / "IRANYekanX-ExtraBold.ttf", 800),
            ("ZM", OWN / "IBMPlexMono-Medium.ttf", 500), ("ZC", OWN / "IBMPlexSansCondensed-Bold.ttf", 700)]
    return "".join(f'@font-face{{font-family:{f};font-weight:{w};src:url("file://{p}");}}' for f, p, w in rows)


def page(s: dict) -> str:
    lines = [ln for ln in (s.get("title") or []) if str(ln).strip()][:2]
    if not lines:
        raise SystemExit("a title is required")
    word = str(s.get("word") or "").strip()
    pill = (f'<div class="pill">کلمه‌ی «<span class="w">{iso(word)}</span>» رو کامنت کن</div>' if word else "")
    if s.get("background"):
        bg = Path(s["background"]).resolve()
        world = (f'<div class="bgp" style="background-image:url(\'file://{bg}\');background-position:'
                 f'{html.escape(str(s.get("focus") or "50% 40%"))}"></div><div class="fadeb"></div>')
    else:
        him = Path(s["cutout"]).resolve()
        num = str(s.get("number") or "").strip()
        nd = str(s.get("number_dir") or "")
        numh = ""
        if num:
            col, gl = {"up": (UP, "▲ "), "down": (DN, "▼ ")}.get(nd, (TX, ""))
            numh = f'<div class="num" style="color:{col}">{gl}{html.escape(num.replace("-", "−"))}</div>'
        world = f"""<div class="glow"></div><div class="arch"></div><img class="him" src="file://{him}"><div class="fadeb"></div>
<div class="top"><span class="wm">Zarib<span class="x">100x</span></span><span class="tag">{html.escape(str(s.get('tag') or ''))}</span></div>{numh}"""
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;background:{GR};overflow:hidden;color:{TX};font-family:ZF}}
.bgp{{position:absolute;inset:0;background-size:cover;background-repeat:no-repeat}}
.glow{{position:absolute;inset:0;background:radial-gradient(1000px 900px at 50% 38%,{OXL} 0%,{OX} 38%,{GR} 78%)}}
.arch{{position:absolute;left:170px;width:740px;top:330px;height:960px;background:{MINT};border-radius:370px 370px 0 0}}
.him{{position:absolute;left:50%;transform:translateX(-50%);bottom:560px;height:940px;max-width:1040px;object-fit:contain;object-position:bottom}}
.fadeb{{position:absolute;left:0;right:0;top:1150px;height:770px;background:linear-gradient(180deg,rgba(22,10,14,0) 0%,{GR} 22%)}}
.top{{position:absolute;top:252px;left:84px;right:84px;display:flex;justify-content:space-between;align-items:center;direction:ltr}}
.wm{{font-family:ZC;font-weight:700;font-size:46px}} .x{{color:{MINT}}}
.tag{{font-family:ZM;font-weight:500;font-size:28px;letter-spacing:4px;color:{TX};opacity:.85}}
.num{{position:absolute;left:84px;top:1240px;direction:ltr;font-family:ZC;font-weight:700;font-size:76px}}
.block{{position:absolute;left:70px;right:70px;top:1300px;display:flex;flex-direction:column;align-items:center;gap:30px}}
.title{{font-weight:950;font-size:122px;line-height:1.26;text-align:center}}
.title div{{white-space:nowrap}}
.title .k{{background:{MINT};color:{GR};border-radius:26px;padding:0 22px}}
.pill{{border:4px solid {TX};border-radius:60px;padding:10px 40px 14px;font-weight:800;font-size:46px}}
.pill .w{{color:{MINT}}}
</style></head><body>{world}
<div class="block"><div class="title" id="ti">{"".join(f"<div>{key(x)}</div>" for x in lines)}</div>{pill}</div>
<script>
// one size for every line: the largest (≤ 122 px, ≥ 84 px) at which every line fits the 940 px column
const ti=document.getElementById('ti');let px=122;
const fit=()=>Array.from(ti.children).every(d=>d.scrollWidth<=940);
document.fonts.ready.then(()=>{{while(px>84&&!fit()){{px-=2;ti.style.fontSize=px+'px';}}document.body.dataset.fit=fit()?'ok':'overflow';}});
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
                    raise SystemExit("the title does not fit in two lines at 84 px: shorten it")
                pg.wait_for_timeout(200)
                if not F.guard(pg, out, "zaribsad-common/cover_compose", numbers="any", overlap=False):
                    raise SystemExit(2)
                pg.screenshot(path=str(png))
            finally:
                b.close()
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.open(png).convert("RGB").save(out, "JPEG", quality=93, optimize=True)


def main(spec_path: str) -> None:
    s = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    if not s.get("background") and not s.get("cutout"):
        raise SystemExit("background (the fallback) or cutout (samples) is required")
    out = Path(s.get("out") or "out/cover.jpg")
    render(page(s), out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
