"""Files as records (prompt 6 §2, contract §17.1): rendering a FileRef, storing
an original with its variants, and attaching owner uploads to a thread.

An owner upload belongs to the holding until it is attached; attaching moves
it, its variants and its processing row to the thread's company, once (the
append-only guard of files.files allows exactly that move). A file already in
another operating company is refused: it is that company's now.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api import media
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import FileRef, FileVariants

MAX_ATTACHMENTS = 10

FILE_SQL = """
    SELECT f.id, f.name, f.mime, f.size, f.sha256, f.kind, f.width, f.height, f.duration_s,
           f.company_id, f.storage_key, f.variant, f.parent_id,
           p.status, p.transcript,
           (SELECT v.id FROM files.files v WHERE v.parent_id = f.id AND v.variant = 'thumb' LIMIT 1) AS thumb,
           (SELECT v.id FROM files.files v WHERE v.parent_id = f.id AND v.variant = 'poster' LIMIT 1) AS poster
    FROM files.files f LEFT JOIN files.processing p ON p.file_id = f.id
"""


def render(r: dict[str, Any]) -> FileRef:
    kind = r.get("kind") or "other"
    return FileRef(
        id=r["id"],
        name=r["name"],
        mime=r["mime"],
        size=int(r["size"]),
        sha256=r["sha256"],
        kind="document" if kind == "other" else kind,
        status=r.get("status") or "ready",
        width=r.get("width"),
        height=r.get("height"),
        duration_s=float(r["duration_s"]) if r.get("duration_s") is not None else None,
        variants=FileVariants(thumb=r.get("thumb"), poster=r.get("poster")),
        transcript=r.get("transcript"),
    )


async def refs(tx: Tx, ids: list[UUID]) -> dict[UUID, FileRef]:
    if not ids:
        return {}
    rows = await tx.all(FILE_SQL + " WHERE f.id = ANY(:ids)", ids=list(ids))
    return {r["id"]: render(r) for r in rows}


async def load(tx: Tx, file_id: UUID) -> dict[str, Any]:
    return await tx.one(FILE_SQL + " WHERE f.id = :id", id=file_id)


async def insert(
    tx: Tx,
    *,
    company_id: UUID,
    name: str,
    mime: str,
    size: int,
    sha256: str,
    storage_key: str,
    kind: str,
    by_kind: str,
    by_code: str,
    variant: str = "original",
    parent_id: UUID | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_s: float | None = None,
    frame_at_s: float | None = None,
) -> UUID:
    file_id: UUID = await tx.scalar(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code, kind, variant, parent_id, width, height, duration_s, frame_at_s)
           VALUES (:co, :name, :mime, :size, :sha, :key, :bk, :bc, :kind, :variant, :parent, :w, :h,
                   :dur, :at)
           RETURNING id""",
        co=company_id,
        name=name[:255],
        mime=mime,
        size=size,
        sha=sha256,
        key=storage_key,
        bk=by_kind,
        bc=by_code,
        kind=kind,
        variant=variant,
        parent=parent_id,
        w=width,
        h=height,
        dur=duration_s,
        at=frame_at_s,
    )
    return file_id


async def attach(tx: Tx, ids: list[UUID], thread_company: UUID, holding_id: UUID) -> list[UUID]:
    """Owner files for a message in a thread of `thread_company`: each must be an
    original the owner may attach (in the holding, i.e. not attached yet, or
    already in this company). Holding files move here with their variants."""
    unique = list(dict.fromkeys(ids))
    if len(unique) > MAX_ATTACHMENTS:
        raise ApiError(
            422, "validation_failed", fields={"attachments": f"at most {MAX_ATTACHMENTS}"}
        )
    if not unique:
        return []
    rows = await tx.all(
        "SELECT id, company_id, variant FROM files.files WHERE id = ANY(:ids)", ids=unique
    )
    found = {r["id"]: r for r in rows}
    for fid in unique:
        r = found.get(fid)
        if r is None or r["variant"] != "original":
            raise ApiError(422, "validation_failed", fields={"attachments": f"unknown file {fid}"})
        if r["company_id"] not in (holding_id, thread_company):
            raise ApiError(
                422,
                "validation_failed",
                fields={"attachments": "a file attached in another company; upload it again"},
            )
    moving = [fid for fid in unique if found[fid]["company_id"] == holding_id]
    if moving and thread_company != holding_id:
        await tx.exec(
            """UPDATE files.files SET company_id = :co
               WHERE (id = ANY(:ids) OR parent_id = ANY(:ids)) AND company_id = :holding""",
            co=thread_company,
            ids=moving,
            holding=holding_id,
        )
        await tx.exec(
            "UPDATE files.processing SET company_id = :co WHERE file_id = ANY(:ids)",
            co=thread_company,
            ids=moving,
        )
    return unique


async def document_pending(tx: Tx, file_id: UUID, company_id: UUID) -> None:
    """A PDF whose text is still to come (prompt 07.1 §1.2): recorded first,
    extracted outside any transaction, written by document_done."""
    await tx.exec(
        """INSERT INTO files.processing (file_id, company_id, status)
           VALUES (:f, :co, 'processing')""",
        f=file_id,
        co=company_id,
    )


async def document_done(
    tx: Tx, file_id: UUID, status: str, text: str | None, error: str | None
) -> None:
    """The second transaction: `ready` (with or without text) or `failed`."""
    await tx.exec(
        """UPDATE files.processing SET status = :st, text = :t, error = :e,
               attempts = attempts + 1, updated_at = now()
           WHERE file_id = :f AND status = 'processing'""",
        f=file_id,
        st=status,
        t=text[:200_000] if text else None,
        e=error[:300] if error else None,
    )


async def extract_text(
    tx: Callable[[], AbstractAsyncContextManager[Tx]], file_id: UUID, path: Path
) -> str:
    """A PDF's text from a child process (media.pdf_text), outside any
    transaction, then written in one of its own -> the status."""
    got = await media.pdf_text(path)
    async with tx() as t:
        await document_done(t, file_id, got.status, got.text, got.error)
    return got.status
