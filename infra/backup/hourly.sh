#!/usr/bin/env bash
# The hourly backup (prompt 07 §1, contract §18.9), run by
# coinepro-hq-backup-hourly.timer (or `make backup-hourly`):
#   1. a fresh set in $HQ_BACKUP_DIR/hourly/set: pg_dump -Fc of every database,
#      globals.sql, the audit anchors, the sha256 of every api file, the
#      OpenBao raft snapshot (only with the owner's snapshot-only token),
#      manifest.json and SHA256SUMS;
#   2. once a day a WAL-G base backup (the WAL archive itself is continuous:
#      archive_command + archive_timeout=60s) and the base-backup retention;
#   3. one restic snapshot of the set, the WAL archive, the api's files and the
#      anchors into the local repository, then copied to Google Drive (and
#      Hetzner Object Storage when switched on); retention on each; once a day
#      prune and `restic check --read-data-subset 5%`;
#   4. status/hourly.json and status/snapshots.json for the worker (metadata only).
# ok = every configured destination got this hour's snapshot. A failed run
# exits non-zero; the worker raises the alerts (older than 2 h: urgent).
set -euo pipefail

BLOG_NAME="backup-hourly"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"
# shellcheck source=files.sh
source "$REPO_DIR/infra/backup/files.sh"

HOURLY_DIR="$BACKUP_ROOT/hourly"
STATE="$HOURLY_DIR/state.json"
WAL_KEEP_FULL="${HQ_WAL_KEEP_FULL:-8}"   # daily base backups kept: PITR over the last 7 days
DAILY_S=$((23 * 3600))                 # "once a day", with room for the timer's jitter
started_s="$(date +%s)"
started_at="$(date -u +%FT%TZ)"

umask 077
mkdir -p "$BACKUP_ROOT" "$HOURLY_DIR"
chmod 700 "$BACKUP_ROOT" "$HOURLY_DIR"

# One hourly run at a time; a busy lock records nothing (the running one will).
exec 9>"$HOURLY_DIR/.lock"
if ! flock -n 9; then
  blog "another hourly backup is running; exiting"
  exit 1
fi

declare -A dest_ok=() dest_err=() dest_used=() dest_quota=()
snapshot=""
size_bytes=0
error=""
succeeded=false
openbao_snap='{"configured": false, "last_at": null, "ok": null}'
base='{"last_at": null, "count": 0}'
wal='{"last_archived_at": null, "lag_s": null, "failed_count": null, "failing": null, "ready_count": null}'

state_get() { jq -r --arg k "$1" '.[$k] // empty' "$STATE" 2>/dev/null || true; }
state_set() { # state_set KEY VALUE
  local cur='{}'
  [[ -s "$STATE" ]] && cur="$(cat "$STATE")"
  jq --arg k "$1" --arg v "$2" '.[$k] = $v' <<<"$cur" >"$STATE.tmp" && mv "$STATE.tmp" "$STATE"
}
due() { # due KEY: true when KEY was last done more than a day ago (or never)
  local last
  last="$(state_get "$1")"
  [[ -z "$last" ]] && return 0
  (($(date +%s) - $(date -d "$last" +%s) > DAILY_S))
}

