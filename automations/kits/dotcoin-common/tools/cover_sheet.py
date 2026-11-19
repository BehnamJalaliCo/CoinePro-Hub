# -*- coding: utf-8 -*-
"""The DotCoin cover's row check (the owner, 2026-11-19: every reel cover is ONE family; COVER_SYSTEM.md
«ONE FAMILY», rule 3): the new cover beside the page's last 4 covers in one contact sheet, plus a ground
check. Read the sheet before delivering: the new cover must sit in that row.

usage: PY -I COMMON/tools/cover_sheet.py NEW_COVER out.jpg [--family DIR] [--n 4]
  NEW_COVER  the candidate (ChatGPT's picture or out/cover.jpg)
  out.jpg    the sheet: the last N covers of DIR (default COMMON/cover/family/, newest last, the files
             named YYYY-MM-DD_<ref>.jpg; workshop only), then the new one, framed in red
prints:
  ground ok | ground WRONG   the median colour of the cover's outer frame against the family's mustard
                             (a black or any other ground is WRONG: never deliver it)
  bottom: N% not ground      the bottom 5 % of the frame: about the arrow alone when the bottom is
                             clean mustard; his legs and shoes when he stands full length. Legs cut by
                             the pill are a FAIL whatever this number says: look at the sheet.
exit code 1 when the ground is wrong.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent / "cover" / "family"
MUSTARD = np.array([252, 192, 47])  # the family's ground as ChatGPT draws #F3C242 (P-000077, P-000108)
H = 800


def arg(k, d):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def frame_median(a: np.ndarray) -> np.ndarray:
    h, w, _ = a.shape
    b = max(4, round(min(h, w) * 0.02))
    ring = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3),
                           a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    return np.median(ring, 0)


def main() -> int:
    new, out = Path(sys.argv[1]), Path(sys.argv[2])
    fam = Path(arg("--family", str(FAMILY)))
    n = int(arg("--n", "4"))
    last = sorted(p for p in fam.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))[-n:]
    im = Image.open(new).convert("RGB")
    a = np.asarray(im).astype(int)
    ref = MUSTARD
    if last:
        ref = np.median([frame_median(np.asarray(Image.open(p).convert("RGB")).astype(int)) for p in last], 0)
    med = frame_median(a)
    dist = float(np.abs(med - ref).sum())
    ok = dist <= 60
    h = a.shape[0]
    strip = a[int(h * 0.95):]
    off = np.abs(strip - ref).sum(2) > 90
    tiles = []
    for p in last + [new]:
        t = Image.open(p).convert("RGB")
        t = t.resize((round(t.width * H / t.height), H), Image.LANCZOS)
        tiles.append(t)
    gap = 14
    sheet = Image.new("RGB", (sum(t.width for t in tiles) + gap * (len(tiles) + 1), H + 2 * gap), (110, 110, 110))
    x = gap
    for i, t in enumerate(tiles):
        sheet.paste(t, (x, gap))
        if i == len(tiles) - 1:
            ImageDraw.Draw(sheet).rectangle([x - 6, gap - 6, x + t.width + 5, gap + H + 5], outline=(230, 30, 30), width=5)
        x += t.width + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    print(f"row: {', '.join(p.name for p in last) or '(no family covers found)'} + {new.name} -> {out}")
    print(f"ground {'ok' if ok else 'WRONG'}: frame median {med.astype(int).tolist()} vs the family's "
          f"{np.asarray(ref).astype(int).tolist()} (distance {dist:.0f}, at most 60)")
    print(f"bottom: {off.mean() * 100:.1f}% not ground (clean mustard ≈ the arrow alone; never legs cut by the pill)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
