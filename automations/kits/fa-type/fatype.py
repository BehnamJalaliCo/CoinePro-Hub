# -*- coding: utf-8 -*-
"""fa-type — Persian typography for every page's drawn text (2026-11-27).

Born from DotCoin's stories of 2026-11-27 (F-0246): the session's own improvised slides set their big
figures in a font stack the page never loaded, so Chromium drew them in a SYSTEM font: Persian zeros as
heavy squares, «٬» as an apostrophe («۵’■■■»), «٫» like «ر», and a highlighted «۱۲ از ۱۰۰» ran out of
its chip. The owner: «با فونت خراب … این اشتباه ها تکرار نشه». Nothing checked it.

This module is the one place for:
  * the NUMBER RULES (`num`, `fa`, `normalize`) and the text LINT (`lint`);
  * the RENDER GATE (`gate`): after the fonts load, Chrome itself says which font drew every text
    node (CDP CSS.getPlatformFontsForNode). Any glyph drawn by a system font (a fallback) fails, any
    @font-face that failed to load fails, any text outside its box / chip / the canvas / a calm band
    fails, any text that breaks the number rules fails;
  * `render`: open an HTML page in the kits' Chromium, gate it, and only then write the picture.
    A failing page writes NOTHING (exit 2 from the tools), so a broken picture cannot be delivered.

Every kit tool that draws text imports it:
    sys.path.insert(0, "/home/studio/kits/fa-type"); import fatype
The rules are in /home/studio/kits/fa-type/README.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_TO_FA = str.maketrans("0123456789٠١٢٣٤٥٦٧٨٩", FA_DIGITS * 2)
THOU = "٬"  # «٬» ARABIC THOUSANDS SEPARATOR: IRANYekanX / Estedad draw it as a clean low comma
# decimals: «/» — the Persian press's decimal mark, drawn the same by every font. «٫» (U+066B) is not used:
# AnjomanMax (bitmart) and Estedad (bjtech) draw it as a descending hook that reads like «ر», IRANYekanX
# Medium as a comma (seen 2026-11-27, fa-type/README.md)
DEC = "/"
MINUS = "−"
LRI, PDI = "⁦", "⁩"
DIG = "0-9۰-۹٠-٩"

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
GATE_LOG = "qc/type_gate.jsonl"  # every gated picture: its sha256, its verdict (relative to the cwd)


# ------------------------------------------------------------------------------------- numbers --
def fa(s: Any) -> str:
    """Latin and Arabic-Indic digits → Persian digits (nothing else changes)."""
    return str(s).translate(_TO_FA)


def group(int_digits: str) -> str:
    """The thousands rule: up to 4 digits NO separator («۵۰۰۰», «۲۰۲۶»); 5 digits or more, «٬» every
    three («۶۰٬۴۸۰», «۱٬۲۵۰٬۰۰۰»). (A 4-digit amount beside a 5-digit one in the same table may take
    «٬» too: pass group4=True to `num`.)"""
    d = int_digits
    if len(d) <= 4:
        return d
    out = []
    while d:
        out.append(d[-3:])
        d = d[:-3]
    return THOU.join(reversed(out))


def num(x: Any, decimals: int | None = None, *, group4: bool = False, pct: bool = False) -> str:
    """One figure in Persian by the rules: Persian digits, the thousands rule, «/» for decimals,
    «٪» right after the number (Persian order). No sign: say up/down in words or with ▲/▼ and the
    meaning colour (a «-» beside a Persian figure flips with the text direction)."""
    if isinstance(x, str):
        x = float(x.replace(",", "").replace(THOU, "").replace(DEC, ".").replace("\u066b", ".").translate(
            str.maketrans(FA_DIGITS, "0123456789")))
    v = abs(float(x))
    s = f"{v:.{decimals}f}" if decimals is not None else (f"{v:.0f}" if float(v).is_integer() else f"{v}")
    ip, _, dp = s.partition(".")
    ip = fa(ip)
    if group4 and len(ip) == 4:
        ip = ip[0] + THOU + ip[1:]
    else:
        ip = group(ip)
    out = ip + (DEC + fa(dp) if dp else "")
    return out + ("٪" if pct else "")


_RUN = re.compile(rf"[{DIG}]+(?:[,٬،’'‘`.٫][{DIG}]+)*")


def normalize(text: str) -> str:
    """A string's figures put right: Persian digits; «٬ , ، ’ '» between digit groups re-grouped by
    the thousands rule; «.» or «٫» before the last group of digits = the decimal «/». An existing «/»
    is left alone (a decimal already, or a date)."""

    def fix(m: re.Match[str]) -> str:
        run = m.group(0)
        parts = re.split(r"([,٬،’'‘`.٫])", run)
        seps = parts[1::2]
        nums = parts[0::2]
        dec_at = next((i for i, sp in enumerate(seps) if sp in ".٫"), None)
        if dec_at is not None and dec_at == len(seps) - 1:
            ip, dp = "".join(nums[: dec_at + 1]), nums[-1]
        elif dec_at is None and all(len(n) == 3 for n in nums[1:]):
            ip, dp = "".join(nums), ""
        else:
            return fa(run)  # not a number we can read safely: digits only
        return group(fa(ip)) + (DEC + fa(dp) if dp else "")

    return _RUN.sub(fix, fa(text))


_LINT = [
    (re.compile(r"[0-9]"), "Latin digit in Persian text (write Persian digits ۰–۹)"),
    (re.compile(r"[٠-٩]"), "Arabic-Indic digit (٠١٢٣٤٥٦٧٨٩ are not Persian: ۰۱۲۳۴۵۶۷۸۹)"),
    (re.compile(rf"[{DIG}][’'‘`´]|[’'‘`´][{DIG}]"), "apostrophe or quote touching a figure («۵’۰۰۰»): use the thousands rule"),
    (re.compile(rf"[{DIG}][,،][{DIG}]"), "comma inside a figure: thousands take «٬» (U+066C), decimals «/»"),
    (re.compile(rf"[{DIG}][.٫][{DIG}]"), "decimal mark «.» or «٫» in a figure: decimals take «/» («۹/۶»; «٫» reads like «ر» in several fonts)"),
    (re.compile(rf"(?<![{DIG}٬])[{DIG}]{{5,}}(?![{DIG}])"), "5+ digit figure without «٬» (thousands rule)"),
    (re.compile(rf"(?<![{DIG}٬/])[{DIG}]٬[{DIG}]{{3}}(?![{DIG}٬])"), "4-digit figure with «٬» (up to 4 digits: no separator)"),
    (re.compile(rf"[{DIG}]٬(?![{DIG}]{{3}}(?![{DIG}]))"), "«٬» not followed by exactly three digits"),
    (re.compile(rf"[{DIG}٪%]-|[-−][{DIG}](?![^\s]*[A-Za-z])"), "minus/hyphen beside a figure: say «افت/رشد» or use ▼/▲ with its colour"),
    (re.compile(r"[يك]"), "Arabic «ي/ك»: Persian takes «ی/ک»"),
    (re.compile(r"[‘’]"), "typographic apostrophe (’ ‘) in Persian text"),
]


# signs IRANYekanX / Estedad do not carry (seen: «←» and «·» fell to Liberation Serif): a tool draws them as
# inline SVG with `symbols()`, never as text
_SVG = {
    "←": '<svg class="sym" viewBox="0 0 48 32"><path d="M44 16H6M18 4 6 16l12 12" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "→": '<svg class="sym" viewBox="0 0 48 32"><path d="M4 16h38M30 4l12 12-12 12" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "▲": '<svg class="sym" viewBox="0 0 32 32"><path d="M16 5 29 27H3z" fill="currentColor"/></svg>',
    "▼": '<svg class="sym" viewBox="0 0 32 32"><path d="M16 27 3 5h26z" fill="currentColor"/></svg>',
    "·": '<svg class="sym dot" viewBox="0 0 20 32"><circle cx="10" cy="17" r="6" fill="currentColor"/></svg>',
    "•": '<svg class="sym dot" viewBox="0 0 20 32"><circle cx="10" cy="17" r="7" fill="currentColor"/></svg>',
    "✓": '<svg class="sym" viewBox="0 0 32 32"><path d="M6 17l7 7 13-15" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
}
SYM_CSS = ".sym{display:inline-block;height:.62em;width:auto;vertical-align:-.02em;margin:0 .18em}.sym.dot{height:.5em}"


def symbols(escaped_html: str) -> str:
    """Arrows, triangles, dots and ticks in already-escaped text → inline SVG (add SYM_CSS)."""
    for ch, svg in _SVG.items():
        escaped_html = escaped_html.replace(ch, svg)
    return escaped_html


def lint(text: str, *, persian: bool = True) -> list[str]:
    """The number and letter rules on one on-screen string: a list of problems (empty = clean).
    `persian=False` (a Latin run: a ticker, a handle) checks only the apostrophe rule."""
    t = str(text)
    out = []
    for rx, why in _LINT if persian else _LINT[2:3]:
        m = rx.search(t)
        if m:
            out.append(f"{why}: «{t[max(0, m.start() - 8): m.end() + 8]}»")
    return out


def _persianish(t: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", t))


# ---------------------------------------------------------------------------------- the gate --
_TEXT_JS = r"""(opts) => {
  const out = [], W = innerWidth, H = innerHeight, T = 2;
  const boxed = (a, s) => a.hasAttribute('data-box') ||
      !['rgba(0, 0, 0, 0)', 'transparent'].includes(s.backgroundColor) ||
      parseFloat(s.borderTopWidth) > 0 || parseFloat(s.borderBottomWidth) > 0 ||
      (s.overflow !== 'visible' && s.overflow !== '') || s.backgroundImage !== 'none';
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const inks = [];  // every text's line boxes shrunk to about its ink, for the text-over-text check
  let n;
  while ((n = w.nextNode())) {
    const t = n.nodeValue.replace(/[⁦-⁩‌‏‎]/g, '').trim();
    if (!t) continue;
    const el = n.parentElement, cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.closest('[data-nogate]')) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const rects = [...r.getClientRects()].filter(q => q.width > 0.5 && q.height > 0.5);
    const snip = t.slice(0, 48);
    out.push({kind: 'text', text: t, weight: cs.fontWeight, size: parseFloat(cs.fontSize), family: cs.fontFamily});
    const dy = 0.24 * parseFloat(cs.fontSize);
    for (const q of rects) inks.push({t: snip, l: q.left + 2, r: q.right - 2, a: q.top + dy, b: q.bottom - dy});
    const VO = Math.max(T, 0.3 * parseFloat(cs.fontSize));  // a line box is taller than its ink
    for (const q of rects) {
      if (q.left < -T || q.right > W + T || q.top < -VO || q.bottom > H + VO) {
        out.push({kind: 'problem', why: 'text runs off the picture', text: snip}); break; }
    }
    // the nearest block: its column holds the text (a line wider than its column, a fixed height)
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.display.startsWith('inline') && s.display !== 'inline-block') continue;
      const b = a.getBoundingClientRect();
      // vertical: a Persian font's line box is taller than its ink, so only a real extra line counts
      const V = Math.max(6, 0.45 * parseFloat(cs.fontSize));
      const bad = rects.find(q => q.left < b.left - T || q.right > b.right + T || q.bottom > b.bottom + V);
      if (bad) out.push({kind: 'problem', why: `text wider or taller than its block <${a.tagName.toLowerCase()}${a.className ? '.' + String(a.className).split(' ')[0] : ''}>`, text: snip});
      break;
    }
    for (let a = el; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (!boxed(a, s)) continue;
      if (s.display === 'inline' && new Set(rects.map(q => Math.round(q.top / 4))).size > 1) {
        out.push({kind: 'problem', why: 'a highlight (chip) broken over two lines', text: snip}); break; }
      const b = a.getBoundingClientRect();
      if (b.width >= W - 1 && b.height >= H - 1) continue;
      const V = s.display === 'inline' ? T : Math.max(T, 0.3 * parseFloat(cs.fontSize));
      const bad = rects.find(q => q.left < b.left - T || q.right > b.right + T || q.top < b.top - V || q.bottom > b.bottom + V);
      if (bad) {
        out.push({kind: 'problem', why: `text overflows its box <${a.tagName.toLowerCase()}${a.className ? '.' + String(a.className).split(' ')[0] : ''}> by ` +
          Math.round(Math.max(b.left - bad.left, bad.right - b.right, b.top - bad.top, bad.bottom - b.bottom)) + ' px', text: snip});
        break;
      }
    }
    if (!el.closest('[data-frame]')) {
      for (const [y0, y1] of (opts.bands || [])) {
        const hit = rects.find(q => q.bottom > y0 + T && q.top < y1 - T);
        if (hit) { out.push({kind: 'problem', why: `text in the calm band y ${y0}–${y1}`, text: snip}); break; }
      }
    }
  }
  const clash = new Set();
  if (opts.overlap !== false) for (let i = 0; i < inks.length; i++) for (let j = i + 1; j < inks.length; j++) {
    const p = inks[i], q = inks[j];
    if (p.t === q.t) continue;
    const ow = Math.min(p.r, q.r) - Math.max(p.l, q.l), oh = Math.min(p.b, q.b) - Math.max(p.a, q.a);
    if (ow > 2 && oh > 2) {
      const k = p.t + ' / ' + q.t;
      if (!clash.has(k)) { clash.add(k); out.push({kind: 'problem', why: 'text over text', text: k}); }
    }
  }
  for (const a of document.querySelectorAll('body *')) {
    const s = getComputedStyle(a);
    if (s.display === 'none' || a.closest('[data-nogate]')) continue;
    if ((s.overflowX !== 'visible' || s.textOverflow === 'ellipsis') && a.scrollWidth > a.clientWidth + 1 && a.innerText.trim())
      out.push({kind: 'problem', why: 'text clipped (scrollWidth > box)', text: a.innerText.trim().slice(0, 48)});
    if (s.overflowY !== 'visible' && a.scrollHeight > a.clientHeight + 1 && a.innerText.trim())
      out.push({kind: 'problem', why: 'text clipped (scrollHeight > box)', text: a.innerText.trim().slice(0, 48)});
  }
  return out;
}"""

_FACES_JS = """async () => {
  await document.fonts.ready;
  const faces = [...document.fonts];
  await Promise.all(faces.map(f => f.status === 'unloaded' ? f.load().catch(() => null) : null));
  await document.fonts.ready;
  return faces.map(f => ({family: f.family, weight: f.weight, status: f.status}));
}"""


def _walk_text_parents(node: dict[str, Any], acc: list[int]) -> None:
    kids = node.get("children") or []
    if any(k.get("nodeType") == 3 and (k.get("nodeValue") or "").strip() for k in kids):
        acc.append(int(node["nodeId"]))
    for k in kids:
        if k.get("nodeName", "").upper() not in ("SCRIPT", "STYLE", "HEAD"):
            _walk_text_parents(k, acc)
    for k in node.get("shadowRoots") or []:
        _walk_text_parents(k, acc)


UNIVERSAL = ("Arabic-Indic digit", "apostrophe or quote touching", "Arabic «ي/ك»", "typographic apostrophe")


def gate(page: Any, *, bands: list[tuple[int, int]] | None = None, max_weight: int = 950,
         fonts_allowed: tuple[str, ...] = (), numbers: str = "fa", overlap: bool = True) -> dict[str, Any]:
    """The page as it stands (fonts loaded): every problem with its fonts, boxes and figures.
    `bands`: [(y0, y1)…] where no text may sit unless inside an element marked data-frame.
    `fonts_allowed`: substrings of the family names that may draw text (empty = any web font we
    loaded); a system font is never allowed. `numbers`: "fa" = every number rule (DotCoin, bjtech,
    bitmart); "any" = only the rules every page shares (a page whose identity sets its data in Latin
    figures, Zarib100x's terminal look: no apostrophes in figures, no Arabic-Indic digits, no Arabic
    «ي ك»). `overlap`: False for a page whose design layers text on text on purpose.
    Returns {"ok", "problems", "fonts", "texts"}."""
    problems: list[str] = []
    faces = page.evaluate(_FACES_JS)
    for f in faces:
        if f["status"] == "error":
            problems.append(f"@font-face {f['family']} {f['weight']} did not load (wrong file or path)")
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        doc = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        ids: list[int] = []
        _walk_text_parents(doc["root"], ids)
        used: dict[str, int] = {}
        for nid in ids:
            try:
                got = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": nid})
            except Exception:  # noqa: BLE001 - a node gone since the walk
                continue
            node_txt = ""
            for f in got.get("fonts") or []:
                name = f"{f.get('familyName')}"
                used[name] = used.get(name, 0) + int(f.get("glyphCount") or 0)
                bad_sys = not f.get("isCustomFont")
                bad_name = fonts_allowed and not any(a.lower() in name.lower() for a in fonts_allowed)
                if bad_sys or bad_name:
                    if not node_txt:
                        try:
                            d = cdp.send("DOM.resolveNode", {"nodeId": nid})
                            oid = d["object"]["objectId"]
                            node_txt = cdp.send("Runtime.callFunctionOn", {
                                "objectId": oid, "returnByValue": True,
                                "functionDeclaration": "function(){return (this.innerText||this.textContent||'').trim().slice(0,48)}",
                            })["result"].get("value", "")
                        except Exception:  # noqa: BLE001
                            node_txt = "?"
                    why = "a SYSTEM font (fallback: the page's font is missing a glyph or was never loaded)" if bad_sys else "a font outside the kit's family"
                    problems.append(f"{f.get('glyphCount')} glyph(s) drawn by «{name}» — {why}: «{node_txt}»")
    finally:
        cdp.detach()
    texts = page.evaluate(_TEXT_JS, {"bands": [list(b) for b in (bands or [])], "overlap": overlap})
    shown = []
    for t in texts:
        if t["kind"] == "problem":
            problems.append(f"{t['why']}: «{t['text']}»")
            continue
        shown.append(t["text"])
        try:
            if int(float(t["weight"])) > max_weight:
                problems.append(f"weight {t['weight']} over {max_weight}: «{t['text'][:40]}»")
        except ValueError:
            pass
        for p in lint(t["text"], persian=_persianish(t["text"])):
            if numbers == "fa" or p.startswith(UNIVERSAL):
                problems.append(p)
    seen, uniq = set(), []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return {"ok": not uniq, "problems": uniq, "fonts": used, "texts": shown}


def record(out: Path, verdict: dict[str, Any], tool: str, log: str | Path = GATE_LOG,
           extra: dict[str, Any] | None = None) -> None:
    """One line in qc/type_gate.jsonl: the picture's sha256 and its verdict (deliver checks read it)."""
    p = Path(log)
    p.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else ""
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tool": tool, "out": str(out),
           "sha256": sha, "ok": verdict["ok"], "problems": verdict["problems"][:30], "fonts": verdict.get("fonts", {}),
           **(extra or {})}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def render(html: str, out: str | Path, *, size: tuple[int, int] = (1080, 1920), bands=None,
           fonts_allowed: tuple[str, ...] = (), tool: str = "fatype", jpeg_q: int = 93,
           log: str | Path | None = GATE_LOG, keep_png: bool = False, wait_ms: int = 300,
           extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """HTML → gated picture. The picture is written ONLY when the gate passes; a failing page
    leaves `out` untouched (or removed when an old one was there) and returns the problems."""
    import tempfile

    from playwright.sync_api import sync_playwright

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "page.html"
        page_file.write_text(html, encoding="utf-8")
        png = Path(tmp) / "page.png"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--allow-file-access-from-files"])
            try:
                pg = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
                pg.goto(page_file.as_uri())
                pg.wait_for_timeout(wait_ms)
                verdict = gate(pg, bands=bands, fonts_allowed=fonts_allowed)
                if verdict["ok"]:
                    pg.screenshot(path=str(png), full_page=False)
            finally:
                b.close()
        if not verdict["ok"]:
            if out.exists():
                out.unlink()
        else:
            if out.suffix.lower() in (".jpg", ".jpeg"):
                from PIL import Image

                Image.open(png).convert("RGB").save(out, "JPEG", quality=jpeg_q, optimize=True, subsampling=0)
            else:
                out.write_bytes(png.read_bytes())
    if log:
        record(out, verdict, tool, log, extra)
    return verdict


def guard(page: Any, out: str | Path, tool: str, **kw: Any) -> bool:
    """For a tool that renders by itself: gate the open page right before its screenshot, print the
    verdict and record it. False = do NOT take the screenshot (exit 2, nothing written)."""
    out = Path(out)
    v = gate(page, **kw)
    report(v, out)
    if not v["ok"] and out.exists():
        out.unlink()
    try:
        record(out, v, tool)
    except OSError:  # (a tool run outside a workspace: the verdict is printed anyway)
        pass
    return bool(v["ok"])


def report(verdict: dict[str, Any], out: str | Path) -> None:
    """The gate's verdict for a person reading the tool's output."""
    if verdict["ok"]:
        print(f"TYPE GATE OK  {out}  fonts: {', '.join(sorted(verdict['fonts']))}")
    else:
        print(f"TYPE GATE FAILED  {out}  (nothing written)")
        for p in verdict["problems"]:
            print("  -", p)
