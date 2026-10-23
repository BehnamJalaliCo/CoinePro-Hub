"""The parts of a render the hub draws itself, never the composition: the
burned-in Persian captions, the company mark and the call to action, laid out
inside the placement's safe zone; and the WebVTT captions file. Pure.

Geometry follows the creative overlay of prompt 12 (apps/api/src/hq_api/
domain/creative_overlay.py): the mark sits at the safe zone's bottom-left at
12% of the shorter side; the call to action is a pill on the same row at the
right (the start of a right-to-left line); captions sit just above that row,
centred, two lines at most.
"""

from __future__ import annotations

from dataclasses import dataclass

from hq_media_render.spec import Caption, SafeZone

MARK_SHARE = 0.12
CAPTION_SHARE = 0.044
CTA_SHARE = 0.04
CTA_SECONDS = 3.0  # a video shows its call to action in its last seconds


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    safe: Box
    mark: Box
    caption: Box  # the caption block: its bottom edge, full safe width
    caption_font_px: int
    cta: Box
    cta_font_px: int


def layout(width: int, height: int, safe: SafeZone, *, mark: bool, cta: bool) -> Layout:
    left, right = safe.left * width, width - safe.right * width
    top, bottom = safe.top * height, height - safe.bottom * height
    short = min(width, height)
    size = short * MARK_SHARE
    row_h = size if mark else (short * CTA_SHARE * 2.2 if cta else 0.0)
    gap = 0.02 * height if row_h else 0.0
    cap_font = max(14, round(short * CAPTION_SHARE))
    cap_h = cap_font * 1.5 * 2 + cap_font  # two lines and the band's padding
    cap_bottom = bottom - row_h - gap
    cta_font = max(12, round(short * CTA_SHARE))
    cta_h = cta_font * 2.2
    return Layout(
        width=width,
        height=height,
        safe=Box(left, top, right - left, bottom - top),
        mark=Box(left, bottom - size, size, size),
        caption=Box(left, max(top, cap_bottom - cap_h), right - left, min(cap_h, cap_bottom - top)),
        caption_font_px=cap_font,
        cta=Box(
            left + (size + gap if mark else 0.0),
            bottom - (row_h + cta_h) / 2,
            right - left - (size + gap if mark else 0.0),
            cta_h,
        ),
        cta_font_px=cta_font,
    )


def cue_windows(
    captions: tuple[Caption, ...], duration_s: float | None
) -> list[tuple[float, float, str]]:
    """The captions inside the video, without overlaps (a cue ends where the
    next begins), each at least a tenth of a second."""
    out: list[tuple[float, float, str]] = []
    cues = sorted(captions, key=lambda c: c.start_s)
    for i, c in enumerate(cues):
        end = c.end_s
        if i + 1 < len(cues):
            end = min(end, cues[i + 1].start_s)
        if duration_s is not None:
            end = min(end, duration_s)
        if end - c.start_s >= 0.1:
            out.append((round(c.start_s, 3), round(end, 3), c.text_fa))
    return out


def _ts(s: float) -> str:
    ms = round(s * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"


def webvtt(windows: list[tuple[float, float, str]]) -> str:
    """WebVTT (captions as text, for the platforms and the app)."""
    lines = ["WEBVTT", ""]
    for n, (start, end, text) in enumerate(windows, 1):
        clean = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("-->", "→")
        )
        lines += [str(n), f"{_ts(start)} --> {_ts(end)}", " ".join(clean.split()), ""]
    return "\n".join(lines)
