"""Owner media (prompt 6 §2, contract §17.1): what a file really is, how big it
may be, and the image work done at upload. No model is involved anywhere.

- The type is decided by the bytes (magic numbers), never by the header: the
  declared Content-Type must be an allowed type AND agree with the content.
- Limits per kind, enforced while the body streams in: images 20 MB, video
  200 MB / 10 min, audio 25 MB / 15 min, pdf 30 MB.
- Images are decoded with a pixel cap, turned upright, re-encoded WITHOUT
  EXIF/GPS/XMP (the stored original is the clean one), and get a 512 px WebP
  `thumb` and the `agent` variant a model sees (long edge <= 1568 px).
- Videos and audio are probed with ffprobe (duration, size); posters, key
  frames and sound tracks are made later by the worker (media_worker).
"""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from typing import Any

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
MAX_PIXELS = 40_000_000  # a 40 MP photo; larger is refused (decompression bombs)
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


@dataclass
class Image:
    original: bytes
    mime: str
    width: int
    height: int
    thumb: bytes  # WebP, long edge <= 512
    agent: bytes  # JPEG, long edge <= 1568


def _open(data: bytes) -> Any:
    from PIL import Image as PILImage
    from pillow_heif import register_heif_opener

    register_heif_opener()
    PILImage.MAX_IMAGE_PIXELS = MAX_PIXELS
    img = PILImage.open(io.BytesIO(data))
    if img.width * img.height > MAX_PIXELS:
        raise ValueError("the image has too many pixels")
    return img


def clean_image(data: bytes, mime: str) -> Image:
    """Upright, without EXIF/GPS/XMP, plus a WebP thumb and the agent variant.
    CPU-bound: run it in a thread."""
    from PIL import ImageOps

    img = _open(data)
    img.load()
    img = ImageOps.exif_transpose(img)
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(mime, "HEIF")
    clean = img.copy()  # no info dict: EXIF, GPS, XMP and comments stay behind
    clean.info = {}
    if fmt == "JPEG" and clean.mode not in ("RGB", "L"):
        clean = clean.convert("RGB")
    out = io.BytesIO()
    params: dict[str, Any] = {"quality": 92} if fmt in ("JPEG", "WEBP", "HEIF") else {}
    clean.save(out, format=fmt, **params)
    return Image(
        original=out.getvalue(),
        mime=mime,
        width=clean.width,
        height=clean.height,
        thumb=_scaled(clean, THUMB_PX, "WEBP", 80),
        agent=_scaled(clean, AGENT_PX, "JPEG", 85),
    )


def _scaled(img: Any, edge: int, fmt: str, quality: int) -> bytes:
    small = img.copy()
    small.thumbnail((edge, edge))
    if fmt == "JPEG" and small.mode not in ("RGB", "L"):
        small = small.convert("RGB")
    out = io.BytesIO()
    small.save(out, format=fmt, quality=quality)
    return out.getvalue()


def has_metadata(data: bytes) -> bool:
    """For tests and checks: does an image still carry EXIF (or GPS) data?"""
    img = _open(data)
    return bool(img.info.get("exif")) or bool(img.getexif())


# ------------------------------------------------------------------- PDF --
MAX_PDF_PAGES = 200
MAX_PDF_CHARS = 200_000  # files.processing.text's cap
PDF_TEXT_S = 30.0


def _pdf_text(data: bytes) -> str | None:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
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
    out = "\n\n".join(parts).strip()[:MAX_PDF_CHARS]
    return out or None


async def pdf_text(data: bytes) -> str | None:
    """The text of a PDF for files.read (prompt 07 §3), or None: a scanned,
    encrypted or broken PDF has none, and that never fails the upload."""
    if not data.startswith(b"%PDF-"):
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(_pdf_text, data), PDF_TEXT_S)
    except Exception:  # noqa: BLE001 - pypdf on a hostile or broken file: no text
        return None
