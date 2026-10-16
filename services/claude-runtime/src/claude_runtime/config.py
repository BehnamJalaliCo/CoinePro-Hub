"""Settings from the environment (non-secret). Secrets come from OpenBao."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    openbao_addr: str = field(
        default_factory=lambda: os.environ.get("OPENBAO_ADDR", "http://openbao:8200")
    )
    approle_file: str = field(
        default_factory=lambda: os.environ.get(
            "OPENBAO_APPROLE_FILE", "/run/secrets/hq/approle.json"
        )
    )
    listen_port: int = field(default_factory=lambda: int(os.environ.get("PORT", "8100")))
    max_concurrency: int = field(
        default_factory=lambda: int(os.environ.get("RUNTIME_MAX_CONCURRENCY", "4"))
    )
    # Per-run scratch space on the container's tmpfs; wiped after every run.
    workdir_root: str = field(
        default_factory=lambda: os.environ.get("RUNTIME_WORKDIR", "/tmp/runs")  # noqa: S108
    )
    # Tests point this at testing/fake_claude.py; production uses the bundled CLI.
    cli_path: str | None = field(default_factory=lambda: os.environ.get("RUNTIME_CLI_PATH") or None)
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))
