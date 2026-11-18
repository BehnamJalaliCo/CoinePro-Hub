#!/usr/bin/env python3
"""DotCoin.me: the static site generator (stdlib only).

    python3 build.py            -> dist/  (+ dist/_og/*.html, the OG cards tools/render.py shoots)

Content lives in content/ (see content/FORMAT.md and README.md): articles, exchanges, the
glossary and the fixed pages, each with its own SEO front matter. Private brand files (fonts,
the owner's logo and the icons made from it) come from private/ (tools/prep_assets.py), never git.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT, TPL, STATIC, PRIVATE = ROOT / "content", ROOT / "templates", ROOT / "static", ROOT / "private"
DIST = Path(os.environ.get("DOTCOIN_DIST", ROOT / "dist"))
# the reels' web copies (sync.py: <slug>.mp4, .jpg, .json); never in git, copied into dist/media/
MEDIA = Path(os.environ.get("DOTCOIN_MEDIA", "/home/Hub/sites/dotcoin-media"))
SITE = json.loads((CONTENT / "site.json").read_text("utf-8"))
URL = SITE["url"].rstrip("/")
TODAY = datetime.now(timezone.utc).date()

# ---------------------------------------------------------------- small helpers
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def fa(x) -> str:
    return str(x).translate(FA_DIGITS)


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Gregorian -> Jalali (the usual arithmetic algorithm)."""
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + gdm[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def jdate(d: date) -> str:
    jy, jm, jd = g2j(d.year, d.month, d.day)
    return fa(f"{jd} {MONTHS[jm - 1]} {jy}")


def two(n: int) -> str:
    return fa(f"{n:02d}")


def words(text: str) -> int:
    return len(re.findall(r"\S+", re.sub(r"[#>*\-\[\]()`|]", " ", text)))


def read_minutes(n_words: int) -> int:
    return max(1, round(n_words / 180))


# ---------------------------------------------------------------- front matter + markdown
PERSIAN_NORM = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", **{chr(0x0660 + i): chr(0x06F0 + i) for i in range(10)}})


def parse_doc(path: Path) -> tuple[dict, str]:
    # Persian normalisation at build time: Arabic ی/ک and Arabic-Indic digits become Persian.
    text = path.read_text("utf-8").replace("\r\n", "\n").translate(PERSIAN_NORM)
    meta: dict = {}
    body = text
    if text.startswith("---\n"):
        end = text.index("\n---", 4)
        head, body = text[4:end], text[end + 4:].lstrip("\n")
        key = None
        for line in head.split("\n"):
            if not line.strip():
                continue
            if line.startswith("- ") and key:
                if not isinstance(meta.get(key), list):
                    meta[key] = []
                meta[key].append(line[2:].strip())
                continue
            k, _, v = line.partition(":")
            key = k.strip()
            meta[key] = v.strip()
    return meta, body


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r'<code dir="ltr">\1</code>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", s)

    def link(m):
        text, href = m.group(1), m.group(2)
        ext = href.startswith("http") and not href.startswith(URL)
        attrs = ' target="_blank" rel="noopener"' if ext else ""
        return f'<a href="{href}"{attrs}>{text}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def markdown(md: str, h2_numbers: bool = True) -> tuple[str, list[dict]]:
    """A small Markdown subset: ## / ### headings, paragraphs, - and 1. lists, > quotes, | tables."""
    out, toc, para, items, kind = [], [], [], [], None
    rows: list[list[str]] = []

    def flush():
        nonlocal para, items, kind
        if rows:
            head, body_rows = rows[0], [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in r)]
            out.append('<div class="tbl"><table><thead><tr>' + "".join(f'<th scope="col">{inline(c)}</th>' for c in head)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(
                           (f'<th scope="row">{inline(c)}</th>' if j == 0 else f"<td>{inline(c)}</td>") for j, c in enumerate(r))
                           + "</tr>" for r in body_rows) + "</tbody></table></div>")
            rows.clear()
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
        if items:
            tag = "ol" if kind == "ol" else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
        if kind == "quote" and quote:
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
        para, items, kind = [], [], None
        quote.clear()

    quote: list[str] = []
    fence: list[str] | None = None
    for raw in md.split("\n"):
        line = raw.strip()
        if fence is not None:  # inside ``` … ```: kept verbatim
            if line.startswith("```"):
                out.append(code_block("\n".join(fence)))
                fence = None
            else:
                fence.append(raw.rstrip())
            continue
        if line.startswith("```"):
            flush()
            fence = []
            continue
        if not line:
            flush()
            continue
        m = re.fullmatch(r"`([^`]+)`", line)
        if m and not para and not items and not rows and kind != "quote":  # a line that is one code span
            out.append(code_block(m.group(1)))
            continue
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            flush()
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 2:
                n = len([t for t in toc if t["level"] == 2]) + 1
                hid = f"s{n}"
                toc.append({"level": 2, "text": text, "id": hid})
                num = f'<span class="h-num" aria-hidden="true">{two(n)}</span>' if h2_numbers else ""
                out.append(f'<h2 id="{hid}">{num}<span>{inline(text)}</span></h2>')  # one flex item
            else:
                out.append(f"<h3>{inline(text)}</h3>")
            continue
        m = re.match(r"^(?:[-*]|\d+[.)]|[۰-۹]+[.)])\s+(.*)$", line)
        if m:
            k = "ul" if line[0] in "-*" else "ol"
            if para or (kind and kind != k):
                flush()
            kind = k
            items.append(m.group(1))
            continue
        if line.startswith("|") and line.endswith("|"):
            if para or items or kind == "quote":
                flush()
            rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        if rows:
            flush()
        if line.startswith(">"):
            if kind != "quote":
                flush()
                kind = "quote"
            quote.append(line.lstrip("> ").strip())
            continue
        if items or kind == "quote":
            flush()
        para.append(line)
    flush()
    if fence:
        out.append(code_block("\n".join(fence)))
    return "\n".join(out), toc


def code_block(text: str) -> str:
    """A hash, an address, a command: LTR, left-aligned, wraps inside its own box (site.css .cb)."""
    return f'<pre class="cb" dir="ltr"><code dir="ltr">{html.escape(text, quote=False)}</code></pre>'


FAQ_HEAD = "## پرسش‌های پرتکرار"


def split_faq(body: str) -> tuple[str, list[dict]]:
    if FAQ_HEAD not in body:
        return body, []
    main, faq_md = body.split(FAQ_HEAD, 1)
    faqs, cur = [], None
    for line in faq_md.split("\n"):
        s = line.strip()
        if s.startswith("### "):
            cur = {"q": s[4:].strip(), "a": []}
            faqs.append(cur)
        elif s and cur is not None:
            cur["a"].append(s)
    for f in faqs:
        f["a_text"] = " ".join(f["a"])
        f["a_html"] = markdown("\n".join(f["a"]))[0]
    return main, faqs


# ---------------------------------------------------------------- icons and motifs
ARROW = '<svg class="i-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5m6-6-6 6 6 6"/></svg>'
IG = '<svg class="i-ig" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.2"/><circle cx="17.4" cy="6.6" r="1.1" class="f"/></svg>'
YT = '<svg class="i-yt" viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="5" width="19" height="14" rx="4"/><path class="f" d="m10 9 5 3-5 3z"/></svg>'
COPY = '<svg class="i-copy" viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="3"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>'
EXT = '<svg class="i-ext" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/></svg>'

MOTIFS = {
    "chain": """<g class="m-ln"><rect x="34" y="122" width="112" height="112" rx="18"/><rect x="184" y="122" width="112" height="112" rx="18"/><rect class="m-new" x="334" y="122" width="112" height="112" rx="18"/><path class="m-link" d="M146 162h38M146 194h38"/><path class="m-link m-link2" d="M296 162h38M296 194h38"/></g><g class="m-fill"><rect x="56" y="150" width="56" height="10" rx="5"/><rect x="56" y="172" width="70" height="10" rx="5"/><rect x="56" y="194" width="40" height="10" rx="5"/><rect x="206" y="150" width="66" height="10" rx="5"/><rect x="206" y="172" width="44" height="10" rx="5"/><rect x="206" y="194" width="70" height="10" rx="5"/><g class="m-new"><rect x="356" y="150" width="48" height="10" rx="5"/><rect x="356" y="172" width="68" height="10" rx="5"/><rect x="356" y="194" width="56" height="10" rx="5"/></g></g>""",
    "vault": """<g class="m-ln"><path class="m-shackle" d="M190 128V96a50 50 0 0 1 100 0v32"/><rect x="110" y="128" width="260" height="150" rx="36"/><circle cx="330" cy="203" r="17"/></g><g class="m-fill"><rect x="146" y="166" width="140" height="74" rx="10"/></g><g class="m-dots"><circle cx="176" cy="203" r="7"/><circle cx="203" cy="203" r="7"/><circle cx="230" cy="203" r="7"/><circle cx="257" cy="203" r="7"/></g>""",
    "halving": """<g class="m-ln"><circle cx="128" cy="180" r="96"/><circle cx="296" cy="180" r="48"/><circle cx="380" cy="180" r="24"/><circle cx="424" cy="180" r="12"/><circle cx="450" cy="180" r="6"/><path d="M128 84v192M296 132v96M380 156v48M424 168v24"/></g><g class="m-fill m-half"><path d="M128 84a96 96 0 0 0 0 192z"/><path d="M296 132a48 48 0 0 0 0 96z"/><path d="M380 156a24 24 0 0 0 0 48z"/><path d="M424 168a12 12 0 0 0 0 24z"/></g>""",
    "peg": """<g class="m-ln"><path class="m-base" d="M30 180h420" stroke-dasharray="4 14"/><path class="m-wave" d="M30 180c20-34 40-34 60 0s40 26 60 0 40-18 60 0 40 12 60 0 40-8 60 0 40 6 60 0 40-3 60 0"/><circle cx="240" cy="180" r="62"/></g><g class="m-fill"><circle cx="240" cy="180" r="46"/></g><text x="240" y="207" class="m-txt" text-anchor="middle">$1</text>""",
    "broken": """<g class="m-ln"><rect x="40" y="122" width="112" height="112" rx="18"/><rect x="328" y="122" width="112" height="112" rx="18" transform="rotate(8 384 178)"/><path d="M152 162h44M152 194h30M284 162h44M300 194h28"/></g><g class="m-fill"><path d="M210 150l14 18-12 10 16 22" fill="none" stroke="currentColor" stroke-width="7"/></g>""",
    "generic": """<g class="m-fill">""" + "".join(
        f'<circle cx="{60 + c * 60}" cy="{90 + r * 60}" r="{14 if (r + c) % 3 else 22}"/>' for r in range(4) for c in range(7)) + "</g>",
}


def motif(name: str, cls: str = "") -> str:
    body = MOTIFS.get(name) or MOTIFS["generic"]
    return f'<svg class="motif motif-{esc(name)} {cls}" viewBox="0 0 480 360" aria-hidden="true" focusable="false">{body}</svg>'


