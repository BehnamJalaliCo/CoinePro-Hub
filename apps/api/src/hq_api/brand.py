"""The company's brand as data (prompt 9.1, contract §18.14): the light half.

What every process needs, in plain Python (no numpy, no image library):
- the SVG path grammar check: a `d` is stored only when it is commands and
  numbers that read as an SVG path; nothing else of any markup survives;
- the digest the owner's seal is bound to (sha256 of the canonical JSON of
  mark, wordmark, ink, accent, accent_night, accent_day);
- colour: sRGB <-> OKLab/OKLCH, the WCAG contrast ratio, and the nearest
  OKLCH lightness (hue and chroma kept) that passes 3:1 on a theme's page;
- the flat design SVGs of design/brand/companies/<code>/ read the way
  apps/web/scripts/gen-assets.mjs reads them (layers by --logo-ink and
  --logo-accent), for the seed.
The tracing itself (Pillow, numpy, VTracer, resvg) is hq_api.brand_trace and
runs only in a child process with hard limits (hq_common.untrusted).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

# The page surfaces of both themes (design/tokens/divan.tokens.json,
# divan.color.primitive.{night,day}.page); a test keeps them equal.
PAGE = {"night": "#0B0D14", "day": "#F3EEE3"}
MIN_CONTRAST = 3.0
PATHS_BUDGET = 48 * 1024  # every d of a version together (bytes)
MAX_D_BYTES = PATHS_BUDGET
OPTIONS_DEFAULT_DETAIL = 3
REASONS = (
    "no_background",
    "too_complex",
    "too_large",
    "too_small",
    "unreadable",
    "unsupported",
    "empty",
    "invalid_path",
    "stopped",
)
WARN_NO_ALPHA = "بدون شفافیت"
WARN_SMALL = "در اندازه‌ی کوچک جزئیات گم میشود"
WARN_IOU = "نشان ساخته‌شده با لوگوی اصلی کاملاً یکی نیست؛ جزئیات بیشتر را امتحان کن"
WARN_NIGHT = "رنگ امضا روی زمینه‌ی شب کم‌کنتراست بود؛ برای شب روشن‌تر شد"
WARN_DAY = "رنگ امضا روی زمینه‌ی روز کم‌کنتراست بود؛ برای روز تیره‌تر شد"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_VB = re.compile(r"^-?\d+(\.\d+)? -?\d+(\.\d+)? \d+(\.\d+)? \d+(\.\d+)?$")


# ------------------------------------------------------------------ paths --
_ARGS = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_WSP = " \t\n\r\f"


def path_ok(d: Any, max_bytes: int = MAX_D_BYTES) -> bool:
    """True when `d` is an SVG path: only commands and numbers, the right
    count of numbers after each command, a moveto first (SVG 1.1 path
    grammar; arc flags must be 0 or 1). Anything else is refused."""
    if not isinstance(d, str) or not d.strip() or len(d.encode()) > max_bytes:
        return False
    i, n = 0, len(d)
    cmd: str | None = None
    args = 0
    first = True

    def done(c: str | None, k: int) -> bool:
        if c is None:
            return True
        want = _ARGS[c.upper()]
        return k == 0 if want == 0 else (k > 0 and k % want == 0)

    while i < n:
        ch = d[i]
        if ch in _WSP:
            i += 1
            continue
        if ch.upper() in _ARGS and ch.isalpha():
            if not done(cmd, args):
                return False
            if first and ch not in "Mm":
                return False
            first = False
            cmd, args = ch, 0
            i += 1
            continue
        if cmd is None:
            return False
        if ch == ",":
            if args == 0:
                return False  # a comma only separates numbers
            i += 1
            while i < n and d[i] in _WSP:
                i += 1
            if i >= n or not (d[i].isdigit() or d[i] in "+-."):
                return False
            continue
        m = _NUMBER.match(d, i)
        if m is None:
            return False
        want = _ARGS[cmd.upper()]
        if want == 0:
            return False  # Z takes no numbers
        if cmd.upper() == "A" and args % 7 in (3, 4) and m.group() not in ("0", "1"):
            return False
        args += 1
        i = m.end()
    return cmd is not None and done(cmd, args)


def fmt(x: float) -> str:
    """A coordinate with at most two decimals, no trailing zeros."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def shape_ok(shape: Any) -> bool:
    """A mark or wordmark as the clients draw it: {vb, layers: [{role, color, d}]}."""
    if not isinstance(shape, dict) or set(shape) != {"vb", "layers"}:
        return False
    if not isinstance(shape["vb"], str) or not _VB.match(shape["vb"]):
        return False
    layers = shape["layers"]
    if not isinstance(layers, list) or not 1 <= len(layers) <= 16:
        return False
    for layer in layers:
        if not isinstance(layer, dict) or set(layer) != {"role", "color", "d"}:
            return False
        if layer["role"] not in ("ink", "accent") or not hex_ok(layer["color"]):
            return False
        if not path_ok(layer["d"]):
            return False
    return True


