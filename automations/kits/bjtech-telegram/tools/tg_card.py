#!/usr/bin/env python3
"""A Telegram card, table or cheat sheet from your own HTML (the render venv's Playwright and the kit's Chromium):
    PY -I KIT/tools/tg_card.py <page.html> <out.jpg> [--size 1080x1350]   a JPEG (quality 92)
    PY -I KIT/tools/tg_card.py <page.html> --pdf <out.pdf>               an A4 PDF (the Wednesday cheat sheet)
Start from KIT/templates/card.html or table.html: `@@FONTS@@` there becomes the page's @font-face rules (Estedad,
Geist, Geist Mono, IRANYekanX from the kits' font folders) and `@@LOGO@@` the page's round profile logo (always beside
the handle, never a coloured dot). The page is opened from its own folder, so relative
pictures work. Every Persian letter is set by the browser, never by an image model."""
import base64
import os
import sys
import tempfile
from pathlib import Path

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
FD = os.environ.get("BJ_FONTS", "/home/studio/kits/fonts-bj")
# ⟨2026-11-19⟩ the page's round profile logo (COMMON/brand/logo_round.png) beside the handle: `@@LOGO@@` in the HTML
LOGO = os.environ.get("BJ_LOGO", "/home/studio/kits/bjtech-common/brand/logo_round.png")
FP = os.environ.get("BJ_FONTS_PRO", "/home/studio/kits/fonts-pro")
FONTS = "".join(
    f"@font-face{{font-family:{fam};src:url(file://{d}/{f});font-weight:{w}}}"
    for fam, d, f, w in (
        ("EST", FD, "Estedad-Medium.ttf", 500), ("EST", FD, "Estedad-Bold.ttf", 700),
        ("EST", FD, "Estedad-ExtraBold.ttf", 800), ("EST", FD, "Estedad-Black.ttf", 900),
        ("GEI", FD, "Geist-Medium.ttf", 500), ("GEI", FD, "Geist-Bold.ttf", 700), ("GEI", FD, "Geist-Black.ttf", 900),
        ("GMO", FD, "GeistMono-Medium.ttf", 500),
        ("YKX", FP, "IRANYekanXFaNum-Bold.ttf", 700), ("YKX", FP, "IRANYekanXFaNum-ExtraBlack.ttf", 900),
    )
)


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 2
    src = Path(args[0]).resolve()
    pdf = args[1] == "--pdf"
    out = Path(args[2] if pdf else args[1]).resolve()
    w, h = 1080, 1350
    if "--size" in args:
        w, h = (int(x) for x in args[args.index("--size") + 1].lower().split("x"))
    logo = "data:image/png;base64," + base64.b64encode(Path(LOGO).read_bytes()).decode()
    page_html = src.read_text("utf-8").replace("@@FONTS@@", FONTS).replace("@@LOGO@@", logo)
    from playwright.sync_api import sync_playwright

    with tempfile.NamedTemporaryFile("w", suffix=".html", dir=src.parent, delete=False, encoding="utf-8") as t:
        t.write(page_html)
        tmp = Path(t.name)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True,
                                  args=["--no-sandbox", "--disable-gpu", "--allow-file-access-from-files"])
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.goto(tmp.as_uri())
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(300)
            if pdf:
                pg.pdf(path=str(out), format="A4", print_background=True)
            else:
                pg.screenshot(path=str(out), type="jpeg", quality=92, full_page=False)
            b.close()
    finally:
        tmp.unlink(missing_ok=True)
    size = out.stat().st_size
    print(f"ok {out.name} {size / 1e6:.2f} MB")
    return 0 if size <= 10 * 1024 * 1024 else 1


if __name__ == "__main__":
    sys.exit(main())