# ---------------------------------------------------------------- content loading
IDEAS = json.loads((ROOT / SITE["ideas"]).resolve().read_text("utf-8"))
PILLARS: dict[str, str] = IDEAS["pillars"]
PILLARS.setdefault("news", "خبر")  # the informational reels' articles (2026-11-17)


def load_articles() -> list[dict]:
    arts, seen = [], {}
    # content/articles: written by hand; content/auto: the hub's daily lessons (sync.py, one per reel)
    for p in sorted((CONTENT / "articles").glob("*.md")) + sorted((CONTENT / "auto").glob("*.md")):
        m, body = parse_doc(p)
        if m.get("draft") == "true":
            continue
        if m.get("slug") in seen:
            sys.exit(f"duplicate slug {m.get('slug')}: {seen[m['slug']].name} and {p.name}")
        seen[m.get("slug")] = p
        main_md, faqs = split_faq(body)
        body_html, toc = markdown(main_md)
        m.update(
            body_html=body_html, toc=toc, faqs=faqs, words=words(main_md),
            date_obj=date.fromisoformat(m.get("date") or TODAY.isoformat()),
            idea=int(m["idea"]) if str(m.get("idea", "")).isdigit() else None,
            summary=m.get("summary") or [], steps=[s.split("|", 1) for s in (m.get("steps") or [])],
        )
        m["minutes"] = read_minutes(m["words"])
        m["url"] = f"/learn/{m['slug']}/"
        m["media"] = load_media(m["slug"])
        if not m.get("reel") and m["media"].get("reel"):
            m["reel"] = m["media"]["reel"]
        m.setdefault("motif", "generic")
        arts.append(m)
    arts.sort(key=lambda a: (-a["date_obj"].toordinal(), a["idea"] or 999))
    return arts


