"""`python -m hq_api.ops_uncap_orders` (the api or worker container, once at the deploy of W11):
the owner, 2026-11-08: «کلا بودجه رو سقفشو بردار … همش برای یه کاری باید کار بخوابه، روشم میزنم عمل
نمیکنه».

From that deploy on, a work of an owner's order is made without a token budget (routes/orders,
routes/internal). This one-off brings the orders already open in line: every open work (queued,
in_progress, waiting) of an open order (its report not ended) loses its token budget
(`budget_tokens` NULL; a `waiting` one is `in_progress` again) and each such order's holder is
woken once, so a session that sat on «بودجه کم است» goes on. Idempotent: a second run finds nothing
to change. Prints what it did, in English, never a secret. `--dry-run` prints the counts only.

    docker compose exec api python -m hq_api.ops_uncap_orders [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database, Tx
from hq_api.domain import order_report as OR
from hq_api.domain import work as W

OPEN_WORKS_SQL = """
SELECT w.id, w.ref, w.status, r.ref AS order_ref FROM owner.order_reports r
JOIN work.work w ON w.ref = ANY(r.work_refs)
WHERE r.ended_at IS NULL AND r.closed_at IS NULL
  AND w.status IN ('queued', 'in_progress', 'waiting') AND w.budget_tokens IS NOT NULL
ORDER BY r.ref, w.ref
"""


async def uncap_open_orders(tx: Tx, *, dry_run: bool = False) -> dict[str, Any]:
    """The open works of open owner orders that still carry a token budget: uncapped, their
    orders' holders woken once. Answers {works: [...], orders: [...], woken: [...]}."""
    from hq_api.domain import session_activity as SA

    rows = [dict(r) for r in await tx.all(OPEN_WORKS_SQL)]
    out: dict[str, Any] = {
        "works": [r["ref"] for r in rows],
        "orders": sorted({r["order_ref"] for r in rows}),
        "woken": [],
    }
    if dry_run:
        return out
    for r in rows:
        await W.uncap(tx, {"id": r["id"]}, OR.SERVICE)
    for ref in out["orders"]:
        rep = await OR.ensure(tx, ref)
        if rep is None:
            continue
        await OR._append_steps(tx, rep["id"], [OR._step("مدیر کل", OR.UNCAPPED_FA)])
        woke = await SA.wake_holder(tx, ref, f"uncapped:{ref}")
        if woke.get("run_id"):
            out["woken"].append(ref)
        await OR.refresh(tx, ref)
    return out


async def run(dry_run: bool) -> dict[str, Any]:
    s = Settings()
    db = Database.create(s, pool_size=1)
    try:
        companies = Companies(db, ttl_s=0)
        async with db.tx(await companies.ids()) as tx:
            return await uncap_open_orders(tx, dry_run=dry_run)
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the counts, change nothing")
    args = parser.parse_args()
    out = asyncio.run(run(args.dry_run))
    verb = "would uncap" if args.dry_run else "uncapped"
    print(
        f"ops_uncap_orders: {verb} {len(out['works'])} work(s) of {len(out['orders'])} open "
        f"order(s); holders woken: {len(out['woken'])}",
        file=sys.stdout,
    )
    for ref in out["orders"]:
        print(f"  {ref}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
