#!/usr/bin/env bash
# The hourly backup (prompt 07 §1, contract §18.9), run by
# coinepro-hq-backup-hourly.timer (or `make backup-hourly`):
#   1. a fresh set in $HQ_BACKUP_DIR/hourly/set: pg_dump -Fc -Z0 of every
#      database (uncompressed: restic compresses with zstd and deduplicates,
#      which a compressed dump defeats; 7.1 §2.7), globals.sql, the audit
#      anchors, the sha256 of every api file, the OpenBao raft snapshot (only
#      with the owner's snapshot-only token, renewed after every snapshot),
#      manifest.json and SHA256SUMS;
#   2. once a calendar day (UTC) a WAL-G base backup (the WAL archive itself
#      is continuous: archive_command + archive_timeout=60s) and the
#      base-backup retention (9: PITR over the last 7 full days); then a PITR
#      end mark: one commit and a WAL switch, archived before the snapshot;
#   3. one restic snapshot of the set, the WAL archive, the api's files and the
#      anchors into the local repository, then copied to Google Drive (and
#      Hetzner Object Storage when switched on); retention on each (a failure
#      is reported per destination); once a day prune and
#      `restic check --read-data-subset 5%` (both wait while the weekly
#      restore test reads a repository);
#   4. status/hourly.json and status/snapshots.json for the worker (metadata
#      only) and hq_backup.prom for node-exporter: the time of the last
#      success, Prometheus' dead-man's switch, independent of the worker.
# ok = every configured destination got this hour's snapshot. A failed run
# exits non-zero; the worker raises the alerts (older than 2 h: urgent).
set -euo pipefail

BLOG_NAME="backup-hourly"
# shellcheck source=restic-lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/restic-lib.sh"

HOURLY_DIR="$BACKUP_ROOT/hourly"
STATE="$HOURLY_STATE"
WAL_KEEP_FULL="${HQ_WAL_KEEP_FULL:-9}"   # daily base backups kept: PITR over the last 7 full days
SNAP_MIN_TTL_S=$((7 * 86400))           # a snapshot token that cannot outlive a week more is an error
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
# The one-shot lock (prompt 12 §4): the TTS pass and the backup never run at
# once, so the memory gate counts the one-shots once. A TTS pass ends within
# minutes; the backup waits for it (at most 15 minutes), then runs anyway.
if [[ -d /run/hq ]]; then
  exec 8>/run/hq/oneshot.lock
  flock -w 900 8 || blog "the one-shot lock stayed busy for 15 minutes; backing up anyway"
fi

declare -A dest_ok=() dest_err=() dest_used=() dest_quota=() dest_ret=() dest_ret_err=()
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
due() { day_due "$(state_get "$1")"; }  # due KEY: KEY was last done on an earlier UTC day (or never)
# The weekly restore test holds its lock while it reads a repository (for a
# long while, from Drive): forget, prune and check need restic's exclusive
# lock, so they wait for the next hour instead of failing (7.1 §2.5).
weekly_running() {
  [[ -e "$BACKUP_ROOT/.restore-weekly.lock" ]] || return 1
  ! flock -n "$BACKUP_ROOT/.restore-weekly.lock" true 2>/dev/null
}
# A run that fails before OpenBao was read still shows Drive as configured
# when it was connected once (7.1 §3), never "not configured".
if gdrive_remembered; then GDRIVE_CONFIGURED=true; fi