def paths_bytes(*shapes: dict[str, Any] | None) -> int:
    return sum(len(layer["d"].encode()) for s in shapes if s for layer in s["layers"])


# ----------------------------------------------------------------- digest --
DIGEST_FIELDS = ("mark", "wordmark", "ink", "accent", "accent_night", "accent_day")


def canonical(brand: dict[str, Any]) -> bytes:
    body = {k: brand.get(k) for k in DIGEST_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(brand: dict[str, Any]) -> str:
    """What the owner's seal is bound to; the server always recomputes it."""
    return hashlib.sha256(canonical(brand)).hexdigest()


# ----------------------------------------------------------------- colour --
def hex_ok(v: Any) -> bool:
    return isinstance(v, str) and bool(_HEX.match(v))


def rgb_of(hex_: str) -> tuple[int, int, int]:
    return int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)


def hex_of(r: float, g: float, b: float) -> str:
    def c(v: float) -> int:
        return max(0, min(255, round(v)))

    return f"#{c(r):02X}{c(g):02X}{c(b):02X}"


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055


def oklab(hex_: str) -> tuple[float, float, float]:
    r, g, b = (_lin(v) for v in rgb_of(hex_))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _lab_to_linear(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_**3, m_**3, s_**3
    return (
        4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
        -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
        -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc,
    )


def _in_gamut(lin: tuple[float, float, float], eps: float = 1e-6) -> bool:
    return all(-eps <= v <= 1 + eps for v in lin)


def lch_to_hex(L: float, C: float, h: float) -> str:
    """OKLCH -> sRGB hex; out of gamut, the chroma is lowered (hue and
    lightness kept) until it fits."""

    def lin(c: float) -> tuple[float, float, float]:
        return _lab_to_linear((L, c * math.cos(h), c * math.sin(h)))

    got = lin(C)
    if not _in_gamut(got):
        lo, hi = 0.0, C
        for _ in range(30):
            mid = (lo + hi) / 2
            if _in_gamut(lin(mid)):
                lo = mid
            else:
                hi = mid
        got = lin(lo)
    return hex_of(*(255 * _gamma(max(0.0, min(1.0, v))) for v in got))


def oklch(hex_: str) -> tuple[float, float, float]:
    L, a, b = oklab(hex_)
    return L, math.hypot(a, b), math.atan2(b, a)


def luminance(hex_: str) -> float:
    r, g, b = (_lin(v) for v in rgb_of(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    x, y = sorted((luminance(a), luminance(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def passing_accent(accent: str, page: str, minimum: float = MIN_CONTRAST) -> str | None:
    """None when the accent already has `minimum`:1 on the page; else the
    nearest OKLCH lightness (hue and chroma kept, chroma lowered only where
    sRGB cannot hold it) that does."""
    if contrast(accent, page) >= minimum:
        return None
    L, C, h = oklch(accent)
    for i in range(1, 1001):
        for cand_l in (L + i / 1000, L - i / 1000):
            if 0.0 <= cand_l <= 1.0:
                cand = lch_to_hex(cand_l, C, h)
                if contrast(cand, page) >= minimum:
                    return cand
    return "#FFFFFF" if luminance(page) < 0.18 else "#000000"


def theme_accents(accent: str | None) -> dict[str, Any]:
    """accent_night/accent_day (only where 3:1 fails), the two ratios and
    the warnings that go with them."""
    if accent is None:
        return {"accent_night": None, "accent_day": None, "contrast_night": None,
                "contrast_day": None, "warnings": []}  # fmt: skip
    night = passing_accent(accent, PAGE["night"])
    day = passing_accent(accent, PAGE["day"])
    return {
        "accent_night": night,
        "accent_day": day,
        "contrast_night": round(contrast(accent, PAGE["night"]), 2),
        "contrast_day": round(contrast(accent, PAGE["day"]), 2),
        "warnings": ([WARN_NIGHT] if night else []) + ([WARN_DAY] if day else []),
    }


# --------------------------------------------------------- flat seed SVGs --
_ATTR = re.compile(r'([a-zA-Z:-]+)="([^"]*)"')
_FILL = re.compile(r"var\(--logo-(ink|accent),\s*(#[0-9A-Fa-f]{3,8})\)")
MARK_FILE = re.compile(r"-mark-flat\.svg$")
WORDMARK_FILE = re.compile(r"-wordmark[^/]*-flat\.svg$")


def _attrs(s: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _ATTR.finditer(s)}


def _hex6(v: str) -> str:
    v = v.upper()
    if len(v) == 4:  # #RGB
        return "#" + "".join(c * 2 for c in v[1:])
    return v[:7]


def flat_svg(text: str) -> dict[str, Any]:
    """{vb, layers} from a flat design SVG, as gen-assets.mjs reads it: the
    viewBox, then every <path> in order with its role and colour from
    `var(--logo-ink|accent, #hex)` (anything else: ink). Raises ValueError
    when it is not such a file."""
    head = re.search(r"<svg\s([^>]*)>", text)
    if head is None:
        raise ValueError("no <svg> element")
    vb = " ".join(_attrs(head.group(1)).get("viewBox", "").split())
    layers = []
    for m in re.finditer(r"<path\s([^>]*?)/?>", text):
        a = _attrs(m.group(1))
        fill = _FILL.search(a.get("fill", ""))
        layers.append(
            {
                "role": fill.group(1) if fill else "ink",
                "color": _hex6(fill.group(2)) if fill else "#000000",
                "d": a.get("d", ""),
            }
        )
    shape = {"vb": vb, "layers": layers}
    if not shape_ok(shape):
        raise ValueError("not a flat mark (viewBox, layers and paths)")
    return shape


def seed_folder(folder: Path) -> dict[str, Any] | None:
    """One design/brand/companies/<code>/ folder: its mark and wordmark (the
    files gen-assets.mjs picks), or None when it has no flat mark."""
    files = sorted(p.name for p in folder.iterdir() if p.is_file())
    mark = next((f for f in files if MARK_FILE.search(f)), None)
    word = next((f for f in files if WORDMARK_FILE.search(f)), None)
    if mark is None:
        return None
    raw = [(folder / mark).read_bytes()] + ([(folder / word).read_bytes()] if word else [])
    return {
        "mark": flat_svg(raw[0].decode("utf-8")),
        "wordmark": flat_svg(raw[1].decode("utf-8")) if word else None,
        "files": [mark] + ([word] if word else []),
        "sha256": hashlib.sha256(b"".join(raw)).hexdigest(),
    }


def colours_of(shape: dict[str, Any]) -> tuple[str, str | None]:
    """ink and accent of a drawn mark: the first layer of each role."""
    ink = next((x["color"] for x in shape["layers"] if x["role"] == "ink"), None)
    acc = next((x["color"] for x in shape["layers"] if x["role"] == "accent"), None)
    return ink or shape["layers"][0]["color"], acc
