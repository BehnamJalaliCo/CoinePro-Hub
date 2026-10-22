"""From the owner's logo to a two-layer vector mark (prompt 9.1 §2, contract
§18.14): code only, no model. Runs in a child process with hard limits
(hq_common.untrusted, no network), started by the worker's brand_trace.

1. Input: PNG (best, with transparency), WebP or JPEG, at most 4096 x 4096
   px; Pillow's decompression-bomb guard refuses a larger header before a
   pixel is decoded.
2. Background: the transparent pixels; with no alpha, the colour of the four
   corners when they agree (CIE Delta E 1976 <= 5) and the border is mostly
   that colour; otherwise `no_background`. (Background, foreground and edge
   decisions are CIELAB distances: OKLab's cube root makes near-black noise
   look far; the colours themselves are quantised in OKLab.)
3. Trim to the content with 4% padding, then work at 1024 px on the long side.
4. Colours: the foreground quantised in OKLab (weighted k-means over binned
   colours, deterministic); anti-aliased pixels (alpha < 0.5, colour edges)
   do not vote. The largest low-chroma cluster is `ink`, the others `accent`
   layers; one colour -> one ink layer and no accent.
5. Each layer traced by VTracer (binary, spline); `detail` 1..5 sets the
   speckle filter and the corner threshold. Subpaths are kept in one `d`
   per layer and drawn even-odd. Coordinates: 2 decimals in a shared vb.
6. All d <= 48 KB, else detail is lowered down to 1, else `too_complex`.
7. Our own paths only: every d is re-checked against the SVG path grammar.
8. Checks: the trace rasterised again by resvg and compared with the mask at
   256 px (`iou`), the thinnest feature at 16 px, the palette (<= 6 by area).

Measured (python 3.12, Pillow 13, numpy 2.5, vtracer 0.6, resvg 0.48):
see docs/ops/reports/PROMPT_09_1.md for the peak memory of a 4096 px PNG.
"""

from __future__ import annotations

import io
import math
import re
import warnings
from typing import Any

from hq_api import brand as B

MAX_SIDE = 4096
MIN_SIDE = 16
WORK = 1024  # the long side everything is traced at
RASTER = 256  # the checks' raster (long side)
PAD = 0.04
BG_DE = 5.0  # four corners agree: CIE Delta E 1976 <= 5
BORDER_DE = 10.0
BORDER_SHARE = 0.6  # this much of the border must be the background colour
FG_DE = 10.0  # a pixel this far from the background is foreground
VOTE_DE = 15.0  # ... and this far votes for the colours
EDGE_DE = 8.0  # a pixel whose neighbour differs this much is an edge: no vote
LOW_CHROMA = 0.08
MERGE_DE = 0.07  # clusters closer than this are one colour (auto)
SAME_DE = 0.02  # ... when the owner chose the count: only identical ones
MIN_SHARE = 0.01
MAX_LAYER_COLOURS = 4
MAX_PALETTE = 6
IOU_WARN = 0.9
# detail -> VTracer (filter_speckle px, corner_threshold deg, length_threshold, splice_threshold)
DETAIL = {
    1: (24, 120, 10.0, 60),
    2: (16, 90, 8.0, 50),
    3: (10, 60, 6.0, 45),
    4: (6, 45, 4.5, 45),
    5: (3, 30, 3.5, 40),
}
MAX_FEATURE_R = 24


class Refused(ValueError):
    """The logo cannot become a mark; str() is the status_reason."""


# ----------------------------------------------------------------- colour --
def _oklab(rgb: Any) -> Any:
    import numpy as np

    c = rgb.astype(np.float32) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m1 = np.array(
        [[0.4122214708, 0.5363325363, 0.0514459929],
         [0.2119034982, 0.6806995451, 0.1073969566],
         [0.0883024619, 0.2817188376, 0.6299787005]], dtype=np.float32)  # fmt: skip
    m2 = np.array(
        [[0.2104542553, 0.7936177850, -0.0040720468],
         [1.9779984951, -2.4285922050, 0.4505937099],
         [0.0259040371, 0.7827717662, -0.8086757660]], dtype=np.float32)  # fmt: skip
    lms = np.cbrt(lin @ m1.T)
    out = lms @ m2.T
    return out.astype(np.float32)


