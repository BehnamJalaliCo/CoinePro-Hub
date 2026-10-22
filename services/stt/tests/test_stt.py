"""stt (prompt 06 §3): the HTTP API with the fake engine, the Whisper engine's
logic with a stand-in model, the pinned-model fetch and check, the idle
unload, and the evaluation tool. No real model is ever downloaded or loaded."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import sys
import types
import wave
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_common import persian
from hq_stt import engine as E
from hq_stt import eval as V
from hq_stt import fetch as F
from hq_stt import lock as L
from hq_stt import main as M
from hq_stt.config import Settings

SAMPLES = Path(__file__).resolve().parent / "samples"


def wav(seconds: float, *, rate: int = 16_000, tone: bool = True, width: int = 2) -> bytes:
    """A mono WAV: a 440 Hz tone, or silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        n = int(seconds * rate)
        if width == 1:
            frames = bytes(
                (128 + int(100 * math.sin(2 * math.pi * 440 * i / rate))) if tone else 128
                for i in range(n)
            )
        else:
            frames = b"".join(
                int(12000 * math.sin(2 * math.pi * 440 * i / rate) if tone else 0).to_bytes(
                    2, "little", signed=True
                )
                for i in range(n)
            )
        w.writeframes(frames)
    return buf.getvalue()


def fake_settings(**kw: Any) -> Settings:
    return replace(Settings(), engine="fake", **kw)


async def client(state: M.State) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=M.build_app(state)), base_url="http://stt"
    )


AUDIO = {"Content-Type": "audio/wav"}


# -------------------------------------------------------------------- HTTP --
async def test_transcribe_over_http_with_the_fake_engine() -> None:
    s = fake_settings()
    state = M.State(s, E.build(s))
    async with await client(state) as c:
        assert (await c.get("/health")).json() == {
            "ok": True,
            "engine": "fake",
            "model": "fake",
            "loaded": False,
        }
        r = await c.post("/v1/transcribe", content=wav(1.5), headers=AUDIO)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["text"] == persian.normalise(body["text_raw"]) and body["text"]
        assert body["language"] == "fa" and body["duration_s"] == 1.5
        assert body["engine"] == {"name": "fake", "model": "fake", "version": "0"}
        assert body["segments"][0]["start_s"] == 0.0 and 0 < body["confidence"] <= 1
        assert set(body["timing"]) == {"load_s", "transcribe_s"}
        assert (await c.get("/health")).json()["loaded"] is True
        metrics = (await c.get("/metrics")).text
        assert 'stt_requests_total{outcome="ok"} 1.0' in metrics


async def test_silence_is_empty_text_without_an_error() -> None:
    s = fake_settings()
    async with await client(M.State(s, E.build(s))) as c:
        for audio in (wav(2, tone=False), wav(1, tone=False, width=1, rate=8000)):
            r = await c.post("/v1/transcribe", content=audio, headers=AUDIO)
            assert r.status_code == 200 and r.json()["text"] == "" and r.json()["segments"] == []


async def test_too_large_is_refused_while_reading() -> None:
    s = fake_settings(max_bytes=4_000)
    async with await client(M.State(s, E.build(s))) as c:
        r = await c.post("/v1/transcribe", content=wav(1), headers=AUDIO)
        assert (r.status_code, r.json()["code"]) == (413, "too_large")
        read: list[int] = []

        async def chunks() -> AsyncIterator[bytes]:  # no Content-Length: counted as it streams
            for _ in range(100):
                read.append(1)
                yield b"\0" * 1000

        r = await c.post("/v1/transcribe", content=chunks(), headers=AUDIO)
        assert (r.status_code, r.json()["code"]) == (413, "too_large")


