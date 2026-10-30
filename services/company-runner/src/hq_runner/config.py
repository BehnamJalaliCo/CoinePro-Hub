"""The runner's own files under the work user's home.

~/.config/hq-runner/            mode 700
    config.json                 mode 600: {hub, hub_ip, server_id, runner_token, company,
                                name, paired_at, rotated_at, state}
    state.json                  mode 600: what `hq-runner run` last saw (for `status`);
                                never holds the token

HQ_RUNNER_CONFIG overrides the path of config.json (state.json sits next to it).
Every write is atomic (temporary file in the same folder, fsync, rename).
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HUB = "https://hq.coinepro.com"
ROTATE_EVERY_S = 24 * 3600


def config_path() -> Path:
    env = os.environ.get("HQ_RUNNER_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "hq-runner" / "config.json"


def state_path(cfg_path: Path | None = None) -> Path:
    return (cfg_path or config_path()).with_name("state.json")


@dataclass
class Config:
    hub: str
    runner_token: str
    server_id: str
    hub_ip: str | None = None
    company: str | None = None
    name: str | None = None
    paired_at: float = field(default_factory=time.time)
    rotated_at: float = field(default_factory=time.time)
    state: str = "paired"  # "paired" | "revoked"
    claude_bin: str | None = None
    ca_file: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Config:
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        for key in ("hub", "runner_token", "server_id"):
            if not known.get(key):
                raise ValueError(f"config is missing {key}")
        known["server_id"] = str(known["server_id"])
        return cls(**known)

    def rotation_due(self, now: float | None = None) -> bool:
        return ((now or time.time()) - self.rotated_at) >= ROTATE_EVERY_S


def write_private(path: Path, data: dict[str, Any]) -> None:
    """Writes JSON with mode 600 in a folder with mode 700, atomically."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def load(path: Path | None = None) -> Config | None:
    p = path or config_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return Config.from_json(json.loads(raw))


def save(cfg: Config, path: Path | None = None) -> None:
    write_private(path or config_path(), cfg.to_json())


def load_state(path: Path | None = None) -> dict[str, Any]:
    try:
        data = json.loads(state_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any], path: Path | None = None) -> None:
    state.pop("runner_token", None)
    write_private(state_path(path), state)


def remove(path: Path | None = None) -> bool:
    p = path or config_path()
    removed = False
    for f in (p, state_path(p)):
        try:
            f.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed
