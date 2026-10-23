"""The render page's harness: the internal origin the composition is served
from, what that origin answers (and that everything else is aborted and
recorded), the strict CSP, and the scripts the hub injects (a virtual clock
installed before any page script, the overlay page). Pure: render.py drives
Chromium with it.

The origin is fictitious and resolves nowhere (and the container has no
network at all): every request is answered by Playwright's route() from the
image or the job's own files, or aborted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ORIGIN = "https://render.hq.invalid"
COMPOSITION_PATH = "/composition"
LOTTIE_PATH = "/lottie"
OVERLAY_PATH = "/overlay"
ASSET = re.compile(r"^/assets/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
LIBS = {"/lib/anime.min.js": "anime.min.js", "/lib/lottie.min.js": "lottie.min.js"}
FONT_FILES = {
    "/fonts/IRANYekanX-Regular.woff2": ("IRANYekanX-Regular.woff2", 400),
    "/fonts/IRANYekanX-Medium.woff2": ("IRANYekanX-Medium.woff2", 500),
    "/fonts/IRANYekanX-DemiBold.woff2": ("IRANYekanX-DemiBold.woff2", 600),
    "/fonts/IRANYekanX-Bold.woff2": ("IRANYekanX-Bold.woff2", 700),
}
CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; media-src 'self'; connect-src 'none'; "
    "worker-src 'none'; frame-src 'none'; child-src 'none'; object-src 'none'; "
    "manifest-src 'none'; base-uri 'none'; form-action 'none'"
)
FONT_FACES = "\n".join(
    f"@font-face {{ font-family: IRANYekanX; font-weight: {w}; font-style: normal; "
    f"font-display: block; src: url('{path}') format('woff2'); }}"
    for path, (_, w) in FONT_FILES.items()
)


@dataclass(frozen=True)
class Answer:
    """What the route answers: a file to serve, or an abort (a violation
    unless it is a harmless browser request)."""

    kind: str  # "composition" | "lottie" | "overlay" | "lib" | "font" | "asset" | "abort"
    path: str | None = None
    mime: str | None = None
    violation: bool = True


def decide(url: str, assets: dict[str, tuple[str, str]], lib_dir: Path, font_dir: Path) -> Answer:
    """The route's decision for one request. `assets`: file id -> (path, mime)
    of this job's files only."""
    if url.startswith("data:") or url == "about:blank":
        return Answer("abort", violation=False)  # never routed by Chromium; kept total
    parts = urlsplit(url)
    if f"{parts.scheme}://{parts.netloc}" != ORIGIN or parts.query or parts.fragment:
        return Answer("abort")
    path = parts.path
    if path == COMPOSITION_PATH:
        return Answer("composition", mime="text/html; charset=utf-8")
    if path == LOTTIE_PATH:
        return Answer("lottie", mime="text/html; charset=utf-8")
    if path == OVERLAY_PATH:
        return Answer("overlay", mime="text/html; charset=utf-8")
    if path in LIBS:
        return Answer("lib", str(lib_dir / LIBS[path]), "text/javascript; charset=utf-8")
    if path in FONT_FILES:
        return Answer("font", str(font_dir / FONT_FILES[path][0]), "font/woff2")
    if path == "/favicon.ico":
        return Answer("abort", violation=False)
    m = ASSET.match(path)
    if m and m.group(1) in assets:
        file, mime = assets[m.group(1)]
        return Answer("asset", file, mime)
    return Answer("abort")


# Installed before any script of the page (Playwright add_init_script): time
# is a function of the frame being drawn, never of the wall clock.
CLOCK_JS = r"""
(() => {
  const T0 = 1767225600000;               // 2026-01-01T00:00:00Z, the page's fixed "now"
  let now = 0;                            // virtual milliseconds since the first frame
  let nextId = 1;
  const timers = new Map();
  const frames = new Map();
  const RealDate = Date;
  const realSetTimeout = window.setTimeout.bind(window);  // the harness's own waits only
  class HqDate extends RealDate {
    constructor(...a) { if (a.length === 0) { super(T0 + now); } else { super(...a); } }
    static now() { return T0 + now; }
  }
  window.Date = HqDate;
  Object.defineProperty(performance, 'now', { value: () => now, configurable: false });
  window.setTimeout = (fn, ms, ...args) => {
    const id = nextId++;
    timers.set(id, { at: now + Math.max(0, Number(ms) || 0), fn, args, every: 0 });
    return id;
  };
  window.setInterval = (fn, ms, ...args) => {
    const id = nextId++;
    const every = Math.max(1, Number(ms) || 0);
    timers.set(id, { at: now + every, fn, args, every });
    return id;
  };
  window.clearTimeout = window.clearInterval = (id) => { timers.delete(id); };
  window.requestAnimationFrame = (cb) => { const id = nextId++; frames.set(id, cb); return id; };
  window.cancelAnimationFrame = (id) => { frames.delete(id); };
  let seed = 0x2f6b3a91;                  // a seeded random: the same frames every render
  Math.random = () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const starts = new WeakMap();
  window.__hqLottie = [];
  window.__hqSeek = async (t) => {
    for (let guard = 0; guard < 10000; guard++) {
      let due = null;
      for (const [id, tm] of timers) {
        if (tm.at <= t && (!due || tm.at < due[1].at)) due = [id, tm];
      }
      if (!due) break;
      now = due[1].at;
      if (due[1].every) { due[1].at += due[1].every; } else { timers.delete(due[0]); }
      try {
        if (typeof due[1].fn === 'function') due[1].fn(...due[1].args);
      } catch (e) { /* the page's own error */ }
    }
    now = t;
    const cbs = [...frames.values()];
    frames.clear();
    for (const cb of cbs) { try { cb(now); } catch (e) { /* the page's own error */ } }
    for (const a of document.getAnimations()) {
      if (!starts.has(a)) starts.set(a, t);
      a.pause();
      a.currentTime = Math.max(0, t - starts.get(a));
    }
    for (const l of window.__hqLottie) {
      try { l.goToAndStop(t, false); } catch (e) { /* bad data */ }
    }
    for (const s of document.querySelectorAll('svg')) {   // SMIL runs on each root svg's own clock
      if (s.ownerSVGElement === null && typeof s.setCurrentTime === 'function') {
        s.pauseAnimations(); s.setCurrentTime(t / 1000);
      }
    }
    const vids = [...document.querySelectorAll('video')];
    await Promise.all(vids.map((v) => new Promise((ok) => {
      v.muted = true; v.pause();
      const want = Math.min(t / 1000, Number.isFinite(v.duration) ? v.duration : t / 1000);
      if (Math.abs(v.currentTime - want) < 0.001) { ok(); return; }
      const done = () => { v.removeEventListener('seeked', done); ok(); };
      v.addEventListener('seeked', done);
      realSetTimeout(done, 1000);
      try { v.currentTime = want; } catch (e) { done(); }
    })));
  };
})();
"""

