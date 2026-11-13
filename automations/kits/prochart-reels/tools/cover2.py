# -*- coding: utf-8 -*-
"""ProChart reel cover v2: ONLY two colours, pure black #000000 and mustard #D4A64A (owner's rule).
usage: cover2.py <out_png> <layout A|B> <series> <title1> <title2> <subtitle> --element ELEMENT.svg
The middle element is the DAY'S OWN, about its topic (owner 2026-11-13: «المان وسطش هر روز تغییر کنه
نسبت به موضوع»): an SVG drawn for the topic, in a 900x480 box, with the two colours only (opacity is
allowed). It is required; `--element candles` draws the replay chart of reel 1 and is for a replay
topic only.
"""
import os, sys, random, html
from playwright.sync_api import sync_playwright

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()  # the day's own folder
KIT = "/home/studio/kits/prochart-reels"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
K, M = "#000000", "#D4A64A"   # the only two colours
import re
args = sys.argv[1:]
element = None
if "--element" in args:
    i = args.index("--element"); element = args[i + 1]; del args[i:i + 2]
out_png, layout, series, t1, t2, sub = args[0:6]
if not element:
    sys.exit("cover2: --element ELEMENT.svg is required (the day's own element, about its topic)")
ALLOWED = {"#000", "#000000", "#d4a64a", "none", "transparent", "currentcolor"}


def day_element(path, w, h):
    """The day's SVG, checked: two colours only; drawn in the w x h box."""
    svg = open(path, encoding="utf-8").read()
    bad = set()
    for m in re.finditer(r'(?:fill|stroke|stop-color|color|flood-color)\s*[:=]\s*["\']?\s*([^"\';\s>]+)', svg, re.I):
        v = m.group(1).lower()
        if v.startswith("url("):
            continue
        if v not in ALLOWED:
            bad.add(v)
    for v in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", svg):
        if v.lower() not in ALLOWED:
            bad.add(v.lower())
    if bad:
        sys.exit(f"cover2: the element uses colours other than #000000 and #D4A64A: {sorted(bad)}")
    head = re.search(r"<svg\b[^>]*>", svg)
    if head is None:
        sys.exit("cover2: the element is not an SVG")
    tag = head.group(0)
    vb = re.search(r'viewBox\s*=\s*["\']([^"\']+)', tag)
    if vb is None:
        ow = re.search(r'width\s*=\s*["\']?([0-9.]+)', tag); oh = re.search(r'height\s*=\s*["\']?([0-9.]+)', tag)
        view = f"0 0 {ow.group(1) if ow else w} {oh.group(1) if oh else h}"
    else:
        view = vb.group(1)
    inner = svg[head.end():svg.rfind("</svg>")]
    return (f'<svg width="{w}" height="{h}" viewBox="{view}" preserveAspectRatio="xMidYMid meet" '
            f'xmlns="http://www.w3.org/2000/svg" font-family="YX">{inner}</svg>')
out_png = os.path.abspath(out_png)
e = html.escape

def candles(w, h, n=24, cut=0.62, seed=7):
    """Up candles: solid mustard. Down candles: hollow (mustard outline, black body). Future: hidden behind hatching."""
    rnd = random.Random(seed); price, pts = 100.0, []
    for i in range(n):
        o = price; c = o + rnd.uniform(-3.2, 3.6) + (0.9 if i > n * 0.35 else -0.4)
        pts.append((o, max(o, c) + rnd.uniform(.4, 2.2), min(o, c) - rnd.uniform(.4, 2.2), c)); price = c
    lo = min(p[2] for p in pts); hi = max(p[1] for p in pts)
    y = lambda v: 24 + (hi - v) / (hi - lo) * (h - 48)
    st = w / n; bw = st * .56; xc = w * cut; s = []
    for i, (o, hh, ll, c) in enumerate(pts):
        x = i * st + st / 2
        if x > xc: continue
        top, bot = y(max(o, c)), y(min(o, c)); up = c >= o
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(hh):.1f}" y2="{y(ll):.1f}" stroke="{M}" stroke-width="3"/>')
        s.append(f'<rect x="{x-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(3,bot-top):.1f}" rx="2" '
                 f'fill="{M if up else K}" stroke="{M}" stroke-width="3"/>')
    hatch = "".join(f'<line x1="{xc+k:.0f}" y1="{h}" x2="{xc+k+h:.0f}" y2="0" stroke="{M}" stroke-width="2" opacity=".22"/>'
                    for k in range(-h, int(w - xc), 26))
    s.append(f'<clipPath id="cp"><rect x="{xc:.0f}" y="0" width="{w-xc:.0f}" height="{h}"/></clipPath><g clip-path="url(#cp)">{hatch}</g>')
    s.append(f'<line x1="{xc:.0f}" x2="{xc:.0f}" y1="6" y2="{h-6}" stroke="{M}" stroke-width="5" stroke-dasharray="16 10"/>')
    s.append(f'<circle cx="{xc:.0f}" cy="42" r="36" fill="{K}" stroke="{M}" stroke-width="5"/>'
             f'<path d="M{xc+13:.0f},27 L{xc-4:.0f},42 L{xc+13:.0f},57 Z M{xc-1:.0f},27 L{xc-18:.0f},42 L{xc-1:.0f},57 Z" fill="{M}"/>')
    s.append(f'<text x="{(xc+w)/2:.0f}" y="{h/2+55:.0f}" text-anchor="middle" font-family="YX" font-weight="700" font-size="170" fill="{M}">؟</text>')
    return f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">{"".join(s)}</svg>'

