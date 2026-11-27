# -*- coding: utf-8 -*-
"""@behnamjalali.tech LUMEN cards (COMMON/tools/card.py): every still picture of the page — the reel's cover,
the 12 daily story cards, the breaking-news flash story, the YouTube thumbnail — set in code, so every Persian
letter is exact (an AI picture is only ever a picture inside the card, never its text).

usage (render venv, PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright):
  PY -I COMMON/tools/card.py <spec.json> <out.jpg>          one card
  PY -I COMMON/tools/card.py --many <specs.json> <outdir>   a list of specs -> outdir/<name>.jpg (one browser)
  PY -I COMMON/tools/card.py --sheet <outdir> <sheet.jpg>   the cards side by side (to look at them all at once)

A spec (JSON; every text Persian unless it is a name; digits may be Latin, they are shown in Persian except in
Latin runs): {"type": "cover" | "story" | "flash" | "thumb", "pillar": "repo|model|news|tool|trick|behind|explain",
  "kicker": "ریپوی روز", "title": "…", "keys": ["words in the spectrum"], "latin": "Claude Fable 5.2" (a big
  Latin name), "body": ["line", "line"], "image": "<path of a picture>", "fit": "cover|contain",
  "chip": "…", "badge": "۲ از ۱۲" (a counter: drawn «n از m» in Persian digits, one RTL run, whatever digits it is given), "word": "<the day's reply word>", "cta": "…", "source": "anthropic.com",
  "time": "۱۸:۴۰", "layout": "hero|split|list|quote|stat|teaser", "stat": "۳۶×", "stat_label": "…",
  "list": ["…", "…"], "accent": "#hex (optional; else the pillar's)"}
Types:
- cover (1080x1920; the grid shows its middle 1080x1350: the title and the hero stay inside it);
- story (1080x1920; the top 250 px and the bottom 340 px stay free of anything important: Instagram's own UI);
- flash (1080x1920; the breaking-news card: «فوری», the vendor, the OFFICIAL picture, the name, the time);
- thumb (1280x720; YouTube: 2–4 Persian words that read at 160 px wide, the hero, the Latin name).
"""
import base64
import html
import tempfile
import json
import os
import re
import sys

# ⟨2026-11-27⟩ the TYPE GATE (fa-type: after DotCoin's broken figures of F-0246): before the screenshot,
# Chrome's own report of the font that drew every glyph (a system-font fallback fails), text out of its box
# or over other text; a failing picture is not written (exit 2)
for _c in (os.environ.get("FATYPE", ""), "/home/studio/kits/fa-type",
           os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "fa-type")):
    if _c and os.path.exists(os.path.join(_c, "fatype.py")):
        sys.path.insert(0, _c)
        break
import fatype as F  # noqa: E402

COMMON = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FD = os.environ.get("BJ_FONTS", "/home/studio/kits/fonts-bj")
FP = os.environ.get("BJ_FONTS_PRO", "/home/studio/kits/fonts-pro")  # the owner's licensed IRANYekanX (the page's covers)
BG = os.path.join(COMMON, "cover", "background.jpg")  # the owner's cover background (2026-11-18)
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
PILLARS = {"repo": "#3CFFB5", "model": "#9B87FF", "news": "#FF4D5E", "tool": "#22D3EE", "trick": "#FFD166",
           "behind": "#FF5FA2", "explain": "#3D8BFF"}
PILLAR_FA = {"repo": "ریپوی روز", "model": "معرفی مدل", "news": "خبر داغ", "tool": "ابزار روز", "trick": "ترفند روز",
             "behind": "پشت صحنه", "explain": "ساده بگم"}
SIZE = {"cover": (1080, 1920), "story": (1080, 1920), "flash": (1080, 1920), "thumb": (1280, 720)}
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9 .:_/@#&+\-–×%$]*[A-Za-z0-9%$+)]|[A-Za-z]|\$?\d+(?:[.,]\d+)?[%×$]?(?=[^؀-ۿ]*[A-Za-z])")


def config():
    try:
        return json.load(open(os.path.join(COMMON, "brand", "config.json"), encoding="utf-8"))
    except OSError:
        return {}


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


# ⟨2026-11-19⟩ the owner: the page's ROUND profile logo beside every «behnamjalali.tech» handle (never a coloured dot);
# COMMON/brand/logo_round.png is made by COMMON/tools/make_logo.py from the real Instagram profile picture
LOGO_FILE = os.path.join(COMMON, "brand", "logo_round.png")


def logo_tag(px=44):
    """The round logo as an <img> beside the handle."""
    return (f'<img class="logo" alt="" src="data:image/png;base64,{b64(LOGO_FILE)}" '
            f'style="width:{px}px;height:{px}px">')


