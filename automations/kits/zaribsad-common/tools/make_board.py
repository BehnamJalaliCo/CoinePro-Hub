# -*- coding: utf-8 -*-
"""Zarib100x — renders the brand board (brand/board.png, for the owner) and the cover style board
(cover/board.png, the reference ChatGPT gets with every cover plate) from the brand's own fonts.

usage (on the workshop, PY = prochart-reels venv): PY -I COMMON/tools/make_board.py [--frames DIR]
  --frames DIR  the sample brief's stills (motion/sample: desk_engine.py --test 0.0,5.4,8.6,11.6,15.6 →
                build/dtest/00..04.jpg); the board shows four of them
Writes brand/board.png (1440×2560) and cover/board.png (1080×1920) next to this tool's kit."""
import sys
import tempfile
from pathlib import Path

COMMON = Path(__file__).resolve().parent.parent
PRO = Path("/home/studio/kits/fonts-pro")
OWN = COMMON / "fonts"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
MARK = COMMON / "brand" / "profile_round.png"
SAMPLES = sorted((COMMON / "cover" / "samples").glob("*.jpg"))


def arg(k, d):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def faces() -> str:
    rows = [(PRO / f"IRANYekanX-{n}.ttf", w) for n, w in (("Light", 300), ("Regular", 400), ("Bold", 700),
                                                               ("ExtraBold", 800), ("ExtraBlack", 950))]
    css = "".join(f'@font-face{{font-family:ZF;font-weight:{w};src:url("file://{p}")}}' for p, w in rows)
    css += "".join(f'@font-face{{font-family:ZM;font-weight:{w};src:url("file://{OWN / f}")}}'
                   for f, w in (("IBMPlexMono-Medium.ttf", 500), ("IBMPlexMono-SemiBold.ttf", 600)))
    css += f'@font-face{{font-family:ZC;font-weight:700;src:url("file://{OWN / "IBMPlexSansCondensed-Bold.ttf"}")}}'
    return css


BASE = """*{margin:0;padding:0;box-sizing:border-box}
body{background:#0A0814;color:#EEEAF8;font-family:ZF;overflow:hidden}
.m{font-family:ZM;font-weight:500;letter-spacing:3px;direction:ltr}
.c{font-family:ZC;font-weight:700;direction:ltr}
.x{color:#B28CFF}
.k{background:#8A3FFC;border-radius:.18em;padding:0 .16em;color:#EEEAF8}
.lab{font-family:ZM;font-weight:500;font-size:24px;letter-spacing:4px;color:#9A95B3;direction:ltr;text-transform:uppercase}
h2{font-weight:800;font-size:44px;display:flex;align-items:center;gap:16px}
h2::before{content:"";width:10px;height:44px;background:#8A3FFC;border-radius:3px}
"""


