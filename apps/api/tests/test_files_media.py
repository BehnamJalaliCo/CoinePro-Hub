"""Prompt 6 §2-§3 (contract §17.1-17.2): owner files, their processing, the
agents' view of them, and voice to Persian text."""

from __future__ import annotations

import io
import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import media, workflows_client
from hq_api.hub import Hub
from hq_api.worker import media as M

from .conftest import agent_headers, idem
from .test_agents import run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")


# ------------------------------------------------------------- the files --


@pytest.fixture(autouse=True)
def _speech_on(hub: Hub, monkeypatch: pytest.MonkeyPatch) -> None:
    """⟨1.7.3⟩ /transcribe answers 503 at once while speech is off: these tests
    exercise the recogniser's path (the worker is faked), so speech is on."""
    if not hub.settings.stt_url:
        monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url="http://stt.test"))


def _jpeg_with_gps() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (2400, 1600), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0), 3: "E", 4: (51.0, 24.0, 0.0)}  # GPS
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _image(fmt: str) -> bytes:
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    out = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(out, format=fmt)
    return out.getvalue()


def _ffmpeg(tmp: Path, name: str, *args: str) -> bytes:
    path = tmp / name
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, str(path)],  # noqa: S607
        check=True,
        timeout=120,
    )
    return path.read_bytes()


def video_30s(tmp: Path) -> bytes:
    """30 s, three scenes (red, green, blue) and a tone."""
    return _ffmpeg(
        tmp,
        "v.mp4",
        "-f", "lavfi", "-i", "color=red:s=320x240:d=10",
        "-f", "lavfi", "-i", "color=green:s=320x240:d=10",
        "-f", "lavfi", "-i", "color=blue:s=320x240:d=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest",
    )  # fmt: skip


def audio(tmp: Path, fmt: str, seconds: float = 2, silent: bool = False) -> bytes:
    src = "anullsrc=r=16000:cl=mono" if silent else "sine=frequency=300"
    return _ffmpeg(tmp, f"a.{fmt}", "-f", "lavfi", "-i", src, "-t", str(seconds), "-ac", "1")


async def upload(
    client: httpx.AsyncClient, owner: dict[str, str], data: bytes, mime: str, name: str = "x"
) -> httpx.Response:
    return await client.post(
        "/api/v1/files",
        content=data,
        headers={**owner, **idem(), "Content-Type": mime, "X-File-Name": name},
    )


async def test_every_allowed_kind_and_type_checked_by_content(
    client: httpx.AsyncClient, owner: dict[str, str], tmp_path: Path
) -> None:
    cases = {
        "image/jpeg": _image("JPEG"),
        "image/png": _image("PNG"),
        "image/webp": _image("WEBP"),
        "image/heic": _image("HEIF"),
        "video/mp4": video_30s(tmp_path),
        "video/webm": _ffmpeg(tmp_path, "w.webm", "-f", "lavfi", "-i", "color=red:s=64x48:d=1", "-c:v", "libvpx-vp9"),
        "video/quicktime": _ffmpeg(tmp_path, "q.mov", "-f", "lavfi", "-i", "color=red:s=64x48:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p"),
        "audio/wav": audio(tmp_path, "wav"),
        "audio/ogg": _ffmpeg(tmp_path, "a.ogg", "-f", "lavfi", "-i", "sine", "-t", "1", "-c:a", "libopus"),
        "audio/mpeg": _ffmpeg(tmp_path, "a.mp3", "-f", "lavfi", "-i", "sine", "-t", "1"),
        "audio/mp4": _ffmpeg(tmp_path, "a.m4a", "-f", "lavfi", "-i", "sine", "-t", "1", "-c:a", "aac"),
        "application/pdf": b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n",
    }  # fmt: skip
    kinds = {}
    for mime, data in cases.items():
        r = await upload(client, owner, data, mime, f"%D8%B9%DA%A9%D8%B3-{mime.split('/')[1]}")
        assert r.status_code == 201, (mime, r.text)
        ref = r.json()
        kinds[mime] = (ref["kind"], ref["status"])
        assert ref["mime"] == mime and ref["size"] > 0
    assert kinds["image/jpeg"] == ("image", "ready") and kinds["application/pdf"] == (
        "document",
        "ready",
    )
    assert kinds["video/mp4"] == ("video", "processing") and kinds["audio/wav"] == (
        "audio",
        "processing",
    )
    jpeg = (await upload(client, owner, cases["image/jpeg"], "image/jpeg", "%D8%B9.jpg")).json()
    assert jpeg["name"] == "ع.jpg" and jpeg["variants"]["thumb"]
    # The header does not decide: a PNG labelled JPEG, a text called an image, an
    # unlisted type.
    for data, mime in (
        (cases["image/png"], "image/jpeg"),
        (b"not an image at all" * 10, "image/png"),
        (cases["image/png"], "image/gif"),
    ):
        r = await upload(client, owner, data, mime)
        assert r.status_code == 415, (mime, r.text)


