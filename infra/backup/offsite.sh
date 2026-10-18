#!/usr/bin/env bash
# The optional second off-site destination (prompt 07 §1.4): Hetzner Object
# Storage is no longer a plain copy of the nightly set but a second restic
# repository (encrypted with the same restic password, deduplicated), fed by
# infra/backup/hourly.sh every hour. It is OFF until HQ_BACKUP_S3_ENABLED=true
# and the HQ_BACKUP_S3_* bucket settings are filled in infra/compose/.env;
# hourly.sh then writes them into its private rclone.conf (never argv or env).
# The nightly set (backup.sh) stays local (7 days); this hook only says so.
#
# Usage: offsite.sh <backup directory>
set -euo pipefail

src="${1:?usage: offsite.sh <backup directory>}"
printf '%s offsite: %s stays local; off-site copies are the hourly restic snapshots (hourly.sh)\n' \
  "$(date -u +%FT%TZ)" "$(basename "$src")"
