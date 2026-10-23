"""media-render (prompt 13 §2.3): the job's shape, the composition re-check,
the harness's request filter, the hub's own overlays and captions, ffmpeg's
arguments, and the courier against a fake api. No browser runs here: the
image's own bench draws a real reel with no network (`make media-bench`)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_common import composition
from hq_media_render import courier as C
from hq_media_render import ffmpeg as FF
from hq_media_render import harness as H
from hq_media_render import layout as L
from hq_media_render import spec as S

JOB_ID = "6c1f0a52-8b7e-4c1d-9a35-2f0e6b1d7a10"
ASSET = "3f2b8a10-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
VOICE = "9d3c2b1a-0f9e-4d8c-8b7a-6c5d4e3f2a1b"
HTML = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>body { font-family: IRANYekanX; background: #0E1116; color: #FFFFFF; }</style>
<script src="/lib/anime.min.js"></script></head><body><h1>بیت‌کوین <bdi>BTC</bdi></h1>
<img src="/assets/3f2b8a10-1c2d-4e5f-8a9b-0c1d2e3f4a5b" alt=""></body></html>"""


def job(**over: Any) -> dict[str, Any]:
    asset = b"\x89PNG fake"
    voice = b"OggS fake"
    data: dict[str, Any] = {
        "id": JOB_ID,
        "item": "MI-0007",
        "company": "TY",
        "kind": "reel",
        "purpose": "final",
        "composition": {"format": "html", "sha256": composition.sha256(HTML), "source": HTML},
        "outputs": [
            {"name": "instagram_reel", "placement": "instagram_reel", "width": 1080, "height": 1920,
             "video": True, "fps": 30, "max_duration_s": 90, "max_bytes": 100 * 1024 * 1024},
        ],
        "duration_s": 30.0,
        "fps": 30,
        "assets": [{"id": ASSET, "name": "bg.png", "mime": "image/png",
                    "sha256": hashlib.sha256(asset).hexdigest(), "size": len(asset)}],
        "voice": {"id": VOICE, "mime": "audio/ogg", "sha256": hashlib.sha256(voice).hexdigest(),
                  "duration_s": 28.0, "size": len(voice)},
        "music": None,
        "captions": [{"start_s": 5.2, "end_s": 9.8, "text_fa": "دوم"},
                     {"start_s": 0.3, "end_s": 6.0, "text_fa": "یکم"}],
        "overlay": {"mark": True, "cta_fa": "عضو شوید"},
        "brand": {"ink": "#0E1116", "accent": "#F2B705", "palette": ["#0E1116", "#F2B705"],
                  "mark": {"vb": "0 0 100 100", "layers": [{"role": "ink", "color": "#FFFFFF",
                                                            "d": "M0 0 L100 0 L100 100 Z"}]}},
        "safe_zone": {"top": 0.14, "right": 0.06, "bottom": 0.20, "left": 0.06},
        "limits": {"timeout_s": 600},
    }  # fmt: skip
    data.update(over)
    return data


FILES = {ASSET: b"\x89PNG fake", VOICE: b"OggS fake"}


# ---------------------------------------------------------------- spec --
def test_a_job_parses_with_its_files_captions_and_brand() -> None:
    j = S.parse(job())
    assert j.video and j.duration_s == 30.0 and j.mark and j.cta_fa == "عضو شوید"
    assert [c.text_fa for c in j.captions] == ["یکم", "دوم"]  # in time order
    assert [f.id for f in j.files()] == [ASSET, VOICE]
    assert j.brand.mark_vb == "0 0 100 100" and j.safe.bottom == 0.2


