#!/usr/bin/env bash
# Logical backup of every HQ Postgres database (pg_dump -Fc, one file per
# database) plus the roles (globals), into $HQ_BACKUP_DIR/<UTC stamp>/,
# together with the api's file volume (files.tar.gz + files.sha256) and a copy
# of the audit-chain anchors (audit-chain.jsonl, prompt 04.1 §1.11).
# Keeps $HQ_BACKUP_RETENTION_DAYS days (default 7), then hands the new set to
# offsite.sh (off until the Object Storage bucket is configured).
# Run nightly by coinepro-hq-backup.timer, or by hand with `make backup`.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
# shellcheck source=files.sh
source "$REPO_DIR/infra/backup/files.sh"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
RETENTION_DAYS="${HQ_BACKUP_RETENTION_DAYS:-7}"
STAMP_RE='^[0-9]{8}T[0-9]{6}Z$'

log() { printf '%s backup: %s\n' "$(date -u +%FT%TZ)" "$*"; }
started_s="$(date +%s)"
# The outcome, for the hub's own health (health.hub, prompt 05 §4): times,
# result and size only, readable by the worker through a read-only mount.
status() { # status OK STAMP SIZE
  mkdir -p "$BACKUP_ROOT/status" && chmod 755 "$BACKUP_ROOT/status"
  jq -n --arg at "$(date -u +%FT%TZ)" --argjson ok "$1" --arg stamp "$2" --argjson size "$3" \
    --argjson dur "$(($(date +%s) - started_s))" \
    '{at: $at, ok: $ok, stamp: $stamp, size_bytes: $size, duration_s: $dur}' >"$BACKUP_ROOT/status/backup.json.tmp"
  chmod 644 "$BACKUP_ROOT/status/backup.json.tmp"
  mv "$BACKUP_ROOT/status/backup.json.tmp" "$BACKUP_ROOT/status/backup.json"
}

umask 077
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
trap 'status false "" 0' ERR

# One run at a time.
exec 9>"$BACKUP_ROOT/.lock"
if ! flock -n 9; then
  log "another backup is running; exiting"
  exit 1
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
work="$BACKUP_ROOT/.$stamp.partial"
mkdir "$work"
trap 'rm -rf "$work"' EXIT

psql_admin() { "$HQ" exec -T postgres psql -U postgres -d postgres -X -At -v ON_ERROR_STOP=1 "$@"; }

# Every non-template database except the maintenance DB, so new databases are
# picked up without editing this script.
mapfile -t databases < <(psql_admin -c \
  "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
if ((${#databases[@]} == 0)); then
  log "no databases found"
  exit 1
fi

"$HQ" exec -T postgres pg_dumpall -U postgres --globals-only >"$work/globals.sql"
for db in "${databases[@]}"; do
  "$HQ" exec -T postgres pg_dump -U postgres -Fc -d "$db" >"$work/$db.dump"
  # A custom-format archive whose TOC cannot be read is not a backup.
  "$HQ" exec -T postgres pg_restore --list <"$work/$db.dump" >/dev/null
  log "dumped $db ($(du -h "$work/$db.dump" | cut -f1))"
done

config="$("$HQ" config --format json)"
tools_image="$(jq -r '.services["hq-tools"].image' <<<"$config")"

# The api's files (volume hq-files): one archive and the sha256 of every file.
files_volume="$(jq -r '.volumes["hq-files"].name' <<<"$config")"
file_count=0
if docker volume inspect "$files_volume" >/dev/null 2>&1; then
  files_archive "$files_volume" "$tools_image" "$work/files.tar.gz" "$work/files.sha256"
  file_count="$(wc -l <"$work/files.sha256")"
  log "files: $file_count file(s) ($(du -h "$work/files.tar.gz" | cut -f1))"
fi

# The audit-chain anchors (append-only, outside the Postgres volume): a copy
# travels with every set, offsite included.
if [[ -d "$BACKUP_ROOT/audit-anchors" ]]; then
  docker run --rm --network none -v "$BACKUP_ROOT/audit-anchors:/a:ro" "$tools_image" \
    sh -c 'cat /a/audit-chain.jsonl 2>/dev/null || true' >"$work/audit-chain.jsonl"
  log "audit anchors: $(wc -l <"$work/audit-chain.jsonl") line(s)"
fi

pg_version="$(psql_admin -c 'SHOW server_version')"
jq -n --arg created "$stamp" --arg pg "$pg_version" --argjson files "$file_count" \
  --arg image "$(jq -r '.services.postgres.image' <<<"$config")" \
  --args '{created_at: $created, postgres_version: $pg, image: $image, files: $files,
           databases: $ARGS.positional}' \
  "${databases[@]}" >"$work/manifest.json"
extra=()
for f in files.tar.gz files.sha256 audit-chain.jsonl; do
  if [[ -e "$work/$f" ]]; then extra+=("$f"); fi
done
(cd "$work" && sha256sum -- *.dump globals.sql manifest.json "${extra[@]}" >SHA256SUMS)

mv "$work" "$BACKUP_ROOT/$stamp"
trap - EXIT
log "complete: $BACKUP_ROOT/$stamp (${#databases[@]} databases)"
status true "$stamp" "$(du -sb "$BACKUP_ROOT/$stamp" | cut -f1)"

# Retention: delete only directories named like a backup stamp and older than
# the cutoff. Names sort chronologically, so a string compare is exact. The
# audit-anchors directory never matches, so it is never pruned.
cutoff="$(date -u -d "-$RETENTION_DAYS days" +%Y%m%dT%H%M%SZ)"
for dir in "$BACKUP_ROOT"/*/; do
  name="$(basename "$dir")"
  if [[ "$name" =~ $STAMP_RE && "$name" < "$cutoff" ]]; then
    rm -rf -- "${BACKUP_ROOT:?}/$name"
    log "retention: removed $name"
  fi
done
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '.*.partial' -mmin +1440 -exec rm -rf -- {} +

"$REPO_DIR/infra/backup/offsite.sh" "$BACKUP_ROOT/$stamp"
