"""⟨1.36⟩ §58.4 What stays after a publication, and what goes.

The owner, 2026-11-13: «میز انتشار … حجمش زیاد میشه … کاور اصلی و ریلز اصلی و متن کپشن بایگانی بشه و
بقیه … پاک بشه دیسک رو سنگین نکنه».

    kept        when IG-Hub confirms a publication (session_publish.after_job), its output gets one
                files.publish_keep row: the package (the published file, its cover, caption.txt)
                and the time. The package is filed to the archive (§23) as the publication's record
                (an archive record of its own, its own copy of the three files, a draft until the
                archivist classes it: no class of the schema takes a video); a filing that does not
                go through now is done by the next sweep.
    the sweep   daily (the archive's daily job): an output published PUBLISH_SWEEP_HOURS ago or more
                loses every other file of it and of the earlier versions of its revision chain
                (§57.6: drafts, other renders, notes, the comment and topic files once used, the
                JPEG copies its publish jobs carried) unless the owner opened or downloaded it since
                the publication (files.opened), or anything else uses it (another output, a
                session's files, a message, an archive record …): files.publish_sweep decides by
                code. One audit row per output (`files.publish_sweep`, the count and bytes freed).
                A failed or cancelled publication has no row: it deletes nothing.

Rule-based, no model, no outside call.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import order_report as OR
from hq_api.principal import Principal

log = logging.getLogger("hq_api.publish_keep")

SERVICE = Principal(kind="service", code="publish_sweep", role="service")
SWEEP_HOURS = 72
SWEEP_LIMIT = 50  # outputs a pass
FILE_DAYS = 14  # a package not filed by then is not tried again (its files may be gone)
CHAIN_MAX = 20  # earlier versions followed back
CAPTION_NAMES = ("caption.txt", "caption.md")
TEXT_MAX = 64 * 1024
RECORD_TITLE_FA = "انتشار: {title}"


class Kept(BaseModel):
    """What the publish desk's `done` card says of it: filed to the archive, and what the sweep
    freed (null until it ran)."""

    archived: bool = False
    freed_bytes: int | None = None


async def of_outputs(tx: Tx, refs: list[str]) -> dict[str, Kept]:
    if not refs:
        return {}
    rows = await tx.all(
        "SELECT output, record_ref, freed_bytes FROM files.publish_keep WHERE output = ANY(:r)",
        r=refs,
    )
    return {
        str(r["output"]): Kept(
            archived=r["record_ref"] is not None,
            freed_bytes=int(r["freed_bytes"]) if r["freed_bytes"] is not None else None,
        )
        for r in rows
    }


def _package(args: dict[str, Any], files: list[dict[str, Any]]) -> list[str]:
    """The package of a publication among the output's own files: the file it published (and a
    carousel's others), the cover it carried, the caption's text file."""
    s = args.get("session") or {}
    ids = {str(f["id"]) for f in files}
    out: list[str] = []
    main = str(s.get("file_id") or "")
    if main in ids:
        out.append(main)
    for x in args.get("files") or []:
        fid = str((x or {}).get("file_id") or "")
        if fid in ids and fid not in out:
            out.append(fid)
    cover = str(s.get("cover_name") or "")
    for f in files:
        name = str(f["name"] or "")
        named = (cover and name == cover) or name.strip().lower() in CAPTION_NAMES
        if named and str(f["id"]) not in out:
            out.append(str(f["id"]))
    return out


async def on_published(tx: Tx, j: dict[str, Any]) -> str | None:
    """IG-Hub confirmed a publication (its job's view is `published`): the output's row, once
    (a later confirmation of the same output, a story beside the reel, changes nothing).
    Answers the output's ref when the row was made now."""
    from hq_api.domain import session_publish as SPB

    args = OR._j(j["args"]) or {}
    out = str((args.get("session") or {}).get("output") or "")
    if not out:
        return None
    d = await tx.first(SPB.OUTPUT_SQL + " WHERE d.ref = :r", r=out)
    if d is None:
        return None
    files = [dict(f) for f in await SPB._files(tx, dict(d))]
    made = await tx.scalar(
        """INSERT INTO files.publish_keep (output, company_id, job_id, published_at, kept)
           VALUES (:o, :co, :j, COALESCE(CAST(:at AS timestamptz), now()), CAST(:k AS uuid[]))
           ON CONFLICT (output) DO NOTHING RETURNING output""",
        o=out,
        co=d["company_id"],
        j=j["id"],
        at=j.get("finished_at"),
        k=_package(args, files),
    )
    return str(made) if made else None


async def _caption_text(hub: Any, f: dict[str, Any]) -> str | None:
    if not str(f["mime"]).startswith("text/") or int(f["size"] or 0) > TEXT_MAX:
        return None

    def read() -> str:
        with open(hub.storage.local_path(str(f["storage_key"])), "rb") as fh:
            return fh.read(TEXT_MAX).decode("utf-8", errors="replace")

    try:
        return (await asyncio.to_thread(read)).replace("﻿", "").strip() or None
    except OSError:
        return None


async def file_to_archive(hub: Any, output: str) -> str | None:
    """The package filed as the publication's record (its own copy of each file); the same
    record on every call. None when there is nothing to file (no row, no file left)."""
    from hq_api.archive import clearance as CL
    from hq_api.archive import records as R
    from hq_api.archive import store as ST

    scope = await hub.companies.ids()
    async with hub.db.tx(scope) as tx:
        row = await tx.first("SELECT * FROM files.publish_keep WHERE output = :o", o=output)
        if row is None or row["record_ref"]:
            return str(row["record_ref"]) if row is not None and row["record_ref"] else None
        files = [
            dict(f)
            for f in await tx.all(
                """SELECT id, name, mime, size, sha256, storage_key FROM files.files
                   WHERE id = ANY(CAST(:ids AS uuid[])) ORDER BY created_at, name""",
                ids=[str(x) for x in row["kept"] or []],
            )
        ]
        title = await tx.scalar("SELECT title FROM cartable.deliverables WHERE ref = :r", r=output)
        await CL.full(tx)
        lv = await R.resolve_level(tx, None, None, None)
    if not files:
        return None
    items = []
    for f in files:
        text = await _caption_text(hub, f)
        items.append(
            ST.Intake(
                file_id=uuid.uuid4(),
                name=str(f["name"]),
                mime=str(f["mime"]),
                size=int(f["size"] or 0),
                sha256=str(f["sha256"]),
                storage_key=str(f["storage_key"]),
                pages=None,
                text_state="text_layer" if text else "none",
                text=text,
                ocr_confidence=None,
            )
        )
    stored = await ST.ingest(hub, items, encrypt_it=bool(lv["encrypt"]))
    try:
        async with hub.db.tx(scope) as tx:
            await CL.full(tx)
            await tx.exec(
                "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"publish_keep:{output}"
            )
            again = await tx.scalar(
                "SELECT record_ref FROM files.publish_keep WHERE output = :o", o=output
            )
            if again:
                await ST.discard(hub, stored)
                return str(again)
            co = dict(
                await tx.one(
                    "SELECT id, code, kind FROM core.companies WHERE id = :c", c=row["company_id"]
                )
            )
            folder = await R.default_folder(tx, co["id"], co["code"], None)
            r = await R.create(
                tx,
                SERVICE,
                scope=co,
                cls=None,
                title_fa=RECORD_TITLE_FA.format(title=str(title or output))[:300],
                metadata={},
                lv=lv,
                folder=folder,
                stored=stored,
                parties=None,
                links=[{"kind": "about", "to": {"kind": "deliverable", "ref": output}}],
                # no class of the schema takes a video yet: the record stays the archive's draft
                # (kept like any; the archivist may class and file it)
                file_now=False,
                source_kind="system",
                source_ref=f"publication:{output}",
            )
            await tx.exec(
                "UPDATE files.publish_keep SET record_ref = :r WHERE output = :o",
                r=r["ref"],
                o=output,
            )
            return str(r["ref"])
    except BaseException:
        await ST.discard(hub, stored)
        raise


async def after_published(hub: Any, output: str) -> None:
    """After the confirming transaction: the filing, which never fails the publication's end
    (the sweep files what this missed)."""
    try:
        await file_to_archive(hub, output)
    except Exception:
        log.warning(
            "the publication's package was not filed yet", extra={"output": output}, exc_info=True
        )


# ------------------------------------------------------------------ the sweep --
async def chain_of(tx: Tx, output: str) -> list[str]:
    """The output and the earlier versions it revises (§57.6 `revision_of`), newest first."""
    out = [output]
    cur = output
    for _ in range(CHAIN_MAX):
        prev = await tx.scalar(
            "SELECT produced_with ->> 'revision_of' FROM cartable.deliverables WHERE ref = :r",
            r=cur,
        )
        if not prev or prev in out:
            break
        out.append(str(prev))
        cur = str(prev)
    return out


async def _candidates(tx: Tx, chain: list[str]) -> list[str]:
    """Every file of the chain's outputs and of the publish jobs that carried them."""
    rows = await tx.all(
        """SELECT DISTINCT unnest(attachments)::text AS id FROM cartable.deliverables
           WHERE ref = ANY(:c)""",
        c=chain,
    )
    ids = [str(r["id"]) for r in rows]
    jobs = await tx.all(
        """SELECT DISTINCT x ->> 'file_id' AS id FROM infra.server_jobs j
           CROSS JOIN LATERAL jsonb_array_elements(COALESCE(j.args -> 'files', '[]'::jsonb)) x
           WHERE j.kind = 'publish' AND j.args -> 'session' ->> 'output' = ANY(:c)""",
        c=chain,
    )
    ids += [str(r["id"]) for r in jobs if r["id"]]
    return list(dict.fromkeys(ids))


async def sweep_one(tx: Tx, row: dict[str, Any]) -> dict[str, int]:
    output = str(row["output"])
    chain = await chain_of(tx, output)
    kept = {str(x) for x in row["kept"] or []}
    ids = [i for i in await _candidates(tx, chain) if i not in kept]
    got = OR._j(
        await tx.scalar(
            """SELECT files.publish_sweep(:o, CAST(:ids AS uuid[]), CAST(:c AS text[]),
                                          CAST(:since AS timestamptz))""",
            o=output,
            ids=ids,
            c=chain,
            since=row["published_at"],
        )
    ) or {"files": 0, "bytes": 0}
    n, freed = int(got.get("files") or 0), int(got.get("bytes") or 0)
    await tx.exec(
        """UPDATE files.publish_keep SET swept_at = now(), swept_files = :n, freed_bytes = :b
           WHERE output = :o""",
        n=n,
        b=freed,
        o=output,
    )
    await audit.record(
        tx,
        SERVICE,
        company_id=row["company_id"],
        action="files.publish_sweep",
        action_class="A1",
        target_kind="deliverable",
        target_ref=output,
        summary=f"{n} files, {freed} bytes freed; kept {len(kept)} (archive "
        f"{row['record_ref'] or 'pending'}); chain {', '.join(chain)}"[:500],
    )
    return {"files": n, "bytes": freed}


async def sweep(hub: Any, txf: Any, now: datetime | None = None) -> dict[str, int]:
    """The daily pass: what is not filed yet is filed, then each output published
    SWEEP_HOURS ago or more is swept once (each in its own transaction)."""
    out = {"filed": 0, "outputs": 0, "files": 0, "bytes": 0}
    async with txf() as tx:
        unfiled = await tx.all(
            """SELECT output FROM files.publish_keep WHERE record_ref IS NULL
                 AND published_at > now() - make_interval(days => :d)
               ORDER BY published_at LIMIT :n""",
            d=FILE_DAYS,
            n=SWEEP_LIMIT,
        )
    for r in unfiled:
        try:
            if await file_to_archive(hub, str(r["output"])):
                out["filed"] += 1
        except Exception:
            log.warning(
                "a publication's package was not filed",
                extra={"output": r["output"]},
                exc_info=True,
            )
    async with txf() as tx:
        due = await tx.all(
            """SELECT output FROM files.publish_keep WHERE swept_at IS NULL
                 AND published_at <= COALESCE(CAST(:now AS timestamptz), now())
                                     - make_interval(hours => :h)
               ORDER BY published_at LIMIT :n""",
            now=now,
            h=SWEEP_HOURS,
            n=SWEEP_LIMIT,
        )
    for r in due:
        try:
            async with txf() as tx:
                row = await tx.first(
                    """SELECT * FROM files.publish_keep WHERE output = :o AND swept_at IS NULL
                       FOR UPDATE""",
                    o=r["output"],
                )
                if row is None:
                    continue
                got = await sweep_one(tx, dict(row))
            out["outputs"] += 1
            out["files"] += got["files"]
            out["bytes"] += got["bytes"]
        except Exception:  # noqa: BLE001 - one output never stops the pass
            log.warning("a published output was not swept", extra={"output": r["output"]})
    return out
