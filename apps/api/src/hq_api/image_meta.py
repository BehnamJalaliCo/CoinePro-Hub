"""Removing an image's metadata without decoding it (prompt 07.1 §1.2, 06.1
§1.4): the clean original keeps the photo's own bytes and loses EXIF, GPS,
XMP, IPTC, comments, maker notes, embedded previews and anything after the
image's end. Only the orientation is kept (a one-tag EXIF), so the photo
still shows upright; the variants a model and the apps see are turned
upright for real.

Why not decode and re-encode (prompt 6): measured in the child process, a
40 MP JPEG needs 256 MiB (348 MiB when it must be turned), a 24 MP WebP
506 MiB and a 12 MP HEIC re-encoded as HEIF 512 MiB, all far over the
child's limit; this way the original costs a copy of its bytes and a lossy
re-encode is avoided.

Every function takes the file's bytes, returns the clean bytes, and raises
ValueError on anything malformed (the upload is then refused).
"""

from __future__ import annotations

import struct
import zlib

ORIENTATION = 0x0112


def tiff_orientation(orientation: int) -> bytes:
    """A big-endian TIFF/EXIF block with one tag: Orientation."""
    return (
        b"MM\x00*" + struct.pack(">I", 8) + struct.pack(">H", 1)
        + struct.pack(">HHI", ORIENTATION, 3, 1) + struct.pack(">HH", orientation, 0)
        + struct.pack(">I", 0)
    )  # fmt: skip


EMPTY_TIFF = b"MM\x00*" + struct.pack(">I", 8) + struct.pack(">H", 0) + struct.pack(">I", 0)
EMPTY_XMP = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"/>'


def strip(data: bytes, mime: str, orientation: int = 1) -> bytes:
    orientation = orientation if orientation in range(2, 9) else 1
    if mime == "image/jpeg":
        return jpeg(data, orientation)
    if mime == "image/png":
        return png(data, orientation)
    if mime == "image/webp":
        return webp(data, orientation)
    if mime in ("image/heic", "image/heif"):
        return heif(data)
    raise ValueError("not an image type")


# ------------------------------------------------------------------- JPEG --
# APPn segments that are image data, not metadata (by their signature).
_JPEG_KEEP = {
    0xE0: (b"JFIF\x00", b"JFXX\x00"),
    0xE2: (b"ICC_PROFILE\x00",),
    0xEE: (b"Adobe",),  # colour transform of CMYK/YCCK files
}


def jpeg(data: bytes, orientation: int) -> bytes:
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    n = len(data)
    out = bytearray(b"\xff\xd8")
    exif_done = orientation == 1
    i = 2
    while i + 1 < n:
        if data[i] != 0xFF:
            raise ValueError("a broken JPEG")
        while i + 1 < n and data[i + 1] == 0xFF:  # fill bytes
            i += 1
        if i + 1 >= n:
            break
        marker = data[i + 1]
        if marker == 0xD9:  # EOI: whatever follows (previews, videos, maker data) is dropped
            out += b"\xff\xd9"
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # standalone markers
            out += data[i : i + 2]
            i += 2
            continue
        if i + 4 > n:
            break
        end = i + 2 + int.from_bytes(data[i + 2 : i + 4], "big")
        if end > n or end < i + 4:
            raise ValueError("a broken JPEG segment")
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:  # APPn and COM
            if any(data[i + 4 : end].startswith(sig) for sig in _JPEG_KEEP.get(marker, ())):
                out += data[i:end]
        else:
            if not exif_done:  # after the kept APPn, before the tables
                body = b"Exif\x00\x00" + tiff_orientation(orientation)
                out += b"\xff\xe1" + (len(body) + 2).to_bytes(2, "big") + body
                exif_done = True
            out += data[i:end]
        i = end
        if marker == 0xDA:  # SOS: entropy-coded data up to the next real marker
            j = i
            while True:
                j = data.find(b"\xff", j)
                if j < 0 or j + 1 >= n:
                    raise ValueError("a truncated JPEG")
                nxt = data[j + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7 or nxt == 0xFF:
                    j += 1
                    continue
                break
            out += data[i:j]
            i = j
    raise ValueError("a truncated JPEG")


# -------------------------------------------------------------------- PNG --
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
# Everything the pixels need; text, eXIf, tIME and private chunks are dropped.
_PNG_KEEP = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT",
    b"bKGD", b"pHYs", b"cICP", b"mDCv", b"cLLi", b"acTL", b"fcTL", b"fdAT",
}  # fmt: skip


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return len(body).to_bytes(4, "big") + kind + body + zlib.crc32(kind + body).to_bytes(4, "big")


