"""Settings from the environment (non-secret; stt has no secret at all)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

LOCK_FILE = Path(__file__).resolve().parents[2] / "model.lock.json"


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    listen_port: int = field(default_factory=lambda: _int("PORT", 8000))
    # "whisper" in production; "fake" for tests and CI (never a model download).
    engine: str = field(default_factory=lambda: os.environ.get("STT_ENGINE", "whisper"))
    # A model named in model.lock.json (pinned repo, revision and sha256 of every file).
    model: str = field(default_factory=lambda: os.environ.get("STT_MODEL", "large-v3-turbo"))
    models_dir: str = field(default_factory=lambda: os.environ.get("STT_MODELS_DIR", "/models"))
    lock_file: str = field(default_factory=lambda: os.environ.get("STT_LOCK_FILE", str(LOCK_FILE)))
    compute_type: str = field(default_factory=lambda: os.environ.get("STT_COMPUTE_TYPE", "int8"))
    cpu_threads: int = field(default_factory=lambda: _int("STT_CPU_THREADS", 4))
    beam_size: int = field(default_factory=lambda: _int("STT_BEAM_SIZE", 5))
    language: str = "fa"
    # The model is loaded on the first request and freed after this many idle seconds.
    idle_unload_s: int = field(default_factory=lambda: _int("STT_IDLE_UNLOAD_S", 300))
    # One transcription at a time; at most this many wait, the rest get 503 busy.
    max_waiting: int = field(default_factory=lambda: _int("STT_MAX_WAITING", 4))
    max_bytes: int = field(default_factory=lambda: _int("STT_MAX_BYTES", 25 * 1024 * 1024))
    max_duration_s: int = field(default_factory=lambda: _int("STT_MAX_DURATION_S", 15 * 60))
    # Fake engine only: JSON {"<sha256 of the audio>": "text", ...}.
    fake_fixtures: str = field(default_factory=lambda: os.environ.get("STT_FAKE_FIXTURES", ""))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))

    @property
    def model_dir(self) -> Path:
        return Path(self.models_dir) / self.model
