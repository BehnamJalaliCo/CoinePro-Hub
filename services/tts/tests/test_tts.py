"""tts (prompt 12 §4): the one-shot's pass against a fake api, its engine's
text handling, and the pinned voice. No real voice is loaded here (the image's
own bench measures RTF and memory: `make tts-bench`)."""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_tts import engine as E
from hq_tts import job as J

ROOT = Path(__file__).resolve().parents[1]


class FakeApi:
    """/internal/v1/tts: a queue of jobs, then 204 (as while locked or idle)."""

    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = list(jobs)
        self.done: list[tuple[str, bytes, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        assert request.headers["authorization"] == "Bearer t"
        if path == "/internal/v1/tts/claim":
            if not self.jobs:
                return httpx.Response(204)
            return httpx.Response(200, json=self.jobs.pop(0))
        if path.endswith("/done"):
            self.done.append(
                (path.split("/")[-2], request.content, request.headers["content-type"])
            )
            return httpx.Response(200, json={"audio_state": "ready"})
        if path.endswith("/fail"):
            self.failed.append((path.split("/")[-2], json.loads(request.content)["error"]))
            return httpx.Response(204)
        return httpx.Response(404)


def client(api: FakeApi) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://api:8000",
        headers={"Authorization": "Bearer t"},
        transport=httpx.MockTransport(api.handler),
    )


async def test_a_pass_speaks_each_claimed_briefing_and_stops_at_204() -> None:
    api = FakeApi(
        [
            {"id": "a1", "ref": "BR-0001", "script": "سلام.", "voice": "fa_IR-amir-medium"},
            {"id": "a2", "ref": "BR-0002", "script": "روز خوب.", "voice": None},
        ]
    )
    fake = E.Fake()
    async with client(api) as c:
        out = await J.run(c, fake, max_jobs=5)
    assert out == {"done": ["BR-0001", "BR-0002"], "failed": []}
    assert [d[0] for d in api.done] == ["a1", "a2"]
    assert all(d[1].startswith(b"OggS") and d[2] == "audio/ogg" for d in api.done)
    assert fake.scripts == ["سلام.", "روز خوب."]
    assert api.calls[-1] == "POST /internal/v1/tts/claim"  # the 204 ended the pass


async def test_nothing_to_say_means_one_claim_and_no_engine_run() -> None:
    api = FakeApi([])
    fake = E.Fake()
    async with client(api) as c:
        out = await J.run(c, fake, max_jobs=3)
    assert out == {"done": [], "failed": []}
    assert api.calls == ["POST /internal/v1/tts/claim"]
    assert fake.scripts == []


async def test_a_failure_is_reported_and_the_pass_goes_on() -> None:
    api = FakeApi(
        [
            {"id": "b1", "ref": "BR-0003", "script": "یک.", "voice": None},
            {"id": "b2", "ref": "BR-0004", "script": "", "voice": None},
        ]
    )
    async with client(api) as c:
        out = await J.run(c, E.Fake(fail=True), max_jobs=3)
    assert out["failed"] == ["BR-0003", "BR-0004"]
    assert [f[0] for f in api.failed] == ["b1", "b2"]
    assert api.failed[1][1] == "empty script"


async def test_the_pass_is_bounded_by_max_jobs() -> None:
    api = FakeApi(
        [{"id": f"c{i}", "ref": f"BR-{i:04d}", "script": "x.", "voice": None} for i in range(5)]
    )
    async with client(api) as c:
        out = await J.run(c, E.Fake(), max_jobs=2)
    assert len(out["done"]) == 2 and len(api.jobs) == 3


def test_piper_reads_short_lines_without_digits_in_argv() -> None:
    script = "اول، دوم، سوم. " + " ".join(["کلمه"] * 40) + ".\nپایان"
    lines = E.piper_lines(script).strip().split("\n")
    assert lines[:3] == ["اول،", "دوم،", "سوم."]
    assert all(len(x.split()) <= E.CLAUSE_WORDS for x in lines)
    assert lines[-1] == "پایان"


def test_wav_seconds_and_the_real_time_factor(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050 * 2)
    assert E.wav_seconds(p) == pytest.approx(2.0)
    s = E.Spoken(ogg=b"OggS", duration_s=2.0, synth_s=0.5, peak_rss_mb=10)
    assert s.rtf == pytest.approx(0.25)
    assert E.Spoken(ogg=b"", duration_s=0, synth_s=1, peak_rss_mb=0).rtf == 0.0
    assert E.peak_child_rss_mb() >= 0


def test_a_missing_voice_is_refused(tmp_path: Path) -> None:
    with pytest.raises(E.EngineError):
        E.Piper(tmp_path, "fa_IR-amir-medium")


def test_the_real_engine_runs_piper_then_opusenc_with_the_text_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "v.onnx").write_bytes(b"x")
    (tmp_path / "v.onnx.json").write_text("{}")
    seen: list[dict[str, Any]] = []

    def run(argv: list[str], **kw: Any) -> Any:
        seen.append({"argv": argv, **kw})
        cwd = Path(kw["cwd"])
        if "piper" in argv:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\0\0" * 16000)
            (cwd / "speech.wav").write_bytes(buf.getvalue())
        else:
            (cwd / "speech.ogg").write_bytes(b"OggS-data")
        return type("R", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(E.subprocess, "run", run)
    spoken = E.Piper(tmp_path, "v").speak("متن محرمانه‌ی گزارش.", tmp_path)
    assert spoken.ogg == b"OggS-data" and spoken.duration_s == pytest.approx(1.0)
    assert seen[0]["input"].decode().strip() == "متن محرمانه‌ی گزارش."
    assert all("محرمانه" not in " ".join(s["argv"]) for s in seen)  # never in argv
    assert seen[0]["env"]["MALLOC_ARENA_MAX"] == "1"
    assert seen[1]["argv"][:4] == [E.OPUSENC, "--quiet", "--speech", "--bitrate"]

    def broken(argv: list[str], **kw: Any) -> Any:
        return type("R", (), {"returncode": 1, "stderr": b"boom"})()

    monkeypatch.setattr(E.subprocess, "run", broken)
    with pytest.raises(E.EngineError, match="piper failed"):
        E.Piper(tmp_path, "v").speak("x.", tmp_path / "none")


def test_the_voice_is_pinned_by_hash_with_a_free_licence() -> None:
    lock = json.loads((ROOT / "voice.lock.json").read_text())
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert lock["repo_license"] == "MIT"
    for name, v in lock["voices"].items():
        assert v["dataset_license"] in ("CC0-1.0", "CC-BY-4.0", "MIT", "Apache-2.0")
        for fname, f in v["files"].items():
            assert len(f["sha256"]) == 64
            assert f"--checksum=sha256:{f['sha256']}" in dockerfile
            assert f"{lock['revision']}/{v['path']}/{fname}" in dockerfile
        assert name.startswith("fa_IR-")


async def test_the_token_comes_from_openbao(monkeypatch: pytest.MonkeyPatch) -> None:
    class Bao:
        def __init__(self, addr: str, approle: str) -> None:
            pass

        async def read_kv(self, path: str) -> dict[str, Any]:
            assert path == "tts/config"
            return {"api_token": "secret-value"}

    import hq_common.openbao as ob

    monkeypatch.setattr(ob, "OpenBaoClient", Bao)
    assert await J.api_token(J.Settings()) == "secret-value"

    class Empty(Bao):
        async def read_kv(self, path: str) -> dict[str, Any]:
            return {}

    monkeypatch.setattr(ob, "OpenBaoClient", Empty)
    with pytest.raises(RuntimeError):
        await J.api_token(J.Settings())