def png(data: bytes, orientation: int) -> bytes:
    if not data.startswith(_PNG_SIG):
        raise ValueError("not a PNG")
    n = len(data)
    out = bytearray(_PNG_SIG)
    exif_done = orientation == 1
    i = len(_PNG_SIG)
    while i + 12 <= n:
        size = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        end = i + 12 + size
        if end > n:
            raise ValueError("a broken PNG chunk")
        if kind in (b"IDAT", b"fdAT", b"IEND") and not exif_done:
            out += _png_chunk(b"eXIf", tiff_orientation(orientation))
            exif_done = True
        if kind in _PNG_KEEP:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            return bytes(out)
    raise ValueError("a truncated PNG")


# ------------------------------------------------------------------- WebP --
_WEBP_KEEP = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ICCP", b"ANIM", b"ANMF"}
_VP8X_EXIF, _VP8X_XMP = 0x08, 0x04


def _riff_chunk(kind: bytes, body: bytes) -> bytes:
    return kind + len(body).to_bytes(4, "little") + body + (b"\x00" if len(body) & 1 else b"")


def webp(data: bytes, orientation: int) -> bytes:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP")
    end = min(len(data), 8 + int.from_bytes(data[4:8], "little"))
    body = bytearray()
    extended = False
    i = 12
    while i + 8 <= end:
        kind = data[i : i + 4]
        size = int.from_bytes(data[i + 4 : i + 8], "little")
        if i + 8 + size > end:
            raise ValueError("a broken WebP chunk")
        payload = data[i + 8 : i + 8 + size]
        i += 8 + size + (size & 1)
        if kind == b"VP8X":
            if not payload:
                raise ValueError("a broken WebP header")
            flags = (payload[0] & ~(_VP8X_EXIF | _VP8X_XMP)) | (
                _VP8X_EXIF if orientation != 1 else 0
            )
            payload = bytes([flags]) + payload[1:]
            extended = True
        if kind in _WEBP_KEEP:
            body += _riff_chunk(kind, payload)
    if not body:
        raise ValueError("a WebP without an image")
    if extended and orientation != 1:  # EXIF comes after the image data
        body += _riff_chunk(b"EXIF", tiff_orientation(orientation))
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + bytes(body)


# ------------------------------------------------------------- HEIC/HEIF --
# ISOBMFF: the Exif and XMP items are overwritten in place (an empty EXIF,
# an empty XMP packet) so that no offset in the file moves; the orientation
# of a HEIF image is a property of the image (irot/imir), not EXIF.


def _boxes(data: bytes | bytearray, start: int, end: int) -> list[tuple[bytes, int, int]]:
    """(type, payload start, box end) of the boxes in [start, end)."""
    out: list[tuple[bytes, int, int]] = []
    i = start
    while i + 8 <= end:
        size = int.from_bytes(data[i : i + 4], "big")
        kind = bytes(data[i + 4 : i + 8])
        head = 8
        if size == 1:
            if i + 16 > end:
                raise ValueError("a broken HEIF box")
            size = int.from_bytes(data[i + 8 : i + 16], "big")
            head = 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            raise ValueError("a broken HEIF box")
        out.append((kind, i + head, i + size))
        i += size
    return out


def _cstring(data: bytes | bytearray, i: int, end: int) -> tuple[bytes, int]:
    j = data.find(b"\x00", i, end)
    if j < 0:
        return bytes(data[i:end]), end
    return bytes(data[i:j]), j + 1


