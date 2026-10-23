"""The hub's own PDFs for its system sources (prompt 14 §7): the hub's
existing libraries only (resvg-py renders each A4 page from SVG text in
IRANYekanX, right to left; Pillow binds the pages into one PDF), in a child
process (hq_common.untrusted). The text the page shows is filed with the
record as its text (`text_layer`: the hub wrote it, so it needs no OCR).
"""

from __future__ import annotations

import asyncio
import html
from pathlib import Path
from typing import Any

from hq_common import untrusted

A4 = (1240, 1754)  # 150 dpi
MARGIN = 90
SIZE = 24
LEADING = 1.6
PER_LINE = 78  # characters of IRANYekanX at SIZE across the text width
MAX_PAGES = 60
FONT = "IRANYekanX"
FONT_FILES = ("IRANYekanX-Regular.ttf", "IRANYekanX-Bold.ttf")
LIMITS = untrusted.Limits(memory_mb=512, cpu_s=60, deadline_s=90.0, write_mb=120, network=False)


def wrap(text: str, per_line: int = PER_LINE) -> list[str]:
    out: list[str] = []
    for para in text.splitlines():
        if not para.strip():
            out.append("")
            continue
        line = ""
        for word in para.split():
            cand = f"{line} {word}".strip()
            if len(cand) > per_line and line:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return out


def pages_of(title: str, body: str) -> list[list[tuple[str, bool]]]:
    lines = [(t, True) for t in wrap(title)] + [("", False)] + [(t, False) for t in wrap(body)]
    per_page = int((A4[1] - 2 * MARGIN) / (SIZE * LEADING))
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    return pages[:MAX_PAGES]


def page_svg(lines: list[tuple[str, bool]], n: int, total: int, footer: str) -> str:
    w, h = A4
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>',
    ]
    y: float = MARGIN
    for text, bold in lines:
        y += SIZE * LEADING
        if not text:
            continue
        parts.append(
            f'<text x="{w - MARGIN}" y="{y:.0f}" font-family="{FONT}" font-size="{SIZE + (6 if bold else 0)}" '
            f'font-weight="{700 if bold else 400}" fill="#111216" direction="rtl" unicode-bidi="embed" '
            f'text-anchor="end">{html.escape(text)}</text>'
        )
    parts.append(
        f'<text x="{MARGIN}" y="{h - MARGIN / 2:.0f}" font-family="{FONT}" font-size="14" fill="#5B6170">'
        f"{html.escape(footer)} · {n}/{total}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def render_job(title: str, body: str, footer: str, out: str, font_dir: str) -> dict[str, Any]:
    """In the child: every page through resvg, then one PDF through Pillow."""
    import io

    import resvg_py
    from PIL import Image

    fonts = [str(Path(font_dir) / f) for f in FONT_FILES if (Path(font_dir) / f).exists()]
    pages = pages_of(title, body)
    images = []
    for i, lines in enumerate(pages, start=1):
        png = bytes(
            resvg_py.svg_to_bytes(
                svg_string=page_svg(lines, i, len(pages), footer),
                skip_system_fonts=True,
                font_files=fonts,
                font_family=FONT,
            )
        )
        images.append(Image.open(io.BytesIO(png)).convert("RGB"))
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    return {"pages": len(images), "fonts": len(fonts)}


async def render(hub: Any, title: str, body: str, footer: str = "CoinePro HQ") -> tuple[bytes, int]:
    """-> (the PDF's bytes, its page count)."""
    out = hub.storage.scratch()
    try:
        got = await untrusted.run(
            "hq_api.archive.pdf:render_job",
            kwargs={
                "title": title,
                "body": body,
                "footer": footer,
                "out": str(out),
                "font_dir": hub.settings.fonts_dir,
            },
            limits=LIMITS,
        )
        if not got.ok or not isinstance(got.value, dict):
            raise RuntimeError(f"pdf render failed: {got.killed or got.error}"[:200])
        return await asyncio.to_thread(out.read_bytes), int(got.value["pages"])
    finally:
        out.unlink(missing_ok=True)
