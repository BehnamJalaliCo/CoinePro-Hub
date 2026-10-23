"""File integrity (prompt 14 §8, contract §23.0, §23.10, §23.12).

Every night one seventh of the archive's stored files is hashed again (the
slice of a file is fixed by its id, so over a week every file is checked);
`kind: weekly` (and `manual`) checks them all. Each run is an
`archive.fixity_runs` row {at, checked, failed: [ref], next_at}.

A mismatch, or a stored object that is missing, is a data-loss alarm: one
`urgent` notification (category data loss; the one urgent the archive ever
raises), the stream event `fixity.failed`, and a work item for the hub's
platform SRE. Rule-only (local hashing; no model, no outside call), so it
runs while the holding is locked; only the SRE's work item waits for the
launch (it is raised by the next run once the holding is unlocked).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from hq_api import audit, events
from hq_api.archive.common import SERVICE, J, dumps, holding
from hq_api.domain import gate

CHUNK = 1024 * 1024
SRE_ROLE = "hub_platform_sre"


def _hash(path: Any) -> str | None:
    d = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(CHUNK), b""):
                d.update(block)
    except OSError:
        return None
    return d.hexdigest()


def slice_of(now: datetime) -> int:
    return now.weekday()


async def run(hub: Any, txf: Any, kind: str = "nightly", now: datetime | None = None) -> dict[str, Any]:
    from hq_api.archive import clearance as CL
    from hq_api.domain import notify

    now = now or datetime.now(UTC)
    sl = slice_of(now) if kind == "nightly" else None
    started = time.monotonic()
    async with txf() as tx:
        await CL.full(tx)
        files = await tx.all(
            """SELECT f.id, f.storage_key, f.stored_sha256, f.name, r.ref
               FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
               WHERE f.destroyed_at IS NULL AND f.storage_key IS NOT NULL
                 AND (CAST(:s AS int) IS NULL OR mod(abs(hashtext(f.id::text)), 7) = :s)
               ORDER BY f.created_at""",
            s=sl,
        )
    failed: list[dict[str, Any]] = []
    for f in files:
        got = await asyncio.to_thread(_hash, hub.storage.local_path(f["storage_key"]))
        if got != f["stored_sha256"]:
            failed.append({"ref": f["ref"], "file_id": str(f["id"]), "name": f["name"],
                           "why": "missing" if got is None else "mismatch"})  # fmt: skip
    next_at = (now + timedelta(days=1)).replace(hour=3, minute=20, second=0, microsecond=0)
    async with txf() as tx:
        await CL.full(tx)
        h = await holding(tx)
        await tx.exec(
            """INSERT INTO archive.fixity_runs (company_id, at, kind, slice, checked, failed, seconds, next_at)
               VALUES (:co, :at, :k, :s, :n, CAST(:f AS jsonb), :sec, :nx)""",
            co=h["id"], at=now, k=kind, s=sl, n=len(files), f=dumps(failed),
            sec=round(time.monotonic() - started, 3), nx=next_at,
        )  # fmt: skip
        pushed = []
        if failed:
            refs = sorted({x["ref"] for x in failed})
            row = await notify.raise_notification(
                tx, company_id=h["id"], company_code=h["code"], level="urgent",
                title_fa=f"هشدار از دست رفتن داده: {len(failed)} فایل بایگانی با hash خود نمیخواند",
                body_fa=("دسته: از دست رفتن داده (data loss). " + "، ".join(refs[:20]))[:500],
                link_kind="archive_fixity", link_ref=refs[0], source_kind="service", source_code="archive-fixity",
            )  # fmt: skip
            pushed.append(row)
            await events.emit(tx, h["code"], "fixity.failed", refs[0], {"failed": len(failed), "refs": refs[:50]})
            await audit.record(
                tx, SERVICE, company_id=h["id"], action="archive.fixity_failed", action_class="A1",
                target_kind="archive_fixity", target_ref=refs[0], summary=f"{len(failed)} file(s): {', '.join(refs[:10])}"[:300],
            )  # fmt: skip
        sre_work = await _sre_item(tx, h)
    if pushed:
        await notify.deliver_pending(hub, [r["id"] for r in pushed if r.get("push_now")])
    return {"kind": kind, "slice": sl, "checked": len(files), "failed": failed, "sre_work": sre_work}


async def _sre_item(tx: Any, h: dict[str, Any]) -> str | None:
    """One work item for the platform SRE about failures it has not had yet
    (only while the holding is unlocked: nothing wakes an agent before)."""
    from hq_api.domain import work as W

    if await gate.holding_lock(tx) is not None:
        return None
    runs = await tx.all(
        """SELECT id, failed FROM archive.fixity_runs WHERE jsonb_array_length(failed) > 0
             AND at > now() - interval '14 days' ORDER BY at DESC LIMIT 20"""
    )
    refs = sorted({x["ref"] for r in runs for x in J(r["failed"], [])})
    if not refs:
        return None
    marker = "fixity:" + hashlib.sha256(",".join(refs).encode()).hexdigest()[:16]
    if await tx.scalar("SELECT 1 FROM work.work WHERE run_meta->>'archive_fixity' = :m", m=marker):
        return None
    sre = await tx.first(
        """SELECT e.code, e.company_id FROM core.employees e WHERE e.company_id = :co AND e.role = :r
             AND e.status = 'active' ORDER BY e.created_at LIMIT 1""",
        co=h["id"], r=SRE_ROLE,
    )  # fmt: skip
    if sre is None:
        return None
    w = await W.create(
        tx, SERVICE, company_id=h["id"], company_code=h["code"],
        title=f"بایگانی: {len(refs)} سند با hash ذخیره‌شده نمیخواند (از دست رفتن داده)",
        brief="The archive's fixity check found stored files that no longer match their SHA-256: "
        + ", ".join(refs[:50]) + ". Find out why (disk, restore, tampering) and restore them from the hourly "
        "backup (RUNBOOK §32); report what you found. Never change an archive row.",
        kind="one_off", priority="P1", assignee_code=sre["code"],
    )  # fmt: skip
    await tx.exec(
        "UPDATE work.work SET run_meta = COALESCE(run_meta, CAST('{}' AS jsonb)) || CAST(:m AS jsonb) WHERE id = :id",
        m=dumps({"archive_fixity": marker}), id=w["id"],
    )  # fmt: skip
    return str(w["ref"])


async def last(tx: Any) -> dict[str, Any]:
    row = await tx.first("SELECT * FROM archive.fixity_runs ORDER BY at DESC, id DESC LIMIT 1")
    if row is None:
        return {"at": None, "checked": 0, "failed": [], "next_at": None}
    return {
        "at": row["at"],
        "checked": row["checked"],
        "failed": sorted({x["ref"] for x in J(row["failed"], [])}),
        "next_at": row["next_at"],
        "kind": row["kind"],
    }
