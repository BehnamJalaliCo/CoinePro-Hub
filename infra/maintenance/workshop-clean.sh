#!/usr/bin/env bash
# infra/maintenance/workshop-clean.sh: the hourly clean-up of the workshop's
# finished work folders (2026-11-19 and 11-20: the disk hit 100% twice and
# Postgres stopped; /home/studio/hq-workspace had grown to 16G, a long video
# leaves ~3G of build/ + ch/ + out/ behind and nothing ever removed it).
# Only ever removes:
#   - /home/studio/hq-workspace/W-NNNNNN of a work that is cancelled, delivered
#     or done and has not changed for 6 hours; a long video still waiting for
#     its YouTube upload keeps out/ (only build/ and ch/ go)
#   - /home/studio/hq-workspace/.hq/W-NNNNNN (the job's home: Claude session
#     logs) of a finished or wiped work after 7 quiet days (kept a week for debugging)
#   - /home/Hub/sites/bjtech-longform-tmp/W-NNNNNN once that upload is done
#   - when / is 90% or more: the local pg_dump sets except the newest one
#     (every set is also in restic and on Drive)
# Never a volume, restic, wal, hourly, kits or a work still queued/in progress.
# Usage: workshop-clean.sh [--dry-run]   (runs as root: the workspace is studio's)
set -euo pipefail
DRY=false
[[ "${1:-}" == "--dry-run" ]] && DRY=true
WS=/home/studio/hq-workspace
TMP=/home/Hub/sites/bjtech-longform-tmp
STATE=/home/Hub/sites/bjtech-youtube.json
BACKUPS=/home/Hub/backups
PG=coinepro-hq-postgres-1
QUIET_MIN=360
HOME_QUIET_MIN=$((7 * 24 * 60))
EMERGENCY_PCT=90
log() { printf '%s workshop-clean: %s\n' "$(date -u +%FT%TZ)" "$*"; }
rmv() { if $DRY; then log "would remove $*"; else rm -rf -- "$@"; log "removed $*"; fi; }
pct() { df --output=pcent / | tail -1 | tr -dc '0-9'; }
before="$(pct)"

# refs whose YouTube long upload is done (bjtech-youtube.json runs.<ref>.status)
done_refs=""
[[ -f "$STATE" ]] && done_refs="$(python3 -I -c '
import json,sys
s=json.load(open(sys.argv[1]))
print(" ".join(k for k,v in s.get("runs",{}).items() if v.get("status")=="done"))' "$STATE" 2>/dev/null || true)"
is_uploaded() { [[ " $done_refs " == *" $1 "* ]]; }

if [[ -d "$WS" ]]; then
  refs="$(find "$WS" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/W-[0-9]{6,9}' -printf '%f\n' | sort)"
  if [[ -n "$refs" ]]; then
    list="$(printf "'%s'," $refs)"
    rows="$(docker exec "$PG" psql -U postgres -d hq -AtF '|' -c \
      "select ref, status, coalesce(run_meta->'flow'->>'youtube','') from work.work where ref in (${list%,})")" || {
      log "postgres not reachable: nothing removed"; exit 0; }
    while IFS='|' read -r ref status yt; do
      [[ "$ref" =~ ^W-[0-9]{6,9}$ ]] || continue
      d="$WS/$ref"
      case "$status" in cancelled|delivered|done) ;; *) continue ;; esac
      if [[ -n "$(find "$d" -mmin "-$QUIET_MIN" -print -quit 2>/dev/null)" ]]; then continue; fi
      if [[ "$yt" == "queued" ]] && ! is_uploaded "$ref" && [[ "$status" != "cancelled" ]]; then
        for sub in build ch; do [[ -d "$d/$sub" ]] && rmv "$d/$sub"; done
        continue
      fi
      rmv "$d"
    done <<<"$rows"
  fi
  # job homes (.hq/W-…) of finished works, after a quiet week
  hrefs="$(find "$WS/.hq" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/W-[0-9]{6,9}' -printf '%f\n' 2>/dev/null | sort)"
  if [[ -n "$hrefs" ]]; then
    list="$(printf "'%s'," $hrefs)"
    # a ref no longer in work.work (an owner wipe) counts as finished too
    if live="$(docker exec "$PG" psql -U postgres -d hq -At -c \
      "select ref from work.work where ref in (${list%,}) and status not in ('cancelled','delivered','done')")"; then
     for ref in $hrefs; do
      [[ " $(echo $live) " == *" $ref "* ]] && continue
      [[ -d "$WS/$ref" ]] && continue
      [[ -n "$(find "$WS/.hq/$ref" -mmin "-$HOME_QUIET_MIN" -print -quit 2>/dev/null)" ]] && continue
      rmv "$WS/.hq/$ref"
     done
    fi
  fi
fi

if [[ -d "$TMP" ]]; then
  for d in "$TMP"/W-*; do
    [[ -d "$d" ]] || continue
    is_uploaded "$(basename "$d")" && rmv "$d"
  done
fi

if (( $(pct) >= EMERGENCY_PCT )); then
  log "EMERGENCY: / is $(pct)% used: removing local pg_dump sets except the newest"
  mapfile -t sets < <(find "$BACKUPS" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z' -printf '%f\n' | sort)
  if (( ${#sets[@]} > 1 )); then
    for s in "${sets[@]:0:${#sets[@]}-1}"; do rmv "$BACKUPS/$s"; done
  fi
fi
log "/ was ${before}%, now $(pct)%"