def test_the_default_size_fits_the_longest_allowed_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """06.1 §2: 25 MB refused legal 14-15 minute audio. The worker's WAV of
    15 min plus the second it is cut at is 28.8 MB; the default is derived
    from the duration limit and never under 29 MiB."""
    monkeypatch.delenv("STT_MAX_BYTES", raising=False)
    monkeypatch.delenv("STT_MAX_DURATION_S", raising=False)
    longest = (15 * 60 + 1) * 16_000 * 2 + 44
    assert Settings().max_bytes >= max(longest, 29 * 1024 * 1024)
    monkeypatch.setenv("STT_MAX_DURATION_S", str(30 * 60))
    assert Settings().max_bytes >= (30 * 60 + 1) * 32_000 + 44
    monkeypatch.setenv("STT_MAX_BYTES", "1234")
    assert Settings().max_bytes == 1234


async def test_too_long_wrong_type_undecodable_and_busy() -> None:
    s = fake_settings(max_duration_s=2)
    state = M.State(s, E.build(s))
    async with await client(state) as c:
        r = await c.post("/v1/transcribe", content=wav(3, rate=8000, width=1), headers=AUDIO)
        assert (r.status_code, r.json()["code"]) == (413, "too_long")
        r = await c.post("/v1/transcribe", content=b"x", headers={"Content-Type": "text/plain"})
        assert (r.status_code, r.json()["code"]) == (415, "unsupported_media_type")
        r = await c.post("/v1/transcribe", content=b"not audio", headers=AUDIO)
        assert (r.status_code, r.json()["code"]) == (422, "undecodable")
        state.waiting = s.max_waiting  # the queue is full
        r = await c.post("/v1/transcribe", content=wav(1), headers=AUDIO)
        assert (r.status_code, r.json()["code"]) == (503, "busy")


async def test_one_at_a_time() -> None:
    s = fake_settings()
    eng = E.build(s)
    state = M.State(s, eng)
    running = 0
    most = 0
    real = eng.transcribe

    def slow(data: bytes) -> E.Transcript:
        nonlocal running, most
        running += 1
        most = max(most, running)
        import time

        time.sleep(0.05)
        running -= 1
        return real(data)

    eng.transcribe = slow  # type: ignore[method-assign]
    async with await client(state) as c:
        rs = await asyncio.gather(
            *(c.post("/v1/transcribe", content=wav(0.2), headers=AUDIO) for _ in range(3))
        )
    assert [r.status_code for r in rs] == [200, 200, 200] and most == 1 and state.waiting == 0


async def test_an_idle_model_is_freed() -> None:
    s = fake_settings(idle_unload_s=0)
    state = M.State(s, E.build(s))
    app = M.build_app(state)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://stt") as c,
    ):
        assert (await c.post("/v1/transcribe", content=wav(0.2), headers=AUDIO)).status_code == 200
        for _ in range(100):
            if not state.engine.loaded:
                break
            await asyncio.sleep(0.02)
    assert state.engine.loaded is False


# ---------------------------------------------------------- whisper engine --
class _Seg:
    def __init__(self, start: float, end: float, text: str, lp: float, ns: float) -> None:
        self.start, self.end, self.text, self.avg_logprob, self.no_speech_prob = (
            start,
            end,
            text,
            lp,
            ns,
        )


class _Model:
    loads = 0

    def __init__(self, path: str, **kw: Any) -> None:
        _Model.loads += 1
        self.kw = kw
        self.path = path

    def transcribe(self, samples: Any, **kw: Any) -> tuple[Any, Any]:
        assert kw["language"] == "fa" and kw["beam_size"] == 5 and kw["vad_filter"] is True
        segs = [_Seg(0.0, 2.0, " می خواهم بروم ", -0.1, 0.05), _Seg(2.0, 2.1, "  ", -1, 0.9)]
        return iter(segs), None


@pytest.fixture
def stub_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    fw = types.ModuleType("faster_whisper")
    fw.__version__ = "9.9.9"  # type: ignore[attr-defined]
    fw.WhisperModel = _Model  # type: ignore[attr-defined]
    audio = types.ModuleType("faster_whisper.audio")

    def decode_audio(fh: Any, sampling_rate: int) -> list[float]:
        data = fh.read()
        if data.startswith(b"bad"):
            raise RuntimeError("not audio")
        return [0.0] * (int(data.decode()) * sampling_rate)

    audio.decode_audio = decode_audio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fw)
    monkeypatch.setitem(sys.modules, "faster_whisper.audio", audio)