@pytest.mark.parametrize(
    "change",
    [
        {"id": "../etc"},
        {"composition": {"format": "svg", "sha256": "0" * 64, "source": "x"}},
        {"duration_s": None},
        {"outputs": []},
        {"assets": [{"id": "x", "mime": "image/png", "sha256": "0" * 64}]},
        {"captions": [{"start_s": 3, "end_s": 2, "text_fa": "x"}]},
        {"brand": {"ink": "red"}},
        {
            "brand": {
                "ink": "#000000",
                "mark": {"vb": "0 0 1 1", "layers": [{"color": "#000000", "d": 'M0 0"/><script>'}]},
            }
        },
        {"safe_zone": {"top": 0.9}},
        {
            "outputs": [
                {
                    "name": "a",
                    "placement": "instagram_reel",
                    "width": 1080,
                    "height": 1920,
                    "video": True,
                    "max_bytes": 1000,
                    "at_s": 1.0,
                }
            ]
        },
    ],
)
def test_a_job_out_of_shape_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(S.SpecError):
        S.parse(job(**change))


def test_a_still_carries_its_time_for_a_carousel_slide() -> None:
    j = S.parse(job(kind="carousel", duration_s=None, outputs=[
        {"name": f"slide{k}", "placement": "instagram_post", "width": 1080, "height": 1350,
         "video": False, "format": "jpeg", "max_bytes": 8_000_000, "at_s": k - 0.5}
        for k in (1, 2, 3)
    ]))  # fmt: skip
    assert [o.at_s for o in j.outputs] == [0.5, 1.5, 2.5]
    assert S.parse(job(kind="post", duration_s=None, outputs=[
        {"name": "post", "placement": "instagram_post", "width": 1080, "height": 1350,
         "video": False, "max_bytes": 8_000_000}])).outputs[0].at_s == 0.0  # fmt: skip


def test_one_render_per_shape_under_the_smaller_limits() -> None:
    reel = {"placement": "instagram_reel", "width": 1080, "height": 1920, "video": True, "fps": 30}
    j = S.parse(job(outputs=[
        {**reel, "name": "instagram_reel", "max_duration_s": 90, "max_bytes": 100_000_000},
        {**reel, "name": "telegram_post", "placement": "telegram_post", "max_duration_s": 600,
         "max_bytes": 50_000_000},
        {**reel, "name": "square", "width": 1080, "height": 1080, "max_bytes": 50_000_000},
    ]))  # fmt: skip
    groups = S.shapes(j.outputs)
    assert [[o.name for o in g] for g in groups] == [
        ["instagram_reel", "telegram_post"],
        ["square"],
    ]
    assert groups[0][0].max_bytes == 50_000_000 and groups[0][0].max_duration_s == 90


def test_the_composition_is_checked_again_before_anything_is_drawn() -> None:
    assert S.refusal(S.parse(job())) is None
    bad = HTML.replace("</body>", "<script>fetch('/x')</script></body>")
    j = S.parse(
        job(composition={"format": "html", "sha256": composition.sha256(bad), "source": bad})
    )
    assert S.refusal(j) == "composition_refused: fetch"
    changed = S.parse(job(composition={"format": "html", "sha256": "0" * 64, "source": HTML}))
    assert S.refusal(changed) == "sha256_mismatch"


# ------------------------------------------------------------- harness --
def test_the_harness_serves_only_its_own_files_and_aborts_the_rest(tmp_path: Path) -> None:
    assets = {ASSET: (str(tmp_path / ASSET), "image/png")}
    lib, fonts = tmp_path / "lib", tmp_path / "fonts"
    o = H.ORIGIN
    assert H.decide(o + "/composition", assets, lib, fonts).kind == "composition"
    assert H.decide(o + "/lib/anime.min.js", assets, lib, fonts).path == str(lib / "anime.min.js")
    assert H.decide(o + "/lib/lottie.min.js", assets, lib, fonts).kind == "lib"
    assert H.decide(o + "/fonts/IRANYekanX-Bold.woff2", assets, lib, fonts).mime == "font/woff2"
    assert H.decide(o + f"/assets/{ASSET}", assets, lib, fonts).kind == "asset"
    for url in (
        o + "/assets/0b4a5c6d-0000-4000-8000-000000000000",  # not this job's file
        o + "/lib/jquery.js",
        o + f"/assets/{ASSET}?x=1",
        o + "/../etc/passwd",
        "https://evil.example/p.png",
        "http://render.hq.invalid/composition",
        "https://render.hq.invalid.evil.example/composition",
        "wss://render.hq.invalid/x",
    ):
        a = H.decide(url, assets, lib, fonts)
        assert a.kind == "abort" and a.violation, url
    assert not H.decide(o + "/favicon.ico", assets, lib, fonts).violation


