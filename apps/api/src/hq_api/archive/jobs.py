"""The archive's child-process jobs (hq_common.untrusted): light imports only,
since each runs in a fresh interpreter under hard memory limits."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

TEXT_MAX = 400_000
MAX_PDF_PAGES = 500


def doc_text_job(path: str) -> dict[str, Any]:
    """In the child: a PDF's own text layer and its page count."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            return {"text": None, "pages": None, "encrypted": True}
        pages = len(reader.pages)
        parts: list[str] = []
        total = 0
        for page in reader.pages[: MAX_PDF_PAGES]:
            t = (page.extract_text() or "").strip()
            if t:
                parts.append(t)
                total += len(t)
            if total >= TEXT_MAX:
                break
        text = "\n\n".join(parts).strip()[:TEXT_MAX]
        return {"text": text or None, "pages": pages}
    except (PyPdfError, ValueError, KeyError, TypeError, AttributeError, IndexError, OSError):
        return {"text": None, "pages": None, "broken": True}


def _pdf_overlay(width: float, height: float, text: str) -> bytes:
    """A one-page PDF that only draws `text` (ASCII) diagonally in light grey
    and once along the bottom edge: merged over each page, nothing else changes."""
    safe = "".join(ch for ch in text if 32 <= ord(ch) < 127).replace("\\", "/")
    safe = safe.replace("(", "[").replace(")", "]")
    size = max(10.0, min(width, height) / 30)
    stream = (
        "q 0.55 g /GS1 gs BT /F1 %.1f Tf 0.7071 0.7071 -0.7071 0.7071 %.1f %.1f Tm (%s) Tj ET "
        "BT /F1 8 Tf 1 0 0 1 18 12 Tm (%s) Tj ET Q"
        % (size, width * 0.15, height * 0.2, safe, safe)
    ).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> /ExtGState << /GS1 6 0 R >> >> >>" % (width, height)
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /ExtGState /ca 0.35 /CA 0.35 >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def watermark_job(src: str, out: str, mime: str, text: str, font_dir: str) -> dict[str, Any]:
    """In the child: a watermarked copy of `src` (PDF via pypdf, images via
    Pillow) written to `out`; the original is never touched."""
    if mime == "application/pdf":
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(src)
        writer = PdfWriter()
        for page in reader.pages:
            box = page.mediabox
            w, h = float(box.width), float(box.height)
            mark = PdfReader(io.BytesIO(_pdf_overlay(w, h, text))).pages[0]
            page.merge_page(mark)
            writer.add_page(page)
        with open(out, "wb") as fh:
            writer.write(fh)
        return {"mime": mime, "pages": len(reader.pages)}
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(src)
    img.load()
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    size = max(12, min(base.size) // 28)
    font: Any
    try:
        font = ImageFont.truetype(str(Path(font_dir) / "IRANYekanX-Regular.ttf"), size)
    except OSError:
        font = ImageFont.load_default()
    step_y = max(size * 6, 80)
    for y in range(size, base.size[1], step_y):
        draw.text((size, y), text, fill=(128, 128, 128, 110), font=font)
    marked = Image.alpha_composite(base, layer)
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(mime, "PNG")
    if fmt == "JPEG":
        marked = marked.convert("RGB")
    marked.save(out, format=fmt, quality=90) if fmt != "PNG" else marked.save(out, format=fmt)
    return {"mime": {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]}


