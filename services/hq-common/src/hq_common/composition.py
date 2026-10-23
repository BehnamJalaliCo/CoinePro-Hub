"""The media studio's composition schema (prompt 13 §2.3, contract §22.2 step 4):
the motion graphics of an item are written as code by a model, so the hub
treats them as untrusted data and checks them by rule, twice: in the api
before a composition is stored (`media.item`, a refusal names the rule) and
again in the render worker before it is drawn (which also runs it with no
network at all and aborts every request the page makes).

A composition is ONE self-contained document:
- `html`: CSS animations, SVG, the Web Animations API, inline scripts, and
  only the libraries the render image carries, by these exact paths:
      <script src="/lib/anime.min.js"></script>    anime.js 3.2.2 (MIT)
      <script src="/lib/lottie.min.js"></script>   lottie-web 5.12.2, light build (MIT)
  images and videos only from the item's own assets as /assets/<file id>
  (or an inline data:image PNG/JPEG/WebP); IRANYekanX the only font (the
  render page declares it: no @font-face, no other family); `lang="fa"` and
  `dir="rtl"` on <html>.
- `lottie`: one Lottie JSON for lottie-web: no expressions (code), no
  external asset or font path, IRANYekanX for every text layer.

Nothing in it may reach a network: no fetch, XHR, WebSocket, EventSource,
beacon, worker, dynamic import or module script, no URL with a scheme, no
protocol-relative URL, no <link>, <base>, <iframe>, <object>, <embed>,
<form> or <meta http-equiv>, no @import, no storage or cookie, no eval.
Determinism (Date.now, timers, animation-frame loops, Math.random) is only
warned about: the render page drives a virtual clock and a seeded random.

`check()` never raises for what the document holds; it returns a Report:
`ok` is False when any problem (a refusal) was found.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_BYTES = 1_500_000
FONT = "IRANYekanX"
LIBRARIES = {
    "/lib/anime.min.js": "anime.js 3.2.2 (MIT)",
    "/lib/lottie.min.js": "lottie-web 5.12.2 light (MIT)",
}
GENERIC_FAMILIES = {"inherit", "initial", "unset", "revert"}
NEUTRAL = {"#ffffff", "#000000"}  # always allowed next to the brand palette
ASSET = re.compile(r"^/assets/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
DATA_IMAGE = re.compile(r"^data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$")

# Script and markup that reach (or could reach) a network, or escape the page.
BANNED_CODE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fetch", re.compile(r"\bfetch\s*\(")),
    ("xhr", re.compile(r"XMLHttpRequest")),
    ("websocket", re.compile(r"\bWebSocket\b|\bWebTransport\b")),
    ("event_source", re.compile(r"\bEventSource\b")),
    ("beacon", re.compile(r"sendBeacon")),
    ("worker", re.compile(r"\b(?:Shared)?Worker\s*\(|serviceWorker|importScripts")),
    ("dynamic_import", re.compile(r"\bimport\s*\(|^\s*import\s[\w{*]", re.M)),
    ("peer_connection", re.compile(r"RTCPeerConnection|RTCDataChannel")),
    ("navigation", re.compile(r"\blocation\s*(?:\.\s*(?:href|assign|replace|reload)\b|=[^=])|window\s*\.\s*open\s*\(")),
    ("storage", re.compile(r"\b(?:localStorage|sessionStorage|indexedDB|caches)\b|document\s*\.\s*cookie")),
    ("eval", re.compile(r"\beval\s*\(|\bFunction\s*\(|set(?:Timeout|Interval)\s*\(\s*['\"`]")),
    ("frames", re.compile(
        r"\bwindow\s*\.\s*(?:parent|top|opener)\b|\b(?:parent|opener)\s*\.\s*(?:postMessage|location|document)"
    )),
)
BANNED_TAGS = ("iframe", "frame", "frameset", "object", "embed", "applet", "base", "link", "form",
               "portal", "audio", "source", "track", "noscript")  # fmt: skip
NONDETERMINISTIC = (
    ("date_now", re.compile(r"Date\s*\.\s*now|new\s+Date\s*\(")),
    ("performance_now", re.compile(r"performance\s*\.\s*now")),
    ("timers", re.compile(r"\bset(?:Timeout|Interval)\s*\(")),
    ("animation_frame", re.compile(r"requestAnimationFrame")),
    ("random", re.compile(r"Math\s*\.\s*random")),
)
SCHEME = re.compile(r"(?i)\b(?:https?|wss?|ftp|file|blob|javascript|data|chrome|about|filesystem):")
URL_ATTRS = ("src", "href", "xlink:href", "poster", "action", "formaction", "data", "srcset",
             "background", "ping", "cite", "longdesc", "manifest", "codebase", "archive")  # fmt: skip

_TAG = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9:-]*)((?:\s[^<>]*?)?)\s*/?>", re.S)
_ATTR = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*("[^"]*"|'[^']*'|[^\s"'=<>`]+))?""")
_SCRIPT = re.compile(r"<\s*script\b([^>]*)>(.*?)<\s*/\s*script\s*>", re.S | re.I)
_STYLE = re.compile(r"<\s*style\b[^>]*>(.*?)<\s*/\s*style\s*>", re.S | re.I)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_CSS_URL = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.I | re.S)
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}\"]+)", re.I)
_FONT_SHORTHAND = re.compile(r"(?<![-\w])font\s*:\s*([^;}\"]+)", re.I)
_HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})", re.I)
_HSL = re.compile(r"hsla?\(\s*(-?\d+(?:\.\d+)?)(?:deg)?\s*[, ]\s*(\d+(?:\.\d+)?)%\s*[, ]\s*(\d+(?:\.\d+)?)%", re.I)
_NAMED = re.compile(
    r"(?i)(?:color|background(?:-color)?|fill|stroke|border(?:-[a-z]+)?-color|outline-color|"
    r"stop-color|text-shadow|box-shadow)\s*[:=]\s*['\"]?([a-z]+)\b"
)
NAMED_NEUTRAL = {"white": "#ffffff", "black": "#000000"}
NAMED_SKIP = {"transparent", "currentcolor", "inherit", "initial", "unset", "none", "revert"}


