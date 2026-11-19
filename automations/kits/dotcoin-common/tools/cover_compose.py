# -*- coding: utf-8 -*-
"""The DotCoin.me cover, composed exactly (the owner's cover system, COVER_SYSTEM.md, and his two
sample covers of 2026-11-16 in cover/samples/): the flat brand ground, the GIANT condensed English
words, the cut-out owner, the Persian title set with the real font, an optional pill with the call
to action and a hand-drawn arrow. Rendered by headless Chromium at 2160x3840 (the master).

The layout is FREE (the owner, 2026-11-16: «نه صرفا کلمه پشت سر باشه، میتونه متفاوت هم باشه جای
نوشته»): the words may stand behind him, in front of him, as an outline over him, at the top, the
bottom or in a side column; the title beside him or under him. Change the layout cover to cover.

usage: cover_compose.py <spec.json> <outdir>
  -> outdir/cover_4k.png (2160x3840), outdir/cover.jpg (1080x1920, q92), outdir/cover_crops.jpg
     (the grid's 3:4 and 1:1 crops, to check)

spec.json (all positions in 1080x1920 units; the master is x2). "subject" or "background".
{
  "palette": "A",                       A: mustard ground + black words — ALWAYS (the owner,
                                        2026-11-19: one cover family, COVER_SYSTEM.md «ONE FAMILY»)
                                        B: black ground + mustard words (retired: never on a cover)
  "background": "assets/gpt_cover.png", optional: a finished picture under everything, filling the
                                        frame (ChatGPT's cover made without its Persian text: the
                                        title is then set here); "subject" may then be omitted
  "subject": "assets/me_cut.png",       the cut-out (tools/cutout.py --trim), RGBA
  "subject_side": "right",              right | left | center
  "subject_height": 0.80,               its height / the frame's (0.45-0.98)
  "subject_shift": 0,                   px sideways (+ toward the centre)
  "subject_bottom": 0,                  px above the frame's bottom edge (0: it stands on it)

  "english": ["FOREX", "CHANNEL"],      0-3 lines, UPPERCASE; each line fitted to the box's width
  "english_font": "Anton",              Anton | Bebas
  "english_box": [26, 110, 1028],       x, y, width of the words' block
  "english_layer": "behind",            behind (he overlaps them) | front (over him) |
                                        outline (solid behind + an outline of them over him)
  "english_color": "",                  mustard | black | white (default: the palette's)
  "english_line_height": 0.86,

  "title": ["برای دریافت", "کانال فارکس"], 0-3 lines (IRANYekanX Pro)
  "title_style": "free",                free: set on the ground (the samples) · bar: in a solid bar
  "title_colors": ["white", "white"],   per line: mustard | white | black
  "chip": "فارکس",                      the key word in a rounded chip (mustard + black on B)
  "highlight": "",                      a word in the accent colour, no chip
  "title_weight": "ExtraBlack",         ExtraBlack | Black | Heavy | ExtraBold
  "title_size": 92,                     px (56-120)
  "title_box": [40, 940, 560],          x, y, width of the title's block
  "title_align": "center",              center | right | left (inside its box)
  "cta": {"text": "کلمه «فارکس» را اینجا بفرست", "mark": "«فارکس»", "size": 34, "gap": 34},
                                        optional pill under the title (or "box": [x, y, w] of its own)
  "arrow": {"from": [300, 1430], "to": [460, 1700], "bend": 0.35},
                                        optional hand-drawn arrow (+bend curves one way, - the other)
  "logo": "assets/brand_logo.png",      optional: the topic's REAL logo (never AI-made); "logo_box"
                                        [x, y, w, h] (default top-left)
  "element": {"path": "assets/x.png", "box": [60, 900, 300, 300], "front": false}   optional, ONE
}
"""
import base64
import html
import json
import math
import mimetypes
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FONTS = "/home/studio/kits/fonts-pro"
MUSTARD, BLACK, WHITE = "#F3C242", "#000000", "#FFFFFF"
NAMED = {"mustard": MUSTARD, "white": WHITE, "black": BLACK}
W, H = 1080, 1920


def data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def font_face(family: str, file: str) -> str:
    return f"@font-face{{font-family:'{family}';src:url('file://{FONTS}/{file}');}}"


