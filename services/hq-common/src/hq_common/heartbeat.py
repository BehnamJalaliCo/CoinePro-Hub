"""File heartbeat for Docker healthchecks.

Every HTTP endpoint requires authentication, so the container healthcheck
cannot use one. Instead the service writes a small JSON file while it is
healthy, and the healthcheck only checks that the file is fresh.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# /tmp is the container's private tmpfs (read-only root filesystem).
DEFAULT_PATH = Path(os.environ.get("HQ_HEALTH_FILE", "/tmp/hq-health.json"))  # noqa: S108
MAX_AGE_S = 30.0


async def run(
    check: Callable[[], Awaitable[dict[str, Any]]],
    *,
    path: Path = DEFAULT_PATH,
    interval: float = 10.0,
) -> None:
    """Write the heartbeat while `check()` reports ok; remove it otherwise."""
    while True:
        try:
            state = await check()
        except Exception as exc:  # noqa: BLE001 - any failure means unhealthy
            state = {"ok": False, "error": type(exc).__name__}
        await asyncio.to_thread(_write, path, state)
        await asyncio.sleep(interval)


def _write(path: Path, state: dict[str, Any]) -> None:
    if state.get("ok"):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**state, "ts": time.time()}))
        tmp.replace(path)
    else:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def is_fresh(path: Path = DEFAULT_PATH, max_age: float = MAX_AGE_S) -> bool:
    try:
        return time.time() - path.stat().st_mtime < max_age
    except FileNotFoundError:
        return False


def main() -> None:  # `python -m hq_common.heartbeat` = the Docker healthcheck
    sys.exit(0 if is_fresh() else 1)


if __name__ == "__main__":
    main()
