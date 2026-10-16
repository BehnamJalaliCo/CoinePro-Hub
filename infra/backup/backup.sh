#!/usr/bin/env bash
# Logical backup of every HQ Postgres database (pg_dump -Fc, one file per
# database) plus the roles (globals), into $HQ_BACKUP_DIR/<UTC stamp>/.
# Keeps $HQ_BACKUP_RETENTION_DAYS days (default 7), then hands the new set to
# offsite.sh (off until the Object Storage bucket is configured).
# Run nightly by coinepro-hq-backup.timer, or by hand with `make backup`.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
RETENTION_DAYS="${HQ_BACKUP_RETENTION_DAYS:-7}"
STAMP_RE='^[0-9]{8}T[0-9]{6}Z$'

log() { printf '%s backup: %s\n' "$(date -u +%FT%TZ)" "$*"; }

umask 077
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

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

pg_version="$(psql_admin -c 'SHOW server_version')"
jq -n --arg created "$stamp" --arg pg "$pg_version" \
  --arg image "$("$HQ" config --format json | jq -r '.services.postgres.image')" \
  --args '{created_at: $created, postgres_version: $pg, image: $image, databases: $ARGS.positional}' \
  "${databases[@]}" >"$work/manifest.json"
(cd "$work" && sha256sum -- *.dump globals.sql manifest.json >SHA256SUMS)

mv "$work" "$BACKUP_ROOT/$stamp"
trap - EXIT
log "complete: $BACKUP_ROOT/$stamp (${#databases[@]} databases)"

# Retention: delete only directories named like a backup stamp and older than
# the cutoff. Names sort chronologically, so a string compare is exact.
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
