"""A creative's file and its Persian overlay (prompt 12 §9.1.4, contract
§21.13): the substitute only renders the picture; every Persian word on it is
set by the hub, by code, never asked of an image model.

- The download goes through §17.1's processing first: its type from its
  bytes, its metadata (EXIF) removed, the size limits of its kind, the image
  decoded only in a child with hard limits (hq_common.untrusted).
- The overlay (title, body, call to action, the company's mark) is laid out
  inside the placement's safe zone (where a story's or a post's own buttons
  never cover it), in IRANYekanX, right to left, in the company's brand
  colours, over the picture scaled to the placement's aspect ("cover"); resvg
  renders it, again in a child -> the `composed` PNG.
- A video keeps its original (its key frames are what the agent reviews); the
  overlay on a video is the media studio's (prompt 13).
"""

from __future__ import annotations

import asyncio
import base64
import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api import media
from hq_api.domain import brands
from hq_api.domain import files as F
from hq_common import untrusted

# Canvas per placement (pixels) and its safe zone as fractions of it:
# (top, right, bottom, left) kept clear of the platform's own interface.
CANVAS = {
    "telegram_post": (1280, 720),
    "telegram_story": (1080, 1920),
    "instagram_post": (1080, 1350),
    "instagram_story": (1080, 1920),
    "banner": (1600, 900),
    "other": (1080, 1080),
}
SAFE = {
    "telegram_post": (0.06, 0.05, 0.06, 0.05),
    "telegram_story": (0.12, 0.06, 0.18, 0.06),
    "instagram_post": (0.05, 0.05, 0.05, 0.05),
    # Instagram's story interface: the top 14% (progress bar, account) and the
    # bottom 20% (reply field, link sticker) are covered.
    "instagram_story": (0.14, 0.06, 0.20, 0.06),
    "banner": (0.06, 0.05, 0.06, 0.05),
    "other": (0.05, 0.05, 0.05, 0.05),
}
FONT = "IRANYekanX"
FONT_FILES = ("IRANYekanX-Bold.ttf", "IRANYekanX-Regular.ttf", "IRANYekanX-DemiBold.ttf")
COMPOSE_LIMITS = untrusted.Limits(write_mb=64)


class Refused(ValueError):
    """The download is not a file the hub keeps."""


@dataclass(frozen=True)
class Box:
    """One text line of the overlay (x is its right edge: the text is RTL)."""

    role: str
    text: str
    x: float
    y: float
    size: float


