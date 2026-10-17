#!/usr/bin/env bash
# The audit-chain anchor directory (prompt 04.1 §1.11): inside the backup set
# but outside the Postgres volume. The worker (uid 10001) appends
# audit-chain.jsonl there; the api reads it. Backup retention only removes
# timestamped sets, never this directory.
# Also the WAL archive (prompt 07 §1): /home/Hub/backups/wal, written by
# Postgres (uid 999) through WAL-G, 0700. Without it Docker would create a
# root-owned directory, archiving would fail and pg_wal would grow.
#   anchor-dir.sh          create it (sudo; `make bootstrap`, once)
#   anchor-dir.sh --check  verify it, without sudo (`make up`, prompt 05 §1.5)
set -euo pipefail

BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
SERVICE_UID=10001
PG_UID=999  # postgres in the pgvector (Debian) image
# Nothing here is created group- or world-readable unless said so below
# (prompt 05.1 §3: before, status/ created the backup root with Hub's umask).
umask 077

ok() { [[ -d "$BACKUP_ROOT/audit-anchors" ]] &&
  [[ "$(stat -c '%u:%a' "$BACKUP_ROOT/audit-anchors")" == "$SERVICE_UID:750" ]]; }
wal_ok() { [[ -d "$BACKUP_ROOT/wal" ]] && [[ "$(stat -c '%u:%a' "$BACKUP_ROOT/wal")" == "$PG_UID:700" ]]; }

if [[ "${1:-}" == "--check" ]]; then
  # Verify only (review of 5.1): a check never creates or changes anything.
  problems=()
  [[ -d "$BACKUP_ROOT" && "$(stat -c '%a' "$BACKUP_ROOT")" == 700 ]] ||
    problems+=("$BACKUP_ROOT (want a 0700 directory)")
  [[ -d "$BACKUP_ROOT/status" ]] || problems+=("$BACKUP_ROOT/status (missing)")
  ok || problems+=("$BACKUP_ROOT/audit-anchors (want uid $SERVICE_UID, 0750)")
  wal_ok || problems+=("$BACKUP_ROOT/wal (want uid $PG_UID, 0700)")
  if ((${#problems[@]})); then
    printf 'anchor-dir: %s: run make bootstrap\n' "${problems[@]}" >&2
    exit 1
  fi
  echo "anchor-dir: $BACKUP_ROOT/audit-anchors and wal ok"
  exit 0
fi

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
# The backup scripts' status files (read-only for the worker, health.hub): Hub's own, no sudo.
mkdir -p "$BACKUP_ROOT/status" && chmod 755 "$BACKUP_ROOT/status"
if ! ok; then
  sudo install -d -o "$SERVICE_UID" -g "$SERVICE_UID" -m 0750 "$BACKUP_ROOT/audit-anchors"
fi
if ! wal_ok; then
  sudo install -d -o "$PG_UID" -g "$PG_UID" -m 0700 "$BACKUP_ROOT/wal"
fi
echo "anchor-dir: $BACKUP_ROOT/audit-anchors (uid $SERVICE_UID, 0750), wal (uid $PG_UID, 0700)"