# ⟨2026-11-19⟩ the owner: a story's counter at the top right read «۷ از 12» (mixed digits, its order scrambled by
# bidi). A counter is «n از m»: ALL Persian digits, ONE right-to-left run, in the handle pill's own font.
COUNTER_IN = re.compile(r"^\s*([0-9۰-۹]{1,3})\s*(?:از|/|of)\s*([0-9۰-۹]{1,3})\s*$")
COUNTER_OUT = re.compile(r"^[۰-۹]{1,3} از [۰-۹]{1,3}$")


def check_counter(text):
    """A counter as it will be drawn: refused when it mixes digits or is not «n از m»."""
    if re.search(r"[0-9٠-٩]", text) or not COUNTER_OUT.fullmatch(text):
        raise ValueError(f"a counter must be «n از m» in Persian digits only, not {text!r}")
    return text


def counter(text):
    """«۷ از 12», «7/12», «7 of 12» -> «۷ از ۱۲» (checked)."""
    m = COUNTER_IN.match(str(text or ""))
    if not m:
        raise ValueError(f"a counter is «n از m» (e.g. «۷ از ۱۲»), not {text!r}")
    return check_counter(f"{m.group(1).translate(FA)} از {m.group(2).translate(FA)}")


def rich(text, keys=()):
    """Persian text as safe HTML: every Latin run isolated (never an RTL/LTR scramble), Persian digits outside
    Latin runs, key words in the spectrum."""
    s = str(text or "")
    out, last = [], 0
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9 .:_/@#&+\-–×%$']*[A-Za-z0-9%$+)']|[A-Za-z]", s):
        out.append(("fa", s[last:m.start()]))
        out.append(("en", m.group(0)))
        last = m.end()
    out.append(("fa", s[last:]))
    parts = []
    for kind, seg in out:
        if not seg:
            continue
        if kind == "en":
            parts.append(f'<bdi dir="ltr" class="en">{html.escape(seg)}</bdi>')
        else:
            parts.append(html.escape(seg.translate(FA)))
    h = "".join(parts)
    for k in keys or ():
        k = html.escape(str(k).translate(FA))
        if k and k in h:
            h = h.replace(k, f'<span class="spec">{k}</span>', 1)
    return h


def img_url(path):
    if not path:
        return ""
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "jpeg"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    return f"data:image/{mime};base64,{b64(path)}"


