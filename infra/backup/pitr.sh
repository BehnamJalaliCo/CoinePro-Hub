#!/usr/bin/env bash
# Point-in-time recovery into a THROWAWAY Postgres (prompt 07 §1.1): the base
# backup taken before TARGET plus the archived WAL up to TARGET, replayed in a
# container without network on a temporary volume; then checked and removed.
# Production is never touched: this is a drill and the proof that the WAL
# archive restores to any minute (`make pitr-test at="2026-10-18 09:41"`).
#
#   pitr.sh TARGET [--prefix DIR] [--image IMAGE] [--sql SQL] [--db DB]
#     TARGET   a timestamp Postgres understands (UTC unless it has a zone)
#     --prefix the WAL-G file storage (default $HQ_BACKUP_DIR/wal)
#     --sql    a query whose single value is printed in the result (tests)
# Prints one JSON line: {target, ok, base_backup, recovered_to, databases,
# hq_tables, value, duration_s, error}. Exit 0 only when ok.
# Env: HQ_PITR_STALL_S (120) and HQ_PITR_DEADLINE_S (2700): see the replay loop.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="${HQ_COMPOSE_CMD:-$REPO_DIR/infra/compose/hq.sh}"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"

target="${1:?usage: pitr.sh TARGET [--prefix DIR] [--image IMAGE] [--sql SQL] [--db DB]}"
shift
prefix="$BACKUP_ROOT/wal"
image=""
query=""
qdb=postgres
while (($#)); do
  case "$1" in
    --prefix) prefix="$2"; shift 2 ;;
    --image) image="$2"; shift 2 ;;
    --sql) query="$2"; shift 2 ;;
    --db) qdb="$2"; shift 2 ;;
    *) echo "pitr: unknown option $1" >&2; exit 2 ;;
  esac
done
[[ -n "$image" ]] || image="$("$HQ" config --format json | jq -r '.services.postgres.image')"
started_s="$(date +%s)"
name="hq-pitr-$$-$(date -u +%s)"
vol="$name-data"
result() { # result OK ERROR [extra json]
  local extra="${3:-}"
  [[ -n "$extra" ]] || extra='{}'
  jq -cn --arg t "$target" --argjson ok "$1" --arg err "$2" --argjson x "$extra" \
    --argjson dur "$(($(date +%s) - started_s))" \
    '{target: $t, ok: $ok, error: (if $err == "" then null else $err end), duration_s: $dur} + $x'
}
cleanup() {
  docker rm -fv "$name" >/dev/null 2>&1 || true  # -v: its anonymous data volume too
  docker volume rm -f "$vol" >/dev/null 2>&1 || true
}
trap cleanup EXIT
fail() { result false "$1" "${2:-}"; exit 1; }

[[ -d "$prefix" ]] || fail "no WAL archive at $prefix"
target_epoch="$(date -u -d "$target" +%s 2>/dev/null)" || fail "target is not a time"
target_iso="$(date -u -d "$target" '+%F %T.%6N+00')"  # the form recovery_target_time accepts

walg_run() { # walg_run [docker args] -- wal-g args: WAL-G against the archive, read-only, no network
  local extra=()
  while (($#)) && [[ "$1" != "--" ]]; do extra+=("$1"); shift; done
  shift
  docker run --rm --network none --memory 512m -e WALG_FILE_PREFIX=/wal -v "$prefix:/wal:ro" \
    "${extra[@]}" "$image" wal-g "$@"
}

# The newest base backup that finished before the target.
list="$(walg_run -- backup-list --json --detail 2>/dev/null)" || fail "WAL-G cannot read the archive"
backup="$(jq -r --argjson t "$target_epoch" '[.[] | select((.finish_time | sub("\\.[0-9]+"; "") |
  sub("Z$"; "") | strptime("%Y-%m-%dT%H:%M:%S") | mktime) <= $t)] | sort_by(.finish_time) | last | .backup_name // empty' \
  <<<"$list")"
[[ -n "$backup" ]] || fail "no base backup finished before $target_iso"

