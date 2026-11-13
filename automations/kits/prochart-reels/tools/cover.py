# -*- coding: utf-8 -*-
"""ProChart reel cover (1080x1920) from HTML/SVG with the owner's IRANYekanX font, plus grid/feed crop previews.
usage: cover.py <out_png> <series> <title1> <title2> <subtitle>
"""
import os, sys, random, html
from playwright.sync_api import sync_playwright

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()  # the day's own folder
KIT = "/home/studio/kits/prochart-reels"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
out_png, series, t1, t2, sub = sys.argv[1:6]
out_png = os.path.abspath(out_png)
e = html.escape

def candles_svg(w=900, h=520, n=26, cut=0.62, seed=7):
    """Candles left of the replay line are drawn; the future to its right is a ghost behind a veil."""
    rnd = random.Random(seed)
    price, pts = 100.0, []
    for i in range(n):
        o = price
        c = o + rnd.uniform(-3.2, 3.6) + (0.9 if i > n * 0.35 else -0.4)
        hi = max(o, c) + rnd.uniform(0.4, 2.2); lo = min(o, c) - rnd.uniform(0.4, 2.2)
        pts.append((o, hi, lo, c)); price = c
    lo_all = min(p[2] for p in pts); hi_all = max(p[1] for p in pts)
    y = lambda v: 30 + (hi_all - v) / (hi_all - lo_all) * (h - 60)
    step = w / n; bw = step * 0.56; xcut = w * cut
    parts = []
    for i, (o, hi, lo, c) in enumerate(pts):
        x = i * step + step / 2
        up = c >= o
        col = "#089981" if up else "#F23645"
        future = x > xcut
        op = "0.16" if future else "1"
        top, bot = y(max(o, c)), y(min(o, c))
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(hi):.1f}" y2="{y(lo):.1f}" stroke="{col}" stroke-width="3" opacity="{op}"/>')
        parts.append(f'<rect x="{x-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(3, bot-top):.1f}" rx="3" fill="{col}" opacity="{op}"/>')
    veil = (f'<rect x="{xcut:.1f}" y="0" width="{w-xcut:.1f}" height="{h}" fill="url(#veil)"/>'
            f'<line x1="{xcut:.1f}" x2="{xcut:.1f}" y1="6" y2="{h-6}" stroke="#D4A64A" stroke-width="4" stroke-dasharray="14 10"/>'
            f'<circle cx="{xcut:.1f}" cy="40" r="34" fill="#0F0F0F" stroke="#D4A64A" stroke-width="4"/>'
            f'<path d="M{xcut+12:.1f},26 L{xcut-4:.1f},40 L{xcut+12:.1f},54 Z M{xcut-2:.1f},26 L{xcut-18:.1f},40 L{xcut-2:.1f},54 Z" fill="#D4A64A"/>')
    q = (f'<text x="{(xcut + w) / 2:.1f}" y="{h/2+40:.1f}" text-anchor="middle" font-size="150" '
         f'font-family="YX" font-weight="700" fill="#D4A64A" opacity="0.85">؟</text>')
    grid = "".join(f'<line x1="0" x2="{w}" y1="{gy}" y2="{gy}" stroke="#262626" stroke-width="2"/>' for gy in range(40, h, 80))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<defs><linearGradient id="veil" x1="0" x2="1"><stop offset="0" stop-color="#0F0F0F" stop-opacity="0.55"/>'
            f'<stop offset="1" stop-color="#0F0F0F" stop-opacity="0.92"/></linearGradient></defs>'
            f'{grid}{"".join(parts)}{veil}{q}</svg>')

fb = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Bold.ttf")
fr = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Regular.ttf")
mark = os.path.join(KIT, "coverkit", "logo", "prochart-mark-white.png")
doc = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>
@font-face {{ font-family: YX; src: url('file://{fb}'); font-weight: 700; }}
@font-face {{ font-family: YX; src: url('file://{fr}'); font-weight: 400; }}
html, body {{ margin:0; width:1080px; height:1920px; overflow:hidden; background:#0F0F0F; }}
body {{ font-family: YX; color:#fff; position:relative; }}
.bg {{ position:absolute; inset:0; background:
   radial-gradient(ellipse 70% 38% at 50% 52%, rgba(212,166,74,0.20), rgba(15,15,15,0) 70%),
   repeating-linear-gradient(90deg, rgba(255,255,255,0.035) 0 2px, transparent 2px 120px),
   repeating-linear-gradient(0deg, rgba(255,255,255,0.035) 0 2px, transparent 2px 120px); }}
.pill {{ position:absolute; top:350px; left:50%; transform:translateX(-50%); border:3px solid #D4A64A; color:#E2B85E;
   border-radius:999px; padding:6px 34px 12px; font-size:40px; font-weight:700; white-space:nowrap; }}
.t1 {{ position:absolute; top:440px; width:100%; text-align:center; font-size:172px; font-weight:700; line-height:1.15; }}
.t2 {{ position:absolute; top:650px; width:100%; text-align:center; font-size:104px; font-weight:700; color:#E2B85E; line-height:1.2; }}
.chart {{ position:absolute; top:850px; left:90px; }}
.sub {{ position:absolute; top:1400px; width:100%; text-align:center; font-size:52px; font-weight:400; color:#DBDBDB; }}
.brand {{ position:absolute; top:1505px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:18px;
   font-size:44px; font-weight:700; color:#fff; white-space:nowrap; }}
.brand img {{ height:66px; }}
</style></head><body><div class="bg"></div>
<div class="pill">{e(series)}</div>
<div class="t1">{e(t1)}</div>
<div class="t2">{e(t2)}</div>
<div class="chart">{candles_svg()}</div>
<div class="sub">{e(sub)}</div>
<div class="brand"><img src="file://{mark}"><span>پرو چارت</span></div>
</body></html>"""
html_path = out_png.replace(".png", ".html")
open(html_path, "w", encoding="utf-8").write(doc)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    pg.goto("file://" + html_path); pg.wait_for_timeout(600)
    pg.screenshot(path=out_png, full_page=False)
    b.close()
print("cover", out_png)
