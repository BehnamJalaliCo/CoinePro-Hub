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
# Single source for the OPA image (also used by test-env and the opa gate).
OPA_IMAGE="$(cat "$COMPOSE_DIR/../opa/IMAGE")"
export OPA_IMAGE

# The public API and passkey login exist only with a real domain over HTTPS
# (contract §2): HQ_SITE_ADDRESS=<domain> switches on /api at the edge and
# gives the api its origin and WebAuthn RP id. Without it /api answers 404.
site="${HQ_SITE_ADDRESS:-$(sed -n 's/^HQ_SITE_ADDRESS=//p' "$ENV_FILE" | tail -n1)}"
# A domain: dot-separated labels whose last label has a letter (an IP address
# is not a domain) and is not "localhost" (no public certificate exists).
tld="${site##*.}"
if [[ "$site" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ &&
  "$tld" =~ [a-z] && "$tld" != localhost ]]; then
  export HQ_API_EDGE=on HQ_PUBLIC_ORIGIN="https://$site" HQ_WEBAUTHN_RP_ID="$site"
else
  export HQ_API_EDGE=off HQ_PUBLIC_ORIGIN="" HQ_WEBAUTHN_RP_ID=""
fi
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