# node-exporter's textfile collector (7.1 §2.4): Prometheus alerts on the time
# of the last success even when the worker or Temporal is down.
write_metrics() {
  local dir="$TEXTFILE_DIR" f last_s=0 lo k v c
  if [[ ! -d "$dir" || ! -w "$dir" ]]; then
    blog "metrics: $dir is not writable (make install-systemd); skipped"
    return 0
  fi
  lo="$(state_get last_ok_at)"
  if [[ -n "$lo" ]]; then last_s="$(date -u -d "$lo" +%s)"; fi
  f="$(mktemp "$dir/.hq_backup.XXXXXX")"
  {
    echo "# HELP hq_backup_last_success_timestamp_seconds Unix time of the newest hourly backup that reached every configured destination (0: none)."
    echo "# TYPE hq_backup_last_success_timestamp_seconds gauge"
    echo "hq_backup_last_success_timestamp_seconds $last_s"
    echo "# HELP hq_backup_last_run_timestamp_seconds Unix time the newest hourly backup run started."
    echo "# TYPE hq_backup_last_run_timestamp_seconds gauge"
    echo "hq_backup_last_run_timestamp_seconds $started_s"
    echo "# HELP hq_backup_last_run_ok 1 when the newest hourly backup run succeeded."
    echo "# TYPE hq_backup_last_run_ok gauge"
    echo "hq_backup_last_run_ok $([[ "$succeeded" == true ]] && echo 1 || echo 0)"
    echo "# HELP hq_backup_destination_ok 1 when the destination got the newest run's snapshot."
    echo "# TYPE hq_backup_destination_ok gauge"
    for k in local gdrive hetzner; do
      v="${dest_ok[$k]:-}"
      if [[ -n "$v" ]]; then echo "hq_backup_destination_ok{destination=\"$k\"} $([[ "$v" == true ]] && echo 1 || echo 0)"; fi
    done
    c="$(state_get check_ok)"
    if [[ -n "$c" ]]; then
      echo "# HELP hq_backup_check_ok 1 when the newest restic check of every repository passed."
      echo "# TYPE hq_backup_check_ok gauge"
      echo "hq_backup_check_ok $([[ "$c" == true ]] && echo 1 || echo 0)"
    fi
    v="$(jq -r 'if .failing == null then "" elif (.failing == true) or ((.ready_count // 0) > 5) then 1 else 0 end' \
      <<<"$wal" 2>/dev/null || true)"
    if [[ -n "$v" ]]; then
      echo "# HELP hq_backup_wal_failing 1 while WAL archiving fails (PITR is cut)."
      echo "# TYPE hq_backup_wal_failing gauge"
      echo "hq_backup_wal_failing $v"
    fi
    v="$(jq -r 'if .configured != true then "" elif .ok == true then 1 else 0 end' <<<"$openbao_snap" 2>/dev/null || true)"
    if [[ -n "$v" ]]; then
      echo "# HELP hq_backup_openbao_snapshot_ok 1 when the newest OpenBao snapshot (and its token's renewal) succeeded."
      echo "# TYPE hq_backup_openbao_snapshot_ok gauge"
      echo "hq_backup_openbao_snapshot_ok $v"
    fi
  } >"$f"
  chmod 644 "$f"
  mv "$f" "$dir/hq_backup.prom"
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
      --arg prev "$(state_get "last_ok_$k")" --arg ret "${dest_ret[$k]:-}" --arg ret_err "${dest_ret_err[$k]:-}" \
      --arg ret_prev "$(state_get "retention_ok_$k")" \
      '. + [{key: $k, configured: $c,
             ok: (if $ok == "" then null else ($ok == "true") end),
             error: (if $err == "" then null else $err end),
             last_ok_at: (if $prev == "" then null else $prev end),
             used_bytes: (if $used == "" then null else ($used | tonumber) end),
             quota_bytes: (if $quota == "" then null else ($quota | tonumber) end),
             retention_ok: (if $ret == "" then null else ($ret == "true") end),
             retention_error: (if $ret_err == "" then null else $ret_err end),
             retention_last_ok_at: (if $ret_prev == "" then null else $ret_prev end)}]' <<<"$dests")"
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
  write_metrics || blog "metrics: could not be written"
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
  "$HQ" exec -T postgres pg_dump -U postgres -Fc -Z0 -d "$db" >"$set_dir/$db.dump"
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

load_secrets || { error="secrets unavailable: $LOAD_ERROR"; exit 1; }
# 7.1 §2.3: Drive, once connected, is remembered; gone from OpenBao later is an error.
if [[ "$GDRIVE_CONFIGURED" == true ]]; then
  [[ -n "$(state_get gdrive_configured_at)" ]] || state_set gdrive_configured_at "$started_at"
elif gdrive_remembered; then
  GDRIVE_CONFIGURED=true
  GDRIVE_ERROR="Google Drive was connected (since $(state_get gdrive_configured_at)) but kv/backup/gdrive is gone: run make gdrive-auth"
fi

# OpenBao: a raft snapshot only with the owner's snapshot-only token, which is
# renewed after every snapshot (a periodic token lapses after 32 days unused).
snap_json() { # snap_json OK ERROR [RENEWED_AT TTL_S]
  jq -n --arg at "$(state_get openbao_at)" --argjson ok "$1" --arg err "$2" --arg ren "${3:-}" --arg ttl "${4:-}" \
    '{configured: true, last_at: (if $at == "" then null else $at end), ok: $ok,
      error: (if $err == "" then null else $err end), renewed_at: (if $ren == "" then null else $ren end),
      ttl_s: (if $ttl == "" then null else ($ttl | tonumber) end)}'
}
if [[ -n "$SNAPSHOT_ERROR" ]]; then
  openbao_snap="$(snap_json false "$SNAPSHOT_ERROR")"
elif [[ "$SNAPSHOT_TOKEN" == true ]]; then
  printf 'X-Vault-Token: %s\n' "$(cat "$SEC/snapshot.token")" >"$SEC/snap.auth"
  if curl -sS -f -H @"$SEC/snap.auth" -o "$set_dir/openbao.snap" "$BAO_ADDR/v1/sys/storage/raft/snapshot" 2>/dev/null &&
    [[ -s "$set_dir/openbao.snap" ]]; then
    state_set openbao_at "$started_at"
    # Only the new lease's length leaves the answer (it also carries the token).
    ttl="$(curl -sS -f -X POST -H @"$SEC/snap.auth" -H 'Content-Type: application/json' --data '{}' \
      "$BAO_ADDR/v1/auth/token/renew-self" 2>/dev/null | jq -r '.auth.lease_duration // empty' 2>/dev/null || true)"
    if [[ "$ttl" =~ ^[0-9]+$ ]] && ((ttl >= SNAP_MIN_TTL_S)); then
      openbao_snap="$(snap_json true "" "$started_at" "$ttl")"
    elif [[ "$ttl" =~ ^[0-9]+$ ]]; then
      openbao_snap="$(snap_json false "the snapshot token expires in $((ttl / 86400)) day(s) and cannot be renewed further: create a periodic one (RUNBOOK §18)" "$started_at" "$ttl")"
    else
      openbao_snap="$(snap_json false "the snapshot token could not be renewed (auth/token/renew-self)")"
    fi
  else
    rm -f "$set_dir/openbao.snap"
    openbao_snap="$(snap_json false "the raft snapshot failed (token expired or revoked?)")"
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

