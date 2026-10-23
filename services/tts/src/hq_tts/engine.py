"""Speech on the hub's CPU: Piper makes a WAV, opusenc makes it Ogg/Opus.

Both run as separate programs (`python -m piper`, `opusenc`): Piper (GPL-3.0)
is never linked into this code. The text goes in on stdin, never in argv.
Nothing here reaches a network.
"""

from __future__ import annotations

import os
import re
import resource
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

OPUS_KBPS = "32"
OPUSENC = "/usr/bin/opusenc"  # opus-tools (Debian)
PIPER_TIMEOUT_S = 900
ENCODE_TIMEOUT_S = 300
CLAUSE_WORDS = 14  # a line Piper reads at once: memory grows with its length
_BREAK = re.compile(r"(?<=[.!?؟؛،,:])\s+")
CGROUP_PEAK = Path("/sys/fs/cgroup/memory.peak")


class EngineError(Exception):
    pass


@dataclass
class Spoken:
    ogg: bytes
    duration_s: float
    synth_s: float
    peak_rss_mb: float

    @property
    def rtf(self) -> float:
        """Real-time factor: seconds of work per second of audio."""
        return self.synth_s / self.duration_s if self.duration_s else 0.0


class Engine(Protocol):
    def speak(self, script: str, work: Path) -> Spoken: ...


def peak_child_rss_mb() -> float:
    """The largest resident set of any child so far (ru_maxrss is KiB on Linux)."""
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024


def run_measured(
    argv: list[str], *, stdin: bytes, env: dict[str, str], cwd: Path, timeout: float
) -> tuple[int, bytes, float]:
    """One program with its text on stdin -> (exit code, stderr tail, its OWN
    peak resident set in MiB). ⟨prompt 13 §4⟩ wait4 reports this child alone,
    so every bake-off sample has its own measured peak (RUSAGE_CHILDREN only
    knows the largest child so far)."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, the text on stdin
            argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err, env=env, cwd=cwd
        )
        assert proc.stdin is not None
        try:
            proc.stdin.write(stdin)
        finally:
            proc.stdin.close()
        deadline = time.monotonic() + timeout
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid == proc.pid:
                break
            if time.monotonic() > deadline:
                proc.kill()
                _, status, usage = os.wait4(proc.pid, 0)
                proc.returncode = -9
                raise EngineError("timed out")
            time.sleep(0.02)
        proc.returncode = os.waitstatus_to_exitcode(status)
        err.seek(0)
        return proc.returncode, err.read()[-2000:], usage.ru_maxrss / 1024


def piper_lines(script: str) -> str:
    """One short clause per line (sentence ends and commas; a long clause is
    cut at a word boundary): Piper reads each line on its own, so its memory
    stays near the model's (measured: about 260 MB for any length)."""
    out: list[str] = []
    for part in _BREAK.split(" ".join(script.split("\n"))):
        words = part.split()
        while words:
            out.append(" ".join(words[:CLAUSE_WORDS]))
            words = words[CLAUSE_WORDS:]
    return "\n".join(out) + "\n"


def cgroup_peak_mb() -> float | None:
    """The container's own peak (cgroup v2), when the kernel shows it."""
    try:
        return int(CGROUP_PEAK.read_text().strip()) / 1048576
    except (OSError, ValueError):
        return None


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def installed(voices_dir: Path) -> list[str]:
    """The voices of the image's /voices (a model and its config)."""
    return sorted(
        p.name.removesuffix(".onnx")
        for p in voices_dir.glob("*.onnx")
        if Path(f"{p}.json").is_file()
    )


class Piper:
    """The real engine: one voice of the image's /voices."""

    def __init__(self, voices_dir: Path, voice: str, threads: int = 1) -> None:
        self.model = voices_dir / f"{voice}.onnx"
        if not self.model.is_file() or not Path(f"{self.model}.json").is_file():
            raise EngineError(f"voice {voice} is not in {voices_dir}")
        self.threads = threads

    def speak(self, script: str, work: Path) -> Spoken:
        wav = work / "speech.wav"
        ogg = work / "speech.ogg"
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(work),
            "OMP_NUM_THREADS": str(self.threads),
            # one malloc arena: onnxruntime's threads otherwise grow the peak by ~50 MB
            "MALLOC_ARENA_MAX": "1",
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        }
        started = time.monotonic()
        code, stderr, peak = run_measured(
            [sys.executable, "-m", "piper", "-m", str(self.model), "-f", str(wav)],
            stdin=piper_lines(script).encode(),
            env=env,
            cwd=work,
            timeout=PIPER_TIMEOUT_S,
        )
        if code != 0 or not wav.is_file():
            raise EngineError("piper failed: " + stderr.decode(errors="replace")[-300:])
        enc = subprocess.run(  # noqa: S603 - fixed argv
            [OPUSENC, "--quiet", "--speech", "--bitrate", OPUS_KBPS, str(wav), str(ogg)],
            capture_output=True,
            env=env,
            cwd=work,
            timeout=ENCODE_TIMEOUT_S,
            check=False,
        )
        synth = time.monotonic() - started
        if enc.returncode != 0 or not ogg.is_file():
            raise EngineError("opusenc failed: " + enc.stderr.decode(errors="replace")[-300:])
        return Spoken(
            ogg=ogg.read_bytes(),
            duration_s=round(wav_seconds(wav), 3),
            synth_s=round(synth, 3),
            peak_rss_mb=round(peak, 1),
        )


class Fake:
    """For tests: a tiny Ogg-looking payload, no program run."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.scripts: list[str] = []

    def speak(self, script: str, work: Path) -> Spoken:
        self.scripts.append(script)
        if self.fail:
            raise EngineError("fake failure")
        return Spoken(ogg=b"OggS" + b"\0" * 60, duration_s=1.0, synth_s=0.1, peak_rss_mb=1.0)