def _cielab(rgb: Any) -> Any:
    """sRGB -> CIELAB (D65), for Delta E 1976."""
    import numpy as np

    c = rgb.astype(np.float32) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [[0.4124564 / 0.95047, 0.3575761 / 0.95047, 0.1804375 / 0.95047],
         [0.2126729, 0.7151522, 0.0721750],
         [0.0193339 / 1.08883, 0.1191920 / 1.08883, 0.9503041 / 1.08883]], dtype=np.float32)  # fmt: skip
    t = lin @ m.T
    d = 6 / 29
    f = np.where(t > d**3, np.cbrt(t), t / (3 * d * d) + 4 / 29)
    out = np.empty_like(f)
    out[..., 0] = 116 * f[..., 1] - 16
    out[..., 1] = 500 * (f[..., 0] - f[..., 1])
    out[..., 2] = 200 * (f[..., 1] - f[..., 2])
    return out


def _hex(lab: Any) -> str:
    L, a, b = (float(v) for v in lab)
    lin = B._lab_to_linear((L, a, b))
    return B.hex_of(*(255 * B._gamma(max(0.0, min(1.0, v))) for v in lin))


# ------------------------------------------------------------------ input --
def _open(path: str) -> Any:
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_SIDE * MAX_SIDE  # over twice that: refused unread
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(path)
            if img.format not in ("PNG", "WEBP", "JPEG"):
                raise Refused("unsupported")
            w, h = img.size
            if max(w, h) > MAX_SIDE:
                raise Refused("too_large")
            if min(w, h) < MIN_SIDE:
                raise Refused("too_small")
            if img.format == "JPEG":
                img.draft("RGB", (WORK * 2, WORK * 2))  # decodes at 1/2..1/8 when that is enough
            img.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise Refused("too_large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, EOFError) as exc:
        raise Refused("unreadable") from exc
    return img


def _rgba(img: Any) -> Any:
    import numpy as np
    from PIL import Image

    if img.mode.startswith("I") or img.mode == "F":
        a = np.asarray(img, dtype=np.float64)
        top = float(a.max()) if a.size else 0.0
        scale = 255.0 / 65535.0 if top > 255 else 1.0
        img = Image.fromarray(np.clip(a * scale, 0, 255).astype(np.uint8), "L")
    return img if img.mode == "RGBA" else img.convert("RGBA")


def _shift_max(lab: Any) -> Any:
    """For each pixel, the largest distance to one of its 8 neighbours."""
    import numpy as np

    h, w, _ = lab.shape
    p = np.pad(lab, ((1, 1), (1, 1), (0, 0)), mode="edge")
    out = np.zeros((h, w), dtype=np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            nb = p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
            np.maximum(out, np.linalg.norm(nb - lab, axis=2), out=out)
    return out


def _background(lab: Any) -> Any:  # CIELAB
    """The background of an opaque logo: the four corners' colour when they
    agree and most of the border has it; else Refused('no_background')."""
    import numpy as np

    h, w, _ = lab.shape
    s = max(2, round(0.01 * min(h, w)))
    corners = [lab[:s, :s], lab[:s, -s:], lab[-s:, :s], lab[-s:, -s:]]
    meds = [np.median(c.reshape(-1, 3), axis=0) for c in corners]
    for i in range(4):
        for j in range(i + 1, 4):
            if float(np.linalg.norm(meds[i] - meds[j])) > BG_DE:
                raise Refused("no_background")
    bg = np.mean(meds, axis=0).astype(np.float32)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    share = float(np.mean(np.linalg.norm(border - bg, axis=1) <= BORDER_DE))
    if share < BORDER_SHARE:
        raise Refused("no_background")
    return bg


def _denoise(mask: Any) -> Any:
    """Drops single stray pixels (a JPEG's noise) from a mask: a pixel stays
    when at least 3 of its 8 neighbours are set too."""
    import numpy as np

    h, w = mask.shape
    p = np.pad(mask.astype(np.uint8), 1)
    n = sum(
        p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
        if dy or dx
    )
    return mask & (n >= 3)


def _prepare(path: str) -> dict[str, Any]:
    """Decoded, background found, trimmed with 4% padding, at WORK px. The
    full-size image stays in its own mode (RGB, L ...) until the crop, so an
    opaque logo never costs a full-size RGBA copy."""
    import numpy as np
    from PIL import Image

    img = _open(path)
    if img.mode.startswith("I") or img.mode == "F":
        img = _rgba(img)
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        img = img if img.mode == "RGBA" else img.convert("RGBA")
        alpha_lo, _ = img.getextrema()[3]
        has_alpha = alpha_lo < 250
    else:
        has_alpha = False
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    width, height = img.size
    k = max(1, math.ceil(max(width, height) / WORK))
    prev = (img.reduce(k) if k > 1 else img).convert("RGBA")
    P = np.asarray(prev)
    bg_lab = None
    bg_cie = None
    bg_rgba: tuple[int, ...] = (0, 0, 0, 0)
    if has_alpha:
        fg = P[..., 3] >= 128
    else:
        cie = _cielab(P[..., :3])
        bg_cie = _background(cie)
        fg = _denoise(np.linalg.norm(cie - bg_cie, axis=2) > FG_DE)
        rgb = np.median(
            np.concatenate([P[:2, :2, :3].reshape(-1, 3), P[-2:, -2:, :3].reshape(-1, 3)]), axis=0
        )
        bg_rgba = (*(int(v) for v in rgb), 255)
        bg_lab = _oklab(np.array(bg_rgba[:3], dtype=np.uint8)[None, :])[0]
        del cie
    if not fg.any():
        raise Refused("empty")
    ys, xs = np.nonzero(fg)
    x0, x1 = int(xs.min()) * k, min(width, (int(xs.max()) + 1) * k)
    y0, y1 = int(ys.min()) * k, min(height, (int(ys.max()) + 1) * k)
    del P, prev, fg
    pad = max(1, round(PAD * max(x1 - x0, y1 - y0)))
    cw, ch = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    scale = WORK / max(cw, ch)
    size = (max(1, round(cw * scale)), max(1, round(ch * scale)))
    inner = (max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale)))
    resample = Image.Resampling.LANCZOS if scale < 1 else Image.Resampling.BICUBIC
    # Resized straight from the content box: no full-size crop or canvas.
    content = img.resize(inner, resample, box=(x0, y0, x1, y1))
    del img
    if content.mode != "RGBA":
        content = content.convert("RGBA")
    work = Image.new("RGBA", size, bg_rgba)
    work.paste(content, (round(pad * scale), round(pad * scale)))
    del content
    return {"work": work, "has_alpha": has_alpha, "bg": bg_lab, "bg_cie": bg_cie,
            "width": width, "height": height}  # fmt: skip