def test_the_page_is_on_a_strict_csp_and_a_virtual_clock() -> None:
    for d in ("default-src 'none'", "connect-src 'none'", "worker-src 'none'", "frame-src 'none'",
              "base-uri 'none'", "form-action 'none'"):  # fmt: skip
        assert d in H.CSP
    assert "unsafe-eval" not in H.CSP
    for hook in ("window.setTimeout", "window.requestAnimationFrame", "Math.random", "performance",
                 "document.getAnimations", "goToAndStop", "setCurrentTime", "window.Date"):  # fmt: skip
        assert hook in H.CLOCK_JS
    assert "innerHTML" not in H.OVERLAY_JS and "textContent" in H.OVERLAY_JS


# ------------------------------------------------------------- overlays --
def test_mark_cta_and_captions_sit_inside_the_safe_zone() -> None:
    safe = S.SafeZone(0.14, 0.06, 0.20, 0.06)
    lay = L.layout(1080, 1920, safe, mark=True, cta=True)
    assert lay.mark.w == pytest.approx(1080 * 0.12)
    assert lay.mark.x == pytest.approx(1080 * 0.06)
    assert lay.mark.y + lay.mark.h == pytest.approx(1920 * 0.80)  # bottom-left of the safe zone
    assert lay.caption.y + lay.caption.h < lay.mark.y  # captions above the mark's row
    assert lay.caption.y >= 1920 * 0.14 and lay.caption.w == pytest.approx(1080 * 0.88)
    assert lay.cta.x > lay.mark.x + lay.mark.w and lay.cta.x + lay.cta.w <= 1080 * 0.94 + 0.01
    assert lay.caption_font_px == 48 and lay.cta_font_px == 43
    bare = L.layout(1080, 1350, S.SafeZone(0.05, 0.05, 0.05, 0.05), mark=False, cta=False)
    assert bare.caption.y + bare.caption.h == pytest.approx(1350 * 0.95)


def test_caption_windows_and_webvtt() -> None:
    caps = (S.Caption(0.3, 6.0, "یکم"), S.Caption(5.2, 9.8, "دوم <b>"), S.Caption(29.9, 31.0, "آخر"),
            S.Caption(9.8, 9.85, "خیلی کوتاه"))  # fmt: skip
    win = L.cue_windows(caps, 30.0)
    assert win == [(0.3, 5.2, "یکم"), (5.2, 9.8, "دوم <b>"), (29.9, 30.0, "آخر")]
    vtt = L.webvtt(win)
    assert vtt.startswith("WEBVTT\n\n1\n00:00:00.300 --> 00:00:05.200\nیکم\n")
    assert "دوم &lt;b&gt;" in vtt and "00:00:29.900 --> 00:00:30.000" in vtt


# --------------------------------------------------------------- ffmpeg --
def test_the_encode_is_h264_high_yuv420p_faststart_with_aac_and_overlays() -> None:
    args = FF.encode_args(
        "/jobs/x/out/r.mp4", fps=30, duration_s=30.0, max_bytes=100 * 1024 * 1024,
        overlays=[FF.Overlay("/m.png"), FF.Overlay("/c1.png", 0.3, 5.2)], voice="/v.ogg",
    )  # fmt: skip
    s = " ".join(args)
    assert args[:2] == ["ffmpeg", "-hide_banner"] and "-i pipe:0" in s and "-c:v mjpeg" in s
    assert "-c:v libx264 -profile:v high" in s and "-pix_fmt yuv420p" in s
    assert "-movflags +faststart" in s and "-t 30.000" in s and "-c:a aac -b:a 128k -ar 48000" in s
    assert "overlay=0:0:eof_action=repeat[b1]" in s
    assert "enable='between(t,0.300,5.200)'" in s and "-maxrate 8000k" in s
    assert args.index("/v.ogg") > args.index("/c1.png")  # the voice is input 3
    assert "[3:a]aresample=48000,apad[a]" in s
    silent = " ".join(FF.encode_args("o.mp4", fps=30, duration_s=10, overlays=[], voice=None,
                                     max_bytes=50 * 1024 * 1024))  # fmt: skip
    assert "anullsrc=r=48000:cl=stereo" in silent and "[1:a]aresample" in silent


