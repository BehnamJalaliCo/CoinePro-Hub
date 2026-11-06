"""Files as records (prompt 6 §2, contract §17.1): rendering a FileRef, storing
an original with its variants, and attaching owner uploads to a thread.

An owner upload belongs to the holding until it is attached; attaching moves
it, its variants and its processing row to the thread's company, once (the
append-only guard of files.files allows exactly that move, and only for the
owner's own uploads: never a holding agent's output or a transcript). A file
already in another operating company is refused: it is that company's now.
Until then the holding's own agents do not see it either (UNATTACHED_UPLOAD).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any
from uuid import UUID

from hq_api import media
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import FileMeta, FileRef, FileVariants

MAX_ATTACHMENTS = 10

FILE_SQL = """
    SELECT f.id, f.name, f.mime, f.size, f.sha256, f.kind, f.width, f.height, f.duration_s,
           f.company_id, f.storage_key, f.variant, f.parent_id, f.meta, f.created_by_kind,
           p.status, p.transcript,
           (SELECT v.id FROM files.files v WHERE v.parent_id = f.id AND v.variant = 'thumb' LIMIT 1) AS thumb,
           (SELECT v.id FROM files.files v WHERE v.parent_id = f.id AND v.variant = 'poster' LIMIT 1) AS poster
    FROM files.files f LEFT JOIN files.processing p ON p.file_id = f.id
"""


# An owner upload still waiting in the holding for its first attachment (06.1
# §3): no agent reads it, not even the holding's own. `f` is files.files.
UNATTACHED_UPLOAD = """(f.created_by_kind = 'owner'
    AND EXISTS (SELECT 1 FROM core.companies hc WHERE hc.id = f.company_id AND hc.kind = 'holding')
    AND NOT EXISTS (SELECT 1 FROM msg.messages m WHERE m.attachments @> ARRAY[f.id]))"""


def _meta(r: dict[str, Any]) -> FileMeta | None:
    raw = r.get("meta")
    meta = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(meta, dict) or not meta.get("family"):
        return None
    return FileMeta(family=str(meta["family"]), style=meta.get("style"))


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
        meta=_meta(r),
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
    meta: dict[str, Any] | None = None,
) -> UUID:
    file_id: UUID = await tx.scalar(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code, kind, variant, parent_id, width, height, duration_s, frame_at_s, meta)
           VALUES (:co, :name, :mime, :size, :sha, :key, :bk, :bc, :kind, :variant, :parent, :w, :h,
                   :dur, :at, CAST(:meta AS jsonb))
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
        meta=json.dumps(meta or {}, ensure_ascii=False),
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
    # Locked first (06.1 §2): the worker storing a variant of one of them holds
    # it FOR SHARE (files.lock_company), so either it finishes first and its
    # variant moves with the file below, or it waits and stores it here after.
    rows = await tx.all(
        """SELECT id, company_id, variant, created_by_kind FROM files.files
           WHERE id = ANY(:ids) ORDER BY id FOR UPDATE""",
        ids=unique,
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
        if (
            r["company_id"] == holding_id
            and thread_company != holding_id
            and r["created_by_kind"] != "owner"
        ):
            raise ApiError(
                422,
                "validation_failed",
                fields={"attachments": "only your own uploads move to a company"},
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


UNKNOWN_FA = "این فایل پیدا نشد؛ دوباره بارگذاری کنید."
ELSEWHERE_FA = "این فایل پیش‌تر در گفتگوی یک شرکت فرستاده شده است؛ دوباره بارگذاری کنید."


async def owner_uploads(tx: Tx, ids: list[UUID], holding_id: UUID) -> list[dict[str, Any]]:
    """⟨1.18⟩ §36.2 the files of a talk turn: the owner's own uploads (originals), still in the
    holding (one already sent in a company's thread is that company's: upload it again). In the
    given order, without repeats; 422 with `message_fa` otherwise."""
    unique = list(dict.fromkeys(ids))
    if len(unique) > MAX_ATTACHMENTS:
        raise ApiError(
            422,
            "validation_failed",
            fields={"file_ids": f"at most {MAX_ATTACHMENTS}"},
            message_fa=f"در هر پیام حداکثر {MAX_ATTACHMENTS} فایل.",
        )
    if not unique:
        return []
    rows = {
        r["id"]: dict(r) for r in await tx.all(FILE_SQL + " WHERE f.id = ANY(:ids)", ids=unique)
    }
    for fid in unique:
        r = rows.get(fid)
        if r is None or r["variant"] != "original" or r["created_by_kind"] != "owner":
            raise ApiError(422, "validation_failed", fields={"file_ids": f"unknown file {fid}"},
                           message_fa=UNKNOWN_FA)  # fmt: skip
        if r["company_id"] != holding_id:
            raise ApiError(422, "validation_failed",
                           fields={"file_ids": "a file sent in a company's thread"},
                           message_fa=ELSEWHERE_FA)  # fmt: skip
    return [rows[f] for f in unique]


ORDER_FILES = 50  # the newest an order's report and briefs list


async def of_order(tx: Tx, order_id: UUID) -> list[dict[str, Any]]:
    """⟨1.18⟩ §36.3 an order's files (the owner's, from its session), newest first."""
    rows = await tx.all(
        FILE_SQL
        + """ JOIN owner.order_files o ON o.file_id = f.id
             WHERE o.order_id = :o ORDER BY o.added_at DESC, o.id LIMIT :l""",
        o=order_id,
        l=ORDER_FILES,
    )
    return [dict(r) for r in rows]


async def order_of_run(tx: Tx, run_id: str | None) -> UUID | None:
    """⟨1.18⟩ §36.3 the order a run works on (its work, up its parents and requests); None for a
    run without a work or a work outside any order. `tx` reads every company's rows."""
    if not run_id:
        return None
    work_id = await tx.scalar(
        "SELECT work_id FROM agents.runs WHERE id = CAST(:r AS uuid)", r=str(run_id)
    )
    if work_id is None:
        return None
    from hq_api.domain import order_report as OR

    ref = await OR.order_of_work(tx, work_id)
    if ref is None:
        return None
    order_id: UUID | None = await tx.scalar("SELECT id FROM owner.orders WHERE ref = :r", r=ref)
    return order_id


