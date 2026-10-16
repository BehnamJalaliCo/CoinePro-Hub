"""Agent tokens (contract §2): short-lived, minted by the agent runtime per
run, bound to one employee code. HMAC-SHA256 with a key held in OpenBao
(kv/hq-api/config agent_token_key), shared only with the agent runtime.

    hqa1.<base64url(json {sub, run, iat, exp})>.<base64url(hmac)>

The company is never taken from the token: it comes from the employee row.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

PREFIX = "hqa1"
MAX_TTL_S = 3600


class InvalidToken(ValueError):
    pass


@dataclass(frozen=True)
class Claims:
    employee: str
    run: str
    exp: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint(key: bytes, employee: str, run: str, *, ttl_s: int = 900, now: float | None = None) -> str:
    if not key:
        raise InvalidToken("no agent token key")
    t = int(time.time() if now is None else now)
    payload = _b64(
        json.dumps(
            {"sub": employee, "run": run, "iat": t, "exp": t + min(ttl_s, MAX_TTL_S)},
            separators=(",", ":"),
        ).encode()
    )
    signing = f"{PREFIX}.{payload}".encode()
    return f"{PREFIX}.{payload}.{_b64(hmac.new(key, signing, hashlib.sha256).digest())}"


def verify(key: bytes, token: str, *, now: float | None = None) -> Claims:
    if not key:
        raise InvalidToken("no agent token key")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise InvalidToken("malformed")
    expected = hmac.new(key, f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    try:
        sig = _unb64(parts[2])
        claims = json.loads(_unb64(parts[1]))
    except ValueError as exc:
        raise InvalidToken("malformed") from exc
    if not hmac.compare_digest(sig, expected):
        raise InvalidToken("bad signature")
    t = int(time.time() if now is None else now)
    try:
        sub, run, iat, exp = (
            str(claims["sub"]),
            str(claims["run"]),
            int(claims["iat"]),
            int(claims["exp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken("malformed") from exc
    if exp <= t or exp - iat > MAX_TTL_S or iat > t + 60:
        raise InvalidToken("expired")
    return Claims(employee=sub, run=run, exp=exp)
