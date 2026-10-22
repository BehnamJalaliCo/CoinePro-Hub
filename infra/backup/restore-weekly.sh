#!/usr/bin/env bash
# The weekly automatic restore test (prompt 07 §1.5), Sunday 06:00 Tehran
# (coinepro-hq-restore-weekly.timer, or `make restore-weekly`):
#   1. the newest hourly snapshot, from Google Drive when it is configured
#      (else the local repository), restored into a temporary directory;
#   2. every check of restore-test.sh on its set (checksums, each database
#      restored with --exit-on-error, table counts, vector, Temporal schema,
#      anchors) and every api file against its sha256;
#   3. point-in-time recovery from the restored WAL archive to a random moment
#      of the last 24 hours (pitr.sh, a throwaway container);
# then status/restore-weekly.json (the worker stores it in backup.restore_tests
# and raises an urgent notification when it failed). Nothing touches production.
# 7.1: one run at a time (a second one exits quietly and writes nothing); every
# restic call waits for a lock (--retry-lock 30m) instead of failing; the
# restore size is compared with the free disk first; Drive, once connected,
# is the source and its absence is a failure (never a quiet local test).
set -euo pipefail

BLOG_NAME="restore-weekly"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"

started_s="$(date +%s)"
started_at="$(date -u +%FT%TZ)"
source_key=""
snapshot=""
snapshot_time=""
db='{"ok": null}'
pitr='{"ok": null}'
notes=""
ok=false
work=""

umask 077
mkdir -p "$BACKUP_ROOT"
# The lock first, then the trap (7.1 §2.5): a run that finds the lock busy
# leaves quietly, without overwriting the running test's result.
exec 9>"$BACKUP_ROOT/.restore-weekly.lock"
if ! flock -n 9; then
  blog "another restore test is running; exiting"
  exit 0
fi

write_result() {
  jq -n --arg at "$started_at" --argjson ok "$ok" --argjson dur "$(($(date +%s) - started_s))" \
    --arg src "$source_key" --arg snap "$snapshot" --arg st "$snapshot_time" --argjson db "$db" \
    --argjson pitr "$pitr" --arg notes "$notes" \
    '{at: $at, ok: $ok, duration_s: $dur, source: (if $src == "" then null else $src end),
      snapshot: (if $snap == "" then null else $snap end),
      snapshot_time: (if $st == "" then null else $st end), db: $db, pitr: $pitr,
      notes: (if $notes == "" then null else $notes end)}' | write_json "$STATUS_DIR/restore-weekly.json"
}
on_exit() {
  local rc=$?
  if [[ -n "$work" && -d "$work" ]]; then
    # The restored files keep their owners (Postgres, the api): removed by a container.
    docker run --rm --network none -v "$work:/x" "$TOOLS_IMAGE" sh -c 'rm -rf /x/* /x/.[!.]* 2>/dev/null; true' \
      >/dev/null 2>&1 || true
    rmdir "$work" 2>/dev/null || true
  fi
  if ((rc != 0)) && [[ "$ok" != true ]]; then
    [[ -n "$notes" ]] || notes="failed (exit $rc)"
    write_result || true
  fi
  secrets_cleanup
}
trap on_exit EXIT

compose_facts
load_secrets || { notes="secrets unavailable: $LOAD_ERROR"; exit 1; }
if [[ -n "$GDRIVE_ERROR" ]]; then
  notes="Google Drive: $GDRIVE_ERROR"
  exit 1
fi
if [[ "$GDRIVE_CONFIGURED" != true ]] && gdrive_remembered; then
  notes="Google Drive was connected but kv/backup/gdrive is gone (make gdrive-auth); no restore from it"
  exit 1
fi
if [[ "$GDRIVE_CONFIGURED" == true ]]; then
  source_key=gdrive repo="$GDRIVE_REPO" network=bridge
else
  source_key=local repo=/restic/repo network=none
fi

latest="$(brestic "$network" -- -r "$repo" "${RETRY_LOCK[@]}" snapshots --tag hourly --latest 1 --json 2>/dev/null |
  jq -c 'sort_by(.time) | last // empty')" || true
[[ -n "$latest" ]] || { notes="no hourly snapshot in $source_key"; exit 1; }
snapshot="$(jq -r .id <<<"$latest")"
snapshot_time="$(jq -r .time <<<"$latest")"

