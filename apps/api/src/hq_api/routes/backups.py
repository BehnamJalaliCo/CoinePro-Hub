"""Backups (contract §18.9, prompt 07 §1): read-only for the owner (and, through
the Tool Gateway's `backups.status`, the overseer and the platform SRE). The
backups run on the host; nothing here can start, change or restore one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import backups as B
from hq_api.errors import responses
from hq_api.schemas import Page

router = APIRouter(tags=["backups"])
E = responses(401, 403)
Destination = Literal["local", "gdrive", "hetzner"]


class Hourly(BaseModel):
    last_at: str | None
    next_at: str | None
    ok: bool | None
    snapshot: str | None
    size_bytes: int | None
    last_ok_at: str | None = None
    error: str | None = None
    stale: bool = True


class Wal(BaseModel):
    last_archived_at: str | None
    lag_s: int | None
    failed_count: int | None = None
    # ⟨1.4.5⟩ 7.1 §1.1: the last failure is newer than the last success, or more
    # than 5 segments wait; then the hourly run is not ok and the owner is told at once
    failing: bool | None = None
    ready_count: int | None = None


class BaseBackup(BaseModel):
    last_at: str | None
    count: int


class DestinationStatus(BaseModel):
    key: Destination
    configured: bool
    last_ok_at: str | None
    used_bytes: int | None
    quota_bytes: int | None
    ok: bool | None = None
    error: str | None = None


class Retention(BaseModel):
    hourly: int
    daily: int
    weekly: int
    monthly: int
    yearly: int


class RestoreTest(BaseModel):
    last_at: str | None
    ok: bool | None
    duration_s: int | None
    notes: str | None
    source: Destination | None = None
    pitr_target: str | None = None


class OpenbaoSnapshot(BaseModel):
    last_at: str | None
    ok: bool | None
    configured: bool = False


class Check(BaseModel):
    last_at: str | None
    ok: bool | None


class BackupStatus(BaseModel):
    """⟨1.4⟩ §18.9 BackupStatus (+ wal.failed_count, base_backup, check,
    hourly.last_ok_at/error/stale, the destination's last ok/error)."""

    hourly: Hourly
    wal: Wal
    base_backup: BaseBackup | None
    destinations: list[DestinationStatus]
    retention: Retention
    restore_test: RestoreTest
    openbao_snapshot: OpenbaoSnapshot
    check: Check | None
    encryption: str


class Snapshot(BaseModel):
    id: str
    destination: Destination
    time: datetime
    size_bytes: int | None
    tags: list[str]


@router.get("/backups/status", response_model=BackupStatus, responses=E)
async def backup_status(ctx: Ctx = Depends(owner_ctx)) -> BackupStatus:
    """The hourly backup, the WAL archive, each destination, the retention, the
    last restore test and the OpenBao snapshot (metadata only)."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        return BackupStatus(**await B.status(tx, holding.id))


@router.get("/backups/snapshots", response_model=Page[Snapshot], responses=E)
async def backup_snapshots(
    destination: Destination | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    ctx: Ctx = Depends(owner_ctx),
) -> Page[Snapshot]:
    """The snapshots each repository lists now, newest first."""
    holding = await ctx.hub.companies.holding()
    async with ctx.tx() as tx:
        rows = await tx.all(
            """SELECT snapshot_id AS id, destination, time, size_bytes, tags FROM backup.snapshots
               WHERE company_id = :co AND (CAST(:d AS text) IS NULL OR destination = :d)
               ORDER BY time DESC, destination LIMIT :n""",
            co=holding.id,
            d=destination,
            n=limit,
        )
    return Page[Snapshot](items=[Snapshot(**r) for r in rows])