def safe_rect(placement: str) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of the safe zone, in pixels."""
    w, h = CANVAS[placement]
    top, right, bottom, left = SAFE[placement]
    return left * w, top * h, w - right * w, h - bottom * h


def _wrap(text: str, width_px: float, size: float) -> list[str]:
    """Greedy wrap by an average glyph width (Persian: ~0.5 em)."""
    per_line = max(4, int(width_px / (size * 0.5)))
    out: list[str] = []
    line = ""
    for word in text.split():
        cand = f"{line} {word}".strip()
        if len(cand) > per_line and line:
            out.append(line)
            line = word
        else:
            line = cand
    if line:
        out.append(line)
    return out[:4]


def layout(placement: str, overlay: dict[str, Any]) -> list[Box]:
    """The overlay's lines, every one inside the placement's safe zone: the
    title and the body from its top, the call to action at its bottom."""
    left, top, right, bottom = safe_rect(placement)
    w = right - left
    base = min(CANVAS[placement]) / 1080
    boxes: list[Box] = []
    y = top
    for role, size in (("title", 64 * base), ("body", 38 * base)):
        text = str(overlay.get(f"{role}_fa") or "").strip()
        if not text:
            continue
        for line in _wrap(text, w, size):
            y += size * 1.25
            boxes.append(Box(role, line, right, y, size))
        y += size * 0.5
    cta = str(overlay.get("cta_fa") or "").strip()
    if cta:
        size = 44 * base
        boxes.append(Box("cta", cta, right, bottom - size * 0.6, size))
    return boxes


def svg(
    placement: str,
    overlay: dict[str, Any],
    picture: tuple[str, bytes] | None,
    colours: dict[str, str],
    mark: dict[str, Any] | None,
) -> str:
    """The composed picture as SVG (resvg renders it)."""
    w, h = CANVAS[placement]
    ink = colours.get("ink", "#111216")
    accent = colours.get("accent", "#0E9F6E")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="{ink}"/>',
    ]
    if picture is not None:
        mime, data = picture
        uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        parts.append(
            f'<image x="0" y="0" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" '
            f'xlink:href="{uri}"/>'
        )
    boxes = layout(placement, overlay)
    left, top, right, bottom = safe_rect(placement)
    if boxes:
        # A soft band behind the text keeps it readable on any picture.
        text_bottom = (
            max(b.y for b in boxes if b.role != "cta")
            if any(b.role != "cta" for b in boxes)
            else top
        )
        parts.append(
            f'<rect x="{left:.0f}" y="{top:.0f}" width="{right - left:.0f}" '
            f'height="{text_bottom - top + 24:.0f}" rx="24" fill="{ink}" fill-opacity="0.55"/>'
        )
    for b in boxes:
        weight = "700" if b.role in ("title", "cta") else "400"
        colour = "#FFFFFF"
        if b.role == "cta":
            pad = b.size * 0.6
            width = min(right - left, len(b.text) * b.size * 0.55 + 2 * pad)
            parts.append(
                f'<rect x="{right - width:.0f}" y="{b.y - b.size - pad / 2:.0f}" width="{width:.0f}" '
                f'height="{b.size + pad * 1.4:.0f}" rx="{b.size / 2:.0f}" fill="{accent}"/>'
            )
            x = right - pad
        else:
            x = b.x - b.size * 0.4
        parts.append(
            f'<text x="{x:.0f}" y="{b.y:.0f}" font-family="{FONT}" font-size="{b.size:.0f}" '
            f'font-weight="{weight}" fill="{colour}" direction="rtl" unicode-bidi="embed" '
            f'text-anchor="start">{html.escape(b.text)}</text>'
        )
    if mark is not None and overlay.get("mark", True):
        vb = str(mark["vb"]).split()
        size = min(CANVAS[placement]) * 0.12
        scale = size / max(float(vb[2]), float(vb[3]))
        tx, ty = left, bottom - size
        parts.append(f'<g transform="translate({tx:.1f} {ty:.1f}) scale({scale:.4f})">')
        for layer in mark["layers"]:
            parts.append(f'<path d="{layer["d"]}" fill="{layer["color"]}" fill-rule="evenodd"/>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def compose_job(svg_text: str, out: str, font_dir: str) -> dict[str, Any]:
    """In the child: resvg renders the overlay with IRANYekanX only (no
    system font)."""
    import resvg_py

    fonts = [str(Path(font_dir) / f) for f in FONT_FILES if (Path(font_dir) / f).exists()]
    png = bytes(
        resvg_py.svg_to_bytes(
            svg_string=svg_text, skip_system_fonts=True, font_files=fonts, font_family=FONT
        )
    )
    Path(out).write_bytes(png)
    return {"bytes": len(png), "fonts": len(fonts)}


async def render_png(hub: Any, svg_text: str) -> Path:
    out = hub.storage.scratch()
    got = await untrusted.run(
        "hq_api.domain.creative_overlay:compose_job",
        kwargs={"svg_text": svg_text, "out": str(out), "font_dir": hub.settings.fonts_dir},
        limits=COMPOSE_LIMITS,
    )
    if not got.ok:
        out.unlink(missing_ok=True)
        raise Refused(f"the overlay could not be rendered ({str(got.error)[:60]})")
    rendered: Path = out
    return rendered


async def _brand(hub: Any, company_id: UUID) -> tuple[dict[str, str], dict[str, Any] | None]:
    async with hub.db.tx([company_id]) as tx:
        b = await brands.active(tx, company_id)
    if b is None:
        return {}, None
    c = brands.content(b)
    colours = {"ink": c["ink"]}
    if c.get("accent"):
        colours["accent"] = c["accent"]
    return colours, c.get("mark")


async def store_result(
    hub: Any, creative: dict[str, Any], data: bytes, name: str
) -> tuple[UUID, UUID | None]:
    """The substitute's download as the company's file (processed by §17.1),
    and the composed picture with the hub's Persian overlay -> (original id,
    composed id; None for a video)."""
    head = data[: media.HEAD_BYTES]
    got = media.check_type(None, head)
    if isinstance(got, str):
        raise Refused(got)
    mime, kind = got
    if kind.kind != creative["kind"]:
        raise Refused(f"a {kind.kind}, not the {creative['kind']} asked for")
    if len(data) > kind.max_bytes:
        raise Refused("too large")
    src = hub.storage.scratch()
    await asyncio.to_thread(src.write_bytes, data)
    company_id = creative["company_id"]
    if kind.kind == "image":
        try:
            img = await media.clean_image(src, mime, hub.storage.scratch)
        except media.ImageRefused as exc:
            raise Refused(str(exc)) from exc
        finally:
            src.unlink(missing_ok=True)
        key, sha, size = await hub.storage.commit(img.original)
        agent_bytes = await asyncio.to_thread(img.agent.read_bytes)
        colours, mark = await _brand(hub, company_id)
        overlay = dict(creative["overlay"] or {})
        png = await render_png(
            hub, svg(creative["placement"], overlay, ("image/jpeg", agent_bytes), colours, mark)
        )
        ckey, csha, csize = await hub.storage.commit(png)
        img.thumb.unlink(missing_ok=True)
        img.agent.unlink(missing_ok=True)
        cw, ch = CANVAS[creative["placement"]]
        async with hub.db.tx([company_id]) as tx:
            original = await F.insert(
                tx, company_id=company_id, name=f"{creative['ref']}-{name}"[:255], mime=mime,
                size=size, sha256=sha, storage_key=key, kind="image", width=img.width,
                height=img.height, by_kind="service", by_code="substitutes",
            )  # fmt: skip
            composed = await F.insert(
                tx, company_id=company_id, name=f"{creative['ref']}-composed.png", mime="image/png",
                size=csize, sha256=csha, storage_key=ckey, kind="image", width=cw, height=ch,
                by_kind="service", by_code="substitutes",
            )  # fmt: skip
        return original, composed
    try:
        info = await media.probe(str(src))
    except (ValueError, TimeoutError) as exc:
        src.unlink(missing_ok=True)
        raise Refused("not a playable video") from exc
    if (info.get("duration_s") or 0) > 10.5:
        src.unlink(missing_ok=True)
        raise Refused("longer than 10 seconds")
    key, sha, size = await hub.storage.commit(src)
    async with hub.db.tx([company_id]) as tx:
        original = await F.insert(
            tx, company_id=company_id, name=f"{creative['ref']}-{name}"[:255], mime=mime, size=size,
            sha256=sha, storage_key=key, kind="video", width=info.get("width"),
            height=info.get("height"), duration_s=info.get("duration_s"), by_kind="service",
            by_code="substitutes",
        )  # fmt: skip
    return original, None
