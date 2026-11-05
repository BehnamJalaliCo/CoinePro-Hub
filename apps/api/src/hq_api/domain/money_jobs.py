"""⟨1.15⟩ Prompt 24 (contract §33.2): what the worker's schedules do with the payments.

read_due        every `read.every_minutes` (hq-money-read): each enabled source one step: a chain
                source is scanned through egress (`chain-read`), a ledger source collects its
                finished job and queues the next one on the company's runner. A failure is
                recorded on the source (a plain Persian reason), never raised.
reconcile_all   daily (hq-money-reconcile): every company with a source is reconciled and its new
                problems alerted (the company's CEO and FIN manager; the owner only for a
                `ledger_only` above the critical amount).
read_one        the owner's explicit read of one source (POST /payment-sources/{id}/read), then
                the company's reconcile; a chain that answers badly is the owner's 502.
weekly          Saturday (hq-money-weekly): the owner's one weekly line, every company together.

Nothing here moves money, signs anything or changes a company system; nothing runs while the
holding (or the company) is locked.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.domain import gate
from hq_api.domain import payments as P
from hq_api.domain import payments_chain as PC
from hq_api.domain import payments_reconcile as PR
from hq_api.errors import ApiError

log = logging.getLogger("hq_api.money")


async def _sources(hub: Any, source_id: UUID | None = None) -> list[dict[str, Any]]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if source_id is not None:
            return [await P.load_source(tx, source_id)]
        rows: list[dict[str, Any]] = await tx.all(
            P.SOURCE_SQL + " WHERE s.enabled ORDER BY s.last_read_at NULLS FIRST"
        )
        return rows


async def read_ledger_step(hub: Any, src: dict[str, Any]) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        locked = await gate.automation_lock(tx, src["company_id"])
        if locked:
            return {"skipped": locked}
        src = await P.load_source(tx, src["id"], lock=True)
        try:
            async with tx.conn.begin_nested():
                out = await P.read_ledger(tx, src)
        except ApiError as exc:  # a locked company refuses a job: recorded, never raised
            out = {"error": exc.message_fa or exc.code}
            await P.mark(tx, src, error_fa=str(out["error"]), read=False)
        await P.emit_read(
            tx, src, queued=bool(out.get("queued")), error=out.get("error") is not None
        )
        return out


async def read_chain_step(hub: Any, src: dict[str, Any]) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        locked = await gate.automation_lock(tx, src["company_id"])
    if locked:
        return {"skipped": locked}
    try:
        out = await PC.read_chain(hub, src["id"])
    except PC.ChainReadError as exc:
        out = {"error": exc.code, "reason_fa": exc.reason_fa}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await P.emit_read(tx, src, transfers=int(out.get("transfers") or 0), error="error" in out)
    return out


async def read_due(hub: Any) -> dict[str, Any]:
    out = {"ledger": 0, "chain": 0, "errors": 0, "skipped": 0}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await gate.holding_lock(tx) is not None:
            return {**out, "locked": 1}
    for src in await _sources(hub):
        step = read_ledger_step if src["kind"] == "ledger" else read_chain_step
        try:
            got = await step(hub, src)
        except Exception:
            log.exception("payment source read failed")
            got = {"error": "internal"}
        if "skipped" in got:
            out["skipped"] += 1
        elif got.get("error"):
            out["errors"] += 1
        else:
            out[src["kind"]] += 1
    return out


async def reconcile_company(hub: Any, company_id: UUID, *, alerts: bool = True) -> dict[str, Any]:
    """One company's reconcile (and its alerts) in one transaction; the critical notifications
    are pushed after the commit."""
    from hq_api.domain import notify

    company = await hub.companies.by_id(company_id)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        counts = await PR.reconcile(tx, company_id)
        told: dict[str, Any] = {"alerts": 0, "critical": 0, "push": []}
        if alerts:
            told = await PR.raise_alerts(hub, tx, company)
    if told["push"]:
        try:
            await notify.deliver_pending(hub, told["push"])
        except Exception:  # noqa: BLE001 - stored; the digest delivers it
            log.warning("critical payment notification not pushed")
    return {"counts": counts, "alerts": told["alerts"], "critical": told["critical"]}


async def reconcile_all(hub: Any) -> dict[str, Any]:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await gate.holding_lock(tx) is not None:
            return {"locked": 1}
        ids = [
            r["company_id"]
            for r in await tx.all("SELECT DISTINCT company_id FROM money.payment_sources")
        ]
    out = {"companies": 0, "alerts": 0, "critical": 0}
    for co in ids:
        try:
            got = await reconcile_company(hub, co)
        except Exception:
            log.exception("reconcile failed")
            continue
        out["companies"] += 1
        out["alerts"] += got["alerts"]
        out["critical"] += got["critical"]
    return out


async def read_one(hub: Any, source_id: UUID) -> dict[str, Any]:
    """The worker's side of the owner's chain read: the scan, then the company's reconcile.
    {"transfers", "pages", "done"} or {"error": code, "reason_fa"}."""
    src = (await _sources(hub, source_id))[0]
    out = await read_chain_step(hub, src)
    if "error" not in out and "skipped" not in out:
        await reconcile_company(hub, src["company_id"])
    return out


async def weekly(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The owner's weekly line (a `report` of the revenue domain): every company together, from
    the stored statuses of the last 7 days."""
    from hq_api.domain import notify

    now = now or datetime.now(UTC)
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if await gate.holding_lock(tx) is not None:
            return {"locked": 1}
        if not await tx.scalar("SELECT EXISTS (SELECT 1 FROM money.payment_sources)"):
            return {"sent": 0}
        line = await PR.weekly_line(tx, now - timedelta(days=7))
        row = await notify.raise_notification(
            tx,
            company_id=holding.id,
            company_code=holding.code,
            level="report",
            title_fa="پرداخت‌های هفته",
            body_fa=line,
            source_kind="system",
            source_code="money",
            domain="revenue",
        )
    return {"sent": 1, "id": str(row["id"])}


async def read_now(hub: Any, source_id: UUID) -> dict[str, Any]:
    """The owner's chain read: on the worker (the one process on the egress network), awaited;
    in a process without Temporal (the tests) it runs right here."""
    import uuid

    client = getattr(hub, "temporal", None)
    if client is None:
        return await read_one(hub, source_id)
    try:
        out: dict[str, Any] = await client.execute_workflow(
            "MoneyReadSource",
            str(source_id),
            id=f"money-read-{source_id}-{uuid.uuid4().hex[:8]}",
            task_queue=hub.settings.task_queue,
            execution_timeout=timedelta(minutes=10),
        )
    except Exception:  # noqa: BLE001 - the owner sees a plain reason
        log.warning("the chain read did not run on the worker")
        return {"error": "egress_down", "reason_fa": PC.ERROR_FA["egress_down"]}
    return out
