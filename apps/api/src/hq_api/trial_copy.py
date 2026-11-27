"""⟨2026-11-26⟩ A reel's Trial Reel copy, as ffmpeg makes it (domain/trial_reels.py): the SAME reel,
very slightly changed, at the reels' own top quality. The standard library only: the worker
imports it, and the hub host runs it as a script (`coinepro-hq-trial-copy.timer`, every minute).

Why the host: x264 on a 1080x1920 60 fps reel takes 280-450 MiB (measured 2026-11-27), past what
the worker's 512 MiB holds beside its own work; the host has the room. The worker asks, the host
makes, the worker takes (all in the file volume, never a network call):

    <volume>/trial-copies/<P-000123-1>.json   the worker's ask: {"key": <the reel's storage key>,
                                               "recipe": recipe_of(...)}
    <volume>/trial-copies/<P-000123-1>.mp4    the host's copy (written as .part, then renamed)
    <volume>/trial-copies/<P-000123-1>.err    the host's failure (the worker asks again an hour on)

The host checks every value (the key is 32 hex digits, the recipe's numbers in their ranges) and
builds ffmpeg's arguments itself; ffmpeg and ffprobe run as the volume's owner (uid 10001), read
only that file with the allowed demuxers (as hq_api.media.ff_input), at most two threads, under a
deadline. One copy per run.

    python3 -I trial_copy.py [--dry-run]
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

QUEUE = "trial-copies"
FORMATS = "mov,mp4,matroska,webm,ogg,mp3,aac,wav"  # as hq_api.media.FORMATS
THREADS = "2"
AUDIO = "256k"
VBV_K = 16000  # the kits' cap (4e7848a5): at most 16 Mbit/s, ~180 MB for the longest reel
CRF = (14, 16, 18)  # a larger one only when the copy would pass IG-Hub's 200 MB
SIZE_MAX = 190 * 1024 * 1024
ENCODE_LIMIT_S = 1800
RID = re.compile(r"^P-\d{6,9}-[1-9]$")
KEY = re.compile(r"^[0-9a-f]{32}$")
VOLUME = Path("/var/lib/docker/volumes/coinepro-hq_hq-files/_data")
OWNER = 10001  # the file volume's owner (the api's and the worker's user)
RANGES = {
    "zoom": (0.01, 0.025),
    "brightness": (-0.015, 0.015),
    "contrast": (0.985, 1.015),
    "saturation": (0.98, 1.02),
    "trim_frames": (0, 6),
    "cover_zoom": (0.01, 0.03),
    "cover_light": (0.98, 1.02),
}


def recipe_of(seed: str) -> dict[str, Any]:
    """How slightly this copy differs: the same for the same reel and try."""
    rng = random.Random(seed)  # noqa: S311 - a spread, not a secret
    sign = rng.choice((-1, 1))
    return {
        "zoom": round(rng.uniform(0.012, 0.02), 4),
        "brightness": round(sign * rng.uniform(0.006, 0.012), 4),
        "contrast": round(1 + rng.choice((-1, 1)) * rng.uniform(0.006, 0.012), 4),
        "saturation": round(1 + rng.choice((-1, 1)) * rng.uniform(0.008, 0.014), 4),
        "trim_frames": rng.randint(2, 4),
        "cover_zoom": round(rng.uniform(0.012, 0.022), 4),
        "cover_light": round(1 + sign * rng.uniform(0.008, 0.015), 4),
    }


def checked(recipe: Any) -> dict[str, Any]:
    """The recipe when every value is a number in its range; ValueError else."""
    if not isinstance(recipe, dict):
        raise ValueError("no recipe")
    out: dict[str, Any] = {}
    for k, (lo, hi) in RANGES.items():
        v = recipe.get(k)
        if isinstance(v, bool) or not isinstance(v, int | float) or not lo <= v <= hi:
            raise ValueError(f"recipe {k}")
        out[k] = int(v) if k == "trim_frames" else float(v)
    return out


def fps_of(raw: str | None) -> tuple[str, float]:
    """ffprobe's frame rate as ffmpeg takes it again, and its value (30 when unreadable)."""
    try:
        a, _, b = str(raw or "").partition("/")
        value = float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        return "30", 30.0
    if not 1 <= value <= 120 or not re.fullmatch(r"\d{1,6}(/\d{1,6})?", str(raw)):
        return "30", 30.0
    return str(raw), value


def info_of(probe: dict[str, Any]) -> dict[str, Any]:
    """What the copy keeps of the reel: its size, frame rate, sound and length."""
    streams = probe.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v is None or not v.get("width") or not v.get("height"):
        raise ValueError("the reel has no picture")
    avg = v.get("avg_frame_rate")
    rate, fps = fps_of(avg if avg not in (None, "0/0") else v.get("r_frame_rate"))
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "rate": rate,
        "fps": fps,
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "duration_s": float((probe.get("format") or {}).get("duration") or 0) or None,
    }


def trim_of(r: dict[str, Any], fps: float) -> int:
    """The frames taken off the start: a few, never more than 0.15 s of the reel."""
    return max(0, min(int(r["trim_frames"]), int(fps * 0.15)))


