"""The hub's own PDFs for its system sources (prompt 14 §7): the hub's
existing libraries only (resvg-py renders each A4 page from SVG text in
IRANYekanX, right to left; Pillow binds the pages into one PDF), in a child
process (hq_common.untrusted). The text the page shows is filed with the
record as its text (`text_layer`: the hub wrote it, so it needs no OCR).
⟨19.2⟩ The body's markdown is laid out, not printed: headings bold, and
every table (a header row, its rule, its rows) drawn as a real grid of cells
whose header repeats on each page; a table wider than GRID_MAX columns is
drawn record by record (column | value).
"""

from __future__ import annotations

import asyncio
import html
import re
from pathlib import Path
from typing import Any

from hq_common import untrusted

A4 = (1240, 1754)  # 150 dpi
MARGIN = 90
SIZE = 24
LEADING = 1.6
PER_LINE = 78  # characters of IRANYekanX at SIZE across the text width
# ⟨1.10.1⟩ no silent cut at 60 pages: a whole document (a company's catalogue) is
# rendered page by page; only past MAX_PAGES (a broken input) is it cut, and
# its last page says so
MAX_PAGES = 3000
FONT = "IRANYekanX"
FONT_FILES = ("IRANYekanX-Regular.ttf", "IRANYekanX-Bold.ttf")
LIMITS = untrusted.Limits(memory_mb=512, cpu_s=60, deadline_s=90.0, write_mb=120, network=False)


def limits_for(chars: int) -> untrusted.Limits:
    """⟨1.10.1⟩ a long document (a whole catalogue) gets the time its pages
    need (about a page per 4 000 characters); memory stays one page."""
    extra = chars // 1500
    return untrusted.Limits(
        memory_mb=LIMITS.memory_mb,
        cpu_s=min(1800, LIMITS.cpu_s + extra),
        deadline_s=min(1900.0, LIMITS.deadline_s + extra),
        write_mb=min(2000, LIMITS.write_mb + chars // 2000),
        network=False,
    )


# ⟨19.2⟩ real tables: a markdown table of the body (a header row, its rule,
# its rows) is drawn as a grid of cells, its header repeated on every page
TSIZE = 18
TLEAD = 1.45
PAD = 8
CHAR_W = 0.57  # IRANYekanX's average glyph width per pixel of size (78 at 24 across 1060)
GRID_MAX = 7  # wider tables: each row drawn as its own two-column grid (column | value)
INK = "#111216"
RULE = "#C9CDD6"
HEAD = "#EEF0F4"
MD_ROW = re.compile(r"^\s*\|(.*)\|\s*$")
MD_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
PERSIAN = re.compile("[\u0600-\u06ff]")


def _bidi(text: str) -> str:
    """A line with Persian in it is embedded right to left (RLE ... PDF), so
    its final full stop and a leading dash sit where a reader expects them;
    a Latin-only line (a path, an image) is left as it is."""
    return f"\u202b{text}\u202c" if PERSIAN.search(text) else text


def wrap(text: str, per_line: int = PER_LINE) -> list[str]:
    out: list[str] = []
    for para in text.splitlines():
        if not para.strip():
            out.append("")
            continue
        line = ""
        for word in para.split():
            # a word longer than the line (a path, a digest) is split, never runs off the page
            while len(word) > per_line:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:per_line])
                word = word[per_line:]
            cand = f"{line} {word}".strip()
            if len(cand) > per_line and line:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return out


def split_row(line: str) -> list[str]:
    """The cells of a markdown table row (a backslash before a pipe keeps it
    inside the cell)."""
    m = MD_ROW.match(line)
    inner = m.group(1) if m else line
    cells, cur, i = [], "", 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner) and inner[i + 1] in "|\\":
            cur += inner[i + 1]
            i += 2
            continue
        if ch == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return ["" if c == "—" else c for c in cells]


Block = tuple[Any, ...]  # ("text", text, bold, size) | ("table", columns, rows)


