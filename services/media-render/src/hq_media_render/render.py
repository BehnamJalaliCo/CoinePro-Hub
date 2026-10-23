"""`render <id>`: one job in the job volume, drawn in headless Chromium with no
network, muxed with ffmpeg, written back into the volume with its manifest
(the courier sends it). The composition is re-checked by rule first.

Frames are drawn at times the harness sets (a virtual clock), never recorded
live: for every frame the clock moves to t, due timers and animation frames
run, every animation is paused at t, Lottie goes to t, and the frame is
captured as JPEG and piped to ffmpeg. The hub's own overlays (captions, the
mark, the call to action) are drawn on a separate transparent page the
composition never sees and laid over the frames by ffmpeg.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hq_media_render import ffmpeg as FF
from hq_media_render import harness as H
from hq_media_render import layout as L
from hq_media_render.spec import Job, Output, SpecError, parse, refusal, shapes

log = logging.getLogger("hq_media_render.render")
LIB_DIR = Path(os.environ.get("MEDIA_LIB_DIR", "/opt/hq-media/lib"))
FONT_DIR = Path(os.environ.get("MEDIA_FONT_DIR", "/opt/hq-media/fonts"))
SANDBOX = os.environ.get("MEDIA_SANDBOX", "1") != "0"
JS_HEAP_MB = int(os.environ.get("MEDIA_JS_HEAP_MB", "256"))
JPEG_QUALITY = int(os.environ.get("MEDIA_FRAME_QUALITY", "92"))
PRESET = os.environ.get("MEDIA_X264_PRESET", "veryfast")
MAX_PAGE_PX = 16000
ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--hide-scrollbars",
    "--mute-audio",
    "--font-render-hinting=none",
    "--force-color-profile=srgb",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication",
    "--disable-sync",
    "--no-first-run",
    # Belt and braces: the container has no network at all, every request
    # is answered by route() or aborted, and anything else would meet a dead
    # proxy (WebRTC included).
    "--proxy-server=http://127.0.0.1:9",
    "--proxy-bypass-list=<-loopback>",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    f"--js-flags=--max-old-space-size={JS_HEAP_MB}",
]


class RenderError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class Result:
    status: str  # "done" | "failed"
    outputs: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# ------------------------------------------------------------- memory --
class Sampler:
    """The peak memory of Chromium's processes (PSS where readable, else RSS),
    sampled twice a second while the job runs."""

    def __init__(self) -> None:
        self.peak_kb = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> Sampler:
        self._t.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._t.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            self.peak_kb = max(self.peak_kb, chromium_kb())


def chromium_kb() -> int:
    total = 0
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes()
            if b"chrom" not in cmd and b"headless_shell" not in cmd:
                continue
            kb = _field(p / "smaps_rollup", "Pss:") or _field(p / "status", "VmRSS:")
            total += kb
        except OSError:
            continue
    return total


def _field(path: Path, key: str) -> int:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(key):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def cgroup_peak_mb() -> float | None:
    for name in ("memory.peak", "memory.max_usage_in_bytes"):
        p = Path("/sys/fs/cgroup") / name
        with contextlib.suppress(OSError, ValueError):
            return round(int(p.read_text().strip()) / 1048576, 1)
    return None


# ------------------------------------------------------------ the page --
class Session:
    """One Chromium for the job; a context per output shape; every request
    through `_route` (this job's own files only, the rest aborted)."""

    def __init__(self, job: Job, job_dir: Path) -> None:
        self.job = job
        self.dir = job_dir
        self.violations: list[dict[str, str]] = []
        self.assets = {f.id: (str(job_dir / "files" / f.id), f.mime) for f in job.assets}
        self._pw: Any = None
        self.browser: Any = None

    async def __aenter__(self) -> Session:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True, args=ARGS, chromium_sandbox=SANDBOX
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        with contextlib.suppress(Exception):
            await self.browser.close()
        with contextlib.suppress(Exception):
            await self._pw.stop()

    def _violation(self, rule: str, detail: str) -> None:
        if (
            len(self.violations) < 50
            and {"rule": rule, "detail": detail[:200]} not in self.violations
        ):
            self.violations.append({"rule": rule, "detail": detail[:200]})

    async def _route(self, route: Any) -> None:
        url = route.request.url
        a = H.decide(url, self.assets, LIB_DIR, FONT_DIR)
        if a.kind == "abort":
            if a.violation:
                self._violation("network_request", url)
            await route.abort("blockedbyclient")
            return
        headers = {"Content-Security-Policy": H.CSP, "Cache-Control": "no-store",
                   "X-Content-Type-Options": "nosniff"}  # fmt: skip
        if a.kind == "composition":
            body = self.job.source.encode("utf-8")
        elif a.kind == "lottie":
            body = H.LOTTIE_PAGE.encode("utf-8")
        elif a.kind == "overlay":
            body = H.OVERLAY_PAGE.encode("utf-8")
        else:
            assert a.path is not None
            body = await asyncio.to_thread(Path(a.path).read_bytes)
        await route.fulfill(status=200, body=body, content_type=a.mime, headers=headers)

    async def page(self, width: int, height: int, scale: int = 1, *, overlay: bool = False) -> Any:
        ctx = await self.browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
            service_workers="block",
            accept_downloads=False,
            locale="fa-IR",
            timezone_id="Asia/Tehran",
            color_scheme="light",
        )
        if not overlay:
            await ctx.add_init_script(H.CLOCK_JS)
        await ctx.route("**/*", self._route)
        page = await ctx.new_page()
        page.on("websocket", lambda ws: self._violation("websocket", str(ws.url)))
        page.on("popup", lambda p: self._violation("popup", str(p.url)))
        path = (
            H.OVERLAY_PATH
            if overlay
            else (H.COMPOSITION_PATH if self.job.fmt == "html" else H.LOTTIE_PATH)
        )
        await page.goto(H.ORIGIN + path, wait_until="load", timeout=30_000)
        if not overlay:
            if self.job.fmt == "html":
                await page.add_style_tag(content=H.FONT_FACES)
            await page.evaluate(H.FONTS_READY_JS)
            if self.job.fmt == "lottie":
                await page.evaluate(H.LOTTIE_START_JS, json.loads(self.job.source))
            await page.evaluate("t => window.__hqSeek(t)", 0)
        return page

    # -------------------------------------------------------- overlays --
    async def overlays(self, out: Output, tmp: Path, *, video: bool) -> list[FF.Overlay]:
        """The hub's overlay images for one output shape."""
        job = self.job
        lay = L.layout(out.width, out.height, job.safe, mark=job.mark, cta=job.cta_fa is not None)
        specs: list[tuple[dict[str, Any], float | None, float | None]] = []
        if job.mark and job.brand.mark_vb:
            m = lay.mark
            specs.append((
                {"mark": {"vb": job.brand.mark_vb, "x": m.x, "y": m.y, "w": m.w, "h": m.h,
                          "layers": [{"d": x.d, "color": x.color} for x in job.brand.mark]}},
                None, None,
            ))  # fmt: skip
        if job.cta_fa:
            c = lay.cta
            colour = job.brand.accent or job.brand.ink
            start = max(0.0, (job.duration_s or 0) - L.CTA_SECONDS) if video else None
            specs.append((
                {"cta": {"x": c.x, "y": c.y, "w": c.w, "h": c.h, "font": lay.cta_font_px,
                         "text": job.cta_fa, "color": colour}},
                start, job.duration_s if video else None,
            ))  # fmt: skip
        if video:
            cb = lay.caption
            for start, end, text in L.cue_windows(job.captions, job.duration_s):
                specs.append((
                    {"caption": {"x": cb.x, "y": cb.y, "w": cb.w, "h": cb.h,
                                 "font": lay.caption_font_px, "text": text}},
                    start, end,
                ))  # fmt: skip
        if not specs:
            return []
        page = await self.page(out.width, out.height, overlay=True)
        result: list[FF.Overlay] = []
        try:
            for i, (spec, at, until) in enumerate(specs):
                await page.evaluate(H.OVERLAY_JS, spec)
                path = tmp / f"overlay-{out.width}x{out.height}-{i}.png"
                await page.screenshot(path=str(path), omit_background=True, type="png")
                result.append(FF.Overlay(str(path), at, until))
        finally:
            await page.context.close()
        return result


