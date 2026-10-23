"""tts, prompt 13 §4: the second queue (bake-off samples, a media item's
narration) with each job's own voice and measurement, the local bake-off
harness, and one synthesis' own peak memory (wait4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_tts import FakeApi, client

from hq_tts import bakeoff as BK
from hq_tts import engine as E
from hq_tts import job as J
from hq_tts.__main__ import engines

ROOT = Path(__file__).resolve().parents[1]


class Named(E.Fake):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


async def test_voice_jobs_speak_with_their_own_voice_and_send_their_numbers() -> None:
    api = FakeApi(
        [{"id": "b1", "ref": "BR-0009", "script": "سلام.", "voice": "fa_IR-unknown"}],
        [
            {"id": "s1", "kind": "sample", "ref": "piper-ganji/numbers", "engine": "piper",
             "voice": "fa_IR-ganji-medium", "script": "یک و دو."},
            {"id": "s2", "kind": "sample", "ref": "parsvoice-xtts/numbers", "engine": "xtts",
             "voice": None, "script": "یک."},
            {"id": "n1", "kind": "narration", "ref": "MI-0001", "engine": "piper",
             "voice": "fa_IR-gyro-medium", "script": "روایت."},
        ],
    )  # fmt: skip
    default, ganji = Named("amir"), Named("ganji")
    shipped = {"fa_IR-ganji-medium": ganji}
    async with client(api) as c:
        out = await J.run(c, default, max_jobs=5, engines=lambda v: shipped.get(v) if v else None)
    assert out == {"done": ["BR-0009", "piper-ganji/numbers"],
                   "failed": ["parsvoice-xtts/numbers", "MI-0001"]}  # fmt: skip
    # A briefing with a voice the image lacks keeps the default; a voice job never does.
    assert default.scripts == ["سلام."] and ganji.scripts == ["یک و دو."]
    assert [f[1] for f in api.failed] == ["voice not installed", "voice not installed"]
    assert api.params[0] == {"duration_s": "1.0"}  # a briefing: its length only
    assert api.params[1] == {"duration_s": "1.0", "synth_s": "0.1", "peak_mb": "1.0"}
    assert [d[0] for d in api.done] == ["b1", "s1"]


async def test_a_locked_or_idle_api_means_no_synthesis_at_all() -> None:
    api = FakeApi([], [])
    fake = E.Fake()
    async with client(api) as c:
        out = await J.run(c, fake, max_jobs=3)
    assert out == {"done": [], "failed": []} and fake.scripts == []


def test_the_harness_measures_every_voice_on_every_script(tmp_path: Path) -> None:
    scripts = [
        {"key": "numbers", "spoken": "یک و دو."},
        {"key": "long", "spoken": "یک جمله‌ی بلند."},
    ]
    report = BK.measure({"a": E.Fake(), "b": E.Fake()}, scripts, tmp_path)
    assert set(report["voices"]) == {"a", "b"}
    a = report["voices"]["a"]
    assert a["rtf"] == pytest.approx(0.1) and a["peak_mb"] == 1.0 and len(a["samples"]) == 2
    assert {p.name for p in tmp_path.iterdir()} == {
        "a.numbers.ogg",
        "a.long.ogg",
        "b.numbers.ogg",
        "b.long.ogg",
    }
    assert "container_peak_mb" in report


def test_the_harness_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    (tmp_path / "voices").mkdir()
    for v in ("fa_IR-a-medium", "fa_IR-b-medium"):
        (tmp_path / "voices" / f"{v}.onnx").write_bytes(b"x")
        (tmp_path / "voices" / f"{v}.onnx.json").write_text("{}")
    (tmp_path / "voices" / "orphan.onnx").write_bytes(b"x")  # no config: not a voice
    assert E.installed(tmp_path / "voices") == ["fa_IR-a-medium", "fa_IR-b-medium"]
    monkeypatch.setenv("TTS_VOICES_DIR", str(tmp_path / "voices"))
    monkeypatch.setattr(BK, "Piper", lambda root, v, threads: E.Fake())
    scripts = tmp_path / "s.json"
    scripts.write_text(json.dumps([{"key": "numbers", "spoken": "یک."}]), encoding="utf-8")
    assert (
        BK.main(
            [
                "--scripts",
                str(scripts),
                "--out",
                str(tmp_path / "out"),
                "--voices",
                "fa_IR-a-medium",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert list(report["voices"]) == ["fa_IR-a-medium"]
    default, shipped = engines(
        J.Settings(voices_dir=str(tmp_path / "voices"), voice="fa_IR-b-medium")
    )
    assert (
        set(shipped) == {"fa_IR-a-medium", "fa_IR-b-medium"}
        and default is shipped["fa_IR-b-medium"]
    )


def test_one_synthesis_has_its_own_peak_and_a_deadline(tmp_path: Path) -> None:
    code, err, peak = E.run_measured(
        [sys.executable, "-c", "import sys; data = sys.stdin.read(); b = bytearray(40 * 1024 * 1024); print(len(data))"],
        stdin="متن".encode(),
        env={"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
        timeout=60,
    )  # fmt: skip
    assert code == 0 and err == b"" and 40 < peak < 400
    with pytest.raises(E.EngineError, match="timed out"):
        E.run_measured(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=b"", env={"PATH": "/usr/bin:/bin"}, cwd=tmp_path, timeout=0.5,
        )  # fmt: skip


def test_every_shipped_voice_is_pinned_and_the_unlicensed_one_is_not_shipped() -> None:
    lock = json.loads((ROOT / "voice.lock.json").read_text())
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert {"fa_IR-amir-medium", "fa_IR-ganji-medium", "fa_IR-ganji_adabi-medium",
            "fa_IR-reza_ibrahim-medium"} == set(lock["voices"])  # fmt: skip
    assert "fa_IR-gyro-medium" in lock["not_installed"] and "gyro" not in dockerfile
    assert dockerfile.count("--checksum=sha256:") == 2 * len(lock["voices"])
    assert all(len(v["model_card_sha256"]) == 64 for v in lock["voices"].values())


async def test_http_errors_of_the_api_end_the_pass() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/v1/tts/claim":
            return httpx.Response(204)
        return httpx.Response(500)

    async with httpx.AsyncClient(
        base_url="http://api:8000", transport=httpx.MockTransport(handler)
    ) as c:
        with pytest.raises(httpx.HTTPStatusError):
            await J.run(c, E.Fake(), max_jobs=2)