CSS = r"""
@font-face{font-family:EST;src:url(file://@@FD@@/Estedad-Medium.ttf);font-weight:500}
@font-face{font-family:EST;src:url(file://@@FD@@/Estedad-Bold.ttf);font-weight:700}
@font-face{font-family:EST;src:url(file://@@FD@@/Estedad-ExtraBold.ttf);font-weight:800}
@font-face{font-family:EST;src:url(file://@@FD@@/Estedad-Black.ttf);font-weight:900}
@font-face{font-family:GEI;src:url(file://@@FD@@/Geist-Medium.ttf);font-weight:500}
@font-face{font-family:GEI;src:url(file://@@FD@@/Geist-Bold.ttf);font-weight:700}
@font-face{font-family:GEI;src:url(file://@@FD@@/Geist-Black.ttf);font-weight:900}
@font-face{font-family:GMO;src:url(file://@@FD@@/GeistMono-Medium.ttf);font-weight:500}
@font-face{font-family:YKX;src:url(file://@@FP@@/IRANYekanXFaNum-ExtraBlack.ttf);font-weight:900}
@font-face{font-family:YKX;src:url(file://@@FP@@/IRANYekanXFaNum-Bold.ttf);font-weight:700}
.nv{font-family:YKX,EST,sans-serif}
.nv .en{font-family:GEI,YKX,sans-serif}
.nvbg{position:absolute;inset:0;background-size:cover;background-position:center}
.nvtitle{font-family:YKX,EST,sans-serif;font-weight:900;color:#fff;line-height:1.2;letter-spacing:-.5px;
  text-shadow:0 0 38px rgba(70,140,255,.5),0 0 12px rgba(120,180,255,.25),0 8px 26px rgba(0,0,0,.6)}
.nvtitle>div,.nvlatin{white-space:nowrap}
.nvbloom{position:absolute;border-radius:50%;background:radial-gradient(closest-side,rgba(60,150,255,.75),rgba(30,90,255,.35) 45%,rgba(20,60,200,0) 100%);
  filter:blur(8px);mix-blend-mode:screen}
.nvtitle .key,.nvkey{background:linear-gradient(180deg,#5CB8FF 0%,#2A86FF 55%,#1A5CFF 100%);-webkit-background-clip:text;
  background-clip:text;color:transparent;-webkit-text-fill-color:transparent;filter:drop-shadow(0 0 18px rgba(40,120,255,.55))}
.nvsub{font-family:YKX,EST,sans-serif;font-weight:700;color:#C9D6EA;text-shadow:0 2px 10px rgba(0,0,0,.6)}
.nvlatin{font-family:GEI,sans-serif;font-weight:900;direction:ltr;letter-spacing:-1px;
  background:linear-gradient(180deg,#FFFFFF 0%,#BFDDFF 45%,#3B8DFF 100%);-webkit-background-clip:text;background-clip:text;
  color:transparent;-webkit-text-fill-color:transparent;filter:drop-shadow(0 0 22px rgba(50,130,255,.5))}
.nvchip{display:inline-flex;align-items:center;gap:12px;padding:12px 28px;border-radius:999px;border:2px solid #2E7BFF;
  background:rgba(18,50,140,.45);box-shadow:0 0 22px rgba(46,123,255,.45),inset 0 0 12px rgba(46,123,255,.25);
  font-family:YKX,EST,sans-serif;font-weight:700;color:#fff;font-size:38px;line-height:1}
.nvel{position:absolute;mix-blend-mode:screen;object-fit:contain}  /* (no drop-shadow: it would outline the picture's box) */
.nvglyph{position:absolute;display:grid;place-items:center;font-family:GEI,sans-serif;font-weight:900;color:transparent;
  -webkit-text-stroke:5px #56B4FF;filter:drop-shadow(0 0 16px #2A86FF) drop-shadow(0 0 40px rgba(42,134,255,.7));direction:ltr}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:@@W@@;height:@@H@@;background:#05060A;overflow:hidden}
body{font-family:EST,GEI,sans-serif;color:#F2F4F8;direction:rtl;position:relative}
.en{font-family:GEI,EST,sans-serif;unicode-bidi:isolate}
.mono{font-family:GMO,monospace}
.spec{background:linear-gradient(100deg,#7B61FF,#3D8BFF 25%,#22D3EE 45%,#3CFFB5 62%,#FFD166 80%,#FF5FA2);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.bg{position:absolute;inset:0;background:
  radial-gradient(60% 40% at 18% 14%,@@ACC@@40,transparent 70%),
  radial-gradient(55% 35% at 88% 58%,#3D8BFF26,transparent 70%),
  radial-gradient(60% 35% at 35% 96%,#FF5FA21F,transparent 70%),#05060A}
.grain{position:absolute;inset:0;opacity:.07;mix-blend-mode:overlay;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.edge{position:absolute;inset:0;border-radius:0;padding:5px;background:conic-gradient(from 210deg,#7B61FF,#3D8BFF,#22D3EE,#3CFFB5,#FFD166,#FF5FA2,#7B61FF);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.95}
.edge.soft{filter:blur(14px);opacity:.75}
.glass{background:linear-gradient(180deg,rgba(22,25,38,.92),rgba(11,13,21,.94));border:1.6px solid rgba(255,255,255,.13);
  border-radius:38px;box-shadow:0 26px 70px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.18)}
.chip{display:inline-flex;align-items:center;gap:12px;padding:12px 26px;border-radius:999px;font-weight:700;
  border:1.6px solid @@ACC@@aa;background:rgba(255,255,255,.06);font-size:32px;line-height:1}
.dot{width:16px;height:16px;border-radius:50%;background:conic-gradient(#7B61FF,#22D3EE,#3CFFB5,#FFD166,#FF5FA2,#7B61FF);box-shadow:0 0 16px @@ACC@@}
.handle{position:absolute;display:flex;gap:14px;align-items:center;padding:8px 28px 8px 8px;border-radius:999px;
  background:rgba(12,14,22,.7);border:1.4px solid rgba(255,255,255,.13);font-family:GMO;font-size:28px;color:#C9CEDA;direction:ltr}
.logo{display:block;border-radius:50%;flex:0 0 auto}
.counter{position:absolute;display:flex;align-items:center;height:62px;padding:0 26px;border-radius:999px;
  background:rgba(12,14,22,.7);border:1.4px solid rgba(255,255,255,.13);font-family:GMO,EST,sans-serif;font-size:28px;
  color:#C9CEDA;direction:rtl;unicode-bidi:isolate}
.frame{position:absolute;overflow:hidden;border-radius:34px;border:2px solid rgba(255,255,255,.14);box-shadow:0 30px 80px rgba(0,0,0,.6);background:#0B0D15}
.frame img{width:100%;height:100%;display:block}
.frame.ring::after{content:"";position:absolute;inset:0;border-radius:34px;padding:4px;background:conic-gradient(from 120deg,#7B61FF,#22D3EE,#3CFFB5,#FFD166,#FF5FA2,#7B61FF);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
.title{font-weight:900;line-height:1.16;letter-spacing:-.5px;text-wrap:balance}
.body{font-weight:700;line-height:1.55;color:#DDE1EA}
.muted{color:#8B91A5}
.bloom{position:absolute;border-radius:50%;filter:blur(70px);background:@@ACC@@;opacity:.22}
.li{display:flex;gap:22px;align-items:flex-start;margin:0 0 26px}
.li b{flex:0 0 64px;height:64px;border-radius:20px;display:grid;place-items:center;font-size:34px;background:rgba(255,255,255,.07);border:1.4px solid @@ACC@@88}
"""