# Room first (7.1 §2.7): the snapshot's restore size plus a reserve that keeps
# the hub itself writable (the PITR's throwaway data directory comes on top).
need="$(brestic "$network" -- -r "$repo" "${RETRY_LOCK[@]}" stats --mode restore-size "$snapshot" --json 2>/dev/null |
  jq -r '.total_size // empty' 2>/dev/null || true)"
[[ "$need" =~ ^[0-9]+$ ]] || { notes="restic stats --mode restore-size failed for ${snapshot:0:8}; nothing restored"; exit 1; }
reserve="${HQ_RESTORE_MIN_FREE_BYTES:-5368709120}"
free="$(df -B1 --output=avail "$BACKUP_ROOT" | tail -n1 | tr -d ' ')"
if ((free < need + reserve)); then
  notes="not enough free disk for the restore test: the snapshot needs $(numfmt --to=iec "$need")"
  notes+=" and $(numfmt --to=iec "$reserve") must stay free, $(numfmt --to=iec "$free") free on $BACKUP_ROOT; nothing restored"
  exit 1
fi
blog "restoring ${snapshot:0:8} ($snapshot_time, $(numfmt --to=iec "$need")) from $source_key"

work="$(mktemp -d "$BACKUP_ROOT/.restore-weekly-XXXXXX")"
brestic "$network" "${RESTORE_CAPS[@]}" -v "$work:/restore" -- -r "$repo" "${RETRY_LOCK[@]}" \
  restore "$snapshot" --target /restore --quiet >/dev/null 2>&1 || { notes="restic restore failed"; exit 1; }

# 2. the database set and the files.
if out="$(HQ_RESTORE_SET="$work/backup/set" HQ_RESTORE_FILES_DIR="$work/backup/files" \
  HQ_RESTORE_STATUS=restore-weekly-db "$REPO_DIR/infra/backup/restore-test.sh" 2>&1)"; then
  db="$(jq -n --arg n "$(tail -n1 <<<"$out")" '{ok: true, notes: $n}')"
else
  db="$(jq -n --arg n "$(grep -m1 'FAIL' <<<"$out" || tail -n1 <<<"$out")" '{ok: false, notes: $n}')"
fi

# 3. point-in-time recovery to a random moment of the last 24 hours that the
# restored archive covers (after its oldest base backup, before the snapshot).
prefix="$work/backup/wal"
first="$(docker run --rm --network none -e WALG_FILE_PREFIX=/wal -v "$prefix:/wal:ro" "$PG_IMAGE" \
  wal-g backup-list --json --detail 2>/dev/null |
  jq -r '[.[].finish_time] | sort | first // empty' 2>/dev/null || true)"
if [[ -z "$first" ]]; then
  pitr='{"ok": false, "error": "no base backup in the restored archive"}'
else
  # Margins: after the base backup, before the snapshot (tests shrink them).
  lo=$(($(date -u -d "$first" +%s) + ${HQ_PITR_AFTER_BASE_S:-60}))
  day_ago=$(($(date +%s) - 86400))
  ((lo < day_ago)) && lo=$day_ago
  hi=$(($(date -u -d "$snapshot_time" +%s) - ${HQ_PITR_BEFORE_SNAPSHOT_S:-120}))
  if ((hi <= lo)); then
    pitr="$(jq -n --arg f "$first" '{ok: false, error: "the archive does not cover the last 24 hours yet", first_base_backup: $f}')"
  else
    # HQ_PITR_TARGET: tests only (a moment their throwaway archive is known to cover).
    target="${HQ_PITR_TARGET:-$(date -u -d "@$(shuf -i "$lo-$hi" -n1)" '+%F %T UTC')}"
    pitr="$("$REPO_DIR/infra/backup/pitr.sh" "$target" --prefix "$prefix" --image "$PG_IMAGE" 2>/dev/null)" ||
      true
    [[ -n "$pitr" ]] || pitr="$(jq -n --arg t "$target" '{ok: false, target: $t, error: "pitr.sh gave no result"}')"
  fi
fi

if [[ "$(jq -r .ok <<<"$db")" == true && "$(jq -r .ok <<<"$pitr")" == true ]]; then
  ok=true
  notes="database set, files and PITR ok"
else
  notes="db: $(jq -r '.notes // .ok' <<<"$db"); pitr: $(jq -r '.error // .ok' <<<"$pitr")"
fi
write_result
blog "$notes"
[[ "$ok" == true ]]
