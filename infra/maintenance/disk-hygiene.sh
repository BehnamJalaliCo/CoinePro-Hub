#!/usr/bin/env bash
# infra/maintenance/disk-hygiene.sh: the weekly clean-up of what tests and
# builds leave behind on the hub's disk (2026-10-29: 92% full, mostly leftovers).
# Only ever removes:
#   - anonymous Docker volumes no container uses (a 64-hex name: test and
#     restore-test Postgres data dirs); a named volume is never touched
#   - coinepro-hq/* images older than 7 days whose tag is not one the hub
#     runs (0.1.0) or tests with (gate), and that no container uses
#   - dangling images, and build cache unused for 7 days
# It writes hq_disk_hygiene.prom for node-exporter (last run, bytes freed).
# Usage: disk-hygiene.sh [--dry-run]
set -euo pipefail
DRY=false
[[ "${1:-}" == "--dry-run" ]] && DRY=true
TEXTFILE_DIR="${HQ_TEXTFILE_DIR:-/var/lib/coinepro-hq/textfile}"
KEEP_TAGS='^(0\.1\.0|gate)$'
AGE_S=$((7 * 24 * 3600))
log() { printf '%s disk-hygiene: %s\n' "$(date -u +%FT%TZ)" "$*"; }
avail() { df --output=avail -B1 / | tail -1 | tr -d ' '; }
run() { if $DRY; then log "would: $*"; else "$@" >/dev/null 2>&1 || log "skipped (in use?): $*"; fi; }

before="$(avail)"
# 1. anonymous volumes no container uses
n=0
while read -r v; do
  [[ "$v" =~ ^[0-9a-f]{64}$ ]] || continue
  run docker volume rm "$v"
  n=$((n + 1))
done < <(docker volume ls -q -f dangling=true)
log "anonymous orphan volumes: $n"

# 2. old coinepro-hq image tags (docker refuses an image a container uses)
now="$(date +%s)"
n=0
while IFS=$'\t' read -r ref created; do
  tag="${ref##*:}"
  [[ "$tag" =~ $KEEP_TAGS ]] && continue
  ts="$(date -d "${created% [A-Z]*}" +%s 2>/dev/null || echo "$now")"
  ((now - ts > AGE_S)) || continue
  run docker rmi "$ref"
  n=$((n + 1))
done < <(docker images --format '{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}' | grep '^coinepro-hq/' | grep -v ':<none>')
log "old test image tags: $n"

# 3. dangling images and stale build cache
run docker image prune -f
run docker builder prune -f --filter until=168h

after="$(avail)"
freed=$((after > before ? after - before : 0))
log "freed $((freed / 1024 / 1024)) MiB; / is $(df --output=pcent / | tail -1 | tr -d ' ') used"
if ! $DRY && [[ -d "$TEXTFILE_DIR" ]]; then
  tmp="$(mktemp "$TEXTFILE_DIR/.hq_disk_hygiene.XXXXXX")"
  printf '# HELP hq_disk_hygiene_last_run_timestamp_seconds The last weekly clean-up.\n# TYPE hq_disk_hygiene_last_run_timestamp_seconds gauge\nhq_disk_hygiene_last_run_timestamp_seconds %s\n# HELP hq_disk_hygiene_freed_bytes Bytes the last clean-up freed.\n# TYPE hq_disk_hygiene_freed_bytes gauge\nhq_disk_hygiene_freed_bytes %s\n' "$(date +%s)" "$freed" >"$tmp"
  chmod 0644 "$tmp"
  mv "$tmp" "$TEXTFILE_DIR/hq_disk_hygiene.prom"
fi
