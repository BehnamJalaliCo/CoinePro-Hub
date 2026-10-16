"""Cursor pagination (contract §1): opaque cursors, `limit` max 200."""

from __future__ import annotations

import base64
import json
from typing import Any

from hq_api.errors import ApiError

MAX_LIMIT = 200


def encode(values: list[Any]) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(cursor: str | None, n: int) -> list[Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(422, "validation_failed", fields={"cursor": "invalid"}) from exc
    if not isinstance(values, list) or len(values) != n:
        raise ApiError(422, "validation_failed", fields={"cursor": "invalid"})
    return values


def page(
    rows: list[dict[str, Any]], limit: int, keys: tuple[str, ...]
) -> tuple[list[dict[str, Any]], str | None]:
    """Rows fetched with LIMIT limit+1 -> (items, next_cursor)."""
    if len(rows) <= limit:
        return rows, None
    items = rows[:limit]
    last = items[-1]
    return items, encode([last[k] for k in keys])
