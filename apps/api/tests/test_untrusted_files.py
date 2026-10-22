"""Prompt 07.1 §1.2 and 06.1 §1.4: a hostile PDF or a huge photo through
either upload path (the owner's POST /api/v1/files, the agents'
/internal/v1/files that web.browse downloads use) answers 201 within 35 s,
the parse runs in a child process that its limits stop, outside any
transaction, and the api's own memory hardly moves (the tests run the app in
this very process)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import image_meta, media
from hq_common import untrusted

from .conftest import agent_headers, idem
from .test_tools_mcp import _finish_runs, pdf_with

MB = 1024 * 1024


def pdf_bomb() -> bytes:
    """~41 KB holding 20 MB of compressed drawing operators and no text:
    pypdf 6.19 alone spends 28 s and 1.1 GB on it (the reviewer's file)."""
    stream = zlib.compress(b"0 0 m 1 1 l S\n" * (20 * MB // 14), 9)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


PHOTO = """
import sys
from PIL import Image
w, h = 7745, 5164  # 39.99 MP
noise = Image.effect_noise((w // 8, h // 8), 40).resize((w, h))
grad = Image.linear_gradient("L").resize((w, h))
img = Image.merge("RGB", (noise, grad, grad.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
exif = Image.Exif()
exif[0x010F] = "PhoneMaker"
exif[0x0112] = 6  # shot in portrait
exif[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0), 3: "E", 4: (51.0, 24.0, 0.0)}
img.save(sys.argv[1], format="JPEG", quality=90, exif=exif)
"""


@pytest.fixture(scope="module")
def photo_40mp(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """A 40 MP JPEG with GPS, made in another process (not in the api's)."""
    path = tmp_path_factory.mktemp("photo") / "p40.jpg"
    subprocess.run([sys.executable, "-c", PHOTO, str(path)], check=True, timeout=120)
    return path.read_bytes()


def _status(key: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) * 1024
    return 0


class Peak:
    """The resident memory of this process (the api's) while a block runs:
    sampled every 5 ms, and its high-water mark reset first where the kernel
    lets a process do that."""

    def __enter__(self) -> Peak:
        try:
            Path("/proc/self/clear_refs").write_text("5")
            self.hwm = True
        except OSError:
            self.hwm = False
        self.base = _status("VmRSS")
        self.top = self.base
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def _sample(self) -> None:
        while not self._stop.wait(0.005):
            self.top = max(self.top, _status("VmRSS"))

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()
        if self.hwm:
            self.top = max(self.top, _status("VmHWM"))

    @property
    def growth_mb(self) -> float:
        return (self.top - self.base) / MB


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


async def _owner_upload(
    client: httpx.AsyncClient, owner: dict[str, str], data: bytes, mime: str, name: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/files",
        content=data,
        headers={**owner, **idem(), "Content-Type": mime, "X-File-Name": name},
    )


async def _agent_upload(
    client: httpx.AsyncClient, me: str, data: bytes, mime: str, name: str
) -> httpx.Response:
    return await client.post(
        "/internal/v1/files",
        params={"name": name},
        headers={**await agent_headers(me), "Content-Type": mime},
        content=data,
    )


async def test_a_pdf_bomb_through_both_upload_paths(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    bomb = pdf_bomb()
    assert len(bomb) < 50_000
    for path in ("owner", "agent"):
        before = len(untrusted._spawned)
        started = time.monotonic()
        with Peak() as peak:
            if path == "owner":
                r = await _owner_upload(client, owner, bomb, "application/pdf", "bomb.pdf")
            else:
                r = await _agent_upload(client, me, bomb, "application/pdf", "bomb.pdf")
        took = time.monotonic() - started
        assert r.status_code == 201, (path, r.text)
        assert took < 35, (path, took)
        assert peak.growth_mb < 50, (path, peak.growth_mb)
        assert len(untrusted._spawned) == before + 1 and gone(untrusted._spawned[-1])
        ref = r.json()
        assert ref["status"] == "failed", (path, ref)
        row = await su.fetchrow(
            "SELECT status, text, error, attempts FROM files.processing WHERE file_id = $1",
            uuid.UUID(ref["id"]),
        )
        assert row["status"] == "failed" and row["text"] is None and row["attempts"] == 1
        assert row["error"].startswith("text extraction stopped: "), row["error"]
        if path == "agent":  # what files.read gives the agent: the file, no text
            meta = (
                await client.get(
                    f"/internal/v1/files/{ref['id']}/meta", headers=await agent_headers(me)
                )
            ).json()
            assert meta["text"] is None and meta["status"] == "failed"
    await _finish_runs(su, [me])


async def test_a_40_mp_photo_through_both_upload_paths(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
    photo_40mp: bytes,
) -> None:
    from PIL import Image

    co = (await new_company())["code"]
    me = f"{co}-TECH-MGR"
    for path in ("owner", "agent"):
        started = time.monotonic()
        with Peak() as peak:
            if path == "owner":
                r = await _owner_upload(client, owner, photo_40mp, "image/jpeg", "p40.jpg")
            else:
                r = await _agent_upload(client, me, photo_40mp, "image/jpeg", "p40.jpg")
        took = time.monotonic() - started
        assert r.status_code == 201, (path, r.text)
        assert took < 35 and peak.growth_mb < 50, (path, took, peak.growth_mb)
        assert r.json()["status"] == "ready"
    ref = (await _owner_upload(client, owner, photo_40mp, "image/jpeg", "again.jpg")).json()
    assert (ref["width"], ref["height"]) == (5164, 7745)  # upright: shot in portrait
    original = (await client.get(f"/api/v1/files/{ref['id']}", headers=owner)).content
    assert media.has_metadata(photo_40mp) and not media.has_metadata(original)
    img = Image.open(io.BytesIO(original))
    assert img.size == (7745, 5164) and dict(img.getexif()) == {image_meta.ORIENTATION: 6}
    assert abs(len(original) - len(photo_40mp)) < 4096  # the photo's own bytes, not re-encoded
    thumb = await client.get(f"/api/v1/files/{ref['id']}?variant=thumb", headers=owner)
    small = Image.open(io.BytesIO(thumb.content))
    assert small.height == 512 and small.width < small.height  # turned upright for real
    await _finish_runs(su, [me])


async def test_pixel_bombs_are_415_not_500(
    client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    def png(size: tuple[int, int]) -> bytes:
        out = io.BytesIO()
        Image.new("1", size).save(out, format="PNG")
        return out.getvalue()

    bomb = await _owner_upload(client, owner, png((9500, 9000)), "image/png", "bomb.png")
    assert bomb.status_code == 415, bomb.text  # > 80 MP: Pillow's DecompressionBombError
    big = await _owner_upload(client, owner, png((8000, 6000)), "image/png", "big.png")
    assert big.status_code == 415 and "too many pixels" in big.text
    # A photo the child's limits stop is refused too, never a 500.
    monkeypatch.setattr(media, "IMAGE_LIMITS", untrusted.Limits(memory_mb=40, write_mb=64))
    out = io.BytesIO()
    Image.new("RGB", (640, 480), (1, 2, 3)).save(out, format="JPEG")
    r = await _owner_upload(client, owner, out.getvalue(), "image/jpeg", "small.jpg")
    assert r.status_code == 415 and "too large to process" in r.text


async def test_every_format_is_cleaned_without_decoding_the_original(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[0x0112] = 8
    exif[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0)}
    xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description/></rdf:RDF></x:xmpmeta>'
    for mime, fmt, extra in (
        ("image/png", "PNG", {}),
        ("image/webp", "WEBP", {"xmp": xmp}),
        ("image/heic", "HEIF", {"xmp": xmp}),
    ):
        out = io.BytesIO()
        Image.new("RGB", (64, 48), (10, 120, 200)).save(out, format=fmt, exif=exif, **extra)
        data = out.getvalue()
        assert media.has_metadata(data), mime
        ref = (await _owner_upload(client, owner, data, mime, f"x.{fmt.lower()}")).json()
        assert ref["status"] == "ready", (mime, ref)
        stored = (await client.get(f"/api/v1/files/{ref['id']}", headers=owner)).content
        assert not media.has_metadata(stored), mime
        if fmt != "HEIF":  # HEIF turns by its own properties, not EXIF
            assert (ref["width"], ref["height"]) == (48, 64), mime


async def test_a_pdf_the_api_never_finished_is_finished_by_the_worker(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, wk: dict[str, Any]
) -> None:
    ref = (
        await _owner_upload(
            client, owner, pdf_with("Resumed by the worker"), "application/pdf", "r.pdf"
        )
    ).json()
    fid = uuid.UUID(ref["id"])
    await su.execute(
        "UPDATE files.processing SET status = 'processing', text = NULL WHERE file_id = $1", fid
    )
    out = await wk["acts"].media.file_process(ref["id"])
    assert out == {"file": ref["id"], "text": "ready"}
    row = await su.fetchrow(
        "SELECT status, text, attempts FROM files.processing WHERE file_id = $1", fid
    )
    assert (
        row["status"] == "ready" and "Resumed by the worker" in row["text"] and row["attempts"] == 2
    )