# ------------------------------------------------------------- clustering --
def _bins(lab: Any) -> tuple[Any, Any]:
    """Voters' colours binned (L by 1/64, a and b by 1/128): (mean colour per
    bin, count per bin)."""
    import numpy as np

    q = np.empty((lab.shape[0], 3), dtype=np.int64)
    q[:, 0] = np.clip(np.round(lab[:, 0] * 64), 0, 64)
    q[:, 1] = np.clip(np.round(lab[:, 1] * 128) + 64, 0, 128)
    q[:, 2] = np.clip(np.round(lab[:, 2] * 128) + 64, 0, 128)
    key = (q[:, 0] * 129 + q[:, 1]) * 129 + q[:, 2]
    uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    means = np.zeros((len(uniq), 3), dtype=np.float64)
    for c in range(3):
        means[:, c] = np.bincount(inv, weights=lab[:, c], minlength=len(uniq)) / counts
    return means, counts.astype(np.float64)


def _kmeans(x: Any, wts: Any, k: int, merge: float, min_share: float) -> tuple[Any, Any]:
    """Weighted k-means, deterministic (farthest-first from the heaviest bin),
    then clusters closer than `merge` joined and ones under `min_share`
    dropped -> (centres, shares), largest first."""
    import numpy as np

    k = max(1, min(k, len(x)))
    centres = [x[int(np.argmax(wts))]]
    while len(centres) < k:
        d2 = np.min(np.stack([np.sum((x - c) ** 2, axis=1) for c in centres]), axis=0)
        score = wts * d2
        if float(score.max()) <= 0:
            break
        centres.append(x[int(np.argmax(score))])
    c = np.array(centres)

    def lloyd(c: Any) -> tuple[Any, Any]:
        for _ in range(30):
            lab = np.argmin(np.stack([np.sum((x - ci) ** 2, axis=1) for ci in c]), axis=0)
            new = np.array(
                [np.average(x[lab == i], axis=0, weights=wts[lab == i]) if np.any(lab == i) else c[i]
                 for i in range(len(c))]
            )  # fmt: skip
            if np.allclose(new, c, atol=1e-5):
                c = new
                break
            c = new
        lab = np.argmin(np.stack([np.sum((x - ci) ** 2, axis=1) for ci in c]), axis=0)
        share = np.array([wts[lab == i].sum() for i in range(len(c))]) / wts.sum()
        return c, share

    c, share = lloyd(c)
    while True:
        keep = share >= min_share
        if not keep.all() and keep.any():
            c, share = lloyd(c[keep])
            continue
        if len(c) < 2:
            break
        dist = np.linalg.norm(c[:, None, :] - c[None, :, :], axis=2)
        np.fill_diagonal(dist, np.inf)
        i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
        if dist[i, j] >= merge:
            break
        joined = (c[i] * share[i] + c[j] * share[j]) / (share[i] + share[j])
        rest = [c[t] for t in range(len(c)) if t not in (i, j)]
        c, share = lloyd(np.array([joined, *rest]))
    order = np.argsort(-share)
    return c[order], share[order]


