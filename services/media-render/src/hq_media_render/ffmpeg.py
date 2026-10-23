"""ffmpeg's arguments for a render (pure). Frames arrive as JPEG on stdin at
the job's fps; the hub's own overlays (captions, mark, call to action) are
transparent PNGs laid on top for their time windows; the narration (or
silence) becomes AAC 128k. H.264 High, yuv420p, +faststart, the exact
duration, a bitrate cap from the output's byte limit."""

from __future__ import annotations

from dataclasses import dataclass

AUDIO_KBPS = 128
MAX_VIDEO_KBPS = 8000  # the platforms' own recommendation for 1080p reels and stories
THREADS = 2


@dataclass(frozen=True)
class Overlay:
    path: str
    start_s: float | None = None  # None: the whole video
    end_s: float | None = None


def video_kbps(max_bytes: int, duration_s: float) -> int:
    """The video bitrate cap that keeps the file under max_bytes (10% kept for
    the container and the audio's own share)."""
    budget = max_bytes * 8 * 0.9 / 1000 / max(duration_s, 0.5) - AUDIO_KBPS
    return max(300, min(MAX_VIDEO_KBPS, int(budget)))


def encode_args(
    out: str,
    *,
    fps: int,
    duration_s: float,
    overlays: list[Overlay],
    voice: str | None,
    max_bytes: int,
    frame_codec: str = "mjpeg",
    preset: str = "veryfast",
) -> list[str]:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y"]
    args += ["-f", "image2pipe", "-framerate", str(fps), "-c:v", frame_codec, "-i", "pipe:0"]
    for o in overlays:
        # One frame each, repeated by the overlay filter (eof_action=repeat):
        # a looped image would race ahead of the frames and queue up in memory.
        args += ["-i", o.path]
    if voice is not None:
        args += ["-i", voice]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    audio_index = 1 + len(overlays)
    chain = ["[0:v]setsar=1[b0]"]
    last = "b0"
    for i, o in enumerate(overlays, start=1):
        enable = ""
        if o.start_s is not None and o.end_s is not None:
            enable = f":enable='between(t,{o.start_s:.3f},{o.end_s:.3f})'"
        chain.append(f"[{last}][{i}:v]overlay=0:0:eof_action=repeat{enable}[b{i}]")
        last = f"b{i}"
    chain.append(f"[{last}]format=yuv420p[v]")
    audio = "[a]"
    chain.append(f"[{audio_index}:a]aresample=48000,apad[a]")
    kbps = video_kbps(max_bytes, duration_s)
    args += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", audio]
    args += [
        "-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", "21",
        "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-g", str(fps * 2), "-threads", str(THREADS),
        "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ar", "48000", "-ac", "2",
        "-t", f"{duration_s:.3f}", "-movflags", "+faststart", out,
    ]  # fmt: skip
    return args


def poster_args(video: str, out: str, at_s: float) -> list[str]:
    """One frame of the encoded video (with the hub's overlays) as JPEG."""
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{at_s:.3f}",
        "-i", video, "-frames:v", "1", "-q:v", "3", out,
    ]  # fmt: skip


def still_args(
    shot: str, overlays: list[str], out: str, *, fmt: str, quality: int = 2
) -> list[str]:
    """A still: the composition's screenshot with the hub's overlays on top."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", shot]
    for o in overlays:
        args += ["-i", o]
    chain = []
    last = "0:v"
    for i in range(1, len(overlays) + 1):
        chain.append(f"[{last}][{i}:v]overlay=0:0[s{i}]")
        last = f"s{i}"
    if chain:
        args += ["-filter_complex", ";".join(chain), "-map", f"[{last}]"]
    args += ["-frames:v", "1"]
    if fmt == "jpeg":
        args += ["-q:v", str(quality), "-pix_fmt", "yuvj420p"]
    args.append(out)
    return args


def probe_args(path: str) -> list[str]:
    return [
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path,
    ]  # fmt: skip
