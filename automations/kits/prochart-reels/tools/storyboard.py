# -*- coding: utf-8 -*-
"""Four storyboard key frames (540x960) for the first reel, in the cover's visual language."""
import os, random
from playwright.sync_api import sync_playwright

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()  # the day's own folder
KIT = "/home/studio/kits/prochart-reels"
OUT = os.path.join(ROOT, "direction", "frames"); os.makedirs(OUT, exist_ok=True)
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FB = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Bold.ttf")
FR = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Regular.ttf")
FL = os.path.join(KIT, "fontpack_raw", "IRANYekanX-Bold.ttf")
MARK = os.path.join(KIT, "coverkit2", "logo", "prochart-mark-mustard.png")

def candles(w, h, n=24, cut=0.62, seed=11, veil=True, sltp=False):
    rnd = random.Random(seed); price, pts = 100.0, []
    for i in range(n):
        o = price; c = o + rnd.uniform(-3, 3.4) + (0.8 if i > n * 0.4 else -0.5)
        pts.append((o, max(o, c) + rnd.uniform(.4, 2), min(o, c) - rnd.uniform(.4, 2), c)); price = c
    lo = min(p[2] for p in pts); hi = max(p[1] for p in pts)
    y = lambda v: 20 + (hi - v) / (hi - lo) * (h - 40)
    st = w / n; bw = st * .56; xc = w * cut; s = []
    for i, (o, hh, ll, c) in enumerate(pts):
        x = i * st + st / 2; col = "#D4A64A"; up = c >= o
        op = ".14" if (veil and x > xc) else "1"
        s.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="{y(hh):.0f}" y2="{y(ll):.0f}" stroke="{col}" stroke-width="2" opacity="{op}"/>')
        s.append(f'<rect x="{x-bw/2:.0f}" y="{y(max(o,c)):.0f}" width="{bw:.0f}" height="{max(2, y(min(o,c))-y(max(o,c))):.0f}" rx="2" fill="{col if up else "#000000"}" stroke="{col}" stroke-width="2" opacity="{op}"/>')
    if veil:
        s.append(f'<rect x="{xc:.0f}" y="0" width="{w-xc:.0f}" height="{h}" fill="#000000" opacity=".82"/>')
        s.append(f'<line x1="{xc:.0f}" x2="{xc:.0f}" y1="4" y2="{h-4}" stroke="#D4A64A" stroke-width="3" stroke-dasharray="10 7"/>')
    if sltp:
        s.append(f'<line x1="{w*.35:.0f}" x2="{xc:.0f}" y1="{h*.22:.0f}" y2="{h*.22:.0f}" stroke="#D4A64A" stroke-width="3" stroke-dasharray="14 6"/>')
        s.append(f'<line x1="{w*.35:.0f}" x2="{xc:.0f}" y1="{h*.78:.0f}" y2="{h*.78:.0f}" stroke="#D4A64A" stroke-width="3" stroke-dasharray="3 6"/>')
        s.append(f'<text x="{w*.36:.0f}" y="{h*.22-8:.0f}" font-family="YX" font-size="20" fill="#D4A64A">حد سود</text>')
        s.append(f'<text x="{w*.36:.0f}" y="{h*.78-8:.0f}" font-family="YX" font-size="20" fill="#D4A64A">حد ضرر</text>')
    return f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">{"".join(s)}</svg>'

