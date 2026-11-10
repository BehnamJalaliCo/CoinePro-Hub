"""⟨0.3.0⟩ The company workspace (contract §33.10): one persistent folder per
work item, `~/hq-workspace/<work-ref>` (mode 700), where the server's own
Claude Code works on that work across every turn (a resume keeps it).

    ~/hq-workspace/W-000123/              the work's folder (never shared)
    ~/.config/hq-runner/workspaces.json   mode 600: {ref: {created_at,
                                          last_used_at, closed_at|null,
                                          sent: {out/ name: sha256}}}

The hub tells the runner when a work is closed (`closed` on the long-poll,
once); the runner records it and logs it. A daily sweep removes a folder 30
days after its close and logs that too. Nothing else ever removes one.

HQ_RUNNER_WORKSPACES overrides the root folder (tests).
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hq_runner.config import config_path, write_private

log = logging.getLogger("hq_runner.workspace")
# ⟨0.3.3⟩ workspaces.json is read, changed and written back by every job of the runner (each in
# its own thread): one lock, so two jobs ending together do not lose each other's change
_LOCK = threading.RLock()


def _locked[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        with _LOCK:
            return fn(*args, **kwargs)

    return inner


REF = re.compile(r"^W-[0-9]{6,12}$")
KEEP_DAYS = 30
SWEEP_EVERY_S = 24 * 3600


class WorkspaceError(ValueError):
    """A workspace name that is not a work ref (never a path)."""


def root() -> Path:
    env = os.environ.get("HQ_RUNNER_WORKSPACES")
    return Path(env).expanduser() if env else Path.home() / "hq-workspace"


def state_file(cfg_path: Path | None = None) -> Path:
    return (cfg_path or config_path()).with_name("workspaces.json")


def check_ref(value: Any) -> str:
    if not isinstance(value, str) or not REF.fullmatch(value):
        raise WorkspaceError("workspace must be a work ref like W-000123")
    return value


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(at: Any) -> float | None:
    if isinstance(at, int | float) and not isinstance(at, bool):
        return float(at)
    if isinstance(at, str):
        with contextlib.suppress(ValueError):
            dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
            return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp()
    return None


def load(cfg_path: Path | None = None) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(state_file(cfg_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and REF.fullmatch(str(k))}


def save(state: dict[str, dict[str, Any]], cfg_path: Path | None = None) -> None:
    write_private(state_file(cfg_path), state)


@_locked
def prepare(ref: str, cfg_path: Path | None = None, now: float | None = None) -> Path:
    """The work's folder, made (700) on its first use; every later turn finds
    it as it was left. A folder whose work was closed is opened again only by
    a new turn of that work (the hub sends none after the close)."""
    ref = check_ref(ref)
    base = root()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base, 0o700)
    path = base / ref
    if path.is_symlink():
        raise WorkspaceError("the workspace folder is a symbolic link")
    path.mkdir(exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    t = now if now is not None else time.time()
    state = load(cfg_path)
    entry = state.setdefault(ref, {"created_at": _iso(t), "closed_at": None})
    entry["last_used_at"] = _iso(t)
    save(state, cfg_path)
    return path


def sent_of(ref: str, cfg_path: Path | None = None) -> dict[str, str]:
    """⟨0.3.2⟩ The files of `out/` already sent to the hub for this work: {name: sha256}."""
    entry = load(cfg_path).get(check_ref(ref)) or {}
    sent = entry.get("sent")
    return {str(k): str(v) for k, v in sent.items()} if isinstance(sent, dict) else {}


@_locked
def mark_sent(
    ref: str, name: str | dict[str, str], digest: str = "", cfg_path: Path | None = None
) -> None:
    """⟨0.3.2⟩ Files of `out/` sent (a name and its bytes' sha256, or ⟨0.3.3⟩ {name: sha256} at
    once: recorded after the hub took the turn's result, so a result that never arrived leaves
    its files to be sent again with the next turn)."""
    marks = name if isinstance(name, dict) else {name: digest}
    if not marks:
        return
    state = load(cfg_path)
    entry = state.setdefault(check_ref(ref), {"created_at": None, "closed_at": None})
    prev = entry.get("sent")
    sent: dict[str, Any] = dict(prev) if isinstance(prev, dict) else {}
    sent.update(marks)
    entry["sent"] = sent
    save(state, cfg_path)


@_locked
def close(refs: list[Any], cfg_path: Path | None = None, now: float | None = None) -> list[str]:
    """The hub's close of each work: recorded once (the folder stays until
    the sweep) and logged. Returns the refs newly recorded."""
    state = load(cfg_path)
    t = now if now is not None else time.time()
    recorded: list[str] = []
    for item in refs:
        raw = item.get("workspace") if isinstance(item, dict) else item
        try:
            ref = check_ref(raw)
        except WorkspaceError:
            log.warning("ignored a close for an invalid workspace name")
            continue
        at = _parse(item.get("closed_at")) if isinstance(item, dict) else None
        entry = state.setdefault(ref, {"created_at": None, "last_used_at": None})
        if entry.get("closed_at"):
            continue
        entry["closed_at"] = _iso(at if at is not None else t)
        recorded.append(ref)
        log.info(
            "workspace %s: the hub closed its work at %s; the folder is removed after %d days",
            ref,
            entry["closed_at"],
            KEEP_DAYS,
        )
    if recorded:
        save(state, cfg_path)
    return recorded


@_locked
def sweep(cfg_path: Path | None = None, now: float | None = None) -> list[str]:
    """Removes every workspace whose work closed more than KEEP_DAYS ago
    (logged, one line each). Returns the refs removed."""
    state = load(cfg_path)
    t = now if now is not None else time.time()
    removed: list[str] = []
    for ref, entry in list(state.items()):
        closed = _parse(entry.get("closed_at"))
        if closed is None or t - closed < KEEP_DAYS * 86400:
            continue
        path = root() / ref
        try:
            if path.is_symlink():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
        except OSError as exc:
            log.error("workspace %s: not removed (%s)", ref, type(exc).__name__)
            continue
        del state[ref]
        removed.append(ref)
        log.info("workspace %s removed (its work closed at %s)", ref, entry.get("closed_at"))
    if removed:
        save(state, cfg_path)
    return removed
