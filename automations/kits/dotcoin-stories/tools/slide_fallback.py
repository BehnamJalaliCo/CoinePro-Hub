# -*- coding: utf-8 -*-
"""DotCoin.me (@DotCoinMe) — the TESTED fallback for the day's story slides (2026-11-27).

When the art path fails (ChatGPT's set did not come, Gemini is off) the session does NOT improvise its
own HTML: it fills one spec per slide and runs this tool. It draws a finance-publication slide (FT /
Bloomberg data page: paper, mustard or ink ground, hairlines, a big figure or a chart drawn from the
numbers) in IRANYekanX Pro FaNum ONLY, applies the number rules (fa-type: Persian digits, no separator
up to 4 digits, «٬» from 5, «/» for decimals), fits every line to its column, and runs the TYPE GATE
(every glyph drawn by the page's own font, nothing out of its box or chip, the frame's zones empty).
A slide that fails the gate is NOT written (exit 2) — fix the text and run again.

Usage: VENV/bin/python -I KIT/tools/slide_fallback.py build/fb/s01.json [build/fb/s02.json …]
       VENV/bin/python -I KIT/tools/slide_fallback.py --set build/fb/set.json   (a list of specs)
Then frame each one with slide_frame.py (bg = this tool's PNG; mark, number, word added there).

spec = {
  "theme": "paper",                 # paper (#F4F0E6) | mustard (#F3C242) | ink (#0B0B0B): one per set,
                                    #   mustard/ink for slide 1 and 12 as accents
  "tag": "مدیریت ریسک",              # the pillar, small chip (optional)
  "series": "حجم پوزیشن با قانون ۱ درصد",  # the lesson's title, small (optional)
  "title": "ترس امروز: [۱۲ از ۱۰۰]",  # [..] = the key words on a chip (never more than one chip a title)
  "lines": ["…", "…"],              # 0–3 short lines under the visual; [..] = a bold key part
  "visual": {…},                    # one of the kinds below (optional)
  "out": "build/fb/slide_01.png"
}
Figures: write them as numbers (60480, 9.6) and the tool sets them, or as Persian text («۶۰٬۴۸۰»);
either way they are normalised. Never «-» beside a figure: tone "down"/"up" colours it red/green.
Visual kinds:
  {"kind": "figure", "value": 12, "unit": "از ۱۰۰", "label": "ترس شدید", "tone": "down"}
  {"kind": "gauge", "value": 12, "max": 100, "label": "ترس شدید", "tone": "down"}
  {"kind": "figures", "items": [{"label": "کل حساب", "value": 5000, "unit": "دلار"},
                                {"label": "حداکثر ضرر", "value": 50, "unit": "دلار", "tone": "down"}]}
  {"kind": "share", "part": 1, "total": 100, "part_label": "۱٪ ریسک هر معامله", "total_label": "کل حساب"}
  {"kind": "formula", "result": "حجم پوزیشن", "top": "مبلغ ریسک", "bottom": "فاصله‌ی حد ضرر"}
  {"kind": "calc", "terms": ["۵۰ دلار", "÷", "۴٪"], "result": "۱۲۵۰ دلار", "note": "حدود ۰/۰۲۱ بیت‌کوین"}
  {"kind": "levels", "levels": [{"label": "ورود", "value": 60480, "unit": "دلار"},
                                {"label": "حد ضرر", "value": 58060, "unit": "دلار", "tone": "down"}],
                     "gap": "۴٪"}
  {"kind": "table", "head": ["حد ضرر", "حجم پوزیشن"], "rows": [["۴٪", "۱۲۵۰ دلار"], ["۸٪", "۶۲۵ دلار"]],
                    "bars": [1250, 625]}
  {"kind": "lines", "series": [{"label": "ریسک ۱٪", "values": [5000, …], "tone": "up"},
                               {"label": "ریسک ۴٪", "values": [5000, …], "tone": "down"}],
                    "x": ["شروع", "ضرر دهم"], "unit": "دلار"}
  {"kind": "bars", "rows": [{"label": "ضرر", "value": 9.6, "pct": true, "tone": "down"},
                            {"label": "سود لازم", "value": 10.6, "pct": true, "tone": "up"}]}
  {"kind": "blocks", "items": [{"label": "اندازه‌ی پوزیشن", "value": 1250, "unit": "دلار", "size": 1250},
                               {"label": "وثیقه با اهرم ۵", "value": 250, "unit": "دلار", "size": 250}]}
  {"kind": "checklist", "items": ["…", "…", "…"]}
  {"kind": "art", "src": "in/gemini_1.png", "focus": "50% 50%"}   (Gemini's picture as the hero)
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for cand in (os.environ.get("FATYPE", ""), "/home/studio/kits/fa-type", str(HERE.parent.parent / "fa-type")):
    if cand and Path(cand, "fatype.py").exists():
        sys.path.insert(0, cand)
        break
import fatype as F  # noqa: E402

FONTS = Path(os.environ.get("FONTS_PRO", "/home/studio/kits/fonts-pro"))
MUSTARD, BLACK, WHITE, UP, DOWN = "#F3C242", "#000000", "#FFFFFF", "#16C784", "#EA3943"
THEMES = {
    # ground, ink, soft ink, rule, chip bg, chip fg, panel
    "paper": ("#F4F0E6", "#0B0B0B", "#55524B", "rgba(11,11,11,.22)", MUSTARD, BLACK, "#ECE6D8"),
    "mustard": (MUSTARD, "#0B0B0B", "#3A3115", "rgba(0,0,0,.28)", BLACK, MUSTARD, "#E7B735"),
    "ink": ("#0B0B0B", "#F4F0E6", "#B9B3A6", "rgba(244,240,230,.22)", MUSTARD, BLACK, "#17150F"),
}
# the frame (slide_frame.py) owns y < 370 (Instagram's bar + the mark) and y > 1390 (the word bar +
# the reply box): this tool's text lives between them
AREA = (380, 1380)
BANDS = [(0, 370), (1390, 1920)]
DOWN_ON = {"paper": "#D92D3A", "mustard": "#B3141F", "ink": DOWN}  # red readable on each ground
UP_ON = {"paper": "#0E9F63", "mustard": "#0B6B43", "ink": UP}


def T(s) -> str:
    """Text for the page: the number rules, escaped, [..] = a chip (titles) — kept whole."""
    s = re.sub(r"[.。]\s*$", "", F.normalize(str(s)).strip())
    # every figure isolated (with its «٪»): two figures around a sign never merge into one run
    s = F.symbols(html.escape(s))
    return re.sub(r"[۰-۹]+(?:[/\u066c][۰-۹]+)*٪?", lambda m: f"<bdi>{m.group(0)}</bdi>", s)


def chips(s: str, cls: str = "k") -> str:
    return re.sub(r"\[(.+?)\]", lambda m: f'<span class="{cls}">{m.group(1)}</span>', T(s))


def fig(v, unit: str = "", *, pct: bool = False, decimals=None) -> str:
    """A figure: a number (set by the rules) or a text (normalised), with its unit after it."""
    if isinstance(v, (int, float)):
        txt = F.num(v, decimals, pct=pct)
    else:
        txt = F.normalize(str(v))
    u = f'<span class="u">{T(unit)}</span>' if unit else ""
    return f'<bdi class="n">{html.escape(txt)}</bdi>{u}'


def tone(t: str | None, theme: str) -> str:
    return {"down": DOWN_ON[theme], "up": UP_ON[theme]}.get(t or "", "")


# -------------------------------------------------------------------------------- the visuals --
def v_figure(v, th):
    c = tone(v.get("tone"), th)
    st = f' style="color:{c}"' if c else ""
    return (f'<div class="figure"><div class="big"{st}>{fig(v.get("value"), v.get("unit", ""), pct=bool(v.get("pct")))}</div>'
            + (f'<div class="lab">{T(v["label"])}</div>' if v.get("label") else "") + "</div>")


def v_gauge(v, th):
    val, mx = float(v.get("value", 0)), float(v.get("max", 100)) or 100
    frac = max(0.0, min(1.0, val / mx))
    c = tone(v.get("tone"), th) or MUSTARD
    r, cx, cy = 300, 360, 330
    a = math.pi * (1 - frac)
    x, y = cx + r * math.cos(a), cy - r * math.sin(a)
    ticks = "".join(
        f'<line x1="{cx + (r + 18) * math.cos(math.pi * (1 - k / 10)):.1f}" y1="{cy - (r + 18) * math.sin(math.pi * (1 - k / 10)):.1f}" '
        f'x2="{cx + (r + 36) * math.cos(math.pi * (1 - k / 10)):.1f}" y2="{cy - (r + 36) * math.sin(math.pi * (1 - k / 10)):.1f}" class="tick"/>'
        for k in range(11))
    arc_bg = f'<path d="M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}" class="track"/>'
    arc = f'<path d="M {cx - r} {cy} A {r} {r} 0 0 1 {x:.1f} {y:.1f}" stroke="{c}" class="arc"/>' if frac > 0 else ""
    nx, ny = cx + 0.78 * r * math.cos(a), cy - 0.78 * r * math.sin(a)
    needle = f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" class="needle"/><circle cx="{cx}" cy="{cy}" r="16" class="hub"/>'
    st = f' style="color:{tone(v.get("tone"), th)}"' if v.get("tone") else ""
    return (f'<div class="gauge"><svg viewBox="0 -30 720 380" preserveAspectRatio="xMidYMid meet">{arc_bg}{ticks}{arc}{needle}</svg>'
            f'<div class="gnum"{st}>{fig(v.get("value"))}<span class="u">{T(v.get("of") or ("از " + F.num(mx)))}</span></div>'
            f'{"<div class=lab>" + T(v["label"]) + "</div>" if v.get("label") else ""}</div>')


def v_figures(v, th):
    rows = []
    for it in v.get("items", [])[:3]:
        c = tone(it.get("tone"), th)
        st = f' style="color:{c}"' if c else ""
        rows.append(f'<div class="frow"><div class="flab">{T(it.get("label", ""))}</div>'
                    f'<div class="fval"{st}>{fig(it.get("value"), it.get("unit", ""), pct=bool(it.get("pct")))}</div></div>')
    return f'<div class="figures">{"".join(rows)}</div>'


def v_share(v, th):
    part, total = float(v.get("part", 1)), float(v.get("total", 100)) or 100
    w = max(0.6, 100 * part / total)
    return (f'<div class="share"><div class="slab"><span class="dn">{T(v.get("part_label", ""))}</span></div>'
            f'<div class="sbar"><div class="spart" style="width:{w:.2f}%"></div></div>'
            f'<div class="slab2">{T(v.get("total_label", ""))}</div></div>')


def v_formula(v, th):
    return (f'<div class="formula"><div class="fres">{T(v.get("result", ""))}</div><div class="eq">=</div>'
            f'<div class="frac"><div class="ftop">{T(v.get("top", ""))}</div><div class="fline"></div>'
            f'<div class="fbot">{T(v.get("bottom", ""))}</div></div></div>')


def v_calc(v, th):
    terms = "".join(f'<span class="{"op" if t.strip() in "÷×+=−" else "term"}">{T(t)}</span>' for t in v.get("terms", []))
    note = f'<div class="cnote">{T(v["note"])}</div>' if v.get("note") else ""
    return (f'<div class="calc"><div class="cline">{terms}</div><div class="eq">=</div>'
            f'<div class="cres">{T(v.get("result", ""))}</div>{note}</div>')


def v_levels(v, th):
    lv = v.get("levels", [])[:3]
    rows = []
    step = 70 / max(1, len(lv) - 1)
    for i, it in enumerate(lv):
        c = tone(it.get("tone"), th)
        cls = "lvl dn" if it.get("tone") == "down" else ("lvl up" if it.get("tone") == "up" else "lvl")
        rows.append(f'<div class="{cls}" style="top:{6 + i * step:.1f}%"><div class="lline"{f" style=border-color:{c}" if c else ""}></div>'
                    f'<div class="ltxt"><b>{T(it.get("label", ""))}</b> {fig(it.get("value"), it.get("unit", ""))}</div></div>')
    gap = (f'<div class="lgap" style="top:6%;height:{step * (len(lv) - 1):.1f}%"><span>{T(v["gap"])}</span></div>'
           if v.get("gap") else "")
    return f'<div class="levels">{"".join(rows)}{gap}</div>'


def v_table(v, th):
    head = "".join(f"<th>{T(h)}</th>" for h in v.get("head", []))
    bars = v.get("bars") or []
    mx = max([float(b) for b in bars] or [1]) or 1
    body = []
    for i, r in enumerate(v.get("rows", [])[:5]):
        cells = "".join(f"<td>{T(c)}</td>" for c in r)
        bar = f'<td class="tb"><div style="width:{100 * float(bars[i]) / mx:.1f}%"></div></td>' if i < len(bars) else ""
        body.append(f"<tr>{cells}{bar}</tr>")
    extra = "<th></th>" if bars else ""
    return f'<table class="tbl"><thead><tr>{head}{extra}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def v_lines(v, th):
    series = v.get("series", [])[:3]
    allv = [float(x) for s in series for x in s.get("values", [])] or [0, 1]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    W, H, L, R, Tp, B = 900, 560, 40, 40, 30, 60

    def xy(i, n, val):
        return L + (W - L - R) * (i / max(1, n - 1)), Tp + (H - Tp - B) * (1 - (val - lo) / (hi - lo))

    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{Tp + (H - Tp - B) * k / 4:.0f}" y2="{Tp + (H - Tp - B) * k / 4:.0f}" class="grid"/>' for k in range(5))
    paths, labels = [], []
    for s in series:
        vals = [float(x) for x in s.get("values", [])]
        c = tone(s.get("tone"), th) or (MUSTARD if th == "ink" else BLACK)
        pts = " ".join(f"{xy(i, len(vals), val)[0]:.1f},{xy(i, len(vals), val)[1]:.1f}" for i, val in enumerate(vals))
        ex, ey = xy(len(vals) - 1, len(vals), vals[-1])
        paths.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>'
                     f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="11" fill="{c}"/>')
        # the end label in HTML (positioned in % of the chart box) so the gate sees its font
        labels.append((100 * ex / W, 100 * ey / H, c, f'<span class="cl">{T(s.get("label", ""))}</span>{fig(vals[-1], v.get("unit", ""))}'))
    lab_html = "".join(
        f'<div class="clab" style="left:{max(4, min(x - 2, 70)):.1f}%;top:{max(0, min(y - 13, 82)):.1f}%;color:{c}">{t}</div>'
        for x, y, c, t in sorted(labels, key=lambda q: q[1]))
    # keep the two end labels apart
    xs = v.get("x") or []
    xl = (f'<div class="xl"><span>{T(xs[0])}</span><span>{T(xs[-1])}</span></div>' if len(xs) >= 2 else "")
    start = f'<div class="ystart">{fig(series[0]["values"][0], v.get("unit", ""))}</div>' if series else ""
    return (f'<div class="chart"><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">{grid}{"".join(paths)}</svg>'
            f'{start}{lab_html}{xl}</div>')


def v_bars(v, th):
    rows = v.get("rows", [])[:6]
    mx = max([float(r.get("value", 0)) for r in rows] or [1]) or 1
    out = []
    for r in rows:
        c = tone(r.get("tone"), th) or (MUSTARD if th != "mustard" else BLACK)
        w = 100 * float(r.get("value", 0)) / mx
        out.append(f'<div class="brow"><div class="blab">{T(r.get("label", ""))}</div>'
                   f'<div class="btrack"><div class="bfill" style="width:{w:.1f}%;background:{c}"></div></div>'
                   f'<div class="bval" style="color:{c}">{fig(r.get("value"), r.get("unit", ""), pct=bool(r.get("pct")))}</div></div>')
    return f'<div class="bars">{"".join(out)}</div>'


def v_blocks(v, th):
    items = v.get("items", [])[:2]
    mx = max([float(i.get("size", 1)) for i in items] or [1]) or 1
    out = []
    for k, it in enumerate(items):
        side = 100 * math.sqrt(float(it.get("size", 1)) / mx)
        out.append(f'<div class="blk"><div class="bsq {"alt" if k else ""}" style="width:{side * 3.6:.0f}px;height:{side * 3.6:.0f}px"></div>'
                   f'<div class="bv">{fig(it.get("value"), it.get("unit", ""))}</div><div class="bl">{T(it.get("label", ""))}</div></div>')
    return f'<div class="blocks">{"".join(out)}</div>'


def v_checklist(v, th):
    tick = '<svg viewBox="0 0 40 40" class="tick"><rect x="1" y="1" width="38" height="38" rx="8"/><path d="M10 21 l7 7 l14 -16"/></svg>'
    return '<div class="check">' + "".join(f'<div class="ci">{tick}<span>{chips(i, "kb")}</span></div>' for i in v.get("items", [])[:4]) + "</div>"


def v_art(v, th):
    src = Path(v["src"]).resolve()
    return f'<div class="art" style="background-image:url(\'file://{src}\');background-position:{html.escape(v.get("focus") or "50% 50%")}"></div>'


VISUALS = {"figure": v_figure, "gauge": v_gauge, "figures": v_figures, "share": v_share, "formula": v_formula,
           "calc": v_calc, "levels": v_levels, "table": v_table, "lines": v_lines, "bars": v_bars,
           "blocks": v_blocks, "checklist": v_checklist, "art": v_art}


def page(s: dict) -> str:
    th = s.get("theme") or "paper"
    if th not in THEMES:
        raise SystemExit(f"theme must be one of {sorted(THEMES)}")
    g, ink, soft, rule, cbg, cfg, panel = THEMES[th]
    vis = s.get("visual") or {}
    kind = vis.get("kind")
    if kind and kind not in VISUALS:
        raise SystemExit(f"visual kind must be one of {sorted(VISUALS)}")
    vhtml = VISUALS[kind](vis, th) if kind else ""
    tag = f'<span class="tag">{T(s["tag"])}</span>' if s.get("tag") else ""
    series = f'<span class="ser">{T(s["series"])}</span>' if s.get("series") else ""
    lines = "".join(f"<p>{chips(x, 'kb')}</p>" for x in (s.get("lines") or [])[:3])
    faces = "".join(
        f'@font-face{{font-family:Yk;font-weight:{w};src:url("file://{FONTS}/IRANYekanXFaNum-{n}.ttf")}}'
        for n, w in (("Regular", 400), ("Medium", 500), ("DemiBold", 600), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)))
    dn, up = DOWN_ON[th], UP_ON[th]
    return f"""<!doctype html><html dir="rtl" lang="fa"><head><meta charset="utf-8"><style>
{faces}
{F.SYM_CSS}
:root {{ --s: 1; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1080px; height:1920px; overflow:hidden; background:{g}; color:{ink};
  font-family: Yk; font-weight:500; font-feature-settings: "kern" 1; -webkit-font-smoothing: antialiased; }}
