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
    """/internal/v1/tts (briefings) and /internal/v1/voices/jobs (bake-off
    samples, narration): a queue of jobs each, then 204 (as while locked or idle)."""

    def __init__(
        self, jobs: list[dict[str, Any]], voice_jobs: list[dict[str, Any]] | None = None
    ) -> None:
        self.jobs = list(jobs)
        self.voice_jobs = list(voice_jobs or [])
        self.talk_jobs: list[dict[str, Any]] = []
        self.done: list[tuple[str, bytes, str]] = []
        self.params: list[dict[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        assert request.headers["authorization"] == "Bearer t"
        if path in (
            "/internal/v1/tts/claim",
            "/internal/v1/voices/jobs/claim",
            "/internal/v1/voices/talk/claim",
        ):
            queue = {
                "/internal/v1/tts/claim": self.jobs,
                "/internal/v1/voices/jobs/claim": self.voice_jobs,
                "/internal/v1/voices/talk/claim": self.talk_jobs,
            }[path]
            if not queue:
                return httpx.Response(204)
            return httpx.Response(200, json=queue.pop(0))
        if path.endswith("/done"):
            self.done.append(
                (path.split("/")[-2], request.content, request.headers["content-type"])
            )
            self.params.append(dict(request.url.params))
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
    assert api.calls[-2:] == [  # each queue's 204 ended its part of the pass
        "POST /internal/v1/tts/claim",
        "POST /internal/v1/voices/jobs/claim",
    ]


async def test_nothing_to_say_means_one_claim_and_no_engine_run() -> None:
    api = FakeApi([])
    fake = E.Fake()
    async with client(api) as c:
        out = await J.run(c, fake, max_jobs=3)
    assert out == {"done": [], "failed": []}
    assert api.calls == ["POST /internal/v1/tts/claim", "POST /internal/v1/voices/jobs/claim"]
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


async def test_the_plain_pass_leaves_the_talk_queue_alone() -> None:
    """Prompt 23: a sentence of the conversation is useless two minutes late; only the serving
    mode answers that queue."""
    api = FakeApi([])
    api.talk_jobs.append({"id": "t0", "ref": "talk/t0", "script": "سلام.", "voice": None})
    async with client(api) as c:
        await J.run(c, E.Fake(), max_jobs=3)
    assert "POST /internal/v1/voices/talk/claim" not in api.calls and len(api.talk_jobs) == 1


async def test_the_talk_queue_is_spoken_with_the_shipped_voice_or_the_default() -> None:
    api = FakeApi([])
    api.talk_jobs += [
        {"id": "t1", "ref": "talk/t1", "script": "سلام.", "voice": "fa_IR-amir-medium"},
        {"id": "t2", "ref": "talk/t2", "script": "خداحافظ.", "voice": "not-shipped"},
    ]
    amir, default = E.Fake(), E.Fake()
    async with client(api) as c:
        out = await J.run_talk(c, default, 5, lambda v: amir if v == "fa_IR-amir-medium" else None)
    assert out == {"done": ["talk/t1", "talk/t2"], "failed": []}
    assert amir.scripts == ["سلام."] and default.scripts == ["خداحافظ."]
    assert [d[0] for d in api.done] == ["t1", "t2"]
    assert api.calls[-1] == "POST /internal/v1/voices/talk/claim"  # the 204 ended it


async def test_serving_mode_answers_the_talk_queue_until_its_time_is_up() -> None:
    from hq_tts.__main__ import serve

    api = FakeApi([])
    api.talk_jobs.append({"id": "t3", "ref": "talk/t3", "script": "یک.", "voice": None})
    s = J.Settings(serve_s=1, serve_poll_s=0.2)
    async with client(api) as c:
        out = await serve(c, E.Fake(), s, lambda _v: None)
    assert out == {"done": ["talk/t3"], "failed": []}
    assert api.calls.count("POST /internal/v1/voices/talk/claim") >= 2  # it kept polling
    # the other queues were asked once in an idle moment (204 both), then not again this pass
    assert api.calls.count("POST /internal/v1/tts/claim") == 1
    assert api.calls.count("POST /internal/v1/voices/jobs/claim") == 1


async def test_serving_mode_speaks_the_other_queues_when_the_talk_is_idle() -> None:
    """23.2: with TTS_SERVE_S set (the hub since 23.1) the pass answered only the talk, so no
    briefing voice and no blind-test sample was made. The talk still goes first."""
    from hq_tts.__main__ import serve

    api = FakeApi(
        [{"id": "b1", "ref": "BR-0001", "script": "خلاصه.", "voice": None}],
        [
            {"id": f"s{i}", "kind": "sample", "ref": f"manatts-piper/{i}", "engine": "piper",
             "voice": "fa_IR-mana-medium", "script": "نمونه."}
            for i in range(4)
        ],
    )  # fmt: skip
    api.talk_jobs.append({"id": "t4", "ref": "talk/t4", "script": "سلام.", "voice": None})
    mana = E.Fake()
    s = J.Settings(serve_s=1, serve_poll_s=0.2, max_jobs=3)
    async with client(api) as c:
        out = await serve(c, E.Fake(), s, lambda v: mana if v == "fa_IR-mana-medium" else None)
    assert out["failed"] == []
    assert out["done"][0] == "talk/t4"  # the talk first
    assert out["done"][1:] == ["BR-0001", "manatts-piper/0", "manatts-piper/1"]  # TTS_MAX_JOBS
    assert len(api.voice_jobs) == 2 and mana.scripts == ["نمونه.", "نمونه."]


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

    def measured(argv: list[str], **kw: Any) -> tuple[int, bytes, float]:
        run(argv, input=kw["stdin"], **{k: v for k, v in kw.items() if k != "stdin"})
        return 0, b"", 251.5

    monkeypatch.setattr(E.subprocess, "run", run)
    monkeypatch.setattr(E, "run_measured", measured)
    spoken = E.Piper(tmp_path, "v").speak("متن محرمانه‌ی گزارش.", tmp_path)
    assert spoken.ogg == b"OggS-data" and spoken.duration_s == pytest.approx(1.0)
    assert spoken.peak_rss_mb == 251.5  # this synthesis' own peak (wait4)
    assert seen[0]["input"].decode().strip() == "متن محرمانه‌ی گزارش."
    assert all("محرمانه" not in " ".join(s["argv"]) for s in seen)  # never in argv
    assert seen[0]["env"]["MALLOC_ARENA_MAX"] == "1"
    assert seen[1]["argv"][:4] == [E.OPUSENC, "--quiet", "--speech", "--bitrate"]

    monkeypatch.setattr(E, "run_measured", lambda argv, **kw: (1, b"boom", 0.0))
    with pytest.raises(E.EngineError, match="piper failed"):
        E.Piper(tmp_path, "v").speak("x.", tmp_path / "none")


def test_other_engine_errors_become_engine_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hung opusenc, a truncated WAV or a pipe error fails the one job (EngineError),
    so the queue posts /fail and goes on instead of ending the whole pass."""
    (tmp_path / "v.onnx").write_bytes(b"x")
    (tmp_path / "v.onnx.json").write_text("{}")

    def piper_ok(argv: list[str], **kw: Any) -> tuple[int, bytes, float]:
        (Path(kw["cwd"]) / "speech.wav").write_bytes(b"RIFF-truncated")
        return 0, b"", 1.0

    def enc_ok(argv: list[str], **kw: Any) -> Any:
        (Path(kw["cwd"]) / "speech.ogg").write_bytes(b"OggS")
        return type("R", (), {"returncode": 0, "stderr": b""})()

    def enc_hangs(argv: list[str], **kw: Any) -> Any:
        raise E.subprocess.TimeoutExpired(argv, kw["timeout"])

    def pipe_breaks(argv: list[str], **kw: Any) -> tuple[int, bytes, float]:
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(E, "run_measured", piper_ok)
    monkeypatch.setattr(E.subprocess, "run", enc_hangs)
    with pytest.raises(E.EngineError, match="opusenc timed out"):
        E.Piper(tmp_path, "v").speak("x.", tmp_path)
    monkeypatch.setattr(E.subprocess, "run", enc_ok)
    with pytest.raises(E.EngineError, match="bad wav"):
        E.Piper(tmp_path, "v").speak("x.", tmp_path)
    monkeypatch.setattr(E, "run_measured", pipe_breaks)
    with pytest.raises(E.EngineError, match="Broken pipe"):
        E.Piper(tmp_path, "v").speak("x.", tmp_path)


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
    for name, v in lock.get("extra", {}).items():  # a voice from its own repository (2026-11-05)
        assert v["repo_license"] == "MIT" and v["dataset_license"] == "CC0-1.0"
        for fname, f in v["files"].items():
            assert f"--checksum=sha256:{f['sha256']}" in dockerfile
            assert f"{v['repo']}/resolve/{v['revision']}/{fname}" in dockerfile
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