LOTTIE_PAGE = """<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}
#stage{width:100vw;height:100vh}</style>
<script src="/lib/lottie.min.js"></script></head>
<body><div id="stage"></div></body></html>"""

LOTTIE_START_JS = """(data) => {
  const anim = lottie.loadAnimation({container: document.getElementById('stage'), renderer: 'svg',
    loop: false, autoplay: false, animationData: data,
    rendererSettings: {preserveAspectRatio: 'xMidYMid meet'}});
  window.__hqLottie.push(anim);
  return new Promise((ok) => {
    if (anim.isLoaded) ok(); else anim.addEventListener('DOMLoaded', () => ok());
  });
}"""

# The hub's overlay page: captions, mark and call to action, drawn into a
# transparent page and laid over the frames by ffmpeg. The composition never
# sees it, so it can neither hide nor change them. Text goes in as text.
OVERLAY_PAGE = f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>{FONT_FACES}
html,body{{margin:0;padding:0;background:transparent;overflow:hidden;font-family:IRANYekanX}}
.cap{{position:absolute;display:flex;align-items:flex-end;justify-content:center}}
.cap span{{background:rgba(0,0,0,.58);color:#fff;font-weight:600;line-height:1.5;padding:.15em .6em;
  border-radius:.4em;text-align:center;direction:rtl;unicode-bidi:plaintext;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;box-decoration-break:clone}}
.cta{{position:absolute;display:flex;align-items:center;justify-content:flex-end}}
.cta span{{color:#fff;font-weight:700;padding:.35em .9em;border-radius:999px;white-space:nowrap}}
.mark{{position:absolute}}</style></head>
<body></body></html>"""

OVERLAY_JS = """(o) => {
  document.body.replaceChildren();
  const px = (v) => `${v}px`;
  if (o.caption) {
    const box = document.createElement('div');
    box.className = 'cap';
    Object.assign(box.style, {left: px(o.caption.x), top: px(o.caption.y), width: px(o.caption.w),
                              height: px(o.caption.h)});
    const s = document.createElement('span');
    s.style.fontSize = px(o.caption.font);
    s.textContent = o.caption.text;
    box.appendChild(s);
    document.body.appendChild(box);
  }
  if (o.cta) {
    const box = document.createElement('div');
    box.className = 'cta';
    Object.assign(box.style, {left: px(o.cta.x), top: px(o.cta.y), width: px(o.cta.w),
                              height: px(o.cta.h)});
    const s = document.createElement('span');
    s.style.fontSize = px(o.cta.font);
    s.style.background = o.cta.color;
    s.textContent = o.cta.text;
    box.appendChild(s);
    document.body.appendChild(box);
  }
  if (o.mark) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'mark');
    svg.setAttribute('viewBox', o.mark.vb);
    svg.setAttribute('width', String(o.mark.w));
    svg.setAttribute('height', String(o.mark.h));
    Object.assign(svg.style, {left: px(o.mark.x), top: px(o.mark.y)});
    for (const l of o.mark.layers) {
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', l.d);
      p.setAttribute('fill', l.color);
      p.setAttribute('fill-rule', 'evenodd');
      svg.appendChild(p);
    }
    document.body.appendChild(svg);
  }
  return document.fonts.ready.then(() => true);
}"""

FONTS_READY_JS = """() => Promise.all(['400', '500', '600', '700'].map(
  (w) => document.fonts.load(`${w} 48px IRANYekanX`, 'آزمون ۱۲۳')))
  .then(() => document.fonts.ready).then(() => true)"""
