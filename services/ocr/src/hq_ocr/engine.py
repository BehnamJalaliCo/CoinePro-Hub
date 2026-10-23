"""One OCR job: an image or a scanned PDF -> text per page with Tesseract's
own word confidence. Untrusted bytes only ever reach two programs, each with
a deadline: `pdftoppm` (a PDF's pages to PNG, the long side capped) and
`tesseract` (one page at a time, TSV out). Nothing here has a network; the
container has none but the worker's.

    detect(content_type, head) -> kind          ("png" | "jpeg" | "webp" | "tiff" | "pdf")
    image_pixels(kind, head) -> int | None      a header's width x height
    parse_tsv(tsv) -> (text, confidence, words) one page's text and mean confidence (0..1)
    run(job) -> Result                          the whole job
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The declared types the service takes, and the kind each one is.
TYPES = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/webp": "webp",
    "image/tiff": "tiff",
    "application/pdf": "pdf",
}
SUFFIX = {"png": ".png", "jpeg": ".jpg", "webp": ".webp", "tiff": ".tif", "pdf": ".pdf"}
HEAD_BYTES = 64 * 1024  # enough for a JPEG's frame header after its EXIF
_MARKS = str.maketrans("", "", "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class OcrError(Exception):
    """A refusal with its HTTP status and stable code."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def detect(content_type: str | None, head: bytes) -> str:
    """The kind of the body: the declared type must be one we take and the
    first bytes must agree with it; else 415 unsupported_type."""
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    kind = TYPES.get(declared)
    if kind is None or sniff(head) != kind:
        raise OcrError(415, "unsupported_type")
    return kind


