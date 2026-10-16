"""Service tokens: random secrets, compared by SHA-256 digest in constant time."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def new_token() -> str:
    """A fresh 256-bit token (hex)."""
    return secrets.token_hex(32)


def digest(token: str) -> str:
    """SHA-256 hex digest. Tokens are high-entropy, so a plain hash is enough."""
    return hashlib.sha256(token.encode()).hexdigest()


def matches(token: str, expected_digest: str) -> bool:
    return bool(expected_digest) and hmac.compare_digest(digest(token), expected_digest)


def bearer(header_value: str | None) -> str | None:
    """Extract the token from an `Authorization: Bearer <token>` header."""
    if not header_value:
        return None
    scheme, _, value = header_value.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()