async def order_grant(tx: Tx, run_id: str | None, file_ids: list[UUID]) -> set[UUID]:
    """⟨1.18⟩ §36.3 which of `file_ids` (originals, or a variant of one: an image's copy for a
    model, a video's poster or frames) belong to the order the run works on: a run of the
    order's works reads them whatever its company; nothing else is granted."""
    if not file_ids:
        return set()
    order_id = await order_of_run(tx, run_id)
    if order_id is None:
        return set()
    rows = await tx.all(
        """SELECT f.id FROM files.files f
           JOIN owner.order_files o ON o.file_id = COALESCE(f.parent_id, f.id)
           WHERE o.order_id = :o AND f.id = ANY(:ids)""",
        o=order_id,
        ids=list(file_ids),
    )
    return {r["id"] for r in rows}


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
    tx: Tx, file_id: UUID, status: str, text: str | None, error: str | None, *, count: bool = True
) -> None:
    """The second transaction: `ready` (with or without text) or `failed`.
    `count`: this is an attempt of its own (the worker counted it at its start)."""
    await tx.exec(
        """UPDATE files.processing SET status = :st, text = :t, error = :e,
               attempts = attempts + CAST(:n AS int), updated_at = now()
           WHERE file_id = :f AND status = 'processing'""",
        f=file_id,
        st=status,
        t=text[:200_000] if text else None,
        e=error[:300] if error else None,
        n=1 if count else 0,
    )


async def extract_text(
    tx: Callable[[], AbstractAsyncContextManager[Tx]],
    file_id: UUID,
    path: Path,
    *,
    count: bool = True,
    mime: str | None = None,
) -> str:
    """A PDF's text from a child process (media.pdf_text), ⟨1.18⟩ a text or Markdown file's
    (`mime`), outside any transaction, then written in one of its own -> the status."""
    got = await media.document_text(path, mime)
    async with tx() as t:
        await document_done(t, file_id, got.status, got.text, got.error, count=count)
    return got.status