def vbv_k(duration_s: float | None) -> int:
    """The kits' cap: at most 16 Mbit/s, less for a reel so long that 16 would pass ~180 MB."""
    end = max(float(duration_s or 90.0), 1.0)
    return max(4000, min(VBV_K, int(180e6 * 8 / end / 1000) - 256))


def _even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def ff_input(path: Path) -> list[str]:
    return ["-protocol_whitelist", "file", "-format_whitelist", FORMATS, "-i", f"file:{path}"]


def ffmpeg_args(
    src: Path, out: Path, info: dict[str, Any], r: dict[str, Any], crf: int
) -> list[str]:
    """x264 CRF `crf` (aq-mode 3, the VBV cap), the same size and frame rate, BT.709 tags, sound
    AAC 256k; a 1.2-2 % centre zoom, ~1 % of brightness/contrast/saturation, a few frames off the
    start, no metadata."""
    w, h = info["width"], info["height"]
    cw, ch = _even(w * (1 - r["zoom"])), _even(h * (1 - r["zoom"]))
    cut = trim_of(r, info["fps"])
    start_s = cut / info["fps"]
    k = vbv_k(info.get("duration_s"))
    graph = (
        f"[0:v]trim=start_frame={cut},setpts=PTS-STARTPTS,"
        f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2,scale={w}:{h}:flags=lanczos,"
        f"eq=brightness={r['brightness']}:contrast={r['contrast']}:saturation={r['saturation']},"
        f"setsar=1,format=yuv420p[v]"
    )
    maps = ["-map", "[v]"]
    if info["audio"]:
        graph += f";[0:a]atrim=start={start_s:.4f},asetpts=PTS-STARTPTS[a]"
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", AUDIO, "-ar", "48000"]
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-filter_threads", "1",
        "-threads", THREADS, *ff_input(src), "-filter_complex", graph, *maps,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-x264-params", "rc-lookahead=20:aq-mode=3",
        "-maxrate", f"{k}k", "-bufsize", f"{k}k",
        "-r", info["rate"], "-fps_mode", "cfr", "-threads", THREADS,
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart",
        "-f", "mp4", str(out),
    ]  # fmt: skip


# ------------------------------------------------------------- the host's run --
def _as_owner(argv: list[str], limit: float) -> subprocess.CompletedProcess[bytes]:
    pre = (
        ["setpriv", f"--reuid={OWNER}", f"--regid={OWNER}", "--clear-groups", "--"]
        if os.geteuid() == 0
        else []
    )
    return subprocess.run(  # noqa: S603 - fixed tools, checked values
        [*pre, *argv], stdin=subprocess.DEVNULL, capture_output=True, timeout=limit, check=False
    )


def probe(path: Path) -> dict[str, Any]:
    p = _as_owner(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         *ff_input(path)], 60,
    )  # fmt: skip
    if p.returncode != 0:
        raise ValueError("ffprobe could not read the reel")
    return info_of(json.loads(p.stdout or b"{}"))


def make(volume: Path, rid: str, ask: dict[str, Any]) -> Path:
    """The copy of one ask, as <rid>.mp4 beside it."""
    key = str(ask.get("key") or "")
    if not KEY.fullmatch(key):
        raise ValueError("bad key")
    r = checked(ask.get("recipe"))
    src = volume / key[:2] / key
    if not src.is_file():
        raise ValueError("the reel's video is gone")
    info = probe(src)
    q = volume / QUEUE
    part, done = q / f"{rid}.part", q / f"{rid}.mp4"
    for crf in CRF:
        p = _as_owner(ffmpeg_args(src, part, info, r, crf), ENCODE_LIMIT_S)
        if p.returncode != 0 or not part.is_file():
            part.unlink(missing_ok=True)
            raise ValueError("ffmpeg: " + p.stderr.decode("utf-8", "replace")[-300:])
        if part.stat().st_size <= SIZE_MAX:
            part.replace(done)
            return done
    part.unlink(missing_ok=True)
    raise ValueError("the copy stays past IG-Hub's 200 MB")


def run(volume: Path = VOLUME, dry: bool = False) -> int:
    q = volume / QUEUE
    if not q.is_dir():
        return 0
    for ask_file in sorted(q.glob("*.json"), key=lambda p: p.stat().st_mtime):
        rid = ask_file.stem
        if not RID.fullmatch(rid):
            continue
        if (q / f"{rid}.mp4").exists() or (q / f"{rid}.err").exists():
            continue
        if dry:
            print(f"would make {rid}")
            return 0
        t = time.monotonic()
        try:
            ask = json.loads(ask_file.read_text(encoding="utf-8"))
            done = make(volume, rid, ask if isinstance(ask, dict) else {})
            if os.geteuid() == 0:
                os.chown(done, OWNER, OWNER)
            print(
                f"trial copy {rid}: {done.stat().st_size / 1e6:.1f} MB in {time.monotonic() - t:.0f} s"
            )
        except (ValueError, OSError, subprocess.TimeoutExpired) as e:
            err = q / f"{rid}.err"
            err.write_text(str(e)[:1000], encoding="utf-8")
            if os.geteuid() == 0:
                os.chown(err, OWNER, OWNER)
            print(f"trial copy {rid} failed: {str(e)[:300]}", file=sys.stderr)
        return 1  # one copy per run
    return 0


if __name__ == "__main__":
    run(dry="--dry-run" in sys.argv[1:])
