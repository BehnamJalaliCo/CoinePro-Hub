#!/usr/bin/env python3
"""Headless Chromium for the site: OG cards and review screenshots.

  render.py og    DIST            -> DIST/og/<key>.jpg from DIST/_og/<key>.html, then removes DIST/_og
  render.py shots DIST OUT [path …] -> OUT/<name>-{desktop,phone}[-dark].png (full page)

Runs with any Python that has Playwright + Chromium (the studio's venv-render on the hub).
"""
import glob
import json
import os
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def chrome():
    """The Chromium the kits use (its Playwright build may be newer than the Python package)."""
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    found = sorted(glob.glob(f"{base}/chromium-*/chrome-linux*/chrome"))
    return found[-1] if found else None


def launch(p):
    return p.chromium.launch(executable_path=chrome(), headless=True, args=["--no-sandbox", "--font-render-hinting=none"])


BASE = "http://dotcoin.local"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2",
         ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json",
         ".xml": "application/xml", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}


def serve_from(ctx, root: Path) -> None:
    """Answer every request from the dist folder (no socket: the studio user has no loopback server)."""
    def handle(route):
        path = route.request.url[len(BASE):].split("?")[0].split("#")[0]
        f = root / path.lstrip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="", content_type="text/plain")
        route.fulfill(status=200, body=f.read_bytes(), content_type=TYPES.get(f.suffix, "application/octet-stream"))
    ctx.route(BASE + "/**", handle)
    ctx.route(lambda url: not url.startswith(BASE) and not url.startswith("data:"), lambda r: r.abort())


def og(dist: Path) -> None:
    src = dist / "_og"
    keys = json.loads((src / "jobs.json").read_text())
    (dist / "og").mkdir(exist_ok=True)
    base = BASE
    with sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        serve_from(ctx, dist)
        page = ctx.new_page()
        for k in keys:
            page.goto(f"{base}/_og/{k}.html", wait_until="load")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(dist / "og" / f"{k}.jpg"), type="jpeg", quality=88)
        b.close()
    shutil.rmtree(src)
    print(f"og: {len(keys)} cards")


def shots(dist: Path, out: Path, paths: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    base = BASE
    views = {"desktop": dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1),
             "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)}
    with sync_playwright() as p:
        b = launch(p)
        for path in paths:
            theme = "light"
            if path.endswith("@dark"):
                path, theme = path[:-5], "dark"
            name = path.strip("/").replace("/", "_") or "home"
            for vname, opts in views.items():
                ctx = b.new_context(**opts, color_scheme=theme, reduced_motion="no-preference")
                serve_from(ctx, dist)
                page = ctx.new_page()
                page.goto(base + path, wait_until="load")
                page.evaluate("document.fonts.ready")
                # scroll through so every reveal plays, then back to the top
                page.evaluate("""async () => { for (let y = 0; y < document.body.scrollHeight; y += 400) { window.scrollTo({top: y, behavior: "instant"}); await new Promise(r => setTimeout(r, 90)); } window.scrollTo({top: 0, behavior: "instant"}); }""")
                held = page.evaluate("document.querySelectorAll('.rv-wait:not(.in)').length")
                if held:
                    print(f"  {path} {vname}: {held} reveals still held after scrolling")
                page.wait_for_timeout(1800)
                suffix = "" if theme == "light" else "-dark"
                page.screenshot(path=str(out / f"{name}-{vname}{suffix}.png"), full_page=True)
                ctx.close()
        b.close()
    print(f"shots: {len(paths)} pages -> {out}")


if __name__ == "__main__":
    mode, dist = sys.argv[1], Path(sys.argv[2]).resolve()
    if mode == "og":
        og(dist)
    else:
        shots(dist, Path(sys.argv[3]).resolve(), sys.argv[4:] or ["/"])