docker volume create "$vol" >/dev/null
# Fetch the base backup and set up recovery (as root, then hand the directory to postgres).
docker run --rm --network none --memory 512m --user 0:0 -e WALG_FILE_PREFIX=/wal -v "$prefix:/wal:ro" \
  -v "$vol:/var/lib/postgresql/data" -e TARGET="$target_iso" -e BACKUP="$backup" "$image" sh -ec '
    d=/var/lib/postgresql/data/pgdata
    mkdir -p "$d"
    wal-g backup-fetch "$d" "$BACKUP" >/dev/null 2>&1
    {
      echo "restore_command = '"'"'wal-g wal-fetch %f %p'"'"'"
      echo "recovery_target_time = '"'"'$TARGET'"'"'"
      echo "recovery_target_action = '"'"'promote'"'"'"
      echo "archive_mode = off"
      echo "listen_addresses = '"'"''"'"'"
    } >>"$d/postgresql.auto.conf"
    touch "$d/recovery.signal"
    chown -R postgres:postgres "$d"
    chmod 700 "$d"' >/dev/null || fail "base backup $backup could not be fetched"

docker run -d --name "$name" --network none --memory 768m -e PGDATA=/var/lib/postgresql/data/pgdata \
  -e WALG_FILE_PREFIX=/wal -v "$prefix:/wal:ro" -v "$vol:/var/lib/postgresql/data" "$image" postgres >/dev/null

sql() { docker exec "$name" psql -U postgres -X -At -v ON_ERROR_STOP=1 "$@"; }
# 7.1 §2.1: a day of WAL (~1440 segments) takes longer than any fixed limit
# worth having, so the limit is progress: recovery fails only when replay
# stands still for HQ_PITR_STALL_S (default 120 s), or after HQ_PITR_DEADLINE_S
# (default 45 min) in all. Progress = pg_last_wal_replay_lsn() once the server
# answers (hot standby), and before that the segments restored from the archive.
deadline_s="${HQ_PITR_DEADLINE_S:-2700}"
stall_s="${HQ_PITR_STALL_S:-120}"
ready=false
why="recovery did not finish"
mark=""
moved_s="$(date +%s)"
while :; do
  if sql -c 'SELECT NOT pg_is_in_recovery()' 2>/dev/null | grep -qx t; then ready=true; break; fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" != true ]]; then
    why="recovery stopped (postgres exited)"
    break
  fi
  now_s="$(date +%s)"
  progress="$(sql -c 'SELECT pg_last_wal_replay_lsn()' 2>/dev/null || true)/$(docker logs "$name" 2>&1 |
    grep -c 'restored log file' || true)"
  if [[ "$progress" != "$mark" ]]; then
    mark="$progress"
    moved_s="$now_s"
  fi
  if ((now_s - moved_s > stall_s)); then
    why="recovery stalled: no WAL replayed for ${stall_s}s"
    break
  fi
  if ((now_s - started_s > deadline_s)); then
    why="recovery did not finish within ${deadline_s}s"
    break
  fi
  sleep 2
done
if [[ "$ready" != true ]]; then
  docker logs --tail 8 "$name" 2>&1 | sed 's/^/pitr: postgres: /' >&2 || true
  fail "$why" "$(jq -cn --arg b "$backup" '{base_backup: $b}')"
fi

recovered="$(sql -c "SELECT coalesce(to_char(pg_last_xact_replay_timestamp() AT TIME ZONE 'UTC',
  'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), '')")"
mapfile -t dbs < <(sql -c "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1")
hq_tables=null
if printf '%s\n' "${dbs[@]}" | grep -qx hq; then
  hq_tables="$(sql -d hq -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
fi
value=""
if [[ -n "$query" ]]; then value="$(sql -d "$qdb" -c "$query")" || fail "check query failed"; fi
# Nothing after the target may have been replayed.
if [[ -n "$recovered" ]] && (($(date -u -d "$recovered" +%s) > target_epoch)); then
  fail "replayed past the target ($recovered)"
fi
result true "" "$(jq -cn --arg b "$backup" --arg r "$recovered" --argjson t "$hq_tables" --arg v "$value" \
  --args '{base_backup: $b, recovered_to: (if $r == "" then null else $r end), databases: $ARGS.positional,
           hq_tables: $t, value: (if $v == "" then null else $v end)}' "${dbs[@]}")"
