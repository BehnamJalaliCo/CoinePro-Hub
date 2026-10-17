#!/usr/bin/env bash
# Creates the audit-chain anchor directory (prompt 04.1 §1.11), run by
# `make up`: inside the backup set but outside the Postgres volume. The
# worker (uid 10001) appends audit-chain.jsonl there; the api reads it.
# Backup retention only removes timestamped sets, never this directory.
set -euo pipefail

BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
SERVICE_UID=10001

umask 077
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
if [[ ! -d "$BACKUP_ROOT/audit-anchors" ]] ||
  [[ "$(stat -c '%u:%a' "$BACKUP_ROOT/audit-anchors")" != "$SERVICE_UID:750" ]]; then
  sudo install -d -o "$SERVICE_UID" -g "$SERVICE_UID" -m 0750 "$BACKUP_ROOT/audit-anchors"
fi
echo "anchor-dir: $BACKUP_ROOT/audit-anchors (uid $SERVICE_UID, 0750)"