def test_the_bitrate_cap_follows_the_byte_limit() -> None:
    assert FF.video_kbps(100 * 1024 * 1024, 30) == 8000
    small = FF.video_kbps(10 * 1024 * 1024, 60)
    assert 300 <= small < 8000 and small * 60 / 8 * 1000 < 10 * 1024 * 1024
    assert FF.video_kbps(1024, 60) == 300


def test_stills_posters_and_probes() -> None:
    s = FF.still_args("/a.png", ["/m.png"], "/o.jpg", fmt="jpeg", quality=4)
    assert "[0:v][1:v]overlay=0:0[s1]" in " ".join(s) and "-q:v" in s and s[-1] == "/o.jpg"
    assert "-filter_complex" not in FF.still_args("/a.png", [], "/o.png", fmt="png")
    poster = FF.poster_args("/v.mp4", "/p.jpg", 1.0)
    assert poster[poster.index("-ss") + 1] == "1.000" and poster[-1] == "/p.jpg"
    assert FF.probe_args("/v.mp4")[0] == "ffprobe"


# -------------------------------------------------------------- courier --
class FakeApi:
    """/internal/v1/media/render: a queue of jobs, then 204 (idle, or locked)."""

    def __init__(self, jobs: list[dict[str, Any]], files: dict[str, bytes] | None = None) -> None:
        self.jobs = list(jobs)
        self.files = dict(FILES if files is None else files)
        self.outputs: list[tuple[dict[str, str], bytes, str]] = []
        self.done: list[dict[str, Any]] = []
        self.failed: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer t"
        path = request.url.path
        base = "/internal/v1/media/render"
        if path == f"{base}/claim":
            return httpx.Response(200, json=self.jobs.pop(0)) if self.jobs else httpx.Response(204)
        if "/files/" in path:
            fid = path.rsplit("/", 1)[1]
            return (
                httpx.Response(200, content=self.files[fid])
                if fid in self.files
                else httpx.Response(404)
            )
        if path.endswith("/output"):
            self.outputs.append(
                (dict(request.url.params), request.read(), request.headers["content-type"])
            )
            return httpx.Response(201, json={"file_id": ASSET})
        if path.endswith("/done"):
            self.done.append(json.loads(request.read()))
            return httpx.Response(200, json={})
        if path.endswith("/fail"):
            self.failed.append(json.loads(request.read())["error"])
            return httpx.Response(200, json={})
        return httpx.Response(404)


def client(api: FakeApi) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://api:8000", headers={"Authorization": "Bearer t"},
                             transport=httpx.MockTransport(api.handler))  # fmt: skip


async def test_nothing_to_render_writes_nothing(tmp_path: Path) -> None:
    api = FakeApi([])
    async with client(api) as c:
        assert await C.claim(c, tmp_path) is None
    assert os.listdir(tmp_path) == []


async def test_a_claimed_job_is_laid_out_with_its_checked_files(tmp_path: Path) -> None:
    api = FakeApi([job()])
    async with client(api) as c:
        assert await C.claim(c, tmp_path) == JOB_ID
    d = tmp_path / JOB_ID
    assert json.loads((d / "job.json").read_text())["item"] == "MI-0007"
    assert (d / "files" / ASSET).read_bytes() == FILES[ASSET]
    assert (d / "files" / VOICE).read_bytes() == FILES[VOICE]


