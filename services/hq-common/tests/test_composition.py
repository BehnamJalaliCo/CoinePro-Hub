"""The media studio's composition schema (prompt 13 §2.3): no network, the
allowed libraries only, IRANYekanX only, right to left; Lottie without code."""

from __future__ import annotations

import json

import pytest

from hq_common import composition as C

ASSET = "3f2b8a10-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
GOOD = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>
  body {{ margin: 0; background: #0E1116; font-family: IRANYekanX; }}
  .t {{ color: #F2B705; font: 700 64px/1.3 IRANYekanX; animation: rise 1.2s ease-out both; }}
  .bg {{ background-image: url('/assets/{ASSET}'); }}
  @keyframes rise {{ from {{ opacity: 0; transform: translateY(40px); }} to {{ opacity: 1; }} }}
</style>
<script src="/lib/anime.min.js"></script></head>
<body><svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><rect fill="#ffffff" width="5" height="5"/>
<use href="#x"/></svg>
<div class="t">بیت‌کوین <bdi>BTC/USDT</bdi> چیست؟</div><img src="/assets/{ASSET}" alt="">
<script>anime({{targets: '.t', translateY: [40, 0], duration: 1200, autoplay: true}});</script>
</body></html>"""


def test_a_clean_composition_passes_and_reports_colours_fonts_and_assets() -> None:
    rep = C.check("html", GOOD, {ASSET})
    assert rep.ok, rep.problems
    assert rep.libraries == ["/lib/anime.min.js"]
    assert rep.fonts == ["IRANYekanX"]
    assert rep.assets == [ASSET]
    assert {"#0e1116", "#f2b705", "#ffffff"} <= set(rep.colors)
    assert rep.sha256 == C.sha256(GOOD)


@pytest.mark.parametrize(
    ("snippet", "rule"),
    [
        ("<script>fetch('/x')</script>", "fetch"),
        ("<script>const r = new XMLHttpRequest()</script>", "xhr"),
        ("<script>new WebSocket('wss://a')</script>", "websocket"),
        ("<script src=https://cdn.example.com/anime.js></script>", "network"),
        ("<script src='//cdn.example.com/x.js'></script>", "network"),
        ("<script src='/lib/other.js'></script>", "script_not_allowed"),
        ("<script type=module>let a = 1</script>", "module_script"),
        ("<script>import('/lib/anime.min.js')</script>", "dynamic_import"),
        ("<script>navigator.sendBeacon('/x', 1)</script>", "beacon"),
        ("<script>localStorage.x = 1</script>", "storage"),
        ("<script>eval('1')</script>", "eval"),
        ("<script>location.href = '/x'</script>", "navigation"),
        ("<img src='https://evil.example/p.png'>", "network"),
        ("<img src='/assets/0b4a5c6d-0000-4000-8000-000000000000'>", "asset_not_allowed"),
        ("<link rel=stylesheet href='/x.css'>", "tag"),
        ("<iframe srcdoc='x'></iframe>", "tag"),
        ("<base href='/'>", "tag"),
        ("<meta http-equiv=refresh content='0;url=/x'>", "tag"),
        ("<style>@import url('/x.css');</style>", "network"),
        ("<style>@font-face { font-family: X; src: url('/f.woff2'); }</style>", "font"),
        ("<style>p { font-family: Vazirmatn, sans-serif; }</style>", "font"),
        ('<div style="background:url(http://a.example/x.png)"></div>', "network"),
        ("<p>see https://example.com</p>", "network"),
    ],
)
def test_network_scripts_tags_and_fonts_are_refused_by_rule(snippet: str, rule: str) -> None:
    doc = GOOD.replace("</body>", snippet + "</body>")
    rep = C.check("html", doc, {ASSET})
    assert not rep.ok
    assert rule in {p["rule"] for p in rep.problems}, rep.problems


def test_rtl_and_persian_are_required() -> None:
    rep = C.check("html", GOOD.replace(' dir="rtl"', ""), {ASSET})
    assert {p["rule"] for p in rep.problems} == {"rtl"}


def test_nondeterminism_is_only_a_warning() -> None:
    doc = GOOD.replace("</body>", "<script>let t = Date.now(); Math.random();</script></body>")
    rep = C.check("html", doc, {ASSET})
    assert rep.ok
    assert {"date_now", "random"} <= {w["rule"] for w in rep.warnings}


def test_size_and_unknown_format() -> None:
    assert not C.check("html", "x" * (C.MAX_BYTES + 1)).ok
    assert C.check("svg", "<svg/>").problems[0]["rule"] == "format"


LOTTIE = {
    "v": "5.12.2",
    "fr": 30,
    "ip": 0,
    "op": 90,
    "w": 1080,
    "h": 1920,
    "fonts": {"list": [{"fName": "IRANYekanX-Bold", "fFamily": "IRANYekanX", "fStyle": "Bold"}]},
    "assets": [{"id": "img0", "u": "/assets/", "p": ASSET, "e": 0}],
    "layers": [{"ty": 4, "shapes": [{"ty": "fl", "c": {"a": 0, "k": [0.949, 0.718, 0.02, 1]}}]}],
}


def test_a_lottie_without_code_passes_and_its_colours_are_read() -> None:
    rep = C.check("lottie", json.dumps(LOTTIE), {ASSET})
    assert rep.ok, rep.problems
    assert "#f2b705" in rep.colors


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        (
            lambda d: d["layers"][0].update({"ks": {"p": {"x": "loopOut('cycle')"}}}),
            "lottie_expression",
        ),
        (lambda d: d["assets"][0].update({"u": "https://evil.example/", "p": "a.png"}), "network"),
        (lambda d: d["fonts"]["list"][0].update({"fFamily": "Arial"}), "font"),
        (
            lambda d: d["fonts"]["list"][0].update({"fPath": "https://fonts.example/x.css"}),
            "network",
        ),
        (lambda d: d.pop("layers"), "lottie_shape"),
    ],
)
def test_lottie_code_paths_and_fonts_are_refused(change, rule) -> None:  # type: ignore[no-untyped-def]
    doc = json.loads(json.dumps(LOTTIE))
    change(doc)
    rep = C.check("lottie", json.dumps(doc), {ASSET})
    assert rule in {p["rule"] for p in rep.problems}, rep.problems


def test_off_palette_allows_the_brand_and_neutrals_only() -> None:
    assert C.off_palette(
        ["#f2b705", "#f2b706", "#ffffff", "#ff0000", "named:red"], ["#F2B705"]
    ) == [
        "#ff0000",
        "named:red",
    ]
