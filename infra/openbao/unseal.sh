#!/usr/bin/env bash
# Unseals OpenBao with the key stored in $HQ_SECRETS_DIR/openbao-init.json.
# Run by coinepro-hq-openbao-unseal.timer after boot and every 5 minutes, so a
# reboot or a container restart heals itself. The key goes in on stdin and is
# never printed or passed as an argument.
#
# Exit codes: 0 unsealed / nothing to do, 1 failure.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
INIT_FILE="$SECRETS_DIR/openbao-init.json"
WAIT_SECONDS="${HQ_UNSEAL_WAIT_SECONDS:-180}"

status_json() {
  "$HQ" exec -T openbao bao status -format=json 2>/dev/null || true
}

# Wait for the container to answer (it may still be starting after a boot).
deadline=$((SECONDS + WAIT_SECONDS))
st=""
while ((SECONDS < deadline)); do
  st="$(status_json)"
  if jq -e . >/dev/null 2>&1 <<<"$st"; then break; fi
  sleep 5
done
if ! jq -e . >/dev/null 2>&1 <<<"$st"; then
  echo "openbao-unseal: OpenBao is not running; nothing to do"
  exit 0
fi

if [[ "$(jq -r .initialized <<<"$st")" != "true" ]]; then
  echo "openbao-unseal: not initialised yet (run make openbao-init); nothing to do"
  exit 0
fi
if [[ "$(jq -r .sealed <<<"$st")" == "false" ]]; then
  echo "openbao-unseal: already unsealed"
  exit 0
fi
if [[ ! -r "$INIT_FILE" ]]; then
  echo "openbao-unseal: sealed, but $INIT_FILE is not readable" >&2
  exit 1
fi

# `key=-` makes the CLI read the value from stdin.
jq -r '.unseal_keys_b64[0]' "$INIT_FILE" |
  "$HQ" exec -T openbao bao write -format=json sys/unseal key=- >/dev/null

if [[ "$(status_json | jq -r .sealed)" == "false" ]]; then
  echo "openbao-unseal: unsealed"
else
  echo "openbao-unseal: still sealed after unseal attempt" >&2
  exit 1
fi