def keyed(path):
    """The hero as a PNG data URL, its near-black crushed to pure black and its edges feathered, so blended with
    `screen` on the navy background it shows no box (a picture's «black» is rarely #000)."""
    import io
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    im = Image.open(path).convert("RGB")
    lift = 26
    im = im.point(lambda v: 0 if v <= lift else int((v - lift) * 255 / (255 - lift)))
    w, h = im.size
    m = Image.new("L", (w, h), 0)
    pad = int(min(w, h) * .07)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, w - pad, h - pad), radius=pad * 2, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(pad * .8))
    im = ImageChops.multiply(im, Image.merge("RGB", (m, m, m)))
    # ⟨2026-11-18⟩ the coordinator: the hero fills the space under the title: its black margins are cut away
    lum = im.convert("L").point(lambda v: 255 if v > 38 else 0)
    box = lum.getbbox()
    if box:
        pw, ph = int((box[2] - box[0]) * .03), int((box[3] - box[1]) * .03)
        im = im.crop((max(0, box[0] - pw), max(0, box[1] - ph), min(w, box[2] + pw), min(h, box[3] + ph)))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def nv_title(spec, keys):
    """The title as lines: «|» breaks a line where the designer wants it; key words in the blue gradient."""
    lines = [x.strip() for x in str(spec.get("title") or "").split("|") if x.strip()]
    out = []
    for ln in lines:
        h = rich(ln)
        for k in keys or ():
            kk = html.escape(str(k).translate(FA))
            if kk and kk in h:
                h = h.replace(kk, f'<span class="key">{kk}</span>', 1)
        out.append(f"<div>{h}</div>")
    return "".join(out)


