"""Small HTTP helpers shared by routes (If-Match / version, contract §1)."""

from __future__ import annotations

from fastapi import Request

from hq_api.errors import ApiError


def if_match(request: Request) -> int:
    """PATCH/PUT need `If-Match: <version>`; a mismatch is checked by the caller."""
    raw = request.headers.get("if-match")
    if raw is None:
        raise ApiError(
            428, "precondition_required", fields={"If-Match": "required (the current version)"}
        )
    raw = raw.strip().removeprefix("W/").strip('"')
    if not raw.isdigit():
        raise ApiError(422, "validation_failed", fields={"If-Match": "must be the version number"})
    return int(raw)


def check_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(409, "version_conflict", f"current version is {current}")
