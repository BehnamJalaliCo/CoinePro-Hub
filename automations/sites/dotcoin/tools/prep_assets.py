#!/usr/bin/env python3
"""Turn the private brand files into web assets (never committed).

usage: prep_assets.py SRC_DIR OUT_DIR
  SRC_DIR holds copies of the studio files: IRANYekanXFaNum-*.ttf, IRANYekanX-Regular.ttf, Anton-Regular.ttf,
          logo_round.png (deploy.sh copies them in with `sudo -n -u studio cat`).
  OUT_DIR receives fonts/*.woff2 and img/* (logo sizes, favicons).
Needs fontTools + brotli + Pillow (deploy.sh makes a venv for them).
"""
import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image

FONTS = {  # source file -> web name
    "IRANYekanXFaNum-Light.ttf": "yekan-300.woff2",
    "IRANYekanXFaNum-Regular.ttf": "yekan-400.woff2",
    "IRANYekanXFaNum-DemiBold.ttf": "yekan-600.woff2",
    "IRANYekanXFaNum-ExtraBold.ttf": "yekan-800.woff2",
    "IRANYekanXFaNum-ExtraBlack.ttf": "yekan-950.woff2",
}
# Persian + Arabic shaping blocks, ZWNJ/marks, basic Latin, punctuation, arrows used in the UI.
YEKAN_RANGES = "U+0020-007E,U+00A0-00BB,U+00D7,U+0600-06FF,U+200C-200F,U+2010-2027,U+2030-203A,U+2190-2193,U+2212,U+FB50-FDFF,U+FE70-FEFF"
ANTON_RANGES = "U+0020-007E,U+00A0,U+00B7,U+2013-2014,U+2019,U+2190-2193"


def make_font(src: Path, dst: Path, ranges: str) -> None:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.hinting = False
    opts.desubroutinize = True
    font = subset.load_font(str(src), opts)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=subset.parse_unicodes(ranges))
    sub.subset(font)
    subset.save_font(font, str(dst), opts)


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    (out / "fonts").mkdir(parents=True, exist_ok=True)
    (out / "img").mkdir(parents=True, exist_ok=True)
    for name, web in FONTS.items():
        make_font(src / name, out / "fonts" / web, YEKAN_RANGES)
    make_font(src / "Anton-Regular.ttf", out / "fonts" / "anton.woff2", ANTON_RANGES)
    # Latin digits for Latin names such as BIP39 (the FaNum cut draws every digit in Persian).
    make_font(src / "IRANYekanX-Regular.ttf", out / "fonts" / "yekan-lat.woff2", "U+0030-0039")
    # Anton advance widths: build.py sizes each giant word to fill its line exactly.
    anton = TTFont(src / "Anton-Regular.ttf")
    cmap, hmtx = anton.getBestCmap(), anton["hmtx"]
    adv = {chr(c): hmtx[g][0] for c, g in cmap.items() if c < 0x2200}
    (out / "anton-metrics.json").write_text(json.dumps({"upm": anton["head"].unitsPerEm, "adv": adv}))

    logo = Image.open(src / "logo_round.png").convert("RGBA")
    for px in (96, 192, 384, 640):
        im = logo.resize((px, px), Image.LANCZOS)
        im.save(out / "img" / f"logo-{px}.webp", "WEBP", quality=88, method=6)
        if px == 384:
            im.save(out / "img" / f"logo-{px}.png", optimize=True)
    # favicons: the round mark as is, transparent corners (browser tab) ...
    logo.resize((32, 32), Image.LANCZOS).save(out / "img" / "favicon-32.png", optimize=True)
    logo.save(out / "img" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # ... and on a mustard square where the platform needs an opaque icon (iOS, Android).
    for px, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        ground = Image.new("RGBA", (px, px), (243, 194, 66, 255))
        ground.alpha_composite(logo.resize((px, px), Image.LANCZOS))
        ground.convert("RGB").save(out / "img" / name, optimize=True)
    for f in sorted((out / "fonts").iterdir()):
        print(f"{f.name}: {f.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
