"""Jobs for test_untrusted: what a child process can be asked to do."""

from __future__ import annotations

import os
import resource
import time
from pathlib import Path
from typing import Any


def echo(data: bytes, suffix: str = "") -> str:
    return data.decode() + suffix


def refuse() -> None:
    raise ValueError("not a file this job accepts")


def hog(mb: int) -> int:
    blocks = [bytearray(1024 * 1024) for _ in range(mb)]
    return len(blocks)


def spin() -> None:
    while True:
        pass


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def big_answer(mb: int) -> str:
    return "x" * (mb * 1024 * 1024)


def inside() -> dict[str, Any]:
    """What the child sees: its environment, limits and OOM preference."""
    return {
        "env": sorted(os.environ),
        "as": resource.getrlimit(resource.RLIMIT_AS),
        "cpu": resource.getrlimit(resource.RLIMIT_CPU),
        "fsize": resource.getrlimit(resource.RLIMIT_FSIZE),
        "core": resource.getrlimit(resource.RLIMIT_CORE),
        "oom": Path("/proc/self/oom_score_adj").read_text().strip(),
        "cwd": os.getcwd(),
    }


def write(path: str, size: int) -> int:
    with open(path, "wb") as fh:
        return fh.write(b"\0" * size)


def open_socket() -> dict[str, str]:
    """Python's socket, then the raw C one (which only the kernel can refuse)."""
    import _socket
    import socket

    out = {}
    for name, make in (("python", socket.socket), ("raw", _socket.socket)):
        try:
            s = make(socket.AF_INET, socket.SOCK_STREAM)
            s.close()
            out[name] = "opened"
        except OSError:
            out[name] = "refused"
    return out
