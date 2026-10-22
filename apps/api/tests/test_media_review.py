"""Review of prompt 6 (06.1 §2-§3), owner media: ffmpeg's inputs, the
duration caps, the attempts, the attach/processing race, the stt queue,
what is served inline, Range and file names, the variants' colour profile,
the append-only guard and what the holding's agents see."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest

from hq_api import media, workflows_client
from hq_api.domain import files as F
from hq_api.hub import Hub
from hq_api.worker import media as M

from .conftest import agent_headers, idem
from .test_files_media import (  # noqa: F401 - fixtures
    FakeStt,
    _ffmpeg,
    _on_worker,
    audio,
    media_acts,
    upload,
    video_30s,
)

pytestmark = pytest.mark.usefixtures("relay")

# An ID3 tag in front of an ffconcat script: plain ffprobe opens the concat
# demuxer, which reads other files (here a relative one).
FFCONCAT = (
    b"ID3\x04\x00\x00\x00\x00\x00\x14" + b"\x00" * 20
    + b"ffconcat version 1.0\nfile inner.wav\n" + b"#" * 3000 + b"\n"
)  # fmt: skip


# ----------------------------------------------------------------- ffmpeg --
async def test_an_id3_ffconcat_never_opens_the_concat_demuxer(
    client: httpx.AsyncClient, owner: dict[str, str], tmp_path: Path
) -> None:
    (tmp_path / "inner.wav").write_bytes(audio(tmp_path, "wav", 1))
    evil = tmp_path / "evil"
    evil.write_bytes(FFCONCAT)
    code, out, _ = await media.run_tool(
        "ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "json",
        str(evil), limit_s=30,
    )  # fmt: skip
    assert code == 0 and json.loads(out)["format"]["format_name"] == "concat"  # the hole
    with pytest.raises(ValueError):
        await media.probe(str(evil))  # only the allowed demuxers, only file:
    r = await upload(client, owner, FFCONCAT, "audio/mpeg", "song.mp3")
    assert r.status_code == 415, r.text


async def test_every_ffmpeg_call_is_fenced_and_the_fallback_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    async def slow(*argv: str, limit_s: float) -> tuple[int, bytes, bytes]:
        calls.append(argv)
        await asyncio.sleep(0.2)
        return 1, b"", b""  # no scene frames, no single frames

    monkeypatch.setattr(M, "run_tool", slow)
    monkeypatch.setattr(M, "FALLBACK_TOTAL_S", 1.5)
    src = tmp_path / "v.mp4"
    started = asyncio.get_running_loop().time()
    got = await M.key_frames(src, 600.0)  # 12 evenly spaced frames wanted
    assert got == [] and asyncio.get_running_loop().time() - started < 3
    assert 2 <= len(calls) < 13  # the scene pass, then as many as the time allows
    with pytest.raises(ValueError):
        await M.poster(src, 10.0)
    with M.temp_file(tmp_path, ".wav") as wav:
        assert not await M.sound_track(src, wav, "audio")
    for argv in calls:
        i = argv.index("-i")
        assert argv[i + 1] == f"file:{src}"
        assert argv[i - 4 : i] == ("-protocol_whitelist", "file", "-format_whitelist", media.FORMATS)
        assert argv.count("-threads") == 2 and argv[argv.index("-threads") + 1] == media.FF_THREADS
    assert calls[0][calls[0].index("-t") + 1] == str(10 * 60 + 1)  # the scene pass: video cap
    assert calls[-1][calls[-1].index("-t") + 1] == str(15 * 60 + 1)  # the sound: audio cap


async def test_a_cancelled_ffmpeg_is_killed() -> None:
    marker = "31.41592"
    task = asyncio.create_task(media.run_tool("sleep", marker, limit_s=60))
    await asyncio.sleep(0.3)
    assert _running(marker)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not _running(marker)


def _running(marker: str) -> bool:
    for proc in Path("/proc").iterdir():
        try:
            if marker.encode() in (proc / "cmdline").read_bytes():
                return True
        except OSError:
            continue
    return False


# --------------------------------------------------------- duration caps --
async def test_audio_without_a_duration_is_cut_and_refused(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    media_acts: Any,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acts, stt = media_acts
    real = media.probe

    async def no_duration(path: str) -> dict[str, Any]:
        return {**(await real(path)), "duration_s": None}  # a WebM written live

    monkeypatch.setattr(media, "probe", no_duration)
    monkeypatch.setattr(M, "cap_s", lambda kind: 4)  # the limit (3 s) plus one second
    ref = (await upload(client, owner, audio(tmp_path, "webm", 10), "audio/webm")).json()
    assert ref["status"] == "processing" and ref["duration_s"] is None  # passed the upload
    out = await acts.file_process(ref["id"])
    assert "longer than" in out["error"] and stt.calls == 0  # nothing reached the recogniser
    row = await su.fetchrow(
        "SELECT status, attempts, error FROM files.processing WHERE file_id = $1",
        uuid.UUID(ref["id"]),
    )
    assert (row["status"], row["attempts"]) == ("failed", 1)
    # /transcribe: the same refusal is a 413.

    async def on_worker(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        return await _on_worker(acts, file_id)

    monkeypatch.setattr(workflows_client, "transcribe", on_worker)
    r = await client.post(
        "/api/v1/transcribe",
        content=audio(tmp_path, "webm", 10),
        headers={**owner, **idem(), "Content-Type": "audio/webm"},
    )
    assert r.status_code == 413, r.text


async def test_attempts_count_from_the_start_and_end(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    media_acts: Any,  # noqa: F811
    tmp_path: Path,
) -> None:
    acts, _ = media_acts
    ref = (await upload(client, owner, audio(tmp_path, "ogg", 2), "audio/ogg")).json()
    fid = uuid.UUID(ref["id"])
    # A worker killed after it started (OOM): that attempt counts already.
    await acts._start(await acts._file(ref["id"]))
    assert await su.fetchval("SELECT attempts FROM files.processing WHERE file_id = $1", fid) == 1
    await su.execute("UPDATE files.processing SET attempts = 3 WHERE file_id = $1", fid)
    out = await acts.file_process(ref["id"])
    assert out["error"] == "attempts"
    row = await su.fetchrow("SELECT status, error FROM files.processing WHERE file_id = $1", fid)
    assert row["status"] == "failed" and "3 attempts" in row["error"]


# ------------------------------------------------------------ stt busy --
class BusyStt(FakeStt):
    """Answers 503 busy `busy` times, then like FakeStt."""

    def __init__(self, busy: int) -> None:
        super().__init__()
        self.busy = busy

    def transport(self) -> httpx.MockTransport:
        ok = super().transport()

        def handle(request: httpx.Request) -> httpx.Response:
            if self.busy > 0:
                self.busy -= 1
                self.calls += 1
                return httpx.Response(503, json={"code": "busy", "detail": "queue full"})
            return ok.handler(request)  # type: ignore[attr-defined]

        return httpx.MockTransport(handle)


async def test_a_busy_stt_is_waited_for_not_called_off(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    media_acts: Any,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acts, _ = media_acts
    monkeypatch.setattr(M, "BUSY_FIRST_S", 0.01)
    stt = BusyStt(busy=2)
    acts.stt_transport = stt.transport()

    async def on_worker(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
        return await _on_worker(acts, file_id)

    monkeypatch.setattr(workflows_client, "transcribe", on_worker)
    r = await client.post(
        "/api/v1/transcribe",
        content=audio(tmp_path, "wav", 2),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 200 and r.json()["text"] and stt.calls == 3, r.text
    # Busy for longer than the owner should wait: 429 rate_limited, not "off".
    monkeypatch.setattr("hq_api.worker.media_activities.BUSY_WAIT_TRANSCRIBE_S", 0.05)
    acts.stt_transport = BusyStt(busy=1000).transport()
    r = await client.post(
        "/api/v1/transcribe",
        content=audio(tmp_path, "wav", 2),
        headers={**owner, **idem(), "Content-Type": "audio/wav"},
    )
    assert r.status_code == 429 and r.json()["code"] == "rate_limited", r.text
    assert r.headers["retry-after"] == "30"
    # An upload in the background: not the last attempt -> retried (Temporal), the file waits.
    monkeypatch.setattr("hq_api.worker.media_activities.BUSY_WAIT_FILE_S", 0.05)
    ref = (await upload(client, owner, audio(tmp_path, "ogg", 2), "audio/ogg")).json()
    from temporalio.exceptions import ApplicationError

    with pytest.raises(ApplicationError) as err:
        await acts.file_process(ref["id"])
    assert err.value.type == "SttBusy" and not err.value.non_retryable
    meta = (await client.get(f"/api/v1/files/{ref['id']}/meta", headers=owner)).json()
    assert meta["status"] == "processing"


# --------------------------------------------------------- attach race --
async def test_variants_follow_the_file_into_its_company(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    hub: Hub,
    media_acts: Any,  # noqa: F811
    tmp_path: Path,
    new_company: Callable[..., Any],
) -> None:
    acts, _ = media_acts
    co = await new_company()
    ref = (await upload(client, owner, video_30s(tmp_path), "video/mp4", "clip.mp4")).json()
    fid = uuid.UUID(ref["id"])
    stale = await acts._file(ref["id"])  # the job read the file while it was the holding's
    holding = await hub.companies.holding()
    # 1. An attachment in progress (the original locked FOR UPDATE): the worker's
    #    variant waits for it, then lands in the file's new company.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await F.attach(tx, [fid], co["id"], holding.id)
        task = asyncio.create_task(acts._store_variant(stale, "poster", b"\xff\xd8poster"))
        await asyncio.sleep(0.5)
        assert not task.done()  # FOR SHARE waits for the attachment
    poster = await asyncio.wait_for(task, 10)
    assert await su.fetchval("SELECT company_id FROM files.files WHERE id = $1", poster) == co["id"]
    # 2. The rest of the job, with the row it read before: frames and file.ready
    #    go to the company the file belongs to now.
    acts._file = _returning(stale)  # type: ignore[method-assign]
    try:
        out = await acts.file_process(ref["id"])
    finally:
        del acts._file
    assert out.get("frames", 0) >= 1 and "error" not in out, out
    left = await su.fetchval(
        "SELECT count(*) FROM files.files WHERE parent_id = $1 AND company_id = $2",
        fid,
        holding.id,
    )
    assert left == 0
    subjects = [
        r["subject"]
        for r in await su.fetch(
            "SELECT subject FROM core.outbox WHERE subject LIKE '%.file.ready' AND payload->>'ref' = $1",
            ref["id"],
        )
    ]
    assert subjects == [f"hq.core.{co['code']}.file.ready"]
    # An agent of that company sees the frames with where they are.
    meta = await client.get(
        f"/internal/v1/files/{ref['id']}/meta", headers=await agent_headers(f"{co['code']}-CEO")
    )
    assert meta.status_code == 200, meta.text
    frames = meta.json()["frames"]
    assert frames and all(set(f) == {"id", "at_s"} for f in frames)
    assert [f["at_s"] for f in frames] == sorted(f["at_s"] for f in frames)


def _returning(row: dict[str, Any]) -> Any:
    async def f(file_id: str) -> dict[str, Any]:
        return dict(row)

    return f


# --------------------------------------------------- guard and visibility --
async def test_only_the_owners_uploads_move_and_holding_agents_wait(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    hub: Hub,
    new_company: Callable[..., Any],
    tmp_path: Path,
) -> None:
    from .test_files_media import _image

    co = (await new_company())["code"]
    adv = await agent_headers("HQ-ADV")
    # A holding agent's own output never moves to a company, by the api or by SQL.
    r = await client.post(
        "/internal/v1/files",
        params={"name": "report.png"},
        content=_image("PNG"),
        headers={**adv, "Content-Type": "image/png"},
    )
    assert r.status_code == 201, r.text
    out_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/threads/{co}-CEO/messages",
        headers={**owner, **idem()},
        json={"body": "", "attachments": [out_id]},
    )
    assert r.status_code == 422 and "own uploads" in r.text
    fx_id = await su.fetchval("SELECT id FROM core.companies WHERE code = $1", co)
    import asyncpg

    with pytest.raises(asyncpg.PostgresError) as err:
        await su.execute(
            "UPDATE files.files SET company_id = $1 WHERE id = $2", fx_id, uuid.UUID(out_id)
        )
    assert err.value.sqlstate == "HQA01"
    # The owner's upload: invisible to the holding's agents until it is attached.
    ref = (await upload(client, owner, _image("PNG"), "image/png", "plan.png")).json()
    r = await client.get(f"/internal/v1/files/{ref['id']}/meta", headers=adv)
    missing = await client.get(f"/internal/v1/files/{uuid.uuid4()}/meta", headers=adv)
    assert r.status_code == missing.status_code == 403
    r = await client.post(
        "/api/v1/threads/A/messages",
        headers={**owner, **idem()},
        json={"body": "این طرح را ببین", "attachments": [ref["id"]]},
    )
    assert r.status_code == 201, r.text
    r = await client.get(f"/internal/v1/files/{ref['id']}/meta", headers=adv)
    assert r.status_code == 200 and r.json()["kind"] == "image"


# -------------------------------------------------------------- serving --
async def test_svg_and_other_types_are_never_inline(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = (await new_company())["code"]
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    r = await client.post(
        "/internal/v1/files",
        params={"name": "chart.svg"},
        content=svg,
        headers={**await agent_headers(f"{co}-CEO"), "Content-Type": "image/svg+xml"},
    )
    assert r.status_code == 201, r.text
    got = await client.get(f"/api/v1/files/{r.json()['id']}", headers=owner)
    assert got.status_code == 200
    assert got.headers["content-disposition"].startswith("attachment;")
    assert got.headers["content-security-policy"] == "sandbox"
    assert got.headers["x-content-type-options"] == "nosniff"


async def test_range_names_and_bad_ranges(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    from .test_files_media import _image

    name = "نقشه‌ی راه ۱۴۰۵.png"
    ref = (
        await client.post(
            "/api/v1/files",
            content=_image("PNG"),
            headers={**owner, **idem(), "Content-Type": "image/png", "X-File-Name": quote(name)},
        )
    ).json()
    url = f"/api/v1/files/{ref['id']}"
    whole = await client.get(url, headers=owner)
    cd = whole.headers["content-disposition"]
    assert cd.startswith("inline;") and f"filename*=UTF-8''{quote(name, safe='')}" in cd
    assert 'filename="' in cd and all(ord(c) < 128 for c in cd)
    assert whole.headers["content-security-policy"] == "sandbox"
    size = len(whole.content)
    # Ignored, the whole file (RFC 9110 §14.2): multi-range, another unit, malformed.
    for header in ("bytes=0-1,4-5", "items=0-10", "bytes=abc", "bytes=-", "bytes=5"):
        r = await client.get(url, headers={**owner, "Range": header})
        assert r.status_code == 200 and len(r.content) == size, header
    # 4300+ digits: int() would raise (a 500 before); far beyond any file instead.
    r = await client.get(url, headers={**owner, "Range": "bytes=" + "9" * 4400 + "-"})
    assert r.status_code == 416 and r.headers["content-range"] == f"bytes */{size}"
    r = await client.get(url, headers={**owner, "Range": "bytes=0-" + "9" * 5000})
    assert r.status_code == 206 and len(r.content) == size
    r = await client.get(url, headers={**owner, "Range": "bytes=-" + "9" * 5000})
    assert r.status_code == 206 and r.content == whole.content


# ----------------------------------------------------------------- ICC --
def _p3_like_jpeg() -> tuple[bytes, bytes]:
    from PIL import Image, ImageCms

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    icc = icc[:48] + b"HQP3" + icc[52:]  # a distinct profile (its header's device field)
    out = io.BytesIO()
    Image.new("RGB", (2000, 1500), (250, 40, 20)).save(out, format="JPEG", icc_profile=icc)
    return out.getvalue(), icc


async def test_the_colour_profile_stays(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    from PIL import Image

    data, icc = _p3_like_jpeg()
    ref = (await upload(client, owner, data, "image/jpeg", "p3.jpg")).json()
    original = (await client.get(f"/api/v1/files/{ref['id']}", headers=owner)).content
    assert Image.open(io.BytesIO(original)).info.get("icc_profile") == icc
    thumb = (await client.get(f"/api/v1/files/{ref['id']}?variant=thumb", headers=owner)).content
    assert Image.open(io.BytesIO(thumb)).info.get("icc_profile") == icc
    assert media.icc_for(icc, "L") == {}  # an RGB profile never on grey pixels
    assert media.icc_for(b"x" * 10, "RGB") == {}