async def test_a_file_that_differs_fails_the_job_and_leaves_nothing(tmp_path: Path) -> None:
    api = FakeApi([job()], files={ASSET: b"something else", VOICE: FILES[VOICE]})
    async with client(api) as c:
        assert await C.claim(c, tmp_path) is None
    assert api.failed and api.failed[0].startswith("fetch_failed:")
    assert not (tmp_path / JOB_ID).exists()


async def test_a_job_out_of_shape_is_failed_at_once(tmp_path: Path) -> None:
    api = FakeApi([job(kind="movie")])
    async with client(api) as c:
        with pytest.raises(C.CourierError):
            await C.claim(c, tmp_path)
    assert api.failed == ["bad_job: bad kind"]


def _rendered(root: Path, manifest: dict[str, Any], files: dict[str, bytes]) -> None:
    out = root / JOB_ID / "out"
    out.mkdir(parents=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "manifest.json").write_text(json.dumps(manifest))


async def test_send_posts_every_output_then_done_and_clears_the_job(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _rendered(tmp_path, {"status": "done", "violations": [], "metrics": {"seconds": 41.2, "frames": 900},
                         "outputs": [
        {"name": "instagram_reel", "kind": "video", "path": "instagram_reel.mp4", "mime": "video/mp4",
         "width": 1080, "height": 1920, "duration_s": 30.0},
        {"name": "instagram_reel", "kind": "poster", "path": "instagram_reel.poster.jpg",
         "mime": "image/jpeg", "width": 1080, "height": 1920},
        {"name": "captions", "kind": "captions", "path": "captions.vtt", "mime": "text/vtt"},
    ]}, {"instagram_reel.mp4": b"\x00\x00\x00 ftyp" * 300_000, "instagram_reel.poster.jpg": b"\xff\xd8",
         "captions.vtt": b"WEBVTT\n"})  # fmt: skip
    api = FakeApi([])
    async with client(api) as c:
        out = await C.send(c, tmp_path, JOB_ID)
    assert out == {"job": JOB_ID, "status": "done", "outputs": 3, "violations": 0}
    assert [(p["name"], p["kind"]) for p, _, _ in api.outputs] == [
        ("instagram_reel", "video"),
        ("instagram_reel", "poster"),
        ("captions", "captions"),
    ]
    assert api.outputs[0][0]["duration_s"] == "30.0" and api.outputs[0][2] == "video/mp4"
    assert len(api.outputs[0][1]) == 8 * 300_000  # streamed whole
    assert api.done == [{"metrics": {"seconds": 41.2, "frames": 900}, "violations": []}]
    assert not (tmp_path / JOB_ID).exists()
    assert "Bearer t" not in caplog.text and "Authorization" not in caplog.text


async def test_violations_are_reported_and_a_failure_is_failed(tmp_path: Path) -> None:
    _rendered(
        tmp_path,
        {
            "status": "done",
            "outputs": [],
            "metrics": {},
            "violations": [{"rule": "network_request", "detail": "https://x.example/"}],
        },
        {},
    )
    api = FakeApi([])
    async with client(api) as c:
        await C.send(c, tmp_path, JOB_ID)
    assert api.done[0]["violations"][0]["rule"] == "network_request" and not api.outputs
    _rendered(tmp_path, {"status": "failed", "error": "too_large: instagram_reel: 9 > 8 bytes"}, {})
    async with client(api) as c:
        assert (await C.send(c, tmp_path, JOB_ID))["error"] == "too_large"
    assert api.failed == ["too_large: instagram_reel: 9 > 8 bytes"]


async def test_a_killed_render_is_failed_and_a_bad_id_refused(tmp_path: Path) -> None:
    (tmp_path / JOB_ID).mkdir()
    api = FakeApi([])
    async with client(api) as c:
        assert (await C.send(c, tmp_path, JOB_ID))["error"] == "render_killed"
        with pytest.raises(C.CourierError):
            await C.send(c, tmp_path, "../x")
    assert api.failed == ["render_killed: no result (timeout or memory)"]