# --------------------------------------------------------------- video --
async def _video(s: Session, out: Output, tmp: Path, dest: Path) -> dict[str, Any]:
    job = s.job
    assert job.duration_s is not None
    duration = job.duration_s
    if out.max_duration_s is not None and duration > out.max_duration_s + 0.01:
        raise RenderError("too_long", f"{duration}s > {out.max_duration_s}s for {out.placement}")
    overlays = await s.overlays(out, tmp, video=True)
    voice = str(s.dir / "files" / job.voice.id) if job.voice else None
    target = dest / f"{out.name}.mp4"
    args = FF.encode_args(str(target), fps=out.fps, duration_s=duration, overlays=overlays,
                          voice=voice, max_bytes=out.max_bytes, preset=PRESET)  # fmt: skip
    page = await s.page(out.width, out.height)
    cdp = await page.context.new_cdp_session(page)
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    frames = round(duration * out.fps)
    assert proc.stdin is not None
    try:
        for i in range(frames):
            await page.evaluate("t => window.__hqSeek(t)", i * 1000.0 / out.fps)
            shot = await cdp.send(
                "Page.captureScreenshot",
                {"format": "jpeg", "quality": JPEG_QUALITY, "optimizeForSpeed": True},
            )
            proc.stdin.write(base64.b64decode(shot["data"]))
            await proc.stdin.drain()
            if s.violations:
                break
            if i and i % (out.fps * 5) == 0:
                log.info("%s: %d of %d frames", out.name, i, frames)
        proc.stdin.close()
        _, err = await proc.communicate()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        raise
    finally:
        await page.context.close()
    if s.violations:
        raise RenderError("violations")
    if proc.returncode != 0:
        raise RenderError("ffmpeg_failed", (err or b"").decode(errors="replace")[-200:])
    size = target.stat().st_size
    if size > out.max_bytes:
        raise RenderError("too_large", f"{out.name}: {size} > {out.max_bytes} bytes")
    poster = dest / f"{out.name}.poster.jpg"
    await _run(FF.poster_args(str(target), str(poster), min(1.0, duration / 2)))
    return {"frames": frames, "files": [
        {"name": out.name, "kind": "video", "path": target.name, "mime": "video/mp4",
         "width": out.width, "height": out.height, "duration_s": duration, "bytes": size},
        {"name": out.name, "kind": "poster", "path": poster.name, "mime": "image/jpeg",
         "width": out.width, "height": out.height, "bytes": poster.stat().st_size},
    ]}  # fmt: skip