def blocks_of(title: str, body: str) -> list[Block]:
    out: list[Block] = [("text", title, True, SIZE + 6), ("text", "", False, SIZE)]
    lines = body.splitlines()
    first = next((n for n, x in enumerate(lines) if x.strip()), None)
    if (
        first is not None
        and (h := HEADING.match(lines[first]))
        and h.group(2).strip() == title.strip()
    ):
        lines = lines[first + 1 :]  # the title is already on the page
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines) and MD_ROW.match(line) and MD_RULE.match(lines[i + 1]):
            cols = split_row(line)
            rows = []
            i += 2
            while i < len(lines) and MD_ROW.match(lines[i]):
                rows.append(split_row(lines[i]))
                i += 1
            width = max([len(cols), *(len(r) for r in rows)])
            cols += [""] * (width - len(cols))
            out.append(("table", cols, [r + [""] * (width - len(r)) for r in rows]))
            continue
        h = HEADING.match(line)
        if h:
            out.append(
                ("text", h.group(2).replace("**", ""), True, SIZE + max(0, 8 - 2 * len(h.group(1))))
            )
        else:
            out.append(("text", line.replace("**", ""), False, SIZE))
        i += 1
    return out


Op = tuple[Any, ...]  # ("t", x, y, text, size, bold) | ("r", x, y, w, h, fill)


class _Pages:
    """Ops laid out top to bottom, a new page when the next piece does not fit."""

    def __init__(self) -> None:
        self.pages: list[list[Op]] = [[]]
        self.y: float = MARGIN
        self.bottom = A4[1] - MARGIN

    def room(self) -> float:
        return self.bottom - self.y

    def new(self) -> None:
        self.pages.append([])
        self.y = MARGIN

    def add(self, op: Op) -> None:
        self.pages[-1].append(op)


def _widths(cols: list[str], rows: list[list[str]], total: float) -> list[float]:
    """Each column at least as wide as its longest word (up to 18 characters:
    a status or a port never breaks mid-word), the rest shared by how long
    its cells run."""
    n = len(cols)
    char = TSIZE * CHAR_W
    sample = [cols, *rows[:500]]
    floor, want = [], []
    for c in range(n):
        cells = [r[c] for r in sample if c < len(r)]
        word = max((len(w) for t in cells for w in t.split()), default=1)
        floor.append((min(max(word, 3), 18) + 1) * char + 2 * PAD)
        want.append((min(max(max((len(t) for t in cells), default=1), 3), 50) + 1) * char + 2 * PAD)
    if sum(floor) >= total:
        return [total * f / sum(floor) for f in floor]
    extra = [w - f for w, f in zip(want, floor, strict=True)]
    spare = total - sum(floor)
    if sum(extra) <= 0:
        return [f + spare / n for f in floor]
    return [f + spare * e / sum(extra) for f, e in zip(floor, extra, strict=True)]


def _cell_lines(text: str, width: float) -> list[str]:
    per = max(3, int((width - 2 * PAD) / (TSIZE * CHAR_W)))
    return wrap(text, per) or [""]