def _assign(lab: Any, centres: Any) -> Any:
    import numpy as np

    return np.argmin(np.stack([np.linalg.norm(lab - c, axis=-1) for c in centres]), axis=0)


# ------------------------------------------------------------------ trace --
_PATH_TAG = re.compile(r"<path\s([^>]*?)/>")
_D = re.compile(r'\bd="([^"]*)"')
_TRANSLATE = re.compile(r'transform="translate\(([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\)"')
_TOK = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_PAIRS = {"M": 2, "L": 2, "T": 2, "C": 6, "S": 4, "Q": 4}


def _absolute(svg: str) -> str:
    """VTracer's paths (absolute M/L/C/Q/Z, each with a translate) as one d
    of our own: translated, 2 decimals, commands and numbers only."""
    out: list[str] = []
    for tag in _PATH_TAG.finditer(svg):
        attrs = tag.group(1)
        dm = _D.search(attrs)
        if dm is None:
            continue
        tm = _TRANSLATE.search(attrs)
        tx, ty = (float(tm.group(1)), float(tm.group(2))) if tm else (0.0, 0.0)
        cmd = ""
        nums: list[float] = []
        for tok in _TOK.findall(dm.group(1)):
            if tok.isalpha():
                _put(out, cmd, nums, tx, ty)
                if tok not in ("M", "L", "C", "Q", "S", "T", "H", "V", "Z"):
                    raise ValueError(f"unexpected command {tok}")
                cmd, nums = tok, []
            else:
                nums.append(float(tok))
        _put(out, cmd, nums, tx, ty)
    return "".join(out)


def _put(out: list[str], cmd: str, nums: list[float], tx: float, ty: float) -> None:
    """One absolute command, translated, its numbers with 2 decimals."""
    if not cmd:
        return
    if cmd == "Z":
        out.append("Z")
        return
    n = _PAIRS.get(cmd, 1)
    if not nums or len(nums) % n:
        raise ValueError(f"unexpected arguments for {cmd}")
    vals = []
    for i, v in enumerate(nums):
        if cmd == "H":
            vals.append(B.fmt(v + tx))
        elif cmd == "V":
            vals.append(B.fmt(v + ty))
        else:
            vals.append(B.fmt(v + (tx if i % 2 == 0 else ty)))
    out.append(cmd + " ".join(vals))


def _trace(mask: Any, detail: int) -> str:
    import numpy as np
    import vtracer  # type: ignore[import-untyped]
    from PIL import Image

    speckle, corner, length, splice = DETAIL[detail]
    buf = io.BytesIO()
    Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L").save(
        buf, format="PNG", compress_level=1
    )
    svg = vtracer.convert_raw_image_to_svg(
        buf.getvalue(),
        img_format="png",
        colormode="binary",
        mode="spline",
        filter_speckle=speckle,
        corner_threshold=corner,
        length_threshold=length,
        splice_threshold=splice,
        max_iterations=10,
        path_precision=3,
    )
    return _absolute(svg)


# ----------------------------------------------------------------- checks --
def raster(vb: str, layers: list[dict[str, Any]], long_side: int = RASTER) -> list[Any]:
    """Each layer rasterised by resvg (even-odd), as boolean masks."""
    import numpy as np
    import resvg_py
    from PIL import Image

    _, _, vw, vh = (float(v) for v in vb.split())
    w = max(1, round(long_side * vw / max(vw, vh)))
    h = max(1, round(long_side * vh / max(vw, vh)))
    out = []
    for layer in layers:
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{vb}">'
            f'<path fill="#000000" fill-rule="evenodd" d="{layer["d"]}"/></svg>'
        )
        png = bytes(resvg_py.svg_to_bytes(svg_string=svg, skip_system_fonts=True))
        a = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))[..., 3]
        out.append(a >= 128)
    return out


