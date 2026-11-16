# -*- coding: utf-8 -*-
"""The DotCoin.me cover, composed exactly (the owner's cover system, COVER_SYSTEM.md): the flat
brand ground, the giant English words BEHIND the cut-out owner, the Persian title in its bar, the
topic's real logo when there is one. Rendered by headless Chromium at 2160x3840 (the master).

usage: cover_compose.py <spec.json> <outdir>
  -> outdir/cover_4k.png (2160x3840), outdir/cover.jpg (1080x1920, q92), outdir/cover_crops.jpg
     (the grid's 3:4 and 1:1 crops, to check)

spec.json (layout in 1080x1920 units; the master is x2):
{
  "palette": "A",                      A: mustard ground + black words · B: black ground + mustard words
  "subject": "assets/me_cut.png",      the cut-out (tools/cutout.py --trim), RGBA
  "subject_side": "right",             right | left | center
  "subject_height": 0.74,              its height / the frame's (bottom-anchored; 0.55-0.92)
  "subject_shift": 0,                  px to move it sideways (+ toward the centre)
  "english": ["NEW", "PAGE"],          1-2 lines, UPPERCASE, each fitted to the full width
  "english_font": "Anton",             Anton | Bebas
  "english_top": 420,                  where the words start (px)
  "outline_over": [2],                 lines drawn AGAIN as an outline in front of the subject
  "title": ["پیج جدید بزنم", "یا نه؟!"], 1-2 lines (IRANYekanX Pro)
  "highlight": "جدید",                 one key word or number in the accent colour
  "title_weight": "ExtraBlack",        ExtraBlack | Black | Heavy | ExtraBold
  "title_size": 92,                    px (72-105)
  "title_top": 1330,                   the bar's top (px)
  "logo": "assets/brand_logo.png",     optional: the topic's REAL logo (never AI-made), top-left zone
  "element": {"path": "assets/x.png", "box": [60, 900, 300, 300], "front": false}   optional, ONE
}
"""
import base64
import html
import json
import mimetypes
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FONTS = "/home/studio/kits/fonts-pro"
MUSTARD, BLACK, WHITE = "#F3C242", "#000000", "#FFFFFF"
W, H = 1080, 1920


def data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def font_face(family: str, file: str) -> str:
    return f"@font-face{{font-family:'{family}';src:url('file://{FONTS}/{file}');}}"


def page(spec: dict, root: str) -> str:
    pal = spec.get("palette", "A").upper()
    ground, words = (MUSTARD, BLACK) if pal == "A" else (BLACK, MUSTARD)
    bar, title_ink, accent = (BLACK, WHITE, MUSTARD) if pal == "A" else (MUSTARD, BLACK, WHITE)
    eng_font = {"anton": "Anton", "bebas": "Bebas"}.get(str(spec.get("english_font", "Anton")).lower(), "Anton")
    weight = spec.get("title_weight", "ExtraBlack")
    side = spec.get("subject_side", "right")
    sh = max(0.55, min(0.92, float(spec.get("subject_height", 0.74)))) * H
    shift = int(spec.get("subject_shift", 0))
    subj = os.path.join(root, spec["subject"])
    place = {"right": f"right:{-40 + shift}px", "left": f"left:{-40 + shift}px",
             "center": "left:50%;transform:translateX(-50%)"}[side]
    lines = [str(x).upper() for x in spec.get("english", [])][:2]
    over = set(int(i) for i in spec.get("outline_over", []))
    top = int(spec.get("english_top", 420))
    eng = "".join(f'<div class="en" data-i="{i}">{html.escape(t)}</div>' for i, t in enumerate(lines, 1))
    eng_over = "".join(
        f'<div class="en ov" data-i="{i}" style="visibility:{"visible" if i in over else "hidden"}">'
        f"{html.escape(t)}</div>" for i, t in enumerate(lines, 1))
    hl = str(spec.get("highlight") or "")

    def mark(t: str) -> str:
        t = html.escape(t)
        return t.replace(html.escape(hl), f'<span class="hl">{html.escape(hl)}</span>') if hl else t

    title = "".join(f"<div>{mark(t)}</div>" for t in spec.get("title", [])[:2])
    logo = ""
    if spec.get("logo"):
        logo = f'<img class="logo" src="{data_url(os.path.join(root, spec["logo"]))}">'
    el = spec.get("element") or None
    el_html = ""
    if el:
        x, y, w, h = el["box"]
        z = 6 if el.get("front") else 3
        el_html = (f'<img src="{data_url(os.path.join(root, el["path"]))}" style="position:absolute;'
                   f'left:{x}px;top:{y}px;width:{w}px;height:{h}px;object-fit:contain;z-index:{z}">')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_face('Anton', 'Anton-Regular.ttf')}{font_face('Bebas', 'BebasNeue-Regular.ttf')}
{font_face('YXP', f'IRANYekanXFaNum-{weight}.ttf')}
html,body{{margin:0;padding:0;width:{W}px;height:{H}px;overflow:hidden;background:{ground}}}
.wrap{{position:absolute;inset:0;background:{ground}}}
.enbox{{position:absolute;left:60px;right:60px;top:{top}px}}
.en{{font-family:'{eng_font}';color:{words};line-height:.84;white-space:nowrap;letter-spacing:-.01em;
     text-align:center;transform-origin:left top}}