def brand_board(frames: list) -> str:
    fr = "".join(f'<img src="file://{f}">' for f in frames[:4])
    cov = f'<img src="file://{SAMPLES[0]}">' if SAMPLES else ""
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}{BASE}
body{{width:1440px;height:2560px;padding:70px 80px}}
.head{{display:flex;align-items:center;justify-content:space-between}}
.lock{{display:flex;align-items:center;gap:26px;direction:ltr}}
.lock img{{width:150px;height:150px;border-radius:50%;border:7px solid #8A3FFC}}
.lock .n{{font-size:96px;line-height:1}} .lock .p{{font-family:ZF;font-size:34px;color:#9A95B3;direction:rtl;margin-top:8px}}
.concept{{margin-top:34px;font-size:40px;line-height:1.6;font-weight:400}} .concept b{{font-weight:800}}
.sw{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:26px}}
.big{{height:250px;border-radius:28px;padding:28px 32px;display:flex;flex-direction:column;justify-content:space-between}}
.big .nm{{font-size:46px;font-weight:950}} .big .hx{{font-family:ZM;font-size:34px;font-weight:600;direction:ltr;text-align:left}}
.small{{display:grid;grid-template-columns:repeat(5,1fr);gap:18px;margin-top:22px}}
.small div{{height:150px;border-radius:20px;padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;font-size:28px;font-weight:700}}
.small .hx{{font-family:ZM;font-size:24px;font-weight:500;direction:ltr;text-align:left}}
.row{{display:flex;gap:40px;margin-top:26px;align-items:flex-start}}
.type{{flex:1;background:#141022;border:2px solid rgba(238,234,248,.12);border-top:5px solid #8A3FFC;border-radius:24px;padding:26px 34px}}
.type .s1{{font-size:120px;font-weight:950;line-height:1.25}} .type .s2{{font-size:44px;font-weight:700;line-height:1.6}}
.type .s3{{font-size:84px;line-height:1.1;margin-top:10px}} .type .s4{{font-size:30px;margin-top:12px;color:#9A95B3}}
.type .meta{{margin-top:8px}}
.frames{{display:flex;gap:22px;margin-top:26px}} .frames img{{width:239px;height:425px;border-radius:16px;border:2px solid rgba(238,234,248,.14)}}
.frames .cv{{border:3px solid #8A3FFC}}
.hud{{margin-top:22px;height:72px;border-radius:14px;background:#141022;display:flex;align-items:center;gap:26px;padding:0 22px;direction:ltr}}
.hud img{{width:44px;height:44px;border-radius:50%;border:3px solid #8A3FFC}} .hud .c{{font-size:36px}} .hud .m{{font-size:24px;color:#9A95B3}}
.cmp{{display:flex;gap:16px;margin-top:22px}} .cmp div{{flex:1;border-radius:16px;padding:14px 16px;font-size:26px;font-weight:700;height:120px;display:flex;flex-direction:column;justify-content:space-between}}
.cmp .t{{font-family:ZM;font-size:20px;font-weight:500;direction:ltr;text-align:left;opacity:.85}}
</style></head><body>
<div class="head"><div class="lock"><img src="file://{MARK}"><div><div class="n c">Zarib<span class="x">100x</span></div><div class="p">بهنام جلالی</div></div></div>
<div style="text-align:left"><div class="lab">BRAND BOARD · v1 · 2026-11-26</div><div class="c" style="font-size:64px;margin-top:10px">THE <span class="x">DESK</span></div></div></div>
<div class="concept"><b>قالب پیج: «میز ضریب»</b> — هر ریلز یک <b>بریف</b> از یک ترمینال سینمایی بازار است: داده‌ی واقعی روی صفحه، نمودار و عددهایی که زنده می‌شمارند، پنل‌های شیشه‌ای سه‌بعدی و یک خط بنفش امضا که «عدد مهم» را نشان می‌دهد</div>
<h2 style="margin-top:44px">دو رنگ سازمانی</h2>
<div class="sw"><div class="big" style="background:#8A3FFC"><div class="nm">بنفش ضریب</div><div class="hx">ZARIB VIOLET #8A3FFC</div></div>
<div class="big" style="background:#0A0814;border:3px solid rgba(238,234,248,.22)"><div class="nm">ابسیدین</div><div class="hx">OBSIDIAN #0A0814</div></div></div>
<div class="small"><div style="background:#EEEAF8;color:#0A0814">پلاتین<span class="hx">#EEEAF8</span></div>
<div style="background:#B28CFF;color:#0A0814">بنفش روشن<span class="hx">#B28CFF</span></div>
<div style="background:#19C37D;color:#0A0814">صعود<span class="hx">UP #19C37D</span></div>
<div style="background:#F2445A;color:#0A0814">نزول<span class="hx">DOWN #F2445A</span></div>
<div style="background:#141022;border:2px solid rgba(238,234,248,.2)">پنل<span class="hx">#141022</span></div></div>
<div class="lab" style="margin-top:14px;text-align:right;direction:rtl;letter-spacing:0;font-family:ZF;font-size:26px">سه لایه: برند (بنفش + ابسیدین) · محتوا (عکس‌ها و صحنه‌ها، آزاد) · معنا (سبز صعود، قرمز نزول؛ هرگز تزئین)</div>
<div class="row"><div class="type"><div class="lab">TYPE · IRANYEKANX PRO · IBM PLEX</div>
<div class="s1">ضریب <span class="k">۱۰۰</span> برابر؟</div>
<div class="s2">زیرنویس‌ها کلمه‌به‌کلمه، کلمه‌ی کلیدی <span class="x">بنفش روشن</span></div>
<div class="s3 c">$70.48 <span style="color:#19C37D;font-size:54px">▲ +1.9%</span></div>
<div class="s4 m">BRIEF 041 · SOL/USDT · 1D · LIVE</div></div></div>
<h2 style="margin-top:40px">نوار وضعیت و نشان</h2>
<div class="hud"><img src="file://{MARK}"><span class="c">Zarib<span class="x">100x</span></span><span class="m">BRIEF 041</span><span class="m">SOL/USDT</span><span class="m">12:00 IRST</span><span class="m" style="margin-left:auto;color:#B28CFF">LIVE ●</span></div>
<h2 style="margin-top:40px">نمونه‌ی ریلز و کاور</h2>
<div class="frames">{fr}{cov.replace('<img', '<img class="cv"')}</div>
<div class="cmp"><div style="background:#F3C242;color:#000">DotCoin<span class="t">#F3C242 + BLACK</span></div>
<div style="background:#05060A;border:2px solid #3D8BFF;color:#F2F4F8">behnamjalali.tech<span class="t">INK + SPECTRUM</span></div>
<div style="background:#000;border:2px solid #D4A64A;color:#D4A64A">Pro-Chart<span class="t">BLACK + #D4A64A</span></div>
<div style="background:#8A3FFC;color:#EEEAF8;outline:4px solid #EEEAF8"><span class="c">Zarib100x</span><span class="t">#8A3FFC + #0A0814</span></div></div>
</body></html>"""


def cover_board() -> str:
    s = "".join(f'<img src="file://{p}">' for p in SAMPLES[:2])
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}{BASE}
body{{width:1080px;height:1920px;padding:56px 60px}}
.t{{font-size:54px;font-weight:950}} .sub{{font-size:30px;color:#9A95B3;margin-top:8px}}
.sw{{display:flex;gap:22px;margin-top:30px}} .sw div{{flex:1;height:170px;border-radius:22px;padding:18px;display:flex;flex-direction:column;justify-content:flex-end;font-size:26px;font-weight:700}}
.sw .h{{font-family:ZM;font-size:22px;direction:ltr;text-align:left}}
.ex{{display:flex;gap:30px;margin-top:34px;justify-content:center}} .ex img{{width:450px;height:800px;border-radius:18px;border:2px solid rgba(238,234,248,.16)}}
.rule{{margin-top:30px;font-size:31px;line-height:1.75}} .rule b{{color:#B28CFF}}
</style></head><body>
<div class="t">کاور Zarib<span class="x">100x</span> — فقط راهنمای سبک</div>
<div class="sub">STYLE GUIDE ONLY — DO NOT COPY THIS BOARD, ITS TEXT OR ITS SWATCHES INTO THE PICTURE</div>
<div class="sw"><div style="background:#0A0814;border:3px solid rgba(238,234,248,.25)">ابسیدین<span class="h">#0A0814 · 75%</span></div>
<div style="background:#8A3FFC">بنفش ضریب<span class="h">#8A3FFC · LIGHT</span></div>
<div style="background:#EEEAF8;color:#0A0814">پلاتین<span class="h">#EEEAF8</span></div></div>
<div class="ex">{s}</div>
<div class="rule">• تصویر شما فقط <b>بخش بالایی</b> است (تا حدود ۶۵٪ ارتفاع): یک سوژه‌ی واحد، فوتورئال یا رندر سه‌بعدی پریمیوم<br>
• زمینه ابسیدین تقریباً سیاه با ته‌رنگ بنفش؛ نور لبه و نور کلید <b>بنفش <bdi dir="ltr">#8A3FFC</bdi></b> از بالا-راست<br>
• ۳۵٪ پایین کاملاً خالی و تیره بماند: تیتر، برچسب و نشان را خودمان می‌گذاریم<br>
• هیچ نوشته، حرف، عدد، لوگو، قاب یا واترمارک — هیچ ذره، مه، بوکه یا دانه</div>
</body></html>"""


def shot(html: str, w: int, h: int, out: Path) -> None:
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "b.html"
        f.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--allow-file-access-from-files", "--no-sandbox"])
            try:
                pg = b.new_page(viewport={"width": w, "height": h})
                pg.goto(f.as_uri())
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(400)
                pg.screenshot(path=str(out))
            finally:
                b.close()
    print(out)


def main() -> None:
    fdir = Path(arg("--frames", str(COMMON / "motion" / "sample" / "build" / "dtest")))
    frames = sorted(fdir.glob("*.jpg"))
    frames = [frames[i] for i in (0, 1, 2, 4) if i < len(frames)] or frames
    shot(brand_board(frames), 1440, 2560, COMMON / "brand" / "board.png")
    shot(cover_board(), 1080, 1920, COMMON / "cover" / "board.png")


if __name__ == "__main__":
    main()