def _down(mask: Any, size: tuple[int, int]) -> Any:
    import numpy as np
    from PIL import Image

    img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    return np.asarray(img.resize(size, Image.Resampling.BOX)) >= 128


def iou(traced: list[Any], wanted: list[Any]) -> float:
    """Pooled over the layers: sum |A n B| / sum |A u B|."""
    import numpy as np

    inter = sum(int(np.sum(a & b)) for a, b in zip(traced, wanted, strict=True))
    union = sum(int(np.sum(a | b)) for a, b in zip(traced, wanted, strict=True))
    return round(inter / union, 3) if union else 0.0


def _step(m: Any, op: Any, cross: bool) -> Any:
    import numpy as np

    h, w = m.shape
    p = np.pad(m, 1, constant_values=op is np.logical_or)
    out = p[1 : 1 + h, 1 : 1 + w].copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)) + (
        () if cross else ((-1, -1), (-1, 1), (1, -1), (1, 1))
    ):
        out = op(out, p[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w])
    return out


def _largest_blob(m: Any) -> int:
    """Size of the largest 4-connected region (min-label propagation)."""
    import numpy as np

    if not m.any():
        return 0
    h, w = m.shape
    big = h * w + 1
    lab = np.where(m, np.arange(h * w).reshape(h, w), big)
    for _ in range(4 * (h + w)):
        p = np.pad(lab, 1, constant_values=big)
        nb = np.minimum.reduce(
            [p[1:-1, 1:-1], p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]]
        )
        nb = np.where(m, nb, big)
        if np.array_equal(nb, lab):
            break
        lab = nb
    _, counts = np.unique(lab[m], return_counts=True)
    return int(counts.max())


def _thinnest(mask: Any, limit: int = MAX_FEATURE_R) -> int:
    """Width (px) of the thinnest part: the first octagonal opening of
    radius r that removes a region at least (2r+1)^2 large says a part is
    thinner than 2r+1."""
    import numpy as np

    eroded = mask
    for r in range(1, limit + 1):
        eroded = _step(eroded, np.logical_and, cross=r % 2 == 0)
        opened = eroded
        for i in range(r):
            opened = _step(opened, np.logical_or, cross=(i + 1) % 2 == 0)
        removed = mask & ~opened
        k = 2 * r + 1
        if int(removed.sum()) >= k * k and _largest_blob(removed) >= k * k:
            return 2 * r - 1
    return 2 * limit + 1


def min_feature_px_16(union: Any) -> float:
    """The thinnest part (ink, or a gap between inks) at 16 px on the long side."""
    import numpy as np

    h, w = union.shape
    ink = _thinnest(union)
    # The outside is padded wide, so only a real gap between inks is thin.
    framed = np.pad(~union, 2 * MAX_FEATURE_R + 2, constant_values=True)
    gap = _thinnest(framed)
    px = min(ink, gap) * 16 / max(h, w)
    return round(float(px), 2)


def shape_checks(shape: dict[str, Any]) -> dict[str, Any]:
    """The rasterised mark's thinnest feature and its area per colour (for a
    seed: the design files are the source, so iou is 1)."""
    import numpy as np

    masks = raster(shape["vb"], shape["layers"])
    union = np.logical_or.reduce(masks)
    painted: dict[str, int] = {}
    seen = np.zeros_like(union)
    for layer, m in reversed(list(zip(shape["layers"], masks, strict=True))):
        own = m & ~seen
        painted[layer["color"]] = painted.get(layer["color"], 0) + int(own.sum())
        seen |= m
    total = sum(painted.values()) or 1
    palette = [
        {"hex": hx, "share": round(n / total, 3)}
        for hx, n in sorted(painted.items(), key=lambda kv: -kv[1])
        if n
    ][:MAX_PALETTE]
    return {"min_feature_px_16": min_feature_px_16(union), "palette": palette}


