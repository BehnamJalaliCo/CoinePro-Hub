"""UUID version 7 (RFC 9562): time-ordered ids for the ledger."""

from __future__ import annotations

import os
import time
import uuid


def uuid7(unix_ms: int | None = None) -> uuid.UUID:
    ms = (time.time_ns() // 1_000_000 if unix_ms is None else unix_ms) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> 68  # 12 bits
    rand_b = rand & ((1 << 62) - 1)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
