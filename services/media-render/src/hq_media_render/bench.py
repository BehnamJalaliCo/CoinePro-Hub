"""`bench reel|lottie|design|sneak`: the render worker's acceptance numbers on this
server (prompt 13 §6, §8), offline, in the real image with no network
(`make media-bench`): a 30-second 1080x1920 reel (CSS animation, SMIL,
anime.js, Persian text with isolated Latin figures, an image asset, a voice,
burned-in captions, the mark and the call to action), a Lottie still (two
frames at two times, as a carousel's slides) and a design page (phone and
desktop, full page). Prints the wall time, the frames, the container's peak
memory (cgroup memory.peak), the peak of Chromium's processes, and what
ffprobe reads in every output. The fixtures are in fixtures/."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from hq_common import composition
from hq_media_render import ffmpeg as FF
from hq_media_render.render import cgroup_peak_mb, render_job
from hq_media_render.spec import parse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
INK, ACCENT, NAVY = "#0E1116", "#F2B705", "#1D3557"
MARK = {
    "vb": "0 0 100 100",
    "layers": [
        {
            "role": "ink",
            "color": "#FFFFFF",
            "d": "M50 4 L96 50 L50 96 L4 50 Z M50 24 L76 50 L50 76 L24 50 Z",
        },
        {"role": "accent", "color": ACCENT, "d": "M50 36 L64 50 L50 64 L36 50 Z"},
    ],
}
BRAND = {"ink": INK, "accent": ACCENT, "palette": [INK, ACCENT, NAVY, "#FFFFFF"], "mark": MARK}
SAFE_STORY = {"top": 0.14, "right": 0.06, "bottom": 0.20, "left": 0.06}
SAFE_POST = {"top": 0.05, "right": 0.05, "bottom": 0.05, "left": 0.05}
MB = 1024 * 1024
VOICE = [
    "بیت‌کوین چیست؟ در سی ثانیه می‌گوییم.",
    "یک دفتر حساب عمومی که هر ده دقیقه یک بلوک تازه می‌گیرد.",
    "بی‌تی‌سی تتر یعنی قیمت بیت‌کوین بر حسب تتر.",
    "عرضه‌اش محدود است: حداکثر بیست و یک میلیون سکه.",
    "معامله‌ی رمزارز پرریسک است و ممکن است سرمایه از دست برود.",
    "هر روز یک درس کوتاه در کانال کوینه‌پرو.",
]


def _sh(*args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argv: ffmpeg's test sources
        args, check=True, stdin=subprocess.DEVNULL, capture_output=True
    )


def _file(d: Path, path: Path, mime: str) -> dict[str, Any]:
    fid = str(uuid.uuid4())
    data = path.read_bytes()
    (d / "files" / fid).write_bytes(data)
    path.unlink()
    digest = hashlib.sha256(data).hexdigest()
    return {"id": fid, "name": path.name, "mime": mime, "sha256": digest, "size": len(data)}


def _composition(fmt: str, source: str) -> dict[str, str]:
    return {"format": fmt, "sha256": composition.sha256(source), "source": source}


def _output(name: str, placement: str, w: int, h: int, **more: Any) -> dict[str, Any]:
    return {"name": name, "placement": placement, "width": w, "height": h, **more}


def _reel(d: Path) -> dict[str, Any]:
    ff = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i")
    png, ogg = d / "bg.png", d / "voice.ogg"
    _sh(*ff, "gradients=s=1080x1080:c0=0x1D3557:c1=0x0E1116:d=1", "-frames:v", "1", str(png))
    tone = "sine=frequency=220:duration=28,volume=0.15"
    _sh(*ff, tone, "-c:a", "libopus", "-b:a", "32k", str(ogg))
    asset = _file(d, png, "image/png")
    voice = {**_file(d, ogg, "audio/ogg"), "duration_s": 28.0}
    source = (FIXTURES / "reel.html").read_text(encoding="utf-8").replace("@ASSET@", asset["id"])
    video = {"video": True, "fps": 30}
    return {
        "kind": "reel",
        "duration_s": 30.0,
        "assets": [asset],
        "voice": voice,
        "safe_zone": SAFE_STORY,
        "composition": _composition("html", source),
        "captions": [
            {"start_s": i * 5 + 0.3, "end_s": i * 5 + 4.8, "text_fa": t}
            for i, t in enumerate(VOICE)
        ],
        "overlay": {"mark": True, "cta_fa": "عضو کانال شوید"},
        "outputs": [
            _output("instagram_reel", "instagram_reel", 1080, 1920, **video, max_duration_s=90,
                    max_bytes=100 * MB),
            _output("telegram_post", "telegram_post", 1080, 1920, **video, max_duration_s=600,
                    max_bytes=50 * MB),
        ],
    }  # fmt: skip


def _lottie() -> dict[str, Any]:
    source = json.dumps(json.loads((FIXTURES / "still.json").read_text(encoding="utf-8")))
    still = {"video": False, "format": "jpeg", "max_bytes": 8 * MB}
    return {
        "kind": "carousel",
        "duration_s": None,
        "safe_zone": SAFE_POST,
        "composition": _composition("lottie", source),
        "overlay": {"mark": True, "cta_fa": None},
        "outputs": [
            _output("slide1", "instagram_post", 1080, 1350, **still, at_s=0.5),
            _output("slide2", "instagram_post", 1080, 1350, **still, at_s=1.5),
        ],
    }


def _design() -> dict[str, Any]:
    card = (
        '<section class="card"><h2>درس {n}</h2><p>متن آزمایشی صفحه با عدد <bdi>{p}%</bdi> و '
        '<bdi>BTC</bdi>.</p><span class="cta">ادامه</span></section>'
    )
    cards = "".join(card.format(n=n, p=n * 7 + 0.5) for n in range(1, 10))
    source = (FIXTURES / "design.html").read_text(encoding="utf-8").replace("@CARDS@", cards)
    page = {"video": False, "format": "png", "full_page": True, "max_bytes": 20 * MB}
    return {
        "kind": "design",
        "duration_s": None,
        "safe_zone": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        "composition": _composition("html", source),
        "overlay": {"mark": False, "cta_fa": None},
        "outputs": [
            _output("phone", "design_phone", 390, 844, **page, scale=2),
            _output("desktop", "design_desktop", 1440, 900, **page),
        ],
    }


def _sneak() -> dict[str, Any]:
    """A still that passes the rule check here (any well-formed asset path) but
    asks for a file that is not the job's: the page's request is aborted and
    recorded, and no output is made."""
    other = "0b4a5c6d-0000-4000-8000-000000000000"
    source = (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"></head>'
        f'<body style="font-family: IRANYekanX"><img src="/assets/{other}" alt=""></body></html>'
    )
    return {
        "kind": "post",
        "duration_s": None,
        "safe_zone": SAFE_POST,
        "composition": _composition("html", source),
        "overlay": {"mark": False, "cta_fa": None},
        "outputs": [_output("post", "instagram_post", 1080, 1350, video=False, max_bytes=8 * MB)],
    }


FIXTURE_KINDS = ("reel", "lottie", "design", "sneak")


def fixture(kind: str, root: Path) -> tuple[dict[str, Any], Path]:
    jid = str(uuid.uuid4())
    d = root / jid
    (d / "files").mkdir(parents=True, mode=0o700)
    base: dict[str, Any] = {
        "id": jid,
        "item": "MI-0001",
        "company": "TY",
        "purpose": "final",
        "fps": 30,
        "assets": [],
        "voice": None,
        "music": None,
        "captions": [],
        "brand": BRAND,
        "limits": {"timeout_s": 600},
    }
    parts = {"lottie": _lottie, "design": _design, "sneak": _sneak}
    base.update(_reel(d) if kind == "reel" else parts[kind]())
    (d / "job.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return base, d


def probe(path: Path) -> dict[str, Any]:
    out = subprocess.run(  # noqa: S603 - fixed argv: ffprobe of our own output
        FF.probe_args(str(path)), check=True, capture_output=True
    ).stdout
    info = json.loads(out)
    v: dict[str, Any] = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a: dict[str, Any] = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    return {
        "vcodec": v.get("codec_name"),
        "profile": v.get("profile"),
        "pix_fmt": v.get("pix_fmt"),
        "w": v.get("width"),
        "h": v.get("height"),
        "duration_s": round(float(info["format"].get("duration") or 0), 3),
        "acodec": a.get("codec_name"),
        "sample_rate": a.get("sample_rate"),
    }


def _video_ok(row: dict[str, Any], duration: float) -> bool:
    return bool(
        row["vcodec"] == "h264"
        and row["profile"] == "High"
        and row["pix_fmt"] == "yuv420p"
        and abs(row["duration_s"] - duration) < 0.1
        and row["acodec"] == "aac"
        and row["sample_rate"] == "48000"
        and (row["w"], row["h"]) == (1080, 1920)
    )


async def bench(kind: str, root: Path) -> int:
    data, d = fixture(kind, root)
    res = await render_job(parse(data), d)
    report: dict[str, Any] = {
        "fixture": kind,
        "status": res.status,
        "error": res.error,
        "violations": res.violations,
        **res.metrics,
        "outputs": [],
    }
    ok = res.status == "done" and not res.violations
    if kind == "sneak":  # the runtime filter's proof: a violation and nothing made
        rules = {v["rule"] for v in res.violations}
        ok = res.status == "done" and rules == {"network_request"} and not res.outputs
    for o in res.outputs:
        row = {"name": o["name"], "kind": o["kind"], "bytes": o["bytes"]}
        if o["kind"] in ("video", "poster", "image"):
            row.update(probe(d / "out" / o["path"]))
        if o["kind"] == "video":
            ok = ok and _video_ok(row, float(data["duration_s"]))
        report["outputs"].append(row)
    if kind == "reel":
        ok = ok and {o["kind"] for o in res.outputs} == {"video", "poster", "captions"}
    report["peak_rss_mb"] = cgroup_peak_mb()
    report["ok"] = ok
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    kind = argv[0] if argv else "reel"
    if kind not in FIXTURE_KINDS:
        print("bench reel|lottie|design|sneak [dir]", file=sys.stderr)
        return 2
    root = Path(argv[1]) if len(argv) > 1 else Path("/jobs")
    return asyncio.run(bench(kind, root))