def load_media(slug: str) -> dict:
    """The reel's web copy for a lesson (sync.py): MEDIA/<slug>.json, with .mp4 and .jpg beside it."""
    try:
        meta = json.loads((MEDIA / f"{slug}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if not ((MEDIA / f"{slug}.mp4").is_file() and (MEDIA / f"{slug}.jpg").is_file()):
        return {"reel": meta.get("reel") or ""}
    return {**meta, "video": f"/media/{slug}.mp4", "poster": f"/media/{slug}.jpg"}


def youtube_id(v: str) -> str:
    """The optional `youtube:` field: a video id or any youtube.com / youtu.be link."""
    v = (v or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
        return v
    m = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})", v)
    return m.group(1) if m and re.match(r"https://(www\.|m\.)?(youtube\.com|youtu\.be)/", v) else ""


def load_exchanges() -> list[dict]:
    """content/exchanges.json is the one place for links, codes, buttons and logos;
    content/exchanges/<slug>.md carries the text (SEO fields, features, steps, body, FAQ)."""
    data = json.loads((CONTENT / "exchanges.json").read_text("utf-8"))
    xs = []
    for x in data["exchanges"]:
        p = CONTENT / "exchanges" / f"{x['slug']}.md"
        m, body = parse_doc(p) if p.exists() else ({}, "")
        main_md, faqs = split_faq(body)
        code = (x.get("code") or "").strip()

        def coded(lines):  # `[code] ` lines exist only while the exchange has a code
            out = []
            for line in lines:
                if line.startswith("[code]"):
                    if not code:
                        continue
                    line = line[6:].strip()
                out.append(line.replace("{code}", code))
            return out

        faqs = [f for f in faqs if code or not f["q"].startswith("[code]")]
        for f in faqs:
            f["q"] = f["q"].replace("[code]", "").strip().replace("{code}", code)
            f["a_text"] = f["a_text"].replace("{code}", code)
            f["a_html"] = f["a_html"].replace("{code}", code)
        for k in ("title", "h1", "description", "lead", "tagline", "features", "steps", "updated"):
            if k in m:
                x.setdefault("seo_title" if k == "title" else k, m[k])
        x.update(code=code, name=x["name_fa"], body_html=markdown(main_md.replace("{code}", code), h2_numbers=False)[0],
                 faqs=faqs, features=coded(m.get("features") or []),
                 steps=[s.split("|", 1) for s in coded(m.get("steps") or []) if "|" in s], url=f"/exchanges/{x['slug']}/")
        x.setdefault("description", f"معرفی {x['name_fa']} ({x['name_en']}) و راهنمای ثبت‌نام.")
        xs.append(x)
    xs.sort(key=lambda x: int(x.get("order") or 9))
    return xs


ALPHA = "ءآاأبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئ"
NORM = str.maketrans({"ي": "ی", "ك": "ک", "أ": "ا", "إ": "ا", "‌": "", " ": ""})


def fa_key(s: str) -> list[int]:
    return [ALPHA.index(ch) if ch in ALPHA else 100 + ord(ch) for ch in s.translate(NORM)]


def letter_of(s: str) -> str:
    ch = s.translate(NORM)[:1]
    return "ا" if ch in "آاأ" else ch


def load_glossary() -> list[dict]:
    terms = []
    for line in (CONTENT / "glossary.txt").read_text("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 4:
            continue
        slug, term, en, definition = parts[0], parts[1], parts[2], "|".join(parts[3:])
        terms.append({"slug": slug, "term": term, "en": en, "def": definition, "letter": letter_of(term)})
    terms.sort(key=lambda t: fa_key(t["term"]))
    return terms


def load_page(name: str) -> tuple[dict, str]:
    return parse_doc(CONTENT / "pages" / f"{name}.md")


# ---------------------------------------------------------------- page shell
NAV = [("/learn/", "آموزش‌ها"), ("/exchanges/", "صرافی‌ها"), ("/glossary/", "واژه‌نامه"), ("/about/", "درباره")]
NAV_EN = ["LEARN", "EXCHANGES", "GLOSSARY", "ABOUT"]
# ⟨2026-11-18⟩ TradeYar's free VIP signal channel (content/vip.json): its own page, last in the menu
VIP_NAV = ("/vip/", "سیگنال VIP")
PAGES: list[dict] = []  # for the sitemap
OG_JOBS: list[dict] = []
_BASE = (TPL / "base.html").read_text("utf-8")
_OG = (TPL / "og.html").read_text("utf-8")


def fill(tpl: str, data: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(data.get(m.group(1), "")), tpl)


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


def version_token() -> str:
    h = hashlib.sha256()
    for p in sorted(list(STATIC.rglob("*")) + list(PRIVATE.rglob("*"))):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return "?v=" + h.hexdigest()[:10]


V = ""
CSS = ""
LATEST = TODAY.isoformat()  # set in main(): the newest lesson's date


def crumbs_ld(crumbs: list[tuple[str, str]]) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": URL + path} for i, (path, name) in enumerate(crumbs)]}


def crumbs_html(crumbs: list[tuple[str, str]]) -> str:
    parts = []
    for i, (path, name) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append(f'<li aria-current="page">{esc(name)}</li>')
        else:
            parts.append(f'<li><a href="{path}">{esc(name)}</a></li>')
    return '<nav class="crumbs" aria-label="مسیر صفحه"><ol>' + "".join(parts) + "</ol></nav>"


ORG_ID = URL + "/#org"
SITE_ID = URL + "/#website"
PERSON = {"@type": "Person", "@id": URL + "/about/#behnam", "name": SITE["author"], "alternateName": SITE["author_en"],
          "url": URL + "/about/", "sameAs": [SITE["instagram"]]}


def org_ld() -> dict:
    return {"@type": "Organization", "@id": ORG_ID, "name": SITE["name_fa"], "alternateName": [SITE["name"], "Dot Coin"], "url": URL + "/",
            "logo": {"@type": "ImageObject", "url": URL + "/assets/img/logo-384.png", "width": 384, "height": 384},
            "sameAs": [SITE["instagram"], SITE["youtube"]]}


# ---------------------------------------------------------------- bidi: Latin runs inside Persian text
# Every page is RTL. A Latin run inside a Persian sentence (SHA-256, DotCoin, USDT TRC20, a URL) is an
# LTR island for the Unicode bidi algorithm, and next to neutral punctuation, digits or a line break it
# can land in the wrong place (the owner saw «هش SHA-256 کلمه‌ی DotCoin» scrambled on an iPhone).
# isolate_html() runs over the <body> of every written page and OG card: each Latin run becomes
# <bdi dir="ltr">…</bdi> (an isolate that keeps its place in the RTL sentence), with class "lat" when
# it has digits (the FaNum font would draw them Persian). Punctuation around a run (، ؛ : . « ») stays
# outside it, on the RTL side. Text under dir="ltr", <code>, <pre>, <svg>, <script> is left alone.
# lint_dist() reads the written pages back and fails the build on any un-isolated Latin run or any
# <code>/<pre> without dir="ltr", so no page (the hub's daily articles included) ships the bug again.
_TOK = re.compile(r"(?<![A-Za-z0-9])(?:\([$@#]?[A-Za-z0-9][^()\n\u0600-\u06FF]*\)"
                  r"|[$@#]?[A-Za-z0-9](?:[A-Za-z0-9]|[-+./:@#%&=~?_'’,]+(?=[A-Za-z0-9]))*(?:%|\+\+?)?)")
_GAP = re.compile(r"[ \u00a0]+|[ \u00a0]*[-–—&/+,][ \u00a0]*")
_HAS_LAT = re.compile(r"[A-Za-z]")
_TAG = re.compile(r"<!--.*?-->|<(/?)([a-zA-Z][\w-]*)([^>]*)>", re.S)
_DIR_LTR = re.compile(r"""\bdir\s*=\s*["']?(?:ltr|auto)\b""", re.I)
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_LTR_TAGS = {"bdi", "code", "pre", "kbd", "samp", "svg", "math", "script", "style", "textarea", "title", "template"}


def latin_runs(text: str) -> list[tuple[int, int]]:
    """(start, end) of each Latin run that has a letter. Words join over spaces or a dash, slash, &
    or Latin comma into one run (Binance Smart Chain (BSC), USDT TRC20, Layer 2); a number before a word does not
    (۱۰ BTC keeps the RTL order); a run ends before its trailing punctuation."""
    runs: list[list] = []  # [start, end, has_letter]
    for m in _TOK.finditer(text):
        lat = bool(_HAS_LAT.search(m.group()))
        if runs:
            prev, gap = runs[-1], text[runs[-1][1]:m.start()]
            if prev[2] and gap and _GAP.fullmatch(gap) and (lat or (not gap.strip() and m.group()[0].isdigit())):
                prev[1] = m.end()
                continue
        runs.append([m.start(), m.end(), lat])
    return [(a, b) for a, b, lat in runs if lat]


def _nodes(page: str):
    """Yield (kind, chunk, ltr) over a page: kind "raw" (head, script/style text), "tag" or "text";
    ltr is True inside an LTR or isolated context (dir="ltr"/"auto", code, pre, bdi, svg, …)."""
    body = max(page.find("<body"), 0)
    yield "raw", page[:body], True
    low, stack, pos = page.lower(), [], body
    while True:
        m = _TAG.search(page, pos)
        ltr = any(s[1] for s in stack)
        if not m:
            yield "text", page[pos:], ltr
            return
        if m.start() > pos:
            yield "text", page[pos:m.start()], ltr
        yield "tag", m.group(0), ltr
        pos = m.end()
        close, name, attrs = m.group(1), (m.group(2) or "").lower(), m.group(3) or ""
        if not name:
            continue
        if close:
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == name:
                    del stack[k:]
                    break
        elif name in _VOID or attrs.rstrip().endswith("/"):
            continue
        elif name in ("script", "style"):
            end = low.find(f"</{name}", pos)
            end = len(page) if end < 0 else end
            yield "raw", page[pos:end], True
            pos = end
        else:
            stack.append((name, name in _LTR_TAGS or bool(_DIR_LTR.search(attrs))))


def _isolate_text(chunk: str) -> str:
    text = html.unescape(chunk)
    runs = latin_runs(text) if _HAS_LAT.search(text) else []
    if not runs:
        return chunk
    out, i = [], 0
    for a, b in runs:
        run = text[a:b]
        cls = ' class="lat"' if re.search(r"[0-9]", run) else ""
        out += [html.escape(text[i:a], quote=False), f'<bdi dir="ltr"{cls}>{html.escape(run, quote=False)}</bdi>']
        i = b
    out.append(html.escape(text[i:], quote=False))
    return "".join(out)


def isolate_html(page: str) -> str:
    return "".join(_isolate_text(c) if kind == "text" and not ltr else c for kind, c, ltr in _nodes(page))


def lint_html(page: str, name: str) -> list[str]:
    problems = []
    for kind, chunk, ltr in _nodes(page):
        if kind == "text" and not ltr:
            text = html.unescape(chunk)
            m = _HAS_LAT.search(text)
            if m:
                ctx = " ".join(text[max(0, m.start() - 30):m.start() + 40].split())
                problems.append(f"{name}: a Latin run not isolated in RTL text: «{ctx}»")
        elif kind == "tag":
            t = _TAG.match(chunk)
            if t and not t.group(1) and (t.group(2) or "").lower() in ("code", "pre") and not _DIR_LTR.search(t.group(3) or ""):
                problems.append(f"{name}: <{t.group(2)}> without dir=\"ltr\": {chunk[:80]}")
    return problems


def lint_dist() -> list[str]:
    """Every written page (and OG card source) read back from dist/."""
    problems = []
    for p in sorted(DIST.rglob("*.html")):
        if "media" not in p.relative_to(DIST).parts:
            problems += lint_html(p.read_text("utf-8"), "/" + str(p.relative_to(DIST)))
    return problems


def render(path: str, meta: dict, main: str, *, kind: str, ld: list[dict], og: dict, og_type: str = "website",
           og_extra: str = "", body_class: str = "", lessons: list[dict] | None = None) -> None:
    """Write one page. SEO fields come from `meta` (front matter): seo_title, description,
    og_title, og_description, noindex; see README.md."""
    title = meta.get("title", "")
    seo_title = meta.get("seo_title") or (title + SITE["title_suffix"])
    desc = meta.get("description", "")
    canonical = URL + (path if path != "/404.html" else "/404")
    key = og["key"]
    OG_JOBS.append({"key": key, "en": og.get("en") or meta.get("og_en") or "DOTCOIN",
                    "title": meta.get("og_title") or title, "kicker": og.get("kicker") or meta.get("og_kicker") or SITE["tagline"]})
    graph = {"@context": "https://schema.org", "@graph": ld} if ld else None
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if path.startswith(href) else ""}>{name}</a>' for href, name in NAV)
    drawer = '<a href="/"><span>خانه</span><i dir="ltr">HOME</i></a>' + "".join(
        f'<a href="{href}"><span>{name}</span><i dir="ltr">{en}</i></a>'
        for (href, name), en in zip(NAV, NAV_EN))
    foot_nav = '<a href="/">خانه</a>' + "".join(f'<a href="{h}">{n}</a>' for h, n in NAV)
    if VIP:
        cur = " aria-current=page" if path.startswith(VIP_NAV[0]) else ""
        nav += f'<a class="nav-vip" href="{VIP_NAV[0]}"{cur}>{VIP_NAV[1]}</a>'
        drawer += f'<a class="drawer-vip" href="{VIP_NAV[0]}"><span>{VIP_NAV[1]}</span><i dir="ltr">VIP</i></a>'
        foot_nav += f'<a href="{VIP_NAV[0]}">کانال VIP تریدیار</a>'
    foot_lessons = "".join(f'<a href="{a["url"]}">{esc(a["title"])}</a>' for a in (lessons or [])[:4])
    page = fill(_BASE, {
        "page_kind": kind, "seo_title": esc(seo_title), "description": esc(desc), "canonical": canonical,
        "robots": '<meta name="robots" content="noindex, follow">\n' if meta.get("noindex") == "true" else
                  '<meta name="robots" content="index, follow, max-image-preview:large">\n',
        "author": esc(SITE["author"]), "og_type": og_type, "site_name": esc(SITE["name_fa"]),
        "og_title": esc(meta.get("og_title") or seo_title), "og_description": esc(meta.get("og_description") or desc),
        "og_image": f"{URL}/og/{key}.jpg", "og_extra": og_extra, "v": V, "css": CSS,
        "jsonld": ('<script type="application/ld+json">' + json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>") if graph else "",
        "body_class": body_class, "nav": nav, "drawer": drawer, "instagram": SITE["instagram"],
        "youtube": SITE["youtube"], "ig_icon": IG, "main": main, "foot_nav": foot_nav, "foot_lessons": foot_lessons,
        "ftr_fit": fit("DOTCOIN.ME"), "year_fa": fa(g2j(TODAY.year, TODAY.month, TODAY.day)[0]),
    })
    out = DIST / (path.lstrip("/") + ("index.html" if path.endswith("/") else ""))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(isolate_html(page), "utf-8")
    if meta.get("noindex") != "true":
        PAGES.append({"loc": canonical, "lastmod": meta.get("lastmod") or meta.get("updated") or LATEST})


# ---------------------------------------------------------------- shared pieces
_METRICS = json.loads((PRIVATE / "anton-metrics.json").read_text()) if (PRIVATE / "anton-metrics.json").exists() else None


def fit(word: str) -> str:
    """em per line width for an Anton word, so CSS can size it to fill its line exactly."""
    if not _METRICS:
        return f"{1 / (0.5 * max(1, len(word))):.4f}"
    em = sum(_METRICS["adv"].get(ch, 1100) for ch in word) / _METRICS["upm"]
    return f"{1 / em:.4f}"


def giant(word: str, cls: str = "") -> str:
    letters = "".join(f'<span style="--i:{i}">{esc(ch) if ch != " " else "&nbsp;"}</span>' for i, ch in enumerate(word))
    return f'<div class="giant {cls}" dir="ltr" aria-hidden="true" style="--fit:{fit(word)}">{letters}</div>'


def sec_head(num: str, en: str, title: str, more: str = "", sub: str = "") -> str:
    sub_html = f'<p class="sec-sub">{sub}</p>' if sub else ""
    return (f'<header class="sec-h rv"><span class="sec-n" dir="ltr">({num}) {en}</span>'
            f'<h2 class="sec-t">{title}</h2>{sub_html}{more}</header>')


def pillar_chip(p: str) -> str:
    return f'<span class="chip">{esc(PILLARS.get(p, p))}</span>'


def lesson_card(a: dict, i: int = 0, big: bool = False) -> str:
    return f"""<article class="card rv{' card-big' if big else ''}" data-pillar="{esc(a['pillar'])}" style="--i:{i}">
<a class="card-a" href="{a['url']}">
<div class="card-art">{motif(a['motif'])}<span class="card-en" dir="ltr" style="--fit:{fit(a['en'])}">{esc(a['en'])}</span><span class="card-no">{two(a.get('n', i + 1))}</span></div>
<div class="card-body"><div class="card-meta">{pillar_chip(a['pillar'])}<span>{fa(a['minutes'])} دقیقه مطالعه</span></div>
<h3 class="card-t">{esc(a['title'])}</h3><p class="card-l">{esc(a.get('lead', ''))}</p>
<span class="go">خواندن درس {ARROW}</span></div></a></article>"""


def go_link(x: dict, page: str = "") -> str:
    """Every signup button goes through /go/<slug>/ (a 302 in _redirects, from exchanges.json)."""
    return f"/go/{x['slug']}/"


REL_SPONSORED = 'target="_blank" rel="sponsored nofollow noopener"'


def svg_size(name: str) -> str:
    """width/height attributes from the SVG file, so the logo box is reserved before it loads."""
    f = STATIC / "exchanges" / name
    t = f.read_text("utf-8", "replace")[:600] if f.exists() else ""
    w, h = re.search(r'<svg[^>]*?\swidth="([\d.]+)', t), re.search(r'<svg[^>]*?\sheight="([\d.]+)', t)
    return f' width="{w.group(1)}" height="{h.group(1)}"' if w and h else ""


def logo_img(x: dict, size: str = "") -> str:
    alt = f"لوگوی {x['name']} ({x['name_en']})"
    if not x.get("logo"):
        return f'<span class="xlogo xlogo-txt {size}" dir="ltr">{esc(x["name_en"])}</span>'
    light = f'<img class="xl {"xl-l" if x.get("logo_dark") else ""}" src="/assets/exchanges/{esc(x["logo"])}{V}"{svg_size(x["logo"])} alt="{esc(alt)}" loading="lazy" decoding="async">'
    dark = (f'<img class="xl xl-d" src="/assets/exchanges/{esc(x["logo_dark"])}{V}"{svg_size(x["logo_dark"])} alt="" loading="lazy" decoding="async">'
            if x.get("logo_dark") else "")
    plate = " xlogo-dark" if x.get("plate") == "dark" else ""
    return f'<span class="xlogo{plate} {size}">{light}{dark}</span>'


def code_chip(x: dict) -> str:
    if not x.get("code"):
        return ""
    return (f'<div class="code"><span class="code-l">{esc(x.get("code_label") or "کد دعوت")}</span>'
            f'<button class="code-b" type="button" data-copy="{esc(x["code"])}" aria-label="کپی {esc(x.get("code_label") or "کد")} {esc(x["code"])}">'
            f'<b dir="ltr">{esc(x["code"])}</b>{COPY}<span class="code-ok" aria-hidden="true">کپی شد</span></button></div>')


def exchange_card(x: dict, page: str, i: int = 0, signup: bool = True) -> str:
    signup_btn = (f'<a class="btn btn-solid" href="{go_link(x)}" target="_blank" rel="sponsored nofollow noopener">{esc(x["button"])} {ARROW}</a>'
                  if signup else "")
    return f"""<article class="xc rv" style="--i:{i}">
<div class="xc-top">{logo_img(x)}<span class="xc-en" dir="ltr">{esc(x['en'])}</span></div>
<h3 class="xc-t">{esc(x['name'])} <span dir="ltr">{esc(x['name_en'])}</span></h3>
<p class="xc-l">{esc(x.get('tagline') or x.get('lead', ''))}</p>
{code_chip(x) if signup else ""}
<div class="xc-act">{signup_btn}<a class="{'lnk' if signup else 'btn btn-solid'}" href="{x['url']}">معرفی و راهنمای ثبت‌نام{'' if signup else ' ' + ARROW}</a></div></article>"""


def faq_html(faqs: list[dict]) -> str:
    if not faqs:
        return ""
    items = "".join(
        f'<details class="faq-i"><summary><span>{inline(f["q"])}</span><i aria-hidden="true"></i></summary><div class="faq-a">{f["a_html"]}</div></details>'
        for f in faqs)
    return f'<section class="faq" id="faq" aria-labelledby="faq-t"><h2 id="faq-t">پرسش‌های پرتکرار</h2>{items}</section>'


def faq_ld(faqs: list[dict]) -> dict:
    return {"@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a_text"]}} for f in faqs]}