.paper {{ position:absolute; inset:0; background:
  radial-gradient(1200px 900px at 80% 10%, rgba(255,255,255,{'.35' if th == 'paper' else '.10'}), transparent 60%); }}
.area {{ position:absolute; left:72px; right:72px; top:{AREA[0]}px; height:{AREA[1] - AREA[0]}px;
  display:flex; flex-direction:column; gap:calc(var(--s)*30px); overflow:hidden; }}
.head {{ display:flex; align-items:center; gap:18px; border-bottom:2px solid {rule}; padding-bottom:calc(var(--s)*18px); }}
.tag {{ background:{cbg}; color:{cfg}; font-weight:800; font-size:calc(var(--s)*28px); padding:4px 18px; border-radius:10px; white-space:nowrap; }}
.ser {{ color:{soft}; font-weight:600; font-size:calc(var(--s)*28px); white-space:nowrap; overflow:hidden; }}
h1 {{ font-weight:900; font-size:calc(var(--s)*92px); line-height:1.32; letter-spacing:0; text-wrap:balance; }}
.k {{ background:{cbg}; color:{cfg}; border-radius:18px; padding:0 18px; white-space:nowrap; }}
.kb {{ font-weight:800; color:{ink}; }}
.vis {{ flex:1 1 auto; min-height:calc(var(--s)*360px); display:flex; align-items:center; justify-content:center; position:relative; }}
.lines p {{ font-size:calc(var(--s)*44px); line-height:1.6; font-weight:500; color:{ink}; text-wrap:pretty; }}
.lines {{ border-top:2px solid {rule}; padding-top:calc(var(--s)*22px); }}
.n {{ font-weight:800; }} .u {{ font-weight:600; font-size:.62em; margin-right:.3em; color:{soft}; }}
.figure .u, .fval .u, .gnum .u {{ font-size:.34em; }}
.dn {{ color:{dn}; }}
/* figure */
.figure {{ text-align:center; }}
.figure .big {{ font-size:calc(var(--s)*230px); line-height:1.15; font-weight:900; white-space:nowrap; }}
.figure .big .n {{ font-weight:900; }}
.lab {{ font-size:calc(var(--s)*40px); font-weight:700; color:{soft}; margin-top:8px; }}
/* gauge */
.gauge {{ width:100%; text-align:center; position:relative; }}
.gauge svg {{ width:88%; height:auto; overflow:visible; }}
.track {{ fill:none; stroke:{rule}; stroke-width:34; stroke-linecap:round; }}
.arc {{ fill:none; stroke-width:34; stroke-linecap:round; }}
.tick {{ stroke:{soft}; stroke-width:4; }}
.needle {{ stroke:{ink}; stroke-width:9; stroke-linecap:round; }} .hub {{ fill:{ink}; }}
.gauge svg {{ width:72%; }}
.gnum {{ font-size:calc(var(--s)*150px); font-weight:900; line-height:1.1; margin-top:calc(var(--s)*6px); white-space:nowrap; }}
.gnum .u {{ font-size:.28em; }}
/* figures */
.figures {{ width:100%; display:flex; flex-direction:column; gap:calc(var(--s)*26px); }}
.frow {{ border-bottom:2px solid {rule}; padding-bottom:calc(var(--s)*20px); }}
.flab {{ font-size:calc(var(--s)*36px); font-weight:600; color:{soft}; }}
.fval {{ font-size:calc(var(--s)*150px); font-weight:900; line-height:1.15; white-space:nowrap; }}
.fval .n {{ font-weight:900; }}
/* share */
.share {{ width:100%; }} .sbar {{ height:calc(var(--s)*120px); background:{ink}; border-radius:6px; position:relative; margin:20px 0; }}
.spart {{ position:absolute; right:0; top:0; bottom:0; background:{dn}; }}
.slab {{ font-size:calc(var(--s)*40px); font-weight:800; }} .slab2 {{ font-size:calc(var(--s)*36px); color:{soft}; font-weight:600; }}
/* formula / calc */
.formula, .calc {{ width:100%; display:flex; flex-direction:column; align-items:center; gap:calc(var(--s)*16px); text-align:center; }}
.fres, .cres {{ background:{cbg}; color:{cfg}; font-weight:900; font-size:calc(var(--s)*72px); padding:6px 36px; border-radius:18px; white-space:nowrap; }}
.eq {{ font-size:calc(var(--s)*80px); font-weight:800; line-height:1; }}
.frac {{ display:flex; flex-direction:column; align-items:center; min-width:70%; }}
.ftop, .fbot {{ font-size:calc(var(--s)*64px); font-weight:800; line-height:1.4; white-space:nowrap; }}
.fline {{ width:100%; height:6px; background:{ink}; margin:12px 0; }}
.cline {{ display:flex; gap:28px; align-items:baseline; font-size:calc(var(--s)*96px); font-weight:900; white-space:nowrap; }}
.cline .op {{ color:{soft}; font-weight:700; }}
.cnote {{ font-size:calc(var(--s)*40px); color:{soft}; font-weight:700; }}
/* levels */
.levels {{ width:100%; height:calc(var(--s)*420px); position:relative; }}
.lvl {{ position:absolute; left:0; right:0; }}
.lline {{ border-top:5px solid {ink}; }} .lvl.dn .lline {{ border-top-style:solid; }}
.ltxt {{ font-size:calc(var(--s)*44px); margin-top:10px; white-space:nowrap; }}
.lvl.dn .ltxt {{ color:{dn}; }} .lvl.up .ltxt {{ color:{up}; }}
.lgap {{ position:absolute; left:6%; border-left:5px solid {soft}; display:flex; align-items:center; }}
.lgap span {{ background:{cbg}; color:{cfg}; font-weight:900; font-size:calc(var(--s)*48px); padding:2px 20px; border-radius:12px; margin-left:18px; white-space:nowrap; }}
/* table */
.tbl {{ width:100%; border-collapse:collapse; font-size:calc(var(--s)*46px); }}
.tbl th {{ text-align:right; font-size:calc(var(--s)*32px); color:{soft}; font-weight:700; padding:10px 8px; border-bottom:3px solid {ink}; }}
.tbl td {{ padding:calc(var(--s)*26px) 8px; border-bottom:2px solid {rule}; font-weight:800; white-space:nowrap; }}
.tbl td.tb {{ width:36%; }} .tbl td.tb div {{ height:calc(var(--s)*46px); background:{ink if th != 'ink' else MUSTARD}; border-radius:4px; }}
/* chart */
.chart {{ width:100%; height:calc(var(--s)*560px); position:relative; direction:ltr; }}
.chart svg {{ position:absolute; inset:0; width:100%; height:86%; }}
.grid {{ stroke:{rule}; stroke-width:2; }}
.clab {{ position:absolute; font-size:calc(var(--s)*36px); font-weight:800; white-space:nowrap; direction:rtl;
  background:{g}; padding:2px 10px; border-radius:8px; }}
