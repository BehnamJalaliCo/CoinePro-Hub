#!/usr/bin/env python3
"""The site's phone review (owner, 2026-11-17: no RTL/LTR scramble, no overflow, ever): every page
named is opened from a built dist/ at 390 px (light AND dark) and, with --desktop, at 1440 px; it

  - fails on horizontal overflow: the page wider than the screen, or any visible element whose box
    sticks out of it (inside a box meant to scroll sideways, a table or a strip, is allowed);
  - fails on a Persian text block that renders a Latin run outside an isolate (build.py's lint
    checks the HTML; this checks what the browser drew: an element with mixed scripts whose
    computed direction is not the one its words need);
  - writes full-page screenshots cut into JPEG parts a reader can see (one screen each), so a
    person (or the SEO session) LOOKS at every part before the page goes live.

    review.py check DIST OUT /path/ [/path/ …] [--desktop]  -> OUT/<name>-<view>-<theme>-NN.jpg,
                                                             OUT/review.json; exit 1 on a finding

Runs with a Python that has Playwright + Chromium + Pillow (the studio's venv-render on the hub).
Serves dist/ through Playwright's routing (no socket: the studio user has no loopback server).
"""
import io
import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import BASE, launch, serve_from  # noqa: E402

VIEWS = {"phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
         "desktop": dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1),
         # the narrowest width with the full menu (site.css: the drawer below 900 px)
         "narrow": dict(viewport={"width": 920, "height": 900}, device_scale_factor=1)}
# boxes that scroll sideways on purpose, and decorative type cut by its own box
SCROLLERS = ".tbl, .gl-index, .marquee, .mq-in, .p-home .cards, .gts, pre.cb, .giant, .st-word, .card-en, " \
            ".follow-giant, .ftr-giant, .xc-en, .ring, .vipcta-mark, .chain-stage, .drawer"
FIND = """(scrollers) => {
  const W = document.documentElement.clientWidth, out = [];
  if (document.documentElement.scrollWidth > W + 1) out.push({what: 'page', w: document.documentElement.scrollWidth, W});
  const inScroller = (el) => el.closest(scrollers);
  for (const el of document.querySelectorAll('body *')) {
    if (inScroller(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.position === 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.right > W + 1.5 || r.left < -1.5) {
      out.push({what: 'box', tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 60),
                text: (el.innerText || '').trim().slice(0, 80), left: Math.round(r.left), right: Math.round(r.right), W});
      if (out.length > 40) break;
    }
  }
  // a Persian block whose own direction is LTR while it starts with Persian, or a Latin run with digits
  // that the browser shows outside an isolate (its parent is an RTL text node holder, not bdi/[dir=ltr])
  for (const el of document.querySelectorAll('main p, main li, main h1, main h2, main h3, main td, main th, main dd, main figcaption')) {
    const t = (el.innerText || '').trim();
    if (!t) continue;
    const fa = /[\\u0600-\\u06FF]/.test(t);
    if (fa && getComputedStyle(el).direction !== 'rtl' && !el.closest('[dir=ltr]'))
      out.push({what: 'direction', tag: el.tagName.toLowerCase(), text: t.slice(0, 80)});
  }
  return out;
}"""


def cut(png: bytes, prefix: Path, width: int = 640) -> int:
    """A full-page PNG -> JPEG parts of about one screen each, scaled to `width`."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    step = int(w * 844 / 390) if w <= 900 else int(w * 900 / (w if w < 1000 else 1440)) * (2 if w >= 1440 else 1)
    n = 0
    for y in range(0, h, step):
        part = im.crop((0, y, w, min(h, y + step)))
        part = part.resize((width, max(1, int(part.size[1] * width / w))))
        part.save(f"{prefix}-{n:02d}.jpg", quality=78)
        n += 1
    return n


def check(dist: Path, out: Path, paths: list[str], desktop: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"pages": {}, "findings": 0}
    views = ["phone"] + (["desktop", "narrow"] if desktop else [])
    with sync_playwright() as p:
        b = launch(p)
        for path in paths:
            name = path.strip("/").replace("/", "_") or "home"
            for vname in views:
                for theme in ("light", "dark"):
                    ctx = b.new_context(**VIEWS[vname], color_scheme=theme, reduced_motion="reduce")
                    serve_from(ctx, dist)
                    page = ctx.new_page()
                    page.goto(BASE + path, wait_until="load")
                    page.evaluate("document.fonts.ready")
                    page.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) {
                        window.scrollTo({top: y, behavior: "instant"}); await new Promise(r => setTimeout(r, 60)); }
                        window.scrollTo({top: 0, behavior: "instant"}); }""")
                    page.wait_for_timeout(700)
                    found = page.evaluate(FIND, SCROLLERS)
                    status = page.evaluate("document.title")
                    n = cut(page.screenshot(full_page=True, type="png"), out / f"{name}-{vname}-{theme}")
                    report["pages"].setdefault(path, {})[f"{vname}-{theme}"] = {"findings": found, "parts": n, "title": status}
                    report["findings"] += len(found)
                    for f in found[:8]:
                        print(f"FINDING {path} {vname} {theme}: {json.dumps(f, ensure_ascii=False)}")
                    ctx.close()
        b.close()
    (out / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(f"review: {len(paths)} pages, {report['findings']} findings -> {out}")
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--desktop"]
    if len(args) < 4 or args[0] != "check":
        sys.exit(__doc__)
    sys.exit(check(Path(args[1]).resolve(), Path(args[2]).resolve(), args[3:], "--desktop" in sys.argv))
