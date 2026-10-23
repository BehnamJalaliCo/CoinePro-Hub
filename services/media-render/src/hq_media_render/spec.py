"""A render job as the api hands it out (POST /internal/v1/media/render/claim),
parsed strictly: anything out of shape refuses the job before a file is
fetched or a browser starts. Pure (no I/O)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from hq_common import composition

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,40}$")
# An SVG path's data and a viewBox: numbers and path commands only (the brand
# pipeline of §18.14 already guarantees the grammar; this keeps it so).
PATH_D = re.compile(r"^[MmZzLlHhVvCcSsQqTtAa0-9eE.,+\-\s]{1,60000}$")
VIEWBOX = re.compile(r"^-?[0-9.]+(?:[\s,]+-?[0-9.]+){3}$")
KINDS = ("reel", "story", "post", "carousel", "design")
PLACEMENTS = (
    "telegram_post",
    "telegram_story",
    "instagram_reel",
    "instagram_story",
    "instagram_post",
    "design_phone",
    "design_desktop",
    "page",
)
MAX_DURATION_S = 180.0
MAX_FPS = 60
MAX_SIDE = 4096
MAX_ASSETS = 50
MAX_CAPTIONS = 400


class SpecError(ValueError):
    """The job is out of shape: `code` is the reason sent back to the api."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.code = "bad_job"


@dataclass(frozen=True)
class Output:
    name: str
    placement: str
    width: int
    height: int
    video: bool
    max_bytes: int
    fps: int = 30
    max_duration_s: float | None = None
    format: str = "jpeg"
    full_page: bool = False
    scale: int = 1
    # a still is the frame at this virtual time (a carousel's slide k: k - 0.5)
    at_s: float = 0.0


@dataclass(frozen=True)
class FileRef:
    id: str
    mime: str
    sha256: str
    size: int | None = None
    name: str = ""
    duration_s: float | None = None


@dataclass(frozen=True)
class Caption:
    start_s: float
    end_s: float
    text_fa: str


@dataclass(frozen=True)
class MarkLayer:
    color: str
    d: str


@dataclass(frozen=True)
class Brand:
    ink: str
    accent: str | None
    palette: tuple[str, ...]
    mark_vb: str | None = None
    mark: tuple[MarkLayer, ...] = ()


@dataclass(frozen=True)
class SafeZone:
    top: float
    right: float
    bottom: float
    left: float


@dataclass(frozen=True)
class Job:
    id: str
    item: str
    company: str
    kind: str
    purpose: str
    fmt: str
    sha256: str
    source: str
    outputs: tuple[Output, ...]
    duration_s: float | None
    fps: int
    assets: tuple[FileRef, ...]
    voice: FileRef | None
    captions: tuple[Caption, ...]
    mark: bool
    cta_fa: str | None
    brand: Brand
    safe: SafeZone
    timeout_s: int
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def video(self) -> bool:
        return any(o.video for o in self.outputs)

    def files(self) -> list[FileRef]:
        return [*self.assets, *([self.voice] if self.voice else [])]


def shapes(outputs: tuple[Output, ...]) -> list[list[Output]]:
    """Outputs drawn once per shape (size, rate, time, format): a reel for
    Instagram and Telegram is one render, under the smaller of their limits,
    which the first output of each group carries."""
    groups: dict[tuple[Any, ...], list[Output]] = {}
    for o in outputs:
        key = (o.video, o.width, o.height, o.fps, o.scale, o.full_page, o.at_s, o.format)
        groups.setdefault(key, []).append(o)
    out = []
    for g in groups.values():
        durations = [o.max_duration_s for o in g if o.max_duration_s is not None]
        first = replace(
            g[0],
            max_bytes=min(o.max_bytes for o in g),
            max_duration_s=min(durations) if durations else None,
        )
        out.append([first, *g[1:]])
    return out


