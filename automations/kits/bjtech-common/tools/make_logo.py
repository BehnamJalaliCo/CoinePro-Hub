#!/usr/bin/env python3
"""The page's ROUND profile logo (COMMON/brand/logo_round.png, 512x512 RGBA), the mark beside every «behnamjalali.tech»
handle (the owner, 2026-11-19): the real Instagram profile picture (COMMON/brand/profile.jpg, IG-Hub account 3's
profile_picture_url) cut to a clean circle, a hair of ink between it and a thin rim in the page's spectral light.
    PY -I COMMON/tools/make_logo.py [profile.jpg] [out.png]
Made again only when the profile picture changes (fetch it through IG-Hub first)."""
import os
import sys

import numpy as np
from PIL import Image

COMMON = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE, SS = 512, 4  # the output, and the supersampling for clean edges
RIM, GAP = 0.034, 0.018  # the rim's and the ink gap's width, of the diameter
SPEC = ["#7B61FF", "#3D8BFF", "#22D3EE", "#3CFFB5", "#FFD166", "#FF5FA2", "#7B61FF"]  # DIRECTION.md's spectrum
INK = (5, 6, 10)


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(COMMON, "brand", "profile.jpg")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(COMMON, "brand", "logo_round.png")
    n = SIZE * SS
    pic = Image.open(src).convert("RGB")
    side = min(pic.size)
    pic = pic.crop(((pic.width - side) // 2, (pic.height - side) // 2, (pic.width + side) // 2, (pic.height + side) // 2))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    r = np.hypot(xx - c, yy - c) / (n / 2)  # 0 at the centre, 1 at the edge
    inner = 1 - 2 * (RIM + GAP)
    photo = np.asarray(pic.resize((round(n * inner), round(n * inner)), Image.LANCZOS), dtype=np.float32)
    img = np.zeros((n, n, 4), dtype=np.float32)
    off = (n - photo.shape[0]) // 2
    img[off:off + photo.shape[0], off:off + photo.shape[1], :3] = photo
    img[..., 3] = (r <= inner).astype(np.float32) * 255
    gap = (r > inner) & (r <= 1 - 2 * RIM)
    img[gap, :3], img[gap, 3] = INK, 255
    # the rim: a conic sweep through the spectrum, starting top right (as the page's edge light)
    ang = (np.degrees(np.arctan2(yy - c, xx - c)) + 90 + 30) % 360 / 360 * (len(SPEC) - 1)
    i0 = np.floor(ang).astype(int)
    f = (ang - i0)[..., None]
    cols = np.stack([rgb(h) for h in SPEC])
    rim = cols[i0] * (1 - f) + cols[np.minimum(i0 + 1, len(SPEC) - 1)] * f
    on = (r > 1 - 2 * RIM) & (r <= 1)
    img[on, :3], img[on, 3] = rim[on], 255
    out_img = Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGBA").resize((SIZE, SIZE), Image.LANCZOS)
    out_img.save(out, optimize=True)
    print(f"ok {out} {SIZE}x{SIZE} {os.path.getsize(out) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