# The PITR end mark (7.1 §2.1): one commit and a WAL switch, archived before
# the snapshot. The snapshot's archive then reaches this moment, and every
# recovery target before it has a commit after it (recovery to a time stops
# at the first commit past the target; without one it fails).
seg=""
if [[ "$wal_failing" != true ]]; then
  seg="$(psql_admin -c 'SELECT txid_current()' -c 'SELECT pg_walfile_name(pg_switch_wal())' | tail -n1)" || seg=""
fi
if [[ "$seg" =~ ^[0-9A-F]{24}$ ]]; then
  archived=false
  for _ in $(seq 1 "${HQ_WAL_MARK_WAIT_S:-60}"); do
    if [[ "$(psql_admin -c "SELECT coalesce(last_archived_wal >= '$seg', false) FROM pg_stat_archiver")" == t ]]; then
      archived=true
      break
    fi
    sleep 1
  done
  [[ "$archived" == true ]] || blog "WAL end mark $seg not archived yet; the snapshot's archive ends earlier"
fi

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
skip_exclusive=false
if weekly_running; then
  skip_exclusive=true
  blog "the weekly restore test is running: retention, prune and check wait for the next hour"
fi
retention() { # retention KEY REPO NETWORK -- forget; a failure is reported, never only logged (7.1 §3)
  local keep=("${REMOTE_KEEP[@]}")
  [[ "$1" == local ]] && keep=("${LOCAL_KEEP[@]}")
  [[ "$skip_exclusive" == true ]] && return 0
  if brestic "$3" -- -r "$2" forget --tag hourly --host coinepro-hq "${keep[@]}" --quiet >/dev/null 2>&1; then
    dest_ret[$1]=true
  else
    dest_ret[$1]=false
    dest_ret_err[$1]="forget failed (kept everything)"
    blog "$1 retention failed (kept everything)"
  fi
}
retention local "$LOCAL_REPO" none
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
  dest_ok[$key]=true
  state_set "last_ok_$key" "$started_at"
  retention "$key" "$repo" "$remote_network"
  dest_used[$key]="$(brestic "$remote_network" -- -r "$repo" stats --mode raw-data --json 2>/dev/null |
    jq -r '.total_size // empty' || true)"
  if [[ "$key" == gdrive ]]; then
    dest_quota[$key]="$(brclone "$remote_network" about gdrive: --json 2>/dev/null | jq -r '.total // empty' || true)"
  fi
  blog "$key: snapshot copied"
}
remotes=()
all_ok=true
if [[ -n "$GDRIVE_ERROR" ]]; then
  # Never a quiet fall-back to local only (7.1 §2.3).
  dest_ok[gdrive]=false
  dest_err[gdrive]="$GDRIVE_ERROR"
  error="${error:-Google Drive: $GDRIVE_ERROR}"
  all_ok=false
elif [[ "$GDRIVE_CONFIGURED" == true ]]; then
  remotes+=("gdrive=$GDRIVE_REPO")
fi
if [[ "$HETZNER_CONFIGURED" == true ]]; then remotes+=("hetzner=$HETZNER_REPO"); fi
for r in "${remotes[@]}"; do
  offsite "${r%%=*}" "${r#*=}" || all_ok=false
done
if [[ "$GDRIVE_CONFIGURED" != true ]]; then
  dest_err[gdrive]="not configured (make gdrive-auth)"
fi

# Once a day: prune and verify 5% of the data of every repository.
if [[ "$skip_exclusive" != true ]] && due prune_at; then
  if ! brestic none -- -r "$LOCAL_REPO" prune --quiet >/dev/null 2>&1; then
    dest_ret[local]=false
    dest_ret_err[local]="prune failed"
    blog "local prune failed"
  fi
  for r in "${remotes[@]}"; do
    [[ "${dest_ok[${r%%=*}]:-}" == true ]] || continue
    if ! brestic "$remote_network" -- -r "${r#*=}" prune --quiet >/dev/null 2>&1; then
      dest_ret[${r%%=*}]=false
      dest_ret_err[${r%%=*}]="prune failed"
      blog "${r%%=*} prune failed"
    fi
  done
  state_set prune_at "$started_at"
fi
for k in "${!dest_ret[@]}"; do
  if [[ "${dest_ret[$k]}" == true ]]; then state_set "retention_ok_$k" "$started_at"; fi
done
if [[ "$skip_exclusive" != true ]] && due check_at; then
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
