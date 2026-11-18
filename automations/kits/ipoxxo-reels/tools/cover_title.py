# -*- coding: utf-8 -*-
"""The reel's cover with the title set by us (COVER_PACK.md step 4, and whenever ChatGPT's letters are not
perfect): a text-free background (ChatGPT, from the pack's brief, «leave the title area empty») + the title in
IRANYekanX Eco Bold, white with the key word in neon cyan, inside the frame's central square (it survives the
1:1 and 4:5 grid crops). Rendered by Chromium, so Persian is shaped right.

usage: PY -I KIT/tools/cover_title.py BG.png out/cover.jpg "عمیق‌ترین|چاه دنیا" [--key عمیق‌ترین] [--sub "۱۲٬۲۶۲ متر"]
       [--y 760] [--px 150]
  the title: lines split by «|»; --key: the word(s) in cyan (comma separated); --sub: one small line under it;
  --y: the title block's centre (default 760: the central square's upper half). No full stop at the end.
"""
import base64
import html
import os
import sys
import tempfile

FD = "/home/studio/kits/fonts-eco/"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def main():
    bg, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
    keys = [k for k in arg("--key", "").split(",") if k]
    sub = arg("--sub", "")
    y, px = int(arg("--y", "760")), int(arg("--px", "150"))
    font = base64.b64encode(open(FD + "IRANYekanXFaNum-Bold.ttf", "rb").read()).decode()
    pic = base64.b64encode(open(bg, "rb").read()).decode()
    mime = "image/png" if bg.lower().endswith(".png") else "image/jpeg"

    def word(w):
        e = html.escape(w.rstrip(".،؛"))
        return f'<span class="k">{e}</span>' if any(k in w for k in keys) else e

    lines = "".join(f"<div>{' '.join(word(w) for w in ln.split())}</div>" for ln in title.split("|"))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Y; src: url(data:font/ttf;base64,{font}); }}
html, body {{ margin: 0; width: 1080px; height: 1920px; background: #000928; }}
.bg {{ position: absolute; inset: 0; background: url(data:{mime};base64,{pic}) center / cover no-repeat; }}
.t {{ position: absolute; left: 60px; right: 60px; top: {y}px; transform: translateY(-50%); direction: rtl;
     text-align: center; font: {px}px/1.18 Y; color: #F5FBFF; text-shadow: 0 6px 30px rgba(0,9,40,.85); }}
.k {{ color: #04F6FF; text-shadow: 0 0 34px rgba(4,246,255,.55), 0 6px 30px rgba(0,9,40,.85); }}
.s {{ font-size: {int(px * .36)}px; color: rgba(245,251,255,.8); margin-top: {int(px * .25)}px; }}
</style></head><body><div class="bg"></div><div class="t">{lines}{f'<div class="s">{html.escape(sub)}</div>' if sub else ''}</div></body></html>"""
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "cover.html")
        open(p, "w", encoding="utf-8").write(page)
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--disable-gpu"])
            pg = b.new_page(viewport={"width": 1080, "height": 1920})
            pg.goto("file://" + p)
            pg.evaluate("document.fonts.ready")
            png = os.path.join(tmp, "c.png")
            pg.screenshot(path=png, full_page=False)
            b.close()
        from PIL import Image
        Image.open(png).convert("RGB").save(out, "JPEG", quality=92)
    print("wrote", out)


if __name__ == "__main__":
    main()