write_status() {
  local dests="[]" k
  for k in local gdrive hetzner; do
    local configured=false
    case "$k" in
      local) configured=true ;;
      gdrive) configured="$GDRIVE_CONFIGURED" ;;
      hetzner) configured="$HETZNER_CONFIGURED" ;;
    esac
    [[ "$k" == hetzner && "$configured" != true ]] && continue  # optional: shown only when on
    dests="$(jq --arg k "$k" --argjson c "$configured" --arg ok "${dest_ok[$k]:-}" \
      --arg err "${dest_err[$k]:-}" --arg used "${dest_used[$k]:-}" --arg quota "${dest_quota[$k]:-}" \
      --arg prev "$(state_get "last_ok_$k")" \
      '. + [{key: $k, configured: $c,
             ok: (if $ok == "" then null else ($ok == "true") end),
             error: (if $err == "" then null else $err end),
             last_ok_at: (if $prev == "" then null else $prev end),
             used_bytes: (if $used == "" then null else ($used | tonumber) end),
             quota_bytes: (if $quota == "" then null else ($quota | tonumber) end)}]' <<<"$dests")"
  done
  jq -n --arg at "$started_at" --argjson ok "$succeeded" --arg snap "$snapshot" \
    --argjson size "$size_bytes" --argjson dur "$(($(date +%s) - started_s))" --arg err "$error" \
    --argjson dests "$dests" --argjson wal "$wal" --argjson base "$base" --argjson bao "$openbao_snap" \
    --arg last_ok "$(state_get last_ok_at)" --arg check_at "$(state_get check_at)" \
    --arg check_ok "$(state_get check_ok)" --arg prune_at "$(state_get prune_at)" \
    --arg hourly "${REMOTE_KEEP[1]}" --arg daily "${REMOTE_KEEP[3]}" --arg weekly "${REMOTE_KEEP[5]}" \
    --arg monthly "${REMOTE_KEEP[7]}" --arg yearly "${REMOTE_KEEP[9]}" '
    {at: $at, ok: $ok, snapshot: (if $snap == "" then null else $snap end), size_bytes: $size,
     duration_s: $dur, error: (if $err == "" then null else $err end),
     last_ok_at: (if $last_ok == "" then null else $last_ok end),
     destinations: $dests, wal: $wal, base_backup: $base, openbao_snapshot: $bao,
     check: {last_at: (if $check_at == "" then null else $check_at end),
             ok: (if $check_ok == "" then null else ($check_ok == "true") end)},
     prune_at: (if $prune_at == "" then null else $prune_at end),
     retention: {hourly: ($hourly | tonumber), daily: ($daily | tonumber), weekly: ($weekly | tonumber),
                 monthly: ($monthly | tonumber), yearly: ($yearly | tonumber)},
     encryption: "restic (AES-256)"}' | write_json "$STATUS_DIR/hourly.json"
}

on_exit() {
  local rc=$?
  if [[ "$succeeded" != true ]]; then
    [[ -z "$error" ]] && error="failed (exit $rc)"
    write_status || true
  fi
  secrets_cleanup
}
trap on_exit EXIT

compose_facts
psql_admin() { "$HQ" exec -T postgres psql -U postgres -d postgres -X -At -v ON_ERROR_STOP=1 "$@"; }
walg() { "$HQ" exec -T -u postgres -e PGHOST=/var/run/postgresql -e PGUSER=postgres postgres wal-g "$@"; }