def _grid(pg: _Pages, cols: list[str], rows: list[list[str]]) -> None:
    total = A4[0] - 2 * MARGIN
    widths = _widths(cols, rows, total)
    line_h = TSIZE * TLEAD

    def draw(cells: list[list[str]], head: bool) -> None:
        h = max(len(c) for c in cells) * line_h + 2 * PAD
        right = float(A4[0] - MARGIN)
        for lines, w in zip(cells, widths, strict=True):
            pg.add(("r", right - w, pg.y, w, h, HEAD if head else "#FFFFFF"))
            for k, text in enumerate(lines):
                if text:
                    pg.add(("t", right - PAD, pg.y + PAD + (k + 0.78) * line_h, text, TSIZE, head))
            right -= w
        pg.y += h

    # a header repeats on every page, so it never takes more than a quarter
    # of one: past that it is cut (a page with no room left for a row would
    # start page after page without end)
    most = max(1, int(((A4[1] - 2 * MARGIN) / 4 - 2 * PAD) // line_h))
    header = [_cell_lines(c, w) for c, w in zip(cols, widths, strict=True)]
    header = [c if len(c) <= most else [*c[: most - 1], c[most - 1] + " …"] for c in header]
    head_h = max(len(c) for c in header) * line_h + 2 * PAD
    if pg.room() < head_h + line_h + 2 * PAD:
        pg.new()
    draw(header, True)
    for r in rows:
        cells = [_cell_lines(v, w) for v, w in zip(r, widths, strict=True)]
        fresh = False
        while True:
            fit = int((pg.room() - 2 * PAD) // line_h)
            need = max(len(c) for c in cells)
            if need <= fit:
                draw(cells, False)
                break
            if fit >= 3 or fresh:  # a row taller than the page goes on in pieces
                fit = max(fit, 1)
                draw([c[:fit] for c in cells], False)
                cells = [c[fit:] or [""] for c in cells]
            pg.new()
            draw(header, True)
            fresh = True
    pg.y += line_h / 2


def pages_of(title: str, body: str) -> list[list[Op]]:
    pg = _Pages()
    for b in blocks_of(title, body):
        if b[0] == "table":
            cols, rows = b[1], b[2]
            if len(cols) <= GRID_MAX:
                _grid(pg, cols, rows)
            else:
                for r in rows:  # one record per row: its first cell heads it
                    rest = [[c, v] for c, v in zip(cols[1:], r[1:], strict=True) if v]
                    _grid(pg, [cols[0] or "ستون", r[0] or "—"], rest)
            continue
        _, text, bold, size = b
        per = max(10, int(PER_LINE * SIZE / size))
        for line in wrap(text, per) if text else [""]:
            h = size * LEADING
            if pg.room() < h:
                pg.new()
            pg.y += h
            if line:
                pg.add(("t", A4[0] - MARGIN, pg.y, line, size, bold))
    pages = pg.pages
    if len(pages) > MAX_PAGES:
        cut = pages[:MAX_PAGES]
        note = f"… {len(pages) - MAX_PAGES} صفحه‌ی دیگر چاپ نشد."
        cut[-1] = [*cut[-1], ("t", A4[0] - MARGIN, A4[1] - MARGIN + SIZE, note, SIZE, True)]
        return cut
    return pages


def page_svg(ops: list[Op], n: int, total: int, footer: str) -> str:
    w, h = A4
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>',
    ]
    for op in ops:
        if op[0] == "r":
            _, x, y, rw, rh, fill = op
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{rw:.1f}" height="{rh:.1f}" fill="{fill}" '
                f'stroke="{RULE}" stroke-width="1"/>'
            )
            continue
        _, x, y, text, size, bold = op
        parts.append(
            f'<text x="{x:.0f}" y="{y:.0f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{700 if bold else 400}" fill="{INK}" direction="rtl" unicode-bidi="embed" '
            f'text-anchor="end">{html.escape(_bidi(text))}</text>'
        )
    parts.append(
        f'<text x="{MARGIN}" y="{h - MARGIN / 2:.0f}" font-family="{FONT}" font-size="14" fill="#5B6170">'
        f"{html.escape(footer)} · {n}/{total}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def render_job(data: bytes, title: str, footer: str, out: str, font_dir: str) -> dict[str, Any]:
    """In the child: every page through resvg, then one PDF through Pillow.
    ⟨1.10.1⟩ the body comes on stdin (`data`), never in argv: a long body
    (a company's whole catalogue) passed the OS's argument limit."""
    body = data.decode("utf-8", "replace")
    import io

    import resvg_py
    from PIL import Image

    fonts = [str(Path(font_dir) / f) for f in FONT_FILES if (Path(font_dir) / f).exists()]
    pages = pages_of(title, body)
    for i, ops in enumerate(pages, start=1):
        png = bytes(
            resvg_py.svg_to_bytes(
                svg_string=page_svg(ops, i, len(pages), footer),
                skip_system_fonts=True,
                font_files=fonts,
                font_family=FONT,
            )
        )
        # ⟨1.10.1⟩ one page in memory at a time (a whole catalogue is hundreds)
        page = Image.open(io.BytesIO(png)).convert("RGB")
        page.save(out, "PDF", append=i > 1, resolution=150.0)
        page.close()
    return {"pages": len(pages), "fonts": len(fonts)}


async def render(hub: Any, title: str, body: str, footer: str = "CoinePro HQ") -> tuple[bytes, int]:
    """-> (the PDF's bytes, its page count)."""
    out = hub.storage.scratch()
    try:
        got = await untrusted.run(
            "hq_api.archive.pdf:render_job",
            kwargs={
                "title": title,
                "footer": footer,
                "out": str(out),
                "font_dir": hub.settings.fonts_dir,
            },
            data=body.encode("utf-8"),
            limits=limits_for(len(body)),
        )
        if not got.ok or not isinstance(got.value, dict):
            raise RuntimeError(f"pdf render failed: {got.killed or got.error}"[:200])
        return await asyncio.to_thread(out.read_bytes), int(got.value["pages"])
    finally:
        out.unlink(missing_ok=True)