.ov{{color:transparent;-webkit-text-stroke:3px {words}}}
.subj{{position:absolute;bottom:0;{place};height:{sh:.0f}px;z-index:4}}
.subj img{{height:100%;display:block}}
.bar{{position:absolute;left:50px;right:50px;top:{int(spec.get('title_top', 1330))}px;background:{bar};
      z-index:7;padding:26px 34px 30px;direction:rtl;text-align:center;font-family:'YXP';
      color:{title_ink};font-size:{int(spec.get('title_size', 92))}px;line-height:1.28}}
.hl{{color:{accent}}}
.logo{{position:absolute;left:60px;top:300px;max-width:250px;max-height:95px;object-fit:contain;z-index:8}}
</style></head><body><div class="wrap">
<div class="enbox" id="back" style="z-index:2">{eng}</div>
{el_html}
<div class="subj"><img src="{data_url(subj)}"></div>
<div class="enbox" id="front" style="z-index:5">{eng_over}</div>
{logo}
{'<div class="bar">' + title + '</div>' if title else ''}
</div><script>
document.fonts.ready.then(() => {{
  for (const box of [document.getElementById('back'), document.getElementById('front')]) {{
    let y = 0;
    for (const d of box.querySelectorAll('.en')) {{
      d.style.fontSize = '400px';
      const r = d.scrollWidth, want = {W - 120};
      const size = Math.min(620, 400 * want / r);
      d.style.fontSize = size + 'px';
    }}
  }}
  window.READY = true;
}});
</script></body></html>"""


def main() -> None:
    spec_path, outdir = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path, encoding="utf-8"))
    root = os.path.dirname(os.path.abspath(spec_path))
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(outdir, "_cover.html")
    open(tmp, "w", encoding="utf-8").write(page(spec, os.getcwd() if spec.get("from_cwd") else root))
    master = os.path.join(outdir, "cover_4k.png")
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True,
                              args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        pg.goto("file://" + os.path.abspath(tmp))
        pg.wait_for_function("window.READY === true", timeout=30000)
        pg.screenshot(path=master, full_page=False)
        b.close()
    os.remove(tmp)
    im = Image.open(master).convert("RGB")
    im.resize((W, H), Image.LANCZOS).save(os.path.join(outdir, "cover.jpg"), quality=92)
    small = im.resize((540, 960), Image.LANCZOS)
    g34 = small.crop((0, 120, 540, 840))
    g11 = small.crop((0, 210, 540, 750))
    sheet = Image.new("RGB", (540 * 3 + 40, 960), "white")
    sheet.paste(small, (0, 0)); sheet.paste(g34, (560, 0)); sheet.paste(g11, (1120, 0))
    sheet.save(os.path.join(outdir, "cover_crops.jpg"), quality=85)
    print("cover:", master, os.path.join(outdir, "cover.jpg"), os.path.join(outdir, "cover_crops.jpg"))


if __name__ == "__main__":
    main()
