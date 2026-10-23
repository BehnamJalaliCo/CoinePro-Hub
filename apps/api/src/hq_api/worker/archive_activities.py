"""Temporal activities of prompt 14 (the archive).

archive_daily     daily 04:30 (owner zone): the retention sweep, the due-date
                  reminders, the destroy queue, and on the first day of the
                  owner's week the archivist's weekly gap report
archive_fixity    nightly 03:20 (owner zone): one seventh of the stored files
                  hashed again (all of them over a week)
archive_ocr_queue every 2 minutes: one OCR job at a time for files still
                  waiting for their text (nothing while the `ocr` profile is off)
archive_ocr_file  the api's intake asks for one image's or scan's OCR and waits
archive_sources   every 15 minutes: the system sources' new events, filed

All of them are rule-only: no model and no outside service (OCR is the
hub's own Tesseract on an internal network without internet). So they run
while the holding is locked, which is what keeps the archive honest before the
launch (fixity alarms, reminders to the owner, disposal cards for the owner).
What would wake an agent is gated inside them (hq_api.domain.gate): a work
item for the archivist, a role's reminder or the platform SRE's item waits
until the holding (and the record's company) is unlocked; no run is queued.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from hq_api.archive import fixity as FX
from hq_api.archive import ocr as OCR
from hq_api.archive import reminders as RM
from hq_api.archive import retention as RT
from hq_api.archive import scan
from hq_api.archive import sources as SRC
from hq_api.archive import store as ST
from hq_api.archive.common import wide_txf
from hq_api.domain import gate
from hq_api.hub import Hub

log = logging.getLogger("hq_api.worker.archive")
OCR_PER_PASS = 5
OCR_ATTEMPTS = 3


class ArchiveActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = wide_txf(hub)  # every company, full clearance (the hub's own jobs)
        del tx

    def all(self) -> list[Any]:
        return [
            self.archive_daily,
            self.archive_fixity,
            self.archive_ocr_queue,
            self.archive_ocr_file,
            self.archive_sources,
        ]

    @activity.defn(name="archive_daily")
    async def archive_daily(self) -> dict[str, Any]:
        out: dict[str, Any] = {"retention": await RT.sweep(self.hub, self._tx)}
        out["reminders"] = await RM.run(self.hub, self._tx)
        out["destroyed"] = await RT.destroy_queued(self.hub, self._tx)
        out["weekly_report"] = await weekly_report(self.hub, self._tx)
        return out

    @activity.defn(name="archive_fixity")
    async def archive_fixity(self, kind: str = "nightly") -> dict[str, Any]:
        res = await FX.run(
            self.hub, self._tx, kind if kind in ("nightly", "weekly", "manual") else "nightly"
        )
        return {**res, "failed": len(res["failed"])}

    @activity.defn(name="archive_ocr_file")
    async def archive_ocr_file(self, storage_key: str, mime: str) -> dict[str, Any]:
        data = await self.hub.storage.get(storage_key)
        return await OCR.run(self.hub.settings, data, mime)

    @activity.defn(name="archive_ocr_queue")
    async def archive_ocr_queue(self) -> dict[str, Any]:
        return await ocr_queue(self.hub, self._tx)

    @activity.defn(name="archive_sources")
    async def archive_sources(self) -> dict[str, Any]:
        return await SRC.run(self.hub, self._tx)


async def ocr_queue(hub: Any, txf: Any) -> dict[str, Any]:
    """One file at a time: its OCR, the secret scan of what it found, its text."""
    from hq_api.archive import records as R
    from hq_api.domain import notify

    out: dict[str, Any] = {"done": 0, "failed": 0, "quarantined": 0, "state": "idle"}
    for _ in range(OCR_PER_PASS):
        async with txf() as tx:
            f = await tx.first(
                """SELECT f.*, r.ref, r.company_id AS rco FROM archive.record_files f
                   JOIN archive.records r ON r.id = f.record_id
                   WHERE f.ocr_wanted AND f.destroyed_at IS NULL AND NOT f.quarantined
                   ORDER BY f.created_at LIMIT 1 FOR UPDATE OF f SKIP LOCKED"""
            )
        if f is None:
            break
        try:
            data = await ST.read(hub, f)
        except Exception:  # noqa: BLE001 - unreadable here: fixity will say why
            async with txf() as tx:
                await tx.exec(
                    "UPDATE archive.record_files SET ocr_wanted = false WHERE id = :id", id=f["id"]
                )
            continue
        res = await OCR.run(hub.settings, data, f["mime"])
        state = res.get("state")
        if state in ("off", "busy"):
            out["state"] = str(state)  # the profile is off, or the service is busy: later
            break
        async with txf() as tx:
            if state != "ok":
                n = int(f["ocr_attempts"]) + 1
                await tx.exec(
                    """UPDATE archive.record_files SET ocr_attempts = :n,
                           ocr_wanted = :n < :max, text_state = CASE WHEN :n >= :max THEN 'failed' ELSE text_state END
                       WHERE id = :id""",
                    id=f["id"],
                    n=n,
                    max=OCR_ATTEMPTS,
                )
                out["failed"] += 1
                continue
            got = OCR.as_text(res, ST.LOW_CONFIDENCE)
            if scan.kinds(got["text"]):
                # Found after the file was kept (the profile was off at intake):
                # never indexed, never served; the owner decides (a disposal card).
                await tx.exec(
                    """UPDATE archive.record_files SET quarantined = true, ocr_wanted = false, text = NULL,
                           text_state = 'failed' WHERE id = :id""",
                    id=f["id"],
                )
                h = await tx.one("SELECT code FROM core.companies WHERE id = :c", c=f["rco"])
                await notify.raise_notification(
                    tx,
                    company_id=f["rco"],
                    company_code=h["code"],
                    level="report",
                    title_fa=f"بایگانی {f['ref']}: در متن یک فایل الگوی رمز پیدا شد",
                    body_fa="این فایل دیگر نمایش داده و جستجو نمیشود؛ امحای آن با تصمیم مدیر کل است.",
                    link_kind="archive_record",
                    link_ref=f["ref"],
                    source_kind="service",
                    source_code="archive",
                )
                out["quarantined"] += 1
            else:
                await tx.exec(
                    """UPDATE archive.record_files SET text = :t, text_state = 'ocr', ocr_confidence = :c,
                           low_conf_pages = :lp, pages = COALESCE(pages, :p), ocr_wanted = false WHERE id = :id""",
                    id=f["id"],
                    t=got["text"],
                    c=got["confidence"],
                    lp=got["low"],
                    p=got["pages"],
                )
                out["done"] += 1
            r = await R.load(tx, f["ref"])
            await R.search_vectors(tx, r, await R.class_fields(tx, r))
    return out


async def weekly_report(hub: Any, txf: Any, now: datetime | None = None) -> str | None:
    """On the first day of the owner's (Jalali) week, Saturday: one work item
    for the archivist, the weekly gap report. Only while the holding is
    unlocked (it wakes an agent)."""
    now = now or datetime.now(UTC)
    if now.weekday() != 5:  # Saturday
        return None
    async with txf() as tx:
        if await gate.holding_lock(tx) is not None:
            return None
        key = f"archive-weekly:{now.date().isoformat()}"
        if await tx.scalar("SELECT 1 FROM work.work WHERE run_meta->>'archive_weekly' = :k", k=key):
            return None
        drafts = await tx.scalar("SELECT count(*) FROM archive.records WHERE state = 'draft'")
        ref = await RT.archivist_work(
            tx,
            "گزارش هفتگی بایگانی",
            "The weekly report (your charter): drafts waiting to be filed or sealed, records missing a required "
            "field, what expires in the next 90 days nearest first, retention reviews due, fixity failures. "
            f"Drafts now: {drafts}. Use archive.search and archive.read; deliver it in Persian, short.",
        )
        if ref:
            await tx.exec(
                """UPDATE work.work SET run_meta = COALESCE(run_meta, CAST('{}' AS jsonb)) || CAST(:m AS jsonb)
                   WHERE ref = :r""",
                m=f'{{"archive_weekly": "{key}"}}',
                r=ref,
            )
        return ref