def colours(pal: str) -> dict:
    if pal == "A":  # mustard ground
        return {"ground": MUSTARD, "words": BLACK, "bar": BLACK, "bar_ink": WHITE, "accent": WHITE,
                "chip_bg": BLACK, "chip_ink": MUSTARD, "line": BLACK, "pill_ink": BLACK,
                "mark": BLACK, "title": ["black", "black", "black"]}
    return {"ground": BLACK, "words": MUSTARD, "bar": MUSTARD, "bar_ink": BLACK, "accent": MUSTARD,
            "chip_bg": MUSTARD, "chip_ink": BLACK, "line": MUSTARD, "pill_ink": WHITE,
            "mark": MUSTARD, "title": ["mustard", "white", "white"]}


def arrow_svg(ar: dict, ink: str) -> str:
    (x1, y1), (x2, y2) = ar["from"], ar["to"]
    bend = float(ar.get("bend", 0.3))
    dx, dy = x2 - x1, y2 - y1
    cx, cy = (x1 + x2) / 2 - dy * bend, (y1 + y2) / 2 + dx * bend
    ang = math.atan2(y2 - cy, x2 - cx)
    hx = [x2 - 46 * math.cos(ang - 0.5), x2 - 46 * math.cos(ang + 0.5)]
    hy = [y2 - 46 * math.sin(ang - 0.5), y2 - 46 * math.sin(ang + 0.5)]
    return (f'<svg style="position:absolute;left:0;top:0;z-index:8" width="{W}" height="{H}">'
            f'<path d="M{x1},{y1} Q{cx:.0f},{cy:.0f} {x2},{y2}" fill="none" stroke="{ink}" '
            f'stroke-width="9" stroke-linecap="round"/>'
            f'<path d="M{hx[0]:.0f},{hy[0]:.0f} L{x2},{y2} L{hx[1]:.0f},{hy[1]:.0f}" fill="none" '
            f'stroke="{ink}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def page(spec: dict, root: str) -> str:
    c = colours(str(spec.get("palette", "A")).upper())
    # --- the subject
    side = spec.get("subject_side", "right")
    sh = max(0.45, min(0.98, float(spec.get("subject_height", 0.80)))) * H
    shift = int(spec.get("subject_shift", 0))
    place = {"right": f"right:{-30 + shift}px", "left": f"left:{-30 + shift}px",
             "center": "left:50%;transform:translateX(-50%)"}[side]
    subject = ""
    if spec.get("subject"):
        subj = data_url(os.path.join(root, spec["subject"]))
        subject = (f'<div style="position:absolute;bottom:{int(spec.get("subject_bottom", 0))}px;{place};'
                   f'height:{sh:.0f}px;z-index:4"><img src="{subj}" style="height:100%;display:block"></div>')
    if spec.get("background"):
        bg = data_url(os.path.join(root, spec["background"]))
        subject = (f'<img src="{bg}" style="position:absolute;inset:0;width:{W}px;height:{H}px;'
                   f'object-fit:cover;z-index:1">') + subject
    # --- the giant English words
    eng_font = {"anton": "Anton", "bebas": "Bebas"}.get(str(spec.get("english_font", "Anton")).lower(), "Anton")
    ex, ey, ew = spec.get("english_box", [26, 110, W - 52])
    words_ink = NAMED.get(str(spec.get("english_color") or ""), c["words"])
    layer = spec.get("english_layer", "behind")
    lh = float(spec.get("english_line_height", 0.86))
    lines = [html.escape(str(x).upper()) for x in spec.get("english", [])][:3]

    def words(z: int, outline: bool, bid: str) -> str:
        if not lines:
            return ""
        css = (f"color:transparent;-webkit-text-stroke:3px {words_ink}" if outline else f"color:{words_ink}")
        rows = "".join(f'<div class="en" style="{css}">{t}</div>' for t in lines)
        return (f'<div class="enbox" id="{bid}" style="left:{ex}px;top:{ey}px;width:{ew}px;'
                f'z-index:{z}">{rows}</div>')

    eng_html = words(6 if layer == "front" else 2, False, "e1")
    if layer == "outline":
        eng_html += words(5, True, "e2")
    # --- the Persian title
    hl, chip = str(spec.get("highlight") or ""), str(spec.get("chip") or "")

    def mark(t: str) -> str:
        t = html.escape(t)
        if chip and html.escape(chip) in t:
            t = t.replace(html.escape(chip), f'<span class="chip">{html.escape(chip)}</span>', 1)
        if hl and html.escape(hl) in t:
            t = t.replace(html.escape(hl), f'<span class="hl">{html.escape(hl)}</span>', 1)
        return t

    tl = [str(x) for x in spec.get("title", [])][:3]
    size = int(spec.get("title_size", 92))
    tx, ty, tw = spec.get("title_box", [50, 1330, W - 100])
    talign = spec.get("title_align", "center")
    cols = list(spec.get("title_colors") or c["title"])
    cta = spec.get("cta") or None
    pill = ""
    if cta:
        ct, mk = html.escape(str(cta.get("text", ""))), html.escape(str(cta.get("mark", "")))
        if mk and mk in ct:
            ct = ct.replace(mk, f'<b style="color:{c["mark"]}">{mk}</b>', 1)
        pill = (f'<span class="pill" style="font-size:{int(cta.get("size", 34))}px">{ct}</span>')
    title_html = ""
    if tl and spec.get("title_style", "free") == "bar":
        rows = "".join(f"<div>{mark(t)}</div>" for t in tl)
        title_html = (f'<div class="bar" style="left:{tx}px;top:{ty}px;width:{tw}px;font-size:{size}px;'
                      f'text-align:{talign}">{rows}</div>')
    elif tl:
        rows = "".join(f'<div style="color:{NAMED.get(cols[min(i, len(cols) - 1)], WHITE)}">{mark(t)}</div>'
                       for i, t in enumerate(tl))
        under = ""
        if pill and not (cta or {}).get("box"):
            under = (f'<div style="text-align:{talign};margin-top:{int(cta.get("gap", 34))}px;'
                     f'font-size:16px">{pill}</div>')
        title_html = (f'<div class="free" style="left:{tx}px;top:{ty}px;width:{tw}px;'
                      f'text-align:{talign};font-size:{size}px">{rows}{under}</div>')
    if pill and (cta or {}).get("box"):
        bx, by, bw = cta["box"]
        title_html += (f'<div class="free" style="left:{bx}px;top:{by}px;width:{bw}px;'
                       f'text-align:{cta.get("align", "center")}">{pill}</div>')
    # --- the arrow, the logo, the element
    arrow_html = arrow_svg(spec["arrow"], c["line"]) if spec.get("arrow") else ""
    logo = ""
    if spec.get("logo"):
        lx, ly, lw, lh2 = spec.get("logo_box", [60, 300, 250, 95])
        logo = (f'<img src="{data_url(os.path.join(root, spec["logo"]))}" style="position:absolute;'
                f'left:{lx}px;top:{ly}px;max-width:{lw}px;max-height:{lh2}px;object-fit:contain;z-index:8">')
    el_html = ""
    el = spec.get("element") or None
    if el:
        x, y, w, h = el["box"]
        el_html = (f'<img src="{data_url(os.path.join(root, el["path"]))}" style="position:absolute;'
                   f'left:{x}px;top:{y}px;width:{w}px;height:{h}px;object-fit:contain;'
                   f'z-index:{6 if el.get("front") else 3}">')
    weight = spec.get("title_weight", "ExtraBlack")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_face('Anton', 'Anton-Regular.ttf')}{font_face('Bebas', 'BebasNeue-Regular.ttf')}
{font_face('YXP', f'IRANYekanXFaNum-{weight}.ttf')}{font_face('YXB', 'IRANYekanXFaNum-Black.ttf')}
html,body{{margin:0;padding:0;width:{W}px;height:{H}px;overflow:hidden;background:{c['ground']}}}
.wrap{{position:absolute;inset:0;background:{c['ground']}}}
.enbox{{position:absolute}}
.en{{font-family:'{eng_font}';line-height:{lh};white-space:nowrap;letter-spacing:-.005em;text-align:center}}
.bar{{position:absolute;background:{c['bar']};z-index:7;padding:26px 34px 30px;direction:rtl;
      font-family:'YXP';color:{c['bar_ink']};line-height:1.28;box-sizing:border-box}}
.free{{position:absolute;z-index:7;direction:rtl;font-family:'YXP';line-height:1.32}}
.free>div{{white-space:nowrap}}
.chip{{background:{c['chip_bg']};color:{c['chip_ink']};border-radius:.2em;padding:0 .2em .06em;
       display:inline-block;line-height:1.18;margin:0 .04em}}
.hl{{color:{c['accent']}}}
.pill{{display:inline-block;direction:rtl;border:4px solid {c['line']};border-radius:999px;
       padding:.38em 1.1em .5em;color:{c['pill_ink']};font-family:'YXB';line-height:1.2;
       white-space:nowrap}}
</style></head><body><div class="wrap">
{eng_html}{el_html}{subject}{logo}{title_html}{arrow_html}
</div><script>
document.fonts.ready.then(() => {{
  for (const d of document.querySelectorAll('.en')) {{
    const want = d.parentElement.clientWidth;
    d.style.fontSize = '400px';
    d.style.fontSize = Math.min(760, 400 * want / d.scrollWidth) + 'px';
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