.clab .cl {{ font-weight:700; margin-left:.45em; padding-left:.45em; border-left:3px solid currentColor; }}
.ystart {{ position:absolute; left:0; top:-2%; font-size:calc(var(--s)*32px); color:{soft}; font-weight:700; direction:rtl; }}
.xl {{ position:absolute; left:0; right:0; bottom:0; display:flex; justify-content:space-between; font-size:calc(var(--s)*32px); color:{soft}; font-weight:600; }}
/* bars */
.bars {{ width:100%; display:flex; flex-direction:column; gap:calc(var(--s)*30px); }}
.brow {{ display:grid; grid-template-columns: 30% 1fr auto; align-items:center; gap:20px; }}
.blab {{ font-size:calc(var(--s)*38px); font-weight:700; }}
.btrack {{ height:calc(var(--s)*64px); background:{panel}; border-radius:6px; overflow:hidden; }}
.bfill {{ height:100%; }}
.bval {{ font-size:calc(var(--s)*48px); font-weight:900; white-space:nowrap; }}
/* blocks */
.blocks {{ width:100%; display:flex; justify-content:center; align-items:flex-end; gap:60px; }}
.blk {{ text-align:center; }} .bsq {{ background:{ink}; margin:0 auto 18px; border-radius:6px; }}
.bsq.alt {{ background:{cbg if th != 'mustard' else BLACK}; }}
.bv {{ font-size:calc(var(--s)*56px); font-weight:900; white-space:nowrap; }} .bl {{ font-size:calc(var(--s)*32px); color:{soft}; font-weight:600; }}
/* checklist */
.check {{ width:100%; display:flex; flex-direction:column; }}
.ci {{ display:flex; gap:26px; align-items:center; padding:calc(var(--s)*30px) 0; border-bottom:2px solid {rule}; font-size:calc(var(--s)*48px); font-weight:700; line-height:1.45; }}
.ci .tick {{ flex:0 0 auto; width:calc(var(--s)*64px); height:calc(var(--s)*64px); }}
.ci .tick rect {{ fill:{cbg}; }} .ci .tick path {{ fill:none; stroke:{cfg}; stroke-width:5; stroke-linecap:round; stroke-linejoin:round; }}
/* art */
.art {{ width:100%; height:100%; min-height:calc(var(--s)*560px); background-size:cover; border-radius:10px; }}
</style></head><body><div class="paper"></div>
<div class="area">
  <div class="head">{tag}{series}</div>
  <h1>{chips(s.get("title") or "")}</h1>
  <div class="vis">{vhtml}</div>
  {f'<div class="lines">{lines}</div>' if lines else ""}