def _uint(data: bytes | bytearray, i: int, size: int) -> int:
    return int.from_bytes(data[i : i + size], "big") if size else 0


def _metadata_items(data: bytearray, start: int, end: int) -> dict[int, str]:
    """iinf: item id -> "exif" | "xmp"."""
    version = data[start]
    i = start + 4
    i += 2 if version == 0 else 4  # entry_count
    found: dict[int, str] = {}
    for kind, p, box_end in _boxes(data, i, end):
        if kind != b"infe" or data[p] < 2:
            continue
        v = data[p]
        q = p + 4
        item_id = _uint(data, q, 2 if v == 2 else 4)
        q += (2 if v == 2 else 4) + 2  # + item_protection_index
        item_type = bytes(data[q : q + 4])
        q += 4
        _name, q = _cstring(data, q, box_end)
        if item_type == b"Exif":
            found[item_id] = "exif"
        elif item_type == b"mime":
            content_type, q = _cstring(data, q, box_end)
            if b"xml" in content_type.lower():
                found[item_id] = "xmp"
    return found


def _extents(
    data: bytearray, start: int, end: int, wanted: dict[int, str], idat: int | None
) -> list[tuple[str, int, int]]:
    """iloc: (what, file offset, length) of every extent of the wanted items."""
    version = data[start]
    i = start + 4
    offset_size, length_size = data[i] >> 4, data[i] & 0x0F
    base_size, index_size = data[i + 1] >> 4, (data[i + 1] & 0x0F) if version in (1, 2) else 0
    i += 2
    count = _uint(data, i, 2 if version < 2 else 4)
    i += 2 if version < 2 else 4
    out: list[tuple[str, int, int]] = []
    for _ in range(count):
        item_id = _uint(data, i, 2 if version < 2 else 4)
        i += 2 if version < 2 else 4
        method = 0
        if version in (1, 2):
            method = _uint(data, i, 2) & 0x0F
            i += 2
        i += 2  # data_reference_index
        base = _uint(data, i, base_size)
        i += base_size
        extents = _uint(data, i, 2)
        i += 2
        for _ in range(extents):
            i += index_size
            off = _uint(data, i, offset_size)
            i += offset_size
            length = _uint(data, i, length_size)
            i += length_size
            if i > end:
                raise ValueError("a broken HEIF item table")
            if item_id not in wanted:
                continue
            if method == 0:
                at = base + off
            elif method == 1 and idat is not None:
                at = idat + base + off
            else:
                raise ValueError("a HEIF metadata item this hub cannot clean")
            if length == 0:
                raise ValueError("a HEIF metadata item without a length")
            out.append((wanted[item_id], at, length))
    return out


def heif(data: bytes) -> bytes:
    buf = bytearray(data)
    meta = next(((p, e) for kind, p, e in _boxes(buf, 0, len(buf)) if kind == b"meta"), None)
    if meta is None:
        raise ValueError("a HEIF without a meta box")
    children = {kind: (p, e) for kind, p, e in _boxes(buf, meta[0] + 4, meta[1])}
    if b"iinf" not in children or b"iloc" not in children:
        raise ValueError("a HEIF without an item table")
    wanted = _metadata_items(buf, *children[b"iinf"])
    if not wanted:
        return bytes(buf)
    idat = children[b"idat"][0] if b"idat" in children else None
    for what, at, length in _extents(buf, *children[b"iloc"], wanted, idat):
        if at + length > len(buf):
            raise ValueError("a HEIF metadata item outside the file")
        if what == "exif":  # 4 bytes: where the TIFF header starts; then an empty TIFF
            fill = (b"\x00\x00\x00\x00" + EMPTY_TIFF)[:length]
            buf[at : at + length] = fill + b"\x00" * (length - len(fill))
        else:
            fill = EMPTY_XMP if length >= len(EMPTY_XMP) else b""
            buf[at : at + length] = fill + b" " * (length - len(fill))
    return bytes(buf)