async def test_size_is_held_while_streaming(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    sent = 0

    async def body() -> AsyncIterator[bytes]:
        nonlocal sent
        head = _image("JPEG")
        sent += len(head)
        yield head
        block = b"\0" * (1024 * 1024)
        for _ in range(64):  # 64 MB of an "image": far over its 20 MB
            sent += len(block)
            yield block

    r = await client.post(
        "/api/v1/files",
        content=body(),
        headers={**owner, **idem(), "Content-Type": "image/jpeg"},
    )
    assert r.status_code == 413, r.text
    assert sent <= 22 * 1024 * 1024  # refused before the body ended


async def test_exif_and_gps_are_gone_and_range_works(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    data = _jpeg_with_gps()
    assert media.has_metadata(data)
    ref = (await upload(client, owner, data, "image/jpeg", "photo.jpg")).json()
    r = await client.get(f"/api/v1/files/{ref['id']}", headers=owner)
    assert r.status_code == 200 and not media.has_metadata(r.content)
    assert r.headers["content-disposition"].startswith("inline")
    assert (ref["width"], ref["height"]) == (2400, 1600)
    thumb = await client.get(f"/api/v1/files/{ref['id']}?variant=thumb", headers=owner)
    assert thumb.headers["content-type"] == "image/webp"
    from PIL import Image

    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 512
    part = await client.get(f"/api/v1/files/{ref['id']}", headers={**owner, "Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"].startswith("bytes 0-99/")
    tail = await client.get(f"/api/v1/files/{ref['id']}", headers={**owner, "Range": "bytes=-10"})
    assert tail.status_code == 206 and tail.content == r.content[-10:]
    bad = await client.get(
        f"/api/v1/files/{ref['id']}", headers={**owner, "Range": "bytes=999999999-"}
    )
    assert bad.status_code == 416
    meta = await client.get(f"/api/v1/files/{ref['id']}/meta", headers=owner)
    assert meta.json()["status"] == "ready"


# --------------------------------------------------------- the processing --
class FakeStt:
    """The stt service (prompt 6 §3) answering with a fixed Persian text."""

    def __init__(self, text: str = "سلام مدير كل امروز جلسه داريم") -> None:
        self.text = text
        self.calls = 0

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.calls += 1
            assert request.url.path == "/v1/transcribe" and request.content[:4] == b"RIFF"
            return httpx.Response(
                200,
                json={
                    "text_raw": self.text,
                    "text": self.text,
                    "language": "fa",
                    "duration_s": 30.0,
                    "confidence": 0.91,
                    "segments": [{"start_s": 0.0, "end_s": 2.5, "text": self.text}],
                    "engine": {
                        "name": "faster-whisper",
                        "model": "large-v3-turbo",
                        "version": "test",
                    },
                },
            )

        return httpx.MockTransport(handle)


@pytest.fixture
def media_acts(wk: dict[str, Any]) -> Any:
    """The worker's media activities with a fake stt service and the stt URL set."""
    acts = wk["acts"].media
    hub = acts.hub
    real = hub.settings
    stt = FakeStt()
    hub.settings = replace(real, stt_url="http://stt.test", stt_punctuation=False)
    acts.stt_transport = stt.transport()
    yield acts, stt
    hub.settings = real
    acts.stt_transport = None


async def test_a_30s_video_gets_a_poster_frames_and_its_transcript(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, media_acts: Any, tmp_path: Path
) -> None:
    acts, stt = media_acts
    ref = (await upload(client, owner, video_30s(tmp_path), "video/mp4", "clip.mp4")).json()
    assert ref["status"] == "processing" and 29 <= ref["duration_s"] <= 31
    out = await acts.file_process(ref["id"])
    # ⟨1.9⟩ stt gets pieces of at most 30 s: a track of a little over 30 s is two
    assert out["frames"] >= 3 and 1 <= stt.calls <= 2, out
    meta = (await client.get(f"/api/v1/files/{ref['id']}/meta", headers=owner)).json()
    assert meta["status"] == "ready" and meta["variants"]["poster"]
    assert meta["transcript"] and "ی" in meta["transcript"] and "ي" not in meta["transcript"]
    frames = await su.fetch(
        "SELECT frame_at_s, width FROM files.files WHERE parent_id = $1 AND variant = 'frame' ORDER BY frame_at_s",
        uuid.UUID(ref["id"]),
    )
    assert 3 <= len(frames) <= 12
    poster = await client.get(f"/api/v1/files/{ref['id']}?variant=poster", headers=owner)
    assert poster.status_code == 200 and poster.headers["content-type"] == "image/jpeg"
    ready = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.file.ready' AND payload->>'ref' = $1",
        ref["id"],
    )
    assert ready == 1


async def test_files_stay_with_their_company(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    fx = (await new_company())["code"]
    ty = (await new_company())["code"]
    ref = (await upload(client, owner, _image("PNG"), "image/png", "plan.png")).json()
    r = await client.post(
        f"/api/v1/threads/{fx}-TECH-MGR/messages",
        headers={**owner, **idem()},
        json={"body": "", "attachments": [ref["id"]]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["message"]["attachments"][0]["id"] == ref["id"]
    # Now FX's: an FX agent sees it, a TY agent does not; owner cannot re-attach it in TY.
    fx_meta = await client.get(
        f"/internal/v1/files/{ref['id']}/meta", headers=await agent_headers(f"{fx}-TECH-MGR")
    )
    assert fx_meta.status_code == 200 and fx_meta.json()["kind"] == "image"
    ty_meta = await client.get(
        f"/internal/v1/files/{ref['id']}/meta", headers=await agent_headers(f"{ty}-TECH-MGR")
    )
    missing = await client.get(
        f"/internal/v1/files/{uuid.uuid4()}/meta", headers=await agent_headers(f"{ty}-TECH-MGR")
    )
    assert ty_meta.status_code == missing.status_code == 403
    r = await client.post(
        f"/api/v1/threads/{ty}-TECH-MGR/messages",
        headers={**owner, **idem()},
        json={"body": "این هم", "attachments": [ref["id"]]},
    )
    assert r.status_code == 422
    # An agent cannot attach another company's file either.
    r = await client.post(
        f"/internal/v1/threads/{ty}-TECH-MGR/messages",
        headers={**await agent_headers(f"{ty}-TECH-MGR"), **idem()},
        json={"body": "x", "attachments": [ref["id"]]},
    )
    assert r.status_code == 422
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'running' AND r.reason = 'test'""",
        [f"{fx}-TECH-MGR", f"{ty}-TECH-MGR"],
    )


async def test_a_photo_to_a_manager_reaches_its_run_as_an_image(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    ref = (
        await upload(client, owner, _jpeg_with_gps(), "image/jpeg", "secret-plan-name.jpg")
    ).json()
    r = await client.post(
        f"/api/v1/threads/{co}-TECH-MGR/messages",
        headers={**owner, **idem()},
        json={"body": "این طرح را ببین", "attachments": [ref["id"]]},
    )
    assert r.status_code == 201, r.text
    row = (await runs_of(su, f"{co}-TECH-MGR"))[-1]
    since = len(agents.fake.calls)
    agents.fake.enqueue(f"{co}-TECH-MGR", step("دیدم", ("message.owner", {"body_md": "دیدم"})))
    assert (await run(agents, row["id"]))["state"] == "done"
    first = next(c for c in agents.fake.calls[since:] if c.actor_ref == f"{co}-TECH-MGR")
    parts = first.messages[0].parts
    images = [p for p in parts if type(p).__name__ == "ImagePart"]
    assert len(images) == 1 and images[0].media_type == "image/jpeg"
    import base64

    from PIL import Image

    seen = Image.open(io.BytesIO(base64.b64decode(images[0].data)))
    assert max(seen.size) <= 1568 and not seen.getexif()  # downscaled, no EXIF
    text = first.messages[0].content
    assert "image 2400x1600" in text and "secret-plan-name" not in text  # no file names


# ---------------------------------------------------------------- voice --
async def _on_worker(acts: Any, file_id: str) -> dict[str, Any]:
    """What workflows_client.transcribe returns, without a Temporal round trip."""
    from temporalio.client import WorkflowFailureError
    from temporalio.exceptions import ApplicationError

    try:
        return dict(await acts.transcribe_file(file_id))
    except ApplicationError as exc:
        raise WorkflowFailureError(cause=exc) from exc


async def test_transcribe_with_the_punctuation_guard(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    agents: Any,
    media_acts: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acts, _stt = media_acts

    async def on_worker(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        return await _on_worker(acts, file_id)

    monkeypatch.setattr(workflows_client, "transcribe", on_worker)
    hub = acts.hub
    hub.settings = replace(hub.settings, stt_punctuation=True)
    real_router, acts.router = acts.router, agents.router
    holding = (await hub.companies.holding()).code
    # The model adds punctuation only: accepted.
    agents.fake.enqueue(f"{holding}-SYS", "سلام مدیر کل، امروز جلسه داریم.")
    r = await client.post(
        "/api/v1/transcribe?purpose=message",
        content=audio(tmp_path, "wav", 3),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert "،" in out["text"] and out["text"].startswith("سلام مدیر کل") and out["language"] == "fa"
    assert out["engine"]["name"] == "faster-whisper" and 0 <= out["confidence"] <= 1
    p = await su.fetchrow(
        "SELECT * FROM files.processing WHERE file_id = $1", uuid.UUID(out["file_id"])
    )
    assert (
        p["punctuation"] == "accepted"
        and p["transcript_normalised"] == "سلام مدیر کل امروز جلسه داریم"
    )
    # The model changed words: dropped, the normalised text kept.
    agents.fake.enqueue(f"{holding}-SYS", "درود بر مدیر محترم، فردا نشست داریم.")
    r = await client.post(
        "/api/v1/transcribe?purpose=note",
        content=audio(tmp_path, "wav", 3),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.json()["text"] == "سلام مدیر کل امروز جلسه داریم"
    p = await su.fetchrow(
        "SELECT punctuation FROM files.processing WHERE file_id = $1",
        uuid.UUID(r.json()["file_id"]),
    )
    assert p["punctuation"] == "rejected"
    # A message with that audio is a voice transcript.
    msg = await client.post(
        "/api/v1/threads/A/messages",
        headers={**owner, **idem()},
        json={"body": out["text"], "attachments": [out["file_id"]]},
    )
    assert msg.status_code == 201 and msg.json()["message"]["kind"] == "voice_transcript"
    acts.router = real_router
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = 'HQ-ADV' AND r.state = 'queued'"""
    )


async def test_transcribe_silence_too_long_and_off(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    media_acts: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acts, stt = media_acts
    assert stt.calls == 0

    async def on_worker(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        return await _on_worker(acts, file_id)

    monkeypatch.setattr(workflows_client, "transcribe", on_worker)
    stt.text = ""
    r = await client.post(
        "/api/v1/transcribe",
        content=audio(tmp_path, "wav", 2, silent=True),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 200 and r.json()["text"] == ""
    long = _ffmpeg(
        tmp_path,
        "long.ogg",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=8000:cl=mono",
        "-t",
        "960",
        "-c:a",
        "libopus",
        "-b:a",
        "6k",
    )
    r = await client.post(
        "/api/v1/transcribe", content=long, headers={**owner, **idem(), "Content-Type": "audio/ogg"}
    )
    assert r.status_code == 413, r.text
    r = await client.post(
        "/api/v1/transcribe",
        content=_image("PNG"),
        headers={**owner, **idem(), "Content-Type": "image/png"},
    )
    assert r.status_code == 415
    hub = acts.hub
    hub.settings = replace(hub.settings, stt_url="")  # the stt profile is off
    r = await client.post(
        "/api/v1/transcribe",
        content=audio(tmp_path, "wav", 2),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 503 and r.json()["code"] == "channel_not_configured"


def test_the_punctuation_guard_counts_words_not_marks() -> None:
    from hq_common import persian

    ok, ratio = M.accept_punctuation(
        "سلام مدیر کل امروز جلسه داریم", "سلام مدیر کل، امروز جلسه داریم."
    )
    assert ok and ratio == 0
    ok, ratio = M.accept_punctuation(
        "سلام مدیر کل امروز جلسه داریم", "سلام مدیر عزیز امروز جلسه داریم"
    )
    assert not ok and ratio > 0.08
    assert M.accept_punctuation("", "") == (True, 0)  # an empty transcript is not an error
    assert persian.words("می‌روم، خانه!") == persian.words("میروم خانه")