def refusal(job: Job) -> str | None:
    """The rule check again, in the render worker: a composition that does not
    pass (or was changed on the way) is never drawn; the reason names the rules."""
    if composition.sha256(job.source) != job.sha256:
        return "sha256_mismatch"
    rep = composition.check(job.fmt, job.source, None)
    if not rep.ok:
        return "composition_refused: " + ",".join(sorted({p["rule"] for p in rep.problems}))
    return None


def _num(v: Any, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= float(v) <= hi:
        raise SpecError(f"{what} out of range")
    return float(v)


def _int(v: Any, lo: int, hi: int, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise SpecError(f"{what} out of range")
    return v


def _str(v: Any, what: str, pattern: re.Pattern[str] | None = None, max_len: int = 200) -> str:
    if not isinstance(v, str) or not v or len(v) > max_len or (pattern and not pattern.match(v)):
        raise SpecError(f"bad {what}")
    return v


def _file(d: Any, what: str) -> FileRef:
    if not isinstance(d, dict):
        raise SpecError(f"bad {what}")
    size = d.get("size")
    return FileRef(
        id=_str(d.get("id"), f"{what}.id", UUID),
        mime=_str(d.get("mime"), f"{what}.mime", re.compile(r"^[a-z]+/[a-z0-9.+-]+$")),
        sha256=_str(d.get("sha256"), f"{what}.sha256", SHA256),
        size=_int(size, 0, 300 * 1024 * 1024, f"{what}.size") if size is not None else None,
        name=str(d.get("name") or "")[:200],
        duration_s=_num(d["duration_s"], 0, 3600, f"{what}.duration_s")
        if d.get("duration_s") is not None
        else None,
    )


def _output(d: Any) -> Output:
    if not isinstance(d, dict):
        raise SpecError("bad output")
    video = d.get("video") is True
    fmt = str(d.get("format") or ("mp4" if video else "jpeg"))
    if fmt not in (("mp4",) if video else ("jpeg", "png")):
        raise SpecError("bad output.format")
    mdur = d.get("max_duration_s")
    at = d.get("at_s")
    if video and at is not None:
        raise SpecError("at_s is for stills only")
    return Output(
        name=_str(d.get("name") or d.get("placement"), "output.name", NAME),
        placement=_str(d.get("placement"), "output.placement", max_len=40),
        width=_int(d.get("width"), 16, MAX_SIDE, "output.width"),
        height=_int(d.get("height"), 16, MAX_SIDE, "output.height"),
        video=video,
        max_bytes=_int(d.get("max_bytes"), 1024, 300 * 1024 * 1024, "output.max_bytes"),
        fps=_int(d.get("fps", 30), 1, MAX_FPS, "output.fps"),
        max_duration_s=_num(mdur, 1, 3600, "output.max_duration_s") if mdur is not None else None,
        format=fmt,
        full_page=d.get("full_page") is True,
        scale=_int(d.get("scale", 1), 1, 2, "output.scale"),
        at_s=_num(at, 0, MAX_DURATION_S, "output.at_s") if at is not None else 0.0,
    )


def parse(data: Any) -> Job:
    """The job, or SpecError (its message never holds the composition)."""
    if not isinstance(data, dict):
        raise SpecError("a job is an object")
    comp = data.get("composition")
    if not isinstance(comp, dict):
        raise SpecError("no composition")
    fmt = comp.get("format")
    if fmt not in ("html", "lottie"):
        raise SpecError("bad composition.format")
    source = comp.get("source")
    if not isinstance(source, str) or not source:
        raise SpecError("bad composition.source")
    kind = data.get("kind")
    if kind not in KINDS:
        raise SpecError("bad kind")
    outputs = data.get("outputs")
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 10:
        raise SpecError("1 to 10 outputs")
    outs = tuple(_output(o) for o in outputs)
    if len({o.name for o in outs}) != len(outs):
        raise SpecError("output names repeat")
    dur = data.get("duration_s")
    duration = _num(dur, 0.5, MAX_DURATION_S, "duration_s") if dur is not None else None
    if any(o.video for o in outs) and duration is None:
        raise SpecError("a video output needs duration_s")
    assets = data.get("assets") or []
    if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
        raise SpecError("too many assets")
    caps = data.get("captions") or []
    if not isinstance(caps, list) or len(caps) > MAX_CAPTIONS:
        raise SpecError("too many captions")
    captions = []
    for c in caps:
        if not isinstance(c, dict):
            raise SpecError("bad caption")
        start = _num(c.get("start_s"), 0, MAX_DURATION_S, "caption.start_s")
        end = _num(c.get("end_s"), 0, MAX_DURATION_S, "caption.end_s")
        if end <= start:
            raise SpecError("a caption ends before it starts")
        text = c.get("text_fa")
        if not isinstance(text, str) or not text.strip() or len(text) > 300:
            raise SpecError("bad caption.text_fa")
        captions.append(Caption(start, end, text.strip()))
    overlay = data.get("overlay") or {}
    if not isinstance(overlay, dict):
        raise SpecError("bad overlay")
    cta = overlay.get("cta_fa")
    if cta is not None and (not isinstance(cta, str) or len(cta) > 80):
        raise SpecError("bad overlay.cta_fa")
    b = data.get("brand") or {}
    if not isinstance(b, dict):
        raise SpecError("bad brand")
    ink = _str(b.get("ink") or "#111216", "brand.ink", HEX)
    accent = _str(b["accent"], "brand.accent", HEX) if b.get("accent") else None
    palette = tuple(_str(p, "brand.palette", HEX) for p in (b.get("palette") or [])[:12])
    mark_vb: str | None = None
    layers: list[MarkLayer] = []
    m = b.get("mark")
    if m:
        if not isinstance(m, dict):
            raise SpecError("bad brand.mark")
        mark_vb = _str(m.get("vb"), "brand.mark.vb", VIEWBOX, 80)
        for layer in (m.get("layers") or [])[:8]:
            if not isinstance(layer, dict):
                raise SpecError("bad brand.mark layer")
            layers.append(
                MarkLayer(
                    color=_str(layer.get("color"), "brand.mark.color", HEX),
                    d=_str(layer.get("d"), "brand.mark.d", PATH_D, 60000),
                )
            )
    sz = data.get("safe_zone") or {}
    if not isinstance(sz, dict):
        raise SpecError("bad safe_zone")
    safe = SafeZone(
        *(
            _num(sz.get(k, 0.05), 0, 0.4, f"safe_zone.{k}")
            for k in ("top", "right", "bottom", "left")
        )
    )
    limits = data.get("limits") or {}
    timeout = limits.get("timeout_s", 600) if isinstance(limits, dict) else 600
    voice = data.get("voice")
    return Job(
        id=_str(data.get("id"), "id", UUID),
        item=_str(data.get("item"), "item", re.compile(r"^MI-[0-9]{4,}$")),
        company=_str(data.get("company"), "company", re.compile(r"^[A-Z][A-Z0-9]{1,9}$")),
        kind=str(kind),
        purpose="preview" if data.get("purpose") == "preview" else "final",
        fmt=str(fmt),
        sha256=_str(comp.get("sha256"), "composition.sha256", SHA256),
        source=source,
        outputs=outs,
        duration_s=duration,
        fps=_int(data.get("fps", 30), 1, MAX_FPS, "fps"),
        assets=tuple(_file(a, "asset") for a in assets),
        voice=_file(voice, "voice") if voice else None,
        captions=tuple(sorted(captions, key=lambda c: c.start_s)),
        mark=overlay.get("mark") is True and bool(layers),
        cta_fa=cta.strip() if isinstance(cta, str) and cta.strip() else None,
        brand=Brand(ink=ink, accent=accent, palette=palette, mark_vb=mark_vb, mark=tuple(layers)),
        safe=safe,
        timeout_s=_int(timeout, 10, 3600, "limits.timeout_s"),
        raw=data,
    )
