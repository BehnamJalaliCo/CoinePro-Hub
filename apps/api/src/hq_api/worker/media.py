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
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from hq_api.media import AGENT_PX, AUDIO, FF_THREADS, VIDEO, ff_input, run_tool
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


FALLBACK_TOTAL_S = 120.0  # all the evenly spaced frames together
WAV_BYTES_PER_S = 16000 * 2  # 16 kHz mono, 16-bit
WAV_HEADER = 44
LENGTH_SLACK_S = 0.5  # what a 15:00 upload may decode to beyond 900 s


def cap_s(kind: str) -> int:
    """What ffmpeg reads of a file at most: its kind's limit plus one second
    (06.1 §2). A WebM without a duration passed the upload's check; whatever
    it really holds, no more than this is ever decoded."""
    k = VIDEO if kind == "video" else AUDIO
    assert k.max_seconds is not None
    return k.max_seconds + 1


async def _ffmpeg(
    src: Path, *args: str, limit_s: float = 600, seek: str | None = None, cap: int | None = None
) -> tuple[int, bytes, bytes]:
    """ffmpeg on one untrusted input: only that local file and the allowed
    demuxers (media.ff_input), at most FF_THREADS threads, at most `cap`
    seconds of it; killed on the timeout and on cancellation."""
    before = ["-ss", seek] if seek else []
    if cap is not None:
        before += ["-t", str(cap)]
    return await run_tool(
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-filter_threads", "1",
        "-threads", FF_THREADS, *before, *ff_input(src), "-threads", FF_THREADS, *args,
        limit_s=limit_s,
    )  # fmt: skip


async def poster(src: Path, duration: float | None) -> bytes:
    at = f"{min(1.0, (duration or 0) * 0.1):.3f}"
    code, out, _ = await _ffmpeg(
        src, "-frames:v", "1", "-vf", _SCALE, "-f", "image2", "-c:v", "mjpeg", "-q:v", "3",
        "pipe:1", seek=at, limit_s=120,
    )  # fmt: skip
    if code != 0 or not out:
        raise ValueError("no poster frame")
    return out


