#!/usr/bin/env python3
"""Model-provider logos for the treasury: design/brand/providers/*.svg -> web TS and Android Kotlin.

Usage: python3 design/brand/providers/gen_logos.py [--check]
(apps/android/scripts/gen_assets.py writes and checks the Kotlin file too, so CI's `gen_assets.py --check` covers it.)

Each logo becomes a list of filled paths on a 24x24 box; a path without its own colour takes the text colour (None).

The web draws the SVG paths as they are, in the browser: a gradient that only overlays a solid base is dropped, a logo made only of a
gradient keeps its first stop colour (unchanged).

Android draws the paths with Compose's path parser, which misreads the compact arc flags of an implicitly repeated arc ("a1 1 0 01-3
-6 1 1 0 01 …"): Gemini's sparkle came out as a broken half-shape. So for Android every path is normalised here: absolute
commands, explicit separators, H/V/S/T expanded and every elliptical arc converted to cubic Béziers (each at most a quarter turn), so
no arc ever reaches the parser. Android also keeps the linear gradients (Gemini's four colours, Qwen's violet), each as its two end
points on the 24x24 box and its stops (offset, ARGB).
"""
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WEB = ROOT / "apps/web/src/generated/provider-logos.ts"
KT = ROOT / "apps/android/app/src/main/java/com/coinepro/hq/designsystem/generated/ProviderLogos.kt"
NS = "{http://www.w3.org/2000/svg}"
# provider key -> (file, title)
LOGOS = {
    "anthropic": ("claude-color.svg", "Claude"),
    "openai": ("openai.svg", "OpenAI"),
    "google": ("gemini-color.svg", "Gemini"),
    "deepseek": ("deepseek-color.svg", "DeepSeek"),
    "zhipu": ("zhipu-color.svg", "GLM"),
    "moonshot": ("kimi-color.svg", "Kimi"),
    "qwen": ("qwen-color.svg", "Qwen"),
    "mistral": ("mistral-color.svg", "Mistral"),
    "xai": ("grok.svg", "Grok"),
    "meta": ("meta.svg", "Llama"),
}
NAMED = {"gold": "#FFD700", "white": "#FFFFFF", "black": "#000000"}