def ring_svg(text: str, rid: str = "ringp") -> str:
    return (f'<svg class="ring" viewBox="0 0 200 200" aria-hidden="true" xmlns:xlink="http://www.w3.org/1999/xlink"><defs><path id="{rid}" d="M100 100m-84 0a84 84 0 1 1 168 0a84 84 0 1 1-168 0"/></defs>'
            f'<text direction="ltr"><textPath href="#{rid}" xlink:href="#{rid}" textLength="525">{esc(text)}</textPath></text></svg>')


# ---------------------------------------------------------------- the VIP (TradeYar's signal channel)
def _json_or_none(name: str) -> dict | None:
    p = CONTENT / name
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else None
    except ValueError:
        sys.exit(f"content/{name} is not valid JSON")


VIP = _json_or_none("vip.json")
VIP_STATS = _json_or_none("vip_stats.json") or {}
REL_TY = 'target="_blank" rel="sponsored nofollow noopener"'


def fa_num(x, digits: int = 0) -> str:
    """1850 -> ۱٬۸۵۰; 63.2 -> ۶۳٫۲ (Persian digits, separators)."""
    t = f"{float(x):,.{digits}f}" if digits else f"{int(round(float(x))):,}"
    return t.replace(",", "٬").replace(".", "٫").translate(FA_DIGITS)


def vip_go(pl: str) -> str:
    """The bot through TradeYar's tracker, behind the site's own redirect (counted per placement)."""
    return f"/go/vip-{pl}/"


def vip_stats_items() -> list[tuple[str, str, str]]:
    """(value, label, note) from TradeYar's public record only; none when the file is missing."""
    st = VIP_STATS
    if not st.get("trades"):
        return []
    out = [(fa_num(st["trades"]), "معامله‌ی بسته‌شده", f"در {fa_num(st.get('days') or 0)} روز")]
    if st.get("win_rate_pct") is not None:
        out.append((fa_num(st["win_rate_pct"], 1) + "٪", "نرخ برد", f"از {fa_num(st['trades'])} معامله"))
    if st.get("profit_factor") is not None:
        out.append((fa_num(st["profit_factor"], 2), "ضریب سود", "مجموع سودها به مجموع زیان‌ها"))
    if st.get("symbols"):
        out.append((fa_num(st["symbols"]), "نماد", "ارزهایی که سیگنال گرفته‌اند"))
    return out


def vip_as_of() -> str:
    """The record's last trade, as a Tehran day (the API gives UTC)."""
    from zoneinfo import ZoneInfo

    try:
        at = datetime.fromisoformat(str(VIP_STATS.get("as_of") or ""))
    except ValueError:
        return ""
    return jdate(at.astimezone(ZoneInfo("Asia/Tehran")).date()) if at.tzinfo else jdate(at.date())


def vip_stats_html(cls: str = "") -> str:
    items = vip_stats_items()
    if not items:
        return ""
    tiles = "".join(f'<li class="vs-i"><b class="vs-v">{v}</b><span class="vs-l">{esc(lbl)}</span><span class="vs-n">{esc(n)}</span></li>'
                    for v, lbl, n in items)
    when = vip_as_of()
    src = (f'<p class="vs-src">منبع: <a href="{esc(VIP["record"])}" {REL_TY}>کارنامه‌ی عمومی تریدیار</a>'
           + (f"، تا {when}" if when else "") + "</p>")
    return f'<div class="vs {cls}"><ul class="vs-list">{tiles}</ul>{src}</div>'


def vip_cta(slug: str) -> str:
    """⟨2026-11-18⟩ ONE block per lesson (after the lesson, its sources, its video box and its FAQ;
    never between its paragraphs, never a pop-up): what the VIP is, its free condition, the guide
    and the bot."""
    if not VIP:
        return ""
    st = VIP_STATS
    line = (f"{fa_num(st['trades'])} معامله‌ی بسته‌شده در کارنامه‌ی عمومی، نرخ برد {fa_num(st['win_rate_pct'], 1)}٪."
            if st.get("trades") and st.get("win_rate_pct") is not None else "")
    return f"""<aside class="vipcta rv" aria-labelledby="vip-{esc(slug)}">
<div class="vipcta-copy"><span class="sec-n" dir="ltr">VIP SIGNALS · TRADEYAR</span>
<h2 id="vip-{esc(slug)}">سیگنال‌های VIP تریدیار، رایگان</h2>
<p>کانال VIP تریدیار سیگنال‌های فیوچرز را پیش از مشخص شدن نتیجه منتشر می‌کند و همه‌ی معامله‌ها، برد و باخت، در کارنامه‌ی عمومی‌اش می‌مانند. عضویت رایگان است: حساب صرافی با لینک تریدیار، دست‌کم {fa(VIP["min_usdt"])} تتر در حساب خودت و ارسال UID به ربات.</p>
{f'<p class="vipcta-num">{line}</p>' if line else ""}
<div class="vipcta-act"><a class="btn btn-acc" href="/vip/">راهنمای ورود رایگان {ARROW}</a><a class="lnk" href="{vip_go("lesson")}" {REL_TY}>ربات تریدیار <bdi>@{esc(VIP["bot"])}</bdi></a></div></div>
<div class="vipcta-mark" aria-hidden="true" dir="ltr"><span>VIP</span></div>
</aside>"""


# ---------------------------------------------------------------- pages
def page_home(arts, xs, terms):
    meta, _ = load_page("home")
    today = next((a for a in arts if a["slug"] == SITE.get("today")), arts[0])
    h1a, _, h1b = meta["title"].rpartition(" به ")
    h1b = "به " + h1b if h1a else h1b
    n_steps = len(today["steps"])
    slides = "".join(
        f'<div class="st-slide{" is-on" if i == 0 else " next"}" role="group" aria-roledescription="گام" aria-label="گام {fa(i + 1)} از {fa(n_steps)}" data-i="{i}">'
        f'<span class="st-num" aria-hidden="true">{two(i + 1)}</span><div class="st-copy"><h3 class="st-t">'
        + "".join(f'<span style="--w:{k}">{esc(w)}</span> ' for k, w in enumerate(t.strip().split()))
        + f'</h3><p class="st-p">{esc(s.strip())}</p></div></div>'
        for i, (t, s) in enumerate(today["steps"]))
    bars = "".join(f'<button class="st-bar{" is-on" if i == 0 else ""}" type="button" aria-label="گام {fa(i + 1)}" data-go="{i}"><i></i></button>' for i in range(n_steps))
    pillar_rows = "".join(
        f'<a class="pl-row rv" style="--i:{k}" href="/learn/#{p}"><span class="pl-n">{two(k + 1)}</span><span class="pl-fa">{esc(name)}</span>'
        f'<span class="pl-en" dir="ltr">{esc(SITE["pillars_en"].get(p, p.upper()))}</span><span class="pl-c">'
        + (f"{fa(c)} درس" if (c := sum(1 for a in arts if a["pillar"] == p)) else "به‌زودی")
        + f"</span>{ARROW}</a>" for k, (p, name) in enumerate(PILLARS.items()))
    pick = ["blockchain", "hash", "seed-phrase", "stablecoin", "halving", "gas-fee", "cold-wallet", "defi"]
    teaser = ([t for s in pick for t in terms if t["slug"] == s] + terms)[:8]
    marquee_words = " · ".join(t["en"].upper() for t in terms[:16])
    term_cards = "".join(
        f'<a class="gt rv" style="--i:{i}" href="/glossary/#{esc(t["slug"])}"><span class="gt-en" dir="ltr">{esc(t["en"])}</span>'
        f'<b class="gt-t">{esc(t["term"])}</b><span class="gt-d">{esc(t["def"])}</span></a>' for i, t in enumerate(teaser))
    lessons = "".join(lesson_card(a, i, big=False) for i, a in enumerate(arts[:4]))
    xcards = "".join(exchange_card(x, "home", i, signup=False) for i, x in enumerate(xs))
    main = f"""
<section class="hero hero-home" aria-labelledby="h1">
  <div class="wrap hero-grid">
    <div class="hero-meta" aria-hidden="true"><span class="ld" style="--d:0">DOTCOIN.ME</span><span class="ld" style="--d:1">CRYPTO, IN PLAIN PERSIAN</span><span class="ld" style="--d:2">{fa(len(arts))} درس · {fa(len(terms))} واژه</span><span class="ld live" style="--d:3"><i></i>LIVE CHAIN</span></div>
    <div class="hero-copy">
      <p class="kicker ld" style="--d:2"><i></i>{esc(SITE['tagline'])}</p>
      <h1 id="h1" class="h-hero"><span class="ln"><span style="--d:3">{esc(h1a)}</span></span><span class="ln"><span style="--d:4">{esc(h1b.rsplit(" ", 1)[0])} <em>{esc(h1b.rsplit(" ", 1)[-1])}</em></span></span></h1>
      <p class="hero-lead ld" style="--d:6">{esc(meta['lead'])}</p>
      <div class="hero-cta ld" style="--d:7"><a class="btn btn-solid btn-lg" href="/learn/">شروع یادگیری {ARROW}</a><a class="btn btn-line btn-lg" href="{SITE['instagram']}" target="_blank" rel="noopener">{IG}<span>دنبال کردن در اینستاگرام</span></a></div>
    </div>
    <figure class="hero-mark ld" style="--d:3">
      <img src="/assets/img/logo-640.webp{V}" srcset="/assets/img/logo-384.webp{V} 384w, /assets/img/logo-640.webp{V} 640w" sizes="(max-width: 760px) 58vw, 30vw" width="640" height="640" alt="بهنام جلالی، سازنده‌ی دات‌کوین" fetchpriority="high">
      {ring_svg("DOTCOIN.ME · CRYPTO IN PLAIN PERSIAN · LEARN · ")}
    </figure>
  </div>
  {giant("DOTCOIN", "giant-hero")}
</section>

<section class="chainband" aria-labelledby="chain-t">
  <div class="wrap chain-head">
    <span class="sec-n" dir="ltr">(00) BLOCK BY BLOCK</span>
    <h2 id="chain-t">زنجیره‌ی زنده</h2>
    <p>هر بلوک «اثر انگشت» بلوک قبلی را با خودش دارد. <b>روی یک بلوک بزن</b> و ببین تغییر دادن یک بلوک قدیمی چطور همه‌ی بلوک‌های بعدی را از زنجیره جدا می‌کند.</p>
  </div>
  <div class="chain-stage"><canvas class="chain" aria-label="نمایش زنده‌ی زنجیره‌ی بلوک‌ها؛ روی هر بلوک بزن تا دست‌کاری آن را ببینی" role="img"></canvas><p class="chain-msg" aria-live="polite"></p></div>
</section>

<section class="sec" aria-labelledby="latest-t">
  <div class="wrap">
    {sec_head("01", "LATEST LESSONS", '<span id="latest-t">تازه‌ترین درس‌ها</span>', f'<a class="lnk sec-more" href="/learn/">همه‌ی درس‌ها {ARROW}</a>')}
    <div class="cards">{lessons}</div>
  </div>
</section>

<section class="sec sec-today" aria-labelledby="today-t">
  <div class="wrap">
    {sec_head("02", "TODAY'S LESSON", '<span id="today-t">درس امروز</span>', "", f'{esc(today["title"])}، در {fa(n_steps)} گام کوتاه')}
    <div class="stepper rv" data-stepper tabindex="0" aria-label="درس امروز گام‌به‌گام: {esc(today['title'])}" style="--n:{n_steps};--p:{1 / max(1, n_steps):.4f}">
      <div class="st-top"><span class="chip chip-inv">{esc(PILLARS.get(today['pillar'], ''))}</span><span class="st-count" aria-live="polite">{fa(1)} / {fa(n_steps)}</span></div>
      <div class="st-stage">{slides}</div>
      <div class="st-word" dir="ltr" aria-hidden="true" style="--fit:{fit(today['en'])}"><span class="st-w0">{esc(today['en'])}</span><span class="st-w1">{esc(today['en'])}</span></div>
      <div class="st-ctrl"><div class="st-bars">{bars}</div>
        <div class="st-btns"><button class="rb st-prev" type="button" aria-label="گام قبل" disabled>{ARROW}</button><button class="rb st-next" type="button" aria-label="گام بعد">{ARROW}</button></div>
        <a class="btn btn-acc st-read" href="{today['url']}">خواندن کامل درس {ARROW}</a></div>
    </div>
  </div>
</section>

<section class="sec sec-pillars" aria-labelledby="pl-t">
  <div class="wrap">
    {sec_head("03", "SEVEN PATHS", '<span id="pl-t">مسیرهای یادگیری</span>', "", "هر درس در یکی از این مسیرهاست. از پایه‌ها شروع کن.")}
    <div class="pl-list">{pillar_rows}</div>
  </div>
</section>

<section class="sec sec-x" aria-labelledby="x-t">
  <div class="wrap">
    {sec_head("04", "EXCHANGES", '<span id="x-t">صرافی‌ها</span>', f'<a class="lnk sec-more" href="/exchanges/">معرفی کامل صرافی‌ها {ARROW}</a>', "صرافی‌هایی که دات‌کوین معرفی می‌کند، با راهنمای ثبت‌نام قدم‌به‌قدم.")}
    <div class="xcards">{xcards}</div>
  </div>
</section>

<section class="sec sec-gl" aria-labelledby="gl-t">
  <div class="marquee" aria-hidden="true" dir="ltr"><div class="mq-in"><span>{esc(marquee_words)} · </span><span>{esc(marquee_words)} · </span></div></div>
  <div class="wrap">
    {sec_head("05", "GLOSSARY", '<span id="gl-t">واژه‌نامه</span>', f'<a class="lnk sec-more" href="/glossary/">همه‌ی {fa(len(terms))} واژه {ARROW}</a>', "اصطلاح‌های کریپتو، هر کدام در یک جمله‌ی روشن.")}
    <div class="gts">{term_cards}</div>
  </div>
</section>

{follow_block("home")}
"""
    ld = [org_ld(), {"@type": "WebSite", "@id": SITE_ID, "url": URL + "/", "name": SITE["name_fa"], "alternateName": [SITE["name"], "Dot Coin"],
                     "inLanguage": "fa", "publisher": {"@id": ORG_ID}, "description": meta["description"]}, PERSON]
    render("/", meta, main, kind="home", ld=ld, og={"key": "home", "en": meta.get("og_en")}, body_class="p-home", lessons=arts)


