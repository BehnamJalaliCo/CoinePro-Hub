#!/usr/bin/env bash
# The single entry point to `docker compose` for project coinepro-hq.
# Picks the memory profile (lean/full), loads the profile's limits and the
# secrets file, then passes every argument straight to `docker compose`.
#
# Usage: hq.sh <docker compose args...>     e.g. hq.sh ps
#        hq.sh --print-profile
# Env:   HQ_PROFILE=lean|full   force a profile (else .env, else server RAM)
#        HQ_ENV_FILE=PATH       use another secrets file (CI uses a throwaway one)
#        HQ_ALL_PROFILES=1      act on the services of every profile (used by `down`)
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$COMPOSE_DIR/.env}"
# A nominal 12 GB server reports a little less (kernel reserve), so the
# threshold is 11 GiB of MemTotal.
FULL_PROFILE_MIN_KB=$((11 * 1024 * 1024))

detect_profile() {
  local p="${HQ_PROFILE:-}"
  if [[ -z "$p" && -r "$ENV_FILE" ]]; then
    p="$(sed -n 's/^HQ_PROFILE=//p' "$ENV_FILE" | tail -n1)"
  fi
  if [[ -z "$p" ]]; then
    local mem_kb
    mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    if ((mem_kb < FULL_PROFILE_MIN_KB)); then p=lean; else p=full; fi
  fi
  case "$p" in
    lean | full) printf '%s\n' "$p" ;;
    *) echo "error: HQ_PROFILE must be lean or full (got '$p')" >&2; return 2 ;;
  esac
}

profile="$(detect_profile)"
if [[ "${1:-}" == "--print-profile" ]]; then
  printf '%s\n' "$profile"
  exit 0
fi

if [[ ! -r "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found; run 'make env' first" >&2
  exit 1
fi

export HQ_PROFILE="$profile"
profile_args=(--profile "$profile")
if [[ "${HQ_ALL_PROFILES:-0}" == "1" ]]; then
  profile_args=(--profile "*")
fi

exec docker compose \
  --project-name coinepro-hq \
  --project-directory "$COMPOSE_DIR" \
  --file "$COMPOSE_DIR/compose.yaml" \
  --env-file "$COMPOSE_DIR/profiles/$profile.env" \
  --env-file "$ENV_FILE" \
  "${profile_args[@]}" \
  "$@"
