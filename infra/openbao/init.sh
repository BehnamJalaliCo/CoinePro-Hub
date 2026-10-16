#!/usr/bin/env bash
# One-time OpenBao initialisation: 1 key share, threshold 1.
# The init output (unseal key + root token) is written straight to
# $HQ_SECRETS_DIR/openbao-init.json (mode 600) and is never printed.
# Safe to re-run: does nothing when OpenBao is already initialised.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HQ="$REPO_DIR/infra/compose/hq.sh"
SECRETS_DIR="${HQ_SECRETS_DIR:-/home/Hub/.secrets}"
INIT_FILE="$SECRETS_DIR/openbao-init.json"

status_json() {
  # `bao status` exits 2 when sealed; the JSON is still valid.
  "$HQ" exec -T openbao bao status -format=json 2>/dev/null || true
}

for _ in $(seq 1 30); do
  st="$(status_json)"
  if jq -e . >/dev/null 2>&1 <<<"$st"; then break; fi
  sleep 2
done
if ! jq -e . >/dev/null 2>&1 <<<"$st"; then
  echo "openbao-init: OpenBao is not answering; is the stack up?" >&2
  exit 1
fi

if [[ "$(jq -r .initialized <<<"$st")" == "true" ]]; then
  if [[ ! -s "$INIT_FILE" ]]; then
    echo "openbao-init: OpenBao is initialised but $INIT_FILE is missing. Stop and ask the owner." >&2
    exit 1
  fi
  echo "openbao-init: already initialised"
  exit 0
fi

if [[ -e "$INIT_FILE" ]]; then
  echo "openbao-init: OpenBao is NOT initialised but $INIT_FILE exists (data volume lost?). Not touching it. Stop and ask the owner." >&2
  exit 1
fi

umask 077
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
tmp="$(mktemp "$SECRETS_DIR/.openbao-init.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

"$HQ" exec -T openbao bao operator init -key-shares=1 -key-threshold=1 -format=json >"$tmp"

if ! jq -e '(.unseal_keys_b64 | length) == 1 and (.root_token | length) > 0' "$tmp" >/dev/null; then
  echo "openbao-init: unexpected init output; aborting (file not kept)" >&2
  exit 1
fi

chmod 600 "$tmp"
mv "$tmp" "$INIT_FILE"
trap - EXIT
echo "openbao-init: initialised; keys saved to $INIT_FILE (mode 600, not shown)"

"$REPO_DIR/infra/openbao/unseal.sh"