# --------------------------------------------------------------- still --
async def _still(s: Session, out: Output, tmp: Path, dest: Path) -> dict[str, Any]:
    page = await s.page(out.width, out.height, out.scale)
    shot = tmp / f"{out.name}.shot.png"
    try:
        await page.evaluate("t => window.__hqSeek(t)", out.at_s * 1000.0)
        clip = None
        if out.full_page:
            h = await page.evaluate("() => document.documentElement.scrollHeight")
            if int(h) > MAX_PAGE_PX // out.scale:
                clip = {"x": 0, "y": 0, "width": out.width, "height": MAX_PAGE_PX // out.scale}
        await page.screenshot(path=str(shot), type="png", full_page=out.full_page and clip is None,
                              clip=clip, caret="hide")  # fmt: skip
    finally:
        await page.context.close()
    if s.violations:
        raise RenderError("violations")
    overlays = [] if out.full_page else [o.path for o in await s.overlays(out, tmp, video=False)]
    ext = "jpg" if out.format == "jpeg" else "png"
    target = dest / f"{out.name}.{ext}"
    for q in (2, 4, 7, 10):
        await _run(FF.still_args(str(shot), overlays, str(target), fmt=out.format, quality=q))
        if target.stat().st_size <= out.max_bytes or out.format != "jpeg":
            break
    size = target.stat().st_size
    if size > out.max_bytes:
        raise RenderError("too_large", f"{out.name}: {size} > {out.max_bytes} bytes")
    w, h = await _dims(target)
    return {"frames": 1, "files": [
        {"name": out.name, "kind": "image", "path": target.name,
         "mime": "image/jpeg" if ext == "jpg" else "image/png", "width": w, "height": h,
         "bytes": size},
    ]}  # fmt: skip


async def _dims(path: Path) -> tuple[int, int]:
    proc = await asyncio.create_subprocess_exec(
        *FF.probe_args(str(path)), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    out, _ = await proc.communicate()
    with contextlib.suppress(ValueError, KeyError, IndexError):
        st = json.loads(out)["streams"][0]
        return int(st["width"]), int(st["height"])
    return 0, 0


async def _run(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RenderError("ffmpeg_failed", (err or b"").decode(errors="replace")[-200:])


# ------------------------------------------------------------- the job --
async def render_job(job: Job, job_dir: Path) -> Result:
    why = refusal(job)
    if why:
        return Result("failed", error=why)
    for f in job.files():
        if not (job_dir / "files" / f.id).is_file():
            return Result("failed", error=f"bad_job: file {f.id} missing")
    dest = job_dir / "out"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(mode=0o700)
    tmp = job_dir / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(mode=0o700)
    started = time.monotonic()
    res = Result("done")
    frames = 0
    session = Session(job, job_dir)
    with Sampler() as sampler:
        try:
            async with session as s:
                for group in shapes(job.outputs):
                    first = group[0]
                    got = await (
                        _video(s, first, tmp, dest) if first.video else _still(s, first, tmp, dest)
                    )
                    frames += int(got["frames"])
                    for out in group:  # the same shape for another placement: the same file
                        res.outputs += [{**f, "name": out.name} for f in got["files"]]
        except RenderError as exc:
            if exc.code == "violations":
                res.outputs = []
            else:
                res = Result("failed", error=str(exc)[:300])
        except Exception as exc:  # reported to the api as a failed render, logged here
            log.warning("render failed", exc_info=True)
            res = Result("failed", error=f"render_error: {type(exc).__name__}")
    res.violations = session.violations
    if res.violations:
        res.status, res.outputs = "done", []  # the api fails the item with them
    if res.status == "done" and job.captions and job.video and not res.violations:
        vtt = dest / "captions.vtt"
        vtt.write_text(L.webvtt(L.cue_windows(job.captions, job.duration_s)), encoding="utf-8")
        res.outputs.append({"name": "captions", "kind": "captions", "path": vtt.name,
                            "mime": "text/vtt", "bytes": vtt.stat().st_size})  # fmt: skip
    seconds = round(time.monotonic() - started, 2)
    res.metrics = {
        "seconds": seconds,
        "frames": frames,
        "fps": round(frames / seconds, 2) if seconds else None,
        "peak_rss_mb": cgroup_peak_mb(),
        "chromium_mb": round(sampler.peak_kb / 1024, 1),
    }
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def write_manifest(job_dir: Path, res: Result) -> None:
    path = job_dir / "out" / "manifest.json"
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_text(json.dumps(asdict(res), ensure_ascii=False), encoding="utf-8")


async def main(job_id: str, root: Path = Path("/jobs")) -> int:
    job_dir = root / job_id
    if Path(job_id).name != job_id or not (job_dir / "job.json").is_file():
        print(json.dumps({"error": "no such job"}))
        return 2
    try:
        job = parse(json.loads((job_dir / "job.json").read_text(encoding="utf-8")))
    except (SpecError, ValueError) as exc:
        write_manifest(job_dir, Result("failed", error=f"bad_job: {str(exc)[:200]}"))
        return 0
    try:
        res = await asyncio.wait_for(render_job(job, job_dir), timeout=job.timeout_s)
    except TimeoutError:
        res = Result("failed", error=f"timeout: over {job.timeout_s}s")
    write_manifest(job_dir, res)
    print(json.dumps({"status": res.status, "error": res.error, "metrics": res.metrics}))
    return 0