def navy(spec, w, h):
    """⟨2026-11-18⟩ The owner: «دقیقا عین کاور های قبلی ریلز هاش»: the page's own established cover family (its 24
    posts before the automation): the owner's navy background with its blue light lines and dot grids, a heavy
    Persian title in white with its key words in electric blue, a small grey line under it, sometimes a blue pill
    on top, and ONE glowing neon element (a 3D icon or illustration on black, blended so its black disappears)."""
    keys = spec.get("keys") or []
    bg = img_url(spec.get("background") or BG)
    el = keyed(spec["element"]) if spec.get("element") else ""
    # ⟨2026-11-18⟩ the coordinator's review: «A published cover must NEVER use a glyph fallback»: the hero is the cover
    glyph = html.escape(str(spec.get("element_text") or "")) if spec.get("draft") else ""
    if not el and not spec.get("draft"):
        raise SystemExit("a cover needs its hero picture (`element`: the neon 3D object on pure black); never a glyph")
    layout = spec.get("layout") or "top"
    thumb = spec.get("type") == "thumb"
    parts = [f'<div class="nvbg" style="background-image:url({bg})"></div>']
    if thumb:
        parts.append('<div style="position:absolute;inset:0;background:linear-gradient(270deg,rgba(2,6,20,.72) 0%,rgba(2,6,20,.35) 55%,rgba(2,6,20,0) 100%)"></div>')
        if el:
            parts.append(f'<div class="nvbloom" style="left:110px;top:560px;width:460px;height:120px"></div>')
            parts.append(f'<img class="nvel" src="{el}" style="left:10px;top:30px;width:660px;height:660px">')
        elif glyph:
            parts.append(f'<div class="nvglyph" style="left:60px;top:150px;width:520px;height:420px;font-size:250px">{glyph}</div>')
        y = 120
        box = [f'<div class="nvchip" style="font-size:26px">{rich(spec["chip"])}</div>'] if spec.get("chip") else []
        box.append(f'<div class="nvtitle" data-fit="{spec.get("fit", 600)}" data-max="{spec.get("px", 150)}" style="font-size:100px;margin-top:18px">{nv_title(spec, keys)}</div>')
        if spec.get("latin"):
            box.append(f'<div class="nvlatin" data-fit="{spec.get("latin_fit", 600)}" data-max="{spec.get("latin_px", 96)}" style="font-size:60px;margin-top:10px;text-align:right">{html.escape(spec["latin"])}</div>')
        if spec.get("sub"):
            box.append(f'<div class="nvsub" style="font-size:30px;margin-top:16px">{rich(spec["sub"])}</div>')
        parts.append(f'<div style="position:absolute;right:56px;top:{spec.get("top", 70)}px;width:{620 if (el or glyph) else 1150}px;text-align:right">{"".join(box)}</div>')
    elif layout == "split":
        # the text block on the left half, the element on the right (as «سریع‌تر کد بزن!» and «چجوری هنوز کد می‌زنه؟»)
        top = spec.get("top", 640)
        if el:
            parts.append(f'<div class="nvbloom" style="left:600px;top:{top + 560}px;width:420px;height:150px"></div>')
            parts.append(f'<img class="nvel" src="{el}" style="left:500px;top:{top - 220}px;width:580px;height:900px">')
        elif glyph:
            parts.append(f'<div class="nvglyph" style="left:580px;top:{top - 60}px;width:460px;height:560px;font-size:220px">{glyph}</div>')
        box = [f'<div class="nvsub" style="font-size:34px;margin-bottom:10px">{rich(spec["chip"])}</div>'] if spec.get("chip") else []
        box.append(f'<div class="nvtitle" data-fit="{spec.get("fit", 500)}" data-max="{spec.get("px", 170)}" style="font-size:120px">{nv_title(spec, keys)}</div>')
        if spec.get("sub"):
            box.append(f'<div class="nvsub" style="font-size:32px;margin-top:20px">{rich(spec["sub"])}</div>')
        parts.append(f'<div style="position:absolute;left:56px;top:{top}px;width:520px;text-align:right">{"".join(box)}</div>')
    else:
        # the title on top, centred; the element under it (the most common cover of the page)
        y = spec.get("top", 300)
        box = [f'<div style="margin-bottom:22px"><span class="nvchip">{rich(spec["chip"])}</span></div>'] if spec.get("chip") else []
        if spec.get("latin") and spec.get("latin_first"):
            box.append(f'<div class="nvlatin" data-fit="{spec.get("latin_fit", 900)}" data-max="{spec.get("latin_px", 170)}" style="font-size:110px;margin-bottom:6px">{html.escape(spec["latin"])}</div>')
        box.append(f'<div class="nvtitle" data-fit="{spec.get("fit", 900)}" data-max="{spec.get("px", 190)}" style="font-size:120px">{nv_title(spec, keys)}</div>')
        if spec.get("latin") and not spec.get("latin_first"):
            box.append(f'<div class="nvlatin" data-fit="{spec.get("latin_fit", 860)}" data-max="{spec.get("latin_px", 150)}" style="font-size:100px;margin-top:8px">{html.escape(spec["latin"])}</div>')
        if spec.get("sub"):
            box.append(f'<div class="nvsub" style="font-size:34px;margin-top:18px">{rich(spec["sub"])}</div>')
            box.append('<div style="margin:16px auto 0;width:150px;height:4px;border-radius:2px;background:linear-gradient(90deg,transparent,#2E7BFF,transparent);box-shadow:0 0 12px #2E7BFF"></div>')
        parts.append(f'<div id="nvhead" style="position:absolute;left:70px;right:70px;top:{y}px;text-align:center">{"".join(box)}</div>')
        ey, eh = spec.get("element_top", 880), spec.get("element_h", 820)
        if el:
            parts.append(f'<div class="nvbloom" data-follow="1" style="left:190px;top:{ey + eh - 170}px;width:700px;height:200px"></div>')
            parts.append(f'<img class="nvel" data-follow="1" src="{el}" style="left:20px;top:{ey}px;width:1040px;height:{eh}px">')
        elif glyph:
            parts.append(f'<div class="nvglyph" style="left:140px;top:{ey}px;width:800px;height:600px;font-size:340px">{glyph}</div>')
    return parts


