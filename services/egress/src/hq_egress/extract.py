"""What a fetched page or file says, as text for a model, and the marks of
instructions hidden in it.

Web content is untrusted data (prompt 07 §2.7): every result carries
`source: "web"` and `suspected_injection`, the instruction-like passages
found in it (English and Persian), so the agent and the overseer see them.
They are flagged, not removed: the text stays what the page says.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Any

from hq_common import untrusted

log = logging.getLogger("hq_egress.extract")

DROP = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "object",
    "embed",
    "head",
)
BLOCKS = frozenset(
    [
        "p",
        "div",
        "section",
        "article",
        "main",
        "header",
        "footer",
        "aside",
        "nav",
        "li",
        "ul",
        "ol",
        "table",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "pre",
        "blockquote",
        "br",
        "hr",
        "dd",
        "dt",
        "dl",
        "figcaption",
        "form",
    ]
)
MAX_PDF_PAGES = 200
SPACES = re.compile("[ \t\u00a0\u200b]+")
LINES = re.compile(r"\n{3,}")

INJECTION = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}"
        r"\b(instructions?|prompts?|rules|directions)\b",
        r"\byou are now\b",
        r"\b(new|updated) (system )?instructions?\b",
        r"\bsystem prompt\b",
        r"\bdo not (tell|inform|show) (the )?(user|owner|human)\b",
        r"\b(act|behave) as (an?|the)\b.{0,30}\b(assistant|ai|model|agent)\b",
        r"\bcall (the )?(tool|function)\b",
        r"<\|?(system|im_start|assistant)\|?>",
        r"دستور(ها|ات)?(ی)?\s*(قبلی|پیشین|بالا).{0,20}(نادیده|فراموش|توجه\s*نکن)",
        r"(نادیده|فراموش)\s*(بگیر|کن).{0,20}دستور",
        r"(تو|شما)\s*(اکنون|از\s*این\s*به\s*بعد)\s*(یک|نقش)",
        r"به\s*(کاربر|مالک)\s*(نگو|اطلاع\s*نده)",
    )
]


def html_text(html: bytes | str, max_chars: int) -> tuple[str, str, bool]:
    """(title, readable text, truncated) of an HTML page: scripts, styles and
    other non-text dropped; the main/article element if there is one."""
    import lxml.html  # here: only the child process parses

    try:
        doc = lxml.html.fromstring(html if isinstance(html, bytes) else html.encode("utf-8"))
    except (ValueError, lxml.etree.ParserError):
        return "", "", False
    title_el = doc.find(".//title")
    title = (title_el.text_content() if title_el is not None else "").strip()[:300]
    for tag in DROP:
        for el in doc.iter(tag):
            el.drop_tree()
    root = next(iter(doc.iter("main", "article")), None)
    root = root if root is not None else doc
    parts: list[str] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in BLOCKS:
            parts.append("\n")
        if el.text:
            parts.append(el.text)
        if el.tag in BLOCKS:
            parts.append("\n")
        if el.tail:
            parts.append(el.tail)
    text = LINES.sub(
        "\n\n", "\n".join(SPACES.sub(" ", ln).strip() for ln in "".join(parts).splitlines())
    )
    return title, *_cap(text.strip(), max_chars)


def pdf_text(data: bytes, max_chars: int) -> tuple[str, str, bool]:
    """(title, text, truncated) of a PDF (the first 200 pages)."""
    from pypdf import PdfReader  # here: only the child process parses
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        title = str((reader.metadata.title if reader.metadata else None) or "")[:300]
        out: list[str] = []
        size = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            t = page.extract_text() or ""
            out.append(t)
            size += len(t)
            if size > max_chars:
                break
    except (PdfReadError, ValueError, KeyError, TypeError):
        return "", "", False
    text = LINES.sub("\n\n", "\n".join(out))
    return title, *_cap(text.strip(), max_chars)


# The parse of a fetched page or file is untrusted work (prompt 07.1 §1.2): it
# runs in a child process with hard limits, never on the event loop. A page
# the limits stop reads as empty and truncated.
PARSE_LIMITS = untrusted.DEFAULT
SLOTS = 2  # children at once: one heavy page does not hold up every other read


async def read_text(kind: str, data: bytes, max_chars: int) -> tuple[str, str, bool]:
    """(title, text, truncated) of a PDF (`kind` "pdf") or an HTML page."""
    target = "hq_egress.extract:pdf_text" if kind == "pdf" else "hq_egress.extract:html_text"
    got = await untrusted.run(
        target, data=data, kwargs={"max_chars": max_chars}, limits=PARSE_LIMITS
    )
    if got.ok and isinstance(got.value, list) and len(got.value) == 3:
        title, text, cut = got.value
        return str(title), str(text), bool(cut)
    log.warning("page not parsed", extra={"kind": kind, "reason": got.reason})
    return "", "", got.killed is not None


def _cap(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def injection_flags(*texts: str) -> list[dict[str, Any]]:
    """Instruction-like passages (at most 10), each with a short snippet."""
    found: list[dict[str, Any]] = []
    for text in texts:
        for rx in INJECTION:
            for m in rx.finditer(text or ""):
                a, b = max(0, m.start() - 40), min(len(text), m.end() + 40)
                found.append({"pattern": rx.pattern[:60], "snippet": text[a:b].replace("\n", " ")})
                if len(found) >= 10:
                    return found
    return found
