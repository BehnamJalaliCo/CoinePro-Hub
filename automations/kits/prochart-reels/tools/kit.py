# -*- coding: utf-8 -*-
"""Builds the ProChart cover kit v1: palette, safe-zone template, grid preview, guide + prompts, fonts, ZIP."""
import os, shutil, json, zipfile
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()  # the day's own folder
KIT = "/home/studio/kits/prochart-reels"
KIT = os.path.join(KIT, "coverkit")
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FB = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Bold.ttf")
FR = os.path.join(KIT, "fontpack_raw", "IRANYekanXFaNum-Regular.ttf")
COVER = os.path.join(KIT, "examples", "cover-01-replay.png")
FONTCSS = f"""@font-face {{ font-family: YX; src: url('file://{FB}'); font-weight:700; }}
@font-face {{ font-family: YX; src: url('file://{FR}'); font-weight:400; }}
@font-face {{ font-family: YXL; src: url('file://{os.path.join(KIT, "fontpack_raw", "IRANYekanX-Regular.ttf")}'); }}
html, body {{ margin:0; background:#0F0F0F; font-family:YX; color:#fff; }}"""

PALETTE = [("پس‌زمینه", "#0F0F0F"), ("سطح", "#161616"), ("سطح بالا", "#1E1E1E"), ("خط شبکه", "#262626"),
           ("طلایی اصلی", "#D4A64A"), ("طلایی روشن", "#E2B85E"), ("متن", "#FFFFFF"), ("متن دوم", "#DBDBDB"),
           ("کندل صعودی", "#089981"), ("کندل نزولی", "#F23645")]

def shoot(html, path, w, h):
    tmp = path + ".html"
    open(tmp, "w", encoding="utf-8").write(html)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto("file://" + tmp); pg.wait_for_timeout(500)
        pg.screenshot(path=path); b.close()
    os.remove(tmp)

os.makedirs(os.path.join(KIT, "palette"), exist_ok=True)
os.makedirs(os.path.join(KIT, "templates"), exist_ok=True)
os.makedirs(os.path.join(KIT, "fonts"), exist_ok=True)

# palette
sw = "".join(f'<div class="s"><div class="c" style="background:{c}"></div><b>{n}</b><span>{c}</span></div>' for n, c in PALETTE)
shoot(f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{FONTCSS}
.w {{ display:grid; grid-template-columns:repeat(5,1fr); gap:24px; padding:40px; }}
.s {{ text-align:center; }} .c {{ height:150px; border-radius:18px; border:2px solid #2E2E2E; }}
b {{ display:block; margin-top:10px; font-size:26px; }} span {{ font-size:24px; color:#B8B8B8; direction:ltr; display:block; font-family:YXL; }}
</style></head><body><div class="w">{sw}</div></body></html>""", os.path.join(KIT, "palette", "palette.png"), 1200, 560)
json.dump({n: c for n, c in PALETTE}, open(os.path.join(KIT, "palette", "palette.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# safe-zone template (1080x1920)
shoot(f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{FONTCSS}
body {{ width:1080px; height:1920px; position:relative; overflow:hidden; }}
.z {{ position:absolute; left:0; width:1080px; box-sizing:border-box; }}
.grid {{ top:240px; height:1440px; border:6px dashed #8C8C8C; }}
.feed {{ top:285px; height:1350px; border:6px solid #D4A64A; }}
.margin {{ top:285px; height:1350px; left:70px; width:940px; border:3px dotted #2EC4B6; }}
.lab {{ position:absolute; font-size:34px; font-weight:700; }}
</style></head><body>
<div class="z grid"></div><div class="z feed"></div><div class="z margin"></div>
<div class="lab" style="top:120px;width:100%;text-align:center;color:#8C8C8C">بیرون از قاب امن: فقط پس‌زمینه</div>
<div class="lab" style="top:300px;right:90px;color:#D4A64A">قاب امن ۱۰۸۰ در ۱۳۵۰ (فید ۴ به ۵)</div>
<div class="lab" style="top:250px;left:20px;color:#8C8C8C;font-size:26px">صفحه‌ی اصلی ۳ به ۴ (۱۰۸۰ در ۱۴۴۰)</div>
<div class="lab" style="top:900px;width:100%;text-align:center;color:#2EC4B6">همه‌ی متن و المان اصلی داخل این کادر · حاشیه ۷۰</div>
<div class="lab" style="top:1760px;width:100%;text-align:center;color:#8C8C8C">بیرون از قاب امن: فقط پس‌زمینه</div>
</body></html>""", os.path.join(KIT, "templates", "safe-zone-1080x1920.png"), 1080, 1920)

# grid / feed preview of the sample cover
prev = os.path.join(ROOT, "build", "cover_preview.png")
shoot(f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{FONTCSS}
body {{ width:1180px; height:900px; padding:30px 30px; box-sizing:border-box; }}
.row {{ display:flex; gap:36px; align-items:flex-start; justify-content:center; }}
.col {{ text-align:center; }} .col b {{ display:block; font-size:30px; margin:12px 0 4px; }} .col span {{ font-size:22px; color:#B8B8B8; }}
.f {{ border-radius:18px; overflow:hidden; border:2px solid #2E2E2E; background:#000; }}
.f img {{ display:block; width:100%; height:100%; object-fit:cover; object-position:50% 50%; }}
h1 {{ font-size:36px; margin:0 0 18px; text-align:center; color:#E2B85E; }}
</style></head><body><h1>کاور نمونه‌ی ویدیوی اول، در سه جای اینستاگرام</h1><div class="row">
<div class="col"><div class="f" style="width:340px;height:604px"><img src="file://{COVER}"></div><b>کامل (ریلز)</b><span>۱۰۸۰ در ۱۹۲۰</span></div>
<div class="col"><div class="f" style="width:340px;height:453px"><img src="file://{COVER}"></div><b>صفحه‌ی اصلی</b><span>برش ۳ به ۴</span></div>
<div class="col"><div class="f" style="width:340px;height:425px"><img src="file://{COVER}"></div><b>فید</b><span>برش ۴ به ۵</span></div>
</div></body></html>""", prev, 1180, 900)

# fonts (owner's IRANYekanX Eco: Regular + Bold, with and without Persian digits)
for f in ["IRANYekanX-Bold.ttf", "IRANYekanX-Regular.ttf", "IRANYekanXFaNum-Bold.ttf", "IRANYekanXFaNum-Regular.ttf", "FontLicense.txt"]:
    shutil.copy(os.path.join(KIT, "fontpack_raw", f), os.path.join(KIT, "fonts", f))

# example cover as JPG too
Image.open(COVER).convert("RGB").save(os.path.join(KIT, "examples", "cover-01-replay.jpg"), quality=92)
print("kit assets ok")