def page(spec, w, h):
    cfg = config()
    pillar = spec.get("pillar") or "explain"
    acc = spec.get("accent") or PILLARS.get(pillar, "#3D8BFF")
    kind = spec.get("type", "story")
    css = (CSS.replace("@@FD@@", FD).replace("@@FP@@", FP).replace("@@W@@", f"{w}px").replace("@@H@@", f"{h}px")
           .replace("@@ACC@@", acc))
    keys = spec.get("keys") or []
    kicker = spec.get("kicker") or PILLAR_FA.get(pillar, "")
    handle = cfg.get("handle", "behnamjalali.tech")
    image = img_url(spec.get("image")) if spec.get("image") else ""
    fit = spec.get("fit") or "cover"
    parts = ['<div class="bg"></div>']
    if kind in ("cover", "thumb") and not spec.get("lumen"):
        parts = navy(spec, w, h) + ['<div class="grain" style="opacity:.04"></div>']
        return (f'<!doctype html><html lang="fa"><head><meta charset="utf-8"><style>{css}</style></head>'
                f'<body class="nv">{"".join(parts)}</body></html>')
    if kind == "thumb":
        # YouTube 1280x720: words on the right (RTL), the hero on the left, the spectral edge
        parts.append(f'<div class="bloom" style="width:520px;height:520px;left:60px;top:120px"></div>')
        if image:
            parts.append(f'<div class="frame ring" style="left:56px;top:110px;width:560px;height:500px"><img src="{image}" style="object-fit:{fit}"></div>')
        parts.append(f'<div style="position:absolute;right:56px;top:96px;width:{620 if image else 1160}px">'
                     f'<div class="chip" style="font-size:26px"><span class="dot"></span>{rich(kicker)}</div>'
                     f'<div class="title" style="font-size:{spec.get("px", 104)}px;margin-top:34px">{rich(spec.get("title"), keys)}</div>'
                     + (f'<div class="en" style="font-weight:900;font-size:54px;margin-top:22px;direction:ltr;text-align:right"><span class="spec">{html.escape(spec["latin"])}</span></div>' if spec.get("latin") else "")
                     + "</div>")
        parts.append('<div class="edge"></div>')
    elif kind == "flash":
        t = spec.get("time", "")
        parts.append('<div class="bloom" style="width:760px;height:760px;left:160px;top:520px;background:#FF4D5E;opacity:.18"></div>')
        parts.append(f'<div class="handle" style="top:150px;left:50%;transform:translateX(-50%)">{logo_tag()}{html.escape(handle)}</div>')
        parts.append('<div style="position:absolute;top:262px;left:0;right:0;text-align:center">'
                     '<div class="chip" style="border-color:#FF4D5E;background:rgba(255,77,94,.14);font-size:40px;padding:16px 34px">'
                     '<span style="width:18px;height:18px;border-radius:50%;background:#FF4D5E;box-shadow:0 0 22px #FF4D5E"></span>فوری'
                     + (f' <span class="mono" style="font-size:30px;color:#FFB3BA;direction:ltr">· {html.escape(t)}</span>' if t else "")
                     + "</div></div>")
        if spec.get("chip"):
            parts.append(f'<div style="position:absolute;top:372px;left:0;right:0;text-align:center"><div class="chip" style="font-size:30px">{rich(spec["chip"])}</div></div>')
        if image:
            parts.append(f'<div class="frame ring" style="left:60px;right:60px;top:470px;height:560px"><img src="{image}" style="object-fit:{fit}"></div>')
        if spec.get("latin"):
            parts.append(f'<div class="en" style="position:absolute;top:1080px;left:60px;right:60px;text-align:center;direction:ltr;font-weight:900;font-size:{spec.get("latin_px", 92)}px;line-height:1.05"><span class="spec">{html.escape(spec["latin"])}</span></div>')
        parts.append(f'<div class="title" style="position:absolute;top:{1230 if spec.get("latin") else 1090}px;left:70px;right:70px;text-align:center;font-size:{spec.get("px", 66)}px">{rich(spec.get("title"), keys)}</div>')
        if spec.get("source"):
            parts.append(f'<div class="mono muted" style="position:absolute;top:1530px;left:0;right:0;text-align:center;font-size:26px;direction:ltr">source: {html.escape(spec["source"])}</div>')
        parts.append('<div class="edge" style="background:conic-gradient(from 200deg,#FF4D5E,#FF8A5B,#FFD166,#FF4D5E 60%,#7B61FF,#FF4D5E)"></div>')
    else:
        # cover and story: the handle on top, the kicker chip, the hero, the title, the body
        top = 150
        parts.append(f'<div class="handle" style="top:{top}px;left:50%;transform:translateX(-50%)">{logo_tag()}{html.escape(handle)}</div>')
        if kind == "cover":
            # the grid's 4:5 window is y 285..1635: everything that matters is inside it
            parts.append('<div class="bloom" style="width:820px;height:820px;left:130px;top:520px"></div>')
            parts.append(f'<div style="position:absolute;top:330px;left:0;right:0;text-align:center"><div class="chip"><span class="dot"></span>{rich(kicker)}</div></div>')
            if image:
                parts.append(f'<div class="frame ring" style="left:90px;right:90px;top:430px;height:{spec.get("image_h", 620)}px"><img src="{image}" style="object-fit:{fit}"></div>')
            y = 430 + (spec.get("image_h", 620) + 50 if image else 120)
            if spec.get("latin"):
                parts.append(f'<div class="en" style="position:absolute;top:{y}px;left:60px;right:60px;text-align:center;direction:ltr;font-weight:900;font-size:{spec.get("latin_px", 88)}px;line-height:1.05"><span class="spec">{html.escape(spec["latin"])}</span></div>')
                y += spec.get("latin_px", 88) + 40
            parts.append(f'<div class="title" style="position:absolute;top:{y}px;left:70px;right:70px;text-align:center;font-size:{spec.get("px", 104)}px">{rich(spec.get("title"), keys)}</div>')
            parts.append('<div class="edge soft"></div><div class="edge" style="opacity:.6"></div>')
        else:
            layout = spec.get("layout") or ("hero" if image else "list")
            if spec.get("badge"):
                parts.append(f'<div class="counter" style="top:{top}px;right:64px"><bdi dir="rtl">{html.escape(counter(spec["badge"]))}</bdi></div>')
            parts.append(f'<div style="position:absolute;top:270px;left:0;right:0;text-align:center"><div class="chip"><span class="dot"></span>{rich(kicker)}</div></div>')
            y = 380
            if layout == "stat" and spec.get("stat"):
                parts.append(f'<div class="bloom" style="width:700px;height:700px;left:190px;top:330px"></div>')
                parts.append(f'<div style="position:absolute;top:{y + 40}px;left:0;right:0;text-align:center;font-weight:900;font-size:{spec.get("stat_px", 250)}px;line-height:1"><span class="spec">{rich(spec["stat"])}</span></div>')
                if spec.get("stat_label"):
                    parts.append(f'<div class="muted" style="position:absolute;top:{y + 330}px;left:80px;right:80px;text-align:center;font-weight:700;font-size:40px">{rich(spec["stat_label"])}</div>')
                y += 460
            elif image and layout in ("hero", "split"):
                hh = spec.get("image_h", 640 if layout == "hero" else 520)
                parts.append(f'<div class="frame ring" style="left:64px;right:64px;top:{y}px;height:{hh}px"><img src="{image}" style="object-fit:{fit}"></div>')
                y += hh + 54
            if spec.get("latin"):
                parts.append(f'<div class="en" style="position:absolute;top:{y}px;left:60px;right:60px;text-align:center;direction:ltr;font-weight:900;font-size:{spec.get("latin_px", 78)}px;line-height:1.05"><span class="spec">{html.escape(spec["latin"])}</span></div>')
                y += spec.get("latin_px", 78) + 34
            px = spec.get("px", 74 if layout != "quote" else 68)
            parts.append(f'<div class="title" style="position:absolute;top:{y}px;left:72px;right:72px;text-align:{"right" if layout == "list" else "center"};font-size:{px}px">{rich(spec.get("title"), keys)}</div>')
            y += int(px * 1.2 * max(1, min(3, len(str(spec.get("title") or "")) // 16 + 1))) + 40
            box = []
            for line in spec.get("body") or []:
                box.append(f'<div class="body" style="font-size:{spec.get("body_px", 40)}px;margin-bottom:12px">{rich(line, keys)}</div>')
            for i, line in enumerate(spec.get("list") or [], 1):
                box.append(f'<div class="li"><b>{str(i).translate(FA)}</b><div class="body" style="font-size:{spec.get("body_px", 40)}px">{rich(line, keys)}</div></div>')
            if box:
                parts.append(f'<div class="glass" style="position:absolute;top:{y}px;left:64px;right:64px;padding:44px 50px 34px">{"".join(box)}</div>')
            bottom = []
            if spec.get("cta"):
                bottom.append(f'<div class="body" style="font-size:36px;color:#C9CEDA">{rich(spec["cta"])}</div>')
            if spec.get("word"):
                bottom.append(f'<div style="margin-top:18px"><div class="chip" style="font-size:44px;padding:16px 40px;border-width:2.5px"><span class="spec">{rich(spec["word"])}</span></div></div>')
            if bottom:
                parts.append(f'<div style="position:absolute;bottom:360px;left:60px;right:60px;text-align:center">{"".join(bottom)}</div>')
            if spec.get("source"):
                parts.append(f'<div class="mono muted" style="position:absolute;bottom:318px;left:0;right:0;text-align:center;font-size:22px;direction:ltr">source: {html.escape(spec["source"])}</div>')
            parts.append('<div class="edge" style="opacity:.35"></div>')
    parts.append('<div class="grain"></div>')
    return f'<!doctype html><html lang="fa"><head><meta charset="utf-8"><style>{css}</style></head><body>{"".join(parts)}</body></html>'


FIT_JS = """() => { document.querySelectorAll('[data-fit]').forEach(el => {
  const target = +el.dataset.fit, max = +el.dataset.max;
  const width = () => { const kids = el.children.length ? [...el.children] : [el];
    return Math.max(...kids.map(c => { const r = document.createRange(); r.selectNodeContents(c); return r.getBoundingClientRect().width; })); };
  let px = parseFloat(getComputedStyle(el).fontSize);
  for (let i = 0; i < 5; i++) { const w = width(); if (!w) break; px = Math.min(max, px * target / w); el.style.fontSize = px + 'px'; }
});
  const head = document.getElementById('nvhead');
  const hero = document.querySelector('img.nvel[data-follow]'), bloom = document.querySelector('.nvbloom[data-follow]');
  if (head && hero && hero.naturalWidth) {
    // ⟨2026-11-18⟩ the hero fills the free area under the text block: 78 % of the width (up to 95 % to fill its
    // height), centred in it, never more than 120 px below the text; its bloom on its base
    const W = innerWidth, freeTop = head.getBoundingClientRect().bottom + 24, freeBot = innerHeight - 70;
    const freeH = freeBot - freeTop, ar = hero.naturalHeight / hero.naturalWidth;
    let w = W * .78, h = w * ar;
    if (h > freeH) { h = freeH; w = h / ar; } else { w = Math.min(W * .95, freeH / ar); h = w * ar; }
    let top = freeTop + (freeH - h) / 2;
    if (top - freeTop > 60) top = freeTop + 60;  // (the picture's own glow adds ~40 px: the eye's gap stays under ~120)
    Object.assign(hero.style, {left: ((W - w) / 2) + 'px', top: top + 'px', width: w + 'px', height: h + 'px'});
    if (bloom) Object.assign(bloom.style, {left: ((W - w * .7) / 2) + 'px', width: (w * .7) + 'px',
                                           top: (top + h * .82) + 'px', height: (h * .2) + 'px'});
  }
}"""


def render(specs, outs):
    from playwright.sync_api import sync_playwright
    failed = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--disable-gpu", "--allow-file-access-from-files"])
        try:
            for spec, out in zip(specs, outs):
                w, h = SIZE.get(spec.get("type", "story"), (1080, 1920))
                pg = b.new_page(viewport={"width": w, "height": h})
                # (the page is written beside the system's temp files, never into out/: a package holds only its files)
                tmp = os.path.join(tempfile.gettempdir(), f"bjcard-{os.getpid()}-{os.path.basename(out)}.html")
                open(tmp, "w", encoding="utf-8").write(page(spec, w, h))
                pg.goto("file://" + os.path.abspath(tmp))
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(150)
                pg.evaluate(FIT_JS)
                pg.wait_for_timeout(100)
                over = pg.evaluate("""() => [...document.querySelectorAll('.title,.body,.chip,.en,.nvtitle,.nvsub,.nvchip,.nvlatin')].filter(e =>
                    e.scrollWidth > e.clientWidth + 2 || e.getBoundingClientRect().right > innerWidth + 1 ||
                    e.getBoundingClientRect().left < -1 || e.getBoundingClientRect().bottom > innerHeight + 1).map(e => e.textContent.slice(0, 40))""")
                if over or not F.guard(pg, out, "bjtech-common/card", numbers="any", overlap=False):
                    failed.append(out)
                    pg.close()
                    os.remove(tmp)
                    print(out, "NOT WRITTEN:", "overflow:" if over else "type gate", *(over or []))
                    continue
                pg.screenshot(path=out, type="jpeg", quality=93)
                pg.close()
                os.remove(tmp)
                print(out, "ok")
        finally:
            b.close()
    if failed:
        sys.exit(f"{len(failed)} card(s) failed (overflow or the type gate) and were not written: fix their text")


def sheet(folder, out):
    from PIL import Image
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png")))
    ims = [Image.open(os.path.join(folder, f)).convert("RGB") for f in files]
    if not ims:
        sys.exit("no pictures")
    tw = 270
    th = int(tw * ims[0].height / ims[0].width)
    cols = min(6, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 8) + 8), (30, 30, 34))
    for i, im in enumerate(ims):
        sh.paste(im.resize((tw, th)), (8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 8)))
    sh.save(out, quality=88)
    print(out, len(ims), "cards")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "--sheet":
        return sheet(a[1], a[2])
    if a[0] == "--many":
        specs = json.load(open(a[1], encoding="utf-8"))
        os.makedirs(a[2], exist_ok=True)
        return render(specs, [os.path.join(a[2], (s.get("name") or f"card_{i + 1}") + ".jpg") for i, s in enumerate(specs)])
    render([json.load(open(a[0], encoding="utf-8"))], [a[1]])


if __name__ == "__main__":
    main()
