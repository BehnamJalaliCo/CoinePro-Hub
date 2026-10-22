"""The media worker's brand tracer (prompt 9.1 §2, contract §18.14).

brand_trace   one `processing` brand version: the owner's logo traced by
              hq_api.brand_trace in a child process (no network, 384 MiB of
              address space, 50 s of CPU, a 60 s deadline; the worker runs
              one such child at a time), then `proposed` or `failed` with its
              reason, an audit row and `brand.updated` on the stream.
Code only: no model is called and nothing leaves the hub. Each attempt is
counted when it starts; a version that used MAX_ATTEMPTS fails (`stopped`).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from temporalio import activity

from hq_api import brand
from hq_api.domain import brands as BR
from hq_api.hub import Hub
from hq_common import untrusted

log = logging.getLogger("hq_api.worker.brand")
# Measured: a 4096 x 4096 PNG peaks at ~190 MiB resident, ~300 MiB of address
# space (docs/ops/reports/PROMPT_09_1.md); the full profile's worker (512m)
# holds its own ~100 MiB and this child.
LIMITS = untrusted.Limits(memory_mb=384, cpu_s=50, deadline_s=60.0, write_mb=0, network=False)
JOB = "hq_api.brand_trace:trace_job"


def reason_of(got: untrusted.Outcome) -> str:
    """The status_reason a stopped or refused child leaves."""
    if got.error and got.error.startswith("Refused: "):
        why = got.error.removeprefix("Refused: ").strip()
        return why if why in brand.REASONS else "unreadable"
    if got.killed == "memory":
        return "too_large"
    if got.killed:
        return "stopped"
    return "unreadable"


class BrandActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx  # a callable opening a transaction over every company

    def all(self) -> list[Any]:
        return [self.brand_trace]

    @activity.defn(name="brand_trace")
    async def brand_trace(self, brand_id: str) -> dict[str, Any]:
        bid = UUID(brand_id)
        async with self._tx() as tx:
            r = await BR.load_id(tx, bid, lock=True)
            if r is None or r["state"] != "processing":
                return {"brand": brand_id, "skipped": r["state"] if r else "missing"}
            attempt = await tx.scalar(
                """UPDATE org.company_brands SET attempts = attempts + 1, updated_at = now()
                   WHERE id = :id RETURNING attempts""",
                id=bid,
            )
            key = await tx.scalar(
                "SELECT storage_key FROM files.files WHERE id = :f", f=r["file_id"]
            )
            mark_checks = (
                await BR.mark_checks(tx, r["company_id"]) if r["part"] == "wordmark" else None
            )
        if int(attempt or 0) > BR.MAX_ATTEMPTS or key is None:
            async with self._tx() as tx:
                r = await BR.load_id(tx, bid, lock=True)
                if r is not None and r["state"] == "processing":
                    await BR.failed(tx, r, "stopped" if key else "unreadable")
            return {"brand": brand_id, "error": "attempts" if key else "file"}
        path = self.hub.storage.local_path(key)
        got = await untrusted.run(JOB, kwargs=BR.job_kwargs(r, path), limits=LIMITS)
        async with self._tx() as tx:
            r = await BR.load_id(tx, bid, lock=True)
            if r is None or r["state"] != "processing":
                return {"brand": brand_id, "skipped": r["state"] if r else "missing"}
            if got.ok:
                try:
                    cols = BR.compose(r, got.value, mark_checks)
                except (ValueError, KeyError, TypeError) as exc:
                    reason = str(exc) if str(exc) in brand.REASONS else "invalid_path"
                    await BR.failed(tx, r, reason)
                    return {"brand": brand_id, "state": "failed", "reason": reason}
                out = await BR.proposed(tx, r, cols)
                log.info("brand traced", extra={"brand": brand_id, "usage": got.usage})
                return {"brand": brand_id, "state": out["state"], "usage": got.usage}
            reason = reason_of(got)
            log.info("brand refused", extra={"brand": brand_id, "reason": got.reason})
            await BR.failed(tx, r, reason)
            return {"brand": brand_id, "state": "failed", "reason": reason, "usage": got.usage}