async def key_frames(src: Path, duration: float | None) -> list[tuple[float, bytes]]:
    """Up to 12 frames: on scene changes, at most one per 5 s; if the scene
    hardly changes, evenly spaced ones (so a talk still has frames), all of
    them within FALLBACK_TOTAL_S."""
    with tempfile.TemporaryDirectory(prefix="frames-") as tmp:
        select = (
            f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{MIN_FRAME_GAP_S})"
            f"*gt(scene\\,{SCENE})',showinfo,{_SCALE}"
        )
        code, _, err = await _ffmpeg(
            src, "-vf", select, "-fps_mode", "vfr", "-frames:v", str(MAX_FRAMES), "-q:v", "4",
            f"{tmp}/f%02d.jpg", cap=cap_s("video"),
        )  # fmt: skip
        times = [float(t) for t in _PTS.findall(err.decode("utf-8", "replace"))]
        got = await asyncio.to_thread(_read_frames, Path(tmp), times)
        want = min(MAX_FRAMES, max(1, int((duration or 0) // MIN_FRAME_GAP_S)))
        if code == 0 and len(got) >= min(3, want):
            return got[:MAX_FRAMES]
        frames_out: list[tuple[float, bytes]] = []
        deadline = time.monotonic() + FALLBACK_TOTAL_S
        for k in range(want):
            left = deadline - time.monotonic()
            if left <= 1:
                break  # bounded: the frames so far are what the agents get
            at = (duration or 0) * (k + 0.5) / want
            try:
                c, out, _ = await _ffmpeg(
                    src, "-frames:v", "1", "-vf", _SCALE, "-f", "image2", "-c:v", "mjpeg",
                    "-q:v", "4", "pipe:1", seek=f"{at:.3f}", limit_s=left,
                )  # fmt: skip
            except TimeoutError:
                break
            if c == 0 and out:
                frames_out.append((round(at, 3), out))
        return frames_out


async def sound_track(src: Path, dst: Path, kind: str = "audio") -> bool:
    """16 kHz mono WAV of the sound (False: there is none). At most the
    kind's limit plus one second is decoded; a longer sound is refused here
    (ValueError), before a byte of it reaches the speech recogniser."""
    cap = cap_s(kind)
    code, _, _ = await _ffmpeg(
        src, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(dst), cap=cap
    )
    size = await asyncio.to_thread(lambda: dst.stat().st_size if dst.exists() else 0)
    if code != 0 or size <= WAV_HEADER:  # a WAV header alone is 44 bytes
        return False
    if (size - WAV_HEADER) / WAV_BYTES_PER_S > cap - 1 + LENGTH_SLACK_S:
        raise ValueError(f"longer than {(cap - 1) // 60} min")
    return True


def _read_frames(tmp: Path, times: list[float]) -> list[tuple[float, bytes]]:
    frames = sorted(tmp.glob("f*.jpg"))
    return [(times[i] if i < len(times) else 0.0, f.read_bytes()) for i, f in enumerate(frames)]


class SttUnavailable(Exception):
    """The stt service is not running (its profile is off) or did not answer."""


class SttBusy(Exception):
    """The stt service is up but kept answering 503 busy (06.1 §3): not
    "off"; the caller tries again later."""


BUSY_FIRST_S = 2.0  # the first pause after a busy answer; doubles, at most BUSY_MAX_S
BUSY_MAX_S = 30.0


# ⟨1.9⟩ contract §27.3: the hub runs Whisper `small` on demand, its memory
# limit sized on its measured peak transcribing 30 s (RUNBOOK §16: 648 MiB;
# 5 minutes in one request peaked at 1225): every recording goes to stt in
# pieces of at most CHUNK_S, each cut at the quietest moment of its last
# QUIET_SEARCH_S, one after another.
CHUNK_S = 30
QUIET_SEARCH_S = 5.0
QUIET_FRAME_S = 0.05
COLD_POLL_S = 1.0


def _quietest(frames: bytes, rate: int, start: int, end: int) -> int:
    """The frame index in [start, end) where a QUIET_FRAME_S window of 16-bit
    mono samples is quietest (the cut)."""
    import array

    step = max(int(QUIET_FRAME_S * rate), 1)
    best, best_at = None, end
    for at in range(start, max(end - step, start), step):
        window = array.array("h", frames[at * 2 : (at + step) * 2])
        energy = sum(abs(v) for v in window)
        if best is None or energy < best:
            best, best_at = energy, at + step // 2
    return best_at


def wav_chunks(data: bytes, seconds: float | None = None) -> list[tuple[float, bytes]]:
    """(start second, WAV bytes) of pieces of at most `seconds`, each cut at
    its quietest moment near the end (16-bit mono; else a plain cut); the
    audio itself when it is short or not a WAV the stdlib reads."""
    import io
    import wave

    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            params = w.getparams()
            rate, total = w.getframerate(), w.getnframes()
            per = max(int((seconds or CHUNK_S) * rate), 1)
            if total <= per:
                return [(0.0, data)]
            frames = w.readframes(total)
    except (wave.Error, EOFError):
        return [(0.0, data)]
    width = params.sampwidth * params.nchannels
    quiet = params.sampwidth == 2 and params.nchannels == 1
    search = min(int(QUIET_SEARCH_S * rate), per // 2)
    out: list[tuple[float, bytes]] = []
    at = 0
    while at < total:
        end = min(at + per, total)
        if end < total and quiet:
            end = _quietest(frames, rate, end - search, end)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as piece:
            piece.setparams(params)
            piece.writeframes(frames[at * width : end * width])
        out.append((at / rate, buf.getvalue()))
        at = end
    return out


def merge_pieces(pieces: list[tuple[float, dict[str, Any]]]) -> dict[str, Any]:
    """One answer of the stt service from the answers of the pieces."""
    if len(pieces) == 1:
        return pieces[0][1]
    first = pieces[0][1]
    total = sum(float(o.get("duration_s") or 0) for _, o in pieces)
    weighted = sum(
        float(o.get("confidence") or 0) * float(o.get("duration_s") or 0) for _, o in pieces
    )
    segments = [
        {**seg, "start_s": round(at + float(seg.get("start_s") or 0), 2),
         "end_s": round(at + float(seg.get("end_s") or 0), 2)}
        for at, o in pieces for seg in o.get("segments") or []
    ]  # fmt: skip
    timing: dict[str, float] = {}
    for _, o in pieces:
        for k, v in (o.get("timing") or {}).items():
            timing[k] = round(timing.get(k, 0.0) + float(v or 0), 3)
    return {
        **first,
        "text_raw": " ".join(t for _, o in pieces if (t := (o.get("text_raw") or "").strip())),
        "text": " ".join(t for _, o in pieces if (t := (o.get("text") or "").strip())),
        "duration_s": round(total, 2),
        "confidence": round(weighted / total, 4) if total else first.get("confidence"),
        "segments": segments,
        "timing": timing,
        "pieces": len(pieces),
    }


def demand(directory: str) -> None:
    """Ask the host for stt (contract §27.3): `want` touched in the demand
    directory starts the container (coinepro-hq-stt.path) and keeps it up;
    5 minutes without a touch, the host stops it. Never fails the caller."""
    if not directory:
        return
    with contextlib.suppress(OSError):
        Path(directory, "want").write_text(f"{time.time():.0f}\n", encoding="ascii")


async def transcribe(
    url: str,
    audio: Path,
    *,
    limit_s: float = 900,
    busy_wait_s: float = 120,
    transport: httpx.AsyncBaseTransport | None = None,
    demand_dir: str = "",
    cold_start_s: float = 120,
) -> dict[str, Any]:
    """POST the audio to the stt service; its answer (text normalised there).
    A `503 busy` (one transcription runs, the queue is full) is retried with
    a growing pause for up to `busy_wait_s`, then SttBusy. ⟨1.9⟩ The audio
    goes in pieces of at most CHUNK_S (the answers joined, timings shifted);
    with `demand_dir`, stt is asked for before each piece and a stopped stt
    is waited for up to `cold_start_s`."""
    if not url:
        raise SttUnavailable("STT_URL is not set")
    data = await asyncio.to_thread(audio.read_bytes)  # at most the kind's limit (sound_track)
    pieces = await asyncio.to_thread(wav_chunks, data)
    answers = []
    for at, piece in pieces:
        demand(demand_dir)
        answers.append(
            (at, await _post(url, piece, limit_s, busy_wait_s, transport, demand_dir, cold_start_s))
        )
    return merge_pieces(answers)


async def _post(
    url: str,
    data: bytes,
    limit_s: float,
    busy_wait_s: float,
    transport: httpx.AsyncBaseTransport | None,
    demand_dir: str = "",
    cold_start_s: float = 0,
) -> dict[str, Any]:
    waited, pause = 0.0, BUSY_FIRST_S
    cold = 0.0
    while True:
        try:
            async with httpx.AsyncClient(timeout=limit_s, transport=transport) as http:
                r = await http.post(
                    url.rstrip("/") + "/v1/transcribe",
                    content=data,
                    headers={"Content-Type": "audio/wav"},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # stt is stopped (on demand): ask for it and wait while it starts
            if not demand_dir or cold >= cold_start_s:
                raise SttUnavailable(type(exc).__name__) from exc
            demand(demand_dir)
            await asyncio.sleep(COLD_POLL_S)
            cold += COLD_POLL_S
            continue
        except httpx.HTTPError as exc:
            raise SttUnavailable(type(exc).__name__) from exc
        if r.status_code == 503 and _code(r) == "busy":
            if waited + pause > busy_wait_s:
                raise SttBusy(f"busy after {waited:.0f} s")
            await asyncio.sleep(pause)
            waited += pause
            pause = min(pause * 2, BUSY_MAX_S)
            continue
        break
    if r.status_code == 413:
        raise ValueError("too long for the speech recogniser")
    if r.status_code != 200:
        raise SttUnavailable(f"stt answered {r.status_code}")
    out: dict[str, Any] = r.json()
    return out


def _code(r: httpx.Response) -> str | None:
    try:
        body = r.json()
    except ValueError:
        return None
    return str(body.get("code")) if isinstance(body, dict) else None


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
