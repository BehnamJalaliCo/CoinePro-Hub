"""Makes the OCR samples from scan_fa.txt (prompt 14 §4, §11): a "scanned"
page of Persian text, IRANYekanX at about 300 dpi, turned a little, with
speckle noise, binarised like a fax; and the same page as an image-only PDF
(no text layer). Deterministic: the noise has a fixed seed.

Run once, in a throwaway container with resvg-py and Pillow (the api's test
image has both), from the repository root:

    docker run --rm --network none -v "$PWD:/repo" -w /repo \
      coinepro-hq/api-test:<tag> python services/ocr/tests/samples/make_samples.py

The committed scan_fa.png and scan_fa.pdf are its output; the tests read only
those and scan_fa.txt.
"""

from __future__ import annotations

import html
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE.parents[3] / "design" / "fonts" / "static"
WIDTH, LINE, SIZE, MARGIN = 2480, 120, 58, 180  # A4 width at 300 dpi; 58 px ~ 14 pt
SEED = 14


def svg(lines: list[str]) -> str:
    height = MARGIN * 2 + LINE * len(lines)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}"><rect width="{WIDTH}" height="{height}" fill="#ffffff"/>'
    ]
    for i, line in enumerate(lines):
        y = MARGIN + LINE * (i + 1)
        parts.append(
            f'<text x="{WIDTH - MARGIN}" y="{y}" font-family="IRANYekanX" font-size="{SIZE}" '
            f'fill="#1a1a1a" direction="rtl" unicode-bidi="embed" text-anchor="end">'
            f"{html.escape(line)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    import io

    import resvg_py
    from PIL import Image

    lines = [x for x in (HERE / "scan_fa.txt").read_text("utf-8").splitlines() if x.strip()]
    png = bytes(
        resvg_py.svg_to_bytes(
            svg_string=svg(lines),
            skip_system_fonts=True,
            font_files=[str(FONTS / "IRANYekanX-Regular.ttf")],
            font_family="IRANYekanX",
        )
    )
    page = Image.open(io.BytesIO(png)).convert("L")
    # A scanner's page: turned 0.7 degrees, a little grey, speckled, binarised.
    page = page.rotate(0.7, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    rnd = random.Random(SEED)
    px = page.load()
    assert px is not None
    w, h = page.size
    for _ in range(w * h // 400):
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = rnd.choice((0, 40, 90))
    page = page.point(lambda v: 0 if v < 150 else 255).convert("1")
    page.save(HERE / "scan_fa.png", optimize=True, dpi=(300, 300))
    page.save(HERE / "scan_fa.pdf", "PDF", resolution=300.0)
    print(f"scan_fa.png {page.size[0]}x{page.size[1]}; scan_fa.pdf (image only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
