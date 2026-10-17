#!/usr/bin/env bash
# make audit-reanchor reason="restore of backup <stamp>" (prompt 05 §1.4)
#
# After a database restore the chain head in Postgres is older than the last
# anchor kept outside it, so /audit/verify says `anchor: mismatch` (as it
# should). This re-anchors on the restored chain - only with an explicit typed
# confirmation, and always with an audit row (hq_api.reanchor):
#   1. the restored chain must verify on its own;
#   2. audit row audit.reanchor (A3) with the reason and both heads;
#   3. a new anchor line that keeps the previous anchor inside it.
# Nothing is ever deleted from the anchor file.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# HQ_COMPOSE_CMD: a stand-in for hq.sh, for the script's own tests only.
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
ANCHORS="${HQ_BACKUP_DIR:-/home/Hub/backups}/audit-anchors/audit-chain.jsonl"
REASON="${1:-}"

[[ -n "$REASON" ]] || { echo 'usage: make audit-reanchor reason="restore of backup <stamp>"' >&2; exit 2; }
# A person at a terminal only (prompt 05.1 §3): no pipe, cron job or agent
# re-anchors the audit chain, not even with HQ_REANCHOR_CONFIRM, which only
# saves the typing in that terminal.
[[ -t 0 ]] || { echo "audit-reanchor: needs a terminal (the confirmation is a person's)" >&2; exit 1; }

echo "audit-reanchor: the current state"
"$HQ" exec -T worker python -c '
import asyncio, json
from hq_api import audit
from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database
async def main():
    s = Settings()
    db = Database.create(s, pool_size=1)
    try:
        async with db.tx(await Companies(db, ttl_s=0).ids()) as tx:
            alone = await tx.one("SELECT ok, checked FROM audit.verify_chain()")
            with_anchor = await audit.verify(tx, anchor_file=s.audit_anchor_file or None)
        last = audit.last_anchor(s.audit_anchor_file)
        print(json.dumps({"chain_verifies_alone": alone["ok"], "rows": alone["checked"],
                          "anchor": with_anchor["anchor"],
                          "last_anchor_seq": last["seq"] if last else None}))
    finally:
        await db.close()
asyncio.run(main())'
echo "audit-reanchor: anchor file $ANCHORS (append-only; nothing is removed)"

if [[ "${HQ_REANCHOR_CONFIRM:-}" != "re-anchor" ]]; then
  read -r -p 'Type re-anchor to accept the restored chain as the new base: ' answer
  [[ "$answer" == "re-anchor" ]] || { echo "audit-reanchor: cancelled"; exit 1; }
fi
"$HQ" exec -T worker python -m hq_api.reanchor --reason "$REASON"