</div>
<script>
// fit: shrink the whole type scale until nothing overflows the area, a chip or the column
function over() {{
  const a = document.querySelector('.area'), ar = a.getBoundingClientRect();
  if (a.scrollHeight > a.clientHeight + 1) return true;
  for (const e of a.querySelectorAll('h1, .k, .lines p, .vis *')) {{
    const r = e.getBoundingClientRect();
    if (r.width && (r.left < ar.left - 1 || r.right > ar.right + 1)) return true;
    if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== 'visible') return true;
  }}
  const v = document.querySelector('.vis'), vr = v.getBoundingClientRect();
  for (const e of v.children) {{ const r = e.getBoundingClientRect(); if (r.height > vr.height + 1) return true; }}
  return false;
}}
window.fitScale = async () => {{
  await document.fonts.ready;
  let s = 1;
  while (over() && s > 0.5) {{ s = +(s - 0.02).toFixed(2); document.documentElement.style.setProperty('--s', s); }}
  return s;
}};
</script></body></html>"""


def make(spec: dict, base: Path) -> bool:
    out = Path(spec["out"])
    if not out.is_absolute():
        out = base / out
    html_text = page(spec)
    # the fit runs inside the gated render (fatype.render opens the page; fitScale before the gate)
    verdict = render_fit(html_text, out)
    F.report(verdict, out)
    if verdict.get("scale") is not None:
        print(f"  type scale {verdict['scale']}")
    return verdict["ok"]


def render_fit(html_text: str, out: Path) -> dict:
    import tempfile

    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pf = Path(tmp) / "slide.html"
        pf.write_text(html_text, encoding="utf-8")
        png = Path(tmp) / "slide.png"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=F.CHROME, headless=True, args=["--allow-file-access-from-files"])
            try:
                pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
                pg.goto(pf.as_uri())
                scale = pg.evaluate("window.fitScale()")
                pg.wait_for_timeout(150)
                verdict = F.gate(pg, bands=BANDS, max_weight=900, fonts_allowed=("IRANYekanX",))
                verdict["scale"] = scale
                if scale <= 0.5 and verdict["ok"]:
                    verdict["ok"] = False
                    verdict["problems"].append("the text does not fit even at half size: shorten it")
                if verdict["ok"]:
                    pg.screenshot(path=str(png), full_page=False)
            finally:
                b.close()
        if verdict["ok"]:
            out.write_bytes(png.read_bytes())
        elif out.exists():
            out.unlink()
    F.record(out, verdict, "dotcoin-stories/slide_fallback")
    return verdict


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    specs: list[tuple[dict, Path]] = []
    if argv[0] == "--set":
        p = Path(argv[1])
        specs = [(s, Path.cwd()) for s in json.loads(p.read_text(encoding="utf-8"))]
    else:
        specs = [(json.loads(Path(a).read_text(encoding="utf-8")), Path.cwd()) for a in argv]
    bad = [s.get("out") for s, base in specs if not make(s, base)]
    if bad:
        print(f"FAILED {len(bad)} of {len(specs)}: {', '.join(map(str, bad))} — nothing written for them; fix and run again")
        return 2
    print(f"ALL {len(specs)} SLIDES PASSED THE TYPE GATE")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
