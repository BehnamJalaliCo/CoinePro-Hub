# -*- coding: utf-8 -*-
"""Zarib100x — the cover's row check (cover/COVER_SYSTEM.md «ONE FAMILY»): the new cover beside the page's last
4 covers in one sheet, plus the family's three machine checks. Read the sheet before delivering.

usage: PY -I COMMON/tools/cover_sheet.py NEW_COVER qc/cover_sheet.jpg [--family DIR] [--n 4]
  the row = the newest N of: DIR if given; else the covers earlier Zarib100x sessions kept as qc/z100x_cover.jpg
  (/home/studio/hq-workspace/*/qc/, newest by time, this folder excluded); fewer than N found → the family's
  samples (COMMON/cover/samples/) fill the row. Every session copies its delivered cover to qc/z100x_cover.jpg.
prints, and exits 1 on any WRONG:
  ground ok|WRONG    the frame's outer ring is obsidian (#0A0814 ± a little), never a light or another colour
  zline ok|WRONG     the violet Zarib Line is under the title (y ≈ 1488 at 1080×1920)
  ticks ok|WRONG     the four violet corner ticks of the frame are there
"""
import glob
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "cover" / "samples"
OB = np.array([10, 8, 20])
VI = np.array([138, 63, 252])
H = 800


def arg(k, d):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def row(new: Path, n: int) -> list:
    fam = arg("--family", "")
    if fam:
        got = sorted(p for p in Path(fam).glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))[-n:]
    else:
        me = os.path.realpath(os.getcwd())
        cands = []
        for p in glob.glob("/home/studio/hq-workspace/*/qc/z100x_cover.jpg"):
            if not os.path.realpath(p).startswith(me + os.sep):
                try:
                    cands.append((os.path.getmtime(p), Path(p)))
                except OSError:
                    pass
        got = [p for _, p in sorted(cands)[-n:]]
    if len(got) < n:
        got = sorted(SAMPLES.glob("*.jpg"))[: n - len(got)] + got
    return got


def checks(a: np.ndarray) -> dict:
    h, w, _ = a.shape
    sy, sx = h / 1920, w / 1080
    b = max(4, round(min(h, w) * 0.015))
    ring = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3)])
    ground = float(np.abs(np.median(ring, 0) - OB).sum()) <= 45
    band = a[int(1478 * sy):int(1500 * sy), int(100 * sx):int(980 * sx)].reshape(-1, 3)
    zline = float((np.abs(band - VI).sum(1) < 120).mean()) > 0.15
    ticks = 0
    for (x0, y0) in ((30, 230), (1006, 230), (30, 1646), (1006, 1646)):
        patch = a[int(y0 * sy):int((y0 + 44) * sy), int(x0 * sx):int((x0 + 44) * sx)].reshape(-1, 3)
        ticks += float((np.abs(patch - VI).sum(1) < 120).mean()) > 0.08
    return {"ground": ground, "zline": zline, "ticks": ticks == 4}


def main() -> int:
    new, out = Path(sys.argv[1]), Path(sys.argv[2])
    n = int(arg("--n", "4"))
    im = Image.open(new).convert("RGB")
    res = checks(np.asarray(im.resize((1080, 1920), Image.LANCZOS)).astype(int))
    tiles = [Image.open(p).convert("RGB") for p in row(new, n)] + [im]
    tiles = [t.resize((round(t.width * H / t.height), H), Image.LANCZOS) for t in tiles]
    W = sum(t.width for t in tiles) + 16 * (len(tiles) + 1)
    sheet = Image.new("RGB", (W, H + 32), (34, 34, 34))
    x = 16
    for i, t in enumerate(tiles):
        sheet.paste(t, (x, 16))
        if i == len(tiles) - 1:
            ImageDraw.Draw(sheet).rectangle([x - 6, 10, x + t.width + 5, H + 21], outline=(242, 68, 90), width=5)
        x += t.width + 16
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    for k, v in res.items():
        print(f"{k} {'ok' if v else 'WRONG'}")
    print("sheet", out, "— read it: the new cover (red) must sit in the row; a different title, plate and tag than the 4 beside it")
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
