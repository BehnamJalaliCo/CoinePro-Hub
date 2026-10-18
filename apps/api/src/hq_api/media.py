"""Owner media (prompt 6 §2, contract §17.1): what a file really is, how big it
may be, and the image work done at upload. No model is involved anywhere.

- The type is decided by the bytes (magic numbers), never by the header: the
  declared Content-Type must be an allowed type AND agree with the content.
- Limits per kind, enforced while the body streams in: images 20 MB, video
  200 MB / 10 min, audio 25 MB / 15 min, pdf 30 MB.
- Images get a pixel cap; the stored original is the clean one: its EXIF,
  GPS, XMP and the rest are removed without decoding it (image_meta; only the
  orientation stays), and it gets the `agent` variant a model sees (upright,
  long edge <= 1568 px) and a 512 px WebP `thumb` made from that.
- Images and PDFs are untrusted: every decode runs in a child process with
  hard limits (hq_common.untrusted), never in the api's own process.
- Videos and audio are probed with ffprobe (duration, size); posters, key
  frames and sound tracks are made later by the worker (media_worker).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hq_common import untrusted

log = logging.getLogger("hq_api.media")

MB = 1024 * 1024


@dataclass(frozen=True)
class Kind:
    kind: str  # image | video | audio | document
    max_bytes: int
    max_seconds: int | None = None


IMAGE = Kind("image", 20 * MB)
VIDEO = Kind("video", 200 * MB, 10 * 60)
AUDIO = Kind("audio", 25 * MB, 15 * 60)
DOCUMENT = Kind("document", 30 * MB)

# The allowed declared types (contract §17.1) and their kind.
ALLOWED: dict[str, Kind] = {
    "image/jpeg": IMAGE,
    "image/png": IMAGE,
    "image/webp": IMAGE,
    "image/heic": IMAGE,
    "image/heif": IMAGE,
    "video/mp4": VIDEO,
    "video/webm": VIDEO,
    "video/quicktime": VIDEO,
    "audio/mp4": AUDIO,
    "audio/m4a": AUDIO,
    "audio/x-m4a": AUDIO,
    "audio/aac": AUDIO,
    "audio/ogg": AUDIO,
    "audio/opus": AUDIO,
    "audio/webm": AUDIO,
    "audio/wav": AUDIO,
    "audio/x-wav": AUDIO,
    "audio/wave": AUDIO,
    "audio/mpeg": AUDIO,
    "application/pdf": DOCUMENT,
}
HEAD_BYTES = 64  # enough for every signature below
# A 40 MP photo; larger is refused, over 80 MP before a byte is decoded (Pillow's
# DecompressionBombError). Measured: a 40 MP JPEG's job peaks at 67 MiB.
MAX_PIXELS = 40_000_000
THUMB_PX = 512
AGENT_PX = 1568  # the long edge a model sees (contract §17.1)

_FTYP_VIDEO = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash",
               b"M4V ", b"MSNV", b"3gp4", b"3gp5", b"3g2a"}  # fmt: skip
_FTYP_QT = {b"qt  "}
_FTYP_AUDIO = {b"M4A ", b"M4B ", b"M4P "}
_FTYP_HEIC = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


def sniff(head: bytes) -> set[str]:
    """The declared types these first bytes are consistent with (empty: none)."""
    if head.startswith(b"\xff\xd8\xff"):
        return {"image/jpeg"}
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"image/png"}
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return {"image/webp"}
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return {"audio/wav", "audio/x-wav", "audio/wave"}
    if head.startswith(b"%PDF-"):
        return {"application/pdf"}
    if head.startswith(b"OggS"):
        return {"audio/ogg", "audio/opus"}
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML: Matroska / WebM
        return {"video/webm", "audio/webm"} if b"webm" in head else set()
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return {"audio/mpeg"}
    if head[:2] in (b"\xff\xf1", b"\xff\xf9"):  # ADTS AAC
        return {"audio/aac"}
    if head[4:8] == b"ftyp":
        brands = {head[8:12]} | {head[i : i + 4] for i in range(16, min(len(head), 40), 4)}
        if brands & _FTYP_HEIC and head[8:12] in _FTYP_HEIC:
            return {"image/heic", "image/heif"}
        if head[8:12] in _FTYP_AUDIO:
            return {"audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"}
        if head[8:12] in _FTYP_QT:
            return {"video/quicktime", "video/mp4"}
        if head[8:12] in _FTYP_VIDEO or brands & _FTYP_VIDEO:
            return {"video/mp4", "video/quicktime", "audio/mp4", "audio/m4a", "audio/x-m4a"}
    if head[4:8] in (b"moov", b"mdat", b"wide", b"free"):  # QuickTime without ftyp
        return {"video/quicktime"}
    return set()


def declared(content_type: str | None) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def check_type(content_type: str | None, head: bytes) -> tuple[str, Kind] | str:
    """(mime, kind) when the declared type is allowed and the bytes agree; else
    the reason (for 415/422)."""
    mime = declared(content_type)
    kind = ALLOWED.get(mime)
    if kind is None:
        return "this type is not accepted"
    if mime not in sniff(head):
        return "the content is not what the Content-Type says"
    return mime, kind


async def probe(path: str) -> dict[str, Any]:
    """ffprobe: duration (s), width, height and whether there is sound."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 30)
    except TimeoutError:
        proc.kill()
        raise
    if proc.returncode != 0:
        raise ValueError("ffprobe could not read the file")
    data = json.loads(out or b"{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    duration = float((data.get("format") or {}).get("duration") or 0) or None
    return {
        "duration_s": duration,
        "width": int(video["width"]) if video and video.get("width") else None,
        "height": int(video["height"]) if video and video.get("height") else None,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "has_video": video is not None,
    }


# ----------------------------------------------------------------- images --
# Untrusted (prompt 07.1 §1.2, 06.1 §1.4): decoded only in a child process
# (hq_common.untrusted) with the limits below, outside any DB transaction.
IMAGE_LIMITS = untrusted.Limits(write_mb=64)  # the child writes the three files


class ImageRefused(ValueError):
    """Not an image this hub keeps (unreadable, too many pixels, or too much
    work for the limits): 415."""


@dataclass
class Image:
    """A cleaned image: the three files (scratch paths) and the original's size."""

    original: Path
    agent: Path
    thumb: Path
    mime: str
    width: int
    height: int


def _open(src: Any) -> Any:
    from PIL import Image as PILImage

    PILImage.MAX_IMAGE_PIXELS = MAX_PIXELS  # over twice that: DecompressionBombError
    img = PILImage.open(src)
    if img.width * img.height > MAX_PIXELS:
        raise ValueError("the image has too many pixels")
    return img


def clean_image_job(src: str, mime: str, original: str, agent: str, thumb: str) -> dict[str, Any]:
    """In the child: the clean original (metadata removed without decoding,
    image_meta), then the agent variant (JPEG, long edge <= 1568, upright)
    decoded from that clean original, and the WebP thumb made from the agent
    variant. A JPEG is decoded at a reduced scale; nothing is ever copied."""
    from PIL import ImageOps

    from hq_api import image_meta

    if mime in ("image/heic", "image/heif"):
        import pillow_heif

        pillow_heif.options.DECODE_THREADS = 1  # each thread costs address space
        pillow_heif.register_heif_opener()
    data = Path(src).read_bytes()
    head = _open(io.BytesIO(data))  # the header only: type, size, pixel cap
    # A HEIF image is turned by its own properties (irot/imir) as it decodes.
    heif = mime in ("image/heic", "image/heif")
    orientation = 1 if heif else int(head.getexif().get(image_meta.ORIENTATION, 1) or 1)
    del head
    clean = image_meta.strip(data, mime, orientation)
    del data
    Path(original).write_bytes(clean)
    del clean
    img = _open(original)
    width, height = img.size
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    scale = min(1.0, AGENT_PX / max(img.size))
    # A JPEG decodes at 1/2 to 1/8 of its size when that is still >= the variant.
    img.draft(None, (max(1, int(img.width * scale)), max(1, int(img.height * scale))))
    img.thumbnail((AGENT_PX, AGENT_PX), reducing_gap=None)  # decodes here
    ImageOps.exif_transpose(img, in_place=True)
    img.info = {}
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(agent, format="JPEG", quality=85)
    img.thumbnail((THUMB_PX, THUMB_PX))
    img.save(thumb, format="WEBP", quality=80)
    return {"width": width, "height": height}


async def clean_image(src: Path, mime: str, scratch: Callable[[], Path]) -> Image:
    """The image job in a child; ImageRefused (415) when it cannot be kept."""
    outs = [scratch() for _ in range(3)]
    got = await untrusted.run(
        "hq_api.media:clean_image_job",
        kwargs={"src": str(src), "mime": mime, "original": str(outs[0]),
                "agent": str(outs[1]), "thumb": str(outs[2])},
        limits=IMAGE_LIMITS,
    )  # fmt: skip
    if not got.ok:
        for p in outs:
            p.unlink(missing_ok=True)
        log.info("image refused", extra={"reason": got.reason, "seconds": round(got.seconds, 2)})
        if got.killed:
            raise ImageRefused("too large to process")
        raise ImageRefused(_short(got.error))
    return Image(outs[0], outs[1], outs[2], mime, got.value["width"], got.value["height"])


def _short(error: str | None) -> str:
    """The job's refusal without the exception's class name."""
    return (error or "unreadable").partition(": ")[2][:100] or "unreadable"


def has_metadata(data: bytes) -> bool:
    """For tests and checks: does an image carry EXIF beyond its orientation,
    GPS, XMP, text chunks or a comment?"""
    from pillow_heif import register_heif_opener

    register_heif_opener()
    img = _open(io.BytesIO(data))
    exif = img.getexif()
    xmp = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp") or b""
    return (
        any(tag != 0x0112 for tag in exif)
        or bool(exif.get_ifd(0x8825))
        or b"rdf:" in (xmp.encode() if isinstance(xmp, str) else xmp)
        or bool(img.info.get("comment"))
        or bool(getattr(img, "text", None))
    )


# ------------------------------------------------------------------- PDF --
MAX_PDF_PAGES = 200
MAX_PDF_CHARS = 200_000  # files.processing.text's cap
PDF_LIMITS = untrusted.DEFAULT


def pdf_text_job(path: str) -> str | None:
    """In the child: the text of the first 200 pages (200k characters)."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            return None  # a password-protected PDF: no text
        parts: list[str] = []
        total = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)
                total += len(text)
            if total >= MAX_PDF_CHARS:
                break
    except (PyPdfError, ValueError, KeyError, TypeError, AttributeError, IndexError, OSError):
        return None  # a broken PDF has no text; that never fails the upload
    out = "\n\n".join(parts).strip()[:MAX_PDF_CHARS]
    return out or None


@dataclass
class PdfText:
    status: str  # ready (text or none) | failed (the job was stopped)
    text: str | None = None
    error: str | None = None


async def pdf_text(path: Path) -> PdfText:
    """A PDF's text for files.read (prompt 07 §3), from a child process. A
    scanned, encrypted or broken PDF is `ready` without text; one the limits
    stopped is `failed`. Neither fails the upload."""
    if not await asyncio.to_thread(_is_pdf, path):
        return PdfText("ready")
    got = await untrusted.run("hq_api.media:pdf_text_job", kwargs={"path": str(path)},
                              limits=PDF_LIMITS)  # fmt: skip
    if got.ok:
        return PdfText("ready", got.value if isinstance(got.value, str) else None)
    log.warning("pdf text stopped", extra={"reason": got.reason, "seconds": round(got.seconds, 2)})
    return PdfText("failed", None, f"text extraction {got.reason}"[:300])


def _is_pdf(path: Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(5) == b"%PDF-"