# ------------------------------------------------------------------ 1. set --
set_dir="$HOURLY_DIR/set"
rm -rf "$set_dir"
mkdir -p "$set_dir"
mapfile -t databases < <(psql_admin -c \
  "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
((${#databases[@]})) || { error="no databases found"; exit 1; }
"$HQ" exec -T postgres pg_dumpall -U postgres --globals-only >"$set_dir/globals.sql"
for db in "${databases[@]}"; do
  "$HQ" exec -T postgres pg_dump -U postgres -Fc -d "$db" >"$set_dir/$db.dump"
  "$HQ" exec -T postgres pg_restore --list <"$set_dir/$db.dump" >/dev/null
done
blog "dumped ${#databases[@]} database(s)"

file_count=0
if docker volume inspect "$FILES_VOLUME" >/dev/null 2>&1; then
  docker run --rm --network none -v "$FILES_VOLUME:/data:ro" "$TOOLS_IMAGE" \
    sh -c 'cd /data && find . -type f -exec sha256sum {} + | sort -k2' >"$set_dir/files.sha256"
  file_count="$(wc -l <"$set_dir/files.sha256")"
fi
if [[ -d "$BACKUP_ROOT/audit-anchors" ]]; then
  docker run --rm --network none -v "$BACKUP_ROOT/audit-anchors:/a:ro" "$TOOLS_IMAGE" \
    sh -c 'cat /a/audit-chain.jsonl 2>/dev/null || true' >"$set_dir/audit-chain.jsonl"
fi

load_secrets || { error="secrets unavailable (OpenBao sealed or not provisioned)"; exit 1; }

# OpenBao: a raft snapshot only with the owner's snapshot-only token.
if [[ "$SNAPSHOT_TOKEN" == true ]]; then
  printf 'X-Vault-Token: %s\n' "$(cat "$SEC/snapshot.token")" >"$SEC/snap.auth"
  if curl -sS -f -H @"$SEC/snap.auth" -o "$set_dir/openbao.snap" "$BAO_ADDR/v1/sys/storage/raft/snapshot" 2>/dev/null &&
    [[ -s "$set_dir/openbao.snap" ]]; then
    state_set openbao_at "$started_at"
    openbao_snap="$(jq -n --arg at "$started_at" '{configured: true, last_at: $at, ok: true}')"
  else
    rm -f "$set_dir/openbao.snap"
    openbao_snap="$(jq -n --arg at "$(state_get openbao_at)" \
      '{configured: true, last_at: (if $at == "" then null else $at end), ok: false}')"
  fi
  rm -f "$SEC/snap.auth"
else
  openbao_snap='{"configured": false, "last_at": null, "ok": null, "note": "waiting for the owner (make openbao-snapshot-token)"}'
fi

pg_version="$(psql_admin -c 'SHOW server_version')"
jq -n --arg created "$started_at" --arg pg "$pg_version" --argjson files "$file_count" --arg image "$PG_IMAGE" \
  --args '{created_at: $created, kind: "hourly", postgres_version: $pg, image: $image, files: $files,
           databases: $ARGS.positional}' "${databases[@]}" >"$set_dir/manifest.json"
(cd "$set_dir" && sha256sum -- * >SHA256SUMS)

# ------------------------------------------------------------- 2. WAL-G ----
wal="$(psql_admin -c "SELECT json_build_object(
    'last_archived_at', to_char(last_archived_time AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'),
    'lag_s', CASE WHEN last_archived_time IS NULL THEN NULL
                  ELSE round(extract(epoch FROM now() - last_archived_time))::int END,
    'failed_count', failed_count,
    'last_failed_at', to_char(last_failed_time AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'),
    'failing', COALESCE(last_failed_time > COALESCE(last_archived_time, '-infinity'::timestamptz), false),
    'ready_count', (SELECT count(*) FROM pg_ls_archive_statusdir() WHERE name LIKE '%.ready'))
  FROM pg_stat_archiver")"
# 7.1 §1.1: archiving that fails is a data-loss alarm, never a statistic. With
# archive_timeout=60s a stuck wal-push grows pg_wal by ~16 MB a minute until
# Postgres stops, and PITR is cut silently. The set is still snapshotted
# below, but this run is not ok and exits non-zero; no base backup is taken.
wal_failing="$(jq -r '(.failing == true) or ((.ready_count // 0) > 5)' <<<"$wal")"
if [[ "$wal_failing" == true ]]; then
  blog "WAL archiving is failing ($(jq -r '"failed \(.failed_count), \(.ready_count) segments waiting"' <<<"$wal"))"
  error="WAL archiving is failing"
elif due base_backup_at; then
  if walg backup-push /var/lib/postgresql/data >/dev/null 2>&1; then
    state_set base_backup_at "$started_at"
    walg delete retain FULL "$WAL_KEEP_FULL" --confirm >/dev/null 2>&1 || blog "WAL-G retention failed (kept everything)"
    blog "base backup done (keeping $WAL_KEEP_FULL)"
  else
    blog "base backup failed"
    error="base backup failed"
  fi
fi
count="$(walg backup-list --json 2>/dev/null | jq 'length' 2>/dev/null || echo 0)"
base="$(jq -n --arg at "$(state_get base_backup_at)" --argjson n "${count:-0}" \
  '{last_at: (if $at == "" then null else $at end), count: $n}')"

# ------------------------------------------------------------ 3. restic ----
inputs=(-v "$set_dir:/backup/set:ro" -v "$BACKUP_ROOT/wal:/backup/wal:ro")
if docker volume inspect "$FILES_VOLUME" >/dev/null 2>&1; then inputs+=(-v "$FILES_VOLUME:/backup/files:ro"); fi

remote_network=bridge
LOCAL_REPO=/restic/repo
if ! repo_ready "$LOCAL_REPO" none; then
  dest_ok[local]=false
  dest_err[local]="local repository unavailable"
  error="local repository unavailable"
  exit 1
fi
if out="$(brestic none "${inputs[@]}" -- -r "$LOCAL_REPO" backup /backup --tag hourly --host coinepro-hq \
  --json --quiet 2>/dev/null)"; then
  snapshot="$(jq -r 'select(.message_type == "summary") | .snapshot_id' <<<"$out" | tail -n1)"
  size_bytes="$(jq -r 'select(.message_type == "summary") | .total_bytes_processed' <<<"$out" | tail -n1)"
  dest_ok[local]=true
  state_set last_ok_local "$started_at"
  blog "local snapshot ${snapshot:0:8}"
else
  dest_ok[local]=false
  dest_err[local]="restic backup failed"
  error="local snapshot failed"
  exit 1
fi
brestic none -- -r "$LOCAL_REPO" forget --tag hourly --host coinepro-hq "${LOCAL_KEEP[@]}" --quiet >/dev/null 2>&1 ||
  blog "local retention failed (kept everything)"
used="$(brestic none -- -r "$LOCAL_REPO" stats --mode raw-data --json 2>/dev/null | jq -r '.total_size // empty' || true)"
dest_used[local]="$used"

offsite() { # offsite KEY REPO
  local key="$1" repo="$2"
  if ! repo_ready "$repo" "$remote_network"; then
    dest_ok[$key]=false
    dest_err[$key]="unreachable"
    return 1
  fi
  if ! brestic "$remote_network" -- -r "$repo" copy --from-repo "$LOCAL_REPO" \
    --from-password-file /run/hq-backup/restic.pass --tag hourly --quiet >/dev/null 2>&1; then
    dest_ok[$key]=false
    dest_err[$key]="copy failed"
    return 1
  fi
  brestic "$remote_network" -- -r "$repo" forget --tag hourly --host coinepro-hq "${REMOTE_KEEP[@]}" --quiet \
    >/dev/null 2>&1 || blog "$key retention failed (kept everything)"
  dest_ok[$key]=true
  state_set "last_ok_$key" "$started_at"
  dest_used[$key]="$(brestic "$remote_network" -- -r "$repo" stats --mode raw-data --json 2>/dev/null |
    jq -r '.total_size // empty' || true)"
  if [[ "$key" == gdrive ]]; then
    dest_quota[$key]="$(docker run --rm --network "$remote_network" --memory "$BACKUP_MEM" --user 0:0 --cap-drop ALL \
      --read-only -v "$SEC:/run/hq-backup:ro" -e RCLONE_CONFIG=/run/hq-backup/rclone.conf "$BACKUP_IMAGE" \
      rclone about gdrive: --json 2>/dev/null | jq -r '.total // empty' || true)"
  fi
  blog "$key: snapshot copied"
}
remotes=()
if [[ "$GDRIVE_CONFIGURED" == true ]]; then remotes+=("gdrive=$GDRIVE_REPO"); fi
if [[ "$HETZNER_CONFIGURED" == true ]]; then remotes+=("hetzner=$HETZNER_REPO"); fi
all_ok=true
for r in "${remotes[@]}"; do
  offsite "${r%%=*}" "${r#*=}" || all_ok=false
done
if [[ "$GDRIVE_CONFIGURED" != true ]]; then
  dest_err[gdrive]="not configured (make gdrive-auth)"
fi

# Once a day: prune and verify 5% of the data of every repository.
if due prune_at; then
  brestic none -- -r "$LOCAL_REPO" prune --quiet >/dev/null 2>&1 || blog "local prune failed"
  for r in "${remotes[@]}"; do
    [[ "${dest_ok[${r%%=*}]:-}" == true ]] || continue
    brestic "$remote_network" -- -r "${r#*=}" prune --quiet >/dev/null 2>&1 || blog "${r%%=*} prune failed"
  done
  state_set prune_at "$started_at"
fi
if due check_at; then
  check_ok=true
  brestic none -- -r "$LOCAL_REPO" check --read-data-subset 5% >/dev/null 2>&1 || check_ok=false
  for r in "${remotes[@]}"; do
    [[ "${dest_ok[${r%%=*}]:-}" == true ]] || continue
    brestic "$remote_network" -- -r "${r#*=}" check --read-data-subset 5% >/dev/null 2>&1 || check_ok=false
  done
  state_set check_at "$started_at"
  state_set check_ok "$check_ok"
  blog "restic check: $check_ok"
fi

# The snapshot lists (newest 100 of each repository), metadata only.
snaps="[]"
list() { # list KEY REPO NETWORK
  brestic "$3" -- -r "$2" snapshots --tag hourly --json --latest 100 2>/dev/null |
    jq --arg k "$1" '[.[] | {id, short_id, time, destination: $k, tags,
      size_bytes: (.summary.total_bytes_processed // null)}]' 2>/dev/null || echo '[]'
}
snaps="$(jq -s 'add' <(list local "$LOCAL_REPO" none) \
  <(for r in "${remotes[@]}"; do [[ "${dest_ok[${r%%=*}]:-}" == true ]] && list "${r%%=*}" "${r#*=}" "$remote_network"; done; echo '[]'))"
jq -n --arg at "$started_at" --argjson items "$snaps" '{at: $at, items: ($items | sort_by(.time) | reverse)}' |
  write_json "$STATUS_DIR/snapshots.json"

if [[ "$all_ok" == true && -z "$error" ]]; then
  succeeded=true
  state_set last_ok_at "$started_at"
  write_status
  blog "complete: snapshot ${snapshot:0:8} ($size_bytes bytes; destinations: local${remotes[*]:+ ${remotes[*]%%=*}})"
else
  [[ -n "$error" ]] || error="an off-site copy failed"
  exit 1
fi