@dataclass
class Report:
    format: str
    sha256: str
    size: int
    problems: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def refuse(self, rule: str, detail: str) -> None:
        if not any(p["rule"] == rule and p["detail"] == detail for p in self.problems):
            self.problems.append({"rule": rule, "detail": detail[:200]})

    def warn(self, rule: str, detail: str) -> None:
        if not any(w["rule"] == rule for w in self.warnings):
            self.warnings.append({"rule": rule, "detail": detail[:200]})

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "format": self.format,
            "sha256": self.sha256,
            "size": self.size,
            "problems": self.problems,
            "warnings": self.warnings,
            "colors": self.colors,
            "fonts": self.fonts,
            "libraries": self.libraries,
            "assets": self.assets,
        }


def sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def check(fmt: str, source: str, allowed_assets: set[str] | None = None) -> Report:
    """The schema check of one composition. `allowed_assets`: the file ids the
    item may use (its company's files and creatives); None = any well-formed
    /assets/<id> (the render worker, which only has the job's own files)."""
    raw = source.encode("utf-8", "surrogatepass")
    rep = Report(format=fmt, sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
    if len(raw) > MAX_BYTES:
        rep.refuse("too_large", f"{len(raw)} bytes > {MAX_BYTES}")
        return rep
    if "\x00" in source:
        rep.refuse("binary", "a NUL byte")
        return rep
    if fmt == "html":
        _check_html(rep, source, allowed_assets)
    elif fmt == "lottie":
        _check_lottie(rep, source, allowed_assets)
    else:
        rep.refuse("format", f"unknown format {fmt!r}")
    rep.colors = sorted(set(rep.colors))
    rep.fonts = sorted(set(rep.fonts))
    rep.assets = sorted(set(rep.assets))
    return rep


# ------------------------------------------------------------------ html --
def _url(rep: Report, value: str, where: str, allowed: set[str] | None, *, image: bool) -> None:
    v = html.unescape(value).strip()
    if not v or v.startswith("#"):
        return  # a fragment (an SVG <use href="#id">, a gradient) stays in the page
    if v in LIBRARIES:
        if where != "script":
            rep.refuse("library_path", f"{v} only as a <script src>")
        return
    m = ASSET.match(v)
    if m:
        if allowed is not None and m.group(1) not in allowed:
            rep.refuse("asset_not_allowed", f"{v}: not a file of this item's company")
        rep.assets.append(m.group(1))
        return
    if image and DATA_IMAGE.match(v):
        return
    if v.startswith("//") or SCHEME.search(v) or "\\" in v:
        rep.refuse("network", f"{where}: {v[:120]}")
        return
    rep.refuse("path_not_allowed", f"{where}: {v[:120]} (only /assets/<id> or /lib/…)")


def _css(rep: Report, css: str, allowed: set[str] | None) -> None:
    text = _CSS_COMMENT.sub(" ", css)
    low = text.lower()
    if "@import" in low:
        rep.refuse("network", "@import")
    if "@font-face" in low:
        rep.refuse("font", "@font-face (the render page declares IRANYekanX)")
    if re.search(r"(?i)expression\s*\(|behavior\s*:|-moz-binding", text):
        rep.refuse("css_code", "CSS expression or binding")
    for m in _CSS_URL.finditer(text):
        _url(rep, m.group(2), "css url()", allowed, image=True)
    for m in _FONT_FAMILY.finditer(text):
        _families(rep, m.group(1))
    for m in _FONT_SHORTHAND.finditer(text):
        # `font: 700 48px/1.2 IRANYekanX` -> the families after the size
        parts = re.split(r"\d+(?:\.\d+)?(?:px|em|rem|%|pt|vw|vh)(?:\s*/\s*[\d.]+\w*)?\s+", m.group(1), 1)
        if len(parts) == 2:
            _families(rep, parts[1])
    _colors(rep, text)


def _families(rep: Report, value: str) -> None:
    for fam in value.split(","):
        name = fam.strip().strip("'\"").strip()
        if not name or name.lower() in GENERIC_FAMILIES or name.startswith("var("):
            continue
        rep.fonts.append(name)
        if name != FONT:
            rep.refuse("font", f"font-family {name!r}: IRANYekanX is the only font")


def _colors(rep: Report, text: str) -> None:
    for m in _HEX.finditer(text):
        rep.colors.append(_hex(m.group(1)))
    for m in _RGB.finditer(text):
        r, g, b = (min(255, int(x)) for x in m.groups())
        rep.colors.append(f"#{r:02x}{g:02x}{b:02x}")
    for m in _HSL.finditer(text):
        rep.colors.append(_hsl(float(m.group(1)), float(m.group(2)), float(m.group(3))))
    for m in _NAMED.finditer(text):
        name = m.group(1).lower()
        if name in NAMED_SKIP or name.startswith(("rgb", "hsl", "var", "url")):
            continue
        rep.colors.append(NAMED_NEUTRAL.get(name, f"named:{name}"))


def _hex(h: str) -> str:
    h = h.lower()
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return "#" + h[:6]


def _hsl(h: float, s: float, light: float) -> str:
    s, light = s / 100, light / 100
    c = (1 - abs(2 * light - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = light - c / 2
    seg = int((h % 360) // 60)
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][seg]
    return "#" + "".join(f"{round((v + m) * 255):02x}" for v in (r, g, b))


def _check_html(rep: Report, source: str, allowed: set[str] | None) -> None:
    doc = _HTML_COMMENT.sub(" ", source)
    if not re.search(r"(?is)<\s*html\b[^>]*\blang\s*=\s*['\"]?fa\b[^>]*>", doc) or not re.search(
        r"(?is)<\s*html\b[^>]*\bdir\s*=\s*['\"]?rtl\b[^>]*>", doc
    ):
        rep.refuse("rtl", '<html lang="fa" dir="rtl"> is required')
    scripts = _SCRIPT.findall(doc)
    for attrs, body in scripts:
        a = {k.lower(): (v or "").strip("'\"") for k, v in _ATTR.findall(attrs)}
        if a.get("type", "").lower() == "module":
            rep.refuse("module_script", "<script type=module>")
        if "src" in a:
            src = html.unescape(a["src"]).strip()
            if src in LIBRARIES:
                rep.libraries.append(src)
            elif src.startswith("//") or SCHEME.search(src):
                rep.refuse("network", f"<script src={src[:100]}>")
            else:
                rep.refuse("script_not_allowed", f"<script src={src[:100]}> (only /lib/…)")
            if body.strip():
                rep.refuse("script_not_allowed", "a <script src> with inline code")
        _code(rep, body)
    for css in _STYLE.findall(doc):
        _css(rep, css, allowed)
    for m in _TAG.finditer(doc):
        tag = m.group(1).lower()
        if tag in BANNED_TAGS:
            rep.refuse("tag", f"<{tag}>")
        if tag == "meta" and re.search(r"(?i)http-equiv", m.group(2)):
            rep.refuse("tag", "<meta http-equiv>")
        for name, value in _ATTR.findall(m.group(2)):
            n = name.lower()
            v = (value or "").strip()
            if v[:1] in ("'", '"'):
                v = v[1:-1]
            if n in URL_ATTRS and tag != "script":
                if n == "srcset":
                    for part in v.split(","):
                        _url(rep, part.strip().split(" ")[0], f"<{tag} srcset>", allowed, image=True)
                else:
                    _url(rep, v, f"<{tag} {n}>", allowed, image=tag in ("img", "image", "video"))
            elif n == "style":
                _css(rep, html.unescape(v), allowed)
            elif n.startswith("on"):
                _code(rep, html.unescape(v))
            elif n in ("fill", "stroke", "stop-color", "color", "flood-color", "lighting-color"):
                _colors(rep, f"{n}: {v}")
    # A backstop: a URL with a scheme anywhere in the document (a string built
    # later in a script, an attribute the tag scan could not split) is refused
    # too, except an SVG/XML namespace, which is a name. A site shown as text
    # is written without its scheme («coinepro.com»).
    stripped = re.sub(r"(?i)xmlns(?::\w+)?\s*=\s*(['\"])[^'\"]*\1", " ", doc)
    stripped = re.sub(r"(?i)https?://www\.w3\.org/[\w/.#-]*", " ", stripped)
    for m in re.finditer(r"(?i)\b(?:https?|wss?|ftp|file)://[^\s'\"<>)]{1,120}", stripped):
        rep.refuse("network", m.group(0)[:120] + " (a site as text is written without https://)")


def _code(rep: Report, js: str) -> None:
    if not js.strip():
        return
    text = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    for rule, pat in BANNED_CODE:
        m = pat.search(text)
        if m:
            rep.refuse(rule, m.group(0).strip()[:80])
    for rule, pat in NONDETERMINISTIC:
        if pat.search(text):
            rep.warn(rule, "the render page drives a virtual clock; tie motion to the timeline")
    _colors(rep, text)
    for m in re.finditer(r"""fontFamily\s*[:=]\s*['"]([^'"]+)['"]""", text):
        _families(rep, m.group(1))


# ---------------------------------------------------------------- lottie --
def _check_lottie(rep: Report, source: str, allowed: set[str] | None) -> None:
    try:
        doc = json.loads(source)
    except ValueError as exc:
        rep.refuse("json", f"not JSON: {str(exc)[:80]}")
        return
    if not isinstance(doc, dict):
        rep.refuse("json", "a Lottie document is an object")
        return
    for key in ("v", "fr", "ip", "op", "w", "h", "layers"):
        if key not in doc:
            rep.refuse("lottie_shape", f"missing {key!r}")
    for f in (doc.get("fonts") or {}).get("list") or []:
        if not isinstance(f, dict):
            continue
        for k in ("fFamily", "fName"):
            name = str(f.get(k) or "")
            rep.fonts.append(name)
            if not name.startswith(FONT):
                rep.refuse("font", f"Lottie font {name!r}: IRANYekanX is the only font")
        if f.get("fPath") or f.get("origin") not in (None, 0):
            rep.refuse("network", "a Lottie font loaded from a path")
    for a in doc.get("assets") or []:
        if not isinstance(a, dict) or "layers" in a:
            continue
        path = f"{a.get('u') or ''}{a.get('p') or ''}"
        if a.get("e") == 1 and DATA_IMAGE.match(str(a.get("p") or "")):
            continue
        _url(rep, path if path.startswith(("/", "data:")) else "/" + path, "lottie asset", allowed, image=True)
    _walk_lottie(rep, doc, 0)


def _walk_lottie(rep: Report, node: Any, depth: int) -> None:
    if depth > 64:
        rep.refuse("lottie_shape", "nested deeper than 64")
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "x" and isinstance(v, str):
                rep.refuse("lottie_expression", "a Lottie expression (code) is not allowed")
            elif isinstance(v, str) and (SCHEME.search(v) and not DATA_IMAGE.match(v) or v.startswith("//")):
                rep.refuse("network", f"lottie {k}: {v[:80]}")
            elif k == "c" and isinstance(v, dict) and isinstance(v.get("k"), list):
                _lottie_color(rep, v["k"])
            else:
                _walk_lottie(rep, v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _walk_lottie(rep, v, depth + 1)


def _lottie_color(rep: Report, k: list[Any]) -> None:
    if len(k) >= 3 and all(isinstance(x, (int, float)) for x in k[:3]):
        rep.colors.append("#" + "".join(f"{round(max(0.0, min(1.0, float(x))) * 255):02x}" for x in k[:3]))


# ------------------------------------------------------------ the brand --
def off_palette(colors: list[str], palette: list[str], tolerance: float = 6.0) -> list[str]:
    """The composition's colours that are not the brand's (within a small
    distance in RGB, so an anti-aliased or rounded hex still counts)."""
    pal = [_rgb(p) for p in {*(c.lower() for c in palette if c), *NEUTRAL}]
    out = []
    for c in colors:
        if c.startswith("named:"):
            out.append(c)
            continue
        rgb = _rgb(c)
        if not any(sum((a - b) ** 2 for a, b in zip(rgb, p, strict=True)) ** 0.5 <= tolerance for p in pal):
            out.append(c)
    return sorted(set(out))


def _rgb(h: str) -> tuple[int, int, int]:
    h = _hex(h.lstrip("#"))
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