fb = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Bold.ttf"); fr = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Regular.ttf")
mark_m = os.path.join(KIT, "coverkit", "logo", "prochart-mark-gold.png")
base = f"""@font-face {{ font-family:YX; src:url('file://{fb}'); font-weight:700; }}
@font-face {{ font-family:YX; src:url('file://{fr}'); font-weight:400; }}
html,body {{ margin:0; width:1080px; height:1920px; overflow:hidden; background:{K}; font-family:YX; }}
.a {{ position:absolute; }} .c {{ left:0; width:100%; text-align:center; }}
.brand {{ position:absolute; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:18px;
  font-size:46px; font-weight:700; color:{M}; white-space:nowrap; }} .brand img {{ height:70px; }}"""
if layout == "A":   # mustard header block with black type, mustard chart on black
    css = base + f"""
.block {{ position:absolute; top:300px; left:70px; width:940px; height:520px; background:{M};
  clip-path:polygon(0 0,100% 0,100% 86%,0 100%); }}
.ser {{ position:absolute; top:340px; right:110px; font-size:38px; font-weight:700; color:{K}; border:4px solid {K}; border-radius:999px; padding:2px 26px 8px; }}
.t1 {{ top:415px; font-size:190px; font-weight:700; color:{K}; line-height:1.1; }}
.t2 {{ top:630px; font-size:96px; font-weight:700; color:{K}; }}
.chart {{ top:900px; left:90px; }}
.sub {{ top:1430px; font-size:52px; font-weight:400; color:{M}; }}"""
    body = f"""<div class="block"></div><div class="ser">{e(series)}</div>
<div class="a c t1">{e(t1)}</div><div class="a c t2">{e(t2)}</div>
<div class="a chart">{candles(900, 480) if element == "candles" else day_element(element, 900, 480)}</div>
<div class="a c sub">{e(sub)}</div><div class="brand" style="top:1530px"><img src="file://{mark_m}"><span>پرو چارت</span></div>"""
else:               # B: black canvas, mustard frame, huge outlined + solid type, chart inside the frame
    css = base + f"""
.frame {{ position:absolute; top:300px; left:70px; width:940px; height:1320px; border:6px solid {M}; border-radius:36px; }}
.ser {{ position:absolute; top:268px; left:50%; transform:translateX(-50%); background:{K}; color:{M}; font-size:40px; font-weight:700; padding:0 30px; }}
.t1 {{ top:360px; font-size:200px; font-weight:700; color:{K}; -webkit-text-stroke:5px {M}; line-height:1.1; }}
.t2 {{ top:590px; font-size:100px; font-weight:700; color:{M}; }}
.chart {{ top:800px; left:110px; }}
.bar {{ position:absolute; top:1330px; left:70px; width:940px; height:150px; background:{M}; }}
.sub {{ top:1352px; font-size:52px; font-weight:700; color:{K}; }}"""
    body = f"""<div class="frame"></div><div class="ser">{e(series)}</div>
<div class="a c t1">{e(t1)}</div><div class="a c t2">{e(t2)}</div>
<div class="a chart">{candles(860, 480, seed=7) if element == "candles" else day_element(element, 860, 480)}</div>
<div class="bar"></div><div class="a c sub">{e(sub)}</div>
<div class="brand" style="top:1515px"><img src="file://{mark_m}"><span>پرو چارت</span></div>"""
doc = f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'
hp = out_png.replace(".png", ".html"); open(hp, "w", encoding="utf-8").write(doc)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920}); pg.goto("file://" + hp); pg.wait_for_timeout(500)
    pg.screenshot(path=out_png); b.close()
os.remove(hp); print("cover", out_png)
