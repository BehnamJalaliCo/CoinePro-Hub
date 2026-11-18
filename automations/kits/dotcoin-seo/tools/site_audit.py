#!/usr/bin/env python3
"""The on-page and technical SEO audit of a built site (stdlib):

    python3 -I KIT/tools/site_audit.py work/dist site/automations/sites/dotcoin > work/audit.md

Every page of dist/ (not the 404, the OG sources or the media): one <title> (≤ 60 characters
warned), a meta description (110–165 characters warned), the canonical equal to its own URL, one
<h1>, JSON-LD that parses (its types listed), every <img> with an alt attribute, every internal
link resolving to a page or file of the build (or a /go/ redirect of _redirects), no hreflang (the
site is Persian only), duplicate titles and descriptions, pages no other page links to, the
sitemap's URLs against the indexable pages and their lastmod. Prints a table per page and ends
with «ERRORS: n» (an error is something to fix before packing; a warning is a judgement call).
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

URL = "https://dotcoin.me"


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title, self.desc, self.canonical, self.robots = "", None, None, ""
        self.h1 = 0
        self.h2 = 0
        self.ld: list[str] = []
        self.imgs_no_alt: list[str] = []
        self.links: list[str] = []
        self.hreflang = 0
        self._in = ""
        self._buf: list[str] = []
        self.text_len = 0
        self._main = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in, self._buf = "title", []
        elif tag == "meta" and a.get("name") == "description":
            self.desc = a.get("content") or ""
        elif tag == "meta" and a.get("name") == "robots":
            self.robots = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "link" and a.get("hreflang"):
            self.hreflang += 1
        elif tag == "h1":
            self.h1 += 1
        elif tag == "h2":
            self.h2 += 1
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in, self._buf = "ld", []
        elif tag == "img" and "alt" not in a:
            self.imgs_no_alt.append(a.get("src") or "?")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "main":
            self._main += 1

    def handle_endtag(self, tag):
        if tag == "title" and self._in == "title":
            self.title, self._in = "".join(self._buf).strip(), ""
        elif tag == "script" and self._in == "ld":
            self.ld.append("".join(self._buf))
            self._in = ""
        elif tag == "main":
            self._main -= 1

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)
        elif self._main > 0:
            self.text_len += len(data.split())


def page_path(dist: Path, f: Path) -> str:
    rel = "/" + str(f.relative_to(dist))
    return rel[: -len("index.html")] if rel.endswith("index.html") else rel


def resolves(dist: Path, href: str, redirects: set[str]) -> bool:
    path = href.split("#")[0].split("?")[0]
    if not path:
        return True
    if path.rstrip("/") in redirects or path in redirects:
        return True
    p = dist / path.lstrip("/")
    return p.is_file() or (p / "index.html").is_file()


def main() -> int:
    dist = Path(sys.argv[1])
    errors, warns = [], []
    redirects = set()
    rf = dist / "_redirects"
    if rf.exists():
        for line in rf.read_text("utf-8").splitlines():
            if line and not line.startswith("#"):
                redirects.add(line.split()[0].rstrip("/"))
    pages: dict[str, Page] = {}
    for f in sorted(dist.rglob("index.html")):
        parts = f.relative_to(dist).parts
        if parts[0] in ("media", "_og", "og", "assets"):
            continue
        p = Page()
        p.feed(f.read_text("utf-8"))
        pages[page_path(dist, f)] = p
    inbound: dict[str, set[str]] = defaultdict(set)
    titles, descs = defaultdict(list), defaultdict(list)
    out = ["# Site audit", "", "| page | title | desc | h1 | h2 | words | JSON-LD | notes |", "|---|---|---|---|---|---|---|---|"]
    for path, p in pages.items():
        notes = []
        indexable = "noindex" not in p.robots
        if not p.title:
            errors.append(f"{path}: no <title>")
        elif len(p.title) > 60:
            warns.append(f"{path}: title {len(p.title)} characters")
        if p.desc is None or not p.desc.strip():
            errors.append(f"{path}: no meta description")
        elif not 110 <= len(p.desc) <= 165:
            warns.append(f"{path}: description {len(p.desc)} characters")
        if p.canonical != URL + path:
            errors.append(f"{path}: canonical {p.canonical!r}")
        if p.h1 != 1:
            errors.append(f"{path}: {p.h1} <h1>")
        if p.hreflang:
            warns.append(f"{path}: hreflang present (the site is Persian only)")
        types = []
        for raw in p.ld:
            try:
                d = json.loads(raw)
                for node in d.get("@graph", [d]):
                    t = node.get("@type")
                    types += t if isinstance(t, list) else [t]
            except ValueError:
                errors.append(f"{path}: JSON-LD does not parse")
        for src in p.imgs_no_alt:
            errors.append(f"{path}: <img> without alt ({src[:60]})")
        for href in p.links:
            if href.startswith(URL):
                href = href[len(URL):] or "/"
            if href.startswith("/") and not href.startswith("//"):
                if not resolves(dist, href, redirects):
                    errors.append(f"{path}: broken internal link {href}")
                target = href.split("#")[0].split("?")[0]
                if target != path:
                    inbound[target].add(path)
        if indexable:
            titles[p.title].append(path)
            descs[p.desc].append(path)
        else:
            notes.append("noindex")
        out.append(f"| {path} | {len(p.title)} | {len(p.desc or '')} | {p.h1} | {p.h2} | {p.text_len} | "
                   f"{', '.join(sorted({str(t) for t in types if t}))} | {' '.join(notes)} |")
    for t, ps in titles.items():
        if len(ps) > 1:
            errors.append(f"the same title on {ps}")
    for d, ps in descs.items():
        if d and len(ps) > 1:
            warns.append(f"the same description on {ps}")
    # orphans: only the nav and footer link to it (every page links to them), or nothing does
    common = set.intersection(*[set(h.split('#')[0] for h in p.links if h.startswith('/')) for p in pages.values()]) if pages else set()
    for path in pages:
        if path in ("/", "/404.html") or path in common:
            continue
        if not inbound.get(path):
            warns.append(f"{path}: no other page links to it")
    sm = dist / "sitemap.xml"
    if sm.exists():
        xml = sm.read_text("utf-8")
        locs = set(re.findall(r"<loc>https://dotcoin\.me([^<]*)</loc>", xml))
        idx = {p for p, pg in pages.items() if "noindex" not in pg.robots and p != "/404.html"}
        for p in sorted(idx - locs):
            errors.append(f"{p}: indexable, not in the sitemap")
        for p in sorted(locs - set(pages)):
            errors.append(f"sitemap lists {p}, no such page")
        for lm in re.findall(r"<lastmod>([^<]*)</lastmod>", xml):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", lm):
                errors.append(f"sitemap lastmod {lm!r}")
    else:
        errors.append("no sitemap.xml")
    out += ["", f"## Warnings ({len(warns)})", ""] + [f"- {w}" for w in warns]
    out += ["", f"## Errors ({len(errors)})", ""] + [f"- {e}" for e in errors]
    out += ["", f"PAGES: {len(pages)}", f"ERRORS: {len(errors)}"]
    print("\n".join(out))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
