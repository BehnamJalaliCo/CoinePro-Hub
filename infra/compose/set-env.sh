#!/usr/bin/env bash
# set-env.sh KEY on|off: switch one opt-in profile in infra/compose/.env
# (review 7.1 §0.2: `make tracing-on/-off`). Only the listed switches, only
# on/off; the file stays 600 and no other line changes (values never shown).
set -euo pipefail
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$COMPOSE_DIR/.env}"
key="${1:-}" value="${2:-}"
case "$key" in HQ_TRACING | HQ_STT | HQ_TTS | HQ_MEDIA) ;; *) echo "error: unknown switch: $key" >&2; exit 2 ;; esac
case "$value" in on | off) ;; *) echo "error: $key is on or off" >&2; exit 2 ;; esac
[[ -f "$ENV_FILE" ]] || { echo "error: $ENV_FILE is missing (make env)" >&2; exit 1; }
tmp="$(mktemp "$(dirname "$ENV_FILE")/.env.tmp.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
if grep -q "^${key}=" "$ENV_FILE"; then
  sed "s/^${key}=.*/${key}=${value}/" "$ENV_FILE" >"$tmp"
else
  { cat "$ENV_FILE"; printf '%s=%s\n' "$key" "$value"; } >"$tmp"
fi
chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"
trap - EXIT
echo "env: $key=$value"
