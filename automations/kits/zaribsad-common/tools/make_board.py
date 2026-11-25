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
body{background:#160A0E;color:#F4EFE6;font-family:ZF;overflow:hidden}
.m{font-family:ZM;font-weight:500;letter-spacing:3px;direction:ltr}
.c{font-family:ZC;font-weight:700;direction:ltr}
.x{color:#83CAAD}
.k{background:#83CAAD;border-radius:.18em;padding:0 .16em;color:#160A0E}
.lab{font-family:ZM;font-weight:500;font-size:24px;letter-spacing:4px;color:#A8979B;direction:ltr;text-transform:uppercase}
h2{font-weight:800;font-size:44px;display:flex;align-items:center;gap:16px}
h2::before{content:"";width:10px;height:44px;background:#83CAAD;border-radius:3px}
"""


def brand_board(frames: list) -> str:
    fr = "".join(f'<img src="file://{f}">' for f in frames[:3])
    cov = "".join(f'<img class="cv" src="file://{p}">' for p in SAMPLES[:2])
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}{BASE}
body{{width:1440px;height:2560px;padding:70px 80px;background:radial-gradient(1200px 900px at 75% 8%,#461A23,#160A0E 70%)}}
.head{{display:flex;align-items:center;justify-content:space-between}}
.lock{{display:flex;align-items:center;gap:26px;direction:ltr}}
.lock img{{width:160px;height:160px;border-radius:50%;border:7px solid #83CAAD}}
.lock .n{{font-size:96px;line-height:1}} .lock .p{{font-family:ZF;font-size:34px;color:#A8979B;direction:rtl;margin-top:8px}}
.concept{{margin-top:30px;font-size:38px;line-height:1.6;font-weight:400}} .concept b{{font-weight:800}}
.sw{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:24px}}
.big{{height:240px;border-radius:28px;padding:26px 32px;display:flex;flex-direction:column;justify-content:space-between}}
.big .nm{{font-size:46px;font-weight:950}} .big .hx{{font-family:ZM;font-size:32px;font-weight:600;direction:ltr;text-align:left}}
.small{{display:grid;grid-template-columns:repeat(5,1fr);gap:18px;margin-top:20px}}
.small div{{height:140px;border-radius:20px;padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;font-size:28px;font-weight:700}}
.small .hx{{font-family:ZM;font-size:23px;font-weight:500;direction:ltr;text-align:left}}
.mean{{margin-top:20px;background:#241016;border:2px solid rgba(244,239,230,.12);border-radius:22px;padding:20px 30px;display:flex;align-items:center;gap:36px}}
.mean .v{{font-family:ZC;font-size:52px;direction:ltr}} .mean p{{font-size:28px;line-height:1.6;flex:1}}
.type{{margin-top:24px;background:#241016;border:2px solid rgba(244,239,230,.12);border-top:5px solid #83CAAD;border-radius:24px;padding:22px 34px}}
.type .s1{{font-size:112px;font-weight:950;line-height:1.25}} .type .s2{{font-size:40px;font-weight:700;line-height:1.6}}
.type .s4{{font-size:28px;margin-top:6px;color:#A8979B}}
.frames{{display:flex;gap:22px;margin-top:24px}} .frames img{{width:239px;height:425px;border-radius:16px;border:2px solid rgba(244,239,230,.14)}}
.frames .cv{{border:3px solid #83CAAD}}
.cmp{{display:flex;gap:16px;margin-top:22px}} .cmp div{{flex:1;border-radius:16px;padding:14px 16px;font-size:26px;font-weight:700;height:112px;display:flex;flex-direction:column;justify-content:space-between}}
.cmp .t{{font-family:ZM;font-size:20px;font-weight:500;direction:ltr;text-align:left;opacity:.85}}
</style></head><body>
<div class="head"><div class="lock"><img src="file://{MARK}"><div><div class="n c">Zarib<span class="x">100x</span></div><div class="p">بهنام جلالی</div></div></div>
<div style="text-align:left"><div class="lab">BRAND BOARD · v2 · 2026-11-26</div><div class="c" style="font-size:64px;margin-top:10px">THE <span class="x">DESK</span></div></div></div>
<div class="concept"><b>رنگ‌ها از عکس پروفایل:</b> نعنایی پس‌زمینه و زرشکی کت. هر ریلز یک <b>بریف</b> از یک ترمینال سینمایی بازار است: داده‌ی واقعی، عددهایی که زنده می‌شمارند و خط نعنایی امضا</div>
<h2 style="margin-top:36px">دو رنگ سازمانی</h2>
<div class="sw"><div class="big" style="background:#83CAAD;color:#160A0E"><div class="nm">نعنایی ضریب</div><div class="hx">ZARIB MINT #83CAAD</div></div>
<div class="big" style="background:#461A23"><div class="nm">زرشکی</div><div class="hx">OXBLOOD #461A23</div></div></div>
<div class="small"><div style="background:#160A0E;border:2px solid rgba(244,239,230,.2)">زمینه<span class="hx">#160A0E</span></div>
<div style="background:#F4EFE6;color:#160A0E">عاجی<span class="hx">#F4EFE6</span></div>
<div style="background:#241016;border:2px solid rgba(244,239,230,.2)">پنل<span class="hx">#241016</span></div>
<div style="background:#6B2A37">زرشکی روشن<span class="hx">#6B2A37</span></div>
<div style="background:#A8979B;color:#160A0E">خاکستری گرم<span class="hx">#A8979B</span></div></div>
<div class="mean"><div class="v" style="color:#35E06E">▲ +1.9%</div><div class="v" style="color:#FF4D57">▼ −3.4%</div>
<p>لایه‌ی معنا: صعود و نزول <b>همیشه با ▲ / ▼ و علامت</b>، به سبز تند <bdi dir="ltr">#35E06E</bdi> و قرمز <bdi dir="ltr">#FF4D57</bdi>؛ نعنایی هرگز روی عدد، نمودار یا جهت نمی‌آید</p></div>
<div class="type"><div class="lab">TYPE · IRANYEKANX PRO · IBM PLEX</div>
<div class="s1">ضریب <span class="k">۱۰۰</span> برابر؟</div>
<div class="s2">زیرنویس‌ها کلمه‌به‌کلمه، کلمه‌ی کلیدی <span class="x">نعنایی</span></div>
<div class="s4 m">BRIEF 041 · SOL/USDT · 1D · LIVE</div></div>
<h2 style="margin-top:34px">نمونه‌ی ریلز و کاور</h2>
<div class="frames">{fr}{cov}</div>
<div class="cmp"><div style="background:#F3C242;color:#000">DotCoin<span class="t">#F3C242 + BLACK</span></div>
<div style="background:#05060A;border:2px solid #3D8BFF;color:#F2F4F8">behnamjalali.tech<span class="t">INK + SPECTRUM</span></div>
<div style="background:#000;border:2px solid #D4A64A;color:#D4A64A">Pro-Chart<span class="t">BLACK + #D4A64A</span></div>
<div style="background:#461A23;color:#F4EFE6;outline:4px solid #83CAAD"><span class="c">Zarib<span class="x">100x</span></span><span class="t">#83CAAD + #461A23</span></div></div>
</body></html>"""


def cover_board() -> str:
    s = "".join(f'<img src="file://{p}">' for p in SAMPLES[:2])
    return f"""<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>{faces()}{BASE}
body{{width:1080px;height:1920px;padding:56px 60px}}
.t{{font-size:52px;font-weight:950}} .sub{{font-size:28px;color:#A8979B;margin-top:8px;direction:ltr;text-align:left}}
.sw{{display:flex;gap:18px;margin-top:26px}} .sw div{{flex:1;height:150px;border-radius:22px;padding:16px;display:flex;flex-direction:column;justify-content:flex-end;font-size:26px;font-weight:700}}
.sw .h{{font-family:ZM;font-size:21px;direction:ltr;text-align:left}}
.ex{{display:flex;gap:30px;margin-top:30px;justify-content:center}} .ex img{{width:440px;height:782px;border-radius:18px;border:2px solid rgba(244,239,230,.16)}}
.rule{{margin-top:26px;font-size:29px;line-height:1.7}} .rule b{{color:#83CAAD}}
</style></head><body>
<div class="t">کاور Zarib<span class="x">100x</span> — راهنمای سبک</div>
<div class="sub">STYLE GUIDE ONLY — FOLLOW ITS STYLE; NEVER COPY THIS BOARD, ITS LABELS OR ITS SWATCHES INTO THE COVER</div>
<div class="sw"><div style="background:#160A0E;border:3px solid rgba(244,239,230,.25)">زمینه<span class="h">#160A0E</span></div>
<div style="background:#461A23">زرشکی<span class="h">#461A23</span></div>
<div style="background:#83CAAD;color:#160A0E">نعنایی<span class="h">#83CAAD</span></div>
<div style="background:#F4EFE6;color:#160A0E">عاجی<span class="h">#F4EFE6</span></div></div>
<div class="ex">{s}</div>
<div class="rule">• زمینه‌ی زرشکیِ تیره با نور نرم؛ پشت او یک <b>طاق نعنایی</b> (مستطیل با سر نیم‌دایره)<br>
• بالای کاور: <bdi dir="ltr">Zarib100x</bdi> کوچک در چپ، برچسب انگلیسی موضوع در راست<br>
• او از کمر به بالا یا تا زانو، تنش پشت تیتر در زمینه‌ی تیره محو می‌شود؛ هرگز پا زیر تیتر<br>
• تیتر فارسی سنگین عاجی، یک کلمه در <b>جعبه‌ی نعنایی</b> با حروف تیره؛ زیرش قرص با حاشیه‌ی عاجی</div>
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
    frames = [frames[i] for i in (0, 1, 4) if i < len(frames)] or frames
    shot(brand_board(frames), 1440, 2560, COMMON / "brand" / "board.png")
    shot(cover_board(), 1080, 1920, COMMON / "cover" / "board.png")


if __name__ == "__main__":
    main()