def follow_block(page: str) -> str:
    return f"""<section class="follow" aria-labelledby="fw-t">
  <div class="wrap follow-in">
    <figure class="follow-mark rv"><img src="/assets/img/logo-384.webp{V}" width="384" height="384" alt="لوگوی دات‌کوین" loading="lazy" decoding="async">{ring_svg("FOLLOW · @DOTCOIN.ME · FOLLOW · @DOTCOIN.ME · ", "ringf")}</figure>
    <div class="follow-copy rv">
      <span class="sec-n" dir="ltr">(06) FOLLOW</span>
      <h2 id="fw-t">درس‌های کوتاه ویدیویی، در اینستاگرام</h2>
      <p>هر درس دات‌کوین اول به‌صورت یک ویدیوی کوتاه در اینستاگرام منتشر می‌شود. دنبال کن تا درس بعدی را از دست ندهی.</p>
      <div class="hero-cta"><a class="btn btn-solid btn-lg" href="{SITE['instagram']}" target="_blank" rel="noopener">{IG}<span>دنبال کردن <bdi>@dotcoin.me</bdi></span></a><a class="btn btn-line btn-lg" href="{SITE['youtube']}" target="_blank" rel="noopener">{YT}<span>یوتیوب</span></a></div>
    </div>
  </div>
  <div class="follow-giant" dir="ltr" aria-hidden="true" style="--fit:{fit("@DOTCOIN.ME")}">@DOTCOIN.ME</div>
</section>"""


def page_hero(meta: dict, en: str, crumbs: list, extra: str = "", cls: str = "") -> str:
    return f"""<section class="hero hero-page {cls}" aria-labelledby="h1">
  <div class="wrap">
    {crumbs_html(crumbs)}
    <h1 id="h1" class="h-page"><span class="ln"><span style="--d:1">{esc(meta['title'])}</span></span></h1>
    <p class="hero-lead ld" style="--d:3">{esc(meta.get('lead', ''))}</p>
    {extra}
  </div>
  {giant(en, "giant-page")}
</section>"""