def sniff(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


def image_pixels(kind: str, head: bytes) -> int | None:
    """Width x height from the header (PNG, JPEG, WebP), or None when the
    header does not say (TIFF; a JPEG whose frame header is further in)."""
    try:
        if kind == "png" and len(head) >= 24:
            w, h = struct.unpack(">II", head[16:24])
            return int(w) * int(h)
        if kind == "webp":
            chunk = head[12:16]
            if chunk == b"VP8X" and len(head) >= 30:
                w = 1 + int.from_bytes(head[24:27], "little")
                h = 1 + int.from_bytes(head[27:30], "little")
                return w * h
            if chunk == b"VP8 " and len(head) >= 30:
                w, h = struct.unpack("<HH", head[26:30])
                return (int(w) & 0x3FFF) * (int(h) & 0x3FFF)
            if chunk == b"VP8L" and len(head) >= 25:
                bits = int.from_bytes(head[21:25], "little")
                return ((bits & 0x3FFF) + 1) * (((bits >> 14) & 0x3FFF) + 1)
        if kind == "jpeg":
            return _jpeg_pixels(head)
    except (struct.error, ValueError):
        return None
    return None


def _jpeg_pixels(head: bytes) -> int | None:
    i = 2
    while i + 9 < len(head):
        if head[i] != 0xFF:
            return None
        marker = head[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", head[i + 2 : i + 4])[0]
        # SOF0..SOF15 except DHT (C4), JPG (C8) and DAC (CC)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", head[i + 5 : i + 9])
            return int(w) * int(h)
        i += 2 + length
    return None


def parse_tsv(tsv: str) -> tuple[str, float | None, int]:
    """Tesseract's TSV -> (text, mean word confidence 0..1 or None, words).
    Words are joined in Tesseract's reading order: a line's words by spaces,
    lines by a new line, paragraphs and blocks by an empty line."""
    lines: dict[tuple[int, int, int, int], list[str]] = {}
    confs: list[float] = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        # Tesseract marks direction around a run of the other script (LRM,
        # RLM); they are not part of the word.
        text = cols[11].translate(_MARKS).strip()
        if not text:
            continue
        try:
            key = (int(cols[1]), int(cols[2]), int(cols[3]), int(cols[4]))
            conf = float(cols[10])
        except ValueError:
            continue
        lines.setdefault(key, []).append(text)
        if conf >= 0:
            confs.append(conf)
    out: list[str] = []
    prev: tuple[int, int, int] | None = None
    for key in sorted(lines):
        para = key[:3]
        if prev is not None and para != prev:
            out.append("")
        out.append(" ".join(lines[key]))
        prev = para
    words = sum(len(v) for v in lines.values())
    confidence = round(sum(confs) / len(confs) / 100, 4) if confs else None
    return "\n".join(out), confidence, words


@dataclass
class Job:
    data: bytes
    kind: str
    max_pages: int
    langs: str
    tessdata: str
    timeout_s: float
    page_long_side_px: int
    threads: int = 1
    tmp_dir: str = ""  # "" = the system temporary directory


@dataclass
class Result:
    pages: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | None = None
    seconds: float = 0.0


def _deadline_left(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise OcrError(504, "timeout")
    return left


def _run(cmd: list[str], deadline: float, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - fixed programs, our own temporary paths
            cmd,
            capture_output=True,
            text=True,
            timeout=_deadline_left(deadline),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrError(504, "timeout") from exc


def _env(job: Job) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": job.tmp_dir or tempfile.gettempdir(),
        "TESSDATA_PREFIX": job.tessdata,
        "OMP_THREAD_LIMIT": str(job.threads),
        "LC_ALL": "C.UTF-8",
    }


def _pages(job: Job, work: Path, deadline: float, env: dict[str, str]) -> Iterator[Path]:
    """The pages to read, one at a time: the image itself, or a PDF's pages
    rasterised one by one (only one page is ever on the tmpfs)."""
    src = work / f"in{SUFFIX[job.kind]}"
    src.write_bytes(job.data)
    if job.kind != "pdf":
        yield src
        return
    pdftoppm = shutil.which("pdftoppm", path=env["PATH"]) or "pdftoppm"
    side = str(job.page_long_side_px)
    for n in range(1, job.max_pages + 1):
        out = work / f"page-{n}"
        _run(
            [pdftoppm, "-q", "-gray", "-png", "-singlefile", "-scale-to", side,
             "-f", str(n), "-l", str(n), str(src), str(out)],
            deadline,
            env,
        )  # fmt: skip
        page = out.with_suffix(".png")
        if not page.is_file():
            if n == 1:  # a broken or encrypted PDF (pdftoppm's exit code alone is not enough)
                raise OcrError(422, "unreadable")
            return  # past its last page
        yield page


def run(job: Job) -> Result:
    started = time.monotonic()
    deadline = started + job.timeout_s
    env = _env(job)
    tesseract = shutil.which("tesseract", path=env["PATH"]) or "tesseract"
    result = Result()
    all_confs: list[tuple[float, int]] = []
    work = Path(tempfile.mkdtemp(prefix="ocr-", dir=job.tmp_dir or None))
    try:
        for n, page in enumerate(_pages(job, work, deadline, env), start=1):
            done = _run(
                [
                    tesseract,
                    str(page),
                    "stdout",
                    "-l",
                    job.langs,
                    "--oem",
                    "1",
                    "--psm",
                    "3",
                    "-c",
                    "tessedit_create_tsv=1",
                ],
                deadline,
                env,
            )
            if done.returncode != 0:
                raise OcrError(422, "unreadable")
            text, conf, words = parse_tsv(done.stdout)
            result.pages.append({"n": n, "text": text, "confidence": conf, "words": words})
            if conf is not None and words:
                all_confs.append((conf, words))
            page.unlink(missing_ok=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if all_confs:
        total = sum(w for _, w in all_confs)
        result.confidence = round(sum(c * w for c, w in all_confs) / total, 4)
    result.seconds = round(time.monotonic() - started, 3)
    return result


def version(env: dict[str, str] | None = None) -> str:
    """`tesseract --version`'s first line's number ("5.5.0"), or "unknown"."""
    try:
        done = subprocess.run(  # noqa: S603 - a fixed program
            [shutil.which("tesseract") or "tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env or {"PATH": "/usr/bin:/bin"},
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    first = (done.stdout or done.stderr).splitlines()[:1]
    parts = first[0].split() if first else []
    return parts[1] if len(parts) > 1 else "unknown"


def available() -> bool:
    return shutil.which("tesseract") is not None
