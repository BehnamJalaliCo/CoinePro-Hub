#!/usr/bin/env bash
# The audit-chain anchor directory (prompt 04.1 §1.11): inside the backup set
# but outside the Postgres volume. The worker (uid 10001) appends
# audit-chain.jsonl there; the api reads it. Backup retention only removes
# timestamped sets, never this directory.
#   anchor-dir.sh          create it (sudo; `make bootstrap`, once)
#   anchor-dir.sh --check  verify it, without sudo (`make up`, prompt 05 §1.5)
set -euo pipefail

BACKUP_ROOT="${HQ_BACKUP_DIR:-/home/Hub/backups}"
SERVICE_UID=10001
# Nothing here is created group- or world-readable unless said so below
# (prompt 05.1 §3: before, status/ created the backup root with Hub's umask).
umask 077

ok() { [[ -d "$BACKUP_ROOT/audit-anchors" ]] &&
  [[ "$(stat -c '%u:%a' "$BACKUP_ROOT/audit-anchors")" == "$SERVICE_UID:750" ]]; }

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
# The backup scripts' status files (read-only for the worker, health.hub): Hub's own, no sudo.
mkdir -p "$BACKUP_ROOT/status" && chmod 755 "$BACKUP_ROOT/status"

if [[ "${1:-}" == "--check" ]]; then
  ok || { echo "anchor-dir: $BACKUP_ROOT/audit-anchors is missing or wrong: run make bootstrap" >&2; exit 1; }
  echo "anchor-dir: $BACKUP_ROOT/audit-anchors ok"
  exit 0
fi
if ! ok; then
  sudo install -d -o "$SERVICE_UID" -g "$SERVICE_UID" -m 0750 "$BACKUP_ROOT/audit-anchors"
fi
echo "anchor-dir: $BACKUP_ROOT/audit-anchors (uid $SERVICE_UID, 0750)"
