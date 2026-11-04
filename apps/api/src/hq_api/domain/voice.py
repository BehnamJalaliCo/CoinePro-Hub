"""Long voice (contract §29.5): one recording of the owner sent to the hub's
speech to text in chunks, when it is over a minute or the phone's own
recogniser failed.

    POST /transcribe/sessions {purpose}        -> {id, ...}
    PUT  /transcribe/sessions/{id}/chunks/{n}  raw audio, ≤ 90 s, in order, idempotent per n
    POST /transcribe/sessions/{id}/finish      -> {text, duration_s, chunks, segments}

Each chunk is a file of the holding (the same checks as an upload, §17.1),
kept in `owner.voice_sessions.chunks` in the order of n. `finish` sends each
chunk through the hub's existing speech to text (on demand, §27.3; a chunk
already transcribed is not sent again), joins the texts in order, runs the
deterministic Persian normaliser over the whole, and offsets each chunk's
segments by the chunks before it. A session holds at most
`STT_SESSION_MAX_S` seconds (default 1 200, 20 minutes); unused for 30
minutes it expires (the worker's sweep). Owner only; nothing leaves the hub.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common import persian

CHUNK_MAX_S = 90
SLACK_S = 1.0  # what a 90-second chunk may probe to beyond 90
IDLE = timedelta(minutes=30)
PURPOSES = ("order", "rule", "message", "note", "talk")  # ⟨1.14⟩ §32.7 a long talk turn


def expired(s: dict[str, Any], now: datetime | None = None) -> bool:
    used: datetime = s["used_at"]
    return s["state"] == "expired" or (
        s["state"] == "open" and used < (now or datetime.now(UTC)) - IDLE
    )


def chunks_of(s: dict[str, Any]) -> list[dict[str, Any]]:
    raw = s.get("chunks") or []
    return [dict(c) for c in (json.loads(raw) if isinstance(raw, str) else raw)]


async def load(tx: Tx, session_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    """An open (or finished) session; an expired one is 410 session_expired."""
    s = await tx.first(
        "SELECT * FROM owner.voice_sessions WHERE id = :id"  # noqa: S608 - a constant
        + (" FOR UPDATE" if lock else ""),
        id=session_id,
    )
    if s is None:
        raise ApiError(404, "not_found", "no such session")
    if expired(s):
        if s["state"] == "open":
            await tx.exec(
                """UPDATE owner.voice_sessions SET state = 'expired', finished_at = now()
                   WHERE id = :id AND state = 'open'""",
                id=session_id,
            )
        raise ApiError(410, "session_expired", "the session expired; start a new one")
    return dict(s)


def place(chunks: list[dict[str, Any]], n: int) -> int | None:
    """Where chunk n goes: its index when it was sent already (sent again),
    the end when it is the next one, else None (out of order). The first
    chunk may be 0 or 1; the rest follow it."""
    for i, c in enumerate(chunks):
        if int(c["n"]) == n:
            return i
    base = int(chunks[0]["n"]) if chunks else (0 if n == 0 else 1)
    return len(chunks) if n == base + len(chunks) else None


def add_chunk(
    chunks: list[dict[str, Any]], n: int, entry: dict[str, Any], max_s: int
) -> tuple[list[dict[str, Any]], float, bool]:
    """(the chunks with this one, the seconds in all, whether it was new);
    422 out of order, 413 past the session's cap."""
    i = place(chunks, n)
    if i is None:
        nxt = (int(chunks[0]["n"]) + len(chunks)) if chunks else 0
        raise ApiError(422, "validation_failed", fields={"n": f"chunks go in order: {nxt} is next"})
    out = list(chunks)
    new = i == len(out)
    if new:
        out.append(entry)
    elif out[i].get("sha256") == entry["sha256"]:
        return out, total(out), False  # the same chunk again: nothing changes
    else:
        out[i] = entry  # sent again with other bytes: the last one counts
    seconds = total(out)
    if seconds > max_s + SLACK_S:
        raise ApiError(
            413, "validation_failed", fields={"duration": f"at most {max_s // 60} min in all"}
        )
    return out, seconds, new


def total(chunks: list[dict[str, Any]]) -> float:
    return round(sum(float(c.get("duration_s") or 0) for c in chunks), 2)


def join(parts: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """The chunks' transcripts (in order) as one: the texts joined and
    normalised again as a whole, the segments on one time line."""
    texts: list[str] = []
    segments: list[dict[str, Any]] = []
    at = 0.0
    for chunk, out in parts:
        text = " ".join(str(out.get("text") or "").split())
        if text:
            texts.append(text)
        for seg in out.get("segments") or []:
            segments.append(
                {
                    "start_s": round(at + float(seg.get("start_s") or 0), 2),
                    "end_s": round(at + float(seg.get("end_s") or 0), 2),
                    "text": str(seg.get("text") or ""),
                }
            )
        at += float(out.get("duration_s") or chunk.get("duration_s") or 0)
    return {
        "text": persian.normalise(" ".join(texts)),
        "duration_s": round(at, 2),
        "chunks": len(parts),
        "segments": segments,
    }


async def expire(tx: Tx, now: datetime | None = None) -> int:
    """The worker's sweep: sessions unused for 30 minutes expire."""
    return int(
        await tx.exec(
            """UPDATE owner.voice_sessions SET state = 'expired', finished_at = now()
               WHERE state = 'open' AND used_at < :t""",
            t=(now or datetime.now(UTC)) - IDLE,
        )
        or 0
    )
