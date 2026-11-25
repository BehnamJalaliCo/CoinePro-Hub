# -*- coding: utf-8 -*-
"""Zarib100x — the cover's row check (cover/COVER_SYSTEM.md «ONE FAMILY»): the new cover beside the page's last
4 covers in one sheet, plus the family's three machine checks. Read the sheet before delivering.

usage: PY -I COMMON/tools/cover_sheet.py NEW_COVER qc/cover_sheet.jpg [--family DIR] [--n 4]
  the row = the newest N of: DIR if given; else the covers earlier Zarib100x sessions kept as qc/z100x_cover.jpg
  (/home/studio/hq-workspace/*/qc/, newest by time, this folder excluded); fewer than N found → the family's
  samples (COMMON/cover/samples/) fill the row. Every session copies its delivered cover to qc/z100x_cover.jpg.
prints, and exits 1 on any WRONG (cover/COVER_SYSTEM.md «ONE FAMILY»):
  ground ok|WRONG    the top corners are the dark wine ground (#160A0E…#461A23), never mint, light or another colour
  arch ok|WRONG      the mint arch (#83CAAD) stands behind him in the upper middle of the frame
  chip ok|WRONG      the mint key-word chip is in the title zone (y ≈ 1280–1700 at 1080×1920)
"""
import glob
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "cover" / "samples"
MINT = np.array([131, 202, 173])
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


def mint_frac(region: np.ndarray) -> float:
    return float((np.abs(region.reshape(-1, 3) - MINT).sum(1) < 75).mean())


def checks(a: np.ndarray) -> dict:
    h, w, _ = a.shape
    sy, sx = h / 1920, w / 1080
    corners = np.concatenate([a[:int(200 * sy), :int(150 * sx)].reshape(-1, 3), a[:int(200 * sy), -int(150 * sx):].reshape(-1, 3)])
    m = np.median(corners, 0)
    ground = float(m.mean()) < 60 and m[0] >= m[1] + 2 and mint_frac(corners) < 0.05
    arch = mint_frac(a[int(380 * sy):int(1100 * sy), int(170 * sx):int(910 * sx)]) > 0.12
    chip = mint_frac(a[int(1280 * sy):int(1700 * sy), int(60 * sx):int(1020 * sx)]) > 0.006
    return {"ground": ground, "arch": arch, "chip": chip}


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
    print("sheet", out, "— read it: the new cover (red) must sit in the row; a different suit, pose, element and title than the 4 beside it")
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