def pinned_dir(tmp_path: Path, files: dict[str, bytes]) -> tuple[Settings, L.PinnedModel]:
    lock_file = tmp_path / "model.lock.json"
    lock_file.write_text(
        json.dumps(
            {
                "models": {
                    "tiny": {
                        "repo": "x/tiny",
                        "revision": "a" * 40,
                        "licence": "MIT",
                        "files": {
                            n: {"size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                            for n, b in files.items()
                        },
                    }
                }
            }
        )
    )
    s = replace(
        Settings(), model="tiny", models_dir=str(tmp_path / "models"), lock_file=str(lock_file)
    )
    return s, L.load(lock_file, "tiny")


def test_whisper_engine_transcribes_loads_and_unloads(stub_whisper: None, tmp_path: Path) -> None:
    s, _ = pinned_dir(tmp_path, {"model.bin": b"weights"})
    eng = E.WhisperEngine(s)
    assert eng.version == "9.9.9+" + "a" * 12 and not eng.loaded
    t = eng.transcribe(b"3")
    assert eng.loaded and t.duration_s == 3.0 and t.text_raw == "می خواهم بروم"
    assert t.text == "می‌خواهم بروم" and len(t.segments) == 1  # the blank one is dropped
    assert 0.8 < t.confidence < 0.9
    eng.transcribe(b"1")
    assert _Model.loads == 1  # loaded once
    assert eng.unload() is True and eng.unload() is False and not eng.loaded
    with pytest.raises(E.TooLong):
        eng.transcribe(str(s.max_duration_s + 1).encode())
    with pytest.raises(E.Undecodable):
        eng.transcribe(b"bad bytes")


def test_a_model_whose_bytes_are_not_pinned_is_refused(stub_whisper: None, tmp_path: Path) -> None:
    s, model = pinned_dir(tmp_path, {"model.bin": b"weights", "config.json": b"{}"})
    d = s.model_dir
    with pytest.raises(L.ModelInvalid, match="missing"):
        M.create_app(s)
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"weights")
    (d / "config.json").write_bytes(b"[]")
    with pytest.raises(L.ModelInvalid, match="sha256"):
        M.create_app(s)
    (d / "config.json").write_bytes(b"{}x")
    with pytest.raises(L.ModelInvalid, match="size"):
        L.verify(model, d)
    (d / "config.json").write_bytes(b"{}")
    assert M.create_app(s) is not None
    with pytest.raises(L.ModelInvalid, match="not pinned"):
        L.load(s.lock_file, "huge")


