"""Workflows of prompt 14, the archive (deterministic; the activities are in
archive_activities.py and are rule-only: no model, no outside call)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name="ArchiveDaily")
class ArchiveDaily:
    """Daily: retention, reminders, the destroy queue, the weekly report (prompt 14 §5, §6)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "archive_daily", start_to_close_timeout=timedelta(minutes=20), retry_policy=TRIES
        )
        return out


@workflow.defn(name="ArchiveFixity")
class ArchiveFixity:
    """Nightly: one seventh of the stored files hashed again (prompt 14 §8)."""

    @workflow.run
    async def run(self, kind: str = "nightly") -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "archive_fixity", kind, start_to_close_timeout=timedelta(hours=2), retry_policy=TRIES
        )
        return out


@workflow.defn(name="ArchiveOcrQueue")
class ArchiveOcrQueue:
    """Every 2 minutes: the OCR queue, one job at a time (prompt 14 §4)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "archive_ocr_queue",
            start_to_close_timeout=timedelta(minutes=14),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return out


@workflow.defn(name="ArchiveOcr")
class ArchiveOcr:
    """One file's OCR for an archive intake (the api waits for it)."""

    @workflow.run
    async def run(self, storage_key: str, mime: str) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "archive_ocr_file",
            args=[storage_key, mime],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return out


@workflow.defn(name="ArchiveSources")
class ArchiveSources:
    """Every 15 minutes: what the hub files by itself (prompt 14 §7)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "archive_sources", start_to_close_timeout=timedelta(minutes=12), retry_policy=TRIES
        )
        return out


P14_WORKFLOWS = [ArchiveDaily, ArchiveFixity, ArchiveOcrQueue, ArchiveOcr, ArchiveSources]
