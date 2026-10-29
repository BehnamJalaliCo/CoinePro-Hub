#!/usr/bin/env bash
# make fresh-start (prompt 16): the hub's fresh start before the owner's
# opening, run only on the owner's own words in the hub session, given here
# as HQ_FRESH_START_CONFIRM="شروع تازه را اجرا کن". In order:
#   1. the api and the worker stop (nothing writes while the data goes);
#   2. a full backup: make backup (the dumps) and an hourly snapshot (local
#      and Google Drive), kept out of every retention as `pre-fresh-start`;
#   3. one transaction as the superuser (hq_api.fresh_start: what ran goes,
#      every employee and everything the hub is made of stays, the audit
#      chain starts again with this fresh start as its first row);
#   4. make up (migrate and the seeds, as at every start), then the new
#      chain's first anchor (worker) and the wiped rows' stored files (api).
# The script prints what it kept and the counts; no secret is ever printed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
TAG=pre-fresh-start

[[ "${HQ_FRESH_START_CONFIRM:-}" == "شروع تازه را اجرا کن" ]] || {
  echo "fresh-start: only on the owner's own words (HQ_FRESH_START_CONFIRM)" >&2
  exit 2
}
work="$(mktemp -d)"
stopped=0
finished=0
on_exit() {
  local rc=$?
  rm -rf "$work"
  if ((stopped && !finished)); then
    # a failure before the commit changed nothing; after it, make up is still due
    echo "fresh-start: stopped before the end (exit $rc); starting the hub again" >&2
    make -s -C "$REPO_DIR" up >/dev/null || true
  fi
}
trap on_exit EXIT
psql() { "$HQ" exec -T postgres psql -U postgres -d hq -v ON_ERROR_STOP=1 -q -tA "$@"; }

echo "fresh-start: 1/4 stopping the api and the worker"
stopped=1
"$HQ" stop api worker >/dev/null

echo "fresh-start: 2/4 backup"
make -s -C "$REPO_DIR" backup >/dev/null
make -s -C "$REPO_DIR" backup-hourly | tee "$work/hourly.log" | tail -n 1
snap="$(sed -n 's/.*complete: snapshot \([0-9a-f]\{8,\}\) .*/\1/p' "$work/hourly.log" | tail -n 1)"
grep -q 'destinations: local gdrive' "$work/hourly.log" || {
  echo "fresh-start: the snapshot did not reach Google Drive; nothing was wiped" >&2
  exit 1
}
"$REPO_DIR/infra/backup/keep-snapshot.sh" "$snap" "$TAG" | tee "$work/kept"
kept="$(sed -n 's/^local //p' "$work/kept")"

echo "fresh-start: 3/4 the fresh start (one transaction)"
read -r prev_seq prev_hash < <(psql -c "SELECT last_seq || ' ' || last_hash FROM audit.chain_head")
before="$(psql -c "SELECT (SELECT count(*) FROM work.work) || ' work, ' || (SELECT count(*) FROM cartable.decisions)
  || ' decisions, ' || (SELECT count(*) FROM cartable.deliverables) || ' deliverables, '
  || (SELECT count(*) FROM msg.messages) || ' messages, ' || (SELECT count(*) FROM agents.runs) || ' runs, '
  || (SELECT count(*) FROM llm.calls) || ' model calls, ' || (SELECT count(*) FROM notify.notifications)
  || ' notifications, ' || (SELECT count(*) FROM audit.entries) || ' audit rows'")"
"$HQ" run --rm --no-deps -T --entrypoint python api-migrate -m hq_api.fresh_start sql \
  --snapshot "$kept" --previous-seq "$prev_seq" --previous-hash "$prev_hash" >"$work/fresh.sql"
psql <"$work/fresh.sql" >"$work/out"
grep '^head ' "$work/out"

echo "fresh-start: 4/4 starting the hub again"
make -s -C "$REPO_DIR" up >/dev/null
"$HQ" exec -T worker python -m hq_api.fresh_start anchor \
  --snapshot "$kept" --previous-seq "$prev_seq" --previous-hash "$prev_hash"
sed -n 's/^blob //p' "$work/out" | "$HQ" exec -T api python -m hq_api.fresh_start blobs
finished=1
echo "fresh-start: done; wiped $before; kept snapshot $kept ($TAG)"