CSS = f"""@font-face {{ font-family:YX; src:url('file://{FB}'); font-weight:700; }}
@font-face {{ font-family:YX; src:url('file://{FR}'); font-weight:400; }}
@font-face {{ font-family:YXL; src:url('file://{FL}'); font-weight:700; }}
html,body {{ margin:0; width:540px; height:960px; overflow:hidden; background:#000000; font-family:YX; color:#D4A64A; }}
.bg {{ position:absolute; inset:0; background: radial-gradient(ellipse 70% 40% at 50% 50%, rgba(212,166,74,.12), transparent 70%),
 repeating-linear-gradient(90deg, rgba(212,166,74,.06) 0 1px, transparent 1px 60px), repeating-linear-gradient(0deg, rgba(212,166,74,.06) 0 1px, transparent 1px 60px); }}
.a {{ position:absolute; }} .c {{ left:0; width:100%; text-align:center; }}
.sub {{ position:absolute; top:640px; left:40px; width:460px; text-align:center; font-size:26px; line-height:1.6; }}
.sub b {{ color:#000; background:#D4A64A; padding:0 8px; border-radius:6px; }}
.card {{ background:#000000; color:#D4A64A; border:2px solid #D4A64A; border-radius:16px; padding:10px 16px; font-size:22px; }}
.key {{ display:inline-block; background:#000000; border:2px solid #D4A64A; border-bottom-width:6px; border-radius:12px; padding:8px 16px;
  font-family:YXL; font-size:30px; color:#D4A64A; margin:0 6px; direction:ltr; }}
"""
frames = {
 "s01-hook": f"""<div class="bg"></div>
  <div class="a c" style="top:250px;font-size:120px;font-weight:700;color:rgba(212,166,74,.10)">دوباره</div>
  <div class="a c" style="top:330px;font-size:44px;font-weight:700;line-height:1.5">دوست داری<br><span style="color:#000;background:#D4A64A;padding:0 14px;border-radius:10px;font-size:58px">یه روزِ بازار</span><br>رو دوباره زندگی کنی؟</div>
  <div class="a c" style="top:620px;font-size:20px;color:#D4A64A;opacity:.7">کلمه‌ها یکی‌یکی با گفتار · سایه‌ی «دوباره» در پس‌زمینه</div>""",
 "s04-hidden": f"""<div class="bg"></div>
  <div class="a" style="top:170px;left:30px">{candles(480, 330)}</div>
  <div class="a" style="top:250px;left:400px;font-size:90px;font-weight:700;color:#D4A64A">؟</div>
  <div class="a card" style="top:130px;right:28px">کندل‌های بعدی: پنهان</div>
  <div class="a card" style="top:520px;left:40px;border-color:#D4A64A;color:#D4A64A;font-size:19px"><span style="font-family:YXL;color:#D4A64A">{{ }}</span> اسکریپت هم فقط گذشته رو می‌بینه</div>
  <div class="sub">یعنی تو هم، درست مثل همون روز، <b>آینده</b> رو نمی‌بینی</div>""",
 "s05-practice": f"""<div class="bg"></div>
  <div class="a" style="top:150px;left:30px">{candles(480, 330, veil=False, sltp=True, seed=5)}</div>
  <div class="a c" style="top:520px"><span class="key">Shift + B</span><span class="key">Shift + S</span></div>
  <div class="a c" style="top:590px;font-size:20px;color:#D4A64A;opacity:.8">خرید تمرینی · فروش تمرینی</div>
  <div class="sub" style="top:660px">با دو تا کلید، <b>خرید یا فروش تمرینی</b> بزن</div>""",
 "s11-end": f"""<div class="bg"></div>
  <div class="a c" style="top:330px;font-size:54px;font-weight:700;line-height:1.5">اول نمودار،<br><span style="color:#000;background:#D4A64A;padding:0 16px;border-radius:12px">بعد تصمیم</span></div>
  <div class="a" style="top:540px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:12px;font-size:30px;font-weight:700">
   <img src="file://{MARK}" style="height:44px"><span>پرو چارت</span></div>""",
}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 540, "height": 960})
    for name, body in frames.items():
        path = os.path.join(OUT, name + ".html")
        open(path, "w", encoding="utf-8").write(f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>')
        pg.goto("file://" + path); pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, name + ".png")); os.remove(path)
    b.close()
print("frames:", sorted(os.listdir(OUT)))
