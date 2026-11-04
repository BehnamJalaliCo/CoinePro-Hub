"""HMAC-SHA256 signing between the hub and n8n (contract §30.4), both ways.

The header `X-HQ-Signature: t=<unix seconds>,v1=<hex>` signs `<t>.<raw body>`; a signature older than
`max_age_s` or not matching is refused. The secret comes from OpenBao (`kv/hq/n8n`), never from a file
in the repository, and is never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import time

HEADER = "X-HQ-Signature"


def sign(secret: str, body: bytes, *, now: int | None = None) -> str:
    t = int(now if now is not None else time.time())
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify(
    secret: str, body: bytes, header: str | None, *, max_age_s: int = 300, now: int | None = None
) -> bool:
    if not secret or not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        t = int(parts.get("t", ""))
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if abs(current - t) > max_age_s:
        return False
    want = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, parts.get("v1", ""))
