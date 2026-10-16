"""Callers (service tokens from OpenBao) and per-caller rate limiting.

OpenBao kv/llm-router/callers:
    {"callers": {"<name>": {"token_sha256": "...", "rpm": 60, "max_input_chars": 200000}}}
Only digests are stored; plaintext tokens live with each caller.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hq_common import tokens


@dataclass(frozen=True)
class Caller:
    name: str
    token_sha256: str
    rpm: int
    max_input_chars: int


class CallerDirectory:
    def __init__(self) -> None:
        self._callers: tuple[Caller, ...] = ()

    def load(
        self, data: Mapping[str, Any], *, default_rpm: int, default_max_input_chars: int
    ) -> int:
        callers = []
        for name, c in (data.get("callers") or {}).items():
            callers.append(
                Caller(
                    name=name,
                    token_sha256=str(c["token_sha256"]),
                    rpm=int(c.get("rpm", default_rpm)),
                    max_input_chars=int(c.get("max_input_chars", default_max_input_chars)),
                )
            )
        self._callers = tuple(callers)
        return len(callers)

    def lookup(self, token: str | None) -> Caller | None:
        if not token:
            return None
        found = None
        for c in self._callers:  # check all: no early exit timing signal
            if tokens.matches(token, c.token_sha256):
                found = c
        return found


class RateLimiter:
    """Token bucket per caller: `rpm` requests per minute, bursts up to `rpm`."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, name: str, rpm: int) -> tuple[bool, int]:
        now = self._clock()
        level, last = self._buckets.get(name, (float(rpm), now))
        level = min(float(rpm), level + (now - last) * rpm / 60.0)
        if level >= 1.0:
            self._buckets[name] = (level - 1.0, now)
            return True, 0
        self._buckets[name] = (level, now)
        return False, max(1, int((1.0 - level) * 60.0 / rpm) + 1)