# -------------------------------------------------------------------- job --
def trace_job(
    path: str, colors: int | None = None, detail: int = 3, extra_bytes: int = 0
) -> dict[str, Any]:
    """In the child: one logo file -> one traced shape with its colours,
    palette and checks. Refused(reason) when it cannot be a mark."""
    import numpy as np

    prep = _prepare(path)
    A = np.asarray(prep["work"])
    del prep["work"]
    h, w = A.shape[:2]
    lab = _oklab(A[..., :3])
    cie = _cielab(A[..., :3])
    if prep["has_alpha"]:
        alpha = A[..., 3]
        fg = alpha >= 128
        solid = fg & ~_step(~fg, np.logical_or, cross=False)  # not next to transparency
        vote = solid
    else:
        dist_bg = np.linalg.norm(cie - prep["bg_cie"], axis=2)
        fg = _denoise(dist_bg > FG_DE)
        vote = fg & (dist_bg > VOTE_DE)
        del dist_bg
    del A
    edges = _shift_max(cie) > EDGE_DE
    del cie
    voters = vote & ~edges
    if int(voters.sum()) < max(50, int(0.01 * fg.sum())):
        voters = vote if vote.any() else fg
    if not voters.any():
        raise Refused("empty")
    means, counts = _bins(lab[voters])
    auto = colors is None
    centres, _share = _kmeans(
        means, counts, MAX_LAYER_COLOURS if colors is None else colors, MERGE_DE if auto else SAME_DE,
        MIN_SHARE if auto else 0.0,
    )  # fmt: skip
    palette_c, _ = _kmeans(means, counts, MAX_PALETTE, MERGE_DE, 0.005)
    # Roles: the largest low-chroma cluster is the body; without one, the least colourful.
    chroma = np.hypot(centres[:, 1], centres[:, 2])
    low = [i for i in range(len(centres)) if chroma[i] < LOW_CHROMA]
    ink_i = low[0] if low else int(np.argmin(chroma))
    # Every foreground pixel goes to its nearest colour (or, opaque, to the background).
    if prep["has_alpha"]:
        label = np.where(fg, _assign(lab, centres), -1)
    else:
        near = _assign(lab, np.vstack([prep["bg"][None, :], centres])) - 1
        label = np.where(fg, near, -1)
        fg = label >= 0
    pal_label = _assign(lab[fg], palette_c)
    pal_share = np.bincount(pal_label, minlength=len(palette_c)) / max(1, int(fg.sum()))
    del lab
    if len(centres) == 1 or colors == 1:
        groups = [("ink", _hex(centres[ink_i]), fg)]
    else:
        order = [ink_i] + [i for i in range(len(centres)) if i != ink_i]
        groups = [("ink" if i == ink_i else "accent", _hex(centres[i]), label == i) for i in order]
    want = int(detail)
    lowered = False
    layers: list[dict[str, Any]] = []
    masks: list[Any] = []
    for det in range(want, 0, -1):
        layers, masks = [], []
        for role, colour, m in groups:
            d = _trace(m, det) if m.any() else ""
            if d:
                layers.append({"role": role, "color": colour, "d": d})
                masks.append(m)
        total = sum(len(x["d"].encode()) for x in layers) + int(extra_bytes)
        if layers and total <= B.PATHS_BUDGET:
            break
        lowered = True
    else:
        raise Refused("too_complex" if layers else "empty")
    if not any(x["role"] == "ink" for x in layers):
        layers[0]["role"] = "ink"  # the body was filtered away: the first colour is the body
    vb = f"0 0 {w} {h}"
    shape = {"vb": vb, "layers": layers}
    if not B.shape_ok(shape):
        raise Refused("invalid_path")
    traced = raster(vb, layers)
    size = (traced[0].shape[1], traced[0].shape[0])
    wanted = [_down(m, size) for m in masks]
    score = iou(traced, wanted)
    union = np.logical_or.reduce(traced)
    small = min_feature_px_16(union)
    warn = []
    if not prep["has_alpha"]:
        warn.append(B.WARN_NO_ALPHA)
    if lowered:
        warn.append(f"لوگو پیچیده بود؛ جزئیات خودکار تا {det} پایین آمد")
    if score < IOU_WARN:
        warn.append(B.WARN_IOU)
    if small < 1:
        warn.append(B.WARN_SMALL)
    ink = next(x["color"] for x in layers if x["role"] == "ink")
    accent = next((x["color"] for x in layers if x["role"] == "accent"), None)
    palette: list[dict[str, Any]] = []
    for i in np.argsort(-pal_share):
        if pal_share[i] > 0 and len(palette) < MAX_PALETTE:
            palette.append({"hex": _hex(palette_c[i]), "share": round(float(pal_share[i]), 3)})
    return {
        "shape": shape,
        "ink": ink,
        "accent": accent,
        "palette": palette,
        "options": {"colors": len({x["color"] for x in layers}), "detail": det},
        "checks": {
            "paths_bytes": B.paths_bytes(shape),
            "min_feature_px_16": small,
            "iou": score,
            "warnings": warn,
        },
        "has_alpha": prep["has_alpha"],
        "width": prep["width"],
        "height": prep["height"],
    }