def test_the_service_refuses_to_start_on_a_bad_model(
    stub_whisper: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hq_stt import __main__ as entry

    s, _ = pinned_dir(tmp_path, {"model.bin": b"weights"})
    monkeypatch.setenv("STT_ENGINE", "whisper")
    monkeypatch.setenv("STT_MODEL", "tiny")
    monkeypatch.setenv("STT_MODELS_DIR", s.models_dir)
    monkeypatch.setenv("STT_LOCK_FILE", s.lock_file)
    assert entry.main() == 2
    assert "refusing to start" in capsys.readouterr().err


def test_confidence() -> None:
    assert E.confidence_of([]) == 0.0
    assert E.confidence_of([(1.0, 0.0, 0.0)]) == 1.0
    assert E.confidence_of([(1.0, -100.0, 0.0), (1.0, 0.0, 1.0)]) == 0.0
    assert E.confidence_of([(3.0, 0.0, 0.0), (1.0, 0.0, 1.0)]) == 0.75
    with pytest.raises(ValueError, match="STT_ENGINE"):
        E.build(replace(Settings(), engine="nope"))


# ------------------------------------------------------------------- fetch --
def test_fetch_downloads_exactly_the_pinned_bytes(tmp_path: Path) -> None:
    good = {"model.bin": b"w" * 3000, "config.json": b"{}"}
    s, model = pinned_dir(tmp_path, good)
    served = dict(good)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        calls.append(name)
        assert f"/resolve/{'a' * 40}/" in request.url.path
        return httpx.Response(200, content=served[name])

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert F.fetch(model, Path(s.models_dir), c) == 2
        assert F.fetch(model, Path(s.models_dir), c) == 0  # present and right: skipped
        assert len(calls) == 2
        (s.model_dir / "config.json").unlink()
        served["config.json"] = b"[]"  # the server now sends other bytes
        with pytest.raises(L.ModelInvalid, match="pinned"):
            F.fetch(model, Path(s.models_dir), c)
        assert not (s.model_dir / "config.json").exists()
        assert not list(s.model_dir.glob("*.part"))
        served["config.json"] = b"{}" + b"x" * 10  # longer than pinned: cut off, refused
        with pytest.raises(L.ModelInvalid):
            F.fetch(model, Path(s.models_dir), c)


def test_fetch_retries_then_gives_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s, model = pinned_dir(tmp_path, {"model.bin": b"w"})
    monkeypatch.setattr(F.time, "sleep", lambda _s: None)
    tries = []

    def handler(request: httpx.Request) -> httpx.Response:
        tries.append(1)
        if len(tries) < 2:
            return httpx.Response(503)
        return httpx.Response(200, content=b"w")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert F.fetch(model, Path(s.models_dir), c) == 1
        tries.clear()
        (s.model_dir / "model.bin").unlink()
        with pytest.raises(httpx.HTTPStatusError):
            F.fetch(
                model,
                Path(s.models_dir),
                httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
            )


def test_the_committed_lock_pins_every_model() -> None:
    data = json.loads(Path(Settings().lock_file).read_text("utf-8"))
    assert set(data["models"]) >= {"large-v3-turbo", "small", "medium"}
    for name in data["models"]:
        m = L.load(Settings().lock_file, name)
        assert len(m.revision) == 40 and m.licence == "MIT"
        assert any(f.name == "model.bin" for f in m.files)
        assert all(len(f.sha256) == 64 and f.size > 0 for f in m.files)


# -------------------------------------------------------------------- eval --
def test_eval_word_error_rate_on_the_synthetic_samples(tmp_path: Path) -> None:
    fixtures = {}
    for audio in sorted(SAMPLES.glob("*.ogg")):
        text = audio.with_suffix(".txt").read_text("utf-8").strip()
        if audio.stem == "s02-order":
            text = text.replace("امروز", "دیروز")  # one wrong word out of eight
        fixtures[hashlib.sha256(audio.read_bytes()).hexdigest()] = {"text": text, "duration_s": 3.0}
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures, ensure_ascii=False))
    eng = E.build(fake_settings(fake_fixtures=str(fx)))
    rows = V.evaluate(eng, SAMPLES)
    assert len(rows) == 5
    by = {r.name: r for r in rows}
    assert by["s02-order"].errors == 1 and by["s02-order"].wer == 1 / by["s02-order"].words
    assert all(r.errors == 0 for n, r in by.items() if n != "s02-order")
    table = V.render(rows, eng, markdown=False)
    assert "overall" in table and "s05-work" in table
    md = V.render(rows, eng, markdown=True)
    assert md.startswith("# STT evaluation") and "| s02-order |" in md and "WER" in md


def test_eval_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STT_ENGINE", "fake")
    assert V.main([str(tmp_path)]) == 1  # no samples
    (tmp_path / "a.wav").write_bytes(wav(0.5))
    (tmp_path / "a.txt").write_text("این یک متن آزمایشی است", "utf-8")
    assert V.main([str(tmp_path), "--markdown"]) == 0
    out = capsys.readouterr().out
    assert "WER: 0.0%" in out