def page_learn(arts):
    meta, _ = load_page("learn")
    crumbs = [("/", "خانه"), ("/learn/", "آموزش‌ها")]
    counts = {p: sum(1 for a in arts if a["pillar"] == p) for p in PILLARS}
    chips = f'<button class="fchip is-on" type="button" data-f="all" aria-pressed="true">همه <i>{fa(len(arts))}</i></button>' + "".join(
        f'<button class="fchip" id="{p}" type="button" data-f="{p}" aria-pressed="false">{esc(n)} <i>{fa(counts[p])}</i></button>'
        for p, n in PILLARS.items() if counts[p] or p != "news")
    for i, a in enumerate(arts):
        a["n"] = len(arts) - i
    cards = "".join(lesson_card(a, i) for i, a in enumerate(arts))
    done = {a["idea"] for a in arts if a["idea"]}
    upcoming = [i for i in IDEAS["ideas"] if i["id"] not in done]
    up = "".join(
        f'<li data-pillar="{esc(i["pillar"])}"><span class="up-p">{esc(PILLARS.get(i["pillar"], ""))}</span><span class="up-t">{esc(i["title"])}</span></li>'
        for i in upcoming)
    by_slug = {a["slug"]: a for a in arts}
    path_li = "".join(
        (f'<li><a href="{by_slug[s]["url"]}">{esc(by_slug[s]["title"])}</a></li>' if s in by_slug else
         f'<li><span>{esc(t)}</span> <i>به‌زودی</i></li>')
        for s, t in (p.split("|", 1) for p in SITE.get("path", [])))
    path_sec = (f"""<section class="sec sec-path" aria-labelledby="path-t"><div class="wrap">
  {sec_head("—", "START HERE", '<span id="path-t">مسیر یادگیری از صفر</span>', "", "اگر تازه شروع کرده‌ای، درس‌ها را به همین ترتیب بخوان.")}
  <ol class="path prose">{path_li}</ol>
</div></section>""" if path_li else "")
    main = page_hero(meta, "LEARN", crumbs, f'<div class="filters ld" style="--d:4" role="group" aria-label="دسته‌بندی درس‌ها">{chips}</div>') + f"""
<section class="sec sec-tight" aria-labelledby="all-t"><div class="wrap">
  <h2 id="all-t" class="sr">همه‌ی درس‌ها</h2>
  <div class="cards cards-learn" data-filter-scope>{cards}</div>
  <p class="empty" hidden>درس این مسیر به‌زودی می‌آید؛ موضوع‌هایش را پایین‌تر ببین.</p>
</div></section>
{path_sec}
<section class="sec sec-up" aria-labelledby="up-t"><div class="wrap">
  {sec_head("—", "COMING NEXT", '<span id="up-t">درس‌های در راه</span>', "", "موضوع‌هایی که به‌زودی هم ویدیو و هم درس نوشتاری‌شان منتشر می‌شود.")}
  <ol class="up">{up}</ol>
</div></section>
{follow_block("learn")}"""
    ld = [org_ld(), crumbs_ld(crumbs), {"@type": "CollectionPage", "@id": URL + "/learn/#page", "url": URL + "/learn/", "name": meta["title"],
          "description": meta["description"], "inLanguage": "fa", "isPartOf": {"@id": SITE_ID},
          "mainEntity": {"@type": "ItemList", "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "url": URL + a["url"], "name": a["title"]} for i, a in enumerate(arts)]}}]
    render("/learn/", meta, main, kind="learn", ld=ld, og={"key": "learn"}, body_class="p-learn", lessons=arts)


def page_article(a, arts):
    crumbs = [("/", "خانه"), ("/learn/", "آموزش‌ها"), (a["url"], a["title"])]
    toc_items = a["toc"] + ([{"level": 2, "text": "پرسش‌های پرتکرار", "id": "faq"}] if a["faqs"] else [])
    toc = "".join(f'<li><a href="#{t["id"]}"><i>{two(k + 1)}</i><span>{esc(t["text"])}</span></a></li>' for k, t in enumerate(toc_items))
    summary = "".join(f"<li>{inline(s)}</li>" for s in a["summary"])
    same = [b for b in arts if b["slug"] != a["slug"] and b["pillar"] == a["pillar"]]
    other = [b for b in arts if b["slug"] != a["slug"] and b["pillar"] != a["pillar"]]
    related = (same + other)[:3]
    rel_html = "".join(lesson_card(b, i) for i, b in enumerate(related))
    idx = arts.index(a)
    answer = (f'<section class="sum ans" aria-labelledby="ans-t"><h2 id="ans-t">پاسخ کوتاه</h2><p>{inline(a["answer"])}</p></section>'
              if a.get("answer") else "")
    src_items = []
    for line in a.get("sources") or []:
        label, _, href = line.rpartition("|")
        if href.strip().startswith("https://"):
            src_items.append(f'<li><a href="{esc(href.strip())}" target="_blank" rel="noopener">{inline(label.strip())}</a></li>')
    sources = (f'<section class="prose srcs" aria-labelledby="src-t"><h2 id="src-t">منابع</h2><ul>{"".join(src_items)}</ul></section>'
               if src_items else "")
    reel = a.get("reel") or ""
    md = a["media"]
    video = ""
    if md.get("video"):  # the reel itself, self-hosted, at the top of the lesson; the Instagram link under it
        ig = (f'<figcaption><a class="lnk" href="{esc(reel)}" target="_blank" rel="noopener">{IG}'
              f'<span>این ویدیو در اینستاگرام دات‌کوین</span></a></figcaption>' if reel else "")
        video = (f'<figure class="vid rv"><video controls muted playsinline preload="none" data-unmute '
                 f'poster="{md["poster"]}{V}" width="{int(md.get("width") or 720)}" height="{int(md.get("height") or 1280)}" '
                 f'aria-label="ویدیوی {esc(a["title"])}"><source src="{md["video"]}{V}" type="video/mp4"></video>{ig}</figure>')
    yt_id = youtube_id(a.get("youtube") or "")
    yt = (f'<figure class="yt rv"><iframe src="https://www.youtube-nocookie.com/embed/{yt_id}" title="{esc(a["title"])}" '
          f'loading="lazy" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>'
          f'<figcaption><a class="lnk" href="https://www.youtube.com/watch?v={yt_id}" target="_blank" rel="noopener">'
          f'دیدن در یوتیوب</a></figcaption></figure>' if yt_id else "")
    # a lesson made for a long YouTube video (no reel of its own): the player is the lesson's video, no reel box
    reel_block = "" if (video or (yt_id and not reel)) else f"""<aside class="reel rv" aria-label="ویدیوی این درس">
<div class="reel-ph" aria-hidden="true"><img src="/assets/img/logo-192.webp{V}" width="96" height="96" alt="" loading="lazy"><span class="reel-play"></span></div>
<div class="reel-copy"><span class="sec-n" dir="ltr">REEL</span><h2>{'ویدیوی کوتاه این درس' if reel else 'ویدیوی این درس در اینستاگرام'}</h2>
<p>{'همین درس را در یک ویدیوی کوتاه در اینستاگرام دات‌کوین ببین.' if reel else 'ویدیوی کوتاه این درس در صفحه‌ی اینستاگرام دات‌کوین منتشر می‌شود. دنبال کن تا آن را ببینی.'}</p>
<a class="btn btn-solid" href="{esc(reel or SITE['instagram'])}" target="_blank" rel="noopener" data-reel="{esc(reel)}">{IG}<span>{'دیدن ویدیو در اینستاگرام' if reel else 'دنبال کردن <bdi>@dotcoin.me</bdi>'}</span></a></div></aside>"""
    pn = []
    if idx > 0:
        pn.append(f'<a class="pn pn-prev" href="{arts[idx - 1]["url"]}"><span>درس جدیدتر</span><b>{esc(arts[idx - 1]["title"])}</b></a>')
    if idx < len(arts) - 1:
        pn.append(f'<a class="pn pn-next" href="{arts[idx + 1]["url"]}"><span>درس قبلی</span><b>{esc(arts[idx + 1]["title"])}</b></a>')
    main = f"""<article class="art" itemscope itemtype="https://schema.org/Article">
<header class="hero hero-art" aria-labelledby="h1">
  <div class="wrap hero-art-grid">
    <div class="hero-art-copy">
      {crumbs_html(crumbs)}
      <div class="art-meta ld" style="--d:1">{pillar_chip(a['pillar'])}<span>{fa(a['minutes'])} دقیقه مطالعه</span></div>
      <h1 id="h1" class="h-art" itemprop="headline"><span class="ln"><span style="--d:2">{esc(a['title'])}</span></span></h1>
      <p class="hero-lead ld" style="--d:4">{esc(a.get('lead', ''))}</p>
      <div class="byline ld" style="--d:5"><img src="/assets/img/logo-96.webp{V}" width="44" height="44" alt="">
        <span><b itemprop="author">{esc(SITE['author'])}</b><time datetime="{a['date_obj'].isoformat()}" itemprop="datePublished">{jdate(a['date_obj'])}</time></span></div>
    </div>
    <div class="hero-art-art ld" style="--d:3">{motif(a['motif'])}</div>
  </div>
  {giant(a['en'], "giant-page")}
</header>
<div class="wrap art-grid">
  <aside class="toc" aria-label="فهرست این درس"><details open><summary>فهرست این درس</summary><ol>{toc}</ol></details></aside>
  <div class="art-body" itemprop="articleBody">
    {video}{yt}
    {answer}
    <section class="sum" aria-labelledby="sum-t"><h2 id="sum-t"><span dir="ltr">TL;DR</span> خلاصه</h2><ul>{summary}</ul></section>
    <div class="prose">{a['body_html']}</div>
    {sources}
    {reel_block}
    {faq_html(a['faqs'])}
    {vip_cta(a['slug'])}
    <nav class="pns" aria-label="درس‌های دیگر">{''.join(pn)}</nav>
  </div>
</div>
</article>
<section class="sec sec-rel" aria-labelledby="rel-t"><div class="wrap">
  {sec_head("—", "RELATED", '<span id="rel-t">درس‌های مرتبط</span>', f'<a class="lnk sec-more" href="/learn/">همه‌ی درس‌ها {ARROW}</a>')}
  <div class="cards cards-3">{rel_html}</div>
</div></section>
{follow_block(a['slug'])}"""
    # seo/ARTICLE_BRIEF.md §3: the suffix joins the seo_title only while the whole stays <= 60 chars
    seo = a.get("seo_title") or a["title"]
    if not seo.endswith(SITE["title_suffix"].strip()) and len(seo + SITE["title_suffix"]) <= 60:
        seo += SITE["title_suffix"]
    meta = {"title": a["title"], "seo_title": seo,
            "description": a["description"], "og_title": a.get("og_title") or a["title"],
            "og_description": a.get("og_description") or a["description"], "lastmod": a.get("updated") or a["date_obj"].isoformat()}
    img = f"{URL}/og/learn-{a['slug']}.jpg"
    ld = [org_ld(), PERSON, crumbs_ld(crumbs), {
        "@type": "Article", "@id": URL + a["url"] + "#article", "headline": a["title"], "description": a["description"],
        "image": [img], "datePublished": a["date_obj"].isoformat(), "dateModified": a.get("updated") or a["date_obj"].isoformat(),
        "author": {"@id": PERSON["@id"]}, "publisher": {"@id": ORG_ID},
        "mainEntityOfPage": URL + a["url"], "inLanguage": "fa", "articleSection": PILLARS.get(a["pillar"], ""),
        "wordCount": a["words"], "isPartOf": {"@id": SITE_ID}}]
    if a["faqs"]:
        ld.append(faq_ld(a["faqs"]))
    if md.get("video"):
        ld.append({k: v for k, v in {
            "@type": "VideoObject", "@id": URL + a["url"] + "#video", "name": a["title"], "description": a["description"],
            "thumbnailUrl": [URL + md["poster"]], "uploadDate": md.get("upload") or a["date_obj"].isoformat(),
            "contentUrl": URL + md["video"], "duration": md.get("duration"), "inLanguage": "fa"}.items() if v})
    if yt_id and not md.get("video"):  # a long video's own lesson: its YouTube video (a reel lesson has its own copy)
        ld.append({k: v for k, v in {
            "@type": "VideoObject", "@id": URL + a["url"] + "#youtube", "name": a["title"], "description": a["description"],
            "thumbnailUrl": [f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"], "uploadDate": a["date_obj"].isoformat(),
            "embedUrl": f"https://www.youtube.com/embed/{yt_id}", "url": f"https://www.youtube.com/watch?v={yt_id}",
            "duration": a.get("duration") if re.fullmatch(r"PT(\d+H)?(\d+M)?(\d+S)?", str(a.get("duration") or "")) else None,
            "inLanguage": "fa"}.items() if v})
    og_extra = (f'<meta property="article:published_time" content="{a["date_obj"].isoformat()}">\n'
                f'<meta property="article:modified_time" content="{a.get("updated") or a["date_obj"].isoformat()}">\n'
                f'<meta property="article:author" content="{esc(SITE["author"])}">\n'
                f'<meta property="article:section" content="{esc(PILLARS.get(a["pillar"], ""))}">\n')
    render(a["url"], meta, main, kind="article", ld=ld, og_type="article", og_extra=og_extra, body_class="p-article",
           og={"key": f"learn-{a['slug']}", "en": a["en"], "kicker": PILLARS.get(a["pillar"], "")}, lessons=arts)


def page_glossary(terms, arts):
    meta, _ = load_page("glossary")
    crumbs = [("/", "خانه"), ("/glossary/", "واژه‌نامه")]
    letters: dict[str, list] = {}
    for t in terms:
        letters.setdefault(t["letter"], []).append(t)
    order = [ch for ch in "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"]
    have = [ch for ch in letters if ch not in order]
    index = "".join(
        (f'<a href="#l-{k}">{ch}</a>' if ch in letters else f'<span aria-hidden="true">{ch}</span>')
        for k, ch in enumerate(order + have))
    groups = ""
    for k, ch in enumerate(order + have):
        if ch not in letters:
            continue
        items = "".join(
            f'<div class="term" id="{esc(t["slug"])}"><dt><a class="term-a" href="#{esc(t["slug"])}" aria-label="پیوند به {esc(t["term"])}">#</a>'
            f'<span class="term-t">{esc(t["term"])}</span><span class="term-en" dir="ltr">{esc(t["en"])}</span></dt><dd>{esc(t["def"])}</dd></div>'
            for t in letters[ch])
        groups += f'<section class="gl-g" id="l-{k}" aria-label="حرف {ch}"><h2 class="gl-l">{ch}</h2><dl>{items}</dl></section>'
    search = ('<div class="gl-search ld" style="--d:4"><label for="q" class="sr">جست‌وجو در واژه‌نامه</label>'
              '<input id="q" type="search" placeholder="مثلاً «هش» یا Wallet" autocomplete="off">'
              f'<span class="gl-count" aria-live="polite">{fa(len(terms))} واژه</span></div>')
    main = page_hero(meta, "GLOSSARY", crumbs, search) + f"""
<section class="sec sec-tight"><div class="wrap">
  <nav class="gl-index" aria-label="حروف الفبا">{index}</nav>
  <div class="gl">{groups}</div>
  <p class="empty" hidden>واژه‌ای پیدا نشد.</p>
</div></section>
{follow_block("glossary")}"""
    ld = [org_ld(), crumbs_ld(crumbs), {
        "@type": "DefinedTermSet", "@id": URL + "/glossary/#set", "name": meta["title"], "description": meta["description"],
        "url": URL + "/glossary/", "inLanguage": "fa",
        "hasDefinedTerm": [{"@type": "DefinedTerm", "@id": URL + "/glossary/#" + t["slug"], "name": t["term"],
                            "alternateName": t["en"], "description": t["def"], "url": URL + "/glossary/#" + t["slug"],
                            "inDefinedTermSet": URL + "/glossary/#set"} for t in terms]}]
    render("/glossary/", meta, main, kind="glossary", ld=ld, og={"key": "glossary"}, body_class="p-glossary", lessons=arts)


HOW = """<section class="sec sec-how" aria-labelledby="how-t"><div class="wrap">
  <header class="sec-h rv"><span class="sec-n" dir="ltr">(—) HOW IT WORKS</span><h2 class="sec-t" id="how-t">کد دعوت چطور کار می‌کند</h2></header>
  <ol class="how rv">
    <li><b>از دکمه‌ی ثبت‌نام همین صفحه وارد شو</b><span>دکمه‌ها مستقیم به صفحه‌ی ثبت‌نام همان صرافی می‌روند.</span></li>
    <li><b>کد را در خانه‌ی «کد دعوت» یا «کد رفرال» بنویس</b><span>اگر کد خودکار پر نشد، آن را از همین صفحه کپی کن و در فرم ثبت‌نام بچسبان.</span></li>
    <li><b>ثبت‌نام را کامل کن</b><span>کد فقط هنگام ساختن حساب ثبت می‌شود؛ پس پیش از پایان ثبت‌نام واردش کن.</span></li>
  </ol>
</div></section>
"""


def page_exchanges(xs, arts):
    meta, _ = load_page("exchanges")
    crumbs = [("/", "خانه"), ("/exchanges/", "صرافی‌ها")]
    cards = "".join(exchange_card(x, "exchanges", i) for i, x in enumerate(xs))
    how = HOW if any(x["code"] for x in xs) else ""
    main = page_hero(meta, "EXCHANGES", crumbs) + f"""
<section class="sec sec-tight" aria-labelledby="xs-t"><div class="wrap"><h2 id="xs-t" class="sr">سه صرافی</h2><div class="xcards xcards-lg">{cards}</div></div></section>
{how}{follow_block("exchanges")}"""
    ld = [org_ld(), crumbs_ld(crumbs), {"@type": "CollectionPage", "@id": URL + "/exchanges/#page", "url": URL + "/exchanges/",
          "name": meta["title"], "description": meta["description"], "inLanguage": "fa", "isPartOf": {"@id": SITE_ID},
          "mainEntity": {"@type": "ItemList", "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "url": URL + x["url"], "name": f"{x['name']} ({x['name_en']})"} for i, x in enumerate(xs)]}}]
    render("/exchanges/", meta, main, kind="exchanges", ld=ld, og={"key": "exchanges"}, body_class="p-exchanges", lessons=arts)


def page_exchange(x, xs, arts):
    crumbs = [("/", "خانه"), ("/exchanges/", "صرافی‌ها"), (x["url"], x["name"])]
    feats = "".join(f'<li class="rv" style="--i:{i}"><span class="fn">{two(i + 1)}</span><span>{inline(f)}</span></li>' for i, f in enumerate(x["features"]))
    steps = "".join(f'<li class="rv" style="--i:{i}"><span class="sn">{fa(i + 1)}</span><div><b>{esc(t.strip())}</b><p>{inline(s.strip())}</p></div></li>'
                    for i, (t, s) in enumerate(x["steps"]))
    others = "".join(exchange_card(o, x["slug"], i) for i, o in enumerate(o for o in xs if o["slug"] != x["slug"]))
    cta = (f'<div class="x-cta ld" style="--d:4"><a class="btn btn-solid btn-lg" href="{esc(go_link(x, x["slug"]))}" target="_blank" rel="sponsored nofollow noopener">{esc(x["button"])} {ARROW}</a>'
           f'{code_chip(x)}<a class="lnk" href="{esc(x["official"])}" target="_blank" rel="noopener">سایت رسمی {EXT}</a></div>')
    main = f"""<section class="hero hero-page hero-x" aria-labelledby="h1">
  <div class="wrap">
    {crumbs_html(crumbs)}
    <div class="x-head ld" style="--d:1">{logo_img(x, "xlogo-lg")}</div>
    <h1 id="h1" class="h-page h-x"><span class="ln"><span style="--d:2">{esc(x.get('h1') or x['name'])}</span></span></h1>
    <p class="hero-lead ld" style="--d:3">{esc(x.get('lead', ''))}</p>
    {cta}
  </div>
  {giant(x['en'], "giant-page")}
</section>
<div class="wrap art-grid x-grid">
  <aside class="x-side"><div class="x-card"><span class="sec-n" dir="ltr">QUICK START</span>
    <b>{esc(x['name'])}</b>{code_chip(x)}
    <a class="btn btn-solid" href="{esc(go_link(x, x['slug']))}" target="_blank" rel="sponsored nofollow noopener">ثبت‌نام {ARROW}</a></div></aside>
  <div class="art-body">
    <section aria-labelledby="ft-t"><h2 id="ft-t" class="x-h">امکانات اصلی</h2><ul class="feats">{feats}</ul></section>
    <section aria-labelledby="st-t"><h2 id="st-t" class="x-h">ثبت‌نام قدم‌به‌قدم</h2><ol class="steps">{steps}</ol>
      <div class="x-cta x-cta-in"><a class="btn btn-solid btn-lg" href="{esc(go_link(x, x['slug']))}" target="_blank" rel="sponsored nofollow noopener">{esc(x['button'])} {ARROW}</a>{code_chip(x)}</div></section>
    <div class="prose">{x['body_html']}</div>
    {faq_html(x['faqs'])}
  </div>
</div>
<section class="sec sec-rel" aria-labelledby="ox-t"><div class="wrap">
  {sec_head("—", "OTHER EXCHANGES", '<span id="ox-t">صرافی‌های دیگر</span>')}
  <div class="xcards">{others}</div>
</div></section>
{follow_block(x['slug'])}"""
    meta = {"title": x["name"], "seo_title": x.get("seo_title") or f"{x['name']} ({x['name_en']}){SITE['title_suffix']}",
            "description": x["description"], "og_title": x.get("og_title") or f"{x['name']} ({x['name_en']})",
            "og_description": x.get("og_description") or x["description"], "updated": x.get("updated", "")}
    ld = [org_ld(), crumbs_ld(crumbs), {
        "@type": "WebPage", "@id": URL + x["url"] + "#page", "url": URL + x["url"], "name": x.get("seo_title") or x["name"],
        "description": x["description"], "inLanguage": "fa", "isPartOf": {"@id": SITE_ID},
        "dateModified": x.get("updated") or LATEST}]
    if x["faqs"]:
        ld.append(faq_ld(x["faqs"]))
    render(x["url"], meta, main, kind="exchange", ld=ld, og={"key": f"x-{x['slug']}", "en": x["en"], "kicker": "صرافی‌ها"},
           body_class="p-exchange", lessons=arts)


def page_vip(arts, xs):
    """⟨2026-11-18⟩ /vip/: TradeYar's free VIP signal channel, its numbers (TradeYar's public record
    only), what it gives, the three steps with TradeYar's own referral links and codes (tracked per
    placement), the bot, the FAQ (content/pages/vip.md, content/vip.json)."""
    meta, body = load_page("vip")
    crumbs = [("/", "خانه"), ("/vip/", "سیگنال VIP")]
    main_md, faqs = split_faq(body)
    by_slug = {x["slug"]: x for x in xs}
    feats = "".join(f'<li class="rv" style="--i:{i}"><span class="fn">{two(i + 1)}</span><span>{inline(f)}</span></li>'
                    for i, f in enumerate(meta.get("features") or []))
    steps_src = [x.split("|", 1) for x in (meta.get("steps") or []) if "|" in x]
    cards = ""
    for i, x in enumerate(VIP["exchanges"]):
        base = by_slug.get(x["slug"]) or {"name": x["slug"], "name_en": x["slug"], "en": x["slug"].upper()}
        chip = {**x, "code_label": x.get("code_label") or "کد دعوت"}
        cards += f"""<article class="xc vip-x rv" style="--i:{i}">
<div class="xc-top">{logo_img(base) if base.get("logo") else ""}<span class="xc-en" dir="ltr">{esc(base.get("en", ""))}</span></div>
<h3 class="xc-t">{esc(base.get("name", ""))} <span dir="ltr">{esc(base.get("name_en", ""))}</span></h3>
<p class="xc-l">{esc(x.get("note") or "")}</p>{code_chip(chip)}
<div class="xc-act"><a class="btn btn-solid" href="/go/vip-{esc(x['slug'])}/" {REL_TY}>{esc(x["button"])} {ARROW}</a></div></article>"""
    steps = ""
    for i, (t, txt) in enumerate(steps_src):
        txt = txt.strip().replace("{min}", fa(VIP["min_usdt"]))
        extra = ""
        if i == 0:
            extra = f'<div class="xcards vip-xs">{cards}</div>'
        elif i == 2:
            extra = (f'<div class="x-cta"><a class="btn btn-solid btn-lg" href="{vip_go("steps")}" {REL_TY}>باز کردن ربات '
                     f'<bdi>@{esc(VIP["bot"])}</bdi> {ARROW}</a></div>')
        steps += f'<li class="rv" style="--i:{i}"><span class="sn">{fa(i + 1)}</span><div><b>{esc(t.strip())}</b><p>{inline(txt)}</p>{extra}</div></li>'
    keep = (f'<p class="vip-keep">شرط ماندن در کانال: موجودی حساب از {fa(VIP["keep_usdt"])} تتر کمتر نشود. '
            "پول همیشه در حساب خود توست.</p>")
    hero_cta = (f'<div class="hero-cta ld" style="--d:4"><a class="btn btn-solid btn-lg" href="#steps">سه قدم تا کانال VIP {ARROW}</a>'
                f'<a class="btn btn-line btn-lg" href="{vip_go("hero")}" {REL_TY}>ربات تریدیار</a></div>')
    stats = vip_stats_html("vs-band")
    record = f'<a class="lnk sec-more" href="{esc(VIP["record"])}" {REL_TY}>کارنامه‌ی کامل {EXT}</a>'
    head = sec_head("01", "THE RECORD", '<span id="vs-t">کارنامه‌ی عمومی، با عدد</span>', record,
                    "هر سیگنال پیش از نتیجه در تلگرام منتشر می‌شود و با کد یکتای خودش در کارنامه می‌ماند، برد یا باخت.")
    stats_sec = (f'<section class="sec sec-tight vip-stats" aria-labelledby="vs-t"><div class="wrap">{head}{stats}</div></section>'
                 if stats else "")
    faq_sec = (markdown(main_md, h2_numbers=False)[0] if main_md.strip() else "") + faq_html(faqs)
    main = page_hero(meta, "VIP", crumbs, hero_cta, "hero-vip") + f"""
{stats_sec}
<section class="sec sec-tight" aria-labelledby="vf-t"><div class="wrap">
  {sec_head("02", "WHAT YOU GET", '<span id="vf-t">VIP چه می‌دهد</span>')}
  <ul class="feats">{feats}</ul>
</div></section>
<section class="sec sec-tight" id="steps" aria-labelledby="st-t"><div class="wrap vip-steps">
  {sec_head("03", "THREE STEPS", '<span id="st-t">ورود رایگان در سه قدم</span>', "", "حساب صرافی و پولت همیشه مال خودت می‌ماند.")}
  <ol class="steps">{steps}</ol>
  {keep}
</div></section>
<section class="sec sec-tight"><div class="wrap vip-faq">{faq_sec}</div></section>
<section class="sec vip-end" aria-labelledby="ve-t"><div class="wrap"><div class="vipcta vipcta-end">
<div class="vipcta-copy"><span class="sec-n" dir="ltr">@{esc(VIP["bot"])}</span><h2 id="ve-t">ربات تریدیار، قدم آخر</h2>
<p>حساب ساختی و شارژش کردی؟ UID را در ربات بفرست؛ بررسی خودکار است و لینک کانال VIP همان‌جا می‌رسد.</p>
<div class="vipcta-act"><a class="btn btn-acc btn-lg" href="{vip_go("final")}" {REL_TY}>ارسال UID در ربات {ARROW}</a></div></div>
<div class="vipcta-mark" aria-hidden="true" dir="ltr"><span>VIP</span></div></div></div></section>
{follow_block("vip")}"""
    ld = [org_ld(), crumbs_ld(crumbs), {"@type": "WebPage", "@id": URL + "/vip/#page", "url": URL + "/vip/",
          "name": meta["title"], "description": meta["description"], "inLanguage": "fa", "isPartOf": {"@id": SITE_ID},
          "dateModified": meta.get("updated") or LATEST}]
    if faqs:
        ld.append(faq_ld(faqs))
    render("/vip/", meta, main, kind="vip", ld=ld, og={"key": "vip", "en": meta.get("og_en") or "VIP",
           "kicker": meta.get("og_kicker") or ""}, body_class="p-vip", lessons=arts)


def page_about(arts, terms):
    meta, body = load_page("about")
    crumbs = [("/", "خانه"), ("/about/", "درباره")]
    body_html, _ = markdown(body)
    main = page_hero(meta, "ABOUT", crumbs) + f"""
<div class="wrap about-grid">
  <figure class="about-mark rv"><img src="/assets/img/logo-640.webp{V}" width="640" height="640" alt="بهنام جلالی، سازنده‌ی دات‌کوین" loading="lazy" decoding="async"><figcaption>بهنام جلالی · سازنده‌ی دات‌کوین</figcaption></figure>
  <div class="prose about-prose">{body_html}
    <div class="about-links"><a class="btn btn-solid" href="{SITE['instagram']}" target="_blank" rel="noopener">{IG}<span>اینستاگرام <bdi>@dotcoin.me</bdi></span></a><a class="btn btn-line" href="{SITE['youtube']}" target="_blank" rel="noopener">{YT}<span>یوتیوب دات‌کوین</span></a></div>
  </div>
</div>
{follow_block("about")}"""
    ld = [org_ld(), crumbs_ld(crumbs), PERSON, {"@type": "AboutPage", "@id": URL + "/about/#page", "url": URL + "/about/", "name": meta["title"],
          "description": meta["description"], "inLanguage": "fa", "about": {"@id": ORG_ID}, "isPartOf": {"@id": SITE_ID}}]
    render("/about/", meta, main, kind="about", ld=ld, og={"key": "about"}, body_class="p-about", lessons=arts)


def page_404(arts):
    meta, _ = load_page("404")
    main = f"""<section class="hero hero-404" aria-labelledby="h1"><div class="wrap nf">
  <div class="nf-art ld" style="--d:1">{motif("broken")}</div>
  <div><h1 id="h1" class="h-page"><span class="ln"><span style="--d:2">{esc(meta['title'])}</span></span></h1>
  <p class="hero-lead ld" style="--d:3">{esc(meta['lead'])}</p>
  <div class="hero-cta ld" style="--d:4"><a class="btn btn-solid btn-lg" href="/">صفحه‌ی اصلی {ARROW}</a><a class="btn btn-line btn-lg" href="/learn/">آموزش‌ها</a><a class="btn btn-line btn-lg" href="/glossary/">واژه‌نامه</a><a class="btn btn-line btn-lg" href="/exchanges/">صرافی‌ها</a></div>
  <ul class="nf-list ld" style="--d:5">{"".join(f'<li><a href="{a["url"]}">{esc(a["title"])}</a></li>' for a in arts[:6])}</ul></div>
</div>{giant("404", "giant-page")}</section>"""
    render("/404.html", meta, main, kind="404", ld=[], og={"key": "home", "en": "DOTCOIN"}, body_class="p-404", lessons=arts)
    OG_JOBS.pop()  # the 404 reuses the home card


# ---------------------------------------------------------------- files around the pages
def write_meta_files(arts):
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in PAGES:
        sm.append(f"<url><loc>{p['loc']}</loc><lastmod>{p['lastmod']}</lastmod></url>")
    sm.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(sm) + "\n", "utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /go/\n\nSitemap: {URL}/sitemap.xml\n", "utf-8")
    items = "".join(
        f"<item><title>{esc(a['title'])}</title><link>{URL}{a['url']}</link><guid>{URL}{a['url']}</guid>"
        f"<pubDate>{a['date_obj'].strftime('%a, %d %b %Y')} 00:00:00 +0000</pubDate><description>{esc(a['description'])}</description></item>"
        for a in arts)
    (DIST / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{esc(SITE['name_fa'])}</title><link>{URL}/</link><description>{esc(SITE['tagline'])}</description>"
        f"<language>fa-IR</language>{items}</channel></rss>\n", "utf-8")
    (DIST / "site.webmanifest").write_text(json.dumps({
        "name": SITE["name"], "short_name": SITE["name_fa"], "lang": "fa", "dir": "rtl", "start_url": "/",
        "display": "standalone", "background_color": "#000000", "theme_color": "#F3C242",
        "icons": [{"src": "/assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/assets/img/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, ensure_ascii=False), "utf-8")
    (DIST / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  X-Frame-Options: SAMEORIGIN\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n  Access-Control-Allow-Origin: *\n"
        "/og/*\n  Cache-Control: public, max-age=86400\n"
        "/media/*\n  Cache-Control: public, max-age=604800\n"
        "https://:project.pages.dev/*\n  X-Robots-Tag: noindex\n", "utf-8")
    # referral links: built from content/exchanges.json, the one place to change a link
    red = ["# referral links (from content/exchanges.json)"]
    for x in load_exchanges():
        target = x["link"].replace("{page}", "site")
        red += [f"/go/{x['slug']}/ {target} 302", f"/go/{x['slug']} {target} 302"]
    if VIP:  # ⟨2026-11-18⟩ TradeYar's tracker, one placement per link (its clicks counted there)
        red.append("# TradeYar's VIP (from content/vip.json; src=dotcoin, pl=<placement>)")
        for pl in VIP["placements"]:
            target = VIP["bot_link"].replace("{pl}", pl)
            red += [f"/go/vip-{pl}/ {target} 302", f"/go/vip-{pl} {target} 302"]
        for x in VIP["exchanges"]:
            target = x["link"].replace("{pl}", "vip_page")
            red += [f"/go/vip-{x['slug']}/ {target} 302", f"/go/vip-{x['slug']} {target} 302"]
        red += [f"/go/vip/ {VIP['bot_link'].replace('{pl}', 'site')} 302"]
    (DIST / "_redirects").write_text("\n".join(red) + "\n", "utf-8")
    # ⟨2026-11-18⟩ IndexNow (Bing, Yandex…): the key is public by design, served at the site's root
    key = str(SITE.get("indexnow") or "")
    if re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
        (DIST / f"{key}.txt").write_text(key, "utf-8")


def write_og_sources():
    od = DIST / "_og"
    od.mkdir(parents=True, exist_ok=True)
    for j in OG_JOBS:
        en = j["en"]
        giant_size = min(300, int(1088 * float(fit(en))))
        title = j["title"]
        title_size = 80 if len(title) <= 24 else 66 if len(title) <= 40 else 56
        (od / f"{j['key']}.html").write_text(isolate_html(fill(_OG, {
            "en": esc(en), "kicker": esc(j["kicker"]), "title": esc(title),
            "giant_size": giant_size, "title_size": title_size})), "utf-8")
    (od / "jobs.json").write_text(json.dumps([j["key"] for j in OG_JOBS]), "utf-8")


def copy_assets():
    if not (PRIVATE / "fonts").is_dir():
        sys.exit("private/ is missing: run tools/prep_assets.py first (deploy.sh does it)")
    shutil.copytree(PRIVATE / "fonts", DIST / "assets" / "fonts")
    shutil.copytree(PRIVATE / "img", DIST / "assets" / "img")
    shutil.copy2(PRIVATE / "img" / "favicon.ico", DIST / "favicon.ico")
    (DIST / "assets" / "js").mkdir(parents=True)
    js = (STATIC / "js" / "site.js").read_text("utf-8")
    (DIST / "assets" / "js" / "site.js").write_text(js, "utf-8")
    if (STATIC / "exchanges").is_dir():
        shutil.copytree(STATIC / "exchanges", DIST / "assets" / "exchanges")


def main() -> int:
    global V, CSS
    keep_og = None
    if (DIST / "og").is_dir() and os.environ.get("DOTCOIN_KEEP_OG") == "1":
        keep_og = DIST.parent / ".og-keep"
        shutil.rmtree(keep_og, ignore_errors=True)
        shutil.move(DIST / "og", keep_og)
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True)
    copy_assets()
    if keep_og:
        shutil.move(keep_og, DIST / "og")
    V = version_token()
    CSS = minify_css((STATIC / "css" / "site.css").read_text("utf-8")).replace(".woff2)", f".woff2{V})")
    arts, xs, terms = load_articles(), load_exchanges(), load_glossary()
    for a in arts:
        if a["media"].get("video"):
            (DIST / "media").mkdir(exist_ok=True)
            for ext in ("mp4", "jpg"):
                shutil.copy2(MEDIA / f"{a['slug']}.{ext}", DIST / "media" / f"{a['slug']}.{ext}")
    global LATEST
    LATEST = max((a.get("updated") or a["date_obj"].isoformat()) for a in arts) if arts else TODAY.isoformat()
    page_home(arts, xs, terms)
    page_learn(arts)
    for a in arts:
        page_article(a, arts)
    page_glossary(terms, arts)
    page_exchanges(xs, arts)
    for x in xs:
        page_exchange(x, xs, arts)
    page_about(arts, terms)
    if VIP:
        page_vip(arts, xs)
    page_404(arts)
    write_meta_files(arts)
    write_og_sources()
    problems = lint_dist()
    if problems:
        print(f"bidi lint: {len(problems)} problem(s); the build stops (see the bidi notes in build.py):", file=sys.stderr)
        for line in problems:
            print("  " + line, file=sys.stderr)
        return 1
    print(f"built {len(PAGES) + 1} pages ({len(arts)} lessons, {len(xs)} exchanges, {len(terms)} terms) -> {DIST}")
    for a in arts:
        print(f"  {a['slug']}: {a['words']} words, {len(a['faqs'])} FAQ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
