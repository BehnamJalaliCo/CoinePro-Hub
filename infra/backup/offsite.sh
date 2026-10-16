#!/usr/bin/env bash
# Copies one backup set to Hetzner Object Storage (any S3 API) with rclone.
# OFF until HQ_BACKUP_S3_ENABLED=true and the bucket settings are filled in
# infra/compose/.env. Credentials reach the rclone container through the
# environment, never through arguments.
#
# Usage: offsite.sh <backup directory>
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$REPO_DIR/infra/compose/.env}"
RCLONE_IMAGE="rclone/rclone:1.75.2"

src="${1:?usage: offsite.sh <backup directory>}"
log() { printf '%s offsite: %s\n' "$(date -u +%FT%TZ)" "$*"; }

# Read only the HQ_BACKUP_S3_* lines; the file is not sourced.
while IFS='=' read -r key value; do
  [[ "$key" =~ ^HQ_BACKUP_S3_[A-Z_]+$ ]] && export "$key=$value"
done <"$ENV_FILE"

if [[ "${HQ_BACKUP_S3_ENABLED:-}" != "true" ]]; then
  log "disabled (set HQ_BACKUP_S3_ENABLED=true in .env once the bucket exists)"
  exit 0
fi

for var in HQ_BACKUP_S3_ENDPOINT HQ_BACKUP_S3_REGION HQ_BACKUP_S3_BUCKET \
  HQ_BACKUP_S3_ACCESS_KEY_ID HQ_BACKUP_S3_SECRET_ACCESS_KEY; do
  [[ -n "${!var:-}" ]] || { log "missing $var"; exit 1; }
done

export RCLONE_CONFIG_HQS3_TYPE=s3
export RCLONE_CONFIG_HQS3_PROVIDER=Other
export RCLONE_CONFIG_HQS3_ENDPOINT="$HQ_BACKUP_S3_ENDPOINT"
export RCLONE_CONFIG_HQS3_REGION="$HQ_BACKUP_S3_REGION"
export RCLONE_CONFIG_HQS3_ACCESS_KEY_ID="$HQ_BACKUP_S3_ACCESS_KEY_ID"
export RCLONE_CONFIG_HQS3_SECRET_ACCESS_KEY="$HQ_BACKUP_S3_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_HQS3_NO_CHECK_BUCKET=true

name="$(basename "$src")"
prefix="${HQ_BACKUP_S3_PREFIX:-coinepro-hq/postgres}"
docker run --rm --memory 256m -v "$src:/backup:ro" \
  -e RCLONE_CONFIG_HQS3_TYPE -e RCLONE_CONFIG_HQS3_PROVIDER -e RCLONE_CONFIG_HQS3_ENDPOINT \
  -e RCLONE_CONFIG_HQS3_REGION -e RCLONE_CONFIG_HQS3_ACCESS_KEY_ID \
  -e RCLONE_CONFIG_HQS3_SECRET_ACCESS_KEY -e RCLONE_CONFIG_HQS3_NO_CHECK_BUCKET \
  "$RCLONE_IMAGE" copy /backup "hqs3:$HQ_BACKUP_S3_BUCKET/$prefix/$name" --checksum
log "uploaded $name to $HQ_BACKUP_S3_BUCKET/$prefix/$name"