def colour(v: str | None) -> str | None:
    if not v or v == "currentColor" or v == "none":
        return None
    v = NAMED.get(v, v)
    if re.fullmatch(r"#[0-9a-fA-F]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    return v.upper()


# ------------------------------------------------------------------ path data --
NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def tokens(d: str):
    """(command, [numbers]) groups, an implicit repetition split into its own group; arc flags read as single digits."""
    i, n = 0, len(d)
    out = []
    cmd = None

    def skip(i):
        while i < n and d[i] in " \t\r\n,":
            i += 1
        return i

    def number(i):
        m = NUM.match(d, i)
        if not m:
            raise ValueError(f"number expected at {i}: {d[i:i + 20]!r}")
        return float(m.group()), m.end()

    def flag(i):
        if d[i] not in "01":
            raise ValueError(f"flag expected at {i}: {d[i:i + 20]!r}")
        return float(d[i]), i + 1

    while True:
        i = skip(i)
        if i >= n:
            break
        if d[i].isalpha():
            cmd = d[i]
            i += 1
            if cmd in "Zz":
                out.append((cmd, []))
                continue
        elif cmd is None:
            raise ValueError("path must start with a command")
        k = ARGS[cmd.upper()]
        args = []
        for j in range(k):
            i = skip(i)
            if cmd in "Aa" and j in (3, 4):
                v, i = flag(i)
            else:
                v, i = number(i)
            args.append(v)
        out.append((cmd, args))
        # after a moveto, implicit pairs are linetos
        if cmd == "M":
            cmd = "L"
        elif cmd == "m":
            cmd = "l"
    return out


def arc_to_cubics(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """SVG 1.1 F.6.5: an elliptical arc as cubic Béziers, each spanning at most 90 degrees."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x1, y1, x2, y2, x2, y2)]
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = c * dx + s * dy, -s * dx + c * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = c * cxp - s * cyp + (x1 + x2) / 2, s * cxp + c * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    segs = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    step = dt / segs
    k = 4 / 3 * math.tan(step / 4)
    out = []
    t = t1
    px, py = x1, y1

    def point(t):
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        return c * ex - s * ey + cx, s * ex + c * ey + cy

    def deriv(t):
        ex, ey = -rx * math.sin(t), ry * math.cos(t)
        return c * ex - s * ey, s * ex + c * ey

    for i in range(segs):
        t2 = t + step
        ex, ey = point(t2) if i < segs - 1 else (x2, y2)
        d1x, d1y = deriv(t)
        d2x, d2y = deriv(t2)
        out.append((px + k * d1x, py + k * d1y, ex - k * d2x, ey - k * d2y, ex, ey))
        px, py = ex, ey
        t = t2
    return out


def absolute(d: str):
    """The path as absolute M, L, C, Q and Z segments (arcs as cubics)."""
    x = y = sx = sy = 0.0
    last_c = last_q = None
    out = []
    for cmd, a in tokens(d):
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if C == "M":
            x, y = a[0] + ox, a[1] + oy
            sx, sy = x, y
            out.append(("M", [x, y]))
            last_c = last_q = None
        elif C == "L":
            x, y = a[0] + ox, a[1] + oy
            out.append(("L", [x, y]))
            last_c = last_q = None
        elif C == "H":
            x = a[0] + (x if rel else 0.0)
            out.append(("L", [x, y]))
            last_c = last_q = None
        elif C == "V":
            y = a[0] + (y if rel else 0.0)
            out.append(("L", [x, y]))
            last_c = last_q = None
        elif C == "C":
            p = [a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy, a[4] + ox, a[5] + oy]
            out.append(("C", p))
            last_c, last_q = (p[2], p[3]), None
            x, y = p[4], p[5]
        elif C == "S":
            c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
            p = [c1[0], c1[1], a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy]
            out.append(("C", p))
            last_c, last_q = (p[2], p[3]), None
            x, y = p[4], p[5]
        elif C == "Q":
            p = [a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy]
            out.append(("Q", p))
            last_q, last_c = (p[0], p[1]), None
            x, y = p[2], p[3]
        elif C == "T":
            c1 = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
            p = [c1[0], c1[1], a[0] + ox, a[1] + oy]
            out.append(("Q", p))
            last_q, last_c = c1, None
            x, y = p[2], p[3]
        elif C == "A":
            ex, ey = a[5] + ox, a[6] + oy
            for seg in arc_to_cubics(x, y, a[0], a[1], a[2], int(a[3]), int(a[4]), ex, ey):
                out.append(("C", list(seg)))
            x, y = ex, ey
            last_c = last_q = None
        elif C == "Z":
            out.append(("Z", []))
            x, y = sx, sy
            last_c = last_q = None
    return out


def fmt(v: float) -> str:
    s = f"{round(v, 3):.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def normalise(d: str) -> str:
    """Absolute commands, explicit separators, no arcs: what any path parser reads the same."""
    return "".join(c + " ".join(fmt(v) for v in a) for c, a in absolute(d))


def bbox(d: str):
    """The path's bounds, sampled along its curves (a gradient in objectBoundingBox units needs them)."""
    xs, ys = [], []
    px = py = 0.0
    for c, a in absolute(d):
        if c in ("M", "L"):
            px, py = a
            xs.append(px); ys.append(py)
        elif c == "C":
            for i in range(1, 9):
                t = i / 8
                u = 1 - t
                xs.append(u ** 3 * px + 3 * u * u * t * a[0] + 3 * u * t * t * a[2] + t ** 3 * a[4])
                ys.append(u ** 3 * py + 3 * u * u * t * a[1] + 3 * u * t * t * a[3] + t ** 3 * a[5])
            px, py = a[4], a[5]
        elif c == "Q":
            for i in range(1, 9):
                t = i / 8
                u = 1 - t
                xs.append(u * u * px + 2 * u * t * a[0] + t * t * a[2])
                ys.append(u * u * py + 2 * u * t * a[1] + t * t * a[3])
            px, py = a[2], a[3]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------------ the SVGs --
def coord(v: str | None, default: float, lo: float, size: float) -> float:
    if v is None:
        return default
    if v.endswith("%"):
        return lo + float(v[:-1]) / 100 * size
    return float(v)


def parse(file: str) -> dict:
    """The logo as the web keeps it: its solid paths (a gradient overlay dropped, a gradient-only logo flattened)."""
    root = ET.parse(HERE / file).getroot()
    box = root.get("viewBox", "0 0 24 24")
    assert box == "0 0 24 24", (file, box)
    evenodd = root.get("fill-rule") == "evenodd"
    stops = {}
    for g in root.iter():
        if g.tag in (NS + "linearGradient", NS + "radialGradient"):
            first = next((s for s in g if s.tag == NS + "stop"), None)
            stops[g.get("id")] = colour(first.get("stop-color")) if first is not None else None
    paths = []
    for p in root.iter(NS + "path"):
        fill = p.get("fill", root.get("fill"))
        grad = re.fullmatch(r"url\(#(.+)\)", fill or "")
        paths.append({"d": p.get("d"), "fill": stops.get(grad.group(1)) if grad else colour(fill), "gradient": bool(grad)})
    if any(not x["gradient"] for x in paths):
        paths = [x for x in paths if not x["gradient"]]
    return {"evenodd": evenodd, "paths": [{"d": x["d"], "fill": x["fill"]} for x in paths]}


def parse_android(file: str) -> dict:
    """The logo as Android draws it: every path normalised (no arcs), linear gradients kept with their end points on the box."""
    root = ET.parse(HERE / file).getroot()
    evenodd = root.get("fill-rule") == "evenodd"
    grads = {g.get("id"): g for g in root.iter(NS + "linearGradient")}
    flat = {}
    for g in root.iter(NS + "radialGradient"):
        first = next((s for s in g if s.tag == NS + "stop"), None)
        flat[g.get("id")] = colour(first.get("stop-color")) if first is not None else None
    paths = []
    for p in root.iter(NS + "path"):
        d = p.get("d")
        fill = p.get("fill", root.get("fill"))
        ref = re.fullmatch(r"url\(#(.+)\)", fill or "")
        out = {"d": normalise(d), "fill": None, "gradient": None}
        if ref and ref.group(1) in grads:
            g = grads[ref.group(1)]
            assert g.get("gradientTransform") is None, (file, "gradientTransform")
            if g.get("gradientUnits") == "userSpaceOnUse":
                x0, y0, w, h = 0.0, 0.0, 24.0, 24.0
                pts = [coord(g.get("x1"), 0, x0, w), coord(g.get("y1"), 0, y0, h), coord(g.get("x2"), 24, x0, w), coord(g.get("y2"), 0, y0, h)]
            else:  # objectBoundingBox: fractions or percentages of the path's own bounds
                bx0, by0, bx1, by1 = bbox(d)
                w, h = bx1 - bx0, by1 - by0

                def frac(v, default, lo, size):
                    if v is None:
                        return lo + default * size
                    return lo + (float(v[:-1]) / 100 if v.endswith("%") else float(v)) * size

                pts = [frac(g.get("x1"), 0, bx0, w), frac(g.get("y1"), 0, by0, h), frac(g.get("x2"), 1, bx0, w), frac(g.get("y2"), 0, by0, h)]
            stops = []
            for s in g.iter(NS + "stop"):
                off = s.get("offset", "0")
                off = float(off[:-1]) / 100 if off.endswith("%") else float(off)
                rgb = colour(s.get("stop-color")) or "#000000"
                alpha = round(float(s.get("stop-opacity", "1")) * 255)
                stops.append((off, f"0x{alpha:02X}{rgb[1:]}"))
            out["gradient"] = {"pts": pts, "stops": stops}
        elif ref:
            out["fill"] = flat.get(ref.group(1))
        else:
            out["fill"] = colour(fill)
        paths.append(out)
    return {"evenodd": evenodd, "paths": paths}


def web(logos: dict) -> str:
    out = ["// Generated by design/brand/providers/gen_logos.py — do not edit. LobeHub Icons, MIT (see NOTICE.md there).",
           "export type ProviderLogo = { title: string; evenodd: boolean; paths: Array<{ d: string; fill: string | null }> };",
           "export const PROVIDER_LOGOS: Record<string, ProviderLogo> = {"]
    for k, (f, title) in LOGOS.items():
        lg = logos[k]
        ps = ", ".join("{ d: %s, fill: %s }" % (repr(p["d"]).replace("'", '"'), ('"%s"' % p["fill"]) if p["fill"] else "null") for p in lg["paths"])
        out.append(f'  {k}: {{ title: "{title}", evenodd: {"true" if lg["evenodd"] else "false"}, paths: [{ps}] }},')
    out.append("};")
    return "\n".join(out) + "\n"


def kotlin(logos: dict) -> str:
    out = ["package com.coinepro.hq.designsystem.generated", "",
           "// Generated by design/brand/providers/gen_logos.py — do not edit. LobeHub Icons, MIT (see NOTICE.md there).",
           "// Paths are normalised for Compose's parser (absolute commands, arcs as cubics); linear gradients are kept.", "",
           "/** A linear gradient on the 24×24 box, from (x1, y1) to (x2, y2); stops are (offset 0..1, ARGB). */",
           "data class LogoGradient(val x1: Float, val y1: Float, val x2: Float, val y2: Float, val stops: List<Pair<Float, Long>>)", "",
           "/** One filled path on a 24×24 box; `fill` null = the text colour, unless it has a [gradient]. */",
           "data class LogoPath(val d: String, val fill: Long?, val gradient: LogoGradient? = null)", "",
           "data class ProviderLogo(val title: String, val evenOdd: Boolean, val paths: List<LogoPath>)", "",
           "val PROVIDER_LOGOS: Map<String, ProviderLogo> = mapOf("]
    for k, (f, title) in LOGOS.items():
        lg = logos[k]
        parts = []
        for p in lg["paths"]:
            fill = ("0xFF" + p["fill"][1:]) if p["fill"] else "null"
            g = p["gradient"]
            if g:
                x1, y1, x2, y2 = (fmt(v) + "f" for v in g["pts"])
                st = ", ".join(f"{fmt(o)}f to {c}L" for o, c in g["stops"])
                parts.append(f'LogoPath("{p["d"]}", null, LogoGradient({x1}, {y1}, {x2}, {y2}, listOf({st})))')
            else:
                parts.append(f'LogoPath("{p["d"]}", {fill})')
        out.append(f'    "{k}" to ProviderLogo("{title}", {"true" if lg["evenodd"] else "false"}, listOf({", ".join(parts)})),')
    out.append(")")
    return "\n".join(out) + "\n"


def outputs() -> dict:
    """Both generated files, by path (gen_assets.py takes the Kotlin one into its own check)."""
    web_logos = {k: parse(f) for k, (f, _) in LOGOS.items()}
    kt_logos = {k: parse_android(f) for k, (f, _) in LOGOS.items()}
    return {WEB: web(web_logos), KT: kotlin(kt_logos)}


def main() -> int:
    files = outputs()
    if "--check" in sys.argv:
        stale = [str(p.relative_to(ROOT)) for p, s in files.items() if not p.exists() or p.read_text(encoding="utf-8") != s]
        if stale:
            print("stale:", ", ".join(stale))
            return 1
        print("provider logos are current")
        return 0
    for p, s in files.items():
        if p.exists() and p.read_text(encoding="utf-8") == s:
            continue
        p.write_text(s, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
