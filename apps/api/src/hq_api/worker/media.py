"""The media worker (prompt 6 §2-§3, contract §17.1-17.2): what an owner video
or audio file becomes for the agents, without a model.

- video: a `poster` frame, up to 12 key frames (scene changes, at most one
  per 5 s; evenly spaced ones when the scene never changes), each with its
  long edge <= 1568 px, and its sound track transcribed;
- audio: transcribed.
Transcription: the self-hosted Whisper service (`stt`, on its own network
with the worker only; nothing leaves the hub), then the deterministic Persian
normaliser, then an optional punctuation pass by the light model whose output
is dropped when it changes more than 8% of the words.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from hq_api.media import AGENT_PX
from hq_common import persian

MAX_FRAMES = 12
MIN_FRAME_GAP_S = 5
SCENE = 0.3
MAX_EDIT_RATIO = 0.08
PUNCTUATION_SYSTEM = (
    "You punctuate a Persian speech-to-text transcript. Add Persian punctuation (، ؛ ؟ .) and "
    "paragraph breaks, and join words the recogniser obviously split. Do NOT change, add, drop, "
    "translate or reorder any word, and do not fix grammar or style. Answer with the punctuated "
    "text only, nothing else."
)
_PTS = re.compile(r"pts_time:\s*([0-9.]+)")
_SCALE = f"scale='if(gt(iw,ih),min({AGENT_PX},iw),-2)':'if(gt(iw,ih),-2,min({AGENT_PX},ih))'"


async def _ffmpeg(*args: str, limit_s: float = 600) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-nostdin", "-y", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        out, err = await asyncio.wait_for(proc.communicate(), limit_s)
    except TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, out, err


async def poster(src: Path, duration: float | None) -> bytes:
    at = f"{min(1.0, (duration or 0) * 0.1):.3f}"
    code, out, _ = await _ffmpeg(
        "-ss", at, "-i", str(src), "-frames:v", "1", "-vf", _SCALE,
        "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1",
    )  # fmt: skip
    if code != 0 or not out:
        raise ValueError("no poster frame")
    return out


async def key_frames(src: Path, duration: float | None) -> list[tuple[float, bytes]]:
    """Up to 12 frames: on scene changes, at most one per 5 s; if the scene
    hardly changes, evenly spaced ones (so a talk still has frames)."""
    with tempfile.TemporaryDirectory(prefix="frames-") as tmp:
        select = (
            f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{MIN_FRAME_GAP_S})"
            f"*gt(scene\\,{SCENE})',showinfo,{_SCALE}"
        )
        code, _, err = await _ffmpeg(
            "-i", str(src), "-vf", select, "-fps_mode", "vfr", "-frames:v", str(MAX_FRAMES),
            "-q:v", "4", f"{tmp}/f%02d.jpg",
        )  # fmt: skip
        times = [float(t) for t in _PTS.findall(err.decode("utf-8", "replace"))]
        got = await asyncio.to_thread(_read_frames, Path(tmp), times)
        want = min(MAX_FRAMES, max(1, int((duration or 0) // MIN_FRAME_GAP_S)))
        if code == 0 and len(got) >= min(3, want):
            return got[:MAX_FRAMES]
        frames_out: list[tuple[float, bytes]] = []
        for k in range(want):
            at = (duration or 0) * (k + 0.5) / want
            c, out, _ = await _ffmpeg(
                "-ss", f"{at:.3f}", "-i", str(src), "-frames:v", "1", "-vf", _SCALE,
                "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "pipe:1",
            )  # fmt: skip
            if c == 0 and out:
                frames_out.append((round(at, 3), out))
        return frames_out


async def sound_track(src: Path, dst: Path) -> bool:
    """16 kHz mono WAV of the sound (False: there is none)."""
    code, _, _ = await _ffmpeg(
        "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(dst)
    )
    size = await asyncio.to_thread(lambda: dst.stat().st_size if dst.exists() else 0)
    return code == 0 and size > 44  # a WAV header alone is 44 bytes


def _read_frames(tmp: Path, times: list[float]) -> list[tuple[float, bytes]]:
    frames = sorted(tmp.glob("f*.jpg"))
    return [(times[i] if i < len(times) else 0.0, f.read_bytes()) for i, f in enumerate(frames)]


class SttUnavailable(Exception):
    """The stt service is not running (its profile is off) or did not answer."""


async def transcribe(
    url: str,
    audio: Path,
    *,
    limit_s: float = 900,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """POST the audio to the stt service; its answer (text normalised there)."""
    if not url:
        raise SttUnavailable("STT_URL is not set")
    data = await asyncio.to_thread(audio.read_bytes)
    try:
        async with httpx.AsyncClient(timeout=limit_s, transport=transport) as http:
            r = await http.post(
                url.rstrip("/") + "/v1/transcribe",
                content=data,
                headers={"Content-Type": "audio/wav"},
            )
    except httpx.HTTPError as exc:
        raise SttUnavailable(type(exc).__name__) from exc
    if r.status_code == 413:
        raise ValueError("too long for the speech recogniser")
    if r.status_code != 200:
        raise SttUnavailable(f"stt answered {r.status_code}")
    out: dict[str, Any] = r.json()
    return out


# ------------------------------------------------------ the punctuation pass --
def accept_punctuation(normalised: str, punctuated: str) -> tuple[bool, float]:
    """The model's output is kept only when it changes at most 8% of the words
    (hq_common.persian.words: punctuation and ZWNJ never count)."""
    distance = persian.word_edit_distance(normalised, punctuated)
    ratio = distance / max(len(persian.words(normalised)), 1)
    return ratio <= MAX_EDIT_RATIO, round(ratio, 4)


def scratch_dir(root: Path) -> Path:
    d = root / "tmp"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


@contextlib.contextmanager
def temp_file(root: Path, suffix: str) -> Any:
    path = scratch_dir(root) / f"{uuid.uuid4().hex}{suffix}"
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
