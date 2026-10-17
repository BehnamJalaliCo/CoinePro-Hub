"""`python -m hq_api.reanchor --reason "..."` (worker container): re-anchor the
audit chain after the database came back from a backup (prompt 05 §1.4).

A restore puts an older chain head in Postgres than the last anchor in the
append-only file, so /audit/verify reports `anchor: mismatch` - correctly: the
file proves the chain once reached further. This tool records, explicitly and
auditably, that the operator accepts the restored chain as the new base:

  1. the restored chain must verify on its own (audit.verify_chain ok);
  2. one audit row `audit.reanchor` (A3, summary: reason, old and new head);
  3. a new anchor line for the new head, carrying the previous anchor, so the
     file still shows what was lost.

It never deletes or rewrites an anchor line. Run it through
`make audit-reanchor`, which asks for a typed confirmation first.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from hq_api import audit
from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database


async def reanchor(db: Database, anchor_file: str, reason: str) -> dict[str, Any]:
    companies = Companies(db, ttl_s=0)
    holding = await companies.holding()
    previous = audit.last_anchor(anchor_file)
    async with db.tx(await companies.ids()) as tx:
        chain = await tx.one("SELECT ok, checked, first_bad_seq FROM audit.verify_chain()")
        if not chain["ok"]:
            return {"ok": False, "reason": "the restored chain does not verify", **dict(chain)}
        head = await tx.one("SELECT last_seq AS seq, last_hash AS hash FROM audit.chain_head")
        await audit.record(
            tx,
            audit.SYSTEM,
            company_id=holding.id,
            action="audit.reanchor",
            action_class="A3",
            target_kind="audit_chain",
            target_ref=f"seq:{head['seq']}",
            summary=(
                f"re-anchored after restore: {reason}"[:300]
                + f" (anchor was seq {previous['seq'] if previous else '-'}, head is seq {head['seq']})"
            ),
        )
    async with db.tx(await companies.ids()) as tx:
        new = await tx.one(
            "SELECT last_seq AS seq, last_hash AS hash, now() AS at FROM audit.chain_head WHERE id = 1"
        )
    line = {
        "seq": new["seq"],
        "hash": new["hash"],
        "at": new["at"].isoformat(),
        "reanchor": True,
        "reason": reason[:300],
        "previous": previous,
    }
    await asyncio.to_thread(audit._append, Path(anchor_file), json.dumps(line))
    return {"ok": True, "seq": new["seq"], "previous": previous}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reason", required=True, help="why (e.g. restore of backup <stamp>)")
    args = parser.parse_args()
    s = Settings()
    if not s.audit_anchor_file:
        print("reanchor: HQ_AUDIT_ANCHOR_FILE is not set", file=sys.stderr)
        return 2
    if len(args.reason.strip()) < 5:
        print("reanchor: give a real reason", file=sys.stderr)
        return 2

    async def run() -> dict[str, Any]:
        db = Database.create(s, pool_size=1)
        try:
            return await reanchor(db, s.audit_anchor_file, args.reason.strip())
        finally:
            await db.close()

    result = asyncio.run(run())
    if not result["ok"]:
        print(f"reanchor: refused: {result['reason']}", file=sys.stderr)
        return 1
    prev = result["previous"]
    print(
        f"reanchor: ok; new anchor at seq {result['seq']}"
        + (f" (previous anchor seq {prev['seq']} kept in the file)" if prev else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
